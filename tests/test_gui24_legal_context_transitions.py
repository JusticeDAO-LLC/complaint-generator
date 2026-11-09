"""Synthetic source-complete context CAS and real dependency invalidation."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from applications.legal_context_api import LegalContextError, select_explicit_legal_context
from complaint_phases.dependency_graph import DependencyGraph, DependencyGraphBuilder, DependencyNode, NodeType
from integrations.ipfs_datasets.legal import empty_legal_context
from applications.legal_context_selection import apply_legal_context_selection


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _case_file(*, selected=False):
    context = empty_legal_context()
    case = {"legal_context": context, "canonical_facts": [{"id": "synthetic-fact", "text": "Synthetic source fact"}],
        "factual_provenance": [{"stable_id": "synthetic-source-proof"}], "proof_leads": [], "legal_dependencies": []}
    if selected:
        context.update(jurisdiction="OR", jurisdiction_explicit=True,
            jurisdiction_applicability="explicit", status="explicit", context_revision=1)
        case["legal_context_applicability"] = "explicit"
        case["legal_context_forum"] = {"value": "Synthetic original forum", "applicability": "explicit"}
    return case


def _graphs():
    graph = DependencyGraph()
    fact = DependencyNode(id="synthetic-fact", node_type=NodeType.FACT,
        name="Synthetic source fact", satisfied=True,
        attributes={"about_complainant": True, "stable_id": "synthetic-source-proof"})
    legal = DependencyNode(id="synthetic-legal", node_type=NodeType.LEGAL_ELEMENT,
        name="Synthetic legal requirement", satisfied=True,
        attributes={"dependency_class": "legally_sourced_requirement", "support_eligible": True,
            "satisfaction_state": "satisfied", "support_identity": "synthetic-support-old",
            "proof_cache_identity": "synthetic-proof-old",
            "proof_cache": {"satisfied": True, "reusable": True},
            "dependency_scope": {"rule_id": "synthetic-rule", "fact_ids": [fact.id]}})
    graph.add_node(fact)
    graph.add_node(legal)
    return graph, fact, legal


def test_first_jurisdiction_selection_advances_revision_and_retains_prior_unknown():
    case = _case_file()
    owner = SimpleNamespace(intake_case_file=case)
    result = select_explicit_legal_context(owner, {"expected_context_revision": 0, "jurisdiction": "Oregon"})
    assert result["jurisdiction"] == "OR"
    assert result["context_revision"] == 1
    assert result["prior_versions"][0]["context_revision"] == 0
    with pytest.raises(LegalContextError, match="legal_context_revision_conflict"):
        select_explicit_legal_context(owner, {"expected_context_revision": 0, "jurisdiction": "Washington"})
    assert case["legal_context"]["jurisdiction"] == "OR"


@pytest.mark.parametrize("field,value", [("forum", "Synthetic replacement forum"), ("applicability", "unknown")])
def test_forum_and_applicability_invalidate_actual_legal_support_and_cache_only(field, value):
    case = _case_file(selected=True)
    graph, fact, legal = _graphs()
    fact_before = deepcopy(fact)
    owner = SimpleNamespace(intake_case_file=case,
        refresh_verified_legal_dependencies=lambda change: DependencyGraphBuilder().refresh_affected_dependencies(graph, change))
    result = select_explicit_legal_context(owner, {"expected_context_revision": 1, field: value})
    assert result["context_revision"] == 2
    assert legal.satisfied is False
    assert legal.attributes["support_eligible"] is False
    assert legal.attributes["satisfaction_state"] == "invalidated"
    assert legal.attributes["proof_cache"]["satisfied"] is False
    assert legal.attributes["proof_cache"]["reusable"] is False
    assert legal.attributes["rejected_proof_cache_identity"] == "synthetic-proof-old"
    assert fact == fact_before


@pytest.mark.parametrize("expected", [None, True, False, 0.0, "0", -1])
def test_context_compare_and_swap_requires_exact_current_integer(expected):
    case = _case_file()
    before = deepcopy(case)
    with pytest.raises(LegalContextError, match="legal_context_revision_conflict"):
        apply_legal_context_selection(case, {"expected_context_revision": expected, "jurisdiction": "OR"})
    assert case == before


@pytest.mark.parametrize("field,value", [
    ("event_date", "2024-03-04"), ("event_dates", ["2024-03-04", "2024-03-05"]),
    ("applicable_law_date", "2024-03-04"), ("filing_reference_date", "2024-04-01"),
    ("corpus_retrieval_date", "2024-05-01"),
])
def test_first_date_answer_versions_without_inventing_jurisdiction(field, value):
    case = _case_file()
    original = deepcopy(case)
    result = apply_legal_context_selection(case, {"expected_context_revision": 0, field: value})
    assert result["changed"] is True
    assert result["projection"]["context_revision"] == 1
    assert result["projection"]["prior_versions"][0]["context_revision"] == 0
    assert result["projection"]["jurisdiction"] == "unknown"
    assert result["projection"]["applicability"] == "unknown"
    assert result["change"]["date_changed"] is True
    assert case == original


@pytest.mark.parametrize("applicability,jurisdiction", [("explicit", "OR"), ("disputed", "federal"), ("unknown", "unknown")])
def test_identical_context_selection_is_noop_not_new_version_or_history(applicability, jurisdiction):
    first = apply_legal_context_selection(_case_file(), {"expected_context_revision": 0,
        "jurisdiction": jurisdiction, "applicability": applicability})
    selected = first["case_file"]
    before = deepcopy(selected)
    repeated = apply_legal_context_selection(selected, {"expected_context_revision": first["projection"]["context_revision"],
        "jurisdiction": jurisdiction, "applicability": applicability})
    assert repeated["changed"] is False
    assert repeated["case_file"] == before
    assert repeated["dependency_refresh"] is None
    assert selected == before


def test_one_actual_dg_refresh_on_copied_snapshot_preserves_inputs_and_factual_provenance(monkeypatch):
    case = _case_file(selected=True)
    graph, fact, legal = _graphs()
    before_case, before_graph = deepcopy(case), deepcopy(graph.to_dict())
    calls = []
    original = DependencyGraphBuilder.refresh_affected_dependencies

    def observed(self, current, change):
        calls.append(deepcopy(change))
        return original(self, current, change)

    monkeypatch.setattr(DependencyGraphBuilder, "refresh_affected_dependencies", observed)
    result = apply_legal_context_selection(case, {"expected_context_revision": 1,
        "jurisdiction": "Washington", "forum": "Synthetic replacement forum", "applicability": "unknown"},
        dependency_graph=graph)
    assert len(calls) == 1
    assert calls[0] == result["change"]
    assert result["projection"]["context_revision"] == 2
    assert result["dependency_refresh"]["user_facts_modified"] is False
    assert result["dependency_graph"] is not graph
    assert result["dependency_graph"].nodes[legal.id].satisfied is False
    assert result["dependency_graph"].nodes[fact.id] == fact
    assert result["case_file"]["canonical_facts"] == case["canonical_facts"]
    assert result["case_file"]["factual_provenance"] == case["factual_provenance"]
    assert case == before_case and graph.to_dict() == before_graph


def test_pure_refresh_failure_cannot_partially_publish_context_or_graph(monkeypatch):
    case = _case_file(selected=True)
    graph, _, _ = _graphs()
    before_case, before_graph = deepcopy(case), deepcopy(graph.to_dict())

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("Synthetic dependency owner unavailable")

    monkeypatch.setattr(DependencyGraphBuilder, "refresh_affected_dependencies", unavailable)
    with pytest.raises(LegalContextError, match="legal_dependency_refresh_unavailable"):
        apply_legal_context_selection(case, {"expected_context_revision": 1,
            "forum": "Synthetic replacement forum"}, dependency_graph=graph)
    assert case == before_case and graph.to_dict() == before_graph


def test_unknown_jurisdiction_cannot_retain_explicit_applicability():
    result = apply_legal_context_selection(_case_file(selected=True),
        {"expected_context_revision": 1, "jurisdiction": "unknown"})
    assert result["projection"]["jurisdiction"] == "unknown"
    assert result["projection"]["applicability"] == "unknown"
    assert result["projection"]["governing_law_defaulted"] is False


@pytest.mark.parametrize("extra", [
    {"jurisdiction": {}}, {"forum": []}, {"applicable_law_date": True},
    {"event_dates": "2024-03-04"}, {"event_dates": [1]}, {"proof_state": "verified"},
])
def test_malformed_fields_or_caller_proof_authority_are_refused_without_mutation(extra):
    case = _case_file()
    before = deepcopy(case)
    with pytest.raises(LegalContextError, match="legal_context_field"):
        apply_legal_context_selection(case, {"expected_context_revision": 0, **extra})
    assert case == before


@pytest.mark.parametrize("updates", [{"jurisdiction": "Oregon"}, {"applicable_law_date": "2024-05-31"}])
def test_existing_mediator_current_source_readmission_retains_eligibility(tmp_path, monkeypatch, updates):
    from complaint_phases.phase_manager import ComplaintPhase
    from tests.test_authority_dependency_public_pipeline import _start
    from tests.test_authority_dependency_pipeline import _source_record, _sourced_nodes

    mediator, graph = _start(monkeypatch, tmp_path, [_source_record("synthetic-context-rule", "notice")])
    initial = [node for node in _sourced_nodes(graph) if node.attributes.get("source_available")]
    assert initial and all(node.attributes.get("support_eligible") is True for node in initial)
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
    mediator.apply_explicit_legal_context(case_file, **updates)
    current = [node for node in _sourced_nodes(graph) if node.attributes.get("source_available")]
    assert current and all(node.attributes.get("support_eligible") is True for node in current)
    assert all(node.satisfied is False for node in current)
    assert mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph") is graph


@pytest.mark.parametrize("mode", ["unknown", "disputed"])
def test_saved_unresolved_applicability_survives_real_workflow_resume_and_source_readmission(tmp_path, monkeypatch, mode):
    from complaint_phases.phase_manager import ComplaintPhase
    from mediator.workflow_service import WorkflowActionService
    from tests.test_authority_dependency_public_pipeline import _workflow
    from tests.test_authority_dependency_pipeline import _CONTEXT, _local_sources, _source_record, _sourced_nodes

    source = _source_record("synthetic-context-rule", "notice")
    initial = _workflow(tmp_path / "initial")
    _local_sources(monkeypatch, initial, [source])
    started = initial.workflow_actions.transition_interview(action="start",
        narrative="Synthetic employment discrimination account." + _CONTEXT)
    assert not started.get("error"), started
    exported = initial.workflow_actions.export_session_projection()
    assert exported and exported["knowledge_graph"]
    selected = apply_legal_context_selection(exported["intake_case_file"], {
        "expected_context_revision": exported["intake_case_file"]["legal_context"]["context_revision"],
        "applicability": mode,
    }, dependency_graph=DependencyGraph.from_dict(deepcopy(exported["dependency_graph"])))
    assert selected["changed"] is True
    saved = WorkflowActionService.project_legal_context_selection(exported,
        case_file=selected["case_file"], dependency_graph=selected["dependency_graph"])
    reopened = _workflow(tmp_path / "reopened")
    _local_sources(monkeypatch, reopened, [source])
    restored = reopened.workflow_actions.transition_interview(action="resume", session_projection=saved)
    assert not restored.get("error"), restored
    case_file = reopened.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
    canonical = reopened.resolve_intake_legal_selection(
        [{"type": "employment_discrimination", "name": "Synthetic claim"}], case_file)
    assert canonical["ready_to_select"] is False
    assert canonical["context_applicability"] == mode
    assert canonical["legal_context"]["candidate_jurisdiction"] == "OR"
    assert canonical["legal_context"]["applicable_law_date"]["raw_text"]
    assert case_file.get("legal_context_overrides", {}) == saved["intake_case_file"].get("legal_context_overrides", {})
    reopened.refresh_verified_legal_dependencies({"context_changed": True})
    current_graph = reopened.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    assert not any(node.attributes.get("source_available") for node in _sourced_nodes(current_graph))


def test_omitted_first_applicability_stays_unresolved_while_legacy_absence_is_preserved(tmp_path, monkeypatch):
    from tests.test_authority_dependency_public_pipeline import _workflow
    from complaint_phases.phase_manager import ComplaintPhase
    from complaint_phases.intake_case_file import apply_explicit_legal_context

    mediator = _workflow(tmp_path)
    legacy = _case_file()
    apply_explicit_legal_context(legacy, jurisdiction="OR", applicable_law_date="2024-06-01")
    claims = [{"type": "employment_discrimination", "name": "Synthetic claim"}]
    assert "legal_context_applicability" not in legacy
    assert mediator.resolve_intake_legal_selection(claims, legacy)["ready_to_select"] is True
    selected = apply_legal_context_selection(_case_file(), {"expected_context_revision": 0,
        "jurisdiction": "OR", "applicable_law_date": "2024-06-01"})
    canonical = mediator.resolve_intake_legal_selection(claims, selected["case_file"])
    assert canonical["ready_to_select"] is False
    assert canonical["context_applicability"] == "unknown"
    assert canonical["legal_context"]["candidate_jurisdiction"] == "OR"
