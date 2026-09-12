#!/usr/bin/env python
"""Build a real-geometry San Francisco dataset: walk network, points of interest,
agents, daily schedules and routed polylines.

Produces every table the simulation engine reads, so the interface can be built
against the final data contract before the full pipeline lands.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"


def log(msg: str, t0: float | None = None) -> float:
    now = time.time()
    tail = f"  ({now - t0:.1f}s)" if t0 else ""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}{tail}", flush=True)
    return now


# --------------------------------------------------------------- categories
# id, label, huff beta (distance decay), dwell minutes, base attractiveness,
# opening minute-of-day, closing minute-of-day
CATEGORIES = [
    ("home", "Home", 0.0, 600, 1.0, 0, 1440),
    ("office", "Office", 0.8, 480, 3.0, 420, 1260),
    ("school", "School", 1.6, 390, 2.5, 450, 1020),
    ("university", "University", 0.9, 300, 4.0, 420, 1320),
    ("cafe", "Cafe", 2.2, 28, 1.4, 390, 1080),
    ("restaurant", "Restaurant", 1.5, 62, 1.8, 660, 1380),
    ("fast_food", "Fast food", 2.0, 24, 1.2, 600, 1380),
    ("bar", "Bar", 1.3, 95, 1.6, 960, 1440),
    ("nightclub", "Nightclub", 0.9, 135, 2.2, 1200, 1440),
    ("grocery", "Grocery", 1.7, 34, 2.4, 480, 1320),
    ("convenience", "Convenience", 2.4, 11, 0.9, 420, 1380),
    ("retail", "Retail", 1.4, 38, 1.3, 600, 1260),
    ("clothing", "Clothing", 1.2, 45, 1.5, 600, 1260),
    ("pharmacy", "Pharmacy", 1.9, 16, 1.1, 540, 1260),
    ("gym", "Gym", 1.2, 72, 1.9, 330, 1350),
    ("park", "Park", 1.1, 68, 2.6, 360, 1320),
    ("library", "Library", 1.0, 96, 1.7, 600, 1200),
    ("museum", "Museum", 0.7, 105, 3.1, 600, 1020),
    ("theatre", "Theatre", 0.6, 150, 2.8, 1020, 1380),
    ("cinema", "Cinema", 0.9, 130, 2.2, 720, 1380),
    ("hotel", "Hotel", 0.5, 540, 3.4, 0, 1440),
    ("clinic", "Clinic", 1.1, 58, 1.8, 480, 1080),
    ("bank", "Bank", 1.5, 18, 1.0, 540, 1020),
    ("worship", "Worship", 1.0, 84, 1.5, 420, 1260),
    ("transit_stop", "Transit", 3.0, 6, 1.0, 0, 1440),
]
CAT_ID = {c[0]: i for i, c in enumerate(CATEGORIES)}

# OpenStreetMap tag pair -> canonical category
OSM_MAP = {
    ("amenity", "cafe"): "cafe",
    ("amenity", "restaurant"): "restaurant",
    ("amenity", "fast_food"): "fast_food",
    ("amenity", "bar"): "bar",
    ("amenity", "pub"): "bar",
    ("amenity", "biergarten"): "bar",
    ("amenity", "nightclub"): "nightclub",
    ("amenity", "pharmacy"): "pharmacy",
    ("amenity", "school"): "school",
    ("amenity", "kindergarten"): "school",
    ("amenity", "college"): "university",
    ("amenity", "university"): "university",
    ("amenity", "library"): "library",
    ("amenity", "theatre"): "theatre",
    ("amenity", "cinema"): "cinema",
    ("amenity", "arts_centre"): "theatre",
    ("amenity", "hospital"): "clinic",
    ("amenity", "clinic"): "clinic",
    ("amenity", "doctors"): "clinic",
    ("amenity", "dentist"): "clinic",
    ("amenity", "bank"): "bank",
    ("amenity", "place_of_worship"): "worship",
    ("amenity", "gym"): "gym",
    ("shop", "supermarket"): "grocery",
    ("shop", "greengrocer"): "grocery",
    ("shop", "grocery"): "grocery",
    ("shop", "convenience"): "convenience",
    ("shop", "clothes"): "clothing",
    ("shop", "shoes"): "clothing",
    ("shop", "boutique"): "clothing",
    ("shop", "chemist"): "pharmacy",
    ("leisure", "fitness_centre"): "gym",
    ("leisure", "sports_centre"): "gym",
    ("leisure", "park"): "park",
    ("leisure", "garden"): "park",
    ("leisure", "playground"): "park",
    ("tourism", "museum"): "museum",
    ("tourism", "gallery"): "museum",
    ("tourism", "hotel"): "hotel",
    ("tourism", "hostel"): "hotel",
    ("tourism", "attraction"): "museum",
    ("railway", "station"): "transit_stop",
    ("railway", "subway_entrance"): "transit_stop",
    ("railway", "tram_stop"): "transit_stop",
    ("public_transport", "station"): "transit_stop",
}
# column search order; the first column that yields a category wins
TAG_ORDER = ("amenity", "shop", "leisure", "tourism", "railway", "public_transport", "office")

# --------------------------------------------------------------- archetypes
# activity tuple: kind, category, anchor, (window_start, window_end),
#                 duration_min, flex_min, probability, mode
ARCHETYPES = [
    dict(
        id="office_worker", label="Office worker", share=0.30, segment=0,
        acts=[
            ("home", "home", "home", (0, 420), 0, 30, 1.00, "walk"),
            ("coffee", "cafe", "work", (465, 520), 18, 20, 0.62, "walk"),
            ("work", "office", "work", (505, 540), 245, 25, 1.00, "walk"),
            ("lunch", "restaurant", "work", (735, 795), 48, 25, 0.78, "walk"),
            ("work", "office", "work", (790, 830), 230, 25, 1.00, "walk"),
            ("evening", "bar", "work", (1065, 1140), 88, 40, 0.24, "walk"),
            ("home", "home", "home", (1140, 1380), 0, 60, 1.00, "transit"),
        ],
    ),
    dict(
        id="tech_commuter", label="Tech commuter", share=0.14, segment=1,
        acts=[
            ("home", "home", "home", (0, 405), 0, 25, 1.00, "walk"),
            ("coffee", "cafe", "home", (430, 480), 16, 18, 0.48, "walk"),
            ("work", "office", "work", (495, 555), 480, 30, 1.00, "transit"),
            ("gym", "gym", "work", (1050, 1125), 68, 30, 0.34, "walk"),
            ("dinner", "restaurant", "home", (1125, 1215), 58, 35, 0.42, "walk"),
            ("home", "home", "home", (1215, 1400), 0, 45, 1.00, "transit"),
        ],
    ),
    dict(
        id="student", label="Student", share=0.13, segment=2,
        acts=[
            ("home", "home", "home", (0, 465), 0, 40, 1.00, "walk"),
            ("class", "university", "work", (510, 570), 210, 30, 1.00, "transit"),
            ("coffee", "cafe", "work", (735, 800), 34, 30, 0.66, "walk"),
            ("study", "library", "work", (810, 900), 165, 45, 0.52, "walk"),
            ("social", "bar", "home", (1140, 1260), 105, 60, 0.28, "walk"),
            ("home", "home", "home", (1260, 1420), 0, 60, 1.00, "walk"),
        ],
    ),
    dict(
        id="service_worker", label="Service worker", share=0.17, segment=3,
        acts=[
            ("home", "home", "home", (0, 480), 0, 45, 1.00, "walk"),
            ("work", "restaurant", "work", (555, 645), 415, 35, 1.00, "transit"),
            ("errand", "grocery", "home", (1080, 1200), 30, 40, 0.46, "walk"),
            ("home", "home", "home", (1170, 1380), 0, 50, 1.00, "transit"),
        ],
    ),
    dict(
        id="remote_worker", label="Remote worker", share=0.10, segment=4,
        acts=[
            ("home", "home", "home", (0, 480), 0, 45, 1.00, "walk"),
            ("coffee", "cafe", "home", (510, 600), 52, 40, 0.72, "walk"),
            ("home", "home", "home", (600, 780), 0, 40, 1.00, "walk"),
            ("lunch", "cafe", "home", (760, 830), 38, 30, 0.40, "walk"),
            ("gym", "gym", "home", (1020, 1110), 66, 40, 0.44, "walk"),
            ("dinner", "restaurant", "home", (1110, 1230), 62, 45, 0.38, "walk"),
            ("home", "home", "home", (1230, 1420), 0, 50, 1.00, "walk"),
        ],
    ),
    dict(
        id="retiree", label="Retiree", share=0.08, segment=5,
        acts=[
            ("home", "home", "home", (0, 480), 0, 60, 1.00, "walk"),
            ("park", "park", "home", (520, 620), 72, 45, 0.58, "walk"),
            ("errand", "grocery", "home", (640, 760), 36, 45, 0.54, "walk"),
            ("coffee", "cafe", "home", (780, 900), 40, 50, 0.34, "walk"),
            ("home", "home", "home", (900, 1200), 0, 60, 1.00, "walk"),
        ],
    ),
    dict(
        id="visitor", label="Visitor", share=0.08, segment=6,
        acts=[
            ("hotel", "hotel", "home", (0, 510), 0, 40, 1.00, "walk"),
            ("sightsee", "museum", "prev", (555, 660), 115, 45, 0.74, "transit"),
            ("lunch", "restaurant", "prev", (720, 820), 62, 40, 0.86, "walk"),
            ("shop", "retail", "prev", (840, 960), 68, 50, 0.56, "walk"),
            ("park", "park", "prev", (960, 1080), 74, 55, 0.46, "walk"),
            ("dinner", "restaurant", "prev", (1110, 1215), 82, 45, 0.80, "walk"),
            ("hotel", "hotel", "home", (1230, 1420), 0, 60, 1.00, "transit"),
        ],
    ),
]
VISITOR_ARCH = 6
MODE_ID = {"walk": 0, "bike": 1, "transit": 2, "car": 3}
WORK_CATS = ("office", "university", "restaurant", "school")


def build_network(bbox, cache_dir):
    """Download the walk network and return dense arrays plus edge geometry."""
    import osmnx as ox

    ox.settings.use_cache = True
    ox.settings.cache_folder = str(cache_dir)
    ox.settings.log_console = False

    t = log(f"downloading walk network for bbox={bbox}")
    graph = ox.graph_from_bbox(bbox, network_type="walk", simplify=True, retain_all=False)
    log(f"graph: {graph.number_of_nodes():,} nodes / {graph.number_of_edges():,} edges", t)

    osmids = np.fromiter(graph.nodes(), dtype=np.int64, count=graph.number_of_nodes())
    idx_of = {int(o): i for i, o in enumerate(osmids)}
    node_lon = np.array([graph.nodes[o]["x"] for o in osmids], dtype=np.float64)
    node_lat = np.array([graph.nodes[o]["y"] for o in osmids], dtype=np.float64)

    t = log("flattening edges and geometry")
    best: dict[tuple[int, int], float] = {}
    geom: dict[tuple[int, int], np.ndarray] = {}
    for u, v, data in graph.edges(data=True):
        iu, iv = idx_of[int(u)], idx_of[int(v)]
        if iu == iv:
            continue
        length = float(data.get("length", 1.0))
        key = (iu, iv)
        if key in best and best[key] <= length:
            continue  # keep the shortest parallel edge only
        best[key] = length
        line = data.get("geometry")
        if line is not None:
            coords = np.asarray(line.coords, dtype=np.float32)
            head = abs(coords[0, 0] - node_lon[iu]) + abs(coords[0, 1] - node_lat[iu])
            tail = abs(coords[-1, 0] - node_lon[iu]) + abs(coords[-1, 1] - node_lat[iu])
            if head > tail:
                coords = coords[::-1].copy()
        else:
            coords = np.array(
                [[node_lon[iu], node_lat[iu]], [node_lon[iv], node_lat[iv]]], dtype=np.float32
            )
        geom[key] = coords
    log(f"{len(best):,} unique directed edges", t)
    return osmids, node_lon, node_lat, best, geom


# Overture category strings are matched by substring, most specific first.
# "barber" must beat "bar", and "parking" must not be read as "park".
OVERTURE_RULES = [
    ("parking", None), ("barber", "retail"), ("bar_", "bar"),
    ("coffee", "cafe"), ("cafe", "cafe"), ("bakery", "cafe"), ("tea_house", "cafe"),
    ("fast_food", "fast_food"), ("burger", "fast_food"), ("sandwich", "fast_food"),
    ("pizza", "fast_food"), ("taco", "fast_food"), ("donut", "fast_food"),
    ("food_truck", "fast_food"), ("restaurant", "restaurant"),
    ("night_club", "nightclub"), ("nightlife", "nightclub"),
    ("brewery", "bar"), ("winery", "bar"), ("distillery", "bar"), ("wine_bar", "bar"),
    ("cocktail", "bar"), ("pub", "bar"), ("bar", "bar"),
    ("grocery", "grocery"), ("supermarket", "grocery"), ("farmers_market", "grocery"),
    ("convenience", "convenience"),
    ("clothing", "clothing"), ("shoe_store", "clothing"), ("jewelry", "clothing"),
    ("boutique", "clothing"),
    ("pharmacy", "pharmacy"), ("drugstore", "pharmacy"),
    ("gym", "gym"), ("fitness", "gym"), ("yoga", "gym"), ("pilates", "gym"),
    ("martial_arts", "gym"),
    ("playground", "park"), ("dog_park", "park"), ("garden", "park"), ("park", "park"),
    ("library", "library"),
    ("museum", "museum"), ("art_gallery", "museum"), ("historical", "museum"),
    ("landmark", "museum"), ("arts_and_crafts", "museum"),
    ("movie_theater", "cinema"), ("cinema", "cinema"),
    ("performing_arts", "theatre"), ("theater", "theatre"), ("theatre", "theatre"),
    ("event_venue", "theatre"), ("music_venue", "theatre"), ("concert", "theatre"),
    ("hotel", "hotel"), ("hostel", "hotel"), ("motel", "hotel"),
    ("bed_and_breakfast", "hotel"),
    ("hospital", "clinic"), ("dentist", "clinic"), ("doctor", "clinic"),
    ("physician", "clinic"), ("clinic", "clinic"), ("medical", "clinic"),
    ("diagnostic", "clinic"), ("chiropract", "clinic"), ("optometr", "clinic"),
    ("credit_union", "bank"), ("bank", "bank"),
    ("church", "worship"), ("cathedral", "worship"), ("mosque", "worship"),
    ("synagogue", "worship"), ("temple", "worship"), ("religious", "worship"),
    ("university", "university"), ("college", "university"),
    ("kindergarten", "school"), ("preschool", "school"), ("childcare", "school"),
    ("school", "school"),
    ("train_station", "transit_stop"), ("bus_station", "transit_stop"),
    ("subway", "transit_stop"), ("metro_station", "transit_stop"),
    ("transit", "transit_stop"),
    ("lawyer", "office"), ("real_estate", "office"), ("software", "office"),
    ("accounting", "office"), ("insurance", "office"), ("consulting", "office"),
    ("marketing", "office"), ("information_technology", "office"), ("office", "office"),
    ("salon", "retail"), ("spa", "retail"), ("laundry", "retail"),
    ("store", "retail"), ("shop", "retail"), ("market", "retail"),
]

# coarse fallback when no specific rule matches
OVERTURE_TAXONOMY = {
    "food_and_drink": "restaurant", "shopping": "retail",
    "services_and_business": "office", "health_care": "clinic",
    "lifestyle_services": "retail", "arts_and_entertainment": "museum",
    "sports_and_recreation": "gym", "education": "school", "lodging": "hotel",
    "travel_and_transportation": "transit_stop", "cultural_and_historic": "museum",
    "community_and_government": "office",
}


def _overture_category(specific: str | None, top: str | None) -> str | None:
    if isinstance(specific, str):
        text = specific.lower()
        for needle, canonical in OVERTURE_RULES:
            if needle in text:
                return canonical
    if isinstance(top, str):
        return OVERTURE_TAXONOMY.get(top)
    return None


def extract_pois_overture(path, cat_id):
    """Read the local Overture extract and reduce it to the category catalog."""
    import pandas as pd

    t = log(f"reading places from {path.name}")
    df = pd.read_parquet(path)
    df = df[(df["operating_status"].isna()) | (df["operating_status"] == "open")]

    top = df["taxonomy"].map(lambda h: h[0] if isinstance(h, (list, np.ndarray)) and len(h) else None)
    specific = df["category_primary"].fillna(df["basic_category"])
    category = [
        _overture_category(s, tp) for s, tp in zip(specific.tolist(), top.tolist())
    ]

    label_of = {c[0]: c[1] for c in CATEGORIES}
    out = pd.DataFrame(
        {
            "name": df["name"].astype("object").to_numpy(),
            "category": category,
            "lon": df["lon"].to_numpy(dtype=np.float64),
            "lat": df["lat"].to_numpy(dtype=np.float64),
            "confidence": df["confidence"].to_numpy(dtype=np.float64),
            "brand": df["brand"].astype("object").to_numpy(),
        }
    )
    out = out[out["category"].notna() & out["category"].isin(cat_id)].reset_index(drop=True)
    out["name"] = [
        n if isinstance(n, str) and n.strip() else label_of[c]
        for n, c in zip(out["name"], out["category"])
    ]
    log(f"{len(out):,} of {len(df):,} Overture places mapped to the catalog", t)
    return out


def _fetch_tile(sub, tags, attempts=3):
    """One Overpass request, retried. Returns None if the tile never lands."""
    import osmnx as ox

    for attempt in range(attempts):
        try:
            return ox.features_from_bbox(sub, tags)
        except Exception as exc:
            if attempt == attempts - 1:
                log(f"  tile {sub} failed after {attempts} tries: {type(exc).__name__}")
                return None
            time.sleep(4 * (attempt + 1))
    return None


def extract_pois(bbox, cat_id, tiles: int = 4):
    """Pull OSM features and reduce them to the canonical category catalog.

    The whole-city bounding box reliably times out on Overpass, so the area is
    split into tiles and fetched one at a time. osmnx caches each tile, which
    also makes a re-run nearly free.
    """
    import osmnx as ox
    import pandas as pd

    ox.settings.requests_timeout = 240
    t = log(f"downloading points of interest in {tiles * tiles} tiles")
    tags = {
        "amenity": True, "shop": True, "leisure": True,
        "tourism": True, "office": True, "railway": ["station", "subway_entrance", "tram_stop"],
    }
    west, south, east, north = bbox
    dx = (east - west) / tiles
    dy = (north - south) / tiles

    frames, failed = [], 0
    for i in range(tiles):
        for j in range(tiles):
            sub = (west + i * dx, south + j * dy, west + (i + 1) * dx, south + (j + 1) * dy)
            got = _fetch_tile(sub, tags)
            if got is None:
                failed += 1
            elif len(got):
                frames.append(got)
        log(f"  column {i + 1}/{tiles}: {sum(len(f) for f in frames):,} features so far")

    if failed:
        log(f"WARNING: {failed}/{tiles * tiles} tiles failed; coverage is incomplete")
    if not frames:
        return pd.DataFrame(columns=["name", "category", "lon", "lat"])

    feats = pd.concat(frames)
    feats = feats[~feats.index.duplicated(keep="first")]

    try:
        pts = feats.geometry.representative_point()
    except Exception:
        pts = feats.geometry.centroid

    cat = pd.Series(pd.NA, index=feats.index, dtype="object")
    for key in TAG_ORDER:
        if key not in feats.columns or not cat.isna().any():
            continue
        col = feats[key]
        mapped = col.map(lambda v, k=key: OSM_MAP.get((k, v)) if isinstance(v, str) else None)
        if key == "shop":  # any unlisted shop is generic retail
            mapped = mapped.fillna(col.map(lambda v: "retail" if isinstance(v, str) else None))
        if key == "office":
            mapped = mapped.fillna(col.map(lambda v: "office" if isinstance(v, str) else None))
        cat = cat.fillna(mapped)

    name = feats["name"] if "name" in feats.columns else pd.Series(pd.NA, index=feats.index)
    out = pd.DataFrame(
        {
            "name": name.astype("object"),
            "category": cat,
            "lon": pts.x.to_numpy(dtype=np.float64),
            "lat": pts.y.to_numpy(dtype=np.float64),
        }
    )
    out = out[out["category"].notna() & out["category"].isin(cat_id)].reset_index(drop=True)
    label_of = {c[0]: c[1] for c in CATEGORIES}
    out["name"] = [
        n if isinstance(n, str) and n.strip() else label_of[c]
        for n, c in zip(out["name"], out["category"])
    ]
    log(f"{len(out):,} points of interest mapped to the catalog", t)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["core", "city"], default="city")
    parser.add_argument("--agents", type=int, default=None)
    parser.add_argument("--places", choices=["overture", "osm"], default="overture",
                        help="Overture is a single reliable download; OSM goes via Overpass")
    args = parser.parse_args()

    global OUT
    final_out = ROOT / "data" / "processed"
    OUT = ROOT / "data" / "processed.building"
    if OUT.exists():
        shutil.rmtree(OUT)

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    rng = np.random.default_rng(cfg["seed"])
    bbox = tuple(cfg["core_bbox"] if args.scope == "core" else cfg["bbox"])
    n_agents = args.agents or int(cfg["sim"]["n_agents"])
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    from scipy.spatial import cKDTree
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    import h3

    # ------------------------------------------------------------- network
    osmids, node_lon, node_lat, edge_len, edge_geom = build_network(
        bbox, RAW / "osmnx_cache"
    )
    n_nodes = len(osmids)
    keys = np.array(list(edge_len.keys()), dtype=np.int32)
    vals = np.array(list(edge_len.values()), dtype=np.float32)
    csr = csr_matrix((vals, (keys[:, 0], keys[:, 1])), shape=(n_nodes, n_nodes))

    # local equirectangular projection, good enough over one city
    lat0 = float(node_lat.mean())
    mx = 111_320.0 * float(np.cos(np.radians(lat0)))
    my = 110_540.0
    node_x = (node_lon - node_lon.min()) * mx
    node_y = (node_lat - node_lat.min()) * my
    node_tree = cKDTree(np.c_[node_x, node_y])

    t = log("indexing nodes to H3 resolution 9")
    h3_r9 = np.array(
        [h3.latlng_to_cell(float(a), float(o), 9) for a, o in zip(node_lat, node_lon)],
        dtype=object,
    )
    log("H3 index built", t)

    pd.DataFrame(
        {
            "node_id": np.arange(n_nodes, dtype=np.int32),
            "osmid": osmids,
            "lon": node_lon.astype(np.float32),
            "lat": node_lat.astype(np.float32),
            "h3_r9": h3_r9,
        }
    ).to_parquet(OUT / "network_nodes.parquet", index=False)

    # ---------------------------------------------------------------- POIs
    overture = RAW / "overture_places_sf.parquet"
    if args.places == "overture" and overture.exists():
        poi = extract_pois_overture(overture, CAT_ID)
        west_b, south_b, east_b, north_b = bbox
        poi = poi[
            poi["lon"].between(west_b, east_b) & poi["lat"].between(south_b, north_b)
        ].reset_index(drop=True)
    else:
        if args.places == "overture":
            log(f"{overture} is missing; run scripts/03_overture_places.py first")
        poi = extract_pois(bbox, CAT_ID)
    if not len(poi):
        raise SystemExit(
            "No points of interest were downloaded, so agents would have nowhere "
            "to go. Overpass is most likely rate-limiting; wait a few minutes and "
            "re-run. Tiles already fetched are cached and will not be re-requested."
        )
    poi = poi.drop_duplicates(subset=["name", "lon", "lat"]).reset_index(drop=True)
    poi["poi_id"] = np.arange(len(poi), dtype=np.int32)
    poi["cat_id"] = poi["category"].map(CAT_ID).astype(np.int16)
    px = (poi["lon"].to_numpy() - node_lon.min()) * mx
    py = (poi["lat"].to_numpy() - node_lat.min()) * my
    _, snapped = node_tree.query(np.c_[px, py], k=1)
    poi["node_id"] = snapped.astype(np.int32)
    base_attr = np.array([CATEGORIES[c][4] for c in poi["cat_id"]], dtype=np.float32)
    spread = rng.lognormal(0.0, 0.55, len(poi))
    if "confidence" in poi.columns:
        # a place several sources agree on is more likely to be a real destination
        spread = spread * (0.55 + 0.9 * poi["confidence"].fillna(0.4).to_numpy())
    poi["attractiveness"] = (base_attr * spread).astype(np.float32)
    poi["open_min"] = np.array([CATEGORIES[c][5] for c in poi["cat_id"]], dtype=np.int16)
    poi["close_min"] = np.array([CATEGORIES[c][6] for c in poi["cat_id"]], dtype=np.int16)
    poi["h3_r9"] = h3_r9[poi["node_id"].to_numpy()]
    poi["is_active"] = True
    poi["rating"] = np.float32(np.nan)
    poi["user_rating_count"] = np.int32(-1)
    poi.to_parquet(OUT / "pois.parquet", index=False)

    pd.DataFrame(
        CATEGORIES,
        columns=["category", "label", "huff_beta", "dwell_min", "base_attr", "open_min", "close_min"],
    ).to_parquet(OUT / "categories.parquet", index=False)

    by_cat = {c: poi.index[poi["category"] == c].to_numpy() for c in poi["category"].unique()}
    top = sorted(by_cat, key=lambda k: -len(by_cat[k]))[:10]
    log("largest categories: " + ", ".join(f"{c}={len(by_cat[c])}" for c in top))

    # ------------------------------------------------------------- agents
    t = log(f"placing {n_agents:,} agents")
    home_pool = rng.choice(n_nodes, size=min(5000, n_nodes), replace=False).astype(np.int32)
    work_nodes = [poi["node_id"].to_numpy()[by_cat[c]] for c in WORK_CATS if c in by_cat]
    work_pool = (
        np.unique(np.concatenate(work_nodes)).astype(np.int32)
        if work_nodes
        else rng.choice(n_nodes, size=min(500, n_nodes), replace=False).astype(np.int32)
    )

    shares = np.array([a["share"] for a in ARCHETYPES], dtype=np.float64)
    shares /= shares.sum()
    arch_of = rng.choice(len(ARCHETYPES), size=n_agents, p=shares).astype(np.int16)
    home_of = rng.choice(home_pool, size=n_agents).astype(np.int32)
    work_of = rng.choice(work_pool, size=n_agents).astype(np.int32)

    if "hotel" in by_cat and len(by_cat["hotel"]):
        hotel_nodes = poi["node_id"].to_numpy()[by_cat["hotel"]]
        visitors = np.flatnonzero(arch_of == VISITOR_ARCH)
        home_of[visitors] = rng.choice(hotel_nodes, size=len(visitors))

    pd.DataFrame(
        {
            "agent_id": np.arange(n_agents, dtype=np.int32),
            "archetype_id": arch_of,
            "segment": np.array([ARCHETYPES[a]["segment"] for a in arch_of], dtype=np.int8),
            "home_node_id": home_of,
            "work_node_id": work_of,
            "weight": np.full(n_agents, 830_000 / max(n_agents, 1), dtype=np.float32),
        }
    ).to_parquet(OUT / "agents.parquet", index=False)
    log("agents placed", t)

    # ---------------------------------------------------------- schedules
    t = log("grounding daily schedules")
    poi_node_arr = poi["node_id"].to_numpy().astype(np.int32)
    poi_attr_arr = poi["attractiveness"].to_numpy()
    cat_trees = {
        c: cKDTree(np.c_[node_x[poi_node_arr[ix]], node_y[poi_node_arr[ix]]])
        for c, ix in by_cat.items()
        if len(ix)
    }

    def pick(cat: str, anchor_node: int, k: int = 28) -> int:
        """Huff-style draw among the k nearest points of interest of a category."""
        ix = by_cat.get(cat)
        if ix is None or not len(ix):
            return -1
        kk = min(k, len(ix))
        dist, j = cat_trees[cat].query([node_x[anchor_node], node_y[anchor_node]], k=kk)
        dist = np.atleast_1d(dist)
        j = np.atleast_1d(j).astype(int)
        beta = CATEGORIES[CAT_ID[cat]][2]
        util = poi_attr_arr[ix[j]] * np.exp(-beta * dist / 1000.0)
        total = float(util.sum())
        if not np.isfinite(total) or total <= 0:
            return int(ix[j[0]])
        return int(ix[j[rng.choice(kk, p=util / total)]])

    speed_of = np.array([78.0, 230.0, 430.0, 330.0])  # metres per minute by mode
    DETOUR = 1.35  # street distance over straight-line distance

    def travel_minutes(a: int, b: int, mode_id: int) -> float:
        metres = float(np.hypot(node_x[a] - node_x[b], node_y[a] - node_y[b])) * DETOUR
        return metres / speed_of[mode_id]

    rows = []
    for aid in range(n_agents):
        arch = ARCHETYPES[arch_of[aid]]
        home_n, work_n = int(home_of[aid]), int(work_of[aid])

        # 1. decide which activities happen today and where each one is
        chosen = []
        prev_n = home_n
        for kind, cat, anchor, window, dur, flex, prob, mode in arch["acts"]:
            if prob < 1.0 and rng.random() > prob:
                continue
            if cat == "home":
                node, pid = home_n, -1
            elif anchor == "work" and cat in WORK_CATS:
                node, pid = work_n, -1
            else:
                anchor_n = {"home": home_n, "work": work_n}.get(anchor, prev_n)
                pid = pick(cat, anchor_n)
                node = int(poi_node_arr[pid]) if pid >= 0 else anchor_n
            chosen.append(
                (kind, CAT_ID.get(cat, 0), pid, node, int(dur), window, int(flex), MODE_ID[mode])
            )
            prev_n = node
        if not chosen:
            chosen = [("home", 0, -1, home_n, 0, (0, 1440), 0, 0)]

        # 2. forward pass: the earliest each activity can realistically begin,
        #    given the previous one and the journey between them
        starts = []
        cursor = 0.0
        for i, (_, _, _, node, dur, window, flex, mode) in enumerate(chosen):
            if i == 0:
                begin = 0.0
            else:
                journey = travel_minutes(chosen[i - 1][3], node, mode)
                begin = max(cursor + journey, window[0] + float(rng.integers(0, max(flex, 1))))
                begin = min(begin, 1439.0)
            starts.append(begin)
            cursor = begin + dur

        # 3. backward pass: an activity ends when it is time to leave for the
        #    next one. Without this a zero-duration stay at home would end at
        #    midnight and send the whole city out before dawn.
        for i, (kind, cid, pid, node, dur, window, flex, mode) in enumerate(chosen):
            if i == len(chosen) - 1:
                finish = 1440.0
            else:
                journey = travel_minutes(node, chosen[i + 1][3], chosen[i + 1][7])
                finish = max(starts[i] + dur, starts[i + 1] - journey)
            rows.append(
                (aid, i, kind, cid, pid, node,
                 int(starts[i]), int(min(finish, 1440.0)), mode)
            )

        if aid and aid % 5000 == 0:
            log(f"  {aid:,}/{n_agents:,} agents scheduled")

    sch = pd.DataFrame(
        rows,
        columns=["agent_id", "slot", "kind", "cat_id", "poi_id", "node_id",
                 "start_min", "end_min", "mode"],
    )
    log(f"{len(sch):,} schedule slots", t)

    # --------------------------------------------------------------- routes
    t = log("collecting legs")
    agent_col = sch["agent_id"].to_numpy()
    node_col = sch["node_id"].to_numpy().astype(np.int32)
    same_agent = agent_col[1:] == agent_col[:-1]
    origin = node_col[:-1][same_agent]
    dest = node_col[1:][same_agent]
    arrive_row = np.flatnonzero(same_agent) + 1
    moved = origin != dest
    origin, dest, arrive_row = origin[moved], dest[moved], arrive_row[moved]

    pairs = np.unique(np.c_[origin, dest], axis=0)
    log(f"{len(origin):,} legs over {len(pairs):,} unique origin/destination pairs", t)

    dest_of: dict[int, list[int]] = {}
    for o, d in pairs:
        dest_of.setdefault(int(o), []).append(int(d))
    origins = np.array(sorted(dest_of), dtype=np.int32)

    route_of: dict[tuple[int, int], int] = {}
    v_lon, v_lat, v_cum = [], [], []
    r_from, r_to, r_start, r_n, r_len = [], [], [], [], []
    vert_offset = 0
    chunk = int(cfg["routing"]["chunk_origins"])
    limit = float(cfg["routing"]["max_route_m"])

    t = log(f"routing {len(origins):,} origins")
    for i in range(0, len(origins), chunk):
        src = origins[i : i + chunk]
        _, pred = dijkstra(csr, directed=True, indices=src,
                           return_predecessors=True, limit=limit)
        for j, o in enumerate(src):
            prow = pred[j]
            for d in dest_of[int(o)]:
                path, cur, ok = [], int(d), False
                for _ in range(4000):
                    path.append(cur)
                    if cur == int(o):
                        ok = True
                        break
                    cur = int(prow[cur])
                    if cur < 0:
                        break
                if ok and len(path) >= 2:
                    path.reverse()
                    segs = []
                    for u, v in zip(path[:-1], path[1:]):
                        g = edge_geom.get((u, v))
                        if g is None:
                            back = edge_geom.get((v, u))
                            g = (
                                back[::-1]
                                if back is not None
                                else np.array([[node_lon[u], node_lat[u]],
                                               [node_lon[v], node_lat[v]]], dtype=np.float32)
                            )
                        segs.append(g if not segs else g[1:])
                    coords = np.concatenate(segs, axis=0).astype(np.float32)
                else:  # unreachable within the limit: fall back to a direct line
                    coords = np.array([[node_lon[o], node_lat[o]],
                                       [node_lon[d], node_lat[d]]], dtype=np.float32)

                dx = np.diff(coords[:, 0].astype(np.float64)) * mx
                dy = np.diff(coords[:, 1].astype(np.float64)) * my
                cum = np.concatenate([[0.0], np.cumsum(np.hypot(dx, dy))]).astype(np.float32)
                route_of[(int(o), int(d))] = len(r_from)
                r_from.append(int(o))
                r_to.append(int(d))
                r_start.append(vert_offset)
                r_n.append(len(coords))
                vert_offset += len(coords)
                r_len.append(float(cum[-1]))
                v_lon.append(coords[:, 0])
                v_lat.append(coords[:, 1])
                v_cum.append(cum)
        if (i // chunk) % 10 == 0:
            log(f"  {min(i + chunk, len(origins)):,}/{len(origins):,} origins, {len(r_from):,} routes")

    pd.DataFrame(
        {
            "route_id": np.arange(len(r_from), dtype=np.int32),
            "from_node": np.array(r_from, dtype=np.int32),
            "to_node": np.array(r_to, dtype=np.int32),
            "vert_start": np.array(r_start, dtype=np.int64),
            "n_verts": np.array(r_n, dtype=np.int32),
            "length_m": np.array(r_len, dtype=np.float32),
        }
    ).to_parquet(OUT / "routes.parquet", index=False)
    pd.DataFrame(
        {
            "lon": np.concatenate(v_lon),
            "lat": np.concatenate(v_lat),
            "cum_m": np.concatenate(v_cum),
        }
    ).to_parquet(OUT / "routes_verts.parquet", index=False)
    log(f"{len(r_from):,} routes, {int(np.sum(r_n)):,} vertices", t)

    route_col = np.full(len(sch), -1, dtype=np.int32)
    for k in range(len(origin)):
        route_col[arrive_row[k]] = route_of.get((int(origin[k]), int(dest[k])), -1)
    sch["route_id"] = route_col
    sch.to_parquet(OUT / "schedules.parquet", index=False)

    # ------------------------------------------- candidates, events, zones
    vac_cats = [c for c in ("retail", "clothing", "cafe", "restaurant") if c in by_cat]
    vac_ix = np.concatenate([by_cat[c] for c in vac_cats]) if vac_cats else np.array([], dtype=int)
    vac = (
        rng.choice(vac_ix, size=min(180, len(vac_ix)), replace=False)
        if len(vac_ix)
        else np.array([], dtype=int)
    )
    pd.DataFrame(
        {
            "cand_id": np.arange(len(vac), dtype=np.int32),
            "source": ["bootstrap_vacancy"] * len(vac),
            "address": [f"{poi.iloc[i]['name']} (vacant)" for i in vac],
            "lon": poi.iloc[vac]["lon"].to_numpy(),
            "lat": poi.iloc[vac]["lat"].to_numpy(),
            "node_id": poi.iloc[vac]["node_id"].to_numpy(),
            "h3_r9": poi.iloc[vac]["h3_r9"].to_numpy(),
            "floor_area_m2": rng.integers(60, 420, len(vac)).astype(np.float32),
        }
    ).to_parquet(OUT / "candidates.parquet", index=False)

    venue_ix = by_cat.get("theatre", by_cat.get("museum", np.array([0], dtype=int)))
    vsel = int(venue_ix[0]) if len(venue_ix) else 0
    pd.DataFrame(
        [
            {
                "event_id": 0, "source": "bootstrap", "kind": "concert",
                "name": "Evening show", "venue_poi_id": int(poi.iloc[vsel]["poi_id"]),
                "lon": float(poi.iloc[vsel]["lon"]), "lat": float(poi.iloc[vsel]["lat"]),
                "day": 4, "start_min": 1140, "end_min": 1320,
                "expected_attendance": 12000,
            }
        ]
    ).to_parquet(OUT / "events.parquet", index=False)

    cells, counts = np.unique(h3_r9, return_counts=True)
    centres = [h3.cell_to_latlng(c) for c in cells]
    pd.DataFrame(
        {
            "h3_r9": cells,
            "lat": np.array([p[0] for p in centres], dtype=np.float32),
            "lon": np.array([p[1] for p in centres], dtype=np.float32),
            "node_count": counts.astype(np.int32),
        }
    ).to_parquet(OUT / "zones_h3.parquet", index=False)

    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "mode": "bootstrap", "scope": args.scope, "bbox": list(bbox),
                "seed": cfg["seed"], "n_nodes": int(n_nodes), "n_pois": int(len(poi)),
                "n_agents": int(n_agents), "n_routes": int(len(r_from)),
                "n_schedule_slots": int(len(sch)),
                "categories": [c[0] for c in CATEGORIES],
            },
            indent=2,
        )
    )
    if final_out.exists():
        shutil.rmtree(final_out)
    OUT.rename(final_out)
    log(f"done -> {final_out}")


if __name__ == "__main__":
    main()
