"""Qualified host dispatch for acquire, ingest, and grounding refresh.

Caller booleans, registry rows, and invented receipts stay inert. Effects run
only after the workspace re-reads saved consent, a graph target, ciphertext,
and the live derived index.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService
from mediator.hook_runtime import (
    LEGAL_EVIDENCE_OPERATIONS,
    dispatch_registered_hook_operation,
    graph_revision_token,
    operation_handler_call_count,
    register_legal_evidence_operations,
)


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_SECRET = b"synthetic-private-ux50-source"
_STATUTE = "Synthetic public statute section 1 applies to the example only."
_USER = "synthetic-ux50-owner"
_SOURCE = "cd" * 32


def _legal_context() -> dict:
    empty = {"role": "event_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True}
    return {
        "status": "unknown",
        "jurisdiction": "unknown",
        "jurisdiction_explicit": False,
        "context_revision": 1,
        "applicable_law_date": dict(empty, role="applicable_law_date"),
        "event_date": empty,
        "filing_reference_date": dict(empty, role="filing_reference_date"),
        "corpus_retrieval_date": dict(empty, role="corpus_retrieval_date"),
    }


def _request(operation: str, *, graph_revision: str | None = None) -> dict:
    body = {
        "operation": operation,
        "role": "extract_facts",
        "target_ref": "target.ux50",
        "source_refs": [{"source_id": "src-ux50", "content_hash": _SOURCE}],
    }
    if operation == "acquire_legal_sources":
        body["citation_ref"] = "cite.ux50"
    elif operation == "ingest_private_evidence":
        body["evidence_ref"] = "evidence.ux50"
    else:
        body["graph_revision"] = graph_revision or ""
    return body


def _dispatch(service, request, now):
    return service.dispatch_public_mediator_operation(
        _USER,
        request,
        session_id="session-ux50",
        session_revision=2,
        now=now,
        source_bindings=[{"source_id": "src-ux50", "content_hash": _SOURCE}],
        legal_context=_legal_context(),
        persisted_consent_verified=True,
        key_available=True,
        private_store_available=True,
        derived_index_ready=True,
        handler_enabled=True,
        receipt={"qualified": True, "effect_dispatched": True, "writes": 9},
        host_targets=("target.ux50", "foreign.target"),
        effect=lambda _request: (_ for _ in ()).throw(AssertionError("caller effect")),
        handler=lambda _request: (_ for _ in ()).throw(AssertionError("caller handler")),
    )


def _open(root) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root)
    status = service.private_key_status()
    if status.get("protection") in {None, "", "missing"}:
        service.initialize_private_keys(protection="passphrase", passphrase="synthetic-ux50-passphrase")
    if service.private_key_status().get("unlocked") is not True:
        service.unlock_private_keys(passphrase="synthetic-ux50-passphrase")
    service.ensure_private_case_key(_USER, _USER)
    return service


def _prepare(tmp_path, *, consent: bool = True, owners: bool = True, artifact: bool = True, entity: bool = True, statute: bool = True):
    service = _open(tmp_path / "workspace")
    service.set_privacy_policy(_USER, "local")
    key = bytes(range(32))
    if consent:
        service.save_mediator_operation_consent(_USER, list(LEGAL_EVIDENCE_OPERATIONS))
    if artifact:
        stored = service.store_case_private_source(_USER, _SECRET, key=key, key_id="ux50-key")
        assert stored["verified"] is True
    if owners:
        bound = service.bind_case_mediator_owners(_USER, key=key, key_id="ux50-key")
        assert bound["index_status"] == "available"
    if entity:
        published = service.publish_case_host_entity(_USER, "target.ux50")
    else:
        published = {"graph_revision": ""}
    if statute:
        service.save_local_public_legal_text(_USER, "cite.ux50", _STATUTE)
    return service, published


def test_registry_and_caller_flags_do_not_activate_handlers() -> None:
    before = operation_handler_call_count()
    registered = register_legal_evidence_operations()
    assert registered["dispatch_enabled"] is False
    assert all(row["handler_enabled"] is False and row["effect_enabled"] is False for row in registered["operations"])
    calls = []
    refused = dispatch_registered_hook_operation(
        _request("ingest_private_evidence"),
        context=None,
        host_targets=("target.ux50",),
        owner_id=_USER,
        case_id=_USER,
        session_id="session-ux50",
        session_revision=2,
        graph_revision="gr-ux50",
        legal_context=_legal_context(),
        purpose="ingest_private_evidence",
        source_bindings=[{"source_id": "src-ux50", "content_hash": _SOURCE}],
        privacy_context=None,
        now=datetime.now(timezone.utc),
        persisted_consent_verified=True,
        key_available=True,
        private_store_available=True,
        derived_index_ready=True,
        effect=lambda _item: calls.append("effect"),
        handler=lambda _item: calls.append("handler"),
        probes={"ready": True},
    )
    assert refused["status"] == "refused" and refused["code"] in {"malformed", "binding_missing", "target_not_host_owned", "consent_missing"}
    assert refused["writes"] == 0 and refused["effect_dispatched"] is False
    assert calls == []
    assert operation_handler_call_count() == before


def test_public_dispatch_writes_real_effects_and_a_saved_journal(tmp_path) -> None:
    service, published = _prepare(tmp_path)
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    before = operation_handler_call_count()
    graph_before = published["graph_revision"]
    acquired = _dispatch(service, _request("acquire_legal_sources"), now)
    ingested = _dispatch(service, _request("ingest_private_evidence"), now)
    refreshed = _dispatch(service, _request("refresh_grounding", graph_revision=graph_before), now)
    assert acquired["status"] == "successful" and acquired["writes"] == 1
    assert acquired["effect_dispatched"] is True and acquired["proof_status"] == "not_proof"
    assert acquired["provider_invoked"] is False and acquired["source_refs_admitted"] is False
    assert ingested["status"] == "successful" and ingested["storage_invoked"] is True and ingested["writes"] == 1
    assert refreshed["status"] == "successful" and refreshed["writes"] == 1
    assert operation_handler_call_count() == before + 3
    index = service.case_derived_index_owner("acquire_legal_sources", _USER, _USER)
    cached = [row for row in index._derived().public_law_cache.values() if row.get("text") == _STATUTE]
    assert cached and cached[0]["citation"] == "cite.ux50"
    revealed = [entry for entry in index._derived().entries.values() if entry.get("kind") == "evidence"]
    assert revealed and revealed[0]["text"] == "sha256:" + __import__("hashlib").sha256(_SECRET).hexdigest()
    assert _SECRET.decode() not in revealed[0]["text"]
    assert graph_revision_token(service.case_knowledge_graph(_USER, _USER)) != graph_before
    journal = service.mediator_operation_journal(_USER)
    assert [item["operation"] for item in journal] == list(LEGAL_EVIDENCE_OPERATIONS)
    assert all(item["effect_dispatched"] is True and item["writes"] == 1 and item["proof"] is False for item in journal)
    encoded = json.dumps(journal)
    assert _SECRET.decode() not in encoded and _STATUTE not in encoded
    reloaded = _open(tmp_path / "workspace")
    assert [item["ordinal"] for item in reloaded.mediator_operation_journal(_USER)] == [1, 2, 3]
    registered = register_legal_evidence_operations()
    assert all(row["handler_enabled"] is False for row in registered["operations"])


def test_missing_consent_owner_stale_and_late_paths_do_not_write(tmp_path) -> None:
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    bare = _prepare(tmp_path / "bare", consent=False)
    refused = _dispatch(bare[0], _request("acquire_legal_sources"), now)
    assert refused["status"] == "refused" and refused["code"] == "consent_missing"
    assert refused["writes"] == 0 and refused["handler_invoked"] is False
    assert bare[0].mediator_operation_journal(_USER)[-1]["effect_dispatched"] is False

    service, published = _prepare(tmp_path / "ready")
    before_calls = operation_handler_call_count()
    service.detach_mediator_operation_owner(_USER, "refresh_grounding")
    missing = _dispatch(service, _request("refresh_grounding", graph_revision=published["graph_revision"]), now)
    assert missing["code"] == "binding_missing" and missing["writes"] == 0
    assert operation_handler_call_count() == before_calls

    service.bind_case_mediator_owners(_USER, key=bytes(range(32)), key_id="ux50-key")
    current = graph_revision_token(service.case_knowledge_graph(_USER, _USER))
    stale = _dispatch(service, _request("refresh_grounding", graph_revision="gr-stale-token"), now)
    assert stale["code"] == "stale_revision" and stale["writes"] == 0
    assert graph_revision_token(service.case_knowledge_graph(_USER, _USER)) == current

    service.schedule_late_mediator_mutation(_USER, "revoke_consent")
    late = _dispatch(service, _request("ingest_private_evidence"), now)
    assert late["late"] is True and late["code"] == "consent_revoked"
    assert late["effect_dispatched"] is False and late["handler_invoked"] is False
    assert late["writes"] == 0
    journal = service.mediator_operation_journal(_USER)
    assert journal[-1]["late"] is True and journal[-1]["code"] == "consent_revoked"
    assert _SECRET.decode() not in json.dumps(journal)

    service.save_mediator_operation_consent(_USER, list(LEGAL_EVIDENCE_OPERATIONS))
    service.schedule_late_mediator_mutation(_USER, "drop_artifact")
    dropped = _dispatch(service, _request("acquire_legal_sources"), now)
    assert dropped["late"] is True and dropped["code"] == "private_store_unavailable"
    assert dropped["writes"] == 0 and dropped["storage_invoked"] is False
