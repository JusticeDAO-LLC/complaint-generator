from importlib import import_module

_LAZY_EXPORTS = {
    "CLI": (".cli", "CLI"),
    "ComplaintWorkspaceService": (".complaint_workspace", "ComplaintWorkspaceService"),
    "SERVER": (".server", "SERVER"),
    "_run_adversarial_autopatch_app": (".launcher", "_run_adversarial_autopatch_app"),
    "attach_complaint_workspace_routes": (".complaint_workspace_api", "attach_complaint_workspace_routes"),
    "canonicalize_application_type": (".launcher", "canonicalize_application_type"),
    "complaint_cli_main": (".complaint_cli", "main"),
    "complaint_mcp_server_main": (".complaint_mcp_server", "main"),
    "create_complaint_workspace_router": (".complaint_workspace_api", "create_complaint_workspace_router"),
    "create_review_api_app": (".review_api", "create_review_api_app"),
    "create_review_dashboard_app": (".review_ui", "create_review_dashboard_app"),
    "create_review_surface_app": (".review_ui", "create_review_surface_app"),
    "create_uvicorn_app_for_type": (".launcher", "create_uvicorn_app_for_type"),
    "handle_jsonrpc_message": (".complaint_mcp_protocol", "handle_jsonrpc_message"),
    "launch_application": (".launcher", "launch_application"),
    "normalize_application_types": (".launcher", "normalize_application_types"),
    "start_configured_applications": (".launcher", "start_configured_applications"),
    "tool_list_payload": (".complaint_mcp_protocol", "tool_list_payload"),
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    return getattr(module, attribute_name)
