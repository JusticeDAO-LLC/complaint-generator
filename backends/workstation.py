import requests
import json

class WorkstationBackendModels:
	def __init__(self, id, model, **config):
		self.id = id
		self.model = model
		self.config = config


	def __call__(self, text):
		r = requests.request("POST",
			'https://'+ self.model +'.justicedao.biz/generate', 
			headers={
				'Content-Type': 'application/json'
			}, 
			data=json.dumps({'prompt': text, **self.config}), 
			verify=False
		)

		data = json.loads(r.text)
		if 'output' in data.keys():
			return data['output']

class WorkstationBackendDatabases:
	def __init__(self, id, model, **config):
		self.id = id
		self.model = model
		self.config = config

		del self.config['type']


	def __call__(self, text):
		r = requests.post(
			'https://db.justicedao.biz/search_citation', 
			headers={
				'Content-Type': 'application/json'
			}, 
			data=json.dumps({'search_citation': text})
		)

		data = json.loads(r.text)

		return data['output']

class WorkstationLoadProfileState:
	def __init__(self, id, model, **config):
		self.id = id
		# self.model = model
		# self.config = config

		del self.config['type']


	def __call__(self, text):
		r = requests.post(
			'https://db.justicedao.biz/load_profile_state',
			headers={
				'Content-Type': 'application/json'
			}, 
			data=json.dumps({'request': text})
		)

		data = json.loads(r.text)

		return data['output']


class WorkstationSaveProfileState:
	def __init__(self, id, model, **config):
		self.id = id
		# self.model = model
		# self.config = config

		del self.config['type']


	def __call__(self, text):
		r = requests.post(
			'https://db.justicedao.biz/save_profile_state', 
			headers={
				'Content-Type': 'application/json'
			}, 
			data=json.dumps({'request': text})
		)

		data = json.loads(r.text)

		return data['output']

# data = WorkstationBackendModels('workstation', 't5').__call__("Hello, world!")
# print(data)

# data = WorkstationBackendModels('workstation', 'gptj').__call__("Hello, world!")
# print(data)