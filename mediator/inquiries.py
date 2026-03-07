from . import strings


class Inquiries:
	_PRIORITY_SCORES = {
		'critical': 300,
		'high': 200,
		'medium': 100,
		'low': 0,
	}

	def __init__(self, mediator):
		# self.nlp = spacy.load('en_core_web_sm')
		self.m = mediator

	def get_next(self):
		self.prioritize()
		return next((i for i in self.m.state.inquiries if not i['answer']), None)

	def explain_inquiry(self, inquiry):
		if not isinstance(inquiry, dict):
			return {
				'summary': 'No inquiry is currently available.',
				'reasons': [],
				'priority': 'Low',
			}

		reasons = []
		priority = str(inquiry.get('priority', 'Low') or 'Low')
		if bool(inquiry.get('dependency_gap_targeted')):
			reasons.append('targets a missing claim element or dependency gap')
		if bool(inquiry.get('support_gap_targeted')):
			reasons.append('targets weakly supported facts or evidence gaps')
		if str(inquiry.get('source', '') or '').strip().lower() == 'legal_question':
			claim_type = str(inquiry.get('claim_type') or '').strip()
			element = str(inquiry.get('element') or '').strip()
			if claim_type and element:
				reasons.append(f'relates to {claim_type}: {element}')
			elif claim_type:
				reasons.append(f'relates to {claim_type}')
		if not reasons:
			reasons.append('next unanswered question in the queue')

		return {
			'summary': f"Selected because it is a {priority.lower()}-priority question and " + reasons[0],
			'reasons': reasons,
			'priority': priority,
			'support_gap_targeted': bool(inquiry.get('support_gap_targeted')),
			'dependency_gap_targeted': bool(inquiry.get('dependency_gap_targeted')),
			'source': inquiry.get('source'),
			'claim_type': inquiry.get('claim_type'),
			'element': inquiry.get('element'),
		}

	def get_next_details(self):
		inquiry = self.get_next()
		return {
			'inquiry': inquiry,
			'explanation': self.explain_inquiry(inquiry),
		}

	def answer(self, text):
		self.get_next()['answer'] = text

	def _normalize_question(self, question):
		return ' '.join(str(question or '').strip().lower().split())

	def _question_priority_score(self, inquiry):
		priority = str((inquiry or {}).get('priority', 'low') or 'low').strip().lower()
		score = self._PRIORITY_SCORES.get(priority, 0)
		if bool((inquiry or {}).get('support_gap_targeted')):
			score += 25
		if bool((inquiry or {}).get('dependency_gap_targeted')):
			score += 40
		if str((inquiry or {}).get('source', '') or '').strip().lower() == 'legal_question':
			score += 10
		return score

	def _tokenize(self, text):
		return {token for token in str(text or '').lower().replace('_', ' ').split() if token}

	def _matches_gap_terms(self, question, metadata=None):
		metadata = dict(metadata or {})
		context_builder = getattr(self.m, 'build_inquiry_gap_context', None)
		if not callable(context_builder):
			return False
		try:
			context = context_builder()
		except Exception:
			return False
		priority_terms = list((context or {}).get('priority_terms', []) or [])
		if not priority_terms:
			return False

		candidate_text = ' '.join([
			str(question or ''),
			str(metadata.get('claim_type') or ''),
			str(metadata.get('element') or ''),
		])
		candidate_tokens = self._tokenize(candidate_text)
		for term in priority_terms:
			term_tokens = self._tokenize(term)
			if term_tokens and term_tokens <= candidate_tokens:
				return True
			term_text = str(term or '').strip().lower()
			if term_text and term_text in candidate_text.lower():
				return True
		return False

	def prioritize(self):
		inquiries = list(getattr(self.m.state, 'inquiries', []) or [])
		answered = [item for item in inquiries if item.get('answer')]
		unanswered = [item for item in inquiries if not item.get('answer')]
		unanswered = sorted(
			unanswered,
			key=lambda item: (
				self._question_priority_score(item),
				str(item.get('question', '') or '').lower(),
			),
			reverse=True,
		)
		self.m.state.inquiries = [*answered, *unanswered]

	def register(self, question, metadata=None):
		metadata = dict(metadata or {})
		normalized = self._normalize_question(question)
		if not normalized:
			return None

		for other in self.m.state.inquiries:
			if self.same_question(normalized, other.get('question')):
				alternatives = other.setdefault('alternative_questions', [])
				if question not in alternatives and question != other.get('question'):
					alternatives.append(question)
				for key, value in metadata.items():
					if key == 'alternative_questions':
						continue
					if key == 'priority':
						existing = self._question_priority_score(other)
						candidate = self._PRIORITY_SCORES.get(str(value or '').lower(), 0)
						if candidate > existing:
							other[key] = value
						continue
					if key == 'support_gap_targeted':
						other[key] = bool(other.get(key)) or bool(value)
						continue
					if key == 'provenance' and isinstance(value, dict):
						existing_prov = dict(other.get('provenance', {}) or {})
						existing_prov.update(value)
						other['provenance'] = existing_prov
						continue
					if key not in other or other.get(key) in (None, '', [], {}):
						other[key] = value
				self.prioritize()
				return other

		entry = {
			'question': question,
			'alternative_questions': list(metadata.pop('alternative_questions', []) or []),
			'answer': metadata.pop('answer', None),
		}
		metadata['dependency_gap_targeted'] = bool(metadata.get('dependency_gap_targeted')) or self._matches_gap_terms(question, metadata)
		entry.update(metadata)
		self.m.state.inquiries.append(entry)
		self.prioritize()
		return entry

	def merge_legal_questions(self, questions):
		merged = 0
		for item in questions or []:
			if not isinstance(item, dict):
				continue
			entry = self.register(
				item.get('question'),
				metadata={
					'source': 'legal_question',
					'priority': item.get('priority', 'High'),
					'claim_type': item.get('claim_type'),
					'element': item.get('element'),
					'support_gap_targeted': item.get('support_gap_targeted', False),
					'provenance': item.get('provenance', {}),
				},
			)
			if entry is not None:
				merged += 1
		return merged


	def generate(self):
		block = self.m.query_backend(
			strings.model_prompts['generate_questions']
				.format(complaint=self.m.state.complaint)
		)

		# doc = self.nlp(block)

		# for sent in doc.sents:
		# 	sent = [word for word in sent if not word.is_space]

		# 	if sent[-1].text != '?':
		# 		continue

		# 	self.register(' '.join([word.text for word in sent]))

   
	# def register(self, question):
	# 	is_unique = True

	# 	for other in self.m.state.inquiries:
	# 		if self.same_question(question, other['question']):
	# 			other['alternative_questions'].append(question)
	# 			is_unique = False

	# 	if is_unique:
	# 		self.m.state.inquiries.append({
	# 			'question': question,
	# 			'alternative_questions': [],
	# 			'answer': None
	# 		})


	def is_complete(self):
		return False

	def same_question(self, a, b):
		return self._normalize_question(a) == self._normalize_question(b)