import hashlib
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

from complaint_phases import ComplaintPhase, DependencyGraph, KnowledgeGraph
from complaint_phases.dependency_graph import NodeType
from intake_status import (
	_build_document_grounding_improvement_next_action,
	_build_document_grounding_recovery_action,
)


__all__ = ['WorkflowActionService', 'WorkflowService']


class WorkflowActionService:
	"""Build mediator workflow queues and document-grounding handoff actions.

	The service is intentionally composed into :class:`mediator.Mediator` rather
	than inherited by it.  The public methods below are the service boundary for
	new callers.  Underscore-prefixed methods remain in place because older code
	may have reached them through ``Mediator`` or the previously exported service
	class.
	"""

	def __init__(
		self,
		mediator,
		*,
		recovery_action_builder=_build_document_grounding_recovery_action,
		improvement_next_action_builder=_build_document_grounding_improvement_next_action,
	):
		self._mediator = mediator
		self._recovery_action_builder = recovery_action_builder
		self._improvement_next_action_builder = improvement_next_action_builder

	def __getattr__(self, name):
		return getattr(self._mediator, name)

	def build_intake_action_queue(
		self,
		intake_case_file: Dict[str, Any],
		claim_pressure: Dict[str, Dict[str, Any]],
		matching_pressure: Dict[str, Dict[str, Any]],
	) -> List[Dict[str, Any]]:
		"""Build the ordered action queue for the intake workflow."""
		return self._build_intake_workflow_action_queue(
			intake_case_file,
			claim_pressure,
			matching_pressure,
		)

	def summarize_intake_action_queue(self, queue: Any) -> Dict[str, Any]:
		"""Summarize an intake action queue without changing its payload."""
		return self._summarize_intake_workflow_action_queue(queue)

	def build_evidence_action_queue(
		self,
		alignment_evidence_tasks: Any,
		evidence_gaps: Any,
	) -> List[Dict[str, Any]]:
		"""Build the ordered action queue for evidence and grounding work."""
		return self._build_evidence_workflow_action_queue(
			alignment_evidence_tasks,
			evidence_gaps,
		)

	def summarize_evidence_action_queue(self, queue: Any) -> Dict[str, Any]:
		"""Summarize an evidence action queue without changing its payload."""
		return self._summarize_evidence_workflow_action_queue(queue)

	def build_question_action_matches(
		self,
		candidate: Dict[str, Any],
		workflow_action_queue: List[Dict[str, Any]],
	) -> Dict[str, Any]:
		"""Return workflow-priority signals for an intake question candidate."""
		return self._build_question_workflow_action_matches(
			candidate,
			workflow_action_queue,
		)

	def get_document_provenance_summary(self) -> Dict[str, Any]:
		"""Return the current formal document provenance summary."""
		return self._get_document_provenance_summary()

	def get_document_grounding_lane_outcome_summary(self) -> Dict[str, Any]:
		"""Return outcomes from the current document-grounding lanes."""
		return self._get_document_grounding_lane_outcome_summary()

	def get_document_grounding_recovery_action(
		self,
		*,
		provisional_evidence_workflow_action_queue: Any = None,
		alignment_evidence_tasks: Any = None,
	) -> Dict[str, Any]:
		"""Resolve the next recovery action for weak document grounding."""
		return self._get_document_grounding_recovery_action(
			provisional_evidence_workflow_action_queue=provisional_evidence_workflow_action_queue,
			alignment_evidence_tasks=alignment_evidence_tasks,
		)

	def get_document_grounding_improvement_next_action(
		self,
		*,
		provisional_evidence_workflow_action_queue: Any = None,
		alignment_evidence_tasks: Any = None,
		document_grounding_recovery_action: Any = None,
	) -> Dict[str, Any]:
		"""Resolve the next learned improvement action for document grounding."""
		return self._get_document_grounding_improvement_next_action(
			provisional_evidence_workflow_action_queue=provisional_evidence_workflow_action_queue,
			alignment_evidence_tasks=alignment_evidence_tasks,
			document_grounding_recovery_action=document_grounding_recovery_action,
		)

	# One versioned interview transition. Session identity lives here; graph
	# updates stay on Mediator.start_three_phase_process and
	# process_denoising_answer.
	INTERVIEW_CONTRACT_VERSION = "interview-transition-v1"
	SESSION_PROJECTION_VERSION = "shared-interview-session-v1"

	def bind_interview_privacy(self, policy: Any, *, user_id: str, case_id: str, data_class: str = "raw_intake") -> Dict[str, Any]:
		"""Attach the per-case privacy context used before any interview inference."""
		from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode

		resolved = policy
		if not isinstance(resolved, dict):
			resolved = privacy_policy_for_mode(user_id, case_id, "local")
		context = build_complaint_privacy_context(
			resolved,
			user_id=str(user_id or ""),
			case_id=str(case_id or user_id or ""),
			data_class=data_class,
		)
		self._mediator._interview_privacy_context = context
		self._interview_privacy_policy = context.get("policy")
		self._bound_case_id = str(context.get("case_id") or case_id or "")
		meta = getattr(self, "_interview_meta", None)
		if isinstance(meta, dict):
			meta["case_id"] = self._bound_case_id
		return context

	@property
	def interview_started(self) -> bool:
		meta = getattr(self, "_interview_meta", None)
		return bool(isinstance(meta, dict) and meta.get("started"))

	def transition_interview(
		self,
		*,
		action: str,
		narrative: Optional[str] = None,
		answer: Optional[str] = None,
		inquiry_id: Optional[str] = None,
		expected_question_revision: Optional[int] = None,
		session_projection: Optional[Dict[str, Any]] = None,
		privacy_policy: Any = None,
		user_id: Optional[str] = None,
		case_id: Optional[str] = None,
	) -> Dict[str, Any]:
		"""Start, answer, resume, or report one shared interview step.

		The pending question is the canonical graph question already stored on
		the phase manager. A caller-supplied question body is not accepted.
		"""
		normalized = str(action or "status").strip().lower()
		identity = str(user_id or getattr(self._mediator.state, "username", None) or "anonymous")
		bound_case = str(case_id or identity)
		if privacy_policy is not None or normalized in {"start", "answer"}:
			self.bind_interview_privacy(privacy_policy, user_id=identity, case_id=bound_case)
		if normalized == "resume":
			if isinstance(session_projection, dict):
				restored = self.restore_session_projection(session_projection)
				if restored.get("error"):
					return restored
			elif not self.interview_started:
				return self._interview_receipt(
					action="resume",
					status="unavailable",
					error=self._interview_error("session_missing", resumable=True),
				)
			return self._interview_receipt(action="resume", status=self._interview_runtime_status())
		if normalized == "prompt":
			return self._interview_receipt(
				action="prompt",
				status="awaiting_user",
				inquiry=self._narrative_prompt_inquiry(),
			)
		if normalized == "start":
			text = str(narrative or "").strip()
			if not text:
				return self._interview_receipt(
					action="start",
					status="awaiting_user",
					inquiry=self._narrative_prompt_inquiry(),
					error=self._interview_error("narrative_required", resumable=True),
				)
			if self.interview_started:
				return self._interview_receipt(action="start", status=self._interview_runtime_status())
			try:
				engine = self._mediator.start_three_phase_process(text)
			except Exception as exc:
				return self._failure_receipt("start", exc)
			self._remember_start(engine)
			return self._interview_receipt(action="start", status=self._interview_runtime_status(), engine=engine)
		if normalized == "answer":
			if not self.interview_started:
				return self._interview_receipt(
					action="answer",
					status="unavailable",
					error=self._interview_error("session_missing", resumable=True),
				)
			pending = self._canonical_pending_question()
			if pending is None:
				return self._interview_receipt(action="answer", status="complete")
			refusal = self._stale_refusal(pending, inquiry_id, expected_question_revision)
			if refusal is not None:
				return refusal
			answer_text = str(answer or "").strip()
			if not answer_text:
				return self._interview_receipt(
					action="answer",
					status="awaiting_user",
					error=self._interview_error("answer_required", resumable=True),
				)
			self._note_answer_quality(answer_text)
			try:
				engine = self._mediator.process_denoising_answer(pending["question"], answer_text)
			except Exception as exc:
				return self._failure_receipt("answer", exc)
			self._remember_answer(engine)
			return self._interview_receipt(action="answer", status=self._interview_runtime_status(), engine=engine)
		if normalized == "status":
			return self._interview_receipt(action="status", status=self._interview_runtime_status())
		if normalized in {"why", "review"}:
			# Read the current explanation. Do not record an answer or edit either graph.
			return self._interview_receipt(action=normalized, status=self._interview_runtime_status())
		return self._interview_receipt(
			action=normalized,
			status="refused",
			error=self._interview_error("unknown_action", resumable=True),
		)

	FACTUAL_CORRECTION_CONTRACT_VERSION = "factual-correction-v1"

	def apply_factual_correction(
		self,
		*,
		action: str,
		target_stable_id: str,
		replacement: str,
		source_context: Optional[Dict[str, Any]],
		event_id: str,
		case_id: str,
		expected_graph_revision: Optional[str],
		expected_session_revision: Optional[int],
	) -> Dict[str, Any]:
		"""Correct or retract one assertion through process_denoising_answer.

		The same event id and payload replay the stored graph result. A missing,
		cross-case, or stale target is refused before any factual record changes.
		"""
		normalized = str(action or "").strip().lower()
		if normalized not in {"correct", "retract"}:
			return self._correction_receipt(
				status="refused",
				action=normalized or "correct",
				case_id=str(case_id or ""),
				event_id=str(event_id or ""),
				target_stable_id=str(target_stable_id or ""),
				error_code="unknown_action",
			)
		if not self.interview_started:
			return self._correction_receipt(
				status="unavailable",
				action=normalized,
				case_id=str(case_id or ""),
				event_id=str(event_id or ""),
				target_stable_id=str(target_stable_id or ""),
				error_code="session_missing",
			)
		mediator = self._mediator
		kg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
		if kg is None or not hasattr(kg, "begin_answer_event"):
			return self._correction_receipt(
				status="unavailable",
				action=normalized,
				case_id=str(case_id or ""),
				event_id=str(event_id or ""),
				target_stable_id=str(target_stable_id or ""),
				error_code="capability_unavailable",
			)
		case_refusal = self._correction_case_refusal(
			kg,
			action=normalized,
			case_id=str(case_id or ""),
			event_id=str(event_id or ""),
			target_stable_id=str(target_stable_id or ""),
		)
		if case_refusal is not None:
			return case_refusal
		stable_event = str(event_id or "").strip()
		if not stable_event:
			return self._correction_receipt(
				status="refused",
				action=normalized,
				case_id=str(case_id or ""),
				event_id="",
				target_stable_id=str(target_stable_id or ""),
				error_code="missing_event",
			)
		statement = str(replacement or "")
		context = dict(source_context) if isinstance(source_context, dict) else None
		question = self._correction_question(stable_event, normalized)
		supersedes = str(target_stable_id or "").strip() if normalized == "correct" else None
		retracts = str(target_stable_id or "").strip() if normalized == "retract" else None
		from complaint_phases.knowledge_graph import AnswerEventConflict, answer_event_payload

		payload = answer_event_payload(
			question=question,
			answer=statement,
			source_context=context,
			factual_action=normalized,
			supersedes_stable_id=supersedes,
			retracts_stable_id=retracts,
		)
		try:
			prior = kg.begin_answer_event(stable_event, payload)
		except AnswerEventConflict:
			return self._correction_receipt(
				status="refused",
				action=normalized,
				case_id=str(case_id or ""),
				event_id=stable_event,
				target_stable_id=str(target_stable_id or ""),
				error_code="event_conflict",
			)
		if prior is None:
			refusal = self._correction_target_refusal(
				kg,
				action=normalized,
				case_id=str(case_id or ""),
				event_id=stable_event,
				target_stable_id=str(target_stable_id or ""),
				statement=statement,
				source_context=context,
				expected_graph_revision=expected_graph_revision,
				expected_session_revision=expected_session_revision,
			)
			if refusal is not None:
				return refusal
		phase_manager = mediator.phase_manager
		saved_questions = list(phase_manager.get_phase_data(ComplaintPhase.INTAKE, "current_questions") or [])
		saved_candidates = list(phase_manager.get_phase_data(ComplaintPhase.INTAKE, "question_candidates") or [])
		try:
			engine = mediator.process_denoising_answer(
				question,
				statement,
				answer_event_id=stable_event,
				source_context=context,
				factual_action=normalized,
				supersedes_stable_id=supersedes,
				retracts_stable_id=retracts,
			)
		except AnswerEventConflict:
			return self._correction_receipt(
				status="refused",
				action=normalized,
				case_id=str(case_id or ""),
				event_id=stable_event,
				target_stable_id=str(target_stable_id or ""),
				error_code="event_conflict",
			)
		except Exception as exc:
			return self._correction_receipt(
				status="unavailable",
				action=normalized,
				case_id=str(case_id or ""),
				event_id=stable_event,
				target_stable_id=str(target_stable_id or ""),
				error_code="capability_unavailable",
				error_type=type(exc).__name__,
			)
		finally:
			phase_manager.update_phase_data(ComplaintPhase.INTAKE, "current_questions", saved_questions)
			phase_manager.update_phase_data(ComplaintPhase.INTAKE, "question_candidates", saved_candidates)
		if prior is None:
			meta = self._interview_meta
			meta["session_revision"] = int(meta.get("session_revision") or 0) + 1
			meta["case_id"] = str(case_id or "")
			metadata = getattr(kg, "metadata", None)
			if isinstance(metadata, dict) and not metadata.get("case_id"):
				metadata["case_id"] = str(case_id or "")
		updates = engine.get("updates") if isinstance(engine, dict) else {}
		if not isinstance(updates, dict):
			updates = {}
		return self._correction_receipt(
			status="applied",
			action=normalized,
			case_id=str(case_id or ""),
			event_id=stable_event,
			target_stable_id=str(target_stable_id or ""),
			idempotent_replay=prior is not None,
			graph_mutated=prior is None,
			updates=updates,
			knowledge_graph=kg,
		)

	@classmethod
	def project_legal_context_selection(cls, projection, *, case_file, dependency_graph):
		"""Copy one persisted workflow DTO without touching a live mediator.

		The workspace owns admission and encrypted CAS. After commit, ordinary
		resume consumes this same versioned projection; facts, pending inquiry,
		answer history and extraction count retain their original identities.
		"""
		from copy import deepcopy
		if (not isinstance(projection, dict)
			or projection.get("schema_version") != cls.SESSION_PROJECTION_VERSION
			or not isinstance(projection.get("knowledge_graph"), dict)
			or not isinstance(case_file, dict)
			or not isinstance(dependency_graph, DependencyGraph)):
			raise ValueError("projection_invalid")
		revision = projection.get("session_revision")
		if type(revision) is not int or revision < 0:
			raise ValueError("projection_invalid")
		KnowledgeGraph.from_dict(projection["knowledge_graph"])
		draft = deepcopy(projection)
		draft["intake_case_file"] = deepcopy(case_file)
		draft["dependency_graph"] = dependency_graph.to_dict()
		draft["session_revision"] = revision + 1
		return _json_ready(draft)

	def export_session_projection(self) -> Optional[Dict[str, Any]]:
		"""Versioned snapshot that can rebuild KG/DG without a new extraction."""
		if not self.interview_started:
			return None
		mediator = self._mediator
		phase_manager = mediator.phase_manager
		kg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
		dg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
		if kg is None or dg is None or not hasattr(kg, "to_dict") or not hasattr(dg, "to_dict"):
			return None
		meta = dict(self._interview_meta)
		denoiser = getattr(mediator, "denoiser", None)
		history = list(getattr(denoiser, "questions_asked", []) or [])
		pending = meta.get("pending_inquiry")
		if isinstance(pending, dict):
			pending = self._explicit_grounding(pending)
			meta["pending_inquiry"] = pending
		projection = {
			"schema_version": self.SESSION_PROJECTION_VERSION,
			"contract_version": self.INTERVIEW_CONTRACT_VERSION,
			"session_id": meta.get("session_id"),
			"session_revision": meta.get("session_revision", 0),
			"phase": phase_manager.current_phase.value,
			"narrative_extraction_count": meta.get("narrative_extraction_count", 0),
			"question_revision": meta.get("question_revision", 0),
			"pending_inquiry": pending,
			"answered_inquiries": list(meta.get("answered_inquiries") or []),
			"unknown_reasons": list(meta.get("unknown_reasons") or []),
			"unavailable_reasons": list(meta.get("unavailable_reasons") or []),
			"capped_reasons": list(meta.get("capped_reasons") or []),
			"legal_sufficiency": False,
			"knowledge_graph": kg.to_dict(),
			"dependency_graph": dg.to_dict(),
			"denoiser_history": history,
			"iteration_count": phase_manager.iteration_count,
			"loss_history": list(getattr(phase_manager, "loss_history", []) or []),
			"phase_history": list(getattr(phase_manager, "phase_history", []) or []),
			"intake_case_file": phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") or {},
			"current_questions": phase_manager.get_phase_data(ComplaintPhase.INTAKE, "current_questions") or [],
			"question_candidates": phase_manager.get_phase_data(ComplaintPhase.INTAKE, "question_candidates") or [],
		}
		return _json_ready(projection)

	def restore_session_projection(self, projection: Dict[str, Any]) -> Dict[str, Any]:
		"""Restore graphs and denoiser history. Does not extract the narrative again."""
		if not isinstance(projection, dict):
			return self._interview_receipt(
				action="resume",
				status="unavailable",
				error=self._interview_error("projection_invalid", resumable=True),
			)
		if projection.get("schema_version") != self.SESSION_PROJECTION_VERSION:
			return self._interview_receipt(
				action="resume",
				status="unavailable",
				error=self._interview_error("projection_version", resumable=True),
			)
		try:
			kg = KnowledgeGraph.from_dict(projection.get("knowledge_graph") or {})
			dg = DependencyGraph.from_dict(projection.get("dependency_graph") or {})
		except Exception as exc:
			return self._failure_receipt("resume", exc)
		phase_manager = self._mediator.phase_manager
		phase_name = str(projection.get("phase") or ComplaintPhase.INTAKE.value)
		try:
			phase_manager.current_phase = ComplaintPhase(phase_name)
		except ValueError:
			phase_manager.current_phase = ComplaintPhase.INTAKE
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", kg)
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", dg)
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", projection.get("intake_case_file") or {})
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "current_questions", list(projection.get("current_questions") or []))
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "question_candidates", list(projection.get("question_candidates") or []))
		phase_manager.iteration_count = int(projection.get("iteration_count") or 0)
		phase_manager.loss_history = list(projection.get("loss_history") or [])
		phase_manager.phase_history = list(projection.get("phase_history") or [])
		denoiser = getattr(self._mediator, "denoiser", None)
		if denoiser is not None:
			denoiser.questions_asked = list(projection.get("denoiser_history") or [])
		self._interview_meta = {
			"started": True,
			"session_id": projection.get("session_id") or f"interview-{uuid4().hex[:12]}",
			"session_revision": int(projection.get("session_revision") or 0),
			"narrative_extraction_count": int(projection.get("narrative_extraction_count") or 0),
			"question_revision": int(projection.get("question_revision") or 0),
			"pending_inquiry": self._explicit_grounding(projection.get("pending_inquiry")),
			"answered_inquiries": list(projection.get("answered_inquiries") or []),
			"unknown_reasons": list(projection.get("unknown_reasons") or []),
			"unavailable_reasons": list(projection.get("unavailable_reasons") or []),
			"capped_reasons": list(projection.get("capped_reasons") or []),
		}
		return self._interview_receipt(action="resume", status=self._interview_runtime_status())

	def _remember_start(self, engine: Dict[str, Any]) -> None:
		questions = list((engine or {}).get("initial_questions") or [])
		candidates = list((engine or {}).get("question_candidates") or [])
		self._interview_meta = {
			"started": True,
			"session_id": f"interview-{uuid4().hex[:12]}",
			"session_revision": 1,
			"case_id": str(getattr(self, "_bound_case_id", "") or ""),
			"narrative_extraction_count": 1,
			"question_revision": 1 if questions else 0,
			"pending_inquiry": self._inquiry_from_question(questions[0], revision=1) if questions else None,
			"answered_inquiries": [],
			"unknown_reasons": [],
			"unavailable_reasons": [],
			"capped_reasons": ["question_cap"] if len(candidates) > len(questions) else [],
		}

	def _remember_answer(self, engine: Dict[str, Any]) -> None:
		meta = self._interview_meta
		previous = meta.get("pending_inquiry") or {}
		meta["answered_inquiries"] = list(meta.get("answered_inquiries") or []) + [
			{"inquiry_id": previous.get("inquiry_id"), "revision": previous.get("revision")}
		]
		meta["session_revision"] = int(meta.get("session_revision") or 0) + 1
		questions = list((engine or {}).get("next_questions") or [])
		candidates = list((engine or {}).get("question_candidates") or [])
		if len(candidates) > len(questions) and "question_cap" not in meta["capped_reasons"]:
			meta["capped_reasons"] = list(meta.get("capped_reasons") or []) + ["question_cap"]
		if questions:
			revision = int(meta.get("question_revision") or 0) + 1
			meta["question_revision"] = revision
			meta["pending_inquiry"] = self._inquiry_from_question(questions[0], revision=revision)
		else:
			meta["pending_inquiry"] = None

	def _note_answer_quality(self, answer_text: str) -> None:
		lowered = answer_text.lower()
		unknown_tokens = {"unknown", "not sure", "unsure", "i don't know", "i do not know", "n/a", "na", "none"}
		meta = self._interview_meta
		if lowered in unknown_tokens and "user_answer_unknown" not in meta.get("unknown_reasons", []):
			meta["unknown_reasons"] = list(meta.get("unknown_reasons") or []) + ["user_answer_unknown"]

	def _canonical_pending_question(self) -> Optional[Dict[str, Any]]:
		questions = self._mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "current_questions") or []
		if not questions or not isinstance(questions[0], dict):
			return None
		meta = self._interview_meta
		inquiry = meta.get("pending_inquiry") or self._inquiry_from_question(
			questions[0], revision=int(meta.get("question_revision") or 1)
		)
		meta["pending_inquiry"] = inquiry
		return {"inquiry": inquiry, "question": questions[0]}

	def _stale_refusal(self, pending: Dict[str, Any], inquiry_id: Optional[str], expected_revision: Optional[int]) -> Optional[Dict[str, Any]]:
		inquiry = pending["inquiry"]
		supplied_id = str(inquiry_id or "").strip()
		if supplied_id and supplied_id != inquiry.get("inquiry_id"):
			return self._interview_receipt(
				action="answer",
				status="refused",
				error=self._interview_error("stale_question", resumable=True),
			)
		if expected_revision is not None and int(expected_revision) != int(inquiry.get("revision") or 0):
			return self._interview_receipt(
				action="answer",
				status="refused",
				error=self._interview_error("stale_question", resumable=True),
			)
		return None

	def _inquiry_from_question(self, question: Dict[str, Any], *, revision: int) -> Dict[str, Any]:
		question = question if isinstance(question, dict) else {}
		qtype = str(question.get("type") or question.get("question_type") or "clarification")
		text = str(question.get("question") or "").strip()
		digest = hashlib.sha256(f"{qtype}|{text}".encode("utf-8")).hexdigest()[:16]
		reasons = []
		if not text:
			reasons.append("question_text_unavailable")
		selected = self._host_selection_for_question(question)
		host_inquiry_id = str(question.get("inquiry_id") or "").strip()
		if not host_inquiry_id.startswith("inq-") or self._reference_is_model_authored(host_inquiry_id, question):
			selected_id = str((selected or {}).get("inquiry_id") or "").strip()
			if selected_id.startswith("inq-") and not self._reference_is_model_authored(selected_id, question):
				host_inquiry_id = selected_id
			else:
				host_inquiry_id = f"inq-{digest}"
		inquiry = {
			"inquiry_id": host_inquiry_id,
			"revision": int(revision),
			"question": text,
			"question_type": qtype,
			"kind": "graph",
			"unknown_reasons": reasons,
			"legal_sufficiency": False,
			"objective_id": self._host_binding(question, selected, "objective_id"),
			"target_id": self._host_binding(question, selected, "target_id"),
			"target_revision": self._host_binding(question, selected, "target_revision"),
			"why_it_matters": self._host_why(question, selected),
			"expected_answer_contract": self._host_contract(question, selected, "expected_answer_contract"),
			"expected_update_contract": self._host_contract(question, selected, "expected_update_contract"),
			"source_references": self._host_source_references(question, selected),
		}
		inquiry["inquiry_explanation"] = self._build_inquiry_explanation(inquiry, question, selected)
		grounded = self._explicit_grounding(inquiry)
		if isinstance(grounded, dict):
			explanation = grounded.get("inquiry_explanation")
			if isinstance(explanation, dict):
				grounded["factual_target"] = explanation.get("factual_target")
				grounded["law_derived_requirement"] = explanation.get("sourced_legal_requirement")
		return grounded

	def _host_selection_for_question(self, question: Dict[str, Any]) -> Optional[Dict[str, Any]]:
		"""Read the denoiser selection contract for this question.

		A stored explained inquiry is used only when it names the same host
		target. The contract may supply an objective id the question itself did
		not carry. It must not replace a target the question did not select,
		and a model proposal is never a selection.
		"""
		if self._question_is_model_authored(question):
			return None
		target_id = str(question.get("target_id") or "").strip()
		if target_id and self._reference_is_model_authored(target_id, question):
			target_id = ""
		candidates: List[Dict[str, Any]] = []
		phase_manager = getattr(self._mediator, "phase_manager", None)
		getter = getattr(phase_manager, "get_phase_data", None)
		if callable(getter):
			try:
				current = getter(ComplaintPhase.INTAKE, "current_explained_inquiry")
				pool = getter(ComplaintPhase.INTAKE, "explained_inquiries") or []
			except Exception:
				current = None
				pool = []
			if isinstance(current, dict):
				candidates.append(current)
			if isinstance(pool, list):
				candidates.extend(item for item in pool if isinstance(item, dict))
		question_text = str(question.get("question") or "").strip()
		inquiry_id = str(question.get("inquiry_id") or "").strip()
		for item in candidates:
			if self._question_is_model_authored(item):
				continue
			same_target = bool(target_id) and target_id == str(item.get("target_id") or "").strip()
			same_inquiry = bool(inquiry_id) and inquiry_id == str(item.get("inquiry_id") or "").strip()
			same_text = bool(question_text) and question_text == str(item.get("question") or "").strip()
			if same_target or same_inquiry or (same_text and str(item.get("objective_id") or "").strip()):
				return item
		if str(question.get("objective_id") or "").strip() and target_id:
			return None
		denoiser = getattr(self._mediator, "denoiser", None)
		builder = getattr(denoiser, "_explained_inquiry_from_candidate", None)
		if not callable(builder) or not target_id:
			return None
		try:
			explained = builder(question)
		except Exception:
			return None
		if not isinstance(explained, dict):
			return None
		if str(explained.get("target_id") or "").strip() != target_id:
			return None
		if self._reference_is_model_authored(str(explained.get("objective_id") or ""), question):
			return None
		return explained

	def _question_is_model_authored(self, question: Dict[str, Any]) -> bool:
		if not isinstance(question, dict):
			return False
		origin = str(question.get("origin") or question.get("record_type") or "").strip().lower()
		return origin in {"model", "model_suggestion"}

	def _reference_is_model_authored(self, value: str, question: Dict[str, Any]) -> bool:
		text = str(value or "").strip()
		if not text or not isinstance(question, dict):
			return False
		proposal = question.get("model_proposal") if isinstance(question.get("model_proposal"), dict) else {}
		authored = {
			str(proposal.get("wording") or "").strip(),
			str(proposal.get("target_ref") or "").strip(),
			str(proposal.get("graph_id") or "").strip(),
			str(proposal.get("entity_id") or "").strip(),
			str(proposal.get("objective_id") or "").strip(),
			str(proposal.get("target_id") or "").strip(),
		}
		authored.discard("")
		return text in authored

	def _host_binding(self, question: Dict[str, Any], selected: Optional[Dict[str, Any]], key: str) -> Optional[str]:
		if self._question_is_model_authored(question):
			return None
		for source in (question, selected if isinstance(selected, dict) else None):
			if not isinstance(source, dict):
				continue
			value = str(source.get(key) or "").strip()
			if value and not self._reference_is_model_authored(value, question):
				return value
		return None

	def _host_why(self, question: Dict[str, Any], selected: Optional[Dict[str, Any]]) -> Optional[str]:
		if self._question_is_model_authored(question):
			return None
		for source in (question, selected if isinstance(selected, dict) else None):
			if not isinstance(source, dict):
				continue
			for key in ("why_it_matters", "why_answer_helps", "question_reason"):
				value = str(source.get(key) or "").strip()
				if value and not self._reference_is_model_authored(value, question):
					return value
		return None

	def _host_contract(self, question: Dict[str, Any], selected: Optional[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
		if self._question_is_model_authored(question):
			return None
		for source in (question, selected if isinstance(selected, dict) else None):
			if not isinstance(source, dict):
				continue
			value = source.get(key)
			if isinstance(value, dict):
				return dict(value)
		return None

	def _host_source_references(self, question: Dict[str, Any], selected: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
		if self._question_is_model_authored(question):
			return None
		records: List[Any] = [question]
		if isinstance(selected, dict):
			records.append(selected)
			candidate = selected.get("candidate")
			if isinstance(candidate, dict):
				records.append(candidate)
		target = question.get("unresolved_target") if isinstance(question.get("unresolved_target"), dict) else None
		if isinstance(target, dict):
			records.append(target)
		for record in records:
			if not isinstance(record, dict):
				continue
			raw = record.get("source_references")
			if not isinstance(raw, list):
				raw = record.get("source_refs")
			if not isinstance(raw, list):
				continue
			refs: List[Dict[str, Any]] = []
			for item in raw:
				if not isinstance(item, dict):
					continue
				origin = str(item.get("origin") or item.get("record_type") or "").strip().lower()
				if origin in {"model", "model_suggestion"}:
					continue
				refs.append({
					str(ref_key): ref_value
					for ref_key, ref_value in item.items()
					if ref_key not in {"text", "prompt", "wording", "narrative"}
				})
			return refs
		return None

	def _explicit_grounding(self, inquiry: Any) -> Any:
		"""Keep host bindings. A thin legacy inquiry stays explicitly unknown."""
		if not isinstance(inquiry, dict):
			return inquiry
		copied = dict(inquiry)
		objective = str(copied.get("objective_id") or "").strip()
		target = str(copied.get("target_id") or "").strip()
		if objective and target and copied.get("grounding_status") != "unknown":
			copied["grounding_status"] = "host_selected"
			if not str(copied.get("target_revision") or "").strip():
				copied["target_revision"] = "unknown"
			if isinstance(copied.get("source_references"), list):
				copied["source_references_status"] = copied.get("source_references_status") or "host_selected"
			else:
				copied["source_references"] = None
				copied["source_references_status"] = "unknown"
			self._preserve_inquiry_explanation(copied)
			return copied
		if not objective:
			copied["objective_id"] = "unknown"
		if not target:
			copied["target_id"] = "unknown"
		if not str(copied.get("target_revision") or "").strip():
			copied["target_revision"] = "unknown"
		copied["grounding_status"] = "unknown"
		if not str(copied.get("why_it_matters") or "").strip():
			copied["why_it_matters"] = None
		if not isinstance(copied.get("expected_answer_contract"), dict):
			copied["expected_answer_contract"] = None
		if not isinstance(copied.get("expected_update_contract"), dict):
			copied["expected_update_contract"] = None
		if isinstance(copied.get("source_references"), list):
			copied["source_references_status"] = "host_selected"
		else:
			copied["source_references"] = None
			copied["source_references_status"] = "unknown"
		reasons = [str(item) for item in (copied.get("unknown_reasons") or []) if str(item or "").strip()]
		if "grounding_unknown" not in reasons:
			reasons.append("grounding_unknown")
		copied["unknown_reasons"] = reasons
		copied["legal_sufficiency"] = False
		self._preserve_inquiry_explanation(copied)
		return copied

	def _preserve_inquiry_explanation(self, inquiry: Dict[str, Any]) -> None:
		"""Keep one explanation identity for this inquiry revision.

		Why and review read this object. They do not mint a new revision.
		"""
		stored = inquiry.get("inquiry_explanation")
		revision = int(inquiry.get("revision") or 0)
		if isinstance(stored, dict) and stored.get("explanation_id") and int(stored.get("revision") or -1) == revision:
			stored = dict(stored)
			stored["stores_answer"] = False
			stored["changes_law"] = False
			stored["legal_sufficiency"] = False
			inquiry["inquiry_explanation"] = stored
			return
		if isinstance(stored, dict) and stored.get("explanation_id"):
			return
		built = self._build_inquiry_explanation(inquiry, inquiry, None)
		if isinstance(built, dict):
			inquiry["inquiry_explanation"] = built
			inquiry["factual_target"] = built.get("factual_target")
			inquiry["law_derived_requirement"] = built.get("sourced_legal_requirement")

	def _clip_explanation_text(self, value: Any, limit: int = 160) -> str:
		text = " ".join(str(value or "").split())
		if len(text) > limit:
			return text[: limit - 3] + "..."
		return text

	def _explanation_graphs(self) -> tuple:
		phase_manager = getattr(self._mediator, "phase_manager", None)
		getter = getattr(phase_manager, "get_phase_data", None)
		if not callable(getter):
			return None, None
		try:
			return (
				getter(ComplaintPhase.INTAKE, "knowledge_graph"),
				getter(ComplaintPhase.INTAKE, "dependency_graph"),
			)
		except Exception:
			return None, None

	def _compact_provenance(self, record: Any, *, graph_kind: str, graph_id: str, node_id: str) -> Dict[str, Any]:
		"""Ids and source locators only. Question text and narrative stay out."""
		source = record if isinstance(record, dict) else {}
		nested = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
		attributes = source.get("attributes") if isinstance(source.get("attributes"), dict) else {}
		origin = str(source.get("origin") or source.get("source") or attributes.get("origin") or "").strip().lower()
		model_authored = origin in {"model", "model_suggestion", "llm", "inference"}
		citation = self._clip_explanation_text(
			source.get("citation") or attributes.get("citation") or nested.get("citation") or ""
		)
		span = self._clip_explanation_text(
			source.get("span") or source.get("span_id") or attributes.get("span")
			or attributes.get("source_passage_id") or nested.get("span_id") or nested.get("source_passage_id") or ""
		)
		source_id = self._clip_explanation_text(
			source.get("source_id") or attributes.get("source_id") or attributes.get("source_passage_id")
			or nested.get("source_id") or nested.get("source_passage_id") or ""
		)
		jurisdiction = self._clip_explanation_text(source.get("jurisdiction") or attributes.get("jurisdiction") or "")
		sourced = bool((citation or source_id or span) and not model_authored and graph_kind == "legal_dependency_graph")
		return {
			"status": "sourced" if sourced else "unknown",
			"graph_kind": graph_kind,
			"graph_id": graph_id or "unknown",
			"node_id": node_id or "unknown",
			"source_id": source_id or "unknown",
			"citation": citation or "unknown",
			"span": span or "unknown",
			"jurisdiction": jurisdiction or "unknown",
			"model_authored": model_authored,
			"inspectable": True,
			"changes_law": False,
		}

	def _matching_legal_node(self, dependency_graph: Any, question: Dict[str, Any], target_id: str) -> Any:
		nodes = getattr(dependency_graph, "nodes", None)
		if not isinstance(nodes, dict):
			return None
		context = question.get("context") if isinstance(question.get("context"), dict) else {}
		ranking = question.get("ranking_explanation") if isinstance(question.get("ranking_explanation"), dict) else {}
		wanted = {
			str(question.get("requirement_id") or "").strip(),
			str(context.get("requirement_id") or "").strip(),
			str(ranking.get("target_element_id") or "").strip(),
			str(question.get("target_element_id") or "").strip(),
		}
		wanted.discard("")
		legal_types = {NodeType.REQUIREMENT, NodeType.LEGAL_ELEMENT}
		for node in nodes.values():
			node_type = getattr(node, "node_type", None)
			if node_type not in legal_types:
				continue
			node_id = str(getattr(node, "id", "") or "")
			attributes = getattr(node, "attributes", None)
			element_id = ""
			if isinstance(attributes, dict):
				element_id = str(attributes.get("element_id") or attributes.get("requirement_id") or "").strip()
			if node_id in wanted or element_id in wanted:
				return node
		if target_id:
			for node in nodes.values():
				if str(getattr(node, "id", "") or "") == target_id and getattr(node, "node_type", None) in legal_types:
					return node
		return None

	def _matching_factual_entity(self, knowledge_graph: Any, target_id: str) -> Any:
		entities = getattr(knowledge_graph, "entities", None)
		if not isinstance(entities, dict) or not target_id:
			return None
		entity = entities.get(target_id)
		if entity is not None:
			return entity
		for item in entities.values():
			if str(getattr(item, "id", "") or "") == target_id:
				return item
		return None

	def _build_inquiry_explanation(
		self,
		inquiry: Dict[str, Any],
		question: Dict[str, Any],
		selected: Optional[Dict[str, Any]],
	) -> Dict[str, Any]:
		"""Why this question is asked, and which graph each part comes from.

		The factual knowledge graph and the legal dependency graph stay separate.
		A missing admitted source stays unknown. This record is not an answer and
		it does not rewrite a legal rule.
		"""
		question = question if isinstance(question, dict) else {}
		selected = selected if isinstance(selected, dict) else {}
		knowledge_graph, dependency_graph = self._explanation_graphs()
		factual_graph_id = self._clip_explanation_text(getattr(knowledge_graph, "graph_id", "") or "")
		legal_meta = getattr(dependency_graph, "metadata", None)
		legal_graph_id = ""
		if isinstance(legal_meta, dict):
			legal_graph_id = self._clip_explanation_text(legal_meta.get("graph_id") or "")
		target_id = str(inquiry.get("target_id") or question.get("target_id") or selected.get("target_id") or "").strip()
		if target_id == "unknown":
			target_id = ""
		unresolved = question.get("unresolved_target") if isinstance(question.get("unresolved_target"), dict) else {}
		if not target_id:
			target_id = str(unresolved.get("target_id") or "").strip()
		factual_label = str(
			unresolved.get("label") or unresolved.get("name") or selected.get("target_kind") or question.get("target_kind") or ""
		).strip()
		entity = self._matching_factual_entity(knowledge_graph, target_id)
		entity_record: Dict[str, Any] = {}
		if entity is not None:
			factual_label = factual_label or str(getattr(entity, "name", "") or "")
			entity_record = {
				"source": getattr(entity, "source", ""),
				"provenance": getattr(entity, "provenance", {}) if isinstance(getattr(entity, "provenance", None), dict) else {},
				"attributes": getattr(entity, "attributes", {}) if isinstance(getattr(entity, "attributes", None), dict) else {},
			}
			if not target_id:
				target_id = str(getattr(entity, "id", "") or "")
		factual_provenance = self._compact_provenance(
			entity_record,
			graph_kind="factual_knowledge_graph",
			graph_id=factual_graph_id,
			node_id=target_id,
		)
		factual_provenance["status"] = "recorded" if entity is not None else "unknown"
		factual_provenance["model_authored"] = False
		legal_node = self._matching_legal_node(dependency_graph, question, target_id)
		legal_record: Dict[str, Any] = {}
		requirement_id = ""
		requirement_label = ""
		if legal_node is not None:
			requirement_id = str(getattr(legal_node, "id", "") or "")
			requirement_label = str(getattr(legal_node, "name", "") or "")
			legal_record = {
				"citation": getattr(legal_node, "description", "") and "",
				"attributes": getattr(legal_node, "attributes", {}) if isinstance(getattr(legal_node, "attributes", None), dict) else {},
				"source": (getattr(legal_node, "attributes", {}) or {}).get("origin") if isinstance(getattr(legal_node, "attributes", None), dict) else "",
			}
			attributes = legal_record["attributes"]
			legal_record["citation"] = attributes.get("citation") or ""
			legal_record["provenance"] = attributes.get("provenance") if isinstance(attributes.get("provenance"), dict) else {}
		legal_provenance = self._compact_provenance(
			legal_record,
			graph_kind="legal_dependency_graph",
			graph_id=legal_graph_id,
			node_id=requirement_id,
		)
		law_derived = legal_provenance["status"] == "sourced"
		why = self._host_why(question, selected) or str(inquiry.get("why_it_matters") or "").strip()
		if not why:
			why = "This question is asked because that factual target is still unresolved. An answer is recorded against the target and does not change the legal rule."
		why = self._clip_explanation_text(why, 400)
		inquiry_id = str(inquiry.get("inquiry_id") or "")
		revision = int(inquiry.get("revision") or 0)
		identity_material = f"{inquiry_id}|{revision}|{target_id}|{requirement_id}"
		explanation_id = "exp-" + hashlib.sha256(identity_material.encode("utf-8")).hexdigest()[:20]
		factual_source = {
			"graph_kind": "factual_knowledge_graph",
			"graph_id": factual_graph_id or "unknown",
			"role": "factual_target",
			"node_id": target_id or "unknown",
			"provenance": factual_provenance,
		}
		legal_source = {
			"graph_kind": "legal_dependency_graph",
			"graph_id": legal_graph_id or "unknown",
			"role": "sourced_legal_requirement",
			"node_id": requirement_id or "unknown",
			"provenance": legal_provenance,
		}
		return {
			"schema": "inquiry-explanation-v1",
			"explanation_id": explanation_id,
			"revision": revision,
			"inquiry_id": inquiry_id,
			"why_asked": why,
			"factual_target": {
				"target_id": target_id or "unknown",
				"label": self._clip_explanation_text(factual_label) or "unknown",
				"kind": "factual",
				"graph_kind": "factual_knowledge_graph",
				"provenance": factual_provenance,
			},
			"sourced_legal_requirement": {
				"requirement_id": requirement_id or "unknown",
				"label": self._clip_explanation_text(requirement_label) or "unknown",
				"law_derived": law_derived,
				"graph_kind": "legal_dependency_graph",
				"provenance": legal_provenance,
			},
			"graph_sources": [factual_source, legal_source],
			"stores_answer": False,
			"changes_law": False,
			"legal_sufficiency": False,
		}

	def _narrative_prompt_inquiry(self) -> Dict[str, Any]:
		return {
			"inquiry_id": "inq-narrative",
			"revision": 0,
			"question": "Describe your complaint in plain language.",
			"question_type": "narrative",
			"kind": "narrative",
			"legal_sufficiency": False,
		}

	def _interview_runtime_status(self) -> str:
		if not self.interview_started:
			return "awaiting_user"
		pending = (self._interview_meta or {}).get("pending_inquiry")
		return "awaiting_user" if pending else "complete"

	def _failure_receipt(self, action: str, exc: BaseException) -> Dict[str, Any]:
		privacy = getattr(exc, "description", "") if exc.__class__.__name__ == "UserPresentableException" else ""
		if isinstance(privacy, str) and privacy.startswith("privacy_denied"):
			meta = getattr(self, "_interview_meta", None)
			if isinstance(meta, dict) and "privacy_refused" not in meta.get("unavailable_reasons", []):
				meta["unavailable_reasons"] = list(meta.get("unavailable_reasons") or []) + ["privacy_refused"]
			return self._interview_receipt(
				action=action,
				status="refused",
				error=self._interview_error("privacy_refused", resumable=True, detail=privacy),
			)
		return self._interview_receipt(
			action=action,
			status="unavailable",
			error=self._interview_error(
				"capability_unavailable",
				resumable=True,
				detail=type(exc).__name__,
			),
		)

	def _interview_error(self, code: str, *, resumable: bool, detail: Optional[str] = None) -> Dict[str, Any]:
		error = {"code": code, "resumable": bool(resumable), "legal_sufficiency": False}
		if detail and detail.startswith("privacy_denied"):
			error["reason"] = detail
		elif detail:
			error["error_type"] = detail
		return error

	def _interview_receipt(
		self,
		*,
		action: str,
		status: str,
		inquiry: Optional[Dict[str, Any]] = None,
		error: Optional[Dict[str, Any]] = None,
		engine: Optional[Dict[str, Any]] = None,
	) -> Dict[str, Any]:
		meta = getattr(self, "_interview_meta", None) or {}
		pending = inquiry if inquiry is not None else meta.get("pending_inquiry")
		kg = None
		try:
			kg = self._mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
		except Exception:
			kg = None
		graph = {
			"entity_count": len(getattr(kg, "entities", {}) or {}),
			"relationship_count": len(getattr(kg, "relationships", {}) or {}),
			"graph_id": getattr(kg, "graph_id", "") if kg is not None else "",
			"graph_version": getattr(kg, "graph_version", "") if kg is not None else "",
			"provenance": {},
			"legal_sufficiency": False,
		}
		if kg is not None:
			provenance = getattr(kg, "provenance", None)
			if not isinstance(provenance, dict):
				provenance = (getattr(kg, "metadata", {}) or {}).get("provenance")
			if isinstance(provenance, dict):
				graph["provenance"] = {"keys": sorted(str(key) for key in provenance.keys())}
		readiness = {}
		if isinstance(engine, dict) and isinstance(engine.get("intake_readiness"), dict):
			readiness = {
				"ready_to_advance": bool(engine["intake_readiness"].get("ready_to_advance", False)),
				"legal_sufficiency": False,
			}
		receipt = {
			"contract_version": self.INTERVIEW_CONTRACT_VERSION,
			"action": action,
			"status": status,
			"awaiting_user": status == "awaiting_user",
			"session_id": meta.get("session_id"),
			"session_revision": int(meta.get("session_revision") or 0),
			"narrative_extraction_count": int(meta.get("narrative_extraction_count") or 0),
			"inquiry": pending,
			"expected_question_revision": None if not isinstance(pending, dict) else pending.get("revision"),
			"answered_count": len(meta.get("answered_inquiries") or []),
			"graph": graph,
			"readiness": readiness,
			"unknown_reasons": list(meta.get("unknown_reasons") or []),
			"unavailable_reasons": list(meta.get("unavailable_reasons") or []),
			"capped_reasons": list(meta.get("capped_reasons") or []),
			"legal_sufficiency": False,
			"error": error,
		}
		if isinstance(pending, dict) and pending.get("unknown_reasons"):
			for reason in pending["unknown_reasons"]:
				if reason not in receipt["unknown_reasons"]:
					receipt["unknown_reasons"].append(reason)
		return receipt

	def _build_intake_workflow_action_queue(
		self,
		intake_case_file: Dict[str, Any],
		claim_pressure: Dict[str, Dict[str, Any]],
		matching_pressure: Dict[str, Dict[str, Any]],
	) -> List[Dict[str, Any]]:
		queue: List[Dict[str, Any]] = []
		intake_sections = (
			intake_case_file.get('intake_sections')
			if isinstance(intake_case_file, dict) and isinstance(intake_case_file.get('intake_sections'), dict)
			else {}
		)
		intake_focus_areas = [
			str(section_name).strip().lower()
			for section_name, payload in intake_sections.items()
			if isinstance(payload, dict) and str(payload.get('status') or '').strip().lower() != 'complete'
		]
		graph_focus_areas: List[str] = []
		for claim_type, claim_state in (claim_pressure or {}).items():
			if not isinstance(claim_state, dict):
				continue
			if int(claim_state.get('missing_count', 0) or 0) > 0:
				graph_focus_areas.append(str(claim_type).strip().lower())
		for claim_type, matching_state in (matching_pressure or {}).items():
			if not isinstance(matching_state, dict):
				continue
			if int(matching_state.get('missing_requirement_count', 0) or 0) > 0:
				for element_id in matching_state.get('missing_requirement_element_ids') or []:
					element_text = str(element_id).strip().lower()
					if element_text and element_text not in graph_focus_areas:
						graph_focus_areas.append(element_text)
		document_focus_areas = [
			name
			for name in ('proof_leads', 'harm', 'remedy')
			if name in intake_focus_areas
		]
		queue.append(
			{
				'rank': 1,
				'phase_name': 'graph_analysis',
				'status': 'warning' if graph_focus_areas else 'ready',
				'action': 'Close graph and legal-element gaps that still block complaint development.',
				'focus_areas': graph_focus_areas[:4],
			}
		)
		queue.append(
			{
				'rank': 2,
				'phase_name': 'intake_questioning',
				'status': 'warning' if intake_focus_areas else 'ready',
				'action': 'Target remaining intake sections that still prevent a complete complaint narrative.',
				'focus_areas': intake_focus_areas[:4],
			}
		)
		queue.append(
			{
				'rank': 3,
				'phase_name': 'document_generation',
				'status': 'warning' if document_focus_areas else 'ready',
				'action': 'Collect proof, harm, and remedy details needed for drafting-ready allegations.',
				'focus_areas': document_focus_areas[:4],
			}
		)
		return queue

	def _summarize_intake_workflow_action_queue(self, queue: Any) -> Dict[str, Any]:
		summary = {
			'count': 0,
			'phase_counts': {},
			'status_counts': {},
			'focus_area_counts': {},
			'actions': [],
		}
		if not isinstance(queue, list):
			return summary
		summary['count'] = len(queue)
		for item in queue:
			if not isinstance(item, dict):
				continue
			phase_name = str(item.get('phase_name') or '').strip()
			status = str(item.get('status') or '').strip()
			if phase_name:
				summary['phase_counts'][phase_name] = summary['phase_counts'].get(phase_name, 0) + 1
			if status:
				summary['status_counts'][status] = summary['status_counts'].get(status, 0) + 1
			for focus_area in item.get('focus_areas') or []:
				focus_text = str(focus_area).strip()
				if focus_text:
					summary['focus_area_counts'][focus_text] = summary['focus_area_counts'].get(focus_text, 0) + 1
			summary['actions'].append(item)
		return summary

	def _build_evidence_workflow_action_queue(
		self,
		alignment_evidence_tasks: Any,
		evidence_gaps: Any,
	) -> List[Dict[str, Any]]:
		queue: List[Dict[str, Any]] = []
		tasks = alignment_evidence_tasks if isinstance(alignment_evidence_tasks, list) else []
		for index, task in enumerate(tasks, start=1):
			if not isinstance(task, dict):
				continue
			focus_areas = [
				str(item).strip()
				for item in (
					[
						task.get('claim_element_id'),
						task.get('claim_type'),
						*(task.get('missing_fact_bundle') or []),
					]
				)
				if str(item).strip()
			]
			queue.append(
				{
					'rank': index,
					'phase_name': 'graph_analysis' if bool(task.get('blocking')) else 'document_generation',
					'status': 'warning',
					'action': str(task.get('action') or 'fill_evidence_gaps').replace('_', ' '),
					'action_code': str(task.get('action') or 'fill_evidence_gaps').strip().lower(),
					'focus_areas': focus_areas[:4],
					'claim_type': str(task.get('claim_type') or '').strip(),
					'claim_element_id': str(task.get('claim_element_id') or '').strip(),
					'claim_element_label': str(task.get('claim_element_label') or '').strip(),
					'preferred_support_kind': str(task.get('preferred_support_kind') or '').strip(),
					'missing_fact_bundle': list(task.get('missing_fact_bundle') or [])[:4],
				}
			)
		if not queue:
			for gap in (evidence_gaps if isinstance(evidence_gaps, list) else [])[:3]:
				if not isinstance(gap, dict):
					continue
				queue.append(
					{
						'rank': len(queue) + 1,
						'phase_name': 'evidence_collection',
						'status': 'warning',
						'action': str(gap.get('name') or gap.get('description') or 'close evidence gap').strip(),
						'action_code': 'fill_evidence_gaps',
						'focus_areas': [
							str(item).strip()
							for item in [gap.get('related_claim'), gap.get('name')]
							if str(item).strip()
						][:3],
						'claim_type': str(gap.get('related_claim') or '').strip(),
					}
				)
		document_grounding_recovery_action = self._get_document_grounding_recovery_action(
			provisional_evidence_workflow_action_queue=queue,
			alignment_evidence_tasks=alignment_evidence_tasks,
		)
		document_grounding_improvement_next_action = self._get_document_grounding_improvement_next_action(
			provisional_evidence_workflow_action_queue=queue,
			alignment_evidence_tasks=alignment_evidence_tasks,
			document_grounding_recovery_action=document_grounding_recovery_action,
		)
		if document_grounding_improvement_next_action:
			refinement_focus_areas = [
				str(item).strip()
				for item in [
					document_grounding_improvement_next_action.get('claim_element_id'),
					document_grounding_improvement_next_action.get('suggested_claim_element_id'),
					document_grounding_improvement_next_action.get('suggested_support_kind'),
					*(document_grounding_improvement_next_action.get('alternate_support_kinds') or []),
				]
				if str(item).strip()
			]
			refinement_entry = {
				'rank': 1,
				'phase_name': 'document_generation',
				'status': 'warning',
				'action': str(document_grounding_improvement_next_action.get('action') or 'refine_document_grounding_strategy').replace('_', ' '),
				'action_code': str(document_grounding_improvement_next_action.get('action') or 'refine_document_grounding_strategy').strip().lower(),
				'focus_areas': refinement_focus_areas[:4],
				'claim_type': str(document_grounding_improvement_next_action.get('claim_type') or '').strip(),
				'claim_element_id': str(document_grounding_improvement_next_action.get('claim_element_id') or '').strip(),
				'claim_element_label': str(document_grounding_improvement_next_action.get('claim_element_id') or '').strip(),
				'suggested_claim_element_id': str(document_grounding_improvement_next_action.get('suggested_claim_element_id') or '').strip(),
				'alternate_claim_element_ids': list(document_grounding_improvement_next_action.get('alternate_claim_element_ids') or [])[:3],
				'preferred_support_kind': str(document_grounding_improvement_next_action.get('preferred_support_kind') or '').strip(),
				'learned_support_kind': str(document_grounding_improvement_next_action.get('learned_support_kind') or '').strip(),
				'suggested_support_kind': str(document_grounding_improvement_next_action.get('suggested_support_kind') or '').strip(),
				'alternate_support_kinds': list(document_grounding_improvement_next_action.get('alternate_support_kinds') or [])[:3],
				'fact_backed_ratio_delta': float(document_grounding_improvement_next_action.get('fact_backed_ratio_delta') or 0.0),
				'learned_support_lane_priority': bool(document_grounding_improvement_next_action.get('learned_support_kind')),
				'document_grounding_strategy_refinement': True,
			}
			if not any(
				isinstance(item, dict)
				and str(item.get('action_code') or '').strip().lower() in {'refine_document_grounding_strategy', 'retarget_document_grounding'}
				for item in queue
			):
				queue = [refinement_entry, *queue]
		if document_grounding_recovery_action:
			recovery_focus_areas = [
				str(item).strip()
				for item in [
					document_grounding_recovery_action.get('claim_element_id'),
					*(document_grounding_recovery_action.get('missing_fact_bundle') or []),
				]
				if str(item).strip()
			]
			recovery_entry = {
				'rank': 1,
				'phase_name': 'document_generation',
				'status': 'warning',
				'action': 'recover document grounding',
				'action_code': 'recover_document_grounding',
				'focus_areas': recovery_focus_areas[:4],
				'claim_type': str(document_grounding_recovery_action.get('claim_type') or '').strip(),
				'claim_element_id': str(document_grounding_recovery_action.get('claim_element_id') or '').strip(),
				'claim_element_label': str(document_grounding_recovery_action.get('claim_element_id') or '').strip(),
				'preferred_support_kind': str(document_grounding_recovery_action.get('preferred_support_kind') or '').strip(),
				'missing_fact_bundle': list(document_grounding_recovery_action.get('missing_fact_bundle') or [])[:4],
				'fact_backed_ratio': float(document_grounding_recovery_action.get('fact_backed_ratio') or 0.0),
				'recovery_source': str(document_grounding_recovery_action.get('recovery_source') or '').strip(),
				'document_grounding_recovery': True,
			}
			if not any(
				isinstance(item, dict)
				and str(item.get('action_code') or '').strip().lower() == 'recover_document_grounding'
				for item in queue
			):
				if any(
					isinstance(item, dict)
					and str(item.get('action_code') or '').strip().lower() in {
						'refine_document_grounding_strategy',
						'retarget_document_grounding',
					}
					for item in queue
				):
					queue = [queue[0], recovery_entry, *queue[1:]]
				else:
					queue = [recovery_entry, *queue]
		for index, item in enumerate(queue, start=1):
			if isinstance(item, dict):
				item['rank'] = index
		return queue

	def _get_document_provenance_summary(self) -> Dict[str, Any]:
		explicit_summary = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'document_provenance_summary')
		if isinstance(explicit_summary, dict) and explicit_summary:
			return dict(explicit_summary)
		formal_complaint = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint')
		if isinstance(formal_complaint, dict):
			document_provenance_summary = formal_complaint.get('document_provenance_summary')
			if isinstance(document_provenance_summary, dict) and document_provenance_summary:
				return dict(document_provenance_summary)
		return {}

	def _get_document_grounding_lane_outcome_summary(self) -> Dict[str, Any]:
		explicit_summary = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'document_grounding_lane_outcome_summary')
		if isinstance(explicit_summary, dict) and explicit_summary:
			return dict(explicit_summary)
		formal_complaint = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint')
		if isinstance(formal_complaint, dict):
			lane_summary = formal_complaint.get('document_grounding_lane_outcome_summary')
			if isinstance(lane_summary, dict) and lane_summary:
				return dict(lane_summary)
		return {}

	def _get_document_grounding_recovery_action(
		self,
		*,
		provisional_evidence_workflow_action_queue: Any = None,
		alignment_evidence_tasks: Any = None,
	) -> Dict[str, Any]:
		explicit_action = self.phase_manager.get_phase_data(
			ComplaintPhase.FORMALIZATION,
			'document_grounding_recovery_action',
		)
		if isinstance(explicit_action, dict) and explicit_action:
			return dict(explicit_action)
		return self._recovery_action_builder(
			self._get_document_provenance_summary(),
			provisional_evidence_workflow_action_queue,
			alignment_evidence_tasks,
		)

	def _get_document_grounding_improvement_next_action(
		self,
		*,
		provisional_evidence_workflow_action_queue: Any = None,
		alignment_evidence_tasks: Any = None,
		document_grounding_recovery_action: Any = None,
	) -> Dict[str, Any]:
		explicit_action = self.phase_manager.get_phase_data(
			ComplaintPhase.FORMALIZATION,
			'document_grounding_improvement_next_action',
		)
		if isinstance(explicit_action, dict) and explicit_action:
			return dict(explicit_action)
		explicit_summary = self.phase_manager.get_phase_data(
			ComplaintPhase.FORMALIZATION,
			'document_grounding_improvement_summary',
		)
		formal_complaint = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint')
		if (not isinstance(explicit_summary, dict) or not explicit_summary) and isinstance(formal_complaint, dict):
			formal_summary = formal_complaint.get('document_grounding_improvement_summary')
			if isinstance(formal_summary, dict) and formal_summary:
				explicit_summary = dict(formal_summary)
		return self._improvement_next_action_builder(
			explicit_summary,
			document_grounding_recovery_action or self._get_document_grounding_recovery_action(
				provisional_evidence_workflow_action_queue=provisional_evidence_workflow_action_queue,
				alignment_evidence_tasks=alignment_evidence_tasks,
			),
			self._get_document_grounding_lane_outcome_summary(),
		)

	def _summarize_evidence_workflow_action_queue(self, queue: Any) -> Dict[str, Any]:
		summary = {
			'count': 0,
			'phase_counts': {},
			'status_counts': {},
			'actions': [],
		}
		if not isinstance(queue, list):
			return summary
		summary['count'] = len(queue)
		for item in queue:
			if not isinstance(item, dict):
				continue
			phase_name = str(item.get('phase_name') or '').strip()
			status = str(item.get('status') or '').strip()
			if phase_name:
				summary['phase_counts'][phase_name] = summary['phase_counts'].get(phase_name, 0) + 1
			if status:
				summary['status_counts'][status] = summary['status_counts'].get(status, 0) + 1
			summary['actions'].append(item)
		return summary

	def _build_question_workflow_action_matches(
		self,
		candidate: Dict[str, Any],
		workflow_action_queue: List[Dict[str, Any]],
	) -> Dict[str, Any]:
		explanation = candidate.get('ranking_explanation', {}) if isinstance(candidate.get('ranking_explanation'), dict) else {}
		question_text = str(candidate.get('question') or '').strip().lower()
		phase1_section = str(explanation.get('phase1_section') or candidate.get('phase1_section') or '').strip().lower()
		target_claim_type = str(explanation.get('target_claim_type') or candidate.get('target_claim_type') or '').strip().lower()
		target_element_id = str(explanation.get('target_element_id') or candidate.get('target_element_id') or '').strip().lower()
		best_rank = 99
		match_count = 0
		matched_phase = ''
		matched_focus_areas: List[str] = []
		for action in workflow_action_queue if isinstance(workflow_action_queue, list) else []:
			if not isinstance(action, dict):
				continue
			phase_name = str(action.get('phase_name') or '').strip().lower()
			rank = int(action.get('rank', 99) or 99)
			focus_areas = [
				str(item).strip().lower()
				for item in (action.get('focus_areas') or [])
				if str(item).strip()
			]
			phase_match = (
				(phase_name == 'graph_analysis' and phase1_section == 'graph_analysis')
				or (phase_name == 'intake_questioning' and phase1_section in {'chronology', 'actors', 'claim_elements', 'harm_remedy', 'proof_leads', 'contradictions'})
				or (phase_name == 'document_generation' and phase1_section in {'proof_leads', 'harm_remedy'})
			)
			focus_matches = [
				focus
				for focus in focus_areas
				if focus in {target_claim_type, target_element_id, phase1_section}
				or (focus and focus in question_text)
			]
			if phase_match or focus_matches:
				match_count += len(focus_matches) or 1
				if rank < best_rank:
					best_rank = rank
					matched_phase = phase_name
					matched_focus_areas = focus_matches or focus_areas[:2]
		return {
			'workflow_action_match_count': match_count,
			'workflow_action_rank': best_rank if best_rank != 99 else None,
			'workflow_action_phase': matched_phase,
			'workflow_action_focus_areas': matched_focus_areas,
		}

	def research_legal_source_gap(
		self,
		*,
		user_id: str,
		case_id: str,
		intake_case_file: Dict[str, Any],
		claims: Optional[List[Dict[str, Any]]] = None,
		query_terms: Optional[List[str]] = None,
		local_rows: Optional[Dict[str, Any]] = None,
		retrieval_mode: str = "cache",
		storage_available: bool = True,
		cancelled: bool = False,
		deadline_seconds: float = 5.0,
		max_bytes: int = 4096,
		max_results: int = 5,
		operation_id: Optional[str] = None,
	) -> Dict[str, Any]:
		"""Acquire and admit sources for the current legal-source gap.

		This is the typed bounded acquisition/admission operation. It does not
		record a factual answer and it does not treat a research receipt as proof.
		The same operation id returns the stored receipt and does not acquire again.
		"""
		operation_key = str(operation_id or "").strip()
		seen = getattr(self, "_research_operation_ids", None)
		if not isinstance(seen, dict):
			seen = {}
			self._research_operation_ids = seen
		if operation_key and operation_key in seen:
			prior = dict(seen[operation_key])
			prior["replayed"] = True
			prior["dispatched"] = False
			return prior
		self._legal_research_dispatch_count = int(getattr(self, "_legal_research_dispatch_count", 0) or 0) + 1
		mediator = self._mediator
		case = intake_case_file if isinstance(intake_case_file, dict) else {}
		claim_rows = [item for item in list(claims or []) if isinstance(item, dict)]
		try:
			binding = mediator.build_legal_acquisition_request(
				case,
				claim_rows,
				query_terms=query_terms,
				storage_available=storage_available,
				max_results=max_results,
				timeout_seconds=deadline_seconds,
			)
			acquisition = mediator.legal_authority_search.acquire_bounded_canonical_sources(
				binding,
				owner_id=str(user_id or ""),
				case_id=str(case_id or ""),
				purpose="public_law_citation",
				data_class="public_legal_source_graph",
				provider_kind="local",
				retrieval_mode=retrieval_mode,
				local_rows=local_rows,
				deadline_seconds=deadline_seconds,
				max_bytes=max_bytes,
				max_results=max_results,
				cancelled=bool(cancelled),
			)
		except Exception:
			acquisition = {
				"status": "unavailable",
				"error_code": "acquisition_unavailable",
				"candidates": [],
				"proof": False,
				"resume": {"resumable": True, "next_action": "retry_unavailable", "worker_stalled": False},
			}
		if not isinstance(acquisition, dict):
			acquisition = {
				"status": "unavailable",
				"error_code": "acquisition_unavailable",
				"candidates": [],
				"proof": False,
				"resume": {"resumable": True, "next_action": "retry_unavailable", "worker_stalled": False},
			}
		try:
			admitted = mediator.admit_acquired_authorities(acquisition, claim_rows, case, user_id=user_id)
		except Exception:
			admitted = {
				"acquisition": {"status": acquisition.get("status") or "unavailable", "error_code": "storage_unavailable"},
				"admission": {
					"status": "unavailable",
					"reason": "storage_unavailable",
					"decisions": [{"status": "unavailable", "reason": "storage_error"}],
					"stored_record_ids": [],
					"proof": False,
				},
			}
		admission = admitted.get("admission") if isinstance(admitted, dict) and isinstance(admitted.get("admission"), dict) else {}
		decisions = [item for item in list(admission.get("decisions") or []) if isinstance(item, dict)]
		candidates = acquisition.get("candidates") if isinstance(acquisition.get("candidates"), list) else []
		retrieved = len(candidates)
		admitted_count = sum(1 for item in decisions if item.get("status") == "admitted")
		rejected_count = sum(1 for item in decisions if item.get("status") not in {"admitted", "unavailable", "stored"})
		unavailable_count = sum(1 for item in decisions if item.get("status") == "unavailable")
		acquisition_status = str(acquisition.get("status") or "unavailable")
		admission_status = str(admission.get("status") or "")
		if acquisition_status in {"unavailable", "timeout", "error"} and unavailable_count == 0:
			unavailable_count = 1
		elif admission_status == "unavailable" and unavailable_count == 0:
			unavailable_count = 1
		if admission_status == "rejected" and rejected_count == 0:
			rejected_count = len(decisions) or 1
		resume = acquisition.get("resume") if isinstance(acquisition.get("resume"), dict) else {}
		next_action = str(resume.get("next_action") or "")
		if not next_action or next_action == "none":
			next_action = "continue_pending_inquiry"
		resumable = bool(resume.get("resumable")) or next_action in {
			"continue_pending_inquiry",
			"resolve_legal_context",
			"retry_unavailable",
			"retry_timeout",
			"supply_edition",
			"supply_owned_source_text",
			"awaiting_user",
		}
		receipt = {
			"action": "legal_research",
			"operation": "acquire_bounded_canonical_sources+admit_acquired_authorities",
			"operation_id": operation_key,
			"stored_as_answer": False,
			"proves_complaint": False,
			"legal_sufficiency": False,
			"replayed": False,
			"dispatched": True,
			"status": acquisition_status if acquisition_status != "candidates" else (admission_status or acquisition_status),
			"acquisition_status": acquisition_status,
			"admission_status": admission_status,
			"error_code": str(acquisition.get("error_code") or admission.get("reason") or ""),
			"counts": {
				"retrieved": retrieved,
				"admitted": admitted_count,
				"rejected": rejected_count,
				"unavailable": unavailable_count,
			},
			"next_action": next_action,
			"resumable": resumable,
			"worker_stalled": False,
			"proof": False,
		}
		if operation_key:
			seen[operation_key] = dict(receipt)
		return receipt

	def publish_finite_dependency_action(
		self,
		*,
		open_questions: Optional[List[Dict[str, Any]]] = None,
		open_dependencies: Optional[List[Dict[str, Any]]] = None,
		context: Optional[Dict[str, Any]] = None,
		provider_status: Any = None,
		budget_exhausted: bool = False,
		worker_stalled: bool = False,
		hook_completed: bool = False,
		cancelled: bool = False,
		loss_converged: bool = False,
		pool_empty: Optional[bool] = None,
		paused: bool = False,
		needs_review: bool = False,
	) -> Dict[str, Any]:
		"""Publish one source, evidence, or review action from the interview stop.

		The denoiser remains the only stop engine. A stalled worker, a spent
		budget, or a completed hook is not an awaiting-user session and is not
		legal sufficiency. One call makes one decision and does not read stdin.
		"""
		from complaint_phases.denoiser import publish_authorized_dependency_action

		denoiser = getattr(self._mediator, "denoiser", None)
		if denoiser is None or not hasattr(denoiser, "evaluate_interview_stop"):
			return {
				"status": "unavailable",
				"published": False,
				"authorized": False,
				"operation": None,
				"legal_sufficiency": False,
				"core_facts_complete": False,
				"proof_requirements_satisfied": False,
				"filing_ready": False,
				"awaiting_user": False,
				"worker_stalled": bool(worker_stalled),
				"busy_loop": False,
				"reads_developer_stdin": False,
				"operation_terminated": False,
				"reason": "denoiser_unavailable",
			}
		stop = denoiser.evaluate_interview_stop(
			open_questions=open_questions,
			open_dependencies=open_dependencies,
			provider_status=provider_status,
			budget_exhausted=bool(budget_exhausted),
			worker_stalled=bool(worker_stalled),
			hook_completed=bool(hook_completed),
			cancelled=bool(cancelled),
			loss_converged=bool(loss_converged),
			pool_empty=pool_empty,
			paused=bool(paused),
			needs_review=bool(needs_review),
		)
		resumed = context if isinstance(context, dict) else {}
		lane = str(stop.get("dependency_lane") or stop.get("stopping_distinction") or "")
		key = (
			str(resumed.get("case_id") or ""),
			lane,
			str(resumed.get("target_id") or ""),
		)
		attempts = self.__dict__.setdefault("_dependency_action_attempts", {})
		if resumed.get("attempt") is None:
			attempt = int(attempts.get(key) or 0)
		else:
			try:
				attempt = int(resumed.get("attempt") or 0)
			except (TypeError, ValueError):
				attempt = 0
		packet = publish_authorized_dependency_action(
			stop,
			attempt=attempt,
			context=resumed,
			hook_completed=bool(hook_completed),
		)
		packet["interview_stop"] = {
			"state": stop.get("state"),
			"outcome": stop.get("outcome"),
			"stopping_distinction": stop.get("stopping_distinction"),
			"legal_sufficiency": False,
			"filing_ready": False,
		}
		if packet.get("published"):
			attempts[key] = int(packet.get("attempt") or attempt + 1)
		elif packet.get("operation_terminated"):
			attempts[key] = max(int(attempts.get(key) or 0), attempt)
		packet["busy_loop"] = False
		packet["reads_developer_stdin"] = False
		return packet

	def declare_legal_evidence_hook_operations(self) -> Dict[str, Any]:
		"""Record the disabled legal/evidence registry. Does not write case state."""
		from mediator.hook_runtime import register_legal_evidence_operations

		receipt = register_legal_evidence_operations()
		self._legal_evidence_operation_registry = receipt
		self._legal_evidence_handlers_enabled = False
		return receipt

	def dispatch_legal_evidence_hook_operation(self, request: Any, **kwargs: Any) -> Dict[str, Any]:
		"""Refuse acquire, ingest, and refresh until later consent and storage tasks."""
		from mediator.hook_runtime import dispatch_registered_hook_operation

		if self.__dict__.get("_legal_evidence_operation_registry") is None:
			from mediator.hook_runtime import HOOK_OPERATION_RESULT_SCHEMA

			return {
				"schema": HOOK_OPERATION_RESULT_SCHEMA,
				"operation": str(request.get("operation") or "") if isinstance(request, dict) else "",
				"status": "refused",
				"code": "operation_unregistered",
				"candidate_status": "refused",
				"source_status": "refused",
				"support_status": "refused",
				"proof_status": "not_proof",
				"source_refs": [],
				"source_refs_admitted": False,
				"handler_enabled": False,
				"handler_invoked": False,
				"effect_dispatched": False,
				"provider_invoked": False,
				"backend_invoked": False,
				"storage_invoked": False,
				"writes": 0,
				"dispatch_enabled": False,
			}
		kwargs.pop("probes", None)
		kwargs.pop("effect", None)
		kwargs.pop("handler", None)
		return dispatch_registered_hook_operation(request, **kwargs)

	def accept_bound_hook_effect(self, **kwargs: Any) -> Dict[str, Any]:
		"""Admit one hook effect through the case graph's revision ledger.

		Candidate acquisitions stay on this service. They are not written into
		the graph, the pending inquiry, or the saved case, and a receipt is not
		treated as durability or proof. No second session database is opened.
		"""
		from mediator.hook_runtime import accept_bound_hook_effect

		graph = kwargs.pop("graph", None)
		if graph is None:
			phase_manager = getattr(self._mediator, "phase_manager", None)
			getter = getattr(phase_manager, "get_phase_data", None)
			graph = getter(ComplaintPhase.INTAKE, "knowledge_graph") if getter is not None else None
		meta = self.__dict__.get("_interview_meta")
		if "pending_inquiry" not in kwargs:
			kwargs["pending_inquiry"] = meta.get("pending_inquiry") if isinstance(meta, dict) else None
		if "saved_case" not in kwargs:
			phase_manager = getattr(self._mediator, "phase_manager", None)
			getter = getattr(phase_manager, "get_phase_data", None)
			loaded = getter(ComplaintPhase.INTAKE, "intake_case_file") if getter is not None else None
			kwargs["saved_case"] = loaded if isinstance(loaded, dict) else {}
		log = self.__dict__.setdefault("_hook_candidate_acquisitions", [])
		kwargs.setdefault("acquisition_log", log)
		pending_before = kwargs.get("pending_inquiry")
		saved_before = kwargs.get("saved_case")
		result = accept_bound_hook_effect(graph=graph, **kwargs)
		if isinstance(meta, dict) and meta.get("pending_inquiry") is not pending_before and "pending_inquiry" not in kwargs:
			result["mutated_pending_inquiry"] = True
		if saved_before is not kwargs.get("saved_case"):
			result["mutated_saved_case"] = True
		result["candidate_log_count"] = len(log)
		result["receipt_is_durable"] = False
		result["receipt_is_proof"] = False
		return result


	def refresh_legal_dependency_graph(
		self, *, case_id: str, actor_principal_id: str, correction_kind: str,
		case_revision: int, consent_generation: int, consent_revoked: bool,
		grant_revision: int, granted_actions: Any, legal_source_hashes: Any,
		operation_id: str, expected_case_revision: int, expected_consent_generation: int,
		expected_grant_revision: int, expected_dependency_generation: int,
		links=None, questions=None, proof_obligations=None, successors=None,
		canonical_source_records=None,
	) -> Dict[str, Any]:
		"""Re-read canonical scoped sources and refresh an actual isolated workflow.

		The workspace supplies authenticated live bindings and, for private GUI
		cases, only records joined to its current encrypted manifest. It commits
		the exported projection through its late-checked private CAS. Client rows
		are never installed as links, questions, sources or proof obligations.
		"""
		from copy import deepcopy
		from mediator.interface import Mediator
		from integrations.ipfs_datasets.legal import adapt_sourced_legal_requirements

		mediator = self._mediator
		case_file = self._refresh_case_file() if isinstance(mediator, Mediator) else {}
		old_ledger = case_file.get("legal_graph_refresh")
		ledger = deepcopy(old_ledger) if isinstance(old_ledger, dict) else {}
		ledger.setdefault("case_id", case_id)
		ledger.setdefault("dependency_generation", 0)
		ledger.setdefault("operation_version", 0)
		ledger.setdefault("legal_source_hashes", [])
		ledger.setdefault("records", {"links": [], "questions": [], "proof_obligations": []})
		ledger.setdefault("operations", {})
		key = str(operation_id or "")
		kind = str(correction_kind or "")
		def refuse(code):
			return self._refresh_receipt(status="refused", case_id=case_id,
				actor_principal_id=actor_principal_id, operation_id=key,
				correction_kind=kind, ledger=ledger, error_code=code, applied=False)
		if (not isinstance(mediator, Mediator) or not isinstance(ledger["operations"], dict)
			or not isinstance(ledger["records"], dict)
			or any(type(ledger[field]) is not int or ledger[field] < 0
				for field in ("dependency_generation", "operation_version"))
			or any(not isinstance(bucket, list) for bucket in ledger["records"].values())):
			return refuse("actual_workflow_unavailable")
		graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
		kg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
		if not isinstance(graph, DependencyGraph) or not isinstance(kg, KnowledgeGraph):
			return refuse("actual_workflow_unavailable")
		if (not key or key != key.strip() or len(key) > 128
			or not case_id or not actor_principal_id or kind not in {"source", "context", "factual"}):
			return refuse("refresh_field")
		if any(value for value in (links, questions, proof_obligations, successors)):
			return refuse("caller_graph_rows_not_accepted")
		if ledger["case_id"] != case_id:
			return refuse("cross_case")
		ints = (case_revision, consent_generation, grant_revision, expected_case_revision,
			expected_consent_generation, expected_grant_revision, expected_dependency_generation)
		if any(type(value) is not int or value < 0 for value in ints):
			return refuse("refresh_field")
		if consent_revoked is True:
			return refuse("consent_revoked")
		if not isinstance(granted_actions, (list, tuple, set, frozenset)) or "case.update" not in granted_actions:
			return refuse("actor_not_permitted")
		for expected, live, code in (
			(expected_case_revision, case_revision, "stale_case_revision"),
			(expected_consent_generation, consent_generation, "stale_consent"),
			(expected_grant_revision, grant_revision, "stale_actor_grant")):
			if expected != live:
				return refuse(code)
		try:
			hashes = self._refresh_hashes(legal_source_hashes)
		except ValueError:
			return refuse("stale_legal_source_hash")
		try:
			manifest_hashes = self._refresh_manifest_hashes(mediator, canonical_source_records)
			manifest_digest = hashlib.sha256(json.dumps(canonical_source_records,
				sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
		except (ValueError, TypeError):
			return refuse("canonical_source_scope_invalid")
		if manifest_hashes is not None and manifest_hashes != hashes:
			return refuse("current_source_scope_mismatch")
		request = {"case_id": case_id, "actor_principal_id": actor_principal_id,
			"correction_kind": kind, "case_revision": case_revision,
			"consent_generation": consent_generation, "grant_revision": grant_revision,
			"legal_source_hashes": list(hashes), "expected_dependency_generation": expected_dependency_generation,
			"manifest_source_scope": canonical_source_records is not None,
			"manifest_source_scope_sha256": manifest_digest}
		fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
		current_basis = self._refresh_snapshot_basis(case_file, graph, kg)
		stored = ledger["operations"].get(key)
		if isinstance(stored, dict):
			if stored.get("request_fingerprint") != fingerprint:
				return refuse("operation_conflict")
			if (stored.get("after_basis_sha256") != current_basis
				or stored.get("dependency_generation") != ledger["dependency_generation"]):
				return refuse("stale_operation_scope")
			receipt = deepcopy(stored["receipt"])
			receipt.update(replayed=True, applied=False, graph_mutated=False)
			return receipt
		if expected_dependency_generation != ledger["dependency_generation"]:
			return refuse("stale_dependency_generation")
		before_case, before_graph = deepcopy(case_file), deepcopy(graph.to_dict())
		old_nodes = [node for node in graph.nodes.values()
			if node.attributes.get("dependency_class") == "legally_sourced_requirement"]
		rule_ids = sorted({str(node.attributes.get("rule_id")) for node in old_nodes if node.attributes.get("rule_id")})
		change = {"rule_ids": rule_ids, "request_id": key,
			"operation": "revalidate_current_legal_dependencies",
			"source_preimage": hashlib.sha256(json.dumps(list(hashes)).encode()).hexdigest(),
			"context_preimage": hashlib.sha256(json.dumps(case_file.get("legal_context") or {},
				sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
		# The real source owner reconciles actual requirements, then its DG owner
		# invalidates/rekeys their support, proof caches and question targets.
		try:
			report = mediator.refresh_verified_legal_dependencies(change, source_records=canonical_source_records)
			selection = mediator.resolve_intake_legal_selection(
				[{"type": node.attributes.get("claim_type")} for node in graph.get_nodes_by_type(NodeType.CLAIM)],
				case_file)
			actual_hashes = set()
			for node in graph.nodes.values():
				attrs = node.attributes
				if attrs.get("dependency_class") != "legally_sourced_requirement" or attrs.get("source_available") is not True:
					continue
				claim = str(attrs.get("claim_type") or "unknown")
				entries = adapt_sourced_legal_requirements({claim: [attrs]}, legal_context=selection["legal_context"])[claim]
				if entries and entries[0].get("intake_requirement_status") == "source_bound":
					actual_hashes.add(str(entries[0]["source_hash"]))
			# Manifest custody and governing admission are different facts. Unknown
			# context may retain owned bytes while admitting no legal requirement.
			if ((manifest_hashes is None and tuple(sorted(actual_hashes)) != hashes)
				or (manifest_hashes is not None and not actual_hashes.issubset(set(hashes)))):
				raise ValueError("current_source_scope_mismatch")
			if report.get("user_facts_modified") is True:
				raise ValueError("factual_state_changed")
			if "legal_context_applicability" in before_case:
				# Source lookup re-derives temporary question/change metadata. It
				# must not rewrite the separate explicit-selection owner's snapshot.
				old_context = before_case.get("legal_context")
				new_context = case_file.get("legal_context")
				transient = {"changed_fields", "questions", "status"}
				if (not isinstance(old_context, dict) or not isinstance(new_context, dict)
					or {k: v for k, v in old_context.items() if k not in transient}
					!= {k: v for k, v in new_context.items() if k not in transient}):
					raise ValueError("current_legal_context_changed")
				for field in list(case_file):
					if field.startswith("legal_context"):
						case_file.pop(field)
				case_file.update({k: deepcopy(v) for k, v in before_case.items() if k.startswith("legal_context")})
		except Exception as exc:
			restored = DependencyGraph.from_dict(deepcopy(before_graph))
			graph.__dict__.clear()
			graph.__dict__.update(restored.__dict__)
			case_file.clear()
			case_file.update(before_case)
			mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", graph)
			mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", case_file)
			return refuse(str(exc) if str(exc) in {"current_source_scope_mismatch", "current_legal_context_changed"}
				else "actual_refresh_unavailable")
		generation = ledger["dependency_generation"] + 1
		invalidated = self._invalidate_refresh_records(ledger, key, kind)
		current_records = self._refresh_records_from_actual_graph(graph)
		for name, rows in current_records.items():
			for row in rows:
				row.update(status="current", dependency_generation=generation, installed_by=key,
					legal_source_hashes=list(hashes), proof=False, legal_sufficiency=False)
				ledger["records"].setdefault(name, []).append(row)
		ledger.update(dependency_generation=generation, operation_version=ledger["operation_version"] + 1,
			legal_source_hashes=list(hashes), case_revision=case_revision, consent_generation=consent_generation,
			consent_revoked=False, grant_revision=grant_revision, actor_principal_id=actor_principal_id)
		case_file["legal_graph_refresh"] = ledger
		receipt = self._refresh_receipt(status="applied", case_id=case_id, actor_principal_id=actor_principal_id,
			operation_id=key, correction_kind=kind, ledger=ledger, error_code=None, applied=True, invalidated=invalidated)
		receipt.update(graph_mutated=before_graph != graph.to_dict(), dependency_refresh=deepcopy(report),
			admitted_source_hashes=sorted(actual_hashes), manifest_source_scope_sha256=manifest_digest,
			actual_graph_sha256=self._refresh_snapshot_basis({}, graph, kg),
			limitations=["A real canonical source/DG refresh was performed on this isolated snapshot.",
				"Caller rows are not installed; source membership comes from the current manifest scope.",
				"Request correction_kind describes intent; dependency_refresh reports actual affected nodes.",
				"Neither source admission nor this refresh proves legal sufficiency."])
		ledger["operations"][key] = {"request_fingerprint": fingerprint,
			"after_basis_sha256": self._refresh_snapshot_basis(case_file, graph, kg),
			"dependency_generation": generation, "receipt": deepcopy(receipt)}
		return receipt

	@staticmethod
	def _refresh_manifest_hashes(mediator, records):
		"""Prove owned source bytes, separately from current-context admission.

		The public workspace owner joins these records to its current encrypted
		manifest before calling. This check supplies no membership or legal
		authority; the existing source owner still evaluates each actual rule.
		"""
		if records is None:
			return None
		if isinstance(records, dict):
			if (len(records) > 32 or any(not isinstance(key, str) or not key.strip()
				or len(key) > 128 or not isinstance(rows, list) for key, rows in records.items())):
				raise ValueError("source_scope_bound")
			flat = [row for rows in records.values() for row in rows]
		elif isinstance(records, list):
			flat = records
		else:
			raise ValueError("source_scope_type")
		if len(flat) > 128:
			raise ValueError("source_record_bound")
		hashes = set()
		for raw in flat:
			if not isinstance(raw, dict) or not mediator._bounded_legal_source_record(raw):
				raise ValueError("source_record_bound")
			record = mediator._reveal_stored_authority_record(raw)
			if not isinstance(record, dict) or record.get("source_unreadable") is True:
				raise ValueError("source_unreadable")
			text = record.get("source_text", record.get("content"))
			if not isinstance(text, str) or not text or len(text) > 65536:
				raise ValueError("source_text_missing")
			digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
			present = []
			for fields in (record, record.get("metadata"), record.get("provenance")):
				if isinstance(fields, dict):
					present.extend(fields[key] for key in ("source_hash", "authority_text_sha256")
						if key in fields and fields[key] not in (None, ""))
			if not present or any(value != digest for value in present):
				raise ValueError("source_hash_mismatch")
			if "content" in record and record["content"] != text:
				raise ValueError("source_body_alias_mismatch")
			hashes.add(digest)
		return tuple(sorted(hashes))

	@staticmethod
	def _refresh_snapshot_basis(case_file, graph, knowledge_graph):
		from copy import deepcopy
		case = deepcopy(case_file)
		case.pop("legal_graph_refresh", None)
		payload = _json_ready({"case_file": case, "dependency_graph": graph.to_dict(),
			"knowledge_graph": knowledge_graph.to_dict()})
		return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

	@staticmethod
	def _refresh_records_from_actual_graph(graph):
		records = {"links": [], "questions": [], "proof_obligations": []}
		for edge in graph.dependencies.values():
			records["links"].append({"id": edge.id, "record_kind": "link", "text": "",
				"content_hash": "", "source_id": edge.source_id, "target_id": edge.target_id})
		for node in graph.nodes.values():
			attrs = node.attributes
			if attrs.get("dependency_class") != "legally_sourced_requirement" or attrs.get("source_available") is not True:
				continue
			if attrs.get("question_target_id"):
				records["questions"].append({"id": attrs["question_target_id"], "record_kind": "question",
					"text": node.description, "content_hash": attrs.get("source_hash", ""), "requirement_id": node.id})
			if attrs.get("proof_identity"):
				records["proof_obligations"].append({"id": attrs["proof_identity"], "record_kind": "proof_obligation",
					"text": "", "content_hash": attrs.get("source_hash", ""), "requirement_id": node.id})
		return records

	def accept_legal_refresh_late_result(
		self, *, case_id: str, actor_principal_id: str, case_revision: int,
		consent_generation: int, consent_revoked: bool, grant_revision: int,
		granted_actions: Any, legal_source_hashes: Any, dependency_generation: int,
		operation_id: str, claimed=None,
	) -> Dict[str, Any]:
		"""Revalidate an existing server-computed refresh, never install client rows.

		No asynchronous producer capability is issued by this workflow. A caller
		can refer to a persisted refresh receipt and prove it is still current;
		arbitrary late worker/model links or proof rows are explicitly unavailable.
		"""
		from copy import deepcopy
		from mediator.interface import Mediator
		case_file = self._refresh_case_file() if isinstance(self._mediator, Mediator) else {}
		raw = case_file.get("legal_graph_refresh")
		ledger = deepcopy(raw) if isinstance(raw, dict) else {}
		ledger.setdefault("records", {"links": [], "questions": [], "proof_obligations": []})
		ledger.setdefault("operations", {})
		def refuse(code):
			return self._late_receipt(status="refused", case_id=case_id,
				actor_principal_id=actor_principal_id, operation_id=str(operation_id or ""),
				ledger=ledger, error_code=code, applied=False)
		if not isinstance(self._mediator, Mediator) or not isinstance(claimed, dict):
			return refuse("actual_workflow_unavailable")
		if (not isinstance(operation_id, str) or not operation_id or operation_id != operation_id.strip()
			or len(operation_id) > 128 or any(key in claimed and (type(claimed[key]) is not int or claimed[key] < 0)
				for key in ("case_revision", "consent_generation", "grant_revision", "dependency_generation"))):
			return refuse("refresh_field")
		if any(claimed.get(key) for key in ("links", "questions", "proof_obligations", "successors", "result", "model_output")):
			return refuse("late_result_capability_unavailable")
		if consent_revoked is True:
			return refuse("consent_revoked")
		if not isinstance(granted_actions, (list, tuple, set, frozenset)) or "case.update" not in granted_actions:
			return refuse("actor_not_permitted")
		if any(type(v) is not int or v < 0 for v in
			(case_revision, consent_generation, grant_revision, dependency_generation)):
			return refuse("refresh_field")
		try:
			hashes = self._refresh_hashes(legal_source_hashes)
		except ValueError:
			return refuse("stale_legal_source_hash")
		for key, value, code in (
			("case_id", case_id, "cross_case"), ("actor_principal_id", actor_principal_id, "stale_actor_grant"),
			("case_revision", case_revision, "stale_case_revision"),
			("consent_generation", consent_generation, "stale_consent"),
			("grant_revision", grant_revision, "stale_actor_grant"),
			("dependency_generation", dependency_generation, "stale_dependency_generation")):
			if ledger.get(key) != value or (key in claimed and claimed[key] != value):
				return refuse(code)
		if tuple(ledger.get("legal_source_hashes") or ()) != hashes:
			return refuse("stale_legal_source_hash")
		if "legal_source_hashes" in claimed:
			try:
				if self._refresh_hashes(claimed["legal_source_hashes"]) != hashes:
					return refuse("stale_legal_source_hash")
			except ValueError:
				return refuse("stale_legal_source_hash")
		if claimed.get("consent_revoked") is True:
			return refuse("consent_revoked")
		parent_key = str(claimed.get("refresh_operation_id") or "")
		stored = ledger["operations"].get(parent_key)
		graph = self._mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
		kg = self._mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
		if (not isinstance(stored, dict) or not isinstance(stored.get("receipt"), dict)
			or not isinstance(graph, DependencyGraph) or not isinstance(kg, KnowledgeGraph)):
			return refuse("server_refresh_receipt_required")
		if (stored.get("dependency_generation") != dependency_generation
			or stored.get("after_basis_sha256") != self._refresh_snapshot_basis(case_file, graph, kg)):
			return refuse("stale_late_result")
		receipt = self._late_receipt(status="verified_current", case_id=case_id,
			actor_principal_id=actor_principal_id, operation_id=str(operation_id or ""),
			ledger=ledger, error_code=None, applied=False)
		receipt.update(parent_operation_id=parent_key, graph_mutated=False, server_refresh_verified=True,
			client_result_installed=False, asynchronous_result_installation="unavailable",
			limitations=["Only an existing persisted server-computed refresh is revalidated.",
				"No client/model rows or unregistered asynchronous results are installed.",
				"This receipt does not prove legal sufficiency."])
		return receipt

	def _refresh_case_file(self) -> Dict[str, Any]:
		mediator = self._mediator
		phase_manager = getattr(mediator, "phase_manager", None)
		if phase_manager is not None and hasattr(phase_manager, "get_phase_data"):
			stored = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
			if isinstance(stored, dict):
				return stored
		stored = getattr(mediator, "intake_case_file", None)
		if not isinstance(stored, dict):
			stored = {}
			setattr(mediator, "intake_case_file", stored)
		return stored

	def _refresh_ledger(self, case_file: Dict[str, Any], case_id: str) -> Dict[str, Any]:
		ledger = case_file.get("legal_graph_refresh")
		if not isinstance(ledger, dict) or ledger.get("case_id") not in {None, "", case_id}:
			ledger = {
				"case_id": case_id,
				"dependency_generation": 0,
				"operation_version": 0,
				"legal_source_hashes": [],
				"records": {"links": [], "questions": [], "proof_obligations": []},
				"operations": {},
			}
		records = ledger.get("records")
		if not isinstance(records, dict):
			records = {}
			ledger["records"] = records
		for name in ("links", "questions", "proof_obligations"):
			if not isinstance(records.get(name), list):
				records[name] = []
		if not isinstance(ledger.get("operations"), dict):
			ledger["operations"] = {}
		return ledger

	def _refresh_binding_refusal(self, **kwargs: Any) -> Optional[str]:
		ledger = kwargs["ledger"]
		if kwargs["consent_revoked"] is True:
			return "consent_revoked"
		actions = kwargs["granted_actions"]
		if not isinstance(actions, (list, tuple, set, frozenset)) or "case.update" not in set(actions):
			return "actor_not_permitted"
		if not str(kwargs["actor_principal_id"] or "").strip() or not str(kwargs["case_id"] or "").strip():
			return "actor_not_permitted"
		if int(kwargs["expected_case_revision"]) != int(kwargs["case_revision"]):
			return "stale_case_revision"
		if int(kwargs["expected_consent_generation"]) != int(kwargs["consent_generation"]):
			return "stale_consent"
		if int(kwargs["expected_grant_revision"]) != int(kwargs["grant_revision"]):
			return "stale_actor_grant"
		if int(kwargs["expected_dependency_generation"]) != int(ledger.get("dependency_generation") or 0):
			return "stale_dependency_generation"
		try:
			self._refresh_hashes(kwargs["legal_source_hashes"])
		except ValueError:
			return "stale_legal_source_hash"
		bound_case = str(ledger.get("case_id") or "")
		if bound_case and bound_case != str(kwargs["case_id"]):
			return "cross_case"
		return None

	def _late_result_refusal(self, **kwargs: Any) -> Optional[str]:
		ledger = kwargs["ledger"]
		if int(ledger.get("dependency_generation") or 0) < 1:
			return "stale_dependency_generation"
		if kwargs["consent_revoked"] is True or ledger.get("consent_revoked") is True:
			return "consent_revoked"
		actions = kwargs["granted_actions"]
		if not isinstance(actions, (list, tuple, set, frozenset)) or "case.update" not in set(actions):
			return "actor_not_permitted"
		claim = kwargs["claimed"]
		try:
			hashes = self._refresh_hashes(kwargs["legal_source_hashes"])
		except ValueError:
			return "stale_legal_source_hash"
		if hashes != tuple(ledger.get("legal_source_hashes") or ()):
			return "stale_legal_source_hash"
		comparisons = (
			("actor_principal_id", str(kwargs["actor_principal_id"]), str(ledger.get("actor_principal_id") or ""), "stale_actor_grant"),
			("case_revision", int(kwargs["case_revision"]), int(ledger.get("case_revision") or 0), "stale_case_revision"),
			("consent_generation", int(kwargs["consent_generation"]), int(ledger.get("consent_generation") or 0), "stale_consent"),
			("grant_revision", int(kwargs["grant_revision"]), int(ledger.get("grant_revision") or 0), "stale_actor_grant"),
			("dependency_generation", int(kwargs["dependency_generation"]), int(ledger.get("dependency_generation") or 0), "stale_dependency_generation"),
			("case_id", str(kwargs["case_id"]), str(ledger.get("case_id") or ""), "cross_case"),
		)
		for key, live, recorded, code in comparisons:
			if live != recorded:
				return code
			if key in claim and claim.get(key) != live and not (key == "case_id" and claim.get(key) in {None, ""}):
				return code
		claimed_hashes = claim.get("legal_source_hashes")
		if isinstance(claimed_hashes, list):
			try:
				if self._refresh_hashes(claimed_hashes) != hashes:
					return "stale_legal_source_hash"
			except ValueError:
				return "stale_legal_source_hash"
		if claim.get("consent_revoked") is True:
			return "consent_revoked"
		if claim.get("actor_principal_id") not in {None, "", str(kwargs["actor_principal_id"])}:
			return "stale_actor_grant"
		return None

	def _refresh_hashes(self, values: Any) -> tuple:
		if not isinstance(values, list):
			raise ValueError("hashes")
		cleaned = []
		for item in values:
			if (not isinstance(item, str) or len(item) != 64
				or any(ch not in "0123456789abcdef" for ch in item)):
				raise ValueError("hashes")
			cleaned.append(item)
		return tuple(sorted(set(cleaned)))

	def _refresh_rows(self, rows: Any, record_kind: str) -> List[Dict[str, Any]]:
		if rows is None:
			return []
		if not isinstance(rows, list):
			raise ValueError("rows")
		cleaned = []
		seen = set()
		for item in rows:
			if not isinstance(item, dict):
				raise ValueError("rows")
			ident = item.get("id")
			if not isinstance(ident, str) or not ident or ident != ident.strip() or ident in seen:
				raise ValueError("rows")
			seen.add(ident)
			content_hash = item.get("content_hash", "")
			if not isinstance(content_hash, str):
				raise ValueError("rows")
			text = item.get("text", "")
			if not isinstance(text, str):
				raise ValueError("rows")
			cleaned.append({
				"id": ident,
				"record_kind": record_kind,
				"text": text[:500],
				"content_hash": content_hash,
				"status": "current",
				"proof": False,
				"legal_sufficiency": False,
			})
		return cleaned

	def _invalidate_refresh_records(self, ledger: Dict[str, Any], operation_id: str, kind: str) -> Dict[str, int]:
		counts = {}
		reason = "stale_after_%s_correction" % kind
		for name, bucket in ledger["records"].items():
			count = 0
			for item in bucket:
				if item.get("status") == "current":
					item["status"] = "invalidated"
					item["invalidated_reason"] = reason
					item["invalidated_by"] = operation_id
					item["invalidated_generation"] = int(ledger.get("dependency_generation") or 0)
					count += 1
			counts[name] = count
		return counts

	def _refresh_receipt(self, **kwargs: Any) -> Dict[str, Any]:
		ledger = kwargs["ledger"]
		records = ledger.get("records") if isinstance(ledger.get("records"), dict) else {}
		return {
			"task_id": "CIMP-GUI-28",
			"action": "legal_dependency_refresh",
			"status": kwargs["status"],
			"applied": bool(kwargs["applied"]),
			"replayed": False,
			"graph_mutated": bool(kwargs["applied"]),
			"operation_id": kwargs["operation_id"],
			"operation_version": int(ledger.get("operation_version") or 0),
			"dependency_generation": int(ledger.get("dependency_generation") or 0),
			"correction_kind": kwargs["correction_kind"],
			"case_id": kwargs["case_id"],
			"actor_principal_id": kwargs["actor_principal_id"],
			"case_revision": int(ledger.get("case_revision") or 0) if kwargs["applied"] else int(ledger.get("case_revision") or 0),
			"consent_generation": int(ledger.get("consent_generation") or 0),
			"grant_revision": int(ledger.get("grant_revision") or 0),
			"legal_source_hashes": list(ledger.get("legal_source_hashes") or []),
			"invalidated": kwargs.get("invalidated") or {"links": 0, "questions": 0, "proof_obligations": 0},
			"links": [dict(item) for item in records.get("links") or []],
			"questions": [dict(item) for item in records.get("questions") or []],
			"proof_obligations": [dict(item) for item in records.get("proof_obligations") or []],
			"proof": False,
			"legal_sufficiency": False,
			"error": None if not kwargs.get("error_code") else {"code": kwargs["error_code"], "resumable": True},
			"limitations": [
				"A refresh versions the dependency generation and invalidates prior links, questions, and proof obligations.",
				"User narratives and model text do not become legal rules.",
				"This receipt is not a proof of legal sufficiency.",
				"WebSocket and SSE transports are not supported.",
			],
		}

	def _late_receipt(self, **kwargs: Any) -> Dict[str, Any]:
		ledger = kwargs["ledger"]
		records = ledger.get("records") if isinstance(ledger.get("records"), dict) else {}
		return {
			"task_id": "CIMP-GUI-28",
			"action": "legal_refresh_late_result",
			"status": kwargs["status"],
			"applied": bool(kwargs["applied"]),
			"replayed": False,
			"graph_mutated": bool(kwargs["applied"]),
			"operation_id": kwargs["operation_id"],
			"operation_version": int(ledger.get("operation_version") or 0),
			"dependency_generation": int(ledger.get("dependency_generation") or 0),
			"case_id": kwargs["case_id"],
			"actor_principal_id": str(ledger.get("actor_principal_id") or kwargs["actor_principal_id"]),
			"case_revision": int(ledger.get("case_revision") or 0),
			"consent_generation": int(ledger.get("consent_generation") or 0),
			"grant_revision": int(ledger.get("grant_revision") or 0),
			"legal_source_hashes": list(ledger.get("legal_source_hashes") or []),
			"links": [dict(item) for item in records.get("links") or []],
			"questions": [dict(item) for item in records.get("questions") or []],
			"proof_obligations": [dict(item) for item in records.get("proof_obligations") or []],
			"proof": False,
			"legal_sufficiency": False,
			"error": None if not kwargs.get("error_code") else {"code": kwargs["error_code"], "resumable": True},
			"limitations": [
				"Only an existing server-computed refresh can be revalidated; caller rows are not installed.",
				"Invalidated links, questions, and proof obligations stay invalidated.",
				"This receipt is not a proof of legal sufficiency.",
				"WebSocket and SSE transports are not supported.",
			],
		}

	def _bound_case_ids(self, knowledge_graph) -> Dict[str, str]:
		meta = getattr(self, "_interview_meta", None) or {}
		privacy = getattr(self._mediator, "_interview_privacy_context", None)
		graph_case = ""
		metadata = getattr(knowledge_graph, "metadata", None)
		if isinstance(metadata, dict):
			graph_case = str(metadata.get("case_id") or "")
		privacy_case = str(privacy.get("case_id") or "") if isinstance(privacy, dict) else ""
		return {
			"session": str(meta.get("case_id") or getattr(self, "_bound_case_id", "") or ""),
			"privacy": privacy_case,
			"graph": graph_case,
		}

	def _correction_case_refusal(self, knowledge_graph, *, action, case_id, event_id, target_stable_id):
		bound = self._bound_case_ids(knowledge_graph)
		requested = str(case_id or "")
		present = [value for value in bound.values() if value]
		if not requested or not present or any(value != requested for value in present):
			return self._correction_receipt(
				status="refused",
				action=action,
				case_id=requested,
				event_id=event_id,
				target_stable_id=target_stable_id,
				error_code="cross_case",
				knowledge_graph=knowledge_graph,
			)
		return None

	def _correction_target_refusal(
		self,
		knowledge_graph,
		*,
		action,
		case_id,
		event_id,
		target_stable_id,
		statement,
		source_context,
		expected_graph_revision,
		expected_session_revision,
	):
		from mediator.hook_runtime import graph_revision_token

		current_session = int((self._interview_meta or {}).get("session_revision") or 0)
		current_graph = graph_revision_token(knowledge_graph)
		stale = (
			expected_session_revision is None
			or int(expected_session_revision) != current_session
			or str(expected_graph_revision or "") != current_graph
		)
		if stale:
			return self._correction_receipt(
				status="refused",
				action=action,
				case_id=case_id,
				event_id=event_id,
				target_stable_id=target_stable_id,
				error_code="stale_target",
				knowledge_graph=knowledge_graph,
			)
		denoiser = getattr(self._mediator, "denoiser", None)
		if denoiser is not None and hasattr(denoiser, "classify_answer_disposition"):
			disposition = denoiser.classify_answer_disposition(statement)
			if disposition in getattr(denoiser, "_NON_FACT_DISPOSITIONS", ()):
				return self._correction_receipt(
					status="refused",
					action=action,
					case_id=case_id,
					event_id=event_id,
					target_stable_id=target_stable_id,
					error_code="correction_required",
					knowledge_graph=knowledge_graph,
				)
		if not isinstance(source_context, dict) or not str(source_context.get("source_text") or ""):
			return self._correction_receipt(
				status="refused",
				action=action,
				case_id=case_id,
				event_id=event_id,
				target_stable_id=target_stable_id,
				error_code="correction_required",
				knowledge_graph=knowledge_graph,
			)
		target = str(target_stable_id or "").strip()
		entity = knowledge_graph.entity_for_stable_id(target) if target else None
		if entity is None:
			return self._correction_receipt(
				status="refused",
				action=action,
				case_id=case_id,
				event_id=event_id,
				target_stable_id=target,
				error_code="missing_target",
				knowledge_graph=knowledge_graph,
			)
		if knowledge_graph.entity_activity(entity.id) in {"superseded", "retracted", "conflict"}:
			return self._correction_receipt(
				status="refused",
				action=action,
				case_id=case_id,
				event_id=event_id,
				target_stable_id=target,
				error_code="stale_target",
				knowledge_graph=knowledge_graph,
			)
		return None

	def _correction_question(self, event_id: str, action: str) -> Dict[str, Any]:
		return {
			"type": "clarification",
			"question": "What is the corrected fact?",
			"context": {
				"fact_type": "clarification",
				"factual_action": action,
				"correction_event_id": event_id,
			},
			"candidate_source": "factual_correction",
		}

	def _affected_support_targets(self, knowledge_graph, updates: Dict[str, Any], target_stable_id: str) -> List[Dict[str, Any]]:
		previous = None
		if knowledge_graph is not None and target_stable_id and hasattr(knowledge_graph, "entity_for_stable_id"):
			previous = knowledge_graph.entity_for_stable_id(target_stable_id)
		previous_id = getattr(previous, "id", "")
		found: List[Dict[str, Any]] = []
		seen = set()
		relationships = getattr(knowledge_graph, "relationships", {}) or {}
		for relationship in relationships.values():
			attributes = getattr(relationship, "attributes", {}) or {}
			if attributes.get("activity_status") != "invalidated":
				continue
			if previous_id and str(attributes.get("invalidated_entity_id") or "") not in {"", previous_id}:
				continue
			if previous_id and previous_id not in {getattr(relationship, "source_id", ""), getattr(relationship, "target_id", "")}:
				continue
			source_id = str(getattr(relationship, "source_id", "") or "")
			target_id = str(getattr(relationship, "target_id", "") or "")
			other = target_id if source_id == previous_id else source_id
			item = {
				"relationship_id": str(getattr(relationship, "id", "") or ""),
				"target_id": other,
				"relation_type": str(getattr(relationship, "relation_type", "") or ""),
			}
			key = (item["relationship_id"], item["target_id"])
			if key in seen:
				continue
			seen.add(key)
			found.append(item)
		for node_id in updates.get("dependency_nodes_invalidated") or []:
			item = {"relationship_id": "", "target_id": str(node_id), "relation_type": "dependency"}
			key = ("", item["target_id"])
			if key in seen:
				continue
			seen.add(key)
			found.append(item)
		return found

	def _correction_receipt(
		self,
		*,
		status: str,
		action: str,
		case_id: str,
		event_id: str,
		target_stable_id: str,
		error_code: Optional[str] = None,
		error_type: Optional[str] = None,
		idempotent_replay: bool = False,
		graph_mutated: bool = False,
		updates: Optional[Dict[str, Any]] = None,
		knowledge_graph=None,
	) -> Dict[str, Any]:
		from mediator.hook_runtime import graph_revision_token

		meta = getattr(self, "_interview_meta", None) or {}
		updates = updates or {}
		graph_revision = ""
		revision_index = 0
		lineage = {
			"action": "supersede" if action == "correct" else "retract",
			"previous_stable_id": target_stable_id,
			"new_stable_id": str(updates.get("stable_id") or ""),
			"previous_envelope_retained": False,
			"replacement_envelope_retained": False,
		}
		if knowledge_graph is not None and hasattr(knowledge_graph, "factual_ledger"):
			graph_revision = graph_revision_token(knowledge_graph)
			revision_index = len(knowledge_graph.factual_ledger().get("revisions") or [])
			previous_state = knowledge_graph.assertion_state(target_stable_id) if target_stable_id else {}
			replacement_state = knowledge_graph.assertion_state(lineage["new_stable_id"]) if lineage["new_stable_id"] else {}
			lineage["previous_envelope_retained"] = isinstance(previous_state.get("envelope"), dict)
			lineage["replacement_envelope_retained"] = isinstance(replacement_state.get("envelope"), dict)
			lineage["previous_status"] = str(previous_state.get("status") or "")
			lineage["replacement_status"] = str(replacement_state.get("status") or "")
		error = None
		if error_code:
			error = {"code": error_code, "resumable": error_code != "event_conflict", "legal_sufficiency": False}
			if error_type:
				error["error_type"] = error_type
		return {
			"contract_version": self.FACTUAL_CORRECTION_CONTRACT_VERSION,
			"status": status,
			"action": action,
			"case_id": case_id,
			"event_id": event_id,
			"target_stable_id": target_stable_id,
			"replacement_stable_id": lineage["new_stable_id"],
			"idempotent_replay": bool(idempotent_replay),
			"graph_mutated": bool(graph_mutated),
			"display_only": False,
			"graph_revision": graph_revision,
			"graph_revision_index": revision_index,
			"session_revision": int(meta.get("session_revision") or 0),
			"affected_support_targets": self._affected_support_targets(knowledge_graph, updates, target_stable_id) if status == "applied" else [],
			"lineage": lineage,
			"awaiting_user": False,
			"worker_stalled": False,
			"legal_sufficiency": False,
			"error": error,
		}


	REVIEW_TRANSITION_CONTRACT_VERSION = "review-state-transition-v1"
	_REVIEW_TARGET_BUCKETS = {
		"fact": "facts",
		"answer": "answers",
		"legal_admission": "legal_admissions",
		"draft_revision": "draft_revisions",
	}

	def apply_authorized_review_transition(
		self,
		*,
		case_id: str,
		actor_principal_id: str,
		canonical_owner_principal_id: str,
		authorized: bool,
		item_type: str,
		item_id: str,
		target_kind: str,
		target_id: str,
		replacement: str,
		expected_review_revision: int,
		expected_target_revision: int,
		request_id: str,
	) -> Dict[str, Any]:
		"""Apply one accepted review proposal to a case-state target.

		Comments, tasks, and unauthorized callers never reach a successful
		write. The review revision and the target revision are both compared
		before the write. A stale caller leaves facts, answers, legal
		admissions, draft revisions, dissent, and history unchanged. Support
		bound to the previous target revision is marked invalidated and kept.
		"""
		case_file = self._review_case_file()
		state = self._review_state(case_file, case_id)
		fingerprint = self._review_fingerprint(
			item_type=item_type,
			item_id=item_id,
			target_kind=target_kind,
			target_id=target_id,
			replacement=replacement,
			expected_review_revision=expected_review_revision,
			expected_target_revision=expected_target_revision,
		)
		stored = state["operations"].get(request_id)
		if isinstance(stored, dict):
			if stored.get("fingerprint") != fingerprint:
				return self._review_receipt(state, status="refused", error_code="replay_mismatch", applied=False, request_id=request_id)
			replay = dict(stored["receipt"])
			replay["replayed"] = True
			replay["applied"] = False
			return replay
		bucket_name = self._REVIEW_TARGET_BUCKETS.get(target_kind)
		refusal = None
		if not authorized or not str(actor_principal_id or "").strip():
			refusal = "actor_not_permitted"
		elif str(actor_principal_id) == str(canonical_owner_principal_id or ""):
			refusal = "actor_is_not_canonical_owner"
		elif item_type != "review_proposal":
			refusal = "not_an_accepted_transition"
		elif bucket_name is None or not str(target_id or "").strip() or not str(replacement or "").strip():
			refusal = "review_field"
		elif not str(item_id or "").strip() or not str(request_id or "").strip():
			refusal = "review_field"
		elif type(expected_review_revision) is not int or isinstance(expected_review_revision, bool):
			refusal = "review_field"
		elif type(expected_target_revision) is not int or isinstance(expected_target_revision, bool):
			refusal = "review_field"
		elif int(expected_review_revision) != int(state["review_revision"]):
			refusal = "stale_review_revision"
		if refusal is not None:
			return self._review_receipt(state, status="refused", error_code=refusal, applied=False, request_id=request_id)
		bucket = state[bucket_name]
		current = bucket.get(target_id) if isinstance(bucket.get(target_id), dict) else None
		current_revision = int(current["revision"]) if current else 0
		if int(expected_target_revision) != current_revision:
			return self._review_receipt(state, status="refused", error_code="stale_target_revision", applied=False, request_id=request_id)
		history = list(current.get("history") or []) if current else []
		if current is not None:
			history.append({
				"revision": current_revision,
				"text": current.get("text") or "",
				"superseded_by": request_id,
				"item_id": item_id,
			})
		new_revision = current_revision + 1
		bucket[target_id] = {
			"target_kind": target_kind,
			"target_id": target_id,
			"text": replacement,
			"revision": new_revision,
			"history": history,
			"updated_by_actor_principal_id": actor_principal_id,
			"item_id": item_id,
			"item_type": "review_proposal",
		}
		invalidated = []
		for support in state["downstream_support"]:
			if not isinstance(support, dict):
				continue
			same_target = support.get("depends_on_kind") == target_kind and support.get("depends_on_id") == target_id
			if same_target and int(support.get("depends_on_revision") or 0) != new_revision and support.get("status") != "invalidated":
				support["status"] = "invalidated"
				support["stale"] = True
				support["invalidated_by"] = request_id
				support["invalidated_at_review_revision"] = int(state["review_revision"]) + 1
				invalidated.append(support.get("support_id"))
		state["review_revision"] = int(state["review_revision"]) + 1
		acceptance = {
			"request_id": request_id,
			"item_id": item_id,
			"item_type": "review_proposal",
			"target_kind": target_kind,
			"target_id": target_id,
			"target_revision": new_revision,
			"prior_target_revision": current_revision,
			"actor_principal_id": actor_principal_id,
			"review_revision": state["review_revision"],
			"invalidated_support_ids": list(invalidated),
		}
		state["acceptance_history"].append(acceptance)
		receipt = self._review_receipt(
			state,
			status="applied",
			error_code=None,
			applied=True,
			request_id=request_id,
			acceptance=acceptance,
			invalidated_support_ids=invalidated,
		)
		state["operations"][request_id] = {"fingerprint": fingerprint, "receipt": dict(receipt)}
		case_file["review_case_state"] = state
		return receipt

	def register_review_downstream_support(
		self,
		*,
		case_id: str,
		support_id: str,
		depends_on_kind: str,
		depends_on_id: str,
		depends_on_revision: int,
		request_id: str,
	) -> Dict[str, Any]:
		"""Bind support to one current target revision without changing that target."""
		case_file = self._review_case_file()
		state = self._review_state(case_file, case_id)
		fingerprint = self._review_fingerprint(
			item_type="downstream_support",
			item_id=support_id,
			target_kind=depends_on_kind,
			target_id=depends_on_id,
			replacement=str(depends_on_revision),
			expected_review_revision=int(state["review_revision"]),
			expected_target_revision=depends_on_revision if type(depends_on_revision) is int else -1,
		)
		stored = state["operations"].get(request_id)
		if isinstance(stored, dict):
			if stored.get("fingerprint") != fingerprint:
				return self._review_receipt(state, status="refused", error_code="replay_mismatch", applied=False, request_id=request_id)
			replay = dict(stored["receipt"])
			replay["replayed"] = True
			replay["applied"] = False
			return replay
		bucket_name = self._REVIEW_TARGET_BUCKETS.get(depends_on_kind)
		current = None
		if bucket_name is not None:
			candidate = state[bucket_name].get(depends_on_id)
			current = candidate if isinstance(candidate, dict) else None
		if (
			bucket_name is None
			or not str(support_id or "").strip()
			or not str(request_id or "").strip()
			or type(depends_on_revision) is not int
			or isinstance(depends_on_revision, bool)
			or current is None
			or int(current.get("revision") or 0) != int(depends_on_revision)
		):
			code = "support_target_missing" if current is None else "stale_target_revision"
			if bucket_name is None or not str(support_id or "").strip() or type(depends_on_revision) is not int or isinstance(depends_on_revision, bool):
				code = "review_field"
			return self._review_receipt(state, status="refused", error_code=code, applied=False, request_id=request_id)
		before = json.dumps(state["facts"], sort_keys=True, default=str)
		row = {
			"support_id": support_id,
			"depends_on_kind": depends_on_kind,
			"depends_on_id": depends_on_id,
			"depends_on_revision": int(depends_on_revision),
			"status": "current",
			"stale": False,
			"invalidated_by": None,
		}
		state["downstream_support"].append(row)
		if json.dumps(state["facts"], sort_keys=True, default=str) != before:
			raise RuntimeError("support registration mutated facts")
		receipt = self._review_receipt(state, status="bound", error_code=None, applied=False, request_id=request_id, support=row)
		state["operations"][request_id] = {"fingerprint": fingerprint, "receipt": dict(receipt)}
		case_file["review_case_state"] = state
		return receipt

	def _review_case_file(self) -> Dict[str, Any]:
		return self._refresh_case_file()

	def _review_state(self, case_file: Dict[str, Any], case_id: str) -> Dict[str, Any]:
		state = case_file.get("review_case_state")
		if not isinstance(state, dict) or state.get("case_id") not in {None, "", case_id}:
			state = {
				"contract_version": self.REVIEW_TRANSITION_CONTRACT_VERSION,
				"case_id": case_id,
				"review_revision": 0,
				"facts": {},
				"answers": {},
				"legal_admissions": {},
				"draft_revisions": {},
				"downstream_support": [],
				"acceptance_history": [],
				"operations": {},
			}
		for name in ("facts", "answers", "legal_admissions", "draft_revisions", "operations"):
			if not isinstance(state.get(name), dict):
				state[name] = {}
		for name in ("downstream_support", "acceptance_history"):
			if not isinstance(state.get(name), list):
				state[name] = []
		if type(state.get("review_revision")) is not int:
			state["review_revision"] = 0
		state["case_id"] = case_id
		return state

	def _review_fingerprint(self, **parts: Any) -> str:
		payload = json.dumps(parts, sort_keys=True, default=str)
		return hashlib.sha256(payload.encode("utf-8")).hexdigest()

	def _review_receipt(self, state: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
		return {
			"task_id": "CIMP-GUI-47",
			"contract_version": self.REVIEW_TRANSITION_CONTRACT_VERSION,
			"status": kwargs["status"],
			"applied": bool(kwargs["applied"]),
			"replayed": False,
			"request_id": kwargs.get("request_id") or "",
			"review_revision": int(state.get("review_revision") or 0),
			"facts": json.loads(json.dumps(state.get("facts") or {})),
			"answers": json.loads(json.dumps(state.get("answers") or {})),
			"legal_admissions": json.loads(json.dumps(state.get("legal_admissions") or {})),
			"draft_revisions": json.loads(json.dumps(state.get("draft_revisions") or {})),
			"downstream_support": json.loads(json.dumps(state.get("downstream_support") or [])),
			"acceptance_history": json.loads(json.dumps(state.get("acceptance_history") or [])),
			"acceptance": json.loads(json.dumps(kwargs.get("acceptance"))) if kwargs.get("acceptance") else None,
			"support": json.loads(json.dumps(kwargs.get("support"))) if kwargs.get("support") else None,
			"invalidated_support_ids": list(kwargs.get("invalidated_support_ids") or []),
			"governing_legal_authority": False,
			"legal_sufficiency": False,
			"error": None if not kwargs.get("error_code") else {"code": kwargs["error_code"], "resumable": kwargs["error_code"] != "replay_mismatch"},
			"limitations": [
				"Only an authorized accepted review_proposal updates facts, answers, legal admissions, or draft revisions.",
				"Review tasks and comments are not case-state transitions.",
				"Concurrent acceptance must present the current review revision and target revision.",
				"Dissent and prior target text stay in history.",
				"Downstream support bound to a replaced revision is invalidated and kept.",
				"This receipt is not governing law or legal sufficiency.",
			],
		}


def _json_ready(value: Any) -> Any:
	"""Drop values that cannot be stored in the versioned session projection."""
	try:
		return json.loads(json.dumps(value, default=_json_default))
	except (TypeError, ValueError):
		return None


def _json_default(value: Any) -> Any:
	if isinstance(value, set):
		return sorted(value)
	name = getattr(value, "value", None)
	if isinstance(name, str):
		return name
	raise TypeError(type(value).__name__)


# A concise name for new integrations.  Keep WorkflowActionService as the
# defining class so its identity and name remain stable for existing callers.
WorkflowService = WorkflowActionService
