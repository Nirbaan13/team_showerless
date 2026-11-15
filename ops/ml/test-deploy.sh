#!/usr/bin/env bash
# Real Docker checks use a separate project, temporary env and disposable DB volume.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
export ML_DIR ML_PORT=127.0.0.1:18011 ML_COMPOSE_PROJECT="ml-ci-$$" DEPLOY_HEALTH_TIMEOUT=25
ML_DIR=$(mktemp -d)
compose=(docker compose --project-name "$ML_COMPOSE_PROJECT" --file "$ML_DIR/compose.yaml" --env-file "$ML_DIR/current.env")
cleanup() {
    if [[ -f "$ML_DIR/current.env" ]]; then "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true; fi
    rm -rf "$ML_DIR"
}
trap cleanup EXIT
revision=${TEST_IMAGE_REVISION:?Set TEST_IMAGE_REVISION to the built ML image SHA}
broken=cccccccccccccccccccccccccccccccccccccccc
if SSH_ORIGINAL_COMMAND='deploy-ml invalid; false' bash "$repo_root/ops/deploy-ml.sh" </dev/null; then
    echo 'Invalid ML release command accepted' >&2; exit 1
fi
deploy() {
    docker image save "spaceapps-ml:$1" | SSH_ORIGINAL_COMMAND="deploy-ml $1" bash "$repo_root/ops/deploy-ml.sh"
}
deploy "$revision"
"${compose[@]}" exec -T ml-inference python -c 'import os,sqlite3; c=sqlite3.connect(os.environ["PLANETX_DB_PATH"]); c.execute("CREATE TABLE deploy_sentinel(value TEXT)"); c.execute("INSERT INTO deploy_sentinel VALUES (?)",("persisted",)); c.commit()'
deploy "$revision"
assert_persisted() {
    "${compose[@]}" exec -T ml-inference python -c 'import os,sqlite3; c=sqlite3.connect(os.environ["PLANETX_DB_PATH"]); assert c.execute("SELECT value FROM deploy_sentinel").fetchone()[0]=="persisted"'
}
assert_persisted
docker build --quiet --tag "spaceapps-ml:$broken" - <<DOCKERFILE
FROM spaceapps-ml:$revision
ENV APP_REVISION=$broken
LABEL org.opencontainers.image.revision=$broken
CMD ["python", "-c", "raise SystemExit(42)"]
DOCKERFILE
if deploy "$broken"; then echo 'Broken ML deployment was accepted' >&2; exit 1; fi
"${compose[@]}" exec -T ml-inference python /app/smoke_deployment.py --base-url http://127.0.0.1:8001 --check-runtime
assert_persisted
grep -Fxq "ML_IMAGE=spaceapps-ml:$revision" "$ML_DIR/current.env"
echo 'ML deployment checks passed: health, image revision, persistence, failed-release rollback'
