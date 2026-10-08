# DriveDogs Radar — POC plan

Working document for the proof of concept (owner + Claude only). Status as of 2026-10-07, game 1.61.

## Goal

A lean speed-camera detector for ETS2, learned from Garage-j1's *RADAR-DETECTOR* (workshop 2857542840)
but keeping only the speed-camera part:

1. **Every fining speed camera** (base game + all SCS map DLCs) blinks a red police-style strobe, always on.
2. **No sounds / voice** at all.
3. **Windshield detector** accessory: decoration only without the plugin; with the optional SDK plugin it
   blinks when a camera is ahead.

Out of scope for now: map mods (ProMods etc.), TruckersMP, the other Garage-j1 warnings (toll, rail,
roadworks, accidents, detours, weigh stations).

## How Garage-j1 does it (summary)

- `sound_hookup` / `flare_blink` locators added to **full copies of base models/prefabs** (+ materials,
  ~930 MB) → drifts with every game update, 13 of today's 69 camera models missing, 5 orphans.
- Random road events via a **full replacement** of `def/world/journey_road_event.sii` (stale vs 1.61).
- Windshield radar = cosmetic accessory; **replaces every truck interior model** to add a slot.

Full analysis: brain report `plan/radar-feature-study/reports/2026-10-06-garage-j1-radar-analysis.md`.

## Architecture

```
extracted base game ──► tools/scan_cameras.py ──► data/cameras.json      (69 camera models)
                    └─► tools/extract_camera_db.py ► data/camera_db.csv  (707 placed cameras)
data + src/ ──► tools/build_mod.py ──► output/drivedog_radar_v<ver>.scs  (mod, ~1.8 MB)
radar_core + SDK ──► plugin/build.ps1 ──► output/plugin/ddradar.dll + ddradar/camera_db.csv
```

### Mod (data only)

| Part | How | Why it's lean |
|---|---|---|
| Camera strobe | inject 2 `ddradar.blink` locators per enforced lane into each camera **.pmg** | only the `.pmg` is overridden; base `.pmd/.pmc`/materials reused; geometry bytes untouched |
| Which models | any model whose `.pmg` has a `speedcam.20`/`speedcam.r` hookup (the game's own fine trigger) | exact list, regenerated per game version |
| Strobe placement | `data/placement_overrides.json` (hand) else heuristic: gantry → above each enforced lane at 70 % height; pole/box → top of the head | **unverified in game** except DE gantry |
| Windshield unit | `accessory_addon_data` in slot **`set_lglass`** (exists in every 1.61 truck interior) | no interior overrides |
| Unit indicator | `flare_blink light_type: aux` → blinks only while the truck's aux light state is on | |
| Aux availability | hidden `flare_vehicle light_type: aux` in the unit so the engine sees an aux light | **hypothesis, untested** |

PMG 0x15 layout + injector: `tools/scs_common.py` (locator array + string pool re-emitted at EOF; header
offsets are absolute, so nothing else moves).

### Camera position DB

Sign items sit in sector `.base`/`.aux` files (map format 907). Each camera `sign_model` unit token is
searched and validated against the fixed item header
`u32 type=36 | u64 uid | f32 kdop_min[5] | f32 kdop_max[5] | u32 flags | u8 view_dist | u64 model`;
the AABB centre = world position (same space as telemetry `truck.world.placement`).
Result 1.61: 707 cameras; Berlin = 30× `speed_camera_ch` (white pole + grey box).

### Plugin (optional, SCS Telemetry SDK)

- `plugin/src/radar_core.hpp` — DB loader, `Detector` (travel direction from position deltas, 350 m alert /
  400 m release, 25° cone, ±30 m height), `AuxController` (rate-limited toggle with telemetry feedback).
  Unit tests: `plugin/tests/test_core.cpp`.
- `plugin/src/plugin.cpp` — telemetry (`truck.world.placement`, `truck.light.aux.front/roof`, frame_start,
  paused) + an input device **"DriveDogs Radar"** with two buttons the user binds once to *front aux* and
  *roof aux* in Options → Controls. Logs `[ddradar] camera ahead: <model> at <d> m` to `game.log.txt`.
- Install: `<game>\bin\win_x64\plugins\ddradar.dll` + `<game>\bin\win_x64\plugins\ddradar\camera_db.csv`.

## Decisions so far

| # | Decision | Date |
|---|---|---|
| D1 | Speed cameras only; strobe on all base + SCS DLC cameras; no sound | 2026-10-06 |
| D2 | Option C: windshield unit decorative, functional only with optional plugin | 2026-10-06 |
| D3 | Strobe = Garage-j1 police pattern `X-X-XXX-----------`, always on | 2026-10-06 |
| D4 | Plugin drives **aux** (user never uses aux; beacon reserved for special transport) | 2026-10-06 |
| D5 | No TruckersMP support | 2026-10-06 |
| D6 | Build from the extracted base game by script; re-run only when the audit flags changes | 2026-10-06 |

## Status

| Item | State |
|---|---|
| Camera scan (69 models) + DB (707) | ✅ done, `data/` |
| Merged mod package | ✅ `output/drivedog_radar_v0.1.0-dev.1.scs`, all 70 patched PMGs verified (geometry identical, original locators kept) |
| Cover image | ✅ `src/cover.jpg` (`tools/generate_cover.py`, shared DriveDogs layout: title centred, version pill top-right - dev.6) |
| Plugin core + unit tests | ✅ `plugin\build.ps1 -Test` passes (707 cameras, 30 Berlin) |
| Plugin DLL (SDK 1.15) | ✅ `output/plugin/ddradar.dll`, zip `output/drivedog_radar_plugin_v<ver>.zip` |
| End-to-end SDK harness | ✅ `plugin\build.ps1 -Harness`: fake game drives through a Berlin camera → aux on 350 m before, off 10 m after |
| In-game test round 1 | Spike 1: tested the wrong model (Berlin = `speed_camera_ch`); Spike 2: unit mounts ✅, aux greyed ❌ |
| In-game test round 2 (dev.1, log `202610072041`) | strobes flash ✅ but **camera meshes invisible** ❌; aux still greyed ❌; plugin detection ✅ (`camera ahead: speed_camera_ch at 293 m`) but input device rejected ❌ |
| In-game test round 3 (dev.2, log `202610072108`) | camera meshes back + strobing ✅; plugin input device registered ✅; unit fitted ✅; aux still greyed ❌ |
| In-game test round 4 (dev.3, log `202610072131`) | **roof aux enabled** by the r_grill TEST part ✅ (switched on); windshield unit shows **no flare at all** ❌ |
| In-game test round 5 (dev.4, log `202610072150`) | **whole hookup file rejected** (`flare_vehicle` has no `fake_interior_offset`) → no strobes, aux greyed ❌ — fixed in dev.5 + build-time lint |
| v0.1.0-dev.6 | cover only (shared DriveDogs layout); mod content identical to dev.5 (not yet playtested), so the dev.5 checklist applies unchanged |
| Fixes in v0.1.0-dev.2 | PMG rebuilt in standard layout (offsets shifted, indices end the file) · `electric_type: aux_light` on the unit · input display names without `( )` (harness now enforces SDK name rules) |

## Test checklist — v0.1.0-dev.1 (one session)

Setup: remove `ddradar_spike1.scs` / `ddradar_spike2.scs` and older `drivedog_radar_v*.scs`; copy
`drivedog_radar_v0.1.0-dev.10.scs` to the mod folder and enable it (needs **Toys DLC** — POC unit body).
Keep Garage-j1 Radar disabled. Re-fit the windshield unit (saves still reference the removed spike part).

**A. Camera strobe** (Berlin is ideal: 30 cameras)
- [ ] Berlin white pole camera (`speed_camera_ch`) strobes red, both directions?
- [ ] Any gantry (DE motorway / NL / FR): strobe visible, roughly on the camera, not floating oddly?
- [ ] Note any camera with a misplaced/absent strobe (country + screenshot) → fix via `placement_overrides.json`.
- [ ] Still fined when speeding? Models look normal (no missing textures)?

**B. Windshield unit + aux** (dev.5 / dev.6)
- [x] r_grill "DriveDogs aux circuit TEST" enables **roof aux** (round 4).
- [ ] Keep it fitted. In the windshield slot try "DriveDogs Radar detector TEST A", B, C, D in turn
      (engine off → on for C). For each: roof aux off / on → flare visible? blinking? (day + night shot)
- [ ] Fit "DriveDogs Radar detector" (windshield left glass slot).
- [ ] F4 → Lights: aux now enabled? (front / roof / both)
- [ ] Bind a key to that aux, toggle → unit blinks red; off → stops.
- [ ] If still greyed: fit any roof-grill with aux lamps → does aux unlock and does the unit blink?

**C. Plugin** (after the toolchain + SDK are available)
- [ ] Unzip `drivedog_radar_plugin_v0.1.0-dev.2.zip` into `<game>\bin\win_x64\` (creates `plugins\ddradar.dll` +
      `plugins\ddradar\camera_db.csv`); accept the "advanced SDK features" notice at game start.
- [ ] `game.log.txt` shows `[ddradar] loaded 707 cameras`, `telemetry ready`, `input device registered`.
- [ ] Options → Controls: bind *front aux* → "DriveDogs Radar / Aux toggle A" (and roof → B).
- [ ] Drive towards a Berlin camera: log `camera ahead`, unit blinks ~350 m before, stops after passing.

Send `game.log.txt` + screenshots.

## Open questions / risks

| # | Question | Resolve by |
|---|---|---|
| Q1 | ~~Does the hidden `flare_vehicle aux` unlock the aux control?~~ No (round 2). Base aux lamps declare `electric_type: aux_light` (only on 27 `r_grill` accessories) → added to our unit; does it unlock from `set_lglass`, and front or roof? | test B (dev.2) |
| Q2 | Does a `flare_blink light_type: aux` follow front, roof or both aux states? | test B |
| Q3 | Strobe heuristic positions on 67 unverified models | test A + overrides |
| Q4 | ~~Aux toggle cycles?~~ SDK docs: aux states 0 off / 1 dimmed / 2 full → toggle cycles; `AuxController` presses until telemetry matches (on = 1 press, off = 2 presses). Harness models this. | resolved |
| Q5 | Map DB coverage: DLC sectors overriding base sectors in the merged extraction — any cameras missing? | test C on DLC maps |
| Q6 | Truck def ids for DLC trucks lacking `accessory/set_lglass` folders (e.g. Scania S 2024e, DAF XF Electric) | map interior ↔ def ids |

### Aux availability (rounds 2-3) and the dev.3 test

The F4 aux (and beacon) controls stay greyed until the engine sees a matching lamp fitted. Not enough:
a `flare_vehicle light_type: aux` in our windshield unit, nor `electric_type: aux_light` on it (even though
`set_lglass` also exists on the exterior cab model). In base data only **roof grills (`r_grill`) with
`electric_type: aux_light`** declare aux lamps; beacon / front-grill lamps have no flag.

dev.3 adds **"DriveDogs aux circuit TEST"** in the `r_grill` slot (same pattern; GPS box body, visible).
Decision tree after the test:

| Result | Next |
|---|---|
| TEST part unlocks **roof aux** and the windshield unit blinks with it | build a near-invisible aux-circuit model → ship it as the plugin companion part (costs the roof-grill slot) |
| TEST part does nothing, but a **real** aux roof grill unlocks it and the unit blinks | aux needs real lamps: either accept real lamps lighting near cameras, or dig into what the engine keys on (model flares vs slot) |
| Even real aux lamps don't make the unit blink | `flare_blink light_type: aux` doesn't follow aux in a cab part → rethink the indicator (e.g. exterior part visible through the windshield) |

Round 4: row 1 half true - the r_grill part unlocks **roof aux**, but the cab flare never appears.
Base *does* put vehicle flares in interior models (beacons, sun visors incl. `flare.vehicle.aux_light` in
`sunshield_10_bc_int`), so it is our flare definition. Base cab-visible flares use the amplified model at
~0.63 x 3 scale and `fake_interior_offset: 1.5`; ours used 0.15 scale, no offset.

dev.4 test matrix (all on the GPS body, roof aux TEST part fitted):

| Variant | Hookup | Tells us |
|---|---|---|
| A | `flare_blink`, aux, amplified + `fake_interior_offset`, faces driver | fixed visuals enough? |
| B | same as A, faces forward (like base interior beacons) | orientation |
| C | `flare_blink`, **electrics** (always on) | does a cab flare render at all |
| D | `flare_vehicle` (steady), aux | does aux drive a cab flare (without blink) |

Beacon is **not** an alternative: same "lamp must be fitted" rule, and the owner uses it for special transport.

### Round 10 (dev.10, local game log 2026-10-09) - lamp material fails; HUD/UI checked

- LED board: `[dx11] Failed to create vertex input layout ... elements=3/4` - the lamp shader needs a 4th
  vertex stream (mask UV) the lightboard mesh lacks → needs a self-authored mesh (Blender).
- HUD (`ui/adviser_tachometer.sii`) icons bind fixed engine IDs: cruise, fuel, blinkers, low/high beam,
  lane assist, engine/parking/trailer brake, retarders, engine, transmission, hazard (1080), beacon (1090),
  diff lock, air pressure, wipers - **no aux**. Dashboard UI IDs: no free on/off state either.
- Options put to the owner: (1) **plugin overlay** - click-through top-most window with a blinking radar icon
  driven by the plugin's detection (needs borderless fullscreen; drops aux, roof-grill part and cab unit);
  (2) restyle the HUD beacon icon (needs a beacon, conflicts with special transport); (3) own LED mesh with
  lamp material; (4) strobes only. Recommended: (1). Owner's game: exclusive fullscreen, 2560x1080.

### Round 9 (dev.9, log `202610082251`) + dev.10 - lamp material instead of flares

- Visor TEST A (always on): LEDs **visible from outside (cam 2) only**, not from the cab.
- Owner tip: the Scania centre-windshield lightboard (`frntglss_mid`) glows inside **and** outside (follows
  parking lights). Base lightboards have **no flares** - one `eut2.light.tex` material. Materials render in
  the cab; flares in cab models do not (in gameplay).
- SCS Blender Tools lamp mask: vehicle lamps = UV tile x by side, RGBA by lamp type; **aux parts**
  (`electric_type: aux_light`): UV tile x 0 = white / 1 = orange, **R = dim, G = bright**.
- dev.10 TEST: "DriveDogs Radar LED board TEST" (Scania S `frntglss_mid`) = Griffin lightboard copy whose
  light material path is patched (same length) to our `eut2.lamp.add.env` material (base = mask = the
  board's LED texture), `electric_type: aux_light`. Expect: glows with roof aux, inside and out.

### dev.9 - radar sun visor POC (owner chose option 1, 2026-10-08; Scania S first)

- Owner always uses a sun visor; modded-visor support is a later topic. POC = copy of the Scania S
  **stock** visor (`sunshld`, exterior slot) with 2 aux-blink LEDs (`flare.vehicle.ddr_blink`) on the front
  lower edge (x = ±0.45): facing the driver in the interior model, forward in the exterior model, plus the
  hidden aux emitter; `electric_type: aux_light`; stock `suitable_for` / `conflict_with` copied.
- "DriveDogs Radar sun visor" (aux) + "… TEST A" (always on with the engine). Windshield unit stays for now.
- Test: fit TEST A → LEDs visible from cab (cam 1) and front (cam 2) with the engine running? Then the main
  visor: does it unlock roof aux by itself (remove the r_grill TEST part)? aux on → LEDs blink? Then plugin.

### Round 8 (dev.8, log `202610082229`) - interior-slot flares are not drawn in gameplay

- TEST A (always on, faces driver, no offset, bigger) and TEST B (aux, driver + glass flares) both fitted:
  **dark in gameplay** (cab and exterior), blinking only in the pause-menu showroom.
- Conclusion: the engine does not draw flare sprites of parts in interior slots (`set_lglass`) during
  gameplay. Base agrees: interior-slot parts only use light-only flares (`intlight_bck/bgr`) or luminous
  materials (steering wheels: `dif.lum…` + `electric_type: vehicle_interior`).
- Options (owner to choose): (1) **sun-visor indicator** - `sunshld` is an exterior slot whose interior
  model may carry aux flares visible from the cab (base: Renault Premium `sunshield_10_bc_int` has
  `flare.vehicle.aux_light`), and it is an aux-lamp slot; costs the sun-visor slot. (2) emissive lamp
  material (mask texture driven by aux) on the windshield unit - more work, unproven in interior slots.
  (3) no in-cab indicator.

### Round 7 (dev.7, log `202610082214`) - flares render!

- With `flare.vehicle.*` names the unit's flare **blinks** - seen in the pause-menu garage (variant B, aux,
  facing forward) - but not while driving: outside it washes out in daylight (small flare); inside, B faced
  away and C was displaced by `fake_interior_offset: 1.5` (a roof-beacon setting); D is steady by design.
- dev.8: TEST A = always on (electrics), faces driver, no offset, bigger (1.0 x 3) -> cab visibility check;
  TEST B = the unit design: aux blink, one flare towards the driver + one through the glass, no offset,
  bigger. The main "DriveDogs Radar detector" = B. C/D removed.

### Lesson from round 6 (dev.6, logs `202610082137`, `202610082156`)

- All four windshield variants fitted (A-D) and **none showed anything - not even C (electrics, always on)**.
  So the problem was not scale, direction, aux or blink: the engine ignored our flare hookups on the truck
  part entirely. Every light hookup on base truck models is named **`flare.vehicle.*`** (452 of 452);
  ours were `ddradar.cab_*`. World models (cameras) accept any name, which is why `ddradar.blink` works.
- dev.7 renames all truck-part flare units to `flare.vehicle.ddr_*` (camera strobe unchanged). Same A-D
  test; all 69 camera models byte-identical to dev.6.

### Lesson from round 5

- **The game drops a whole `.sii` file on the first unknown attribute.** All flare units live in
  `unit/hookup/ddradar.sii`, so one bad attribute disabled every strobe and the aux emitter.
  `tools/lint_units.py` (run by `build_mod.py`, blocks packing) checks every unit attribute against what
  base data uses on that class, plus a small `PROVEN` allowlist.

### Lessons from round 2

- **PMG files must keep the converter layout.** Appending blocks after the index buffer kept every offset
  valid, yet the game dropped the mesh (locators still worked). `Pmg.check_layout()` now guards the
  layout and `with_locators()` shifts offsets instead.
- **SDK input names are validated by the game** — a single bad character rejects the whole device.
- Fallback if `electric_type` does not unlock aux: the F4 menu also has an always-available
  *Dashboard backlight* toggle (no known flare `light_type` for it yet - investigate only if needed).

## Release blockers (not for POC)

- Windshield unit body is a **copy of the Toys DLC GPS model** → needs our own model (Blender + SCS Blender
  Tools), then the Toys DLC dependency goes away.
- Plugin ships SCS SDK-derived code only as compiled DLL; SDK headers stay out of git.
- Audit command: compare a new extracted base with `data/cameras.json` (new / changed camera models).

## Prerequisites on the dev machine

- Python 3 + Pillow; `scs_packer` on `PATH` (already: `D:\Programs\ScsSoftwares\bin`).
- Extracted reference: `<root>/base/<version>` (default 1.61.1.1, `GAME_VERSION` in `tools/scs_common.py`);
  `<root>` comes from this host's `games.ets2.reference_root` (scs-mod-developer profile) - never
  hard-coded. The reference keeps text files on disk; `.pmg` assets are fetched on demand through the
  profile's `megapack` helpers (`ref_path` / `ref_fetch`). `scan_cameras.py` scans only the models of
  `sign_model` units (~8.5k, ~200 MB) - the map can only place cameras through those.
- Visual Studio *Desktop development with C++* (MSVC 14.51 + Windows SDK 10.0.26100) — installed 2026-10-07.
- SCS SDK 1.15 (`https://download.eurotrucksimulator2.com/scs_sdk_1_15.zip`, MIT-style licence) unpacked to
  `plugin/sdk/` (git-ignored); its licence ships with the plugin.

## Commands

```bash
python tools/scan_cameras.py          # data/cameras.json
python tools/extract_camera_db.py     # data/camera_db.csv
python tools/generate_cover.py        # src/cover.jpg (reads VERSION)
python tools/build_mod.py --version "$(cat VERSION)"   # runs tools/lint_units.py first
```
```powershell
plugin\build.ps1 -Test                # core unit tests
plugin\build.ps1                      # output\plugin\ddradar.dll + ddradar\camera_db.csv
plugin\build.ps1 -Harness             # build + end-to-end SDK harness
```
