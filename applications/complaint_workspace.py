from __future__ import annotations

import anyio
import json
import os
import re
import shutil
import threading
import uuid
import zipfile
from base64 import b64encode
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape


DEFAULT_USER_ID = "did:key:anonymous"
DEFAULT_UI_UX_OPTIMIZER_METHOD = "actor_critic"
DEFAULT_UI_UX_OPTIMIZER_PRIORITY = 90
DEFAULT_LLM_DRAFT_TIMEOUT_SECONDS = 20
DEFAULT_LLM_DRAFT_TIMEOUTS_BY_PROVIDER: Dict[str, int] = {
    "codex": 60,
    "codex_cli": 60,
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
    "save_evidence",
    "review_case",
    "build_mediator_prompt",
    "get_complaint_readiness",
    "get_ui_readiness",
    "get_client_release_gate",
    "get_workflow_capabilities",
    "generate_complaint",
    "export_complaint_packet",
    "export_complaint_markdown",
    "export_complaint_docx",
    "export_complaint_pdf",
    "analyze_complaint_output",
    "get_formal_diagnostics",
    "get_filing_provenance",
    "get_provider_diagnostics",
    "review_generated_exports",
    "review_ui",
    "optimize_ui",
    "run_browser_audit",
]
_CLI_COMMAND_CONTRACT: List[str] = [
    "identity",
    "session",
    "answer",
    "add-evidence",
    "review",
    "mediator-prompt",
    "complaint-readiness",
    "ui-readiness",
    "client-release-gate",
    "capabilities",
    "generate",
    "export-packet",
    "export-markdown",
    "export-docx",
    "export-pdf",
    "analyze-output",
    "formal-diagnostics",
    "filing-provenance",
    "provider-diagnostics",
    "review-exports",
    "review-ui",
    "optimize-ui",
    "browser-audit",
]
_BROWSER_SDK_METHOD_CONTRACT: List[str] = [
    "createIdentity",
    "bootstrapWorkspace",
    "getSession",
    "submitIntake",
    "saveEvidence",
    "reviewCase",
    "buildMediatorPrompt",
    "getComplaintReadiness",
    "getUiReadiness",
    "getClientReleaseGate",
    "getWorkflowCapabilities",
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
    "reviewUiArtifacts",
    "optimizeUiArtifacts",
    "runBrowserAudit",
]
_CORE_FLOW_CONTRACT: Dict[str, Dict[str, str]] = {
    "intake": {
        "package_export": "submit_intake_answers",
        "cli_command": "answer",
        "mcp_tool": "complaint.submit_intake",
        "browser_sdk_method": "submitIntake",
    },
    "evidence_capture": {
        "package_export": "save_evidence",
        "cli_command": "add-evidence",
        "mcp_tool": "complaint.save_evidence",
        "browser_sdk_method": "saveEvidence",
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


def _normalize_fragment(value: Optional[str], fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"[.?!,;:]+$", "", text)
    return text or fallback


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


def _pleading_timeline_sentence(value: Optional[str], fallback: str) -> str:
    text = _normalize_fragment(value, fallback)
    if not text:
        return _pleading_sentence(fallback, fallback)
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
    title = str(item.get("title") or f"Untitled {kind}").strip()
    element_label = _claim_element_label(item.get("claim_element_id")).lower()
    if kind == "testimony":
        return f"testimony presently identified as '{title}' on the {element_label} element"
    return f"documentary exhibit presently identified as '{title}' on the {element_label} element"


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
        "draft": None,
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
        payload = json.loads(path.read_text())
        if not isinstance(payload, dict):
            return _default_state(user_id)
        payload.setdefault("user_id", user_id)
        payload["claim_type"] = _normalize_claim_type(payload.get("claim_type"))
        payload.setdefault("case_synopsis", "")
        payload.setdefault("intake_answers", {})
        payload.setdefault("intake_history", [])
        payload.setdefault("evidence", {"testimony": [], "documents": []})
        payload.setdefault("draft", None)
        payload.setdefault("ui_readiness", None)
        return payload

    def _save_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["updated_at"] = _utc_now()
        path = self._session_path(str(state.get("user_id") or DEFAULT_USER_ID))
        path.write_text(json.dumps(state, indent=2, sort_keys=True))
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
        testimony_items = list(evidence.get("testimony") or [])
        document_items = list(evidence.get("documents") or [])
        claim_type = _normalize_claim_type(state.get("claim_type"))
        claim_label = _claim_type_display_name(claim_type)
        plaintiff = answers.get("party_name") or "Plaintiff"
        defendant = answers.get("opposing_party") or "Defendant"
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
            answers.get("timeline"),
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
        testimony_reference_lines = _unique_preserve_order([
            f"Plaintiff expects to offer testimony presently identified as '{item.get('title') or 'Untitled testimony'}' in support of the {_claim_element_label(item.get('claim_element_id')).lower()} element."
            for item in testimony_items[:3]
        ])
        document_reference_lines = _unique_preserve_order([
            f"Plaintiff expects to offer documentary exhibit '{item.get('title') or 'Untitled document'}' in support of the {_claim_element_label(item.get('claim_element_id')).lower()} element."
            for item in document_items[:3]
        ])
        testimony_summary = "; ".join(_unique_preserve_order([
            _formal_evidence_summary_item(item, kind="testimony")
            for item in testimony_items[:3]
        ])) or "No witness or complainant testimony is presently identified"
        document_summary = "; ".join(_unique_preserve_order([
            _formal_evidence_summary_item(item, kind="document")
            for item in document_items[:3]
        ])) or "No documentary exhibits are presently identified"
        complaint_heading = f"COMPLAINT FOR {claim_label.upper()}"
        nature_of_action = {
            "retaliation": (
                f"1. {plaintiff} brings this retaliation complaint against {defendant}. "
                f"This civil action arises from {defendant}'s retaliatory response after {plaintiff} engaged in protected activity, including {pleading_activity}."
            ),
            "employment_discrimination": (
                f"1. {plaintiff} brings this employment discrimination complaint against {defendant}. "
                f"This civil action arises from discriminatory workplace treatment, unequal terms or conditions, and resulting harm."
            ),
            "housing_discrimination": (
                f"1. {plaintiff} brings this housing discrimination complaint against {defendant}. "
                f"This civil action arises from discriminatory denial, limitation, interference, or retaliation affecting housing rights or benefits."
            ),
            "due_process_failure": (
                f"1. {plaintiff} brings this due process complaint against {defendant}. "
                f"This civil action arises from adverse action imposed without the notice, hearing, review, or procedural protections required by law."
            ),
            "consumer_protection": (
                f"1. {plaintiff} brings this consumer protection complaint against {defendant}. "
                f"This civil action arises from unfair, deceptive, fraudulent, or otherwise unlawful business practices that caused injury."
            ),
        }.get(
            claim_type,
            f"1. {plaintiff} brings this {claim_label.lower()} complaint against {defendant}. "
            f"This civil action arises from unlawful conduct that injured {plaintiff}.",
        )
        relief_paragraph = {
            "retaliation": (
                "2. Plaintiff seeks back pay, front pay or reinstatement, compensatory damages, attorney's fees and costs, "
                "equitable relief, and such further relief as may be just to remedy Defendant's retaliatory acts and the losses flowing from them."
            ),
            "employment_discrimination": (
                f"2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy discriminatory employment practices, "
                f"restore lost opportunities, and address the harm caused when Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse employment action')}."
            ),
            "housing_discrimination": (
                f"2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy discriminatory housing practices, "
                f"preserve housing stability, and address the harm caused when Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered a housing-related deprivation')}."
            ),
            "due_process_failure": (
                f"2. Plaintiff seeks declaratory relief, equitable relief, damages, and such further relief as may be just to remedy the procedural deprivation "
                f"and the harm caused by the challenged action through which Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered a deprivation without adequate process')}."
            ),
            "consumer_protection": (
                f"2. Plaintiff seeks damages, restitution, equitable relief, and such further relief as may be just to remedy deceptive or unfair consumer practices "
                f"and the harm caused when Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered a consumer-facing injury')}."
            ),
        }.get(
            claim_type,
            f"2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy unlawful conduct and the harm caused when Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse action')}.",
        )
        jurisdiction_paragraph = {
            "retaliation": (
                "3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges retaliation for protected activity "
                "and seeks relief for materially adverse acts taken in response to that activity."
            ),
            "employment_discrimination": (
                "3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges discriminatory employment practices, "
                "workplace bias, and related unlawful employment actions for which judicial relief is available."
            ),
            "housing_discrimination": (
                "3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges discriminatory housing practices, "
                "interference with housing rights or benefits, and related misconduct for which judicial relief is available."
            ),
            "due_process_failure": (
                "3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges deprivation without constitutionally "
                "or statutorily required notice, hearing, review, or other procedural protections."
            ),
            "consumer_protection": (
                "3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges unfair, deceptive, or unlawful consumer-facing conduct "
                "for which damages, equitable relief, restitution, or related remedies may be awarded."
            ),
        }.get(
            claim_type,
            "3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges unlawful conduct for which judicial relief is available.",
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
                f"5. Plaintiff {plaintiff} is an individual who engaged in protected activity and was thereafter harmed by the retaliatory conduct described below.",
                f"6. Defendant {defendant} is the party from whom relief is sought and is responsible for the retaliatory actions alleged in this pleading.",
            ),
            "employment_discrimination": (
                f"5. Plaintiff {plaintiff} is the employee, applicant, or worker harmed by the discriminatory employment conduct described below.",
                f"6. Defendant {defendant} is the employer or responsible actor from whom relief is sought for the discriminatory employment actions alleged in this pleading.",
            ),
            "housing_discrimination": (
                f"5. Plaintiff {plaintiff} is the housing applicant, tenant, resident, or person seeking housing-related rights or benefits who was harmed by the discriminatory conduct described below.",
                f"6. Defendant {defendant} is the housing provider, landlord, authority, manager, or responsible actor from whom relief is sought for the housing discrimination alleged in this pleading.",
            ),
            "due_process_failure": (
                f"5. Plaintiff {plaintiff} is the person deprived of rights, benefits, or protected interests without adequate process.",
                f"6. Defendant {defendant} is the person or entity responsible for the challenged deprivation and the missing procedural safeguards alleged in this pleading.",
            ),
            "consumer_protection": (
                f"5. Plaintiff {plaintiff} is the consumer or injured person harmed by the deceptive, unfair, or unlawful conduct described below.",
                f"6. Defendant {defendant} is the seller, business, servicer, or responsible actor from whom relief is sought for the consumer-facing conduct alleged in this pleading.",
            ),
        }.get(
            claim_type,
            (
                f"5. Plaintiff {plaintiff} is the person harmed by the conduct described below.",
                f"6. Defendant {defendant} is the party from whom relief is sought and is responsible for the conduct alleged in this pleading.",
            ),
        )
        factual_allegation_lines = {
            "retaliation": [
                f"7. Plaintiff engaged in protected activity by {pleading_activity}.",
                "8. That protected activity constituted protected opposition, reporting, or participation activity under the governing anti-retaliation framework.",
                f"9. Within days of that protected activity, Defendant took materially adverse action against Plaintiff by {_adverse_action_clause(answers.get('adverse_action'), 'taking materially adverse action against Plaintiff')}.",
                f"10. The relevant chronology is as follows: {_pleading_timeline_sentence(answers.get('timeline'), 'The events occurred in close temporal proximity')}",
                f"11. As a direct and proximate result of Defendant's conduct, Plaintiff {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
            "employment_discrimination": [
                f"7. Plaintiff alleges facts showing discriminatory employment treatment, including protected conduct or circumstances such as {pleading_activity}.",
                f"8. Defendant thereafter took or maintained adverse employment action by which Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse employment action')}.",
                f"9. The employment chronology is as follows: {_pleading_timeline_sentence(answers.get('timeline'), 'The relevant employment events occurred in close succession')}",
                "10. The present record supports an inference of discriminatory motive, disparate treatment, prohibited bias, retaliation, or other unlawful employment decision-making.",
                f"11. As a direct and proximate result of Defendant's conduct, Plaintiff {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
            "housing_discrimination": [
                f"7. Plaintiff alleges that they sought, used, requested, or protected housing-related rights, accommodations, benefits, tenancy rights, or fair treatment, including {pleading_activity}.",
                f"8. Defendant thereafter denied, burdened, interfered with, or threatened housing-related rights or benefits when Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered a housing-related deprivation')}.",
                f"9. The housing-related chronology is as follows: {_pleading_timeline_sentence(answers.get('timeline'), 'The housing-related events occurred in close succession')}",
                "10. The present record supports an inference that Defendant acted in a discriminatory manner, interfered with protected housing rights, or retaliated in connection with protected housing activity.",
                f"11. As a direct and proximate result of Defendant's conduct, Plaintiff {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
            "due_process_failure": [
                "7. Plaintiff alleges that Defendant imposed or maintained a deprivation affecting protected rights, interests, status, benefits, or property.",
                f"8. The challenged action is that Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered a deprivation without adequate process')}.",
                f"9. The chronology is as follows: {_pleading_timeline_sentence(answers.get('timeline'), 'The challenged events occurred in close succession')}",
                "10. Plaintiff alleges that the deprivation occurred without adequate notice, hearing, review, appeal, or other required procedural protection.",
                f"11. As a direct and proximate result of Defendant's conduct, Plaintiff {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
            "consumer_protection": [
                "7. Plaintiff alleges that Defendant engaged in deceptive, misleading, unfair, or otherwise unlawful consumer-facing conduct.",
                f"8. That conduct included or resulted in adverse action or consequences when Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered a consumer-facing injury')}.",
                f"9. The chronology is as follows: {_pleading_timeline_sentence(answers.get('timeline'), 'The relevant consumer-facing events occurred in close succession')}",
                "10. Plaintiff alleges that the challenged conduct caused consumer harm, financial loss, or other compensable injury in a transactional or service context.",
                f"11. As a direct and proximate result of Defendant's conduct, Plaintiff {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
        }.get(
            claim_type,
            [
                f"7. Plaintiff alleges conduct or circumstances including {pleading_activity}.",
                f"8. Defendant engaged in conduct through which Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse action')}.",
                f"9. The chronology is as follows: {_pleading_timeline_sentence(answers.get('timeline'), 'The relevant events occurred in close succession')}",
                "10. Plaintiff alleges facts supporting a plausible claim for relief.",
                f"11. As a direct and proximate result of Defendant's conduct, Plaintiff {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
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
                f"Plaintiff engaged in protected activity by {pleading_activity}, and Defendant knew or should have known of that protected conduct.",
                f"Defendant thereafter subjected Plaintiff to materially adverse action by {_adverse_action_clause(answers.get('adverse_action'), 'taking materially adverse action against Plaintiff')}, under circumstances supporting a causal inference of retaliation.",
                "The close temporal proximity, Defendant's knowledge of the protected activity, the evidentiary record, and the resulting harm plausibly support a retaliation claim and entitle Plaintiff to relief.",
            ],
            "employment_discrimination": [
                f"Plaintiff was subjected to adverse employment treatment described as {adverse_action}, in a manner that was discriminatory, disparate, or otherwise unlawful.",
                "The pleaded facts support an inference that Defendant's conduct was motivated by unlawful bias, protected status, protected conduct, or a prohibited employment practice.",
                "The evidentiary record and resulting harm support a plausible employment discrimination claim.",
            ],
            "housing_discrimination": [
                f"Defendant denied, limited, burdened, or interfered with housing-related rights, opportunities, services, or benefits through conduct described as {adverse_action}.",
                "The pleaded facts support an inference that Defendant acted in a discriminatory manner or retaliated in connection with protected housing activity, status, or rights.",
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
                f"12. Plaintiff presently relies on {evidence_count} identified evidentiary items. The witness proof currently identified includes: {testimony_summary}."
                if testimony_items
                else "12. Plaintiff presently relies on the evidentiary materials identified below and anticipates that testimonial proof may be supplemented through discovery, amendment, or sworn declarations."
            ),
            (
                f"13. Plaintiff presently identifies the following documents, exhibits, or records in support of this pleading: {document_summary}."
                if document_items
                else "13. Plaintiff has not yet attached documentary exhibits to this export, but preserves the right to supplement the pleading with records, correspondence, or other supporting materials."
            ),
            (
                f"14. Based on the information presently available, Plaintiff contends that the evidentiary record presently supports {support_count} core claim elements "
                f"and that {missing_count} areas, if any, may be further corroborated through discovery, amendment, or additional evidentiary development."
            ),
            (
                "15. Plaintiff gives notice that the identified testimony, documentary exhibits, and chronology materials constitute part of the evidentiary basis for this pleading "
                "and may be supplemented, authenticated, or amended as discovery proceeds."
            ),
        ]
        extra_evidence_lines = (testimony_reference_lines + document_reference_lines)[:2]
        evidentiary_lines.extend(
            f"{16 + index}. {line}"
            for index, line in enumerate(extra_evidence_lines)
        )
        claim_intro_paragraph = 16 + len(extra_evidence_lines)
        claim_detail_start = claim_intro_paragraph + 1
        body = "\n\n".join(
            [
                "IN THE UNITED STATES DISTRICT COURT",
                court_header,
                "",
                f"{plaintiff}, Plaintiff,",
                "v.",
                f"{defendant}, Defendant.",
                "",
                "Civil Action No. ________________",
                complaint_heading,
                "JURY TRIAL DEMANDED",
                "",
                (
                    f"Plaintiff {plaintiff}, proceeding pro se, alleges upon personal knowledge as to "
                    "their own acts and upon information and belief as to all other matters as follows:"
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
                f"{claim_intro_paragraph}. {plaintiff} repeats and realleges the preceding paragraphs as if fully set forth herein.",
                *[f"{claim_detail_start + index}. {line}" for index, line in enumerate(claim_paragraphs)],
                f"{claim_detail_start + 3}. Plaintiff has sustained damages and losses including {_sentence_fragment(answers.get('harm'), 'compensable harm')}.",
                (
                    f"{claim_detail_start + 4}. As a direct and proximate result of Defendant's retaliatory conduct, Plaintiff is entitled to recover damages, equitable relief, fees and costs where available, and such further relief as the Court deems just and proper."
                    if claim_type == "retaliation"
                    else f"{claim_detail_start + 4}. Defendant's acts were intentional, knowing, reckless, retaliatory, discriminatory, deceptive, or otherwise unlawful under the governing claim theory."
                ),
                "",
                "PRAYER FOR RELIEF",
                (
                    "Wherefore, Plaintiff respectfully requests judgment against Defendant on the retaliation claim alleged herein and seeks the following relief:"
                    if claim_type == "retaliation"
                    else "Wherefore, Plaintiff requests judgment against Defendant and the following relief:"
                ),
                "\n".join(relief_lines),
                "",
                "JURY DEMAND",
                "Plaintiff demands a trial by jury on all issues so triable.",
                "",
                "SIGNATURE BLOCK",
                f"Dated: ____________________",
                "",
                "Respectfully submitted,",
                "",
                f"{plaintiff}",
                "Plaintiff, Pro Se",
                "Address: ____________________",
                "Telephone: ____________________",
                "Email: ____________________",
            ]
        )
        draft = {
            "title": f"{plaintiff} v. {defendant} {claim_label} Complaint",
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
            refined_draft = self._refine_draft_with_llm_router(
                state,
                draft,
                provider=provider,
                model=model,
                config_path=config_path,
                backend_id=backend_id,
            )
            if refined_draft:
                return refined_draft
            if self._last_draft_refinement_error:
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
        party_name = answers.get("party_name") or "The complainant"
        opposing_party = answers.get("opposing_party") or "the opposing party"
        protected_activity = answers.get("protected_activity") or "an identified protected activity"
        adverse_action = answers.get("adverse_action") or "an adverse action"
        harm = answers.get("harm") or "described harm"
        timeline = answers.get("timeline") or "a still-developing timeline"
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
                "requested_provider": str(provider or "").strip() or None,
                "requested_model": str(model or "").strip() or None,
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
            "issue_counts": severity_counts,
            "summary": summary_text,
            "workflow_type": str((result or {}).get("workflow_type") or (result or {}).get("backend", {}).get("strategy") or "review"),
            "review_backend": deepcopy((result or {}).get("backend") or {}),
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
            "issue_counts": {"high": 0, "medium": 0, "low": 0},
            "workflow_type": None,
            "review_backend": {},
            "updated_at": None,
        }

    def get_filing_provenance(self, user_id: Optional[str]) -> Dict[str, Any]:
        payload = self.export_complaint_packet(user_id)
        packet = dict(payload.get("packet") or {})
        draft = dict(packet.get("draft") or {})
        packet_summary = dict(payload.get("packet_summary") or {})
        ui_feedback = dict(payload.get("ui_feedback") or {})
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        cached_ui_readiness = dict(state.get("ui_readiness") or {})
        cached_export_critic = dict(state.get("latest_export_critic") or {})
        export_critic_feedback = dict(cached_export_critic.get("complaint_output_feedback") or {})
        export_critic_aggregate = dict(cached_export_critic.get("aggregate") or {})
        export_router_backends = [
            deepcopy(item)
            for item in list(export_critic_aggregate.get("router_backends") or export_critic_feedback.get("router_backends") or [])
            if isinstance(item, dict) and item
        ]
        return {
            "user_id": str(packet.get("user_id") or user_id or DEFAULT_USER_ID),
            "claim_type": str(packet.get("claim_type") or ""),
            "draft_strategy": str(draft.get("draft_strategy") or "template"),
            "draft_backend": deepcopy(draft.get("draft_backend") or {}),
            "complaint_output_router_backend": deepcopy(packet_summary.get("complaint_output_router_backend") or {}),
            "complaint_output_router_backends": [
                deepcopy(item)
                for item in list(ui_feedback.get("router_backends") or [])
                if isinstance(item, dict) and item
            ],
            "export_critic_router_backends": export_router_backends,
            "ui_review_backend": deepcopy(cached_ui_readiness.get("review_backend") or {}),
            "ui_workflow_type": str(cached_ui_readiness.get("workflow_type") or "").strip() or "unavailable",
            "artifact_formats": list(packet_summary.get("artifact_formats") or []),
            "has_draft": bool(packet_summary.get("has_draft")),
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
        return {
            "user_id": str(user_id or DEFAULT_USER_ID),
            "package_exports": package_exports,
            "cli_commands": cli_commands,
            "mcp_tools": mcp_tools,
            "browser_sdk_methods": browser_sdk_methods,
            "core_flow_steps": core_flow_steps,
            "missing_exposures": missing_exposures,
            "all_core_flow_steps_exposed": not missing_exposures,
        }

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
        return {
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
        return {
            "user_id": str(analysis.get("user_id") or user_id or DEFAULT_USER_ID),
            "claim_type_alignment_score": int(ui_feedback.get("claim_type_alignment_score") or 0),
            "filing_shape_score": int(ui_feedback.get("filing_shape_score") or 0),
            "release_gate": deepcopy(ui_feedback.get("release_gate") or {}),
            "formal_diagnostics": diagnostics,
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
        openai_key = str(llm_router._resolve_openai_api_key() or "").strip()
        hf_token = str(llm_router._resolve_hf_api_token() or "").strip()
        copilot_provider = llm_router._builtin_provider_by_name("copilot_cli")

        providers = [
            {
                "name": "codex_cli",
                "available": bool(codex_path),
                "reason": "Codex CLI is installed and available on PATH." if codex_path else "Codex CLI binary not found on PATH.",
                "binary_path": codex_path or None,
                "credential_source": "local_codex_auth" if codex_path else "unavailable",
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
            },
        ]

        effective_default = next((item["name"] for item in providers if item["available"]), None)
        return {
            "user_id": str(user_id or DEFAULT_USER_ID),
            "forced_provider": forced_provider or None,
            "default_order": default_order,
            "effective_default_provider": forced_provider or effective_default,
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
        claim_element_id: str = "causation",
        folder: str = "INBOX",
        limit: Optional[int] = None,
        date_after: Optional[str] = None,
        date_before: Optional[str] = None,
        evidence_root: Optional[str] = None,
        gmail_user: Optional[str] = None,
        gmail_app_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        async def _run_import() -> Dict[str, Any]:
            from complaint_generator.email_import import import_gmail_evidence

            return await import_gmail_evidence(
                addresses=addresses,
                user_id=str(user_id or DEFAULT_USER_ID),
                claim_element_id=claim_element_id,
                workspace_root=self._session_dir,
                evidence_root=Path(evidence_root) if evidence_root else None,
                folder=folder,
                limit=limit,
                date_after=date_after,
                date_before=date_before,
                gmail_user=gmail_user,
                gmail_app_password=gmail_app_password,
                service=self,
            )

        return anyio.run(_run_import)

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

    def reset_session(self, user_id: Optional[str]) -> Dict[str, Any]:
        state = _default_state(str(user_id or DEFAULT_USER_ID))
        self._save_state(state)
        return self.get_session(str(state["user_id"]))

    def list_mcp_tools(self) -> Dict[str, Any]:
        return {
            "tools": [
                {"name": "complaint.create_identity", "description": "Create a decentralized identity for browser or CLI use."},
                {"name": "complaint.list_intake_questions", "description": "List the complaint intake questions used across browser, CLI, and MCP flows."},
                {"name": "complaint.list_claim_elements", "description": "List the tracked claim elements used for evidence and review."},
                {"name": "complaint.start_session", "description": "Load or initialize a complaint workspace session."},
                {"name": "complaint.submit_intake", "description": "Save complaint intake answers."},
                {"name": "complaint.save_evidence", "description": "Save testimony or document evidence to the workspace."},
                {"name": "complaint.import_gmail_evidence", "description": "Import matching Gmail messages and attachments into the complaint evidence workspace."},
                {"name": "complaint.review_case", "description": "Return the current support matrix and evidence review."},
                {"name": "complaint.build_mediator_prompt", "description": "Build a testimony-ready chat mediator prompt from the shared case synopsis and support gaps."},
                {"name": "complaint.get_complaint_readiness", "description": "Estimate whether the current complaint record is ready for drafting, still building, or already in draft refinement."},
                {"name": "complaint.get_ui_readiness", "description": "Return the latest cached actor/critic UI readiness verdict for this complaint session."},
                {"name": "complaint.get_client_release_gate", "description": "Combine complaint readiness, UI readiness, and complaint-output quality into one client-safety release gate."},
                {"name": "complaint.get_workflow_capabilities", "description": "Summarize which complaint-workflow abilities are currently available for the session."},
                {"name": "complaint.get_tooling_contract", "description": "Show how the core complaint workflow is exposed across package exports, CLI commands, MCP tools, and browser SDK methods."},
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
                {"name": "complaint.review_generated_exports", "description": "Review generated complaint export artifacts through llm_router and turn filing-output weaknesses into UI/UX repair suggestions."},
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
                limit=int(args["limit"]) if args.get("limit") is not None else None,
                date_after=str(args.get("date_after") or "") or None,
                date_before=str(args.get("date_before") or "") or None,
                evidence_root=str(args.get("evidence_root") or "") or None,
                gmail_user=str(args.get("gmail_user") or "") or None,
                gmail_app_password=str(args.get("gmail_app_password") or "") or None,
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
            supplemental_artifacts = self._build_complaint_output_review_artifacts(args.get("user_id"))
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
            supplemental_artifacts = self._build_complaint_output_review_artifacts(args.get("user_id"))
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
