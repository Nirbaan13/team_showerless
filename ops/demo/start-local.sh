#!/usr/bin/env bash
set -euo pipefail
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
build_dir=${DEMO_BUILD_ROOT:-/tmp/spaceapps-demo-build}
if [ ! -f "$build_dir/compose.run.yaml" ]; then
    python3 "$repo_dir/ops/demo/prepare_local.py"
fi
exec podman compose -p spaceapps-demo-v1-preview -f "$build_dir/compose.run.yaml" up -d --wait --wait-timeout 180 "$@"
