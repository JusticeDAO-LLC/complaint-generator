"""Refresh current legal dependencies after source or context changes.

Cases are synthetic private fixtures. No test is skipped. Changes go through
the public complaint-service research flow. A later source outage invalidates
stale legal support and keeps the existing graph, user facts, and one case
revision. It does not replace that graph with an empty success result.
"""

from __future__ import annotations

import pytest

from complaint_phases.dependency_graph import NodeType
from complaint_phases.phase_manager import ComplaintPhase
from tests.mgnd_fixtures import CASE_LABELS, USER_ID, materialize_case, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_LAW_DATE = "2024-03-15"


def _ready_text(case) -> str:
    text = case.narrative.text
    if case.narrative.jurisdiction == "unknown":
        return text
    return text + " Under Oregon law. Applicable law date: " + _LAW_DATE + "."


def _rows_for(case):
    rows = []
    for source in case.sources:
        rows.append({
            "text": source.source_text,
            "citation": source.citation,
            "uri": "fixture://" + source.authority_id,
            "corpus_version": source.version,
            "jurisdiction": "OR",
            "effective_date": source.effective_date,
        })
    return {"state_statute": rows}


def _seed(service, case) -> None:
    state = service._load_state(USER_ID)
    record = state["original_complaint"]
    record["text"] = _ready_text(case)
    record["revision"] = int(record.get("revision") or 0) + 1
    state["claim_type"] = "termination"
    service._save_state(state)


def _research(service, case, **kwargs):
    if case.label == "cancellation":
        kwargs.setdefault("cancelled", True)
    elif case.label == "storage_outage":
        cache = service._session_dir / "legal-source-cache"
        cache.write_bytes(b"storage-outage")
        kwargs.setdefault("local_rows", _rows_for(case))
    elif case.label != "missing_authority" and case.sources and case.label != "unknown":
        kwargs.setdefault("local_rows", _rows_for(case))
    return service.run_legal_research(USER_ID, **kwargs)


def _mediator(service):
    mediators = list(service._interview_mediators.values())
    assert mediators
    return mediators[-1]


def _graph(mediator):
    return mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")


def _legal_nodes(graph):
    return [
        node for node in graph.nodes.values()
        if isinstance(node.attributes, dict)
        and node.attributes.get("dependency_class") == "legally_sourced_requirement"
    ]


def _fact_snapshot(graph):
    return {
        node.id: (node.name, node.description, bool(node.satisfied), dict(node.attributes))
        for node in graph.nodes.values()
        if node.node_type == NodeType.FACT or (
            isinstance(node.attributes, dict) and node.attributes.get("about_complainant") is True
            and node.attributes.get("dependency_class") != "legally_sourced_requirement"
        )
    }


def test_meaningful_cases_are_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id and case.narrative.text for case in cases)


def test_each_case_refreshes_through_public_research_without_claiming_proof(tmp_path, monkeypatch):
    for case in meaningful_cases():
        materialized = materialize_case(tmp_path / case.label, monkeypatch, case)
        service = materialized.service
        _seed(service, case)
        receipt = _research(
            service,
            case,
            effect_receipt={
                "request_id": "effect-" + case.label,
                "source_preimage": "source-" + case.label,
                "context_preimage": "context-" + case.label,
                "operation": "refresh_verified_legal_dependencies",
                "proof": False,
            },
        )
        assert receipt["stored_as_answer"] is False
        assert receipt["proves_complaint"] is False
        assert receipt["proof"] is False
        assert receipt["worker_stalled"] is False
        counts = receipt["counts"]
        assert set(counts) == {"retrieved", "admitted", "rejected", "unavailable"}
        mediator = _mediator(service)
        graph = _graph(mediator)
        assert graph is not None and graph.nodes
        assert graph.metadata.get("empty_success") is False
        refresh = receipt.get("dependency_refresh") or {}
        assert refresh.get("graph_replaced") is False
        assert refresh.get("empty_success") is False
        assert refresh.get("atomic_case_revision") is True
        assert isinstance(refresh.get("case_revision"), int) and refresh["case_revision"] >= 1
        assert refresh.get("effect_request_id") == "effect-" + case.label
        assert graph.metadata["legal_dependency_effect"]["proof"] is False
        if case.label == "baseline":
            assert counts["admitted"] >= 1
            assert any(node.attributes.get("source_available") is not False for node in _legal_nodes(graph))
        elif case.label in {"missing_authority", "storage_outage", "cancellation", "unknown"}:
            assert all(not node.satisfied for node in _legal_nodes(graph))


def test_context_version_treatment_and_outage_keep_facts_and_drop_stale_law(tmp_path, monkeypatch):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    materialized = materialize_case(tmp_path, monkeypatch, case)
    service = materialized.service
    _seed(service, case)
    opened = service.run_intake_chat_turn(USER_ID, message=_ready_text(case))
    assert opened.get("stored_as_answer") is not True or "interview" in opened or "message" in opened
    first = _research(service, case, effect_receipt={
        "request_id": "effect-baseline-admit",
        "source_preimage": "source-baseline",
        "context_preimage": "context-baseline",
        "operation": "refresh_verified_legal_dependencies",
        "proof": False,
    })
    assert first["counts"]["admitted"] >= 1
    assert first["dependency_refresh"]["source_admission_reread"] is True
    mediator = _mediator(service)
    graph = _graph(mediator)
    graph_id = id(graph)
    legal_before = _legal_nodes(graph)
    assert legal_before
    legal_ids = {node.id for node in legal_before}
    support_before = {node.id: node.attributes.get("support_identity") for node in legal_before}
    questions_before = {node.id: node.attributes.get("question_target_id") for node in legal_before}
    facts_before = _fact_snapshot(graph)
    assert facts_before
    revision_before = int(graph.metadata.get("legal_dependency_case_revision") or 0)

    dated = service.run_legal_research(
        USER_ID,
        local_rows=_rows_for(case),
        context_updates={"applicable_law_date": "2099-01-01"},
        dependency_change={"date_changed": True},
    )
    assert dated["proof"] is False
    assert dated["dependency_refresh"]["graph_replaced"] is False
    assert dated["dependency_refresh"]["empty_success"] is False
    assert _graph(mediator) is graph
    assert id(graph) == graph_id
    assert _fact_snapshot(graph) == facts_before
    assert all(not node.satisfied for node in _legal_nodes(graph))

    versioned = service.run_legal_research(
        USER_ID,
        local_rows=_rows_for(case),
        dependency_change={"version_changed": True},
    )
    assert versioned["dependency_refresh"]["atomic_case_revision"] is True
    treated = service.run_legal_research(
        USER_ID,
        local_rows=_rows_for(case),
        dependency_change={"treatment_changed": True},
    )
    assert treated["proof"] is False
    current_legal = _legal_nodes(graph)
    assert current_legal
    assert all(not node.satisfied for node in current_legal)
    assert all(node.attributes.get("support_eligible") is False for node in current_legal)
    assert any(node.attributes.get("invalidation_reason") == "treatment_changed" for node in current_legal)
    assert any(
        node.attributes.get("support_identity") and node.attributes.get("support_identity") != support_before.get(node.id)
        for node in current_legal
    )
    assert any(
        node.attributes.get("question_target_id") and node.attributes.get("question_target_id") != questions_before.get(node.id)
        for node in current_legal
    )
    assert _fact_snapshot(graph) == facts_before
    assert all(node_id not in versioned["dependency_refresh"]["affected_node_ids"] for node_id in facts_before)

    outage_before = int(graph.metadata["legal_dependency_case_revision"])
    outage = service.run_legal_research(
        USER_ID,
        local_rows=_rows_for(case),
        dependency_change={"source_outage": True},
        effect_receipt={
            "request_id": "effect-baseline-outage",
            "source_preimage": "source-outage",
            "context_preimage": "context-outage",
            "operation": "source_outage",
            "proof": False,
        },
    )
    assert outage["dependency_refresh"]["source_outage"] is True
    assert outage["dependency_refresh"]["empty_success"] is False
    assert outage["dependency_refresh"]["graph_replaced"] is False
    assert outage["dependency_refresh"]["effect_request_id"] == "effect-baseline-outage"
    assert _graph(mediator) is graph
    assert graph.nodes
    assert graph.metadata.get("empty_success") is False
    assert graph.metadata.get("admission_status") == "unavailable"
    survived = [node for node in _legal_nodes(graph) if node.id in legal_ids]
    assert survived
    assert all(not node.satisfied for node in survived)
    assert all(node.attributes.get("source_available") is False for node in survived)
    assert _fact_snapshot(graph) == facts_before
    revision_after = int(graph.metadata["legal_dependency_case_revision"])
    assert revision_after > revision_before
    assert revision_after - outage_before <= 2
    assert graph.metadata["legal_dependency_case_revision"] == outage["dependency_refresh"]["case_revision"]
