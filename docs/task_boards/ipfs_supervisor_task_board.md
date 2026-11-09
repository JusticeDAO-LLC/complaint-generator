# IPFS Supervisor Daemon Task Board

Generated from `docs/task_boards/ipfs_supervisor_task_board.json`.
Edit the JSON board first, then regenerate this markdown projection.

## SUP-CSR-M0 Question and testimony foundation

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: templates/claim_support_review.html, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, complaint_phases/knowledge_graph.py, complaint_phases/dependency_graph.py, docs/PAYLOAD_CONTRACTS.md, docs/APPLICATIONS.md, docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_claim_support_hooks.py -q; python -m pytest tests/test_review_api.py -q
- Acceptance: Recommended questions map to unresolved elements, contradictions, or gaps. Testimony persists as raw narrative plus structured facts. Review payloads show testimony-to-element support. Dashboard explains why each question is being asked.
- Source doc: docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Canonical task id: CSR-M0
- Canonical status: complete

## SUP-CSR-M1 Document intake and decomposition plane

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: templates/claim_support_review.html, integrations/ipfs_datasets/documents.py, mediator/evidence_hooks.py, mediator/web_evidence_hooks.py, mediator/claim_support_hooks.py, docs/PAYLOAD_CONTRACTS.md, docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_evidence_hooks.py -q; python -m pytest tests/test_web_evidence_hooks.py -q; python -m pytest tests/test_review_api.py -q
- Acceptance: Dashboard-ingested materials produce normalized parse records and chunk references. Chunks trace to artifact and page or span provenance. Low-quality parses are visible and remediable.
- Source doc: docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Canonical task id: CSR-M1
- Canonical status: complete

## SUP-CSR-M2 Fact registry and element support ledger

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: mediator/claim_support_hooks.py, integrations/ipfs_datasets/types.py, integrations/ipfs_datasets/provenance.py, docs/PAYLOAD_CONTRACTS.md, templates/claim_support_review.html, docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_claim_support_hooks.py -q
- Acceptance: Element status can be explained by concrete fact IDs. Facts trace to testimony, document chunks, or authorities. Support ledgers can feed replay and document handoff.
- Source doc: docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Canonical task id: CSR-M2
- Canonical status: complete

## SUP-CSR-M3 Graph snapshot persistence and support paths

- Status: completed
- Completion: validation
- Priority: P1
- Track: sup
- Depends on: SUP-CSR-M2
- Outputs: integrations/ipfs_datasets/graphs.py, complaint_phases/knowledge_graph.py, complaint_phases/dependency_graph.py, mediator/claim_support_hooks.py, templates/claim_support_review.html, docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_claim_support_hooks.py -q; python -m pytest tests/test_review_api.py -q
- Acceptance: Each claim element can show a graph-backed support path. Review flows reuse persisted graph snapshots. Entity resolution reduces duplicate source nodes.
- Source doc: docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Canonical task id: CSR-M3
- Canonical status: complete

## SUP-CSR-M4 Retrieval sessions and evidence ranking

- Status: completed
- Completion: validation
- Priority: P1
- Track: sup
- Depends on: SUP-CSR-M2
- Outputs: integrations/ipfs_datasets/vector_store.py, integrations/ipfs_datasets/documents.py, mediator/claim_support_hooks.py, templates/claim_support_review.html, docs/PAYLOAD_CONTRACTS.md, docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_m4_retrieval_sessions.py -q; python -m pytest tests/test_claim_support_hooks.py -q
- Acceptance: Operators can inspect ranked chunks for a claim element. Retrieval sessions are replayable. Questions can cite retrieval context.
- Source doc: docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Canonical task id: CSR-M4
- Canonical status: complete

## SUP-CSR-M5 Legal proof and contradiction engine

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: SUP-CSR-M2
- Outputs: integrations/ipfs_datasets/logic.py, integrations/ipfs_datasets/graphrag.py, mediator/claim_support_hooks.py, complaint_phases/legal_graph.py, complaint_phases/neurosymbolic_matcher.py, templates/claim_support_review.html, docs/PAYLOAD_CONTRACTS.md, docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_claim_support_hooks.py -q; python -m pytest tests/test_probate_integration.py -q
- Acceptance: Review payloads distinguish supported, missing, contradicted, uncertain, and exception-barred elements. Proof results include concise explanations tied to facts, authorities, or failed predicates. Dashboard shows facts applied to law.
- Source doc: docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Canonical task id: CSR-M5
- Canonical status: complete

## SUP-CSR-M6 Operator productization and document handoff

- Status: completed
- Completion: validation
- Priority: P1
- Track: sup
- Depends on: SUP-CSR-M5
- Outputs: templates/claim_support_review.html, templates/document.html, mediator/claim_support_hooks.py, applications/server.py, docs/APPLICATIONS.md, docs/PAYLOAD_CONTRACTS.md, docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_document_pipeline.py -q; python -m pytest tests/test_review_api.py -q
- Acceptance: Operators can move from intake to proof review to drafting impact in one workflow. Unresolved elements expose visible next actions. Document generation consumes validated support state.
- Source doc: docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md
- Canonical task id: CSR-M6
- Canonical status: complete

## SUP-IE-B0 Timeline ledger foundation

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: complaint_phases/intake_case_file.py, mediator/mediator.py, complaint_phases/phase_manager.py, intake_status.py, docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_mediator_three_phase.py -q; python -m pytest tests/test_intake_status.py -q; python -m pytest tests/test_review_api.py -q
- Acceptance: Event and relation IDs created during intake are visible downstream. Chronology blockers identify missing anchors, relations, or contradictions.
- Source doc: docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Canonical task id: IE-B0
- Canonical status: complete

## SUP-IE-B1 Intake structure foundation

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: complaint_phases/intake_case_file.py, mediator/mediator.py, intake_status.py, docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_mediator_three_phase.py -q; python -m pytest tests/test_intake_status.py -q
- Acceptance: Intake answers produce structured facts and proof leads with stable references. Open intake work is explicit queueable work.
- Source doc: docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Canonical task id: IE-B1
- Canonical status: complete

## SUP-IE-B2 Proof-directed question planner

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: complaint_phases/denoiser.py, mediator/mediator.py, docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_mediator.py -q; python -m pytest tests/test_mediator_three_phase.py -q
- Acceptance: Mediator explains each question proof objective. Repeated questions fall without reducing claim-element coverage.
- Source doc: docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Canonical task id: IE-B2
- Canonical status: complete

## SUP-IE-B3 Claim ambiguity and contradiction workflow

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: complaint_phases/phase_manager.py, mediator/mediator.py, intake_status.py, docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_mediator.py -q; python -m pytest tests/test_intake_status.py -q
- Acceptance: Intake summaries distinguish contradictions from missingness. Blocking contradictions prevent silent advancement.
- Source doc: docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Canonical task id: IE-B3
- Canonical status: complete

## SUP-IE-B4 Minimum fact bundles and evidence task board

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: mediator/claim_support_hooks.py, mediator/mediator.py, complaint_phases/phase_manager.py, complaint_phases/denoiser.py, docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_mediator_three_phase.py -q; python -m pytest tests/test_claim_support_hooks.py -q
- Acceptance: Unresolved elements produce explainable tasks with success targets. Phase 2 questioning is task-structure driven.
- Source doc: docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Canonical task id: IE-B4
- Canonical status: complete

## SUP-IE-B5 Support lane unification and provenance quality

- Status: completed
- Completion: validation
- Priority: P1
- Track: sup
- Depends on: 
- Outputs: mediator/evidence_hooks.py, mediator/claim_support_hooks.py, docs/EVIDENCE_MANAGEMENT.md, docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_claim_support_hooks.py -q; python -m pytest tests/test_document_pipeline.py -q
- Acceptance: Support summaries explain type and quality of support. Operators can trace packet conclusions to source lineage.
- Source doc: docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Canonical task id: IE-B5
- Canonical status: complete

## SUP-IE-B6 Proof-readiness gates

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: complaint_phases/phase_manager.py, mediator/mediator.py, docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_document_pipeline.py -q; python -m pytest tests/test_parallel_validation_fix.py -q
- Acceptance: Complaint-ready and proof-ready are distinct states. Unsupported core elements surface before drafting.
- Source doc: docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Canonical task id: IE-B6
- Canonical status: complete

## SUP-IE-B7 Review and trace surfaces

- Status: completed
- Completion: validation
- Priority: P1
- Track: sup
- Depends on: 
- Outputs: intake_status.py, applications/review_api.py, applications/document_api.py, templates/claim_support_review.html, templates/document.html, templates/optimization_trace.html, docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_review_api.py -q; python -m pytest tests/test_claim_support_review_playwright_smoke.py -q
- Acceptance: Operators can explain blockers without raw graph or ledger rows. Traces replay intake-to-evidence progression.
- Source doc: docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Canonical task id: IE-B7
- Canonical status: complete

## SUP-IE-B8 Validation harness and metrics

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: adversarial_harness/harness.py, adversarial_harness/critic.py, docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_adversarial_harness.py -q; python -m pytest tests/test_document_pipeline.py -q --run-llm
- Acceptance: Adversarial batches show proof-readiness and question-precision changes. Regressions in proof readiness or question precision are detectable.
- Source doc: docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md
- Canonical task id: IE-B8
- Canonical status: complete

## SUP-IPFS-M0 Adapter and capability hardening

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: integrations/ipfs_datasets/capabilities.py, integrations/ipfs_datasets/loader.py, integrations/ipfs_datasets/legal.py, integrations/ipfs_datasets/search.py, integrations/ipfs_datasets/graphs.py, integrations/ipfs_datasets/logic.py, mediator/mediator.py, docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Validation: python -m pytest tests/test_ipfs_adapter_layer.py -q; python -m pytest tests/test_ipfs_adapter_types.py -q
- Acceptance: Startup succeeds with or without optional ipfs_datasets_py extras. Missing features produce explicit capability payloads. Production code does not import ipfs_datasets_py internals directly.
- Source doc: docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Canonical task id: IPFS-M0
- Canonical status: complete

## SUP-IPFS-M1 Shared parse and corpus contract

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: SUP-IPFS-M0
- Outputs: integrations/ipfs_datasets/documents.py, integrations/ipfs_datasets/types.py, integrations/ipfs_datasets/provenance.py, mediator/evidence_hooks.py, mediator/web_evidence_hooks.py, mediator/legal_authority_hooks.py, docs/PAYLOAD_CONTRACTS.md, docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Validation: python -m pytest tests/test_evidence_hooks.py -q; python -m pytest tests/test_web_evidence_hooks.py -q; python -m pytest tests/test_legal_authority_hooks.py -q
- Acceptance: Evidence, web evidence, and authority text produce one parse contract family. Document-format handling does not leak into mediator code.
- Source doc: docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Canonical task id: IPFS-M1
- Canonical status: complete

## SUP-IPFS-M2 Persistent support and graph query plane

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: SUP-IPFS-M1
- Outputs: integrations/ipfs_datasets/graphs.py, mediator/claim_support_hooks.py, mediator/evidence_hooks.py, mediator/web_evidence_hooks.py, mediator/legal_authority_hooks.py, mediator/mediator.py, complaint_phases/knowledge_graph.py, complaint_phases/dependency_graph.py, docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Validation: python -m pytest tests/test_claim_support_hooks.py -q; python -m pytest tests/test_review_api.py -q; python -m pytest tests/test_evidence_hooks.py tests/test_claim_support_hooks.py tests/test_legal_authority_hooks.py -q
- Acceptance: Mediator review flows explain coverage using provenance-backed support traces.
- Source doc: docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Canonical task id: IPFS-M2
- Canonical status: complete

## SUP-IPFS-M3 Support-quality and validation layer

- Status: completed
- Completion: validation
- Priority: P1
- Track: sup
- Depends on: SUP-IPFS-M2
- Outputs: integrations/ipfs_datasets/graphrag.py, integrations/ipfs_datasets/logic.py, complaint_phases/legal_graph.py, complaint_phases/neurosymbolic_matcher.py, complaint_phases/phase_manager.py, mediator/claim_support_hooks.py, mediator/mediator.py, docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Validation: python -m pytest tests/test_m3_graphrag_quality_scoring.py -q; python -m pytest tests/test_ipfs_logic_adapter.py -q; python -m pytest tests/test_m5_legal_proof_contradiction_engine.py -q
- Acceptance: Support strength, missing premises, and contradictions surface before drafting for at least one complaint workflow.
- Source doc: docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Canonical task id: IPFS-M3
- Canonical status: complete

## SUP-IPFS-M4 Operator productization

- Status: completed
- Completion: validation
- Priority: P1
- Track: sup
- Depends on: SUP-IPFS-M3
- Outputs: applications/review_api.py, mediator/mediator.py, mediator/web_evidence_hooks.py, docs/APPLICATIONS.md, docs/PAYLOAD_CONTRACTS.md, docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Validation: python -m pytest tests/test_review_api.py -q; python -m pytest tests/test_web_evidence_hooks.py tests/test_claim_support_hooks.py tests/test_review_api.py -q
- Acceptance: Operators can inspect coverage, contradictions, provenance, and queued enrichment work without raw tables.
- Source doc: docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Canonical task id: IPFS-M4
- Canonical status: complete

## SUP-IPFS-M5 Drafting and filing readiness

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: SUP-IPFS-M4
- Outputs: document_pipeline.py, applications/document_api.py, templates/document.html, mediator/mediator.py, mediator/claim_support_hooks.py, claim_support_review.py, docs/APPLICATIONS.md, docs/PAYLOAD_CONTRACTS.md, docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Validation: python -m pytest tests/test_document_pipeline.py -q; python -m pytest tests/test_claim_support_review_template.py -q; python -m pytest tests/test_review_api.py -q
- Acceptance: At least one complaint workflow emits a filing draft with explicit readiness and warning metadata. Operators can move from support review into drafting without losing provenance.
- Source doc: docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md
- Canonical task id: IPFS-M5
- Canonical status: complete

## SUP-TEMP-T0 Canonical temporal registry

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: complaint_phases/intake_case_file.py, mediator/claim_support_hooks.py, docs/PAYLOAD_CONTRACTS.md, docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_intake_status.py -q; python -m pytest tests/test_claim_support_hooks.py -q; python -m pytest tests/test_review_api.py -q
- Acceptance: Timeline-capable facts can be represented in a shared registry. Relations and issues are claim-aware and element-aware. Legacy timeline summaries derive from canonical registries.
- Source doc: docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Canonical task id: TEMP-T0
- Canonical status: complete

## SUP-TEMP-T1 Claim-scoped temporal graph assembly

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: SUP-TEMP-T0
- Outputs: complaint_phases/intake_case_file.py, mediator/claim_support_hooks.py, mediator/mediator.py, docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_t1_t3_temporal_next_steps.py -q; python -m pytest tests/test_claim_support_hooks.py tests/test_mediator_three_phase.py -q; python -m pytest tests/test_review_api.py -q
- Acceptance: Claim-level temporal summaries are reproducible from one graph assembly path. Temporal readiness traces to fact and relation IDs. Temporal warnings align with graph issues.
- Source doc: docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Canonical task id: TEMP-T1
- Canonical status: complete

## SUP-TEMP-T2 Legal temporal rule profiles

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: SUP-TEMP-T1
- Outputs: complaint_analysis/decision_trees.py, complaint_analysis/legal_patterns.py, complaint_analysis/temporal_rule_profiles.py, docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_claim_support_hooks.py -q; python -m pytest tests/test_review_api.py -q
- Acceptance: At least one claim type evaluates chronology against an explicit rule profile. Proof failures identify missing events, ordering relations, or legal-window violations. Rule-profile evaluation is independent of HTML rendering.
- Source doc: docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Canonical task id: TEMP-T2
- Canonical status: complete

## SUP-TEMP-T3 Theorem export and proof bundles

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: SUP-TEMP-T2
- Outputs: mediator/claim_support_hooks.py, claim_support_review.py, integrations/ipfs_datasets/logic.py, docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_claim_support_hooks.py tests/test_review_api.py -q; python -m pytest tests/test_claim_support_review_dashboard_flow.py -q
- Acceptance: Theorem exports are reproducible from persisted proof bundles. Operator formula previews come from the same bundle used for proof execution. Proof failures identify concrete missing facts or relations.
- Source doc: docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Canonical task id: TEMP-T3
- Canonical status: complete

## SUP-TEMP-T4 Temporal contradiction and follow-up planner

- Status: completed
- Completion: validation
- Priority: P1
- Track: sup
- Depends on: SUP-TEMP-T3
- Outputs: mediator/claim_support_hooks.py, complaint_phases/denoiser.py, mediator/mediator.py, intake_status.py, docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_mediator_three_phase.py tests/test_intake_status.py -q; python -m pytest tests/test_claim_support_review_dashboard_flow.py -q
- Acceptance: Each blocking temporal issue yields explicit next action. Operators can see the affected rule or fact. Follow-up planning distinguishes temporal gaps from non-temporal missingness.
- Source doc: docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Canonical task id: TEMP-T4
- Canonical status: complete

## SUP-TEMP-T5 Review, drafting, and optimization integration

- Status: completed
- Completion: validation
- Priority: P1
- Track: sup
- Depends on: SUP-TEMP-T4
- Outputs: templates/claim_support_review.html, templates/document.html, templates/optimization_trace.html, applications/review_api.py, applications/document_api.py, docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_claim_support_review_dashboard_flow.py tests/test_claim_support_review_playwright_smoke.py -q; python -m pytest tests/test_claim_support_review_template.py -q
- Acceptance: Operators can move from summary metrics to concrete chronology blockers. Drafting surfaces do not overstate readiness when timing rules are unproved. Review and document flows consume the same temporal proof payloads.
- Source doc: docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Canonical task id: TEMP-T5
- Canonical status: complete

## SUP-TEMP-T6 Regression and gold-case enforcement

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: SUP-TEMP-T5
- Outputs: tests/test_t1_t3_temporal_next_steps.py, tests/test_temporal_rule_profiles.py, tests/test_claim_support_hooks.py, tests/test_review_api.py, tests/test_mediator_three_phase.py, tests/test_claim_support_review_dashboard_flow.py, tests/test_claim_support_review_playwright_smoke.py, tests/test_intake_status.py, docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Validation: python -m pytest tests/test_claim_support_hooks.py tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py tests/test_claim_support_review_playwright_smoke.py tests/test_mediator_three_phase.py tests/test_intake_status.py -q; python scripts/run_claim_support_review_regression.py --browser on
- Acceptance: Chronology regressions fail on payload drift and UI drift. At least one gold case proves sufficient ordering and one fails for an explainable temporal reason.
- Source doc: docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md
- Canonical task id: TEMP-T6
- Canonical status: complete

## SUP-CONTRACT-PAYLOADS Payload contract validation and fixture hygiene

- Status: completed
- Completion: validation
- Priority: P0
- Track: sup
- Depends on: 
- Outputs: docs/PAYLOAD_CONTRACTS.md, scripts/validate_task_boards.py, tests/test_task_board_contracts.py
- Validation: python scripts/validate_task_boards.py; python -m pytest tests/test_task_board_contracts.py -q
- Acceptance: Every json fence in PAYLOAD_CONTRACTS.md parses as JSON. Task-board validation catches malformed payload examples before supervisor execution. Contract changes remain compatible with markdown and machine-readable consumers.
- Source doc: docs/PAYLOAD_CONTRACTS.md
- Canonical task id: CONTRACT-PAYLOADS
- Canonical status: complete
