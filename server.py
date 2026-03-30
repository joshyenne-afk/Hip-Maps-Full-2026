#!/usr/bin/env python3
"""HipMaps Full dev server with Static Maps proxy and tile generation."""

import http.server
import urllib.request
import urllib.parse
import json
import os
import base64
import subprocess
import shutil
import threading

PORT = 8080

# Track tile generation status
tile_status = {
    "running": False,
    "progress": "",
    "error": None,
    "done": False,
    "tile_count": 0,
    "tile_size": ""
}

class HipMapsHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files + proxy + tile generation endpoints."""

    def do_GET(self):
        if self.path.startswith('/proxy?'):
            self.handle_proxy()
        elif self.path == '/tile-status':
            self.handle_tile_status()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/generate-tiles':
            self.handle_generate_tiles()
        else:
            self.send_error(404, 'Not Found')

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def handle_proxy(self):
        """Fetch an external URL server-side and return it with CORS headers."""
        try:
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            url = params.get('url', [None])[0]

            if not url:
                self.send_error(400, 'Missing url parameter')
                return

            parsed = urllib.parse.urlparse(url)
            if parsed.hostname not in ('maps.googleapis.com', 'maps.google.com'):
                self.send_error(403, 'Only Google Maps URLs are allowed')
                return

            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'HipMaps-Server/1.0')
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                content_type = resp.headers.get('Content-Type', 'image/png')

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'public, max-age=3600')
            self.end_headers()
            self.wfile.write(data)

        except urllib.error.HTTPError as e:
            self.send_error(e.code, f'Upstream error: {e.reason}')
        except Exception as e:
            self.send_error(500, f'Proxy error: {str(e)}')

    def handle_tile_status(self):
        """Return current tile generation status as JSON."""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(tile_status).encode())

    def handle_generate_tiles(self):
        """Accept image + bounds and kick off tile generation."""
        global tile_status

        if tile_status["running"]:
            self.send_response(409)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Tile generation already in progress"}).encode())
            return

        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body)

            image_b64 = data.get('image')
            bounds = data.get('bounds')
            min_zoom = data.get('minZoom', 10)
            max_zoom = data.get('maxZoom', 14)

            if not image_b64 or not bounds:
                self.send_error(400, 'Missing image or bounds')
                return

            if ',' in image_b64:
                image_b64 = image_b64.split(',', 1)[1]

            tile_status = {
                "running": True,
                "progress": "Starting tile generation...",
                "error": None,
                "done": False,
                "tile_count": 0,
                "tile_size": ""
            }

            thread = threading.Thread(
                target=run_tile_generation,
                args=(image_b64, bounds, min_zoom, max_zoom),
                daemon=True
            )
            thread.start()

            self.send_response(202)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started", "poll": "/tile-status"}).encode())

        except Exception as e:
            tile_status["running"] = False
            tile_status["error"] = str(e)
            self.send_error(500, f'Error: {str(e)}')

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()


def run_tile_generation(image_b64, bounds, min_zoom, max_zoom):
    """Run GDAL georeferencing + tile slicing in a background thread."""
    global tile_status

    project_dir = os.path.dirname(os.path.abspath(__file__))
    tiles_dir = os.path.join(project_dir, 'tiles')
    georef_file = os.path.join(project_dir, 'georeferenced.tif')
    tmp_image = os.path.join(project_dir, '_tmp_tile_source.png')

    try:
        tile_status["progress"] = "Decoding image..."
        print("🧩 Tile Gen: Decoding image...")
        image_data = base64.b64decode(image_b64)

        with open(tmp_image, 'wb') as f:
            f.write(image_data)

        image_size_mb = len(image_data) / (1024 * 1024)
        print(f"   Image size: {image_size_mb:.1f} MB")

        tile_status["progress"] = "Georeferencing image with GDAL..."
        print("🧩 Tile Gen: Running gdal_translate...")

        cmd_georef = [
            'gdal_translate', '-of', 'GTiff',
            '-a_ullr', str(bounds['west']), str(bounds['north']),
                       str(bounds['east']), str(bounds['south']),
            '-a_srs', 'EPSG:4326',
            tmp_image, georef_file
        ]

        result = subprocess.run(cmd_georef, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"gdal_translate failed: {result.stderr}")

        print(f"   Created: {georef_file}")

        if os.path.exists(tiles_dir):
            tile_status["progress"] = "Cleaning old tiles..."
            print("🧩 Tile Gen: Cleaning old tiles directory...")
            shutil.rmtree(tiles_dir)

        tile_status["progress"] = f"Generating tiles (zoom {min_zoom}-{max_zoom})... This may take a while."
        print(f"🧩 Tile Gen: Running gdal2tiles.py (zoom {min_zoom}-{max_zoom})...")

        cmd_tiles = [
            'gdal2tiles.py',
            '-z', f'{min_zoom}-{max_zoom}',
            '-w', 'none',
            '--xyz',
            georef_file, tiles_dir
        ]

        result = subprocess.run(cmd_tiles, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"gdal2tiles.py failed: {result.stderr}")

        tile_count = 0
        total_size = 0
        for root, dirs, files in os.walk(tiles_dir):
            for f in files:
                if f.endswith('.png'):
                    tile_count += 1
                total_size += os.path.getsize(os.path.join(root, f))

        if total_size > 1024 * 1024:
            size_str = f"{total_size / (1024*1024):.1f} MB"
        else:
            size_str = f"{total_size / 1024:.0f} KB"

        if os.path.exists(tmp_image):
            os.remove(tmp_image)

        tile_status["running"] = False
        tile_status["done"] = True
        tile_status["progress"] = f"Complete! Generated {tile_count} tiles ({size_str})"
        tile_status["tile_count"] = tile_count
        tile_status["tile_size"] = size_str

        print(f"🧩 Tile Gen: ✅ Done! {tile_count} tiles, {size_str}")
        print(f"   Tiles URL: http://localhost:{PORT}/tiles/{{z}}/{{x}}/{{y}}.png")

    except Exception as e:
        tile_status["running"] = False
        tile_status["error"] = str(e)
        tile_status["progress"] = f"Error: {str(e)}"
        print(f"🧩 Tile Gen: ❌ Error: {e}")

        if os.path.exists(tmp_image):
            os.remove(tmp_image)


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with http.server.HTTPServer(('', PORT), HipMapsHandler) as httpd:
        print(f'🗺️  HipMaps Full 2026 server at http://localhost:{PORT}')
        print(f'   Proxy:  http://localhost:{PORT}/proxy?url=<encoded_url>')
        print(f'   Tiles:  POST http://localhost:{PORT}/generate-tiles')
        print(f'   Status: http://localhost:{PORT}/tile-status')
        httpd.serve_forever()
