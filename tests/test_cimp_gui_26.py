"""Versioned-source review against actual local acquisition and Mediator contracts.

Source storage admission is distinct from applicability to a case and from a
proof. Actual Data candidates remain unknown. The HTTP case uses real cookie/case/key/encrypted Workspace publication.
An assigned lawyer without an explicit resource-key capability is refused.
"""
from pathlib import Path
from types import SimpleNamespace
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import BrowserSessionConfiguration, BrowserSessionService, PrincipalStoreCredentialAdapter
from applications.case_access import CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.legal_research_api import _index_acquired_passages, project_authority_admissions, review_versioned_authority
from applications.principal_store import PrincipalStore
from tests.test_gui25_26_canonical_contract import _real_source, _unknown_review

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
ROOT = Path(__file__).resolve().parents[1]


def test_owner_review_uses_real_source_contract_and_unknowns_stay_unresolved(tmp_path):
    mediator, case_file, authority, acquisition, candidate = _real_source(tmp_path)
    actual = mediator.admit_acquired_authorities(acquisition, [{"type": "termination"}], case_file,
        user_id=authority.actor_principal_id)
    assert "status" not in actual
    assert actual["admission"]["status"] == "admitted"
    assert actual["admission"]["stored_record_ids"]
    assert actual["admission"]["proof"] is False
    assert candidate["applicability"] == "unknown"
    _index_acquired_passages(case_file, acquisition)
    workspace = object()
    body = _unknown_review(candidate)
    record = review_versioned_authority(mediator, workspace, authority, body,
        membership="owner", canonical_owner_principal_id="synthetic-canonical-owner")
    assert record["status"] == "unresolved"
    assert record["reason"] == "source_metadata_unresolved"
    assert record["admitted_law"] is False
    assert record["proof"] is False and record["legal_sufficiency"] is False
    assert record["source_passage"] == candidate["source_text"]
    assert record["applicability"] == "unknown"
    assert record["treatment_state"] == "unknown" and record["exceptions"] is None
    assert record["attribution"]["actor_principal_id"] == authority.actor_principal_id
    assert record["attribution"]["canonical_owner_principal_id"] == "synthetic-canonical-owner"
    assert record["attribution"]["actor_is_encrypted_owner"] is False
    replay = review_versioned_authority(mediator, workspace, authority, body,
        membership="owner", canonical_owner_principal_id="synthetic-canonical-owner")
    assert replay["replayed"] is True and replay["admitted_law"] is False
    assert len(case_file["legal_authority_admissions"]) == 1
    checks = [
        ("mismatch", {"jurisdiction": "different-scope"}, "owner", "source_mismatch"),
        ("stale", {"version": "prior-edition"}, "owner", "stale_version"),
        ("missing", {"source_passage": "   "}, "owner", "missing_passage"),
        ("reject", {"decision": "reject"}, "assigned-lawyer", "rejected"),
        ("forged", {"reviewer_principal_id": "different-actor"}, "owner", "unauthorized_reviewer"),
        ("admin", {}, "operational-admin", "unauthorized_reviewer"),
    ]
    for name, changes, membership, reason in checks:
        request = {**body, "operation_id": "synthetic-review-" + name, **changes}
        denied = review_versioned_authority(mediator, workspace, authority, request,
            membership=membership, canonical_owner_principal_id="synthetic-canonical-owner")
        assert denied["status"] == "unresolved" and denied["reason"] == reason
        assert denied["admitted_law"] is False and denied["proof"] is False
        assert denied["attribution"]["actor_principal_id"] == authority.actor_principal_id
    projected = project_authority_admissions(case_file)
    assert projected["admitted_count"] == 0
    assert projected["unresolved_count"] == 7
    assert all(row["proof"] is False for row in projected["admissions"])


def test_http_owner_keeps_unknown_source_unresolved_and_no_role_grants_owner_key(tmp_path):
    from tests.test_gui25_26_private_owner_http import _world, _login, _headers, _start_case, _choose, _acquire
    world = _world(tmp_path)
    case = world.case
    path = f"/api/legal-research/{case.case_id}/admissions"
    grant = world.authorizer.grant_assigned_lawyer(owner_principal_id=world.owner.principal_id,
        lawyer_principal_id=world.lawyer.principal_id, case_id=case.case_id, resource_id=case.resource_id,
        tenant_id=case.tenant_id, actions={"case.read", "case.review"}, expected_case_revision=case.revision)
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.get(path, headers=_headers(world)).status_code == 401
        csrf = _login(client)
        _start_case(client, world, csrf)
        generation = _choose(client, world, csrf)
        acquired = _acquire(client, world, csrf, generation)
        source = next(row for row in acquired["source_version_receipts"] if row["kind"] == "candidate")
        body = {"decision": "admit", "source_passage": source["source_passage"],
            "authority_identity": source["authority_identity"], "jurisdiction": source["jurisdiction"],
            "effective_date": source["effective_date"], "version": source["version"], "content_hash": source["content_hash"],
            "applicability": source["stated_applicability"], "treatment_state": source["treatment_state"],
            "exceptions": source["exceptions"], "operation_id": "synthetic-http-review"}
        assert client.post(path, headers=_headers(world), json=body).status_code == 403
        saved = client.post(path, headers=_headers(world, csrf), json=body)
        assert saved.status_code == 200
        result = saved.json()
        assert result["status"] == "unresolved" and result["reason"] == "source_metadata_unresolved"
        assert result["source_status"] == "source_admitted"
        assert result["admitted_law"] is False and result["proof"] is False
        assert result["attribution"]["actor_principal_id"] == world.owner.principal_id
        assert result["attribution"]["canonical_owner_principal_id"] == case.tenant_id
        assert world.owner.principal_id != case.tenant_id
        listed = client.get(path, headers=_headers(world))
        assert listed.status_code == 200 and listed.json()["admitted_count"] == 0
        assert listed.json()["source_admitted_count"] == 1
        issued = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-lawyer-credential"})
        assert issued.status_code == 200
        headers = {**_headers(world, issued.json()["csrf_token"]), "x-expected-membership-revision": str(grant.revision)}
        # A policy assignment is not possession of the owner's encryption key.
        denied = client.post(path, headers=headers, json={**body, "operation_id": "synthetic-lawyer-review"})
        assert denied.status_code == 403
        issued = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-stranger-credential"})
        assert issued.status_code == 200
        assert client.post(path, headers=_headers(world, issued.json()["csrf_token"]), json=body).status_code == 403


def test_workspace_collects_explicit_authority_review_fields():
    html = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    section = html.split('id="legal-authority-admission"', 1)[1].split('id="workspace-privacy-actions"', 1)[0]
    for element_id in ("legal-admission-case-id", "legal-admission-decision", "legal-admission-identity",
        "legal-admission-version", "legal-admission-jurisdiction", "legal-admission-effective-date",
        "legal-admission-applicability", "legal-admission-treatment", "legal-admission-exceptions",
        "legal-admission-hash", "legal-admission-passage", "legal-admission-display",
        "legal-admission-attribution", "legal-admission-submit"):
        assert f'id="{element_id}"' in section
    assert "unauthorized reviewer" in section and "stale version" in section
    assert "/admissions" in html and "source_passage: fields.source_passage" in html
    assert "membership" in html
