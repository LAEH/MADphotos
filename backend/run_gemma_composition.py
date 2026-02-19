#!/usr/bin/env python3
"""
Extract composition signals from Gemma for Bento/grid layout optimization.

Signals per photo:
  - visual_weight (1-10): how heavy/dominant vs airy/light
  - energy_direction: where visual energy flows
  - archetype: visual category for smart pairing
  - ideal_ratio: best crop ratio from fixed set, respecting orientation
  - color_temp: one-word color temperature feel

Usage:
    .venv-gen/bin/python3 backend/run_gemma_composition.py
    .venv-gen/bin/python3 backend/run_gemma_composition.py --workers 6
    .venv-gen/bin/python3 backend/run_gemma_composition.py --rerun
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
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
PICKS_JSON = PROJECT_ROOT / "frontend" / "show" / "public" / "data" / "picks.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:27b"

FLUSH_SIZE = 20

# The prompt asks Gemma for composition signals with constrained enums
PROMPT = (
    "Analyze this photograph for grid layout composition. "
    "Respond ONLY with valid JSON, no markdown, no backticks.\n\n"
    "{\n"
    '  "visual_weight": 1-10,\n'
    '  "energy_direction": "left_to_right|right_to_left|up|down|center_out|inward|diagonal_down|diagonal_up|static",\n'
    '  "archetype": "portal|horizon|texture|figure|geometry|void|cluster|reflection|silhouette|panorama",\n'
    '  "ideal_ratio": "RATIO",\n'
    '  "color_temp": "glacial|cool|neutral|warm|molten|electric|neon|muted|monochrome"\n'
    "}\n\n"
    "RULES:\n"
    "- visual_weight: 1=very airy/light/spacious, 10=very heavy/dark/dense/dominant. "
    "Consider darkness, density of content, visual mass.\n"
    "- energy_direction: where does the eye travel? The dominant flow of lines, gaze, or movement.\n"
    "- archetype: the visual category.\n"
    "  portal=looking through something (door, window, arch)\n"
    "  horizon=wide landscape with horizon line\n"
    "  texture=close-up surface or pattern\n"
    "  figure=human form or animal as subject\n"
    "  geometry=architectural lines, built structures\n"
    "  void=negative space dominant, minimal\n"
    "  cluster=group of objects or people\n"
    "  reflection=mirror, water reflection, glass\n"
    "  silhouette=backlit form against light\n"
    "  panorama=sweeping wide vista\n"
    "- ideal_ratio: ORIENTATION_PLACEHOLDER\n"
    "- color_temp: one word for the overall color feel of the image.\n"
)

PROMPT_LANDSCAPE = PROMPT.replace(
    "ORIENTATION_PLACEHOLDER",
    "This is a LANDSCAPE photo. Pick the best crop from: "
    '"2:1" (ultra-wide cinematic), "3:2" (classic photo), "4:3" (standard), "1:1" (square). '
    "Choose the ratio that best frames the subject without losing important content."
)

PROMPT_PORTRAIT = PROMPT.replace(
    "ORIENTATION_PLACEHOLDER",
    "This is a PORTRAIT photo. Pick the best crop from: "
    '"1:2" (tall narrow), "2:3" (classic portrait), "3:4" (standard tall), "1:1" (square). '
    "Choose the ratio that best frames the subject without losing important content."
)


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gemma_composition (
            image_uuid          TEXT PRIMARY KEY,
            raw_json            TEXT NOT NULL,
            visual_weight       INTEGER,
            energy_direction    TEXT,
            archetype           TEXT,
            ideal_ratio         TEXT,
            color_temp          TEXT,
            orientation         TEXT,
            processed_at        TEXT NOT NULL
        )
    """)
    conn.commit()


def load_pick_uuids() -> list[str]:
    data = json.loads(PICKS_JSON.read_text())
    return list(dict.fromkeys(data.get("portrait", []) + data.get("landscape", [])))


def load_orientations(conn: sqlite3.Connection, uuids: list[str]) -> dict[str, str]:
    """Determine landscape vs portrait from picks.json."""
    data = json.loads(PICKS_JSON.read_text())
    portrait_set = set(data.get("portrait", []))
    landscape_set = set(data.get("landscape", []))
    result = {}
    for uid in uuids:
        if uid in portrait_set:
            result[uid] = "portrait"
        elif uid in landscape_set:
            result[uid] = "landscape"
        else:
            result[uid] = "landscape"  # default
    return result


def get_mobile_paths(conn: sqlite3.Connection, uuids: list[str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for i in range(0, len(uuids), 500):
        batch = uuids[i:i + 500]
        ph = ",".join(["?"] * len(batch))
        rows = conn.execute(
            f"SELECT image_uuid, MIN(local_path) FROM tiers "
            f"WHERE tier_name='mobile' AND format='jpeg' AND variant_id IS NULL "
            f"AND image_uuid IN ({ph}) GROUP BY image_uuid",
            batch,
        ).fetchall()
        for uid, path in rows:
            paths[uid] = path
    return paths


def query_gemma(img_path: str, orientation: str, model: str) -> dict | None:
    prompt = PROMPT_LANDSCAPE if orientation == "landscape" else PROMPT_PORTRAIT

    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 500},
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=180)
        result = json.loads(resp.read())
        text = result.get("response", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"  Gemma error: {e}")
        return None


def process_one(uid: str, img_path: str, orientation: str, model: str) -> dict | None:
    if not Path(img_path).exists():
        return None
    parsed = query_gemma(img_path, orientation, model)
    if not parsed:
        return None
    return {"uuid": uid, "parsed": parsed, "orientation": orientation}


def _to_int(val, default: int = 0) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, (float,)):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            return default
    return default


def _to_str(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def flush_batch(conn: sqlite3.Connection, batch: list[dict]) -> None:
    for row in batch:
        p = row["parsed"]
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn.execute(
            """INSERT INTO gemma_composition
               (image_uuid, raw_json, visual_weight, energy_direction,
                archetype, ideal_ratio, color_temp, orientation, processed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(image_uuid) DO UPDATE SET
                 raw_json=excluded.raw_json,
                 visual_weight=excluded.visual_weight,
                 energy_direction=excluded.energy_direction,
                 archetype=excluded.archetype,
                 ideal_ratio=excluded.ideal_ratio,
                 color_temp=excluded.color_temp,
                 orientation=excluded.orientation,
                 processed_at=excluded.processed_at
            """,
            (
                row["uuid"],
                json.dumps(p, ensure_ascii=False),
                _to_int(p.get("visual_weight")),
                _to_str(p.get("energy_direction")),
                _to_str(p.get("archetype")),
                _to_str(p.get("ideal_ratio")),
                _to_str(p.get("color_temp")),
                row["orientation"],
                now,
            ),
        )
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract composition signals via Gemma")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--model", type=str, default=MODEL)
    parser.add_argument("--rerun", action="store_true", help="Reprocess all")
    parser.add_argument("--limit", type=int, default=0, help="Max photos to process")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_table(conn)

    uuids = load_pick_uuids()
    orientations = load_orientations(conn, uuids)
    paths = get_mobile_paths(conn, uuids)

    if not args.rerun:
        done = {r[0] for r in conn.execute("SELECT image_uuid FROM gemma_composition").fetchall()}
        pending = [u for u in uuids if u not in done and u in paths]
    else:
        pending = [u for u in uuids if u in paths]

    if args.limit > 0:
        pending = pending[:args.limit]

    print(f"Gemma Composition Signals")
    print(f"  Model: {args.model}")
    print(f"  Workers: {args.workers}")
    print(f"  Total picks: {len(uuids)}")
    print(f"  Have paths: {len(paths)}")
    print(f"  Pending: {len(pending)}")
    print()

    if not pending:
        print("Nothing to process.")
        return

    db_lock = threading.Lock()
    batch: list[dict] = []
    done_count = 0
    fail_count = 0
    t0 = time.time()

    def flush_locked(b: list[dict]) -> None:
        with db_lock:
            flush_batch(conn, b)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process_one, uid, paths[uid], orientations.get(uid, "landscape"), args.model): uid
            for uid in pending
        }

        for future in as_completed(futures):
            uid = futures[future]
            try:
                result = future.result()
            except Exception as e:
                fail_count += 1
                print(f"  [{done_count + fail_count}/{len(pending)}] {uid[:8]}... FAILED: {e}")
                continue

            if result is None:
                fail_count += 1
                print(f"  [{done_count + fail_count}/{len(pending)}] {uid[:8]}... FAILED (no result)")
                continue

            done_count += 1
            p = result["parsed"]
            w = p.get("visual_weight", "?")
            arch = p.get("archetype", "?")
            ratio = p.get("ideal_ratio", "?")
            temp = p.get("color_temp", "?")
            elapsed = time.time() - t0
            rate = done_count / elapsed * 60 if elapsed > 0 else 0
            print(
                f"  [{done_count + fail_count}/{len(pending)}] {uid[:8]}... "
                f"w={w} arch={arch} ratio={ratio} temp={temp} "
                f"({rate:.0f}/min)"
            )

            batch.append(result)
            if len(batch) >= FLUSH_SIZE:
                flush_locked(list(batch))
                batch.clear()

    if batch:
        flush_locked(batch)

    elapsed = time.time() - t0
    print(f"\nDone: {done_count} processed, {fail_count} failed in {elapsed / 60:.1f} min")


if __name__ == "__main__":
    main()
