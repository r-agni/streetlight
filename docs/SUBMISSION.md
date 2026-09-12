# Streetlight — submission

**Team Name**
Streetlight

**Team Members**
Agni R (solo) — ragni.works@gmail.com · github.com/r-agni

**Track**
What Does Abundance Look Like Here (Community connection and public space)

---

## The Problem: What is broken, and who feels it?

San Francisco decides what happens in public space without knowing who the space
actually reaches.

A block party, a plaza redesign, a Sunday street closure, a night market — these get
approved on the strength of a permit application and a turnout guess. Nobody can say,
before the money is spent, *which* neighbourhoods a location draws from, who is close
enough to walk, who would need two buses, or which doorways get crowded at 7:45pm.

So the same few places keep getting programmed. Somewhere central and already busy
gets the festival, because it is the safe choice, and the argument for anywhere else
has no numbers behind it. The 21,869 registered commercial vacancies and the
150,000 land use parcels in this city are public record; the question of who a place
would serve is not recorded anywhere.

Three specific people feel this:

- **A neighbourhood group** proposing a plaza activation, who cannot show a funder
  that their site reaches 14,000 people on foot while the default downtown site
  reaches mostly commuters who have already left by 6pm.
- **A city ops planner** who needs to know which ring around the doors fills up, and
  when, before they decide where the barriers go.
- **A ground-floor business owner** two blocks from a proposed event, who has no way
  to know whether they are inside the crowd or outside it.

## Who This Is For

Concretely: the person writing an SF Shared Spaces or Sunday Streets application for
a block they live on, and the city staffer who has to compare their proposal against
four others by Friday.

Not urban-planning researchers. Someone who has one block in mind, twenty minutes,
and no GIS training.

## Your Idea

**Streetlight** is a working simulation of a San Francisco day that you can ask
questions in plain English.

45,000 synthetic residents, workers and visitors live out a Tuesday on San
Francisco's real street network — 54,236 walk nodes, 132,128 cached routes,
18.1 million vertices. Nobody draws where they go. Each one has a home, places
they need to be, and a distance-decay preference over 53,059 real businesses from
Overture Maps. Foot traffic *emerges*: a morning peak near 8,800 people moving at
once, an evening peak, a dead night. A full simulated day runs in 3.2 seconds.

On top of that, the part built for this track: **drop an event, a fixture or any
venue anywhere and see who it actually reaches.**

- How many people come, and how many of those are residents versus arriving from
  outside the city
- Where they come from, in distance bands — and drawn on the map as their real home
  locations, so "this reaches the whole west side" is something you can see rather
  than assert
- How they would get there: walk, transit, drive
- Arrival and departure curves in quarter-hour buckets, so the crowd has a shape
- Which rings around the doors fill up, and how crowded each gets
- Which specific businesses sit inside the crowd

Every view also takes natural-language questions. "Who would a night market at 24th
and Mission reach?" calls the same tools the panels do — there is no separate
LLM-flavoured answer path, and no LLM call anywhere in the render loop. Answers label
which figures are modelled and which are recorded from open data, because the two are
not the same kind of claim and the tool should not blur them.

Layered underneath, clickable anywhere: 98,771 311 complaints, 88,850 police
incidents, 21,869 commercial vacancy filings, 73,868 building permits, 150,000 land
use parcels — all San Francisco open data, each on its own colour.

**What it is honest about.** Event attendance is a gravity model over the simulated
population, not a re-run of the simulation with every affected agent re-planning
their day. That is the more faithful method and it is a larger piece of work. The
output says so in the same breath as the number. Footfall is simulation output, not
measurement.

## Why It Matters

If this works, the argument for a public space stops being a vibe and starts being a
number that a neighbourhood group can hold.

Abundance is not more events. It is events in the places that reach people who are
currently reached by nothing. Right now the case for a non-obvious location cannot be
made, so it is not made, and programming concentrates where it already is. A tool that
shows a plaza in the outer Mission reaches 14,000 people within a ten-minute walk —
and shows *whose* ten minutes — moves the default.

It also changes who gets to make the argument. Footfall modelling is currently
something you buy. This runs on open data, on a laptop, in seconds, and answers in
plain English. That is the difference between a consultant's deliverable and something
a neighbourhood group uses on a Tuesday night.

## The Next 90 Days

1. **Replace the gravity model with real re-planning.** Affected agents rebuild their
   day around the event and re-route. This is the single biggest honesty gap in the
   tool and it is a known, scoped piece of work.
2. **Validate against ground truth.** SFMTA automatic passenger counts and available
   pedestrian counts, compared against modelled footfall at the same locations and
   hours. Publish the error. A model nobody has checked is a graphic, not evidence.
3. **Equity as a first-class output.** Right now the tool answers "how many". It
   should answer "who is left out" — which blocks are within a ten-minute walk of
   nothing programmed, ranked, as a standing list.
4. **Put it in front of the three people above.** Sit with someone writing a real
   Shared Spaces application and cut every feature they do not touch.
5. **Deploy it.** It currently runs locally in two processes. It needs to be a URL.

## Your Committed Next Step (two weeks)

Two things, both checkable:

1. **Ship a public URL** with the event simulation and the question box working on
   pre-built San Francisco data — no install, no API key.
2. **Run it with three real users**: one neighbourhood group member, one SF city
   staffer, one ground-floor business owner. Recorded sessions, one page of findings
   published to the repo.

---

## Link

Repository: https://github.com/r-agni/streetlight

Screenshots in [`docs/shots/`](shots/). Runs locally in two processes; setup is in the
README and takes about six minutes of data building.
