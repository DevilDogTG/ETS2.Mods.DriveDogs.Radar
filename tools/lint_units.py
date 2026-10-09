#!/usr/bin/env python3
"""Lint our .sii units against the extracted base game before packing.

The game rejects a whole .sii file on the first unknown attribute (round 5: one bad attribute on
`ddradar.cab_test_d` dropped every camera strobe and the aux emitter). For every unit in src/ we check
that its class exists in base data and that each attribute is one base data uses on that class - or
one we have already seen load in game (PROVEN). Exit code 1 on any problem.

usage: python tools/lint_units.py [--base ...]
"""
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from scs_common import default_base  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIT = re.compile(r"^\s*(\w+)\s*:\s*([\w.]+)\s*\{(.*?)^\s*\}", re.M | re.S)
ATTR = re.compile(r"^\s*(\w+)\s*(?:\[\d*\])?\s*:", re.M)
SCAN_DIRS = ("unit", "def/vehicle")

# attributes not used by base data on that class but confirmed to load in game
PROVEN = {
    "flare_blink": {"fade_distance", "fade_span"},          # ddradar.blink, rounds 2-4
}


def strip_comments(text):
    return re.sub(r"(#|//).*", "", text)


def base_attributes(base):
    attrs = collections.defaultdict(set)
    for sub in SCAN_DIRS:
        for dirpath, _, files in os.walk(os.path.join(base, sub)):
            for f in files:
                if f.endswith((".sii", ".sui")):
                    with open(os.path.join(dirpath, f), encoding="utf-8", errors="ignore") as fh:
                        for cls, _, body in UNIT.findall(strip_comments(fh.read())):
                            attrs[cls].update(ATTR.findall(body))
    return attrs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="default: <host reference root>/base/<GAME_VERSION>")
    ap.add_argument("files", nargs="*", help="defaults to every .sii under src/ and build/stage/def")
    args = ap.parse_args()
    args.base = args.base or default_base()

    files = args.files or [os.path.join(d, f)
                           for top in (os.path.join(ROOT, "src"), os.path.join(ROOT, "build", "stage", "def"))
                           for d, _, fs in os.walk(top) for f in fs if f.endswith(".sii")]
    known = base_attributes(args.base)
    problems = []
    for path in files:
        if os.path.basename(path) == "manifest.sii":
            continue
        with open(path, encoding="utf-8") as fh:
            for cls, name, body in UNIT.findall(strip_comments(fh.read())):
                if cls not in known:
                    problems.append(f"{path}: {name}: unknown class '{cls}'")
                    continue
                allowed = known[cls] | PROVEN.get(cls, set())
                for attr in ATTR.findall(body):
                    if attr not in allowed:
                        problems.append(f"{path}: {name} ({cls}): attribute '{attr}' not seen in base")
    for p in problems:
        print(p)
    print(f"lint: {len(files)} files, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
