#!/usr/bin/env bash
# Install the ML release handler alongside the existing restricted backend key.
set -euo pipefail
if [[ $EUID != 0 ]] || ! id deploy >/dev/null 2>&1; then
    echo 'Run as root after ops/bootstrap-vps.sh has created deploy' >&2
    exit 64
fi
repo_root=$(cd "$(dirname "$0")/.." && pwd)
install -d -o deploy -g deploy -m 0750 /opt/spaceapps-ml
install -o root -g root -m 0755 "$repo_root/ops/deploy-ml.sh" /usr/local/bin/spaceapps-deploy-ml
install -o root -g root -m 0755 "$repo_root/ops/ci-ssh.sh" /usr/local/bin/spaceapps-ci-ssh
echo 'ML release handler installed; existing CI key accepts deploy-ml <SHA>'
