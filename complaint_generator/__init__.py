from .apps import (
    attach_complaint_workspace_routes,
    create_complaint_workspace_router,
    create_review_dashboard_app,
    create_review_surface_app,
)
from .mcp import handle_jsonrpc_message, tool_list_payload
from .ui_ux_workflow import (
    build_ui_ux_review_prompt,
    collect_screenshot_artifacts,
    review_screenshot_audit_with_llm_router,
    run_end_to_end_complaint_browser_audit,
    run_closed_loop_ui_ux_improvement,
    run_iterative_ui_ux_workflow,
    run_playwright_screenshot_audit,
)
from .workspace import (
    ComplaintWorkspaceService,
    DEFAULT_CLAIM_ELEMENTS,
    DEFAULT_INTAKE_QUESTIONS,
    build_mediator_prompt,
    get_complaint_readiness,
    get_ui_readiness,
    get_client_release_gate,
    create_identity,
    export_complaint_packet,
    export_complaint_markdown,
    export_complaint_pdf,
    export_complaint_docx,
    analyze_complaint_output,
    get_formal_diagnostics,
    review_generated_exports,
    update_claim_type,
    generate_decentralized_id,
    generate_complaint,
    get_workflow_capabilities,
    list_claim_elements,
    list_intake_questions,
    list_mcp_tools,
    optimize_ui,
    reset_session,
    review_ui,
    review_case,
    run_browser_audit,
    save_evidence,
    start_session,
    submit_intake_answers,
    update_case_synopsis,
    update_draft,
)
from applications.ui_review import create_ui_review_report, run_ui_review_workflow

__all__ = [
    "ComplaintWorkspaceService",
    "DEFAULT_CLAIM_ELEMENTS",
    "DEFAULT_INTAKE_QUESTIONS",
    "attach_complaint_workspace_routes",
    "build_mediator_prompt",
    "get_complaint_readiness",
    "get_ui_readiness",
    "get_client_release_gate",
    "build_ui_ux_review_prompt",
    "collect_screenshot_artifacts",
    "complaint_cli_main",
    "complaint_generator_main",
    "complaint_mcp_server_main",
    "complaint_workspace_cli_app",
    "complaint_workspace_cli_main",
    "create_identity",
    "create_complaint_workspace_router",
    "create_review_dashboard_app",
    "create_review_surface_app",
    "create_ui_review_report",
    "analyze_complaint_output",
    "get_formal_diagnostics",
    "review_generated_exports",
    "run_main",
    "export_complaint_packet",
    "export_complaint_markdown",
    "export_complaint_pdf",
    "export_complaint_docx",
    "generate_decentralized_id",
    "generate_complaint",
    "get_workflow_capabilities",
    "handle_jsonrpc_message",
    "import_gmail_evidence",
    "list_claim_elements",
    "list_intake_questions",
    "list_mcp_tools",
    "optimize_ui",
    "reset_session",
    "review_screenshot_audit_with_llm_router",
    "review_ui",
    "review_case",
    "run_browser_audit",
    "run_end_to_end_complaint_browser_audit",
    "run_closed_loop_ui_ux_improvement",
    "run_iterative_ui_ux_workflow",
    "run_playwright_screenshot_audit",
    "run_ui_review_workflow",
    "save_evidence",
    "start_session",
    "submit_intake_answers",
    "tool_list_payload",
    "update_claim_type",
    "update_case_synopsis",
    "update_draft",
]

__version__ = "0.1.0"

_LAZY_EXPORTS = {
    "complaint_workspace_cli_app": (".cli", "app"),
    "complaint_cli_main": (".cli", "main"),
    "complaint_workspace_cli_main": (".cli", "main"),
    "complaint_mcp_server_main": (".mcp_server", "main"),
    "complaint_generator_main": (".entrypoints", "main"),
    "import_gmail_evidence": (".email_import", "import_gmail_evidence"),
    "run_main": (".entrypoints", "run_main"),
}


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    module = __import__(f"{__name__}{module_name}", fromlist=[attribute_name])
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
