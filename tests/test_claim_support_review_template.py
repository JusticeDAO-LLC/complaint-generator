from pathlib import Path

from fastapi.testclient import TestClient

from applications.review_ui import create_review_dashboard_app, create_review_surface_app


def test_claim_support_review_template_exists_and_targets_review_endpoints():
    template_path = Path("templates/claim_support_review.html")

    assert template_path.exists()
    content = template_path.read_text()
    assert "/document" in content
    assert "/api/claim-support/review" in content
    assert "/api/claim-support/execute-follow-up" in content
    assert "/api/claim-support/resolve-manual-review" in content
    assert "/api/claim-support/save-testimony" in content
    assert "/api/claim-support/save-document" in content
    assert "/api/claim-support/upload-document" in content
    assert "Load Review" in content
    assert "Execute Follow-Up" in content
    assert "Question Queue" in content
    assert "Testimony Intake" in content
    assert "Document Intake" in content
    assert "Save Testimony" in content
    assert "Save Document" in content
    assert "question-list" in content
    assert "Intake Case Summary" in content
    assert "intake-next-action-banner" in content
    assert "recent-validation-outcome-card" in content
    assert "Recent Validation Outcome" in content
    assert "recent-validation-outcome-status" in content
    assert "recent-validation-outcome-chips" in content
    assert "recent-validation-outcome-notes" in content
    assert "alignment-promotion-drift-card" in content
    assert "alignment-promotion-drift-title" in content
    assert "alignment-promotion-drift-status" in content
    assert "alignment-promotion-drift-chips" in content
    assert "alignment-promotion-drift-notes" in content
    assert "alignment-validation-focus-list" in content
    assert "const orderedValidationFocusTargets = [...validationFocusTargets].sort((left, right) => {" in content
    assert "Promotion Drift Summary" in content
    assert "Validate promoted support" in content
    assert "validation targets: ${validationTargetCount}" in content
    assert "intake-next-action-open-promoted" in content
    assert "Review promoted updates" in content
    assert "intake-next-action-prefill-testimony" in content
    assert "Prefill testimony validation" in content
    assert "intake-next-action-prefill-document" in content
    assert "Prefill document validation" in content
    assert "intake-next-action-review-conflicts" in content
    assert "Review manual conflicts" in content
    assert "intake-next-action-prefill-resolution" in content
    assert "Load into resolution form" in content
    assert "intake-next-action-review-evidence-task" in content
    assert "Review evidence task" in content
    assert "intake-next-action-build-packets" in content
    assert "Build claim support packets" in content
    assert "intake-next-action-review-knowledge-graph" in content
    assert "Review intake graph inputs" in content
    assert "intake-next-action-review-dependencies" in content
    assert "Review dependency inputs" in content
    assert "intake-next-action-review-denoising" in content
    assert "Review denoising queue" in content
    assert "intake-next-action-review-legal-graph" in content
    assert "Review legal graph inputs" in content
    assert "intake-next-action-review-matching" in content
    assert "Review matching inputs" in content
    assert "intake-next-action-open-document-builder" in content
    assert "Open formal complaint builder" in content
    assert "workflow-phase-guidance-card" in content
    assert "Workflow Phase Guidance" in content
    assert "workflowPhasePlan.recommended_order" in content
    assert "workflowPhasePriorityFromPayload" in content
    assert "resolveReviewWorkflowPhasePriority(workflowPhasePlanPayload)" in content
    assert "workflowPhasePriority.action_id" in content
    assert "workflowPhasePriority.action_label" in content
    assert "workflowPhasePriority.chip_labels" in content
    assert "intake-next-action-open-formal-generator" in content
    assert "intake-next-action-confirm-summary" in content
    assert "Confirm intake summary" in content
    assert "intake-next-action-review-gaps" in content
    assert "Review intake gaps" in content
    assert "intake-next-action-review-packet-readiness" in content
    assert "Review packet readiness" in content
    assert "Resolve graph analysis before drafting" in content
    assert "Resolve drafting readiness before filing" in content
    assert "workflow phase: ${humanizeQueryValue(prioritizedPhaseName)}" in content
    assert "phase status: ${humanizeQueryValue(prioritizedPhase.status || 'warning')}" in content
    assert "remaining gap count: ${remainingGapCount}" in content
    assert "current gap count: ${currentGapCount}" in content
    assert "knowledge graph enhanced: ${Boolean(graphEnhanced) ? 'yes' : 'no'}" in content
    assert "unresolved temporal issues: ${unresolvedTemporalIssueCount}" in content
    assert "unresolved without review path: ${unresolvedWithoutReviewPathCount}" in content
    assert "Showing packet readiness summary and evidence blockers before drafting." in content
    assert "recommended action: ${nextAction.action}" in content
    assert "focus claim: ${humanizeQueryValue(focusedPromotedClaimType)}" in content
    assert "focus element: ${humanizeQueryValue(focusedPromotedElementId)}" in content
    assert "primary target: ${humanizeQueryValue(primaryValidationTarget.claim_element_id)}" in content
    assert "primary promotion kind: ${humanizeQueryValue(primaryValidationTarget.promotion_kind)}" in content
    assert "primary promotion ref: ${primaryValidationTarget.promotion_ref}" in content
    assert "Promoted testimony or document support is accumulating faster than packet validation is reaching resolved supported status." in content
    assert "Primary validation target: ${humanizeQueryValue(primaryValidationTarget.claim_element_id)}." in content
    assert "Primary promotion ref: ${primaryValidationTarget.promotion_ref}." in content
    assert "const primaryValidationClaimType = String(" in content
    assert "const primaryValidationElementId = String(" in content
    assert "data-claim-type=\"${primaryValidationClaimType}\"" in content
    assert "data-claim-element-id=\"${primaryValidationElementId}\"" in content
    assert "intake-readiness-criteria-chips" in content
    assert "intake-claim-summary-chips" in content
    assert "intake-context-chips" in content
    assert "${satisfied ? 'ready' : 'needs'} ${humanizeQueryValue(criterion)}" in content
    assert "candidate claims: ${Number(intakeStatus.candidate_claim_count || 0)}" in content
    assert "canonical facts: ${Number(intakeStatus.canonical_fact_count || 0)}" in content
    assert "proof leads: ${Number(intakeStatus.proof_lead_count || 0)}" in content
    assert "confidence: ${confidenceValue.toFixed(2)}" in content
    assert "ambiguity: ${humanizeQueryValue(flag)}" in content
    assert "average confidence: ${Number(candidateClaimSummary.average_confidence || 0).toFixed(2)}" in content
    assert "claim disambiguation: ${candidateClaimSummary.close_leading_claims ? 'needed' : 'stable'}" in content
    assert "event ledger: ${Number(eventLedgerSummary.count || 0)}" in content
    assert "timeline anchors: ${Number(timelineAnchorSummary.count || 0)}" in content
    assert "Event Ledger" in content
    assert "Stable chronology objects carried from intake into evidence review" in content
    assert "event: ${event.event_id || event.temporal_fact_id || event.fact_id || 'unknown'}" in content
    assert "harm profile: ${harmCategories.map((item) => humanizeQueryValue(item)).join(', ')}" in content
    assert "remedy profile: ${remedyCategories.map((item) => humanizeQueryValue(item)).join(', ')}" in content
    assert "Intake matching summary" in content
    assert "Unresolved legal elements for" in content
    assert "intake-matching-summary-list" in content
    assert "question target:" in content
    assert "Intake-Evidence Alignment" in content
    assert "intake-evidence-alignment-summary-list" in content
    assert "Cross-phase element alignment for" in content
    assert "Intake-evidence alignment" in content
    assert "aligned ${element.element_id}: ${element.support_status || 'unknown'}" in content
    assert "Alignment Evidence Tasks" in content
    assert "alignment-evidence-task-list" in content
    assert "Alignment task for ${task.claim_type || 'claim'}" in content
    assert "evidence action ${task.action || 'fill_evidence_gaps'}" in content
    assert "element: ${task.claim_element_id || 'unknown'}" in content
    assert "chronology bundle: ${task.temporal_proof_bundle_id}" in content
    assert "chronology objective: ${humanizeQueryValue(task.temporal_proof_objective)}" in content
    assert "chronology events: ${taskEventIds.length}" in content
    assert "chronology relations: ${taskTemporalRelationIds.length}" in content
    assert "chronology issues: ${taskTimelineIssueIds.length}" in content
    assert "Proof artifacts: ${Number(reviewData.proof_artifact_element_count || 0)}" in content
    assert "proof id ${escapeHtml(element.proof_artifact_proof_id)}" in content
    assert "Copy proof ID" in content
    assert "Copy proof explanation" in content
    assert "Proof artifact sentence" in content
    assert "Proof artifact notes" in content
    assert "Proof explanation copied for ${proofExplanationButton.dataset.proofElement || 'the selected element'}." in content
    assert "Chronology event IDs" in content
    assert "Chronology relation IDs" in content
    assert "Chronology issue IDs" in content
    assert "pending_review" in content
    assert "promoted" in content
    assert "promoted_testimony" in content
    assert "promoted_document" in content
    assert "answered_pending_review" in content
    assert "answered, pending review" in content
    assert "review state: awaiting support validation" in content
    assert "Pinned for validation focus" in content
    assert "promoted_to_testimony" in content
    assert "promoted_to_document" in content
    assert "saved as testimony" in content
    assert "saved as document" in content
    assert "promotion: testimony record saved" in content
    assert "promotion: document saved" in content
    assert "promotion ref:" in content
    assert "promoted testimony:" in content
    assert "promoted document:" in content
    assert "promotion drift:" in content
    assert "resolved supported:" in content
    assert "pending conversion:" in content
    assert "drift ratio:" in content
    assert "Promoted support and packet validation are moving at a comparable pace." in content
    assert "validation target:" in content
    assert "promotion kind:" in content
    assert "Validation focus for ${humanizeQueryValue(claimType || 'claim')} / ${humanizeQueryValue(claimElementId || 'element')}" in content
    assert "Promoted support for this element still needs validation before packet support can be treated as settled." in content
    assert "primary validation target" in content
    assert "task-card ${isPrimaryValidationTarget ? 'is-section-focus' : ''}" in content
    assert "This is the current primary validation target from the promoted-support banner." in content
    assert "return rightPrimary - leftPrimary;" in content
    assert "return rightSequence - leftSequence;" in content
    assert "validation-focus-open-promoted-button" in content
    assert "validation-focus-prefill-testimony-button" in content
    assert "validation-focus-prefill-document-button" in content
    assert "Showing promoted alignment updates for the selected validation target." in content
    assert "Testimony form prefilled from validation focus target." in content
    assert "Document form prefilled from validation focus target." in content
    assert "prefill-testimony-update-button" in content
    assert "prefill-document-update-button" in content
    assert "Load Into Document Form" in content
    assert "prefillDocumentForm" in content
    assert "Testimony form prefilled from pending-review alignment update." in content
    assert "Document form prefilled from pending-review alignment update." in content
    assert "data-claim-type=\"${nextAction.claim_type || ''}\"" in content
    assert "data-claim-element-id=\"${nextAction.claim_element_id || ''}\"" in content
    assert "openAlignmentUpdateFilter(" in content
    assert "openPromotedUpdatesButton.dataset.claimType" in content
    assert "openPromotedUpdatesButton.dataset.claimElementId" in content
    assert "prefillPromotedValidationForm(" in content
    assert "Validation follow-up for promoted support tied to ${humanizedElement}." in content
    assert "Validation support for ${humanizedElement}" in content
    assert "postSaveValidationFocus" in content
    assert "lastValidationOutcome" in content
    assert "evidenceSequence" in content
    assert "recentValidationOutcome" in content
    assert "The latest backend-tracked validation event resolved support for this claim element." in content
    assert "The latest backend-tracked validation event did not fully resolve support for this claim element yet." in content
    assert "findMatchingAlignmentUpdate(payload, focus.claimType, focus.claimElementId)" in content
    assert "Validation save improved support for ${focus.claimElementId || 'the targeted element'} and returned you to the promoted update lane." in content
    assert "Validation save recorded for ${focus.claimElementId || 'the targeted element'}; the refreshed update still needs support validation." in content
    assert "validation ${validationOutcome.improved ? 'improved' : 'still needs review'}" in content
    assert "Testimony form prefilled from focused promoted-support validation." in content
    assert "Document form prefilled from focused promoted-support validation." in content
    assert "recommended action: build_knowledge_graph" in content
    assert "Intake facts and timeline anchors are present, but the knowledge graph has not been built into an operator-reviewable structure yet." in content
    assert "openKnowledgeGraphInputsReview()" in content
    assert "Showing timeline and canonical fact inputs for intake graph building." in content
    assert "recommended action: build_dependency_graph" in content
    assert "Intake sections are populated enough to map cross-section dependencies, but the dependency graph has not been built yet." in content
    assert "openDependencyGraphInputsReview()" in content
    assert "Showing alignment and contradiction inputs for dependency graph review." in content
    assert "recommended action: continue_denoising" in content
    assert "Intake contradictions or open clarification paths still need another denoising pass before the case theory can settle." in content
    assert "openDenoisingQueueReview()" in content
    assert "Showing contradictions and targeted questions for continued intake denoising." in content
    assert "recommended action: build_legal_graph" in content
    assert "Claim targeting is available, but the legal graph that organizes statutes and requirements has not been built yet." in content
    assert "openLegalGraphInputsReview()" in content
    assert "Showing unresolved legal elements and question targets for legal graph review." in content
    assert "recommended action: perform_neurosymbolic_matching" in content
    assert "The legal graph is available, but formal claim-to-law matching still needs operator review support." in content
    assert "openNeurosymbolicMatchingReview()" in content
    assert "Showing unresolved legal elements and question targets for neurosymbolic matching." in content
    assert "recommended action: generate_formal_complaint" in content
    assert "Formalization is ready to move from matching outputs into a draft complaint package." in content
    assert "recommended action: build_claim_support_packets" in content
    assert "Evidence records exist, but the claim support packet still needs an explicit packet build before evidence review can be trusted." in content
    assert "recommended action: resolve_support_conflicts" in content
    assert "manual review blockers: ${manualReviewBlockers.length}" in content
    assert "packet escalations: ${reviewableEscalations}" in content
    assert "support status: ${humanizeQueryValue(nextAction.support_status)}" in content
    assert "recommended lane: ${humanizeQueryValue(item)}" in content
    assert "Contradicted or escalated support is blocking evidence completion for a priority element." in content
    assert "openManualReviewFocus(" in content
    assert "Showing manual-review conflicts that are blocking evidence completion." in content
    assert "Resolution form prefilled from blocking evidence conflict." in content
    assert "recommended action: fill_evidence_gaps" in content
    assert "recommended action: fill_temporal_chronology_gap" in content
    assert "chronology issues: ${unresolvedChronologyIssues.length}" in content
    assert "chronology objective: ${humanizeQueryValue(focusedAlignmentTask.temporal_proof_objective)}" in content
    assert "preferred lane: ${humanizeQueryValue(preferredSupportKind)}" in content
    assert "quality target: ${humanizeQueryValue(focusedAlignmentTask.source_quality_target)}" in content
    assert "fallback lane: ${humanizeQueryValue(lane)}" in content
    assert "Temporal ordering is still unresolved for a shared intake-to-packet element." in content
    assert "Unresolved chronology issue IDs: ${unresolvedChronologyIssues.length ? unresolvedChronologyIssues.join(', ') : 'none recorded'}" in content
    assert "intake-next-action-review-chronology-task" in content
    assert "Review chronology task" in content
    assert "Showing chronology blocker task and unresolved issue IDs." in content
    assert "Priority evidence is still missing for a shared intake-to-packet element." in content
    assert "openEvidenceTaskReview(" in content
    assert "Showing priority evidence task and preferred support lane." in content
    assert "recommended action: complete_evidence" in content
    assert "packet completion ready: ${evidenceCompletionReady ? 'yes' : 'no'}" in content
    assert "proof readiness: ${proofReadinessScore.toFixed(2)}" in content
    assert "Evidence support is sufficiently assembled to move from packet review into formal complaint drafting." in content
    assert "openDocumentDraftingHandoff()" in content
    assert "recommended action: confirm_intake_summary" in content
    assert "recommended action: address_gaps" in content
    assert "gap count: ${actionGaps.length}" in content
    assert "question candidates: ${questionCandidateCount}" in content
    assert "readiness score: ${readinessScore.toFixed(2)}" in content
    assert "gap: ${humanizeQueryValue(gap)}" in content
    assert "Intake still has unresolved proof or chronology gaps that should be clarified before handoff quality degrades." in content
    assert "The latest intake summary snapshot is still waiting for complainant confirmation before the intake phase can fully settle." in content
    assert "confirmSummaryBannerButton" in content
    assert "confirmIntakeSummary();" in content
    assert "openIntakeGapReview('summary_of_facts', 'question-list')" in content
    assert "Showing unresolved intake gaps and targeted questions." in content
    assert "Showing promoted alignment updates that still need validation." in content
    assert "intake only:" in content
    assert "evidence only:" in content
    assert "testimony-list" in content
    assert "document-list" in content
    assert "save-testimony-button" in content
    assert "save-document-button" in content
    assert "document-file-input" in content
    assert "testimony-summary-chips" in content
    assert "document-summary-chips" in content
    assert "task-summary-chips" in content
    assert "prefill-testimony-button" in content
    assert "renderQuestionRecommendations" in content
    assert "renderTestimonyRecords" in content
    assert "renderDocumentArtifacts" in content
    assert "Fact previews" in content
    assert "Graph preview" in content
    assert "document-fact-preview" in content
    assert "document-graph-preview" in content
    assert "Document proof facts" in content
    assert "All proof facts" in content
    assert "proof-gap-details" in content
    assert "document supporting" in content
    assert "contradicting" in content
    assert "unresolved" in content
    assert "source_fact_status" in content
    assert "source_fact_ids" in content
    assert "Contradiction pairs" in content
    assert "contradiction-pair-details" in content
    assert "affected elements:" in content
    assert "packet blocking covered:" in content
    assert "packet credible support:" in content
    assert "packet draft ready:" in content
    assert "packet parse quality:" in content
    assert "packet review escalations:" in content
    assert "packet escalations:" in content
    assert "packet unresolved without path:" in content
    assert "packet proof readiness:" in content
    assert "packet completion ready:" in content
    assert "preferred lane:" in content
    assert "fallback lane:" in content
    assert "quality target:" in content
    assert "priority:" in content
    assert "resolution:" in content
    assert "buildTestimonyRequest" in content
    assert "saveTestimony" in content
    assert "buildDocumentRequest" in content
    assert "buildDocumentUploadFormData" in content
    assert "saveDocument" in content
    assert "postFormData" in content
    assert "resolution-result-card" in content
    assert "signal-archive-captures" in content
    assert "signal-fallback-authorities" in content
    assert "signal-low-quality-records" in content
    assert "signal-parse-quality-tasks" in content
    assert "signal-supportive-authorities" in content
    assert "signal-adverse-authorities" in content
    assert "signal-follow-up-source-context" in content
    assert "execution-result-card" in content
    assert "parse_quality_recommendation" in content
    assert "authority_treatment_summary" in content
    assert "authority_search_program_summary" in content
    assert "normalizeFactBundle" in content
    assert "renderFactBundleChips" in content
    assert "buildCountSummaryLabel" in content
    assert "primary gap ${task.primary_missing_fact}" in content
    assert "covered facts ${satisfiedFactBundle.length}" in content
    assert "Primary gaps" in content
    assert "Gap coverage" in content
    assert "Covered facts" in content
    assert "authority program ${task.authority_search_program_summary.primary_program_type}" in content
    assert "authority bias ${task.authority_search_program_summary.primary_program_bias}" in content
    assert "rule bias ${task.authority_search_program_summary.primary_program_rule_bias}" in content
    assert "primary gap: ${entry.primary_missing_fact}" in content
    assert "covered facts: ${satisfiedFactBundle.length}" in content
    assert "History programs: ${selectedProgramTypes.map(([label, count]) => `${label}=${count}`).join(', ')}" in content
    assert "History biases: ${selectedProgramBiases.map(([label, count]) => `${label}=${count}`).join(', ')}" in content
    assert "History rule biases: ${selectedProgramRuleBiases.map(([label, count]) => `${label}=${count}`).join(', ')}" in content
    assert "program: ${entry.selected_search_program_type}" in content
    assert "History source context:" in content
    assert "family: ${entry.source_family}" in content
    assert "artifact: ${entry.artifact_family}" in content
    assert "origin: ${entry.content_origin}" in content
    assert "recommended_next_action" in content
    assert "URLSearchParams(window.location.search" in content
    assert "REVIEW_INTENT_STORAGE_KEY" in content
    assert "formalComplaintReviewIntent" in content
    assert "prefill-context-line" in content
    assert "section-focus-chip-row" in content
    assert "Opened from document workflow:" in content
    assert "params.get('section')" in content
    assert "params.get('follow_up_support_kind')" in content
    assert "SECTION_FOCUS_CONFIG" in content
    assert "applySectionFocus" in content
    assert "clearSectionFocus" in content
    assert "getLocalStorage" in content
    assert "buildReviewIntent" in content
    assert "params.set('follow_up_support_kind', supportKind)" in content
    assert "persistReviewIntent" in content
    assert "restoreReviewIntent" in content
    assert "syncReviewIntentUrl" in content
    assert "window.history.replaceState" in content
    assert "sectionFocusState" in content
    assert "scrollToSectionFocus" in content
    assert "expandSectionFocusDetails" in content
    assert "finalizeSectionFocus" in content
    assert "getActiveSectionFocusConfig" in content
    assert "sortBySectionFocus" in content
    assert "scoreElementForSectionFocus" in content
    assert "scoreTaskForSectionFocus" in content
    assert "scoreHistoryEntryForSectionFocus" in content
    assert "Pinned for section focus" in content
    assert "scrollIntoView({ behavior: 'smooth', block: 'start' })" in content
    assert "firstPacketDetails.open = true" in content
    assert "Focused lane:" in content
    assert "data-section-focus-target" in content
    assert "is-section-focus" in content
    assert "Lineage Signals" in content
    assert "Parse Signals" in content
    assert "Authority Signals" in content
    assert "View lineage packets" in content
    assert "packet-details" in content
    assert "All packets" in content
    assert "Archived only" in content
    assert "Fallback only" in content
    assert "data-packet-filter-button" in content
    assert "packet-filter-count" in content
    assert "data-packet-filter-summary" in content
    assert "Showing ${visibleCount} of ${totalCount} packets" in content
    assert "data-packet-url-action" in content
    assert "Open archive" in content
    assert "Copy archive" in content
    assert "Open original" in content
    assert "Copy original" in content
    assert "data-packet-action-feedback" in content
    assert "setPacketActionFeedback" in content
    assert "packetSortRank" in content
    assert "sortSupportPackets" in content
    assert "buildFollowUpSourceSignalCounts" in content
    assert "summarizeGraphSupportSourceContext" in content
    assert "renderSourceContextChips" in content
    assert "No graph-backed source context" in content
    assert "No graph source context" in content


def test_landing_pages_link_to_claim_support_review_dashboard():
    index_content = Path("templates/index.html").read_text()
    home_content = Path("templates/home.html").read_text()

    assert "/claim-support-review" in index_content
    assert "/claim-support-review" in home_content
    assert "/document" in index_content
    assert "/document" in home_content


def test_document_template_exists_and_targets_document_endpoints():
    template_path = Path("templates/document.html")

    assert template_path.exists()
    content = template_path.read_text()
    assert "/claim-support-review" in content
    assert "/api/documents/formal-complaint" in content
    assert "download_url" in content
    assert "Formal Complaint Builder" in content
    assert "Generate Formal Complaint" in content
    assert "Assigned Judge" in content
    assert "Courtroom" in content
    assert "County" in content
    assert "Lead Case Number" in content
    assert "Related Case Number" in content
    assert "caption.case_number_label || 'Civil Action No.'" in content
    assert "caption.caption_party_lines" in content
    assert "Requested Relief Overrides" in content
    assert "Demand Jury Trial" in content
    assert "Jury Demand Text" in content
    assert "Signer Name" in content
    assert "Law Firm or Office" in content
    assert "Bar Number" in content
    assert "Signer Contact Block" in content
    assert "Additional Signature Entries" in content
    assert "Verification Declarant" in content
    assert "Affidavit Title Override" in content
    assert "Affidavit Intro Override" in content
    assert "Affidavit Fact Overrides" in content
    assert "Affidavit Venue Lines" in content
    assert "Affidavit Jurat" in content
    assert "Affidavit Notary Block" in content
    assert "Service Method" in content
    assert "Service Recipients" in content
    assert "Detailed Service Entries" in content
    assert "Signature Date" in content
    assert "Verification Date" in content
    assert "Service Date" in content
    assert "Draft Preview" in content
    assert "Drafting Readiness" in content
    assert "Pre-Filing Checklist" in content
    assert "Open Checklist Review" in content
    assert "Section Readiness" in content
    assert "Claim Readiness" in content
    assert "Factual Allegations" in content
    assert "Affidavit in Support of Complaint" in content
    assert "Affidavit Supporting Exhibits" in content
    assert "Mirror complaint exhibits into affidavit" in content
    assert "Leave this enabled to let the affidavit inherit the complaint exhibit list" in content
    assert "Affidavit Execution" in content
    assert "Affidavit Exhibit Source:" in content
    assert "Incorporated Support" in content
    assert "Supporting Exhibit Details" in content
    assert "Open filing warnings" in content
    assert "pleading-paragraphs" in content
    assert "Pleading Text" in content
    assert "Copy Pleading Text" in content
    assert "value=\"txt\"" in content
    assert "value=\"checklist\"" in content
    assert "formalComplaintBuilderState" in content
    assert "formalComplaintBuilderPreview" in content
    assert "parseAdditionalSigners" in content
    assert "parseAffidavitSupportingExhibits" in content
    assert "describeAffidavitExhibitSource" in content
    assert "formatAdditionalSignerLines" in content
    assert "affidavit_title" in content
    assert "affidavit_intro" in content
    assert "affidavit_facts" in content
    assert "affidavit_supporting_exhibits" in content
    assert "affidavit_include_complaint_exhibits" in content
    assert "affidavit_venue_lines" in content
    assert "affidavit_jurat" in content
    assert "affidavit_notary_block" in content
    assert "localStorage" in content
    assert "REVIEW_INTENT_STORAGE_KEY" in content
    assert "Resume Review Focus" in content
    assert "data-review-intent-link=\"true\"" in content
    assert "persistReviewIntent({ review_url: node.getAttribute('href') || '' })" in content
    assert "payload.review_intent" in content
    assert "Workflow Priority" in content
    assert "document-workflow-priority" in content
    assert "document-workflow-action-link" in content
    assert "renderWorkflowPriority(reviewLinks, intakeCaseSummary, workflowPhasePlan, manualReviewClaims, pendingReviewClaims)" in content
    assert "resolveDocumentWorkflowAction(reviewLinks, intakeCaseSummary)" in content
    assert "reviewLinks.workflow_phase_priority" in content
    assert "workflowPriorityFromLinks" in content
    assert "workflowPriorityFromLinks.action_label" in content or "workflowPhasePriority.action_label" in content
    assert "workflowPriorityFromLinks.action_url" in content or "workflowPhasePriority.action_url" in content
    assert "workflowPriorityFromLinks.chip_labels" in content or "workflowPhasePriority.chip_labels" in content
    assert "resolveDocumentWorkflowPhasePriority(workflowPhasePlan)" in content
    assert "Confirm intake summary before drafting" in content
    assert "Resolve intake gaps before drafting" in content
    assert "Continue intake denoising before drafting" in content
    assert "actionKind = 'button'" in content
    assert 'onclick="confirmIntakeSummaryFromDocument()"' in content
    assert "Review intake graph inputs before drafting" in content
    assert "Resolve graph analysis before drafting" in content
    assert "Review dependency inputs before drafting" in content
    assert "Review legal graph inputs before drafting" in content
    assert "Review matching inputs before drafting" in content
    assert "Build support packets before drafting" in content
    assert "Resolve drafting readiness before filing" in content
    assert "Evidence is ready for formal drafting" in content
    assert "Intake Review Signals" in content
    assert "Intake blockers:" in content
    assert "Tracked intake contradictions:" in content
    assert "Intake Summary Handoff" in content
    assert "Confirm intake summary" in content
    assert "confirm-intake-summary-button" in content
    assert "/api/claim-support/confirm-intake-summary" in content
    assert "Confirmation records the latest intake summary snapshot before evidence marshalling continues." in content
    assert "Persisted Trace Snapshot" in content
    assert "Open Persisted Trace" in content
    assert "Checklist Intake Signals" in content
    assert "Checklist intake blockers:" in content
    assert "Contradiction lanes:" in content
    assert "Corroboration-required contradictions:" in content
    assert "affected elements" in content
    assert "Contradiction target elements" in content
    assert "Source Context:" in content
    assert "Source families:" in content
    assert "follow_up_support_kind" in content
    assert "appendAlignmentTaskViewToReviewUrl" in content
    assert "appendClaimQueueIntentToReviewUrl" in content
    assert "appendSectionReviewIntentToReviewUrl" in content
    assert "Manual Review Blockers" in content
    assert "Pending Review Items" in content
    assert "Open ${escapeHtml(humanizeKey(claimType))} Manual Review" in content
    assert "Open ${escapeHtml(humanizeKey(claimType))} Pending Review" in content
    assert "renderSectionReadiness" in content
    assert "renderClaimReadiness" in content
    assert "Open Section Review" in content
    assert "No claim-level drafting signals are available." in content
    assert "Source Drilldown" in content
    assert "Open Claim Support Review" in content
    assert "Open Review Dashboard" in content
    assert "Review manual conflicts" in content
    assert "Drafting is the current workflow priority" in content
    assert "buildClaimReviewUrl" in content
    assert "resolveClaimReviewUrl" in content
    assert "resolveSectionReviewUrl" in content
    assert "getSectionReviewLinkMap" in content
    assert "renderSectionClaimLinks" in content
    assert "renderFilingChecklist(items, manualReviewClaims, pendingReviewClaims)" in content
    assert "Section Review</a>" in content
    assert "renderReviewLinks" in content
    assert "review_links" in content
    assert "trace_download_url" in content
    assert "trace_view_url" in content
    assert "Open Persisted Trace" in content
    assert "Persisted Trace Snapshot" in content
    assert "Optimization Focus" in content
    assert "Relief-targeted optimization:" in content
    assert "Final recommended focus:" in content
    assert "Accepted Changes" in content
    assert "Rejected Changes" in content
    assert "claim changes:" in content
    assert "added claims:" in content
    assert "changed claims:" in content
    assert "remedy changes:" in content
    assert "added remedies:" in content
    assert "change-group ${normalizedTone}" in content
    assert "renderChangeGroup" in content
    assert "change-group-badge" in content
    assert "Intake Constraints" in content
    assert "Intake Evidence Snapshot" in content
    assert "Candidate claims:" in content
    assert "Candidate claim count:" in content
    assert "Candidate claim average confidence:" in content
    assert "Leading claim:" in content
    assert "Claim disambiguation:" in content
    assert "Claim ambiguity flags:" in content
    assert "Claim ambiguity details:" in content
    assert "Event ledger:" in content
    assert "Timeline anchors:" in content
    assert "Harm profile:" in content
    assert "Remedy profile:" in content
    assert "Canonical facts:" in content
    assert "Proof leads:" in content
    assert "Question candidates:" in content
    assert "Question candidate sources:" in content
    assert "Question goals:" in content
    assert "Question target sections:" in content
    assert "Question blocking levels:" in content
    assert "Packet blocking covered:" in content
    assert "Packet credible support:" in content
    assert "Packet draft ready:" in content
    assert "Packet parse quality:" in content
    assert "Packet review escalations:" in content
    assert "Packet escalations:" in content
    assert "Packet proof readiness:" in content
    assert "Packet unresolved without path:" in content
    assert "Packet unresolved chronology issues:" in content
    assert "Packet chronology issue ids:" in content
    assert "Packet completion ready:" in content
    assert "Packet temporal facts:" in content
    assert "Packet temporal relations:" in content
    assert "Packet temporal issues:" in content
    assert "Packet temporal ready elements:" in content
    assert "Packet temporal warnings:" in content
    assert "Alignment chronology tasks:" in content
    assert "Alignment chronology events:" in content
    assert "Alignment chronology relations:" in content
    assert "Alignment chronology issues:" in content
    assert "Alignment chronology targeted:" in content
    assert "Alignment chronology status:" in content
    assert "Alignment chronology blockers:" in content
    assert "Alignment chronology handoffs:" in content
    assert "Packet chronology tasks:" in content
    assert "Packet chronology targeted:" in content
    assert "Packet chronology status:" in content
    assert "Packet chronology blockers:" in content
    assert "Packet chronology handoffs:" in content
    assert "renderTriageChipRow" in content
    assert "triage-chip" in content
    assert "Question Blocking Levels" in content
    assert "Question Review Targets" in content
    assert "Question Review (" in content
    assert "defaultSupportKindForSection" in content
    assert "inferQuestionSupportKind" in content
    assert "appendSupportKindToReviewUrl" in content
    assert "Intake Claim Review" in content
    assert "Intake Section Review" in content
    assert "Packet next steps:" in content
    assert "Current intake phase:" in content
    assert "Intake readiness score:" in content
    assert "Persisted intake phase:" in content
    assert "Persisted intake contradictions:" in content
    assert "Persisted contradiction lanes:" in content
    assert "Persisted corroboration-required contradictions:" in content
    assert "Persisted contradiction target elements" in content
    assert "Persisted intake criteria:" in content


def test_chat_and_results_templates_link_to_document_workflow():
    chat_content = Path("templates/chat.html").read_text()
    results_content = Path("templates/results.html").read_text()

    assert "/document" in chat_content
    assert "Open Formal Complaint Builder" in chat_content
    assert "/claim-support-review" in chat_content
    assert "/document" in results_content
    assert "Open Formal Complaint Builder" in results_content
    assert "/claim-support-review" in results_content


def test_review_dashboard_app_registers_claim_support_review_page():
    app = create_review_dashboard_app()

    assert any(
        route.path == "/claim-support-review" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/health" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )


def test_review_surface_app_registers_dashboard_and_api_routes():
    app = create_review_surface_app(mediator=object())

    assert any(
        route.path == "/claim-support-review" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/review" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/execute-follow-up" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/documents/optimization-trace" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/document/optimization-trace" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/save-testimony" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/save-document" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/upload-document" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/document" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/documents/formal-complaint" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/health" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )


def test_review_surface_document_route_serves_builder_template():
	app = create_review_surface_app(mediator=object())
	client = TestClient(app)

	response = client.get("/document")

	assert response.status_code == 200
	assert "Formal Complaint Builder" in response.text
	assert "/api/documents/formal-complaint" in response.text


def test_review_surface_optimization_trace_route_serves_trace_template():
    app = create_review_surface_app(mediator=object())
    client = TestClient(app)

    response = client.get("/document/optimization-trace")

    assert response.status_code == 200
    assert "Optimization Trace Viewer" in response.text
    assert "/api/documents/optimization-trace?cid=" in response.text
    assert "Load Trace" in response.text
    assert "Export Trace Bundle" in response.text
    assert "Iteration Changes" in response.text
    assert "Review Snapshot" in response.text
    assert "Workflow Phase Guidance" in response.text
    assert "Accepted Only" in response.text
    assert "Rejected Only" in response.text


def test_optimization_trace_template_includes_export_and_diff_controls():
    content = Path("templates/optimization_trace.html").read_text()

    assert "exportTraceButton" in content
    assert "Export Trace Bundle" in content
    assert "data-iteration-filter=\"accepted\"" in content
    assert "data-iteration-filter=\"rejected\"" in content
    assert "traceDiffList" in content
    assert "Iteration Changes" in content
    assert "Accepted Changes" in content
    assert "Rejected Changes" in content
    assert "Workflow Phase Guidance" in content
    assert "traceWorkflowPhaseGuidance" in content
    assert "resolveWorkflowPhasePlan" in content
    assert "renderWorkflowPhaseGuidance" in content
    assert "workflow_phase_plan" in content
    assert "Recommended order:" in content
    assert "traceEvidenceList" in content
    assert "traceTemporalHandoff" in content
    assert "Intake Evidence Snapshot" in content
    assert "Claim Support Chronology Handoff" in content
    assert "Candidate claims:" in content
    assert "Candidate claim count:" in content
    assert "Candidate claim average confidence:" in content
    assert "Leading claim:" in content
    assert "Claim disambiguation:" in content
    assert "Claim ambiguity flags:" in content
    assert "Claim ambiguity details:" in content
    assert "Event ledger:" in content
    assert "Timeline anchors:" in content
    assert "Harm profile:" in content
    assert "Remedy profile:" in content
    assert "Canonical facts:" in content
    assert "Question candidates:" in content
    assert "Question candidate sources:" in content
    assert "Question goals:" in content
    assert "Question target sections:" in content
    assert "Question blocking levels:" in content
    assert "Alignment tasks:" in content
    assert "Alignment preferred lanes:" in content
    assert "Alignment fallback lanes:" in content
    assert "Alignment quality targets:" in content
    assert "Packet blocking covered:" in content
    assert "Packet credible support:" in content
    assert "Packet draft ready:" in content
    assert "Packet parse quality:" in content
    assert "Packet review escalations:" in content
    assert "Packet escalations:" in content
    assert "Packet proof readiness:" in content
    assert "Packet unresolved without path:" in content
    assert "Packet unresolved chronology issues:" in content
    assert "Packet chronology issue ids:" in content
    assert "Packet completion ready:" in content
    assert "Packet temporal facts:" in content
    assert "Packet temporal relations:" in content
    assert "Packet temporal issues:" in content
    assert "Packet temporal ready elements:" in content
    assert "Packet temporal warnings:" in content
    assert "Alignment chronology tasks:" in content
    assert "Alignment chronology events:" in content
    assert "Alignment chronology relations:" in content
    assert "Alignment chronology issues:" in content
    assert "Alignment chronology targeted:" in content
    assert "Alignment chronology status:" in content
    assert "Alignment chronology blockers:" in content
    assert "Alignment chronology handoffs:" in content
    assert "Unresolved chronology issues" in content
    assert "Chronology tasks" in content
    assert "Event refs" in content
    assert "Temporal relations" in content
    assert "Proof bundles" in content
    assert "Review chronology blockers" in content
    assert "Packet chronology tasks:" in content
    assert "Packet chronology targeted:" in content
    assert "Packet chronology status:" in content
    assert "Packet chronology blockers:" in content
    assert "Packet chronology handoffs:" in content
    assert "Corroboration-required contradictions:" in content
    assert "Contradiction lanes:" in content
    assert "Affected elements" in content
    assert "traceEvidenceTriage" in content
    assert "traceEvidenceQuestionTargets" in content
    assert "renderTriageChipRow" in content
    assert "triage-chip" in content
    assert "Question Review Targets" in content
    assert "Question Review (" in content
    assert "defaultSupportKindForSection" in content
    assert "inferQuestionSupportKind" in content
    assert "appendSupportKindToReviewUrl" in content
    assert "appendAlignmentTaskViewToReviewUrl" in content
    assert "appendClaimQueueIntentToReviewUrl" in content
    assert "traceEvidenceLinks" in content
    assert "buildTraceClaimReviewUrl" in content
    assert "buildTraceSectionReviewUrl" in content
    assert "buildTraceDashboardUrl" in content
    assert "Intake Claim Review" in content
    assert "Intake Section Review" in content
    assert "traceIntakeConfirmation" in content
    assert "Intake Summary Handoff" in content
    assert "Confirm on Review Dashboard" in content
    assert "Manual Review Blockers" in content
    assert "Pending Review Items" in content
    assert "Open ${escapeHtml(humanizeKey(claimType))} Manual Review" in content
    assert "Open ${escapeHtml(humanizeKey(claimType))} Pending Review" in content
    assert "renderGroupedList" in content
    assert "filterIterations" in content
    assert "setIterationFilter" in content
    assert "buildGroupedIterationDiffLines" in content
    assert "summarizeActorPayloadChanges" in content
    assert "summarizeChangeManifestEntry" in content
    assert "summarizePersistedChanges" in content
    assert "changed_items" in content
    assert "added_items" in content
    assert "removed_items" in content
    assert "Focus trajectory:" in content
    assert "Relief-targeted optimization:" in content
    assert "Final recommended focus:" in content
    assert "summarizeStructuredArrayField" in content
    assert "summarizeStructuredObjectField" in content
    assert "buildIterationDiffLines" in content
    assert "exportActiveTrace" in content
