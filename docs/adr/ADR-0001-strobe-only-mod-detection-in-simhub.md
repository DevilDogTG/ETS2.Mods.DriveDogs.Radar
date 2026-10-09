# ADR-0001: Strobe-only mod; speed-camera detection moves to the SimHub plugin

- Status: Accepted
- Date: 2026-10-09
- Deciders: DevilDogTG (owner), with Claude

## Context

The POC (docs/POC-PLAN.md, rounds 1–10 on ETS2 1.61) aimed at two things: a red strobe on every
fining speed camera, and an in-cab "camera ahead" indicator driven by an SCS SDK plugin.

- **Strobes work.** `.pmg`-only overrides of the 69 fining camera models (locators injected by
  `tools/build_mod.py`) show a police-pattern strobe on all 707 placed cameras.
- **Detection works.** The SDK plugin located cameras from `data/camera_db.csv` (707 cameras extracted
  from the map sectors) using telemetry `truck.world.placement`; its log showed
  `camera ahead … / camera passed` reliably in game.
- **The in-cab indicator could not be built.** An SCS mod cannot read world data, so the plugin had to
  toggle a light state (aux) that a truck part follows. Findings:
  - aux stays greyed until an aux lamp is fitted (roof grill with `electric_type: aux_light` unlocks it);
  - flares on truck parts are not drawn in the cab view during gameplay (windshield slot: never;
    sun visor: outside only) — only in the pause-menu showroom;
  - the aux-driven lamp material needs a 4th vertex stream existing meshes lack (own mesh needed);
  - the HUD and dashboard UI expose no aux / free on/off state for a custom icon.
- The owner already runs SimHub, whose ETS2 telemetry includes the truck's world position.

## Decision

1. **This mod is strobe-only**: camera models + strobe unit, no truck parts, no SDK plugin.
2. **Detection and display move to the DevDogs.TruckSimulator SimHub plugin** (repo
   `DevilDogTG/SimHub.Plugins.TruckSimulator`), as a feature planned after its .NET port passes testing:
   properties `DDTruckPlugin.Radar.*`, events `RadarCameraAhead` / `RadarCameraPassed`, shown on SimHub
   dashboards / LEDs. ETS2 first, ATS later.
3. **Camera data is duplicated, not shared.** Each repo keeps its own copy of the camera DB, always
   labelled with game and game version (`data/camera_db.meta.json`). Copies are interchangeable only for
   the same game version.

## Consequences

- The mod stays tiny (~1.8 MB) and conflict-free with truck/interior mods; no Toys DLC dependency.
- No `ddradar.dll` in the game folder, no "advanced SDK features" notice, no aux binding.
- The in-cab experience depends on SimHub; players without SimHub get strobes only.
- After a game update both repos must refresh their camera DB (rerun `scan_cameras.py` +
  `extract_camera_db.py` here, then copy if the plugin targets the same game version).
- Removed code stays in history: C++ plugin and harness at `12a5936:plugin/`; windshield / visor /
  LED / aux parts in `12a5936:tools/build_mod.py`.
