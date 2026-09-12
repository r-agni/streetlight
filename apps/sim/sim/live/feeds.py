"""Real upcoming events in San Francisco.

Two feeds that need no API key: the official MLB schedule endpoint for the
Giants at Oracle Park, and the NBA's published league schedule for Warriors
home games at Chase Center. Both are public JSON that the league's own sites
consume.

Ticketmaster would add concerts and theatre, but it needs a key; when
TICKETMASTER_KEY is present it is used, and when it is not the two league feeds
still give a real calendar to plan against.

Responses are cached for an hour because a schedule does not change minute to
minute and the endpoints are somebody else's to pay for.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CACHE = ROOT / "data" / "raw" / "events"
CACHE_SECONDS = 3600

GIANTS_TEAM_ID = 137
WARRIORS_TRICODE = "GSW"

VENUES = {
    "Oracle Park": (-122.3892, 37.7786, 41_331),
    "Chase Center": (-122.3879, 37.7680, 18_064),
}


def _cached(name: str, fetch) -> dict | list | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.json"
    if path.exists() and (time.time() - path.stat().st_mtime) < CACHE_SECONDS:
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    try:
        data = fetch()
    except Exception:
        # a stale cache beats no calendar at all
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                return None
        return None
    path.write_text(json.dumps(data))
    return data


def _giants(days: int) -> list[dict]:
    import httpx
    from datetime import date, timedelta

    start = date.today()
    end = start + timedelta(days=days)

    def fetch():
        response = httpx.get(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={
                "sportId": 1,
                "teamId": GIANTS_TEAM_ID,
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
            },
            timeout=25,
        )
        response.raise_for_status()
        return response.json()

    data = _cached("mlb_giants", fetch)
    if not isinstance(data, dict):
        return []

    out = []
    for day in data.get("dates", []):
        for game in day.get("games", []):
            venue = (game.get("venue") or {}).get("name", "")
            if "Oracle Park" not in venue:
                continue  # away games do not put anyone on San Francisco's streets
            teams = game.get("teams") or {}
            away = ((teams.get("away") or {}).get("team") or {}).get("name", "Visitors")
            out.append(
                {
                    "source": "MLB",
                    "kind": "game",
                    "name": f"Giants vs {away}",
                    "venue": "Oracle Park",
                    "startsAt": game.get("gameDate"),
                    "expectedAttendance": VENUES["Oracle Park"][2],
                }
            )
    return out


def _warriors(days: int) -> list[dict]:
    import httpx
    from datetime import datetime, timedelta

    def fetch():
        response = httpx.get(
            "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json",
            timeout=30,
            headers={"User-Agent": "sf-city-sim/0.1"},
        )
        response.raise_for_status()
        return response.json()

    data = _cached("nba_schedule", fetch)
    if not isinstance(data, dict):
        return []

    horizon = datetime.now() + timedelta(days=days)
    out = []
    for month in (data.get("leagueSchedule") or {}).get("gameDates", []):
        for game in month.get("games", []):
            home = (game.get("homeTeam") or {}).get("teamTricode")
            if home != WARRIORS_TRICODE:
                continue
            stamp = game.get("gameDateTimeEst") or game.get("gameDateEst") or ""
            try:
                when = datetime.fromisoformat(stamp.replace("Z", ""))
            except Exception:
                continue
            if not (datetime.now() <= when <= horizon):
                continue
            away = (game.get("awayTeam") or {}).get("teamName", "Visitors")
            out.append(
                {
                    "source": "NBA",
                    "kind": "game",
                    "name": f"Warriors vs {away}",
                    "venue": "Chase Center",
                    "startsAt": when.isoformat(),
                    "expectedAttendance": VENUES["Chase Center"][2],
                }
            )
    return out


def _ticketmaster(days: int) -> list[dict]:
    key = os.environ.get("TICKETMASTER_KEY")
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("TICKETMASTER_KEY="):
                    key = line.split("=", 1)[1].strip()
    if not key:
        return []

    import httpx
    from datetime import datetime, timedelta

    def fetch():
        response = httpx.get(
            "https://app.ticketmaster.com/discovery/v2/events.json",
            params={
                "apikey": key,
                "latlong": "37.7775,-122.4183",
                "radius": 8,
                "unit": "miles",
                "size": 60,
                "sort": "date,asc",
                "endDateTime": (datetime.utcnow() + timedelta(days=days)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            },
            timeout=25,
        )
        response.raise_for_status()
        return response.json()

    data = _cached("ticketmaster", fetch)
    if not isinstance(data, dict):
        return []

    out = []
    for event in (data.get("_embedded") or {}).get("events", []):
        venues = (event.get("_embedded") or {}).get("venues") or [{}]
        venue = venues[0]
        location = venue.get("location") or {}
        out.append(
            {
                "source": "Ticketmaster",
                "kind": "event",
                "name": event.get("name", "Event"),
                "venue": venue.get("name", "Venue"),
                "startsAt": ((event.get("dates") or {}).get("start") or {}).get("dateTime"),
                "lon": float(location["longitude"]) if location.get("longitude") else None,
                "lat": float(location["latitude"]) if location.get("latitude") else None,
                "expectedAttendance": None,
            }
        )
    return out


def upcoming(days: int = 45) -> dict:
    """Real events coming up, newest first, with the venue resolved."""
    events = _giants(days) + _warriors(days) + _ticketmaster(days)

    for event in events:
        known = VENUES.get(event.get("venue", ""))
        if known and event.get("lon") is None:
            event["lon"], event["lat"] = known[0], known[1]
        if not event.get("expectedAttendance") and known:
            event["expectedAttendance"] = known[2]

    events = [e for e in events if e.get("lon") is not None and e.get("startsAt")]
    events.sort(key=lambda e: e["startsAt"])

    sources = sorted({e["source"] for e in events})
    return {
        "count": len(events),
        "sources": sources,
        "events": events[:40],
        "note": (
            "Live league schedules. Concerts and theatre need a free "
            "Ticketmaster key in TICKETMASTER_KEY."
            if "Ticketmaster" not in sources
            else "Live league and Ticketmaster listings."
        ),
    }
