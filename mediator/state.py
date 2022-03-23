class State:
	@classmethod
	def from_serialized(cls, serialized):
		state = cls()
		state.inquiries = serialized['inquiries']
		state.complaint = serialized['complaint']
		state.log = serialized['log']

		return state
		

	def __init__(self):
		self.inquiries = []
		self.complaint = None
		self.log = []

	def serialize(self):
		return {
			'inquiries': self.inquiries,
			'complaint': self.complaint,
			'log': self.log
		}