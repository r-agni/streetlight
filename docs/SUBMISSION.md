# Streetlight — submission

**Team Name**
Streetlight

**Team Members**
Agni R (solo) — ragni.works@gmail.com · github.com/r-agni

**Track**
What Does Abundance Look Like Here (Community connection and public space)

---

## The Problem: What is broken, and who feels it?

Two people on the same block are guessing about the same crowd, and neither can ask
the other.

**The event organizer** picks a location and an hour, then finds out whether it worked
afterwards. Before the event they cannot say how many people are close enough to walk,
which neighbourhoods the site actually draws from, what time the crowd arrives, or
whether the sidewalk outside the doors holds it. So they book the place that worked
last time. Merchant outreach is a flyer on a door, because there is no list of which
businesses are inside the crowd and which are two blocks outside it.

**The business owner** on that block finds out a street closure is happening from a
notice taped to a pole. Nobody has told them 15,000 people are coming, that the peak
arrival is 6:45pm and not 7:00, or that their door sits in the 150–300m ring where most
of the walk-up traffic passes. So they staff a normal Friday and either lose the day or
lose the crowd. The same problem runs in reverse when a closure hurts them: they have
no number to bring to the organizer or to DPW.

The public record does not help either of them. San Francisco publishes 21,869
commercial vacancy filings, 98,771 311 complaints, 88,850 police incidents and 73,868
permits. None of it answers *who walks past your door at 7pm on a Friday.* That is sold
by consultants, and a corner store cannot buy it.

The result is that programming concentrates where it already is. The organizer returns
to the proven central block; the merchant on a quieter commercial strip never gets the
foot traffic, and has no evidence to argue that they should.

## Who This Is For

Two named users, on the same block, using the same model:

**An event organizer** — the person filing a Sunday Streets, Shared Spaces or block
party application. They have a date, an attendance estimate, and two or three possible
locations. They need to choose between them and tell the merchants what is coming.

**A ground-floor business owner** — a cafe on 24th, a bar on Valencia, a corner store
near the ballpark. They have one location and an event happening near it that they did
not plan. They need to know whether they are in the crowd, when it arrives, and roughly
how many people that means for a place their size.

Not planners, not researchers. Someone with a door on a street, twenty minutes, and no
GIS training.

## Your Idea

**Streetlight** is a working simulation of a San Francisco day you can ask questions in
plain English.

45,000 synthetic residents, workers and visitors live out a day on San Francisco's real
street network — 54,236 walk nodes, 132,128 cached routes, 18.1 million vertices.
Nobody draws where they go. Each has a home, places they need to be, and a
distance-decay preference over 53,059 real businesses from Overture Maps. Foot traffic
*emerges*: a morning peak near 8,800 people moving at once, an evening peak, a dead
night. A full simulated day runs in 3.2 seconds.

Drop an event, a real MLB or NBA fixture, or any venue anywhere — and the two users
above get different answers out of the same run.

**What the organizer gets, per candidate location:**

- Attendance split into residents the model can place and visitors from outside the city
- Where they come from in distance bands, *and drawn on the map as real home locations* —
  so "this site reaches the whole west side" is visible, not asserted
- Walk / transit / drive split, from distance
- Arrival and departure curves in quarter-hour buckets, so the crowd has a shape and a
  peak minute rather than a start time
- Crowding per ring around the doors — people per square metre at 0–150m, 150–300m and
  300–600m, each read in plain words against Fruin pedestrian levels of service: *free
  flowing*, *busy but walkable*, *constrained, slow walking*, *congested, queuing likely*
- The named businesses inside the crowd, which is the merchant outreach list

**What the business owner gets, for their own address:**

- Whether their door is in the crowd at all, and which ring
- Modelled walk-past footfall by hour on an ordinary day, and the peak hour
- Residents within a ten-minute walk of them, over the actual walk network, not a circle
- With an event running: an estimated share of attendees who stop somewhere, broken out
  by category and divided across the places competing for them — so a bar on that block
  sees a per-place number, not a citywide total
- What else trades nearby, and what the block reports to 311 and to police

Both views take natural-language questions. "How many people walk past 24th and Mission
at 7pm?" calls the same tools the panels do — there is no separate LLM-flavoured answer
path, and no LLM call anywhere in the render loop. Answers label which figures are
modelled and which are recorded from open data, because those are not the same kind of
claim.

**What it is honest about.** Event attendance is a gravity model over the simulated
population, not a re-run of the simulation with affected agents re-planning their day.
The per-place customer estimate uses flat capture rates by category — a bar sees about
10% of attendees, a cafe about 4% — which is a planning assumption, not a measurement.
Both are stated next to the number. Footfall is simulation output, not a counter on a
pole.

## Why It Matters

If this works, the merchant and the organizer are looking at the same number before the
event instead of arguing about it afterwards.

For the business owner that number is directly operational: staff up or do not, order
more or do not, open early or do not. A cafe that knows 600 people will pass its door
between 6:15 and 7:00 runs a different Friday than one that finds out at 6:30. And when
an event would genuinely hurt them, they have a figure to bring to the organizer rather
than a complaint.

For the organizer it changes which location wins. Right now the argument for a
non-obvious block cannot be made, so it is not made. A tool that shows a quieter
commercial strip puts the crowd within a ten-minute walk of 14,000 residents — and shows
*whose* ten minutes — makes the case that currently has no evidence behind it.

That is what abundance looks like at street level: not more events, but events on the
blocks currently reached by nothing, with the merchants there told far enough in advance
to capture it.

It also changes who gets to ask. Footfall modelling is something you buy. This runs on
open data, on a laptop, in seconds, and answers in plain English — the difference between
a consultant deliverable and something a corner store uses on a Tuesday night.

## The Next 90 Days

1. **Replace the gravity model with real re-planning.** Affected agents rebuild their
   day around the event and re-route. This is the largest honesty gap in the tool, and a
   scoped piece of work.
2. **Ground the per-place capture rates.** The flat rates by category are the weakest
   number a business owner would rely on. Replace them with rates fitted to observed
   event-day transaction counts from a handful of willing merchants.
3. **Validate footfall against ground truth.** SFMTA automatic passenger counts and
   available pedestrian counts, at the same locations and hours. Publish the error. A
   model nobody has checked is a graphic, not evidence.
4. **A merchant notice the organizer can send.** One address in, one page out: your
   ring, your hours, your expected walk-past. The outreach list already exists in the
   output; the artifact a merchant would actually receive does not.
5. **Deploy it.** It currently runs locally in two processes. It needs to be a URL.

## Your Committed Next Step (two weeks)

Two things, both checkable:

1. **Ship a public URL** with the event simulation and the question box working on
   pre-built San Francisco data — no install, no API key.
2. **Run it with five real users: three ground-floor business owners and two event
   organizers.** Recorded sessions, testing one decision each — "would you staff
   differently because of this?" and "would you move your location because of this?" One
   page of findings published to the repo, including what they did not believe.

---

## Link

Repository: https://github.com/r-agni/streetlight

Screenshots in [`docs/shots/`](shots/). Runs locally in two processes; setup is in the
README and takes about six minutes of data building.
