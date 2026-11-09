"""First-party adapter for current source-sampling context and definition evidence.

The sampling-context and contextual definition binding/review owners keep the
replay, population, and correspondence rules. This module only forwards whole
source, context, attachment, and response populations with the caller's
explicit declaration and request hashes. A prepared or replayed context does
not grant applicability, truth, training, graph, or proof authority, and it
does not collapse candidate, source-review, and meaning-review states.

Norm definition evidence and norm scope correspondence are forwarded the same
way. Occurrence, span, entity, and edition identities stay on the owner
records. A governing definition is never filled in when the owner leaves it
unset or when two asserted uses remain separate. Missing or conflicting
evidence stays an explicit unresolved dependency.

Norm interpretation review and bound-variable definition reports are forwarded
through their current owners. Source, edition, meaning, and context permissions
stay separate. This adapter does not sign reviews or turn generated Lean into
a build or a proof unless that owner report already records execution and a
declared prover result matches the source-pinned hashes.

Qualified compact-content and predicate-training outputs are described here as
engineering candidates. Load, score, inspect, and checkpoint identity stay tied
to the caller's exact source-space, conditioning, policy, and checkpoint pins.
Preparation and numerical qualification do not select governing law, close a
definition review, or prove an element.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
from copy import deepcopy
from typing import Any, Mapping

from .loader import import_module_optional


SCHEMA = "complaint-mediator-source-sampling-definition-evidence/v1"

_CONTEXT_MODULE_NAME = "ipfs_datasets_py.logic.autoformal.legal_source_sampling_review_context"
_BINDING_MODULE_NAME = "ipfs_datasets_py.logic.autoformal.legal_source_sampling_context_definition_binding_v2"
_REVIEW_MODULE_NAME = "ipfs_datasets_py.logic.autoformal.legal_source_sampling_context_definition_review_v2"
_DEFINITION_MODULE_NAME = "ipfs_datasets_py.logic.autoformal.legal_norm_definition_evidence_v1"
_SCOPE_MODULE_NAME = "ipfs_datasets_py.logic.autoformal.legal_norm_scope_correspondence_v1"
_NORM_REVIEW_MODULE_NAME = "ipfs_datasets_py.logic.autoformal.legal_norm_interpretation_review_v1"
_BOUND_VARIABLE_MODULE_NAME = "ipfs_datasets_py.logic.autoformal.legal_bound_variable_definition_v1"

_context_module, _context_error = import_module_optional(_CONTEXT_MODULE_NAME)
_binding_module, _binding_error = import_module_optional(_BINDING_MODULE_NAME)
_review_module, _review_error = import_module_optional(_REVIEW_MODULE_NAME)
_definition_module, _definition_error = import_module_optional(_DEFINITION_MODULE_NAME)
_scope_module, _scope_error = import_module_optional(_SCOPE_MODULE_NAME)
_norm_review_module, _norm_review_error = import_module_optional(_NORM_REVIEW_MODULE_NAME)
_bound_variable_module, _bound_variable_error = import_module_optional(_BOUND_VARIABLE_MODULE_NAME)

_CONTEXT_SCHEMA = "legal-source-sampling-review-context/v1"
_RESPONSE_SCHEMA = "legal-source-sampling-context-declaration/v1"
_POPULATION_SCHEMA = "legal-source-sampling-context-population/v1"
_BINDING_SCHEMA = "legal-source-sampling-context-definition-binding/v2"
_REVIEW_SCHEMA = "legal-source-sampling-context-definition-review-correspondence/v1"
_DEFINITION_EVIDENCE_SCHEMA = "legal-norm-definition-evidence/v1"
_SCOPE_CORRESPONDENCE_SCHEMA = "legal-norm-scope-correspondence-report/v1"
_NORM_REVIEW_PREPARATION_SCHEMA = "legal-norm-interpretation-review-evidence/v1"
_NORM_REVIEW_SUBJECT_SCHEMA = "legal-norm-interpretation-review-subject/v1"
_NORM_REVIEW_ASSESSMENT_SCHEMA = "legal-norm-interpretation-review-assessment/v1"
_BOUND_VARIABLE_SCHEMA = "legal-bound-variable-definition-report/v1"
_HANDOFF_SCHEMA = "complaint-mediator-norm-definition-scope-handoff/v1"
_DECISION_HANDOFF_SCHEMA = "complaint-mediator-independent-norm-decision-handoff/v1"
_DECISION_SCHEMAS = {
    _NORM_REVIEW_PREPARATION_SCHEMA,
    _NORM_REVIEW_SUBJECT_SCHEMA,
    _NORM_REVIEW_ASSESSMENT_SCHEMA,
    _BOUND_VARIABLE_SCHEMA,
}
_ACCEPTED_SCHEMAS = {
    _CONTEXT_SCHEMA,
    _RESPONSE_SCHEMA,
    _POPULATION_SCHEMA,
    _BINDING_SCHEMA,
    _REVIEW_SCHEMA,
    _DEFINITION_EVIDENCE_SCHEMA,
    _SCOPE_CORRESPONDENCE_SCHEMA,
    *_DECISION_SCHEMAS,
}

_DENIED_AUTHORITY = {
    "applicability": False,
    "truth": False,
    "training": False,
    "graph": False,
    "proof": False,
}

_PERSISTENT_OWNER = (
    "ipfs_datasets_py.logic.formalization.autoencoder.legal_compact_content_persistent_v1"
)
_PREDICATE_OWNER = (
    "ipfs_datasets_py.logic.formalization.autoencoder.legal_compact_content_predicate_training_v1"
)
QUALIFIED_MODEL_CANDIDATE_SCHEMA = "complaint-mediator-qualified-model-candidate/v1"
_PERSISTENT_SCORE_SCHEMA = "legal-compact-content-persistent-score/v1"
_PREDICATE_CHECKPOINT_SCHEMA = "legal-compact-predicate-training-checkpoint/v1"
_SHA256_TEXT = re.compile(r"[0-9a-f]{64}\Z")
_CANDIDATE_AUTHORITY = {
    "selects_governing_law": False,
    "satisfies_definition_review": False,
    "proves_element": False,
    "governing_law": False,
    "definition_review": False,
    "element_proof": False,
    "semantic_authority": False,
    "proof_authority": False,
}
_REFUSED_MODEL_EFFECTS = (
    "train_compact_content_persistent_v1",
    "training",
    "optimizer",
    "model_download",
    "restore",
    "numerical_fit",
)


def _diagnostic(error: Any) -> dict[str, str] | None:
    if error is None:
        return None
    as_dict = getattr(error, "as_dict", None)
    if callable(as_dict):
        return dict(as_dict())
    return {"error_type": type(error).__name__, "message": str(error)}


def _subject_key(bundle_sha256: Any, subject: Any) -> tuple[Any, ...] | None:
    if not isinstance(subject, dict):
        return None
    return (
        bundle_sha256,
        subject.get("kind"),
        subject.get("index"),
        subject.get("sha256"),
    )


def _nominations(attachments: Any) -> list[dict[str, Any]]:
    if not isinstance(attachments, list):
        return []
    rows = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        nomination = item.get("nomination", item)
        if isinstance(nomination, dict) and "supporting_bundle_sha256" in nomination:
            rows.append(nomination)
    return rows


def _unreviewed_supporting_subjects(owner_result: dict[str, Any], attachments: Any) -> list[dict[str, Any]]:
    """Supporting endpoints that still have no recorded declaration."""

    supporting = []
    seen = set()
    for nomination in _nominations(attachments):
        key = _subject_key(
            nomination.get("supporting_bundle_sha256"),
            nomination.get("supporting_subject_ref"),
        )
        if key is None or key in seen:
            continue
        seen.add(key)
        supporting.append({
            "bundle_sha256": nomination.get("supporting_bundle_sha256"),
            "subject_ref": nomination.get("supporting_subject_ref"),
            "role": nomination.get("role"),
        })
    if not supporting:
        return []
    declared: set[tuple[Any, ...]] = set()
    subjects = owner_result.get("subjects")
    if not isinstance(subjects, list):
        population = owner_result.get("contextual_population")
        if isinstance(population, dict):
            subjects = population.get("subjects")
    if isinstance(subjects, list):
        for row in subjects:
            if isinstance(row, dict) and row.get("response_refs"):
                key = _subject_key(row.get("bundle_sha256"), row.get("subject_ref"))
                if key is not None:
                    declared.add(key)
    return [
        row for row in supporting
        if _subject_key(row["bundle_sha256"], row["subject_ref"]) not in declared
    ]


def _states(owner_result: dict[str, Any]) -> dict[str, Any]:
    """Keep candidate, source-review, and meaning-review observations distinct."""

    schema = owner_result.get("schema")
    if schema == _CONTEXT_SCHEMA:
        return {
            "candidate": "not_a_definition_candidate",
            "source_review": "unreviewed",
            "meaning_review": "unreviewed",
            "context_status": owner_result.get("status"),
        }
    if schema == _RESPONSE_SCHEMA:
        declaration = owner_result.get("declaration")
        source_dispositions = []
        meaning_dispositions = []
        if isinstance(declaration, dict):
            for row in declaration.get("source_answers") or []:
                if isinstance(row, dict):
                    source_dispositions.append(row.get("disposition"))
            for row in declaration.get("meaning_proposals") or []:
                if isinstance(row, dict):
                    meaning_dispositions.append(row.get("disposition"))
        return {
            "candidate": "not_a_definition_candidate",
            "source_review": owner_result.get("status"),
            "meaning_review": "unreviewed",
            "source_dispositions": source_dispositions,
            "meaning_dispositions": meaning_dispositions,
        }
    if schema == _POPULATION_SCHEMA:
        return {
            "candidate": "not_a_definition_candidate",
            "source_review": "unreviewed" if owner_result.get("review_completed") is False else owner_result.get("status"),
            "meaning_review": "unreviewed" if owner_result.get("adjudication_performed") is False else owner_result.get("status"),
            "population_counts": owner_result.get("counts"),
            "review_completed": owner_result.get("review_completed"),
            "adjudication_performed": owner_result.get("adjudication_performed"),
        }
    if schema == _BINDING_SCHEMA:
        base = owner_result.get("base_binding")
        contextual = owner_result.get("contextual_binding")
        binding = base.get("binding") if isinstance(base, dict) else None
        return {
            "candidate": binding.get("status") if isinstance(binding, dict) else None,
            "candidate_interpretation": binding.get("interpretation_status") if isinstance(binding, dict) else None,
            "source_review": contextual.get("status") if isinstance(contextual, dict) else None,
            "meaning_review": contextual.get("interpretation_status") if isinstance(contextual, dict) else None,
        }
    if schema == _REVIEW_SCHEMA:
        definition = owner_result.get("definition_correspondence")
        contextual = owner_result.get("contextual_correspondence")
        definition = definition if isinstance(definition, dict) else {}
        contextual = contextual if isinstance(contextual, dict) else {}
        return {
            "candidate": definition.get("view"),
            "candidate_status": definition.get("status"),
            "source_review": contextual.get("source_declaration_status"),
            "meaning_review": definition.get("source_declaration_status"),
            "meaning_assessment_created": definition.get("assessment_created"),
            "related_declarations_close_definition_review": contextual.get(
                "related_declarations_close_definition_review"
            ),
        }
    if schema in {_DEFINITION_EVIDENCE_SCHEMA, _SCOPE_CORRESPONDENCE_SCHEMA}:
        counts = owner_result.get("counts") if isinstance(owner_result.get("counts"), dict) else {}
        return {
            "candidate": "unsigned_nomination",
            "source_review": owner_result.get("status"),
            "meaning_review": "unreviewed",
            "governing_definition_use": owner_result.get("governing_definition_use"),
            "alternative_count": counts.get("alternatives"),
            "asserted_use_count": counts.get("distinct_typed_uses", counts.get("typed_targets")),
            "selected_interpretation": owner_result.get("selected_interpretation"),
        }
    if schema == _NORM_REVIEW_PREPARATION_SCHEMA:
        return {
            "candidate": "unsigned_interpretation_review_evidence",
            "source_review": owner_result.get("status"),
            "meaning_review": "unreviewed",
            "context_review": "unreviewed",
            "governing_definition_use": owner_result.get("governing_definition_use"),
            "context_slot_count": len(owner_result.get("context_slot_ids") or []),
        }
    if schema == _NORM_REVIEW_SUBJECT_SCHEMA:
        return {
            "candidate": "unsigned_review_subject",
            "source_review": "unreviewed",
            "meaning_review": "unreviewed",
            "context_review": "unreviewed",
            "context_slot_count": len(owner_result.get("context_slot_ids") or []),
        }
    if schema == _NORM_REVIEW_ASSESSMENT_SCHEMA:
        ready = owner_result.get("norm_interpretation_ready") is True
        return {
            "candidate": "unsigned_review_assessment",
            "source_review": owner_result.get("evidence_assessment_status"),
            "meaning_review": "owner_marked_ready" if ready else "unreviewed",
            "context_review": "unreviewed",
            "review_count": owner_result.get("review_count"),
            "norm_interpretation_ready": owner_result.get("norm_interpretation_ready"),
            "governing_definition_use": owner_result.get("governing_definition_use"),
            "context_slot_count": len(owner_result.get("original_context_slots") or []),
        }
    if schema == _BOUND_VARIABLE_SCHEMA:
        return {
            "candidate": owner_result.get("status"),
            "source_review": "unreviewed",
            "meaning_review": "unreviewed",
            "context_review": "unreviewed",
            "governing_definition_use": owner_result.get("governing_definition_use"),
            "selected_interpretation": owner_result.get("selected_interpretation"),
            "backend_executed": owner_result.get("backend_executed"),
            "lean_compilation_verified": owner_result.get("lean_compilation_verified"),
        }
    return {
        "candidate": None,
        "source_review": None,
        "meaning_review": None,
    }


def _population(owner_result: dict[str, Any], attachments: Any) -> dict[str, Any]:
    counts = owner_result.get("counts") if isinstance(owner_result.get("counts"), dict) else {}
    contextual = owner_result.get("contextual_population")
    if isinstance(contextual, dict) and isinstance(contextual.get("counts"), dict):
        counts = contextual["counts"]
    supporting = _unreviewed_supporting_subjects(owner_result, attachments)
    packet_counts = owner_result.get("context_counts")
    if not isinstance(packet_counts, dict):
        binding = owner_result.get("contextual_binding")
        if isinstance(binding, dict) and isinstance(binding.get("context_counts"), dict):
            packet_counts = binding["context_counts"]
        elif isinstance(owner_result.get("contextual_correspondence"), dict):
            packet_counts = owner_result["contextual_correspondence"].get("context_counts")
    if not isinstance(packet_counts, dict):
        packet_counts = counts if "sources" in counts else {}
    return {
        "source_count": packet_counts.get("sources", counts.get("sources")),
        "attachment_count": packet_counts.get("attachments", owner_result.get("attachment_count")),
        "subject_count": packet_counts.get("subjects", owner_result.get("subject_count")),
        "response_count": owner_result.get("response_count"),
        "population_counts": counts or None,
        "unreviewed_supporting_subjects": supporting,
        "unreviewed_supporting_subject_count": len(supporting),
    }


def _dedupe(rows: list[Any]) -> list[Any]:
    kept: list[Any] = []
    seen: set[str] = set()
    for row in rows:
        token = repr(row)
        if token in seen:
            continue
        seen.add(token)
        kept.append(row)
    return kept


def _source_identities(result: dict[str, Any]) -> dict[str, list[Any]]:
    """Copy occurrence, span, entity, and edition identities without rewriting them."""

    occurrences: list[Any] = []
    spans: list[Any] = []
    entities: list[Any] = []
    editions: list[Any] = []

    def walk(node: Any, parent_key: str | None = None) -> None:
        if isinstance(node, dict):
            path = node.get("declaration_path")
            if isinstance(path, str) and "/occurrences/" in path:
                occurrences.append(path)
            if parent_key in {"target", "typed_row", "anchor_mapping"} or "typed_path" in node:
                typed = node.get("typed_path")
                if isinstance(typed, str):
                    entities.append({
                        "typed_path": typed,
                        "kind": node.get("kind"),
                        "binder_name": node.get("binder_name"),
                        "symbol": node.get("symbol"),
                    })
            if "span_text" in node and ("start_utf8" in node or "char_start" in node or "end_utf8" in node):
                spans.append({
                    key: node.get(key)
                    for key in ("span_text", "start_utf8", "end_utf8", "char_start", "char_end", "text")
                    if key in node
                })
            if parent_key in {"applicability", "descriptor", "source_version", "source_identity"} and "edition" in node:
                editions.append(node.get("edition"))
            if "source_edition" in node:
                editions.append(node.get("source_edition"))
            for key, value in node.items():
                if key in {"producer_pins", "authority", "limitations"}:
                    continue
                walk(value, key)
        elif isinstance(node, list):
            for item in node:
                walk(item, parent_key)

    walk(result)
    return {
        "occurrences": _dedupe(occurrences),
        "spans": _dedupe(spans),
        "entities": _dedupe(entities),
        "editions": _dedupe(editions),
    }


def _definition_uses(result: dict[str, Any]) -> dict[str, Any]:
    """Keep a governing definition distinct from each asserted term use."""

    links = result.get("links") if isinstance(result.get("links"), list) else []
    uses = []
    for link in links:
        if not isinstance(link, dict):
            continue
        request = link.get("request_link") if isinstance(link.get("request_link"), dict) else {}
        target = request.get("target") if isinstance(request.get("target"), dict) else {}
        uses.append({
            "alternative_id": request.get("alternative_id"),
            "typed_path": target.get("typed_path"),
            "kind": target.get("kind"),
            "source_paths": list(request.get("source_paths") or []),
            "governing_definition_use": link.get("governing_definition_use"),
            "status": link.get("status"),
        })
    alternatives = result.get("definitions") if isinstance(result.get("definitions"), list) else []
    alternative_ids = [
        row.get("alternative_id") for row in alternatives if isinstance(row, dict)
    ]
    return {
        "governing_definition_use": result.get("governing_definition_use"),
        "selected_interpretation": result.get("selected_interpretation"),
        "alternative_ids": alternative_ids,
        "asserted_uses": uses,
        "model_filled_binding": False,
    }


def _independent_permissions(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Keep source, edition, meaning, and context grants as separate records."""

    identities = _source_identities(result) if result else {
        "occurrences": [],
        "spans": [],
        "entities": [],
        "editions": [],
    }
    correspondence = result.get("correspondence") if isinstance(result.get("correspondence"), dict) else {}
    source_bound = correspondence.get("source_bound") is True or result.get("source_bound") is True
    meaning_ready = result.get("norm_interpretation_ready") is True
    selected = result.get("selected_interpretation")
    slots = result.get("context_slot_ids")
    if not isinstance(slots, list):
        slots = result.get("original_context_slots")
    if not isinstance(slots, list):
        slots = []
    context_evidence = result.get("context_evidence")
    context_supplied = bool(slots) or context_evidence not in (None, {}, [])
    return {
        "source": {"permission": "source", "granted": False, "source_bound": source_bound},
        "edition": {
            "permission": "edition",
            "granted": False,
            "editions": list(identities["editions"]),
        },
        "meaning": {
            "permission": "meaning",
            "granted": bool(meaning_ready and selected is not None),
            "norm_interpretation_ready": meaning_ready,
            "selected_interpretation": selected,
        },
        "context": {
            "permission": "context",
            "granted": False,
            "context_supplied": context_supplied,
            "closes_meaning": False,
            "slot_count": len(slots),
        },
    }


def _binding_pins(result: dict[str, Any]) -> dict[str, Any]:
    binding = result.get("native_binding") if isinstance(result.get("native_binding"), dict) else {}
    original = result.get("original_norm") if isinstance(result.get("original_norm"), dict) else {}
    return {
        "correspondence_sha256": result.get("correspondence_sha256") or binding.get("correspondence_sha256"),
        "graph_sha256": result.get("graph_sha256") or binding.get("correspondence_sha256"),
        "preparation_sha256": binding.get("preparation_sha256"),
        "companion_sha256": result.get("companion_sha256"),
        "request_sha256": result.get("request_sha256"),
        "original_norm": original or None,
    }


def _retained_decision(result: dict[str, Any]) -> dict[str, Any]:
    """Copy alternatives, assumptions, and carrier correspondence without choosing one."""

    request = result.get("request") if isinstance(result.get("request"), dict) else {}
    correspondence = result.get("correspondence") if isinstance(result.get("correspondence"), dict) else {}
    alternatives = result.get("definition_alternatives")
    if not isinstance(alternatives, list):
        alternatives = result.get("definitions") if isinstance(result.get("definitions"), list) else None
    unresolved = result.get("original_unresolved")
    if unresolved is None:
        unresolved = correspondence.get("retained_unresolved")
    assumptions = result.get("assumptions") if isinstance(result.get("assumptions"), list) else []
    return {
        "alternatives": alternatives,
        "alternative_ids": [
            row.get("alternative_id") for row in alternatives if isinstance(row, dict)
        ] if isinstance(alternatives, list) else [],
        "assumptions": list(assumptions),
        "definition_assumption": request.get("definition_assumption"),
        "membership_assumption": request.get("membership_assumption"),
        "carrier_map": request.get("carrier_map"),
        "evaluation_context": request.get("evaluation_context"),
        "occurrence_binding": result.get("occurrence_binding"),
        "original_unresolved": unresolved,
        "governing_definition_use": result.get("governing_definition_use"),
        "source_pins": _binding_pins(result),
    }


def _matching_prover_result(declared: Any, result: dict[str, Any]) -> bool:
    if not isinstance(declared, dict):
        return False
    required = ("status", "lean_source_sha256", "companion_sha256", "request_sha256", "theorems", "kernel_checked")
    if any(key not in declared for key in required):
        return False
    if declared.get("status") not in {"verified", "proved"} or declared.get("kernel_checked") is not True:
        return False
    source = result.get("lean_source")
    if not isinstance(source, str) or not source:
        return False
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return (
        declared.get("lean_source_sha256") == digest
        and declared.get("companion_sha256") == result.get("companion_sha256")
        and declared.get("request_sha256") == result.get("request_sha256")
        and declared.get("theorems") == result.get("conditional_theorems")
    )


def _conditional_lean(result: dict[str, Any] | None, declared_prover_result: Any) -> dict[str, Any]:
    """Leave generated Lean unbuilt and unproved unless the owner and a matching declaration agree."""

    if not isinstance(result, dict) or result.get("schema") != _BOUND_VARIABLE_SCHEMA:
        return {
            "generated": False,
            "built": False,
            "proved": False,
            "kernel_checked": False,
            "declared_prover_result_matches": False,
            "reason": "no_declared_prover_result",
        }
    source = result.get("lean_source")
    generated = isinstance(source, str) and "theorem" in source
    authority = result.get("authority") if isinstance(result.get("authority"), dict) else {}
    statements = result.get("conditional_theorem_statements")
    kernel = (
        isinstance(statements, list)
        and bool(statements)
        and all(isinstance(row, dict) and row.get("kernel_checked") is True for row in statements)
    )
    built = result.get("backend_executed") is True and result.get("lean_compilation_verified") is True
    owner_checked = (
        authority.get("conditional_theorems_checked") is True
        and authority.get("lean_compilation_verified") is True
    )
    declared_matches = _matching_prover_result(declared_prover_result, result)
    proved = bool(built and kernel and owner_checked and declared_matches)
    if proved:
        reason = "declared_prover_result"
    elif declared_prover_result is None:
        reason = "no_declared_prover_result"
    elif not declared_matches:
        reason = "declared_prover_result_does_not_match_source_pins"
    else:
        reason = "owner_execution_absent"
    return {
        "generated": generated,
        "built": built,
        "proved": proved,
        "kernel_checked": kernel,
        "declared_prover_result_matches": declared_matches,
        "reason": reason,
    }


def _decision_invoke(
    module: Any,
    error: Any,
    module_name: str,
    function_name: str,
    operation: str,
    /,
    *args: Any,
    hashes: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    envelope = _invoke(
        module,
        error,
        module_name,
        function_name,
        operation,
        *args,
        hashes=hashes,
        **kwargs,
    )
    envelope["reviews_synthesized"] = False
    if "permissions" not in envelope:
        result = envelope.get("result") if isinstance(envelope.get("result"), dict) else {}
        envelope["permissions"] = _independent_permissions(result)
    if "conditional_lean" not in envelope:
        result = envelope.get("result") if isinstance(envelope.get("result"), dict) else None
        envelope["conditional_lean"] = _conditional_lean(result, None)
    return envelope


def _pin_hashes(kwargs: dict[str, Any]) -> dict[str, Any]:
    pins = {
        key: value
        for key, value in kwargs.items()
        if key.startswith("expected_") and (key.endswith("sha256") or key.endswith("_sha256s"))
    }
    return _hashes(**pins)


def _hashes(**pins: Any) -> dict[str, Any]:
    bound = {}
    for key, value in pins.items():
        if value is None:
            continue
        bound[key] = list(value) if isinstance(value, (list, tuple)) else value
    return bound


def _envelope(
    *,
    status: str,
    operation: str,
    owner: str,
    owner_function: str,
    result: dict[str, Any] | None,
    reason: str | None,
    error_type: str | None,
    hashes: dict[str, Any],
    attachments: Any,
    dependency: dict[str, str] | None = None,
) -> dict[str, Any]:
    owner_authority = None
    training_mask = 0
    evaluation_gold_mask = 0
    states = {"candidate": None, "source_review": None, "meaning_review": None}
    population = {
        "source_count": None,
        "attachment_count": None,
        "subject_count": None,
        "response_count": None,
        "population_counts": None,
        "unreviewed_supporting_subjects": [],
        "unreviewed_supporting_subject_count": 0,
    }
    if isinstance(result, dict):
        authority = result.get("authority")
        if isinstance(authority, dict):
            owner_authority = dict(authority)
        else:
            contextual = result.get("contextual_binding")
            if isinstance(contextual, dict) and isinstance(contextual.get("authority"), dict):
                owner_authority = dict(contextual["authority"])
            correspondence = result.get("contextual_correspondence")
            if isinstance(correspondence, dict) and isinstance(correspondence.get("authority"), dict):
                owner_authority = dict(correspondence["authority"])
        if isinstance(result.get("training_mask"), int):
            training_mask = result["training_mask"]
        if isinstance(result.get("evaluation_gold_mask"), int):
            evaluation_gold_mask = result["evaluation_gold_mask"]
        states = _states(result)
        population = _population(result, attachments)
        if result.get("schema") == _REVIEW_SCHEMA:
            contextual = result.get("contextual_correspondence")
            if isinstance(contextual, dict):
                if isinstance(contextual.get("training_mask"), int):
                    training_mask = contextual["training_mask"]
                if isinstance(contextual.get("evaluation_gold_mask"), int):
                    evaluation_gold_mask = contextual["evaluation_gold_mask"]
    envelope = {
        "schema": SCHEMA,
        "status": status,
        "operation": operation,
        "owner": owner,
        "owner_function": owner_function,
        "reason": reason,
        "error_type": error_type,
        "dependency": dependency,
        "result": result,
        "states": states,
        "population": population,
        "bound_hashes": hashes,
        "owner_authority": owner_authority,
        "authority_granted": dict(_DENIED_AUTHORITY),
        "applicability_granted": False,
        "truth_granted": False,
        "training_authority_granted": False,
        "graph_authority_granted": False,
        "proof_authority_granted": False,
        "training_mask": training_mask,
        "evaluation_gold_mask": evaluation_gold_mask,
        "legal_review_completed": False,
        "fabricated": False,
    }
    if isinstance(result, dict) and result.get("schema") in {
        _DEFINITION_EVIDENCE_SCHEMA,
        _SCOPE_CORRESPONDENCE_SCHEMA,
        *_DECISION_SCHEMAS,
    }:
        envelope["identities"] = _source_identities(result)
        envelope["definition_uses"] = _definition_uses(result)
    if isinstance(result, dict) and result.get("schema") in _DECISION_SCHEMAS:
        envelope["permissions"] = _independent_permissions(result)
        envelope["reviews_synthesized"] = False
        envelope["retained"] = _retained_decision(result)
        envelope["conditional_lean"] = _conditional_lean(result, None)
    return envelope


def _invoke(
    module: Any,
    error: Any,
    module_name: str,
    function_name: str,
    operation: str,
    /,
    *args: Any,
    attachments: Any = None,
    hashes: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    bound = hashes or {}
    if module is None or not callable(getattr(module, function_name, None)):
        diagnostic = _diagnostic(error)
        return _envelope(
            status="unavailable",
            operation=operation,
            owner=module_name,
            owner_function=function_name,
            result=None,
            reason="owner_unavailable" if module is None else "owner_function_unavailable",
            error_type=None if diagnostic is None else diagnostic.get("error_type"),
            hashes=bound,
            attachments=attachments,
            dependency=diagnostic,
        )
    try:
        result = getattr(module, function_name)(*args, **kwargs)
    except Exception as exc:
        return _envelope(
            status="failed",
            operation=operation,
            owner=module_name,
            owner_function=function_name,
            result=None,
            reason=str(exc) or type(exc).__name__,
            error_type=type(exc).__name__,
            hashes=bound,
            attachments=attachments,
        )
    if not isinstance(result, dict) or result.get("schema") not in _ACCEPTED_SCHEMAS:
        return _envelope(
            status="failed",
            operation=operation,
            owner=module_name,
            owner_function=function_name,
            result=result if isinstance(result, dict) else None,
            reason="unexpected_owner_schema",
            error_type="UnexpectedOwnerSchema",
            hashes=bound,
            attachments=attachments,
        )
    return _envelope(
        status="replayed",
        operation=operation,
        owner=module_name,
        owner_function=function_name,
        result=result,
        reason=None,
        error_type=None,
        hashes=bound,
        attachments=attachments,
    )


def prepare_sampling_review_context(
    sources: Any,
    attachments: Any,
    *,
    expected_attachments_sha256: str,
    limits: Any = None,
) -> dict[str, Any]:
    """Replay whole sources and the exact attachment population."""

    return _invoke(
        _context_module,
        _context_error,
        _CONTEXT_MODULE_NAME,
        "prepare",
        "prepare_sampling_review_context",
        sources,
        attachments,
        expected_attachments_sha256=expected_attachments_sha256,
        limits=limits,
        attachments=attachments,
        hashes=_hashes(expected_attachments_sha256=expected_attachments_sha256),
    )


def validate_sampling_review_context(
    packet: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_context_sha256: str,
    expected_attachments_sha256: str,
    limits: Any = None,
) -> dict[str, Any]:
    """Replay the pinned context against the whole source and attachment populations."""

    return _invoke(
        _context_module,
        _context_error,
        _CONTEXT_MODULE_NAME,
        "validate",
        "validate_sampling_review_context",
        packet,
        sources,
        attachments,
        expected_context_sha256=expected_context_sha256,
        expected_attachments_sha256=expected_attachments_sha256,
        limits=limits,
        attachments=attachments,
        hashes=_hashes(
            expected_context_sha256=expected_context_sha256,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def record_sampling_review_context_response(
    packet: Any,
    declaration: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_context_sha256: str,
    expected_declaration_sha256: str,
    expected_attachments_sha256: str,
    limits: Any = None,
) -> dict[str, Any]:
    """Record one explicit declaration hash against the whole context population."""

    return _invoke(
        _context_module,
        _context_error,
        _CONTEXT_MODULE_NAME,
        "record_response",
        "record_sampling_review_context_response",
        packet,
        declaration,
        sources,
        attachments,
        expected_context_sha256=expected_context_sha256,
        expected_declaration_sha256=expected_declaration_sha256,
        expected_attachments_sha256=expected_attachments_sha256,
        limits=limits,
        attachments=attachments,
        hashes=_hashes(
            expected_context_sha256=expected_context_sha256,
            expected_declaration_sha256=expected_declaration_sha256,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def validate_sampling_review_context_response(
    response: Any,
    packet: Any,
    declaration: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_response_sha256: str,
    expected_context_sha256: str,
    expected_declaration_sha256: str,
    expected_attachments_sha256: str,
    limits: Any = None,
) -> dict[str, Any]:
    """Replay one recorded declaration without promoting source or meaning review."""

    return _invoke(
        _context_module,
        _context_error,
        _CONTEXT_MODULE_NAME,
        "validate_response",
        "validate_sampling_review_context_response",
        response,
        packet,
        declaration,
        sources,
        attachments,
        expected_response_sha256=expected_response_sha256,
        expected_context_sha256=expected_context_sha256,
        expected_declaration_sha256=expected_declaration_sha256,
        expected_attachments_sha256=expected_attachments_sha256,
        limits=limits,
        attachments=attachments,
        hashes=_hashes(
            expected_response_sha256=expected_response_sha256,
            expected_context_sha256=expected_context_sha256,
            expected_declaration_sha256=expected_declaration_sha256,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def summarize_sampling_review_context(
    packet: Any,
    responses: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_context_sha256: str,
    expected_response_sha256s: Any,
    expected_attachments_sha256: str,
    limits: Any = None,
) -> dict[str, Any]:
    """Retain every subject, including supporting sources with no declaration."""

    return _invoke(
        _context_module,
        _context_error,
        _CONTEXT_MODULE_NAME,
        "summarize",
        "summarize_sampling_review_context",
        packet,
        responses,
        sources,
        attachments,
        expected_context_sha256=expected_context_sha256,
        expected_response_sha256s=expected_response_sha256s,
        expected_attachments_sha256=expected_attachments_sha256,
        limits=limits,
        attachments=attachments,
        hashes=_hashes(
            expected_context_sha256=expected_context_sha256,
            expected_response_sha256s=expected_response_sha256s,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def prepare_contextual_definition_binding(
    request_raw: Any,
    context: Any,
    responses: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_request_sha256: str,
    expected_definition_bundle_sha256: str,
    expected_context_sha256: str,
    expected_response_sha256s: Any,
    expected_attachments_sha256: str,
) -> dict[str, Any]:
    """Bind the explicit request hash to the whole context population."""

    return _invoke(
        _binding_module,
        _binding_error,
        _BINDING_MODULE_NAME,
        "prepare",
        "prepare_contextual_definition_binding",
        request_raw,
        context,
        responses,
        sources,
        attachments,
        expected_request_sha256=expected_request_sha256,
        expected_definition_bundle_sha256=expected_definition_bundle_sha256,
        expected_context_sha256=expected_context_sha256,
        expected_response_sha256s=expected_response_sha256s,
        expected_attachments_sha256=expected_attachments_sha256,
        attachments=attachments,
        hashes=_hashes(
            expected_request_sha256=expected_request_sha256,
            expected_definition_bundle_sha256=expected_definition_bundle_sha256,
            expected_context_sha256=expected_context_sha256,
            expected_response_sha256s=expected_response_sha256s,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def validate_contextual_definition_binding(
    result: Any,
    request_raw: Any,
    context: Any,
    responses: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_binding_sha256: str,
    expected_request_sha256: str,
    expected_definition_bundle_sha256: str,
    expected_context_sha256: str,
    expected_response_sha256s: Any,
    expected_attachments_sha256: str,
) -> dict[str, Any]:
    """Regenerate the contextual binding from the same whole populations."""

    return _invoke(
        _binding_module,
        _binding_error,
        _BINDING_MODULE_NAME,
        "validate",
        "validate_contextual_definition_binding",
        result,
        request_raw,
        context,
        responses,
        sources,
        attachments,
        expected_binding_sha256=expected_binding_sha256,
        expected_request_sha256=expected_request_sha256,
        expected_definition_bundle_sha256=expected_definition_bundle_sha256,
        expected_context_sha256=expected_context_sha256,
        expected_response_sha256s=expected_response_sha256s,
        expected_attachments_sha256=expected_attachments_sha256,
        attachments=attachments,
        hashes=_hashes(
            expected_binding_sha256=expected_binding_sha256,
            expected_request_sha256=expected_request_sha256,
            expected_definition_bundle_sha256=expected_definition_bundle_sha256,
            expected_context_sha256=expected_context_sha256,
            expected_response_sha256s=expected_response_sha256s,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def prepare_contextual_definition_review(
    binding_result: Any,
    review_subject: Any,
    *,
    expected_binding_sha256: str,
    expected_subject_sha256: str,
    contextual_replay_inputs: Any,
    candidate_inputs: Any,
    expected_candidate_pin: Any,
    context_inputs: Any,
    expected_context_population: Any,
    dependency_manifest: Any,
    expected_manifest_sha256: str,
    required_dependency_ids: Any,
) -> dict[str, Any]:
    """Replay contextual correspondence without covering the meaning subject."""

    attachments = None
    responses = None
    if isinstance(contextual_replay_inputs, dict):
        attachments = contextual_replay_inputs.get("attachments")
        responses = contextual_replay_inputs.get("responses")
    return _invoke(
        _review_module,
        _review_error,
        _REVIEW_MODULE_NAME,
        "prepare",
        "prepare_contextual_definition_review",
        binding_result,
        review_subject,
        expected_binding_sha256=expected_binding_sha256,
        expected_subject_sha256=expected_subject_sha256,
        contextual_replay_inputs=contextual_replay_inputs,
        candidate_inputs=candidate_inputs,
        expected_candidate_pin=expected_candidate_pin,
        context_inputs=context_inputs,
        expected_context_population=expected_context_population,
        dependency_manifest=dependency_manifest,
        expected_manifest_sha256=expected_manifest_sha256,
        required_dependency_ids=required_dependency_ids,
        attachments=attachments,
        hashes=_hashes(
            expected_binding_sha256=expected_binding_sha256,
            expected_subject_sha256=expected_subject_sha256,
            expected_request_sha256=(
                contextual_replay_inputs.get("expected_request_sha256")
                if isinstance(contextual_replay_inputs, dict) else None
            ),
            expected_context_sha256=(
                contextual_replay_inputs.get("expected_context_sha256")
                if isinstance(contextual_replay_inputs, dict) else None
            ),
            expected_response_sha256s=(
                contextual_replay_inputs.get("expected_response_sha256s")
                if isinstance(contextual_replay_inputs, dict) else None
            ),
            expected_attachments_sha256=(
                contextual_replay_inputs.get("expected_attachments_sha256")
                if isinstance(contextual_replay_inputs, dict) else None
            ),
            expected_manifest_sha256=expected_manifest_sha256,
        ),
    )


def validate_contextual_definition_review(
    correspondence: Any,
    binding_result: Any,
    review_subject: Any,
    *,
    expected_correspondence_sha256: str,
    expected_binding_sha256: str,
    expected_subject_sha256: str,
    contextual_replay_inputs: Any,
    candidate_inputs: Any,
    expected_candidate_pin: Any,
    context_inputs: Any,
    expected_context_population: Any,
    dependency_manifest: Any,
    expected_manifest_sha256: str,
    required_dependency_ids: Any,
) -> dict[str, Any]:
    """Regenerate the contextual review envelope under its independent pin."""

    attachments = None
    if isinstance(contextual_replay_inputs, dict):
        attachments = contextual_replay_inputs.get("attachments")
    return _invoke(
        _review_module,
        _review_error,
        _REVIEW_MODULE_NAME,
        "validate",
        "validate_contextual_definition_review",
        correspondence,
        binding_result,
        review_subject,
        expected_correspondence_sha256=expected_correspondence_sha256,
        expected_binding_sha256=expected_binding_sha256,
        expected_subject_sha256=expected_subject_sha256,
        contextual_replay_inputs=contextual_replay_inputs,
        candidate_inputs=candidate_inputs,
        expected_candidate_pin=expected_candidate_pin,
        context_inputs=context_inputs,
        expected_context_population=expected_context_population,
        dependency_manifest=dependency_manifest,
        expected_manifest_sha256=expected_manifest_sha256,
        required_dependency_ids=required_dependency_ids,
        attachments=attachments,
        hashes=_hashes(
            expected_correspondence_sha256=expected_correspondence_sha256,
            expected_binding_sha256=expected_binding_sha256,
            expected_subject_sha256=expected_subject_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
        ),
    )


def prepare_norm_definition_evidence_v1(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Replay unsigned exact-use nominations through the current definition owner."""

    return _invoke(
        _definition_module,
        _definition_error,
        _DEFINITION_MODULE_NAME,
        "prepare_norm_definition_evidence_v1",
        "prepare_norm_definition_evidence",
        *args,
        hashes=_pin_hashes(kwargs),
        **kwargs,
    )


def validate_norm_definition_evidence_v1(
    report: Any,
    *args: Any,
    expected_report_sha256: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Regenerate definition evidence under its independent report pin."""

    return _invoke(
        _definition_module,
        _definition_error,
        _DEFINITION_MODULE_NAME,
        "validate_norm_definition_evidence_v1",
        "validate_norm_definition_evidence",
        report,
        *args,
        expected_report_sha256=expected_report_sha256,
        hashes=_pin_hashes({"expected_report_sha256": expected_report_sha256, **kwargs}),
        **kwargs,
    )


def prepare_norm_scope_correspondence_v1(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Replay one declared scope correspondence without granting meaning authority."""

    return _invoke(
        _scope_module,
        _scope_error,
        _SCOPE_MODULE_NAME,
        "prepare_norm_scope_correspondence_v1",
        "prepare_norm_scope_correspondence",
        *args,
        hashes=_pin_hashes(kwargs),
        **kwargs,
    )


def validate_norm_scope_correspondence_v1(
    report: Any,
    *args: Any,
    expected_report_sha256: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Regenerate scope correspondence under its independent report pin."""

    return _invoke(
        _scope_module,
        _scope_error,
        _SCOPE_MODULE_NAME,
        "validate_norm_scope_correspondence_v1",
        "validate_norm_scope_correspondence",
        report,
        *args,
        expected_report_sha256=expected_report_sha256,
        hashes=_pin_hashes({"expected_report_sha256": expected_report_sha256, **kwargs}),
        **kwargs,
    )


def prepare_norm_review_evidence_v1(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Replay unsigned interpretation-review evidence. Reviews are not created here."""

    return _decision_invoke(
        _norm_review_module,
        _norm_review_error,
        _NORM_REVIEW_MODULE_NAME,
        "prepare_norm_review_evidence_v1",
        "prepare_norm_review_evidence",
        *args,
        hashes=_pin_hashes(kwargs),
        **kwargs,
    )


def build_norm_review_subject_v1(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Replay the review subject bound to the caller's dependency manifest."""

    return _decision_invoke(
        _norm_review_module,
        _norm_review_error,
        _NORM_REVIEW_MODULE_NAME,
        "build_norm_review_subject_v1",
        "build_norm_review_subject",
        *args,
        hashes=_pin_hashes(kwargs),
        **kwargs,
    )


def assess_norm_reviews_v1(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Authenticate only reviews the caller supplied. Unsigned reviews stay unsigned."""

    return _decision_invoke(
        _norm_review_module,
        _norm_review_error,
        _NORM_REVIEW_MODULE_NAME,
        "assess_norm_reviews_v1",
        "assess_norm_reviews",
        *args,
        hashes=_pin_hashes(kwargs),
        **kwargs,
    )


def validate_norm_review_assessment_v1(report: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Regenerate a norm-review assessment without adding a signature."""

    return _decision_invoke(
        _norm_review_module,
        _norm_review_error,
        _NORM_REVIEW_MODULE_NAME,
        "validate_norm_review_assessment_v1",
        "validate_norm_review_assessment",
        report,
        *args,
        hashes=_pin_hashes(kwargs),
        **kwargs,
    )


def prepare_bound_variable_definition_v1(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Replay a conditional bound-variable definition without executing Lean."""

    return _decision_invoke(
        _bound_variable_module,
        _bound_variable_error,
        _BOUND_VARIABLE_MODULE_NAME,
        "prepare_bound_variable_definition_v1",
        "prepare_bound_variable_definition",
        *args,
        hashes=_pin_hashes(kwargs),
        **kwargs,
    )


def validate_bound_variable_definition_v1(
    record: Any,
    *args: Any,
    expected_report_sha256: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Regenerate a bound-variable report under its independent report pin."""

    return _decision_invoke(
        _bound_variable_module,
        _bound_variable_error,
        _BOUND_VARIABLE_MODULE_NAME,
        "validate_bound_variable_definition_v1",
        "validate_bound_variable_definition",
        record,
        *args,
        expected_report_sha256=expected_report_sha256,
        hashes=_pin_hashes({"expected_report_sha256": expected_report_sha256, **kwargs}),
        **kwargs,
    )


def conditional_lean_disposition(
    envelope: dict[str, Any] | None,
    declared_prover_result: Any = None,
) -> dict[str, Any]:
    """Read Lean execution only from the owner report and a hash-matching declaration."""

    result = None
    if isinstance(envelope, dict) and isinstance(envelope.get("result"), dict):
        result = envelope["result"]
    return _conditional_lean(result, declared_prover_result)


def absent_norm_evidence(kind: str) -> dict[str, Any]:
    """Record that definition, scope, review, or bound-variable evidence was not supplied."""

    if kind == "definition":
        owner, function, operation = (
            _DEFINITION_MODULE_NAME,
            "prepare_norm_definition_evidence_v1",
            "prepare_norm_definition_evidence",
        )
    elif kind == "review":
        owner, function, operation = (
            _NORM_REVIEW_MODULE_NAME,
            "assess_norm_reviews_v1",
            "assess_norm_reviews",
        )
    elif kind == "bound_variable":
        owner, function, operation = (
            _BOUND_VARIABLE_MODULE_NAME,
            "prepare_bound_variable_definition_v1",
            "prepare_bound_variable_definition",
        )
    else:
        owner, function, operation = (
            _SCOPE_MODULE_NAME,
            "prepare_norm_scope_correspondence_v1",
            "prepare_norm_scope_correspondence",
        )
    envelope = _envelope(
        status="unavailable",
        operation=operation,
        owner=owner,
        owner_function=function,
        result=None,
        reason="evidence_not_supplied",
        error_type=None,
        hashes={},
        attachments=None,
        dependency={"error_type": "EvidenceNotSupplied", "message": kind},
    )
    if kind in {"review", "bound_variable"}:
        envelope["reviews_synthesized"] = False
        envelope["permissions"] = _independent_permissions({})
        envelope["conditional_lean"] = _conditional_lean(None, None)
        envelope["retained"] = {
            "alternatives": None,
            "alternative_ids": [],
            "assumptions": [],
            "carrier_map": None,
            "evaluation_context": None,
            "occurrence_binding": None,
            "source_pins": {},
        }
    return envelope


def _editions(envelope: dict[str, Any]) -> set[Any]:
    identities = envelope.get("identities") if isinstance(envelope.get("identities"), dict) else {}
    return {item for item in identities.get("editions") or [] if item is not None}


def _occurrence_paths(envelope: dict[str, Any]) -> set[str]:
    identities = envelope.get("identities") if isinstance(envelope.get("identities"), dict) else {}
    return {item for item in identities.get("occurrences") or [] if isinstance(item, str)}


def definition_scope_dependency(
    definition_envelope: dict[str, Any] | None,
    scope_envelope: dict[str, Any] | None,
) -> dict[str, Any]:
    """Leave conflicts and gaps unresolved instead of choosing a binding."""

    definition_envelope = definition_envelope or absent_norm_evidence("definition")
    scope_envelope = scope_envelope or absent_norm_evidence("scope")
    reasons: list[str] = []
    if definition_envelope.get("status") != "replayed":
        reasons.append("absent_or_failed_definition_evidence")
    if scope_envelope.get("status") != "replayed":
        reasons.append("absent_or_failed_scope_evidence")
    uses = {}
    if isinstance(definition_envelope.get("definition_uses"), dict):
        uses = definition_envelope["definition_uses"]
    elif isinstance(definition_envelope.get("result"), dict):
        uses = _definition_uses(definition_envelope["result"])
    governing = uses.get("governing_definition_use") if uses else None
    asserted = list(uses.get("asserted_uses") or []) if uses else []
    link_governing = [row.get("governing_definition_use") for row in asserted]
    if any(item is not None for item in link_governing):
        reasons.append("conflicting_governing_definition")
        governing = None
    alternative_ids = list(uses.get("alternative_ids") or []) if uses else []
    typed_paths = {row.get("typed_path") for row in asserted if row.get("typed_path")}
    if definition_envelope.get("status") == "replayed" and governing is None:
        if len(set(alternative_ids)) > 1 or len(typed_paths) > 1 or len(asserted) > 1:
            reasons.append("asserted_uses_without_governing_definition")
        else:
            reasons.append("governing_definition_unverified")
    scope_result = scope_envelope.get("result") if isinstance(scope_envelope.get("result"), dict) else {}
    if scope_envelope.get("status") == "replayed" and scope_result.get("governing_definition_use") is not None:
        reasons.append("conflicting_scope_governing_use")
    definition_editions = _editions(definition_envelope)
    scope_editions = _editions(scope_envelope)
    if definition_editions and scope_editions and definition_editions.isdisjoint(scope_editions):
        reasons.append("conflicting_edition_identity")
    definition_occurrences = _occurrence_paths(definition_envelope)
    scope_occurrences = _occurrence_paths(scope_envelope)
    if (
        definition_envelope.get("status") == "replayed"
        and scope_envelope.get("status") == "replayed"
        and definition_occurrences
        and scope_occurrences
        and definition_occurrences.isdisjoint(scope_occurrences)
    ):
        reasons.append("conflicting_occurrence_identity")
    return {
        "status": "unresolved_dependency" if reasons else "conditional_evidence",
        "reasons": reasons,
        "governing_definition": None,
        "selected_alternative_id": None,
        "model_filled_binding": False,
        "alternative_ids": alternative_ids,
        "asserted_uses": asserted,
        "distinct_typed_paths": sorted(path for path in typed_paths if isinstance(path, str)),
    }


def forward_conditional_norm_evidence(
    requirement: dict[str, Any],
    definition_envelope: dict[str, Any] | None,
    scope_envelope: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach conditional evidence to a requirement without editing its text or proof."""

    dependency = definition_scope_dependency(definition_envelope, scope_envelope)
    definition_envelope = definition_envelope or absent_norm_evidence("definition")
    scope_envelope = scope_envelope or absent_norm_evidence("scope")
    return {
        "schema": _HANDOFF_SCHEMA,
        "requirement_id": requirement.get("requirement_id"),
        "admitted_legal_text": requirement.get("admitted_legal_text"),
        "admitted_legal_text_changed": False,
        "proof": requirement.get("proof"),
        "proof_satisfied": False,
        "proof_changed": False,
        "conditional_evidence": {
            "definition": definition_envelope,
            "scope": scope_envelope,
        },
        "unresolved_dependency": dependency if dependency["status"] == "unresolved_dependency" else None,
        "dependency": dependency,
        "governing_definition": None,
        "asserted_uses": dependency["asserted_uses"],
        "identities": {
            "definition": definition_envelope.get("identities"),
            "scope": scope_envelope.get("identities"),
        },
    }


def _permission_record(envelope: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if isinstance(envelope, dict) and isinstance(envelope.get("permissions"), dict):
        permissions = envelope["permissions"]
        if all(isinstance(permissions.get(name), dict) for name in ("source", "edition", "meaning", "context")):
            return {
                "source": deepcopy(permissions["source"]),
                "edition": deepcopy(permissions["edition"]),
                "meaning": deepcopy(permissions["meaning"]),
                "context": deepcopy(permissions["context"]),
            }
    result = envelope.get("result") if isinstance(envelope, dict) and isinstance(envelope.get("result"), dict) else {}
    return _independent_permissions(result)


def forward_independent_norm_decisions(
    requirement: dict[str, Any],
    definition_envelope: dict[str, Any] | None = None,
    scope_envelope: dict[str, Any] | None = None,
    review_envelope: dict[str, Any] | None = None,
    bound_variable_envelope: dict[str, Any] | None = None,
    declared_prover_result: Any = None,
) -> dict[str, Any]:
    """Attach review and bound-variable decisions without merging their permissions or proofs."""

    base = forward_conditional_norm_evidence(requirement, definition_envelope, scope_envelope)
    review_envelope = review_envelope or absent_norm_evidence("review")
    bound_variable_envelope = bound_variable_envelope or absent_norm_evidence("bound_variable")
    review_permissions = _permission_record(review_envelope)
    bound_permissions = _permission_record(bound_variable_envelope)
    retained = bound_variable_envelope.get("retained") if isinstance(bound_variable_envelope.get("retained"), dict) else {}
    review_retained = review_envelope.get("retained") if isinstance(review_envelope.get("retained"), dict) else {}
    lean = conditional_lean_disposition(bound_variable_envelope, declared_prover_result)
    return {
        "schema": _DECISION_HANDOFF_SCHEMA,
        "requirement_id": requirement.get("requirement_id"),
        "admitted_legal_text": requirement.get("admitted_legal_text"),
        "admitted_legal_text_changed": False,
        "proof": requirement.get("proof"),
        "proof_satisfied": False,
        "proof_changed": False,
        "definition_scope": base,
        "review": review_envelope,
        "bound_variable": bound_variable_envelope,
        "permissions": {
            "source": review_permissions["source"],
            "edition": review_permissions["edition"],
            "meaning": review_permissions["meaning"],
            "context": review_permissions["context"],
            "bound_variable": bound_permissions,
        },
        "retained": {
            "alternatives": retained.get("alternatives", review_retained.get("alternatives")),
            "alternative_ids": list(retained.get("alternative_ids") or review_retained.get("alternative_ids") or []),
            "assumptions": list(retained.get("assumptions") or []),
            "definition_assumption": retained.get("definition_assumption"),
            "membership_assumption": retained.get("membership_assumption"),
            "carrier_map": retained.get("carrier_map"),
            "evaluation_context": retained.get("evaluation_context"),
            "occurrence_binding": retained.get("occurrence_binding"),
            "original_unresolved": review_retained.get("original_unresolved"),
            "source_pins": {
                "review": dict(review_retained.get("source_pins") or {}),
                "bound_variable": dict(retained.get("source_pins") or {}),
            },
        },
        "conditional_lean": lean,
        "reviews_synthesized": False,
        "governing_definition": None,
        "unresolved_dependency": base.get("unresolved_dependency"),
    }


def _sha256_text(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_TEXT.fullmatch(value) is not None


def _source_space_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 256
        and bool(value.strip())
        and "\x00" not in value
    )


def _runtime_available() -> bool:
    return importlib.util.find_spec("torch") is not None


def _owner_call(module: Any, name: str, *args: Any, **kwargs: Any) -> tuple[Any, str | None]:
    function = getattr(module, name, None)
    if not callable(function):
        return None, "owner_function_unavailable"
    try:
        return function(*args, **kwargs), None
    except Exception as exc:
        return None, type(exc).__name__


def _effects_not_run() -> dict[str, bool]:
    return {name: False for name in _REFUSED_MODEL_EFFECTS}


def _persistent_identity(
    module: Any,
    error: Any,
    *,
    source_space: Any,
    conditioning_mode: Any,
    expected_raw_sha256: Any,
    expected_checkpoint_sha256: Any,
    checkpoint: Any,
    checkpoint_raw: Any,
    observed_score: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Describe load/score identity. Do not train, restore, download, or fit."""

    requested = {
        "source_space": source_space,
        "conditioning_mode": conditioning_mode,
        "expected_raw_sha256": expected_raw_sha256,
        "expected_checkpoint_sha256": expected_checkpoint_sha256,
    }
    record: dict[str, Any] = {
        "owner": _PERSISTENT_OWNER,
        "load_function": "load_compact_content_persistent_v1",
        "score_function": "score_compact_content_persistent_v1",
        "qualified_name_load": _PERSISTENT_OWNER + ".load_compact_content_persistent_v1",
        "qualified_name_score": _PERSISTENT_OWNER + ".score_compact_content_persistent_v1",
        "requested": requested,
        "observed": {
            "raw_sha256": hashlib.sha256(checkpoint_raw).hexdigest() if isinstance(checkpoint_raw, bytes) else None,
            "checkpoint_sha256": None,
            "conditioning_mode": None,
            "source_space": None,
            "profile": None,
            "modes": [],
        },
        "load_called": False,
        "score_called": False,
        "restore_called": False,
        "runtime_available": _runtime_available(),
        "metadata_exact": False,
        "score_schema_exact": False,
        "engineering_evidence": False,
        "effects": _effects_not_run(),
    }
    if module is None:
        diagnostic = _diagnostic(error)
        record.update({
            "status": "unavailable",
            "eligible": False,
            "reason": "owner_unavailable",
            "error_type": None if diagnostic is None else diagnostic.get("error_type"),
        })
        return record
    modes = tuple(getattr(module, "MODES", ()) or ())
    record["observed"]["modes"] = list(modes)
    record["observed"]["profile"] = getattr(module, "PROFILE", None)
    checkpoint_sha, hash_error = (None, None)
    if isinstance(checkpoint, dict):
        checkpoint_sha, hash_error = _owner_call(module, "compact_content_persistent_sha256", checkpoint)
    record["observed"]["checkpoint_sha256"] = checkpoint_sha if isinstance(checkpoint_sha, str) else None
    mode_exact = isinstance(conditioning_mode, str) and conditioning_mode in modes
    space_exact = _source_space_text(source_space)
    raw_exact = (
        isinstance(record["observed"]["raw_sha256"], str)
        and record["observed"]["raw_sha256"] == expected_raw_sha256
        and _sha256_text(expected_raw_sha256)
    )
    checkpoint_exact = (
        isinstance(checkpoint_sha, str)
        and checkpoint_sha == expected_checkpoint_sha256
        and _sha256_text(expected_checkpoint_sha256)
    )
    record["metadata_exact"] = bool(mode_exact and space_exact and raw_exact and checkpoint_exact)
    record["observed"]["conditioning_mode"] = conditioning_mode if mode_exact else None
    record["observed"]["source_space"] = source_space if space_exact else None
    score_exact = False
    if isinstance(observed_score, Mapping):
        score_exact = (
            observed_score.get("schema") == _PERSISTENT_SCORE_SCHEMA
            and observed_score.get("conditioning_mode") == conditioning_mode
            and observed_score.get("source_space") == source_space
            and observed_score.get("checkpoint_sha256") == expected_checkpoint_sha256
            and record["metadata_exact"]
        )
    record["score_schema_exact"] = score_exact
    if not record["runtime_available"]:
        status, reason = "unavailable", "runtime_unavailable"
    elif hash_error == "owner_function_unavailable":
        status, reason = "unavailable", "owner_function_unavailable"
    elif hash_error is not None:
        status, reason = "ineligible", "incompatible_checkpoint"
    elif not record["metadata_exact"]:
        status, reason = "ineligible", "incompatible_metadata"
    elif not score_exact:
        status, reason = "ineligible", "model_output_absent"
    else:
        status, reason = "candidate", "metadata_and_score_identity"
    record.update({
        "status": status,
        "eligible": status == "candidate",
        "reason": reason,
        "error_type": hash_error if hash_error not in {None, "owner_function_unavailable"} else record.get("error_type"),
        "engineering_evidence": bool(record["metadata_exact"] and status != "unavailable"),
        "claimed_authority_ignored": True,
    })
    return record


def _predicate_identity(
    module: Any,
    error: Any,
    *,
    objective_kind: Any,
    expected_policy_sha256: Any,
    expected_checkpoint_sha256: Any,
    checkpoint: Any,
    observed_inspect: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Describe inspect/checkpoint identity and objective preparation. Do not train."""

    requested = {
        "objective_kind": objective_kind,
        "expected_policy_sha256": expected_policy_sha256,
        "expected_checkpoint_sha256": expected_checkpoint_sha256,
    }
    record: dict[str, Any] = {
        "owner": _PREDICATE_OWNER,
        "inspect_function": "inspect",
        "checkpoint_function": "checkpoint_sha256",
        "policy_function": "policy",
        "qualified_name_inspect": _PREDICATE_OWNER + ".inspect",
        "qualified_name_checkpoint": _PREDICATE_OWNER + ".checkpoint_sha256",
        "qualified_name_policy": _PREDICATE_OWNER + ".policy",
        "requested": requested,
        "observed": {
            "policy_sha256": None,
            "checkpoint_sha256": None,
            "objective_kind": None,
            "policy_schema": None,
            "profile": None,
            "authority_all_false": None,
        },
        "inspect_called": False,
        "checkpoint_called": False,
        "policy_called": False,
        "training_executed": False,
        "optimizer_constructed": False,
        "metadata_exact": False,
        "inspect_schema_exact": False,
        "engineering_evidence": False,
        "effects": _effects_not_run(),
    }
    if module is None:
        diagnostic = _diagnostic(error)
        record.update({
            "status": "unavailable",
            "eligible": False,
            "reason": "owner_unavailable",
            "error_type": None if diagnostic is None else diagnostic.get("error_type"),
        })
        return record
    policy, policy_error = _owner_call(module, "policy", objective_kind)
    policy_sha = None
    policy_sha_error = None
    if isinstance(policy, dict):
        policy_sha, policy_sha_error = _owner_call(module, "policy_sha256", policy)
        record["policy_called"] = policy_sha_error is None
    checkpoint_sha, checkpoint_error = (None, None)
    if isinstance(checkpoint, dict):
        checkpoint_sha, checkpoint_error = _owner_call(module, "checkpoint_sha256", checkpoint)
        record["checkpoint_called"] = checkpoint_error is None
    authority = getattr(module, "AUTHORITY", None)
    authority_all_false = (
        isinstance(authority, dict)
        and bool(authority)
        and all(value is False for value in authority.values())
    )
    record["observed"].update({
        "policy_sha256": policy_sha if isinstance(policy_sha, str) else None,
        "checkpoint_sha256": checkpoint_sha if isinstance(checkpoint_sha, str) else None,
        "objective_kind": policy.get("objective_kind") if isinstance(policy, dict) else None,
        "policy_schema": policy.get("schema") if isinstance(policy, dict) else None,
        "profile": getattr(module, "PROFILE", None),
        "authority_all_false": authority_all_false,
    })
    policy_exact = (
        isinstance(policy_sha, str)
        and policy_sha == expected_policy_sha256
        and _sha256_text(expected_policy_sha256)
        and isinstance(policy, dict)
        and policy.get("objective_kind") == objective_kind
    )
    checkpoint_exact = (
        isinstance(checkpoint_sha, str)
        and checkpoint_sha == expected_checkpoint_sha256
        and _sha256_text(expected_checkpoint_sha256)
    )
    record["metadata_exact"] = bool(policy_exact and checkpoint_exact and authority_all_false)
    inspect_exact = False
    if isinstance(observed_inspect, Mapping):
        inspect_exact = (
            observed_inspect.get("schema") == _PREDICATE_CHECKPOINT_SCHEMA
            and observed_inspect.get("checkpoint_sha256") == expected_checkpoint_sha256
            and observed_inspect.get("objective_policy_sha256") == expected_policy_sha256
            and record["metadata_exact"]
        )
    record["inspect_schema_exact"] = inspect_exact
    owner_error = policy_error or policy_sha_error or checkpoint_error
    if owner_error == "owner_function_unavailable":
        status, reason = "unavailable", "owner_function_unavailable"
    elif owner_error is not None and not isinstance(checkpoint, dict):
        status, reason = "unavailable", "owner_call_failed"
    elif not record["metadata_exact"]:
        status, reason = "ineligible", "incompatible_checkpoint"
    elif isinstance(observed_inspect, Mapping) and not inspect_exact:
        status, reason = "ineligible", "incompatible_inspect_identity"
    elif not inspect_exact:
        status, reason = "ineligible", "inspect_not_executed"
    else:
        status, reason = "candidate", "policy_checkpoint_and_inspect_identity"
    record.update({
        "status": status,
        "eligible": status == "candidate",
        "reason": reason,
        "error_type": owner_error if status == "unavailable" else None,
        "engineering_evidence": bool(record["metadata_exact"] and authority_all_false),
        "numerical_qualification_is_engineering_evidence": True,
        "training_preparation_is_engineering_evidence": bool(record["policy_called"]),
    })
    return record


def describe_qualified_model_candidate(
    *,
    source_space: Any = None,
    conditioning_mode: Any = None,
    objective_kind: Any = None,
    expected_policy_sha256: Any = None,
    expected_checkpoint_sha256: Any = None,
    expected_persistent_checkpoint_sha256: Any = None,
    expected_raw_sha256: Any = None,
    checkpoint: Any = None,
    persistent_checkpoint: Any = None,
    checkpoint_raw: Any = None,
    observed_score: Mapping[str, Any] | None = None,
    observed_inspect: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record qualified model identity as engineering evidence, never as authority.

    Persistent load/score and predicate inspect are named and pin-checked.
    This function does not call training, optimizer, download, restore, numerical
    fit, load, score, or inspect. A schema-matching supplied output can be a
    candidate only when its source-space, conditioning, policy, and checkpoint
    pins match the owner hashes. Candidate status still grants no legal effect.
    """

    persistent_module, persistent_error = import_module_optional(_PERSISTENT_OWNER)
    predicate_module, predicate_error = import_module_optional(_PREDICATE_OWNER)
    persistent_sha = expected_persistent_checkpoint_sha256
    if persistent_sha is None:
        persistent_sha = expected_checkpoint_sha256
    persistent = _persistent_identity(
        persistent_module,
        persistent_error,
        source_space=source_space,
        conditioning_mode=conditioning_mode,
        expected_raw_sha256=expected_raw_sha256,
        expected_checkpoint_sha256=persistent_sha,
        checkpoint=persistent_checkpoint if persistent_checkpoint is not None else checkpoint,
        checkpoint_raw=checkpoint_raw,
        observed_score=observed_score,
    )
    predicate = _predicate_identity(
        predicate_module,
        predicate_error,
        objective_kind=objective_kind,
        expected_policy_sha256=expected_policy_sha256,
        expected_checkpoint_sha256=expected_checkpoint_sha256,
        checkpoint=checkpoint,
        observed_inspect=observed_inspect,
    )
    if persistent["status"] == "unavailable" or predicate["status"] == "unavailable":
        status = "unavailable"
        reason = persistent["reason"] if persistent["status"] == "unavailable" else predicate["reason"]
    elif persistent["status"] == "candidate" and predicate["status"] == "candidate":
        status = "candidate"
        reason = "qualified_engineering_candidate"
    else:
        status = "ineligible"
        reason = persistent["reason"] if persistent["status"] != "candidate" else predicate["reason"]
    return {
        "schema": QUALIFIED_MODEL_CANDIDATE_SCHEMA,
        "status": status,
        "reason": reason,
        "eligible": status == "candidate",
        "eligible_as_authority": False,
        "legally_eligible": False,
        "role": "candidate" if status == "candidate" else "not_admitted",
        "engineering_evidence": bool(persistent.get("engineering_evidence") or predicate.get("engineering_evidence")),
        "live_owner_verified": False,
        "model_executed": False,
        "skipped": False,
        "authority": dict(_CANDIDATE_AUTHORITY),
        "selects_governing_law": False,
        "satisfies_definition_review": False,
        "proves_element": False,
        "effects": _effects_not_run(),
        "requested": {
            "source_space": source_space,
            "conditioning_mode": conditioning_mode,
            "objective_kind": objective_kind,
            "expected_policy_sha256": expected_policy_sha256,
            "expected_checkpoint_sha256": expected_checkpoint_sha256,
            "expected_persistent_checkpoint_sha256": persistent_sha,
            "expected_raw_sha256": expected_raw_sha256,
        },
        "persistent": persistent,
        "predicate": predicate,
    }
