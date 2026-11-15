# Resource policy for the 1 GiB migration target

From the repository checkout on the new host, after API/ML/frontend bootstrap and a Compose plugin with `!reset` support are installed:

```sh
sudo bash ops/lowmemory/install.sh
```

The installer validates both merged Compose configurations before writing anything. It installs all three deployment handlers, the image retention helper, deploy-owned `host.override.yaml` files in `/opt/spaceapps` and `/opt/spaceapps-ml`, and disk-backed scratch directories. Scratch directory ownership is UID/GID 10001 with mode 0700, matching the images' unprivileged application user. Parent API/ML application directories remain owned by `deploy` with mode 0750. It does not start or restart containers.

This target policy assumes the current release schema with both API and pipeline services. Install it after migrating the target's current topology; it is not a compatibility layer for legacy API-only Compose files.

The installer also creates `/var/lock/spaceapps-release.lock` as root:docker mode 0660 if absent. Release handlers acquire that optional shared lock before their local application lock, preventing simultaneous image loads and release startups on the small host. Existing lock files are left untouched. `RELEASE_LOCK_FILE` can select a separate path for isolated checks.

Each release handler adds its host override after the Compose file extracted from the release image. The same file also applies to rollback, health checks, logs and first-release cleanup. Release success replaces `compose.yaml` and `current.env` while leaving `host.override.yaml` in place. Without that file, the release handler retains its existing behavior. Host configuration is passed to Compose as data and is never sourced as shell code.

The installer enables target-only post-success image retention with `prune-images.enabled` in each API, ML and frontend application directory. Each healthy release keeps its current SHA tag and one distinct previous SHA tag in the same repository. `previous.env` records that prior reference so rerunning the current SHA preserves the rollback release. The helper accepts only the three application repositories and lowercase 40-character SHA tags, skips running image IDs, and removes stale tags without force. Unrelated repositories, non-SHA tags and volumes are untouched; Docker refusals produce warnings without failing a healthy release. The API also removes its completed regular `incoming-image.tar` upload after health succeeds, while preserving symlinks. Cleanup runs before the release locks are released. Without the marker, existing release behavior remains unchanged. `IMAGE_PRUNE_HELPER` can select an isolated helper for checks.

The API limit is 448 MiB RAM / 768 MiB combined RAM and swap, pipeline 512 MiB / 1024 MiB, and ML 384 MiB / 768 MiB. These caps overlap intentionally and rely on host swap; they do not promise all maximum request shapes fit concurrently. The API JVM uses a 160 MiB heap, Serial GC and one effective processor, with no metaspace cap. Target-specific worker and math thread settings serialize work. Autonomous mirror scanning is disabled while the migrated index remains available; the index limit controls future growth rather than shrinking the existing database.

The `/tmp` mounts use disk rather than tmpfs. Persistent named data volumes and the pipeline's nested `/tmp/spherex_cutouts` mount are retained. Images, routing, accepted science input sizes, and security settings remain supplied by the release.

Validate locally without contacting a Docker daemon:

```sh
bash ops/test-host-overrides.sh
bash ops/lowmemory/test-config.sh
bash ops/lowmemory/test-prune-images.sh
```

Apply these example files only to the constrained target. The previous host remains the migration rollback target and does not need this policy.
