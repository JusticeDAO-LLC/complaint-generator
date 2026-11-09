"""Contract: factual, authority, rule, requirement, and support-link namespaces stay distinct."""

import pytest

from complaint_phases.dependency_graph import DependencyGraph, DependencyGraphBuilder
from complaint_phases.knowledge_graph import KnowledgeGraphBuilder
from complaint_phases.legal_graph import LegalGraphBuilder
from integrations.ipfs_datasets.graphs import (
    DISTINCT_GRAPH_RECORD_KINDS,
    build_namespaced_support_link,
    extract_graph_from_text,
    mint_graph_record_id,
    record_kind_from_id,
    resolve_duplicate_entities,
)


def test_record_kinds_use_distinct_id_prefixes():
    ids = [
        mint_graph_record_id(kind, "same-label", "same-source")
        for kind in DISTINCT_GRAPH_RECORD_KINDS
    ]
    prefixes = [record_kind_from_id(record_id) for record_id in ids]
    assert prefixes == list(DISTINCT_GRAPH_RECORD_KINDS)
    assert len(set(ids)) == len(ids)
    assert len(set(prefixes)) == len(prefixes)


def test_legal_passage_is_not_a_complainant_fact():
    passage = "The employer shall not discharge an employee for opposing an unlawful practice."
    provenance = {"source_id": "statute-42-usc-2000e", "source_type": "statute", "citation": "42 USC 2000e-3"}
    extracted = extract_graph_from_text(
        passage,
        source_id="statute-42-usc-2000e",
        metadata={"source_kind": "law", "passage_role": "authority_source", "provenance": provenance, "legal_passage": True},
    )
    kinds = {entity["type"] for entity in extracted["entities"]}
    assert "fact" not in kinds
    assert "factual_assertion" not in kinds
    legal_nodes = [entity for entity in extracted["entities"] if entity["type"] == "authority_source"]
    assert legal_nodes
    assert all(entity["attributes"]["about_complainant"] is False for entity in legal_nodes)
    assert all(entity["attributes"]["provenance"]["source_id"] == "statute-42-usc-2000e" for entity in legal_nodes)

    projected = LegalGraphBuilder().project_legal_passage({
        "text": passage,
        "passage_role": "authority_source",
        "provenance": provenance,
    })
    assert projected.element_type == "authority_source"
    assert projected.id.startswith("authority_source:")
    assert projected.attributes["about_complainant"] is False
    assert projected.attributes["provenance"]["citation"] == "42 USC 2000e-3"

    graph = KnowledgeGraphBuilder().build_from_text(
        passage,
        source_context={"source_kind": "law", "source_id": "statute-42-usc-2000e", "legal_passage": True},
        extracted_entities=[{"name": passage, "type": "fact", "attributes": {"description": passage}}],
    )
    assert graph.entities
    for entity in graph.entities.values():
        assert entity.type == "legal_text"
        assert entity.source == "legal"
        assert entity.id.startswith("authority_source:")
        assert entity.attributes["about_complainant"] is False
        envelope = entity.provenance["user_assertion"]
        assert envelope["assertion_status"] != "asserted"
        assert envelope["record_type"] == "legal_text"


def test_entity_dedup_does_not_merge_testimony_with_legal_norm():
    entities = [
        {"entity_id": "e-user", "name": "Equal Protection", "source_kind": "testimony"},
        {"entity_id": "e-law", "name": "equal protection", "source_kind": "law", "record_kind": "legal_requirement"},
        {"entity_id": "e-doc", "name": "Equal Protection", "source_kind": "document"},
    ]
    result = resolve_duplicate_entities(entities)
    assert result["entity_count"] == 2
    assert result["merged_count"] == 1
    by_namespace = {cluster["resolution_namespace"]: cluster for cluster in result["clusters"]}
    assert "e-law" in by_namespace["legal_norm"]["entity_ids"]
    assert "e-user" in by_namespace["user_testimony"]["entity_ids"]
    assert "e-doc" in by_namespace["user_testimony"]["entity_ids"]
    assert "e-law" not in by_namespace["user_testimony"]["entity_ids"]


def test_support_and_contradiction_links_keep_both_provenance_chains():
    fact_id = mint_graph_record_id("factual_assertion", "user-said-fired")
    rule_id = mint_graph_record_id("rule_candidate", "anti-retaliation")
    fact_provenance = {"source_id": "msg-1", "source_kind": "testimony", "span": "I was fired"}
    rule_provenance = {"source_id": "statute-42-usc-2000e", "source_kind": "law", "citation": "42 USC 2000e-3"}

    support = build_namespaced_support_link(
        factual_assertion_id=fact_id,
        rule_id=rule_id,
        relation="supports",
        factual_provenance=fact_provenance,
        rule_provenance=rule_provenance,
    )
    contradiction = build_namespaced_support_link(
        factual_assertion_id=fact_id,
        rule_id=rule_id,
        relation="contradicts",
        factual_provenance=fact_provenance,
        rule_provenance=rule_provenance,
    )
    assert support["link_type"] == "support_link"
    assert contradiction["link_type"] == "contradiction_link"
    assert support["link_id"] != contradiction["link_id"]
    assert support["factual_assertion_id"] == fact_id
    assert support["rule_id"] == rule_id
    assert record_kind_from_id(support["link_id"]) == "support_link"
    assert support["provenance_chains"]["factual_assertion"] == fact_provenance
    assert support["provenance_chains"]["rule"] == rule_provenance
    assert support["provenance_chains"]["factual_assertion"] is not support["provenance_chains"]["rule"]

    graph = DependencyGraph()
    stored = DependencyGraphBuilder().add_fact_rule_link(
        graph,
        factual_assertion_id=fact_id,
        rule_id=rule_id,
        relation="contradicts",
        factual_provenance=fact_provenance,
        rule_provenance=rule_provenance,
    )
    assert stored["link_id"] in graph.dependencies
    assert graph.dependencies[stored["link_id"]].source_id == fact_id
    assert graph.dependencies[stored["link_id"]].target_id == rule_id
    assert graph.nodes[fact_id].attributes["provenance"]["source_kind"] == "testimony"
    assert graph.nodes[rule_id].attributes["provenance"]["source_kind"] == "law"
    assert graph.metadata["cross_graph_links"][0]["provenance_chains"]["factual_assertion"]["span"] == "I was fired"
    assert graph.metadata["cross_graph_links"][0]["provenance_chains"]["rule"]["citation"] == "42 USC 2000e-3"


def test_legal_builder_namespaces_authority_rule_and_requirement():
    builder = LegalGraphBuilder()
    graph = builder.build_from_authorities(
        [{
            "authority_id": "auth-1",
            "name": "Title VII retaliation",
            "citation": "42 USC 2000e-3",
            "provenance": {"source_id": "auth-1"},
            "rule_candidates": [{
                "rule_text": "An employer may not retaliate against an employee for opposing an unlawful practice.",
                "rule_type": "prohibition",
                "claim_element_id": "element-1",
                "provenance": {"source_id": "rule-span-1"},
            }],
        }],
        claim_elements=[{"element_id": "element-1", "element_text": "retaliation"}],
    )
    kinds = {element.element_type for element in graph.elements.values()}
    assert "authority_source" in kinds
    assert "rule_candidate" in kinds
    authority = next(element for element in graph.elements.values() if element.element_type == "authority_source")
    rule = next(element for element in graph.elements.values() if element.element_type == "rule_candidate")
    assert authority.id.startswith("authority_source:")
    assert rule.id.startswith("rule_candidate:")
    assert authority.id != rule.id
    assert authority.attributes["provenance"]["source_id"] == "auth-1"
    assert rule.attributes["provenance"]["source_id"] == "rule-span-1"

    statute_graph = builder.build_from_statutes(
        [{"name": "Title VII", "citation": "42 USC 2000e", "description": "discrimination"}],
        ["discrimination"],
    )
    requirements = statute_graph.get_elements_by_type("legal_requirement")
    assert requirements
    assert all(element.id.startswith("legal_requirement:") for element in requirements)
    assert all(element.attributes["about_complainant"] is False for element in requirements)

    dependency = DependencyGraphBuilder().build_from_claims(
        [{"name": "Retaliation", "type": "retaliation", "description": "I was fired"}],
        {"retaliation": [{"name": "Protected opposition", "description": "Employee opposed an unlawful practice", "provenance": {"source_id": "req-1"}}]},
    )
    legal_nodes = [node for node in dependency.nodes.values() if node.attributes.get("record_kind") == "legal_requirement"]
    assert legal_nodes
    assert all(node.id.startswith("legal_requirement:") for node in legal_nodes)
    assert legal_nodes[0].attributes["provenance"]["source_id"] == "req-1"


def test_colliding_legacy_entity_ids_do_not_drop_a_domain():
    result = resolve_duplicate_entities([
        {"entity_id": "shared", "name": "Equal protection", "source_kind": "testimony"},
        {"entity_id": "shared", "name": "Equal protection", "source_kind": "law", "record_kind": "legal_requirement"},
    ])
    assert result["entity_count"] == 2
    assert len(result["entity_map"]) == 2
    assert {c["resolution_namespace"] for c in result["entity_map"].values()} == {"user_testimony", "legal_norm"}


def test_nested_legal_provenance_cannot_merge_into_testimony():
    result = resolve_duplicate_entities([
        {"entity_id": "user", "name": "Equal protection", "source_kind": "testimony"},
        {"entity_id": "law", "name": "Equal protection", "attributes": {"provenance": {"source_type": "statute"}}},
    ])
    assert result["entity_count"] == 2


def test_nested_legal_passage_provenance_is_not_a_complainant_fact():
    result = extract_graph_from_text("A landlord shall provide reasonable accommodation.",
        source_id="synthetic-statute", metadata={"provenance": {"source_type": "statute", "source_id": "synthetic-statute"}})
    passages = [e for e in result["entities"] if e["type"] != "artifact"]
    assert passages
    assert all(e["type"] == "authority_source" and not e["attributes"]["about_complainant"] for e in passages)


def test_real_verified_graph_fact_can_link_to_real_legal_rule_without_rewriting_proof():
    from integrations.ipfs_datasets.types import source_byte_hash, user_assertion_from_mapping
    text = "I was fired."
    factual = KnowledgeGraphBuilder().build_from_text(text, source_context={
        "source_kind": "user_statement", "source_id": "message-real", "message_id": "message-real",
        "source_hash": source_byte_hash(text), "assertion_status": "asserted", "extractor_version": "audit.v1"})
    fact = next(e for e in factual.entities.values() if e.type == "fact" and user_assertion_from_mapping(e.provenance["user_assertion"]).is_asserted_user_fact)
    original_id, original_proof = fact.id, dict(fact.provenance["user_assertion"])
    rule = LegalGraphBuilder().project_legal_passage({"text": "Retaliation is prohibited.", "passage_role": "rule_candidate", "source_id": "rule-source", "provenance": {"source_id": "rule-source"}})
    graph = DependencyGraph()
    link = DependencyGraphBuilder().add_fact_rule_link(graph,
        factual_assertion_id=fact.id, rule_id=rule.id,
        factual_provenance=fact.provenance, rule_provenance=rule.attributes["provenance"])
    assert record_kind_from_id(link["factual_assertion_id"]) == "factual_assertion"
    assert fact.id == original_id and fact.provenance["user_assertion"] == original_proof
    assert link["provenance_chains"]["factual_assertion"]["user_assertion"] == original_proof


def test_cross_graph_link_rejects_existing_wrong_typed_endpoint():
    import pytest
    from complaint_phases.dependency_graph import DependencyNode, NodeType
    graph = DependencyGraph()
    factual_id = mint_graph_record_id("factual_assertion", "fact")
    rule_id = mint_graph_record_id("rule_candidate", "rule")
    graph.add_node(DependencyNode(id=factual_id, node_type=NodeType.LEGAL_ELEMENT, name="a norm",
        attributes={"record_kind": "authority_source", "provenance": {"source_id": "statute"}}))
    with pytest.raises(ValueError):
        DependencyGraphBuilder().add_fact_rule_link(graph, factual_assertion_id=factual_id, rule_id=rule_id,
            factual_provenance={"source_id": "message"}, rule_provenance={"source_id": "rule"})


def test_support_query_dedup_retains_distinct_factual_and_legal_records():
    from integrations.ipfs_datasets.graphs import query_graph_support
    fact_id = mint_graph_record_id("factual_assertion", "f")
    rule_id = mint_graph_record_id("legal_requirement", "r")
    result = query_graph_support("element", claim_element_text="Equal protection", support_facts=[
        {"fact_id": fact_id, "text": "Equal protection", "record_kind": "factual_assertion", "source_kind": "testimony", "confidence": .6},
        {"fact_id": rule_id, "text": "Equal protection", "record_kind": "legal_requirement", "source_kind": "law", "confidence": .9},
    ])
    assert {r["fact_id"] for r in result["results"]} == {fact_id, rule_id}


def test_namespaced_identity_does_not_alias_delimiter_bearing_parts():
    assert mint_graph_record_id("factual_assertion", "a|b", "c") != mint_graph_record_id("factual_assertion", "a", "b|c")


def test_snapshot_content_identity_binds_explicit_namespace():
    from integrations.ipfs_datasets.graphs import build_graph_persistence_request
    payload = {"source_id": "same", "entities": [{"id": "same", "name": "same"}], "relationships": []}
    first = build_graph_persistence_request({**payload, "metadata": {"namespace": "factual_assertion"}})
    second = build_graph_persistence_request({**payload, "metadata": {"namespace": "authority_source"}})
    assert first["content_hash"] != second["content_hash"]
    assert first["snapshot_id"] != second["snapshot_id"]


def test_nested_legal_context_never_creates_an_asserted_user_fact():
    from integrations.ipfs_datasets.types import source_byte_hash, user_assertion_from_mapping
    text = "A landlord must accommodate a disability."
    graph = KnowledgeGraphBuilder().build_from_text(text, source_context={
        "source_kind": "user_statement", "source_id": "synthetic-message", "message_id": "synthetic-message",
        "source_hash": source_byte_hash(text), "assertion_status": "asserted", "extractor_version": "audit.v1",
        "provenance": {"source_type": "statute", "source_id": "synthetic-law"},
    })
    assert graph.entities
    assert all(e.type == "legal_text" and e.attributes["about_complainant"] is False for e in graph.entities.values())
    assert all(not user_assertion_from_mapping(e.provenance["user_assertion"]).is_asserted_user_fact for e in graph.entities.values())


def test_legal_subtypes_do_not_collapse_in_resolution_or_support_query():
    from integrations.ipfs_datasets.graphs import query_graph_support
    records = [
        {"id": mint_graph_record_id(kind, "same"), "fact_id": mint_graph_record_id(kind, "same"),
         "name": "Equal protection", "text": "Equal protection", "record_kind": kind, "source_kind": "law"}
        for kind in ("authority_source", "rule_candidate", "legal_requirement")
    ]
    assert resolve_duplicate_entities(records)["entity_count"] == 3
    queried = query_graph_support("element", claim_element_text="Equal protection", support_facts=records)
    assert {r["fact_id"] for r in queried["results"]} == {r["fact_id"] for r in records}


def test_unclassified_record_cannot_be_merged_into_testimony():
    result = resolve_duplicate_entities([
        {"id": "known", "name": "Equal protection", "source_kind": "testimony"},
        {"id": "unknown", "name": "Equal protection"},
    ])
    assert result["entity_count"] == 2


def test_cross_graph_link_checks_rule_before_creating_any_endpoint():
    import pytest
    from complaint_phases.dependency_graph import DependencyNode, NodeType
    graph = DependencyGraph()
    fact_id, rule_id = mint_graph_record_id("factual_assertion", "f"), mint_graph_record_id("rule_candidate", "r")
    graph.add_node(DependencyNode(id=rule_id, node_type=NodeType.FACT, name="not a rule", attributes={"record_kind": "factual_assertion"}))
    before = graph.to_dict()
    with pytest.raises(ValueError):
        DependencyGraphBuilder().add_fact_rule_link(graph, factual_assertion_id=fact_id, rule_id=rule_id)
    assert graph.to_dict() == before


def test_link_replay_is_idempotent_and_preserves_independent_source_chains():
    import pytest
    graph, builder = DependencyGraph(), DependencyGraphBuilder()
    fact_id, rule_id = mint_graph_record_id("factual_assertion", "f"), mint_graph_record_id("rule_candidate", "r")
    factual = {"source_id": "message", "nested": {"source_revision": 1}}
    legal = {"source_id": "law", "nested": {"source_revision": 2}}
    kwargs = {"factual_assertion_id": fact_id, "rule_id": rule_id, "factual_provenance": factual, "rule_provenance": legal}
    first = builder.add_fact_rule_link(graph, **kwargs)
    assert builder.add_fact_rule_link(graph, **kwargs) == first
    assert len(graph.dependencies) == 1 and len(graph.metadata["cross_graph_links"]) == 1
    assert not graph.nodes[fact_id].satisfied and not graph.nodes[rule_id].satisfied
    factual["nested"]["source_revision"] = 99
    legal["nested"]["source_revision"] = 98
    first["provenance_chains"]["rule"]["nested"]["source_revision"] = 97
    assert graph.nodes[fact_id].attributes["provenance"]["nested"]["source_revision"] == 1
    assert graph.metadata["cross_graph_links"][0]["provenance_chains"]["rule"]["nested"]["source_revision"] == 2
    before = graph.to_dict()
    with pytest.raises(ValueError):
        builder.add_fact_rule_link(graph, **kwargs)
    assert graph.to_dict() == before


def test_local_unverified_or_legal_proof_cannot_supply_a_factual_link():
    import pytest
    rule_id = mint_graph_record_id("rule_candidate", "r")
    with pytest.raises(ValueError):
        build_namespaced_support_link(factual_assertion_id="ent_1", rule_id=rule_id,
                                      factual_provenance={"source_id": "unknown"})
    with pytest.raises(ValueError):
        build_namespaced_support_link(factual_assertion_id=mint_graph_record_id("factual_assertion", "f"),
            rule_id=rule_id, factual_provenance={"attributes": {"provenance": {"source_type": "statute"}}})
    with pytest.raises(ValueError):
        build_namespaced_support_link(factual_assertion_id=mint_graph_record_id("factual_assertion", "f"),
            rule_id=rule_id, rule_provenance={"source_kind": "user_statement"})


def test_same_local_id_cannot_overwrite_factual_graph_with_a_legal_record():
    import pytest
    from complaint_phases.knowledge_graph import Entity, KnowledgeGraph
    factual, legal = KnowledgeGraph(), KnowledgeGraph()
    original = Entity(id="ent_1", type="fact", name="I was fired.", provenance={"source_id": "message"})
    factual.add_entity(original)
    legal.add_entity(Entity(id="ent_1", type="legal_text", name="Discharge is prohibited.", source="legal"))
    with pytest.raises(ValueError):
        factual.merge_with(legal)
    assert factual.entities["ent_1"] is original
    assert original.provenance == {"source_id": "message"}


def test_legal_and_requirement_ids_bind_source_content_across_fresh_builders():
    passage = {"text": "Retaliation is prohibited.", "passage_role": "rule_candidate", "provenance": {"source_id": "law-A"}}
    first = LegalGraphBuilder().project_legal_passage(passage)
    builder = LegalGraphBuilder()
    builder.project_legal_passage({**passage, "text": "An unrelated rule."})
    assert builder.project_legal_passage(passage).id == first.id
    assert LegalGraphBuilder().project_legal_passage({**passage, "provenance": {"source_id": "law-B"}}).id != first.id
    def requirement_id(source):
        graph = DependencyGraphBuilder().build_from_claims([{"name": "Retaliation", "type": "retaliation"}],
            {"retaliation": [{"name": "Protected activity", "provenance": {"source_id": source}}]})
        return next(n.id for n in graph.nodes.values() if n.attributes.get("record_kind") == "legal_requirement")
    assert requirement_id("law-A") == requirement_id("law-A")
    assert requirement_id("law-A") != requirement_id("law-B")


def _verified_fact_for_namespace_checks():
    from integrations.ipfs_datasets.types import source_byte_hash, user_assertion_from_mapping
    text = "I was fired."
    graph = KnowledgeGraphBuilder().build_from_text(text, source_context={
        "source_kind": "user_statement", "source_id": "typed-message", "message_id": "typed-message",
        "source_hash": source_byte_hash(text), "assertion_status": "asserted", "extractor_version": "audit.v1"})
    return next(entity for entity in graph.entities.values() if entity.type == "fact"
                and user_assertion_from_mapping(entity.provenance["user_assertion"]).is_asserted_user_fact)


@pytest.mark.parametrize("source", ["law", "statute", "regulation", "case_law"])
def test_deserialized_legal_origin_cannot_replay_a_verified_user_envelope(source):
    from copy import deepcopy
    from complaint_phases.knowledge_graph import Entity
    from integrations.ipfs_datasets.types import user_assertion_from_mapping
    fact = _verified_fact_for_namespace_checks()
    original = deepcopy(fact.provenance)
    replay = Entity(id=fact.id, type=fact.type, name=fact.name, attributes=deepcopy(fact.attributes),
                    source=source, provenance=deepcopy(fact.provenance))
    assert not user_assertion_from_mapping(replay.provenance["user_assertion"]).is_asserted_user_fact
    assert replay.provenance["user_assertion"]["record_type"] == "legal_text"
    assert fact.provenance == original
    assert user_assertion_from_mapping(fact.provenance["user_assertion"]).is_asserted_user_fact


@pytest.mark.parametrize("alias", ["", "authority_source:law", "rule_candidate:rule", "legal_requirement:req", "support_link:s", "contradiction_link:c", "factual_assertion:wrong", "authority_source:", "factual_assertion:"])
def test_verified_user_proof_does_not_authorize_an_empty_or_wrong_namespace_alias(alias):
    fact = _verified_fact_for_namespace_checks()
    with pytest.raises(ValueError):
        build_namespaced_support_link(factual_assertion_id=alias, rule_id=mint_graph_record_id("rule_candidate", "r"),
                                      factual_provenance=fact.provenance)


def test_verified_fact_node_text_is_the_proven_span_not_a_caller_claim():
    fact = _verified_fact_for_namespace_checks()
    graph, builder = DependencyGraph(), DependencyGraphBuilder()
    kwargs = {"factual_assertion_id": fact.id, "rule_id": mint_graph_record_id("rule_candidate", "r"),
              "factual_provenance": fact.provenance, "rule_provenance": {"source_id": "law"}}
    before = graph.to_dict()
    with pytest.raises(ValueError):
        builder.add_fact_rule_link(graph, **kwargs, factual_name="A different and unsupported allegation.")
    assert graph.to_dict() == before
    link = builder.add_fact_rule_link(graph, **kwargs)
    node = graph.nodes[link["factual_assertion_id"]]
    assert node.name == fact.provenance["user_assertion"]["source_span_text"]
    assert node.attributes["source_entity_id"] == fact.id
    assert node.attributes["assertion_verified"] is True
    assert node.attributes["provenance"]["user_assertion"] == fact.provenance["user_assertion"]


def test_current_legal_kind_precedes_inherited_rule_provenance():
    records = [
        {"id": "requirement", "name": "Same text", "record_kind": "legal_requirement", "provenance": {"passage_role": "rule_candidate"}},
        {"id": "authority", "name": "Same text", "record_kind": "authority_source", "provenance": {"passage_role": "rule_candidate"}},
        {"id": "rule", "name": "Same text", "record_kind": "rule_candidate"},
    ]
    result = resolve_duplicate_entities(records)
    assert result["entity_count"] == 3
    assert {record["resolution_kind"] for record in result["clusters"]} == {"legal_requirement", "authority_source", "rule_candidate"}


def test_nested_span_serialization_remains_valid_without_rewriting_its_proof():
    from copy import deepcopy
    from integrations.ipfs_datasets.types import user_assertion_from_mapping
    fact = _verified_fact_for_namespace_checks()
    proof = deepcopy(fact.provenance)
    for key in ("source_span_start", "source_span_end", "source_span_text"):
        proof["user_assertion"].pop(key)
    original = deepcopy(proof)
    envelope = user_assertion_from_mapping(proof["user_assertion"])
    assert envelope.is_asserted_user_fact
    graph = DependencyGraph()
    link = DependencyGraphBuilder().add_fact_rule_link(graph,
        factual_assertion_id=fact.id, rule_id=mint_graph_record_id("rule_candidate", "r"),
        factual_provenance=proof)
    assert graph.nodes[link["factual_assertion_id"]].name == envelope.source_span_text
    assert link["provenance_chains"]["factual_assertion"] == original == proof


@pytest.mark.parametrize("tamper", ["fact_id", "rule_id", "dependency_id", "fact_name"])
def test_deserialized_link_replay_checks_stored_identity_and_verified_content(tamper):
    from copy import deepcopy
    fact = _verified_fact_for_namespace_checks()
    graph, builder = DependencyGraph(), DependencyGraphBuilder()
    rule = LegalGraphBuilder().project_legal_passage({"text": "Retaliation is prohibited.",
        "passage_role": "rule_candidate", "provenance": {"source_id": "synthetic-law"}})
    kwargs = {"factual_assertion_id": fact.id, "rule_id": rule.id,
              "factual_provenance": deepcopy(fact.provenance), "rule_provenance": deepcopy(rule.attributes["provenance"])}
    link = builder.add_fact_rule_link(graph, **kwargs)
    payload = deepcopy(graph.to_dict())
    if tamper == "fact_id":
        payload["nodes"][link["factual_assertion_id"]]["id"] = "authority_source:foreign"
    elif tamper == "rule_id":
        payload["nodes"][rule.id]["id"] = "factual_assertion:foreign"
    elif tamper == "dependency_id":
        payload["dependencies"][link["link_id"]]["id"] = "contradiction_link:foreign"
    else:
        payload["nodes"][link["factual_assertion_id"]]["name"] = "An unrelated unsupported allegation."
    replay = DependencyGraph.from_dict(payload)
    before = deepcopy(replay.to_dict())
    with pytest.raises(ValueError):
        builder.add_fact_rule_link(replay, **kwargs)
    assert replay.to_dict() == before
    assert fact.provenance == kwargs["factual_provenance"]


def test_unchanged_deserialized_real_link_replays_without_rewriting_proof():
    from copy import deepcopy
    fact = _verified_fact_for_namespace_checks()
    graph, builder = DependencyGraph(), DependencyGraphBuilder()
    kwargs = {"factual_assertion_id": fact.id, "rule_id": mint_graph_record_id("rule_candidate", "synthetic-law"),
              "factual_provenance": deepcopy(fact.provenance), "rule_provenance": {"source_id": "synthetic-law"}}
    link = builder.add_fact_rule_link(graph, **kwargs)
    replay = DependencyGraph.from_dict(deepcopy(graph.to_dict()))
    assert builder.add_fact_rule_link(replay, **kwargs) == link
    assert len(replay.dependencies) == len(replay.metadata["cross_graph_links"]) == 1
    assert fact.provenance == kwargs["factual_provenance"]


def _statement_context(text, **overrides):
    from integrations.ipfs_datasets.types import source_byte_hash
    context = {
        "source_kind": "user_statement",
        "source_id": "message-private",
        "message_id": "message-private",
        "source_hash": source_byte_hash(text),
        "assertion_status": "asserted",
        "extractor_version": "audit.v1",
    }
    context.update(overrides)
    return context


class _UpstreamEntity:
    def __init__(self, entity_id, entity_type, name, source_text, extraction_method="rule_based"):
        self.entity_id = entity_id
        self.entity_type = entity_type
        self.name = name
        self.properties = {}
        self.confidence = 0.99
        self.source_text = source_text
        self.extraction_method = extraction_method

    def to_dict(self):
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "properties": dict(self.properties),
            "confidence": self.confidence,
            "source_text": self.source_text,
        }


class _UpstreamRelationship:
    def __init__(self, relationship_id, relationship_type, source, target, source_text):
        self.relationship_id = relationship_id
        self.relationship_type = relationship_type
        self.source_entity = source
        self.target_entity = target
        self.properties = {"source_id": source.entity_id, "target_id": target.entity_id}
        self.confidence = 0.91
        self.source_text = source_text
        self.extraction_method = "rule_based"

    def to_dict(self):
        return {
            "relationship_id": self.relationship_id,
            "relationship_type": self.relationship_type,
            "source": self.source_entity.to_dict(),
            "target": self.target_entity.to_dict(),
            "properties": dict(self.properties),
            "confidence": self.confidence,
            "source_text": self.source_text,
        }


class _UpstreamGraph:
    def __init__(self, entities, relationships):
        self.entities = {entity.entity_id: entity for entity in entities}
        self.relationships = {relationship.relationship_id: relationship for relationship in relationships}

    def to_dict(self):
        return {
            "entities": [entity.to_dict() for entity in self.entities.values()],
            "relationships": [relationship.to_dict() for relationship in self.relationships.values()],
        }


def _patch_extractor(monkeypatch, graph_factory):
    seen = {"constructed": [], "texts": []}

    class _Extractor:
        def __init__(self, **options):
            seen["constructed"].append(dict(options))

        def extract_knowledge_graph(self, text, extraction_temperature=0.7, structure_temperature=0.5):
            seen["texts"].append(text)
            seen["temperatures"] = (extraction_temperature, structure_temperature)
            return graph_factory(text)

    def _owned_transport(text, timeout_seconds):
        from integrations.ipfs_datasets.graphs import _PRIVATE_EXTRACTOR_OPTIONS
        instance = _Extractor(**_PRIVATE_EXTRACTOR_OPTIONS)
        graph = instance.extract_knowledge_graph(text)
        return "ok", {
            "status": "ok", "entities": list(graph.entities.values()),
            "relationships": list(graph.relationships.values()),
        }
    monkeypatch.setattr("integrations.ipfs_datasets.graphs._run_owned_private_extractor", _owned_transport)
    return seen


def _asserted_upstream(result):
    from integrations.ipfs_datasets.types import user_assertion_from_mapping
    asserted = []
    for entity in result["entities"]:
        if entity.get("attributes", {}).get("extraction_mode") == "legacy_sentence_heuristic":
            continue
        if entity.get("type") in {"artifact", "claim_element"}:
            continue
        envelope = user_assertion_from_mapping(entity.get("assertion") or {})
        if envelope.is_asserted_user_fact:
            asserted.append((entity, envelope))
    return asserted


def test_private_extractor_is_called_with_safe_flags_and_exact_spans(monkeypatch):
    text = "José reported the hazard."
    person = _UpstreamEntity("uuid-person", "person", "José", text)
    date = _UpstreamEntity("uuid-date", "date", "hazard", text)
    relation = _UpstreamRelationship("uuid-rel", "reported", person, date, text)
    seen = _patch_extractor(monkeypatch, lambda submitted: _UpstreamGraph([person, date], [relation]))
    result = extract_graph_from_text(text, source_id="message-private", metadata=_statement_context(text))
    assert seen["constructed"] == [{
        "use_spacy": False,
        "use_transformers": False,
        "use_tracer": False,
        "use_srl": False,
    }]
    assert seen["texts"] == [text]
    assert result["metadata"]["implementation_status"] == "upstream"
    asserted = _asserted_upstream(result)
    assert {entity["name"] for entity, _envelope in asserted} == {"José", "hazard"}
    raw = text.encode("utf-8")
    for entity, envelope in asserted:
        assert entity["id"] not in {"uuid-person", "uuid-date", "message-private"}
        assert raw[envelope.source_span_start:envelope.source_span_end].decode("utf-8") == entity["name"]
        assert envelope.source_hash
        assert entity["provenance"]["extractor"]["extraction_method"] == "rule_based"
    relationships = [item for item in result["relationships"] if item["relation_type"] == "reported"]
    assert len(relationships) == 1
    relation_payload = relationships[0]
    asserted_ids = {entity["id"] for entity, _envelope in asserted}
    assert relation_payload["source_id"] in asserted_ids
    assert relation_payload["target_id"] in asserted_ids
    assert relation_payload["source_id"] != "message-private"
    assert "uuid-rel" not in {relation_payload["id"], relation_payload["source_id"], relation_payload["target_id"]}
    from integrations.ipfs_datasets.types import user_assertion_from_mapping
    assert not user_assertion_from_mapping(relation_payload["assertion"]).is_asserted_user_fact


def test_repeated_unicode_and_model_mentions_stay_unasserted(monkeypatch):
    text = "José saw José near the café."
    records = [
        _UpstreamEntity("p1", "person", "José", text),
        _UpstreamEntity("f1", "field", "café", text, extraction_method="model"),
        _UpstreamEntity("w1", "person", text, text),
    ]
    _patch_extractor(monkeypatch, lambda _submitted: _UpstreamGraph(records, []))
    result = extract_graph_from_text(text, source_id="message-private", metadata=_statement_context(text))
    assert _asserted_upstream(result) == []
    rendered = str(result["entities"])
    assert "ambiguous_source_span" in rendered
    assert "source_text_not_a_span" in rendered or "model" in rendered


def test_document_source_binds_graph_endpoints_not_document_ids(monkeypatch):
    from integrations.ipfs_datasets.types import source_byte_hash, user_assertion_from_mapping
    text = "Ada notified HR."
    person = _UpstreamEntity("uuid-ada", "person", "Ada", "window")
    org = _UpstreamEntity("uuid-hr", "organization", "HR", "window")
    relation = _UpstreamRelationship("uuid-edge", "notified", person, org, text)
    _patch_extractor(monkeypatch, lambda _submitted: _UpstreamGraph([person, org], [relation]))
    metadata = {
        "source_kind": "user_uploaded_document",
        "source_id": "document-9",
        "document_id": "document-9",
        "source_hash": source_byte_hash(text),
        "assertion_status": "asserted",
        "extractor_version": "audit.v1",
    }
    result = extract_graph_from_text(text, source_id="document-9", metadata=metadata)
    asserted = {entity["name"]: entity for entity, _envelope in _asserted_upstream(result)}
    assert set(asserted) == {"Ada", "HR"}
    edge = next(item for item in result["relationships"] if item["relation_type"] == "notified")
    assert edge["source_id"] == asserted["Ada"]["id"]
    assert edge["target_id"] == asserted["HR"]["id"]
    assert edge["assertion"]["graph_source_id"] == asserted["Ada"]["id"]
    assert edge["assertion"]["graph_target_id"] == asserted["HR"]["id"]
    assert edge["source_id"] != "document-9"
    assert not user_assertion_from_mapping(edge["assertion"]).is_asserted_user_fact


@pytest.mark.parametrize("override", [
    {"source_hash": "0" * 64},
    {"message_id": "", "source_id": ""},
    {"assertion_status": "suggestion"},
    {"extractor_version": ""},
    {"source_kind": "model_output"},
])
def test_missing_or_mismatched_caller_source_cannot_assert(monkeypatch, override):
    text = "Ada notified HR."
    _patch_extractor(monkeypatch, lambda _submitted: _UpstreamGraph([
        _UpstreamEntity("uuid-ada", "person", "Ada", text),
    ], []))
    context = _statement_context(text)
    context.update(override)
    result = extract_graph_from_text(text, source_id=context.get("source_id") or None, metadata=context)
    assert _asserted_upstream(result) == []


def test_absent_error_invalid_and_hanging_backends_fabricate_nothing(monkeypatch):
    """Typed transport mapping; real deadline/cleanup is exercised separately."""
    from integrations.ipfs_datasets.types import user_assertion_from_mapping
    text = "Ada notified HR."
    context = _statement_context(text, extraction_timeout_seconds=0.05)
    outcomes = [
        ("extractor_unavailable", None, "unavailable", "extractor_unavailable"),
        ("error", None, "degraded", "extractor_error"),
        ("ok", {"status": "extractor_invalid_result"}, "degraded", "extractor_invalid_result"),
        ("timeout", None, "degraded", "extractor_timeout"),
    ]
    for outcome, payload, expected_status, diagnostic in outcomes:
        monkeypatch.setattr("integrations.ipfs_datasets.graphs._run_owned_private_extractor",
                            lambda *_args, _outcome=outcome, _payload=payload: (_outcome, _payload))
        result = extract_graph_from_text(text, source_id="message-private", metadata=context)
        assert result["status"] == expected_status
        assert result["metadata"]["private_extraction"]["diagnostic"] == diagnostic
        assert _asserted_upstream(result) == []
        assert not result["relationships"]
        for entity in result["entities"]:
            envelope = user_assertion_from_mapping(entity.get("assertion") or {})
            assert not envelope.is_asserted_user_fact


def test_real_private_extractor_smoke_disables_network_and_downloads(tmp_path, monkeypatch):
    """Actual configured source checkout; optional absence remains explicit."""
    text = "Marie Curie reported a hazard in 2020."
    result = extract_graph_from_text(text, source_id="message-private", metadata=_statement_context(text))
    private = result["metadata"]["private_extraction"]
    # Keep the real optional-backend branch observable without retaining text.
    import json
    observed = {
        "schema": "complaint-fact02-configured-smoke-outcome@1",
        "status": private.get("status"), "diagnostic": private.get("diagnostic"),
        "bounded": private.get("bounded"), "options": private.get("options"),
        "entity_count": len(result["entities"]), "relationship_count": len(result["relationships"]),
        "asserted_entity_count": len(_asserted_upstream(result)),
        "real_network_permitted": False,
    }
    outcome = tmp_path / "configured-extractor-smoke.json"
    outcome.write_text(json.dumps(observed, sort_keys=True) + "\n")
    outcome.chmod(0o600)
    if private.get("status") != "available":
        assert private.get("status") in {"unavailable", "degraded"}
        assert private.get("diagnostic") in {
            "extractor_unavailable", "extractor_custody_unavailable", "extractor_effect_denied",
            "extractor_timeout", "extractor_cleanup_unconfirmed", "extractor_error",
        }
        assert _asserted_upstream(result) == []
        return
    assert private["status"] == "available"
    assert private["options"] == {
        "use_spacy": False,
        "use_transformers": False,
        "use_tracer": False,
        "use_srl": False,
    }
    asserted = _asserted_upstream(result)
    assert asserted
    raw = text.encode("utf-8")
    for entity, envelope in asserted:
        assert raw[envelope.source_span_start:envelope.source_span_end].decode("utf-8") == envelope.source_span_text
        assert entity["name"] in text
    from integrations.ipfs_datasets.types import user_assertion_from_mapping
    for relationship in result["relationships"]:
        if relationship.get("attributes", {}).get("upstream_extraction") is True:
            assert not user_assertion_from_mapping(relationship.get("assertion") or {}).is_asserted_user_fact



def test_model_person_with_exact_span_is_not_a_user_fact(monkeypatch):
    text = "Ada notified HR."
    _patch_extractor(monkeypatch, lambda _submitted: _UpstreamGraph([
        _UpstreamEntity("model-ada", "person", "Ada", text, extraction_method="neural"),
    ], []))
    result = extract_graph_from_text(text, source_id="message-private", metadata=_statement_context(text))
    assert _asserted_upstream(result) == []
    person = next(item for item in result["entities"] if item["name"] == "Ada")
    assert person["assertion"]["assertion_status"] != "asserted"
    assert not any(item["relation_type"] == "supports" for item in result["relationships"])


def test_empty_upstream_graph_does_not_invent_legacy_fact_or_support(monkeypatch):
    text = "A synthetic allegation with no extracted record."
    _patch_extractor(monkeypatch, lambda _submitted: _UpstreamGraph([], []))
    result = extract_graph_from_text(text, source_id="message-private", metadata={
        **_statement_context(text), "claim_element_id": "synthetic-causation",
        "claim_element_text": "causation",
    })
    assert result["status"] == "available"
    assert "extractor_empty" in result["metadata"]["private_extraction"]["diagnostics"]
    assert {item["type"] for item in result["entities"]} <= {"artifact", "claim_element"}
    assert result["relationships"] == []
    assert _asserted_upstream(result) == []
    from complaint_phases.knowledge_graph import KnowledgeGraph, graph_entity_to_entity
    graph = KnowledgeGraph()
    for entity in result["entities"]:
        graph.add_entity(graph_entity_to_entity(entity))
    assert graph._support_facts("synthetic-causation", "causation") == []
    assert graph.query_support("synthetic-causation", claim_element_text="causation")["results"] == []


def test_canonical_builder_uses_same_owned_preparation_once_and_preserves_local_proofs(monkeypatch):
    text = "My employer Acme fired me on January 2, 2025. Ada notified HR."
    context = _statement_context(text)
    baseline = KnowledgeGraphBuilder().build_from_text(
        text, source_context=context, extracted_entities=[], extracted_relationships=[],
    )
    person = _UpstreamEntity("upstream-ada", "person", "Ada", text)
    organization = _UpstreamEntity("upstream-hr", "organization", "HR", text)
    relation = _UpstreamRelationship("upstream-notified", "notified", person, organization, text)
    seen = _patch_extractor(monkeypatch, lambda _submitted: _UpstreamGraph([person, organization], [relation]))
    graph = KnowledgeGraphBuilder().build_from_text(text, source_context=context)
    assert seen["texts"] == [text]
    assert len(seen["constructed"]) == 1
    assert graph.metadata["private_extraction"]["status"] == "available"
    assert baseline.entities
    for identifier, entity in baseline.entities.items():
        assert graph.entities[identifier].to_dict() == entity.to_dict()
    for identifier, relationship in baseline.relationships.items():
        assert graph.relationships[identifier].to_dict() == relationship.to_dict()
    upstream = {entity.name:entity for entity in graph.entities.values()
                if entity.attributes.get("upstream_extraction") is True}
    assert set(upstream) == {"Ada", "HR"}
    assert not set(entity.id for entity in upstream.values()) & set(baseline.entities)
    from integrations.ipfs_datasets.types import user_assertion_from_mapping
    for entity in upstream.values():
        envelope = user_assertion_from_mapping(entity.provenance["user_assertion"])
        assert envelope.is_asserted_user_fact
        assert text.encode()[envelope.source_span_start:envelope.source_span_end].decode() == entity.name
    upstream_links = [link for link in graph.relationships.values()
                      if link.attributes.get("upstream_extraction") is True]
    assert len(upstream_links) == 1
    assert upstream_links[0].source_id == upstream["Ada"].id
    assert upstream_links[0].target_id == upstream["HR"].id
    assert upstream_links[0].relation_type == "notified"
    assert not user_assertion_from_mapping(upstream_links[0].provenance["user_assertion"]).is_asserted_user_fact
    assert all(link.id in baseline.relationships or link.attributes.get("upstream_extraction") is True
               for link in graph.relationships.values())


def test_canonical_builder_missing_source_cannot_authorize_upstream_model_or_support(monkeypatch):
    text = "Ada notified HR."
    seen = _patch_extractor(monkeypatch, lambda _submitted: _UpstreamGraph([
        _UpstreamEntity("upstream-ada", "person", "Ada", text),
    ], []))
    graph = KnowledgeGraphBuilder().build_from_text(text)
    upstream = [entity for entity in graph.entities.values() if entity.attributes.get("upstream_extraction") is True]
    assert seen["texts"] == [text]
    assert len(upstream) == 1
    assert upstream[0].provenance["user_assertion"]["assertion_status"] != "asserted"
    assert "caller_source_not_authorized" in graph.metadata["private_extraction"]["diagnostics"]
    assert not any(link.relation_type in {"supports", "supported_by", "has_fact"}
                   and upstream[0].id in {link.source_id, link.target_id}
                   for link in graph.relationships.values())


@pytest.mark.parametrize("method, text, context_override", [
    ("neural", "Ada notified HR.", {}),
    ("rule_based", "Ada notified HR.", {"source_hash":"0"*64}),
    ("rule_based", "Ada saw Ada.", {}),
])
def test_unverified_upstream_fact_cannot_enter_actual_support_query(monkeypatch, method, text, context_override):
    from complaint_phases.knowledge_graph import KnowledgeGraph, graph_entity_to_entity
    _patch_extractor(monkeypatch, lambda _submitted: _UpstreamGraph([
        _UpstreamEntity("upstream-fact", "fact", "Ada", text, extraction_method=method),
    ], []))
    result = extract_graph_from_text(text, source_id="message-private", metadata=_statement_context(text, **context_override))
    graph = KnowledgeGraph()
    for record in result["entities"]:
        graph.add_entity(graph_entity_to_entity(record))
    candidate = next(entity for entity in graph.entities.values() if entity.attributes.get("upstream_extraction") is True)
    assert candidate.type == "model_suggestion"
    assert candidate.attributes["origin"] == "model"
    assert candidate.attributes["record_type"] == "model_suggestion"
    assert candidate.attributes["upstream_entity_type"] == "fact"
    assert candidate.provenance["user_assertion"]["assertion_status"] != "asserted"
    assert graph._support_facts("unseen-claim", "Ada") == []
    assert graph.query_support("unseen-claim", claim_element_text="Ada")["results"] == []


def test_verified_upstream_fact_retains_source_proof_and_support_visibility(monkeypatch):
    from complaint_phases.knowledge_graph import KnowledgeGraph, graph_entity_to_entity
    text = "Ada notified HR."
    _patch_extractor(monkeypatch, lambda _submitted: _UpstreamGraph([
        _UpstreamEntity("upstream-fact", "fact", "Ada", text),
    ], []))
    result = extract_graph_from_text(text, source_id="message-private", metadata=_statement_context(text))
    graph = KnowledgeGraph()
    for record in result["entities"]:
        graph.add_entity(graph_entity_to_entity(record))
    fact = next(entity for entity in graph.entities.values() if entity.attributes.get("upstream_extraction") is True)
    assert fact.type == "fact"
    assert fact.provenance["user_assertion"]["assertion_status"] == "asserted"
    support = graph._support_facts("unseen-claim", "Ada")
    assert len(support) == 1 and support[0]["fact_id"] == fact.id
    assert support[0]["provenance"]["user_assertion"] == fact.provenance["user_assertion"]
    assert len(graph.query_support("unseen-claim", claim_element_text="Ada")["results"]) == 1


@pytest.mark.parametrize("relation_type", ["supports", "supported_by"])
def test_unverified_upstream_support_edge_cannot_link_a_verified_fact_to_a_claim(monkeypatch, relation_type):
    from complaint_phases.knowledge_graph import KnowledgeGraph, graph_entity_to_entity, graph_relationship_to_relationship
    text = "Ada notified HR."
    fact = _UpstreamEntity("upstream-fact", "fact", "Ada", text)
    claim = _UpstreamEntity("upstream-claim", "claim", "HR", text, extraction_method="model")
    link = _UpstreamRelationship("upstream-support", relation_type, fact, claim, text)
    _patch_extractor(monkeypatch, lambda _submitted: _UpstreamGraph([fact, claim], [link]))
    result = extract_graph_from_text(text, source_id="message-private", metadata=_statement_context(text))
    graph = KnowledgeGraph()
    for record in result["entities"]:
        graph.add_entity(graph_entity_to_entity(record))
    for record in result["relationships"]:
        graph.add_relationship(graph_relationship_to_relationship(record))
    fact_node = next(entity for entity in graph.entities.values() if entity.name == "Ada")
    claim_node = next(entity for entity in graph.entities.values() if entity.name == "HR")
    assert fact_node.provenance["user_assertion"]["assertion_status"] == "asserted"
    assert len(graph.relationships) == 1
    suggestion = next(iter(graph.relationships.values()))
    assert suggestion.relation_type == "model_suggestion"
    assert suggestion.attributes["upstream_relationship_type"] == relation_type
    assert suggestion.attributes["record_type"] == "model_suggestion"
    assert suggestion.provenance["user_assertion"]["assertion_status"] != "asserted"
    assert graph._support_facts(claim_node.id, "HR") == []
    assert graph.query_support(claim_node.id, claim_element_text="HR")["results"] == []


def test_canonical_legal_and_explicit_record_projections_do_not_dispatch_private_extractor(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Explicit/legal projection must not invoke the private extractor")
    monkeypatch.setattr("integrations.ipfs_datasets.graphs._run_owned_private_extractor", forbidden)
    legal = KnowledgeGraphBuilder().build_from_text(
        "Retaliation is prohibited.", source_context={"source_kind":"law", "source_id":"synthetic-law"},
    )
    assert all(entity.type == "legal_text" for entity in legal.entities.values())
    explicit = KnowledgeGraphBuilder().build_from_text("Ada notified HR.", extracted_entities=[], extracted_relationships=[])
    assert "private_extraction" not in explicit.metadata
    projected = KnowledgeGraphBuilder().build_from_text("Ada notified HR.", include_local_heuristics=False)
    assert not projected.entities


PRIVATE_EXTRACTOR_FIXTURE_SOURCE = r"""
import hashlib, json, os, pathlib, socket, subprocess, sys, time
from types import SimpleNamespace
root = pathlib.Path(__file__).resolve().parents[3]
mode = json.loads((root/'mode.json').read_text())['mode']
def birth(pid):
    value = pathlib.Path('/proc/'+str(pid)+'/stat').read_text()
    return int(value[value.rfind(')')+2:].split()[19])
(root/'worker.json').write_text(json.dumps({'pid':os.getpid(),'ticks':birth(os.getpid()),
    'manager_pid':os.getppid(),'manager_ticks':birth(os.getppid()),'mode':mode}))
if mode == 'import-block': time.sleep(30)
class KnowledgeGraphExtractor:
    def __init__(self, **options):
        assert options == {'use_spacy':False,'use_transformers':False,'use_tracer':False,'use_srl':False}
        assert os.environ.get('IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD') == '0'
        assert os.environ.get('HF_HUB_OFFLINE') == '1'
        assert os.environ.get('TRANSFORMERS_OFFLINE') == '1'
        assert not any(os.environ.get(k) for k in ('XAI_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','GROK_API_KEY'))
        (root/'options.json').write_text(json.dumps({'options':options,'nltk_auto_download':'0'}))
        if mode == 'constructor-block': time.sleep(30)
    def extract_knowledge_graph(self, text):
        assert text == 'Ada notified HR.'
        (root/'submitted.json').write_text(json.dumps({'text_sha256':hashlib.sha256(text.encode()).hexdigest()}))
        if mode == 'call-inner-block':
            pid=os.fork()
            if pid == 0:
                (root/'inner.json').write_text(json.dumps({'pid':os.getpid(),'ticks':birth(os.getpid())}))
                time.sleep(30)
                os._exit(0)
            while not (root/'inner.json').exists(): time.sleep(.005)
            time.sleep(30)
        if mode == 'private-error': raise RuntimeError('synthetic-private-backend-secret-marker')
        if mode == 'network-denied': socket.create_connection(('127.0.0.1',9),timeout=.1)
        if mode == 'caught-network-denied':
            try: socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            except PermissionError: pass
        if mode == 'spawn-denied': subprocess.Popen([sys.executable,'-c','raise SystemExit(0)'])
        if mode == 'invalid': return SimpleNamespace(entities='invalid',relationships={})
        if mode == 'empty': return SimpleNamespace(entities={},relationships={})
        class Entity:
            entity_id='source-ada';entity_type='person';name='Ada';confidence=.9
            source_text=text;extraction_method='rule_based'
            @property
            def properties(self):
                if mode == 'serialization-block': time.sleep(30)
                if mode == 'output-limit': return {str(i):'x'*18000 for i in range(30)}
                return {}
        return SimpleNamespace(entities={'source-ada':Entity()},relationships={})
"""


@pytest.mark.parametrize("mode, diagnostic", [
    ("success", ""), ("empty", ""),
    ("import-block", "extractor_timeout"),
    ("constructor-block", "extractor_timeout"),
    ("call-inner-block", "extractor_timeout"),
    ("serialization-block", "extractor_timeout"),
    ("private-error", "extractor_error"),
    ("network-denied", "extractor_effect_denied"),
    ("caught-network-denied", "extractor_effect_denied"),
    ("spawn-denied", "extractor_effect_denied"),
    ("invalid", "extractor_invalid_result"),
    ("output-limit", "extractor_output_limit"),
])
def test_real_owned_extractor_bounds_import_call_serialization_and_reaps_inner_child(tmp_path, monkeypatch, mode, diagnostic):
    """Real current manager/call, fixed inert source package, no provider/network."""
    import concurrent.futures
    import hashlib
    import json
    import os
    from pathlib import Path
    import time
    from integrations.ipfs_datasets import graphs
    root = tmp_path / "extractor-owned-process"
    root.mkdir(mode=0o700)
    package = root / "ipfs_datasets_py" / "knowledge_graphs" / "extraction"
    package.mkdir(parents=True, mode=0o700)
    for directory in (package, package.parent, package.parent.parent):
        directory.chmod(0o700)
        path = directory / "__init__.py"
        path.write_text("")
        path.chmod(0o600)
    module = package / "extractor.py"
    module.write_text(PRIVATE_EXTRACTOR_FIXTURE_SOURCE)
    module.chmod(0o600)
    mode_file = root / "mode.json"
    mode_file.write_text(json.dumps({"mode": mode}))
    mode_file.chmod(0o600)
    before = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.py")}
    monkeypatch.setattr(graphs, "_private_extractor_roots", lambda: [str(root)])
    def no_threads(*_args, **_kwargs):
        raise AssertionError("An uncooperative extractor cannot use an abandoned thread")
    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", no_threads)
    text = "Ada notified HR."
    started = time.monotonic()
    result = extract_graph_from_text(text, source_id="message-private", metadata=_statement_context(text, extraction_timeout_seconds=.8))
    elapsed = time.monotonic() - started
    private = result["metadata"]["private_extraction"]
    assert elapsed < 4.0
    assert private["diagnostic"] == diagnostic
    assert private["bounded"] is True
    assert private["status"] == ("available" if diagnostic == "" else "degraded")
    assert "synthetic-private-backend-secret-marker" not in json.dumps(result)
    assert before == {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.py")}
    assert not list(root.rglob("__pycache__"))
    worker = json.loads((root / "worker.json").read_text())
    def same_birth(pid, ticks):
        try:
            value = Path('/proc/'+str(pid)+'/stat').read_text()
        except FileNotFoundError:
            return False
        fields = value[value.rfind(')')+2:].split()
        return int(fields[19]) == ticks
    assert not same_birth(worker['pid'], worker['ticks'])
    assert not same_birth(worker['manager_pid'], worker['manager_ticks'])
    if mode == 'call-inner-block':
        inner = json.loads((root / "inner.json").read_text())
        assert not same_birth(inner['pid'], inner['ticks'])
    if mode != 'import-block':
        options = json.loads((root / "options.json").read_text())
        assert options == {'options':graphs._PRIVATE_EXTRACTOR_OPTIONS,'nltk_auto_download':'0'}
    if mode not in {'import-block','constructor-block'}:
        assert json.loads((root/'submitted.json').read_text()) == {'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
    if mode == 'success':
        assert {item['name'] for item,_ in _asserted_upstream(result)} == {'Ada'}
    else:
        assert _asserted_upstream(result) == []
    assert not any(item['relation_type'] in {'supports','has_fact'} for item in result['relationships'])


@pytest.mark.parametrize("ack", [b'not-json synthetic-private-backend-secret-marker',
    b'{"outcome":"ok","payload":{"status":"ok","entities":[],"relationships":[]}}',
    b'{"outcome":"ok","cleanup_confirmed":false,"payload":{}}'])
def test_missing_or_malformed_cleanup_acknowledgement_is_not_a_bounded_success(tmp_path, monkeypatch, ack):
    import subprocess
    from integrations.ipfs_datasets import graphs
    class Manager:
        returncode = 0
        def communicate(self, *_args, **_kwargs): return ack, None
        def poll(self): return 0
    monkeypatch.setattr(graphs, '_private_extractor_roots', lambda: [str(tmp_path)])
    monkeypatch.setattr(subprocess, 'Popen', lambda *_args, **_kwargs: Manager())
    text = 'Ada notified HR.'
    result = extract_graph_from_text(text, source_id='message-private', metadata=_statement_context(text))
    private = result['metadata']['private_extraction']
    assert private['diagnostic'] == 'extractor_cleanup_unconfirmed'
    assert private['bounded'] is False
    assert private['status'] == 'degraded'
    assert _asserted_upstream(result) == []
    assert 'synthetic-private-backend-secret-marker' not in str(result)


def test_scripted_interview_keeps_fact_and_law_lineage_separate(tmp_path, monkeypatch):
    """User facts cite user turns. Applicable requirements cite admitted sources only."""
    from tests.test_question_saturation_contract import (
        application_level_interview_fixture,
        assert_scripted_interview_contract,
        scripted_turn,
    )

    session = application_level_interview_fixture(tmp_path, monkeypatch)
    assert_scripted_interview_contract(session)
    user_corpus = "\n".join(item["text"] for item in session["transcript"])
    final = session["turns"][-1]["observation"]
    sourced_facts = [fact for fact in final["facts"] if fact["source_id"]]
    assert sourced_facts
    assert {fact["source_id"] for fact in sourced_facts} >= {"msg-complete", "msg-correction", "msg-contradiction"}
    for fact in sourced_facts:
        assert fact["statement"] in user_corpus
        assert fact["source_hash"]
    applicable = [
        item for item in final["legal"]
        if item["dependency_class"] == "legally_sourced_requirement" and item["source_available"] is not False
    ]
    # A jurisdiction with no admitted source leaves no applicable requirement.
    during_rule = [
        item for item in scripted_turn(session, "rule_version")["observation"]["legal"]
        if item["dependency_class"] == "legally_sourced_requirement" and item["source_available"] is not False
    ]
    assert during_rule
    assert {item["source_hash"] for item in during_rule} <= session["admitted_source_hashes"]
    assert {item["source_hash"] for item in applicable} <= session["admitted_source_hashes"]
    assert all(item["verification_status"] not in {None, "", "heuristic", "unverified"} for item in applicable)
    gaps = [item for item in final["legal"] if item["dependency_class"] != "legally_sourced_requirement"]
    assert all(item["satisfied"] is False and item["law_derived"] is False for item in gaps)
