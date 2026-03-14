import importlib.util
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import duckdb


def _load_cli_module():
    module_path = Path(__file__).resolve().parents[1] / 'scripts' / 'backfill_claim_testimony_links.py'
    spec = importlib.util.spec_from_file_location('backfill_claim_testimony_links', module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_parser_parses_backfill_filters():
    cli = _load_cli_module()
    parser = cli.create_parser()

    args = parser.parse_args([
        '--db-path', 'statefiles/claim_support.duckdb',
        '--user-id', 'testuser',
        '--claim-type', 'retaliation',
        '--limit', '25',
        '--dry-run',
    ])

    assert args.db_path == 'statefiles/claim_support.duckdb'
    assert args.user_id == 'testuser'
    assert args.claim_type == 'retaliation'
    assert args.limit == 25
    assert args.dry_run is True


def test_execute_command_backfills_legacy_rows():
    cli = _load_cli_module()

    with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as handle:
        db_path = handle.name

    try:
        hook = cli.create_hook(db_path)
        hook.register_claim_requirements(
            'testuser',
            {'retaliation': ['Protected activity', 'Adverse action']},
        )

        conn = duckdb.connect(db_path)
        conn.execute(
            """
            INSERT INTO claim_testimony (
                testimony_id,
                user_id,
                claim_type,
                claim_element_id,
                claim_element_text,
                raw_narrative,
                firsthand_status,
                source_confidence,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                'testimony:retaliation:cli-legacy',
                'testuser',
                'retaliation',
                None,
                'Protected activity',
                'The HR complaint email does not exist.',
                'firsthand',
                0.91,
                json.dumps({'source': 'cli-test'}),
            ],
        )
        conn.close()

        payload = cli.execute_command(
            SimpleNamespace(user_id='testuser', claim_type='retaliation', limit=0, dry_run=False),
            hook,
        )

        assert payload['updated_count'] == 1
        assert payload['records'][0]['claim_element_id'] == 'retaliation:1'

        conn = duckdb.connect(db_path)
        persisted = conn.execute(
            'SELECT claim_element_id, claim_element_text FROM claim_testimony WHERE testimony_id = ?',
            ['testimony:retaliation:cli-legacy'],
        ).fetchone()
        conn.close()

        assert persisted == ('retaliation:1', 'Protected activity')
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_render_output_formats_backfill_summary():
    cli = _load_cli_module()

    output = cli.render_output(
        {
            'available': True,
            'dry_run': False,
            'scanned_count': 2,
            'candidate_count': 1,
            'updated_count': 1,
            'records': [
                {
                    'record_id': 7,
                    'user_id': 'testuser',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'retaliation:1',
                    'testimony_id': 'testimony:retaliation:cli-legacy',
                }
            ],
        },
        as_json=False,
    )

    assert 'updated_count: 1' in output
    assert 'claim_element_id=retaliation:1' in output
    assert 'testimony:retaliation:cli-legacy' in output