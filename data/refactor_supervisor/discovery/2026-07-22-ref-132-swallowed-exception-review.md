# REF-132 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/storage.py:218`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-132-codebase-scan-3f2581f03aaa.md`

## Decision

The runtime probe may replace a missing Kubo command with a repository-local
Kubo binary. The backend's `_cmd` attribute is the command used by subsequent
subprocess calls, so successfully updating it is required before the probe can
report that backend as available. The broad exception handler was a defect: if
the backend rejected the update, the handler discarded the error and reported
availability even though operations would continue using the missing command.

The probe now converts an assignment failure into its existing structured
`unavailable` result. The diagnostic retains the backend identity, discovered
command, exception type, and exception message. Storage operations therefore
degrade before calling the router instead of attempting work through a backend
whose command could not be configured.

## Focused Validation

`tests/test_ref_132_storage_kubo_probe.py` verifies that an immutable
Kubo-shaped backend produces an observable unavailable status with the original
failure details. It also verifies that `store_bytes` does not call the router
after the probe fails.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/storage.py
```

Validation results:

- PASS — `python3 -m py_compile integrations/ipfs_datasets/storage.py`
- PASS — `python3 -m pytest tests/test_ref_132_storage_kubo_probe.py -q`
  (2 passed)
- PASS — focused existing storage adapter regression cases in
  `tests/test_ipfs_adapter_layer.py` (5 passed)
