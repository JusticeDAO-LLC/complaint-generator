from cgitb import text
from dataclasses import fields
from lib2to3.pytree import _Results
import profile
from readline import append_history_file
from urllib import response



class State:
	@classmethod		

	def __init__(self):
		self.complaint_summary = None
		self.complaint = None
		self.log = []
		self.username = None
		self.password = None
		self.hashed_password = None
		self.hashed_username = None
		self.last_question = None
		self.answered_questions = {}
		self.questions = {}
		self.data = {}


	def resume(self):
		files = list(glob('statefiles/*.json'))

		if len(files) == 0:
			self.print_error('no statefiles')
			return

		print('available files:')

		for i, file in enumerate(files):
			print('[%i] %s' % (i+1, file))

		while True:
			choice = input('\npick a file (1-%i): ' % len(files))

			try:
				index = int(choice)
				file = files[index - 1]
				break
			except:
				continue

		with open(file) as f:
			self.mediator.set_state(json.load(f))

	def from_serialized(cls, serialized):
		state = cls()
		state.inquiries = serialized['inquiries']
		state.complaint = serialized['complaint']
		state.log = serialized['log']

		return state
		
	def serialize(self):
		return {
			'inquiries': self.inquiries,
			'complaint': self.complaint,
			'log': self.log
		}

	def save(self):
		state = self.mediator.get_state()
		date = datetime.strftime(datetime.now(), '%d-%m-%Y %H+%M+%S')
		peek = state['inquiries'][0]['answer'][0:20]
		file = 'statefiles/%s %s.json' % (date, peek)

		with open(file, 'w') as f:
			json.dump(state, f, indent=4)

		print('[wrote statefile to %s]' % file)



	
	def load_profile(self, request):
		r = requests.post(
			'https://10.10.0.10:1792/load_profile',
			headers={
				'Content-Type': 'application/json'
			},
			data=json.dumps({'request': request})
		response  = json.loads(r.text)
		if "err" in response:
			self.log.append(response["err"])			
		else:
			response_results = response["results"]
			for result in results:
				setattr(self, result, results[result])
			
			return response_results
		
	def store_profile(self, request):

		profile_fields = "complaint_summary, complaint, log, username, password, hashed_password, hashed_username,	last_question, answered_questions, questions, data"
		profile_fields_list = profile_fields.split(", ")
		profile = {}
		for i in range(0, len(profile_fields_list)):
			profile[profile_fields_list[i]] = getattr(self, profile_fields_list[i])

		r = requests.post(
			'https://10.10.0.10:1792/store_profile',
			headers={
				'Content-Type': 'application/json'
			},
			data=json.dumps({'request': profile})
		response  = json.loads(r.text)
		if "err" in response:
			self.log.append(response["err"])
		else:
			return response

	def create_profile(self, request):
		r = requests.post(
			'https://10.10.0.10:1792/store_profile',
			headers={
				'Content-Type': 'application/json'
			},
			data=json.dumps({'request': request})
		response  = json.loads(r.text)
		return response

	def recover_profile(self, request):
		r = requests.post(
			'https://10.10.0.10:1792/recover_profile',
			headers={
				'Content-Type': 'application/json'
			},
			data=json.dumps({'request': request})
		response  = json.loads(r.text)
		return response

	def reset_password(self, request):
		r = requests.post(
			'https://10.10.0.10:1792/reset_password',
			headers={
				'Content-Type': 'application/json'
			},
			data=json.dumps({'request': request})
		response  = json.loads(r.text)
		return response



