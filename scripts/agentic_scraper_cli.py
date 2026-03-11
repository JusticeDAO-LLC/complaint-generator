#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backends import LLMRouterBackend, WorkstationBackendDatabases, WorkstationBackendModels
from mediator import Mediator


def load_config(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def build_backends(config: Dict[str, Any], backend_id: Optional[str] = None) -> List[Any]:
    mediator_config = config.get('MEDIATOR', {})
    backend_ids = mediator_config.get('backends', [])
    if backend_id:
        backend_ids = [backend_id]

    backends_config = config.get('BACKENDS', [])
    backends: List[Any] = []
    for current_backend_id in backend_ids:
        backend_config = next((item for item in backends_config if item.get('id') == current_backend_id), None)
        if backend_config is None:
            raise ValueError(f'Missing backend configuration: {current_backend_id}')

        backend_type = backend_config.get('type')
        if backend_type == 'openai':
            cfg = dict(backend_config)
            model = cfg.get('model') or cfg.get('engine')
            cfg.pop('api_key', None)
            cfg.pop('engine', None)
            backend = LLMRouterBackend(
                id=cfg.get('id', current_backend_id),
                provider=cfg.get('provider', 'openai'),
                model=model,
                **{k: v for k, v in cfg.items() if k not in ('id', 'type', 'provider', 'model')},
            )
        elif backend_type == 'huggingface':
            cfg = dict(backend_config)
            model = cfg.get('model') or cfg.get('engine')
            cfg.pop('api_key', None)
            cfg.pop('engine', None)
            backend = LLMRouterBackend(
                id=cfg.get('id', current_backend_id),
                provider=cfg.get('provider', 'huggingface'),
                model=model,
                **{k: v for k, v in cfg.items() if k not in ('id', 'type', 'provider', 'model')},
            )
        elif backend_type == 'workstation':
            WorkstationBackendDatabases(**backend_config)
            backend = WorkstationBackendModels(**backend_config)
        elif backend_type == 'llm_router':
            backend = LLMRouterBackend(**backend_config)
        else:
            raise ValueError(f'Unsupported backend type: {backend_type}')
        backends.append(backend)
    return backends


def create_mediator(config_path: str, backend_id: Optional[str] = None, allow_no_backend: bool = False) -> Mediator:
    if not os.path.exists(config_path):
        if allow_no_backend:
            return Mediator(backends=[])
        raise FileNotFoundError(f'Config not found: {config_path}')

    config = load_config(config_path)
    try:
        backends = build_backends(config, backend_id=backend_id)
    except ValueError:
        if not allow_no_backend:
            raise
        backends = []
    return Mediator(backends=backends)


def format_run_summary(result: Dict[str, Any]) -> str:
    scraper_run = result.get('scraper_run', {}) if isinstance(result.get('scraper_run'), dict) else {}
    storage_summary = result.get('storage_summary', {}) if isinstance(result.get('storage_summary'), dict) else {}
    final_quality = result.get('final_quality', {}) if isinstance(result.get('final_quality'), dict) else {}
    return '\n'.join([
        f"iterations: {len(result.get('iterations', []) or [])}",
        f"final_results: {len(result.get('final_results', []) or [])}",
        f"stored: {int(storage_summary.get('stored', 0) or 0)}",
        f"new_records: {int(storage_summary.get('total_new', 0) or 0)}",
        f"reused_records: {int(storage_summary.get('total_reused', 0) or 0)}",
        f"quality_score: {float(final_quality.get('data_quality_score', 0.0) or 0.0):.2f}",
        f"persisted_run_id: {scraper_run.get('run_id', -1)}",
    ])


def format_history_rows(rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return 'No scraper runs found.'
    lines = []
    for row in rows:
        lines.append(
            f"run_id={row.get('id')} claim_type={row.get('claim_type') or '-'} iterations={row.get('iteration_count', 0)} "
            f"stored={row.get('stored_count', 0)} urls={row.get('unique_url_count', 0)}"
        )
    return '\n'.join(lines)


def format_tactic_rows(result: Dict[str, Any]) -> str:
    tactics = result.get('tactics', []) if isinstance(result, dict) else []
    if not tactics:
        return 'No tactic performance found.'
    lines = []
    for tactic in tactics:
        lines.append(
            f"{tactic.get('name')}: quality={float(tactic.get('avg_quality_score', 0.0) or 0.0):.2f} "
            f"weight={float(tactic.get('avg_weight', 0.0) or 0.0):.2f} obs={int(tactic.get('observation_count', 0) or 0)}"
        )
    return '\n'.join(lines)


def format_queue_rows(rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return 'No scraper jobs found.'
    lines = []
    for row in rows:
        keywords = ','.join(row.get('keywords', []) or [])
        lines.append(
            f"job_id={row.get('id')} status={row.get('status')} priority={row.get('priority', 100)} "
            f"claim_type={row.get('claim_type') or '-'} keywords={keywords or '-'}"
        )
    return '\n'.join(lines)


def format_worker_summary(payload: Dict[str, Any]) -> str:
    processed_jobs = payload.get('processed_jobs', []) if isinstance(payload, dict) else []
    if not processed_jobs and payload.get('idle'):
        return 'No queued scraper jobs available.'
    if not processed_jobs:
        return 'Worker did not process any scraper jobs.'

    lines = [f"processed_jobs: {len(processed_jobs)}"]
    for item in processed_jobs:
        lines.append(
            f"job_id={item.get('job_id')} status={item.get('status')} run_id={item.get('run_id', '-') } "
            f"claim_type={item.get('claim_type') or '-'}"
        )
    return '\n'.join(lines)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run and inspect the complaint-generator agentic scraper daemon')
    parser.add_argument(
        '--config',
        default=os.environ.get('COMPLAINT_GENERATOR_CONFIG', 'config.llm_router.json'),
        help='Path to configuration JSON (default: config.llm_router.json)',
    )
    parser.add_argument('--backend-id', default=None, help='Backend id to use from config')
    parser.add_argument('--allow-no-backend', action='store_true', help='Allow running without a configured backend')
    parser.add_argument('--json', action='store_true', help='Emit raw JSON output')

    subparsers = parser.add_subparsers(dest='command', required=True)

    run_parser = subparsers.add_parser('run', help='Run the bounded agentic scraper loop')
    run_parser.add_argument('--keywords', nargs='+', required=True, help='Seed keywords for the scraper loop')
    run_parser.add_argument('--domains', nargs='*', default=None, help='Optional domains to prioritize')
    run_parser.add_argument('--iterations', type=int, default=3, help='Number of optimization iterations')
    run_parser.add_argument('--sleep-seconds', type=float, default=0.0, help='Delay between iterations')
    run_parser.add_argument('--quality-domain', default='caselaw', help='Validation domain for scraper quality scoring')
    run_parser.add_argument('--user-id', default='cli-user', help='User id for stored records and run history')
    run_parser.add_argument('--claim-type', default=None, help='Optional claim type for stored results')
    run_parser.add_argument('--min-relevance', type=float, default=0.5, help='Minimum relevance when storing results')
    run_parser.add_argument('--no-store-results', action='store_true', help='Do not store accepted daemon results as evidence')

    enqueue_parser = subparsers.add_parser('enqueue', help='Queue a scraper job for later worker execution')
    enqueue_parser.add_argument('--keywords', nargs='+', required=True, help='Seed keywords for the scraper loop')
    enqueue_parser.add_argument('--domains', nargs='*', default=None, help='Optional domains to prioritize')
    enqueue_parser.add_argument('--iterations', type=int, default=3, help='Number of optimization iterations')
    enqueue_parser.add_argument('--sleep-seconds', type=float, default=0.0, help='Delay between iterations')
    enqueue_parser.add_argument('--quality-domain', default='caselaw', help='Validation domain for scraper quality scoring')
    enqueue_parser.add_argument('--user-id', default='cli-user', help='User id for queue ownership')
    enqueue_parser.add_argument('--claim-type', default=None, help='Optional claim type for stored results')
    enqueue_parser.add_argument('--min-relevance', type=float, default=0.5, help='Minimum relevance when storing results')
    enqueue_parser.add_argument('--priority', type=int, default=100, help='Lower numbers run first')
    enqueue_parser.add_argument('--ready-in-seconds', type=float, default=0.0, help='Delay before the job becomes claimable')
    enqueue_parser.add_argument('--no-store-results', action='store_true', help='Do not store accepted daemon results as evidence')

    queue_parser = subparsers.add_parser('queue', help='Show scraper queue entries')
    queue_parser.add_argument('--user-id', default='cli-user', help='User id to inspect')
    queue_parser.add_argument('--status', default='queued', choices=['queued', 'running', 'completed', 'failed', 'all'], help='Queue status to show')
    queue_parser.add_argument('--limit', type=int, default=20, help='Maximum number of jobs to return')

    worker_parser = subparsers.add_parser('worker', help='Consume queued scraper jobs')
    worker_parser.add_argument('--worker-id', default=f"scraper-worker@{socket.gethostname()}", help='Worker identifier for claimed jobs')
    worker_parser.add_argument('--user-id', default=None, help='Optional user id filter for claimed jobs')
    worker_parser.add_argument('--poll-seconds', type=float, default=30.0, help='Idle poll interval when no jobs are queued')
    worker_parser.add_argument('--max-jobs', type=int, default=0, help='Maximum queued jobs to process before exiting, 0 means unlimited')
    worker_parser.add_argument('--max-idle-polls', type=int, default=0, help='Maximum empty polls before exiting, 0 means unlimited')
    worker_parser.add_argument('--once', action='store_true', help='Poll once and exit if no queued job is available')

    history_parser = subparsers.add_parser('history', help='Show persisted scraper run summaries')
    history_parser.add_argument('--user-id', default='cli-user', help='User id to inspect')
    history_parser.add_argument('--limit', type=int, default=20, help='Maximum number of runs to return')

    detail_parser = subparsers.add_parser('detail', help='Show one persisted scraper run in detail')
    detail_parser.add_argument('run_id', type=int, help='Persisted scraper run id')

    tactics_parser = subparsers.add_parser('tactics', help='Show aggregated tactic performance')
    tactics_parser.add_argument('--user-id', default='cli-user', help='User id to inspect')
    tactics_parser.add_argument('--limit-runs', type=int, default=20, help='Number of recent runs to aggregate')

    return parser


def run_worker(args: argparse.Namespace, mediator: Mediator) -> Dict[str, Any]:
    processed_jobs: List[Dict[str, Any]] = []
    idle_polls = 0

    while True:
        result = mediator.run_next_agentic_scraper_job(worker_id=args.worker_id, user_id=args.user_id)
        job = result.get('job') or {}
        if result.get('claimed'):
            processed_jobs.append({
                'job_id': job.get('id'),
                'status': job.get('status'),
                'run_id': job.get('run_id'),
                'claim_type': job.get('claim_type'),
                'error': result.get('error'),
            })
            if args.once:
                break
            if args.max_jobs and len(processed_jobs) >= int(args.max_jobs):
                break
            continue

        idle_polls += 1
        if args.once or (args.max_idle_polls and idle_polls >= int(args.max_idle_polls)):
            return {
                'worker_id': args.worker_id,
                'processed_jobs': processed_jobs,
                'idle': True,
                'idle_polls': idle_polls,
                'last_poll': result,
            }
        time.sleep(max(float(args.poll_seconds), 0.0))

    return {
        'worker_id': args.worker_id,
        'processed_jobs': processed_jobs,
        'idle': False,
        'idle_polls': idle_polls,
    }


def execute_command(args: argparse.Namespace, mediator: Mediator) -> Dict[str, Any]:
    if args.command == 'run':
        mediator.state.username = args.user_id
        return mediator.run_agentic_scraper_cycle(
            keywords=args.keywords,
            domains=args.domains,
            iterations=args.iterations,
            sleep_seconds=args.sleep_seconds,
            quality_domain=args.quality_domain,
            user_id=args.user_id,
            claim_type=args.claim_type,
            min_relevance=args.min_relevance,
            store_results=not args.no_store_results,
        )
    if args.command == 'enqueue':
        mediator.state.username = args.user_id
        available_at = datetime.utcnow() + timedelta(seconds=max(float(args.ready_in_seconds), 0.0))
        return mediator.enqueue_agentic_scraper_job(
            keywords=args.keywords,
            domains=args.domains,
            iterations=args.iterations,
            sleep_seconds=args.sleep_seconds,
            quality_domain=args.quality_domain,
            user_id=args.user_id,
            claim_type=args.claim_type,
            min_relevance=args.min_relevance,
            store_results=not args.no_store_results,
            priority=args.priority,
            available_at=available_at,
        )
    if args.command == 'queue':
        if args.user_id:
            mediator.state.username = args.user_id
        status = None if args.status == 'all' else args.status
        return {'jobs': mediator.get_scraper_queue(user_id=args.user_id, status=status, limit=args.limit)}
    if args.command == 'worker':
        return run_worker(args, mediator)
    if args.command == 'history':
        mediator.state.username = args.user_id
        return {'runs': mediator.get_scraper_runs(user_id=args.user_id, limit=args.limit)}
    if args.command == 'detail':
        return mediator.get_scraper_run_details(args.run_id)
    if args.command == 'tactics':
        mediator.state.username = args.user_id
        return mediator.get_scraper_tactic_performance(user_id=args.user_id, limit_runs=args.limit_runs)
    raise ValueError(f'Unsupported command: {args.command}')


def render_output(command: str, payload: Dict[str, Any], as_json: bool) -> str:
    if as_json:
        return json.dumps(payload, indent=2, default=str)
    if command == 'run':
        return format_run_summary(payload)
    if command == 'enqueue':
        return f"queued_job_id: {payload.get('job_id', -1)}"
    if command == 'queue':
        return format_queue_rows(payload.get('jobs', []))
    if command == 'worker':
        return format_worker_summary(payload)
    if command == 'history':
        return format_history_rows(payload.get('runs', []))
    if command == 'detail':
        return json.dumps(payload, indent=2, default=str)
    if command == 'tactics':
        return format_tactic_rows(payload)
    return json.dumps(payload, indent=2, default=str)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    mediator = create_mediator(args.config, backend_id=args.backend_id, allow_no_backend=args.allow_no_backend)
    payload = execute_command(args, mediator)
    print(render_output(args.command, payload, args.json))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())