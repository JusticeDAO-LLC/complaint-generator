from __future__ import annotations

from typing import Any, Dict, Optional

from .loader import import_module_optional
from .types import with_adapter_metadata

from applications.complaint_workspace import ComplaintWorkspaceService


_mcp_server_module, _mcp_server_error = import_module_optional("ipfs_datasets_py.mcp_server")
_complaint_workspace = ComplaintWorkspaceService()

MCP_GATEWAY_AVAILABLE = _mcp_server_module is not None
MCP_GATEWAY_ERROR = _mcp_server_error


def list_gateway_tools() -> Dict[str, Any]:
    return with_adapter_metadata(
        {
            "status": "available",
            "tools": _complaint_workspace.list_mcp_tools().get("tools", []),
        },
        operation="list_gateway_tools",
        backend_available=True,
        degraded_reason=MCP_GATEWAY_ERROR if not MCP_GATEWAY_AVAILABLE else None,
        implementation_status="available",
    )


def execute_gateway_tool(
    tool_name: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    result = _complaint_workspace.call_mcp_tool(tool_name, payload or {})
    return with_adapter_metadata(
        {
            "status": "available",
            "tool_name": tool_name,
            "payload": payload or {},
            "result": result,
        },
        operation="execute_gateway_tool",
        backend_available=True,
        degraded_reason=MCP_GATEWAY_ERROR if not MCP_GATEWAY_AVAILABLE else None,
        implementation_status="available",
    )


__all__ = [
    "MCP_GATEWAY_AVAILABLE",
    "MCP_GATEWAY_ERROR",
    "list_gateway_tools",
    "execute_gateway_tool",
]
