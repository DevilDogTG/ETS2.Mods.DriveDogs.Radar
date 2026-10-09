#!/usr/bin/env python3
"""Extract world positions of every speed camera placed on the map -> data/camera_db.csv.

Sign items live in the sector `.base` and `.aux` files (map format 907 in 1.61). Instead of parsing every item
type, we look for the model token of each camera `sign_model` unit and validate the fixed item
header in front of it:

  u32 type (36 = sign) | u64 uid | f32 kdop_min[5] | f32 kdop_max[5] | u32 flags | u8 view_dist | u64 model

kdop_min/max[0..2] are the item's world-space AABB (x, y, z), so its centre is the camera position in
the same coordinate system the telemetry SDK reports (`truck.world.placement`).

usage: python tools/extract_camera_db.py [--base ...] [--cameras data/cameras.json]
"""
import argparse
import csv
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from scs_common import default_base, token  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGN_ITEM = 36
# offsets relative to the model token
TYPE_AT, UID_AT, KDOP_AT = -57, -53, -45


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="default: <host reference root>/base/<GAME_VERSION>")
    ap.add_argument("--cameras", default=os.path.join(ROOT, "data", "cameras.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "camera_db.csv"))
    args = ap.parse_args()
    args.base = args.base or default_base()

    with open(args.cameras) as fh:
        cameras = json.load(fh)["cameras"]
    units = {}
    for cam in cameras:
        for unit in cam["sign_units"]:
            units[struct.pack("<Q", token(unit.split(".", 1)[1]))] = (unit, cam["model"])

    sector_dir = os.path.join(args.base, "map", "europe")
    rows, seen, rejected = [], set(), 0
    for f in sorted(os.listdir(sector_dir)):
        if not f.endswith((".base", ".aux")):
            continue
        with open(os.path.join(sector_dir, f), "rb") as fh:
            data = fh.read()
        for packed, (unit, model) in units.items():
            i = data.find(packed)
            while i >= 0:
                ok = i + TYPE_AT >= 0 and struct.unpack_from("<I", data, i + TYPE_AT)[0] == SIGN_ITEM
                if ok:
                    uid = struct.unpack_from("<Q", data, i + UID_AT)[0]
                    kmin = struct.unpack_from("<5f", data, i + KDOP_AT)
                    kmax = struct.unpack_from("<5f", data, i + KDOP_AT + 20)
                    if uid not in seen:
                        seen.add(uid)
                        c = [(kmin[k] + kmax[k]) / 2 for k in range(3)]
                        rows.append([f"{uid:016x}", round(c[0], 2), round(c[1], 2), round(c[2], 2),
                                     unit, model.split("/")[-1], f.rsplit(".", 1)[0]])
                else:
                    rejected += 1
                i = data.find(packed, i + 1)

    rows.sort(key=lambda r: (r[6], r[0]))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["uid", "x", "y", "z", "unit", "model", "sector"])
        w.writerows(rows)
    # The DB is copied into other repos (DevDogs.TruckSimulator SimHub plugin) - always state which
    # game and game version it was extracted from, so a copy can be matched to the game it serves.
    meta = {"game": "ets2", "game_version": os.path.basename(args.base.rstrip("/\\")),
            "cameras": len(rows), "source": "DriveDogs Radar tools/extract_camera_db.py",
            "columns": ["uid", "x", "y", "z", "unit", "model", "sector"],
            "coordinates": "world space, metres - same as SCS telemetry truck.world.placement"}
    with open(os.path.splitext(args.out)[0] + ".meta.json", "w", newline="\n") as fh:
        json.dump(meta, fh, indent=1)
    print(f"{len(rows)} cameras placed on the map ({rejected} token hits rejected) -> {args.out}")


if __name__ == "__main__":
    main()
