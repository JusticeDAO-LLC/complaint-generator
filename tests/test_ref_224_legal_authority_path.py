"""Focused regression coverage for REF-224's DuckDB path preparation."""

from unittest.mock import Mock, patch

import pytest

from mediator.legal_authority_hooks import LegalAuthorityStorageHook


pytestmark = pytest.mark.no_auto_network


def _uninitialized_hook(db_path: object) -> LegalAuthorityStorageHook:
    """Build a hook without opening DuckDB so path behavior is isolated."""
    hook = LegalAuthorityStorageHook.__new__(LegalAuthorityStorageHook)
    hook.db_path = db_path
    hook.mediator = Mock()
    return hook


def test_prepare_duckdb_path_logs_filesystem_failure() -> None:
    hook = _uninitialized_hook('/read-only/legal-authority/authorities.duckdb')
    failure = PermissionError(13, 'permission denied')

    with patch('mediator.legal_authority_hooks.Path.exists', side_effect=failure):
        hook._prepare_duckdb_path()

    hook.mediator.log.assert_called_once_with(
        'legal_authority_db_path_prepare_error',
        db_path='/read-only/legal-authority/authorities.duckdb',
        error='[Errno 13] permission denied',
        error_type='PermissionError',
    )


def test_prepare_duckdb_path_does_not_hide_invalid_configuration() -> None:
    hook = _uninitialized_hook(object())

    with pytest.raises(TypeError):
        hook._prepare_duckdb_path()

    hook.mediator.log.assert_not_called()
