# Demo video

`scripts/record_demo.mjs` drives a real browser against the running services
and records the result, so everything on screen is the application answering
real questions. Every figure that appears was computed during the take.

```bash
npm run sim          # simulation service on :8000
npm run dev          # interface on :5173
node scripts/record_demo.mjs --out docs/video
```

Add `--fast` to rehearse the whole run in about a third of the time, which is
how to check the selectors still match after an interface change.

The video is not committed: it is ~86 MB and regenerating it takes one command.

## What the take covers

1. The whole city at commute hour, 45,000 agents on the real street network.
2. Pushing in on downtown, where the dots resolve into people.
3. Street level: pixel characters walking, vehicles, and place signs by category.
4. City data layers switched on one at a time, close enough to read.
5. Clicking a block for its report: footfall by hour, complaints, incidents,
   permits, land use, and the places already there.
6. **Business** — a chai house with a stated budget and customer, answered with
   real vacant addresses and quoted reviews.
7. **Planner** — the Tenderloin: complaints, walkability and what is being
   built, with the assistant switching the matching layers on itself.
8. **City operations** — a sold-out Warriors game: transit surge, departure
   crush and block-level crowding.
9. Time travel back and forward, then back to now.

The clock is re-anchored between chapters. Without that the take drifts five
simulated days ahead of real time, and later chapters carry a date nobody asked
about.
