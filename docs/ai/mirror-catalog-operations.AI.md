# Mirror metadata catalogue

The API stores the catalogue in `/app/data/irsa-mirror.sqlite` on its persistent Docker volume. The same database retains previously verified rows. Metadata bodies and WCS footprints are compressed without losing numeric precision; older text rows remain readable.

Ingestion discovers the official release/planning-period/processing-version/detector hierarchy and checkpoints each partition. First samples cover partitions before deeper pages. Thirty-two bounded header workers read 64 KiB initially, extending only when necessary to 256 KiB; they never download image arrays. Failed objects retain durable retries. The catalogue is a snapshot of listed archive contents; completed partitions are not automatically refreshed for future releases.

SQLite RTree bounds first select spatial candidates, then the existing spherical WCS geometry checks the actual overlap. The Cartesian index handles RA wrap and polar fields without longitude seams. Status aggregates and search results share a consistent read snapshot. [SQLite documents conservative outward rounding of RTree coordinates](https://www.sqlite.org/rtree.html).

`/api/infra/external-services` reports `mirror_index.catalogue`: discovered releases, total/completed partitions, and committed pages, plus total verified objects and failures. Progress refreshes every 15 seconds while ingestion runs. `complete=false` remains until every configured partition is listed and every failed header is resolved. A partial empty search still reports warming; a partial nonempty search retains its provenance. Partition completion is a listing measure, not a percentage of sky.

The production metadata budget is 8 GiB, separate from the FITS file cache. Exhaustion stops checkpoint advancement and preserves partial searchable results. Do not reset the database to address capacity or network errors.

Operator commands inside the API image:

```sh
/opt/inference-venv/bin/python /app/integrations/irsa_mirror.py --db /app/data/irsa-mirror.sqlite status
```

The supervised builder uses `catalog --page-size 128 --max-pages 4096 --workers 32 --max-seconds 180`. A batch yields between bounded request groups; the deadline does not cancel an in-flight HTTP request. Scala supervises retries and restarts.

Local verification: `python -m pytest backend/tests/test_irsa_mirror.py backend/tests/test_irsa_catalog.py -q` using the shared astronomy environment; `backend/sbtw 'testOnly spaceapps.MirrorProcessSpec spaceapps.MirrorSearchGateSpec spaceapps.ResilientArchiveSpec'`.

Real anonymous mirror smoke on 2026-11-15, using the deployed image's Python runtime and an isolated volume: three releases discovered, 2,562 partitions, 78 verified FITS records, 96 committed partition pages, no ingestion errors. This is protocol/ingestion evidence, not a complete catalogue or proof that IRSA cutout downloads work during the outage.
