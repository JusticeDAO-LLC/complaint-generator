"""Factual revisions persist through the private case transaction.

Synthetic fixtures only. Ciphertext storage ids stay distinct from source and
assertion ids. Wrong key, wrong case, corrupt bytes, and an unavailable
backend fail without replacing the last committed graph or writing plaintext.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService, WorkspacePersistenceError
from complaint_phases.knowledge_graph import Entity, KnowledgeGraph, Relationship
from integrations.ipfs_datasets import graphs as graph_module
from integrations.ipfs_datasets.types import build_user_assertion_envelope, source_byte_hash
from integrations.private_storage import PrivateArtifactIntegrityError, PrivateStorageError


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_OWNER = "mgnd14-owner"
_PASSPHRASE = "synthetic-passphrase-mgnd14"
_CASES = ("supersede", "retract", "conflict")


def _envelope(text: str, message_id: str):
    return build_user_assertion_envelope(
        source_text=text,
        source_kind="user_statement",
        source_id=message_id,
        message_id=message_id,
        assertion_status="asserted",
        extractor_version="mgnd14-test",
        source_hash=source_byte_hash(text),
        source_span={"start": 0, "end": len(text.encode("utf-8")), "text": text, "unit": "byte"},
        subject_key="employment-fact",
    )


def _fact(entity_id: str, text: str, message_id: str):
    envelope = _envelope(text, message_id)
    entity = Entity(
        id=entity_id,
        type="fact",
        name=text,
        attributes={"description": text, "fact_type": "timeline"},
        confidence=0.4,
        source="complaint",
        provenance={"user_assertion": envelope.as_dict()},
    )
    return entity, envelope


def _graph_for(label: str):
    sentinel = f"MGND14-SENTINEL-{label}-private-fact"
    original = f"{sentinel} original warehouse statement"
    replacement = f"{sentinel} replacement warehouse statement"
    graph = KnowledgeGraph(
        graph_id=f"graph-{label}",
        graph_version="1",
        provenance={"source_kind": "user_statement", "task": "CIMP-MGND-14", "label": label},
    )
    fact, envelope = _fact(f"fact-{label}", original, f"msg-{label}")
    other, other_envelope = _fact(f"fact-other-{label}", f"{sentinel} schedule stayed", f"msg-other-{label}")
    claim = Entity(id=f"claim-{label}", type="claim", name="Termination", attributes={"claim_type": "employment"}, confidence=0.8)
    graph.add_entity(claim)
    graph.add_entity(fact)
    graph.add_entity(other)
    graph.register_assertion(fact, envelope, status="active")
    graph.register_assertion(other, other_envelope, status="active")
    graph.add_relationship(Relationship(
        id=f"rel-support-{label}",
        source_id=fact.id,
        target_id=claim.id,
        relation_type="supports",
        attributes={"proof_cache": {"fact_id": fact.id, "satisfied": True}},
        confidence=0.9,
    ))
    graph.add_relationship(Relationship(
        id=f"rel-other-{label}",
        source_id=other.id,
        target_id=claim.id,
        relation_type="supports",
        attributes={"proof_cache": {"fact_id": other.id, "satisfied": True}},
        confidence=0.9,
    ))
    if label == "supersede":
        revised, revised_envelope = _fact(f"fact-new-{label}", replacement, f"msg-new-{label}")
        graph.add_entity(revised)
        graph.supersede_assertion(envelope.stable_id, revised, revised_envelope, event_id=f"event-{label}")
    elif label == "retract":
        revised, revised_envelope = _fact(f"fact-new-{label}", replacement, f"msg-new-{label}")
        graph.add_entity(revised)
        graph.retract_assertion(envelope.stable_id, revised, revised_envelope, event_id=f"event-{label}")
    else:
        graph.record_assertion_conflict(
            envelope.stable_id,
            other_envelope.stable_id,
            event_id=f"event-{label}",
            left_entity_id=fact.id,
            right_entity_id=other.id,
        )
    return graph, sentinel, envelope.stable_id


def _service(root: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root)
    created = service.initialize_private_keys(protection="passphrase", passphrase=_PASSPHRASE)
    assert created.get("unlocked") is True or created.get("status") in {"available", "ready"}
    unlocked = service.unlock_private_keys(passphrase=_PASSPHRASE)
    assert unlocked.get("awaiting_user") is not True
    return service


def _bind(service: ComplaintWorkspaceService, case_id: str) -> None:
    ready = service.ensure_private_case_key(_OWNER, case_id)
    assert ready.get("data_key_id")


def _head_bytes(root: Path) -> bytes:
    matches = [path for path in (root / "joined-revisions").rglob("head.cgpe") if path.is_file()]
    assert len(matches) == 1
    return matches[0].read_bytes()


def _plaintext_cid(payload: bytes) -> str:
    return "bafy" + hashlib.sha256(payload).hexdigest()[:55]


def _assert_no_plaintext(root: Path, sentinel: str, plaintext_ids: set[str], payload: bytes) -> None:
    needle = sentinel.encode("utf-8")
    plain_cid = _plaintext_cid(payload)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        blob = path.read_bytes()
        assert needle not in blob
        assert plain_cid.encode("utf-8") not in blob
        assert path.name not in plaintext_ids
        assert path.suffix != ".json" or b"cimp-mgnd-14-factual-graph-v1" not in blob


class _UnavailableBackend:
    def add_bytes(self, data, pin=True):
        raise OSError("synthetic factual-graph backend unavailable")

    def cat(self, cid):
        raise OSError("synthetic factual-graph backend unavailable")

    def pin(self, cid):
        raise OSError("synthetic factual-graph backend unavailable")


@pytest.mark.parametrize("label", _CASES)
def test_factual_graph_roundtrip_uses_the_private_case_transaction(tmp_path: Path, label: str):
    graph, sentinel, stable_id = _graph_for(label)
    before_registry = set(graph_module._GRAPH_SNAPSHOT_REGISTRY)
    case_id = f"mgnd14-{label}"
    root = tmp_path / "sessions"
    service = _service(root)
    _bind(service, case_id)
    artifact = graph_module.build_factual_graph_artifact(graph)
    payload = graph_module.encode_factual_graph_artifact(artifact)
    plaintext_ids = graph_module.factual_graph_plaintext_ids(artifact)
    assert stable_id in plaintext_ids
    assert artifact["revisions"]
    if label == "conflict":
        assert artifact["unresolved_conflicts"]
        assert all(item["status"] == "unresolved" for item in artifact["unresolved_conflicts"])
    else:
        assert artifact["unresolved_conflicts"] == []
    assert artifact["invalidations"]
    assert any(item["activity_status"] == "invalidated" for item in artifact["invalidations"])

    receipt = service.commit_factual_graph_revision(
        _OWNER,
        graph,
        case_id=case_id,
        transaction_id=f"tx-{label}",
        effect_id=f"effect-{label}",
    )
    storage_id = receipt["ciphertext_storage_id"]
    assert receipt["committed"] is True
    assert receipt["plaintext_fallback"] is False
    assert receipt["private_artifact"] is True
    assert receipt["graph_registry_used"] is False
    assert storage_id not in plaintext_ids
    assert storage_id != _plaintext_cid(payload)
    assert not storage_id.startswith("assertion:")
    assert set(graph_module._GRAPH_SNAPSHOT_REGISTRY) == before_registry

    reloaded = service.reload_factual_graph_revision(_OWNER, case_id=case_id)
    assert reloaded["owner"] == _OWNER
    assert reloaded["case_id"] == case_id
    assert reloaded["ciphertext_storage_id"] == storage_id
    assert reloaded["plaintext_fallback"] is False
    assert reloaded["assertion_states"] == artifact["assertion_states"]
    assert reloaded["relationships"] == artifact["relationships"]
    assert reloaded["invalidations"] == artifact["invalidations"]
    assert reloaded["unresolved_conflicts"] == artifact["unresolved_conflicts"]
    assert reloaded["revisions"] == artifact["revisions"]
    if label == "supersede":
        assert any(item.get("status") == "superseded" for item in reloaded["assertion_states"].values())
    elif label == "retract":
        assert any(item.get("status") == "retracted" for item in reloaded["assertion_states"].values())
    else:
        assert {item.get("status") for item in reloaded["assertion_states"].values()} == {"conflict"}

    restarted = ComplaintWorkspaceService(root)
    restarted.unlock_private_keys(passphrase=_PASSPHRASE)
    _bind(restarted, case_id)
    again = restarted.reload_factual_graph_revision(_OWNER, case_id=case_id)
    assert again["artifact"] == reloaded["artifact"]
    loaded_state = restarted._load_state(_OWNER, case_id=case_id)
    assert loaded_state["private_revision"] == reloaded["revision"]
    _assert_no_plaintext(root, sentinel, plaintext_ids, payload)


def test_wrong_key_case_corrupt_bytes_and_unavailable_backend_preserve_the_commit(tmp_path: Path):
    label = "supersede"
    graph, sentinel, _stable_id = _graph_for(label)
    case_id = "mgnd14-failure"
    root = tmp_path / "sessions"
    service = _service(root)
    _bind(service, case_id)
    receipt = service.commit_factual_graph_revision(
        _OWNER,
        graph,
        case_id=case_id,
        transaction_id="tx-failure",
        effect_id="effect-failure",
    )
    committed = service.reload_factual_graph_revision(_OWNER, case_id=case_id)
    head = _head_bytes(root)
    artifact_path = root / "private-artifacts" / receipt["ciphertext_storage_id"]
    stored_blob = artifact_path.read_bytes()
    assert stored_blob.startswith(b"CGPE")
    assert sentinel.encode("utf-8") not in stored_blob

    context = service._private_artifact_context(_OWNER, case_id)
    with pytest.raises((PrivateStorageError, PrivateArtifactIntegrityError)):
        graph_module.open_factual_graph_artifact(
            receipt["ciphertext_storage_id"],
            access=context["access"],
            tenant_id=context["tenant_id"],
            case_id=case_id,
            principal_id=context["principal_id"],
            revision=receipt["artifact_revision"],
            backend=service._private_local_backend(),
            backend_name="local_cache",
            key=os.urandom(32),
            key_id=str(receipt.get("key_id") or context["key_provider"].resolve(
                __import__("integrations.private_storage", fromlist=["PrivateArtifactBinding"]).PrivateArtifactBinding(
                    tenant_id=_OWNER,
                    case_id=case_id,
                    artifact_kind="fact-graph",
                    revision=receipt["artifact_revision"],
                    principal_id=_OWNER,
                )
            )[0]),
        )
    assert _head_bytes(root) == head
    assert artifact_path.read_bytes() == stored_blob

    other_case = "mgnd14-other-case"
    _bind(service, other_case)
    with pytest.raises(WorkspacePersistenceError) as wrong_case:
        service.reload_factual_graph_revision(_OWNER, case_id=other_case)
    assert wrong_case.value.code
    assert _head_bytes(root) == head
    assert service.reload_factual_graph_revision(_OWNER, case_id=case_id)["artifact"] == committed["artifact"]

    flipped = bytearray(stored_blob)
    flipped[-1] ^= 0x01
    artifact_path.write_bytes(bytes(flipped))
    with pytest.raises(WorkspacePersistenceError) as corrupt:
        service.reload_factual_graph_revision(_OWNER, case_id=case_id)
    assert corrupt.value.code == "authentication_failed"
    assert _head_bytes(root) == head
    assert artifact_path.read_bytes() == bytes(flipped)
    artifact_path.write_bytes(stored_blob)
    assert service.reload_factual_graph_revision(_OWNER, case_id=case_id)["revisions"] == committed["revisions"]

    with pytest.raises(WorkspacePersistenceError) as unavailable:
        service.commit_factual_graph_revision(
            _OWNER,
            graph,
            case_id=case_id,
            transaction_id="tx-unavailable",
            effect_id="effect-unavailable",
            backend=_UnavailableBackend(),
        )
    assert unavailable.value.code
    assert unavailable.value.public_status == "unavailable"
    assert _head_bytes(root) == head
    restored = service.reload_factual_graph_revision(_OWNER, case_id=case_id)
    assert restored["artifact"] == committed["artifact"]
    assert restored["invalidations"] == committed["invalidations"]
    assert restored["unresolved_conflicts"] == committed["unresolved_conflicts"]
    _assert_no_plaintext(root, sentinel, graph_module.factual_graph_plaintext_ids(committed["artifact"]), graph_module.encode_factual_graph_artifact(committed["artifact"]))
