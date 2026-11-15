# Domain to VPS implementation plan

Goal: serve spherexblink.tech and its API from the existing VPS using HTTPS, with existing CI and direct-IP API compatibility.
Architecture: Caddy on 80/443 proxies domain traffic to the existing frontend and API. API moves to 127.0.0.1:18000; a host-owned listen.env persists this binding across deployment/rollback. Direct-IP HTTP continues proxying to API. Caddy manages certificates after Nirbaan changes DNS.
Scope: ops scripts/configuration and operational documentation only. No frontend TypeScript, Python science, model, or data edits.

- [x] Add a real deployment regression asserting that host binding survives release deployment and rollback; reproduce failure before implementing host configuration.
- [x] Teach ops/deploy.sh to validate and retain a single APP_PORT setting from listen.env, without evaluating shell code.
- [x] Add Caddy domain, prefix-stripped backend, native API, Swagger and legacy IP routes; validate routing and streaming against real upstreams.
- [x] Back up installed deploy entry point, compose/environment and binding settings. Under deployment locks, migrate the API binding and start the validated proxy; restore previous state if health fails.
- [x] Verify HTTP host routing, HTTPS using an isolated test certificate before DNS, actual JSON API errors/status, frontend assets and Swagger. Preserve cached data and revisions.
- [ ] Request independent review, push an ops PR, and provide Nirbaan the exact A/www/AAAA DNS changes. Verify public TLS after DNS propagation if completed during the task.

Review focus: prefix stripping/query preservation; SSE buffering/cancellation; IP-based CI health compatibility; malformed host configuration before mutation; deployment rollback and preservation of API volume/revision; DNS changes do not affect MX/TXT records.
