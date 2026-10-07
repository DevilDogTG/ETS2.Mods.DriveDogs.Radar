#!/usr/bin/env python3
"""Find every fining speed camera in an extracted game tree -> data/cameras.json.

A model is a real camera when its .pmg carries a `speed_camera` hookup (`speedcam.20` / `speedcam.r`,
unit/hookup/speed_camera.sii). `speedcam.toll` (Scandinavian toll gates) is not speed enforcement
and is skipped. Each model is mapped to the `sign_model` units that place it on the map, because the
map stores sign items by that unit's token (see extract_camera_db.py).

usage: python tools/scan_cameras.py [--base D:/Repositories/ETS2/Extracted/base/1.61.1.1]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from scs_common import Pmg  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BASE = "D:/Repositories/ETS2/Extracted/base/1.61.1.1"
MODEL_DIRS = ("model", "model2", "prefab", "prefab2")
SIGN_UNIT = re.compile(r"^\s*sign_model\s*:\s*([\w.]+)\s*\{(.*?)^\s*\}", re.M | re.S)
MODEL_DESC = re.compile(r'model_desc\s*:\s*"/?([^"]+)\.pmd"')


def find_camera_models(base):
    found = {}
    for top in MODEL_DIRS:
        for dirpath, _, files in os.walk(os.path.join(base, top)):
            for f in files:
                if not f.endswith(".pmg"):
                    continue
                path = os.path.join(dirpath, f)
                with open(path, "rb") as fh:
                    data = fh.read()
                if b"speedcam." not in data:
                    continue
                pmg = Pmg(data)
                hooks = [l for l in pmg.locators() if l[4] and l[4].startswith("speedcam.")]
                if not any(h[4] != "speedcam.toll" for h in hooks):
                    continue
                rel = os.path.relpath(path, base).replace(os.sep, "/")[:-4]
                found[rel] = {
                    "model": rel,
                    "speedcam": [{"hookup": h[4], "pos": [round(v, 3) for v in h[1]],
                                  "quat": [round(v, 4) for v in h[3]]} for h in hooks],
                    "bbox_min": [round(v, 3) for v in pmg.bbox_min],
                    "bbox_max": [round(v, 3) for v in pmg.bbox_max],
                    "sign_units": [],
                }
    return found


def map_sign_units(base, cameras):
    world = os.path.join(base, "def", "world")
    for f in sorted(os.listdir(world)):
        if not (f.startswith("sign") and f.endswith(".sii")):
            continue
        with open(os.path.join(world, f), encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
        for unit, body in SIGN_UNIT.findall(text):
            m = MODEL_DESC.search(body)
            if m and m.group(1) in cameras:
                cameras[m.group(1)]["sign_units"].append(unit)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "cameras.json"))
    args = ap.parse_args()

    cameras = find_camera_models(args.base)
    map_sign_units(args.base, cameras)
    orphans = [m for m, c in cameras.items() if not c["sign_units"]]
    if orphans:
        print("warning: camera models without a sign unit:", orphans)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="\n") as fh:
        json.dump({"base": os.path.basename(args.base.rstrip("/\\")),
                   "cameras": [cameras[k] for k in sorted(cameras)]}, fh, indent=1)
    print(f"{len(cameras)} camera models -> {args.out}")


if __name__ == "__main__":
    main()
