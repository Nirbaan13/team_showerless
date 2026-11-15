#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$SCRIPT_DIR/manifest.json" ]; then
    exec python3 "$SCRIPT_DIR/bundle.py" install --directory "$SCRIPT_DIR" "$@"
fi
exec python3 "$SCRIPT_DIR/bundle.py" install --bundle "${DEMO_BUNDLE:-$SCRIPT_DIR/bundle.tar.gz}" "$@"
