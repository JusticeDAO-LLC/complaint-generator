import requests
import json


class OpenAIBackend:
	def __init__(self, id, api_key, engine, **config):
		self.id = id
		self.api_key = api_key
		self.engine = engine
		self.config = config

		del self.config['type']

	def __call__(self, text):
		r = requests.post(
			'https://api.openai.com/v1/engines/%s/completions' % self.engine, 
			headers={
				'Content-Type': 'application/json',
				'Authorization': 'Bearer %s' % self.api_key
			}, 
			data=json.dumps({'prompt': text, **self.config})
		)

		data = json.loads(r.text)

		try:
			return data['choices'][0]['text'].strip()
		except Exception as exception:
			raise Exception('empty-response')

