#!/usr/bin/env python3
"""
Generates the Mod Manager cover/thumbnail (src/cover.jpg, referenced by manifest.sii `icon:`). SCS requires a
276x162 JPEG.

Same layout and gold/amber palette as the other DriveDogs covers (logo top-left, title block right centred
on the cover, road, amber version badge top-right); the Radar motif is a night road with a pole-mounted speed
camera in the bottom-right corner beside the road, firing the mod's red police-style strobe, its red glow
reflected on the verge.

Composited at 4x (1104x648) then downscaled for anti-aliasing. The badge is read from VERSION, so rerun this
before every build that bumps the version.

The game badge (bottom-left, one colour per game so the ETS2 and ATS covers differ at thumbnail size) reads
the game from pack.config.json (it holds only `game`: Radar builds with tools/build_mod.py), the declaration
the megapack host config's repo_game() reads too.
"""
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "logo.png"
OUT_PATH = ROOT / "src" / "cover.jpg"
VERSION_PATH = ROOT / "VERSION"
PACK_CONFIG_PATH = ROOT / "pack.config.json"

SCALE = 4
FINAL_SIZE = (276, 162)
CANVAS_SIZE = (FINAL_SIZE[0] * SCALE, FINAL_SIZE[1] * SCALE)

FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf"
FONT_REG = r"C:\Windows\Fonts\arial.ttf"

BG_TOP = (8, 12, 22)
BG_BOTTOM = (24, 20, 14)
TITLE_COLOR = (255, 255, 255)
SUBTITLE_COLOR = (255, 196, 84)
STAR_COLOR = (255, 236, 200)
HORIZON_GLOW = (90, 105, 140)
HILL_FAR = (30, 30, 40)
HILL_NEAR = (19, 19, 26)
POLE_COLOR = (150, 152, 160)
BOX_COLOR = (92, 96, 106)
LENS_COLOR = (16, 16, 20)
STROBE_COLOR = (255, 40, 40)
STROBE_CORE = (255, 220, 220)
ROAD_EDGE = (255, 170, 70)
BADGE_COLOR = (255, 196, 84)
BADGE_TEXT_COLOR = (20, 16, 10)
# Same values as the DriveDogs family reference (DriveDogs Pets): ETS2 blue, ATS red.
GAME_BADGES = {"ets2": ("ETS2", (40, 110, 210)), "ats": ("ATS", (200, 45, 45))}
GAME_TEXT_COLOR = (255, 255, 255)

HORIZON = 0.74


def read_version():
    version = VERSION_PATH.read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit(f"Empty {VERSION_PATH}")
    return version


def read_game():
    game = json.loads(PACK_CONFIG_PATH.read_text(encoding="utf-8-sig")).get("game", "ets2")
    if game not in GAME_BADGES:
        raise SystemExit(f"{PACK_CONFIG_PATH} game {game!r}: no badge defined")
    return game


def composite(img, *layers):
    base = img.convert("RGBA")
    for layer in layers:
        base = Image.alpha_composite(base, layer)
    return base.convert("RGB")


def make_background(size):
    w, h = size
    img = Image.new("RGB", size, BG_BOTTOM)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        draw.line([(0, y), (w, y)], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    return img


def add_stars(img):
    w, h = img.size
    rng = random.Random(20261007)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for _ in range(60):
        x, y = rng.uniform(0, w), rng.uniform(0, h * HORIZON * 0.85)
        r = rng.choice((1, 1, 1, 2, 2, 3))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(*STAR_COLOR, rng.randint(50, 160)))
    return composite(img, layer)


def add_horizon_glow(img):
    w, h = img.size
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([-w * 0.1, h * (HORIZON - 0.16), w * 1.1, h * (HORIZON + 0.06)],
                                  fill=(*HORIZON_GLOW, 110))
    return composite(img, layer.filter(ImageFilter.GaussianBlur(radius=h * 0.07)))


def add_hills(img):
    w, h = img.size
    draw = ImageDraw.Draw(img)
    for color, y0, amp, phase in ((HILL_FAR, HORIZON - 0.04, 0.05, 0.3), (HILL_NEAR, HORIZON + 0.02, 0.03, 1.9)):
        pts = [(0, h)]
        for i in range(0, 101):
            t = i / 100
            y = h * (y0 - amp * (0.6 * abs(((t * 2.1 + phase) % 2) - 1) + 0.4 * abs(((t * 4.7 + phase) % 2) - 1)))
            pts.append((w * t, y))
        pts.append((w, h))
        draw.polygon(pts, fill=color)
    return img


def add_road(img):
    """Road vanishing at the horizon, dashed centre line, amber edge lines."""
    w, h = img.size
    draw = ImageDraw.Draw(img)
    top_y = int(h * (HORIZON - 0.01))
    draw.polygon([(w * 0.26, h), (w * 0.74, h), (w * 0.52, top_y), (w * 0.48, top_y)], fill=(28, 30, 36))
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.line([(w * 0.27, h), (w * 0.482, top_y)], fill=(*ROAD_EDGE, 170), width=max(2, int(h * 0.006)))
    ld.line([(w * 0.73, h), (w * 0.518, top_y)], fill=(*ROAD_EDGE, 170), width=max(2, int(h * 0.006)))
    for i in range(5):
        t0, t1 = i / 5, (i + 0.5) / 5
        y0, y1 = h - (h - top_y) * t0, h - (h - top_y) * t1
        half = w * 0.006 * (1 - t0)
        ld.rectangle([w * 0.5 - half, y1, w * 0.5 + half, y0], fill=(120, 110, 90, 255))
    return composite(img, layer.filter(ImageFilter.GaussianBlur(radius=h * 0.004)), layer)


def add_camera(img):
    """Pole speed camera on the right verge in the bottom-right corner, below the title block (where Economy keeps
    its coins and Physics its springs), box facing the driver, firing the red strobe: hard core + wide bloom + a
    red smear on the verge below."""
    w, h = img.size
    x, base_y = w * 0.88, h * 0.98
    top_y = h * 0.76
    pole_w, box_w, box_h = w * 0.006, w * 0.045, h * 0.12

    body = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    d.rectangle([x - pole_w, top_y + box_h * 0.6, x + pole_w, base_y], fill=(*POLE_COLOR, 255))
    d.rounded_rectangle([x - box_w / 2, top_y, x + box_w / 2, top_y + box_h], radius=h * 0.01,
                        fill=(*BOX_COLOR, 255))
    lens_r = box_w * 0.17
    for k in (0.33, 0.68):
        ly = top_y + box_h * k
        d.ellipse([x - lens_r, ly - lens_r, x + lens_r, ly + lens_r], fill=(*LENS_COLOR, 255))

    sx, sy = x + box_w * 0.32, top_y - h * 0.012
    core = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(core).ellipse([sx - h * 0.016, sy - h * 0.016, sx + h * 0.016, sy + h * 0.016],
                                 fill=(*STROBE_CORE, 255))
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse([sx - h * 0.05, sy - h * 0.05, sx + h * 0.05, sy + h * 0.05],
                                 fill=(*STROBE_COLOR, 255))
    bloom = halo.filter(ImageFilter.GaussianBlur(radius=h * 0.06))
    rays = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(rays)
    rd.line([(sx - h * 0.18, sy), (sx + h * 0.18, sy)], fill=(*STROBE_COLOR, 200), width=int(h * 0.006))
    rd.line([(sx, sy - h * 0.10), (sx, sy + h * 0.10)], fill=(*STROBE_COLOR, 160), width=int(h * 0.005))

    smear = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(smear).ellipse([w * 0.76, h * 0.90, w * 1.00, h * 1.04], fill=(*STROBE_COLOR, 90))
    return composite(img, smear.filter(ImageFilter.GaussianBlur(radius=h * 0.04)), body, bloom, bloom,
                     rays.filter(ImageFilter.GaussianBlur(radius=h * 0.006)),
                     halo.filter(ImageFilter.GaussianBlur(radius=h * 0.015)), core)


def paste_logo(img):
    logo = Image.open(LOGO_PATH).convert("RGBA")
    target_h = int(img.height * 0.62)
    logo = logo.resize((int(logo.width * target_h / logo.height), target_h), Image.LANCZOS)
    pad = int(img.height * 0.06)
    pos = (pad, pad)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow_logo = Image.new("RGBA", logo.size, (0, 0, 0, 255))
    shadow_logo.putalpha(logo.split()[3].point(lambda a: a * 160 // 255))
    shadow.paste(shadow_logo, (pos[0] + 6, pos[1] + 6), shadow_logo)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
    base = Image.alpha_composite(img.convert("RGBA"), shadow)
    base.paste(logo, pos, logo)
    return base.convert("RGB")


def fit_font(draw, text, font_path, max_width, start_size, min_size=10):
    size = start_size
    while size > min_size:
        font = ImageFont.truetype(font_path, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(font_path, min_size)


def draw_with_outline(draw, pos, text, font, fill, outline=(0, 0, 0), width=2):
    x, y = pos
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def add_text(img):
    draw = ImageDraw.Draw(img)
    w, h = img.size
    x_start = w * 0.40
    max_width = w * 0.97 - x_start
    title_lines = ["DriveDogs:", "Radar"]
    subtitle = "Speed Camera Detector"

    title_size = int(h * 0.135)
    for line in title_lines:
        title_size = min(title_size, fit_font(draw, line, FONT_BOLD, max_width, title_size).size)
    title_font = ImageFont.truetype(FONT_BOLD, title_size)
    subtitle_font = fit_font(draw, subtitle, FONT_REG, max_width, int(h * 0.06))

    line_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (line_bbox[3] - line_bbox[1]) * 1.15
    y = h * 0.50 - (line_h * len(title_lines) + line_h * 0.9) / 2
    for line in title_lines:
        draw_with_outline(draw, (x_start, y), line, title_font, TITLE_COLOR, width=3)
        y += line_h
    y += line_h * 0.15
    draw_with_outline(draw, (x_start, y), subtitle, subtitle_font, SUBTITLE_COLOR, width=2)
    return img


def pill(img, text, fill, text_fill, anchor):
    """A rounded pill holding `text`; anchor = ("right", "top") for the version, ("left", "bottom") for the
    game - legible at the final 276x162 size."""
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    font = ImageFont.truetype(FONT_BOLD, int(h * 0.06))
    bbox = draw.textbbox((0, 0), text, font=font)
    pad_x, pad_y, margin = h * 0.02, h * 0.015, h * 0.03
    pw, ph = (bbox[2] - bbox[0]) + 2 * pad_x, (bbox[3] - bbox[1]) + 2 * pad_y
    x0 = w - margin - pw if anchor[0] == "right" else margin
    y0 = margin if anchor[1] == "top" else h - margin - ph
    draw.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=ph / 2, fill=(*fill, 235))
    draw.text((x0 + pad_x - bbox[0], y0 + pad_y - bbox[1]), text, font=font, fill=text_fill)
    return img


def main():
    version, game = read_version(), read_game()
    img = make_background(CANVAS_SIZE)
    img = add_stars(img)
    img = add_horizon_glow(img)
    img = add_hills(img)
    img = add_road(img)
    img = add_camera(img)
    img = paste_logo(img)
    img = add_text(img)
    img = pill(img, f"v{version}", BADGE_COLOR, BADGE_TEXT_COLOR, ("right", "top"))
    label, colour = GAME_BADGES[game]
    img = pill(img, label, colour, GAME_TEXT_COLOR, ("left", "bottom"))
    img = img.resize(FINAL_SIZE, Image.LANCZOS)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT_PATH, "JPEG", quality=92)
    print(f"Wrote {OUT_PATH} ({img.size[0]}x{img.size[1]}, v{version}, {label})")


if __name__ == "__main__":
    main()
