# streetlight

A simulated San Francisco day you can ask questions. 45,000 agents on the real street network, to see who a public space actually reaches.

Where people walk is not drawn — it emerges from who they are and where they need to be.

![City view](docs/shots/01-city.png)

## How it works

- **45,000 agents** routed over a 54,236-node walk network with 132,128 cached polylines and 18.1M vertices. A full simulated day runs in 3.2 seconds.
- **53,059 real places** from Overture Maps, reduced to a 25-category catalog that drives destination choice through a distance-decay gravity model.
- **The commute emerges rather than being scripted** — a bimodal morning and evening peak falls out of agent schedules, not from a curve anyone drew.
- **Three audiences, one engine:** businesses ranking vacant parcels by modelled footfall and 10-minute walking catchment; planners clicking any block for land use, permits, 311 reports and police records; city operations dropping a real fixture to see arrival curves and which blocks fill.
- **Natural-language questions** hit the same tools the panels do, and answers state which figures are modelled and which are recorded.
- **Census-backed demographics** so population questions resolve against real data rather than simulation output.

Scores are relative to the candidate set, which the panel says on screen.

## Demo

![Street level](docs/shots/street-loop.gif)

Eight seconds at street level: residents walking real sidewalks, each following a schedule the simulation gave them.

**[Full walkthrough](docs/video/streetlight-demo-720p.mp4)** — 8:40, recorded by driving a real browser against the running services, so every figure on screen was computed during the take. GitHub serves committed video as a download rather than playing it inline (~14 MB).

| The city | The data | The three audiences |
|---|---|---|
| **00:04** Whole city at commute hour | **01:54** City data layers | **03:08** Business: where to sign a lease |
| **00:18** Pushing into downtown | **02:50** Clicking a block | **05:47** Planner: the Tenderloin |
| **00:43** Street level | | **06:48** Operations: a sold-out game |

Longer write-up, setup and recording notes: [docs/README-full.md](docs/README-full.md).
