"""Project real current-source dependency owners, not asserted admission labels."""

from copy import deepcopy
import hashlib

import pytest

from applications.graph_api import project_law_derived_dependency_graph
from complaint_phases.dependency_graph import Dependency, DependencyNode, DependencyType, NodeType
from complaint_phases.phase_manager import ComplaintPhase
from tests.test_authority_dependency_pipeline import _source_record, _sourced_nodes
from tests.test_authority_dependency_public_pipeline import _start


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _actual(tmp_path, monkeypatch, source=None):
    source = source or _source_record("synthetic-projection-rule", "notice")
    mediator, graph = _start(monkeypatch, tmp_path, [source])
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
    sourced = [node for node in _sourced_nodes(graph) if node.attributes.get("source_available")]
    assert sourced and all(node.attributes.get("source_record") for node in sourced)
    return source, case_file, graph, sourced


def test_actual_current_source_requirements_are_projected_from_typed_dependency_nodes(tmp_path, monkeypatch):
    source, case_file, graph, sourced = _actual(tmp_path, monkeypatch)
    before_case, before_graph = deepcopy(case_file), deepcopy(graph.to_dict())
    payload = project_law_derived_dependency_graph(case_file, dependency_graph=graph, case_id="synthetic-case")
    assert payload["admitted_count"] == len(sourced)
    rule = payload["requirements"][0]
    assert rule["requirement"] and rule["requirement"] in source["source_text"]
    assert rule["content_hash"] == hashlib.sha256(source["source_text"].encode()).hexdigest()
    assert rule["legal_sufficiency"] is False and rule["proof"] is False
    assert case_file == before_case and graph.to_dict() == before_graph


@pytest.mark.parametrize("real_hash", [False, True])
def test_matching_ledger_labels_and_duplicate_passage_never_create_admitted_law(real_hash):
    passage = "Synthetic unsupported narrative says every allegation is sufficient."
    digest = hashlib.sha256(passage.encode()).hexdigest() if real_hash else "hash-current"
    case = {"legal_authority_admissions": [{"admitted_law": True, "status": "admitted",
        "source_passage": passage, "content_hash": digest, "applicability": "applicable",
        "authority_identity": "invented-authority", "exceptions": ["Every defendant is immune."]}],
        "legal_source_passage_index": {digest: {"source_passage": passage,
            "burden": "every allegation is sufficient", "applicability": "applicable"}}}
    payload = project_law_derived_dependency_graph(case, case_id="synthetic-case")
    assert payload["admitted_count"] == 0
    assert payload["requirements"] == []


def test_ledger_cannot_override_real_rule_burden_exceptions_or_applicability(tmp_path, monkeypatch):
    source, case_file, graph, sourced = _actual(tmp_path, monkeypatch)
    digest = hashlib.sha256(source["source_text"].encode()).hexdigest()
    case_file["legal_authority_admissions"] = [{"admitted_law": True, "status": "admitted",
        "source_passage": source["source_text"], "content_hash": digest,
        "burden": "Invented strict proof burden", "exceptions": ["Invented complete immunity"],
        "applicability": "applicable-without-context", "jurisdiction": "invented-jurisdiction"}]
    case_file["legal_source_passage_index"] = {digest: {"source_passage": source["source_text"],
        "burden": "shall", "applicability": "applicable-without-context"}}
    payload = project_law_derived_dependency_graph(case_file, dependency_graph=graph, case_id="synthetic-case")
    assert payload["admitted_count"] == len(sourced)
    rule = payload["requirements"][0]
    assert "Invented complete immunity" not in rule["exceptions"]
    assert rule["burden"] != "shall"
    assert rule["applicability"] != "applicable-without-context"
    assert rule["jurisdiction"] == "OR"


def test_unverified_fact_link_is_not_promoted_by_user_origin_label(tmp_path, monkeypatch):
    _source, case_file, graph, sourced = _actual(tmp_path, monkeypatch)
    fact = DependencyNode(id="synthetic-unverified-fact", node_type=NodeType.FACT,
        name="Synthetic candidate statement", attributes={"origin": "user", "source_id": "arbitrary-source"})
    graph.add_node(fact)
    graph.add_dependency(Dependency(id="synthetic-support", source_id=fact.id, target_id=sourced[0].id,
        dependency_type=DependencyType.SUPPORTS))
    payload = project_law_derived_dependency_graph(case_file, dependency_graph=graph, case_id="synthetic-case")
    assert payload["admitted_count"] == len(sourced)
    link = next(row for row in payload["factual_links"] if row.get("fact_text") == fact.name)
    assert link["authority_is_user_fact"] is False
    assert link["rewrites_legal_rule"] is False


@pytest.mark.parametrize("mode", ["unknown", "disputed"])
def test_unresolved_current_applicability_cannot_reuse_previously_admitted_nodes(tmp_path, monkeypatch, mode):
    _source, case_file, graph, _sourced = _actual(tmp_path, monkeypatch)
    case_file["legal_context_applicability"] = mode
    payload = project_law_derived_dependency_graph(case_file, dependency_graph=graph, case_id="synthetic-case")
    assert payload["admitted_count"] == 0
    assert payload["proof"] is False and payload["legal_sufficiency"] is False


def test_exceptions_are_reextracted_with_exact_source_spans_not_ledger_labels(tmp_path, monkeypatch):
    source = _source_record("synthetic-exception-rule", "notice")
    text = "An employer shall provide notice unless an emergency applies."
    source.update(content=text, source_text=text, source_hash=hashlib.sha256(text.encode()).hexdigest())
    _source, case, graph, _nodes = _actual(tmp_path, monkeypatch, source)
    result = project_law_derived_dependency_graph(case, dependency_graph=graph)
    assert result["admitted_count"] == 1
    rule = result["requirements"][0]
    assert rule["exceptions"] == ["unless an emergency applies."]
    for clause in rule["exception_source_spans"]:
        span = clause["span"]
        assert text.encode()[span["start"]:span["end"]].decode() == clause["text"]
    assert rule["exceptions_status"] == "source_clause_candidates"
    assert rule["burden"] == "" and rule["burden_status"] == "unavailable_from_source_owner"


def test_distinct_typed_requirements_from_one_document_are_not_deduplicated_by_hash(tmp_path, monkeypatch):
    source = _source_record("synthetic-two-clause-rule", "notice")
    text = "An employer shall provide written notice. An employer shall provide a hearing."
    source.update(content=text, source_text=text, source_hash=hashlib.sha256(text.encode()).hexdigest())
    _source, case, graph, nodes = _actual(tmp_path, monkeypatch, source)
    assert len(nodes) == 2
    result = project_law_derived_dependency_graph(case, dependency_graph=graph)
    assert len(result["requirements"]) == 2
    assert len({r["requirement_id"] for r in result["requirements"]}) == 2
    assert len({r["content_hash"] for r in result["requirements"]}) == 1


@pytest.mark.parametrize("activity", ["active", "retracted", "conflict", "superseded", "unknown"])
def test_real_assertion_proof_and_active_status_are_needed_for_factual_support(tmp_path, monkeypatch, activity):
    from integrations.ipfs_datasets.types import build_user_assertion_envelope

    _source, case, graph, nodes = _actual(tmp_path, monkeypatch)
    text = "Synthetic user reports written notice."
    envelope = build_user_assertion_envelope(source_text=text, source_kind="user_statement",
        message_id="synthetic-user-message", assertion_status="asserted", extractor_version="synthetic-gui27",
        source_span={"start": 0, "end": len(text.encode()), "text": text, "unit": "byte"})
    assert envelope.is_asserted_user_fact
    fact = DependencyNode(id="synthetic-assertion", node_type=NodeType.FACT, name=text,
        attributes={"activity_status": activity, "provenance": {"user_assertion": envelope.as_dict()}})
    graph.add_node(fact)
    graph.add_dependency(Dependency(id="synthetic-support", source_id=fact.id, target_id=nodes[0].id,
        dependency_type=DependencyType.SUPPORTS))
    result = project_law_derived_dependency_graph(case, dependency_graph=graph)
    link = next(row for row in result["factual_links"] if row.get("fact_text") == text)
    assert link["assertion_verified"] is True
    assert link["authority_is_user_fact"] is (activity == "active")
    assert link["effective_support"] is (activity == "active")
    assert link["fact_source_id"] == envelope.stable_id
    assert any(row["link_kind"] == "missing_evidence" for row in result["factual_links"]) is (activity != "active")


@pytest.mark.parametrize("damage", ["source_bytes", "source_hash", "authority_version", "source_unavailable", "support_ineligible", "context_revision"])
def test_stale_or_tampered_typed_source_proof_is_not_admitted(tmp_path, monkeypatch, damage):
    _source, case, graph, nodes = _actual(tmp_path, monkeypatch)
    node = nodes[0]
    if damage == "source_bytes":
        node.attributes["source_record"]["source_text"] = "Synthetic changed source text."
    elif damage == "source_hash":
        node.attributes["source_hash"] = "0" * 64
    elif damage == "authority_version":
        node.attributes["authority_version"] = "invented-version"
    elif damage == "source_unavailable":
        node.attributes["source_available"] = False
    elif damage == "support_ineligible":
        node.attributes["support_eligible"] = False
    else:
        node.attributes["context_revision"] = 999
    result = project_law_derived_dependency_graph(case, dependency_graph=graph)
    assert result["admitted_count"] == 0
    assert result["requirements"] == []


def test_actual_current_date_change_cannot_relabel_stale_source_proof(tmp_path, monkeypatch):
    from complaint_phases.intake_case_file import apply_explicit_legal_context

    _source, case, graph, _nodes = _actual(tmp_path, monkeypatch)
    apply_explicit_legal_context(case, applicable_law_date="2099-01-01")
    result = project_law_derived_dependency_graph(case, dependency_graph=graph)
    assert result["admitted_count"] == 0


def test_serialized_typed_dependency_snapshot_retains_real_claim_and_requirement_ids(tmp_path, monkeypatch):
    _source, case, graph, nodes = _actual(tmp_path, monkeypatch)
    case.pop("candidate_claims", None)
    raw = deepcopy(graph.to_dict())
    before = deepcopy(raw)
    result = project_law_derived_dependency_graph(case, dependency_graph=raw)
    assert {row["requirement_id"] for row in result["requirements"]} == {node.id for node in nodes}
    assert raw == before
