"""Types shared by the assistant and its tools.

Kept in its own module because the assistant imports the keyword fallback, the
fallback imports the tools, and the tools need this type: putting it in either
of the other two closes an import cycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolResult:
    """What a tool returns to the model, plus anything it wants drawn."""

    payload: Any
    map_actions: list[dict] = field(default_factory=list)


ToolFn = Callable[..., "ToolResult"]
