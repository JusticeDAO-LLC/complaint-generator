# Objective Bundle: refactor/g11/g11-s6

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-264: REF-264 Define ZKP receipt-attestation statements and trust semantics

## REF-264 Define ZKP receipt-attestation statements and trust semantics

- Status: completed
- Completion: manual
- Priority: P1
- Track: G11
- Depends on: REF-245
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_attestation.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_attestation_contracts.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_attestation_contracts.py -q
- Bundle: refactor/g11/g11-s6
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S6
- Missing evidence: A ZKP can bind a trusted proof receipt or protect private premises, but it does not independently prove arbitrary Python correctness.
- AST symbols: PROOF_ATTESTATION_CONTRACT_VERSION, PROOF_ATTESTATION_STATEMENT_SCHEMA, PROOF_ATTESTATION_ENVELOPE_SCHEMA, PROOF_ATTESTATION_VERIFICATION_SCHEMA, PROOF_ATTESTATION_RECORD_SCHEMA, PERSISTED_ATTESTATION_SCHEMA, ATTESTATION_BACKEND_POLICY_SCHEMA, ATTESTATION_BACKEND_TEST_RESULT_SCHEMA, ATTESTATION_BACKEND_HEALTH_SCHEMA, ZKP_RECEIPT_ATTESTATION_STATEMENT_SCHEMA, ZKP_RECEIPT_ATTESTATION_ENVELOPE_SCHEMA, ZKP_RECEIPT_ATTESTATION_VERIFICATION_SCHEMA, RECEIPT_ATTESTATION_STATEMENT_SCHEMA, RECEIPT_ATTESTATION_ENVELOPE_SCHEMA, ATTESTATION_VERIFICATION_SCHEMA, ZKP_RECEIPT_ATTESTATION_RECORD_SCHEMA, RECEIPT_ATTESTATION_RECORD_SCHEMA, AttestationValidationError, WitnessDisclosureError, CryptographicBackendFailure, AttestationBackendMode, ZKPBackendMode, AttestationTrust, AttestationGate, AttestationVerificationVerdict, AttestationMode, AttestationBackendHealth, BackendTestCase, BackendTestVerdict, REQUIRED_BACKEND_TEST_CASES
- Merge key: refactor/g11/g11-s6
- Candidate kind: seed
- Todo vector key: ref-264-definezkpreceipt-attestationstatementsandtrustse
- Acceptance: The public statement binds tree, obligation, policy, kernel, receipt, circuit, backend, and verification-key identities.; Attestation is available only for an existing kernel-verified receipt.; Simulated ZKP is labeled non-authoritative and cannot satisfy production or completion gates.; Hidden witness fields are excluded from logs, context capsules, caches, and public artifacts.

- [x] Task checkbox-265: REF-265 Gate cryptographic backends on health, circuit, key, and no-leak evidence

## REF-265 Gate cryptographic backends on health, circuit, key, and no-leak evidence

- Status: completed
- Completion: manual
- Priority: P1
- Track: G11
- Depends on: REF-244, REF-264
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_attestation.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_capabilities.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_attestation_backends.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_attestation_backends.py -q
- Bundle: refactor/g11/g11-s6
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S6
- Missing evidence: ProveKit or Groth16 must fail closed when binaries, circuits, verification keys, schemas, or witness protections are unavailable or stale.
- AST symbols: PROOF_ATTESTATION_CONTRACT_VERSION, PROOF_ATTESTATION_STATEMENT_SCHEMA, PROOF_ATTESTATION_ENVELOPE_SCHEMA, PROOF_ATTESTATION_VERIFICATION_SCHEMA, PROOF_ATTESTATION_RECORD_SCHEMA, PERSISTED_ATTESTATION_SCHEMA, ATTESTATION_BACKEND_POLICY_SCHEMA, ATTESTATION_BACKEND_TEST_RESULT_SCHEMA, ATTESTATION_BACKEND_HEALTH_SCHEMA, ZKP_RECEIPT_ATTESTATION_STATEMENT_SCHEMA, ZKP_RECEIPT_ATTESTATION_ENVELOPE_SCHEMA, ZKP_RECEIPT_ATTESTATION_VERIFICATION_SCHEMA, RECEIPT_ATTESTATION_STATEMENT_SCHEMA, RECEIPT_ATTESTATION_ENVELOPE_SCHEMA, ATTESTATION_VERIFICATION_SCHEMA, ZKP_RECEIPT_ATTESTATION_RECORD_SCHEMA, RECEIPT_ATTESTATION_RECORD_SCHEMA, AttestationValidationError, WitnessDisclosureError, CryptographicBackendFailure, AttestationBackendMode, ZKPBackendMode, AttestationTrust, AttestationGate, AttestationVerificationVerdict, AttestationMode, AttestationBackendHealth, BackendTestCase, BackendTestVerdict, REQUIRED_BACKEND_TEST_CASES
- Merge key: refactor/g11/g11-s6
- Candidate kind: seed
- Todo vector key: ref-265-gatecryptographicbackendsonhealthcircuitkeyandno
- Acceptance: Backend health distinguishes simulated, configured, available, verified, degraded, and unavailable states.; Circuit, public-input schema, verification-key, and backend versions are pinned in policy and receipt identity.; Golden, negative, stale-key, malformed-proof, and witness no-leak cases gate production eligibility.; A cryptographic failure cannot fall back to simulated success.

- [x] Task checkbox-266: REF-266 Persist optional ZKP envelopes beside trusted proof receipts

## REF-266 Persist optional ZKP envelopes beside trusted proof receipts

- Status: completed
- Completion: manual
- Priority: P1
- Track: G11
- Depends on: REF-254, REF-255, REF-265
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_attestation.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_cache.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/artifact_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_attestation_store.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_attestation_store.py -q
- Bundle: refactor/g11/g11-s6
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S6
- Missing evidence: Verified envelopes should be queryable and optionally content-addressed without changing the underlying proof verdict or exposing witnesses.
- AST symbols: PROOF_ATTESTATION_CONTRACT_VERSION, PROOF_ATTESTATION_STATEMENT_SCHEMA, PROOF_ATTESTATION_ENVELOPE_SCHEMA, PROOF_ATTESTATION_VERIFICATION_SCHEMA, PROOF_ATTESTATION_RECORD_SCHEMA, PERSISTED_ATTESTATION_SCHEMA, ATTESTATION_BACKEND_POLICY_SCHEMA, ATTESTATION_BACKEND_TEST_RESULT_SCHEMA, ATTESTATION_BACKEND_HEALTH_SCHEMA, ZKP_RECEIPT_ATTESTATION_STATEMENT_SCHEMA, ZKP_RECEIPT_ATTESTATION_ENVELOPE_SCHEMA, ZKP_RECEIPT_ATTESTATION_VERIFICATION_SCHEMA, RECEIPT_ATTESTATION_STATEMENT_SCHEMA, RECEIPT_ATTESTATION_ENVELOPE_SCHEMA, ATTESTATION_VERIFICATION_SCHEMA, ZKP_RECEIPT_ATTESTATION_RECORD_SCHEMA, RECEIPT_ATTESTATION_RECORD_SCHEMA, AttestationValidationError, WitnessDisclosureError, CryptographicBackendFailure, AttestationBackendMode, ZKPBackendMode, AttestationTrust, AttestationGate, AttestationVerificationVerdict, AttestationMode, AttestationBackendHealth, BackendTestCase, BackendTestVerdict, REQUIRED_BACKEND_TEST_CASES
- Merge key: refactor/g11/g11-s6
- Candidate kind: seed
- Todo vector key: ref-266-persistoptionalzkpenvelopesbesidetrustedproofrec
- Acceptance: Attestation envelopes preserve a reference to the immutable kernel receipt and public-input digest.; Cache and optional IPFS records bind backend, circuit, key, policy, and expiration.; Verifier results are reproducible from public artifacts and fail when any bound identity changes.; Attestation loss or expiration leaves kernel assurance intact but removes attested assurance.
