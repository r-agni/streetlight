"""The analyst assistant.

Claude is given tools over the simulation's own results and the city's open
data, never over raw tables. That boundary matters: the model decides what to
ask and how to explain it, while every number it quotes is computed by the
code in sim.analysis. It is not asked to estimate footfall, invent a zoning
rule, or produce a coordinate.

Some tools also draw. Their side effects are emitted as map actions as soon as
they run, so the map reacts while the answer is still being written rather
than after it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import fallback
from .contracts import ToolFn, ToolResult  # noqa: F401  (re-exported for callers)

SYSTEM = """You are the analyst for a San Francisco city simulation.

Three kinds of people use it:
- business operators deciding where to open something
- urban planners testing housing, zoning and access
- city staff preparing for events and reading complaints

You have tools over the running simulation and over San Francisco's open data.
Rules you must follow:

- Never invent a number. If you have not called a tool for it, you do not know
  it. Call the tool.
- Never state a coordinate you were not given. To point at somewhere, call
  show_on_map or fly_to.
- Distinguish modelled from observed every time. Footfall, catchments and
  agent behaviour are model output. Complaints, incidents, permits, vacancy
  and place ratings are recorded data.
- When you draw a conclusion, say what would change it.
- Be brief. Lead with the answer. A planner reading this is busy.

When a question is about a place, call get_area_report first: it returns
complaints, incidents, permits, land use and nearby places in one call.
When a question is about where to put a business, call rank_sites.
When a question is about an event, call simulate_event.
Always call show_on_map so the user can see what you are describing."""


def load_key() -> str | None:
    # this module sits two packages deep, so the repository root is four up
    root = Path(__file__).resolve().parents[4]
    env = root / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    return os.environ.get("ANTHROPIC_API_KEY") or None


def tool_definitions() -> list[dict]:
    """Schemas handed to the model. Kept strict so inputs never need repair."""
    return [
        {
            "name": "get_area_report",
            "description": (
                "Everything known about one location: modelled footfall by hour, "
                "311 complaints, police incidents, building permits, commercial "
                "vacancy, land use, and the real places nearby with their ratings. "
                "Use this for any question about what a place is like."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "place": {
                        "type": "string",
                        "description": "Address or landmark, for example '18th and Valencia'.",
                    },
                    "radius_metres": {"type": "number", "default": 300},
                },
                "required": ["place"],
                "additionalProperties": False,
            },
        },
        {
            "name": "rank_sites",
            "description": (
                "Score and rank candidate locations for a kind of business, using "
                "modelled footfall, walking catchment, complementary places nearby "
                "and existing competition. Returns the best sites with a breakdown."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "One of the place categories, e.g. cafe, restaurant, gym, grocery.",
                    },
                    "near": {
                        "type": "string",
                        "description": "Optional neighbourhood or address to search around.",
                    },
                    "limit": {"type": "integer", "default": 6},
                },
                "required": ["category"],
                "additionalProperties": False,
            },
        },
        {
            "name": "simulate_event",
            "description": (
                "Model a large event: who attends, where they come from, how the "
                "surrounding blocks fill up, and which nearby businesses see more "
                "people. Use for concerts, games, festivals and street closures."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "venue": {"type": "string", "description": "Venue name or address."},
                    "attendance": {"type": "integer", "default": 15000},
                    "start_hour": {"type": "integer", "default": 19},
                    "day": {
                        "type": "string",
                        "description": "Day of week, e.g. Friday.",
                        "default": "Friday",
                    },
                },
                "required": ["venue"],
                "additionalProperties": False,
            },
        },
        {
            "name": "compare_areas",
            "description": (
                "Compare two or more neighbourhoods or addresses on modelled "
                "footfall, complaints, incidents and place mix."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "places": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Two to four places to compare.",
                    }
                },
                "required": ["places"],
                "additionalProperties": False,
            },
        },
        {
            "name": "show_on_map",
            "description": (
                "Draw something for the user: move the camera, drop markers, or "
                "outline an area. Call this whenever your answer refers to a place."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "place": {"type": "string", "description": "Where to centre the view."},
                    "zoom": {"type": "number", "default": 15},
                    "markers": {
                        "type": "array",
                        "description": "Optional labelled points to drop.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "lon": {"type": "number"},
                                "lat": {"type": "number"},
                            },
                            "required": ["label", "lon", "lat"],
                            "additionalProperties": False,
                        },
                    },
                    "layer": {
                        "type": "string",
                        "description": "Optional data layer to switch on: complaints, incidents, vacancy, permits.",
                    },
                },
                "required": ["place"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_time",
            "description": "Move the simulation clock, e.g. to look at the evening peak.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "day": {"type": "string", "default": "Tuesday"},
                    "hour": {"type": "integer"},
                    "minute": {"type": "integer", "default": 0},
                },
                "required": ["hour"],
                "additionalProperties": False,
            },
        },
    ]


class Assistant:
    """Runs the tool loop and streams text back to the browser."""

    def __init__(self, tools: dict[str, ToolFn], model: str = "claude-opus-5"):
        self.tools = tools
        self.model = model
        self.key = load_key()
        self.history: list[dict] = []

    @property
    def available(self) -> bool:
        return bool(self.key)

    def reset(self) -> None:
        self.history = []

    async def ask(self, question: str, context: dict, emit) -> None:
        """Answer one question, emitting events as the answer develops.

        `emit` is an async callable taking a dict; it is used for streamed text,
        tool activity and map actions.
        """
        if not self.key:
            await self._answer_without_model(question, emit)
            return

        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self.key)
        try:
            await self._answer_with_model(client, question, context, emit)
        except Exception as exc:
            name = type(exc).__name__
            if "Authentication" in name or "PermissionDenied" in name:
                # a dead key should degrade to the keyword router, not to an error
                self.key = None
                await self._answer_without_model(question, emit)
                return
            raise

    async def _answer_without_model(self, question: str, emit) -> None:
        """Route by keyword and render from templates over the same tools."""
        name, arguments = fallback.route(question)
        await emit({"type": "assistantTool", "name": name, "status": "start"})
        fn = self.tools.get(name)
        if fn is None:
            await emit({"type": "assistantDelta", "text": "No tool for that.", "done": True})
            return
        try:
            result = fn(**arguments)
            for action in result.map_actions:
                await emit({"type": "mapAction", **action})
            await emit({"type": "assistantTool", "name": name, "status": "ok"})
            text = fallback.render(name, result.payload) + fallback.NOTICE
        except Exception as exc:
            await emit({"type": "assistantTool", "name": name, "status": "error"})
            text = f"That failed: {type(exc).__name__}: {exc}"
        await emit({"type": "assistantDelta", "text": text, "done": True})

    async def _answer_with_model(self, client, question: str, context: dict, emit) -> None:
        where = json.dumps(context, default=str)[:1200]
        self.history.append(
            {"role": "user", "content": f"{question}\n\n[current view: {where}]"}
        )

        definitions = tool_definitions()
        for _ in range(6):  # bounded so a tool loop cannot run away
            text_parts: list[str] = []
            tool_calls: list[dict] = []

            async with client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM,
                        # the instructions and schemas are identical on every
                        # turn, so they are cached rather than resent
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=definitions,
                messages=self.history,
            ) as stream:
                async for event in stream.text_stream:
                    text_parts.append(event)
                    await emit({"type": "assistantDelta", "text": event})
                final = await stream.get_final_message()

            for block in final.content:
                if block.type == "tool_use":
                    tool_calls.append(
                        {"id": block.id, "name": block.name, "input": block.input}
                    )

            self.history.append({"role": "assistant", "content": final.content})

            if not tool_calls:
                await emit({"type": "assistantDelta", "text": "", "done": True})
                return

            results = []
            for call in tool_calls:
                await emit(
                    {"type": "assistantTool", "name": call["name"], "status": "start"}
                )
                fn = self.tools.get(call["name"])
                if fn is None:
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call["id"],
                            "content": json.dumps({"error": "no such tool"}),
                        }
                    )
                    continue
                try:
                    result = fn(**call["input"])
                    for action in result.map_actions:
                        await emit({"type": "mapAction", **action})
                    payload = json.dumps(result.payload, default=str)[:24_000]
                    await emit(
                        {
                            "type": "assistantTool",
                            "name": call["name"],
                            "status": "ok",
                        }
                    )
                except Exception as exc:  # a failing tool must not kill the answer
                    payload = json.dumps({"error": f"{type(exc).__name__}: {exc}"})
                    await emit(
                        {
                            "type": "assistantTool",
                            "name": call["name"],
                            "status": "error",
                            "summary": str(exc)[:160],
                        }
                    )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": payload,
                    }
                )

            # every tool result goes back in one message, which is what keeps
            # the model willing to call tools in parallel next turn
            self.history.append({"role": "user", "content": results})

        await emit({"type": "assistantDelta", "text": "", "done": True})
