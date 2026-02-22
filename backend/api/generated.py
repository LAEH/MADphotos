"""Generated (smart_style) variants API + stub endpoints."""
from __future__ import annotations

import sqlite3

from ._common import DB_PATH, GENERATED_DIR

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


def get_generated_data():
    """Return unreviewed smart_style variants for the review UI."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        # Get unreviewed successful variants from DB
        unreviewed = conn.execute(
            "SELECT variant_id, image_uuid, prompt FROM ai_variants "
            "WHERE variant_type='smart_style' AND generation_status='success' "
            "AND review_status IS NULL"
        ).fetchall()
        # Get counts
        counts = conn.execute(
            "SELECT review_status, COUNT(*) as cnt FROM ai_variants "
            "WHERE variant_type='smart_style' AND generation_status='success' "
            "GROUP BY review_status"
        ).fetchall()
        conn.close()
    except Exception:
        return {"pairs": [], "run_dir": None, "accepted": 0, "rejected": 0}

    accepted = sum(r["cnt"] for r in counts if r["review_status"] == "accepted")
    rejected = sum(r["cnt"] for r in counts if r["review_status"] == "rejected")

    # Build a map of uuid -> run_dir by scanning filesystem
    uuid_to_run = {}
    if GENERATED_DIR.exists():
        for run_dir in sorted(GENERATED_DIR.iterdir(), reverse=True):
            if not run_dir.is_dir() or run_dir.name.startswith("."):
                continue
            for uuid_dir in run_dir.iterdir():
                if uuid_dir.is_dir() and uuid_dir.name not in uuid_to_run:
                    uuid_to_run[uuid_dir.name] = run_dir.name

    pairs = []
    for row in unreviewed:
        uid = row["image_uuid"]
        vid = row["variant_id"]
        run = uuid_to_run.get(uid)
        if not run:
            continue
        # Find the variant file on disk
        uuid_dir = GENERATED_DIR / run / uid
        # Match variant_id to style key
        for vf in uuid_dir.glob("imagen_smart_*.jpg"):
            style_key = vf.stem.replace("imagen_smart_", "")
            if _variant_id_for(uid, style_key) == vid:
                pairs.append({
                    "variant_id": vid,
                    "uuid": uid,
                    "original_path": f"/generated/{run}/{uid}/original.jpg",
                    "variant_path": f"/generated/{run}/{uid}/{vf.name}",
                    "style_name": style_key,
                    "style_prompt": row["prompt"] or "",
                    "strength": 0,
                    "why": "",
                    "rotation": 0,
                    "review": None,
                    "variant_type": "smart_style",
                })
                break

    return {
        "pairs": pairs,
        "run_dir": None,
        "accepted": accepted,
        "rejected": rejected,
    }


def review_generated(variant_id: str, status):
    """Update review_status for a smart_style variant."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute(
            "UPDATE ai_variants SET review_status = ? WHERE variant_id = ?",
            (status, variant_id),
        )
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_unpicked_data():
    """Return unpicked images for the curation UI."""
    return {"images": []}


def get_location_tagger_data(camera=None, obj=None):
    """Return location tagger data."""
    return {"images": [], "locations": []}


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
