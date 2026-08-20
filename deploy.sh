#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# HipMaps Deploy — Package tiles + viewer + venues for Firebase Hosting
# Usage: ./deploy.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PUBLIC_DIR="$PROJECT_DIR/public"
TILES_DIR="$PROJECT_DIR/tiles"

echo "🗺️  HipMaps Deploy"
echo "   Project: $PROJECT_DIR"
echo ""

# server.py now writes tiles/venues.json/bounds.json directly into public/.
# This script just verifies + ships config.js + deploys.

# 1. Verify tiles exist in public/
if [ ! -d "$PUBLIC_DIR/tiles" ] || [ -z "$(ls -A "$PUBLIC_DIR/tiles" 2>/dev/null)" ]; then
    echo "❌ No tiles in $PUBLIC_DIR/tiles"
    echo "   Run 'Generate Tile Layer' in Studio first."
    exit 1
fi
TILE_COUNT=$(find "$PUBLIC_DIR/tiles" -name "*.png" | wc -l | tr -d ' ')
echo "   ✅ $TILE_COUNT tiles found"

# 2. Inject config.js (gitignored — never lives in public/ between deploys).
#    GEMINI_API_KEY is stripped: the deployed viewer never references it, and
#    anything in public/ is served publicly by Firebase Hosting. Only the
#    referrer-restricted Maps key ships.
echo "📦 Copying config.js (stripping GEMINI_API_KEY)..."
sed '/GEMINI_API_KEY/d' "$PROJECT_DIR/config.js" > "$PUBLIC_DIR/config.js"

if ! grep -q 'GOOGLE_API_KEY' "$PUBLIC_DIR/config.js"; then
    echo "❌ public/config.js has no GOOGLE_API_KEY — the map would not load."
    exit 1
fi
if grep -q 'GEMINI_API_KEY' "$PUBLIC_DIR/config.js"; then
    echo "❌ GEMINI_API_KEY survived the strip — refusing to deploy."
    exit 1
fi
echo "   ✅ Maps key only"

# 3. Sanity check venues.json + bounds.json
[ -f "$PUBLIC_DIR/venues.json" ] || echo "[]" > "$PUBLIC_DIR/venues.json"
if [ ! -f "$PUBLIC_DIR/bounds.json" ]; then
    echo "   ⚠️  No bounds.json — viewer will use default center."
fi

# 4. Count total size
TOTAL_SIZE=$(du -sh "$PUBLIC_DIR" | cut -f1)
echo ""
echo "📊 Package ready:"
echo "   Directory: $PUBLIC_DIR"
echo "   Total size: $TOTAL_SIZE"
echo "   Tiles: $TILE_COUNT"
echo ""

# 7. Deploy to Firebase Hosting
echo "🚀 Deploying to Firebase Hosting..."
cd "$PROJECT_DIR"
export PATH="/opt/homebrew/bin:$PATH"
firebase deploy --only hosting --project hipmaps-2026

echo ""
echo "✅ Deployed! Your map is live."
echo "   Open on your phone to see the interactive map with styled tiles."
