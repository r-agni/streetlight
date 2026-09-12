#!/usr/bin/env python
"""Attach Google ratings and review counts to the places table.

Review count is the best free proxy we have for how busy a place actually is,
so it replaces the synthetic attractiveness term that drives destination
choice. Its biases are real and worth stating: chains and tourist spots
accumulate reviews far faster than neighbourhood businesses serving the same
number of people, and older businesses out-score newer ones. It is used as a
relative weight within a category, never as an absolute visit count.

Cost control: one nearby search covers a whole cell rather than one call per
place, which turns ~40,000 lookups into ~1,000. Every response is cached on
disk, so re-running costs nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
CACHE = ROOT / "data" / "raw" / "google_places"

ENDPOINT = "https://places.googleapis.com/v1/places:searchNearby"
FIELD_MASK = ",".join(
    [
        "places.displayName",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.primaryType",
    ]
)

# our category -> Google place types worth asking for
GOOGLE_TYPES = {
    "cafe": ["cafe", "coffee_shop"],
    "restaurant": ["restaurant"],
    "fast_food": ["fast_food_restaurant"],
    "bar": ["bar"],
    "nightclub": ["night_club"],
    "grocery": ["supermarket", "grocery_store"],
    "convenience": ["convenience_store"],
    "retail": ["store"],
    "clothing": ["clothing_store"],
    "pharmacy": ["pharmacy"],
    "gym": ["gym", "fitness_center"],
    "hotel": ["hotel"],
    "museum": ["museum", "art_gallery"],
    "theatre": ["performing_arts_theater"],
    "cinema": ["movie_theater"],
    "bank": ["bank"],
    "park": ["park"],
}
ENRICHABLE = list(GOOGLE_TYPES)

CELL_DEGREES = 0.0022  # roughly 200 m
SEARCH_RADIUS_M = 170.0


def load_key() -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GOOGLE_MAPS_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not key:
        raise SystemExit("GOOGLE_MAPS_API_KEY is not set in .env or the environment")
    return key


def search_cell(client, key: str, lat: float, lon: float, types: list[str]) -> dict:
    """One nearby search, cached on disk by cell and type set."""
    CACHE.mkdir(parents=True, exist_ok=True)
    stamp = f"{lat:.4f}_{lon:.4f}_{len(types)}"
    path = CACHE / f"{stamp}.json"
    if path.exists():
        return json.loads(path.read_text())

    body = {
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lon}, "radius": SEARCH_RADIUS_M}
        },
        "maxResultCount": 20,
        "includedTypes": types,
    }
    response = client.post(
        ENDPOINT,
        json=body,
        headers={
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": FIELD_MASK,
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    if response.status_code != 200:
        data = {"error": response.status_code, "body": response.text[:400]}
    else:
        data = response.json()
    path.write_text(json.dumps(data))
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-calls", type=int, default=900,
                        help="hard ceiling on billable requests this run")
    parser.add_argument("--match-metres", type=float, default=130.0)
    args = parser.parse_args()

    import httpx

    key = load_key()
    poi = pd.read_parquet(OUT / "pois.parquet")
    cats = pd.read_parquet(OUT / "categories.parquet")
    label_of = dict(zip(range(len(cats)), cats["category"]))
    poi["category"] = poi["cat_id"].map(label_of)

    target = poi[poi["category"].isin(ENRICHABLE)]
    if target.empty:
        raise SystemExit("no enrichable places found; run 00_bootstrap.py first")
    print(f"{len(target):,} of {len(poi):,} places are enrichable")

    # bin into cells and visit the densest first, so a capped run still covers
    # the commercial streets that matter
    cell_lat = (target["lat"] / CELL_DEGREES).round().astype(int)
    cell_lon = (target["lon"] / CELL_DEGREES).round().astype(int)
    grouped = (
        target.assign(ci=cell_lat, cj=cell_lon)
        .groupby(["ci", "cj"])
        .agg(n=("poi_id", "size"), lat=("lat", "mean"), lon=("lon", "mean"))
        .sort_values("n", ascending=False)
        .reset_index()
    )
    print(f"{len(grouped):,} cells; visiting up to {args.max_calls:,}")

    types = sorted({t for c in ENRICHABLE for t in GOOGLE_TYPES[c]})
    found: list[tuple[float, float, float, int, str]] = []
    calls = cached = errors = 0

    with httpx.Client() as client:
        for row in grouped.itertuples():
            if calls >= args.max_calls:
                print(f"reached the {args.max_calls:,} call ceiling; stopping")
                break
            was_cached = (CACHE / f"{row.lat:.4f}_{row.lon:.4f}_{len(types)}.json").exists()
            data = search_cell(client, key, float(row.lat), float(row.lon), types)
            if was_cached:
                cached += 1
            else:
                calls += 1
                time.sleep(0.06)  # stay well inside the queries-per-second limit
            if "error" in data:
                errors += 1
                if errors <= 3:
                    print(f"  request failed: {data['error']} {data.get('body', '')[:160]}")
                if errors > 25:
                    raise SystemExit("too many failed requests; check the key and its quota")
                continue
            for place in data.get("places", []):
                loc = place.get("location") or {}
                if "latitude" not in loc:
                    continue
                found.append(
                    (
                        float(loc["latitude"]),
                        float(loc["longitude"]),
                        float(place.get("rating") or 0.0),
                        int(place.get("userRatingCount") or 0),
                        (place.get("displayName") or {}).get("text", ""),
                    )
                )
            if (calls + cached) % 100 == 0:
                print(f"  {calls:,} new calls, {cached:,} cached, {len(found):,} places")

    print(f"done: {calls:,} billable calls, {cached:,} cached, {len(found):,} Google places")
    if not found:
        raise SystemExit("nothing returned; leaving the places table untouched")

    # ---- spatially match Google places onto our places -------------------
    from scipy.spatial import cKDTree

    g = np.array([[f[0], f[1]] for f in found])
    g_rating = np.array([f[2] for f in found])
    g_count = np.array([f[3] for f in found])

    lat0 = float(poi["lat"].mean())
    mx = 111_320.0 * float(np.cos(np.radians(lat0)))
    my = 110_540.0
    tree = cKDTree(np.c_[g[:, 1] * mx, g[:, 0] * my])
    dist, idx = tree.query(np.c_[poi["lon"].to_numpy() * mx, poi["lat"].to_numpy() * my], k=1)

    hit = (dist <= args.match_metres) & poi["category"].isin(ENRICHABLE).to_numpy()
    rating = np.where(hit, g_rating[idx], np.nan)
    count = np.where(hit, g_count[idx], -1)
    poi["rating"] = rating.astype(np.float32)
    poi["user_rating_count"] = count.astype(np.int32)
    print(f"matched {int(hit.sum()):,} places within {args.match_metres:.0f} m")

    # ---- fold popularity into the attractiveness term --------------------
    # log of review count, because the difference between 10 and 100 reviews
    # matters far more than between 900 and 990
    base = poi["attractiveness"].to_numpy(np.float32)
    popularity = np.where(count > 0, np.log1p(count) / np.log(200.0), 0.0)
    quality = np.where(np.isfinite(rating) & (rating > 0), rating / 4.3, 1.0)
    boosted = base * (1.0 + 1.6 * popularity) * quality
    poi["attractiveness"] = np.where(hit, boosted, base).astype(np.float32)

    poi.drop(columns=["category"]).to_parquet(OUT / "pois.parquet", index=False)

    enriched = poi[hit]
    print(
        f"attractiveness rebuilt. median review count {int(np.median(enriched['user_rating_count'])) if len(enriched) else 0}, "
        f"top places:"
    )
    for row in enriched.nlargest(8, "user_rating_count").itertuples():
        print(f"   {row.user_rating_count:>6,} reviews  {row.rating:.1f}*  {row.name[:44]}")


if __name__ == "__main__":
    main()
