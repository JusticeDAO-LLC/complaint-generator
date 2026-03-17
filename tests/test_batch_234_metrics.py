"""
Batch 234: Feature tests for new metrics.

Tests for:
- OntologyOptimizer.score_peak_ratio()
- OntologyCritic.score_dimension_range()
- OntologyGenerator.entity_count_per_type()
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


class TestScorePeakRatio:
    def test_empty_history(self):
        opt = _make_opt([])
        assert opt.score_peak_ratio() == 0.0

    def test_single_entry(self):
        opt = _make_opt([0.5])
        assert opt.score_peak_ratio() == 0.0

    def test_two_entries(self):
        opt = _make_opt([0.2, 0.8])
        assert opt.score_peak_ratio() == 0.0

    def test_one_peak(self):
        opt = _make_opt([0.1, 0.5, 0.2])
        assert opt.score_peak_ratio() == pytest.approx(1.0 / 3.0, abs=1e-9)

    def test_two_peaks(self):
        opt = _make_opt([0.1, 0.5, 0.2, 0.6, 0.3])
        assert opt.score_peak_ratio() == pytest.approx(2.0 / 5.0, abs=1e-9)

    def test_no_peaks(self):
        opt = _make_opt([0.1, 0.2, 0.3, 0.4, 0.5])
        assert opt.score_peak_ratio() == 0.0

    def test_return_type(self):
        opt = _make_opt([0.0, 0.5, 0.3])
        assert isinstance(opt.score_peak_ratio(), float)


class TestScoreDimensionRange:
    def test_uniform_zero(self):
        critic = OntologyCritic()
        assert critic.score_dimension_range(_cs()) == pytest.approx(0.0)

    def test_uniform_nonzero(self):
        critic = OntologyCritic()
        s = _cs(completeness=0.5, consistency=0.5, clarity=0.5,
                granularity=0.5, relationship_coherence=0.5, domain_alignment=0.5)
        assert critic.score_dimension_range(s) == pytest.approx(0.0)

    def test_half_range(self):
        critic = OntologyCritic()
        s = _cs(completeness=0.2, consistency=0.8, clarity=0.5,
                granularity=0.5, relationship_coherence=0.5, domain_alignment=0.5)
        assert critic.score_dimension_range(s) == pytest.approx(0.6, abs=1e-9)

    def test_full_range(self):
        critic = OntologyCritic()
        s = _cs(completeness=0.0, consistency=1.0, clarity=0.5,
                granularity=0.5, relationship_coherence=0.5, domain_alignment=0.5)
        assert critic.score_dimension_range(s) == pytest.approx(1.0, abs=1e-9)

    def test_return_type(self):
        critic = OntologyCritic()
        assert isinstance(critic.score_dimension_range(_cs(clarity=0.3)), float)

    def test_non_negative(self):
        critic = OntologyCritic()
        s = _cs(completeness=-0.1, consistency=0.9, clarity=0.5,
                granularity=0.5, relationship_coherence=0.5, domain_alignment=0.5)
        assert critic.score_dimension_range(s) >= 0.0


class TestEntityCountPerType:
    def test_empty_result(self):
        gen = OntologyGenerator()
        result = type('obj', (object,), {'entities': []})()
        assert gen.entity_count_per_type(result) == {}

    def test_single_type_single_entity(self):
        gen = OntologyGenerator()
        entities = [type('obj', (object,), {'type': 'Person'})()]
        result = type('obj', (object,), {'entities': entities})()
        assert gen.entity_count_per_type(result) == {'Person': 1}

    def test_single_type_multiple_entities(self):
        gen = OntologyGenerator()
        entities = [type('obj', (object,), {'type': 'Person'})() for _ in range(3)]
        result = type('obj', (object,), {'entities': entities})()
        assert gen.entity_count_per_type(result) == {'Person': 3}

    def test_multiple_types(self):
        gen = OntologyGenerator()
        entities = [
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Organization'})(),
            type('obj', (object,), {'type': 'Location'})(),
        ]
        result = type('obj', (object,), {'entities': entities})()
        counts = gen.entity_count_per_type(result)
        assert counts == {'Person': 2, 'Organization': 1, 'Location': 1}

    def test_unknown_type(self):
        gen = OntologyGenerator()
        entities = [type('obj', (object,), {})()]
        result = type('obj', (object,), {'entities': entities})()
        assert gen.entity_count_per_type(result) == {'Unknown': 1}

    def test_return_type(self):
        gen = OntologyGenerator()
        entities = [type('obj', (object,), {'type': 'A'})()]
        result = type('obj', (object,), {'entities': entities})()
        assert isinstance(gen.entity_count_per_type(result), dict)
