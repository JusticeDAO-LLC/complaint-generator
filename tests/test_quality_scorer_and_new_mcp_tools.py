"""Tests for the draft quality scorer, MCP proof-report tools, and
legal corpus IPFS streaming backend.

These tests verify structural contracts and graceful degradation; they do not
make network calls or require a running IPFS daemon.
"""

from __future__ import annotations

from typing import Any, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_PASSED_REPORT: Dict[str, Any] = {
    "proof_status": "passed",
    "contradiction_count": 0,
    "chronology_blocked": False,
    "ungrounded_assertions": [],
    "ungrounded_assertion_count": 0,
    "corpus_coverage_percent": 95,
    "norms": [],
    "policy_violations": [],
    "policy_warnings": [],
    "has_blockers": False,
    "predicate_count": 5,
    "theorem_export": {
        "lean4": "namespace CP axiom H1 end CP",
        "coq": "Module CP Hypothesis H1 End CP.",
        "tdfol_formula_count": 3,
        "dcec_formula_count": 2,
    },
    "pipeline_version": "draft-logic-pipeline-v1",
    "errors": [],
}

_BLOCKED_REPORT: Dict[str, Any] = {
    "proof_status": "needs_review",
    "contradiction_count": 2,
    "chronology_blocked": True,
    "ungrounded_assertions": [
        {"assertion_id": "sent-1", "text": "Defendant violated 42 USC §1983."},
        {"assertion_id": "sent-2", "text": "Plaintiff suffered irreparable harm."},
    ],
    "ungrounded_assertion_count": 2,
    "corpus_coverage_percent": 20,
    "norms": [{"norm_type": "prohibition", "formula": "F(actor,action)", "trigger_keyword": "violate"}],
    "policy_violations": [
        {"violation_type": "prohibited_action_found", "offending_sentence": "Defendant violated…"}
    ],
    "policy_warnings": [
        {"warning_type": "obligation_not_satisfied", "formula": "O(actor,action)"}
    ],
    "has_blockers": True,
    "predicate_count": 3,
    "theorem_export": {},
    "pipeline_version": "draft-logic-pipeline-v1",
    "errors": ["text_to_fol: import error"],
}


# ---------------------------------------------------------------------------
# score_draft_quality tests
# ---------------------------------------------------------------------------


def _score(report: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    from integrations.ipfs_datasets.quality import score_draft_quality

    return score_draft_quality(report, **kwargs)


def test_score_returns_required_keys_on_passed_report():
    result = _score(_MINIMAL_PASSED_REPORT)
    required = {"overall_score", "grade", "dimensions", "suggestions", "claim_id", "scorer_version"}
    for key in required:
        assert key in result, f"Missing key: {key}"


def test_score_dimensions_keys():
    result = _score(_MINIMAL_PASSED_REPORT)
    dims = result["dimensions"]
    expected_dims = {
        "corpus_grounding",
        "proof_completeness",
        "policy_compliance",
        "contradiction_free",
        "theorem_readiness",
    }
    for d in expected_dims:
        assert d in dims, f"Missing dimension: {d}"


def test_score_overall_in_range():
    for report in (_MINIMAL_PASSED_REPORT, _BLOCKED_REPORT):
        result = _score(report)
        score = result["overall_score"]
        assert 0 <= score <= 100, f"Score out of range: {score}"


def test_score_grade_valid():
    for report in (_MINIMAL_PASSED_REPORT, _BLOCKED_REPORT):
        result = _score(report)
        assert result["grade"] in ("A", "B", "C", "D", "F"), f"Invalid grade: {result['grade']}"


def test_passed_report_high_score():
    result = _score(_MINIMAL_PASSED_REPORT)
    assert result["overall_score"] >= 70, "Passed report should score at least 70"
    assert result["grade"] in ("A", "B", "C"), "Passed report should get A/B/C grade"


def test_blocked_report_low_score():
    result = _score(_BLOCKED_REPORT)
    assert result["overall_score"] < 70, "Blocked report should score below 70"


def test_blocked_report_has_suggestions():
    result = _score(_BLOCKED_REPORT)
    suggestions = result["suggestions"]
    assert len(suggestions) >= 2, "Blocked report should have at least 2 suggestions"
    priorities = {s["priority"] for s in suggestions}
    assert "high" in priorities, "Should have at least one high-priority suggestion"


def test_suggestions_have_required_fields():
    result = _score(_BLOCKED_REPORT)
    for suggestion in result["suggestions"]:
        assert "priority" in suggestion
        assert "dimension" in suggestion
        assert "action" in suggestion
        assert suggestion["priority"] in ("high", "medium", "low")


def test_claim_id_echoed():
    result = _score(_MINIMAL_PASSED_REPORT, claim_id="case-123")
    assert result["claim_id"] == "case-123"


def test_empty_report_does_not_crash():
    result = _score({})
    assert "overall_score" in result
    assert 0 <= result["overall_score"] <= 100


def test_no_predicate_caps_proof_score():
    report = dict(_MINIMAL_PASSED_REPORT)
    report["predicate_count"] = 0
    result = _score(report)
    assert result["dimensions"]["proof_completeness"] <= 40


def test_contradiction_reduces_score():
    report = dict(_MINIMAL_PASSED_REPORT)
    report["contradiction_count"] = 3
    with_contradictions = _score(report)
    without = _score(_MINIMAL_PASSED_REPORT)
    assert with_contradictions["dimensions"]["contradiction_free"] < without["dimensions"]["contradiction_free"]


def test_fact_registry_summary_scores_corpus_grounding_without_coverage_percent():
    report = {
        "proof_status": "passed",
        "predicate_count": 2,
        "contradiction_count": 0,
        "chronology_blocked": False,
        "theorem_export": {"tdfol_formula_count": 1, "dcec_formula_count": 1, "lean4": "x", "coq": "x"},
        "fact_registry_summary": {
            "fact_count": 2,
            "unique_source_ref_count": 2,
            "passage_anchored_count": 2,
            "source_family_counts": {"evidence": 1, "legal_authority": 1},
        },
    }

    result = _score(report)

    assert result["dimensions"]["corpus_grounding"] >= 80
    assert result["fact_registry_summary"]["source_family_counts"] == {
        "evidence": 1,
        "legal_authority": 1,
    }


def test_empty_fact_registry_summary_triggers_source_backing_suggestion():
    report = {
        "proof_status": "needs_review",
        "predicate_count": 2,
        "contradiction_count": 0,
        "chronology_blocked": False,
        "fact_registry_summary": {"fact_count": 0},
    }

    result = _score(report)

    assert result["dimensions"]["corpus_grounding"] == 35
    assert any(
        suggestion["dimension"] == "corpus_grounding"
        and "fact registry has no source-backed facts" in suggestion["action"]
        for suggestion in result["suggestions"]
    )


def test_unanchored_fact_registry_summary_suggests_passage_anchors():
    report = {
        "proof_status": "needs_review",
        "predicate_count": 2,
        "contradiction_count": 0,
        "chronology_blocked": False,
        "fact_registry_summary": {
            "fact_count": 1,
            "unique_source_ref_count": 1,
            "passage_anchored_count": 0,
            "source_family_counts": {"evidence": 1},
        },
    }

    result = _score(report)

    assert result["dimensions"]["corpus_grounding"] < 70
    assert any(
        suggestion["dimension"] == "corpus_grounding"
        and "passage anchors" in suggestion["action"]
        for suggestion in result["suggestions"]
    )


def test_quality_scorer_exported_from_package():
    from integrations.ipfs_datasets import score_draft_quality, QUALITY_SCORER_VERSION

    assert callable(score_draft_quality)
    assert isinstance(QUALITY_SCORER_VERSION, str)
    assert QUALITY_SCORER_VERSION.startswith("draft-quality-scorer")


# ---------------------------------------------------------------------------
# MCP tool dispatch tests — get_draft_proof_report
# ---------------------------------------------------------------------------


def _make_service():
    from applications.complaint_workspace import ComplaintWorkspaceService

    return ComplaintWorkspaceService()


def test_get_draft_proof_report_no_draft():
    svc = _make_service()
    result = svc.call_mcp_tool("complaint.get_draft_proof_report", {"user_id": "test-qdpr-no-draft"})
    assert result.get("status") == "no_draft"
    assert result.get("proof_report") is None


def test_get_draft_proof_report_with_draft(monkeypatch):
    svc = _make_service()
    # Inject a fake draft state
    state = svc._load_state("test-qdpr-with-draft")
    state["draft"] = {"body": "Plaintiff was wrongfully terminated by Defendant Corp."}
    svc._save_state(state)

    result = svc.call_mcp_tool("complaint.get_draft_proof_report", {"user_id": "test-qdpr-with-draft"})
    assert result.get("status") == "ok"
    assert "proof_report" in result
    pr = result["proof_report"]
    assert isinstance(pr, dict)
    # proof_report should have the pipeline contract keys
    assert "proof_status" in pr
    assert "pipeline_version" in pr
    # quality score should also be present
    qs = result.get("quality_score")
    assert qs is not None
    assert "overall_score" in qs
    assert "grade" in qs


def test_render_draft_proof_report_no_draft():
    svc = _make_service()
    result = svc.call_mcp_tool("complaint.render_draft_proof_report", {"user_id": "test-rdpr-no-draft"})
    assert result.get("status") == "no_draft"


def test_render_draft_proof_report_with_draft():
    svc = _make_service()
    state = svc._load_state("test-rdpr-with-draft")
    state["draft"] = {"body": "Defendant violated FMLA by retaliating against Plaintiff."}
    svc._save_state(state)

    result = svc.call_mcp_tool(
        "complaint.render_draft_proof_report",
        {"user_id": "test-rdpr-with-draft", "claim_id": "case-42"},
    )
    assert result.get("status") == "ok"
    rendered = result.get("rendered", "")
    assert isinstance(rendered, str)
    assert len(rendered) > 10, "Rendered report should have content"
    # Check for Markdown headers
    assert "#" in rendered


def test_pin_draft_proof_report_no_draft():
    svc = _make_service()
    result = svc.call_mcp_tool("complaint.pin_draft_proof_report", {"user_id": "test-pdpr-no-draft"})
    assert result.get("status") == "no_draft"


def test_pin_draft_proof_report_with_draft():
    svc = _make_service()
    state = svc._load_state("test-pdpr-with-draft")
    state["draft"] = {"body": "Plaintiff suffered damages due to employer negligence."}
    svc._save_state(state)

    result = svc.call_mcp_tool("complaint.pin_draft_proof_report", {"user_id": "test-pdpr-with-draft"})
    assert result.get("status") == "ok"
    pin = result.get("pin_result", {})
    assert isinstance(pin, dict)
    assert "report_cid" in pin
    assert "pinned" in pin
    assert "backend" in pin
    # Even if IPFS is unavailable, report_cid should be a non-empty content hash
    assert pin.get("report_cid", ""), "report_cid should be non-empty"


def test_proof_report_mcp_tools_in_tool_list():
    svc = _make_service()
    tools = svc.list_mcp_tools()
    tool_names = {t["name"] for t in tools.get("tools", [])}
    assert "complaint.get_draft_proof_report" in tool_names
    assert "complaint.render_draft_proof_report" in tool_names
    assert "complaint.pin_draft_proof_report" in tool_names


# ---------------------------------------------------------------------------
# Legal corpus IPFS streaming tests
# ---------------------------------------------------------------------------


def test_ipfs_stream_state_laws_not_enabled_by_default(monkeypatch):
    """When COMPLAINT_ENABLE_IPFS_STATE_LAWS_STREAM is not set, returns empty."""
    import os

    monkeypatch.delenv("COMPLAINT_ENABLE_IPFS_STATE_LAWS_STREAM", raising=False)
    from integrations.ipfs_datasets.legal import _search_ipfs_state_laws_stream

    result = _search_ipfs_state_laws_stream(
        "employment discrimination",
        state_code="CA",
        max_results=5,
    )
    assert result == [], "Should return empty list when IPFS stream is not enabled"


def test_ipfs_stream_env_var_gate(monkeypatch):
    """When enabled but adapter is absent, still returns empty gracefully."""
    import os

    monkeypatch.setenv("COMPLAINT_ENABLE_IPFS_STATE_LAWS_STREAM", "1")
    from integrations.ipfs_datasets import legal

    # Temporarily remove the adapter to simulate it being absent
    orig = legal._stream_ipfs_state_laws_async
    legal._stream_ipfs_state_laws_async = None
    try:
        from integrations.ipfs_datasets.legal import _search_ipfs_state_laws_stream

        result = _search_ipfs_state_laws_stream(
            "workplace harassment",
            state_code="TX",
            max_results=5,
        )
        assert result == [], "Should return empty when adapter is None"
    finally:
        legal._stream_ipfs_state_laws_async = orig


def test_legal_source_availability_includes_ipfs_stream():
    from integrations.ipfs_datasets.legal import LEGAL_SOURCE_AVAILABILITY

    assert "state_laws_ipfs_stream" in LEGAL_SOURCE_AVAILABILITY
    assert isinstance(LEGAL_SOURCE_AVAILABILITY["state_laws_ipfs_stream"], bool)


# ---------------------------------------------------------------------------
# corpus index builder script dry-run test
# ---------------------------------------------------------------------------


def test_build_corpus_index_script_imports():
    """The build_legal_corpus_index script should import without error."""
    import importlib.util
    from pathlib import Path

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "build_legal_corpus_index.py"
    assert script_path.is_file(), "build_legal_corpus_index.py should exist"

    spec = importlib.util.spec_from_file_location("build_legal_corpus_index", script_path)
    mod = importlib.util.module_from_spec(spec)
    # Just loading the module (not running main) should not raise
    spec.loader.exec_module(mod)
    assert hasattr(mod, "build_index")
    assert hasattr(mod, "main")
    assert hasattr(mod, "VALID_SOURCES")
    assert "us_code" in mod.VALID_SOURCES
    assert "all" in mod.VALID_SOURCES
