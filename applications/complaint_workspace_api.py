from __future__ import annotations

import functools
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionError,
    BrowserSessionService,
    browser_session_http_status,
)
from .case_routes import INQUIRY_CONFLICT_STATUS, shared_inquiry_conflict
from .complaint_mcp_protocol import (handle_jsonrpc_message, project_shared_inquiry_contract,
    tool_list_payload, gui_inference_tool_failed)
from .complaint_workspace import (
    ComplaintWorkspaceService,
    PrincipalRegistry,
    WorkspaceAccess,
    WorkspaceAuthorizationDenied,
    WorkspacePersistenceError,
    access_from_http_headers,
    generate_decentralized_id,
    workspace_access_scope,
)
from .fastapi_compat import attach_router_routes

try:
    import python_multipart  # type: ignore  # noqa: F401

    _MULTIPART_AVAILABLE = True
except Exception:
    _MULTIPART_AVAILABLE = False


_DOCKET_CALENDAR_DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|[A-Z][a-z]+ \d{1,2}, \d{4}|\d{4}-\d{2}-\d{2})\b"
)


def _parse_calendar_date(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _extract_case_calendar_from_docket_view(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    documents = list((payload or {}).get("documents") or [])
    events: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for document in documents:
        if not isinstance(document, dict):
            continue
        title = str(document.get("title") or "").strip()
        text = str(document.get("text") or "").strip()
        metadata = dict(document.get("metadata") or {})
        combined_text = " ".join(
            part for part in [title, text, json.dumps(metadata, sort_keys=True, default=str)] if part
        ).lower()
        if not combined_text:
            continue

        event_kind = ""
        if "hearing" in combined_text:
            event_kind = "hearing"
        elif any(keyword in combined_text for keyword in ("deadline", "must respond", "response due", "due date", " due ")):
            event_kind = "deadline"
        elif any(keyword in combined_text for keyword in ("conference", "trial", "oral argument", "status conference", "calendar call")):
            event_kind = "calendar_event"
        if not event_kind:
            continue

        matched_dates = [
            match.strip()
            for match in _DOCKET_CALENDAR_DATE_PATTERN.findall(" ".join(part for part in [title, text] if part))
            if str(match).strip()
        ]
        explicit_date = str(
            metadata.get("event_date")
            or metadata.get("scheduled_date")
            or metadata.get("hearing_date")
            or document.get("date_filed")
            or ""
        ).strip()
        date_value = matched_dates[0] if matched_dates else explicit_date
        normalized_date = _parse_calendar_date(date_value)
        dedupe_key = (
            event_kind,
            title or event_kind,
            date_value,
            str(document.get("id") or ""),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        events.append(
            {
                "kind": event_kind,
                "title": title or {
                    "hearing": "Hearing event",
                    "deadline": "Deadline event",
                    "calendar_event": "Court calendar event",
                }.get(event_kind, "Calendar event"),
                "date": date_value,
                "normalized_date": normalized_date.isoformat() if normalized_date else None,
                "source_document_id": document.get("id"),
                "source_document_title": title,
                "document_number": document.get("document_number"),
                "source": "complaint_workspace_docket_view",
            }
        )

    events.sort(
        key=lambda item: (
            0 if item.get("normalized_date") else 1,
            str(item.get("normalized_date") or ""),
            str(item.get("title") or ""),
        )
    )
    return events


def _attach_case_calendar(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized_payload = dict(payload or {})
    case_calendar = _extract_case_calendar_from_docket_view(normalized_payload)
    normalized_payload["case_calendar"] = case_calendar
    normalized_payload["case_calendar_summary"] = {
        "count": len(case_calendar),
        "next_event": case_calendar[0] if case_calendar else None,
    }
    return normalized_payload


class IntakeRequest(BaseModel):
    user_id: Optional[str] = None
    answers: Dict[str, Any] = Field(default_factory=dict)


class GuiInferenceRequest(BaseModel):
    model_config = {"extra": "forbid"}
    purpose: str
    inputs: Dict[str, Any]
    timeout_seconds: float = Field(default=30.0, gt=0, le=60)


class GuiInferenceAdmissionRequest(BaseModel):
    model_config = {"extra": "forbid"}
    invocation_id: str


class IntakeChatTurnRequest(BaseModel):
    user_id: Optional[str] = None
    message: Optional[str] = None
    question_id: Optional[str] = None
    expected_question_revision: Optional[int] = Field(default=None, ge=0)
    interview_action: Optional[str] = None
    expected_graph_revision: Optional[str] = Field(default=None, strict=True)
    expected_session_revision: Optional[int] = Field(default=None, ge=0, strict=True)


class EvidenceRequest(BaseModel):
    user_id: Optional[str] = None
    kind: str = "testimony"
    claim_element_id: str
    title: str
    content: str
    source: Optional[str] = None
    attachment_names: List[str] = Field(default_factory=list)


class DocumentAnnotationTagRequest(BaseModel):
    user_id: Optional[str] = None
    document_id: str
    tags: List[str] = Field(default_factory=list)
    note: str
    claim_element_id: str = "causation"
    title: str = "Dataset document annotation"
    dataset_kind: str = "dataset"
    document_title: Optional[str] = None
    document_text_preview: Optional[str] = None
    document_metadata: Dict[str, Any] = Field(default_factory=dict)
    user_metadata: Dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None


class WorkspaceDatasetAnnotationRequest(BaseModel):
    user_id: Optional[str] = None
    document_id: str
    tags: List[str] = Field(default_factory=list)
    note: str
    claim_element_id: str = "causation"
    title: str = "Workspace dataset document annotation"
    document_title: Optional[str] = None
    document_text_preview: Optional[str] = None
    collection_id: Optional[str] = None
    document_type: Optional[str] = None
    claim_type: Optional[str] = None
    source_type: Optional[str] = None
    document_metadata: Dict[str, Any] = Field(default_factory=dict)
    user_metadata: Dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None


class GmailEvidenceImportRequest(BaseModel):
    user_id: Optional[str] = None
    addresses: List[str] = Field(default_factory=list)
    collect_all_messages: bool = False
    claim_element_id: str = "causation"
    folder: str = "INBOX"
    folders: List[str] = Field(default_factory=list)
    limit: Optional[int] = None
    date_after: Optional[str] = None
    date_before: Optional[str] = None
    years_back: Optional[int] = None
    evidence_root: Optional[str] = None
    gmail_user: Optional[str] = None
    gmail_app_password: Optional[str] = None
    use_gmail_oauth: bool = False
    gmail_oauth_client_secrets: Optional[str] = None
    gmail_oauth_token_cache: Optional[str] = None
    gmail_oauth_open_browser: bool = True
    complaint_query: Optional[str] = None
    complaint_keywords: List[str] = Field(default_factory=list)
    min_relevance_score: float = 0.0
    use_uid_checkpoint: bool = False
    checkpoint_name: Optional[str] = None
    uid_window_size: Optional[int] = None


class GmailDuckdbPipelineRequest(BaseModel):
    user_id: Optional[str] = None
    addresses: List[str] = Field(default_factory=list)
    collect_all_messages: bool = False
    claim_element_id: str = "causation"
    folder: str = "INBOX"
    folders: List[str] = Field(default_factory=list)
    years_back: Optional[int] = 2
    date_after: Optional[str] = None
    date_before: Optional[str] = None
    complaint_query: Optional[str] = None
    complaint_keywords: List[str] = Field(default_factory=list)
    min_relevance_score: float = 0.0
    evidence_root: Optional[str] = None
    gmail_user: Optional[str] = None
    gmail_app_password: Optional[str] = None
    use_gmail_oauth: bool = False
    gmail_oauth_client_secrets: Optional[str] = None
    gmail_oauth_token_cache: Optional[str] = None
    gmail_oauth_open_browser: bool = True
    checkpoint_name: str = "gmail-duckdb-pipeline"
    uid_window_size: int = 500
    duckdb_build_every_batches: int = 10
    max_batches: int = 20
    duckdb_output_dir: Optional[str] = None
    append_to_existing_corpus: bool = False
    bm25_search_query: Optional[str] = None
    bm25_search_limit: int = 20


class EmailDuckdbSearchRequest(BaseModel):
    index_path: str
    query: str
    limit: int = 20
    ranking: str = "bm25"
    bm25_k1: float = 1.2
    bm25_b: float = 0.75


class LocalEvidenceImportRequest(BaseModel):
    user_id: Optional[str] = None
    paths: List[str] = Field(default_factory=list)
    claim_element_id: str = "causation"
    kind: str = "document"
    evidence_root: Optional[str] = None


class GenerateRequest(BaseModel):
    user_id: Optional[str] = None
    requested_relief: List[str] = Field(default_factory=list)
    title_override: Optional[str] = None
    use_llm: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    config_path: Optional[str] = None
    backend_id: Optional[str] = None


class DraftUpdateRequest(BaseModel):
    user_id: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    requested_relief: Optional[List[str]] = None


class MikeHandoffRequest(BaseModel):
    user_id: Optional[str] = None
    mike_base_url: Optional[str] = None
    project_id: Optional[str] = None
    workspace_id: Optional[str] = None
    generate_draft_if_missing: bool = True
    grounding_mode: Optional[str] = None


class MikeDraftSyncRequest(BaseModel):
    user_id: Optional[str] = None
    body: str
    title: Optional[str] = None
    requested_relief: Optional[List[str]] = None
    handoff_id: Optional[str] = None
    project_id: Optional[str] = None
    workspace_id: Optional[str] = None
    mike_document_id: Optional[str] = None
    citation_links: List[Dict[str, Any]] = Field(default_factory=list)
    redline_summary: Optional[str] = None
    source_updated_at: Optional[str] = None
    structured_deltas: List[Dict[str, Any]] = Field(default_factory=list)
    editor_metadata: Dict[str, Any] = Field(default_factory=dict)
    grounding_mode: Optional[str] = None
    assertion_annotations: List[Dict[str, Any]] = Field(default_factory=list)
    authority_links: List[Dict[str, Any]] = Field(default_factory=list)
    sync_provenance: Dict[str, Any] = Field(default_factory=dict)


class SynopsisUpdateRequest(BaseModel):
    user_id: Optional[str] = None
    synopsis: str


class McpCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Any] = None
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)


class PackagedDocketRevalidationRequest(BaseModel):
    manifest_path: str
    top_k: int = 10
    min_priority: str = "low"
    queue_limit: Optional[int] = None
    execution_top_k: int = 10
    chain_until_satisfied: bool = True
    attach_refreshed_packets: bool = False


class PackagedDocketRevalidationPersistRequest(BaseModel):
    manifest_path: str
    output_dir: str
    package_name: Optional[str] = None
    include_car: bool = True
    top_k: int = 10
    min_priority: str = "low"
    queue_limit: Optional[int] = None
    execution_top_k: int = 10
    chain_until_satisfied: bool = True


def _browser_session_http_error(error: BrowserSessionError) -> HTTPException:
    status, code = browser_session_http_status(error)
    return HTTPException(status_code=status, detail=code)


def create_complaint_workspace_router(
    service: Optional[ComplaintWorkspaceService] = None,
    *,
    principal_registry: Optional[PrincipalRegistry] = None,
    trusted_local: bool = False,
    browser_sessions: Optional[BrowserSessionService] = None,
) -> APIRouter:
    """HTTP and MCP routes share one principal/case authorizer.

    ``trusted_local`` must be passed explicitly for a local operator binding.
    A process-wide bearer token or a caller-supplied ``user_id`` does not
    authorize a private read, write, or export.

    When ``browser_sessions`` is installed, including an unavailable service
    from a missing verifier or signing key, requests fail closed. That path
    does not fall back to trusted-local access.
    """

    router = APIRouter()
    workspace = service or ComplaintWorkspaceService()
    registry = principal_registry
    sessions = browser_sessions

    async def _bind_request_access(http_request: Request):
        if sessions is not None:
            anonymous = http_request.url.path.rstrip("/").endswith("/api/complaint-workspace/auth/login")
            try:
                bound = await sessions.bind_http(http_request, allow_anonymous=anonymous)
            except BrowserSessionError as error:
                raise _browser_session_http_error(error) from None
            if bound is None:
                access = WorkspaceAccess.unauthenticated()
            else:
                from .workspace_case_authority import (WorkspaceCaseAuthorityError,
                    current_workspace_case_authority)
                try:
                    authority = current_workspace_case_authority()
                    if authority is not None:
                        authority.revalidate(actor_principal_id=bound.principal_id)
                except WorkspaceCaseAuthorityError:
                    raise HTTPException(status_code=403, detail="authorization_denied") from None
                access = WorkspaceAccess.authenticated(bound.principal_id,
                    case_id=authority.case_id if authority is not None else None)
                http_request.state.browser_principal = bound
        else:
            access = access_from_http_headers(
                http_request.headers,
                principal_registry=registry,
                trusted_local=trusted_local,
            )
        with workspace_access_scope(access):
            yield

    def _register(method_registrar):
        def wrapper(path: str, *args: Any, **kwargs: Any):
            def decorator(fn):
                if path.endswith("/mcp/call") or path.endswith("/mcp/rpc") or path.endswith("/mcp/tools") or path.endswith("/identity"):
                    return method_registrar(path, *args, **kwargs)(fn)

                @functools.wraps(fn)
                async def guarded(*guard_args: Any, **guard_kwargs: Any):
                    try:
                        return await fn(*guard_args, **guard_kwargs)
                    except WorkspaceAuthorizationDenied:
                        raise HTTPException(status_code=403, detail="authorization_denied") from None
                    except HTTPException:
                        raise
                    except Exception:
                        raise HTTPException(status_code=500, detail="workspace_operation_failed") from None

                return method_registrar(path, *args, **kwargs)(guarded)

            return decorator

        return wrapper

    router.get = _register(router.get)  # type: ignore[method-assign]
    router.post = _register(router.post)  # type: ignore[method-assign]
    router.dependencies.append(Depends(_bind_request_access))

    def _json_payload(http_request: Request) -> Dict[str, Any]:
        payload = getattr(http_request.state, "browser_json", None)
        if not isinstance(payload, dict):
            raise HTTPException(status_code=401, detail="authentication_failed")
        return payload

    @router.post("/api/complaint-workspace/auth/login")
    async def login_browser_session(http_request: Request) -> JSONResponse:
        if sessions is None or not sessions.configured:
            raise HTTPException(status_code=503, detail="authentication_unavailable")
        try:
            issued = sessions.login(_json_payload(http_request))
        except BrowserSessionError as error:
            raise _browser_session_http_error(error) from None
        response = JSONResponse(issued.public_view())
        sessions.attach_session_cookie(response, issued)
        return response

    @router.post("/api/complaint-workspace/auth/logout")
    async def logout_browser_session(http_request: Request) -> JSONResponse:
        if sessions is None or not sessions.configured:
            raise HTTPException(status_code=503, detail="authentication_unavailable")
        token = str(http_request.cookies.get(SESSION_COOKIE) or "")
        try:
            sessions.logout(token, csrf_token=str(http_request.headers.get("x-csrf-token") or ""))
        except BrowserSessionError as error:
            raise _browser_session_http_error(error) from None
        response = JSONResponse({"authenticated": False})
        sessions.clear_session_cookie(response)
        return response

    @router.post("/api/complaint-workspace/auth/rotate")
    async def rotate_browser_session(http_request: Request) -> JSONResponse:
        if sessions is None or not sessions.configured:
            raise HTTPException(status_code=503, detail="authentication_unavailable")
        token = str(http_request.cookies.get(SESSION_COOKIE) or "")
        try:
            issued = sessions.rotate(token, csrf_token=str(http_request.headers.get("x-csrf-token") or ""))
        except BrowserSessionError as error:
            raise _browser_session_http_error(error) from None
        response = JSONResponse(issued.public_view())
        sessions.attach_session_cookie(response, issued)
        return response

    @router.get("/api/complaint-workspace/auth/session")
    async def read_browser_session(http_request: Request) -> JSONResponse:
        bound = getattr(http_request.state, "browser_principal", None)
        if bound is None:
            raise HTTPException(status_code=401, detail="session_required")
        try:
            resumed = sessions.resume_http(http_request, bound=bound)
        except BrowserSessionError as error:
            raise _browser_session_http_error(error) from None
        return JSONResponse(resumed, headers={"Cache-Control": "private, no-store",
            "Pragma": "no-cache", "Expires": "0"})

    @router.get("/api/complaint-workspace/factual-graph")
    async def read_current_factual_graph(
        user_id: Optional[str] = None,
        case_id: Optional[str] = None,
    ):
        """Current factual projection. Cached flags are not a second graph store."""
        try:
            return workspace.current_factual_graph_projection(user_id, case_id=case_id)
        except WorkspacePersistenceError as error:
            code = str(error.code or "")
            if code == "cross_case_id":
                status_code = 403
            elif code == "revision_conflict":
                status_code = 409
            else:
                status_code = 503
            public = code if code in {
                "unlock_needed", "key_unavailable", "revision_conflict", "cross_case_id",
                "knowledge_graph_unavailable", "data_graph_owner_unavailable", "factual_ledger_invalid",
            } else "private_session_unavailable"
            return JSONResponse(status_code=status_code, content={
                "status": "unavailable", "error": public, "read_only": True,
                "user_statements": [], "adopted_evidence": [], "corrections": [], "contradictions": [],
            })

    @router.get("/api/complaint-workspace/session")
    async def get_session(
        user_id: Optional[str] = None,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            return workspace.get_session(user_id, case_id=case_id)
        except WorkspacePersistenceError as error:
            # The real case/key owner supplies this error. Do not expose its
            # exception text, paths, ciphertext, or partial session payload.
            code = str(error.code or "")
            public = code if code in {"unlock_needed", "key_unavailable", "revision_conflict"} else "private_session_unavailable"
            return JSONResponse(status_code=409 if public == "revision_conflict" else 503,
                content={"status": "unavailable", "error": public, "session_readable": False})

    @router.post("/api/complaint-workspace/identity")
    async def create_identity() -> Dict[str, Any]:
        return generate_decentralized_id()

    @router.post("/api/complaint-workspace/intake")
    async def submit_intake(request: IntakeRequest) -> Dict[str, Any]:
        return workspace.submit_intake_answers(request.user_id, request.answers)

    @router.post("/api/complaint-workspace/intake-chat")
    async def intake_chat_turn(request: IntakeChatTurnRequest) -> Response:
        action = str(request.interview_action or "").strip().lower()
        if action in {"correct", "edit", "pause", "cancel", "cap", "unavailable", "saturate", "encrypted_resume"}:
            # Keep the actual event loop available for logout/revocation while
            # the guarded effect encrypts. Starlette preserves the issued scope.
            try:
                result = await run_in_threadpool(workspace.run_intake_chat_turn,
                    request.user_id, message=request.message, question_id=request.question_id,
                    expected_question_revision=request.expected_question_revision,
                    interview_action=request.interview_action,
                    expected_graph_revision=request.expected_graph_revision,
                    expected_session_revision=request.expected_session_revision)
            except WorkspacePersistenceError as error:
                if action not in {"pause", "cancel", "cap", "unavailable", "saturate"}:
                    raise
                code = error.code if error.code in {"revision_conflict", "unlock_needed", "durability_unproven",
                    "overwrite_blocked", "wal_unavailable"} else "finite_stop_unavailable"
                return JSONResponse(status_code=409 if code == "revision_conflict" else 503,
                    content={"status":"unavailable", "error":code, "outcome_unknown":True,
                        "legal_sufficiency":False, "worker_stalled":False})
        else:
            result = workspace.run_intake_chat_turn(request.user_id,
                message=request.message, question_id=request.question_id,
                expected_question_revision=request.expected_question_revision,
                interview_action=request.interview_action,
                expected_graph_revision=request.expected_graph_revision,
                expected_session_revision=request.expected_session_revision)
        payload = project_shared_inquiry_contract(result)
        if shared_inquiry_conflict(payload):
            return JSONResponse(status_code=INQUIRY_CONFLICT_STATUS, content=payload)
        return JSONResponse(status_code=200, content=payload)

    @router.post("/api/complaint-workspace/evidence")
    async def save_evidence(request: EvidenceRequest) -> Dict[str, Any]:
        return workspace.save_evidence(
            request.user_id,
            kind=request.kind,
            claim_element_id=request.claim_element_id,
            title=request.title,
            content=request.content,
            source=request.source,
            attachment_names=list(request.attachment_names or []),
        )

    @router.post("/api/complaint-workspace/document-annotations/tag")
    async def tag_document_annotation(request: DocumentAnnotationTagRequest) -> Dict[str, Any]:
        return workspace.tag_document_annotation(
            request.user_id,
            document_id=request.document_id,
            tags=list(request.tags or []),
            note=request.note,
            claim_element_id=request.claim_element_id,
            title=request.title,
            dataset_kind=request.dataset_kind,
            document_title=request.document_title,
            document_text_preview=request.document_text_preview,
            document_metadata=dict(request.document_metadata or {}),
            user_metadata=dict(request.user_metadata or {}),
            source=request.source,
        )

    @router.get("/api/complaint-workspace/document-annotations/graph")
    async def get_document_annotation_graph(user_id: Optional[str] = None) -> Dict[str, Any]:
        return workspace.get_document_annotation_graph(user_id)

    @router.post("/api/complaint-workspace/workspace-dataset/annotations/tag")
    async def tag_workspace_dataset_document(request: WorkspaceDatasetAnnotationRequest) -> Dict[str, Any]:
        return workspace.tag_workspace_dataset_document(
            request.user_id,
            document_id=request.document_id,
            tags=list(request.tags or []),
            note=request.note,
            claim_element_id=request.claim_element_id,
            title=request.title,
            document_title=request.document_title,
            document_text_preview=request.document_text_preview,
            collection_id=request.collection_id,
            document_type=request.document_type,
            claim_type=request.claim_type,
            source_type=request.source_type,
            document_metadata=dict(request.document_metadata or {}),
            user_metadata=dict(request.user_metadata or {}),
            source=request.source,
        )

    @router.get("/api/complaint-workspace/workspace-dataset/annotations")
    async def get_workspace_dataset_annotation_index(user_id: Optional[str] = None) -> Dict[str, Any]:
        return workspace.get_workspace_dataset_annotation_index(user_id)

    @router.post("/api/complaint-workspace/import-gmail-evidence")
    async def import_gmail_evidence_route(request: GmailEvidenceImportRequest) -> Dict[str, Any]:
        return workspace.import_gmail_evidence(
            request.user_id,
            addresses=list(request.addresses or []),
            collect_all_messages=bool(request.collect_all_messages),
            claim_element_id=request.claim_element_id,
            folder=request.folder,
            folders=list(request.folders or []),
            limit=request.limit,
            date_after=request.date_after,
            date_before=request.date_before,
            years_back=request.years_back,
            evidence_root=request.evidence_root,
            gmail_user=request.gmail_user,
            gmail_app_password=request.gmail_app_password,
            use_gmail_oauth=request.use_gmail_oauth,
            gmail_oauth_client_secrets=request.gmail_oauth_client_secrets,
            gmail_oauth_token_cache=request.gmail_oauth_token_cache,
            gmail_oauth_open_browser=request.gmail_oauth_open_browser,
            complaint_query=request.complaint_query,
            complaint_keywords=list(request.complaint_keywords or []),
            min_relevance_score=request.min_relevance_score,
            use_uid_checkpoint=request.use_uid_checkpoint,
            checkpoint_name=request.checkpoint_name,
            uid_window_size=request.uid_window_size,
        )

    @router.post("/api/complaint-workspace/import-local-evidence")
    async def import_local_evidence_route(request: LocalEvidenceImportRequest) -> Dict[str, Any]:
        return workspace.import_local_evidence(
            request.user_id,
            paths=list(request.paths or []),
            claim_element_id=request.claim_element_id,
            kind=request.kind,
            evidence_root=request.evidence_root,
        )

    if _MULTIPART_AVAILABLE:

        @router.post("/api/complaint-workspace/upload-local-evidence")
        async def upload_local_evidence_route(
            files: List[UploadFile] = File(...),
            user_id: Optional[str] = Form(default=None),
            claim_element_id: str = Form(default="causation"),
            kind: str = Form(default="document"),
            evidence_root: Optional[str] = Form(default=None),
            note: Optional[str] = Form(default=None),
            note_title: Optional[str] = Form(default=None),
            source: Optional[str] = Form(default="dashboard-chat-upload"),
        ) -> Dict[str, Any]:
            if not files:
                raise HTTPException(status_code=400, detail="At least one file is required.")
            return await workspace.upload_local_evidence_files(
                user_id,
                files=files,
                claim_element_id=claim_element_id,
                kind=kind,
                evidence_root=evidence_root,
                note=note,
                note_title=note_title,
                source=source,
            )
    else:

        @router.post("/api/complaint-workspace/upload-local-evidence")
        async def upload_local_evidence_unavailable(_: Request) -> Dict[str, Any]:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Local evidence upload requires the optional dependency 'python-multipart'. "
                    "Install it to enable browser file uploads."
                ),
            )

    @router.post("/api/complaint-workspace/run-gmail-duckdb-pipeline")
    async def run_gmail_duckdb_pipeline_route(request: GmailDuckdbPipelineRequest) -> Dict[str, Any]:
        return workspace.run_gmail_duckdb_pipeline(
            request.user_id,
            addresses=list(request.addresses or []),
            collect_all_messages=bool(request.collect_all_messages),
            claim_element_id=request.claim_element_id,
            folder=request.folder,
            folders=list(request.folders or []),
            years_back=request.years_back,
            date_after=request.date_after,
            date_before=request.date_before,
            complaint_query=request.complaint_query,
            complaint_keywords=list(request.complaint_keywords or []),
            min_relevance_score=request.min_relevance_score,
            evidence_root=request.evidence_root,
            gmail_user=request.gmail_user,
            gmail_app_password=request.gmail_app_password,
            use_gmail_oauth=request.use_gmail_oauth,
            gmail_oauth_client_secrets=request.gmail_oauth_client_secrets,
            gmail_oauth_token_cache=request.gmail_oauth_token_cache,
            gmail_oauth_open_browser=request.gmail_oauth_open_browser,
            checkpoint_name=request.checkpoint_name,
            uid_window_size=request.uid_window_size,
            duckdb_build_every_batches=request.duckdb_build_every_batches,
            max_batches=request.max_batches,
            duckdb_output_dir=request.duckdb_output_dir,
            append_to_existing_corpus=request.append_to_existing_corpus,
            bm25_search_query=request.bm25_search_query,
            bm25_search_limit=request.bm25_search_limit,
        )

    @router.post("/api/complaint-workspace/search-email-duckdb")
    async def search_email_duckdb_route(request: EmailDuckdbSearchRequest) -> Dict[str, Any]:
        return workspace.search_email_duckdb_corpus(
            index_path=request.index_path,
            query=request.query,
            limit=request.limit,
            ranking=request.ranking,
            bm25_k1=request.bm25_k1,
            bm25_b=request.bm25_b,
        )

    @router.post("/api/complaint-workspace/review")
    async def review_case(request: Dict[str, Any]) -> Dict[str, Any]:
        return workspace.call_mcp_tool("complaint.review_case", request)

    @router.post("/api/complaint-workspace/generate")
    async def generate_complaint(request: GenerateRequest) -> Dict[str, Any]:
        return workspace.generate_complaint(
            request.user_id,
            requested_relief=request.requested_relief or None,
            title_override=request.title_override,
            use_llm=request.use_llm,
            provider=request.provider,
            model=request.model,
            config_path=request.config_path,
            backend_id=request.backend_id,
        )

    @router.post("/api/complaint-workspace/update-draft")
    async def update_draft(request: DraftUpdateRequest) -> Dict[str, Any]:
        return workspace.update_draft(
            request.user_id,
            title=request.title,
            body=request.body,
            requested_relief=request.requested_relief,
        )

    @router.post("/api/complaint-workspace/mike/handoff")
    async def build_mike_handoff(request: MikeHandoffRequest) -> Dict[str, Any]:
        return workspace.build_mike_handoff(
            request.user_id,
            mike_base_url=request.mike_base_url,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            generate_draft_if_missing=request.generate_draft_if_missing,
            grounding_mode=request.grounding_mode,
        )

    @router.get("/api/complaint-workspace/mike/status")
    async def get_mike_integration_status(user_id: Optional[str] = None) -> Dict[str, Any]:
        return workspace.get_mike_integration_status(user_id)

    @router.post("/api/complaint-workspace/mike/sync")
    async def sync_mike_final_draft(request: MikeDraftSyncRequest) -> Dict[str, Any]:
        return workspace.sync_mike_final_draft(
            request.user_id,
            body=request.body,
            title=request.title,
            requested_relief=request.requested_relief,
            handoff_id=request.handoff_id,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            mike_document_id=request.mike_document_id,
            citation_links=request.citation_links,
            redline_summary=request.redline_summary,
            source_updated_at=request.source_updated_at,
            structured_deltas=request.structured_deltas,
            editor_metadata=request.editor_metadata,
            grounding_mode=request.grounding_mode,
            assertion_annotations=request.assertion_annotations,
            authority_links=request.authority_links,
            sync_provenance=request.sync_provenance,
        )

    @router.post("/api/complaint-workspace/update-synopsis")
    async def update_case_synopsis(request: SynopsisUpdateRequest) -> Dict[str, Any]:
        return workspace.update_case_synopsis(request.user_id, request.synopsis)

    @router.post("/api/complaint-workspace/reset")
    async def reset_session(request: Dict[str, Any]) -> Dict[str, Any]:
        return workspace.reset_session(request.get("user_id"))

    @router.get("/api/complaint-workspace/export/download")
    async def download_complaint_packet(
        user_id: Optional[str] = Query(default=None),
        case_id: Optional[str] = Query(default=None),
        output_format: str = Query(default="json"),
        cid: Optional[str] = Query(default=None),
        storage_key: Optional[str] = Query(default=None),
    ) -> Response:
        if case_id or cid or storage_key:
            workspace.resolve_private_reference(
                user_id,
                case_id=case_id,
                cid=cid,
                storage_key=storage_key,
            )
        artifact = workspace.build_export_artifact(user_id, output_format=output_format)
        return Response(
            content=artifact["body"],
            media_type=str(artifact["media_type"]),
            headers={"Content-Disposition": f'attachment; filename="{artifact["filename"]}"'},
        )

    @router.get("/api/complaint-workspace/contained-file")
    async def read_contained_file(
        relative_name: str,
        user_id: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        payload = workspace.read_contained_workspace_file(user_id, relative_name)
        return {
            "content_b64": __import__("base64").b64encode(payload).decode("ascii"),
            "at_rest_protection": "plaintext_pending",
        }

    @router.post("/api/complaint-workspace/contained-file")
    async def write_contained_file(request: Dict[str, Any]) -> Dict[str, Any]:
        content = request.get("content")
        if isinstance(content, str):
            raw = content.encode("utf-8")
        else:
            raw = bytes(content or b"")
        return workspace.write_contained_workspace_file(
            request.get("user_id"),
            str(request.get("relative_name") or ""),
            raw,
        )

    @router.get("/api/complaint-workspace/mcp/tools")
    async def list_mcp_tools() -> Dict[str, Any]:
        return tool_list_payload(workspace)

    @router.get("/api/complaint-workspace/packaged-docket/operator-dashboard")
    async def get_packaged_docket_operator_dashboard_route(manifest_path: str) -> Dict[str, Any]:
        return workspace.get_packaged_docket_operator_dashboard(manifest_path)

    @router.get("/api/complaint-workspace/packaged-docket/view")
    async def view_packaged_docket_route(
        manifest_path: str,
        include_document_text: bool = Query(default=False),
        document_limit: int = Query(default=25),
    ) -> Dict[str, Any]:
        return _attach_case_calendar(
            workspace.view_docket_dataset(
                manifest_path,
                input_type="packaged",
                include_document_text=include_document_text,
                document_limit=document_limit,
            )
        )

    @router.get("/api/complaint-workspace/packaged-docket/operator-dashboard-report")
    async def load_packaged_docket_operator_dashboard_report_route(
        manifest_path: str,
        report_format: str = Query(default="parsed"),
    ) -> Dict[str, Any]:
        return workspace.load_packaged_docket_operator_dashboard_report(
            manifest_path,
            report_format=report_format,
        )

    @router.get("/api/complaint-workspace/docket-dataset/view")
    async def view_docket_dataset_route(
        input_path: str,
        input_type: str = Query(default="single"),
        include_document_text: bool = Query(default=False),
        document_limit: int = Query(default=25),
    ) -> Dict[str, Any]:
        return _attach_case_calendar(
            workspace.view_docket_dataset(
                input_path,
                input_type=input_type,
                include_document_text=include_document_text,
                document_limit=document_limit,
            )
        )

    @router.get("/api/complaint-workspace/docket-dataset/search")
    async def search_docket_dataset_route(
        input_path: str,
        query: str,
        input_type: str = Query(default="single"),
        search_backend: str = Query(default="bm25"),
        top_k: int = Query(default=10),
        vector_dimension: int = Query(default=32),
    ) -> Dict[str, Any]:
        return workspace.search_docket_dataset(
            input_path,
            input_type=input_type,
            query=query,
            search_backend=search_backend,
            top_k=top_k,
            vector_dimension=vector_dimension,
        )

    @router.get("/api/complaint-workspace/docket-dataset/metadata")
    async def get_docket_dataset_metadata_route(
        input_path: str,
        input_type: str = Query(default="single"),
    ) -> Dict[str, Any]:
        return workspace.get_docket_dataset_metadata(input_path, input_type=input_type)

    @router.get("/api/complaint-workspace/docket-dataset/graph")
    async def get_docket_dataset_graph_route(
        input_path: str,
        input_type: str = Query(default="single"),
    ) -> Dict[str, Any]:
        return workspace.get_docket_dataset_graph(input_path, input_type=input_type)

    @router.get("/api/complaint-workspace/workspace-dataset/view")
    async def view_workspace_dataset_route(
        input_path: str,
        input_type: str = Query(default="single"),
        include_document_text: bool = Query(default=False),
        document_limit: int = Query(default=25),
        collection_id: Optional[str] = Query(default=None),
        document_type: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        claim_element_id: Optional[str] = Query(default=None),
        source_type: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        return workspace.view_workspace_dataset(
            input_path,
            input_type=input_type,
            include_document_text=include_document_text,
            document_limit=document_limit,
            collection_id=collection_id,
            document_type=document_type,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            source_type=source_type,
        )

    @router.get("/api/complaint-workspace/workspace-dataset/search")
    async def search_workspace_dataset_route(
        input_path: str,
        query: str,
        input_type: str = Query(default="single"),
        search_backend: str = Query(default="bm25"),
        top_k: int = Query(default=10),
        vector_dimension: int = Query(default=32),
        collection_id: Optional[str] = Query(default=None),
        document_type: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        claim_element_id: Optional[str] = Query(default=None),
        source_type: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        return workspace.search_workspace_dataset(
            input_path,
            input_type=input_type,
            query=query,
            search_backend=search_backend,
            top_k=top_k,
            vector_dimension=vector_dimension,
            collection_id=collection_id,
            document_type=document_type,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            source_type=source_type,
        )

    @router.get("/api/complaint-workspace/workspace-dataset/graph")
    async def get_workspace_dataset_graph_route(
        input_path: str,
        input_type: str = Query(default="single"),
        entity_query: str = Query(default=""),
        relationship_type: str = Query(default=""),
        document_id: str = Query(default=""),
        modality: str = Query(default=""),
        limit: int = Query(default=50),
    ) -> Dict[str, Any]:
        return workspace.get_workspace_dataset_graph(
            input_path,
            input_type=input_type,
            entity_query=entity_query,
            relationship_type=relationship_type,
            document_id=document_id,
            modality=modality,
            limit=limit,
        )

    @router.post("/api/complaint-workspace/packaged-docket/revalidation/execute")
    async def execute_packaged_docket_revalidation_route(
        request: PackagedDocketRevalidationRequest,
    ) -> Dict[str, Any]:
        return workspace.execute_packaged_docket_proof_revalidation_queue(
            request.manifest_path,
            top_k=request.top_k,
            min_priority=request.min_priority,
            queue_limit=request.queue_limit,
            execution_top_k=request.execution_top_k,
            chain_until_satisfied=request.chain_until_satisfied,
            attach_refreshed_packets=request.attach_refreshed_packets,
        )

    @router.post("/api/complaint-workspace/packaged-docket/revalidation/persist")
    async def persist_packaged_docket_revalidation_route(
        request: PackagedDocketRevalidationPersistRequest,
    ) -> Dict[str, Any]:
        return workspace.persist_packaged_docket_proof_revalidation_queue(
            request.manifest_path,
            request.output_dir,
            package_name=request.package_name,
            include_car=request.include_car,
            top_k=request.top_k,
            min_priority=request.min_priority,
            queue_limit=request.queue_limit,
            execution_top_k=request.execution_top_k,
            chain_until_satisfied=request.chain_until_satisfied,
        )

    @router.post("/api/complaint-workspace/inference/dispatch")
    async def dispatch_gui_inference(request: GuiInferenceRequest) -> Dict[str, Any]:
        return await run_in_threadpool(workspace.dispatch_bounded_gui_inference, None, purpose=request.purpose,
            inputs=request.inputs, timeout_seconds=request.timeout_seconds)

    @router.post("/api/complaint-workspace/inference/admit")
    async def admit_gui_inference(request: GuiInferenceAdmissionRequest) -> Dict[str, Any]:
        return await run_in_threadpool(workspace.admit_bounded_gui_inference, None, invocation_id=request.invocation_id)

    @router.post("/api/complaint-workspace/mcp/call")
    async def call_mcp_tool(request: McpCallRequest) -> Response:
        try:
            threaded_intake = request.tool_name == "complaint.run_intake_chat_turn" and str(
                request.arguments.get("interview_action") or "").strip().lower() in {"correct", "edit", "pause", "cancel", "cap", "unavailable", "saturate", "encrypted_resume"}
            if threaded_intake or request.tool_name in {"complaint.dispatch_bounded_gui_inference", "complaint.admit_bounded_gui_inference"}:
                payload = await run_in_threadpool(workspace.call_mcp_tool, request.tool_name, request.arguments)
            else:
                payload = workspace.call_mcp_tool(request.tool_name, request.arguments)
        except WorkspaceAuthorizationDenied:
            return JSONResponse(status_code=200, content={"ok": False, "error": "authorization_denied", "isError": True})
        except Exception:
            return JSONResponse(status_code=200, content={"ok": False, "error": "workspace_operation_failed", "isError": True})
        if gui_inference_tool_failed(request.tool_name, payload):
            return JSONResponse(status_code=200, content={**payload, "ok": False, "isError": True})
        if request.tool_name == "complaint.run_intake_chat_turn":
            payload = project_shared_inquiry_contract(payload)
            if shared_inquiry_conflict(payload):
                payload = dict(payload)
                payload["isError"] = True
                payload["ok"] = False
                return JSONResponse(status_code=INQUIRY_CONFLICT_STATUS, content=payload)
        return JSONResponse(status_code=200, content=payload)

    @router.post("/api/complaint-workspace/mcp/rpc")
    async def call_jsonrpc(request: JsonRpcRequest, http_request: Request) -> Response:
        token = os.environ.get("COMPLAINT_MCP_AUTH_TOKEN", "").strip()
        if token:
            authorization = http_request.headers.get("authorization", "")
            if authorization != f"Bearer {token}":
                raise HTTPException(status_code=401, detail="MCP bearer token required")
        params = request.params if isinstance(request.params, dict) else {}
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        threaded_intake = params.get("name") == "complaint.run_intake_chat_turn" and str(
            arguments.get("interview_action") or "").strip().lower() in {"correct", "edit", "pause", "cancel", "cap", "unavailable", "saturate", "encrypted_resume"}
        if request.method == "tools/call" and (threaded_intake or params.get("name") in {
                "complaint.dispatch_bounded_gui_inference", "complaint.admit_bounded_gui_inference"}):
            response = await run_in_threadpool(handle_jsonrpc_message, workspace, request.model_dump())
        else:
            response = handle_jsonrpc_message(workspace, request.model_dump())
        body = response or {"jsonrpc": "2.0", "id": request.id, "result": None}
        return Response(
            content=json.dumps(body),
            media_type="application/json",
        )

    return router


def attach_complaint_workspace_routes(
    app: FastAPI,
    service: Optional[ComplaintWorkspaceService] = None,
    *,
    principal_registry: Optional[PrincipalRegistry] = None,
    trusted_local: bool = False,
    browser_sessions: Optional[BrowserSessionService] = None,
) -> FastAPI:
    return attach_router_routes(
        app,
        create_complaint_workspace_router(
            service,
            principal_registry=principal_registry,
            trusted_local=trusted_local,
            browser_sessions=browser_sessions,
        ),
    )
