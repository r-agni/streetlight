"""FastAPI service: runs the clock and streams agent frames to the browser.

Frames are pushed into a one-slot mailbox per client. A slow client loses
intermediate frames rather than building a backlog, which keeps the displayed
time close to the simulated time no matter how fast the clock is running.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from pathlib import Path

import numpy as np
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from .analysis import events as events_mod
from .analysis import insight, layers
from .engine import calendar
from .engine.sim import MINUTES_PER_DAY, Simulation
from .engine.world import load_world
from .llm.assistant import Assistant
from .llm.openai_provider import OpenAIAssistant
from .live import feeds
from .llm.tools import build_tools, geocode
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
        # Twenty crosses a whole day in seventy seconds, which drops the
        # view into the small hours before anyone has finished reading the
        # first panel. Eight is still lively and stays in daylight far longer.
        self.speed = 8.0  # simulated minutes per real second
        self.frame_hz = 6.0
        self.run_id = "run-0"
        self._task: asyncio.Task | None = None
        self._tps = 0.0
        self.assistant: Assistant | None = None
        self.tools: dict = {}
        #: the real moment the clock is currently standing in for
        self.anchor = calendar.live()
        #: the tick count when that anchor was set, so elapsed time is monotonic
        self.anchor_tick = 0

    def load(self) -> None:
        self.cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
        self.world = load_world(ROOT)
        self.sim = Simulation(self.world, seed=int(self.cfg.get("seed", 42)))
        self.frame_hz = float(self.cfg["sim"].get("frame_hz", 6))
        # Start at the actual current time in San Francisco. Opening the app
        # on a Saturday evening should show a Saturday evening, not an
        # arbitrary weekday the session happened to begin on.
        self.anchor = calendar.live()
        self.sim.seek(self.anchor.minute)
        self.anchor_tick = self.sim.tick_count
        self.tools = build_tools(ROOT, self.world, self.sim, self)
        self.assistant = _make_assistant(self.tools)
        print(f"assistant: {type(self.assistant).__name__} "
              f"({'ready' if self.assistant.available else 'no key, keyword routing'})",
              flush=True)
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
                        "clock": self.clock_state(),
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

    def clock_state(self) -> dict:
        """What real moment the simulation minute currently stands for.

        The anchor holds the date; the running clock supplies the time of day.
        Recombining them each tick keeps the label honest while the simulation
        advances, without the engine having to know about dates at all.
        """
        from datetime import timedelta

        # Count elapsed ticks rather than compare minute-of-week positions.
        # Comparing positions walks the date a week backwards the moment the
        # simulation crosses Sunday midnight; ticks are monotonic, so the date
        # only ever moves forward.
        elapsed = max(0, self.sim.tick_count - self.anchor_tick)
        moment = (self.anchor.moment + timedelta(minutes=elapsed)).replace(
            second=0, microsecond=0
        )
        instant = calendar.at(moment)

        # The playhead runs faster than wall time, so classifying the current
        # moment alone would relabel the view "projecting" seconds after
        # pressing play. Playing forward from now is simulating ahead, not time
        # travel, and is described as such.
        horizon = self.anchor.horizon
        instant = calendar.Instant(
            moment=instant.moment, minute=instant.minute, horizon=horizon
        )
        state = {**instant.to_dict(), "describe": calendar.describe(instant)}
        state["elapsedMinutes"] = int(elapsed)
        if horizon == "live" and elapsed > 90:
            hours = elapsed / 60.0
            # Not a projection of a chosen date: the same typical week simply
            # rolling on from now. Calling that "projected" invites the reader
            # to treat it as a forecast of a specific day.
            state["horizon"] = "running"
            state["describe"] = (
                f"Running on from now: {instant.label}, {hours:.1f} hours past "
                "the real clock. This is the modelled week continuing, not a "
                "forecast of that date. Press the live button to return."
            )
        return state

    def set_anchor(self, instant) -> None:
        """Move to a real date and time, past or future."""
        self.anchor = instant
        self.sim.seek(instant.minute)
        self.anchor_tick = self.sim.tick_count

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
            "clock": self.clock_state(),
            "grid": {
                "origin": list(world.grid_origin),
                "step": list(world.grid_step),
                "shape": list(world.grid_shape),
            },
        }


def _read_env(name: str) -> str | None:
    """Read one value from .env, falling back to the process environment."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    return os.environ.get(name) or None


def _make_assistant(tools: dict):
    """Pick a provider. OpenAI is preferred when configured, Claude otherwise.

    Whichever is chosen, a missing or rejected key degrades to keyword routing
    over the same tools rather than to an error.
    """
    provider = (_read_env("LLM_PROVIDER") or "anthropic").lower()
    model = _read_env("LLM_MODEL")
    if provider.startswith("openai"):
        assistant = OpenAIAssistant(tools, model=model or "gpt-4.1")
        if assistant.available:
            return assistant
        print("openai selected but no key found; falling back", flush=True)
    return Assistant(tools, model=model or "claude-opus-5")


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


# ----------------------------------------------------------- data layers


@app.get("/api/layers")
def layer_index() -> dict:
    """Which city data layers are loaded, and what is in them."""
    return {"layers": layers.available(ROOT)}


@app.get("/api/layer/{name}")
def layer_points(name: str, category: str | None = None) -> dict:
    return layers.points(ROOT, name, category)


@app.get("/api/area")
def area(lon: float, lat: float, radius: float = 300.0) -> dict:
    """Everything known about one point: the click-anywhere report."""
    report = layers.area_report(ROOT, lon, lat, radius)
    report["footfall"] = insight.hourly_footfall(hub.world, hub.sim, lon, lat, 150.0)
    report["places"] = insight.nearby_places(hub.world, lon, lat, radius, limit=14)
    report["placeMix"] = insight.category_mix(hub.world, lon, lat, radius)
    return report


@app.get("/api/site")
def site(lon: float, lat: float, category: str = "cafe") -> dict:
    return insight.site_score(ROOT, hub.world, hub.sim, lon, lat, category)


@app.get("/api/sites")
def sites(category: str = "cafe", near: str | None = None, limit: int = 8) -> dict:
    """Rank real registered vacancies for a kind of business."""
    from .llm.tools import _candidate_frame

    candidates = _candidate_frame(ROOT, hub.world, near)
    if candidates.empty:
        return {"category": category, "ranked": [], "note": "no candidate sites loaded"}
    return {
        "category": category,
        "ranked": insight.rank_sites(ROOT, hub.world, hub.sim, category, candidates, limit),
    }


@app.get("/api/catchment")
def catchment(lon: float, lat: float, minutes: float = 10.0) -> dict:
    result = insight.walk_catchment(ROOT, hub.world, lon, lat, minutes)
    return {
        "method": result["method"],
        "minutes": result["minutes"],
        "hull": result["hull"],
        "nodesReached": int(len(result["nodes"])),
    }


@app.get("/api/geocode")
def geocode_place(place: str) -> dict:
    lon, lat, resolved = geocode(place)
    return {"lon": lon, "lat": lat, "resolved": resolved}


@app.get("/api/live-events")
def live_events(days: int = 45) -> dict:
    """Real fixtures and listings coming up, for the events panel to plan against."""
    return feeds.upcoming(days)


@app.post("/api/event")
def event_sim(venue: str, attendance: int = 15000, start_hour: int = 19) -> dict:
    lon, lat, resolved = geocode(venue)
    spec = events_mod.EventSpec(
        lon=lon, lat=lat, name=resolved, attendance=attendance,
        start_minute=start_hour * 60, end_minute=start_hour * 60 + 180,
    )
    return events_mod.simulate(hub.world, hub.sim, spec)


@app.get("/api/clock")
def clock() -> dict:
    """What moment the viewer is looking at, and what that means."""
    return hub.clock_state()


@app.post("/api/clock")
def set_clock(iso: str | None = None, day_offset: int | None = None,
              weekday: str | None = None, hour: int | None = None,
              minute: int = 0) -> dict:
    """Move the clock to a real date and time."""
    if iso is None and day_offset is None and weekday is None and hour is None:
        hub.set_anchor(calendar.live())
    else:
        hub.set_anchor(
            calendar.resolve(iso=iso, day_offset=day_offset, weekday=weekday,
                             hour=hour, minute=minute)
        )
    return hub.clock_state()


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
            if msg.get("type") == "ask":
                asyncio.create_task(_answer(ws, msg))
            else:
                handle_client_message(msg)
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        hub.clients.discard(queue)


async def _answer(ws: WebSocket, msg: dict) -> None:
    """Run one assistant question, streaming everything it produces."""
    if hub.assistant is None:
        return

    async def emit(event: dict) -> None:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            pass  # the client went away mid-answer

    question = str(msg.get("text", ""))
    try:
        await hub.assistant.ask(question, msg.get("context") or {}, emit)
    except Exception as exc:
        name = type(exc).__name__
        if "Authentication" in name or "PermissionDenied" in name:
            # a rejected key should still answer, just without the model
            from .llm import fallback

            tool, arguments = fallback.route(question)
            fn = hub.tools.get(tool)
            if fn is not None:
                try:
                    result = fn(**arguments)
                    for action in result.map_actions:
                        await emit({"type": "mapAction", **action})
                    await emit({"type": "assistantTool", "name": tool, "status": "ok"})
                    await emit({
                        "type": "assistantDelta",
                        "text": fallback.render(tool, result.payload) + fallback.NOTICE,
                        "done": True,
                    })
                    return
                except Exception:
                    pass
        await emit(
            {
                "type": "assistantDelta",
                "text": f"The assistant failed: {type(exc).__name__}: {exc}",
                "done": True,
            }
        )


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
