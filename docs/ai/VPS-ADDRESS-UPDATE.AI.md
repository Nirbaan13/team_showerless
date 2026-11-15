# VPS endpoint reference migration

The user requested replacing the retired VPS endpoint throughout the repository with `146.103.122.246`.

This changes endpoint references in the raw OpenAPI YAML, deployment documentation, smoke/benchmark/probe script defaults, and saved verification documents. Strict SSH scripts use the new server's administrative identity and pinned known-hosts file.

Historical verification JSON and reports also had endpoint references readdressed at the user's explicit request. Their captured results, timestamps, model identities, metrics and scientific data have not been recomputed. Updated endpoint references are not evidence that the old checks ran on the new host. Original records remain available in Git at parent revision `47224cb853adcd42a54b09b09b85333f961d2f40`.

The current browser client continues using same-origin `/backend`; the Hostinger proxy and deployment workflows already target the new VPS. Runtime Swagger JSON continues using `/`, while the standalone YAML now points to the current host.

Seven integrity manifests that bind rewritten scripts/reports were refreshed to match current file SHA-256 and byte counts, including nested manifest bindings. Each carries an explicit `endpoint_reference_migration` annotation tying the historical results to the parent revision and recording `results_rerun: false`. This is an endpoint-reference migration, not a new scientific publication or verification run.
