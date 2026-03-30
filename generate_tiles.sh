#!/bin/bash
# HipMaps Tile Generator
# Uses GDAL to georeference an image and generate map tiles
#
# Usage: ./generate_tiles.sh <image_file> <bounds_json> [min_zoom] [max_zoom]
#
# Example: ./generate_tiles.sh artistic_map.png hipmaps_georef_bounds.json 10 14

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check arguments
if [ $# -lt 2 ]; then
    echo -e "${YELLOW}Usage:${NC} $0 <image_file> <bounds_json> [min_zoom] [max_zoom]"
    echo ""
    echo "Arguments:"
    echo "  image_file   - Your artistic map image (PNG, JPG, etc.)"
    echo "  bounds_json  - JSON file exported from HipMaps Aligner"
    echo "  min_zoom     - Minimum zoom level (default: 10)"
    echo "  max_zoom     - Maximum zoom level (default: 14)"
    echo ""
    echo "Example:"
    echo "  ./generate_tiles.sh my_map.png hipmaps_georef_bounds.json 10 14"
    exit 1
fi

IMAGE_FILE="$1"
BOUNDS_JSON="$2"
MIN_ZOOM="${3:-10}"
MAX_ZOOM="${4:-14}"

# Check if files exist
if [ ! -f "$IMAGE_FILE" ]; then
    echo -e "${RED}Error:${NC} Image file '$IMAGE_FILE' not found"
    exit 1
fi

if [ ! -f "$BOUNDS_JSON" ]; then
    echo -e "${RED}Error:${NC} Bounds JSON file '$BOUNDS_JSON' not found"
    exit 1
fi

# Check if GDAL is installed
if ! command -v gdal_translate &> /dev/null; then
    echo -e "${RED}Error:${NC} GDAL is not installed"
    echo "Install with: brew install gdal"
    exit 1
fi

if ! command -v gdal2tiles.py &> /dev/null; then
    echo -e "${RED}Error:${NC} gdal2tiles.py not found"
    echo "Install with: brew install gdal"
    exit 1
fi

echo -e "${GREEN}HipMaps Tile Generator${NC}"
echo "========================"

# Parse bounds from JSON
echo -e "${YELLOW}Reading bounds from $BOUNDS_JSON...${NC}"

# Read all bounds in one go to be efficient and secure
BOUNDS=$(python3 -c "import json, sys; b=json.load(open(sys.argv[1]))['bounds']; print(f\"{b['north']} {b['south']} {b['east']} {b['west']}\")" "$BOUNDS_JSON")

NORTH=$(echo $BOUNDS | cut -d' ' -f1)
SOUTH=$(echo $BOUNDS | cut -d' ' -f2)
EAST=$(echo $BOUNDS | cut -d' ' -f3)
WEST=$(echo $BOUNDS | cut -d' ' -f4)

echo "  North: $NORTH"
echo "  South: $SOUTH"
echo "  East:  $EAST"
echo "  West:  $WEST"

# Create output directory
OUTPUT_DIR="./tiles"
GEOREF_FILE="./georeferenced.tif"

# Step 1: Georeference the image
echo ""
echo -e "${YELLOW}Step 1: Georeferencing image...${NC}"
gdal_translate -of GTiff \
    -a_ullr "$WEST" "$NORTH" "$EAST" "$SOUTH" \
    -a_srs EPSG:4326 \
    "$IMAGE_FILE" "$GEOREF_FILE"

echo -e "${GREEN}Created:${NC} $GEOREF_FILE"

# Step 2: Generate tiles
echo ""
echo -e "${YELLOW}Step 2: Generating tiles (zoom $MIN_ZOOM-$MAX_ZOOM)...${NC}"
gdal2tiles.py -z "$MIN_ZOOM-$MAX_ZOOM" -w none --xyz "$GEOREF_FILE" "$OUTPUT_DIR"

# Count tiles
TILE_COUNT=$(find "$OUTPUT_DIR" -name "*.png" | wc -l | tr -d ' ')
TILE_SIZE=$(du -sh "$OUTPUT_DIR" | cut -f1)

echo ""
echo -e "${GREEN}Done!${NC}"
echo "========================"
echo "Generated: $TILE_COUNT tiles"
echo "Total size: $TILE_SIZE"
echo "Output folder: $OUTPUT_DIR"
echo ""
echo "To view your tiles, open viewer.html in your browser"
echo "Tiles URL pattern: http://localhost:8080/tiles/{z}/{x}/{y}.png"
