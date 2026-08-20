import math

def latlng_to_world(lat, lng):
    siny = math.sin(math.radians(lat))
    siny = min(max(siny, -0.9999), 0.9999)
    x = 256 * (0.5 + lng / 360)
    y = 256 * (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi))
    return x, y

def world_to_latlng(x, y):
    lng = (x / 256 - 0.5) * 360
    n = math.pi - 2 * math.pi * y / 256
    lat = math.degrees(math.atan(math.sinh(n)))
    return lat, lng

clat = 38.30
clng = -122.47
zoom = 13
scale = 1 << zoom

cx, cy = latlng_to_world(clat, clng)

# 640x640 pixels at zoom 13
width_px = 640
height_px = 640

# The world coordinates correspond to pixels at zoom 0.
# At zoom 13, world coords are multiplied by 2^13.
# So delta world = delta_px / 2^13
wx_west = cx - (width_px/2) / scale
wx_east = cx + (width_px/2) / scale
wy_north = cy - (height_px/2) / scale
wy_south = cy + (height_px/2) / scale

n_lat, w_lng = world_to_latlng(wx_west, wy_north)
s_lat, e_lng = world_to_latlng(wx_east, wy_south)

print(f"West: {w_lng}")
print(f"North: {n_lat}")
print(f"East: {e_lng}")
print(f"South: {s_lat}")
