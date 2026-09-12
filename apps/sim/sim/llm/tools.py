"""Tool implementations the assistant calls.

Each one is a thin adapter: resolve whatever the model said into coordinates,
call the analysis code, and return three things - a compact payload for the
model, any map actions for the browser, and the list of sources it read. No
analysis happens here.

The sources are declared by the tool rather than described by the model, so the
trail shown to the user is a record of what was actually touched rather than a
plausible account of it.

Place names are resolved with Google Geocoding, biased to San Francisco. If no
key is configured, a built-in gazetteer of neighbourhoods and landmarks covers
the common cases so the assistant still works.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

import numpy as np
import pandas as pd

from ..analysis import events as events_mod
from ..analysis import insight, layers, opportunity, research, websearch
from .contracts import (
    Source,
    ToolResult,
    network_source,
    open_data_source,
    places_source,
    simulation_source,
)

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

# open-data tables, and the wording used when reporting them
SECTION_SOURCES = {
    "complaints": ("311 complaints", "last 12 months"),
    "incidents": ("Police incidents", "last 12 months"),
    "vacancy": ("Commercial vacancy filings", "latest filing"),
    "permits": ("Building permits", "last 3 years"),
    "landUse": ("Land use and parcels", "assessor roll"),
}


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


def _geocode_source(resolved: str) -> Source:
    local = "gazetteer" in resolved or "could not be resolved" in resolved
    return Source(
        label="Geocoding",
        kind="reference",
        detail="Built-in gazetteer" if local else "Google Geocoding, biased to San Francisco",
    )


def _section_sources(report: dict) -> list[Source]:
    """One source per open-data section the report actually found."""
    out = []
    for key, section in (report.get("sections") or {}).items():
        label, window = SECTION_SOURCES.get(key, (section.get("label", key), None))
        count = section.get("total") or section.get("parcels")
        out.append(open_data_source(label, int(count or 0), section.get("window") or window))
    return out


def _dedupe(sources: list[Source]) -> list[Source]:
    """Merge repeats, summing counts, so a comparison lists each table once."""
    merged: dict[str, Source] = {}
    for source in sources:
        existing = merged.get(source.label)
        if existing is None:
            merged[source.label] = Source(
                label=source.label, kind=source.kind, detail=source.detail,
                count=source.count, window=source.window,
            )
        elif source.count and existing.count:
            existing.count += source.count
    return list(merged.values())


def build_tools(root: Path, world, sim, hub) -> dict:
    """Bind the tool names in the assistant's schema to real work."""

    enriched = int(np.count_nonzero(world.poi_reviews > 0))

    def get_area_report(place: str, radius_metres: float = 300.0) -> ToolResult:
        lon, lat, resolved = geocode(place)
        report = layers.area_report(root, lon, lat, radius_metres)
        report["resolvedPlace"] = resolved
        foot = insight.hourly_footfall(world, sim, lon, lat, radius_m=150.0)
        report["footfall"] = foot
        report["places"] = insight.nearby_places(world, lon, lat, radius_metres, limit=12)
        report["placeMix"] = insight.category_mix(world, lon, lat, radius_metres)

        sources = [_geocode_source(resolved), *_section_sources(report)]
        sources.append(
            simulation_source(
                world.n_agents,
                "Density within 150 m, averaged over "
                f"{len(foot.get('hoursSimulated', []))} simulated hours",
            )
        )
        sources.append(places_source(world.n_pois, enriched))
        # Switch on the layers this report actually has numbers for. An answer
        # quoting complaint counts beside a blank map is a paragraph, not a map
        # product, and whether that happens should not depend on the model
        # remembering to ask for it.
        present = set((report.get("sections") or {}).keys())
        layers_on = [name for name in ("complaints", "incidents", "permits", "vacancy")
                     if name in present]
        return ToolResult(
            report,
            [
                {"action": "setLayers", "payload": {"on": layers_on}},
                {"action": "flyTo",
                 "payload": {"lon": lon, "lat": lat, "zoom": 15.2, "label": resolved}},
                {"action": "highlight",
                 "payload": {"markers": [{"label": resolved.split(",")[0][:22],
                                          "lon": lon, "lat": lat}], "kind": "pin"}},
            ],
            sources,
            f"Read everything within {int(radius_metres)} m of {resolved}.",
        )

    def find_opportunity(concept: str, search_terms: list[str],
                         areas: list[str] | None = None,
                         category: str | None = None) -> ToolResult:
        """Where appetite for a concept outruns what already trades there."""
        names = areas or [
            "mission", "soma", "downtown", "hayes valley", "richmond",
            "sunset", "north beach", "castro", "nob hill", "potrero hill",
        ]
        resolved = []
        for name in names[:10]:
            lon, lat, label = geocode(name)
            resolved.append(opportunity.Area(name=label.split(" (")[0], lon=lon, lat=lat))

        result = opportunity.analyse(
            root, world, sim, concept, list(search_terms), resolved, category
        )
        top = result["areas"][:6]

        # A neighbourhood is not a place you can lease. Score the registered
        # vacancies inside the best areas so the recommendation ends at an
        # address the operator can actually go and look at.
        lease_category = category or "cafe"
        best_areas = [row["area"] for row in result["areas"][:3]]
        vacancies = []
        for area_name in best_areas:
            frame = _candidate_frame(root, world, area_name)
            if frame.empty:
                continue
            ranked = insight.rank_sites(root, world, sim, lease_category, frame, limit=3)
            for site in ranked:
                if "location" not in site:
                    continue
                site["area"] = area_name
                vacancies.append(site)
        vacancies.sort(key=lambda s: -s["score"])
        vacancies = vacancies[:6]
        result["vacantSites"] = vacancies
        result["vacantSiteNote"] = (
            "Registered under the commercial vacancy tax and scored against each "
            "other for a " + lease_category.replace("_", " ") + ". A filing means "
            "the space was reported vacant, not that it is listed or available today."
        )

        markers = [
            {"label": str(i + 1), "lon": site["location"][0], "lat": site["location"][1]}
            for i, site in enumerate(vacancies)
        ] or [
            {"label": str(row["rank"]), "lon": row["lon"], "lat": row["lat"]}
            for row in top
        ]
        actions = [
            {"action": "setMode", "payload": {"mode": "business"}},
            {"action": "highlight", "payload": {"markers": markers, "kind": "site"}},
        ]
        if vacancies:
            # the panel shows the same addresses the answer names
            actions.append({"action": "setSites", "payload": {"sites": vacancies}})
            actions.append(
                {"action": "setPanelQuery",
                 "payload": {"siteCategory": lease_category,
                             "siteNear": best_areas[0] if best_areas else ""}}
            )
        if markers:
            actions.append(
                {"action": "flyTo",
                 "payload": {"lon": markers[0]["lon"], "lat": markers[0]["lat"],
                             "zoom": 15.0 if vacancies else 13.6}}
            )

        sources = [
            places_source(world.n_pois, enriched),
            simulation_source(world.n_agents, "Footfall and ten-minute catchment per area"),
            network_source(len(world.node_lon), "Walking catchment by Dijkstra over the street graph"),
        ]
        if result.get("listingsSearched"):
            sources.insert(
                0,
                Source(
                    label="Google Places listings",
                    kind="recorded",
                    detail=(
                        f"Text search for {', '.join(search_terms[:3])} across "
                        f"{len(resolved)} areas, with ratings and review counts"
                    ),
                    count=result.get("listingCalls"),
                ),
            )
        else:
            sources.insert(
                0,
                Source(
                    label="Listings search",
                    kind="reference",
                    detail="No Google key configured; supply counted from the catalog only",
                ),
            )
        if vacancies:
            sources.append(
                open_data_source(
                    "Commercial vacancy filings",
                    len(vacancies),
                    "scored inside the best areas",
                )
            )
        summary = (
            f"Weighed {len(resolved)} areas for {concept}, then scored "
            f"{len(vacancies)} registered vacancies inside the best of them."
            if vacancies
            else f"Weighed {len(resolved)} areas for {concept} against what already trades there."
        )
        return ToolResult(result, actions, sources, summary)

    def research_demand(topic: str, place: str,
                        search_terms: list[str] | None = None) -> ToolResult:
        """Fetch live evidence about a topic in one place, and cite it."""
        lon, lat, resolved = geocode(place)
        terms = list(search_terms or [topic])
        found = research.ResearchResult()

        # 1. what trades there right now
        listings: list[dict] = []
        for term in terms[:3]:
            listings.extend(research.search_listings(f"{term} in {resolved}", lon, lat))
        seen: set[str] = set()
        unique: list[dict] = []
        for entry in listings:
            name = (entry.get("name") or "").lower()
            if name and name not in seen:
                seen.add(name)
                unique.append(entry)
        unique.sort(key=lambda e: -(e.get("reviews") or 0))

        for entry in unique[:8]:
            found.citations.append(
                research.Citation(
                    source="Google Places",
                    title=entry["name"],
                    detail=entry.get("address", ""),
                    rating=entry.get("rating"),
                    reviews=entry.get("reviews"),
                )
            )

        # 2. what customers say about the busiest of them
        quotes: list[dict] = []
        for entry in unique[:3]:
            for review in research.fetch_reviews(entry.get("id") or "", limit=2):
                quotes.append(review)
                found.citations.append(
                    research.Citation(
                        source="Google review",
                        title=review["place"],
                        detail=review["text"][:240],
                        rating=review.get("rating"),
                    )
                )

        # 3. who lives there
        demographics = research.census_tracts([])
        if not demographics.get("available"):
            found.unavailable.append(
                {"source": "Census ACS", "reason": demographics.get("reason", "")}
            )

        # 4. public discussion
        talk = research.discussion(f"{topic} san francisco")
        if talk.get("available"):
            for post in talk["posts"]:
                found.citations.append(
                    research.Citation(
                        source=f"Reddit r/{post['subreddit']}",
                        title=post["title"],
                        url=post["url"],
                        detail=f"{post['score']} points",
                    )
                )
        else:
            found.unavailable.append({"source": "Reddit", "reason": talk.get("reason", "")})
            found.unavailable.append(
                {"source": "Facebook", "reason": "No public search API exists."}
            )

        # 5. what sits empty nearby
        vacancy = layers.area_report(root, lon, lat, 600.0).get("sections", {}).get("vacancy")
        if vacancy:
            found.notes.append(
                f"{vacancy['total']:,} commercial vacancy filings sit within 600 m."
            )

        payload = {
            "topic": topic,
            "place": resolved,
            "tradingNow": unique[:8],
            "customerQuotes": quotes[:6],
            "vacancyNearby": (vacancy or {}).get("total", 0),
            "demographics": demographics,
            **found.to_dict(),
        }

        sources = [_geocode_source(resolved)]
        if unique:
            sources.append(
                Source(
                    label="Google Places listings",
                    kind="recorded",
                    detail="Live text search for " + ", ".join(terms[:3]),
                    count=len(unique),
                )
            )
        if quotes:
            sources.append(
                Source(
                    label="Google review text",
                    kind="recorded",
                    detail="Customer reviews of the busiest competitors",
                    count=len(quotes),
                )
            )
        if demographics.get("available"):
            sources.append(
                Source(
                    label="Census ACS 2023",
                    kind="recorded",
                    detail="Tract population, income, rent and detailed origin",
                    count=len(demographics.get("tracts", [])),
                )
            )
        if vacancy:
            sources.append(
                open_data_source("Commercial vacancy filings", vacancy["total"], "latest filing")
            )
        for gap in found.unavailable:
            sources.append(
                Source(
                    label=gap["source"],
                    kind="reference",
                    detail="Not reachable: " + gap["reason"][:140],
                )
            )

        return ToolResult(
            payload,
            [{"action": "flyTo",
              "payload": {"lon": lon, "lat": lat, "zoom": 14.6, "label": resolved}}],
            sources,
            f"Fetched live listings, review text and vacancy for {topic} in {resolved}.",
        )

    def search_public_discussion(topic: str, place: str = "San Francisco",
                                 include_press: bool = True) -> ToolResult:
        """Read Reddit, Facebook and local press through hosted web search."""
        community = websearch.community_sentiment(topic, place)
        press = websearch.local_demand(topic, place) if include_press else {"available": False}

        sources: list[Source] = []
        warnings: list[str] = []

        for label, result in (("Reddit and Facebook", community), ("Press and blogs", press)):
            if not result.get("available"):
                if result.get("reason"):
                    sources.append(
                        Source(label=label, kind="reference",
                               detail="Not reachable: " + str(result["reason"])[:140])
                    )
                continue
            cited = ", ".join(result.get("platformsCited") or []) or "web pages"
            sources.append(
                Source(
                    label=label,
                    kind="reference",
                    detail=(
                        "Hosted web search, summarised with links from "
                        + cited
                        + ". Not fetched from the platform directly."
                    ),
                    count=len(result.get("citations") or []),
                )
            )
            if result.get("attributionWarning"):
                warnings.append(result["attributionWarning"])

        payload = {
            "topic": topic,
            "place": place,
            "community": {
                "summary": community.get("summary"),
                "citations": community.get("citations"),
                "trustworthy": community.get("trustworthy"),
                "attributionWarning": community.get("attributionWarning"),
                "queriesRun": community.get("queriesRun"),
                "reason": community.get("reason"),
            },
            "press": {
                "summary": press.get("summary"),
                "citations": press.get("citations"),
                "trustworthy": press.get("trustworthy"),
                "attributionWarning": press.get("attributionWarning"),
                "reason": press.get("reason"),
            },
            "howToUseThis": (
                "These are search results summarised by a model, with links, not "
                "posts fetched from Reddit or Facebook. Quote something only if a "
                "citation points at the platform it is attributed to. Where an "
                "attribution warning is present, say the discussion could not be "
                "verified instead of repeating the quote."
            ),
        }
        if warnings:
            payload["warnings"] = warnings

        return ToolResult(
            payload,
            [],
            sources,
            f"Searched public discussion and press for {topic} in {place}.",
        )

    def rank_sites(category: str, near: str | None = None, limit: int = 6) -> ToolResult:
        candidates = _candidate_frame(root, world, near)
        if candidates.empty:
            return ToolResult({"error": "no candidate sites available"})
        ranked = insight.rank_sites(root, world, sim, category, candidates, limit=limit)
        markers = [
            {"label": str(r["rank"]), "lon": r["location"][0], "lat": r["location"][1]}
            for r in ranked
            if "location" in r
        ]
        actions = [
            {"action": "setMode", "payload": {"mode": "business"}},
            {"action": "setPanelQuery",
             "payload": {"siteCategory": category, "siteNear": near or ""}},
            {"action": "setSites", "payload": {"sites": ranked}},
            {"action": "highlight", "payload": {"markers": markers, "kind": "site"}},
        ]
        if markers:
            actions.append(
                {"action": "flyTo",
                 "payload": {"lon": markers[0]["lon"], "lat": markers[0]["lat"], "zoom": 14.4}}
            )

        sources = [
            open_data_source("Commercial vacancy filings", len(candidates), "latest filing"),
            simulation_source(world.n_agents, "Footfall within 150 m of each candidate"),
            network_source(
                len(world.node_lon),
                "Ten-minute walking catchment by Dijkstra over the street graph",
            ),
            places_source(world.n_pois, enriched),
        ]
        if near:
            sources.insert(0, _geocode_source(geocode(near)[2]))
        return ToolResult(
            {"category": category, "ranked": ranked},
            actions,
            sources,
            f"Scored {len(candidates)} vacant parcels for a "
            f"{category.replace('_', ' ')} against each other.",
        )

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
        origins = result.get("attendeeHomeSample", [])
        actions = [
            {"action": "setMode", "payload": {"mode": "events"}},
            {"action": "setPanelQuery",
             "payload": {"eventVenue": resolved, "eventAttendance": int(attendance),
                         "eventHour": start_hour}},
            {"action": "setEventReport", "payload": {"report": result}},
            {"action": "flyTo",
             "payload": {"lon": lon, "lat": lat, "zoom": 14.6, "label": resolved}},
            {"action": "event",
             "payload": {"lon": lon, "lat": lat, "label": resolved,
                         "attendance": int(attendance), "origins": origins}},
            # the crowd is the whole point, so make sure people are drawn, and
            # put the clock where the arrivals actually happen
            {"action": "setToggles", "payload": {"showAgents": True, "showDensity": True}},
            {"action": "setTime", "payload": {"minute": 4 * 1440 + max(start - 45, 0)}},
        ]
        result.pop("attendeeHomeSample", None)  # drawn, not narrated
        sources = [
            _geocode_source(resolved),
            simulation_source(
                world.n_agents,
                "Attendance drawn from agent home locations by distance decay",
            ),
            places_source(world.n_pois, enriched),
        ]
        return ToolResult(
            result, actions, sources,
            f"Modelled {int(attendance):,} people at {resolved} starting {start_hour:02d}:00.",
        )

    def compare_areas(places: list[str]) -> ToolResult:
        rows, markers, sources = [], [], []
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
            sources.extend(_section_sources(report))
        sources.append(simulation_source(world.n_agents, "Footfall within 150 m of each place"))
        compare_actions: list[dict] = [
            {"action": "highlight", "payload": {"markers": markers, "kind": "compare"}},
            {"action": "setLayers", "payload": {"on": ["complaints", "incidents"]}},
        ]
        if markers:
            compare_actions.append(
                {"action": "flyTo",
                 "payload": {"lon": markers[0]["lon"], "lat": markers[0]["lat"], "zoom": 13.4}}
            )
        return ToolResult(
            {"comparison": rows},
            compare_actions,
            _dedupe(sources),
            f"Compared {len(rows)} places on footfall, complaints, incidents and vacancy.",
        )

    def show_on_map(place: str, zoom: float = 15.0, markers: list | None = None,
                    layer: str | None = None) -> ToolResult:
        lon, lat, resolved = geocode(place)
        actions = [
            {"action": "flyTo",
             "payload": {"lon": lon, "lat": lat, "zoom": zoom, "label": resolved}}
        ]
        if markers:
            actions.append({"action": "highlight", "payload": {"markers": markers, "kind": "pin"}})
        if layer:
            actions.append({"action": "setLayer", "payload": {"layer": layer, "on": True}})
        return ToolResult(
            {"shown": resolved, "lon": lon, "lat": lat},
            actions,
            [_geocode_source(resolved)],
            f"Moved the map to {resolved}.",
        )

    def set_time(hour: int, day: str = "Tuesday", minute: int = 0) -> ToolResult:
        day_index = DAYS.index(day.lower()) if day.lower() in DAYS else 1
        target = day_index * 1440 + int(hour) * 60 + int(minute)
        hub.sim.seek(target)
        return ToolResult(
            {"nowShowing": f"{day.capitalize()} {hour:02d}:{minute:02d}"},
            [{"action": "setTime", "payload": {"minute": target}}],
            [simulation_source(world.n_agents, "Clock moved; the day replays to that minute")],
            f"Set the clock to {day.capitalize()} {hour:02d}:{minute:02d}.",
        )

    def control_interface(
        mode: str | None = None,
        layers_on: list[str] | None = None,
        layers_off: list[str] | None = None,
        show_places: bool | None = None,
        show_people: bool | None = None,
        show_density: bool | None = None,
        playing: bool | None = None,
        speed: int | None = None,
        centre_on: str | None = None,
        zoom: float | None = None,
        bearing: float | None = None,
        pitch: float | None = None,
        clear_drawing: bool | None = None,
    ) -> ToolResult:
        """Drive the interface itself: tabs, switches, playback and camera."""
        actions: list[dict] = []
        did: list[str] = []

        if mode:
            actions.append({"action": "setMode", "payload": {"mode": mode}})
            did.append(f"opened the {mode} panel")

        for name in layers_on or []:
            actions.append({"action": "setLayer", "payload": {"layer": name, "on": True}})
        for name in layers_off or []:
            actions.append({"action": "setLayer", "payload": {"layer": name, "on": False}})
        if layers_on:
            did.append("switched on " + ", ".join(layers_on))
        if layers_off:
            did.append("switched off " + ", ".join(layers_off))

        toggles: dict = {}
        if show_places is not None:
            toggles["showPlaces"] = show_places
        if show_people is not None:
            toggles["showAgents"] = show_people
        if show_density is not None:
            toggles["showDensity"] = show_density
        if toggles:
            actions.append({"action": "setToggles", "payload": toggles})
            did.append("adjusted the map switches")

        if playing is not None or speed is not None:
            payload: dict = {}
            if playing is not None:
                hub.playing = bool(playing)
                payload["playing"] = bool(playing)
            if speed is not None:
                hub.speed = float(np.clip(float(speed), 1.0, 600.0))
                payload["speed"] = hub.speed
            actions.append({"action": "setPlayback", "payload": payload})
            did.append("changed playback")

        if centre_on or zoom is not None or bearing is not None or pitch is not None:
            camera: dict = {}
            if centre_on:
                lon, lat, resolved = geocode(centre_on)
                camera.update({"lon": lon, "lat": lat, "label": resolved})
                did.append(f"moved the map to {resolved}")
            if zoom is not None:
                camera["zoom"] = float(zoom)
            if bearing is not None:
                camera["bearing"] = float(bearing)
            if pitch is not None:
                camera["pitch"] = float(pitch)
            actions.append({"action": "flyTo", "payload": camera})

        if clear_drawing:
            actions.append({"action": "clear", "payload": {}})
            did.append("cleared the drawing")

        return ToolResult(
            {"applied": did or ["nothing to change"]},
            actions,
            [Source(label="Interface", kind="derived",
                    detail="Panels, switches, playback and camera")],
            "; ".join(did) if did else "No interface change requested.",
        )

    return {
        "get_area_report": get_area_report,
        "find_opportunity": find_opportunity,
        "research_demand": research_demand,
        "search_public_discussion": search_public_discussion,
        "rank_sites": rank_sites,
        "simulate_event": simulate_event,
        "compare_areas": compare_areas,
        "show_on_map": show_on_map,
        "set_time": set_time,
        "control_interface": control_interface,
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
