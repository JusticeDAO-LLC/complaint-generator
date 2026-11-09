"""Narrative capture stays off the structured seven-field answers.

Chat asks for the complaint in plain language first and stores that text on
``original_complaint``. A housing story must not become ``party_name``.
Revisions and file or stdin reads stay on the narrative. Package, API, and
MCP callers share ``run_intake_chat_turn``.
"""

from __future__ import annotations

import importlib
import json
from io import StringIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.complaint_workspace import (
    ORIGINAL_COMPLAINT_SCHEMA,
    ComplaintWorkspaceService,
    namespace_filename,
)
from applications.complaint_workspace_api import attach_complaint_workspace_routes
from complaint_generator.workspace import run_intake_chat_turn
from tests.private_session_assertions import assert_private_session_frame, private_session_path

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

HOUSING = "My landlord evicted me after my accommodation request."
SEVEN_FIELDS = (
    "party_name",
    "opposing_party",
    "protected_activity",
    "adverse_action",
    "timeline",
    "harm",
    "court_header",
)


def _service(tmp_path: Path, *users: str) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase="synthetic-narrative-fixture-passphrase")
    for user_id in users:
        service.ensure_private_case_key(user_id, user_id)
    return _bind_deterministic_interview_backend(service)


def _bind_deterministic_interview_backend(service):
    """Inject only this fixture's backend; preserve the real engine and policy guard."""
    real_factory = service._mediator_for_shared_interview
    def fixture_backend(prompt, complaint_privacy_context=None, **kwargs):
        assert isinstance(complaint_privacy_context, dict)
        return '{"entities":[],"relationships":[]}'
    def factory(user_id, case_id):
        mediator = real_factory(user_id, case_id)
        mediator.backends = [fixture_backend]
        return mediator
    service._mediator_for_shared_interview = factory
    return service


def _assert_narrative_then_name(payload: dict, narrative: str) -> None:
    accepted = payload.get("accepted_answer") or {}
    inquiry = payload.get("inquiry") or {}
    record = payload.get("original_complaint") or {}
    answers = (payload.get("session") or {}).get("intake_answers") or {}
    assert accepted.get("question_id") == "original_complaint"
    assert accepted.get("kind") == "narrative"
    assert accepted.get("answer") == narrative
    assert record.get("schema_version") == ORIGINAL_COMPLAINT_SCHEMA
    assert record.get("text") == narrative
    assert int(record.get("revision") or 0) == 1
    assert answers.get("party_name") in (None, "")
    legacy = payload.get("legacy_inquiry") or {}
    interview = payload.get("interview") or {}
    assert legacy.get("question_id") == "party_name"
    assert legacy.get("kind") == "structured"
    assert inquiry.get("kind") == "graph"
    assert inquiry.get("question_id") == interview["inquiry"]["inquiry_id"]
    assert inquiry.get("revision") == interview["expected_question_revision"]
    assert inquiry.get("question_id") != "original_complaint"


def test_chat_starts_with_plain_language_narrative(tmp_path: Path) -> None:
    service = _service(tmp_path, "narrative-open")
    opening = service.run_intake_chat_turn("narrative-open")
    inquiry = opening.get("inquiry") or {}
    assert inquiry.get("question_id") == "original_complaint"
    assert inquiry.get("kind") == "narrative"
    assert "plain language" in str(opening.get("message") or "")
    assert inquiry.get("question_id") != "party_name"
    assert opening.get("accepted_answer") is None


def test_housing_narrative_never_becomes_party_name(tmp_path: Path) -> None:
    service = _service(tmp_path, "housing-user")
    payload = service.run_intake_chat_turn("housing-user", message=HOUSING)
    _assert_narrative_then_name(payload, HOUSING)
    encoded = private_session_path(tmp_path / "sessions", "housing-user").read_bytes()
    assert_private_session_frame(encoded, HOUSING)
    saved = service.get_session("housing-user")["session"]
    assert saved["intake_answers"].get("party_name") in (None, "")
    assert saved["original_complaint"]["text"] == HOUSING
    assert HOUSING not in json.dumps(saved["intake_answers"])
    history = saved.get("intake_history") or []
    assert [item["question_id"] for item in history] == ["original_complaint"]
    assert history[0]["answer"] == HOUSING


def test_saved_seven_field_session_migrates_without_rewriting_answers(tmp_path: Path) -> None:
    service = _service(tmp_path, "legacy-seven")
    user_id = "legacy-seven"
    answers = {field: f"saved-{field}" for field in SEVEN_FIELDS}
    legacy = {
        "user_id": user_id,
        "case_id": user_id,
        "claim_type": "retaliation",
        "intake_answers": dict(answers),
        "intake_history": [{"question_id": "party_name", "answer": answers["party_name"], "captured_at": "t0"}],
    }
    session_dir = tmp_path / "sessions"
    target = session_dir / namespace_filename(user_id)
    target.write_text(json.dumps(legacy), encoding="utf-8")
    original_bytes = target.read_bytes()
    migrated = service.migrate_legacy_private_session(user_id)
    assert migrated["complete"] is True and migrated["private_session_verified"] is True
    assert migrated["cleanup_performed"] is False and migrated["source_bytes_preserved"] is True

    loaded = service.get_session(user_id)
    session = loaded.get("session") or {}
    assert session.get("intake_answers") == answers
    record = session.get("original_complaint") or {}
    assert record.get("schema_version") == ORIGINAL_COMPLAINT_SCHEMA
    assert record.get("text") == ""
    assert int(record.get("revision") or 0) == 0
    assert record.get("revisions") == []
    assert session.get("intake_session_schema") == "complaint-generator.intake-session.v2"
    assert (session.get("intake_answers") or {}).get("party_name") == "saved-party_name"
    follow = service.run_intake_chat_turn(user_id)
    assert (follow.get("inquiry") or None) is None
    assert "saturation" in str(follow.get("message") or "").lower()
    assert follow["legal_sufficiency"] is False
    assert follow["stopping_policy"]["legal_sufficiency"] is False
    assert target.read_bytes() == original_bytes
    successor = target.with_name(target.name + ".cgpe").read_bytes()
    assert_private_session_frame(successor, "saved-party_name")
    persisted = service.get_session(user_id)["session"]
    assert persisted["intake_answers"] == answers
    assert persisted["original_complaint"]["text"] == ""


def test_multiline_answer_revisions_stay_distinct(tmp_path: Path) -> None:
    service = _service(tmp_path, "revision-user")
    user_id = "revision-user"
    narrative = "Line one of the complaint.\nLine two stays in the narrative."
    first = service.run_intake_chat_turn(user_id, message=narrative)
    assert (first.get("original_complaint") or {}).get("text") == narrative
    named = service.run_intake_chat_turn(user_id, message="Jordan Example", question_id="party_name")
    assert (named.get("accepted_answer") or {}).get("question_id") == "party_name"
    assert (named.get("original_complaint") or {}).get("text") == narrative
    assert int((named.get("original_complaint") or {}).get("revision") or 0) == 1
    revised = service.run_intake_chat_turn(
        user_id,
        message="Line one revised.\nLine two revised.",
        question_id="original_complaint",
    )
    record = revised.get("original_complaint") or {}
    assert record.get("text") == "Line one revised.\nLine two revised."
    assert int(record.get("revision") or 0) == 2
    revisions = list(record.get("revisions") or [])
    assert [item.get("text") for item in revisions] == [
        narrative,
        "Line one revised.\nLine two revised.",
    ]
    answers = (revised.get("session") or {}).get("intake_answers") or {}
    assert answers.get("party_name") == "Jordan Example"
    assert "Line one" not in str(answers.get("party_name") or "")
    history = (revised.get("session") or {}).get("intake_history") or []
    assert [item.get("question_id") for item in history] == ["original_complaint", "party_name", "original_complaint"]
    assert [item["answer"] for item in history] == [narrative, "Jordan Example", record["text"]]
    assert (revised.get("legacy_inquiry") or {}).get("question_id") == "opposing_party"
    assert revised["inquiry"]["question_id"] == revised["interview"]["inquiry"]["inquiry_id"]
    assert revised["inquiry"]["revision"] == revised["interview"]["expected_question_revision"]


def test_file_and_stdin_narrative_does_not_run_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    workspace = importlib.import_module("applications.complaint_workspace")
    monkeypatch.setattr(workspace, "_SESSION_DIR", session_dir)
    cli = importlib.import_module("applications.complaint_cli")
    read_original_complaint_input = cli.read_original_complaint_input
    story = tmp_path / "story.txt"
    story.write_text("alpha line\nbeta line\n", encoding="utf-8")
    piped = StringIO(f"@{story}\nJordan Example\n")
    loaded = read_original_complaint_input(piped, interactive=False)
    assert loaded == "alpha line\nbeta line"
    assert piped.readline() == "Jordan Example\n"

    block = StringIO("first paragraph\nsecond paragraph\n.\nnext structured answer\n")
    assert read_original_complaint_input(block, interactive=False) == "first paragraph\nsecond paragraph"
    assert block.readline() == "next structured answer\n"

    continued = StringIO("kept line\\\nnext line\n")
    assert read_original_complaint_input(continued, interactive=True) == "kept line\nnext line"

    marker = tmp_path / "pwned-by-narrative"
    injection = f"@$(touch {marker})"
    with pytest.raises(ValueError):
        read_original_complaint_input(StringIO(injection + "\n"), interactive=False)
    assert marker.exists() is False
    semicolon = tmp_path / "semicolon-marker"
    with pytest.raises(ValueError):
        read_original_complaint_input(
            StringIO(f"@/tmp/no-such-narrative; touch {semicolon}\n"),
            interactive=False,
        )
    assert semicolon.exists() is False


def test_package_api_and_mcp_share_narrative_transition(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    service = _service(tmp_path, "package-user", "mcp-user", "api-user")
    package_turn = run_intake_chat_turn("package-user", message=HOUSING, service=service)
    _assert_narrative_then_name(package_turn, HOUSING)

    opening = service.call_mcp_tool("complaint.run_intake_chat_turn", {"user_id": "mcp-user"})
    assert (opening.get("inquiry") or {}).get("question_id") == "original_complaint"
    mcp_turn = service.call_mcp_tool(
        "complaint.run_intake_chat_turn",
        {"user_id": "mcp-user", "message": HOUSING},
    )
    _assert_narrative_then_name(mcp_turn, HOUSING)

    app = FastAPI()
    attach_complaint_workspace_routes(app, service, trusted_local=True)
    client = TestClient(app)
    response = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": "api-user", "message": HOUSING},
    )
    assert response.status_code == 200
    _assert_narrative_then_name(response.json(), HOUSING)
