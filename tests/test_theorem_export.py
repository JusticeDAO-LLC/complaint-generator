"""Tests for integrations/ipfs_datasets/theorem_export.py.

These tests exercise the Lean 4 and Coq export of TDFOL/DCEC formula sets.
All tests run offline and require no external dependencies.
"""

from __future__ import annotations

from typing import List

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lean(tdfol: List[str], dcec: List[str] | None = None) -> str:
    from integrations.ipfs_datasets.theorem_export import export_formulas_to_lean4
    return export_formulas_to_lean4(tdfol, dcec)


def _coq(tdfol: List[str], dcec: List[str] | None = None) -> str:
    from integrations.ipfs_datasets.theorem_export import export_formulas_to_coq
    return export_formulas_to_coq(tdfol, dcec)


def _export_result(proof_result: dict) -> dict:
    from integrations.ipfs_datasets.theorem_export import export_proof_result_to_theorems
    return export_proof_result_to_theorems(proof_result)


# ---------------------------------------------------------------------------
# Basic structure tests
# ---------------------------------------------------------------------------

def test_lean4_export_returns_string_on_empty_formulas():
    result = _lean([])
    assert isinstance(result, str)
    assert len(result) > 0


def test_coq_export_returns_string_on_empty_formulas():
    result = _coq([])
    assert isinstance(result, str)
    assert len(result) > 0


def test_lean4_export_contains_namespace():
    result = _lean(["Fact(event_1,t_2023)"])
    assert "namespace ComplaintProof" in result
    assert "end ComplaintProof" in result


def test_coq_export_contains_module():
    result = _coq(["Fact(event_1,t_2023)"])
    assert "Module ComplaintProof" in result
    assert "End ComplaintProof." in result


def test_lean4_export_contains_type_declarations():
    result = _lean(["Fact(event_1,t_2023)"])
    assert "variable (Time" in result or "Time Event" in result


def test_coq_export_contains_variable_declarations():
    result = _coq(["Fact(event_1,t_2023)"])
    assert "Variable" in result


def test_lean4_export_contains_axiom_for_formula():
    formulas = ["Fact(event_1,t_2023_01_15)"]
    result = _lean(formulas)
    assert "axiom_formula_1" in result


def test_coq_export_contains_hypothesis_for_formula():
    formulas = ["Fact(event_1,t_2023_01_15)"]
    result = _coq(formulas)
    assert "Hypothesis formula_1" in result


def test_lean4_export_embeds_claim_id():
    from integrations.ipfs_datasets.theorem_export import export_formulas_to_lean4
    result = export_formulas_to_lean4(["Before(e1,e2)"], claim_id="claim-abc-123")
    assert "claim-abc-123" in result


def test_coq_export_embeds_claim_id():
    from integrations.ipfs_datasets.theorem_export import export_formulas_to_coq
    result = export_formulas_to_coq(["Before(e1,e2)"], claim_id="claim-xyz-999")
    assert "claim-xyz-999" in result


def test_lean4_export_multiple_formulas_all_appear():
    formulas = [
        "forall t (AtTime(t,t_jan) -> Fact(ev1,t))",
        "Supports(sup1,claim1)",
        "Before(ev1,ev2)",
    ]
    result = _lean(formulas)
    assert "axiom_formula_1" in result
    assert "axiom_formula_2" in result
    assert "axiom_formula_3" in result


def test_lean4_export_header_contains_auto_generated_comment():
    result = _lean(["Observed(ev1)"])
    assert "Auto-generated" in result
    assert "theorem-export-v1" in result


def test_coq_export_header_contains_auto_generated_comment():
    result = _coq(["Observed(ev1)"])
    assert "Auto-generated" in result
    assert "theorem-export-v1" in result


def test_lean4_export_with_dcec_formulas():
    tdfol = ["forall t (AtTime(t,t_jan) -> Fact(ev1,t))"]
    dcec = ["Happens(ev1,t_jan)"]
    result = _lean(tdfol, dcec)
    assert "TDFOL" in result
    assert "DCEC" in result


def test_coq_export_with_dcec_formulas():
    tdfol = ["forall t (AtTime(t,t_jan) -> Fact(ev1,t))"]
    dcec = ["Happens(ev1,t_jan)"]
    result = _coq(tdfol, dcec)
    assert "TDFOL" in result
    assert "DCEC" in result


# ---------------------------------------------------------------------------
# export_proof_result_to_theorems tests
# ---------------------------------------------------------------------------

def test_export_proof_result_returns_required_keys():
    result = _export_result({})
    assert "lean4" in result
    assert "coq" in result
    assert "tdfol_formula_count" in result
    assert "dcec_formula_count" in result
    assert "export_version" in result
    assert "exported_at" in result


def test_export_proof_result_formula_counts_match():
    payload = {
        "temporal_reasoning_payload": {
            "tdfol_formulas": ["Fact(e1,t1)", "Before(e1,e2)"],
            "dcec_formulas": ["Happens(e1,t1)"],
        }
    }
    result = _export_result(payload)
    assert result["tdfol_formula_count"] == 2
    assert result["dcec_formula_count"] == 1


def test_export_proof_result_preserves_fact_registry_summary():
    payload = {
        "temporal_reasoning_payload": {
            "tdfol_formulas": ["Supports(s1,c1)"],
            "dcec_formulas": [],
            "fact_registry_summary": {
                "fact_count": 2,
                "source_family_counts": {"evidence": 1, "legal_authority": 1},
                "corpus_family_counts": {"web_archive": 1, "legal_corpus": 1},
                "passage_anchored_count": 1,
            },
        }
    }

    result = _export_result(payload)

    assert result["fact_registry_summary"] == {
        "fact_count": 2,
        "source_family_counts": {"evidence": 1, "legal_authority": 1},
        "corpus_family_counts": {"web_archive": 1, "legal_corpus": 1},
        "passage_anchored_count": 1,
    }


def test_export_proof_result_prefers_top_level_fact_registry_summary():
    payload = {
        "fact_registry_summary": {"fact_count": 3, "source_family_counts": {"evidence": 3}},
        "temporal_reasoning_payload": {
            "tdfol_formulas": ["Supports(s1,c1)"],
            "fact_registry_summary": {"fact_count": 1},
        },
    }

    result = _export_result(payload)

    assert result["fact_registry_summary"] == {
        "fact_count": 3,
        "source_family_counts": {"evidence": 3},
    }


def test_export_proof_result_lean4_is_nonempty_string():
    payload = {
        "temporal_reasoning_payload": {
            "tdfol_formulas": ["Supports(sup1,claim1)"],
            "dcec_formulas": [],
        }
    }
    result = _export_result(payload)
    assert isinstance(result["lean4"], str)
    assert len(result["lean4"]) > 50


def test_export_proof_result_coq_is_nonempty_string():
    payload = {
        "temporal_reasoning_payload": {
            "tdfol_formulas": ["Conflict(e1,e2)"],
            "dcec_formulas": ["Conflicts(e1,e2)"],
        }
    }
    result = _export_result(payload)
    assert isinstance(result["coq"], str)
    assert len(result["coq"]) > 50


def test_export_proof_result_version_constant():
    from integrations.ipfs_datasets.theorem_export import THEOREM_EXPORT_VERSION
    result = _export_result({})
    assert result["export_version"] == THEOREM_EXPORT_VERSION


# ---------------------------------------------------------------------------
# Integration: pipeline result includes theorem_export
# ---------------------------------------------------------------------------

def test_draft_logic_pipeline_result_has_theorem_export_key():
    from integrations.ipfs_datasets.draft_logic_pipeline import run_pipeline
    result = run_pipeline("Plaintiff reported safety concerns. Defendant terminated Plaintiff.")
    assert "theorem_export" in result
    assert isinstance(result["theorem_export"], dict)


def test_prove_claim_elements_result_has_theorem_export():
    from integrations.ipfs_datasets.logic import prove_claim_elements
    result = prove_claim_elements([
        {"predicate_type": "factual_statement", "formula": "Fact(ev1,t1)"},
    ])
    assert "theorem_export" in result
    assert isinstance(result["theorem_export"], dict)
