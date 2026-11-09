import re
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_heavy]

from complaint_generator.workspace import (
    build_mike_handoff as package_build_mike_handoff,
    sync_mike_final_draft as package_sync_mike_final_draft,
)
import applications.complaint_workspace as complaint_workspace_module
from applications.complaint_workspace import ComplaintWorkspaceService


def test_mike_status_contract_state_transitions_and_invariants(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-contract-user"

    initial = service.get_mike_integration_status(user_id)
    assert initial["status_contract_version"] == "complaint-mike-status-v4"
    assert initial["workflow_state"]["key"] == "not_handed_off"
    assert initial["pending_sync"] is False
    assert isinstance(initial["citation_link_conflict_count"], int)
    assert isinstance(initial["citation_link_unknown_element_count"], int)
    assert initial["invariants"]["conflict_counters_non_null_numeric"] is True
    assert initial["invariants"]["recommended_action_present"] is True

    handoff = service.build_mike_handoff(user_id)
    after_handoff = service.get_mike_integration_status(user_id)
    assert handoff["handoff_id"] == after_handoff["latest_handoff_id"]
    assert after_handoff["workflow_state"]["key"] == "handoff_pending_sync"
    assert after_handoff["pending_sync"] is True
    assert after_handoff["latest_sync_handoff_id"] is None

    service.sync_mike_final_draft(
        user_id,
        body="Synced clean body",
        handoff_id=handoff["handoff_id"],
        citation_links=[{"citation_id": "cite-clean", "claim_element_id": "causation"}],
    )
    after_clean_sync = service.get_mike_integration_status(user_id)
    assert after_clean_sync["workflow_state"]["key"] == "synced_clean"
    assert after_clean_sync["pending_sync"] is False
    assert after_clean_sync["has_citation_link_conflicts"] is False
    assert "grounding_component" in after_clean_sync
    assert "proof_component" in after_clean_sync

    service.sync_mike_final_draft(
        user_id,
        body="Synced conflicting body",
        handoff_id=handoff["handoff_id"],
        citation_links=[
            {"citation_id": "cite-conflict", "claim_element_id": "causation"},
            {"citation_id": "cite-conflict", "claim_element_id": "harm"},
            {"citation_id": "cite-unknown", "claim_element_id": "unknown"},
        ],
    )
    after_conflict_sync = service.get_mike_integration_status(user_id)
    assert after_conflict_sync["workflow_state"]["key"] == "synced_with_conflicts"
    assert after_conflict_sync["has_citation_link_conflicts"] is True
    assert after_conflict_sync["conflict_component"]["conflict_count"] == 1
    assert after_conflict_sync["conflict_component"]["unknown_element_count"] == 1
    assert after_conflict_sync["invariants"]["pending_sync_implies_handoff"] is True
    assert after_conflict_sync["invariants"]["synced_handoff_never_pending"] is True
    assert "router_policy" in after_conflict_sync


def test_mike_ui_state_contract_keys_are_shared_across_surfaces():
    repo_root = Path(__file__).resolve().parent.parent
    workspace_content = (repo_root / "templates" / "workspace.html").read_text()
    document_content = (repo_root / "templates" / "document.html").read_text()
    dashboard_content = (repo_root / "applications" / "dashboard_ui.py").read_text()

    expected_keys = [
        "not_handed_off",
        "handoff_pending_sync",
        "synced_clean",
        "synced_with_conflicts",
    ]

    for key in expected_keys:
        assert key in workspace_content
        assert key in document_content
        assert key in dashboard_content


def test_mike_status_guardrail_copy_mentions_stale_or_missing_contract_across_surfaces():
    repo_root = Path(__file__).resolve().parent.parent
    workspace_content = (repo_root / "templates" / "workspace.html").read_text()
    document_content = (repo_root / "templates" / "document.html").read_text()
    dashboard_content = (repo_root / "applications" / "dashboard_ui.py").read_text()

    assert "status_contract_version" in workspace_content
    assert "status_contract_version" in document_content
    assert "status_contract_version" in dashboard_content
    assert "stale — refresh before export" in workspace_content
    assert "stale — refresh before export" in document_content
    assert "stale or missing contract metadata" in dashboard_content


def test_mike_sync_uses_latest_handoff_when_handoff_id_is_omitted(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-handoff-fallback-user"
    handoff = service.build_mike_handoff(user_id)

    service.sync_mike_final_draft(
        user_id,
        body="Synced body without explicit handoff id",
    )

    status = service.get_mike_integration_status(user_id)
    assert status["latest_handoff_id"] == handoff["handoff_id"]
    assert status["latest_sync_handoff_id"] == handoff["handoff_id"]
    assert status["pending_sync"] is False


def test_mike_sync_preserves_intentional_body_whitespace(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-whitespace-user"
    service.build_mike_handoff(user_id)
    original_body = "\n  Final draft body with intentional spacing  \n"

    service.sync_mike_final_draft(user_id, body=original_body)

    session = service.get_session(user_id)
    assert session["session"]["draft"]["body"] == original_body


def test_local_edits_after_mike_sync_mark_status_as_not_current(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-local-edit-user"
    handoff = service.build_mike_handoff(user_id)
    service.sync_mike_final_draft(user_id, body="Synced Mike body", handoff_id=handoff["handoff_id"])

    synced_status = service.get_mike_integration_status(user_id)
    assert synced_status["workflow_state"]["key"] == "synced_clean"

    service.update_draft(user_id, body="Locally edited body after sync")

    diverged_status = service.get_mike_integration_status(user_id)
    assert diverged_status["has_mike_synced_draft"] is False
    assert diverged_status["workflow_state"]["key"] == "handoff_pending_sync"


def test_package_sync_wrapper_passes_structured_deltas_and_editor_metadata(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-package-wrapper-user"
    package_build_mike_handoff(user_id, service=service)

    package_sync_mike_final_draft(
        user_id,
        body="Package wrapper synced body",
        structured_deltas=[{"op": "replace", "target": "paragraph-1", "before": "old", "after": "new"}],
        editor_metadata={"editor_user_id": "wrapper-editor", "channel": "package-api"},
        service=service,
    )

    session = service.get_session(user_id)
    sync_metadata = session["session"]["draft"]["sync_metadata"]
    assert sync_metadata["structured_deltas"][0]["target"] == "paragraph-1"
    assert sync_metadata["editor_metadata"]["editor_user_id"] == "wrapper-editor"


def test_mike_handoff_exposes_router_grounding_logic_and_submodule_contracts(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    service.submit_intake_answers(
        "handoff-contract-user",
        {
            "party_name": "Taylor Smith",
            "opposing_party": "Acme Logistics",
            "protected_activity": "Reported safety violations",
            "adverse_action": "Termination",
            "timeline": "Reported on April 2; terminated on April 5",
            "harm": "Lost wages",
        },
    )

    payload = service.build_mike_handoff("handoff-contract-user", grounding_mode="legal_corpus_only")
    handoff_payload = payload["handoff_payload"]

    assert payload["contract_versions"]["handoff"] == "complaint-mike-handoff-v4"
    assert handoff_payload["router_policy"]["provider_policy_source"] == "complaint_generator"
    assert handoff_payload["grounding_mode"] == "legal_corpus_only"
    assert handoff_payload["corpus_boundaries"]["strict_legal_containment"] is True
    assert {
        item["adapter"] for item in handoff_payload["corpus_boundaries"]["adapter_lane"]
    } == {
        "integrations/ipfs_datasets/legal.py",
        "integrations/ipfs_datasets/search.py",
        "integrations/ipfs_datasets/policy_rules.py",
        "integrations/ipfs_datasets/graphs.py",
    }
    assert "logic_handoff" in handoff_payload
    assert handoff_payload["skill_asset_manifest"]["version"] == "complaint-mike-skill-assets-v2"
    assert "complaint-grounding" in handoff_payload["skill_asset_manifest"]["asset_ids"]
    assert "complaint-corpus-search" in handoff_payload["skill_asset_manifest"]["asset_ids"]
    assert "complaint-policy-rules" in handoff_payload["skill_asset_manifest"]["asset_ids"]
    assert "complaint-authority-graphs" in handoff_payload["skill_asset_manifest"]["asset_ids"]
    assert "submodule_inventory" in handoff_payload
    assert "compatibility_target_matrix" in handoff_payload
    assert handoff_payload["submodule_inventory"]["mike"]["skill_asset_count"] >= 1
    assert handoff_payload["submodule_inventory"]["mike"]["commit"] != "unavailable"
    assert handoff_payload["submodule_inventory"]["mike"]["origin_main_commit"] != "unavailable"
    assert handoff_payload["submodule_inventory"]["ipfs_datasets_py"]["commit"] != "unavailable"
    assert handoff_payload["submodule_inventory"]["ipfs_datasets_py"]["origin_main_commit"] != "unavailable"
    assert re.fullmatch(r"[0-9a-f]{40}", handoff_payload["submodule_inventory"]["mike"]["commit"])
    assert re.fullmatch(r"[0-9a-f]{40}", handoff_payload["submodule_inventory"]["mike"]["origin_main_commit"])
    assert re.fullmatch(r"[0-9a-f]{40}", handoff_payload["submodule_inventory"]["ipfs_datasets_py"]["commit"])
    assert re.fullmatch(r"[0-9a-f]{40}", handoff_payload["submodule_inventory"]["ipfs_datasets_py"]["origin_main_commit"])
    assert re.fullmatch(r"[0-9a-f]{40}", handoff_payload["compatibility_target_matrix"]["submodule_shas"]["mike_commit"])
    assert re.fullmatch(
        r"[0-9a-f]{40}",
        handoff_payload["compatibility_target_matrix"]["submodule_shas"]["mike_origin_main_commit"],
    )
    assert re.fullmatch(
        r"[0-9a-f]{40}",
        handoff_payload["compatibility_target_matrix"]["submodule_shas"]["ipfs_datasets_py_commit"],
    )
    assert re.fullmatch(
        r"[0-9a-f]{40}",
        handoff_payload["compatibility_target_matrix"]["submodule_shas"]["ipfs_datasets_py_origin_main_commit"],
    )
    for sha_key in (
        "ipfs_accelerate_py_commit",
        "ipfs_accelerate_py_origin_main_commit",
        "ipfs_kit_py_commit",
        "ipfs_kit_py_origin_main_commit",
    ):
        assert re.fullmatch(
            r"[0-9a-f]{40}",
            handoff_payload["compatibility_target_matrix"]["submodule_shas"][sha_key],
        )
    mike_integration = handoff_payload["mike_integration"]
    assert mike_integration["transport"] == "mcp_connector"
    assert mike_integration["tools"] == [
        "complaint.generate_grounded_text",
        "complaint.search_corpus",
        "complaint.get_handoff",
        "complaint.sync_draft",
    ]
    assert mike_integration["connector_url"].endswith("/api/complaint-workspace/mcp/rpc")
    assert handoff_payload["submodule_inventory"]["strategy"]["mike"] == "external/mike@origin/main"
    assert "grounding_mode" in payload["sync_contract"]["optional_fields"]
    assert "assertion_annotations" in payload["sync_contract"]["optional_fields"]
    assert "authority_links" in payload["sync_contract"]["optional_fields"]


def test_mike_safe_read_git_ref_handles_edge_cases(tmp_path, monkeypatch):
    missing_dir = tmp_path / "missing-submodule"
    assert ComplaintWorkspaceService._safe_read_git_ref(missing_dir, "HEAD") == "unavailable"

    file_path = tmp_path / "not-a-dir.txt"
    file_path.write_text("noop")
    assert ComplaintWorkspaceService._safe_read_git_ref(file_path, "HEAD") == "unavailable"

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    def _raise_called_process_error(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=["git"])

    monkeypatch.setattr(complaint_workspace_module.subprocess, "run", _raise_called_process_error)
    assert ComplaintWorkspaceService._safe_read_git_ref(repo_dir, "HEAD") == "unavailable"

    monkeypatch.setattr(
        complaint_workspace_module.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"stdout": ""})(),
    )
    assert ComplaintWorkspaceService._safe_read_git_ref(repo_dir, "HEAD") == "unavailable"

def test_mike_sync_persists_grounding_logic_and_release_gate_blockers(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-grounding-user"
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Taylor Smith",
            "opposing_party": "Acme Logistics",
            "protected_activity": "Reported safety violations to HR",
            "adverse_action": "Was terminated three days later",
            "timeline": "Reported on April 2; terminated on April 5",
            "harm": "Lost wages and benefits",
        },
    )
    handoff = service.build_mike_handoff(user_id)

    sync_payload = service.sync_mike_final_draft(
        user_id,
        body="Defendant unlawfully retaliated against Plaintiff. Plaintiff seeks damages and fees.",
        handoff_id=handoff["handoff_id"],
        grounding_mode="legal_corpus_only",
        assertion_annotations=[
            {
                "assertion_id": "a-1",
                "text": "Defendant unlawfully retaliated against Plaintiff.",
                "assertion_type": "legal_conclusion",
                "grounded": False,
            },
            {
                "assertion_id": "a-2",
                "text": "Plaintiff seeks damages and fees.",
                "assertion_type": "requested_relief",
                "grounded": True,
                "authority_ids": ["relief-1"],
            },
        ],
        authority_links=[
            {
                "authority_id": "relief-1",
                "authority_type": "statute",
                "citation": "42 U.S.C. § 1988",
                "source": "federal_statutes",
                "assertion_ids": ["a-2"],
            }
        ],
        sync_provenance={
            "editor_version": "mike-test",
            "skill_asset_ids": ["complaint-grounding"],
            "redline_metadata": {"summary": "Tightened retaliation theory."},
        },
    )

    assert sync_payload["legal_corpus_review"]["has_blockers"] is True
    assert {
        item["adapter"] for item in sync_payload["legal_corpus_review"]["adapter_lane"]
    } == {
        "integrations/ipfs_datasets/legal.py",
        "integrations/ipfs_datasets/search.py",
        "integrations/ipfs_datasets/policy_rules.py",
        "integrations/ipfs_datasets/graphs.py",
    }
    assert sync_payload["logic_review"]["has_blockers"] is True
    assert sync_payload["draft"]["sync_metadata"]["sync_provenance"]["editor_version"] == "mike-test"
    assert sync_payload["sync_provenance"]["enabled_skill_ids"] == ["complaint-grounding"]
    assert sync_payload["sync_provenance"]["base_draft_identity"]["hash"]
    assert sync_payload["redline_metadata"]["structured_delta_count"] == 0
    assert sync_payload["logic_review"]["leanstral_assist"]["bypass_release_gate"] is False

    gate = service.get_client_release_gate(user_id)
    assert gate["complaint_output_release_gate"]["verdict"] == "blocked"
    assert "Legal-corpus-only mode" in gate["complaint_output_release_gate"]["reason"]
    assert "Formal proof coverage, contradiction, or chronology checks are still failing" in gate["complaint_output_release_gate"]["reason"]


def test_mike_sync_preserves_router_policy_ownership(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-router-policy-user"
    handoff = service.build_mike_handoff(user_id)

    handoff_payload = handoff["handoff_payload"]
    assert "complaint-router" in handoff_payload["skill_asset_manifest"]["asset_ids"]
    assert handoff_payload["router_policy"]["provider_policy_source"] == "complaint_generator"
    assert handoff_payload["router_policy"]["narrow_adapter_boundary"]["mike_requests_generation_via_workspace"] is True
    assert handoff_payload["router_policy"]["narrow_adapter_boundary"]["mike_does_not_choose_provider"] is True
    assert handoff_payload["router_policy"]["narrow_adapter_boundary"]["mike_does_not_choose_model"] is True

    sync_payload = service.sync_mike_final_draft(
        user_id,
        body="Plaintiff reported safety concerns. Defendant terminated Plaintiff shortly after.",
        handoff_id=handoff["handoff_id"],
        sync_provenance={
            "editor_version": "mike-web",
            "skill_asset_ids": ["complaint-router", "complaint-logic", "unknown-skill"],
            "redline_metadata": {"summary": "Applied complaint-owned routing edits."},
        },
        structured_deltas=[{"op": "replace", "target": "paragraph-001", "before": "old", "after": "new"}],
    )

    assert sync_payload["router_policy"]["provider_policy_source"] == "complaint_generator"
    assert sync_payload["router_policy"]["narrow_adapter_boundary"]["mike_requests_generation_via_workspace"] is True
    assert sync_payload["sync_provenance"]["enabled_skill_ids"] == ["complaint-router", "complaint-logic"]
    assert sync_payload["sync_provenance"]["unknown_skill_asset_ids"] == ["unknown-skill"]
    assert sync_payload["sync_provenance"]["base_draft_identity"]["hash"]
    assert sync_payload["redline_metadata"]["structured_delta_count"] == 1

    status_payload = service.get_mike_integration_status(user_id)
    assert status_payload["router_policy"]["provider_policy_source"] == "complaint_generator"


def test_formal_diagnostics_include_mike_grounding_and_logic_snapshot(tmp_path, monkeypatch):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-formal-diagnostics-user"
    handoff = service.build_mike_handoff(user_id)
    service.sync_mike_final_draft(
        user_id,
        body="Plaintiff reported discrimination on March 1. Defendant terminated Plaintiff on March 3.",
        handoff_id=handoff["handoff_id"],
    )

    monkeypatch.setattr(
        service,
        "analyze_complaint_output",
        lambda user_id: {
            "user_id": user_id,
            "ui_feedback": {
                "claim_type_alignment_score": 75,
                "filing_shape_score": 80,
                "release_gate": {"verdict": "warning"},
                "formal_diagnostics": {"release_gate_verdict": "warning"},
                "router_review": {"backend": {"provider": "template"}},
            },
            "packet_summary": {
                "has_draft": True,
                "draft_strategy": "template",
                "formal_defect_count": 0,
                "high_severity_issue_count": 0,
                "complaint_output_router_backend": {"provider": "template"},
            },
        },
    )
    monkeypatch.setattr(
        service,
        "build_export_artifact",
        lambda user_id, output_format="markdown": {
            "filename": "complaint.md",
            "media_type": "text/markdown",
            "body": b"COMPLAINT\n\n1. Plaintiff reported discrimination.\n2. Defendant terminated Plaintiff.\n",
        },
    )

    payload = service.get_formal_diagnostics(user_id)
    assert "mike_grounding" in payload
    assert "mike_logic" in payload
    assert "mike_sync_diagnostics" in payload


def test_mike_sync_logic_review_contains_proof_pipeline_fields(tmp_path):
    """After sync_mike_final_draft, logic_review must expose proof-pipeline fields."""
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-proof-pipeline-user"
    handoff = service.build_mike_handoff(user_id)

    sync_payload = service.sync_mike_final_draft(
        user_id,
        body=(
            "Plaintiff reported safety violations to HR on January 15. "
            "Defendant terminated Plaintiff on January 17. "
            "Plaintiff seeks back pay, compensatory damages, and attorneys fees."
        ),
        handoff_id=handoff["handoff_id"],
    )

    logic_review = sync_payload["logic_review"]
    # Core proof fields must always be present.
    assert "proof_status" in logic_review
    assert "contradiction_count" in logic_review
    assert "chronology_blocked" in logic_review
    assert "has_blockers" in logic_review
    assert isinstance(logic_review["proof_status"], str)
    assert isinstance(logic_review["contradiction_count"], int)
    assert isinstance(logic_review["chronology_blocked"], bool)
    assert isinstance(logic_review["has_blockers"], bool)

    # Pipeline-injected fields must be present (even when pipeline is disabled).
    assert "ungrounded_assertions" in logic_review
    assert "corpus_coverage_percent" in logic_review
    assert "pipeline_norms" in logic_review
    assert "pipeline_policy_violations" in logic_review
    assert "pipeline_policy_warnings" in logic_review
    assert "draft_proof_pipeline_version" in logic_review
    assert isinstance(logic_review["ungrounded_assertions"], list)
    assert isinstance(logic_review["pipeline_norms"], list)
    assert isinstance(logic_review["pipeline_policy_violations"], list)

    # Editor guardrails must expose corpus_coverage_percent and ungrounded_assertions.
    # guardrails are computed from logic_review in _build_mike_editor_guardrails.
    # We can verify the guardrails contract via a direct call.
    from applications.complaint_workspace import ComplaintWorkspaceService as _WS
    review = service._build_review(service._load_state(user_id))
    guardrails = _WS._build_mike_editor_guardrails(
        review,
        legal_corpus_review={},
        logic_review=logic_review,
    )
    assert "proof_readiness_flags" in guardrails
    prf = guardrails["proof_readiness_flags"]
    assert "ungrounded_assertion_count" in prf
    assert isinstance(prf["ungrounded_assertion_count"], int)
    assert "ungrounded_assertions" in guardrails
    assert isinstance(guardrails["ungrounded_assertions"], list)


def test_mike_assertion_classifier_covers_relief_temporal_legal_and_factual_cases():
    assert ComplaintWorkspaceService._classify_mike_assertion_type("Plaintiff seeks injunctive relief and damages.") == "requested_relief"
    assert ComplaintWorkspaceService._classify_mike_assertion_type("On March 3, Defendant terminated Plaintiff after the complaint.") == "temporal_assertion"
    assert ComplaintWorkspaceService._classify_mike_assertion_type("Defendant unlawfully retaliated against Plaintiff.") == "legal_conclusion"
    assert ComplaintWorkspaceService._classify_mike_assertion_type("Plaintiff reported safety concerns to HR in writing.") == "factual_statement"
    assert ComplaintWorkspaceService._classify_mike_assertion_type("") == "unsupported_rhetoric"
    assert ComplaintWorkspaceService._classify_mike_assertion_type("Too vague.") == "unsupported_rhetoric"
