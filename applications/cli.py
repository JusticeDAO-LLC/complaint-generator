import json
import shlex
from urllib import request
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
			
			if self.mediator.state.hashed_username is not None and self.mediator.state.hashed_password is not None:
				profile = self.mediator.state.load_profile(self, {"hashed_username": self.mediator.state.hashed_username, "hashed_password": self.mediator.state.hashed_password})
			else:
				if self.mediator.state.username is None:	
					self.mediator.state.username = input('Username:\n> ')
			
				if self.mediator.state.password is None:
					self.mediator.state.password = input('Password:\n> ')
				profile = self.mediator.state.load_profile(self, {"username": self.mediator.state.username, "password": self.mediator.state.password})

			last_question = self.mediator.state.last_question

			text = input(last_question + '> ')
			self.mediator.state.answered_questions["last_question"] = text

			if text == '':
				self.feed()
			elif text[0] != '!':
				self.feed(text)
			else:
				self.interpret_command(text[len(last_question + '> '):])

			self.mediator.state.last_question.pop(0)
			self.mediator.state.store_profile(self, profile)

	def feed(self, text=None):
		try:
			self.print_response(self.mediator.io(text))
		except UserPresentableException as exception:
			self.print_error(exception.description)
		except Exception as exception:
			self.print_error('error occured: %s' % exception)
			print('\ninternal state may be corrupted. proceed with caution.')



	def interpret_command(self, line):
		parts = shlex.split(line)
		if not parts:
			self.print_error('command unknown, available commands are:')
			self.print_commands()
			return
		command = parts[0]

		if command == 'reset':
			self.mediator.reset()
			self.feed()
		elif command == 'save':
			self.save()
		elif command == 'resume':
			self.resume()
		elif command == 'claim-review':
			self.claim_review(parts[1:])
		elif command == 'execute-follow-up':
			self.execute_follow_up(parts[1:])
		else:
			self.print_error('command unknown, available commands are:')
			self.print_commands()

	def _parse_command_options(self, args):
		options = {}
		positionals = []
		for arg in args:
			if '=' not in arg:
				positionals.append(arg)
				continue
			key, value = arg.split('=', 1)
			value = value.strip()
			lowered = value.lower()
			if lowered in ('true', 'false'):
				parsed_value = lowered == 'true'
			elif key.replace('-', '_') == 'required_support_kinds':
				parsed_value = [item.strip() for item in value.split(',') if item.strip()]
			else:
				try:
					parsed_value = int(value)
				except ValueError:
					parsed_value = value
			options[key.replace('-', '_')] = parsed_value
		return positionals, options

	def claim_review(self, args):
		positionals, options = self._parse_command_options(args)
		claim_type = options.get('claim_type')
		if claim_type is None and positionals:
			claim_type = ' '.join(positionals)
		payload = self.mediator.build_claim_support_review_payload(
			claim_type=claim_type,
			user_id=options.get('user_id'),
			required_support_kinds=options.get('required_support_kinds'),
			follow_up_cooldown_seconds=options.get('follow_up_cooldown_seconds', 3600),
			include_support_summary=options.get('include_support_summary', True),
			include_overview=options.get('include_overview', True),
			include_follow_up_plan=options.get('include_follow_up_plan', True),
			execute_follow_up=options.get('execute_follow_up', False),
			follow_up_support_kind=options.get('follow_up_support_kind'),
			follow_up_max_tasks_per_claim=options.get('follow_up_max_tasks_per_claim', 3),
		)
		self.print_response(json.dumps(payload, indent=2, default=str))

	def execute_follow_up(self, args):
		positionals, options = self._parse_command_options(args)
		claim_type = options.get('claim_type')
		if claim_type is None and positionals:
			claim_type = ' '.join(positionals)
		payload = self.mediator.build_claim_support_follow_up_execution_payload(
			claim_type=claim_type,
			user_id=options.get('user_id'),
			required_support_kinds=options.get('required_support_kinds'),
			follow_up_cooldown_seconds=options.get('follow_up_cooldown_seconds', 3600),
			follow_up_support_kind=options.get('follow_up_support_kind'),
			follow_up_max_tasks_per_claim=options.get('follow_up_max_tasks_per_claim', 3),
			follow_up_force=options.get('follow_up_force', False),
			include_post_execution_review=options.get('include_post_execution_review', True),
			include_support_summary=options.get('include_support_summary', True),
			include_overview=options.get('include_overview', True),
			include_follow_up_plan=options.get('include_follow_up_plan', True),
		)
		self.print_response(json.dumps(payload, indent=2, default=str))


	def save(self):
		request = dict({"username": self.mediator.state.username, "password": self.mediator.state.password})
		profile = self.mediator.state.load_profile(self, request)
		profile["data"] = self.mediator.state.answered_questions
		profile["data"]["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		self.mediator.state.store_profile(self, profile)
		print("Profile saved")
	
	def resume(self):
		request = dict({"username": self.mediator.state.username, "password": self.mediator.state.password})
		profile = self.mediator.state.load_profile(self,request)
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
		print('!claim-review [claim_type] [key=value]')
		print('!execute-follow-up [claim_type] [key=value]')