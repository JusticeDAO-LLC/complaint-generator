"""Focused regression coverage for REF-225's authority lookup boundary."""

from unittest.mock import Mock, patch

import pytest

from mediator.legal_authority_hooks import LegalAuthorityStorageHook


pytestmark = pytest.mark.no_auto_network


def _uninitialized_hook() -> LegalAuthorityStorageHook:
    """Build a hook without schema initialization so lookup behavior is isolated."""
    hook = LegalAuthorityStorageHook.__new__(LegalAuthorityStorageHook)
    hook.db_path = '/tmp/ref-225-legal-authorities.duckdb'
    hook.mediator = Mock()
    return hook


def test_get_authority_by_id_propagates_query_failure_and_closes_connection() -> None:
    hook = _uninitialized_hook()
    connection = Mock()
    failure = RuntimeError('authority query failed')
    connection.execute.side_effect = failure

    with (
        patch('mediator.legal_authority_hooks.DUCKDB_AVAILABLE', True),
        patch('mediator.legal_authority_hooks.duckdb.connect', return_value=connection),
        pytest.raises(RuntimeError, match='authority query failed') as raised,
    ):
        hook.get_authority_by_id(42)

    assert raised.value is failure
    connection.close.assert_called_once_with()
    hook.mediator.log.assert_called_once_with(
        'legal_authority_query_error',
        error='authority query failed',
        error_type='RuntimeError',
        authority_id=42,
    )


def test_get_authority_by_id_preserves_not_found_sentinel_and_closes_connection() -> None:
    hook = _uninitialized_hook()
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = None

    with (
        patch('mediator.legal_authority_hooks.DUCKDB_AVAILABLE', True),
        patch('mediator.legal_authority_hooks.duckdb.connect', return_value=connection),
    ):
        result = hook.get_authority_by_id(404)

    assert result is None
    connection.close.assert_called_once_with()
    hook.mediator.log.assert_not_called()
