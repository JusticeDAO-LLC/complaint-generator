"""Compose case routes behind verified sessions and server-owned case handlers.

Case identifiers select a resource; they never authenticate its caller. A
BrowserSessionService verifies the received cookie and CSRF token before the
shared CaseActionAuthorizer sees the actor. Case tenants and principal-roster
tenants are distinct namespaces. Legacy captured-mediator chat stays retired. JSON control bodies default to
1 MiB, 1024 ASGI messages and five seconds after authentication (login is
bounded to 16 KiB before credential verification). Multipart/raw uploads are
explicitly unqualified and denied; these limits do not claim upload support.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import asyncio
import math
from pathlib import Path
import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qs

from starlette.requests import Request

from .browser_sessions import BrowserSessionError, BrowserSessionService, SESSION_COOKIE, browser_session_http_status
from .case_access import BOUNDARIES, CaseAccessError, CaseActionAuthorizer
from .case_audit import path_targets_audit_download
from .case_directory import CaseNamespace

CASE_ROUTE_KINDS = ("case", "graph", "message", "admin")
COMPOSITION_NAME = "compose_case_routes"
PROTECTED_PREFIXES = ("/api/complaint-workspace", "/api/claim-support", "/api/documents", "/api/chat", "/api/graphs", "/api/legal-context", "/api/legal-research", "/api/legal-analysis")
CASE_CATALOG_PREFIX = "/api/cases"
CASE_PAGE_PATH = "/cases"
ADMIN_API_PREFIX = "/api/admin"
AUDIT_EXPORT_PATH = "/api/cases/audit-exports"
ADMIN_AUDIT_EXPORT_PATH = "/api/admin/audit/export"
MESSAGE_INBOX_PATH = "/case-messages"
MESSAGE_INBOX_SCRIPT_PATH = "/static/complaint_case_messages.js"
GRANT_CONTROL_PATH = "/case-grants"
RETIRED_EXACT_PATHS = frozenset({"/cookies", "/load_profile", "/create_profile", "/api/chat", "/api/chat/fallback"})
AUTH_PATHS = frozenset("/api/complaint-workspace/auth/" + name for name in ("login", "logout", "rotate", "session"))
INQUIRY_CONTRACT_PATHS = frozenset({
    "/api/complaint-workspace/intake-chat",
    "/api/complaint-workspace/mcp/call",
    "/api/complaint-workspace/mcp/rpc",
})
INQUIRY_CONFLICT_CODE = "stale_question"
INQUIRY_CONFLICT_STATUS = 409
_MODULES: List[Tuple[str, Callable[..., None], Tuple[str, ...]]] = []
RouteMount = Callable[[Any, Optional[CaseActionAuthorizer]], None]
_BOUND_HANDLERS: ContextVar[Optional[Callable[[], Tuple[Any, Any, Any]]]] = ContextVar("case_route_handlers", default=None)


@dataclass(frozen=True)
class CaseJSONBodyLimits:
    """Explicit bounded JSON control admission; never a multipart upload cap."""

    max_bytes: int = 1024 * 1024
    max_messages: int = 1024
    read_timeout_seconds: float = 5.0

    def __post_init__(self):
        if (type(self.max_bytes) is not int or not 1 <= self.max_bytes <= 16 * 1024 * 1024
                or type(self.max_messages) is not int or not 1 <= self.max_messages <= 4096
                or isinstance(self.read_timeout_seconds, bool)
                or not isinstance(self.read_timeout_seconds, (int, float))
                or not math.isfinite(self.read_timeout_seconds)
                or not 0 < self.read_timeout_seconds <= 30):
            raise ValueError("invalid_case_json_body_limits")


class _BodyAdmissionError(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code
        super().__init__(code)


class CaseHandlerRegistry:
    """Explicit operator bindings, never a captured mediator shared by all cases."""

    def __init__(self) -> None:
        self._bindings: Dict[Tuple[str, str, str], Tuple[Any, Any, Any, Any]] = {}

    def bind(self, case: CaseNamespace, *, mediator: Any, workspace_service: Any,
             download_root: Optional[Path] = None,
             authorize_delegated: Optional[Callable[[Any], bool]] = None) -> None:
        if not isinstance(case, CaseNamespace) or mediator is None or workspace_service is None:
            raise CaseAccessError("case_handler_binding")
        key = (case.tenant_id, case.case_id, case.resource_id)
        if key in self._bindings:
            raise CaseAccessError("case_handler_already_bound")
        root = Path(download_root).resolve(strict=True) if download_root is not None else None
        if root is not None and not root.is_dir():
            raise CaseAccessError("case_download_root")
        for bound_mediator, bound_workspace, bound_root, _grant_check in self._bindings.values():
            if mediator is bound_mediator or workspace_service is bound_workspace:
                raise CaseAccessError("case_handler_reused")
            if root is not None and bound_root is not None and (root.is_relative_to(bound_root) or bound_root.is_relative_to(root)):
                raise CaseAccessError("case_download_root_overlap")
        self._bindings[key] = (mediator, workspace_service, root, authorize_delegated)

    def authorized_correspondence_activity(self, *, actor_principal_id: str, case_id: str,
                                           tenant_id: str, resource_id: str) -> Mapping[str, Any]:
        """Read mediator turns and review decisions from the bound workspace.

        A missing binding or a workspace without this view is unavailable.
        The registry does not copy the records or grant access.
        """

        binding = self._bindings.get((tenant_id, case_id, resource_id))
        unavailable = {"mediator_turns": "unavailable", "review_decisions": "unavailable"}
        if binding is None or resource_id == "":
            return unavailable
        reader = getattr(binding[1], "authorized_correspondence_activity", None)
        if not callable(reader):
            return unavailable
        payload = reader(actor_principal_id=actor_principal_id, case_id=case_id,
                         tenant_id=tenant_id, resource_id=resource_id)
        if not isinstance(payload, Mapping):
            from .case_correspondence_api import CaseCorrespondenceError
            raise CaseCorrespondenceError("activity_record")
        return payload

    def resolve(self, decision: Any) -> Tuple[Any, Any, Any]:
        key = (decision.tenant_id, decision.case_id, decision.resource_id)
        try:
            mediator, workspace, root, grant_check = self._bindings[key]
        except KeyError:
            raise CaseAccessError("case_handler_unavailable") from None
        if decision.membership != "owner":
            # Policy membership alone does not grant decryption. The later
            # private-grant owner can supply a live checker; absent grants deny.
            try:
                granted = callable(grant_check) and grant_check(decision) is True
            except Exception:
                granted = False
            if not granted:
                raise CaseAccessError("case_key_grant_required")
        return mediator, workspace, root


def case_download_root() -> Path:
    resolver = _BOUND_HANDLERS.get()
    if resolver is None:
        raise CaseAccessError("case_handler_unavailable")
    handlers = resolver()
    if handlers[2] is None:
        raise CaseAccessError("case_handler_unavailable")
    return handlers[2]


class _RequestCaseTarget:
    def __init__(self, index: int) -> None:
        self._index = index

    def __getattr__(self, name: str) -> Any:
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise CaseAccessError("case_handler_unavailable")
        return getattr(resolver()[self._index], name)


def _credential_request(scope: Dict[str, Any]) -> Request:
    """Pass actual wire credentials to Task05 without resource identity claims.

    The case tenant is not the authentication roster tenant. Resource and
    actor claims are separately checked below, not relabeled as credentials.
    Actual method/cookie/CSRF values remain unchanged; no identity is injected.
    """
    credential_scope = dict(scope)
    credential_scope["headers"] = [(key, value) for key, value in scope.get("headers", [])
                                   if key.lower() in {b"cookie", b"x-csrf-token"}]
    credential_scope["query_string"] = b""
    credential_scope["state"] = {}
    return Request(credential_scope)


class _WorkspaceSessions:
    """Reuse Task05 verification for the mounted workspace dependency too."""

    def __init__(self, service: BrowserSessionService) -> None:
        self._service = service

    async def bind_http(self, request: Request, *, allow_anonymous: bool):
        if _path_of(request.scope) in AUTH_PATHS:
            return await self._service.bind_http(request, allow_anonymous=allow_anonymous)
        return await self._service.bind_http(_credential_request(request.scope), allow_anonymous=False)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._service, name)


def register_case_route_module(kind: str, mount: RouteMount, *, protected_prefixes: Sequence[str]) -> None:
    if kind not in CASE_ROUTE_KINDS or not callable(mount):
        raise ValueError("case route module must declare an approved kind and callable")
    prefixes = tuple(str(prefix) for prefix in protected_prefixes if str(prefix).strip())
    if not prefixes or any(not prefix.startswith("/api/") for prefix in prefixes):
        raise ValueError("case route module must declare protected API prefixes")
    _MODULES.append((kind, mount, prefixes))


def unregister_case_route_module(mount: RouteMount) -> None:
    _MODULES[:] = [item for item in _MODULES if item[1] is not mount]


def _is_case_catalog_path(path: str) -> bool:
    return path == CASE_PAGE_PATH or path == CASE_CATALOG_PREFIX or path.startswith(CASE_CATALOG_PREFIX + "/")


def _is_admin_api_path(path: str) -> bool:
    return path == ADMIN_API_PREFIX or path.startswith(ADMIN_API_PREFIX + "/")


def durability_readiness_boundary() -> dict[str, Any]:
    """Storage readiness is a separate owner from interview and legal readiness.

    A storage, key, or backend failure must not clear or satisfy interview or
    legal readiness. Callers may read this boundary; storage routes publish
    only ``storage_readiness``.
    """

    return {
        "storage_readiness_owner": "case_storage",
        "interview_readiness_owner": "interview",
        "legal_readiness_owner": "legal",
        "storage_sets_interview_readiness": False,
        "storage_sets_legal_readiness": False,
        "storage_failure_clears_interview_readiness": False,
        "storage_failure_clears_legal_readiness": False,
    }


def compose_case_routes(app: Any, *, authorizer: Optional[CaseActionAuthorizer], mediator: Any = None,
                        include_workspace: bool = True, include_review: bool = True,
                        include_document: bool = True, workspace_service: Any = None,
                        browser_sessions: Optional[BrowserSessionService] = None,
                        case_handlers: Optional[CaseHandlerRegistry] = None,
                        json_body_limits: Optional[CaseJSONBodyLimits] = None,
                        case_catalog: Any = None,
                        case_assignments: Any = None,
                        case_messages: Any = None,
                        case_attachments: Any = None,
                        case_storage: Any = None,
                        evidence_workspace: Any = None,
                        case_consent: Any = None, gui_inference_transport: Any = None,
                        gui_inference_route: Any = None,
                        operational_admin: Any = None, case_reviews: Any = None,
                        case_notifications: Any = None, case_audit: Any = None) -> Any:
    """Mount the same fail-closed boundary in every production app variant.

    Historical mediator/workspace arguments grant no ambient case access.
    Operators bind each case explicitly in case_handlers. Missing session or
    handler configuration stays unavailable, without a trusted-local fallback.
    """
    if authorizer is not None and not isinstance(authorizer, CaseActionAuthorizer):
        raise CaseAccessError("authority_owners")
    if browser_sessions is not None and not isinstance(browser_sessions, BrowserSessionService):
        raise CaseAccessError("authentication_configuration")
    if case_handlers is not None and not isinstance(case_handlers, CaseHandlerRegistry):
        raise CaseAccessError("case_handler_binding")
    from .case_api import CaseCatalog
    if case_catalog is not None and not isinstance(case_catalog, CaseCatalog):
        raise CaseAccessError("case_catalog")
    if json_body_limits is not None and not isinstance(json_body_limits, CaseJSONBodyLimits):
        raise ValueError("invalid_case_json_body_limits")
    limits = json_body_limits if json_body_limits is not None else CaseJSONBodyLimits()
    sessions = browser_sessions if browser_sessions is not None else BrowserSessionService.unavailable()
    from .complaint_workspace_api import create_complaint_workspace_router
    from .fastapi_compat import attach_router_routes
    router = create_complaint_workspace_router(_RequestCaseTarget(1), browser_sessions=_WorkspaceSessions(sessions))
    if not include_workspace:
        router.routes[:] = [route for route in router.routes if getattr(route, "path", None) in AUTH_PATHS]
    attach_router_routes(app, router)
    if include_review:
        from .review_api import attach_claim_support_review_routes
        attach_claim_support_review_routes(app, _RequestCaseTarget(0))
    if include_document:
        from .document_api import attach_document_routes
        attach_document_routes(app, _RequestCaseTarget(0))
    modules = tuple(_MODULES)
    extensions = tuple((kind, prefix) for kind, _mount, prefixes in modules for prefix in prefixes)
    for _kind, mount, _prefixes in modules:
        mount(app, authorizer)
    from .case_assignment_api import CaseAssignmentService, mount_case_assignments
    if case_assignments is not None and not isinstance(case_assignments, CaseAssignmentService):
        raise CaseAccessError("case_assignments")
    mount_case_assignments(app)
    _mount_grant_control(app)
    from .case_message_api import CaseMessageService, mount_case_messages
    if case_messages is not None and not isinstance(case_messages, CaseMessageService):
        raise CaseAccessError("case_messages")
    mount_case_messages(app)
    from .case_correspondence_api import mount_case_correspondence
    mount_case_correspondence(app)
    _mount_case_message_inbox(app)
    from .case_attachment_api import CaseAttachmentService, mount_case_attachments
    if case_attachments is not None and not isinstance(case_attachments, CaseAttachmentService):
        raise CaseAccessError("case_attachments")
    mount_case_attachments(app)
    from .case_storage_api import CaseStorageService, mount_case_storage
    if case_storage is not None and not isinstance(case_storage, CaseStorageService):
        raise CaseAccessError("case_storage")
    mount_case_storage(app)
    from .evidence_workspace_api import mount_evidence_workspace
    from .evidence_annotation_store import EvidenceAnnotationStore
    from integrations.evidence_workspace import EvidenceWorkspace
    if evidence_workspace is not None and not isinstance(evidence_workspace, EvidenceWorkspace):
        raise CaseAccessError("evidence_workspace")
    mount_evidence_workspace(app)
    annotation_root = getattr(evidence_workspace, "_root", None)
    app.state.evidence_annotation_store = (
        EvidenceAnnotationStore(Path(annotation_root) / "annotations") if annotation_root is not None else None
    )
    if case_messages is not None and case_attachments is not None:
        case_attachments.bind_message_admission(case_messages.store)
        case_messages.bind_attachments(case_attachments)
    from .case_consent_api import CaseConsentService, mount_case_consent
    if case_consent is not None and not isinstance(case_consent, CaseConsentService):
        raise CaseAccessError("case_consent")
    if gui_inference_transport is not None and not callable(gui_inference_transport):
        raise CaseAccessError("gui_inference_transport")
    from .gui_inference_route import resolve_gui_inference_route
    selected_inference_transport = resolve_gui_inference_route(gui_inference_route,
        synthetic_transport=gui_inference_transport)
    mount_case_consent(app)
    from .case_notifications import CaseNotificationService, mount_case_notifications
    if case_notifications is not None and not isinstance(case_notifications, CaseNotificationService):
        raise CaseAccessError("case_notifications")
    if isinstance(case_notifications, CaseNotificationService):
        case_notifications.observe(case_assignments, case_messages)
    mount_case_notifications(app)
    from .lawyer_workspace_api import LAWYER_WORKSPACE_API, mount_lawyer_workspace
    mount_lawyer_workspace(app)
    from .case_api import mount_case_catalog
    mount_case_catalog(app)
    if not (LAWYER_WORKSPACE_API == CASE_CATALOG_PREFIX or LAWYER_WORKSPACE_API.startswith(CASE_CATALOG_PREFIX + "/")):
        raise CaseAccessError("lawyer_workspace_route")
    from .graph_api import mount_factual_graph_routes, mount_law_dependency_graph_routes
    mount_factual_graph_routes(app)
    mount_law_dependency_graph_routes(app)
    from .legal_context_api import mount_legal_context_routes
    mount_legal_context_routes(app)
    from .legal_research_api import mount_legal_research_routes
    mount_legal_research_routes(app)
    from .legal_analysis_api import DEFINITION_CORRESPONDENCE_ROUTE, PROOF_TRACE_ROUTE, mount_legal_analysis_routes
    if not any(DEFINITION_CORRESPONDENCE_ROUTE.startswith(prefix + "/") or DEFINITION_CORRESPONDENCE_ROUTE.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        raise CaseAccessError("definition_correspondence_route")
    if not any(PROOF_TRACE_ROUTE.startswith(prefix + "/") or PROOF_TRACE_ROUTE.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        raise CaseAccessError("proof_trace_route")
    mount_legal_analysis_routes(app)
    from .case_review import (
        LAWYER_REVIEW_ROUTE,
        LAWYER_WORKSPACE_ROUTE,
        REVIEW_ITEMS_ROUTE,
        REVIEW_TRANSITIONS_ROUTE,
        WORKFLOW_STAGE_ROUTE,
        DRAFT_VERSIONS_ROUTE,
        DRAFT_REVIEWS_ROUTE,
        DRAFT_EXPORTS_ROUTE,
        mount_lawyer_review_routes,
    )
    if not any(LAWYER_REVIEW_ROUTE.startswith(prefix + "/") or LAWYER_REVIEW_ROUTE.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        raise CaseAccessError("lawyer_review_route")
    if not any(LAWYER_WORKSPACE_ROUTE.startswith(prefix + "/") or LAWYER_WORKSPACE_ROUTE.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        raise CaseAccessError("lawyer_workspace_route")
    if not any(REVIEW_ITEMS_ROUTE.startswith(prefix + "/") or REVIEW_ITEMS_ROUTE.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        raise CaseAccessError("review_items_route")
    if not any(REVIEW_TRANSITIONS_ROUTE.startswith(prefix + "/") or REVIEW_TRANSITIONS_ROUTE.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        raise CaseAccessError("review_transitions_route")
    for route_template, code in (
        (WORKFLOW_STAGE_ROUTE, "workflow_stage_route"),
        (DRAFT_VERSIONS_ROUTE, "draft_versions_route"),
        (DRAFT_REVIEWS_ROUTE, "draft_reviews_route"),
        (DRAFT_EXPORTS_ROUTE, "draft_exports_route"),
    ):
        if not any(route_template.startswith(prefix + "/") or route_template.startswith(prefix) for prefix in PROTECTED_PREFIXES):
            raise CaseAccessError(code)
    mount_lawyer_review_routes(app)
    from .admin_api import OperationalAdminService, mount_operational_admin
    from .case_audit import CaseAuditStore
    if operational_admin is not None and not isinstance(operational_admin, OperationalAdminService):
        raise CaseAccessError("operational_admin")
    if case_audit is not None and not isinstance(case_audit, CaseAuditStore):
        raise CaseAccessError("case_audit")
    mount_operational_admin(app)
    _mount_case_audit_exports(app)
    app.state.operational_admin = operational_admin
    app.state.case_audit = case_audit
    from .case_directory import CaseDirectory
    directory = getattr(case_catalog, "_cases", None)
    app.state.case_directory = directory if isinstance(directory, CaseDirectory) else None
    app.state.case_authorizer = authorizer
    app.state.browser_sessions = sessions
    app.state.case_handlers = case_handlers
    app.state.case_catalog = case_catalog
    app.state.case_assignments = case_assignments
    app.state.case_messages = case_messages
    app.state.case_attachments = case_attachments
    app.state.case_storage = case_storage
    app.state.evidence_workspace = evidence_workspace
    app.state.durability_readiness_boundary = durability_readiness_boundary()
    app.state.case_consent = case_consent
    from .case_review_store import CaseReviewService
    if case_reviews is not None and (type(case_reviews) is not CaseReviewService or case_reviews.authorizer is not authorizer):
        raise CaseAccessError('case_reviews')
    app.state.case_reviews = case_reviews
    app.state.case_notifications = case_notifications
    app.state.gui_inference_transport = selected_inference_transport
    app.state.gui_inference_route = gui_inference_route
    app.state.case_json_body_limits = limits
    app.state.case_route_composition = COMPOSITION_NAME
    app.state.case_route_extension_kinds = tuple(kind for kind, _mount, _prefixes in modules)
    app.state.case_route_boundaries = BOUNDARIES
    app.add_middleware(CaseRouteAuthorizationMiddleware, authorizer=authorizer, sessions=sessions,
                       case_handlers=case_handlers, extensions=extensions, json_body_limits=limits)
    return app


def _mount_case_audit_exports(app: Any) -> None:
    """Case-scoped audit export. Direct file reads are not this route."""

    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool

    from .case_audit import CaseAuditError, CaseAuditStore, audit_export_session_verifier

    def _store(request: Any) -> CaseAuditStore:
        store = getattr(request.app.state, "case_audit", None)
        if not isinstance(store, CaseAuditStore):
            raise CaseAuditError("audit_export_unavailable")
        return store

    def _actor(request: Any) -> Any:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        roles = getattr(principal, "roles", None)
        if not isinstance(actor, str) or actor == "" or not isinstance(roles, tuple):
            raise CaseAuditError("unauthenticated")
        return principal

    @app.post(AUDIT_EXPORT_PATH)
    async def export_case_audit(request: Request):
        try:
            principal = _actor(request)
            material = getattr(request.state, "case_catalog_material", None)
            body = dict(material) if isinstance(material, dict) else {}
            body["actor_principal_id"] = principal.principal_id
            verify = audit_export_session_verifier(request)
            payload = await run_in_threadpool(_store(request).export_from_request, body,
                                             session_roles=principal.roles, verify_access=verify)
            verify()
        except CaseAuditError as exc:
            status = 503 if exc.code == "audit_export_unavailable" else 403
            return JSONResponse({"error": exc.code}, status_code=status)
        return JSONResponse(payload)

    @app.get(AUDIT_EXPORT_PATH + "/{export_id}")
    async def download_case_audit_export(export_id: str):
        del export_id
        return JSONResponse({"error": "direct_download_denied"}, status_code=403)


def _mount_grant_control(app: Any) -> None:
    """Serve the workspace document that owns collaborator grant controls.

    The page does not authenticate by itself. Grant reads and changes use the
    assignment API. WebSocket and SSE are not used.
    """

    from fastapi.responses import HTMLResponse

    root = Path(__file__).resolve().parent.parent

    @app.get(GRANT_CONTROL_PATH)
    async def grant_control_page():
        html = (root / "templates" / "workspace.html").read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"cache-control": "no-store"})


def _mount_case_message_inbox(app: Any) -> None:
    """Serve the conversation inbox shell. Message APIs stay on the catalog boundary.

    The page is a static document. It does not authenticate by itself and does
    not open a WebSocket or event stream. Polling uses the existing HTTP routes.
    """

    from fastapi.responses import HTMLResponse, Response

    root = Path(__file__).resolve().parent.parent

    @app.get(MESSAGE_INBOX_PATH)
    async def case_message_inbox():
        html = (root / "templates" / "case_messages.html").read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"cache-control": "no-store"})

    @app.get(MESSAGE_INBOX_SCRIPT_PATH)
    async def case_message_inbox_script():
        script = (root / "static" / "complaint_case_messages.js").read_bytes()
        return Response(script, media_type="text/javascript; charset=utf-8", headers={"cache-control": "no-store"})


def _path_of(scope: Dict[str, Any]) -> str:
    path = str(scope.get("path") or "")
    return path.rstrip("/") if len(path) > 1 else path


def _within_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def boundary_for_path(path: str) -> str:
    if "/mcp" in path:
        return "mcp"
    if path.startswith("/api/documents"):
        return "download"
    if path.startswith("/api/claim-support"):
        return "review"
    return "http"


def _nested_interview(payload: Any) -> Optional[Dict[str, Any]]:
    """Find the WorkflowActionService receipt inside HTTP or MCP envelopes."""
    if not isinstance(payload, dict):
        return None
    interview = payload.get("interview")
    if isinstance(interview, dict) and ("status" in interview or "inquiry" in interview):
        return interview
    for key in ("structuredContent", "result"):
        nested = _nested_interview(payload.get(key))
        if nested is not None:
            return nested
    return None


def shared_inquiry_conflict(payload: Any) -> bool:
    """True when the service refused a stale or mismatched inquiry answer.

    A missing expected revision is not a conflict. Only an explicit service
    refusal with ``stale_question`` is. Callers must not treat that refusal
    as a successful advance.
    """
    interview = _nested_interview(payload)
    if not isinstance(interview, dict) or interview.get("status") != "refused":
        return False
    error = interview.get("error") if isinstance(interview.get("error"), dict) else {}
    return error.get("code") == INQUIRY_CONFLICT_CODE


def _status_for_denial(code: str) -> int:
    if code in {"unauthenticated", "missing_principal", "authorizer_required", "request_body"}:
        return 401
    if code in {"revision_conflict", INQUIRY_CONFLICT_CODE}:
        return 409
    if code == "case_handler_unavailable":
        return 503
    return 403


def _material_from_scope(scope: Dict[str, Any], body: bytes) -> Dict[str, Any]:
    query = scope.get("query_string") or b""
    parsed = parse_qs(query.decode("latin1"), keep_blank_values=True)
    material = {key: values[-1] for key, values in parsed.items() if values}
    headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
    fields = {"x-actor-principal-id": "actor_principal_id", "x-tenant-id": "tenant_id",
              "x-case-id": "case_id", "x-resource-id": "resource_id", "x-case-action": "action",
              "x-expected-revision": "expected_revision", "x-expected-membership-revision": "expected_membership_revision",
              "x-owner-principal-id": "owner_principal_id", "x-role": "role"}
    for header, field in fields.items():
        if header in headers:
            material[field] = headers[header]
    if "x-trusted-local" in headers:
        material["trusted_local"] = True
    if body:
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            payload = None
        if isinstance(payload, dict):
            material.update(payload)
    for field in ("expected_revision", "expected_membership_revision", "membership_version"):
        value = material.get(field)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            material[field] = int(value.strip())
    return material


def _check_actor_claims(scope: Dict[str, Any], body: bytes, principal_id: str) -> None:
    query = parse_qs((scope.get("query_string") or b"").decode("latin1"), keep_blank_values=True)
    claims = []
    for key in ("actor_principal_id", "principal_id", "user_id"):
        if any(value != principal_id for value in query.get(key, [])):
            raise CaseAccessError("actor_mismatch")
    headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
    for key in ("x-actor-principal-id", "x-user-id", "x-principal-id"):
        if key in headers and headers[key] != principal_id:
            raise CaseAccessError("actor_mismatch")
    if body:
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            payload = None
        if isinstance(payload, dict):
            claims.append(payload)
            for container in (payload.get("arguments"), payload.get("params")):
                if isinstance(container, dict):
                    claims.append(container)
                    if isinstance(container.get("arguments"), dict):
                        claims.append(container["arguments"])
    for claim in claims:
        for key in ("actor_principal_id", "principal_id", "user_id"):
            if key in claim and claim[key] != principal_id:
                raise CaseAccessError("actor_mismatch")


def _required_action(path: str, method: str, material: Mapping[str, Any], extensions) -> str:
    grant_id = material.get("membership_grant_id")
    if isinstance(grant_id, str) and grant_id != "":
        if "/inference" in path:
            return "case.read" if method in {"GET", "HEAD"} else "case.review"
        if path.rstrip("/").endswith("/intake-chat") and material.get("interview_action") == "resume":
            return "case.read"
    if path.rstrip('/').endswith('/lawyer-reviews/share') or path.rstrip('/').endswith('/review-transitions'):
        return 'case.update'
    if _within_prefix(path, "/api/legal-research") and path.rstrip("/").endswith("/admissions"):
        return "case.read" if method in {"GET", "HEAD"} else "case.review"
    # Assigned-lawyer review is case.review. It is not case.update and not an owner-key grant.
    if "/lawyer-review" in path or "/review-items" in path or "/review-transitions" in path:
        return "case.read" if method in {"GET", "HEAD"} else "case.review"
    # Factual review writes the encrypted owner graph. Assigned-lawyer review
    # authority is not an owner-key grant, so this route stays case.update.
    if _within_prefix(path, "/api/graphs"):
        return "case.read" if method in {"GET", "HEAD"} else "case.update"
    if path.startswith("/api/documents"):
        if path.endswith("/workflow-stage"):
            return "case.read"
        if path.endswith("/draft-versions"):
            return "case.read" if method in {"GET", "HEAD"} else "case.update"
        if path.endswith("/draft-reviews"):
            return "case.read" if method in {"GET", "HEAD"} else "case.review"
        if path.endswith("/draft-exports"):
            return "case.download"
        return "case.download" if method in {"GET", "HEAD"} else "case.update"
    if path.startswith("/api/claim-support"):
        return "case.review" if method in {"GET", "HEAD"} else "case.update"
    if "/mcp" in path:
        params = material.get("params") if isinstance(material.get("params"), dict) else {}
        name = str(material.get("tool_name") or params.get("name") or "")
        rpc_method = str(material.get("method") or "") if path.endswith("/mcp/rpc") else ""
        if path.endswith("/mcp/call"):
            name = str(material.get("tool_name") or "")
        elif path.endswith("/mcp/rpc"):
            name = str(params.get("name") or "") if rpc_method == "tools/call" else ""
        read = method in {"GET", "HEAD"} or rpc_method in {"ping", "initialize", "tools/list"}
        read = read or name.startswith(("complaint.get_", "complaint.list_")) or name in {"complaint.review_case", "complaint.search_corpus"}
        return "case.read" if read else "case.update"
    for kind, prefix in extensions:
        if _within_prefix(path, prefix):
            if kind == "admin":
                return "account.metadata.read" if method in {"GET", "HEAD"} else "role.assign"
            if kind == "message" and method not in {"GET", "HEAD"}:
                return "case.message.send"
    return "case.read" if method in {"GET", "HEAD"} else "case.update"


async def _read_json_body(scope, receive, limits: CaseJSONBodyLimits, *, login=False):
    """Bound actual bytes/messages/time, then replay the identical JSON body."""
    headers = {key.lower(): value for key, value in scope.get("headers", [])}
    content_type = headers.get(b"content-type", b"").decode("latin1").split(";", 1)[0].strip().lower()
    if content_type and content_type != "application/json" and not content_type.endswith("+json"):
        raise _BodyAdmissionError(415, "body_transport_unqualified")
    maximum = min(limits.max_bytes, 16 * 1024) if login else limits.max_bytes
    length = headers.get(b"content-length")
    if length is not None:
        try:
            declared = int(length)
        except (ValueError, TypeError):
            raise _BodyAdmissionError(400, "request_body_length") from None
        if declared < 0:
            raise _BodyAdmissionError(400, "request_body_length")
        if declared > maximum:
            raise _BodyAdmissionError(413, "request_body_too_large")
    chunks, total, messages = [], 0, 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limits.read_timeout_seconds
    try:
        async with asyncio.timeout(limits.read_timeout_seconds):
            while True:
                if loop.time() >= deadline:
                    raise _BodyAdmissionError(408, "request_body_timeout")
                message = await receive()
                if loop.time() >= deadline:
                    raise _BodyAdmissionError(408, "request_body_timeout")
                messages += 1
                if messages > limits.max_messages:
                    raise _BodyAdmissionError(413, "request_body_too_many_messages")
                if message.get("type") != "http.request":
                    raise _BodyAdmissionError(400, "request_body_incomplete")
                chunk = message.get("body", b"")
                if not isinstance(chunk, bytes):
                    raise _BodyAdmissionError(400, "request_body_invalid")
                total += len(chunk)
                if total > maximum:
                    raise _BodyAdmissionError(413, "request_body_too_large")
                if chunk:
                    chunks.append(chunk)
                if not message.get("more_body", False):
                    break
    except TimeoutError:
        raise _BodyAdmissionError(408, "request_body_timeout") from None
    body = b"".join(chunks)
    if body:
        if not content_type:
            raise _BodyAdmissionError(415, "body_transport_unqualified")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise _BodyAdmissionError(400, "request_body_invalid") from None
        if not isinstance(payload, dict):
            raise _BodyAdmissionError(400, "request_body_invalid")
    if loop.time() >= deadline:
        raise _BodyAdmissionError(408, "request_body_timeout")
    sent = False

    async def replay():
        nonlocal sent
        data = b"" if sent else body
        sent = True
        return {"type": "http.request", "body": data, "more_body": False}
    return body, replay


def _inquiry_conflict_send(path: str, send):
    """Rewrite a single-body 200 that carries a stale inquiry into HTTP 409.

    Multi-chunk bodies are forwarded unchanged. This boundary does not claim
    WebSocket, SSE, or streaming support.
    """
    if path not in INQUIRY_CONTRACT_PATHS:
        return send
    pending_start = None
    forwarded = False

    async def wrapped(message):
        nonlocal pending_start, forwarded
        if forwarded:
            await send(message)
            return
        if message.get("type") == "http.response.start":
            pending_start = message
            return
        if message.get("type") != "http.response.body":
            await send(message)
            return
        start = pending_start if pending_start is not None else {"type": "http.response.start", "status": 200, "headers": []}
        pending_start = None
        # The first body commits the response. If it is a stream, all later
        # chunks pass through without re-parsing or sending another start.
        forwarded = True
        status = int(start.get("status") or 200)
        body = message.get("body") or b""
        if status == 200 and not message.get("more_body", False) and body:
            try:
                payload = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                payload = None
            if shared_inquiry_conflict(payload):
                encoded = json.dumps(payload).encode("utf-8")
                headers = [
                    (key, value)
                    for key, value in start.get("headers", [])
                    if key.lower() != b"content-length"
                ]
                headers.append((b"content-length", str(len(encoded)).encode("ascii")))
                await send({"type": "http.response.start", "status": INQUIRY_CONFLICT_STATUS, "headers": headers})
                await send({"type": "http.response.body", "body": encoded, "more_body": False})
                return
        await send(start)
        await send(message)

    return wrapped


async def _send_json(send, status, payload):
    data = json.dumps(payload).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode())]})
    await send({"type": "http.response.body", "body": data, "more_body": False})


def _enforce_live_participant_grant(scope: Dict[str, Any], actor: str, material: Mapping[str, Any], action: str) -> None:
    """Apply the current membership grant on download, inference, resume, and other API use.

    A request that names ``membership_grant_id`` is checked against the live
    grant before case content handlers run. Owner requests are not narrowed by
    the participant grant. ``membership_version`` is the membership revision;
    it is separate from the authorizer's ``expected_membership_revision``.
    """

    from .case_assignment_api import CaseAssignmentError, CaseAssignmentService

    grant_id = material.get("membership_grant_id")
    if not isinstance(grant_id, str) or grant_id == "":
        return
    path = _path_of(scope)
    if "/inference" in path:
        surface = "inference"
    elif path.rstrip("/").endswith("/intake-chat") and material.get("interview_action") == "resume":
        surface = "browser_resume"
    elif path.startswith("/api/documents") or action == "case.download":
        surface = "download"
    else:
        surface = "api"
    service = getattr(scope["app"].state, "case_assignments", None)
    if not isinstance(service, CaseAssignmentService):
        raise CaseAssignmentError("assignment_unavailable")
    service.enforce_participant(
        actor,
        grant_id=grant_id,
        surface=surface,
        expected_version=material.get("membership_version"),
        request_action=action,
    )


class CaseRouteAuthorizationMiddleware:
    def __init__(self, app: Any, *, authorizer, sessions, case_handlers, extensions, json_body_limits) -> None:
        self.app, self.authorizer, self.sessions = app, authorizer, sessions
        self.case_handlers, self.extensions = case_handlers, extensions
        self.json_body_limits = json_body_limits
        self.prefixes = PROTECTED_PREFIXES + tuple(prefix for _kind, prefix in extensions) + (CASE_CATALOG_PREFIX, CASE_PAGE_PATH, ADMIN_API_PREFIX)

    async def __call__(self, scope, receive, send):
        from .workspace_case_authority import (WorkspaceCaseAuthorityError,
            issue_workspace_case_authority, workspace_case_authority_scope)
        from .case_assignment_api import CaseAssignmentError, assignment_http_status
        if scope.get("type") not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        path = _path_of(scope)
        if scope.get("method") in {"GET", "HEAD"} and path_targets_audit_download(path, (scope.get("query_string") or b"").decode("latin1")):
            await self._deny(scope, send, 403, "direct_download_denied")
            return
        if path in RETIRED_EXACT_PATHS:
            await self._deny(scope, send, 401, "legacy_route_retired")
            return
        if not any(_within_prefix(path, prefix) for prefix in self.prefixes):
            await self.app(scope, receive, send)
            return
        # WS/streaming have no qualified session/revocation adapter yet.
        if scope.get("type") == "websocket":
            await self._deny(scope, send, 401, "transport_unqualified")
            return
        if path in AUTH_PATHS:
            inbound = receive
            try:
                if not path.endswith("/auth/login"):
                    await self.sessions.bind_http(_credential_request(scope), allow_anonymous=False)
                if scope.get("method") not in {"GET", "HEAD", "OPTIONS"}:
                    _body, inbound = await _read_json_body(scope, receive, self.json_body_limits, login=path.endswith("/auth/login"))
            except BrowserSessionError as exc:
                status, code = browser_session_http_status(exc)
                await self._deny(scope, send, status, code)
                return
            except _BodyAdmissionError as exc:
                await self._deny(scope, send, exc.status, exc.code)
                return
            await self.app(scope, inbound, send)
            return
        if _is_case_catalog_path(path):
            await self._catalog(scope, receive, send)
            return
        if _is_admin_api_path(path):
            await self._admin(scope, receive, send)
            return
        if not isinstance(self.authorizer, CaseActionAuthorizer):
            await self._deny(scope, send, 401, "authorizer_required")
            return
        body, inbound = b"", receive
        try:
            # Verify the received cookie/CSRF before awaiting or buffering even
            # one private request-body message.
            bound = await self.sessions.bind_http(_credential_request(scope), allow_anonymous=False)
            if path == "/api/claim-support/upload-document":
                raise _BodyAdmissionError(415, "upload_transport_unqualified")
            if scope.get("method") not in {"GET", "HEAD", "OPTIONS"}:
                body, inbound = await _read_json_body(scope, receive, self.json_body_limits)
            # A session may expire or be revoked while an admitted body arrives.
            bound = await self.sessions.bind_http(_credential_request(scope), allow_anonymous=False)
            _check_actor_claims(scope, body, bound.principal_id)
            material = _material_from_scope(scope, body)
            action = _required_action(path, str(scope.get("method") or ""), material, self.extensions)
            if "action" in material and material["action"] != action:
                raise CaseAccessError("action_mismatch")
            material["actor_principal_id"], material["action"] = bound.principal_id, action
            decision = self.authorizer.authorize_request(boundary_for_path(path), material)
            _enforce_live_participant_grant(scope, bound.principal_id, material, action)
            handlers = None
            workspace_authority = None
            if decision.permits_case_content:
                if self.case_handlers is None:
                    raise CaseAccessError("case_handler_unavailable")
                self.case_handlers.resolve(decision)
                handlers = lambda: self.case_handlers.resolve(decision)
                workspace_authority = issue_workspace_case_authority(authorizer=self.authorizer,
                    sessions=self.sessions, token=str(_credential_request(scope).cookies.get(SESSION_COOKIE) or ""),
                    decision=decision, registry=self.case_handlers,
                    case_consent=getattr(scope["app"].state, "case_consent", None),
                    inference_transport=getattr(scope["app"].state, "gui_inference_transport", None))
        except BrowserSessionError as exc:
            status, code = browser_session_http_status(exc)
            await self._deny(scope, send, status, code)
            return
        except _BodyAdmissionError as exc:
            await self._deny(scope, send, exc.status, exc.code)
            return
        except CaseAccessError as exc:
            await self._deny(scope, send, _status_for_denial(exc.code), exc.code)
            return
        except CaseAssignmentError as exc:
            await self._deny(scope, send, assignment_http_status(exc.code), exc.code)
            return
        except WorkspaceCaseAuthorityError:
            await self._deny(scope, send, 403, "workspace_case_authorization_denied")
            return
        forwarded = dict(scope)
        state = dict(scope.get("state") or {})
        state.update(case_authorization=decision, browser_principal=bound)
        forwarded["state"] = state
        token = _BOUND_HANDLERS.set(handlers)
        try:
            with workspace_case_authority_scope(workspace_authority):
                await self.app(forwarded, inbound, _inquiry_conflict_send(path, send))
        finally:
            _BOUND_HANDLERS.reset(token)

    async def _catalog(self, scope, receive, send):
        """Authenticate the actor. Case identity is checked by the catalog, not a global mediator."""

        from .case_access import PRIVILEGE_BODY_FIELDS

        path = _path_of(scope)
        body, inbound = b"", receive
        try:
            if path != CASE_PAGE_PATH:
                await self.sessions.bind_http(_credential_request(scope), allow_anonymous=False)
            if path != CASE_PAGE_PATH and scope.get("method") not in {"GET", "HEAD", "OPTIONS"}:
                body, inbound = await _read_json_body(scope, receive, self.json_body_limits)
            bound = None
            if path != CASE_PAGE_PATH:
                bound = await self.sessions.bind_http(_credential_request(scope), allow_anonymous=False)
                _check_actor_claims(scope, body, bound.principal_id)
                material = _material_from_scope(scope, body)
                if material.get("trusted_local") is True or material.get("trust") == "trusted_local" or "trusted_local" in material:
                    raise CaseAccessError("trusted_local_not_production")
                if path == AUDIT_EXPORT_PATH and any(name in material for name in ("role", "roles", "staff_role", "is_admin", "is_staff", "is_lawyer")):
                    raise CaseAccessError("forged_role")
                if any(name in material for name in PRIVILEGE_BODY_FIELDS):
                    raise CaseAccessError("request_cannot_mint_authority")
            else:
                material = {}
        except BrowserSessionError as exc:
            status, code = browser_session_http_status(exc)
            await self._deny(scope, send, status, code)
            return
        except _BodyAdmissionError as exc:
            await self._deny(scope, send, exc.status, exc.code)
            return
        except CaseAccessError as exc:
            await self._deny(scope, send, _status_for_denial(exc.code), exc.code)
            return
        forwarded = dict(scope)
        state = dict(scope.get("state") or {})
        if bound is not None:
            state["browser_principal"] = bound
        state["case_catalog_material"] = material
        forwarded["state"] = state
        await self.app(forwarded, inbound, send)

    async def _admin(self, scope, receive, send):
        """Authenticate the actor. Account authority is re-read from the roster.

        Admin routes do not authorize a case and do not open case handlers.
        A disabled or demoted principal fails on the next request because the
        directory drops the live session and the roster no longer matches it.
        """

        from .case_access import PRIVILEGE_BODY_FIELDS

        path = _path_of(scope)
        body, inbound = b"", receive
        try:
            await self.sessions.bind_http(_credential_request(scope), allow_anonymous=False)
            if scope.get("method") not in {"GET", "HEAD", "OPTIONS"}:
                body, inbound = await _read_json_body(scope, receive, self.json_body_limits)
            bound = await self.sessions.bind_http(_credential_request(scope), allow_anonymous=False)
            _check_actor_claims(scope, body, bound.principal_id)
            material = _material_from_scope(scope, body)
            if material.get("trusted_local") is True or material.get("trust") == "trusted_local" or "trusted_local" in material:
                raise CaseAccessError("trusted_local_not_production")
            if path == ADMIN_AUDIT_EXPORT_PATH and any(name in material for name in ("role", "roles", "staff_role", "is_admin", "is_staff", "is_lawyer")):
                raise CaseAccessError("forged_role")
            if any(name in material for name in PRIVILEGE_BODY_FIELDS):
                raise CaseAccessError("request_cannot_mint_authority")
        except BrowserSessionError as exc:
            status, code = browser_session_http_status(exc)
            await self._deny(scope, send, status, code)
            return
        except _BodyAdmissionError as exc:
            await self._deny(scope, send, exc.status, exc.code)
            return
        except CaseAccessError as exc:
            await self._deny(scope, send, _status_for_denial(exc.code), exc.code)
            return
        forwarded = dict(scope)
        state = dict(scope.get("state") or {})
        state["browser_principal"] = bound
        state["admin_material"] = material
        forwarded["state"] = state
        await self.app(forwarded, inbound, send)

    async def _deny(self, scope, send, status, code):
        if scope.get("type") == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            await _send_json(send, status, {"error": code})
