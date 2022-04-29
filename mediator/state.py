# from asyncio.windows_events import NULL
from ast import Return
from cgitb import text
from dataclasses import fields
# from lib2to3.pytree import _Results
import profile
from readline import append_history_file
from time import sleep
from urllib import response
import json
import datetime
import glob
import requests
import datetime 
import sys
import time
sys.path.append('../backends') 
from huggingface import HuggingFaceBackend
sys.path.append('../backends') 
from openaibackend import OpenAIBackend



class State:
	@classmethod		

	def __init__(self, **kwargs):
		self.data_fields = list(str("complaint_summary original_complaint log username password hashed_username hashed_password chat_history questions answered_questions last_question last_message").split(" "))
		self.complaint_summary = None
		self.original_complaint = None
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
		self.chat_history = {}

		self.hostname = "http://10.10.0.10:1792"
		self.hostname2 = "http://localhost:19000"

	def response(self):
		response_message = ''
		now = datetime.datetime.now()
		time = now.strftime("%Y-%m-%d %H:%M:%S")
		# print(self.data)
		labels = ''
		while "error" in HuggingFaceBackend('intent', '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', 'bespin-global/klue-roberta-small-3i4k-intent-classification').__call__({"inputs": "what does the word copyright mean?"}):
			sleep(5)
			pass
		labels = HuggingFaceBackend('intent', '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', 'bespin-global/klue-roberta-small-3i4k-intent-classification').__call__({"inputs": "what does the word copyright mean?"})
		label_dict = {}
		best_score = 0
		for label in labels[0]:
			label_dict[label['label']] = label['score']
		best_label = None
		for label in label_dict:
			score = label_dict[label]
			if score > best_score:
				best_score = score
				best_label = label
			else:
				pass
		intent = ''
		if best_label == "question" or best_label == "rhetorical question":
			label_question_type = ""
			if best_label == "question":
				response_message = OpenAIBackend('openai', 'sk-hhmt0YZxBvLUyBolMj93330e0WVy5upUdsQKA2cE', 'text-davinci-002', temperature = 0.7, max_tokens = 256, top_p = 1, frequency_penalty = 0, presence_penalty = 0).__call__("what does the word copyright mean?")
			if best_label == "rhetorical question":
				response_message = OpenAIBackend('openai', 'sk-hhmt0YZxBvLUyBolMj93330e0WVy5upUdsQKA2cE', 'text-davinci-002', temperature = 0.7, max_tokens = 256, top_p = 1, frequency_penalty = 0, presence_penalty = 0).__call__("what does the word copyright mean?")				
			pass
		if best_label == "command" or best_label == "rhetorical command":
			label_command_type = ""
			command_list = ["1", "2"]
			if label_command_type not in command_list:
				response_message = "I don't understand that command"
				pass
			else:
				# run_command(label_command_type)
				pass
			pass
		if best_label == "fragment" or best_label == "statement":
			# answer = ''
			pass
		if best_label == 'intonation-dependent utterance':
			# unknown = ''
			reponse_message = 'I don\'t know what you mean. please try again.'
			pass

		# data = HuggingFaceBackend('huggingface', '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', 'EleutherAI/gpt-j-6B').__call__({"inputs": "Hello, world!"})
		# response_message = dict({"sender": "Bot","message": data[0]["generated_text"]})
		if "chat_history" not in self.data:
			self.data["chat_history"] = {}
		self.data["chat_history"][time] = response_message
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
				if type(response["data"]) is str:
					resultsData = json.loads(response["data"])
				else:
					resultsData = response["data"]


				# resultsData["data"] = None
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


	def merge_dictionaries(self, dict1, dict2):
		for key in dict2:
			if key in dict1:
				if isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
					merge_dictionaries(dict1[key], dict2[key])
				elif isinstance(dict1[key], list) and isinstance(dict2[key], list):
					dict1[key].extend(dict2[key])
				else:
					dict1[key] = dict2[key]
			else:
				dict1[key] = dict2[key]
		return dict1   



	def store_profile(self, request):
		store_data = dict()
		if "hashed_username" in request["results"]:
			hashed_username = request["results"]["hashed_username"]
		if "hashed_password" in request["results"]:
			hashed_password = request["results"]["hashed_password"]
		if "data" in request["results"]:
			data = request["results"]["data"]
		else:
			data = None
		if type(data) is str:
			data = json.loads(data)
		if hashed_username is not None and hashed_password is not None:
			for item in self.data_fields:
				# if "data" not in item:
				store_data[item] = self.data[item]
				# pass
			if (type(data) is dict) and (type(store_data) is dict):
				store_data = self.merge_dictionaries(data, store_data)	
		
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
		now = datetime.datetime.now()
		time = now.strftime("%Y-%m-%d %H:%M:%S")
		if "chat_history" not in self.data:
			self.data["chat_history"] = {}
		self.data["chat_history"][time] = message
		return None


test = State()
data = test.response()
print(data)