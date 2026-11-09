# Objective Bundle: refactor/g11/g11-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-248: REF-248 Compile candidate diffs into typed AST proof scopes

## REF-248 Compile candidate diffs into typed AST proof scopes

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-245
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/code_proof_obligations.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_proof_scopes.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_proof_scopes.py -q
- Bundle: refactor/g11/g11-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S2
- Missing evidence: Proof planning must start from deterministic changed symbols and contracts rather than sending repository-wide source or AST records to a model.
- AST symbols: PROOF_SCOPE_SCHEMA, PROOF_SCOPE_SET_SCHEMA, CODE_OBLIGATION_REQUEST_SCHEMA, CODE_OBLIGATION_CACHE_KEY_SCHEMA, DiffChangeKind, ProofScopeKind, ProofScopeType, CandidateChangeKind, _sha256_source, _enum_change_kind, CandidateDiffEntry, CodeProofScope, ASTProofScope, TypedASTProofScope, ProofScopeCompilationStats, CodeProofScopeSet, CompiledProofScopes, ProofScopeSet, ProofScopeCompilation, CandidateFileDiff, CodeObligationRequest, CodeProofObligationRequest, ProofObligationRequest, _selected_obligation_scopes, materialize_code_proof_obligation, build_code_proof_obligation, obligation_cache_identity, code_proof_obligation_cache_identity, build_obligation_cache_key, _module_name
- Merge key: refactor/g11/g11-s2
- Candidate kind: seed
- Todo vector key: ref-248-compilecandidatediffsintotypedastproofscopes
- Acceptance: Python diffs produce qualified symbols, imports, calls, state transitions, interfaces, source hashes, and changed-path scopes.; Renames, deletes, generated files, syntax failures, and non-Python changes have explicit conservative handling.; Scopes reuse existing AST and conflict-graph records by blob identity.; Equivalent cold and warm scans produce the same canonical scope identities.

- [x] Task checkbox-249: REF-249 Build a reviewed code-invariant obligation template registry

## REF-249 Build a reviewed code-invariant obligation template registry

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-247, REF-248
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_obligation_templates.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/code_proof_obligations.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_obligation_templates.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_obligation_templates.py -q
- Bundle: refactor/g11/g11-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S2
- Missing evidence: Arbitrary Python cannot be made formally verified by translating free-form model claims; enforcement needs reviewed templates with explicit semantics.
- AST symbols: PROOF_OBLIGATION_TEMPLATE_SCHEMA, PROOF_OBLIGATION_TEMPLATE_REGISTRY_SCHEMA, TEMPLATE_REGISTRY_VERSION, TemplateValidationError, UnsupportedProofTemplateError, AmbiguousProofTemplateError, TemplateSelectionStatus, ReviewedCodeShape, ReferencePredicate, _strings, _strict_mapping, _predicate_semantics, _mapping_rows, legal_state_transition, lease_uniqueness_and_fencing, dag_is_acyclic, merge_is_idempotent, cache_key_is_complete, evidence_is_fresh, projection_is_equivalent, unsupported_proof_fails_closed, TemplateMutationCase, MutationCase, ProofObligationTemplate, ObligationTemplate, CodeProofObligationTemplate, TemplateSelection, ProofObligationTemplateRegistry, TemplateRegistry, _case
- Merge key: refactor/g11/g11-s2
- Candidate kind: seed
- Todo vector key: ref-249-buildareviewedcode-invariantobligationtemplatere
- Acceptance: Initial templates cover legal state transitions, lease uniqueness and fencing, DAG acyclicity, merge idempotence, cache-key completeness, evidence freshness, projection equivalence, and unsupported-proof fail-closed behavior.; Every template declares a Python reference predicate, canonical statement, supported backends, assumptions, mutation cases, and fallback tests.; Template versions and semantic hashes participate in obligation and cache identity.; Unknown or ambiguous code shapes remain unsupported instead of selecting a similar template heuristically.

- [x] Task checkbox-250: REF-250 Materialize a deterministic code and proof evidence graph in JSON and DuckDB

## REF-250 Materialize a deterministic code and proof evidence graph in JSON and DuckDB

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-245, REF-248
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/code_evidence_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/artifact_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_evidence_graph.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_evidence_graph.py -q
- Bundle: refactor/g11/g11-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S2
- Missing evidence: Goals, tasks, symbols, obligations, attempts, receipts, validations, and merges need a query plane that does not require parsing a full graph into a model context.
- AST symbols: CODE_EVIDENCE_GRAPH_SCHEMA, CODE_EVIDENCE_NODE_SCHEMA, CODE_EVIDENCE_EDGE_SCHEMA, EvidenceGraphValidationError, EvidenceNodeKind, EvidenceEdgeKind, EvidenceProvenance, ENRICHMENT_EDGE_KINDS, UNTRUSTED_PROVENANCE, _canonical_value, canonical_json, _identity, _record, _text, _strings, _enum, EvidenceNode, ProvenanceEdge, CodeEvidenceGraph, CodeEvidenceNode, CodeEvidenceEdge, EvidenceGraph, _GraphBuilder, _record_key, _task_id, _tree_id, _successful, _freshness, _add_tree, _ingest_tasks
- Merge key: refactor/g11/g11-s2
- Candidate kind: seed
- Todo vector key: ref-250-materializeadeterministiccodeandproofevidencegra
- Acceptance: The graph uses deterministic nodes and provenance edges derived from AST, task, validation, merge, and proof records.; Paired JSON and DuckDB artifacts expose indexed task, tree, symbol, obligation, assurance, freshness, and dependency queries.; JSON and DuckDB projections round-trip to equivalent canonical graph records.; LLM or GraphRAG enrichment cannot create authoritative proof, merge, coverage, or completion edges.

- [x] Task checkbox-251: REF-251 Index proof scopes and invalidate stale dependent evidence incrementally

## REF-251 Index proof scopes and invalidate stale dependent evidence incrementally

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-248, REF-250
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_scope_index.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scope_index.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scope_index.py -q
- Bundle: refactor/g11/g11-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S2
- Missing evidence: Proof reuse is useful only when every changed semantic input invalidates the affected obligations and receipts.
- AST symbols: PROOF_SCOPE_INDEX_SCHEMA_VERSION, PROOF_SCOPE_INDEX_SCHEMA, PROOF_INVALIDATION_EVENT_SCHEMA_VERSION, PROOF_INVALIDATION_EVENT_SCHEMA, DEFAULT_MAX_INVALIDATION_REASON_CHAIN, ProofScopeIndexError, ProofInputKind, ScopeKind, ProofScopeDimension, _canonical, _canonical_json, _identity, _repo_path, _strings, _record, _first, _many, _metadata, ProofScopeKey, IndexedScopeRecord, ProofScopeBlobRecord, IndexedObligation, IndexedReceipt, InvalidationRecord, ProofCriterionBinding, ProofInvalidationEdge, ProofReplacementTask, _strings_preserving_order, ScopeDependents, ProofScopeIndexStats
- Merge key: refactor/g11/g11-s2
- Candidate kind: seed
- Todo vector key: ref-251-indexproofscopesandinvalidatestaledependentevide
- Acceptance: Scope indexes map files, qualified symbols, interfaces, assumptions, templates, toolchains, and policies to dependent obligations and receipts.; Blob reuse avoids reparsing unchanged scopes while deletes and renames invalidate stale records.; Invalidation is transitive across proof-plan dependencies and records a bounded reason chain.; Incremental and exhaustive rebuilds produce equivalent active evidence sets.

- [x] Task checkbox-252: REF-252 Generate bounded proof context capsules for Codex and Leanstral

## REF-252 Generate bounded proof context capsules for Codex and Leanstral

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-249, REF-250, REF-251
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_context.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/artifact_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_context.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_context.py -q
- Bundle: refactor/g11/g11-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S2
- Missing evidence: Models should receive only task-relevant invariants, trusted prior evidence, counterexamples, and source excerpts.
- AST symbols: PROOF_CONTEXT_CAPSULE_SCHEMA, PROOF_CONTEXT_QUERY_SCHEMA, PROOF_CONTEXT_LIMITS_SCHEMA, PROOF_PLANNING_CONTEXT_CAPSULE_SCHEMA, PROOF_PLANNING_CONTEXT_LIMITS_SCHEMA, LEANSTRAL_FIXED_THEOREM_SCHEMA, LEANSTRAL_PROOF_CONTEXT_SCHEMA, LEANSTRAL_PROOF_OUTPUT_SCHEMA, LEANSTRAL_PROMPT_LIMITS_SCHEMA, DEFAULT_MAX_CONTEXT_ROWS, DEFAULT_MAX_CONTEXT_BYTES, DEFAULT_MAX_CONTEXT_TOKENS, DEFAULT_MAX_GRAPH_HOPS, DEFAULT_MAX_SOURCE_EXCERPTS, DEFAULT_MAX_SOURCE_EXCERPT_BYTES, DEFAULT_MAX_SOURCE_BYTES, DEFAULT_MAX_PROOF_TRANSCRIPTS, DEFAULT_MAX_PROOF_TRANSCRIPT_BYTES, DEFAULT_MAX_PROOF_TRANSCRIPT_BYTES_TOTAL, DEFAULT_MAX_PLANNING_CANDIDATES, DEFAULT_MAX_PLANNING_OBLIGATIONS, DEFAULT_MAX_REJECTED_ALTERNATIVES, DEFAULT_MAX_REJECTION_RATIONALE_BYTES, DEFAULT_MAX_PLANNING_DEPENDENCIES, DEFAULT_MAX_PLANNING_RESOURCE_CLASSES, DEFAULT_MAX_PLANNING_CONTEXT_BYTES, DEFAULT_MAX_PLANNING_CONTEXT_TOKENS, DEFAULT_MAX_LEANSTRAL_PREMISES, DEFAULT_MAX_LEANSTRAL_TRUSTED_RECEIPTS, DEFAULT_MAX_LEANSTRAL_FAILURES
- Merge key: refactor/g11/g11-s2
- Candidate kind: seed
- Todo vector key: ref-252-generateboundedproofcontextcapsulesforcodexandle
- Acceptance: Context queries select exact task, symbol, dependency, obligation, receipt, and contradiction neighborhoods.; Row, byte, token, graph-hop, source-excerpt, and proof-transcript limits are enforced before prompt assembly.; Capsules distinguish trusted facts, untrusted suggestions, unsupported semantics, and required fallback checks.; Repository-wide AST records, full graphs, hidden witnesses, and unrelated transcripts never enter a capsule.
