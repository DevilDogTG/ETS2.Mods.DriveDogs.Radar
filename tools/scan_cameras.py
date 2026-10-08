#!/usr/bin/env python3
"""Find every fining speed camera the map can place -> data/cameras.json.

A model is a real camera when its .pmg carries a `speed_camera` hookup (`speedcam.20` / `speedcam.r`,
unit/hookup/speed_camera.sii). `speedcam.toll` (Scandinavian toll gates) is not speed enforcement
and is skipped.

Candidates are the models of the `sign_model` units in def/world/sign*.sii: the map places cameras as
sign items by that unit's token (see extract_camera_db.py), so a camera model no sign unit references
could never show up in the camera DB anyway. This keeps the scan to the sign models (~8.5k .pmg,
~200 MB) instead of every model in the game (~43k, 9.4 GB) now that the extracted base keeps assets
in the archives and fetches them on demand. In 1.61 both scans find the same 69 models.

usage: python tools/scan_cameras.py [--base <reference root>/base/<version>]
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from scs_common import Pmg, default_base, megapack  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGN_UNIT = re.compile(r"^\s*sign_model\s*:\s*([\w.]+)\s*\{(.*?)^\s*\}", re.M | re.S)
MODEL_DESC = re.compile(r'model_desc\s*:\s*"/?([^"]+)\.pmd"')


def sign_units_by_model(base):
    """{model path without extension: [sign_model unit names]} from def/world/sign*.sii."""
    by_model = {}
    world = os.path.join(base, "def", "world")
    for f in sorted(os.listdir(world)):
        if not (f.startswith("sign") and f.endswith(".sii")):
            continue
        with open(os.path.join(world, f), encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
        for unit, body in SIGN_UNIT.findall(text):
            m = MODEL_DESC.search(body)
            if m:
                by_model.setdefault(m.group(1), []).append(unit)
    return by_model


def find_camera_models(base, by_model):
    mp = megapack()
    rels = [m + ".pmg" for m in sorted(by_model) if mp.ref_exists(Path(base), m + ".pmg")]
    paths = mp.ref_fetch(Path(base), rels)   # one extractor run per archive; no-op when on disk
    found = {}
    for rel, path in zip(rels, paths):
        with open(path, "rb") as fh:
            data = fh.read()
        if b"speedcam." not in data:
            continue
        pmg = Pmg(data)
        hooks = [l for l in pmg.locators() if l[4] and l[4].startswith("speedcam.")]
        if not any(h[4] != "speedcam.toll" for h in hooks):
            continue
        model = rel[:-4]
        found[model] = {
            "model": model,
            "speedcam": [{"hookup": h[4], "pos": [round(v, 3) for v in h[1]],
                          "quat": [round(v, 4) for v in h[3]]} for h in hooks],
            "bbox_min": [round(v, 3) for v in pmg.bbox_min],
            "bbox_max": [round(v, 3) for v in pmg.bbox_max],
            "sign_units": by_model[model],
        }
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="default: <host reference root>/base/<GAME_VERSION>")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "cameras.json"))
    args = ap.parse_args()
    base = args.base or default_base()

    by_model = sign_units_by_model(base)
    cameras = find_camera_models(base, by_model)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="\n") as fh:
        json.dump({"base": os.path.basename(base.rstrip("/\\")),
                   "cameras": [cameras[k] for k in sorted(cameras)]}, fh, indent=1)
    print(f"{len(cameras)} camera models (of {len(by_model)} sign models) -> {args.out}")


if __name__ == "__main__":
    main()
