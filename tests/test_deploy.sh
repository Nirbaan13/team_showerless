#!/usr/bin/env bash
# Run against a real Docker daemon; no production resources are used.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/.." && pwd)
export APP_DIR
APP_DIR=$(mktemp -d)
export APP_PORT=18080 COMPOSE_PROJECT_NAME="spaceapps-ci-$$" DEPLOY_HEALTH_TIMEOUT=15
cp "$repo_root/compose.yaml" "$APP_DIR/compose.yaml"
cleanup() {
    if [[ -f "$APP_DIR/current.env" ]]; then
        docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$APP_DIR/compose.yaml" \
            --env-file "$APP_DIR/current.env" down --remove-orphans >/dev/null 2>&1 || true
    fi
    rm -rf "$APP_DIR"
}
trap cleanup EXIT

first=${TEST_IMAGE_REVISION:-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}
second=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
broken=cccccccccccccccccccccccccccccccccccccccc
deploy() {
    docker image save "spaceapps-api:$1" | SSH_ORIGINAL_COMMAND="deploy $1" bash "$repo_root/ops/deploy.sh"
}
assert_version() {
    python3 - "$1" <<'PY'
import json
import sys
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:18080/version", timeout=5) as response:
    assert json.load(response)["version"] == sys.argv[1]
PY
}

if SSH_ORIGINAL_COMMAND='deploy invalid; touch /tmp/should-not-exist' \
    bash "$repo_root/ops/deploy.sh" </dev/null; then
    echo "ERROR: invalid deployment command was accepted" >&2
    exit 1
fi

deploy "$first"
assert_version "$first"

docker build --build-arg "BASE_IMAGE=spaceapps-api:$first" --build-arg "REVISION=$second" \
    --tag "spaceapps-api:$second" - <<'DOCKER'
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG REVISION
ENV APP_REVISION=${REVISION}
LABEL org.opencontainers.image.revision=${REVISION}
DOCKER
deploy "$second"
assert_version "$second"
test "$(docker image inspect --format '{{.Id}}' spaceapps-api:latest)" = \
    "$(docker image inspect --format '{{.Id}}' "spaceapps-api:$second")"

docker build --build-arg "BASE_IMAGE=spaceapps-api:$first" --build-arg "REVISION=$broken" \
    --tag "spaceapps-api:$broken" - <<'DOCKER'
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG REVISION
ENV APP_REVISION=${REVISION}
LABEL org.opencontainers.image.revision=${REVISION}
CMD ["python", "-c", "raise SystemExit(1)"]
DOCKER
if deploy "$broken"; then
    echo "ERROR: unhealthy deployment was accepted" >&2
    exit 1
fi
assert_version "$second"
grep -qx "APP_IMAGE=spaceapps-api:$second" "$APP_DIR/current.env"
test "$(docker image inspect --format '{{.Id}}' spaceapps-api:latest)" = \
    "$(docker image inspect --format '{{.Id}}' "spaceapps-api:$second")"

# A workflow rerun can rebuild the current SHA. Loading that image must not
# destroy the previous healthy image that rollback needs.
previous_id=$(docker image inspect --format '{{.Id}}' "spaceapps-api:$second")
docker build --build-arg "BASE_IMAGE=spaceapps-api:$first" --build-arg "REVISION=$second" \
    --tag "spaceapps-api:$second" - <<'DOCKER'
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG REVISION
ENV APP_REVISION=${REVISION}
LABEL org.opencontainers.image.revision=${REVISION}
CMD ["python", "-c", "raise SystemExit(1)"]
DOCKER
# Save the replacement, then restore the currently running tag before invoking
# the deployment, just as CI uploads a newly rebuilt image from another machine.
docker image save "spaceapps-api:$second" >"$APP_DIR/rebuilt.tar"
docker image tag "$previous_id" "spaceapps-api:$second"
if SSH_ORIGINAL_COMMAND="deploy $second" bash "$repo_root/ops/deploy.sh" <"$APP_DIR/rebuilt.tar"; then
    echo "ERROR: unhealthy rebuild of current SHA was accepted" >&2
    exit 1
fi
assert_version "$second"
test "$(docker image inspect --format '{{.Id}}' "spaceapps-api:$second")" = "$previous_id"
test "$(docker image inspect --format '{{.Id}}' spaceapps-api:latest)" = "$previous_id"
echo "Deployment integration tests passed: update, revision, latest, invalid command, rollback, same-SHA rollback."
