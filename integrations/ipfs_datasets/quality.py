"""Draft quality scoring for complaint proof reports.

:func:`score_draft_quality` consumes a :class:`DraftProofReport` dict
(returned by :func:`~integrations.ipfs_datasets.draft_logic_pipeline.run_pipeline`)
and returns a structured quality score with five dimension scores, an overall
grade, and a prioritised list of actionable suggestions.

Dimension weights
-----------------
* ``corpus_grounding``    (30 %) — how well assertions are grounded in legal authority
* ``proof_completeness``  (25 %) — absence of logical gaps / needs-review signals
* ``policy_compliance``   (20 %) — freedom from deontic policy violations / warnings
* ``contradiction_free``  (15 %) — absence of logical contradictions
* ``theorem_readiness``   (10 %) — availability and richness of theorem export
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

QUALITY_SCORER_VERSION = "draft-quality-scorer-v1"

# Overall score thresholds → letter grades
_GRADE_THRESHOLDS: List[Tuple[int, str]] = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
]

# Dimension weights must sum to 1.0
_WEIGHTS: Dict[str, float] = {
    "corpus_grounding": 0.30,
    "proof_completeness": 0.25,
    "policy_compliance": 0.20,
    "contradiction_free": 0.15,
    "theorem_readiness": 0.10,
}


def _grade(score: int) -> str:
    for threshold, letter in _GRADE_THRESHOLDS:
        if score >= threshold:
            return letter
    return "F"


def _extract_fact_registry_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    """Return the first fact-registry summary exposed by proof/theorem payloads."""
    candidates = [
        report.get("fact_registry_summary"),
        (report.get("theorem_export") or {}).get("fact_registry_summary")
        if isinstance(report.get("theorem_export"), dict)
        else {},
        (report.get("temporal_reasoning_payload") or {}).get("fact_registry_summary")
        if isinstance(report.get("temporal_reasoning_payload"), dict)
        else {},
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return dict(candidate)
    return {}


def _score_corpus_grounding(report: Dict[str, Any]) -> int:
    """0-100 based on corpus coverage, support facts, and ungrounded assertions."""
    fact_registry_summary = _extract_fact_registry_summary(report)
    fact_count = int(fact_registry_summary.get("fact_count") or 0)
    unique_source_refs = int(fact_registry_summary.get("unique_source_ref_count") or 0)
    passage_anchored_count = int(fact_registry_summary.get("passage_anchored_count") or 0)
    source_family_counts = (
        fact_registry_summary.get("source_family_counts")
        if isinstance(fact_registry_summary.get("source_family_counts"), dict)
        else {}
    )
    coverage = report.get("corpus_coverage_percent")
    if coverage is not None:
        score = int(max(0, min(100, int(coverage))))
        if fact_registry_summary:
            if fact_count <= 0:
                score = min(score, 65)
            else:
                passage_ratio = passage_anchored_count / max(fact_count, 1)
                score += min(8, int(round(passage_ratio * 8)))
                score += min(4, len(source_family_counts) * 2)
                score = min(score, 100)
        return score
    if fact_registry_summary:
        if fact_count <= 0:
            return 35
        passage_ratio = passage_anchored_count / max(fact_count, 1)
        score = 45
        score += min(30, fact_count * 4)
        score += min(10, unique_source_refs * 2)
        score += min(10, len(source_family_counts) * 5)
        score += min(15, int(round(passage_ratio * 15)))
        return int(max(0, min(100, score)))
    # If no coverage data, check ungrounded count vs total
    ungrounded_count = int(report.get("ungrounded_assertion_count") or 0)
    predicate_count = int(report.get("predicate_count") or 0)
    total = predicate_count or ungrounded_count
    if not total:
        return 50  # Neutral when no data
    grounded = max(0, total - ungrounded_count)
    return int(round((grounded / total) * 100))


def _score_proof_completeness(report: Dict[str, Any]) -> int:
    """0-100 based on proof_status and predicate coverage."""
    proof_status = str(report.get("proof_status") or "needs_review").lower()
    status_scores = {
        "passed": 100,
        "needs_review": 60,
        "failed": 30,
        "error": 10,
        "violation": 20,
    }
    base = status_scores.get(proof_status, 50)
    errors = list(report.get("errors") or [])
    if errors:
        base = max(0, base - 10 * min(len(errors), 5))
    predicate_count = int(report.get("predicate_count") or 0)
    if predicate_count == 0:
        base = min(base, 40)  # No predicates extracted — capped
    return int(max(0, min(100, base)))


def _score_policy_compliance(report: Dict[str, Any]) -> int:
    """0-100 based on violation and warning counts."""
    violations = list(report.get("policy_violations") or [])
    warnings = list(report.get("policy_warnings") or [])
    if violations:
        return max(0, 50 - 15 * min(len(violations), 3))
    if warnings:
        return max(50, 90 - 10 * min(len(warnings), 4))
    return 100


def _score_contradiction_free(report: Dict[str, Any]) -> int:
    """0-100 based on contradiction count and chronology block."""
    contradiction_count = int(report.get("contradiction_count") or 0)
    chronology_blocked = bool(report.get("chronology_blocked"))
    if contradiction_count == 0 and not chronology_blocked:
        return 100
    score = 100
    if chronology_blocked:
        score -= 40
    score -= 20 * min(contradiction_count, 3)
    return max(0, score)


def _score_theorem_readiness(report: Dict[str, Any]) -> int:
    """0-100 based on availability and richness of the theorem export."""
    theorem_export = dict(report.get("theorem_export") or {})
    tdfol_count = int(theorem_export.get("tdfol_formula_count") or 0)
    dcec_count = int(theorem_export.get("dcec_formula_count") or 0)
    lean4 = bool(theorem_export.get("lean4"))
    coq = bool(theorem_export.get("coq"))
    if not theorem_export:
        return 20  # Pipeline ran but no export data
    score = 40
    if tdfol_count > 0:
        score += min(20, tdfol_count * 4)
    if dcec_count > 0:
        score += min(20, dcec_count * 4)
    if lean4:
        score += 10
    if coq:
        score += 10
    return min(100, score)


def _build_suggestions(
    *,
    corpus_score: int,
    proof_score: int,
    policy_score: int,
    contradiction_score: int,
    theorem_score: int,
    report: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Return a prioritised list of actionable suggestions."""
    suggestions: List[Dict[str, Any]] = []

    ungrounded = list(report.get("ungrounded_assertions") or [])
    if corpus_score < 70:
        fact_registry_summary = _extract_fact_registry_summary(report)
        fact_count = int(fact_registry_summary.get("fact_count") or 0)
        passage_anchored_count = int(fact_registry_summary.get("passage_anchored_count") or 0)
        if fact_registry_summary and fact_count <= 0:
            action = "Attach persisted support facts before proof review; the fact registry has no source-backed facts."
        elif fact_registry_summary and passage_anchored_count <= 0:
            action = "Add chunk or passage anchors to support facts so proof reviewers can trace generated predicates to source text."
        elif ungrounded:
            action = (
                f"Ground {len(ungrounded)} ungrounded assertion(s) in US Code, "
                "Federal Register, or state law before filing."
            )
        else:
            action = (
                "Improve legal corpus grounding — run constrain_assertions_to_corpus with "
                "COMPLAINT_LEGAL_VECTOR_INDEX_DIR set to enable semantic search."
            )
        suggestions.append(
            {
                "priority": "high",
                "dimension": "corpus_grounding",
                "action": action,
            }
        )

    violations = list(report.get("policy_violations") or [])
    if violations:
        suggestions.append(
            {
                "priority": "high",
                "dimension": "policy_compliance",
                "action": (
                    f"Resolve {len(violations)} deontic policy violation(s): "
                    + "; ".join(
                        str(v.get("violation_type") or "violation") for v in violations[:3]
                    )
                    + ("…" if len(violations) > 3 else ".")
                ),
            }
        )

    contradiction_count = int(report.get("contradiction_count") or 0)
    if contradiction_count:
        suggestions.append(
            {
                "priority": "high",
                "dimension": "contradiction_free",
                "action": (
                    f"Eliminate {contradiction_count} logical contradiction(s) in the draft.  "
                    "Review the contradictions list in the proof report for details."
                ),
            }
        )

    if bool(report.get("chronology_blocked")):
        suggestions.append(
            {
                "priority": "high",
                "dimension": "contradiction_free",
                "action": "Fix the chronological inconsistency flagged by the temporal-reasoning engine.",
            }
        )

    if proof_score < 70:
        errors = list(report.get("errors") or [])
        suggestions.append(
            {
                "priority": "medium",
                "dimension": "proof_completeness",
                "action": (
                    "Pipeline reported errors: " + "; ".join(str(e) for e in errors[:3])
                    if errors
                    else "Proof status is 'needs_review'.  Add more factual predicates to improve coverage."
                ),
            }
        )

    warnings = list(report.get("policy_warnings") or [])
    if warnings:
        suggestions.append(
            {
                "priority": "medium",
                "dimension": "policy_compliance",
                "action": (
                    f"Address {len(warnings)} deontic obligation warning(s) — "
                    "one or more required obligations may not be satisfied in the draft."
                ),
            }
        )

    if theorem_score < 60:
        suggestions.append(
            {
                "priority": "low",
                "dimension": "theorem_readiness",
                "action": (
                    "Enable the theorem export pipeline to generate Lean 4 / Coq proof stubs.  "
                    "Set COMPLAINT_USE_DRAFT_LOGIC_PIPELINE=1 and ensure ipfs_datasets_py is importable."
                ),
            }
        )

    return suggestions


def score_draft_quality(
    report: Dict[str, Any],
    *,
    claim_id: str = "",
) -> Dict[str, Any]:
    """Score a :class:`DraftProofReport` across five quality dimensions.

    Parameters
    ----------
    report:
        The dict returned by :func:`~integrations.ipfs_datasets.draft_logic_pipeline.run_pipeline`.
    claim_id:
        Optional claim identifier embedded in the output.

    Returns
    -------
    dict
        ``DraftQualityScore`` with the following keys:

        * ``overall_score``     — 0-100 integer
        * ``grade``             — letter grade "A" … "F"
        * ``dimensions``        — dict of per-dimension 0-100 integer scores
        * ``suggestions``       — prioritised list of actionable suggestion dicts
        * ``claim_id``          — echoed back
        * ``scorer_version``    — str
    """
    fact_registry_summary = _extract_fact_registry_summary(report)
    corpus_score = _score_corpus_grounding(report)
    proof_score = _score_proof_completeness(report)
    policy_score = _score_policy_compliance(report)
    contradiction_score = _score_contradiction_free(report)
    theorem_score = _score_theorem_readiness(report)

    overall_score = int(
        round(
            corpus_score * _WEIGHTS["corpus_grounding"]
            + proof_score * _WEIGHTS["proof_completeness"]
            + policy_score * _WEIGHTS["policy_compliance"]
            + contradiction_score * _WEIGHTS["contradiction_free"]
            + theorem_score * _WEIGHTS["theorem_readiness"]
        )
    )

    suggestions = _build_suggestions(
        corpus_score=corpus_score,
        proof_score=proof_score,
        policy_score=policy_score,
        contradiction_score=contradiction_score,
        theorem_score=theorem_score,
        report=report,
    )

    return {
        "overall_score": overall_score,
        "grade": _grade(overall_score),
        "dimensions": {
            "corpus_grounding": corpus_score,
            "proof_completeness": proof_score,
            "policy_compliance": policy_score,
            "contradiction_free": contradiction_score,
            "theorem_readiness": theorem_score,
        },
        "suggestions": suggestions,
        "claim_id": claim_id,
        "scorer_version": QUALITY_SCORER_VERSION,
        "pipeline_version": str(report.get("pipeline_version") or ""),
        "fact_registry_summary": fact_registry_summary,
    }


__all__ = [
    "QUALITY_SCORER_VERSION",
    "score_draft_quality",
]
