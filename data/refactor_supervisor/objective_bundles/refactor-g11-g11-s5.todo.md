# Objective Bundle: refactor/g11/g11-s5

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-261: REF-261 Expose Leanstral through a capability-isolated llm_router provider

## REF-261 Expose Leanstral through a capability-isolated llm_router provider

- Status: completed
- Completion: manual
- Priority: P1
- Track: G11
- Depends on: REF-244, REF-246
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leanstral_proof_provider.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_capabilities.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_leanstral_proof_provider.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_leanstral_proof_provider.py -q
- Bundle: refactor/g11/g11-s5
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S5
- Missing evidence: Leanstral can draft useful Lean proof text, but its legal-modal implementation has optional model and spaCy dependencies that cannot become supervisor startup requirements.
- AST symbols: _ROUTER_ALIASES, _CANONICAL_MUTATION_KEYS, LLMGenerate, _nonempty_text, _positive_integer, _json_mapping, _identifiers, LeanstralResourceIsolation, LeanstralProofProviderConfig, LeanstralProviderConfig, LeanstralProofDraft, LeanstralGateStatus, LeanstralProofGateResult, _default_llm_generate, _LeanstralInvocation, _strict_response_object, _parse_fixed_theorem_response, _coerce_leanstral_draft, _validate_draft_integrity, verify_leanstral_draft, LeanstralPatchGatePolicy, LeanstralPatchGateResult, _safe_patch_path, _header_patch_path, _paths_from_patch, _path_in_task_scope, _task_declared_scope, _command_payload, _execute_patch_command, check_leanstral_patch_proposal
- Merge key: refactor/g11/g11-s5
- Candidate kind: seed
- Todo vector key: ref-261-exposeleanstralthroughacapability-isolatedllm-ro
- Acceptance: Leanstral inference is invoked through llm_router with explicit provider, model, timeout, and token budgets.; Missing spaCy, model service, codec, or Leanstral dependencies produce degraded capability rather than import failure.; Model output is always marked unverified and cannot mutate canonical source or obligations.; Inference runs in the model resource class, separate from local kernel checking.

- [x] Task checkbox-262: REF-262 Generate fixed-theorem Leanstral prompts from proof context capsules

## REF-262 Generate fixed-theorem Leanstral prompts from proof context capsules

- Status: completed
- Completion: manual
- Priority: P1
- Track: G11
- Depends on: REF-252, REF-261
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leanstral_proof_provider.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_context.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_leanstral_proof_context.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_leanstral_proof_context.py -q
- Bundle: refactor/g11/g11-s5
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S5
- Missing evidence: Leanstral should solve a verifier-generated theorem with bounded premises instead of rediscovering repository structure in its context window.
- AST symbols: _ROUTER_ALIASES, _CANONICAL_MUTATION_KEYS, LLMGenerate, _nonempty_text, _positive_integer, _json_mapping, _identifiers, LeanstralResourceIsolation, LeanstralProofProviderConfig, LeanstralProviderConfig, LeanstralProofDraft, LeanstralGateStatus, LeanstralProofGateResult, _default_llm_generate, _LeanstralInvocation, _strict_response_object, _parse_fixed_theorem_response, _coerce_leanstral_draft, _validate_draft_integrity, verify_leanstral_draft, LeanstralPatchGatePolicy, LeanstralPatchGateResult, _safe_patch_path, _header_patch_path, _paths_from_patch, _path_in_task_scope, _task_declared_scope, _command_payload, _execute_patch_command, check_leanstral_patch_proposal
- Merge key: refactor/g11/g11-s5
- Candidate kind: seed
- Todo vector key: ref-262-generatefixed-theoremleanstralpromptsfromproofco
- Acceptance: Prompts contain a fixed theorem identity, allowed premises, trusted prior receipts, compact failures, and output schema.; The model may propose proof text or decomposition but cannot change assumptions, conclusion, template, or source scope.; Prompt and response sizes obey context-capsule and token budgets.; Equivalent tasks reuse untrusted draft artifacts without treating them as checked evidence.

- [x] Task checkbox-263: REF-263 Kernel-check Leanstral drafts and constrain patch proposals

## REF-263 Kernel-check Leanstral drafts and constrain patch proposals

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-255, REF-262
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leanstral_proof_provider.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/kernel_verification.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_leanstral_proof_gate.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_leanstral_proof_gate.py -q
- Bundle: refactor/g11/g11-s5
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S5
- Missing evidence: Leanstral output is useful only after deterministic schema, theorem-integrity, source-scope, patch, and local kernel checks.
- AST symbols: _ROUTER_ALIASES, _CANONICAL_MUTATION_KEYS, LLMGenerate, _nonempty_text, _positive_integer, _json_mapping, _identifiers, LeanstralResourceIsolation, LeanstralProofProviderConfig, LeanstralProviderConfig, LeanstralProofDraft, LeanstralGateStatus, LeanstralProofGateResult, _default_llm_generate, _LeanstralInvocation, _strict_response_object, _parse_fixed_theorem_response, _coerce_leanstral_draft, _validate_draft_integrity, verify_leanstral_draft, LeanstralPatchGatePolicy, LeanstralPatchGateResult, _safe_patch_path, _header_patch_path, _paths_from_patch, _path_in_task_scope, _task_declared_scope, _command_payload, _execute_patch_command, check_leanstral_patch_proposal
- Merge key: refactor/g11/g11-s5
- Candidate kind: seed
- Todo vector key: ref-263-kernel-checkleanstraldraftsandconstrainpatchprop
- Acceptance: Forbidden imports, axioms, unsafe declarations, sorry, admit, theorem substitution, and source-copy attacks are rejected.; Accepted proof text passes the same independent kernel reconstruction path as non-LLM candidates.; Patch proposals are restricted to task-declared paths and must pass git apply check plus configured validation.; Model and kernel artifacts retain separate provenance and assurance.
