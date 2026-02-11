#!/usr/bin/env python3
"""Run Gemma 3 4B vision (via Ollama) on picked photos for rich analysis.

Sends each curated photo to the local Gemma 3 4B model for deep descriptive
analysis: description, subject, story, composition, lighting, colors, texture,
mood, technical assessment, strength, tags, and print-worthiness.

Results stored in `gemma_picks` table in mad_photos.db and exported to
frontend/show/data/gemma_picks.json.

Usage:
  python3 backend/run_gemma_picks.py              # all pending picks
  python3 backend/run_gemma_picks.py --limit 10   # first 10 (for testing)
  python3 backend/run_gemma_picks.py --rerun       # reprocess all (overwrite)
"""
from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
PICKS_JSON = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"
OUTPUT_JSON = PROJECT_ROOT / "frontend" / "show" / "data" / "gemma_picks.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:4b"
FLUSH_SIZE = 25

PROMPT = (
    "You are an expert photography critic. Analyze this photograph in detail. "
    "Respond ONLY with valid JSON, no markdown, no backticks:\n"
    '{"description":"2-3 sentence vivid description of what this photograph shows",'
    '"subject":"primary subject(s) of the photograph",'
    '"story":"what moment, narrative, or feeling this image captures",'
    '"composition":"how the frame is arranged — technique, balance, eye flow",'
    '"lighting":"quality, direction, and character of the light",'
    '"colors":"dominant colors and their relationships described naturally",'
    '"texture":"visible textures, materials, surfaces",'
    '"mood":"emotional atmosphere in 2-3 words",'
    '"technical":"assessment of exposure, focus, depth of field, sharpness",'
    '"strength":"what makes this a strong photograph",'
    '"tags":["up to 15 descriptive tags"],'
    '"print_worthy":true or false}'
)


def init_table(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gemma_picks (
            uuid             TEXT PRIMARY KEY,
            gemma_json       TEXT NOT NULL,
            gemma_description TEXT,
            gemma_mood       TEXT,
            gemma_tags       TEXT,
            print_worthy     INTEGER,
            processed_at     TEXT NOT NULL
        );
    """)


def load_pick_uuids() -> list[str]:
    data = json.loads(PICKS_JSON.read_text())
    uuids = list(dict.fromkeys(data["portrait"] + data["landscape"]))
    return uuids


def get_mobile_paths(conn: sqlite3.Connection, uuids: list[str]) -> dict[str, str]:
    """Map UUIDs to their mobile JPEG local paths from the tiers table."""
    paths = {}
    # Query in batches of 500 to avoid SQL variable limits
    for i in range(0, len(uuids), 500):
        batch = uuids[i:i + 500]
        placeholders = ",".join(["?"] * len(batch))
        rows = conn.execute(
            f"SELECT image_uuid, local_path FROM tiers "
            f"WHERE tier_name='mobile' AND format='jpeg' "
            f"AND image_uuid IN ({placeholders})",
            batch,
        ).fetchall()
        for uuid, path in rows:
            paths[uuid] = path
    return paths


def get_processed(conn: sqlite3.Connection) -> set[str]:
    try:
        return {row[0] for row in conn.execute("SELECT uuid FROM gemma_picks").fetchall()}
    except sqlite3.OperationalError:
        return set()


def query_gemma(img_path: str) -> dict | None:
    """Send image to Gemma 3 via Ollama and parse JSON response."""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = json.dumps({
        "model": MODEL,
        "prompt": PROMPT,
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 800},
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=180)
    result = json.loads(resp.read())
    text = result.get("response", "")

    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _to_str(val, fallback: str = "") -> str:
    """Coerce any Gemma output value to a plain string for sqlite."""
    if val is None:
        return fallback
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


def flush_batch(conn: sqlite3.Connection, batch: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for row in batch:
        parsed = row["parsed"]
        tags = parsed.get("tags", [])
        if isinstance(tags, list):
            tags_str = ", ".join(str(t).lower().strip() for t in tags)
        else:
            tags_str = str(tags).lower()

        print_worthy = parsed.get("print_worthy")
        if isinstance(print_worthy, bool):
            print_worthy = 1 if print_worthy else 0
        elif isinstance(print_worthy, str):
            print_worthy = 1 if print_worthy.lower() == "true" else 0
        elif isinstance(print_worthy, (int, float)):
            print_worthy = 1 if print_worthy else 0
        else:
            print_worthy = None

        # Coerce description/mood to str — Gemma sometimes returns lists or dicts
        description = _to_str(
            parsed.get("description", parsed.get("raw", "")))
        mood = _to_str(parsed.get("mood", ""))

        conn.execute("""
            INSERT INTO gemma_picks (uuid, gemma_json, gemma_description, gemma_mood, gemma_tags, print_worthy, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uuid) DO UPDATE SET
                gemma_json = excluded.gemma_json,
                gemma_description = excluded.gemma_description,
                gemma_mood = excluded.gemma_mood,
                gemma_tags = excluded.gemma_tags,
                print_worthy = excluded.print_worthy,
                processed_at = excluded.processed_at
        """, (
            row["uuid"],
            json.dumps(parsed, ensure_ascii=False),
            description,
            mood,
            tags_str,
            print_worthy,
            now,
        ))
    conn.commit()


def export_json(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT uuid, gemma_json FROM gemma_picks").fetchall()
    result = {}
    for uuid, gemma_json in rows:
        try:
            result[uuid] = json.loads(gemma_json)
        except (json.JSONDecodeError, TypeError):
            result[uuid] = {"raw": gemma_json}

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return len(result)


def process_one(uuid: str, img_path: str) -> dict | None:
    """Process a single image. Returns result dict or None on error."""
    if not Path(img_path).exists():
        return {"uuid": uuid, "error": f"file not found — {img_path}"}
    try:
        parsed = query_gemma(img_path)
        if parsed is None:
            raise ValueError("Empty response")
        return {"uuid": uuid, "parsed": parsed}
    except Exception as e:
        return {"uuid": uuid, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Run Gemma 3 4B on picked photos")
    parser.add_argument("--limit", type=int, help="Max images to process")
    parser.add_argument("--rerun", action="store_true", help="Reprocess all (overwrite existing)")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers (default 1)")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")
    init_table(conn)

    # Load picks and resolve paths
    all_uuids = load_pick_uuids()
    paths = get_mobile_paths(conn, all_uuids)
    print(f"Picks: {len(all_uuids)} UUIDs, {len(paths)} have mobile JPEGs")

    # Filter to pending
    if args.rerun:
        pending_uuids = [u for u in all_uuids if u in paths]
    else:
        already = get_processed(conn)
        pending_uuids = [u for u in all_uuids if u in paths and u not in already]
        print(f"Already processed: {len(already)}, pending: {len(pending_uuids)}")

    if args.limit:
        pending_uuids = pending_uuids[:args.limit]

    if not pending_uuids:
        print("Nothing to do.")
        exported = export_json(conn)
        print(f"Exported {exported} results to gemma_picks.json")
        conn.close()
        return

    workers = max(1, args.workers)
    print(f"Processing {len(pending_uuids)} images with {MODEL} ({workers} workers)...")
    t0 = time.time()
    errors = 0
    error_msgs = []
    batch = []
    db_lock = threading.Lock()

    bar = tqdm(total=len(pending_uuids), desc="gemma")

    def flush_locked(b):
        with db_lock:
            flush_batch(conn, b)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(process_one, uuid, paths[uuid]): uuid
            for uuid in pending_uuids
        }
        for future in as_completed(futures):
            result = future.result()
            bar.update(1)

            if "error" in result:
                errors += 1
                if len(error_msgs) < 10:
                    error_msgs.append(f"{result['uuid']}: {result['error']}")
                continue

            batch.append(result)
            if len(batch) >= FLUSH_SIZE:
                flush_locked(list(batch))
                batch.clear()

    bar.close()

    if batch:
        flush_batch(conn, batch)

    elapsed = time.time() - t0
    processed = len(pending_uuids) - errors

    # Export results
    exported = export_json(conn)

    conn.close()

    # Summary
    print(f"\nDone in {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"  Processed: {processed:,}")
    print(f"  Errors:    {errors:,}")
    print(f"  Exported:  {exported:,} → gemma_picks.json")
    if processed > 0:
        print(f"  Avg time:  {elapsed / processed:.1f}s per image")

    if error_msgs:
        print(f"\nFirst {len(error_msgs)} errors:")
        for msg in error_msgs:
            print(f"  {msg}")


if __name__ == "__main__":
    main()
