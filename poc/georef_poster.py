#!/usr/bin/env python3
"""Georeference a POSTER (map + brand chrome) and slice it into XYZ tiles.

The problem this solves
-----------------------
server.py assigns the capture bounds to the ENTIRE image. That is correct only
when the image IS the map. A HipMaps deliverable wraps the map in a title band,
frame and legend, so the map occupies a sub-rectangle — feeding the poster to
the old path shears the geography by the proportion of the chrome.

Here we extrapolate outward from the map sub-rectangle to the poster edges, and
we do it in EPSG:3857 (Web Mercator) where that extrapolation is LINEAR. Doing
it in EPSG:4326 would bow the result, because Mercator is nonlinear in latitude.
That also removes the Plate-Carree error the old 4326 path carried.

Usage: python3 georef_poster.py [poster.png] [poster_georef.json] [out_tiles_dir]
"""
import json
import math
import os
import subprocess
import sys

R = 6378137.0  # WGS84 semi-major axis, the Web Mercator sphere radius

HERE = os.path.dirname(os.path.abspath(__file__))


def lng_to_merc_x(lng):
    return math.radians(lng) * R


def lat_to_merc_y(lat):
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * R


def main():
    poster = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "poster_girls_weekend.png")
    sidecar = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "poster_georef.json")
    out_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "poster_tiles")

    meta = json.load(open(sidecar))
    W = meta["poster"]["width"]
    H = meta["poster"]["height"]
    r = meta["mapRect"]
    b = meta["mapBounds"]

    # 1. Map sub-rectangle corners in Mercator metres.
    mx0 = lng_to_merc_x(b["west"])
    mx1 = lng_to_merc_x(b["east"])
    my_top = lat_to_merc_y(b["north"])
    my_bot = lat_to_merc_y(b["south"])

    # 2. Metres per pixel, derived from the MAP AREA only.
    mppx = (mx1 - mx0) / (r["x1"] - r["x0"])
    mppy = (my_top - my_bot) / (r["y1"] - r["y0"])

    # 3. Linear extrapolation to the poster edges — valid because we are in 3857.
    west_m = mx0 - r["x0"] * mppx
    east_m = mx1 + (W - r["x1"]) * mppx
    north_m = my_top + r["y0"] * mppy
    south_m = my_bot - (H - r["y1"]) * mppy

    print("Poster %d×%d  map rect (%d,%d)-(%d,%d)"
          % (W, H, r["x0"], r["y0"], r["x1"], r["y1"]))
    print("  map area  : %.1f m/px x, %.1f m/px y" % (mppx, mppy))
    print("  poster ext: W %.1f  N %.1f  E %.1f  S %.1f (EPSG:3857 m)"
          % (west_m, north_m, east_m, south_m))

    tif = os.path.join(HERE, "_poster_georef.tif")
    cmd = [
        "gdal_translate", "-of", "GTiff",
        "-a_srs", "EPSG:3857",
        "-a_ullr", str(west_m), str(north_m), str(east_m), str(south_m),
        poster, tif,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    print("  ✅ %s" % tif)

    if os.path.isdir(out_dir):
        import shutil
        shutil.rmtree(out_dir)

    # Native 3857 in, XYZ out — gdal2tiles does no reprojection at all here.
    tiles = subprocess.run(
        ["gdal2tiles.py", "-z", "10-16", "-w", "none", "--xyz",
         "--processes=4", "-r", "lanczos", tif, out_dir],
        capture_output=True, text=True,
    )
    if tiles.returncode != 0:
        print("❌ gdal2tiles failed:\n" + tiles.stderr[-1500:])
        sys.exit(1)

    n = sum(1 for _, _, fs in os.walk(out_dir) for f in fs if f.endswith(".png"))
    print("  ✅ %d tiles -> %s" % (n, out_dir))

    # Emit viewer metadata: full poster extent AND the map rect's true bounds.
    def merc_to_lng(x):
        return math.degrees(x / R)

    def merc_to_lat(y):
        return math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)

    json.dump({
        "posterBounds": {
            "north": merc_to_lat(north_m), "south": merc_to_lat(south_m),
            "east": merc_to_lng(east_m), "west": merc_to_lng(west_m),
        },
        "mapBounds": b,
        "center": {"lat": (b["north"] + b["south"]) / 2,
                   "lng": (b["east"] + b["west"]) / 2},
        "zoom": 12, "maxZoom": 16,
    }, open(os.path.join(HERE, "poster_bounds.json"), "w"), indent=2)
    print("  ✅ poster_bounds.json")


if __name__ == "__main__":
    main()
