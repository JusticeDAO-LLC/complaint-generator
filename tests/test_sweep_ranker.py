import importlib.util
import json
import os

import pytest


def _load_ranker_module():
	project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	path = os.path.join(project_root, "examples", "sweep_ranker.py")
	spec = importlib.util.spec_from_file_location("sweep_ranker", path)
	assert spec and spec.loader
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)  # type: ignore[attr-defined]
	return module


_ranker = _load_ranker_module()


@pytest.mark.parametrize("value", [None, "not-a-number", object(), 10**1000])
def test_safe_float_returns_none_for_expected_conversion_failures(value):
	assert _ranker._safe_float(value) is None


def test_safe_float_does_not_swallow_unexpected_exceptions():
	class BrokenNumericValue:
		def __float__(self):
			raise RuntimeError("conversion implementation failed")

	with pytest.raises(RuntimeError, match="conversion implementation failed"):
		_ranker._safe_float(BrokenNumericValue())


def test_parse_weights_skips_only_malformed_numeric_values(monkeypatch):
	assert _ranker._parse_weights("success_rate=bad, throughput=2.5") == {"throughput": 2.5}

	def broken_float(_value):
		raise RuntimeError("float conversion unavailable")

	monkeypatch.setattr(_ranker, "float", broken_float, raising=False)
	with pytest.raises(RuntimeError, match="float conversion unavailable"):
		_ranker._parse_weights("throughput=2.5")


def test_ranker_prefers_success_and_score(tmp_path):
	sweep = {
		"results": [
			{
				"label": "bad",
				"settings": {"max_parallel": 4},
				"metrics": {"success_rate": 0.5, "throughput_sessions_per_min": 10.0, "batch_duration_seconds": 12.0},
				"retry_stats": {"complainant": {"retries_total": 10}, "critic": {"retries_total": 10}},
				"sgd": {"averages": {"overall_score": 0.2}},
				"paths": {},
			},
			{
				"label": "good",
				"settings": {"max_parallel": 2},
				"metrics": {"success_rate": 1.0, "throughput_sessions_per_min": 6.0, "batch_duration_seconds": 20.0},
				"retry_stats": {"complainant": {"retries_total": 0}, "critic": {"retries_total": 0}},
				"sgd": {"averages": {"overall_score": 0.8}},
				"paths": {},
			},
		]
	}

	ranked = _ranker.rank_sweep_results(sweep, top_n=2)
	assert ranked[0]["label"] == "good"

	# Ensure JSON serialization is stable
	out_path = tmp_path / "ranked.json"
	out_path.write_text(json.dumps(ranked), encoding="utf-8")
	assert out_path.read_text(encoding="utf-8").startswith("[")
