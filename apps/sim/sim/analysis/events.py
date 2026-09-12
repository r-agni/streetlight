"""Model a large event and what it does to the surrounding blocks.

This is a gravity model over the simulated population, not a re-run of the
simulation. Attendees are drawn from the existing agents by distance from the
venue, weighted the way event attendance actually falls off, and the arrival
and departure curves are applied analytically.

That distinction is stated in the output. A full re-plan, where affected agents
rebuild their day around the event and re-route, is the more faithful method
and is a larger piece of work; this answers the operational questions - how
many, from where, arriving when, and which blocks fill - without claiming to be
the other thing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..engine.sim import Simulation
from ..engine.world import World

METRES_PER_DEGREE_LAT = 110_540.0

# Attendance falls off with distance far more slowly than a shopping trip:
# people travel across a metro for a concert. Beyond this, out-of-city visitors
# dominate and the resident model stops being the right tool.
EVENT_BETA_PER_KM = 0.18
RESIDENT_SHARE = 0.72  # the rest arrive from outside the simulated area

# minutes before the start that arrivals span, and after the end for departures
ARRIVAL_WINDOW = 90
DEPARTURE_WINDOW = 45


@dataclass(frozen=True)
class EventSpec:
    lon: float
    lat: float
    name: str
    attendance: int
    start_minute: int
    end_minute: int


def _metres_per_degree_lon(lat: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat))


def simulate(world: World, sim: Simulation, spec: EventSpec) -> dict:
    """Who comes, from where, when they arrive, and what fills up."""
    weight = float(world.agent_weight[0]) if world.n_agents else 1.0
    mx = _metres_per_degree_lon(spec.lat)

    # distance from every agent's home to the venue
    home_lon = world.node_lon[world.agent_home]
    home_lat = world.node_lat[world.agent_home]
    dx = (home_lon - spec.lon) * mx
    dy = (home_lat - spec.lat) * METRES_PER_DEGREE_LAT
    km = np.hypot(dx, dy) / 1000.0

    pull = np.exp(-EVENT_BETA_PER_KM * km)
    total_pull = float(pull.sum())
    if total_pull <= 0:
        return {"error": "no population near this venue"}

    resident_attendance = spec.attendance * RESIDENT_SHARE
    expected_agents = resident_attendance / max(weight, 1e-6)
    probability = np.clip(pull / total_pull * expected_agents, 0.0, 1.0)

    rng = np.random.default_rng(abs(hash((spec.name, spec.attendance))) % (2**32))
    attending = np.flatnonzero(rng.random(len(probability)) < probability)
    modelled_people = int(len(attending) * weight)

    # where they come from, by distance band
    bands = [(0, 1), (1, 3), (3, 6), (6, 100)]
    origins = []
    for lo, hi in bands:
        in_band = int(np.count_nonzero((km[attending] >= lo) & (km[attending] < hi)))
        origins.append(
            {
                "band": f"{lo}-{hi} km" if hi < 100 else f"over {lo} km",
                "people": int(in_band * weight),
                "share": round(in_band / max(len(attending), 1), 3),
            }
        )

    # likely mode, from distance alone
    walkable = int(np.count_nonzero(km[attending] < 1.2) * weight)
    transit = int(np.count_nonzero((km[attending] >= 1.2) & (km[attending] < 12)) * weight)
    driving = int(np.count_nonzero(km[attending] >= 12) * weight)
    outside = int(spec.attendance - modelled_people)

    # arrival curve: most people arrive in the last third of the window
    arrival = _curve(spec.start_minute - ARRIVAL_WINDOW, spec.start_minute,
                     spec.attendance, skew=2.4)
    departure = _curve(spec.end_minute, spec.end_minute + DEPARTURE_WINDOW,
                       spec.attendance, skew=0.5)

    # which blocks fill: cells near the venue, and how crowded they get
    crowding = _crowding(world, spec, spec.attendance)

    # businesses that sit inside the crowd
    uplift = _business_uplift(world, spec)

    return {
        "event": {
            "name": spec.name,
            "venue": [spec.lon, spec.lat],
            "attendance": spec.attendance,
            "startMinute": spec.start_minute,
            "endMinute": spec.end_minute,
        },
        "method": (
            "Gravity model over the simulated resident population. Attendance "
            "falls off with distance from the venue; arrival and departure "
            "curves are applied analytically rather than re-simulated."
        ),
        "modelledFromResidents": modelled_people,
        "assumedFromOutsideTheCity": outside,
        "originBands": origins,
        "likelyMode": {
            "walk": walkable,
            "transit": transit,
            "drive": driving,
            "fromOutside": outside,
        },
        "arrivalByQuarterHour": arrival,
        "departureByQuarterHour": departure,
        "peakArrivalMinute": spec.start_minute - 15,
        "crowding": crowding,
        "businessUplift": uplift,
        "attendeeHomeSample": _sample_origins(world, attending, 400),
    }


def _curve(start: int, end: int, total: int, skew: float) -> list[dict]:
    """Arrivals or departures in quarter-hour buckets."""
    span = max(end - start, 1)
    buckets = max(1, span // 15)
    out = []
    weights = []
    for b in range(buckets):
        t = (b + 0.5) / buckets
        # skew > 1 loads the end of the window, < 1 loads the start
        weights.append(t**skew if skew >= 1 else (1 - t) ** (1 / max(skew, 0.05)))
    scale = sum(weights) or 1.0
    for b in range(buckets):
        out.append(
            {
                "minute": start + b * 15,
                "people": int(round(total * weights[b] / scale)),
            }
        )
    return out


def _crowding(world: World, spec: EventSpec, attendance: int) -> list[dict]:
    """How many people per grid cell in the rings around the venue."""
    mx = _metres_per_degree_lon(spec.lat)
    rings = [(0, 150), (150, 300), (300, 600)]
    # crowd thins with distance from the doors; shares chosen to sum to one
    shares = [0.55, 0.30, 0.15]
    out = []
    for (lo, hi), share in zip(rings, shares):
        area_m2 = math.pi * (hi**2 - lo**2)
        people = int(attendance * share)
        out.append(
            {
                "ring": f"{lo}-{hi} m from the venue",
                "people": people,
                "peoplePerSquareMetre": round(people / max(area_m2, 1), 3),
                "comfort": _comfort(people / max(area_m2, 1)),
            }
        )
    return out


def _comfort(density: float) -> str:
    """Plain reading of pedestrian density, loosely following Fruin's levels."""
    if density < 0.3:
        return "free flowing"
    if density < 0.7:
        return "busy but walkable"
    if density < 1.4:
        return "constrained, slow walking"
    return "congested, queuing likely"


def _business_uplift(world: World, spec: EventSpec) -> list[dict]:
    """Places within the crowd, and a share of attendees they might see."""
    labels = world.categories["category"].tolist()
    mx = _metres_per_degree_lon(spec.lat)
    dx = (world.poi_lon - spec.lon) * mx
    dy = (world.poi_lat - spec.lat) * METRES_PER_DEGREE_LAT
    distance = np.hypot(dx, dy)
    near = np.flatnonzero(distance <= 500)
    if near.size == 0:
        return []

    # rough share of attendees who stop somewhere before or after
    capture = {"bar": 0.10, "restaurant": 0.09, "fast_food": 0.06,
               "cafe": 0.04, "convenience": 0.03, "retail": 0.02}
    grouped: dict[str, dict] = {}
    for i in near:
        name = labels[int(world.poi_cat[i])]
        rate = capture.get(name)
        if rate is None:
            continue
        entry = grouped.setdefault(name, {"category": name, "places": 0, "peopleAcrossAll": 0})
        entry["places"] += 1
        entry["peopleAcrossAll"] = int(spec.attendance * rate)
    out = sorted(grouped.values(), key=lambda e: -e["peopleAcrossAll"])
    for entry in out:
        entry["peoplePerPlace"] = int(entry["peopleAcrossAll"] / max(entry["places"], 1))
    return out


def _sample_origins(world: World, attending: np.ndarray, limit: int) -> list[list[float]]:
    """A sample of attendee home locations, for drawing flow on the map."""
    if attending.size == 0:
        return []
    step = max(1, attending.size // limit)
    picked = attending[::step][:limit]
    nodes = world.agent_home[picked]
    return [
        [round(float(world.node_lon[n]), 5), round(float(world.node_lat[n]), 5)]
        for n in nodes
    ]
