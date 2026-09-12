"""Answering questions without a language model.

The assistant is better with Claude: it handles phrasing nobody anticipated,
asks follow-up tools, and explains trade-offs. But a demo that dies without an
API key is not a demo, and the underlying analysis does not need a model at
all - only the routing and the wording do.

So this module does the routing with keywords and the wording with templates,
over exactly the same tools. Numbers are identical either way; what is lost is
flexibility of phrasing, and that loss is stated to the user rather than
hidden.
"""
from __future__ import annotations

import re

from .tools import GAZETTEER

# category words a person might use, mapped to the catalog
CATEGORY_WORDS = {
    "cafe": "cafe", "coffee": "cafe", "coffee shop": "cafe",
    "restaurant": "restaurant", "eatery": "restaurant", "diner": "restaurant",
    "bar": "bar", "pub": "bar", "cocktail": "bar",
    "grocery": "grocery", "supermarket": "grocery", "market": "grocery",
    "gym": "gym", "fitness": "gym", "studio": "gym",
    "shop": "retail", "store": "retail", "retail": "retail",
    "clothing": "clothing", "boutique": "clothing",
    "pharmacy": "pharmacy", "chemist": "pharmacy",
    "hotel": "hotel",
    "fast food": "fast_food", "takeaway": "fast_food",
}

EVENT_WORDS = (
    "event", "concert", "game", "match", "festival", "crowd", "warriors",
    "giants", "sold out", "gig", "show at",
)
SITE_WORDS = (
    "where should", "best place", "best site", "open a", "open my", "put a",
    "site for", "location for", "locate", "rank", "candidates",
)
COMPARE_WORDS = ("compare", " vs ", "versus", "better than", "which is better")


def _find_places(text: str) -> list[str]:
    """Gazetteer names mentioned, longest first so 'mission district' wins."""
    lowered = text.lower()
    found = [name for name in GAZETTEER if name in lowered and name != "san francisco"]
    found.sort(key=len, reverse=True)
    # drop names contained inside a longer match
    kept: list[str] = []
    for name in found:
        if not any(name in other for other in kept):
            kept.append(name)
    return kept


def _find_place(text: str) -> str:
    places = _find_places(text)
    if places:
        return places[0]
    # fall back to whatever follows a locative preposition, for real addresses
    match = re.search(r"\b(?:in|near|at|around|by)\s+([A-Za-z0-9'&.\- ]{3,48})", text, re.I)
    if match:
        return match.group(1).strip(" ?.!,")
    return "san francisco"


def _find_category(text: str) -> str:
    lowered = text.lower()
    for word in sorted(CATEGORY_WORDS, key=len, reverse=True):
        if word in lowered:
            return CATEGORY_WORDS[word]
    return "cafe"


def _find_attendance(text: str) -> int:
    match = re.search(r"([\d,]{3,7})\s*(?:people|fans|attendees|seats)?", text)
    if match:
        try:
            value = int(match.group(1).replace(",", ""))
            if 500 <= value <= 100_000:
                return value
        except ValueError:
            pass
    return 18_000


def _find_hour(text: str) -> int:
    match = re.search(r"\b(\d{1,2})\s*(?:pm|p\.m\.)", text, re.I)
    if match:
        hour = int(match.group(1))
        return hour + 12 if hour < 12 else hour
    match = re.search(r"\b(\d{1,2})\s*(?:am|a\.m\.)", text, re.I)
    if match:
        return int(match.group(1)) % 12
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if match:
        return int(match.group(1))
    return 19


def route(question: str) -> tuple[str, dict]:
    """Pick a tool and its arguments from the wording alone."""
    lowered = question.lower()
    if any(w in lowered for w in EVENT_WORDS):
        return "simulate_event", {
            "venue": _find_place(question),
            "attendance": _find_attendance(question),
            "start_hour": _find_hour(question),
        }
    if any(w in lowered for w in COMPARE_WORDS):
        places = _find_places(question)
        if len(places) >= 2:
            return "compare_areas", {"places": places[:3]}
    if any(w in lowered for w in SITE_WORDS):
        return "rank_sites", {
            "category": _find_category(question),
            "near": _find_place(question),
            "limit": 5,
        }
    return "get_area_report", {"place": _find_place(question)}


# ------------------------------------------------------------------ wording


def _hour(h: int) -> str:
    return f"{h:02d}:00"


def render(tool: str, payload: dict) -> str:
    if "error" in payload:
        return f"That did not work: {payload['error']}"
    if tool == "get_area_report":
        return _render_area(payload)
    if tool == "rank_sites":
        return _render_sites(payload)
    if tool == "simulate_event":
        return _render_event(payload)
    if tool == "compare_areas":
        return _render_compare(payload)
    return "I do not have an answer for that yet."


def _render_area(p: dict) -> str:
    lines = [f"**{p.get('resolvedPlace', 'That location')}**", ""]
    foot = p.get("footfall") or {}
    if foot.get("peopleAtPeak"):
        lines.append(
            f"Modelled footfall peaks at about {foot['peopleAtPeak']:,} people "
            f"around {_hour(foot['peakHour'])}. That is simulation output, not a count."
        )
    sections = p.get("sections") or {}
    if "complaints" in sections:
        c = sections["complaints"]
        top = ", ".join(t["name"] for t in (c.get("top") or [])[:3])
        lines.append(
            f"Residents filed {c['total']:,} 311 complaints here in the {c['window']}"
            + (f", mostly {top.lower()}." if top else ".")
        )
    if "incidents" in sections:
        i = sections["incidents"]
        top = ", ".join(t["name"] for t in (i.get("top") or [])[:2])
        lines.append(
            f"Police recorded {i['total']:,} incidents in the same period"
            + (f", led by {top.lower()}." if top else ".")
        )
    if "vacancy" in sections:
        lines.append(
            f"{sections['vacancy']['total']:,} commercial vacancy filings sit within the radius."
        )
    if "permits" in sections:
        pm = sections["permits"]
        extra = f", proposing {pm['proposedUnits']:,} homes" if pm.get("proposedUnits") else ""
        lines.append(f"{pm['total']:,} building permits were filed here in the last three years{extra}.")
    if "landUse" in sections:
        lu = sections["landUse"]
        lines.append(
            f"Land use covers {lu.get('parcels', 0):,} parcels with about "
            f"{lu.get('residentialUnits', 0):,} homes and "
            f"{lu.get('retailSqFt', 0):,} square feet of retail."
        )
    mix = p.get("placeMix") or []
    if mix:
        lines.append(
            "The mix nearby is mostly "
            + ", ".join(f"{m['category'].replace('_', ' ')} ({m['count']})" for m in mix[:4])
            + "."
        )
    return "\n\n".join(lines)


def _render_sites(p: dict) -> str:
    ranked = p.get("ranked") or []
    if not ranked:
        return "No candidate sites came back for that category and area."
    category = p.get("category", "business")
    lines = [
        f"Best {category.replace('_', ' ')} sites among {len(ranked)} registered "
        f"vacant parcels, scored against each other:",
        "",
    ]
    for site in ranked[:5]:
        address = site.get("address") or "unnamed parcel"
        lines.append(
            f"**{site['rank']}. {address}** — score {site['score']}. "
            f"Modelled peak footfall {site['modelledPeakFootfall']:,}, "
            f"{site['walkCatchmentResidents']:,} people within a ten-minute walk, "
            f"{site['competitorsWithinRadius']} competitors nearby. {site['reading']}"
        )
    lines.append("")
    lines.append(
        "Scores are relative to this candidate set, not absolute. Footfall and "
        "catchment are model output; the vacancies are filed records."
    )
    return "\n\n".join(lines)


def _render_event(p: dict) -> str:
    event = p.get("event") or {}
    mode = p.get("likelyMode") or {}
    crowd = p.get("crowding") or []
    lines = [
        f"**{event.get('name', 'That venue')} — {event.get('attendance', 0):,} people**",
        "",
        f"About {p.get('modelledFromResidents', 0):,} would come from within the city "
        f"and {p.get('assumedFromOutsideTheCity', 0):,} from outside it.",
    ]
    if mode:
        lines.append(
            "Likely arrival: "
            + ", ".join(f"{v:,} {k.replace('fromOutside', 'from outside')}" for k, v in mode.items())
            + "."
        )
    if crowd:
        first = crowd[0]
        lines.append(
            f"Within 150 m of the doors, about {first['people']:,} people, "
            f"roughly {first['peoplePerSquareMetre']} per square metre: {first['comfort']}."
        )
    uplift = p.get("businessUplift") or []
    if uplift:
        lines.append(
            "Businesses inside the crowd: "
            + ", ".join(
                f"{u['places']} {u['category'].replace('_', ' ')} places seeing about "
                f"{u['peoplePerPlace']:,} people each"
                for u in uplift[:3]
            )
            + "."
        )
    lines.append("")
    lines.append(p.get("method", ""))
    return "\n\n".join(line for line in lines if line is not None)


def _render_compare(p: dict) -> str:
    rows = p.get("comparison") or []
    if not rows:
        return "I could not resolve those places."
    lines = ["Comparison:", ""]
    for row in rows:
        lines.append(
            f"**{row['place']}** — modelled peak footfall {row['modelledPeakFootfall']:,} "
            f"at {_hour(row['peakHour'])}; {row['complaints12Months']:,} complaints and "
            f"{row['incidents12Months']:,} incidents in twelve months; "
            f"{row['vacantStorefronts']:,} vacancy filings."
        )
    return "\n\n".join(lines)


NOTICE = (
    "\n\n_Answered without a language model: no valid Anthropic key is "
    "configured, so the question was routed by keyword. The numbers are the "
    "same either way. Add a key to ANTHROPIC_API_KEY for open-ended questions._"
)
