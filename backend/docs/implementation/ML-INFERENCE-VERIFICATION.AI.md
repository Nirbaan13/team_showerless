# Motion inference integration verification

This record covers the feature based on commit `14aac18439ef9259c4ae5391c691efecb7920e58` and the subsequent Swagger proxy correction. CI and the deployed revision must be checked separately before release. Scientific evaluation and its limitations are recorded in [ML-MODEL-EVALUATION.AI.md](ML-MODEL-EVALUATION.AI.md).

## Automated checks

- Full scientific suite: 78 passed, including frozen-release hash/provenance checks, ONNX/sklearn parity, training-import exclusion, WCS/mask/native-input handling, real fixtures and evaluation accounting.
- Full Scala suite plus staging after final integration: 120 passed, zero failures. This includes native snapshot leases, durable jobs/recovery, HTTP/gRPC contracts, result/resource bounds, existing metadata/equipment/deep/LRU coverage and Swagger URL resolution.
- Frontend lint and production build passed. Five warnings already exist in the surrounding frontend.
- Independent read-only integration review found no P1/P2 blocker in service wiring, snapshot lifetime, output publication, packaging, frontend contracts or release bookkeeping.

## Running HTTP and gRPC

The actual staged Scala service loaded model `spherex-track-rf-v2`, SHA-256 `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9`.

HTTP example `e70826da-0481-4c18-b12d-6fb043b069f3` completed with four real archived exposures and ten computed candidates. SSE reached completion; 28 PNG resources were fetched and validated; the actual result passed its OpenAPI schema. Identical submissions reused the persisted job. A threshold-100 request completed with zero candidates; a missing download returned404 and oversized options returned422. After an actual API stop/restart, the same completed result and all four frame PNGs remained available.

Actual gRPC submission `ad021a13-591d-4d63-bba1-d64778bea76d` completed with three real exposures and two candidates. Its result equalled the HTTP result for the same persisted job; watching an already completed job replayed completion. The public protobuf and its resolved imports were used with checksum-verified grpcurl1.9.4.

## Browser and Swagger

Isolated Firefox exercised the actual API. A threshold-4.25 request returned four exposures and nine candidates; real PNGs and selected trajectories loaded, and changing to heuristic ordering changed the candidate order. Empty and missing-download cases displayed their actual responses. Desktop and mobile navigation reached the analysis page without JavaScript errors or mobile horizontal overflow.

The new API-documentation link exposed a preexisting proxy issue: Swagger loaded `/openapi.json` from the frontend and received HTML. The regression failed before changing its specification URL to relative `openapi.json`. It then resolved correctly from both `/docs` and `/backend/docs`. Browser verification loaded all 20 OpenAPI paths through the frontend proxy and successfully executed `GET /api/analyses/models` in Swagger. The development proxy also forwards `/api/`, matching the existing production nginx routes.

## Native FITS download-to-analysis chain

Direct live SIA discovery attempts encountered upstream HTTP502 and metadata timeouts. They produced explicit retryable errors. Full public S3 transfers also exceeded the existing five-minute per-file deadline on this connection; no application fallback or archive-query behavior was changed.

To isolate native processing from SIA availability, a verification-only local endpoint replayed six genuine SIA rows captured from the archive for M101 on2025-05-10. Its access URLs requested the corresponding official IRSA cutouts. All science bytes were downloaded from IRSA; no local image substitute, generated source or expected trajectory was supplied. This metadata replay is a controlled integration test, not proof that live SIA discovery is universally available.

Native analysis `95901b7d-5a62-4d73-aee5-90e43f84e49f` downloaded three detector-2 FITS files totaling12,000,960bytes, completed in12.08seconds, and published three59×59 prepared frame PNGs. It returned zero tracks for these closely spaced observations. That empty result was preserved. Its physical observations were `2025W19_2B_0346_1`, `_2`, `_3`; exposure midpoints came from FITS.

Input SHA-256 values:

```text
0143817ceec1a56d8ec85b7f8f5d760e20b3376a7afd73bf637657ff36eb980b
024ca59a1b8e7d1756f8abdcb186aaa769b2b347184dd3a18daed5aef418a38f
e94807c1118d905f973b586c87237d6b71b8fe9ae1d418545bc1a9b1d9580ccb
```

The first digest independently matches the original preserved M101 sample provenance. Warnings correctly describe uncorrected passband/PSF variation, experimental ranking, linear-motion assumptions and the empty candidate set. This test complements the frozen model's separate full-native real-background evaluation; it does not add training data or retune the model.

## Container/runtime

An isolated VPS image built from feature commit14aac18 ran the real CLI smoke with a read-only root filesystem,2CPUs and2GiB. It verified the v2 model digest. A separate temporary Scala API container, limited to2CPUs/4GiB and bound only to loopback, ran Scala→Python3.12.3→ONNX→SQLite→HTTPPNG successfully: four exposures, ten candidates, about2.51seconds. Observed memory after completion was228.9MiB; this is not a peak-memory measurement. The temporary container and anonymous data volume were removed. Production containers remained unchanged during these checks.

The final CI image, deployment rollback checks and deployed HTTP/gRPC/frontend revision still require their normal release gates.
