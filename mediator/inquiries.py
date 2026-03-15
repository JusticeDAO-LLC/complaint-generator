import re

from . import strings


_QUESTION_RE = re.compile(r"[^?\n]+?\?")
_WS_RE = re.compile(r"\s+")


class Inquiries:
	def __init__(self, mediator):
		self.m = mediator

	def get_next(self):
		inquiries = getattr(self.m.state, "inquiries", None)
		if not inquiries:
			return None
		for inquiry in inquiries:
			if not inquiry.get("answer"):
				return inquiry
		return None

	def answer(self, text):
		current = self.get_next()
		if current is None:
			return
		current["answer"] = text

	def generate(self):
		template = strings.model_prompts.get("generate_questions")
		if not template:
			return

		block = self.m.query_backend(
			template.format(complaint=self.m.state.complaint)
		)
		if not block:
			return

		for question in self._extract_questions(block):
			self.register(question)

	def register(self, question):
		if not question:
			return
		inquiries = self.m.state.inquiries
		for other in inquiries:
			if self.same_question(question, other.get("question", "")):
				other.setdefault("alternative_questions", []).append(question)
				return
		inquiries.append({
			"question": question,
			"alternative_questions": [],
			"answer": None,
		})

	def _extract_questions(self, block):
		questions = []
		for match in _QUESTION_RE.findall(block):
			question = _WS_RE.sub(" ", match).strip()
			if question:
				questions.append(question)
		return questions

	def is_complete(self):
		inquiries = getattr(self.m.state, "inquiries", None)
		if not inquiries:
			return True
		for inquiry in inquiries:
			if not inquiry.get("answer"):
				return False
		return True

	def same_question(self, a, b):
		if not a or not b:
			return False
		return self._normalize_question(a) == self._normalize_question(b)

	def _normalize_question(self, text):
		normalized = text.strip().rstrip("?").lower()
		normalized = _WS_RE.sub(" ", normalized)
		normalized = re.sub(r"[^a-z0-9 ]+", "", normalized)
		return normalized.strip()
