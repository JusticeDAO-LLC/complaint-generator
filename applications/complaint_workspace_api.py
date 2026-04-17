from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .complaint_mcp_protocol import handle_jsonrpc_message, tool_list_payload
from .complaint_workspace import ComplaintWorkspaceService, generate_decentralized_id

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


class IntakeChatTurnRequest(BaseModel):
    user_id: Optional[str] = None
    message: Optional[str] = None
    question_id: Optional[str] = None


class EvidenceRequest(BaseModel):
    user_id: Optional[str] = None
    kind: str = "testimony"
    claim_element_id: str
    title: str
    content: str
    source: Optional[str] = None
    attachment_names: List[str] = Field(default_factory=list)


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


def create_complaint_workspace_router(service: Optional[ComplaintWorkspaceService] = None) -> APIRouter:
    router = APIRouter()
    workspace = service or ComplaintWorkspaceService()

    @router.get("/api/complaint-workspace/session")
    async def get_session(user_id: Optional[str] = None) -> Dict[str, Any]:
        return workspace.get_session(user_id)

    @router.post("/api/complaint-workspace/identity")
    async def create_identity() -> Dict[str, Any]:
        return generate_decentralized_id()

    @router.post("/api/complaint-workspace/intake")
    async def submit_intake(request: IntakeRequest) -> Dict[str, Any]:
        return workspace.submit_intake_answers(request.user_id, request.answers)

    @router.post("/api/complaint-workspace/intake-chat")
    async def intake_chat_turn(request: IntakeChatTurnRequest) -> Dict[str, Any]:
        return workspace.run_intake_chat_turn(
            request.user_id,
            message=request.message,
            question_id=request.question_id,
        )

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

            with tempfile.TemporaryDirectory(prefix="complaint-workspace-upload-") as temp_dir:
                temp_root = Path(temp_dir)
                temp_paths: List[str] = []
                uploaded_files: List[Dict[str, Any]] = []
                for index, file in enumerate(files, start=1):
                    original_name = Path(str(file.filename or f"upload-{index}")).name or f"upload-{index}"
                    destination = temp_root / f"{index:04d}_{original_name}"
                    file_bytes = await file.read()
                    destination.write_bytes(file_bytes)
                    temp_paths.append(str(destination))
                    uploaded_files.append(
                        {
                            "filename": original_name,
                            "content_type": str(file.content_type or "application/octet-stream"),
                            "size": len(file_bytes),
                            "temporary_path": str(destination),
                        }
                    )

                payload = workspace.import_local_evidence(
                    user_id,
                    paths=temp_paths,
                    claim_element_id=claim_element_id,
                    kind=kind,
                    evidence_root=evidence_root,
                )

                note_record = None
                normalized_note = str(note or "").strip()
                if normalized_note:
                    uploaded_names = [item["filename"] for item in uploaded_files if item.get("filename")]
                    effective_claim_element_id = claim_element_id
                    if claim_element_id in {"auto", "suggested"}:
                        first_import = next(iter(payload.get("imported") or []), {})
                        effective_claim_element_id = str(
                            first_import.get("effective_claim_element_id")
                            or first_import.get("suggested_claim_element_id")
                            or "causation"
                        ).strip() or "causation"
                    note_record = workspace.save_evidence(
                        user_id,
                        kind="testimony",
                        claim_element_id=effective_claim_element_id,
                        title=str(note_title or "Chat upload note").strip() or "Chat upload note",
                        content=normalized_note,
                        source=str(source or "dashboard-chat-upload").strip() or "dashboard-chat-upload",
                        attachment_names=uploaded_names,
                    )
                    payload["note_record"] = note_record.get("saved")
                    payload["session"] = note_record.get("session")
                    payload["review"] = note_record.get("review")
                    payload["case_synopsis"] = note_record.get("case_synopsis")

                payload["uploaded_files"] = uploaded_files
                payload["upload_source"] = str(source or "dashboard-chat-upload").strip() or "dashboard-chat-upload"
                return payload
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

    @router.post("/api/complaint-workspace/update-synopsis")
    async def update_case_synopsis(request: SynopsisUpdateRequest) -> Dict[str, Any]:
        return workspace.update_case_synopsis(request.user_id, request.synopsis)

    @router.post("/api/complaint-workspace/reset")
    async def reset_session(request: Dict[str, Any]) -> Dict[str, Any]:
        return workspace.reset_session(request.get("user_id"))

    @router.get("/api/complaint-workspace/export/download")
    async def download_complaint_packet(
        user_id: Optional[str] = Query(default=None),
        output_format: str = Query(default="json"),
    ) -> Response:
        artifact = workspace.build_export_artifact(user_id, output_format=output_format)
        return Response(
            content=artifact["body"],
            media_type=str(artifact["media_type"]),
            headers={"Content-Disposition": f'attachment; filename="{artifact["filename"]}"'},
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

    @router.post("/api/complaint-workspace/mcp/call")
    async def call_mcp_tool(request: McpCallRequest) -> Dict[str, Any]:
        return workspace.call_mcp_tool(request.tool_name, request.arguments)

    @router.post("/api/complaint-workspace/mcp/rpc")
    async def call_jsonrpc(request: JsonRpcRequest) -> Dict[str, Any]:
        response = handle_jsonrpc_message(workspace, request.model_dump())
        return response or {"jsonrpc": "2.0", "id": request.id, "result": None}

    return router


def attach_complaint_workspace_routes(
    app: FastAPI,
    service: Optional[ComplaintWorkspaceService] = None,
) -> FastAPI:
    app.include_router(create_complaint_workspace_router(service))
    return app
