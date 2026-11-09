# REF-088 Swallowed Exception Review

Date: 2026-07-22
Source finding: `adversarial_harness/session.py:4284`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-088-codebase-scan-350c07cde027.md`

## Decision

The flagged boundary reads optional evidence and intake snapshots while building
the degraded document packet. These inputs should remain best-effort because the
packet can still be assembled from the seed complaint and conversation history.
The failure must not be silent, however, and a failure reading one snapshot must
not prevent the remaining independent snapshots from being recovered.

The fallback now reads each phase-data input independently and logs failures with
the input key, adversarial session identifier, and traceback. Missing inputs
retain the existing empty-mapping behavior, while invalid non-mapping values are
ignored with a warning so malformed phase state cannot break the fallback path.
Failure to import the phase definitions is also observable while preserving the
seed-and-conversation-only fallback.

## Focused Validation

`test_fallback_document_logs_failed_phase_read_and_recovers_remaining_inputs`
injects a failure for the first phase-data read and verifies that the warning
contains the input, session, and exception while later claim-support and intake
snapshots still contribute to the generated packet.

Required syntax validation:

```text
python3 -m py_compile adversarial_harness/session.py
```
