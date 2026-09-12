## 0. Scope warning — I was handed a truncated spec

What arrived starts **mid-table inside §9** ("…`erasableSyntaxOnly`…"). Sections 1–8 are absent. Every acceptance criterion in §10 dereferences a section I cannot see: §1.5, §3.1, §3.5, §3.6, §4.3, §4.5, §4.8, §5.1, §5.4, §6.2. So this review covers §9 (reuse inventory), §10 (build order), and — more usefully — the **code already committed at `C:\Users\agni_\Documents\sfModeling`**, which I read and which contradicts the build order in several load-bearing places. Treat the design-system and halftone findings below as inferred from the reference aesthetic, not from spec text I was shown.

---

## What I actually verified (not from memory)

| Claim | Method | Result |
|---|---|---|
| `maplibre-gl` 6.9 | npm registry | **Real.** 6.9.0, published **2026-09-09 — three days ago** |
| `deck.gl` / `@deck.gl/*` 9.4.0 | npm registry | **Real.** 9.4.0 published **2026-09-05 — one week ago** |
| `@vis.gl/react-maplibre` 8.1 | npm registry | Real, 8.1.3 |
| `@napi-rs/canvas@1.0.9` + `-win32-x64-msvc@1.0.9` | npm registry + optionalDependencies of 1.0.9 | **Real**, and the win32 package is a declared optionalDependency — see §5 |
| `vitest 4.1.4` | npm registry | Latest is **5.0.0**; the repo's `apps/web/package.json` already pins `^5.0.0`. Spec is stale against its own repo |
| deck.gl #10700, #10681, #10703, #10688 | GitHub API | **All real, all open.** #10703 was filed **today** (2026-09-12T16:24Z) |
| maplibre-gl-js #8413 | GitHub API | Real, and **closed 2026-09-11** — body confirms the UBO-rebind repro and the restore-previous-binding workaround |
| `layers()` / `namedFlavor("white")` | `node_modules/@protomaps/basemaps@5.7.2/dist/esm/index.d.ts` | Valid: `namedFlavor(name: string): Flavor`, `layers(source, flavor, opts)`, `WHITE` exported |
| `vs:#main-end` injection point | `@luma.gl/shadertools/.../shader-injections.js:81` | Valid (`vs:#decl`, `vs:#main-start`, `vs:#main-end`, `fs:#main-end`) |
| `out vec2 vTextureCoords` writable in IconLayer VS | `@deck.gl/layers/dist/icon-layer/icon-layer-vertex.glsl.js:22` | Confirmed |
| `bufferGroup: 'icon-instance-data'` | `@deck.gl/layers/dist/dist.dev.js:2661+` | Confirmed |
| `alphaCutoff` prop | `icon-layer.js:21` (`default 0.05`) | Confirmed |
| `depthCompare` | `@luma.gl/core/.../parameters.d.ts` | Confirmed |
| `MapLibreOverlay` | `@deck.gl/mapbox/dist/index.d.ts` | **Does not exist.** Only `MapboxOverlay` is exported. §9's reuse table names `MapLibreOverlay`; §10 step 5 names `DeckOverlay`; the header names `MapboxOverlay`. Three names, one class |
| `makeAtlas({mipLevels: 1})` | `icon-manager.js:63, 244` | **`mipLevels` is not a user-facing prop.** It is computed internally as `device.getMipLevelCount(w,h)` — see §4 |

Nothing is hallucinated. The versions are, if anything, *too* current — which is finding #1.

---

## P0 — will break the demo or the #1 priority

### 1. The single biggest risk to the visuals: there is no non-interleaved fallback, on a stack whose newest component is three days old

You are shipping the visual centerpiece on `maplibre-gl` **6.9.0 (3 days old)** + `deck.gl 9.4.0` (7 days old) in **interleaved** mode, against **four open, unfixed interleaved-mode bugs**, one filed the same day as this spec. §10 lists them honestly and then specifies no Plan B beyond "don't press Ctrl+−". If #10688 or #10703 bites during a 5-minute demo, the map and the agents are visibly desynced and there is no recovery.

**Fix:** make `interleaved` a single build-time flag (`VITE_DECK_INTERLEAVED`), and make the app correct in *both* modes from step 5, not step 16. Overlaid mode dodges #10700, #10681, #10688 and #10703 outright — the only thing you lose is `beforeId: LABELS_ANCHOR` label layering, i.e. agents draw over street labels. That is a smaller aesthetic loss than "the demo is broken." Budget 30 minutes in step 5 and add an acceptance line: *both modes render agents on SF streets at z15.* Also keep a `maplibre-gl@6.8.x` lockfile branch; 6.9.0 is three days old and #8413 was closed two days ago, meaning the fix ships in 6.10 and 6.9.0 is the single worst version to pin.

### 2. `frame_at(t)` purity and "emergent foot traffic" are mutually exclusive — and the committed protocol commits to both

§9 adopts `frame_at(t)` "architecture verbatim" so the timeline is scrubbable. The committed `ControlMessage` has `action: 'seek'`. But the product claim is *emergent* behaviour — queueing, crowding, competitor cannibalization. Emergence is path-dependent: `frame_at(t)` cannot be pure unless it replays from t=0, which at 50k agents × 10,080 simulated minutes is not a seek, it's a re-run. For 8 drones on fixed polylines the pattern is free; here it is a contradiction that will surface the first time someone drags the scrubber backwards and the shop queue lengths don't match what they saw going forwards.

**Fix:** split it. Run the day (week) **offline** once into a per-agent keyframe table — `(agent_id, t, x, y, heading, state, segment)` at waypoint granularity, Parquet/npz. `frame_at(t)` then becomes a pure `searchsorted` + lerp over that table: genuinely pure, genuinely scrubbable, ~1 ms for 50k, and deterministic under replay. Scenario edits (rezone, new event) re-run the offline pass in seconds. State this explicitly in §4, because the current wording lets an engineer build a stateful tick loop and only discover the conflict at step 9.

### 3. The committed binary frame carries no `segment` byte — you cannot render persona variety, which *is* the visual product

`packages/protocol/src/index.ts` defines `SEGMENT_LABELS` with the comment *"indexed by the segment byte on each agent"*, `HelloMessage` declares `segments: string[]` and `archetypes`, and `AgentFrame` carries **`positions`, `heading`, `state`, optional `ids` — and nothing else**. There is no segment byte. `Interpolator` derives `kind` from `state` alone: travelling / dwelling / at-home. Three values.

So residents, workers and visitors are visually indistinguishable, and the character `IconLayer` in step 10 has nothing to pick an atlas row from. For a user whose stated #1 priority is animated sprites with character, this is the whole feature missing from the wire.

**Fix (cheap, no size cost):** the `state` enum has 5 values and needs 3 bits. Pack `state | (segment << 3)` into the existing byte — 32 segments, frame stays 10 B/agent. Update `decodeFrame` to split it, `SEGMENT_LABELS` to index it, and make the atlas row = segment, the atlas column = walk-cycle phase. Add an acceptance line to step 10: *at z16, at least four visually distinct character types are on screen simultaneously.*

### 4. Sprite atlas mip bleed: `mipLevels: 1` is not a thing you can pass, and the fix has an ordering constraint step 10 doesn't mention

Step 10 says "`makeAtlas` with `mipLevels: 1`" and verifies "no neighbouring-cell bleed at any zoom." But `icon-manager.js` creates every texture with `mipLevels: device.getMipLevelCount(width, height)` and calls `regenerateMipmaps()`. Passing a URL or an image as `iconAtlas` gives you a full mip chain, and mip level 3 of a 1024×256 atlas with 6 px gutters bleeds adjacent cells guaranteed. The `textureParameters` prop only sets *sampler* params — it does not remove the mip chain.

**Fix:** you must create the Texture yourself: `device.createTexture({ mipLevels: 1, sampler: { minFilter: 'nearest', magFilter: 'nearest', mipmapFilter: undefined, addressModeU: 'clamp-to-edge', addressModeV: 'clamp-to-edge' } })` and pass **that Texture object** as `iconAtlas` (it lands on `_externalTexture` and bypasses the manager's creation path). The `device` only exists after the overlay initializes, so the atlas upload must hang off `onDeviceInitialized` — which §10 already introduces for #10688, so wire both there. Spell this out; "mipLevels: 1" as written is unbuildable.

### 5. Positions are `Float32` **lng/lat**, which quantizes San Francisco to ~1.2 m — and then step 8 asks for `METER_OFFSETS` anyway

Verified in both halves of the committed protocol (`xy = np.empty(n*2, dtype=np.float32)` in `apps/sim/sim/protocol.py`; `new Float32Array(buffer, offset, count*2)` in the TS decoder). Float32 ULP at longitude −122.4 is ≈1.45e-5° ≈ **1.2 m**; at latitude 37.77 it's ≈0.5 m. A walking agent moves ~1.4 m/s, so at 10 Hz its per-frame delta is *smaller than one representable step in x*. The lerp then interpolates between two identical quantized values for several frames and jumps — this is exactly the "steppy, not smooth" failure step 9 is supposed to rule out, baked into the wire format, and it is worst at z16–z17 where the sprites are.

Worse, step 8 specifies `COORDINATE_SYSTEM.METER_OFFSETS` with `coordinateOrigin: SF_ORIGIN` — so the client must convert 50,000 lng/lat pairs to metres every frame, allocate a second 400 KB buffer, and do the work `METER_OFFSETS` exists to avoid.

**Fix:** send **Float32 metre offsets from `SF_ORIGIN`** instead of lng/lat. Same 8 bytes. At ±6,000 m the Float32 ULP is ≈0.0007 m — a 1,700× precision gain — the client uploads the buffer to the GPU untouched, and `SF_ORIGIN` moves into `HelloMessage` next to `bounds`. Do the equirectangular projection once, in numpy, server-side; `hades/realworld/geo.py` already has it.

### 6. `Interpolator` will teleport 50,000 agents across the city, silently

`apps/web/src/ws/interpolator.ts:44` guards the lerp with `if (!prev || prev.count !== n)`. The protocol defines `FLAG_POPULATION_CHANGED` precisely because count is not a safe identity check — one agent despawns and one spawns in the same tick, count is unchanged, every index after the splice shifts by one, and the interpolator smoothly glides each agent to some *other* agent's position over 100 ms. 50,000 straight lines across San Francisco, once, looking like a deliberate effect. Then it settles. Nobody will diagnose that at 2am.

**Fix:** guard on `next.flags & FLAG_POPULATION_CHANGED` and on `next.tick !== prev.tick + 1`, not on count. Additionally, `decodeFrame` should `throw` when `FLAG_POPULATION_CHANGED` is set without `FLAG_HAS_IDS` — the format permits an undecodable frame today. And when ids *are* present, rebuild the index map before the next lerp rather than snapping.

### 7. Heading is passed through unblended — every sprite snaps direction 6–10×/second

`interpolator.ts` returns `heading: next.heading` verbatim. §9 correctly identifies the shortest-path yaw blend as essential ("without the yaw fix every bus and pedestrian spins a full turn… immediately visible") and then the committed interpolator doesn't blend heading at all. At 60 fps with a 10 Hz feed, every vehicle and pedestrian on screen rotates in six discrete jerks per second while its position glides smoothly. That is more visually damaging than positional stepping.

**Fix:** blend on the uint8 ring, into a reusable `Uint8Array`, with wraparound — `const d = ((b - a + 128) & 255) - 128; out[i] = (a + Math.round(d * alpha)) & 255;`. Note that §9's `atan2(sin(b-a), cos(b-a))` formulation assumes radians; applied naively to a 0–255 byte it reintroduces the bug it was imported to fix. Add to step 9's acceptance: *a bus turning from Market onto Van Ness rotates continuously; step the timeline frame by frame and the heading never jumps more than ~3° per rAF.*

---

## P1 — performance and correctness at 50k

### 8. The step 7 bandwidth acceptance number is wrong, and 50k over venue wifi is not credible

Step 7 verifies "~30 KB/tick at 10 Hz for 5k agents (scale-check: **6 B/agent**)." The committed format is **10 B/agent** (Float32 lon + Float32 lat + heading + state), or **14 B/agent** on full frames with ids. So 5k = 50 KB/tick, not 30 KB — an engineer following the spec will "fail" a passing build, or "pass" by shipping a format that doesn't exist.

At 50k: **500 KB/frame, 5 MB/s = 40 Mbit/s sustained**, with a 700 KB full frame on every population change. Step 16 measures fps and never measures bytes. Localhost survives this; a hackathon venue's wifi does not, and neither does 5 MB/s of ArrayBuffer garbage per second on the client.

**Fix:** (a) correct the constant to 10 B/agent and add a byte budget to step 16's acceptance, not just step 7's. (b) At 50k, drop to **Int16 metre offsets at 0.25 m scale** — ±8,191 m covers SF from a centred origin at 0.25 m precision, still better than the Float32-lat/lng you have now, and halves the frame to 6 B/agent (the number the spec already believes). (c) Send position at 10 Hz but heading/state at 2 Hz in a separate frame type. (d) Add an explicit backpressure rule — §9 admits no repo has one — and test the *slow* server, not just the dead one: step 16 disconnects the backend, but the real failure is a Python GC pause queueing three frames so agents teleport on catch-up. Acceptance: *throttle the sim to 2 Hz mid-demo; agents slow down smoothly, they do not stutter-jump.*

### 9. `alpha` is computed from arrival timestamps, so motion speed jitters with the network

`const span = next.at - prev.at` uses wall-clock arrival times. A 40 ms jitter on a 100 ms interval is a 40% frame-to-frame speed error — agents visibly surge and stall even though the lerp itself is correct. The server already sends a monotonic `tick`; the interpolator ignores it.

**Fix:** `span = (next.tick - prev.tick) * tickIntervalMs`, with `tickIntervalMs` from `HelloMessage`, and smooth the local clock offset with an EMA rather than trusting each arrival. Also reconcile the rate: the interpolator docstring says "6 Hz", the header says 5–10 Hz, step 7 verifies 10 Hz, and `ControlMessage` has a `frameHz` action. Pin one number and derive the rest.

### 10. `overlay.setProps` at 60 Hz is the wrong 50k pattern

Step 8 says "binary attributes, `updateTriggers: {}`… drive it from `useAgentLoop` with `overlay.setProps` outside React." deck.gl layers are immutable descriptors; `setProps` at 60 Hz constructs new layer objects and runs a full prop diff sixty times a second across every layer in the stack. It works, but it is the thing that will show up as the "scripting under 2 ms/frame" failure in step 16.

**Fix:** allocate persistent `Buffer` objects once on `onDeviceInitialized`, pass `data: { length: n, attributes: { getPosition: { buffer, size: 2, type: 'float32' } } }`, and each frame call `buffer.write(scratchArray)` followed by `deck.redraw()` — no `setProps`, no layer reconstruction, no diff. Make this the text of step 8, because the current wording actively points at the slower path.

Related: `Interpolator` recomputes `kind` for all 50k agents **inside the rAF loop**, but `kind` only changes when a new snapshot arrives. Move it to frame-arrival; otherwise its `updateTriggers` fire at 60 Hz and re-upload a 50 KB attribute every frame for data that changed 10 times a second.

### 11. Where 50k actually breaks: fill rate, not CPU

The CPU story is fine — 100k float ops per frame in typed arrays is genuinely sub-millisecond. The break is the GPU:

- `parameters: { depthCompare: 'always' }` (step 10) disables early-Z. Every sprite quad is blended, in order, with zero rejection.
- At z16 with 24 px sprites and 50k on-screen agents that is ~29 M blended pixels/frame; at z17 with 64 px sprites it is ~205 M/frame. On the integrated GPU a student laptop probably has, 205 M blended px at 60 Hz is not happening.

Step 16 asserts 55–60 fps at **z15** — where the LOD ramp has most agents as dots — and never tests the zoom level where the sprites, the entire point, are visible.

**Fix:** add an explicit acceptance at **z17 over the Financial District** (the densest thing in the sim), with a stated on-screen agent cap — cull + LOD to e.g. 12,000 visible sprites and let the rest stay dots regardless of zoom. Also specify the demo machine's GPU in §10; "the demo machine" is doing a lot of unexamined work in a spec that promises 50k at 60fps.

### 12. `GridFrame` uses flat row-major raster indices; the stack and `CountersMessage` use H3

`decodeGridFrame` returns *"flat row-major cell indices"* while `CountersMessage` carries `keys: string[]` documented as *"H3 cell index"*, `StatsMessage.topCells` carries H3 strings, and the confirmed stack lists "H3 hex aggregation." Step 13 feeds the halftone footfall layer "from H3 at 1 Hz." Two incompatible spatial aggregations in one protocol, with the halftone layer — the signature visual — wired to whichever one the engineer reads first.

**Fix:** pick H3 and delete the raster path, or keep the raster for the GPU density texture and rename it unambiguously (`DensityRasterFrame`) with a documented cell size, origin and row stride. Do not leave `GridFrame` and `CountersMessage` both undefined-by-implication.

---

## P2 — design system, accessibility, and the halftone

### 13. Contrast failure: `rgba(255,255,255,0.55)` on `#2323E5` is **3.47:1** — fails WCAG AA for body text

Computed: the composite is `#9C9CF3`; relative luminance 0.3734 against the blue card's 0.0722 → 3.47:1. That passes AA for large text (≥24 px, or ≥18.66 px bold) and **fails** the 4.5:1 threshold for everything smaller. In the reference poster, 55% white is used for the second headline *and* for the footer rows *and* the body paragraph is at 55% of headline size. Ported to UI at 13–14 px — panel labels, axis ticks, timeline stamps, the assistant dock — every one of those fails.

For reference, the rest of the palette is fine: `#2323E5` on `#D9D9D9` is 6.09:1; pure white on `#2323E5` is 8.59:1.

**Fix:** two tokens, not one. `--on-blue-muted-display: rgba(255,255,255,0.55)` restricted to ≥24 px, and `--on-blue-muted: rgba(255,255,255,0.72)` (→ **5.03:1**) for everything else. Add a step-14 acceptance: *run axe or a contrast checker over the built page; zero AA failures on text.* Do the same arithmetic for dark mode — step 14 says the agent blue lifts to `#4F4FFF` but no dark-mode token values or ratios are given anywhere I can see.

### 14. The halftone is decorative and geographic at the same time, and that will mislead a planner

Step 13's own acceptance criteria describe two dot fields in the same visual language:

- the **paper grain**, which explicitly *"does not pan with the map"* — screen-fixed, meaningless;
- the **H3 footfall plate**, which does pan — geographic, meaningful;

both blue-ish halftone primitives, both layered over the same grey ground. A planner looking at a dense patch cannot tell whether it is data or texture. Then the data layer is specified to vary **size** *and* **shape** (step 13: "at least three distinct primitive shapes") *and*, per the aesthetic, rotation — with no statement of what shape encodes. In the reference poster, shape and rotation encode *letterforms*. Here they encode nothing, but a reader will assume they do. Dot **area** is also a non-linear perceptual channel: halving the radius quarters the ink, so a linear radius ramp systematically under-reads high density.

That is not a style objection. This product's stated buyers are urban planners and city government reading crowding and vacancy; a density map that is ambiguous about which marks are data is worse than no map.

**Fix, all four:**
1. **Separate the channels by hue and opacity.** Grain: greyscale only, ≤4% opacity, never blue. Data: blue only. One rule, stated once, enforced in review.
2. **One variable per channel.** Radius = density, monotonic, with the ramp defined in `sqrt` space so ink area is linear in people/ha. Shape = *category* (resident / worker / visitor), with its own legend, or shape is constant. Rotation = decorative, therefore constant in the data plate.
3. **Ship a legend.** Actual radii, actual units (people per hectare, at what hour). There is no legend anywhere in §10. A density visualization without units is a mood board.
4. **Keep the letterform halftone for the loading plate and empty states only** — where it is unambiguously typography — which is what step 13 already does well. Just say the two are different systems.

### 15. No accessibility section at all, in an app that is 60 fps of moving sprites

Nothing I can see covers:

- **`prefers-reduced-motion`.** This is a full-screen field of animating characters plus `TripsLayer` trails. That is a textbook vestibular trigger and the browser tells you when to stop. Fix: reduced-motion freezes `spriteTime`, disables trails, and snaps the timeline instead of animating it — one uniform and one boolean, 20 minutes of work.
- **Keyboard operation of the map.** Pan/zoom/select via keyboard, and a tab order that doesn't trap the user inside the canvas.
- **Any non-visual path to the data.** A WebGL canvas is opaque to a screen reader. The minimum credible answer for a data product: the ranked-vacancy list and the KPI tiles are real DOM, and the map is `aria-hidden` with a text summary alongside — not an attempt to make 50,000 canvas agents accessible.
- **Focus-visible on the segmented control, timeline scrubber and drawer**, plus focus return when the site-detail drawer closes. Step 14 checks for a focus ring but not for focus *management*.

### 16. No responsive behaviour below 1440×900, which is the only size step 14 tests

Hackathon demos land on projectors (1280×720, often 16:10 letterboxed) and judges' laptops (1366×768). At 768 px tall, two side panels plus a top bar plus a timeline plus an assistant dock at the §6.2 measurements will leave a map slot of a few hundred pixels. There is no breakpoint story, no panel-collapse rule, no minimum map dimension.

**Fix:** define one breakpoint (`<1280px`: right panel becomes an overlay sheet; `<900px` tall: assistant dock collapses to a launcher button) and add to step 14's acceptance: *at 1280×720 the map is at least 720×480 and nothing overlaps.* Also state the demo display resolution in §10 so the layout is tuned for the screen it will actually run on.

### 17. Undefined states across the board

Step 13 specifies a loading plate and "empty states" without enumerating them. Missing, at minimum: WebSocket reconnecting (backoff is capped at 30 s — what does the UI show at second 25?); sim paused vs sim disconnected vs sim at end-of-week (they look identical if you only show "no motion"); zero results in the vacancy ranking; a scenario still computing; PMTiles 404 (bare grey canvas, indistinguishable from a working map at night); an agent popup for an agent that despawned mid-click. Step 16 checks one of these — backend disconnect — and the status chip it describes is the only state affordance in the whole build order.

### 18. Basemap attribution is not mentioned anywhere, and step 4 strips the map to nothing

OSM (ODbL) and Protomaps both require visible attribution, and step 4's acceptance list — no green parks, no POI icons, no missing-image warnings — reads like a style pass that would delete the attribution control on sight. Step 15's compliance checklist covers Google carefully and Overture/Foursquare/OSM/DataSF not at all.

**Fix:** design the attribution line into the paper aesthetic now (tracked-out caps, muted grey, bottom-right, ~10 px) rather than bolting it on at demo time, and add the non-Google sources to step 15's checklist.

### 19. Step 15's Google quota arithmetic doesn't add up

"Cloud Console daily quota on `places.googleapis.com` set to **200**" against a ledger asserting "`pro` under **5,000**/month". 200 × 30 = 6,000 > 5,000. A daily cap does not enforce a monthly cap, and the two numbers disagree by 20%.

**Fix:** set the daily cap at 160 (≈4,800/month) *and* make the SQLite ledger the hard gate that refuses the call, since the Console cap is per-project and per-SKU and won't distinguish `pro` from `enterprise` for you. Separately: a ranked list of real vacant storefronts built partly from Places data is a derived dataset — the "no Google content on the MapLibre canvas" rule is the right instinct but doesn't cover ranking derived from Google fields. For a non-commercial hackathon project this is a risk-of-embarrassment issue rather than a legal one, but decide it deliberately rather than at the demo.

---

## P3 — spec/repo drift that will waste an afternoon

### 20. §10 describes a repo that isn't the repo

Checked against `C:\Users\agni_\Documents\sfModeling`:

| §10 says | Repo has |
|---|---|
| Copy `eslint.config.js` from `gaia/worldview`, "demonstrably the house config" | `"lint": "oxlint"`, `oxlint@^1.81.0`, **no ESLint** |
| `vitest 4.1.4` | `vitest ^5.0.0` |
| `protomaps-themes-base` (implied by §9's era) | `@protomaps/basemaps@^5.7.2` — different package name, different import |
| `scripts/build-sprites.mjs` | `package.json` runs `scripts/make_sprites.mjs` — **and neither file exists** |
| step 2 PMTiles extract | `"tiles": "powershell -File scripts/make_pmtiles.ps1"` — **file does not exist** |
| `src/map/paperStyle.ts`, `src/map/bootstrap.ts` | `src/map/basemapStyle.ts`, no bootstrap module |
| `MapLibreOverlay` / `DeckOverlay` / `MapboxOverlay` | Only `MapboxOverlay` exists |

Steps 1 and 2 will fail as written on the first try. Reconcile the names before anyone runs the build order, and pick one linter — importing `eslint.config.js` into a repo already on oxlint is a step-1 rabbit hole for zero demo value.

### 21. Windows-specific sprite pipeline risks (the honest answer: fewer than you'd think, but three are real)

`@napi-rs/canvas` is prebuilt N-API — no node-gyp, no MSVC, no Cairo. That is the right choice and it will work. The actual Windows exposures:

1. **`npm i -D @napi-rs/canvas-win32-x64-msvc@1.0.9` (step 6) is wrong.** I confirmed that package is already an `optionalDependency` of `@napi-rs/canvas@1.0.9`; npm resolves it by platform automatically. Adding it as an explicit devDependency puts a win32-only package in `package.json`, so `npm ci` **fails outright** on any teammate's mac and in any Linux CI. If `Cannot find native binding` appears, the cause is `--no-optional`, a `--omit=optional` in CI, or an `npm_config_platform` override — not a missing explicit dep. Fix the diagnosis, delete the dep.
2. **Fonts.** If `build-sprites.mjs` uses `GlobalFonts.registerFromPath`, a bare family name resolves against the Windows font set and silently falls back to a different face on mac/CI — sprites that differ between machines. Register the exact TTF from `node_modules/@fontsource-variable/inter` by path, and assert `GlobalFonts.register()` returned `true`.
3. **Git + binaries.** The PNGs and `atlas.json` are committed (step 6). Without a `.gitattributes` marking `*.png binary`, `core.autocrlf=true` on Windows is a live corruption risk for anything Git guesses as text. Add `.gitattributes` before step 6, not after. Note `.gitignore` currently ignores `apps/web/public/sprites/*.png` — which **contradicts** step 6's "commit the PNGs." Pick one.
4. Step 4's `maplibre/font-maker` on a **variable** Inter font produces one static instance; if the paper style calls for two weights you need two runs with explicit instance names. Not Windows-specific, but it fails the same way on every platform: silently, as a wrong-weight label.

### 22. Smaller things, batched

- `decodeGridFrame` reads `minute` at offset 8 **without validating `GRID_MAGIC` or the version byte** — `frameKind` checks magic separately, so a caller that skips it decodes garbage as a grid. Add the guard inside the decoder.
- `decodeFrame`'s doc says *"views alias the incoming buffer; copy if retained"* — and the interpolator retains `prev` and `next` across frames. Safe only while the Worker hands over a fresh transferred ArrayBuffer each time, which costs 5 MB/s of allocation at 50k. Specify the pooled pattern: two pre-allocated Float32Arrays that the Worker `.set()`s into, with the raw buffer released immediately.
- `Interpolator.ensure()` reallocates all buffers on any count change and discards the previous contents — combined with finding #6, a population change both reallocates *and* snaps. Grow with headroom (`capacity = count * 1.25`) and keep `count` separate from capacity.
- `AgentFrame.minute` is "minute of the simulated **week** (0–10079)" but the poster footer is "time over date" and §10 talks about a day timeline. Define the sim epoch, the timezone (`America/Los_Angeles` — SF crosses a DST boundary, so a "week" is not always 10,080 minutes of wall clock), and whether the scrubber spans a day or a week.
- §9's "adopt verbatim: *there is no LLM call anywhere in the render path*" is the single best line in the spec — but `AssistantDeltaMessage`/`AssistantToolMessage` stream over the **same WebSocket** as the 500 KB binary frames. A slow Anthropic response or a large tool summary now competes with position frames on one connection, and a head-of-line stall shows up as agent stutter. Put the assistant on a second socket or on plain SSE. The invariant is about the *tick*; the wire needs its own.
- §9's Co-Authored-By conflict: correctly flagged, correctly deferred to the user. For what it's worth, my session instructions also mandate the trailer, which means the conflict is live right now — resolve it before the first commit as §9 says.
- Secrets hygiene is currently **fine** and worth locking in: `.gitignore` covers `.env`, `git ls-files` returns nothing matching `.env|.pem|key|credential`, and nothing is committed yet (everything is `??`). But `.gitignore` has no `*.pem` and no `*-key.json` rule — §9 explicitly asks for both and the file doesn't have them. Add them now, while the repo is still empty and it costs nothing.

---

**Sources:** [MapLibre GL JS v6 migration guide](https://maplibre.org/maplibre-gl-js/docs/guides/v5-to-v6-migration-guide/), [maplibre-gl on npm](https://www.npmjs.com/package/maplibre-gl), [MapLibre news](https://maplibre.org/news/). Version and API facts above came from the npm registry API, the GitHub issues API, and direct reads of `C:\Users\agni_\Documents\sfModeling\node_modules\{@deck.gl,@luma.gl,@protomaps}` and `C:\Users\agni_\Documents\sfModeling\{packages\protocol\src\index.ts, apps\sim\sim\protocol.py, apps\web\src\ws\interpolator.ts}`.