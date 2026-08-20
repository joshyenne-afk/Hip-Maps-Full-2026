#!/usr/bin/env python3
"""Generate a proof-of-concept branded HipMaps tile overlay.

Creates an 'Italian Ladies Weekend in Sonoma' branded map image,
georeferences it with GDAL, and generates z/x/y tiles for the viewer.

V2: Much prettier borders, compass rose, and venue legend.
"""

import os, sys, subprocess, shutil, json, math, re, urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, '.venv', 'lib'))

from PIL import Image, ImageDraw, ImageFont

# ── Paths ──
PUBLIC_DIR = os.path.join(SCRIPT_DIR, 'public')
TILES_DIR  = os.path.join(PUBLIC_DIR, 'tiles')

# ── 3 Sonoma Venues ──
VENUES = [
    {"name": "Kivelstadt Cellars",  "lat": 38.2444, "lng": -122.4487, "icon": "🍷", "type": "Tasting Room"},
    {"name": "Little Vineyards",    "lat": 38.3444, "lng": -122.5040, "icon": "🍇", "type": "Vineyard"},
    {"name": "Bettencourt House",   "lat": 38.2872, "lng": -122.4623, "icon": "🏠", "type": "Stay"},
]

# ── Geographic bounds ──
BOUNDS = {"north": 38.39, "south": 38.21, "east": -122.39, "west": -122.55}

# ── Image size ──
W, H = 6400, 8400

# ── Colors ──
WINE_DARK  = (89, 32, 42)
WINE       = (114, 47, 55)
WINE_LIGHT = (155, 77, 85)
GOLD       = (218, 175, 62)
GOLD_LIGHT = (235, 210, 130)
GOLD_DARK  = (178, 140, 40)
PARCHMENT  = (245, 238, 228)
CREAM      = (252, 248, 240)
WHITE      = (255, 255, 255)
DARK       = (30, 41, 59)
WATER      = (163, 193, 214)
PARK       = (197, 221, 182)
IT_GREEN   = (0, 140, 69)
IT_RED     = (205, 33, 42)
BORDER_BG  = (62, 35, 40)


def get_api_key():
    with open(os.path.join(SCRIPT_DIR, 'config.js')) as f:
        for line in f:
            m = re.search(r'GOOGLE_API_KEY\s*=\s*["\']([^"\']+)["\']', line)
            if m:
                return m.group(1)
    return None


def latlng_to_px(lat, lng):
    x = int((lng - BOUNDS["west"]) / (BOUNDS["east"] - BOUNDS["west"]) * W)
    y = int((BOUNDS["north"] - lat) / (BOUNDS["north"] - BOUNDS["south"]) * H)
    return x, y


def load_font(name, size):
    paths = [
        f"/System/Library/Fonts/Supplemental/{name}.ttf",
        f"/System/Library/Fonts/{name}.ttf",
        f"/Library/Fonts/{name}.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ════════════════════════════════════════════
# DECORATIVE ELEMENTS
# ════════════════════════════════════════════

def draw_ornate_border(draw, w, h):
    """Draw a multi-layered ornate border with corner ornaments."""
    # Outermost solid band
    draw.rectangle([0, 0, w-1, h-1], fill=BORDER_BG)

    # Gold outer frame
    b = 28
    draw.rectangle([b, b, w-b, h-b], outline=GOLD, width=6)

    # Inner gold frame with gap
    b2 = b + 16
    draw.rectangle([b2, b2, w-b2, h-b2], outline=GOLD_DARK, width=3)

    # Decorative dots along the border
    dot_spacing = 48
    dot_r = 4
    for x in range(b2 + 30, w - b2 - 30, dot_spacing):
        draw.ellipse([x-dot_r, b+4, x+dot_r, b+4+dot_r*2], fill=GOLD)
        draw.ellipse([x-dot_r, h-b-4-dot_r*2, x+dot_r, h-b-4], fill=GOLD)
    for y in range(b2 + 30, h - b2 - 30, dot_spacing):
        draw.ellipse([b+4, y-dot_r, b+4+dot_r*2, y+dot_r], fill=GOLD)
        draw.ellipse([w-b-4-dot_r*2, y-dot_r, w-b-4, y+dot_r], fill=GOLD)

    # Corner ornaments (grape/vine flourish)
    corners = [(b2+10, b2+10), (w-b2-10, b2+10), (b2+10, h-b2-10), (w-b2-10, h-b2-10)]
    for cx, cy in corners:
        draw_corner_ornament(draw, cx, cy)

    return b2 + 8  # inner margin


def draw_corner_ornament(draw, cx, cy):
    """Draw a grape cluster corner ornament."""
    r = 10
    # Grape cluster — small circles in a triangle pattern
    offsets = [
        (0, 0), (-12, -10), (12, -10),
        (-6, 12), (6, 12), (0, 24),
        (-18, 2), (18, 2),
    ]
    for dx, dy in offsets:
        draw.ellipse([cx+dx-r, cy+dy-r, cx+dx+r, cy+dy+r], fill=WINE, outline=GOLD_DARK, width=2)

    # Vine tendrils — curved lines from the cluster
    for angle_mult in [-1, 1]:
        points = []
        for t in range(20):
            px = cx + angle_mult * (30 + t * 3)
            py = cy - 15 + int(12 * math.sin(t * 0.5))
            points.append((px, py))
        if len(points) > 2:
            draw.line(points, fill=GOLD_DARK, width=2)

    # Small leaves
    leaf_pts = [
        [(cx-35, cy-8), (cx-45, cy-20), (cx-30, cy-18), (cx-35, cy-8)],
        [(cx+35, cy-8), (cx+45, cy-20), (cx+30, cy-18), (cx+35, cy-8)],
    ]
    for lp in leaf_pts:
        draw.polygon(lp, fill=IT_GREEN, outline=GOLD_DARK, width=1)


def draw_fancy_compass(draw, cx, cy, r):
    """Draw a gorgeous multi-layered compass rose."""
    # Outer decorative ring
    draw.ellipse([cx-r-8, cy-r-8, cx+r+8, cy+r+8], fill=None, outline=GOLD, width=4)

    # Degree tick marks
    for angle in range(0, 360, 15):
        rad = math.radians(angle)
        inner_r = r - 6 if angle % 45 == 0 else r - 3
        outer_r = r + 3
        x1, y1 = cx + inner_r * math.sin(rad), cy - inner_r * math.cos(rad)
        x2, y2 = cx + outer_r * math.sin(rad), cy - outer_r * math.cos(rad)
        w = 2 if angle % 45 == 0 else 1
        draw.line([(x1, y1), (x2, y2)], fill=GOLD, width=w)

    # White filled circle
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=CREAM, outline=GOLD_DARK, width=3)

    # 8-point star (intercardinal thin points)
    ir = r * 0.25
    for angle in [45, 135, 225, 315]:
        rad = math.radians(angle)
        tip_x = cx + (r - 14) * math.sin(rad)
        tip_y = cy - (r - 14) * math.cos(rad)
        left_rad = math.radians(angle - 12)
        right_rad = math.radians(angle + 12)
        lx, ly = cx + ir * math.sin(left_rad), cy - ir * math.cos(left_rad)
        rx, ry = cx + ir * math.sin(right_rad), cy - ir * math.cos(right_rad)
        draw.polygon([(tip_x, tip_y), (lx, ly), (rx, ry)], fill=GOLD_LIGHT, outline=GOLD_DARK, width=1)

    # 4 cardinal points (big bold)
    cardinal_data = [
        (0, WINE_DARK, WINE),       # N
        (90, (160,160,160), (130,130,130)),   # E
        (180, (160,160,160), (130,130,130)),  # S
        (270, (160,160,160), (130,130,130)),  # W
    ]
    for angle, fill1, fill2 in cardinal_data:
        rad = math.radians(angle)
        tip_x = cx + (r - 10) * math.sin(rad)
        tip_y = cy - (r - 10) * math.cos(rad)
        # Two-tone diamond shape
        left_rad = math.radians(angle - 18)
        right_rad = math.radians(angle + 18)
        lx, ly = cx + ir * math.sin(left_rad), cy - ir * math.cos(left_rad)
        rx, ry = cx + ir * math.sin(right_rad), cy - ir * math.cos(right_rad)
        draw.polygon([(tip_x, tip_y), (lx, ly), (cx, cy)], fill=fill1, outline=GOLD_DARK, width=1)
        draw.polygon([(tip_x, tip_y), (rx, ry), (cx, cy)], fill=fill2, outline=GOLD_DARK, width=1)

    # Center jewel
    draw.ellipse([cx-12, cy-12, cx+12, cy+12], fill=GOLD, outline=WINE_DARK, width=2)
    draw.ellipse([cx-6, cy-6, cx+6, cy+6], fill=WINE, outline=GOLD, width=1)

    # Cardinal letters
    cfont = load_font("Georgia Bold", 26)
    draw.text((cx-8, cy-r-32), "N", fill=WINE_DARK, font=cfont)
    draw.text((cx-5, cy+r+10), "S", fill=DARK, font=cfont)
    draw.text((cx+r+12, cy-9), "E", fill=DARK, font=cfont)
    draw.text((cx-r-28, cy-9), "W", fill=DARK, font=cfont)


def draw_venue_legend(img, draw, x, y, venues):
    """Draw a polished venue legend box with wine theme."""
    leg_w, leg_h = 600, 340
    title_font = load_font("Georgia Bold", 38)
    item_font  = load_font("Georgia", 30)
    type_font  = load_font("Georgia Italic", 24)

    # Semi-transparent background
    legend_bg = Image.new('RGBA', (leg_w, leg_h), (255, 255, 255, 235))
    lg_draw = ImageDraw.Draw(legend_bg)

    # Border with double-line effect
    lg_draw.rectangle([0, 0, leg_w-1, leg_h-1], outline=WINE + (255,), width=4)
    lg_draw.rectangle([6, 6, leg_w-7, leg_h-7], outline=GOLD + (255,), width=2)

    # Header bar
    lg_draw.rectangle([8, 8, leg_w-8, 62], fill=WINE + (255,))
    lg_draw.text((20, 16), "🍷 VENUE GUIDE", fill=WHITE + (255,), font=title_font)

    # Italian flag stripe under header
    stripe_h = 4
    third = (leg_w - 16) // 3
    lg_draw.rectangle([8, 62, 8+third, 62+stripe_h], fill=IT_GREEN + (255,))
    lg_draw.rectangle([8+third, 62, 8+third*2, 62+stripe_h], fill=WHITE + (255,))
    lg_draw.rectangle([8+third*2, 62, leg_w-8, 62+stripe_h], fill=IT_RED + (255,))

    # Venue items
    for i, v in enumerate(venues):
        ey = 80 + i * 80
        # Numbered circle
        lg_draw.ellipse([20, ey+8, 52, ey+40], fill=WINE + (255,), outline=GOLD + (255,), width=2)
        num_font = load_font("Georgia Bold", 24)
        nb = lg_draw.textbbox((0,0), str(i+1), font=num_font)
        nw = nb[2] - nb[0]
        lg_draw.text((36 - nw//2, ey+12), str(i+1), fill=WHITE + (255,), font=num_font)
        # Name and type
        lg_draw.text((62, ey+6), v["name"], fill=DARK + (255,), font=item_font)
        lg_draw.text((62, ey+40), v["type"], fill=WINE_LIGHT + (255,), font=type_font)

    # Composite onto main image
    img.paste(Image.alpha_composite(
        Image.new('RGBA', (leg_w, leg_h), (0,0,0,0)), legend_bg
    ).convert('RGB'), (x, y))


def download_static_map(api_key, center_lat, center_lng, zoom, img_w, img_h):
    """Download a styled Google Static Map image."""
    req_w = min(640, img_w // 2)
    req_h = min(640, img_h // 2)

    styles = [
        "feature:all|element:labels|visibility:off",
        "feature:road|element:geometry.fill|color:0xFF00FF",
        "feature:road|element:geometry.stroke|color:0xFF00FF",
        "feature:road.highway|element:geometry.fill|color:0xFF00FF",
        "feature:road.highway|element:geometry.stroke|color:0xDD00DD",
        "feature:water|element:geometry|color:0xa3c1d6",
        "feature:landscape|element:geometry.fill|color:0xf0ebe1",
        "feature:poi.park|element:geometry.fill|color:0xc5ddb6",
        "feature:transit|visibility:off",
        "feature:poi|element:labels|visibility:off",
    ]
    style_str = '&'.join(f'style={s}' for s in styles)

    url = (
        f"https://maps.googleapis.com/maps/api/staticmap?"
        f"center={center_lat},{center_lng}&zoom={zoom}"
        f"&size={req_w}x{req_h}&scale=2&maptype=roadmap"
        f"&{style_str}&key={api_key}"
    )

    print(f"  📥 Downloading styled map (zoom {zoom})...")
    req = urllib.request.Request(url, headers={'User-Agent': 'HipMaps-POC/1.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()

    tmp = os.path.join(SCRIPT_DIR, '_tmp_static.png')
    with open(tmp, 'wb') as f:
        f.write(data)
    print(f"     {len(data)//1024} KB downloaded")
    return tmp


# ════════════════════════════════════════════
# SPAGHETTI STREETS + DECORATIVE ELEMENTS
# ════════════════════════════════════════════

def apply_spaghetti_to_roads(img, map_left, map_top, map_right, map_bot):
    """Scan for magenta road pixels and replace with spaghetti pasta texture."""
    import numpy as np

    pixels = np.array(img)
    region = pixels[map_top:map_bot, map_left:map_right].copy()

    r, g, b = region[:,:,0].astype(np.int16), region[:,:,1].astype(np.int16), region[:,:,2].astype(np.int16)

    # Detect magenta/pink road pixels: R and B both high, G much lower
    # Wider threshold catches anti-aliased edges too
    is_road = (r > 140) & (b > 140) & (g < 180) & ((r - g) > 40) & ((b - g) > 40)

    road_count = np.sum(is_road)
    print(f"     Found {road_count:,} road pixels to replace")

    if road_count > 0:
        # Vectorized spaghetti texture — no Python loop needed
        h, w = region.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]

        # Wavy strand pattern based on position
        strand = (np.sin(xx.astype(np.float32) * 0.3 + yy.astype(np.float32) * 0.1) * 20).astype(np.int16)
        # Per-pixel noise (deterministic via seed)
        rng = np.random.RandomState(42)
        noise = rng.randint(-15, 16, size=(h, w), dtype=np.int16)

        # Pasta golden color with texture
        pr = np.clip(218 + noise + (strand * 3 // 10), 0, 255).astype(np.uint8)
        pg = np.clip(185 + noise + (strand * 2 // 10), 0, 255).astype(np.uint8)
        pb = np.clip(107 + noise // 2, 0, 255).astype(np.uint8)

        region[is_road, 0] = pr[is_road]
        region[is_road, 1] = pg[is_road]
        region[is_road, 2] = pb[is_road]

    pixels[map_top:map_bot, map_left:map_right] = region
    return Image.fromarray(pixels)


def draw_route_path(draw, venues, mx, my, mr, mb):
    """Draw a dotted route path connecting venues with Italian flag colors."""
    if len(venues) < 2:
        return
    pts = []
    for v in venues:
        vx, vy = latlng_to_px(v["lat"], v["lng"])
        if mx < vx < mr and my < vy < mb:
            pts.append((vx, vy))

    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i+1]
        steps = 40
        colors = [(0, 140, 69), (255, 255, 255), (205, 33, 42)]  # Italian flag
        for s in range(steps):
            t = s / steps
            sx = int(x1 + (x2 - x1) * t)
            sy = int(y1 + (y2 - y1) * t)
            if s % 3 == 0:  # Dotted
                c = colors[s % 3]
                draw.ellipse([sx-4, sy-4, sx+4, sy+4], fill=c)


def draw_italian_illustrations(draw, mx, my, mr, mb):
    """Draw scattered Italian food and wine illustrations on the map."""
    import random
    random.seed(99)

    def draw_wine_bottle(cx, cy, scale=1.0):
        s = scale
        # Bottle body
        draw.rectangle([int(cx-6*s), int(cy-20*s), int(cx+6*s), int(cy+20*s)],
                       fill=(60, 20, 20), outline=(40, 10, 10), width=1)
        # Neck
        draw.rectangle([int(cx-3*s), int(cy-35*s), int(cx+3*s), int(cy-20*s)],
                       fill=(60, 20, 20))
        # Cork
        draw.rectangle([int(cx-2*s), int(cy-40*s), int(cx+2*s), int(cy-35*s)],
                       fill=(180, 150, 100))
        # Label
        draw.rectangle([int(cx-5*s), int(cy-8*s), int(cx+5*s), int(cy+8*s)],
                       fill=(245, 235, 210), outline=(180, 150, 100))

    def draw_cheese_wedge(cx, cy, scale=1.0):
        s = scale
        pts = [(int(cx-15*s), int(cy+10*s)), (int(cx+15*s), int(cy+10*s)),
               (int(cx+5*s), int(cy-15*s))]
        draw.polygon(pts, fill=(255, 210, 80), outline=(200, 165, 50), width=2)
        # Holes
        for _ in range(3):
            hx = cx + random.randint(int(-8*s), int(8*s))
            hy = cy + random.randint(int(-5*s), int(5*s))
            draw.ellipse([hx-2, hy-2, hx+2, hy+2], fill=(230, 190, 60))

    def draw_grape_cluster(cx, cy, scale=1.0):
        s = scale
        PURPLE = (100, 30, 80)
        positions = [(0,0), (-7,6), (7,6), (-4,12), (4,12), (0,18), (-8,-2), (8,-2)]
        for dx, dy in positions:
            gx = int(cx + dx*s)
            gy = int(cy + dy*s)
            r = int(5*s)
            draw.ellipse([gx-r, gy-r, gx+r, gy+r], fill=PURPLE, outline=(80, 20, 60))
        # Stem
        draw.line([(cx, int(cy-5*s)), (cx, int(cy-18*s))], fill=(80, 60, 30), width=2)
        # Leaf
        draw.ellipse([int(cx+2), int(cy-20*s), int(cx+14*s), int(cy-12*s)],
                     fill=(80, 140, 60))

    map_w = mr - mx
    map_h = mb - my

    # Place illustrations at strategic spots (away from venues)
    spots = [
        (0.12, 0.15, 'bottle'), (0.82, 0.20, 'grapes'), (0.15, 0.75, 'cheese'),
        (0.85, 0.70, 'bottle'), (0.75, 0.15, 'cheese'), (0.20, 0.45, 'grapes'),
        (0.70, 0.80, 'grapes'), (0.08, 0.50, 'bottle'),
    ]

    for px, py, kind in spots:
        x = int(mx + px * map_w)
        y = int(my + py * map_h)
        sc = random.uniform(1.2, 1.8)
        if kind == 'bottle':
            draw_wine_bottle(x, y, sc)
        elif kind == 'cheese':
            draw_cheese_wedge(x, y, sc)
        elif kind == 'grapes':
            draw_grape_cluster(x, y, sc)


def draw_scale_bar(draw, x, y):
    """Draw a professional scale bar."""
    font = load_font("Georgia", 22)
    bar_w = 200
    # Background
    draw.rectangle([x-5, y-5, x+bar_w+60, y+35], fill=(255, 255, 255, 200))
    # Bar segments
    draw.rectangle([x, y+10, x+bar_w//2, y+20], fill=(80, 40, 30))
    draw.rectangle([x+bar_w//2, y+10, x+bar_w, y+20], fill=(200, 180, 160))
    draw.rectangle([x, y+10, x+bar_w, y+20], outline=(80, 40, 30), width=1)
    # Labels
    draw.text((x, y-4), "0", fill=(80, 40, 30), font=font)
    draw.text((x+bar_w//2-10, y-4), "1.5", fill=(80, 40, 30), font=font)
    draw.text((x+bar_w-5, y-4), "3 mi", fill=(80, 40, 30), font=font)


# ════════════════════════════════════════════
# MAIN IMAGE BUILDER
# ════════════════════════════════════════════

def create_branded_map():
    """Build the full 'Italian Ladies Weekend' branded map image."""
    print("🎨 Creating branded map image (v2 — pretty borders)...")

    img = Image.new('RGB', (W, H), BORDER_BG)
    draw = ImageDraw.Draw(img)

    # Fonts
    title_font   = load_font("Georgia Bold", 120)
    title2_font  = load_font("Georgia Bold Italic", 100)
    sub_font     = load_font("Georgia Italic", 52)
    small_font   = load_font("Georgia", 36)
    tiny_font    = load_font("Georgia Italic", 28)
    footer_font  = load_font("Georgia", 32)

    # ═══ ORNATE BORDER ═══
    margin = draw_ornate_border(draw, W, H)

    # ═══ HEADER BAND ═══
    hdr_top = margin + 6
    hdr_h = 520
    # Gradient-like header (dark wine to wine)
    for i in range(hdr_h):
        t = i / hdr_h
        r = int(WINE_DARK[0] + (WINE[0] - WINE_DARK[0]) * t * 0.5)
        g = int(WINE_DARK[1] + (WINE[1] - WINE_DARK[1]) * t * 0.5)
        b = int(WINE_DARK[2] + (WINE[2] - WINE_DARK[2]) * t * 0.5)
        draw.line([(margin+6, hdr_top+i), (W-margin-6, hdr_top+i)], fill=(r, g, b))

    # Gold line at top of header
    draw.rectangle([margin+6, hdr_top, W-margin-6, hdr_top+5], fill=GOLD)

    # Italian flag stripe at very top
    stripe_w = (W - 2*margin - 12) // 3
    draw.rectangle([margin+6, hdr_top+6, margin+6+stripe_w, hdr_top+12], fill=IT_GREEN)
    draw.rectangle([margin+6+stripe_w, hdr_top+6, margin+6+stripe_w*2, hdr_top+12], fill=WHITE)
    draw.rectangle([margin+6+stripe_w*2, hdr_top+6, W-margin-6, hdr_top+12], fill=IT_RED)

    # Title text
    t1 = "Italian Ladies"
    bb1 = draw.textbbox((0,0), t1, font=title_font)
    tx = (W - (bb1[2]-bb1[0])) // 2
    # Gold shadow
    draw.text((tx+3, hdr_top+63), t1, fill=GOLD_DARK, font=title_font)
    draw.text((tx, hdr_top+60), t1, fill=WHITE, font=title_font)

    t2 = "Weekend!"
    bb2 = draw.textbbox((0,0), t2, font=title2_font)
    tx2 = (W - (bb2[2]-bb2[0])) // 2
    draw.text((tx2+2, hdr_top+192), t2, fill=WINE_DARK, font=title2_font)
    draw.text((tx2, hdr_top+190), t2, fill=GOLD, font=title2_font)

    # Decorative divider
    div_y = hdr_top + 310
    div_cx = W // 2
    # Line — diamond — line
    draw.line([(margin+120, div_y), (div_cx-60, div_y)], fill=GOLD, width=2)
    draw.line([(div_cx+60, div_y), (W-margin-120, div_y)], fill=GOLD, width=2)
    # Diamond
    d = 12
    draw.polygon([(div_cx, div_y-d), (div_cx+d, div_y), (div_cx, div_y+d), (div_cx-d, div_y)],
                  fill=GOLD, outline=GOLD_DARK, width=1)

    # Subtitle
    sub = "~ Sonoma Wine Country ~"
    bbs = draw.textbbox((0,0), sub, font=sub_font)
    draw.text(((W-(bbs[2]-bbs[0]))//2, hdr_top+340), sub, fill=(255,230,210), font=sub_font)

    # Tagline
    tag = "Three days of wine, laughter & la dolce vita"
    bbt = draw.textbbox((0,0), tag, font=tiny_font)
    draw.text(((W-(bbt[2]-bbt[0]))//2, hdr_top+420), tag, fill=(255,210,190), font=tiny_font)

    # Gold line at bottom of header
    draw.rectangle([margin+6, hdr_top+hdr_h-5, W-margin-6, hdr_top+hdr_h], fill=GOLD)

    # ═══ MAP AREA ═══
    map_top = hdr_top + hdr_h + 8
    map_bot = H - margin - 70
    map_left = margin + 6
    map_right = W - margin - 6
    map_w = map_right - map_left
    map_h = map_bot - map_top

    draw.rectangle([map_left, map_top, map_right, map_bot], fill=PARCHMENT)

    # Try to composite a real styled Google Map
    api_key = get_api_key()
    if api_key:
        try:
            clat = (BOUNDS["north"] + BOUNDS["south"]) / 2
            clng = (BOUNDS["east"] + BOUNDS["west"]) / 2
            tmp = download_static_map(api_key, clat, clng, 14, map_w, map_h)
            smap = Image.open(tmp).convert('RGB')
            smap = smap.resize((map_w, map_h), Image.LANCZOS)
            img.paste(smap, (map_left, map_top))
            os.remove(tmp)
            print("  ✅ Real styled map composited")
        except Exception as e:
            print(f"  ⚠️ Static map failed ({e}), using parchment fill")

    # ═══ SPAGHETTI STREETS ═══
    # Replace magenta road pixels with golden spaghetti pasta texture
    print("  🍝 Applying spaghetti texture to roads...")
    img = apply_spaghetti_to_roads(img, map_left, map_top, map_right, map_bot)
    draw = ImageDraw.Draw(img)  # Refresh draw after pixel manipulation

    # ═══ ROUTE PATH BETWEEN VENUES ═══
    draw_route_path(draw, VENUES, map_left, map_top, map_right, map_bot)

    # ═══ DECORATIVE ILLUSTRATIONS ═══
    draw_italian_illustrations(draw, map_left, map_top, map_right, map_bot)

    # ═══ SCALE BAR ═══
    draw_scale_bar(draw, map_left + 40, map_bot - 60)

    # ═══ VENUE MARKERS ═══
    pin_font = load_font("Georgia Bold", 28)
    label_font = load_font("Georgia Bold", 26)

    for i, v in enumerate(VENUES):
        px, py = latlng_to_px(v["lat"], v["lng"])
        if not (map_left < px < map_right and map_top < py < map_bot):
            continue

        # Shadow
        sr = 26
        draw.ellipse([px-sr+3, py-sr-8, px+sr+3, py+sr-8], fill=(0,0,0,80))

        # Teardrop body
        r = 24
        draw.ellipse([px-r, py-r-10, px+r, py+r-10], fill=WINE, outline=GOLD, width=3)
        draw.polygon([(px-r+8, py+r-18), (px, py+r+14), (px+r-8, py+r-18)], fill=WINE)
        # Gold outline on point
        draw.line([(px-r+8, py+r-18), (px, py+r+14)], fill=GOLD, width=2)
        draw.line([(px+r-8, py+r-18), (px, py+r+14)], fill=GOLD, width=2)

        # Number
        num = str(i+1)
        nb = draw.textbbox((0,0), num, font=pin_font)
        nw, nh = nb[2]-nb[0], nb[3]-nb[1]
        draw.text((px - nw//2, py - nh//2 - 12), num, fill=WHITE, font=pin_font)

        # Label banner
        name_short = v["name"]
        lb = draw.textbbox((0,0), name_short, font=label_font)
        lw = lb[2] - lb[0]
        lx = px - lw//2
        ly = py + r + 20
        # Rounded label bg
        pad = 8
        draw.rounded_rectangle([lx-pad, ly-4, lx+lw+pad, ly+lb[3]-lb[1]+6],
                                radius=6, fill=WHITE, outline=WINE, width=2)
        draw.text((lx, ly), name_short, fill=DARK, font=label_font)

    # ═══ COMPASS ROSE ═══
    draw_fancy_compass(draw, map_right - 180, map_top + 180, 75)

    # ═══ VENUE LEGEND ═══
    draw_venue_legend(img, draw, map_left + 30, map_bot - 370, VENUES)

    # ═══ FOOTER ═══
    footer_y = H - margin - 55
    # Dark bar
    draw.rectangle([margin+6, footer_y-8, W-margin-6, H-margin-6], fill=WINE_DARK)
    draw.rectangle([margin+6, footer_y-8, W-margin-6, footer_y-5], fill=GOLD)

    ft = "Map designed by HipMaps.com  ·  hipmaps.com"
    fb = draw.textbbox((0,0), ft, font=footer_font)
    draw.text(((W-(fb[2]-fb[0]))//2, footer_y+4), ft, fill=GOLD_LIGHT, font=footer_font)

    # ═══ SAVE ═══
    out = os.path.join(SCRIPT_DIR, 'poc_branded_map.png')
    img.save(out, 'PNG')
    sz = os.path.getsize(out) / (1024*1024)
    print(f"  ✅ Saved: poc_branded_map.png ({sz:.1f} MB, {W}x{H})")
    return out


def georeference_and_tile(image_path):
    """Georeference with GDAL and generate tiles."""
    georef = os.path.join(SCRIPT_DIR, '_poc_georef.tif')

    print("🌍 Georeferencing...")
    r = subprocess.run([
        'gdal_translate', '-of', 'GTiff',
        '-a_ullr', str(BOUNDS['west']), str(BOUNDS['north']),
                   str(BOUNDS['east']), str(BOUNDS['south']),
        '-a_srs', 'EPSG:4326',
        image_path, georef
    ], capture_output=True, text=True, timeout=60)

    if r.returncode != 0:
        print(f"  ❌ gdal_translate failed: {r.stderr}")
        return False
    print("  ✅ Georeferenced")

    # Clean old tiles
    if os.path.exists(TILES_DIR):
        shutil.rmtree(TILES_DIR)

    min_z, max_z = 12, 17
    print(f"🧩 Generating tiles (zoom {min_z}-{max_z})...")
    r = subprocess.run([
        'gdal2tiles.py', '-z', f'{min_z}-{max_z}',
        '-w', 'none', '--xyz', georef, TILES_DIR
    ], capture_output=True, text=True, timeout=300)

    if r.returncode != 0:
        print(f"  ❌ gdal2tiles failed: {r.stderr}")
        return False

    count = sum(1 for root, _, files in os.walk(TILES_DIR) for f in files if f.endswith('.png'))
    print(f"  ✅ Generated {count} tiles")

    # Update bounds.json
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    with open(os.path.join(PUBLIC_DIR, 'bounds.json'), 'w') as f:
        json.dump({
            **BOUNDS,
            "center": {
                "lat": (BOUNDS["north"]+BOUNDS["south"])/2,
                "lng": (BOUNDS["east"]+BOUNDS["west"])/2
            },
            "zoom": 14,
            "maxZoom": max_z
        }, f, indent=2)
    print("  ✅ Updated bounds.json")

    # Cleanup
    if os.path.exists(georef):
        os.remove(georef)

    return True


if __name__ == '__main__':
    print("=" * 55)
    print("🗺️  HipMaps POC v2: Italian Ladies Weekend")
    print("   Pretty borders · Compass rose · Venue legend")
    print("=" * 55)

    img_path = create_branded_map()
    ok = georeference_and_tile(img_path)

    if ok:
        print()
        print("✅ PROOF OF CONCEPT v2 READY!")
        print("   → http://localhost:8080/viewer.html")
    else:
        print("❌ Failed — check GDAL output above")
