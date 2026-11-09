import logging

from mediator.integrations.graph_tools import GraphAwareRetrievalReranker


class _Mediator:
    def __init__(self, phase_manager):
        self.phase_manager = phase_manager


def test_legal_graph_failure_is_logged_and_other_graph_terms_remain(caplog):
    error = RuntimeError("legal graph provider unavailable")

    class _DependencyNode:
        name = "Retaliation claim"
        description = "Termination after protected activity"

    class _DependencyGraph:
        def get_nodes_by_type(self, _node_type):
            return [_DependencyNode()]

    class _PhaseManager:
        def get_phase_data(self, _phase, key):
            if key == "dependency_graph":
                return _DependencyGraph()
            if key == "legal_graph":
                raise error
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


def test_partial_legal_graph_terms_do_not_leak_after_failure(caplog):
    error = ValueError("malformed legal element")

    class _ValidElement:
        name = "Partially extracted authority"
        description = "Partially extracted rule"

    class _InvalidName:
        def __str__(self):
            raise error

    class _InvalidElement:
        name = _InvalidName()
        description = "Unreachable description"

    class _LegalGraph:
        elements = {
            "valid": _ValidElement(),
            "invalid": _InvalidElement(),
        }

    class _PhaseManager:
        def get_phase_data(self, _phase, key):
            return _LegalGraph() if key == "legal_graph" else None

    with caplog.at_level(logging.WARNING, logger="mediator.integrations.graph_tools"):
        terms = GraphAwareRetrievalReranker().extract_graph_terms(
            _Mediator(_PhaseManager())
        )

    assert terms == []
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "continuing with other graph sources" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[1] is error
