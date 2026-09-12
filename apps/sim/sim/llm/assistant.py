"""The analyst assistant.

Claude or GPT is given tools over the simulation's own results and over real
data, never over raw tables. That boundary matters: the model decides what to
ask and how to explain it, while every number it quotes is computed by the code
in sim.analysis. It is not asked to estimate footfall, invent a zoning rule, or
produce a coordinate.

Two behaviours are enforced by the prompt rather than by code, because they are
what separates a useful analyst from a search box. The assistant asks before it
assumes when a request is under-specified, and it drives the interface so the
screen ends up showing the evidence for whatever it just said.

Tool side effects are emitted as map actions the moment they run, so the map
reacts while the answer is still being written.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import fallback
from .contracts import ToolFn, ToolResult  # noqa: F401  (re-exported for callers)

SYSTEM = """You are the analyst for a San Francisco city simulation. You work
with three kinds of people: business operators deciding where to open
something, urban planners testing housing and access, and city staff preparing
for events.

HOW TO BEHAVE

Ask before you assume. If a request is under-specified in a way that would
change the answer, ask one to three short, concrete questions and stop. Do not
produce a generic answer to a vague question. Worth asking about: the specific
concept rather than the category (a chai house is not "a cafe"), the budget or
size, who the customer is, which part of the city, and whether they care most
about rent, foot traffic or competition.

Once you have enough, answer properly. Lead with the recommendation. Name
specific streets, blocks and businesses. Quote the numbers you actually
retrieved. Say what would change your mind.

Never give a generic answer. "It depends on foot traffic and competition" is
worthless. If you have not called a tool, you do not know the answer yet.

WHAT YOU MUST NOT DO

- Never invent a number. Every figure comes from a tool call.
- Never state a coordinate you were not given. To point somewhere, use a tool.
- Never blur modelled and observed. Footfall, catchments and agent behaviour
  are model output. Complaints, incidents, permits, vacancy, place listings and
  ratings are recorded data. Say which is which every time.

TOOLS

- get_area_report: what one place is like, in one call.
- find_opportunity: for a specific business concept, where demand outruns the
  supply that already trades there. Use this whenever someone names a concept
  rather than a generic category.
- rank_sites: score real vacant parcels for a category.
- simulate_event: who comes to a large event, from where, and what fills up.
- compare_areas: two to four places side by side.
- control_interface: open a panel, switch data layers on or off, move, zoom,
  rotate or tilt the camera, and start, stop or speed up the clock.
- show_on_map, set_time: smaller versions of the same.

You drive the interface, not just the map. Open the right panel, switch on the
layers that support your point, and move the camera. Do it while answering
rather than asking permission. Leave the screen showing your evidence."""


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
    """Schemas handed to the model. Strict, so inputs never need repair."""
    layer_enum = ["complaints", "incidents", "vacancy", "permits"]
    return [
        {
            "name": "get_area_report",
            "description": (
                "Everything known about one location: modelled footfall by hour, "
                "311 complaints, police incidents, building permits, commercial "
                "vacancy, land use, and the real places nearby with their ratings."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "place": {"type": "string", "description": "Address, corner or neighbourhood."},
                    "radius_metres": {"type": "number", "default": 300},
                },
                "required": ["place"],
                "additionalProperties": False,
            },
        },
        {
            "name": "find_opportunity",
            "description": (
                "For a specific business concept, find where demand outruns the "
                "supply already trading. Searches real listings for what exists, "
                "reads their ratings and review counts as a demand signal, "
                "measures modelled footfall and residents nearby, and ranks "
                "neighbourhoods by the gap. Use whenever someone names a concept "
                "rather than a category, such as 'Indian chai house', 'natural "
                "wine bar' or 'Ethiopian restaurant'."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "concept": {
                        "type": "string",
                        "description": "The concept in the user's own words.",
                    },
                    "search_terms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Two to five phrases to search real listings for, such "
                            "as ['chai', 'indian tea', 'masala chai']. Include close "
                            "substitutes, since those are the real competition."
                        ),
                    },
                    "areas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Neighbourhoods to weigh up. Omit for a citywide sweep.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Closest catalog category, such as cafe or restaurant.",
                    },
                },
                "required": ["concept", "search_terms"],
                "additionalProperties": False,
            },
        },
        {
            "name": "rank_sites",
            "description": (
                "Score and rank real vacant parcels for a category, using modelled "
                "footfall, walking catchment, complementary places and competition."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "near": {"type": "string"},
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
                "surrounding blocks fill, and which businesses sit in the crowd."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "venue": {"type": "string"},
                    "attendance": {"type": "integer", "default": 15000},
                    "start_hour": {"type": "integer", "default": 19},
                    "day": {"type": "string", "default": "Friday"},
                },
                "required": ["venue"],
                "additionalProperties": False,
            },
        },
        {
            "name": "compare_areas",
            "description": "Compare two to four places on footfall, complaints, incidents and mix.",
            "input_schema": {
                "type": "object",
                "properties": {"places": {"type": "array", "items": {"type": "string"}}},
                "required": ["places"],
                "additionalProperties": False,
            },
        },
        {
            "name": "control_interface",
            "description": (
                "Drive the application. Open a panel, switch data layers on or "
                "off, toggle people, places or density, start, stop or speed up "
                "the clock, and move, zoom, rotate or tilt the camera. Use it to "
                "leave the screen showing the evidence for your answer."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["explore", "business", "planner", "events"]},
                    "layers_on": {"type": "array", "items": {"type": "string", "enum": layer_enum}},
                    "layers_off": {"type": "array", "items": {"type": "string", "enum": layer_enum}},
                    "show_places": {"type": "boolean"},
                    "show_people": {"type": "boolean"},
                    "show_density": {"type": "boolean"},
                    "playing": {"type": "boolean"},
                    "speed": {"type": "integer", "description": "Simulated minutes per second, 1-600."},
                    "centre_on": {"type": "string"},
                    "zoom": {"type": "number"},
                    "bearing": {"type": "number", "description": "Rotation in degrees."},
                    "pitch": {"type": "number", "description": "Tilt, 0 to 60 degrees."},
                    "clear_drawing": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "show_on_map",
            "description": "Move the camera, drop labelled markers, or switch on one layer.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "place": {"type": "string"},
                    "zoom": {"type": "number", "default": 15},
                    "markers": {
                        "type": "array",
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
                    "layer": {"type": "string"},
                },
                "required": ["place"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_time",
            "description": "Move the simulation clock, for instance to the evening peak.",
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
    """Runs the tool loop against Claude and streams back to the browser."""

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
        await emit({"type": "assistantTool", "name": name, "status": "start", "input": arguments})
        fn = self.tools.get(name)
        if fn is None:
            await emit({"type": "assistantDelta", "text": "No tool for that.", "done": True})
            return
        try:
            result = fn(**arguments)
            for action in result.map_actions:
                await emit({"type": "mapAction", **action})
            await emit(
                {
                    "type": "assistantTool",
                    "name": name,
                    "status": "ok",
                    "input": arguments,
                    "summary": result.summary,
                    "sources": [s.to_dict() for s in result.sources],
                }
            )
            text = fallback.render(name, result.payload) + fallback.NOTICE
        except Exception as exc:
            await emit({"type": "assistantTool", "name": name, "status": "error"})
            text = f"That failed: {type(exc).__name__}: {exc}"
        await emit({"type": "assistantDelta", "text": text, "done": True})

    async def _answer_with_model(self, client, question: str, context: dict, emit) -> None:
        where = json.dumps(context, default=str)[:1200]
        self.history.append({"role": "user", "content": f"{question}\n\n[current view: {where}]"})

        definitions = tool_definitions()
        for _ in range(8):  # bounded so a tool loop cannot run away
            text_parts: list[str] = []
            tool_calls: list[dict] = []

            async with client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM,
                        # identical every turn, so it is cached rather than resent
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
                    tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

            self.history.append({"role": "assistant", "content": final.content})

            if not tool_calls:
                await emit({"type": "assistantDelta", "text": "", "done": True})
                return

            results = []
            for call in tool_calls:
                await emit(
                    {
                        "type": "assistantTool",
                        "name": call["name"],
                        "status": "start",
                        "input": call["input"],
                    }
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
                            "input": call["input"],
                            "summary": result.summary,
                            "sources": [s.to_dict() for s in result.sources],
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
                    {"type": "tool_result", "tool_use_id": call["id"], "content": payload}
                )

            # every tool result goes back in one message, which is what keeps
            # the model willing to call tools in parallel next turn
            self.history.append({"role": "user", "content": results})

        await emit({"type": "assistantDelta", "text": "", "done": True})
