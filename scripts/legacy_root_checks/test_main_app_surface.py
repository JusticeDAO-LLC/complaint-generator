from fastapi.testclient import TestClient

from main import app


def test_main_app_exposes_unified_complaint_surface_routes():
    client = TestClient(app)

    landing = client.get("/")
    assert landing.status_code == 200
    assert "Lex Publicus Complaint Generator" in landing.text

    workspace = client.get("/workspace")
    assert workspace.status_code == 200
    assert "Unified Complaint Workspace" in workspace.text

    review = client.get("/claim-support-review")
    assert review.status_code == 200
    assert "Operator Review Surface" in review.text

    builder = client.get("/document")
    assert builder.status_code == 200
    assert "Formal Complaint Builder" in builder.text

    session = client.get("/api/complaint-workspace/session")
    assert session.status_code == 200
    payload = session.json()
    assert payload["session"]["user_id"]
    assert "review" in payload

    handoff = client.post(
        "/api/complaint-workspace/mike/handoff",
        json={
            "user_id": payload["session"]["user_id"],
            "project_id": "project-demo",
            "workspace_id": "workspace-demo",
        },
    )
    assert handoff.status_code == 200
    handoff_payload = handoff.json()
    assert handoff_payload["handoff_id"].startswith("mike-handoff-")
    assert handoff_payload["mike"]["launch_url"]
    handoff_data = handoff_payload.get("handoff_payload") or {}
    evidence_context = handoff_data.get("evidence_context") or {}
    assert evidence_context.get("elements")
    claim_element_ids = list((evidence_context.get("elements") or {}).keys())
    assert len(claim_element_ids) >= 2
    mike_status_after_handoff = client.get(
        "/api/complaint-workspace/mike/status",
        params={"user_id": payload["session"]["user_id"]},
    )
    assert mike_status_after_handoff.status_code == 200
    handoff_status_payload = mike_status_after_handoff.json()
    assert handoff_status_payload["pending_sync"] is True
    assert handoff_status_payload["status_contract_version"] == "complaint-mike-status-v2"
    assert handoff_status_payload["workflow_state"]["key"] == "handoff_pending_sync"
    assert isinstance(handoff_status_payload["has_citation_link_conflicts"], bool)
    assert isinstance(handoff_status_payload["citation_link_conflict_count"], int)
    assert isinstance(handoff_status_payload["citation_link_unknown_element_count"], int)
    assert isinstance(handoff_status_payload["recommended_action"], str)
    assert handoff_status_payload["recommended_action"].strip()

    synced_body = "This draft body was synced from Mike."
    sync = client.post(
        "/api/complaint-workspace/mike/sync",
        json={
            "user_id": payload["session"]["user_id"],
            "handoff_id": handoff_payload["handoff_id"],
            "title": "Synced Draft",
            "body": synced_body,
            "citation_links": [
                {"citation_id": "doc-100", "claim_element_id": claim_element_ids[0]},
                {"citation_id": "doc-100", "claim_element_id": claim_element_ids[1]},
                {"citation_id": "doc-200", "claim_element_id": "unknown"},
            ],
            "structured_deltas": [
                {"op": "replace", "target": "paragraph-001", "before": "old", "after": "new"},
            ],
            "editor_metadata": {
                "editor_user_id": "editor-demo",
                "editor_session_id": "session-1",
                "source_transport": "http",
            },
        },
    )
    assert sync.status_code == 200
    sync_payload = sync.json()
    assert sync_payload["draft"]["title"] == "Synced Draft"
    assert sync_payload["draft"]["sync_source"] == "mike"
    assert sync_payload["sync_record"]["handoff_id"] == handoff_payload["handoff_id"]
    assert sync_payload["sync_record"]["body_chars"] == len(synced_body)
    assert sync_payload["sync_record"]["citation_link_conflict_count"] == 1
    assert sync_payload["sync_record"]["citation_link_has_conflicts"] is True
    assert sync_payload["sync_record"]["structured_delta_count"] == 1
    assert sync_payload["sync_record"]["editor_user_id"] == "editor-demo"
    assert sync_payload["sync_diagnostics"]["severity"] == "error"
    assert sync_payload["citation_link_check"]["unknown_claim_element_ids"] == ["unknown"]
    # We intentionally conflict the first two known element IDs with the same citation ID.
    expected_conflict_elements = sorted([claim_element_ids[0], claim_element_ids[1]])
    assert sync_payload["citation_link_check"]["conflicts"] == [
        {"citation_id": "doc-100", "claim_element_ids": expected_conflict_elements}
    ]
    mike_status_after_sync = client.get(
        "/api/complaint-workspace/mike/status",
        params={"user_id": payload["session"]["user_id"]},
    )
    assert mike_status_after_sync.status_code == 200
    status_payload = mike_status_after_sync.json()
    assert status_payload["pending_sync"] is False
    assert status_payload["workflow_state"]["key"] == "synced_with_conflicts"
    assert status_payload["has_mike_synced_draft"] is True
    assert status_payload["has_citation_link_conflicts"] is True
    assert status_payload["citation_link_conflict_count"] == 1
    assert status_payload["citation_link_unknown_element_count"] == 1
    assert status_payload["conflict_component"]["conflict_count"] == 1
    assert status_payload["invariants"]["pending_sync_implies_handoff"] is True
    assert status_payload["invariants"]["synced_handoff_never_pending"] is True
    assert "Resolve conflicts in Mike and sync again before export." in status_payload["recommended_action"]
