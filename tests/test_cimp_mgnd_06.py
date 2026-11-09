"""Typed legal and evidence operations stay registered and effect-disabled.

Cases are synthetic private fixtures. No test is skipped. Registration does
not call a provider, backend, or store, and dispatch does not write.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode
from mediator.hook_runtime import (
    LEGAL_EVIDENCE_OPERATIONS,
    MODEL_PURPOSE_IDS,
    bind_hook_execution_context,
    dispatch_registered_hook_operation,
    operation_handler_call_count,
    register_legal_evidence_operations,
)
from mediator.workflow_service import WorkflowActionService
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases, prepare_private_root


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
_DEADLINE = datetime(2026, 12, 1, tzinfo=timezone.utc)
_SECRET = "PRIVATE-PROMPT-do-not-echo"
_OWNERS = {
    "acquire_legal_sources": "mediator.legal_authority_hooks.LegalAuthoritySearchHook",
    "ingest_private_evidence": "mediator.evidence_hooks.EvidenceStorageHook",
    "refresh_grounding": "mediator.mediator.Mediator.refresh_verified_legal_dependencies",
}


class _Probe:
    def __init__(self):
        self.calls = []

    def provider(self, *_args, **_kwargs):
        self.calls.append("provider")
        raise AssertionError("provider")

    def backend(self, *_args, **_kwargs):
        self.calls.append("backend")
        raise AssertionError("backend")

    def storage(self, *_args, **_kwargs):
        self.calls.append("storage")
        raise AssertionError("storage")


class _Mediator:
    def __getattr__(self, name):
        raise AssertionError(name)


def _privacy(owner_id: str, case_id: str):
    policy = privacy_policy_for_mode(owner_id, case_id, "local")
    return build_complaint_privacy_context(policy, user_id=owner_id, case_id=case_id, data_class="fact_kg")


def _legal_context(case) -> dict:
    event = case.narrative.event_date
    return {
        "status": "explicit" if event and case.narrative.jurisdiction != "unknown" else "unknown",
        "jurisdiction": case.narrative.jurisdiction,
        "jurisdiction_explicit": case.narrative.jurisdiction != "unknown",
        "context_revision": 1,
        "applicable_law_date": {"role": "applicable_law_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "event_date": {"role": "event_date", "raw_text": event, "start_date": event, "end_date": event, "is_uncertain": not bool(event)},
        "filing_reference_date": {"role": "filing_reference_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "corpus_retrieval_date": {"role": "corpus_retrieval_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "questions": [_SECRET],
    }


def _bindings(case) -> list[dict]:
    if not case.sources:
        return [{"source_id": f"src-{case.label}", "content_hash": "ab" * 32}]
    return [{"source_id": source.authority_id, "content_hash": source.source_sha256, "source_text": source.source_text} for source in case.sources]


def _source_refs(case) -> list[dict]:
    return [{"source_id": row["source_id"], "content_hash": row["content_hash"]} for row in _bindings(case)]


def _bind(case, operation: str):
    owner_id = "synthetic-owner"
    return bind_hook_execution_context(
        operation=operation,
        owner_id=owner_id,
        case_id=case.case_id,
        session_id=f"session-{case.label}",
        session_revision=2,
        graph_revision=f"gr-{case.label}-1",
        legal_context=_legal_context(case),
        purpose=operation,
        deadline=_DEADLINE,
        source_bindings=_bindings(case),
        privacy_context=_privacy(owner_id, case.case_id),
    )


def _auth(case, context, **overrides):
    fields = {
        "owner_id": context.owner_id,
        "case_id": context.case_id,
        "session_id": context.session_id,
        "session_revision": context.session_revision,
        "graph_revision": context.graph_revision,
        "legal_context": _legal_context(case),
        "purpose": context.purpose,
        "source_bindings": _bindings(case),
        "privacy_context": _privacy(context.owner_id, context.case_id),
        "now": _NOW,
        "storage_available": True,
        "request_state": "active",
        "key_available": True,
        "private_store_available": True,
        "derived_index_ready": True,
        "persisted_consent_verified": True,
    }
    fields.update(overrides)
    return fields


def _request(case, operation: str, **overrides):
    body = {
        "operation": operation,
        "role": "extract_facts",
        "target_ref": f"target.{case.label}",
        "source_refs": _source_refs(case),
    }
    if operation == "acquire_legal_sources":
        body["citation_ref"] = f"cite.{case.label}"
    elif operation == "ingest_private_evidence":
        body["evidence_ref"] = f"evidence.{case.label}"
    else:
        body["graph_revision"] = f"gr-{case.label}-1"
    body.update(overrides)
    return body


def _assert_closed(result: dict, case) -> None:
    encoded = json.dumps(result, sort_keys=True)
    assert _SECRET not in encoded
    assert case.narrative.text not in encoded
    for source in case.sources:
        assert source.source_text not in encoded
    assert result["candidate_status"] in {"not_candidate", "refused"}
    assert result["source_status"] in {"not_admitted", "refused"}
    assert result["support_status"] in {"unsupported", "refused"}
    assert result["proof_status"] == "not_proof"
    assert result["effect_dispatched"] is False
    assert result["provider_invoked"] is False
    assert result["backend_invoked"] is False
    assert result["storage_invoked"] is False
    assert result["writes"] == 0
    assert result["handler_invoked"] is False
    assert result["dispatch_enabled"] is False
    assert result["source_refs_admitted"] is False
    assert len(result["source_refs"]) <= 8


def test_registry_maps_owners_without_effects(tmp_path):
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    root = prepare_private_root(tmp_path, storage_available=True)
    before_tree = sorted(path.relative_to(root.root).as_posix() for path in root.root.rglob("*"))
    probe = _Probe()
    before = operation_handler_call_count()
    receipt = register_legal_evidence_operations(probes={"provider": probe.provider, "backend": probe.backend, "storage": probe.storage})
    assert receipt["registered"] is True
    assert receipt["dispatch_enabled"] is False
    assert receipt["writes_enabled"] is False
    assert receipt["handler_call_count"] == before
    assert probe.calls == []
    names = [row["operation"] for row in receipt["operations"]]
    assert names == list(LEGAL_EVIDENCE_OPERATIONS)
    for row in receipt["operations"]:
        assert row["owner"] == _OWNERS[row["operation"]]
        assert row["handler_bound"] is True
        assert row["handler_enabled"] is False
        assert row["next_operations"] == []
        assert row["adjacent_roles"] == ["extract_facts", "propose_questions", "explain_candidate"]
        assert set(row["adjacent_roles"]) == set(MODEL_PURPOSE_IDS)
        assert {item["id"] for item in row["prerequisites"]} == {
            "persisted_operation_consent",
            "encrypted_private_artifact_store",
            "derived_index_boundary",
        }
        assert all(item["verified"] is False and item["implemented"] is False for item in row["prerequisites"])
    after_tree = sorted(path.relative_to(root.root).as_posix() for path in root.root.rglob("*"))
    assert after_tree == before_tree
    service = WorkflowActionService(_Mediator())
    declared = service.declare_legal_evidence_hook_operations()
    assert declared["dispatch_enabled"] is False
    assert service._legal_evidence_handlers_enabled is False
    assert probe.calls == []


def test_catalog_dispatch_stays_unavailable_without_writes():
    probe = _Probe()
    service = WorkflowActionService(_Mediator())
    service.declare_legal_evidence_hook_operations()
    seen = []
    for case in meaningful_cases():
        for operation in LEGAL_EVIDENCE_OPERATIONS:
            context = _bind(case, operation)
            result = service.dispatch_legal_evidence_hook_operation(
                _request(case, operation),
                context=context,
                host_targets=(f"target.{case.label}",),
                probes={"provider": probe.provider, "backend": probe.backend, "storage": probe.storage},
                effect=lambda _receipt: probe.calls.append("effect"),
                handler=lambda _request: probe.calls.append("handler"),
                **_auth(case, context),
            )
            seen.append(result["code"])
            _assert_closed(result, case)
            assert result["status"] == "unavailable"
            assert result["code"] == "prerequisite_unavailable"
            assert result["owner"] == _OWNERS[operation]
            assert result["role"] == "extract_facts"
            assert result["role_dispatched"] is False
            assert result["source_refs"] == _source_refs(case)
            assert all(item["verified"] is False for item in result["prerequisites"])
    assert seen
    assert probe.calls == []
    assert operation_handler_call_count() == 0


def test_negative_boundaries_do_not_touch_provider_or_store():
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    operation = "ingest_private_evidence"
    context = _bind(case, operation)
    probe = _Probe()
    service = WorkflowActionService(_Mediator())
    unregistered = service.dispatch_legal_evidence_hook_operation(_request(case, operation))
    assert unregistered["code"] == "operation_unregistered"
    assert probe.calls == []
    service.declare_legal_evidence_hook_operations()
    common = {
        "context": context,
        "host_targets": (f"target.{case.label}",),
        "probes": {"provider": probe.provider, "backend": probe.backend, "storage": probe.storage},
    }
    missing = dispatch_registered_hook_operation(
        _request(case, operation),
        **common,
        **_auth(case, context, privacy_context=None),
    )
    assert missing["code"] == "consent_missing"
    assert missing["status"] == "refused"
    key = service.dispatch_legal_evidence_hook_operation(
        _request(case, operation),
        **common,
        **_auth(case, context, key_available=False),
    )
    assert key["code"] == "key_unavailable"
    store = service.dispatch_legal_evidence_hook_operation(
        _request(case, operation),
        **common,
        **_auth(case, context, private_store_available=False),
    )
    assert store["code"] == "private_store_unavailable"
    index = service.dispatch_legal_evidence_hook_operation(
        _request(case, operation),
        **common,
        **_auth(case, context, derived_index_ready=False),
    )
    assert index["code"] == "derived_index_unready"
    for result in (missing, key, store, index):
        _assert_closed(result, case)
    assert probe.calls == []
    assert operation_handler_call_count() == 0


def test_model_fields_and_unknown_targets_fail_closed():
    case = next(item for item in meaningful_cases() if item.label == "contradiction")
    operation = "acquire_legal_sources"
    context = _bind(case, operation)
    probe = _Probe()
    host_targets = (f"target.{case.label}",)
    base = _auth(case, context)
    samples = [
        (_request(case, operation, tools=[{"name": "search"}]), "model_cannot_invoke_tools"),
        (_request(case, operation, destination="https://example.test/write"), "model_cannot_supply_destination"),
        (_request(case, operation, file_path="/tmp/private-evidence.bin"), "model_cannot_supply_path"),
        (_request(case, operation, provider_command="grok --prompt"), "model_cannot_supply_provider_command"),
        (_request(case, operation, satisfied_nodes=["node-1"]), "model_cannot_satisfy_requirements"),
        (_request(case, operation, chain=["ingest_private_evidence"]), "unbounded_chain"),
        (_request(case, operation, note="extra"), "unknown_field"),
        (_request(case, operation, target_ref="model.chosen.target"), "target_not_host_owned"),
        (
            {
                "operation": operation,
                "model_proposal": {
                    "target_ref": "model.chosen.target",
                    "tools": ["shell"],
                    "file_path": "/tmp/out",
                    "provider_command": "grok",
                    "node_edits": [{"id": "n1", "satisfied": True}],
                },
            },
            "model_cannot_invoke_tools",
        ),
    ]
    for request, code in samples:
        result = dispatch_registered_hook_operation(
            request,
            context=context,
            host_targets=host_targets,
            probes={"provider": probe.provider, "storage": probe.storage, "backend": probe.backend},
            effect=lambda _receipt: probe.calls.append("effect"),
            **base,
        )
        assert result["code"] == code
        assert result["status"] == "refused"
        _assert_closed(result, case)
        assert result["source_refs"] == [] or code == "target_not_host_owned"
    refresh = _bind(case, "refresh_grounding")
    stale = dispatch_registered_hook_operation(
        _request(case, "refresh_grounding", graph_revision="gr-other"),
        context=refresh,
        host_targets=host_targets,
        **_auth(case, refresh),
    )
    assert stale["code"] == "stale_revision"
    assert probe.calls == []
    assert operation_handler_call_count() == 0
