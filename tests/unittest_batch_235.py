"""Batch 235 Metrics Tests: score_acceleration_trend, score_dimension_std, relationship_density."""

import pytest
from dataclasses import dataclass
from typing import Any, Optional

# Import the classes we're testing
from ipfs_datasets_py.optimizers.graphrag.ontology_optimizer import OntologyOptimizer
from ipfs_datasets_py.optimizers.graphrag.ontology_critic import OntologyCritic
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import OntologyGenerator


# Mark all tests as unit tests (not LLM-gated)
pytestmark = pytest.mark.unit


@dataclass
class _FakeEntry:
    """Fake history entry with average_score."""
    average_score: float


@dataclass
class _FakeCriticScore:
    """Fake CriticScore for testing."""
    completeness: float = 0.0
    consistency: float = 0.0
    clarity: float = 0.0
    granularity: float = 0.0
    relationship_coherence: float = 0.0
    domain_alignment: float = 0.0


@dataclass
class _FakeEntity:
    """Fake entity for relationship_density tests."""
    id: str
    name: str


@dataclass
class _FakeRelationship:
    """Fake relationship."""
    source_id: str
    target_id: str
    type: str


@dataclass
class _FakeExtractionResult:
    """Fake EntityExtractionResult."""
    entities: Optional[list] = None
    relationships: Optional[list] = None


def _make_opt(**kwargs) -> OntologyOptimizer:
    """Create a mock OntologyOptimizer with given history."""
    opt = OntologyOptimizer(enable_tracing=False)
    opt._history = [_FakeEntry(average_score=score) for score in kwargs.get('scores', [])]
    return opt


def _cs(**kwargs) -> _FakeCriticScore:
    """Create a fake CriticScore with given dimension values."""
    return _FakeCriticScore(**kwargs)


# ============================================================================
# Tests for score_acceleration_trend
# ============================================================================

class TestScoreAccelerationTrend:
    """Test OntologyOptimizer.score_acceleration_trend()."""

    def test_empty_history(self):
        """Empty history should return 0.0."""
        opt = _make_opt(scores=[])
        assert opt.score_acceleration_trend() == 0.0

    def test_single_entry(self):
        """Single entry should return 0.0."""
        opt = _make_opt(scores=[0.5])
        assert opt.score_acceleration_trend() == 0.0

    def test_two_entries(self):
        """Two entries should return 0.0."""
        opt = _make_opt(scores=[0.1, 0.2])
        assert opt.score_acceleration_trend() == 0.0

    def test_three_entries(self):
        """Three entries should return 0.0."""
        opt = _make_opt(scores=[0.1, 0.2, 0.3])
        assert opt.score_acceleration_trend() == 0.0

    def test_increasing_acceleration(self):
        """Increasing acceleration (e.g., acceleration is positive trend)."""
        # Scores: 0, 1, 3, 6 → diffs: 1, 2, 3 → 2nd: 1, 1 → 3rd: 0 (constant)
        # Try: 0, 1, 3, 7 → diffs: 1, 2, 4 → 2nd: 1, 2 → 3rd: 1 (positive)
        opt = _make_opt(scores=[0.0, 1.0, 3.0, 7.0])
        result = opt.score_acceleration_trend()
        assert result == 1.0

    def test_decreasing_acceleration(self):
        """Decreasing acceleration."""
        # Scores: 0, 4, 7, 9 → diffs: 4, 3, 2 → 2nd: -1, -1 → 3rd: 0
        # Try: 0, 4, 7, 8 → diffs: 4, 3, 1 → 2nd: -1, -2 → 3rd: -1 (negative)
        opt = _make_opt(scores=[0.0, 4.0, 7.0, 8.0])
        result = opt.score_acceleration_trend()
        assert result == -1.0

    def test_constant_acceleration(self):
        """Constant acceleration (third derivative is 0)."""
        opt = _make_opt(scores=[0.0, 1.0, 3.0, 6.0])
        # diffs: 1, 2, 3 → 2nd: 1, 1 → 3rd: 0
        assert opt.score_acceleration_trend() == 0.0

    def test_return_type(self):
        """Return type should be float."""
        opt = _make_opt(scores=[0.1, 0.2, 0.3, 0.4])
        result = opt.score_acceleration_trend()
        assert isinstance(result, float)


# ============================================================================
# Tests for score_dimension_std
# ============================================================================

class TestScoreDimensionStd:
    """Test OntologyCritic.score_dimension_std()."""

    def test_uniform_zero(self):
        """All dimensions at 0.0 should return 0.0 std."""
        critic = OntologyCritic(use_llm=False) # NO LLM
        score = _cs(
            completeness=0.0, consistency=0.0, clarity=0.0,
            granularity=0.0, relationship_coherence=0.0, domain_alignment=0.0
        )
        assert critic.score_dimension_std(score) == pytest.approx(0.0)

    def test_uniform_nonzero(self):
        """All dimensions at same nonzero value should return 0.0 std."""
        critic = OntologyCritic(use_llm=False)
        score = _cs(
            completeness=0.5, consistency=0.5, clarity=0.5,
            granularity=0.5, relationship_coherence=0.5, domain_alignment=0.5
        )
        assert critic.score_dimension_std(score) == pytest.approx(0.0)

    def test_range_distribution(self):
        """Dimensions spread across range [0, 1]."""
        critic = OntologyCritic(use_llm=False)
        s = _cs(
            completeness=0.0, consistency=0.2, clarity=0.4,
            granularity=0.6, relationship_coherence=0.8, domain_alignment=1.0
        )
        # values: [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        # mean: 0.5
        # variance: ((0-0.5)^2 + (0.2-0.5)^2 + (0.4-0.5)^2 + (0.6-0.5)^2 + (0.8-0.5)^2 + (1.0-0.5)^2) / 6
        #         = (0.25 + 0.09 + 0.01 + 0.01 + 0.09 + 0.25) / 6 = 0.7 / 6 ≈ 0.11666...
        # std: sqrt(0.11666...) ≈ 0.3415...
        assert critic.score_dimension_std(s) == pytest.approx(0.3415650255, abs=1e-6)

    def test_return_type(self):
        """Return type should be float."""
        critic = OntologyCritic(use_llm=False)
        result = critic.score_dimension_std(_cs(clarity=0.5))
        assert isinstance(result, float)

    def test_non_negative(self):
        """Result should always be non-negative."""
        critic = OntologyCritic(use_llm=False)
        s = _cs(
            completeness=0.1, consistency=0.9, clarity=0.2,
            granularity=0.8, relationship_coherence=0.3, domain_alignment=0.7
        )
        assert critic.score_dimension_std(s) >= 0.0


# ============================================================================
# Tests for relationship_density
# ============================================================================

class TestRelationshipDensity:
    """Test OntologyGenerator.relationship_density()."""

    def test_empty_result(self):
        """Empty result (no entities) should return 0.0."""
        gen = OntologyGenerator(use_ipfs_accelerate=False)
        result = _FakeExtractionResult(entities=[], relationships=[])
        assert gen.relationship_density(result) == pytest.approx(0.0)

    def test_single_entity(self):
        """Single entity (no pairs) should return 0.0."""
        gen = OntologyGenerator(use_ipfs_accelerate=False)
        result = _FakeExtractionResult(
            entities=[_FakeEntity(id="e1", name="Entity1")],
            relationships=[]
        )
        assert gen.relationship_density(result) == pytest.approx(0.0)

    def test_two_entities_no_rel(self):
        """Two entities, no relationships: 0 / 1 = 0.0."""
        gen = OntologyGenerator(use_ipfs_accelerate=False)
        result = _FakeExtractionResult(
            entities=[
                _FakeEntity(id="e1", name="E1"),
                _FakeEntity(id="e2", name="E2"),
            ],
            relationships=[]
        )
        assert gen.relationship_density(result) == pytest.approx(0.0)

    def test_two_entities_one_rel(self):
        """Two entities, one relationship: 1 / (2*1/2) = 1 / 1 = 1.0."""
        gen = OntologyGenerator(use_ipfs_accelerate=False)
        result = _FakeExtractionResult(
            entities=[
                _FakeEntity(id="e1", name="E1"),
                _FakeEntity(id="e2", name="E2"),
            ],
            relationships=[
                _FakeRelationship(source_id="e1", target_id="e2", type="rel")
            ]
        )
        assert gen.relationship_density(result) == pytest.approx(1.0, abs=1e-9)

    def test_four_entities_three_rels(self):
        """Four entities, three relationships: 3 / (4*3/2) = 3 / 6 = 0.5."""
        gen = OntologyGenerator(use_ipfs_accelerate=False)
        result = _FakeExtractionResult(
            entities=[
                _FakeEntity(id=f"e{i}", name=f"E{i}") for i in range(1, 5)
            ],
            relationships=[
                _FakeRelationship(source_id="e1", target_id="e2", type="rel"),
                _FakeRelationship(source_id="e2", target_id="e3", type="rel"),
                _FakeRelationship(source_id="e3", target_id="e4", type="rel"),
            ]
        )
        assert gen.relationship_density(result) == pytest.approx(0.5, abs=1e-9)

    def test_five_entities_five_rels(self):
        """Five entities, five relationships: 5 / (5*4/2) = 5 / 10 = 0.5."""
        gen = OntologyGenerator(use_ipfs_accelerate=False)
        result = _FakeExtractionResult(
            entities=[
                _FakeEntity(id=f"e{i}", name=f"E{i}") for i in range(1, 6)
            ],
            relationships=[
                _FakeRelationship(source_id="e1", target_id="e2", type="rel"),
                _FakeRelationship(source_id="e2", target_id="e3", type="rel"),
                _FakeRelationship(source_id="e3", target_id="e4", type="rel"),
                _FakeRelationship(source_id="e4", target_id="e5", type="rel"),
                _FakeRelationship(source_id="e1", target_id="e5", type="rel"),
            ]
        )
        assert gen.relationship_density(result) == pytest.approx(0.5, abs=1e-9)

    def test_return_type(self):
        """Return type should be float."""
        gen = OntologyGenerator(use_ipfs_accelerate=False)
        result = _FakeExtractionResult(entities=[_FakeEntity("e1", "E1")], relationships=[])
        res = gen.relationship_density(result)
        assert isinstance(res, float)
