from __future__ import annotations

import json
import sys
from typing import Any, Dict

from .complaint_mcp_protocol import handle_jsonrpc_message
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
            _write({
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error",
                    "data": str(exc),
                },
            })
            continue
        response = handle_jsonrpc_message(service, request)
        if response is not None:
            _write(response)
        if isinstance(request, dict) and request.get("method") == "exit":
            break


if __name__ == "__main__":
    main()
