"""One-gap terminal intake: encrypted save, exit, and resume.

The scripted user answers a single open legal gap, then the process drops
its memory and reloads the sealed snapshot before the next question.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from applications.cli import CLI
from integrations.ipfs_datasets.storage import InterviewSnapshotError, run_one_gap_intake

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

COMPLAINT = "SYNTHETIC-DUR006-COMPLAINT the assignment ended."
KEY = bytes(range(4, 36))
KEY_ID = "dur006-interview-key"
IDENTITY = {
    "protection": "user_chosen_encrypted",
    "tenant_id": "dur006-tenant",
    "case_id": "dur006-case",
    "principal_id": "dur006-tenant",
}


def _run(directory: Path, **kwargs):
    return run_one_gap_intake(
        directory,
        key=KEY,
        key_id=KEY_ID,
        complaint_text=COMPLAINT,
        **kwargs,
    )


def test_each_turn_answers_one_new_gap_and_resume_keeps_facts(tmp_path: Path) -> None:
    result = _run(tmp_path / "intake", mode="local_private")
    turns = result["turns"]
    assert [turn["field"] for turn in turns] == [
        "jurisdiction",
        "event_date",
        "applicable_law_date",
        "filing_reference_date",
        "claim_candidates",
    ]
    assert len({turn["question_id"] for turn in turns}) == len(turns)
    seen: list[str] = []
    for turn in turns:
        assert turn["fact_ids"] == sorted(set(seen + ["fact-" + turn["field"]]))
        seen = list(turn["fact_ids"])
        assert turn["question_id"] not in (turn["pending_question_id"] or "")
    assert turns[-1]["mapping_status"] == "selected"
    assert turns[0]["mapping_status"] == "unresolved"
    assert result["mapping_status"] == "selected"
    assert result["fact_ids"] == seen
    assert len(result["fact_ids"]) == len(set(result["fact_ids"])) == 5
    graph = result["snapshot"]["graphs"]["knowledge_graph"]["entities"]
    assert graph["jurisdiction"]["value"] == "Oregon"
    assert graph["jurisdiction"]["source_span"] == [0, len("Oregon")]
    node = result["snapshot"]["graphs"]["dependency_graph"]["nodes"]["synthetic-or-wt-1"]
    assert node["applicability"] == "selected"
    assert node["locator"] == "synthetic-local-statute"
    assert result["captures"] == []
    assert COMPLAINT not in json.dumps(result["receipt"])
    for path in (tmp_path / "intake").rglob("*"):
        if path.is_file():
            assert COMPLAINT.encode() not in path.read_bytes()
            assert KEY not in path.read_bytes()


def test_cli_exit_and_fresh_resume_restore_the_pending_gap(tmp_path: Path) -> None:
    directory = tmp_path / "cli"
    result = _run(directory, mode="local_private", turns=2)
    pending = result["turns"][-1]["pending_question_id"]
    assert pending == "legal_context.applicable_law_date"
    assert result["fact_ids"] == ["fact-event_date", "fact-jurisdiction"]

    class _State:
        pass

    class _Mediator:
        pass

    fresh = object.__new__(CLI)
    state = _State()
    state.answered_questions = {}
    state.chat_history = {}
    state.original_complaint = None
    state.complaint_summary = None
    state.complaint = None
    state.current_inquiry = None
    state.username = "dur006-tenant"
    fresh.mediator = _Mediator()
    fresh.mediator.state = state
    fresh.mediator.workflow_actions = None
    fresh._interview_protection = "user_chosen_encrypted"
    fresh._interview_snapshot_dir = str(directory)
    fresh._interview_key = KEY
    fresh._interview_key_id = KEY_ID
    fresh._interview_tenant_id = IDENTITY["tenant_id"]
    fresh._interview_case_id = IDENTITY["case_id"]
    loaded = fresh.resume()
    assert state.original_complaint == COMPLAINT
    assert state.current_inquiry["question_id"] == pending
    entities = loaded["snapshot"]["graphs"]["knowledge_graph"]["entities"]
    assert set(entities) == {"jurisdiction", "event_date"}
    assert loaded["snapshot"]["graphs"]["dependency_graph"]["mapping_status"] == "unresolved"
    again = fresh.resume()
    assert again["snapshot"]["revision"] == loaded["snapshot"]["revision"]
    assert set(again["snapshot"]["graphs"]["knowledge_graph"]["entities"]) == set(entities)


def test_cloud_mode_captures_redacted_grok_and_local_mode_refuses_transport(tmp_path: Path) -> None:
    seen: list[dict] = []

    def transport(payload: dict) -> str:
        seen.append(dict(payload))
        return "synthetic-ok"

    cloud = _run(tmp_path / "cloud", mode="cloud_grok", transport=transport, turns=1)
    assert len(seen) == 1
    assert seen[0]["provider"] == "grok_cli"
    assert seen[0]["model_name"] == "grok-4.7"
    assert seen[0]["allow_local_fallback"] is False
    assert seen[0]["allow_cross_provider_fallback"] is False
    assert COMPLAINT not in seen[0]["prompt"]
    assert cloud["captures"][0]["prompt"] == seen[0]["prompt"]
    assert "gap=legal_context.jurisdiction" in seen[0]["prompt"]
    with pytest.raises(InterviewSnapshotError) as refused:
        _run(tmp_path / "blocked", mode="local_private", transport=transport, turns=1)
    assert refused.value.code == "egress_forbidden"
    assert len(seen) == 1
