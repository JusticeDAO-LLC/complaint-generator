import spacy
from .strings import model_prompts


class Inquiries:
	def __init__(self, mediator):
		self.nlp = spacy.load('en_core_web_sm')
		self.m = mediator

	def get_next(self):
		return next((i for i in self.m.state.inquiries if not i['answer']), None)

	def answer(self, text):
		self.get_next()['answer'] = text


	def generate(self):
		block = self.m.query_backend(
			model_prompts['generate_questions']
				.format(complaint=self.m.state.complaint)
		)

		doc = self.nlp(block)

		for sent in doc.sents:
			sent = [word for word in sent if not word.is_space]

			if sent[-1].text != '?':
				continue

			self.register(' '.join([word.text for word in sent]))


	def register(self, question):
		is_unique = True

		for other in self.m.state.inquiries:
			if self.same_question(question, other['question']):
				other['alternative_questions'].append(question)
				is_unique = False

		if is_unique:
			self.m.state.inquiries.append({
				'question': question,
				'alternative_questions': [],
				'answer': None
			})


	def same_question(self, a, b):
		return False