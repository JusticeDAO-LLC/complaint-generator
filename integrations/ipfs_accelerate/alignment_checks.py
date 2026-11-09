"""Local file checks for alignment plan tasks.

Each check reads source in this repository. None of them import a model,
start an IPFS daemon, or contact Mike.
"""

from __future__ import annotations

from pathlib import Path


CheckResult = tuple[bool, str]

_CONTROL_PLANE_TOKENS = ("SupervisorControlService", "OperationRequest")
_JOB_NAMES = ("evidence_acquisition", "draft_repair", "graph_refresh")


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(relative)
    return path.read_text(encoding="utf-8")


def _require(text: str, *needles: str) -> str:
    missing = [needle for needle in needles if needle not in text]
    return ", ".join(missing)


def check_mike_protocol_versions(root: Path) -> CheckResult:
    text = _read(root, "applications/complaint_mcp_protocol.py")
    missing = _require(
        text,
        "2024-11-05",
        "2025-03-26",
        "2025-06-18",
        "def negotiated_protocol_version",
    )
    if missing:
        return False, "protocol handshake missing " + missing
    return True, "protocol versions negotiated"


def check_mike_connector_tools(root: Path) -> CheckResult:
    text = _read(root, "applications/complaint_workspace.py")
    missing = _require(
        text,
        "complaint.generate_grounded_text",
        "complaint.search_corpus",
        "complaint.get_handoff",
        "complaint.sync_draft",
    )
    if missing:
        return False, "connector tools missing " + missing
    return True, "four connector tools"


def check_mike_http_route_gate(root: Path) -> CheckResult:
    text = _read(root, "applications/complaint_workspace_api.py")
    missing = _require(
        text,
        "/api/complaint-workspace/mcp/rpc",
        "COMPLAINT_MCP_AUTH_TOKEN",
        "application/json",
        "status_code=401",
    )
    forbidden = [name for name in (*_JOB_NAMES, "run_alignment_watchdog") if name in text]
    if missing or forbidden:
        return False, "route missing " + missing + " forbidden " + ",".join(forbidden)
    return True, "stateless json-rpc route"


def check_mike_compatibility_stamp(root: Path) -> CheckResult:
    text = _read(root, "integrations/mike/llm_patch.py")
    missing = _require(
        text,
        'MIKE_LLM_PATCH_VERSION = "mike-llm-router-patch-v1"',
        '"compatibility_only": True',
        '"transport": "mcp_connector"',
    )
    if missing:
        return False, "compatibility stamp missing " + missing
    return True, "compatibility stamp"


def check_mike_registration_text(root: Path) -> CheckResult:
    text = _read(root, "applications/complaint_workspace.py")
    missing = _require(
        text,
        "Streamable HTTP",
        "public https",
        "/api/complaint-workspace/mcp/rpc",
        "compatibility-only",
        "COMPLAINT_MCP_AUTH_TOKEN",
    )
    if missing:
        return False, "registration text missing " + missing
    return True, "registration text"


def check_multimedia_attachment_adapter(root: Path) -> CheckResult:
    text = _read(root, "integrations/ipfs_datasets/multimedia.py")
    missing = _require(
        text,
        "def extract_attachment_text",
        "ipfs_datasets_py.processors.multimedia.attachment_text_extractor",
    )
    if missing:
        return False, "multimedia adapter missing " + missing
    return True, "multimedia adapter"


def check_graph_client_persist(root: Path) -> CheckResult:
    text = _read(root, "integrations/ipfs_datasets/graphs.py")
    missing = _require(text, "knowledge_graphs.Client", "def persist_graph_snapshot", "graph_persist_path")
    if missing or "client.query" in text:
        return False, "graph client missing " + missing
    return True, "graph client persist"


def check_legal_symbol_loader(root: Path) -> CheckResult:
    text = _read(root, "integrations/ipfs_datasets/legal_data.py")
    if "def load_legal_symbol" not in text:
        return False, "load_legal_symbol missing"
    return True, "legal symbol loader"


def check_operator_scripts_use_adapter(root: Path) -> CheckResult:
    scripts = root / "scripts"
    offenders = sorted(
        path.name
        for path in scripts.glob("*.py")
        if "ipfs_datasets_py.processors.legal_data" in path.read_text(encoding="utf-8")
    )
    if offenders:
        return False, "direct legal imports in " + ", ".join(offenders)
    return True, "operator scripts use the legal adapter"


def check_logic_adapter_paths(root: Path) -> CheckResult:
    logic = _read(root, "integrations/ipfs_datasets/logic.py")
    theorem = _read(root, "integrations/ipfs_datasets/theorem_export.py")
    missing = _require(logic, "logic.fol", "logic.deontic")
    if missing or "logic.tools" in logic or "verification_api" in theorem:
        return False, "logic paths missing " + missing
    return True, "logic adapter paths"


def check_kit_gate_default_off(root: Path) -> CheckResult:
    text = _read(root, "integrations/ipfs_datasets/storage.py")
    start = text.find("def _kit_enabled")
    end = text.find("\ndef ", start + 1) if start >= 0 else -1
    if start < 0 or end < 0:
        return False, "kit gate missing"
    chunk = text[start:end]
    missing = _require(chunk, "COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", '""', '"1"', '"true"', '"yes"', '"on"')
    if missing:
        return False, "kit gate missing " + missing
    return True, "kit gate defaults off"


def check_storage_fallback_order(root: Path) -> CheckResult:
    text = _read(root, "integrations/ipfs_datasets/storage.py")
    if "IPFSSimpleAPI" not in text:
        return False, "IPFSSimpleAPI missing"
    start = text.find("def store_bytes")
    end = text.find("\ndef retrieve_bytes", start)
    body = text[start:end]
    kit = body.find("_load_optional_kit_backend")
    router = body.find("add_bytes")
    cache = body.find("_local_cache_store")
    if not (0 <= kit < router < cache):
        return False, "storage fallback order changed"
    return True, "storage fallback order"


def check_llm_router_facade(root: Path) -> CheckResult:
    text = _read(root, "integrations/ipfs_accelerate/routers.py")
    missing = _require(text, "def load_llm_symbols", "ipfs_accelerate_py.llm_router")
    table = text.split("_ACCELERATE_PROVIDER_ALIASES", 1)[-1].split("def accelerate_provider_name", 1)[0]
    if missing or "p2p" in table:
        return False, "llm router facade missing " + missing
    return True, "llm router facade"


def check_embedding_router_facade(root: Path) -> CheckResult:
    text = _read(root, "integrations/ipfs_accelerate/routers.py")
    missing = _require(text, "def load_embedding_symbols", "ipfs_accelerate_py.embeddings_router")
    if missing:
        return False, "embedding router facade missing " + missing
    return True, "embedding router facade"


def check_multimodal_router_facade(root: Path) -> CheckResult:
    text = _read(root, "integrations/ipfs_accelerate/routers.py")
    missing = _require(text, "def load_multimodal_symbols", "ipfs_accelerate_py.multimodal_router")
    if missing:
        return False, "multimodal router facade missing " + missing
    return True, "multimodal router facade"


def check_supervisor_jobs_off_request_path(root: Path) -> CheckResult:
    supervisor = _read(root, "integrations/ipfs_accelerate/supervisor.py")
    route = _read(root, "applications/complaint_workspace_api.py")
    missing = _require(
        supervisor,
        "def evidence_acquisition",
        "def draft_repair",
        "def graph_refresh",
        '"off_request_path": True',
    )
    leaked = [name for name in _JOB_NAMES if name in route]
    if missing or leaked:
        return False, "supervisor jobs missing " + missing + " leaked " + ",".join(leaked)
    return True, "supervisor jobs stay off the request path"


def _control_plane_hits(text: str) -> list[str]:
    return [token for token in _CONTROL_PLANE_TOKENS if token in text]


def check_supervisor_cli_has_three_operations(root: Path) -> CheckResult:
    text = _read(root, "scripts/run_complaint_supervisor_job.py")
    missing = _require(text, *_JOB_NAMES)
    hits = _control_plane_hits(text)
    if missing or hits or "complaint_workspace_api" in text:
        return False, "supervisor cli missing " + missing + " hits " + ",".join(hits)
    return True, "supervisor cli"


def check_watchdog_repairs_board(root: Path) -> CheckResult:
    text = _read(root, "integrations/ipfs_accelerate/watchdog.py")
    missing = _require(text, "def repair_execution_board", "def run_watchdog")
    hits = _control_plane_hits(text)
    if missing or hits:
        return False, "watchdog missing " + missing + " hits " + ",".join(hits)
    return True, "watchdog repairs the board"


def check_watchdog_cli_off_control_plane(root: Path) -> CheckResult:
    cli = _read(root, "scripts/run_alignment_watchdog.py")
    route = _read(root, "applications/complaint_workspace_api.py")
    hits = _control_plane_hits(cli)
    if hits or "complaint_workspace_api" in cli or "run_alignment_watchdog" in route:
        return False, "watchdog cli hits " + ",".join(hits)
    return True, "watchdog cli stays off the control plane"


CHECKERS = {
    "task.mike_protocol_versions": check_mike_protocol_versions,
    "task.mike_connector_tools": check_mike_connector_tools,
    "task.mike_http_route_gate": check_mike_http_route_gate,
    "task.mike_compatibility_stamp": check_mike_compatibility_stamp,
    "task.mike_registration_text": check_mike_registration_text,
    "task.multimedia_attachment_adapter": check_multimedia_attachment_adapter,
    "task.graph_client_persist": check_graph_client_persist,
    "task.legal_symbol_loader": check_legal_symbol_loader,
    "task.operator_scripts_use_adapter": check_operator_scripts_use_adapter,
    "task.logic_adapter_paths": check_logic_adapter_paths,
    "task.kit_gate_default_off": check_kit_gate_default_off,
    "task.storage_fallback_order": check_storage_fallback_order,
    "task.llm_router_facade": check_llm_router_facade,
    "task.embedding_router_facade": check_embedding_router_facade,
    "task.multimodal_router_facade": check_multimodal_router_facade,
    "task.supervisor_jobs_off_request_path": check_supervisor_jobs_off_request_path,
    "task.supervisor_cli_has_three_operations": check_supervisor_cli_has_three_operations,
    "task.watchdog_repairs_board": check_watchdog_repairs_board,
    "task.watchdog_cli_off_control_plane": check_watchdog_cli_off_control_plane,
}
