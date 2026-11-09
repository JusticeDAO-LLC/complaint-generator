"""Terminal /edit uses the public factual correction.

Synthetic private fixtures only. No test is skipped. /edit corrects the last
eligible accepted answer on the shared graph and keeps the previous assertion
and history line. An unrelated pending question stays pending. A pending
question bound to that answer is reopened. A stale revision is refused.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService
from complaint_phases.dependency_graph import DependencyGraph
from complaint_phases.knowledge_graph import Entity, KnowledgeGraph, Relationship
from integrations.ipfs_datasets.types import build_user_assertion_envelope, source_byte_hash
from mediator.hook_runtime import graph_revision_token


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_OWNER = "mgnd12-owner"
_PASSPHRASE = "synthetic-passphrase-mgnd12"
_CASES = (
    {
        "label": "date-correction",
        "original": "I was fired on January 1, 2020.",
        "replacement": "I was fired on January 2, 2020.",
        "pending": "unrelated",
    },
    {
        "label": "party-correction",
        "original": "Alex ended the warehouse job.",
        "replacement": "Riley ended the warehouse job.",
        "pending": "unrelated",
    },
    {
        "label": "skip-does-not-hide-prior-answer",
        "original": "The meeting was on March 3, 2024.",
        "replacement": "The meeting was on March 4, 2024.",
        "pending": "affected",
        "trailing_skip": True,
    },
)


def _envelope(text: str, message_id: str):
    return build_user_assertion_envelope(
        source_text=text,
        source_kind="user_statement",
        source_id=message_id,
        message_id=message_id,
        assertion_status="asserted",
        extractor_version="mgnd12-test",
        source_hash=source_byte_hash(text),
        source_span={"start": 0, "end": len(text.encode("utf-8")), "text": text, "unit": "byte"},
        subject_key="employment-fact",
    )


def _service(root: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root)
    created = service.initialize_private_keys(protection="passphrase", passphrase=_PASSPHRASE)
    assert created.get("unlocked") is True or created.get("status") in {"available", "ready"}
    unlocked = service.unlock_private_keys(passphrase=_PASSPHRASE)
    assert unlocked.get("awaiting_user") is not True
    assert service.ensure_private_case_key(_OWNER, _OWNER).get("data_key_id")
    return service


def _graph(case: dict, case_id: str):
    graph = KnowledgeGraph()
    original = case["original"]
    envelope = _envelope(original, f"msg-{case['label']}")
    fact = Entity(
        id="fact-accepted",
        type="fact",
        name=original,
        attributes={"description": original, "fact_type": "timeline"},
        confidence=0.4,
        source="complaint",
        provenance={"user_assertion": envelope.as_dict()},
    )
    claim = Entity(
        id="claim-1",
        type="claim",
        name="Termination",
        attributes={"claim_type": "employment"},
        confidence=0.8,
    )
    graph.add_entity(claim)
    graph.add_entity(fact)
    graph.register_assertion(fact, envelope, status="active", event_id=f"answer-{case['label']}")
    graph.add_relationship(Relationship(
        id="rel-support",
        source_id=fact.id,
        target_id=claim.id,
        relation_type="supports",
        attributes={},
        confidence=0.9,
    ))
    graph.metadata["case_id"] = case_id
    graph.append_revision({
        "action": "answer",
        "event_id": f"answer-{case['label']}",
        "statement": original,
        "stable_id": envelope.stable_id,
        "entity_id": fact.id,
        "value_status": "stated",
        "audit_retained": True,
    })
    if case.get("pending") == "affected":
        graph.register_inquiry_target(
            inquiry_id="inq-pending",
            entity_id=fact.id,
            stable_id=envelope.stable_id,
            question="What date should the accepted answer use?",
        )
    return graph, fact, envelope


def _pending(case: dict, fact_id: str) -> dict:
    if case.get("pending") == "affected":
        target_id = fact_id
        question = "What date should the accepted answer use?"
        objective = "fact-date"
    else:
        target_id = "witness-gap"
        question = "Who else was present?"
        objective = "witnesses"
    return {
        "inquiry_id": "inq-pending",
        "revision": 4,
        "question": question,
        "question_type": "clarification",
        "kind": "graph",
        "objective_id": objective,
        "target_id": target_id,
        "target_revision": "1",
        "why_it_matters": "The pending question is separate from a display edit.",
        "legal_sufficiency": False,
    }


def _seed(service: ComplaintWorkspaceService, case: dict) -> dict:
    graph, fact, envelope = _graph(case, _OWNER)
    pending = _pending(case, fact.id)
    history = [{
        "question_id": "inq-accepted",
        "answer": case["original"],
        "disposition": "accepted",
        "target_stable_id": envelope.stable_id,
        "audit_id": f"audit-{case['label']}",
        "captured_at": "2026-01-01T00:00:00Z",
    }]
    if case.get("trailing_skip"):
        history.append({
            "question_id": "inq-pending",
            "answer": "skipped",
            "disposition": "skipped",
            "satisfies_requirement": False,
            "audit_id": f"skip-{case['label']}",
        })
    projection = {
        "schema_version": "shared-interview-session-v1",
        "contract_version": "interview-transition-v1",
        "session_id": f"interview-{case['label']}",
        "session_revision": 2,
        "phase": "intake",
        "narrative_extraction_count": 1,
        "question_revision": 4,
        "pending_inquiry": pending,
        "answered_inquiries": [{"inquiry_id": "inq-accepted", "revision": 3}],
        "unknown_reasons": [],
        "unavailable_reasons": [],
        "capped_reasons": [],
        "legal_sufficiency": False,
        "knowledge_graph": graph.to_dict(),
        "dependency_graph": DependencyGraph().to_dict(),
        "denoiser_history": [],
        "iteration_count": 1,
        "loss_history": [],
        "phase_history": [],
        "intake_case_file": {"canonical_facts": [], "candidate_claims": []},
        "current_questions": [{
            "type": "clarification",
            "question": pending["question"],
            "inquiry_id": pending["inquiry_id"],
            "target_id": pending["target_id"],
            "objective_id": pending["objective_id"],
            "context": {},
        }],
        "question_candidates": [],
    }
    state = service._load_state(_OWNER)
    state["case_id"] = _OWNER
    state["privacy_notice_shown"] = True
    state["original_complaint"] = {"text": "Synthetic narrative that is not the edited answer.", "revision": 1, "revisions": []}
    state["intake_answers"] = {"inq-accepted": case["original"], "unrelated_note": "kept"}
    state["intake_history"] = history
    state["shared_interview"] = projection
    service._save_state(state)
    return {
        "token": graph_revision_token(graph),
        "stable_id": envelope.stable_id,
        "audit_id": history[0]["audit_id"],
        "pending": pending,
        "session_revision": 2,
    }


def _session(service: ComplaintWorkspaceService) -> dict:
    payload = service.get_session(_OWNER)
    session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    return session


def _graph_from(session: dict) -> KnowledgeGraph:
    projection = session.get("shared_interview") if isinstance(session.get("shared_interview"), dict) else {}
    return KnowledgeGraph.from_dict(projection.get("knowledge_graph") or {})


def test_module_collects_meaningful_cases_without_required_skips():
    assert _CASES
    assert len({item["label"] for item in _CASES}) == len(_CASES)
    assert all(item["original"].strip() and item["replacement"].strip() for item in _CASES)
    assert {item["pending"] for item in _CASES} >= {"unrelated", "affected"}
    assert any(item.get("trailing_skip") for item in _CASES)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["label"])
def test_edit_updates_shared_graph_and_keeps_audit_lineage(tmp_path: Path, case: dict):
    service = _service(tmp_path / "sessions")
    seeded = _seed(service, case)
    before_history = list(_session(service).get("intake_history") or [])
    receipt = service.apply_terminal_graph_edit(
        _OWNER,
        case["replacement"],
        expected_graph_revision=seeded["token"],
        expected_session_revision=seeded["session_revision"],
    )
    assert receipt["status"] == "applied"
    assert receipt["display_only"] is False
    assert receipt["legal_sufficiency"] is False
    assert receipt["worker_stalled"] is False
    assert "Edited the last recorded answer." in receipt["message"]
    session = _session(service)
    graph = _graph_from(session)
    previous = graph.assertion_state(seeded["stable_id"])
    assert previous["status"] == "superseded"
    assert previous["envelope"]["source_text"] == case["original"]
    assert previous["envelope"]["source_identity"] == f"msg-{case['label']}"
    replacement_state = graph.assertion_state(receipt["correction"]["replacement_stable_id"])
    assert replacement_state["status"] == "active"
    assert replacement_state["envelope"]["source_text"] == case["replacement"]
    assert receipt["graph_revision"] == graph_revision_token(graph)
    assert receipt["graph_revision"] != seeded["token"]
    assert receipt["session_revision"] == seeded["session_revision"] + 1
    answers = session.get("intake_answers") or {}
    assert answers["inq-accepted"] == case["replacement"]
    assert answers["unrelated_note"] == "kept"
    history = session.get("intake_history") or []
    assert history[0]["answer"] == case["original"]
    assert history[0]["audit_id"] == seeded["audit_id"]
    assert history[:len(before_history)] == before_history
    assert history[-1]["disposition"] == "corrected"
    assert history[-1]["answer"] == case["replacement"]
    assert history[-1]["display_only"] is False
    pending = (session.get("shared_interview") or {}).get("pending_inquiry") or {}
    if case.get("pending") == "affected":
        assert receipt["pending_reselected"] is True
        assert pending.get("reopened") is True
        assert pending.get("inquiry_id") == "inq-pending"
        assert int(pending.get("revision") or 0) == 5
    else:
        assert receipt["pending_reselected"] is False
        assert pending.get("question") == seeded["pending"]["question"]
        assert pending.get("target_id") == "witness-gap"
        assert pending.get("revision") == 4
        assert "unchanged" in receipt["message"]


def test_chat_edit_command_uses_the_public_correction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    case = _CASES[0]
    root = tmp_path / "sessions"
    service = _service(root)
    seeded = _seed(service, case)
    import applications.complaint_cli as cli

    monkeypatch.setattr(cli, "service", service)
    monkeypatch.setattr(sys, "stdin", io.StringIO("/edit " + case["replacement"] + "\n"))
    with pytest.raises(SystemExit) as exited:
        cli.chat(user_id=_OWNER, max_turns=0, privacy_mode="local")
    assert exited.value.code == 1
    transcript = capsys.readouterr().out
    assert "Edited the last recorded answer." in transcript
    assert "The pending question is unchanged." in transcript
    session = _session(service)
    graph = _graph_from(session)
    assert graph.assertion_state(seeded["stable_id"])["status"] == "superseded"
    assert case["replacement"] in {
        str((graph.assertion_state(stable).get("envelope") or {}).get("source_text") or "")
        for stable, record in graph.factual_ledger()["assertion_states"].items()
        if isinstance(record, dict) and record.get("status") == "active"
    }
    assert (session.get("intake_answers") or {})["inq-accepted"] == case["replacement"]
    assert (session.get("intake_history") or [])[0]["answer"] == case["original"]
    pending = (session.get("shared_interview") or {}).get("pending_inquiry") or {}
    assert pending.get("inquiry_id") == "inq-pending"
    assert pending.get("target_id") == "witness-gap"


def test_stale_concurrent_edit_is_refused(tmp_path: Path):
    case = _CASES[1]
    service = _service(tmp_path / "sessions")
    seeded = _seed(service, case)
    before = _session(service)
    receipt = service.apply_terminal_graph_edit(
        _OWNER,
        case["replacement"],
        expected_graph_revision="gr_stale",
        expected_session_revision=seeded["session_revision"],
    )
    assert receipt["status"] == "refused"
    assert receipt["error"]["code"] == "stale_target"
    assert "Stale concurrent edit rejected" in receipt["message"]
    after = _session(service)
    assert after.get("intake_answers") == before.get("intake_answers")
    assert after.get("intake_history") == before.get("intake_history")
    assert graph_revision_token(_graph_from(after)) == seeded["token"]
    assert _graph_from(after).assertion_state(seeded["stable_id"])["status"] == "active"


def test_encrypted_cold_resume_sees_corrected_graph_and_lineage(tmp_path: Path):
    case = _CASES[0]
    root = tmp_path / "sessions"
    service = _service(root)
    seeded = _seed(service, case)
    applied = service.apply_terminal_graph_edit(
        _OWNER,
        case["replacement"],
        expected_graph_revision=seeded["token"],
        expected_session_revision=seeded["session_revision"],
    )
    assert applied["status"] == "applied"
    restarted = ComplaintWorkspaceService(root)
    assert restarted is not service
    unlocked = restarted.unlock_private_keys(passphrase=_PASSPHRASE)
    assert unlocked.get("awaiting_user") is not True
    resumed = restarted.run_intake_chat_turn(_OWNER, interview_action="resume")
    session = resumed.get("session") if isinstance(resumed.get("session"), dict) else {}
    graph = _graph_from(session)
    previous = graph.assertion_state(seeded["stable_id"])
    assert previous["status"] == "superseded"
    assert previous["envelope"]["source_text"] == case["original"]
    active_text = {
        str((graph.assertion_state(stable).get("envelope") or {}).get("source_text") or "")
        for stable in graph.factual_ledger()["assertion_states"]
    }
    assert case["replacement"] in active_text
    assert (session.get("intake_answers") or {})["inq-accepted"] == case["replacement"]
    history = session.get("intake_history") or []
    assert history[0]["answer"] == case["original"]
    assert history[0]["audit_id"] == seeded["audit_id"]
    assert history[-1]["answer"] == case["replacement"]
    pending = (session.get("shared_interview") or {}).get("pending_inquiry") or {}
    assert pending.get("question") == "Who else was present?"
    assert pending.get("target_id") == "witness-gap"


def test_missing_session_stays_unavailable_without_a_display_edit(tmp_path: Path):
    service = _service(tmp_path / "sessions")
    state = service._load_state(_OWNER)
    state["case_id"] = _OWNER
    state["intake_answers"] = {}
    state["intake_history"] = []
    service._save_state(state)
    receipt = service.apply_terminal_graph_edit(_OWNER, "A later date that must not be stored.")
    assert receipt["status"] == "unavailable"
    assert receipt["error"]["code"] == "session_missing"
    assert receipt["worker_stalled"] is False
    assert receipt["display_only"] is False
    session = _session(service)
    assert session.get("intake_answers") in ({}, None) or session.get("intake_answers") == {}
    assert "A later date that must not be stored." not in str(session.get("intake_history"))
    assert not (session.get("shared_interview") or {})
