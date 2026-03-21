import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from . import strings


_QUESTION_RE = re.compile(r"[^?\n]+?\?")
_WS_RE = re.compile(r"\s+")
_NORMALIZE_RE = re.compile(r"[^a-z0-9 ]+")
_LIST_PREFIX_RE = re.compile(r"^\s*(?:\d+\s*[.)]|[-*•])\s+")


@lru_cache(maxsize=2048)
def _normalize_question_cached(text: str) -> str:
	normalized = text.strip().rstrip("?").lower()
	normalized = _LIST_PREFIX_RE.sub("", normalized, count=1)
	normalized = _WS_RE.sub(" ", normalized)
	normalized = _NORMALIZE_RE.sub("", normalized)
	return normalized.strip()


class Inquiries:
	_PRIORITY_RANK = {
		"critical": 0,
		"high": 1,
		"medium": 2,
		"low": 3,
	}
	_OBJECTIVE_KEYWORDS = {
		"timeline": ("when", "date", "time", "timeline", "first incident", "date range"),
		"exact_dates": ("exact date", "exact dates", "specific date", "what date", "calendar date"),
		"actors": ("who", "decision", "decision-maker", "supervisor", "manager", "hr", "told you"),
		"documents": ("document", "documents", "email", "emails", "notice", "records", "message", "written"),
		"witnesses": ("witness", "witnesses", "saw", "heard", "present"),
		"harm_remedy": ("harm", "damages", "impact", "injury", "remedy", "relief", "requesting"),
		"anchor_adverse_action": ("adverse action", "terminate", "termination", "fired", "suspend", "demot", "discipline", "denied"),
		"anchor_grievance_hearing": ("grievance", "hearing", "internal complaint", "complaint process"),
		"anchor_appeal_rights": ("appeal", "review", "deadline", "rights to appeal"),
		"anchor_reasonable_accommodation": ("accommodation", "disability", "medical restriction", "interactive process"),
		"anchor_selection_criteria": ("selection criteria", "criteria", "qualifications", "not selected", "selection process"),
		"causation_sequence": ("sequence", "chronology", "order of events", "protected activity", "retaliation timeline"),
		"hearing_request_timing": ("hearing request", "review request", "requested a hearing", "asked for review"),
		"response_dates": ("response date", "decision date", "notice date", "when did they respond", "when were you notified"),
	}

	def __init__(self, mediator):
		self.m = mediator
		self._index: Optional[Dict[str, Dict[str, Any]]] = None
		self._index_signature: Tuple[int, int] = (0, 0)

	@staticmethod
	def _find_unanswered(inquiries):
		for inquiry in inquiries:
			if not inquiry.get("answer"):
				return inquiry
		return None

	def _state_inquiries(self):
		return getattr(self.m.state, "inquiries", None)

	def _index_key(self, inquiries) -> Tuple[int, int]:
		return (id(inquiries), len(inquiries))

	def _index_for(self, inquiries) -> Dict[str, Dict[str, Any]]:
		signature = self._index_key(inquiries)
		if self._index is None or self._index_signature != signature:
			self._index = self._build_index(inquiries)
			self._index_signature = signature
		return self._index

	def get_next(self):
		inquiries = self._state_inquiries()
		if not inquiries:
			return None
		gap_context = self._build_gap_context()
		unanswered = [
			(item, index)
			for index, item in enumerate(inquiries)
			if not item.get("answer")
		]
		if not unanswered:
			return None
		unanswered.sort(
			key=lambda pair: (
				0 if pair[0].get("support_gap_targeted") else 1,
				0 if pair[0].get("dependency_gap_targeted") else 1,
				self._intake_priority_sort_key(pair[0], gap_context),
				self._priority_rank(pair[0].get("priority")),
				pair[1],
			)
		)
		return unanswered[0][0]

	def answer(self, text):
		current = self.get_next()
		if current is None:
			return
		current["answer"] = text

	def generate(self):
		template = strings.model_prompts.get("generate_questions")
		if not template:
			return

		inquiries = self._state_inquiries()
		if inquiries is None:
			return

		block = self.m.query_backend(template.format(complaint=self.m.state.complaint))
		if not block:
			return

		index = self._index_for(inquiries)
		for question in self._extract_questions(block):
			self._register(question, inquiries, index)

	def register(self, question):
		if not question:
			return

		inquiries = self._state_inquiries()
		if inquiries is None:
			return

		index = self._index_for(inquiries)
		self._register(question, inquiries, index)

	def merge_legal_questions(self, questions: List[Dict[str, Any]]) -> int:
		inquiries = self._state_inquiries()
		if inquiries is None:
			return 0

		index = self._index_for(inquiries)
		gap_context = self._build_gap_context()
		priority_terms = [
			str(term).strip().lower()
			for term in (gap_context.get("priority_terms") or [])
			if str(term).strip()
		]

		merged = 0
		for item in questions or []:
			if not isinstance(item, dict):
				continue
			question_text = str(item.get("question") or "").strip()
			if not question_text:
				continue

			normalized = self._normalize_question(question_text)
			dependency_gap_targeted = any(term in question_text.lower() for term in priority_terms)
			intake_objectives, intake_rank = self._match_intake_objectives(item, gap_context)
			existing = index.get(normalized)
			if existing is not None:
				existing_priority = self._priority_rank(existing.get("priority"))
				incoming_priority = self._priority_rank(item.get("priority"))
				if incoming_priority < existing_priority:
					existing["priority"] = item.get("priority")
				existing["support_gap_targeted"] = bool(
					existing.get("support_gap_targeted") or item.get("support_gap_targeted")
				)
				existing["dependency_gap_targeted"] = bool(
					existing.get("dependency_gap_targeted") or dependency_gap_targeted
				)
				self._merge_intake_priority(existing, intake_objectives, intake_rank)
				if not existing.get("source") or str(existing.get("source")).strip().lower() == "legal_question":
					existing["source"] = "legal_question"
				if item.get("claim_type"):
					existing["claim_type"] = item.get("claim_type")
				if item.get("element"):
					existing["element"] = item.get("element")
				if item.get("provenance"):
					existing["provenance"] = dict(item.get("provenance") or {})
				if question_text != existing.get("question"):
					alternatives = existing.setdefault("alternative_questions", [])
					if all(self._normalize_question(candidate) != normalized for candidate in alternatives):
						alternatives.append(question_text)
				merged += 1
				continue

			inquiry = {
				"question": question_text,
				"alternative_questions": list(item.get("alternative_questions") or []),
				"answer": item.get("answer"),
				"priority": item.get("priority", "Medium"),
				"support_gap_targeted": bool(item.get("support_gap_targeted", False)),
				"dependency_gap_targeted": dependency_gap_targeted,
				"intake_priority_targeted": bool(intake_objectives),
				"intake_priority_objectives": intake_objectives,
				"intake_priority_rank": intake_rank,
				"source": "legal_question",
				"claim_type": item.get("claim_type"),
				"element": item.get("element"),
				"provenance": dict(item.get("provenance") or {}),
			}
			inquiries.append(inquiry)
			index[normalized] = inquiry
			merged += 1

		self._index_signature = (id(inquiries), len(inquiries))
		return merged

	def explain_inquiry(self, inquiry: Dict[str, Any]) -> Dict[str, Any]:
		inquiry = dict(inquiry or {})
		priority = str(inquiry.get("priority") or "Medium")
		reasons: List[str] = []
		gap_context = self._build_gap_context()
		matched_objectives, _ = self._match_intake_objectives(inquiry, gap_context)
		chronology_objectives = {"timeline", "exact_dates", "causation_sequence", "hearing_request_timing", "response_dates"}
		if bool(gap_context.get("needs_chronology_closure")) and any(
			objective in chronology_objectives for objective in matched_objectives
		):
			unresolved_temporal_issue_count = int(gap_context.get("unresolved_temporal_issue_count") or 0)
			chronology_task_count = int(gap_context.get("chronology_task_count") or 0)
			if unresolved_temporal_issue_count or chronology_task_count:
				reasons.append(
					f"helps close chronology gaps flagged by review ({unresolved_temporal_issue_count} unresolved issues, {chronology_task_count} chronology tasks)"
				)
			else:
				reasons.append("helps close chronology gaps flagged by review")
		if bool(gap_context.get("needs_decision_document_precision")) and "documents" in matched_objectives:
			missing_proof_artifact_count = int(gap_context.get("missing_proof_artifact_count") or 0)
			if missing_proof_artifact_count:
				reasons.append(
					f"helps recover missing decision or notice documents flagged by proof review ({missing_proof_artifact_count} missing artifacts)"
				)
			else:
				reasons.append("helps recover missing decision or notice documents flagged by proof review")
		if inquiry.get("support_gap_targeted"):
			reasons.append("targets a missing claim element or support gap")
		if inquiry.get("dependency_gap_targeted"):
			reasons.append("targets a missing claim element or dependency gap")
		if inquiry.get("intake_priority_targeted"):
			objectives = ", ".join(inquiry.get("intake_priority_objectives") or [])
			if objectives:
				reasons.append(f"targets prioritized intake objectives: {objectives}")
		if str(inquiry.get("source") or "").strip().lower() == "legal_question":
			reasons.append("generated from legal claim requirements")
		claim_type = str(inquiry.get("claim_type") or "").strip()
		element = str(inquiry.get("element") or "").strip()
		if claim_type and element:
			reasons.append(f"addresses {claim_type} element: {element}")
		if not reasons:
			reasons.append("selected as the next unanswered question")
		return {
			"summary": f"Selected because it is a {priority} priority question and {'; '.join(reasons)}",
			"priority": priority,
			"support_gap_targeted": bool(inquiry.get("support_gap_targeted")),
			"dependency_gap_targeted": bool(inquiry.get("dependency_gap_targeted")),
			"reasons": reasons,
		}

	def _register(self, question, inquiries, index):
		normalized = self._normalize_question(question)
		existing = index.get(normalized)
		if existing is not None:
			existing.setdefault("alternative_questions", []).append(question)
			return

		inquiry = {
			"question": question,
			"alternative_questions": [],
			"answer": None,
		}
		inquiries.append(inquiry)
		index[normalized] = inquiry
		self._index_signature = (id(inquiries), len(inquiries))

	def _build_index(self, inquiries):
		index: Dict[str, Dict[str, Any]] = {}
		for inquiry in inquiries:
			question = inquiry.get("question")
			if not question:
				continue

			normalized = self._normalize_question(question)
			if normalized not in index:
				index[normalized] = inquiry
		return index

	@staticmethod
	def _trim_question_prefix(text: str) -> str:
		return _LIST_PREFIX_RE.sub("", text, count=1).strip()

	@classmethod
	def _clean_question(cls, raw_question: str) -> str:
		question = cls._trim_question_prefix(raw_question)
		question = _WS_RE.sub(" ", question).strip()
		if not question:
			return ""
		return question

	def _extract_questions(self, block):
		text = str(block)
		questions: List[str] = []

		for match in _QUESTION_RE.finditer(text):
			question = self._clean_question(match.group(0))
			if question:
				questions.append(question)

		if questions:
			return questions

		for line in text.splitlines():
			line = line.strip()
			if not line or "?" not in line:
				continue

			for match in _QUESTION_RE.finditer(line):
				question = self._clean_question(match.group(0))
				if question:
					questions.append(question)

		return questions

	def is_complete(self):
		inquiries = self._state_inquiries()
		if not inquiries:
			return True
		return self._find_unanswered(inquiries) is None

	def same_question(self, a, b):
		if not a or not b:
			return False
		return self._normalize_question(a) == self._normalize_question(b)

	def _normalize_question(self, text):
		return _normalize_question_cached(text)

	def _priority_rank(self, value: Any) -> int:
		return self._PRIORITY_RANK.get(str(value or "medium").strip().lower(), 2)

	def _intake_priority_sort_key(self, inquiry: Dict[str, Any], gap_context: Dict[str, Any]) -> tuple[int, int]:
		matched_objectives, matched_rank = self._match_intake_objectives(inquiry, gap_context)
		if not matched_objectives:
			return (2, 999)
		uncovered = {
			str(value).strip().lower()
			for value in (gap_context.get("intake_uncovered_objectives") or [])
			if str(value).strip()
		}
		if any(objective.lower() in uncovered for objective in matched_objectives):
			return (0, matched_rank)
		return (1, matched_rank)

	def _merge_intake_priority(self, inquiry: Dict[str, Any], intake_objectives: List[str], intake_rank: int | None) -> None:
		existing_objectives = [
			str(value).strip()
			for value in (inquiry.get("intake_priority_objectives") or [])
			if str(value).strip()
		]
		for objective in intake_objectives:
			if objective not in existing_objectives:
				existing_objectives.append(objective)
		inquiry["intake_priority_targeted"] = bool(existing_objectives)
		inquiry["intake_priority_objectives"] = existing_objectives
		current_rank = inquiry.get("intake_priority_rank")
		if intake_rank is None:
			return
		if current_rank is None or int(intake_rank) < int(current_rank):
			inquiry["intake_priority_rank"] = intake_rank

	def _match_intake_objectives(self, inquiry: Any, gap_context: Dict[str, Any]) -> tuple[List[str], int | None]:
		ordered_objectives = self._ordered_intake_objectives(gap_context)
		if not ordered_objectives:
			return ([], None)
		candidate_objectives = self._objectives_for_inquiry(inquiry)
		if not candidate_objectives:
			return ([], None)
		matched = [objective for objective in ordered_objectives if objective in candidate_objectives]
		if not matched:
			return ([], None)
		return (matched, ordered_objectives.index(matched[0]))

	def _ordered_intake_objectives(self, gap_context: Dict[str, Any]) -> List[str]:
		ordered: List[str] = []
		for field in ("intake_uncovered_objectives", "intake_expected_objectives", "intake_covered_objectives"):
			for value in (gap_context.get(field) or []):
				objective = str(value).strip()
				if objective and objective not in ordered:
					ordered.append(objective)
		priority_prefix: List[str] = []
		if bool(gap_context.get("needs_chronology_closure")):
			for objective in ("timeline", "exact_dates", "causation_sequence", "response_dates", "hearing_request_timing"):
				if objective in ordered and objective not in priority_prefix:
					priority_prefix.append(objective)
		if bool(gap_context.get("needs_decision_document_precision")) and "documents" in ordered:
			priority_prefix.append("documents")
		if not priority_prefix:
			return ordered
		return priority_prefix + [objective for objective in ordered if objective not in priority_prefix]

	def _objectives_for_inquiry(self, inquiry: Any) -> List[str]:
		if not isinstance(inquiry, dict):
			return self._infer_objectives_from_text(str(inquiry or ""))
		objectives: List[str] = []
		for key in ("question_objective", "type"):
			value = str(inquiry.get(key) or "").strip()
			if value and value not in objectives and value in self._OBJECTIVE_KEYWORDS:
				objectives.append(value)
		for value in list(inquiry.get("intake_priority_objectives") or []):
			objective = str(value).strip()
			if objective and objective not in objectives:
				objectives.append(objective)
		selector_signals = inquiry.get("selector_signals")
		if isinstance(selector_signals, dict):
			for value in list(selector_signals.get("intake_priority_match") or []):
				objective = str(value).strip()
				if objective and objective not in objectives:
					objectives.append(objective)
		for objective in self._infer_objectives_from_text(str(inquiry.get("question") or "")):
			if objective not in objectives:
				objectives.append(objective)
		return objectives

	def _infer_objectives_from_text(self, text: str) -> List[str]:
		lowered = str(text or "").strip().lower()
		if not lowered:
			return []
		matched: List[str] = []
		for objective, keywords in self._OBJECTIVE_KEYWORDS.items():
			if any(keyword in lowered for keyword in keywords):
				matched.append(objective)
		return matched

	def _build_gap_context(self) -> Dict[str, Any]:
		builder = getattr(self.m, "build_inquiry_gap_context", None)
		context: Dict[str, Any] = {}
		if callable(builder):
			try:
				context = builder()
			except Exception:
				context = {}
			context = context if isinstance(context, dict) else {}
		try:
			phase_manager = getattr(self.m, "phase_manager", None)
			if phase_manager is not None:
				from complaint_phases import ComplaintPhase
				summary = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "adversarial_intake_priority_summary") or {}
				if isinstance(summary, dict):
					context = dict(context)
					context.setdefault("intake_expected_objectives", list(summary.get("expected_objectives") or []))
					context.setdefault("intake_covered_objectives", list(summary.get("covered_objectives") or []))
					context.setdefault("intake_uncovered_objectives", list(summary.get("uncovered_objectives") or []))
		except Exception:
			pass
		return context
