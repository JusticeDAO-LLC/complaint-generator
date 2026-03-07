import argparse
import json
import os

from lib.log import init_logging, make_logger
from backends import WorkstationBackendModels, WorkstationBackendDatabases, LLMRouterBackend
from mediator import Mediator

parser = argparse.ArgumentParser(description='Complaint Generator')
parser.add_argument(
	'--config',
	default=os.environ.get('COMPLAINT_GENERATOR_CONFIG', 'config.llm_router.json'),
	help='Path to configuration JSON (default: config.llm_router.json)'
)
parser.add_argument(
	'--export-reranker-metrics',
	default=None,
	nargs='?',
	const='',
	help='Export reranker metrics JSON on shutdown; provide optional path or omit to auto-generate under statefiles/'
)
args = parser.parse_args()

if not os.path.exists(args.config):
	raise FileNotFoundError(f'Config not found: {args.config}')

with open(args.config) as f:
	config = json.load(f)
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
		log.warning('backend type "openai" is deprecated; routing via llm_router instead')
		cfg = dict(backend_config)
		model = cfg.get('model') or cfg.get('engine')
		# llm_router reads secrets from env; ignore explicit api_key fields.
		cfg.pop('api_key', None)
		cfg.pop('engine', None)
		backend = LLMRouterBackend(id=cfg.get('id', backend_id), provider=cfg.get('provider', 'openai'), model=model, **{k: v for k, v in cfg.items() if k not in ('id', 'type', 'provider', 'model')})
	elif backend_config['type'] == 'huggingface':
		log.warning('backend type "huggingface" is deprecated; routing via llm_router instead')
		cfg = dict(backend_config)
		model = cfg.get('model') or cfg.get('engine')
		cfg.pop('api_key', None)
		cfg.pop('engine', None)
		backend = LLMRouterBackend(id=cfg.get('id', backend_id), provider=cfg.get('provider', 'huggingface'), model=model, **{k: v for k, v in cfg.items() if k not in ('id', 'type', 'provider', 'model')})
	elif backend_config['type'] == 'workstation':
		backendDatabases  = WorkstationBackendDatabases(**backend_config)
		backendModels = WorkstationBackendModels(**backend_config)
		backend = backendModels  # Use backendModels as the primary backend
	elif backend_config['type'] == 'llm_router':
		backend = LLMRouterBackend(**backend_config)
	else:
		log.error('unknown backend type: %s' % backend_config['type'])
		exit(-1)
	backends.append(backend)


#test backend
#print(backends[1]('What is 4 + 4?'))

# inquiries = Inquiries(hashed_username = hashed_username, hashed_password = hashed_password, token = token)
mediator = Mediator(backends=backends)

try:
	for type in config_application['type']:
		if type == 'cli':
			from applications import CLI
			application = CLI(mediator)
		elif type == 'server':
			from applications import SERVER
			application = SERVER(mediator)
		else:
			log.error('unknown application type: %s' % type)
			exit(-1)

		application.run()
finally:
	if args.export_reranker_metrics is not None:
		try:
			requested_path = args.export_reranker_metrics or None
			export_path = mediator.export_reranker_metrics_json(requested_path)
			log.info('reranker metrics exported to: %s' % export_path)
		except Exception as exception:
			log.error('failed to export reranker metrics: %s' % str(exception))
	

