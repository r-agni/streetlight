"""Answers for the three audiences: businesses, planners and city operations.

Everything here reads the simulation's own counters plus the city open-data
layers. Two honesty rules run through it.

First, simulated counts are expanded from agents to people by the agent weight,
and they are model output, not observation. They are reported as "modelled".

Second, the walking catchment is measured along the street network with a
Dijkstra search, not with a circle. A circle crosses freeways and water; in a
city cut by both, that is the difference between a defensible trade area and a
decorative one.
"""
from __future__ import annotations

import functools
import math
from pathlib import Path

import numpy as np
import pandas as pd

from ..engine.sim import Simulation
from ..engine.world import World

METRES_PER_DEGREE_LAT = 110_540.0


def _metres_per_degree_lon(lat: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat))


@functools.lru_cache(maxsize=2)
def _graph(root_str: str):
    """The walk network as a compressed sparse row matrix, or None."""
    path = Path(root_str) / "data" / "processed" / "graph_walk.npz"
    if not path.exists():
        return None
    from scipy.sparse import csr_matrix

    blob = np.load(path)
    n = int(blob["n_nodes"])
    return csr_matrix((blob["weights"], blob["indices"], blob["indptr"]), shape=(n, n))


def nearest_node(world: World, lon: float, lat: float) -> int:
    mx = _metres_per_degree_lon(lat)
    dx = (world.node_lon - lon) * mx
    dy = (world.node_lat - lat) * METRES_PER_DEGREE_LAT
    return int(np.argmin(dx * dx + dy * dy))


# ---------------------------------------------------------------- catchment


def walk_catchment(root: Path, world: World, lon: float, lat: float,
                   minutes: float = 10.0, speed_m_per_min: float = 78.0) -> dict:
    """Nodes reachable on foot within a time budget, and the shape they make."""
    budget = minutes * speed_m_per_min
    graph = _graph(str(root))
    origin = nearest_node(world, lon, lat)

    if graph is None:  # no graph on disk: fall back, and say so in the output
        mx = _metres_per_degree_lon(lat)
        dx = (world.node_lon - lon) * mx
        dy = (world.node_lat - lat) * METRES_PER_DEGREE_LAT
        inside = np.flatnonzero(np.hypot(dx, dy) <= budget)
        return {
            "method": "straight-line radius (street graph unavailable)",
            "minutes": minutes,
            "metres": budget,
            "nodes": inside,
            "hull": _hull(world.node_lon[inside], world.node_lat[inside]),
        }

    from scipy.sparse.csgraph import dijkstra

    distance = dijkstra(graph, directed=False, indices=origin, limit=budget)
    inside = np.flatnonzero(np.isfinite(distance))
    return {
        "method": "along the street network",
        "minutes": minutes,
        "metres": budget,
        "nodes": inside,
        "hull": _hull(world.node_lon[inside], world.node_lat[inside]),
    }


def _hull(lon: np.ndarray, lat: np.ndarray) -> list[list[float]]:
    """Convex hull of the reached nodes, as a drawable ring."""
    if len(lon) < 3:
        return []
    points = np.c_[lon, lat].astype(float)
    try:
        from scipy.spatial import ConvexHull

        ring = points[ConvexHull(points).vertices]
    except Exception:
        return []
    closed = [[float(x), float(y)] for x, y in ring]
    return closed + [closed[0]]


# ------------------------------------------------------------- foot traffic


def hourly_footfall(world: World, sim: Simulation, lon: float, lat: float,
                    radius_m: float = 150.0) -> dict:
    """Modelled people present near a point, hour by hour."""
    rows, cols = world.grid_shape
    lon0, lat0 = world.grid_origin
    dlon, dlat = world.grid_step

    mx = _metres_per_degree_lon(lat)
    reach_j = max(0, int(radius_m / (dlon * mx)))
    reach_i = max(0, int(radius_m / (dlat * METRES_PER_DEGREE_LAT)))
    cj = int((lon - lon0) / dlon)
    ci = int((lat - lat0) / dlat)
    js = [j for j in range(cj - reach_j, cj + reach_j + 1) if 0 <= j < cols]
    is_ = [i for i in range(ci - reach_i, ci + reach_i + 1) if 0 <= i < rows]
    flat = np.array([i * cols + j for i in is_ for j in js], dtype=np.int64)

    weight = float(world.agent_weight[0]) if world.n_agents else 1.0
    if flat.size == 0:
        return {"byHour": [0] * 24, "peakHour": 0, "peopleAtPeak": 0, "cells": 0,
                "hoursSimulated": []}

    # Average over the minutes of each hour actually simulated. Seeking the
    # clock replays a day, and without this the replayed hours would read as
    # several times busier than the ones seen once.
    samples = np.maximum(sim.grid_hour_samples, 1).astype(float)
    per_hour = sim.grid_hour[:, flat].sum(axis=1).astype(float) / samples
    people = (per_hour * weight).round().astype(int)
    simulated = sim.grid_hour_samples > 0
    masked = np.where(simulated, people, -1)
    peak = int(np.argmax(masked)) if simulated.any() else 0

    return {
        "byHour": people.tolist(),
        "hoursSimulated": [int(h) for h in np.flatnonzero(simulated)],
        "peakHour": peak,
        "peopleAtPeak": int(people[peak]) if simulated.any() else 0,
        "cells": int(flat.size),
        "note": (
            "Modelled presence, averaged over the minutes of each hour that "
            "have been simulated. Hours not yet reached read zero."
        ),
    }


# ------------------------------------------------------------------- places


def nearby_places(world: World, lon: float, lat: float, radius_m: float = 250.0,
                  category: str | None = None, limit: int = 25) -> list[dict]:
    """Real places around a point, best known first."""
    labels = world.categories["category"].tolist()
    mx = _metres_per_degree_lon(lat)
    dx = (world.poi_lon - lon) * mx
    dy = (world.poi_lat - lat) * METRES_PER_DEGREE_LAT
    distance = np.hypot(dx, dy)
    inside = np.flatnonzero(distance <= radius_m)

    if category:
        want = labels.index(category) if category in labels else -1
        inside = inside[world.poi_cat[inside] == want]

    order = inside[np.argsort(-world.poi_attr[inside])][:limit]
    out = []
    for i in order:
        entry = {
            "name": world.poi_name[int(i)],
            "category": labels[int(world.poi_cat[i])],
            "metres": int(distance[i]),
            "lon": float(world.poi_lon[i]),
            "lat": float(world.poi_lat[i]),
        }
        rating = float(world.poi_rating[i])
        reviews = int(world.poi_reviews[i])
        if np.isfinite(rating) and rating > 0:
            entry["rating"] = round(rating, 1)
        if reviews > 0:
            entry["reviews"] = reviews
        out.append(entry)
    return out


def category_mix(world: World, lon: float, lat: float, radius_m: float = 250.0) -> list[dict]:
    """What kind of place this area is made of."""
    labels = world.categories["category"].tolist()
    mx = _metres_per_degree_lon(lat)
    dx = (world.poi_lon - lon) * mx
    dy = (world.poi_lat - lat) * METRES_PER_DEGREE_LAT
    inside = np.flatnonzero(np.hypot(dx, dy) <= radius_m)
    if inside.size == 0:
        return []
    counts = np.bincount(world.poi_cat[inside], minlength=len(labels))
    order = np.argsort(-counts)[:10]
    return [{"category": labels[int(i)], "count": int(counts[i])}
            for i in order if counts[i] > 0]


# ----------------------------------------------------------- site selection

# categories that tend to support each other on a street
COMPLEMENTS = {
    "cafe": ("office", "retail", "clothing", "university", "transit_stop"),
    "restaurant": ("bar", "theatre", "cinema", "hotel", "retail"),
    "fast_food": ("office", "school", "transit_stop", "university"),
    "bar": ("restaurant", "nightclub", "theatre", "hotel"),
    "grocery": ("pharmacy", "bank", "convenience"),
    "retail": ("cafe", "clothing", "restaurant"),
    "clothing": ("retail", "cafe", "hotel"),
    "gym": ("cafe", "park", "grocery"),
    "pharmacy": ("grocery", "clinic", "bank"),
    "hotel": ("restaurant", "museum", "theatre", "transit_stop"),
}

COMPONENT_NAMES = {
    "footfall": "passing footfall",
    "catchment": "people within a ten-minute walk",
    "complement": "nearby complementary businesses",
    "headroom": "room against existing competition",
}
COMPONENT_WEIGHTS = {"footfall": 0.35, "catchment": 0.25, "complement": 0.20, "headroom": 0.20}


def _complement_count(world: World, lon: float, lat: float, category: str,
                      radius_m: float) -> int:
    """How many surrounding places are the kind this business likes to sit near."""
    wanted = COMPLEMENTS.get(category)
    if not wanted:
        return 0
    labels = world.categories["category"].tolist()
    ids = [labels.index(c) for c in wanted if c in labels]
    mx = _metres_per_degree_lon(lat)
    dx = (world.poi_lon - lon) * mx
    dy = (world.poi_lat - lat) * METRES_PER_DEGREE_LAT
    inside = np.flatnonzero(np.hypot(dx, dy) <= radius_m)
    if inside.size == 0:
        return 0
    return int(np.count_nonzero(np.isin(world.poi_cat[inside], ids)))


def _site_metrics(root: Path, world: World, sim: Simulation, lon: float, lat: float,
                  category: str, radius_m: float = 400.0) -> dict | None:
    """Raw, unscaled numbers for one candidate."""
    labels = world.categories["category"].tolist()
    if category not in labels:
        return None
    cat_id = labels.index(category)

    foot = hourly_footfall(world, sim, lon, lat, radius_m=150.0)
    catchment = walk_catchment(root, world, lon, lat, minutes=10.0)

    weight = float(world.agent_weight[0]) if world.n_agents else 1.0
    reached = catchment["nodes"]
    residents = 0
    if reached.size:
        mask = np.zeros(len(world.node_lon), dtype=bool)
        mask[reached] = True
        residents = int(np.count_nonzero(mask[world.agent_home]) * weight)

    mx = _metres_per_degree_lon(lat)
    dx = (world.poi_lon - lon) * mx
    dy = (world.poi_lat - lat) * METRES_PER_DEGREE_LAT
    distance = np.hypot(dx, dy)
    same = np.flatnonzero((distance <= radius_m) & (world.poi_cat == cat_id))

    beta = float(world.categories.iloc[cat_id]["huff_beta"])
    competitor_pull = float(
        np.sum(world.poi_attr[same] * np.exp(-beta * distance[same] / 1000.0))
    )
    own_pull = float(np.median(world.poi_attr[same])) if same.size else 1.0
    denominator = own_pull + competitor_pull
    headroom = own_pull / denominator if denominator > 0 else 1.0

    complements = _complement_count(world, lon, lat, category, radius_m)
    return {
        "lon": lon,
        "lat": lat,
        "footfall": foot["peopleAtPeak"],
        "peakHour": foot["peakHour"],
        "byHour": foot["byHour"],
        "catchment": residents,
        "competitors": int(same.size),
        "headroom": float(headroom),
        "complement": float(complements),
        "complementCount": complements,
        "method": catchment["method"],
    }


def _scale_across(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    """Min-max each component across the candidate set."""
    scaled: list[dict] = [{} for _ in rows]
    for key in keys:
        values = np.array([float(r[key]) for r in rows])
        low, high = float(values.min()), float(values.max())
        span = high - low
        for i, value in enumerate(values):
            # with no spread, the candidates are genuinely equal on this axis
            scaled[i][key] = 0.5 if span <= 0 else (value - low) / span
    return scaled


def _address_of(row) -> str:
    for field in ("address", "unit_address", "parcel"):
        value = getattr(row, field, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"{float(row.lat):.5f}, {float(row.lon):.5f}"


def _reading(parts: dict, metrics: dict, category: str) -> str:
    """One sentence a user can argue with."""
    best = max(parts, key=parts.get)
    worst = min(parts, key=parts.get)
    return (
        f"Strongest on {COMPONENT_NAMES[best]}, weakest on {COMPONENT_NAMES[worst]}. "
        f"{metrics['competitors']} other {category} places sit within 400 m."
    )


def rank_sites(root: Path, world: World, sim: Simulation, category: str,
               candidates: pd.DataFrame, limit: int = 8) -> list[dict]:
    """Score candidate locations against each other.

    Scoring each site against fixed absolute thresholds produced a ranking in
    which every candidate scored the same, because in a dense city they all
    clear those thresholds. The comparison a user actually wants is relative:
    of these sites, which is best. So each component is scaled across the
    candidate set before weighting, and a score only means something beside the
    others in the same list.
    """
    raw = []
    for row in candidates.itertuples():
        metrics = _site_metrics(root, world, sim, float(row.lon), float(row.lat), category)
        if metrics is None:
            return [
                {
                    "error": f"unknown category {category}",
                    "categories": world.categories["category"].tolist(),
                }
            ]
        metrics["candidateId"] = int(getattr(row, "cand_id", len(raw)))
        metrics["address"] = _address_of(row)
        raw.append(metrics)

    if not raw:
        return []

    scaled = _scale_across(raw, tuple(COMPONENT_WEIGHTS))
    out = []
    for metrics, parts in zip(raw, scaled):
        score = round(100 * sum(parts[k] * COMPONENT_WEIGHTS[k] for k in COMPONENT_WEIGHTS), 1)
        out.append(
            {
                "candidateId": metrics["candidateId"],
                "address": metrics["address"],
                "location": [metrics["lon"], metrics["lat"]],
                "category": category,
                "score": score,
                "components": {
                    k: {"relative": round(parts[k], 3), "weight": COMPONENT_WEIGHTS[k]}
                    for k in COMPONENT_WEIGHTS
                },
                "modelledPeakFootfall": metrics["footfall"],
                "peakHour": metrics["peakHour"],
                "footfallByHour": metrics["byHour"],
                "walkCatchmentResidents": metrics["catchment"],
                "competitorsWithinRadius": metrics["competitors"],
                "estimatedShareOfCategory": round(metrics["headroom"], 3),
                "complementaryPlaces": metrics["complementCount"],
                "catchmentMethod": metrics["method"],
                "reading": _reading(parts, metrics, category),
            }
        )
    out.sort(key=lambda r: -r["score"])
    for rank, entry in enumerate(out, 1):
        entry["rank"] = rank
    return out[:limit]


def site_score(root: Path, world: World, sim: Simulation, lon: float, lat: float,
               category: str, radius_m: float = 400.0) -> dict:
    """Full report for one location, including the drawable catchment."""
    metrics = _site_metrics(root, world, sim, lon, lat, category, radius_m)
    if metrics is None:
        return {
            "error": f"unknown category {category}",
            "categories": world.categories["category"].tolist(),
        }
    catchment = walk_catchment(root, world, lon, lat, minutes=10.0)
    return {
        "location": [lon, lat],
        "category": category,
        "modelledPeakFootfall": metrics["footfall"],
        "peakHour": metrics["peakHour"],
        "footfallByHour": metrics["byHour"],
        "walkCatchmentResidents": metrics["catchment"],
        "catchmentMethod": catchment["method"],
        "catchmentHull": catchment["hull"],
        "competitorsWithinRadius": metrics["competitors"],
        "estimatedShareOfCategory": round(metrics["headroom"], 3),
        "complementaryPlaces": metrics["complementCount"],
        "nearbyPlaces": nearby_places(world, lon, lat, radius_m=200.0, limit=10),
        "categoryMix": category_mix(world, lon, lat, radius_m=250.0),
        "caveat": (
            "Footfall and catchment are model output, not measurement. A single "
            "site has no score on its own: scores exist only relative to other "
            "candidates, so compare through the ranking endpoint."
        ),
    }
