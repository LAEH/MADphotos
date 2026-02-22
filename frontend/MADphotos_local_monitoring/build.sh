#!/bin/bash
# Build See and update the .app bundle
set -e
cd "$(dirname "$0")"
swift build 2>&1
cp .build/debug/See See.app/Contents/MacOS/See
echo "See.app updated"
