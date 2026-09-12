"""Types shared by the assistant and its tools.

Kept in its own module because the assistant imports the keyword fallback, the
fallback imports the tools, and the tools need these types: putting them in
either of the other two closes an import cycle.

`Source` exists so an answer can show its working. A number on screen is worth
little unless the reader can see which dataset it came from, how many records
that was, over what period, and whether it was measured or modelled. Tools
therefore declare their sources rather than leaving the model to describe them,
which also means the trail cannot be hallucinated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal

Kind = Literal["recorded", "modelled", "derived", "reference"]


@dataclass
class Source:
    """One dataset or computation an answer leaned on."""

    label: str
    kind: Kind
    detail: str = ""
    count: int | None = None
    window: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None and v != ""}


@dataclass
class ToolResult:
    """What a tool returns to the model, plus what the interface should show."""

    payload: Any
    map_actions: list[dict] = field(default_factory=list)
    #: what this call actually read, for the visible trail
    sources: list[Source] = field(default_factory=list)
    #: one line on what the tool did, in the tool's own words
    summary: str = ""


ToolFn = Callable[..., "ToolResult"]


# ---- source constructors, so wording stays consistent across tools --------


def simulation_source(agents: int, detail: str = "") -> Source:
    return Source(
        label="Agent simulation",
        kind="modelled",
        detail=detail or "Density grid accumulated as the clock runs",
        count=agents,
    )


def places_source(count: int, enriched: int = 0) -> Source:
    detail = "Overture Maps places, reduced to a 25-category catalog"
    if enriched:
        detail += f"; {enriched:,} carry Google ratings"
    return Source(label="Places", kind="reference", detail=detail, count=count)


def open_data_source(label: str, count: int, window: str | None = None) -> Source:
    return Source(
        label=label,
        kind="recorded",
        detail="San Francisco open data (DataSF)",
        count=count,
        window=window,
    )


def network_source(nodes: int, method: str) -> Source:
    return Source(
        label="Street network",
        kind="derived",
        detail=method,
        count=nodes,
    )
