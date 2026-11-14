# Backend bootstrap — AI-generated documentation

Scala/ZIO IRSA retrieval service for the Planet X and SPHEREx challenge. See [running instructions](docs/implementation/RUNNING.AI.md) for API behavior and limits.

## Live server

- API: http://35.159.162.202/
- Swagger UI: http://35.159.162.202/docs
- Health: http://35.159.162.202/health
- Version: http://35.159.162.202/version

The application version and OpenAPI version are the full GitHub commit SHA.
Each successful deployment creates `spaceapps-api:<commit-sha>` and moves
`spaceapps-api:latest` to the healthy deployed image **on the VPS**. Images are
streamed directly from CI; this bootstrap does not publish a registry image.

## Local development

```bash
cd backend
./sbtw test stage
APP_REVISION=$(git rev-parse HEAD) java --enable-native-access=ALL-UNNAMED -cp 'target/stage/classes:target/stage/lib/*' spaceapps.Main
```

JDK25 and sbt1.13.1 are the build baseline. Application sources live under backend/src/; persistent state and native FITS are stored under DATA_DIR. Scientific processing and PNG previews are explicitly deferred.

## CI and deployment

Pull requests to `main` run the API tests, build the container, and exercise
successful deployment, version reporting, the `latest` tag, and rollback against
a real Docker daemon. A push to `main` runs those checks and deploys the exact
tested image. The workflow can also be run manually from the `main` branch.
Deployments are serialized. Rapid pushes replace older pending workflow runs;
the active deployment finishes before the newest pending commit is deployed.
Failed health checks restore the previous image, including on a rebuild of the same SHA;
neither the recorded version nor `latest` is updated for a failed deployment.
Container replacement causes a short interruption; this is a single-server setup.

The workflow uses these repository Actions secrets:

| Secret | Meaning |
| --- | --- |
| `VPS_HOST` | Server IP, currently `35.159.162.202` |
| `VPS_USER` | Dedicated SSH account, `deploy` |
| `VPS_SSH_KEY` | Dedicated CI private key; never commit it |
| `VPS_KNOWN_HOSTS` | Server SSH host key verified through the owner's SSH connection |

The CI key is restricted to `/usr/local/bin/spaceapps-deploy`; it cannot open an
interactive shell or forward ports. Only trusted contributors should be able to
push to `main`: deploying application containers is privileged server access.

To bootstrap a replacement Ubuntu 24.04 server, copy this checkout and the CI
public key to it, then run:

```bash
sudo bash ops/bootstrap-vps.sh /path/to/ci-key.pub
```

Allow inbound TCP 22 for GitHub-hosted runners and TCP 80 for the API. This
bootstrap serves HTTP; add a domain and HTTPS before introducing sensitive data.
If the EC2 public IP changes after a stop/start, update `VPS_HOST` and
`VPS_KNOWN_HOSTS` (or attach an Elastic IP).

On the VPS, deployment state is in `/opt/spaceapps/current.env`. Inspect it using
the owner's SSH account:

```bash
sudo cat /opt/spaceapps/current.env
sudo docker compose --project-name spaceapps --file /opt/spaceapps/compose.yaml \
  --env-file /opt/spaceapps/current.env ps
sudo docker compose --project-name spaceapps --file /opt/spaceapps/compose.yaml \
  --env-file /opt/spaceapps/current.env logs --tail 100
```

To rerun the container deployment integration test locally with Docker:

```bash
cd backend
revision=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
docker build --build-arg "APP_REVISION=$revision" --tag "spaceapps-api:$revision" .
TEST_IMAGE_REVISION="$revision" bash tests/test_deploy.sh
```

Application code, dependencies, tests, and the Docker build context live in
`backend/`. Shared deployment infrastructure (`compose.yaml`, `ops/`, and
`.github/workflows/`) stays at the repository root. Run the VPS bootstrap command
from the repository root. Generated documentation uses the `.AI.md` suffix;
the root `README.md` is intentionally empty.
