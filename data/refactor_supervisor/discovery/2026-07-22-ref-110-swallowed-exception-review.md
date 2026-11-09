# REF-110 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:2613`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-110-codebase-scan-74442262a542.md`

## Decision

The flagged handler appends a rate-limit event to the Codex chat transcript
after constructing the primary rate-limit artifact. Transcript persistence is
supplemental: an unavailable or non-encodable transcript must not conceal the
quota or rate-limit outcome that the caller is already handling. Filesystem and
text-encoding failures are therefore expected best-effort failures.

The broad handler silently discarded those failures and also concealed
unexpected defects in event construction and serialization. Optional JSONL
appends now catch only `OSError` and `UnicodeError`, report the failed event and
transcript path on stderr, and return their persistence status. Unexpected
failures propagate for diagnosis.

## Focused Validation

`tests/test_codex_rate_limit_parsing.py` verifies successful transcript
persistence, the visible non-fatal fallback for an expected artifact failure,
and propagation of an unexpected writer failure.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
