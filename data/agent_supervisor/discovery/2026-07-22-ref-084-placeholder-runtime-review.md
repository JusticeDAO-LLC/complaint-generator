# REF-084 Placeholder Runtime Review

Date: 2026-07-22
Source finding: `complaint_analysis/indexer.py:231`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-084-codebase-scan-12fef95f050b.md`

## Decision

The flagged `NotImplementedError` was reachable through the public asynchronous
`HybridDocumentIndexer.search()` method after documents had been successfully
indexed. This made the indexer's advertised hybrid-search path fail at runtime.

The placeholder has been replaced with an in-memory hybrid search over indexed
documents. Source complaint text is retained privately rather than added to the
public indexing result. Exact token/phrase relevance is combined with normalized
cosine similarity when compatible embeddings are available, and search degrades
to lexical matching if query embedding generation fails. Results are stable,
scored copies, and filters support top-level fields, explicit dotted fields, and
plain metadata keys.

## Focused Validation

`tests/test_ref_084_indexer_search.py` covers lexical ranking, result immutability,
metadata and applicability filters, synchronous embedding adapters, hybrid score
composition, and invalid arguments.

Required syntax validation:

```text
python3 -m py_compile complaint_analysis/indexer.py
```
