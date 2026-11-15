#!/usr/bin/env bash
# Release the independently owned ML HTTP service without touching the API stack.
set -euo pipefail
umask 077
if [[ ! ${SSH_ORIGINAL_COMMAND:-} =~ ^deploy-ml\ ([0-9a-f]{40})$ ]]; then
    echo 'Expected: deploy-ml <40-character lowercase Git commit SHA>' >&2
    exit 64
fi
revision=${BASH_REMATCH[1]}
image="spaceapps-ml:$revision"
app_dir=${ML_DIR:-/opt/spaceapps-ml}
project=${ML_COMPOSE_PROJECT:-spaceapps-ml}
timeout=${DEPLOY_HEALTH_TIMEOUT:-90}
port=${ML_PORT:-8001}
if [[ ! $port =~ ^(127\.0\.0\.1:)?([1-9][0-9]{0,4})$ ]] || ((10#${BASH_REMATCH[2]:-0}>65535)); then
    echo 'ML_PORT must be a valid port, optionally bound to loopback' >&2
    exit 64
fi
exec 9>"$app_dir/deploy.lock"
flock -w 600 9
previous_image=
previous_id=
if [[ -f "$app_dir/current.env" ]]; then
    previous_image=$(sed -n 's/^ML_IMAGE=//p' "$app_dir/current.env")
    previous_id=$(docker image inspect --format '{{.Id}}' "$previous_image")
fi
restore_tag() {
    if [[ -n $previous_id ]]; then docker image tag "$previous_id" "$previous_image"; fi
}
if ! docker image load; then restore_tag; exit 1; fi
label=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")
if [[ $label != "$revision" ]]; then
    restore_tag
    echo 'ML image revision does not match requested commit' >&2
    exit 65
fi
candidate=$(mktemp "$app_dir/candidate.XXXXXX.env")
candidate_compose=$(mktemp "$app_dir/candidate.XXXXXX.compose.yaml")
config_container=
deployed=false
cleanup() {
    if [[ $deployed != true ]]; then restore_tag; fi
    rm -f "$candidate" "$candidate_compose"
    if [[ -n $config_container ]]; then docker container rm --volumes "$config_container" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT
printf 'ML_IMAGE=%s\nML_PORT=%s\n' "$image" "$port" >"$candidate"
config_container=$(docker create --entrypoint /bin/true "$image")
docker cp "$config_container:/app/deploy/compose.yaml" "$candidate_compose"
docker container rm --volumes "$config_container" >/dev/null
config_container=
compose=(docker compose --project-name "$project" --file "$candidate_compose" --env-file "$candidate")
previous=(docker compose --project-name "$project" --file "$app_dir/compose.yaml" --env-file "$app_dir/current.env")
"${compose[@]}" config --quiet
if ! "${compose[@]}" up --detach --wait --remove-orphans --wait-timeout "$timeout" ||
    ! "${compose[@]}" exec -T ml-inference python /app/smoke_deployment.py --base-url http://127.0.0.1:8001; then
    "${compose[@]}" logs --tail 40 >&2 || true
    restore_tag
    if [[ -f "$app_dir/current.env" ]]; then
        echo 'ML release failed; restoring previous image and topology' >&2
        "${previous[@]}" up --detach --wait --remove-orphans --wait-timeout "$timeout"
    else
        "${compose[@]}" down --remove-orphans
    fi
    exit 1
fi
container=$("${compose[@]}" ps --quiet ml-inference)
actual=$(docker inspect --format '{{.Image}}' "$container")
expected=$(docker image inspect --format '{{.Id}}' "$image")
if [[ $actual != "$expected" ]]; then
    echo 'Running ML image does not match the requested image' >&2
    restore_tag
    if [[ -f "$app_dir/current.env" ]]; then "${previous[@]}" up --detach --wait --remove-orphans --wait-timeout "$timeout"; else "${compose[@]}" down --remove-orphans; fi
    exit 1
fi
docker image tag "$image" spaceapps-ml:latest
mv "$candidate_compose" "$app_dir/compose.yaml"
mv "$candidate" "$app_dir/current.env"
deployed=true
printf 'Deployed ML %s; spaceapps-ml:latest points to this healthy revision\n' "$revision"
