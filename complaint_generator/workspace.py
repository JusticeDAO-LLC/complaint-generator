from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import (
    attach_complaint_workspace_routes,
    create_complaint_workspace_router,
)

__all__ = [
    "ComplaintWorkspaceService",
    "attach_complaint_workspace_routes",
    "create_complaint_workspace_router",
]
