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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
PICKS_JSON = PROJECT_ROOT / "frontend" / "show" / "public" / "data" / "picks.json"
OUTPUT_JSON = PROJECT_ROOT / "frontend" / "show" / "data" / "gemma_analysis.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_DEFAULT = "madphotos-critic"
FLUSH_SIZE = 5

_PROMPT_BASE = (
    "You are an expert photography critic. Analyze this photograph. "
    "Respond ONLY with valid JSON, no markdown, no backticks:\n"
    '{{"description":"2-3 sentence vivid description",'
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
    '"crops":{{{crops_spec}}},'
    '"stories":{{'
    '"silly":"1-sentence playful story",'
    '"poetic":"1-sentence lyrical interpretation",'
    '"surrealist":"1-sentence dreamlike narrative",'
    '"noir":"1-sentence noir description",'
    '"romantic":"1-sentence romantic interpretation"}},'
    '"cartoon_style":"best cartoon/illustration transformation and why",'
    '"visual_weight":1-10,'
    '"energy_direction":"left_to_right|right_to_left|up|down|center_out|inward|diagonal_down|diagonal_up|static",'
    '"archetype":"portal|horizon|texture|figure|geometry|void|cluster|reflection|silhouette|panorama",'
    '"color_temp":"glacial|cool|neutral|warm|molten|electric|neon|muted|monochrome",'
    '"exposure_label":"balanced|under|over",'
    '"sharpness_label":"sharp|soft|motion_blur",'
    '"vibes":["3-5 single lowercase mood words"],'
    '"semantic_pops":[{{"color":"name","object":"what","impact":"high|medium|low"}}]}}'
    "\n\nFor crops: center_x/center_y = center of crop region (0-100), "
    "coverage = percentage of image to include (30-90). "
    "Higher coverage = more context, lower = tighter on subject.\n"
    "For stories: SHORT punchy 1-sentence each.\n"
    "visual_weight: 1=airy/minimal, 10=dense/heavy.\n"
    "energy_direction: dominant visual flow.\n"
    "archetype: single best compositional archetype.\n"
    "color_temp: overall temperature feeling.\n"
    "exposure_label: overall exposure assessment.\n"
    "sharpness_label: overall sharpness.\n"
    "vibes: 3-5 single lowercase words capturing the atmosphere.\n"
    "semantic_pops: 1-3 visually striking elements that grab attention."
)

_CROPS_PORTRAIT = (
    '"1:1":{"center_x":0-100,"center_y":0-100,"coverage":30-90},'
    '"1:2":{"center_x":0-100,"center_y":0-100,"coverage":30-90},'
    '"2:3":{"center_x":0-100,"center_y":0-100,"coverage":30-90},'
    '"3:4":{"center_x":0-100,"center_y":0-100,"coverage":30-90}'
)
_CROPS_LANDSCAPE = (
    '"1:1":{"center_x":0-100,"center_y":0-100,"coverage":30-90},'
    '"2:1":{"center_x":0-100,"center_y":0-100,"coverage":30-90},'
    '"3:2":{"center_x":0-100,"center_y":0-100,"coverage":30-90},'
    '"4:3":{"center_x":0-100,"center_y":0-100,"coverage":30-90}'
)

PROMPT_PORTRAIT = _PROMPT_BASE.format(crops_spec=_CROPS_PORTRAIT)
PROMPT_LANDSCAPE = _PROMPT_BASE.format(crops_spec=_CROPS_LANDSCAPE)


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
            -- Structured labels (Gemini-equivalent)
            setting           TEXT,
            time_of_day       TEXT,
            weather           TEXT,
            grading_style     TEXT,
            exposure_label    TEXT,
            sharpness_label   TEXT,
            vibes             TEXT,
            faces_count       INTEGER,
            semantic_pops     TEXT,
            -- Meta
            model             TEXT,
            processed_at      TEXT NOT NULL
        );
    """)
    # Add new columns to existing table if needed
    for col, ctype in [
        ("setting", "TEXT"), ("time_of_day", "TEXT"), ("weather", "TEXT"),
        ("grading_style", "TEXT"), ("exposure_label", "TEXT"),
        ("sharpness_label", "TEXT"), ("vibes", "TEXT"),
        ("faces_count", "INTEGER"), ("semantic_pops", "TEXT"),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM gemma_analysis LIMIT 0")
        except sqlite3.OperationalError:
            conn.execute(f"ALTER TABLE gemma_analysis ADD COLUMN {col} {ctype}")
            conn.commit()


def load_pick_uuids() -> tuple[list[str], dict[str, str]]:
    """Load pick UUIDs from picks.json, filtering out variant IDs.
    Returns (uuids, orientation_map) where orientation_map[uuid] = 'portrait'|'landscape'.
    """
    picks_path = PICKS_JSON
    if not picks_path.exists():
        alt = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"
        if alt.exists():
            picks_path = alt
    data = json.loads(picks_path.read_text())
    orientation = {}
    for u in data.get("portrait", []):
        if "_" not in u:
            orientation[u] = "portrait"
    for u in data.get("landscape", []):
        if "_" not in u:
            orientation.setdefault(u, "landscape")
    uuids = list(dict.fromkeys(
        [u for u in data["portrait"] if "_" not in u] +
        [u for u in data["landscape"] if "_" not in u]
    ))
    return uuids, orientation


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


_REQUIRED_FIELDS = [
    "visual_weight", "energy_direction", "archetype", "color_temp",
    "cartoon_style", "story_silly", "story_poetic", "story_surrealist",
    "story_noir", "story_romantic", "print_worthy",
    "vibes",
]


def get_pending_uuids(
    conn: sqlite3.Connection, all_uuids: list[str], rerun: bool,
) -> list[str]:
    """Determine which UUIDs need processing.
    A row is complete only if ALL required fields are non-NULL and non-empty.
    """
    if rerun:
        return all_uuids
    try:
        cols = ", ".join(_REQUIRED_FIELDS)
        rows = conn.execute(
            f"SELECT uuid, {cols} FROM gemma_analysis"
        ).fetchall()
    except sqlite3.OperationalError:
        return all_uuids

    done = set()
    for row in rows:
        uuid = row[0]
        fields = row[1:]
        # All required fields must be non-NULL and non-empty
        if all(f is not None and f != "" for f in fields):
            done.add(uuid)
    return [u for u in all_uuids if u not in done]


def query_gemma(img_path: str, model: str = MODEL_DEFAULT,
                prompt: str = PROMPT_LANDSCAPE,
                retries: int = 3) -> dict | None:
    """Send image to Gemma via Ollama and parse JSON response. Retries on failure."""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
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
            # Connection refused = Ollama down, wait longer
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

    # Vibes: should be a JSON array of strings
    vibes = parsed.get("vibes", [])
    if isinstance(vibes, list):
        vibes_json = json.dumps([str(v).lower().strip() for v in vibes], ensure_ascii=False)
    elif isinstance(vibes, str):
        vibes_json = json.dumps([v.strip().lower() for v in vibes.split(",")], ensure_ascii=False)
    else:
        vibes_json = "[]"

    # Semantic pops: should be a JSON array of {color, object, impact}
    pops = parsed.get("semantic_pops", [])
    if isinstance(pops, list):
        pops_json = json.dumps(pops, ensure_ascii=False)
    else:
        pops_json = "[]"

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
        # Gemini-redundant fields — no longer generated, NULLed for new rows
        # (existing data preserved for 2,415 rows already processed)
        "setting": None,
        "time_of_day": None,
        "weather": None,
        "grading_style": None,
        "faces_count": None,
        # Gemma-unique structured labels
        "exposure_label": _to_str(parsed.get("exposure_label", "")),
        "sharpness_label": _to_str(parsed.get("sharpness_label", "")),
        "vibes": vibes_json,
        "semantic_pops": pops_json,
    }


_INSERT_SQL = """
    INSERT INTO gemma_analysis (
        uuid, raw_json, description, subject, story, mood,
        composition, lighting, colors, texture, technical, strength,
        tags, print_worthy, cartoon_style, crops,
        story_silly, story_poetic, story_surrealist, story_noir, story_romantic,
        visual_weight, energy_direction, archetype, color_temp,
        setting, time_of_day, weather, grading_style,
        exposure_label, sharpness_label, vibes, faces_count, semantic_pops,
        model, processed_at
    ) VALUES (
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
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
        setting = excluded.setting,
        time_of_day = excluded.time_of_day,
        weather = excluded.weather,
        grading_style = excluded.grading_style,
        exposure_label = excluded.exposure_label,
        sharpness_label = excluded.sharpness_label,
        vibes = excluded.vibes,
        faces_count = excluded.faces_count,
        semantic_pops = excluded.semantic_pops,
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
        fields.get("setting"),
        fields.get("time_of_day"),
        fields.get("weather"),
        fields.get("grading_style"),
        fields.get("exposure_label", ""),
        fields.get("sharpness_label", ""),
        fields.get("vibes", "[]"),
        fields.get("faces_count"),
        fields.get("semantic_pops", "[]"),
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


def process_one(uuid: str, img_path: str, model: str,
                prompt: str = PROMPT_LANDSCAPE) -> dict:
    """Process a single image. Returns result dict with 'parsed' or 'error'."""
    if not Path(img_path).exists():
        return {"uuid": uuid, "error": f"file not found — {img_path}"}
    try:
        parsed = query_gemma(img_path, model, prompt=prompt)
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
    parser.add_argument("--all", action="store_true",
                        help="Process ALL images, not just picks")
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
    orientation_map = {}
    if args.uuids_file:
        with open(args.uuids_file, 'r') as f:
            all_uuids = [line.strip() for line in f if line.strip()]
        print(f"Loaded {len(all_uuids)} UUIDs from {args.uuids_file}")
    elif args.all:
        all_uuids = [r[0] for r in conn.execute("SELECT uuid FROM images ORDER BY uuid").fetchall()]
        print(f"All images: {len(all_uuids)} UUIDs")
    else:
        all_uuids, orientation_map = load_pick_uuids()

    paths = get_mobile_paths(conn, all_uuids)
    label = "All" if args.all else "Picks"
    print(f"{label}: {len(all_uuids)} UUIDs, {len(paths)} have mobile JPEGs")

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
        active: dict = {}
        pending_iter = iter(pending_uuids)

        def submit_next():
            """Submit next image from pending queue."""
            try:
                uuid = next(pending_iter)
                f = pool.submit(
                    process_one, uuid, paths[uuid], model,
                    prompt=PROMPT_PORTRAIT if orientation_map.get(uuid) == "portrait" else PROMPT_LANDSCAPE,
                )
                active[f] = uuid
            except StopIteration:
                pass

        # Prime the pool with initial batch
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

                # Submit next
                submit_next()

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
