from .strings import model_prompts


class Complaint:
	def __init__(self, mediator):
		self.m = mediator

	
	def generate(self):
		inquiries = []

		for inquiry in self.m.state.inquiries:
			if not inquiry['answer']:
				continue

			inquiries.append(model_prompts['inquiry_block'].format(
				lawyer=inquiry['question'],
				plaintiff=inquiry['answer']
			))


		self.m.state.complaint = self.m.query_backend(
			model_prompts['summarize_complaint'].format(inquiries='\n'.join(inquiries))
		)

