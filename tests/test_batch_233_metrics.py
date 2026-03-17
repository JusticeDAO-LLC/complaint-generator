"""
Batch 233: Feature tests for new metrics.

Tests for:
- OntologyOptimizer.score_velocity_std()
- OntologyCritic.score_dimension_median_abs_deviation()
- OntologyGenerator.entity_type_gini_coefficient()
"""

from pathlib import Path
import sys
import types

import pytest

LOCAL_PKG_ROOT = Path(__file__).resolve().parents[1] / "ipfs_datasets_py"
if str(LOCAL_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(LOCAL_PKG_ROOT))

_optional_mods = ("tor" + "ch", "trans" + "formers")
for _mod in _optional_mods:
    if _mod not in sys.modules:
        mod = types.ModuleType(_mod)
        mod.Tensor = object
        sys.modules[_mod] = mod

from ipfs_datasets_py.optimizers.graphrag.ontology_optimizer import OntologyOptimizer
from ipfs_datasets_py.optimizers.graphrag.ontology_critic import OntologyCritic, CriticScore
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import OntologyGenerator


class _FakeEntry:
    def __init__(self, score: float) -> None:
        self.average_score = score


def _make_opt(scores):
    opt = object.__new__(OntologyOptimizer)
    opt._history = [_FakeEntry(s) for s in scores]
    return opt


def _cs(**overrides) -> CriticScore:
    base = {
        "completeness": 0.0,
        "consistency": 0.0,
        "clarity": 0.0,
        "granularity": 0.0,
        "relationship_coherence": 0.0,
        "domain_alignment": 0.0,
    }
    base.update(overrides)
    return CriticScore(**base)


class TestScoreVelocityStd:
    def test_empty_history(self):
        opt = _make_opt([])
        assert opt.score_velocity_std() == 0.0

    def test_single_entry(self):
        opt = _make_opt([0.3])
        assert opt.score_velocity_std() == 0.0

    def test_two_entries_zero_std(self):
        opt = _make_opt([0.2, 0.2])
        assert opt.score_velocity_std() == 0.0

    def test_nonzero_std(self):
        opt = _make_opt([0.1, 0.2, 0.4])
        assert opt.score_velocity_std() == pytest.approx(0.05, abs=1e-9)

    def test_return_type(self):
        opt = _make_opt([0.0, 0.1, 0.2])
        assert isinstance(opt.score_velocity_std(), float)


class TestScoreDimensionMedianAbsDeviation:
    def test_uniform_zero(self):
        critic = OntologyCritic()
        assert critic.score_dimension_median_abs_deviation(_cs()) == pytest.approx(0.0)

    def test_half_and_half(self):
        critic = OntologyCritic()
        s = _cs(completeness=0.0, consistency=0.0, clarity=0.0,
                granularity=1.0, relationship_coherence=1.0, domain_alignment=1.0)
        assert critic.score_dimension_median_abs_deviation(s) == pytest.approx(0.5)

    def test_return_type(self):
        critic = OntologyCritic()
        assert isinstance(critic.score_dimension_median_abs_deviation(_cs(clarity=0.2)), float)

    def test_non_negative(self):
        critic = OntologyCritic()
        s = _cs(completeness=-0.1, consistency=0.0, clarity=0.1,
                granularity=0.2, relationship_coherence=0.3, domain_alignment=0.4)
        assert critic.score_dimension_median_abs_deviation(s) >= 0.0


class TestEntityTypeGiniCoefficient:
    def test_empty_result(self):
        gen = OntologyGenerator()
        result = type('obj', (object,), {'entities': []})()
        assert gen.entity_type_gini_coefficient(result) == 0.0

    def test_single_type(self):
        gen = OntologyGenerator()
        entities = [type('obj', (object,), {'type': 'Person'})() for _ in range(3)]
        result = type('obj', (object,), {'entities': entities})()
        assert gen.entity_type_gini_coefficient(result) == 0.0

    def test_two_types(self):
        gen = OntologyGenerator()
        entities = [
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Org'})(),
        ]
        result = type('obj', (object,), {'entities': entities})()
        assert gen.entity_type_gini_coefficient(result) == pytest.approx(1 / 6, abs=1e-9)

    def test_return_type(self):
        gen = OntologyGenerator()
        entities = [type('obj', (object,), {'type': 'A'})(), type('obj', (object,), {'type': 'B'})()]
        result = type('obj', (object,), {'entities': entities})()
        assert isinstance(gen.entity_type_gini_coefficient(result), float)
