"""Read one current encrypted case graph under live browser/case authority.

A mediator cache is not a private-read capability. The bound workspace decrypts
the current session twice around the pure projection. Changed source, locked
keys, or expired request authority refuse publication. Graph refresh uses the
actual owner's current citation_acquisition decision and encrypted source
manifest; it performs local revalidation and grants no remote-egress authority.
This owner-key path does not issue delegated decryption authority or claim
WebSocket/SSE support.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from applications.complaint_workspace import (
    ComplaintWorkspaceService, WorkspaceAccess, WorkspaceAuthorizationDenied,
    WorkspacePersistenceError, workspace_access_scope,
)
from applications.workspace_case_authority import (
    WorkspaceCaseAuthorityError, current_workspace_case_authority,
)
from complaint_phases.knowledge_graph import FactualReviewError, KnowledgeGraph
from mediator.integrations.graph_tools import FactualGraphProjectionError, project_factual_kg

TASK_ID = "CIMP-GUI-21"
REVIEW_TASK_ID = "CIMP-GUI-22"
FACTUAL_GRAPH_PREFIX = "/api/graphs"


def factual_graph_http_status(code: str) -> int:
    if code in {"graph_revision_changed", "stale_graph_revision", "event_conflict"}:
        return 409
    if code in {"unknown_target", "proposal_missing"}:
        return 404
    if code in {"constrained_text", "constrained_record", "source_required", "source_not_user_fact",
                "proposal_required", "proposal_not_hypothesis", "target_required", "unknown_action",
                "revision_refused"}:
        return 400
    if code in {"graph_read_ungranted", "cross_case_id", "actor_authority_required", "actor_not_permitted"}:
        return 403
    if code in {"mediator_graph_hook_unavailable", "knowledge_graph_unavailable", "data_graph_owner_unavailable",
                "workspace_graph_read_unavailable", "private_graph_unavailable", "unlock_needed"}:
        return 503
    return 403


def _read_snapshot(workspace, authority, actor, case_id):
    """Use the public read-only session seam; never an in-memory mediator graph."""
    decision = authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    if authority.action != "case.read" or authority.case_id != case_id:
        raise FactualGraphProjectionError("graph_read_ungranted")
    response = workspace.get_session(actor, case_id=case_id)
    state = response.get("session") if isinstance(response, dict) else None
    if (not isinstance(state, dict) or state.get("case_id") != case_id
            or state.get("user_id") != decision.canonical_owner_principal_id):
        raise FactualGraphProjectionError("cross_case_id")
    interview = state.get("shared_interview")
    graph = interview.get("knowledge_graph") if isinstance(interview, dict) else None
    if not isinstance(graph, dict) or not graph:
        raise FactualGraphProjectionError("knowledge_graph_unavailable")
    try:
        identity = hashlib.sha256(json.dumps({
            "owner": state["user_id"], "case_id": case_id,
            "private_revision": state.get("private_revision"), "shared_interview": interview,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
        hydrated = KnowledgeGraph.from_dict(graph)
    except (ValueError, TypeError, KeyError):
        raise FactualGraphProjectionError("knowledge_graph_unavailable") from None
    authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    return hydrated, identity


def _project_current(workspace, authority, actor, case_id):
    with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
        graph, before = _read_snapshot(workspace, authority, actor, case_id)
        payload = project_factual_kg(graph, case_id=case_id)
        _current_graph, after = _read_snapshot(workspace, authority, actor, case_id)
        if before != after:
            raise FactualGraphProjectionError("graph_revision_changed")
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        payload["factual_review_revision"] = graph.factual_review_revision()
        return payload


def _json_object(raw: bytes) -> dict:
    if not raw:
        raise FactualReviewError("constrained_text")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise FactualReviewError("constrained_text") from None
    if not isinstance(payload, dict):
        raise FactualReviewError("constrained_text")
    return payload


def _review_current(workspace, authority, actor, case_id, body: dict):
    """Delegate encrypted mutation and late publication checks to its owner."""
    authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
        return workspace.review_case_factual_graph(actor, case_id=case_id, updates=body)


def mount_factual_graph_routes(app: Any) -> None:
    """Mount the factual projection. Authorization middleware protects the prefix."""

    from fastapi.responses import JSONResponse

    from applications.case_routes import _BOUND_HANDLERS

    def _fail(exc: FactualGraphProjectionError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "status": "denied"}, status_code=factual_graph_http_status(exc.code))

    def _review_fail(exc: FactualReviewError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "status": "refused"}, status_code=factual_graph_http_status(exc.code))

    @app.get(FACTUAL_GRAPH_PREFIX + "/{case_id}/factual")
    async def read_factual_graph(case_id: str, request: Request):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        if getattr(decision, "action", "") != "case.read":
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        authorized_case = str(getattr(decision, "case_id", "") or "")
        query_case = str(request.query_params.get("case_id") or "")
        if authorized_case != case_id or (query_case and query_case != authorized_case):
            return _fail(FactualGraphProjectionError("cross_case_id"))
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        try:
            _mediator, workspace, _root = resolver()
        except Exception:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        if not isinstance(workspace, ComplaintWorkspaceService):
            return _fail(FactualGraphProjectionError("workspace_graph_read_unavailable"))
        try:
            principal = getattr(request.state, "browser_principal", None)
            actor = getattr(principal, "principal_id", None)
            authority = current_workspace_case_authority()
            if not actor or authority is None:
                raise FactualGraphProjectionError("graph_read_ungranted")
            # ContextVars carry the real issued capability into the managed
            # thread; concurrent logout/revoke can still complete on the loop.
            payload = await run_in_threadpool(_project_current, workspace, authority, actor, authorized_case)
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        except WorkspacePersistenceError as exc:
            code = "unlock_needed" if exc.code == "unlock_needed" else "private_graph_unavailable"
            return _fail(FactualGraphProjectionError(code))
        except FactualGraphProjectionError as exc:
            return _fail(exc)
        payload["task_id"] = TASK_ID
        return JSONResponse(payload)

    @app.post(FACTUAL_GRAPH_PREFIX + "/{case_id}/factual/reviews")
    async def review_factual_graph(case_id: str, request: Request):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        if getattr(decision, "action", "") != "case.update":
            return _review_fail(FactualReviewError("actor_authority_required"))
        if getattr(decision, "membership", "") != "owner":
            return _review_fail(FactualReviewError("actor_not_permitted"))
        authorized_case = str(getattr(decision, "case_id", "") or "")
        if authorized_case != case_id:
            return _fail(FactualGraphProjectionError("cross_case_id"))
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        try:
            _mediator, workspace, _root = resolver()
        except Exception:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        if not isinstance(workspace, ComplaintWorkspaceService):
            return _fail(FactualGraphProjectionError("workspace_graph_read_unavailable"))
        try:
            raw = await request.body()
            body = _json_object(raw)
            supplied_case = str(body.get("case_id") or "")
            if supplied_case and supplied_case != authorized_case:
                return _fail(FactualGraphProjectionError("cross_case_id"))
            principal = getattr(request.state, "browser_principal", None)
            actor = getattr(principal, "principal_id", None)
            authority = current_workspace_case_authority()
            if not actor or authority is None:
                raise FactualReviewError("actor_authority_required")
            payload = await run_in_threadpool(
                _review_current, workspace, authority, actor, authorized_case, body,
            )
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return _review_fail(FactualReviewError("actor_authority_required"))
        except WorkspacePersistenceError as exc:
            code = "unlock_needed" if exc.code == "unlock_needed" else "private_graph_unavailable"
            return _fail(FactualGraphProjectionError(code))
        except FactualReviewError as exc:
            return _review_fail(exc)
        except FactualGraphProjectionError as exc:
            return _fail(exc)
        return JSONResponse(payload)


LAW_DEPENDENCY_TASK_ID = "CIMP-GUI-27"
_LAW_LINK_KINDS = frozenset({"supports", "contradicts", "missing_evidence"})
_MODEL_ORIGINS = frozenset({"model", "llm", "inference", "model_output", "llm_text"})
_NARRATIVE_KEYS = ("user_narrative", "model_output", "llm_text")


class LegalDependencyGraphError(Exception):
    """Fail-closed law-derived graph error. ``code`` is a stable machine reason."""

    def __init__(self, code: str, details: dict | None = None) -> None:
        self.code = str(code)
        self.details = details if isinstance(details, dict) else {}
        super().__init__(self.code)


def legal_dependency_http_status(code: str) -> int:
    if code in {"narrative_not_law", "legal_dependency_field", "refresh_field", "correction_kind_required",
                "caller_graph_rows_not_accepted", "client_case_authority"}:
        return 400
    if code in {
        "stale_case_revision", "stale_consent", "stale_actor_grant", "stale_legal_source_hash",
        "stale_dependency_generation", "stale_late_result", "consent_revision_conflict", "source_unchanged",
        "graph_revision_changed", "operation_conflict", "stale_operation_scope",
        "server_refresh_receipt_required", "current_source_scope_mismatch", "current_legal_context_changed",
    }:
        return 409
    if code in {"graph_read_ungranted", "cross_case_id", "cross_case", "actor_authority_required",
                "actor_not_permitted", "consent_revoked", "purpose_consent_required"}:
        return 403
    if code in {"legal_dependency_unavailable", "mediator_graph_hook_unavailable", "unlock_needed",
                "workspace_graph_read_unavailable", "workspace_graph_refresh_unavailable",
                "actual_workflow_unavailable", "canonical_source_scope_invalid", "actual_refresh_unavailable",
                "late_result_capability_unavailable"}:
        return 503
    return 403


def _mapping(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _admitted_authority(record: Mapping[str, Any] | dict) -> bool:
    return (
        isinstance(record, dict)
        and record.get("admitted_law") is True
        and record.get("status") == "admitted"
        and bool(_clean_text(record.get("source_passage")))
        and bool(_clean_text(record.get("content_hash")))
    )


def _passage_index(case_file: Mapping[str, Any]) -> dict:
    index = case_file.get("legal_source_passage_index")
    return index if isinstance(index, dict) else {}


def _burden_from_authority(admission: Mapping[str, Any], stored: Mapping[str, Any] | None) -> tuple[str, str]:
    """A burden is law only when the stored admitted passage contains that text.

    A burden string on the review record, a user narrative, or model output
    does not become the burden unless the stored passage index already has it.
    """
    passage = _clean_text(admission.get("source_passage"))
    stored_burden = _clean_text((stored or {}).get("burden"))
    if stored_burden and stored_burden in passage:
        return stored_burden, "admitted_passage"
    return "", "missing_from_admitted_authority"


def _requirement_from_admission(admission: Mapping[str, Any], stored: Mapping[str, Any] | None) -> dict:
    passage = _clean_text(admission.get("source_passage"))
    exceptions = admission.get("exceptions")
    if not isinstance(exceptions, list):
        exceptions = []
    exceptions = [item for item in exceptions if isinstance(item, str)]
    burden, burden_status = _burden_from_authority(admission, stored)
    stored_applicability = _clean_text((stored or {}).get("applicability"))
    applicability = _clean_text(admission.get("applicability"))
    if stored is not None and stored_applicability and applicability != stored_applicability:
        applicability = stored_applicability
    return {
        "content_hash": _clean_text(admission.get("content_hash")),
        "authority_identity": _clean_text(admission.get("authority_identity")),
        "requirement": passage,
        "burden": burden,
        "burden_status": burden_status,
        "exceptions": exceptions,
        "applicability": applicability,
        "jurisdiction": _clean_text(admission.get("jurisdiction")),
        "effective_date": _clean_text(admission.get("effective_date")),
        "treatment_state": _clean_text(admission.get("treatment_state")),
        "version": _clean_text(admission.get("version")),
        "source": "admitted_authority",
        "admitted_law": True,
        "proof": False,
        "legal_sufficiency": False,
        "rewritten_by_user_or_model": False,
    }


def _node_rows(graph: Any) -> list[dict]:
    if graph is None:
        return []
    raw_nodes = getattr(graph, "nodes", None)
    if raw_nodes is None and isinstance(graph, dict):
        raw_nodes = graph.get("nodes")
    rows = []
    if isinstance(raw_nodes, dict):
        values = list(raw_nodes.values())
    elif isinstance(raw_nodes, list):
        values = raw_nodes
    else:
        return []
    for item in values:
        if hasattr(item, "to_dict"):
            item = item.to_dict()
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _edge_rows(graph: Any) -> list[dict]:
    if graph is None:
        return []
    raw = getattr(graph, "dependencies", None)
    if raw is None and isinstance(graph, dict):
        raw = graph.get("edges") if isinstance(graph.get("edges"), list) else graph.get("dependencies")
    if isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, list):
        values = raw
    else:
        return []
    rows = []
    for item in values:
        if hasattr(item, "to_dict"):
            item = item.to_dict()
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _node_text(node: Mapping[str, Any]) -> str:
    attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    return _clean_text(node.get("description") or node.get("name") or attributes.get("description"))


def _node_origin(node: Mapping[str, Any]) -> str:
    attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    return _clean_text(node.get("origin") or attributes.get("origin") or node.get("source") or attributes.get("source")).lower()


def _node_hash(node: Mapping[str, Any]) -> str:
    attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    return _clean_text(node.get("content_hash") or attributes.get("content_hash") or attributes.get("authority_text_sha256"))


def _node_source_id(node: Mapping[str, Any]) -> str:
    attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    provenance = node.get("provenance") if isinstance(node.get("provenance"), dict) else {}
    return _clean_text(
        node.get("source_id")
        or node.get("immutable_source_id")
        or attributes.get("source_id")
        or provenance.get("source_id")
        or node.get("id")
    )


def _edge_kind(edge: Mapping[str, Any]) -> str:
    kind = _clean_text(edge.get("dependency_type") or edge.get("link_kind")).lower()
    if kind == "supports":
        return "supports"
    if kind == "contradicts":
        return "contradicts"
    return ""


def _edge_endpoint(edge: Mapping[str, Any], side: str) -> str:
    return _clean_text(edge.get(side) or edge.get(side.replace("_id", "")) or "")


def project_law_derived_dependency_graph(
    case_file: Mapping[str, Any] | None, *, dependency_graph: Any = None, case_id: str = "",
) -> dict:
    """Project the canonical DG/source owners under the current case context.

    Admission/index labels are not evidence. Every rule is re-bound through
    the same typed source adapter used by actual mediator construction.
    This pure function grants no access and never reads a global catalog.
    """
    from copy import deepcopy
    from complaint_phases.dependency_graph import DependencyGraph, NodeType
    from complaint_phases.intake_case_file import refresh_explicit_legal_context
    from integrations.ipfs_datasets.legal import adapt_sourced_legal_requirements, intake_legal_selection
    from integrations.ipfs_datasets.logic import extract_source_bound_rule_candidates
    from integrations.ipfs_datasets.types import user_assertion_from_mapping

    if not isinstance(case_file, Mapping):
        raise LegalDependencyGraphError("legal_dependency_unavailable")
    case = deepcopy(dict(case_file))
    context = refresh_explicit_legal_context(case)
    policy = case.get("legal_context_applicability")
    if "legal_context_applicability" in case and policy != "explicit":
        context = dict(context, jurisdiction="unknown", jurisdiction_explicit=False)
    if isinstance(dependency_graph, Mapping):
        try:
            dependency_graph = DependencyGraph.from_dict(deepcopy(dict(dependency_graph)))
        except (KeyError, TypeError, ValueError, AttributeError):
            dependency_graph = None
    graph = dependency_graph if isinstance(dependency_graph, DependencyGraph) else None
    claims = case.get("candidate_claims") or []
    if not claims and graph is not None:
        claims = [{"type": node.attributes.get("claim_type")} for node in graph.nodes.values()
            if isinstance(node.attributes, dict) and node.node_type == NodeType.CLAIM]
    selection = intake_legal_selection(context, claims)
    requirements, rejected, factual_links = [], [], []
    accepted = {}

    for row in case.get("legal_authority_admissions") or []:
        if isinstance(row, dict):
            rejected.append({"origin": "admission_label", "content_hash": _clean_text(row.get("content_hash")),
                "text": "", "reason": "serialized_admission_labels_are_not_source_proof",
                "rewrites_legal_rule": False})
    for key in _NARRATIVE_KEYS:
        text = _clean_text(case.get(key))
        if text:
            rejected.append({"origin": key, "content_hash": "", "text": text[:500],
                "reason": "user_or_model_text_not_law", "rewrites_legal_rule": False})
    if graph is not None and selection["ready_to_select"]:
        for node in graph.nodes.values():
            attributes = node.attributes
            if (not isinstance(attributes, dict)
                    or attributes.get("dependency_class") != "legally_sourced_requirement"):
                continue
            reason = ""
            entry = None
            if (node.node_type not in {NodeType.LEGAL_ELEMENT, NodeType.REQUIREMENT}
                    or attributes.get("source_available") is not True
                    or attributes.get("support_eligible") is not True
                    or attributes.get("legal_support_invalidated") is True):
                reason = "source_support_unavailable"
            else:
                record = deepcopy(attributes)
                record.update(name=node.name, description=node.description)
                claim_type = str(attributes.get("claim_type") or "unknown")
                entries = adapt_sourced_legal_requirements({claim_type: [record]}, legal_context=context)[claim_type]
                entry = entries[0] if entries else None
                if not entry or entry.get("intake_requirement_status") != "source_bound":
                    reason = (entry or {}).get("unresolved_reason") or "source_proof_unavailable"
            if reason:
                rejected.append({"origin": "dependency_graph", "requirement_id": node.id,
                    "content_hash": _clean_text(attributes.get("source_hash")), "text": "",
                    "reason": str(reason), "rewrites_legal_rule": False})
                continue
            derived = extract_source_bound_rule_candidates(entry["source_record"])["promoted_requirements"]
            proof = next((row for row in derived if row.get("rule_text") == entry.get("rule_text")
                and row.get("source_span") == entry.get("source_span")
                and row.get("source_hash") == entry.get("source_hash")), None)
            if proof is None:
                continue
            # Clause labels come from a fresh canonical owner extraction and
            # retain exact source spans. They are not adjudicated legal meaning.
            exception_rows = [deepcopy(row) for row in proof["structure"].get("exceptions", [])
                if isinstance(row, dict) and row.get("span_status") == "exact"]
            temporal = deepcopy(proof["temporal_applicability"])
            rule = {
                "requirement_id": node.id,
                "rule_id": str(attributes.get("rule_id") or proof["authority_id"]),
                "claim_id": str((attributes.get("dependency_scope") or {}).get("claim_id") or ""),
                "content_hash": proof["source_hash"],
                "source_hash_scope": proof["source_hash_scope"],
                "authority_text_sha256": proof["authority_text_sha256"],
                "span_sha256": proof["span_sha256"],
                "source_span": deepcopy(proof["source_span"]),
                "authority_identity": proof["authority_identity"],
                "requirement": proof["rule_text"],
                "burden": "",
                "burden_status": "unavailable_from_source_owner",
                "exceptions": [row["text"] for row in exception_rows],
                "exception_source_spans": exception_rows,
                "exceptions_status": "source_clause_candidates",
                "applicability": "applicable" if temporal.get("applicable") is True else "unknown",
                "temporal_applicability": temporal,
                "jurisdiction": proof["jurisdiction"],
                "effective_date": temporal.get("effective_date") or "",
                "treatment_state": "support_eligible",
                "treatment_edges": deepcopy(proof["treatment_edges"]),
                "version": proof["authority_version"],
                "context_revision": entry["context_revision"],
                "source": "admitted_authority",
                "admitted_law": True,
                "proof": False,
                "legal_sufficiency": False,
                "rewritten_by_user_or_model": False,
            }
            requirements.append(rule)
            accepted[node.id] = rule
    supported = set()
    if graph is not None:
        for edge in graph.dependencies.values():
            kind = str(getattr(edge.dependency_type, "value", edge.dependency_type))
            if kind not in {"supports", "contradicts"}:
                continue
            if edge.target_id in accepted:
                rule_id, fact_id = edge.target_id, edge.source_id
            elif edge.source_id in accepted:
                rule_id, fact_id = edge.source_id, edge.target_id
            else:
                continue
            fact = graph.nodes.get(fact_id)
            if fact is None or fact.node_type not in {NodeType.FACT, NodeType.EVIDENCE}:
                continue
            attributes = fact.attributes if isinstance(fact.attributes, dict) else {}
            provenance = attributes.get("provenance") if isinstance(attributes.get("provenance"), dict) else {}
            raw = provenance.get("user_assertion") or attributes.get("user_assertion")
            envelope = None
            try:
                candidate = user_assertion_from_mapping(raw) if isinstance(raw, dict) else None
                if candidate is not None and candidate.is_asserted_user_fact:
                    envelope = candidate
            except (TypeError, ValueError, OverflowError):
                pass
            activity = str(attributes.get("activity_status") or "unknown")
            verified = envelope is not None and activity == "active"
            effective_support = bool(kind == "supports" and verified and edge.strength > 0)
            rule = accepted[rule_id]
            factual_links.append({
                "link_kind": kind, "requirement_id": rule_id, "content_hash": rule["content_hash"],
                "fact_source_id": envelope.stable_id if envelope is not None else fact.id,
                "fact_text": envelope.source_span_text if envelope is not None else fact.description or fact.name,
                "origin": "user_assertion" if envelope is not None else "unverified_graph_record",
                "authority_is_user_fact": verified, "assertion_verified": envelope is not None,
                "activity_status": activity, "rewrites_legal_rule": False, "reason": "", "proof": False,
                "effective_support": effective_support,
            })
            if effective_support:
                supported.add(rule_id)
    for rule in requirements:
        if rule["requirement_id"] not in supported:
            factual_links.append({"link_kind": "missing_evidence", "requirement_id": rule["requirement_id"],
                "content_hash": rule["content_hash"], "fact_source_id": "", "fact_text": "",
                "origin": "projection", "authority_is_user_fact": False, "rewrites_legal_rule": False,
                "reason": "no_verified_supporting_fact", "proof": False})
    return {
        "task_id": LAW_DEPENDENCY_TASK_ID, "case_id": case_id, "requirements": requirements,
        "factual_links": factual_links, "rejected_narratives": rejected, "admitted_count": len(requirements),
        "user_facts_are_not_law": True, "rules_rewritten_by_user_or_model": False,
        "proof": False, "legal_sufficiency": False,
        "research_gap": "" if requirements else ("unresolved_current_legal_context"
            if not selection["ready_to_select"] else "no_admitted_authority"),
        "limitations": [
            "Rules are re-bound to current source bytes, jurisdiction, date and revision by the canonical owner.",
            "The pinned source owner does not provide a verified burden of proof; burden stays unavailable.",
            "Exception clauses are source-bound pattern candidates, not adjudicated legal meaning.",
            "User narratives, model output and serialized admission labels do not establish law or proof.",
            "This projection grants no access and does not claim WebSocket or SSE support.",
        ],
    }


def _materials_from_mediator(mediator: Any) -> tuple[dict, Any]:
    from complaint_phases.phase_manager import ComplaintPhase

    case_file = None
    graph = None
    phase_manager = getattr(mediator, "phase_manager", None)
    if phase_manager is not None and hasattr(phase_manager, "get_phase_data"):
        stored = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
        if isinstance(stored, dict):
            case_file = stored
        graph = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    if case_file is None:
        stored = getattr(mediator, "intake_case_file", None)
        if isinstance(stored, dict):
            case_file = stored
    if graph is None:
        graph = getattr(mediator, "dependency_graph", None)
    if case_file is None:
        raise LegalDependencyGraphError("legal_dependency_unavailable")
    return case_file, graph


LEGAL_REFRESH_TASK_ID = "CIMP-GUI-28"
_REFRESH_PURPOSE = "citation_acquisition"


def current_admitted_source_hashes(case_file: Mapping[str, Any] | None, *, dependency_graph=None) -> list[str]:
    """Re-derive actual current DG admissions; serialized labels grant nothing."""
    if not isinstance(case_file, Mapping) or dependency_graph is None:
        return []
    projected = project_law_derived_dependency_graph(case_file, dependency_graph=dependency_graph)
    return sorted({row["content_hash"] for row in projected["requirements"]})


def _workflow_service(mediator: Any) -> Any:
    service = getattr(mediator, "workflow_actions", None)
    if service is not None and hasattr(service, "refresh_legal_dependency_graph"):
        return service
    if hasattr(mediator, "refresh_legal_dependency_graph"):
        return mediator
    raise LegalDependencyGraphError("mediator_graph_hook_unavailable")


def _exact_int(value: Any, code: str) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise LegalDependencyGraphError(code)
    return value


def _refresh_error(receipt: Mapping[str, Any]) -> None:
    error = receipt.get("error") if isinstance(receipt.get("error"), dict) else {}
    code = _clean_text(error.get("code"))
    if code:
        raise LegalDependencyGraphError(code, {"task_id": LEGAL_REFRESH_TASK_ID, "applied": False, "proof": False})


def refresh_versioned_law_graph(mediator: Any, *, live: Mapping[str, Any], body: Mapping[str, Any],
                                canonical_source_records=None) -> dict:
    """Refresh the law graph after a source, context, or factual correction.

    ``live`` is the server binding: actor, grant, case revision, and consent.
    Body expectations must match that binding and the admitted source hashes.
    """
    if not isinstance(live, Mapping) or not isinstance(body, Mapping):
        raise LegalDependencyGraphError("refresh_field")
    case_file, _graph = _materials_from_mediator(mediator)
    workflow = _workflow_service(mediator)
    if canonical_source_records is None:
        hashes = current_admitted_source_hashes(case_file, dependency_graph=_graph)
    else:
        try:
            hashes = list(workflow._refresh_manifest_hashes(mediator, canonical_source_records))
        except (TypeError, ValueError):
            raise LegalDependencyGraphError("canonical_source_scope_invalid") from None
    supplied = body.get("legal_source_hashes")
    if supplied != hashes:
        raise LegalDependencyGraphError("stale_legal_source_hash")
    case_id = _clean_text(live.get("case_id"))
    if _clean_text(body.get("case_id")) not in {"", case_id}:
        raise LegalDependencyGraphError("cross_case_id")
    if not _clean_text(body.get("operation_id")):
        raise LegalDependencyGraphError("refresh_field")
    workflow = _workflow_service(mediator)
    receipt = workflow.refresh_legal_dependency_graph(
        case_id=case_id,
        actor_principal_id=_clean_text(live.get("actor_principal_id")),
        correction_kind=_clean_text(body.get("correction_kind")),
        case_revision=_exact_int(live.get("case_revision"), "stale_case_revision"),
        consent_generation=_exact_int(live.get("consent_generation"), "stale_consent"),
        consent_revoked=live.get("consent_revoked") is True,
        grant_revision=_exact_int(live.get("grant_revision"), "stale_actor_grant"),
        granted_actions=live.get("granted_actions"),
        legal_source_hashes=hashes,
        operation_id=_clean_text(body.get("operation_id")),
        expected_case_revision=_exact_int(body.get("expected_case_revision"), "refresh_field"),
        expected_consent_generation=_exact_int(body.get("expected_consent_generation"), "refresh_field"),
        expected_grant_revision=_exact_int(body.get("expected_grant_revision"), "refresh_field"),
        expected_dependency_generation=_exact_int(body.get("expected_dependency_generation"), "refresh_field"),
        links=body.get("links"),
        questions=body.get("questions"),
        proof_obligations=body.get("proof_obligations"),
        successors=body.get("successors") if isinstance(body.get("successors"), dict) else {},
        canonical_source_records=canonical_source_records,
    )
    _refresh_error(receipt)
    receipt["task_id"] = LEGAL_REFRESH_TASK_ID
    receipt["rules_rewritten_by_user_or_model"] = False
    return receipt


def accept_versioned_law_late_result(mediator: Any, *, live: Mapping[str, Any], body: Mapping[str, Any],
                                    canonical_source_records=None) -> dict:
    """Revalidate a server-computed receipt; no caller/model rows are installed."""
    if not isinstance(live, Mapping) or not isinstance(body, Mapping):
        raise LegalDependencyGraphError("refresh_field")
    case_file, _graph = _materials_from_mediator(mediator)
    workflow = _workflow_service(mediator)
    if canonical_source_records is None:
        hashes = current_admitted_source_hashes(case_file, dependency_graph=_graph)
    else:
        try:
            hashes = list(workflow._refresh_manifest_hashes(mediator, canonical_source_records))
        except (TypeError, ValueError):
            raise LegalDependencyGraphError("canonical_source_scope_invalid") from None
    case_id = _clean_text(live.get("case_id"))
    if _clean_text(body.get("case_id")) not in {"", case_id}:
        raise LegalDependencyGraphError("cross_case_id")
    if not _clean_text(body.get("operation_id")):
        raise LegalDependencyGraphError("refresh_field")
    workflow = _workflow_service(mediator)
    receipt = workflow.accept_legal_refresh_late_result(
        case_id=case_id,
        actor_principal_id=_clean_text(live.get("actor_principal_id")),
        case_revision=_exact_int(live.get("case_revision"), "stale_case_revision"),
        consent_generation=_exact_int(live.get("consent_generation"), "stale_consent"),
        consent_revoked=live.get("consent_revoked") is True,
        grant_revision=_exact_int(live.get("grant_revision"), "stale_actor_grant"),
        granted_actions=live.get("granted_actions"),
        legal_source_hashes=hashes,
        dependency_generation=_exact_int(body.get("dependency_generation"), "refresh_field"),
        operation_id=_clean_text(body.get("operation_id")),
        claimed=dict(body),
    )
    _refresh_error(receipt)
    receipt["task_id"] = LEGAL_REFRESH_TASK_ID
    receipt["rules_rewritten_by_user_or_model"] = False
    return receipt


def _read_current_law_materials(workspace, authority, actor, case_id):
    """Read canonical legal materials through the public, read-only owner."""
    from copy import deepcopy

    decision = authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    if authority.action != "case.read" or authority.case_id != case_id:
        raise LegalDependencyGraphError("graph_read_ungranted")
    response = workspace.get_session(actor, case_id=case_id)
    state = response.get("session") if isinstance(response, dict) else None
    if (not isinstance(state, dict) or state.get("case_id") != case_id
            or state.get("user_id") != decision.canonical_owner_principal_id):
        raise LegalDependencyGraphError("cross_case_id")
    shared = state.get("shared_interview")
    if (not isinstance(shared, dict) or not isinstance(shared.get("intake_case_file"), dict)
            or not isinstance(shared.get("dependency_graph"), dict)):
        raise LegalDependencyGraphError("legal_dependency_unavailable")
    try:
        identity = hashlib.sha256(json.dumps({
            "owner": state["user_id"], "case_id": case_id,
            "private_revision": state.get("private_revision"), "shared_interview": shared,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    except (ValueError, TypeError, KeyError):
        raise LegalDependencyGraphError("legal_dependency_unavailable") from None
    authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    return deepcopy(shared["intake_case_file"]), deepcopy(shared["dependency_graph"]), identity


def _project_current_law_graph(workspace, authority, actor, case_id):
    with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
        case_file, graph, before = _read_current_law_materials(workspace, authority, actor, case_id)
        payload = project_law_derived_dependency_graph(case_file, dependency_graph=graph, case_id=case_id)
        _case_again, _graph_again, after = _read_current_law_materials(workspace, authority, actor, case_id)
        if before != after:
            raise LegalDependencyGraphError("graph_revision_changed")
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        return payload


def _refresh_current_law_graph(workspace, authority, actor, case_id, updates, *, late=False):
    """Delegate the encrypted transition to its actual current owner only."""
    if not isinstance(workspace, ComplaintWorkspaceService) or not isinstance(updates, dict):
        raise LegalDependencyGraphError("workspace_graph_refresh_unavailable")
    if {"canonical_source_records", "source_records", "reviewed_source_record", "source_admission",
            "legal_authority_admissions", "legal_source_passage_index", "live"}.intersection(updates):
        raise LegalDependencyGraphError("client_case_authority")
    common = {"operation_id", "case_id", "legal_source_hashes", "expected_private_revision",
              "expected_session_revision", "expected_source_scope_sha256"}
    permitted = common | ({"refresh_operation_id", "actor_principal_id", "case_revision", "consent_generation",
        "consent_revoked", "grant_revision", "dependency_generation"} if late else
        {"correction_kind", "expected_case_revision", "expected_consent_generation", "expected_grant_revision",
         "expected_dependency_generation"})
    if set(updates) - permitted:
        raise LegalDependencyGraphError("caller_graph_rows_not_accepted")
    if updates.get("case_id", case_id) != case_id:
        raise LegalDependencyGraphError("cross_case_id")
    if not isinstance(updates.get("legal_source_hashes"), list):
        raise LegalDependencyGraphError("refresh_field")
    if any(not isinstance(value, str) or len(value) != 64
           or any(char not in "0123456789abcdef" for char in value) for value in updates["legal_source_hashes"]):
        raise LegalDependencyGraphError("stale_legal_source_hash")
    if len(updates["legal_source_hashes"]) > 128:
        raise LegalDependencyGraphError("refresh_field")
    if "expected_private_revision" in updates:
        value = updates["expected_private_revision"]
        if (not isinstance(value, str) or not value.isascii() or not value.isdecimal()
                or len(value) > 32 or str(int(value)) != value):
            raise LegalDependencyGraphError("refresh_field")
    for key in permitted.intersection(updates):
        if key != "expected_private_revision" and key.endswith(("_revision", "_generation")):
            _exact_int(updates[key], "refresh_field")
    method_name = "revalidate_case_legal_dependency_refresh" if late else "refresh_case_legal_dependency_graph"
    method = getattr(workspace, method_name, None)
    if not callable(method):
        raise LegalDependencyGraphError("workspace_graph_refresh_unavailable")
    with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        if authority.action != "case.update" or authority.case_id != case_id:
            raise LegalDependencyGraphError("actor_not_permitted")
        result = method(actor, case_id=case_id, updates=updates)
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        return result


def mount_law_dependency_graph_routes(app: Any) -> None:
    """Mount the read-only law-derived dependency graph beside the factual graph."""

    from fastapi.responses import JSONResponse

    from applications.case_routes import _BOUND_HANDLERS
    from applications.workspace_case_authority import current_workspace_case_authority

    def _fail(exc: LegalDependencyGraphError, *, task_id: str | None = None) -> JSONResponse:
        payload = {
            "error": exc.code,
            "status": "denied",
            "task_id": LEGAL_REFRESH_TASK_ID if exc.code not in {"narrative_not_law"} else LAW_DEPENDENCY_TASK_ID,
            "rules_rewritten_by_user_or_model": False,
            "proof": False,
            "applied": False,
        }
        payload.update(exc.details)
        if task_id is not None:
            payload["task_id"] = task_id
        payload["error"] = exc.code
        payload["proof"] = False
        return JSONResponse(payload, status_code=legal_dependency_http_status(exc.code))

    async def _refresh_body(request: Request) -> dict:
        raw = await request.body()
        if not raw:
            raise LegalDependencyGraphError("refresh_field")
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise LegalDependencyGraphError("refresh_field") from None
        if not isinstance(parsed, dict):
            raise LegalDependencyGraphError("refresh_field")
        return parsed

    def _authorized(request: Request, case_id: str):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            raise LegalDependencyGraphError("graph_read_ungranted")
        action = getattr(decision, "action", "")
        expected = "case.read" if request.method.upper() in {"GET", "HEAD"} else "case.update"
        if action != expected:
            raise LegalDependencyGraphError("graph_read_ungranted")
        authorized_case = str(getattr(decision, "case_id", "") or "")
        query_case = str(request.query_params.get("case_id") or "")
        if authorized_case != case_id or (query_case and query_case != authorized_case):
            raise LegalDependencyGraphError("cross_case_id")
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise LegalDependencyGraphError("mediator_graph_hook_unavailable")
        try:
            mediator, _workspace, _root = resolver()
            authority = current_workspace_case_authority()
        except Exception as exc:
            raise LegalDependencyGraphError("mediator_graph_hook_unavailable") from exc
        if mediator is None or authority is None or getattr(authority, "case_id", None) != case_id:
            raise LegalDependencyGraphError("graph_read_ungranted")
        return mediator

    @app.get(FACTUAL_GRAPH_PREFIX + "/{case_id}/legal-dependency")
    async def read_law_dependency_graph(case_id: str, request: Request):
        try:
            decision = getattr(request.state, "case_authorization", None)
            if (decision is None or getattr(decision, "permits_case_content", False) is not True
                    or getattr(decision, "action", "") != "case.read"):
                raise LegalDependencyGraphError("graph_read_ungranted")
            query_case = str(request.query_params.get("case_id", "") or "")
            if decision.case_id != case_id or (query_case and query_case != case_id):
                raise LegalDependencyGraphError("cross_case_id")
            resolver = _BOUND_HANDLERS.get()
            if resolver is None:
                raise LegalDependencyGraphError("mediator_graph_hook_unavailable")
            _mediator, workspace, _root = resolver()
            if not isinstance(workspace, ComplaintWorkspaceService):
                raise LegalDependencyGraphError("workspace_graph_read_unavailable")
            authority = current_workspace_case_authority()
            actor = getattr(getattr(request.state, "browser_principal", None), "principal_id", None)
            if authority is None or not actor:
                raise LegalDependencyGraphError("graph_read_ungranted")
            payload = await run_in_threadpool(_project_current_law_graph, workspace, authority, actor, case_id)
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return _fail(LegalDependencyGraphError("actor_not_permitted"), task_id=LAW_DEPENDENCY_TASK_ID)
        except WorkspacePersistenceError as exc:
            code = str(getattr(exc, "code", "") or "")
            return _fail(LegalDependencyGraphError("unlock_needed" if code == "unlock_needed" else "legal_dependency_unavailable"), task_id=LAW_DEPENDENCY_TASK_ID)
        except LegalDependencyGraphError as exc:
            return _fail(exc, task_id=LAW_DEPENDENCY_TASK_ID)
        return JSONResponse(payload)

    @app.post(FACTUAL_GRAPH_PREFIX + "/{case_id}/legal-dependency")
    async def reject_law_dependency_rewrite(case_id: str, request: Request):
        """User narratives and model output cannot be posted back as legal rules."""
        try:
            _authorized(request, case_id)
            raw = await request.body()
            if raw:
                parsed = json.loads(raw.decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise LegalDependencyGraphError("legal_dependency_field")
        except LegalDependencyGraphError as exc:
            return _fail(exc)
        except (UnicodeDecodeError, ValueError):
            return _fail(LegalDependencyGraphError("legal_dependency_field"))
        return JSONResponse(
            {
                "error": "narrative_not_law",
                "status": "refused",
                "task_id": LAW_DEPENDENCY_TASK_ID,
                "rules_rewritten_by_user_or_model": False,
                "proof": False,
            },
            status_code=400,
        )

    def _current_owner(request, case_id):
        decision = getattr(request.state, "case_authorization", None)
        actor = getattr(getattr(request.state, "browser_principal", None), "principal_id", None)
        if (decision is None or getattr(decision, "permits_case_content", False) is not True
                or getattr(decision, "action", "") != "case.update" or not actor):
            raise LegalDependencyGraphError("actor_not_permitted")
        if decision.case_id != case_id:
            raise LegalDependencyGraphError("cross_case_id")
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise LegalDependencyGraphError("workspace_graph_refresh_unavailable")
        _mediator, workspace, _root = resolver()
        authority = current_workspace_case_authority()
        if not isinstance(workspace, ComplaintWorkspaceService) or authority is None:
            raise LegalDependencyGraphError("workspace_graph_refresh_unavailable")
        return workspace, authority, actor

    async def _apply_refresh(request, case_id, *, late=False):
        from applications.legal_research_api import LegalResearchError

        try:
            workspace, authority, actor = _current_owner(request, case_id)
            body = await _refresh_body(request)
            payload = await run_in_threadpool(_refresh_current_law_graph, workspace, authority,
                                              actor, case_id, body, late=late)
            _refresh_error(payload)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return _fail(LegalDependencyGraphError("actor_not_permitted"))
        except WorkspacePersistenceError as exc:
            code = str(getattr(exc, "code", "") or "")
            public = ("unlock_needed" if code == "unlock_needed" else "graph_revision_changed"
                      if code == "revision_conflict" else "legal_dependency_unavailable")
            return _fail(LegalDependencyGraphError(public))
        except LegalResearchError as exc:
            public = {"purpose_consent_required": "purpose_consent_required", "consent_revoked": "consent_revoked",
                "consent_revision_conflict": "stale_consent", "caller_graph_rows_not_accepted": "caller_graph_rows_not_accepted",
                "legal_research_revision_conflict": "stale_legal_source_hash", "cross_case_id": "cross_case_id"}.get(
                    str(getattr(exc, "code", "") or ""), "legal_dependency_unavailable")
            return _fail(LegalDependencyGraphError(public))
        except LegalDependencyGraphError as exc:
            return _fail(exc)
        return JSONResponse(payload)

    @app.post(FACTUAL_GRAPH_PREFIX + "/{case_id}/legal-dependency/refresh")
    async def refresh_law_dependency_graph(case_id: str, request: Request):
        return await _apply_refresh(request, case_id)

    @app.post(FACTUAL_GRAPH_PREFIX + "/{case_id}/legal-dependency/late-result")
    async def accept_law_dependency_late_result(case_id: str, request: Request):
        return await _apply_refresh(request, case_id, late=True)
