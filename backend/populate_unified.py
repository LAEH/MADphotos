#!/usr/bin/env python3
"""Populate unified_labels and unified_texts from all signal tables.

Creates a cross-model label index and a caption/prose layer that enables
consensus queries, best-caption resolution, and full signal profiles.

Usage:
    python3 backend/populate_unified.py              # incremental (skip existing)
    python3 backend/populate_unified.py --rebuild    # drop + rebuild from scratch
    python3 backend/populate_unified.py --stats      # show counts only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import database as db

# ── Tag Classification Vocabularies ─────────────────────────────────────────

OBJECT_NOUNS = frozenset({
    "person", "man", "woman", "child", "baby", "boy", "girl", "people", "crowd",
    "car", "truck", "bus", "motorcycle", "bicycle", "train", "airplane", "boat",
    "cat", "dog", "bird", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "fish", "rabbit", "deer", "lion", "tiger", "monkey", "duck",
    "tree", "flower", "plant", "grass", "leaf", "bush", "palm tree", "cactus",
    "building", "house", "church", "tower", "bridge", "fence", "wall", "gate",
    "window", "door", "roof", "staircase", "balcony", "column",
    "table", "chair", "bench", "sofa", "bed", "desk", "shelf",
    "bottle", "cup", "glass", "plate", "bowl", "fork", "knife", "spoon",
    "phone", "laptop", "computer", "keyboard", "mouse", "camera", "clock",
    "book", "newspaper", "magazine", "pen", "umbrella", "bag", "suitcase",
    "hat", "shoe", "sunglasses", "tie", "shirt", "dress", "jacket",
    "lamp", "candle", "mirror", "vase", "sculpture", "painting", "sign",
    "flag", "ball", "kite", "skateboard", "surfboard", "skis",
    "food", "fruit", "bread", "cake", "pizza", "rice",
    "street", "road", "sidewalk", "path", "alley",
    "river", "lake", "ocean", "sea", "waterfall", "mountain", "rock", "sand",
    "snow", "cloud", "rain", "sun", "moon", "star", "sky",
    "fire", "smoke", "fog", "mist",
})

VIBE_WORDS = frozenset({
    "moody", "nostalgic", "gritty", "minimalist", "dramatic", "serene",
    "contemplative", "dreamy", "ethereal", "melancholic", "romantic", "raw",
    "cinematic", "atmospheric", "intimate", "powerful", "haunting", "elegant",
    "bold", "quiet", "mysterious", "playful", "vibrant", "somber", "intense",
    "peaceful", "lonely", "whimsical", "surreal", "poetic", "gloomy",
    "majestic", "tender", "fierce", "delicate", "austere", "lush",
    "warm", "cold", "dark", "light", "soft", "harsh",
    "monumental", "resilient", "isolated", "vulnerable", "solitude",
    "humanity", "strength", "contemplation", "vulnerability",
    "awe", "wonder", "stillness", "tension", "calm", "chaos",
    "urban", "rural", "industrial", "organic",
})

TECHNIQUE_WORDS = frozenset({
    "leading lines", "shallow depth of field", "negative space",
    "rule of thirds", "bokeh", "symmetry", "reflection", "silhouette",
    "long exposure", "double exposure", "panning", "tilt shift",
    "framing", "layering", "juxtaposition", "repetition", "pattern",
    "diagonal", "converging lines", "vanishing point", "golden ratio",
    "filling the frame", "selective focus", "backlighting",
    "high contrast", "low key", "high key",
    "vertical composition", "horizontal composition",
    "off-center", "centered", "dynamic",
})

TEXTURE_WORDS = frozenset({
    "concrete", "metal", "wood", "glass", "fabric", "stone", "rust",
    "leather", "brick", "marble", "steel", "iron", "ceramic", "paper",
    "silk", "wool", "cotton", "linen", "velvet", "denim",
    "rough", "smooth", "glossy", "matte", "weathered", "polished",
    "cracked", "peeling", "worn", "aged", "patina",
    "grain", "grit", "gravel", "sand", "bark", "moss",
})


def classify_tag(tag: str) -> str:
    """Classify a normalized tag into a semantic category."""
    tag_lower = tag.lower().strip()
    if tag_lower in OBJECT_NOUNS:
        return "object"
    if tag_lower in VIBE_WORDS:
        return "vibe"
    if tag_lower in TECHNIQUE_WORDS:
        return "technique"
    if tag_lower in TEXTURE_WORDS:
        return "texture"
    # Check partial matches for multi-word vibe/technique
    for v in VIBE_WORDS:
        if v in tag_lower or tag_lower in v:
            return "vibe"
    for t in TECHNIQUE_WORDS:
        if t in tag_lower or tag_lower in t:
            return "technique"
    for t in TEXTURE_WORDS:
        if t in tag_lower or tag_lower in t:
            return "texture"
    return "tag"


# ── Table Creation ──────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS unified_labels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    image_uuid      TEXT NOT NULL,
    label           TEXT NOT NULL,
    category        TEXT NOT NULL,
    source_model    TEXT NOT NULL,
    source_table    TEXT NOT NULL,
    confidence      REAL,
    rank_in_source  INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ul_unique
    ON unified_labels(image_uuid, label, category, source_model);
CREATE INDEX IF NOT EXISTS idx_ul_label ON unified_labels(label);
CREATE INDEX IF NOT EXISTS idx_ul_cat_label ON unified_labels(category, label);
CREATE INDEX IF NOT EXISTS idx_ul_image ON unified_labels(image_uuid);
CREATE INDEX IF NOT EXISTS idx_ul_source ON unified_labels(source_model);

CREATE TABLE IF NOT EXISTS unified_texts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    image_uuid      TEXT NOT NULL,
    text_type       TEXT NOT NULL,
    content         TEXT NOT NULL,
    source_model    TEXT NOT NULL,
    source_table    TEXT NOT NULL,
    priority        INTEGER NOT NULL,
    char_count      INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ut_unique
    ON unified_texts(image_uuid, text_type, source_model);
CREATE INDEX IF NOT EXISTS idx_ut_image_type
    ON unified_texts(image_uuid, text_type, priority);
"""


def create_tables(conn: Any) -> None:
    conn.executescript(SCHEMA_SQL)


def drop_tables(conn: Any) -> None:
    conn.execute("DROP TABLE IF EXISTS unified_labels")
    conn.execute("DROP TABLE IF EXISTS unified_texts")
    conn.commit()


# ── Label Insertion Helper ──────────────────────────────────────────────────

def insert_label(
    conn: Any,
    image_uuid: str,
    label: str,
    category: str,
    source_model: str,
    source_table: str,
    confidence: Optional[float] = None,
    rank_in_source: Optional[int] = None,
) -> None:
    """Insert or ignore a single unified label."""
    label = label.lower().strip()
    if not label or len(label) < 2:
        return
    conn.execute("""
        INSERT INTO unified_labels
            (image_uuid, label, category, source_model, source_table, confidence, rank_in_source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(image_uuid, label, category, source_model) DO UPDATE SET
            confidence = MAX(excluded.confidence, unified_labels.confidence),
            rank_in_source = MIN(excluded.rank_in_source, unified_labels.rank_in_source)
    """, (image_uuid, label, category, source_model, source_table, confidence, rank_in_source))


def insert_text(
    conn: Any,
    image_uuid: str,
    text_type: str,
    content: str,
    source_model: str,
    source_table: str,
    priority: int,
) -> None:
    """Insert or ignore a single unified text."""
    content = content.strip()
    if not content:
        return
    conn.execute("""
        INSERT INTO unified_texts
            (image_uuid, text_type, content, source_model, source_table, priority, char_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(image_uuid, text_type, source_model) DO UPDATE SET
            content = excluded.content,
            priority = excluded.priority,
            char_count = excluded.char_count
    """, (image_uuid, text_type, content, source_model, source_table, priority, len(content)))


# ── Population Sources ──────────────────────────────────────────────────────

def populate_gemini_vibes(conn: Any) -> int:
    """Source 1: gemini_analysis.vibe → category 'vibe'."""
    rows = conn.execute("""
        SELECT image_uuid, vibe FROM gemini_analysis
        WHERE vibe IS NOT NULL AND vibe != ''
    """).fetchall()
    count = 0
    for r in rows:
        try:
            vibes = json.loads(r["vibe"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(vibes, list):
            continue
        for i, v in enumerate(vibes):
            if isinstance(v, str) and v.strip():
                insert_label(conn, r["image_uuid"], v, "vibe",
                             "gemini-2.5-pro", "gemini_analysis", 0.85, i + 1)
                count += 1
    conn.commit()
    return count


def populate_gemini_categoricals(conn: Any) -> int:
    """Source 2: gemini categoricals → scene/time/style/technique."""
    rows = conn.execute("""
        SELECT image_uuid, setting, time_of_day, grading_style,
               composition_technique, geometry
        FROM gemini_analysis
        WHERE raw_json IS NOT NULL AND error IS NULL
    """).fetchall()
    count = 0
    for r in rows:
        uuid = r["image_uuid"]
        if r["setting"] and r["setting"].strip():
            insert_label(conn, uuid, r["setting"], "scene",
                         "gemini-2.5-pro", "gemini_analysis", 0.90, 1)
            count += 1
        if r["time_of_day"] and r["time_of_day"].strip():
            insert_label(conn, uuid, r["time_of_day"], "time",
                         "gemini-2.5-pro", "gemini_analysis", 0.90, 1)
            count += 1
        if r["grading_style"] and r["grading_style"].strip():
            insert_label(conn, uuid, r["grading_style"], "style",
                         "gemini-2.5-pro", "gemini_analysis", 0.90, 1)
            count += 1
        if r["composition_technique"] and r["composition_technique"].strip():
            insert_label(conn, uuid, r["composition_technique"], "technique",
                         "gemini-2.5-pro", "gemini_analysis", 0.90, 1)
            count += 1
    conn.commit()
    return count


def populate_gemini_geometry(conn: Any) -> int:
    """Source 3: gemini_analysis.geometry → category 'technique'."""
    rows = conn.execute("""
        SELECT image_uuid, geometry FROM gemini_analysis
        WHERE geometry IS NOT NULL AND geometry != ''
    """).fetchall()
    count = 0
    for r in rows:
        try:
            geom = json.loads(r["geometry"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(geom, list):
            continue
        for i, g in enumerate(geom):
            if isinstance(g, str) and g.strip():
                insert_label(conn, r["image_uuid"], g, "technique",
                             "gemini-2.5-pro", "gemini_analysis", 0.85, i + 1)
                count += 1
    conn.commit()
    return count


def populate_ram_tags(conn: Any) -> int:
    """Source 4: image_tags → classified via classify_tag()."""
    rows = conn.execute("""
        SELECT image_uuid, tags, confidence_json FROM image_tags
        WHERE tags IS NOT NULL AND tags != ''
    """).fetchall()
    count = 0
    for r in rows:
        tags_list = [t.strip() for t in r["tags"].split("|") if t.strip()]
        conf_map = {}
        if r["confidence_json"]:
            try:
                conf_map = json.loads(r["confidence_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        for i, tag in enumerate(tags_list):
            tag_lower = tag.lower().strip()
            raw_conf = conf_map.get(tag)
            if raw_conf is not None:
                # Normalize RAM-Plus confidence: clamp((raw - 0.15) / 0.35, 0, 1)
                conf = max(0.0, min(1.0, (raw_conf - 0.15) / 0.35))
            else:
                conf = 0.5
            category = classify_tag(tag_lower)
            insert_label(conn, r["image_uuid"], tag_lower, category,
                         "ram-plus", "image_tags", round(conf, 3), i + 1)
            count += 1
    conn.commit()
    return count


def populate_yolo_objects(conn: Any) -> int:
    """Source 5: object_detections → category 'object'."""
    rows = conn.execute("""
        SELECT image_uuid, label, confidence
        FROM object_detections
        WHERE label IS NOT NULL
        ORDER BY image_uuid, confidence DESC
    """).fetchall()
    count = 0
    prev_uuid = None
    rank = 0
    for r in rows:
        if r["image_uuid"] != prev_uuid:
            prev_uuid = r["image_uuid"]
            rank = 0
        rank += 1
        insert_label(conn, r["image_uuid"], r["label"], "object",
                     "yolov8", "object_detections",
                     round(r["confidence"] or 0, 3), rank)
        count += 1
    conn.commit()
    return count


def populate_open_detections(conn: Any) -> int:
    """Source 6: open_detections → category 'object' (top 15 per image)."""
    rows = conn.execute("""
        SELECT image_uuid, label, confidence
        FROM open_detections
        WHERE label IS NOT NULL
        ORDER BY image_uuid, confidence DESC
    """).fetchall()
    count = 0
    prev_uuid = None
    rank = 0
    for r in rows:
        if r["image_uuid"] != prev_uuid:
            prev_uuid = r["image_uuid"]
            rank = 0
        rank += 1
        if rank > 15:
            continue
        insert_label(conn, r["image_uuid"], r["label"], "object",
                     "florence-dino", "open_detections",
                     round(r["confidence"] or 0, 3), rank)
        count += 1
    conn.commit()
    return count


def populate_scenes(conn: Any) -> int:
    """Source 7: scene_classification.scene_1 → category 'scene'."""
    rows = conn.execute("""
        SELECT image_uuid, scene_1, score_1 FROM scene_classification
        WHERE scene_1 IS NOT NULL AND scene_1 != ''
    """).fetchall()
    count = 0
    for r in rows:
        insert_label(conn, r["image_uuid"], r["scene_1"], "scene",
                     "places365", "scene_classification",
                     round(r["score_1"] or 0, 3), 1)
        count += 1
    conn.commit()
    return count


def populate_styles(conn: Any) -> int:
    """Source 8: style_classification → category 'style'."""
    rows = conn.execute("""
        SELECT image_uuid, style, confidence FROM style_classification
        WHERE style IS NOT NULL AND style != ''
    """).fetchall()
    count = 0
    for r in rows:
        insert_label(conn, r["image_uuid"], r["style"], "style",
                     "resnet50", "style_classification",
                     round(r["confidence"] or 0.70, 3), 1)
        count += 1
    conn.commit()
    return count


def populate_emotions(conn: Any) -> int:
    """Source 9: facial_emotions → category 'emotion'."""
    rows = conn.execute("""
        SELECT image_uuid, face_index, dominant_emotion, confidence
        FROM facial_emotions
        WHERE dominant_emotion IS NOT NULL AND dominant_emotion != ''
        ORDER BY image_uuid, face_index
    """).fetchall()
    count = 0
    prev_uuid = None
    rank = 0
    for r in rows:
        if r["image_uuid"] != prev_uuid:
            prev_uuid = r["image_uuid"]
            rank = 0
        rank += 1
        insert_label(conn, r["image_uuid"], r["dominant_emotion"], "emotion",
                     "deepface", "facial_emotions",
                     round(r["confidence"] or 0, 3), rank)
        count += 1
    conn.commit()
    return count


def populate_colors(conn: Any) -> int:
    """Source 10: dominant_colors.color_name → category 'color'."""
    rows = conn.execute("""
        SELECT image_uuid, color_name, percentage
        FROM dominant_colors
        WHERE color_name IS NOT NULL AND color_name != ''
        ORDER BY image_uuid, percentage DESC
    """).fetchall()
    count = 0
    prev_uuid = None
    rank = 0
    for r in rows:
        if r["image_uuid"] != prev_uuid:
            prev_uuid = r["image_uuid"]
            rank = 0
        rank += 1
        insert_label(conn, r["image_uuid"], r["color_name"], "color",
                     "kmeans", "dominant_colors",
                     round(r["percentage"] or 0, 3), rank)
        count += 1
    conn.commit()
    return count


def populate_gemma(conn: Any) -> int:
    """Source 11: gemma_picks → mood words → 'vibe', tags → classified."""
    rows = conn.execute("""
        SELECT uuid, gemma_json, gemma_mood, gemma_tags FROM gemma_picks
    """).fetchall()
    count = 0
    for r in rows:
        uuid = r["uuid"]

        # Mood words → vibe
        mood = r["gemma_mood"] or ""
        for i, word in enumerate(w.strip() for w in mood.split(",") if w.strip()):
            insert_label(conn, uuid, word, "vibe",
                         "gemma-3-4b", "gemma_picks", 0.80, i + 1)
            count += 1

        # Tags → classified
        tags_str = r["gemma_tags"] or ""
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        for i, tag in enumerate(tags):
            conf = max(0.38, round(0.80 - (i * 0.03), 2))
            category = classify_tag(tag)
            insert_label(conn, uuid, tag, category,
                         "gemma-3-4b", "gemma_picks", conf, i + 1)
            count += 1

    conn.commit()
    return count


# ── Text Population ─────────────────────────────────────────────────────────

def populate_captions_short(conn: Any) -> int:
    """caption_short: Florence short → priority 1, BLIP → priority 2."""
    count = 0

    # Florence short_caption (priority 1)
    rows = conn.execute("""
        SELECT image_uuid, short_caption FROM florence_captions
        WHERE short_caption IS NOT NULL AND short_caption != ''
    """).fetchall()
    for r in rows:
        insert_text(conn, r["image_uuid"], "caption_short", r["short_caption"],
                    "florence-2-large", "florence_captions", 1)
        count += 1

    # BLIP caption (priority 2)
    rows = conn.execute("""
        SELECT image_uuid, caption FROM image_captions
        WHERE caption IS NOT NULL AND caption != ''
    """).fetchall()
    for r in rows:
        insert_text(conn, r["image_uuid"], "caption_short", r["caption"],
                    "blip", "image_captions", 2)
        count += 1

    conn.commit()
    return count


def populate_captions_detailed(conn: Any) -> int:
    """caption_detailed: Gemma → 1, Gemini alt_text → 2, Florence detailed → 3."""
    count = 0

    # Gemma description (priority 1, picks only)
    rows = conn.execute("""
        SELECT uuid, gemma_description FROM gemma_picks
        WHERE gemma_description IS NOT NULL AND gemma_description != ''
    """).fetchall()
    for r in rows:
        insert_text(conn, r["uuid"], "caption_detailed", r["gemma_description"],
                    "gemma-3-4b", "gemma_picks", 1)
        count += 1

    # Gemini alt_text (priority 2)
    rows = conn.execute("""
        SELECT image_uuid, alt_text FROM gemini_analysis
        WHERE alt_text IS NOT NULL AND alt_text != '' AND error IS NULL
    """).fetchall()
    for r in rows:
        insert_text(conn, r["image_uuid"], "caption_detailed", r["alt_text"],
                    "gemini-2.5-pro", "gemini_analysis", 2)
        count += 1

    # Florence detailed_caption (priority 3)
    rows = conn.execute("""
        SELECT image_uuid, detailed_caption FROM florence_captions
        WHERE detailed_caption IS NOT NULL AND detailed_caption != ''
    """).fetchall()
    for r in rows:
        insert_text(conn, r["image_uuid"], "caption_detailed", r["detailed_caption"],
                    "florence-2-large", "florence_captions", 3)
        count += 1

    conn.commit()
    return count


def populate_captions_rich(conn: Any) -> int:
    """caption_rich: Gemma → 1, Florence more_detailed → 2."""
    count = 0

    # Gemma description (priority 1)
    rows = conn.execute("""
        SELECT uuid, gemma_description FROM gemma_picks
        WHERE gemma_description IS NOT NULL AND gemma_description != ''
    """).fetchall()
    for r in rows:
        insert_text(conn, r["uuid"], "caption_rich", r["gemma_description"],
                    "gemma-3-4b", "gemma_picks", 1)
        count += 1

    # Florence more_detailed (priority 2)
    rows = conn.execute("""
        SELECT image_uuid, more_detailed FROM florence_captions
        WHERE more_detailed IS NOT NULL AND more_detailed != ''
    """).fetchall()
    for r in rows:
        insert_text(conn, r["image_uuid"], "caption_rich", r["more_detailed"],
                    "florence-2-large", "florence_captions", 2)
        count += 1

    conn.commit()
    return count


def populate_gemma_texts(conn: Any) -> int:
    """Gemma-only text types: story, subject, mood, critique_*."""
    rows = conn.execute("""
        SELECT uuid, gemma_json FROM gemma_picks
        WHERE gemma_json IS NOT NULL
    """).fetchall()
    count = 0
    for r in rows:
        try:
            parsed = json.loads(r["gemma_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        uuid = r["uuid"]

        field_map = {
            "story": "story",
            "subject": "subject",
            "mood": "mood",
            "critique_composition": "composition",
            "critique_lighting": "lighting",
            "critique_colors": "colors",
            "critique_texture": "texture",
            "critique_technical": "technical",
            "critique_strength": "strength",
        }
        for text_type, json_key in field_map.items():
            val = parsed.get(json_key)
            if val and isinstance(val, str) and val.strip():
                insert_text(conn, uuid, text_type, val.strip(),
                            "gemma-3-4b", "gemma_picks", 1)
                count += 1

    conn.commit()
    return count


# ── Stats ───────────────────────────────────────────────────────────────────

def print_stats(conn: Any) -> None:
    print("\n=== unified_labels ===")
    rows = conn.execute("""
        SELECT category, COUNT(*) as cnt,
               COUNT(DISTINCT label) as unique_labels,
               COUNT(DISTINCT image_uuid) as images
        FROM unified_labels
        GROUP BY category
        ORDER BY cnt DESC
    """).fetchall()
    total = 0
    for r in rows:
        print(f"  {r['category']:12s}  {r['cnt']:>8,} rows  "
              f"{r['unique_labels']:>6,} labels  {r['images']:>6,} images")
        total += r["cnt"]
    print(f"  {'TOTAL':12s}  {total:>8,} rows")

    # Consensus
    consensus = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT image_uuid, label FROM unified_labels
            GROUP BY image_uuid, label
            HAVING COUNT(DISTINCT source_model) >= 2
        )
    """).fetchone()[0]
    print(f"\n  Consensus pairs (2+ models agree): {consensus:,}")

    print("\n=== unified_texts ===")
    rows = conn.execute("""
        SELECT text_type, COUNT(*) as cnt,
               COUNT(DISTINCT image_uuid) as images
        FROM unified_texts
        GROUP BY text_type
        ORDER BY text_type
    """).fetchall()
    total = 0
    for r in rows:
        print(f"  {r['text_type']:24s}  {r['cnt']:>6,} rows  {r['images']:>6,} images")
        total += r["cnt"]
    print(f"  {'TOTAL':24s}  {total:>6,} rows")


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Populate unified signal tables")
    parser.add_argument("--rebuild", action="store_true", help="Drop and recreate tables")
    parser.add_argument("--stats", action="store_true", help="Show stats only")
    args = parser.parse_args()

    conn = db.get_connection()

    if args.stats:
        print_stats(conn)
        conn.close()
        return

    if args.rebuild:
        print("Dropping existing unified tables...")
        drop_tables(conn)

    print("Creating tables...")
    create_tables(conn)

    print("\nPopulating unified_labels...")
    total_labels = 0

    n = populate_gemini_vibes(conn)
    print(f"  1. Gemini vibes:        {n:>8,}")
    total_labels += n

    n = populate_gemini_categoricals(conn)
    print(f"  2. Gemini categoricals: {n:>8,}")
    total_labels += n

    n = populate_gemini_geometry(conn)
    print(f"  3. Gemini geometry:     {n:>8,}")
    total_labels += n

    n = populate_ram_tags(conn)
    print(f"  4. RAM-Plus tags:       {n:>8,}")
    total_labels += n

    n = populate_yolo_objects(conn)
    print(f"  5. YOLO objects:        {n:>8,}")
    total_labels += n

    n = populate_open_detections(conn)
    print(f"  6. Open detections:     {n:>8,}")
    total_labels += n

    n = populate_scenes(conn)
    print(f"  7. Places365 scenes:    {n:>8,}")
    total_labels += n

    n = populate_styles(conn)
    print(f"  8. ResNet50 styles:     {n:>8,}")
    total_labels += n

    n = populate_emotions(conn)
    print(f"  9. DeepFace emotions:   {n:>8,}")
    total_labels += n

    n = populate_colors(conn)
    print(f" 10. Dominant colors:     {n:>8,}")
    total_labels += n

    n = populate_gemma(conn)
    print(f" 11. Gemma picks:         {n:>8,}")
    total_labels += n

    print(f"\n  Total labels inserted: {total_labels:,}")

    print("\nPopulating unified_texts...")
    total_texts = 0

    n = populate_captions_short(conn)
    print(f"  caption_short:     {n:>6,}")
    total_texts += n

    n = populate_captions_detailed(conn)
    print(f"  caption_detailed:  {n:>6,}")
    total_texts += n

    n = populate_captions_rich(conn)
    print(f"  caption_rich:      {n:>6,}")
    total_texts += n

    n = populate_gemma_texts(conn)
    print(f"  gemma texts:       {n:>6,}")
    total_texts += n

    print(f"\n  Total texts inserted: {total_texts:,}")

    print_stats(conn)
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
