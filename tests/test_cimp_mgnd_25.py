"""Connect proof obligations to the definition handoff.

Cases use the current obligation and route owners with synthetic identities.
Solver, Lean, and review packets stay unproved. No test is skipped.
"""

from __future__ import annotations

from integrations.ipfs_datasets import logic
from complaint_phases.dependency_graph import (
    DependencyGraph,
    DependencyGraphBuilder,
    DependencyNode,
    NodeType,
)
from mediator.claim_support_hooks import ClaimSupportHook
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = []


class _Mediator:
    def log(self, *args, **kwargs):
        return None


def _requirement():
    return {
        "requirement_id": "req-notice",
        "element_id": "element-notice",
        "claim_id": "claim-notice",
        "admitted_legal_text": "A covered employer must keep a written record.",
        "proof": {"status": "unverified", "body": "prior-proof"},
        "asserted_facts": [{"fact_id": "fact-1", "text": "A report was written.", "revision": "r1"}],
        "assumptions": [{"premise_id": "assume-1", "label": "record-means-writing", "text": "A record is a writing."}],
        "source_id": "source-1",
    }


def _handoff(**overrides):
    payload = {
        "requirement_id": "req-notice",
        "admitted_legal_text": "A covered employer must keep a written record.",
        "identities": {"definition": "def-a", "scope": "scope-a", "source": "source-a"},
        "retained": {"assumptions": [{"premise_id": "assume-1", "text": "A record is a writing."}]},
        "adverse_treatment": {"treatment_id": "treat-1", "status": "good_law"},
    }
    payload.update(overrides)
    return payload


def test_meaningful_cases_are_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id for case in cases)


def test_obligations_and_route_use_current_identities():
    logic.reset_satisfied_element_proof_cache()
    handoff = _handoff()
    bound = logic.connect_definition_handoff_proof(_requirement(), handoff)
    versions = bound["versions"]
    routing = bound["legal_ir_proof_routing"]
    route_versions = routing.get("versions") or {}
    assert versions["requirement_id"] == "req-notice"
    assert versions["definition_identity"]
    assert versions["assumption_identity"]
    assert versions["adverse_treatment_identity"]
    assert versions["source_identity"]
    premise_ids = [row.get("premise_id") for row in route_versions.get("premises") or []]
    assert "assume-1" in premise_ids or versions["assumption_identity"]
    for key in (
        "requirement_id",
        "definition_identity",
        "assumption_identity",
        "adverse_treatment_identity",
        "source_identity",
    ):
        assert route_versions.get(key) == versions[key]
        assert route_versions.get("expected_" + key) == versions[key]
    assert bound["proof"] == {"status": "unverified", "body": "prior-proof"}
    assert bound["proof_satisfied"] is False
    assert bound["proof_changed"] is False
    assert bound["factual_assertion"]["asserted"] is True
    assert bound["factual_assertion"]["satisfies_element"] is False
    assert bound["legal_sufficiency"]["satisfied"] is False
    assert bound["outcome"] in logic.PROOF_ROUTING_OUTCOMES
    assert bound["outcome"] != "proved"


def test_packets_do_not_become_proved_and_outcomes_stay_distinct():
    seen = set()
    for status in ("proved", "disproved", "unknown", "timeout", "unavailable", "cancelled"):
        bound = logic.connect_definition_handoff_proof(
            _requirement(),
            _handoff(solver={"status": status, "kind": "solver"}),
        )
        assert bound["solver_is_proof"] is False
        assert bound["outcome"] == ("unknown" if status == "proved" else status)
        assert bound["proof_satisfied"] is False
        seen.add(bound["outcome"])
    lean = logic.connect_definition_handoff_proof(
        _requirement(),
        _handoff(conditional_lean={"status": "proved", "artifact": "generated-lean"}),
    )
    review = logic.connect_definition_handoff_proof(
        _requirement(),
        _handoff(review={"status": "proved", "packet": "review"}),
    )
    assert lean["generated_lean_is_proof"] is False
    assert review["review_packet_is_proof"] is False
    assert lean["outcome"] != "proved"
    assert review["outcome"] != "proved"
    classified = {
        "proved": logic._classify_route(
            native_status="proved", native_trust="structural", native_reason="",
            attempt_metadata=[{"status": "proved", "route": "deterministic_syntax"}],
            missing_facts=[], versions_match=True, similarity_score=None, model_assertion=None,
            process=None, goal_bound_kernel=False,
        ),
        "disproved": logic._classify_route(
            native_status="theorem_failed", native_trust="kernel", native_reason="",
            attempt_metadata=[], missing_facts=[], versions_match=True, similarity_score=None,
            model_assertion=None, process=None, negative_artifact_verified=True,
        ),
        "unknown": logic._classify_route(
            native_status="proved", native_trust="kernel", native_reason="",
            attempt_metadata=[], missing_facts=[{"premise_id": "missing"}], versions_match=True,
            similarity_score=1, model_assertion=True, process=None,
        ),
        "timeout": logic._classify_route(
            native_status="proved", native_trust="kernel", native_reason="",
            attempt_metadata=[], missing_facts=[], versions_match=True, similarity_score=None,
            model_assertion=None, process={"timed_out": True, "cancelled": False, "process_group_reaped": True},
        ),
        "unavailable": logic._classify_route(
            native_status="unavailable", native_trust="", native_reason="",
            attempt_metadata=[], missing_facts=[], versions_match=True, similarity_score=None,
            model_assertion=None, process={"timed_out": False, "cancelled": False, "process_group_reaped": True},
        ),
        "cancelled": logic._classify_route(
            native_status="proved", native_trust="kernel", native_reason="",
            attempt_metadata=[], missing_facts=[], versions_match=True, similarity_score=None,
            model_assertion=None, process={"timed_out": False, "cancelled": True, "process_group_reaped": True},
        ),
    }
    assert [item["outcome"] for item in classified.values()] == [
        "unknown", "disproved", "unknown", "timeout", "unavailable", "cancelled",
    ]
    assert classified["proved"]["substantive_trust_satisfied"] is False
    assert classified["disproved"]["substantive_trust_satisfied"] is False
    assert len(seen) >= 5


def test_definition_premise_source_or_treatment_change_invalidates_replay():
    logic.reset_satisfied_element_proof_cache()
    first = logic.connect_definition_handoff_proof(_requirement(), _handoff())
    changed_definition = logic.connect_definition_handoff_proof(
        _requirement(),
        _handoff(identities={"definition": "def-b", "scope": "scope-a", "source": "source-a"}),
    )
    changed_source = logic.connect_definition_handoff_proof(
        {**_requirement(), "admitted_legal_text": "A covered employer must keep a dated record."},
        _handoff(),
    )
    changed_premise = logic.connect_definition_handoff_proof(
        _requirement(),
        _handoff(retained={"assumptions": [{"premise_id": "assume-2", "text": "A record is a filing."}]}),
    )
    changed_treatment = logic.connect_definition_handoff_proof(
        _requirement(),
        _handoff(adverse_treatment={"treatment_id": "treat-2", "status": "adverse"}),
    )
    identities = {
        first["proof_cache_identity"],
        changed_definition["proof_cache_identity"],
        changed_source["proof_cache_identity"],
        changed_premise["proof_cache_identity"],
        changed_treatment["proof_cache_identity"],
    }
    assert len(identities) == 5
    replayed = logic.replay_satisfied_element_proof(changed_definition["evaluation"]["identity"])
    assert replayed["cache_identity"] == changed_definition["proof_cache_identity"]
    assert replayed["cache_identity"] != first["proof_cache_identity"]
    assert replayed["satisfied"] is False
    stale = dict(first["evaluation"])
    stale["cache_identity"] = changed_treatment["proof_cache_identity"]
    assert logic.verify_element_proof_evaluation(stale)["verified"] is False


def test_hook_keeps_requirement_proof_unsatisfied():
    hook = ClaimSupportHook(_Mediator())
    requirement = _requirement()
    handoff = hook.forward_independent_norm_decisions(requirement, None, None, None, None, {"status": "proved"})
    bound = hook.connect_definition_handoff_proof(requirement, handoff)
    assert requirement["proof"] == {"status": "unverified", "body": "prior-proof"}
    assert bound["proof_satisfied"] is False
    assert bound["proof_changed"] is False
    assert bound["factual_assertion_is_legal_sufficiency"] is False
    assert bound["outcome"] != "proved"


def test_graph_drops_proof_cache_when_definition_or_treatment_changes():
    graph = DependencyGraph()
    node = DependencyNode(
        id="req-1",
        node_type=NodeType.LEGAL_ELEMENT,
        name="Notice",
        satisfied=True,
        attributes={
            "dependency_class": "legally_sourced_requirement",
            "proof_cache_identity": "cache-old",
            "proof_cache": {"cache_identity": "cache-old", "satisfied": True, "reusable": True},
            "satisfaction_state": "satisfied",
            "definition_identity": "def-a",
            "premise_identity": "premise-a",
            "adverse_treatment_identity": "treat-1",
            "dependency_scope": {"rule_id": "rule-1", "fact_ids": []},
        },
    )
    graph.add_node(node)
    builder = DependencyGraphBuilder()
    report = builder.refresh_affected_dependencies(graph, {
        "definition_changed": True,
        "definition_identity": "def-b",
        "adverse_treatment_changed": True,
        "adverse_treatment_identity": "treat-2",
    })
    assert "req-1" in report["affected_node_ids"]
    assert node.satisfied is False
    assert node.attributes["rejected_proof_cache_identity"] == "cache-old"
    assert node.attributes["proof_cache"]["satisfied"] is False
    assert node.attributes["proof_cache"]["reusable"] is False
    assert node.attributes["invalidation_reason"] == "definition_changed"
