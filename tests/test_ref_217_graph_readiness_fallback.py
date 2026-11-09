import logging

from mediator.integrations.graph_tools import GraphAwareRetrievalReranker


class _Mediator:
    def __init__(self, dependency_graph):
        class _PhaseManager:
            def get_phase_data(self, _phase, key):
                assert key == "dependency_graph"
                return dependency_graph

        self.phase_manager = _PhaseManager()


def test_readiness_failure_is_logged_and_uses_neutral_fallback(caplog):
    error = RuntimeError("readiness service unavailable")

    class _DependencyGraph:
        def get_claim_readiness(self):
            raise error

        def find_unsatisfied_requirements(self):
            return [{"node_name": "Retaliation", "missing_dependencies": []}]

    with caplog.at_level(logging.WARNING, logger="mediator.integrations.graph_tools"):
        context = GraphAwareRetrievalReranker()._extract_readiness_context(
            _Mediator(_DependencyGraph())
        )

    assert context == {
        "overall_readiness": 1.0,
        "priority_terms": ["Retaliation"],
    }
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "using neutral readiness defaults" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[1] is error


def test_invalid_partial_readiness_does_not_leak_into_fallback(caplog):
    class _DependencyGraph:
        def get_claim_readiness(self):
            return {
                "overall_readiness": 0.2,
                "incomplete_claim_details": [
                    {"claim_name": "Valid claim"},
                    {"claim_name": object()},
                ],
            }

        def find_unsatisfied_requirements(self):
            return []

    # Force conversion of the second name to fail after the first name was parsed.
    class _BadName:
        def __str__(self):
            raise ValueError("invalid claim name")

    dependency_graph = _DependencyGraph()
    readiness = dependency_graph.get_claim_readiness()
    readiness["incomplete_claim_details"][1]["claim_name"] = _BadName()
    dependency_graph.get_claim_readiness = lambda: readiness

    with caplog.at_level(logging.WARNING, logger="mediator.integrations.graph_tools"):
        context = GraphAwareRetrievalReranker()._extract_readiness_context(
            _Mediator(dependency_graph)
        )

    assert context == {"overall_readiness": 1.0, "priority_terms": []}
    assert len(caplog.records) == 1
