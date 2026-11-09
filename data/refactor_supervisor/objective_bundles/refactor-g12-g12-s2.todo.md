# Objective Bundle: refactor/g12/g12-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-279: REF-279 Build an executable, self-testing prover capability matrix

## REF-279 Build an executable, self-testing prover capability matrix

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-246
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/prover_matrix_registry.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_prover_matrix_registry.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_prover_matrix_registry.py -q
- Bundle: refactor/g12/g12-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S2
- Missing evidence: Source files, installers, and executable discovery do not establish that a prover can soundly check a supervisor obligation.
- AST symbols: PROVER_MATRIX_SCHEMA_VERSION, PROVER_SELF_TEST_SCHEMA_VERSION, PROVER_MATRIX_DUCKDB_SCHEMA_VERSION, PROVER_MATRIX_REPORT_VERSION, DEFAULT_SELF_TEST_TIMEOUT_SECONDS, DEFAULT_MATRIX_TIMEOUT_SECONDS, DEFAULT_MAX_OUTPUT_BYTES, DEFAULT_MAX_IDENTITY_FILE_BYTES, DEFAULT_MAX_SELF_TESTS, DEFAULT_DOCUMENTATION_MATRIX, ProverState, SelfTestStatus, IdentityKind, _canonical_json, _identity, _utc_timestamp, _strict_json_mapping, _nonempty_tuple, BoundIdentity, SelfTestBinding, ProverFixture, ProverDefinition, CommandRequest, CommandResult, CommandRunner, PackageFinder, VersionFinder, ExecutableFinder, ProverSelfTestReceipt, DocumentationClaim
- Merge key: refactor/g12/g12-s2
- Candidate kind: seed
- Todo vector key: ref-279-buildanexecutableself-testingprovercapabilitymat
- Acceptance: The registry covers Z3, CVC5, TLA+/TLC, Apalache, Datalog/SecPAL, Tamarin, ProVerif, HyperLTL/AutoHyper/MCHyper, Lean, Coq, runtime MTL, DCEC, TDFOL, Hammer, Vampire, E, Isabelle, ShadowProver, Leanstral, and ZKP backends.; Each entry distinguishes absent, discovered, versioned, smoke-tested, translation-conformant, reconstruction-capable, and authoritative-for states.; Bounded self-tests bind executable, package, model, translator, semantic profile, and fixture identities.; The repository prover matrix is projected into queryable JSON and DuckDB without treating documentation claims as runtime evidence.

- [x] Task checkbox-280: REF-280 Conformance-test and quarantine logic translations and legacy prover paths

## REF-280 Conformance-test and quarantine logic translations and legacy prover paths

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-275, REF-279
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/prover_conformance.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/logic_translation_validation.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_prover_conformance.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_prover_conformance.py -q
- Bundle: refactor/g12/g12-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S2
- Missing evidence: A solver is only as sound as the translation and semantic abstraction used to invoke it.
- AST symbols: PROVER_CONFORMANCE_VERSION, CONFORMANCE_FIXTURE_SCHEMA, CONFORMANCE_FIXTURE_SET_SCHEMA, CONFORMANCE_CASE_SCHEMA, CONFORMANCE_REPORT_SCHEMA, CONFORMANCE_GATE_SCHEMA, DEFAULT_MAX_CONFORMANCE_CASES, DEFAULT_CONFORMANCE_TIMEOUT_SECONDS, ConformanceTestKind, ConformanceMethod, ConformanceStatus, RouteHealth, QuarantineReason, _enum, _text, _strings, _strict_mapping, _timestamp, _digest, _schema, _claimed_identity, ConformanceFixture, ConformanceFixtureSet, ConformanceObservation, ConformanceCaseResult, ConformanceReport, FixtureRunner, ConformanceRunConfig, ProverConformanceRunner, QuarantineRule
- Merge key: refactor/g12/g12-s2
- Candidate kind: seed
- Todo vector key: ref-280-conformance-testandquarantinelogictranslationsan
- Acceptance: Translation contracts label exact, equisatisfiable, bounded abstraction, conservative approximation, and heuristic mappings and define permitted assurance for each.; Round-trip, differential, metamorphic, mutation, and negative fixtures cover AST, DCEC, TDFOL, FOL, TPTP, SMT-LIB, TLA+, protocol, and hyperproperty forms.; Known CEC deontic API drift and timing-sensitive cache tests keep affected paths degraded until semantic conformance fixtures pass.; Dropped agents, times, quantifiers, modal operators, bounds, or premises are detected and cannot silently promote a result.

- [x] Task checkbox-281: REF-281 Route obligations through property-specific multi-prover portfolios

## REF-281 Route obligations through property-specific multi-prover portfolios

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-255, REF-280
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/multi_prover_router.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_multi_prover_router.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_multi_prover_router.py -q
- Bundle: refactor/g12/g12-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S2
- Missing evidence: Different supervisor claims require different semantics; one generic solver-success flag cannot verify them all.
- AST symbols: MULTI_PROVER_ROUTER_VERSION, PROPERTY_OBLIGATION_SCHEMA, PORTFOLIO_PLAN_SCHEMA, PORTFOLIO_ATTEMPT_SCHEMA, PORTFOLIO_RESULT_SCHEMA, DEFAULT_PORTFOLIO_TIMEOUT_SECONDS, DEFAULT_MAX_PARALLEL_PROVERS, DEFAULT_MAX_EVIDENCE_BYTES, PropertyKind, PropertyType, ObligationProperty, ProverRole, AttemptOutcome, PortfolioVerdict, RouteVerdict, _enum, _text, _strings, _mapping, _schema, _claimed_identity, _strict_json_size, PropertyObligation, classify_property_kind, ProverLane, PropertyPolicy, _authority, _KERNEL_LANES, PortfolioPlan, AttemptRequest
- Merge key: refactor/g12/g12-s2
- Candidate kind: seed
- Todo vector key: ref-281-routeobligationsthroughproperty-specificmulti-pr
- Acceptance: Routing selects SMT for finite constraints, TLA tools for state machines, Datalog/SecPAL for authorization, Tamarin/ProVerif for protocols, HyperLTL tools for hyperproperties, runtime MTL for traces, and Lean/Coq/Isabelle for kernel checking.; DCEC and TDFOL provide typed planning and temporal-deontic reasoning while Hammer coordinates premise selection, ATP/SMT candidates, and kernel reconstruction.; Disagreement, unknown, unsupported, timeout, and malformed output fail closed according to property policy and retain every attempt.; Conclusive counterexamples cancel redundant attempts while successful solver candidates still require the configured reconstruction or model-checking authority.

- [x] Task checkbox-282: REF-282 Persist conformance-bound prover receipts, caches, and matrix projections

## REF-282 Persist conformance-bound prover receipts, caches, and matrix projections

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-260, REF-281
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/prover_evidence_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_prover_evidence_store.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_prover_evidence_store.py -q
- Bundle: refactor/g12/g12-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S2
- Missing evidence: Multi-prover reuse must bind every semantic, model, bound, toolchain, and trust dimension and remain queryable without loading raw transcripts.
- AST symbols: EvidenceLookupStatus, EvidenceRejectionReason, ProverCacheLookupStatus, ProverCacheRejectionReason, ProverSingleFlightError, ProverSingleFlightTimeout, ProverSingleFlightExecutionError, _json, _required, _mapping, _ordered_values, _digest, _timestamp_ms, _named_identity, ProverEvidenceKey, build_prover_evidence_key, make_prover_evidence_key, ProverCacheKey, ConformanceBinding, ProverEvidenceReceipt, EvidenceRequirements, EvidenceLookupResult, EvidenceStoreResult, SingleFlightResult, T, ProverEvidenceStore, ProverEvidenceProjectionPaths, prover_evidence_projection_paths, _public_attempt, _projection_payload
- Merge key: refactor/g12/g12-s2
- Candidate kind: seed
- Todo vector key: ref-282-persistconformance-boundproverreceiptscachesandm
- Acceptance: Receipt and cache identities include property class, normalized model, translator profile, assumptions, finite bounds, prover and kernel versions, policy, tree, and conformance fixture set.; Stale, lower-assurance, model-only, or non-conformant results cannot satisfy a stronger request.; JSON and DuckDB projections expose capabilities, attempts, disagreements, counterexamples, assurance, freshness, and invalidation lineage.; Single-flight ownership deduplicates equivalent heavy prover requests across serial and parallel supervisors.
