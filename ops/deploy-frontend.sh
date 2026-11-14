#!/usr/bin/env bash
# Fixed SSH entry point; stdin is a docker-save archive (optionally gzip).
set -euo pipefail
umask 077
if [[ ! ${SSH_ORIGINAL_COMMAND:-} =~ ^deploy-frontend\ ([0-9a-f]{40})$ ]]; then
    echo 'Expected: deploy-frontend <40-character lowercase Git commit SHA>' >&2
    exit 64
fi
revision=${BASH_REMATCH[1]}
image="spaceapps-frontend:$revision"
app_dir=${FRONTEND_DIR:-/opt/spaceapps-frontend}
project=${COMPOSE_PROJECT_NAME:-spaceapps-frontend}
timeout=${DEPLOY_HEALTH_TIMEOUT:-60}
exec 9>"$app_dir/deploy.lock"
flock -w 600 9
previous_image=
previous_id=
if [[ -f "$app_dir/current.env" ]]; then
    previous_image=$(sed -n 's/^FRONTEND_IMAGE=//p' "$app_dir/current.env")
    previous_id=$(docker image inspect --format '{{.Id}}' "$previous_image")
fi
restore_previous_tag() {
    if [[ -n "$previous_id" ]]; then
        docker image tag "$previous_id" "$previous_image"
    fi
}
if ! docker image load; then
    restore_previous_tag
    exit 1
fi
if ! label=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image") || [[ "$label" != "$revision" ]]; then
    restore_previous_tag
    echo 'Image revision does not match requested commit' >&2
    exit 65
fi
candidate=$(mktemp "$app_dir/candidate.XXXXXX.env")
trap 'rm -f "$candidate"' EXIT
printf 'FRONTEND_IMAGE=%s\n' "$image" > "$candidate"
compose=(docker compose --project-name "$project" --file "$app_dir/compose.yaml")
if ! "${compose[@]}" --env-file "$candidate" up --detach --wait --wait-timeout "$timeout"; then
    "${compose[@]}" --env-file "$candidate" logs --tail 50 >&2 || true
    if [[ -f "$app_dir/current.env" ]]; then
        echo 'Frontend deployment failed; restoring previous version' >&2
        restore_previous_tag
        "${compose[@]}" --env-file "$app_dir/current.env" up --detach --wait --wait-timeout "$timeout"
    else
        "${compose[@]}" --env-file "$candidate" down --remove-orphans
    fi
    exit 1
fi
docker image tag "$image" spaceapps-frontend:latest
mv "$candidate" "$app_dir/current.env"
printf 'Deployed frontend %s; latest now points to this revision\n' "$revision"
