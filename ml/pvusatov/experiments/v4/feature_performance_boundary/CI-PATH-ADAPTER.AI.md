# Portable boundary tests

The original frozen harness loaded C596 from the development snapshot `/tmp/spaceapps-v4-operating-points/models/C596`. The local benchmark and tests had that cache; clean CI did not. CI correctly reported two missing-model-file failures.

The added test fixture verifies the exact C596 graph and472a metadata in the versioned release directory, then relocates the harness's model path for each pytest case. Frozen harness/test/protocol bytes and all32 benchmark results remain unchanged. Reference/prototype arithmetic, model bytes and source bindings do not change. This is a test-location adapter, not a new benchmark or a fabricated cache.
