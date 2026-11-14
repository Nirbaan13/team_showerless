# Frontend deployment

The frontend is served from the existing VPS at `http://35.159.162.202:8080/`.
The API and Swagger keep port 80. No additional hosting service is needed.

## Automatic delivery

`.github/workflows/frontend-deploy.yml` runs `npm ci`, lint, TypeScript/Vite build,
an nginx image build, and isolated container deployment/rollback tests for pull
requests and pushes to `main`. Only `main` deploys. Workflow dispatch on `main`
can redeploy the current revision. Images use `spaceapps-frontend:<commit SHA>`;
`spaceapps-frontend:latest` advances only after the container becomes healthy.
`/frontend-version.json` returns the deployed Git commit and disables caching.

The production build sets `VITE_BACKEND_URL=/backend`. nginx removes that prefix
before forwarding to the existing backend at host port 80. Direct `/api/` paths
also proxy to the backend because manifests return relative FITS, preview and
event URLs. Both proxy locations disable buffering and allow one hour between
response reads for SSE. HTML is revalidated and hashed assets have immutable
caching. An unknown asset returns 404 instead of the SPA HTML.

The SSH entry point validates `deploy-frontend <40 lowercase hex digits>`, loads
the image from stdin, verifies its revision label, and serializes deployments.
A failed health check restores the previous image. The previous immutable image
ID is retained during upload so a broken rebuild of the same SHA can also roll
back. Its Compose project, directory, deploy user and image tags are independent
of the backend.

## One-time VPS setup

Use the existing owner SSH key and a separate Ed25519 key for frontend CI. Keep
private key material out of source control and command output. Copy these files
to a temporary directory on the VPS, preserving their paths:

```text
ops/bootstrap-frontend.sh
ops/deploy-frontend.sh
ops/frontend/compose.yaml
```

Copy only the frontend CI public key to that directory, then run as the existing
Ubuntu owner:

```bash
sudo bash /path/to/staged-repo/ops/bootstrap-frontend.sh /path/to/frontend-ci-key.pub
```

This creates `frontend-deploy`, installs the restricted SSH entry point, and
installs `/opt/spaceapps-frontend/compose.yaml`. It relies on Docker/Compose
already installed for the backend. Permit inbound TCP 8080 on the instance's
existing AWS security group and any enabled host firewall. Existing backend
ingress and deployment configuration are unchanged.

GitHub Actions uses the existing `VPS_HOST` and `VPS_KNOWN_HOSTS` secrets. Add one
secret, `FRONTEND_VPS_SSH_KEY`, containing the separate frontend CI private key.
The username is fixed to `frontend-deploy`; do not replace `VPS_SSH_KEY` or
`VPS_USER`, which belong to the backend deployment.

```bash
gh secret set FRONTEND_VPS_SSH_KEY --repo Nirbaan13/team_showerless < /path/to/frontend-ci-private-key
```

## Manual verification and rollback

```bash
curl --fail http://35.159.162.202:8080/
curl --fail http://35.159.162.202:8080/frontend-version.json
curl --fail http://35.159.162.202:8080/backend/health
```

To deploy or roll back a previously built image, stream that image with the
frontend CI key, the existing pinned known-hosts file, and the desired commit:

```bash
docker image save "spaceapps-frontend:$revision" | gzip -1 |
  ssh -i /path/to/frontend-ci-private-key -o IdentitiesOnly=yes -o BatchMode=yes \
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/path/to/pinned-known-hosts \
    frontend-deploy@35.159.162.202 "deploy-frontend $revision"
```

The installed entry point also automatically rolls back a candidate that fails
its internal HTML/version health check. The workflow additionally verifies the
public revision, HTML, an asset, and the API proxy after deployment. If only the
external network check fails, diagnose networking before rolling back a healthy
container. Bootstrap changes must be installed by the owner separately; the CI
key only accepts image deployment commands.

## Local validation

```bash
cd frontend
npm ci --no-audit --no-fund
npm run lint
VITE_BACKEND_URL=/backend npm run build
cd ..
bash -n ops/deploy-frontend.sh ops/bootstrap-frontend.sh ops/frontend/test-deploy.sh
docker build --file ops/frontend/Dockerfile --build-arg "APP_REVISION=$revision" \
  --tag "spaceapps-frontend:$revision" .
TEST_IMAGE_REVISION="$revision" bash ops/frontend/test-deploy.sh
```

An existing rootless Podman installation can provide the Docker API when the
system Docker socket is unavailable:

```bash
podman system service --time=0 unix:///tmp/spaceapps-frontend-podman.sock
# In another terminal:
export DOCKER_HOST=unix:///tmp/spaceapps-frontend-podman.sock
podman build --format docker --file ops/frontend/Dockerfile \
  --build-arg "APP_REVISION=$revision" --tag "spaceapps-frontend:$revision" .
TEST_IMAGE_REVISION="$revision" bash ops/frontend/test-deploy.sh
```

Use Docker image format with Podman so the Dockerfile health check is retained.
The tests use local port 18081 and their own Compose project; production port
8080 is not touched. Existing frontend lint warnings are not deployment errors.

On this workstation, rootless Podman served and validated the initial container
but failed Compose replacement with `rootless netns: kill network process:
permission denied`. Use a real Docker daemon for the full suite if that host
limitation recurs. The full suite passed on the existing VPS Docker daemon in an
isolated temporary project on 2026-11-14, including both rollback scenarios.
Separate temporary-container checks confirmed `/backend/health` and direct
`/api/` forwarding. All temporary VPS containers, networks, images and files
were removed afterward; the production backend was untouched.

## Hosting evidence and scope

On 2026-11-14 the VPS had only the backend container on port 80 and no nginx or
frontend static directory. A historical GitHub Pages deployment had succeeded
earlier that day, but its public URL returned 404 and its `gh-pages` branch was
absent. This workflow establishes frontend delivery on the existing VPS.

The frontend application behavior is unchanged. Its backend client module is
currently not imported into the app, so deploying the frontend does not by
itself switch the existing demonstration UI to live API data.

References: [Vite static deployment](https://vite.dev/guide/static-deploy.html),
[GitHub Actions deployments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments),
[nginx try_files](https://nginx.org/en/docs/http/ngx_http_core_module.html#try_files).
