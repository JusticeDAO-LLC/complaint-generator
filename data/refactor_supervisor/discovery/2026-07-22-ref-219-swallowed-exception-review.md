# REF-219 Swallowed Exception Review

Date: 2026-07-22
Source finding: `mediator/integrations/graph_tools.py:187`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-219-codebase-scan-35764e294944.md`

## Decision

Graph-aware reranking is an optional retrieval enhancement, so an unavailable
`complaint_phases` import should continue to produce an empty graph-term set
rather than making retrieval fail. The flagged handler was defective because it
silently concealed the import failure and caught every `Exception`, including
unrelated faults raised while initializing the module.

The fallback now catches only `ImportError` and emits a warning with the
original exception context before returning no graph terms. Other initialization
errors propagate to the caller so programming defects and corrupted runtime
state remain visible instead of being misreported as an unavailable enhancement.

## Focused Validation

`tests/test_ref_219_graph_type_import_fallback.py` verifies that an unavailable
graph-types import remains non-fatal and records the original exception. It also
verifies that a non-import error raised during module initialization is not
swallowed.

Required syntax validation:

```text
python3 -m py_compile mediator/integrations/graph_tools.py
```

Validation results:

- PASS — `python3 -m py_compile mediator/integrations/graph_tools.py`
- PASS — `python3 -m pytest tests/test_ref_219_graph_type_import_fallback.py tests/test_ref_218_unsatisfied_requirements_fallback.py tests/test_ref_217_graph_readiness_fallback.py tests/test_graph_phase2_integration.py -q`
  (17 passed)
- PASS — `python3 -m pytest tests/test_search_hooks.py tests/test_web_evidence_hooks.py -q`
  (59 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
