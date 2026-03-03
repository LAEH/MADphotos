#!/usr/bin/env python3
"""Qwen 2.5 VL 7B image analysis — spatial precision & structured inventory.

Complementary VLM to Gemma (narrative) and Gemini (technical). Focused on
spatial precision, object inventory, relationship reasoning, quantified
technical assessment, crop coordinates, and variant generation prompts.

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
    "You are an expert image analyst and creative director. "
    "Analyze this photograph with precision. "
    "Respond ONLY with valid JSON, no markdown, no extra text.\n\n"
    '{\n'
    '  "alt_text": "concise 1-sentence accessibility description of this image",\n'
    '  "people_count": 0,\n'
    '  "objects_inventory": [{"object": "name", "count": 1, "prominence": "high"}],\n'
    '  "focal_point": {"x": 50, "y": 50, "strength": 8, "what": "the main focal element"},\n'
    '  "spatial_layers": {"foreground": "description", "midground": "description", "background": "description"},\n'
    '  "relationships": [{"subject": "A", "relation": "verb/prep", "object": "B"}],\n'
    '  "text_present": false,\n'
    '  "text_content": "",\n'
    '  "text_type": "none",\n'
    '  "bokeh_quality": "absent",\n'
    '  "focus_description": "what is sharp and what is soft",\n'
    '  "motion_blur": "none",\n'
    '  "noise_grain": "clean",\n'
    '  "symmetry": {"type": "none", "strength": 3},\n'
    '  "leading_lines": false,\n'
    '  "repetition_pattern": false,\n'
    '  "environmental_order": 5,\n'
    '  "era_feeling": "modern",\n'
    '  "narrative_tension": "1-sentence: what unresolved story exists in this frame",\n'
    '  "variant_prompts": [\n'
    '    {"style": "style name", "prompt": "2-3 sentence image generation prompt", "mood": "target mood", "color_palette": "3-4 dominant colors"},\n'
    '    {"style": "style name", "prompt": "2-3 sentence prompt", "mood": "mood", "color_palette": "colors"},\n'
    '    {"style": "style name", "prompt": "2-3 sentence prompt", "mood": "mood", "color_palette": "colors"},\n'
    '    {"style": "style name", "prompt": "2-3 sentence prompt", "mood": "mood", "color_palette": "colors"},\n'
    '    {"style": "style name", "prompt": "2-3 sentence prompt", "mood": "mood", "color_palette": "colors"}\n'
    '  ]\n'
    '}\n\n'
    "FIELD RULES:\n"
    "- alt_text: 1 sentence, for screen readers\n"
    "- people_count: exact integer, 0 if none\n"
    "- objects_inventory: every distinct object with count and prominence (high/medium/low)\n"
    "- focal_point: x,y as 0-100 percentage from top-left corner, strength 1-10\n"
    "- spatial_layers: what occupies foreground, midground, background\n"
    "- relationships: 2-5 subject-relation-object triples\n"
    "- text_type: pick ONE of sign/graffiti/label/handwriting/tattoo/none\n"
    "- bokeh_quality: pick ONE of creamy/busy/absent/na\n"
    "- motion_blur: pick ONE of none/intentional/camera_shake\n"
    "- noise_grain: pick ONE of clean/film_grain/sensor_noise/intentional\n"
    "- symmetry type: pick ONE of none/bilateral/radial, strength 1-10\n"
    "- environmental_order: 1=chaotic, 10=perfectly orderly\n"
    "- era_feeling: pick ONE of modern/vintage/timeless/retro/futuristic\n"
    "- variant_prompts: 5 WILDLY DIFFERENT creative image generation prompts. "
    "This is the most important field. Dream big. Each prompt must:\n"
    "  1. Describe a COMPLETE visual transformation of this photograph\n"
    "  2. Be 2-3 detailed sentences specifying colors, textures, lighting, and technique\n"
    "  3. CRITICAL: The layout, composition, and position of every subject MUST stay IDENTICAL. "
    "If there is a cat in the center, the cat stays in the center. Eyes, legs, pose — all in the exact same place. "
    "Only the visual STYLE changes (colors, textures, medium, rendering). The image structure is sacred.\n"
    "  4. Include a color_palette field with 3-4 dominant colors of the dreamed variant\n"
    "  5. Cover DIVERSE styles across the 5 prompts. Pick from:\n"
    "     oil painting, watercolor, cyberpunk neon, film noir, anime cel-shaded, ukiyo-e woodblock,\n"
    "     art deco gold leaf, impressionist, infrared photography, double exposure,\n"
    "     paper cutout collage, stained glass, pixel art, vaporwave, gothic illustration,\n"
    "     soviet propaganda poster, 1970s kodachrome, daguerreotype, risograph print,\n"
    "     botanical illustration, blueprint/technical drawing, embroidery textile,\n"
    "     cave painting, pop art screenprint, isometric 3D render"
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
            crops               TEXT,
            variant_prompts     TEXT,
            model               TEXT,
            processed_at        TEXT NOT NULL
        );
    """)
    # Add new columns to existing table if needed
    for col, ctype in [("crops", "TEXT"), ("variant_prompts", "TEXT")]:
        try:
            conn.execute(f"SELECT {col} FROM qwen_analysis LIMIT 0")
        except sqlite3.OperationalError:
            conn.execute(f"ALTER TABLE qwen_analysis ADD COLUMN {col} {ctype}")
            conn.commit()


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
    """Determine which UUIDs need processing.
    Prioritizes: 1) never processed, 2) processed but missing good variants.
    """
    if rerun:
        return all_uuids
    try:
        rows = conn.execute("SELECT uuid, variant_prompts FROM qwen_analysis").fetchall()
    except sqlite3.OperationalError:
        return all_uuids

    # Split into: has good variants vs missing/bad variants
    good = set()
    needs_rerun = set()
    for uuid, vp in rows:
        ok = False
        if vp:
            try:
                data = json.loads(vp)
                if isinstance(data, list) and len(data) >= 3:
                    if any(v.get("prompt", "") for v in data if isinstance(v, dict)):
                        ok = True
            except (json.JSONDecodeError, TypeError):
                pass
        if ok:
            good.add(uuid)
        else:
            needs_rerun.add(uuid)

    # Priority order: never processed first, then bad variants, skip good ones
    never = [u for u in all_uuids if u not in good and u not in needs_rerun]
    retry = [u for u in all_uuids if u in needs_rerun]
    return retry + never


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
        "options": {"temperature": 0.4, "num_predict": 3000},
    }).encode()

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                OLLAMA_URL, data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=300)
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
        "crops": _to_json(parsed.get("crops")),
        "variant_prompts": _to_json(parsed.get("variant_prompts")),
    }


_INSERT_SQL = """
    INSERT INTO qwen_analysis (
        uuid, raw_json, alt_text, people_count,
        objects_inventory, focal_point, spatial_layers, relationships,
        text_present, text_content, text_type,
        bokeh_quality, focus_description, motion_blur, noise_grain,
        symmetry, leading_lines, repetition_pattern, environmental_order,
        era_feeling, narrative_tension, crops, variant_prompts,
        model, processed_at
    ) VALUES (
        ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?,
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
        crops = excluded.crops,
        variant_prompts = excluded.variant_prompts,
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
        fields["crops"],
        fields["variant_prompts"],
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

def import_results(conn: sqlite3.Connection, results_file: Path,
                   model: str) -> int:
    """Bulk-import results from JSONL file into DB. Returns count imported."""
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    with open(results_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "error" in row:
                continue
            fields = _parse_row(row["parsed"])
            _insert_row(conn, row["uuid"], fields, model, now)
            count += 1
            if count % 50 == 0:
                conn.commit()
    conn.commit()
    return count


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
    parser.add_argument("--import-only", type=str, default=None,
                        help="Import results from JSONL file (skip inference)")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")

    init_table(conn)

    # Import-only mode: read JSONL → DB, no inference
    if args.import_only:
        results_file = Path(args.import_only)
        if not results_file.exists():
            print(f"File not found: {results_file}")
            conn.close()
            return
        print(f"Importing from {results_file}...")
        count = import_results(conn, results_file, args.model)
        print(f"Imported {count} rows.")
        conn.close()
        return

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

    # Close DB — all inference writes go to JSONL file, not DB
    conn.close()

    model = args.model
    workers = max(1, args.workers)

    # Results file: JSONL, one JSON object per line
    results_file = PROJECT_ROOT / "backend" / "image_signals" / "qwen_results.jsonl"
    print(f"Processing {len(pending_uuids)} images with {model} "
          f"({workers} worker{'s' if workers > 1 else ''})...")
    print(f"Results → {results_file}")
    t0 = time.time()
    errors = 0
    error_msgs = []
    results_lock = threading.Lock()

    bar = tqdm(total=len(pending_uuids), desc="qwen-analysis")

    with open(results_file, "a") as rf:
        def write_result(result):
            with results_lock:
                rf.write(json.dumps(result, ensure_ascii=False) + "\n")
                rf.flush()

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
                    write_result(result)
                    submit_next()

    bar.close()

    elapsed = time.time() - t0
    processed = len(pending_uuids) - errors

    # Summary
    print(f"\nInference done in {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"  Processed: {processed:,}")
    print(f"  Errors:    {errors:,}")
    if processed > 0:
        print(f"  Avg time:  {elapsed / processed:.1f}s per image")

    if error_msgs:
        print(f"\nFirst {len(error_msgs)} errors:")
        for msg in error_msgs:
            print(f"  {msg}")

    # Bulk import to DB
    print(f"\nImporting {processed} results to DB...")
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    count = import_results(conn, results_file, model)
    conn.close()
    print(f"Imported {count} rows to qwen_analysis.")


if __name__ == "__main__":
    main()
