#!/usr/bin/env python3
"""Consolidated Gemma analysis — one table, one prompt, all signals.

Replaces run_gemma_picks.py + run_gemma_composition.py with a single unified
analysis per image.  Results stored in `gemma_analysis` table in mad_photos.db
and exported to frontend/show/data/gemma_analysis.json.

Usage:
    python3 backend/run_gemma_analysis.py              # all pending picks
    python3 backend/run_gemma_analysis.py --limit 10   # first 10
    python3 backend/run_gemma_analysis.py --rerun       # reprocess all
    python3 backend/run_gemma_analysis.py --migrate     # seed from legacy tables
    python3 backend/run_gemma_analysis.py --uuids-file path.txt
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
PICKS_JSON = PROJECT_ROOT / "frontend" / "show" / "public" / "data" / "picks.json"
OUTPUT_JSON = PROJECT_ROOT / "frontend" / "show" / "data" / "gemma_analysis.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_DEFAULT = "madphotos-critic"
FLUSH_SIZE = 25

PROMPT = (
    "You are an expert photography critic. Analyze this photograph. "
    "Respond ONLY with valid JSON, no markdown, no backticks:\n"
    '{"description":"2-3 sentence vivid description",'
    '"subject":"primary subject(s)",'
    '"story":"moment, narrative, or feeling captured",'
    '"composition":"frame arrangement, technique, balance, eye flow",'
    '"lighting":"quality, direction, character of light",'
    '"colors":"dominant colors and relationships",'
    '"texture":"visible textures, materials, surfaces",'
    '"mood":"emotional atmosphere in 2-3 words",'
    '"technical":"exposure, focus, depth of field, sharpness",'
    '"strength":"what makes this strong",'
    '"tags":["up to 15 descriptive tags"],'
    '"print_worthy":true or false,'
    '"crops":{'
    '"1:1":{"center_x":0-100,"center_y":0-100,"coverage":30-90},'
    '"2:3":{"center_x":0-100,"center_y":0-100,"coverage":30-90},'
    '"3:2":{"center_x":0-100,"center_y":0-100,"coverage":30-90},'
    '"16:9":{"center_x":0-100,"center_y":0-100,"coverage":30-90}},'
    '"stories":{'
    '"silly":"1-sentence playful story",'
    '"poetic":"1-sentence lyrical interpretation",'
    '"surrealist":"1-sentence dreamlike narrative",'
    '"noir":"1-sentence noir description",'
    '"romantic":"1-sentence romantic interpretation"},'
    '"cartoon_style":"best cartoon/illustration transformation and why",'
    '"visual_weight":1-10,'
    '"energy_direction":"left_to_right|right_to_left|up|down|center_out|inward|diagonal_down|diagonal_up|static",'
    '"archetype":"portal|horizon|texture|figure|geometry|void|cluster|reflection|silhouette|panorama",'
    '"color_temp":"glacial|cool|neutral|warm|molten|electric|neon|muted|monochrome"}'
    "\n\nFor crops: center_x/center_y = center of crop region (0-100), "
    "coverage = percentage of image to include (30-90). "
    "Higher coverage = more context, lower = tighter on subject.\n"
    "For stories: SHORT punchy 1-sentence each.\n"
    "visual_weight: 1=airy/minimal, 10=dense/heavy.\n"
    "energy_direction: dominant visual flow.\n"
    "archetype: single best compositional archetype.\n"
    "color_temp: overall temperature feeling."
)


def init_table(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gemma_analysis (
            uuid              TEXT PRIMARY KEY,
            raw_json          TEXT NOT NULL,
            -- Narrative
            description       TEXT,
            subject           TEXT,
            story             TEXT,
            mood              TEXT,
            -- Technical
            composition       TEXT,
            lighting          TEXT,
            colors            TEXT,
            texture           TEXT,
            technical         TEXT,
            strength          TEXT,
            -- Tags & flags
            tags              TEXT,
            print_worthy      INTEGER,
            cartoon_style     TEXT,
            -- Crops
            crops             TEXT,
            -- Stories
            story_silly       TEXT,
            story_poetic      TEXT,
            story_surrealist  TEXT,
            story_noir        TEXT,
            story_romantic    TEXT,
            -- Composition intelligence (was gemma_composition)
            visual_weight     INTEGER,
            energy_direction  TEXT,
            archetype         TEXT,
            color_temp        TEXT,
            -- Meta
            model             TEXT,
            processed_at      TEXT NOT NULL
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
    uuids = list(dict.fromkeys(data["portrait"] + data["landscape"]))
    # Filter variant UUIDs (contain _ from parent_stylename format)
    return [u for u in uuids if "_" not in u]


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
        rows = conn.execute(
            "SELECT uuid, model, visual_weight FROM gemma_analysis"
        ).fetchall()
    except sqlite3.OperationalError:
        return all_uuids

    # Skip completed rows, but reprocess migrated rows missing composition
    done = set()
    for uuid, model, vw in rows:
        if model == "migrated" and vw is None:
            continue  # incomplete migration — needs reprocessing
        done.add(uuid)
    return [u for u in all_uuids if u not in done]


def query_gemma(img_path: str, model: str = MODEL_DEFAULT) -> dict | None:
    """Send image to Gemma via Ollama and parse JSON response."""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = json.dumps({
        "model": model,
        "prompt": PROMPT,
        "images": [img_b64],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 1500},
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=240)
    result = json.loads(resp.read())
    text = result.get("response", "").strip()

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


def _to_int(val, default: int | None = None) -> int | None:
    """Coerce to int, return default if not possible."""
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


def _parse_row(parsed: dict) -> dict:
    """Extract all fields from a parsed Gemma response for DB insertion."""
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

    crops = parsed.get("crops", {})
    crops_json = json.dumps(crops, ensure_ascii=False) if isinstance(crops, dict) else None

    stories = parsed.get("stories", {})
    if not isinstance(stories, dict):
        stories = {}

    return {
        "raw_json": json.dumps(parsed, ensure_ascii=False),
        "description": _to_str(parsed.get("description", parsed.get("raw", ""))),
        "subject": _to_str(parsed.get("subject", "")),
        "story": _to_str(parsed.get("story", "")),
        "mood": _to_str(parsed.get("mood", "")),
        "composition": _to_str(parsed.get("composition", "")),
        "lighting": _to_str(parsed.get("lighting", "")),
        "colors": _to_str(parsed.get("colors", "")),
        "texture": _to_str(parsed.get("texture", "")),
        "technical": _to_str(parsed.get("technical", "")),
        "strength": _to_str(parsed.get("strength", "")),
        "tags": tags_str,
        "print_worthy": print_worthy,
        "cartoon_style": _to_str(parsed.get("cartoon_style", "")),
        "crops": crops_json,
        "story_silly": _to_str(stories.get("silly", "")),
        "story_poetic": _to_str(stories.get("poetic", "")),
        "story_surrealist": _to_str(stories.get("surrealist", "")),
        "story_noir": _to_str(stories.get("noir", "")),
        "story_romantic": _to_str(stories.get("romantic", "")),
        "visual_weight": _to_int(parsed.get("visual_weight")),
        "energy_direction": _to_str(parsed.get("energy_direction", "")),
        "archetype": _to_str(parsed.get("archetype", "")),
        "color_temp": _to_str(parsed.get("color_temp", "")),
    }


_INSERT_SQL = """
    INSERT INTO gemma_analysis (
        uuid, raw_json, description, subject, story, mood,
        composition, lighting, colors, texture, technical, strength,
        tags, print_worthy, cartoon_style, crops,
        story_silly, story_poetic, story_surrealist, story_noir, story_romantic,
        visual_weight, energy_direction, archetype, color_temp,
        model, processed_at
    ) VALUES (
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?
    )
    ON CONFLICT(uuid) DO UPDATE SET
        raw_json = excluded.raw_json,
        description = excluded.description,
        subject = excluded.subject,
        story = excluded.story,
        mood = excluded.mood,
        composition = excluded.composition,
        lighting = excluded.lighting,
        colors = excluded.colors,
        texture = excluded.texture,
        technical = excluded.technical,
        strength = excluded.strength,
        tags = excluded.tags,
        print_worthy = excluded.print_worthy,
        cartoon_style = excluded.cartoon_style,
        crops = excluded.crops,
        story_silly = excluded.story_silly,
        story_poetic = excluded.story_poetic,
        story_surrealist = excluded.story_surrealist,
        story_noir = excluded.story_noir,
        story_romantic = excluded.story_romantic,
        visual_weight = excluded.visual_weight,
        energy_direction = excluded.energy_direction,
        archetype = excluded.archetype,
        color_temp = excluded.color_temp,
        model = excluded.model,
        processed_at = excluded.processed_at
"""


def _insert_row(conn: sqlite3.Connection, uuid: str, fields: dict,
                model: str, now: str) -> None:
    conn.execute(_INSERT_SQL, (
        uuid,
        fields["raw_json"],
        fields["description"],
        fields["subject"],
        fields["story"],
        fields["mood"],
        fields["composition"],
        fields["lighting"],
        fields["colors"],
        fields["texture"],
        fields["technical"],
        fields["strength"],
        fields["tags"],
        fields["print_worthy"],
        fields["cartoon_style"],
        fields["crops"],
        fields["story_silly"],
        fields["story_poetic"],
        fields["story_surrealist"],
        fields["story_noir"],
        fields["story_romantic"],
        fields["visual_weight"],
        fields["energy_direction"],
        fields["archetype"],
        fields["color_temp"],
        model,
        now,
    ))


def flush_batch(conn: sqlite3.Connection, batch: list[dict], model: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for row in batch:
        fields = _parse_row(row["parsed"])
        _insert_row(conn, row["uuid"], fields, model, now)
    conn.commit()


def export_json(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT uuid, raw_json FROM gemma_analysis").fetchall()
    result = {}
    for uuid, raw_json in rows:
        try:
            result[uuid] = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            result[uuid] = {"raw": raw_json}

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return len(result)


def process_one(uuid: str, img_path: str, model: str) -> dict:
    """Process a single image. Returns result dict with 'parsed' or 'error'."""
    if not Path(img_path).exists():
        return {"uuid": uuid, "error": f"file not found — {img_path}"}
    try:
        parsed = query_gemma(img_path, model)
        if parsed is None:
            raise ValueError("Empty response")
        return {"uuid": uuid, "parsed": parsed}
    except Exception as e:
        return {"uuid": uuid, "error": str(e)}


# ── Migration ───────────────────────────────────────────────────────────────

def migrate(conn: sqlite3.Connection) -> None:
    """Seed gemma_analysis from legacy gemma_picks + gemma_composition tables."""
    init_table(conn)
    now = datetime.now(timezone.utc).isoformat()

    # Load legacy gemma_picks
    picks_data: dict[str, dict] = {}
    try:
        rows = conn.execute("SELECT uuid, gemma_json FROM gemma_picks").fetchall()
        for uuid, gj in rows:
            try:
                picks_data[uuid] = json.loads(gj)
            except (json.JSONDecodeError, TypeError):
                picks_data[uuid] = {}
        print(f"  Legacy gemma_picks: {len(picks_data)} rows")
    except sqlite3.OperationalError:
        print("  Legacy gemma_picks: table not found")

    # Load legacy gemma_composition
    comp_data: dict[str, dict] = {}
    try:
        rows = conn.execute(
            "SELECT image_uuid, visual_weight, energy_direction, archetype, color_temp "
            "FROM gemma_composition"
        ).fetchall()
        for row in rows:
            comp_data[row[0]] = {
                "visual_weight": row[1],
                "energy_direction": row[2],
                "archetype": row[3],
                "color_temp": row[4],
            }
        print(f"  Legacy gemma_composition: {len(comp_data)} rows")
    except sqlite3.OperationalError:
        print("  Legacy gemma_composition: table not found")

    all_uuids = set(picks_data) | set(comp_data)
    if not all_uuids:
        print("  Nothing to migrate.")
        return

    migrated = 0
    for uuid in all_uuids:
        picks = picks_data.get(uuid, {})
        comp = comp_data.get(uuid, {})

        # Merge: picks data is the base, composition fields overlay
        merged = dict(picks)
        if comp.get("visual_weight") is not None:
            merged["visual_weight"] = comp["visual_weight"]
        if comp.get("energy_direction"):
            merged["energy_direction"] = comp["energy_direction"]
        if comp.get("archetype"):
            merged["archetype"] = comp["archetype"]
        if comp.get("color_temp"):
            merged["color_temp"] = comp["color_temp"]

        fields = _parse_row(merged)
        _insert_row(conn, uuid, fields, "migrated", now)
        migrated += 1

    conn.commit()
    print(f"  Migrated {migrated} rows into gemma_analysis")

    # Report completeness
    incomplete = conn.execute(
        "SELECT COUNT(*) FROM gemma_analysis WHERE model = 'migrated' AND visual_weight IS NULL"
    ).fetchone()[0]
    if incomplete:
        print(f"  {incomplete} rows missing composition signals (candidates for reprocessing)")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Consolidated Gemma analysis for picked photos")
    parser.add_argument("--model", type=str, default=MODEL_DEFAULT,
                        help=f"Ollama model (default: {MODEL_DEFAULT})")
    parser.add_argument("--workers", type=int, default=1,
                        help="Parallel workers (default: 1 for 27B)")
    parser.add_argument("--limit", type=int, help="Process first N pending")
    parser.add_argument("--rerun", action="store_true",
                        help="Reprocess all picks")
    parser.add_argument("--uuids-file", type=str,
                        help="File with UUIDs to process (one per line)")
    parser.add_argument("--migrate", action="store_true",
                        help="Seed from gemma_picks + gemma_composition (no Ollama)")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")

    if args.migrate:
        print("Migrating legacy tables -> gemma_analysis...")
        migrate(conn)
        exported = export_json(conn)
        print(f"Exported {exported} results -> gemma_analysis.json")
        conn.close()
        return

    init_table(conn)

    # Load target UUIDs
    if args.uuids_file:
        with open(args.uuids_file, 'r') as f:
            all_uuids = [line.strip() for line in f if line.strip()]
        print(f"Loaded {len(all_uuids)} UUIDs from {args.uuids_file}")
    else:
        all_uuids = load_pick_uuids()

    paths = get_mobile_paths(conn, all_uuids)
    print(f"Picks: {len(all_uuids)} UUIDs, {len(paths)} have mobile JPEGs")

    # Determine pending
    if args.uuids_file:
        pending_uuids = [u for u in all_uuids if u in paths]
    else:
        pending_uuids = get_pending_uuids(
            conn, [u for u in all_uuids if u in paths], args.rerun)
        print(f"Pending: {len(pending_uuids)}")

    if args.limit:
        pending_uuids = pending_uuids[:args.limit]

    if not pending_uuids:
        print("Nothing to do.")
        exported = export_json(conn)
        print(f"Exported {exported} results -> gemma_analysis.json")
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

    bar = tqdm(total=len(pending_uuids), desc="gemma-analysis")

    def flush_locked(b):
        with db_lock:
            flush_batch(conn, b, model)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(process_one, uuid, paths[uuid], model): uuid
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
        flush_batch(conn, batch, model)

    elapsed = time.time() - t0
    processed = len(pending_uuids) - errors

    # Export results
    exported = export_json(conn)
    conn.close()

    # Summary
    print(f"\nDone in {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"  Processed: {processed:,}")
    print(f"  Errors:    {errors:,}")
    print(f"  Exported:  {exported:,} -> gemma_analysis.json")
    if processed > 0:
        print(f"  Avg time:  {elapsed / processed:.1f}s per image")

    if error_msgs:
        print(f"\nFirst {len(error_msgs)} errors:")
        for msg in error_msgs:
            print(f"  {msg}")


if __name__ == "__main__":
    main()
