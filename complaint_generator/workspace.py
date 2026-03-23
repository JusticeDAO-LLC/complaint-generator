from pathlib import Path
from typing import Any, Optional

from applications.complaint_workspace import (
    ComplaintWorkspaceService,
    DEFAULT_CLAIM_ELEMENTS,
    DEFAULT_INTAKE_QUESTIONS,
    generate_decentralized_id,
)
from applications.complaint_workspace_api import (
    attach_complaint_workspace_routes,
    create_complaint_workspace_router,
)
from complaint_generator.ui_ux_workflow import (
    run_closed_loop_ui_ux_improvement,
    run_end_to_end_complaint_browser_audit,
    run_iterative_ui_ux_workflow,
)


def _resolve_service(
    service: Optional[ComplaintWorkspaceService] = None,
    *,
    root_dir: Optional[str | Path] = None,
) -> ComplaintWorkspaceService:
    if service is not None:
        return service
    if root_dir is not None:
        return ComplaintWorkspaceService(root_dir=Path(root_dir))
    return ComplaintWorkspaceService()


def create_identity(
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).call_mcp_tool("complaint.create_identity", {})


def list_intake_questions(
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).list_intake_questions()


def list_claim_elements(
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).list_claim_elements()


def start_session(
    user_id: Optional[str] = None,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_session(user_id)


def submit_intake_answers(
    user_id: Optional[str],
    answers: dict[str, Any],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).submit_intake_answers(user_id, answers)


def save_evidence(
    user_id: Optional[str],
    *,
    kind: str,
    claim_element_id: str,
    title: str,
    content: str,
    source: Optional[str] = None,
    attachment_names: Optional[list[str]] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).save_evidence(
        user_id,
        kind=kind,
        claim_element_id=claim_element_id,
        title=title,
        content=content,
        source=source,
        attachment_names=attachment_names,
    )


def review_case(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).call_mcp_tool("complaint.review_case", {"user_id": user_id})


def build_mediator_prompt(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).build_mediator_prompt(user_id)


def get_complaint_readiness(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_complaint_readiness(user_id)


def get_ui_readiness(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_ui_readiness(user_id)


def get_workflow_capabilities(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_workflow_capabilities(user_id)


def generate_complaint(
    user_id: Optional[str],
    *,
    requested_relief: Optional[list[str]] = None,
    title_override: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).generate_complaint(
        user_id,
        requested_relief=requested_relief,
        title_override=title_override,
    )


def update_draft(
    user_id: Optional[str],
    *,
    title: Optional[str] = None,
    body: Optional[str] = None,
    requested_relief: Optional[list[str]] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).update_draft(
        user_id,
        title=title,
        body=body,
        requested_relief=requested_relief,
    )


def export_complaint_packet(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).export_complaint_packet(user_id)


def update_case_synopsis(
    user_id: Optional[str],
    synopsis: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).update_case_synopsis(user_id, synopsis)


def reset_session(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).reset_session(user_id)


def list_mcp_tools(
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).list_mcp_tools()

__all__ = [
    "ComplaintWorkspaceService",
    "DEFAULT_CLAIM_ELEMENTS",
    "DEFAULT_INTAKE_QUESTIONS",
    "attach_complaint_workspace_routes",
    "build_mediator_prompt",
    "get_complaint_readiness",
    "get_ui_readiness",
    "create_identity",
    "create_complaint_workspace_router",
    "export_complaint_packet",
    "generate_decentralized_id",
    "generate_complaint",
    "get_workflow_capabilities",
    "list_claim_elements",
    "list_intake_questions",
    "list_mcp_tools",
    "reset_session",
    "review_case",
    "run_closed_loop_ui_ux_improvement",
    "run_end_to_end_complaint_browser_audit",
    "run_iterative_ui_ux_workflow",
    "save_evidence",
    "start_session",
    "submit_intake_answers",
    "update_case_synopsis",
    "update_draft",
]
