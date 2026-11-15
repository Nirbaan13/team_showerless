# spherexblink.tech domain routing

## Problem and target

The domain serves a separate static copy on Hostinger. Its /backend/health and
POST /backend/api/observations/search returned the SPA HTML as HTTP200, causing
JSON parsing to fail and the frontend to select its synthetic fallback. The VPS
API health returned real JSON. This change prepares the VPS as the domain origin.
No frontend TypeScript, Python science, model, cache content or database changes.

## Runtime topology

- Caddy2.11.9, installed from its official stable package, listens on80/443.
- HTTPS apex and www serve the frontend on127.0.0.1:8080.
- /backend/* strips that prefix and forwards to API127.0.0.1:18000.
- /api/*, /health, /version, /docs and /openapi.json forward to the same API.
- /api/motion/* and /api/catalogue/* retain the frontend nginx's existing routing
  to its separately owned service. This migration does not create that service;
  it was not listening on the VPS during inspection. Errors remain actual errors.
- Explicit HTTP domain routes redirect to HTTPS before the catch-all route.
- Direct-IP HTTP keeps exposing the API for existing clients and CI checks.
- Caddy's ordinary SSE proxy behavior flushes text/event-stream immediately.

API host binding is recorded as a single `APP_PORT=127.0.0.1:18000` line in
/opt/spaceapps/listen.env. ops/deploy.sh parses and validates it as data before
loading a release, persists it into current.env, and applies it to deployment and
rollback. New release Compose files already use the APP_PORT variable. Existing
API data volume and image revision remain unchanged during migration.

## Installation and rollback

Install Caddy using its [official package instructions](https://caddyserver.com/docs/install#debian-ubuntu-raspbian),
keeping its service stopped until the API port can be moved. Run as root:

```sh
bash ops/bootstrap-domain.sh
```

The script validates configuration, holds the API deployment lock, backs up the
installed deploy entry point, Compose/environment, binding and Caddyfile, then
migrates only the API container binding and starts Caddy. On failure it restores
those files and service state and exits nonzero. It preserves the API volume.
Current migration backup: /opt/spaceapps-domain-backup.1zvXGq.
Caddyfile: /etc/caddy/Caddyfile. Deployment entry point:
/usr/local/bin/spaceapps-deploy. The proxy is enabled for startup.

## DNS handoff

Nirbaan controls DNS at apollo.dns-parking.com and athena.dns-parking.com. No
DNS-management credential is available in this environment. Existing FTPS GitHub
secrets deploy files; they do not grant DNS management. The Hostinger workflow is
unchanged by this migration; its static copy is selected only while DNS points
there.

Change only the web host records in the authoritative zone:

| Name | Type | Value |
|---|---|---|
| @ | A | 144.124.238.101 |
| www | CNAME | spherexblink.tech |

Replace the old apex A records; remove conflicting www A/CNAME and old apex/www
AAAA records that send traffic to Hostinger. No VPS IPv6 was configured for this
site. Preserve unrelated DNS records. If Hostinger's CDN manages these records,
disable that CDN for these hostnames before applying the origin records.

Caddy's [automatic HTTPS](https://caddyserver.com/docs/automatic-https) obtains and
renews the public certificates after the authoritative A/AAAA records reach this
VPS. Before DNS changes, successful private-CA tests do not establish a valid
public certificate or a completed domain cutover.

## Verification

The real deployment regression first failed because the old deployer ignored the
host-owned binding. The updated test asserts the loopback binding and saved
configuration before update/rollback scenarios. Nine malformed configurations
(including multiline and shell-like content) are rejected before Docker is run.

ops/domain/test-routing.py starts isolated Caddy with its own private CA and local
HTTP fixtures. It verifies TLS hostname trust, www, frontend routes, prefix/query
and POST body preservation, actual JSON error statuses, legacy health, canonical
HTTPS redirects and SSE delivered before the upstream completes. It does not
install a CA into system trust or share production certificate storage.

The CI workflow executes that test with Caddy2.11.9 from the official image and
runs the host binding rejection checks and real container update/rollback suite.
Public HTTPS and DNS checks remain pending until Nirbaan updates the zone.

After installation, a second isolated HTTPS proxy using the same config and a
private CA was connected to the real live upstreams. It served the actual
2,441,762-byte JavaScript asset, frontend and API revision758fb29, backend health,
one inference model, Swagger UI and all41 OpenAPI paths. A malformed search
returned HTTP422 JSON rather than SPA HTML. www and certificate hostname trust
passed. No public certificate is claimed by this test.

The exact Caddy2.11.9 official-image binary used in the CI step also passed the
routing/streaming fixture. CI pins image manifest
sha256:4e2425f6009577e7c651010f16679c28f7d12df3e7b1914f941a7a3370746b3c.
Independent review's rollback control-flow and service-state findings were fixed
and rechecked before installation; no blocking findings remain.

The first full container test on the shared VPS Docker daemon collided with a
concurrent production CI deployment changing the global latest tag. Initial
binding, update and rollback scenarios passed, but that run as a whole failed.
The repeat holds the production deployment lock and restores the actual live
latest tag afterward; production containers/data are distinct from its fixture
Compose project.

The WhatsApp DNS handoff failed with the connector's device-list/LID error. No
notification was delivered. DNS instructions must be forwarded to Nirbaan by the
user until messaging is restored.
