"""Lean 4 and Coq theorem export for TDFOL/DCEC formula sets.

This module translates the TDFOL (Temporal Domain First-Order Logic) and DCEC
(Deontic Cognitive Event Calculus) formula strings produced by the hybrid
reasoning pipeline into syntactically valid Lean 4 and Coq proof stubs.

Each formula is emitted as a ``sorry``-bodied theorem stub (Lean 4) or a
``Hypothesis`` declaration (Coq) so that a human or automated prover can
fill in the proof obligations.

Typical call pattern::

    from integrations.ipfs_datasets.theorem_export import export_formulas_to_lean4, export_formulas_to_coq

    lean_src = export_formulas_to_lean4(tdfol_formulas, dcec_formulas, claim_id="my-claim")
    coq_src = export_formulas_to_coq(tdfol_formulas, dcec_formulas, claim_id="my-claim")

The exported sources are pure text strings suitable for writing to ``*.lean``
or ``*.v`` files and loading in Lean 4 / Coq tool-chains.
"""

from __future__ import annotations

import re
import textwrap
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

THEOREM_EXPORT_VERSION = "theorem-export-v1"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")
_SYMBOL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")

# Known TDFOL/DCEC predicate arities used in the generated declarations.
_LEAN4_PREDICATE_DECLARATIONS = """\
  -- Core temporal predicates
  variable (AtTime : Time → Prop)
  variable (Fact : Event → Time → Prop)
  variable (Happens : Event → Time → Prop)
  variable (HoldsDuring : Event → Time → Time → Prop)
  variable (Observed : Event → Prop)
  variable (Approximate : Event → Prop)
  variable (ApproximateTime : Event → Prop)
  variable (Before : Event → Event → Prop)
  variable (After : Event → Event → Prop)
  variable (SameTime : Event → Event → Prop)
  variable (Overlaps : Event → Event → Prop)
  variable (During : Time → Time → Time → Prop)
  -- Support / claim predicates
  variable (Supports : Support → Claim → Prop)
  variable (EvidenceLead : Support → Time → Prop)
  variable (Available : Support → Time → Prop)
  variable (AvailableDuring : Support → Time → Time → Prop)
  -- Conflict predicates
  variable (Conflict : Event → Event → Prop)
  variable (Conflicts : Event → Event → Prop)
  -- Deontic predicates (obligation O, permission P, prohibition F)
  variable (O : Actor → Action → Prop)
  variable (P : Actor → Action → Prop)
  variable (F : Actor → Action → Prop)\
"""

_COQ_PREDICATE_DECLARATIONS = """\
Variable AtTime : Time -> Prop.
Variable Fact : Event -> Time -> Prop.
Variable Happens : Event -> Time -> Prop.
Variable HoldsDuring : Event -> Time -> Time -> Prop.
Variable Observed : Event -> Prop.
Variable Approximate : Event -> Prop.
Variable ApproximateTime : Event -> Prop.
Variable Before : Event -> Event -> Prop.
Variable After : Event -> Event -> Prop.
Variable SameTime : Event -> Event -> Prop.
Variable Overlaps : Event -> Event -> Prop.
Variable During : Time -> Time -> Time -> Prop.
Variable Supports : Support -> Claim -> Prop.
Variable EvidenceLead : Support -> Time -> Prop.
Variable Available : Support -> Time -> Prop.
Variable AvailableDuring : Support -> Time -> Time -> Prop.
Variable Conflict : Event -> Event -> Prop.
Variable Conflicts : Event -> Event -> Prop.
Variable O : Actor -> Action -> Prop.
Variable P : Actor -> Action -> Prop.
Variable F : Actor -> Action -> Prop.\
"""


def _to_ident(name: str) -> str:
    """Convert *name* to a valid Lean/Coq identifier."""
    cleaned = _IDENT_RE.sub("_", str(name or "")).strip("_")
    if not cleaned:
        return "x"
    if cleaned[0].isdigit():
        cleaned = f"v_{cleaned}"
    return cleaned


def _formula_to_lean4_comment(formula: str) -> str:
    return f"  -- {formula}"


def _formula_to_lean4_hypothesis(index: int, formula: str) -> str:
    """Emit a single Lean 4 axiom for *formula*."""
    ident = f"axiom_formula_{index}"
    # Collect all identifiers in the formula and declare them as variables.
    symbols = sorted({_to_ident(m) for m in _SYMBOL_RE.findall(formula)})
    # Heuristic: single-character upper-case → Type, lower-case → term variable.
    # We emit a simple sorry-proof stub; users replace sorry with real proofs.
    lean_formula = _tdfol_to_lean4(formula)
    return f"  axiom {ident} : {lean_formula}"


def _formula_to_coq_hypothesis(index: int, formula: str) -> str:
    """Emit a single Coq Hypothesis for *formula*."""
    ident = f"formula_{index}"
    coq_formula = _tdfol_to_coq(formula)
    return f"Hypothesis {ident} : {coq_formula}."


# ---------------------------------------------------------------------------
# TDFOL → Lean 4 / Coq surface-syntax translators
#
# These translators handle the small subset of TDFOL/DCEC syntax produced by
# _build_temporal_reasoning_payload() in logic.py:
#
#   forall t (Pred(a,b) -> Pred2(c,t))
#   Pred(a,b)
#   Pred(a,b) and Pred2(c)
# ---------------------------------------------------------------------------

def _tdfol_to_lean4(formula: str) -> str:
    """Translate a TDFOL formula string to Lean 4 surface syntax."""
    formula = formula.strip()
    # forall t (...) → ∀ t : Time, ...  (non-greedy inner capture)
    formula = re.sub(
        r"\bforall\s+(\w+)\s*\((.+?)\)\s*$",
        lambda m: f"∀ ({_to_ident(m.group(1))} : Time), {_tdfol_to_lean4(m.group(2))}",
        formula,
    )
    # implication: A -> B
    formula = re.sub(r"\s+->\s+", " → ", formula)
    # conjunction: A and B
    formula = re.sub(r"\s+and\s+", " ∧ ", formula, flags=re.IGNORECASE)
    # Predicate(a,b) → Predicate a b  (Lean 4 application syntax)
    formula = re.sub(
        r"(\b[A-Za-z_][A-Za-z0-9_]*\b)\(([^)]+)\)",
        lambda m: _lean4_apply(m.group(1), m.group(2)),
        formula,
    )
    return formula


def _lean4_apply(pred: str, args_str: str) -> str:
    """Convert ``Pred(a,b,c)`` → ``Pred a b c``."""
    args = [_to_ident(a.strip()) for a in args_str.split(",")]
    return f"{pred} {' '.join(args)}"


def _tdfol_to_coq(formula: str) -> str:
    """Translate a TDFOL formula string to Coq surface syntax."""
    formula = formula.strip()
    # forall t (...) → forall t : Time, ...  (non-greedy inner capture)
    formula = re.sub(
        r"\bforall\s+(\w+)\s*\((.+?)\)\s*$",
        lambda m: f"forall ({_to_ident(m.group(1))} : Time), {_tdfol_to_coq(m.group(2))}",
        formula,
    )
    # implication: A -> B  (already valid Coq)
    formula = re.sub(r"\s+and\s+", " /\\ ", formula, flags=re.IGNORECASE)
    # Predicate(a,b) → Predicate a b  (Coq application syntax)
    formula = re.sub(
        r"(\b[A-Za-z_][A-Za-z0-9_]*\b)\(([^)]+)\)",
        lambda m: _coq_apply(m.group(1), m.group(2)),
        formula,
    )
    return formula


def _coq_apply(pred: str, args_str: str) -> str:
    """Convert ``Pred(a,b,c)`` → ``Pred a b c``."""
    args = [_to_ident(a.strip()) for a in args_str.split(",")]
    return f"{pred} {' '.join(args)}"


# ---------------------------------------------------------------------------
# Public export functions
# ---------------------------------------------------------------------------

def export_formulas_to_lean4(
    tdfol_formulas: Sequence[str],
    dcec_formulas: Optional[Sequence[str]] = None,
    *,
    claim_id: str = "",
    module_name: str = "ComplaintProof",
    exported_at: Optional[str] = None,
) -> str:
    """Render TDFOL/DCEC formula lists as a Lean 4 module.

    Parameters
    ----------
    tdfol_formulas:
        Sequence of TDFOL formula strings (the ``tdfol_formulas`` field from
        the temporal reasoning payload).
    dcec_formulas:
        Optional sequence of DCEC formula strings.  If provided they are
        emitted in a separate axiom block after the TDFOL axioms.
    claim_id:
        Optional claim identifier embedded as a comment in the module header.
    module_name:
        The Lean 4 ``namespace`` name.  Defaults to ``"ComplaintProof"``.
    exported_at:
        ISO-8601 timestamp string.  Defaults to the current UTC time.

    Returns
    -------
    str
        Complete Lean 4 source text.
    """
    timestamp = exported_at or datetime.now(tz=timezone.utc).isoformat()
    tdfol_list = [str(f).strip() for f in (tdfol_formulas or []) if str(f).strip()]
    dcec_list = [str(f).strip() for f in (dcec_formulas or []) if str(f).strip()]

    lines: List[str] = [
        f"-- Auto-generated by complaint-generator {THEOREM_EXPORT_VERSION}",
        f"-- exported_at: {timestamp}",
    ]
    if claim_id:
        lines.append(f"-- claim_id: {claim_id}")
    lines += [
        "-- NOTE: Every theorem stub uses `sorry`.  Replace with real proofs.",
        "",
        "import Mathlib.Logic.Basic",
        "",
        f"namespace {module_name}",
        "",
        "-- Type universe declarations",
        "variable (Time Event Support Claim Actor Action : Type)",
        "",
        "-- Predicate declarations",
        _LEAN4_PREDICATE_DECLARATIONS,
        "",
    ]

    if tdfol_list:
        lines += [
            "-- ── TDFOL axioms ──────────────────────────────────────────────",
        ]
        for index, formula in enumerate(tdfol_list, start=1):
            lines.append(_formula_to_lean4_comment(formula))
            lines.append(_formula_to_lean4_hypothesis(index, formula))
        lines.append("")

    if dcec_list:
        lines += [
            "-- ── DCEC axioms ───────────────────────────────────────────────",
        ]
        tdfol_count = len(tdfol_list)
        for index, formula in enumerate(dcec_list, start=tdfol_count + 1):
            lines.append(_formula_to_lean4_comment(formula))
            lines.append(_formula_to_lean4_hypothesis(index, formula))
        lines.append("")

    if not tdfol_list and not dcec_list:
        lines.append("  -- No formulas to export.")
        lines.append("")

    lines.append(f"end {module_name}")
    return "\n".join(lines) + "\n"


def export_formulas_to_coq(
    tdfol_formulas: Sequence[str],
    dcec_formulas: Optional[Sequence[str]] = None,
    *,
    claim_id: str = "",
    module_name: str = "ComplaintProof",
    exported_at: Optional[str] = None,
) -> str:
    """Render TDFOL/DCEC formula lists as a Coq source file.

    Parameters
    ----------
    tdfol_formulas:
        Sequence of TDFOL formula strings.
    dcec_formulas:
        Optional sequence of DCEC formula strings.
    claim_id:
        Optional claim identifier embedded as a comment in the file header.
    module_name:
        The Coq ``Module`` name.  Defaults to ``"ComplaintProof"``.
    exported_at:
        ISO-8601 timestamp string.  Defaults to the current UTC time.

    Returns
    -------
    str
        Complete Coq (``.v``) source text.
    """
    timestamp = exported_at or datetime.now(tz=timezone.utc).isoformat()
    tdfol_list = [str(f).strip() for f in (tdfol_formulas or []) if str(f).strip()]
    dcec_list = [str(f).strip() for f in (dcec_formulas or []) if str(f).strip()]

    lines: List[str] = [
        f"(* Auto-generated by complaint-generator {THEOREM_EXPORT_VERSION} *)",
        f"(* exported_at: {timestamp} *)",
    ]
    if claim_id:
        lines.append(f"(* claim_id: {claim_id} *)")
    lines += [
        "(* NOTE: Each hypothesis is declared as an axiom.  Prove with Proof. *)",
        "",
        "Require Import Coq.Logic.Classical.",
        "",
        f"Module {module_name}.",
        "",
        "(* Type universe declarations *)",
        "Variable Time Event Support Claim Actor Action : Type.",
        "",
        "(* Predicate declarations *)",
        _COQ_PREDICATE_DECLARATIONS,
        "",
    ]

    if tdfol_list:
        lines += [
            "(* ── TDFOL axioms ──────────────────────────────────────── *)",
        ]
        for index, formula in enumerate(tdfol_list, start=1):
            lines.append(f"(* {formula} *)")
            lines.append(_formula_to_coq_hypothesis(index, formula))
        lines.append("")

    if dcec_list:
        lines += [
            "(* ── DCEC axioms ───────────────────────────────────────── *)",
        ]
        tdfol_count = len(tdfol_list)
        for index, formula in enumerate(dcec_list, start=tdfol_count + 1):
            lines.append(f"(* {formula} *)")
            lines.append(_formula_to_coq_hypothesis(index, formula))
        lines.append("")

    if not tdfol_list and not dcec_list:
        lines.append("(* No formulas to export. *)")
        lines.append("")

    lines.append(f"End {module_name}.")
    return "\n".join(lines) + "\n"


def export_proof_result_to_theorems(
    proof_result: Dict[str, Any],
    *,
    claim_id: str = "",
    exported_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract TDFOL/DCEC formulas from *proof_result* and export to both targets.

    ``proof_result`` is expected to be the dict returned by
    :func:`integrations.ipfs_datasets.logic.prove_claim_elements` or
    :func:`run_hybrid_reasoning`.

    Returns a ``theorem_export`` dict with keys:

    * ``lean4`` — Lean 4 source string
    * ``coq`` — Coq source string
    * ``tdfol_formula_count`` — int
    * ``dcec_formula_count`` — int
    * ``export_version`` — str
    * ``exported_at`` — ISO-8601 timestamp
    """
    timestamp = exported_at or datetime.now(tz=timezone.utc).isoformat()

    # Pull formulas from the temporal_reasoning_payload layer.
    temporal_payload: Dict[str, Any] = {}
    if isinstance(proof_result.get("temporal_reasoning_payload"), dict):
        temporal_payload = proof_result["temporal_reasoning_payload"]
    elif isinstance((proof_result.get("result") or {}).get("temporal_reasoning_payload"), dict):
        temporal_payload = proof_result["result"]["temporal_reasoning_payload"]

    proof_bundle_payload: Dict[str, Any] = {}
    proof_bundles = proof_result.get("proof_bundles")
    if isinstance(proof_bundles, dict):
        for bundle in proof_bundles.values():
            if isinstance(bundle, dict) and isinstance(bundle.get("theorem_exports"), dict):
                proof_bundle_payload = bundle["theorem_exports"]
                if not claim_id:
                    claim_id = str(bundle.get("proof_bundle_id") or "")
                break
    if not proof_bundle_payload and isinstance(proof_result.get("temporal_proof_bundle"), dict):
        bundle = proof_result["temporal_proof_bundle"]
        if isinstance(bundle.get("theorem_exports"), dict):
            proof_bundle_payload = bundle["theorem_exports"]
            if not claim_id:
                claim_id = str(bundle.get("proof_bundle_id") or "")

    # Also check the result sub-dict (run_hybrid_reasoning layout).
    result_inner = proof_result.get("result") or {}
    tdfol_formulas: List[str] = list(
        proof_bundle_payload.get("tdfol_formulas")
        or temporal_payload.get("tdfol_formulas")
        or result_inner.get("tdfol_formulas")
        or []
    )
    dcec_formulas: List[str] = list(
        proof_bundle_payload.get("dcec_formulas")
        or temporal_payload.get("dcec_formulas")
        or result_inner.get("dcec_formulas")
        or []
    )
    fact_registry_summary = {}
    for candidate in (
        proof_result.get("fact_registry_summary"),
        temporal_payload.get("fact_registry_summary"),
        result_inner.get("fact_registry_summary") if isinstance(result_inner, dict) else {},
    ):
        if isinstance(candidate, dict):
            fact_registry_summary = dict(candidate)
            break

    lean4_src = export_formulas_to_lean4(
        tdfol_formulas,
        dcec_formulas,
        claim_id=claim_id,
        exported_at=timestamp,
    )
    coq_src = export_formulas_to_coq(
        tdfol_formulas,
        dcec_formulas,
        claim_id=claim_id,
        exported_at=timestamp,
    )

    return {
        "lean4": lean4_src,
        "coq": coq_src,
        "tdfol_formula_count": len(tdfol_formulas),
        "dcec_formula_count": len(dcec_formulas),
        "export_version": THEOREM_EXPORT_VERSION,
        "exported_at": timestamp,
        "fact_registry_summary": fact_registry_summary,
    }


__all__ = [
    "THEOREM_EXPORT_VERSION",
    "export_formulas_to_lean4",
    "export_formulas_to_coq",
    "export_proof_result_to_theorems",
]
