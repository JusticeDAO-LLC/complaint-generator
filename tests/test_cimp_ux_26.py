"""Current requirements come from admitted passages, not from generic elements.

The corpus lookup and the source-bound rule extractor produce the lineage.
Facts can be recorded as support. They cannot change the rule. Missing context
and conflicting full texts stay visible unresolved research.
"""
from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from complaint_phases.dependency_graph import DependencyGraph, DependencyGraphBuilder, DependencyNode, NodeType
from mediator.legal_authority_hooks import LegalAuthorityAnalysisHook, derive_admitted_dependency_requirements
from tests.test_cimp_gui_14 import _composed_case_world, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

PASSAGE = "An employer must pay wages that are due."
OTHER = "An employer must keep a payroll record."
QUERY = "wage statute"


def _case():
    return {
        "legal_context": {
            "jurisdiction": "WA",
            "jurisdiction_explicit": True,
            "jurisdiction_applicability": "explicit",
            "event_date": {"raw_text": "2024-03-04", "precise_date": "2024-03-04"},
            "applicable_law_date": {"raw_text": "2024-01-01", "precise_date": "2024-01-01"},
            "filing_reference_date": {"raw_text": "2024-04-01", "precise_date": "2024-04-01"},
            "context_revision": 1,
        },
        "legal_context_forum": {"value": "King County Superior Court", "applicability": "explicit"},
        "legal_context_applicability": "explicit",
    }


def _cache(*rows):
    return {"us_code|wage statute|wa|": list(rows)}


def _row(text, citation="29 U.S.C. 206"):
    return {"text": text, "citation": citation, "uri": "https://example.invalid/usc-206", "jurisdiction": "WA"}


def _body(**extra):
    payload = {
        "query": QUERY,
        "offline_cache": _cache(_row(PASSAGE)),
        "review_decision": "admit",
        "authority_version": "2024-03-04",
        "facts": [{"fact_id": "fact-wages", "text": "The employer did not pay wages.", "rule_text": "An employer must not pay."}],
    }
    payload.update(extra)
    return payload


class _Mediator:
    def __init__(self):
        self.events = []

    def log(self, name, **fields):
        self.events.append((name, fields))


def _admitted_body(case):
    preview = derive_admitted_dependency_requirements(case, {**_body(), "review_decision": None, "facts": []})
    assert preview["status"] == "unresolved_research"
    found = derive_admitted_dependency_requirements(case, {**_body(), "review_decision": None, "facts": []})
    # The second call still has no review. Discover the passage through a reviewed call's custody by
    # reading the flow indirectly: admit after a dry discovery is not available, so review the hash
    # produced by the corpus tool on the same cache.
    from applications.legal_context_api import conduct_legal_source_flow
    flow = conduct_legal_source_flow(case, {**_body(), "review_decision": None, "facts": []})
    passage_id = flow["decisions"]["custody"][0]["passage_id"]
    return _body(review_passage_id=passage_id, governing_law_passage_id=passage_id), passage_id


def test_admitted_passage_becomes_a_current_requirement_and_facts_do_not_rewrite_it():
    case = _case()
    body, passage_id = _admitted_body(case)
    hook = LegalAuthorityAnalysisHook(_Mediator())
    derived = hook.derive_dependency_requirements(case, body)
    assert hook.mediator.events[0][0] == "derived_dependency_requirements"
    assert derived["status"] == "current"
    assert derived["hardcoded_elements_used"] is False
    assert derived["fact_rewrites_ignored"] is True
    requirement = derived["requirements"][0]
    assert requirement["rule_text"] == PASSAGE
    assert requirement["description"] == PASSAGE
    assert requirement["jurisdiction"] == "WA"
    assert requirement["effective_date"] == "2024-01-01"
    assert requirement["authority_version"] == "2024-03-04"
    assert requirement["passage_id"] == passage_id
    lineage = requirement["derivation_lineage"]
    assert lineage["tool"] == "extract_source_bound_rule_candidates"
    assert lineage["corpus_tool"] == "lookup_bounded_legal_corpus"
    assert lineage["temporal_api"].endswith("legal_ir_temporal_authority")
    assert lineage["source_hash"] == hashlib.sha256(PASSAGE.encode()).hexdigest()
    assert requirement["support_state"] == "fact_recorded"
    assert requirement["fact_support"][0]["rewrites_law"] is False
    assert requirement["fact_support"][0]["fact_id"] == "fact-wages"
    assert requirement["satisfied"] is False and requirement["proof"] is False
    assert "Protected Class" not in str(derived)
    graph = DependencyGraph()
    graph.add_node(DependencyNode(id="claim-1", node_type=NodeType.CLAIM, name="Wages", attributes={"claim_type": "wage"}))
    graph.add_node(DependencyNode(id="fact-wages", node_type=NodeType.FACT, name="fact-wages", description="The employer did not pay wages."))
    installed = DependencyGraphBuilder().apply_derived_dependency_requirements(graph, derived)
    node = next(item for item in graph.nodes.values() if item.attributes.get("admitted_law") is True)
    assert node.description == PASSAGE
    assert node.attributes["fact_support"][0]["fact_id"] == "fact-wages"
    assert any(edge.source_id == "fact-wages" and edge.target_id == node.id for edge in graph.dependencies.values())
    assert installed["requirement_ids"] == [node.id]
    derived["requirements"][0]["rule_text"] = "rewritten"
    again = DependencyGraphBuilder().apply_derived_dependency_requirements(graph, derived)
    assert again["requirement_ids"] == []
    assert node.description == PASSAGE


def test_missing_context_and_conflicting_passages_stay_unresolved():
    blocked = derive_admitted_dependency_requirements({"legal_context": {}}, _body())
    assert blocked["status"] == "unresolved_research"
    assert blocked["requirements"] == []
    assert blocked["unresolved_research"][0]["reason"] == "missing_legal_context"
    assert blocked["unresolved_research"][0]["visible"] is True
    assert blocked["source_flow_status"] == "questions_open"
    case = _case()
    conflict = _body(offline_cache=_cache(_row(PASSAGE), _row(OTHER)))
    from applications.legal_context_api import conduct_legal_source_flow
    flow = conduct_legal_source_flow(case, {**conflict, "review_decision": None})
    assert len(flow["decisions"]["custody"]) == 2
    conflict["review_passage_id"] = flow["decisions"]["custody"][0]["passage_id"]
    result = derive_admitted_dependency_requirements(case, conflict)
    assert result["requirements"] == []
    assert result["unresolved_research"][0]["reason"] == "conflicting_authority"
    assert result["unresolved_research"][0]["visible"] is True
    assert result["derivation_lineage"][0]["withheld_because"] == "conflicting_authority"
    assert "Protected Class Membership" not in str(result)
    missing_version = _body(authority_version="")
    flow = conduct_legal_source_flow(case, {**missing_version, "review_decision": "admit"})
    missing_version["review_passage_id"] = flow["decisions"]["custody"][0]["passage_id"]
    withheld = derive_admitted_dependency_requirements(case, missing_version)
    assert withheld["requirements"] == []
    assert withheld["unresolved_research"][0]["reason"] == "authority_not_promoted"
    assert "missing_authority_version" in withheld["unresolved_research"][0]["review_reasons"]


def test_workspace_persists_derivation_and_rejects_a_stale_revision(tmp_path):
    world = _composed_case_world(tmp_path)
    case = world.case
    path = f"/api/legal-analysis/{case.case_id}/dependency-requirements"
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        headers = _composed_headers(case, csrf)
        started = client.post("/api/complaint-workspace/intake-chat", headers=headers,
            json={"message": "On March 4, 2024 my wages were not paid.", "interview_action": "start",
                  "question_id": "original_complaint"})
        assert started.status_code == 200, started.text
        context = client.get(f"/api/legal-context/{case.case_id}", headers=headers)
        assert context.status_code == 200, context.text
        selected = client.post(f"/api/legal-context/{case.case_id}", headers=headers, json={
            "expected_context_revision": context.json()["context_revision"],
            "jurisdiction": "WA", "forum": "King County Superior Court", "applicability": "explicit",
            "applicable_law_date": "2024-01-01", "event_date": "2024-03-04",
            "filing_reference_date": "2024-04-01"})
        assert selected.status_code == 200, selected.text
        session = client.get("/api/complaint-workspace/session", headers=headers)
        assert session.status_code == 200, session.text
        body = session.json()
        private_revision = body["encrypted_head"]["private_revision"]
        session_revision = body["session"]["shared_interview"]["session_revision"]
        stale = client.post(path, headers=headers, json={
            **_body(), "request_id": "ux26-stale", "expected_private_revision": private_revision,
            "expected_session_revision": session_revision + 1})
        assert stale.status_code == 409, stale.text
        assert stale.json()["requirements"] == []
        preview = derive_admitted_dependency_requirements(_case(), {**_body(), "review_decision": None})
        assert preview["requirements"] == []
        from applications.legal_context_api import conduct_legal_source_flow
        flow = conduct_legal_source_flow(_case(), {**_body(), "review_decision": None})
        passage_id = flow["decisions"]["custody"][0]["passage_id"]
        saved = client.post(path, headers=headers, json={
            **_body(review_passage_id=passage_id), "request_id": "ux26-current",
            "expected_private_revision": private_revision, "expected_session_revision": session_revision,
            "elements": ["Protected Class Membership"]})
        assert saved.status_code == 200, saved.text
        payload = saved.json()
        assert payload["status"] == "current"
        assert payload["requirements"][0]["rule_text"] == PASSAGE
        assert payload["supplied_rule_text_ignored"] is True
        assert payload["derivation_persisted"] is True
        read = client.get(path, headers=headers)
        assert read.status_code == 200, read.text
        assert read.json()["read_only"] is True
        assert read.json()["requirements"][0]["rule_text"] == PASSAGE
        assert read.json()["requirements"][0]["support_state"] == "fact_recorded"
        stored = client.get("/api/complaint-workspace/session", headers=headers)
        graph = stored.json()["session"]["shared_interview"]["dependency_graph"]
        nodes = list((graph.get("nodes") or {}).values())
        assert any((node.get("attributes") or {}).get("admitted_law") is True and node.get("description") == PASSAGE for node in nodes)
        assert not any("Protected Class" in str(node.get("name")) for node in nodes)
