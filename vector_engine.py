#!/usr/bin/env python3
"""
vector_engine.py — Extract feature vectors from MADphotos images.

Three models, three purposes:
  DINOv2  (facebook/dinov2-base)           → Artistic similarity (composition, texture, layout)
  SigLIP  (google/siglip-base-patch16-224) → Semantic search (vibe, mood, subject)
  CLIP    (openai/clip-vit-base-patch32)   → Duplicate detection (high-fidelity subject matching)

Vectors are L2-normalized and stored in LanceDB for fast cosine similarity search.

Usage:
  python3 vector_engine.py                        # Process all unprocessed images
  python3 vector_engine.py --batch-size 16        # Smaller batches (less memory)
  python3 vector_engine.py --reprocess            # Re-extract everything
  python3 vector_engine.py --search UUID          # Find similar images
  python3 vector_engine.py --text "golden hour"   # Semantic text search (SigLIP)
  python3 vector_engine.py --duplicates 0.95      # Find near-duplicates (CLIP > threshold)
"""
from __future__ import annotations

import argparse
import gc
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import numpy as np

# ─── Constants ────────────────────────────────────────────────────────────────

BASE_PATH = Path("/Users/laeh/Pictures/MADphotos")
DB_PATH = BASE_PATH / "mad_photos.db"
LANCE_PATH = str(BASE_PATH / "vectors.lance")
SOURCE_TIER = "display"  # 2048px — models resize to 224px anyway
TABLE_NAME = "image_vectors"

MODEL_CONFIGS = {
    "dino": {
        "checkpoint": "facebook/dinov2-base",
        "dim": 768,
        "description": "Artistic/Composition",
    },
    "siglip": {
        "checkpoint": "google/siglip-base-patch16-224",
        "dim": 768,
        "description": "Semantic/Vibe",
    },
    "clip": {
        "checkpoint": "openai/clip-vit-base-patch32",
        "dim": 512,
        "description": "Subject/Duplicate",
    },
}


# ─── Device ───────────────────────────────────────────────────────────────────

def get_device() -> str:
    """Best available device, preferring Apple Silicon MPS."""
    import torch
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


# ─── Image List ───────────────────────────────────────────────────────────────

def load_image_list() -> List[Tuple[str, str]]:
    """Load (uuid, image_path) pairs from the database."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute("""
        SELECT i.uuid, COALESCE(t.local_path, '')
        FROM images i
        LEFT JOIN tiers t ON i.uuid = t.image_uuid
            AND t.tier_name = ? AND t.format = 'jpeg' AND t.variant_id IS NULL
        WHERE i.uuid IS NOT NULL
        ORDER BY i.category, i.subcategory, i.filename
    """, (SOURCE_TIER,))
    results = []
    for uuid, path in cursor:
        if not path:
            path = str(BASE_PATH / f"rendered/{SOURCE_TIER}/jpeg/{uuid}.jpg")
        results.append((uuid, path))
    conn.close()
    return results


def load_existing_uuids() -> set:
    """Get UUIDs already in LanceDB."""
    import lancedb
    db = lancedb.connect(LANCE_PATH)
    if TABLE_NAME not in db.table_names():
        return set()
    table = db.open_table(TABLE_NAME)
    uuids = table.to_arrow().column("uuid").to_pylist()
    return set(uuids)


# ─── Feature Extraction ──────────────────────────────────────────────────────

def _free_model(device: str):
    """Release GPU/MPS memory after model unload."""
    import torch
    gc.collect()
    if device == "mps":
        torch.mps.empty_cache()
    elif device == "cuda":
        torch.cuda.empty_cache()


def _load_images(batch: List[Tuple[str, str]]) -> Tuple[List, List[str]]:
    """Load and convert a batch of images. Returns (images, uuids)."""
    from PIL import Image
    images = []
    uuids = []
    for uuid, path in batch:
        try:
            img = Image.open(path).convert("RGB")
            images.append(img)
            uuids.append(uuid)
        except Exception as e:
            print(f"  SKIP {uuid}: {e}")
    return images, uuids


def extract_dino(
    image_paths: List[Tuple[str, str]], batch_size: int, device: str
) -> Dict[str, np.ndarray]:
    """Extract DINOv2 CLS token embeddings — artistic/geometric similarity."""
    import torch
    from transformers import AutoImageProcessor, AutoModel
    from tqdm import tqdm

    print(f"\n{'─'*60}")
    print(f"[DINOv2] facebook/dinov2-base → {MODEL_CONFIGS['dino']['dim']}d")
    print(f"{'─'*60}")

    processor = AutoImageProcessor.from_pretrained("facebook/dinov2-base")
    model = AutoModel.from_pretrained("facebook/dinov2-base").to(device).eval()

    vectors = {}
    batches = [image_paths[i:i+batch_size] for i in range(0, len(image_paths), batch_size)]

    with torch.no_grad():
        for batch in tqdm(batches, desc="  DINOv2", unit="batch"):
            images, uuids = _load_images(batch)
            if not images:
                continue

            inputs = processor(images=images, return_tensors="pt").to(device)
            outputs = model(**inputs)

            # CLS token from last hidden state
            embeddings = outputs.last_hidden_state[:, 0]
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=-1)
            embeddings_np = embeddings.cpu().numpy()

            for i, uuid in enumerate(uuids):
                vectors[uuid] = embeddings_np[i]

    print(f"  Extracted: {len(vectors)} vectors")
    del model, processor
    _free_model(device)
    return vectors


def extract_siglip(
    image_paths: List[Tuple[str, str]], batch_size: int, device: str
) -> Dict[str, np.ndarray]:
    """Extract SigLIP image embeddings — semantic/vibe similarity + text search."""
    import torch
    from transformers import AutoProcessor, AutoModel
    from tqdm import tqdm

    print(f"\n{'─'*60}")
    print(f"[SigLIP] google/siglip-base-patch16-224 → {MODEL_CONFIGS['siglip']['dim']}d")
    print(f"{'─'*60}")

    processor = AutoProcessor.from_pretrained("google/siglip-base-patch16-224")
    model = AutoModel.from_pretrained("google/siglip-base-patch16-224").to(device).eval()

    vectors = {}
    batches = [image_paths[i:i+batch_size] for i in range(0, len(image_paths), batch_size)]

    with torch.no_grad():
        for batch in tqdm(batches, desc="  SigLIP", unit="batch"):
            images, uuids = _load_images(batch)
            if not images:
                continue

            inputs = processor(images=images, return_tensors="pt", padding=True)
            pixel_values = inputs["pixel_values"].to(device)
            embeddings = model.get_image_features(pixel_values=pixel_values)
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=-1)
            embeddings_np = embeddings.cpu().numpy()

            for i, uuid in enumerate(uuids):
                vectors[uuid] = embeddings_np[i]

    print(f"  Extracted: {len(vectors)} vectors")
    del model, processor
    _free_model(device)
    return vectors


def extract_clip(
    image_paths: List[Tuple[str, str]], batch_size: int, device: str
) -> Dict[str, np.ndarray]:
    """Extract CLIP image embeddings — high-fidelity subject/duplicate matching."""
    import torch
    from transformers import CLIPModel, CLIPProcessor
    from tqdm import tqdm

    print(f"\n{'─'*60}")
    print(f"[CLIP] openai/clip-vit-base-patch32 → {MODEL_CONFIGS['clip']['dim']}d")
    print(f"{'─'*60}")

    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device).eval()

    vectors = {}
    batches = [image_paths[i:i+batch_size] for i in range(0, len(image_paths), batch_size)]

    with torch.no_grad():
        for batch in tqdm(batches, desc="  CLIP", unit="batch"):
            images, uuids = _load_images(batch)
            if not images:
                continue

            inputs = processor(images=images, return_tensors="pt", padding=True)
            pixel_values = inputs["pixel_values"].to(device)
            embeddings = model.get_image_features(pixel_values=pixel_values)
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=-1)
            embeddings_np = embeddings.cpu().numpy()

            for i, uuid in enumerate(uuids):
                vectors[uuid] = embeddings_np[i]

    print(f"  Extracted: {len(vectors)} vectors")
    del model, processor
    _free_model(device)
    return vectors


# ─── LanceDB Storage ─────────────────────────────────────────────────────────

def _build_arrow_table(
    dino: Dict[str, np.ndarray],
    siglip: Dict[str, np.ndarray],
    clip: Dict[str, np.ndarray],
    uuids: list,
):
    """Build a PyArrow table with proper vector (FixedSizeList) types."""
    import pyarrow as pa

    schema = pa.schema([
        pa.field("uuid", pa.utf8()),
        pa.field("dino", pa.list_(pa.float32(), MODEL_CONFIGS["dino"]["dim"])),
        pa.field("siglip", pa.list_(pa.float32(), MODEL_CONFIGS["siglip"]["dim"])),
        pa.field("clip", pa.list_(pa.float32(), MODEL_CONFIGS["clip"]["dim"])),
    ])

    uuid_arr = pa.array(uuids, type=pa.utf8())
    dino_arr = pa.FixedSizeListArray.from_arrays(
        pa.array(np.concatenate([dino[u] for u in uuids]).astype(np.float32)),
        MODEL_CONFIGS["dino"]["dim"],
    )
    siglip_arr = pa.FixedSizeListArray.from_arrays(
        pa.array(np.concatenate([siglip[u] for u in uuids]).astype(np.float32)),
        MODEL_CONFIGS["siglip"]["dim"],
    )
    clip_arr = pa.FixedSizeListArray.from_arrays(
        pa.array(np.concatenate([clip[u] for u in uuids]).astype(np.float32)),
        MODEL_CONFIGS["clip"]["dim"],
    )

    return pa.table(
        [uuid_arr, dino_arr, siglip_arr, clip_arr],
        schema=schema,
    )


def write_to_lancedb(
    dino: Dict[str, np.ndarray],
    siglip: Dict[str, np.ndarray],
    clip: Dict[str, np.ndarray],
    reprocess: bool = False,
):
    """Write all vectors to LanceDB. Only writes UUIDs that have all 3 vectors."""
    import lancedb

    complete = sorted(set(dino.keys()) & set(siglip.keys()) & set(clip.keys()))
    partial_dino = len(dino) - len(complete)
    partial_siglip = len(siglip) - len(complete)
    partial_clip = len(clip) - len(complete)

    if partial_dino or partial_siglip or partial_clip:
        print(f"\n  Partial extractions (skipped): "
              f"DINOv2={partial_dino}, SigLIP={partial_siglip}, CLIP={partial_clip}")

    if not complete:
        print("No complete vector triples to write.")
        return

    print(f"\n[LanceDB] Writing {len(complete)} complete vector triples...")

    arrow_table = _build_arrow_table(dino, siglip, clip, complete)
    db = lancedb.connect(LANCE_PATH)

    if TABLE_NAME in db.table_names():
        if reprocess:
            db.drop_table(TABLE_NAME)
            table = db.create_table(TABLE_NAME, data=arrow_table)
        else:
            table = db.open_table(TABLE_NAME)
            table.add(arrow_table)
    else:
        table = db.create_table(TABLE_NAME, data=arrow_table)

    total = table.count_rows()
    print(f"[LanceDB] Table '{TABLE_NAME}': {total} total rows")


# ─── Search Modes ─────────────────────────────────────────────────────────────

def search_similar(uuid: str, top_k: int = 10):
    """Find similar images to a given UUID, using all 3 models."""
    import lancedb

    db = lancedb.connect(LANCE_PATH)
    if TABLE_NAME not in db.table_names():
        print("No vectors found. Run extraction first.")
        return

    table = db.open_table(TABLE_NAME)

    # Fetch the query row by UUID
    results_arrow = table.search().where(f"uuid = '{uuid}'", prefilter=True).limit(1).to_arrow()
    if len(results_arrow) == 0:
        print(f"UUID '{uuid}' not found in vector DB.")
        return

    row = results_arrow.to_pydict()
    print(f"\nSimilar to: {uuid}")
    print(f"{'='*70}\n")

    for model_name in ["dino", "siglip", "clip"]:
        desc = MODEL_CONFIGS[model_name]["description"]
        query_vec = np.array(row[model_name][0], dtype=np.float32)

        results = (
            table.search(query_vec, vector_column_name=model_name)
            .metric("cosine")
            .limit(top_k + 1)  # +1 to exclude self
            .to_list()
        )

        print(f"  [{model_name.upper()}] {desc}:")
        rank = 1
        for r in results:
            if r["uuid"] == uuid:
                continue
            dist = r.get("_distance", 0)
            sim = 1.0 - dist
            print(f"    {rank:2d}. {r['uuid']}  sim={sim:.4f}")
            rank += 1
            if rank > top_k:
                break
        print()


def text_search(query: str, top_k: int = 10):
    """Semantic text→image search using SigLIP's shared embedding space."""
    import torch
    import lancedb
    from transformers import AutoProcessor, AutoModel

    db = lancedb.connect(LANCE_PATH)
    if TABLE_NAME not in db.table_names():
        print("No vectors found. Run extraction first.")
        return

    table = db.open_table(TABLE_NAME)

    print(f"\n[SigLIP] Encoding: \"{query}\"")
    processor = AutoProcessor.from_pretrained("google/siglip-base-patch16-224")
    model = AutoModel.from_pretrained("google/siglip-base-patch16-224").eval()

    with torch.no_grad():
        inputs = processor(text=[query], return_tensors="pt", padding=True)
        text_features = model.get_text_features(**inputs)
        text_features = torch.nn.functional.normalize(text_features, p=2, dim=-1)
        query_vec = text_features[0].numpy()

    del model, processor

    results = (
        table.search(query_vec, vector_column_name="siglip")
        .metric("cosine")
        .limit(top_k)
        .to_list()
    )

    print(f"\nResults for \"{query}\":")
    print(f"{'─'*50}")
    for i, r in enumerate(results, 1):
        dist = r.get("_distance", 0)
        sim = 1.0 - dist
        print(f"  {i:2d}. {r['uuid']}  sim={sim:.4f}")


def find_duplicates(threshold: float = 0.95, limit: int = 100):
    """Find near-duplicate pairs using CLIP vectors."""
    import lancedb

    db = lancedb.connect(LANCE_PATH)
    if TABLE_NAME not in db.table_names():
        print("No vectors found. Run extraction first.")
        return

    table = db.open_table(TABLE_NAME)
    arrow_table = table.to_arrow()
    n = len(arrow_table)

    print(f"\n[Duplicates] Scanning {n} images (CLIP, threshold={threshold})...")

    uuids = arrow_table.column("uuid").to_pylist()
    clip_list = arrow_table.column("clip").to_pylist()
    clip_vecs = np.array(clip_list, dtype=np.float32)

    # Cosine similarity matrix (vectors are already L2-normalized)
    # Process in chunks to avoid OOM on large sets
    pairs = []
    chunk_size = 500
    for i in range(0, len(clip_vecs), chunk_size):
        chunk = clip_vecs[i:i+chunk_size]
        sims = chunk @ clip_vecs.T  # (chunk_size, N)
        for ci in range(len(chunk)):
            gi = i + ci  # global index
            for j in range(gi + 1, len(clip_vecs)):
                if sims[ci, j] >= threshold:
                    pairs.append((uuids[gi], uuids[j], float(sims[ci, j])))
                    if len(pairs) >= limit:
                        break
            if len(pairs) >= limit:
                break
        if len(pairs) >= limit:
            break

    pairs.sort(key=lambda x: x[2], reverse=True)

    print(f"\nFound {len(pairs)} pairs above {threshold}:")
    print(f"{'─'*70}")
    for a, b, sim in pairs:
        print(f"  {a}  ↔  {b}  sim={sim:.4f}")

    if not pairs:
        print("  No duplicates found at this threshold.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="MADphotos Vector Engine — 3-model feature extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Images per batch (default: 32)")
    parser.add_argument("--reprocess", action="store_true",
                        help="Re-extract all vectors from scratch")
    parser.add_argument("--search", type=str, metavar="UUID",
                        help="Find similar images to this UUID")
    parser.add_argument("--text", type=str, metavar="QUERY",
                        help="Semantic text search via SigLIP")
    parser.add_argument("--duplicates", type=float, metavar="THRESHOLD", nargs="?",
                        const=0.95, default=None,
                        help="Find near-duplicate pairs (default threshold: 0.95)")
    parser.add_argument("--top-k", type=int, default=10,
                        help="Number of results (default: 10)")
    args = parser.parse_args()

    # ── Search / query modes ──
    if args.search:
        search_similar(args.search, args.top_k)
        return

    if args.text:
        text_search(args.text, args.top_k)
        return

    if args.duplicates is not None:
        find_duplicates(args.duplicates, limit=args.top_k * 10)
        return

    # ── Extraction mode ──
    device = get_device()
    print(f"MADphotos Vector Engine")
    print(f"{'='*60}")
    print(f"  Device:     {device}")
    print(f"  Source:     rendered/{SOURCE_TIER}/jpeg/")
    print(f"  Vector DB:  {LANCE_PATH}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Models:     DINOv2 (768d) + SigLIP (768d) + CLIP (512d)")
    print(f"{'='*60}")

    # Load image list
    all_images = load_image_list()
    print(f"\n  Images in DB: {len(all_images)}")

    # Filter to unprocessed
    if not args.reprocess:
        existing = load_existing_uuids()
        images = [(u, p) for u, p in all_images if u not in existing]
        print(f"  Already vectorized: {len(existing)}")
        print(f"  To process: {len(images)}")
    else:
        images = all_images
        print(f"  Reprocessing all {len(images)} images")

    if not images:
        print("\n  Nothing to do — all images already vectorized.")
        return

    # Filter to images that exist on disk
    valid = []
    missing = 0
    for uuid, path in images:
        if Path(path).exists():
            valid.append((uuid, path))
        else:
            missing += 1
    if missing:
        print(f"  Missing files (skipped): {missing}")
    images = valid
    print(f"  Valid images: {len(images)}")

    if not images:
        print("\n  No valid images found.")
        return

    # ── Extract features, one model at a time ──
    t0 = time.time()

    dino_vecs = extract_dino(images, args.batch_size, device)
    siglip_vecs = extract_siglip(images, args.batch_size, device)
    clip_vecs = extract_clip(images, args.batch_size, device)

    # ── Write to LanceDB ──
    write_to_lancedb(dino_vecs, siglip_vecs, clip_vecs, reprocess=args.reprocess)

    elapsed = time.time() - t0
    rate = len(images) / elapsed if elapsed > 0 else 0

    print(f"\n{'='*60}")
    print(f"  Done: {len(images)} images in {elapsed:.1f}s ({rate:.1f} img/s)")
    print(f"  Vectors: DINOv2={len(dino_vecs)}, SigLIP={len(siglip_vecs)}, CLIP={len(clip_vecs)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
