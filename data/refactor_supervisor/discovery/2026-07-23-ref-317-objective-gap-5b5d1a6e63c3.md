# REF-317 Objective Goal Gap

Date: 2026-07-23
Fingerprint: 5b5d1a6e63c3ad5e91e9c7f16664d5f2ed8af755
Goal id: G3.S1
Goal title: Normalize IPFS datasets adapter payloads
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Priority: P0
Track: ops
Parent goals: G3
Graph depth: 1
Bundle: refactor/g3/g3-s1
Parallel lane: refactor/g3/g3-s1
Bundle strategy: explicit
Goal packet: goal_packet/ops/integrations/de7d9d2f5784
Goal packet role: packet_anchor
Goal packet goals: G3.S1, G3.S2
Goal packet task count: 2
Goal packet work item count: 2
Evidence methods: ast, embedding, exact, path
Embedding query: Normalize IPFS datasets adapter payloads
AST query: integrations/ipfs_datasets/capabilities.py, integrations/ipfs_datasets/loader.py, All adapter groups report stable keys., Missing optional extras produce actionable reasons., python -m pytest tests/test_ipfs_adapter_layer.py -q, integrations/ipfs_datasets/documents.py, mediator/evidence_hooks.py, Evidence, authority, and web ingestion can call one parse contract., Fallback mode preserves current behavior., python -m pytest tests/test_document_pipeline.py tests/test_document_pipeline_fallbacks.py -q
Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
Predicted files: none
AST symbols: integrations/ipfs_datasets/capabilities.py, integrations/ipfs_datasets/loader.py, All adapter groups report stable keys., Missing optional extras produce actionable reasons., python -m pytest tests/test_ipfs_adapter_layer.py -q, integrations/ipfs_datasets/documents.py, mediator/evidence_hooks.py, Evidence, authority, and web ingestion can call one parse contract., Fallback mode preserves current behavior., python -m pytest tests/test_document_pipeline.py tests/test_document_pipeline_fallbacks.py -q
Interfaces: none
Submodules: none
Generated artifacts: none
Allow concurrent with: none

## Goal

Normalize IPFS datasets adapter payloads

## Missing Evidence

- objective validation repair

## Present Evidence

- integrations/ipfs_datasets/capabilities.py: integrations/ipfs_datasets/capabilities.py (path), SESSION_84_FINAL_SUMMARY.md (ast), TODO.md (embedding:0.31)
- integrations/ipfs_datasets/loader.py: integrations/ipfs_datasets/loader.py (path), P3_INFRASTRUCTURE_COMPLETION_SESSION.md (embedding:0.54), P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md (embedding:0.33)
- All adapter groups report stable keys.: .vscode/tasks.json (ast), adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast)
- Missing optional extras produce actionable reasons.: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), adversarial_harness/complainant.py (ast)
- python -m pytest tests/test_ipfs_adapter_layer.py -q: BATCH_328_API_RETURN_TYPES_SUMMARY.md (embedding:0.35), BENCHMARK_SUITE_SESSION_SUMMARY.md (embedding:0.36), CONTRIBUTING.md (embedding:0.39)
- integrations/ipfs_datasets/documents.py: integrations/ipfs_datasets/documents.py (path), .complaint_workspace/sessions/alias-script-user.json (ast), .complaint_workspace/sessions/demo-user.json (ast)
- mediator/evidence_hooks.py: mediator/evidence_hooks.py (path), .complaint_workspace/sessions/alias-script-user.json (ast), .complaint_workspace/sessions/demo-user.json (ast)
- Evidence: .complaint_workspace/sessions/alias-script-user.json (exact), .complaint_workspace/sessions/demo-user.json (exact), .complaint_workspace/sessions/did-key-008c3dbfb02e6dd4bbaaaaab753abb3927af5d5b97a59ac2e30b8f8eb21d4388.json (exact)
- authority: .complaint_workspace/sessions/demo-user.json (exact), .complaint_workspace/sessions/did-key-3f9542d258f6ccddf8e318787f6f485911da0f70eddfafca5a8467c53f208c1b.json (exact), .vscode/tasks.json (exact)
- and web ingestion can call one parse contract.: README.md (embedding:0.31), adversarial_harness/demo_autopatch.py (ast), applications/complaint_cli.py (ast)
- Fallback mode preserves current behavior.: adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast), adversarial_harness/hacc_evidence.py (ast)
- python -m pytest tests/test_document_pipeline.py tests/test_document_pipeline_fallbacks.py -q: .github/workflows/claim-support-regression.yml (embedding:0.66), .github/workflows/hacc-unit-regression.yml (embedding:0.62), .github/workflows/standard-regression.yml (embedding:0.80)

## Suggested Handling

Run and repair the objective validation command until it passes, then record the evidence.
