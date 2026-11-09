"""Factual invalidation must not promote retrieval nominations.

Synthetic private fixtures only. No test is skipped. Superseding or retracting
a fact drops dependent support and proof-cache references and reopens only the
inquiries bound to that fact. Retrieval confidence stays a candidate nomination
until the claim, requirement, and source span match exactly. Contradictions
stay visible and do not satisfy a legal requirement. Evidence may support an
allegation without rewriting the governing requirement text or source identity.
"""

from __future__ import annotations

import copy

import pytest

from complaint_phases.dependency_graph import (
    Dependency,
    DependencyGraph,
    DependencyGraphBuilder,
    DependencyNode,
    DependencyType,
    NodeType,
)
from complaint_phases.knowledge_graph import Entity, KnowledgeGraph, Relationship
from integrations.ipfs_datasets.types import build_user_assertion_envelope, source_byte_hash
from mediator.integrations.graph_tools import GraphRetrievalAugmentor


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _cases():
    return (
        {"label": "supersede-date", "action": "supersede", "original": "I was fired on January 1, 2020.", "replacement": "I was fired on January 2, 2020."},
        {"label": "retract-party", "action": "retract", "original": "Alex ended the warehouse job.", "replacement": "I withdraw the statement that Alex ended the warehouse job."},
        {"label": "supersede-place", "action": "supersede", "original": "The meeting was in the east office.", "replacement": "The meeting was in the west office."},
    )


def _context(text, message_id):
    return {
        "source_text": text,
        "source_kind": "user_statement",
        "source_id": message_id,
        "message_id": message_id,
        "assertion_status": "asserted",
        "extractor_version": "mgnd13-test",
        "source_hash": source_byte_hash(text),
        "source_span": {"start": 0, "end": len(text.encode("utf-8")), "text": text, "unit": "byte"},
        "subject_key": "employment-fact",
    }


def _fact(entity_id, text, message_id):
    envelope = build_user_assertion_envelope(**_context(text, message_id))
    assert envelope.is_asserted_user_fact
    entity = Entity(
        id=entity_id,
        type="fact",
        name=text,
        attributes={"description": text, "fact_type": "timeline"},
        confidence=0.4,
        source="complaint",
        provenance={"user_assertion": envelope.as_dict()},
    )
    return entity, envelope


def _span():
    text = "protected activity on March 1"
    return {"start": 0, "end": len(text.encode("utf-8")), "text": text, "unit": "byte"}


def _payload_item():
    span = _span()
    return {
        "title": "Title VII excerpt",
        "confidence": 0.93,
        "requirement_id": "req-protected",
        "source_span": span,
        "metadata": {"requirement_id": "req-protected", "source_span": span},
    }


def _graph_for(case):
    graph = KnowledgeGraph()
    fact, envelope = _fact("fact-old", case["original"], f"msg-{case['label']}")
    other, other_envelope = _fact("fact-other", "Riley wrote the schedule.", f"msg-other-{case['label']}")
    claim = Entity(
        id="claim-affected",
        type="claim",
        name="Termination",
        attributes={
            "claim_type": "employment",
            "satisfied_requirements": [fact.id, other.id],
            "proof_cache_identity": "kg-cache-affected",
            "proof_cache_entity_id": fact.id,
            "proof_cache": {"fact_id": fact.id, "satisfied": True, "reusable": True},
        },
        confidence=0.8,
    )
    unrelated = Entity(
        id="claim-unrelated",
        type="claim",
        name="Schedule",
        attributes={
            "claim_type": "employment",
            "satisfied_requirements": [other.id],
            "proof_cache_identity": "kg-cache-stable",
            "proof_cache_entity_id": other.id,
            "proof_cache": {"fact_id": other.id, "satisfied": True, "reusable": True},
        },
        confidence=0.8,
    )
    graph.add_entity(claim)
    graph.add_entity(unrelated)
    graph.add_entity(fact)
    graph.add_entity(other)
    graph.register_assertion(fact, envelope, status="active")
    graph.register_assertion(other, other_envelope, status="active")
    graph.add_relationship(Relationship(
        id="rel-support",
        source_id=fact.id,
        target_id=claim.id,
        relation_type="supports",
        attributes={"proof_cache": {"fact_id": fact.id, "satisfied": True, "reusable": True}, "proof_cache_identity": "rel-cache"},
        confidence=0.9,
    ))
    graph.add_relationship(Relationship(
        id="rel-other-support",
        source_id=other.id,
        target_id=unrelated.id,
        relation_type="supports",
        attributes={"proof_cache": {"fact_id": other.id, "satisfied": True, "reusable": True}, "proof_cache_identity": "rel-other"},
        confidence=0.9,
    ))
    graph.add_relationship(Relationship(
        id="rel-contradiction",
        source_id=fact.id,
        target_id=other.id,
        relation_type="contradicts",
        attributes={"proof_cache": {"fact_id": fact.id, "satisfied": True, "reusable": True}, "proof_cache_identity": "contradiction-cache"},
        confidence=1.0,
    ))
    graph.register_inquiry_target(
        inquiry_id=f"inq-{case['label']}",
        entity_id=fact.id,
        stable_id=envelope.stable_id,
        question="Which date should the complaint use?",
    )
    graph.register_inquiry_target(
        inquiry_id=f"inq-other-{case['label']}",
        entity_id=other.id,
        stable_id=other_envelope.stable_id,
        question="Who wrote the schedule?",
    )
    dependency = _dependency_graph(fact.id, other.id)
    graph._dependency_graph = dependency
    return graph, fact, envelope, other, dependency


def _dependency_graph(fact_id, other_id):
    graph = DependencyGraph()
    legal = DependencyNode(
        id="req-protected",
        node_type=NodeType.LEGAL_ELEMENT,
        name="Employer must not fire for protected activity",
        description="Statutory text stays fixed",
        satisfied=True,
        confidence=0.91,
        attributes={
            "rule_id": "rule-42",
            "authority_id": "auth-42",
            "source_hash": "source-hash-42",
            "source_span": {"start": 1, "end": 5, "text": "rule"},
            "provenance": {"source_id": "statute-1"},
            "dependency_class": "legally_sourced_requirement",
            "dependency_scope": {"fact_ids": [fact_id], "rule_id": "rule-42"},
            "proof_cache_identity": "dg-cache-affected",
            "proof_cache": {"fact_id": fact_id, "satisfied": True, "reusable": True},
            "satisfaction_state": "satisfied",
            "inquiry_targets": [
                {"inquiry_id": "inq-dg-affected", "fact_id": fact_id, "status": "open"},
                {"inquiry_id": "inq-dg-other", "fact_id": other_id, "status": "open"},
            ],
        },
    )
    stable = DependencyNode(
        id="req-stable",
        node_type=NodeType.LEGAL_ELEMENT,
        name="Unrelated notice rule",
        description="Unrelated source text",
        satisfied=True,
        confidence=0.4,
        attributes={
            "rule_id": "rule-stable",
            "authority_id": "auth-stable",
            "source_hash": "source-hash-stable",
            "provenance": {"source_id": "statute-stable"},
            "dependency_scope": {"fact_ids": [other_id], "rule_id": "rule-stable"},
            "proof_cache_identity": "dg-cache-stable",
            "proof_cache": {"fact_id": other_id, "satisfied": True, "reusable": True},
            "satisfaction_state": "satisfied",
        },
    )
    fact = DependencyNode(id=fact_id, node_type=NodeType.FACT, name="old fact", attributes={"epistemic_class": "assertion"})
    other = DependencyNode(id=other_id, node_type=NodeType.FACT, name="other fact", attributes={"epistemic_class": "assertion"})
    allegation = DependencyNode(
        id="allegation-1",
        node_type=NodeType.FACT,
        name="I was fired after I complained",
        attributes={"epistemic_class": "allegation"},
    )
    graph.add_node(legal)
    graph.add_node(stable)
    graph.add_node(fact)
    graph.add_node(other)
    graph.add_node(allegation)
    graph.add_dependency(Dependency(
        id="dep-support-old",
        source_id=fact_id,
        target_id=legal.id,
        dependency_type=DependencyType.SUPPORTS,
        required=False,
        strength=1.0,
    ))
    graph.add_dependency(Dependency(
        id="dep-support-other",
        source_id=other_id,
        target_id=stable.id,
        dependency_type=DependencyType.SUPPORTS,
        required=False,
        strength=1.0,
    ))
    return graph


def test_module_collects_meaningful_cases_without_required_skips():
    cases = _cases()
    assert cases
    assert len({item["label"] for item in cases}) == len(cases)
    assert all(item["original"].strip() and item["replacement"].strip() for item in cases)
    assert all(item["action"] in {"supersede", "retract"} for item in cases)


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["label"])
def test_revision_invalidates_only_dependent_support_and_reopens_target(case):
    graph, fact, envelope, other, dependency = _graph_for(case)
    replacement, replacement_envelope = _fact("fact-new", case["replacement"], f"msg-next-{case['label']}")
    before_ids = set(graph.entities)
    before_other_support = copy.deepcopy(graph.relationships["rel-other-support"].attributes)
    before_other_claim = copy.deepcopy(graph.entities["claim-unrelated"].attributes)
    before_stable = copy.deepcopy(dependency.nodes["req-stable"].attributes)
    stable_satisfied = dependency.nodes["req-stable"].satisfied
    if case["action"] == "supersede":
        graph.supersede_assertion(envelope.stable_id, replacement, replacement_envelope, event_id=f"event-{case['label']}")
    else:
        graph.retract_assertion(envelope.stable_id, replacement, replacement_envelope, event_id=f"event-{case['label']}")

    support = graph.relationships["rel-support"]
    assert support.attributes["activity_status"] == "invalidated"
    assert support.attributes["effective"] is False
    assert support.attributes["proof_cache"]["reusable"] is False
    assert support.attributes["proof_cache"]["satisfied"] is False
    assert graph.relationships["rel-other-support"].attributes == before_other_support
    assert graph.relationships["rel-other-support"].attributes.get("activity_status") != "invalidated"
    contradiction = graph.relationships["rel-contradiction"]
    assert contradiction.relation_type == "contradicts"
    assert contradiction.attributes.get("activity_status") != "invalidated"
    assert contradiction.attributes["proof_cache"]["reusable"] is False
    assert fact.id in graph.entities and other.id in graph.entities
    assert before_ids <= set(graph.entities)
    affected_claim = graph.entities["claim-affected"]
    assert fact.id not in affected_claim.attributes["satisfied_requirements"]
    assert other.id in affected_claim.attributes["satisfied_requirements"]
    assert affected_claim.attributes["proof_cache"]["reusable"] is False
    assert affected_claim.attributes["proof_cache_reusable"] is False
    assert graph.entities["claim-unrelated"].attributes["proof_cache"] == before_other_claim["proof_cache"]
    assert graph.entities["claim-unrelated"].attributes["proof_cache_identity"] == "kg-cache-stable"
    inquiries = {item["inquiry_id"]: item for item in graph.factual_ledger()["inquiry_targets"]}
    assert inquiries[f"inq-{case['label']}"]["status"] == "reopened"
    assert inquiries[f"inq-other-{case['label']}"]["status"] == "open"
    assert any(item["context"].get("inquiry_id") == f"inq-{case['label']}" for item in graph.factual_ledger()["reopened_questions"])
    assert not any(item["context"].get("inquiry_id") == f"inq-other-{case['label']}" for item in graph.factual_ledger()["reopened_questions"])

    legal = dependency.nodes["req-protected"]
    assert legal.id == "req-protected"
    assert legal.name == "Employer must not fire for protected activity"
    assert legal.description == "Statutory text stays fixed"
    assert legal.satisfied is False
    assert legal.attributes["rule_id"] == "rule-42"
    assert legal.attributes["authority_id"] == "auth-42"
    assert legal.attributes["source_hash"] == "source-hash-42"
    assert legal.attributes["provenance"] == {"source_id": "statute-1"}
    assert legal.attributes["proof_cache"]["reusable"] is False
    assert legal.attributes["rejected_proof_cache_identity"] == "dg-cache-affected"
    inquiries = {item["inquiry_id"]: item for item in legal.attributes["inquiry_targets"]}
    assert inquiries["inq-dg-affected"]["status"] == "reopened"
    assert inquiries["inq-dg-other"]["status"] == "open"
    assert dependency.nodes["req-stable"].satisfied is stable_satisfied
    assert dependency.nodes["req-stable"].attributes["proof_cache"] == before_stable["proof_cache"]
    assert dependency.nodes["req-stable"].id == "req-stable"
    assert any(item["dependency_id"] == "dep-support-old" for item in dependency.metadata["invalidated_support_refs"])
    assert not any(item["dependency_id"] == "dep-support-other" for item in dependency.metadata["invalidated_support_refs"])
    assert "dep-support-other" in dependency.dependencies
    assert dependency.nodes[fact.id].id == fact.id
    assert dependency.nodes[other.id].id == other.id


def test_retrieval_confidence_stays_a_nomination_until_exact_binding():
    augmentor = GraphRetrievalAugmentor()
    payloads = augmentor.build_evidence_payloads(
        legal_normalized=[_payload_item()],
        web_normalized=[{"title": "Public page", "confidence": 0.4, "metadata": {}}],
        claim_ids=["claim-affected", "claim-unrelated"],
        max_items=5,
    )
    assert len(payloads) == 2
    for payload in payloads:
        assert payload["support_status"] == "candidate_nomination"
        assert payload["binding_status"] == "unbound"
        assert payload["bound_support"] is False
        assert payload["satisfied_legal_requirement"] is False
        assert payload["confidence_role"] == "retrieval_candidate"
        assert payload["retrieval_confidence"] == payload["confidence"]
        assert payload["supports_claims"] == ["claim-affected", "claim-unrelated"]

    legal_payload = payloads[0]
    span = _span()
    mismatched = augmentor.recheck_support_binding(
        legal_payload,
        claim_id="claim-affected",
        requirement_id="req-protected",
        source_span={**span, "text": "a different sentence"},
    )
    assert mismatched["bound_support"] is False
    assert mismatched["support_status"] == "candidate_nomination"
    assert mismatched["satisfied_legal_requirement"] is False
    assert "source_span_not_exact" in mismatched["binding_reason"]
    assert legal_payload["bound_support"] is False

    wrong_claim = augmentor.recheck_support_binding(
        legal_payload,
        claim_id="claim-not-nominated",
        requirement_id="req-protected",
        source_span=span,
    )
    assert wrong_claim["bound_support"] is False
    assert "claim_not_nominated" in wrong_claim["binding_reason"]

    missing_requirement = augmentor.recheck_support_binding(
        payloads[1],
        claim_id="claim-affected",
        requirement_id="req-protected",
        source_span=span,
    )
    assert missing_requirement["bound_support"] is False
    assert missing_requirement["satisfied_support"] is False
    assert "requirement_not_exact" in missing_requirement["binding_reason"]

    bound = augmentor.recheck_support_binding(
        legal_payload,
        claim_id="claim-affected",
        requirement_id="req-protected",
        source_span=span,
    )
    assert bound["binding_status"] == "exact"
    assert bound["bound_support"] is True
    assert bound["supports_claims"] == ["claim-affected"]
    assert bound["bound_requirement_id"] == "req-protected"
    assert bound["bound_source_span"]["text"] == span["text"]
    assert bound["satisfied_legal_requirement"] is False
    assert bound["confidence_role"] == "retrieval_candidate"
    assert bound["retrieval_confidence"] == 0.93

    graph = _dependency_graph("fact-old", "fact-other")
    legal_before = copy.deepcopy(graph.nodes["req-protected"].to_dict())
    refused = DependencyGraphBuilder().apply_retrieval_nomination(graph, legal_payload)
    assert refused["admitted"] is False
    assert refused["bound_support"] is False
    assert refused["satisfied_legal_requirement"] is False
    assert graph.nodes["req-protected"].name == legal_before["name"]
    assert graph.nodes["req-protected"].satisfied is True

    admitted = DependencyGraphBuilder().apply_retrieval_nomination(
        graph,
        legal_payload,
        claim_id="claim-affected",
        requirement_id="req-protected",
        source_span=span,
        allegation_id="allegation-1",
    )
    assert admitted["admitted"] is True
    assert admitted["satisfied_legal_requirement"] is False
    legal = graph.nodes["req-protected"]
    assert legal.name == legal_before["name"]
    assert legal.description == legal_before["description"]
    assert legal.attributes["rule_id"] == "rule-42"
    assert legal.attributes["source_hash"] == "source-hash-42"
    assert legal.attributes["provenance"] == {"source_id": "statute-1"}
    assert legal.attributes["satisfied_by_retrieval"] is False
    assert graph.nodes["allegation-1"].attributes["evidence_support_refs"]
    unavailable = DependencyGraphBuilder().apply_retrieval_nomination(None, legal_payload)
    assert unavailable["admitted"] is False
    assert unavailable["reason"] == "dependency_graph_unavailable"
    assert unavailable["bound_support"] is False


def test_contradiction_stays_visible_and_evidence_does_not_rewrite_law():
    graph = _dependency_graph("fact-old", "fact-other")
    builder = DependencyGraphBuilder()
    evidence = DependencyNode(
        id="evidence-1",
        node_type=NodeType.EVIDENCE,
        name="Email to HR",
        description="I complained on March 1",
        satisfied=True,
        attributes={"source_id": "evidence-source-1"},
    )
    graph.add_node(evidence)
    legal_before = {
        "name": graph.nodes["req-protected"].name,
        "description": graph.nodes["req-protected"].description,
        "rule_id": graph.nodes["req-protected"].attributes["rule_id"],
        "source_hash": graph.nodes["req-protected"].attributes["source_hash"],
        "provenance": copy.deepcopy(graph.nodes["req-protected"].attributes["provenance"]),
        "id": graph.nodes["req-protected"].id,
    }
    supported = builder.support_factual_allegation(
        graph,
        evidence_id="evidence-1",
        allegation_id="allegation-1",
        legal_requirement_id="req-protected",
    )
    assert supported["supported"] is True
    allegation = graph.nodes["allegation-1"]
    assert allegation.attributes["epistemic_class"] == "allegation"
    assert "evidence-1" in allegation.attributes["evidence_support_refs"]
    assert graph.dependencies["supports:evidence-1:allegation-1"].target_id == "allegation-1"
    legal = graph.nodes["req-protected"]
    assert legal.id == legal_before["id"]
    assert legal.name == legal_before["name"]
    assert legal.description == legal_before["description"]
    assert legal.attributes["rule_id"] == legal_before["rule_id"]
    assert legal.attributes["source_hash"] == legal_before["source_hash"]
    assert legal.attributes["provenance"] == legal_before["provenance"]

    visible = builder.record_visible_contradiction(
        graph,
        left_fact_id="fact-old",
        right_fact_id="fact-other",
        legal_requirement_id="req-protected",
    )
    assert visible["visible"] is True
    assert visible["legal_requirement_satisfied"] is False
    assert graph.nodes["fact-old"].id == "fact-old"
    assert graph.nodes["fact-other"].id == "fact-other"
    assert graph.dependencies[visible["dependency_id"]].dependency_type == DependencyType.CONTRADICTS
    assert legal.satisfied is False
    assert legal.name == legal_before["name"]
    assert legal.attributes["source_hash"] == legal_before["source_hash"]
    assert legal.attributes["satisfied_by_contradiction"] is False

    missing = builder.support_factual_allegation(
        graph,
        evidence_id="missing-evidence",
        allegation_id="allegation-1",
        legal_requirement_id="req-protected",
    )
    assert missing["supported"] is False
    assert missing["reason"] == "endpoint_unavailable"
    assert legal.name == legal_before["name"]

    nomination = builder.add_evidence_to_graph(
        graph,
        {"name": "Retrieved snippet", "support_status": "candidate_nomination", "binding_status": "unbound", "confidence": 0.99, "attributes": {}},
        "req-protected",
    )
    nominated = graph.nodes[nomination]
    assert nominated.satisfied is False
    assert nominated.attributes["satisfied_legal_requirement"] is False
    assert not any(item.source_id == nomination for item in graph.dependencies.values())
