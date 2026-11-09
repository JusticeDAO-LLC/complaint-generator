# REF-221 Swallowed Exception Review

Date: 2026-07-22
Source finding: `mediator/integrations/graph_tools.py:223`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-221-codebase-scan-2986b4a153d9.md`

## Decision

Dependency-graph terms are an optional input to graph-aware retrieval
reranking. A dependency-graph provider or malformed graph node should not make
retrieval unavailable because knowledge-graph and legal-graph terms can still
produce useful ranking context. The flagged handler was defective because it
silently concealed provider and parsing failures, making degraded reranking
indistinguishable from a dependency graph with no claim nodes.

The fallback now emits a warning with the original exception context and
continues without dependency-graph terms. Dependency-node parsing is also
atomic: malformed data encountered after valid nodes can no longer leak a
partial dependency-graph result into ranking. Terms extracted independently
from the other graph sources remain available.

## Focused Validation

`tests/test_ref_221_dependency_graph_terms_fallback.py` verifies that a
dependency-graph provider failure remains non-fatal, retains terms from another
graph source, and records the original exception. It also verifies that a
failure after partial dependency-node parsing discards the entire partial
result.

Required syntax validation:

```text
python3 -m py_compile mediator/integrations/graph_tools.py
```

Validation results:

- PASS — `python3 -m py_compile mediator/integrations/graph_tools.py`
- PASS — `python3 -m pytest tests/test_ref_221_dependency_graph_terms_fallback.py -q`
  (2 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
- PASS — `python3 -m pytest tests/test_graph_phase2_integration.py tests/test_search_hooks.py tests/test_web_evidence_hooks.py -q`
  (70 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
