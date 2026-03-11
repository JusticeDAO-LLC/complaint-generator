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

    def test_add_support_link_deduplicates_same_reference(self):
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
                {'employment': ['Protected activity']},
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
                claim_element_id='employment:1',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidence1',
                support_label='Email thread',
                source_table='evidence',
            )

            links = hook.get_support_links('testuser', 'employment')
            summary = hook.summarize_claim_support('testuser', 'employment')

            assert first_id == second_id
            assert len(links) == 1
            assert summary['claims']['employment']['total_links'] == 1
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

    def test_get_claim_element_summary(self):
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
                {'employment': ['Protected activity', 'Adverse employment action']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                support_kind='evidence',
                support_ref='QmEvidence3',
                support_label='Protected activity email',
                metadata={'keywords': ['protected', 'activity']},
            )

            summary = hook.get_claim_element_summary(
                'testuser',
                'employment',
                claim_element_text='Protected activity',
            )

            assert summary['element_id'] == 'employment:1'
            assert summary['total_links'] == 1
            assert summary['support_by_kind']['evidence'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_summarize_claim_support_enriches_evidence_links_with_facts(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 12,
            'fact_count': 2,
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:1', 'text': 'Employee complained about discrimination.'},
            {'fact_id': 'fact:2', 'text': 'Complaint was sent to HR.'},
        ])

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceFacts',
                support_label='HR complaint email',
                source_table='evidence',
            )

            summary = hook.summarize_claim_support('testuser', 'employment')
            element = summary['claims']['employment']['elements'][0]

            assert summary['claims']['employment']['total_facts'] == 2
            assert element['fact_count'] == 2
            assert element['links'][0]['evidence_record_id'] == 12
            assert element['links'][0]['fact_count'] == 2
            assert len(element['links'][0]['facts']) == 2
            assert element['links'][0]['facts'][0]['fact_id'] == 'fact:1'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_facts_collects_enriched_fact_rows(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 12,
            'fact_count': 2,
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:1', 'text': 'Employee complained about discrimination.'},
            {'fact_id': 'fact:2', 'text': 'Complaint was sent to HR.'},
        ])

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceFacts',
                support_label='HR complaint email',
                source_table='evidence',
            )

            facts = hook.get_claim_support_facts(
                'testuser',
                'employment',
                claim_element_text='Protected activity',
            )

            assert len(facts) == 2
            assert facts[0]['claim_type'] == 'employment'
            assert facts[0]['claim_element_text'] == 'Protected activity'
            assert facts[0]['support_kind'] == 'evidence'
            assert facts[0]['evidence_record_id'] == 12
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_overview_classifies_elements(self):
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
                        'Causal connection',
                    ]
                },
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidence4',
                support_label='Protected activity email',
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='42 U.S.C. § 1983',
                support_label='Protected activity authority',
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Adverse employment action',
                support_kind='evidence',
                support_ref='QmEvidence5',
                support_label='Termination notice',
            )

            overview = hook.get_claim_overview('testuser', 'employment')
            claim_overview = overview['claims']['employment']

            assert claim_overview['covered_count'] == 1
            assert claim_overview['partially_supported_count'] == 1
            assert claim_overview['missing_count'] == 1
            assert claim_overview['covered'][0]['element_text'] == 'Protected activity'
            assert claim_overview['partially_supported'][0]['element_text'] == 'Adverse employment action'
            assert claim_overview['missing'][0]['element_text'] == 'Causal connection'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_coverage_matrix_groups_links_by_support_kind(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 18,
            'cid': 'QmEvidence6',
            'type': 'document',
            'source_url': 'https://example.com/evidence',
            'parse_status': 'parsed',
            'chunk_count': 2,
            'graph_status': 'ready',
            'graph_entity_count': 3,
            'graph_relationship_count': 2,
            'fact_count': 2,
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:1', 'text': 'Employee complained to HR.'},
            {'fact_id': 'fact:2', 'text': 'Complaint referenced discrimination.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}, {'id': 'entity:2'}, {'id': 'entity:3'}],
            'relationships': [{'id': 'rel:1'}, {'id': 'rel:2'}],
        })
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value={
            'id': 7,
            'citation': '42 U.S.C. § 1983',
            'title': 'Civil Rights Act',
            'url': 'https://example.com/usc/1983',
            'parse_status': 'parsed',
            'chunk_count': 1,
            'graph_status': 'ready',
            'graph_entity_count': 1,
            'graph_relationship_count': 1,
            'fact_count': 1,
        })
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[
            {'fact_id': 'auth:1', 'text': 'Section 1983 authorizes relief.'},
        ])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:a'}],
            'relationships': [{'id': 'rel:a'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity', 'Adverse employment action']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidence6',
                support_label='HR complaint email',
                source_table='evidence',
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='42 U.S.C. § 1983',
                support_label='Civil Rights Act',
                source_table='legal_authorities',
            )

            matrix = hook.get_claim_coverage_matrix('testuser', 'employment')
            claim_matrix = matrix['claims']['employment']
            protected_activity = claim_matrix['elements'][0]

            assert claim_matrix['status_counts']['covered'] == 1
            assert claim_matrix['status_counts']['missing'] == 1
            assert claim_matrix['total_links'] == 2
            assert claim_matrix['total_facts'] == 3
            assert protected_activity['status'] == 'covered'
            assert protected_activity['missing_support_kinds'] == []
            assert len(protected_activity['links_by_kind']['evidence']) == 1
            assert len(protected_activity['links_by_kind']['authority']) == 1
            assert protected_activity['links_by_kind']['evidence'][0]['record_summary']['cid'] == 'QmEvidence6'
            assert protected_activity['links_by_kind']['authority'][0]['record_summary']['citation'] == '42 U.S.C. § 1983'
            assert protected_activity['links_by_kind']['evidence'][0]['graph_summary']['entity_count'] == 3
            assert protected_activity['links_by_kind']['authority'][0]['graph_summary']['relationship_count'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)