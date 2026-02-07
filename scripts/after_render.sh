#!/bin/bash
# after_render.sh — Wait for render pipeline to finish, then run Gemini analysis
# This script monitors the render process and kicks off analysis once complete.

set -e

PROJ="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== MADphotos: Post-Render Pipeline ==="
echo "Waiting for render.py to finish..."

# Wait for render to complete
while pgrep -f "render.py" > /dev/null 2>&1; do
    # Show progress every 30 seconds
    COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$PROJ/images/mad_photos.db')
n = conn.execute('SELECT COUNT(*) FROM images').fetchone()[0]
print(n)
")
    echo "  $(date '+%H:%M') — $COUNT images registered..."
    sleep 30
done

echo ""
echo "Render complete. Final state:"
python3 -c "
import sqlite3
conn = sqlite3.connect('$PROJ/images/mad_photos.db')
imgs = conn.execute('SELECT COUNT(*) FROM images').fetchone()[0]
tiers = conn.execute('SELECT COUNT(DISTINCT image_uuid) FROM tiers WHERE variant_id IS NULL').fetchone()[0]
analyzed = conn.execute(\"SELECT COUNT(*) FROM gemini_analysis WHERE raw_json IS NOT NULL AND raw_json != '' AND error IS NULL\").fetchone()[0]
print(f'  Images: {imgs}')
print(f'  With tiers: {tiers}')
print(f'  Analyzed: {analyzed}')
print(f'  Need analysis: {imgs - analyzed}')
"

echo ""
echo "=== Starting Gemini Analysis ==="
echo "Running gemini.py with concurrency 5..."
python3 -u "$PROJ/backend/gemini.py" --concurrent 5 --max-retries 5

echo ""
echo "=== Analysis Complete ==="
python3 -c "
import sqlite3
conn = sqlite3.connect('$PROJ/images/mad_photos.db')
analyzed = conn.execute(\"SELECT COUNT(*) FROM gemini_analysis WHERE raw_json IS NOT NULL AND raw_json != '' AND error IS NULL\").fetchone()[0]
errors = conn.execute('SELECT COUNT(*) FROM gemini_analysis WHERE error IS NOT NULL').fetchone()[0]
print(f'  Analyzed OK: {analyzed}')
print(f'  Errors: {errors}')
"

echo ""
echo "=== Refreshing Gallery Data ==="
python3 "$PROJ/backend/export_gallery.py"
echo ""
echo "Done. Gallery data updated with all analyzed photos."
