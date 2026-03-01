#!/usr/bin/env python3
"""Neural Style Transfer variant generation — dramatic, free, local.

Generates style-transferred variants using VGG19 feature matching (Gatys et al.)
with industrial/construction art references. Runs on Apple Silicon MPS.
Records results in ai_variants table for the standard review/accept/deploy workflow.

Usage:
    .venv-gen/bin/python3 -m backend.suggest_image_variant.nst_generate
    .venv-gen/bin/python3 -m backend.suggest_image_variant.nst_generate --count 40
    .venv-gen/bin/python3 -m backend.suggest_image_variant.nst_generate --dry
    .venv-gen/bin/python3 -m backend.suggest_image_variant.nst_generate --steps 400 --size 768
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image

from .config import DB_PATH, GENERATED_DIR, UUID_NAMESPACE

# ── Style References ─────────────────────────────────────────────────────────
# Public domain industrial/constructivist/architectural artworks.
# Downloaded to style_references/ on first run.

STYLES_DIR = Path(__file__).resolve().parent / "style_references"

NST_STYLES = [
    {
        "key": "nst_lissitzky",
        "name": "Lissitzky Red Wedge",
        "file": "lissitzky_red_wedge.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/1/13/Beat_the_Whites_with_the_Red_Wedge.jpg",
        "style_ratio": 5e4,
        "affinities": {"urban", "gritty", "dramatic", "monochrome", "industrial"},
    },
    {
        "key": "nst_sheeler",
        "name": "Sheeler River Rouge",
        "file": "sheeler_river_rouge.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/e/e0/Charles_Sheeler%2C_River_Rouge_Plant%2C_1932_1_15_18_-whitneymuseum_%2839273167440%29.jpg",
        "style_ratio": 3e4,
        "affinities": {"exterior", "industrial", "urban", "monochrome", "architectural"},
    },
    {
        "key": "nst_piranesi",
        "name": "Piranesi Carceri",
        "file": "piranesi_drawbridge.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/f/fc/Giovanni_Battista_Piranesi_-_The_Drawbridge%2C_plate_VII_from_the_series_Carceri_d%27Invenzione_-_Google_Art_Project.jpg",
        "style_ratio": 3e4,
        "affinities": {"architectural", "dark", "moody", "cinematic", "dramatic"},
    },
    {
        "key": "nst_leger",
        "name": "Léger The City",
        "file": "leger_the_city.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/8/8a/Fernand_L%C3%A9ger%2C_1919%2C_The_City_%28La_Ville%29%2C_oil_on_canvas%2C_231.1_x_298.4_cm%2C_Philadelphia_Museum_of_Art.jpg",
        "style_ratio": 5e4,
        "affinities": {"urban", "exterior", "cinematic", "industrial", "architectural"},
    },
    {
        "key": "nst_popova",
        "name": "Popova Architectonic",
        "file": "popova_architectonic.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/c/c1/Painterly_Architectonic_-_Lyubov_Popova.jpg",
        "style_ratio": 5e4,
        "affinities": {"monochrome", "minimal", "abstract", "dark", "architectural"},
    },
]

# VGG19 layers for feature extraction
CONTENT_LAYERS = ["conv_4"]
STYLE_LAYERS = {
    "conv_1": 0.1,
    "conv_2": 0.1,
    "conv_3": 0.2,
    "conv_4": 0.3,
    "conv_5": 0.3,
}

MEAN = torch.tensor([0.485, 0.456, 0.406])
STD = torch.tensor([0.229, 0.224, 0.225])


# ── Image Loading ─────────────────────────────────────────────────────────────

def get_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_image(path: str, max_size: int, device: torch.device) -> torch.Tensor:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = max_size / max(w, h)
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return transforms.ToTensor()(img).unsqueeze(0).to(device)


def load_style_image(path: str, content_shape: tuple, device: torch.device) -> torch.Tensor:
    img = Image.open(path).convert("RGB")
    _, _, h, w = content_shape
    img = img.resize((w, h), Image.LANCZOS)
    return transforms.ToTensor()(img).unsqueeze(0).to(device)


def tensor_to_image(tensor: torch.Tensor, original_size: tuple[int, int]) -> Image.Image:
    img = tensor.cpu().clone().squeeze(0).clamp(0, 1)
    img = transforms.ToPILImage()(img)
    if img.size != original_size:
        img = img.resize(original_size, Image.LANCZOS)
    return img


def preserve_detail(original: Image.Image, stylized: Image.Image,
                    detail_strength: float = 0.7) -> Image.Image:
    """Blend back original's high-frequency detail into the stylized image."""
    orig = np.array(original).astype(np.float32)
    styled = np.array(stylized.resize(original.size, Image.LANCZOS)).astype(np.float32)

    blur = cv2.GaussianBlur(orig, (0, 0), sigmaX=5)
    detail = orig - blur

    orig_gray = cv2.cvtColor(orig, cv2.COLOR_RGB2GRAY)
    styled_gray = cv2.cvtColor(styled.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)

    lum_ratio = np.where(styled_gray > 1, orig_gray / styled_gray, 1.0)
    lum_ratio = np.clip(lum_ratio, 0.3, 3.0)
    lum_blend = 0.35

    result = styled.copy()
    for c in range(3):
        result[:, :, c] = styled[:, :, c] * (1 - lum_blend + lum_blend * lum_ratio)

    result = result + detail * detail_strength
    result = np.clip(result, 0, 255).astype(np.uint8)
    return Image.fromarray(result)


# ── VGG19 Model ──────────────────────────────────────────────────────────────

def gram_matrix(tensor: torch.Tensor) -> torch.Tensor:
    b, c, h, w = tensor.size()
    features = tensor.view(b * c, h * w)
    G = torch.mm(features, features.t())
    return G.div(b * c * h * w)


class ContentLoss(nn.Module):
    def __init__(self, target: torch.Tensor):
        super().__init__()
        self.target = target.detach()
        self.loss = torch.tensor(0.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        self.loss = F.mse_loss(x, self.target)
        return x


class StyleLoss(nn.Module):
    def __init__(self, target_feature: torch.Tensor, weight: float = 1.0):
        super().__init__()
        self.target = gram_matrix(target_feature).detach()
        self.weight = weight
        self.loss = torch.tensor(0.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        self.loss = self.weight * F.mse_loss(gram_matrix(x), self.target)
        return x


class Normalization(nn.Module):
    def __init__(self, mean: torch.Tensor, std: torch.Tensor):
        super().__init__()
        self.mean = mean.clone().view(-1, 1, 1)
        self.std = std.clone().view(-1, 1, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return (x - self.mean) / self.std


def build_model(cnn, content_img, style_img, device):
    normalization = Normalization(MEAN.to(device), STD.to(device))
    content_losses = []
    style_losses = []
    model = nn.Sequential(normalization)

    i = 0
    for layer in cnn.children():
        if isinstance(layer, nn.Conv2d):
            i += 1
            name = f"conv_{i}"
        elif isinstance(layer, nn.ReLU):
            name = f"relu_{i}"
            layer = nn.ReLU(inplace=False)
        elif isinstance(layer, nn.MaxPool2d):
            name = f"pool_{i}"
        elif isinstance(layer, nn.BatchNorm2d):
            name = f"bn_{i}"
        else:
            continue

        model.add_module(name, layer)

        if name in CONTENT_LAYERS:
            target = model(content_img).detach()
            cl = ContentLoss(target)
            model.add_module(f"content_loss_{i}", cl)
            content_losses.append(cl)

        if name in STYLE_LAYERS:
            target = model(style_img).detach()
            sl = StyleLoss(target, weight=STYLE_LAYERS[name])
            model.add_module(f"style_loss_{i}", sl)
            style_losses.append(sl)

    for k in range(len(model) - 1, -1, -1):
        if isinstance(model[k], (ContentLoss, StyleLoss)):
            break
    model = model[:k + 1]
    return model, content_losses, style_losses


def run_style_transfer(content_img, style_img, device,
                       num_steps=300, style_ratio=5e4):
    cnn = models.vgg19(weights=models.VGG19_Weights.DEFAULT).features.to(device).eval()
    for param in cnn.parameters():
        param.requires_grad_(False)

    model, content_losses, style_losses = build_model(cnn, content_img, style_img, device)
    input_img = content_img.clone().requires_grad_(True)

    with torch.no_grad():
        model(input_img)
        init_style = sum(sl.loss.item() for sl in style_losses)

    style_weight = style_ratio / init_style if init_style > 1e-10 else 1e6

    optimizer = optim.LBFGS([input_img])
    run = [0]
    while run[0] < num_steps:
        def closure():
            input_img.data.clamp_(0, 1)
            optimizer.zero_grad()
            model(input_img)
            s_loss = sum(sl.loss for sl in style_losses)
            c_loss = sum(cl.loss for cl in content_losses)
            loss = style_weight * s_loss + c_loss
            loss.backward()
            run[0] += 1
            if run[0] % 100 == 0:
                print(f"      step {run[0]}/{num_steps} "
                      f"style={s_loss.item():.6f} content={c_loss.item():.2f}")
            return loss
        optimizer.step(closure)

    input_img.data.clamp_(0, 1)
    return input_img


# ── Style Reference Management ───────────────────────────────────────────────

def download_style_refs() -> int:
    """Download missing style references. Returns count downloaded."""
    import urllib.request
    STYLES_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for ref in NST_STYLES:
        path = STYLES_DIR / ref["file"]
        if path.exists():
            continue
        print(f"  Downloading {ref['name']}...")
        try:
            req = urllib.request.Request(ref["url"], headers={
                "User-Agent": "MADphotos/1.0 (style-transfer-research)"
            })
            with urllib.request.urlopen(req, timeout=30) as resp, open(path, "wb") as f:
                f.write(resp.read())
            downloaded += 1
        except Exception as e:
            print(f"    FAILED: {e}")
    return downloaded


# ── Candidate Selection ───────────────────────────────────────────────────────

def get_candidates(conn: sqlite3.Connection, count: int) -> List[Dict]:
    """Select picked originals without existing variants, scored for diversity."""
    picks_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "show" / "public" / "data" / "picks.json"
    with open(picks_path) as f:
        picks = json.load(f)
    all_pick_ids = set(picks.get("portrait", []) + picks.get("landscape", []))
    gen_ids = set(picks.get("generated", []))
    orig_pick_ids = all_pick_ids - gen_ids

    placeholders = ",".join("?" for _ in orig_pick_ids)
    rows = conn.execute(f"""
        SELECT i.uuid, i.orientation, i.is_monochrome,
               gem.setting, gem.vibe, gem.faces_count,
               gem.composition_technique,
               ga.mood as gemma_mood,
               MIN(t.local_path) as source_path
        FROM images i
        JOIN gemini_analysis gem ON i.uuid = gem.image_uuid
        LEFT JOIN gemma_analysis ga ON i.uuid = ga.uuid
        JOIN tiers t ON i.uuid = t.image_uuid
            AND t.tier_name = 'mobile' AND t.format = 'jpeg' AND t.variant_id IS NULL
        WHERE i.uuid IN ({placeholders})
        AND i.uuid NOT IN (
            SELECT DISTINCT image_uuid FROM ai_variants
            WHERE generation_status = 'success'
        )
        GROUP BY i.uuid
    """, list(orig_pick_ids)).fetchall()

    candidates = []
    for r in rows:
        photo = dict(r)
        # Score: prefer no-face exteriors, add randomness for diversity
        score = random.random() * 4.0
        if (photo.get("faces_count") or 0) == 0:
            score += 1.0
        setting = (photo.get("setting") or "").lower()
        if "exterior" in setting:
            score += 1.0
        if photo.get("is_monochrome"):
            score += 0.5
        photo["_score"] = score
        candidates.append(photo)

    candidates.sort(key=lambda p: -p["_score"])
    return candidates[:count]


def pick_styles_for_photo(photo: Dict) -> List[str]:
    """Pick 2 best NST styles for a photo based on signal affinity."""
    setting = (photo.get("setting") or "").lower()
    vibes_raw = photo.get("vibe") or "[]"
    try:
        vibes = set(v.lower() for v in json.loads(vibes_raw)) if vibes_raw else set()
    except (json.JSONDecodeError, TypeError):
        vibes = set()

    is_mono = bool(photo.get("is_monochrome"))
    mood = (photo.get("gemma_mood") or "").lower()

    # Build signal tags for this photo
    tags = set()
    if "exterior" in setting:
        tags.add("exterior")
    if "interior" in setting:
        tags.add("interior")
    for v in vibes:
        for kw in ("urban", "gritty", "industrial", "moody", "dark", "cinematic",
                    "dramatic", "monochrome", "minimal", "abstract", "architectural",
                    "serene", "peaceful"):
            if kw in v:
                tags.add(kw)
    if is_mono:
        tags.add("monochrome")
    for kw in ("moody", "dark", "dramatic", "gritty", "industrial", "cinematic"):
        if kw in mood:
            tags.add(kw)

    # Score each style
    scored = []
    for style in NST_STYLES:
        overlap = len(tags & style["affinities"])
        # Add small randomness so not every photo gets the same top 2
        score = overlap + random.random() * 1.5
        scored.append((style["key"], score))

    scored.sort(key=lambda x: -x[1])
    return [scored[0][0], scored[1][0]]


# ── DB ────────────────────────────────────────────────────────────────────────

def variant_id_for(image_uuid: str, style_key: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:{style_key}"))


def db_upsert(conn: sqlite3.Connection, variant_id: str, image_uuid: str,
              style_key: str, status: str, elapsed_ms: int = 0,
              error: Optional[str] = None) -> None:
    style_name = next((s["name"] for s in NST_STYLES if s["key"] == style_key), style_key)
    conn.execute("""
        INSERT INTO ai_variants (
            variant_id, image_uuid, variant_type, model, prompt,
            edit_mode, guidance_scale, source_tier,
            generation_status, error_message,
            generation_time_ms, created_at, style_key
        ) VALUES (?, ?, 'nst', 'VGG19', ?,
                  'neural_style_transfer', 0, 'mobile',
                  ?, ?, ?, ?, ?)
        ON CONFLICT(variant_id) DO UPDATE SET
            generation_status=excluded.generation_status,
            error_message=excluded.error_message,
            generation_time_ms=excluded.generation_time_ms,
            style_key=excluded.style_key
    """, (
        variant_id, image_uuid, f"Neural Style Transfer: {style_name}",
        status, error, elapsed_ms,
        datetime.now(timezone.utc).isoformat(),
        style_key,
    ))
    conn.commit()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate NST variants (free, local)")
    parser.add_argument("--count", type=int, default=40, help="Number of source photos")
    parser.add_argument("--steps", type=int, default=300, help="Optimization steps")
    parser.add_argument("--size", type=int, default=512, help="Processing resolution")
    parser.add_argument("--detail", type=float, default=0.7, help="Detail preservation (0-1)")
    parser.add_argument("--styles-per-photo", type=int, default=2, help="Styles per photo")
    parser.add_argument("--dry", action="store_true", help="Preview only")
    args = parser.parse_args()

    device = get_device()
    print(f"Device: {device}")
    print(f"Steps: {args.steps} | Size: {args.size}px | Detail: {args.detail}")

    # Download style references
    print("\nChecking style references...")
    downloaded = download_style_refs()
    available = [s for s in NST_STYLES if (STYLES_DIR / s["file"]).exists()]
    print(f"  {len(available)}/{len(NST_STYLES)} styles available"
          + (f" ({downloaded} downloaded)" if downloaded else ""))

    if not available:
        print("ERROR: No style references available. Check network.")
        return

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    candidates = get_candidates(conn, args.count)
    print(f"\nFound {len(candidates)} candidates without variants")

    if not candidates:
        print("Nothing to do — all picked photos already have variants.")
        conn.close()
        return

    # Assign styles
    assignments = []
    style_counts: Dict[str, int] = {}
    for photo in candidates:
        styles = pick_styles_for_photo(photo)[:args.styles_per_photo]
        # Only use available styles
        styles = [s for s in styles if any(a["key"] == s for a in available)]
        if not styles:
            styles = [available[0]["key"]]
        assignments.append((photo, styles))
        for s in styles:
            style_counts[s] = style_counts.get(s, 0) + 1

    total = sum(style_counts.values())
    print(f"\nStyle distribution ({total} variants from {len(candidates)} photos):")
    for key in sorted(style_counts, key=lambda k: -style_counts[k]):
        name = next((s["name"] for s in NST_STYLES if s["key"] == key), key)
        pct = style_counts[key] * 100 // max(total, 1)
        print(f"  {name:<30} {style_counts[key]:>3} ({pct}%)")

    n_portrait = sum(1 for c in candidates if c.get("orientation") == "portrait")
    print(f"\nOrientation: {n_portrait}P + {len(candidates) - n_portrait}L")
    est_time = total * (args.steps / 300) * 15  # ~15s per transfer at 300 steps
    print(f"Estimated time: ~{est_time / 60:.0f} min")
    print(f"Cost: $0.00 (local computation)")

    if args.dry:
        print(f"\n{'UUID':<38} {'Orient':<10} {'Setting':<12} {'Faces':>5} → {'Style 1':<25} {'Style 2'}")
        print("-" * 120)
        for photo, styles in assignments[:50]:
            setting = (photo.get("setting") or "")[:10]
            s1_name = next((s["name"] for s in NST_STYLES if s["key"] == styles[0]), styles[0])
            s2_name = next((s["name"] for s in NST_STYLES if s["key"] == styles[1]), styles[1]) if len(styles) > 1 else "—"
            print(f"{photo['uuid']:<38} {photo.get('orientation', '?'):<10} {setting:<12} "
                  f"{photo.get('faces_count') or 0:>5} → {s1_name:<25} {s2_name}")
        conn.close()
        return

    # Generate
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = GENERATED_DIR / f"nst_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput: {run_dir}")

    # Load VGG19 once
    cnn_weights = models.VGG19_Weights.DEFAULT

    success_count = 0
    fail_count = 0
    t0 = time.time()

    for img_i, (photo, styles) in enumerate(assignments):
        uid = photo["uuid"]
        source = photo["source_path"]
        img_dir = run_dir / uid

        print(f"\n[{img_i + 1}/{len(assignments)}] {uid}")
        print(f"  {photo.get('orientation', '?')} | {photo.get('setting', '?')} | "
              f"faces={photo.get('faces_count', 0)}")

        content_img = load_image(source, args.size, device)
        original_size = Image.open(source).size

        # Copy original for review UI
        img_dir.mkdir(parents=True, exist_ok=True)
        orig_dest = img_dir / "original.jpg"
        if not orig_dest.exists():
            shutil.copy2(source, orig_dest)

        for style_key in styles:
            style = next((s for s in NST_STYLES if s["key"] == style_key), None)
            if not style:
                continue

            vid = variant_id_for(uid, style_key)
            style_path = STYLES_DIR / style["file"]
            out_path = img_dir / f"{style_key}.jpg"

            # Skip if already done
            row = conn.execute(
                "SELECT generation_status FROM ai_variants WHERE variant_id=?", (vid,)
            ).fetchone()
            if row and row[0] == "success":
                print(f"  {style['name']:<25} — already done, skip")
                success_count += 1
                continue

            print(f"  {style['name']:<25} — generating...", end=" ", flush=True)
            t1 = time.time()

            try:
                style_img = load_style_image(str(style_path), content_img.shape, device)
                output = run_style_transfer(
                    content_img, style_img, device,
                    num_steps=args.steps,
                    style_ratio=style["style_ratio"],
                )
                raw_stylized = tensor_to_image(output, original_size)

                if args.detail > 0:
                    original_pil = Image.open(source).convert("RGB")
                    result = preserve_detail(original_pil, raw_stylized, args.detail)
                else:
                    result = raw_stylized

                result.save(str(out_path), "JPEG", quality=92)
                elapsed_ms = int((time.time() - t1) * 1000)

                db_upsert(conn, vid, uid, style_key, "success", elapsed_ms)
                success_count += 1
                print(f"OK ({elapsed_ms / 1000:.1f}s)")

            except Exception as e:
                elapsed_ms = int((time.time() - t1) * 1000)
                err = str(e)[:200]
                db_upsert(conn, vid, uid, style_key, "failed", elapsed_ms, error=err)
                fail_count += 1
                print(f"FAILED: {err[:60]}")
                import traceback
                traceback.print_exc()

            if device.type == "mps":
                torch.mps.empty_cache()

    conn.close()
    elapsed = time.time() - t0
    print(f"\n{'═' * 60}")
    print(f"  Done in {elapsed / 60:.1f} min")
    print(f"  {success_count} OK, {fail_count} failed")
    print(f"  Cost: $0.00")
    print(f"  Output: {run_dir}")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
