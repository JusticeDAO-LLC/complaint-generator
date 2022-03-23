import json
from lib.log import make_logger
from mediator.exceptions import UserPresentableException
from datetime import datetime
from glob import glob

log = make_logger('cli')


class CLI:
	def __init__(self, mediator):
		self.mediator = mediator

		log.info('created CLI app')

		print('')
		print('*** JusticeDAO / Complaint Generator v1.0 ***')
		print('')
		print('commands are:')
		self.print_commands()
		print('')

		self.feed()
		self.loop()


	def loop(self):
		while True:
			text = input('\n> ')

			print('')

			if text == '':
				self.feed()
			elif text[0] != '!':
				self.feed(text)
			else:
				self.interpret_command(text[1:])
			

	def feed(self, text=None):
		try:
			self.print_response(self.mediator.io(text))
		except UserPresentableException as exception:
			self.print_error(exception.description)
		except Exception as exception:
			self.print_error('error occured: %s' % exception)
			print('\ninternal state may be corrupted. proceed with caution.')



	def interpret_command(self, line):
		parts = line.split(' ')
		command = parts[0]

		if command == 'reset':
			self.mediator.reset()
			self.feed()
		elif command == 'save':
			self.save()
		elif command == 'resume':
			self.resume()
		else:
			self.print_error('command unknown, available commands are:')
			self.print_commands()


	def save(self):
		state = self.mediator.get_state()
		date = datetime.strftime(datetime.now(), '%d-%m-%Y %H+%M+%S')
		peek = state['inquiries'][0]['answer'][0:20]
		file = 'statefiles/%s %s.json' % (date, peek)
		
		with open(file, 'w') as f:
			json.dump(state, f, indent=4)

		print('[wrote statefile to %s]' % file)


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
			
		print('')
		print('[resumed state]')
		print('')

		self.feed()

			


	def print_response(self, text):
		print('\033[1m%s\033[0m' % text)

	def print_error(self, text):
		print('\033[91m%s\033[0m' % text)

	def print_commands(self):
		print('!reset      wipe current state and start over')
		print('!resume     resumes from a statefile from disk')
		print('!save       saves current state to disk')