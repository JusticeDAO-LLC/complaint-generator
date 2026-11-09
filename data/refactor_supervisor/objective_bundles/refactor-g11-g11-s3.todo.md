# Objective Bundle: refactor/g11/g11-s3

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-253: REF-253 Adapt code obligations to the ipfs_datasets_py Hammer portfolio

## REF-253 Adapt code obligations to the ipfs_datasets_py Hammer portfolio

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-246, REF-249
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/ipfs_datasets_logic_provider.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_provider.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_ipfs_datasets_logic_provider.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_ipfs_datasets_logic_provider.py -q
- Bundle: refactor/g11/g11-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S3
- Missing evidence: The mature Hammer portfolio should be consumed through the provider boundary rather than copied into the supervisor.
- AST symbols: _EPOCH, HammerAdapterStatus, _text, _strings, _strict_mapping, _positive_int, _family, _solver_names, _digest, _minimum_positive, _seconds_within, _memory_mb_within, _provider_safe, HammerSupervisorPolicy, IpfsDatasetsLogicProviderConfig, IPFSDatasetsLogicProviderConfig, HammerProviderPolicy, IpfsDatasetsProviderPolicy, EffectiveHammerPolicy, HammerRequestBundle, HammerPortfolioInvocation, PortfolioRunner, _load_hammer, _obligation, _effective_policy, _resolve_family, _premise_payloads, _environment_lock, translate_obligation_to_hammer_request, _status_from_hammer
- Merge key: refactor/g11/g11-s3
- Candidate kind: seed
- Todo vector key: ref-253-adaptcodeobligationstotheipfs-datasets-pyhammerp
- Acceptance: Supported obligations translate deterministically into Hammer requests with explicit premises and environment locks.; Solver allowlists, timeouts, CPU, memory, network denial, and maximum premise counts flow from supervisor policy.; Portfolio attempts and candidate proofs preserve upstream receipt provenance.; Unsupported translation families return a typed unsupported result and configured fallback checks.

- [x] Task checkbox-254: REF-254 Add trust-aware proof caching and single-flight execution

## REF-254 Add trust-aware proof caching and single-flight execution

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-245, REF-253
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_cache.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/ipfs_datasets_logic_provider.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_cache.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_cache.py -q
- Bundle: refactor/g11/g11-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S3
- Missing evidence: Parallel lanes must reuse sound results without executing the same expensive obligation or trusting a stale or weaker cache entry.
- AST symbols: CacheLookupStatus, CacheRejectionReason, SingleFlightError, SingleFlightTimeout, SingleFlightExecutionError, _json_value, _identity_component, _premises, _sha256, _rfc3339_from_ms, _timestamp_ms, ProofCacheKey, build_proof_cache_key, make_proof_cache_key, FormalVerificationCacheKey, CacheRequirements, ProofCacheEntry, AttestationCacheEntry, CacheLookupResult, CacheStoreResult, AttestationCacheLookupResult, AttestationCacheStoreResult, SingleFlightLease, _strict_json_loads, _PRIVATE_FLIGHT_FIELDS, _contains_private_flight_material, _single_flight_public_value, _component_identifier, _obligation_identifier, _premise_identifiers
- Merge key: refactor/g11/g11-s3
- Candidate kind: seed
- Todo vector key: ref-254-addtrust-awareproofcachingandsingle-flightexecut
- Acceptance: Cache keys bind obligation, premises, translator, solver, kernel, toolchain, theorem registry, policy, resource budget, and candidate tree.; Only results meeting the requested assurance and freshness can satisfy a lookup.; A cross-thread and cross-process single-flight lease deduplicates active proof work.; Poisoned, malformed, stale, partial, solver-only, and simulated-attestation cache entries are rejected with reason codes.

- [x] Task checkbox-255: REF-255 Enforce independent kernel reconstruction and verdict derivation

## REF-255 Enforce independent kernel reconstruction and verdict derivation

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-245, REF-253
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/kernel_verification.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_kernel_verification.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_kernel_verification.py -q
- Bundle: refactor/g11/g11-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S3
- Missing evidence: A solver candidate or LLM proof draft is not formal verification until an allowed target kernel accepts the exact reconstructed obligation.
- AST symbols: KernelVerificationError, KernelTarget, KernelVerificationStatus, KernelFailureCode, LeanProofAdmission, KernelVerificationPolicy, KernelVerificationBindings, KernelVerificationResult, _enum_value, _target, _text, _record, _json_safe, _upstream_content_digest, _digest_matches, _normalized_statement, _LEAN_DECLARATION, _COQ_DECLARATION, _ISABELLE_DECLARATION, _extract_statement, _FORBIDDEN_DECLARATIONS, _INCOMPLETE_PROOFS, _LEAN_PROOF_FORBIDDEN_IMPORT, _LEAN_PROOF_FORBIDDEN_DECLARATION, _LEAN_PROOF_DECLARATION_ANYWHERE, _LEAN_PROOF_INCOMPLETE, _LEAN_PROOF_SOURCE_MARKERS, _sha256_text, _lean_admission_rejection, admit_lean_proof_text
- Merge key: refactor/g11/g11-s3
- Candidate kind: seed
- Todo vector key: ref-255-enforceindependentkernelreconstructionandverdict
- Acceptance: Lean, Coq, and Isabelle reconstruction records are mapped without weakening upstream trust semantics.; Kernel unavailability, timeout, mismatch, forbidden declarations, sorry or admit, and changed theorem statements fail closed.; The authoritative verdict is derived from reconstruction evidence and cannot be upgraded by provider status text.; Negative and corrupt proof fixtures never produce kernel-verified receipts.

- [x] Task checkbox-256: REF-256 Route counterexamples and unsupported obligations into focused validation

## REF-256 Route counterexamples and unsupported obligations into focused validation

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-247, REF-249, REF-255
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_fallbacks.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_fallbacks.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_fallbacks.py -q
- Bundle: refactor/g11/g11-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S3
- Missing evidence: Disproved, unsupported, or inconclusive obligations should reduce model search and trigger actionable checks instead of becoming generic failures.
- AST symbols: PROOF_FALLBACK_VERSION, PROOF_DIAGNOSTIC_SCHEMA, REGRESSION_FIXTURE_SCHEMA, PROOF_FALLBACK_PLAN_SCHEMA, DEFAULT_MAX_DIAGNOSTIC_BYTES, DEFAULT_MAX_FIXTURE_BYTES, DEFAULT_MAX_TEXT_CHARS, DEFAULT_MAX_COLLECTION_ITEMS, DEFAULT_MAX_NESTING_DEPTH, DEFAULT_MAX_DIAGNOSTICS, _DIAGNOSTIC_PAYLOAD_BYTES, _SENSITIVE_KEY_RE, _COUNTEREXAMPLE_KEYS, _UNSAT_CORE_KEYS, ProofFallbackValidationError, ProofFailureKind, RegressionExpectation, _enum, _schema, _text, _NormalizationBudget, _bounded_value, _bounded_payload, normalize_counterexample, normalize_unsat_core, ProofFallbackDiagnostic, ProofRegressionFixture, build_regression_fixture, ProofFallbackDeduplicator, ProofFallbackPlan
- Merge key: refactor/g11/g11-s3
- Candidate kind: seed
- Todo vector key: ref-256-routecounterexamplesandunsupportedobligationsint
- Acceptance: Counterexamples and unsat cores are normalized into bounded task diagnostics and regression fixtures.; Unsupported obligations map to declared focused tests, static checks, or manual-review requirements.; Shadow mode can continue through fallback validation while enforcement mode honors required assurance.; Repeated equivalent failures deduplicate by obligation, tree, and counterexample identity.
