from __future__ import annotations

import json
import sys
from typing import Any, Dict

from .complaint_workspace import ComplaintWorkspaceService


def _write(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def main() -> None:
    service = ComplaintWorkspaceService()
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _write({"error": f"Invalid JSON: {exc}"})
            continue

        method = request.get("method")
        params = request.get("params") or {}
        request_id = request.get("id")

        try:
            if method == "initialize":
                result = {
                    "server": "complaint-workspace-mcp",
                    "version": "1.0.0",
                    "capabilities": {"tools": True},
                }
            elif method == "tools/list":
                result = service.list_mcp_tools()
            elif method == "tools/call":
                result = service.call_mcp_tool(
                    str(params.get("name") or ""),
                    params.get("arguments") or {},
                )
            else:
                raise ValueError(f"Unsupported method: {method}")
            _write({"id": request_id, "result": result})
        except Exception as exc:
            _write({"id": request_id, "error": str(exc)})


if __name__ == "__main__":
    main()
