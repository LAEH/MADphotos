#!/usr/bin/env python3
"""
run_gemma_deep.py — Deep visual analysis via Gemma 3 27B for all picked photos.

Extracts signals that directly improve the Show app experience:
  - Object-level color mapping (Colors view: semantic color search)
  - Visual structure analysis (Bento view: hero vs supporting placement)
  - Pairing descriptors (Couple view: better matching)
  - Style transfer readiness (generation: predict best styles, avoid bad ones)
  - Emotional/aesthetic essence (all views: richer curation)

Results stored in `gemma_deep` table in mad_photos.db.

Usage:
    python3 run_gemma_deep.py              # all pending picks
    python3 run_gemma_deep.py --limit 10   # first 10 (testing)
    python3 run_gemma_deep.py --rerun      # reprocess all
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
PICKS_JSON = PROJECT_ROOT / "frontend" / "show" / "public" / "data" / "picks.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_DEFAULT = "gemma3:4b"
FLUSH_SIZE = 20

# The 8 style keys from generate_smart_variants.py
STYLE_KEYS = "archer, gonzo, ukiyoe, batman, pixar, moebius, sumie, marvel"

PROMPT = (
    "Analyze this photograph for a visual art application. "
    "Respond ONLY with valid JSON, no markdown, no backticks.\n\n"
    "{\n"
    '  "should_rotate": "none|cw90|ccw90|180 (is this image wrongly rotated? none if correct)",\n'
    '  "salient_objects": [\n'
    '    {"object": "name", "color": "color name", "hex": "#rrggbb", '
    '"position": "center|top|bottom|left|right|top-left|top-right|bottom-left|bottom-right", '
    '"salience": "high|medium (how much it grabs attention)"}\n'
    "  ],\n"
    '  "color_regions": [\n'
    '    {"object": "what this colored area is", "color_name": "simple color name", '
    '"hex": "#rrggbb", "area": "large|medium|small"}\n'
    "  ],\n"
    '  "color_harmony": "complementary|analogous|triadic|monochromatic|split-complementary|neutral",\n'
    '  "color_mood": "2-4 word color feeling",\n'
    '  "color_contrast": "high|medium|low (overall tonal contrast)",\n'
    '  "dominant_material": "metal|wood|fabric|stone|glass|water|foliage|skin|concrete|mixed",\n'
    '  "texture_richness": "smooth|subtle|moderate|rich|extreme",\n'
    '  "visual_complexity": "1-5 integer (1=minimal/zen, 5=extremely busy)",\n'
    '  "focal_strength": "strong|moderate|weak|none",\n'
    '  "negative_space": "none|minimal|moderate|generous|dominant",\n'
    '  "depth_layers": "flat|shallow|medium|deep (how many depth planes are visible)",\n'
    '  "line_quality": "geometric|organic|diagonal|curved|mixed|minimal",\n'
    '  "symmetry": "symmetric|near-symmetric|asymmetric-balanced|asymmetric|radial",\n'
    '  "best_crop_subject": "what the ideal tight crop centers on",\n'
    '  "grid_role": "hero|supporting|versatile",\n'
    '  "edge_colors": {"top": "#hex", "bottom": "#hex", "left": "#hex", "right": "#hex"},\n'
    '  "pair_words": ["6-8 abstract words for matching similar photos"],\n'
    '  "emotional_intensity": "1-10 integer",\n'
    '  "scene_mood": "1-3 word mood essence",\n'
    '  "time_feel": "dawn|morning|golden-hour|midday|afternoon|blue-hour|night|overcast|timeless",\n'
    '  "season_feel": "spring|summer|autumn|winter|tropical|arid|timeless",\n'
    '  "isolation_level": "crowded|populated|sparse|solitary|empty",\n'
    f'  "best_styles": ["2-3 from: {STYLE_KEYS}"],\n'
    '  "style_reasoning": "1 sentence why",\n'
    f'  "avoid_styles": ["1-2 from: {STYLE_KEYS}"],\n'
    '  "avoid_reasoning": "1 sentence why",\n'
    '  "transform_ease": "easy|medium|hard",\n'
    '  "preserve_elements": ["2-3 key elements that must survive style transfer"],\n'
    '  "abstract_essence": "1 sentence: what this image IS as pure visual pattern",\n'
    '  "reminds_of": "what famous artist, film, or visual style this evokes (1 phrase)"\n'
    "}\n\n"
    "RULES:\n"
    "- should_rotate: Check if the image looks sideways or upside down. 'none' if it looks correct.\n"
    "- salient_objects: List 1-5 visually striking colored objects that grab the eye. "
    "These are SPECIFIC things (red door, yellow taxi, blue jacket) not backgrounds.\n"
    "- color_regions: ALL distinct colored areas, largest first, 3-8 entries. "
    "Include backgrounds (sky, wall, floor, shadow areas).\n"
    "- hex values must be valid 6-digit hex colors\n"
    "- pair_words: abstract concepts for finding visually similar photos "
    "(e.g. geometry, warmth, solitude, texture, horizon, symmetry, rhythm, decay, glow)\n"
    "- Style keys are exactly: archer (Archer TV), gonzo (Ralph Steadman), "
    "ukiyoe (Japanese woodblock), batman (Batman TAS noir), pixar (Pixar 3D), "
    "moebius (European Ligne Claire), sumie (sumi-e ink wash), marvel (Marvel comics)\n"
    "- Output ONLY valid JSON"
)


def init_table(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gemma_deep (
            image_uuid          TEXT PRIMARY KEY,
            raw_json            TEXT NOT NULL,
            should_rotate       TEXT,
            salient_objects     TEXT,
            color_regions       TEXT,
            color_harmony       TEXT,
            color_mood          TEXT,
            color_contrast      TEXT,
            dominant_material   TEXT,
            texture_richness    TEXT,
            visual_complexity   INTEGER,
            focal_strength      TEXT,
            negative_space      TEXT,
            depth_layers        TEXT,
            line_quality        TEXT,
            symmetry            TEXT,
            grid_role           TEXT,
            edge_colors         TEXT,
            pair_words          TEXT,
            emotional_intensity INTEGER,
            scene_mood          TEXT,
            time_feel           TEXT,
            season_feel         TEXT,
            isolation_level     TEXT,
            best_styles         TEXT,
            style_reasoning     TEXT,
            avoid_styles        TEXT,
            avoid_reasoning     TEXT,
            transform_ease      TEXT,
            preserve_elements   TEXT,
            abstract_essence    TEXT,
            reminds_of          TEXT,
            processed_at        TEXT NOT NULL
        );
    """)


def load_pick_uuids() -> list[str]:
    data = json.loads(PICKS_JSON.read_text())
    return list(dict.fromkeys(data.get("portrait", []) + data.get("landscape", [])))


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


def get_processed(conn: sqlite3.Connection) -> set[str]:
    try:
        return {r[0] for r in conn.execute("SELECT image_uuid FROM gemma_deep").fetchall()}
    except sqlite3.OperationalError:
        return set()


def query_gemma(img_path: str, model: str) -> dict | None:
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
    resp = urllib.request.urlopen(req, timeout=300)
    result = json.loads(resp.read())
    text = result.get("response", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _to_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


def _to_int(val, default: int = 0) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            return default
    return default


def _json_list(val) -> str:
    if isinstance(val, list):
        return json.dumps(val, ensure_ascii=False)
    return _to_str(val)


def _csv_list(val) -> str:
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return _to_str(val)


def flush_batch(conn: sqlite3.Connection, batch: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for row in batch:
        p = row["parsed"]

        conn.execute("""
            INSERT INTO gemma_deep (
                image_uuid, raw_json, should_rotate, salient_objects,
                color_regions, color_harmony, color_mood, color_contrast,
                dominant_material, texture_richness, visual_complexity,
                focal_strength, negative_space, depth_layers, line_quality, symmetry,
                grid_role, edge_colors, pair_words, emotional_intensity,
                scene_mood, time_feel, season_feel, isolation_level,
                best_styles, style_reasoning, avoid_styles, avoid_reasoning,
                transform_ease, preserve_elements, abstract_essence, reminds_of,
                processed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(image_uuid) DO UPDATE SET
                raw_json=excluded.raw_json,
                should_rotate=excluded.should_rotate,
                salient_objects=excluded.salient_objects,
                color_regions=excluded.color_regions,
                color_harmony=excluded.color_harmony,
                color_mood=excluded.color_mood,
                color_contrast=excluded.color_contrast,
                dominant_material=excluded.dominant_material,
                texture_richness=excluded.texture_richness,
                visual_complexity=excluded.visual_complexity,
                focal_strength=excluded.focal_strength,
                negative_space=excluded.negative_space,
                depth_layers=excluded.depth_layers,
                line_quality=excluded.line_quality,
                symmetry=excluded.symmetry,
                grid_role=excluded.grid_role,
                edge_colors=excluded.edge_colors,
                pair_words=excluded.pair_words,
                emotional_intensity=excluded.emotional_intensity,
                scene_mood=excluded.scene_mood,
                time_feel=excluded.time_feel,
                season_feel=excluded.season_feel,
                isolation_level=excluded.isolation_level,
                best_styles=excluded.best_styles,
                style_reasoning=excluded.style_reasoning,
                avoid_styles=excluded.avoid_styles,
                avoid_reasoning=excluded.avoid_reasoning,
                transform_ease=excluded.transform_ease,
                preserve_elements=excluded.preserve_elements,
                abstract_essence=excluded.abstract_essence,
                reminds_of=excluded.reminds_of,
                processed_at=excluded.processed_at
        """, (
            row["uuid"],
            json.dumps(p, ensure_ascii=False),
            _to_str(p.get("should_rotate")),
            _json_list(p.get("salient_objects", [])),
            _json_list(p.get("color_regions", [])),
            _to_str(p.get("color_harmony")),
            _to_str(p.get("color_mood")),
            _to_str(p.get("color_contrast")),
            _to_str(p.get("dominant_material")),
            _to_str(p.get("texture_richness")),
            _to_int(p.get("visual_complexity")),
            _to_str(p.get("focal_strength")),
            _to_str(p.get("negative_space")),
            _to_str(p.get("depth_layers")),
            _to_str(p.get("line_quality")),
            _to_str(p.get("symmetry")),
            _to_str(p.get("grid_role")),
            json.dumps(p.get("edge_colors", {}), ensure_ascii=False),
            _csv_list(p.get("pair_words", [])),
            _to_int(p.get("emotional_intensity")),
            _to_str(p.get("scene_mood")),
            _to_str(p.get("time_feel")),
            _to_str(p.get("season_feel")),
            _to_str(p.get("isolation_level")),
            _csv_list(p.get("best_styles", [])),
            _to_str(p.get("style_reasoning")),
            _csv_list(p.get("avoid_styles", [])),
            _to_str(p.get("avoid_reasoning")),
            _to_str(p.get("transform_ease")),
            _json_list(p.get("preserve_elements", [])),
            _to_str(p.get("abstract_essence")),
            _to_str(p.get("reminds_of")),
            now,
        ))
    conn.commit()


def process_one(uuid: str, img_path: str, model: str) -> dict | None:
    """Process a single image. Returns result dict or None on error."""
    if not Path(img_path).exists():
        return {"uuid": uuid, "error": "file not found"}
    try:
        parsed = query_gemma(img_path, model)
        if parsed is None:
            raise ValueError("Empty response")
        return {"uuid": uuid, "parsed": parsed}
    except Exception as e:
        return {"uuid": uuid, "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Deep visual analysis via Gemma 3")
    parser.add_argument("--limit", type=int, help="Max images to process")
    parser.add_argument("--rerun", action="store_true", help="Reprocess all")
    parser.add_argument("--model", type=str, default=MODEL_DEFAULT,
                        help=f"Ollama model (default: {MODEL_DEFAULT})")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel workers (default: 4)")
    args = parser.parse_args()

    model = args.model
    workers = max(1, args.workers)

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    init_table(conn)

    all_uuids = load_pick_uuids()
    paths = get_mobile_paths(conn, all_uuids)
    print(f"Picks: {len(all_uuids)}, with mobile JPEGs: {len(paths)}")

    if args.rerun:
        pending = [u for u in all_uuids if u in paths]
    else:
        done = get_processed(conn)
        pending = [u for u in all_uuids if u in paths and u not in done]
        print(f"Already done: {len(done)}, pending: {len(pending)}")

    if args.limit:
        pending = pending[:args.limit]

    if not pending:
        print("Nothing to do.")
        conn.close()
        return

    print(f"Processing {len(pending)} images with {model} ({workers} workers)...")

    from tqdm import tqdm
    t0 = time.time()
    ok = 0
    errors = 0
    error_msgs: list[str] = []
    batch: list[dict] = []
    db_lock = threading.Lock()
    bar = tqdm(total=len(pending), desc="gemma-deep", unit="img",
               bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]")

    def flush_locked(b: list[dict]) -> None:
        with db_lock:
            flush_batch(conn, b)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(process_one, uid, paths[uid], model): uid
            for uid in pending
        }
        for future in as_completed(futures):
            result = future.result()
            bar.update(1)

            if "error" in result:
                errors += 1
                if len(error_msgs) < 10:
                    error_msgs.append(f"{result['uuid']}: {result['error']}")
                continue

            parsed = result["parsed"]
            rot = parsed.get("should_rotate", "?")
            sal = len(parsed.get("salient_objects", []))
            sty = ", ".join(parsed.get("best_styles", [])[:2])
            bar.set_postfix_str(f"rot={rot} sal={sal} sty={sty}")

            batch.append(result)
            ok += 1
            if len(batch) >= FLUSH_SIZE:
                flush_locked(list(batch))
                batch.clear()

    bar.close()

    if batch:
        flush_batch(conn, batch)

    conn.close()
    elapsed = time.time() - t0

    print(f"\nDone in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  OK:     {ok}")
    print(f"  Errors: {errors}")
    if ok > 0:
        print(f"  Avg:    {elapsed/ok:.1f}s/image")

    if error_msgs:
        print(f"\nFirst {len(error_msgs)} errors:")
        for msg in error_msgs:
            print(f"  {msg}")


if __name__ == "__main__":
    main()
