# REF-108 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:1674`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-108-codebase-scan-98dd4c65d363.md`

## Decision

Codex tool and final responses are untrusted model output, so syntactically
malformed JSON is an expected per-response parse miss. `json.loads` reports that
condition with `json.JSONDecodeError`, and the helper should continue returning
`None` so callers can inspect the response as a raw patch or request a corrected
response.

The broad `Exception` handler also concealed unexpected decoder and runtime
failures, making internal defects indistinguishable from malformed model output.
The handler now catches only `json.JSONDecodeError`, preserving tolerant handling
of invalid responses while allowing unexpected failures to propagate for
diagnosis.

## Focused Validation

`tests/test_codex_autopatch_json_parsing.py` verifies that malformed direct and
trailing JSON remains non-fatal, that a valid trailing object is recovered, and
that an unexpected decoder failure is no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
