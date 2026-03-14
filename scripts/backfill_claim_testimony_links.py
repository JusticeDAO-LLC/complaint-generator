#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _HookMediator:
    def log(self, *_args, **_kwargs) -> None:
        return None


def create_hook(db_path: Optional[str] = None):
    from mediator.claim_support_hooks import ClaimSupportHook

    return ClaimSupportHook(_HookMediator(), db_path=db_path)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Backfill canonical claim element links for legacy claim testimony rows.'
    )
    parser.add_argument('--db-path', default=None, help='Path to claim_support DuckDB file')
    parser.add_argument('--user-id', default=None, help='Restrict to one user id')
    parser.add_argument('--claim-type', default=None, help='Restrict to one claim type')
    parser.add_argument('--limit', type=int, default=0, help='Max legacy rows to scan, 0 means no limit')
    parser.add_argument('--dry-run', action='store_true', help='Report candidate repairs without updating rows')
    parser.add_argument('--json', action='store_true', help='Emit raw JSON output')
    return parser


def execute_command(args: argparse.Namespace, hook) -> Dict[str, Any]:
    return hook.backfill_claim_testimony_links(
        user_id=args.user_id,
        claim_type=args.claim_type,
        limit=args.limit,
        dry_run=args.dry_run,
    )


def render_output(payload: Dict[str, Any], as_json: bool) -> str:
    if as_json:
        return json.dumps(payload, indent=2, default=str)

    lines = [
        f"available: {bool(payload.get('available', False))}",
        f"dry_run: {bool(payload.get('dry_run', False))}",
        f"scanned_count: {int(payload.get('scanned_count', 0) or 0)}",
        f"candidate_count: {int(payload.get('candidate_count', 0) or 0)}",
        f"updated_count: {int(payload.get('updated_count', 0) or 0)}",
    ]
    error = str(payload.get('error') or '').strip()
    if error:
        lines.append(f'error: {error}')

    records = payload.get('records', []) if isinstance(payload.get('records'), list) else []
    if not records:
        lines.append('No legacy testimony rows required backfill.')
        return '\n'.join(lines)

    lines.append('records:')
    for record in records:
        lines.append(
            '- '
            f"record_id={record.get('record_id')} "
            f"user_id={record.get('user_id')} "
            f"claim_type={record.get('claim_type')} "
            f"claim_element_id={record.get('claim_element_id')} "
            f"testimony_id={record.get('testimony_id')}"
        )
    return '\n'.join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    hook = create_hook(args.db_path)
    payload = execute_command(args, hook)
    print(render_output(payload, args.json))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())