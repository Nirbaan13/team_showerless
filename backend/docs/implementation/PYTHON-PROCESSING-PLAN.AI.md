# Team pipeline integration

The final user-approved design is specified in
[PIPELINE-INTEGRATION-COMPLETION.AI.md](PIPELINE-INTEGRATION-COMPLETION.AI.md).
Scala calls the team pipeline's HTTP container. The obsolete backend Python
subprocess adapter and its configuration are removed. Numerical functions and
HTTP service tests live with the team pipeline under pipeline/.
