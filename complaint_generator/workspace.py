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


def get_client_release_gate(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_client_release_gate(user_id)


def get_workflow_capabilities(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_workflow_capabilities(user_id)


def get_tooling_contract(
    user_id: Optional[str] = None,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_tooling_contract(user_id)


def generate_complaint(
    user_id: Optional[str],
    *,
    requested_relief: Optional[list[str]] = None,
    title_override: Optional[str] = None,
    use_llm: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).generate_complaint(
        user_id,
        requested_relief=requested_relief,
        title_override=title_override,
        use_llm=use_llm,
        provider=provider,
        model=model,
        config_path=config_path,
        backend_id=backend_id,
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


def export_complaint_markdown(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).export_complaint_markdown(user_id)


def export_complaint_pdf(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).export_complaint_pdf(user_id)


def export_complaint_docx(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).export_complaint_docx(user_id)


def analyze_complaint_output(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).analyze_complaint_output(user_id)


def get_formal_diagnostics(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_formal_diagnostics(user_id)


def get_filing_provenance(
    user_id: Optional[str],
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_filing_provenance(user_id)


def get_provider_diagnostics(
    user_id: Optional[str] = None,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).get_provider_diagnostics(user_id)


def review_generated_exports(
    user_id: Optional[str] = None,
    *,
    artifact_path: Optional[str | Path] = None,
    artifact_dir: Optional[str | Path] = None,
    notes: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).review_generated_exports(
        user_id,
        artifact_path=str(artifact_path) if artifact_path is not None else None,
        artifact_dir=str(artifact_dir) if artifact_dir is not None else None,
        notes=notes,
        provider=provider,
        model=model,
        config_path=config_path,
        backend_id=backend_id,
    )


def update_claim_type(
    user_id: Optional[str],
    claim_type: str,
    *,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).update_claim_type(user_id, claim_type)


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


def review_ui(
    *,
    screenshot_paths: Optional[list[str]] = None,
    screenshot_dir: Optional[str | Path] = None,
    user_id: Optional[str] = None,
    notes: Optional[str] = None,
    goals: Optional[list[str]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    output_path: Optional[str | Path] = None,
    iterations: int = 0,
    pytest_target: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "user_id": user_id,
        "notes": notes,
        "goals": goals,
        "provider": provider,
        "model": model,
        "config_path": config_path,
        "backend_id": backend_id,
        "iterations": iterations,
        "pytest_target": pytest_target,
    }
    if screenshot_paths is not None:
        arguments["screenshot_paths"] = screenshot_paths
    if screenshot_dir is not None:
        arguments["screenshot_dir"] = str(screenshot_dir)
    if output_path is not None:
        arguments["output_path"] = str(output_path)
    return _resolve_service(service, root_dir=root_dir).call_mcp_tool("complaint.review_ui", arguments)


def optimize_ui(
    *,
    screenshot_dir: str | Path,
    user_id: Optional[str] = None,
    output_path: Optional[str | Path] = None,
    max_rounds: int = 2,
    iterations: int = 1,
    notes: Optional[str] = None,
    goals: Optional[list[str]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    method: Optional[str] = None,
    priority: Optional[int] = None,
    pytest_target: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "screenshot_dir": str(screenshot_dir),
        "user_id": user_id,
        "max_rounds": max_rounds,
        "iterations": iterations,
        "notes": notes,
        "goals": goals,
        "provider": provider,
        "model": model,
        "method": method,
        "priority": priority,
        "pytest_target": pytest_target,
    }
    if output_path is not None:
        arguments["output_path"] = str(output_path)
    return _resolve_service(service, root_dir=root_dir).call_mcp_tool("complaint.optimize_ui", arguments)


def run_browser_audit(
    *,
    screenshot_dir: str | Path,
    pytest_target: Optional[str] = None,
    service: Optional[ComplaintWorkspaceService] = None,
    root_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    return _resolve_service(service, root_dir=root_dir).call_mcp_tool(
        "complaint.run_browser_audit",
        {
            "screenshot_dir": str(screenshot_dir),
            "pytest_target": pytest_target,
        },
    )

__all__ = [
    "ComplaintWorkspaceService",
    "DEFAULT_CLAIM_ELEMENTS",
    "DEFAULT_INTAKE_QUESTIONS",
    "attach_complaint_workspace_routes",
    "build_mediator_prompt",
    "get_complaint_readiness",
    "get_ui_readiness",
    "get_client_release_gate",
    "create_identity",
    "create_complaint_workspace_router",
    "export_complaint_packet",
    "export_complaint_markdown",
    "export_complaint_pdf",
    "export_complaint_docx",
    "analyze_complaint_output",
    "get_formal_diagnostics",
    "get_filing_provenance",
    "get_provider_diagnostics",
    "review_generated_exports",
    "update_claim_type",
    "generate_decentralized_id",
    "generate_complaint",
    "get_workflow_capabilities",
    "list_claim_elements",
    "list_intake_questions",
    "list_mcp_tools",
    "optimize_ui",
    "reset_session",
    "review_ui",
    "review_case",
    "run_browser_audit",
    "run_closed_loop_ui_ux_improvement",
    "run_end_to_end_complaint_browser_audit",
    "run_iterative_ui_ux_workflow",
    "save_evidence",
    "start_session",
    "submit_intake_answers",
    "update_case_synopsis",
    "update_draft",
]
