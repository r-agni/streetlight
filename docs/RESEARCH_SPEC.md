`, `erasableSyntaxOnly`, `moduleResolution: "bundler"`, ES2022) | `<path>` | **verbatim** |
| `eslint.config.js` (ESLint 9 flat, typescript-eslint + `reactHooks.configs.flat.recommended` + `reactRefresh.configs.vite`) | `<path>` | **verbatim** — this exact file is duplicated in `capital`, `hearth`, `physicalAI` and `systemScale-cloud/server/dashboard`, so it demonstrably *is* the house config |
| Tailwind v4 `@theme` token mechanism + the `touch-action: none` map fix + the `pointer-events: none` vignette | `<path>` | **mechanism verbatim**, values replaced by §1.5 |
| `WsManager.ts` — singleton, ref-counted `subscribe/unsubscribe`, exponential backoff capped at 30 s, `onclose` nulled before a deliberate close, token in the first message **body** not the URL | `<path>` | **verbatim**, one line changed: `if (typeof data !== 'string') return` becomes the ArrayBuffer decode path, and set `ws.binaryType = 'arraybuffer'` |
| `CircularBuffer.ts` — 1000-slot O(1) allocation-free ring | `...\dashboard\src\ws\CircularBuffer.ts` | **verbatim** |
| `telemetryStore.ts` — module-level rAF flush coalescing N pushes into one zustand `setState` bumping a `generation` counter | `...\dashboard\src\store\telemetryStore.ts` | **verbatim**, for KPIs/charts only |
| Ref-`Map` marker diffing keyed by id | `...\dashboard\src\components\GpsMap\GpsMap.tsx` | **adapt** for the small overlay layers (vacancy pins, event pins) |
| FastAPI module layout: `bridge/server.py` assembly-only, `bridge/routes/*.py`, `set_publisher()` injected singleton, frozen-dataclass config with module-level singleton overridden by env at the entrypoint only | `<hades repo>\bridge\`, `<hades repo>\hades\config.py` | **structure verbatim** |
| **Drift-corrected tick loop** | `<hades repo>\bridge\server.py` | **verbatim.** Take this one, **not** `HADES\bridge\routes\stream.py`, which regressed to a naive `await asyncio.sleep(delay_s)` — that drifts by the frame-generation time on every tick, which at 10 Hz with 50k agents is not negligible |
| `frame_at(t)` pure-function publisher | `<hades repo>\bridge\sim_publisher.py` | **architecture verbatim.** It is what makes the timeline scrubbable, the replay deterministic and the tests trivial |
| `geo.py` — `haversine_m`, `cumulative_distances`, `bearing_rad`, `decode_polyline`; equirectangular for lat/lng↔metres, spherical for distance and heading | `<hades repo>\hades\realworld\geo.py` | **verbatim.** `cumulative_distances` is exactly the arc-length parameterization for placing an agent at fraction *t* along an SF street segment |
| **Shortest-path yaw blend** `atan2(sin(b-a), cos(b-a))` + `smoothstep` | `<hades repo>\hades\motion.py` | **math only — vectorize it.** Without the yaw fix every bus and pedestrian spins a full turn each time heading crosses 0/360°, which is immediately visible. The surrounding `route_pose` is an O(segments) Python loop per agent per tick: correct for 8 drones, fatal at 50,000. Reimplement as `np.searchsorted` over a precomputed cumulative-distance array |
| rAF interpolation between low-rate WS frames, with the **first-frame snap** and the **sub-metre dead-band** | `<hades repo>\viz\realworld-tempVisualizer\app.js` ~1660–1705, `MOTION_SMOOTH_MS = 220` | **adapt.** The dead-band is the anti-jitter fix that is easy to omit and annoying to diagnose. Apply the same smoothstep once per frame over typed arrays, not per object |
| Procedural canvas texture generation (`grain()`, `sketchLine()`, draw-once-upload-once) | `<path>` | **adapt** into `scripts/build-sprites.mjs` and `src/lib/halftone.ts` |
| `mulberry32` seeded PRNG; `makeToonGradient()` with `NearestFilter` (NearestFilter is what makes it *flat*) | `<path>` | **adapt** — the PRNG is already in §2.1 |
| Easing library (`ease_out_cubic`, `ease_out_quint`, `ease_out_back`, `clamp01`, `EASINGS` registry) | `<path>` | **port to TS** as `src/lib/easing.ts` |
| Imperative high-count-entity lifecycle: collection in a `useRef`, create/destroy in one effect keyed on the map, refill in a second, rich `id` payload for picking | `<path>` | **shape only** — deck.gl replaces the Cesium calls |
| Hoist WebGL/context constants to **module scope** so the map is not recreated per render | `<path>` | **the lesson.** The identical trap exists with `@vis.gl/react-maplibre` + `MapLibreOverlay` |
| Demo fallback: phase counter on `setInterval`, positions via `useMemo` lerp + `sin` jitter | `<path>` | **adapt** so the front end is demoable before the Python engine exists |
| Frozen-dataclass settings gate with an explicit enable flag and a cheap default model | `<hades repo>\hades\realworld\openai_settings.py` | **verbatim**, retargeted at Anthropic |
| Cost pre-flight gate before every generation call | `<path>` | **adapt** — directly useful when persona generation could run away |
| Module-level `STYLE_BLOCK` constant prepended to every prompt | `<path>` | **adapt** for persona generation: one shared constant pins style and schema across N personas |
| The rule *"there is no LLM call anywhere in the render path, and that stays true"* | `<path>` docstring | **adopt verbatim** as the sim-tick invariant |
| CLAUDE.md skeleton (Overview / Repository Structure tree / Quick Commands / Env Vars table / Architecture Decisions / Coding Conventions / Data Flow diagram / External APIs table / Testing / Known Considerations) | `<path>` | **skeleton only.** That file has drifted badly — it documents `FlightLayer.tsx`, `TrafficLayer.tsx`, `CCTVLayer.tsx`, `CCTVPanel.tsx`, `useTraffic.ts` and `data/airports.ts`, none of which still exist. Budget a pass to keep the new one honest |

**Explicitly do not reuse:** `hr-system/web-platform/components/ui/*` (shadcn-shaped but hand-rolled, on React 18 + Tailwind v3 — copying it silently imports the older stack's conventions); `HADES/hades/autonomy/*` (domain does not transfer); `agent-parameter-optimization` and `llmGuidedRLTraining` (RL parameter search, not crowd simulation); any Python WebSocket send path (**every** socket in every repo is `json.dumps` over `send_text` — there is no binary framing, no `send_bytes`, no struct/numpy packing, no backpressure handling and no per-client send queue anywhere, so §4.8 is written from scratch).

**Conventions to match:**

- Docstrings and module comments explain **why**, the rejected alternative, and the known failure mode — never what the code does. This is the most consistent and distinctive thing across the user's best files.
- Section banners inside files: `# --- easing ------------------` / `/* ── palette ── */` / `// ── Public API ──`.
- Every Python module opens `from __future__ import annotations`; config is frozen dataclasses; type hints throughout.
- Inline comments justify one specific line (`// Send token in first message body (not URL) to avoid log/proxy leaks`).
- `uv` for Python (both of the user's most recent Python repos have `uv.lock`; no poetry, no conda, no Pipfile anywhere).
- Tests: `vitest` 4.1.4 + `@testing-library/react` + jsdom on **zustand stores and pure logic only**, mirroring `systemScale-cloud/server/dashboard/src/store/__tests__/`. `pytest` for the Python engine. **No component tests, no Playwright suite** for a hackathon.
- Commits: single-line messages, many small commits, no multi-line bodies.
- Deferred work goes in `<todo file>` with a reason and an unblocking trigger — "nothing 'to do later' lives only in chat."

**One conflict to resolve before the first commit.** `<path>` states, in the user's own words: *"Never include any AI attribution in commit messages — no 'Co-Authored-By: Claude', 'Made-with: Cursor', or any similar trailer from any AI tool."* The current session instructions mandate exactly such a trailer. These are directly opposed; ask which governs this repo rather than guessing, because the wrong choice is visible in every commit.

**Secrets hygiene.** Several scouted repos hold live credentials in tracked-looking locations (`gaia/worldview/.env` and `server/.env` with Google Maps and OpenSky keys; `HADES/.env` plus `hades.pem` and `hades_tmp.pem` in the repo root; an Ecotone Firebase admin SDK JSON). Copy `.env.example` **shapes** only, and confirm `.gitignore` covers `.env`, `*.pem` and `*.json` keys before the first commit.

---

## 10. BUILD ORDER

Sixteen steps. Each has one verification that must pass before the next begins. Do not batch them; the failure modes in this stack are silent and compound.

**1 — Scaffold.**
Copy `vite.config.ts`, the three tsconfigs and `eslint.config.js` from `gaia/worldview`; strip Cesium. `npm i` the pinned versions from the header. Write `src/index.css` (§1.5). Add `@fontsource-variable/inter`.
✅ `npm run build` (`tsc -b && vite build`) exits 0. A page rendering `<div class="u-card-blue">` shows `#2323E5` with white Inter, radius 20, and no shadow.

**2 — PMTiles extract.**
Run the `pmtiles extract` command in §3.1 into `public/sf.pmtiles`. Add `*.pmtiles` to Git LFS or a fetch script.
✅ `pmtiles show public/sf.pmtiles` prints `spec 3 | mvt | z0-15 | clustered: true | gzip`, and the file is ~13.7 MB. Not 151 MB.

**3 — Map bootstrap.**
`src/map/bootstrap.ts` with `setWorkerUrl(workerUrl)` from `?worker&url` and `addProtocol("pmtiles", …)` at module scope. Render a bare `<Map>` with the raw `layers("protomaps", namedFlavor("white"))` style.
✅ Tiles render in `npm run dev` **and** in `npm run build && npm run preview`. The preview check is the whole point of this step — `?url` vs `?worker&url` fails **only** in production builds.

**4 — Paper style.**
Write `src/map/paperStyle.ts` (§3.5). Generate the Inter glyph PBFs with `maplibre/font-maker` into `public/fonts/`.
✅ Water is grey, not blue. No green park polygons. No POI icons. Roads are white channels with a visible hairline keyline at z13, z15 and z17. Neighbourhood names render in tracked-out caps with paper-coloured halos. Zero `missing image` warnings in the console.

**5 — Overlay + both workarounds.**
Add `DeckOverlay` (§3.6) with `interleaved: true`, the UBO guard and `deviceProps: { _reuseDevices: true }`. Add one throwaway `ScatterplotLayer` with `beforeId: LABELS_ANCHOR`.
✅ The dots render **under** the street labels, and the labels do not change size when the layer is toggled. Toggle it five times. Then reload under React 19 StrictMode — no `WebGL context already attached to device`. If labels still break, the UBO guard is not firing; if it crashes on the second mount, `_reuseDevices` is missing.

**6 — Sprite atlas.**
`npm i -D @napi-rs/canvas@1.0.9 @napi-rs/canvas-win32-x64-msvc@1.0.9`. Write and run `scripts/build-sprites.mjs` (§5.4). Commit the PNGs and `atlas.json`.
✅ Script completes in under 1.5 s and writes `people-1024x256.png`, `vehicles-1024x128.png`, `atlas.json`. Open the PNGs: pure white pictograms on transparent, 6 px clear inside every cell edge, bus windows are holes not fills. If you get `Cannot find native binding`, the platform package did not install — §5.1.

**7 — Binary WebSocket, static agents.**
Python: HADES module layout, `frame_at(t)`, the drift-corrected tick loop, `send_bytes` with the §4.8 frame. Start with 5,000 agents standing still at random street nodes. Client: `WsManager` with `binaryType='arraybuffer'` and a Worker decoder into `prev`/`next`.
✅ DevTools Network shows ~30 KB/tick at 10 Hz for 5k agents (scale-check: 6 B/agent). The decoded `next` array's first 10 x/y values land inside the SF bbox when converted back to lng/lat.

**8 — Dots.**
`ScatterplotLayer` with `COORDINATE_SYSTEM.METER_OFFSETS`, `coordinateOrigin: SF_ORIGIN`, binary attributes, `updateTriggers: {}`. Drive it from `useAgentLoop` with `overlay.setProps` outside React.
✅ 5,000 dots appear on real SF streets, not in the ocean and not offset by a block. Add `console.count` inside the React component: it must **not** increment at 60 Hz. Add `map.triggerRepaint()` — without it the layer freezes between map interactions.

**9 — Motion.**
Python moves agents along OSM street segments using the numpy `searchsorted` arc-length sampler; client runs `lerpInto` with double-buffered scratch arrays.
✅ Motion is smooth, not steppy, at 10 Hz server rate. Profile: the lerp is under 0.5 ms for 50k in the Performance panel. Kill the server mid-motion — agents coast to the last target and stop, they do not teleport or NaN.

**10 — Sprites.**
Add `SpriteAnimationExtension` (§4.5), `makeAtlas` with `mipLevels: 1`, and the character `IconLayer`. Set `spriteDirCount: 2`, `alphaCutoff: 0.02`, `parameters: { depthCompare: 'always' }`.
✅ At z15 characters walk with visible leg and head motion, feet on the ground point, no neighbouring-cell bleed at any zoom. Rotate the map 180° — characters still face their direction of travel, they do not walk backwards. Set `spriteTime` to a constant: they freeze mid-stride (proves the animation is the uniform, not an accident).

**11 — LOD crossfade.**
Wire the five zoom ramps from §4.3 plus the GPU cull bounds.
✅ Zooming 12→16 slowly: dots grow, sprites bloom in over them, nothing pops or flickers. Set `spriteCullBounds` to a small box — sprites outside it vanish instantly with no gap in the dot layer, and the frame rate rises. At z16 the Chrome frame timeline shows no scripting spike per frame.

**12 — Vehicles, trails, routes.**
Vehicle `IconLayer` sharing `SPRITE_EXT`, `TripsLayer` trails with the `currentTime` uniform, static `PathLayer` route geometry.
✅ Buses follow street geometry with a fading trail behind them. `PathLayer` never re-uploads (check `updateTriggers` is absent, and that layer update count stays 1 in the deck.gl debug overlay).

**13 — Halftone.**
`src/lib/halftone.ts` plate for the loading screen and empty states; `paper.css` overlay and panel texture; the `HalftoneShapeExtension` footfall layer fed from H3 at 1 Hz.
✅ The loading plate resolves into "SF / CITY / SIM" when you squint or step back two metres. The map grain does **not** pan with the map. The footfall dots sit under the street labels, vary in size with density, and show at least three distinct primitive shapes. Blue UI cards over the map are still exactly `#2323E5` — sample them with the colour picker; if they read `#1B1BB0` a multiply blend leaked in.

**14 — UI shell.**
Top bar, timeline, both panels, popups, charts, assistant dock at the §6.2 measurements. Three view modes behind the segmented control.
✅ At 1440×900 nothing overlaps and the map is visible between the panels. Every interactive element has a visible `--blue` focus ring on Tab. No element has a `box-shadow` except `body::after` (grep the built CSS for `box-shadow` — two hits maximum). Set the OS to dark mode: every token flips, the agent blue lifts to `#4F4FFF`, and nothing becomes unreadable.

**15 — Data + enrichment.**
Load Overture + Foursquare + DataSF + OSM into Store A. Run the quadtree harvest with the SKU ledger. Compute the archetype affinity matrix offline. Wire the site-detail drawer with its Maps Static tile.
✅ The SQLite ledger shows `pro` under 5,000 and `enterprise` under 1,000 for the month, and the Cloud Console daily quota on `places.googleapis.com` is set to 200. Grep the client bundle for the Places key — zero hits. Confirm no Google-sourced field other than `place_id` is written to any table with a lifetime over 30 days. Confirm no Google content renders on the MapLibre canvas.

**16 — Scale and demo hardening.**
Push to 50,000 agents. Record the frame timeline. Add the `useDemoShips`-style synthetic fallback so the front end runs with no backend.
✅ 55–60 fps at z15 with 50k agents on the demo machine, scripting under 2 ms/frame, deck.gl draw calls ≤ 8 (check `deck.gl` debug stats). Disconnect the backend: the UI degrades to the synthetic feed and shows a status chip, it does not white-screen. Then the demo rehearsal: **do not press Ctrl+− during it** — deck.gl #10703 desyncs the interleaved overlay completely on browser page zoom and there is no released fix.

### Known live bugs to watch, with no released fix

- **deck.gl #10700 / maplibre #8413** — interleaved + maplibre-gl 6.9.0 label corruption. Guarded in §3.6; **delete the guard when 6.10.0 lands.**
- **deck.gl #10681** — React 19 StrictMode device-attach race. Guarded by `_reuseDevices`.
- **deck.gl #10703** — total desync on browser page zoom. No workaround; avoid in the demo.
- **deck.gl #10688** — overlay cut off after tiles load, desync when switching map instances or tabs. Mitigation is an `onDeviceInitialized` that re-sets the drawing buffer size.
- **`vs:#main-end` injection** depends on IconLayer's internal shader keeping `vTextureCoords` as a writable VS `out` and `positions` / `instancePositions` in scope. Verified against 9.4 source, but these are internal details with no API stability guarantee — a 9.5 refactor breaks it **silently** (wrong UVs, not a crash). Pin `@deck.gl/*` to exact 9.4.0 and keep step 10's visual check as a smoke test.
- **deck.gl 9.4's `bufferGroup: 'icon-instance-data'`** interleaves several icon attributes into one buffer; how an extension-added `addInstanced` attribute interacts with an existing buffer group is unverified. If the extension attributes behave oddly, give them an explicit separate `bufferGroup`, or fall back to a full `IconLayer` subclass (the SimWrapper pattern) as the escape hatch.
- **Uppercase + heavy letter-spacing** breaks on short street names at tight zooms — `symbol-placement: line` cannot fit tracked text along the geometry and the label drops out entirely. Expect to tune `text-letter-spacing` down or raise `roads_labels_minor`'s minzoom after seeing it on real SF geometry.