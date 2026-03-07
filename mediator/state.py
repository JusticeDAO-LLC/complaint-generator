"""State management for complaint mediator workflow."""
import json
import os
import sys
import time
import warnings
from dataclasses import fields
from datetime import datetime
from glob import glob

import requests

from backends.llm_router_backend import LLMRouterBackend



class State:
	@classmethod		

	def __init__(self, **kwargs):
		self.data_fields = list(str("complaint_summary original_complaint log username password hashed_username hashed_password chat_history questions answered_questions last_question last_message").split(" "))
		self.complaint_summary = None
		self.original_complaint = None
		# Core mediator workflow fields
		self.inquiries = []
		self.complaint = None
		self.log = []
		self.username = None
		self.password = None
		self.hashed_password = None
		self.hashed_username = None
		self.last_question = None
		self.last_message = None
		self.current_inquiry = None
		self.current_inquiry_explanation = None
		self.answered_questions = {}
		self.questions = {}
		self.data = {}
		self.chat_history = {}

		self.hostname = "http://10.10.0.10:1792"
		self.hostname2 = "http://localhost:19000"

	def response(self):
		warnings.warn(
			"State.response() legacy OpenAI/HF path is deprecated; routing via llm_router.",
			DeprecationWarning,
			stacklevel=2,
		)

		response_message = ''
		now = datetime.now()
		time_str = now.strftime("%Y-%m-%d %H:%M:%S")

		provider = os.environ.get("COMPLAINT_GENERATOR_LLM_PROVIDER", "copilot_cli")
		model = os.environ.get("COMPLAINT_GENERATOR_LLM_MODEL", "gpt-5-mini")
		backend = LLMRouterBackend(id="llm-router", provider=provider, model=model)
		response_message = backend("what does the word copyright mean?")
		self.append_chat_history(response_message, timestamp=time_str)
		return response_message

	def normalize_chat_history_entry(self, entry):
		if isinstance(entry, dict):
			normalized = dict(entry)
		else:
			normalized = {"message": entry}

		normalized_message = normalized.get("message")
		if normalized_message is None:
			normalized_message = normalized.get("question") or ""
		normalized["message"] = normalized_message

		if normalized.get("question") is None:
			inquiry = normalized.get("inquiry")
			if isinstance(inquiry, dict):
				normalized["question"] = inquiry.get("question") or normalized_message
			else:
				normalized["question"] = normalized_message

		return normalized

	def normalize_chat_history(self, chat_history):
		if not isinstance(chat_history, dict):
			return {}
		return {
			key: self.normalize_chat_history_entry(value)
			for key, value in chat_history.items()
		}

	def _sync_chat_history_state(self):
		normalized = self.normalize_chat_history(self.data.get("chat_history", {}))
		self.data["chat_history"] = normalized
		self.chat_history = normalized
		if normalized:
			last_entry = list(normalized.values())[-1]
			self.last_message = last_entry.get("message")

	def extract_chat_history_context_strings(self, limit=3):
		self._sync_chat_history_state()
		chat_history = self.chat_history
		context = []
		for _, value in list(chat_history.items())[-limit:]:
			for candidate in (value.get("message"), value.get("question")):
				text = str(candidate or "").strip()
				if text and text not in context:
					context.append(text)
		return context

	def append_chat_history(self, message, sender=None, inquiry=None, explanation=None, hashed_username=None, timestamp=None):
		if "chat_history" not in self.data or not isinstance(self.data.get("chat_history"), dict):
			self.data["chat_history"] = {}

		entry = self.normalize_chat_history_entry(message)

		if sender is not None and "sender" not in entry:
			entry["sender"] = sender
		if inquiry is not None and "inquiry" not in entry:
			entry["inquiry"] = inquiry
		if explanation is not None and "explanation" not in entry:
			entry["explanation"] = explanation
		if hashed_username is not None and "hashed_username" not in entry:
			entry["hashed_username"] = hashed_username
		if entry.get("question") is None and isinstance(entry.get("inquiry"), dict):
			entry["question"] = entry["inquiry"].get("question") or entry.get("message")
		elif entry.get("question") is None:
			entry["question"] = entry.get("message")

		time_str = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		self.data["chat_history"][time_str] = entry
		self._sync_chat_history_state()
		return entry

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

	@classmethod
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
		date = datetime.now().strftime('%d-%m-%Y %H+%M+%S')
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

				if isinstance(resultsData, dict) and "chat_history" in resultsData:
					resultsData["chat_history"] = self.normalize_chat_history(resultsData.get("chat_history"))


				# resultsData["data"] = None
				for result in resultsData:
					self.data[result] = resultsData[result]
				self._sync_chat_history_state()

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
					self.merge_dictionaries(dict1[key], dict2[key])
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
		self.append_chat_history(message)
		return None


if __name__ == "__main__":
	test = State()
	data = test.response()
	print(data)