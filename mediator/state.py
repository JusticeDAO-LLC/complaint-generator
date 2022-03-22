class State:
	@classmethod
	def from_serialized(cls, serialized):
		state = cls()
		state.genesis_statement = serialized['genesis_statement']
		state.answers = serialized['answers']

		return state
		

	def __init__(self):
		self.genesis_statement = None
		self.answers = []

	def serialize(self):
		return {
			'genesis_statement': self.genesis_statement,
			'answers': self.answers
		}