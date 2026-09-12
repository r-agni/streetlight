#!/usr/bin/env python
"""Pull the San Francisco open-data layers the city and planners actually read.

Complaints, incidents, zoning, parcels, permits and vacancy. Everything comes
from the Socrata endpoints on data.sf.gov, which are free and need only an
optional app token to lift the shared anonymous rate limit.

Each dataset is cached as raw JSON under data/raw/datasf so a re-run costs
nothing, and reduced to a tidy parquet table under data/processed.

Note the portal moved: data.sfgov.org now redirects to data.sf.gov, and the
redirect drops query parameters on some clients, so the new host is used
directly here.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw" / "datasf"
BASE = "https://data.sf.gov/resource"

# dataset id -> (output name, page size, optional SoQL where clause)
DATASETS = {
    "vw6y-z8j6": ("cases_311", 50_000, "requested_datetime > '{since}'"),
    "wg3w-h783": ("police_incidents", 50_000, "incident_datetime > '{since}'"),
    "rzkk-54yv": ("commercial_vacancy", 50_000, None),
    "i98e-djp9": ("building_permits", 50_000, "filed_date > '{since_old}'"),
    "c5ge-t6pj": ("land_use", 50_000, None),
}

# how far back to pull the time-series datasets
MONTHS_BACK = 12
PERMIT_YEARS_BACK = 3


def load_token() -> str | None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("SODA_APP_TOKEN="):
                token = line.split("=", 1)[1].strip()
                if token:
                    return token
    return os.environ.get("SODA_APP_TOKEN") or None


def fetch(client, dataset: str, where: str | None, page: int, token: str | None,
          limit: int = 50_000) -> list[dict]:
    """One page of a Socrata dataset, cached on disk."""
    RAW.mkdir(parents=True, exist_ok=True)
    cache = RAW / f"{dataset}_{page}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    params = {"$limit": limit, "$offset": page * limit, "$order": ":id"}
    if where:
        params["$where"] = where
    if token:
        params["$$app_token"] = token

    last: Exception | None = None
    for attempt in range(4):
        try:
            response = client.get(f"{BASE}/{dataset}.json", params=params, timeout=180)
            response.raise_for_status()
            rows = response.json()
            cache.write_text(json.dumps(rows))
            return rows
        except Exception as exc:  # the busier feeds time out under load
            last = exc
            if attempt < 3:
                wait = 5 * (attempt + 1)
                print(f"    retry {attempt + 1}/3 after {type(exc).__name__} "
                      f"(waiting {wait}s)", flush=True)
                time.sleep(wait)
    raise last  # type: ignore[misc]


def pull(client, dataset: str, where: str | None, token: str | None,
         max_pages: int) -> pd.DataFrame:
    frames = []
    for page in range(max_pages):
        rows = fetch(client, dataset, where, page, token)
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        print(f"    page {page + 1}: {len(rows):,} rows", flush=True)
        if len(rows) < 50_000:
            break
        time.sleep(0.2)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def first_column(df: pd.DataFrame, *names: str) -> pd.Series | None:
    """Socrata column names drift between datasets and over time."""
    for name in names:
        if name in df.columns:
            return df[name]
    return None


def coordinates(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Extract longitude and latitude however this dataset happens to store them."""
    lon = first_column(df, "longitude", "long", "lon", "x")
    lat = first_column(df, "latitude", "lat", "y")
    if lon is not None and lat is not None:
        return (
            pd.to_numeric(lon, errors="coerce").to_numpy(),
            pd.to_numeric(lat, errors="coerce").to_numpy(),
        )

    # otherwise the dataset carries GeoJSON, which may be a point, a polygon
    # or a multipolygon; parcels and land use are areas, so take a centre
    for name in ("point", "location", "the_geom", "shape", "multipolygon"):
        if name in df.columns:
            centres = df[name].map(_representative_point)
            return (
                np.array([c[0] for c in centres], dtype=float),
                np.array([c[1] for c in centres], dtype=float),
            )
    return np.full(len(df), np.nan), np.full(len(df), np.nan)


def _representative_point(value) -> tuple[float, float]:
    """A single longitude/latitude for any GeoJSON geometry, or NaN."""
    if not isinstance(value, dict):
        return (np.nan, np.nan)
    coords = value.get("coordinates")
    if coords is None:
        return (np.nan, np.nan)

    # descend until the first pair of numbers, collecting the ring we land in
    node = coords
    while isinstance(node, list) and node and isinstance(node[0], list):
        if node and isinstance(node[0], list) and node[0] and not isinstance(node[0][0], list):
            break  # `node` is now a ring of coordinate pairs
        node = node[0]

    if isinstance(node, list) and node and isinstance(node[0], (int, float)):
        return (float(node[0]), float(node[1]))  # a bare point
    if isinstance(node, list) and node and isinstance(node[0], list):
        xs = [float(p[0]) for p in node if isinstance(p, list) and len(p) >= 2]
        ys = [float(p[1]) for p in node if isinstance(p, list) and len(p) >= 2]
        if xs:
            return (sum(xs) / len(xs), sum(ys) / len(ys))
    return (np.nan, np.nan)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pages", type=int, default=4)
    parser.add_argument("--only", default=None, help="one dataset id")
    args = parser.parse_args()

    import httpx

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    west, south, east, north = cfg["bbox"]
    token = load_token()
    print("app token:", "present" if token else "absent (shared rate limit)")
    OUT.mkdir(parents=True, exist_ok=True)

    since = (pd.Timestamp.now() - pd.DateOffset(months=MONTHS_BACK)).strftime("%Y-%m-%dT00:00:00")
    since_old = (pd.Timestamp.now() - pd.DateOffset(years=PERMIT_YEARS_BACK)).strftime(
        "%Y-%m-%dT00:00:00"
    )

    summary = {}
    with httpx.Client(follow_redirects=True) as client:
        for dataset, (name, _, where_template) in DATASETS.items():
            if args.only and dataset != args.only:
                continue
            where = (
                where_template.format(since=since, since_old=since_old)
                if where_template
                else None
            )
            print(f"\n{name}  ({dataset})")
            try:
                df = pull(client, dataset, where, token, args.max_pages)
            except Exception as exc:
                print(f"    failed: {type(exc).__name__}: {str(exc)[:160]}")
                continue
            if df.empty:
                print("    no rows returned")
                continue

            lon, lat = coordinates(df)
            df["lon"] = lon
            df["lat"] = lat
            located = df[
                df["lon"].between(west, east) & df["lat"].between(south, north)
            ].reset_index(drop=True)

            keep = _reduce(name, located)
            keep.to_parquet(OUT / f"{name}.parquet", index=False)
            summary[name] = len(keep)
            print(f"    {len(df):,} rows -> {len(keep):,} located in San Francisco")

    print("\nwrote:")
    for name, count in summary.items():
        print(f"  {count:>8,}  {name}.parquet")


def _reduce(name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Keep the columns each layer is actually read for."""
    # Column names verified against the live feeds, not assumed: Socrata
    # spellings differ per dataset and several are truncated to ten characters
    # in the older land-use export.
    if name == "cases_311":
        cols = {
            "service_request_id": "case_id",
            "requested_datetime": "opened",
            "closed_date": "closed",
            "status_description": "status",
            "service_name": "category",
            "service_subtype": "subcategory",
            "service_details": "detail",
            "analysis_neighborhood": "neighborhood",
            "police_district": "district",
            "address": "address",
            "agency_responsible": "agency",
            "source": "source",
        }
    elif name == "police_incidents":
        cols = {
            "incident_id": "incident_id",
            "incident_datetime": "opened",
            "incident_day_of_week": "day_of_week",
            "incident_category": "category",
            "incident_subcategory": "subcategory",
            "incident_description": "description",
            "analysis_neighborhood": "neighborhood",
            "police_district": "district",
            "resolution": "resolution",
            "intersection": "address",
        }
    elif name == "commercial_vacancy":
        cols = {
            "parcelnumber": "parcel",
            "parcelsitusaddress": "address",
            "linaddress": "unit_address",
            "entity": "entity",
            "filertype": "filer_type",
            "vacant": "vacant",
            "taxyear": "tax_year",
            "rate": "rate",
            "analysis_neighborhood": "neighborhood",
        }
    elif name == "building_permits":
        cols = {
            "permit_number": "permit",
            "filed_date": "filed",
            "issued_date": "issued",
            "status": "status",
            "permit_type_definition": "permit_type",
            "street_number": "street_number",
            "street_name": "street",
            "street_suffix": "street_suffix",
            "description": "description",
            "existing_use": "existing_use",
            "proposed_use": "proposed_use",
            "estimated_cost": "estimated_cost",
            "revised_cost": "revised_cost",
            "existing_units": "existing_units",
            "proposed_units": "proposed_units",
            "neighborhoods_analysis_boundaries": "neighborhood",
        }
    elif name == "land_use":
        cols = {
            "mapblklot": "block_lot",
            "landuse": "land_use",
            "geography_type": "geography_type",
            "resunits": "residential_units",
            "retail": "retail_sqft",
            "mips": "office_sqft",
            "pdr": "industrial_sqft",
            "cie": "institutional_sqft",
            "med": "medical_sqft",
            "visitor": "visitor_sqft",
            "total_comm": "commercial_sqft",
            "residentia": "residential_sqft",
            "open_space": "open_space_sqft",
            "garage": "garage_sqft",
        }
    else:
        drop = [c for c in df.columns if c in ("the_geom", "shape", "point", "location")]
        return df.drop(columns=drop, errors="ignore")

    present = {src: dst for src, dst in cols.items() if src in df.columns}
    missing = [src for src in cols if src not in df.columns]
    if missing:
        print(f"    note: {len(missing)} expected column(s) absent: {', '.join(missing[:6])}")
    out = df[list(present)].rename(columns=present)
    out["lon"] = df["lon"].to_numpy()
    out["lat"] = df["lat"].to_numpy()
    return out


if __name__ == "__main__":
    main()
