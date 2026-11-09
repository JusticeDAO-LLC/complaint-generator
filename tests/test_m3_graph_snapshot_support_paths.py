"""Tests for M3: Graph Snapshot Persistence and Support Paths.

Validates:
- resolve_duplicate_entities() in integrations/ipfs_datasets/graphs.py
- attach_provenance_edges() in integrations/ipfs_datasets/graphs.py
- persist_typed_graph_snapshot() in mediator/claim_support_hooks.py
- get_support_paths_for_element() in mediator/claim_support_hooks.py
- get_contradiction_paths_for_element() in mediator/claim_support_hooks.py
- get_graph_snapshot_refs_for_element() in mediator/claim_support_hooks.py
- graph_snapshot_refs and support_path_summary in get_claim_coverage_matrix()
"""
import sys
import os
import json
import types
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.ipfs_datasets.graphs import (
    resolve_duplicate_entities,
    attach_provenance_edges,
    query_graph_snapshot,
)


# ---------------------------------------------------------------------------
# resolve_duplicate_entities
# ---------------------------------------------------------------------------

class TestResolveDuplicateEntities:
    def test_empty_input_returns_empty_map(self):
        result = resolve_duplicate_entities([])
        assert result['entity_count'] == 0
        assert result['input_count'] == 0
        assert result['merged_count'] == 0
        assert result['clusters'] == []
        assert result['entity_map'] == {}

    def test_none_input_returns_empty_map(self):
        result = resolve_duplicate_entities(None)
        assert result['entity_count'] == 0

    def test_single_entity_no_merge(self):
        entities = [{'entity_id': 'e1', 'name': 'John Smith', 'source_kind': 'testimony'}]
        result = resolve_duplicate_entities(entities)
        assert result['entity_count'] == 1
        assert result['input_count'] == 1
        assert result['merged_count'] == 0
        assert len(result['clusters']) == 1
        cluster = result['clusters'][0]
        assert cluster['canonical_name'] == 'John Smith'
        assert cluster['source_kinds'] == ['testimony']

    def test_distinct_entities_no_merge(self):
        entities = [
            {'entity_id': 'e1', 'name': 'Alice Brown', 'source_kind': 'testimony'},
            {'entity_id': 'e2', 'name': 'Bob Green', 'source_kind': 'evidence'},
        ]
        result = resolve_duplicate_entities(entities)
        assert result['entity_count'] == 2
        assert result['merged_count'] == 0

    def test_near_duplicate_names_merged(self):
        # "John Smith" and "john smith" are same person
        entities = [
            {'entity_id': 'e1', 'name': 'John Smith', 'source_kind': 'testimony'},
            {'entity_id': 'e2', 'name': 'john smith', 'source_kind': 'evidence'},
        ]
        result = resolve_duplicate_entities(entities)
        assert result['entity_count'] == 1
        assert result['merged_count'] == 1
        cluster = result['clusters'][0]
        assert 'testimony' in cluster['source_kinds']
        assert 'evidence' in cluster['source_kinds']
        assert len(cluster['entity_ids']) == 2

    def test_cross_source_entity_resolution(self):
        entities = [
            {'entity_id': 'e1', 'name': 'Acme Corp', 'source_kind': 'testimony'},
            {'entity_id': 'e2', 'name': 'acme corp', 'source_kind': 'document'},
            {'entity_id': 'e3', 'name': 'BetaCo', 'source_kind': 'law'},
        ]
        result = resolve_duplicate_entities(entities)
        assert result['entity_count'] == 2
        assert result['merged_count'] == 1

    def test_entity_without_id_gets_stable_identifier(self):
        entities = [{'name': 'Jane Doe', 'source_kind': 'testimony'}]
        result = resolve_duplicate_entities(entities)
        cluster = result['clusters'][0]
        assert cluster['canonical_entity_id'].startswith('entity:')

    def test_resolved_returns_true(self):
        result = resolve_duplicate_entities([{'entity_id': 'x', 'name': 'foo'}])
        assert result['resolved'] is True


# ---------------------------------------------------------------------------
# attach_provenance_edges
# ---------------------------------------------------------------------------

class TestAttachProvenanceEdges:
    def test_empty_inputs_returns_no_edges(self):
        result = attach_provenance_edges([], [], [])
        assert result['attached'] is True
        assert result['edge_count'] == 0
        assert result['edges'] == []

    def test_none_inputs_returns_no_edges(self):
        result = attach_provenance_edges(None, None, None)
        assert result['edge_count'] == 0

    def test_fact_with_matching_chunk_creates_edge(self):
        facts = [{'fact_id': 'f1', 'chunk_ref': 'c1'}]
        chunks = [{'chunk_ref': 'c1', 'artifact_id': 'a1'}]
        artifacts = [{'artifact_id': 'a1'}]
        result = attach_provenance_edges(facts, chunks, artifacts)
        assert result['fact_to_chunk_count'] == 1
        assert result['chunk_to_artifact_count'] == 1
        assert result['edge_count'] == 2
        kinds = {e['edge_kind'] for e in result['edges']}
        assert 'fact_to_chunk' in kinds
        assert 'chunk_to_artifact' in kinds

    def test_fact_without_chunk_ref_is_unresolved(self):
        facts = [{'fact_id': 'f1', 'chunk_ref': ''}]
        result = attach_provenance_edges(facts, [], [])
        assert result['unresolved_fact_count'] == 1
        assert result['fact_to_chunk_count'] == 0

    def test_fact_with_nonexistent_chunk_is_unresolved(self):
        facts = [{'fact_id': 'f1', 'chunk_ref': 'missing_chunk'}]
        result = attach_provenance_edges(facts, [], [])
        assert result['unresolved_fact_count'] == 1

    def test_chunk_without_artifact_does_not_create_chunk_artifact_edge(self):
        facts = [{'fact_id': 'f1', 'chunk_ref': 'c1'}]
        chunks = [{'chunk_ref': 'c1', 'artifact_id': 'nonexistent'}]
        artifacts = []
        result = attach_provenance_edges(facts, chunks, artifacts)
        assert result['fact_to_chunk_count'] == 1
        assert result['chunk_to_artifact_count'] == 0
        assert result['unresolved_chunk_count'] == 1

    def test_multiple_facts_same_chunk_no_duplicate_chunk_artifact_edge(self):
        facts = [
            {'fact_id': 'f1', 'chunk_ref': 'c1'},
            {'fact_id': 'f2', 'chunk_ref': 'c1'},
        ]
        chunks = [{'chunk_ref': 'c1', 'artifact_id': 'a1'}]
        artifacts = [{'artifact_id': 'a1'}]
        result = attach_provenance_edges(facts, chunks, artifacts)
        assert result['fact_to_chunk_count'] == 2
        assert result['chunk_to_artifact_count'] == 1
        chunk_artifact_edges = [e for e in result['edges'] if e['edge_kind'] == 'chunk_to_artifact']
        assert len(chunk_artifact_edges) == 1

    def test_edge_ids_are_stable(self):
        facts = [{'fact_id': 'f1', 'chunk_ref': 'c1'}]
        chunks = [{'chunk_ref': 'c1', 'artifact_id': 'a1'}]
        artifacts = [{'artifact_id': 'a1'}]
        r1 = attach_provenance_edges(facts, chunks, artifacts)
        r2 = attach_provenance_edges(facts, chunks, artifacts)
        ids1 = {e['edge_id'] for e in r1['edges']}
        ids2 = {e['edge_id'] for e in r2['edges']}
        assert ids1 == ids2


# ---------------------------------------------------------------------------
# Claim support hooks - M3 methods (DuckDB-backed)
# ---------------------------------------------------------------------------

def _make_fake_mediator():
    m = types.SimpleNamespace()
    m.log = lambda *a, **kw: None
    m.state = types.SimpleNamespace(username='test_user', hashed_username='test_user')
    return m


def _make_hooks(db_path):
    from mediator.claim_support_hooks import ClaimSupportHook
    mediator = _make_fake_mediator()
    hooks = ClaimSupportHook(mediator, db_path=db_path)
    return hooks


@pytest.fixture
def hooks_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test_m3.duckdb')
        hooks = _make_hooks(db_path)
        yield hooks


class TestPersistTypedGraphSnapshot:
    def test_persist_testimony_snapshot(self, hooks_db):
        graph_payload = {
            'source_id': 'src1',
            'entities': [{'id': 'e1', 'name': 'Alice'}],
            'relationships': [],
        }
        result = hooks_db.persist_typed_graph_snapshot(
            'user1', 'employment_discrimination', 'testimony', graph_payload
        )
        assert result['available'] is True
        assert result['recorded'] is True
        assert result['source_kind'] == 'testimony'
        assert result['snapshot_kind'] == 'graph:testimony'
        assert result['entity_count'] == 1
        assert result['graph_id'].startswith('graph:')

    def test_persist_evidence_snapshot(self, hooks_db):
        graph_payload = {
            'source_id': 'ev1',
            'entities': [{'id': 'e1', 'name': 'HR Dept'}, {'id': 'e2', 'name': 'Employee'}],
            'relationships': [{'from': 'e1', 'to': 'e2', 'type': 'employs'}],
            'support_facts': [
                {
                    'fact_id': 'fact-1',
                    'text': 'Employee reported discrimination to HR.',
                    'support_kind': 'evidence',
                    'source_table': 'evidence_facts',
                    'source_family': 'evidence',
                    'source_record_id': 11,
                    'source_ref': 'bafy-hr',
                    'record_scope': 'claim',
                    'artifact_family': 'archived_web_page',
                    'corpus_family': 'web_archive',
                    'content_origin': 'historical_archive_capture',
                    'parse_source': 'ipfs_datasets_py',
                    'input_format': 'html',
                    'quality_tier': 'high',
                    'chunk_id': 'chunk-hr',
                    'source_passage': {'chunk_id': 'chunk-hr', 'text': 'reported discrimination'},
                }
            ],
        }
        result = hooks_db.persist_typed_graph_snapshot(
            'user1', 'employment_discrimination', 'evidence', graph_payload
        )
        assert result['available'] is True
        assert result['source_kind'] == 'evidence'
        assert result['entity_count'] == 2
        assert result['relationship_count'] == 1
        assert result['fact_registry_summary']['source_family_counts'] == {'evidence': 1}
        assert result['fact_registry_summary']['corpus_family_counts'] == {'web_archive': 1}
        assert result['fact_registry_summary']['passage_anchored_count'] == 1
        assert result['graph_snapshot']['status'] == 'stored-fallback'
        assert result['graph_snapshot']['persisted'] is True
        snapshot_lookup = query_graph_snapshot(result['graph_id'])
        assert snapshot_lookup['found'] is True
        assert snapshot_lookup['fact_registry_summary']['snapshot_count'] == 1
        assert snapshot_lookup['fact_registry_summary']['source_family_counts'] == {'evidence': 1}
        assert snapshot_lookup['fact_registry_summary']['passage_anchored_count'] == 1
        assert snapshot_lookup['snapshots'][0]['graph_id'] == result['graph_id']
        assert snapshot_lookup['snapshots'][0]['source_id'] == 'ev1'
        assert snapshot_lookup['snapshots'][0]['metadata']['claim_type'] == 'employment_discrimination'
        assert snapshot_lookup['snapshots'][0]['fact_registry_summary']['source_family_counts'] == {'evidence': 1}
        assert snapshot_lookup['snapshots'][0]['metadata']['fact_registry_summary']['passage_anchored_count'] == 1

    def test_persist_law_snapshot(self, hooks_db):
        graph_payload = {'source_id': 'law1', 'entities': [], 'relationships': []}
        result = hooks_db.persist_typed_graph_snapshot(
            'user1', 'employment_discrimination', 'law', graph_payload
        )
        assert result['snapshot_kind'] == 'graph:law'
        assert result['entity_count'] == 0

    def test_stable_graph_id_is_deterministic(self, hooks_db):
        graph_payload = {
            'source_id': 'same_source',
            'entities': [{'id': 'e1'}],
            'relationships': [],
        }
        r1 = hooks_db.persist_typed_graph_snapshot(
            'user1', 'claim_type', 'testimony', graph_payload, graph_id='explicit-id'
        )
        r2 = hooks_db.persist_typed_graph_snapshot(
            'user1', 'claim_type', 'testimony', graph_payload, graph_id='explicit-id'
        )
        assert r1['graph_id'] == r2['graph_id'] == 'explicit-id'


class TestGetSupportPathsForElement:
    def test_empty_db_returns_empty_paths(self, hooks_db):
        result = hooks_db.get_support_paths_for_element('user1', 'employment_discrimination')
        assert result['available'] is True
        assert result['paths'] == []
        assert result['path_count'] == 0

    def test_persisted_path_is_queryable(self, hooks_db):
        # First persist a path
        support_traces = [{'fact_id': 'fact:abc', 'text': 'relevant text'}]
        hooks_db.persist_support_path(
            'user1', 'employment_discrimination', 'elem:hostile_work_env',
            support_traces
        )
        result = hooks_db.get_support_paths_for_element(
            'user1', 'employment_discrimination',
            claim_element_id='elem:hostile_work_env'
        )
        assert result['available'] is True
        assert result['path_count'] >= 1
        path = result['paths'][0]
        assert 'proof_path_id' in path
        assert 'fact_ids' in path
        assert 'fact:abc' in path['fact_ids']

    def test_path_kind_filter(self, hooks_db):
        support_traces = [{'fact_id': 'fact:s1'}]
        contradiction_traces = [{'fact_id': 'fact:c1'}]
        hooks_db.persist_support_path(
            'user1', 'retaliation', 'elem:adverse_action',
            support_traces, path_kind='support'
        )
        hooks_db.persist_support_path(
            'user1', 'retaliation', 'elem:adverse_action',
            contradiction_traces, path_kind='contradiction'
        )
        support_only = hooks_db.get_support_paths_for_element(
            'user1', 'retaliation', claim_element_id='elem:adverse_action', path_kind='support'
        )
        contradiction_only = hooks_db.get_support_paths_for_element(
            'user1', 'retaliation', claim_element_id='elem:adverse_action', path_kind='contradiction'
        )
        assert all(p['path_kind'] == 'support' for p in support_only['paths'])
        assert all(p['path_kind'] == 'contradiction' for p in contradiction_only['paths'])

    def test_path_count_field_matches_paths_list(self, hooks_db):
        hooks_db.persist_support_path(
            'user1', 'housing_discrimination', 'elem:protected_class',
            [{'fact_id': 'f1'}]
        )
        result = hooks_db.get_support_paths_for_element(
            'user1', 'housing_discrimination',
            claim_element_id='elem:protected_class'
        )
        assert result['path_count'] == len(result['paths'])


class TestGetContradictionPathsForElement:
    def test_delegates_to_support_paths_with_contradiction_kind(self, hooks_db):
        hooks_db.persist_support_path(
            'user1', 'retaliation', 'elem:temporal_connection',
            [{'fact_id': 'f_contra'}], path_kind='contradiction'
        )
        result = hooks_db.get_contradiction_paths_for_element(
            'user1', 'retaliation', claim_element_id='elem:temporal_connection'
        )
        assert result['path_kind'] == 'contradiction'
        assert all(p['path_kind'] == 'contradiction' for p in result['paths'])


class TestGetGraphSnapshotRefsForElement:
    def test_empty_db_returns_empty_list(self, hooks_db):
        refs = hooks_db.get_graph_snapshot_refs_for_element('user1', 'claim_type')
        assert refs == []

    def test_only_graph_snapshots_returned(self, hooks_db):
        # Persist a non-graph snapshot (gaps kind)
        import duckdb
        conn = duckdb.connect(hooks_db.db_path)
        conn.execute(
            "INSERT INTO claim_support_snapshot (user_id, claim_type, snapshot_kind, required_support_kinds, payload, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            ['user1', 'claim_type', 'gaps', '[]', '{"gap": true}', '{}']
        )
        conn.close()
        # Also persist a graph snapshot
        hooks_db.persist_typed_graph_snapshot(
            'user1', 'claim_type', 'testimony',
            {'source_id': 's1', 'entities': [{'id': 'e1'}], 'relationships': []}
        )
        refs = hooks_db.get_graph_snapshot_refs_for_element('user1', 'claim_type')
        assert all(ref['snapshot_kind'].startswith('graph:') for ref in refs)
        assert len(refs) >= 1

    def test_snapshot_ref_fields_present(self, hooks_db):
        hooks_db.persist_typed_graph_snapshot(
            'user1', 'employment_discrimination', 'evidence',
            {'source_id': 'ev1', 'entities': [{'id': 'e1'}, {'id': 'e2'}], 'relationships': []}
        )
        refs = hooks_db.get_graph_snapshot_refs_for_element(
            'user1', 'employment_discrimination'
        )
        assert len(refs) >= 1
        ref = refs[0]
        assert 'snapshot_id' in ref
        assert 'snapshot_kind' in ref
        assert 'source_kind' in ref
        assert 'graph_id' in ref
        assert 'entity_count' in ref
        assert 'relationship_count' in ref
        assert 'timestamp' in ref
        assert ref['source_kind'] == 'evidence'
        assert ref['entity_count'] == 2

    def test_snapshot_ref_preserves_fact_registry_summary(self, hooks_db):
        hooks_db.persist_typed_graph_snapshot(
            'user1',
            'retaliation',
            'evidence',
            {
                'source_id': 'ev-registry',
                'entities': [{'id': 'e1'}],
                'relationships': [],
                'fact_registry_summary': {
                    'fact_count': 2,
                    'source_family_counts': {'evidence': 2},
                    'artifact_family_counts': {'archived_web_page': 2},
                    'corpus_family_counts': {'web_archive': 2},
                    'passage_anchored_count': 1,
                },
            },
        )

        refs = hooks_db.get_graph_snapshot_refs_for_element('user1', 'retaliation')

        assert refs[0]['fact_registry_summary'] == {
            'fact_count': 2,
            'source_family_counts': {'evidence': 2},
            'artifact_family_counts': {'archived_web_page': 2},
            'corpus_family_counts': {'web_archive': 2},
            'passage_anchored_count': 1,
        }
        assert refs[0]['graph_snapshot_query']['found'] is True
        assert refs[0]['graph_snapshot_query']['snapshot_count'] == 1
        assert refs[0]['graph_snapshot_query']['fact_registry_summary']['fact_count'] == 2
        assert refs[0]['graph_snapshot_query']['fact_registry_summary']['source_family_counts'] == {'evidence': 2}
        assert refs[0]['graph_snapshot']['graph_id'] == refs[0]['graph_id']
        assert refs[0]['graph_snapshot']['source_id'] == 'ev-registry'
        assert refs[0]['graph_snapshot']['fact_registry_summary']['passage_anchored_count'] == 1


class TestCoverageMatrixM3Fields:
    def test_coverage_matrix_includes_graph_snapshot_refs_and_support_path_summary(self, hooks_db):
        # Register claim requirements so there's at least one element
        hooks_db.register_claim_requirements(
            'user1',
            {'employment_discrimination': ['adverse_employment_action', 'protected_class']},
        )
        matrix = hooks_db.get_claim_coverage_matrix('user1', 'employment_discrimination')
        assert matrix['available'] is True
        for claim_data in matrix.get('claims', {}).values():
            for element in claim_data.get('elements', []):
                assert 'graph_snapshot_refs' in element
                assert 'support_path_summary' in element
                assert isinstance(element['graph_snapshot_refs'], list)
                assert isinstance(element['support_path_summary'], dict)
