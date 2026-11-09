"""Tests for integrations/ipfs_datasets/draft_logic_pipeline.py.

These tests exercise the pipeline's structural contract (correct keys, types,
graceful degradation) without making network calls or requiring the full
ipfs_datasets_py logic stack.
"""

from __future__ import annotations

from typing import Any, Dict


def _run(body: str, **kwargs: Any) -> Dict[str, Any]:
    from integrations.ipfs_datasets.draft_logic_pipeline import run_pipeline

    return run_pipeline(body, **kwargs)


def test_pipeline_returns_required_keys_on_empty_body():
    result = _run("")
    required = {
        "proof_status",
        "contradiction_count",
        "chronology_blocked",
        "ungrounded_assertions",
        "corpus_coverage_percent",
        "norms",
        "policy_violations",
        "policy_warnings",
        "has_blockers",
        "predicate_count",
        "fact_registry_summary",
        "pipeline_version",
        "errors",
    }
    for key in required:
        assert key in result, f"Missing required key: {key}"


def test_pipeline_proof_status_type():
    result = _run("Plaintiff reported safety concerns. Defendant terminated Plaintiff.")
    assert isinstance(result["proof_status"], str)
    assert result["proof_status"] in {"passed", "needs_review", "error", "failed"}


def test_pipeline_contradiction_count_is_non_negative_int():
    result = _run("Plaintiff reported safety concerns.")
    assert isinstance(result["contradiction_count"], int)
    assert result["contradiction_count"] >= 0


def test_pipeline_chronology_blocked_is_bool():
    result = _run("Plaintiff reported safety concerns.")
    assert isinstance(result["chronology_blocked"], bool)


def test_pipeline_norms_is_list():
    result = _run("Defendant must not retaliate against employees who report violations.")
    assert isinstance(result["norms"], list)


def test_pipeline_ungrounded_assertions_is_list():
    result = _run("Defendant unlawfully retaliated.")
    assert isinstance(result["ungrounded_assertions"], list)


def test_pipeline_has_blockers_is_bool():
    result = _run("Defendant shall not discriminate.")
    assert isinstance(result["has_blockers"], bool)


def test_pipeline_errors_is_list():
    result = _run("Defendant terminated Plaintiff on March 3.")
    assert isinstance(result["errors"], list)


def test_pipeline_version_string_is_present():
    from integrations.ipfs_datasets.draft_logic_pipeline import DRAFT_LOGIC_PIPELINE_VERSION

    result = _run("Plaintiff seeks relief.")
    assert result["pipeline_version"] == DRAFT_LOGIC_PIPELINE_VERSION


def test_pipeline_sub_results_are_dicts():
    result = _run("Plaintiff reported safety violations to HR on January 15.")
    for key in ("fol_result", "deontic_result", "corpus_result", "proof_result", "policy_result"):
        assert isinstance(result.get(key), dict), f"Sub-result '{key}' should be a dict"


def test_pipeline_summarizes_support_fact_registry_inputs():
    result = _run(
        "Plaintiff reported discrimination to HR.",
        support_facts=[
            {
                "fact_id": "fact:complaint",
                "text": "Plaintiff reported discrimination to HR.",
                "source_family": "evidence",
                "source_ref": "QmComplaint",
                "artifact_family": "archived_web_page",
                "corpus_family": "web_page",
                "content_origin": "historical_archive_capture",
                "parse_source": "web_document",
                "input_format": "html",
                "chunk_id": "chunk-0",
                "source_passage": {"chunk_id": "chunk-0", "chunk_index": 0},
            },
            {
                "fact_id": "fact:authority",
                "text": "Protected activity is recognized by statute.",
                "source_family": "legal_authority",
                "source_ref": "authority:42",
                "artifact_family": "legal_authority_text",
                "corpus_family": "legal_authority",
                "content_origin": "authority_full_text",
                "parse_source": "legal_authority",
                "input_format": "text",
            },
        ],
    )

    summary = result["fact_registry_summary"]
    assert summary["registry_version"] == "claim_fact_registry_summary.v1"
    assert summary["fact_count"] == 2
    assert summary["unique_fact_count"] == 2
    assert summary["unique_source_ref_count"] == 2
    assert summary["passage_anchored_count"] == 1
    assert summary["source_family_counts"] == {
        "evidence": 1,
        "legal_authority": 1,
    }
    assert summary["artifact_family_counts"] == {
        "archived_web_page": 1,
        "legal_authority_text": 1,
    }
    assert summary["corpus_family_counts"] == {
        "web_page": 1,
        "legal_authority": 1,
    }


def test_render_proof_report_includes_fact_registry_metrics():
    from integrations.ipfs_datasets.draft_logic_pipeline import render_proof_report

    rendered = render_proof_report({
        "proof_status": "needs_review",
        "predicate_count": 1,
        "fact_registry_summary": {
            "fact_count": 3,
            "passage_anchored_count": 2,
        },
    })

    assert "| Support facts | 3 |" in rendered
    assert "| Passage-anchored facts | 2 |" in rendered


def test_pipeline_text_to_fol_extracts_predicates():
    from integrations.ipfs_datasets.logic import text_to_fol

    result = text_to_fol("Defendant terminated Plaintiff after the complaint.")
    assert result["status"] == "success"
    assert isinstance(result["predicates"], list)
    assert result["source_text"] == "Defendant terminated Plaintiff after the complaint."


def test_pipeline_legal_text_to_deontic_extracts_norms():
    from integrations.ipfs_datasets.logic import legal_text_to_deontic

    result = legal_text_to_deontic("Employer must not retaliate against employees who file complaints.")
    assert result["status"] == "success"
    assert isinstance(result["norms"], list)
    # At least one prohibition norm should be found
    modalities = [n.get("modality") or n.get("norm_type", "") for n in result["norms"]]
    norm_types = [n.get("norm_type", "") for n in result["norms"]]
    assert any(m in ("F", "prohibition") for m in modalities + norm_types), (
        f"Expected at least one prohibition norm in: {result['norms']}"
    )


def test_pipeline_prove_claim_elements_returns_proof_structure():
    from integrations.ipfs_datasets.logic import prove_claim_elements

    predicates = [
        {
            "predicate_type": "claim_element",
            "claim_element_id": "causation",
            "coverage_status": "unsupported",
            "formula": "Causes(termination,complaint)",
        },
        {
            "predicate_type": "temporal_fact",
            "formula": "AtTime(termination,t_march_3)",
            "start_date": "2024-03-03",
        },
    ]
    result = prove_claim_elements(predicates)
    assert "proof_status" in result
    assert "provable_elements" in result
    assert "unprovable_elements" in result
    assert isinstance(result["provable_elements"], list)
    assert isinstance(result["unprovable_elements"], list)


def test_constrain_assertions_to_corpus_structure():
    from integrations.ipfs_datasets.legal import constrain_assertions_to_corpus

    assertions = [
        {"assertion_id": "a-1", "text": "Employer retaliated against employee."},
        {"assertion_id": "a-2", "text": ""},
    ]
    # With no network available, all assertions should end up ungrounded.
    result = constrain_assertions_to_corpus(assertions, allow_live_scrape_fallback=False)
    assert "grounded" in result
    assert "ungrounded" in result
    assert "corpus_coverage_percent" in result
    assert "total_assertion_count" in result
    assert result["total_assertion_count"] == 2
    # The empty-text assertion must be ungrounded
    assert any(
        item.get("assertion_id") == "a-2" for item in result["ungrounded"]
    )


def test_check_policy_rules_with_deontic_norms_violations():
    from integrations.ipfs_datasets.policy_rules import check_policy_rules_with_deontic_norms

    text = "The employer terminated the employee without cause."
    norms = [
        {
            "norm_type": "prohibition",
            "modality": "F",
            "formula": "F(employer,terminate_without_cause)",
            "trigger_keyword": "terminated",
            "source_sentence": "The employer must not terminate without cause.",
        }
    ]
    result = check_policy_rules_with_deontic_norms(text, norms=norms)
    assert "violations" in result
    assert "warnings" in result
    assert "has_violations" in result
    assert isinstance(result["violations"], list)
    assert result["has_violations"] is True


def test_check_policy_rules_no_violations():
    from integrations.ipfs_datasets.policy_rules import check_policy_rules_with_deontic_norms

    result = check_policy_rules_with_deontic_norms("Plaintiff seeks monetary damages.", norms=[])
    assert isinstance(result["violations"], list)
    assert result["violation_count"] == 0


def test_get_authority_graph_api_version():
    from integrations.ipfs_datasets.graphs import get_authority_graph_api_version

    result = get_authority_graph_api_version()
    assert result["api_version"] == "authority-graph-v1"
    assert "backend_available" in result
    assert isinstance(result["modules_available"], dict)
    assert "knowledge_graphs" in result["modules_available"]
