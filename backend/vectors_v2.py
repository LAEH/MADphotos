#!/usr/bin/env python3
"""
vectors_v2.py — Upgraded embedding pipeline for MADphotos.

Upgrades:
  DINOv2 base (768d) → DINOv2-Large (1024d)
  SigLIP base (768d) → SigLIP2-SO400M (1152d)
  CLIP ViT-B/32 (512d) — kept as-is (copied from v1)

Strategy:
  1. Create image_vectors_v2 LanceDB table with new dimensions
  2. Process all 9,011 images through upgraded models
  3. Copy existing CLIP vectors from old table
  4. Once complete, rename tables

Usage:
    python vectors_v2.py                       # Process all unprocessed
    python vectors_v2.py --batch-size 16       # Custom batch size
    python vectors_v2.py --limit 50            # Test run
    python vectors_v2.py --reprocess           # Re-extract everything
    python vectors_v2.py --status              # Show vector counts
"""
from __future__ import annotations

import argparse
import gc
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

# ─── Constants ────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
LANCE_PATH = str(PROJECT_ROOT / "images" / "vectors.lance")
SOURCE_TIER = "display"
V1_TABLE = "image_vectors"
V2_TABLE = "image_vectors_v2"

MODEL_CONFIGS_V2 = {
    "dino": {
        "checkpoint": "facebook/dinov2-large",
        "dim": 1024,
        "description": "DINOv2-Large (Artistic/Composition)",
    },
    "siglip": {
        "checkpoint": "google/siglip2-so400m-patch14-384",
        "dim": 1152,
        "description": "SigLIP2-SO400M (Semantic/Vibe)",
    },
    "clip": {
        "checkpoint": "openai/clip-vit-base-patch32",
        "dim": 512,
        "description": "CLIP ViT-B/32 (Subject/Duplicate)",
    },
}


def get_device() -> str:
    import torch
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _free_model(device: str):
    import torch
    gc.collect()
    if device == "mps":
        torch.mps.empty_cache()
    elif device == "cuda":
        torch.cuda.empty_cache()


def _load_images(batch: List[Tuple[str, str]]) -> Tuple[list, List[str]]:
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


# ─── Image List ───────────────────────────────────────────────────────────────

def load_image_list() -> List[Tuple[str, str]]:
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
            path = str(PROJECT_ROOT / f"images/rendered/{SOURCE_TIER}/jpeg/{uuid}.jpg")
        results.append((uuid, path))
    conn.close()
    return results


def load_existing_v2_uuids() -> set:
    import lancedb
    db = lancedb.connect(LANCE_PATH)
    if V2_TABLE not in db.table_names():
        return set()
    table = db.open_table(V2_TABLE)
    uuids = table.to_arrow().column("uuid").to_pylist()
    return set(uuids)


def load_v1_clip_vectors() -> Dict[str, np.ndarray]:
    """Load existing CLIP vectors from v1 table."""
    import lancedb
    db = lancedb.connect(LANCE_PATH)
    if V1_TABLE not in db.table_names():
        return {}
    table = db.open_table(V1_TABLE)
    arrow = table.to_arrow()
    uuids = arrow.column("uuid").to_pylist()
    clips = arrow.column("clip").to_pylist()
    return {u: np.array(c, dtype=np.float32) for u, c in zip(uuids, clips)}


# ─── Feature Extraction ──────────────────────────────────────────────────────

def extract_dino_large(
    image_paths: List[Tuple[str, str]], batch_size: int, device: str
) -> Dict[str, np.ndarray]:
    """Extract DINOv2-Large CLS token embeddings — 1024d."""
    import torch
    from transformers import AutoImageProcessor, AutoModel
    from tqdm import tqdm

    ckpt = MODEL_CONFIGS_V2["dino"]["checkpoint"]
    dim = MODEL_CONFIGS_V2["dino"]["dim"]
    print(f"\n{'─'*60}")
    print(f"[DINOv2-Large] {ckpt} → {dim}d")
    print(f"{'─'*60}")

    processor = AutoImageProcessor.from_pretrained(ckpt)
    model = AutoModel.from_pretrained(ckpt).to(device).eval()

    vectors = {}
    batches = [image_paths[i:i+batch_size] for i in range(0, len(image_paths), batch_size)]

    with torch.no_grad():
        for batch in tqdm(batches, desc="  DINOv2-L", unit="batch"):
            images, uuids = _load_images(batch)
            if not images:
                continue

            inputs = processor(images=images, return_tensors="pt").to(device)
            outputs = model(**inputs)

            embeddings = outputs.last_hidden_state[:, 0]
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=-1)
            embeddings_np = embeddings.cpu().numpy()

            for i, uuid in enumerate(uuids):
                vectors[uuid] = embeddings_np[i]

    print(f"  Extracted: {len(vectors)} vectors ({dim}d)")
    del model, processor
    _free_model(device)
    return vectors


def extract_siglip2(
    image_paths: List[Tuple[str, str]], batch_size: int, device: str
) -> Dict[str, np.ndarray]:
    """Extract SigLIP2-SO400M image embeddings — 1152d."""
    import torch
    from transformers import AutoProcessor, AutoModel
    from tqdm import tqdm

    ckpt = MODEL_CONFIGS_V2["siglip"]["checkpoint"]
    dim = MODEL_CONFIGS_V2["siglip"]["dim"]
    print(f"\n{'─'*60}")
    print(f"[SigLIP2-SO400M] {ckpt} → {dim}d")
    print(f"{'─'*60}")

    processor = AutoProcessor.from_pretrained(ckpt)
    model = AutoModel.from_pretrained(ckpt).to(device).eval()

    vectors = {}
    batches = [image_paths[i:i+batch_size] for i in range(0, len(image_paths), batch_size)]

    with torch.no_grad():
        for batch in tqdm(batches, desc="  SigLIP2", unit="batch"):
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

    print(f"  Extracted: {len(vectors)} vectors ({dim}d)")
    del model, processor
    _free_model(device)
    return vectors


def extract_clip(
    image_paths: List[Tuple[str, str]], batch_size: int, device: str
) -> Dict[str, np.ndarray]:
    """Extract CLIP ViT-B/32 image embeddings — 512d (same as v1)."""
    import torch
    from transformers import CLIPModel, CLIPProcessor
    from tqdm import tqdm

    ckpt = MODEL_CONFIGS_V2["clip"]["checkpoint"]
    dim = MODEL_CONFIGS_V2["clip"]["dim"]
    print(f"\n{'─'*60}")
    print(f"[CLIP] {ckpt} → {dim}d")
    print(f"{'─'*60}")

    processor = CLIPProcessor.from_pretrained(ckpt)
    model = CLIPModel.from_pretrained(ckpt).to(device).eval()

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

    print(f"  Extracted: {len(vectors)} vectors ({dim}d)")
    del model, processor
    _free_model(device)
    return vectors


# ─── LanceDB Storage ─────────────────────────────────────────────────────────

def _build_arrow_table_v2(
    dino: Dict[str, np.ndarray],
    siglip: Dict[str, np.ndarray],
    clip: Dict[str, np.ndarray],
    uuids: list,
):
    """Build a PyArrow table with v2 vector dimensions."""
    import pyarrow as pa

    dino_dim = MODEL_CONFIGS_V2["dino"]["dim"]
    siglip_dim = MODEL_CONFIGS_V2["siglip"]["dim"]
    clip_dim = MODEL_CONFIGS_V2["clip"]["dim"]

    schema = pa.schema([
        pa.field("uuid", pa.utf8()),
        pa.field("dino", pa.list_(pa.float32(), dino_dim)),
        pa.field("siglip", pa.list_(pa.float32(), siglip_dim)),
        pa.field("clip", pa.list_(pa.float32(), clip_dim)),
    ])

    uuid_arr = pa.array(uuids, type=pa.utf8())
    dino_arr = pa.FixedSizeListArray.from_arrays(
        pa.array(np.concatenate([dino[u] for u in uuids]).astype(np.float32)),
        dino_dim,
    )
    siglip_arr = pa.FixedSizeListArray.from_arrays(
        pa.array(np.concatenate([siglip[u] for u in uuids]).astype(np.float32)),
        siglip_dim,
    )
    clip_arr = pa.FixedSizeListArray.from_arrays(
        pa.array(np.concatenate([clip[u] for u in uuids]).astype(np.float32)),
        clip_dim,
    )

    return pa.table(
        [uuid_arr, dino_arr, siglip_arr, clip_arr],
        schema=schema,
    )


def write_to_lancedb_v2(
    dino: Dict[str, np.ndarray],
    siglip: Dict[str, np.ndarray],
    clip: Dict[str, np.ndarray],
    reprocess: bool = False,
):
    """Write all vectors to LanceDB v2 table."""
    import lancedb

    complete = sorted(set(dino.keys()) & set(siglip.keys()) & set(clip.keys()))
    partial_dino = len(dino) - len(complete)
    partial_siglip = len(siglip) - len(complete)
    partial_clip = len(clip) - len(complete)

    if partial_dino or partial_siglip or partial_clip:
        print(f"\n  Partial extractions (skipped): "
              f"DINOv2-L={partial_dino}, SigLIP2={partial_siglip}, CLIP={partial_clip}")

    if not complete:
        print("No complete vector triples to write.")
        return

    print(f"\n[LanceDB] Writing {len(complete)} complete vector triples to '{V2_TABLE}'...")

    arrow_table = _build_arrow_table_v2(dino, siglip, clip, complete)
    db = lancedb.connect(LANCE_PATH)

    if V2_TABLE in db.table_names():
        if reprocess:
            db.drop_table(V2_TABLE)
            table = db.create_table(V2_TABLE, data=arrow_table)
        else:
            table = db.open_table(V2_TABLE)
            table.add(arrow_table)
    else:
        table = db.create_table(V2_TABLE, data=arrow_table)

    total = table.count_rows()
    print(f"[LanceDB] Table '{V2_TABLE}': {total} total rows")


def show_status():
    """Show vector table status."""
    import lancedb

    db = lancedb.connect(LANCE_PATH)
    tables = db.table_names()

    print(f"\nVector Store Status ({LANCE_PATH})")
    print(f"{'='*60}")

    for name in sorted(tables):
        tbl = db.open_table(name)
        count = tbl.count_rows()
        schema = tbl.schema
        dims = []
        for field in schema:
            if hasattr(field.type, 'list_size'):
                dims.append(f"{field.name}:{field.type.list_size}d")
        dim_str = ", ".join(dims) if dims else "?"
        print(f"  {name:30s}  {count:>6} rows  ({dim_str})")

    print()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="MADphotos Vector Engine V2 — Upgraded embeddings",
    )
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Images per batch (default: 32)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only N images (for testing)")
    parser.add_argument("--reprocess", action="store_true",
                        help="Re-extract all vectors from scratch")
    parser.add_argument("--status", action="store_true",
                        help="Show vector table status and exit")
    parser.add_argument("--copy-clip", action="store_true",
                        help="Copy CLIP vectors from v1 table instead of re-extracting")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    device = get_device()
    print(f"MADphotos Vector Engine V2")
    print(f"{'='*60}")
    print(f"  Device:     {device}")
    print(f"  Source:     rendered/{SOURCE_TIER}/jpeg/")
    print(f"  Vector DB:  {LANCE_PATH}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Models:     DINOv2-L (1024d) + SigLIP2-SO400M (1152d) + CLIP (512d)")
    print(f"  Target:     {V2_TABLE}")
    print(f"{'='*60}")

    # Load image list
    all_images = load_image_list()
    print(f"\n  Images in DB: {len(all_images)}")

    # Filter to unprocessed
    if not args.reprocess:
        existing = load_existing_v2_uuids()
        images = [(u, p) for u, p in all_images if u not in existing]
        print(f"  Already in v2: {len(existing)}")
        print(f"  To process: {len(images)}")
    else:
        images = all_images
        print(f"  Reprocessing all {len(images)} images")

    if args.limit:
        images = images[:args.limit]
        print(f"  Limited to: {len(images)} images")

    if not images:
        print("\n  Nothing to do — all images already vectorized.")
        show_status()
        return

    # Filter to existing files
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

    # Acquire pipeline lock
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from pipeline_lock import acquire_lock, release_lock
    try:
        acquire_lock("vectors_v2.py")
    except RuntimeError as e:
        print(f"\n  Lock error: {e}")
        sys.exit(1)

    try:
        t0 = time.time()

        # Extract DINOv2-Large
        dino_vecs = extract_dino_large(images, args.batch_size, device)

        # Extract SigLIP2-SO400M
        siglip_vecs = extract_siglip2(images, args.batch_size, device)

        # CLIP: copy from v1 or re-extract
        if args.copy_clip:
            print(f"\n{'─'*60}")
            print(f"[CLIP] Copying from v1 table...")
            print(f"{'─'*60}")
            v1_clips = load_v1_clip_vectors()
            clip_vecs = {u: v1_clips[u] for u, _ in images if u in v1_clips}
            missing_clip = len(images) - len(clip_vecs)
            if missing_clip > 0:
                print(f"  Copied {len(clip_vecs)} from v1, {missing_clip} need extraction")
                to_extract = [(u, p) for u, p in images if u not in clip_vecs]
                if to_extract:
                    new_clips = extract_clip(to_extract, args.batch_size, device)
                    clip_vecs.update(new_clips)
            else:
                print(f"  Copied {len(clip_vecs)} CLIP vectors from v1")
        else:
            clip_vecs = extract_clip(images, args.batch_size, device)

        # Write to LanceDB v2 table
        write_to_lancedb_v2(dino_vecs, siglip_vecs, clip_vecs,
                            reprocess=args.reprocess)

        elapsed = time.time() - t0
        rate = len(images) / elapsed if elapsed > 0 else 0

        print(f"\n{'='*60}")
        print(f"  Done: {len(images)} images in {elapsed:.1f}s ({rate:.1f} img/s)")
        print(f"  Vectors: DINOv2-L={len(dino_vecs)}, SigLIP2={len(siglip_vecs)}, CLIP={len(clip_vecs)}")
        print(f"{'='*60}")

        show_status()
    finally:
        release_lock()


if __name__ == "__main__":
    main()
