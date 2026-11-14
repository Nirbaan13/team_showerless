#!/usr/bin/env bash
# Exercise the actual forced-command parser without Docker or a live VPS.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/.." && pwd)
export APP_DIR
APP_DIR=$(mktemp -d)
trap 'rm -rf "$APP_DIR"' EXIT
archive="$APP_DIR/incoming-image.tar"
sha=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

rejects() {
    local status=0
    SSH_ORIGINAL_COMMAND="$1" bash "$repo_root/ops/ci-ssh.sh" </dev/null >"$APP_DIR/output" 2>&1 || status=$?
    if [[ $status != 64 ]]; then
        printf 'Expected rejection (64), got %s: %q\n' "$status" "$1" >&2
        cat "$APP_DIR/output" >&2
        exit 1
    fi
}

rejects ''
rejects "deploy invalid; touch $APP_DIR/injected"
rejects "deploy-cached $sha; touch $APP_DIR/injected"
rejects $'deploy aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\ntrue'
rejects "sync-image --server -cze.LsfxCIvu --inplace . /tmp/elsewhere.tar"
rejects "sync-image --server -cze.LsfxCIvu --inplace . $archive extra"
rejects "sync-image --server -cze.LsfxCIvu --sender --inplace . $archive"
rejects "sync-image --server -cze.LsfxCIvu --stats --stats --inplace . $archive"
rejects "sync-image --server --sender --inplace . $archive"
rejects "sync-image --server -rcze.LsfxCIvu --inplace . $archive"
rejects "sync-image --server -cze.LsfxCIvu --inplace . $archive;true"
rejects "sync-image --server -cze.LsfxCIvu --inplace . $archive"$'\ntrue'
rejects "deploy-cached $sha"
touch "$archive"
rejects "deploy-cached $sha"
rm "$archive"
printf sentinel >"$APP_DIR/target"
ln -s "$APP_DIR/target" "$archive"
rejects "deploy-cached $sha"
rejects "sync-image --server -cze.LsfxCIvu --inplace . $archive"
[[ $(cat "$APP_DIR/target") == sentinel && ! -e $APP_DIR/injected ]]
rm "$archive"
mkdir "$archive"
rejects "deploy-cached $sha"
rejects "sync-image --server -cze.LsfxCIvu --inplace . $archive"
echo "CI SSH command rejection checks passed"
