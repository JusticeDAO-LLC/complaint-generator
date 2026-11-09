# Objective Bundle: refactor/g12/g12-s3

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-283: REF-283 Model-check supervisor state machines with TLA+, TLC, and Apalache

## REF-283 Model-check supervisor state machines with TLA+, TLC, and Apalache

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-277, REF-279
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/supervisor_state_model.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_supervisor_state_model.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_supervisor_state_model.py -q
- Bundle: refactor/g12/g12-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S3
- Missing evidence: Leases, retries, merges, refill, cancellation, and resource scheduling are concurrent state machines suited to bounded model checking.
- AST symbols: _NO_AGENT, _RESERVED_IDENTIFIERS, _TLC_SUCCESS_MARKERS, _APALACHE_SUCCESS_MARKERS, _COUNTEREXAMPLE_MARKERS, ModelValidationError, ModelCheckerTool, ModelCheckStatus, _strict_mapping, _strings, _positive_int, _boolean, _sha256_text, _utc_timestamp, _enum_value, TransitionRule, SupervisorTransitionSchema, ModelCheckBounds, _tla_string, _tla_set, _tla_function, _model_name, GeneratedSupervisorStateModel, SupervisorStateModelGenerator, CounterexampleState, CounterexampleTrace, ModelCheckerExecutionConfig, ModelCheckReceipt, CommandRunner, ExecutableFinder
- Merge key: refactor/g12/g12-s3
- Candidate kind: seed
- Todo vector key: ref-283-model-checksupervisorstatemachineswithtlatlcanda
- Acceptance: A deterministic generator emits a finite TLA+ model from the supervisor transition schema rather than a domain-specific hard-coded workflow.; Safety covers unique acceptance, fencing, dependency order, idempotent merge, capacity, and evidence gates; liveness covers bounded progress and terminal outcomes.; TLC and Apalache execution receipts record exact model, configuration, bounds, versions, output, and counterexample traces.; Bounded model-check success is labeled by its explored bounds and is never described as an unbounded proof.

- [x] Task checkbox-284: REF-284 Formalize task authority and delegation with Datalog and SecPAL-style policy

## REF-284 Formalize task authority and delegation with Datalog and SecPAL-style policy

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-277, REF-279
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/authorization_logic.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_authorization_logic.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_authorization_logic.py -q
- Bundle: refactor/g12/g12-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S3
- Missing evidence: Claims, leases, merge authority, proof promotion, and overrides need explicit delegation and revocation semantics.
- AST symbols: AuthorizationValidationError, Capability, AuthorizationCapability, AuthorizationVerdict, DenialReason, GeneratedCodeCorrectness, AuthorizationEngine, PolicyEngine, EngineSupportStatus, ConformanceStatus, LaneStatus, _text, _strings, _ordered_strings, _nonnegative, _optional_nonnegative, _enum, _schema, _identity, _normalized_path, _normalize_scopes, _scope_contains, _path_contains, _item_covered, _scope_subset, Principal, _principal_id, AuthorizationGrant, PolicyGrant, DelegationGrant
- Merge key: refactor/g12/g12-s3
- Candidate kind: seed
- Todo vector key: ref-284-formalizetaskauthorityanddelegationwithdatalogan
- Acceptance: Rules model principals, capabilities, delegation depth, lease scope, fencing epoch, proof authority, override scope, expiration, and revocation.; The reference evaluator and any external Datalog or SecPAL lane agree on positive, negative, revocation, confused-deputy, and stale-lease fixtures.; Missing engines remain unsupported while deterministic policy checks continue in shadow mode.; Authorization evidence can permit an action but cannot establish generated-code correctness.

- [!] Task checkbox-285: REF-285 Verify claim, fencing, receipt, and attestation protocols with Tamarin and ProVerif

## REF-285 Verify claim, fencing, receipt, and attestation protocols with Tamarin and ProVerif

- Status: blocked
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-264, REF-284
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/protocol_verification.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_protocol_verification.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_protocol_verification.py -q
- Bundle: refactor/g12/g12-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S3
- Missing evidence: Supervisor coordination and evidence exchange have protocol properties that unit tests and state invariants alone do not cover.
- AST symbols: 
- Merge key: refactor/g12/g12-s3
- Candidate kind: seed
- Todo vector key: ref-285-verifyclaimfencingreceiptandattestationprotocols
- Acceptance: Versioned models cover claimant authentication, lease grants, fencing freshness, replay resistance, receipt binding, merge authorization, and optional attestation exchange.; Tamarin and ProVerif lanes expose secrecy, authenticity, correspondence, and replay queries with exact model and toolchain receipts.; Attack traces become canonical counterexamples and model abstractions are documented per query.; Executable presence or installer success cannot satisfy protocol verification without a passing end-to-end model fixture.

- [x] Task checkbox-286: REF-286 Check cross-lane information-flow hyperproperties

## REF-286 Check cross-lane information-flow hyperproperties

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-252, REF-265, REF-279
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/hyperproperty_verification.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_hyperproperty_verification.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_hyperproperty_verification.py -q
- Bundle: refactor/g12/g12-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S3
- Missing evidence: Single-trace checks cannot establish that secrets, witnesses, or unrelated lane data do not affect observable prompts, logs, or artifacts.
- AST symbols: HYPERPROPERTY_VERIFICATION_VERSION, OBSERVATION_POLICY_SCHEMA, HYPERPROPERTY_MODEL_SCHEMA, HYPERTRACE_COUNTEREXAMPLE_SCHEMA, HYPERPROPERTY_RESULT_SCHEMA, ENGINE_CONFORMANCE_FIXTURE_SCHEMA, ENGINE_CONFORMANCE_RECEIPT_SCHEMA, ENGINE_CAPABILITY_SCHEMA, DEFAULT_MAX_COMPOSITION_TRACES, DEFAULT_MAX_COMPOSITION_PAIRS, DEFAULT_ENGINE_TIMEOUT_SECONDS, DEFAULT_MAX_ENGINE_OUTPUT_BYTES, DEFAULT_MAX_EXECUTABLE_BYTES, REDACTED_VALUE, MISSING_VALUE, HyperpropertyValidationError, HyperpropertyKind, HyperpropertyEngine, EngineKind, ConformanceStatus, EngineCapabilityStatus, HyperpropertyVerdict, HyperpropertyEvidenceKind, _text, _enum, _strings, _mapping, _positive_int, _schema, _claimed_identity
- Merge key: refactor/g12/g12-s3
- Candidate kind: seed
- Todo vector key: ref-286-checkcross-laneinformation-flowhyperproperties
- Acceptance: Hyperproperty models cover prompt isolation, worktree isolation, log redaction, provider routing, ZKP witness noninterference, and cross-task cache separation.; HyperLTL, AutoHyper, and MCHyper adapters are capability-gated and report unavailable until executable conformance fixtures pass.; Bounded self-composition tests provide non-authoritative fallback evidence when no hyperproperty engine is available.; Counterexample hypertraces are redacted, minimized, and bound to the exact observation policy.
