"""Explicit jurisdiction, forum, and legal-date selection.

Positive cases collect those fields without inventing governing law, then show
that a later context change invalidates legal dependencies and proofs while
the factual provenance and the prior context version remain. Negative cases
refuse a missing session, a cross-case id, a governing-law default, and a
stale context revision.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
    SESSION_COOKIE,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.legal_context_api import (
    LegalContextError,
    project_legal_context,
    select_explicit_legal_context,
)
from applications.principal_store import PrincipalStore

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]


def _case_file() -> dict:
    return {
        "legal_context": {},
        "proof_leads": [{
            "proof_id": "proof-1",
            "proof_state": "supported",
            "provenance": {"source_id": "src-fact-immutable", "stable_id": "fact-1"},
        }],
        "legal_dependencies": [{
            "dependency_id": "dep-statute-1",
            "proof_state": "admitted",
            "provenance": {"source_id": "src-fact-immutable"},
            "factual_premise_ids": ["fact-1"],
        }],
        "factual_provenance": [{
            "source_id": "src-fact-immutable",
            "stable_id": "fact-1",
            "text": "Alex arrived at nine",
        }],
        "canonical_facts": [{
            "id": "fact-1",
            "source_id": "src-fact-immutable",
            "statement": "Alex arrived at nine",
        }],
    }


class _Mediator:
    def __init__(self, case_file: dict) -> None:
        self.intake_case_file = case_file
        self.updates = []
        self.refreshes = []

    def apply_explicit_legal_context(self, case_file, **updates):
        self.updates.append(dict(updates))
        from complaint_phases.intake_case_file import apply_explicit_legal_context

        return apply_explicit_legal_context(case_file, **updates)

    def refresh_verified_legal_dependencies(self, change):
        self.refreshes.append(dict(change))
        return {"affected_node_ids": ["dep-statute-1"], "empty_success": False}


def _explicit_body(**extra):
    body = {
        "expected_context_revision": 0,
        "applicability": "explicit",
        "jurisdiction": "Oregon",
        "forum": "Multnomah County Circuit Court",
        "event_date": "2024-03-04",
        "applicable_law_date": "2024-03-04",
        "filing_reference_date": "2024-04-01",
        "corpus_retrieval_date": "2024-05-02",
    }
    body.update(extra)
    return body


def test_explicit_context_keeps_unknown_and_disputed_without_governing_law():
    mediator = _Mediator(_case_file())
    selected = select_explicit_legal_context(mediator, _explicit_body())
    assert selected["governing_law_defaulted"] is False
    assert selected["jurisdiction"] == "OR"
    assert selected["jurisdiction_applicability"] == "explicit"
    assert selected["forum"] == "Multnomah County Circuit Court"
    assert selected["forum_applicability"] == "explicit"
    assert selected["applicability"] == "explicit"
    assert selected["context_revision"] == 1
    assert selected["dependent_proof"][0]["proof_state"] == "invalidated"
    assert selected["dependent_proof"][0]["invalidated_by"] == "legal_context_change"
    assert selected["legal_dependencies"][0]["proof_state"] == "invalidated"
    assert selected["legal_dependencies"][0]["provenance"]["source_id"] == "src-fact-immutable"
    assert selected["dependent_proof"][0]["provenance"]["stable_id"] == "fact-1"
    assert selected["factual_provenance"] == [{
        "source_id": "src-fact-immutable", "stable_id": "fact-1", "text": "Alex arrived at nine",
    }]
    assert selected["prior_versions"][0]["context_revision"] == 0
    assert mediator.intake_case_file["legal_context_overrides"]["jurisdiction"] == "Oregon"
    assert mediator.refreshes and mediator.refreshes[0]["jurisdiction_changed"] is True
    assert "governing_law" not in mediator.intake_case_file["legal_context_overrides"]

    disputed = select_explicit_legal_context(mediator, {
        "expected_context_revision": selected["context_revision"],
        "applicability": "disputed",
        "jurisdiction": "federal",
        "forum": "disputed",
    })
    assert disputed["applicability"] == "disputed"
    assert disputed["jurisdiction"] == "unknown"
    assert disputed["jurisdiction_applicability"] == "disputed"
    assert disputed["candidate_jurisdiction"] == "federal"
    assert disputed["forum"] == "disputed"
    assert disputed["forum_applicability"] == "disputed"
    assert disputed["governing_law_defaulted"] is False
    assert disputed["jurisdiction"] != "federal"
    assert disputed["factual_provenance"][0]["source_id"] == "src-fact-immutable"
    assert any(item["jurisdiction"] == "OR" for item in disputed["prior_versions"])

    unknown = project_legal_context({"legal_context": {}})
    assert unknown["jurisdiction"] == "unknown"
    assert unknown["forum"] == "unknown"
    assert unknown["applicability"] == "unknown"
    assert unknown["governing_law_defaulted"] is False


def test_forum_change_invalidates_dependencies_and_rejects_defaults():
    mediator = _Mediator(_case_file())
    selected = select_explicit_legal_context(mediator, _explicit_body())
    provenance = list(selected["factual_provenance"])
    changed = select_explicit_legal_context(mediator, {
        "expected_context_revision": selected["context_revision"],
        "applicability": "explicit",
        "jurisdiction": "OR",
        "forum": "U.S. District Court for the District of Oregon",
    })
    assert changed["forum"] == "U.S. District Court for the District of Oregon"
    assert changed["context_revision"] > selected["context_revision"]
    assert changed["legal_dependencies"][0]["proof_state"] == "invalidated"
    assert changed["legal_dependencies"][0]["factual_premise_ids"] == ["fact-1"]
    assert changed["factual_provenance"] == provenance
    assert mediator.intake_case_file["canonical_facts"][0]["statement"] == "Alex arrived at nine"
    assert any(item["forum"] == "Multnomah County Circuit Court" for item in changed["prior_versions"])

    with pytest.raises(LegalContextError) as governing:
        select_explicit_legal_context(mediator, {
            "expected_context_revision": changed["context_revision"],
            "governing_law": "OR",
        })
    assert governing.value.code == "governing_law_not_admitted"
    assert mediator.intake_case_file["legal_context"]["jurisdiction"] == "OR"

    with pytest.raises(LegalContextError) as stale:
        select_explicit_legal_context(mediator, _explicit_body(expected_context_revision=0, forum="somewhere else"))
    assert stale.value.code == "legal_context_revision_conflict"
    assert mediator.intake_case_file["legal_context_forum"]["value"] != "somewhere else"

    with pytest.raises(LegalContextError) as applicability:
        select_explicit_legal_context(mediator, {
            "expected_context_revision": changed["context_revision"],
            "applicability": "governing_law",
            "jurisdiction": "WA",
        })
    assert applicability.value.code == "governing_law_not_admitted"


def _world(tmp_path):
    from tests.test_cimp_gui_14 import _composed_case_world
    return _composed_case_world(tmp_path)


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


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_http_selection_allows_owner_and_denies_default_and_cross_case(tmp_path):
    world = _world(tmp_path)
    case = world.case
    path = f"/api/legal-context/{case.case_id}"
    with TestClient(world.app, base_url="https://testserver") as client:
        anonymous = client.get(path, headers=_headers(case))
        assert anonymous.status_code == 401
        csrf = _login(client, "synthetic-owner-credential")
        from tests.test_cimp_gui_14 import NARRATIVE
        started = client.post("/api/complaint-workspace/intake-chat", headers=_headers(case, csrf),
            json={"message": NARRATIVE, "interview_action": "start"})
        assert started.status_code == 200, started.text
        before = client.get("/api/complaint-workspace/session", headers=_headers(case)).json()["session"]
        initial = client.get(path, headers=_headers(case, csrf))
        assert initial.status_code == 200, initial.text
        assert initial.json()["jurisdiction"] == "unknown"
        assert initial.json()["applicability"] == "unknown"
        assert initial.json()["governing_law_defaulted"] is False
        saved = client.post(path, headers=_headers(case, csrf), json=_explicit_body())
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["case_id"] == case.case_id
        assert body["jurisdiction"] == "OR"
        assert body["forum_applicability"] == "explicit"
        # The real intake snapshot has no pre-admitted synthetic legal proof.
        # Actual typed proof/cache invalidation is exercised separately in the
        # transition-owner tests; this frontdoor proves persisted source facts.
        after = client.get("/api/complaint-workspace/session", headers=_headers(case)).json()["session"]
        assert after["shared_interview"]["knowledge_graph"] == before["shared_interview"]["knowledge_graph"]
        assert int(after["private_revision"]) == int(before["private_revision"]) + 1
        assert body["prior_versions"]
        refused = client.post(path, headers=_headers(case, csrf), json={
            "expected_context_revision": body["context_revision"],
            "governing_law": "federal",
        })
        assert refused.status_code == 422
        assert refused.json()["error"] == "governing_law_not_admitted"
        stale = client.post(path, headers=_headers(case, csrf), json=_explicit_body(
            expected_context_revision=0, jurisdiction="Washington"))
        assert stale.status_code == 409
        assert stale.json()["error"] == "legal_context_revision_conflict"
        crossed = client.post(f"/api/legal-context/{world.second.case_id}", headers=_headers(case, csrf), json=_explicit_body(
            expected_context_revision=body["context_revision"]))
        assert crossed.status_code == 403
        assert crossed.json()["error"] == "cross_case_id"
        # The foreign owned service was never opened or modified by this POST.
        from tests.test_cimp_gui_14 import _composed_ciphertext_snapshot
        assert _composed_ciphertext_snapshot(world.services[world.second.case_id]) == {}
        _login(client, "synthetic-stranger-credential")
        denied = client.get(path, headers=_headers(case))
        assert denied.status_code == 403


def test_workspace_collects_context_without_a_governing_law_default():
    html = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    section = html.split('id="legal-effective-context"', 1)[1].split('id="case-processing-consent"', 1)[0]
    for element_id in (
        "legal-context-case-id",
        "legal-context-applicability",
        "legal-context-jurisdiction",
        "legal-context-forum",
        "legal-context-event-date",
        "legal-context-applicable-law-date",
        "legal-context-filing-reference-date",
        "legal-context-corpus-retrieval-date",
        "legal-context-display",
        "legal-context-save",
    ):
        assert f'id="{element_id}"' in section
    assert 'value="unknown"' in section
    assert 'value="disputed"' in section
    assert 'value="explicit"' in section
    assert "governing_law" not in section
    assert 'placeholder="State, federal, unknown, or disputed"' in section
    assert "/api/legal-context/" in html
    assert "Governing law was not defaulted" in html
    assert "expected_context_revision" in html
