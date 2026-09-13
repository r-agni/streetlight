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

Playwright writes WebM, which is why the commands below read `.webm` while the
file committed here is `.mp4`: the take was converted after recording and the
WebM was not kept. Two commands turn a fresh recording into what the README
carries, an MP4 that plays once downloaded and a short loop that animates in
the page:

```bash
ffmpeg -i docs/video/streetlight-demo.webm -vf scale=1280:720 \
  -c:v libx264 -preset slow -crf 37 -pix_fmt yuv420p -movflags +faststart -an \
  docs/video/streetlight-demo-720p.mp4

ffmpeg -ss 67 -t 8 -i docs/video/streetlight-demo.webm \
  -vf "fps=10,crop=820:560:400:150,scale=640:437:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" \
  docs/shots/street-loop.gif
```

The 720p cut is about 14 MB and is committed, because a reader should not have
to run anything to see what this is. The full-resolution recording is 90 MB and
is not: `.gitignore` keeps everything in `docs/video/` except the 720p file.
Recording again clears stale WebM takes and leaves that file alone.

CRF 37 is the point where the assistant's text is still readable at 720p. Lower
numbers look better and cost megabytes that every clone pays for.

The loop is a GIF because GitHub documents GIF as rendering everywhere, and a
README that animates for some readers and not others is worse than one that
does not animate at all. Animated WebP is several times smaller and does render
in practice, but it is not on GitHub's supported list.

## What the take covers

Timestamps are from the recording committed as `streetlight-demo-720p.mp4`, read
off the video rather than computed from the script. A fresh take will drift:
chapters 6 to 8 each wait on a live model answer, and those ran between one and
three minutes apiece.

1. **00:04** The whole city at commute hour, 45,000 agents on the real street
   network.
2. **00:18** Pushing in on downtown, where the dots resolve into people.
3. **00:43** Street level: pixel characters walking, vehicles, and place signs
   by category.
4. **01:54** City data layers switched on one at a time, close enough to read.
5. **02:50** Clicking a block on the map and drawing its catchment. The report
   itself, footfall by hour, complaints, incidents, permits, land use and the
   places already there, appears with the panel in the next chapter.
6. **03:08** **Business** — a chai house with a stated budget and customer,
   answered with real vacant addresses and quoted reviews.
7. **05:47** **Planner** — the Tenderloin: complaints, walkability and what is
   being built, with the assistant switching the matching layers on itself.
8. **06:48** **City operations** — a sold-out Warriors game: transit surge,
   departure crush and block-level crowding.
9. **07:39** Time travel back and forward, then back to now.

The clock is re-anchored between chapters. Without that the take drifts five
simulated days ahead of real time, and later chapters carry a date nobody asked
about.
