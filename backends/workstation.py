import requests
import json

class WorkstationBackendModels:
	def __init__(self, id, model, **config):
		self.id = id
		self.model = model
		self.config = config

		del self.config['type']


	def __call__(self, text):
		r = requests.post(
			'https://%s.justicedao.biz/generate' % self.model, 
			headers={
				'Content-Type': 'application/json'
			}, 
			data=json.dumps({'prompt': text, **self.config})
		)

		data = json.loads(r.text)

		return data['output']

class WorkstationBackendDatabases:
	def __init__(self, id, model, **config):
		self.id = id
		# self.model = model
		# self.config = config

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
