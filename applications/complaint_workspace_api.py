from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field

from .complaint_workspace import ComplaintWorkspaceService


class IntakeRequest(BaseModel):
    user_id: Optional[str] = None
    answers: Dict[str, Any] = Field(default_factory=dict)


class EvidenceRequest(BaseModel):
    user_id: Optional[str] = None
    kind: str = "testimony"
    claim_element_id: str
    title: str
    content: str
    source: Optional[str] = None


class GenerateRequest(BaseModel):
    user_id: Optional[str] = None
    requested_relief: List[str] = Field(default_factory=list)
    title_override: Optional[str] = None


class DraftUpdateRequest(BaseModel):
    user_id: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    requested_relief: Optional[List[str]] = None


class McpCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


def create_complaint_workspace_router(service: Optional[ComplaintWorkspaceService] = None) -> APIRouter:
    router = APIRouter()
    workspace = service or ComplaintWorkspaceService()

    @router.get("/api/complaint-workspace/session")
    async def get_session(user_id: Optional[str] = None) -> Dict[str, Any]:
        return workspace.get_session(user_id)

    @router.post("/api/complaint-workspace/intake")
    async def submit_intake(request: IntakeRequest) -> Dict[str, Any]:
        return workspace.submit_intake_answers(request.user_id, request.answers)

    @router.post("/api/complaint-workspace/evidence")
    async def save_evidence(request: EvidenceRequest) -> Dict[str, Any]:
        return workspace.save_evidence(
            request.user_id,
            kind=request.kind,
            claim_element_id=request.claim_element_id,
            title=request.title,
            content=request.content,
            source=request.source,
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
        )

    @router.post("/api/complaint-workspace/update-draft")
    async def update_draft(request: DraftUpdateRequest) -> Dict[str, Any]:
        return workspace.update_draft(
            request.user_id,
            title=request.title,
            body=request.body,
            requested_relief=request.requested_relief,
        )

    @router.post("/api/complaint-workspace/reset")
    async def reset_session(request: Dict[str, Any]) -> Dict[str, Any]:
        return workspace.reset_session(request.get("user_id"))

    @router.get("/api/complaint-workspace/mcp/tools")
    async def list_mcp_tools() -> Dict[str, Any]:
        return workspace.list_mcp_tools()

    @router.post("/api/complaint-workspace/mcp/call")
    async def call_mcp_tool(request: McpCallRequest) -> Dict[str, Any]:
        return workspace.call_mcp_tool(request.tool_name, request.arguments)

    return router


def attach_complaint_workspace_routes(
    app: FastAPI,
    service: Optional[ComplaintWorkspaceService] = None,
) -> FastAPI:
    app.include_router(create_complaint_workspace_router(service))
    return app

