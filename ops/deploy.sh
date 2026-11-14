#!/usr/bin/env bash
# Fixed SSH entry point. stdin is a docker-save archive (optionally gzip).
set -euo pipefail
umask 077

if [[ ! ${SSH_ORIGINAL_COMMAND:-} =~ ^deploy\ ([0-9a-f]{40})$ ]]; then
    echo "Expected: deploy <40-character lowercase Git commit SHA>" >&2
    exit 64
fi
revision=${BASH_REMATCH[1]}
image="spaceapps-api:$revision"
app_dir=${APP_DIR:-/opt/spaceapps}
project=${COMPOSE_PROJECT_NAME:-spaceapps}
timeout=${DEPLOY_HEALTH_TIMEOUT:-60}

# Also serialize manual deployments with deployments started by GitHub Actions.
exec 9>"$app_dir/deploy.lock"
flock -w 600 9

previous_image=
previous_id=
if [[ -f "$app_dir/current.env" ]]; then
    previous_image=$(sed -n 's/^APP_IMAGE=//p' "$app_dir/current.env")
    previous_id=$(docker image inspect --format '{{.Id}}' "$previous_image")
fi
restore_previous_tag() {
    if [[ -n "$previous_id" ]]; then
        docker image tag "$previous_id" "$previous_image"
    fi
}

# A rerun can upload a different image under the currently deployed SHA tag.
# Capture the old immutable ID before loading so rollback can repair that tag.
if ! docker image load; then
    restore_previous_tag
    exit 1
fi
label=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")
if [[ "$label" != "$revision" ]]; then
    restore_previous_tag
    echo "Image revision does not match requested commit" >&2
    exit 65
fi

candidate=$(mktemp "$app_dir/candidate.XXXXXX.env")
trap 'rm -f "$candidate"' EXIT
printf 'APP_IMAGE=%s\n' "$image" >"$candidate"
compose=(docker compose --project-name "$project" --file "$app_dir/compose.yaml")

if ! "${compose[@]}" --env-file "$candidate" up --detach --wait --wait-timeout "$timeout"; then
    "${compose[@]}" --env-file "$candidate" logs --tail 50 >&2 || true
    if [[ -f "$app_dir/current.env" ]]; then
        echo "New deployment failed; restoring previous version" >&2
        restore_previous_tag
        "${compose[@]}" --env-file "$app_dir/current.env" up --detach --wait --wait-timeout "$timeout"
    else
        "${compose[@]}" --env-file "$candidate" down --remove-orphans
    fi
    exit 1
fi

# Publish latest only after this exact image is healthy. Keep the previous
# current.env until then so a failed deployment cannot become the baseline.
docker image tag "$image" spaceapps-api:latest
mv "$candidate" "$app_dir/current.env"
printf 'Deployed %s; spaceapps-api:latest now points to this revision\n' "$revision"
