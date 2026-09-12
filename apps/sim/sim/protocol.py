"""Binary wire format for agent position frames.

Mirrors packages/protocol/src/index.ts. Positions are sent as a struct of
arrays so the browser can upload the coordinate buffer straight to the GPU.
"""
from __future__ import annotations

import struct
from enum import IntEnum

import numpy as np

FRAME_MAGIC = 0x5346  # "SF"
FRAME_VERSION = 2
HEADER_BYTES = 16

FLAG_HAS_IDS = 1 << 0
FLAG_POPULATION_CHANGED = 1 << 1

_HEADER = struct.Struct("<HBBIII")


class AgentState(IntEnum):
    HOME = 0
    DWELL = 1
    TRAVEL = 2
    WAIT_TRANSIT = 3
    HIDDEN = 4


class TravelMode(IntEnum):
    WALK = 0
    BIKE = 1
    TRANSIT = 2
    CAR = 3


def encode_frame(
    tick: int,
    minute: int,
    lon: np.ndarray,
    lat: np.ndarray,
    heading: np.ndarray,
    state: np.ndarray,
    segment: np.ndarray,
    ids: np.ndarray | None = None,
    population_changed: bool = False,
) -> bytes:
    """Pack one agent frame.

    `lon` and `lat` are float32 of length n; `heading`, `state` and `segment`
    are uint8. The segment byte is what lets the browser choose a sprite per
    persona - without it every character on screen is identical, which defeats
    the point of drawing characters at all.

    Passing `ids` marks the frame as full, which the client uses to rebuild its
    agent table after the population changes.
    """
    n = int(lon.shape[0])
    flags = 0
    if ids is not None:
        flags |= FLAG_HAS_IDS
    if population_changed:
        flags |= FLAG_POPULATION_CHANGED

    parts = [_HEADER.pack(FRAME_MAGIC, FRAME_VERSION, flags, tick, minute, n)]
    if ids is not None:
        parts.append(np.ascontiguousarray(ids, dtype=np.uint32).tobytes())

    # interleave into a single lon/lat buffer
    xy = np.empty(n * 2, dtype=np.float32)
    xy[0::2] = lon
    xy[1::2] = lat
    parts.append(xy.tobytes())
    parts.append(np.ascontiguousarray(heading, dtype=np.uint8).tobytes())
    parts.append(np.ascontiguousarray(state, dtype=np.uint8).tobytes())
    parts.append(np.ascontiguousarray(segment, dtype=np.uint8).tobytes())

    body = sum(len(p) for p in parts) - HEADER_BYTES
    pad = (4 - (body % 4)) % 4
    if pad:
        parts.append(b"\x00" * pad)
    return b"".join(parts)


GRID_MAGIC = 0x4744  # "GD"
_GRID_HEADER = struct.Struct("<HBBIII")


def encode_grid_frame(minute: int, indices: np.ndarray, values: np.ndarray) -> bytes:
    """Pack the non-empty cells of the density grid.

    Sending only occupied cells keeps this at a few kilobytes even though the
    grid itself covers the whole city.
    """
    n = int(indices.shape[0])
    parts = [_GRID_HEADER.pack(GRID_MAGIC, FRAME_VERSION, 0, 0, minute, n)]
    parts.append(np.ascontiguousarray(indices, dtype=np.uint32).tobytes())
    parts.append(np.ascontiguousarray(np.minimum(values, 65535), dtype=np.uint16).tobytes())
    body = sum(len(p) for p in parts) - HEADER_BYTES
    pad = (4 - (body % 4)) % 4
    if pad:
        parts.append(bytes(pad))
    return b"".join(parts)
