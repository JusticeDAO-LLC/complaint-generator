"""Workflow stage and draft review follow live domain state.

Checkbox maps do not advance readiness. Draft, review, and export are
versioned and separately authorized. Export does not file with a court and
does not claim legal sufficiency.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import BrowserSessionConfiguration, BrowserSessionService, PrincipalStoreCredentialAdapter
from applications.case_access import CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_review import DRAFT_EXPORTS_ROUTE, DRAFT_REVIEWS_ROUTE, DRAFT_VERSIONS_ROUTE, WORKFLOW_STAGE_ROUTE
from applications.case_routes import PROTECTED_PREFIXES, CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]


def _domains(*, proof_status="executed", proof_result="verified", factual_revision=1):
    return {
        "factual": {
            "status": "current",
            "revision": factual_revision,
            "complete": True,
            "assertions": [{"id": "fact-1", "bound": True, "revision": factual_revision}],
        },
        "legal": {
            "status": "admitted",
            "revision": 2,
            "factual_revision": factual_revision,
            "authority_id": "auth-synthetic",
            "governing_law": True,
        },
        "evidence": {
            "status": "bound",
            "revision": 3,
            "factual_revision": factual_revision,
            "legal_revision": 2,
            "exhibits": [{"id": "exhibit-1", "supports_factual_revision": factual_revision}],
        },
        "proof": {
            "status": proof_status,
            "result": proof_result,
            "revision": 4,
            "factual_revision": factual_revision,
            "evidence_revision": 3,
            "complete": True,
        },
    }


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    reader = principals.install_server_role(role="lawyer")
    exporter = principals.install_server_role(role="lawyer")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    common = dict(owner_principal_id=owner.principal_id, case_id=case.case_id, resource_id=case.resource_id,
                  tenant_id=case.tenant_id, expected_case_revision=case.revision)
    lawyer_grant = authorizer.grant_assigned_lawyer(
        lawyer_principal_id=lawyer.principal_id, actions=frozenset({"case.read", "case.review"}), **common)
    authorizer.grant_assigned_lawyer(
        lawyer_principal_id=reader.principal_id, actions=frozenset({"case.read"}), **common)
    export_grant = authorizer.grant_assigned_lawyer(
        lawyer_principal_id=exporter.principal_id,
        actions=frozenset({"case.read", "case.review", "case.download"}), **common)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            "synthetic-owner-credential": owner.principal_id,
            "synthetic-lawyer-credential": lawyer.principal_id,
            "synthetic-reader-credential": reader.principal_id,
            "synthetic-exporter-credential": exporter.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=300,
    ))
    mediator = SimpleNamespace(intake_case_file={})
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id),
                  authorize_delegated=lambda decision: decision.membership == "assigned-lawyer")
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
                        include_workspace=False, include_review=False, include_document=True)
    return SimpleNamespace(case=case, app=app, mediator=mediator, lawyer_grant=lawyer_grant, export_grant=export_grant)


def _client(app):
    return TestClient(app, base_url="https://testserver")


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _headers(case, csrf, membership_revision=None):
    headers = {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision),
        "x-csrf-token": csrf,
    }
    if membership_revision is not None:
        headers["x-expected-membership-revision"] = str(membership_revision)
    return headers


def _stage_path(case_id):
    return f"/api/documents/{case_id}/workflow-stage"


def test_workspace_states_stage_is_not_checkbox_completion_or_filing():
    html = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    assert 'id="derived-workflow-stage"' in html
    assert 'data-checkbox-completion="ignored"' in html
    assert 'data-automatic-court-filing="false"' in html
    assert 'data-legal-sufficiency="false"' in html
    assert "Checked boxes do not complete a stage." in html
    assert "Export does not file with a court and is not a claim of legal sufficiency." in html
    for route in (WORKFLOW_STAGE_ROUTE, DRAFT_VERSIONS_ROUTE, DRAFT_REVIEWS_ROUTE, DRAFT_EXPORTS_ROUTE):
        assert any(route.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)


def test_checkboxes_do_not_advance_stage_or_authorize_export(tmp_path):
    world = _world(tmp_path)
    world.mediator.intake_case_file = {
        "workflow_checkboxes": {
            "facts_complete": True,
            "legal_complete": True,
            "evidence_complete": True,
            "proof_complete": True,
            "ready_to_file": True,
        },
        "workflow_domains": {"factual": {"complete": True, "checked": True}},
    }
    client = _client(world.app)
    csrf = _login(client, "synthetic-owner-credential")
    stage = client.get(_stage_path(world.case.case_id), headers=_headers(world.case, csrf))
    assert stage.status_code == 200, stage.text
    body = stage.json()
    assert body["stage"] == "factual_unresolved"
    assert body["readiness"]["checkbox_completion_counts"] is False
    assert body["readiness"]["ready_for_draft_review"] is False
    assert body["readiness"]["legal_sufficiency"] is False
    assert body["readiness"]["court_filed"] is False
    assert "facts_complete" in body["readiness"]["ignored_checkbox_keys"]
    assert body["owner_actions"] == ["record_current_facts"]
    assert body["download_scoped_actions"] == []
    assert "file_with_court" in body["refused_actions"]
    version = client.post(
        f"/api/documents/{world.case.case_id}/draft-versions",
        headers=_headers(world.case, csrf),
        json={"request_id": "draft-too-soon", "draft_id": "draft-1", "text": "Synthetic paragraph."},
    )
    assert version.status_code == 422
    assert version.json()["detail"] == "stage_not_ready"
    assert world.mediator.intake_case_file.get("draft_workflow") is None


def test_version_review_and_export_stay_scoped_and_do_not_file(tmp_path):
    world = _world(tmp_path)
    world.mediator.intake_case_file = {"workflow_domains": _domains()}
    owner = _client(world.app)
    lawyer = _client(world.app)
    owner_csrf = _login(owner, "synthetic-owner-credential")
    stage = owner.get(_stage_path(world.case.case_id), headers=_headers(world.case, owner_csrf))
    assert stage.status_code == 200, stage.text
    projected = stage.json()
    assert projected["stage"] == "draft_review"
    assert projected["domains"]["legal"]["governing_law"] is False
    assert projected["domains"]["proof"]["legal_sufficiency"] is False
    assert projected["owner_actions"] == ["version_draft", "review_draft"]
    assert projected["lawyer_actions"] == ["review_draft"]
    assert projected["download_scoped_actions"] == []
    lawyer_csrf = _login(lawyer, "synthetic-lawyer-credential")
    lawyer_headers = _headers(world.case, lawyer_csrf, world.lawyer_grant.revision)
    refused_version = lawyer.post(
        f"/api/documents/{world.case.case_id}/draft-versions",
        headers=lawyer_headers,
        json={"request_id": "lawyer-draft", "draft_id": "draft-1", "text": "Synthetic paragraph."},
    )
    assert refused_version.status_code == 403
    assert refused_version.json()["error"] == "action_not_permitted"
    version = owner.post(
        f"/api/documents/{world.case.case_id}/draft-versions",
        headers=_headers(world.case, owner_csrf),
        json={"request_id": "owner-draft", "draft_id": "draft-1", "text": "Synthetic paragraph."},
    )
    assert version.status_code == 200, version.text
    created = version.json()
    assert created["record"]["revision"] == 1
    assert created["record"]["legal_sufficiency"] is False
    assert created["record"]["court_filed"] is False
    digest = created["text_digest"]
    replay = owner.post(
        f"/api/documents/{world.case.case_id}/draft-versions",
        headers=_headers(world.case, owner_csrf),
        json={"request_id": "owner-draft", "draft_id": "draft-1", "text": "Synthetic paragraph."},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["record"]["revision"] == 1
    mismatch = owner.post(
        f"/api/documents/{world.case.case_id}/draft-versions",
        headers=_headers(world.case, owner_csrf),
        json={"request_id": "owner-draft", "draft_id": "draft-1", "text": "Different paragraph."},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"] == "replay_mismatch"
    filing = owner.post(
        f"/api/documents/{world.case.case_id}/draft-exports",
        headers=_headers(world.case, owner_csrf),
        json={"operation": "file_with_court", "request_id": "file-1", "draft_id": "draft-1", "expected_revision": 1},
    )
    assert filing.status_code == 403
    assert filing.json()["detail"] == "automatic_filing_refused"
    sufficiency = lawyer.post(
        f"/api/documents/{world.case.case_id}/draft-reviews",
        headers=lawyer_headers,
        json={"request_id": "review-claim", "draft_id": "draft-1", "expected_revision": 1,
              "expected_text_digest": digest, "decision": "accepted_for_export", "legal_sufficiency": True},
    )
    assert sufficiency.status_code == 403
    assert sufficiency.json()["detail"] == "legal_sufficiency_refused"
    early_export = owner.post(
        f"/api/documents/{world.case.case_id}/draft-exports",
        headers=_headers(world.case, owner_csrf),
        json={"request_id": "export-early", "draft_id": "draft-1", "expected_revision": 1},
    )
    assert early_export.status_code == 422
    assert early_export.json()["detail"] == "review_required"
    review = lawyer.post(
        f"/api/documents/{world.case.case_id}/draft-reviews",
        headers=lawyer_headers,
        json={"request_id": "review-1", "draft_id": "draft-1", "expected_revision": 1,
              "expected_text_digest": digest, "decision": "accepted_for_export"},
    )
    assert review.status_code == 200, review.text
    reviewed = review.json()
    assert reviewed["record"]["authorizes_export"] is True
    assert reviewed["record"]["legal_sufficiency"] is False
    assert reviewed["record"]["court_filed"] is False
    assert reviewed["readiness"]["ready_for_versioned_export"] is True
    blocked_export = lawyer.post(
        f"/api/documents/{world.case.case_id}/draft-exports",
        headers=lawyer_headers,
        json={"request_id": "export-lawyer", "draft_id": "draft-1", "expected_revision": 1},
    )
    assert blocked_export.status_code == 403
    assert blocked_export.json()["error"] == "action_not_permitted"
    exported = owner.post(
        f"/api/documents/{world.case.case_id}/draft-exports",
        headers=_headers(world.case, owner_csrf),
        json={"request_id": "export-1", "draft_id": "draft-1", "expected_revision": 1},
    )
    assert exported.status_code == 200, exported.text
    envelope = exported.json()["record"]
    assert envelope["status"] == "exported"
    assert envelope["authorization_scope"] == "case.download"
    assert envelope["legal_sufficiency"] is False
    assert envelope["court_filed"] is False
    assert envelope["automatic_court_filing"] is False
    assert "text" not in envelope
    store = world.mediator.intake_case_file["draft_workflow"]
    assert len(store["versions"]) == 1
    assert len(store["exports"]) == 1
    assert all(item.get("court_filed") is False for item in store["exports"])


def test_stale_domain_and_unexecuted_proof_block_export(tmp_path):
    world = _world(tmp_path)
    world.mediator.intake_case_file = {"workflow_domains": _domains(proof_status="not_executed", proof_result="pending")}
    owner = _client(world.app)
    exporter = _client(world.app)
    reader = _client(world.app)
    csrf = _login(owner, "synthetic-owner-credential")
    stage = owner.get(_stage_path(world.case.case_id), headers=_headers(world.case, csrf))
    assert stage.status_code == 200, stage.text
    assert stage.json()["stage"] == "proof_unresolved"
    assert stage.json()["owner_actions"] == ["record_current_proof"]
    assert stage.json()["lawyer_actions"] == ["review_proof_gap"]
    assert stage.json()["readiness"]["ready_for_draft_review"] is False
    world.mediator.intake_case_file["workflow_domains"] = _domains()
    version = owner.post(
        f"/api/documents/{world.case.case_id}/draft-versions",
        headers=_headers(world.case, csrf),
        json={"request_id": "owner-draft", "draft_id": "draft-1", "text": "Synthetic paragraph."},
    )
    digest = version.json()["text_digest"]
    exporter_csrf = _login(exporter, "synthetic-exporter-credential")
    exporter_headers = _headers(world.case, exporter_csrf, world.export_grant.revision)
    review = exporter.post(
        f"/api/documents/{world.case.case_id}/draft-reviews",
        headers=exporter_headers,
        json={"request_id": "review-1", "draft_id": "draft-1", "expected_revision": 1,
              "expected_text_digest": digest, "decision": "accepted_for_export"},
    )
    assert review.status_code == 200, review.text
    world.mediator.intake_case_file["workflow_domains"]["factual"]["revision"] = 9
    world.mediator.intake_case_file["workflow_domains"]["factual"]["assertions"][0]["revision"] = 9
    drifted = owner.post(
        f"/api/documents/{world.case.case_id}/draft-exports",
        headers=_headers(world.case, csrf),
        json={"request_id": "export-stale", "draft_id": "draft-1", "expected_revision": 1},
    )
    assert drifted.status_code == 409
    assert drifted.json()["detail"] == "stale_domain"
    assert world.mediator.intake_case_file["draft_workflow"].get("exports") == []
    reader_csrf = _login(reader, "synthetic-reader-credential")
    denied = reader.post(
        f"/api/documents/{world.case.case_id}/draft-reviews",
        headers=_headers(world.case, reader_csrf, 1),
        json={"request_id": "reader-review", "draft_id": "draft-1", "expected_revision": 1,
              "expected_text_digest": digest, "decision": "commented"},
    )
    assert denied.status_code == 403
