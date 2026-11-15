#!/usr/bin/env bash
# Malformed host configuration must fail before Docker or shell evaluation.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/.." && pwd)
task_dir=$(mktemp -d)
trap 'rm -rf "$task_dir"' EXIT
mkdir -p "$task_dir/bin" "$task_dir/app"
cat >"$task_dir/bin/docker" <<'DOCKER'
#!/usr/bin/env bash
printf called >"$BINDING_DOCKER_SENTINEL"
exit 78
DOCKER
chmod +x "$task_dir/bin/docker"
export BINDING_DOCKER_SENTINEL="$task_dir/docker-called"
export PATH="$task_dir/bin:$PATH"
export APP_DIR="$task_dir/app"
export SSH_ORIGINAL_COMMAND='deploy aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
values=('' 'APP_PORT=0' 'APP_PORT=65536' 'APP_PORT=-1' 'APP_PORT=080' 'APP_PORT=127.0.0.2:18000' 'APP_PORT=18000;false' 'APP_PORT=$(false)' $'APP_PORT=18000\nAPP_PORT=18001')
for value in "${values[@]}"; do
    printf '%s\n' "$value" >"$APP_DIR/listen.env"
    status=0
    bash "$repo_root/ops/deploy.sh" </dev/null >"$task_dir/output" 2>&1 || status=$?
    test "$status" = 64
    test ! -e "$BINDING_DOCKER_SENTINEL"
    grep -q 'listen.env must contain one valid APP_PORT setting' "$task_dir/output"
done
printf 'Host binding rejection checks passed (%s malformed configurations)\n' "${#values[@]}"
