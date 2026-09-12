"""Public discussion, read through OpenAI's web search.

Reddit refuses unauthenticated API requests and Facebook has no public search
API, so neither can be read directly. Both are indexed by search engines
though, and OpenAI's Responses API exposes a hosted web search that returns
answers with URL annotations.

That indirection is worth stating plainly, because it changes what the result
is. These are search results summarised by a model, with links, not raw posts
fetched from the platform. The links are kept and surfaced so a reader can go
and check; the summary is labelled as a summary.

Failures here are reported rather than swallowed. "No discussion found" and
"could not look" are different facts for someone deciding where to spend money.
"""
from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CACHE_DIR = ROOT / "data" / "raw" / "websearch"
CACHE_SECONDS = 3600

ENDPOINT = "https://api.openai.com/v1/responses"
MODEL = "gpt-4.1"


def _key() -> str | None:
    env = ROOT / ".env"
    if env.exists():
        for line in io.open(env, encoding="utf-8"):
            if line.startswith("OPENAI_API_KEY="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    return os.environ.get("OPENAI_API_KEY") or None


def _cached(name: str, fetch):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:120]
    path = CACHE_DIR / f"{safe}.json"
    if path.exists() and (time.time() - path.stat().st_mtime) < CACHE_SECONDS:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    data = fetch()
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass
    return data


def search(prompt: str, context_size: str = "medium", timeout: float = 120.0) -> dict:
    """One hosted web search. Returns the summary, its citations and the queries run."""
    key = _key()
    if not key:
        return {
            "available": False,
            "reason": "No OPENAI_API_KEY configured, so web search is unavailable.",
        }

    import httpx

    def fetch() -> dict:
        response = httpx.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "tools": [
                    {"type": "web_search_preview", "search_context_size": context_size}
                ],
                "input": prompt,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    try:
        data = _cached(f"ws_{prompt}", fetch)
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}: {str(exc)[:160]}"}

    if data.get("error"):
        return {"available": False, "reason": str(data["error"])[:200]}

    text_parts: list[str] = []
    citations: list[dict] = []
    queries: list[str] = []

    for item in data.get("output") or []:
        kind = item.get("type")
        if kind == "web_search_call":
            action = item.get("action") or {}
            for q in action.get("queries") or ([action["query"]] if action.get("query") else []):
                queries.append(q)
        elif kind == "message":
            for block in item.get("content") or []:
                if block.get("text"):
                    text_parts.append(block["text"])
                for annotation in block.get("annotations") or []:
                    url = annotation.get("url")
                    if not url:
                        continue
                    citations.append(
                        {
                            "title": (annotation.get("title") or url)[:160],
                            "url": url,
                        }
                    )

    # de-duplicate links while keeping the order the model cited them in
    seen: set[str] = set()
    unique = []
    for citation in citations:
        if citation["url"] not in seen:
            seen.add(citation["url"])
            unique.append(citation)

    summary = "\n".join(text_parts).strip()
    return {
        "available": True,
        "summary": summary,
        "citations": unique,
        "queriesRun": queries,
        "method": (
            "Summarised from web search results by a model, with links, rather "
            "than fetched from the platform directly."
        ),
        "foundSomething": bool(unique) or len(summary) > 180,
    }


def community_sentiment(topic: str, place: str = "San Francisco") -> dict:
    """What people are saying on Reddit and Facebook about a topic in a place."""
    prompt = (
        f"Search Reddit (r/sanfrancisco, r/AskSF, r/bayarea) and Facebook groups "
        f"for what people say about {topic} in {place}. Report only what you "
        f"actually find in the search results.\n\n"
        f"Give: (1) up to four short direct quotes with the subreddit or group "
        f"they came from, (2) what people complain is missing or hard to find, "
        f"(3) which specific businesses get recommended by name, (4) any "
        f"neighbourhood people associate with it.\n\n"
        f"If you find nothing on a platform, say so for that platform rather "
        f"than filling the gap. Do not invent quotes or business names."
    )
    result = check_attribution(search(prompt, context_size="high"))
    result["topic"] = topic
    result["place"] = place
    return result


def local_demand(concept: str, place: str = "San Francisco") -> dict:
    """Press, blog and listicle coverage of a concept, for demand signal."""
    prompt = (
        f"Search for recent articles, blog posts and local press about {concept} "
        f"in {place}. Report only what the search results actually contain.\n\n"
        f"Give: (1) which businesses are named and where they are, (2) whether "
        f"coverage suggests the market is growing, saturated or underserved, "
        f"(3) any neighbourhood repeatedly associated with it, (4) anything "
        f"about openings or closures in the last two years.\n\n"
        f"Name your sources. Do not invent businesses."
    )
    result = check_attribution(search(prompt, context_size="high"))
    result["concept"] = concept
    result["place"] = place
    return result

# --------------------------------------------------------------- attribution

PLATFORM_HOSTS = {
    "reddit": ("reddit.com",),
    "facebook": ("facebook.com", "fb.com"),
    "instagram": ("instagram.com",),
    "yelp": ("yelp.com",),
}


def _hosts(citations: list[dict]) -> set[str]:
    found = set()
    for citation in citations:
        url = (citation.get("url") or "").lower()
        for platform, hosts in PLATFORM_HOSTS.items():
            if any(host in url for host in hosts):
                found.add(platform)
    return found


def check_attribution(result: dict) -> dict:
    """Flag claims about a platform that its own citations do not support.

    The search will happily write "on Reddit, someone said ..." while every
    link it returns points somewhere else. That is worse than finding nothing,
    because it reads as evidence. Where the summary names a platform that none
    of the citations come from, the result is marked unreliable and the reason
    is carried through to the answer.
    """
    if not result.get("available"):
        return result

    summary = (result.get("summary") or "").lower()
    cited = _hosts(result.get("citations") or [])
    claimed = {name for name in PLATFORM_HOSTS if name in summary}
    unsupported = sorted(claimed - cited)

    result["platformsCited"] = sorted(cited)
    result["platformsClaimed"] = sorted(claimed)
    if unsupported:
        result["attributionWarning"] = (
            "The search wrote about "
            + ", ".join(unsupported)
            + " but returned no link from "
            + ("that platform" if len(unsupported) == 1 else "those platforms")
            + ". Treat those passages as unverified: quotes without a matching "
            "link should not be repeated as evidence."
        )
        result["trustworthy"] = False
    else:
        result["trustworthy"] = bool(result.get("citations"))
    return result
