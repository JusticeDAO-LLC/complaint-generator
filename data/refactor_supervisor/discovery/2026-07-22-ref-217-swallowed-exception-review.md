# REF-217 Swallowed Exception Review

Date: 2026-07-22
Source finding: `mediator/integrations/graph_tools.py:133`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-217-codebase-scan-bc9890458816.md`

## Decision

Claim-readiness extraction is an optional reranking enhancement. A dependency
graph implementation can fail while the remaining graph terms and unsatisfied
requirements are still usable, so falling back to neutral readiness is the
correct availability behavior. The flagged handler was nevertheless defective
because it silently concealed the failure, making a degraded reranking result
indistinguishable from a genuinely complete graph.

The fallback now emits a warning with exception context before continuing with
neutral readiness. Readiness parsing is also atomic: malformed claim details can
no longer leak a partially parsed readiness value or priority terms into the
fallback result. Unsatisfied requirements are still collected independently.

## Focused Validation

`tests/test_ref_217_graph_readiness_fallback.py` verifies that a readiness
provider failure remains non-fatal, retains independently available unsatisfied
requirements, and records the original exception. It also verifies that a
failure after partial parsing restores the complete neutral fallback instead of
returning internally inconsistent context.

Required syntax validation:

```text
python3 -m py_compile mediator/integrations/graph_tools.py
```

Validation results:

- PASS — `python3 -m py_compile mediator/integrations/graph_tools.py`
- PASS — `python3 -m pytest tests/test_ref_217_graph_readiness_fallback.py -q`
  (2 passed)
- PASS — `python3 -m pytest tests/test_graph_phase2_integration.py -q`
  (11 passed)
