"""Live research, run when a question is asked rather than precomputed.

Everything here reaches out at question time. A cached answer about which
businesses trade on a street goes stale the week a lease turns over, and the
whole point of asking is to get today's picture.

What is actually reachable, and what is not:

- **Google Places text search** finds what trades there now, with ratings and
  review counts. Live, keyed, and the best supply measure available.
- **Google Place Details** returns real review text. This is the closest thing
  to hearing customers in their own words, and quotes are returned with the
  business name so an answer can cite them.
- **Census American Community Survey** gives who lives there. The Bureau's own
  API began demanding a key, so the same estimates are mirrored keylessly and
  pulled ahead of time by `scripts/06_census.py`; `demographics_near` reads
  those tables. Every figure keeps its margin of error.
- **Reddit** refuses unauthenticated requests: both the search endpoint and the
  old host return 403 or 404 without an OAuth app. It is reported as
  unavailable rather than quietly skipped, because "no discussion found" and
  "could not look" mean very different things to someone deciding where to
  put their money.
- **Facebook** has no free public search API at all.

Every fetch is cached briefly so that one question asking several things does
not pay for the same lookup twice.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CACHE_DIR = ROOT / "data" / "raw" / "research"
CACHE_SECONDS = 1800

PLACES_SEARCH = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS = "https://places.googleapis.com/v1/places/{place_id}"


@dataclass
class Citation:
    """Something an answer can point at."""

    source: str
    title: str
    detail: str = ""
    url: str = ""
    rating: float | None = None
    reviews: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "")}


@dataclass
class ResearchResult:
    citations: list[Citation] = field(default_factory=list)
    unavailable: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "citations": [c.to_dict() for c in self.citations],
            "unavailable": self.unavailable,
            "notes": self.notes,
        }


def _google_key() -> str | None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GOOGLE_MAPS_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    return os.environ.get("GOOGLE_MAPS_API_KEY") or None


def _cached(name: str, fetch):
    """Short-lived disk cache, so one question does not pay twice."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:120]
    path = CACHE_DIR / f"{safe}.json"
    if path.exists() and (time.time() - path.stat().st_mtime) < CACHE_SECONDS:
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    data = fetch()
    try:
        path.write_text(json.dumps(data))
    except Exception:
        pass
    return data


# ------------------------------------------------------------------ listings


def search_listings(query: str, lon: float, lat: float, radius_m: float = 1500,
                    limit: int = 12) -> list[dict]:
    """What actually trades near a point, right now."""
    key = _google_key()
    if not key:
        return []
    import httpx

    def fetch():
        response = httpx.post(
            PLACES_SEARCH,
            headers={
                "X-Goog-Api-Key": key,
                "Content-Type": "application/json",
                "X-Goog-FieldMask": ",".join(
                    [
                        "places.id",
                        "places.displayName",
                        "places.formattedAddress",
                        "places.location",
                        "places.rating",
                        "places.userRatingCount",
                        "places.primaryType",
                        "places.businessStatus",
                        "places.priceLevel",
                    ]
                ),
            },
            json={
                "textQuery": query,
                "maxResultCount": limit,
                "locationBias": {
                    "circle": {"center": {"latitude": lat, "longitude": lon},
                               "radius": float(radius_m)}
                },
            },
            timeout=25,
        )
        if response.status_code != 200:
            return {"places": []}
        return response.json()

    data = _cached(f"search_{query}_{lon:.3f}_{lat:.3f}", fetch)
    out = []
    for place in data.get("places", []):
        if place.get("businessStatus") not in (None, "OPERATIONAL"):
            continue
        location = place.get("location") or {}
        out.append(
            {
                "id": place.get("id"),
                "name": (place.get("displayName") or {}).get("text", ""),
                "address": place.get("formattedAddress", ""),
                "rating": place.get("rating"),
                "reviews": place.get("userRatingCount") or 0,
                "type": place.get("primaryType"),
                "priceLevel": place.get("priceLevel"),
                "lon": location.get("longitude"),
                "lat": location.get("latitude"),
            }
        )
    return out


def fetch_reviews(place_id: str, limit: int = 4) -> list[dict]:
    """What customers said, in their own words."""
    key = _google_key()
    if not key or not place_id:
        return []
    import httpx

    def fetch():
        response = httpx.get(
            PLACES_DETAILS.format(place_id=place_id),
            headers={
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "displayName,rating,userRatingCount,reviews",
            },
            timeout=25,
        )
        if response.status_code != 200:
            return {}
        return response.json()

    data = _cached(f"details_{place_id}", fetch)
    out = []
    for review in (data.get("reviews") or [])[:limit]:
        text = (review.get("text") or {}).get("text", "").strip()
        if not text:
            continue
        out.append(
            {
                "rating": review.get("rating"),
                "text": text[:420],
                "when": review.get("relativePublishTimeDescription", ""),
                "place": (data.get("displayName") or {}).get("text", ""),
            }
        )
    return out


# --------------------------------------------------------------- demographics


def demographics_near(lon: float | None, lat: float | None, radius_m: float = 900.0) -> dict:
    """Who lives around a point, from the census tables built by 06_census.py.

    This replaced a live call to the Census Bureau API, which now refuses
    unauthenticated requests. The data is the same American Community Survey,
    reached through keyless mirrors and pulled ahead of time, so a question
    asked at 2am does not depend on a signup.
    """
    from . import demographics as demo

    if not demo.available():
        return {
            "available": False,
            "reason": (
                "Census tables have not been built on this machine. "
                "Run scripts/06_census.py, which needs no API key."
            ),
        }
    if lon is None or lat is None:
        return {"available": True, "citywide": demo._citywide(), "source": demo.SOURCE_NOTE}
    return demo.near(lon, lat, radius_m)


# ---------------------------------------------------------------- discussion


def discussion(query: str) -> dict:
    """Public discussion about a topic. Currently not reachable without keys."""
    import httpx

    attempts = []
    for url in (
        f"https://www.reddit.com/search.json?q={query}&limit=8&t=year",
        f"https://old.reddit.com/search.json?q={query}&limit=8",
    ):
        try:
            response = httpx.get(
                url,
                headers={"User-Agent": "sf-city-sim/0.1 (research)"},
                timeout=15,
                follow_redirects=True,
            )
            if response.status_code == 200:
                children = (response.json().get("data") or {}).get("children") or []
                if children:
                    return {
                        "available": True,
                        "posts": [
                            {
                                "title": c["data"].get("title", ""),
                                "subreddit": c["data"].get("subreddit", ""),
                                "score": c["data"].get("score", 0),
                                "url": "https://reddit.com" + c["data"].get("permalink", ""),
                            }
                            for c in children[:6]
                        ],
                    }
            attempts.append(f"{response.status_code} from {url.split('/')[2]}")
        except Exception as exc:
            attempts.append(f"{type(exc).__name__} from {url.split('/')[2]}")

    return {
        "available": False,
        "reason": (
            "Reddit refuses unauthenticated requests ("
            + "; ".join(attempts)
            + "). Reading it needs a free Reddit OAuth app. Facebook has no "
            "public search API at all. Customer opinion here comes from Google "
            "review text instead."
        ),
    }
