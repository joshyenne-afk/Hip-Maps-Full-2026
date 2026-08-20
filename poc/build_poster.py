#!/usr/bin/env python3
"""POC: composite a HipMaps-style poster from a stylized tile source.

Proves the deliverable look — title banner, brand frame, venue pins + labels,
legend panel, compass, scale bar, logo — on top of the AI-traced map.

Pin placement uses Web Mercator y (NOT linear latitude); the stylized image is
a Mercator capture, so linear-in-degrees placement would drift toward the edges.
"""
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TITLE = "GIRLS WEEKEND IN SONOMA"
SUBTITLE = "A Wine Country Wander"

# ── Brand palette (matches the flat editorial house style) ──
FRAME_OUTER = (232, 163, 61)     # warm gold
BAND        = (108, 33, 45)      # deep burgundy
CREAM       = (247, 239, 217)
INK         = (58, 42, 38)
PIN_RED     = (176, 46, 46)
RULE        = (140, 45, 61)

FONTS = "/System/Library/Fonts/Supplemental"

# Map art is composited at its NATIVE resolution — downscaling here throws away
# detail before tiling and lowers the max usable zoom. Layout was authored
# against a 3000px map, so chrome and type scale by S to match.
MAP = 4096
S = MAP / 3000.0


def sc(v):
    """Scale a design-unit length to the current map resolution."""
    return int(round(v * S))


def font(name, size, index=0):
    path = os.path.join(FONTS, name)
    try:
        return ImageFont.truetype(path, sc(size), index=index)
    except Exception:
        return ImageFont.load_default(size=sc(size))


def merc_y(lat):
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def build():
    src = Image.open(os.path.join(HERE, "stylized_4k.png")).convert("RGB")
    bounds = json.load(open(os.path.join(ROOT, "public", "bounds.json")))
    venues = json.load(open(os.path.join(ROOT, "public", "venues.json")))

    # Crop 1.2% off each edge to drop the baked-in Static Maps watermarks;
    # clean attribution goes in the footer instead.
    w0, h0 = src.size
    inset = int(w0 * 0.012)
    src = src.crop((inset, inset, w0 - inset, h0 - inset))

    # Bounds shrink with the crop, so pins stay correct.
    fx = inset / w0
    n, s = bounds["north"], bounds["south"]
    e, w = bounds["east"], bounds["west"]
    my_n, my_s = merc_y(n), merc_y(s)
    n = math.degrees(2 * math.atan(math.exp(my_n - (my_n - my_s) * fx)) - math.pi / 2)
    s = math.degrees(2 * math.atan(math.exp(my_s + (my_n - my_s) * fx)) - math.pi / 2)
    e -= (e - w) * fx
    w += (bounds["east"] - bounds["west"]) * fx

    if src.size[0] != MAP:
        src = src.resize((MAP, MAP), Image.LANCZOS)

    FRAME, BAND_H, FOOT_H = sc(70), sc(620), sc(300)
    W = MAP + FRAME * 2
    H = BAND_H + MAP + FOOT_H + FRAME * 2

    poster = Image.new("RGB", (W, H), FRAME_OUTER)
    d = ImageDraw.Draw(poster)

    # Title band
    d.rectangle([FRAME, FRAME, W - FRAME, FRAME + BAND_H], fill=BAND)

    # Track the DESIGN-unit size; font() applies S internally, so feeding a
    # scaled size back in would compound the scaling on every iteration.
    title_pt = 210
    f_title = font("Didot.ttc", title_pt, index=1)
    f_sub = font("Didot.ttc", 78, index=0)

    while d.textlength(TITLE, font=f_title) > MAP - sc(160) and title_pt > 20:
        title_pt = int(title_pt * 0.94)
        f_title = font("Didot.ttc", title_pt, index=1)
    d.text((W / 2, FRAME + BAND_H * 0.40), TITLE, font=f_title, fill=CREAM, anchor="mm")

    # rules flanking the subtitle
    sw = d.textlength(SUBTITLE, font=f_sub)
    ry = FRAME + BAND_H * 0.72
    d.text((W / 2, ry), SUBTITLE, font=f_sub, fill=FRAME_OUTER, anchor="mm")
    for sign in (-1, 1):
        x0 = W / 2 + sign * (sw / 2 + sc(60))
        x1 = W / 2 + sign * (sw / 2 + sc(300))
        d.line([x0, ry, x1, ry], fill=FRAME_OUTER, width=sc(5))

    # Map
    my = FRAME + BAND_H
    poster.paste(src, (FRAME, my))
    d.rectangle([FRAME, my, W - FRAME, my + MAP], outline=BAND, width=sc(10))

    # ── Venue pins ──
    # OFF by default. Pins baked into the image are dead pixels — they cannot be
    # tapped, they do not scale with zoom, and they cannot show info windows.
    # The app renders them as live Google Maps markers on top of these tiles.
    # Set DRAW_PINS=1 only when exporting a flat poster for print.
    if os.environ.get("DRAW_PINS") == "1":
        f_lbl = font("Didot.ttc", 62, index=1)
        myn, mys = merc_y(n), merc_y(s)
        placed = []
        for i, v in enumerate(venues, 1):
            px = FRAME + (v["lng"] - w) / (e - w) * MAP
            py = my + (myn - merc_y(v["lat"])) / (myn - mys) * MAP
            r = 30
            d.ellipse([px - r, py - r, px + r, py + r], fill=PIN_RED, outline=CREAM, width=7)
            d.text((px, py), str(i), font=font("Didot.ttc", 40, index=1), fill=CREAM, anchor="mm")

            name = v["name"].title()
            lw = d.textlength(name, font=f_lbl)
            lx, ly = px + r + 22, py - 34
            if lx + lw > FRAME + MAP - 30:
                lx = px - r - 22 - lw
            placed.append((lx, ly, lw, name))

        for lx, ly, lw, name in placed:
            d.rectangle([lx - 14, ly - 8, lx + lw + 14, ly + 68], fill=(247, 239, 217, 230))
            d.text((lx, ly), name, font=f_lbl, fill=BAND)

    # ── Compass ──
    cx, cy, cr = FRAME + sc(230), my + MAP - sc(260), sc(120)
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=CREAM, outline=BAND, width=6)
    d.polygon([(cx, cy - cr + sc(18)), (cx - sc(34), cy + sc(22)), (cx + sc(34), cy + sc(22))], fill=PIN_RED)
    d.polygon([(cx, cy + cr - sc(18)), (cx - sc(34), cy - sc(22)), (cx + sc(34), cy - sc(22))], fill=BAND)
    d.text((cx, cy - cr + sc(46)), "N", font=font("Didot.ttc", 46, index=1), fill=CREAM, anchor="mm")

    # ── Scale bar ── (segment count chosen so the bar always fits the frame)
    km_px = MAP / ((e - w) * 111.32 * math.cos(math.radians((n + s) / 2)))
    segs, seg_km = 4, 1
    while km_px * segs * seg_km > MAP * 0.30:
        if seg_km == 1:
            seg_km = 0.5
        else:
            segs -= 1
        if segs <= 1:
            break
    bar_w = km_px * segs * seg_km
    bx = FRAME + MAP - bar_w - sc(90)
    by = my + MAP - sc(130)
    for k in range(segs):
        seg = km_px * seg_km
        d.rectangle([bx + k * seg, by, bx + (k + 1) * seg, by + sc(26)],
                    fill=BAND if k % 2 == 0 else CREAM, outline=BAND, width=4)
    d.text((bx, by - sc(52)), "0", font=font("Didot.ttc", 40), fill=BAND, anchor="la")
    d.text((bx + bar_w, by - sc(52)), f"{segs * seg_km:g} km",
           font=font("Didot.ttc", 40), fill=BAND, anchor="ra")

    # ── Footer: legend + logo + attribution ──
    fy = my + MAP
    d.rectangle([FRAME, fy, W - FRAME, fy + FOOT_H], fill=BAND)

    f_leg = font("Didot.ttc", 50, index=0)
    for i, v in enumerate(venues, 1):
        col = i - 1
        lx = FRAME + sc(70) + col * (MAP - sc(700)) / 3
        d.ellipse([lx, fy + sc(74), lx + sc(42), fy + sc(116)], fill=PIN_RED, outline=CREAM, width=4)
        d.text((lx + sc(21), fy + sc(95)), str(i), font=font("Didot.ttc", 30, index=1),
               fill=CREAM, anchor="mm")
        d.text((lx + sc(62), fy + sc(72)), v["name"].title(), font=f_leg, fill=CREAM)

    # made-up logo mark
    gx, gy = W - FRAME - sc(190), fy + FOOT_H / 2
    d.ellipse([gx - sc(92), gy - sc(92), gx + sc(92), gy + sc(92)], outline=FRAME_OUTER, width=7)
    d.text((gx, gy - sc(22)), "HIP", font=font("Didot.ttc", 62, index=1), fill=CREAM, anchor="mm")
    d.text((gx, gy + sc(34)), "MAPS", font=font("Didot.ttc", 44, index=1), fill=FRAME_OUTER, anchor="mm")

    d.text((FRAME + sc(70), fy + FOOT_H - sc(74)),
           "Map data ©2026 Google  ·  Illustrated by HipMaps",
           font=font("Didot.ttc", 34), fill=FRAME_OUTER)

    out = os.path.join(HERE, "poster_girls_weekend.png")
    poster.save(out)
    print(f"✅ {out}  {poster.size[0]}×{poster.size[1]}")

    # Sidecar: where the georeferenced map sits inside the poster, and the exact
    # bounds of THAT sub-rectangle. The tiler extrapolates outward from this to
    # the poster edges in EPSG:3857 so the blue dot lands correctly on the art.
    sidecar = {
        "poster": {"width": poster.size[0], "height": poster.size[1]},
        "mapRect": {"x0": FRAME, "y0": my, "x1": FRAME + MAP, "y1": my + MAP},
        "mapBounds": {"north": n, "south": s, "east": e, "west": w},
    }
    sidecar_path = os.path.join(HERE, "poster_georef.json")
    json.dump(sidecar, open(sidecar_path, "w"), indent=2)
    print(f"   sidecar: {sidecar_path}")
    prev = poster.copy()
    prev.thumbnail((1100, 1100), Image.LANCZOS)
    prev.save(os.path.join(HERE, "poster_preview.png"))
    print("   preview: poc/poster_preview.png")


if __name__ == "__main__":
    build()
