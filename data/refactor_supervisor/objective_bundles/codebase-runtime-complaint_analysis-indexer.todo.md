# Codebase Bundle: codebase/runtime/complaint_analysis-indexer

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-084 Replace placeholder runtime path in complaint_analysis/indexer.py:231

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on:
- Outputs: data/agent_supervisor/discovery, complaint_analysis/indexer.py
- Validation: python3 -m py_compile complaint_analysis/indexer.py
- Bundle: codebase/runtime/complaint_analysis-indexer
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-complaint_analysis-indexer.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/complaint_analysis-indexer
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: complaint_analysis/indexer.py
- AST symbols: __init__, _calculate_relevance, _extract_keywords, _tag_applicability, applicability distribution, applicability_distribution, average legal provisions, average relevance score, average_legal_provisions, average_relevance_score, calculate relevance, datetime, datetime datetime, datetime.datetime, documents by applicability, documents by risk level, documents with embeddings, documents_by_applicability, documents_by_risk_level, documents_with_embeddings, extract keywords, get statistics, get_statistics, high risk documents percentage, high_risk_documents_percentage, hybriddocumentindexer, hybriddocumentindexer applicability distribution, hybriddocumentindexer average legal provisions, hybriddocumentindexer average relevance score, hybriddocumentindexer calculate relevance, hybriddocumentindexer documents by applicability, hybriddocumentindexer documents by risk level, hybriddocumentindexer documents with embeddings, hybriddocumentindexer extract keywords, hybriddocumentindexer get statistics, hybriddocumentindexer high risk documents percentage, hybriddocumentindexer index document, hybriddocumentindexer init, hybriddocumentindexer maximum relevance score, hybriddocumentindexer risk level distribution, hybriddocumentindexer search, hybriddocumentindexer tag applicability, hybriddocumentindexer total indexed documents, hybriddocumentindexer.__init__, hybriddocumentindexer._calculate_relevance, hybriddocumentindexer._extract_keywords, hybriddocumentindexer._tag_applicability, hybriddocumentindexer.applicability_distribution, hybriddocumentindexer.average_legal_provisions, hybriddocumentindexer.average_relevance_score, hybriddocumentindexer.documents_by_applicability, hybriddocumentindexer.documents_by_risk_level, hybriddocumentindexer.documents_with_embeddings, hybriddocumentindexer.get_statistics, hybriddocumentindexer.high_risk_documents_percentage, hybriddocumentindexer.index_document, hybriddocumentindexer.maximum_relevance_score, hybriddocumentindexer.risk_level_distribution, hybriddocumentindexer.search, hybriddocumentindexer.total_indexed_documents, index document, index_document, init, integrations ipfs datasets vector store, integrations ipfs datasets vector store embeddings available, integrations ipfs datasets vector store embeddingsrouter, integrations.ipfs_datasets.vector_store, integrations.ipfs_datasets.vector_store.embeddings_available, integrations.ipfs_datasets.vector_store.embeddingsrouter, keywords, keywords get keywords, keywords get type specific keywords, keywords.get_keywords, keywords.get_type_specific_keywords, legal patterns, legal patterns legalpatternextractor, legal_patterns, legal_patterns.legalpatternextractor, logging, maximum relevance score
- Goal id: codebase/runtime/complaint_analysis-indexer
- Missing evidence: Replace placeholder runtime path in complaint_analysis/indexer.py:231
- Merge key: codebase/runtime/complaint_analysis-indexer
- Merge family: complaint_analysis/indexer.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Todo vector key: 12fef95f050ba8c9
- Acceptance: Codebase scan filed this finding from complaint_analysis/indexer.py:231. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-084-codebase-scan-12fef95f050b.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-091 Replace placeholder runtime path in complaint_analysis/indexer.py:231

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on:
- Outputs: data/refactor_supervisor/discovery, complaint_analysis/indexer.py
- Validation: python3 -m py_compile complaint_analysis/indexer.py
- Bundle: codebase/runtime/complaint_analysis-indexer
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-complaint_analysis-indexer.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/complaint_analysis-indexer
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: complaint_analysis/indexer.py
- AST symbols: __init__, _calculate_relevance, _extract_keywords, _tag_applicability, applicability distribution, applicability_distribution, average legal provisions, average relevance score, average_legal_provisions, average_relevance_score, calculate relevance, datetime, datetime datetime, datetime.datetime, documents by applicability, documents by risk level, documents with embeddings, documents_by_applicability, documents_by_risk_level, documents_with_embeddings, extract keywords, get statistics, get_statistics, high risk documents percentage, high_risk_documents_percentage, hybriddocumentindexer, hybriddocumentindexer applicability distribution, hybriddocumentindexer average legal provisions, hybriddocumentindexer average relevance score, hybriddocumentindexer calculate relevance, hybriddocumentindexer documents by applicability, hybriddocumentindexer documents by risk level, hybriddocumentindexer documents with embeddings, hybriddocumentindexer extract keywords, hybriddocumentindexer get statistics, hybriddocumentindexer high risk documents percentage, hybriddocumentindexer index document, hybriddocumentindexer init, hybriddocumentindexer maximum relevance score, hybriddocumentindexer risk level distribution, hybriddocumentindexer search, hybriddocumentindexer tag applicability, hybriddocumentindexer total indexed documents, hybriddocumentindexer.__init__, hybriddocumentindexer._calculate_relevance, hybriddocumentindexer._extract_keywords, hybriddocumentindexer._tag_applicability, hybriddocumentindexer.applicability_distribution, hybriddocumentindexer.average_legal_provisions, hybriddocumentindexer.average_relevance_score, hybriddocumentindexer.documents_by_applicability, hybriddocumentindexer.documents_by_risk_level, hybriddocumentindexer.documents_with_embeddings, hybriddocumentindexer.get_statistics, hybriddocumentindexer.high_risk_documents_percentage, hybriddocumentindexer.index_document, hybriddocumentindexer.maximum_relevance_score, hybriddocumentindexer.risk_level_distribution, hybriddocumentindexer.search, hybriddocumentindexer.total_indexed_documents, index document, index_document, init, integrations ipfs datasets vector store, integrations ipfs datasets vector store embeddings available, integrations ipfs datasets vector store embeddingsrouter, integrations.ipfs_datasets.vector_store, integrations.ipfs_datasets.vector_store.embeddings_available, integrations.ipfs_datasets.vector_store.embeddingsrouter, keywords, keywords get keywords, keywords get type specific keywords, keywords.get_keywords, keywords.get_type_specific_keywords, legal patterns, legal patterns legalpatternextractor, legal_patterns, legal_patterns.legalpatternextractor, logging, maximum relevance score
- Goal id: codebase/runtime/complaint_analysis-indexer
- Missing evidence: Replace placeholder runtime path in complaint_analysis/indexer.py:231
- Merge key: codebase/runtime/complaint_analysis-indexer
- Merge family: complaint_analysis/indexer.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 12fef95f050ba8c9
- Acceptance: Codebase scan filed this finding from complaint_analysis/indexer.py:231. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-091-codebase-scan-12fef95f050b.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
