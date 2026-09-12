"""Movement, arrival and frame-encoding tests against a hand-built world.

These use a synthetic three-node world so the expected positions can be worked
out by hand, independently of whatever the data pipeline produced.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sim.engine.sim import Simulation
from sim.engine.world import ROUTE_KEY_STRIDE, World
from sim.protocol import AgentState, encode_frame

WALK_SPEED = 78.0  # metres per simulated minute


def build_world(n_agents: int = 1) -> World:
    """Three nodes on a line, one 200 m route from the first to the third."""
    node_lon = np.array([0.0, 0.001, 0.002], dtype=np.float32)
    node_lat = np.array([0.0, 0.0, 0.0], dtype=np.float32)

    vert_lon = node_lon.copy()
    vert_lat = node_lat.copy()
    vert_cum = np.array([0.0, 100.0, 200.0], dtype=np.float32)
    vert_key = vert_cum.astype(np.float64)  # single route, so route index is 0

    shape = (n_agents, 2)
    sch_cat = np.zeros(shape, np.int16)
    sch_cat[:, 1] = 4  # a cafe: anything other than home
    sch_poi = np.full(shape, -1, np.int32)
    sch_poi[:, 1] = 0
    sch_node = np.zeros(shape, np.int32)
    sch_node[:, 1] = 2
    sch_start = np.zeros(shape, np.int16)
    sch_end = np.full(shape, 1440, np.int16)
    sch_end[:, 0] = 10  # leave home at 00:10
    sch_mode = np.zeros(shape, np.int8)
    sch_route = np.full(shape, -1, np.int32)
    sch_route[:, 1] = 0

    return World(
        node_lon=node_lon,
        node_lat=node_lat,
        route_start=np.array([0], np.int64),
        route_n=np.array([3], np.int32),
        route_len=np.array([200.0], np.float32),
        vert_lon=vert_lon,
        vert_lat=vert_lat,
        vert_cum=vert_cum,
        vert_key=vert_key,
        poi_lon=np.array([0.002], np.float32),
        poi_lat=np.array([0.0], np.float32),
        poi_cat=np.array([4], np.int16),
        poi_node=np.array([2], np.int32),
        poi_name=["Test cafe"],
        poi_attr=np.array([1.0], np.float32),
        poi_rating=np.array([np.nan], np.float32),
        poi_reviews=np.array([-1], np.int32),
        agent_home=np.zeros(n_agents, np.int32),
        agent_work=np.full(n_agents, 2, np.int32),
        agent_arch=np.zeros(n_agents, np.int16),
        agent_segment=np.zeros(n_agents, np.int8),
        agent_weight=np.ones(n_agents, np.float32),
        sch_cat=sch_cat,
        sch_poi=sch_poi,
        sch_node=sch_node,
        sch_start=sch_start,
        sch_end=sch_end,
        sch_mode=sch_mode,
        sch_route=sch_route,
        sch_count=np.full(n_agents, 2, np.int8),
        grid_origin=(-0.001, -0.001),
        grid_step=(0.0005, 0.0005),
        grid_shape=(8, 12),
        categories=pd.DataFrame(
            {"category": ["home"] * 5, "label": ["Home"] * 5}
        ),
        bounds=(-0.001, -0.001, 0.005, 0.003),
        manifest={"mode": "test", "bbox": [-0.001, -0.001, 0.005, 0.003]},
    )


@pytest.fixture()
def sim() -> Simulation:
    s = Simulation(build_world(), seed=1)
    s.jitter[:] = 1.0  # remove pace variation so positions are exact
    return s


def test_starts_at_home(sim: Simulation) -> None:
    assert sim.state[0] == AgentState.HOME
    assert sim.lon[0] == pytest.approx(0.0)


def test_departs_when_the_activity_ends(sim: Simulation) -> None:
    for _ in range(10):
        sim.step()
    assert sim.minute_of_day == 10
    assert sim.state[0] == AgentState.TRAVEL
    assert sim.route[0] == 0


def test_position_matches_distance_travelled(sim: Simulation) -> None:
    # departure and the first minute of walking happen in the same tick
    for _ in range(10):
        sim.step()
    assert sim.progress[0] == pytest.approx(WALK_SPEED)
    # 78 m along a 100 m first segment spanning 0.000 to 0.001 degrees
    assert sim.lon[0] == pytest.approx(0.001 * 0.78, rel=1e-3)


def test_crosses_a_vertex_correctly(sim: Simulation) -> None:
    for _ in range(11):  # 156 m: past the first vertex, inside the second segment
        sim.step()
    assert sim.progress[0] == pytest.approx(2 * WALK_SPEED)
    assert sim.lon[0] == pytest.approx(0.001 + 0.001 * 0.56, rel=1e-3)


def test_arrives_and_dwells(sim: Simulation) -> None:
    for _ in range(12):  # 234 m exceeds the 200 m route
        sim.step()
    assert sim.state[0] == AgentState.DWELL
    assert sim.lon[0] == pytest.approx(0.002)
    assert sim.at_poi[0] == 0
    assert sim.poi_visits.sum() == 1


def test_midnight_resets_the_day(sim: Simulation) -> None:
    for _ in range(20):
        sim.step()
    assert sim.state[0] == AgentState.DWELL
    while sim.minute_of_day != 0:
        sim.step()
    assert sim.state[0] == AgentState.HOME
    assert sim.slot[0] == 0


def test_density_grid_tracks_agents(sim: Simulation) -> None:
    for _ in range(12):
        sim.step()
    assert sim.grid_now.sum() == 1
    assert sim.grid_hour.sum() > 0


def test_scales_to_many_agents() -> None:
    many = Simulation(build_world(5000), seed=7)
    for _ in range(30):
        many.step()
    assert np.count_nonzero(many.state == AgentState.DWELL) == 5000
    assert many.grid_now.sum() == 5000


def test_route_key_is_globally_monotonic() -> None:
    """The search key must never let one route's distances reach the next."""
    world = build_world()
    assert float(world.route_len.max()) < ROUTE_KEY_STRIDE


def test_frame_round_trips_through_numpy(sim: Simulation) -> None:
    for _ in range(10):
        sim.step()
    # persona in the low three bits, travel mode in the next two
    packed = (sim.world.agent_segment.view(np.uint8) & 0x07) | (sim.mode << 3)
    blob = encode_frame(
        sim.tick_count, sim.minute_of_week, sim.lon, sim.lat,
        sim.heading, sim.state, packed,
    )
    assert len(blob) % 4 == 0
    assert int.from_bytes(blob[:2], "little") == 0x5346
    count = int.from_bytes(blob[12:16], "little")
    assert count == sim.n
    xy = np.frombuffer(blob, dtype=np.float32, count=count * 2, offset=16)
    assert xy[0] == pytest.approx(float(sim.lon[0]), rel=1e-6)

    # the packed byte sits after positions, heading and state
    tail = 16 + count * 8 + count * 2
    seg = np.frombuffer(blob, dtype=np.uint8, count=count, offset=tail)
    assert int(seg[0]) & 0x07 == int(sim.world.agent_segment[0])
    assert (int(seg[0]) >> 3) & 0x03 == int(sim.mode[0])


def test_travel_mode_is_reported_while_moving(sim: Simulation) -> None:
    """A walking leg must report the walking mode, and clear it on arrival."""
    for _ in range(10):
        sim.step()
    assert sim.state[0] == AgentState.TRAVEL
    assert sim.mode[0] == 0
    for _ in range(3):
        sim.step()
    assert sim.state[0] == AgentState.DWELL
    assert sim.mode[0] == 0
