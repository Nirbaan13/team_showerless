Moves this session's dedicated ML implementation and already published release into `ml/pvusatov/`, preserving the previous backend/frontend subdirectories. Shared application entry points and builds include the relocated sources; the existing retrieval and teammates' ML services keep their current locations.

The Python runtime, training, fixtures, frozen models, reports, experimental source/evidence, dedicated Scala API/service/domain/repository/gRPC sources, protobuf definitions and frontend review page/client now share this namespace. Docker uses the repository build context, and CI tests the relocated package and experiments. The analysis protobuf file is separate while its wire package/service/messages remain compatible.

Validation before publication:

- 131 Scala tests passed and staging succeeded; one existing optional live-IRSA test was ignored.
- 78 Python package tests and30 experimental tests passed after the reviewed shared-selection-cohort correction; the real-data smoke loaded the unchanged v2 model.
- All78 frozen runtime/scientific files retained their original byte hashes; modelSHA is `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9`.
- Frontend lint/build passed. Five existing shared React-hook warnings and the existing bundle-size warning remain.
- Running local HTTP/gRPC returned equal real results;28PNGresources, SSE, deduplication, empty/error responses and result schema passed. Actual browser Swagger execution and desktop/mobile result bounds passed.
- A client generated from the extracted protobuf interoperated with the existing VPS service before rollout.
- Independent review reproduced and verified the fresh-CI scratch-directory fix; no remaining concrete Docker/CI/frontend blocker was found. Initial PR12 CI passed clean Python/Scala/frontend checks, image build, packaged real-data inference and current/legacy rollback. A subsequent experimental selection-cohort correction receives fresh checks before merge.

V3 experiments are development evidence only. Their final synthetic/native inputs remain closed, and this relocation does not promote a new model. `relocation-manifest.json` retains original path/hash records; historical manifests are preserved rather than rewritten.
