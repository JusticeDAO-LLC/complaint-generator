from cgitb import text
from dataclasses import fields
# from lib2to3.pytree import _Results
import profile
from readline import append_history_file
from urllib import response
import json
import datetime
import glob
import requests
import datetime 

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
		self.last_message = None
		self.answered_questions = {}
		self.questions = {}
		self.data = {}
		self.chat_history = []

		self.hostname = "http://10.10.0.10:1792"
		self.hostname2 = "http://localhost:19000"

	def response(self):
		response_message = dict({"sender": "Bot:","message":"response"})
		if "chat_history" not in self.data:
			self.data["chat_history"] = []
		self.data["chat_history"].append(response_message)
		return response_message

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
		if "hashed_username" in request["results"]:
			hashed_username = request["results"]["hashed_username"]
		if "hashed_password" in request["results"]:
			hashed_password = request["results"]["hashed_password"]
		if hashed_username is not None and hashed_password is not None:
			r = requests.post(
				self.hostname + '/load_profile',
				headers={
					'Content-Type': 'application/json'
				},
				data=json.dumps({'request': {"hashed_username": hashed_username, "hashed_password": hashed_password}})
			)

			if "{" in r.text:
				response  = json.loads(r.text)
			if type(response) is list:
				response = response[0]
			if "Err" in response:
				self.log.append(response["Err"])
				return ({"Err": response["Err"]})
			else:
				resultsData = json.loads(response["data"])
				for result in resultsData:
					self.data[result] = resultsData[result]
				return resultsData
			
		else:
			self.log.append("No username or password provided")
			return ({"Err": "No username or password provided"})

	def get_class_attributes(self):
		return [field.name for field in fields(self)]


	def get_class_attributes_with_values(self):
		return {field.name: getattr(self, field.name) for field in fields(self)}



	def store_profile(self, request):
		store_data = dict()
		if "hashed_username" in request["results"]:
			hashed_username = request["results"]["hashed_username"]
		if "hashed_password" in request["results"]:
			hashed_password = request["results"]["hashed_password"]
		if hashed_username is not None and hashed_password is not None:
			for item in self.data:
				store_data[item] = self.data[item]
			r = requests.post(
				self.hostname + '/store_profile',
				headers={
					'Content-Type': 'application/json'
				},
				data=json.dumps({'request': {"hashed_username": hashed_username, "hashed_password": hashed_password, "data": store_data}})
			)

			if "{" in r.text:
				response  = json.loads(r.text)
				if type(response) is list:
					response = response[0]				
				if "Err" in response:
					self.log.append(response["Err"])
					return ({"Err": response["Err"]})
				else:
					if "data" in response:
						resultsData = json.loads(response["data"])
						return resultsData
			
		else:
			self.log.append("No username or password provided")
			return ({"Err": "No username or password provided"})
			
	def recover_profile(self, request):
		r = requests.post(
			'https://10.10.0.10:1792/recover_profile',
			headers={
				'Content-Type': 'application/json'
			},
			data=json.dumps({'request': request})
		)
		response  = json.loads(r.text)
		return response

	def reset_password(self, request):
		r = requests.post(
			'https://10.10.0.10:1792/reset_password',
			headers={
				'Content-Type': 'application/json'
			},
			data=json.dumps({'request': request})
		)
		response  = json.loads(r.text)
		return response



	def message(self, message):
		self.chat_history.append({"from" : "Me", "message": message, "timestamp": datetime.datetime.now()})
		return None