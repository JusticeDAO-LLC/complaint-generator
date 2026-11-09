"""Draft-text → Formal Logic → Theorem Prover pipeline.

Orchestrates the full proof pipeline for a complaint draft body:

    Step A  text_to_fol(body)              → FOL predicates
    Step B  legal_text_to_deontic(body)    → deontic norms
    Step C  constrain_assertions_to_corpus → ground assertions in legal corpus
    Step D  prove_claim_elements(preds)    → hybrid reasoner + Z3 prover
    Step E  check_policy_rules_with_deontic_norms → deontic violation check

The result is a :class:`DraftProofReport` (plain dict) that the workspace
injects into ``_build_mike_sync_diagnostics()`` via the ``logic_review``
parameter.

Additional utilities:

* :func:`render_proof_report` — render a ``DraftProofReport`` as a human-readable
  Markdown document suitable for display in the complaint editor or export.
* :func:`pin_proof_report_to_ipfs` — pin a ``DraftProofReport`` (plus its
  Lean 4 / Coq theorem exports) to IPFS for immutable provenance tracking.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .legal import constrain_assertions_to_corpus
from .logic import (
    legal_text_to_deontic,
    prove_claim_elements,
    text_to_fol,
)
from .policy_rules import check_policy_rules_with_deontic_norms

DRAFT_LOGIC_PIPELINE_VERSION = "draft-logic-pipeline-v1"


def _extract_text_assertions(body: str) -> List[Dict[str, Any]]:
    """Split *body* into per-sentence assertion dicts."""
    import re

    sentence_re = re.compile(r"(?<=[.!?])\s+|\n+")
    assertions: List[Dict[str, Any]] = []
    for index, sentence in enumerate(sentence_re.split(body), start=1):
        text = sentence.strip()
        if text:
            assertions.append({"assertion_id": f"sent-{index}", "text": text})
    return assertions


def _summarize_support_facts(support_facts: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    facts = [fact for fact in (support_facts or []) if isinstance(fact, dict)]
    source_family_counts: Dict[str, int] = {}
    artifact_family_counts: Dict[str, int] = {}
    corpus_family_counts: Dict[str, int] = {}
    content_origin_counts: Dict[str, int] = {}
    parse_source_counts: Dict[str, int] = {}
    input_format_counts: Dict[str, int] = {}
    unique_fact_ids = set()
    unique_source_refs = set()
    passage_anchored_count = 0

    def _count(target: Dict[str, int], value: Any) -> None:
        text = str(value or "").strip()
        if text:
            target[text] = target.get(text, 0) + 1

    for fact in facts:
        fact_id = str(fact.get("fact_id") or "").strip()
        if fact_id:
            unique_fact_ids.add(fact_id)
        source_ref = str(fact.get("source_ref") or "").strip()
        if source_ref:
            unique_source_refs.add(source_ref)
        source_passage = fact.get("source_passage") if isinstance(fact.get("source_passage"), dict) else {}
        if fact.get("chunk_id") or source_passage.get("chunk_id"):
            passage_anchored_count += 1

        _count(source_family_counts, fact.get("source_family"))
        _count(artifact_family_counts, fact.get("artifact_family"))
        _count(corpus_family_counts, fact.get("corpus_family"))
        _count(content_origin_counts, fact.get("content_origin"))
        _count(parse_source_counts, fact.get("parse_source"))
        _count(input_format_counts, fact.get("input_format"))

    return {
        "fact_count": len(facts),
        "unique_fact_count": len(unique_fact_ids),
        "unique_source_ref_count": len(unique_source_refs),
        "passage_anchored_count": passage_anchored_count,
        "source_family_counts": source_family_counts,
        "artifact_family_counts": artifact_family_counts,
        "corpus_family_counts": corpus_family_counts,
        "content_origin_counts": content_origin_counts,
        "parse_source_counts": parse_source_counts,
        "input_format_counts": input_format_counts,
    }


def run_pipeline(
    body: str,
    *,
    state: Optional[str] = None,
    allow_live_scrape_fallback: bool = False,
    support_facts: Optional[List[Dict[str, Any]]] = None,
    fact_registry_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the full draft-logic pipeline on *body*.

    Parameters
    ----------
    body:
        The full draft complaint body text.
    state:
        Optional two-letter US state code used to narrow state-law corpus
        searches inside :func:`constrain_assertions_to_corpus`.
    allow_live_scrape_fallback:
        Whether to permit live-scrape calls for corpus searches.  Defaults to
        ``False`` so the pipeline stays fast in offline / test environments.

    Returns
    -------
    dict
        A ``DraftProofReport`` dict with the following keys:

        * ``proof_status`` — ``"passed"`` | ``"needs_review"`` | ``"error"``
        * ``contradiction_count`` — integer
        * ``chronology_blocked`` — bool
        * ``ungrounded_assertions`` — list of ungrounded assertion dicts
        * ``corpus_coverage_percent`` — int or None
        * ``norms`` — deontic norms extracted from the draft
        * ``policy_violations`` — list of deontic violation dicts
        * ``policy_warnings`` — list of deontic warning dicts
        * ``has_blockers`` — bool
        * ``pipeline_version`` — str
    """
    errors: List[str] = []
    normalized_fact_registry_summary = (
        dict(fact_registry_summary)
        if isinstance(fact_registry_summary, dict)
        else _summarize_support_facts(support_facts)
    )
    normalized_fact_registry_summary.setdefault("registry_version", "claim_fact_registry_summary.v1")
    normalized_fact_registry_summary.setdefault("source", "claim_support_facts")

    # ------------------------------------------------------------------
    # Step A — text → FOL predicates
    # ------------------------------------------------------------------
    fol_result: Dict[str, Any] = {}
    predicates: List[Dict[str, Any]] = []
    try:
        fol_result = text_to_fol(body)
        predicates = list(fol_result.get("predicates") or [])
    except Exception as exc:
        errors.append(f"text_to_fol: {exc}")

    # ------------------------------------------------------------------
    # Step B — legal text → deontic norms
    # ------------------------------------------------------------------
    deontic_result: Dict[str, Any] = {}
    norms: List[Dict[str, Any]] = []
    try:
        deontic_result = legal_text_to_deontic(body)
        norms = list(deontic_result.get("norms") or [])
    except Exception as exc:
        errors.append(f"legal_text_to_deontic: {exc}")

    # ------------------------------------------------------------------
    # Step C — constrain assertions to legal corpus
    # ------------------------------------------------------------------
    corpus_result: Dict[str, Any] = {}
    ungrounded_assertions: List[Dict[str, Any]] = []
    corpus_coverage_percent: Optional[int] = None
    try:
        assertions = _extract_text_assertions(body)
        corpus_result = constrain_assertions_to_corpus(
            assertions,
            state=state,
            allow_live_scrape_fallback=allow_live_scrape_fallback,
        )
        ungrounded_assertions = list(corpus_result.get("ungrounded") or [])
        corpus_coverage_percent = corpus_result.get("corpus_coverage_percent")
    except Exception as exc:
        errors.append(f"constrain_assertions_to_corpus: {exc}")

    # ------------------------------------------------------------------
    # Step D — prove claim elements via hybrid reasoner
    # ------------------------------------------------------------------
    proof_result: Dict[str, Any] = {}
    proof_status = "needs_review"
    contradiction_count = 0
    chronology_blocked = False
    theorem_export: Dict[str, Any] = {}
    try:
        proof_result = prove_claim_elements(predicates)
        proof_status = str(
            proof_result.get("proof_status")
            or (proof_result.get("proof_artifact") or {}).get("proof_status")
            or "needs_review"
        )
        contradiction_count = int(
            proof_result.get("contradiction_signal_count")
            or proof_result.get("contradiction_count")
            or 0
        )
        theorem_meta = dict(
            (proof_result.get("proof_artifact") or {}).get("theorem_export_metadata")
            or (proof_result.get("temporal_reasoning_payload") or {}).get("theorem_export_metadata")
            or {}
        )
        chronology_blocked = bool(theorem_meta.get("chronology_blocked"))
        # Carry through the Lean 4 / Coq export from prove_claim_elements.
        theorem_export = dict(proof_result.get("theorem_export") or {})
    except Exception as exc:
        errors.append(f"prove_claim_elements: {exc}")

    # ------------------------------------------------------------------
    # Step E — deontic policy rule check
    # ------------------------------------------------------------------
    policy_result: Dict[str, Any] = {}
    policy_violations: List[Dict[str, Any]] = []
    policy_warnings: List[Dict[str, Any]] = []
    try:
        policy_result = check_policy_rules_with_deontic_norms(body, norms=norms or None)
        policy_violations = list(policy_result.get("violations") or [])
        policy_warnings = list(policy_result.get("warnings") or [])
    except Exception as exc:
        errors.append(f"check_policy_rules_with_deontic_norms: {exc}")

    # ------------------------------------------------------------------
    # Assemble DraftProofReport
    # ------------------------------------------------------------------
    has_blockers = bool(
        contradiction_count
        or chronology_blocked
        or policy_violations
        or (proof_status in {"error", "failed", "violation"})
    )

    return {
        "proof_status": proof_status,
        "contradiction_count": contradiction_count,
        "chronology_blocked": chronology_blocked,
        "ungrounded_assertions": ungrounded_assertions,
        "ungrounded_assertion_count": len(ungrounded_assertions),
        "corpus_coverage_percent": corpus_coverage_percent,
        "norms": norms,
        "policy_violations": policy_violations,
        "policy_warnings": policy_warnings,
        "has_blockers": has_blockers,
        "predicate_count": len(predicates),
        "fact_registry_summary": normalized_fact_registry_summary,
        "theorem_export": theorem_export,
        "pipeline_version": DRAFT_LOGIC_PIPELINE_VERSION,
        "errors": errors,
        # Carry through sub-results for downstream consumers.
        "fol_result": fol_result,
        "deontic_result": deontic_result,
        "corpus_result": corpus_result,
        "proof_result": proof_result,
        "policy_result": policy_result,
    }


# ---------------------------------------------------------------------------
# Proof report renderer
# ---------------------------------------------------------------------------

def render_proof_report(
    report: Dict[str, Any],
    *,
    claim_id: str = "",
    rendered_at: Optional[str] = None,
) -> str:
    """Render a ``DraftProofReport`` as a human-readable Markdown document.

    Parameters
    ----------
    report:
        The dict returned by :func:`run_pipeline`.
    claim_id:
        Optional claim or case identifier embedded in the report header.
    rendered_at:
        ISO-8601 timestamp.  Defaults to the current UTC time.

    Returns
    -------
    str
        Markdown-formatted proof report suitable for display or export.
    """
    timestamp = rendered_at or datetime.now(tz=timezone.utc).isoformat()
    lines: List[str] = []

    # Header
    lines.append("# Complaint Draft Proof Report")
    if claim_id:
        lines.append(f"**Claim ID:** {claim_id}")
    lines.append(f"**Generated:** {timestamp}")
    lines.append(f"**Pipeline version:** {report.get('pipeline_version', DRAFT_LOGIC_PIPELINE_VERSION)}")
    lines.append("")

    # Status summary
    proof_status = str(report.get("proof_status") or "needs_review")
    status_icon = {"passed": "✅", "needs_review": "⚠️", "error": "❌", "failed": "❌"}.get(
        proof_status, "⚠️"
    )
    lines.append(f"## Status: {status_icon} `{proof_status}`")
    lines.append("")

    has_blockers = bool(report.get("has_blockers"))
    if has_blockers:
        lines.append("> **⛔ This draft has blockers that must be resolved before filing.**")
    else:
        lines.append("> **✔ No blockers found.  Draft may proceed.**")
    lines.append("")

    # Key metrics
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Predicates extracted | {report.get('predicate_count', 0)} |")
    contradiction_count = int(report.get("contradiction_count") or 0)
    lines.append(f"| Contradictions | {contradiction_count} |")
    chronology_blocked = bool(report.get("chronology_blocked"))
    lines.append(f"| Chronology blocked | {'Yes' if chronology_blocked else 'No'} |")
    coverage = report.get("corpus_coverage_percent")
    lines.append(f"| Corpus coverage | {f'{coverage}%' if coverage is not None else 'n/a'} |")
    fact_registry_summary = report.get("fact_registry_summary") if isinstance(report.get("fact_registry_summary"), dict) else {}
    lines.append(f"| Support facts | {int(fact_registry_summary.get('fact_count') or 0)} |")
    lines.append(f"| Passage-anchored facts | {int(fact_registry_summary.get('passage_anchored_count') or 0)} |")
    norms = list(report.get("norms") or [])
    lines.append(f"| Deontic norms found | {len(norms)} |")
    violations = list(report.get("policy_violations") or [])
    warnings = list(report.get("policy_warnings") or [])
    lines.append(f"| Policy violations | {len(violations)} |")
    lines.append(f"| Policy warnings | {len(warnings)} |")
    lines.append("")

    # Ungrounded assertions
    ungrounded = list(report.get("ungrounded_assertions") or [])
    if ungrounded:
        lines.append("## ⚠ Ungrounded Assertions")
        lines.append("")
        lines.append(
            "The following assertions could not be matched to any authoritative legal corpus document."
        )
        lines.append("Each must be grounded in a statute, regulation, or case before filing.")
        lines.append("")
        for item in ungrounded:
            assertion_id = str(item.get("assertion_id") or item.get("id") or "")
            text = str(item.get("text") or "").strip()
            prefix = f"**[{assertion_id}]** " if assertion_id else ""
            lines.append(f"- {prefix}{text}")
        lines.append("")

    # Contradictions
    if contradiction_count:
        lines.append("## ❌ Contradictions")
        lines.append("")
        proof_result = dict(report.get("proof_result") or {})
        contradiction_list = list(proof_result.get("contradictions") or [])
        if contradiction_list:
            for c in contradiction_list:
                cid = str(c.get("contradiction_id") or "")
                summary = str(c.get("summary") or "")
                severity = str(c.get("severity") or "warning")
                icon = "❌" if severity == "error" else "⚠️"
                lines.append(f"- {icon} **[{cid}]** {summary}")
        else:
            lines.append(f"- {contradiction_count} contradiction(s) detected.")
        lines.append("")

    # Policy violations
    if violations:
        lines.append("## ❌ Policy Violations")
        lines.append("")
        for v in violations:
            vtype = str(v.get("violation_type") or "violation")
            offending = str(v.get("offending_sentence") or "").strip()
            lines.append(f"- **{vtype}**: _{offending}_")
        lines.append("")

    # Policy warnings
    if warnings:
        lines.append("## ⚠ Policy Warnings")
        lines.append("")
        for w in warnings:
            wtype = str(w.get("warning_type") or "warning")
            formula = str(w.get("formula") or "").strip()
            suffix = f" (`{formula}`)" if formula else ""
            lines.append(f"- **{wtype}**{suffix}")
        lines.append("")

    # Deontic norms summary
    if norms:
        lines.append("## Deontic Norms Detected")
        lines.append("")
        for norm in norms:
            norm_type = str(norm.get("norm_type") or "").capitalize()
            formula = str(norm.get("formula") or "").strip()
            trigger = str(norm.get("trigger_keyword") or "").strip()
            detail = formula or trigger
            lines.append(f"- **{norm_type}**: `{detail}`")
        lines.append("")

    # Theorem export summary
    theorem_export = dict(report.get("theorem_export") or {})
    tdfol_count = int(theorem_export.get("tdfol_formula_count") or 0)
    dcec_count = int(theorem_export.get("dcec_formula_count") or 0)
    if tdfol_count or dcec_count:
        lines.append("## Theorem Export")
        lines.append("")
        lines.append(f"- TDFOL formulas: {tdfol_count}")
        lines.append(f"- DCEC formulas: {dcec_count}")
        export_version = str(theorem_export.get("export_version") or "")
        if export_version:
            lines.append(f"- Export version: `{export_version}`")
        lean4_present = bool(theorem_export.get("lean4"))
        coq_present = bool(theorem_export.get("coq"))
        if lean4_present:
            lines.append("- Lean 4 stub: available")
        if coq_present:
            lines.append("- Coq stub: available")
        lines.append("")

    # Pipeline errors
    errors = list(report.get("errors") or [])
    if errors:
        lines.append("## Pipeline Errors")
        lines.append("")
        for err in errors:
            lines.append(f"- `{err}`")
        lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# IPFS provenance pinning
# ---------------------------------------------------------------------------

def _pin_private_proof_report(report: Dict[str, Any], private_context: Dict[str, Any], *, claim_id: str, pinned_at: str) -> Dict[str, Any]:
    """Seal report and full theorem sources; private failures never fall back."""
    from integrations.ipfs_datasets.storage import store_automatic_private_artifact
    from integrations.private_storage import PrivateKeyLockedError

    empty = {"report_cid": "", "lean4_cid": "", "coq_cid": "", "pinned": False,
             "backend": "private", "pinned_at": pinned_at, "claim_id": "", "stored_local": False,
             "uploaded": False, "verified": False, "replicated": False, "deferred": False,
             "network_durable": False, "private_artifact": True, "plaintext_exported": False,
             "overwrites_existing": False}
    if not isinstance(private_context, dict):
        return {**empty, "status": "recoverable", "deferred": True, "code": "private_context_invalid"}
    missing_key = private_context.get("key") is None and private_context.get("key_provider") is None
    if private_context.get("locked") or missing_key:
        return {**empty, "status": "unlock_needed"}
    artifacts: dict[str, Any] = {}
    try:
        theorem_export = dict(report.get("theorem_export") or {})
        pieces = {
            "proof-history": json.dumps(report, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"),
            "theorem-source": json.dumps({"lean4": theorem_export.get("lean4") or "", "coq": theorem_export.get("coq") or "",
                                           "errors": list(report.get("errors") or [])}, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        }
        for kind, payload in pieces.items():
            artifacts[kind] = store_automatic_private_artifact(
                payload, access=private_context["access"], tenant_id=str(private_context["tenant_id"]),
                case_id=str(private_context["case_id"]), artifact_kind=kind,
                revision=str(private_context.get("revision") or "proof-1") + ":" + kind,
                principal_id=str(private_context.get("principal_id") or private_context["tenant_id"]),
                key=private_context.get("key"), key_id=private_context.get("key_id"),
                key_provider=private_context.get("key_provider"), backend=private_context.get("backend"),
                backend_name=private_context.get("backend_name"), pin_content=bool(private_context.get("pin_content", True)),
            )
    except Exception as exc:
        return {**empty, "status": "unlock_needed" if isinstance(exc, PrivateKeyLockedError) else "recoverable",
                "deferred": not isinstance(exc, PrivateKeyLockedError), "error": type(exc).__name__,
                "code": str(getattr(exc, "code", "") or "private_proof_failed"), "artifacts": artifacts}
    report_pin, theorem_pin = artifacts["proof-history"], artifacts["theorem-source"]
    complete = all(item.get("verified") is True and item.get("status") in {"available", "degraded"} for item in artifacts.values())
    if not complete:
        return {**empty, "status": "recoverable", "deferred": True,
                "code": "private_proof_incomplete", "artifacts": artifacts}
    return {
        **empty, "report_cid": str(report_pin.get("cid") or ""),
        "lean4_cid": str(theorem_pin.get("cid") or "") if theorem_export.get("lean4") else "",
        "coq_cid": str(theorem_pin.get("cid") or "") if theorem_export.get("coq") else "",
        "claim_id": claim_id, "pinned": all(item.get("pinned") is True for item in artifacts.values()),
        "stored_local": all(item.get("stored_local") is True for item in artifacts.values()),
        "uploaded": all(item.get("uploaded") is True for item in artifacts.values()), "verified": True,
        "deferred": any(item.get("deferred") is True for item in artifacts.values()),
        "network_durable": all((item.get("receipt") or {}).get("network_durable") is True for item in artifacts.values()),
        "verification": {"matched": True, "method": "all-private-artifact-ciphertext-readbacks"},
        "receipt": dict(report_pin.get("receipt") or {}), "artifacts": artifacts,
        "status": "degraded" if any(item.get("status") == "degraded" for item in artifacts.values()) else "available",
    }


def pin_proof_report_to_ipfs(
    report: Dict[str, Any],
    *,
    claim_id: str = "",
    private_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Pin a ``DraftProofReport`` and its theorem exports to IPFS.

    Serialises the report as JSON and pins it via the workspace IPFS backend
    (``integrations.ipfs_datasets.storage``).  The Lean 4 and Coq theorem
    export strings are pinned as separate blobs so each artifact has its own
    CID.

    When the IPFS backend is unavailable (e.g. in offline / test
    environments) the function falls back gracefully to a local content-hash
    record without raising an exception.

    Parameters
    ----------
    report:
        The dict returned by :func:`run_pipeline`.
    claim_id:
        Optional claim identifier embedded in the pinned JSON envelope.

    Returns
    -------
    dict
        ``{"report_cid": str, "lean4_cid": str, "coq_cid": str,
           "pinned": bool, "backend": str, "pinned_at": str}``
    """
    from .storage import store_bytes, pin_cid

    pinned_at = datetime.now(tz=timezone.utc).isoformat()
    if private_context is not None:
        return _pin_private_proof_report(report, private_context, claim_id=claim_id, pinned_at=pinned_at)

    # Serialise the report envelope (exclude large sub-results to keep the
    # primary blob focused on the DraftProofReport keys).
    envelope: Dict[str, Any] = {
        "claim_id": claim_id,
        "pinned_at": pinned_at,
        "pipeline_version": report.get("pipeline_version", DRAFT_LOGIC_PIPELINE_VERSION),
        "proof_status": report.get("proof_status"),
        "contradiction_count": report.get("contradiction_count"),
        "chronology_blocked": report.get("chronology_blocked"),
        "corpus_coverage_percent": report.get("corpus_coverage_percent"),
        "ungrounded_assertion_count": report.get("ungrounded_assertion_count"),
        "has_blockers": report.get("has_blockers"),
        "predicate_count": report.get("predicate_count"),
        "policy_violation_count": len(list(report.get("policy_violations") or [])),
        "policy_warning_count": len(list(report.get("policy_warnings") or [])),
        "norm_count": len(list(report.get("norms") or [])),
        "errors": list(report.get("errors") or []),
    }

    theorem_export = dict(report.get("theorem_export") or {})
    lean4_src = str(theorem_export.get("lean4") or "")
    coq_src = str(theorem_export.get("coq") or "")

    def _fallback_id(data: bytes) -> str:
        import hashlib
        return "sha256:" + hashlib.sha256(data).hexdigest()

    def _pin_blob(data: bytes, description: str) -> dict[str, Any]:
        del description
        try:
            result = store_bytes(data)
        except Exception as exc:
            return {
                "cid": _fallback_id(data),
                "pinned": False,
                "stored_local": False,
                "uploaded": False,
                "verified": False,
                "replicated": False,
                "deferred": True,
                "network_durable": False,
                "backend": "local_content_hash",
                "error": str(exc),
                "verification": {"matched": False, "method": "none", "reason": "store failed"},
                "receipt": {"cid_kind": "sha256_fallback"},
            }
        if not isinstance(result, dict):
            return {
                "cid": _fallback_id(data),
                "pinned": False,
                "stored_local": False,
                "uploaded": False,
                "verified": False,
                "replicated": False,
                "deferred": True,
                "network_durable": False,
                "backend": "local_content_hash",
                "error": "malformed storage result",
                "verification": {"matched": False, "method": "none", "reason": "malformed storage result"},
                "receipt": {"cid_kind": "sha256_fallback"},
            }
        cid = str(result.get("cid") or "").strip()
        local_only = (
            bool(result.get("stored_local"))
            or result.get("cid_kind") in {"pseudo_cid", "sha256_fallback"}
            or result.get("backend_name") == "local_cache"
            or cid.startswith("sha256:")
        )
        pin_result: dict[str, Any] | None = None
        if cid and not local_only and result.get("pinned") is not True and result.get("status") in {"available", "degraded"}:
            try:
                raw_pin = pin_cid(cid)
                pin_result = raw_pin if isinstance(raw_pin, dict) else {"pinned": False, "status": "error", "error": "malformed pin result"}
            except Exception as exc:
                pin_result = {"pinned": False, "error": str(exc), "status": "error"}
        elif result.get("pinned") is True and not local_only:
            pin_result = result
        network_durable = bool(
            pin_result
            and pin_result.get("pinned") is True
            and pin_result.get("network_durable") is True
            and result.get("verified") is True
            and not local_only
        )
        if not network_durable:
            return {
                "cid": _fallback_id(data),
                "pinned": False,
                "stored_local": result.get("stored_local") is True,
                "uploaded": result.get("uploaded") is True and not local_only,
                "verified": result.get("verified") is True,
                "replicated": result.get("replicated") is True,
                "deferred": True,
                "network_durable": False,
                "backend": "local_content_hash",
                "error": str((pin_result or result).get("error") or result.get("error") or ""),
                "verification": dict(result.get("verification") or {}),
                "receipt": {
                    **dict(result.get("receipt") or {}),
                    "cid_kind": "sha256_fallback",
                    "storage_cid": cid,
                    "storage_backend": result.get("backend_name") or "",
                    "storage_status": result.get("status") or "error",
                    "pin": None if pin_result is None else {
                        "status": pin_result.get("status"),
                        "pinned": False if pin_result.get("pinned") is not True else True,
                        "error": pin_result.get("error"),
                    },
                },
            }
        return {
            "cid": cid,
            "pinned": True,
            "stored_local": False,
            "uploaded": True,
            "verified": True,
            "replicated": False,
            "deferred": False,
            "network_durable": True,
            "backend": "ipfs",
            "error": "",
            "verification": dict(result.get("verification") or {}),
            "receipt": dict(result.get("receipt") or {}),
        }

    report_bytes = json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode("utf-8")
    report_pin = _pin_blob(report_bytes, "DraftProofReport")
    lean4_pin = _pin_blob(lean4_src.encode("utf-8"), "Lean4Export") if lean4_src else None
    coq_pin = _pin_blob(coq_src.encode("utf-8"), "CoqExport") if coq_src else None
    report_cid = str(report_pin["cid"])
    lean4_cid = str(lean4_pin["cid"]) if lean4_pin else ""
    coq_cid = str(coq_pin["cid"]) if coq_pin else ""
    network_pinned = bool(report_pin["pinned"])
    resolved_backend = "ipfs" if network_pinned else "local_content_hash"

    return {
        "report_cid": report_cid,
        "lean4_cid": lean4_cid,
        "coq_cid": coq_cid,
        "pinned": network_pinned,
        "backend": resolved_backend,
        "pinned_at": pinned_at,
        "claim_id": claim_id,
        "stored_local": bool(report_pin["stored_local"]),
        "uploaded": bool(report_pin["uploaded"]),
        "verified": bool(report_pin["verified"]),
        "replicated": bool(report_pin["replicated"]),
        "deferred": bool(report_pin["deferred"]),
        "network_durable": bool(report_pin["network_durable"]),
        "verification": report_pin["verification"],
        "receipt": report_pin["receipt"],
        "artifacts": {
            "report": report_pin,
            "lean4": lean4_pin,
            "coq": coq_pin,
        },
    }


__all__ = [
    "DRAFT_LOGIC_PIPELINE_VERSION",
    "run_pipeline",
    "render_proof_report",
    "pin_proof_report_to_ipfs",
]
