import logging

from mediator.integrations.graph_tools import GraphAwareRetrievalReranker


class _Entity:
    name = "Preserved knowledge-graph term"
    attributes = {}


class _KnowledgeGraph:
    def get_entities_by_type(self, entity_type):
        return [_Entity()] if entity_type == "claim" else []


class _Mediator:
    def __init__(self, dependency_graph):
        class _PhaseManager:
            def get_phase_data(self, _phase, key):
                if key == "knowledge_graph":
                    return _KnowledgeGraph()
                if key == "dependency_graph":
                    return dependency_graph
                if key == "legal_graph":
                    return None
                raise AssertionError(f"unexpected graph key: {key}")

        self.phase_manager = _PhaseManager()


def test_dependency_graph_failure_is_logged_and_keeps_other_graph_terms(caplog):
    error = RuntimeError("dependency graph unavailable")

    class _DependencyGraph:
        def get_nodes_by_type(self, _node_type):
            raise error

    with caplog.at_level(logging.WARNING, logger="mediator.integrations.graph_tools"):
        terms = GraphAwareRetrievalReranker().extract_graph_terms(
            _Mediator(_DependencyGraph())
        )

    assert terms == ["Preserved knowledge-graph term"]
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "continuing without dependency-graph terms" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[1] is error


def test_invalid_partial_dependency_graph_terms_do_not_leak_into_fallback(caplog):
    class _BadName:
        def __str__(self):
            raise ValueError("invalid dependency node name")

    class _Node:
        def __init__(self, name, description=""):
            self.name = name
            self.description = description

    class _DependencyGraph:
        def get_nodes_by_type(self, _node_type):
            return [
                _Node("Partially parsed dependency term", "Partial description"),
                _Node(_BadName()),
            ]

    with caplog.at_level(logging.WARNING, logger="mediator.integrations.graph_tools"):
        terms = GraphAwareRetrievalReranker().extract_graph_terms(
            _Mediator(_DependencyGraph())
        )

    assert terms == ["Preserved knowledge-graph term"]
    assert len(caplog.records) == 1
    assert "continuing without dependency-graph terms" in caplog.records[0].getMessage()
