from .cli import app as complaint_workspace_cli_app
from .cli import main as complaint_cli_main
from .cli import main as complaint_workspace_cli_main
from .entrypoints import main as complaint_generator_main, run_main
from .mcp import handle_jsonrpc_message, tool_list_payload
from .mcp_server import main as complaint_mcp_server_main
from .review import create_review_dashboard_app, create_review_surface_app
from .workspace import (
    ComplaintWorkspaceService,
    attach_complaint_workspace_routes,
    create_complaint_workspace_router,
)

__all__ = [
    "ComplaintWorkspaceService",
    "attach_complaint_workspace_routes",
    "complaint_cli_main",
    "complaint_generator_main",
    "complaint_mcp_server_main",
    "complaint_workspace_cli_app",
    "complaint_workspace_cli_main",
    "create_complaint_workspace_router",
    "create_review_dashboard_app",
    "create_review_surface_app",
    "handle_jsonrpc_message",
    "run_main",
    "tool_list_payload",
]

__version__ = "0.1.0"
