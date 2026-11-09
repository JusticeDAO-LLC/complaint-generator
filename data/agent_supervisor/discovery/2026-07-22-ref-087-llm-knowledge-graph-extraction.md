# REF-087 LLM Knowledge Graph Extraction

Date: 2026-07-22
Source finding: `complaint_phases/knowledge_graph.py:2168`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-087-codebase-scan-fef985c2cd7e.md`

## Decision

The annotation marked a functional gap. `KnowledgeGraphBuilder` accepted a
mediator and called its LLM hooks, but those hooks always returned empty lists,
so configuring a backend could never enrich a graph.

The hooks now call the repository's synchronous `mediator.query_backend`
contract with strict JSON prompts. Responses may be native JSON values, plain
JSON strings, or Markdown-fenced JSON. Entity candidates are normalized to the
graph's supported types, and relationship candidates must reference existing
entity IDs and use a supported relationship type. Invalid candidates are
discarded, confidence values are clamped, and backend or parsing failures are
logged before the builder continues with its existing rule-based results.

## Focused Validation

`test_knowledge_graph_builder_enriches_graph_from_llm_json` verifies fenced JSON
parsing, entity schema validation, relationship ID validation, and confidence
normalization. `test_knowledge_graph_builder_falls_back_when_llm_backend_fails`
verifies that a backend exception is observable and does not prevent heuristic
graph construction.

Required syntax validation:

```text
python3 -m py_compile complaint_phases/knowledge_graph.py
```
