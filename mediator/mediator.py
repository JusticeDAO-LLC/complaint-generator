from .strings import user_promps, model_prompts
from .state import State
from .exceptions import UserPresentableException


class Mediator:
	def __init__(self, backends):
		self.backends = backends
		self.reset()

	def reset(self):
		self.state = State()

	def resume(self, state):
		self.state = state

	def get_state(self):
		return self.state.serialize()

	def set_state(self, serialized):
		self.state = State.from_serialized(serialized)

	def io(self, text):
		if not self.state:
			raise UserPresentableException(
				'no-context', 
				'No internal state given. Either create new, or resume.'
			)
			
		if not self.state.genesis_statement:
			if not text:
				return user_promps['genesis']
			else:
				self.state.genesis_statement = text

		

		

	def query_backend(self, template, args):
		return self.backends[0].prompt(model_prompts[template].format(**args))

	