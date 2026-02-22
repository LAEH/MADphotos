#!/usr/bin/env python3
"""Neural Style Transfer — dramatic artistic transformations, 100% local & free.

Uses VGG19 feature matching (Gatys et al.) to apply famous artistic styles
to photos while preserving composition. Runs on Apple Silicon MPS.

5 curated styles from public domain masterworks:
  1. Van Gogh — Starry Night (swirling impasto)
  2. Hokusai — Great Wave (Japanese woodblock print)
  3. Kandinsky — Composition VII (abstract expressionism)
  4. Monet — Water Lilies (soft impressionism)
  5. Munch — The Scream (dramatic expressionism)

Usage:
  .venv-gen/bin/python3 backend/neural_style_transfer.py
  .venv-gen/bin/python3 backend/neural_style_transfer.py --steps 300 --size 768
  .venv-gen/bin/python3 backend/neural_style_transfer.py --count 2
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_FILE = PROJECT_ROOT / "backend" / "style_prompts_test.json"
OUTPUT_ROOT = PROJECT_ROOT / "backend" / "suggest_image_variant" / "output"
STYLES_DIR = PROJECT_ROOT / "backend" / "suggest_image_variant" / "style_references"

# ImageNet normalization for VGG19
MEAN = torch.tensor([0.485, 0.456, 0.406])
STD = torch.tensor([0.229, 0.224, 0.225])

# 5 dramatically different public domain artworks
STYLE_REFS = [
    {
        "name": "Starry Night",
        "safe_name": "starry_night",
        "file": "van_gogh_starry_night.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg/1280px-Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg",
    },
    {
        "name": "Klimt Gold",
        "safe_name": "klimt_gold",
        "file": "klimt_the_kiss.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/4/40/The_Kiss_-_Gustav_Klimt_-_Google_Cultural_Institute.jpg",
    },
    {
        "name": "Seurat Pointillism",
        "safe_name": "seurat_pointillism",
        "file": "seurat_sunday.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/7/7d/A_Sunday_on_La_Grande_Jatte%2C_Georges_Seurat%2C_1884.jpg",
    },
    {
        "name": "Water Lilies",
        "safe_name": "water_lilies",
        "file": "monet_water_lilies.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/aa/Claude_Monet_-_Water_Lilies_-_1906%2C_Chicago.jpg/1280px-Claude_Monet_-_Water_Lilies_-_1906%2C_Chicago.jpg",
    },
    {
        "name": "The Scream",
        "safe_name": "the_scream",
        "file": "munch_the_scream.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Edvard_Munch%2C_1893%2C_The_Scream%2C_oil%2C_tempera_and_pastel_on_cardboard%2C_91_x_73_cm%2C_National_Gallery_of_Norway.jpg/800px-Edvard_Munch%2C_1893%2C_The_Scream%2C_oil%2C_tempera_and_pastel_on_cardboard%2C_91_x_73_cm%2C_National_Gallery_of_Norway.jpg",
    },
]

# VGG19 layers for feature extraction
CONTENT_LAYERS = ["conv_4"]
# Weight deeper layers more heavily to capture global style (color, composition)
# rather than fine texture, which overwhelms content on complex references.
STYLE_LAYERS = {
    "conv_1": 0.1,   # fine texture
    "conv_2": 0.1,   # medium texture
    "conv_3": 0.2,   # medium features
    "conv_4": 0.3,   # high-level patterns
    "conv_5": 0.3,   # global style
}


def get_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def download_style_refs() -> None:
    STYLES_DIR.mkdir(parents=True, exist_ok=True)
    for ref in STYLE_REFS:
        path = STYLES_DIR / ref["file"]
        if path.exists():
            continue
        print(f"  Downloading {ref['name']}...")
        req = urllib.request.Request(ref["url"], headers={
            "User-Agent": "MADphotos/1.0 (style-transfer-research)"
        })
        with urllib.request.urlopen(req) as resp, open(path, "wb") as f:
            f.write(resp.read())
    print(f"  Style references ready: {STYLES_DIR}")


def load_image(path: str, max_size: int, device: torch.device) -> torch.Tensor:
    """Load image as tensor [0,1] — normalization happens inside the model."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = max_size / max(w, h)
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return transforms.ToTensor()(img).unsqueeze(0).to(device)


def load_style_image(path: str, content_shape: tuple, device: torch.device) -> torch.Tensor:
    """Load style image resized to match content tensor dimensions."""
    img = Image.open(path).convert("RGB")
    _, _, h, w = content_shape
    img = img.resize((w, h), Image.LANCZOS)
    return transforms.ToTensor()(img).unsqueeze(0).to(device)


def tensor_to_image(tensor: torch.Tensor, original_size: tuple[int, int]) -> Image.Image:
    """Convert output tensor back to PIL Image at original dimensions."""
    img = tensor.cpu().clone().squeeze(0).clamp(0, 1)
    img = transforms.ToPILImage()(img)
    if img.size != original_size:
        img = img.resize(original_size, Image.LANCZOS)
    return img


def preserve_detail(original: Image.Image, stylized: Image.Image,
                    detail_strength: float = 0.8) -> Image.Image:
    """Blend back original's high-frequency detail into the stylized image.

    This preserves edges, textures, and recognizable features while keeping
    the artistic color palette and broad brushwork from the style transfer.
    """
    import numpy as np
    import cv2

    orig = np.array(original).astype(np.float32)
    styled = np.array(stylized.resize(original.size, Image.LANCZOS)).astype(np.float32)

    # Extract high-frequency detail (edges, texture) from original
    blur = cv2.GaussianBlur(orig, (0, 0), sigmaX=5)
    detail = orig - blur

    # Also preserve luminance structure from original
    orig_gray = cv2.cvtColor(orig, cv2.COLOR_RGB2GRAY)
    styled_gray = cv2.cvtColor(styled.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)

    # Transfer original's luminance to stylized (keeps subject visible)
    lum_ratio = np.where(styled_gray > 1, orig_gray / styled_gray, 1.0)
    lum_ratio = np.clip(lum_ratio, 0.3, 3.0)  # prevent extreme adjustments
    lum_blend = 0.4  # how much original luminance to restore

    result = styled.copy()
    for c in range(3):
        result[:, :, c] = styled[:, :, c] * (1 - lum_blend + lum_blend * lum_ratio)

    # Add back high-frequency detail
    result = result + detail * detail_strength
    result = np.clip(result, 0, 255).astype(np.uint8)
    return Image.fromarray(result)


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
    """ImageNet normalization layer inserted at the start of the model."""
    def __init__(self, mean: torch.Tensor, std: torch.Tensor):
        super().__init__()
        self.mean = mean.clone().view(-1, 1, 1)
        self.std = std.clone().view(-1, 1, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return (x - self.mean) / self.std


def build_model(
    cnn: nn.Module,
    content_img: torch.Tensor,
    style_img: torch.Tensor,
    device: torch.device,
) -> tuple[nn.Sequential, list[ContentLoss], list[StyleLoss]]:
    normalization = Normalization(MEAN.to(device), STD.to(device))
    content_losses: list[ContentLoss] = []
    style_losses: list[StyleLoss] = []
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

    # Trim model after last content/style loss
    for k in range(len(model) - 1, -1, -1):
        if isinstance(model[k], (ContentLoss, StyleLoss)):
            break
    model = model[: k + 1]
    return model, content_losses, style_losses


def run_style_transfer(
    content_img: torch.Tensor,
    style_img: torch.Tensor,
    device: torch.device,
    num_steps: int = 300,
    style_ratio: float = 100.0,
    content_weight: float = 1.0,
) -> torch.Tensor:
    """Run NST with auto-balanced style weight.

    style_ratio controls how dominant the style is.
    Higher = more stylization. 1e4 = moderate, 1e5 = strong, 1e6 = extreme.
    The actual style_weight is normalized by the initial style loss so results
    are consistent across different style references regardless of complexity.
    """
    cnn = models.vgg19(weights=models.VGG19_Weights.DEFAULT).features.to(device).eval()
    for param in cnn.parameters():
        param.requires_grad_(False)

    model, content_losses, style_losses = build_model(cnn, content_img, style_img, device)

    # Start from content image
    input_img = content_img.clone().requires_grad_(True)

    # Auto-balance: normalize style_weight by initial style loss so all
    # styles get the same initial push regardless of reference complexity.
    # style_weight * init_style = style_ratio (constant across all styles)
    with torch.no_grad():
        model(input_img)
        init_style = sum(sl.loss.item() for sl in style_losses)

    if init_style > 1e-10:
        style_weight = style_ratio / init_style
    else:
        style_weight = 1e6

    print(f"      auto-balance: weight={style_weight:.0f} "
          f"(init_style={init_style:.6f}, ratio={style_ratio:.0f})")

    optimizer = optim.LBFGS([input_img])

    run = [0]
    while run[0] < num_steps:
        def closure():
            input_img.data.clamp_(0, 1)
            optimizer.zero_grad()
            model(input_img)

            s_loss = sum(sl.loss for sl in style_losses)
            c_loss = sum(cl.loss for cl in content_losses)
            loss = style_weight * s_loss + content_weight * c_loss
            loss.backward()

            run[0] += 1
            if run[0] % 100 == 0:
                print(f"      step {run[0]}/{num_steps}  "
                      f"style={s_loss.item():.6f}  content={c_loss.item():.2f}")
            return loss

        optimizer.step(closure)

    input_img.data.clamp_(0, 1)
    return input_img


def get_original_size(path: str) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--count", type=int, default=0, help="0 = all images")
    parser.add_argument("--style-ratio", type=float, default=5e4,
                        help="Style dominance (1e4=moderate, 5e4=strong, 1e5=extreme)")
    parser.add_argument("--detail", type=float, default=0.8,
                        help="Detail preservation from original (0=none, 0.8=strong)")
    args = parser.parse_args()

    device = get_device()
    print(f"Device: {device}")
    print(f"Steps: {args.steps} | Size: {args.size}px | Style ratio: {args.style_ratio}")

    print("\nDownloading style references...")
    download_style_refs()

    prompts_data = json.loads(PROMPTS_FILE.read_text())
    if args.count > 0:
        prompts_data = prompts_data[: args.count]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "config.json").write_text(json.dumps({
        "method": "neural_style_transfer",
        "model": "VGG19",
        "device": str(device),
        "steps": args.steps,
        "size": args.size,
        "style_ratio": args.style_ratio,
        "detail_preservation": args.detail,
        "styles": [s["name"] for s in STYLE_REFS],
        "images": len(prompts_data),
    }, indent=2))

    # Copy style references into experiment
    ref_dir = run_dir / "style_references"
    ref_dir.mkdir(exist_ok=True)
    for ref in STYLE_REFS:
        src = STYLES_DIR / ref["file"]
        if src.exists():
            shutil.copy2(src, ref_dir / ref["file"])

    total = len(prompts_data) * len(STYLE_REFS)
    done = 0
    t0 = time.time()

    print(f"\n{len(prompts_data)} images × {len(STYLE_REFS)} styles = {total} transfers")
    print(f"Experiment: {run_dir}\n")

    for i, img_data in enumerate(prompts_data):
        uuid = img_data["uuid"]
        src_path = img_data["path"]
        original_size = get_original_size(src_path)

        img_dir = run_dir / uuid
        img_dir.mkdir(parents=True, exist_ok=True)

        orig_dest = img_dir / "original.jpg"
        if not orig_dest.exists():
            shutil.copy2(src_path, orig_dest)

        print(f"{'=' * 60}")
        print(f"[{i + 1}/{len(prompts_data)}] {uuid}")
        print(f"  Original: {original_size[0]}×{original_size[1]}")

        content_img = load_image(src_path, args.size, device)

        for j, ref in enumerate(STYLE_REFS):
            style_path = STYLES_DIR / ref["file"]
            out_path = img_dir / f"nst_{j}_{ref['safe_name']}.jpg"

            if out_path.exists():
                print(f"  [{j + 1}/{len(STYLE_REFS)}] {ref['name']}: exists, skipping")
                done += 1
                continue

            print(f"  [{j + 1}/{len(STYLE_REFS)}] {ref['name']}...")
            t1 = time.time()

            try:
                style_img = load_style_image(str(style_path), content_img.shape, device)
                output = run_style_transfer(
                    content_img, style_img, device,
                    num_steps=args.steps,
                    style_ratio=args.style_ratio,
                )
                raw_stylized = tensor_to_image(output, original_size)

                # Blend back original's detail (edges, luminance, texture)
                if args.detail > 0:
                    original_pil = Image.open(src_path).convert("RGB")
                    result_img = preserve_detail(original_pil, raw_stylized, args.detail)
                else:
                    result_img = raw_stylized

                result_img.save(str(out_path), "JPEG", quality=92)

                elapsed_s = time.time() - t1
                print(f"    ✓ {elapsed_s:.1f}s → {out_path.name}")
            except Exception as e:
                print(f"    ✗ FAILED: {e}")
                import traceback
                traceback.print_exc()

            done += 1

            if device.type == "mps":
                torch.mps.empty_cache()

        print()

    elapsed = time.time() - t0
    count = len(list(run_dir.glob("*/nst_*.jpg")))
    print(f"\nDone! {count} images in {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"Experiment: {run_dir}")


if __name__ == "__main__":
    main()
