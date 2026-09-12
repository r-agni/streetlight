"""Load the processed dataset into flat numpy arrays the tick loop can use.

Everything here is read-only once built. Positions along a route are found with
a single vectorised binary search over a globally monotonic distance key, which
keeps per-tick cost independent of the number of routes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# Stride that separates one route's distance keys from the next. Any value
# larger than the longest possible route works; float64 keeps full precision.
ROUTE_KEY_STRIDE = 1.0e7


@dataclass
class World:
    """Immutable simulation inputs."""

    # street network
    node_lon: np.ndarray
    node_lat: np.ndarray

    # routes, as a flat vertex table
    route_start: np.ndarray  # int64, index of first vertex
    route_n: np.ndarray  # int32, vertex count
    route_len: np.ndarray  # float32, metres
    vert_lon: np.ndarray
    vert_lat: np.ndarray
    vert_cum: np.ndarray  # float32, metres along the route
    vert_key: np.ndarray  # float64, globally monotonic search key

    # points of interest
    poi_lon: np.ndarray
    poi_lat: np.ndarray
    poi_cat: np.ndarray
    poi_node: np.ndarray
    poi_name: list[str]
    poi_attr: np.ndarray

    # agents
    agent_home: np.ndarray
    agent_work: np.ndarray
    agent_arch: np.ndarray
    agent_segment: np.ndarray
    agent_weight: np.ndarray

    # padded per-agent schedule table, shape (n_agents, max_slots)
    sch_cat: np.ndarray
    sch_poi: np.ndarray
    sch_node: np.ndarray
    sch_start: np.ndarray
    sch_end: np.ndarray
    sch_mode: np.ndarray
    sch_route: np.ndarray
    sch_count: np.ndarray

    # density grid
    grid_origin: tuple[float, float]  # lon, lat of cell (0, 0)
    grid_step: tuple[float, float]  # degrees per cell
    grid_shape: tuple[int, int]  # rows, cols

    categories: pd.DataFrame
    bounds: tuple[float, float, float, float]
    manifest: dict = field(default_factory=dict)

    @property
    def n_agents(self) -> int:
        return int(self.agent_home.shape[0])

    @property
    def n_pois(self) -> int:
        return int(self.poi_lon.shape[0])

    @property
    def max_slots(self) -> int:
        return int(self.sch_cat.shape[1])


# density grid resolution in degrees; roughly 100 m at San Francisco's latitude
GRID_DLAT = 0.0009
GRID_DLON = 0.00114


def load_world(root: Path) -> World:
    """Read data/processed into memory."""
    proc = root / "data" / "processed"
    cfg = yaml.safe_load((root / "config.yaml").read_text())

    nodes = pd.read_parquet(proc / "network_nodes.parquet")
    routes = pd.read_parquet(proc / "routes.parquet")
    verts = pd.read_parquet(proc / "routes_verts.parquet")
    pois = pd.read_parquet(proc / "pois.parquet")
    agents = pd.read_parquet(proc / "agents.parquet")
    sched = pd.read_parquet(proc / "schedules.parquet")
    cats = pd.read_parquet(proc / "categories.parquet")
    manifest = json.loads((proc / "manifest.json").read_text())

    node_lon = nodes["lon"].to_numpy(np.float32)
    node_lat = nodes["lat"].to_numpy(np.float32)

    route_start = routes["vert_start"].to_numpy(np.int64)
    route_n = routes["n_verts"].to_numpy(np.int32)
    route_len = routes["length_m"].to_numpy(np.float32)
    vert_lon = verts["lon"].to_numpy(np.float32)
    vert_lat = verts["lat"].to_numpy(np.float32)
    vert_cum = verts["cum_m"].to_numpy(np.float32)

    # one monotonically increasing key across every route, so a single
    # searchsorted locates the segment for any (route, distance) pair
    vert_route = np.repeat(np.arange(len(route_start), dtype=np.int64), route_n)
    vert_key = vert_cum.astype(np.float64) + vert_route * ROUTE_KEY_STRIDE

    # ---- schedules into a dense padded table -----------------------------
    n_agents = int(agents["agent_id"].max()) + 1 if len(agents) else 0
    max_slots = int(sched["slot"].max()) + 1 if len(sched) else 1
    shape = (n_agents, max_slots)

    sch_cat = np.zeros(shape, np.int16)
    sch_poi = np.full(shape, -1, np.int32)
    sch_node = np.zeros(shape, np.int32)
    sch_start = np.zeros(shape, np.int16)
    sch_end = np.full(shape, 1440, np.int16)
    sch_mode = np.zeros(shape, np.int8)
    sch_route = np.full(shape, -1, np.int32)

    aid = sched["agent_id"].to_numpy(np.int32)
    slot = sched["slot"].to_numpy(np.int32)
    sch_cat[aid, slot] = sched["cat_id"].to_numpy(np.int16)
    sch_poi[aid, slot] = sched["poi_id"].to_numpy(np.int32)
    sch_node[aid, slot] = sched["node_id"].to_numpy(np.int32)
    sch_start[aid, slot] = np.clip(sched["start_min"].to_numpy(), 0, 32767).astype(np.int16)
    sch_end[aid, slot] = np.clip(sched["end_min"].to_numpy(), 0, 32767).astype(np.int16)
    sch_mode[aid, slot] = sched["mode"].to_numpy(np.int8)
    sch_route[aid, slot] = sched["route_id"].to_numpy(np.int32)
    sch_count = np.bincount(aid, minlength=n_agents).astype(np.int8)

    west, south, east, north = manifest.get("bbox", cfg["bbox"])
    rows = max(2, int(np.ceil((north - south) / GRID_DLAT)))
    cols = max(2, int(np.ceil((east - west) / GRID_DLON)))

    return World(
        node_lon=node_lon,
        node_lat=node_lat,
        route_start=route_start,
        route_n=route_n,
        route_len=route_len,
        vert_lon=vert_lon,
        vert_lat=vert_lat,
        vert_cum=vert_cum,
        vert_key=vert_key,
        poi_lon=pois["lon"].to_numpy(np.float32),
        poi_lat=pois["lat"].to_numpy(np.float32),
        poi_cat=pois["cat_id"].to_numpy(np.int16),
        poi_node=pois["node_id"].to_numpy(np.int32),
        poi_name=pois["name"].astype(str).tolist(),
        poi_attr=pois["attractiveness"].to_numpy(np.float32),
        agent_home=agents["home_node_id"].to_numpy(np.int32),
        agent_work=agents["work_node_id"].to_numpy(np.int32),
        agent_arch=agents["archetype_id"].to_numpy(np.int16),
        agent_segment=agents["segment"].to_numpy(np.int8),
        agent_weight=agents["weight"].to_numpy(np.float32),
        sch_cat=sch_cat,
        sch_poi=sch_poi,
        sch_node=sch_node,
        sch_start=sch_start,
        sch_end=sch_end,
        sch_mode=sch_mode,
        sch_route=sch_route,
        sch_count=sch_count,
        grid_origin=(float(west), float(south)),
        grid_step=(GRID_DLON, GRID_DLAT),
        grid_shape=(rows, cols),
        categories=cats,
        bounds=(float(west), float(south), float(east), float(north)),
        manifest=manifest,
    )
