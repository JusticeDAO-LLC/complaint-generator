"""Synthetic wire2 graph/proof storage; no nodes, providers, or user cases."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.ipfs_datasets.graphs import persist_graph_snapshot
from integrations.ipfs_datasets.draft_logic_pipeline import pin_proof_report_to_ipfs
from integrations.private_storage import (
    InjectedCaseKeyProvider, PrivateArtifactBinding, PrivateKeyLockedError,
    open_private_artifact, seal_private_artifact,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
KEY = bytes(range(32))
KEY_ID = 'synthetic-graph-proof-key'
MARKER = 'SYNTHETIC-PRIVATE-GRAPH-PROOF-MARKER'


class BytesBackend:
    measurement_label = 'measured-hermetic'

    def __init__(self, *, graph_readback='normal', fail_theorem=False):
        self.blobs = {}
        self.reads = {}
        self.seen = []
        self.graph_readback = graph_readback
        self.fail_theorem = fail_theorem

    def add_bytes(self, data, pin=True):
        del pin
        if self.fail_theorem and self.seen:
            raise RuntimeError('synthetic theorem write refusal')
        blob = bytes(data)
        self.seen.append(blob)
        cid = 'bafyhermetic' + hashlib.sha256(blob).hexdigest()
        self.blobs[cid] = blob
        return {'success': True, 'cid': cid, 'pinned': True}

    def cat(self, cid):
        count = self.reads[cid] = self.reads.get(cid, 0) + 1
        # Store adapter readback and private envelope readback must both pass;
        # only the graph destination export's later raw read changes.
        if count == 3:
            if self.graph_readback == 'plaintext':
                return MARKER.encode()
            if self.graph_readback == 'failure':
                return {'success': False, 'error': 'synthetic read failure', 'data': self.blobs[cid]}
            if self.graph_readback == 'empty':
                return b''
            if self.graph_readback == 'foreign-envelope':
                return seal_private_artifact(b'foreign', binding=_binding('fact-graph', 'fact-graph-1', case='other-case'), key=KEY, key_id=KEY_ID)
        return self.blobs[cid]

    def pin(self, cid):
        return {'success': True, 'cid': cid, 'pinned': True}


def _binding(kind, revision, *, case='synthetic-case'):
    return PrivateArtifactBinding(tenant_id='synthetic-owner', case_id=case,
        principal_id='synthetic-owner', artifact_kind=kind, revision=revision)


def _context(backend, *, provider=False):
    context = {
        'access': SimpleNamespace(trust='authenticated', principal_id='synthetic-owner', case_id='synthetic-case'),
        'tenant_id': 'synthetic-owner', 'case_id': 'synthetic-case', 'principal_id': 'synthetic-owner',
        'revision': 'fact-graph-1', 'backend': backend,
    }
    if provider:
        context['key_provider'] = InjectedCaseKeyProvider({('synthetic-owner', 'synthetic-case'): (KEY_ID, KEY)})
    else:
        context.update(key=KEY, key_id=KEY_ID)
    return context


@pytest.mark.parametrize('changed_read', ['plaintext', 'failure', 'empty', 'foreign-envelope'])
def test_graph_destination_rejects_unverified_later_ciphertext(tmp_path: Path, changed_read):
    backend = BytesBackend(graph_readback=changed_read)
    context = _context(backend)
    destination = tmp_path / 'encrypted-graphs'
    context['destination_dir'] = destination
    result = persist_graph_snapshot({'entities': [{'text': MARKER}], 'relationships': []}, private_context=context)
    assert len(backend.seen) == 1
    assert max(backend.reads.values()) == 3
    assert result['status'] == 'recoverable'
    assert result['persisted'] is False
    assert result.get('verified') is not True
    assert not destination.exists() or list(destination.iterdir()) == []
    assert all(MARKER.encode() not in blob for blob in backend.seen)


@pytest.mark.parametrize('provider', [False, True])
def test_graph_destination_contains_authenticated_full_private_graph(tmp_path: Path, provider):
    backend = BytesBackend()
    context = _context(backend, provider=provider)
    context['destination_dir'] = tmp_path / 'encrypted-graphs'
    graph = {'entities': [{'text': MARKER, 'source_text': MARKER}], 'relationships': []}
    result = persist_graph_snapshot(graph, private_context=context)
    assert result['status'] == 'stored-private' and result['persisted'] is True and result['verified'] is True
    artifacts = list(context['destination_dir'].glob('*.bin'))
    assert len(artifacts) == 1
    blob = artifacts[0].read_bytes()
    assert blob == backend.blobs[result['cid']] and MARKER.encode() not in blob
    assert json.loads(open_private_artifact(blob, binding=_binding('fact-graph', 'fact-graph-1'), key=KEY, expected_key_id=KEY_ID)) == graph
    assert result['private_indexing'] == 'unsupported' and result['plaintext_catalog'] is False


@pytest.mark.parametrize('provider', [False, True])
def test_foreign_graph_access_never_stores_or_creates_destination(tmp_path: Path, provider):
    backend = BytesBackend()
    context = _context(backend, provider=provider)
    context['access'] = SimpleNamespace(trust='authenticated', principal_id='foreign-owner', case_id='synthetic-case')
    context['destination_dir'] = tmp_path / 'must-not-exist'
    result = persist_graph_snapshot({'text': MARKER}, private_context=context)
    assert result['persisted'] is False and result['status'] in {'recoverable', 'unlock_needed'}
    assert backend.seen == [] and not context['destination_dir'].exists()


@pytest.mark.parametrize('dialects', [{'lean4': 'lean-private'}, {'coq': 'coq-private'}, {'lean4': 'lean-private', 'coq': 'coq-private'}, {}])
def test_private_theorem_receipt_cids_resolve_with_theorem_binding(dialects):
    backend = BytesBackend()
    context = _context(backend)
    context['revision'] = 'proof-1'
    report = {'source_text': MARKER, 'errors': [MARKER], 'theorem_export': dialects}
    result = pin_proof_report_to_ipfs(report, private_context=context, claim_id='synthetic-claim')
    assert result['status'] == 'available' and result['verified'] is True
    report_cid = result['artifacts']['proof-history']['cid']
    assert result['report_cid'] == report_cid
    assert json.loads(open_private_artifact(backend.blobs[report_cid], binding=_binding('proof-history', 'proof-1:proof-history'), key=KEY, expected_key_id=KEY_ID)) == report
    for dialect, field in [('lean4', 'lean4_cid'), ('coq', 'coq_cid')]:
        if dialect in dialects:
            cid = result[field]
            assert cid == result['artifacts']['theorem-source']['cid']
            assert cid != report_cid
            theorem = json.loads(open_private_artifact(backend.blobs[cid], binding=_binding('theorem-source', 'proof-1:theorem-source'), key=KEY, expected_key_id=KEY_ID))
            assert theorem[dialect] == dialects[dialect]
        else:
            assert result[field] == ''
    assert all(MARKER.encode() not in blob for blob in backend.seen)


def test_private_proof_accepts_live_case_provider_without_raw_key():
    backend = BytesBackend()
    context = _context(backend, provider=True)
    context['revision'] = 'proof-1'
    result = pin_proof_report_to_ipfs({'source_text': MARKER, 'theorem_export': {'lean4': MARKER}}, private_context=context)
    assert result['status'] == 'available' and result['verified'] is True
    assert len(backend.seen) == 2 and all(MARKER.encode() not in blob for blob in backend.seen)


def test_private_proof_key_lookup_failure_has_no_public_fallback():
    backend = BytesBackend()
    class LockedProvider:
        def resolve(self, binding):
            raise PrivateKeyLockedError('synthetic locked case')
    context = _context(backend, provider=True)
    context['key_provider'] = LockedProvider()
    result = pin_proof_report_to_ipfs({'source_text': MARKER}, private_context=context)
    assert result['status'] in {'unlock_needed', 'recoverable'}
    assert result['verified'] is False and not result.get('report_cid')
    assert backend.seen == []


def test_private_graph_export_never_replaces_existing_ciphertext(tmp_path: Path):
    class CollidingBackend(BytesBackend):
        def add_bytes(self, data, pin=True):
            result = super().add_bytes(data, pin=pin)
            self.blobs['bafyhermeticfixed'] = self.blobs.pop(result['cid'])
            return {**result, 'cid': 'bafyhermeticfixed'}
    backend = CollidingBackend()
    context = _context(backend)
    context['destination_dir'] = tmp_path / 'encrypted-graphs'
    first = persist_graph_snapshot({'text': MARKER}, private_context=context)
    assert first['persisted'] is True
    target = next(context['destination_dir'].glob('*.bin'))
    before = target.read_bytes()
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700
    second = persist_graph_snapshot({'text': 'different-private-graph'}, private_context=context)
    assert second['status'] == 'recoverable' and second['persisted'] is False
    assert second['overwrites_existing'] is False and target.read_bytes() == before
    assert list(target.parent.iterdir()) == [target]


def test_private_proof_partial_failure_keeps_only_genuine_encrypted_artifact_receipt():
    backend = BytesBackend(fail_theorem=True)
    context = _context(backend, provider=True)
    context['revision'] = 'proof-1'
    report = {'source_text': MARKER, 'theorem_export': {'lean4': MARKER}}
    result = pin_proof_report_to_ipfs(report, private_context=context)
    assert result['status'] == 'recoverable' and result['deferred'] is True
    assert result['verified'] is False and result['network_durable'] is False
    assert result['report_cid'] == result['lean4_cid'] == result['coq_cid'] == ''
    assert set(result['artifacts']) == {'proof-history'}
    prior = result['artifacts']['proof-history']
    assert prior['verified'] is True and len(backend.seen) == 1
    assert json.loads(open_private_artifact(backend.blobs[prior['cid']], binding=_binding('proof-history', 'proof-1:proof-history'), key=KEY, expected_key_id=KEY_ID)) == report
    assert MARKER.encode() not in backend.seen[0]
