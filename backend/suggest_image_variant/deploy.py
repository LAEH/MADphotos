"""Deploy accepted smart_style variants: extract colors, render tiers, upload GCS, update DB."""
from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageFilter

from .config import DB_PATH, PROJECT_ROOT

# ── Prompt → style_key extraction patterns ─────────────────────────────────
# Each tuple: (substring_to_match_in_prompt, style_key)
# Order matters — first match wins. More specific patterns first.
_PROMPT_STYLE_PATTERNS = [
    ("Archer animated", "archer"),
    ("Ralph Steadman", "gonzo"),
    ("Batman", "batman"),
    ("Animated Series", "batman"),
    ("Scraperboard", "scraperboard"),
    ("Scratchboard", "scraperboard"),
    ("ukiyo-e", "ukiyoe"),
    ("Hokusai", "ukiyoe"),
    ("Hiroshige", "ukiyoe"),
    ("sumi-e", "sumie"),
    ("ink wash painting", "sumie"),
    ("Pixar", "pixar"),
    ("3D render", "pixar"),
    ("Studio Ghibli", "ghibli"),
    ("Miyazaki", "ghibli"),
    ("Moebius", "moebius"),
    ("Ligne Claire", "moebius"),
    ("Makoto Shinkai", "shinkai"),
    ("Your Name", "shinkai"),
    ("Hugo Pratt", "hugopratt"),
    ("Corto Maltese", "hugopratt"),
    ("Sin City", "sincity"),
    ("Frank Miller", "sincity"),
    ("Saul Bass", "saulbass"),
    ("Banksy", "banksy"),
    ("stencil street art", "banksy"),
    ("Alphonse Mucha", "mucha"),
    ("Art Nouveau", "mucha"),
    ("Technicolor", "technicolor"),
    ("Fauvist explosion", "technicolor"),
    ("Matisse cutouts", "technicolor"),
    ("Marvel comic", "marvel"),
    ("Jack Kirby", "marvel"),
    ("Jim Steranko", "marvel"),
    ("manga", "marvel"),
    ("One Piece", "marvel"),
    ("linocut", "linocut"),
    ("linoleum block", "linocut"),
    ("woodcut", "woodcut"),
    ("wood grain texture", "woodcut"),
    ("Monet", "impressionist"),
    ("Renoir", "impressionist"),
    ("Impressionist", "impressionist"),
    ("watercolor", "watercolor"),
    ("editorial illustration", "editorial"),
    ("Bold black ink drawing", "boldink"),
    ("BALANCED variant", "balanced_v2"),
    ("LIGHT variant", "ligneclaire_v2"),
    ("DARK variant", "sincity_v2"),
]


def _extract_style_key(prompt: str) -> str | None:
    """Extract style_key from prompt text using known signature patterns."""
    for pattern, key in _PROMPT_STYLE_PATTERNS:
        if pattern in prompt:
            return key
    return None


def backfill_style_keys() -> dict:
    """One-time: extract style_key from prompt text for all smart_style variants.

    Adds the style_key column if missing, then parses prompt text for known
    style signatures and populates the column.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Add column if it doesn't exist
    cols = [r[1] for r in conn.execute("PRAGMA table_info(ai_variants)").fetchall()]
    if "style_key" not in cols:
        conn.execute("ALTER TABLE ai_variants ADD COLUMN style_key TEXT")
        conn.commit()
        print("Added style_key column to ai_variants")

    # Fetch all smart_style rows missing style_key
    rows = conn.execute("""
        SELECT variant_id, prompt FROM ai_variants
        WHERE variant_type = 'smart_style' AND (style_key IS NULL OR style_key = '')
    """).fetchall()

    if not rows:
        print("No rows to backfill — all smart_style variants already have style_key.")
        conn.close()
        return {"updated": 0, "unmatched": 0}

    updated = 0
    unmatched = 0
    for r in rows:
        key = _extract_style_key(r["prompt"])
        if key:
            conn.execute(
                "UPDATE ai_variants SET style_key = ? WHERE variant_id = ?",
                (key, r["variant_id"]),
            )
            updated += 1
        else:
            unmatched += 1

    conn.commit()
    conn.close()

    print(f"Backfilled {updated} rows, {unmatched} unmatched")
    return {"updated": updated, "unmatched": unmatched}

GENERATED_DIR = PROJECT_ROOT / "backend" / "suggest_image_variant" / "output"
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
VARIANT_RENDERED_DIR = RENDERED_DIR / "variants"
GCS_VARIANTS_PREFIX = "gs://myproject-public-assets/art/MADphotos/v/variants"

TIER_CONFIGS = [
    # (name, long_edge, jpeg_q, webp_q, progressive, subsampling, sharpen)
    ("display", 1024, 88, 82, True, 1, (0.5, 40, 2)),
    ("mobile", 768, 85, 80, True, 1, (0.4, 50, 2)),
    ("thumb", 480, 82, 78, False, 2, (0.3, 60, 2)),
    ("micro", 64, 70, 68, False, 2, None),
]


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _scan_variant_files() -> Dict[str, Path]:
    """Scan suggest_image_variant/output/ to build variant_id → file_path mapping."""
    import re
    import uuid

    UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    smart_re = re.compile(r"^imagen_smart_(.+)\.jpg$")
    qwen_re = re.compile(r"^qwen_(.+)\.jpg$")
    mapping: Dict[str, Path] = {}

    if not GENERATED_DIR.exists():
        return mapping

    run_dirs = sorted(d for d in GENERATED_DIR.iterdir() if d.is_dir())
    for run_dir in run_dirs:
        for uuid_dir in run_dir.iterdir():
            if not uuid_dir.is_dir():
                continue
            image_uuid = uuid_dir.name
            for img_file in uuid_dir.iterdir():
                if not img_file.name.endswith(".jpg"):
                    continue
                ms = smart_re.match(img_file.name)
                if ms:
                    style_key = ms.group(1)
                    vid = str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:smart_{style_key}"))
                    mapping[vid] = img_file
                    continue
                mq = qwen_re.match(img_file.name)
                if mq:
                    style_key = mq.group(1)
                    vid = str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:{style_key}"))
                    mapping[vid] = img_file

    return mapping


def _extract_colors(conn: sqlite3.Connection, variant_id: str, file_path: Path) -> int:
    """Extract dominant colors for one variant. Returns number of clusters inserted."""
    from backend.extract_variant_colors import extract_colors_for_image

    clusters = extract_colors_for_image(file_path, n_clusters=5)
    if not clusters:
        return 0

    ts = datetime.now(timezone.utc).isoformat()
    for c in clusters:
        conn.execute("""
            INSERT OR REPLACE INTO dominant_colors (
                image_uuid, cluster_index, r, g, b, hex, l, a, b_val,
                percentage, color_name, analyzed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            variant_id, c["cluster_index"], c["r"], c["g"], c["b"], c["hex"],
            c["l"], c["a"], c["b_val"],
            c["percentage"], c["color_name"], ts,
        ))
    return len(clusters)


def _render_tiers(variant_id: str, file_path: Path) -> List[Path]:
    """Render all serving tiers for one variant. Returns list of created files."""
    img = Image.open(file_path)
    img.load()
    img = img.convert("RGB")
    w, h = img.size
    created = []

    for name, long_edge, jpeg_q, webp_q, progressive, subsampling, sharpen in TIER_CONFIGS:
        cur_long = max(w, h)
        if cur_long > long_edge:
            ratio = long_edge / cur_long
            tier_img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        else:
            tier_img = img.copy()

        if sharpen:
            tier_img = tier_img.filter(ImageFilter.UnsharpMask(*sharpen))

        # JPEG
        jpeg_dir = VARIANT_RENDERED_DIR / name / "jpeg"
        jpeg_dir.mkdir(parents=True, exist_ok=True)
        jpeg_path = jpeg_dir / f"{variant_id}.jpg"
        tier_img.save(
            str(jpeg_path), format="JPEG", quality=jpeg_q, optimize=True,
            progressive=progressive, subsampling=subsampling,
        )
        created.append(jpeg_path)

        # WebP
        webp_dir = VARIANT_RENDERED_DIR / name / "webp"
        webp_dir.mkdir(parents=True, exist_ok=True)
        webp_path = webp_dir / f"{variant_id}.webp"
        tier_img.save(
            str(webp_path), format="WEBP", quality=webp_q, method=4, exact=False,
        )
        created.append(webp_path)

    return created


_GCS_BUCKET = "myproject-public-assets"
_GCS_BASE = "art/MADphotos/v"
_GCS_CACHE = "public, max-age=31536000, immutable"
_gcs_client = None


def _get_gcs_bucket():
    """Lazy-init GCS client using application-default credentials."""
    global _gcs_client
    if _gcs_client is None:
        from google.cloud import storage as gcs
        _gcs_client = gcs.Client()
    return _gcs_client.bucket(_GCS_BUCKET)


def _upload_source_to_gcs(variant_id: str, file_path: Path) -> bool:
    """Upload the source JPEG to GCS. Returns True on success."""
    try:
        bucket = _get_gcs_bucket()
        blob = bucket.blob(f"{_GCS_BASE}/variants/{variant_id}.jpg")
        blob.cache_control = _GCS_CACHE
        blob.upload_from_filename(str(file_path), content_type="image/jpeg")
        return True
    except Exception as e:
        print(f"  GCS error for {variant_id}: {e}")
        return False


def _upload_tiers_to_gcs(variant_id: str, tier_files: List[Path]) -> int:
    """Upload rendered tier files to GCS. Returns number of successful uploads."""
    uploaded = 0
    try:
        bucket = _get_gcs_bucket()
    except Exception as e:
        print(f"  GCS init error: {e}")
        return 0
    for f in tier_files:
        parts = f.parts
        try:
            idx = parts.index("variants")
        except ValueError:
            continue
        gcs_key = f"{_GCS_BASE}/{'/'.join(parts[idx:])}"
        content_type = "image/webp" if f.suffix == ".webp" else "image/jpeg"
        try:
            blob = bucket.blob(gcs_key)
            blob.cache_control = _GCS_CACHE
            blob.upload_from_filename(str(f), content_type=content_type)
            uploaded += 1
        except Exception as e:
            print(f"  GCS tier error for {f.name}: {e}")
    return uploaded


def deploy_accepted(skip_gcs: bool = False) -> dict:
    """Deploy all accepted-but-unexported smart_style variants.

    Pipeline:
    1. Query accepted variants not yet exported
    2. Extract colors (K-means LAB, 5 clusters)
    3. Render 4 tiers (display/mobile/thumb/micro in jpeg+webp)
    4. Upload source + tiers to GCS
    5. Mark exported_at in ai_variants
    """
    conn = _get_connection()

    rows = conn.execute("""
        SELECT variant_id, image_uuid, variant_type, prompt
        FROM ai_variants
        WHERE variant_type IN ('smart_style', 'qwen_variant')
          AND review_status = 'accepted'
          AND exported_at IS NULL
          AND generation_status = 'success'
    """).fetchall()

    if not rows:
        print("No accepted variants to deploy.")
        conn.close()
        return {"deployed": 0}

    print(f"Deploying {len(rows)} accepted variants...")

    # Build file map
    file_map = _scan_variant_files()
    print(f"  Found {len(file_map)} variant files on disk")

    deployed_ids = []
    total_colors = 0
    total_tiers = 0
    total_gcs = 0
    t0 = time.time()

    for i, r in enumerate(rows):
        vid = r["variant_id"]
        print(f"  [{i+1}/{len(rows)}] {vid[:12]}...")

        if vid not in file_map:
            print(f"    SKIP: source file not found")
            continue

        file_path = file_map[vid]

        # 1. Extract colors
        n_colors = _extract_colors(conn, vid, file_path)
        total_colors += n_colors
        print(f"    Colors: {n_colors} clusters")

        # 2. Render tiers
        tier_files = _render_tiers(vid, file_path)
        total_tiers += len(tier_files)
        print(f"    Rendered: {len(tier_files)} tier files")

        # 3. Upload to GCS
        if not skip_gcs:
            _upload_source_to_gcs(vid, file_path)
            uploaded = _upload_tiers_to_gcs(vid, tier_files)
            total_gcs += uploaded + 1
            print(f"    GCS: {uploaded + 1} uploads")

        deployed_ids.append(vid)

    # 4. Mark exported
    if deployed_ids:
        now = datetime.now(timezone.utc).isoformat()
        for vid in deployed_ids:
            conn.execute(
                "UPDATE ai_variants SET exported_at = ? WHERE variant_id = ?",
                (now, vid),
            )
        conn.commit()
        print(f"\nMarked {len(deployed_ids)} variants as exported")

    conn.close()
    elapsed = time.time() - t0

    result = {
        "deployed": len(deployed_ids),
        "colors_extracted": total_colors,
        "tiers_rendered": total_tiers,
        "gcs_uploads": total_gcs,
        "elapsed_seconds": round(elapsed, 1),
    }
    print(f"Done: {len(deployed_ids)} deployed, {total_tiers} tiers, "
          f"{total_gcs} GCS uploads in {elapsed:.1f}s")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deploy accepted style variants")
    parser.add_argument("--skip-gcs", action="store_true",
                        help="Skip GCS uploads (local render + DB only)")
    args = parser.parse_args()
    deploy_accepted(skip_gcs=args.skip_gcs)
