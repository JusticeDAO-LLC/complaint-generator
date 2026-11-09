"""Public legal-research action for the current source gap.

Cases are synthetic private fixtures. No test is skipped. /research is a
deliberate terminal and service action. It is not stored as an answer, it
does not run on status or resume, and replaying it does not dispatch again.
Counts stay truthful when acquisition or storage is unavailable.
"""

from __future__ import annotations

import pytest

from applications.complaint_cli import TERMINAL_COMMANDS, _HELP_TEXT, _command_name
from tests.mgnd_fixtures import CASE_LABELS, PASSPHRASE, USER_ID, materialize_case, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_LAW_DATE = "2024-03-15"


def _ready_text(case) -> str:
    text = case.narrative.text
    if case.narrative.jurisdiction == "unknown":
        return text
    return text + " Under Oregon law. Applicable law date: " + _LAW_DATE + "."


def _rows_for(case):
    rows = []
    for source in case.sources:
        rows.append({
            "text": source.source_text,
            "citation": source.citation,
            "uri": "fixture://" + source.authority_id,
            "corpus_version": source.version,
            "jurisdiction": "OR",
            "effective_date": source.effective_date,
        })
    return {"state_statute": rows}


def _seed(service, case) -> None:
    state = service._load_state(USER_ID)
    record = state["original_complaint"]
    record["text"] = _ready_text(case)
    record["revision"] = int(record.get("revision") or 0) + 1
    state["claim_type"] = "termination"
    service._save_state(state)


def _research(service, case, **kwargs):
    if case.label == "cancellation":
        kwargs.setdefault("cancelled", True)
    elif case.label == "storage_outage":
        cache = service._session_dir / "legal-source-cache"
        cache.write_bytes(b"storage-outage")
        kwargs.setdefault("local_rows", _rows_for(case))
    elif case.label != "missing_authority" and case.sources and case.label != "unknown":
        kwargs.setdefault("local_rows", _rows_for(case))
    return service.run_legal_research(USER_ID, **kwargs)


def test_meaningful_cases_are_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id and case.narrative.text for case in cases)


def test_research_command_is_documented_and_is_not_an_answer():
    assert "/research" in TERMINAL_COMMANDS
    assert "/status" in TERMINAL_COMMANDS
    assert "/resume" in TERMINAL_COMMANDS
    assert _command_name("/research") == "/research"
    assert _command_name("/status") == "/status"
    assert "not an answer" in _HELP_TEXT
    assert "prove" not in _HELP_TEXT.lower()


def test_each_case_reports_counts_without_claiming_proof(tmp_path, monkeypatch):
    for case in meaningful_cases():
        materialized = materialize_case(tmp_path / case.label, monkeypatch, case)
        service = materialized.service
        _seed(service, case)
        before = service._load_state(USER_ID)
        answers = dict(before.get("intake_answers") or {})
        history = list(before.get("intake_history") or [])
        receipt = _research(service, case)
        assert receipt["stored_as_answer"] is False
        assert receipt["proves_complaint"] is False
        assert receipt["legal_sufficiency"] is False
        assert receipt["proof"] is False
        assert receipt["worker_stalled"] is False
        counts = receipt["counts"]
        assert set(counts) == {"retrieved", "admitted", "rejected", "unavailable"}
        assert all(isinstance(counts[key], int) and counts[key] >= 0 for key in counts)
        assert receipt["next_action"]
        assert receipt["resumable"] is True or receipt["status"] == "cancelled"
        display = receipt["display"]
        assert f"retrieved={counts['retrieved']}" in display
        assert f"admitted={counts['admitted']}" in display
        assert f"rejected={counts['rejected']}" in display
        assert f"unavailable={counts['unavailable']}" in display
        assert "prove" not in display.lower()
        after = service._load_state(USER_ID)
        assert after.get("intake_answers") == answers
        assert after.get("intake_history") == history
        if case.label == "baseline":
            assert counts["retrieved"] >= 1
            assert counts["admitted"] >= 1
            assert counts["unavailable"] == 0
        elif case.label == "missing_authority":
            assert counts["retrieved"] == 0
            assert counts["admitted"] == 0
            assert counts["unavailable"] >= 1
            assert receipt["status"] == "unavailable"
        elif case.label == "unknown":
            assert counts["admitted"] == 0
            assert receipt["next_action"] == "resolve_legal_context"
        elif case.label == "cancellation":
            assert counts["retrieved"] == 0
            assert counts["admitted"] == 0
            assert receipt["status"] == "cancelled"
            assert receipt["dispatched"] is True
        elif case.label == "storage_outage":
            assert counts["admitted"] == 0
            assert counts["unavailable"] >= 1
            assert receipt["status"] == "unavailable"
        elif case.label == "contradiction":
            assert counts["retrieved"] >= 1
            assert counts["admitted"] + counts["rejected"] + counts["unavailable"] >= 1


def test_replay_status_and_resume_do_not_dispatch_again(tmp_path, monkeypatch):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    materialized = materialize_case(tmp_path, monkeypatch, case)
    service = materialized.service
    _seed(service, case)
    assert int(getattr(service, "_legal_research_dispatch_count", 0) or 0) == 0
    status = service.run_intake_chat_turn(USER_ID, interview_action="status")
    resume = service.run_intake_chat_turn(USER_ID, interview_action="resume")
    assert "legal_research" not in status
    assert "legal_research" not in resume
    assert int(getattr(service, "_legal_research_dispatch_count", 0) or 0) == 0
    first = service.run_intake_chat_turn(USER_ID, message="/research")
    assert first["command"] == "/research"
    assert first["stored_as_answer"] is False
    assert first["legal_research"]["dispatched"] is True
    assert first["legal_research"]["replayed"] is False
    assert "prove" not in str(first.get("message") or "").lower()
    dispatched = int(getattr(service, "_legal_research_dispatch_count", 0) or 0)
    assert dispatched == 1
    status_again = service.run_intake_chat_turn(USER_ID, interview_action="status")
    resume_again = service.run_intake_chat_turn(USER_ID, interview_action="resume")
    assert "legal_research" not in status_again
    assert "legal_research" not in resume_again
    second = service.run_intake_chat_turn(USER_ID, message="/research")
    assert second["legal_research"]["replayed"] is True
    assert second["legal_research"]["dispatched"] is False
    assert second["legal_research"]["counts"] == first["legal_research"]["counts"]
    assert int(getattr(service, "_legal_research_dispatch_count", 0) or 0) == dispatched
    rows = _rows_for(case)
    acquired = service.run_legal_research(USER_ID, local_rows=rows)
    assert acquired["dispatched"] is True
    assert acquired["replayed"] is False
    assert int(getattr(service, "_legal_research_dispatch_count", 0) or 0) == dispatched + 1
    replayed = service.run_legal_research(USER_ID, local_rows=rows)
    assert replayed["replayed"] is True
    assert replayed["dispatched"] is False
    assert replayed["counts"] == acquired["counts"]
    assert int(getattr(service, "_legal_research_dispatch_count", 0) or 0) == dispatched + 1
    terminal = materialized.terminal
    unlocked = terminal.unlock_private_keys(passphrase=PASSPHRASE)
    assert unlocked.get("unlocked") is True
    echoed = terminal.run_intake_chat_turn(USER_ID, message="/research")
    assert echoed["stored_as_answer"] is False
    assert echoed["legal_research"]["replayed"] is True
    assert echoed["legal_research"]["dispatched"] is False
