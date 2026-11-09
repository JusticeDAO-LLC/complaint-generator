# REF-216 Swallowed Exception Review

Date: 2026-07-22
Source finding: `mediator/inquiries.py:446`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-216-codebase-scan-038dc49c2e81.md`

## Decision

Inquiry gap priorities are optional enrichment. A failure in the persisted phase
store must not prevent the mediator from returning the next unanswered inquiry,
so the best-effort fallback remains necessary. The broad handler was a defect
because it silently discarded the phase-store failure and made degraded inquiry
ordering indistinguishable from a valid empty priority summary.

The phase-summary boundary now emits a warning with traceback information and
returns any gap context that was already built. The adjacent optional mediator
gap-context boundary follows the same policy: it logs its failure, falls back to
an empty context, and still attempts to recover persisted intake priorities.
Neither warning message interpolates complaint content or inquiry answers.

## Focused Validation

`tests/test_inquiries.py` verifies both degraded paths. A mediator context-builder
failure is observable while persisted priorities are still recovered, and a
phase-store failure is observable while the successfully built mediator context
is preserved.

Required syntax validation:

```text
python3 -m py_compile mediator/inquiries.py
```

Validation results:

- PASS — `python3 -m py_compile mediator/inquiries.py`
- PASS — `IPFS_ACCEL_SKIP_CORE=1 IPFS_KIT_DISABLE=1 python3 -m pytest tests/test_inquiries.py -q`
  (5 passed)
