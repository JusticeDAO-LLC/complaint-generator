import os
import json
import tempfile
from unittest.mock import Mock, patch

from mediator.integrations.graph_tools import GraphRetrievalAugmentor, GraphAwareRetrievalReranker


def test_graph_retrieval_augmentor_builds_payloads():
    augmentor = GraphRetrievalAugmentor()
    payloads = augmentor.build_evidence_payloads(
        legal_normalized=[{"title": "Title VII", "confidence": 0.9, "metadata": {"a": 1}}],
        web_normalized=[{"title": "EEOC Guidance", "confidence": 0.8, "metadata": {"b": 2}}],
        claim_ids=["claim_1"],
        max_items=5,
    )

    assert len(payloads) == 2
    assert payloads[0]["supports_claims"] == ["claim_1"]
    assert payloads[0]["source_type"] == "normalized_legal_authority"


def test_mediator_enrich_graphs_with_retrieval_artifacts_adds_evidence():
    from mediator import Mediator

    mock_backend = Mock()
    mock_backend.id = "test-backend"

    mediator = Mediator(backends=[mock_backend])
    mediator.start_three_phase_process("I was terminated after reporting discrimination.")
    mediator.phase_manager.update_phase_data(mediator.phase_manager.get_current_phase(), "remaining_gaps", 0)
    mediator.phase_manager.update_phase_data(mediator.phase_manager.get_current_phase(), "denoising_converged", True)
    mediator.advance_to_evidence_phase()

    mediator.state.last_legal_authorities_normalized = [
        {
            "title": "Title VII",
            "snippet": "Employment discrimination statute",
            "confidence": 0.9,
            "metadata": {"vector_augmented": True},
        }
    ]
    mediator.state.last_web_evidence_normalized = [
        {
            "title": "EEOC retaliation guidance",
            "snippet": "Federal guidance",
            "confidence": 0.8,
            "metadata": {"vector_augmented": True},
        }
    ]

    result = mediator.enrich_graphs_with_retrieval_artifacts(max_items=10)
    assert result["enriched"] is True
    assert result["added"] >= 1

    evidence_count = mediator.phase_manager.get_phase_data(
        mediator.phase_manager.get_current_phase(), "evidence_count"
    )
    assert isinstance(evidence_count, int)


def test_advance_to_evidence_phase_runs_graph_enrichment_when_enabled():
    from mediator import Mediator

    mock_backend = Mock()
    mock_backend.id = "test-backend"

    mediator = Mediator(backends=[mock_backend])
    mediator.start_three_phase_process("I was discriminated against by my employer.")
    mediator.phase_manager.update_phase_data(mediator.phase_manager.get_current_phase(), "remaining_gaps", 0)
    mediator.phase_manager.update_phase_data(mediator.phase_manager.get_current_phase(), "denoising_converged", True)

    mediator.state.last_legal_authorities_normalized = [
        {"title": "Title VII", "confidence": 0.9, "metadata": {}}
    ]

    with patch.dict(os.environ, {"IPFS_DATASETS_ENHANCED_GRAPH": "1"}, clear=False):
        result = mediator.advance_to_evidence_phase()

    assert "graph_enrichment" in result
    assert result["graph_enrichment"]["enriched"] is True


def test_graph_reranker_optimizer_mode_increases_effective_boost_budget():
    class _Entity:
        def __init__(self, name):
            self.name = name
            self.attributes = {}

    class _Node:
        def __init__(self, name):
            self.name = name
            self.description = ""

    class _DG:
        def get_nodes_by_type(self, _):
            return [_Node("retaliation")]

        def get_claim_readiness(self):
            return {
                "overall_readiness": 0.0,
                "incomplete_claim_details": [
                    {"claim_name": "employment discrimination retaliation"},
                ],
            }

        def find_unsatisfied_requirements(self):
            return [
                {
                    "node_name": "retaliation claim",
                    "missing_dependencies": [
                        {"source_name": "termination letter"},
                        {"source_name": "witness affidavit"},
                    ],
                }
            ]

    class _KG:
        def get_entities_by_type(self, entity_type):
            if entity_type == "claim":
                return [_Entity("employment discrimination")]
            return []

    class _PM:
        def get_phase_data(self, _phase, key=None):
            if key == "knowledge_graph":
                return _KG()
            if key == "dependency_graph":
                return _DG()
            return None

    class _Mediator:
        phase_manager = _PM()

    reranker = GraphAwareRetrievalReranker()
    base_records = [
        {
            "title": "Employment discrimination retaliation standards",
            "snippet": "Termination letter and witness affidavit relevance",
            "score": 0.30,
            "confidence": 0.30,
            "metadata": {},
        }
    ]

    without_optimizer = reranker.augment_normalized_records(
        records=base_records,
        query="claim requirements",
        mediator=_Mediator(),
        enable_optimizer=False,
    )
    with_optimizer = reranker.augment_normalized_records(
        records=base_records,
        query="claim requirements",
        mediator=_Mediator(),
        enable_optimizer=True,
    )

    assert without_optimizer[0]["metadata"].get("graph_optimizer_tuned") is False
    assert with_optimizer[0]["metadata"].get("graph_optimizer_tuned") is True
    assert with_optimizer[0]["metadata"].get("graph_effective_max_boost", 0) >= without_optimizer[0]["metadata"].get("graph_effective_max_boost", 0)
    assert with_optimizer[0]["score"] >= without_optimizer[0]["score"]


def test_graph_reranker_applies_latency_budget_guard():
    class _Entity:
        def __init__(self, name):
            self.name = name
            self.attributes = {}

    class _Node:
        def __init__(self, name):
            self.name = name
            self.description = ""

    class _DG:
        def get_nodes_by_type(self, _):
            return [_Node("retaliation")]

        def get_claim_readiness(self):
            return {
                "overall_readiness": 0.1,
                "incomplete_claim_details": [
                    {"claim_name": "employment discrimination retaliation"},
                ],
            }

        def find_unsatisfied_requirements(self):
            return [
                {
                    "node_name": "retaliation claim",
                    "missing_dependencies": [
                        {"source_name": "termination letter"},
                    ],
                }
            ]

    class _KG:
        def get_entities_by_type(self, entity_type):
            if entity_type == "claim":
                return [_Entity("employment discrimination")]
            return []

    class _PM:
        def get_phase_data(self, _phase, key=None):
            if key == "knowledge_graph":
                return _KG()
            if key == "dependency_graph":
                return _DG()
            return None

    class _Mediator:
        phase_manager = _PM()

    reranker = GraphAwareRetrievalReranker()
    records = [
        {
            "title": "Employment discrimination retaliation standards",
            "snippet": "Termination letter evidence",
            "score": 0.30,
            "confidence": 0.30,
            "metadata": {},
        }
    ]

    normal_budget = reranker.augment_normalized_records(
        records=records,
        query="claim requirements",
        mediator=_Mediator(),
        enable_optimizer=True,
        retrieval_max_latency_ms=1500,
    )
    tight_budget = reranker.augment_normalized_records(
        records=records,
        query="claim requirements",
        mediator=_Mediator(),
        enable_optimizer=True,
        retrieval_max_latency_ms=100,
    )

    assert tight_budget[0]["metadata"].get("graph_latency_guard_applied") is True
    assert tight_budget[0]["metadata"].get("graph_latency_budget_ms") == 100
    assert tight_budget[0]["metadata"].get("graph_effective_max_boost", 0) <= normal_budget[0]["metadata"].get("graph_effective_max_boost", 0)


def test_graph_reranker_canary_sampling_is_deterministic_and_bounded():
    reranker = GraphAwareRetrievalReranker()

    assert reranker.should_apply_canary(seed="abc", percent=0) is False
    assert reranker.should_apply_canary(seed="abc", percent=100) is True

    first = reranker.should_apply_canary(seed="stable-seed", percent=37)
    second = reranker.should_apply_canary(seed="stable-seed", percent=37)
    assert first is second


def test_mediator_reranker_metrics_aggregation_updates_state():
    from mediator import Mediator

    mock_backend = Mock()
    mock_backend.id = "test-backend"

    mediator = Mediator(backends=[mock_backend])

    mediator.update_reranker_metrics(
        source="legal_authority",
        applied=True,
        metadata={
            "graph_run_avg_boost": 0.08,
            "graph_run_elapsed_ms": 4.2,
            "graph_latency_guard_applied": True,
        },
        canary_enabled=True,
    )
    mediator.update_reranker_metrics(
        source="legal_authority",
        applied=False,
        metadata={},
        canary_enabled=False,
    )

    metrics = getattr(mediator.state, "reranker_metrics", {})
    assert metrics.get("total_runs") == 2
    assert metrics.get("applied_runs") == 1
    assert metrics.get("skipped_runs") == 1
    assert metrics.get("canary_enabled_runs") == 1
    assert metrics.get("latency_guard_runs") == 1

    source_metrics = metrics.get("by_source", {}).get("legal_authority", {})
    assert source_metrics.get("total_runs") == 2
    assert source_metrics.get("applied_runs") == 1
    assert source_metrics.get("skipped_runs") == 1


def test_mediator_get_reranker_metrics_defaults_and_status_snapshot():
    from mediator import Mediator

    mock_backend = Mock()
    mock_backend.id = "test-backend"

    mediator = Mediator(backends=[mock_backend])
    defaults = mediator.get_reranker_metrics()
    assert defaults.get("total_runs") == 0
    assert defaults.get("by_source") == {}
    assert isinstance(defaults.get("first_seen_at"), int)
    assert isinstance(defaults.get("last_updated_at"), int)
    assert isinstance(defaults.get("last_reset_at"), int)

    mediator.update_reranker_metrics(
        source="web_evidence",
        applied=True,
        metadata={
            "graph_run_avg_boost": 0.05,
            "graph_run_elapsed_ms": 3.0,
            "graph_latency_guard_applied": False,
        },
        canary_enabled=True,
    )

    status = mediator.get_three_phase_status()
    assert "reranking_metrics" in status
    snapshot = status["reranking_metrics"]
    assert snapshot.get("total_runs") == 1
    assert snapshot.get("applied_runs") == 1
    assert snapshot.get("by_source", {}).get("web_evidence", {}).get("total_runs") == 1
    assert isinstance(snapshot.get("last_updated_at"), int)


def test_mediator_reset_reranker_metrics_clears_state_snapshot():
    from mediator import Mediator

    mock_backend = Mock()
    mock_backend.id = "test-backend"

    mediator = Mediator(backends=[mock_backend])
    mediator.update_reranker_metrics(
        source="legal_corpus",
        applied=True,
        metadata={"graph_run_avg_boost": 0.03, "graph_run_elapsed_ms": 1.2},
        canary_enabled=True,
    )
    before_reset = mediator.get_reranker_metrics()
    assert mediator.get_reranker_metrics().get("total_runs") == 1

    mediator.reset_reranker_metrics()
    reset_metrics = mediator.get_reranker_metrics()
    assert reset_metrics.get("total_runs") == 0
    assert reset_metrics.get("applied_runs") == 0
    assert reset_metrics.get("by_source") == {}
    assert reset_metrics.get("last_reset_at") >= before_reset.get("first_seen_at")


def test_mediator_reranker_metrics_window_rollover_resets_counts():
    from mediator import Mediator

    mock_backend = Mock()
    mock_backend.id = "test-backend"

    mediator = Mediator(backends=[mock_backend])

    mediator.update_reranker_metrics(
        source="legal_authority",
        applied=True,
        metadata={"graph_run_avg_boost": 0.02, "graph_run_elapsed_ms": 1.0},
        canary_enabled=True,
        window_size=2,
    )
    mediator.update_reranker_metrics(
        source="legal_authority",
        applied=False,
        metadata={},
        canary_enabled=False,
        window_size=2,
    )

    snapshot_before_roll = mediator.get_reranker_metrics()
    assert snapshot_before_roll.get("total_runs") == 2

    mediator.update_reranker_metrics(
        source="legal_authority",
        applied=True,
        metadata={"graph_run_avg_boost": 0.05, "graph_run_elapsed_ms": 2.0},
        canary_enabled=True,
        window_size=2,
    )

    snapshot_after_roll = mediator.get_reranker_metrics()
    assert snapshot_after_roll.get("total_runs") == 1
    assert snapshot_after_roll.get("applied_runs") == 1
    assert getattr(mediator.state, "reranker_metrics_window_resets", 0) >= 1


def test_mediator_export_reranker_metrics_json_writes_snapshot_file():
    from mediator import Mediator

    mock_backend = Mock()
    mock_backend.id = "test-backend"

    mediator = Mediator(backends=[mock_backend])
    mediator.update_reranker_metrics(
        source="web_evidence",
        applied=True,
        metadata={
            "graph_run_avg_boost": 0.06,
            "graph_run_elapsed_ms": 2.5,
        },
        canary_enabled=True,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = os.path.join(temp_dir, "reranker_metrics.json")
        written_path = mediator.export_reranker_metrics_json(output_path)

        assert written_path == output_path
        assert os.path.exists(written_path)

        with open(written_path, "r") as handle:
            payload = json.load(handle)

        assert isinstance(payload.get("exported_at"), int)
        assert payload.get("metrics", {}).get("total_runs") == 1
        assert payload.get("metrics", {}).get("by_source", {}).get("web_evidence", {}).get("applied_runs") == 1
