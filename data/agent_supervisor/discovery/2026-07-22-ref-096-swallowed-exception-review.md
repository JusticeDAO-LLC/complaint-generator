# REF-096 Swallowed Exception Review

Date: 2026-07-22
Source finding: `document_optimization.py:4355`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-096-codebase-scan-6d722b95b86a.md`

## Decision

The document builder's requested-relief extractor is an optional enrichment used
by the optimizer's fallback actor payload. An extractor failure should not abort
document optimization because existing relief and deterministic claim-based
defaults can still produce a useful payload.

The recovery boundary is therefore retained, but the failure is no longer
silent. It now logs a warning with traceback information before continuing to
claim-derived fallback relief. The log intentionally omits support text because
that content can contain sensitive complaint facts.

## Focused Validation

`test_requested_relief_extraction_failure_is_logged_and_uses_claim_fallback`
injects a failing builder extractor and verifies both the deterministic
retaliation-relief fallback and a warning containing the original exception.

Required syntax validation:

```text
python3 -m py_compile document_optimization.py
```
