from time import time
from .strings import user_prompts
from .state import State
from .inquiries import Inquiries
from .complaint import Complaint
from .exceptions import UserPresentableException


class Mediator:
	def __init__(self, backends):
		self.backends = backends
		self.inquiries = Inquiries(self)
		self.complaint = Complaint(self)
		self.reset()


	def reset(self):
		self.state = State()
		self.inquiries.register(user_prompts['genesis_question'])


	def resume(self, state):
		self.state = state


	def get_state(self):
		return self.state.serialize()


	def set_state(self, serialized):
		self.state = State.from_serialized(serialized)


	def io(self, text):
		self.log('user_input', text=text)

		try:
			output = self.process(text)
			self.log('user_output', text=output)
		except Exception as exception:
			self.log('io_error', error=str(exception))
			raise exception

		return output


	def process(self, text):
		if not self.state:
			raise UserPresentableException(
				'no-context',
				'No internal state given. Either create new, or resume.'
			)

		if text:
			self.inquiries.answer(text)

		if not self.inquiries.get_next():
			self.complaint.generate()
			self.inquiries.generate()

		return self.inquiries.get_next()['question']



	def query_backend(self, prompt):
		backend = self.backends[0]

		try:
			response = backend(prompt)
		except Exception as exception:
			self.log('backend_error', backend=backend.id, prompt=prompt, error=str(exception))
			raise exception

		self.log('backend_query', backend=backend.id, prompt=prompt, response=response)

		return response
		


	def log(self, type, **data):
		self.state.log.append({
			'time': int(time()),
			'type': type,
			**data
		})