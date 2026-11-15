# CI and deployment

Tests and deployment run in independent GitHub Actions workflows.

- `Backend tests (agents do not wait)` and `Frontend tests (agents do not wait)` run asynchronously. Agents must not block a merge, deployment, or task completion waiting for these workflows. Do not poll or use `gh run watch` for test workflows. Report any already-known failures; do not describe pending tests as passed.
- `Backend deploy (agents wait)`, `Frontend deploy (agents wait)`, and `Hostinger deploy (agents wait)` are the release completion gates. After an authorized merge to `main`, wait for the deployments of that exact revision and verify the deployed revision and health before claiming deployment is complete.
- Deployment includes the production build and live revision/health checks. It must not depend on test workflow completion, test artifacts, or `workflow_run` triggers.
- Keep tests enabled with normal failing statuses. Asynchronous tests are not `continue-on-error` tests.
- Apply the additional instructions in `backend/AGENTS.md` when working under `backend/`.
