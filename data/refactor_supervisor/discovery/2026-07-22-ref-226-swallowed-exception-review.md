# REF-226 Swallowed Exception Review

Date: 2026-07-22
Source finding: `mediator/web_evidence_hooks.py:498`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-226-codebase-scan-1296d7ba66dc.md`

## Decision

LLM relevance assessment is intentionally optional. When it is unavailable,
`validate_evidence` must retain the deterministic score assigned from the
evidence source so that evidence discovery remains usable. The flagged handler
was defective because it silently discarded backend, response, and score
parsing failures, leaving operators unable to distinguish a successful default
score from a degraded assessment.

The fallback behavior is preserved, but failures now emit the structured
`web_evidence_relevance_assessment_error` event. The event records the exception
type and message, evidence source and URL, and the fallback score returned to the
caller.

## Focused Validation

`tests/test_ref_226_web_evidence_validation.py` verifies that a backend failure
is observable and that validation still returns the expected source-based score
without adding a fabricated LLM recommendation.

Required syntax validation:

```text
python3 -m py_compile mediator/web_evidence_hooks.py
```

Validation results:

- PASS — `python3 -m py_compile mediator/web_evidence_hooks.py`
- PASS — `python3 -m pytest tests/test_ref_226_web_evidence_validation.py -q`
  (1 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
- PASS — `python3 -m pytest tests/test_web_evidence_hooks.py -q`
  (31 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
