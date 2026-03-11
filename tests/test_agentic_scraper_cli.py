import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def _load_cli_module():
    module_path = Path(__file__).resolve().parents[1] / 'scripts' / 'agentic_scraper_cli.py'
    spec = importlib.util.spec_from_file_location('agentic_scraper_cli', module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_parser_parses_run_command():
    cli = _load_cli_module()
    parser = cli.create_parser()

    args = parser.parse_args([
        '--allow-no-backend',
        'run',
        '--keywords', 'employment', 'discrimination',
        '--domains', 'eeoc.gov', 'dol.gov',
        '--iterations', '2',
    ])

    assert args.command == 'run'
    assert args.allow_no_backend is True
    assert args.keywords == ['employment', 'discrimination']
    assert args.domains == ['eeoc.gov', 'dol.gov']
    assert args.iterations == 2


def test_create_parser_parses_worker_command():
    cli = _load_cli_module()
    parser = cli.create_parser()

    args = parser.parse_args([
        'worker',
        '--once',
        '--poll-seconds', '5',
        '--max-jobs', '2',
    ])

    assert args.command == 'worker'
    assert args.once is True
    assert args.poll_seconds == 5.0
    assert args.max_jobs == 2


def test_execute_command_dispatches_run_to_mediator():
    cli = _load_cli_module()
    mediator = Mock()
    mediator.state = SimpleNamespace(username=None)
    mediator.run_agentic_scraper_cycle = Mock(return_value={'iterations': [], 'final_results': []})

    args = SimpleNamespace(
        command='run',
        keywords=['employment discrimination'],
        domains=['eeoc.gov'],
        iterations=3,
        sleep_seconds=0.0,
        quality_domain='caselaw',
        user_id='testuser',
        claim_type='employment discrimination',
        min_relevance=0.6,
        no_store_results=False,
    )

    result = cli.execute_command(args, mediator)

    assert result == {'iterations': [], 'final_results': []}
    mediator.run_agentic_scraper_cycle.assert_called_once()
    kwargs = mediator.run_agentic_scraper_cycle.call_args.kwargs
    assert kwargs['user_id'] == 'testuser'
    assert kwargs['store_results'] is True


def test_execute_command_dispatches_enqueue_to_mediator():
    cli = _load_cli_module()
    mediator = Mock()
    mediator.state = SimpleNamespace(username=None)
    mediator.enqueue_agentic_scraper_job = Mock(return_value={'queued': True, 'job_id': 12})

    args = SimpleNamespace(
        command='enqueue',
        keywords=['employment discrimination'],
        domains=['eeoc.gov'],
        iterations=2,
        sleep_seconds=0.0,
        quality_domain='caselaw',
        user_id='testuser',
        claim_type='employment discrimination',
        min_relevance=0.65,
        no_store_results=False,
        priority=10,
        ready_in_seconds=0.0,
    )

    result = cli.execute_command(args, mediator)

    assert result == {'queued': True, 'job_id': 12}
    mediator.enqueue_agentic_scraper_job.assert_called_once()
    kwargs = mediator.enqueue_agentic_scraper_job.call_args.kwargs
    assert kwargs['user_id'] == 'testuser'
    assert kwargs['priority'] == 10
    assert kwargs['store_results'] is True


def test_execute_command_worker_exits_cleanly_when_queue_is_empty():
    cli = _load_cli_module()
    mediator = Mock()
    mediator.state = SimpleNamespace(username=None)
    mediator.run_next_agentic_scraper_job = Mock(return_value={'claimed': False, 'job': None})

    args = SimpleNamespace(
        command='worker',
        worker_id='worker-1',
        user_id=None,
        poll_seconds=0.0,
        max_jobs=0,
        max_idle_polls=0,
        once=True,
    )

    result = cli.execute_command(args, mediator)

    assert result['idle'] is True
    assert result['processed_jobs'] == []
    mediator.run_next_agentic_scraper_job.assert_called_once_with(worker_id='worker-1', user_id=None)


def test_format_history_rows_renders_summary_lines():
    cli = _load_cli_module()
    output = cli.format_history_rows([
        {
            'id': 5,
            'claim_type': 'employment discrimination',
            'iteration_count': 3,
            'stored_count': 4,
            'unique_url_count': 7,
        }
    ])

    assert 'run_id=5' in output
    assert 'employment discrimination' in output
    assert 'stored=4' in output


def test_render_output_formats_tactics():
    cli = _load_cli_module()
    output = cli.render_output('tactics', {
        'tactics': [
            {
                'name': 'multi_engine_search',
                'avg_quality_score': 82.0,
                'avg_weight': 1.15,
                'observation_count': 6,
            }
        ]
    }, as_json=False)

    assert 'multi_engine_search' in output
    assert 'quality=82.00' in output


def test_render_output_formats_queue_rows():
    cli = _load_cli_module()
    output = cli.render_output('queue', {
        'jobs': [
            {
                'id': 4,
                'status': 'queued',
                'priority': 20,
                'claim_type': 'employment discrimination',
                'keywords': ['employment', 'discrimination'],
            }
        ]
    }, as_json=False)

    assert 'job_id=4' in output
    assert 'status=queued' in output
    assert 'employment discrimination' in output


def test_render_output_formats_idle_worker_state():
    cli = _load_cli_module()
    output = cli.render_output('worker', {
        'processed_jobs': [],
        'idle': True,
    }, as_json=False)

    assert output == 'No queued scraper jobs available.'