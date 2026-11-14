# ML delivery state — latest checkpoint 2026-11-14 20:38 UTC

## Latest user steering: namespace relocation in progress

The user explicitly requires ALL of this session's dedicated ML work, including the already published release, under `ml/pvusatov/` with subdirectories preserved. They additionally authorized VPS use and merging this namespace. Root created branch `refactor/ml-pvusatov` from fresh origin/main0bf04fa. The complete Python directory now lives at `ml/pvusatov/backend/inference`; no compatibility symlink or old copy remains. Dedicated Scala/test/protobuf, frontend and ML reports have also moved. `ml/pvusatov/relocation-manifest.json` records152 original byte hashes. Frozen v2 and its source/scientific evidence are unchanged.

Run preserved offline commands from repository `ml/pvusatov` with `PYTHONPATH=backend/inference`; the historical relative backend/inference subpaths remain valid within that namespace. Root protocols and this ledger now live in `ml/pvusatov/docs/ai`, superseding the old external local docs/ai paths. Do not recreate ML work in those old locations.

Agents have transitioned: detector agent completed frontend build/lint/browser relocation and is fixing the experimental stale-geometry recacher before twelve twin recaches; native-data agent owns Scala/build/protobuf wiring plus compact acquisition-evidence publication; ranker agent owns selection provenance/comparator/common-attribution fixes after its remaining initialized forest workers finish. All final pixels remain closed. Source-dependent native generator4467 finished successfully BEFORE the Python move. Grid5096 can finish from memory and/tmp, no old-source reads.

Root checks at relocated path:78 scientific tests passed,23 experimental tests passed, real packaged-data smoke/model SHA passed. Frontend build/lint passed with preexisting warnings; isolated actual browser module/CSS checks passed. Scala compilation/integration checks are running. Root owns Docker/CI context changes and final publish/review. New VPS has7.3GiB RAM/4CPUs with6.4GiB available; use for bounded validation, without disturbing the existing runtime. Existing v2 proof scripts/outputs are preserved in `ml/pvusatov/verification/v2-delivery/` with hashes and explicit historical limitations.

## Current authoritative checkpoint

The goal remains ACTIVE. Latest explicit user steering asks to use the laptop's 64 GB RAM and dispatch more parallel agents. All three child slots are now active: `/root/v3_ranker_training`, `/root/v3_detection`, `/root/v3_native_data`. Root plus three workers is the current concurrency limit. OS reports 61 GiB and 22 CPUs; budgets are 10CPU/24GiB, 6CPU/12GiB and 2CPU/4GiB, with >=10GiB left globally available. Do not allocate idle RAM merely to fill it.

The prospective v3 protocol, ownership, data split, seed reservation and promotion gate are recorded in `docs/ai/ML-V3-COORDINATION.AI.md`. This file is the next-turn entry point. Three agents own ONLY new experiment directories/reports; no one has changed frozen v2 or production defaults. Do not checkout/reset/rebase or broadly stage paths while agents write untracked files in the shared worktree.

Native expansion now comprises 8 train / 11 development validation / 10 quarantined final parent fields, with all new validation downloads complete and final byte acquisition running. Final augmented variants are primary; shorter original variants secondary. No final pixels opened. A primary-documentation plus asymmetric-marker orientation audit passed on12 D1–3 development frames through actual native ePSF sampler and WCS pull map (max centroid discrepancy0.02415px); MWIR4–6 is unverified.

Ranker has 3,000 independent synthetic train fields and800 validation fields cached, original sigma1.2 grid48 forests fitted, sigma0.8 domain-balanced84-model grid ongoing. Positive-only acquisition domain AUC0.873 is a real shortcut concern; zero-native-mass and stationary-native-artifact ablations retained. Detector narrow sigma0.8 adds substantial synthetic/native detection recall but frozen v2 ranker does not automatically improve same-budget results. Slow-profile450-trial diagnostic distinguishes spatial matches from established motion and records temporal subtraction attenuation. Expanded validation270 derivatives/parent is now being generated for both sigmas and equal default/slow options.

Final synthetic seeds are **2000000..2001999**, reserved but unopened. Provisional1700000/1800000 ranges were withdrawn before any final generation because different development generators already used them. No candidate may be final-tested before artifact/code/options/data-manifest freeze. Root owns final evaluation and promotion; keep v2 if no mean-regression gates fail. Do not complete the overarching goal merely because v2 is deployed.

V2 delivery IS VERIFIED: PR9 merged and actual new-VPS HTTP, gRPC, PNG, SSE and Swagger passed. PR11 merged at20:03:56UTC as eeda82aff7c1e524df6c3d4ee94a0f5e7c01466a; both PR workflows passed. Actual public viewport regression now PASSED on latest frontend0bf04fa at20:32UTC: desktop panel top48/bottom1000, provenance976; mobile top48/bottom844, provenance830; Homepage exits inference. Proof `/tmp/spaceapps-ml-viewport-prod-proof.json`.

Read-only actual server audit `/tmp/spaceapps-ml-server-audit-current.json` at20:32:32UTC: backend82c1dbc healthy, frontend0bf04fa healthy, each running image equals its exact and latest tag; Python3.12.3; actual ONNX v2SHA verified; gRPC private127.0.0.1:50051. Different component revisions are legitimate; other user-authorized sessions keep advancing main. Preserve their migration/deployment work. Main0bf backendCI43637772586 was still running at20:31 while frontend43637772577 passed. Earlier82c backend/frontend both passed. No need to fight cancelled redundant uploads.

The older sections below are chronological historical checkpoints; their pending actions and old process/status claims are superseded by this section. Current root worktree remains `fix/inference-viewport` atd0b9e3c with only untracked agent experiment/report files. Production target is144.124.238.101; old35.159.162.202 must not be redeployed. Only the root-owned private new-VPS SSH tunnel51344 remains; local test API/Vite servers are stopped.

## Final ML scope and UI follow-up (19:58 UTC)

- The backend actually deployed on the new VPS is healthy d1e633c and its entire inference/runtime backend subtree is identical to subsequent frontend-only main revisions. Its main CI43631682074 passed all tests, image, rollback and automatic deployment. Later redundant backend uploads were intentionally cancelled by the migration owner; do not restart them or require backend/frontend commits to match when the backend source is unchanged. Verify each deployed component's real revision and latest tag instead.
- Physical server audit `/tmp/spaceapps-ml-server-audit.json` proves Python3.12.3, exact v2 ONNX digest, private gRPC127.0.0.1:50051, and healthy running/exact/latest image equality. Backendd1; latest frontend at that audit0a2da5a. No ML source/artifact changed.
- Frontend owner000c2e5 integrated InferencePage inside the shared application and restored global navigation. It **did not remove inference**: `?analysis=1` initializes the inference tab; Homepage can leave it. Do not revert this behavior or add query hijacking.
- That integration exposed a real48px clipping bug (panel bottom1048 in1000px viewport). Root created branch `fix/inference-viewport` at main000c2e5 and changed ONLY InferencePage.css: min-height0,flex1. Actual Firefox RED reproduced; local GREEN desktop bottom1000/provenance976, mobile bottom844/provenance830; Homepage exit preserved. Lint/build passed with existing warnings.
- Follow-up PR11 <https://github.com/Nirbaan13/team_showerless/pull/11>, headd0b9e3cb52c4f6a830284389aad41a37c05d28fa. Frontend CI43634663279 passed; backend CI43634663250 (unchanged runtime) still building/rollback at last check. Wait for appropriate checks, merge through PR, and verify the CSS on the actual production page before completion.
- Current worktree is `fix/inference-viewport` atd0b9e3c, clean; original feat/ml-inference remains preserved. Subsequent main0a2da5a optimizes Docker image-delta transfer for the migration; its backend runtime/inference source is unchanged. Keep the migration owner's deployment changes.
- Local API92846 and Vite91213 were explicitly stopped after local GREEN; owned PIDs61825/23642 receivedSIGTERM. Native/test waiters terminal. Only private new-VPS SSH tunnel51344 remains needed for final proof; stop after completion verification.
- Production HTTP/gRPC/Swagger/model proofs already passed. Final after-UI-rollout check should load the bookmarked real jobf5a4bcc9-fbce-4291-88dd-945182ea8de5 directly (ML nav link was intentionally removed by frontend owner), verify viewport/provenance + global navigation, actual current versions/modelhash/latest tags, and CI frontend success. Do not insist on cancelled unrelated backend reuploads if source identity and deployed ML are proven.

## New-target live proof (subsequent update)

- Verified owner SSH through `/home/usatovpavel/.local/state/spaceapps-migration-20261114/known_hosts`, preserving strict checking. Admin root key works. Private gRPC tunnel session51344 forwards local15057 to new VPS127.0.0.1:50051; old tunnel remains stopped.
- Backend migration workflow43631682074 succeeded and deployed d1e633c; frontend fc0a4be is healthy. Frontend workflow43631776614 was successfully rerun by its owner (attempt2), so no extra rerun was made here.
- Actual production HTTP proof `/tmp/spaceapps-ml-http-prod-proof.json`: d1e633c, jobf5a4bcc9-fbce-4291-88dd-945182ea8de5,4frames/10candidates,28PNGresources,89,233bytes,modelSHAverified,SSE/schema/dedup/empty/error passed. An initial concurrent probe hit one connection timeout; isolated retry passed in3.18seconds.
- Actual private gRPC proof `/tmp/spaceapps-ml-grpc-prod-proof.json`: jobdc295412-a195-42bf-82b8-7fb3dafc3b2f,3frames/2candidates,HTTP/gRPC result equality and completed watch replay passed.
- Actual production Firefox proof `/tmp/spaceapps-ml-browser-prod-proof.json`: jobe56a45c5-9951-4590-9a60-a128b09f21c4,4frames/9candidates atSNR4.25,realPNG/trajectory/order/empty/error/desktop/mobile allpassed,noJSerrors. Production screenshot `/tmp/spaceapps-ml-v2-browser-prod.png` visually inspected.
- Actual production Swagger proof `/tmp/spaceapps-ml-swagger-prod-proof.json`: frontend proxy fetched20paths and TryItOut returnedv2models,noJSerrors.
- Latest backend fc0a4be run43631776603 has passed tests/image/model/current+legacyrollback and is now in **Deploy main to VPS**. Do not mark complete before its outcome and current-version/tag checks.
- New-target version waiter session27222 runs `/tmp/spaceapps-ml-await-netherlands.py`; log `/tmp/spaceapps-ml-netherlands-deployment-wait.log`. It expects both servicesfc0a4be on144.124.238.101. Production scripts were rewritten to target newIP; HTTP accepts d1/fc0 and checks≥20paths. All prior verification-only native test handles terminal.
- Need after fc0 deploy: confirm both public versions, compare persisted HTTP result/PNGs to pre-upgrade proof, confirm running/latest Docker image IDs+filemodelSHA/privategrpcbinding, latestCIgreen, save final audit and stop only owned temporary localAPI92846/Vite91213/tunnel51344. Root source worktree remains clean on9050, original feature alreadymerged.

The active goal remains “read WhatsApp and build corresponding ML inference”, with the original15-hour allocation. Do not claim complete until deployment and actual production behavior are verified.

## Finished source and verification

- Worktree `/home/usatovpavel/.codex/worktrees/spaceapps-zio-backend`, branch `feat/ml-inference`, commits14aac18 and9050dc8. PR9 merged by authorized PR flow at19:13:16UTC: <https://github.com/Nirbaan13/team_showerless/pull/9>, merge973e9a7deb681f49bd422533ccf8ceebaf222ac4.
- Frozen model `spherex-track-rf-v2`, SHA-256 `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9`; no retuning after the final held-out tests. Honest results: synthetic top3 143vs99/785; one real parent field150correlated injections, detector28, RFtop3 24vs17 buttop1 11vs15. V1negative findings archived; full reports/manifests coherent.
-120Scala tests/stage,78Python tests, frontendlint/build passed. Actual local HTTP/gRPC/SSE/PNG/schema/dedup/restart, browserpositive/empty/error/mobile and proxiedSwaggerTryItOut passed. Native chain used genuine captured SIA metadata plus three live IRSA cutouts:12MB,3frames,0tracks,12sec; firstSHA matches independent originalsample. Controlled metadata replay is explicit; no fake image fallback.
- Isolated old-VPS Docker Python3.12 real-model smoke and Scala→Python→ONNX→SQLite→PNG passed. Temporary container/volume removed. Production model has NOT yet been verified.
- PR CI43630056544 and43630056545 both passed, including exact image, packaged model and current/legacy Compose rollback. Detailed repo record: backend/docs/implementation/ML-INFERENCE-VERIFICATION.AI.md.

## CRITICAL deployment handoff

The old AWS target35.159.162.202 is obsolete for this release. DO NOT restart its cancelled main workflow or deploy there. Another user-authorized session intentionally cancelled main run43630900739 before deployment to perform urgent Netherlands-VPS migration. This was confirmed by its narrowly read cancellation records after cross-thread connector transport failures.

New target is **144.124.238.101**, declared in main workflows/OpenAPI. Migration commitd1e633c0f962c89fcf29228923d0e0c1845900f4 retains all ML changes. Latest main fetched at19:23 is **fc0a4be6437188f1c86a633314c3300f609527a6**, also incorporating teammate frontend/motion-review changes. Inspection confirms `?analysis=1` still renders InferencePage and new backend methods/model source remain unchanged; Vite/nginx preserve `/backend` and `/api` proxy routes.

Current new-target workflows:

-43631682074: backend migration d1e633c, running at last check.
-43631682028: frontend d1e633c deployed but final API-proxy probe failed502 because backend not up yet.
-43631776603: latest backend fc0a4be, pending behind prior backend.
-43631776614: latest frontend fc0a4be, check actual conclusion.

New frontend public version already reportsfc0a4be; backend public/version currently resets connection while bootstrap/deploy proceeds. Wait for actual current run handles, do not infer failure from observation timeout. If frontend final proxy probe failed before backend existed, rerun only after backend is live, checking whether the migration owner already restarted it.

Owner key exists at `/home/usatovpavel/.ssh/spaceapps-netherlands-admin-20261114`. First root SSH attempt with strict global known_hosts failed because no global host-key record; DO NOT disable verification. Locate the migration owner's verified known-hosts file/fingerprint and use it. Backend/frontend CI keys also exist but have restricted commands; do not print their content. No credentials were exposed.

Cross-thread send_message_to_thread fails transport at127.0.0.1:46293. WhatsApp reading still works; latest messages only update mobile frontend, no new ML requirement. a2a registry belongs to unrelated Diploma agents; do not send there. The other migration session is01a1d8c1-8242-7c03-ad19-cdaff7ad7016. Its local rollout path was found narrowly by UUID for cancellation diagnosis; do not dump unrelated messages or credentials.

## Remaining work

1. Observe new-target backend/latest CI and frontend proxy health; preserve other session's migration ownership.
2. Rewrite prepared production verification scripts from oldIP35.159 to144.124.238.101 and expected revision to actual new deployed main (fc0a4be or later descendant retaining973). Current scripts under/tmp/spaceapps-ml-*-prod-smoke.* still target OLDIP and must not be run unchanged.
3. Verify actual public HTTP computed result and all PNGs, typed private gRPC via verified SSH tunnel, actual frontend page and SwaggerTryItOut. Confirm modelSHA and Gitrevision/latest image tags. Final goal audit must inspect live evidence, not only CI.
4. Record final live results in an AI-named local docs file, clean up only owned local temporary servers/tunnels, then mark goal complete only when every required gate is proven.

Old-target deploy waiter45226 and SSH tunnel46446 were intentionally stopped after learning migration; terminal exits130/0. Current local review API92846 at18086/GRPC15056 and Vite91213 at18087 remain; stop only these verified owned processes after final production proof. No training/native test process remains.

PR7processing,PR8federatedarchives,PR10IRSAcutouts are separate open teammate work. Do not merge or rewrite them as part of ML delivery. Current root worktree stays clean on feature9050; origin/main is fetched tofc0. All scientific source/artifact hashes remain frozen.
