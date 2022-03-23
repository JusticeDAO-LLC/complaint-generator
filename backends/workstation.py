import requests
import json


class WorkstationBackend:
	def __init__(self, id, model, **config):
		self.id = id
		self.model = model
		self.config = config

		del self.config['type']


	def prompt(self, text):
		r = requests.post(
			'https://%s.justicedao.biz/generate' % self.model, 
			headers={
				'Content-Type': 'application/json'
			}, 
			data=json.dumps({'prompt': text, **self.config})
		)

		print(r.text)

		data = json.loads(r.text)

		return data

