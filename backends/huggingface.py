import requests
import json

def install_pip_module(module_name):
	import subprocess
	import sys

	try:
		subprocess.check_call([sys.executable, '-m', 'pip', 'install', module_name])
	except subprocess.CalledProcessError as e:
		print('Failed to install module %s' % module_name)
		raise e

# install_pip_module('huggingface_hub')
# install_pip_module('huggingface_inference')

class HuggingFaceBackend:
	def __init__(self, id, api_key, engine, **config):
		self.id = id
		self.api_key = api_key
		self.engine = engine
		self.config = config

		self.API_URL = "https://api-inference.huggingface.co/models/" + self.engine
		self.headers = {"Authorization": f"Bearer {api_key}"}

	def __call__(self, payload):
		data = json.dumps(payload)
		response = requests.request("POST", self.API_URL , headers=self.headers, data=data)
		return json.loads(response.content.decode("utf-8"))

data = HuggingFaceBackend('huggingface', '', 'bert-base-cased').__call__({"text": "Hello, world!"})