import json
import os
import importlib.util

from adversarial_harness import AdversarialHarness


def _load_session_sgd_report_module():
	project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	path = os.path.join(project_root, "examples", "session_sgd_report.py")
	spec = importlib.util.spec_from_file_location("session_sgd_report", path)
	assert spec and spec.loader
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)  # type: ignore[attr-defined]
	return module


_sgd = _load_session_sgd_report_module()
_find_session_json_files = _sgd._find_session_json_files
_maybe_load_json = _sgd._maybe_load_json
_safe_int = _sgd._safe_int
_summarize_session = _sgd._summarize_session
_write_report = _sgd._write_report


class MockLLMBackend:
	def __init__(self, response: str):
		self.response = response
		self.call_count = 0

	def __call__(self, prompt: str) -> str:
		self.call_count += 1
		return self.response


class MockMediator:
	def __init__(self):
		self.questions_asked = 0
		self.phase_manager = None

	def start_three_phase_process(self, complaint_text):
		return {
			'phase': 'intake',
			'initial_questions': [
				{'question': 'When did this happen?', 'type': 'timeline'},
			]
		}

	def process_denoising_answer(self, question, answer):
		self.questions_asked += 1
		return {
			'converged': self.questions_asked >= 1,
			'next_questions': [],
			'ready_for_evidence_phase': True,
		}

	def get_three_phase_status(self):
		return {
			'current_phase': 'intake',
			'iteration_count': self.questions_asked,
			'next_action': {'action': 'complete_intake'},
			'phase_completion': {'intake': True},
		}


def test_safe_int_treats_expected_conversion_failures_as_missing():
	assert _safe_int("42") == 42
	assert _safe_int(None) is None
	assert _safe_int("not-an-integer") is None
	assert _safe_int([]) is None
	assert _safe_int(float("inf")) is None


def test_safe_int_does_not_swallow_unexpected_conversion_failures():
	class BrokenInteger:
		def __int__(self):
			raise RuntimeError("unexpected conversion failure")

	try:
		_safe_int(BrokenInteger())
	except RuntimeError as exc:
		assert str(exc) == "unexpected conversion failure"
	else:
		raise AssertionError("_safe_int swallowed an unexpected RuntimeError")


def test_maybe_load_json_treats_expected_artifact_failures_as_missing(tmp_path, monkeypatch):
	missing_path = tmp_path / "missing.json"
	malformed_path = tmp_path / "malformed.json"
	malformed_path.write_text('{"entities":', encoding="utf-8")
	invalid_utf8_path = tmp_path / "invalid-utf8.json"
	invalid_utf8_path.write_bytes(b'\xff')

	assert _maybe_load_json(None) is None
	assert _maybe_load_json(str(missing_path)) is None
	assert _maybe_load_json(str(malformed_path)) is None
	assert _maybe_load_json(str(invalid_utf8_path)) is None

	def raise_oserror(path):
		raise OSError(f"unable to read {path}")

	monkeypatch.setattr(_sgd, "_load_json", raise_oserror)
	assert _maybe_load_json(str(malformed_path)) is None


def test_maybe_load_json_does_not_swallow_unexpected_failures(tmp_path, monkeypatch):
	artifact_path = tmp_path / "artifact.json"
	artifact_path.write_text("{}", encoding="utf-8")

	def raise_runtime_error(path):
		raise RuntimeError(f"unexpected loader failure for {path}")

	monkeypatch.setattr(_sgd, "_load_json", raise_runtime_error)
	try:
		_maybe_load_json(str(artifact_path))
	except RuntimeError as exc:
		assert str(exc) == f"unexpected loader failure for {artifact_path}"
	else:
		raise AssertionError("_maybe_load_json swallowed an unexpected RuntimeError")


def test_batch_persist_then_sgd_report(tmp_path):
	# LLM backends: complainant generates complaint, critic returns parsable score text.
	complainant_backend = MockLLMBackend("I was discriminated against at work.")
	critic_backend = MockLLMBackend(
		"""SCORES:
question_quality: 0.7
information_extraction: 0.6
empathy: 0.6
efficiency: 0.7
coverage: 0.6

FEEDBACK:
OK.

STRENGTHS:
- Clear

WEAKNESSES:
- Short

SUGGESTIONS:
- Ask one more follow-up
"""
	)

	def mediator_factory():
		return MockMediator()

	harness = AdversarialHarness(
		llm_backend_complainant=complainant_backend,
		llm_backend_critic=critic_backend,
		mediator_factory=mediator_factory,
		max_parallel=2,
		session_state_dir=str(tmp_path),
	)

	seeds = [
		{'type': 'employment_discrimination', 'key_facts': {'employer': 'Acme'}},
		{'type': 'housing_discrimination', 'key_facts': {'landlord': 'Test'}},
	]

	results = harness.run_batch(num_sessions=2, seed_complaints=seeds, max_turns_per_session=2)
	assert len(results) == 2

	session_json_files = _find_session_json_files(str(tmp_path))
	assert len(session_json_files) == 2

	summaries = [_summarize_session(p) for p in session_json_files]
	report_path = _write_report(str(tmp_path), str(tmp_path / "_reports"), summaries)
	with open(report_path, "r", encoding="utf-8") as f:
		report = json.load(f)

	assert report["num_sessions"] == 2
	assert "ended_reason_counts" in report
	assert "averages" in report
