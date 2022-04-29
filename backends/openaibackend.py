import requests
import json


class OpenAIBackend:
	def __init__(self, id, api_key, engine, **config):
		self.id = id
		self.api_key = api_key
		self.engine = engine
		self.config = config


	def __call__(self, text):
		r = requests.post(
			'https://api.openai.com/v1/engines/'+ self.engine + '/completions' , 
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

# data = OpenAIBackend('openai', 'sk-hhmt0YZxBvLUyBolMj93330e0WVy5upUdsQKA2cE', 'text-davinci-002', temperature = 0.7, max_tokens = 256, top_p = 1, frequency_penalty = 0, presence_penalty = 0).__call__("Hello, world!")
# print(data)
