# REF-218 Swallowed Exception Review

Date: 2026-07-22
Source finding: `mediator/integrations/graph_tools.py:154`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-218-codebase-scan-b6c5f32da80a.md`

## Decision

Unsatisfied-requirement extraction is an optional graph-reranking enhancement.
Failure should not make retrieval unavailable because claim-readiness context and
the rest of the graph can still produce a useful result. The flagged handler was
nevertheless defective because it silently hid provider and parsing failures,
making degraded reranking indistinguishable from a graph with no missing
requirements.

The fallback now emits a warning with the original exception context and
continues without requirement-derived priority terms. Requirement parsing is
also atomic: malformed data encountered after valid entries can no longer leak
partially parsed terms into reranking. Independently parsed claim-readiness
values and terms remain available.

## Focused Validation

`tests/test_ref_218_unsatisfied_requirements_fallback.py` verifies that a
requirement-provider failure remains non-fatal, retains claim-readiness context,
and records the original exception. It also verifies that a failure after
partial requirement parsing discards the entire partial result without
discarding valid readiness context.

Required syntax validation:

```text
python3 -m py_compile mediator/integrations/graph_tools.py
```

Validation results:

- PASS — `python3 -m py_compile mediator/integrations/graph_tools.py`
- PASS — `python3 -m pytest tests/test_ref_218_unsatisfied_requirements_fallback.py tests/test_ref_217_graph_readiness_fallback.py tests/test_graph_phase2_integration.py -q`
  (15 passed)
- PASS — `python3 -m pytest tests/test_search_hooks.py tests/test_web_evidence_hooks.py -q`
  (59 passed, 2 unrelated deprecation warnings)
