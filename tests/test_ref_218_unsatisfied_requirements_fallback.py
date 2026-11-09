import logging

from mediator.integrations.graph_tools import GraphAwareRetrievalReranker


class _Mediator:
    def __init__(self, dependency_graph):
        class _PhaseManager:
            def get_phase_data(self, _phase, key):
                assert key == "dependency_graph"
                return dependency_graph

        self.phase_manager = _PhaseManager()


def test_requirement_failure_is_logged_and_keeps_readiness_context(caplog):
    error = RuntimeError("requirement traversal unavailable")

    class _DependencyGraph:
        def get_claim_readiness(self):
            return {
                "overall_readiness": 0.25,
                "incomplete_claim_details": [{"claim_name": "Retaliation"}],
            }

        def find_unsatisfied_requirements(self):
            raise error

    with caplog.at_level(logging.WARNING, logger="mediator.integrations.graph_tools"):
        context = GraphAwareRetrievalReranker()._extract_readiness_context(
            _Mediator(_DependencyGraph())
        )

    assert context == {
        "overall_readiness": 0.25,
        "priority_terms": ["Retaliation"],
    }
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "continuing without requirement priority terms" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[1] is error


def test_invalid_partial_requirements_do_not_leak_into_fallback(caplog):
    class _BadSourceName:
        def __str__(self):
            raise ValueError("invalid source name")

    class _DependencyGraph:
        def get_claim_readiness(self):
            return {
                "overall_readiness": 0.5,
                "incomplete_claim_details": [{"claim_name": "Valid readiness term"}],
            }

        def find_unsatisfied_requirements(self):
            return [
                {
                    "node_name": "Partially parsed requirement",
                    "missing_dependencies": [
                        {"source_name": "Valid source"},
                        {"source_name": _BadSourceName()},
                    ],
                }
            ]

    with caplog.at_level(logging.WARNING, logger="mediator.integrations.graph_tools"):
        context = GraphAwareRetrievalReranker()._extract_readiness_context(
            _Mediator(_DependencyGraph())
        )

    assert context == {
        "overall_readiness": 0.5,
        "priority_terms": ["Valid readiness term"],
    }
    assert len(caplog.records) == 1
    assert (
        "continuing without requirement priority terms"
        in caplog.records[0].getMessage()
    )
