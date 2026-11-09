"""Jurisdiction-specific legal requirements enter intake only through sourced records."""

from copy import deepcopy

import pytest

from complaint_phases.dependency_graph import DependencyGraphBuilder
from complaint_phases.phase_manager import ComplaintPhase
from integrations.ipfs_datasets.legal import (
    SourcedLegalRequirement,
    adapt_sourced_legal_requirements,
    classify_legal_date,
    empty_legal_context,
    intake_legal_selection,
    unresolved_legal_requirement,
)
from integrations.ipfs_datasets.logic import extract_source_bound_rule_candidates
from mediator.legal_hooks import SummaryJudgmentHook
from tests.test_authority_dependency_pipeline import _source_record


class _MockBackend:
    id = "mock_backend"

    def __call__(self, prompt):
        return "1. A complainant-supplied element that is not a statute."


def _mediator():
    from mediator.mediator import Mediator

    return Mediator([_MockBackend()])


def _sourced_nodes(graph):
    return [
        node for node in graph.nodes.values()
        if isinstance(node.attributes, dict)
        and node.attributes.get("dependency_class") == "legally_sourced_requirement"
    ]


def _unresolved_nodes(graph):
    return [
        node for node in graph.nodes.values()
        if isinstance(node.attributes, dict)
        and node.attributes.get("dependency_class") == "unresolved_legal_requirement"
    ]


def _current_context(query_date="2024-06-01", *, jurisdiction="OR", revision=0):
    context = empty_legal_context()
    context.update(jurisdiction=jurisdiction, context_revision=revision)
    context["applicable_law_date"] = classify_legal_date(query_date, role="applicable_law_date")
    return context


def _promoted_fixture(*, expires=False):
    # A clearly synthetic, owned source exercises the real LAW04/05 promotion
    # and pinned LegalIR API; no promotion or verification method is replaced.
    source = _source_record("notice", "notice")
    source["rule_text"] = source["source_text"]
    if expires:
        source["expiration_date"] = "2024-12-31"
    result = extract_source_bound_rule_candidates(source)
    assert len(result["promoted_requirements"]) == 1
    candidate = result["promoted_requirements"][0]
    return dict(candidate, claim_type="employment_discrimination", name="Notice",
                description=candidate["rule_text"], source_record=source)


def _typed_fixture(record):
    core = {"claim_type", "name", "description", "jurisdiction", "authority_version", "source_record"}
    return SourcedLegalRequirement(
        claim_type=record["claim_type"], name=record["name"], description=record["description"],
        authority_locator=record["citation"], source_locator=str(record["source_span"]),
        jurisdiction=record["jurisdiction"], effective_date=record["temporal_applicability"]["effective_date"],
        authority_version=record["authority_version"], derivation_status="source_derived",
        proof_status="source_bound", source_record=record["source_record"],
        extra={key: deepcopy(value) for key, value in record.items() if key not in core},
    )


def test_unknown_jurisdiction_is_preserved_and_blocks_rule_selection():
    context = {
        "jurisdiction": "",
        "applicable_law_date": {"raw_text": "", "role": "applicable_law_date"},
        "event_date": {"raw_text": "", "role": "event_date"},
    }
    selection = intake_legal_selection(context, [])
    assert selection["ready_to_select"] is False
    assert selection["jurisdiction"] == "unknown"
    reasons = {item["reason"] for item in selection["questions"]}
    assert {"unresolved_jurisdiction", "missing_applicable_law_date", "missing_claim_candidates"} <= reasons

    mediator = _mediator()
    result = mediator.start_three_phase_process("Something unfair happened and I want the law applied.")
    graph = mediator.phase_manager.get_phase_data(
        __import__("complaint_phases.phase_manager", fromlist=["ComplaintPhase"]).ComplaintPhase.INTAKE,
        "dependency_graph",
    )
    assert graph.metadata["legal_context_jurisdiction"] == "unknown"
    assert graph.metadata["legal_selection_status"] == "unresolved_context"
    assert not _sourced_nodes(graph)
    unresolved = _unresolved_nodes(graph)
    assert unresolved
    assert all(node.attributes.get("jurisdiction") == "unknown" for node in unresolved)
    assert all(node.attributes.get("law_derived") is False for node in unresolved)
    assert all(node.attributes.get("source_available") is False for node in unresolved)
    assert graph.metadata["heuristic_law_derived_invoked"] is False
    assert graph.metadata["unresolved_legal_requirements"]
    questions = result["initial_questions"]
    assert questions
    assert questions[0]["type"] == "legal_context"
    assert questions[0]["jurisdiction"] == "unknown"
    assert any(item.get("reason") == "unresolved_jurisdiction" for item in questions)


def test_summary_judgment_strings_are_not_builder_rules():
    hook = SummaryJudgmentHook(_mediator())
    generated = hook.generate_requirements(
        {"claim_types": ["employment_discrimination"], "jurisdiction": "federal", "legal_areas": []},
        [{"citation": "Synthetic", "title": "Fixture", "relevance": "none"}],
    )
    assert all(isinstance(item, str) for item in generated["employment_discrimination"])
    adapted = hook.adapt_requirements_for_dependency_graph(generated)
    assert adapted["employment_discrimination"]
    assert all(entry["intake_requirement_status"] == "unresolved" for entry in adapted["employment_discrimination"])
    assert all(entry["proof_status"] == "not_authoritative" for entry in adapted["employment_discrimination"])
    assert all(entry["name"] == "Unresolved legal requirement" for entry in adapted["employment_discrimination"])
    asserted = " ".join(entry["asserted_text"] for entry in adapted["employment_discrimination"])
    graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Discrimination", "type": "employment_discrimination", "description": "I was fired"}],
        legal_requirements=generated,
        require_verified_legal_sources=True,
    )
    assert not _sourced_nodes(graph)
    unresolved = _unresolved_nodes(graph)
    assert unresolved
    assert all(node.name == "Unresolved legal requirement" for node in unresolved)
    assert all(asserted.find(node.name) < 0 for node in unresolved)
    assert graph.metadata["unresolved_legal_requirements"]


def test_sourced_requirement_keeps_authority_identity():
    record = _promoted_fixture()
    requirement = _typed_fixture(record)
    entry = requirement.as_builder_entry(legal_context=_current_context())
    for key in (
        "authority_locator", "source_locator", "jurisdiction", "effective_date",
        "authority_version", "derivation_status", "proof_status",
    ):
        assert entry[key]
    assert entry["jurisdiction"] == "OR"
    assert entry["derivation_status"] == "source_derived"
    assert entry["proof_status"] == "source_bound"
    assert entry["intake_requirement_status"] == "source_bound"
    assert entry["source_span"] == record["source_span"]
    assert entry["source_hash"] == record["source_hash"]
    assert entry["source_record"] == record["source_record"]
    assert entry["source_record"] is not record["source_record"]


def test_user_assertion_cannot_create_authoritative_law():
    asserted = {
        "claim_type": "retaliation",
        "name": "The statute requires reinstatement",
        "description": "The statute requires reinstatement",
        "citation": "ORS 000.000",
        "jurisdiction": "OR",
        "effective_date": "2024-01-01",
        "authority_version": "user-typed",
        "origin": "user",
        "user_asserted": True,
    }
    adapted = adapt_sourced_legal_requirements({"retaliation": [asserted]})
    entry = adapted["retaliation"][0]
    assert entry["derivation_status"] == "user_assertion"
    assert entry["proof_status"] == "not_authoritative"
    assert entry["authority_locator"] == ""
    assert entry["unresolved_reason"] == "user_assertion_cannot_create_law"
    graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Retaliation", "type": "retaliation", "description": "I was fired"}],
        legal_requirements=adapted,
        require_verified_legal_sources=True,
    )
    assert not _sourced_nodes(graph)
    unresolved = _unresolved_nodes(graph)
    assert unresolved
    assert all(node.attributes["user_assertion_is_not_law"] is True for node in unresolved)
    assert all(node.name != asserted["name"] for node in unresolved)


def test_ambiguous_authority_is_unresolved_and_initial_graph_receives_requirements():
    ambiguous = {
        "name": "Maybe a duty",
        "description": "Some duty might exist",
        "jurisdiction": "OR",
    }
    adapted = adapt_sourced_legal_requirements({"employment_discrimination": [ambiguous]})
    assert adapted["employment_discrimination"][0]["unresolved_reason"] == "missing_authority_locator"
    graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Discrimination", "type": "employment_discrimination", "description": "I was fired"}],
        legal_requirements=adapted,
        require_verified_legal_sources=True,
    )
    assert not _sourced_nodes(graph)
    assert _unresolved_nodes(graph)
    assert graph.metadata["unresolved_legal_requirements"][0]["reason"] == "missing_authority_locator"

    mediator = _mediator()
    seen = {}
    original = mediator.dg_builder.build_from_claims

    def _capture(claims, legal_requirements=None, **kwargs):
        seen["legal_requirements"] = legal_requirements
        seen["explicit"] = "legal_requirements" in kwargs or legal_requirements is not None
        return original(claims, legal_requirements=legal_requirements, **kwargs)

    mediator.dg_builder.build_from_claims = _capture
    mediator.start_three_phase_process("I was treated unfairly.")
    assert isinstance(seen["legal_requirements"], dict)
    assert seen["explicit"] is True
    assert seen["legal_requirements"]
    assert all(
        entry.get("intake_requirement_status") == "unresolved"
        for entries in seen["legal_requirements"].values()
        for entry in entries
    )


def test_unresolved_helper_does_not_invent_a_rule():
    requirement = unresolved_legal_requirement("unknown", "unresolved_jurisdiction")
    assert requirement.jurisdiction == "unknown"
    assert requirement.authority_locator == ""
    assert requirement.proof_status == "unresolved"
    assert requirement.name == "Unresolved legal requirement"


@pytest.mark.parametrize("typed", [False, True])
def test_public_hook_current_source_proof_enters_strict_initial_graph(typed):
    record = _promoted_fixture()
    before = deepcopy(record)
    value = _typed_fixture(record) if typed else record
    context = _current_context()
    adapted = SummaryJudgmentHook(None).adapt_requirements_for_dependency_graph(
        {"employment_discrimination": [value]}, context,
    )
    entry = adapted["employment_discrimination"][0]
    assert entry["proof_status"] == entry["intake_requirement_status"] == "source_bound"
    assert entry["context_revision"] == context["context_revision"]
    graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Discrimination", "type": "employment_discrimination", "description": "I was fired"}],
        legal_requirements=adapted, require_verified_legal_sources=True,
    )
    sourced = _sourced_nodes(graph)
    assert len(sourced) == 1
    assert not _unresolved_nodes(graph)
    assert not graph.metadata["legal_source_gaps"]
    assert sourced[0].attributes["source_span"] == record["source_span"]
    assert sourced[0].attributes["source_hash"] == record["source_hash"]
    assert sourced[0].attributes["temporal_applicability"]["query_date"] == "2024-06-01"
    assert record == before


def test_actual_mediator_initial_graph_uses_local_source_proof_through_adapter(tmp_path):
    from mediator.mediator import Mediator

    mediator = Mediator([_MockBackend()], evidence_db_path=str(tmp_path / "evidence.duckdb"),
                        legal_authority_db_path=str(tmp_path / "authorities.duckdb"),
                        claim_support_db_path=str(tmp_path / "support.duckdb"))
    mediator.state.username = "tui04-synthetic-source-owner"
    source = _source_record("notice", "notice")
    stored = mediator.legal_authority_storage.add_authority({
        "type": "statute", "source": "owned-synthetic-local-corpus", "title": "Synthetic notice rule",
        "citation": source["citation"], "content": source["source_text"], "jurisdiction": "OR",
        "metadata": {key: value for key, value in source.items() if key not in {"id", "content", "claim_type"}},
    }, mediator.state.username, claim_type="employment_discrimination")
    assert stored > 0
    mediator.start_three_phase_process(
        "My employer discriminated against me. Under Oregon law. Applicable law date: 2024-06-01."
    )
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    sourced = _sourced_nodes(graph)
    assert len(sourced) == 1
    assert not _unresolved_nodes(graph)
    assert not graph.metadata["legal_source_gaps"]
    proof = sourced[0].attributes
    assert proof["proof_status"] == proof["intake_requirement_status"] == "source_bound"
    assert proof["source_record"]["source_text"] == source["source_text"]
    assert proof["source_hash"] == source["source_hash"]
    assert proof["source_record"]["metadata"]["provenance"] == source["provenance"]
    assert proof["temporal_applicability"]["query_date"] == "2024-06-01"


@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize("change", ["missing", "missing_date", "missing_jurisdiction", "new_date", "new_jurisdiction", "revision"])
def test_genuine_old_source_proof_cannot_override_current_context(typed, change):
    record = _promoted_fixture(expires=True)
    before = deepcopy(record)
    context = _current_context()
    if change == "missing":
        context = None
    elif change == "missing_date":
        context = _current_context("")
    elif change == "missing_jurisdiction":
        context["jurisdiction"] = "unknown"
    elif change == "new_date":
        context = _current_context("2025-06-01")
    elif change == "new_jurisdiction":
        context["jurisdiction"] = "CA"
    elif change == "revision":
        record["context_revision"] = 0
        context["context_revision"] = 1
        before = deepcopy(record)
    value = _typed_fixture(record) if typed else record
    adapted = SummaryJudgmentHook(None).adapt_requirements_for_dependency_graph(
        {"employment_discrimination": [value]}, context,
    )
    entry = adapted["employment_discrimination"][0]
    assert entry["intake_requirement_status"] == entry["proof_status"] == "unresolved"
    assert entry["unresolved_reason"]
    graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Discrimination", "type": "employment_discrimination", "description": "I was fired"}],
        legal_requirements=adapted, require_verified_legal_sources=True,
    )
    assert not _sourced_nodes(graph)
    assert _unresolved_nodes(graph)
    assert graph.metadata["legal_source_gaps"]
    assert record == before


@pytest.mark.parametrize("typed", [False, True])
def test_coordinate_and_verified_labels_without_source_proof_stay_unresolved(typed):
    record = {"claim_type": "employment_discrimination", "name": "Notice", "description": "A model says give notice.",
              "authority_locator": "Synthetic fixture citation", "source_locator": "span:0-10",
              "citation": "Synthetic fixture citation", "jurisdiction": "OR", "effective_date": "2024-01-01",
              "authority_version": "2024-edition", "proof_status": "source_bound", "source_bound": True,
              "verification_status": "verified", "promoted": True, "applicable": True, "support_eligible": True}
    if typed:
        value = SourcedLegalRequirement(claim_type=record["claim_type"], name=record["name"], description=record["description"],
            authority_locator=record["authority_locator"], source_locator=record["source_locator"],
            jurisdiction="OR", effective_date="2024-01-01", authority_version="2024-edition",
            derivation_status="source_derived", proof_status="source_bound")
        assert value.as_builder_entry(legal_context=_current_context())["proof_status"] == "unresolved"
    else:
        value = record
    entry = adapt_sourced_legal_requirements({record["claim_type"]: [value]}, legal_context=_current_context())[record["claim_type"]][0]
    assert entry["proof_status"] == entry["intake_requirement_status"] == "unresolved"
    graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Discrimination", "type": record["claim_type"], "description": "I was fired"}],
        legal_requirements={record["claim_type"]: [entry]}, require_verified_legal_sources=True,
    )
    assert not _sourced_nodes(graph)
    assert _unresolved_nodes(graph)
