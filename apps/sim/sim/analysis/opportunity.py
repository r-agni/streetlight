"""Where demand for a specific concept outruns what already trades there.

A category answer ("open a cafe in the Mission") is nearly useless, because the
Mission has two hundred cafes. The question worth answering is narrower: for
*this* concept, where is there appetite that nothing is currently serving?

Three measurements, kept separate so a user can argue with each:

**Supply** is counted from real listings, not guessed. Place names are searched
for the concept's own words across the Overture catalog, and Google Places text
search is queried for the same words so that businesses too new or too small to
be in the catalog still count against the opportunity.

**Demand** is a proxy, and is labelled as one. It combines modelled footfall,
residents within a walk, and - importantly - the presence of *adjacent*
businesses. Somewhere with six Indian restaurants and no chai house has
demonstrated appetite for the cuisine without anyone serving that format; that
is a far better signal than raw population.

**The gap** is demand relative to supply. It is a ranking device, not a revenue
forecast, and nothing here should be read as one.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..engine.sim import Simulation
from ..engine.world import World
from . import insight

METRES_PER_DEGREE_LAT = 110_540.0

# Cuisine and concept words that imply an existing community or market for
# adjacent formats. Used to find demonstrated appetite, not to infer ethnicity
# of residents, which this model has no data for and does not attempt.
ADJACENCY_HINTS: dict[str, tuple[str, ...]] = {
    "indian": ("indian", "curry", "tandoor", "masala", "dosa", "punjab", "biryani", "chaat"),
    "chai": ("indian", "chai", "tea", "curry", "masala", "dosa", "samosa"),
    "chinese": ("chinese", "szechuan", "dim sum", "wok", "noodle", "dumpling"),
    "japanese": ("japanese", "sushi", "ramen", "izakaya", "udon"),
    "korean": ("korean", "kimchi", "bibimbap", "bbq"),
    "mexican": ("taqueria", "mexican", "taco", "burrito", "mariscos"),
    "thai": ("thai", "pad", "bangkok"),
    "vietnamese": ("pho", "vietnamese", "banh"),
    "ethiopian": ("ethiopian", "injera", "habesha"),
    "italian": ("italian", "pizzeria", "trattoria", "pasta"),
    "coffee": ("coffee", "espresso", "roaster", "cafe"),
    "wine": ("wine", "vino", "enoteca", "bottle"),
    "bakery": ("bakery", "patisserie", "boulangerie", "pastry"),
}


@dataclass(frozen=True)
class Area:
    name: str
    lon: float
    lat: float


def _metres_per_degree_lon(lat: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat))


def _google_key(root: Path) -> str | None:
    env = root / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GOOGLE_MAPS_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    return os.environ.get("GOOGLE_MAPS_API_KEY") or None


def _matches(names: list[str], terms: list[str]) -> np.ndarray:
    """Indices of catalog places whose name contains any of the search terms."""
    if not terms:
        return np.array([], dtype=int)
    pattern = re.compile("|".join(re.escape(t.strip().lower()) for t in terms if t.strip()))
    return np.array(
        [i for i, name in enumerate(names) if name and pattern.search(name.lower())],
        dtype=int,
    )


def _adjacency_terms(concept: str, search_terms: list[str]) -> tuple[str, ...]:
    """Words that indicate a related market already trading nearby."""
    text = " ".join([concept, *search_terms]).lower()
    found: list[str] = []
    for key, words in ADJACENCY_HINTS.items():
        if key in text or any(w in text for w in words):
            found.extend(words)
    return tuple(dict.fromkeys(found)) or tuple(search_terms)


def google_supply(root: Path, terms: list[str], areas: list[Area],
                  budget: int = 12) -> tuple[dict[str, list[dict]], int, bool]:
    """Search real listings per area. Returns hits, calls made, and whether it ran."""
    key = _google_key(root)
    if not key:
        return {}, 0, False

    import httpx

    found: dict[str, list[dict]] = {a.name: [] for a in areas}
    calls = 0
    query = " ".join(terms[:3])

    with httpx.Client() as client:
        for area in areas:
            if calls >= budget:
                break
            try:
                response = client.post(
                    "https://places.googleapis.com/v1/places:searchText",
                    headers={
                        "X-Goog-Api-Key": key,
                        "Content-Type": "application/json",
                        "X-Goog-FieldMask": ",".join(
                            [
                                "places.displayName",
                                "places.location",
                                "places.rating",
                                "places.userRatingCount",
                                "places.primaryType",
                                "places.businessStatus",
                            ]
                        ),
                    },
                    json={
                        "textQuery": f"{query} in {area.name}, San Francisco",
                        "maxResultCount": 20,
                        "locationBias": {
                            "circle": {
                                "center": {"latitude": area.lat, "longitude": area.lon},
                                "radius": 1200.0,
                            }
                        },
                    },
                    timeout=25,
                )
                calls += 1
                if response.status_code != 200:
                    continue
                for place in response.json().get("places", []):
                    if place.get("businessStatus") not in (None, "OPERATIONAL"):
                        continue
                    location = place.get("location") or {}
                    if "latitude" not in location:
                        continue
                    # keep only results genuinely inside the area's radius
                    mx = _metres_per_degree_lon(area.lat)
                    dx = (location["longitude"] - area.lon) * mx
                    dy = (location["latitude"] - area.lat) * METRES_PER_DEGREE_LAT
                    if math.hypot(dx, dy) > 1400:
                        continue
                    found[area.name].append(
                        {
                            "name": (place.get("displayName") or {}).get("text", ""),
                            "rating": place.get("rating"),
                            "reviews": place.get("userRatingCount") or 0,
                            "type": place.get("primaryType"),
                            "lon": location["longitude"],
                            "lat": location["latitude"],
                        }
                    )
            except Exception:
                continue
    return found, calls, True


def analyse(root: Path, world: World, sim: Simulation, concept: str,
            search_terms: list[str], areas: list[Area],
            category: str | None = None) -> dict:
    """Rank areas by appetite for a concept against what already serves it."""
    names = world.poi_name
    labels = world.categories["category"].tolist()
    weight = float(world.agent_weight[0]) if world.n_agents else 1.0

    direct = _matches(names, search_terms)
    adjacency = _adjacency_terms(concept, search_terms)
    related = _matches(names, list(adjacency))

    google, google_calls, google_ran = google_supply(root, search_terms, areas)

    rows = []
    for area in areas:
        mx = _metres_per_degree_lon(area.lat)
        dx = (world.poi_lon - area.lon) * mx
        dy = (world.poi_lat - area.lat) * METRES_PER_DEGREE_LAT
        distance = np.hypot(dx, dy)
        within = distance <= 900

        direct_here = [int(i) for i in direct if within[i]]
        related_here = [int(i) for i in related if within[i] and i not in set(direct_here)]

        listings = google.get(area.name, [])
        listing_names = {entry["name"].lower() for entry in listings}
        catalog_names = {names[i].lower() for i in direct_here}
        supply_count = len(listing_names | catalog_names)

        # review counts on what already trades are the closest thing to a
        # revealed-appetite measure that is free and public
        reviews = [entry["reviews"] for entry in listings if entry["reviews"]]
        ratings = [entry["rating"] for entry in listings if entry["rating"]]
        median_reviews = int(np.median(reviews)) if reviews else 0
        median_rating = round(float(np.median(ratings)), 2) if ratings else None

        foot = insight.hourly_footfall(world, sim, area.lon, area.lat, radius_m=250.0)
        catchment = insight.walk_catchment(root, world, area.lon, area.lat, minutes=10.0)
        residents = 0
        if catchment["nodes"].size:
            mask = np.zeros(len(world.node_lon), dtype=bool)
            mask[catchment["nodes"]] = True
            residents = int(np.count_nonzero(mask[world.agent_home]) * weight)

        rows.append(
            {
                "area": area.name,
                "lon": area.lon,
                "lat": area.lat,
                "supplyDirect": supply_count,
                "supplyFromListings": len(listings),
                "supplyFromCatalog": len(direct_here),
                "adjacentBusinesses": len(related_here),
                "medianReviewsOfExisting": median_reviews,
                "medianRatingOfExisting": median_rating,
                "modelledPeakFootfall": foot["peopleAtPeak"],
                "peakHour": foot["peakHour"],
                "residentsWithinTenMinuteWalk": residents,
                "examplesAlreadyTrading": [
                    entry["name"] for entry in sorted(
                        listings, key=lambda e: -(e["reviews"] or 0)
                    )[:4]
                ] or [names[i] for i in direct_here[:4]],
                "adjacentExamples": [names[i] for i in related_here[:5]],
            }
        )

    _score(rows)
    rows.sort(key=lambda r: -r["opportunityScore"])
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank

    return {
        "concept": concept,
        "searchTerms": search_terms,
        "adjacencyTerms": list(adjacency)[:10],
        "category": category,
        "areas": rows,
        "listingsSearched": google_ran,
        "listingCalls": google_calls,
        "method": (
            "Supply is counted from real listings: place names in the catalog "
            "plus a Google Places text search per area. Demand is a proxy built "
            "from modelled footfall, residents within a ten-minute walk, and "
            "adjacent businesses that show the market already exists. The score "
            "ranks areas against each other and is not a revenue forecast."
        ),
        "caveats": [
            "Adjacent businesses indicate a market for the cuisine, not the "
            "ethnicity or preferences of residents, which this model has no data for.",
            "Review counts favour older and more central businesses, so a low "
            "count can mean new rather than unwanted.",
            "Footfall and catchment are simulation output, not measurement.",
        ],
    }


def _score(rows: list[dict]) -> None:
    """Scale each signal across the areas compared, then combine."""
    if not rows:
        return

    def scaled(key: str) -> list[float]:
        values = np.array([float(r[key]) for r in rows])
        low, high = values.min(), values.max()
        span = high - low
        return [0.5] * len(rows) if span <= 0 else list((values - low) / span)

    footfall = scaled("modelledPeakFootfall")
    residents = scaled("residentsWithinTenMinuteWalk")
    adjacent = scaled("adjacentBusinesses")
    supply = scaled("supplyDirect")

    for i, row in enumerate(rows):
        demand = 0.40 * footfall[i] + 0.25 * residents[i] + 0.35 * adjacent[i]
        # supply suppresses opportunity rather than cancelling it: a busy street
        # with one competitor can still be the right answer
        gap = demand * (1.0 - 0.55 * supply[i])
        row["demandProxy"] = round(demand, 3)
        row["supplyPressure"] = round(supply[i], 3)
        row["opportunityScore"] = round(100 * gap, 1)
        row["reading"] = _reading(row, footfall[i], residents[i], adjacent[i], supply[i])


def _reading(row: dict, footfall: float, residents: float, adjacent: float,
             supply: float) -> str:
    parts = []
    if adjacent > 0.6 and supply < 0.4:
        parts.append(
            f"{row['adjacentBusinesses']} related businesses trade here but only "
            f"{row['supplyDirect']} serve the concept directly"
        )
    elif supply > 0.6:
        parts.append(f"already served by {row['supplyDirect']} places")
    if footfall > 0.6:
        parts.append(f"heavy passing trade, peaking {row['modelledPeakFootfall']:,} at {row['peakHour']:02d}:00")
    if residents > 0.6:
        parts.append(f"{row['residentsWithinTenMinuteWalk']:,} people within a ten-minute walk")
    if not parts:
        parts.append("no signal stands out here")
    return "; ".join(parts) + "."
