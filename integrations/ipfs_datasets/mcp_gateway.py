from __future__ import annotations

from typing import Any, Dict, Optional

from .loader import import_module_optional


_mcp_server_module, _mcp_server_error = import_module_optional("ipfs_datasets_py.mcp_server")

MCP_GATEWAY_AVAILABLE = _mcp_server_module is not None
MCP_GATEWAY_ERROR = _mcp_server_error


def list_gateway_tools() -> Dict[str, Any]:
    return {
        "status": "not_implemented" if MCP_GATEWAY_AVAILABLE else "unavailable",
        "tools": [],
    }


def execute_gateway_tool(
    tool_name: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "status": "not_implemented" if MCP_GATEWAY_AVAILABLE else "unavailable",
        "tool_name": tool_name,
        "payload": payload or {},
        "result": None,
    }


__all__ = [
    "MCP_GATEWAY_AVAILABLE",
    "MCP_GATEWAY_ERROR",
    "list_gateway_tools",
    "execute_gateway_tool",
]