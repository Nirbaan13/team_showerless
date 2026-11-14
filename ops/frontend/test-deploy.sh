#!/usr/bin/env bash
# Integration checks use an isolated Compose project and a local high port.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
export FRONTEND_DIR FRONTEND_PORT=18081 FRONTEND_BIND_ADDRESS=127.0.0.1 COMPOSE_PROJECT_NAME="frontend-ci-$$" DEPLOY_HEALTH_TIMEOUT=10
FRONTEND_DIR=$(mktemp -d)
cp "$repo_root/ops/frontend/compose.yaml" "$FRONTEND_DIR/compose.yaml"
compose=(docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$FRONTEND_DIR/compose.yaml")
cleanup() {
    if [[ -f "$FRONTEND_DIR/current.env" ]]; then
        "${compose[@]}" --env-file "$FRONTEND_DIR/current.env" down --remove-orphans >/dev/null 2>&1 || true
    fi
    rm -rf "$FRONTEND_DIR"
}
trap cleanup EXIT
first=${TEST_IMAGE_REVISION:-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}
second=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
broken=cccccccccccccccccccccccccccccccccccccccc
deploy() {
    docker image save "spaceapps-frontend:$1" | SSH_ORIGINAL_COMMAND="deploy-frontend $1" bash "$repo_root/ops/deploy-frontend.sh"
}
assert_version() {
    python3 - "$1" <<'PY'
import json, re, sys, urllib.error, urllib.request
base = 'http://127.0.0.1:18081'
with urllib.request.urlopen(base + '/frontend-version.json', timeout=5) as response:
    assert json.load(response)['version'] == sys.argv[1]
with urllib.request.urlopen(base + '/', timeout=5) as response:
    html = response.read().decode()
    assert '<div id="root">' in html
asset = re.search(r'(?:src|href)="([^\"]+/assets/[^\"]+|\.?/assets/[^\"]+)"', html)
assert asset, html
with urllib.request.urlopen(base + '/' + asset[1].removeprefix('./').lstrip('/'), timeout=5) as response:
    assert response.status == 200
try:
    urllib.request.urlopen(base + '/assets/missing-file.js', timeout=5)
except urllib.error.HTTPError as error:
    assert error.code == 404
else:
    raise AssertionError('missing asset must not serve index.html')
PY
}
if SSH_ORIGINAL_COMMAND='deploy-frontend invalid; touch /tmp/not-allowed' bash "$repo_root/ops/deploy-frontend.sh" </dev/null; then
    echo 'ERROR: invalid SSH command accepted' >&2
    exit 1
fi
deploy "$first"
assert_version "$first"
docker build --build-arg "BASE_IMAGE=spaceapps-frontend:$first" --build-arg "REVISION=$second" --tag "spaceapps-frontend:$second" - <<'DOCKER'
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG REVISION
ENV FRONTEND_REVISION=${REVISION}
LABEL org.opencontainers.image.revision=${REVISION}
RUN printf '{"version":"%s"}\n' "$FRONTEND_REVISION" > /usr/share/nginx/html/frontend-version.json
DOCKER
deploy "$second"
assert_version "$second"
previous_id=$(docker image inspect --format '{{.Id}}' "spaceapps-frontend:$second")
for revision in "$broken" "$second"; do
    docker build --build-arg "BASE_IMAGE=spaceapps-frontend:$first" --build-arg "REVISION=$revision" --tag "spaceapps-frontend:$revision" - <<'DOCKER'
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG REVISION
LABEL org.opencontainers.image.revision=${REVISION}
CMD ["/bin/sh", "-c", "exit 1"]
DOCKER
    docker image save "spaceapps-frontend:$revision" > "$FRONTEND_DIR/broken.tar"
    docker image tag "$previous_id" "spaceapps-frontend:$second"
    if SSH_ORIGINAL_COMMAND="deploy-frontend $revision" bash "$repo_root/ops/deploy-frontend.sh" < "$FRONTEND_DIR/broken.tar"; then
        echo 'ERROR: unhealthy deployment accepted' >&2
        exit 1
    fi
    assert_version "$second"
    test "$(docker image inspect --format '{{.Id}}' "spaceapps-frontend:$second")" = "$previous_id"
    test "$(docker image inspect --format '{{.Id}}' spaceapps-frontend:latest)" = "$previous_id"
    grep -qx "FRONTEND_IMAGE=spaceapps-frontend:$second" "$FRONTEND_DIR/current.env"
done
echo 'Frontend deployment checks passed: HTML/assets, revision, invalid command, update, rollback and same-SHA rollback.'
