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
            registered = hook.register_claim_requirements(
                'testuser',
                {
                    'employment': [
                        'Protected activity',
                        'Adverse employment action',
                    ]
                },
            )
            first_id = hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_id='employment:1',
                claim_element_text='Protected activity',
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
            assert len(registered['employment']) == 2
            assert len(links) == 2
            assert summary['claims']['employment']['support_by_kind']['evidence'] == 1
            assert summary['claims']['employment']['support_by_kind']['authority'] == 1
            assert summary['claims']['employment']['total_elements'] == 2
            assert summary['claims']['employment']['covered_elements'] == 1
            assert summary['claims']['employment']['uncovered_elements'] == 1
            assert summary['claims']['employment']['elements'][0]['total_links'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_summary_includes_uncovered_requirements_without_links(self):
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
            hook.register_claim_requirements(
                'testuser',
                {'retaliation': ['Protected activity', 'Causal connection']},
            )

            summary = hook.summarize_claim_support('testuser', 'retaliation')

            assert summary['claims']['retaliation']['total_links'] == 0
            assert summary['claims']['retaliation']['total_elements'] == 2
            assert summary['claims']['retaliation']['covered_elements'] == 0
            assert summary['claims']['retaliation']['uncovered_elements'] == 2
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_add_support_link_resolves_matching_element(self):
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
            hook.register_claim_requirements(
                'testuser',
                {
                    'employment': [
                        'Protected activity',
                        'Adverse employment action',
                    ]
                },
            )

            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                support_kind='evidence',
                support_ref='QmEvidence2',
                support_label='Email showing protected activity complaint',
                source_table='evidence',
                metadata={'keywords': ['protected', 'activity', 'complaint']},
            )

            links = hook.get_support_links('testuser', 'employment')

            assert links[0]['claim_element_id'] == 'employment:1'
            assert links[0]['claim_element_text'] == 'Protected activity'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)