#!/usr/bin/env python3
"""HipMaps Full dev server with Static Maps proxy and tile generation."""

import http.server
import urllib.request
import urllib.parse
import json
import os
import re
import base64
import subprocess
import shutil
import threading

PORT = 8080


def _get_gemini_key():
    """Read GEMINI_API_KEY from env var, falling back to parsing config.js."""
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if key:
        return key
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.js')
    if os.path.exists(config_path):
        with open(config_path) as f:
            for line in f:
                m = re.search(r'GEMINI_API_KEY\s*=\s*["\']([^"\']+)["\']', line)
                if m:
                    return m.group(1)
    return None


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

    def end_headers(self):
        """Add CORS + no-cache headers (no-cache only for HTML/JS/CSS during development)."""
        self.send_header('Access-Control-Allow-Origin', '*')
        path = self.path.split('?')[0]
        if path.endswith(('.html', '.js', '.css')):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    def do_POST(self):
        if self.path == '/generate-tiles':
            self.handle_generate_tiles()
        elif self.path == '/scrape':
            self.handle_scrape()
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

    def handle_scrape(self):
        """Fetch any URL and return its text content for AI processing."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            url = data.get('url', '').strip()

            if not url:
                self.send_error(400, 'Missing url')
                return

            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            req.add_header('Accept', 'text/html,application/xhtml+xml,*/*')

            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode('utf-8', errors='ignore')

            # Strip script, style, and nav tags
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
            # Strip all remaining HTML tags
            text = re.sub(r'<[^>]+>', ' ', html)
            # Collapse whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            # Limit to ~30k chars to stay within Gemini context
            text = text[:30000]

            result = json.dumps({'url': url, 'text': text, 'length': len(text)})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(result)))
            self.end_headers()
            self.wfile.write(result.encode())

        except urllib.error.HTTPError as e:
            error = json.dumps({'error': f'HTTP {e.code}: {e.reason}'})
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(error.encode())
        except Exception as e:
            error = json.dumps({'error': str(e)})
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(error.encode())

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
            venues = data.get('venues', [])
            min_zoom = data.get('minZoom', 10)
            max_zoom = data.get('maxZoom', 14)

            if not image_b64 or not bounds:
                self.send_error(400, 'Missing image or bounds')
                return

            if ',' in image_b64:
                image_b64 = image_b64.split(',', 1)[1]

            # Save venues.json directly into public/ so the deploy picks it up (no staging step).
            project_dir = os.path.dirname(os.path.abspath(__file__))
            public_dir = os.path.join(project_dir, 'public')
            os.makedirs(public_dir, exist_ok=True)
            venues_file = os.path.join(public_dir, 'venues.json')
            with open(venues_file, 'w') as vf:
                json.dump(venues, vf, indent=2)
            print(f"📍 Saved {len(venues)} venues to {venues_file}")

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


def png_dimensions(path):
    """Read width/height from a PNG header (no PIL dependency). Returns (w, h) or None."""
    try:
        with open(path, 'rb') as f:
            header = f.read(26)
        if header[:8] != b'\x89PNG\r\n\x1a\n':
            return None
        width = int.from_bytes(header[16:20], 'big')
        height = int.from_bytes(header[20:24], 'big')
        return (width, height)
    except Exception:
        return None


def pick_upscale_factor(input_path, requested=4):
    """Pick an upscale factor based on source resolution.

    Hi-res stitched/AI captures (2K-4K) don't need the full 4x — it just
    creates multi-hundred-MB TIFFs without adding real detail.
    """
    dims = png_dimensions(input_path)
    if not dims:
        return requested
    longest = max(dims)
    if longest >= 4096:
        return 1  # already 4K+: skip upscaling
    if longest >= 2048:
        return 2
    return requested


def upscale_image(input_path, output_path, scale=4):
    """Upscale an image using Upscayl's bundled Real-ESRGAN binary.

    Uses the digital-art-4x model which is optimized for illustrated/stylized content.
    Paths/model are overridable via UPSCAYL_BIN, UPSCAYL_MODELS_DIR, UPSCAYL_MODEL
    environment variables. Falls back gracefully if Upscayl is not installed.
    """
    upscayl_bin = os.environ.get('UPSCAYL_BIN', '/Applications/Upscayl.app/Contents/Resources/bin/upscayl-bin')
    models_dir = os.environ.get('UPSCAYL_MODELS_DIR', '/Applications/Upscayl.app/Contents/Resources/models')
    model_name = os.environ.get('UPSCAYL_MODEL', 'digital-art-4x')

    if not os.path.exists(upscayl_bin):
        print("⚠️  Upscayl not found — skipping upscale, using original image")
        tile_status["progress"] = "⚠️ Upscayl not found — tiling WITHOUT upscale (quality may suffer). Set UPSCAYL_BIN to fix."
        shutil.copy(input_path, output_path)
        return False

    print(f"🔍 Upscaling with {model_name} at {scale}x...")
    cmd = [
        upscayl_bin,
        '-i', input_path,
        '-o', output_path,
        '-s', str(scale),
        '-n', model_name,
        '-m', models_dir,
        '-f', 'png',
        '-v'
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"⚠️  Upscale failed: {result.stderr}")
        tile_status["progress"] = "⚠️ Upscale failed — tiling with the original image (see server log)."
        shutil.copy(input_path, output_path)
        return False

    upscaled_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"   ✅ Upscaled to {upscaled_size:.1f} MB")
    return True


def run_tile_generation(image_b64, bounds, min_zoom, max_zoom):
    """Run upscale + GDAL georeferencing + tile slicing in a background thread."""
    global tile_status

    project_dir = os.path.dirname(os.path.abspath(__file__))
    public_dir = os.path.join(project_dir, 'public')
    os.makedirs(public_dir, exist_ok=True)
    tiles_dir = os.path.join(public_dir, 'tiles')  # write straight into public/ for firebase deploy
    georef_file = os.path.join(project_dir, 'georeferenced.tif')
    tmp_image = os.path.join(project_dir, '_tmp_tile_source.png')
    upscaled_image = os.path.join(project_dir, '_tmp_tile_upscaled.png')

    try:
        tile_status["progress"] = "Decoding image..."
        print("🧩 Tile Gen: Decoding image...")
        image_data = base64.b64decode(image_b64)

        with open(tmp_image, 'wb') as f:
            f.write(image_data)

        image_size_mb = len(image_data) / (1024 * 1024)
        print(f"   Image size: {image_size_mb:.1f} MB")

        # Upscale before tiling — factor adapts to source resolution
        scale_factor = pick_upscale_factor(tmp_image, requested=4)
        if scale_factor > 1:
            tile_status["progress"] = f"Upscaling image {scale_factor}x with Real-ESRGAN..."
            print(f"🧩 Tile Gen: Upscaling image {scale_factor}x...")
            upscaled = upscale_image(tmp_image, upscaled_image, scale=scale_factor)
        else:
            print("🧩 Tile Gen: Source is already 4K+ — skipping upscale")
            upscaled = False

        # Use upscaled image for tiling if available, otherwise original
        tile_source = upscaled_image if upscaled and os.path.exists(upscaled_image) else tmp_image
        if upscaled:
            print(f"   Using {scale_factor}x upscaled image for tile generation")
        else:
            print("   Using original image for tile generation")

        tile_status["progress"] = "Georeferencing image with GDAL..."
        print("🧩 Tile Gen: Running gdal_translate...")

        cmd_georef = [
            'gdal_translate', '-of', 'GTiff',
            '-a_ullr', str(bounds['west']), str(bounds['north']),
                       str(bounds['east']), str(bounds['south']),
            '-a_srs', 'EPSG:4326',
            tile_source, georef_file
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
            '--processes=4',
            '-r', 'lanczos',
            georef_file, tiles_dir
        ]

        result = subprocess.run(cmd_tiles, capture_output=True, text=True, timeout=900)
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

        # Save bounds metadata into public/ for the viewer
        bounds_meta = {
            "north": bounds['north'],
            "south": bounds['south'],
            "east": bounds['east'],
            "west": bounds['west'],
            "center": {
                "lat": (bounds['north'] + bounds['south']) / 2,
                "lng": (bounds['east'] + bounds['west']) / 2
            },
            "zoom": min_zoom,
            "maxZoom": max_zoom
        }
        bounds_file = os.path.join(public_dir, 'bounds.json')
        with open(bounds_file, 'w') as bf:
            json.dump(bounds_meta, bf, indent=2)
        print(f"   Saved: {bounds_file}")

        # Clean up temp files
        for tmp in (tmp_image, upscaled_image):
            if os.path.exists(tmp):
                os.remove(tmp)

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

        for tmp in (tmp_image, upscaled_image):
            if os.path.exists(tmp):
                os.remove(tmp)


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with http.server.HTTPServer(('', PORT), HipMapsHandler) as httpd:
        print(f'🗺️  HipMaps Full 2026 server at http://localhost:{PORT}')
        print(f'   Proxy:  http://localhost:{PORT}/proxy?url=<encoded_url>')
        print(f'   Scrape: POST http://localhost:{PORT}/scrape')
        print(f'   Tiles:  POST http://localhost:{PORT}/generate-tiles')
        print(f'   Status: http://localhost:{PORT}/tile-status')
        httpd.serve_forever()
