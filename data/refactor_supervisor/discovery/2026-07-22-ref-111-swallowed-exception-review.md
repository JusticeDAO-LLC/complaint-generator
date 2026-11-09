# REF-111 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_multi_run_autopatch.py:972`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-111-codebase-scan-36cf294a133f.md`

## Decision

The flagged helper loads `progress.json` before selecting the run and stage from
which an autopatch orchestration should resume. A missing file is expected for a
new orchestration and should continue to produce an empty initial state. An
existing malformed, unreadable, or non-object file indicates corrupt progress
state and must not be treated as if the orchestration had never run: doing so can
repeat expensive batches or attempt to apply a patch more than once.

The loader now catches only `FileNotFoundError`. JSON decoding and filesystem
errors propagate for diagnosis, and a decoded non-object value raises a
path-specific `ValueError` instead of silently becoming an empty mapping. This
keeps the fresh-run behavior while making unsafe resume-state failures visible.

## Focused Validation

`tests/test_codex_multi_run_autopatch_progress.py` covers missing and valid state,
rejects non-object and malformed JSON, and verifies that unexpected read errors
are no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_multi_run_autopatch.py
```
