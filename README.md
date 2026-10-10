# DriveDogs: Radar

Euro Truck Simulator 2 mod: every **fining speed camera** of the base game and all SCS map DLCs blinks a
red police-style strobe, so you see it before it sees you. No sounds, no truck parts, ~1.8 MB.

- 69 camera models (every model the game fines with), 707 cameras placed on the map (ETS2 1.61).
- Only the cameras' `.pmg` files are overridden (strobe locators added); base models, collisions and
  materials are reused, so it does not conflict with truck, interior or map-look mods.

Want a "camera ahead" warning on a dashboard, phone or LEDs? Detection lives in the
**DevDogs.TruckSimulator** SimHub plugin, which uses the same camera database (see
[ADR-0001](docs/adr/ADR-0001-strobe-only-mod-detection-in-simhub.md)).

## Install
Copy `drivedog_radar_v<version>.scs` into `Documents\Euro Truck Simulator 2\mod` and enable it in the Mod
Manager. Optional for multiplayer (`mp_mod_optional`).

## Build (after a game update)
Requires Python 3 + Pillow, `scs_packer` on `PATH`, and the extracted game reference
(`<reference root>/base/<version>`, resolved through the `scs-mod-developer` profile helpers;
`GAME_VERSION` in `tools/scs_common.py`).

```bash
python tools/scan_cameras.py        # data/cameras.json  - fining camera models
python tools/extract_camera_db.py   # data/camera_db.csv + .meta.json - placed cameras (game version)
python tools/generate_cover.py      # src/cover.jpg (version badge from VERSION)
python tools/build_mod.py --version "$(cat VERSION)"   # lint + output/drivedog_radar_v<version>.scs
```

Strobe positions come from `data/placement_overrides.json` (hand-placed) or a gantry/pole heuristic.
The camera DB is copied into the SimHub plugin repo only for the **same game version**
(`data/camera_db.meta.json`).

## History
`docs/POC-PLAN.md` records the proof of concept (10 in-game rounds), including why an in-cab indicator
was not possible as a mod.
