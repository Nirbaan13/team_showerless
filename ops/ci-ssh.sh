#!/usr/bin/env bash
# Restricted SSH entry point for image delta uploads and deployments.
set -euo pipefail
umask 077

app_dir=${APP_DIR:-/opt/spaceapps}
archive="$app_dir/incoming-image.tar"
command=${SSH_ORIGINAL_COMMAND:-}
reject() {
    echo "Unsupported CI SSH command or image archive" >&2
    exit 64
}

[[ $command != *$'\n'* && $command != *$'\r'* ]] || reject

# A separate Compose project keeps backend --remove-orphans away from ML.
if [[ $command =~ ^deploy-ml\ ([0-9a-f]{40})$ ]]; then
    exec /usr/local/bin/spaceapps-deploy-ml
fi

# Keep supporting direct docker-save streams for manual recovery.
if [[ $command =~ ^deploy\ ([0-9a-f]{40})$ ]]; then
    exec /usr/local/bin/spaceapps-deploy
fi

if [[ $command =~ ^deploy-cached\ ([0-9a-f]{40})$ ]]; then
    revision=${BASH_REMATCH[1]}
    [[ ! -L $archive && -f $archive && -s $archive ]] || reject
    export SSH_ORIGINAL_COMMAND="deploy $revision"
    exec /usr/local/bin/spaceapps-deploy <"$archive"
fi

# Parse words without invoking a shell: only our rsync receiver invocation is
# allowed. rsync's compact flags encode checksum/compression and protocol
# features; neither arbitrary options nor a sender invocation are accepted.
read -r -a args <<<"$command"
stats=()
if [[ ${#args[@]} -eq 7 && ${args[3]} == --stats ]]; then
    stats=(--stats)
    args=("${args[@]:0:3}" "${args[@]:4}")
fi
[[ ${#args[@]} -eq 6 ]] || reject
[[ ${args[0]} == sync-image && ${args[1]} == --server ]] || reject
[[ ${args[2]} =~ ^-[cz]*e\.[LsfxCIvu]+$ ]] || reject
[[ ${args[3]} == --inplace && ${args[4]} == . && ${args[5]} == "$archive" ]] || reject
[[ ! -L $archive && ( ! -e $archive || -f $archive ) ]] || reject

# Share the deployer's lock so an upload cannot alter an image during load.
exec 9>"$app_dir/deploy.lock"
flock -w 600 9
[[ ! -L $archive && ( ! -e $archive || -f $archive ) ]] || reject
exec /usr/bin/rsync --server "${args[2]}" "${stats[@]}" --inplace . "$archive"
