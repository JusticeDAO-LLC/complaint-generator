"""Replay-safe, graph-bound hook effects.

Cases are synthetic private fixtures. No test is skipped. Effect receipts bind
the current source and context preimages and the accepted graph revision.
Identical replay does not add source, evidence, or support records. Changed
preimages, stale revisions, and late cancelled or stale results do not mutate
the graph, the pending inquiry, or the saved case. A candidate acquisition and
a receipt are not durability or proof.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from complaint_phases.knowledge_graph import KnowledgeGraph
from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode
from mediator.hook_runtime import (
    accept_bound_hook_effect,
    bind_hook_execution_context,
    graph_revision_token,
    receipt_establishes_durability,
    receipt_establishes_proof,
    saved_case_hash,
)
from mediator.workflow_service import WorkflowActionService
from tests.mgnd_fixtures import meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
_DEADLINE = datetime(2026, 12, 1, tzinfo=timezone.utc)
_SECRET = "PRIVATE-PROMPT-do-not-echo"


def _privacy(owner_id: str, case_id: str):
    policy = privacy_policy_for_mode(owner_id, case_id, "local")
    return build_complaint_privacy_context(policy, user_id=owner_id, case_id=case_id, data_class="fact_kg")


def _legal_context(case, *, revision: int = 1) -> dict:
    event = case.narrative.event_date
    return {
        "status": "explicit" if event and case.narrative.jurisdiction != "unknown" else "unknown",
        "jurisdiction": case.narrative.jurisdiction,
        "jurisdiction_explicit": case.narrative.jurisdiction != "unknown",
        "context_revision": revision,
        "applicable_law_date": {"role": "applicable_law_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "event_date": {"role": "event_date", "raw_text": event, "start_date": event, "end_date": event, "is_uncertain": not bool(event)},
        "filing_reference_date": {"role": "filing_reference_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "corpus_retrieval_date": {"role": "corpus_retrieval_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "questions": [_SECRET],
    }


def _bindings(case) -> list[dict]:
    if not case.sources:
        return [{"source_id": f"src-{case.label}", "content_hash": "ab" * 32}]
    return [
        {"source_id": source.authority_id, "content_hash": source.source_sha256, "source_text": source.source_text}
        for source in case.sources
    ]


def _records(case) -> list[dict]:
    rows = []
    for binding in _bindings(case):
        for kind in ("source", "evidence", "support"):
            rows.append({
                "kind": kind,
                "source_id": binding["source_id"],
                "content_hash": binding["content_hash"],
            })
    return rows


def _inquiry(case, revision: int = 1) -> dict:
    return {"inquiry_id": f"inq-{case.label}", "revision": revision, "question": _SECRET}


def _saved_case(case) -> dict:
    return {"case_id": case.case_id, "label": case.label, "narrative_id": case.narrative.narrative_id}


def _context(case, graph: KnowledgeGraph, operation: str = "refresh_grounding"):
    owner_id = "synthetic-owner"
    return bind_hook_execution_context(
        operation=operation,
        owner_id=owner_id,
        case_id=case.case_id,
        session_id=f"session-{case.label}",
        session_revision=2,
        graph_revision=graph_revision_token(graph),
        legal_context=_legal_context(case),
        purpose=operation,
        deadline=_DEADLINE,
        source_bindings=_bindings(case),
        privacy_context=_privacy(owner_id, case.case_id),
    )


def _counts(graph: KnowledgeGraph) -> dict:
    ledger = graph.factual_ledger()
    stored = ledger.get("hook_effect_records") or {}
    flat = [row for rows in stored.values() for row in rows]
    return {
        "revisions": len(ledger.get("revisions") or []),
        "entities": len(graph.entities),
        "relationships": len(graph.relationships),
        "records": len(flat),
        "events": len(ledger.get("answer_events") or {}),
    }


def _accept(case, graph, **overrides):
    context = overrides.pop("context", None) or _context(case, graph)
    pending = overrides.pop("pending_inquiry", _inquiry(case))
    saved = overrides.pop("saved_case", _saved_case(case))
    fields = {
        "context": context,
        "graph": graph,
        "source_bindings": _bindings(case),
        "legal_context": _legal_context(case),
        "request_id": f"req-{case.label}",
        "records": _records(case),
        "pending_inquiry": pending,
        "saved_case": saved,
        "bound_pending_inquiry": _inquiry(case),
        "bound_saved_case_hash": saved_case_hash(saved if "saved_case" not in overrides else overrides.get("saved_case")),
        "result_state": "active",
        "storage_available": case.storage_available,
    }
    fields.update(overrides)
    if "bound_saved_case_hash" not in overrides and "saved_case" in overrides:
        fields["bound_saved_case_hash"] = saved_case_hash(fields["saved_case"])
    return accept_bound_hook_effect(**fields)


def test_meaningful_cases_are_nonempty():
    cases = meaningful_cases()
    assert len(cases) >= 1
    assert {case.label for case in cases} >= {"baseline", "cancellation", "storage_outage"}


@pytest.mark.parametrize("case", meaningful_cases(), ids=lambda case: case.label)
def test_effect_receipt_binds_preimages_and_replays_without_duplicates(case):
    graph = KnowledgeGraph(graph_id=f"kg-{case.label}")
    pending = _inquiry(case)
    saved = _saved_case(case)
    context = _context(case, graph)
    before = _counts(graph)
    if not case.storage_available:
        refused = _accept(case, graph, context=context, pending_inquiry=pending, saved_case=saved)
        assert refused["accepted"] is False
        assert refused["code"] == "storage_unavailable"
        assert refused["candidate_acquisition"]["admitted"] is False
        assert refused["candidate_acquisition"]["candidate_status"] == "unavailable"
        assert receipt_establishes_durability(refused["effect_receipt"]) is False
        assert receipt_establishes_proof(refused["effect_receipt"]) is False
        assert _counts(graph) == before
        assert pending == _inquiry(case)
        assert saved == _saved_case(case)
        assert _SECRET not in str(refused["effect_receipt"])
        return

    first = _accept(case, graph, context=context, pending_inquiry=pending, saved_case=saved)
    assert first["accepted"] is True
    assert first["idempotent_replay"] is False
    assert first["mutated_pending_inquiry"] is False
    assert first["mutated_saved_case"] is False
    receipt = first["effect_receipt"]
    assert receipt["source_preimage"]
    assert receipt["context_preimage"]
    assert receipt["accepted_graph_revision"] == graph_revision_token(KnowledgeGraph(graph_id="unused")) or receipt["revision_index"] == 1
    assert receipt["accepted_graph_revision"].startswith("gr_")
    assert receipt["durable"] is False
    assert receipt["proof"] is False
    assert receipt["proof_status"] == "not_proof"
    assert receipt_establishes_durability(receipt) is False
    assert receipt_establishes_proof(receipt) is False
    assert first["candidate_acquisition"]["admitted"] is False
    assert first["candidate_acquisition"]["schema"] == "hook_candidate_acquisition_v1"
    assert _SECRET not in str(receipt)
    admitted = _counts(graph)
    assert admitted["revisions"] == before["revisions"] + 1
    assert admitted["records"] == before["records"] + len(_records(case))
    assert admitted["entities"] == before["entities"]
    assert pending == _inquiry(case)
    assert saved == _saved_case(case)

    replay = _accept(case, graph, context=context, pending_inquiry=pending, saved_case=saved)
    assert replay["accepted"] is True
    assert replay["idempotent_replay"] is True
    assert replay["effect_receipt"] == receipt
    assert replay["mutated_graph"] is False
    assert replay["mutated_pending_inquiry"] is False
    assert replay["mutated_saved_case"] is False
    assert _counts(graph) == admitted

    changed_sources = [{"source_id": row["source_id"], "content_hash": "cd" * 32} for row in _bindings(case)]
    drifted = _accept(case, graph, context=context, source_bindings=changed_sources, pending_inquiry=pending, saved_case=saved)
    assert drifted["accepted"] is False
    assert drifted["code"] == "source_preimage_changed"
    assert drifted["mutated_graph"] is False
    assert _counts(graph) == admitted

    drifted_context = _accept(
        case,
        graph,
        context=context,
        legal_context=_legal_context(case, revision=2),
        pending_inquiry=pending,
        saved_case=saved,
    )
    assert drifted_context["accepted"] is False
    assert drifted_context["code"] == "context_preimage_changed"
    assert _counts(graph) == admitted

    graph.append_revision({"action": "unrelated", "event_id": f"other-{case.label}"})
    moved = _counts(graph)
    stale = _accept(
        case,
        graph,
        context=context,
        request_id=f"req-{case.label}-late",
        pending_inquiry=pending,
        saved_case=saved,
    )
    assert stale["accepted"] is False
    assert stale["code"] == "stale_revision"
    assert stale["mutated_graph"] is False
    assert _counts(graph) == moved

    if case.label == "cancellation":
        late = _accept(case, graph, context=context, result_state="cancelled", pending_inquiry=pending, saved_case=saved)
        assert late["accepted"] is False
        assert late["code"] == "cancelled"
        assert late["mutated_graph"] is False
        assert late["mutated_pending_inquiry"] is False
        assert late["mutated_saved_case"] is False
        assert _counts(graph) == moved
        assert pending == _inquiry(case)
        assert saved == _saved_case(case)


@pytest.mark.parametrize("case", meaningful_cases(), ids=lambda case: case.label)
def test_late_stale_result_does_not_mutate_inquiry_or_saved_case(case):
    graph = KnowledgeGraph(graph_id=f"late-{case.label}")
    pending = _inquiry(case)
    saved = _saved_case(case)
    if case.storage_available:
        accepted = _accept(case, graph, pending_inquiry=pending, saved_case=saved)
        assert accepted["accepted"] is True
    before = _counts(graph)
    pending["revision"] = 2
    saved["label"] = saved["label"] + "-edited"
    late = _accept(
        case,
        graph,
        pending_inquiry=pending,
        saved_case=saved,
        bound_pending_inquiry=_inquiry(case),
        bound_saved_case_hash=saved_case_hash(_saved_case(case)),
        result_state="stale",
        storage_available=True,
    )
    assert late["accepted"] is False
    assert late["code"] == "stale_result"
    assert late["mutated_graph"] is False
    assert late["mutated_pending_inquiry"] is False
    assert late["mutated_saved_case"] is False
    assert late["candidate_acquisition"]["admitted"] is False
    assert receipt_establishes_durability(late["effect_receipt"]) is False
    assert _counts(graph) == before
    assert pending["revision"] == 2
    assert saved["label"].endswith("-edited")

    active_late = _accept(
        case,
        graph,
        request_id=f"req-{case.label}-inquiry",
        pending_inquiry=pending,
        saved_case=_saved_case(case),
        bound_pending_inquiry=_inquiry(case),
        bound_saved_case_hash=saved_case_hash(_saved_case(case)),
        result_state="active",
        storage_available=case.storage_available,
    )
    if not case.storage_available:
        assert active_late["code"] == "storage_unavailable"
    else:
        assert active_late["code"] == "stale_inquiry"
    assert active_late["mutated_graph"] is False
    assert _counts(graph) == before


@pytest.mark.parametrize("case", meaningful_cases(), ids=lambda case: case.label)
def test_workflow_service_reuses_graph_revision_owner(case):
    graph = KnowledgeGraph(graph_id=f"svc-{case.label}")
    saved = _saved_case(case)
    pending = _inquiry(case)

    class _Phase:
        def get_phase_data(self, _phase, key):
            if key == "knowledge_graph":
                return graph
            if key == "intake_case_file":
                return saved
            return None

    class _Mediator:
        phase_manager = _Phase()
        state = type("State", (), {"username": "synthetic-owner"})()

    service = WorkflowActionService(_Mediator())
    service._interview_meta = {"started": True, "pending_inquiry": pending}
    context = _context(case, graph, operation="ingest_private_evidence")
    result = service.accept_bound_hook_effect(
        context=context,
        source_bindings=_bindings(case),
        legal_context=_legal_context(case),
        request_id=f"svc-{case.label}",
        records=_records(case),
        bound_pending_inquiry=dict(pending),
        bound_saved_case_hash=saved_case_hash(saved),
        storage_available=case.storage_available,
        result_state="cancelled" if case.label == "cancellation" else "active",
    )
    assert result["receipt_is_durable"] is False
    assert result["receipt_is_proof"] is False
    assert result["candidate_acquisition"]["admitted"] is False
    assert result["mutated_pending_inquiry"] is False
    assert result["mutated_saved_case"] is False
    if case.label == "cancellation" or not case.storage_available:
        assert result["accepted"] is False
        assert graph.factual_ledger().get("hook_effect_records") in (None, {})
    else:
        assert result["accepted"] is True
        assert result["effect_receipt"]["accepted_graph_revision"] == context.graph_revision
        again = service.accept_bound_hook_effect(
            context=context,
            source_bindings=_bindings(case),
            legal_context=_legal_context(case),
            request_id=f"svc-{case.label}",
            records=_records(case),
            bound_pending_inquiry=dict(pending),
            bound_saved_case_hash=saved_case_hash(saved),
            storage_available=True,
        )
        assert again["idempotent_replay"] is True
        assert again["effect_receipt"] == result["effect_receipt"]
        assert result["candidate_log_count"] == 1
        assert again["candidate_log_count"] == 1
        stored = graph.factual_ledger()["hook_effect_records"]
        assert len(stored) == 1
        assert _SECRET not in str(stored)
    assert pending == _inquiry(case)
    assert saved == _saved_case(case)
