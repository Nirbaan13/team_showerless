#!/usr/bin/env bash
# One-time, root-only migration. Install Caddy from its official package first.
set -euo pipefail
if [[ $EUID -ne 0 || $# -ne 0 ]]; then
    echo 'Usage: sudo bash ops/bootstrap-domain.sh' >&2
    exit 64
fi
repo_root=$(cd "$(dirname "$0")/.." && pwd)
app_dir=/opt/spaceapps
command -v caddy >/dev/null
command -v docker >/dev/null
test -s "$app_dir/current.env"
test -s "$app_dir/compose.yaml"
caddy validate --config "$repo_root/ops/domain/Caddyfile" --adapter caddyfile
bash -n "$repo_root/ops/deploy.sh"
exec 9>"$app_dir/deploy.lock"
flock -w 600 9
backup=$(mktemp -d /opt/spaceapps-domain-backup.XXXXXX)
chmod 0700 "$backup"
cp -p "$app_dir/current.env" "$backup/current.env"
cp -p "$app_dir/compose.yaml" "$backup/compose.yaml"
cp -p /usr/local/bin/spaceapps-deploy "$backup/deploy"
[[ ! -e "$app_dir/listen.env" ]] || cp -p "$app_dir/listen.env" "$backup/listen.env"
[[ ! -e /etc/caddy/Caddyfile ]] || cp -p /etc/caddy/Caddyfile "$backup/Caddyfile"
was_active=false
if systemctl is-active --quiet caddy; then was_active=true; fi
was_enabled=false
if systemctl is-enabled --quiet caddy; then was_enabled=true; fi
enable_state=$(systemctl is-enabled caddy 2>/dev/null || true)
rollback() {
    local failure=$?
    trap - ERR
    set +e
    echo "Migration failed; restoring $backup" >&2
    systemctl stop caddy
    cp -p "$backup/current.env" "$app_dir/current.env"
    cp -p "$backup/compose.yaml" "$app_dir/compose.yaml"
    cp -p "$backup/deploy" /usr/local/bin/spaceapps-deploy
    if [[ -f "$backup/listen.env" ]]; then cp -p "$backup/listen.env" "$app_dir/listen.env"; else rm -f "$app_dir/listen.env"; fi
    if [[ -f "$backup/Caddyfile" ]]; then cp -p "$backup/Caddyfile" /etc/caddy/Caddyfile; fi
    docker compose --project-name spaceapps --file "$app_dir/compose.yaml" --env-file "$app_dir/current.env" up --detach --no-deps --wait --wait-timeout 90 api
    if [[ $was_active == true ]]; then systemctl start caddy; fi
    if [[ $was_enabled != true ]]; then systemctl disable caddy; fi
    case "$enable_state" in
        masked-runtime) systemctl mask --runtime caddy.service ;;
        masked) systemctl mask caddy.service ;;
    esac
    exit "$failure"
}
trap rollback ERR
install -o root -g root -m 0755 "$repo_root/ops/deploy.sh" /usr/local/bin/spaceapps-deploy
printf 'APP_PORT=127.0.0.1:18000\n' >"$app_dir/listen.env"
chown root:root "$app_dir/listen.env"
chmod 0644 "$app_dir/listen.env"
candidate=$(mktemp "$app_dir/domain.XXXXXX.env")
sed '/^APP_PORT=/d' "$app_dir/current.env" >"$candidate"
printf 'APP_PORT=127.0.0.1:18000\n' >>"$candidate"
chown --reference="$app_dir/current.env" "$candidate"
chmod --reference="$app_dir/current.env" "$candidate"
mv "$candidate" "$app_dir/current.env"
docker compose --project-name spaceapps --file "$app_dir/compose.yaml" --env-file "$app_dir/current.env" up --detach --no-deps --wait --wait-timeout 90 api
curl --fail --silent --retry 10 --retry-all-errors --retry-delay 1 http://127.0.0.1:18000/health
install -o root -g root -m 0644 "$repo_root/ops/domain/Caddyfile" /etc/caddy/Caddyfile
systemctl unmask --runtime caddy.service
systemctl enable caddy.service
systemctl reload-or-restart caddy.service
curl --fail --silent --retry 10 --retry-all-errors --retry-delay 1 http://127.0.0.1/health
curl --fail --silent --retry 10 --retry-all-errors --retry-delay 1 http://127.0.0.1:8080/backend/health
trap - ERR
printf '\nDomain proxy installed; rollback backup: %s\n' "$backup"
printf 'Public certificates will be issued after domain A/AAAA records reach this VPS.\n'
