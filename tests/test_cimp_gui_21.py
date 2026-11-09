"""Authorized factual knowledge-graph projection.

Positive cases project user statements, evidence revisions, allegations, and
hypotheses with immutable source ids and separate confidence and authority.
Negative cases deny a missing session, a lawyer without a key grant, and a
case id that does not match the authorized case.
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
    SESSION_COOKIE,
)
from applications.case_access import ASSIGNED_LAWYER_ACTIONS, CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from complaint_phases.knowledge_graph import Entity, KnowledgeGraph
from mediator.integrations.graph_tools import (
    FactualGraphProjectionError,
    project_authorized_factual_kg,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


class _PhaseHook:
    """The mediator hook graph projection already uses. Not a second interview."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self.phase_manager = self
        self._graph = graph

    def get_phase_data(self, _phase, key: str):
        if key == "knowledge_graph":
            return self._graph
        return None


def _graph(case_id: str) -> KnowledgeGraph:
    graph = KnowledgeGraph(graph_id="factual-" + case_id[:8], graph_version="1")
    graph.metadata["case_id"] = case_id
    graph.add_entity(Entity(
        id="mutable-statement-node",
        type="fact",
        name="I arrived at nine",
        attributes={"description": "I arrived at nine", "factual_record_class": "user_fact"},
        confidence=1.0,
        source="complaint",
        provenance={"source_id": "src-statement-immutable", "case_id": case_id},
    ))
    graph.add_entity(Entity(
        id="mutable-allegation-node",
        type="allegation",
        name="The employer denied the request",
        attributes={
            "description": "The employer denied the request",
            "factual_record_class": "user_fact",
            "epistemic_class": "user_allegation",
        },
        confidence=0.55,
        source="complaint",
        provenance={"source_id": "src-allegation-immutable", "case_id": case_id, "epistemic_class": "user_allegation"},
    ))
    graph.add_entity(Entity(
        id="mutable-hypothesis-node",
        type="fact",
        name="I think the schedule changed",
        attributes={"description": "I think the schedule changed", "factual_record_class": "extraction_hypothesis", "origin": "model"},
        confidence=0.2,
        source="inference",
        provenance={"source_id": "src-hypothesis-immutable", "case_id": case_id, "origin": "model"},
    ))
    graph.add_entity(Entity(
        id="legal-node",
        type="legal_text",
        name="Synthetic statute section 1",
        attributes={"description": "Synthetic statute section 1", "factual_record_class": "legal_text"},
        confidence=0.99,
        source="legal",
        provenance={"source_id": "src-legal-immutable", "case_id": case_id, "origin": "legal"},
    ))
    graph.add_entity(Entity(
        id="foreign-node",
        type="fact",
        name="Foreign case secret",
        attributes={"description": "Foreign case secret", "factual_record_class": "user_fact", "case_id": "case-foreign"},
        confidence=1.0,
        source="complaint",
        provenance={"source_id": "src-foreign", "case_id": "case-foreign"},
    ))
    graph.factual_ledger()["revisions"].append({
        "revision_id": "rev-1",
        "immutable_source_id": "src-evidence-immutable",
        "confidence": 0.8,
        "text": "Exhibit A records the arrival",
        "case_id": case_id,
    })
    return graph


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    stranger = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    second = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            "synthetic-owner-credential": owner.principal_id,
            "synthetic-stranger-credential": stranger.principal_id,
            "synthetic-lawyer-credential": lawyer.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=300,
    ))
    primary = _graph(case.case_id)
    other = _graph(second.case_id)
    other.entities["mutable-statement-node"].name = "Second case statement"
    other.entities["mutable-statement-node"].attributes["description"] = "Second case statement"
    handlers = CaseHandlerRegistry()
    hooks = {}
    for selected, graph in ((case, primary), (second, other)):
        hook = _PhaseHook(graph)
        handlers.bind(selected, mediator=hook, workspace_service=SimpleNamespace(case_id=selected.case_id),
            authorize_delegated=lambda _decision: False)
        hooks[selected.case_id] = hook
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(owner=owner, stranger=stranger, lawyer=lawyer, case=case, second=second,
        authorizer=authorizer, app=app, hooks=hooks)


def _headers(case, csrf=None, *, membership=None):
    headers = {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision),
    }
    if csrf is not None:
        headers["x-csrf-token"] = csrf
    if membership is not None:
        headers["x-expected-membership-revision"] = str(membership)
    return headers


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def test_projection_separates_authority_and_keeps_source_ids(tmp_path):
    world = _world(tmp_path)
    hook = world.hooks[world.case.case_id]
    payload = project_authorized_factual_kg(hook, case_id=world.case.case_id, graph_read_granted=True)
    assert payload["data_graph_owner"]["owner_id"] == "ipfs_datasets_py"
    assert payload["data_graph_owner"]["available"] is True
    statement = payload["user_statements"][0]
    allegation = payload["allegations"][0]
    evidence = payload["evidence_revisions"][0]
    hypothesis = payload["hypotheses"][0]
    assert statement["immutable_source_id"] == "src-statement-immutable"
    assert allegation["immutable_source_id"] == "src-allegation-immutable"
    assert evidence["immutable_source_id"] == "src-evidence-immutable"
    assert hypothesis["immutable_source_id"] == "src-hypothesis-immutable"
    assert statement["immutable_source_id"] != "mutable-statement-node"
    assert [statement["authority"], allegation["authority"], evidence["authority"], hypothesis["authority"]] == [
        "user", "allegation", "evidence", "hypothesis",
    ]
    assert statement["confidence_role"] != hypothesis["confidence_role"]
    assert statement["confidence"] == 1.0
    assert hypothesis["confidence"] == 0.2
    assert hypothesis["authority_is_user_fact"] is False
    assert hypothesis["admitted_user_fact"] is False
    # A raw imported graph fact has no verified UserAssertionEnvelope.
    assert statement["admitted_user_fact"] is False
    texts = " ".join(item["text"] for bucket in (
        payload["user_statements"], payload["allegations"], payload["evidence_revisions"], payload["hypotheses"],
    ) for item in bucket)
    assert "Synthetic statute section 1" not in texts
    assert "Foreign case secret" not in texts
    assert payload["denied_cross_case_ids"] == ["case-foreign"]
    assert payload["withheld_legal_text"]
    hook._graph.entities["mutable-statement-node"].name = "renamed after projection"
    again = project_authorized_factual_kg(hook, case_id=world.case.case_id, graph_read_granted=True)
    assert again["user_statements"][0]["immutable_source_id"] == "src-statement-immutable"

    with pytest.raises(FactualGraphProjectionError) as ungranted:
        project_authorized_factual_kg(hook, case_id=world.case.case_id, graph_read_granted=False)
    assert ungranted.value.code == "graph_read_ungranted"
    with pytest.raises(FactualGraphProjectionError) as crossed:
        project_authorized_factual_kg(hook, case_id=world.case.case_id, graph_read_granted=True,
            requested_case_id=world.second.case_id)
    assert crossed.value.code == "cross_case_id"
    hook._graph.metadata["case_id"] = world.second.case_id
    with pytest.raises(FactualGraphProjectionError) as bound:
        project_authorized_factual_kg(hook, case_id=world.case.case_id, graph_read_granted=True)
    assert bound.value.code == "cross_case_id"


def test_http_projection_allows_owner_and_denies_ungranted_and_cross_case(tmp_path):
    from tests.test_cimp_gui_14 import NARRATIVE, _composed_case_world

    # Read the same encrypted service used by the real composed intake route.
    # The earlier phase-hook/SimpleNamespace fixture could pass while a real
    # browser actor could neither read its graph nor enforce key locking.
    world = _composed_case_world(tmp_path)
    handlers = CaseHandlerRegistry()
    for selected in (world.case, world.second, world.foreign):
        service = world.services[selected.case_id]
        handlers.bind(selected, mediator=service, workspace_service=service,
            authorize_delegated=lambda _decision: False)
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=handlers, include_review=False, include_document=False)
    case = world.case
    assert case.tenant_id != world.owner.principal_id
    path = f"/api/graphs/{case.case_id}/factual"
    with TestClient(app, base_url="https://testserver") as client:
        anonymous = client.get(path, headers=_headers(case))
        assert anonymous.status_code == 401
        csrf = _login(client, "synthetic-owner-credential")
        for selected, text in ((case, NARRATIVE), (world.second, "Foreign case secret: a synthetic separate workplace account.")):
            started = client.post("/api/complaint-workspace/intake-chat", headers=_headers(selected, csrf),
                json={"message": text, "interview_action": "start"})
            assert started.status_code == 200, started.text
        allowed = client.get(path, headers=_headers(case, csrf))
        assert allowed.status_code == 200, allowed.text
        body = allowed.json()
        assert body["case_id"] == case.case_id
        assert body["read_only"] is True
        rows = [item for field in ("user_statements", "allegations", "evidence_revisions", "hypotheses")
            for item in body[field]]
        assert rows
        assert all(item["immutable_source_id"] for item in rows)
        assert all(not item["admitted_user_fact"] for field in ("allegations", "evidence_revisions", "hypotheses")
            for item in body[field])
        assert all(item["assertion_id"] and item["provenance_status"] == "verified"
            for item in rows if item["admitted_user_fact"])
        assert "Foreign case secret" not in allowed.text
        crossed = client.get(f"/api/graphs/{world.second.case_id}/factual", headers=_headers(case, csrf))
        assert crossed.status_code == 403
        assert crossed.json()["error"] == "cross_case_id"
        query = client.get(path + f"?case_id={world.second.case_id}", headers=_headers(case, csrf))
        assert query.status_code == 403
        assert query.json()["error"] == "cross_case_id"
        _login(client, "synthetic-stranger-credential")
        assert client.get(path, headers=_headers(case)).status_code == 403
        grant = world.authorizer.grant_assigned_lawyer(
            owner_principal_id=world.owner.principal_id,
            lawyer_principal_id=world.lawyer.principal_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            tenant_id=case.tenant_id,
            actions=set(ASSIGNED_LAWYER_ACTIONS),
            expected_case_revision=case.revision,
        )
        lawyer_csrf = _login(client, "synthetic-lawyer-credential")
        denied = client.get(path, headers=_headers(case, lawyer_csrf, membership=grant.revision))
        assert denied.status_code == 403
        assert denied.json()["error"] == "case_key_grant_required"
