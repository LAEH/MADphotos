#!/bin/bash
set -e

# MADphotos — Push local state to GCS so another machine can pull it.
#
# What it uploads:
#   1. images/mad_photos.db                         — SQLite, ~3.2 GB
#   2. frontend/show/public/data/*                  — generated JSON + mosaic mp4s
#   3. images/vectors.lance/                        — LanceDB vector store (~165 MB)
#   4. backend/suggest_image_variant/output/        — Imagen/neural-style variants (irreplaceable)
#   5. images/rendered/                             — 6-tier pyramids (~59 GB)
#
# What it does NOT upload (recreate on the new machine instead):
#   - .venv-gen / .venv-mflux   → `python3 -m venv` + `pip install -r requirements-gen.lock.txt`
#   - Ollama models              → `ollama create madphotos-critic -f backend/Modelfile.madphotos`
#   - HuggingFace cache          → re-downloads on first use
#
# Flags:
#   --skip-rendered    Skip the 59 GB rendered/ upload (everything else still syncs).
#   --only-rendered    ONLY sync rendered/ (useful to resume a big upload).
#
# Safe: uses rsync (only uploads changed files, never deletes remote).

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
GCS_BASE="gs://myproject-public-assets/madphotos/sync"

DB_PATH="$PROJECT_ROOT/images/mad_photos.db"
DATA_DIR="$PROJECT_ROOT/frontend/show/public/data"
VECTORS_DIR="$PROJECT_ROOT/images/vectors.lance"
VARIANTS_DIR="$PROJECT_ROOT/backend/suggest_image_variant/output"
RENDERED_DIR="$PROJECT_ROOT/images/rendered"

SKIP_RENDERED=0
ONLY_RENDERED=0
for arg in "$@"; do
    case "$arg" in
        --skip-rendered) SKIP_RENDERED=1 ;;
        --only-rendered) ONLY_RENDERED=1 ;;
    esac
done

echo "=== MADphotos sync-up ==="
echo "Target: $GCS_BASE"
echo ""

if [ "$ONLY_RENDERED" -eq 0 ]; then

    # 1. Upload DB (checkpoint WAL first for consistency)
    if [ -f "$DB_PATH" ]; then
        echo "[1/5] Uploading database..."
        sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(TRUNCATE);" 2>/dev/null || true
        db_size=$(du -sh "$DB_PATH" | awk '{print $1}')
        echo "  mad_photos.db ($db_size)"
        gcloud storage cp "$DB_PATH" "$GCS_BASE/mad_photos.db"
        echo "  done"
    else
        echo "[1/5] SKIP — no database found at $DB_PATH"
    fi
    echo ""

    # 2. Upload generated JSON data files
    if [ -d "$DATA_DIR" ]; then
        echo "[2/5] Uploading data files..."
        file_count=$(find "$DATA_DIR" -type f | wc -l | tr -d ' ')
        data_size=$(du -sh "$DATA_DIR" | awk '{print $1}')
        echo "  $file_count files ($data_size)"
        gcloud storage rsync "$DATA_DIR" "$GCS_BASE/data/" --recursive --checksums-only
        echo "  done"
    else
        echo "[2/5] SKIP — no data directory at $DATA_DIR"
    fi
    echo ""

    # 3. Upload LanceDB vector store
    if [ -d "$VECTORS_DIR" ]; then
        echo "[3/5] Uploading vectors.lance..."
        v_size=$(du -sh "$VECTORS_DIR" | awk '{print $1}')
        echo "  vectors.lance ($v_size)"
        gcloud storage rsync "$VECTORS_DIR" "$GCS_BASE/vectors.lance/" --recursive --checksums-only
        echo "  done"
    else
        echo "[3/5] SKIP — no vectors.lance at $VECTORS_DIR"
    fi
    echo ""

    # 4. Upload AI variant outputs (irreplaceable — Imagen API calls)
    if [ -d "$VARIANTS_DIR" ]; then
        echo "[4/5] Uploading variant outputs..."
        var_size=$(du -sh "$VARIANTS_DIR" | awk '{print $1}')
        var_count=$(find "$VARIANTS_DIR" -type f | wc -l | tr -d ' ')
        echo "  $var_count files ($var_size)"
        gcloud storage rsync "$VARIANTS_DIR" "$GCS_BASE/variants/" --recursive --checksums-only
        echo "  done"
    else
        echo "[4/5] SKIP — no variant output dir at $VARIANTS_DIR"
    fi
    echo ""

fi

# 5. Upload rendered tier pyramids (big — 59 GB)
if [ "$SKIP_RENDERED" -eq 1 ]; then
    echo "[5/5] SKIP — --skip-rendered flag set"
elif [ -d "$RENDERED_DIR" ]; then
    echo "[5/5] Uploading rendered/ (this is ~59 GB, go get coffee)..."
    r_size=$(du -sh "$RENDERED_DIR" | awk '{print $1}')
    r_count=$(find "$RENDERED_DIR" -type f | wc -l | tr -d ' ')
    echo "  $r_count files ($r_size)"
    gcloud storage rsync "$RENDERED_DIR" "$GCS_BASE/rendered/" --recursive --checksums-only
    echo "  done"
else
    echo "[5/5] SKIP — no rendered dir at $RENDERED_DIR"
fi

echo ""
echo "=== Sync-up complete ==="
echo "GCS location: $GCS_BASE/"
