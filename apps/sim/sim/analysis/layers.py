"""City data layers served to the map.

Each layer is returned as parallel arrays rather than a list of objects, which
is roughly four times smaller on the wire and drops straight into deck.gl's
binary attribute path.

Large layers are thinned deterministically by a stride rather than sampled
randomly, so the same request always returns the same points and panning does
not make the map shimmer. The response always reports how many rows exist
versus how many were sent, because a thinned layer that silently claims to be
complete would misread as "this neighbourhood has few complaints".
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# how many points any single layer will put on the map at once
MAX_POINTS = 24_000


@dataclass(frozen=True)
class LayerSpec:
    """Where a layer comes from and which column carries its category."""

    table: str
    category_column: str | None
    label: str
    description: str


LAYERS: dict[str, LayerSpec] = {
    "complaints": LayerSpec(
        "cases_311", "category", "311 complaints",
        "Resident-reported street conditions over the last twelve months.",
    ),
    "incidents": LayerSpec(
        "police_incidents", "category", "Police incidents",
        "Reported incidents over the last twelve months.",
    ),
    "vacancy": LayerSpec(
        "commercial_vacancy", "vacant", "Commercial vacancy",
        "Parcels registered under the commercial vacancy tax.",
    ),
    "permits": LayerSpec(
        "building_permits", "status", "Building permits",
        "Permits filed over the last three years.",
    ),
}


@functools.lru_cache(maxsize=16)
def _load(root_str: str, table: str) -> pd.DataFrame:
    path = Path(root_str) / "data" / "processed" / f"{table}.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if "lon" in df.columns:
        df = df[df["lon"].notna() & df["lat"].notna()]
    return df.reset_index(drop=True)


def available(root: Path) -> list[dict]:
    """Which layers actually have data on disk."""
    out = []
    for name, spec in LAYERS.items():
        df = _load(str(root), spec.table)
        if df.empty:
            continue
        out.append(
            {
                "id": name,
                "label": spec.label,
                "description": spec.description,
                "count": int(len(df)),
                "categories": _top_categories(df, spec.category_column, 12),
            }
        )
    return out


def _top_categories(df: pd.DataFrame, column: str | None, limit: int) -> list[dict]:
    if not column or column not in df.columns:
        return []
    counts = df[column].astype(str).value_counts().head(limit)
    return [{"value": str(k), "count": int(v)} for k, v in counts.items()]


def points(root: Path, name: str, category: str | None = None) -> dict:
    """One layer as parallel arrays, thinned to a drawable number of points."""
    spec = LAYERS.get(name)
    if spec is None:
        return {"error": f"unknown layer {name}"}
    df = _load(str(root), spec.table)
    if df.empty:
        return {"id": name, "count": 0, "total": 0, "lon": [], "lat": [], "category": []}

    if category and spec.category_column and spec.category_column in df.columns:
        df = df[df[spec.category_column].astype(str) == category]

    total = len(df)
    if total > MAX_POINTS:
        stride = int(np.ceil(total / MAX_POINTS))
        df = df.iloc[::stride]

    cats = (
        df[spec.category_column].astype(str).tolist()
        if spec.category_column and spec.category_column in df.columns
        else []
    )
    return {
        "id": name,
        "label": spec.label,
        "count": int(len(df)),
        "total": int(total),
        "thinned": bool(total > MAX_POINTS),
        "lon": df["lon"].round(5).tolist(),
        "lat": df["lat"].round(5).tolist(),
        "category": cats,
    }


# --------------------------------------------------------------- area report


def _within(df: pd.DataFrame, lon: float, lat: float, metres: float) -> pd.DataFrame:
    """Rows within a radius, using a local flat-earth approximation."""
    if df.empty or "lon" not in df.columns:
        return df
    mx = 111_320.0 * np.cos(np.radians(lat))
    dx = (df["lon"].to_numpy() - lon) * mx
    dy = (df["lat"].to_numpy() - lat) * 110_540.0
    return df[np.hypot(dx, dy) <= metres]


def area_report(root: Path, lon: float, lat: float, radius_m: float = 300.0) -> dict:
    """Everything the city, a planner or an operator would ask about one spot.

    Counts are raw totals within the radius over the loaded window, not rates,
    and the window differs per source, so each section states its own period.
    """
    report: dict = {
        "centre": [lon, lat],
        "radiusMetres": radius_m,
        "sections": {},
    }

    complaints = _within(_load(str(root), "cases_311"), lon, lat, radius_m)
    if len(complaints):
        top = complaints["category"].astype(str).value_counts().head(6)
        open_now = 0
        if "status" in complaints.columns:
            status = complaints["status"].astype(str).str.lower()
            open_now = int((status == "open").sum())
        report["sections"]["complaints"] = {
            "label": "311 complaints",
            "window": "last 12 months",
            "total": int(len(complaints)),
            "stillOpen": open_now,
            "top": [{"name": str(k), "count": int(v)} for k, v in top.items()],
        }

    incidents = _within(_load(str(root), "police_incidents"), lon, lat, radius_m)
    if len(incidents):
        top = incidents["category"].astype(str).value_counts().head(6)
        report["sections"]["incidents"] = {
            "label": "Police incidents",
            "window": "last 12 months",
            "total": int(len(incidents)),
            "top": [{"name": str(k), "count": int(v)} for k, v in top.items()],
        }

    vacancy = _within(_load(str(root), "commercial_vacancy"), lon, lat, radius_m)
    if len(vacancy):
        report["sections"]["vacancy"] = {
            "label": "Commercial vacancy",
            "window": "latest filing",
            "total": int(len(vacancy)),
            "addresses": [
                str(a) for a in vacancy.get("address", pd.Series(dtype=str)).head(6).tolist()
            ],
            "reportedVacant": int(
                (vacancy.get("vacant", pd.Series(dtype=str)).astype(str).str.lower() == "true").sum()
            ),
        }

    permits = _within(_load(str(root), "building_permits"), lon, lat, radius_m)
    if len(permits):
        units = 0
        if "proposed_units" in permits.columns:
            units = int(pd.to_numeric(permits["proposed_units"], errors="coerce").fillna(0).sum())
        report["sections"]["permits"] = {
            "label": "Building permits",
            "window": "last 3 years",
            "total": int(len(permits)),
            "proposedUnits": units,
        }

    land = _within(_load(str(root), "land_use"), lon, lat, radius_m)
    if len(land):
        report["sections"]["landUse"] = _land_use_summary(land)

    return report


def _land_use_summary(land: pd.DataFrame) -> dict:
    """Built form around a point, from the assessor's land-use table."""
    out: dict = {"label": "Land use and property", "parcels": int(len(land))}

    def total(*names: str) -> float:
        for name in names:
            if name in land.columns:
                return float(pd.to_numeric(land[name], errors="coerce").fillna(0).sum())
        return 0.0

    out["residentialUnits"] = int(total("residential_units", "resunits"))
    out["retailSqFt"] = int(total("retail_sqft", "retail"))
    out["officeSqFt"] = int(total("office_sqft", "mips"))
    out["industrialSqFt"] = int(total("industrial_sqft", "pdr"))
    out["commercialSqFt"] = int(total("commercial_sqft", "total_comm"))
    out["openSpaceSqFt"] = int(total("open_space_sqft", "open_space"))

    for name in ("land_use", "landuse", "geography_type"):
        if name in land.columns:
            top = land[name].astype(str).value_counts().head(5)
            out["mix"] = [{"name": str(k), "parcels": int(v)} for k, v in top.items()]
            break
    for name in ("yrbuilt", "year_built"):
        if name in land.columns:
            years = pd.to_numeric(land[name], errors="coerce")
            years = years[(years > 1800) & (years <= 2030)]
            if len(years):
                out["medianYearBuilt"] = int(years.median())
            break
    return out
