# REF-114 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_multi_run_autopatch_loop.py:139`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-114-codebase-scan-6b02f453cf79.md`

## Decision

The flagged helper loads the loop's persisted state before deciding its next
iteration and whether an orchestrator can be resumed. A missing file is expected
on the first run and should continue to produce an empty initial state. An
existing malformed, unreadable, or non-object file indicates corrupt state and
must not be treated as a first run: doing so can restart the loop at iteration
one and lose the active orchestrator needed for a safe resume.

The loader now catches only `FileNotFoundError`. JSON decoding, text decoding,
and other filesystem errors propagate for diagnosis, and a decoded non-object
value raises a path-specific `ValueError` instead of silently becoming an empty
mapping. This preserves fresh-run behavior while making unsafe state failures
visible before the loop starts work or overwrites the persisted state.

## Focused Validation

`tests/test_codex_multi_run_autopatch_loop_state.py` covers missing and valid
state, rejects non-object and malformed JSON, and verifies that unexpected read
errors are no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_multi_run_autopatch_loop.py
```
