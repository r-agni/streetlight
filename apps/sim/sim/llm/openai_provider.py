"""OpenAI-backed assistant.

Same tools, same system prompt, same map side effects as the Anthropic path.
Only the transport differs, and the differences that matter are small but real:
tool schemas nest under `function`, arguments arrive as a JSON string rather
than a parsed object, and each tool result is its own message instead of one
combined message.

Streaming deltas are forwarded as they arrive so the answer appears while it is
being written, and tool calls are executed the moment the model finishes asking
for them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .assistant import SYSTEM, tool_definitions
from .contracts import ToolFn

DEFAULT_MODEL = "gpt-4.1"

# a tool loop that cannot terminate would spend the user's money in silence
MAX_ROUNDS = 6


def load_key() -> str | None:
    root = Path(__file__).resolve().parents[4]
    env = root / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    return os.environ.get("OPENAI_API_KEY") or None


def as_openai_tools() -> list[dict]:
    """Translate the shared tool schemas into OpenAI's function format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in tool_definitions()
    ]


class OpenAIAssistant:
    """Runs the tool loop against OpenAI and streams back to the browser."""

    def __init__(self, tools: dict[str, ToolFn], model: str = DEFAULT_MODEL):
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
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.key)
        where = json.dumps(context, default=str)[:1200]
        self.history.append(
            {"role": "user", "content": f"{question}\n\n[current view: {where}]"}
        )

        messages = [{"role": "system", "content": SYSTEM}, *self.history]
        tools = as_openai_tools()

        for _ in range(MAX_ROUNDS):
            calls: dict[int, dict] = {}
            text_parts: list[str] = []

            stream = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                stream=True,
                max_tokens=2000,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    text_parts.append(delta.content)
                    await emit({"type": "assistantDelta", "text": delta.content})
                # tool calls arrive in fragments and must be reassembled by index
                for piece in delta.tool_calls or []:
                    slot = calls.setdefault(
                        piece.index, {"id": "", "name": "", "arguments": ""}
                    )
                    if piece.id:
                        slot["id"] = piece.id
                    if piece.function and piece.function.name:
                        slot["name"] = piece.function.name
                    if piece.function and piece.function.arguments:
                        slot["arguments"] += piece.function.arguments

            assistant_message: dict = {
                "role": "assistant",
                "content": "".join(text_parts) or None,
            }
            if calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": call["name"], "arguments": call["arguments"] or "{}"},
                    }
                    for call in calls.values()
                ]
            messages.append(assistant_message)
            self.history.append(assistant_message)

            if not calls:
                await emit({"type": "assistantDelta", "text": "", "done": True})
                return

            for call in calls.values():
                name = call["name"]
                try:
                    parsed = json.loads(call["arguments"] or "{}")
                except json.JSONDecodeError:
                    parsed = {}
                await emit(
                    {"type": "assistantTool", "name": name, "status": "start", "input": parsed}
                )
                fn = self.tools.get(name)
                if fn is None:
                    payload = json.dumps({"error": f"no tool named {name}"})
                    await emit({"type": "assistantTool", "name": name, "status": "error"})
                else:
                    try:
                        # arguments arrive as a JSON string here, never parsed
                        result = fn(**parsed)
                        for action in result.map_actions:
                            await emit({"type": "mapAction", **action})
                        payload = json.dumps(result.payload, default=str)[:24_000]
                        await emit(
                            {
                                "type": "assistantTool",
                                "name": name,
                                "status": "ok",
                                "input": parsed,
                                "summary": result.summary,
                                "sources": [src.to_dict() for src in result.sources],
                            }
                        )
                    except Exception as exc:
                        payload = json.dumps({"error": f"{type(exc).__name__}: {exc}"})
                        await emit(
                            {
                                "type": "assistantTool",
                                "name": name,
                                "status": "error",
                                "summary": str(exc)[:160],
                            }
                        )
                tool_message = {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": payload,
                }
                messages.append(tool_message)
                self.history.append(tool_message)

        await emit({"type": "assistantDelta", "text": "", "done": True})
