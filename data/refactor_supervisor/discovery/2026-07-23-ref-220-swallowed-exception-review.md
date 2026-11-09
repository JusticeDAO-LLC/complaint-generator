# REF-220 Swallowed Exception Review

Date: 2026-07-23
Source finding: `mediator/integrations/graph_tools.py:209`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-220-codebase-scan-3781a2e00c21.md`

## Decision

Knowledge-graph term extraction is one optional source for graph-aware retrieval
reranking. A provider or malformed entity can fail while dependency-graph and
legal-graph terms remain usable, so continuing with those sources is the correct
availability behavior. The flagged handler was nevertheless defective because
it silently concealed the failure, making degraded reranking indistinguishable
from a knowledge graph with no relevant entities.

The fallback now emits a warning with the original exception context before
continuing with the other graph sources. Knowledge-graph extraction is also
atomic: an error after some entities have been parsed discards that source's
partial terms so reranking does not consume an incomplete, internally
inconsistent view of the knowledge graph.

## Focused Validation

`tests/test_ref_220_knowledge_graph_terms_fallback.py` verifies that a
knowledge-graph provider failure remains non-fatal, retains independently
available dependency-graph terms, and records the original exception. It also
verifies that a failure after partial extraction discards all partial
knowledge-graph terms.

Required syntax validation:

```text
python3 -m py_compile mediator/integrations/graph_tools.py
```

Validation results:

- PASS — `python3 -m py_compile mediator/integrations/graph_tools.py`
- PASS — `python3 -m pytest tests/test_ref_220_knowledge_graph_terms_fallback.py tests/test_ref_219_graph_type_import_fallback.py tests/test_ref_218_unsatisfied_requirements_fallback.py tests/test_ref_217_graph_readiness_fallback.py tests/test_graph_phase2_integration.py -q`
  (19 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
- PASS — `python3 -m pytest tests/test_search_hooks.py tests/test_web_evidence_hooks.py -q`
  (59 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
