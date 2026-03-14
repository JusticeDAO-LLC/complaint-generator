import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SessionSummary:
	session_id: str
	success: bool
	num_turns: int
	num_questions: int
	max_turns: Optional[int]
	personality: Optional[str]
	overall_score: Optional[float]
	empathy: Optional[float]
	coverage: Optional[float]
	question_quality: Optional[float]
	info_extraction: Optional[float]
	efficiency: Optional[float]
	next_action: Optional[str]
	phase: Optional[str]
	ended_reason: str
	has_timeline_question: bool
	has_impact_remedy_question: bool
	knowledge_graph_path: Optional[str]
	dependency_graph_path: Optional[str]
	kg_total_entities: Optional[int]
	kg_total_relationships: Optional[int]
	dg_total_nodes: Optional[int]
	dg_total_dependencies: Optional[int]
	dg_satisfaction_rate: Optional[float]
	path: str


def _safe_int(value: Any) -> Optional[int]:
	try:
		if value is None:
			return None
		return int(value)
	except Exception:
		return None


def _load_json(path: str) -> Dict[str, Any]:
	with open(path, "r", encoding="utf-8") as f:
		return json.load(f)


def _maybe_load_json(path: Optional[str]) -> Optional[Dict[str, Any]]:
	if not path:
		return None
	try:
		if not os.path.isfile(path):
			return None
		return _load_json(path)
	except Exception:
		return None


def _session_graph_paths(doc: Dict[str, Any], session_json_path: str) -> Tuple[Optional[str], Optional[str]]:
	"""Return (knowledge_graph_path, dependency_graph_path)."""
	art = doc.get("artifacts") or {}
	kg = art.get("knowledge_graph_json")
	dg = art.get("dependency_graph_json")
	if isinstance(kg, str) and kg:
		kg_path = kg
	else:
		kg_path = os.path.join(os.path.dirname(session_json_path), "knowledge_graph.json")
	if isinstance(dg, str) and dg:
		dg_path = dg
	else:
		dg_path = os.path.join(os.path.dirname(session_json_path), "dependency_graph.json")
	if not os.path.isfile(kg_path):
		kg_path = None
	if not os.path.isfile(dg_path):
		dg_path = None
	return kg_path, dg_path


def _kg_counts(kg: Optional[Dict[str, Any]]) -> Tuple[Optional[int], Optional[int]]:
	if not isinstance(kg, dict):
		return None, None
	entities = kg.get("entities") or {}
	rels = kg.get("relationships") or {}
	if isinstance(entities, dict) and isinstance(rels, dict):
		return len(entities), len(rels)
	return None, None


def _dg_counts(dg: Optional[Dict[str, Any]]) -> Tuple[Optional[int], Optional[int], Optional[float]]:
	if not isinstance(dg, dict):
		return None, None, None
	nodes = dg.get("nodes") or {}
	deps = dg.get("dependencies") or {}
	if not isinstance(nodes, dict) or not isinstance(deps, dict):
		return None, None, None
	satisfied = 0
	for n in nodes.values():
		if isinstance(n, dict) and n.get("satisfied") is True:
			satisfied += 1
	rate = (satisfied / len(nodes)) if nodes else 0.0
	return len(nodes), len(deps), rate


def _find_session_json_files(state_dir: str) -> List[str]:
	paths: List[str] = []
	if not os.path.isdir(state_dir):
		return paths

	for name in os.listdir(state_dir):
		if not name.startswith("session_"):
			continue
		session_dir = os.path.join(state_dir, name)
		if not os.path.isdir(session_dir):
			continue
		candidate = os.path.join(session_dir, "session.json")
		if os.path.isfile(candidate):
			paths.append(candidate)

	return sorted(paths)


def _termination_reason(doc: Dict[str, Any]) -> str:
	if not doc.get("success", True):
		return "error"

	seed_meta = (doc.get("seed_complaint") or {}).get("_meta") or {}
	max_turns = _safe_int(seed_meta.get("max_turns"))
	num_turns = _safe_int(doc.get("num_turns")) or 0
	final_state = doc.get("final_state") or {}
	next_action = ((final_state.get("next_action") or {}).get("action"))

	# If we hit the configured cap and mediator wants to continue, this is truncation.
	if max_turns is not None and num_turns >= max_turns:
		if next_action in {"continue_denoising", "address_gaps", "gather_evidence", "fill_evidence_gaps"}:
			return "turn_cap_before_completion"
		return "turn_cap"

	# Otherwise, infer completion vs no-questions.
	if final_state.get("phase_completion", {}).get("intake") is True:
		return "intake_complete"
	if next_action == "complete_intake":
		return "intake_complete"
	if (doc.get("num_questions") or 0) == 0:
		return "no_questions"
	return "ended_early"


def _summarize_session(path: str) -> SessionSummary:
	doc = _load_json(path)
	seed = doc.get("seed_complaint") or {}
	seed_meta = seed.get("_meta") or {}
	critic = doc.get("critic_score") or {}
	final_state = doc.get("final_state") or {}
	history = doc.get("conversation_history") or []

	def _has_question_matching(substrs: List[str]) -> bool:
		for msg in history:
			if msg.get('role') != 'mediator':
				continue
			if msg.get('type') not in {'question'}:
				continue
			text = (msg.get('content') or '').lower()
			if any(s in text for s in substrs):
				return True
		return False

	has_timeline = _has_question_matching(['timeline', 'when', 'what date', 'dates', 'how long'])
	has_impact = _has_question_matching(['harm', 'damages', 'lost', 'impact', 'remedy', 'seeking', 'outcome'])

	kg_path, dg_path = _session_graph_paths(doc, path)
	kg_doc = _maybe_load_json(kg_path)
	dg_doc = _maybe_load_json(dg_path)
	kg_entities, kg_rels = _kg_counts(kg_doc)
	dg_nodes, dg_deps, dg_rate = _dg_counts(dg_doc)

	return SessionSummary(
		session_id=doc.get("session_id", os.path.basename(os.path.dirname(path))),
		success=bool(doc.get("success", True)),
		num_turns=int(doc.get("num_turns") or 0),
		num_questions=int(doc.get("num_questions") or 0),
		max_turns=_safe_int(seed_meta.get("max_turns")),
		personality=seed_meta.get("personality"),
		overall_score=critic.get("overall_score"),
		empathy=critic.get("empathy"),
		coverage=critic.get("coverage"),
		question_quality=critic.get("question_quality"),
		info_extraction=critic.get("information_extraction"),
		efficiency=critic.get("efficiency"),
		next_action=((final_state.get("next_action") or {}).get("action")),
		phase=final_state.get("current_phase"),
		ended_reason=_termination_reason(doc),
		has_timeline_question=has_timeline,
		has_impact_remedy_question=has_impact,
		knowledge_graph_path=os.path.abspath(kg_path) if kg_path else None,
		dependency_graph_path=os.path.abspath(dg_path) if dg_path else None,
		kg_total_entities=kg_entities,
		kg_total_relationships=kg_rels,
		dg_total_nodes=dg_nodes,
		dg_total_dependencies=dg_deps,
		dg_satisfaction_rate=dg_rate,
		path=path,
	)


def _avg(values: List[float]) -> Optional[float]:
	vals = [v for v in values if isinstance(v, (int, float))]
	if not vals:
		return None
	return sum(vals) / len(vals)


def _write_report(state_dir: str, out_dir: str, sessions: List[SessionSummary]) -> str:
	os.makedirs(out_dir, exist_ok=True)
	report_path = os.path.join(out_dir, f"report_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json")

	ended_counts: Dict[str, int] = {}
	for s in sessions:
		ended_counts[s.ended_reason] = ended_counts.get(s.ended_reason, 0) + 1

	scores = [s.overall_score for s in sessions if isinstance(s.overall_score, (int, float))]
	emp = [s.empathy for s in sessions if isinstance(s.empathy, (int, float))]
	cov = [s.coverage for s in sessions if isinstance(s.coverage, (int, float))]
	qq = [s.question_quality for s in sessions if isinstance(s.question_quality, (int, float))]
	ie = [s.info_extraction for s in sessions if isinstance(s.info_extraction, (int, float))]
	eff = [s.efficiency for s in sessions if isinstance(s.efficiency, (int, float))]

	# Heuristic recommendations
	recommendations: List[str] = []
	if ended_counts.get("turn_cap_before_completion", 0) > 0:
		recommendations.append(
			"Many sessions hit --max-turns before intake completion. Increase --max-turns (e.g. 5-15) for richer transcripts."
		)
	avg_empathy = _avg(emp)
	if avg_empathy is not None and avg_empathy < 0.5:
		recommendations.append(
			"Empathy scores are low on average. Consider adding brief acknowledgement language to denoising questions (see complaint_phases/denoiser.py)."
		)
	avg_cov = _avg(cov)
	if avg_cov is not None and avg_cov < 0.6:
		recommendations.append(
			"Coverage is low on average. Consider ensuring denoiser generates at least one timeline question and one harm/remedy question per session."
		)

	missing_timeline = sum(1 for s in sessions if not s.has_timeline_question)
	missing_impact = sum(1 for s in sessions if not s.has_impact_remedy_question)
	if missing_timeline > 0:
		recommendations.append(f"{missing_timeline}/{len(sessions)} sessions lacked a timeline question. Consider prioritizing timeline coverage early in Phase 1.")
	if missing_impact > 0:
		recommendations.append(f"{missing_impact}/{len(sessions)} sessions lacked a harms/remedy question. Consider prioritizing harms+remedy coverage early in Phase 1.")

	kg_present = sum(1 for s in sessions if s.knowledge_graph_path)
	dg_present = sum(1 for s in sessions if s.dependency_graph_path)
	kg_empty = sum(1 for s in sessions if (s.kg_total_entities == 0 if s.kg_total_entities is not None else False))
	dg_empty = sum(1 for s in sessions if (s.dg_total_nodes == 0 if s.dg_total_nodes is not None else False))
	if kg_present > 0 and kg_empty == kg_present:
		recommendations.append(
			"All sessions had empty knowledge graphs. Improve extraction in complaint_phases/knowledge_graph.py (the LLM extractors are currently placeholders)."
		)
	if dg_present > 0 and dg_empty == dg_present:
		recommendations.append(
			"All sessions had empty dependency graphs. This is usually downstream of empty claim extraction from the knowledge graph."
		)

	report = {
		"generated_at": datetime.now(UTC).isoformat(),
		"state_dir": os.path.abspath(state_dir),
		"num_sessions": len(sessions),
		"ended_reason_counts": ended_counts,
		"graphs": {
			"knowledge_graph": {
				"sessions_with_file": kg_present,
				"sessions_empty": kg_empty,
				"avg_total_entities": _avg([float(s.kg_total_entities) for s in sessions if s.kg_total_entities is not None]),
				"avg_total_relationships": _avg([float(s.kg_total_relationships) for s in sessions if s.kg_total_relationships is not None]),
			},
			"dependency_graph": {
				"sessions_with_file": dg_present,
				"sessions_empty": dg_empty,
				"avg_total_nodes": _avg([float(s.dg_total_nodes) for s in sessions if s.dg_total_nodes is not None]),
				"avg_total_dependencies": _avg([float(s.dg_total_dependencies) for s in sessions if s.dg_total_dependencies is not None]),
				"avg_satisfaction_rate": _avg([float(s.dg_satisfaction_rate) for s in sessions if s.dg_satisfaction_rate is not None]),
			},
		},
		"missing_question_category_counts": {
			"timeline": missing_timeline,
			"impact_remedy": missing_impact,
		},
		"averages": {
			"overall_score": _avg(scores),
			"question_quality": _avg(qq),
			"information_extraction": _avg(ie),
			"empathy": _avg(emp),
			"efficiency": _avg(eff),
			"coverage": _avg(cov),
			"num_turns": _avg([float(s.num_turns) for s in sessions]),
			"num_questions": _avg([float(s.num_questions) for s in sessions]),
		},
		"recommendations": recommendations,
		"sessions": [
			{
				"session_id": s.session_id,
				"success": s.success,
				"num_turns": s.num_turns,
				"num_questions": s.num_questions,
				"max_turns": s.max_turns,
				"personality": s.personality,
				"overall_score": s.overall_score,
				"empathy": s.empathy,
				"coverage": s.coverage,
				"has_timeline_question": s.has_timeline_question,
				"has_impact_remedy_question": s.has_impact_remedy_question,
				"knowledge_graph": {
					"path": s.knowledge_graph_path,
					"total_entities": s.kg_total_entities,
					"total_relationships": s.kg_total_relationships,
				},
				"dependency_graph": {
					"path": s.dependency_graph_path,
					"total_nodes": s.dg_total_nodes,
					"total_dependencies": s.dg_total_dependencies,
					"satisfaction_rate": s.dg_satisfaction_rate,
				},
				"next_action": s.next_action,
				"phase": s.phase,
				"ended_reason": s.ended_reason,
				"session_json": os.path.abspath(s.path),
			}
			for s in sessions
		],
	}

	with open(report_path, "w", encoding="utf-8") as f:
		json.dump(report, f, ensure_ascii=False, indent=2)

	return report_path


def main() -> int:
	parser = argparse.ArgumentParser(description="Summarize saved session artifacts for SGD-style iteration")
	parser.add_argument("--state-dir", default="statefiles", help="Directory containing session_* subfolders")
	parser.add_argument("--out-dir", default=None, help="Output directory (default: <state-dir>/_reports)")
	args = parser.parse_args()

	state_dir = args.state_dir
	out_dir = args.out_dir or os.path.join(state_dir, "_reports")

	session_json_files = _find_session_json_files(state_dir)
	if not session_json_files:
		print(f"No session.json files found under {state_dir}")
		return 1

	sessions = [_summarize_session(p) for p in session_json_files]
	report_path = _write_report(state_dir, out_dir, sessions)

	# Print a short console summary
	ended_counts: Dict[str, int] = {}
	for s in sessions:
		ended_counts[s.ended_reason] = ended_counts.get(s.ended_reason, 0) + 1
	print(f"Sessions: {len(sessions)}")
	print("Ended reasons:", ended_counts)
	print(f"Wrote report: {report_path}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
