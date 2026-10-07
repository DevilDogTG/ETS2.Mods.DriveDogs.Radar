#!/usr/bin/env python3
"""Build the DriveDogs Radar mod package -> output/drivedog_radar_v<version>.scs

Inputs:
  data/cameras.json            fining camera models (tools/scan_cameras.py)
  data/placement_overrides.json  hand-placed flare locators for models where the heuristic is off
  src/                         static mod files (manifest, hookup units, icon)
  extracted base game          source .pmg files (never shipped unmodified)

Per camera model only the .pmg is overridden: the base .pmd/.pmc and materials are reused, so the
package stays tiny and inherits base-game fixes to anything except locators.

POC parts that are NOT for release: the cab unit body is a copy of the Toys DLC GPS model.

usage: python tools/build_mod.py [--base ...] [--version 0.1.0-dev.1]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from scs_common import Pmg  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BASE = "D:/Repositories/ETS2/Extracted/base/1.61.1.1"
CAMERA_HOOKUP = "ddradar.blink"
FACE_NEG_Z = (1.0, 0.0, 0.0, 0.0)   # quaternion (w, x, y, z): identity, flare faces -Z
FACE_POS_Z = (0.0, 0.0, 1.0, 0.0)   # 180 deg about Y
GANTRY_MIN_WIDTH = 3.0
GANTRY_HEIGHT_RATIO = 0.7

CAB_UNIT_SRC = "vehicle/truck/upgrade/interior_decors/toyglass/gps.dlc_toys"   # POC body (Toys DLC)
CAB_UNIT_DST = "vehicle/truck/upgrade/ddradar/radar_unit"
CAB_LOCATORS = [
    # model axes: x = width, y = height, z = out of the glass towards the driver (face at z ~ 0.12)
    ("ddr_cab0", (0.055, 0.035, 0.125), FACE_POS_Z, "ddradar.cab_blink"),
    ("ddr_aux0", (0.0, 0.0, 0.02), FACE_POS_Z, "ddradar.cab_aux"),
]


def camera_locators(cam, overrides):
    """Flare locators for one camera model: hand override, else gantry/pole heuristic."""
    if cam["model"] in overrides:
        return [(o["name"], tuple(o["pos"]), tuple(o["quat"])) for o in overrides[cam["model"]]]
    mn, mx = cam["bbox_min"], cam["bbox_max"]
    cz = (mn[2] + mx[2]) / 2
    half_depth = min((mx[2] - mn[2]) / 2, 0.5)
    lanes = sorted({round(h["pos"][0], 1) for h in cam["speedcam"]
                    if mn[0] - 0.5 <= h["pos"][0] <= mx[0] + 0.5})
    if lanes and mx[0] - mn[0] >= GANTRY_MIN_WIDTH:
        # gantry: a flare pair above every enforced lane
        y = mx[1] * GANTRY_HEIGHT_RATIO
        xs = lanes
    else:
        # pole / box beside the road: a flare pair on top of the head
        y = mx[1] - 0.25
        xs = [(mn[0] + mx[0]) / 2]
    out = []
    for n, x in enumerate(xs):
        out.append((f"ddr_bl{2 * n}", (x, y, cz - half_depth), FACE_NEG_Z))
        out.append((f"ddr_bl{2 * n + 1}", (x, y, cz + half_depth), FACE_POS_Z))
    return out


def write_accessories(base, stage):
    """One windshield (set_lglass) accessory per truck that defines the slot."""
    trucks_dir = os.path.join(base, "def", "vehicle", "truck")
    trucks = sorted(t for t in os.listdir(trucks_dir)
                    if os.path.isdir(os.path.join(trucks_dir, t, "accessory", "set_lglass")))
    for truck in trucks:
        d = os.path.join(stage, "def", "vehicle", "truck", truck, "accessory", "set_lglass")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "ddradar.sii"), "w", newline="\n") as fh:
            fh.write(f"""SiiNunit
{{
accessory_addon_data : ddradar.{truck}.set_lglass
{{
	name: "DriveDogs Radar detector"
	price: 450
	unlock: 0
	icon: "gps.dlc_toys"
	part_type: aftermarket
	electric_type: aux_light

	interior_model: "/{CAB_UNIT_DST}.pmd"
	exterior_model: "/{CAB_UNIT_DST}.pmd"
}}
}}
""")
    return trucks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--version", default="0.1.0-dev.1")
    ap.add_argument("--packer", default="scs_packer")
    args = ap.parse_args()

    with open(os.path.join(ROOT, "data", "cameras.json")) as fh:
        cameras = json.load(fh)["cameras"]
    with open(os.path.join(ROOT, "data", "placement_overrides.json")) as fh:
        overrides = json.load(fh)

    stage = os.path.join(ROOT, "build", "stage")
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    shutil.copytree(os.path.join(ROOT, "src"), stage)

    manifest = os.path.join(stage, "manifest.sii")
    with open(manifest) as fh:
        text = fh.read().replace("@VERSION@", args.version)
    with open(manifest, "w", newline="\n") as fh:
        fh.write(text)

    placed = []
    for cam in cameras:
        src = os.path.join(args.base, cam["model"] + ".pmg")
        dst = os.path.join(stage, cam["model"] + ".pmg")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        locs = camera_locators(cam, overrides)
        with open(dst, "wb") as fh:
            fh.write(Pmg.load(src).with_locators([(n, p, q, CAMERA_HOOKUP) for n, p, q in locs]))
        placed.append({"model": cam["model"], "locators": [[n, [round(v, 3) for v in p]] for n, p, _ in locs],
                       "source": "override" if cam["model"] in overrides else "heuristic"})

    cab_dst = os.path.join(stage, CAB_UNIT_DST)
    os.makedirs(os.path.dirname(cab_dst), exist_ok=True)
    shutil.copy(os.path.join(args.base, CAB_UNIT_SRC + ".pmd"), cab_dst + ".pmd")
    with open(cab_dst + ".pmg", "wb") as fh:
        fh.write(Pmg.load(os.path.join(args.base, CAB_UNIT_SRC + ".pmg")).with_locators(CAB_LOCATORS))
    trucks = write_accessories(args.base, stage)

    out_dir = os.path.join(ROOT, "output")
    os.makedirs(out_dir, exist_ok=True)
    package = os.path.join(out_dir, f"drivedog_radar_v{args.version}.scs")
    if os.path.exists(package):
        os.remove(package)
    subprocess.run([args.packer, "create", package, "-root", stage], check=True,
                   stdout=subprocess.DEVNULL)
    with open(os.path.join(ROOT, "build", "placements.json"), "w", newline="\n") as fh:
        json.dump(placed, fh, indent=1)
    print(f"{len(placed)} camera models, cab unit for {len(trucks)} trucks -> {package} "
          f"({os.path.getsize(package) // 1024} KB)")


if __name__ == "__main__":
    main()
