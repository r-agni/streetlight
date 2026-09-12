"""Tool implementations the assistant calls.

Each one is a thin adapter: resolve whatever the model said into coordinates,
call the analysis code, and return both a compact payload for the model and
any map actions for the browser. No analysis happens here.

Place names are resolved with Google Geocoding, biased to San Francisco. If no
key is configured, a small built-in gazetteer of neighbourhoods and landmarks
covers the common cases so the assistant still works.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

import numpy as np
import pandas as pd

from ..analysis import events as events_mod
from ..analysis import insight, layers
from .contracts import ToolResult

# fallback when no geocoding key is available
GAZETTEER = {
    "downtown": (-122.4041, 37.7879),
    "financial district": (-122.4001, 37.7935),
    "union square": (-122.4075, 37.7880),
    "soma": (-122.4014, 37.7785),
    "south of market": (-122.4014, 37.7785),
    "mission": (-122.4192, 37.7599),
    "mission district": (-122.4192, 37.7599),
    "castro": (-122.4350, 37.7609),
    "hayes valley": (-122.4241, 37.7763),
    "north beach": (-122.4103, 37.8000),
    "chinatown": (-122.4067, 37.7941),
    "marina": (-122.4367, 37.8030),
    "richmond": (-122.4836, 37.7801),
    "sunset": (-122.4944, 37.7500),
    "haight": (-122.4469, 37.7692),
    "nob hill": (-122.4144, 37.7930),
    "potrero hill": (-122.4004, 37.7576),
    "dogpatch": (-122.3893, 37.7576),
    "bayview": (-122.3914, 37.7300),
    "tenderloin": (-122.4139, 37.7840),
    "embarcadero": (-122.3937, 37.7955),
    "fisherman's wharf": (-122.4169, 37.8080),
    "chase center": (-122.3879, 37.7680),
    "oracle park": (-122.3892, 37.7786),
    "moscone center": (-122.4014, 37.7840),
    "civic center": (-122.4173, 37.7796),
    "san francisco": (-122.4183, 37.7775),
}

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _google_key() -> str | None:
    # this module sits two packages deep, so the repository root is four up
    root = Path(__file__).resolve().parents[4]
    env = root / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GOOGLE_MAPS_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    return os.environ.get("GOOGLE_MAPS_API_KEY") or None


@functools.lru_cache(maxsize=512)
def geocode(place: str) -> tuple[float, float, str]:
    """Resolve a place name to a point inside San Francisco."""
    key = (place or "").strip().lower()
    for name, (lon, lat) in GAZETTEER.items():
        if name in key:
            return lon, lat, f"{place} (gazetteer)"

    api_key = _google_key()
    if api_key:
        try:
            import httpx

            response = httpx.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "address": f"{place}, San Francisco, CA",
                    "bounds": "37.708,-122.517|37.834,-122.357",
                    "key": api_key,
                },
                timeout=20,
            )
            data = response.json()
            if data.get("results"):
                best = data["results"][0]
                loc = best["geometry"]["location"]
                return float(loc["lng"]), float(loc["lat"]), best["formatted_address"]
        except Exception:
            pass

    lon, lat = GAZETTEER["san francisco"]
    return lon, lat, f"{place} (could not be resolved; centred on the city)"


def build_tools(root: Path, world, sim, hub) -> dict:
    """Bind the tool names in the assistant's schema to real work."""

    def get_area_report(place: str, radius_metres: float = 300.0) -> ToolResult:
        lon, lat, resolved = geocode(place)
        report = layers.area_report(root, lon, lat, radius_metres)
        report["resolvedPlace"] = resolved
        report["footfall"] = insight.hourly_footfall(world, sim, lon, lat, radius_m=150.0)
        report["places"] = insight.nearby_places(world, lon, lat, radius_metres, limit=12)
        report["placeMix"] = insight.category_mix(world, lon, lat, radius_metres)
        return ToolResult(
            report,
            [
                {
                    "action": "flyTo",
                    "payload": {"lon": lon, "lat": lat, "zoom": 15.2, "label": resolved},
                }
            ],
        )

    def rank_sites(category: str, near: str | None = None, limit: int = 6) -> ToolResult:
        candidates = _candidate_frame(root, world, near)
        if candidates.empty:
            return ToolResult({"error": "no candidate sites available"})
        ranked = insight.rank_sites(root, world, sim, category, candidates, limit=limit)
        markers = [
            {
                "label": f"{i + 1}. score {r['score']}",
                "lon": r["location"][0],
                "lat": r["location"][1],
            }
            for i, r in enumerate(ranked)
            if "location" in r
        ]
        actions = [{"action": "highlight", "payload": {"markers": markers, "kind": "site"}}]
        if markers:
            actions.append(
                {
                    "action": "flyTo",
                    "payload": {"lon": markers[0]["lon"], "lat": markers[0]["lat"], "zoom": 14.4},
                }
            )
        return ToolResult({"category": category, "ranked": ranked}, actions)

    def simulate_event(venue: str, attendance: int = 15000, start_hour: int = 19,
                       day: str = "Friday") -> ToolResult:
        lon, lat, resolved = geocode(venue)
        day_index = DAYS.index(day.lower()) if day.lower() in DAYS else 4
        start = start_hour * 60
        spec = events_mod.EventSpec(
            lon=lon, lat=lat, name=resolved, attendance=int(attendance),
            start_minute=start, end_minute=start + 180,
        )
        result = events_mod.simulate(world, sim, spec)
        result["day"] = DAYS[day_index].capitalize()
        actions = [
            {"action": "flyTo", "payload": {"lon": lon, "lat": lat, "zoom": 14.6, "label": resolved}},
            {
                "action": "event",
                "payload": {
                    "lon": lon, "lat": lat, "label": resolved,
                    "attendance": int(attendance),
                    "origins": result.get("attendeeHomeSample", []),
                },
            },
        ]
        result.pop("attendeeHomeSample", None)  # drawn, not narrated
        return ToolResult(result, actions)

    def compare_areas(places: list[str]) -> ToolResult:
        rows = []
        markers = []
        for place in places[:4]:
            lon, lat, resolved = geocode(place)
            report = layers.area_report(root, lon, lat, 300.0)
            foot = insight.hourly_footfall(world, sim, lon, lat, radius_m=150.0)
            sections = report.get("sections", {})
            rows.append(
                {
                    "place": resolved,
                    "modelledPeakFootfall": foot["peopleAtPeak"],
                    "peakHour": foot["peakHour"],
                    "complaints12Months": sections.get("complaints", {}).get("total", 0),
                    "incidents12Months": sections.get("incidents", {}).get("total", 0),
                    "vacantStorefronts": sections.get("vacancy", {}).get("total", 0),
                    "placeMix": insight.category_mix(world, lon, lat, 250.0)[:5],
                }
            )
            markers.append({"label": resolved, "lon": lon, "lat": lat})
        return ToolResult(
            {"comparison": rows},
            [{"action": "highlight", "payload": {"markers": markers, "kind": "compare"}}],
        )

    def show_on_map(place: str, zoom: float = 15.0, markers: list | None = None,
                    layer: str | None = None) -> ToolResult:
        lon, lat, resolved = geocode(place)
        actions = [
            {"action": "flyTo", "payload": {"lon": lon, "lat": lat, "zoom": zoom, "label": resolved}}
        ]
        if markers:
            actions.append({"action": "highlight", "payload": {"markers": markers, "kind": "pin"}})
        if layer:
            actions.append({"action": "setLayer", "payload": {"layer": layer, "on": True}})
        return ToolResult({"shown": resolved, "lon": lon, "lat": lat}, actions)

    def set_time(hour: int, day: str = "Tuesday", minute: int = 0) -> ToolResult:
        day_index = DAYS.index(day.lower()) if day.lower() in DAYS else 1
        target = day_index * 1440 + int(hour) * 60 + int(minute)
        hub.sim.seek(target)
        return ToolResult(
            {"nowShowing": f"{day.capitalize()} {hour:02d}:{minute:02d}"},
            [{"action": "setTime", "payload": {"minute": target}}],
        )

    return {
        "get_area_report": get_area_report,
        "rank_sites": rank_sites,
        "simulate_event": simulate_event,
        "compare_areas": compare_areas,
        "show_on_map": show_on_map,
        "set_time": set_time,
    }


def _candidate_frame(root: Path, world, near: str | None) -> pd.DataFrame:
    """Candidate sites: real registered vacancies, narrowed to an area if asked."""
    path = root / "data" / "processed" / "commercial_vacancy.parquet"
    if path.exists():
        df = pd.read_parquet(path)
        df = df[df["lon"].notna() & df["lat"].notna()].copy()
        df["cand_id"] = np.arange(len(df))
    else:
        path = root / "data" / "processed" / "candidates.parquet"
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_parquet(path)

    if near:
        lon, lat, _ = geocode(near)
        mx = 111_320.0 * np.cos(np.radians(lat))
        dx = (df["lon"].to_numpy() - lon) * mx
        dy = (df["lat"].to_numpy() - lat) * 110_540.0
        df = df[np.hypot(dx, dy) <= 1200]

    # scoring every vacancy would be slow and pointless; thin to a spread
    if len(df) > 60:
        df = df.iloc[:: max(1, len(df) // 60)]
    return df.head(60).reset_index(drop=True)
