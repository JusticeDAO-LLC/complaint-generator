"""Focused regression coverage for REF-214's DuckDB path preparation."""

from unittest.mock import Mock, patch

import pytest

from mediator.claim_support_hooks import ClaimSupportHook


pytestmark = pytest.mark.no_auto_network


def _uninitialized_hook(db_path: object) -> ClaimSupportHook:
    """Build a hook without opening DuckDB so path behavior is isolated."""
    hook = ClaimSupportHook.__new__(ClaimSupportHook)
    hook.db_path = db_path
    hook.mediator = Mock()
    return hook


def test_prepare_duckdb_path_logs_filesystem_failure() -> None:
    hook = _uninitialized_hook('/read-only/claim-support/claims.duckdb')
    failure = PermissionError(13, 'permission denied')

    with patch('mediator.claim_support_hooks.Path.exists', side_effect=failure):
        hook._prepare_duckdb_path()

    hook.mediator.log.assert_called_once_with(
        'claim_support_db_path_prepare_error',
        db_path='/read-only/claim-support/claims.duckdb',
        error='[Errno 13] permission denied',
        error_type='PermissionError',
    )


def test_prepare_duckdb_path_does_not_hide_invalid_configuration() -> None:
    hook = _uninitialized_hook(object())

    with pytest.raises(TypeError):
        hook._prepare_duckdb_path()

    hook.mediator.log.assert_not_called()
