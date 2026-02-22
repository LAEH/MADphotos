"""Vector search via LanceDB — similarity and drift."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

_lance_db = None   # type: Optional[object]
_lance_tbl = None  # type: Optional[object]


def _get_lance():
    """Lazy-load lancedb connection, returns (tbl, df) or (None, None)."""
    global _lance_db, _lance_tbl
    try:
        import lancedb as _ldb
    except ImportError:
        return None, None
    lance_path = Path(__file__).resolve().parent.parent / "vectors.lance"
    if not lance_path.exists():
        return None, None
    if _lance_db is None:
        _lance_db = _ldb.connect(str(lance_path))
        _lance_tbl = _lance_db.open_table("image_vectors")
    return _lance_tbl, _lance_tbl.to_pandas()


def similarity_search(query_uuid):
    # type: (str) -> Optional[dict]
    """Find nearest neighbors for a UUID across all 3 models. Returns JSON-ready dict."""
    tbl, df = _get_lance()
    if tbl is None:
        return None
    matches = df[df["uuid"] == query_uuid]
    if matches.empty:
        return None
    query_row = matches.iloc[0]
    models = [
        ("dino", "DINOv2", "Texture & structure — finds images with similar visual geometry"),
        ("siglip", "SigLIP", "Semantic meaning — finds images about similar things"),
        ("clip", "CLIP", "Subject matching — finds images of similar objects"),
    ]
    result = {"uuid": query_uuid, "models": []}
    for col, name, desc in models:
        query_vec = query_row[col]
        results = tbl.search(query_vec, vector_column_name=col).limit(9).to_pandas()
        neighbors = results[results["uuid"] != query_uuid].head(8)
        nb_list = []
        for _, nb_row in neighbors.iterrows():
            nb_list.append({"uuid": nb_row["uuid"], "dist": round(float(nb_row["_distance"]), 4)})
        result["models"].append({"name": name, "desc": desc, "neighbors": nb_list})
    return result


def drift_search(query_uuid):
    # type: (str) -> Optional[dict]
    """Find creative drift neighbors: structurally similar (DINOv2) but semantically different (SigLIP).
    Skip the closest matches to find surprising connections."""
    tbl, df = _get_lance()
    if tbl is None:
        return None
    matches = df[df["uuid"] == query_uuid]
    if matches.empty:
        return None
    query_row = matches.iloc[0]

    # Get DINOv2 neighbors (structural) — skip top 3 closest (too similar), take rank 4-20
    dino_vec = query_row["dino"]
    dino_results = tbl.search(dino_vec, vector_column_name="dino").limit(25).to_pandas()
    dino_results = dino_results[dino_results["uuid"] != query_uuid]

    # Also get SigLIP distances for these same images to find semantic divergence
    siglip_vec = query_row["siglip"]
    siglip_results = tbl.search(siglip_vec, vector_column_name="siglip").limit(100).to_pandas()
    siglip_dist_map = dict(zip(siglip_results["uuid"].tolist(), siglip_results["_distance"].tolist()))

    # Score: want LOW dino distance (similar structure) but HIGH siglip distance (different meaning)
    candidates = []
    for _, row in dino_results.iterrows():
        nb_uuid = row["uuid"]
        dino_dist = float(row["_distance"])
        siglip_dist = siglip_dist_map.get(nb_uuid, 1.0)
        # Creative score: penalize close semantic matches, reward structural similarity
        creativity = siglip_dist / max(dino_dist, 0.01)
        candidates.append({
            "uuid": nb_uuid,
            "dino_dist": round(dino_dist, 4),
            "siglip_dist": round(siglip_dist, 4),
            "creativity": round(creativity, 2),
        })

    # Sort by creativity score (highest = most interesting structural match with different meaning)
    candidates.sort(key=lambda x: -x["creativity"])
    return {"uuid": query_uuid, "neighbors": candidates[:8]}
