"""Tests for M4 Retrieval Sessions and Evidence Ranking.

Covers:
- create_retrieval_session: stable session ID, persisted to DB
- index_chunks_for_retrieval: indexes testimony + document chunks into unified plane
- run_retrieval_session: scores, ranks, explains, deduplicates, persists
- get_retrieval_session: retrieves persisted session + ranked results
- list_retrieval_sessions: lists sessions scoped to user/claim/element
- get_retrieval_context_for_element: best results for a claim element across sessions
- get_question_recommendations: now includes retrieval_context per recommendation
"""
from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.no_auto_network


def _make_minimal_mediator() -> MagicMock:
    mediator = MagicMock()
    mediator.log = MagicMock()
    mediator.get_three_phase_status = MagicMock(return_value={})
    state = MagicMock()
    state.username = "test_user"
    mediator.state = state
    return mediator


def _make_hooks(db_path: str = None):
    from mediator.claim_support_hooks import ClaimSupportHook
    if db_path is None:
        # Use a temp file so DuckDB connections share state across calls
        db_path = _tmp_db_path()
    return ClaimSupportHook(_make_minimal_mediator(), db_path=db_path)


def _tmp_db_path() -> str:
    """Return a fresh temporary DuckDB file path."""
    f = tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False)
    f.close()
    os.unlink(f.name)  # remove so DuckDB creates it fresh
    return f.name


def _sample_chunks() -> List[Dict[str, Any]]:
    return [
        {
            "source_kind": "testimony",
            "source_ref": "testimony:001",
            "source_label": "Complainant testimony on adverse action",
            "chunk_text": "I was terminated on March 15 after filing a harassment complaint.",
            "confidence": 0.85,
        },
        {
            "source_kind": "document",
            "source_ref": "doc:evidence-001",
            "source_label": "Termination letter",
            "chunk_text": "Your employment is terminated effective March 15 per company policy.",
            "confidence": 0.9,
        },
        {
            "source_kind": "testimony",
            "source_ref": "testimony:002",
            "source_label": "Complainant testimony on retaliation",
            "chunk_text": "My supervisor told me not to file a complaint or I would be fired.",
            "confidence": 0.75,
        },
    ]


# ---------------------------------------------------------------------------
# create_retrieval_session
# ---------------------------------------------------------------------------

def test_create_retrieval_session_returns_session_id():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    result = hooks.create_retrieval_session(
        "user1",
        "employment_discrimination",
        claim_element_id="adverse_action",
        claim_element_text="Adverse employment action",
        query_text="termination harassment retaliation",
    )
    assert result["created"] is True
    assert result["session_id"].startswith("rsession:")
    assert result["status"] == "pending"
    assert result["claim_type"] == "employment_discrimination"
    assert result["claim_element_id"] == "adverse_action"


def test_create_retrieval_session_stable_id():
    """Same inputs at the same created_at should produce the same session_id."""
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    hooks2 = _make_hooks()
    # Build id directly via helper to verify determinism
    created_at = "2025-06-01T00:00:00+00:00"
    sid1 = hooks._make_retrieval_session_id(
        user_id="u1",
        claim_type="employment_discrimination",
        claim_element_id="adverse_action",
        query_text="termination",
        created_at=created_at,
    )
    sid2 = hooks2._make_retrieval_session_id(
        user_id="u1",
        claim_type="employment_discrimination",
        claim_element_id="adverse_action",
        query_text="termination",
        created_at=created_at,
    )
    assert sid1 == sid2
    assert sid1.startswith("rsession:")


def test_create_retrieval_session_no_duckdb():
    import mediator.claim_support_hooks as hooks_module
    original = hooks_module.DUCKDB_AVAILABLE
    try:
        hooks_module.DUCKDB_AVAILABLE = False
        hooks = _make_hooks()
        result = hooks.create_retrieval_session("u1", "employment_discrimination")
        assert result["created"] is False
        assert "error" in result
        assert result["session_id"] == ""
    finally:
        hooks_module.DUCKDB_AVAILABLE = original


# ---------------------------------------------------------------------------
# index_chunks_for_retrieval
# ---------------------------------------------------------------------------

def test_index_chunks_for_retrieval_counts():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    result = hooks.index_chunks_for_retrieval(
        "user1",
        "employment_discrimination",
        _sample_chunks(),
        claim_element_id="adverse_action",
    )
    assert result["indexed"] is True
    assert result["indexed_count"] == len(_sample_chunks())


def test_index_chunks_for_retrieval_detects_duplicates():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    duplicate_chunks = [
        {
            "source_kind": "testimony",
            "source_ref": "t:001",
            "chunk_text": "I was fired after the complaint.",
        },
        {
            "source_kind": "testimony",
            "source_ref": "t:002",
            "chunk_text": "I was fired after the complaint.",  # exact duplicate
        },
    ]
    result = hooks.index_chunks_for_retrieval(
        "user1", "employment_discrimination", duplicate_chunks
    )
    assert result["indexed"] is True
    # Only 1 unique cluster despite 2 chunks
    assert result["duplicate_cluster_count"] == 1


def test_index_chunks_skips_empty():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    result = hooks.index_chunks_for_retrieval("user1", "employment_discrimination", [])
    assert result["indexed"] is True
    assert result["indexed_count"] == 0


# ---------------------------------------------------------------------------
# run_retrieval_session
# ---------------------------------------------------------------------------

def test_run_retrieval_session_returns_required_keys():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    result = hooks.run_retrieval_session(
        "user1",
        "employment_discrimination",
        claim_element_id="adverse_action",
        claim_element_text="Adverse employment action",
        query_text="termination retaliation",
        chunks=_sample_chunks(),
    )
    assert result["available"] is True
    assert "session_id" in result
    assert result["session_id"].startswith("rsession:")
    assert "results" in result
    assert "result_count" in result
    assert "duplicate_count" in result
    assert "duplicate_cluster_count" in result
    assert result["status"] == "complete"


def test_run_retrieval_session_ranks_by_score():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    chunks = [
        {
            "source_kind": "testimony",
            "source_ref": "t:low",
            "chunk_text": "Some unrelated content.",
            "score": 0.1,
        },
        {
            "source_kind": "testimony",
            "source_ref": "t:high",
            "chunk_text": "Termination retaliation adverse action employer employee.",
            "score": 0.0,
        },
    ]
    result = hooks.run_retrieval_session(
        "user1",
        "employment_discrimination",
        query_text="termination retaliation adverse action",
        chunks=chunks,
        max_results=10,
    )
    assert result["available"] is True
    assert len(result["results"]) == 2
    # The chunk with query term overlap should rank higher
    top = result["results"][0]
    assert top["source_ref"] == "t:high"


def test_run_retrieval_session_each_result_has_explanation():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    result = hooks.run_retrieval_session(
        "user1",
        "employment_discrimination",
        query_text="termination",
        chunks=_sample_chunks(),
    )
    for r in result["results"]:
        assert "explanation" in r
        assert isinstance(r["explanation"], str)
        assert len(r["explanation"]) > 0


def test_run_retrieval_session_persists_w7_ranking_factors():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    result = hooks.run_retrieval_session(
        "user1",
        "employment_discrimination",
        claim_element_id="adverse_action",
        claim_element_text="Adverse employment action after protected activity",
        query_text="termination retaliation 2025",
        chunks=[
            {
                "source_kind": "document",
                "source_ref": "doc:timeline",
                "source_label": "Termination timeline",
                "chunk_text": "Adverse employment action after protected activity in 2025.",
                "metadata": {
                    "quality_score": 0.9,
                    "published_date": "2025-03-15",
                    "graph_trace_summary": {"traced_link_count": 2},
                    "support_quality_summary": {"dominant_quality_tier": "strong_support"},
                },
            }
        ],
    )

    top = result["results"][0]
    factors = top["metadata"]["retrieval_ranking_factors"]
    assert factors["claim_element_fit_weight"] > 0.0
    assert factors["source_quality_weight"] > 0.0
    assert factors["temporal_relevance_weight"] > 0.0
    assert factors["graph_signal_weight"] > 0.0
    assert top["metadata"]["retrieval_ranking_explanation"]

    context = hooks.get_retrieval_context_for_element(
        "user1", "employment_discrimination", "adverse_action"
    )
    assert context["top_results"][0]["retrieval_ranking_factors"]["graph_signal_weight"] > 0.0


def test_run_retrieval_session_marks_duplicate_representatives():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    chunks = [
        {"source_ref": "t:a", "source_kind": "testimony", "chunk_text": "Fired after complaint."},
        {"source_ref": "t:b", "source_kind": "testimony", "chunk_text": "Fired after complaint."},
        {"source_ref": "t:c", "source_kind": "testimony", "chunk_text": "Supervisor told me not to complain."},
    ]
    result = hooks.run_retrieval_session(
        "user1", "employment_discrimination", query_text="termination complaint", chunks=chunks
    )
    reps = [r for r in result["results"] if r["is_duplicate_representative"]]
    non_reps = [r for r in result["results"] if not r["is_duplicate_representative"]]
    # Two unique clusters -> 2 representatives
    assert len(reps) == 2
    assert len(non_reps) == 1
    assert result["duplicate_count"] == 1


def test_run_retrieval_session_no_duckdb():
    import mediator.claim_support_hooks as hooks_module
    original = hooks_module.DUCKDB_AVAILABLE
    try:
        hooks_module.DUCKDB_AVAILABLE = False
        hooks = _make_hooks()
        result = hooks.run_retrieval_session(
            "user1", "employment_discrimination", chunks=_sample_chunks()
        )
        assert result["available"] is False
        assert result["results"] == []
    finally:
        hooks_module.DUCKDB_AVAILABLE = original


# ---------------------------------------------------------------------------
# get_retrieval_session
# ---------------------------------------------------------------------------

def test_get_retrieval_session_round_trip():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    run = hooks.run_retrieval_session(
        "user1",
        "employment_discrimination",
        claim_element_id="adverse_action",
        claim_element_text="Adverse employment action",
        query_text="termination",
        chunks=_sample_chunks(),
    )
    assert run["available"] is True
    session_id = run["session_id"]

    fetched = hooks.get_retrieval_session("user1", session_id)
    assert fetched["available"] is True
    assert fetched["found"] is True
    assert fetched["session_id"] == session_id
    assert fetched["claim_type"] == "employment_discrimination"
    assert fetched["claim_element_id"] == "adverse_action"
    assert fetched["status"] == "complete"
    assert isinstance(fetched["results"], list)
    assert len(fetched["results"]) == len(_sample_chunks())


def test_get_retrieval_session_not_found():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    result = hooks.get_retrieval_session("user1", "rsession:doesnotexist")
    assert result["available"] is True
    assert result["found"] is False
    assert result["results"] == []


def test_get_retrieval_session_has_duplicate_cluster_info():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    chunks = [
        {"source_ref": "t:a", "source_kind": "testimony", "chunk_text": "Fired after complaint."},
        {"source_ref": "t:b", "source_kind": "testimony", "chunk_text": "Fired after complaint."},
    ]
    run = hooks.run_retrieval_session(
        "user1", "employment_discrimination", chunks=chunks
    )
    fetched = hooks.get_retrieval_session("user1", run["session_id"])
    assert fetched["duplicate_count"] >= 1
    assert fetched["duplicate_cluster_count"] >= 1
    assert isinstance(fetched["duplicate_cluster_ids"], list)


# ---------------------------------------------------------------------------
# list_retrieval_sessions
# ---------------------------------------------------------------------------

def test_list_retrieval_sessions_returns_required_keys():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    result = hooks.list_retrieval_sessions("user1")
    assert result["available"] is True
    assert "sessions" in result
    assert "session_count" in result


def test_list_retrieval_sessions_empty():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    result = hooks.list_retrieval_sessions("user1")
    assert result["session_count"] == 0
    assert result["sessions"] == []


def test_list_retrieval_sessions_after_creation():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    hooks.run_retrieval_session(
        "user2",
        "employment_discrimination",
        claim_element_id="adverse_action",
        query_text="termination",
        chunks=_sample_chunks(),
    )
    result = hooks.list_retrieval_sessions("user2", claim_type="employment_discrimination")
    assert result["session_count"] >= 1
    session_ids = [s["session_id"] for s in result["sessions"]]
    assert all(sid.startswith("rsession:") for sid in session_ids)


def test_list_retrieval_sessions_scoped_by_element():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    hooks.run_retrieval_session(
        "user3", "employment_discrimination",
        claim_element_id="adverse_action", query_text="termination", chunks=_sample_chunks()
    )
    hooks.run_retrieval_session(
        "user3", "employment_discrimination",
        claim_element_id="protected_trait", query_text="race gender", chunks=_sample_chunks()
    )
    result_all = hooks.list_retrieval_sessions("user3", claim_type="employment_discrimination")
    result_scoped = hooks.list_retrieval_sessions(
        "user3", claim_type="employment_discrimination", claim_element_id="adverse_action"
    )
    assert result_all["session_count"] >= 2
    assert result_scoped["session_count"] >= 1
    for s in result_scoped["sessions"]:
        assert s["claim_element_id"] == "adverse_action"


# ---------------------------------------------------------------------------
# get_retrieval_context_for_element
# ---------------------------------------------------------------------------

def test_get_retrieval_context_returns_required_keys():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    result = hooks.get_retrieval_context_for_element(
        "user1", "employment_discrimination", "adverse_action"
    )
    assert result["available"] is True
    assert "has_retrieval_context" in result
    assert "top_results" in result
    assert "result_count" in result
    assert "duplicate_cluster_count" in result


def test_get_retrieval_context_empty_when_no_sessions():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    result = hooks.get_retrieval_context_for_element(
        "user1", "employment_discrimination", "adverse_action"
    )
    assert result["has_retrieval_context"] is False
    assert result["top_results"] == []
    assert result["result_count"] == 0


def test_get_retrieval_context_populated_after_run():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    hooks.run_retrieval_session(
        "user4",
        "employment_discrimination",
        claim_element_id="adverse_action",
        claim_element_text="Adverse employment action",
        query_text="termination",
        chunks=_sample_chunks(),
    )
    result = hooks.get_retrieval_context_for_element(
        "user4", "employment_discrimination", "adverse_action"
    )
    assert result["has_retrieval_context"] is True
    assert result["result_count"] > 0
    assert len(result["top_results"]) > 0
    for r in result["top_results"]:
        assert "source_kind" in r
        assert "retrieval_score" in r
        assert "explanation" in r
        assert "duplicate_cluster_id" in r


def test_get_retrieval_context_top_score_populated():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_hooks()
    hooks.run_retrieval_session(
        "user5",
        "employment_discrimination",
        claim_element_id="adverse_action",
        query_text="termination retaliation",
        chunks=_sample_chunks(),
    )
    result = hooks.get_retrieval_context_for_element(
        "user5", "employment_discrimination", "adverse_action"
    )
    assert result["top_score"] > 0.0


# ---------------------------------------------------------------------------
# get_question_recommendations: retrieval_context enrichment
# ---------------------------------------------------------------------------

def test_question_recommendations_include_retrieval_context_field():
    """Each recommendation should now carry a retrieval_context sub-object."""
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    from mediator.claim_support_hooks import ClaimSupportHook

    mediator = _make_minimal_mediator()
    hooks = ClaimSupportHook(mediator, db_path=":memory:")

    # Stub get_claim_support_gaps to return one gap element
    hooks.get_claim_support_gaps = MagicMock(return_value={
        "claims": {
            "employment_discrimination": {
                "unresolved_elements": [
                    {
                        "element_id": "adverse_action",
                        "element_text": "Adverse employment action",
                        "status": "missing",
                        "total_links": 0,
                        "missing_support_kinds": ["testimony", "evidence"],
                    }
                ]
            }
        }
    })
    hooks.get_claim_contradiction_candidates = MagicMock(return_value={"claims": {}})

    result = hooks.get_question_recommendations("user1", claim_type="employment_discrimination")
    assert result["available"] is True
    recs = result["recommendations"]
    assert len(recs) == 1
    rec = recs[0]
    assert "retrieval_context" in rec
    rc = rec["retrieval_context"]
    assert "has_retrieval_context" in rc
    assert "result_count" in rc
    assert "top_score" in rc
    assert "duplicate_cluster_count" in rc
    assert "top_results" in rc


def test_question_recommendations_gain_dampened_when_retrieval_context_exists():
    """Expected proof gain should be dampened when retrieval context already exists."""
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    from mediator.claim_support_hooks import ClaimSupportHook

    db_path = _tmp_db_path()
    try:
        mediator = _make_minimal_mediator()
        hooks = ClaimSupportHook(mediator, db_path=db_path)

        # Pre-populate retrieval results for the element
        hooks.run_retrieval_session(
            "user6",
            "employment_discrimination",
            claim_element_id="adverse_action",
            claim_element_text="Adverse employment action",
            query_text="termination",
            chunks=_sample_chunks(),
        )

        hooks.get_claim_support_gaps = MagicMock(return_value={
            "claims": {
                "employment_discrimination": {
                    "unresolved_elements": [
                        {
                            "element_id": "adverse_action",
                            "element_text": "Adverse employment action",
                            "status": "missing",
                            "total_links": 0,
                            "missing_support_kinds": ["testimony"],
                        }
                    ]
                }
            }
        })
        hooks.get_claim_contradiction_candidates = MagicMock(return_value={"claims": {}})

        # Compute gain without retrieval context
        element_no_ctx = {"element_id": "adverse_action", "status": "missing", "total_links": 0}
        lane = "missing_element"
        gain_no_ctx = hooks._expected_proof_gain_for_element(element_no_ctx, lane)

        result = hooks.get_question_recommendations("user6", claim_type="employment_discrimination")
        rec = result["recommendations"][0]
        # When retrieval context exists, gain should be lower
        assert rec["retrieval_context"]["has_retrieval_context"] is True
        assert rec["expected_proof_gain"] < gain_no_ctx
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# Helpers: _score_retrieval_chunk and _explain_retrieval_result
# ---------------------------------------------------------------------------

def test_score_retrieval_chunk_higher_for_query_overlap():
    hooks = _make_hooks()
    high_chunk = {
        "chunk_text": "Termination retaliation adverse action employer employee",
        "score": 0.0,
    }
    low_chunk = {
        "chunk_text": "Some completely unrelated content here",
        "score": 0.0,
    }
    q_tokens = ["termination", "retaliation", "adverse"]
    high_score = hooks._score_retrieval_chunk(high_chunk, q_tokens, "adverse action")
    low_score = hooks._score_retrieval_chunk(low_chunk, q_tokens, "adverse action")
    assert high_score > low_score


def test_explain_retrieval_result_mentions_matched_terms():
    hooks = _make_hooks()
    chunk = {"chunk_text": "termination retaliation complaint", "source_kind": "testimony"}
    explanation = hooks._explain_retrieval_result(chunk, ["termination", "retaliation"], 0.75, "adverse action")
    assert "termination" in explanation or "retaliation" in explanation
    assert "0.75" in explanation


def test_normalize_chunk_for_indexing_testimony():
    hooks = _make_hooks()
    testimony = {
        "testimony_id": "t:001",
        "raw_narrative": "I was terminated after filing a complaint.",
        "source_confidence": 0.9,
    }
    normalized = hooks._normalize_chunk_for_indexing(testimony, "testimony")
    assert normalized["source_ref"] == "t:001"
    assert "terminated" in normalized["chunk_text"]
    assert normalized["source_kind"] == "testimony"
    assert normalized["confidence"] == 0.9


def test_normalize_chunk_for_indexing_fact():
    hooks = _make_hooks()
    fact = {
        "fact_id": "fact:abc",
        "proposition_text": "Employer terminated claimant on March 15.",
        "confidence": 0.8,
    }
    normalized = hooks._normalize_chunk_for_indexing(fact, "fact")
    assert normalized["source_ref"] == "fact:abc"
    assert "terminated" in normalized["chunk_text"]
    assert normalized["confidence"] == 0.8


def test_duplicate_cluster_id_stable_for_same_text():
    hooks = _make_hooks()
    cluster1 = hooks._make_duplicate_cluster_id("I was fired after the complaint.")
    cluster2 = hooks._make_duplicate_cluster_id("I was fired after the complaint.")
    assert cluster1 == cluster2
    assert cluster1.startswith("dc:")


def test_duplicate_cluster_id_differs_for_different_text():
    hooks = _make_hooks()
    cluster1 = hooks._make_duplicate_cluster_id("I was fired after the complaint.")
    cluster2 = hooks._make_duplicate_cluster_id("My supervisor told me not to complain.")
    assert cluster1 != cluster2
