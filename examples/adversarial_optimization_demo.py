import argparse
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict

# Allow running via: python examples/adversarial_optimization_demo.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
	sys.path.insert(0, PROJECT_ROOT)

from adversarial_harness import AdversarialHarness, Critic, Optimizer
from adversarial_harness.demo_autopatch import DemoPatchOptimizer, run_demo_autopatch_batch
from adversarial_harness.session import SessionResult
from backends import LLMRouterBackend
from mediator import Mediator


def _load_config(path: str) -> Dict[str, Any]:
	with open(path, "r", encoding="utf-8") as f:
		return json.load(f)


def _get_llm_router_backend_config(config: Dict[str, Any], backend_id: str | None) -> Dict[str, Any]:
	backend_ids = config.get("MEDIATOR", {}).get("backends", [])
	if not backend_id:
		backend_id = backend_ids[0] if backend_ids else None
	if not backend_id:
		raise ValueError("No backend id specified and config.MEDIATOR.backends is empty")

	backends = config.get("BACKENDS", [])
	backend_config = next((b for b in backends if b.get("id") == backend_id), None)
	if not backend_config:
		raise ValueError(f"Backend id not found in config.BACKENDS: {backend_id}")
	if backend_config.get("type") != "llm_router":
		raise ValueError(f"Backend {backend_id} must have type 'llm_router'")

	# Avoid passing config keys that aren't meaningful to the router.
	backend_kwargs = dict(backend_config)
	backend_kwargs.pop("type", None)
	return backend_kwargs


def _prompt_multiline(prompt: str) -> str:
	print(prompt)
	print("(finish input with an empty line)")
	lines = []
	while True:
		line = input("> ")
		if line == "":
			break
		lines.append(line)
	return "\n".join(lines).strip()


def _safe_session_id(text: str) -> str:
	allowed = []
	for ch in text:
		if ch.isalnum() or ch in ("-", "_", "."):
			allowed.append(ch)
		else:
			allowed.append("_")
	return "".join(allowed)


def _write_jsonl_line(fp, obj: Dict[str, Any]) -> None:
	fp.write(json.dumps(obj, ensure_ascii=False) + "\n")
	fp.flush()


def _print_question_details(question: Dict[str, Any]) -> None:
	question_text = str(question.get("question") or "").strip()
	question_objective = str(question.get("question_objective") or "").strip()
	question_reason = str(question.get("question_reason") or "").strip()
	expected_proof_gain = str(question.get("expected_proof_gain") or "").strip()

	print(question_text)
	if question_objective:
		print(f"Objective: {question_objective}")
	if expected_proof_gain:
		print(f"Expected proof gain: {expected_proof_gain}")
	if question_reason:
		print(f"Why this question: {question_reason}")


def main() -> int:
	parser = argparse.ArgumentParser(
		description="Interactive multi-turn mediator chat; saves JSONL history and prints an optimization report"
	)
	parser.add_argument(
		"--mode",
		choices=["interactive", "batch"],
		default="interactive",
		help="Run an interactive session or an automated adversarial batch",
	)
	parser.add_argument(
		"--config",
		default="config.llm_router.json",
		help="Path to JSON config (default: config.llm_router.json)",
	)
	parser.add_argument(
		"--backend-id",
		default=None,
		help="Backend id to use (default: first entry in MEDIATOR.backends)",
	)
	parser.add_argument("--max-turns", type=int, default=3)
	parser.add_argument(
		"--session-id",
		default=None,
		help="Optional session id (default: timestamp-based)",
	)
	parser.add_argument(
		"--session-cache-friendly",
		action="store_true",
		help=(
			"Enable a Copilot CLI cache-friendly mode by isolating each session into its own Copilot --config-dir and using --continue. "
			"This reduces prompt-prefix churn across turns."
		),
	)
	parser.add_argument("--num-sessions", type=int, default=3, help="(batch mode) number of sessions")
	parser.add_argument("--max-parallel", type=int, default=1, help="(batch mode) parallel sessions")
	parser.add_argument(
		"--emit-autopatch",
		action="store_true",
		help="(batch mode) generate a demo patch artifact from the optimization report",
	)
	parser.add_argument(
		"--autopatch-target-file",
		default="adversarial_harness/session.py",
		help="(batch mode) repository file to target when generating the demo patch",
	)
	parser.add_argument(
		"--autopatch-output-dir",
		default=None,
		help="(batch mode) directory for demo autopatch artifacts; defaults to tmp/adversarial_optimization_demo",
	)
	parser.add_argument(
		"--demo-backend",
		action="store_true",
		help="(batch mode) use mock complainant, critic, and mediator components instead of llm_router",
	)
	args = parser.parse_args()

	logging.basicConfig(level=logging.INFO)

	backend_kwargs: Dict[str, Any] = {}
	if not (args.mode == "batch" and args.demo_backend):
		config = _load_config(args.config)
		backend_kwargs = _get_llm_router_backend_config(config, args.backend_id)

	if args.mode == "batch":
		state_dir = os.path.join(PROJECT_ROOT, "statefiles")

		if args.demo_backend:
			output_dir = Path(args.autopatch_output_dir) if args.autopatch_output_dir else Path(PROJECT_ROOT) / "tmp" / "adversarial_optimization_demo"
			payload = run_demo_autopatch_batch(
				project_root=PROJECT_ROOT,
				output_dir=output_dir,
				target_file=args.autopatch_target_file,
				num_sessions=args.num_sessions,
				max_turns=args.max_turns,
				max_parallel=args.max_parallel,
				session_state_dir=state_dir,
				marker_prefix="Batch autopatch recommendation",
			)
			if not args.emit_autopatch:
				print(json.dumps(payload["report"], indent=2))
				return 0
			print(json.dumps(payload, indent=2))
			return 0

		def _make_session_backend(*, role: str, session_id: str, session_dir: str | None) -> LLMRouterBackend:
			per_call_kwargs: Dict[str, Any] = dict(backend_kwargs)
			if args.session_cache_friendly and session_dir:
				per_call_kwargs["copilot_config_dir"] = os.path.join(session_dir, "_copilot", role, "config")
				per_call_kwargs["continue_session"] = True
				per_call_kwargs.setdefault("copilot_log_dir", os.path.join(session_dir, "_copilot", role, "logs"))
			return LLMRouterBackend(**per_call_kwargs)

		llm_backend_complainant = LLMRouterBackend(**backend_kwargs)
		llm_backend_critic = LLMRouterBackend(**backend_kwargs)

		complainant_factory = None
		critic_factory = None
		if args.session_cache_friendly:
			complainant_factory = lambda session_id, session_dir: _make_session_backend(
				role="complainant",
				session_id=session_id,
				session_dir=session_dir,
			)
			critic_factory = lambda session_id, session_dir: _make_session_backend(
				role="critic",
				session_id=session_id,
				session_dir=session_dir,
			)

		def mediator_factory(session_id: str | None = None, session_dir: str | None = None) -> Mediator:
			if args.session_cache_friendly and session_id and session_dir:
				backend = _make_session_backend(role="mediator", session_id=session_id, session_dir=session_dir)
			else:
				backend = LLMRouterBackend(**backend_kwargs)
			return Mediator(backends=[backend])

		harness = AdversarialHarness(
			llm_backend_complainant=llm_backend_complainant,
			llm_backend_critic=llm_backend_critic,
			mediator_factory=mediator_factory,
			max_parallel=args.max_parallel,
			session_state_dir=state_dir,
			llm_backend_complainant_factory=complainant_factory,
			llm_backend_critic_factory=critic_factory,
		)
		results = harness.run_batch(num_sessions=args.num_sessions, max_turns_per_session=args.max_turns)
		optimizer = Optimizer()
		report = optimizer.analyze(results)
		if not args.emit_autopatch:
			print(json.dumps(report.to_dict(), indent=2))
			return 0

		output_dir = Path(args.autopatch_output_dir) if args.autopatch_output_dir else Path(PROJECT_ROOT) / "tmp" / "adversarial_optimization_demo"
		autopatch_result = optimizer.run_agentic_autopatch(
			results,
			target_files=[args.autopatch_target_file],
			method="actor_critic",
			llm_router=object(),
			optimizer=DemoPatchOptimizer(
				project_root=Path(PROJECT_ROOT),
				output_dir=output_dir,
				marker_prefix="Batch autopatch recommendation",
			),
			report=report,
		)
		payload = {
			"num_results": len(results),
			"report": report.to_dict(),
			"autopatch": {
				"success": bool(getattr(autopatch_result, "success", False)),
				"patch_path": str(getattr(autopatch_result, "patch_path", "")),
				"patch_cid": str(getattr(autopatch_result, "patch_cid", "")),
				"metadata": dict(getattr(autopatch_result, "metadata", {}) or {}),
			},
		}
		summary_path = output_dir / "summary.json"
		summary_path.parent.mkdir(parents=True, exist_ok=True)
		summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
		print(json.dumps(payload, indent=2))
		return 0

	# interactive mode
	session_id = args.session_id or f"session_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
	session_id = _safe_session_id(session_id)
	session_dir = os.path.join(PROJECT_ROOT, "statefiles", session_id)
	os.makedirs(session_dir, exist_ok=True)

	chat_jsonl_path = os.path.join(session_dir, "chat.jsonl")
	session_json_path = os.path.join(session_dir, "session.json")
	report_json_path = os.path.join(session_dir, "optimization_report.json")

	logging.info("Session folder: %s", session_dir)

	if args.session_cache_friendly:
		backend_kwargs = {
			**backend_kwargs,
			"copilot_config_dir": os.path.join(session_dir, "_copilot", "interactive", "config"),
			"copilot_log_dir": os.path.join(session_dir, "_copilot", "interactive", "logs"),
			"continue_session": True,
		}

	llm_backend = LLMRouterBackend(**backend_kwargs)
	mediator = Mediator(backends=[llm_backend])
	critic = Critic(llm_backend)

	initial_complaint = _prompt_multiline("Paste/enter the initial complaint text:")
	if not initial_complaint:
		raise SystemExit("No complaint text provided")

	conversation_history: list[dict[str, Any]] = []
	start_time = time.time()

	with open(chat_jsonl_path, "a", encoding="utf-8") as chat_fp:
		_write_jsonl_line(
			chat_fp,
			{
				"timestamp": datetime.utcnow().isoformat(),
				"role": "complainant",
				"type": "initial_complaint",
				"content": initial_complaint,
			},
		)

		status = mediator.start_three_phase_process(initial_complaint)
		questions = status.get("initial_questions") or []
		turns = 0
		questions_asked = 0

		while turns < args.max_turns:
			if not questions:
				logging.info("No more questions; ending session")
				break

			question = questions[0]
			question_text = question.get("question") if isinstance(question, dict) else str(question)
			question_objective = question.get("question_objective") if isinstance(question, dict) else None
			question_reason = question.get("question_reason") if isinstance(question, dict) else None
			expected_proof_gain = question.get("expected_proof_gain") if isinstance(question, dict) else None

			print("\nMediator question:")
			if isinstance(question, dict):
				_print_question_details(question)
			else:
				print(question_text)

			mediator_turn = {
				"role": "mediator",
				"type": "question",
				"content": question_text,
			}
			if question_objective:
				mediator_turn["question_objective"] = question_objective
			if question_reason:
				mediator_turn["question_reason"] = question_reason
			if expected_proof_gain:
				mediator_turn["expected_proof_gain"] = expected_proof_gain
			conversation_history.append(mediator_turn)
			_write_jsonl_line(
				chat_fp,
				mediator_turn | {
					"timestamp": datetime.utcnow().isoformat(),
				},
			)

			answer = _prompt_multiline("Your answer:")
			conversation_history.append(
				{
					"role": "complainant",
					"type": "answer",
					"content": answer,
				}
			)
			_write_jsonl_line(
				chat_fp,
				{
					"timestamp": datetime.utcnow().isoformat(),
					"role": "complainant",
					"type": "answer",
					"content": answer,
				},
			)

			status = mediator.process_denoising_answer(question, answer)
			questions = status.get("next_questions") or []

			turns += 1
			questions_asked += 1
			if status.get("converged") or status.get("ready_for_evidence_phase"):
				logging.info("Mediator indicates convergence/phase transition; ending session")
				break

	final_state = mediator.get_three_phase_status()
	critic_score = critic.evaluate_session(
		initial_complaint,
		conversation_history,
		final_state,
		context={"mode": "interactive", "session_id": session_id},
	)

	duration = time.time() - start_time
	session_result = SessionResult(
		session_id=session_id,
		timestamp=datetime.utcnow().isoformat(),
		seed_complaint={"mode": "interactive", "_meta": {"max_turns": args.max_turns}},
		initial_complaint_text=initial_complaint,
		conversation_history=conversation_history,
		num_questions=questions_asked,
		num_turns=turns,
		final_state=final_state,
		critic_score=critic_score,
		duration_seconds=duration,
		success=True,
	)

	with open(session_json_path, "w", encoding="utf-8") as f:
		json.dump(session_result.to_dict(), f, ensure_ascii=False, indent=2)

	report = Optimizer().analyze([session_result])
	with open(report_json_path, "w", encoding="utf-8") as f:
		json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

	print("\nOptimization report:")
	print(json.dumps(report.to_dict(), indent=2))
	print("\nSaved:")
	print(f"- {chat_jsonl_path}")
	print(f"- {session_json_path}")
	print(f"- {report_json_path}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
