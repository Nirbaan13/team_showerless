# ML HTTP service deployment

The frontend's /api/motion/* and /api/catalogue/* routes target the existing
FastAPI ML service on host port8001. It was defined only in the development
compose.services.yaml; the production API and frontend release workflows never
started it. The missing container caused Nginx502 responses. The service also
imports Pillow without declaring it, and its catalogue database needs a separate
explicit persistent path.

The service now has an independent Compose project, spaceapps-ml, under
/opt/spaceapps-ml. Backend --remove-orphans cannot remove it. Its ml-data volume
contains both verifications.sqlite and planetx_catalogue.db; no volume deletion
occurs during release/rollback. The image runs as UID10001 with a read-only root
and temporary writable /tmp. Existing scientific and catalogue code is unchanged.

Install once as root: bash ops/bootstrap-ml.sh. It reuses the existing restricted
backend CI key, adding only the exact deploy-ml <40-hex SHA> operation. The release
handler loads a commit-tagged image, verifies its OCI revision, extracts its own
Compose snapshot, waits for HTTP/database health, runs read-only smoke checks,
and only then updates current.env and spaceapps-ml:latest. Failure restores the
previous immutable image and topology. Port8001 is published for the existing
frontend host.docker.internal proxy.

ML deploy (agents wait) builds and deploys every main revision independently from
test workflows. ML tests (agents do not wait) exercises the packaged service,
SQLite persistence and failed-release rollback in a disposable Compose project.
Neither tests nor their artifacts gate deployment.

The smoke checks health, benchmark, catalogue, discussions, PNG preview and real
synthetic track detection. They do not create public comments/candidates or send
external submissions. Local mode starts a temporary server with isolated SQLite.
Existing legacy tests have one independently confirmed pre-existing failure:
test_catalogue_pipeline.TestCataloguePipeline.test_02_kpi_counters expects an
external submission absent from the seeded database (9 pass, 1 fail). This
packaging/deployment fix does not change catalogue semantics to satisfy it.

Operations:

- docker compose --project-name spaceapps-ml --file /opt/spaceapps-ml/compose.yaml
  --env-file /opt/spaceapps-ml/current.env ps
- GET http://144.124.238.101:8001/health
- GET http://144.124.238.101:8080/api/motion/verifications
- GET http://144.124.238.101:8080/api/catalogue/candidates

Production release revision is verified through the immutable image label and
running container identity; the original /health application version is retained.
