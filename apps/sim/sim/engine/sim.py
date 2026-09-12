"""The simulation state and its vectorised tick.

One tick advances the clock by one simulated minute. Every agent is updated
with whole-array numpy operations, so cost scales with the population rather
than with any Python-level loop.
"""
from __future__ import annotations

import numpy as np

from ..protocol import AgentState
from .world import ROUTE_KEY_STRIDE, World

MINUTES_PER_DAY = 1440
DAYS_PER_WEEK = 7

# metres travelled per simulated minute, indexed by TravelMode
DEFAULT_SPEEDS = np.array([78.0, 230.0, 430.0, 330.0], dtype=np.float32)


class Simulation:
    """Mutable agent state plus the counters the interface reads."""

    def __init__(self, world: World, seed: int = 42, speeds: np.ndarray | None = None):
        self.world = world
        self.rng = np.random.default_rng(seed)
        self.speeds = DEFAULT_SPEEDS if speeds is None else np.asarray(speeds, np.float32)

        n = world.n_agents
        self.n = n
        self._all = np.arange(n, dtype=np.int32)

        self.state = np.full(n, AgentState.HOME, dtype=np.uint8)
        self.slot = np.zeros(n, dtype=np.int8)
        self.route = np.full(n, -1, dtype=np.int32)
        self.progress = np.zeros(n, dtype=np.float32)
        self.speed = np.zeros(n, dtype=np.float32)
        self.at_poi = np.full(n, -1, dtype=np.int32)
        self.heading = np.zeros(n, dtype=np.uint8)
        # travel mode of the current leg, so the interface can draw a bus
        # rather than a pedestrian for someone who is on one
        self.mode = np.zeros(n, dtype=np.uint8)
        # per-agent pace variation, fixed for the run so replays are stable
        self.jitter = self.rng.uniform(0.86, 1.16, n).astype(np.float32)

        self.lon = world.node_lon[world.agent_home].copy()
        self.lat = world.node_lat[world.agent_home].copy()

        self.tick_count = 0
        self.minute_of_week = 0

        rows, cols = world.grid_shape
        self.grid_cells = rows * cols
        self.grid_now = np.zeros(self.grid_cells, dtype=np.int32)
        self.grid_hour = np.zeros((24, self.grid_cells), dtype=np.int32)
        self.poi_visits = np.zeros((24, max(world.n_pois, 1)), dtype=np.int32)

        self._cos_lat = float(np.cos(np.radians(float(np.mean(world.node_lat)))))
        self._reset_day()

    # ------------------------------------------------------------------ clock
    @property
    def minute_of_day(self) -> int:
        return self.minute_of_week % MINUTES_PER_DAY

    @property
    def day_of_week(self) -> int:
        return (self.minute_of_week // MINUTES_PER_DAY) % DAYS_PER_WEEK

    @property
    def hour(self) -> int:
        return self.minute_of_day // 60

    # ------------------------------------------------------------------ state
    def _reset_day(self) -> None:
        """Return every agent to the start of its daily chain."""
        w = self.world
        self.state[:] = AgentState.HOME
        self.slot[:] = 0
        self.route[:] = -1
        self.progress[:] = 0.0
        self.at_poi[:] = w.sch_poi[self._all, 0]
        node = w.sch_node[self._all, 0]
        self.lon[:] = w.node_lon[node]
        self.lat[:] = w.node_lat[node]

    def _arrive(self, idx: np.ndarray) -> None:
        """Place agents at the node of their current slot and start dwelling."""
        if idx.size == 0:
            return
        w = self.world
        slot = self.slot[idx]
        node = w.sch_node[idx, slot]
        self.lon[idx] = w.node_lon[node]
        self.lat[idx] = w.node_lat[node]
        self.route[idx] = -1
        self.progress[idx] = 0.0
        self.mode[idx] = 0  # standing still is never "by bus"

        poi = w.sch_poi[idx, slot]
        self.at_poi[idx] = poi
        cat = w.sch_cat[idx, slot]
        self.state[idx] = np.where(cat == 0, AgentState.HOME, AgentState.DWELL).astype(np.uint8)

        visiting = poi[poi >= 0]
        if visiting.size:
            counts = np.bincount(visiting, minlength=self.poi_visits.shape[1])
            self.poi_visits[self.hour] += counts.astype(np.int32)

    # ------------------------------------------------------------------- tick
    def step(self) -> None:
        """Advance the simulation by one minute."""
        w = self.world
        self.minute_of_week = (self.minute_of_week + 1) % (MINUTES_PER_DAY * DAYS_PER_WEEK)
        self.tick_count += 1
        minute = self.minute_of_day
        if minute == 0:
            self._reset_day()
            self._update_grid()
            return

        travelling = self.state == AgentState.TRAVEL

        # --- departures: an activity has ended and another one follows -----
        slot = self.slot.astype(np.int32)
        has_next = (slot + 1) < w.sch_count
        ends = w.sch_end[self._all, slot]
        leaving = np.flatnonzero((~travelling) & has_next & (minute >= ends))
        if leaving.size:
            nxt = slot[leaving] + 1
            self.slot[leaving] = nxt.astype(np.int8)
            route = w.sch_route[leaving, nxt]
            self.route[leaving] = route
            self.progress[leaving] = 0.0
            mode = np.clip(w.sch_mode[leaving, nxt], 0, len(self.speeds) - 1)
            self.mode[leaving] = mode.astype(np.uint8)
            self.speed[leaving] = self.speeds[mode] * self.jitter[leaving]
            self.state[leaving] = AgentState.TRAVEL
            # a leg with no route is a move within the same node
            immediate = leaving[route < 0]
            if immediate.size:
                self._arrive(immediate)

        # --- movement -------------------------------------------------------
        moving = np.flatnonzero(self.state == AgentState.TRAVEL)
        if moving.size:
            self.progress[moving] += self.speed[moving]
            rid = self.route[moving]
            remaining = w.route_len[rid] - self.progress[moving]
            arrived = moving[remaining <= 0.0]
            still = moving[remaining > 0.0]
            if still.size:
                self._advance_positions(still)
            self._arrive(arrived)

        self._update_grid()

    def _advance_positions(self, idx: np.ndarray) -> None:
        """Interpolate positions along each agent's route polyline."""
        w = self.world
        rid = self.route[idx]
        progress = self.progress[idx]

        key = rid.astype(np.float64) * ROUTE_KEY_STRIDE + progress
        vi = np.searchsorted(w.vert_key, key, side="right") - 1
        first = w.route_start[rid]
        last = first + w.route_n[rid] - 2
        vi = np.clip(vi, first, last)

        c0 = w.vert_cum[vi]
        c1 = w.vert_cum[vi + 1]
        frac = np.clip((progress - c0) / np.maximum(c1 - c0, 1e-3), 0.0, 1.0)

        lon0, lon1 = w.vert_lon[vi], w.vert_lon[vi + 1]
        lat0, lat1 = w.vert_lat[vi], w.vert_lat[vi + 1]
        dlon = lon1 - lon0
        dlat = lat1 - lat0
        self.lon[idx] = lon0 + dlon * frac
        self.lat[idx] = lat0 + dlat * frac

        angle = np.degrees(np.arctan2(dlat, dlon * self._cos_lat))
        self.heading[idx] = np.mod(angle, 360.0) * (256.0 / 360.0)

    def _update_grid(self) -> None:
        """Rebuild the instantaneous density grid and fold it into the hour."""
        w = self.world
        rows, cols = w.grid_shape
        lon0, lat0 = w.grid_origin
        dlon, dlat = w.grid_step

        gj = ((self.lon - lon0) / dlon).astype(np.int32)
        gi = ((self.lat - lat0) / dlat).astype(np.int32)
        inside = (gi >= 0) & (gi < rows) & (gj >= 0) & (gj < cols)
        flat = gi[inside] * cols + gj[inside]
        self.grid_now = np.bincount(flat, minlength=self.grid_cells).astype(np.int32)
        self.grid_hour[self.hour] += self.grid_now

    # -------------------------------------------------------------- reporting
    def counts(self) -> dict[str, int]:
        moving = int(np.count_nonzero(self.state == AgentState.TRAVEL))
        dwelling = int(np.count_nonzero(self.state == AgentState.DWELL))
        home = int(np.count_nonzero(self.state == AgentState.HOME))
        return {"moving": moving, "dwelling": dwelling, "atHome": home}

    def top_cells(self, k: int = 8) -> list[tuple[int, int]]:
        """Busiest grid cells right now, as (flat index, agent count)."""
        if not self.grid_now.any():
            return []
        k = min(k, int(np.count_nonzero(self.grid_now)))
        idx = np.argpartition(self.grid_now, -k)[-k:]
        idx = idx[np.argsort(-self.grid_now[idx])]
        return [(int(i), int(self.grid_now[i])) for i in idx]

    def seek(self, minute_of_week: int) -> None:
        """Jump to a time by replaying ticks from the start of that day."""
        target = int(minute_of_week) % (MINUTES_PER_DAY * DAYS_PER_WEEK)
        day = target // MINUTES_PER_DAY
        self.minute_of_week = day * MINUTES_PER_DAY
        self._reset_day()
        while self.minute_of_day != target % MINUTES_PER_DAY:
            self.step()
