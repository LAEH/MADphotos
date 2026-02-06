#!/bin/bash
set -e
cd /Users/laeh/Pictures/MADphotos

echo "=== MADphotos: Full DNG Reprocess ==="
echo "$(date) — Starting render of all DNGs..."

python3 -u render_pipeline.py --workers 6

echo ""
echo "$(date) — Render complete. Running spot check..."
python3 -u << 'PYEOF'
import sqlite3, numpy as np
from PIL import Image

conn = sqlite3.connect('mad_photos.db')
dng_sample = conn.execute("SELECT uuid FROM images WHERE source_format = 'dng' ORDER BY RANDOM() LIMIT 10").fetchall()
bad = 0
for row in dng_sample:
    uuid = row[0]
    path = f"rendered/gemini/jpeg/{uuid}.jpg"
    try:
        img = Image.open(path)
        arr = np.array(img)
        r, g, b = arr[:,:,0].mean(), arr[:,:,1].mean(), arr[:,:,2].mean()
        excess = ((r + b) / 2) - g
        if excess > 15:
            bad += 1
            print(f"  BAD  {uuid[:8]} R={r:.0f} G={g:.0f} B={b:.0f}")
        else:
            print(f"  OK   {uuid[:8]} R={r:.0f} G={g:.0f} B={b:.0f}")
    except Exception as e:
        print(f"  ERR  {uuid[:8]}: {e}")

print(f"\nSpot check: {bad}/10 bad")
if bad > 0:
    print("WARNING: Some DNG renders still have color issues!")
else:
    print("All clear — DNG renders look good.")
PYEOF

echo ""
echo "$(date) — Starting Gemini analysis..."
python3 -u photography_engine.py --concurrent 5 --max-retries 5

echo ""
echo "$(date) — Refreshing gallery data..."
python3 export_gallery_data.py

echo ""
echo "$(date) — All done."
python3 -c "
import sqlite3
conn = sqlite3.connect('mad_photos.db')
imgs = conn.execute('SELECT COUNT(*) FROM images').fetchone()[0]
analyzed = conn.execute(\"SELECT COUNT(*) FROM gemini_analysis WHERE raw_json IS NOT NULL AND raw_json != '' AND error IS NULL\").fetchone()[0]
print(f'  Images: {imgs}')
print(f'  Analyzed: {analyzed}')
"
