#!/usr/bin/env bash
# Run as root on Ubuntu 24.04: bash ops/bootstrap-vps.sh /path/to/ci-key.pub
set -euo pipefail
if [[ $EUID -ne 0 || $# -ne 1 ]]; then
    echo "Usage: sudo bash ops/bootstrap-vps.sh /path/to/ci-key.pub" >&2
    exit 64
fi
public_key=$(cat "$1")
if [[ ! $public_key =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ .*)?$ ]]; then
    echo "Expected an OpenSSH Ed25519 public key" >&2
    exit 64
fi
repo_root=$(cd "$(dirname "$0")/.." && pwd)
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2
fi
systemctl enable --now docker
if ! id deploy >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash deploy
fi
usermod -aG docker deploy
install -d -o deploy -g deploy -m 0750 /opt/spaceapps
install -o root -g root -m 0755 "$repo_root/ops/deploy.sh" /usr/local/bin/spaceapps-deploy
install -o root -g root -m 0644 "$repo_root/compose.yaml" /opt/spaceapps/compose.yaml
install -d -o deploy -g deploy -m 0700 /home/deploy/.ssh
printf 'restrict,command="/usr/local/bin/spaceapps-deploy" %s\n' "$public_key" \
    >/home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 0600 /home/deploy/.ssh/authorized_keys
echo "VPS bootstrap ready; deployment directory: /opt/spaceapps"
