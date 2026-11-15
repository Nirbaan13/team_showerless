#!/usr/bin/env bash
# Called only after a healthy release, while shared and application locks are held.
# Keep current plus one distinct previous release; never prune volumes or force rm.
set -euo pipefail
umask 077
reject() {
    echo 'Image retention requires an application directory and same-repository lowercase SHA release references' >&2
    exit 64
}
valid_ref() {
    [[ $1 =~ ^(spaceapps-api|spaceapps-ml|spaceapps-frontend):[0-9a-f]{40}$ ]]
}
[[ $# -eq 3 && -d $1 ]] || reject
app_dir=$1
current=$2
previous=$3
valid_ref "$current" || reject
repo=${current%:*}
if [[ $previous == "$current" ]]; then
    previous=
    # A rerun of the current SHA must not evict the distinct rollback release.
    if [[ -f "$app_dir/previous.env" ]]; then
        mapfile -t previous_lines <"$app_dir/previous.env"
        [[ ${#previous_lines[@]} -eq 1 && ${previous_lines[0]} == PREVIOUS_IMAGE=* ]] || reject
        previous=${previous_lines[0]#PREVIOUS_IMAGE=}
    fi
fi
if [[ -n $previous ]]; then
    valid_ref "$previous" && [[ ${previous%:*} == "$repo" ]] || reject
fi
if [[ $previous == "$current" ]]; then previous=; fi
if [[ -n $previous ]]; then
    marker=$(mktemp "$app_dir/previous.XXXXXX.env")
    trap 'rm -f "$marker"' EXIT
    printf 'PREVIOUS_IMAGE=%s\n' "$previous" >"$marker"
    mv "$marker" "$app_dir/previous.env"
else
    rm -f "$app_dir/previous.env"
fi

# Snapshot running image IDs before considering any removals. Query failures abort
# cleanup rather than treating unknown running state as permission to delete.
running=$(docker ps --quiet)
running_ids=
if [[ -n $running ]]; then
    mapfile -t containers <<<"$running"
    running_ids=$(docker inspect --format '{{.Image}}' "${containers[@]}")
fi
releases=$(docker image ls --format '{{.Repository}}:{{.Tag}}' "$repo")
while IFS= read -r ref; do
    valid_ref "$ref" || continue
    [[ ${ref%:*} == "$repo" && $ref != "$current" && $ref != "$previous" ]] || continue
    if ! id=$(docker image inspect --format '{{.Id}}' "$ref"); then
        echo "Warning: could not inspect retained image candidate $ref" >&2
        continue
    fi
    [[ -n $id ]] || continue
    if [[ $'\n'"$running_ids"$'\n' == *$'\n'"$id"$'\n'* ]]; then continue; fi
    if ! docker image rm "$ref"; then
        echo "Warning: leaving image $ref because Docker refused removal" >&2
    fi
done <<<"$releases"
