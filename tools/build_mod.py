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

usage: python tools/build_mod.py [--base <reference root>/base/<version>] [--version 0.1.0-dev.1]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from scs_common import Pmg, default_base, megapack  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMERA_HOOKUP = "ddradar.blink"
FACE_NEG_Z = (1.0, 0.0, 0.0, 0.0)   # quaternion (w, x, y, z): identity, flare faces -Z
FACE_POS_Z = (0.0, 0.0, 1.0, 0.0)   # 180 deg about Y
GANTRY_MIN_WIDTH = 3.0
GANTRY_HEIGHT_RATIO = 0.7

CAB_UNIT_SRC = "vehicle/truck/upgrade/interior_decors/toyglass/gps.dlc_toys"   # POC body (Toys DLC)
CAB_UNIT_DST = "vehicle/truck/upgrade/ddradar/radar_unit"
# model axes: x = width, y = height, z = out of the glass towards the driver (screen face at z ~ 0.12,
# glass side at z ~ 0). The hidden aux emitter is on every unit.
CAB_FACE_DRIVER = (0.055, 0.035, 0.125)
CAB_FACE_GLASS = (0.055, 0.035, -0.005)
CAB_AUX_EMITTER = ("ddr_aux0", (0.0, 0.0, 0.02), FACE_POS_Z, "flare.vehicle.ddr_aux")
# unit design (dev.8): aux-driven blink, one flare towards the driver (cab view) + one through the glass
CAB_LOCATORS = [
    ("ddr_cab0", CAB_FACE_DRIVER, FACE_POS_Z, "flare.vehicle.ddr_blink"),
    ("ddr_cab1", CAB_FACE_GLASS, FACE_NEG_Z, "flare.vehicle.ddr_blink"),
    CAB_AUX_EMITTER,
]

# TEST (dev.3): the engine greys out the aux controls unless an aux lamp it recognises is fitted.
# Base pattern = roof grill (r_grill) accessory with `electric_type: aux_light` + aux flares, so this
# part copies that pattern in the r_grill slot. Body is the POC GPS box (visible on the roof) until a
# real near-invisible model exists.
AUX_PART_DST = "vehicle/truck/upgrade/ddradar/aux_circuit"

# TEST (dev.8). dev.7 showed the renamed flare.vehicle.* flares blinking in the pause-menu garage, not
# while driving: from outside the small flare washes out in daylight, inside it faced away (B) or was
# moved away by fake_interior_offset (C). Variants: (suffix, locators)
CAB_TEST_VARIANTS = [
    # always on with the engine, faces the driver, no interior offset: can the driver see a cab flare?
    ("A", [("ddr_cab0", CAB_FACE_DRIVER, FACE_POS_Z, "flare.vehicle.ddr_test_e"), CAB_AUX_EMITTER]),
    # the unit design itself (aux blink, driver + glass flares)
    ("B", CAB_LOCATORS),
]
AUX_PART_LOCATORS = [CAB_AUX_EMITTER]

# POC (dev.9): the windshield slot is an interior slot and the engine does not draw its flares in
# gameplay (round 8). The sun visor (sunshld) is an exterior slot with an interior model; base precedent:
# Renault Premium sunshield_10_bc_int carries flare.vehicle.aux_light visible from the cab. So the radar
# indicator becomes a sun visor: a copy of the truck's stock visor with LED flares on the front lower
# edge - towards the driver in the interior model, forward in the exterior model. Scania S only for now.
VISOR_POC = {
    # truck: (base accessory def, LED x positions, LED y, LED z)  - model axes: z- = forward
    "scania.s_2016": ("def/vehicle/truck/scania.s_2016/accessory/sunshld/stock.sii", (-0.45, 0.45), -0.09, -0.02),
}
# TEST (dev.10): materials render in the cab (owner's Scania centre-windshield lightboard glows inside
# and out; it is lit by one `eut2.light.tex` material following parking lights). The lamp shader
# follows aux on parts with `electric_type: aux_light` (SCS Blender Tools: aux mask R = dim, G = bright,
# UV tile x 0 = white). So: copy the Griffin lightboard into frntglss_mid and point its light piece at our
# eut2.lamp material, using the board's own LED texture as base and mask.
LED_POC = {
    # truck: (base lightboard model, light material to replace)
    "scania.s_2016": ("vehicle/truck/upgrade/frntglass_mid/scania_rcab_2009/lightboard01",
                      "/automat/ba/ba6d368f32889c80.mat"),
}
LED_MAT = "/automat/dd/ddradar000led001.mat"   # same length as the replaced path (patched in place)
LED_MAT_TEXT = """effect : "eut2.lamp.add.env.rfx" {
	additional_ambient : 0.000000
	diffuse : { 1.000000 , 1.000000 , 1.000000 }
	env_factor : { 0.380056 , 0.380056 , 0.380056 }
	fresnel : { 0.200000 , 0.900000 }
	shininess : 90.000000
	specular : { 0.447988 , 0.447988 , 0.447988 }
	texture : "texture_base" {
		source : "/vehicle/truck/upgrade/frntglass_mid/scania_rcab_2009/griff01l.tobj"
		u_address : clamp
		v_address : clamp
	}
	texture : "texture_mask" {
		source : "/vehicle/truck/upgrade/frntglass_mid/scania_rcab_2009/griff01l.tobj"
		u_address : clamp
		v_address : clamp
	}
	texture : "texture_reflection" {
		source : "/material/environment/vehicle_reflection.tobj"
		u_address : clamp
		v_address : clamp
		w_address : clamp
		aniso : disabled
	}
}
"""

VISOR_VARIANTS = [
    # (suffix, name label, hookup)
    ("", "", "flare.vehicle.ddr_blink"),                 # aux blink - the design
    ("_t", " TEST A", "flare.vehicle.ddr_test_e"),       # always on with the engine - visibility check
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


def build_visors(base, stage, base_pmg):
    """POC radar sun visors (see VISOR_POC): per truck and variant, copied stock models + LED locators."""
    built = []
    for truck, (def_rel, xs, y, z) in VISOR_POC.items():
        with open(os.path.join(base, def_rel), encoding="utf-8") as fh:
            stock = fh.read()
        ext = re.search(r'exterior_model\s*:\s*"/?([^"]+)\.pmd"', stock).group(1)
        intr = re.search(r'interior_model\s*:\s*"/?([^"]+)\.pmd"', stock).group(1)
        keep = "".join(f"\t{line.strip()}\n" for line in stock.splitlines()
                       if re.match(r"\s*(suitable_for|conflict_with)\[\]", line))
        d = os.path.join(stage, "def", "vehicle", "truck", truck, "accessory", "sunshld")
        os.makedirs(d, exist_ok=True)
        for suffix, label, hookup in VISOR_VARIANTS:
            leds_in = [(f"ddr_led{i}", (x, y, z), FACE_POS_Z, hookup) for i, x in enumerate(xs)]
            leds_out = [(f"ddr_led{i}", (x, y, z), FACE_NEG_Z, hookup) for i, x in enumerate(xs)]
            model = f"vehicle/truck/upgrade/ddradar/visor_{truck.replace('.', '_')}{suffix}"
            for src, dst, locs in ((ext, model, leds_out + [CAB_AUX_EMITTER]), (intr, model + "_int", leds_in)):
                shutil.copy(os.path.join(base, src + ".pmd"), os.path.join(stage, dst + ".pmd"))
                with open(os.path.join(stage, dst + ".pmg"), "wb") as fh:
                    fh.write(base_pmg(src).with_locators(locs))
            unit = f"ddrvisor{suffix.lstrip('_')}"
            with open(os.path.join(d, f"{unit}.sii"), "w", newline="\n") as fh:
                fh.write(f"""SiiNunit
{{
accessory_addon_data : {unit}.{truck}.sunshld
{{
	name: "DriveDogs Radar sun visor{label}"
	price: 2400
	unlock: 0
	icon: "truck/scania_2016/accessory/sunshld/stock"
	part_type: aftermarket
	electric_type: aux_light

	exterior_model: "/{model}.pmd"
	interior_model: "/{model}_int.pmd"

{keep}}}
}}
""")
            built.append(f"{truck}{label}")
    return built


def build_led_tests(base, stage, base_pmg):
    """TEST (see LED_POC): aux-driven lamp-material lightboard in the centre windshield slot."""
    built = []
    os.makedirs(os.path.dirname(os.path.join(stage, LED_MAT.lstrip("/"))), exist_ok=True)
    with open(os.path.join(stage, LED_MAT.lstrip("/")), "w", newline="\n") as fh:
        fh.write(LED_MAT_TEXT)
    for truck, (model, old_mat) in LED_POC.items():
        if len(old_mat) != len(LED_MAT):
            raise ValueError("material path lengths differ - cannot patch the pmd in place")
        with open(os.path.join(base, model + ".pmd"), "rb") as fh:
            pmd = fh.read()
        if pmd.count(old_mat.encode()) != 1:
            raise ValueError(f"{old_mat} not found exactly once in {model}.pmd")
        dst = f"vehicle/truck/upgrade/ddradar/led_{truck.replace('.', '_')}"
        with open(os.path.join(stage, dst + ".pmd"), "wb") as fh:
            fh.write(pmd.replace(old_mat.encode(), LED_MAT.encode()))
        with open(os.path.join(stage, dst + ".pmg"), "wb") as fh:
            fh.write(base_pmg(model).data)
        d = os.path.join(stage, "def", "vehicle", "truck", truck, "accessory", "frntglss_mid")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "ddrled.sii"), "w", newline="\n") as fh:
            fh.write(f"""SiiNunit
{{
accessory_addon_data : ddrled.{truck}.frntglss_mid
{{
	name: "DriveDogs Radar LED board TEST"
	price: 480
	unlock: 0
	icon: "frntglass_mid/scania_rcab_2009/lightboard01"
	part_type: aftermarket
	electric_type: aux_light

	exterior_model: "/{dst}.pmd"
	interior_model: "/{dst}.pmd"
}}
}}
""")
        built.append(truck)
    return built


def write_aux_parts(base, stage):
    """TEST: one roof-grill (r_grill) aux-circuit part per truck that has the slot."""
    trucks_dir = os.path.join(base, "def", "vehicle", "truck")
    trucks = sorted(t for t in os.listdir(trucks_dir)
                    if os.path.isdir(os.path.join(trucks_dir, t, "accessory", "r_grill")))
    for truck in trucks:
        d = os.path.join(stage, "def", "vehicle", "truck", truck, "accessory", "r_grill")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "ddradar_aux.sii"), "w", newline="\n") as fh:
            fh.write(f"""SiiNunit
{{
accessory_addon_data : ddradar_aux.{truck}.r_grill
{{
	name: "DriveDogs aux circuit TEST"
	price: 10
	unlock: 0
	icon: "gps.dlc_toys"
	part_type: aftermarket

	electric_type: aux_light

	exterior_model: "/{AUX_PART_DST}.pmd"
}}
}}
""")
    return trucks


def write_accessories(base, stage, variants):
    """Windshield (set_lglass) accessories per truck that defines the slot.

    variants: [(suffix, model)] - suffix "" is the unit itself, others are TEST variants.
    """
    trucks_dir = os.path.join(base, "def", "vehicle", "truck")
    trucks = sorted(t for t in os.listdir(trucks_dir)
                    if os.path.isdir(os.path.join(trucks_dir, t, "accessory", "set_lglass")))
    for truck in trucks:
        d = os.path.join(stage, "def", "vehicle", "truck", truck, "accessory", "set_lglass")
        os.makedirs(d, exist_ok=True)
        for suffix, model in variants:
            unit = "ddradar" + suffix.lower()
            label = f" TEST {suffix}" if suffix else ""
            with open(os.path.join(d, f"{unit}.sii"), "w", newline="\n") as fh:
                fh.write(f"""SiiNunit
{{
accessory_addon_data : {unit}.{truck}.set_lglass
{{
	name: "DriveDogs Radar detector{label}"
	price: 450
	unlock: 0
	icon: "gps.dlc_toys"
	part_type: aftermarket
	electric_type: aux_light

	interior_model: "/{model}.pmd"
	exterior_model: "/{model}.pmd"
}}
}}
""")
    return trucks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="default: <host reference root>/base/<GAME_VERSION>")
    ap.add_argument("--version", default="0.1.0-dev.1")
    ap.add_argument("--packer", default="scs_packer")
    args = ap.parse_args()
    args.base = args.base or default_base()
    mp = megapack()

    def base_pmg(model):
        """A base .pmg - assets are fetched from the game archives on demand (text-only reference)."""
        return Pmg.load(mp.ref_path(Path(args.base), model + ".pmg"))

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
        dst = os.path.join(stage, cam["model"] + ".pmg")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        locs = camera_locators(cam, overrides)
        with open(dst, "wb") as fh:
            fh.write(base_pmg(cam["model"]).with_locators([(n, p, q, CAMERA_HOOKUP) for n, p, q in locs]))
        placed.append({"model": cam["model"], "locators": [[n, [round(v, 3) for v in p]] for n, p, _ in locs],
                       "source": "override" if cam["model"] in overrides else "heuristic"})

    cab_dst = os.path.join(stage, CAB_UNIT_DST)
    os.makedirs(os.path.dirname(cab_dst), exist_ok=True)
    shutil.copy(os.path.join(args.base, CAB_UNIT_SRC + ".pmd"), cab_dst + ".pmd")
    with open(cab_dst + ".pmg", "wb") as fh:
        fh.write(base_pmg(CAB_UNIT_SRC).with_locators(CAB_LOCATORS))
    gps_pmg = base_pmg(CAB_UNIT_SRC)
    variants = [("", CAB_UNIT_DST)]
    for suffix, locators in CAB_TEST_VARIANTS:
        model = f"{CAB_UNIT_DST}_test_{suffix.lower()}"
        shutil.copy(os.path.join(args.base, CAB_UNIT_SRC + ".pmd"), os.path.join(stage, model + ".pmd"))
        with open(os.path.join(stage, model + ".pmg"), "wb") as fh:
            fh.write(gps_pmg.with_locators(locators))
        variants.append((suffix, model))
    trucks = write_accessories(args.base, stage, variants)

    aux_dst = os.path.join(stage, AUX_PART_DST)
    shutil.copy(os.path.join(args.base, CAB_UNIT_SRC + ".pmd"), aux_dst + ".pmd")
    with open(aux_dst + ".pmg", "wb") as fh:
        fh.write(base_pmg(CAB_UNIT_SRC).with_locators(AUX_PART_LOCATORS))
    aux_trucks = write_aux_parts(args.base, stage)
    visors = build_visors(args.base, stage, base_pmg)
    leds = build_led_tests(args.base, stage, base_pmg)

    # one unknown attribute makes the game drop a whole .sii file (round 5) - never pack that
    lint = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "lint_units.py"), "--base", args.base])
    if lint.returncode:
        sys.exit("lint failed - package not built")

    out_dir = os.path.join(ROOT, "output")
    os.makedirs(out_dir, exist_ok=True)
    package = os.path.join(out_dir, f"drivedog_radar_v{args.version}.scs")
    if os.path.exists(package):
        os.remove(package)
    subprocess.run([args.packer, "create", package, "-root", stage], check=True,
                   stdout=subprocess.DEVNULL)
    with open(os.path.join(ROOT, "build", "placements.json"), "w", newline="\n") as fh:
        json.dump(placed, fh, indent=1)
    print(f"{len(placed)} camera models, cab unit for {len(trucks)} trucks, aux TEST part for "
          f"{len(aux_trucks)} trucks, radar sun visor POC: {', '.join(visors)}, LED board TEST: {', '.join(leds)} -> {package} "
          f"({os.path.getsize(package) // 1024} KB)")


if __name__ == "__main__":
    main()
