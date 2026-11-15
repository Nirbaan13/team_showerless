#!/usr/bin/env bash
set -euo pipefail
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
build_dir=${DEMO_BUILD_ROOT:-/tmp/spaceapps-demo-build}
mkdir -p "$build_dir"
exec 9>"$build_dir/v1-build.lock"
flock 9
if [ ! -f "$build_dir/v1-bundle-ready" ]; then
    python3 "$repo_dir/ops/demo/build_variants.py" --inventory "$build_dir/source/inventory-source-validated.json" --output "$build_dir/inventory-service-v1.json" --engine podman
    python3 "$repo_dir/ops/demo/build_api_variant.py" --inventory "$build_dir/inventory-service-v1.json" --source "${DEMO_API_SOURCE:-/home/usatovpavel/.codex/worktrees/spaceapps-mirror-operational}" --revision 455adc578c0631c7d341439e7050e2e61793905a --output "$build_dir/inventory-v1.json" --engine podman
    python3 "$repo_dir/ops/demo/export_overlays.py" --inventory "$build_dir/inventory-v1.json" --output "$build_dir/overlay-images-normalized.tar.gz"
    python3 "$repo_dir/ops/demo/bundle.py" build --inventory "$build_dir/inventory-v1.json" --images "$build_dir/source/images-source.tar.gz" --overlay-images "$build_dir/overlay-images-normalized.tar.gz" --seed-data "$build_dir/seed-v1" --output "$build_dir/spaceapps-demo-v1.tar.gz"
    touch "$build_dir/v1-bundle-ready"
fi
python3 "$repo_dir/ops/demo/bundle.py" install --bundle "$build_dir/spaceapps-demo-v1.tar.gz" --engine podman --project spaceapps-demo-v1 --port "${DEMO_PORT:-18080}" "$@"
