#!/usr/bin/env python3
"""Qwen 2.5 VL 7B image analysis — spatial precision & structured inventory.

Complementary VLM to Gemma (narrative) and Gemini (technical). Focused on
spatial precision, object inventory, relationship reasoning, and quantified
technical assessment.

Usage:
    python3 backend/image_signals/run_qwen_analysis.py              # all pending picks
    python3 backend/image_signals/run_qwen_analysis.py --limit 100  # first 100
    python3 backend/image_signals/run_qwen_analysis.py --rerun      # reprocess all
    python3 backend/image_signals/run_qwen_analysis.py --workers 4  # parallel (7B is lighter)
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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
PICKS_JSON = PROJECT_ROOT / "frontend" / "show" / "public" / "data" / "picks.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_DEFAULT = "qwen2.5vl:7b"
FLUSH_SIZE = 5

PROMPT = (
    "You are an expert image analyst. Analyze this photograph with precision. "
    "Respond ONLY with valid JSON, no markdown, no backticks:\n"
    "{\n"
    '  "alt_text": "concise 1-sentence accessibility description",\n'
    '  "people_count": 0,\n'
    '  "objects_inventory": [{"object": "name", "count": 1, "prominence": "high|medium|low"}],\n'
    '  "focal_point": {"x": 0, "y": 0, "strength": 1, "what": "description of focal element"},\n'
    '  "spatial_layers": {"foreground": "what is here", "midground": "what is here", "background": "what is here"},\n'
    '  "relationships": [{"subject": "A", "relation": "verb/preposition", "object": "B"}],\n'
    '  "text_present": false,\n'
    '  "text_content": "",\n'
    '  "text_type": "sign|graffiti|label|handwriting|tattoo|none",\n'
    '  "bokeh_quality": "creamy|busy|absent|na",\n'
    '  "focus_description": "what is sharp, what is soft",\n'
    '  "motion_blur": "none|intentional|camera_shake",\n'
    '  "noise_grain": "clean|film_grain|sensor_noise|intentional",\n'
    '  "symmetry": {"type": "none|bilateral|radial", "strength": 1},\n'
    '  "leading_lines": false,\n'
    '  "repetition_pattern": false,\n'
    '  "environmental_order": 5,\n'
    '  "era_feeling": "modern|vintage|timeless|retro|futuristic",\n'
    '  "narrative_tension": "1-sentence description of story tension"\n'
    "}\n\n"
    "Rules:\n"
    "- people_count: exact integer count of visible people (0 if none)\n"
    "- objects_inventory: list every distinct object, with count and prominence\n"
    "- focal_point: x,y as percentage 0-100 from top-left, strength 1-10\n"
    "- spatial_layers: describe what occupies each depth layer\n"
    "- relationships: subject-relation-object triples describing spatial/action relationships\n"
    "- text_present: true only if readable text is visible in the image\n"
    "- symmetry strength: 1-10 (1=asymmetric, 10=perfect symmetry)\n"
    "- environmental_order: 1=chaotic, 10=orderly\n"
    "- narrative_tension: what unresolved story exists in this single frame"
)


def init_table(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS qwen_analysis (
            uuid                TEXT PRIMARY KEY,
            raw_json            TEXT NOT NULL,
            alt_text            TEXT,
            people_count        INTEGER,
            objects_inventory   TEXT,
            focal_point         TEXT,
            spatial_layers      TEXT,
            relationships       TEXT,
            text_present        INTEGER,
            text_content        TEXT,
            text_type           TEXT,
            bokeh_quality       TEXT,
            focus_description   TEXT,
            motion_blur         TEXT,
            noise_grain         TEXT,
            symmetry            TEXT,
            leading_lines       INTEGER,
            repetition_pattern  INTEGER,
            environmental_order INTEGER,
            era_feeling         TEXT,
            narrative_tension   TEXT,
            model               TEXT,
            processed_at        TEXT NOT NULL
        );
    """)


def load_pick_uuids() -> list[str]:
    """Load pick UUIDs from picks.json, filtering out variant IDs."""
    picks_path = PICKS_JSON
    if not picks_path.exists():
        alt = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"
        if alt.exists():
            picks_path = alt
    data = json.loads(picks_path.read_text())
    uuids = list(dict.fromkeys(
        [u for u in data["portrait"] if "_" not in u] +
        [u for u in data["landscape"] if "_" not in u]
    ))
    return uuids


def get_mobile_paths(conn: sqlite3.Connection, uuids: list[str]) -> dict[str, str]:
    """Map UUIDs to their mobile JPEG local paths from the tiers table."""
    paths = {}
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


def get_pending_uuids(
    conn: sqlite3.Connection, all_uuids: list[str], rerun: bool,
) -> list[str]:
    """Determine which UUIDs need processing."""
    if rerun:
        return all_uuids
    try:
        rows = conn.execute("SELECT uuid FROM qwen_analysis").fetchall()
    except sqlite3.OperationalError:
        return all_uuids
    done = {r[0] for r in rows}
    return [u for u in all_uuids if u not in done]


def query_qwen(img_path: str, model: str = MODEL_DEFAULT,
               retries: int = 3) -> dict | None:
    """Send image to Qwen via Ollama and parse JSON response."""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = json.dumps({
        "model": model,
        "prompt": PROMPT,
        "images": [img_b64],
        "format": "json",
        "stream": False,
        "keep_alive": "24h",
        "options": {"temperature": 0.3, "num_predict": 2000},
    }).encode()

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                OLLAMA_URL, data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=180)
            result = json.loads(resp.read())
            text = result.get("response", "").strip()

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw": text}
        except urllib.error.URLError as e:
            if "Connection refused" in str(e):
                wait = 30 * (attempt + 1)
                print(f"\n  Ollama down, waiting {wait}s... (attempt {attempt+1}/{retries})")
                time.sleep(wait)
            elif attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
            else:
                raise
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
            else:
                raise


def _to_str(val, fallback: str = "") -> str:
    if val is None:
        return fallback
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


def _to_int(val, default: int | None = None) -> int | None:
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            return default
    return default


def _to_bool_int(val, default: int | None = None) -> int | None:
    """Convert bool/string/int to 0/1 for SQLite."""
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, int):
        return 1 if val else 0
    if isinstance(val, str):
        return 1 if val.lower() in ("true", "yes", "1") else 0
    return default


def _to_json(val) -> str | None:
    """Serialize a dict or list to JSON string, pass through strings."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, str):
        return val
    return json.dumps(val, ensure_ascii=False)


def _parse_row(parsed: dict) -> dict:
    """Extract all fields from a parsed Qwen response for DB insertion."""
    return {
        "raw_json": json.dumps(parsed, ensure_ascii=False),
        "alt_text": _to_str(parsed.get("alt_text", "")),
        "people_count": _to_int(parsed.get("people_count"), 0),
        "objects_inventory": _to_json(parsed.get("objects_inventory")),
        "focal_point": _to_json(parsed.get("focal_point")),
        "spatial_layers": _to_json(parsed.get("spatial_layers")),
        "relationships": _to_json(parsed.get("relationships")),
        "text_present": _to_bool_int(parsed.get("text_present"), 0),
        "text_content": _to_str(parsed.get("text_content", "")),
        "text_type": _to_str(parsed.get("text_type", "none")),
        "bokeh_quality": _to_str(parsed.get("bokeh_quality", "")),
        "focus_description": _to_str(parsed.get("focus_description", "")),
        "motion_blur": _to_str(parsed.get("motion_blur", "")),
        "noise_grain": _to_str(parsed.get("noise_grain", "")),
        "symmetry": _to_json(parsed.get("symmetry")),
        "leading_lines": _to_bool_int(parsed.get("leading_lines"), 0),
        "repetition_pattern": _to_bool_int(parsed.get("repetition_pattern"), 0),
        "environmental_order": _to_int(parsed.get("environmental_order")),
        "era_feeling": _to_str(parsed.get("era_feeling", "")),
        "narrative_tension": _to_str(parsed.get("narrative_tension", "")),
    }


_INSERT_SQL = """
    INSERT INTO qwen_analysis (
        uuid, raw_json, alt_text, people_count,
        objects_inventory, focal_point, spatial_layers, relationships,
        text_present, text_content, text_type,
        bokeh_quality, focus_description, motion_blur, noise_grain,
        symmetry, leading_lines, repetition_pattern, environmental_order,
        era_feeling, narrative_tension,
        model, processed_at
    ) VALUES (
        ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?,
        ?, ?
    )
    ON CONFLICT(uuid) DO UPDATE SET
        raw_json = excluded.raw_json,
        alt_text = excluded.alt_text,
        people_count = excluded.people_count,
        objects_inventory = excluded.objects_inventory,
        focal_point = excluded.focal_point,
        spatial_layers = excluded.spatial_layers,
        relationships = excluded.relationships,
        text_present = excluded.text_present,
        text_content = excluded.text_content,
        text_type = excluded.text_type,
        bokeh_quality = excluded.bokeh_quality,
        focus_description = excluded.focus_description,
        motion_blur = excluded.motion_blur,
        noise_grain = excluded.noise_grain,
        symmetry = excluded.symmetry,
        leading_lines = excluded.leading_lines,
        repetition_pattern = excluded.repetition_pattern,
        environmental_order = excluded.environmental_order,
        era_feeling = excluded.era_feeling,
        narrative_tension = excluded.narrative_tension,
        model = excluded.model,
        processed_at = excluded.processed_at
"""


def _insert_row(conn: sqlite3.Connection, uuid: str, fields: dict,
                model: str, now: str) -> None:
    conn.execute(_INSERT_SQL, (
        uuid,
        fields["raw_json"],
        fields["alt_text"],
        fields["people_count"],
        fields["objects_inventory"],
        fields["focal_point"],
        fields["spatial_layers"],
        fields["relationships"],
        fields["text_present"],
        fields["text_content"],
        fields["text_type"],
        fields["bokeh_quality"],
        fields["focus_description"],
        fields["motion_blur"],
        fields["noise_grain"],
        fields["symmetry"],
        fields["leading_lines"],
        fields["repetition_pattern"],
        fields["environmental_order"],
        fields["era_feeling"],
        fields["narrative_tension"],
        model,
        now,
    ))


def flush_batch(conn: sqlite3.Connection, batch: list[dict], model: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for row in batch:
        fields = _parse_row(row["parsed"])
        _insert_row(conn, row["uuid"], fields, model, now)
    conn.commit()


def process_one(uuid: str, img_path: str, model: str) -> dict:
    """Process a single image. Returns result dict with 'parsed' or 'error'."""
    if not Path(img_path).exists():
        return {"uuid": uuid, "error": f"file not found — {img_path}"}
    try:
        parsed = query_qwen(img_path, model)
        if parsed is None:
            raise ValueError("Empty response")
        return {"uuid": uuid, "parsed": parsed}
    except Exception as e:
        return {"uuid": uuid, "error": str(e)}


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Qwen 2.5 VL 7B analysis for picked photos")
    parser.add_argument("--model", type=str, default=MODEL_DEFAULT,
                        help=f"Ollama model (default: {MODEL_DEFAULT})")
    parser.add_argument("--workers", type=int, default=1,
                        help="Parallel workers (default: 1)")
    parser.add_argument("--limit", type=int, help="Process first N pending")
    parser.add_argument("--rerun", action="store_true",
                        help="Reprocess all picks")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")

    init_table(conn)

    # Load target UUIDs
    all_uuids = load_pick_uuids()
    paths = get_mobile_paths(conn, all_uuids)
    print(f"Picks: {len(all_uuids)} UUIDs, {len(paths)} have mobile JPEGs")

    # Determine pending
    pending_uuids = get_pending_uuids(
        conn, [u for u in all_uuids if u in paths], args.rerun)
    print(f"Pending: {len(pending_uuids)}")

    if args.limit:
        pending_uuids = pending_uuids[:args.limit]

    if not pending_uuids:
        print("Nothing to do.")
        conn.close()
        return

    model = args.model
    workers = max(1, args.workers)
    print(f"Processing {len(pending_uuids)} images with {model} "
          f"({workers} worker{'s' if workers > 1 else ''})...")
    t0 = time.time()
    errors = 0
    error_msgs = []
    batch = []
    db_lock = threading.Lock()

    bar = tqdm(total=len(pending_uuids), desc="qwen-analysis")

    def flush_locked(b):
        with db_lock:
            flush_batch(conn, b, model)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        active: dict = {}
        pending_iter = iter(pending_uuids)

        def submit_next():
            try:
                uuid = next(pending_iter)
                f = pool.submit(process_one, uuid, paths[uuid], model)
                active[f] = uuid
            except StopIteration:
                pass

        # Prime the pool
        for _ in range(min(workers, len(pending_uuids))):
            submit_next()

        while active:
            done_futures = []
            for f in list(active):
                if f.done():
                    done_futures.append(f)
            if not done_futures:
                time.sleep(0.1)
                continue
            for future in done_futures:
                uuid = active.pop(future)
                try:
                    result = future.result()
                except Exception as e:
                    result = {"uuid": uuid, "error": str(e)}
                bar.update(1)

                if "error" in result:
                    errors += 1
                    if len(error_msgs) < 10:
                        error_msgs.append(f"{result.get('uuid', '?')}: {result.get('error', '?')}")
                else:
                    batch.append(result)
                    if len(batch) >= FLUSH_SIZE:
                        flush_locked(list(batch))
                        batch.clear()

                submit_next()

    bar.close()

    if batch:
        flush_batch(conn, batch, model)

    elapsed = time.time() - t0
    processed = len(pending_uuids) - errors

    conn.close()

    # Summary
    print(f"\nDone in {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"  Processed: {processed:,}")
    print(f"  Errors:    {errors:,}")
    if processed > 0:
        print(f"  Avg time:  {elapsed / processed:.1f}s per image")

    if error_msgs:
        print(f"\nFirst {len(error_msgs)} errors:")
        for msg in error_msgs:
            print(f"  {msg}")


if __name__ == "__main__":
    main()
