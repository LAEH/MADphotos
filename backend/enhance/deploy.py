"""Deploy accepted enhancement proposals: render tiers, upload GCS, update DB."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageFilter

from . import (DISPLAY_JPEG_DIR, ENHANCED_DIR, ENHANCED_EXPOSURE_DIR, PROJECT_ROOT)
from .db import ensure_tables, get_accepted_undeployed, get_connection, mark_deployed
from .preview import render_border_crop, render_gemma_crop, render_rotation

GCS_BASE = "gs://myproject-public-assets/art/MADphotos/v/enhanced"

TIER_CONFIGS = [
    # (name, long_edge, jpeg_q, webp_q, progressive, subsampling, sharpen)
    ("display", 2048, 88, 82, True, 1, None),
    ("mobile", 1280, 85, 80, True, 1, (0.4, 50, 2)),
    ("thumb", 480, 82, 78, False, 2, (0.3, 60, 2)),
    ("micro", 64, 70, 68, False, 2, None),
]


def _apply_transform(proposal: dict) -> Image.Image | None:
    """Apply the proposal's transformation to the display-tier source.
    Uses render_combined for multi-transform proposals (same as preview)."""
    uuid = proposal["image_uuid"]
    params = json.loads(proposal["params_json"])
    source = DISPLAY_JPEG_DIR / f"{uuid}.jpg"

    if not source.exists():
        print(f"  SKIP {uuid}: display source not found")
        return None

    from .preview import render_combined
    try:
        return render_combined(source, params)
    except Exception as e:
        print(f"  SKIP {uuid}: render failed: {e}")
        return None


def _render_tiers(uuid: str, img: Image.Image) -> list[Path]:
    """Render all serving tiers for one image. Returns list of created files."""
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
        jpeg_dir = ENHANCED_DIR / name / "jpeg"
        jpeg_dir.mkdir(parents=True, exist_ok=True)
        jpeg_path = jpeg_dir / f"{uuid}.jpg"
        tier_img.save(
            str(jpeg_path), format="JPEG", quality=jpeg_q, optimize=True,
            progressive=progressive, subsampling=subsampling,
        )
        created.append(jpeg_path)

        # WebP
        webp_dir = ENHANCED_DIR / name / "webp"
        webp_dir.mkdir(parents=True, exist_ok=True)
        webp_path = webp_dir / f"{uuid}.webp"
        tier_img.save(
            str(webp_path), format="WEBP", quality=webp_q, method=4, exact=False,
        )
        created.append(webp_path)

    return created


def _upload_to_gcs(uuid: str, files: list[Path]) -> int:
    """Upload tier files to GCS. Returns number of successful uploads."""
    uploaded = 0
    for f in files:
        # Determine GCS path from local path structure
        # e.g. .../enhanced/display/jpeg/uuid.jpg → gs://.../display/jpeg/uuid.jpg
        parts = f.parts
        # Find 'enhanced' in path and take everything after
        try:
            idx = parts.index("enhanced")
        except ValueError:
            continue
        rel = "/".join(parts[idx + 1:])
        gcs_path = f"{GCS_BASE}/{rel}"

        result = subprocess.run(
            [
                "gcloud", "storage", "cp", str(f), gcs_path,
                "--cache-control=public, max-age=31536000, immutable",
                "--quiet",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            uploaded += 1
        else:
            print(f"  GCS error for {f.name}: {result.stderr.strip()}")
    return uploaded


def _mark_enhancement_plans(conn, uuids: set) -> int:
    """Mark enhancement_plans.status = 'accepted' for compatibility with export_gallery.py."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    for uuid in uuids:
        conn.execute(
            """UPDATE enhancement_plans
               SET status = 'accepted', reviewed_at = ?
               WHERE image_uuid = ? AND status != 'accepted'""",
            (now, uuid),
        )
        updated += conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    return updated


def deploy_accepted(skip_gcs: bool = False) -> dict:
    """Deploy all accepted-but-undeployed proposals."""
    conn = get_connection()
    ensure_tables(conn)

    proposals = get_accepted_undeployed(conn)
    if not proposals:
        print("No accepted proposals to deploy.")
        conn.close()
        return {"deployed": 0}

    print(f"Deploying {len(proposals)} accepted proposals...")
    deployed_ids = []
    exposure_uuids = set()
    total_uploads = 0

    for i, p in enumerate(proposals):
        uuid = p["image_uuid"]
        ptype = p["type"]
        print(f"  [{i+1}/{len(proposals)}] {ptype}: {uuid}")

        img = _apply_transform(p)
        if img is None:
            continue

        files = _render_tiers(uuid, img)
        print(f"    Rendered {len(files)} tier files")

        if not skip_gcs:
            uploaded = _upload_to_gcs(uuid, files)
            total_uploads += uploaded
            print(f"    Uploaded {uploaded} to GCS")

        deployed_ids.append(p["id"])

        # Track exposure proposals for enhancement_plans compatibility
        if ptype == "exposure":
            exposure_uuids.add(uuid)

    # Mark proposals as deployed
    if deployed_ids:
        marked = mark_deployed(conn, deployed_ids)
        print(f"\nMarked {marked} proposals as deployed")

    # Update enhancement_plans for exposure enhancements (export_gallery.py compat)
    if exposure_uuids:
        ep_updated = _mark_enhancement_plans(conn, exposure_uuids)
        print(f"Updated {ep_updated} enhancement_plans rows to 'accepted'")

    conn.close()

    result = {
        "deployed": len(deployed_ids),
        "gcs_uploads": total_uploads,
        "types": {},
    }
    for p in proposals:
        t = p["type"]
        result["types"][t] = result["types"].get(t, 0) + 1

    print(f"\nDone: {len(deployed_ids)} deployed, {total_uploads} GCS uploads")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deploy accepted enhancements")
    parser.add_argument("--skip-gcs", action="store_true")
    args = parser.parse_args()
    deploy_accepted(skip_gcs=args.skip_gcs)
