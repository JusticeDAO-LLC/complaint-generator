"""Real typed dependency refresh and encrypted current-owner publication.

The previous fixture accepted invented links/proof rows on a namespace holding
only a ledger. These regressions keep its version/replay/stale-authority intent
while requiring actual source admission, DG effects and private owner custody.
No asynchronous producer capability exists: late rows stay unavailable, and a
persisted server-computed refresh can only be revalidated read-only. The owner
requires its current citation_acquisition consent; no earlier public-law or
Grok decision is aliased to that purpose, and local refresh grants no egress.
"""
from copy import deepcopy
from types import SimpleNamespace
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from applications.case_consent_api import CaseConsentService
from applications.case_routes import compose_case_routes
from applications.graph_api import LegalDependencyGraphError, refresh_versioned_law_graph, accept_versioned_law_late_result
from tests.test_gui28_actual_dependency_refresh import _actual
from tests.test_authority_dependency_pipeline import _source_record, _sourced_nodes
from tests.test_cimp_gui_14 import _composed_case_world, _composed_headers, _composed_login, _composed_ciphertext_snapshot
from tests.test_gui24_private_context import _start

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _live(**overrides):
    value = {"case_id": "synthetic-case", "actor_principal_id": "source-fixture-owner",
        "case_revision": 3, "grant_revision": 1, "granted_actions": ["case.update"],
        "consent_generation": 2, "consent_revoked": False}
    value.update(overrides)
    return value


def _refresh_body(source, **overrides):
    value = {"operation_id": "refresh-1", "correction_kind": "factual", "case_id": "synthetic-case",
        "expected_case_revision": 3, "expected_consent_generation": 2, "expected_grant_revision": 1,
        "expected_dependency_generation": 0, "legal_source_hashes": [source["source_hash"]]}
    value.update(overrides)
    return value


def _scope(source):
    return {"employment_discrimination": [source]}


def test_refresh_versions_generation_and_invalidates_prior_dependencies(tmp_path, monkeypatch):
    mediator, graph, node, source = _actual(tmp_path, monkeypatch)
    before = deepcopy(graph.to_dict())
    first = refresh_versioned_law_graph(mediator, live=_live(), body=_refresh_body(source), canonical_source_records=_scope(source))
    assert first["task_id"] == "CIMP-GUI-28" and first["applied"] is True
    assert first["proof"] is False and first["legal_sufficiency"] is False
    assert first["dependency_generation"] == first["operation_version"] == 1
    assert first["graph_mutated"] is True and graph.to_dict() != before
    assert graph.nodes[node.id].satisfied is False
    assert graph.nodes[node.id].attributes["proof_cache"]["reusable"] is False
    assert all(item["proof"] is False for item in first["links"] + first["questions"] + first["proof_obligations"])
    assert {item["id"] for item in first["links"]} == set(graph.dependencies)
    saved = deepcopy(graph.to_dict())
    replay = refresh_versioned_law_graph(mediator, live=_live(), body=_refresh_body(source), canonical_source_records=_scope(source))
    assert replay["replayed"] is True and replay["applied"] is False and replay["dependency_generation"] == 1
    assert graph.to_dict() == saved

    replacement = _source_record("new-current-rule", "hearing")
    second = refresh_versioned_law_graph(mediator, live=_live(case_revision=4),
        body=_refresh_body(replacement, operation_id="refresh-source", correction_kind="source",
            expected_case_revision=4, expected_dependency_generation=1), canonical_source_records=_scope(replacement))
    assert second["dependency_generation"] == second["operation_version"] == 2
    assert second["admitted_source_hashes"] == [replacement["source_hash"]]
    assert second["dependency_refresh"]["source_admission_reread"] is True
    assert any(row["status"] == "invalidated" for row in second["links"])
    assert not [n for n in _sourced_nodes(graph) if n.attributes.get("source_available") is True
                and n.attributes.get("source_hash") == source["source_hash"]]
    third = refresh_versioned_law_graph(mediator, live=_live(case_revision=4, consent_generation=3),
        body=_refresh_body(replacement, operation_id="refresh-context", correction_kind="context",
            expected_case_revision=4, expected_consent_generation=3, expected_dependency_generation=2),
        canonical_source_records=_scope(replacement))
    assert third["dependency_generation"] == 3 and third["graph_mutated"] is True


def test_late_result_matches_current_binding_and_stale_results_do_not_apply(tmp_path, monkeypatch):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    refresh_versioned_law_graph(mediator, live=_live(), body=_refresh_body(source), canonical_source_records=_scope(source))
    body = {"operation_id": "late-current", "refresh_operation_id": "refresh-1", "case_id": "synthetic-case",
        "dependency_generation": 1, "legal_source_hashes": [source["source_hash"]]}
    before = deepcopy(graph.to_dict())
    current = accept_versioned_law_late_result(mediator, live=_live(), body=body, canonical_source_records=_scope(source))
    assert current["status"] == "verified_current" and current["server_refresh_verified"] is True
    assert current["applied"] is False and current["graph_mutated"] is False
    assert current["client_result_installed"] is False and current["proof"] is False
    assert graph.to_dict() == before
    with pytest.raises(LegalDependencyGraphError) as arbitrary:
        accept_versioned_law_late_result(mediator, live=_live(), body={**body,
            "links": [{"id": "caller-proof-row"}]}, canonical_source_records=_scope(source))
    assert arbitrary.value.code == "late_result_capability_unavailable"
    stale = [(_live(case_revision=9), {}, "stale_case_revision"),
        (_live(consent_generation=8), {}, "stale_consent"), (_live(grant_revision=7), {}, "stale_actor_grant"),
        (_live(actor_principal_id="other"), {}, "stale_actor_grant"),
        (_live(consent_revoked=True), {}, "consent_revoked"), (_live(granted_actions=["case.read"]), {}, "actor_not_permitted"),
        (_live(), {"dependency_generation": 0}, "stale_dependency_generation"),
        (_live(), {"case_id": "foreign"}, "cross_case_id"),
        (_live(), {"legal_source_hashes": ["0" * 64]}, "stale_legal_source_hash")]
    for live, overrides, code in stale:
        with pytest.raises(LegalDependencyGraphError) as error:
            accept_versioned_law_late_result(mediator, live=live, body={**body, **overrides}, canonical_source_records=_scope(source))
        assert error.value.code == code
    assert graph.to_dict() == before


def test_refresh_refuses_stale_expectations_without_writing(tmp_path, monkeypatch):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    before = deepcopy(graph.to_dict())
    changes = [({"expected_case_revision": 1}, "stale_case_revision"),
        ({"expected_consent_generation": 1}, "stale_consent"),
        ({"expected_grant_revision": 0}, "stale_actor_grant"),
        ({"expected_dependency_generation": 1}, "stale_dependency_generation"),
        ({"correction_kind": "narrative"}, "refresh_field"),
        ({"legal_source_hashes": ["hash-current"]}, "stale_legal_source_hash"),
        ({"successors": {"proof_obligations": [{"id": "invented"}]}}, "caller_graph_rows_not_accepted")]
    for overrides, code in changes:
        with pytest.raises(LegalDependencyGraphError) as error:
            refresh_versioned_law_graph(mediator, live=_live(), body=_refresh_body(source, **overrides), canonical_source_records=_scope(source))
        assert error.value.code == code
    assert graph.to_dict() == before


def _world(tmp_path):
    world = _composed_case_world(tmp_path)
    consent = CaseConsentService(tmp_path / "consent", cases=world.cases, key=os.urandom(32), key_id="consent-key", clock=lambda: int(world.clock["now"]))
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=world.handlers, case_consent=consent, include_review=False, include_document=False)
    world.app, world.consent = app, consent
    return world


def test_http_refresh_and_late_result_follow_live_authority(tmp_path):
    world = _world(tmp_path)
    case, service = world.case, world.services[world.case.case_id]
    assert world.owner.principal_id != case.tenant_id
    path = f"/api/graphs/{case.case_id}/legal-dependency/refresh"
    late_path = f"/api/graphs/{case.case_id}/legal-dependency/late-result"
    body = {"operation_id": "private-refresh", "correction_kind": "context", "case_id": case.case_id,
        "expected_case_revision": case.revision, "expected_consent_generation": 1,
        "expected_grant_revision": 0, "expected_dependency_generation": 0, "legal_source_hashes": []}
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.post(path, headers=_composed_headers(case), json=body).status_code == 401
        csrf = _start(client, case)
        consent = world.consent.choose(world.owner.principal_id, case.case_id,
            {"purpose": "citation_acquisition", "mode": "local_private", "expected_generation": 0})
        assert consent["generation"] == 1
        headers = _composed_headers(case, csrf)
        before = client.get("/api/complaint-workspace/session", headers=headers).json()["session"]
        stale = client.post(path, headers=headers, json={**body, "expected_consent_generation": 0})
        assert stale.status_code == 409 and stale.json()["error"] == "stale_consent"
        response = client.post(path, headers=headers, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["applied"] is True and response.json()["dependency_generation"] == 1
        assert response.json()["admitted_source_hashes"] == [] and response.json()["proof"] is False
        after = client.get("/api/complaint-workspace/session", headers=headers).json()["session"]
        assert int(after["private_revision"]) == int(before["private_revision"]) + 1
        assert after["shared_interview"]["knowledge_graph"] == before["shared_interview"]["knowledge_graph"]
        assert after["shared_interview"]["intake_case_file"]["legal_graph_refresh"]["dependency_generation"] == 1
        saved = _composed_ciphertext_snapshot(service)
        replay = client.post(path, headers=headers, json=body)
        assert replay.status_code == 200 and replay.json()["replayed"] is True
        assert _composed_ciphertext_snapshot(service) == saved
        checked = client.post(late_path, headers=headers, json={"operation_id": "private-late-check",
            "refresh_operation_id": "private-refresh", "case_id": case.case_id, "dependency_generation": 1,
            "legal_source_hashes": []})
        assert checked.status_code == 200, checked.text
        assert checked.json()["server_refresh_verified"] is True and checked.json()["applied"] is False
        assert _composed_ciphertext_snapshot(service) == saved
        denied = client.post(path, headers=headers, json={**body, "source_records": []})
        assert denied.status_code == 400 and denied.json()["error"] == "client_case_authority"
        assert _composed_ciphertext_snapshot(service) == saved
        _composed_login(client, "synthetic-stranger-credential")
        assert client.post(path, headers=headers, json=body).status_code == 403
