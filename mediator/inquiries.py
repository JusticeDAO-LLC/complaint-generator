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
				existing["source"] = "legal_question"
				if item.get("claim_type"):
					existing["claim_type"] = item.get("claim_type")
				if item.get("element"):
					existing["element"] = item.get("element")
				if item.get("provenance"):
					existing["provenance"] = dict(item.get("provenance") or {})
				if question_text != existing.get("question"):
					existing.setdefault("alternative_questions", []).append(question_text)
				merged += 1
				continue

			inquiry = {
				"question": question_text,
				"alternative_questions": list(item.get("alternative_questions") or []),
				"answer": item.get("answer"),
				"priority": item.get("priority", "Medium"),
				"support_gap_targeted": bool(item.get("support_gap_targeted", False)),
				"dependency_gap_targeted": dependency_gap_targeted,
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
		if inquiry.get("support_gap_targeted"):
			reasons.append("targets a missing claim element or support gap")
		if inquiry.get("dependency_gap_targeted"):
			reasons.append("targets a missing claim element or dependency gap")
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

	def _build_gap_context(self) -> Dict[str, Any]:
		builder = getattr(self.m, "build_inquiry_gap_context", None)
		if callable(builder):
			try:
				context = builder()
			except Exception:
				context = {}
			return context if isinstance(context, dict) else {}
		return {}
