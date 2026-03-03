"""Generated (smart_style) variants API + stub endpoints."""
from __future__ import annotations

import json
import sqlite3

from ._common import DB_PATH, GENERATED_DIR, PROJECT_ROOT, RENDERED_DIR

_UUID_NS = None


def _uuid_ns():
    global _UUID_NS
    if _UUID_NS is None:
        import uuid as _u
        _UUID_NS = _u.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    return _UUID_NS


def _variant_id_for(image_uuid: str, style_key: str) -> str:
    import uuid as _u
    return str(_u.uuid5(_uuid_ns(), f"{image_uuid}:smart_{style_key}"))


def _qwen_variant_id_for(image_uuid: str, style_key: str) -> str:
    import uuid as _u
    return str(_u.uuid5(_uuid_ns(), f"{image_uuid}:{style_key}"))


def get_generated_data():
    """Return unreviewed smart_style and qwen_variant variants for the review UI."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        # Get unreviewed successful variants from DB (smart_style + qwen_variant)
        unreviewed = conn.execute(
            "SELECT variant_id, image_uuid, prompt, variant_type FROM ai_variants "
            "WHERE variant_type IN ('smart_style', 'qwen_variant') "
            "AND generation_status='success' "
            "AND review_status IS NULL"
        ).fetchall()
        # Get counts
        counts = conn.execute(
            "SELECT review_status, COUNT(*) as cnt FROM ai_variants "
            "WHERE variant_type IN ('smart_style', 'qwen_variant') "
            "AND generation_status='success' "
            "GROUP BY review_status"
        ).fetchall()
        conn.close()
    except Exception:
        return {"pairs": [], "run_dir": None, "accepted": 0, "rejected": 0}

    accepted = sum(r["cnt"] for r in counts if r["review_status"] == "accepted")
    rejected = sum(r["cnt"] for r in counts if r["review_status"] == "rejected")

    # Build a map of uuid -> list of run_dirs (a UUID may appear in multiple runs)
    uuid_to_runs: dict[str, list[str]] = {}
    if GENERATED_DIR.exists():
        for run_dir in sorted(GENERATED_DIR.iterdir(), reverse=True):
            if not run_dir.is_dir() or run_dir.name.startswith("."):
                continue
            for uuid_dir in run_dir.iterdir():
                if uuid_dir.is_dir():
                    uuid_to_runs.setdefault(uuid_dir.name, []).append(run_dir.name)

    pairs = []
    for row in unreviewed:
        uid = row["image_uuid"]
        vid = row["variant_id"]
        vtype = row["variant_type"]
        runs = uuid_to_runs.get(uid, [])
        found = False

        # Determine file glob pattern based on variant type
        if vtype == "qwen_variant":
            glob_pattern = "qwen_*.jpg"
            prefix = "qwen_"
        else:
            glob_pattern = "imagen_smart_*.jpg"
            prefix = "imagen_smart_"

        for run in runs:
            uuid_dir = GENERATED_DIR / run / uid
            for vf in uuid_dir.glob(glob_pattern):
                style_key = vf.stem.replace(prefix, "", 1)
                check_id = _qwen_variant_id_for(uid, style_key) if vtype == "qwen_variant" else _variant_id_for(uid, style_key)
                if check_id == vid:
                    orig_file = GENERATED_DIR / run / uid / "original.jpg"
                    if orig_file.exists():
                        orig_path = f"/generated/{run}/{uid}/original.jpg"
                    else:
                        orig_path = f"/images/display/{uid}.jpg"
                    pairs.append({
                        "variant_id": vid,
                        "uuid": uid,
                        "original_path": orig_path,
                        "variant_path": f"/generated/{run}/{uid}/{vf.name}",
                        "style_name": style_key,
                        "style_prompt": row["prompt"] or "",
                        "strength": 0,
                        "why": "",
                        "rotation": 0,
                        "review": None,
                        "variant_type": vtype,
                    })
                    found = True
                    break
            if found:
                break

    return {
        "pairs": pairs,
        "run_dir": None,
        "accepted": accepted,
        "rejected": rejected,
    }


def review_generated(variant_id: str, status, comment: str | None = None):
    """Update review_status (and optional comment) for a smart_style variant."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute(
            "UPDATE ai_variants SET review_status = ?, review_comment = ? WHERE variant_id = ?",
            (status, comment or None, variant_id),
        )
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_variant_review_data():
    """Return accepted variants for the disk review page."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT v.variant_id, v.image_uuid, v.style_key, v.variant_type, "
            "v.review_status, v.prompt "
            "FROM ai_variants v "
            "WHERE v.generation_status='success' AND v.review_status='accepted' "
            "ORDER BY v.variant_type, v.variant_id"
        ).fetchall()
        conn.close()
    except Exception:
        return {"variants": []}

    # Build filesystem map: uuid -> (run_dir, files)
    uuid_to_runs: dict[str, list[tuple[str, list[str]]]] = {}
    if GENERATED_DIR.exists():
        for run_dir in sorted(GENERATED_DIR.iterdir(), reverse=True):
            if not run_dir.is_dir() or run_dir.name.startswith("."):
                continue
            for uuid_dir in run_dir.iterdir():
                if not uuid_dir.is_dir():
                    continue
                files = [f.name for f in uuid_dir.iterdir() if f.is_file()]
                if uuid_dir.name not in uuid_to_runs:
                    uuid_to_runs[uuid_dir.name] = []
                uuid_to_runs[uuid_dir.name].append((run_dir.name, files))

    # Also check rendered thumb/display for originals
    rendered_dir = GENERATED_DIR.parent.parent / "images" / "rendered"

    variants = []
    for row in rows:
        uid = row["image_uuid"]
        vid = row["variant_id"]
        vtype = row["variant_type"]
        style = row["style_key"] or ""

        # Find variant file on disk
        original_path = None
        variant_path = None

        runs = uuid_to_runs.get(uid, [])
        for run_name, files in runs:
            # Find original — check on disk, fall back to rendered display tier
            if "original.jpg" in files:
                original_path = f"/generated/{run_name}/{uid}/original.jpg"
            elif not original_path:
                display_file = RENDERED_DIR / "display" / "jpeg" / f"{uid}.jpg"
                if display_file.exists():
                    original_path = f"/images/display/{uid}.jpg"

            # Find variant file matching style
            if vtype == "nst":
                fname = f"{style}.jpg"
                if fname in files:
                    variant_path = f"/generated/{run_name}/{uid}/{fname}"
            elif vtype == "smart_style":
                fname = f"imagen_smart_{style}.jpg"
                if fname in files:
                    variant_path = f"/generated/{run_name}/{uid}/{fname}"
            elif vtype == "qwen_variant":
                fname = f"qwen_{style}.jpg"
                if fname in files:
                    variant_path = f"/generated/{run_name}/{uid}/{fname}"
            elif vtype in ("style_transfer", "cartoon", "gemma_cartoon"):
                # Legacy types — try pattern matching
                for f in files:
                    if f != "original.jpg" and f.endswith(".jpg"):
                        if style in f or vtype in f:
                            variant_path = f"/generated/{run_name}/{uid}/{f}"
                            break

            if original_path and variant_path:
                break

        if not original_path or not variant_path:
            continue

        variants.append({
            "variant_id": vid,
            "uuid": uid,
            "style_key": style,
            "variant_type": vtype,
            "review_status": row["review_status"],
            "original_path": original_path,
            "variant_path": variant_path,
            "prompt": row["prompt"] or "",
        })

    return {"variants": variants}


def batch_reject_variants(variant_ids: list[str]):
    """Reject a batch of variants by ID."""
    if not variant_ids:
        return {"ok": True, "count": 0}
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        placeholders = ",".join("?" for _ in variant_ids)
        conn.execute(
            f"UPDATE ai_variants SET review_status='rejected' WHERE variant_id IN ({placeholders})",
            variant_ids,
        )
        conn.commit()
        count = conn.total_changes
        conn.close()
        return {"ok": True, "count": count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_unpicked_data():
    """Return unpicked images for the curation UI."""
    return {"images": []}


def get_location_tagger_data(camera=None, obj=None):
    """Return picks that have no location tag, with filter options."""
    picks_path = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"
    if not picks_path.exists():
        return {"photos": [], "locations": [], "tagged_count": 0, "total_count": 0, "cameras": [], "objects": []}

    picks_data = json.loads(picks_path.read_text())
    pick_uuids = set()
    for o in ("landscape", "portrait"):
        pick_uuids.update(picks_data.get(o, []))

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row

    # Already-tagged UUIDs
    tagged = set(r[0] for r in conn.execute(
        "SELECT image_uuid FROM image_locations WHERE location_name IS NOT NULL AND location_name != ''"
    ).fetchall())

    # Distinct location names for chips
    locations = sorted(set(r[0] for r in conn.execute(
        "SELECT DISTINCT location_name FROM image_locations WHERE location_name IS NOT NULL AND location_name != ''"
    ).fetchall()))

    # Camera list from EXIF
    cameras = sorted(set(r[0] for r in conn.execute(
        "SELECT DISTINCT model FROM exif_metadata WHERE model IS NOT NULL AND model != ''"
    ).fetchall()))

    # Top object labels
    obj_rows = conn.execute(
        "SELECT label, COUNT(*) as cnt FROM object_detections GROUP BY label ORDER BY cnt DESC LIMIT 30"
    ).fetchall()
    objects = [{"label": r["label"], "count": r["cnt"]} for r in obj_rows]

    # Build set of UUIDs matching filters
    filter_uuids = None
    if camera:
        filter_uuids = set(r[0] for r in conn.execute(
            "SELECT image_uuid FROM exif_metadata WHERE model = ?", (camera,)
        ).fetchall())
    if obj:
        obj_uuids = set(r[0] for r in conn.execute(
            "SELECT DISTINCT image_uuid FROM object_detections WHERE label = ?", (obj,)
        ).fetchall())
        filter_uuids = obj_uuids if filter_uuids is None else filter_uuids & obj_uuids

    # Untagged picks (optionally filtered)
    untagged = pick_uuids - tagged
    if filter_uuids is not None:
        untagged = untagged & filter_uuids

    # Build photo list with category + thumb URL
    photos = []
    for uid in sorted(untagged):
        row = conn.execute("SELECT category FROM images WHERE uuid = ?", (uid,)).fetchone()
        cat = row["category"] if row else "unknown"
        photos.append({
            "uuid": uid,
            "category": cat,
            "thumb_url": f"/rendered/thumb/jpeg/{uid}.jpg",
            "predicted": None,
        })

    conn.close()
    return {
        "photos": photos,
        "locations": locations,
        "tagged_count": len(tagged & pick_uuids),
        "total_count": len(pick_uuids),
        "cameras": cameras,
        "objects": objects,
    }


def do_pick(uuids):
    """Toggle pick status for a list of UUIDs."""
    return {"ok": True, "uuids": uuids}


def tag_location(uuid, location):
    """Tag an image with a location name."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT OR REPLACE INTO image_locations (image_uuid, location_name, source, accepted) "
        "VALUES (?, ?, 'manual', 1)",
        (uuid, location)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


def untag_location(uuid):
    """Remove location tag from an image."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DELETE FROM image_locations WHERE image_uuid = ?", (uuid,))
    conn.commit()
    conn.close()
    return {"ok": True}


def register_location(name):
    """Register a new location name for tagging."""
    return {"ok": True, "name": name}


def get_show_photography():
    """Return all picked photos for the Show Content / Photography page."""
    picks_path = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"
    if not picks_path.exists():
        return {"photos": [], "portrait": 0, "landscape": 0}

    picks_data = json.loads(picks_path.read_text())
    portrait_ids = picks_data.get("portrait", [])
    landscape_ids = picks_data.get("landscape", [])
    all_ids = portrait_ids + landscape_ids
    portrait_set = set(portrait_ids)

    if not all_ids:
        return {"photos": [], "portrait": 0, "landscape": 0}

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row

    placeholders = ",".join("?" * len(all_ids))
    rows = conn.execute(f"""
        SELECT i.uuid, i.category, i.subcategory, i.width, i.height,
               e.make AS camera_make, e.model AS camera_model,
               qs.combined_score AS quality
        FROM images i
        LEFT JOIN exif_metadata e ON e.image_uuid = i.uuid
        LEFT JOIN quality_scores qs ON qs.image_uuid = i.uuid
        WHERE i.uuid IN ({placeholders})
    """, all_ids).fetchall()
    conn.close()

    cameras = {}
    photos = []
    for r in rows:
        uuid = r["uuid"]
        cam = r["camera_model"] or r["camera_make"] or "Unknown"
        cameras[cam] = cameras.get(cam, 0) + 1
        photos.append({
            "uuid": uuid,
            "category": r["category"],
            "orientation": "portrait" if uuid in portrait_set else "landscape",
            "w": r["width"],
            "h": r["height"],
            "camera": cam,
            "quality": round(r["quality"], 1) if r["quality"] else None,
        })

    return {
        "photos": photos,
        "portrait": len(portrait_ids),
        "landscape": len(landscape_ids),
        "cameras": cameras,
    }


def get_show_variants():
    """Return all deployed variants for the Show Content / Variants page."""
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT v.variant_id, v.image_uuid, v.variant_type, v.style_key, v.prompt,
               v.review_status, v.exported_at, v.created_at,
               i.category, i.subcategory
        FROM ai_variants v
        LEFT JOIN images i ON i.uuid = v.image_uuid
        WHERE v.review_status = 'accepted'
          AND v.exported_at IS NOT NULL
          AND v.generation_status = 'success'
        ORDER BY v.exported_at DESC
    """).fetchall()
    conn.close()

    styles = {}
    photos = []
    for r in rows:
        style = r["style_key"] or "unknown"
        styles[style] = styles.get(style, 0) + 1
        photos.append({
            "variant_id": r["variant_id"],
            "parent": r["image_uuid"],
            "style": style,
            "category": r["category"],
            "exported_at": r["exported_at"],
        })

    return {
        "variants": photos,
        "total": len(photos),
        "styles": styles,
    }
