"""Cartoon variant data and review API."""
from __future__ import annotations

import sqlite3

from ._common import DB_PATH


def get_cartoon_data():
    """Return cartoon pairs from the database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    pairs = []
    try:
        for r in conn.execute("""
            SELECT v.image_uuid, v.variant_id, i.category, i.subcategory,
                   COALESCE(g.alt_text, '') as caption
            FROM ai_variants v
            JOIN images i ON v.image_uuid = i.uuid
            LEFT JOIN gemini_analysis g ON v.image_uuid = g.image_uuid
            WHERE v.variant_type = 'cartoon' AND v.generation_status = 'success'
            ORDER BY i.category, i.subcategory, v.image_uuid
        """).fetchall():
            pairs.append({
                "uuid": r["image_uuid"],
                "variant_uuid": r["variant_id"],
                "category": r["category"],
                "subcategory": r["subcategory"] or "Landscape",
                "caption": r["caption"],
            })
    except Exception:
        pass
    conn.close()
    return pairs


def get_gemma_cartoon_data():
    """Return gemma_cartoon pairs with per-image cartoon_style from Gemma."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    pairs = []
    try:
        for r in conn.execute("""
            SELECT v.image_uuid, v.variant_id, i.category, i.subcategory,
                   COALESCE(g.alt_text, '') as caption,
                   COALESCE(gp.cartoon_style, '') as cartoon_style
            FROM ai_variants v
            JOIN images i ON v.image_uuid = i.uuid
            LEFT JOIN gemini_analysis g ON v.image_uuid = g.image_uuid
            LEFT JOIN gemma_picks gp ON v.image_uuid = gp.uuid
            WHERE v.variant_type = 'gemma_cartoon' AND v.generation_status = 'success'
            ORDER BY i.category, i.subcategory, v.image_uuid
        """).fetchall():
            pairs.append({
                "uuid": r["image_uuid"],
                "variant_uuid": r["variant_id"],
                "category": r["category"],
                "subcategory": r["subcategory"] or "Landscape",
                "caption": r["caption"],
                "cartoon_style": r["cartoon_style"],
            })
    except Exception:
        pass
    conn.close()
    return pairs


def get_all_cartoon_data():
    """Return all cartoon + gemma_cartoon pairs with review status."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    pairs = []
    try:
        for r in conn.execute("""
            SELECT v.variant_id, v.image_uuid, v.variant_type, v.review_status,
                   i.category, i.subcategory,
                   COALESCE(g.alt_text, '') as caption,
                   COALESCE(gp.cartoon_style, '') as cartoon_style
            FROM ai_variants v
            JOIN images i ON v.image_uuid = i.uuid
            LEFT JOIN gemini_analysis g ON v.image_uuid = g.image_uuid
            LEFT JOIN gemma_picks gp ON v.image_uuid = gp.uuid
            WHERE v.variant_type IN ('cartoon', 'gemma_cartoon')
              AND v.generation_status = 'success'
            ORDER BY v.review_status IS NULL DESC, i.category, i.subcategory, v.image_uuid
        """).fetchall():
            pairs.append({
                "uuid": r["image_uuid"],
                "variant_uuid": r["variant_id"],
                "type": r["variant_type"],
                "category": r["category"],
                "subcategory": r["subcategory"] or "Landscape",
                "caption": r["caption"],
                "cartoon_style": r["cartoon_style"] or "",
                "review": r["review_status"],
            })
    except Exception:
        pass
    conn.close()
    accepted = sum(1 for p in pairs if p["review"] == "accepted")
    rejected = sum(1 for p in pairs if p["review"] == "rejected")
    return {"pairs": pairs, "accepted": accepted, "rejected": rejected}


def review_cartoon(variant_id, status):
    """Set review_status ('accepted' or 'rejected') for a cartoon variant."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "UPDATE ai_variants SET review_status = ? WHERE variant_id = ?",
        (status, variant_id)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "variant_id": variant_id, "status": status}
