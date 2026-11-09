from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from applications.complaint_workspace import ComplaintWorkspaceService


DEFAULT_STATEFILE = Path("/home/barberb/HACC/complaint-generator/statefiles/temporary-cli-session-latest.json")
DEFAULT_WORKSPACE_ROOT = Path("/home/barberb/HACC/workspace")
MIGRATED_SOURCES_ROOTNAME = "migrated_sources"

SOURCE_ROOTS = {
    "hacc_research": Path("/home/barberb/HACC/hacc_research"),
    "hacc_website": Path("/home/barberb/HACC/hacc_website"),
    "legal_data": Path("/home/barberb/HACC/legal_data"),
    "research_data": Path("/home/barberb/HACC/research_data"),
    "research_results": Path("/home/barberb/HACC/research_results"),
}

PRIMARY_POLICY_PATHS = [
    Path("/home/barberb/HACC/hacc_website/knowledge_graph/texts/a38c7914-ea37-4c2f-a815-711d4a97c92b.txt"),
    Path("/home/barberb/HACC/hacc_website/knowledge_graph/texts/8ee6f7d1-0c36-48e4-9677-336b95fb9858.txt"),
]
PRIMARY_LEGAL_PATHS = [
    Path("/home/barberb/HACC/research_data/raw_documents/HUD_Fair_Housing_Act.html"),
    Path("/home/barberb/HACC/research_data/raw_documents/ORS_Chapter_659A_Discrimination_Definitions_and_Procedures.html"),
    Path("/home/barberb/HACC/research_data/raw_documents/ORS_Chapter_456_Housing_Authorities.html"),
]
SUPPORTING_PROGRAM_PATHS = [
    Path("/home/barberb/HACC/hacc_website/knowledge_graph/texts/945af141-c7d1-4973-88c0-b57024243114.txt"),
    Path("/home/barberb/HACC/hacc_website/knowledge_graph/texts/b53a0523-fa60-4df6-bba3-6ae34a47cb02.txt"),
]
SUPPORTING_MISC_PATHS = [
    Path("/home/barberb/HACC/hacc_research/engine.py"),
    Path("/home/barberb/HACC/hacc_website/knowledge_graph/summary.json"),
]
WORKSPACE_GENERATED_PATHS = [
    Path("/home/barberb/HACC/workspace/temporary-cli-session-migration/workspace-generated/exhibit_index.md"),
    Path("/home/barberb/HACC/workspace/temporary-cli-session-migration/workspace-generated/email_evidence_memo.md"),
    Path("/home/barberb/HACC/workspace/temporary-cli-session-migration/workspace-generated/reasonable_accommodation_ocr_memo.md"),
    Path("/home/barberb/HACC/workspace/temporary-cli-session-migration/workspace-generated/chronology_evidence_matrix.json"),
]
FORMER_EMPLOYEE_REVIEW_SCREENSHOT_PATH = Path("/home/barberb/HACC/evidence/paper documents/image (2).png")


@dataclass
class CaseFacts:
    caption_plaintiffs: str
    signature_plaintiff: str
    mailing_address: str
    defendants_caption: str
    defendants_short: str
    protected_activity: str
    adverse_action: str
    harm: str
    chronology_paragraphs: List[str]
    requested_relief: List[str]
    unresolved_gaps: List[str]
    intake_answers: Dict[str, str]
    filing_metadata: Dict[str, str]


def _caption_name_list(caption: str) -> List[str]:
    text = _normalize_text(caption)
    if not text:
        return []
    parts = [item.strip(" ,") for item in re.split(r",|\sand\s", text) if item.strip(" ,")]
    return parts


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\u2014", "-").split())


def _normalize_lower(value: Any) -> str:
    return _normalize_text(value).lower()


def _sanitize_phrase(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    replacements = {
        " via Email": " via email",
        "2br": "2BR",
        "$50000": "$50,000",
        "accomodation": "accommodation",
        "accomodations": "accommodations",
        "effected": "affected",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"^yes,?\s*i do,?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ,;.")
    return text


def _join_phrases(parts: Iterable[str]) -> str:
    cleaned = [_sanitize_phrase(part) for part in parts]
    return "; ".join([part for part in cleaned if part])


def _question_matches(question: str, contains_any: Iterable[str]) -> bool:
    lowered = _normalize_lower(question)
    return any(token.lower() in lowered for token in contains_any)


def _answered_inquiries(state: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for inquiry in list(state.get("inquiries") or []):
        answer = _normalize_text(inquiry.get("answer"))
        if not answer or answer.lower() == "none":
            continue
        rows.append(
            {
                "question": _normalize_text(inquiry.get("question")),
                "answer": answer,
            }
        )
    return rows


def _first_answer(inquiries: Iterable[Dict[str, str]], contains_any: Iterable[str], default: str = "") -> str:
    for inquiry in inquiries:
        if _question_matches(inquiry.get("question", ""), contains_any):
            answer = _normalize_text(inquiry.get("answer"))
            if answer:
                return answer
    return default


def _extract_primary_name(raw_identity: str) -> tuple[str, str]:
    cleaned = _normalize_text(raw_identity)
    address = ""
    lowered = cleaned.lower()
    for splitter in (", my address is ", " my address is "):
        if splitter in lowered:
            idx = lowered.index(splitter)
            address = cleaned[idx + len(splitter):].strip(" ,")
            cleaned = cleaned[:idx].strip(" ,")
            break
    cleaned = re.sub(r"^(i am|i'm)\s+", "", cleaned, flags=re.IGNORECASE).strip(" ,")
    return cleaned or "Benjamin Barber", address


def _extract_plaintiff_caption(inquiries: List[Dict[str, str]], fallback_name: str) -> tuple[str, str]:
    exact_names = _first_answer(
        inquiries,
        ["exact legal name you want on the complaint", "legal name you want on the complaint"],
    )
    if exact_names:
        parts = [item.strip() for item in exact_names.split(",") if item.strip()]
        if parts:
            if len(parts) == 1:
                return parts[0], parts[0]
            return ", ".join(parts[:-1]) + f", and {parts[-1]}", parts[0]
    raw = _first_answer(
        inquiries,
        ["who is named as the plaintiff, and who are the defendants"],
        fallback_name,
    )
    if " vs " in raw.lower():
        raw = raw[: raw.lower().index(" vs ")].strip()
    parts = [item.strip() for item in re.split(r",|\sand\s", raw) if item.strip()]
    if len(parts) >= 2:
        if len(parts) == 2:
            return f"{parts[0]} and {parts[1]}", parts[0]
        return ", ".join(parts[:-1]) + f", and {parts[-1]}", parts[0]
    return fallback_name, fallback_name


def _extract_defendants(inquiries: List[Dict[str, str]]) -> tuple[str, str]:
    raw = _first_answer(
        inquiries,
        ["who is named as the plaintiff, and who are the defendants"],
        "Housing Authority of Clackamas County and Quantum Residential",
    )
    lowered = raw.lower()
    if " vs " in lowered:
        raw = raw[lowered.index(" vs ") + 4 :].strip()
    raw = raw.strip(" ,") or "Housing Authority of Clackamas County and Quantum Residential"
    return raw, raw


def _extract_timeline_paragraphs(inquiries: List[Dict[str, str]]) -> List[str]:
    narrative = _first_answer(inquiries, ["chronological order", "timeline of events", "event or events started"])
    if not narrative:
        return []
    priority_fragments = [
        "In October 2025, plaintiff raised concerns about stepfather abuse and requested lease bifurcation, and HACC said a restraining order was required.",
        "In November 2025, plaintiff obtained a restraining order, and the order was later continued after a December 9, 2025 hearing.",
        "In December 2025, plaintiff applied to Blossom Apartments, which was described as prioritized for displaced public-housing tenants, but the application was allegedly never processed.",
        "In January 2026, HACC removed Benjamin Barber from the lease and restored the restrained party to the lease.",
        "In February 2026, plaintiff was placed back on the lease, requested a two-bedroom accommodation after being told he would receive only a one-bedroom voucher, and then received a February 4, 2026 eviction notice.",
        "Plaintiff alleges the tenant protection voucher was requested as early as November 2025 but was not issued until March 20, 2026.",
        "Plaintiff alleges the requested two-bedroom accommodation was denied in writing and that he was told he could sleep in the living room instead.",
    ]
    selected: List[str] = []
    lowered_narrative = narrative.lower()
    for fragment in priority_fragments:
        if any(token in lowered_narrative for token in fragment.lower().split()[:3]):
            selected.append(fragment)
    supplemental = _first_answer(inquiries, ["supplemental update regarding julio"])
    if supplemental:
        selected.append(
            "Plaintiffs also allege Julio Regal Florez-Cortez was evicted instead of being bifurcated from the lease and was denied a hearing after an oral request because defendants insisted on a written request he could not make."
        )
    if not selected:
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", narrative) if item.strip()]
        selected = sentences[:8]
    return selected[:8]


def _extract_requested_relief() -> List[str]:
    return [
        "Temporary and preliminary injunctive relief preventing eviction, lockout, or loss of housing assistance while these claims are resolved.",
        "Declaratory relief that defendants' handling of the voucher, accommodation, grievance, hearing, and lease issues was unlawful.",
        "Injunctive relief requiring prompt processing of a two-bedroom accommodation and non-discriminatory voucher administration.",
        "Injunctive relief requiring meaningful hearing access and reasonable accommodation in any grievance or appeal process.",
        "Compensatory damages for housing instability, lost work time, emotional distress, and relocation-related losses.",
        "Costs, fees, and any further relief authorized by law.",
    ]


def _build_unresolved_gaps() -> List[str]:
    return [
        "Some exact dates for accommodation emails, staff-specific responses, and each notice still need exhibit-level support.",
        "The statefile names several staff members but does not map each challenged act to one individual with exact dates.",
        "The precise amount of wage loss and relocation damages still needs documentary support.",
        "The tenant-protection-voucher request date should be reconciled against the email record before filing.",
    ]


def extract_case_facts(state: Dict[str, Any]) -> CaseFacts:
    inquiries = _answered_inquiries(state)
    raw_identity = _first_answer(inquiries, ["full legal name"], "Benjamin Barber")
    fallback_name, address = _extract_primary_name(raw_identity)
    caption_plaintiffs, signature_plaintiff = _extract_plaintiff_caption(inquiries, fallback_name)
    defendants_caption, defendants_short = _extract_defendants(inquiries)
    chronology = _extract_timeline_paragraphs(inquiries)
    communication = _first_answer(inquiries, ["if yes, when and how"], "on multiple occasions via email")
    protected_activity = _sanitize_phrase(
        "complaining about race discrimination and housing steering, requesting reasonable accommodation "
        "for a two-bedroom voucher and caregiving needs, seeking domestic-violence-related safety and lease protections, "
        f"and communicating those complaints {communication}"
    )
    adverse_action = _sanitize_phrase(
        "removing Benjamin Barber from the lease while the restrained party was restored, failing to timely process the "
        "Blossom application and tenant protection voucher request, denying the requested two-bedroom accommodation, "
        "serving a February 4, 2026 eviction notice after protected complaints, and failing to provide Julio Regal Florez-Cortez "
        "a hearing after an oral request"
    )
    harm = _join_phrases(
        [
            _first_answer(inquiries, ["what damages or harm have you suffered"], "financial losses and lost opportunities"),
            _first_answer(inquiries, ["health, financial, or employment impacts"], ""),
            "foreseeable future housing and relocation losses of "
            + _first_answer(inquiries, ["what future damages are reasonably foreseeable"], "")
            if _first_answer(inquiries, ["what future damages are reasonably foreseeable"], "")
            else "",
        ]
    )
    intake_answers = {
        "party_name": signature_plaintiff,
        "opposing_party": defendants_short,
        "protected_activity": protected_activity[:1].upper() + protected_activity[1:] if protected_activity else "",
        "adverse_action": adverse_action[:1].upper() + adverse_action[1:] if adverse_action else "",
        "timeline": " ".join(chronology),
        "harm": harm[:1].upper() + harm[1:] if harm else "",
        "court_header": "FOR THE DISTRICT OF OREGON",
    }
    filing_metadata = {
        "caption_plaintiffs": caption_plaintiffs,
        "caption_defendants": defendants_caption,
        "signature_plaintiff": signature_plaintiff,
        "signature_role": "Primary Filer / Proposed Plaintiff",
        "mailing_address": address,
    }
    return CaseFacts(
        caption_plaintiffs=caption_plaintiffs,
        signature_plaintiff=signature_plaintiff,
        mailing_address=address,
        defendants_caption=defendants_caption,
        defendants_short=defendants_short,
        protected_activity=protected_activity,
        adverse_action=adverse_action,
        harm=harm,
        chronology_paragraphs=chronology,
        requested_relief=_extract_requested_relief(),
        unresolved_gaps=_build_unresolved_gaps(),
        intake_answers=intake_answers,
        filing_metadata=filing_metadata,
    )


def _hardlink_or_copy_tree(source: Path, target: Path) -> str:
    if not source.exists():
        return "missing"
    if target.exists():
        return "existing"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(source, target, copy_function=os.link)
        return "hardlinked"
    except Exception:
        shutil.copytree(source, target, copy_function=shutil.copy2)
        return "copied"


def ensure_workspace_source_snapshot(workspace_root: Path) -> Dict[str, Any]:
    migrated_root = workspace_root / MIGRATED_SOURCES_ROOTNAME
    migrated_root.mkdir(parents=True, exist_ok=True)
    manifest_sources = []
    for name, source in SOURCE_ROOTS.items():
        target = migrated_root / name
        mode = _hardlink_or_copy_tree(source, target)
        manifest_sources.append(
            {
                "name": name,
                "source": str(source),
                "path": str(target),
                "exists": target.exists(),
                "migration_mode": mode,
            }
        )
    manifest = {
        "created_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workspace": str(workspace_root),
        "migration_mode": "per-tree",
        "sources": manifest_sources,
    }
    (workspace_root / "migration_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _resolve_source_roots(workspace_root: Path) -> Dict[str, Path]:
    migrated_root = workspace_root / MIGRATED_SOURCES_ROOTNAME
    return {
        name: (migrated_root / name if (migrated_root / name).exists() else path)
        for name, path in SOURCE_ROOTS.items()
    }


def _resolve_candidate(path: Path, roots: Dict[str, Path]) -> Path:
    raw = str(path)
    for name, source_root in SOURCE_ROOTS.items():
        prefix = str(source_root)
        if raw.startswith(prefix):
            return roots[name] / raw[len(prefix) :].lstrip("/")
    return path


def _collect_research_results_paths(research_results_root: Path) -> List[Path]:
    ordered: List[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        lookup = str(path)
        if path.exists() and lookup not in seen:
            seen.add(lookup)
            ordered.append(path)

    for review_dir in sorted(research_results_root.glob("evidence_review_*"), reverse=True)[:5]:
        _add(review_dir / "evidence_review.md")
        _add(review_dir / "evidence_review.json")

    _add(research_results_root / "search_indexes" / "hacc_corpus.summary.json")
    _add(research_results_root / "search_indexes" / "hacc_enhanced_index_20260314_055513.summary.json")

    oregon_docs = research_results_root / "oregon_documents"
    if oregon_docs.exists():
        keywords = ("fair", "housing", "voucher", "accommodation", "discrimination", "659", "hacc", "quantum")
        for candidate in sorted(oregon_docs.glob("*")):
            if candidate.is_file() and any(token in candidate.name.lower() for token in keywords):
                _add(candidate)
            if len(ordered) >= 18:
                break
    return ordered


def evidence_import_paths(workspace_root: Path) -> List[Path]:
    roots = _resolve_source_roots(workspace_root)
    ordered: List[Path] = []
    for path in PRIMARY_POLICY_PATHS + PRIMARY_LEGAL_PATHS + SUPPORTING_PROGRAM_PATHS + SUPPORTING_MISC_PATHS:
        candidate = _resolve_candidate(path, roots)
        if candidate.exists() and candidate not in ordered:
            ordered.append(candidate)
    for path in WORKSPACE_GENERATED_PATHS:
        candidate = path
        if candidate.exists() and candidate not in ordered:
            ordered.append(candidate)
    for extra in _collect_research_results_paths(roots["research_results"]):
        if extra not in ordered:
            ordered.append(extra)
    if FORMER_EMPLOYEE_REVIEW_SCREENSHOT_PATH.exists() and FORMER_EMPLOYEE_REVIEW_SCREENSHOT_PATH not in ordered:
        ordered.append(FORMER_EMPLOYEE_REVIEW_SCREENSHOT_PATH)
    return ordered


def _save_structured_evidence(
    service: ComplaintWorkspaceService,
    user_id: str,
    facts: CaseFacts,
    statefile: Path,
) -> None:
    testimony_entries = [
        {
            "title": "Legacy chronology from temporary CLI session",
            "claim_element_id": "adverse_action",
            "content": " ".join(facts.chronology_paragraphs),
        },
        {
            "title": "Protected complaints and accommodation requests",
            "claim_element_id": "protected_activity",
            "content": facts.protected_activity,
        },
        {
            "title": "Housing harms and threatened eviction",
            "claim_element_id": "harm",
            "content": facts.harm,
        },
    ]
    for entry in testimony_entries:
        service.save_evidence(
            user_id,
            kind="testimony",
            claim_element_id=entry["claim_element_id"],
            title=entry["title"],
            content=_normalize_text(entry["content"])[:7000],
            source=f"legacy_statefile:{statefile}",
        )


def _recommended_exhibits(workspace_root: Path) -> List[Dict[str, str]]:
    base = workspace_root / "temporary-cli-session-migration" / "prior-research-results" / "full-evidence-review-run" / "chronology"
    packet = base / "formal_complaint_recommended_filing_packet"
    emergency = base / "emergency_motion_packet" / "exhibits"
    accommodation_packet = workspace_root / "temporary-cli-session-migration" / "paper-exhibits" / "Reasonable accomidation.pdf"
    former_employee_review = workspace_root / "improved-complaint-from-temporary-session.former-employee-review.png"
    return [
        {"label": "Exhibit A", "title": "HACC add to lease", "path": str(packet / "included" / "01_Exhibit_A_HACC_add_to_lease.pdf"), "use": "Lease amendment or add/remove-tenant record for the household."},
        {"label": "Exhibit B", "title": "HACC phase2 2024 notice", "path": str(packet / "included" / "02_Exhibit_B_HACC_phase2_2024.pdf"), "use": "General displacement and project notice."},
        {"label": "Exhibit C", "title": "HACC 30-day notice without cause", "path": str(packet / "included" / "03_Exhibit_C_HACC_90_day_notice_2.pdf"), "use": "December 23, 2025 30-day lease termination notice without cause."},
        {"label": "Exhibit D", "title": "HACC 90-day notice without cause", "path": str(packet / "included" / "04_Exhibit_D_HACC_90_day_notice.pdf"), "use": "December 23, 2025 90-day lease termination notice without cause."},
        {"label": "Exhibit E", "title": "HACC notice of eligibility and 90-day displacement notice", "path": str(packet / "included" / "05_Exhibit_E_HACC_90_day_notice_3.pdf"), "use": "December 31, 2025 displacement notice."},
        {"label": "Exhibit F", "title": "HACC VAWA-related lease amendment", "path": str(packet / "included" / "06_Exhibit_F_HACC_vawa_violation.pdf"), "use": "January 1, 2026 lease amendment tied to household composition."},
        {"label": "Exhibit G", "title": "HACC January 2026 Blossom notice", "path": str(packet / "included" / "07_Exhibit_G_HACC_Jan_2026_blossom.pdf"), "use": "January 8, 2026 Blossom and TPV communication."},
        {"label": "Exhibit H", "title": "HACC February 4, 2026 for-cause notice", "path": str(packet / "included" / "08_Exhibit_H_HACC_first_amendment.pdf"), "use": "February 4, 2026 30-day for-cause notice."},
        {"label": "Exhibit I", "title": "HACC financial requests", "path": str(packet / "included" / "09_Exhibit_I_HACC_financial_requests.pdf"), "use": "February 9, 2026 additional-information demand."},
        {"label": "Exhibit J", "title": "Additional information email thread export", "path": str(packet / "candidate_email_exhibits" / "10_Exhibit_J_Email_Thread_Export_starworks5_additional_info_import"), "use": "Escalating email documentation demands and complaints about Blossom processing, service-animal issues, and discrimination."},
        {"label": "Exhibit K", "title": "HACC steering-related notice", "path": str(packet / "included" / "11_Exhibit_K_HACC_steering.pdf"), "use": "February 26, 2026 notice tied to ongoing occupancy and relocation handling."},
        {"label": "Exhibit L", "title": "HACC inspection notice", "path": str(packet / "included" / "12_Exhibit_L_HACC_inspection.pdf"), "use": "March 17, 2026 NSPIRE inspection notice."},
        {"label": "Exhibit M", "title": "HCV orientation email thread export", "path": str(packet / "candidate_email_exhibits" / "13_Exhibit_M_Email_Thread_Export_starworks5_ktilton_orientation_import"), "use": "Orientation, voucher issuance, bedroom-size reversal, and reasonable-accommodation emails."},
        {"label": "Exhibit N", "title": "Julio eviction notice", "path": str(emergency / "Exhibit N - Julio Eviction notice.jpeg"), "use": "February 13, 2026 termination notice addressed directly to Julio Cortez."},
        {"label": "Exhibit O", "title": "Reasonable accommodation packet", "path": str(accommodation_packet), "use": "March 24, 2026 provider letter and HACC verification form supporting disability status, service-animal need, and a two-bedroom first-floor accommodation request."},
        {"label": "Exhibit Q", "title": "Former-employee review screenshot", "path": str(former_employee_review), "use": "Third-party former-employee review material circulated by plaintiffs as context for race-discrimination and retaliation complaints; not a direct company admission."},
    ]


def _render_exhibit_map(workspace_root: Path) -> str:
    exhibits = _recommended_exhibits(workspace_root)
    lines = [
        "# Workspace Exhibit Map",
        "",
        "This map identifies the exhibit set currently supporting the cited complaint generated from the temporary CLI session.",
        "",
    ]
    for exhibit in exhibits:
        lines.extend(
            [
                f"## {exhibit['label']}",
                "",
                f"- Title: {exhibit['title']}",
                f"- Path: {exhibit['path']}",
                f"- Use: {exhibit['use']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Core Citation Themes",
            "",
            "- Notice and displacement sequence: Exhibits B, C, D, E, H, K, and N.",
            "- Lease and household-composition handling: Exhibits A and F.",
            "- Blossom processing and transfer opportunity: Exhibit G and Exhibit J.",
            "- Documentation demands and retaliation sequence: Exhibits I and J.",
            "- Voucher issuance, bedroom size, and accommodation communications: Exhibit M.",
            "- Disability verification and requested two-bedroom first-floor accommodation: Exhibit O.",
            "- Former-employee review material cited as notice and context for race-discrimination complaints: Exhibit Q.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_julio_hearing_declaration_template(facts: CaseFacts) -> str:
    address_block = facts.mailing_address or "Address on file in workspace"
    return "\n".join(
        [
            "# Declaration Regarding Julio Hearing Access",
            "",
            "Use this only if the declarant has firsthand knowledge of Julio Regal Florez-Cortez's inability to write, the oral hearing request, or HACC's response.",
            "",
            "IN THE UNITED STATES DISTRICT COURT",
            "FOR THE DISTRICT OF OREGON",
            "",
            f"{facts.caption_plaintiffs}, Plaintiffs,",
            "",
            "v.",
            "",
            f"{facts.defendants_caption}, Defendants.",
            "",
            "Civil Action No. ________________",
            "",
            "I, ____________________, declare as follows:",
            "",
            "1. I have personal knowledge of the matters stated here.",
            "2. I know Julio Regal Florez-Cortez and have personally observed that he cannot write in any language, or cannot reliably complete a written hearing request without assistance.",
            "3. I personally observed Julio Regal Florez-Cortez request a hearing orally on or about ____________________.",
            "4. I personally observed, or was told directly by HACC staff, that HACC required a written hearing request.",
            "5. To my knowledge, HACC did not provide Julio Regal Florez-Cortez an oral, assisted, interpreter-supported, or otherwise accessible way to invoke a hearing.",
            "6. To my knowledge, no hearing was provided after the oral request.",
            "7. I have seen the February 13, 2026 termination notice addressed to Julio Regal Florez-Cortez.",
            "8. Based on what I observed, requiring a written request made the hearing process inaccessible to him.",
            "",
            "I declare under penalty of perjury under the laws of the United States that the foregoing is true and correct.",
            "",
            "Executed on ____________________, 2026, at ____________________.",
            "",
            "__________________________________",
            "Signature",
            "__________________________________",
            "Printed name",
            address_block,
            "",
        ]
    )


def _render_benjamin_julio_hearing_declaration(facts: CaseFacts) -> str:
    address_block = facts.mailing_address or "Address on file in workspace"
    return "\n".join(
        [
            "# Declaration Of Benjamin Jay Barber Regarding Julio Hearing Access",
            "",
            "IN THE UNITED STATES DISTRICT COURT",
            "FOR THE DISTRICT OF OREGON",
            "",
            f"{facts.caption_plaintiffs}, Plaintiffs,",
            "",
            "v.",
            "",
            f"{facts.defendants_caption}, Defendants.",
            "",
            "Civil Action No. ________________",
            "",
            "I, Benjamin Jay Barber, declare as follows:",
            "",
            "1. I am a plaintiff in this action and make this declaration from personal knowledge.",
            "2. I live with members of my household affected by the events described in the complaint, including Jane Kay Cortez and Julio Regal Florez-Cortez.",
            "3. I have personally observed that Julio Regal Florez-Cortez cannot write in any language.",
            "4. During the February 2026 termination sequence, I personally observed that Julio Regal Florez-Cortez requested a hearing orally.",
            "5. I also personally observed, or was told directly in connection with that request, that HACC required a written hearing request.",
            "6. To my knowledge, HACC did not provide Julio Regal Florez-Cortez an oral, assisted, interpreter-supported, or otherwise accessible means to invoke a hearing.",
            "7. To my knowledge, no hearing was provided after the oral request.",
            "8. I have seen the February 13, 2026 30-Day Notice of Termination addressed directly to Julio Regal Florez-Cortez and stating an effective date of March 19, 2026. Exhibit N.",
            "9. Based on what I observed, requiring a written request made the hearing process inaccessible to Julio Regal Florez-Cortez.",
            "10. HACC's ACOP materials state that termination notices must inform the family of hearing rights and that HACC must provide reasonable accommodation for persons with disabilities to participate in the hearing process.",
            "11. Based on what I observed, the threatened loss of housing and absence of an accessible hearing process created immediate hardship for Julio Regal Florez-Cortez and the household.",
            "",
            "I declare under penalty of perjury under the laws of the United States that the foregoing is true and correct.",
            "",
            "Executed on ____________________, 2026, at ____________________.",
            "",
            "__________________________________",
            "Benjamin Jay Barber",
            address_block,
            "",
        ]
    )


def _render_jane_julio_hearing_declaration(facts: CaseFacts) -> str:
    address_block = facts.mailing_address or "Address on file in workspace"
    return "\n".join(
        [
            "# Declaration Of Jane Kay Cortez Regarding Julio Hearing Access",
            "",
            "Use this draft only if Jane Kay Cortez has firsthand knowledge of the matters stated below and can truthfully adopt them.",
            "",
            "IN THE UNITED STATES DISTRICT COURT",
            "FOR THE DISTRICT OF OREGON",
            "",
            f"{facts.caption_plaintiffs}, Plaintiffs,",
            "",
            "v.",
            "",
            f"{facts.defendants_caption}, Defendants.",
            "",
            "Civil Action No. ________________",
            "",
            "I, Jane Kay Cortez, declare as follows:",
            "",
            "1. I am a plaintiff in this action and make this declaration from personal knowledge.",
            "2. I am part of the household with Benjamin Jay Barber and Julio Regal Florez-Cortez that was affected by the HACC notices, relocation problems, voucher issues, and hearing-access problems described in the complaint.",
            "3. I have personally observed that Julio Regal Florez-Cortez cannot write in any language, or cannot reliably complete a written hearing request without assistance.",
            "4. I personally observed, or was present when, Julio Regal Florez-Cortez requested a hearing orally during the February 2026 termination sequence.",
            "5. I personally observed, or was told directly in connection with that request, that HACC required a written hearing request.",
            "6. To my knowledge, HACC did not provide Julio Regal Florez-Cortez an oral, assisted, interpreter-supported, or otherwise accessible means to invoke a hearing.",
            "7. To my knowledge, no hearing was provided after the oral request.",
            "8. I am aware of the February 13, 2026 30-Day Notice of Termination addressed directly to Julio Regal Florez-Cortez and stating an effective date of March 19, 2026. Exhibit N.",
            "9. Based on what I observed, requiring a written request made the hearing process inaccessible to Julio Regal Florez-Cortez.",
            "10. Based on what I observed, the threatened loss of housing and absence of an accessible hearing process created immediate hardship for Julio Regal Florez-Cortez and the household.",
            "",
            "I declare under penalty of perjury under the laws of the United States that the foregoing is true and correct.",
            "",
            "Executed on ____________________, 2026, at ____________________.",
            "",
            "__________________________________",
            "Jane Kay Cortez",
            address_block,
            "",
        ]
    )


def _render_julio_hearing_witness_prep_memo() -> str:
    return "\n".join(
        [
            "# Julio Hearing Witness Prep Memo",
            "",
            "## Current Best Date Window",
            "",
            "- The February 13, 2026 termination notice to Julio Regal Florez-Cortez set an effective date of March 19, 2026.",
            "- The strongest current inference is that the oral hearing request and the written-request response happened during that February 13 to March 19, 2026 termination window.",
            "- If the witness remembers a narrower point, the best immediate anchor would be: after receipt of the February 13, 2026 notice and before March 19, 2026.",
            "",
            "## Best Current Support",
            "",
            "- Exhibit N: February 13, 2026 termination notice addressed to Julio Regal Florez-Cortez.",
            "- HACC ACOP: termination notices must inform the family of hearing rights, and HACC must provide reasonable accommodation for persons with disabilities to participate in the hearing process.",
            "- Existing Benjamin declaration draft: states that Julio could not write, requested a hearing orally, was told to request it in writing, and received no hearing.",
            "- Existing emergency-motion exhibit index and manifest: both identify the inaccessible hearing process as a core fact theme, but treat it as declaration-supported rather than independently documented.",
            "",
            "## Missing Facts To Fill Before Signing",
            "",
            "1. Who exactly heard Julio make the oral request?",
            "2. Approximately where did it happen?",
            "3. Was the request made in person, by phone, or both?",
            "4. Who from HACC said a written request was required, if the witness knows the name?",
            "5. What is the narrowest truthful date anchor the witness can give?",
            "6. Did anyone send a follow-up email, text, or letter afterward mentioning the hearing request?",
            "",
            "## Recommended Declaration Wording For Date Anchor",
            "",
            "- If exact date is unknown: `during the period after the February 13, 2026 termination notice and before the March 19, 2026 effective date`.",
            "- If month only is known: `in February 2026, after Julio received the February 13, 2026 notice`.",
            "- If a specific day can be recalled, use that exact date instead.",
            "",
            "## Filing Note",
            "",
            "- A signed declaration from Benjamin Jay Barber is presently the strongest available next step.",
            "- A signed declaration from Jane Kay Cortez should be used only if she personally observed the oral request or HACC's response.",
            "- If another household member or advocate witnessed the request more directly, a third declaration from that person could be stronger than Jane's.",
            "",
        ]
    )


def _render_julio_hearing_finalize_checklist() -> str:
    return "\n".join(
        [
            "# Julio Hearing Finalize And Sign Checklist",
            "",
            "## Best Current Path",
            "",
            "1. Use the Benjamin Jay Barber declaration as the primary hearing-access declaration.",
            "2. Use the Jane Kay Cortez declaration only if she personally observed the oral request or HACC's response.",
            "3. Attach Exhibit N to whichever declaration is signed.",
            "4. If available, attach the relevant ACOP excerpt on hearing rights and reasonable accommodation in the hearing process.",
            "",
            "## Fill Before Signing",
            "",
            "1. Replace the broad time reference with the narrowest truthful date anchor.",
            "2. Add where the oral request happened: office, phone call, lobby, meeting, or other location.",
            "3. Add the HACC staff name if known.",
            "4. If the witness remembers exact words, add a short quoted or near-quoted description.",
            "5. Confirm whether any follow-up email, text, or letter mentioned the request.",
            "",
            "## Safe Date Anchors",
            "",
            "- Best fallback: `during the period after the February 13, 2026 termination notice and before the March 19, 2026 effective date`.",
            "- If only month is known: `in February 2026, after receipt of the February 13, 2026 notice`.",
            "- If a specific day is remembered, use the exact date instead.",
            "",
            "## Attachments",
            "",
            "- Exhibit N: February 13, 2026 termination notice to Julio Regal Florez-Cortez.",
            "- ACOP excerpt: hearing-rights notice and reasonable accommodation in hearing participation.",
            "- Complaint draft: improved-complaint-from-temporary-session.md.",
            "",
            "## Filing Caution",
            "",
            "- Do not state that HACC's refusal was documented in writing unless such a record is found.",
            "- Keep the oral-request point framed as firsthand witness testimony unless a contemporaneous memorialization is located.",
            "",
        ]
    )


def _render_julio_hearing_acop_excerpt() -> str:
    return "\n".join(
        [
            "# HACC ACOP Hearing-Access Excerpt For Julio Hearing Issue",
            "",
            "Source: HACC ACOP 11/1/2024, extracted from the migrated HACC policy text in the workspace.",
            "",
            "## Accommodation Appeal Language",
            "",
            "- If HACC denies a requested accommodation for lack of nexus, the notice must inform the family of the right to appeal through an informal hearing if applicable or through the grievance process.",
            "- If HACC denies a requested accommodation as unreasonable, the notice must inform the family of the right to appeal through an informal hearing if applicable or through the grievance process.",
            "- If HACC identifies an alternative accommodation instead of the requested accommodation, the notice must still inform the family of the right to appeal through an informal hearing if applicable or through the grievance process.",
            "",
            "## Program Accessibility Language",
            "",
            "- HACC must take reasonable steps to ensure that persons with disabilities related to hearing and vision have reasonable access to HACC programs and services.",
            "- At the initial point of contact, HACC must inform applicants of alternative forms of communication other than plain language paperwork.",
            "- HACC's listed examples of alternative communication include having material explained orally by staff or using a third-party representative to receive, interpret, and explain housing materials and be present at meetings.",
            "",
            "## Denial Or Termination Language",
            "",
            "- When a family's lease is terminated, the notice of termination must inform the family of the right to request a hearing in accordance with HACC's grievance process.",
            "- HACC must consider reasonable accommodation when deciding whether to deny or terminate assistance for a family that includes a person with disabilities.",
            "- HACC must provide reasonable accommodation for persons with disabilities to participate in the hearing process.",
            "",
            "## Best Use",
            "",
            "- Attach this excerpt with the Benjamin or Jane declaration to show the policy basis for the hearing-rights and accessibility allegations.",
            "- Pair this excerpt with Exhibit N, the February 13, 2026 termination notice to Julio Regal Florez-Cortez.",
            "",
        ]
    )


def _render_julio_hearing_packet_index() -> str:
    return "\n".join(
        [
            "# Julio Hearing Packet Index",
            "",
            "This index collects the current workspace artifacts that best support the Julio Regal Florez-Cortez hearing-access issue in Count III.",
            "",
            "## Recommended Core Packet",
            "",
            "1. Complaint draft: improved-complaint-from-temporary-session.md",
            "2. Benjamin declaration: improved-complaint-from-temporary-session.benjamin-julio-hearing-declaration.md",
            "3. Exhibit N: February 13, 2026 termination notice to Julio Regal Florez-Cortez",
            "4. ACOP excerpt: improved-complaint-from-temporary-session.julio-hearing-acop-excerpt.md",
            "",
            "## Optional Supporting Materials",
            "",
            "1. Jane declaration draft: improved-complaint-from-temporary-session.jane-julio-hearing-declaration.md",
            "2. Witness prep memo: improved-complaint-from-temporary-session.julio-hearing-witness-prep.md",
            "3. Finalize checklist: improved-complaint-from-temporary-session.julio-hearing-finalize-checklist.md",
            "4. Exhibit map: improved-complaint-from-temporary-session.exhibit-map.md",
            "",
            "## Best Current Theory",
            "",
            "- Julio Regal Florez-Cortez received a February 13, 2026 termination notice effective March 19, 2026.",
            "- During that termination period, he allegedly requested a hearing orally.",
            "- HACC allegedly required a written hearing request even though he could not write in any language.",
            "- No meaningful accessible hearing was provided.",
            "- HACC's ACOP requires hearing-rights notice in termination situations and reasonable accommodation in hearing participation.",
            "",
            "## Remaining Gap",
            "",
            "- The strongest remaining factual improvement would be a signed declaration with the narrowest truthful date, location, and staff-name detail for the oral request and response.",
            "",
        ]
    )


def _render_julio_hearing_filing_cover_note() -> str:
    return "\n".join(
        [
            "# Julio Hearing Filing Cover Note",
            "",
            "This note is intended to accompany the Count III hearing-access support packet.",
            "",
            "## Suggested Attachment Order",
            "",
            "1. Complaint: improved-complaint-from-temporary-session.md",
            "2. Declaration Of Benjamin Jay Barber Regarding Julio Hearing Access",
            "3. Exhibit N: February 13, 2026 termination notice to Julio Regal Florez-Cortez",
            "4. HACC ACOP Hearing-Access Excerpt For Julio Hearing Issue",
            "",
            "## Purpose Of This Packet",
            "",
            "- To support the allegation that Julio Regal Florez-Cortez was denied a meaningful and accessible hearing process during the February to March 2026 termination period.",
            "- To show that the hearing-access allegation is supported by both firsthand household testimony and HACC's own policy requirements.",
            "",
            "## Core Factual Theory",
            "",
            "- Julio Regal Florez-Cortez received a February 13, 2026 termination notice with a March 19, 2026 effective date.",
            "- During that termination period, he allegedly requested a hearing orally.",
            "- HACC allegedly required a written request even though he could not write in any language.",
            "- No accessible alternative or meaningful hearing was provided.",
            "",
            "## Policy Theory",
            "",
            "- HACC policy requires termination notices to inform the family of hearing rights.",
            "- HACC policy also requires reasonable accommodation for persons with disabilities to participate in the hearing process.",
            "- HACC policy identifies oral explanation and third-party assistance as examples of alternative communication methods.",
            "",
            "## Caution",
            "",
            "- Keep the oral-request allegation framed as witness testimony unless a contemporaneous memorialization is found.",
            "- Do not state that HACC refused the request in writing unless such a record is attached.",
            "",
        ]
    )


def _render_benjamin_julio_signing_worksheet() -> str:
    return "\n".join(
        [
            "# Benjamin Julio Declaration Signing Worksheet",
            "",
            "Use this worksheet before signing `improved-complaint-from-temporary-session.benjamin-julio-hearing-declaration.md`.",
            "",
            "## Fill These Facts First",
            "",
            "1. Narrowest truthful date or date range for the oral hearing request:",
            "   ________________________________",
            "",
            "2. Where the request happened:",
            "   ________________________________",
            "",
            "3. How the request was made:",
            "   in person / phone / both / other: ________________________________",
            "",
            "4. Name of HACC staff member involved, if known:",
            "   ________________________________",
            "",
            "5. What HACC said about a written request, as closely remembered:",
            "   ________________________________",
            "",
            "6. Whether any follow-up email, text, or letter mentioned the request:",
            "   yes / no",
            "   If yes, describe or locate it: ________________________________",
            "",
            "## Safe Fallback Wording",
            "",
            "- Date anchor: `during the period after the February 13, 2026 termination notice and before the March 19, 2026 effective date`.",
            "- If staff name is unknown, say `a HACC staff member` rather than guessing.",
            "- If exact words are uncertain, use `in substance` rather than quotation marks.",
            "",
            "## Attach With The Signed Declaration",
            "",
            "1. Exhibit N termination notice.",
            "2. ACOP hearing-access excerpt.",
            "3. Complaint draft or the relevant Count III pages if needed.",
            "",
        ]
    )


def _render_benjamin_julio_fillable_declaration(facts: CaseFacts) -> str:
    address_block = facts.mailing_address or "Address on file in workspace"
    return "\n".join(
        [
            "# Declaration Of Benjamin Jay Barber Regarding Julio Hearing Access (Fillable)",
            "",
            "Replace each bracketed placeholder with the narrowest truthful detail available before signing.",
            "",
            "IN THE UNITED STATES DISTRICT COURT",
            "FOR THE DISTRICT OF OREGON",
            "",
            f"{facts.caption_plaintiffs}, Plaintiffs,",
            "",
            "v.",
            "",
            f"{facts.defendants_caption}, Defendants.",
            "",
            "Civil Action No. ________________",
            "",
            "I, Benjamin Jay Barber, declare as follows:",
            "",
            "1. I am a plaintiff in this action and make this declaration from personal knowledge.",
            "2. I live with members of my household affected by the events described in the complaint, including Jane Kay Cortez and Julio Regal Florez-Cortez.",
            "3. I have personally observed that Julio Regal Florez-Cortez cannot write in any language.",
            "4. During [DATE OR DATE RANGE], after receipt of the February 13, 2026 termination notice and before the March 19, 2026 effective date, I personally observed that Julio Regal Florez-Cortez requested a hearing orally [IN PERSON / BY PHONE / OTHER] at [LOCATION].",
            "5. In connection with that request, [HACC STAFF NAME OR 'a HACC staff member'] stated in substance that Julio Regal Florez-Cortez had to request a hearing in writing.",
            "6. To my knowledge, HACC did not provide Julio Regal Florez-Cortez an oral, assisted, interpreter-supported, or otherwise accessible means to invoke a hearing.",
            "7. To my knowledge, no hearing was provided after the oral request.",
            "8. I have seen the February 13, 2026 30-Day Notice of Termination addressed directly to Julio Regal Florez-Cortez and stating an effective date of March 19, 2026. Exhibit N.",
            "9. Based on what I observed, requiring a written request made the hearing process inaccessible to Julio Regal Florez-Cortez.",
            "10. HACC's ACOP materials state that termination notices must inform the family of hearing rights and that HACC must provide reasonable accommodation for persons with disabilities to participate in the hearing process.",
            "11. [OPTIONAL FOLLOW-UP DETAIL ABOUT ANY EMAIL, TEXT, LETTER, OR LATER CONVERSATION MENTIONING THE REQUEST.]",
            "12. Based on what I observed, the threatened loss of housing and absence of an accessible hearing process created immediate hardship for Julio Regal Florez-Cortez and the household.",
            "",
            "I declare under penalty of perjury under the laws of the United States that the foregoing is true and correct.",
            "",
            "Executed on ____________________, 2026, at ____________________.",
            "",
            "__________________________________",
            "Benjamin Jay Barber",
            address_block,
            "",
        ]
    )


def _render_exhibit_cited_complaint(facts: CaseFacts) -> str:
    plaintiff_names = _caption_name_list(facts.caption_plaintiffs)
    address_block = facts.mailing_address or "Address on file in workspace"
    lines = [
        "IN THE UNITED STATES DISTRICT COURT",
        "FOR THE DISTRICT OF OREGON",
        "",
        f"{facts.caption_plaintiffs}, Plaintiffs,",
        "",
        "v.",
        "",
        f"{facts.defendants_caption}, Defendants.",
        "",
        "Civil Action No. ________________",
        "",
        "COMPLAINT FOR VIOLATION OF THE FAIR HOUSING ACT, SECTION 504 OF THE REHABILITATION ACT,",
        "TITLE II OF THE AMERICANS WITH DISABILITIES ACT, 42 U.S.C. section 1983,",
        "AND RELATED OREGON HOUSING LAW",
        "",
        "JURY TRIAL DEMANDED",
        "",
        "Plaintiffs allege as follows:",
        "",
        "NATURE OF THE ACTION",
        "",
        "1. This civil action arises from housing-discrimination, relocation, voucher-administration, and hearing-access disputes involving a displaced public-housing household in Clackamas County, Oregon.",
        "2. Plaintiffs allege that defendants delayed or obstructed relocation, denied or delayed reasonable accommodation, interfered with fair-housing rights, imposed retaliatory barriers after protected complaints, and failed to provide a meaningful and accessible hearing process when housing rights were threatened.",
        "3. Plaintiffs seek declaratory, injunctive, and monetary relief sufficient to stop unlawful eviction and displacement, require lawful housing and voucher administration, and compensate the household for the resulting harms.",
        "",
        "JURISDICTION AND VENUE",
        "",
        "4. This Court has federal-question jurisdiction under 28 U.S.C. section 1331 because this action arises under the Fair Housing Act, Section 504 of the Rehabilitation Act, Title II of the Americans with Disabilities Act, 42 U.S.C. section 1983, 42 U.S.C. section 1437d(k), and 24 C.F.R. section 982.555.",
        "5. This Court also has jurisdiction under 28 U.S.C. section 1343 because plaintiffs seek relief for deprivations of federal civil-rights protections under color of state law.",
        "6. This Court has supplemental jurisdiction over related Oregon-law claims under 28 U.S.C. section 1367 because those claims arise from the same nucleus of operative facts.",
        "7. Venue is proper in the District of Oregon under 28 U.S.C. section 1391 because the notices, voucher administration, accommodation requests, application failures, threatened eviction, and resulting harms occurred in Clackamas County, Oregon.",
        "",
        "PARTIES",
        "",
        f"8. Plaintiffs are {facts.caption_plaintiffs}, members of the same displaced household whose housing stability, relocation, and continued occupancy were affected by the challenged conduct.",
        "9. Defendant Housing Authority of Clackamas County is a public housing authority that administered the relevant lease, displacement, voucher, accommodation, grievance, and hearing processes described in this complaint.",
        "10. Defendant Quantum Residential managed or controlled the Blossom Apartments application and placement process and is alleged to have participated in the denial, delay, or obstruction of housing access described below.",
        "",
        "GENERAL ALLEGATIONS",
        "",
        "11. Plaintiffs engaged in protected activity by complaining about race discrimination and housing steering, requesting reasonable accommodation for a two-bedroom voucher and caregiving needs, seeking domestic-violence-related safety and lease protections, and communicating those complaints on multiple occasions via email.",
        "12. Plaintiffs allege that defendants then took or maintained adverse actions by removing Benjamin Barber from the lease while the restrained party was restored, failing to timely process the Blossom application and tenant protection voucher request, denying the requested two-bedroom accommodation, serving a February 4, 2026 eviction notice after protected complaints, and failing to provide Julio Regal Florez-Cortez a hearing after an oral request.",
        "13. On August 5, 2024, HACC generated a lease amendment or add/remove-tenant document for the household. Exhibit A.",
        "14. On September 19, 2024, HACC issued a general information notice concerning Hillside Park Apartments Phase II and the coming displacement sequence. Exhibit B.",
        "15. On December 23, 2025, HACC issued both a 30-day lease termination notice without cause and a 90-day lease termination notice without cause addressed to Jane Kay Cortez at the subject residence. Exhibits C and D.",
        "16. On December 31, 2025, HACC issued a notice of eligibility and 90-day notice to a residential tenant to be displaced. Exhibit E.",
        "17. Plaintiffs allege that, instead of lawfully bifurcating Julio Regal Florez-Cortez from the lease after bifurcation was requested, HACC removed or excluded him from the tenancy and effectively evicted him through the same notice and lease-administration sequence.",
        "18. On January 1, 2026, HACC generated another lease-amendment document tied to household composition and a VAWA-related sequence. Exhibit F.",
        "19. On January 8, 2026, HACC sent a Blossom-related notice stating in substance that if the letter was received, the Tenant Protection Voucher process had not yet started and that Ashley Ferron should be contacted to start that process. Exhibit G.",
        "20. Plaintiffs allege that they submitted Blossom-related paperwork in December 2025 and later reiterated in writing that the application had not been processed, that service-animal issues had been raised, and that the relocation path through Blossom had stalled. Exhibit J.",
        "21. Plaintiffs allege that Quantum failed to process or transmit the application to HACC and that neither HACC nor Quantum issued a timely approval, denial, or lawful written deficiency notice. Exhibit G; Exhibit J.",
        "22. On February 4, 2026, HACC issued a 30-day for-cause notice directed to Jane Kay Cortez and Benjamin Jay Barber. Exhibit H.",
        "23. On February 9, 2026, HACC issued an additional-information demand requiring extensive income, tax, banking, and asset documentation. Exhibit I.",
        "24. The associated email thread shows repeated escalations of documentation demands even after plaintiffs had already supplied tax and financial materials. Exhibit J.",
        "25. In that thread, HACC requested proof of tax filings for multiple businesses, crypto-account statements, all bank statements for household members, and other asset categories, and demanded production by March 4, 2026. Exhibit J.",
        "26. On February 13, 2026, HACC issued a 30-Day Notice of Termination addressed directly to Julio Regal Florez-Cortez, effective March 19, 2026, stating that HACC was terminating his tenancy under the public housing lease. Exhibit N.",
        "27. Plaintiffs further allege, based on household observation during the February 2026 termination sequence, that HACC told Julio Regal Florez-Cortez he could request a hearing in writing even though he could not write in any language, and that no hearing was provided after he requested one orally. Plaintiffs further allege that HACC policy materials required hearing rights to be stated in termination notices and required reasonable accommodation for persons with disabilities to participate in the hearing process.",
        "28. On February 26, 2026, HACC issued another written communication identified in the evidence review as a steering-related notice. Exhibit K.",
        "29. In emails preserved in Exhibit J, Benjamin Jay Barber wrote that Blossom had refused to process applications submitted for two months, refused to house a service animal, and engaged in race discrimination, while HACC and Quantum continued to delay the processes needed to leave HACC-controlled housing. Exhibit J.",
        "30. Plaintiffs allege that HACC knew of those complaints and continued the challenged documentation and relocation conduct afterward. Exhibit J; Exhibit K.",
        "31. Exhibit G identified Ashley Ferron as the contact to start the Tenant Protection Voucher process. Preserved complaint emails in Exhibit J show Ashley Ferron remained copied on plaintiffs' written complaints through March 10, 2026, and by March 17 through March 20, 2026 the orientation and voucher emails were being sent by Kati Tilton. Exhibit G; Exhibit J; Exhibit M.",
        "32. Exhibit G shows that, as of January 8, 2026, HACC stated the Tenant Protection Voucher process had not yet started, while Exhibit J shows written complaints continuing through late February and early March 2026, and Exhibit M does not show orientation and voucher communications until March 17 through March 20, 2026. Together, those exhibits support plaintiffs' allegation that voucher processing was materially delayed during the relocation dispute.",
        "33. On March 17, 2026, HACC circulated an inspection notice referencing a HUD NSPIRE inspection. Exhibit L.",
        "34. On March 17 through March 20, 2026, HACC and Benjamin Jay Barber exchanged emails about HCV orientation, voucher issuance, and accommodation. Exhibit M.",
        "35. In those emails, HACC first sent a two-bedroom subsidy worksheet and voucher issuance, then stated on March 19, 2026 that the two-bedroom voucher had been created and sent in error and that a one-bedroom voucher would instead be issued. Exhibit M.",
        "36. In the March 20, 2026 thread, Benjamin Jay Barber responded that he already had a scheduled appointment to obtain a reasonable accommodation for a two-bedroom, first-floor unit and explained that a one-bedroom arrangement was not workable because Jane Kay Cortez could not climb stairs, Benjamin Barber served as her main caregiver, the two could not reasonably share a bedroom because of privacy concerns, and Jane needed ongoing assistance with ADLs and IADLs. Exhibit M. By March 24, 2026, plaintiffs had provider verification stating that Jane Kay Cortez met the fair-housing disability definition, that her dog Sarah alleviated disability symptoms, and that the requested accommodation was disability-related and necessary for equal housing access. Exhibit O.",
        "37. On March 20, 2026, Kati Tilton wrote that the voucher could be reissued as a two-bedroom if plaintiffs were approved for a reasonable accommodation. Exhibit M.",
        "38. Plaintiffs allege that HACC nevertheless delayed or denied the accommodation and redirected the household from the expected two-bedroom, first-floor arrangement to a one-bedroom configuration that did not meet the household's no-stairs, caregiving, privacy, ADL/IADL support, work-from-home, mobility, and service-animal needs, even after provider verification was completed in late March 2026. Exhibits J, M, and O.",
        "39. Plaintiffs further allege that defendants knew of disability-related needs affecting bedroom count, accessibility, service-animal use, caregiver status, dignitary privacy, and Julio Regal Florez-Cortez's inability to submit a written hearing request, but still refused to process the housing transition in a timely and lawful manner.",
        "40. Plaintiffs allege that defendants' conduct caused concrete injury including imminent eviction risk, delayed relocation, loss of housing opportunity, loss of time and income, emotional distress, and continuing instability for the household.",
        "",
        "AUTHORITIES INCORPORATED INTO THIS PLEADING",
        "",
        "41. The Fair Housing Act prohibits discrimination in the terms, conditions, privileges, services, or facilities connected to a dwelling because of disability and requires reasonable accommodations in rules, policies, practices, or services when necessary to afford equal opportunity to use and enjoy a dwelling. 42 U.S.C. section 3604(f)(2) and (3)(B).",
        "42. The Fair Housing Act also prohibits coercion, intimidation, threats, and interference with persons who exercise or aid fair-housing rights. 42 U.S.C. section 3617; 24 C.F.R. section 100.400.",
        "43. Section 504 of the Rehabilitation Act prohibits disability discrimination by programs or activities receiving federal financial assistance. 29 U.S.C. section 794.",
        "44. Title II of the Americans with Disabilities Act prohibits disability discrimination by public entities in services, programs, and activities. 42 U.S.C. section 12132.",
        "45. Federal housing-program law requires notice and an opportunity for an informal hearing in covered participant disputes. 42 U.S.C. section 1437d(k); 24 C.F.R. section 982.555.",
        "46. Oregon law independently prohibits disability discrimination and source-of-income discrimination in housing transactions and authorizes civil remedies. ORS 659A.145; ORS 659A.421; ORS 659A.425; ORS 659A.885.",
        "47. Oregon law and HACC policy also govern the notice and termination process implicated by the challenged displacement and lease actions. ORS 90.427; HACC ACOP 13-IV.D.",
        "",
        "COUNT I",
        "FAILURE TO PROVIDE REASONABLE ACCOMMODATION AND DISABILITY DISCRIMINATION",
        "Against HACC and Quantum under the Fair Housing Act, and against HACC only under Section 504 and Title II",
        "",
        "48. Plaintiffs reallege the preceding paragraphs.",
        "49. Plaintiffs requested a two-bedroom, first-floor accommodation and related housing relief because Jane Kay Cortez required mobility and cognitive accommodations, could not climb stairs, needed Benjamin Jay Barber as her live-in caregiver, could not reasonably share a bedroom with him because of privacy concerns, and required ongoing assistance with ADLs and IADLs, while the household also needed room for a scooter and service animal. Exhibits M and O.",
        "50. Plaintiffs further allege that Julio Regal Florez-Cortez required an accessible means of requesting a hearing because he could not write in any language and therefore could not use a hearing-request procedure conditioned on written submission. Exhibit N. Plaintiffs further rely on HACC's ACOP provisions requiring reasonable accommodation in the hearing process and written notice of hearing rights when assistance is terminated.",
        "51. HACC acknowledged in writing on March 20, 2026 that the voucher could be reissued as a two-bedroom if the accommodation were approved, but had already reversed a two-bedroom issuance and replaced it with a one-bedroom issuance it claimed had been sent in error. Exhibit M. By March 24, 2026, the provider verification materials reflected that the requested accommodation was related to disability and necessary for equal housing access. Exhibit O.",
        "52. Plaintiffs allege that defendants failed to provide a prompt, interactive, and lawful accommodation process and still denied or delayed the two-bedroom voucher accommodation needed for Jane's stair, privacy, and caregiver-support needs despite the late-March disability verification. Exhibits G, J, M, and O.",
        "53. Plaintiffs further allege that Quantum refused to process the Blossom application and refused to accommodate the household's service animal, thereby participating in disability-based housing discrimination under the Fair Housing Act. Exhibit J.",
        "54. These acts violated 42 U.S.C. section 3604(f)(2) and (3)(B), and as to HACC also violated 29 U.S.C. section 794 and 42 U.S.C. section 12132.",
        "",
        "COUNT II",
        "FAIR HOUSING RETALIATION AND INTERFERENCE",
        "Against HACC and Quantum",
        "",
        "55. Plaintiffs reallege the preceding paragraphs.",
        "56. Plaintiffs engaged in protected activity by complaining to HACC and Quantum about race discrimination, disability discrimination, service-animal issues, unlawful housing administration, retaliation, and violations of fair-housing rights. Exhibit J.",
        "57. Defendants knew of those complaints.",
        "58. After those complaints, defendants escalated adverse conduct by issuing or maintaining notices to vacate, delaying voucher issuance, reversing a two-bedroom voucher, demanding excessive documentation, refusing to process the Blossom application, and blocking or burdening relocation out of HACC-controlled housing. Exhibits H, I, J, K, and M.",
        "59. These acts violated 42 U.S.C. section 3617 and 24 C.F.R. section 100.400.",
        "",
        "COUNT III",
        "PROCEDURAL DUE PROCESS AND FEDERAL HEARING VIOLATIONS",
        "Against HACC",
        "",
        "60. Plaintiffs reallege the preceding paragraphs.",
        "61. HACC acted under color of state law when administering public-housing, displacement, TPV, PBV, HCV, grievance, and hearing processes.",
        "62. Plaintiffs had protected interests in continued housing benefits, lawful displacement procedures, and the notice and hearing protections attached to HACC-administered housing assistance.",
        "63. HACC issued or maintained adverse notices and housing-administration decisions affecting plaintiffs' rights, obligations, welfare, or status without providing the clear, timely, and meaningful hearing process required by federal law, including the February 13, 2026 termination notice addressed to Julio Regal Florez-Cortez. Exhibits B, C, D, E, H, K, and N.",
        "64. Plaintiffs allege, based on household observation, that HACC conditioned Julio Regal Florez-Cortez's access to a hearing on a written request even though he was incapable of writing in any language and had specifically requested a hearing orally. Exhibit N. Plaintiffs further rely on HACC's ACOP provisions requiring reasonable accommodation for persons with disabilities to participate in the hearing process.",
        "65. Plaintiffs allege that no meaningful hearing or appeal was scheduled before the threatened loss of housing and that HACC failed to provide sufficient notice, document access, hearing access, accommodation in the hearing-request process, or a timely decision process.",
        "66. These acts violated the Fourteenth Amendment, actionable under 42 U.S.C. section 1983, together with 42 U.S.C. section 1437d(k) and 24 C.F.R. section 982.555.",
        "",
        "COUNT IV",
        "SUPPLEMENTAL OREGON HOUSING DISCRIMINATION CLAIMS",
        "Against HACC and Quantum",
        "",
        "67. Plaintiffs reallege the preceding paragraphs.",
        "68. Defendants discriminated in housing-related terms, services, processing, and access on the basis of disability and source of income by refusing or delaying accommodation, failing to process the Blossom application, obstructing voucher-backed housing access, and imposing unreasonable or selectively administered intake barriers. Exhibits G, I, J, and M.",
        "69. Plaintiffs further allege that Quantum participated in the refusal to process a voucher-linked application and in service-animal or accommodation-related discrimination at Blossom. Exhibit J.",
        "70. These acts violated ORS 659A.145, ORS 659A.421, ORS 659A.425, and ORS 659A.885.",
        "",
        "COUNT V",
        "SUPPLEMENTAL OREGON NOTICE, LEASE, AND PROGRAM CLAIMS",
        "Against HACC",
        "",
        "71. Plaintiffs reallege the preceding paragraphs.",
        "72. HACC issued or maintained termination and displacement notices while also controlling the relocation and voucher process needed to avoid unlawful housing loss. Exhibits A, C, D, E, F, H, and N.",
        "73. Plaintiffs further allege that HACC destabilized the household through unlawful lease-administration and household-composition handling despite prior requests for bifurcation, restraining-order-related protections, and relocation assistance, and that HACC effectively evicted Julio Regal Florez-Cortez instead of lawfully handling the requested bifurcation process.",
        "74. These acts violated ORS 90.427 and the applicable HACC lease and ACOP provisions incorporated into the tenancy and displacement process.",
        "",
        "PRAYER FOR RELIEF",
        "",
        "WHEREFORE, Plaintiffs request judgment against defendants as follows:",
        "A. Temporary, preliminary, and permanent injunctive relief preventing eviction, lockout, or loss of housing assistance while these claims are resolved.",
        "B. Declaratory relief that defendants' handling of the voucher, accommodation, grievance, hearing, application, and lease issues was unlawful.",
        "C. Injunctive relief requiring prompt processing of a two-bedroom accommodation, lawful voucher administration, and meaningful hearing access.",
        "D. Compensatory damages for housing instability, lost work time, emotional distress, and relocation-related losses.",
        "E. Punitive damages on the Fair Housing Act retaliation and interference claims to the extent permitted by law.",
        "F. Costs, fees, and any further relief authorized by law.",
        "G. Pre-judgment and post-judgment interest as permitted by law.",
        "H. Such other and further relief as the Court deems just and proper.",
        "",
        "JURY DEMAND",
        "",
        "Plaintiffs demand a trial by jury on all issues so triable.",
        "",
        "SIGNATURE BLOCK",
        "",
        "Dated: ____________________",
        "",
        "Respectfully submitted,",
        "",
    ]
    for name in plaintiff_names:
        lines.extend([f"{name}, pro se", address_block, ""])
    return "\n".join(lines).rstrip() + "\n"


def migrate_legacy_session(
    *,
    statefile: Path = DEFAULT_STATEFILE,
    workspace_root: Path = DEFAULT_WORKSPACE_ROOT,
    user_id: str = "did:key:legacy-temporary-session",
) -> Dict[str, Any]:
    workspace_root.mkdir(parents=True, exist_ok=True)
    migration_manifest = ensure_workspace_source_snapshot(workspace_root)
    payload = json.loads(statefile.read_text(encoding="utf-8"))
    state = dict(payload.get("state") or {})
    facts = extract_case_facts(state)

    service = ComplaintWorkspaceService(root_dir=workspace_root)
    service.reset_session(user_id)
    service.update_claim_type(user_id, "housing_discrimination")
    service.update_filing_metadata(user_id, facts.filing_metadata)
    service.submit_intake_answers(user_id, facts.intake_answers)
    _save_structured_evidence(service, user_id, facts, statefile)

    imported_paths: List[str] = []
    for path in evidence_import_paths(workspace_root):
        service.import_local_evidence(
            user_id,
            paths=[str(path)],
            claim_element_id="causation",
            kind="document",
        )
        imported_paths.append(str(path))

    draft_payload = service.generate_complaint(user_id, requested_relief=facts.requested_relief)
    custom_body = _render_exhibit_cited_complaint(facts)
    custom_title = (
        ((draft_payload.get("draft") or {}).get("title"))
        or "Complaint for Housing Discrimination and Related Violations"
    )
    draft_payload = service.update_draft(
        user_id,
        title=custom_title,
        body=custom_body,
        requested_relief=facts.requested_relief,
    )
    if isinstance(draft_payload.get("draft"), dict):
        draft_payload["draft"]["draft_strategy"] = "exhibit_cited_legacy_renderer"
    review_payload = service.call_mcp_tool("complaint.review_case", {"user_id": user_id})
    export_payload = service.export_complaint_markdown(user_id)
    body = str(((draft_payload.get("draft") or {}).get("body")) or custom_body)

    markdown_path = workspace_root / "improved-complaint-from-temporary-session.md"
    exhibit_map_path = workspace_root / "improved-complaint-from-temporary-session.exhibit-map.md"
    julio_declaration_path = workspace_root / "improved-complaint-from-temporary-session.julio-hearing-declaration.md"
    benjamin_julio_declaration_path = workspace_root / "improved-complaint-from-temporary-session.benjamin-julio-hearing-declaration.md"
    jane_julio_declaration_path = workspace_root / "improved-complaint-from-temporary-session.jane-julio-hearing-declaration.md"
    julio_hearing_prep_memo_path = workspace_root / "improved-complaint-from-temporary-session.julio-hearing-witness-prep.md"
    julio_hearing_finalize_path = workspace_root / "improved-complaint-from-temporary-session.julio-hearing-finalize-checklist.md"
    julio_hearing_acop_excerpt_path = workspace_root / "improved-complaint-from-temporary-session.julio-hearing-acop-excerpt.md"
    julio_hearing_packet_index_path = workspace_root / "improved-complaint-from-temporary-session.julio-hearing-packet-index.md"
    julio_hearing_filing_cover_note_path = workspace_root / "improved-complaint-from-temporary-session.julio-hearing-filing-cover-note.md"
    benjamin_julio_signing_worksheet_path = workspace_root / "improved-complaint-from-temporary-session.benjamin-julio-signing-worksheet.md"
    benjamin_julio_fillable_declaration_path = workspace_root / "improved-complaint-from-temporary-session.benjamin-julio-hearing-declaration-fillable.md"
    former_employee_review_path = workspace_root / "improved-complaint-from-temporary-session.former-employee-review.png"
    summary_path = workspace_root / "improved-complaint-from-temporary-session.summary.json"
    if FORMER_EMPLOYEE_REVIEW_SCREENSHOT_PATH.exists():
        shutil.copy2(FORMER_EMPLOYEE_REVIEW_SCREENSHOT_PATH, former_employee_review_path)
    markdown_path.write_text(body.rstrip() + "\n", encoding="utf-8")
    exhibit_map_path.write_text(_render_exhibit_map(workspace_root).rstrip() + "\n", encoding="utf-8")
    julio_declaration_path.write_text(
        _render_julio_hearing_declaration_template(facts).rstrip() + "\n",
        encoding="utf-8",
    )
    benjamin_julio_declaration_path.write_text(
        _render_benjamin_julio_hearing_declaration(facts).rstrip() + "\n",
        encoding="utf-8",
    )
    jane_julio_declaration_path.write_text(
        _render_jane_julio_hearing_declaration(facts).rstrip() + "\n",
        encoding="utf-8",
    )
    julio_hearing_prep_memo_path.write_text(
        _render_julio_hearing_witness_prep_memo().rstrip() + "\n",
        encoding="utf-8",
    )
    julio_hearing_finalize_path.write_text(
        _render_julio_hearing_finalize_checklist().rstrip() + "\n",
        encoding="utf-8",
    )
    julio_hearing_acop_excerpt_path.write_text(
        _render_julio_hearing_acop_excerpt().rstrip() + "\n",
        encoding="utf-8",
    )
    julio_hearing_packet_index_path.write_text(
        _render_julio_hearing_packet_index().rstrip() + "\n",
        encoding="utf-8",
    )
    julio_hearing_filing_cover_note_path.write_text(
        _render_julio_hearing_filing_cover_note().rstrip() + "\n",
        encoding="utf-8",
    )
    benjamin_julio_signing_worksheet_path.write_text(
        _render_benjamin_julio_signing_worksheet().rstrip() + "\n",
        encoding="utf-8",
    )
    benjamin_julio_fillable_declaration_path.write_text(
        _render_benjamin_julio_fillable_declaration(facts).rstrip() + "\n",
        encoding="utf-8",
    )
    summary = {
        "statefile": str(statefile),
        "workspace_root": str(workspace_root),
        "user_id": user_id,
        "draft_title": ((draft_payload.get("draft") or {}).get("title")),
        "draft_strategy": "exhibit_cited_legacy_renderer",
        "claim_type": "housing_discrimination",
        "caption_plaintiffs": facts.caption_plaintiffs,
        "defendants": facts.defendants_caption,
        "filing_metadata": facts.filing_metadata,
        "intake_answers": facts.intake_answers,
        "chronology_paragraphs": facts.chronology_paragraphs,
        "requested_relief": facts.requested_relief,
        "unresolved_gaps": facts.unresolved_gaps,
        "review_overview": ((review_payload.get("review") or {}).get("overview") or {}),
        "generated_review_snapshot": ((draft_payload.get("review") or {}).get("overview") or {}),
        "migration_manifest": migration_manifest,
        "imported_paths": imported_paths,
        "output_markdown_path": str(markdown_path),
        "exhibit_map_path": str(exhibit_map_path),
        "julio_hearing_declaration_path": str(julio_declaration_path),
        "benjamin_julio_hearing_declaration_path": str(benjamin_julio_declaration_path),
        "jane_julio_hearing_declaration_path": str(jane_julio_declaration_path),
        "julio_hearing_witness_prep_memo_path": str(julio_hearing_prep_memo_path),
        "former_employee_review_path": str(former_employee_review_path),
        "export_excerpt": str(((export_payload.get("artifacts") or {}).get("markdown") or {}).get("excerpt") or "")[:2000],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "markdown_path": str(markdown_path),
        "exhibit_map_path": str(exhibit_map_path),
        "julio_hearing_declaration_path": str(julio_declaration_path),
        "benjamin_julio_hearing_declaration_path": str(benjamin_julio_declaration_path),
        "jane_julio_hearing_declaration_path": str(jane_julio_declaration_path),
        "julio_hearing_witness_prep_memo_path": str(julio_hearing_prep_memo_path),
        "julio_hearing_finalize_checklist_path": str(julio_hearing_finalize_path),
        "julio_hearing_acop_excerpt_path": str(julio_hearing_acop_excerpt_path),
        "former_employee_review_path": str(former_employee_review_path),
        "julio_hearing_packet_index_path": str(julio_hearing_packet_index_path),
        "julio_hearing_filing_cover_note_path": str(julio_hearing_filing_cover_note_path),
        "benjamin_julio_signing_worksheet_path": str(benjamin_julio_signing_worksheet_path),
        "benjamin_julio_fillable_declaration_path": str(benjamin_julio_fillable_declaration_path),
        "summary_path": str(summary_path),
        "draft": draft_payload.get("draft") or {},
        "review": review_payload.get("review") or {},
        "migration_manifest": migration_manifest,
        "imported_paths": imported_paths,
    }


# ---------------------------------------------------------------------------
# Versioned private migration (CIMP-DUR-002)
# The legacy snapshot above remains an explicit plaintext export. It is not
# invoked by the encrypted migration path.
# ---------------------------------------------------------------------------

import hashlib
import stat as _stat

PRIVATE_MIGRATION_SCHEMA = "complaint-private-migration/v1"
PRIVATE_MIGRATION_VERSION = 1
_MANIFEST_NAME = "private_migration_manifest.json"
_PUBLIC_ENTRY_FIELDS = (
    "artifact_ref",
    "ciphertext_name",
    "ciphertext_sha256",
    "readback",
    "status",
)


class PrivateMigrationError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class PrivateMigrationInterrupted(PrivateMigrationError):
    def __init__(self, partial: Dict[str, Any]) -> None:
        super().__init__("interrupted", "migration interrupted before the next artifact commit")
        self.partial = partial


def _opaque_ref(tenant_id: str, case_id: str, kind: str, revision: str) -> str:
    material = "\0".join((tenant_id, case_id, kind, revision)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_path(path: Path, *, root: Path | None = None) -> Path:
    """Reject symbolic paths before a source is opened or a destination is created."""
    path = Path(os.path.abspath(path))
    if root is not None and not path.is_relative_to(root):
        raise PrivateMigrationError("path_outside_source")
    for parent in [*reversed(path.parents), path]:
        try:
            metadata = parent.lstat()
        except FileNotFoundError:
            continue
        if _stat.S_ISLNK(metadata.st_mode):
            raise PrivateMigrationError("unsafe_path")
    return path


def _regular_bytes(path: Path, *, single_link: bool = False) -> bytes:
    _safe_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        if not _stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise PrivateMigrationError("unsafe_path")
        if single_link and metadata.st_nlink != 1:
            raise PrivateMigrationError("unsafe_path")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(fd)


def _private_directory(path: Path) -> Path:
    path = _safe_path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = path.lstat()
    if not _stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise PrivateMigrationError("unsafe_path")
    os.chmod(path, 0o700)
    return path


def _read_manifest(path: Path) -> Dict[str, Any]:
    try:
        raw = _regular_bytes(path, single_link=True)
    except FileNotFoundError:
        return {"schema": PRIVATE_MIGRATION_SCHEMA, "schema_version": PRIVATE_MIGRATION_VERSION, "entries": [], "complete": False}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise PrivateMigrationError("malformed_manifest") from None
    if (not isinstance(payload, dict) or set(payload) != {"schema", "schema_version", "entries", "complete"}
            or payload.get("schema") != PRIVATE_MIGRATION_SCHEMA
            or type(payload.get("schema_version")) is not int or payload["schema_version"] != PRIVATE_MIGRATION_VERSION
            or type(payload.get("complete")) is not bool or not isinstance(payload.get("entries"), list)):
        raise PrivateMigrationError("malformed_manifest")
    seen = set()
    for entry in payload["entries"]:
        if not isinstance(entry, dict) or set(entry) != set(_PUBLIC_ENTRY_FIELDS):
            raise PrivateMigrationError("malformed_manifest")
        ref = entry["artifact_ref"]
        digest = entry["ciphertext_sha256"]
        if (not isinstance(ref, str) or len(ref) != 64 or any(c not in "0123456789abcdef" for c in ref)
                or ref in seen or entry["ciphertext_name"] != ref + ".bin"
                or not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                or entry["readback"] != "verified" or entry["status"] != "processed"):
            raise PrivateMigrationError("malformed_manifest")
        seen.add(ref)
    return payload


def _write_private_bytes(path: Path, payload: bytes, *, replace: bool = True) -> None:
    import tempfile
    fd, name = tempfile.mkstemp(prefix=".private-migration-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    published = False
    directory_fd = None
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if _regular_bytes(temporary, single_link=True) != payload:
            raise PrivateMigrationError("readback_mismatch")
        if path.exists():
            _regular_bytes(path, single_link=True)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        if replace:
            os.replace(temporary, path)
        else:
            # Exclusive publication preserves a concurrently created destination.
            os.link(temporary, path, follow_symlinks=False)
            published = True
            temporary.unlink()
        published = True
        os.fsync(directory_fd)
    except OSError:
        raise PrivateMigrationError("publication_indeterminate" if published else "publication_failed") from None
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass  # A retained staging file contains ciphertext only.


def _write_manifest(path: Path, payload: Dict[str, Any]) -> None:
    _write_private_bytes(path, json.dumps(payload, sort_keys=True).encode("utf-8"))


def _owner_record_matches(artifact: Dict[str, Any]) -> bool:
    record = artifact.get("owner_record")
    if not isinstance(record, dict):
        return False
    owner, case_id = record.get("owner"), record.get("case_id")
    access = artifact.get("access")
    return bool(isinstance(owner, str) and owner and isinstance(case_id, str) and case_id
                and owner == artifact.get("tenant_id") and case_id == artifact.get("case_id")
                and str(artifact.get("principal_id") or owner) == owner
                and getattr(access, "trust", None) in {"authenticated", "trusted_local"}
                and getattr(access, "principal_id", None) == owner and getattr(access, "case_id", None) == case_id)


def _artifact_bytes(artifact: Dict[str, Any]) -> bytes:
    if "payload" in artifact:
        payload = artifact["payload"]
        return payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    if artifact.get("source_path") is None:
        raise PrivateMigrationError("missing_payload")
    return _regular_bytes(Path(artifact["source_path"]))


def _sources_match(original_sources: Dict[str, bytes]) -> bool:
    try:
        return all(_regular_bytes(Path(path)) == payload for path, payload in original_sources.items())
    except (OSError, PrivateMigrationError):
        return False


def _cleanup_sources(artifacts: List[Dict[str, Any]], roots: List[Path], originals: Dict[str, bytes]) -> Dict[str, Any]:
    """Validate every original, located hardlink and declared copy before deleting any."""
    planned: Dict[Path, tuple[int, int, bytes]] = {}
    try:
        for artifact in artifacts:
            if artifact.get("source_path") is None:
                continue
            source = Path(artifact["source_path"])
            payload = originals[str(source)]
            if _regular_bytes(source) != payload:
                return {"cleanup_performed": False, "cleanup_complete": False, "code": "source_changed"}
            metadata = source.stat()
            located = set()
            for root in roots:
                for candidate in root.rglob("*"):
                    if candidate.is_symlink():
                        continue
                    info = candidate.lstat()
                    if _stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == (metadata.st_dev, metadata.st_ino):
                        located.add(candidate)
            if len(located) != metadata.st_nlink:
                return {"cleanup_performed": False, "cleanup_complete": False, "code": "external_hardlink"}
            for candidate in located | {Path(item) for item in artifact.get("copy_paths", [])}:
                if _regular_bytes(candidate) != payload:
                    return {"cleanup_performed": False, "cleanup_complete": False, "code": "copy_mismatch"}
                info = candidate.stat()
                # A declared copy with an unaccounted external link is also not erased.
                if candidate not in located and info.st_nlink != 1:
                    return {"cleanup_performed": False, "cleanup_complete": False, "code": "external_hardlink"}
                planned[candidate] = (info.st_dev, info.st_ino, payload)
        # Recheck the entire deletion set; never restore or replace an outside writer's bytes.
        for candidate, (dev, ino, payload) in planned.items():
            info = candidate.lstat()
            if (info.st_dev, info.st_ino) != (dev, ino) or _regular_bytes(candidate) != payload:
                return {"cleanup_performed": False, "cleanup_complete": False, "code": "source_changed"}
    except (OSError, PrivateMigrationError):
        return {"cleanup_performed": False, "cleanup_complete": False, "code": "cleanup_unavailable"}
    removed = 0
    try:
        for candidate in planned:
            candidate.unlink()
            removed += 1
    except OSError:
        return {"cleanup_performed": bool(removed), "cleanup_complete": False, "removed_count": removed, "code": "cleanup_incomplete"}
    return {"cleanup_performed": True, "cleanup_complete": True, "removed_count": removed}


def migrate_private_workspace(
    *, source_root: Path, destination_root: Path, artifacts: List[Dict[str, Any]],
    snapshot_roots: List[Path] | None = None, cleanup: bool = False,
    fail_after_committed: int | None = None,
) -> Dict[str, Any]:
    """Explicit owned migration: encrypt, authenticate readback, then record progress.

    Legacy originals remain unchanged until a separate explicit cleanup request.
    No source rollback can overwrite another writer's changes.
    """
    from integrations.private_storage import (PrivateArtifactBinding, PrivateKeyMaterialError,
        PrivateStorageError, open_private_artifact, seal_private_artifact)
    source_root = _safe_path(Path(source_root))
    if not source_root.is_dir() or source_root.stat().st_uid != os.getuid():
        raise PrivateMigrationError("unsafe_path")
    roots = [source_root, *[_safe_path(Path(item)) for item in snapshot_roots or []]]
    for root in roots:
        if not root.is_dir() or root.stat().st_uid != os.getuid():
            raise PrivateMigrationError("unsafe_path")
    # Admit every owner before opening any source or creating a destination.
    if not artifacts or any(not isinstance(item, dict) or not _owner_record_matches(item) for item in artifacts):
        return {"schema": PRIVATE_MIGRATION_SCHEMA, "schema_version": PRIVATE_MIGRATION_VERSION,
                "status": "owner_mismatch", "code": "owner_mismatch", "complete": False,
                "committed": 0, "total": len(artifacts), "entries": [], "source_bytes_preserved": True,
                "cleanup_performed": False, "cleanup_complete": False}
    admitted = []
    refs = set()
    for supplied in artifacts:
        item = dict(supplied)
        for field in ("artifact_kind", "revision"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise PrivateMigrationError("invalid_binding")
        if item.get("source_path") is not None:
            item["source_path"] = _safe_path(Path(item["source_path"]), root=source_root)
        copies = []
        for name in item.get("copy_paths", []):
            path = _safe_path(Path(name))
            if not any(path.is_relative_to(root) for root in roots):
                raise PrivateMigrationError("path_outside_source")
            copies.append(path)
        item["copy_paths"] = copies
        ref = _opaque_ref(item["tenant_id"], item["case_id"], item["artifact_kind"], item["revision"])
        if ref in refs:
            raise PrivateMigrationError("duplicate_binding")
        refs.add(ref)
        admitted.append(item)
    destination_root = _private_directory(Path(destination_root))
    # Ciphertext output may not replace a source or one of its declared copies.
    source_paths = {Path(item["source_path"]) for item in admitted if item.get("source_path") is not None}
    source_paths.update(Path(copy) for item in admitted for copy in item["copy_paths"])
    manifest_path = destination_root / _MANIFEST_NAME
    if manifest_path in source_paths or any(destination_root / (ref + ".bin") in source_paths for ref in refs):
        raise PrivateMigrationError("source_destination_overlap")
    manifest = _read_manifest(manifest_path)
    entries = {entry["artifact_ref"]: entry for entry in manifest["entries"]}
    originals = {str(item["source_path"]): _artifact_bytes(item) for item in admitted if item.get("source_path") is not None}
    committed = 0

    def finish(status: str, code: str = "", *, publish: bool = True) -> Dict[str, Any]:
        preserved = _sources_match(originals)
        if status == "complete" and not preserved:
            status, code = "recoverable", "source_changed"
        complete = status == "complete" and bool(refs) and refs.issubset(entries) and committed == len(admitted)
        manifest["entries"] = list(entries.values())
        manifest["complete"] = complete
        manifest_durable = False
        if publish and (manifest_path.exists() or entries):
            try:
                _write_manifest(manifest_path, manifest)
                manifest_durable = True
            except (PrivateMigrationError, OSError) as exc:
                status, code, complete = "recoverable", getattr(exc, "code", "publication_failed"), False
        elif complete:
            complete = False
        result = {"cleanup_performed": False, "cleanup_complete": False}
        if complete and cleanup:
            result = _cleanup_sources(admitted, roots, originals)
        return {"schema": PRIVATE_MIGRATION_SCHEMA, "schema_version": PRIVATE_MIGRATION_VERSION,
                "status": status, "code": code, "committed": committed, "total": len(admitted), "complete": complete,
                "manifest_durable": manifest_durable,
                "publication_indeterminate": code == "publication_indeterminate",
                "cleanup_available": complete and not result["cleanup_performed"],
                **result, "cleanup_code": result.get("code", ""), "code": code,
                "manifest_path": str(manifest_path), "entries": list(entries.values()),
                "source_bytes_preserved": preserved if not result["cleanup_performed"] else False}

    for item in admitted:
        binding = PrivateArtifactBinding(tenant_id=item["tenant_id"], case_id=item["case_id"],
            artifact_kind=item["artifact_kind"], revision=item["revision"], principal_id=item.get("principal_id") or item["tenant_id"])
        ref = _opaque_ref(item["tenant_id"], item["case_id"], item["artifact_kind"], item["revision"])
        target = destination_root / (ref + ".bin")
        if fail_after_committed is not None and committed >= fail_after_committed:
            raise PrivateMigrationInterrupted(finish("interrupted"))
        try:
            if item.get("locked") is True:
                raise PrivateKeyMaterialError("key_locked")
            provider = item.get("key_provider")
            if provider is not None:
                key_id, key = provider.resolve(binding)
                if ((item.get("key") is not None and item["key"] != key)
                        or (item.get("key_id") is not None and item["key_id"] != key_id)):
                    raise PrivateKeyMaterialError("key_mismatch")
            else:
                key_id, key = item.get("key_id"), item.get("key")
                if key is None or not key_id:
                    raise PrivateKeyMaterialError("key_locked")
        except PrivateKeyMaterialError:
            return finish("recoverable", "destination_preserved") if target.exists() else finish("unlock_needed", "unlock_needed")
        try:
            payload = originals[str(item["source_path"])] if item.get("source_path") is not None else _artifact_bytes(item)
            if target.exists():
                if item.get("reject_existing_destination"):
                    return finish("recoverable", "destination_preserved")
                envelope = _regular_bytes(target, single_link=True)
                existing = entries.get(ref)
                if existing is not None and _sha256(envelope) != existing["ciphertext_sha256"]:
                    return finish("recoverable", "readback_failed")
                opened = open_private_artifact(envelope, binding=binding, key=key, expected_key_id=key_id)
                if opened != payload:
                    return finish("recoverable", "destination_preserved")
            else:
                if ref in entries:
                    return finish("recoverable", "readback_failed")
                envelope = seal_private_artifact(payload, binding=binding, key=key, key_id=key_id)
                # Staged bytes are ciphertext only; authenticate before committing the name.
                if open_private_artifact(envelope, binding=binding, key=key, expected_key_id=key_id) != payload:
                    return finish("recoverable", "readback_failed")
                _write_private_bytes(target, envelope, replace=False)
            readback = _regular_bytes(target, single_link=True)
            if readback != envelope or open_private_artifact(readback, binding=binding, key=key, expected_key_id=key_id) != payload:
                return finish("recoverable", "readback_failed")
        except PrivateMigrationError as exc:
            return finish("recoverable", exc.code, publish=False)
        except (OSError, PrivateStorageError, ValueError):
            return finish("recoverable", "readback_failed")
        entries[ref] = {"artifact_ref": ref, "ciphertext_name": ref + ".bin", "ciphertext_sha256": _sha256(envelope),
                        "readback": "verified", "status": "processed"}
        committed += 1
        manifest["entries"], manifest["complete"] = list(entries.values()), False
        try:
            _write_manifest(manifest_path, manifest)
        except (PrivateMigrationError, OSError) as exc:
            return finish("recoverable", getattr(exc, "code", "publication_failed"), publish=False)
    return finish("complete")
