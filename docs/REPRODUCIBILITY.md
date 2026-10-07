# Preserving and Replaying Research

Frozen experiments retain their original code, data, configuration, costs and search history. Corrected code creates a new research version; it cannot silently replace evidence from an older version. Runtime hashes intentionally block changing an experiment midway.

The source-only preservation command excludes credentials, caches and research datasets:

```bash
PYTHONPATH=python .venv/bin/python -m research.source_archive create \
  --output local/source-archives/core-0.5.0
PYTHONPATH=python .venv/bin/python -m research.source_archive verify \
  local/source-archives/core-0.5.0
```

It refuses existing output and verifies every Python file and the exact source set. Source manifests and checksum files establish integrity relative to the recorded manifest, not authorship or trust. Execute only archives with trusted provenance.

To verify the old stock campaign after the live code has evolved:

```bash
PYTHONPATH=python .venv/bin/python -m research.source_archive verify-stock \
  --archive local/frozen-stock-source-2026-10-03 \
  --campaign local/stock-campaign-2026-10-03-finalized
```

This checks the archived files against the campaign's frozen source hashes and invokes its original verifier in a separate Python process using a clean temporary copy of those verified source files. Cached bytecode and native artifacts in the original archive cannot override the copied source. It verifies saved results; it does not run a new strategy experiment, alter results or relax hashes. The current live verifier correctly refuses the older file-set binding. Source archives must be outside the source tree they preserve.

Before remediation, 113 source, test, fixture and documentation files were captured in `local/audit-remediation-2026-10-04/baseline-source.tar.gz`; `BASELINE.json` records every content hash and the archive hash. Existing research archives and original result bundles remain intact. A same-disk copy does not protect against disk failure: copy the source archive and permitted research artifacts to a separately controlled backup location. No cloud transfer is performed by these commands.

Git integration remains a separate authorized action. Do not delete archived sources or raw evidence merely because source commits or tags become available. A tag does not preserve ignored datasets, result bundles, source licenses or the applicable Python runtime.
