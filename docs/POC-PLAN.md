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
| Cover image | ✅ `src/cover.jpg` (`tools/generate_cover.py`, World style) |
| Plugin core + unit tests | ✅ `plugin\build.ps1 -Test` passes (707 cameras, 30 Berlin) |
| Plugin DLL (SDK 1.15) | ✅ `output/plugin/ddradar.dll`, zip `output/drivedog_radar_plugin_v0.1.0-dev.1.zip` |
| End-to-end SDK harness | ✅ `plugin\build.ps1 -Harness`: fake game drives through a Berlin camera → aux on 350 m before, off 10 m after |
| In-game test round 1 | Spike 1: tested the wrong model (Berlin = `speed_camera_ch`); Spike 2: unit mounts ✅, aux greyed ❌ |

## Test checklist — v0.1.0-dev.1 (one session)

Setup: remove `ddradar_spike1.scs` / `ddradar_spike2.scs`; copy `drivedog_radar_v0.1.0-dev.1.scs` to the
mod folder and enable it (needs **Toys DLC** — POC unit body). Keep Garage-j1 Radar disabled.

**A. Camera strobe** (Berlin is ideal: 30 cameras)
- [ ] Berlin white pole camera (`speed_camera_ch`) strobes red, both directions?
- [ ] Any gantry (DE motorway / NL / FR): strobe visible, roughly on the camera, not floating oddly?
- [ ] Note any camera with a misplaced/absent strobe (country + screenshot) → fix via `placement_overrides.json`.
- [ ] Still fined when speeding? Models look normal (no missing textures)?

**B. Windshield unit + aux**
- [ ] Fit "DriveDogs Radar detector" (windshield left glass slot).
- [ ] F4 → Lights: aux now enabled? (front / roof / both)
- [ ] Bind a key to that aux, toggle → unit blinks red; off → stops.
- [ ] If still greyed: fit any roof-grill with aux lamps → does aux unlock and does the unit blink?

**C. Plugin** (after the toolchain + SDK are available)
- [ ] Unzip `drivedog_radar_plugin_v0.1.0-dev.1.zip` into `<game>\bin\win_x64\` (creates `plugins\ddradar.dll` +
      `plugins\ddradar\camera_db.csv`); accept the "advanced SDK features" notice at game start.
- [ ] `game.log.txt` shows `[ddradar] loaded 707 cameras`, `telemetry ready`, `input device registered`.
- [ ] Options → Controls: bind *front aux* → "DriveDogs Radar / Aux toggle A" (and roof → B).
- [ ] Drive towards a Berlin camera: log `camera ahead`, unit blinks ~350 m before, stops after passing.

Send `game.log.txt` + screenshots.

## Open questions / risks

| # | Question | Resolve by |
|---|---|---|
| Q1 | Does the hidden `flare_vehicle aux` unlock the aux control? | test B |
| Q2 | Does a `flare_blink light_type: aux` follow front, roof or both aux states? | test B |
| Q3 | Strobe heuristic positions on 67 unverified models | test A + overrides |
| Q4 | ~~Aux toggle cycles?~~ SDK docs: aux states 0 off / 1 dimmed / 2 full → toggle cycles; `AuxController` presses until telemetry matches (on = 1 press, off = 2 presses). Harness models this. | resolved |
| Q5 | Map DB coverage: DLC sectors overriding base sectors in the merged extraction — any cameras missing? | test C on DLC maps |
| Q6 | Truck def ids for DLC trucks lacking `accessory/set_lglass` folders (e.g. Scania S 2024e, DAF XF Electric) | map interior ↔ def ids |

## Release blockers (not for POC)

- Windshield unit body is a **copy of the Toys DLC GPS model** → needs our own model (Blender + SCS Blender
  Tools), then the Toys DLC dependency goes away.
- Plugin ships SCS SDK-derived code only as compiled DLL; SDK headers stay out of git.
- Audit command: compare a new extracted base with `data/cameras.json` (new / changed camera models).

## Prerequisites on the dev machine

- Python 3 + Pillow; `scs_packer` on `PATH` (already: `D:\Programs\ScsSoftwares\bin`).
- Extracted base game: `D:\Repositories\ETS2\Extracted\base\<version>` (default 1.61.1.1).
- Visual Studio *Desktop development with C++* (MSVC 14.51 + Windows SDK 10.0.26100) — installed 2026-10-07.
- SCS SDK 1.15 (`https://download.eurotrucksimulator2.com/scs_sdk_1_15.zip`, MIT-style licence) unpacked to
  `plugin/sdk/` (git-ignored); its licence ships with the plugin.

## Commands

```bash
python tools/scan_cameras.py          # data/cameras.json
python tools/extract_camera_db.py     # data/camera_db.csv
python tools/generate_cover.py        # src/cover.jpg (reads VERSION)
python tools/build_mod.py --version "$(cat VERSION)"
```
```powershell
plugin\build.ps1 -Test                # core unit tests
plugin\build.ps1                      # output\plugin\ddradar.dll + ddradar\camera_db.csv
plugin\build.ps1 -Harness             # build + end-to-end SDK harness
```
