#!/usr/bin/env python3
"""
Standalone Florence-2 caption worker.

Runs as an independent process, handling a slice of pending images.
Multiple workers can run in parallel — each takes every Nth image.

Usage:
    python _florence_worker.py --worker 0 --total-workers 3
    python _florence_worker.py --worker 1 --total-workers 3
    python _florence_worker.py --worker 2 --total-workers 3
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

import torch
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
DISPLAY_DIR = PROJECT_ROOT / "images" / "rendered" / "display" / "jpeg"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS florence_captions (
    image_uuid      TEXT PRIMARY KEY,
    short_caption   TEXT,
    detailed_caption TEXT,
    more_detailed   TEXT,
    model           TEXT DEFAULT 'florence-2-base',
    analyzed_at     TEXT NOT NULL
);
"""

UPSERT_SQL = """
INSERT INTO florence_captions
    (image_uuid, short_caption, detailed_caption, more_detailed, model, analyzed_at)
VALUES (?, ?, ?, ?, 'florence-2-base', ?)
ON CONFLICT(image_uuid) DO UPDATE SET
    short_caption=excluded.short_caption,
    detailed_caption=excluded.detailed_caption,
    more_detailed=excluded.more_detailed,
    analyzed_at=excluded.analyzed_at;
"""

PENDING_SQL = """
SELECT i.uuid
FROM images i
JOIN tiers t ON t.image_uuid = i.uuid
    AND t.tier_name = 'display'
    AND t.format = 'jpeg'
    AND t.variant_id IS NULL
WHERE NOT EXISTS (
    SELECT 1 FROM florence_captions fc WHERE fc.image_uuid = i.uuid
)
ORDER BY i.uuid;
"""


def main():
    parser = argparse.ArgumentParser(description="Florence-2 caption worker")
    parser.add_argument("--worker", type=int, required=True, help="Worker index (0-based)")
    parser.add_argument("--total-workers", type=int, required=True, help="Total number of workers")
    parser.add_argument("--device", default="mps", help="Device: mps or cpu")
    args = parser.parse_args()

    worker_id = args.worker
    total_workers = args.total_workers
    device = args.device

    print(f"Worker {worker_id}/{total_workers} — device={device}")
    print(f"DB: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()

    # Get all pending UUIDs, take every Nth one
    all_uuids = [r[0] for r in conn.execute(PENDING_SQL).fetchall()]
    my_uuids = [u for i, u in enumerate(all_uuids) if i % total_workers == worker_id]

    total = len(my_uuids)
    print(f"Pending total: {len(all_uuids)}, this worker: {total}")

    if total == 0:
        print("Nothing to do.")
        conn.close()
        return

    # Load model
    print(f"Loading Florence-2-base on {device}...")
    from transformers import AutoProcessor, AutoModelForCausalLM

    processor = AutoProcessor.from_pretrained(
        "microsoft/Florence-2-base", trust_remote_code=True
    )
    model = AutoModelForCausalLM.from_pretrained(
        "microsoft/Florence-2-base", trust_remote_code=True,
        torch_dtype=torch.float32, attn_implementation="eager"
    ).to(device).eval()
    print("Model ready.\n")

    def caption(img, task_prompt):
        inputs = processor(text=task_prompt, images=img, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            generated = model.generate(
                **inputs, max_new_tokens=256, num_beams=1, use_cache=False
            )
        result = processor.batch_decode(generated, skip_special_tokens=False)[0]
        parsed = processor.post_process_generation(
            result, task=task_prompt, image_size=(img.width, img.height)
        )
        return parsed.get(task_prompt, "")

    t0 = time.time()
    done = 0
    errors = 0
    batch = []  # accumulate results in memory, flush to DB periodically
    FLUSH_SIZE = 50

    def flush_batch():
        """Write accumulated results to DB in one short transaction."""
        if not batch:
            return
        for attempt in range(10):
            try:
                conn.executemany(UPSERT_SQL, batch)
                conn.commit()
                batch.clear()
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < 9:
                    time.sleep(0.5 + attempt * 0.5)
                else:
                    raise

    for i, uuid in enumerate(my_uuids):
        img_path = DISPLAY_DIR / f"{uuid}.jpg"
        if not img_path.exists():
            errors += 1
            continue

        try:
            img = Image.open(img_path).convert("RGB")
            w, h = img.size
            scale = min(1.0, 384.0 / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            short = caption(img, "<CAPTION>")
            detailed = caption(img, "<DETAILED_CAPTION>")
            more = caption(img, "<MORE_DETAILED_CAPTION>")

            now = datetime.now(timezone.utc).isoformat()
            batch.append((uuid, short, detailed, more, now))
            done += 1

        except Exception as e:
            print(f"  ERROR {uuid[:8]}: {e}", file=sys.stderr)
            errors += 1

        # Flush batch + progress
        if len(batch) >= FLUSH_SIZE or (i + 1) == total:
            flush_batch()
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (total - i - 1) / rate if rate > 0 else 0
            print(f"  W{worker_id}: {i+1}/{total} done={done} err={errors} {rate:.2f}/s ~{remaining:.0f}s")

    flush_batch()
    conn.close()

    elapsed = time.time() - t0
    rate = done / elapsed if elapsed > 0 else 0
    print(f"\nW{worker_id} finished: {done} captions, {errors} errors, {rate:.2f}/s, {elapsed:.0f}s")


if __name__ == "__main__":
    main()
