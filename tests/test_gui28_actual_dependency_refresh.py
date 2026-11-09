"""Actual typed graph effects and bound operation replay, synthetic sources only."""
from copy import deepcopy

import pytest

from tests.test_authority_dependency_pipeline import _source_record, _sourced_nodes
from tests.test_authority_dependency_public_pipeline import _start

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _actual(tmp_path, monkeypatch):
    source = _source_record("synthetic-refresh-rule", "notice")
    mediator, graph = _start(monkeypatch, tmp_path, [source])
    nodes = [n for n in _sourced_nodes(graph) if n.attributes.get("source_available")]
    assert nodes
    nodes[0].satisfied = True
    nodes[0].attributes["satisfaction_state"] = "satisfied"
    # Seed a historical cache identity whose prior satisfaction must be retired;
    # this is not an issued positive proof evaluation.
    nodes[0].attributes["proof_cache_identity"] = "synthetic-stale-cache"
    nodes[0].attributes["proof_cache"] = {"satisfied": True, "reusable": True}
    return mediator, graph, nodes[0], source


def _request(source, **extra):
    values = dict(case_id="synthetic-case", actor_principal_id="source-fixture-owner",
        correction_kind="context", case_revision=1, consent_generation=1, consent_revoked=False,
        grant_revision=0, granted_actions={"case.update"}, legal_source_hashes=[source["source_hash"]],
        operation_id="synthetic-refresh-operation", expected_case_revision=1,
        expected_consent_generation=1, expected_grant_revision=0, expected_dependency_generation=0)
    values.update(extra)
    return values


def test_refresh_claims_graph_mutation_only_after_actual_owner_invalidates_real_support(tmp_path, monkeypatch):
    mediator, graph, node, source = _actual(tmp_path, monkeypatch)
    before = deepcopy(graph.to_dict())
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source))
    assert result["graph_mutated"] is True
    assert graph.to_dict() != before
    assert node.satisfied is False
    assert node.attributes["proof_cache"]["satisfied"] is False
    assert result["dependency_refresh"]["source_admission_reread"] is True


def test_same_operation_id_with_changed_payload_is_not_successful_replay(tmp_path, monkeypatch):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    first = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source))
    assert first["applied"] is True
    before = deepcopy(graph.to_dict())
    changed = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source, correction_kind="factual"))
    assert changed["status"] == "refused"
    assert changed["error"]["code"] == "operation_conflict"
    assert graph.to_dict() == before


def test_caller_rows_cannot_install_links_questions_or_proof_obligations(tmp_path, monkeypatch):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    before = deepcopy(graph.to_dict())
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source,
        successors={"proof_obligations": [{"id": "invented-proof", "text": "Client declares proof complete.",
            "content_hash": source["source_hash"]}]}))
    assert result["status"] == "refused"
    assert result["applied"] is False and result["graph_mutated"] is False
    assert graph.to_dict() == before


def test_exact_replay_retains_generation_and_graph_bytes(tmp_path, monkeypatch):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    first = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source))
    assert first["applied"] is True
    before = deepcopy(graph.to_dict())
    case_before = deepcopy(mediator.workflow_actions._refresh_case_file())
    replay = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source))
    assert replay["replayed"] is True and replay["applied"] is False
    assert replay["graph_mutated"] is False
    assert replay["dependency_generation"] == first["dependency_generation"] == 1
    assert graph.to_dict() == before and mediator.workflow_actions._refresh_case_file() == case_before


@pytest.mark.parametrize("changed,code", [
    ({"expected_case_revision": 0}, "stale_case_revision"),
    ({"consent_revoked": True}, "consent_revoked"),
    ({"expected_consent_generation": 0}, "stale_consent"),
    ({"expected_grant_revision": 1}, "stale_actor_grant"),
    ({"expected_dependency_generation": 1}, "stale_dependency_generation"),
    ({"granted_actions": {"case.read"}}, "actor_not_permitted"),
    ({"case_revision": True}, "refresh_field"),
    ({"legal_source_hashes": ["hash-current"]}, "stale_legal_source_hash"),
])
def test_stale_or_ungranted_refresh_does_not_change_actual_graph(tmp_path, monkeypatch, changed, code):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    before = deepcopy(graph.to_dict())
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source, **changed))
    assert result["status"] == "refused" and result["error"]["code"] == code
    assert result["graph_mutated"] is False and graph.to_dict() == before


def test_late_revalidation_joins_persisted_actual_refresh_without_installing_rows(tmp_path, monkeypatch):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source))
    assert result["applied"] is True
    before = deepcopy(graph.to_dict())
    values = _request(source)
    late = {key: values[key] for key in ("case_id", "actor_principal_id", "case_revision", "consent_generation",
            "consent_revoked", "grant_revision", "granted_actions", "legal_source_hashes")}
    late.update(operation_id="synthetic-late-check", dependency_generation=1,
                claimed={"refresh_operation_id": values["operation_id"]})
    checked = mediator.workflow_actions.accept_legal_refresh_late_result(**late)
    assert checked["status"] == "verified_current" and checked["server_refresh_verified"] is True
    assert checked["applied"] is False and checked["client_result_installed"] is False
    assert graph.to_dict() == before
    late["claimed"]["proof_obligations"] = [{"id": "caller-claims-proof"}]
    denied = mediator.workflow_actions.accept_legal_refresh_late_result(**late)
    assert denied["status"] == "refused"
    assert denied["error"]["code"] == "late_result_capability_unavailable"
    assert graph.to_dict() == before


def test_current_fact_or_source_change_invalidates_replay_and_late_check(tmp_path, monkeypatch):
    from complaint_phases.phase_manager import ComplaintPhase
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source))
    assert result["applied"] is True
    case = mediator.workflow_actions._refresh_case_file()
    case["new_factual_answer"] = "A new synthetic answer entered by the real case owner."
    changed_before = deepcopy(graph.to_dict())
    replay = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source))
    assert replay["error"]["code"] == "stale_operation_scope" and replay["applied"] is False
    assert graph.to_dict() == changed_before


def test_explicit_manifest_scope_excludes_real_orphan_database_authority(tmp_path):
    from complaint_phases.phase_manager import ComplaintPhase
    from tests.test_authority_dependency_public_pipeline import _workflow
    from tests.test_authority_dependency_pipeline import _CONTEXT
    mediator = _workflow(tmp_path)
    current = _source_record("manifest-current", "notice")
    orphan = _source_record("orphan-after-denied-case-CAS", "hearing")
    def store(record):
        return mediator.legal_authority_storage.add_authority({
            "type": "statute", "source": "synthetic-owned-corpus", "title": record["citation"],
            "citation": record["citation"], "content": record["source_text"], "jurisdiction": "OR",
            "metadata": {k: v for k, v in record.items() if k not in {"id", "content", "claim_type"}},
        }, "source-fixture-owner", claim_type="employment_discrimination")
    assert store(current) > 0
    mediator.start_three_phase_process("My employer discriminated against me." + _CONTEXT)
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    assert store(orphan) > 0
    assert len(mediator.get_legal_authorities(claim_type="employment_discrimination")) == 2
    # This list represents only records joined to the current encrypted case
    # manifest; the uncommitted source-owner DB row remains present.
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(current),
        canonical_source_records=[current])
    assert result["applied"] is True
    admitted = {n.attributes.get("source_hash") for n in _sourced_nodes(graph)
                if n.attributes.get("source_available") is True}
    assert admitted == {current["source_hash"]} and orphan["source_hash"] not in admitted
    assert len(mediator.get_legal_authorities(claim_type="employment_discrimination")) == 2


def test_empty_manifest_scope_never_falls_back_to_present_database_rows(tmp_path, monkeypatch):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source, legal_source_hashes=[]),
        canonical_source_records=[])
    assert result["applied"] is True
    assert not [n for n in _sourced_nodes(graph) if n.attributes.get("source_available") is True]
    assert result["proof"] is False and result["legal_sufficiency"] is False


@pytest.mark.parametrize("applicability", ["unknown", "disputed"])
def test_unknown_context_retains_manifest_custody_without_admitting_governing_law(tmp_path, monkeypatch, applicability):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    case = mediator.workflow_actions._refresh_case_file()
    case["legal_context_applicability"] = applicability
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source),
        canonical_source_records=[source])
    assert result["applied"] is True
    assert result["legal_source_hashes"] == [source["source_hash"]]
    assert result["admitted_source_hashes"] == []
    assert not [n for n in _sourced_nodes(graph) if n.attributes.get("source_available") is True
                and n.attributes.get("support_eligible") is not False]
    assert result["proof"] is False and result["legal_sufficiency"] is False


@pytest.mark.parametrize("field,value", [("source_text", "Different owned bytes."),
    ("source_hash", "0" * 64), ("content", "Different alias bytes.")])
def test_manifest_source_bytes_must_match_current_owned_hash(tmp_path, monkeypatch, field, value):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    bad = dict(source, **{field: value})
    before = deepcopy(graph.to_dict())
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source),
        canonical_source_records=[bad])
    assert result["status"] == "refused" and result["error"]["code"] == "canonical_source_scope_invalid"
    assert graph.to_dict() == before


def test_same_manifest_hash_with_changed_treatment_is_not_replayed_as_old_success(tmp_path, monkeypatch):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    first = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source),
        canonical_source_records=[source])
    assert first["applied"] is True
    changed = dict(source, authority_treatment_edges=[{"relation_type": "adverse", "target_authority_id": source["authority_id"]}])
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source),
        canonical_source_records=[changed])
    assert result["status"] == "refused" and result["error"]["code"] == "operation_conflict"


def test_real_factual_nodes_and_knowledge_graph_are_preserved_by_refresh(tmp_path, monkeypatch):
    from complaint_phases.phase_manager import ComplaintPhase
    from tests.test_authority_dependency_pipeline import _factual_nodes
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    kg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    before_kg = deepcopy(kg.to_dict())
    before_facts = {node.id: deepcopy(node.__dict__) for node in _factual_nodes(graph)}
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source),
        canonical_source_records=[source])
    assert result["applied"] is True
    assert kg.to_dict() == before_kg
    assert {node.id: node.__dict__ for node in _factual_nodes(graph)} == before_facts


def _prepared_owned_source():
    from integrations.ipfs_datasets.logic import prepare_acquired_authority_record
    source = _source_record("prepared-current-source", "notice")
    prepared = prepare_acquired_authority_record({
        "source_text": source["source_text"], "locator": "urn:synthetic:owned-notice",
        "locator_kind": "owned-local", "version": "2024-edition",
        "source_family": "statute", "law_query_date": "2024-06-01",
        "retrieval": {"effective_date": "2024-01-01"},
    }, jurisdiction="OR", as_of_date="2024-06-01")
    assert prepared["status"] == "admitted"
    record = prepared["record"]
    assert "source_hash" not in record and record["metadata"]["source_hash"] == source["source_hash"]
    return record, source


def test_actual_prepared_record_metadata_shape_refreshes_only_authenticated_claim_scope(tmp_path, monkeypatch):
    mediator, graph, _node, _source = _actual(tmp_path, monkeypatch)
    record, source = _prepared_owned_source()
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source),
        canonical_source_records={"employment_discrimination": [record]})
    assert result["applied"] is True
    assert result["admitted_source_hashes"] == [source["source_hash"]]
    assert any(n.attributes.get("authority_id") == "urn:synthetic:owned-notice"
               and n.attributes.get("source_available") is True for n in _sourced_nodes(graph))


@pytest.mark.parametrize("scope_kind", ["wrong_claim", "unassociated_flat"])
def test_manifest_custody_cannot_assign_a_prepared_record_to_an_unreviewed_claim(tmp_path, monkeypatch, scope_kind):
    mediator, graph, _node, _source = _actual(tmp_path, monkeypatch)
    record, source = _prepared_owned_source()
    scope = {"defamation": [record]} if scope_kind == "wrong_claim" else [record]
    result = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source), canonical_source_records=scope)
    assert result["applied"] is True
    assert result["admitted_source_hashes"] == []
    assert not [n for n in _sourced_nodes(graph) if n.attributes.get("source_available") is True]


def test_late_result_rejects_a_changed_provided_source_expectation(tmp_path, monkeypatch):
    mediator, graph, _node, source = _actual(tmp_path, monkeypatch)
    first = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source))
    assert first["applied"] is True
    values = _request(source)
    late = {key: values[key] for key in ("case_id", "actor_principal_id", "case_revision", "consent_generation",
            "consent_revoked", "grant_revision", "granted_actions", "legal_source_hashes")}
    late.update(operation_id="late-wrong-source", dependency_generation=1,
                claimed={"refresh_operation_id": values["operation_id"], "legal_source_hashes": ["0" * 64]})
    result = mediator.workflow_actions.accept_legal_refresh_late_result(**late)
    assert result["status"] == "refused" and result["error"]["code"] == "stale_legal_source_hash"


def test_export_restore_preserves_actual_refresh_and_exact_idempotent_replay(tmp_path, monkeypatch):
    from tests.test_authority_dependency_pipeline import _CONTEXT, _local_sources
    from tests.test_authority_dependency_public_pipeline import _workflow
    source = _source_record("cold-case-source", "notice")
    mediator = _workflow(tmp_path / "first")
    _local_sources(monkeypatch, mediator, [source])
    started = mediator.workflow_actions.transition_interview(action="start",
        narrative="My employer discriminated against me." + _CONTEXT,
        user_id="source-fixture-owner", case_id="synthetic-case")
    assert not started.get("error")
    first = mediator.workflow_actions.refresh_legal_dependency_graph(**_request(source),
        canonical_source_records={"employment_discrimination": [source]})
    assert first["applied"] is True
    projection = deepcopy(mediator.workflow_actions.export_session_projection())
    assert projection and projection["intake_case_file"]["legal_graph_refresh"]["dependency_generation"] == 1
    fresh = _workflow(tmp_path / "cold")
    restored = fresh.workflow_actions.restore_session_projection(deepcopy(projection))
    assert not restored.get("error")
    before = deepcopy(fresh.workflow_actions.export_session_projection())
    replay = fresh.workflow_actions.refresh_legal_dependency_graph(**_request(source),
        canonical_source_records={"employment_discrimination": [source]})
    assert replay["replayed"] is True and replay["applied"] is False
    assert replay["dependency_generation"] == 1 and replay["graph_mutated"] is False
    assert fresh.workflow_actions.export_session_projection() == before
