#!/bin/bash
set -e

# MADphotos — Upload DB + generated JSON data to GCS
# Run this after any significant changes (new picks, variants, analysis)
# Safe: uses rsync (only uploads changed files, never deletes remote)

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
GCS_BASE="gs://myproject-public-assets/madphotos/sync"

DB_PATH="$PROJECT_ROOT/images/mad_photos.db"
DATA_DIR="$PROJECT_ROOT/frontend/show/public/data"

echo "=== MADphotos sync-up ==="
echo ""

# 1. Upload DB (checkpoint WAL first for consistency)
if [ -f "$DB_PATH" ]; then
    echo "[1/2] Uploading database..."
    # Checkpoint WAL to ensure DB file has all data
    sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(TRUNCATE);" 2>/dev/null || true
    db_size=$(du -sh "$DB_PATH" | awk '{print $1}')
    echo "  mad_photos.db ($db_size)"
    gcloud storage cp "$DB_PATH" "$GCS_BASE/mad_photos.db"
    echo "  done"
else
    echo "[1/2] SKIP — no database found at $DB_PATH"
fi

echo ""

# 2. Upload generated JSON data files
if [ -d "$DATA_DIR" ]; then
    echo "[2/2] Uploading data files..."
    file_count=$(find "$DATA_DIR" -type f | wc -l | tr -d ' ')
    data_size=$(du -sh "$DATA_DIR" | awk '{print $1}')
    echo "  $file_count files ($data_size)"
    gcloud storage rsync "$DATA_DIR" "$GCS_BASE/data/" --recursive --checksums-only
    echo "  done"
else
    echo "[2/2] SKIP — no data directory at $DATA_DIR"
fi

echo ""
echo "=== Sync complete ==="
echo "GCS location: $GCS_BASE/"
