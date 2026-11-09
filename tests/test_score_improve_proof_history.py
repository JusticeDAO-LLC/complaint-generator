"""Tests for the score_draft_quality MCP tool, improve_draft MCP tool,
get_proof_history MCP tool, proof-history persistence, and the wired quality
score in get_client_release_gate.

All tests are offline and do not require a running LLM, IPFS daemon, or
network connection.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# Make sure the repo root is on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_DRAFT_BODY = (
    "Plaintiff hereby alleges that Defendant violated 42 U.S.C. § 1983 by "
    "depriving Plaintiff of constitutionally protected rights under color of law. "
    "The acts described herein occurred on January 15, 2024. "
    "Plaintiff suffered compensatory damages as a direct result."
)

_MINIMAL_PROOF_REPORT: Dict[str, Any] = {
    "proof_status": "passed",
    "contradiction_count": 0,
    "chronology_blocked": False,
    "ungrounded_assertions": [],
    "ungrounded_assertion_count": 0,
    "corpus_coverage_percent": 90,
    "norms": [],
    "policy_violations": [],
    "policy_warnings": [],
    "has_blockers": False,
    "predicate_count": 4,
    "theorem_export": {
        "lean4": "namespace CP axiom H1 end CP",
        "coq": "Module CP Hypothesis H1 End CP.",
        "tdfol_formula_count": 2,
        "dcec_formula_count": 1,
    },
    "pipeline_version": "draft-logic-pipeline-v1",
    "errors": [],
}

_BLOCKED_PROOF_REPORT: Dict[str, Any] = {
    "proof_status": "needs_review",
    "contradiction_count": 2,
    "chronology_blocked": True,
    "ungrounded_assertions": [
        {"assertion_id": "sent-1", "text": "Defendant violated 42 USC §1983."},
    ],
    "ungrounded_assertion_count": 1,
    "corpus_coverage_percent": 20,
    "norms": [{"norm_type": "prohibition", "formula": "F(a,b)", "trigger_keyword": "violate"}],
    "policy_violations": [{"violation_type": "prohibition_violation", "offending_sentence": "violated"}],
    "policy_warnings": [],
    "has_blockers": True,
    "predicate_count": 3,
    "theorem_export": {},
    "pipeline_version": "draft-logic-pipeline-v1",
    "errors": ["constrain_assertions_to_corpus: timeout"],
}


def _make_service(draft_body: Optional[str] = _SAMPLE_DRAFT_BODY) -> Any:
    """Return a fresh ComplaintWorkspaceService backed by a tmp directory."""
    from applications.complaint_workspace import ComplaintWorkspaceService

    tmp = tempfile.mkdtemp(prefix="cw_test_")
    svc = ComplaintWorkspaceService(root_dir=Path(tmp))
    if draft_body:
        state = svc._load_state("test-user")
        state["draft"] = {"body": draft_body, "title": "Test Complaint"}
        state["intake_answers"] = {"state": "CA"}
        svc._save_state(state)
    return svc


# ---------------------------------------------------------------------------
# _persist_proof_run
# ---------------------------------------------------------------------------


def test_persist_proof_run_appends_entry():
    from applications.complaint_workspace import ComplaintWorkspaceService

    svc = _make_service()
    state = svc._load_state("test-user")
    svc._persist_proof_run(state, proof_report=_MINIMAL_PROOF_REPORT, quality_score=None)
    assert len(state["proof_history"]) == 1
    entry = state["proof_history"][0]
    assert entry["proof_status"] == "passed"
    assert entry["contradiction_count"] == 0
    assert "run_at" in entry


def test_persist_proof_run_includes_quality_score_when_provided():
    svc = _make_service()
    state = svc._load_state("test-user")
    qscore = {"overall_score": 85, "grade": "B", "dimensions": {"corpus_grounding": 90}}
    svc._persist_proof_run(state, proof_report=_MINIMAL_PROOF_REPORT, quality_score=qscore)
    entry = state["proof_history"][0]
    assert entry["overall_score"] == 85
    assert entry["grade"] == "B"


def test_persist_proof_run_caps_at_max_entries():
    from applications.complaint_workspace import ComplaintWorkspaceService

    svc = _make_service()
    state = svc._load_state("test-user")
    for _ in range(ComplaintWorkspaceService._PROOF_HISTORY_MAX_ENTRIES + 5):
        svc._persist_proof_run(state, proof_report=_MINIMAL_PROOF_REPORT, quality_score=None)
    assert len(state["proof_history"]) == ComplaintWorkspaceService._PROOF_HISTORY_MAX_ENTRIES


# ---------------------------------------------------------------------------
# score_draft_quality MCP tool
# ---------------------------------------------------------------------------


def test_score_draft_quality_no_draft():
    svc = _make_service(draft_body=None)
    result = svc.score_draft_quality("test-user")
    assert result["status"] == "no_draft"
    assert result["quality_score"] is None


def test_score_draft_quality_returns_ok_with_draft(monkeypatch):
    svc = _make_service()

    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_MINIMAL_PROOF_REPORT),
    )

    result = svc.score_draft_quality("test-user")
    assert result["status"] == "ok"
    assert result["quality_score"] is not None
    assert "overall_score" in result["quality_score"]
    assert "grade" in result["quality_score"]


def test_score_draft_quality_persists_to_history(monkeypatch):
    svc = _make_service()

    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_MINIMAL_PROOF_REPORT),
    )

    svc.score_draft_quality("test-user", persist=True)
    state = svc._load_state("test-user")
    assert len(state.get("proof_history") or []) == 1


def test_score_draft_quality_persist_false_does_not_mutate_history(monkeypatch):
    svc = _make_service()

    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_MINIMAL_PROOF_REPORT),
    )

    svc.score_draft_quality("test-user", persist=False)
    state = svc._load_state("test-user")
    assert len(state.get("proof_history") or []) == 0


def test_score_draft_quality_mcp_tool_dispatch(monkeypatch):
    svc = _make_service()

    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_MINIMAL_PROOF_REPORT),
    )

    result = svc.call_mcp_tool("complaint.score_draft_quality", {"user_id": "test-user"})
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# improve_draft MCP tool
# ---------------------------------------------------------------------------


def test_improve_draft_no_draft():
    svc = _make_service(draft_body=None)
    result = svc.improve_draft("test-user")
    assert result["status"] == "no_draft"
    assert result["improved"] is False


def test_improve_draft_no_suggestions_when_perfect(monkeypatch):
    """A perfect proof report produces no suggestions → no LLM calls needed."""
    svc = _make_service()

    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_MINIMAL_PROOF_REPORT),
    )

    result = svc.improve_draft("test-user")
    assert result["status"] == "ok"
    assert isinstance(result["improved"], bool)
    assert isinstance(result["applied_suggestions"], list)


def test_improve_draft_applies_llm_for_high_priority_suggestions(monkeypatch):
    """When there are high-priority suggestions the LLM should be called."""
    svc = _make_service()

    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_BLOCKED_PROOF_REPORT),
    )

    llm_calls: List[str] = []

    def _fake_generate(prompt, **kwargs):
        llm_calls.append(prompt)
        return {"text": "Revised paragraph text that is longer than fifty characters total here."}

    monkeypatch.setattr(
        "integrations.ipfs_datasets.llm.generate_text_with_metadata",
        _fake_generate,
    )

    result = svc.improve_draft("test-user", max_suggestions=2)
    assert result["status"] == "ok"
    # Blocked report → at least one high-priority suggestion → at least one LLM call.
    assert len(llm_calls) >= 1
    assert result["improved"] is True
    assert len(result["applied_suggestions"]) >= 1


def test_improve_draft_persists_improved_body(monkeypatch):
    """After improvement the draft body should be updated in state."""
    svc = _make_service()

    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_BLOCKED_PROOF_REPORT),
    )

    revised_text = "Improved draft body text that is definitely more than fifty characters long for the test."

    def _fake_generate(prompt, **kwargs):
        return {"text": revised_text}

    monkeypatch.setattr(
        "integrations.ipfs_datasets.llm.generate_text_with_metadata",
        _fake_generate,
    )

    result = svc.improve_draft("test-user", max_suggestions=1)
    if result["improved"]:
        state = svc._load_state("test-user")
        draft_body = str(state.get("draft", {}).get("body") or "")
        assert len(draft_body) > 0


def test_improve_draft_tolerates_llm_error(monkeypatch):
    """If the LLM raises an exception the call should return without raising."""
    svc = _make_service()

    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_BLOCKED_PROOF_REPORT),
    )

    def _failing_generate(prompt, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(
        "integrations.ipfs_datasets.llm.generate_text_with_metadata",
        _failing_generate,
    )

    result = svc.improve_draft("test-user")
    assert result["status"] == "ok"
    assert result["improved"] is False
    assert len(result["llm_errors"]) >= 1


def test_improve_draft_mcp_tool_dispatch(monkeypatch):
    svc = _make_service()

    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_MINIMAL_PROOF_REPORT),
    )

    result = svc.call_mcp_tool("complaint.improve_draft", {"user_id": "test-user"})
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# get_proof_history MCP tool
# ---------------------------------------------------------------------------


def test_get_proof_history_empty():
    svc = _make_service()
    result = svc.get_proof_history("test-user")
    assert result["status"] == "ok"
    assert result["history"] == []
    assert result["run_count"] == 0
    assert result["trend"] is None
    assert result["latest"] is None


def test_get_proof_history_single_entry(monkeypatch):
    svc = _make_service()

    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_MINIMAL_PROOF_REPORT),
    )
    svc.score_draft_quality("test-user", persist=True)

    result = svc.get_proof_history("test-user")
    assert result["run_count"] == 1
    assert result["latest"] is not None
    assert result["latest"]["proof_status"] == "passed"


def test_get_proof_history_trend_values(monkeypatch):
    svc = _make_service()

    # First run — low quality score via blocked report.
    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_BLOCKED_PROOF_REPORT),
    )
    svc.score_draft_quality("test-user", persist=True)

    # Second run — high quality score via passed report.
    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_MINIMAL_PROOF_REPORT),
    )
    svc.score_draft_quality("test-user", persist=True)

    result = svc.get_proof_history("test-user")
    assert result["run_count"] == 2
    assert result["trend"] in {"improving", "stable", "declining"}


def test_get_proof_history_returns_required_fields():
    svc = _make_service()
    state = svc._load_state("test-user")
    svc._persist_proof_run(
        state,
        proof_report=_MINIMAL_PROOF_REPORT,
        quality_score={"overall_score": 82, "grade": "B", "dimensions": {}},
    )
    svc._save_state(state)
    result = svc.get_proof_history("test-user")
    entry = result["latest"]
    assert "run_at" in entry
    assert "proof_status" in entry
    assert "contradiction_count" in entry
    assert "overall_score" in entry
    assert "grade" in entry


def test_get_proof_history_mcp_tool_dispatch():
    svc = _make_service()
    result = svc.call_mcp_tool("complaint.get_proof_history", {"user_id": "test-user"})
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# get_client_release_gate — proof quality integration
# ---------------------------------------------------------------------------


def test_release_gate_includes_proof_quality_key(monkeypatch):
    svc = _make_service()

    import applications.complaint_workspace as _ws_mod

    monkeypatch.setattr(
        _ws_mod,
        "_build_local_client_release_gate_for_state",
        lambda state, review: {"verdict": "pass", "reason": ""},
    )

    result = svc.get_client_release_gate("test-user")
    assert "proof_quality" in result
    pq = result["proof_quality"]
    assert "overall_score" in pq
    assert "grade" in pq
    assert "has_blockers" in pq
    assert "proof_status" in pq


def test_release_gate_no_history_proof_quality_is_null(monkeypatch):
    svc = _make_service()

    import applications.complaint_workspace as _ws_mod

    monkeypatch.setattr(
        _ws_mod,
        "_build_local_client_release_gate_for_state",
        lambda state, review: {"verdict": "pass", "reason": ""},
    )

    result = svc.get_client_release_gate("test-user")
    pq = result["proof_quality"]
    assert pq["overall_score"] is None
    assert pq["has_blockers"] is False


def test_release_gate_proof_blockers_in_blockers_list(monkeypatch):
    """A proof-quality run with has_blockers=True should surface in blockers."""
    svc = _make_service()
    state = svc._load_state("test-user")
    state["proof_history"] = [
        {
            "run_at": "2024-01-01T00:00:00+00:00",
            "proof_status": "needs_review",
            "contradiction_count": 2,
            "has_blockers": True,
            "overall_score": 30,
            "grade": "F",
            "dimensions": {},
            "pipeline_errors": [],
        }
    ]
    svc._save_state(state)

    import applications.complaint_workspace as _ws_mod

    monkeypatch.setattr(
        _ws_mod,
        "_build_local_client_release_gate_for_state",
        lambda state, review: {"verdict": "warning", "reason": ""},
    )

    result = svc.get_client_release_gate("test-user")
    blockers = result["blockers"]
    assert any(
        "proof" in b.lower() or "quality" in b.lower() or "contradict" in b.lower()
        for b in blockers
    )


def test_release_gate_score_incorporates_proof_quality(monkeypatch):
    """Score with a very low proof quality should be ≤ score with no history."""
    svc_no_history = _make_service()
    svc_low_quality = _make_service()

    import applications.complaint_workspace as _ws_mod

    monkeypatch.setattr(
        _ws_mod,
        "_build_local_client_release_gate_for_state",
        lambda state, review: {"verdict": "warning", "reason": ""},
    )

    result_no_history = svc_no_history.get_client_release_gate("test-user")
    score_no_history = result_no_history["score"]

    state = svc_low_quality._load_state("test-user")
    state["proof_history"] = [
        {
            "run_at": "2024-01-01T00:00:00+00:00",
            "proof_status": "needs_review",
            "contradiction_count": 3,
            "has_blockers": True,
            "overall_score": 10,
            "grade": "F",
            "dimensions": {},
            "pipeline_errors": [],
        }
    ]
    svc_low_quality._save_state(state)
    result_low = svc_low_quality.get_client_release_gate("test-user")
    score_low = result_low["score"]

    assert score_low <= score_no_history


# ---------------------------------------------------------------------------
# get_draft_proof_report persists to proof history
# ---------------------------------------------------------------------------


def test_get_draft_proof_report_persists_history(monkeypatch):
    svc = _make_service()

    monkeypatch.setattr(
        "applications.complaint_workspace._run_draft_logic_pipeline_safely",
        lambda body, state=None: dict(_MINIMAL_PROOF_REPORT),
    )

    result = svc.call_mcp_tool("complaint.get_draft_proof_report", {"user_id": "test-user"})
    assert result.get("status") == "ok"
    state = svc._load_state("test-user")
    assert len(state.get("proof_history") or []) >= 1


# ---------------------------------------------------------------------------
# MCP tool list includes new tools
# ---------------------------------------------------------------------------


def test_new_tools_in_mcp_tool_list():
    svc = _make_service(draft_body=None)
    tools = svc.list_mcp_tools()
    tool_names = {t["name"] for t in tools.get("tools") or []}
    assert "complaint.score_draft_quality" in tool_names
    assert "complaint.improve_draft" in tool_names
    assert "complaint.get_proof_history" in tool_names
