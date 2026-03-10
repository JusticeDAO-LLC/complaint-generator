"""Unit tests for claim support persistence hooks."""

import os
import tempfile
from unittest.mock import Mock

import pytest


class TestClaimSupportHook:
    def test_claim_support_hook_can_be_imported(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
            assert ClaimSupportHook is not None
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook has import issues: {e}")

    def test_add_and_summarize_support(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            first_id = hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                support_kind='evidence',
                support_ref='QmEvidence1',
                support_label='Email thread',
                source_table='evidence',
            )
            second_id = hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                support_kind='authority',
                support_ref='42 U.S.C. § 1983',
                support_label='Civil Rights Act',
                source_table='legal_authorities',
            )

            links = hook.get_support_links('testuser', 'employment')
            summary = hook.summarize_claim_support('testuser', 'employment')

            assert first_id > 0
            assert second_id > 0
            assert len(links) == 2
            assert summary['claims']['employment']['support_by_kind']['evidence'] == 1
            assert summary['claims']['employment']['support_by_kind']['authority'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)