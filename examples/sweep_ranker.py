import argparse
import json
import math
import os
from typing import Any, Dict, List, Tuple


def _load_json(path: str) -> Dict[str, Any]:
	with open(path, "r", encoding="utf-8") as f:
		return json.load(f)


def _safe_float(value: Any) -> float | None:
	try:
		if value is None:
			return None
		if isinstance(value, bool):
			return float(value)
		return float(value)
	except (TypeError, ValueError, OverflowError):
		return None


def score_point(
	point: Dict[str, Any],
	*,
	w_success_rate: float = 100.0,
	w_throughput_per_min: float = 1.0,
	w_overall_score: float = 50.0,
	w_retry_penalty: float = -0.5,
	w_duration_penalty_s: float = 0.0,
) -> float:
	metrics = point.get("metrics") or {}
	sgd = point.get("sgd") or {}
	averages = (sgd.get("averages") or {})
	retry_stats = point.get("retry_stats") or {}

	success_rate = _safe_float(metrics.get("success_rate")) or 0.0
	throughput = _safe_float(metrics.get("throughput_sessions_per_min")) or 0.0
	overall = _safe_float(averages.get("overall_score"))
	overall = overall if overall is not None else 0.0
	duration_s = _safe_float(metrics.get("batch_duration_seconds")) or 0.0

	complainant_retries = int((retry_stats.get("complainant") or {}).get("retries_total") or 0)
	critic_retries = int((retry_stats.get("critic") or {}).get("retries_total") or 0)
	retries_total = complainant_retries + critic_retries

	score = 0.0
	score += w_success_rate * success_rate
	score += w_throughput_per_min * throughput
	score += w_overall_score * overall
	score += w_retry_penalty * float(retries_total)
	score += w_duration_penalty_s * float(duration_s)

	# Prevent NaNs from poisoning the ordering.
	if math.isnan(score) or math.isinf(score):
		return -1e9
	return score


def rank_sweep_results(
	sweep_doc: Dict[str, Any],
	*,
	top_n: int = 10,
	weights: Dict[str, float] | None = None,
) -> List[Dict[str, Any]]:
	weights = weights or {}
	results = sweep_doc.get("results") or []
	ranked: List[Tuple[float, Dict[str, Any]]] = []
	for point in results:
		s = score_point(
			point,
			w_success_rate=weights.get("success_rate", 100.0),
			w_throughput_per_min=weights.get("throughput", 1.0),
			w_overall_score=weights.get("overall", 50.0),
			w_retry_penalty=weights.get("retries", -0.5),
			w_duration_penalty_s=weights.get("duration_s", 0.0),
		)
		ranked.append((s, point))

	ranked.sort(key=lambda x: x[0], reverse=True)
	out: List[Dict[str, Any]] = []
	for s, point in ranked[: max(1, int(top_n))]:
		out.append({
			"score": s,
			"label": point.get("label"),
			"settings": point.get("settings"),
			"metrics": point.get("metrics"),
			"retry_stats": point.get("retry_stats"),
			"sgd": point.get("sgd"),
			"paths": point.get("paths"),
		})
	return out


def _parse_weights(s: str | None) -> Dict[str, float]:
	# "success_rate=120,throughput=1,overall=40,retries=-1"
	if not s:
		return {}
	out: Dict[str, float] = {}
	for part in s.split(","):
		part = part.strip()
		if not part:
			continue
		if "=" not in part:
			continue
		k, v = part.split("=", 1)
		k = k.strip()
		v = v.strip()
		try:
			out[k] = float(v)
		except ValueError:
			continue
	return out


def main() -> int:
	parser = argparse.ArgumentParser(description="Rank sweep_results.json configs by a weighted objective")
	parser.add_argument("--input", required=True, help="Path to sweep_results.json")
	parser.add_argument("--top", type=int, default=10)
	parser.add_argument(
		"--weights",
		default=None,
		help="Comma-separated weights: success_rate,throughput,overall,retries,duration_s.",
	)
	args = parser.parse_args()

	path = args.input
	if not os.path.isfile(path):
		raise SystemExit(f"Input not found: {path}")

	sweep = _load_json(path)
	ranked = rank_sweep_results(sweep, top_n=args.top, weights=_parse_weights(args.weights))
	print(json.dumps({"input": os.path.abspath(path), "top": ranked}, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
