# Independent VPS engineering audit: bundle v3

Verified **25 evidence artifacts and 26 bundle inputs**. Graph `c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35` and metadata `472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13` match the selected V4 package. No FINAL data, inference/model session, service/container change or VPS write was performed.

| Probe | Wall time | Whole-cgroup peak |
|---|---:|---:|
| presets | 6.212 s | 110.55 MiB |
| maximum | 19.890 s | 672.90 MiB |
| native-coverage | 1.271 s | 94.41 MiB |

All three completed with one CPU quota, 1 GiB hard memory, no swap, no OOM/max-memory events, network none, read-only rootfs/input bundle, configured user `app`, PID cap 64 and 256 MiB `/tmp`. Writable evidence binds and three separate inherited anonymous `/app/data` volumes were present; no production data bind appears in the receipts. Python 3.12.3 and dependency versions agree across probes.

The native engineering fixture retains all four physical IDs/timestamps and reports epoch 1 at zero coverage with its warning. Independently fetched/decoded PNG samples: **7**. Both blank-epoch frame and difference PNGs are entirely black; four preset frames and one covered engineering frame were also verified.

The controlled 32×512×512 maximum ran one measured 32-epoch track at minSNR 10 and publication cap 3, generating 66 transient resources. Its child CLI took 17.936s / 638.95MiB child maxRSS. The outer cgroup measurement includes the probe process and child; it is not Docker CLI RSS.

Earlier **V4 prototype**, same graph/workload: 44.10s / 727.15MiB versus 19.89s / 672.90MiB now (2.22× observed wall-time ratio). This is not a production V3 comparison or a repeated latency study.

Limits:

- Numeric process UID not recorded; Docker configured user app verified
- Writable output bind,256MiB tmpfs and distinct inherited anonymous /app/data volumes exist; rootfs and input bundle are read-only
- Only sampled retained PNGs independently checked; maximum-run PNGs were deleted with its temporary directory
- Controlled one-track maximum shape at minSNR10/publication cap3 is not a worst-density/default-options guarantee
- One run per mode; observed timings are not p95, concurrency or throughput guarantees
- Five bundle inputs live outside git in the declared engineering fixture directory; full input rehash requires those exact files
- Standalone maximum child text says no cgroup claim; outer actual cgroup proof supplies the hard bound
- Resource/integration engineering audit does not substitute for independent recovery or promotion approval

Run `python ml/pvusatov/verification/v4-runtime/audit-v3-data.py --ssh-pngs` using the shared UtilsAI interpreter for the optional Pillow byte checks. SSH uses the externally held key and strict known-host verification; it only cats the seven declared existing engineering/DEV PNGs. Omit the flag for local metadata/hash replay; that does not repeat PNG-byte verification. Default execution prints a check result without overwriting the published audit; add `--write` explicitly to produce a new JSON/report.
