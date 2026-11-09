"""A dependency refresh cannot rewrite the explicit selection owner's history."""
from copy import deepcopy

import pytest

from applications.legal_context_selection import apply_legal_context_selection
from complaint_phases.phase_manager import ComplaintPhase
from tests.test_gui28_actual_dependency_refresh import _actual, _request

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.mark.parametrize("applicability", ["explicit", "unknown", "disputed"])
def test_actual_selected_legal_context_is_unchanged_by_dependency_refresh(tmp_path, monkeypatch, applicability):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    case = mediator.workflow_actions._refresh_case_file()
    selected = apply_legal_context_selection(case, {
        "expected_context_revision": case["legal_context"]["context_revision"],
        "jurisdiction": "OR", "forum": "Synthetic selected owner forum", "applicability": applicability,
        "applicable_law_date": "2024-06-01"}, dependency_graph=graph)
    assert selected["changed"] is True
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", selected["case_file"])
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", selected["dependency_graph"])
    owner_fields = {key: deepcopy(value) for key, value in selected["case_file"].items() if key.startswith("legal_context")}
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source),
        canonical_source_records={"employment_discrimination": [source]})
    assert result["applied"] is True
    actual = {key: value for key, value in mediator.workflow_actions._refresh_case_file().items() if key.startswith("legal_context")}
    assert actual == owner_fields


def test_inconsistent_selected_context_refuses_instead_of_silently_rewriting_owner(tmp_path, monkeypatch):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    case = mediator.workflow_actions._refresh_case_file()
    selected = apply_legal_context_selection(case, {"expected_context_revision": case["legal_context"]["context_revision"],
        "jurisdiction": "OR", "forum": "Synthetic selected owner forum", "applicability": "explicit",
        "applicable_law_date": "2024-06-01"}, dependency_graph=graph)
    draft = selected["case_file"]
    draft["legal_context_overrides"]["jurisdiction"] = "WA"
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", draft)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", selected["dependency_graph"])
    before_case, before_graph = deepcopy(draft), deepcopy(selected["dependency_graph"].to_dict())
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source),
        canonical_source_records={"employment_discrimination": [source]})
    assert result["applied"] is False and result["error"]["code"] == "current_legal_context_changed"
    assert mediator.workflow_actions._refresh_case_file() == before_case
    assert selected["dependency_graph"].to_dict() == before_graph


@pytest.mark.parametrize("bad", ["boolean_generation", "empty_operation"])
def test_readonly_receipt_revalidation_retains_exact_typed_request_boundary(tmp_path, monkeypatch, bad):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    first = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source))
    assert first["applied"] is True
    values = _request(source)
    kwargs = {key: values[key] for key in ("case_id", "actor_principal_id", "case_revision", "consent_generation",
        "consent_revoked", "grant_revision", "granted_actions", "legal_source_hashes")}
    kwargs.update(dependency_generation=1, operation_id="check-current",
        claimed={"refresh_operation_id": values["operation_id"]})
    if bad == "boolean_generation":
        kwargs["claimed"]["dependency_generation"] = True
    else:
        kwargs["operation_id"] = ""
    before = deepcopy(graph.to_dict())
    result = mediator.workflow_actions.accept_legal_refresh_late_result(**kwargs)
    assert result["applied"] is False and result["error"]["code"] == "refresh_field"
    assert graph.to_dict() == before


def test_cold_source_replacement_preserves_existing_factual_dependency_edges(tmp_path, monkeypatch):
    from complaint_phases.dependency_graph import NodeType
    from tests.test_authority_dependency_pipeline import _CONTEXT, _local_sources, _source_record
    from tests.test_authority_dependency_public_pipeline import _workflow
    source = _source_record("cold-old-authority", "notice")
    first = _workflow(tmp_path / "first")
    _local_sources(monkeypatch, first, [source])
    started = first.workflow_actions.transition_interview(action="start",
        narrative="My employer discriminated against me." + _CONTEXT,
        user_id="source-fixture-owner", case_id="synthetic-case")
    assert not started.get("error")
    projection = deepcopy(first.workflow_actions.export_session_projection())
    fresh = _workflow(tmp_path / "cold")
    assert not fresh.workflow_actions.restore_session_projection(deepcopy(projection)).get("error")
    graph = fresh.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    factual = {key: deepcopy(edge.to_dict()) for key, edge in graph.dependencies.items()
        if graph.nodes[edge.source_id].node_type == NodeType.FACT}
    assert factual
    replacement = _source_record("cold-new-authority", "hearing")
    result = fresh.workflow_actions.refresh_legal_dependency_graph(**_request(replacement),
        canonical_source_records={"employment_discrimination": [replacement]})
    assert result["applied"] is True
    assert {key: graph.dependencies[key].to_dict() for key in factual if key in graph.dependencies} == factual
    assert len(graph.dependencies) == len({edge.id for edge in graph.dependencies.values()})
