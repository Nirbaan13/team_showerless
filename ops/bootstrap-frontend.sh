#!/usr/bin/env bash
# Install the independent frontend deployment entry point on the existing VPS.
set -euo pipefail
if [[ $EUID -ne 0 || $# -ne 1 ]]; then
    echo 'Usage: sudo bash ops/bootstrap-frontend.sh /path/to/frontend-ci-key.pub' >&2
    exit 64
fi
public_key=$(cat "$1")
if [[ ! $public_key =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ .*)?$ ]]; then
    echo 'Expected an OpenSSH Ed25519 public key' >&2
    exit 64
fi
docker compose version >/dev/null
repo_root=$(cd "$(dirname "$0")/.." && pwd)
if ! id frontend-deploy >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash frontend-deploy
fi
usermod -aG docker frontend-deploy
install -d -o frontend-deploy -g frontend-deploy -m 0750 /opt/spaceapps-frontend
install -o root -g root -m 0755 "$repo_root/ops/deploy-frontend.sh" /usr/local/bin/spaceapps-deploy-frontend
install -o root -g root -m 0644 "$repo_root/ops/frontend/compose.yaml" /opt/spaceapps-frontend/compose.yaml
install -d -o frontend-deploy -g frontend-deploy -m 0700 /home/frontend-deploy/.ssh
printf 'restrict,command="/usr/local/bin/spaceapps-deploy-frontend" %s\n' "$public_key" > /home/frontend-deploy/.ssh/authorized_keys
chown frontend-deploy:frontend-deploy /home/frontend-deploy/.ssh/authorized_keys
chmod 0600 /home/frontend-deploy/.ssh/authorized_keys
echo 'Frontend bootstrap ready: /opt/spaceapps-frontend, TCP 8080.'
