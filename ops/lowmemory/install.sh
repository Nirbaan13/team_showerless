#!/usr/bin/env bash
# Run on the constrained target after API, ML and frontend bootstrap.
# Installs policy and handlers only; does not start, stop or update containers.
set -euo pipefail
if [[ $EUID -ne 0 || $# -ne 0 ]] || ! id deploy >/dev/null 2>&1 || ! id frontend-deploy >/dev/null 2>&1; then
    echo 'Usage: sudo bash ops/lowmemory/install.sh (after API/ML/frontend bootstrap)' >&2
    exit 64
fi
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
# Validate merging before any host mutation, including !reset support. This does
# not contact the daemon. An older plugin must be upgraded by host provisioning.
APP_IMAGE=spaceapps-api:host-policy-check docker compose \
    --file "$repo_root/compose.yaml" --file "$repo_root/ops/lowmemory/api.override.yaml" config --quiet
ML_IMAGE=spaceapps-ml:host-policy-check docker compose \
    --file "$repo_root/ops/ml/compose.yaml" --file "$repo_root/ops/lowmemory/ml.override.yaml" config --quiet

if [[ ! -e /var/lock/spaceapps-release.lock ]]; then
    install -o root -g docker -m 0660 /dev/null /var/lock/spaceapps-release.lock
fi
install -d -o deploy -g deploy -m 0750 /opt/spaceapps /opt/spaceapps-ml /opt/spaceapps/runtime-tmp
# Only the image's unprivileged UID10001 needs access to each scratch directory.
install -d -o 10001 -g 10001 -m 0700 \
    /opt/spaceapps/runtime-tmp/api /opt/spaceapps/runtime-tmp/pipeline /opt/spaceapps-ml/runtime-tmp
install -o deploy -g deploy -m 0640 "$repo_root/ops/lowmemory/api.override.yaml" /opt/spaceapps/host.override.yaml
install -o deploy -g deploy -m 0640 "$repo_root/ops/lowmemory/ml.override.yaml" /opt/spaceapps-ml/host.override.yaml
install -o root -g root -m 0755 "$repo_root/ops/deploy.sh" /usr/local/bin/spaceapps-deploy
install -o root -g root -m 0755 "$repo_root/ops/deploy-ml.sh" /usr/local/bin/spaceapps-deploy-ml
install -o root -g root -m 0755 "$repo_root/ops/deploy-frontend.sh" /usr/local/bin/spaceapps-deploy-frontend
install -o root -g root -m 0755 "$repo_root/ops/lowmemory/prune-images.sh" /usr/local/bin/spaceapps-prune-images
install -o deploy -g deploy -m 0640 /dev/null /opt/spaceapps/prune-images.enabled
install -o deploy -g deploy -m 0640 /dev/null /opt/spaceapps-ml/prune-images.enabled
install -o frontend-deploy -g frontend-deploy -m 0640 /dev/null /opt/spaceapps-frontend/prune-images.enabled
printf 'Low-memory host policy installed; it applies on the next release or explicit Compose update.\n'
