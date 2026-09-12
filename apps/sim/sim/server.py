"""FastAPI service: runs the clock and streams agent frames to the browser.

Frames are pushed into a one-slot mailbox per client. A slow client loses
intermediate frames rather than building a backlog, which keeps the displayed
time close to the simulated time no matter how fast the clock is running.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from pathlib import Path

import numpy as np
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from .engine.sim import MINUTES_PER_DAY, Simulation
from .engine.world import load_world
from .protocol import encode_frame, encode_grid_frame

ROOT = Path(__file__).resolve().parents[3]
SEGMENTS = [
    "Office worker", "Tech commuter", "Student", "Service worker",
    "Remote worker", "Retiree", "Visitor", "Other",
]
ARCHETYPE_LABELS = [
    "Office worker", "Tech commuter", "Student", "Service worker",
    "Remote worker", "Retiree", "Visitor",
]

app = FastAPI(title="SF City Sim", default_response_class=ORJSONResponse)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Hub:
    """Owns the simulation clock and the set of connected clients."""

    def __init__(self) -> None:
        self.world = None
        self.sim: Simulation | None = None
        self.cfg: dict = {}
        self.clients: set[asyncio.Queue] = set()
        self.playing = True
        self.speed = 20.0  # simulated minutes per real second
        self.frame_hz = 6.0
        self.run_id = "run-0"
        self._task: asyncio.Task | None = None
        self._tps = 0.0

    def load(self) -> None:
        self.cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
        self.world = load_world(ROOT)
        self.sim = Simulation(self.world, seed=int(self.cfg.get("seed", 42)))
        self.frame_hz = float(self.cfg["sim"].get("frame_hz", 6))
        # start mid-morning so the first thing anyone sees is a busy city
        self.sim.seek(8 * 60 + 20)
        print(
            f"world: {self.world.n_agents:,} agents, {self.world.n_pois:,} places, "
            f"{len(self.world.route_len):,} routes, grid {self.world.grid_shape}",
            flush=True,
        )

    # ---------------------------------------------------------------- clock
    async def run(self) -> None:
        sim = self.sim
        assert sim is not None
        period = 1.0 / self.frame_hz
        next_at = time.perf_counter()
        carry = 0.0
        last_stats = 0.0
        ticks_since = 0
        window_start = time.perf_counter()

        while True:
            now = time.perf_counter()
            if self.playing:
                carry += self.speed * period
                steps = int(carry)
                carry -= steps
                for _ in range(min(steps, 600)):
                    sim.step()
                ticks_since += steps

            self.broadcast_binary(
                encode_frame(
                    sim.tick_count, sim.minute_of_week,
                    sim.lon, sim.lat, sim.heading, sim.state,
                    # low three bits persona, next two bits travel mode
                    (self.world.agent_segment.view(np.uint8) & 0x07)
                    | (sim.mode << 3),
                )
            )

            nz = np.flatnonzero(sim.grid_now)
            if nz.size:
                self.broadcast_binary(
                    encode_grid_frame(sim.minute_of_week, nz, sim.grid_now[nz])
                )

            if now - last_stats >= 1.0:
                elapsed = max(now - window_start, 1e-6)
                self._tps = ticks_since / elapsed
                ticks_since = 0
                window_start = now
                last_stats = now
                counts = sim.counts()
                self.broadcast_json(
                    {
                        "type": "stats",
                        "minute": sim.minute_of_week,
                        "tick": sim.tick_count,
                        "ticksPerSecond": round(self._tps, 1),
                        "topCells": [
                            {"cell": str(i), "count": c} for i, c in sim.top_cells(8)
                        ],
                        **counts,
                    }
                )

            next_at += period
            await asyncio.sleep(max(0.0, next_at - time.perf_counter()))
            if time.perf_counter() - next_at > 1.0:  # fell far behind; resynchronise
                next_at = time.perf_counter()

    # ------------------------------------------------------------ broadcast
    def _push(self, payload) -> None:
        for q in list(self.clients):
            if q.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(payload)

    def broadcast_binary(self, data: bytes) -> None:
        self._push(data)

    def broadcast_json(self, obj: dict) -> None:
        self._push(obj)

    def hello(self) -> dict:
        sim, world = self.sim, self.world
        cats = world.categories
        return {
            "type": "hello",
            "runId": self.run_id,
            "nAgents": world.n_agents,
            "minute": sim.minute_of_week,
            "speed": self.speed,
            "playing": self.playing,
            "bounds": list(world.bounds),
            "categories": [
                {"id": r.category, "label": r.label} for r in cats.itertuples()
            ],
            "segments": SEGMENTS,
            "archetypes": [
                {"id": i, "label": label} for i, label in enumerate(ARCHETYPE_LABELS)
            ],
            "dataMode": world.manifest.get("mode", "unknown"),
            "grid": {
                "origin": list(world.grid_origin),
                "step": list(world.grid_step),
                "shape": list(world.grid_shape),
            },
        }


hub = Hub()


@app.on_event("startup")
async def _startup() -> None:
    hub.load()
    hub._task = asyncio.create_task(hub.run())


@app.get("/api/manifest")
def manifest() -> dict:
    return {
        **hub.world.manifest,
        "bounds": list(hub.world.bounds),
        "grid": {
            "origin": list(hub.world.grid_origin),
            "step": list(hub.world.grid_step),
            "shape": list(hub.world.grid_shape),
        },
    }


@app.get("/api/pois")
def pois(limit: int = 60000) -> dict:
    """Places as parallel arrays, which is far smaller than a list of objects."""
    w = hub.world
    n = min(limit, w.n_pois)
    order = np.argsort(-w.poi_attr)[:n]
    cats = w.categories["category"].tolist()
    return {
        "count": int(n),
        "lon": w.poi_lon[order].round(6).tolist(),
        "lat": w.poi_lat[order].round(6).tolist(),
        "cat": w.poi_cat[order].tolist(),
        "attr": w.poi_attr[order].round(3).tolist(),
        "name": [w.poi_name[i] for i in order],
        "categories": cats,
    }


@app.get("/api/candidates")
def candidates() -> dict:
    import pandas as pd

    path = ROOT / "data" / "processed" / "candidates.parquet"
    if not path.exists():
        return {"count": 0, "items": []}
    df = pd.read_parquet(path)
    return {"count": len(df), "items": json.loads(df.to_json(orient="records"))}


@app.get("/api/events")
def events() -> dict:
    import pandas as pd

    path = ROOT / "data" / "processed" / "events.parquet"
    if not path.exists():
        return {"count": 0, "items": []}
    df = pd.read_parquet(path)
    return {"count": len(df), "items": json.loads(df.to_json(orient="records"))}


@app.get("/api/agent/{agent_id}")
def agent_detail(agent_id: int) -> dict:
    """Everything the agent card shows: identity plus today's chain."""
    w, sim = hub.world, hub.sim
    if not (0 <= agent_id < w.n_agents):
        return {"error": "out of range"}
    labels = w.categories["label"].tolist()
    chain = []
    for s in range(int(w.sch_count[agent_id])):
        poi = int(w.sch_poi[agent_id, s])
        chain.append(
            {
                "slot": s,
                "category": labels[int(w.sch_cat[agent_id, s])],
                "place": w.poi_name[poi] if poi >= 0 else "Home",
                "start": int(w.sch_start[agent_id, s]),
                "end": int(w.sch_end[agent_id, s]),
                "mode": int(w.sch_mode[agent_id, s]),
            }
        )
    arch = int(w.agent_arch[agent_id])
    return {
        "agentId": agent_id,
        "archetype": ARCHETYPE_LABELS[arch] if arch < len(ARCHETYPE_LABELS) else "Resident",
        "segment": SEGMENTS[int(w.agent_segment[agent_id])],
        "weight": float(w.agent_weight[agent_id]),
        "slot": int(sim.slot[agent_id]),
        "state": int(sim.state[agent_id]),
        "lon": float(sim.lon[agent_id]),
        "lat": float(sim.lat[agent_id]),
        "chain": chain,
    }


@app.post("/api/control")
def control(action: str, value: float | None = None) -> dict:
    """Same controls as the socket, for scripts and screenshot harnesses."""
    handle_client_message({"type": "control", "action": action, "value": value})
    return {
        "playing": hub.playing,
        "speed": hub.speed,
        "minute": hub.sim.minute_of_week,
        "frameHz": hub.frame_hz,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=2)
    hub.clients.add(queue)
    await ws.send_text(json.dumps(hub.hello()))

    async def pump() -> None:
        while True:
            payload = await queue.get()
            if isinstance(payload, (bytes, bytearray)):
                await ws.send_bytes(payload)
            else:
                await ws.send_text(json.dumps(payload))

    pump_task = asyncio.create_task(pump())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            handle_client_message(msg)
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        hub.clients.discard(queue)


def handle_client_message(msg: dict) -> None:
    kind = msg.get("type")
    if kind != "control":
        return
    action = msg.get("action")
    value = msg.get("value")
    if action == "play":
        hub.playing = True
    elif action == "pause":
        hub.playing = False
    elif action == "speed" and value:
        hub.speed = float(np.clip(float(value), 1.0, 600.0))
    elif action == "seek" and value is not None:
        hub.sim.seek(int(value) % (MINUTES_PER_DAY * 7))
    elif action == "frameHz" and value:
        hub.frame_hz = float(np.clip(float(value), 1.0, 30.0))
