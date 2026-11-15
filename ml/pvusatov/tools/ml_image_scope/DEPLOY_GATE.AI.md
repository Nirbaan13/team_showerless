# Verify the active frontend contract

The ML image deployment for `f0dd775` succeeded, then its final proxy check failed because it required HTTP 200 from three retired routes. The live frontend forwards those routes to Scala, whose capabilities advertise `legacy_motion_service` and `community_catalogue` as unsupported. `LegacyUiApi` returns HTTP 501 with `unsupported_legacy_operation`. Restoring the retired routes would change the intentional application contract.

The deployment workflow now invokes `verify_frontend_routes.py`. It requires a healthy processing worker, installed motion models, supported motion analysis and a functioning models route through the frontend. It checks each legacy route against the advertised capability: an unsupported route must return HTTP 501, the exact unsupported code, `retryable: false` and the current motion-analysis URL. A supported route must return HTTP 200. No application route or status is changed by this probe.

The direct live probe passed at revision `f0dd7757b0a5925527cafe43838c0f231b3bfd5f`, with one installed model and all three legacy responses matching their declared unsupported state. The laptop needed the direct-IP host in `NO_PROXY`; the server route itself was healthy.

Review found that model discovery can temporarily return `motion_models: null`. A regression first reproduced the unhandled `TypeError`, then passed after explicit readiness validation. The test verifies that the same check retries once and completes when the subsequent discovery and routes become ready. Workflow YAML parsing and the live probe also pass. Actual merged-image build, source closure and deployment health remain release gates.
