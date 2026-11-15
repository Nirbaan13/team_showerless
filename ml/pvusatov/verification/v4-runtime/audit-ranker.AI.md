# Independent VPS runtime audit

PASS. Exact selected graph `c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35` and administrative metadata `472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13` remain unchanged. The audit validated 20 downloaded evidence file hashes plus the local 20-file probe bundle.

The isolated image ran Python 3.12.3; the independent comparison used Python 3.14.4. All 153 published residual candidates have identical ordered IDs, scores and measured epoch sets. Maximum position difference is below 1e-10 pixels. The 13 capped Vesta D3 residual rows were not present in the VPS output and are not claimed tested cross-version. Comet D2 ranks first and D6 second. Vesta D3 and D6 flagged targets remain unscored at ranks100 and18.

Actual cgroup and Docker receipts enforce one CPU, 1 GiB RAM, zero swap,64PIDs, network none, a read-only root filesystem and a256MiB /tmp. Presets used 6.48s and peaked at 110.48MiB. The nonempty32×512×512 workload used 44.10s including probe setup and peaked at 727.15MiB; its CLI took 41.97s and retained a32-epoch measured track. Both cgroups reported zero OOM and limit-hit events. The startup import guard blocks sklearn,skl2onnx,joblib and training; exact runtime sources match the reviewed inference-only implementation.

The maximum-shape fixture uses min_snr10 and output cap3 and does not establish worst-density behavior. Writable evidence/tmp and isolated anonymous data volumes are explicit in the receipt. These are isolated engineering checks; production health, cleanup and independent recovery remain separate. No final data or outcomes were read, and no model fitting, reselection or modification occurred.

Machine-readable hash references and per-case results are in `audit-ranker.json` (SHA `c544cdbefe870953ac4f8647e6f89d23b69033fa42ea7f7f6c3aa8687c43f31b`).
