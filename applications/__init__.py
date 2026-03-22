from .cli import CLI
from .complaint_cli import main as complaint_cli_main
from .complaint_mcp_protocol import handle_jsonrpc_message, tool_list_payload
from .complaint_mcp_server import main as complaint_mcp_server_main
from .complaint_workspace import ComplaintWorkspaceService
from .complaint_workspace_api import attach_complaint_workspace_routes, create_complaint_workspace_router
from .launcher import (
	canonicalize_application_type,
	create_uvicorn_app_for_type,
	launch_application,
	normalize_application_types,
	_run_adversarial_autopatch_app,
	start_configured_applications,
)
from .review_api import create_review_api_app
from .review_ui import create_review_dashboard_app, create_review_surface_app
from .server import SERVER
