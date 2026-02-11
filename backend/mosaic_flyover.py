#!/usr/bin/env python3
"""
Mosaic Flyover Video Generator
===============================
Projects 846 curated picks onto a 2D canvas via UMAP on DINOv2 vectors,
then renders a smooth 60fps flyover video travelling above the mosaic.

Three camera styles:
  breathing  — wide constellation → slow zoom into clusters → meditative pullback
  drift      — continuous satellite-like drift at medium altitude
  dives      — rapid zoom dives into individual photos, energetic & punchy

Usage:
  python3 backend/mosaic_flyover.py                     # default: breathing, 30s
  python3 backend/mosaic_flyover.py --style drift
  python3 backend/mosaic_flyover.py --style dives
  python3 backend/mosaic_flyover.py --all-styles
  python3 backend/mosaic_flyover.py --duration 60 --res 4k
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LANCE_PATH = str(PROJECT_ROOT / "images" / "vectors.lance")
PICKS_JSON = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"
OUTPUT_DIR = PROJECT_ROOT / "frontend" / "show" / "data"
MOBILE_DIR = PROJECT_ROOT / "images" / "rendered" / "mobile" / "jpeg"
THUMB_DIR = PROJECT_ROOT / "images" / "rendered" / "thumb" / "jpeg"
MICRO_DIR = PROJECT_ROOT / "images" / "rendered" / "micro" / "jpeg"

# ── Canvas / Rendering ──────────────────────────────────────────────────
CANVAS_SIZE = 8000          # virtual canvas units
BASE_TILE = 180             # base tile dimension
BG_COLOR = (10, 10, 10)     # charcoal #0a0a0a
FPS = 60

RESOLUTIONS = {
    "1080p": (1920, 1080),
    "4k": (3840, 2160),
}


# ═══════════════════════════════════════════════════════════════════════
# Step 1: Load picks & UMAP projection
# ═══════════════════════════════════════════════════════════════════════

def load_picks() -> Tuple[List[str], Dict[str, str]]:
    """Load pick UUIDs and their orientation (portrait/landscape)."""
    with open(PICKS_JSON) as f:
        data = json.load(f)
    orientation = {}
    uuids = []
    for uuid in data.get("portrait", []):
        orientation[uuid] = "portrait"
        uuids.append(uuid)
    for uuid in data.get("landscape", []):
        orientation[uuid] = "landscape"
        uuids.append(uuid)
    return uuids, orientation


def load_vectors(pick_uuids: List[str]) -> np.ndarray:
    """Extract DINOv2-Large 1024d vectors from LanceDB for pick UUIDs."""
    import lancedb

    db = lancedb.connect(LANCE_PATH)
    table_list = db.list_tables()
    table_names = table_list.tables if hasattr(table_list, "tables") else list(table_list)
    table_name = "image_vectors_v2" if "image_vectors_v2" in table_names else "image_vectors"
    table = db.open_table(table_name)
    print(f"  vectors: using '{table_name}'")

    arrow = table.to_arrow()
    all_uuids = arrow.column("uuid").to_pylist()
    all_dino = arrow.column("dino").to_pylist()

    uuid_to_vec = {u: v for u, v in zip(all_uuids, all_dino)}

    vectors = []
    missing = []
    for uuid in pick_uuids:
        vec = uuid_to_vec.get(uuid)
        if vec is not None:
            vectors.append(vec)
        else:
            missing.append(uuid)

    if missing:
        print(f"  warning: {len(missing)} picks missing vectors, skipping")

    return np.array(vectors, dtype=np.float32), missing


def project_umap(vectors: np.ndarray) -> np.ndarray:
    """UMAP 2D projection with t-SNE fallback."""
    try:
        import umap
        print("  projection: UMAP (n_neighbors=15, min_dist=0.1, cosine)")
        reducer = umap.UMAP(
            n_components=2,
            n_neighbors=15,
            min_dist=0.1,
            metric="cosine",
            random_state=42,
        )
        coords = reducer.fit_transform(vectors)
    except ImportError:
        from sklearn.manifold import TSNE
        print("  projection: t-SNE fallback (cosine)")
        coords = TSNE(
            n_components=2,
            metric="cosine",
            random_state=42,
            perplexity=min(30, len(vectors) - 1),
        ).fit_transform(vectors)

    # Normalize to canvas with padding
    pad = 0.05
    for dim in range(2):
        mn, mx = coords[:, dim].min(), coords[:, dim].max()
        span = mx - mn if mx > mn else 1.0
        coords[:, dim] = pad * CANVAS_SIZE + (coords[:, dim] - mn) / span * CANVAS_SIZE * (1 - 2 * pad)

    return coords


# ═══════════════════════════════════════════════════════════════════════
# Step 2: Tile layout
# ═══════════════════════════════════════════════════════════════════════

class Tile:
    __slots__ = ("uuid", "cx", "cy", "w", "h", "orientation")

    def __init__(self, uuid: str, cx: float, cy: float, orientation: str):
        self.uuid = uuid
        self.cx = cx
        self.cy = cy
        self.orientation = orientation
        if orientation == "portrait":
            self.w = BASE_TILE
            self.h = int(BASE_TILE * 1.5)
        else:
            self.w = int(BASE_TILE * 1.5)
            self.h = BASE_TILE

    @property
    def left(self) -> float:
        return self.cx - self.w / 2

    @property
    def top(self) -> float:
        return self.cy - self.h / 2


def build_tiles(
    uuids: List[str],
    coords: np.ndarray,
    orientations: Dict[str, str],
) -> List[Tile]:
    """Create tiles from UMAP coords with slight jitter."""
    rng = np.random.RandomState(7)
    tiles = []
    for i, uuid in enumerate(uuids):
        jx = rng.uniform(-5, 5)
        jy = rng.uniform(-5, 5)
        t = Tile(uuid, coords[i, 0] + jx, coords[i, 1] + jy, orientations[uuid])
        tiles.append(t)
    return tiles


# ═══════════════════════════════════════════════════════════════════════
# Step 3: Spatial hash for O(1) tile lookup
# ═══════════════════════════════════════════════════════════════════════

class SpatialHash:
    """Grid-based spatial index for fast viewport queries."""

    def __init__(self, tiles: List[Tile], cell_size: float = 400):
        self.cell_size = cell_size
        self.grid: Dict[Tuple[int, int], List[int]] = {}
        for idx, t in enumerate(tiles):
            for cx, cy in self._cells_for(t):
                self.grid.setdefault((cx, cy), []).append(idx)

    def _cells_for(self, t: Tile) -> List[Tuple[int, int]]:
        cs = self.cell_size
        x0 = int(math.floor(t.left / cs))
        y0 = int(math.floor(t.top / cs))
        x1 = int(math.floor((t.left + t.w) / cs))
        y1 = int(math.floor((t.top + t.h) / cs))
        return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]

    def query(self, vx0: float, vy0: float, vx1: float, vy1: float) -> set:
        """Return tile indices visible in viewport (vx0,vy0)-(vx1,vy1)."""
        cs = self.cell_size
        cx0 = int(math.floor(vx0 / cs))
        cy0 = int(math.floor(vy0 / cs))
        cx1 = int(math.floor(vx1 / cs))
        cy1 = int(math.floor(vy1 / cs))
        result = set()
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                bucket = self.grid.get((cx, cy))
                if bucket:
                    result.update(bucket)
        return result


# ═══════════════════════════════════════════════════════════════════════
# Step 4: Image cache with zoom-adaptive resolution
# ═══════════════════════════════════════════════════════════════════════

class ImageCache:
    """Two-level cache: source images (by tier) + resized images (by quantized size).

    The resized cache avoids re-calling PIL resize when zoom changes slowly,
    which is the #1 bottleneck in the render loop.
    """

    QUANT = 4  # quantize target sizes to 4px steps — smaller = less size-jitter

    def __init__(self, max_source: int = 500, max_resized: int = 2000):
        self._src: OrderedDict[Tuple[str, str], Image.Image] = OrderedDict()
        self._resized: OrderedDict[Tuple[str, int, int], Image.Image] = OrderedDict()
        self._max_src = max_source
        self._max_resized = max_resized

    def _load_source(self, uuid: str, screen_size: int) -> Optional[Image.Image]:
        """Load source image at appropriate tier."""
        if screen_size >= 200:
            tier, path = "mobile", MOBILE_DIR / f"{uuid}.jpg"
        elif screen_size >= 60:
            tier, path = "thumb", THUMB_DIR / f"{uuid}.jpg"
        else:
            tier, path = "micro", MICRO_DIR / f"{uuid}.jpg"

        key = (uuid, tier)
        if key in self._src:
            self._src.move_to_end(key)
            return self._src[key]

        if not path.exists():
            for fb_dir in (MOBILE_DIR, THUMB_DIR, MICRO_DIR):
                fb = fb_dir / f"{uuid}.jpg"
                if fb.exists():
                    path = fb
                    break
            else:
                return None

        try:
            img = Image.open(path)
            img.load()
            img = img.convert("RGB")
        except Exception:
            return None

        self._src[key] = img
        if len(self._src) > self._max_src:
            self._src.popitem(last=False)
        return img

    def get_resized(self, uuid: str, tw: int, th: int) -> Optional[Image.Image]:
        """Get image resized to (tw, th), using quantized cache."""
        if tw < 3 or th < 3:
            return None

        q = self.QUANT
        qw = max(q, (tw + q - 1) // q * q)
        qh = max(q, (th + q - 1) // q * q)

        rkey = (uuid, qw, qh)
        if rkey in self._resized:
            self._resized.move_to_end(rkey)
            return self._resized[rkey]

        src = self._load_source(uuid, max(tw, th))
        if src is None:
            return None

        method = Image.BILINEAR if max(qw, qh) < 100 else Image.LANCZOS
        resized = src.resize((qw, qh), method)

        self._resized[rkey] = resized
        if len(self._resized) > self._max_resized:
            self._resized.popitem(last=False)
        return resized


# ═══════════════════════════════════════════════════════════════════════
# Step 5: Camera paths — Catmull-Rom spline + Gaussian pre-smoothing
# ═══════════════════════════════════════════════════════════════════════

def catmull_rom(p0, p1, p2, p3, t):
    """Catmull-Rom spline interpolation at parameter t in [0, 1]."""
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        (2 * p1)
        + (-p0 + p2) * t
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
        + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
    )


def _interpolate_raw(
    keyframes: List[Tuple[float, float, float, float]],
    time_sec: float,
) -> Tuple[float, float, float]:
    """Raw Catmull-Rom interpolation — NO per-segment easing (preserves C1 continuity)."""
    if time_sec <= keyframes[0][0]:
        return keyframes[0][1], keyframes[0][2], keyframes[0][3]
    if time_sec >= keyframes[-1][0]:
        return keyframes[-1][1], keyframes[-1][2], keyframes[-1][3]

    # Find segment
    seg = 0
    for i in range(len(keyframes) - 1):
        if keyframes[i][0] <= time_sec <= keyframes[i + 1][0]:
            seg = i
            break

    t0, t1 = keyframes[seg][0], keyframes[seg + 1][0]
    local_t = (time_sec - t0) / (t1 - t0) if t1 > t0 else 0
    # NO easing here — linear parameterization keeps the spline smooth

    # Gather 4 control points for Catmull-Rom
    indices = [max(0, seg - 1), seg, min(seg + 1, len(keyframes) - 1), min(seg + 2, len(keyframes) - 1)]
    pts = [keyframes[i] for i in indices]

    x = catmull_rom(pts[0][1], pts[1][1], pts[2][1], pts[3][1], local_t)
    y = catmull_rom(pts[0][2], pts[1][2], pts[2][2], pts[3][2], local_t)
    z = catmull_rom(pts[0][3], pts[1][3], pts[2][3], pts[3][3], local_t)
    return float(x), float(y), max(0.3, float(z))


def precompute_camera_path(
    keyframes: List[Tuple[float, float, float, float]],
    total_frames: int,
    fps: int,
    smooth_sigma: float = 8.0,
) -> np.ndarray:
    """Pre-compute the entire camera path with Gaussian smoothing for buttery motion.

    Returns shape (total_frames, 3) array of (x, y, zoom).
    smooth_sigma = number of frames for Gaussian kernel (higher = smoother).
    """
    from scipy.ndimage import gaussian_filter1d

    # Sample raw spline at every frame
    raw = np.empty((total_frames, 3), dtype=np.float64)
    for i in range(total_frames):
        t_sec = i / fps
        raw[i] = _interpolate_raw(keyframes, t_sec)

    # Apply Gaussian smoothing independently to x, y, zoom
    # Use 'nearest' mode to clamp endpoints (no fade to zero)
    smoothed = np.empty_like(raw)
    smoothed[:, 0] = gaussian_filter1d(raw[:, 0], sigma=smooth_sigma, mode='nearest')
    smoothed[:, 1] = gaussian_filter1d(raw[:, 1], sigma=smooth_sigma, mode='nearest')
    # Use smaller sigma for zoom to preserve intentional zoom changes
    smoothed[:, 2] = gaussian_filter1d(raw[:, 2], sigma=smooth_sigma * 0.6, mode='nearest')

    # Ensure zoom stays positive
    smoothed[:, 2] = np.maximum(smoothed[:, 2], 0.3)

    return smoothed


def compute_cluster_waypoints(
    tiles: List[Tile], n_clusters: int = 8
) -> Tuple[List[Tuple[float, float]], List[int]]:
    """KMeans on tile positions → cluster centers + nearest-neighbor travel order."""
    from sklearn.cluster import KMeans

    positions = np.array([[t.cx, t.cy] for t in tiles], dtype=np.float32)
    k = min(n_clusters, len(tiles))
    km = KMeans(n_clusters=k, random_state=42, n_init=10).fit(positions)
    centers = km.cluster_centers_.tolist()

    # Nearest-neighbor TSP for visit order
    visited = [0]
    remaining = set(range(1, k))
    while remaining:
        last = centers[visited[-1]]
        best_d, best_i = float("inf"), 0
        for r in remaining:
            d = (centers[r][0] - last[0]) ** 2 + (centers[r][1] - last[1]) ** 2
            if d < best_d:
                best_d, best_i = d, r
        visited.append(best_i)
        remaining.discard(best_i)

    ordered_centers = [(centers[i][0], centers[i][1]) for i in visited]

    # For each cluster, find the tile closest to center (best dive target)
    labels = km.labels_
    dive_targets = []
    for ci in visited:
        members = [j for j, lbl in enumerate(labels) if lbl == ci]
        cx, cy = centers[ci]
        best_j = min(members, key=lambda j: (tiles[j].cx - cx) ** 2 + (tiles[j].cy - cy) ** 2)
        dive_targets.append(best_j)

    return ordered_centers, dive_targets


def make_keyframes_breathing(
    centers: List[Tuple[float, float]],
    dive_targets: List[int],
    tiles: List[Tile],
    duration: float,
) -> List[Tuple[float, float, float, float]]:
    """Cinematic Breathing: wide → slow ease in → pan → pullback → deep zoom → wide.

    Uses dense keyframes with gentle position offsets for smooth motion.
    """
    mid_x = CANVAS_SIZE / 2
    mid_y = CANVAS_SIZE / 2
    visit = min(4, len(centers))
    kf = []

    # Wide opening — hold for a breath
    kf.append((0.0, mid_x, mid_y, 1.0))
    kf.append((duration * 0.06, mid_x + 50, mid_y + 30, 1.0))

    # Visit clusters with slow approach + gentle pan
    cluster_time = duration * 0.6 / visit
    for i in range(visit):
        cx, cy = centers[i]
        t0 = duration * 0.08 + cluster_time * i
        # Approach
        kf.append((t0, cx - 80, cy - 40, 2.0))
        # Arrive
        kf.append((t0 + cluster_time * 0.4, cx, cy, 2.8))
        # Gentle pan
        kf.append((t0 + cluster_time * 0.8, cx + 60, cy + 30, 2.6))

    # Deep zoom into one photo
    if dive_targets:
        target = tiles[dive_targets[0]]
        t_dive = duration * 0.72
        kf.append((t_dive, target.cx - 30, target.cy, 4.0))
        kf.append((t_dive + duration * 0.06, target.cx, target.cy, 5.5))
        kf.append((t_dive + duration * 0.12, target.cx + 15, target.cy + 10, 5.8))

    # Final wide pullback
    kf.append((duration * 0.92, mid_x, mid_y, 1.5))
    kf.append((duration, mid_x, mid_y, 0.9))

    kf.sort(key=lambda k: k[0])
    return kf


def make_keyframes_drift(
    centers: List[Tuple[float, float]],
    dive_targets: List[int],
    tiles: List[Tile],
    duration: float,
) -> List[Tuple[float, float, float, float]]:
    """Continuous Drift: medium altitude, gentle zoom pulses, visits all clusters.

    Dense keyframes with sinusoidal zoom modulation for smooth breathing.
    """
    kf = []
    n = len(centers)
    segment = duration / (n + 1)

    # Start at first cluster
    kf.append((0.0, centers[0][0], centers[0][1], 2.5))

    for i in range(n):
        cx, cy = centers[i]
        t = segment * (i + 1)
        # Smooth sinusoidal zoom between 2.2 and 3.2
        z = 2.7 + 0.5 * math.sin(i * math.pi / 3)
        kf.append((t, cx, cy, z))
        # Add intermediate point midway to next cluster for continuous motion
        if i < n - 1:
            nx, ny = centers[i + 1]
            mid_t = t + segment * 0.5
            mid_z = 2.7 + 0.5 * math.sin((i + 0.5) * math.pi / 3)
            kf.append((mid_t, (cx + nx) / 2, (cy + ny) / 2, mid_z))

    # End near start for smooth loop potential
    kf.append((duration, centers[0][0], centers[0][1], 2.5))
    return kf


def make_keyframes_dives(
    centers: List[Tuple[float, float]],
    dive_targets: List[int],
    tiles: List[Tile],
    duration: float,
) -> List[Tuple[float, float, float, float]]:
    """Deep Dives: wide → zoom to photo → hold → pullback → slide to next. 4 dives.

    Dense keyframes with intermediate cruise altitude between dives.
    """
    mid_x = CANVAS_SIZE / 2
    mid_y = CANVAS_SIZE / 2
    kf = []

    n_dives = min(4, len(dive_targets))
    dive_dur = duration / n_dives

    # Wide start
    kf.append((0.0, mid_x, mid_y, 1.0))
    kf.append((dive_dur * 0.15, mid_x, mid_y, 1.2))

    for i in range(n_dives):
        target = tiles[dive_targets[i]]
        t_base = i * dive_dur

        # Cruise altitude between dives (except before first)
        if i > 0:
            prev = tiles[dive_targets[i - 1]]
            # Smooth transition at cruise altitude between targets
            kf.append((t_base + dive_dur * 0.05, prev.cx, prev.cy, 2.0))
            kf.append((t_base + dive_dur * 0.15,
                        (prev.cx + target.cx) / 2, (prev.cy + target.cy) / 2, 1.8))

        # Approach from above
        kf.append((t_base + dive_dur * 0.3, target.cx, target.cy, 3.0))
        # Zoom in
        kf.append((t_base + dive_dur * 0.5, target.cx, target.cy, 5.5))
        # Hold with micro-drift
        kf.append((t_base + dive_dur * 0.7, target.cx + 15, target.cy + 8, 5.8))
        # Pull back
        kf.append((t_base + dive_dur * 0.9, target.cx, target.cy, 2.5))

    # Final wide
    kf.append((duration * 0.95, mid_x, mid_y, 1.2))
    kf.append((duration, mid_x, mid_y, 1.0))
    kf.sort(key=lambda k: k[0])
    return kf


STYLE_BUILDERS = {
    "breathing": make_keyframes_breathing,
    "drift": make_keyframes_drift,
    "dives": make_keyframes_dives,
}


# ═══════════════════════════════════════════════════════════════════════
# Step 6: Vignette overlay
# ═══════════════════════════════════════════════════════════════════════

def make_vignette_rgb(width: int, height: int) -> Image.Image:
    """Create a subtle radial vignette as an RGB image for ImageChops.multiply (pure C)."""
    from PIL import ImageChops  # noqa: F811
    y = np.linspace(-1, 1, height, dtype=np.float32)
    x = np.linspace(-1, 1, width, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    r = np.sqrt(xx ** 2 + yy ** 2)
    # 255 in center, ~153 at far corners (40% darken)
    gray = (255 * (1.0 - np.clip((r - 0.6) / 0.8, 0, 1) * 0.4)).astype(np.uint8)
    # Stack to 3-channel RGB for ImageChops.multiply
    rgb = np.stack([gray, gray, gray], axis=-1)
    return Image.fromarray(rgb)


# ═══════════════════════════════════════════════════════════════════════
# Step 7: Frame renderer (PIL-based compositing)
# ═══════════════════════════════════════════════════════════════════════

def render_frame(
    cam_x: float,
    cam_y: float,
    zoom: float,
    tiles: List[Tile],
    spatial: SpatialHash,
    cache: ImageCache,
    width: int,
    height: int,
    vignette_rgb: Image.Image,
    bg_frame: Image.Image,
) -> bytes:
    """Render a single frame using PIL paste + ImageChops (all pure C) → raw RGB bytes."""
    from PIL import ImageChops

    # Viewport in canvas coords
    vw = width / zoom
    vh = height / zoom
    vx0 = cam_x - vw / 2
    vy0 = cam_y - vh / 2
    vx1 = cam_x + vw / 2
    vy1 = cam_y + vh / 2

    # Start with background copy
    frame = bg_frame.copy()

    # Find visible tiles
    visible_indices = spatial.query(vx0, vy0, vx1, vy1)

    for idx in visible_indices:
        t = tiles[idx]

        # Screen position & size
        sx = (t.left - vx0) * zoom
        sy = (t.top - vy0) * zoom
        sw = t.w * zoom
        sh = t.h * zoom

        if sw < 3 or sh < 3:
            continue

        sx_int = int(round(sx))
        sy_int = int(round(sy))
        sw_int = max(1, int(round(sw)))
        sh_int = max(1, int(round(sh)))

        if sx_int + sw_int <= 0 or sy_int + sh_int <= 0:
            continue
        if sx_int >= width or sy_int >= height:
            continue

        # Get pre-resized (quantized cache) image
        img = cache.get_resized(t.uuid, sw_int, sh_int)
        if img is None:
            continue

        # Crop to exact size if quantized cache returned slightly larger
        if img.width != sw_int or img.height != sh_int:
            img = img.crop((0, 0, min(sw_int, img.width), min(sh_int, img.height)))

        # Clip source if partially off-screen
        src_x0 = max(0, -sx_int)
        src_y0 = max(0, -sy_int)
        if src_x0 > 0 or src_y0 > 0:
            img = img.crop((src_x0, src_y0, img.width, img.height))
            sx_int = max(0, sx_int)
            sy_int = max(0, sy_int)

        # PIL paste — fast C implementation
        try:
            frame.paste(img, (sx_int, sy_int))
        except Exception:
            continue

    # Apply vignette — pure C path (pixel = frame * vignette / 255)
    frame = ImageChops.multiply(frame, vignette_rgb)
    return frame.tobytes()


# ═══════════════════════════════════════════════════════════════════════
# Step 8: Main render pipeline
# ═══════════════════════════════════════════════════════════════════════

def render_video(
    style: str,
    tiles: List[Tile],
    spatial: SpatialHash,
    duration: float,
    resolution: str,
    centers: List[Tuple[float, float]],
    dive_targets: List[int],
) -> Path:
    """Render full video for a given style."""
    width, height = RESOLUTIONS[resolution]
    total_frames = int(duration * FPS)

    # Build camera keyframes → pre-smooth entire path
    builder = STYLE_BUILDERS[style]
    keyframes = builder(centers, dive_targets, tiles, duration)

    # Sigma scales with FPS — 8 frames at 60fps ≈ 133ms window
    # Dives use less smoothing to keep the punch
    sigma = 6.0 if style == "dives" else 10.0
    camera_path = precompute_camera_path(keyframes, total_frames, FPS, smooth_sigma=sigma)

    print(f"\n{'='*60}")
    print(f"  Style:      {style}")
    print(f"  Duration:   {duration}s @ {FPS}fps = {total_frames} frames")
    print(f"  Resolution: {width}x{height} ({resolution})")
    print(f"  Keyframes:  {len(keyframes)}, smoothing sigma={sigma}")
    print(f"{'='*60}")

    # Output path
    out_path = OUTPUT_DIR / f"mosaic_{style}_{int(duration)}s.mp4"

    # Vignette (RGB for ImageChops.multiply) + reusable background
    vignette_rgb = make_vignette_rgb(width, height)
    bg_frame = Image.new("RGB", (width, height), BG_COLOR)

    # Image cache
    cache = ImageCache(max_source=500, max_resized=2000)

    # FFmpeg process
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-pixel_format", "rgb24",
        "-video_size", f"{width}x{height}",
        "-framerate", str(FPS),
        "-i", "pipe:0",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_path),
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    t_start = time.time()
    try:
        for frame_i in range(total_frames):
            cam_x, cam_y, zoom = camera_path[frame_i]

            raw = render_frame(
                cam_x, cam_y, zoom, tiles, spatial, cache, width, height,
                vignette_rgb, bg_frame,
            )
            proc.stdin.write(raw)

            # Progress
            if frame_i % FPS == 0 or frame_i == total_frames - 1:
                elapsed = time.time() - t_start
                fps_actual = (frame_i + 1) / elapsed if elapsed > 0 else 0
                pct = (frame_i + 1) / total_frames * 100
                remaining = (total_frames - frame_i - 1) / fps_actual if fps_actual > 0 else 0
                sys.stdout.write(
                    f"\r  [{pct:5.1f}%] frame {frame_i+1}/{total_frames}  "
                    f"{fps_actual:.1f} fps  ETA {remaining:.0f}s  "
                    f"zoom={zoom:.1f}  "
                )
                sys.stdout.flush()

    finally:
        proc.stdin.close()
        stderr = proc.stderr.read().decode()
        proc.wait()

    elapsed = time.time() - t_start
    print(f"\n  Done in {elapsed:.1f}s — {out_path.name} ({out_path.stat().st_size / (1024*1024):.1f} MB)")

    if proc.returncode != 0:
        print(f"  ffmpeg error: {stderr[-500:]}")
        sys.exit(1)

    return out_path


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Mosaic Flyover Video Generator")
    parser.add_argument("--style", choices=["breathing", "drift", "dives"], default="breathing")
    parser.add_argument("--all-styles", action="store_true", help="Render all 3 styles")
    parser.add_argument("--duration", type=float, default=30, help="Video duration in seconds")
    parser.add_argument("--res", choices=["1080p", "4k"], default="1080p")
    args = parser.parse_args()

    print("Mosaic Flyover Video Generator")
    print("=" * 40)

    # Step 1: Load picks
    print("\n[1/5] Loading picks...")
    pick_uuids, orientations = load_picks()
    print(f"  {len(pick_uuids)} picks ({sum(1 for v in orientations.values() if v == 'portrait')} portrait, "
          f"{sum(1 for v in orientations.values() if v == 'landscape')} landscape)")

    # Step 2: Load vectors & UMAP
    print("\n[2/5] Loading vectors & projecting to 2D...")
    vectors, missing = load_vectors(pick_uuids)
    # Remove missing UUIDs
    if missing:
        missing_set = set(missing)
        pick_uuids = [u for u in pick_uuids if u not in missing_set]
    print(f"  {vectors.shape[0]} vectors × {vectors.shape[1]}d")

    coords = project_umap(vectors)
    print(f"  canvas: {CANVAS_SIZE}×{CANVAS_SIZE}, range x=[{coords[:,0].min():.0f}, {coords[:,0].max():.0f}], "
          f"y=[{coords[:,1].min():.0f}, {coords[:,1].max():.0f}]")

    # Step 3: Build tiles & spatial index
    print("\n[3/5] Building tile layout...")
    tiles = build_tiles(pick_uuids, coords, orientations)
    spatial = SpatialHash(tiles)
    print(f"  {len(tiles)} tiles, {len(spatial.grid)} spatial cells")

    # Step 4: Compute waypoints
    print("\n[4/5] Computing camera waypoints...")
    centers, dive_targets = compute_cluster_waypoints(tiles)
    print(f"  {len(centers)} cluster centers, {len(dive_targets)} dive targets")

    # Step 5: Render
    print("\n[5/5] Rendering video(s)...")
    styles = ["breathing", "drift", "dives"] if args.all_styles else [args.style]
    outputs = []
    for style in styles:
        out = render_video(style, tiles, spatial, args.duration, args.res, centers, dive_targets)
        outputs.append(out)

    print(f"\n{'='*40}")
    print("Complete!")
    for p in outputs:
        print(f"  {p}")


if __name__ == "__main__":
    main()
