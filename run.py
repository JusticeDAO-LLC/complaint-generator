from turtle import back
import toml
from lib.log import init_logging, make_logger
from backends import OpenAIBackend, WorkstationBackend
from mediator import Mediator
from applications import CLI



with open('config.toml') as f:
	config = toml.load(f)
	config_backends = config['BACKENDS']
	config_mediator = config['MEDIATOR']
	config_application = config['APPLICATION']
	config_log = config['LOG']


init_logging(level=config_log['level'])
log = make_logger('main')

log.info('log level is set to: %s' % config_log['level'])
log.info('config is loaded successfully')
log.info('creating mediator with backends: %s' % ', '.join(config_mediator['backends']))




backends = []

for backend_id in config_mediator['backends']:
	backend_config = next((conf for conf in config_backends if conf['id'] == backend_id), None)

	if not backend_config:
		log.error('missing backend configuration "%s" - cannot continue' % backend_id)
		exit(-1)

	if backend_config['type'] == 'openai':
		backend = OpenAIBackend(**backend_config)
	elif backend_config['type'] == 'workstation':
		backend = WorkstationBackend(**backend_config)

	backends.append(backend)


#test backend
#print(backends[1]('What is 4 + 4?'))


mediator = Mediator(backends=backends)

if config_application['type'] == 'cli':
	CLI(mediator)