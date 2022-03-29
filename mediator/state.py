from cgitb import text
from urllib import response


class State:
	@classmethod
	def from_serialized(cls, serialized):
		state = cls()
		state.questions = serialized['questions']
		state.answered_questions = serialized['answered_questions']
		state.last_questions = serialized['last_question']
		state.log = serialized['log']
		return state
		

	def __init__(self):
		self.inquiries = []
		self.complaint = None
		self.log = []
		self.username = None
		self.password = None
		self.hashed_password = None
		self.hashed_username = None
		self.data = dict()

	def serialize(self):
		return {
			'inquiries': self.questions,
			'complaint': self.answered_questions,
			'log': self.log
		}

	def load_profile(self, request):
		r = requests.post(
			'https://10.10.0.10:1792/load_profile',
			headers={
				'Content-Type': 'application/json'
			},
			data=json.dumps({'request': request})
		response = r.text
		return r
	
	def store_profile(self, request):
		r = requests.post(
			'https://10.10.0.10:1792/store_profile',
			headers={
				'Content-Type': 'application/json'
			},
			data=json.dumps({'request': request})
		response = r.text
		return r

	def create_profile(self, request):
	r = requests.post(
		'https://10.10.0.10:1792/store_profile',
		headers={
			'Content-Type': 'application/json'
		},
		data=json.dumps({'request': request})
	return r

	def recover_profile(self, request):
		r = requests.post(
			'https://10.10.0.10:1792/recover_profile',
			headers={
				'Content-Type': 'application/json'
			},
			data=json.dumps({'request': request})
	return r

	def reset_password(self, request):
		r = requests.post(
			'https://10.10.0.10:1792/reset_password',
			headers={
				'Content-Type': 'application/json'
			},
			data=json.dumps({'request': request})
		return r.text


