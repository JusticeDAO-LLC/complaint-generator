"""Canonical legal IR attachment and current-source obligations.

Positive cases compile through compile_canonical_legal_ir, verify the stored
receipt against the current source, and keep exact character spans with
applicability context and typed obligations. Negative cases reject a drifted
source, a mismatched span, a caller-supplied receipt, and any claim that IR
parsing, consistency, or Lean text is executed proof or governing law.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.legal_analysis_api import (
    LegalAnalysisError,
    attach_case_canonical_legal_ir,
    project_canonical_legal_ir,
)
from applications.principal_store import PrincipalStore
from integrations.ipfs_datasets import logic

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

LEGAL_TEXT = "Company A shall submit backup report within 10 days unless emergency."
OBLIGATION_TEXT = "Company A shall submit backup report within 10 days"
LEAN_TEXT = "theorem synthetic_duty : True := by trivial"
VOCABULARY = {
    "actors": ["agency", "company_a"],
    "actions": ["file", "submit", "withdraw"],
    "objects": ["backup_report", "notice"],
    "qualifiers": ["emergency", "natural_disaster", "within_10_days"],
}
APPLICABILITY = {
    "jurisdiction": "US",
    "authority_version": "law04-synthetic-1",
    "effective_date": "1996-10-19",
    "forum": "synthetic-district",
    "applicability": "limited",
    "governing_law": True,
}


@pytest.fixture(autouse=True)
def _clear_canonical_cache() -> None:
    logic.reset_canonical_formalization_cache()
    yield
    logic.reset_canonical_formalization_cache()


def _span(text: str = OBLIGATION_TEXT) -> dict:
    start = LEGAL_TEXT.index(text)
    return {"unit": "character", "start": start, "end": start + len(text), "text": text}


def _body(**overrides):
    payload = {
        "request_id": "cimp-gui-29-synthetic",
        "source_text": LEGAL_TEXT,
        "vocabulary": VOCABULARY,
        "applicability_context": dict(APPLICABILITY),
        "legal_context": {
            "citation": "Synthetic Authority §1",
            "authority_locator": "synthetic:authority-1",
            "authority_version": "law04-synthetic-1",
            "source_text": LEGAL_TEXT,
        },
        "user_facts": ["The complainant missed a filing on 1 March 2024."],
        "typed_obligations": [{
            "obligation_id": "duty-submit",
            "kind": "obligation",
            "statement": OBLIGATION_TEXT,
            "source_span": _span(),
            "executed_proof": False,
        }],
        "emitted_lean": LEAN_TEXT,
        "receipt": {"status": "success", "executed_proof": True, "governing_legal_authority": True},
    }
    payload.update(overrides)
    return payload


def _assert_non_authority(payload: dict) -> None:
    assert payload["executed_proof"] is False
    assert payload["governing_legal_authority"] is False
    assert payload["ir_parse_is_proof"] is False
    assert payload["consistency_is_proof"] is False
    assert payload["lean_text_is_proof"] is False
    assert payload["proof"] is False
    assert payload["supplied_receipt_ignored"] is True
    assert payload["emitted_lean_character_length"] == len(LEAN_TEXT)
    for item in payload["typed_obligations"]:
        assert item["executed_proof"] is False
        assert item["governing_legal_authority"] is False
        assert item["discharged"] is False
        assert item["lean_text_is_proof"] is False
        assert item["applicability_context"]["applicability"] == "limited"
        assert item["applicability_context"]["governing_legal_authority"] is False
        start, end = item["source_span"]["start"], item["source_span"]["end"]
        assert LEGAL_TEXT[start:end] == item["source_span"]["text"] == item["statement"]


def test_attachment_verifies_current_source_spans_and_typed_obligations():
    mediator = SimpleNamespace(intake_case_file={})
    payload = attach_case_canonical_legal_ir(mediator, _body())
    assert payload["task_id"] == "CIMP-GUI-29"
    assert payload["status"] == "attached"
    assert payload["compile_status"] == "success"
    assert payload["receipt_verification"]["status"] == "verified"
    assert payload["receipt_verification"]["execution_origin_verified"] is True
    assert payload["receipt_verification"]["tampered"] is False
    assert payload["source_spans"]
    kinds = {item["kind"] for item in payload["typed_obligations"]}
    assert "source_span" in kinds
    assert "obligation" in kinds
    _assert_non_authority(payload)
    assert any(item["reason"] == "supplied_receipt_ignored" for item in payload["rejected_obligations"])
    stored = mediator.intake_case_file["canonical_legal_ir_attachment"]
    assert stored["receipt_id"] == payload["receipt_id"]
    projected = project_canonical_legal_ir(mediator.intake_case_file)
    assert projected["status"] == "attached"
    assert projected["admitted_law"] is False
    audit = logic.verify_canonical_formalization_receipt(payload["receipt_id"], source_text=LEGAL_TEXT)
    assert audit["status"] == "verified"


def test_drifted_source_mismatched_span_and_authority_claims_do_not_attach():
    mediator = SimpleNamespace(intake_case_file={})
    drifted = attach_case_canonical_legal_ir(mediator, _body(
        request_id="cimp-gui-29-drift",
        current_source=LEGAL_TEXT.replace("10 days", "30 days"),
    ))
    assert drifted["status"] == "source_unverified"
    assert drifted["typed_obligations"] == []
    assert drifted["source_spans"] == []
    assert drifted["executed_proof"] is False
    assert drifted["governing_legal_authority"] is False
    assert drifted["receipt_verification"]["status"] != "verified"

    logic.reset_canonical_formalization_cache()
    bad_span = _span()
    bad_span["end"] = bad_span["start"] + 4
    bad_span["text"] = LEGAL_TEXT[bad_span["start"]:bad_span["end"]]
    mismatched = attach_case_canonical_legal_ir(mediator, _body(
        request_id="cimp-gui-29-span",
        typed_obligations=[{
            "obligation_id": "rewritten",
            "kind": "obligation",
            "statement": "Company A shall actually pay damages",
            "source_span": bad_span,
            "executed_proof": True,
            "governing_legal_authority": True,
        }],
    ))
    assert mismatched["status"] == "attached"
    assert all(item["origin"] != "caller_typed" or item["statement"] != "Company A shall actually pay damages"
               for item in mismatched["typed_obligations"])
    reasons = {item["reason"] for item in mismatched["rejected_obligations"]}
    assert "typed_obligation_authority_claim_rejected" in reasons
    assert mismatched["lean_text_is_proof"] is False

    with pytest.raises(LegalAnalysisError) as missing:
        attach_case_canonical_legal_ir(SimpleNamespace(), _body())
    assert missing.value.code == "legal_analysis_unavailable"
    empty = project_canonical_legal_ir({})
    assert empty["status"] == "empty"
    assert empty["typed_obligations"] == []
    assert empty["governing_legal_authority"] is False


class _Mediator:
    def __init__(self) -> None:
        self.intake_case_file = {"legal_context": {"jurisdiction": "US"}}


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    stranger = principals.register_from_request({})
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    second = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            "synthetic-owner-credential": owner.principal_id,
            "synthetic-stranger-credential": stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=300,
    ))
    mediator = _Mediator()
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id),
        authorize_delegated=lambda _decision: False)
    handlers.bind(second, mediator=_Mediator(), workspace_service=SimpleNamespace(case_id=second.case_id),
        authorize_delegated=lambda _decision: False)
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(owner=owner, stranger=stranger, case=case, second=second, app=app, mediator=mediator)


def _headers(case, csrf=None):
    headers = {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision),
    }
    if csrf is not None:
        headers["x-csrf-token"] = csrf
    return headers


def test_http_attaches_for_owner_and_refuses_cross_case_and_anonymous(tmp_path):
    # Migrate the old cache-only fixture to the actual encrypted owner. Source
    # text/context/facts are no longer client authority at the HTTP boundary.
    from tests.test_gui25_26_private_owner_http import _world as encrypted_world
    from tests.test_gui29_private_legal_analysis import _reviewed_source, _analysis_request
    world = encrypted_world(tmp_path)
    case = world.case
    second = world.cases.create_case(actor_principal_id=world.owner.principal_id)
    path = f"/api/legal-analysis/{case.case_id}"
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.get(path, headers=_headers(case)).status_code == 401
        login = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-credential"})
        assert login.status_code == 200, login.text
        csrf = login.json()["csrf_token"]
        source = _reviewed_source(client, world, csrf)
        empty = client.get(path, headers=_headers(case))
        assert empty.status_code == 200, empty.text
        assert empty.json()["status"] == "empty"
        assert empty.json()["executed_proof"] is False
        request = _analysis_request(client, world, source)
        attached = client.post(path, headers=_headers(case, csrf), json=request)
        assert attached.status_code == 200, attached.text
        body = attached.json()
        assert body["status"] == "attached"
        assert body["case_id"] == case.case_id
        assert body["receipt_verification"]["execution_origin_verified"] is True
        assert body["source_binding"]["content_hash"] == source["content_hash"]
        assert body["applicability_context"]["applicability"] == "unknown"
        assert body["proof"] is False and body["admitted_law"] is False
        assert body["governing_legal_authority"] is False and body["lean_text_is_proof"] is False
        assert all(item["discharged"] is False and item["executed_proof"] is False
            for item in body["typed_obligations"])
        again = client.get(path, headers=_headers(case))
        assert again.status_code == 200
        assert again.json()["receipt_id"] == body["receipt_id"]
        assert again.json()["lean_text_is_proof"] is False
        crossed = client.get(path, headers=_headers(case), params={"case_id": second.case_id})
        assert crossed.status_code == 403
        assert crossed.json()["error"] == "cross_case_id"
        assert crossed.json()["governing_legal_authority"] is False
        other = client.post(f"/api/legal-analysis/{second.case_id}",
            headers=_headers(case, csrf), json=request)
        assert other.status_code == 403
        current = _analysis_request(client, world, source)
        forged = client.post(path, headers=_headers(case, csrf), json={**current,
            "current_source":"A different statute that was not selected from this case."})
        assert forged.status_code == 422
        assert forged.json()["error"] == "client_case_authority"
        stale = client.post(path, headers=_headers(case, csrf), json={**current,
            "source_content_hash":"sha256:" + "0" * 64})
        assert stale.status_code == 409
        assert stale.json()["error"] == "legal_source_unavailable"
        assert stale.json()["executed_proof"] is False
        stranger = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-stranger-credential"})
        assert stranger.status_code == 200
        denied = client.get(path, headers=_headers(case, stranger.json()["csrf_token"]))
        assert denied.status_code == 403
