# Archive execution ledger

Architecture and all six tasks read in full. Base: 13d580e. Worktree and branch isolated.
Using executing-plans, test-driven-development and verification-before-completion.

Ruling: use bounded secure TABLEDATA parsing initially, rather than generalized STIL — retained production probes use TABLEDATA; unsupported binary serialization returns a typed error, never silent loss. No BINARY2 claim.
Ruling: no push or PR from this worker — coordinating root explicitly owns final review and delivery.
Context7 is absent from available tools; supplied primary protocol research and repository runtime examples are the fallback.

Task 1: 4 targeted domain/repository tests green (27 s), committed 1f236ac.
Tasks 2–4: 21 archive tests green (16 s), including retained ESO/CADC overflow and DataLink, bounded plain/gzip transfer, native ART-XC, BASS, Gaia, LAMOST, static catalogue and IRSA bridge.
Fresh anonymous metadata checked 2026-11-14: LAMOST release-status + DR11 v2.0 cone, SRG first-year catalogue. Fixture bytes are bounded, no response headers/cookies/grants retained.
Ruling: BASS exposes native date form parameters but rejects exact UTC filters — its clock was not verified. Image host remains a declared unavailable delivery capability, preserving discovery records.

Task 5: initial 4 federated tests passed (19 s). Extended tests cover shared concurrency, two transient retries, recovery, additive routes and native foreign download. API uses a bounded 64 KiB body and strict property sets, never accepts upstream URLs. Typed outcomes expose provider failures and genuine continuation independently of local snapshot pagination.
Main binding added only after sending interface/route details to coordinator. Existing Api, gRPC server, IRSA source and processing services remain intact.

Tasks 3/5 follow-up review: one shared legacy `FitsCache` coordinator now guards
archive and SPHEREx admission. Gzip reserves both encoded and decoded temporary
space. Four capacity tests cover combined product quota, gzip working storage,
legacy admission after archive publication, and minimum free space. Completed
foreign assets are retained and count toward the shared budget; they are not
legacy LRU eviction candidates.

Lifecycle regressions were run red before their fixes: native download admission
must not wait for a running transfer; ordinary provider and resolver defects must
produce sanitized outcomes and leave no indefinitely running job. A real malformed
HTTP 200 Gaia VOTable is isolated while another provider completes. Multiple
DataLink science originals now fail `ambiguous_science_asset` rather than overwrite
one another under a shared key. 307/308 redirects preserve POST method/body, and
provider continuation honors the same bounded admission queue as a new search.

Final targeted archive run: 49 passed, zero failed, two optional network tests
ignored (`/tmp/spaceapps-archive-final-targeted.log`, 2026-11-14). Final regression
and merge with current main follow this checkpoint; root owns PR delivery.
