import logging

from mediator.integrations.graph_tools import GraphAwareRetrievalReranker


class _Mediator:
    def __init__(self, phase_manager):
        self.phase_manager = phase_manager


def test_knowledge_graph_failure_is_logged_and_other_graph_terms_remain(caplog):
    error = RuntimeError("knowledge graph provider unavailable")

    class _KnowledgeGraph:
        def get_entities_by_type(self, _entity_type):
            raise error

    class _DependencyNode:
        name = "Retaliation claim"
        description = "Termination after protected activity"

    class _DependencyGraph:
        def get_nodes_by_type(self, _node_type):
            return [_DependencyNode()]

    class _PhaseManager:
        def get_phase_data(self, _phase, key):
            if key == "knowledge_graph":
                return _KnowledgeGraph()
            if key == "dependency_graph":
                return _DependencyGraph()
            return None

    with caplog.at_level(logging.WARNING, logger="mediator.integrations.graph_tools"):
        terms = GraphAwareRetrievalReranker().extract_graph_terms(
            _Mediator(_PhaseManager())
        )

    assert terms == ["Retaliation claim", "Termination after protected activity"]
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "continuing with other graph sources" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[1] is error


def test_partial_knowledge_graph_terms_do_not_leak_after_failure(caplog):
    error = ValueError("malformed fact entity")

    class _Entity:
        name = "Partially extracted claim"
        attributes = {"detail": "Partially extracted detail"}

    class _KnowledgeGraph:
        def get_entities_by_type(self, entity_type):
            if entity_type == "claim":
                return [_Entity()]
            raise error

    class _PhaseManager:
        def get_phase_data(self, _phase, key):
            return _KnowledgeGraph() if key == "knowledge_graph" else None

    with caplog.at_level(logging.WARNING, logger="mediator.integrations.graph_tools"):
        terms = GraphAwareRetrievalReranker().extract_graph_terms(
            _Mediator(_PhaseManager())
        )

    assert terms == []
    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info is not None
    assert caplog.records[0].exc_info[1] is error
