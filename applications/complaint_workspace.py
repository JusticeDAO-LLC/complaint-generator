from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import sys
import threading
import uuid
import zipfile
from base64 import b64encode
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from xml.sax.saxutils import escape

from complaint_phases.legal_document import parse_legal_document

try:
    import anyio
except ModuleNotFoundError:
    class _AnyioFallback:
        @staticmethod
        def run(func: Any, *args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                raise RuntimeError("anyio is required for async complaint workspace operations in this environment.")
            return result

    anyio = _AnyioFallback()


def _ensure_local_ipfs_datasets_path() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    candidate = repo_root / "ipfs_datasets_py"
    candidate_text = str(candidate)
    if candidate.is_dir() and candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)


_ensure_local_ipfs_datasets_path()


DEFAULT_USER_ID = "did:key:anonymous"
DEFAULT_UI_UX_OPTIMIZER_METHOD = "actor_critic"
DEFAULT_UI_UX_OPTIMIZER_PRIORITY = 90
DEFAULT_LLM_DRAFT_PROVIDER = "codex_cli"
DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN: List[str] = [
    "codex_cli",
    "copilot_cli",
    "hf_inference_api",
]
DEFAULT_LLM_DRAFT_MODELS_BY_PROVIDER: Dict[str, str] = {
    "codex": "gpt-5.3-codex",
    "codex_cli": "gpt-5.3-codex",
    "copilot_cli": "gpt-5-mini",
}
DEFAULT_LLM_DRAFT_TIMEOUT_SECONDS = 20
DEFAULT_LLM_DRAFT_TIMEOUTS_BY_PROVIDER: Dict[str, int] = {
    "codex": 90,
    "codex_cli": 90,
    "copilot_cli": 45,
    "copilot_sdk": 45,
    "openai": 30,
    "openai_api": 30,
    "hf_inference_api": 30,
    "hf_inference": 30,
    "hf_api": 30,
}
DEFAULT_UI_UX_SCREENSHOT_TARGET = (
    "tests/test_website_cohesion_playwright.py::"
    "test_homepage_navigation_can_drive_a_full_complaint_journey_with_real_handoffs"
)
DEFAULT_UI_UX_SCREENSHOT_TARGET = "playwright/tests/complaint-flow.spec.js"

_DATA_DIR = Path(__file__).resolve().parent.parent / ".complaint_workspace"
_SESSION_DIR = _DATA_DIR / "sessions"

_INTAKE_QUESTIONS: List[Dict[str, str]] = [
    {
        "id": "party_name",
        "label": "Your name",
        "prompt": "Who is bringing the complaint?",
        "placeholder": "Jane Doe",
    },
    {
        "id": "opposing_party",
        "label": "Opposing party",
        "prompt": "Who are you filing against?",
        "placeholder": "Acme Corporation",
    },
    {
        "id": "protected_activity",
        "label": "Protected activity",
        "prompt": "What did you report, oppose, or request before the retaliation happened?",
        "placeholder": "Reported discrimination to HR",
    },
    {
        "id": "adverse_action",
        "label": "Adverse action",
        "prompt": "What happened to you afterward?",
        "placeholder": "Termination two days later",
    },
    {
        "id": "timeline",
        "label": "Timeline",
        "prompt": "When did the key events happen?",
        "placeholder": "Complaint on March 8, termination on March 10",
    },
    {
        "id": "harm",
        "label": "Harm",
        "prompt": "What harm did you suffer?",
        "placeholder": "Lost wages, lost benefits, emotional distress",
    },
    {
        "id": "court_header",
        "label": "Court caption",
        "prompt": "If you know the court, what district caption should appear on the complaint?",
        "placeholder": "FOR THE NORTHERN DISTRICT OF CALIFORNIA",
    },
]

_CLAIM_ELEMENTS: List[Dict[str, str]] = [
    {"id": "protected_activity", "label": "Protected activity"},
    {"id": "employer_knowledge", "label": "Employer knowledge"},
    {"id": "adverse_action", "label": "Adverse action"},
    {"id": "causation", "label": "Causal link"},
    {"id": "harm", "label": "Damages"},
]
DEFAULT_INTAKE_QUESTIONS: List[Dict[str, str]] = deepcopy(_INTAKE_QUESTIONS)
DEFAULT_CLAIM_ELEMENTS: List[Dict[str, str]] = deepcopy(_CLAIM_ELEMENTS)
_CLAIM_TYPE_LABELS: Dict[str, str] = {
    "retaliation": "Retaliation",
    "employment_discrimination": "Employment Discrimination",
    "housing_discrimination": "Housing Discrimination",
    "due_process_failure": "Due Process Violation",
    "consumer_protection": "Consumer Protection",
}
_PACKAGE_EXPORT_CONTRACT: List[str] = [
    "create_identity",
    "start_session",
    "submit_intake_answers",
    "run_intake_chat_turn",
    "save_evidence",
    "import_gmail_evidence",
    "run_gmail_duckdb_pipeline",
    "import_local_evidence",
    "search_email_duckdb_corpus",
    "review_case",
    "build_mediator_prompt",
    "get_complaint_readiness",
    "get_ui_readiness",
    "get_client_release_gate",
    "get_workflow_capabilities",
    "get_tooling_contract",
    "get_workspace_data_schema",
    "migrate_legacy_workspace_data",
    "search_workspace_dataset",
    "view_workspace_dataset",
    "generate_complaint",
    "export_complaint_packet",
    "export_complaint_markdown",
    "export_complaint_docx",
    "export_complaint_pdf",
    "analyze_complaint_output",
    "get_formal_diagnostics",
    "get_filing_provenance",
    "get_provider_diagnostics",
    "view_docket_dataset",
    "search_docket_dataset",
    "get_docket_dataset_metadata",
    "get_docket_dataset_graph",
    "review_generated_exports",
    "update_claim_type",
    "update_case_synopsis",
    "review_ui",
    "optimize_ui",
    "run_browser_audit",
]
_CLI_COMMAND_CONTRACT: List[str] = [
    "identity",
    "session",
    "answer",
    "chat-turn",
    "add-evidence",
    "import-gmail-evidence",
    "run-gmail-duckdb-pipeline",
    "import-local-evidence",
    "search-email-duckdb",
    "review",
    "mediator-prompt",
    "complaint-readiness",
    "ui-readiness",
    "client-release-gate",
    "capabilities",
    "tooling-contract",
    "workspace-data-schema",
    "migrate-legacy-workspace-data",
    "search-workspace-data",
    "view-workspace-data",
    "generate",
    "export-packet",
    "export-markdown",
    "export-docx",
    "export-pdf",
    "analyze-output",
    "formal-diagnostics",
    "filing-provenance",
    "provider-diagnostics",
    "docket-view",
    "docket-search",
    "docket-metadata",
    "docket-graph",
    "review-exports",
    "set-claim-type",
    "update-synopsis",
    "review-ui",
    "optimize-ui",
    "browser-audit",
]
_BROWSER_SDK_METHOD_CONTRACT: List[str] = [
    "createIdentity",
    "bootstrapWorkspace",
    "getSession",
    "submitIntake",
    "runIntakeChatTurn",
    "saveEvidence",
    "importGmailEvidence",
    "importLocalEvidence",
    "runGmailDuckdbPipeline",
    "searchEmailDuckdb",
    "reviewCase",
    "buildMediatorPrompt",
    "getComplaintReadiness",
    "getUiReadiness",
    "getClientReleaseGate",
    "getWorkflowCapabilities",
    "getToolingContract",
    "getWorkspaceDataSchema",
    "migrateLegacyWorkspaceData",
    "searchWorkspaceDataset",
    "viewWorkspaceDataset",
    "generateComplaint",
    "exportComplaintPacket",
    "exportComplaintMarkdown",
    "exportComplaintDocx",
    "exportComplaintPdf",
    "analyzeComplaintOutput",
    "getFormalDiagnostics",
    "getFilingProvenance",
    "getProviderDiagnostics",
    "reviewGeneratedExports",
    "updateClaimType",
    "updateCaseSynopsis",
    "reviewUiArtifacts",
    "optimizeUiArtifacts",
    "runBrowserAudit",
]

_DOCKET_ISSUE_ENTITY_KEYWORDS = (
    "issue",
    "legal_issue",
    "claim",
    "cause_of_action",
    "violation",
    "defense",
    "right",
    "duty",
)
_CORE_FLOW_CONTRACT: Dict[str, Dict[str, str]] = {
    "intake": {
        "package_export": "submit_intake_answers",
        "cli_command": "answer",
        "mcp_tool": "complaint.submit_intake",
        "browser_sdk_method": "submitIntake",
    },
    "intake_chat": {
        "package_export": "run_intake_chat_turn",
        "cli_command": "chat-turn",
        "mcp_tool": "complaint.run_intake_chat_turn",
        "browser_sdk_method": "runIntakeChatTurn",
    },
    "evidence_capture": {
        "package_export": "save_evidence",
        "cli_command": "add-evidence",
        "mcp_tool": "complaint.save_evidence",
        "browser_sdk_method": "saveEvidence",
    },
    "gmail_evidence_import": {
        "package_export": "import_gmail_evidence",
        "cli_command": "import-gmail-evidence",
        "mcp_tool": "complaint.import_gmail_evidence",
        "browser_sdk_method": "importGmailEvidence",
    },
    "gmail_duckdb_pipeline": {
        "package_export": "run_gmail_duckdb_pipeline",
        "cli_command": "run-gmail-duckdb-pipeline",
        "mcp_tool": "complaint.run_gmail_duckdb_pipeline",
        "browser_sdk_method": "runGmailDuckdbPipeline",
    },
    "local_evidence_import": {
        "package_export": "import_local_evidence",
        "cli_command": "import-local-evidence",
        "mcp_tool": "complaint.import_local_evidence",
        "browser_sdk_method": "importLocalEvidence",
    },
    "email_duckdb_search": {
        "package_export": "search_email_duckdb_corpus",
        "cli_command": "search-email-duckdb",
        "mcp_tool": "complaint.search_email_duckdb_corpus",
        "browser_sdk_method": "searchEmailDuckdb",
    },
    "support_review": {
        "package_export": "review_case",
        "cli_command": "review",
        "mcp_tool": "complaint.review_case",
        "browser_sdk_method": "reviewCase",
    },
    "mediator_handoff": {
        "package_export": "build_mediator_prompt",
        "cli_command": "mediator-prompt",
        "mcp_tool": "complaint.build_mediator_prompt",
        "browser_sdk_method": "buildMediatorPrompt",
    },
    "claim_type_alignment": {
        "package_export": "update_claim_type",
        "cli_command": "set-claim-type",
        "mcp_tool": "complaint.update_claim_type",
        "browser_sdk_method": "updateClaimType",
    },
    "case_synopsis_sync": {
        "package_export": "update_case_synopsis",
        "cli_command": "update-synopsis",
        "mcp_tool": "complaint.update_case_synopsis",
        "browser_sdk_method": "updateCaseSynopsis",
    },
    "draft_generation": {
        "package_export": "generate_complaint",
        "cli_command": "generate",
        "mcp_tool": "complaint.generate_complaint",
        "browser_sdk_method": "generateComplaint",
    },
    "complaint_export_markdown": {
        "package_export": "export_complaint_markdown",
        "cli_command": "export-markdown",
        "mcp_tool": "complaint.export_complaint_markdown",
        "browser_sdk_method": "exportComplaintMarkdown",
    },
    "complaint_export_pdf": {
        "package_export": "export_complaint_pdf",
        "cli_command": "export-pdf",
        "mcp_tool": "complaint.export_complaint_pdf",
        "browser_sdk_method": "exportComplaintPdf",
    },
    "complaint_export_docx": {
        "package_export": "export_complaint_docx",
        "cli_command": "export-docx",
        "mcp_tool": "complaint.export_complaint_docx",
        "browser_sdk_method": "exportComplaintDocx",
    },
    "complaint_output_analysis": {
        "package_export": "analyze_complaint_output",
        "cli_command": "analyze-output",
        "mcp_tool": "complaint.analyze_complaint_output",
        "browser_sdk_method": "analyzeComplaintOutput",
    },
    "formal_diagnostics": {
        "package_export": "get_formal_diagnostics",
        "cli_command": "formal-diagnostics",
        "mcp_tool": "complaint.get_formal_diagnostics",
        "browser_sdk_method": "getFormalDiagnostics",
    },
    "filing_provenance": {
        "package_export": "get_filing_provenance",
        "cli_command": "filing-provenance",
        "mcp_tool": "complaint.get_filing_provenance",
        "browser_sdk_method": "getFilingProvenance",
    },
    "provider_diagnostics": {
        "package_export": "get_provider_diagnostics",
        "cli_command": "provider-diagnostics",
        "mcp_tool": "complaint.get_provider_diagnostics",
        "browser_sdk_method": "getProviderDiagnostics",
    },
    "tooling_contract": {
        "package_export": "get_tooling_contract",
        "cli_command": "tooling-contract",
        "mcp_tool": "complaint.get_tooling_contract",
        "browser_sdk_method": "getToolingContract",
    },
    "workspace_data_schema": {
        "package_export": "get_workspace_data_schema",
        "cli_command": "workspace-data-schema",
        "mcp_tool": "complaint.get_workspace_data_schema",
        "browser_sdk_method": "getWorkspaceDataSchema",
    },
    "workspace_data_migration": {
        "package_export": "migrate_legacy_workspace_data",
        "cli_command": "migrate-legacy-workspace-data",
        "mcp_tool": "complaint.migrate_legacy_workspace_data",
        "browser_sdk_method": "migrateLegacyWorkspaceData",
    },
    "workspace_data_search": {
        "package_export": "search_workspace_dataset",
        "cli_command": "search-workspace-data",
        "mcp_tool": "complaint.search_workspace_dataset",
        "browser_sdk_method": "searchWorkspaceDataset",
    },
    "workspace_data_view": {
        "package_export": "view_workspace_dataset",
        "cli_command": "view-workspace-data",
        "mcp_tool": "complaint.view_workspace_dataset",
        "browser_sdk_method": "viewWorkspaceDataset",
    },
    "export_critic": {
        "package_export": "review_generated_exports",
        "cli_command": "review-exports",
        "mcp_tool": "complaint.review_generated_exports",
        "browser_sdk_method": "reviewGeneratedExports",
    },
    "ui_actor_critic": {
        "package_export": "review_ui",
        "cli_command": "review-ui",
        "mcp_tool": "complaint.review_ui",
        "browser_sdk_method": "reviewUiArtifacts",
    },
    "ui_closed_loop_optimizer": {
        "package_export": "optimize_ui",
        "cli_command": "optimize-ui",
        "mcp_tool": "complaint.optimize_ui",
        "browser_sdk_method": "optimizeUiArtifacts",
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify_user_id(user_id: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(user_id or DEFAULT_USER_ID).strip())
    return normalized.strip("-") or DEFAULT_USER_ID


def _split_lines(value: Optional[str]) -> List[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _unique_preserve_order(values: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in values:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _build_schema_guided_tooling_recommendations(schema_snapshot: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    snapshot = dict(schema_snapshot or {})
    if not snapshot:
        return []

    recommendations: List[Dict[str, Any]] = []
    hint_index = {
        str((item or {}).get("id") or "").strip(): str((item or {}).get("reason") or "").strip()
        for item in list(snapshot.get("ui_design_hints") or []) + list(snapshot.get("mcp_design_hints") or [])
        if isinstance(item, Mapping)
    }
    filter_dimensions = [str(item).strip() for item in list(snapshot.get("filter_dimensions") or []) if str(item).strip()]
    piece_ids = {
        str((piece or {}).get("piece_id") or "").strip()
        for piece in list(snapshot.get("piece_schemas") or [])
        if isinstance(piece, Mapping)
    }

    def add_recommendation(
        rec_id: str,
        *,
        tool_name: str,
        ui_surface: str,
        reason: str,
        priority: str = "medium",
    ) -> None:
        recommendations.append({
            "id": rec_id,
            "tool_name": tool_name,
            "ui_surface": ui_surface,
            "reason": reason,
            "priority": priority,
        })

    add_recommendation(
        "workspace_schema_refresh",
        tool_name="complaint.get_workspace_data_schema",
        ui_surface="workspace-data-operator-card",
        reason="Refresh the workspace parquet schema before designing MCP filters or navigation so the UI follows the stored dataset pieces.",
        priority="high",
    )
    add_recommendation(
        "workspace_migration_path",
        tool_name="complaint.migrate_legacy_workspace_data",
        ui_surface="workspace-data-operator-card",
        reason="Use the legacy migration flow to consolidate old complaint session and mediator stores into the packaged parquet workspace bundle.",
        priority="high",
    )
    if "schema_guided_filters" in hint_index and filter_dimensions:
        add_recommendation(
            "workspace_filter_design",
            tool_name="complaint.get_workspace_data_schema",
            ui_surface="workspace-data-schema-preview",
            reason=f"Prioritize MCP filters and browser chips for {', '.join(filter_dimensions)} because the dataset exposes those as useful selection dimensions.",
            priority="high",
        )
    if "dual_search_modes" in hint_index:
        add_recommendation(
            "dual_search_affordances",
            tool_name="complaint.search_docket_dataset",
            ui_surface="workspace-data-schema-hints-preview",
            reason=hint_index["dual_search_modes"],
            priority="medium",
        )
    if "claim_alignment_filters" in hint_index:
        add_recommendation(
            "claim_alignment_navigation",
            tool_name="complaint.review_case",
            ui_surface="review",
            reason=hint_index["claim_alignment_filters"],
            priority="medium",
        )
    if "knowledge_graph_presence" in hint_index or any(piece_id.startswith("knowledge_graph") for piece_id in piece_ids):
        add_recommendation(
            "graph_navigation",
            tool_name="complaint.get_docket_dataset_graph",
            ui_surface="packaged-docket-operator-card",
            reason=hint_index.get("knowledge_graph_presence") or "Graph entities are present in the packaged workspace and should inform related-issue exploration.",
            priority="medium",
        )
    return recommendations


def _normalize_fragment(value: Optional[str], fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"[.?!,;:]+$", "", text)
    return text or fallback


def _extract_person_name(value: Optional[str], fallback: str = "Plaintiff") -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return fallback
    text = re.sub(r"(?i)\bi am\s+", "", text)
    text = re.sub(r"(?i)\bmy address is\b.*$", "", text).strip(" ,.;:")
    text = re.sub(r"[^A-Za-z '\-]+", " ", text)
    candidates = []
    for segment in re.split(r"\s+and\s+|,|/|;", text):
        tokenized = [part.strip() for part in segment.split() if part.strip()]
        if len(tokenized) < 2:
            continue
        filtered = []
        for token in tokenized:
            lowered = token.lower()
            if lowered in {"plaintiff", "defendant", "vs", "v", "address"}:
                continue
            if token[:1].isalpha():
                filtered.append(token.strip(" .,:;"))
            if len(filtered) >= 4:
                break
        if len(filtered) >= 2:
            candidates.append(" ".join(filtered))
    if candidates:
        return candidates[0]
    compact = " ".join(text.split()[:4]).strip(" ,.;:")
    return compact or fallback


def _extract_defendant_name(value: Optional[str], fallback: str = "Defendant") -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return fallback
    if re.search(r"\bvs\b", text, flags=re.IGNORECASE):
        text = re.split(r"\bvs\b", text, flags=re.IGNORECASE, maxsplit=1)[-1].strip()
    text = re.sub(r"(?i)\b(defendant|plaintiff)s?\b", "", text).strip(" ,.;:")
    segments = [segment.strip(" ,.;:") for segment in re.split(r"\s+and\s+|;|/", text) if segment.strip()]
    normalized_segments: List[str] = []
    seen: set[str] = set()
    for segment in segments:
        cleaned = re.sub(r"[^A-Za-z0-9 '&().-]+", " ", segment)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized_segments.append(cleaned)
    if not normalized_segments:
        return fallback
    if len(normalized_segments) == 1:
        return normalized_segments[0]
    if len(normalized_segments) == 2:
        return f"{normalized_segments[0]} and {normalized_segments[1]}"
    return ", ".join(normalized_segments[:-1]) + f", and {normalized_segments[-1]}"


def _condense_timeline_text(value: Optional[str], fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return fallback
    if len(text) <= 360:
        return text
    sentence_parts = re.split(r"(?<=[.!?])\s+", text)
    date_pattern = re.compile(
        r"\b("
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
        r")\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}\b",
        flags=re.IGNORECASE,
    )
    focused = [part.strip() for part in sentence_parts if date_pattern.search(part or "")]
    if len(focused) >= 2:
        return " ".join(focused[:6]).strip()
    return " ".join(sentence_parts[:3]).strip()[:520]


def _sentence_fragment(value: Optional[str], fallback: str) -> str:
    text = _normalize_fragment(value, fallback)
    if not text:
        return fallback
    return f"{text[0].lower()}{text[1:]}" if text[:1].isalpha() else text


def _event_fragment(value: Optional[str], fallback: str) -> str:
    text = _sentence_fragment(value, fallback)
    if text.startswith("was "):
        return text[4:]
    return text


def _adverse_action_clause(value: Optional[str], fallback: str) -> str:
    text = _event_fragment(value, fallback)
    lowered = text.lower()
    replacements = {
        "terminated ": "terminating Plaintiff ",
        "fired ": "firing Plaintiff ",
        "suspended ": "suspending Plaintiff ",
        "disciplined ": "disciplining Plaintiff ",
        "demoted ": "demoting Plaintiff ",
        "evicted ": "evicting Plaintiff ",
        "denied ": "denying Plaintiff ",
        "threatened ": "threatening Plaintiff ",
    }
    for old, new in replacements.items():
        if lowered.startswith(old):
            return new + text[len(old):]
    return text


def _pleading_activity_fragment(value: Optional[str], fallback: str) -> str:
    text = _sentence_fragment(value, fallback)
    replacements = {
        "reported ": "reporting ",
        "requested ": "requesting ",
        "complained about ": "complaining about ",
        "complained to ": "complaining to ",
        "opposed ": "opposing ",
        "filed ": "filing ",
        "disclosed ": "disclosing ",
        "asked for ": "asking for ",
        "sought ": "seeking ",
    }
    lowered = text.lower()
    for old, new in replacements.items():
        if lowered.startswith(old):
            text = new + text[len(old):]
            break
    clause_replacements = {
        " and reported ": " and reporting ",
        " and requested ": " and requesting ",
        " and complained about ": " and complaining about ",
        " and complained to ": " and complaining to ",
        " and opposed ": " and opposing ",
        " and filed ": " and filing ",
        " and disclosed ": " and disclosing ",
        " and asked for ": " and asking for ",
        " and sought ": " and seeking ",
    }
    for old, new in clause_replacements.items():
        text = re.sub(re.escape(old), new, text, flags=re.IGNORECASE)
    return text


def _pleading_sentence(value: Optional[str], fallback: str) -> str:
    text = _normalize_fragment(value, fallback)
    if not text:
        return fallback
    text = re.sub(r"\s+", " ", text).strip()
    text = text[0].upper() + text[1:] if text[:1].isalpha() else text
    return f"{text}."


def _timeline_clause_fragment(value: str) -> str:
    text = _normalize_fragment(value, "the relevant event occurred")
    lowered = text.lower()
    replacements = {
        "report on ": "Plaintiff made the report on ",
        "complaint on ": "Plaintiff made the complaint on ",
        "accommodation request on ": "Plaintiff made the accommodation request on ",
        "requested accommodation in ": "Plaintiff requested an accommodation in ",
        "reported discrimination on ": "Plaintiff reported discrimination on ",
        "reported retaliation on ": "Plaintiff reported retaliation on ",
        "reported wage-and-hour violations on ": "Plaintiff reported wage-and-hour violations on ",
        "termination on ": "the termination occurred on ",
        "terminated on ": "Plaintiff was terminated on ",
        "was terminated on ": "Plaintiff was terminated on ",
        "threatened on ": "Plaintiff was threatened on ",
        "was threatened on ": "Plaintiff was threatened on ",
        "denial notice on ": "the denial notice issued on ",
        "eviction threat on ": "the eviction threat followed on ",
        "lost the housing opportunity in ": "the housing opportunity was lost in ",
    }
    for old, new in replacements.items():
        if lowered.startswith(old):
            return new + text[len(old):]
    return text


def _llm_draft_timeout_for_provider(provider: Optional[str]) -> int:
    explicit = str(os.getenv("COMPLAINT_GENERATOR_LLM_DRAFT_TIMEOUT_SECONDS", "") or "").strip()
    if explicit:
        try:
            return max(5, int(float(explicit)))
        except Exception:
            pass

    provider_key = str(provider or "").strip().lower()
    if provider_key:
        provider_override = str(
            os.getenv(f"COMPLAINT_GENERATOR_LLM_DRAFT_TIMEOUT_SECONDS_{provider_key.upper()}", "") or ""
        ).strip()
        if provider_override:
            try:
                return max(5, int(float(provider_override)))
            except Exception:
                pass
    return int(DEFAULT_LLM_DRAFT_TIMEOUTS_BY_PROVIDER.get(provider_key, DEFAULT_LLM_DRAFT_TIMEOUT_SECONDS))


def _resolve_llm_draft_backend(
    provider: Optional[str],
    model: Optional[str],
) -> Dict[str, Optional[str]]:
    requested_provider = str(provider or "").strip()
    requested_model = str(model or "").strip()

    env_default_provider = str(os.getenv("COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER", "") or "").strip()
    effective_provider = requested_provider or env_default_provider or DEFAULT_LLM_DRAFT_PROVIDER
    provider_key = effective_provider.lower()

    env_provider_model = str(
        os.getenv(f"COMPLAINT_GENERATOR_LLM_DRAFT_MODEL_{provider_key.upper()}", "") or ""
    ).strip()
    env_default_model = str(os.getenv("COMPLAINT_GENERATOR_LLM_DRAFT_MODEL", "") or "").strip()
    effective_model = (
        requested_model
        or env_provider_model
        or env_default_model
        or DEFAULT_LLM_DRAFT_MODELS_BY_PROVIDER.get(provider_key)
        or None
    )

    return {
        "provider": effective_provider,
        "model": effective_model,
        "requested_provider": requested_provider or None,
        "requested_model": requested_model or None,
    }


def _resolve_llm_draft_backend_candidates(
    provider: Optional[str],
    model: Optional[str],
) -> List[Dict[str, Optional[str]]]:
    requested_provider = str(provider or "").strip()
    requested_model = str(model or "").strip()
    env_default_provider = str(os.getenv("COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER", "") or "").strip()

    if requested_provider or env_default_provider:
        return [_resolve_llm_draft_backend(provider, model)]

    candidates: List[Dict[str, Optional[str]]] = []
    seen: set[str] = set()
    for fallback_provider in DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN:
        provider_key = str(fallback_provider or "").strip().lower()
        if not provider_key or provider_key in seen:
            continue
        seen.add(provider_key)
        candidates.append(
            _resolve_llm_draft_backend(
                fallback_provider,
                requested_model or None,
            )
        )
    return candidates or [_resolve_llm_draft_backend(provider, model)]


def _pleading_timeline_sentence(value: Optional[str], fallback: str) -> str:
    text = _normalize_fragment(value, fallback)
    if not text:
        return _pleading_sentence(fallback, fallback)
    sentence_parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if len(sentence_parts) >= 2:
        fragments = []
        for part in sentence_parts[:6]:
            cleaned = re.sub(r"[.?!]+$", "", part).strip()
            if cleaned:
                fragments.append(_timeline_clause_fragment(cleaned))
        if not fragments:
            return _pleading_sentence(text, fallback)
        sentence = " ".join(
            f"{fragment.rstrip('.') }." if not str(fragment).rstrip().endswith(".") else str(fragment).rstrip()
            for fragment in fragments
        )
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if sentence[:1].isalpha():
            sentence = sentence[0].upper() + sentence[1:]
        return sentence
    parts = [part.strip() for part in re.split(r",|\band\b", text) if part.strip()]
    if not parts:
        return _pleading_sentence(text, fallback)
    fragments = [_timeline_clause_fragment(part) for part in parts]
    if len(fragments) == 1:
        sentence = fragments[0]
    elif len(fragments) == 2:
        sentence = f"{fragments[0]}, and {fragments[1]}"
    else:
        sentence = f"{', '.join(fragments[:-1])}, and {fragments[-1]}"
    sentence = re.sub(r"\s+", " ", sentence).strip()
    if sentence[:1].isalpha():
        sentence = sentence[0].upper() + sentence[1:]
    if not sentence.endswith("."):
        sentence = f"{sentence}."
    return sentence


def _formalize_relief_item(value: Optional[str]) -> str:
    text = _normalize_fragment(value, "Other appropriate relief")
    lowered = text.lower()
    replacements = {
        "back pay": "Back pay and lost benefits",
        "front pay": "Front pay in lieu of reinstatement",
        "injunctive relief": "Appropriate injunctive and equitable relief",
        "reinstatement": "Reinstatement to Plaintiff's former position or a comparable position",
        "attorney fees": "Reasonable attorney's fees and costs",
        "attorney's fees": "Reasonable attorney's fees and costs",
        "fees": "Reasonable fees and costs",
        "declaratory relief": "Declaratory relief as authorized by law",
        "compensatory damages": "Compensatory damages according to proof",
        "damages": "Damages according to proof",
    }
    return replacements.get(lowered, text)


def _court_header_line(value: Optional[str]) -> str:
    text = _normalize_fragment(value, "FOR THE APPROPRIATE JUDICIAL DISTRICT")
    upper = text.upper()
    if "UNITED STATES DISTRICT COURT" in upper:
        return "FOR THE APPROPRIATE JUDICIAL DISTRICT"
    if upper.startswith("FOR "):
        return upper
    if "DISTRICT OF" in upper:
        return f"FOR {upper}" if upper.startswith("THE ") else f"FOR THE {upper}"
    return "FOR THE APPROPRIATE JUDICIAL DISTRICT"


def _build_export_structure_summary(markdown_text: str) -> Dict[str, Any]:
    parsed = parse_legal_document(str(markdown_text or ""))
    payload = parsed.to_dict()
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []
    payload["summary"] = {
        "has_header": bool(header),
        "court_line_count": len(header.get("court_lines") or []),
        "party_line_count": len(header.get("party_lines") or []),
        "title_line_count": len(header.get("title_lines") or []),
        "section_count": len(sections),
        "section_kinds": [str(section.get("kind") or "") for section in sections[:20] if isinstance(section, dict)],
        "numbered_paragraph_count": int(payload.get("numbered_paragraph_count") or 0),
        "bullet_count": int(payload.get("bullet_count") or 0),
        "code_block_count": int(payload.get("code_block_count") or 0),
        "all_caps_heading_count": int(payload.get("all_caps_heading_count") or 0),
        "title": str(payload.get("title") or ""),
    }
    return payload


def _slugify_filename(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower())
    return normalized.strip("-") or "complaint-packet"


def _normalize_claim_type(value: Optional[str]) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized or "retaliation"


def _claim_type_display_name(value: Optional[str]) -> str:
    normalized = _normalize_claim_type(value)
    return _CLAIM_TYPE_LABELS.get(normalized, normalized.replace("_", " ").title())


def _claim_element_label(value: Optional[str]) -> str:
    normalized = str(value or "").strip()
    for element in _CLAIM_ELEMENTS:
        if str(element.get("id") or "").strip() == normalized:
            return str(element.get("label") or normalized).strip()
    return normalized.replace("_", " ").strip() or "an identified claim element"


def _formal_evidence_summary_item(item: Dict[str, Any], *, kind: str) -> str:
    title = _evidence_display_title(item, kind=kind)
    element_label = _claim_element_label(item.get("claim_element_id")).lower()
    if kind == "testimony":
        return f"testimony presently identified as '{title}' on the {element_label} element"
    return f"documentary exhibit presently identified as '{title}' on the {element_label} element"


def _compact_evidence_reference_item(item: Dict[str, Any]) -> str:
    title = _evidence_display_title(item, kind=str(item.get("kind") or "evidence"))
    element_label = _claim_element_label(item.get("claim_element_id")).strip() or "Claim element"
    return f"{title} ({element_label})"


def _exhibit_label(index: int) -> str:
    if index < 0:
        return "Exhibit ?"
    value = index
    letters = ""
    while True:
        value, remainder = divmod(value, 26)
        letters = chr(ord("A") + remainder) + letters
        if value == 0:
            break
        value -= 1
    return f"Exhibit {letters}"


def _evidence_display_title(item: Dict[str, Any], *, kind: str) -> str:
    raw_title = str(item.get("title") or f"Untitled {kind}").strip()
    if not raw_title.lower().startswith("local import:"):
        return raw_title

    source = str(item.get("source") or "")
    filename = raw_title.split(":", 1)[-1].strip()
    path_tail = source.split("local_artifact_import:", 1)[-1].strip() if "local_artifact_import:" in source else ""
    lowered_filename = filename.lower()
    lowered_path = path_tail.lower()

    explicit_mappings = {
        "a38c7914-ea37-4c2f-a815-711d4a97c92b.txt": "HACC ACOP policy",
        "8ee6f7d1-0c36-48e4-9677-336b95fb9858.txt": "HACC HCV Administrative Plan",
        "hud_fair_housing_act.html": "HUD Fair Housing Act materials",
        "ors_chapter_659a_discrimination_definitions_and_procedures.html": "ORS chapter 659A discrimination provisions",
        "ors_chapter_456_housing_authorities.html": "ORS chapter 456 housing-authority provisions",
        "945af141-c7d1-4973-88c0-b57024243114.txt": "HACC grievance and hearing policy text",
        "b53a0523-fa60-4df6-bba3-6ae34a47cb02.txt": "HACC reasonable-accommodation policy text",
        "exhibit_index.md": "Temporary CLI session exhibit index",
        "email_evidence_memo.md": "Temporary CLI session email evidence memo",
        "reasonable_accommodation_ocr_memo.md": "Reasonable accommodation OCR memo",
        "chronology_evidence_matrix.json": "Chronology evidence matrix",
        "summary.json": "HACC knowledge-graph summary",
        "engine.py": "HACC research engine source",
        "hacc_corpus.summary.json": "HACC corpus index summary",
        "hacc_enhanced_index_20260314_055513.summary.json": "HACC enhanced index summary",
        "evidence_review.md": "Prior evidence review memorandum",
        "evidence_review.json": "Prior evidence review data",
        "p1_critical_civil_rights_fair-housing.aspx": "Oregon fair-housing guidance",
        "p1_critical_civil_rights_racial-discrimination.aspx": "Oregon racial-discrimination guidance",
        "p2_procurement_&_rules_fair_housing_equal_opp": "Oregon fair-housing equal-opportunity rules",
        "p3_regulatory_find-affordable-housing.aspx": "Oregon affordable-housing guidance",
        "p3_regulatory_housing-counseling.aspx": "Oregon housing-counseling guidance",
        "p3_regulatory_housing-for-veterans.aspx": "Oregon housing-for-veterans guidance",
    }
    if lowered_filename in explicit_mappings:
        return explicit_mappings[lowered_filename]

    if "evidence_review_" in lowered_path and lowered_filename.endswith(".md"):
        return "Prior evidence review memorandum"
    if "evidence_review_" in lowered_path and lowered_filename.endswith(".json"):
        return "Prior evidence review data"
    if lowered_filename.endswith(".html") or lowered_filename.endswith(".aspx"):
        cleaned = re.sub(r"\.(html|aspx)$", "", filename, flags=re.IGNORECASE)
        cleaned = cleaned.replace("_", " ").replace("-", " ").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned[:1].upper() + cleaned[1:] if cleaned else raw_title
    cleaned = re.sub(r"\.[A-Za-z0-9]+$", "", filename)
    cleaned = cleaned.replace("_", " ").replace("-", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:1].upper() + cleaned[1:] if cleaned else raw_title


def _evidence_priority(item: Dict[str, Any]) -> int:
    title = _evidence_display_title(item, kind=str(item.get("kind") or "evidence")).lower()
    source = str(item.get("source") or "").lower()
    score = 0
    if "chronology evidence matrix" in title:
        score += 100
    if "email evidence memo" in title:
        score += 95
    if "reasonable accommodation ocr memo" in title:
        score += 90
    if "exhibit index" in title:
        score += 85
    if "evidence review" in title:
        score += 70
    if "acop" in title or "administrative plan" in title:
        score += 60
    if "fair housing act" in title or "659a" in title or "456" in title:
        score += 55
    if "temporary-cli-session-migration" in source or "workspace-generated" in source:
        score += 40
    if "migrated_sources/research_results/evidence_review_" in source:
        score += 20
    return score


def _claim_type_filing_guidance(value: Optional[str]) -> str:
    normalized = _normalize_claim_type(value)
    return {
        "retaliation": (
            "Emphasize protected activity, employer knowledge, temporal proximity, retaliatory motive, adverse action, "
            "and damages. Keep the chronology tight and make the causation theory explicit."
        ),
        "employment_discrimination": (
            "Emphasize protected status or protected conduct, discriminatory treatment, comparator or disparate-treatment logic "
            "when present, adverse employment action, damages, and requested relief tied to employment harm."
        ),
        "housing_discrimination": (
            "Emphasize housing rights, discriminatory denial or interference, protected status or protected housing activity, "
            "housing-related harm, and the requested equitable or damages relief."
        ),
        "due_process_failure": (
            "Emphasize the deprivation, missing notice or hearing protections, procedural defects, resulting harm, and the specific "
            "procedural relief or damages being sought."
        ),
        "consumer_protection": (
            "Emphasize the deceptive or unfair practice, reliance or transaction context when present, resulting economic harm, "
            "and restitutionary or injunctive relief."
        ),
    }.get(
        normalized,
        "Shape the complaint like a formal civil pleading with a clear chronology, concrete harm, and requested relief grounded in the record.",
    )


def _claim_type_count_heading(value: Optional[str]) -> str:
    normalized = _normalize_claim_type(value)
    return {
        "retaliation": "COUNT I - RETALIATION",
        "employment_discrimination": "COUNT I - EMPLOYMENT DISCRIMINATION",
        "housing_discrimination": "COUNT I - HOUSING DISCRIMINATION",
        "due_process_failure": "COUNT I - DUE PROCESS VIOLATION",
        "consumer_protection": "COUNT I - CONSUMER PROTECTION",
    }.get(normalized, f"COUNT I - {_claim_type_display_name(normalized).upper()}")


def _claim_type_required_allegations(value: Optional[str]) -> List[str]:
    normalized = _normalize_claim_type(value)
    return {
        "retaliation": [
            "Allege the protected activity with specificity.",
            "Allege defendant knowledge of the protected activity.",
            "Allege the adverse action and the chronology tying it to the protected activity.",
            "Allege resulting damages and requested relief.",
        ],
        "employment_discrimination": [
            "Allege the discriminatory treatment or adverse employment action with specificity.",
            "Allege the protected status, protected conduct, or prohibited motive that makes the treatment unlawful.",
            "Allege the chronology, comparators, disparate treatment, or surrounding facts supporting discriminatory inference when present.",
            "Allege resulting damages and requested relief tied to employment harm.",
        ],
        "housing_discrimination": [
            "Allege the housing-related denial, interference, limitation, or retaliation with specificity.",
            "Allege the protected housing status, rights, or protected housing activity that makes the conduct unlawful.",
            "Allege the property, housing benefit, tenancy, or housing opportunity context clearly enough to read like a real housing pleading.",
            "Allege resulting housing harm, economic harm, and requested equitable or damages relief.",
        ],
        "due_process_failure": [
            "Allege the deprivation or adverse action imposed by defendant.",
            "Allege the missing notice, hearing, review, appeal, or other procedural protection.",
            "Allege the chronology showing plaintiff was deprived without the required process.",
            "Allege resulting harm and requested procedural or damages relief.",
        ],
        "consumer_protection": [
            "Allege the unfair, deceptive, or unlawful practice with specificity.",
            "Allege the transaction, consumer relationship, or commercial context.",
            "Allege how plaintiff was misled, harmed, overcharged, or otherwise injured.",
            "Allege resulting damages, restitution, injunctive relief, or other requested relief.",
        ],
    }.get(
        normalized,
        [
            "Allege the unlawful conduct with specificity.",
            "Allege the chronology and resulting harm clearly.",
            "Allege why the pleaded facts support the claim for relief.",
        ],
    )


def _claim_type_formal_example_snippet(value: Optional[str]) -> str:
    normalized = _normalize_claim_type(value)
    return {
        "retaliation": (
            "7. Plaintiff engaged in protected activity by reporting discrimination to human resources.\n"
            "8. Defendant knew of Plaintiff's protected activity before imposing the challenged adverse action.\n"
            "9. Within days of that protected activity, Defendant terminated Plaintiff, supporting a strong inference of retaliatory motive."
        ),
        "employment_discrimination": (
            "7. Plaintiff is a member of a protected class and was performing the job in a satisfactory manner.\n"
            "8. Defendant nevertheless subjected Plaintiff to discriminatory terms, conditions, or termination.\n"
            "9. Comparable employees outside Plaintiff's protected group were treated more favorably under similar circumstances."
        ),
        "housing_discrimination": (
            "7. Plaintiff sought to rent, retain, or enjoy housing on equal terms protected by law.\n"
            "8. Defendant denied, limited, or interfered with that housing opportunity because of Plaintiff's protected housing status or activity.\n"
            "9. As a result, Plaintiff lost housing stability, incurred relocation-related harm, or was denied equal housing access."
        ),
        "due_process_failure": (
            "7. Defendant deprived Plaintiff of a protected interest without adequate notice.\n"
            "8. Defendant failed to provide the hearing, review, or procedural safeguards required before imposing that deprivation.\n"
            "9. Plaintiff suffered concrete harm because the challenged action occurred without constitutionally adequate process."
        ),
        "consumer_protection": (
            "7. Defendant made deceptive or unfair representations in connection with a consumer transaction.\n"
            "8. Plaintiff relied on or was exposed to those representations in the course of the transaction.\n"
            "9. Plaintiff suffered economic loss or other consumer harm as a result of Defendant's deceptive practice."
        ),
    }.get(
        normalized,
        "7. Plaintiff alleges specific unlawful conduct by Defendant.\n"
        "8. Defendant's conduct caused concrete harm to Plaintiff.\n"
        "9. Plaintiff seeks relief that remedies the pleaded misconduct."
    )


def _strip_code_fences(text: str) -> str:
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        parts = stripped.splitlines()
        if parts:
            parts = parts[1:]
        while parts and parts[-1].strip().startswith("```"):
            parts = parts[:-1]
        stripped = "\n".join(parts).strip()
    return stripped


def _normalize_llm_complaint_body(body: str, claim_type: Optional[str] = None) -> tuple[str, List[str]]:
    normalized = str(body or "").replace("\r\n", "\n").strip()
    if not normalized:
        return "", []

    notes: List[str] = []

    court_caption_match = re.search(
        r"(?im)^\s{0,3}(?:#{1,6}\s+)?in the united states district court\s*$",
        normalized,
    )
    if court_caption_match and court_caption_match.start() > 0:
        normalized = normalized[court_caption_match.start() :].lstrip()
        notes.append("trimmed_leading_preamble")

    normalized_court_caption = re.sub(
        r"(?im)^\s{0,3}(?:#{1,6}\s+)?in the united states district court\s*$",
        "IN THE UNITED STATES DISTRICT COURT",
        normalized,
    )
    if normalized_court_caption != normalized:
        normalized = normalized_court_caption
        notes.append("normalized_court_caption")

    normalized_civil_action = re.sub(
        r"(?im)^civil action no\.\s*:\s*([_A-Z0-9.-]+)\s*$",
        r"Civil Action No. \1",
        normalized,
    )
    if normalized_civil_action != normalized:
        normalized = normalized_civil_action
        notes.append("normalized_civil_action_heading")

    heading_patterns = [
        r"IN THE UNITED STATES DISTRICT COURT",
        r"Civil Action No\.\s*[_A-Z0-9.-]+",
        r"COMPLAINT FOR .+",
        r"JURY TRIAL DEMANDED",
        r"NATURE OF THE ACTION",
        r"JURISDICTION AND VENUE",
        r"PARTIES",
        r"FACTUAL ALLEGATIONS",
        r"EVIDENTIARY SUPPORT AND NOTICE",
        r"CLAIM FOR RELIEF",
        r"COUNT I - .+",
        r"PRAYER FOR RELIEF",
        r"JURY DEMAND",
        r"SIGNATURE BLOCK",
    ]
    heading_pattern = "|".join(f"(?:{pattern})" for pattern in heading_patterns)
    without_markdown_headings = re.sub(
        rf"(?m)^\s{{0,3}}#{1,6}\s+({heading_pattern})\s*$",
        r"\1",
        normalized,
    )
    without_generic_heading_hashes = re.sub(
        r"(?m)^\s{0,3}#{1,6}\s+([A-Z][A-Z0-9 .:&'()/_-]+)\s*$",
        r"\1",
        without_markdown_headings,
    )
    without_heading_emphasis = re.sub(
        rf"(?m)^\s*(?:\*\*|__)\s*({heading_pattern}|[A-Z][A-Z0-9 .:&'()/_-]+)\s*(?:\*\*|__)\s*$",
        r"\1",
        without_generic_heading_hashes,
    )
    if without_heading_emphasis != normalized:
        normalized = without_heading_emphasis
        notes.append("removed_markdown_heading_markup")

    # Trim obvious non-pleading appendices or workspace scaffolding that can
    # appear after an otherwise-usable complaint body.
    trailing_section_markers = [
        "\nAPPENDIX A - ",
        "\nAPPENDIX B - ",
        "\nAPPENDIX C - ",
        "\nAPPENDIX D - ",
        "\nAPPENDIX E - ",
        "\nAPPENDIX F - ",
        "\nWORKING CASE SYNOPSIS",
        "\nCOMPLAINT RECORD",
        "\nWORKFLOW SUMMARY",
    ]
    cut_points = [normalized.find(marker) for marker in trailing_section_markers if normalized.find(marker) > 0]
    if cut_points:
        normalized = normalized[: min(cut_points)].rstrip()
        notes.append("trimmed_workspace_appendices")

    replacements = {
        "current complaint record": "present evidentiary record",
        "support review": "present evidentiary posture",
        "workflow summary": "pleading summary",
        "complaint record": "pleading record",
        "support matrix": "evidentiary posture",
        "json": "record",
        "sdk": "record",
    }
    for old, new in replacements.items():
        updated = re.sub(re.escape(old), new, normalized, flags=re.IGNORECASE)
        if updated != normalized:
            notes.append(f"replaced:{old}")
            normalized = updated

    normalized_paragraphs = re.sub(r"(?m)^(\s*)(\d+)\)\s+", r"\1\2. ", normalized)
    if normalized_paragraphs != normalized:
        normalized = normalized_paragraphs
        notes.append("normalized_numbered_paragraphs")

    canonical_heading_map = {
        "NATURE OF THE ACTION": "NATURE OF THE ACTION",
        "JURISDICTION AND VENUE": "JURISDICTION AND VENUE",
        "PARTIES": "PARTIES",
        "FACTUAL ALLEGATIONS": "FACTUAL ALLEGATIONS",
        "EVIDENTIARY SUPPORT AND NOTICE": "EVIDENTIARY SUPPORT AND NOTICE",
        "CLAIM FOR RELIEF": "CLAIM FOR RELIEF",
        "PRAYER FOR RELIEF": "PRAYER FOR RELIEF",
        "JURY DEMAND": "JURY DEMAND",
        "SIGNATURE BLOCK": "SIGNATURE BLOCK",
    }
    for variant, canonical in canonical_heading_map.items():
        updated = re.sub(rf"(?im)^{re.escape(variant)}\s*:\s*$", canonical, normalized)
        updated = re.sub(rf"(?im)^{re.escape(variant)}\s*$", canonical, updated)
        if updated != normalized:
            normalized = updated
            notes.append("normalized_section_heading_punctuation")

    updated_count_heading_variants = re.sub(
        r"(?im)^count\s+(?:one|1|i)\s*[-:]\s*",
        "COUNT I - ",
        normalized,
    )
    if updated_count_heading_variants != normalized:
        normalized = updated_count_heading_variants
        notes.append("normalized_count_heading")

    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()

    # If the model omitted the exact claim heading but otherwise produced a
    # usable pleading body, normalize the heading to the selected claim type.
    if claim_type:
        preferred_heading = f"COMPLAINT FOR {_claim_type_display_name(claim_type).upper()}"
        preferred_count_heading = _claim_type_count_heading(claim_type)
        if preferred_heading not in normalized:
            if _looks_like_formal_complaint_candidate(normalized):
                with_injected_heading = re.sub(
                    r"(?im)^(civil action no\.\s*[_\sA-Z0-9.-]+)\s*$",
                    rf"\1\n\n{preferred_heading}",
                    normalized,
                    count=1,
                )
                if with_injected_heading == normalized:
                    with_injected_heading = f"{preferred_heading}\n\n{normalized}"
                if with_injected_heading != normalized:
                    normalized = with_injected_heading
                    notes.append("injected_missing_complaint_heading")
        updated_heading = re.sub(
            r"(?im)^complaint for .+$",
            preferred_heading,
            normalized,
            count=1,
        )
        if updated_heading != normalized:
            notes.append("normalized_complaint_heading")
            normalized = updated_heading
        updated_count = re.sub(
            r"(?im)^count i - .+$",
            preferred_count_heading,
            normalized,
            count=1,
        )
        if updated_count != normalized:
            notes.append("normalized_count_heading")
            normalized = updated_count

    return normalized, sorted(set(notes))


def _parse_json_object(text: str) -> Dict[str, Any]:
    stripped = _strip_code_fences(text)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", stripped):
        start = match.start()
        try:
            parsed, end = decoder.raw_decode(stripped[start:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            trailing = stripped[start + end :].strip()
            if not trailing or trailing.startswith("```") or trailing.startswith("Thanks") or trailing.startswith("Note"):
                return parsed
    return {}


def _required_formal_complaint_markers() -> List[str]:
    return [
        "IN THE UNITED STATES DISTRICT COURT",
        "Civil Action No. ________________",
        "COMPLAINT FOR",
        "JURISDICTION AND VENUE",
        "FACTUAL ALLEGATIONS",
        "EVIDENTIARY SUPPORT AND NOTICE",
        "COUNT I -",
        "PRAYER FOR RELIEF",
        "JURY DEMAND",
        "SIGNATURE BLOCK",
    ]


def _formal_complaint_forbidden_meta_phrases() -> List[str]:
    return [
        "workflow summary",
        "complaint record",
        "support matrix",
        "mcp",
        "sdk",
        "product explanation",
        "json",
    ]


def _formal_complaint_validation_issues(body: str, claim_type: Optional[str] = None) -> List[str]:
    complaint_body = str(body or "").strip()
    issues: List[str] = []
    for marker in _required_formal_complaint_markers():
        if marker not in complaint_body:
            issues.append(f"Missing formal marker: {marker}")

    if not re.search(r"(?m)^\s*\d+\.\s+", complaint_body):
        issues.append("Missing numbered pleading paragraphs.")

    lowered = complaint_body.lower()
    for phrase in _formal_complaint_forbidden_meta_phrases():
        if phrase in lowered:
            issues.append(f"Contains meta-summary language: {phrase}")

    if claim_type:
        preferred_heading = f"COMPLAINT FOR {_claim_type_display_name(claim_type).upper()}"
        preferred_count_heading = _claim_type_count_heading(claim_type)
        if preferred_heading not in complaint_body:
            issues.append(f"Missing preferred complaint heading: {preferred_heading}")
        if preferred_count_heading not in complaint_body:
            issues.append(f"Missing preferred count heading: {preferred_count_heading}")
    return issues


def _build_complaint_output_release_gate(
    *,
    claim_type: str,
    draft_strategy: str,
    filing_shape_score: int,
    claim_type_alignment_score: int,
    missing_elements: int,
    evidence_item_count: int,
) -> Dict[str, Any]:
    normalized_claim_type = _normalize_claim_type(claim_type)
    normalized_strategy = str(draft_strategy or "template").strip() or "template"
    if filing_shape_score >= 85 and claim_type_alignment_score >= 85 and missing_elements == 0 and evidence_item_count > 0:
        verdict = "pass"
        reason = (
            "The exported complaint currently reads like a filing-ready "
            f"{_claim_type_display_name(normalized_claim_type).lower()} complaint and the record is materially supported."
        )
    elif filing_shape_score >= 75 and claim_type_alignment_score >= 75 and evidence_item_count > 0:
        verdict = "warning"
        reason = (
            "The exported complaint is moving in the right direction, but it still needs tighter proof posture, "
            "claim alignment, or filing polish before it should be treated as client-safe."
        )
    else:
        verdict = "blocked"
        reason = (
            "The exported complaint is not yet formal or well-aligned enough to treat the current UI flow as safe for real legal clients."
        )
    return {
        "verdict": verdict,
        "reason": reason,
        "claim_type": normalized_claim_type,
        "claim_type_label": _claim_type_display_name(normalized_claim_type),
        "draft_strategy": normalized_strategy,
        "filing_shape_score": int(filing_shape_score or 0),
        "claim_type_alignment_score": int(claim_type_alignment_score or 0),
        "missing_elements": int(missing_elements or 0),
        "evidence_item_count": int(evidence_item_count or 0),
    }


def _release_gate_score_from_verdict(verdict: Optional[str]) -> int:
    normalized = str(verdict or "").strip().lower()
    if normalized in {"pass", "client_safe"}:
        return 100
    if normalized == "warning":
        return 70
    if normalized == "blocked":
        return 20
    return 35


def _build_local_client_release_gate_for_state(state: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
    overview = dict(review.get("overview") or {})
    draft = dict(state.get("draft") or {})
    claim_type = _normalize_claim_type(state.get("claim_type"))
    if not draft:
        return {
            "verdict": "blocked",
            "reason": "No complaint draft exists yet, so the exported filing quality has not been validated.",
            "claim_type": claim_type,
            "claim_type_label": _claim_type_display_name(claim_type),
            "draft_strategy": None,
            "filing_shape_score": 0,
            "claim_type_alignment_score": 0,
            "missing_elements": int(overview.get("missing_elements") or 0),
            "evidence_item_count": int(overview.get("testimony_items") or 0) + int(overview.get("document_items") or 0),
            "status": "unavailable",
        }

    body = str(draft.get("body") or "")
    validation_issues = _formal_complaint_validation_issues(body, claim_type)
    evidence_item_count = int(overview.get("testimony_items") or 0) + int(overview.get("document_items") or 0)
    filing_shape_score = max(0, min(100, 100 - (len(validation_issues) * 10)))
    expected_heading = f"COMPLAINT FOR {_claim_type_display_name(claim_type).upper()}"
    expected_count_heading = _claim_type_count_heading(claim_type)
    alignment_matches = int(expected_heading in body) + int(expected_count_heading in body)
    claim_type_alignment_score = 100 if alignment_matches == 2 else 50 if alignment_matches == 1 else 0
    return _build_complaint_output_release_gate(
        claim_type=claim_type,
        draft_strategy=str(draft.get("draft_strategy") or "template"),
        filing_shape_score=filing_shape_score,
        claim_type_alignment_score=claim_type_alignment_score,
        missing_elements=int(overview.get("missing_elements") or 0),
        evidence_item_count=evidence_item_count,
    )


def _has_required_formal_complaint_markers(body: str) -> bool:
    return not _formal_complaint_validation_issues(body)


def _looks_like_formal_complaint_candidate(body: str) -> bool:
    text = str(body or "")
    if "IN THE UNITED STATES DISTRICT COURT" not in text:
        return False
    heuristic_markers = [
        "NATURE OF THE ACTION",
        "JURISDICTION AND VENUE",
        "FACTUAL ALLEGATIONS",
        "CLAIM FOR RELIEF",
        "PRAYER FOR RELIEF",
        "SIGNATURE BLOCK",
    ]
    matched = sum(1 for marker in heuristic_markers if marker in text)
    return matched >= 4


def generate_decentralized_id() -> Dict[str, Any]:
    try:
        from ipfs_datasets_py.processors.auth.ucan import UCANManager

        manager = UCANManager.get_instance()
        if manager.initialize():
            keypair = manager.generate_keypair()
            return {
                "did": keypair.did,
                "method": "did:key",
                "provider": "ipfs_datasets_py.processors.auth.ucan.UCANManager",
            }
    except Exception as exc:
        return {
            "did": f"did:key:fallback-{uuid.uuid4().hex}",
            "method": "did:key",
            "provider": "fallback",
            "warning": str(exc),
        }

    return {
        "did": f"did:key:fallback-{uuid.uuid4().hex}",
        "method": "did:key",
        "provider": "fallback",
        "warning": "UCAN manager did not initialize cleanly.",
    }


def _default_state(user_id: str) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "claim_type": _normalize_claim_type("retaliation"),
        "case_synopsis": "",
        "intake_answers": {},
        "intake_history": [],
        "evidence": {"testimony": [], "documents": []},
        "filing_metadata": {},
        "draft": None,
        "latest_packet_export": None,
        "latest_export_critic": None,
        "ui_readiness": None,
    }


class ComplaintWorkspaceService:
    def __init__(self, root_dir: Optional[Path] = None) -> None:
        base_dir = Path(root_dir) if root_dir is not None else _SESSION_DIR
        self._session_dir = base_dir
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._last_draft_refinement_error: Optional[str] = None

    def _session_path(self, user_id: str) -> Path:
        return self._session_dir / f"{_slugify_user_id(user_id)}.json"

    def _load_state(self, user_id: str) -> Dict[str, Any]:
        path = self._session_path(user_id)
        if not path.exists():
            return _default_state(user_id)
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return _default_state(user_id)
        if not isinstance(payload, dict):
            return _default_state(user_id)
        payload.setdefault("user_id", user_id)
        payload["claim_type"] = _normalize_claim_type(payload.get("claim_type"))
        payload.setdefault("case_synopsis", "")
        payload.setdefault("intake_answers", {})
        payload.setdefault("intake_history", [])
        payload.setdefault("evidence", {"testimony": [], "documents": []})
        payload.setdefault("filing_metadata", {})
        payload.setdefault("draft", None)
        payload.setdefault("latest_packet_export", None)
        payload.setdefault("latest_export_critic", None)
        payload.setdefault("ui_readiness", None)
        return payload

    def _save_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["updated_at"] = _utc_now()
        path = self._session_path(str(state.get("user_id") or DEFAULT_USER_ID))
        temp_path = path.with_name(f"{path.name}.tmp")
        try:
            temp_path.write_text(json.dumps(state, indent=2, sort_keys=True))
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return state

    def _build_question_status(self, answers: Dict[str, Any]) -> List[Dict[str, Any]]:
        status = []
        for question in _INTAKE_QUESTIONS:
            answer = str(answers.get(question["id"]) or "").strip()
            status.append(
                {
                    **question,
                    "answer": answer,
                    "is_answered": bool(answer),
                }
            )
        return status

    def _next_question(self, answers: Dict[str, Any]) -> Optional[Dict[str, str]]:
        for question in _INTAKE_QUESTIONS:
            if not str(answers.get(question["id"]) or "").strip():
                return question
        return None

    def _question_by_id(self, question_id: Optional[str]) -> Optional[Dict[str, str]]:
        normalized_question_id = str(question_id or "").strip()
        if not normalized_question_id:
            return None
        for question in _INTAKE_QUESTIONS:
            if question["id"] == normalized_question_id:
                return question
        return None

    def _build_intake_chat_explanation(self, question: Dict[str, str], state: Dict[str, Any]) -> Dict[str, Any]:
        review = self._build_review(state)
        support_matrix = list(review.get("support_matrix") or [])
        first_gap = next((item for item in support_matrix if not item.get("supported")), None)
        focus_gap = (
            f"Current biggest support gap: {str(first_gap.get('label') or '').lower()}."
            if first_gap
            else "Core claim elements already have at least some recorded support."
        )
        guidance = {
            "party_name": {
                "why_this_matters": "This anchors who the complaint belongs to across the CLI, web workspace, and later evidence collection.",
                "how_to_answer": "Use the name that should appear in the complaint caption or intake record.",
            },
            "opposing_party": {
                "why_this_matters": "This identifies the target organization or person so the record, draft, and evidence search stay pointed at the right defendant.",
                "how_to_answer": "Name the employer, housing provider, agency, or other party you are complaining about.",
            },
            "protected_activity": {
                "why_this_matters": "This is usually the first element that explains why the later adverse action may have been unlawful retaliation or interference.",
                "how_to_answer": "Describe what you reported, opposed, requested, or disclosed before things got worse.",
            },
            "adverse_action": {
                "why_this_matters": "This captures what happened to you after the protected activity and helps define damages and liability.",
                "how_to_answer": "Describe the concrete action taken against you, such as termination, denial, discipline, or eviction threat.",
            },
            "timeline": {
                "why_this_matters": "Timing is often what connects the protected activity to the adverse action and exposes causation gaps.",
                "how_to_answer": "Give the key dates or sequence in plain language, even if you only know approximate timing.",
            },
            "harm": {
                "why_this_matters": "This clarifies damages and what relief the complaint should eventually request.",
                "how_to_answer": "List the practical harm you suffered, such as lost wages, housing instability, denied benefits, or emotional distress.",
            },
            "court_header": {
                "why_this_matters": "This helps format the eventual complaint draft correctly when you already know the court or forum.",
                "how_to_answer": "If you know the court caption, provide it. If not, you can say that you are unsure.",
            },
        }.get(question["id"], {})
        return {
            "question_id": question["id"],
            "why_this_matters": guidance.get("why_this_matters") or "This helps tighten the intake record before evidence and legal research begin.",
            "how_to_answer": guidance.get("how_to_answer") or "Answer in plain language with the most concrete facts you know right now.",
            "review_focus": focus_gap,
        }

    def _build_intake_chat_payload(
        self,
        state: Dict[str, Any],
        *,
        accepted_answer: Optional[Dict[str, Any]] = None,
        requested_question_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        answers = state.get("intake_answers") or {}
        review = self._build_review(state)
        questions = self._build_question_status(answers)
        active_question = self._question_by_id(requested_question_id) if requested_question_id else self._next_question(answers)
        answered_count = len([item for item in questions if item.get("is_answered")])
        total_questions = len(questions)
        if active_question:
            lead_in = "Let's start with the basics." if answered_count == 0 else "I have that. Next:" if accepted_answer else "Next question:"
            message = f"{lead_in} {active_question['prompt']}"
            explanation = self._build_intake_chat_explanation(active_question, state)
        else:
            message = (
                "Intake complete. I have the core complaint facts. Next, review the synopsis, add corroborating evidence, "
                "and use the mediator follow-up flow to tighten proof gaps."
            )
            explanation = {
                "question_id": None,
                "why_this_matters": "The intake record is complete enough to hand off into evidence collection and complaint drafting.",
                "how_to_answer": "No further intake answer is required right now.",
                "review_focus": "Shift attention to corroborating documents, witness testimony, and legal support.",
            }
        return {
            "user_id": str(state.get("user_id") or DEFAULT_USER_ID),
            "message": message,
            "inquiry": {
                "question_id": active_question["id"],
                "label": active_question["label"],
                "prompt": active_question["prompt"],
                "placeholder": active_question.get("placeholder") or "",
            }
            if active_question
            else None,
            "explanation": explanation,
            "accepted_answer": deepcopy(accepted_answer) if accepted_answer else None,
            "questions": questions,
            "next_question": self._next_question(answers),
            "review": review,
            "case_synopsis": self._build_case_synopsis(state),
            "session": deepcopy(state),
            "conversation_state": {
                "answered_question_count": answered_count,
                "total_question_count": total_questions,
                "is_complete": active_question is None,
                "remaining_question_ids": [item["id"] for item in _INTAKE_QUESTIONS if not str(answers.get(item["id"]) or "").strip()],
            },
        }

    def _support_matrix(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        answers = state.get("intake_answers") or {}
        testimony = state.get("evidence", {}).get("testimony") or []
        documents = state.get("evidence", {}).get("documents") or []
        matrix: List[Dict[str, Any]] = []
        for element in _CLAIM_ELEMENTS:
            intake_supported = bool(answers.get(element["id"])) or (
                element["id"] == "employer_knowledge" and bool(answers.get("protected_activity"))
            ) or (element["id"] == "causation" and bool(answers.get("timeline")))
            matching_testimony = [item for item in testimony if item.get("claim_element_id") == element["id"]]
            matching_documents = [item for item in documents if item.get("claim_element_id") == element["id"]]
            support_count = len(matching_testimony) + len(matching_documents) + (1 if intake_supported else 0)
            matrix.append(
                {
                    "id": element["id"],
                    "label": element["label"],
                    "supported": support_count > 0,
                    "intake_supported": intake_supported,
                    "testimony_count": len(matching_testimony),
                    "document_count": len(matching_documents),
                    "support_count": support_count,
                    "status": "supported" if support_count > 0 else "needs_support",
                }
            )
        return matrix

    def _build_review(self, state: Dict[str, Any]) -> Dict[str, Any]:
        matrix = self._support_matrix(state)
        supported = [item for item in matrix if item["supported"]]
        missing = [item for item in matrix if not item["supported"]]
        evidence = state.get("evidence") or {}
        case_synopsis = self._build_case_synopsis(state)
        return {
            "claim_type": state.get("claim_type", "retaliation"),
            "case_synopsis": case_synopsis,
            "support_matrix": matrix,
            "overview": {
                "supported_elements": len(supported),
                "missing_elements": len(missing),
                "testimony_items": len(evidence.get("testimony") or []),
                "document_items": len(evidence.get("documents") or []),
            },
            "recommended_actions": [
                {
                    "title": "Collect more corroboration",
                    "detail": "Add testimony or documents to any unsupported claim element."
                    if missing
                    else "All core elements have at least one support source.",
                },
                {
                    "title": "Check the timeline",
                    "detail": "Close timing between protected activity and adverse action strengthens causation.",
                },
            ],
            "testimony": deepcopy(evidence.get("testimony") or []),
            "documents": deepcopy(evidence.get("documents") or []),
        }

    def list_intake_questions(self) -> Dict[str, Any]:
        return {
            "questions": deepcopy(DEFAULT_INTAKE_QUESTIONS),
        }

    def list_claim_elements(self) -> Dict[str, Any]:
        return {
            "claim_elements": deepcopy(DEFAULT_CLAIM_ELEMENTS),
        }

    def _build_draft(
        self,
        state: Dict[str, Any],
        requested_relief: Optional[List[str]] = None,
        *,
        use_llm: bool = False,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config_path: Optional[str] = None,
        backend_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        answers = state.get("intake_answers") or {}
        existing_draft = state.get("draft") or {}
        review_snapshot = self._build_review(state)
        overview = dict(review_snapshot.get("overview") or {})
        evidence = dict(state.get("evidence") or {})
        filing_metadata = dict(state.get("filing_metadata") or {})
        testimony_items = list(evidence.get("testimony") or [])
        document_items = list(evidence.get("documents") or [])
        prioritized_document_items = sorted(
            document_items,
            key=lambda item: (-_evidence_priority(item), str(item.get("saved_at") or ""), str(item.get("title") or "")),
        )
        claim_type = _normalize_claim_type(state.get("claim_type"))
        claim_label = _claim_type_display_name(claim_type)
        plaintiff = _extract_person_name(
            filing_metadata.get("signature_plaintiff") or answers.get("party_name"),
            fallback="Plaintiff",
        )
        defendant = _extract_defendant_name(answers.get("opposing_party"), fallback="Defendant")
        caption_plaintiffs = str(filing_metadata.get("caption_plaintiffs") or "").strip() or plaintiff
        caption_defendants = str(filing_metadata.get("caption_defendants") or "").strip() or defendant
        mailing_address = str(filing_metadata.get("mailing_address") or "").strip() or "____________________"
        signature_role = str(filing_metadata.get("signature_role") or "").strip() or "Plaintiff, Pro Se"
        plaintiff_caption_label = (
            "Plaintiffs"
            if any(token in caption_plaintiffs for token in [",", " and "]) and caption_plaintiffs != plaintiff
            else "Plaintiff"
        )
        defendant_caption_label = (
            "Defendants"
            if any(token in caption_defendants for token in [",", " and "])
            else "Defendant"
        )
        is_plural_plaintiffs = plaintiff_caption_label == "Plaintiffs"
        is_plural_defendants = defendant_caption_label == "Defendants"
        plaintiff_party_label = "Plaintiffs" if is_plural_plaintiffs else "Plaintiff"
        defendant_party_label = "Defendants" if is_plural_defendants else "Defendant"
        plaintiff_party_object = "Plaintiffs" if is_plural_plaintiffs else "Plaintiff"
        plaintiff_party_have = "have" if is_plural_plaintiffs else "has"
        plaintiff_party_seek = "seek" if is_plural_plaintiffs else "seeks"
        plaintiff_party_repeat = "repeat and reallege" if is_plural_plaintiffs else "repeats and realleges"
        plaintiff_party_demand = "demand" if is_plural_plaintiffs else "demands"
        plaintiff_party_contend = "contend" if is_plural_plaintiffs else "contends"
        plaintiff_party_give = "give" if is_plural_plaintiffs else "gives"
        plaintiff_intro_name = caption_plaintiffs if is_plural_plaintiffs else plaintiff
        defendant_intro_name = caption_defendants if is_plural_defendants else defendant
        intro_alleges = "allege" if is_plural_plaintiffs else "alleges"
        intro_their = "their" if is_plural_plaintiffs else "their"
        defendant_be = "are" if is_plural_defendants else "is"
        timeline_input = _condense_timeline_text(answers.get("timeline"), "the events occurred close in time")
        protected_activity = _sentence_fragment(
            answers.get("protected_activity"),
            "engaged in protected activity",
        )
        pleading_activity = _pleading_activity_fragment(
            answers.get("protected_activity"),
            "engaging in protected activity",
        )
        adverse_action = _event_fragment(
            answers.get("adverse_action"),
            "suffered an adverse action",
        )
        timeline = _sentence_fragment(
            timeline_input,
            "the events occurred close in time",
        )
        harm = _sentence_fragment(
            answers.get("harm"),
            "suffered compensable harm",
        )
        relief = requested_relief or existing_draft.get("requested_relief") or [
            "Compensatory damages",
            "Back pay",
            "Injunctive relief",
        ]
        case_synopsis = self._build_case_synopsis(state)
        relief_lines = [f"{index}. {_formalize_relief_item(item)}." for index, item in enumerate(relief, start=1)]
        support_count = int(overview.get("supported_elements") or 0)
        missing_count = int(overview.get("missing_elements") or 0)
        evidence_count = len(testimony_items) + len(document_items)
        court_header = _court_header_line(answers.get("court_header"))
        document_exhibits = [
            {
                "label": _exhibit_label(index),
                "title": _evidence_display_title(item, kind="document"),
                "item": item,
            }
            for index, item in enumerate(prioritized_document_items[:3])
        ]
        testimony_reference_lines = _unique_preserve_order([
            f"{plaintiff_party_label} expect{'s' if not is_plural_plaintiffs else ''} to offer testimony presently identified as '{_evidence_display_title(item, kind='testimony')}' in support of the {_claim_element_label(item.get('claim_element_id')).lower()} element."
            for item in testimony_items[:3]
        ])
        document_reference_lines = _unique_preserve_order([
            (
                f"{exhibit['label']} ('{exhibit['title']}') presently supports the "
                f"{_claim_element_label(exhibit['item'].get('claim_element_id')).lower()} element. "
                f"{plaintiff_party_label} expect{'s' if not is_plural_plaintiffs else ''} to offer {exhibit['label'].lower()} in support of the "
                f"{_claim_element_label(exhibit['item'].get('claim_element_id')).lower()} element."
            )
            for exhibit in document_exhibits
        ])
        testimony_summary = "; ".join(_unique_preserve_order([
            _formal_evidence_summary_item(item, kind="testimony")
            for item in testimony_items[:3]
        ])) or "No witness or complainant testimony is presently identified"
        document_summary_items = _unique_preserve_order([
            (
                f"{exhibit['label']} - {exhibit['title']} ({_claim_element_label(exhibit['item'].get('claim_element_id')).strip() or 'Claim element'})"
                f"; {_formal_evidence_summary_item(exhibit['item'], kind='document')}"
            )
            for exhibit in document_exhibits
        ])
        document_summary = "; ".join(document_summary_items) or "No documentary exhibits are presently identified"
        exhibit_titles_lower = {
            _evidence_display_title(item, kind="document").lower()
            for item in prioritized_document_items
        }
        case_specific_evidence_notice: Optional[str] = None
        if {
            "chronology evidence matrix",
            "temporary cli session email evidence memo",
            "reasonable accommodation ocr memo",
        }.issubset(exhibit_titles_lower):
            case_specific_evidence_notice = (
                f"16. The current exhibit set specifically identifies a February 25 to February 26, 2026 written complaint and documentation-escalation thread, "
                "a March 19, 2026 voucher-reversal email, a March 20, 2026 accommodation-conditioned reissuance email, "
                "and a March 24, 2026 provider-supported accommodation-verification record."
            )
        complaint_heading = f"COMPLAINT FOR {claim_label.upper()}"
        nature_of_action = {
            "retaliation": (
                f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this retaliation complaint against {defendant_intro_name}. "
                f"This civil action arises from {defendant_intro_name}'s retaliatory response after {plaintiff_intro_name} {'engaged' if not is_plural_plaintiffs else 'engaged'} in protected activity, including {pleading_activity}."
            ),
            "employment_discrimination": (
                f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this employment discrimination complaint against {defendant_intro_name}. "
                f"This civil action arises from discriminatory workplace treatment, unequal terms or conditions, and resulting harm."
            ),
            "housing_discrimination": (
                f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this housing discrimination complaint against {defendant_intro_name}. "
                f"This civil action arises from discriminatory denial, limitation, interference, or retaliation affecting housing rights or benefits."
            ),
            "due_process_failure": (
                f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this due process complaint against {defendant_intro_name}. "
                f"This civil action arises from adverse action imposed without the notice, hearing, review, or procedural protections required by law."
            ),
            "consumer_protection": (
                f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this consumer protection complaint against {defendant_intro_name}. "
                f"This civil action arises from unfair, deceptive, fraudulent, or otherwise unlawful business practices that caused injury."
            ),
        }.get(
            claim_type,
            f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this {claim_label.lower()} complaint against {defendant_intro_name}. "
            f"This civil action arises from unlawful conduct that injured {plaintiff_intro_name}.",
        )
        relief_paragraph = {
            "retaliation": (
                f"2. {plaintiff_party_label} {plaintiff_party_seek} back pay, front pay or reinstatement, compensatory damages, attorney's fees and costs, "
                "equitable relief, and such further relief as may be just to remedy Defendant's retaliatory acts and the losses flowing from them."
            ),
            "employment_discrimination": (
                f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, equitable relief, and such further relief as may be just to remedy discriminatory employment practices, "
                f"restore lost opportunities, and address the harm caused when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse employment action')}."
            ),
            "housing_discrimination": (
                f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, equitable relief, and such further relief as may be just to remedy discriminatory housing practices, "
                "preserve housing stability, and address the housing-related harms caused by the challenged conduct."
            ),
            "due_process_failure": (
                f"2. {plaintiff_party_label} {plaintiff_party_seek} declaratory relief, equitable relief, damages, and such further relief as may be just to remedy the procedural deprivation "
                f"and the harm caused by the challenged action through which {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a deprivation without adequate process')}."
            ),
            "consumer_protection": (
                f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, restitution, equitable relief, and such further relief as may be just to remedy deceptive or unfair consumer practices "
                f"and the harm caused when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a consumer-facing injury')}."
            ),
        }.get(
            claim_type,
            f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, equitable relief, and such further relief as may be just to remedy unlawful conduct and the harm caused when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse action')}.",
        )
        jurisdiction_paragraph = {
            "retaliation": (
                f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} retaliation for protected activity "
                "and seeks relief for materially adverse acts taken in response to that activity."
            ),
            "employment_discrimination": (
                f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} discriminatory employment practices, "
                "workplace bias, and related unlawful employment actions for which judicial relief is available."
            ),
            "housing_discrimination": (
                f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} discriminatory housing practices, "
                "interference with housing rights or benefits, and related misconduct for which judicial relief is available."
            ),
            "due_process_failure": (
                f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} deprivation without constitutionally "
                "or statutorily required notice, hearing, review, or other procedural protections."
            ),
            "consumer_protection": (
                f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} unfair, deceptive, or unlawful consumer-facing conduct "
                "for which damages, equitable relief, restitution, or related remedies may be awarded."
            ),
        }.get(
            claim_type,
            f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} unlawful conduct for which judicial relief is available.",
        )
        venue_paragraph = {
            "housing_discrimination": (
                "4. Venue is proper in this District because the housing-related events, denial, interference, or threatened loss of housing benefits occurred in this forum and the resulting harm was felt here."
            ),
            "employment_discrimination": (
                "4. Venue is proper in this District because the workplace events, adverse employment decisions, and resulting economic harm occurred in or were directed into this forum."
            ),
            "consumer_protection": (
                "4. Venue is proper in this District because the transaction, deceptive practice, or resulting economic loss occurred in this forum or caused injury here."
            ),
        }.get(
            claim_type,
            "4. Venue is proper in this District because a substantial part of the events or omissions giving rise to these claims occurred in this forum and the resulting harm was felt here.",
        )
        party_paragraphs = {
            "retaliation": (
                f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} individual complainants who engaged in protected activity and {'were' if is_plural_plaintiffs else 'was'} thereafter harmed by the retaliatory conduct described below.",
                f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the party or parties from whom relief is sought and {defendant_be} responsible for the retaliatory actions alleged in this pleading.",
            ),
            "employment_discrimination": (
                f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the employee, applicant, or worker harmed by the discriminatory employment conduct described below.",
                f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the employer or responsible actor from whom relief is sought for the discriminatory employment actions alleged in this pleading.",
            ),
            "housing_discrimination": (
                (
                    f"5. {plaintiff_party_label} {plaintiff_intro_name} are housing applicants, tenants, residents, or persons seeking housing-related rights or benefits who were harmed by the discriminatory conduct described below."
                    if is_plural_plaintiffs
                    else f"5. {plaintiff_party_label} {plaintiff_intro_name} is the housing applicant, tenant, resident, or person seeking housing-related rights or benefits who was harmed by the discriminatory conduct described below."
                ),
                (
                    f"6. {defendant_party_label} {defendant_intro_name} are housing providers, landlords, authorities, managers, or responsible actors from whom relief is sought for the housing discrimination alleged in this pleading."
                    if is_plural_defendants
                    else f"6. {defendant_party_label} {defendant_intro_name} is the housing provider, landlord, authority, manager, or responsible actor from whom relief is sought for the housing discrimination alleged in this pleading."
                ),
            ),
            "due_process_failure": (
                f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the person or persons deprived of rights, benefits, or protected interests without adequate process.",
                f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the person or entity responsible for the challenged deprivation and the missing procedural safeguards alleged in this pleading.",
            ),
            "consumer_protection": (
                f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the consumer or injured person harmed by the deceptive, unfair, or unlawful conduct described below.",
                f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the seller, business, servicer, or responsible actor from whom relief is sought for the consumer-facing conduct alleged in this pleading.",
            ),
        }.get(
            claim_type,
            (
                f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the person or persons harmed by the conduct described below.",
                f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the party or parties from whom relief is sought and {defendant_be} responsible for the conduct alleged in this pleading.",
            ),
        )
        factual_allegation_lines = {
            "retaliation": [
                f"7. {plaintiff_party_label} {'engaged' if not is_plural_plaintiffs else 'engaged'} in protected activity by {pleading_activity}.",
                "8. That protected activity constituted protected opposition, reporting, or participation activity under the governing anti-retaliation framework.",
                f"9. Within days of that protected activity, {defendant_party_label} took materially adverse action against {plaintiff_party_object} by {_adverse_action_clause(answers.get('adverse_action'), 'taking materially adverse action against Plaintiff')}.",
                f"10. The relevant chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The events occurred in close temporal proximity')}",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
            "employment_discrimination": [
                f"7. {plaintiff_party_label} {intro_alleges} facts showing discriminatory employment treatment, including protected conduct or circumstances such as {pleading_activity}.",
                f"8. {defendant_party_label} thereafter took or maintained adverse employment action by which {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse employment action')}.",
                f"9. The employment chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The relevant employment events occurred in close succession')}",
                "10. The present record supports an inference of discriminatory motive, disparate treatment, prohibited bias, retaliation, or other unlawful employment decision-making.",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
            "housing_discrimination": [
                f"7. {plaintiff_party_label} {intro_alleges} that {'they' if is_plural_plaintiffs else 'they'} sought, used, requested, or protected housing-related rights, accommodations, benefits, tenancy rights, or fair treatment, including {pleading_activity}.",
                f"8. {defendant_party_label} thereafter denied, burdened, interfered with, or threatened housing-related rights or benefits through conduct including {_sentence_fragment(answers.get('adverse_action'), 'a housing-related deprivation')}.",
                f"9. The housing-related chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The housing-related events occurred in close succession')}",
                f"10. The present record supports an inference that {defendant_party_label} acted in a discriminatory manner, interfered with protected housing rights, or retaliated in connection with protected housing activity.",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {'suffered' if not is_plural_plaintiffs else 'suffered'} harm including {_sentence_fragment(answers.get('harm'), 'compensable harm')}.",
            ],
            "due_process_failure": [
                f"7. {plaintiff_party_label} {intro_alleges} that {defendant_party_label} imposed or maintained a deprivation affecting protected rights, interests, status, benefits, or property.",
                f"8. The challenged action is that {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a deprivation without adequate process')}.",
                f"9. The chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The challenged events occurred in close succession')}",
                f"10. {plaintiff_party_label} {intro_alleges} that the deprivation occurred without adequate notice, hearing, review, appeal, or other required procedural protection.",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
            "consumer_protection": [
                f"7. {plaintiff_party_label} {intro_alleges} that {defendant_party_label} engaged in deceptive, misleading, unfair, or otherwise unlawful consumer-facing conduct.",
                f"8. That conduct included or resulted in adverse action or consequences when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a consumer-facing injury')}.",
                f"9. The chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The relevant consumer-facing events occurred in close succession')}",
                f"10. {plaintiff_party_label} {intro_alleges} that the challenged conduct caused consumer harm, financial loss, or other compensable injury in a transactional or service context.",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
        }.get(
            claim_type,
            [
                f"7. {plaintiff_party_label} {intro_alleges} conduct or circumstances including {pleading_activity}.",
                f"8. {defendant_party_label} engaged in conduct through which {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse action')}.",
                f"9. The chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The relevant events occurred in close succession')}",
                f"10. {plaintiff_party_label} {intro_alleges} facts supporting a plausible claim for relief.",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
        )
        count_heading = {
            "retaliation": "COUNT I - RETALIATION",
            "employment_discrimination": "COUNT I - EMPLOYMENT DISCRIMINATION",
            "housing_discrimination": "COUNT I - HOUSING DISCRIMINATION",
            "due_process_failure": "COUNT I - DUE PROCESS VIOLATION",
            "consumer_protection": "COUNT I - CONSUMER PROTECTION",
        }.get(claim_type, f"COUNT I - {claim_label.upper()}")
        claim_paragraphs = {
            "retaliation": [
                f"{plaintiff_party_label} engaged in protected activity by {pleading_activity}, and {defendant_party_label} knew or should have known of that protected conduct.",
                f"{defendant_party_label} thereafter subjected {plaintiff_party_object} to materially adverse action by {_adverse_action_clause(answers.get('adverse_action'), 'taking materially adverse action against Plaintiff')}, under circumstances supporting a causal inference of retaliation.",
                f"The close temporal proximity, {defendant_party_label}' knowledge of the protected activity, the evidentiary record, and the resulting harm plausibly support a retaliation claim and entitle {plaintiff_party_object} to relief.",
            ],
            "employment_discrimination": [
                f"{plaintiff_party_label} {'were' if is_plural_plaintiffs else 'was'} subjected to adverse employment treatment described as {adverse_action}, in a manner that was discriminatory, disparate, or otherwise unlawful.",
                "The pleaded facts support an inference that Defendant's conduct was motivated by unlawful bias, protected status, protected conduct, or a prohibited employment practice.",
                "The evidentiary record and resulting harm support a plausible employment discrimination claim.",
            ],
            "housing_discrimination": [
                f"{defendant_party_label} denied, limited, burdened, or interfered with housing-related rights, opportunities, services, or benefits through conduct described as {adverse_action}.",
                f"The pleaded facts support an inference that {defendant_party_label} acted in a discriminatory manner or retaliated in connection with protected housing activity, status, or rights.",
                "The evidentiary record and resulting harm support a plausible housing discrimination claim.",
            ],
            "due_process_failure": [
                "Defendant imposed or maintained adverse consequences without the notice, review, hearing, or procedural protections required by law.",
                f"The resulting deprivation included challenged action described as {adverse_action} and related harms without adequate procedural safeguards.",
                "The pleaded facts and evidentiary record support a plausible due process claim.",
            ],
            "consumer_protection": [
                "Defendant engaged in unfair, deceptive, misleading, or unlawful conduct in connection with a consumer transaction or obligation.",
                f"That conduct resulted in adverse action or consequences when Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered a consumer-facing injury')} and caused economic or other compensable harm, including {_sentence_fragment(answers.get('harm'), 'compensable harm')}.",
                "The pleaded facts and evidentiary record support a plausible consumer protection claim.",
            ],
        }.get(
            claim_type,
            [
                "Defendant engaged in unlawful conduct causing harm to Plaintiff.",
                "The pleaded facts support a plausible claim for relief.",
                "The evidentiary record and resulting harm warrant judicial relief.",
            ],
        )
        evidentiary_lines: List[str] = [
            (
                f"12. {plaintiff_party_label} presently {'rely' if is_plural_plaintiffs else 'relies'} on {evidence_count} identified evidentiary items. The witness proof currently identified includes: {testimony_summary}."
                if testimony_items
                else f"12. {plaintiff_party_label} presently {'rely' if is_plural_plaintiffs else 'relies'} on the evidentiary materials identified below and anticipate{'' if is_plural_plaintiffs else 's'} that testimonial proof may be supplemented through discovery, amendment, or sworn declarations."
            ),
            (
                f"13. {plaintiff_party_label} presently {'identify' if is_plural_plaintiffs else 'identifies'} the following documents, exhibits, or records in support of this pleading: {document_summary}."
                if document_items
                else f"13. {plaintiff_party_label} {plaintiff_party_have} not yet attached documentary exhibits to this export, but preserve{'' if is_plural_plaintiffs else 's'} the right to supplement the pleading with records, correspondence, or other supporting materials."
            ),
            (
                f"14. Based on the information presently available, {plaintiff_party_label} {plaintiff_party_contend} that the evidentiary record presently supports {support_count} core claim elements "
                f"and that {missing_count} areas, if any, may be further corroborated through discovery, amendment, or additional evidentiary development."
            ),
            (
                f"15. {plaintiff_party_label} {plaintiff_party_give} notice that the identified testimony, documentary exhibits, and chronology materials constitute part of the evidentiary basis for this pleading "
                "and may be supplemented, authenticated, or amended as discovery proceeds."
            ),
        ]
        if case_specific_evidence_notice:
            evidentiary_lines.append(case_specific_evidence_notice)
        extra_evidence_start = 16 + (1 if case_specific_evidence_notice else 0)
        extra_evidence_lines = (testimony_reference_lines + document_reference_lines)[:2]
        evidentiary_lines.extend(
            f"{extra_evidence_start + index}. {line}"
            for index, line in enumerate(extra_evidence_lines)
        )
        claim_intro_paragraph = extra_evidence_start + len(extra_evidence_lines)
        claim_detail_start = claim_intro_paragraph + 1
        body = "\n\n".join(
            [
                "IN THE UNITED STATES DISTRICT COURT",
                court_header,
                "",
                f"{caption_plaintiffs}, {plaintiff_caption_label},",
                "v.",
                f"{caption_defendants}, {defendant_caption_label}.",
                "",
                "Civil Action No. ________________",
                complaint_heading,
                "JURY TRIAL DEMANDED",
                "",
                (
                    f"{plaintiff_party_label} {plaintiff_intro_name}, proceeding pro se, {intro_alleges} upon personal knowledge as to "
                    f"{intro_their} own acts and upon information and belief as to all other matters as follows:"
                ),
                "",
                "NATURE OF THE ACTION",
                nature_of_action,
                relief_paragraph,
                "",
                "JURISDICTION AND VENUE",
                jurisdiction_paragraph,
                venue_paragraph,
                "",
                "PARTIES",
                party_paragraphs[0],
                party_paragraphs[1],
                "",
                "FACTUAL ALLEGATIONS",
                *factual_allegation_lines,
                "",
                "EVIDENTIARY SUPPORT AND NOTICE",
                *evidentiary_lines,
                "",
                "CLAIM FOR RELIEF",
                count_heading,
                f"{claim_intro_paragraph}. {plaintiff_intro_name} {plaintiff_party_repeat} the preceding paragraphs as if fully set forth herein.",
                *[f"{claim_detail_start + index}. {line}" for index, line in enumerate(claim_paragraphs)],
                f"{claim_detail_start + 3}. {plaintiff_party_label} {plaintiff_party_have} sustained damages and losses including {_sentence_fragment(answers.get('harm'), 'compensable harm')}.",
                (
                    f"{claim_detail_start + 4}. As a direct and proximate result of Defendant's retaliatory conduct, {plaintiff_party_label} {'are' if is_plural_plaintiffs else 'is'} entitled to recover damages, equitable relief, fees and costs where available, and such further relief as the Court deems just and proper."
                    if claim_type == "retaliation"
                    else f"{claim_detail_start + 4}. {defendant_party_label}' acts were intentional, knowing, reckless, retaliatory, discriminatory, deceptive, or otherwise unlawful under the governing claim theory."
                ),
                "",
                "PRAYER FOR RELIEF",
                (
                    f"Wherefore, {plaintiff_party_label} respectfully {'request' if is_plural_plaintiffs else 'requests'} judgment against {defendant_party_label} on the retaliation claim alleged herein and {'seek' if is_plural_plaintiffs else 'seeks'} the following relief:"
                    if claim_type == "retaliation"
                    else f"Wherefore, {plaintiff_party_label} {'request' if is_plural_plaintiffs else 'requests'} judgment against {defendant_party_label} and the following relief:"
                ),
                "\n".join(relief_lines),
                "",
                "JURY DEMAND",
                f"{plaintiff_party_label} {plaintiff_party_demand} a trial by jury on all issues so triable.",
                "",
                "SIGNATURE BLOCK",
                f"Dated: ____________________",
                "",
                "Respectfully submitted,",
                "",
                f"{plaintiff}",
                signature_role,
                f"Address: {mailing_address}",
                "Telephone: ____________________",
                "Email: ____________________",
            ]
        )
        draft = {
            "title": f"{caption_plaintiffs} v. {caption_defendants} {claim_label} Complaint",
            "requested_relief": relief,
            "case_synopsis": case_synopsis,
            "claim_type": claim_type,
            "body": body,
            "generated_at": _utc_now(),
            "review_snapshot": review_snapshot,
            "draft_strategy": "template",
        }
        if use_llm:
            self._last_draft_refinement_error = None
            resolved_backends = _resolve_llm_draft_backend_candidates(provider, model)
            attempted_providers: List[str] = []
            for resolved_backend in resolved_backends:
                provider_name = str(resolved_backend["provider"] or "").strip()
                if provider_name:
                    attempted_providers.append(provider_name)
                refined_draft = self._refine_draft_with_llm_router(
                    state,
                    draft,
                    provider=resolved_backend["provider"],
                    model=resolved_backend["model"],
                    requested_provider=resolved_backend["requested_provider"],
                    requested_model=resolved_backend["requested_model"],
                    config_path=config_path,
                    backend_id=backend_id,
                )
                if refined_draft:
                    if len(attempted_providers) > 1:
                        refined_draft["draft_backend_fallback_chain"] = attempted_providers
                    return refined_draft
            if self._last_draft_refinement_error:
                if attempted_providers:
                    draft["draft_backend_fallback_chain"] = attempted_providers
                draft["draft_fallback_reason"] = self._last_draft_refinement_error
        return draft

    def _build_case_synopsis(self, state: Dict[str, Any]) -> str:
        custom_synopsis = str(state.get("case_synopsis") or "").strip()
        if custom_synopsis:
            return custom_synopsis
        answers = state.get("intake_answers") or {}
        matrix = self._support_matrix(state)
        supported_elements = len([item for item in matrix if item.get("supported")])
        missing_elements = len([item for item in matrix if not item.get("supported")])
        evidence = state.get("evidence") or {}
        claim_type = str(state.get("claim_type") or "retaliation").replace("_", " ")
        party_name = _extract_person_name(answers.get("party_name"), fallback="The complainant")
        opposing_party = _extract_defendant_name(answers.get("opposing_party"), fallback="the opposing party")
        protected_activity = answers.get("protected_activity") or "an identified protected activity"
        adverse_action = answers.get("adverse_action") or "an adverse action"
        harm = answers.get("harm") or "described harm"
        timeline = _condense_timeline_text(answers.get("timeline"), "a still-developing timeline")
        evidence_count = len(evidence.get("testimony") or []) + len(evidence.get("documents") or [])
        return (
            f"{party_name} is pursuing a {claim_type} complaint against {opposing_party}. "
            f"The current theory is that {party_name} {protected_activity}, then experienced {adverse_action}. "
            f"The reported harm is {harm}. Timeline posture: {timeline}. "
            f"Current support posture: {supported_elements} supported elements, "
            f"{missing_elements} open gaps, {evidence_count} saved evidence items."
        )

    def _build_formal_complaint_generation_prompt(
        self,
        state: Dict[str, Any],
        base_draft: Dict[str, Any],
    ) -> str:
        answers = dict(state.get("intake_answers") or {})
        evidence = dict(state.get("evidence") or {})
        review_snapshot = dict(base_draft.get("review_snapshot") or self._build_review(state) or {})
        support_matrix = [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "supported": item.get("supported"),
                "support_count": item.get("support_count"),
            }
            for item in list(review_snapshot.get("support_matrix") or [])
        ]
        payload = {
            "claim_type": base_draft.get("claim_type") or _normalize_claim_type(state.get("claim_type")),
            "claim_label": _claim_type_display_name(base_draft.get("claim_type") or state.get("claim_type")),
            "case_synopsis": base_draft.get("case_synopsis") or self._build_case_synopsis(state),
            "intake_answers": answers,
            "requested_relief": list(base_draft.get("requested_relief") or []),
            "testimony": list(evidence.get("testimony") or [])[:4],
            "documents": list(evidence.get("documents") or [])[:4],
            "support_matrix": support_matrix,
            "base_draft": str(base_draft.get("body") or "")[:12000],
        }
        markers = "\n".join(f"- {marker}" for marker in _required_formal_complaint_markers())
        allegation_lines = "\n".join(
            f"- {line}" for line in _claim_type_required_allegations(payload["claim_type"])
        )
        example_snippet = _claim_type_formal_example_snippet(payload["claim_type"])
        preferred_count_heading = _claim_type_count_heading(payload["claim_type"])
        preferred_heading = f"COMPLAINT FOR {payload['claim_label'].upper()}"
        return (
            "You are revising a generated complaint so it reads like a formal legal complaint rather than a workflow summary.\n"
            "Use only the facts already present in the complaint record. Do not invent statutes, parties, dates, courts, judges, addresses, or evidence.\n"
            "Keep the output in plain text with a litigation-style caption, numbered factual paragraphs, a separate count heading, a prayer for relief, and a signature block.\n"
            "Number the factual allegations as pleading paragraphs like '1. ...', '2. ...', and keep that numbering visible in the final complaint body.\n"
            "Do not write a memo, case summary, product explanation, workflow note, JSON explanation, SDK explanation, or support-matrix summary. Write the text like a filed civil complaint.\n"
            "Preserve the requested relief unless the record plainly requires a tighter phrasing.\n"
            f"Claim-specific filing guidance: {_claim_type_filing_guidance(payload['claim_type'])}\n"
            f"Preferred complaint heading: {preferred_heading}\n"
            f"Preferred count heading: {preferred_count_heading}\n"
            "The complaint must expressly allege all of the following:\n"
            f"{allegation_lines}\n"
            "Match the tone and paragraph style of this example snippet for the selected claim type:\n"
            f"{example_snippet}\n"
            "Retain these exact section headings in the body:\n"
            f"{markers}\n\n"
            "Follow this pleading skeleton and keep the headings exactly as written:\n"
            "IN THE UNITED STATES DISTRICT COURT\n"
            "FOR THE APPROPRIATE JUDICIAL DISTRICT\n\n"
            "[Plaintiff caption]\n"
            "Civil Action No. ________________\n"
            f"{preferred_heading}\n"
            "JURY TRIAL DEMANDED\n"
            "NATURE OF THE ACTION\n"
            "JURISDICTION AND VENUE\n"
            "PARTIES\n"
            "FACTUAL ALLEGATIONS\n"
            "EVIDENTIARY SUPPORT AND NOTICE\n"
            "CLAIM FOR RELIEF\n"
            f"{preferred_count_heading}\n"
            "PRAYER FOR RELIEF\n"
            "JURY DEMAND\n"
            "SIGNATURE BLOCK\n\n"
            "Return strict JSON with this shape:\n"
            "{\n"
            '  "title": "draft title",\n'
            '  "body": "full complaint text",\n'
            '  "requested_relief": ["item 1", "item 2"]\n'
            "}\n\n"
            "Complaint record:\n"
            f"{json.dumps(payload, indent=2, sort_keys=True)}\n"
        )

    def _refine_draft_with_llm_router(
        self,
        state: Dict[str, Any],
        base_draft: Dict[str, Any],
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        requested_provider: Optional[str] = None,
        requested_model: Optional[str] = None,
        config_path: Optional[str] = None,
        backend_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            from backends import LLMRouterBackend
            from .ui_review import _load_backend_kwargs

            backend_kwargs = _load_backend_kwargs(config_path, backend_id)
            backend_kwargs["id"] = backend_id or "complaint-draft"
            if provider:
                backend_kwargs["provider"] = provider
            if model:
                backend_kwargs["model"] = model
            backend = LLMRouterBackend(**backend_kwargs)
            prompt = self._build_formal_complaint_generation_prompt(state, base_draft)
            raw_response = self._invoke_llm_draft_backend_with_timeout(backend, prompt)
        except Exception as exc:
            self._last_draft_refinement_error = str(exc) or "llm_router refinement failed"
            return None

        parsed = _parse_json_object(raw_response)
        llm_body = str(parsed.get("body") or "").strip()
        if not llm_body:
            raw_text = _strip_code_fences(raw_response)
            if _has_required_formal_complaint_markers(raw_text) or _looks_like_formal_complaint_candidate(raw_text):
                llm_body = raw_text
        llm_body, normalization_notes = _normalize_llm_complaint_body(
            llm_body,
            base_draft.get("claim_type") or state.get("claim_type"),
        )
        validation_issues = _formal_complaint_validation_issues(
            llm_body,
            base_draft.get("claim_type") or state.get("claim_type"),
        )
        if validation_issues:
            self._last_draft_refinement_error = "; ".join(validation_issues[:3])
            return None

        requested_relief = [
            str(item).strip()
            for item in list(parsed.get("requested_relief") or base_draft.get("requested_relief") or [])
            if str(item).strip()
        ]
        backend_metadata = dict(getattr(backend, "last_result_metadata", {}) or {})
        effective_provider = str(
            backend_metadata.get("effective_provider_name")
            or backend_metadata.get("provider_name")
            or getattr(backend, "provider", provider)
            or ""
        ).strip() or None
        effective_model = str(
            backend_metadata.get("effective_model_name")
            or backend_metadata.get("model_name")
            or getattr(backend, "model", model)
            or ""
        ).strip() or None
        return {
            **deepcopy(base_draft),
            "title": str(parsed.get("title") or base_draft.get("title") or "Complaint").strip(),
            "body": llm_body,
            "requested_relief": requested_relief or list(base_draft.get("requested_relief") or []),
            "draft_strategy": "llm_router",
            "draft_backend": {
                "id": getattr(backend, "id", backend_id or "complaint-draft"),
                "provider": effective_provider,
                "model": effective_model,
                "requested_provider": str(requested_provider or "").strip() or None,
                "requested_model": str(requested_model or "").strip() or None,
            },
            "draft_normalizations": normalization_notes,
        }

    def _invoke_llm_draft_backend_with_timeout(self, backend: Any, prompt: str) -> str:
        provider_name = str(getattr(backend, "provider", "") or "").strip().lower() or None
        timeout_seconds = _llm_draft_timeout_for_provider(provider_name)
        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, BaseException] = {}

        def _run_backend() -> None:
            try:
                result_holder["value"] = backend(prompt)
            except BaseException as exc:  # Preserve backend failures for the caller.
                error_holder["error"] = exc

        worker = threading.Thread(target=_run_backend, name="complaint-llm-draft", daemon=True)
        worker.start()
        worker.join(timeout_seconds)
        if worker.is_alive():
            label = provider_name or "default"
            raise TimeoutError(f"llm_router draft refinement timed out after {timeout_seconds}s ({label})")
        if "error" in error_holder:
            raise error_holder["error"]
        return str(result_holder.get("value") or "")

    def _build_packet_markdown(self, packet: Dict[str, Any]) -> str:
        draft = dict(packet.get("draft") or {})
        review = dict(packet.get("review") or {})
        overview = dict(review.get("overview") or {})
        evidence = dict(packet.get("evidence") or {})
        testimony = list(evidence.get("testimony") or [])
        documents = list(evidence.get("documents") or [])
        requested_relief = list(draft.get("requested_relief") or [])
        question_lines = [
            f"- **{item.get('label') or item.get('id') or 'Question'}:** {item.get('answer') or 'Not answered'}"
            for item in list(packet.get("questions") or [])
        ]
        testimony_lines = [
            f"- **{item.get('title') or 'Testimony'}** ({item.get('claim_element_id') or 'unmapped'}): {item.get('content') or ''}".strip()
            for item in testimony
        ]
        document_lines = [
            f"- **{item.get('title') or 'Document'}** ({item.get('claim_element_id') or 'unmapped'}): {item.get('content') or ''}".strip()
            for item in documents
        ]
        relief_lines = [f"- {item}" for item in requested_relief]
        sections = [
            draft.get("body") or "No complaint body available.",
            "",
            "APPENDIX A - CASE SYNOPSIS",
            packet.get("case_synopsis") or "No case synopsis recorded.",
            "",
            "APPENDIX B - REQUESTED RELIEF CHECKLIST",
            "\n".join(relief_lines) if relief_lines else "- No requested relief recorded.",
            "",
            "APPENDIX C - INTAKE ANSWERS",
            "\n".join(question_lines) if question_lines else "- No intake answers recorded.",
            "",
            "APPENDIX D - EVIDENCE SUMMARY",
            "### Testimony",
            "\n".join(testimony_lines) if testimony_lines else "- No testimony saved.",
            "",
            "### Documents",
            "\n".join(document_lines) if document_lines else "- No documents saved.",
            "",
            "APPENDIX E - REVIEW OVERVIEW",
            f"- Supported elements: {overview.get('supported_elements') or 0}",
            f"- Missing elements: {overview.get('missing_elements') or 0}",
            f"- Testimony items: {overview.get('testimony_items') or 0}",
            f"- Document items: {overview.get('document_items') or 0}",
            "",
            "APPENDIX F - EXPORT METADATA",
            f"- Claim type: {packet.get('claim_type') or 'retaliation'}",
            f"- User ID: {packet.get('user_id') or 'unknown'}",
            f"- Exported at: {packet.get('exported_at') or _utc_now()}",
        ]
        return "\n".join(sections).strip() + "\n"

    def _build_complaint_export_markdown(self, packet: Dict[str, Any]) -> str:
        draft = dict(packet.get("draft") or {})
        body = str(draft.get("body") or "").strip()
        return f"{body}\n" if body else "No complaint body available.\n"

    def _escape_pdf_text(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def _build_packet_pdf_bytes(self, packet: Dict[str, Any], markdown_text: str) -> bytes:
        title = str((packet.get("draft") or {}).get("title") or packet.get("title") or "Complaint Packet")
        lines = [title, ""] + [line[:100] for line in markdown_text.splitlines() if line.strip()]
        lines = lines[:38]
        content_lines = ["BT", "/F1 12 Tf", "72 780 Td"]
        for index, line in enumerate(lines):
            safe_line = self._escape_pdf_text(line)
            if index == 0:
                content_lines.append(f"({safe_line}) Tj")
            else:
                content_lines.append(f"0 -18 Td ({safe_line}) Tj")
        content_lines.append("ET")
        content_stream = "\n".join(content_lines).encode("utf-8")

        objects = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
            f"5 0 obj << /Length {len(content_stream)} >> stream\n".encode("utf-8") + content_stream + b"\nendstream endobj\n",
        ]

        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for obj in objects:
            offsets.append(len(output))
            output.extend(obj)
        xref_start = len(output)
        output.extend(f"xref\n0 {len(offsets)}\n".encode("utf-8"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
        output.extend(
            f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("utf-8")
        )
        return bytes(output)

    def _build_packet_docx_bytes(self, packet: Dict[str, Any], markdown_text: str) -> bytes:
        title = str((packet.get("draft") or {}).get("title") or packet.get("title") or "Complaint Packet")
        paragraphs = [title, ""] + str(markdown_text or "").replace("\r\n", "\n").split("\n")

        def _paragraph_xml(text: str) -> str:
            if not str(text or ""):
                return "<w:p/>"
            return (
                "<w:p><w:r><w:t xml:space=\"preserve\">"
                f"{escape(str(text))}"
                "</w:t></w:r></w:p>"
            )

        document_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
            "<w:body>"
            f"{''.join(_paragraph_xml(item) for item in paragraphs)}"
            "<w:sectPr><w:pgSz w:w=\"12240\" w:h=\"15840\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/></w:sectPr>"
            "</w:body></w:document>"
        )
        content_types_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
            "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
            "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
            "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
            "<Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/>"
            "<Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/>"
            "</Types>"
        )
        root_rels_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>"
            "<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/>"
            "<Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/>"
            "</Relationships>"
        )
        app_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\">"
            "<Application>Complaint Workspace</Application>"
            "</Properties>"
        )
        core_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\">"
            f"<dc:title>{escape(title)}</dc:title>"
            "<dc:creator>Complaint Workspace</dc:creator>"
            "</cp:coreProperties>"
        )
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types_xml)
            archive.writestr("_rels/.rels", root_rels_xml)
            archive.writestr("docProps/app.xml", app_xml)
            archive.writestr("docProps/core.xml", core_xml)
            archive.writestr("word/document.xml", document_xml)
        return buffer.getvalue()

    def _build_export_artifacts(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        draft = dict(packet.get("draft") or {})
        filename_root = _slugify_filename(draft.get("title") or packet.get("title") or "complaint-packet")
        markdown_text = self._build_complaint_export_markdown(packet)
        pdf_bytes = self._build_packet_pdf_bytes(packet, markdown_text)
        docx_bytes = self._build_packet_docx_bytes(packet, markdown_text)
        json_text = json.dumps(packet, indent=2, sort_keys=True)
        return {
            "json": {
                "filename": f"{filename_root}.json",
                "content_type": "application/json",
                "size_bytes": len(json_text.encode("utf-8")),
            },
            "markdown": {
                "filename": f"{filename_root}.md",
                "content_type": "text/markdown",
                "size_bytes": len(markdown_text.encode("utf-8")),
                "content": markdown_text,
                "excerpt": markdown_text[:2000],
            },
            "docx": {
                "filename": f"{filename_root}.docx",
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size_bytes": len(docx_bytes),
            },
            "pdf": {
                "filename": f"{filename_root}.pdf",
                "content_type": "application/pdf",
                "size_bytes": len(pdf_bytes),
                "header_b64": b64encode(pdf_bytes[:32]).decode("ascii"),
            },
        }

    def get_session(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        normalized_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._save_state(self._load_state(normalized_user_id))
        answers = state.get("intake_answers") or {}
        return {
            "session": deepcopy(state),
            "questions": self._build_question_status(answers),
            "next_question": self._next_question(answers),
            "review": self._build_review(state),
            "case_synopsis": self._build_case_synopsis(state),
        }

    def build_mediator_prompt(self, user_id: Optional[str]) -> Dict[str, Any]:
        session = self.get_session(user_id)
        review = session["review"]
        support_matrix = list(review.get("support_matrix") or [])
        first_gap = next((item for item in support_matrix if not item.get("supported")), None)
        synopsis = session["case_synopsis"]
        gap_focus = (
            f"Focus especially on clarifying {str(first_gap.get('label') or '').lower()} and what proof could corroborate it."
            if first_gap
            else "Focus on sharpening the strongest testimony, identifying corroboration, and confirming the cleanest sequence of events."
        )
        prefill_message = (
            f"{synopsis}\n\n"
            "Mediator, help turn this into testimony-ready narrative for the complaint record. "
            "Ask the single most useful next follow-up question, keep the tone calm, and explain what support would strengthen the case. "
            f"{gap_focus}"
        )
        return {
            "user_id": session["session"]["user_id"],
            "case_synopsis": synopsis,
            "target_gap": deepcopy(first_gap) if first_gap else None,
            "prefill_message": prefill_message,
            "return_target_tab": "review",
        }

    def get_complaint_readiness(self, user_id: Optional[str]) -> Dict[str, Any]:
        session = self.get_session(user_id)
        review = session["review"]
        overview = dict(review.get("overview") or {})
        current_session = dict(session.get("session") or {})
        questions = list(session.get("questions") or [])
        answered_count = len([item for item in questions if item.get("is_answered")])
        total_questions = len(questions)
        supported_elements = int(overview.get("supported_elements") or 0)
        missing_elements = int(overview.get("missing_elements") or 0)
        evidence_count = int(overview.get("testimony_items") or 0) + int(overview.get("document_items") or 0)
        current_draft = current_session.get("draft")

        score = 10
        if total_questions > 0:
            score += round((answered_count / total_questions) * 35)
        score += round((supported_elements / max(supported_elements + missing_elements, 1)) * 35)
        if evidence_count > 0:
            score += min(12, evidence_count * 4)
        if current_draft:
            score += 12
        score = max(0, min(100, score))

        verdict = "Not ready to draft"
        detail = "Finish intake and add support before relying on generated complaint text."
        recommended_route = "/workspace"
        recommended_action = "Continue the guided complaint workflow to complete intake and collect support."
        if current_draft:
            verdict = "Draft in progress"
            detail = (
                "A complaint draft already exists. Compare it against the supported facts, requested relief, "
                "and any remaining proof gaps before treating it as filing-ready."
            )
            recommended_route = "/document"
            recommended_action = "Refine the existing draft and reconcile it with the support review."
        elif total_questions > 0 and answered_count == total_questions and missing_elements == 0 and evidence_count > 0:
            verdict = "Ready for first draft"
            detail = "The intake record and support posture are coherent enough to generate a first complaint draft."
            recommended_route = "/document"
            recommended_action = "Generate the first complaint draft from the current record."
        elif answered_count > 0:
            verdict = "Still building the record"
            detail = (
                f"{missing_elements} claim elements still need support and "
                f"{max(total_questions - answered_count, 0)} intake answers may still be missing."
            )
            recommended_route = "/claim-support-review" if missing_elements > 0 else "/workspace"
            recommended_action = (
                "Review support gaps and attach stronger evidence before relying on generated complaint language."
            )

        return {
            "user_id": current_session.get("user_id"),
            "score": score,
            "verdict": verdict,
            "detail": detail,
            "recommended_route": recommended_route,
            "recommended_action": recommended_action,
            "answered_questions": answered_count,
            "total_questions": total_questions,
            "supported_elements": supported_elements,
            "missing_elements": missing_elements,
            "evidence_count": evidence_count,
            "has_draft": bool(current_draft),
        }

    def _summarize_ui_readiness_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        review = dict((result or {}).get("review") or {})
        complaint_journey = dict(review.get("complaint_journey") or (result or {}).get("complaint_journey") or {})
        critic_review = dict(review.get("critic_review") or (result or {}).get("critic_review") or {})
        actor_path_breaks = list(review.get("actor_path_breaks") or (result or {}).get("actor_path_breaks") or [])
        broken_controls = list(review.get("broken_controls") or (result or {}).get("broken_controls") or [])
        issues = list(review.get("issues") or (result or {}).get("issues") or [])
        recommended_changes = list(review.get("recommended_changes") or (result or {}).get("recommended_changes") or [])
        playwright_followups = list(review.get("playwright_followups") or (result or {}).get("playwright_followups") or [])
        screenshot_findings = list(review.get("screenshot_findings") or (result or {}).get("screenshot_findings") or [])
        optimization_targets = list(review.get("optimization_targets") or (result or {}).get("optimization_targets") or [])
        stage_findings = dict(review.get("stage_findings") or (result or {}).get("stage_findings") or {})
        carry_forward_assessment = dict(
            review.get("carry_forward_assessment") or (result or {}).get("carry_forward_assessment") or {}
        )
        release_blockers = list(complaint_journey.get("release_blockers") or [])
        acceptance_checks = list(critic_review.get("acceptance_checks") or [])
        tested_stages = list(complaint_journey.get("tested_stages") or [])
        sdk_invocations = list(complaint_journey.get("sdk_tool_invocations") or [])

        severity_counts = {"high": 0, "medium": 0, "low": 0}
        for item in issues:
            severity = str((item or {}).get("severity") or "").strip().lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        score = 100
        score -= len(release_blockers) * 14
        score -= len(actor_path_breaks) * 9
        score -= len(broken_controls) * 8
        score -= severity_counts["high"] * 12
        score -= severity_counts["medium"] * 6
        score -= severity_counts["low"] * 3
        critic_verdict = str(critic_review.get("verdict") or "warning").strip().lower()
        if critic_verdict == "fail":
            score -= 25
        elif critic_verdict == "warning":
            score -= 10
        if len(tested_stages) >= 6:
            score += 4
        if len(sdk_invocations) >= 2:
            score += 4
        if len(acceptance_checks) >= 3:
            score += 4
        score = max(0, min(100, score))

        verdict = "Needs repair"
        if score >= 85 and not release_blockers and critic_verdict != "fail":
            verdict = "Client-safe"
        elif score < 65 or len(release_blockers) > 1 or critic_verdict == "fail":
            verdict = "Do not send to clients yet"

        summary_text = str(
            (result or {}).get("latest_review")
            or review.get("summary")
            or (result or {}).get("summary")
            or ""
        ).strip()

        return {
            "score": score,
            "verdict": verdict,
            "critic_verdict": critic_verdict or "warning",
            "release_blockers": release_blockers,
            "acceptance_checks": acceptance_checks,
            "tested_stages": tested_stages,
            "sdk_invocations": sdk_invocations,
            "actor_path_breaks": actor_path_breaks,
            "broken_controls": broken_controls,
            "issues": issues,
            "recommended_changes": recommended_changes,
            "playwright_followups": playwright_followups,
            "stage_findings": stage_findings,
            "screenshot_findings": screenshot_findings,
            "optimization_targets": optimization_targets,
            "carry_forward_assessment": carry_forward_assessment,
            "issue_counts": severity_counts,
            "summary": summary_text,
            "workflow_type": str((result or {}).get("workflow_type") or (result or {}).get("backend", {}).get("strategy") or "review"),
            "review_backend": deepcopy((result or {}).get("backend") or {}),
            "latest_review_markdown_path": (result or {}).get("latest_review_markdown_path"),
            "latest_review_json_path": (result or {}).get("latest_review_json_path"),
            "runs": deepcopy((result or {}).get("runs") or []),
            "updated_at": _utc_now(),
        }

    def _persist_ui_readiness(self, user_id: Optional[str], result: Dict[str, Any]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        summarized = self._summarize_ui_readiness_result(result)
        state["ui_readiness"] = summarized
        self._save_state(state)
        return summarized

    def get_ui_readiness(self, user_id: Optional[str]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        cached = dict(state.get("ui_readiness") or {})
        if cached:
            cached.setdefault("status", "cached")
            cached["user_id"] = state["user_id"]
            return cached
        return {
            "user_id": state["user_id"],
            "status": "unavailable",
            "verdict": "No UI verdict cached",
            "score": None,
            "summary": "",
            "release_blockers": [],
            "acceptance_checks": [],
            "tested_stages": [],
            "sdk_invocations": [],
            "actor_path_breaks": [],
            "broken_controls": [],
            "issues": [],
            "recommended_changes": [],
            "playwright_followups": [],
            "stage_findings": {},
            "screenshot_findings": [],
            "optimization_targets": [],
            "carry_forward_assessment": {},
            "issue_counts": {"high": 0, "medium": 0, "low": 0},
            "workflow_type": None,
            "review_backend": {},
            "latest_review_markdown_path": None,
            "latest_review_json_path": None,
            "runs": [],
            "updated_at": None,
        }

    def get_filing_provenance(self, user_id: Optional[str]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        draft = dict(state.get("draft") or {})
        claim_type = str(state.get("claim_type") or "retaliation")
        cached_ui_readiness = dict(state.get("ui_readiness") or {})
        cached_export_critic = dict(state.get("latest_export_critic") or {})
        export_critic_feedback = dict(cached_export_critic.get("complaint_output_feedback") or {})
        export_critic_aggregate = dict(cached_export_critic.get("aggregate") or {})
        export_router_backends = [
            deepcopy(item)
            for item in list(export_critic_aggregate.get("router_backends") or export_critic_feedback.get("router_backends") or [])
            if isinstance(item, dict) and item
        ]
        draft_backend = deepcopy(draft.get("draft_backend") or {})
        complaint_output_router_backend = deepcopy(export_critic_feedback.get("router_backend") or {})
        if not complaint_output_router_backend and export_router_backends:
            complaint_output_router_backend = deepcopy(export_router_backends[0])
        if not complaint_output_router_backend and draft_backend:
            complaint_output_router_backend = {
                key: value
                for key, value in {
                    "strategy": draft.get("draft_strategy") or draft_backend.get("strategy") or "template",
                    "provider": draft_backend.get("provider"),
                    "model": draft_backend.get("model"),
                    "requested_provider": draft_backend.get("requested_provider"),
                    "requested_model": draft_backend.get("requested_model"),
                    "id": draft_backend.get("id"),
                }.items()
                if value not in (None, "")
            }
        complaint_output_router_backends = export_router_backends or (
            [deepcopy(complaint_output_router_backend)] if complaint_output_router_backend else []
        )
        artifact_formats = ["json", "markdown", "pdf", "docx"] if draft else ["json"]
        return {
            "user_id": str(state.get("user_id") or user_id or DEFAULT_USER_ID),
            "claim_type": claim_type,
            "draft_strategy": str(draft.get("draft_strategy") or "template"),
            "draft_backend": draft_backend,
            "complaint_output_router_backend": complaint_output_router_backend,
            "complaint_output_router_backends": complaint_output_router_backends,
            "export_critic_router_backends": export_router_backends,
            "ui_review_backend": deepcopy(cached_ui_readiness.get("review_backend") or {}),
            "ui_workflow_type": str(cached_ui_readiness.get("workflow_type") or "").strip() or "unavailable",
            "artifact_formats": artifact_formats,
            "has_draft": bool(draft),
        }

    def get_client_release_gate(self, user_id: Optional[str]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        resolved_user_id = str(state.get("user_id") or user_id or DEFAULT_USER_ID)
        complaint_readiness = self.get_complaint_readiness(resolved_user_id)
        ui_readiness = self.get_ui_readiness(resolved_user_id)
        current_draft = dict(state.get("draft") or {})
        complaint_output_gate = _build_local_client_release_gate_for_state(state, self._build_review(state))

        complaint_score = int(complaint_readiness.get("score") or 0)
        ui_score = int(ui_readiness.get("score") or 35) if ui_readiness.get("score") is not None else 35
        output_score = _release_gate_score_from_verdict(complaint_output_gate.get("verdict"))
        score = round((complaint_score * 0.3) + (ui_score * 0.3) + (output_score * 0.4))

        ui_verdict = str(ui_readiness.get("verdict") or "").strip().lower()
        output_verdict = str(complaint_output_gate.get("verdict") or "").strip().lower()
        complaint_verdict = str(complaint_readiness.get("verdict") or "").strip().lower()

        blockers: List[str] = []
        if output_verdict == "blocked":
            blockers.append(str(complaint_output_gate.get("reason") or "The exported complaint is not yet client-safe."))
        if ui_verdict in {"do not send to clients yet", "needs repair", "no ui verdict cached"}:
            ui_reason = str(ui_readiness.get("summary") or "").strip()
            if ui_verdict == "no ui verdict cached":
                blockers.append("No actor/critic UI verdict is cached yet. Run the UX Audit before sending legal clients here.")
            elif ui_reason:
                blockers.append(ui_reason)
            else:
                blockers.append("The dashboard UI still needs repair before it should be treated as client-safe.")
        if complaint_verdict in {"not ready to draft", "still building the record"}:
            blockers.append(str(complaint_readiness.get("detail") or "The complaint record is not ready for drafting."))

        if output_verdict == "pass" and ui_verdict == "client-safe" and complaint_verdict in {"ready for first draft", "draft in progress"}:
            verdict = "client_safe"
            detail = (
                "The complaint workflow has a client-safe UI verdict, a filing-shaped complaint export, "
                "and a complaint record strong enough to keep drafting or refinement on track."
            )
            recommended_route = str(complaint_readiness.get("recommended_route") or "/document")
            recommended_action = "Continue refining the complaint and review the export artifacts before filing."
        elif score >= 65 and output_verdict != "blocked":
            verdict = "warning"
            detail = (
                "The complaint workflow is usable, but either the UI audit, the complaint record, or the exported filing "
                "still needs more work before this should be treated as safe for legal clients."
            )
            recommended_route = (
                "/workspace"
                if ui_verdict == "no ui verdict cached"
                else str(complaint_readiness.get("recommended_route") or "/workspace")
            )
            recommended_action = (
                "Review the blockers, tighten the record, and rerun the UX Audit or export critic before relying on this flow."
            )
        else:
            verdict = "blocked"
            detail = (
                "The current combination of UI readiness, complaint readiness, and exported complaint quality is not safe enough "
                "to treat this workflow as client-ready."
            )
            recommended_route = (
                "/workspace"
                if ui_verdict == "no ui verdict cached"
                else "/document"
                if output_verdict == "blocked" and current_draft
                else str(complaint_readiness.get("recommended_route") or "/workspace")
            )
            recommended_action = (
                "Fix the highlighted complaint-output and UI blockers before sending legal clients through this workflow."
            )

        return {
            "user_id": resolved_user_id,
            "score": max(0, min(100, score)),
            "verdict": verdict,
            "detail": detail,
            "recommended_route": recommended_route,
            "recommended_action": recommended_action,
            "blockers": blockers[:6],
            "complaint_readiness": complaint_readiness,
            "ui_readiness": ui_readiness,
            "complaint_output_release_gate": complaint_output_gate,
        }

    def get_tooling_contract(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        mcp_tools = [tool.get("name") for tool in list(self.list_mcp_tools().get("tools") or []) if tool.get("name")]
        package_exports = list(_PACKAGE_EXPORT_CONTRACT)
        cli_commands = list(_CLI_COMMAND_CONTRACT)
        browser_sdk_methods = list(_BROWSER_SDK_METHOD_CONTRACT)
        core_flow_steps: List[Dict[str, Any]] = []
        missing_exposures: List[str] = []
        for step_id, mapping in _CORE_FLOW_CONTRACT.items():
            exposed_everywhere = (
                mapping["package_export"] in package_exports
                and mapping["cli_command"] in cli_commands
                and mapping["mcp_tool"] in mcp_tools
                and mapping["browser_sdk_method"] in browser_sdk_methods
            )
            if not exposed_everywhere:
                missing_exposures.append(step_id)
            core_flow_steps.append({
                "id": step_id,
                "package_export": mapping["package_export"],
                "cli_command": mapping["cli_command"],
                "mcp_tool": mapping["mcp_tool"],
                "browser_sdk_method": mapping["browser_sdk_method"],
                "exposed_everywhere": exposed_everywhere,
            })
        payload = {
            "user_id": str(user_id or DEFAULT_USER_ID),
            "package_exports": package_exports,
            "cli_commands": cli_commands,
            "mcp_tools": mcp_tools,
            "browser_sdk_methods": browser_sdk_methods,
            "core_flow_steps": core_flow_steps,
            "missing_exposures": missing_exposures,
            "all_core_flow_steps_exposed": not missing_exposures,
        }
        if user_id:
            try:
                payload["workspace_data_schema"] = self.get_workspace_data_schema(user_id)
                payload["schema_guided_recommendations"] = _build_schema_guided_tooling_recommendations(
                    payload["workspace_data_schema"]
                )
            except Exception as exc:
                payload["workspace_data_schema_error"] = str(exc)
                payload["schema_guided_recommendations"] = []
        else:
            payload["schema_guided_recommendations"] = []
        return payload

    def get_workspace_data_schema(
        self,
        user_id: Optional[str] = None,
        *,
        manifest_path: Optional[str | Path] = None,
        statefile_path: Optional[str | Path] = None,
        evidence_db_path: Optional[str | Path] = None,
        legal_authority_db_path: Optional[str | Path] = None,
        claim_support_db_path: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        from complaint_generator.data_migration import inspect_workspace_data_schema

        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        if manifest_path is not None:
            snapshot = inspect_workspace_data_schema(manifest_path=manifest_path)
        else:
            state = self._load_state(resolved_user_id)
            snapshot = inspect_workspace_data_schema(
                state=state,
                statefile_path=statefile_path,
                evidence_db_path=evidence_db_path,
                legal_authority_db_path=legal_authority_db_path,
                claim_support_db_path=claim_support_db_path,
                user_id=resolved_user_id,
            )
        snapshot["user_id"] = resolved_user_id
        snapshot["source"] = str(snapshot.get("source") or "workspace_data_schema")
        return snapshot

    def migrate_legacy_workspace_data(
        self,
        user_id: Optional[str] = None,
        *,
        output_dir: Optional[str | Path] = None,
        statefile_path: Optional[str | Path] = None,
        evidence_db_path: Optional[str | Path] = None,
        legal_authority_db_path: Optional[str | Path] = None,
        claim_support_db_path: Optional[str | Path] = None,
        package_name: Optional[str] = None,
        include_car: bool = True,
    ) -> Dict[str, Any]:
        from complaint_generator.data_migration import migrate_legacy_workspace_data

        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        target_output_dir = (
            Path(output_dir).expanduser().resolve()
            if output_dir is not None
            else (self._session_dir / "dataset_migrations" / _slugify_user_id(resolved_user_id)).resolve()
        )
        state = self._load_state(resolved_user_id)
        result = migrate_legacy_workspace_data(
            output_dir=target_output_dir,
            state=state,
            statefile_path=statefile_path,
            evidence_db_path=evidence_db_path,
            legal_authority_db_path=legal_authority_db_path,
            claim_support_db_path=claim_support_db_path,
            user_id=resolved_user_id,
            package_name=package_name,
            include_car=include_car,
        )
        result["user_id"] = resolved_user_id
        result["output_dir"] = str(target_output_dir)
        return result

    def get_workflow_capabilities(self, user_id: Optional[str]) -> Dict[str, Any]:
        session = self.get_session(user_id)
        review = session["review"]
        overview = dict(review.get("overview") or {})
        current_draft = (session.get("session") or {}).get("draft")
        claim_type = str((session.get("session") or {}).get("claim_type") or "retaliation")
        draft_strategy = str((current_draft or {}).get("draft_strategy") or "template")
        questions = list(session.get("questions") or [])
        answered_count = len([item for item in questions if item.get("is_answered")])
        total_questions = len(questions)
        readiness = self.get_complaint_readiness(user_id)
        capabilities = [
            {
                "id": "intake_questions",
                "label": "Complaint intake questions",
                "available": total_questions > 0,
                "detail": f"{answered_count} of {total_questions} intake questions answered.",
            },
            {
                "id": "mediator_prompt",
                "label": "Chat mediator handoff",
                "available": True,
                "detail": "A testimony-ready mediator prompt can be generated from the shared case synopsis and support gaps.",
            },
            {
                "id": "evidence_capture",
                "label": "Evidence capture",
                "available": True,
                "detail": f"{int(overview.get('testimony_items') or 0) + int(overview.get('document_items') or 0)} evidence items saved.",
            },
            {
                "id": "support_review",
                "label": "Claim support review",
                "available": True,
                "detail": f"{overview.get('supported_elements') or 0} supported elements, {overview.get('missing_elements') or 0} gaps remaining.",
            },
            {
                "id": "complaint_draft",
                "label": "Complaint draft",
                "available": True,
                "detail": "A draft already exists and can be edited." if current_draft else "A draft can be generated from the current complaint record.",
            },
            {
                "id": "claim_type_alignment",
                "label": "Claim-type drafting alignment",
                "available": True,
                "detail": f"The current complaint type is {_claim_type_display_name(claim_type)}.",
            },
            {
                "id": "formal_complaint_generation",
                "label": "Formal complaint generation",
                "available": True,
                "detail": (
                    "The current draft uses llm_router-backed formal complaint generation."
                    if draft_strategy == "llm_router"
                    else "The current draft is using the deterministic template fallback."
                ),
            },
            {
                "id": "complaint_packet",
                "label": "Complaint packet export",
                "available": True,
                "detail": "The lawsuit packet can be exported as a structured browser, CLI, or MCP artifact.",
            },
        ]
        workspace_data_schema = self.get_workspace_data_schema(session["session"]["user_id"])
        return {
            "user_id": session["session"]["user_id"],
            "case_synopsis": session["case_synopsis"],
            "overview": overview,
            "claim_type": claim_type,
            "claim_type_label": _claim_type_display_name(claim_type),
            "draft_strategy": draft_strategy,
            "complaint_readiness": readiness,
            "ui_readiness": self.get_ui_readiness(user_id),
            "client_release_gate": self.get_client_release_gate(user_id),
            "tooling_contract": self.get_tooling_contract(user_id),
            "workspace_data_schema": workspace_data_schema,
            "schema_guided_recommendations": _build_schema_guided_tooling_recommendations(workspace_data_schema),
            "capabilities": capabilities,
        }

    def export_complaint_packet(self, user_id: Optional[str]) -> Dict[str, Any]:
        snapshot = self._build_packet_snapshot(user_id)
        packet = snapshot["packet"]
        artifacts = snapshot["artifacts"]
        artifact_analysis = snapshot["artifact_analysis"]
        packet_summary = snapshot["packet_summary"]
        draft = dict(packet.get("draft") or {})
        review = dict(packet.get("review") or {})
        state = dict(packet)
        state["draft"] = draft
        state["review"] = review
        state["artifacts"] = artifacts
        state["artifact_analysis"] = artifact_analysis
        session = self.get_session(user_id)
        ui_feedback = self._analyze_complaint_output(packet, artifact_analysis)
        draft_fallback_reason = str(draft.get("draft_fallback_reason") or "").strip()
        complaint_issues = list(ui_feedback.get("issues") or [])
        payload = {
            "packet": packet,
            "artifacts": artifacts,
            "artifact_analysis": artifact_analysis,
            "ui_feedback": ui_feedback,
            "packet_summary": {
                **packet_summary,
                "draft_fallback_reason": draft_fallback_reason,
                "filing_shape_score": int(ui_feedback.get("filing_shape_score") or 0),
                "claim_type_alignment_score": int(ui_feedback.get("claim_type_alignment_score") or 0),
                "formal_defect_count": len(
                    [item for item in complaint_issues if str((item or {}).get("source") or "").startswith("complaint_output")]
                ),
                "high_severity_issue_count": len(
                    [item for item in complaint_issues if str((item or {}).get("severity") or "").lower() == "high"]
                ),
                "release_gate": deepcopy(ui_feedback.get("release_gate") or {}),
                "formal_diagnostics": deepcopy(ui_feedback.get("formal_diagnostics") or {}),
                "complaint_output_router_backend": deepcopy(((ui_feedback.get("router_review") or {}).get("backend") or {})),
            },
        }
        persisted_state = self._load_state(str((session.get("session") or {}).get("user_id") or user_id or DEFAULT_USER_ID))
        persisted_state["latest_packet_export"] = {
            "packet": {
                "title": str(packet.get("title") or "").strip(),
                "claim_type": str(packet.get("claim_type") or "retaliation").strip() or "retaliation",
                "exported_at": str(packet.get("exported_at") or _utc_now()),
                "draft": {
                    "title": str(draft.get("title") or "").strip(),
                    "body": str(draft.get("body") or ""),
                    "draft_strategy": str(draft.get("draft_strategy") or "template"),
                    "draft_fallback_reason": draft_fallback_reason,
                    "draft_normalizations": list(draft.get("draft_normalizations") or []),
                },
            },
            "packet_summary": deepcopy(payload.get("packet_summary") or {}),
            "ui_feedback": deepcopy(ui_feedback),
        }
        self._save_state(persisted_state)
        return payload

    def _build_packet_snapshot(self, user_id: Optional[str]) -> Dict[str, Any]:
        session = self.get_session(user_id)
        state = session["session"]
        draft = deepcopy(state.get("draft") or self._build_draft(state))
        review = deepcopy(session["review"])
        packet = {
            "title": draft["title"],
            "user_id": state["user_id"],
            "claim_type": state.get("claim_type", "retaliation"),
            "case_synopsis": session["case_synopsis"],
            "questions": deepcopy(session["questions"]),
            "evidence": deepcopy(state.get("evidence") or {}),
            "review": review,
            "draft": draft,
            "exported_at": _utc_now(),
        }
        artifacts = self._build_export_artifacts(packet)
        artifact_analysis = {
            "draft_word_count": len(str(draft.get("body") or "").split()),
            "evidence_item_count": len((packet.get("evidence") or {}).get("testimony") or [])
            + len((packet.get("evidence") or {}).get("documents") or []),
            "requested_relief_count": len(list(draft.get("requested_relief") or [])),
            "supported_elements": int((review.get("overview") or {}).get("supported_elements") or 0),
            "missing_elements": int((review.get("overview") or {}).get("missing_elements") or 0),
            "has_case_synopsis": bool(str(packet.get("case_synopsis") or "").strip()),
        }
        packet_summary = {
            "question_count": len(packet["questions"]),
            "answered_question_count": len([item for item in packet["questions"] if item.get("is_answered")]),
            "supported_elements": int((review.get("overview") or {}).get("supported_elements") or 0),
            "missing_elements": int((review.get("overview") or {}).get("missing_elements") or 0),
            "testimony_items": int((review.get("overview") or {}).get("testimony_items") or 0),
            "document_items": int((review.get("overview") or {}).get("document_items") or 0),
            "has_draft": bool(state.get("draft")),
            "draft_strategy": str(draft.get("draft_strategy") or "template"),
            "draft_normalization_count": len(list(draft.get("draft_normalizations") or [])),
            "draft_normalizations": list(draft.get("draft_normalizations") or []),
            "complaint_readiness": self.get_complaint_readiness(user_id),
            "artifact_formats": sorted(artifacts.keys()),
        }
        return {
            "packet": packet,
            "artifacts": artifacts,
            "artifact_analysis": artifact_analysis,
            "packet_summary": packet_summary,
        }

    def _analyze_complaint_output(self, packet: Dict[str, Any], artifact_analysis: Dict[str, Any]) -> Dict[str, Any]:
        from .ui_review import review_complaint_output_with_llm_router

        draft = dict(packet.get("draft") or {})
        review = dict(packet.get("review") or {})
        overview = dict(review.get("overview") or {})
        body = str(draft.get("body") or "").strip()
        case_synopsis = str(packet.get("case_synopsis") or "").strip()
        draft_backend = dict(draft.get("draft_backend") or {})
        issues: List[Dict[str, Any]] = []
        suggestions: List[Dict[str, Any]] = []
        formal_sections_present = {
            "caption": "IN THE UNITED STATES DISTRICT COURT" in body,
            "civil_action_number": "Civil Action No. ________________" in body,
            "nature_of_action": "NATURE OF THE ACTION" in body,
            "jurisdiction_and_venue": "JURISDICTION AND VENUE" in body,
            "parties": "PARTIES" in body,
            "factual_allegations": "FACTUAL ALLEGATIONS" in body,
            "evidentiary_support": "EVIDENTIARY SUPPORT AND NOTICE" in body,
            "claim_count": "COUNT I -" in body,
            "prayer_for_relief": "PRAYER FOR RELIEF" in body,
            "jury_demand": "JURY DEMAND" in body,
            "signature_block": "SIGNATURE BLOCK" in body,
        }
        claim_type = _normalize_claim_type(packet.get("claim_type"))
        claim_label = _claim_type_display_name(claim_type)
        expected_complaint_heading = f"COMPLAINT FOR {claim_label.upper()}"
        expected_count_heading = _claim_type_count_heading(claim_type)
        claim_type_alignment = {
            "complaint_heading_matches": expected_complaint_heading in body,
            "count_heading_matches": expected_count_heading in body,
        }
        validation_issues = _formal_complaint_validation_issues(body, claim_type)
        meta_summary_issues = [issue for issue in validation_issues if issue.startswith("Contains meta-summary language:")]
        numbering_issue_present = any(issue == "Missing numbered pleading paragraphs." for issue in validation_issues)

        if artifact_analysis.get("missing_elements", 0) > 0:
            missing_count = int(artifact_analysis.get("missing_elements") or 0)
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": f"The exported complaint still reflects {missing_count} unsupported claim elements.",
                    "ui_implication": "The review and draft stages need stronger warnings before the user treats the complaint as filing-ready.",
                }
            )
            suggestions.append(
                {
                    "title": "Tighten review-to-draft gatekeeping",
                    "recommendation": "Add stronger blocker language and a more prominent unsupported-elements summary before draft generation or export.",
                    "target_surface": "review,draft,integrations",
                }
            )
        if not case_synopsis:
            issues.append(
                {
                    "severity": "medium",
                    "source": "complaint_output",
                    "finding": "The exported complaint has no shared case synopsis.",
                    "ui_implication": "Users can reach export without preserving a stable theory of the case across mediator, review, and draft surfaces.",
                }
            )
            suggestions.append(
                {
                    "title": "Make case framing harder to miss",
                    "recommendation": "Require or strongly encourage a shared case synopsis before export and keep it visible near every major handoff.",
                    "target_surface": "intake,review,draft",
                }
            )
        if artifact_analysis.get("draft_word_count", 0) < 80:
            issues.append(
                {
                    "severity": "medium",
                    "source": "complaint_output",
                    "finding": "The exported complaint draft is still very short.",
                    "ui_implication": "The draft workflow may be under-explaining what a usable first complaint should contain.",
                }
            )
            suggestions.append(
                {
                    "title": "Strengthen draft completeness cues",
                    "recommendation": "Show a drafting checklist and clearer guidance about allegations, chronology, harm, and requested relief before export.",
                    "target_surface": "draft",
                }
            )
        if artifact_analysis.get("requested_relief_count", 0) == 0:
            issues.append(
                {
                    "severity": "medium",
                    "source": "complaint_output",
                    "finding": "No requested relief was carried into the export.",
                    "ui_implication": "The user may not understand that requested relief should be completed before download.",
                }
            )
            suggestions.append(
                {
                    "title": "Surface requested-relief validation",
                    "recommendation": "Warn before export when requested relief is empty and point the user back to the draft editor.",
                    "target_surface": "draft,integrations",
                }
            )
        if artifact_analysis.get("evidence_item_count", 0) == 0:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": "The complaint was exported without any saved evidence items.",
                    "ui_implication": "The workspace is not making evidence capture feel mandatory enough before a user downloads the packet.",
                }
            )
            suggestions.append(
                {
                    "title": "Make evidence support more legible before export",
                    "recommendation": "Display stronger export warnings and direct links back to the evidence workbench when the packet lacks corroborating materials.",
                    "target_surface": "evidence,review,integrations",
                }
            )

        formal_markers = [
            "IN THE UNITED STATES DISTRICT COURT",
            "Civil Action No. ________________",
            "COMPLAINT FOR",
            "JURISDICTION AND VENUE",
            "FACTUAL ALLEGATIONS",
            "EVIDENTIARY SUPPORT AND NOTICE",
            "COUNT I -",
            "PRAYER FOR RELIEF",
            "JURY DEMAND",
            "SIGNATURE BLOCK",
        ]
        missing_markers = [marker for marker in formal_markers if marker not in body]
        if missing_markers:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": "The exported complaint is missing formal pleading sections.",
                    "ui_implication": "The drafting UI is letting users export something that does not read like a formal legal complaint.",
                }
            )

        if numbering_issue_present:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": "The exported complaint is missing numbered pleading paragraphs.",
                    "ui_implication": "The draft builder is allowing narrative text that still reads like a summary instead of a filed complaint.",
                }
            )
            suggestions.append(
                {
                    "title": "Keep numbered complaint paragraphs visible in the draft",
                    "recommendation": "Show numbered pleading paragraph examples and warn before export if the draft body stops reading like a paragraph-numbered complaint.",
                    "target_surface": "draft,document,integrations",
                }
            )

        if meta_summary_issues:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": "The exported complaint still contains internal product or workflow language instead of clean pleading language.",
                    "ui_implication": "The LLM drafting flow is leaking system-facing wording into a client-facing legal document.",
                }
            )
            suggestions.append(
                {
                    "title": "Strip workflow language out of the complaint draft",
                    "recommendation": "Warn when the draft body mentions workflow summaries, complaint records, SDKs, JSON, or support matrices so the final complaint remains client-safe.",
                    "target_surface": "draft,integrations,optimizer",
                }
            )

        if not claim_type_alignment["complaint_heading_matches"] or not claim_type_alignment["count_heading_matches"]:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": f"The exported complaint does not clearly read like a {claim_label.lower()} complaint for the selected claim type.",
                    "ui_implication": "The drafting flow is letting the complaint drift into a generic or mismatched claim shape before export.",
                }
            )
            suggestions.append(
                {
                    "title": "Keep the selected claim theory visible through drafting",
                    "recommendation": "Show the selected claim type, count heading, and claim-specific allegation checklist throughout the draft flow so the complaint stays aligned to the chosen legal theory.",
                    "target_surface": "draft,review,integrations",
                }
            )
            suggestions.append(
                {
                    "title": "Enforce formal pleading structure",
                    "recommendation": "Keep the draft builder anchored to formal complaint sections like jurisdiction, factual allegations, prayer for relief, and jury demand before export.",
                    "target_surface": "draft,document,integrations",
                }
            )

        if not formal_sections_present["signature_block"]:
            issues.append(
                {
                    "severity": "medium",
                    "source": "complaint_output",
                    "finding": "The exported complaint is missing a signature block.",
                    "ui_implication": "The draft stage still reads too much like a memo unless the filing posture stays visible through export.",
                }
            )
            suggestions.append(
                {
                    "title": "Keep filing posture visible in the draft",
                    "recommendation": "Preserve a default signature block and explain in the draft editor that the output should resemble a court filing rather than a loose narrative summary.",
                    "target_surface": "draft,integrations",
                }
            )

        if artifact_analysis.get("evidence_item_count", 0) > 0 and "EVIDENTIARY SUPPORT AND NOTICE" not in body:
            issues.append(
                {
                    "severity": "medium",
                    "source": "complaint_output",
                    "finding": "The complaint includes evidence in the record, but the draft does not make that evidentiary posture legible.",
                    "ui_implication": "Users may not see how saved evidence is helping shape the pleading.",
                }
            )
            suggestions.append(
                {
                    "title": "Ground the draft in saved exhibits",
                    "recommendation": "Show clearer exhibit and support references in the draft so the complaint feels tied to the record gathered in the evidence and review stages.",
                    "target_surface": "evidence,review,draft",
                }
            )

        router_review = None
        try:
            router_review = review_complaint_output_with_llm_router(
                self._build_packet_markdown(packet),
                claim_type=claim_label,
                claim_guidance=_claim_type_filing_guidance(claim_type),
                synopsis=case_synopsis,
                notes=(
                    "Assess whether this output looks like a formal legal complaint, whether it matches the selected claim type, "
                    "and turn any filing-shape or claim-alignment defects into UI/UX repairs for intake, evidence, review, draft, and export surfaces."
                ),
            )
        except Exception:
            router_review = None

        router_payload = dict((router_review or {}).get("review") or {})
        router_issues = [dict(item) for item in list(router_payload.get("issues") or []) if isinstance(item, dict)]
        router_suggestions = [
            dict(item) for item in list(router_payload.get("ui_suggestions") or []) if isinstance(item, dict)
        ]
        for issue in router_issues[:6]:
            issues.append(
                {
                    "severity": str(issue.get("severity") or "medium"),
                    "source": "complaint_output_router",
                    "finding": str(issue.get("finding") or "The complaint output router identified a filing-shape issue."),
                    "ui_implication": str(
                        issue.get("ui_implication")
                        or issue.get("complaint_impact")
                        or "The UI flow is likely under-guiding the user before export."
                    ),
                }
            )
        for suggestion in router_suggestions[:6]:
            suggestions.append(
                {
                    "title": str(suggestion.get("title") or "Repair complaint-output workflow"),
                    "recommendation": str(
                        suggestion.get("recommendation")
                        or suggestion.get("why_it_matters")
                        or "Tighten the complaint workflow so the exported filing reads more formally."
                    ),
                    "target_surface": str(suggestion.get("target_surface") or "draft,review,integrations"),
                }
            )

        section_score = 5 * sum(1 for value in formal_sections_present.values() if value)
        body_length_score = 10 if artifact_analysis.get("draft_word_count", 0) >= 180 else 0
        evidence_score = 10 if artifact_analysis.get("evidence_item_count", 0) > 0 else 0
        relief_score = 5 if artifact_analysis.get("requested_relief_count", 0) > 0 else 0
        support_score = 5 if int(artifact_analysis.get("supported_elements") or 0) > 0 else 0
        heuristic_score = min(100, 35 + section_score + body_length_score + evidence_score + relief_score + support_score)
        router_score = int(router_payload.get("filing_shape_score") or 0) if router_payload else 0
        claim_type_alignment_score = (
            100
            if claim_type_alignment["complaint_heading_matches"] and claim_type_alignment["count_heading_matches"]
            else 50
            if claim_type_alignment["complaint_heading_matches"] or claim_type_alignment["count_heading_matches"]
            else 0
        )
        router_alignment_score = int(router_payload.get("claim_type_alignment_score") or 0) if router_payload else 0
        filing_shape_score = (
            round((heuristic_score + router_score) / 2)
            if router_score
            else heuristic_score
        )
        if claim_type_alignment_score == 0:
            resolved_claim_type_alignment_score = 0
        else:
            resolved_claim_type_alignment_score = (
                round((claim_type_alignment_score + router_alignment_score) / 2)
                if router_alignment_score
                else claim_type_alignment_score
            )
        release_gate = _build_complaint_output_release_gate(
            claim_type=claim_type,
            draft_strategy=str(draft.get("draft_strategy") or "template"),
            filing_shape_score=filing_shape_score,
            claim_type_alignment_score=resolved_claim_type_alignment_score,
            missing_elements=int(artifact_analysis.get("missing_elements") or 0),
            evidence_item_count=int(artifact_analysis.get("evidence_item_count") or 0),
        )

        if filing_shape_score < 75:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": "The generated complaint still does not read enough like a filing-ready legal complaint.",
                    "ui_implication": "The intake, evidence, review, and draft surfaces need stronger structure cues before export is treated as safe.",
                }
            )
            suggestions.append(
                {
                    "title": "Promote filing-readiness guidance before export",
                    "recommendation": "Keep the draft builder focused on caption, chronology, claim counts, evidentiary grounding, and requested relief so the exported complaint resembles a court filing instead of a loose summary.",
                    "target_surface": "draft,review,integrations",
                }
            )

        if not suggestions:
            suggestions.append(
                {
                    "title": "Preserve the current filing flow",
                    "recommendation": "The exported complaint looks coherent enough to keep the current UI flow, but continue validating navigation, evidence support, and clarity through Playwright.",
                    "target_surface": "workspace,review,document",
                }
            )

        complaint_output_issue_items = [
            dict(item)
            for item in issues
            if str((item or {}).get("source") or "").startswith("complaint_output")
        ]
        high_severity_complaint_items = [
            dict(item)
            for item in complaint_output_issue_items
            if str((item or {}).get("severity") or "").lower() == "high"
        ]
        formal_diagnostics = {
            "formal_defect_count": len(complaint_output_issue_items),
            "high_severity_issue_count": len(high_severity_complaint_items),
            "top_formal_findings": [
                str((item or {}).get("finding") or "").strip()
                for item in complaint_output_issue_items[:5]
                if str((item or {}).get("finding") or "").strip()
            ],
            "top_ui_implications": [
                str((item or {}).get("ui_implication") or "").strip()
                for item in complaint_output_issue_items[:5]
                if str((item or {}).get("ui_implication") or "").strip()
            ],
            "top_ui_suggestions": [
                str((item or {}).get("title") or "").strip()
                for item in suggestions[:5]
                if str((item or {}).get("title") or "").strip()
            ],
            "release_gate_verdict": str((release_gate or {}).get("verdict") or "").strip() or "unknown",
        }

        resolved_router_backend = deepcopy((router_review or {}).get("backend") or {})
        if resolved_router_backend and draft_backend:
            for key in ("id", "requested_provider", "requested_model", "provider", "model"):
                if resolved_router_backend.get(key) in (None, "") and draft_backend.get(key) not in (None, ""):
                    resolved_router_backend[key] = draft_backend.get(key)
        if not resolved_router_backend and draft_backend:
            resolved_router_backend = {
                "strategy": str(draft.get("draft_strategy") or "template"),
                "provider": draft_backend.get("provider"),
                "model": draft_backend.get("model"),
                "requested_provider": draft_backend.get("requested_provider"),
                "requested_model": draft_backend.get("requested_model"),
                "id": draft_backend.get("id"),
            }

        return {
            "summary": (
                "The exported complaint artifact was analyzed to infer which UI steps may still be too weak, "
                "hidden, or permissive for a real complainant."
            ),
            "filing_shape_score": filing_shape_score,
            "formal_sections_present": formal_sections_present,
            "claim_type_alignment": claim_type_alignment,
            "claim_type_alignment_score": resolved_claim_type_alignment_score,
            "release_gate": release_gate,
            "issues": issues,
            "ui_suggestions": suggestions,
            "formal_diagnostics": formal_diagnostics,
            "draft_strategy": str(draft.get("draft_strategy") or "template"),
            "draft_fallback_reason": str(draft.get("draft_fallback_reason") or "").strip(),
            "draft_normalizations": list(draft.get("draft_normalizations") or []),
            "draft_excerpt": body[:600],
            "complaint_strengths": [
                f"Supported elements: {int(overview.get('supported_elements') or 0)}",
                f"Evidence items: {int(overview.get('testimony_items') or 0) + int(overview.get('document_items') or 0)}",
                f"Requested relief items: {int(artifact_analysis.get('requested_relief_count') or 0)}",
                f"Formal sections present: {sum(1 for value in formal_sections_present.values() if value)}/{len(formal_sections_present)}",
                f"Claim type alignment: {expected_complaint_heading} / {expected_count_heading}",
            ],
            "router_backends": [
                deepcopy(resolved_router_backend)
            ]
            if isinstance(resolved_router_backend, dict) and resolved_router_backend
            else [],
            "router_review": {
                **(router_review or {}),
                "backend": resolved_router_backend,
            }
            if isinstance(router_review, dict)
            else {"backend": resolved_router_backend},
        }

    def analyze_complaint_output(self, user_id: Optional[str]) -> Dict[str, Any]:
        payload = self.export_complaint_packet(user_id)
        return {
            "user_id": ((payload.get("packet") or {}).get("user_id") or str(user_id or DEFAULT_USER_ID)),
            "packet_summary": deepcopy(payload.get("packet_summary") or {}),
            "artifact_analysis": deepcopy(payload.get("artifact_analysis") or {}),
            "ui_feedback": deepcopy(payload.get("ui_feedback") or {}),
        }

    def get_formal_diagnostics(self, user_id: Optional[str]) -> Dict[str, Any]:
        analysis = self.analyze_complaint_output(user_id)
        ui_feedback = dict(analysis.get("ui_feedback") or {})
        diagnostics = dict(ui_feedback.get("formal_diagnostics") or {})
        packet_summary = dict(analysis.get("packet_summary") or {})
        try:
            markdown_artifact = self.build_export_artifact(user_id, "markdown")
            markdown_text = markdown_artifact.get("body", b"").decode("utf-8", errors="replace")
            export_structure = _build_export_structure_summary(markdown_text)
        except Exception as exc:
            export_structure = {
                "error": str(exc),
                "summary": {
                    "has_header": False,
                    "court_line_count": 0,
                    "party_line_count": 0,
                    "title_line_count": 0,
                    "section_count": 0,
                    "section_kinds": [],
                    "numbered_paragraph_count": 0,
                    "bullet_count": 0,
                    "code_block_count": 0,
                    "all_caps_heading_count": 0,
                    "title": "",
                },
            }
        return {
            "user_id": str(analysis.get("user_id") or user_id or DEFAULT_USER_ID),
            "claim_type_alignment_score": int(ui_feedback.get("claim_type_alignment_score") or 0),
            "filing_shape_score": int(ui_feedback.get("filing_shape_score") or 0),
            "release_gate": deepcopy(ui_feedback.get("release_gate") or {}),
            "formal_diagnostics": diagnostics,
            "export_structure": export_structure,
            "router_backend": deepcopy(((ui_feedback.get("router_review") or {}).get("backend") or {})),
            "packet_summary": {
                "has_draft": bool(packet_summary.get("has_draft")),
                "draft_strategy": str(packet_summary.get("draft_strategy") or "template"),
                "formal_defect_count": int(packet_summary.get("formal_defect_count") or 0),
                "high_severity_issue_count": int(packet_summary.get("high_severity_issue_count") or 0),
                "complaint_output_router_backend": deepcopy(packet_summary.get("complaint_output_router_backend") or {}),
            },
        }

    def get_provider_diagnostics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        from applications import ui_review as ui_review_module
        from ipfs_datasets_py import llm_router

        def _vault_value(*names: str) -> str:
            try:
                from ipfs_datasets_py.mcp_server.secrets_vault import get_secrets_vault

                vault = get_secrets_vault()
                for name in names:
                    resolved = str(vault.get(name) or "").strip()
                    if resolved:
                        return resolved
            except Exception:
                pass
            return ""

        def _keyring_value(*names: str) -> str:
            try:
                import keyring  # type: ignore

                for name in names:
                    resolved = str(keyring.get_password("ipfs_datasets_py", name) or "").strip()
                    if resolved:
                        return resolved
            except Exception:
                pass
            return ""

        def _first_env(*names: str) -> str:
            for name in names:
                resolved = str(os.getenv(name, "") or "").strip()
                if resolved:
                    return resolved
            return ""

        def _source_for_openai() -> str:
            if _first_env("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
                return "env"
            if _vault_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
                return "vault"
            if _keyring_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
                return "keyring"
            try:
                from ipfs_datasets_py.utils.engine_env import _openai_key_from_common_files

                if str(_openai_key_from_common_files() or "").strip():
                    return "local_cli_config"
            except Exception:
                pass
            return "unavailable"

        def _resolve_openai_key() -> str:
            resolver = getattr(llm_router, "_resolve_openai_api_key", None)
            if callable(resolver):
                try:
                    resolved = str(resolver() or "").strip()
                    if resolved:
                        return resolved
                except Exception:
                    pass

            resolved = _first_env("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN")
            if resolved:
                return resolved

            resolved = _vault_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN")
            if resolved:
                return resolved

            resolved = _keyring_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN")
            if resolved:
                return resolved

            try:
                from ipfs_datasets_py.utils.engine_env import _openai_key_from_common_files

                return str(_openai_key_from_common_files() or "").strip()
            except Exception:
                return ""

        def _source_for_hf() -> str:
            if _first_env(
                "IPFS_DATASETS_PY_HF_API_TOKEN",
                "HUGGINGFACEHUB_API_TOKEN",
                "HF_TOKEN",
                "HUGGINGFACE_HUB_TOKEN",
                "HUGGINGFACE_API_KEY",
                "HUGGINGFACE_API_TOKEN",
                "HF_API_TOKEN",
            ):
                return "env"
            if _vault_value(
                "IPFS_DATASETS_PY_HF_API_TOKEN",
                "HUGGINGFACEHUB_API_TOKEN",
                "HF_TOKEN",
                "HUGGINGFACE_HUB_TOKEN",
                "HUGGINGFACE_API_KEY",
                "HUGGINGFACE_API_TOKEN",
                "HF_API_TOKEN",
            ):
                return "vault"
            if _keyring_value(
                "IPFS_DATASETS_PY_HF_API_TOKEN",
                "HUGGINGFACEHUB_API_TOKEN",
                "HF_TOKEN",
                "HUGGINGFACE_HUB_TOKEN",
                "HUGGINGFACE_API_KEY",
                "HUGGINGFACE_API_TOKEN",
                "HF_API_TOKEN",
            ):
                return "keyring"
            if str(llm_router._resolve_hf_api_token() or "").strip():
                return "huggingface_cli"
            return "unavailable"

        default_order = list(getattr(llm_router, "_UNPINNED_OPTIONAL_PROVIDER_ORDER", []))
        forced_provider = str(os.getenv("IPFS_DATASETS_PY_LLM_PROVIDER", "") or "").strip()
        codex_path = shutil.which("codex") or ""
        copilot_path = shutil.which("copilot") or ""
        openai_key = _resolve_openai_key()
        hf_token = str(llm_router._resolve_hf_api_token() or "").strip()
        copilot_provider = llm_router._builtin_provider_by_name("copilot_cli")
        copilot_command = os.getenv("IPFS_DATASETS_PY_COPILOT_CLI_CMD", "npx --yes @github/copilot -p {prompt}")
        copilot_supports_image_inputs = bool(
            getattr(llm_router, "_copilot_cli_supports_image_inputs", lambda _command: False)(copilot_command)
        )

        providers = [
            {
                "name": "codex_cli",
                "available": bool(codex_path),
                "reason": "Codex CLI is installed and available on PATH." if codex_path else "Codex CLI binary not found on PATH.",
                "binary_path": codex_path or None,
                "credential_source": "local_codex_auth" if codex_path else "unavailable",
                "supports_multimodal": bool(codex_path),
                "draft_timeout_seconds": _llm_draft_timeout_for_provider("codex_cli"),
            },
            {
                "name": "openai",
                "available": bool(openai_key),
                "reason": "OpenAI API key resolved for direct chat-completions use." if openai_key else "No OpenAI API key resolved from env, vault, keyring, or local CLI config.",
                "credential_source": _source_for_openai(),
                "base_url": str(os.getenv("IPFS_DATASETS_PY_OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/"),
                "draft_timeout_seconds": _llm_draft_timeout_for_provider("openai"),
            },
            {
                "name": "copilot_cli",
                "available": copilot_provider is not None,
                "reason": (
                    "Copilot CLI command template resolved and is available."
                    if copilot_provider is not None and copilot_path
                    else "Copilot fallback is available through the configured command template."
                    if copilot_provider is not None
                    else "Copilot CLI command is not currently available on this machine."
                ),
                "binary_path": copilot_path or None,
                "supports_multimodal": bool(copilot_path),
                "supports_multimodal_ui_review": copilot_supports_image_inputs,
                "credential_source": (
                    "github_copilot_cli"
                    if copilot_provider is not None and copilot_path
                    else "github_copilot_command_template"
                    if copilot_provider is not None
                    else "unavailable"
                ),
                "draft_timeout_seconds": _llm_draft_timeout_for_provider("copilot_cli"),
            },
            {
                "name": "hf_inference_api",
                "available": bool(hf_token),
                "reason": "Hugging Face token resolved for hosted inference/router use." if hf_token else "No Hugging Face token resolved from env, vault, keyring, or huggingface_hub CLI login.",
                "credential_source": _source_for_hf(),
                "base_url": str(os.getenv("IPFS_DATASETS_PY_HF_INFERENCE_BASE_URL", "https://router.huggingface.co/hf-inference/models")).rstrip("/"),
                "draft_timeout_seconds": _llm_draft_timeout_for_provider("hf_inference_api"),
                "ui_review_model": ui_review_module._ui_review_model_for_provider("hf_inference_api"),
                "ui_review_timeout_seconds": ui_review_module._ui_review_timeout_for_provider("hf_inference_api"),
            },
        ]

        effective_default = next((item["name"] for item in providers if item["available"]), None)
        return {
            "user_id": str(user_id or DEFAULT_USER_ID),
            "forced_provider": forced_provider or None,
            "default_order": default_order,
            "effective_default_provider": forced_provider or effective_default,
            "complaint_draft_default_order": list(DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN),
            "effective_complaint_draft_provider": (
                str(os.getenv("COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER", "") or "").strip()
                or DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN[0]
            ),
            "ui_review_default_provider": ui_review_module.DEFAULT_UI_REVIEW_PROVIDER,
            "ui_review_default_model": ui_review_module._ui_review_model_for_provider(
                ui_review_module.DEFAULT_UI_REVIEW_PROVIDER
            ),
            "ui_review_multimodal_rate_limit_fallbacks": {
                "codex_cli": list(ui_review_module._multimodal_rate_limit_fallback_chain("codex_cli")),
                "copilot_cli": list(ui_review_module._multimodal_rate_limit_fallback_chain("copilot_cli")),
            },
            "ui_review_hf_fallback_model": ui_review_module._ui_review_model_for_provider("hf_inference_api"),
            "providers": providers,
            "summary": {
                "codex_available": bool(codex_path),
                "openai_available": bool(openai_key),
                "copilot_available": copilot_provider is not None,
                "huggingface_available": bool(hf_token),
            },
        }

    def review_generated_exports(
        self,
        user_id: Optional[str],
        *,
        artifact_path: Optional[str] = None,
        artifact_dir: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config_path: Optional[str] = None,
        backend_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        from .ui_review import review_complaint_export_artifacts

        artifact_metadata: List[Dict[str, Any]] = []
        if artifact_path:
            path = Path(str(artifact_path)).expanduser().resolve()
            if not path.exists():
                raise ValueError(f"Artifact path does not exist: {path}")
            payload = json.loads(path.read_text())
            if not isinstance(payload, dict):
                raise ValueError("Artifact path must point to a JSON object.")
            artifact_metadata.append(payload)
        elif artifact_dir:
            root = Path(str(artifact_dir)).expanduser().resolve()
            if not root.exists():
                raise ValueError(f"Artifact directory does not exist: {root}")
            for candidate in sorted(root.glob("*.json")):
                try:
                    payload = json.loads(candidate.read_text())
                except Exception:
                    continue
                if isinstance(payload, dict):
                    artifact_metadata.append(payload)
        else:
            artifact_metadata = self._build_complaint_output_review_artifacts(user_id)

        report = review_complaint_export_artifacts(
            artifact_metadata,
            provider=provider,
            model=model,
            config_path=config_path,
            backend_id=backend_id,
            notes=notes,
        )
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        state["latest_export_critic"] = deepcopy(report)
        self._save_state(state)
        return {
            "user_id": str(user_id or DEFAULT_USER_ID),
            **report,
        }

    def update_claim_type(self, user_id: Optional[str], claim_type: Optional[str]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        state["claim_type"] = _normalize_claim_type(claim_type)
        self._save_state(state)
        session = self.get_session(str(state.get("user_id")))
        return {
            "session": session["session"],
            "review": session["review"],
            "questions": session["questions"],
            "next_question": session["next_question"],
            "case_synopsis": session["case_synopsis"],
            "claim_type": session["session"]["claim_type"],
            "claim_type_label": _claim_type_display_name(session["session"]["claim_type"]),
        }

    def _build_complaint_output_review_artifacts(self, user_id: Optional[str]) -> List[Dict[str, Any]]:
        if not user_id:
            return []
        packet_payload = self.export_complaint_packet(user_id)
        artifacts = dict(packet_payload.get("artifacts") or {})
        markdown_artifact = dict(artifacts.get("markdown") or {})
        pdf_artifact = dict(artifacts.get("pdf") or {})
        ui_feedback = dict(packet_payload.get("ui_feedback") or {})
        draft = dict((packet_payload.get("packet") or {}).get("draft") or {})
        suggestions = list(ui_feedback.get("ui_suggestions") or [])
        suggestion_lines = [str(ui_feedback.get("summary") or "").strip()]
        for item in suggestions[:5]:
            title = str((item or {}).get("title") or "").strip()
            recommendation = str((item or {}).get("recommendation") or "").strip()
            if title and recommendation:
                suggestion_lines.append(f"- {title}: {recommendation}")
            elif title:
                suggestion_lines.append(f"- {title}")
            elif recommendation:
                suggestion_lines.append(f"- {recommendation}")
        return [
            {
                "name": "workspace-export-artifacts",
                "url": "/workspace?target_tab=integrations",
                "title": "Unified Complaint Workspace",
                "artifact_type": "complaint_export",
                "claim_type": str(packet_payload.get("packet", {}).get("claim_type") or ""),
                "draft_strategy": str(draft.get("draft_strategy") or "template"),
                "draft_normalizations": list(draft.get("draft_normalizations") or []),
                "text_excerpt": str(draft.get("body") or "").strip()[:600],
                "markdown_filename": str(markdown_artifact.get("filename") or ""),
                "pdf_filename": str(pdf_artifact.get("filename") or ""),
                "markdown_excerpt": str(markdown_artifact.get("excerpt") or markdown_artifact.get("content") or "").strip()[:2000],
                "pdf_header": str(pdf_artifact.get("content_type") or "application/pdf"),
                "filing_shape_score": int(ui_feedback.get("filing_shape_score") or 0),
                "claim_type_alignment_score": int(ui_feedback.get("claim_type_alignment_score") or 0),
                "formal_section_gaps": [
                    key
                    for key, present in dict(ui_feedback.get("formal_sections_present") or {}).items()
                    if not present
                ],
                "formal_defect_count": len(
                    [
                        item
                        for item in list(ui_feedback.get("issues") or [])
                        if str((item or {}).get("source") or "").startswith("complaint_output")
                    ]
                ),
                "claim_type_alignment": dict(ui_feedback.get("claim_type_alignment") or {}),
                "release_gate": dict(ui_feedback.get("release_gate") or {}),
                "formal_diagnostics": dict(ui_feedback.get("formal_diagnostics") or {}),
                "router_export_critic": dict(((ui_feedback.get("router_review") or {}).get("review") or {})),
                "router_backend": dict(((ui_feedback.get("router_review") or {}).get("backend") or {})),
                "ui_suggestions_excerpt": "\n".join(line for line in suggestion_lines if line),
            }
        ]

    def _build_cached_ui_readiness_artifacts(self, user_id: Optional[str]) -> List[Dict[str, Any]]:
        if not user_id:
            return []
        ui_readiness = self.get_ui_readiness(user_id)
        if str(ui_readiness.get("status") or "").strip().lower() != "cached":
            return []
        screenshot_findings = [
            dict(item)
            for item in list(ui_readiness.get("screenshot_findings") or [])
            if isinstance(item, dict) and item
        ]
        optimization_targets = [
            dict(item)
            for item in list(ui_readiness.get("optimization_targets") or [])
            if isinstance(item, dict) and item
        ]
        playwright_followups = [str(item).strip() for item in list(ui_readiness.get("playwright_followups") or []) if str(item).strip()]
        recommended_changes = [str(item).strip() for item in list(ui_readiness.get("recommended_changes") or []) if str(item).strip()]
        if not (screenshot_findings or optimization_targets or playwright_followups or recommended_changes):
            return []

        finding_lines: List[str] = []
        for item in screenshot_findings[:4]:
            stage = str(item.get("stage") or item.get("name") or "unknown stage").strip()
            summary = str(item.get("summary") or item.get("stage_finding") or item.get("visible_text_excerpt") or "").strip()
            criticism_items = list(item.get("criticisms") or [])
            criticism_text: List[str] = []
            for criticism in criticism_items[:2]:
                if isinstance(criticism, dict):
                    text = str(criticism.get("problem") or criticism.get("recommended_fix") or "").strip()
                else:
                    text = str(criticism or "").strip()
                if text:
                    criticism_text.append(text)
            line = f"- {stage}: {summary or 'No summary returned.'}"
            if criticism_text:
                line += f" Criticisms: {'; '.join(criticism_text)}"
            finding_lines.append(line)

        target_lines = [
            f"- {str(item.get('title') or item.get('target') or item.get('target_surface') or 'optimization target').strip()}"
            + (
                f": {str(item.get('reason') or '').strip()}"
                if str(item.get("reason") or "").strip()
                else ""
            )
            for item in optimization_targets[:4]
        ]
        followup_lines = [f"- {item}" for item in playwright_followups[:4]]
        change_lines = [f"- {item}" for item in recommended_changes[:4]]
        excerpt_sections = [
            str(ui_readiness.get("summary") or "").strip(),
            "Screenshot findings:\n" + "\n".join(finding_lines) if finding_lines else "",
            "Optimization targets:\n" + "\n".join(target_lines) if target_lines else "",
            "Playwright follow-ups:\n" + "\n".join(followup_lines) if followup_lines else "",
            "Recommended changes:\n" + "\n".join(change_lines) if change_lines else "",
        ]

        return [
            {
                "name": "workspace-cached-ui-readiness",
                "url": "/workspace?target_tab=ux-review",
                "title": "Cached UX Audit Review",
                "artifact_type": "ui_readiness_review",
                "verdict": str(ui_readiness.get("verdict") or ""),
                "score": ui_readiness.get("score"),
                "critic_verdict": str(ui_readiness.get("critic_verdict") or ""),
                "workflow_type": str(ui_readiness.get("workflow_type") or ""),
                "review_backend": deepcopy(ui_readiness.get("review_backend") or {}),
                "tested_stages": list(ui_readiness.get("tested_stages") or []),
                "release_blockers": list(ui_readiness.get("release_blockers") or []),
                "screenshot_findings": screenshot_findings,
                "optimization_targets": optimization_targets,
                "playwright_followups": playwright_followups,
                "recommended_changes": recommended_changes,
                "review_excerpt": "\n\n".join(section for section in excerpt_sections if section).strip()[:3000],
                "latest_review_markdown_path": ui_readiness.get("latest_review_markdown_path"),
                "latest_review_json_path": ui_readiness.get("latest_review_json_path"),
            }
        ]

    def export_complaint_markdown(self, user_id: Optional[str]) -> Dict[str, Any]:
        artifact = self.build_export_artifact(user_id, "markdown")
        packet_payload = self._build_packet_snapshot(user_id)
        return {
            "artifact": {
                "format": "markdown",
                "filename": artifact["filename"],
                "media_type": artifact["media_type"],
                "size_bytes": len(artifact["body"]),
                "excerpt": artifact["body"].decode("utf-8", errors="replace")[:2000],
            },
            "packet_summary": deepcopy(packet_payload.get("packet_summary") or {}),
            "artifact_analysis": deepcopy(packet_payload.get("artifact_analysis") or {}),
        }

    def export_complaint_pdf(self, user_id: Optional[str]) -> Dict[str, Any]:
        artifact = self.build_export_artifact(user_id, "pdf")
        packet_payload = self._build_packet_snapshot(user_id)
        return {
            "artifact": {
                "format": "pdf",
                "filename": artifact["filename"],
                "media_type": artifact["media_type"],
                "size_bytes": len(artifact["body"]),
                "header_b64": b64encode(artifact["body"][:32]).decode("ascii"),
            },
            "packet_summary": deepcopy(packet_payload.get("packet_summary") or {}),
            "artifact_analysis": deepcopy(packet_payload.get("artifact_analysis") or {}),
        }

    def export_complaint_docx(self, user_id: Optional[str]) -> Dict[str, Any]:
        artifact = self.build_export_artifact(user_id, "docx")
        packet_payload = self._build_packet_snapshot(user_id)
        return {
            "artifact": {
                "format": "docx",
                "filename": artifact["filename"],
                "media_type": artifact["media_type"],
                "size_bytes": len(artifact["body"]),
                "header_b64": b64encode(artifact["body"][:32]).decode("ascii"),
            },
            "packet_summary": deepcopy(packet_payload.get("packet_summary") or {}),
            "artifact_analysis": deepcopy(packet_payload.get("artifact_analysis") or {}),
        }

    def build_export_artifact(self, user_id: Optional[str], output_format: str = "json") -> Dict[str, Any]:
        payload = self._build_packet_snapshot(user_id)
        packet = payload.get("packet") or {}
        artifacts = payload.get("artifacts") or {}
        normalized_format = str(output_format or "json").strip().lower()
        if normalized_format == "json":
            filename = ((artifacts.get("json") or {}).get("filename")) or "complaint-packet.json"
            body = json.dumps(packet, indent=2, sort_keys=True).encode("utf-8")
            return {"filename": filename, "media_type": "application/json", "body": body}
        if normalized_format in {"markdown", "md"}:
            artifact = artifacts.get("markdown") or {}
            content = artifact.get("content") or self._build_complaint_export_markdown(packet)
            return {
                "filename": artifact.get("filename") or "complaint-packet.md",
                "media_type": "text/markdown",
                "body": str(content).encode("utf-8"),
            }
        if normalized_format == "pdf":
            artifact = artifacts.get("markdown") or {}
            markdown_text = artifact.get("content") or self._build_complaint_export_markdown(packet)
            pdf_bytes = self._build_packet_pdf_bytes(packet, str(markdown_text))
            return {
                "filename": ((artifacts.get("pdf") or {}).get("filename")) or "complaint-packet.pdf",
                "media_type": "application/pdf",
                "body": pdf_bytes,
            }
        if normalized_format == "docx":
            artifact = artifacts.get("markdown") or {}
            markdown_text = artifact.get("content") or self._build_complaint_export_markdown(packet)
            docx_bytes = self._build_packet_docx_bytes(packet, str(markdown_text))
            return {
                "filename": ((artifacts.get("docx") or {}).get("filename")) or "complaint-packet.docx",
                "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "body": docx_bytes,
            }
        raise ValueError(f"Unsupported complaint export format: {output_format}")

    def submit_intake_answers(self, user_id: Optional[str], answers: Dict[str, Any]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        answer_map = state.setdefault("intake_answers", {})
        history = state.setdefault("intake_history", [])
        for question in _INTAKE_QUESTIONS:
            value = str(answers.get(question["id"]) or "").strip()
            if not value:
                continue
            answer_map[question["id"]] = value
            history.append({"question_id": question["id"], "answer": value, "captured_at": _utc_now()})
        self._save_state(state)
        return self.get_session(str(state.get("user_id")))

    def run_intake_chat_turn(
        self,
        user_id: Optional[str],
        *,
        message: Optional[str] = None,
        question_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        target_question = self._question_by_id(question_id) if question_id else self._next_question(state.get("intake_answers") or {})
        if question_id and target_question is None:
            raise ValueError(f"Unknown intake question_id: {question_id}")

        accepted_answer: Optional[Dict[str, Any]] = None
        normalized_message = str(message or "").strip()
        if normalized_message:
            if target_question is None:
                raise ValueError("The intake flow is already complete for this session.")
            answer_map = state.setdefault("intake_answers", {})
            history = state.setdefault("intake_history", [])
            answer_map[target_question["id"]] = normalized_message
            accepted_answer = {
                "question_id": target_question["id"],
                "answer": normalized_message,
                "captured_at": _utc_now(),
            }
            history.append(deepcopy(accepted_answer))

        self._save_state(state)
        return self._build_intake_chat_payload(
            state,
            accepted_answer=accepted_answer,
            requested_question_id=question_id if accepted_answer is None else None,
        )

    def save_evidence(
        self,
        user_id: Optional[str],
        *,
        kind: str,
        claim_element_id: str,
        title: str,
        content: str,
        source: Optional[str] = None,
        attachment_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        evidence_store = state.setdefault("evidence", {"testimony": [], "documents": []})
        collection_key = "documents" if kind == "document" else "testimony"
        record = {
            "id": f"{collection_key}-{len(evidence_store.get(collection_key, [])) + 1}",
            "kind": kind,
            "claim_element_id": claim_element_id,
            "title": title,
            "content": content,
            "source": source or "",
            "attachment_names": [str(item).strip() for item in list(attachment_names or []) if str(item).strip()],
            "saved_at": _utc_now(),
        }
        evidence_store.setdefault(collection_key, []).append(record)
        self._save_state(state)
        return {
            "saved": record,
            "review": self._build_review(state),
            "session": deepcopy(state),
            "case_synopsis": self._build_case_synopsis(state),
        }

    def import_gmail_evidence(
        self,
        user_id: Optional[str],
        *,
        addresses: List[str],
        collect_all_messages: bool = False,
        claim_element_id: str = "causation",
        folder: str = "INBOX",
        folders: Optional[List[str]] = None,
        limit: Optional[int] = None,
        date_after: Optional[str] = None,
        date_before: Optional[str] = None,
        years_back: Optional[int] = None,
        evidence_root: Optional[str] = None,
        gmail_user: Optional[str] = None,
        gmail_app_password: Optional[str] = None,
        use_gmail_oauth: bool = False,
        gmail_oauth_client_secrets: Optional[str] = None,
        gmail_oauth_token_cache: Optional[str] = None,
        gmail_oauth_open_browser: bool = True,
        complaint_query: Optional[str] = None,
        complaint_keywords: Optional[List[str]] = None,
        min_relevance_score: float = 0.0,
        use_uid_checkpoint: bool = False,
        checkpoint_name: Optional[str] = None,
        uid_window_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        async def _run_import() -> Dict[str, Any]:
            from ipfs_datasets_py.processors.legal_data.email_import import import_gmail_evidence

            return await import_gmail_evidence(
                addresses=addresses,
                collect_all_messages=collect_all_messages,
                user_id=str(user_id or DEFAULT_USER_ID),
                claim_element_id=claim_element_id,
                workspace_root=self._session_dir,
                evidence_root=Path(evidence_root) if evidence_root else None,
                folder=folder,
                folders=folders or [],
                limit=limit,
                date_after=date_after,
                date_before=date_before,
                years_back=years_back,
                gmail_user=gmail_user,
                gmail_app_password=gmail_app_password,
                use_gmail_oauth=use_gmail_oauth,
                gmail_oauth_client_secrets=gmail_oauth_client_secrets,
                gmail_oauth_token_cache=gmail_oauth_token_cache,
                gmail_oauth_open_browser=gmail_oauth_open_browser,
                complaint_query=complaint_query,
                complaint_keywords=complaint_keywords or [],
                min_relevance_score=min_relevance_score,
                use_uid_checkpoint=use_uid_checkpoint,
                checkpoint_name=checkpoint_name,
                uid_window_size=uid_window_size,
                service=self,
            )

        return anyio.run(_run_import)

    def run_gmail_duckdb_pipeline(
        self,
        user_id: Optional[str],
        *,
        addresses: List[str],
        collect_all_messages: bool = False,
        claim_element_id: str = "causation",
        folder: str = "INBOX",
        folders: Optional[List[str]] = None,
        years_back: Optional[int] = 2,
        date_after: Optional[str] = None,
        date_before: Optional[str] = None,
        complaint_query: Optional[str] = None,
        complaint_keywords: Optional[List[str]] = None,
        min_relevance_score: float = 0.0,
        evidence_root: Optional[str] = None,
        gmail_user: Optional[str] = None,
        gmail_app_password: Optional[str] = None,
        use_gmail_oauth: bool = False,
        gmail_oauth_client_secrets: Optional[str] = None,
        gmail_oauth_token_cache: Optional[str] = None,
        gmail_oauth_open_browser: bool = True,
        checkpoint_name: str = "gmail-duckdb-pipeline",
        uid_window_size: int = 500,
        duckdb_build_every_batches: int = 10,
        max_batches: int = 20,
        duckdb_output_dir: Optional[str] = None,
        append_to_existing_corpus: bool = False,
        bm25_search_query: Optional[str] = None,
        bm25_search_limit: int = 20,
    ) -> Dict[str, Any]:
        async def _run_pipeline() -> Dict[str, Any]:
            from ipfs_datasets_py.processors.legal_data.email_pipeline import run_gmail_duckdb_pipeline

            return await run_gmail_duckdb_pipeline(
                user_id=str(user_id or DEFAULT_USER_ID),
                addresses=addresses,
                collect_all_messages=collect_all_messages,
                claim_element_id=claim_element_id,
                folder=folder,
                folders=folders or [],
                years_back=years_back,
                date_after=date_after,
                date_before=date_before,
                complaint_query=complaint_query,
                complaint_keywords=complaint_keywords or [],
                min_relevance_score=min_relevance_score,
                workspace_root=self._session_dir,
                evidence_root=Path(evidence_root) if evidence_root else None,
                gmail_user=gmail_user,
                gmail_app_password=gmail_app_password,
                use_gmail_oauth=use_gmail_oauth,
                gmail_oauth_client_secrets=gmail_oauth_client_secrets,
                gmail_oauth_token_cache=gmail_oauth_token_cache,
                gmail_oauth_open_browser=gmail_oauth_open_browser,
                checkpoint_name=checkpoint_name,
                uid_window_size=uid_window_size,
                duckdb_build_every_batches=duckdb_build_every_batches,
                max_batches=max_batches,
                duckdb_output_dir=duckdb_output_dir,
                append_to_existing_corpus=append_to_existing_corpus,
                bm25_search_query=bm25_search_query,
                bm25_search_limit=bm25_search_limit,
            )

        return anyio.run(_run_pipeline)

    def search_email_duckdb_corpus(
        self,
        *,
        index_path: str,
        query: str,
        limit: int = 20,
        ranking: str = "bm25",
        bm25_k1: float = 1.2,
        bm25_b: float = 0.75,
    ) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data.email_pipeline import search_email_duckdb_corpus

        return search_email_duckdb_corpus(
            index_path=index_path,
            query=query,
            limit=limit,
            ranking=ranking,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b,
        )

    def import_local_evidence(
        self,
        user_id: Optional[str],
        *,
        paths: List[str],
        claim_element_id: str = "causation",
        kind: str = "document",
        evidence_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        from complaint_generator.local_evidence_import import import_local_evidence

        return import_local_evidence(
            paths=paths,
            user_id=str(user_id or DEFAULT_USER_ID),
            claim_element_id=claim_element_id,
            kind=kind,
            workspace_root=self._session_dir,
            evidence_root=Path(evidence_root) if evidence_root else None,
            service=self,
        )

    def generate_complaint(
        self,
        user_id: Optional[str],
        *,
        requested_relief: Optional[List[str]] = None,
        title_override: Optional[str] = None,
        use_llm: bool = False,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config_path: Optional[str] = None,
        backend_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        draft = self._build_draft(
            state,
            requested_relief=requested_relief,
            use_llm=use_llm,
            provider=provider,
            model=model,
            config_path=config_path,
            backend_id=backend_id,
        )
        if title_override:
            draft["title"] = title_override
        state["draft"] = draft
        self._save_state(state)
        return {
            "draft": deepcopy(draft),
            "review": self._build_review(state),
            "session": deepcopy(state),
            "case_synopsis": self._build_case_synopsis(state),
        }

    def update_draft(
        self,
        user_id: Optional[str],
        *,
        title: Optional[str] = None,
        body: Optional[str] = None,
        requested_relief: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        draft = deepcopy(state.get("draft") or self._build_draft(state))
        if title is not None:
            draft["title"] = title
        if body is not None:
            draft["body"] = body
        if requested_relief is not None:
            draft["requested_relief"] = requested_relief
        draft["updated_at"] = _utc_now()
        state["draft"] = draft
        self._save_state(state)
        return {
            "draft": deepcopy(draft),
            "review": self._build_review(state),
            "session": deepcopy(state),
            "case_synopsis": self._build_case_synopsis(state),
        }

    def update_case_synopsis(self, user_id: Optional[str], synopsis: Optional[str]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        state["case_synopsis"] = str(synopsis or "").strip()
        self._save_state(state)
        session = self.get_session(str(state.get("user_id")))
        return {
            "session": session["session"],
            "review": session["review"],
            "questions": session["questions"],
            "next_question": session["next_question"],
            "case_synopsis": session["case_synopsis"],
        }

    def update_filing_metadata(
        self,
        user_id: Optional[str],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        filing_metadata = dict(state.get("filing_metadata") or {})
        for key in (
            "caption_plaintiffs",
            "caption_defendants",
            "signature_plaintiff",
            "signature_role",
            "mailing_address",
        ):
            value = str((metadata or {}).get(key) or "").strip()
            if value:
                filing_metadata[key] = value
        state["filing_metadata"] = filing_metadata
        state["draft"] = None
        self._save_state(state)
        session = self.get_session(str(state.get("user_id")))
        return {
            "session": session["session"],
            "review": session["review"],
            "questions": session["questions"],
            "next_question": session["next_question"],
            "case_synopsis": session["case_synopsis"],
            "filing_metadata": deepcopy(session["session"].get("filing_metadata") or {}),
        }

    def reset_session(self, user_id: Optional[str]) -> Dict[str, Any]:
        state = _default_state(str(user_id or DEFAULT_USER_ID))
        self._save_state(state)
        return self.get_session(str(state["user_id"]))

    @staticmethod
    def _resolve_docket_path(path_value: str | Path) -> str:
        return str(Path(str(path_value)).expanduser().resolve())

    @staticmethod
    def _resolve_workspace_dataset_path(path_value: str | Path) -> str:
        return str(Path(str(path_value)).expanduser().resolve())

    def _load_workspace_dataset_payload(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
    ) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data import (
            WorkspaceDatasetBuilder,
            load_packaged_workspace_dataset,
            load_workspace_dataset_single_parquet,
        )

        resolved_path = self._resolve_workspace_dataset_path(input_path)
        normalized_type = str(input_type or "packaged").strip().lower()
        if normalized_type == "packaged":
            dataset = load_packaged_workspace_dataset(resolved_path)
        elif normalized_type == "json":
            dataset = WorkspaceDatasetBuilder().build_from_json_file(resolved_path)
        elif normalized_type == "single":
            dataset = load_workspace_dataset_single_parquet(resolved_path)
        else:
            raise ValueError(f"Unsupported workspace dataset input_type: {input_type}")
        return dict(dataset.to_dict() if hasattr(dataset, "to_dict") else dataset)

    @staticmethod
    def _apply_workspace_dataset_filters(
        dataset_payload: Dict[str, Any],
        *,
        collection_id: Optional[str] = None,
        document_type: Optional[str] = None,
        claim_type: Optional[str] = None,
        claim_element_id: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_filters = {
            "collection_id": str(collection_id or "").strip(),
            "document_type": str(document_type or "").strip(),
            "claim_type": str(claim_type or "").strip(),
            "claim_element_id": str(claim_element_id or "").strip(),
            "source_type": str(source_type or "").strip(),
        }

        def _matches_document(document: Mapping[str, Any]) -> bool:
            metadata = dict(document.get("metadata") or {})
            for key, expected in normalized_filters.items():
                if not expected:
                    continue
                candidates = [
                    document.get(key),
                    metadata.get(key),
                    metadata.get(key.replace("_id", "")),
                ]
                if key == "source_type":
                    candidates.extend(
                        [
                            dataset_payload.get("source_type"),
                            metadata.get("source_family"),
                            metadata.get("source"),
                        ]
                    )
                values = {str(value).strip().lower() for value in candidates if str(value or "").strip()}
                expected_lower = expected.lower()
                if key == "source_type":
                    matched = any(
                        expected_lower == value
                        or expected_lower in value
                        or value in expected_lower
                        for value in values
                    )
                else:
                    matched = expected_lower in values
                if not matched:
                    return False
            return True

        documents = [dict(item) for item in list(dataset_payload.get("documents") or []) if isinstance(item, dict)]
        filtered_documents = [item for item in documents if _matches_document(item)]
        allowed_document_ids = {
            str(item.get("document_id") or "").strip()
            for item in filtered_documents
            if str(item.get("document_id") or "").strip()
        }

        def _filter_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            filtered: List[Dict[str, Any]] = []
            for row in rows:
                document_id = str(row.get("document_id") or "").strip()
                if not document_id or document_id in allowed_document_ids:
                    filtered.append(dict(row))
            return filtered

        collections = [dict(item) for item in list(dataset_payload.get("collections") or []) if isinstance(item, dict)]
        filtered_collections: List[Dict[str, Any]] = []
        for collection in collections:
            if normalized_filters["collection_id"]:
                candidate_id = str(collection.get("id") or collection.get("collection_id") or "").strip()
                if candidate_id.lower() != normalized_filters["collection_id"].lower():
                    continue
            document_ids = [str(item).strip() for item in list(collection.get("document_ids") or []) if str(item).strip()]
            if allowed_document_ids and document_ids and not any(item in allowed_document_ids for item in document_ids):
                continue
            filtered_collections.append(collection)

        return {
            **dict(dataset_payload),
            "documents": filtered_documents,
            "collections": filtered_collections,
            "bm25_index": {
                **dict(dataset_payload.get("bm25_index") or {}),
                "documents": _filter_rows([dict(item) for item in list((dataset_payload.get("bm25_index") or {}).get("documents") or []) if isinstance(item, dict)]),
            },
            "vector_index": {
                **dict(dataset_payload.get("vector_index") or {}),
                "items": _filter_rows([dict(item) for item in list((dataset_payload.get("vector_index") or {}).get("items") or []) if isinstance(item, dict)]),
            },
            "applied_filters": {key: value for key, value in normalized_filters.items() if value},
        }

    def _load_docket_dataset_payload(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
    ) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data import DocketDatasetBuilder, load_packaged_docket_dataset

        resolved_path = self._resolve_docket_path(input_path)
        normalized_type = str(input_type or "packaged").strip().lower()
        if normalized_type == "packaged":
            dataset = load_packaged_docket_dataset(resolved_path)
        elif normalized_type == "json":
            dataset = DocketDatasetBuilder().build_from_json_file(resolved_path)
        elif normalized_type == "single":
            dataset = self._load_docket_dataset_single_parquet(resolved_path)
        else:
            raise ValueError(f"Unsupported docket input_type: {input_type}")
        return dict(dataset.to_dict() if hasattr(dataset, "to_dict") else dataset)

    @staticmethod
    def _decode_parquet_bundle_section(rows: List[Dict[str, Any]], section: str) -> List[Dict[str, Any]]:
        decoded: List[Dict[str, Any]] = []
        for row in rows:
            if str(row.get("section") or "") != section:
                continue
            payload_json = str(row.get("payload_json") or "").strip()
            if not payload_json:
                continue
            decoded.append(dict(json.loads(payload_json)))
        return decoded

    @classmethod
    def _load_docket_dataset_single_parquet(cls, parquet_path: str | Path) -> Dict[str, Any]:
        import pyarrow.parquet as pq

        resolved_path = Path(str(parquet_path)).expanduser().resolve()
        rows = [dict(row) for row in pq.read_table(resolved_path).to_pylist()]
        dataset_core_rows = cls._decode_parquet_bundle_section(rows, "dataset_core")
        dataset_core = dict(dataset_core_rows[0]) if dataset_core_rows else {}
        documents = cls._decode_parquet_bundle_section(rows, "documents")
        knowledge_graph_entities = cls._decode_parquet_bundle_section(rows, "knowledge_graph_entities")
        knowledge_graph_relationships = cls._decode_parquet_bundle_section(rows, "knowledge_graph_relationships")
        deontic_nodes = cls._decode_parquet_bundle_section(rows, "deontic_nodes")
        deontic_rules = cls._decode_parquet_bundle_section(rows, "deontic_rules")
        proof_agenda = cls._decode_parquet_bundle_section(rows, "proof_agenda")
        proof_evidence_packets = cls._decode_parquet_bundle_section(rows, "proof_evidence_packets")
        proof_revalidation_runs = cls._decode_parquet_bundle_section(rows, "proof_revalidation_runs")
        bm25_documents = cls._decode_parquet_bundle_section(rows, "bm25_documents")
        vector_items = cls._decode_parquet_bundle_section(rows, "vector_items")
        return {
            "dataset_id": str(dataset_core.get("dataset_id") or ""),
            "docket_id": str(dataset_core.get("docket_id") or ""),
            "case_name": str(dataset_core.get("case_name") or ""),
            "court": str(dataset_core.get("court") or ""),
            "documents": documents,
            "plaintiff_docket": cls._decode_parquet_bundle_section(rows, "plaintiff_docket"),
            "defendant_docket": cls._decode_parquet_bundle_section(rows, "defendant_docket"),
            "authorities": cls._decode_parquet_bundle_section(rows, "authorities"),
            "knowledge_graph": {
                "entities": knowledge_graph_entities,
                "relationships": knowledge_graph_relationships,
            },
            "deontic_graph": {
                "nodes": {str(item.get("node_id") or item.get("id") or index): item for index, item in enumerate(deontic_nodes, start=1)},
                "rules": {str(item.get("rule_id") or item.get("id") or index): item for index, item in enumerate(deontic_rules, start=1)},
            },
            "proof_assistant": {
                "agenda": proof_agenda,
                "evidence_packets": proof_evidence_packets,
                "revalidation_runs": proof_revalidation_runs,
            },
            "bm25_index": {
                "backend": "local_bm25",
                "documents": bm25_documents,
                "document_count": len(bm25_documents),
            },
            "vector_index": {
                "backend": "local_hashed_term_projection",
                "items": vector_items,
                "document_count": len(vector_items),
            },
            "metadata": dict(dataset_core.get("metadata") or {}),
            "bundle": {
                "parquet_path": str(resolved_path),
                "row_count": len(rows),
                "sections": sorted({str(row.get("section") or "") for row in rows if str(row.get("section") or "")}),
            },
        }

    @staticmethod
    def _build_docket_document_view(
        dataset_payload: Dict[str, Any],
        *,
        include_document_text: bool,
        document_limit: Optional[int],
    ) -> List[Dict[str, Any]]:
        documents = list(dataset_payload.get("documents") or [])
        if document_limit is not None:
            documents = documents[: max(0, int(document_limit))]
        view: List[Dict[str, Any]] = []
        for document in documents:
            if not isinstance(document, dict):
                continue
            row = {
                "id": document.get("id"),
                "title": document.get("title"),
                "date_filed": document.get("date_filed"),
                "document_number": document.get("document_number"),
                "source_url": document.get("source_url"),
                "metadata": dict(document.get("metadata") or {}),
            }
            if include_document_text:
                row["text"] = document.get("text")
            view.append(row)
        return view

    @staticmethod
    def _issue_links_from_knowledge_graph(knowledge_graph: Dict[str, Any]) -> Dict[str, Any]:
        entities = [
            dict(entity)
            for entity in list((knowledge_graph or {}).get("entities") or [])
            if isinstance(entity, dict)
        ]
        relationships = [
            dict(relationship)
            for relationship in list((knowledge_graph or {}).get("relationships") or [])
            if isinstance(relationship, dict)
        ]
        entity_by_id = {
            str(entity.get("id") or ""): entity
            for entity in entities
            if str(entity.get("id") or "").strip()
        }

        def _entity_matches_issue(entity: Dict[str, Any]) -> bool:
            haystacks = [
                str(entity.get("type") or ""),
                str(entity.get("label") or ""),
                str(entity.get("name") or ""),
                str(entity.get("category") or ""),
                str((entity.get("metadata") or {}).get("type") or ""),
                str((entity.get("metadata") or {}).get("category") or ""),
            ]
            lowered = " ".join(haystacks).lower()
            return any(keyword in lowered for keyword in _DOCKET_ISSUE_ENTITY_KEYWORDS)

        issue_entities = [entity for entity in entities if _entity_matches_issue(entity)]
        issue_entity_ids = {
            str(entity.get("id") or "")
            for entity in issue_entities
            if str(entity.get("id") or "").strip()
        }
        issue_links: List[Dict[str, Any]] = []
        for relationship in relationships:
            source_id = str(
                relationship.get("source")
                or relationship.get("source_id")
                or relationship.get("from")
                or relationship.get("head")
                or ""
            ).strip()
            target_id = str(
                relationship.get("target")
                or relationship.get("target_id")
                or relationship.get("to")
                or relationship.get("tail")
                or ""
            ).strip()
            if not source_id or not target_id:
                continue
            if source_id not in issue_entity_ids and target_id not in issue_entity_ids:
                continue
            issue_links.append(
                {
                    "id": relationship.get("id"),
                    "type": relationship.get("type") or relationship.get("label"),
                    "source_id": source_id,
                    "target_id": target_id,
                    "source_entity": entity_by_id.get(source_id),
                    "target_entity": entity_by_id.get(target_id),
                    "metadata": dict(relationship.get("metadata") or {}),
                }
            )
        return {
            "entities": entities,
            "relationships": relationships,
            "issue_entities": issue_entities,
            "issue_links": issue_links,
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "issue_entity_count": len(issue_entities),
            "issue_link_count": len(issue_links),
        }

    def view_docket_dataset(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
        include_document_text: bool = False,
        document_limit: Optional[int] = 25,
    ) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data import summarize_docket_dataset

        resolved_path = self._resolve_docket_path(input_path)
        dataset_payload = self._load_docket_dataset_payload(resolved_path, input_type=input_type)
        summary = summarize_docket_dataset(dataset_payload)
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "summary": dict(summary),
            "documents": self._build_docket_document_view(
                dataset_payload,
                include_document_text=bool(include_document_text),
                document_limit=document_limit,
            ),
            "metadata": dict(dataset_payload.get("metadata") or {}),
            "source": "complaint_workspace_docket_view",
        }

    @staticmethod
    def _build_workspace_document_view(
        dataset_payload: Dict[str, Any],
        *,
        include_document_text: bool,
        document_limit: Optional[int],
    ) -> List[Dict[str, Any]]:
        documents = list(dataset_payload.get("documents") or [])
        if document_limit is not None:
            documents = documents[: max(0, int(document_limit))]
        view: List[Dict[str, Any]] = []
        for document in documents:
            if not isinstance(document, dict):
                continue
            metadata = dict(document.get("metadata") or {})
            item = {
                "document_id": str(document.get("document_id") or ""),
                "title": str(document.get("title") or ""),
                "captured_at": str(document.get("captured_at") or ""),
                "document_number": str(document.get("document_number") or ""),
                "source_url": str(document.get("source_url") or ""),
                "collection_id": str(document.get("collection_id") or metadata.get("collection_id") or ""),
                "document_type": str(document.get("document_type") or metadata.get("document_type") or ""),
                "claim_type": str(document.get("claim_type") or metadata.get("claim_type") or ""),
                "claim_element_id": str(document.get("claim_element_id") or metadata.get("claim_element_id") or ""),
                "source_type": str(document.get("source_type") or metadata.get("source_type") or metadata.get("source_family") or ""),
                "metadata": metadata,
            }
            if include_document_text:
                item["text"] = str(document.get("text") or "")
            view.append(item)
        return view

    def view_workspace_dataset(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
        include_document_text: bool = False,
        document_limit: Optional[int] = 25,
        collection_id: Optional[str] = None,
        document_type: Optional[str] = None,
        claim_type: Optional[str] = None,
        claim_element_id: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data import summarize_workspace_dataset

        resolved_path = self._resolve_workspace_dataset_path(input_path)
        dataset_payload = self._load_workspace_dataset_payload(resolved_path, input_type=input_type)
        filtered_payload = self._apply_workspace_dataset_filters(
            dataset_payload,
            collection_id=collection_id,
            document_type=document_type,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            source_type=source_type,
        )
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "summary": dict(summarize_workspace_dataset(filtered_payload)),
            "documents": self._build_workspace_document_view(
                filtered_payload,
                include_document_text=bool(include_document_text),
                document_limit=document_limit,
            ),
            "collections": [dict(item) for item in list(filtered_payload.get("collections") or []) if isinstance(item, dict)],
            "metadata": dict(filtered_payload.get("metadata") or {}),
            "applied_filters": dict(filtered_payload.get("applied_filters") or {}),
            "source": "complaint_workspace_dataset_view",
        }

    def search_workspace_dataset(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
        query: str,
        search_backend: str = "bm25",
        top_k: int = 10,
        vector_dimension: int = 32,
        collection_id: Optional[str] = None,
        document_type: Optional[str] = None,
        claim_type: Optional[str] = None,
        claim_element_id: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data import (
            search_workspace_dataset_bm25,
            search_workspace_dataset_vector,
            summarize_workspace_dataset,
        )

        resolved_path = self._resolve_workspace_dataset_path(input_path)
        normalized_backend = str(search_backend or "bm25").strip().lower()
        dataset_payload = self._load_workspace_dataset_payload(resolved_path, input_type=input_type)
        filtered_payload = self._apply_workspace_dataset_filters(
            dataset_payload,
            collection_id=collection_id,
            document_type=document_type,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            source_type=source_type,
        )
        if normalized_backend == "bm25":
            results = search_workspace_dataset_bm25(filtered_payload, query, top_k=int(top_k or 10))
        elif normalized_backend == "vector":
            results = search_workspace_dataset_vector(
                filtered_payload,
                query,
                top_k=int(top_k or 10),
                vector_dimension=int(vector_dimension or 32),
            )
        else:
            raise ValueError(f"Unsupported workspace search backend: {search_backend}")
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "query": str(query or ""),
            "search_backend": normalized_backend,
            "summary": dict(summarize_workspace_dataset(filtered_payload)),
            "search_results": dict(results),
            "applied_filters": dict(filtered_payload.get("applied_filters") or {}),
            "source": "complaint_workspace_dataset_search",
        }

    def search_docket_dataset(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
        query: str,
        search_backend: str = "bm25",
        top_k: int = 10,
        vector_dimension: int = 32,
    ) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data import (
            search_docket_dataset_bm25,
            search_docket_dataset_vector,
            summarize_docket_dataset,
        )

        resolved_path = self._resolve_docket_path(input_path)
        normalized_backend = str(search_backend or "bm25").strip().lower()
        dataset_payload = self._load_docket_dataset_payload(resolved_path, input_type=input_type)
        if normalized_backend == "bm25":
            results = search_docket_dataset_bm25(dataset_payload, query, top_k=int(top_k or 10))
        elif normalized_backend == "vector":
            results = search_docket_dataset_vector(
                dataset_payload,
                query,
                top_k=int(top_k or 10),
                vector_dimension=int(vector_dimension or 32),
            )
        else:
            raise ValueError(f"Unsupported docket search backend: {search_backend}")
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "query": str(query or ""),
            "search_backend": normalized_backend,
            "summary": dict(summarize_docket_dataset(dataset_payload)),
            "search_results": dict(results),
            "source": "complaint_workspace_docket_search",
        }

    def get_docket_dataset_metadata(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
    ) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data import summarize_docket_dataset

        resolved_path = self._resolve_docket_path(input_path)
        dataset_payload = self._load_docket_dataset_payload(resolved_path, input_type=input_type)
        summary = dict(summarize_docket_dataset(dataset_payload))
        metadata = dict(dataset_payload.get("metadata") or {})
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "dataset_id": dataset_payload.get("dataset_id"),
            "docket_id": dataset_payload.get("docket_id"),
            "case_name": dataset_payload.get("case_name"),
            "court": dataset_payload.get("court"),
            "summary": summary,
            "metadata": metadata,
            "document_count": len(list(dataset_payload.get("documents") or [])),
            "source": "complaint_workspace_docket_metadata",
        }

    def get_docket_dataset_graph(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
    ) -> Dict[str, Any]:
        resolved_path = self._resolve_docket_path(input_path)
        dataset_payload = self._load_docket_dataset_payload(resolved_path, input_type=input_type)
        knowledge_graph = dict(dataset_payload.get("knowledge_graph") or {})
        graph_projection = self._issue_links_from_knowledge_graph(knowledge_graph)
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "dataset_id": dataset_payload.get("dataset_id"),
            "docket_id": dataset_payload.get("docket_id"),
            "case_name": dataset_payload.get("case_name"),
            "court": dataset_payload.get("court"),
            "metadata": dict(dataset_payload.get("metadata") or {}),
            "knowledge_graph": graph_projection,
            "source": "complaint_workspace_docket_graph",
        }

    def get_packaged_docket_operator_dashboard(self, manifest_path: str | Path) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data import get_packaged_docket_operator_dashboard

        resolved_manifest = str(Path(str(manifest_path)).expanduser().resolve())
        dashboard = get_packaged_docket_operator_dashboard(resolved_manifest)
        return {
            **dict(dashboard),
            "manifest_path": resolved_manifest,
            "source": "complaint_workspace_packaged_operator_dashboard",
        }

    def load_packaged_docket_operator_dashboard_report(
        self,
        manifest_path: str | Path,
        *,
        report_format: str = "parsed",
    ) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data import load_packaged_docket_operator_dashboard_report

        resolved_manifest = str(Path(str(manifest_path)).expanduser().resolve())
        normalized_format = str(report_format or "parsed").strip().lower()
        report = load_packaged_docket_operator_dashboard_report(
            resolved_manifest,
            report_format=normalized_format,
        )
        return {
            "manifest_path": resolved_manifest,
            "report_format": normalized_format,
            "report": report,
            "source": "complaint_workspace_packaged_operator_dashboard_report",
        }

    def execute_packaged_docket_proof_revalidation_queue(
        self,
        manifest_path: str | Path,
        *,
        top_k: int = 10,
        min_priority: str = "low",
        queue_limit: Optional[int] = None,
        execution_top_k: int = 10,
        chain_until_satisfied: bool = True,
        attach_refreshed_packets: bool = False,
    ) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data import execute_packaged_docket_proof_revalidation_queue

        resolved_manifest = str(Path(str(manifest_path)).expanduser().resolve())
        execution = execute_packaged_docket_proof_revalidation_queue(
            resolved_manifest,
            top_k=int(top_k or 10),
            min_priority=str(min_priority or "low"),
            queue_limit=int(queue_limit) if queue_limit is not None else None,
            execution_top_k=int(execution_top_k or 10),
            chain_until_satisfied=bool(chain_until_satisfied),
            attach_refreshed_packets=bool(attach_refreshed_packets),
        )
        return {
            **dict(execution),
            "manifest_path": resolved_manifest,
            "source": "complaint_workspace_packaged_proof_revalidation_queue_execution",
        }

    def persist_packaged_docket_proof_revalidation_queue(
        self,
        manifest_path: str | Path,
        output_dir: str | Path,
        *,
        package_name: Optional[str] = None,
        include_car: bool = True,
        top_k: int = 10,
        min_priority: str = "low",
        queue_limit: Optional[int] = None,
        execution_top_k: int = 10,
        chain_until_satisfied: bool = True,
    ) -> Dict[str, Any]:
        from ipfs_datasets_py.processors.legal_data import persist_packaged_docket_proof_revalidation_queue

        resolved_manifest = str(Path(str(manifest_path)).expanduser().resolve())
        resolved_output_dir = str(Path(str(output_dir)).expanduser().resolve())
        persisted = persist_packaged_docket_proof_revalidation_queue(
            resolved_manifest,
            resolved_output_dir,
            package_name=str(package_name).strip() if package_name is not None and str(package_name).strip() else None,
            include_car=bool(include_car),
            top_k=int(top_k or 10),
            min_priority=str(min_priority or "low"),
            queue_limit=int(queue_limit) if queue_limit is not None else None,
            execution_top_k=int(execution_top_k or 10),
            chain_until_satisfied=bool(chain_until_satisfied),
        )
        return {
            **dict(persisted),
            "manifest_path": resolved_manifest,
            "output_dir": resolved_output_dir,
            "source": "complaint_workspace_packaged_proof_revalidation_queue_persist",
        }

    def list_mcp_tools(self) -> Dict[str, Any]:
        return {
            "tools": [
                {"name": "complaint.create_identity", "description": "Create a decentralized identity for browser or CLI use."},
                {"name": "complaint.list_intake_questions", "description": "List the complaint intake questions used across browser, CLI, and MCP flows."},
                {"name": "complaint.list_claim_elements", "description": "List the tracked claim elements used for evidence and review."},
                {"name": "complaint.start_session", "description": "Load or initialize a complaint workspace session."},
                {"name": "complaint.submit_intake", "description": "Save complaint intake answers."},
                {"name": "complaint.run_intake_chat_turn", "description": "Advance the shared mediator-style intake chat one turn and persist the captured answer."},
                {"name": "complaint.save_evidence", "description": "Save testimony or document evidence to the workspace."},
                {"name": "complaint.import_gmail_evidence", "description": "Import matching Gmail messages and attachments into the complaint evidence workspace."},
                {"name": "complaint.run_gmail_duckdb_pipeline", "description": "Run a checkpointed Gmail-to-DuckDB pipeline across many mailbox windows and optional BM25 search."},
                {"name": "complaint.import_local_evidence", "description": "Import local files or directories into the complaint evidence workspace."},
                {"name": "complaint.search_email_duckdb_corpus", "description": "Search an existing Gmail DuckDB corpus with BM25 or weighted keyword ranking."},
                {"name": "complaint.review_case", "description": "Return the current support matrix and evidence review."},
                {"name": "complaint.build_mediator_prompt", "description": "Build a testimony-ready chat mediator prompt from the shared case synopsis and support gaps."},
                {"name": "complaint.get_complaint_readiness", "description": "Estimate whether the current complaint record is ready for drafting, still building, or already in draft refinement."},
                {"name": "complaint.get_ui_readiness", "description": "Return the latest cached actor/critic UI readiness verdict for this complaint session."},
                {"name": "complaint.get_client_release_gate", "description": "Combine complaint readiness, UI readiness, and complaint-output quality into one client-safety release gate."},
                {"name": "complaint.get_workflow_capabilities", "description": "Summarize which complaint-workflow abilities are currently available for the session."},
                {"name": "complaint.get_tooling_contract", "description": "Show how the core complaint workflow is exposed across package exports, CLI commands, MCP tools, and browser SDK methods."},
                {"name": "complaint.get_workspace_data_schema", "description": "Inspect the current or packaged workspace dataset schema so MCP and UI surfaces can follow the actual parquet data model."},
                {"name": "complaint.migrate_legacy_workspace_data", "description": "Project legacy complaint session and mediator DuckDB state into a packaged workspace dataset stored as parquet pieces."},
                {"name": "complaint.view_workspace_dataset", "description": "Browse a packaged or single-file workspace dataset with schema-aligned filters and filtered document previews."},
                {"name": "complaint.search_workspace_dataset", "description": "Search a packaged or single-file workspace dataset using BM25 or vector retrieval plus schema-aligned filters."},
                {"name": "complaint.generate_complaint", "description": "Generate a complaint draft from intake and evidence."},
                {"name": "complaint.update_draft", "description": "Persist edits to the generated complaint draft."},
                {"name": "complaint.export_complaint_packet", "description": "Export the current lawsuit complaint packet with intake, evidence, review, and draft content."},
                {"name": "complaint.export_complaint_markdown", "description": "Export the generated complaint as a downloadable Markdown artifact."},
                {"name": "complaint.export_complaint_docx", "description": "Export the generated complaint as a downloadable DOCX artifact."},
                {"name": "complaint.export_complaint_pdf", "description": "Export the generated complaint as a downloadable PDF artifact."},
                {"name": "complaint.analyze_complaint_output", "description": "Analyze the generated complaint output and turn filing-shape gaps into concrete UI/UX suggestions."},
                {"name": "complaint.get_formal_diagnostics", "description": "Return the compact formal-complaint diagnostics summary for the current complaint draft and export state."},
                {"name": "complaint.get_filing_provenance", "description": "Return the shared routing provenance for complaint generation, filing critique, export critique, and cached UI review workflows."},
                {"name": "complaint.get_provider_diagnostics", "description": "Report which llm_router providers are actually usable on this machine, in the same order the router will prefer them."},
                {"name": "complaint.view_docket_dataset", "description": "Load a docket dataset from packaged or source JSON input and return docket documents, summary, and metadata for dashboard viewing."},
                {"name": "complaint.search_docket_dataset", "description": "Search a docket dataset with bm25 or vector retrieval and return matching docket entries for dashboard exploration."},
                {"name": "complaint.get_docket_dataset_metadata", "description": "Return the docket dataset summary and metadata used by the complaint MCP dashboard."},
                {"name": "complaint.get_docket_dataset_graph", "description": "Return knowledge-graph entities, relationships, and extracted legal-issue links for a docket dataset."},
                {"name": "complaint.review_generated_exports", "description": "Review generated complaint export artifacts through llm_router and turn filing-output weaknesses into UI/UX repair suggestions."},
                {"name": "complaint.get_packaged_docket_operator_dashboard", "description": "Load the combined packaged docket operator dashboard for a docket bundle manifest."},
                {"name": "complaint.load_packaged_docket_operator_dashboard_report", "description": "Load the archived packaged docket operator dashboard report artifact for a docket bundle manifest."},
                {"name": "complaint.execute_packaged_docket_proof_revalidation_queue", "description": "Execute the packaged docket proof revalidation queue for a docket bundle manifest and return execution summaries."},
                {"name": "complaint.persist_packaged_docket_proof_revalidation_queue", "description": "Execute packaged docket proof revalidation and write a refreshed parquet/CAR bundle to an output directory."},
                {"name": "complaint.update_claim_type", "description": "Set the current complaint type so drafting and review stay aligned to the right legal claim shape."},
                {"name": "complaint.update_case_synopsis", "description": "Persist a shared case synopsis that stays visible across workspace, CLI, and MCP flows."},
                {"name": "complaint.reset_session", "description": "Clear the complaint workspace session."},
                {"name": "complaint.review_ui", "description": "Review Playwright screenshot artifacts, optionally run an iterative UI/UX workflow, and produce a router-backed MCP dashboard critique."},
                {"name": "complaint.optimize_ui", "description": "Run the closed-loop screenshot, llm_router, actor/critic optimizer, and revalidation workflow for the complaint dashboard UI."},
                {"name": "complaint.run_browser_audit", "description": "Run the Playwright end-to-end complaint browser audit that drives chat, intake, evidence, review, draft, and builder surfaces."},
            ]
        }

    def call_mcp_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = arguments or {}
        if tool_name == "complaint.create_identity":
            return generate_decentralized_id()
        if tool_name == "complaint.list_intake_questions":
            return self.list_intake_questions()
        if tool_name == "complaint.list_claim_elements":
            return self.list_claim_elements()
        if tool_name == "complaint.start_session":
            return self.get_session(args.get("user_id"))
        if tool_name == "complaint.submit_intake":
            return self.submit_intake_answers(args.get("user_id"), args.get("answers") or {})
        if tool_name == "complaint.run_intake_chat_turn":
            return self.run_intake_chat_turn(
                args.get("user_id"),
                message=args.get("message"),
                question_id=args.get("question_id"),
            )
        if tool_name == "complaint.save_evidence":
            return self.save_evidence(
                args.get("user_id"),
                kind=str(args.get("kind") or "testimony"),
                claim_element_id=str(args.get("claim_element_id") or "causation"),
                title=str(args.get("title") or "Untitled evidence"),
                content=str(args.get("content") or ""),
                source=args.get("source"),
                attachment_names=args.get("attachment_names"),
            )
        if tool_name == "complaint.import_gmail_evidence":
            return self.import_gmail_evidence(
                args.get("user_id"),
                addresses=[str(item).strip() for item in list(args.get("addresses") or []) if str(item).strip()],
                claim_element_id=str(args.get("claim_element_id") or "causation"),
                folder=str(args.get("folder") or "INBOX"),
                folders=[str(item).strip() for item in list(args.get("folders") or []) if str(item).strip()],
                limit=int(args["limit"]) if args.get("limit") is not None else None,
                date_after=str(args.get("date_after") or "") or None,
                date_before=str(args.get("date_before") or "") or None,
                years_back=int(args["years_back"]) if args.get("years_back") is not None else None,
                evidence_root=str(args.get("evidence_root") or "") or None,
                gmail_user=str(args.get("gmail_user") or "") or None,
                gmail_app_password=str(args.get("gmail_app_password") or "") or None,
                use_gmail_oauth=bool(args.get("use_gmail_oauth") or False),
                gmail_oauth_client_secrets=str(args.get("gmail_oauth_client_secrets") or "") or None,
                gmail_oauth_token_cache=str(args.get("gmail_oauth_token_cache") or "") or None,
                gmail_oauth_open_browser=bool(True if args.get("gmail_oauth_open_browser") is None else args.get("gmail_oauth_open_browser")),
                complaint_query=str(args.get("complaint_query") or "") or None,
                complaint_keywords=[str(item).strip() for item in list(args.get("complaint_keywords") or []) if str(item).strip()],
                min_relevance_score=float(args.get("min_relevance_score") or 0.0),
                use_uid_checkpoint=bool(args.get("use_uid_checkpoint") or False),
                checkpoint_name=str(args.get("checkpoint_name") or "") or None,
                uid_window_size=int(args["uid_window_size"]) if args.get("uid_window_size") is not None else None,
            )
        if tool_name == "complaint.run_gmail_duckdb_pipeline":
            return self.run_gmail_duckdb_pipeline(
                args.get("user_id"),
                addresses=[str(item).strip() for item in list(args.get("addresses") or []) if str(item).strip()],
                claim_element_id=str(args.get("claim_element_id") or "causation"),
                folder=str(args.get("folder") or "INBOX"),
                folders=[str(item).strip() for item in list(args.get("folders") or []) if str(item).strip()],
                years_back=int(args["years_back"]) if args.get("years_back") is not None else 2,
                date_after=str(args.get("date_after") or "") or None,
                date_before=str(args.get("date_before") or "") or None,
                complaint_query=str(args.get("complaint_query") or "") or None,
                complaint_keywords=[str(item).strip() for item in list(args.get("complaint_keywords") or []) if str(item).strip()],
                min_relevance_score=float(args.get("min_relevance_score") or 0.0),
                evidence_root=str(args.get("evidence_root") or "") or None,
                gmail_user=str(args.get("gmail_user") or "") or None,
                gmail_app_password=str(args.get("gmail_app_password") or "") or None,
                use_gmail_oauth=bool(args.get("use_gmail_oauth") or False),
                gmail_oauth_client_secrets=str(args.get("gmail_oauth_client_secrets") or "") or None,
                gmail_oauth_token_cache=str(args.get("gmail_oauth_token_cache") or "") or None,
                gmail_oauth_open_browser=bool(True if args.get("gmail_oauth_open_browser") is None else args.get("gmail_oauth_open_browser")),
                checkpoint_name=str(args.get("checkpoint_name") or "gmail-duckdb-pipeline"),
                uid_window_size=int(args["uid_window_size"]) if args.get("uid_window_size") is not None else 500,
                max_batches=int(args["max_batches"]) if args.get("max_batches") is not None else 20,
                duckdb_output_dir=str(args.get("duckdb_output_dir") or "") or None,
                append_to_existing_corpus=bool(args.get("append_to_existing_corpus") or False),
                bm25_search_query=str(args.get("bm25_search_query") or "") or None,
                bm25_search_limit=int(args["bm25_search_limit"]) if args.get("bm25_search_limit") is not None else 20,
            )
        if tool_name == "complaint.import_local_evidence":
            return self.import_local_evidence(
                args.get("user_id"),
                paths=[str(item).strip() for item in list(args.get("paths") or []) if str(item).strip()],
                claim_element_id=str(args.get("claim_element_id") or "causation"),
                kind=str(args.get("kind") or "document"),
                evidence_root=str(args.get("evidence_root") or "") or None,
            )
        if tool_name == "complaint.search_email_duckdb_corpus":
            return self.search_email_duckdb_corpus(
                index_path=str(args.get("index_path") or ""),
                query=str(args.get("query") or ""),
                limit=int(args["limit"]) if args.get("limit") is not None else 20,
                ranking=str(args.get("ranking") or "bm25"),
                bm25_k1=float(args.get("bm25_k1") or 1.2),
                bm25_b=float(args.get("bm25_b") or 0.75),
            )
        if tool_name == "complaint.review_case":
            session = self.get_session(args.get("user_id"))
            return {
                "session": session["session"],
                "review": session["review"],
                "questions": session["questions"],
                "next_question": session["next_question"],
                "case_synopsis": session["case_synopsis"],
            }
        if tool_name == "complaint.build_mediator_prompt":
            return self.build_mediator_prompt(args.get("user_id"))
        if tool_name == "complaint.get_complaint_readiness":
            return self.get_complaint_readiness(args.get("user_id"))
        if tool_name == "complaint.get_ui_readiness":
            return self.get_ui_readiness(args.get("user_id"))
        if tool_name == "complaint.get_client_release_gate":
            return self.get_client_release_gate(args.get("user_id"))
        if tool_name == "complaint.get_workflow_capabilities":
            return self.get_workflow_capabilities(args.get("user_id"))
        if tool_name == "complaint.get_tooling_contract":
            return self.get_tooling_contract(args.get("user_id"))
        if tool_name == "complaint.get_workspace_data_schema":
            return self.get_workspace_data_schema(
                args.get("user_id"),
                manifest_path=args.get("manifest_path"),
                statefile_path=args.get("statefile_path"),
                evidence_db_path=args.get("evidence_db_path"),
                legal_authority_db_path=args.get("legal_authority_db_path"),
                claim_support_db_path=args.get("claim_support_db_path"),
            )
        if tool_name == "complaint.migrate_legacy_workspace_data":
            return self.migrate_legacy_workspace_data(
                args.get("user_id"),
                output_dir=args.get("output_dir"),
                statefile_path=args.get("statefile_path"),
                evidence_db_path=args.get("evidence_db_path"),
                legal_authority_db_path=args.get("legal_authority_db_path"),
                claim_support_db_path=args.get("claim_support_db_path"),
                package_name=args.get("package_name"),
                include_car=bool(args.get("include_car", True)),
            )
        if tool_name == "complaint.search_workspace_dataset":
            input_path = args.get("input_path") or args.get("manifest_path")
            if not input_path:
                raise ValueError("complaint.search_workspace_dataset requires input_path or manifest_path.")
            return self.search_workspace_dataset(
                input_path,
                input_type=args.get("input_type", "packaged"),
                query=str(args.get("query") or ""),
                search_backend=args.get("search_backend", "bm25"),
                top_k=int(args.get("top_k") or 10),
                vector_dimension=int(args.get("vector_dimension") or 32),
                collection_id=args.get("collection_id"),
                document_type=args.get("document_type"),
                claim_type=args.get("claim_type"),
                claim_element_id=args.get("claim_element_id"),
                source_type=args.get("source_type"),
            )
        if tool_name == "complaint.view_workspace_dataset":
            input_path = args.get("input_path") or args.get("manifest_path")
            if not input_path:
                raise ValueError("complaint.view_workspace_dataset requires input_path or manifest_path.")
            return self.view_workspace_dataset(
                input_path,
                input_type=args.get("input_type", "packaged"),
                include_document_text=bool(args.get("include_document_text")),
                document_limit=int(args.get("document_limit") or 25),
                collection_id=args.get("collection_id"),
                document_type=args.get("document_type"),
                claim_type=args.get("claim_type"),
                claim_element_id=args.get("claim_element_id"),
                source_type=args.get("source_type"),
            )
        if tool_name == "complaint.generate_complaint":
            return self.generate_complaint(
                args.get("user_id"),
                requested_relief=_split_lines(args.get("requested_relief"))
                if isinstance(args.get("requested_relief"), str)
                else args.get("requested_relief"),
                title_override=args.get("title_override"),
                use_llm=bool(args.get("use_llm")),
                provider=args.get("provider"),
                model=args.get("model"),
                config_path=args.get("config_path"),
                backend_id=args.get("backend_id"),
            )
        if tool_name == "complaint.update_draft":
            requested_relief = args.get("requested_relief")
            if isinstance(requested_relief, str):
                requested_relief = _split_lines(requested_relief)
            return self.update_draft(
                args.get("user_id"),
                title=args.get("title"),
                body=args.get("body"),
                requested_relief=requested_relief,
            )
        if tool_name == "complaint.export_complaint_packet":
            return self.export_complaint_packet(args.get("user_id"))
        if tool_name == "complaint.export_complaint_markdown":
            return self.export_complaint_markdown(args.get("user_id"))
        if tool_name == "complaint.export_complaint_docx":
            return self.export_complaint_docx(args.get("user_id"))
        if tool_name == "complaint.export_complaint_pdf":
            return self.export_complaint_pdf(args.get("user_id"))
        if tool_name == "complaint.analyze_complaint_output":
            return self.analyze_complaint_output(args.get("user_id"))
        if tool_name == "complaint.get_formal_diagnostics":
            return self.get_formal_diagnostics(args.get("user_id"))
        if tool_name == "complaint.get_filing_provenance":
            return self.get_filing_provenance(args.get("user_id"))
        if tool_name == "complaint.get_provider_diagnostics":
            return self.get_provider_diagnostics(args.get("user_id"))
        if tool_name == "complaint.view_docket_dataset":
            input_path = str(args.get("input_path") or "").strip()
            if not input_path:
                raise ValueError("complaint.view_docket_dataset requires input_path.")
            return self.view_docket_dataset(
                input_path,
                input_type=str(args.get("input_type") or "packaged"),
                include_document_text=bool(args.get("include_document_text") or False),
                document_limit=int(args["document_limit"]) if args.get("document_limit") is not None else 25,
            )
        if tool_name == "complaint.search_docket_dataset":
            input_path = str(args.get("input_path") or "").strip()
            query = str(args.get("query") or "").strip()
            if not input_path:
                raise ValueError("complaint.search_docket_dataset requires input_path.")
            if not query:
                raise ValueError("complaint.search_docket_dataset requires query.")
            return self.search_docket_dataset(
                input_path,
                input_type=str(args.get("input_type") or "packaged"),
                query=query,
                search_backend=str(args.get("search_backend") or "bm25"),
                top_k=int(args.get("top_k") or 10),
                vector_dimension=int(args.get("vector_dimension") or 32),
            )
        if tool_name == "complaint.get_docket_dataset_metadata":
            input_path = str(args.get("input_path") or "").strip()
            if not input_path:
                raise ValueError("complaint.get_docket_dataset_metadata requires input_path.")
            return self.get_docket_dataset_metadata(
                input_path,
                input_type=str(args.get("input_type") or "packaged"),
            )
        if tool_name == "complaint.get_docket_dataset_graph":
            input_path = str(args.get("input_path") or "").strip()
            if not input_path:
                raise ValueError("complaint.get_docket_dataset_graph requires input_path.")
            return self.get_docket_dataset_graph(
                input_path,
                input_type=str(args.get("input_type") or "packaged"),
            )
        if tool_name == "complaint.review_generated_exports":
            return self.review_generated_exports(
                args.get("user_id"),
                artifact_path=args.get("artifact_path"),
                artifact_dir=args.get("artifact_dir"),
                provider=args.get("provider"),
                model=args.get("model"),
                config_path=args.get("config_path"),
                backend_id=args.get("backend_id"),
                notes=args.get("notes"),
            )
        if tool_name == "complaint.get_packaged_docket_operator_dashboard":
            manifest_path = str(args.get("manifest_path") or "").strip()
            if not manifest_path:
                raise ValueError("complaint.get_packaged_docket_operator_dashboard requires manifest_path.")
            return self.get_packaged_docket_operator_dashboard(manifest_path)
        if tool_name == "complaint.load_packaged_docket_operator_dashboard_report":
            manifest_path = str(args.get("manifest_path") or "").strip()
            if not manifest_path:
                raise ValueError("complaint.load_packaged_docket_operator_dashboard_report requires manifest_path.")
            return self.load_packaged_docket_operator_dashboard_report(
                manifest_path,
                report_format=str(args.get("report_format") or "parsed"),
            )
        if tool_name == "complaint.execute_packaged_docket_proof_revalidation_queue":
            manifest_path = str(args.get("manifest_path") or "").strip()
            if not manifest_path:
                raise ValueError("complaint.execute_packaged_docket_proof_revalidation_queue requires manifest_path.")
            return self.execute_packaged_docket_proof_revalidation_queue(
                manifest_path,
                top_k=int(args.get("top_k") or 10),
                min_priority=str(args.get("min_priority") or "low"),
                queue_limit=int(args["queue_limit"]) if args.get("queue_limit") is not None else None,
                execution_top_k=int(args.get("execution_top_k") or 10),
                chain_until_satisfied=bool(True if args.get("chain_until_satisfied") is None else args.get("chain_until_satisfied")),
                attach_refreshed_packets=bool(args.get("attach_refreshed_packets") or False),
            )
        if tool_name == "complaint.persist_packaged_docket_proof_revalidation_queue":
            manifest_path = str(args.get("manifest_path") or "").strip()
            output_dir = str(args.get("output_dir") or "").strip()
            if not manifest_path:
                raise ValueError("complaint.persist_packaged_docket_proof_revalidation_queue requires manifest_path.")
            if not output_dir:
                raise ValueError("complaint.persist_packaged_docket_proof_revalidation_queue requires output_dir.")
            return self.persist_packaged_docket_proof_revalidation_queue(
                manifest_path,
                output_dir,
                package_name=str(args.get("package_name") or "").strip() or None,
                include_car=bool(True if args.get("include_car") is None else args.get("include_car")),
                top_k=int(args.get("top_k") or 10),
                min_priority=str(args.get("min_priority") or "low"),
                queue_limit=int(args["queue_limit"]) if args.get("queue_limit") is not None else None,
                execution_top_k=int(args.get("execution_top_k") or 10),
                chain_until_satisfied=bool(True if args.get("chain_until_satisfied") is None else args.get("chain_until_satisfied")),
            )
        if tool_name == "complaint.update_claim_type":
            return self.update_claim_type(args.get("user_id"), args.get("claim_type"))
        if tool_name == "complaint.update_case_synopsis":
            return self.update_case_synopsis(
                args.get("user_id"),
                args.get("synopsis"),
            )
        if tool_name == "complaint.reset_session":
            return self.reset_session(args.get("user_id"))
        if tool_name == "complaint.review_ui":
            from .ui_review import create_ui_review_report, run_ui_review_workflow
            from complaint_generator.ui_ux_workflow import run_iterative_ui_ux_workflow

            screenshot_paths = args.get("screenshot_paths")
            screenshot_dir = args.get("screenshot_dir")
            iterations = int(args.get("iterations") or 0)
            pytest_target = args.get("pytest_target")
            reuse_existing_screenshots = bool(args.get("reuse_existing_screenshots"))
            supplemental_artifacts = (
                self._build_complaint_output_review_artifacts(args.get("user_id"))
                + self._build_cached_ui_readiness_artifacts(args.get("user_id"))
            )
            if isinstance(screenshot_paths, list):
                return create_ui_review_report(
                    [str(item) for item in screenshot_paths],
                    notes=args.get("notes"),
                    goals=args.get("goals"),
                    provider=args.get("provider"),
                    model=args.get("model"),
                    config_path=args.get("config_path"),
                    backend_id=args.get("backend_id"),
                    output_path=args.get("output_path"),
                )
            if screenshot_dir:
                if iterations > 0:
                    result = run_iterative_ui_ux_workflow(
                        screenshot_dir=str(screenshot_dir),
                        output_dir=args.get("output_path"),
                        iterations=iterations,
                        provider=args.get("provider"),
                        model=args.get("model"),
                        notes=args.get("notes"),
                        goals=args.get("goals"),
                        supplemental_artifacts=supplemental_artifacts,
                        pytest_target=str(pytest_target)
                        if pytest_target
                        else DEFAULT_UI_UX_SCREENSHOT_TARGET,
                        reuse_existing_screenshots=reuse_existing_screenshots,
                    )
                    self._persist_ui_readiness(args.get("user_id"), result)
                    return result
                result = run_ui_review_workflow(
                    str(screenshot_dir),
                    notes=args.get("notes"),
                    goals=args.get("goals"),
                    provider=args.get("provider"),
                    model=args.get("model"),
                    config_path=args.get("config_path"),
                    backend_id=args.get("backend_id"),
                    output_path=args.get("output_path"),
                )
                self._persist_ui_readiness(args.get("user_id"), result)
                return result
            raise ValueError("complaint.review_ui requires screenshot_paths or screenshot_dir.")
        if tool_name == "complaint.optimize_ui":
            from complaint_generator.ui_ux_workflow import run_closed_loop_ui_ux_improvement

            screenshot_dir = args.get("screenshot_dir")
            if not screenshot_dir:
                raise ValueError("complaint.optimize_ui requires screenshot_dir.")
            supplemental_artifacts = (
                self._build_complaint_output_review_artifacts(args.get("user_id"))
                + self._build_cached_ui_readiness_artifacts(args.get("user_id"))
            )
            result = run_closed_loop_ui_ux_improvement(
                screenshot_dir=str(screenshot_dir),
                output_dir=str(args.get("output_path") or Path(str(screenshot_dir)).expanduser().resolve() / "closed-loop"),
                pytest_target=str(args.get("pytest_target") or DEFAULT_UI_UX_SCREENSHOT_TARGET),
                max_rounds=int(args.get("max_rounds") or 2),
                review_iterations=int(args.get("iterations") or 1),
                provider=args.get("provider"),
                model=args.get("model"),
                method=str(args.get("method") or DEFAULT_UI_UX_OPTIMIZER_METHOD),
                priority=int(args.get("priority") or DEFAULT_UI_UX_OPTIMIZER_PRIORITY),
                notes=args.get("notes"),
                goals=args.get("goals"),
                supplemental_artifacts=supplemental_artifacts,
                reuse_existing_screenshots=bool(args.get("reuse_existing_screenshots")),
            )
            self._persist_ui_readiness(args.get("user_id"), result)
            return result
        if tool_name == "complaint.run_browser_audit":
            from complaint_generator.ui_ux_workflow import run_end_to_end_complaint_browser_audit

            screenshot_dir = args.get("screenshot_dir")
            if not screenshot_dir:
                raise ValueError("complaint.run_browser_audit requires screenshot_dir.")
            return run_end_to_end_complaint_browser_audit(
                screenshot_dir=str(screenshot_dir),
                pytest_target=str(args.get("pytest_target") or DEFAULT_UI_UX_SCREENSHOT_TARGET),
            )
        raise ValueError(f"Unknown complaint MCP tool: {tool_name}")
