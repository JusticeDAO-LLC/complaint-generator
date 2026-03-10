# IPFS Datasets Py Capability Matrix

Date: 2026-03-10

Validated against submodule commit:

- `ipfs_datasets_py`: `eed7a60f307225848d892ae6bf06b513c6cbb784`

## Purpose

This matrix maps the actual `ipfs_datasets_py` package layout to complaint-generator integration targets. It is a companion to `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md` and replaces older assumptions that some features lived under flatter package names.

## Key Findings

### 1. Web archiving exports differ from older complaint-generator docs

Validated package:

- `ipfs_datasets_py.web_archiving`

Current canonical exports include:

- `BraveSearchAPI`
- `search_google`
- `search_wayback_machine`
- `archive_to_wayback`
- `search_archive_is`
- `search_ipwb_archive`

Important implication:

- complaint-generator currently references `BraveSearchClient` and `CommonCrawlSearchEngine` in older docs and hook code
- the current stable `web_archiving/__init__.py` exports `BraveSearchAPI`
- Common Crawl support exists, but it is not exported from `web_archiving/__init__.py`; it is vendored as a nested submodule under `ipfs_datasets_py/ipfs_datasets_py/web_archiving/common_crawl_search_engine`

### 2. Legal scraper APIs are async and live under `processors/legal_scrapers`

Validated modules:

- `ipfs_datasets_py.processors.legal_scrapers.us_code_scraper`
- `ipfs_datasets_py.processors.legal_scrapers.federal_register_scraper`
- `ipfs_datasets_py.processors.legal_scrapers.recap_archive_scraper`

Validated async entrypoints:

- `search_us_code(...)`
- `search_federal_register(...)`
- `search_recap_documents(...)`

Important implication:

- complaint-generator currently imports these as if they were sync functions from `ipfs_datasets_py.legal_scrapers`
- the adapter layer should expose sync wrappers or move mediator flows to async execution

### 3. Knowledge graph root imports are deprecated

Validated package:

- `ipfs_datasets_py.knowledge_graphs`

Validated guidance from package:

- prefer subpackages such as:
  - `ipfs_datasets_py.knowledge_graphs.extraction`
  - `ipfs_datasets_py.knowledge_graphs.query`
  - `ipfs_datasets_py.knowledge_graphs.cypher`
  - `ipfs_datasets_py.knowledge_graphs.neo4j_compat`
  - `ipfs_datasets_py.knowledge_graphs.storage`

Important implication:

- complaint-generator should not target deprecated root exports for graph operations
- the adapter layer should bind to stable subpackages only

### 4. IPFS storage entrypoint is stable

Validated module:

- `ipfs_datasets_py.ipfs_backend_router`

Observed behavior:

- stable backend router with pluggable strategy
- fallback to Kubo CLI by default
- optional enablement of `ipfs_accelerate_py` and `ipfs_kit_py`

Important implication:

- this is the correct storage entrypoint for complaint-generator
- current evidence hook usage is directionally correct, but should be centralized behind an adapter

### 5. GraphRAG optimizer stack is real and extensive

Validated package:

- `ipfs_datasets_py.optimizers.graphrag`

Validated exports and modules include:

- `OntologyGenerator`
- `OntologyCritic`
- `LogicValidator`
- `OntologyMediator`
- `OntologyOptimizer`
- `OntologySession`
- `OntologyHarness`
- `OntologyPipeline`
- `ontology_pipeline.py`
- `logic_validator.py`

Important implication:

- this is a strong candidate for ontology extraction, support scoring, and graph quality analysis in complaint-generator
- it is better suited for graph refinement and coverage analysis than for direct legal authority scraping

### 6. Logic and theorem-proving stack is substantial

Validated packages and modules include:

- `ipfs_datasets_py.logic.fol`
- `ipfs_datasets_py.logic.deontic`
- `ipfs_datasets_py.logic.TDFOL`
- `ipfs_datasets_py.logic.external_provers.smt.z3_prover_bridge`
- `ipfs_datasets_py.logic.external_provers.smt.cvc5_prover_bridge`
- `ipfs_datasets_py.logic.external_provers.interactive.lean_prover_bridge`
- `ipfs_datasets_py.logic.external_provers.interactive.coq_prover_bridge`
- `ipfs_datasets_py.logic.integration.neurosymbolic`
- `ipfs_datasets_py.logic.integration.symbolic.neurosymbolic.reasoning_coordinator`

Important implication:

- complaint-generator can target concrete proof and validation workflows, not just abstract “theorem prover” ideas
- the adapter should distinguish between:
  - text-to-logic conversion
  - deontic translation for legal rules
  - proof execution
  - hybrid neuro-symbolic reasoning

## Capability Mapping

| Capability | Validated Module(s) | Recommended Adapter | Complaint Generator Consumer |
|---|---|---|---|
| LLM routing | `ipfs_datasets_py.llm_router` | `integrations.ipfs_datasets.llm` | `backends/llm_router_backend.py` |
| IPFS storage | `ipfs_datasets_py.ipfs_backend_router` | `integrations.ipfs_datasets.storage` | `mediator/evidence_hooks.py` |
| Web search | `ipfs_datasets_py.web_archiving` | `integrations.ipfs_datasets.search` | `mediator/web_evidence_hooks.py` |
| Common Crawl | nested `web_archiving/common_crawl_search_engine` | `integrations.ipfs_datasets.search` | `mediator/web_evidence_hooks.py`, `mediator/legal_authority_hooks.py` |
| Legal scrapers | `ipfs_datasets_py.processors.legal_scrapers.*` | `integrations.ipfs_datasets.legal` | `mediator/legal_authority_hooks.py` |
| Knowledge graph extraction | `ipfs_datasets_py.knowledge_graphs.extraction` | `integrations.ipfs_datasets.graphs` | `complaint_phases/knowledge_graph.py` |
| Hybrid graph query | `ipfs_datasets_py.knowledge_graphs.query` | `integrations.ipfs_datasets.graphs` | `complaint_phases/dependency_graph.py`, future retrieval APIs |
| Graph storage / IPLD | `ipfs_datasets_py.knowledge_graphs.storage` | `integrations.ipfs_datasets.graphs` | graph persistence pipeline |
| GraphRAG optimization | `ipfs_datasets_py.optimizers.graphrag` | `integrations.ipfs_datasets.graphrag` | coverage scoring, ontology extraction, validation |
| FOL translation | `ipfs_datasets_py.logic.fol` | `integrations.ipfs_datasets.logic` | formal claim-element support |
| Deontic translation | `ipfs_datasets_py.logic.deontic` | `integrations.ipfs_datasets.logic` | legal obligation / permission modeling |
| TDFOL proving | `ipfs_datasets_py.logic.TDFOL` | `integrations.ipfs_datasets.logic` | proof and contradiction checks |
| External provers | `ipfs_datasets_py.logic.external_provers.*` | `integrations.ipfs_datasets.logic` | optional formal validation tier |
| Neuro-symbolic reasoning | `ipfs_datasets_py.logic.integration.*` | `integrations.ipfs_datasets.logic` | `complaint_phases/neurosymbolic_matcher.py` |

## Recommended Adapter Contracts

### `integrations.ipfs_datasets.storage`

Should expose:

- `store_bytes(data, pin=True) -> ArtifactStoreResult`
- `retrieve_bytes(cid) -> bytes`
- `pin(cid) -> None`
- `backend_status() -> StorageCapability`

Backed by:

- `ipfs_datasets_py.ipfs_backend_router`

### `integrations.ipfs_datasets.search`

Should expose:

- `search_current_web(query, limit) -> list[NormalizedSearchResult]`
- `search_archives(query_or_domain, limit) -> list[NormalizedSearchResult]`
- `archive_url(url) -> ArchiveResult`

Backed by:

- `ipfs_datasets_py.web_archiving.BraveSearchAPI`
- `ipfs_datasets_py.web_archiving.search_wayback_machine`
- `ipfs_datasets_py.web_archiving.archive_to_wayback`
- nested Common Crawl engine adapter

### `integrations.ipfs_datasets.legal`

Should expose:

- `search_us_code_sync(...) -> NormalizedAuthorityBatch`
- `search_federal_register_sync(...) -> NormalizedAuthorityBatch`
- `search_recap_sync(...) -> NormalizedAuthorityBatch`
- `search_all_authorities(...) -> AuthoritySearchBundle`

Backed by async internals:

- `ipfs_datasets_py.processors.legal_scrapers.us_code_scraper.search_us_code`
- `ipfs_datasets_py.processors.legal_scrapers.federal_register_scraper.search_federal_register`
- `ipfs_datasets_py.processors.legal_scrapers.recap_archive_scraper.search_recap_documents`

Implementation note:

- the adapter should normalize different return shapes such as `results` vs `documents`
- the adapter must manage async execution explicitly

### `integrations.ipfs_datasets.graphs`

Should expose:

- `extract_graph_from_text(...)`
- `extract_graph_from_document(...)`
- `query_graph_support(...)`
- `persist_graph_snapshot(...)`
- `resolve_cross_document_entities(...)`

Backed by:

- `ipfs_datasets_py.knowledge_graphs.extraction`
- `ipfs_datasets_py.knowledge_graphs.query`
- `ipfs_datasets_py.knowledge_graphs.storage`
- `ipfs_datasets_py.knowledge_graphs.lineage`

### `integrations.ipfs_datasets.graphrag`

Should expose:

- `build_ontology(...)`
- `validate_ontology(...)`
- `score_ontology(...)`
- `run_refinement_cycle(...)`

Backed by:

- `ipfs_datasets_py.optimizers.graphrag.OntologyGenerator`
- `ipfs_datasets_py.optimizers.graphrag.LogicValidator`
- `ipfs_datasets_py.optimizers.graphrag.OntologyMediator`
- `ipfs_datasets_py.optimizers.graphrag.OntologyPipeline`

### `integrations.ipfs_datasets.logic`

Should expose:

- `text_to_fol(...)`
- `legal_text_to_deontic(...)`
- `prove_claim_elements(...)`
- `check_contradictions(...)`
- `run_hybrid_reasoning(...)`

Backed by:

- `ipfs_datasets_py.logic.fol`
- `ipfs_datasets_py.logic.deontic`
- `ipfs_datasets_py.logic.TDFOL`
- `ipfs_datasets_py.logic.external_provers`
- `ipfs_datasets_py.logic.integration`

## Integration Risks Confirmed By Submodule Inspection

### API drift risk is real

Examples:

- complaint-generator docs mention `BraveSearchClient`, but current export is `BraveSearchAPI`
- complaint-generator code assumes sync legal scraper functions, but current functions are async
- root knowledge graph imports are explicitly deprecated by the submodule

Conclusion:

- direct imports from mediator hooks should be treated as technical debt and moved behind adapters immediately

### Return shapes are not uniform

Observed scraper patterns:

- US Code returns `results`
- Federal Register returns `documents`
- RECAP returns `documents`

Conclusion:

- adapter normalization is mandatory before broader feature integration

### Optional and nested dependencies are significant

Observed submodules include:

- `ipfs_accelerate_py`
- `ipfs_kit_py`
- Common Crawl engine
- multiple prover backends

Conclusion:

- capability detection must be explicit and granular
- “submodule present” is not enough; each feature family needs separate readiness checks

## Immediate Refactor Order

1. Create `integrations/ipfs_datasets/loader.py` and `capabilities.py`.
2. Wrap `ipfs_backend_router` in `storage.py`.
3. Wrap web archiving plus Common Crawl in `search.py`.
4. Wrap async legal scrapers in `legal.py` with sync-safe facades.
5. Refactor mediator hooks to import adapters only.
6. Add graph and logic adapters after the import boundary is stable.

## Minimum Compatibility Tests To Add

1. `test_ipfs_adapter_capabilities.py`: verifies capability detection with submodule present.
2. `test_ipfs_adapter_missing_modules.py`: verifies degraded behavior when imports fail.
3. `test_legal_adapter_normalization.py`: verifies normalization across US Code, Federal Register, and RECAP return shapes.
4. `test_search_adapter_exports.py`: verifies current exports such as `BraveSearchAPI` and archive search functions.
5. `test_graph_logic_adapter_smoke.py`: verifies stable subpackage imports without using deprecated roots.

## Recommendation

Use this matrix as the source of truth for implementation. The improvement plan remains the right roadmap, but execution should follow the validated module paths and deprecation guidance captured here.