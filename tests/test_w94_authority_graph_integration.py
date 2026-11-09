"""Tests for W9.4: Authority graph and review integration.

Covers:
  - LegalGraphBuilder.build_from_authorities() with treatment edges
  - Authority-to-rule and rule-to-claim-element edges
  - Mediator _is_authority_treatment_weak_follow_up() helper
  - follow_up_focus = 'confirm_good_law' / 'find_better_authority'
  - claim_support_review confirm_good_law_task_count / find_better_authority_task_count
"""

from __future__ import annotations

from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# LegalGraph authority-treatment helpers
# ---------------------------------------------------------------------------

def _build_authority_graph(authorities, claim_elements=None):
    from complaint_phases.legal_graph import LegalGraphBuilder
    builder = LegalGraphBuilder()
    return builder.build_from_authorities(authorities, claim_elements=claim_elements)


def test_build_from_authorities_empty():
    graph = _build_authority_graph([])
    assert graph.total_elements() == 0
    assert graph.total_relations() == 0


def test_build_from_authorities_creates_authority_source_elements():
    authorities = [
        {"authority_id": "A1", "name": "Title VII", "citation": "42 U.S.C. § 2000e"},
        {"authority_id": "A2", "name": "McDonnell Douglas Corp. v. Green"},
    ]
    graph = _build_authority_graph(authorities)
    authority_nodes = graph.get_elements_by_type("authority_source")
    assert len(authority_nodes) == 2
    names = {n.name for n in authority_nodes}
    assert "Title VII" in names
    assert "McDonnell Douglas Corp. v. Green" in names


def test_build_from_authorities_preserves_citation_jurisdiction():
    authorities = [
        {
            "authority_id": "A1",
            "name": "Title VII",
            "citation": "42 U.S.C. § 2000e",
            "jurisdiction": "federal",
        }
    ]
    graph = _build_authority_graph(authorities)
    nodes = graph.get_elements_by_type("authority_source")
    assert len(nodes) == 1
    assert nodes[0].citation == "42 U.S.C. § 2000e"
    assert nodes[0].jurisdiction == "federal"


def test_treatment_edges_added_between_authorities():
    """An authority that cites treatment of another authority gets a treatment edge."""
    authorities = [
        {
            "authority_id": "A1",
            "name": "Reeves v. Sanderson",
            "treatment_records": [
                {
                    "treatment_type": "limits",
                    "treated_authority_id": "A2",
                    "treatment_confidence": 0.8,
                    "treatment_explanation": "limits McDonnell Douglas to pretext stage",
                }
            ],
        },
        {"authority_id": "A2", "name": "McDonnell Douglas"},
    ]
    graph = _build_authority_graph(authorities)
    relations = [r for r in graph.relations.values() if r.relation_type == "limits"]
    assert len(relations) == 1
    rel = relations[0]
    assert float(rel.attributes.get("confidence", 0)) == 0.8


def test_treatment_edge_types_accepted():
    """All valid treatment types create edges; invalid types are skipped."""
    valid_types = [
        "supports", "adverse", "limits", "distinguishes",
        "questioned", "superseded", "good_law_unconfirmed",
    ]
    authority_a = {"authority_id": "SRC", "name": "Source Authority"}
    authority_b = {"authority_id": "TGT", "name": "Target Authority"}
    treatment_records = [
        {"treatment_type": t, "treated_authority_id": "TGT"}
        for t in valid_types
    ]
    treatment_records.append({"treatment_type": "unknown_type", "treated_authority_id": "TGT"})
    authority_a["treatment_records"] = treatment_records
    graph = _build_authority_graph([authority_a, authority_b])
    relation_types = {r.relation_type for r in graph.relations.values()}
    for t in valid_types:
        assert t in relation_types, f"Expected relation type '{t}' not found"
    assert "unknown_type" not in relation_types


def test_treatment_edges_accept_persisted_treated_by_alias():
    authority_a = {"authority_id": "A", "name": "Source Authority"}
    authority_b = {"authority_id": "B", "name": "Target Authority"}
    authority_a["treatment_records"] = [
        {"treatment_type": "questioned", "treated_by_authority_id": "B"}
    ]

    graph = _build_authority_graph([authority_a, authority_b])
    relations = [r for r in graph.relations.values() if r.relation_type == "questioned"]

    assert len(relations) == 1
    assert relations[0].source_id != relations[0].target_id


def test_authority_treatment_edges_preserve_graph_ready_direction():
    current_authority = {
        "authority_id": "authority:current-case",
        "name": "Current Case",
        "authority_treatment_edges": [
            {
                "edge_id": "treatment:later-current",
                "source_authority_id": "authority:later-case",
                "target_authority_id": "authority:current-case",
                "relation_type": "questioned",
                "confidence": 0.82,
                "source_citation": "Later v. Current, 456 F.4th 789",
                "target_citation": "Current v. Earlier, 123 F.3d 456",
                "treatment_source": "later_case_search",
                "treatment_date": "2025-02-14",
                "explanation": "Later authority questioned the earlier rule.",
                "metadata": {"program_type": "treatment_check_search"},
            }
        ],
        "treatment_records": [
            {
                "treatment_id": "treatment:later-current",
                "treatment_type": "questioned",
                "treated_by_authority_id": "authority:later-case",
                "treatment_confidence": 0.82,
            }
        ],
    }
    later_authority = {
        "authority_id": "authority:later-case",
        "name": "Later Case",
    }

    graph = _build_authority_graph([current_authority, later_authority])
    relations = [r for r in graph.relations.values() if r.relation_type == "questioned"]
    authority_nodes = {
        node.attributes["source_authority_id"]: node
        for node in graph.get_elements_by_type("authority_source")
    }

    assert len(relations) == 1
    assert relations[0].source_id == authority_nodes["authority:later-case"].id
    assert relations[0].target_id == authority_nodes["authority:current-case"].id
    assert relations[0].attributes["source_authority_id"] == "authority:later-case"
    assert relations[0].attributes["target_authority_id"] == "authority:current-case"
    assert relations[0].attributes["treatment_id"] == "treatment:later-current"
    assert relations[0].attributes["metadata"]["program_type"] == "treatment_check_search"


def test_authority_treatment_edges_resolve_authority_prefixed_id_aliases():
    authorities = [
        {
            "id": 7,
            "name": "Stored Current Case",
            "authority_treatment_edges": [
                {
                    "source_authority_id": "authority:8",
                    "target_authority_id": "authority:7",
                    "relation_type": "limits",
                    "confidence": 0.7,
                }
            ],
        },
        {"id": 8, "name": "Stored Later Case"},
    ]

    graph = _build_authority_graph(authorities)
    relations = [r for r in graph.relations.values() if r.relation_type == "limits"]

    assert len(relations) == 1
    assert float(relations[0].attributes["confidence"]) == 0.7


def test_treatment_edges_skip_missing_target():
    """Treatment records referencing unknown authority IDs are silently skipped."""
    authority = {
        "authority_id": "A1",
        "name": "Authority One",
        "treatment_records": [
            {"treatment_type": "superseded", "treated_authority_id": "NONEXISTENT"}
        ],
    }
    graph = _build_authority_graph([authority])
    assert graph.total_relations() == 0


def test_rule_candidates_create_rule_candidate_elements():
    authority = {
        "authority_id": "A1",
        "name": "Title VII",
        "rule_candidates": [
            {
                "rule_text": "Employer shall not discriminate on basis of race",
                "rule_type": "obligation",
                "extraction_confidence": 0.9,
                "grounded_rule": {
                    "deontic_operator": "obligation",
                    "operator_family": "affirmative_duty",
                    "grounding_status": "grounded",
                },
            }
        ],
    }
    graph = _build_authority_graph([authority])
    rule_nodes = graph.get_elements_by_type("rule_candidate")
    assert len(rule_nodes) == 1
    assert rule_nodes[0].attributes.get("rule_type") == "obligation"
    assert rule_nodes[0].attributes.get("deontic_operator") == "obligation"
    assert rule_nodes[0].attributes.get("operator_family") == "affirmative_duty"


def test_rule_candidate_extracted_from_edge():
    """A rule candidate node has an extracted_from edge pointing to its authority.

    The edge models 'rule extracted_from authority', so source=rule, target=authority.
    """
    authority = {
        "authority_id": "A1",
        "name": "Title VII",
        "rule_candidates": [
            {"rule_text": "Protected class prohibition", "rule_type": "obligation"}
        ],
    }
    graph = _build_authority_graph([authority])
    extracted_rels = [r for r in graph.relations.values() if r.relation_type == "extracted_from"]
    assert len(extracted_rels) == 1
    rule_nodes = graph.get_elements_by_type("rule_candidate")
    authority_nodes = graph.get_elements_by_type("authority_source")
    rel = extracted_rels[0]
    assert rel.source_id == rule_nodes[0].id
    assert rel.target_id == authority_nodes[0].id


def test_rule_candidate_governs_claim_element():
    """When rule candidate claim_element_id matches, a governs edge is added."""
    authorities = [
        {
            "authority_id": "A1",
            "name": "Title VII",
            "rule_candidates": [
                {
                    "rule_text": "Protected class prohibition",
                    "rule_type": "obligation",
                    "claim_element_id": "elem_protected_class",
                }
            ],
        }
    ]
    claim_elements = [
        {
            "element_id": "elem_protected_class",
            "element_text": "Membership in protected class",
        }
    ]
    graph = _build_authority_graph(authorities, claim_elements=claim_elements)
    governs_rels = [r for r in graph.relations.values() if r.relation_type == "governs"]
    assert len(governs_rels) == 1
    elem_nodes = graph.get_elements_by_type("claim_element")
    assert governs_rels[0].target_id == elem_nodes[0].id


def test_rule_candidate_no_governs_when_no_match():
    """When claim_element_id does not match any claim element, no governs edge is added."""
    authorities = [
        {
            "authority_id": "A1",
            "name": "Title VII",
            "rule_candidates": [
                {
                    "rule_text": "Protected class prohibition",
                    "claim_element_id": "elem_nonexistent",
                }
            ],
        }
    ]
    claim_elements = [{"element_id": "elem_other", "element_text": "Some other element"}]
    graph = _build_authority_graph(authorities, claim_elements=claim_elements)
    governs_rels = [r for r in graph.relations.values() if r.relation_type == "governs"]
    assert len(governs_rels) == 0


def test_claim_elements_create_nodes():
    claim_elements = [
        {"element_id": "e1", "element_text": "Protected class membership"},
        {"element_id": "e2", "element_text": "Adverse employment action"},
    ]
    graph = _build_authority_graph([], claim_elements=claim_elements)
    elem_nodes = graph.get_elements_by_type("claim_element")
    assert len(elem_nodes) == 2


def test_build_from_authorities_graph_summary():
    authorities = [
        {"authority_id": "A1", "name": "Authority 1"},
        {"authority_id": "A2", "name": "Authority 2"},
    ]
    graph = _build_authority_graph(authorities)
    summary = graph.summary()
    assert summary["total_elements"] == 2
    assert "authority_source" in summary["element_types"]


# ---------------------------------------------------------------------------
# Mediator _is_authority_treatment_weak_follow_up helper
# ---------------------------------------------------------------------------

def _make_mediator():
    """Create a minimal Mediator instance without a real DB."""
    from unittest.mock import MagicMock
    from mediator.mediator import Mediator
    backends = MagicMock()
    m = Mediator.__new__(Mediator)
    m.backends = backends
    m.state = MagicMock()
    m.claim_support = MagicMock()
    m.mediator = m
    return m


def test_is_authority_treatment_weak_confirm_good_law():
    m = _make_mediator()
    treatment_summary = {
        "supportive_authority_link_count": 2,
        "adverse_authority_link_count": 0,
        "uncertain_authority_link_count": 1,
        "treatment_type_counts": {"good_law_unconfirmed": 2},
    }
    result = m._is_authority_treatment_weak_follow_up(treatment_summary)
    assert result == "confirm_good_law"


def test_is_authority_treatment_weak_find_better_authority():
    m = _make_mediator()
    treatment_summary = {
        "supportive_authority_link_count": 2,
        "adverse_authority_link_count": 0,
        "uncertain_authority_link_count": 0,
        "treatment_type_counts": {"limits": 1, "distinguishes": 1},
    }
    result = m._is_authority_treatment_weak_follow_up(treatment_summary)
    assert result == "find_better_authority"


def test_is_authority_treatment_weak_no_signal_on_adverse():
    """When adverse authority exists, _is_authority_treatment_weak should NOT fire
    (adverse_authority_review takes priority via recommended_action)."""
    m = _make_mediator()
    treatment_summary = {
        "supportive_authority_link_count": 1,
        "adverse_authority_link_count": 2,
        "uncertain_authority_link_count": 0,
        "treatment_type_counts": {"adverse": 2, "good_law_unconfirmed": 1},
    }
    result = m._is_authority_treatment_weak_follow_up(treatment_summary)
    assert result == ""


def test_is_authority_treatment_weak_no_signal_when_no_support():
    m = _make_mediator()
    treatment_summary = {
        "supportive_authority_link_count": 0,
        "adverse_authority_link_count": 0,
        "uncertain_authority_link_count": 0,
        "treatment_type_counts": {},
    }
    result = m._is_authority_treatment_weak_follow_up(treatment_summary)
    assert result == ""


def test_is_authority_treatment_weak_empty_summary():
    m = _make_mediator()
    assert m._is_authority_treatment_weak_follow_up({}) == ""
    assert m._is_authority_treatment_weak_follow_up(None) == ""


# ---------------------------------------------------------------------------
# Mediator _manual_review_skip_reason for new focus values
# ---------------------------------------------------------------------------

def test_manual_review_skip_reason_confirm_good_law():
    m = _make_mediator()
    task = {"follow_up_focus": "confirm_good_law"}
    assert m._manual_review_skip_reason(task) == "authority_good_law_status_unconfirmed"


def test_manual_review_skip_reason_find_better_authority():
    m = _make_mediator()
    task = {"follow_up_focus": "find_better_authority"}
    assert m._manual_review_skip_reason(task) == "authority_support_limited_by_treatment"


# ---------------------------------------------------------------------------
# Mediator _should_suppress_follow_up_task exemptions
# ---------------------------------------------------------------------------

def test_should_suppress_exempts_confirm_good_law():
    m = _make_mediator()
    task = {"follow_up_focus": "confirm_good_law"}
    result = m._should_suppress_follow_up_task(task)
    assert result["suppress"] is False


def test_should_suppress_exempts_find_better_authority():
    m = _make_mediator()
    task = {"follow_up_focus": "find_better_authority"}
    result = m._should_suppress_follow_up_task(task)
    assert result["suppress"] is False


# ---------------------------------------------------------------------------
# Mediator _resolved_manual_review_gap_types
# ---------------------------------------------------------------------------

def test_resolved_gap_types_confirm_good_law():
    m = _make_mediator()
    task = {"follow_up_focus": "confirm_good_law"}
    assert "authority_treatment_weak" in m._resolved_manual_review_gap_types(task)


def test_resolved_gap_types_find_better_authority():
    m = _make_mediator()
    task = {"follow_up_focus": "find_better_authority"}
    assert "authority_treatment_weak" in m._resolved_manual_review_gap_types(task)


# ---------------------------------------------------------------------------
# claim_support_review aggregate counts
# ---------------------------------------------------------------------------

def test_claim_support_review_confirm_good_law_task_count():
    from claim_support_review import _summarize_follow_up_plan_claim
    tasks = [
        {"follow_up_focus": "confirm_good_law", "status": "missing", "claim_element": "elem"},
        {"follow_up_focus": "confirm_good_law", "status": "missing", "claim_element": "elem2"},
        {"follow_up_focus": "adverse_authority_review", "status": "missing", "claim_element": "elem3"},
    ]
    plan_claim = {"tasks": tasks, "skipped_tasks": []}
    summary = _summarize_follow_up_plan_claim(plan_claim)
    assert summary["confirm_good_law_task_count"] == 2
    assert summary["find_better_authority_task_count"] == 0
    assert summary["adverse_authority_task_count"] == 1


def test_claim_support_review_find_better_authority_task_count():
    from claim_support_review import _summarize_follow_up_plan_claim
    tasks = [
        {"follow_up_focus": "find_better_authority", "status": "partially_supported", "claim_element": "elem"},
    ]
    plan_claim = {"tasks": tasks, "skipped_tasks": []}
    summary = _summarize_follow_up_plan_claim(plan_claim)
    assert summary["find_better_authority_task_count"] == 1
    assert summary["confirm_good_law_task_count"] == 0


def test_claim_support_review_execution_confirm_good_law_count():
    from claim_support_review import _summarize_follow_up_execution_claim
    executed = [
        {"follow_up_focus": "confirm_good_law", "claim_element": "elem"},
        {"follow_up_focus": "find_better_authority", "claim_element": "elem2"},
    ]
    execution_claim = {"tasks": executed, "skipped_tasks": []}
    summary = _summarize_follow_up_execution_claim(execution_claim)
    assert summary["confirm_good_law_task_count"] == 1
    assert summary["find_better_authority_task_count"] == 1
