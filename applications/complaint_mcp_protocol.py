from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .complaint_workspace import ComplaintWorkspaceService


JSONRPC_VERSION = "2.0"

_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "complaint.create_identity": {
        "type": "object",
        "properties": {},
    },
    "complaint.list_intake_questions": {
        "type": "object",
        "properties": {},
    },
    "complaint.list_claim_elements": {
        "type": "object",
        "properties": {},
    },
    "complaint.start_session": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.submit_intake": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "answers": {"type": "object"},
        },
        "required": ["answers"],
    },
    "complaint.save_evidence": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "kind": {"type": "string", "enum": ["testimony", "document"]},
            "claim_element_id": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "source": {"type": "string"},
            "attachment_names": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["kind", "claim_element_id", "title", "content"],
    },
    "complaint.review_case": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.build_mediator_prompt": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.get_workflow_capabilities": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.generate_complaint": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "requested_relief": {
                "type": "array",
                "items": {"type": "string"},
            },
            "title_override": {"type": "string"},
        },
    },
    "complaint.update_draft": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "requested_relief": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
    "complaint.export_complaint_packet": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.update_case_synopsis": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "synopsis": {"type": "string"},
        },
        "required": ["synopsis"],
    },
    "complaint.reset_session": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.review_ui": {
        "type": "object",
        "properties": {
            "screenshot_paths": {
                "type": "array",
                "items": {"type": "string"},
            },
            "screenshot_dir": {"type": "string"},
            "notes": {"type": "string"},
            "goals": {
                "type": "array",
                "items": {"type": "string"},
            },
            "provider": {"type": "string"},
            "model": {"type": "string"},
            "config_path": {"type": "string"},
            "backend_id": {"type": "string"},
            "output_path": {"type": "string"},
            "iterations": {"type": "integer"},
            "pytest_target": {"type": "string"},
        },
    },
    "complaint.optimize_ui": {
        "type": "object",
        "properties": {
            "screenshot_dir": {"type": "string"},
            "output_path": {"type": "string"},
            "notes": {"type": "string"},
            "goals": {
                "type": "array",
                "items": {"type": "string"},
            },
            "provider": {"type": "string"},
            "model": {"type": "string"},
            "iterations": {"type": "integer"},
            "max_rounds": {"type": "integer"},
            "method": {"type": "string"},
            "priority": {"type": "integer"},
            "pytest_target": {"type": "string"},
        },
        "required": ["screenshot_dir"],
    },
    "complaint.run_browser_audit": {
        "type": "object",
        "properties": {
            "screenshot_dir": {"type": "string"},
            "pytest_target": {"type": "string"},
        },
        "required": ["screenshot_dir"],
    },
}


def tool_list_payload(service: ComplaintWorkspaceService) -> Dict[str, Any]:
    return {
        "tools": [
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": _TOOL_SCHEMAS.get(tool["name"], {"type": "object"}),
            }
            for tool in service.list_mcp_tools().get("tools", [])
        ]
    }


def _success(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload


def handle_jsonrpc_message(
    service: ComplaintWorkspaceService,
    request: Any,
) -> Optional[Dict[str, Any]]:
    if not isinstance(request, dict):
        return _error(None, -32600, "Invalid Request", "JSON-RPC payload must be an object.")

    request_id = request.get("id")
    if request.get("jsonrpc") != JSONRPC_VERSION:
        return _error(request_id, -32600, "Invalid Request", "Expected jsonrpc='2.0'.")

    method = request.get("method")
    if not isinstance(method, str) or not method.strip():
        return _error(request_id, -32600, "Invalid Request", "Missing method.")

    params = request.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _error(request_id, -32602, "Invalid params", "Params must be an object.")

    is_notification = request_id is None

    if method == "notifications/initialized":
        return None if is_notification else _success(request_id, None)

    if method == "exit":
        return None

    if method == "ping":
        return None if is_notification else _success(request_id, {"ok": True})

    if method == "initialize":
        return _success(
            request_id,
            {
                "protocolVersion": "2026-03-22",
                "serverInfo": {
                    "name": "complaint-workspace-mcp",
                    "version": "1.0.0",
                },
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "instructions": "Use tools/list and tools/call to drive the complaint workspace workflow.",
            },
        )

    if method == "shutdown":
        return None if is_notification else _success(request_id, None)

    if method == "tools/list":
        return _success(request_id, tool_list_payload(service))

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(tool_name, str) or not tool_name.strip():
            return _error(request_id, -32602, "Invalid params", "tools/call requires params.name.")
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "Invalid params", "tools/call arguments must be an object.")
        try:
            structured = service.call_mcp_tool(tool_name, arguments)
            return _success(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(structured, sort_keys=True),
                        }
                    ],
                    "structuredContent": structured,
                    "isError": False,
                },
            )
        except Exception as exc:
            return _success(
                request_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )

    return _error(request_id, -32601, "Method not found", method)
