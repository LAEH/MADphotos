#!/bin/bash
set -e

# MADphotos — Pull state from GCS on a fresh clone.
#
# What it downloads:
#   1. images/mad_photos.db                         — SQLite, ~3.2 GB
#   2. frontend/show/public/data/*                  — generated JSON + mosaic mp4s
#   3. images/vectors.lance/                        — LanceDB vector store (~165 MB)
#   4. backend/suggest_image_variant/output/        — Imagen/neural-style variants
#   5. images/rendered/                             — 6-tier pyramids (~59 GB)
#
# What you still need to do manually after sync-down:
#   - Create .venv-gen:  python3.13 -m venv .venv-gen && .venv-gen/bin/pip install -r requirements-gen.lock.txt
#   - (optional) Create .venv-mflux (Python 3.9): python3.9 -m venv .venv-mflux && .venv-mflux/bin/pip install -r requirements-mflux.lock.txt
#   - Install Ollama, pull gemma3:27b, then: ollama create madphotos-critic -f backend/Modelfile.madphotos
#   - gcloud auth login && gcloud config set project laeh380to760   (for Firebase deploy + GCS auth)
#
# Flags:
#   --skip-rendered    Don't download the 59 GB rendered/ (frontend build only)
#   --only-rendered    ONLY download rendered/
#   --force            Re-download files that appear identical in size
#
# Safe: never deletes local files (no --delete-unmatched-destination).

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
GCS_BASE="gs://myproject-public-assets/madphotos/sync"

DB_PATH="$PROJECT_ROOT/images/mad_photos.db"
DATA_DIR="$PROJECT_ROOT/frontend/show/public/data"
VECTORS_DIR="$PROJECT_ROOT/images/vectors.lance"
VARIANTS_DIR="$PROJECT_ROOT/backend/suggest_image_variant/output"
RENDERED_DIR="$PROJECT_ROOT/images/rendered"

SKIP_RENDERED=0
ONLY_RENDERED=0
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --skip-rendered) SKIP_RENDERED=1 ;;
        --only-rendered) ONLY_RENDERED=1 ;;
        --force) FORCE=1 ;;
    esac
done

echo "=== MADphotos sync-down ==="
echo "Source: $GCS_BASE"
echo ""

if [ "$ONLY_RENDERED" -eq 0 ]; then

    # 1. Download DB
    echo "[1/5] Downloading database..."
    mkdir -p "$(dirname "$DB_PATH")"
    if gcloud storage ls "$GCS_BASE/mad_photos.db" &>/dev/null; then
        skip_db=""
        if [ -f "$DB_PATH" ] && [ "$FORCE" -eq 0 ]; then
            local_size=$(stat -f%z "$DB_PATH" 2>/dev/null || stat -c%s "$DB_PATH" 2>/dev/null)
            remote_size=$(gcloud storage ls -l "$GCS_BASE/mad_photos.db" 2>/dev/null | head -1 | awk '{print $1}')
            echo "  Local:  $local_size bytes"
            echo "  Remote: $remote_size bytes"
            if [ "$local_size" = "$remote_size" ]; then
                echo "  Same size — skipping (use --force to re-download)"
                skip_db=1
            fi
        fi
        if [ -z "$skip_db" ]; then
            gcloud storage cp "$GCS_BASE/mad_photos.db" "$DB_PATH"
            echo "  done ($(du -sh "$DB_PATH" | awk '{print $1}'))"
        fi
    else
        echo "  SKIP — no database found on GCS"
    fi
    echo ""

    # 2. Download data files
    echo "[2/5] Downloading data files..."
    mkdir -p "$DATA_DIR"
    if gcloud storage ls "$GCS_BASE/data/" &>/dev/null; then
        gcloud storage rsync "$GCS_BASE/data/" "$DATA_DIR" --recursive --checksums-only
        file_count=$(find "$DATA_DIR" -type f | wc -l | tr -d ' ')
        echo "  done ($file_count files)"
    else
        echo "  SKIP — no data files found on GCS"
    fi
    echo ""

    # 3. Download LanceDB vectors
    echo "[3/5] Downloading vectors.lance..."
    mkdir -p "$VECTORS_DIR"
    if gcloud storage ls "$GCS_BASE/vectors.lance/" &>/dev/null; then
        gcloud storage rsync "$GCS_BASE/vectors.lance/" "$VECTORS_DIR" --recursive --checksums-only
        echo "  done ($(du -sh "$VECTORS_DIR" | awk '{print $1}'))"
    else
        echo "  SKIP — no vectors.lance found on GCS"
    fi
    echo ""

    # 4. Download variant outputs
    echo "[4/5] Downloading variant outputs..."
    mkdir -p "$VARIANTS_DIR"
    if gcloud storage ls "$GCS_BASE/variants/" &>/dev/null; then
        gcloud storage rsync "$GCS_BASE/variants/" "$VARIANTS_DIR" --recursive --checksums-only
        var_count=$(find "$VARIANTS_DIR" -type f | wc -l | tr -d ' ')
        echo "  done ($var_count files)"
    else
        echo "  SKIP — no variants found on GCS"
    fi
    echo ""

fi

# 5. Download rendered tier pyramids (big)
if [ "$SKIP_RENDERED" -eq 1 ]; then
    echo "[5/5] SKIP — --skip-rendered flag set"
    echo "      (You can build the Show/System frontend without this, but any pipeline step"
    echo "       that reads tier images will fail until you run: ./sync-down.sh --only-rendered)"
elif gcloud storage ls "$GCS_BASE/rendered/" &>/dev/null; then
    echo "[5/5] Downloading rendered/ (~59 GB, this will take a while)..."
    mkdir -p "$RENDERED_DIR"
    gcloud storage rsync "$GCS_BASE/rendered/" "$RENDERED_DIR" --recursive --checksums-only
    r_count=$(find "$RENDERED_DIR" -type f | wc -l | tr -d ' ')
    echo "  done ($r_count files, $(du -sh "$RENDERED_DIR" | awk '{print $1}'))"
else
    echo "[5/5] SKIP — no rendered/ found on GCS"
fi

echo ""
echo "=== Sync-down complete ==="
echo ""
echo "Next steps (if this is a fresh clone on a new machine):"
echo "  1. Python env:"
echo "     python3.13 -m venv .venv-gen"
echo "     .venv-gen/bin/pip install -r requirements-gen.lock.txt"
echo "  2. Ollama model:"
echo "     ollama pull gemma3:27b"
echo "     ollama create madphotos-critic -f backend/Modelfile.madphotos"
echo "  3. gcloud auth:"
echo "     gcloud auth login"
echo "     gcloud config set project laeh380to760"
echo "  4. Frontend build + deploy:"
echo "     npm install --prefix frontend/show"
echo "     cd frontend/show && npx vite build"
echo "     firebase deploy --only hosting:laeh-madphotos"
