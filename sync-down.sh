#!/bin/bash
set -e

# MADphotos — Download DB + generated JSON data from GCS
# Run this on a fresh clone to get everything needed for build & deploy
# Safe: never deletes local files (no --delete-unmatched-destination)

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
GCS_BASE="gs://myproject-public-assets/madphotos/sync"

DB_PATH="$PROJECT_ROOT/images/mad_photos.db"
DATA_DIR="$PROJECT_ROOT/frontend/show/public/data"

echo "=== MADphotos sync-down ==="
echo ""

# 1. Download DB
echo "[1/2] Downloading database..."
mkdir -p "$(dirname "$DB_PATH")"
if gcloud storage ls "$GCS_BASE/mad_photos.db" &>/dev/null; then
    if [ -f "$DB_PATH" ]; then
        local_size=$(stat -f%z "$DB_PATH" 2>/dev/null || stat -c%s "$DB_PATH" 2>/dev/null)
        remote_size=$(gcloud storage ls -l "$GCS_BASE/mad_photos.db" 2>/dev/null | head -1 | awk '{print $1}')
        echo "  Local:  $local_size bytes"
        echo "  Remote: $remote_size bytes"
        if [ "$local_size" = "$remote_size" ]; then
            echo "  Same size — skipping (use --force to re-download)"
            if [ "$1" != "--force" ]; then
                skip_db=1
            fi
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
echo "[2/2] Downloading data files..."
mkdir -p "$DATA_DIR"
if gcloud storage ls "$GCS_BASE/data/" &>/dev/null; then
    gcloud storage rsync "$GCS_BASE/data/" "$DATA_DIR" --recursive --checksums-only
    file_count=$(find "$DATA_DIR" -type f | wc -l | tr -d ' ')
    echo "  done ($file_count files)"
else
    echo "  SKIP — no data files found on GCS"
fi

echo ""
echo "=== Sync complete ==="
echo ""
echo "Next steps:"
echo "  npm install --prefix frontend/show"
echo "  cd frontend/show && npx vite build"
echo "  firebase deploy --only hosting:laeh-madphotos"
