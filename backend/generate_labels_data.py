#!/usr/bin/env python3
"""
Generate labels data for WIP view: camera info + top 4 unified labels per photo.
Output: frontend/show/data/photo_labels.json
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
OUTPUT_PATH = PROJECT_ROOT / "frontend" / "show" / "data" / "photo_labels.json"

def generate_labels_data():
    """Generate labels data with camera + top 4 unified labels for each photo."""
    conn = sqlite3.connect(str(DB_PATH))

    # Get all photos with their camera info
    photos_data = {}

    for row in conn.execute("""
        SELECT uuid, camera_body, film_stock, medium
        FROM images
        ORDER BY uuid
    """).fetchall():
        uuid, camera_body, film_stock, medium = row

        # Build camera label
        camera_label = None
        if camera_body:
            if film_stock:
                camera_label = f"{camera_body} • {film_stock}"
            else:
                camera_label = camera_body

        # Get top 4 labels by confidence
        top_labels = []
        for label_row in conn.execute("""
            SELECT label, category, confidence
            FROM unified_labels
            WHERE image_uuid = ?
            ORDER BY confidence DESC
            LIMIT 4
        """, (uuid,)).fetchall():
            top_labels.append({
                "label": label_row[0],
                "category": label_row[1],
                "confidence": label_row[2]
            })

        # Only include photos that have either camera or labels
        if camera_label or top_labels:
            photos_data[uuid] = {
                "camera": camera_label,
                "labels": top_labels
            }

    conn.close()

    # Write to JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(photos_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Generated labels data for {len(photos_data)} photos")
    print(f"   → {OUTPUT_PATH}")

    # Show sample
    sample_uuid = list(photos_data.keys())[0] if photos_data else None
    if sample_uuid:
        sample = photos_data[sample_uuid]
        print(f"\nSample ({sample_uuid[:8]}):")
        print(f"  Camera: {sample.get('camera')}")
        print(f"  Labels: {[l['label'] for l in sample['labels']]}")

if __name__ == "__main__":
    generate_labels_data()
