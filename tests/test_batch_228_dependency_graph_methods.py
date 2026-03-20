"""
Unit tests for Batch 228: DependencyGraph analysis methods.
"""

import pytest

from complaint_phases.dependency_graph import (
    DependencyGraph,
    DependencyGraphBuilder,
    DependencyNode,
    Dependency,
    NodeType,
    DependencyType,
)


@pytest.fixture
def graph():
    return DependencyGraph()


def create_node(
    node_id,
    node_type=NodeType.CLAIM,
    name="Node",
    description="",
    satisfied=False,
    confidence=0.0,
):
    return DependencyNode(
        id=node_id,
        node_type=node_type,
        name=name,
        description=description,
        satisfied=satisfied,
        confidence=confidence,
    )


def create_dependency(
    dep_id,
    source_id,
    target_id,
    dep_type=DependencyType.REQUIRES,
    required=True,
    strength=1.0,
):
    return Dependency(
        id=dep_id,
        source_id=source_id,
        target_id=target_id,
        dependency_type=dep_type,
        required=required,
        strength=strength,
    )


class TestConfidenceThresholds:
    def test_nodes_with_confidence_above_below(self, graph):
        graph.add_node(create_node("n1", confidence=0.2))
        graph.add_node(create_node("n2", confidence=0.8))
        graph.add_node(create_node("n3", confidence=0.5))

        assert graph.nodes_with_confidence_above(0.6) == 1
        assert graph.nodes_with_confidence_below(0.3) == 1


class TestDependencyStrengthRanges:
    def test_strength_ranges_empty(self, graph):
        assert graph.dependency_strength_range() == 0.0
        assert graph.dependency_strength_range_required() == 0.0
        assert graph.dependency_strength_range_optional() == 0.0
        assert graph.dependency_strength_median() == 0.0

    def test_strength_ranges(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_dependency(create_dependency("d1", "n1", "n2", required=True, strength=0.2))
        graph.add_dependency(create_dependency("d2", "n2", "n1", required=True, strength=0.8))
        graph.add_dependency(create_dependency("d3", "n1", "n2", required=False, strength=0.4))

        assert graph.dependency_strength_range() == pytest.approx(0.6)
        assert graph.dependency_strength_range_required() == pytest.approx(0.6)
        assert graph.dependency_strength_range_optional() == pytest.approx(0.0)
        assert graph.dependency_strength_median() == pytest.approx(0.4)


class TestAverageDependenciesByType:
    def test_average_dependencies_per_claim_node(self, graph):
        graph.add_node(create_node("c1", node_type=NodeType.CLAIM))
        graph.add_node(create_node("c2", node_type=NodeType.CLAIM))
        graph.add_node(create_node("e1", node_type=NodeType.EVIDENCE))
        graph.add_dependency(create_dependency("d1", "c1", "e1"))
        graph.add_dependency(create_dependency("d2", "c2", "e1"))

        assert graph.average_dependencies_per_claim_node() == pytest.approx(1.0)
        assert graph.average_dependencies_per_evidence_node() == pytest.approx(2.0)

    def test_average_dependencies_per_requirement_node_empty(self, graph):
        assert graph.average_dependencies_per_requirement_node() == 0.0


class TestNodeTypeDistributionForSatisfaction:
    def test_distribution_for_satisfied(self, graph):
        graph.add_node(create_node("c1", node_type=NodeType.CLAIM, satisfied=True))
        graph.add_node(create_node("e1", node_type=NodeType.EVIDENCE, satisfied=True))
        graph.add_node(create_node("r1", node_type=NodeType.REQUIREMENT, satisfied=False))

        satisfied = graph.node_type_distribution_for_satisfaction(True)
        unsatisfied = graph.node_type_distribution_for_satisfaction(False)

        assert satisfied == {"claim": 1, "evidence": 1}
        assert unsatisfied == {"requirement": 1}


class TestBuildFromClaimsHeuristics:
    def test_retaliation_notice_and_hearing_claim_adds_fact_dependencies(self):
        builder = DependencyGraphBuilder()

        graph = builder.build_from_claims(
            [
                {
                    "name": "Retaliation",
                    "type": "retaliation",
                    "description": "They sent a denial notice and blocked my hearing request.",
                }
            ],
            {},
        )

        fact_names = {node.name for node in graph.nodes.values() if node.node_type == NodeType.FACT}

        assert "Timeline of events" in fact_names
        assert "Responsible party" in fact_names
        assert "Protected activity facts" in fact_names
        assert "Adverse action facts" in fact_names
        assert "Retaliation causation chronology" in fact_names
        assert "Written notice date" in fact_names
        assert "Hearing request date" in fact_names
