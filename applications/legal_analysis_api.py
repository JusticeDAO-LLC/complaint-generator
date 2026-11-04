"""Attach canonical legal IR and source obligations for one authorized case.

The route is mounted by ``compose_case_routes``. Session and case-action checks
run before these handlers. Formalization goes through
``attach_canonical_legal_ir_source_obligations``, which reuses
``compile_canonical_legal_ir`` and current-source receipt verification.
Parsed IR, consistency, and emitted Lean text stay non-authority. This module
does not claim WebSocket or SSE support.
"""
from __future__ import annotations

import json
import base64
import lzma
import binascii
import hashlib
from copy import deepcopy
from typing import Any, Dict, Mapping, MutableMapping

from starlette.requests import Request

TASK_ID = "CIMP-GUI-29"
DEFINITION_CORRESPONDENCE_TASK_ID = "CIMP-GUI-30"
LEGAL_ANALYSIS_PREFIX = "/api/legal-analysis"
DEFINITION_CORRESPONDENCE_ROUTE = LEGAL_ANALYSIS_PREFIX + "/{case_id}/definition-correspondence"
PROOF_TRACE_TASK_ID = "CIMP-GUI-31"
PROOF_TRACE_ROUTE = LEGAL_ANALYSIS_PREFIX + "/{case_id}/proof-traces"
DEPENDENCY_REQUIREMENT_TASK_ID = "CIMP-UX-26"
DEPENDENCY_REQUIREMENT_ROUTE = LEGAL_ANALYSIS_PREFIX + "/{case_id}/dependency-requirements"
_TRACE_STATUSES = ("executed", "degraded", "not_executed", "missing_prover", "timeout", "source_drift")
_UNAVAILABLE_TRACE_STATUSES = ("missing_prover", "timeout", "source_drift")

_BODY_CAP = 65536
_VOCABULARY_KEYS = ("actors", "actions", "objects", "qualifiers")


class LegalAnalysisError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def legal_analysis_http_status(code: str) -> int:
    if code == "unauthenticated":
        return 401
    if code in {"legal_analysis_field", "legal_analysis_bounds", "client_case_authority"}:
        return 422
    if code in {"canonical_compiler_unavailable", "definition_owner_unavailable", "legal_analysis_unavailable", "unlock_needed", "proof_producer_unavailable"}:
        return 503
    if code in {"revision_conflict", "legal_source_changed", "legal_source_unavailable"}:
        return 409
    return 403


def _case_file_from_mediator(mediator: Any) -> MutableMapping[str, Any]:
    phase_manager = getattr(mediator, "phase_manager", None)
    if phase_manager is not None and hasattr(phase_manager, "get_phase_data"):
        from complaint_phases.phase_manager import ComplaintPhase

        stored = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
        if isinstance(stored, dict):
            return stored
    stored = getattr(mediator, "intake_case_file", None)
    if isinstance(stored, dict):
        return stored
    raise LegalAnalysisError("legal_analysis_unavailable")


def _string_list(value: Any, *, label: str, limit: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        raise LegalAnalysisError("legal_analysis_bounds")
    rows: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 512:
            raise LegalAnalysisError("legal_analysis_field")
        rows.append(item)
    if label == "user_facts" and any(len(item) > 512 for item in rows):
        raise LegalAnalysisError("legal_analysis_bounds")
    return rows


def _request_body(body: Mapping[str, Any]) -> Dict[str, Any]:
    if len(json.dumps(body, default=str)) > _BODY_CAP:
        raise LegalAnalysisError("legal_analysis_bounds")
    source_text = body.get("source_text")
    if not isinstance(source_text, str) or not source_text.strip() or len(source_text) > 8192:
        raise LegalAnalysisError("legal_analysis_field")
    request_id = body.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 80:
        raise LegalAnalysisError("legal_analysis_field")
    vocabulary = body.get("vocabulary")
    if not isinstance(vocabulary, dict):
        raise LegalAnalysisError("legal_analysis_field")
    cleaned_vocabulary: Dict[str, list[str]] = {}
    for key in _VOCABULARY_KEYS:
        cleaned_vocabulary[key] = _string_list(vocabulary.get(key), label=key, limit=32)
    applicability = body.get("applicability_context", {})
    if not isinstance(applicability, dict):
        raise LegalAnalysisError("legal_analysis_field")
    legal_context = body.get("legal_context")
    if legal_context is not None and not isinstance(legal_context, dict):
        raise LegalAnalysisError("legal_analysis_field")
    typed = body.get("typed_obligations")
    if typed is not None and (not isinstance(typed, list) or len(typed) > 32):
        raise LegalAnalysisError("legal_analysis_bounds")
    current_source = body.get("current_source", source_text)
    if not isinstance(current_source, str):
        raise LegalAnalysisError("legal_analysis_field")
    emitted_lean = body.get("emitted_lean")
    if emitted_lean is not None and (not isinstance(emitted_lean, str) or len(emitted_lean) > 4096):
        raise LegalAnalysisError("legal_analysis_field")
    return {
        "source_text": source_text,
        "request_id": request_id,
        "vocabulary": cleaned_vocabulary,
        "applicability_context": applicability,
        "legal_context": legal_context,
        "user_facts": _string_list(body.get("user_facts"), label="user_facts", limit=16),
        "typed_obligations": typed,
        "current_source": current_source,
        "emitted_lean": emitted_lean,
        "supplied_receipt": body.get("receipt") if isinstance(body.get("receipt"), dict) else body.get("canonical_receipt"),
    }


def attach_case_canonical_legal_ir(mediator: Any, body: Mapping[str, Any]) -> Dict[str, Any]:
    """Legacy in-process utility; not the authenticated GUI publication owner."""

    from integrations.ipfs_datasets.logic import attach_canonical_legal_ir_source_obligations

    case_file = _case_file_from_mediator(mediator)
    fields = _request_body(body)
    supplied = fields.pop("supplied_receipt")
    payload = attach_canonical_legal_ir_source_obligations(supplied_receipt=supplied if isinstance(supplied, dict) else None, **fields)
    payload["task_id"] = TASK_ID
    payload["admitted_law"] = False
    payload["proof"] = False
    payload["legal_sufficiency"] = False
    if payload.get("status") == "unavailable":
        raise LegalAnalysisError("canonical_compiler_unavailable")
    case_file["canonical_legal_ir_attachment"] = payload
    return payload


def project_canonical_legal_ir(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    stored = case_file.get("canonical_legal_ir_attachment") if isinstance(case_file, Mapping) else None
    if not isinstance(stored, dict):
        return {
            "task_id": TASK_ID,
            "operation": "attach_canonical_legal_ir_source_obligations",
            "status": "empty",
            "typed_obligations": [],
            "source_spans": [],
            "executed_proof": False,
            "governing_legal_authority": False,
            "ir_parse_is_proof": False,
            "consistency_is_proof": False,
            "lean_text_is_proof": False,
            "proof": False,
            "admitted_law": False,
            "limitations": ["No canonical legal IR attachment has been recorded."],
        }
    projected = deepcopy(stored)
    projected["task_id"] = TASK_ID
    projected["executed_proof"] = False
    projected["governing_legal_authority"] = False
    projected["ir_parse_is_proof"] = False
    projected["consistency_is_proof"] = False
    projected["lean_text_is_proof"] = False
    projected["proof"] = False
    projected["admitted_law"] = False
    obligations = projected.get("typed_obligations")
    if isinstance(obligations, list):
        for item in obligations:
            if isinstance(item, dict):
                item["executed_proof"] = False
                item["governing_legal_authority"] = False
                item["discharged"] = False
    return projected


def _population_ids(value: Any) -> Dict[str, list[str]]:
    if not isinstance(value, dict):
        raise LegalAnalysisError("legal_analysis_field")
    cleaned: Dict[str, list[str]] = {}
    for key, items in value.items():
        if not isinstance(key, str) or not isinstance(items, list) or len(items) > 32:
            raise LegalAnalysisError("legal_analysis_bounds")
        rows = []
        for item in items:
            if not isinstance(item, str) or not item.strip() or len(item) > 256:
                raise LegalAnalysisError("legal_analysis_field")
            rows.append(item)
        cleaned[key] = rows
    return cleaned


def _owner_bundle(value: Any) -> Dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise LegalAnalysisError("legal_analysis_field")
    return value


def bind_case_definition_correspondence(mediator: Any, body: Mapping[str, Any]) -> Dict[str, Any]:
    """Public case entry for current definition and correspondence owners."""

    from integrations.ipfs_datasets.logic import bind_current_definition_correspondence_owners

    source_text = body.get("source_text")
    request_id = body.get("request_id")
    if not isinstance(source_text, str) or not isinstance(request_id, str):
        raise LegalAnalysisError("legal_analysis_field")
    case_file = _case_file_from_mediator(mediator)
    payload = bind_current_definition_correspondence_owners(
        source_text,
        request_id=request_id,
        declared_populations=_population_ids(body.get("declared_populations") or {}),
        scope_correspondence=_owner_bundle(body.get("scope_correspondence")),
        correspondence_requests=_owner_bundle(body.get("correspondence_requests")),
        applicability=_owner_bundle(body.get("applicability")),
        contextual_review=_owner_bundle(body.get("contextual_review")),
        supplied_receipt=body.get("receipt") if isinstance(body.get("receipt"), dict) else None,
        training_metrics=body.get("training_metrics"),
        graph_join=body.get("graph_join"),
    )
    payload["task_id"] = DEFINITION_CORRESPONDENCE_TASK_ID
    payload["authorizes_law"] = False
    payload["authorizes_proof"] = False
    payload["executed_proof"] = False
    payload["governing_legal_authority"] = False
    payload["proof"] = False
    if payload.get("status") == "unavailable":
        raise LegalAnalysisError("definition_owner_unavailable")
    case_file["definition_correspondence_binding"] = payload
    return payload


def project_definition_correspondence(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    stored = case_file.get("definition_correspondence_binding") if isinstance(case_file, Mapping) else None
    if not isinstance(stored, dict):
        return {
            "task_id": DEFINITION_CORRESPONDENCE_TASK_ID,
            "operation": "bind_current_definition_correspondence_owners",
            "status": "empty",
            "owners": {},
            "authorizes_law": False,
            "authorizes_proof": False,
            "executed_proof": False,
            "governing_legal_authority": False,
            "proof": False,
            "limitations": ["No definition correspondence binding has been recorded."],
        }
    projected = dict(stored)
    projected["task_id"] = DEFINITION_CORRESPONDENCE_TASK_ID
    projected["authorizes_law"] = False
    projected["authorizes_proof"] = False
    projected["executed_proof"] = False
    projected["governing_legal_authority"] = False
    projected["proof"] = False
    return projected


_DEFINITION_BODY_CAP = 256 * 1024
_DEFINITION_BYTES_CAP = 2 * 1024 * 1024
_DEFINITION_EXPANDED_CAP = 8 * 1024 * 1024
_DEFINITION_INPUT_TAG = "$complaint_definition_inputs"
_DEFINITION_WIRE_TAG = "$complaint_definition_bytes"


def definition_wire(value, *, decode=False):
    """Bounded versioned JSON byte transport; never file/object authority."""
    count, byte_count = 0, 0
    def walk(item, depth):
        nonlocal count, byte_count
        count += 1
        if depth > 32 or count > 100000:
            raise LegalAnalysisError("legal_analysis_bounds")
        if isinstance(item, dict):
            if _DEFINITION_WIRE_TAG in item:
                if not decode or set(item) != {_DEFINITION_WIRE_TAG}:
                    raise LegalAnalysisError("legal_analysis_field")
                inner = item[_DEFINITION_WIRE_TAG]
                if (not isinstance(inner, dict) or set(inner) != {"version", "base64"}
                        or type(inner["version"]) is not int or inner["version"] != 1
                        or not isinstance(inner["base64"], str) or len(inner["base64"]) > 4 * ((_DEFINITION_BYTES_CAP + 2) // 3)):
                    raise LegalAnalysisError("legal_analysis_field")
                padding = len(inner["base64"]) - len(inner["base64"].rstrip("="))
                estimated = len(inner["base64"]) // 4 * 3 - padding
                if padding > 2 or len(inner["base64"]) % 4:
                    raise LegalAnalysisError("legal_analysis_field")
                if estimated < 0 or byte_count + estimated > _DEFINITION_BYTES_CAP:
                    raise LegalAnalysisError("legal_analysis_bounds")
                try:
                    raw = base64.b64decode(inner["base64"], validate=True)
                except (ValueError, binascii.Error):
                    raise LegalAnalysisError("legal_analysis_field") from None
                if base64.b64encode(raw).decode("ascii") != inner["base64"]:
                    raise LegalAnalysisError("legal_analysis_field")
                byte_count += len(raw)
                if byte_count > _DEFINITION_BYTES_CAP:
                    raise LegalAnalysisError("legal_analysis_bounds")
                return raw
            if any(not isinstance(key, str) for key in item):
                raise LegalAnalysisError("legal_analysis_field")
            return {key: walk(child, depth + 1) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [walk(child, depth + 1) for child in item]
        if isinstance(item, bytes) and not decode:
            byte_count += len(item)
            if byte_count > _DEFINITION_BYTES_CAP:
                raise LegalAnalysisError("legal_analysis_bounds")
            return {_DEFINITION_WIRE_TAG: {"version": 1, "base64": base64.b64encode(item).decode("ascii")}}
        if item is None or type(item) in {str, bool, int, float}:
            return item
        raise LegalAnalysisError("legal_analysis_field")
    result = walk(value, 0)
    if not decode:
        try:
            if len(json.dumps(result, allow_nan=False).encode()) > _DEFINITION_EXPANDED_CAP:
                raise LegalAnalysisError("legal_analysis_bounds")
        except (ValueError, TypeError):
            raise LegalAnalysisError("legal_analysis_field") from None
    return result


def definition_inputs_wire(bundle):
    """Lossless v1 data transport for the unchanged current Data owners.

    Wire JSON stays below256KiB and ordinary case middleware remains1MiB.
    Expanded canonical JSON is at most8MiB,100000nodes,depth32; decoded
    byte leaves total at most2MiB. XZ decoder memory is capped at32MiB.
    No file/env/object references, custom constructors or verdicts are loaded.
    """
    raw = json.dumps(definition_wire(bundle), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > _DEFINITION_EXPANDED_CAP:
        raise LegalAnalysisError("legal_analysis_bounds")
    packed = {_DEFINITION_INPUT_TAG: {"version": 1, "encoding": "xz-json-base64",
        "byte_length": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "base64": base64.b64encode(lzma.compress(raw, format=lzma.FORMAT_XZ, preset=6)).decode("ascii")}}
    if len(json.dumps(packed).encode()) > _DEFINITION_BODY_CAP:
        raise LegalAnalysisError("legal_analysis_bounds")
    return packed


def _definition_inputs(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {_DEFINITION_INPUT_TAG}:
        raise LegalAnalysisError("legal_analysis_field")
    fields = bundle[_DEFINITION_INPUT_TAG]
    if (not isinstance(fields, dict) or set(fields) != {"version", "encoding", "byte_length", "sha256", "base64"}
            or type(fields["version"]) is not int or fields["version"] != 1
            or fields["encoding"] != "xz-json-base64"
            or type(fields["byte_length"]) is not int or not 0 < fields["byte_length"] <= _DEFINITION_EXPANDED_CAP
            or not isinstance(fields["sha256"], str) or len(fields["sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in fields["sha256"])
            or not isinstance(fields["base64"], str) or len(fields["base64"]) > _DEFINITION_BODY_CAP):
        raise LegalAnalysisError("legal_analysis_field")
    try:
        compressed = base64.b64decode(fields["base64"], validate=True)
        if base64.b64encode(compressed).decode("ascii") != fields["base64"]:
            raise ValueError("noncanonical_base64")
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=32 * 1024 * 1024)
        raw = decoder.decompress(compressed, max_length=fields["byte_length"] + 1)
        # Before EOF, needs_input distinguishes truncation from buffered output
        # past the declared budget. Both are refused; no draining/flush occurs.
        if (not decoder.eof or decoder.unused_data
                or len(raw) != fields["byte_length"]
                or hashlib.sha256(raw).hexdigest() != fields["sha256"]):
            raise ValueError("invalid_expansion")
        def pairs(rows):
            result = {}
            for key, value in rows:
                if key in result:
                    raise ValueError("duplicate_json_key")
                result[key] = value
            return result
        def constant(_value):
            raise ValueError("nonfinite_json")
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        if json.dumps(decoded, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() != raw:
            raise ValueError("noncanonical_json")
    except (ValueError, TypeError, UnicodeDecodeError, RecursionError, lzma.LZMAError, binascii.Error):
        raise LegalAnalysisError("legal_analysis_field") from None
    return definition_wire(decoded, decode=True)


def bind_current_case_definition_correspondence(case_file, body, *, case_id, source_scope_sha256):
    """Replay unchanged Data owners using one current server-owned source."""
    from integrations.ipfs_datasets.logic import bind_current_definition_correspondence_owners
    if not isinstance(body, Mapping):
        raise LegalAnalysisError("legal_analysis_field")
    forbidden = {"source_text", "current_source", "source_record", "canonical_source", "case_file",
        "legal_context", "applicability_context", "user_facts", "factual_premises", "receipt", "canonical_receipt"}
    if forbidden.intersection(body):
        raise LegalAnalysisError("client_case_authority")
    allowed = {"request_id", "source_content_hash", "declared_populations", "scope_correspondence",
        "correspondence_requests", "applicability", "contextual_review", "training_metrics", "graph_join",
        "expected_private_revision", "expected_session_revision", "owner_inputs"}
    if set(body) - allowed or len(json.dumps(body, allow_nan=False).encode()) > _DEFINITION_BODY_CAP:
        raise LegalAnalysisError("legal_analysis_bounds")
    selected = current_case_legal_ir_source(case_file, body.get("source_content_hash"), case_id=case_id)
    admission, record = selected["admission"], selected["record"]
    if admission.get("source_scope_sha256") != source_scope_sha256:
        raise LegalAnalysisError("legal_source_changed")
    request_id = body.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 80:
        raise LegalAnalysisError("legal_analysis_field")
    if "owner_inputs" in body:
        if any(name in body for name in ("scope_correspondence", "correspondence_requests", "applicability", "contextual_review")):
            raise LegalAnalysisError("legal_analysis_field")
        inputs = _definition_inputs(body["owner_inputs"])
        if not isinstance(inputs, dict) or set(inputs) - {"scope_correspondence", "correspondence_requests", "applicability", "contextual_review"}:
            raise LegalAnalysisError("legal_analysis_field")
        decoded = {**dict(body), **inputs}
    else:
        decoded = definition_wire(dict(body), decode=True)
    payload = bind_current_definition_correspondence_owners(selected["text"], request_id=request_id,
        declared_populations=_population_ids(decoded.get("declared_populations") or {}),
        scope_correspondence=_owner_bundle(decoded.get("scope_correspondence")),
        correspondence_requests=_owner_bundle(decoded.get("correspondence_requests")),
        applicability=_owner_bundle(decoded.get("applicability")),
        contextual_review=_owner_bundle(decoded.get("contextual_review")),
        training_metrics=decoded.get("training_metrics"), graph_join=decoded.get("graph_join"))
    if payload.get("status") == "unavailable":
        raise LegalAnalysisError("definition_owner_unavailable")
    payload.update(task_id=DEFINITION_CORRESPONDENCE_TASK_ID, case_id=case_id,
        authorizes_law=False, authorizes_proof=False, executed_proof=False, governing_legal_authority=False, proof=False,
        source_binding={"content_hash":body["source_content_hash"], "source_record_sha256":_document_sha256(record),
            "source_scope_sha256":source_scope_sha256, "source_storage_admitted":True,
            "governing_applicability":selected["review"].get("governing_applicability", "unknown")},
        case_applicability_unchanged=True, current_owner_replayed=True)
    return definition_wire(payload)


def _document_sha256(value: Mapping[str, Any]) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError):
        raise LegalAnalysisError("legal_analysis_field") from None
    return hashlib.sha256(raw).hexdigest()


def current_case_legal_ir_source(case_file: Mapping[str, Any], source_hash: str, *, case_id: str) -> Dict[str, Any]:
    """Revalidate the saved current SourceRecord without compilation or mutation."""
    from integrations.ipfs_datasets.logic import prepare_acquired_authority_record
    digest = source_hash[7:] if isinstance(source_hash, str) and source_hash.startswith("sha256:") else source_hash
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)):
        raise LegalAnalysisError("legal_analysis_field")
    index = case_file.get("legal_source_passage_index")
    stored = index.get(source_hash) if isinstance(index, Mapping) else None
    if not isinstance(stored, Mapping):
        raise LegalAnalysisError("legal_source_unavailable")
    if (stored.get("version_state") == "stale"
            or (stored.get("current_version") and stored.get("current_version") != stored.get("version"))):
        raise LegalAnalysisError("legal_source_changed")
    admission = stored.get("source_admission")
    source = stored.get("canonical_source")
    record = stored.get("reviewed_source_record")
    if not all(isinstance(item, Mapping) for item in (admission, source, record)):
        raise LegalAnalysisError("legal_source_unavailable")
    metadata = record.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    prepared = prepare_acquired_authority_record(source,
        jurisdiction=str(record.get("jurisdiction") or ""), as_of_date=str(metadata.get("as_of_date") or ""))
    record_ids = admission.get("stored_record_ids")
    if (prepared.get("status") != "admitted" or prepared.get("record") != record
            or admission.get("record") != record or admission.get("status") != "admitted"
            or admission.get("proof") is not False or admission.get("hashes") != prepared.get("hashes")
            or admission.get("source_record_sha256") != _document_sha256(record)
            or not isinstance(record_ids, list) or not record_ids
            or any(type(item) is not int or item < 0 for item in record_ids)):
        raise LegalAnalysisError("legal_source_changed")
    text = record.get("content")
    if (not isinstance(text, str) or not text or len(text) > 8192
            or hashlib.sha256(text.encode()).hexdigest() != digest
            or stored.get("content_hash") != source_hash or stored.get("source_passage") != text):
        raise LegalAnalysisError("legal_source_changed")
    reviews = case_file.get("legal_authority_admissions")
    current_review = next((row for row in reversed(reviews) if isinstance(row, Mapping)
        and row.get("content_hash") == source_hash), None) if isinstance(reviews, list) else None
    if (not current_review or current_review.get("case_id") != case_id
            or current_review.get("source_status") != "source_admitted"
            or current_review.get("source_admission") != admission
            or current_review.get("proof") is not False):
        raise LegalAnalysisError("legal_source_unavailable")
    return {"stored": stored, "record": record, "admission": admission,
        "review": current_review, "text": text, "metadata": metadata}


def compile_current_case_legal_ir(case_file: Mapping[str, Any], knowledge_graph: Mapping[str, Any],
                                  body: Mapping[str, Any], *, case_id: str,
                                  source_scope_sha256: str) -> Dict[str, Any]:
    """Compile one freshly read, reviewed SourceRecord; grant no access here.

    The authenticated Workspace owner supplies the copied current case and KG.
    Client fields select a stored source and annotate exact spans only. Neither
    source admission nor compiler execution appoints governing law or a proof.
    """
    from complaint_phases.knowledge_graph import KnowledgeGraph
    from integrations.ipfs_datasets.logic import attach_canonical_legal_ir_source_obligations
    from mediator.integrations.graph_tools import project_factual_kg

    if not isinstance(body, Mapping) or not isinstance(case_file, Mapping):
        raise LegalAnalysisError("legal_analysis_field")
    forbidden = {"source_text", "current_source", "legal_context", "applicability_context", "user_facts",
        "factual_premises", "admitted_law", "source_record", "canonical_source", "receipt", "canonical_receipt"}
    if forbidden.intersection(body):
        raise LegalAnalysisError("client_case_authority")
    allowed = {"request_id", "source_content_hash", "vocabulary", "typed_obligations", "emitted_lean",
        "expected_private_revision", "expected_session_revision"}
    if set(body) - allowed or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise LegalAnalysisError("legal_analysis_bounds")
    source_hash = body.get("source_content_hash")
    selected = current_case_legal_ir_source(case_file, source_hash, case_id=case_id)
    stored, record, admission = selected["stored"], selected["record"], selected["admission"]
    current_review, text, metadata = selected["review"], selected["text"], selected["metadata"]
    fields = _request_body({**dict(body), "source_text": text})
    fields.pop("supplied_receipt")
    context = case_file.get("legal_context")
    context = context if isinstance(context, Mapping) else {}
    applicability = current_review.get("governing_applicability")
    if applicability not in {"applicable", "inapplicable", "limited", "unknown"}:
        applicability = "unknown"
    # A source can be admitted to storage while its case applicability remains
    # unresolved. Retain that distinction instead of manufacturing applicable law.
    declared_applicability = case_file.get("legal_context_applicability")
    if (declared_applicability != "explicit"
            or admission.get("source_scope_sha256") != source_scope_sha256):
        applicability = "unknown"
    source_context = {"authority_version": str(metadata.get("authority_version") or ""),
        "effective_date": str(metadata.get("effective_date") or ""), "applicability": applicability}
    for name, value in (("jurisdiction", context.get("jurisdiction")),
                        ("forum", case_file.get("legal_context_forum"))):
        if isinstance(value, str) and value.strip():
            source_context[name] = value
    try:
        graph = KnowledgeGraph.from_dict(deepcopy(dict(knowledge_graph)))
        factual = project_factual_kg(graph, case_id=case_id)
    except (TypeError, ValueError, KeyError, AttributeError):
        raise LegalAnalysisError("legal_analysis_unavailable") from None
    facts = [row for row in factual.get("user_statements", [])
        if isinstance(row, dict) and row.get("admitted_user_fact") is True]
    bounded = [row for row in facts if isinstance(row.get("text"), str) and len(row["text"]) <= 512][:16]
    fields.update(current_source=text, user_facts=[row["text"] for row in bounded],
        applicability_context=source_context,
        legal_context={"citation": str(record.get("citation") or ""),
            "authority_locator": str(metadata.get("source_locator") or ""),
            "authority_version": str(metadata.get("authority_version") or ""), "source_text": text})
    payload = attach_canonical_legal_ir_source_obligations(**fields)
    if payload.get("status") == "unavailable":
        raise LegalAnalysisError("canonical_compiler_unavailable")
    payload.update(task_id=TASK_ID, case_id=case_id, admitted_law=False, proof=False, legal_sufficiency=False,
        source_binding={"content_hash": source_hash, "source_record_sha256": _document_sha256(record),
            "source_scope_sha256": source_scope_sha256,
            "authority_locator": str(metadata.get("source_locator") or ""),
            "authority_version": str(metadata.get("authority_version") or ""),
            "source_storage_admitted": True, "governing_applicability": applicability},
        factual_premise_bindings=[{"assertion_id": row["assertion_id"], "source_identity": row["source_identity"]}
            for row in bounded], factual_premises_truncated=len(bounded) != len(facts))
    return payload


def _bounded_text(value: Any, *, limit: int, required: bool) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise LegalAnalysisError("legal_analysis_field")
    text = value.strip()
    if required and not text:
        raise LegalAnalysisError("legal_analysis_field")
    return text


def _canonical_obligation_rows(case_file: Mapping[str, Any]) -> list[Dict[str, str]]:
    stored = case_file.get("canonical_legal_ir_attachment") if isinstance(case_file, Mapping) else None
    if not isinstance(stored, dict):
        return []
    rows = stored.get("typed_obligations")
    if not isinstance(rows, list):
        return []
    projected: list[Dict[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        obligation_id = str(item.get("obligation_id") or item.get("id") or "").strip()
        if not obligation_id:
            continue
        statement = str(item.get("statement") or item.get("text") or item.get("goal") or "").strip()
        source_span = str(item.get("source_span") or item.get("span") or item.get("source_binding") or "").strip()
        source_identity = str(item.get("source_identity") or stored.get("source_identity") or "").strip()
        projected.append({
            "obligation_id": obligation_id[:128],
            "statement": statement[:512],
            "source_span": source_span[:512],
            "source_identity": source_identity[:256],
        })
    return projected


def _classify_trace_row(row: Mapping[str, Any], *, envelope_source: str, expected_source: str) -> Dict[str, Any]:
    status = _bounded_text(row.get("proof_status"), limit=32, required=True)
    if status not in _TRACE_STATUSES:
        raise LegalAnalysisError("legal_analysis_field")
    obligation_source = _bounded_text(row.get("source_identity"), limit=256, required=False) or envelope_source
    engine_name = _bounded_text(row.get("engine_name"), limit=80, required=False)
    engine_version = _bounded_text(row.get("engine_version"), limit=80, required=False)
    counterexample = _bounded_text(row.get("counterexample"), limit=1024, required=False)
    timed_out = row.get("timed_out") is True or status == "timeout"
    prover_missing = row.get("prover_missing") is True or status == "missing_prover"
    drifted = (
        status == "source_drift"
        or (expected_source and envelope_source != expected_source)
        or (obligation_source and envelope_source and obligation_source != envelope_source)
    )
    if drifted:
        status = "source_drift"
    elif timed_out:
        status = "timeout"
    elif prover_missing or (status == "executed" and (not engine_name or not engine_version)):
        status = "missing_prover"
    elif status == "degraded":
        status = "degraded"
    elif status == "not_executed":
        status = "not_executed"
    elif status == "executed":
        status = "executed"
    reported_status = status
    if status == "executed":
        status = "not_executed"
    green = False  # A caller label or engine name is not an issued proof observation.
    if status in _UNAVAILABLE_TRACE_STATUSES or status in {"degraded", "not_executed"}:
        green = False
    return {
        "obligation_id": _bounded_text(row.get("obligation_id"), limit=128, required=True),
        "statement": _bounded_text(row.get("statement"), limit=512, required=True),
        "source_span": _bounded_text(row.get("source_span"), limit=512, required=True),
        "source_identity": obligation_source,
        "source_bound": False,
        "source_binding_status": "unverified_claim",
        "proof_status": status,
        "reported_proof_status": reported_status,
        "reported_engine_name": engine_name,
        "reported_engine_version": engine_version,
        "engine_name": "",
        "engine_version": "",
        "counterexample": counterexample,
        "green_checkmark": green,
        "legal_sufficiency": False,
        "executed_proof": False,
        "governing_legal_authority": False,
        "supplied_legal_sufficiency_ignored": row.get("legal_sufficiency") is True or row.get("green_checkmark") is True,
    }


def record_case_proof_traces(mediator: Any, body: Mapping[str, Any]) -> Dict[str, Any]:
    """Record a display trace. Caller flags cannot create legal sufficiency."""

    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise LegalAnalysisError("legal_analysis_bounds")
    request_id = _bounded_text(body.get("request_id"), limit=80, required=True)
    source_identity = _bounded_text(body.get("source_identity"), limit=256, required=True)
    expected_source = _bounded_text(body.get("expected_source_identity"), limit=256, required=False) or source_identity
    supplied = body.get("obligations")
    if not isinstance(supplied, list) or len(supplied) > 24:
        raise LegalAnalysisError("legal_analysis_bounds")
    case_file = _case_file_from_mediator(mediator)
    rows = [
        _classify_trace_row(item, envelope_source=source_identity, expected_source=expected_source)
        for item in supplied
        if isinstance(item, dict)
    ]
    if len(rows) != len(supplied):
        raise LegalAnalysisError("legal_analysis_field")
    seen = {item["obligation_id"] for item in rows}
    for canonical in _canonical_obligation_rows(case_file):
        if canonical["obligation_id"] in seen:
            continue
        rows.append(_classify_trace_row({
            "obligation_id": canonical["obligation_id"],
            "statement": canonical["statement"] or "source-bound obligation",
            "source_span": canonical["source_span"] or "unspecified-span",
            "source_identity": canonical["source_identity"] or source_identity,
            "proof_status": "not_executed",
            "engine_name": "",
            "engine_version": "",
        }, envelope_source=source_identity, expected_source=expected_source))
    engines = []
    seen_engines = set()
    counterexamples = []
    for item in rows:
        if item["engine_name"] and item["engine_version"]:
            key = (item["engine_name"], item["engine_version"])
            if key not in seen_engines:
                seen_engines.add(key)
                engines.append({"name": item["engine_name"], "version": item["engine_version"]})
        if item["counterexample"]:
            counterexamples.append({
                "obligation_id": item["obligation_id"],
                "trace": item["counterexample"],
                "legal_sufficiency": False,
                "green_checkmark": False,
            })
    payload = {
        "task_id": PROOF_TRACE_TASK_ID,
        "operation": "record_case_proof_traces",
        "request_id": request_id,
        "status": "visible" if rows else "empty",
        "source_identity": source_identity,
        "expected_source_identity": expected_source,
        "source_drift": source_identity != expected_source or any(item["proof_status"] == "source_drift" for item in rows),
        "obligations": rows,
        "counterexamples": counterexamples,
        "engine_versions": engines,
        "proof_status_counts": {name: sum(1 for item in rows if item["proof_status"] == name) for name in _TRACE_STATUSES},
        "legal_sufficiency": False,
        "proof": False,
        "executed_proof": False,
        "governing_legal_authority": False,
        "admitted_law": False,
        "supplied_legal_sufficiency_ignored": body.get("legal_sufficiency") is True or any(item["supplied_legal_sufficiency_ignored"] for item in rows),
        "limitations": [
            "Displayed proof status is not legal sufficiency.",
            "Missing prover, timeout, and source drift stay visible and are not green checkmarks.",
            "This view does not execute a prover and does not admit law.",
        ],
    }
    case_file["proof_trace_display"] = payload
    return payload


def project_proof_traces(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    stored = case_file.get("proof_trace_display") if isinstance(case_file, Mapping) else None
    if not isinstance(stored, dict):
        return {
            "task_id": PROOF_TRACE_TASK_ID,
            "operation": "record_case_proof_traces",
            "status": "empty",
            "obligations": [],
            "counterexamples": [],
            "engine_versions": [],
            "proof_status_counts": {name: 0 for name in _TRACE_STATUSES},
            "legal_sufficiency": False,
            "proof": False,
            "executed_proof": False,
            "governing_legal_authority": False,
            "admitted_law": False,
            "source_drift": False,
            "limitations": ["No proof trace has been recorded. Absence is not a successful proof."],
        }
    projected = deepcopy(stored)
    projected["task_id"] = PROOF_TRACE_TASK_ID
    projected["engine_versions"] = []
    projected["legal_sufficiency"] = False
    projected["proof"] = False
    projected["executed_proof"] = False
    projected["governing_legal_authority"] = False
    projected["admitted_law"] = False
    obligations = projected.get("obligations")
    if isinstance(obligations, list):
        for item in obligations:
            if isinstance(item, dict):
                item["legal_sufficiency"] = False
                item["executed_proof"] = False
                item["governing_legal_authority"] = False
                item["green_checkmark"] = False
                item["source_bound"] = False
                if item.get("proof_status") == "executed":
                    item["reported_proof_status"] = "executed"
                    item["proof_status"] = "not_executed"
                item["engine_name"] = ""
                item["engine_version"] = ""
                if item.get("counterexample"):
                    item["green_checkmark"] = False
    return projected


def project_current_case_proof_traces(analysis: Mapping[str, Any], *, source_text: str | None) -> Dict[str, Any]:
    """Project the current owner's canonical IR without running any engine.

    The workspace provides its freshly verified IR/source. The pinned proof
    adapter has no configured checked substantive kernel; compiler execution,
    serialized engine names and old display claims do not supply that backend.
    """
    if not isinstance(analysis, Mapping):
        raise LegalAnalysisError("legal_analysis_unavailable")
    source_current = analysis.get("source_current") is True
    binding = analysis.get("source_binding")
    binding = binding if isinstance(binding, Mapping) else {}
    source_id = str(binding.get("content_hash") or "")
    owned_text = source_text if isinstance(source_text, str) and len(source_text) <= 8192 else None
    digest = source_id.removeprefix("sha256:")
    source_current = bool(source_current and owned_text is not None
        and hashlib.sha256(owned_text.encode()).hexdigest() == digest)
    rows, invalid_rows = [], 0
    candidates = analysis.get("typed_obligations")
    if not isinstance(candidates, list) or len(candidates) > 32:
        candidates = []
    if source_current:
        for item in candidates:
            if not isinstance(item, Mapping):
                invalid_rows += 1
                continue
            span = item.get("source_span")
            span = span if isinstance(span, Mapping) else {}
            start, end, unit = span.get("start"), span.get("end"), span.get("unit")
            text = None
            if type(start) is int and type(end) is int and 0 <= start < end:
                if unit in {"character", "characters"} and end <= len(owned_text):
                    text = owned_text[start:end]
                elif unit in {"byte", "bytes", "utf-8-bytes"} and end <= len(owned_text.encode()):
                    try:
                        text = owned_text.encode()[start:end].decode()
                    except UnicodeDecodeError:
                        pass
            bound = bool(text is not None and text == span.get("text") == item.get("statement"))
            if not bound or not isinstance(item.get("obligation_id"), str) or not 1 <= len(item["obligation_id"]) <= 128:
                invalid_rows += 1
                continue
            rows.append({"obligation_id": item["obligation_id"],
                "statement": text, "source_span": f"{unit}:{start}-{end}",
                "source_span_binding": deepcopy(dict(span)), "source_identity": source_id,
                "source_bound": True, "proof_status": "not_executed",
                "engine_name": "", "engine_version": "", "counterexample": "",
                "green_checkmark": False, "executed_proof": False,
                "governing_legal_authority": False, "legal_sufficiency": False,
                "proof_verification": {"status": "unavailable", "checked_kernel_verified": False,
                    "reason": "checked_kernel_backend_not_configured"}})
    stale = analysis.get("status") == "stale" or (analysis.get("status") != "empty" and not source_current)
    return {"task_id": PROOF_TRACE_TASK_ID, "operation": "read_current_case_proof_traces",
        "status": "stale" if stale else "unavailable" if rows or invalid_rows else "empty",
        "reason": "legal_case_sources_changed" if stale else "canonical_obligation_source_unbound"
            if invalid_rows else "checked_kernel_backend_not_configured",
        "source_identity": source_id, "source_current": source_current, "source_drift": stale,
        "source_binding": deepcopy(dict(binding)), "obligations": rows,
        "counterexamples": [], "engine_versions": [],
        "proof_status_counts": {name: len(rows) if name == "not_executed" else 0 for name in _TRACE_STATUSES},
        "compiler_execution_verified": analysis.get("current_execution_verified") is True,
        "capabilities": {"read_only": True, "executes_engine": False, "executes_compiler": False,
            "executes_model": False, "checked_kernel_backend_configured": False},
        "proof": False, "executed_proof": False, "admitted_law": False,
        "governing_legal_authority": False, "legal_sufficiency": False,
        "limitations": ["Canonical IR compilation is not an executed substantive proof.",
            "The pinned proof owner has no configured checked kernel; no green checkmark is authorized.",
            "Client engine/status claims and old cached display rows are not proof provenance."]}


def project_dependency_requirements(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    """Read the stored derivation. An empty case is unresolved, not a template."""
    stored = case_file.get("derived_dependency_requirements") if isinstance(case_file, Mapping) else None
    if not isinstance(stored, dict):
        return {"task_id": DEPENDENCY_REQUIREMENT_TASK_ID, "status": "empty", "requirements": [],
            "unresolved_research": [], "admitted_law": False, "proof": False, "legal_sufficiency": False,
            "hardcoded_elements_used": False}
    payload = deepcopy(stored)
    payload["task_id"] = DEPENDENCY_REQUIREMENT_TASK_ID
    payload["proof"] = False
    payload["legal_sufficiency"] = False
    payload["hardcoded_elements_used"] = False
    return payload


def derive_case_dependency_requirements(case_file: Mapping[str, Any], body: Mapping[str, Any]) -> Dict[str, Any]:
    """Derive from the case's admitted passages. Caller rule text is not authority."""
    from applications.legal_context_api import LegalContextError
    from mediator.legal_authority_hooks import derive_admitted_dependency_requirements

    if not isinstance(case_file, Mapping) or not isinstance(body, Mapping):
        raise LegalAnalysisError("legal_analysis_field")
    request_id = body.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 80:
        raise LegalAnalysisError("legal_analysis_field")
    try:
        payload = derive_admitted_dependency_requirements(dict(case_file), dict(body))
    except LegalContextError as exc:
        raise LegalAnalysisError("legal_analysis_field" if exc.code == "legal_context_field" else exc.code) from None
    payload["request_id"] = request_id
    payload["supplied_rule_text_ignored"] = "rule_text" in body or "elements" in body
    return payload


def mount_legal_analysis_routes(app: Any) -> None:
    """Serve only the current encrypted owner, under the issued case capability."""
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool
    from applications.case_routes import _BOUND_HANDLERS
    from applications.complaint_workspace import (ComplaintWorkspaceService, WorkspaceAccess,
        WorkspaceAuthorizationDenied, WorkspacePersistenceError, workspace_access_scope)
    from applications.workspace_case_authority import (current_workspace_case_authority,
        WorkspaceCaseAuthorityError)

    def fail(code):
        return JSONResponse({"error": code, "status": "denied", "executed_proof": False,
            "governing_legal_authority": False, "proof": False}, status_code=legal_analysis_http_status(code))

    def authorized(request, case_id):
        decision = getattr(request.state, "case_authorization", None)
        expected = "case.read" if request.method.upper() in {"GET", "HEAD"} else "case.update"
        if (decision is None or getattr(decision, "permits_case_content", False) is not True
                or getattr(decision, "action", "") != expected):
            raise LegalAnalysisError("legal_analysis_ungranted")
        query_case = str(request.query_params.get("case_id") or "")
        if getattr(decision, "case_id", "") != case_id or (query_case and query_case != case_id):
            raise LegalAnalysisError("cross_case_id")
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise LegalAnalysisError("legal_analysis_unavailable")
        try:
            _mediator, workspace, _root = resolver()
        except Exception:
            raise LegalAnalysisError("legal_analysis_unavailable") from None
        if not isinstance(workspace, ComplaintWorkspaceService):
            raise LegalAnalysisError("legal_analysis_unavailable")
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        authority = current_workspace_case_authority()
        if not actor or authority is None or authority.case_id != case_id:
            raise LegalAnalysisError("legal_analysis_ungranted")
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        return workspace, authority, actor

    def execute(workspace, actor, case_id, body):
        with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
            if body is None:
                return workspace.read_case_legal_analysis(actor, case_id=case_id)
            return workspace.attach_case_legal_analysis(actor, case_id=case_id, request=body)

    async def dispatch(request, case_id, write):
        try:
            workspace, authority, actor = authorized(request, case_id)
            body = None
            if write:
                try:
                    body = await request.json()
                except (UnicodeDecodeError, ValueError):
                    raise LegalAnalysisError("legal_analysis_field") from None
                if not isinstance(body, dict):
                    raise LegalAnalysisError("legal_analysis_field")
            # Permit real logout/revocation to complete while local compilation
            # runs; copied ContextVars retain only this issued request scope.
            payload = await run_in_threadpool(execute, workspace, actor, case_id, body)
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
            return JSONResponse(payload)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return fail("legal_analysis_ungranted")
        except WorkspacePersistenceError as exc:
            return fail("revision_conflict" if exc.code == "revision_conflict" else (
                "unlock_needed" if exc.code == "unlock_needed" else "legal_analysis_unavailable"))
        except LegalAnalysisError as exc:
            return fail(exc.code)

    @app.get(LEGAL_ANALYSIS_PREFIX + "/{case_id}")
    async def read_legal_analysis(case_id: str, request: Request):
        return await dispatch(request, case_id, False)

    @app.post(LEGAL_ANALYSIS_PREFIX + "/{case_id}")
    async def attach_legal_analysis(case_id: str, request: Request):
        return await dispatch(request, case_id, True)


    def definition_execute(workspace, authority, actor, case_id, body=None):
        with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
            payload = (workspace.read_case_definition_correspondence(actor, case_id=case_id) if body is None
                else workspace.bind_case_definition_correspondence(actor, case_id=case_id, request=body))
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
            return payload

    async def definition_apply(request, case_id, *, write=False):
        try:
            workspace, authority, actor = authorized(request, case_id)
            body = await request.json() if write else None
            if write and not isinstance(body, dict):
                raise LegalAnalysisError("legal_analysis_field")
            payload = await run_in_threadpool(definition_execute, workspace, authority, actor, case_id, body)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return definition_fail("legal_analysis_ungranted")
        except WorkspacePersistenceError as exc:
            return definition_fail(str(getattr(exc, "code", "") or "legal_analysis_unavailable"))
        except LegalAnalysisError as exc:
            return definition_fail(exc.code)
        except (ValueError, UnicodeDecodeError):
            return definition_fail("legal_analysis_field")
        return JSONResponse(payload)

    def definition_fail(code):
        return JSONResponse({"error": code, "status": "denied", "task_id": DEFINITION_CORRESPONDENCE_TASK_ID,
            "authorizes_law": False, "authorizes_proof": False, "executed_proof": False,
            "governing_legal_authority": False, "proof": False}, status_code=legal_analysis_http_status(code))

    @app.get(DEFINITION_CORRESPONDENCE_ROUTE)
    async def read_definition_correspondence(case_id: str, request: Request):
        return await definition_apply(request, case_id)

    @app.post(DEFINITION_CORRESPONDENCE_ROUTE)
    async def bind_definition_correspondence(case_id: str, request: Request):
        return await definition_apply(request, case_id, write=True)


    def proof_fail(code):
        return JSONResponse({"task_id": PROOF_TRACE_TASK_ID, "error": code, "status": "unavailable",
            "obligations": [], "engine_versions": [], "counterexamples": [],
            "proof_status_counts": {name: 0 for name in _TRACE_STATUSES},
            "executed_proof": False, "proof": False, "legal_sufficiency": False,
            "governing_legal_authority": False}, status_code=legal_analysis_http_status(code))

    def proof_read(workspace, authority, actor, case_id):
        with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
            result = workspace.read_case_proof_traces(actor, case_id=case_id)
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
            return result

    @app.get(PROOF_TRACE_ROUTE)
    async def read_proof_traces(case_id: str, request: Request):
        try:
            workspace, authority, actor = authorized(request, case_id)
            payload = await run_in_threadpool(proof_read, workspace, authority, actor, case_id)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return proof_fail("legal_analysis_ungranted")
        except WorkspacePersistenceError as exc:
            return proof_fail("revision_conflict" if exc.code == "revision_conflict" else
                "unlock_needed" if exc.code == "unlock_needed" else "legal_analysis_unavailable")
        except LegalAnalysisError as exc:
            return proof_fail(exc.code)
        return JSONResponse(payload)

    def dependency_fail(code):
        return JSONResponse({"task_id": DEPENDENCY_REQUIREMENT_TASK_ID, "error": code, "status": "denied",
            "requirements": [], "unresolved_research": [], "admitted_law": False, "proof": False,
            "legal_sufficiency": False, "hardcoded_elements_used": False},
            status_code=legal_analysis_http_status(code))

    def dependency_execute(workspace, authority, actor, case_id, body=None):
        with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
            payload = (workspace.read_case_dependency_requirements(actor, case_id=case_id) if body is None
                else workspace.derive_case_dependency_requirements(actor, case_id=case_id, request=body))
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
            return payload

    async def dependency_apply(request, case_id, *, write=False):
        try:
            workspace, authority, actor = authorized(request, case_id)
            body = await request.json() if write else None
            if write and not isinstance(body, dict):
                raise LegalAnalysisError("legal_analysis_field")
            payload = await run_in_threadpool(dependency_execute, workspace, authority, actor, case_id, body)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return dependency_fail("legal_analysis_ungranted")
        except WorkspacePersistenceError as exc:
            return dependency_fail("revision_conflict" if exc.code == "revision_conflict" else (
                "unlock_needed" if exc.code == "unlock_needed" else "legal_analysis_unavailable"))
        except LegalAnalysisError as exc:
            return dependency_fail(exc.code)
        except (ValueError, UnicodeDecodeError):
            return dependency_fail("legal_analysis_field")
        return JSONResponse(payload)

    @app.get(DEPENDENCY_REQUIREMENT_ROUTE)
    async def read_dependency_requirements(case_id: str, request: Request):
        return await dependency_apply(request, case_id)

    @app.post(DEPENDENCY_REQUIREMENT_ROUTE)
    async def derive_dependency_requirements(case_id: str, request: Request):
        return await dependency_apply(request, case_id, write=True)

    @app.post(PROOF_TRACE_ROUTE)
    async def record_proof_traces(case_id: str, request: Request):
        try:
            workspace, authority, actor = authorized(request, case_id)
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return proof_fail("legal_analysis_ungranted")
        except LegalAnalysisError as exc:
            return proof_fail(exc.code)
        # No server-issued producer/job capability is configured. Client rows
        # cannot turn a display status into a current executed proof.
        return proof_fail("proof_producer_unavailable")
