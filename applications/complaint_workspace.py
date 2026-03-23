from __future__ import annotations

import json
import re
import uuid
from base64 import b64encode
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_USER_ID = "did:key:anonymous"
DEFAULT_UI_UX_OPTIMIZER_METHOD = "actor_critic"
DEFAULT_UI_UX_OPTIMIZER_PRIORITY = 90
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify_user_id(user_id: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(user_id or DEFAULT_USER_ID).strip())
    return normalized.strip("-") or DEFAULT_USER_ID


def _split_lines(value: Optional[str]) -> List[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _slugify_filename(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower())
    return normalized.strip("-") or "complaint-packet"


def _normalize_claim_type(value: Optional[str]) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized or "retaliation"


def _claim_type_display_name(value: Optional[str]) -> str:
    normalized = _normalize_claim_type(value)
    return _CLAIM_TYPE_LABELS.get(normalized, normalized.replace("_", " ").title())


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


def _parse_json_object(text: str) -> Dict[str, Any]:
    stripped = _strip_code_fences(text)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
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


def _has_required_formal_complaint_markers(body: str) -> bool:
    complaint_body = str(body or "")
    return all(marker in complaint_body for marker in _required_formal_complaint_markers())


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
        protected_activity = answers.get("protected_activity") or "engaged in protected activity"
        adverse_action = answers.get("adverse_action") or "suffered adverse action"
        timeline = answers.get("timeline") or "the events occurred close in time"
        harm = answers.get("harm") or "suffered compensable harm"
        relief = requested_relief or existing_draft.get("requested_relief") or [
            "Compensatory damages",
            "Back pay",
            "Injunctive relief",
        ]
        case_synopsis = self._build_case_synopsis(state)
        relief_lines = [f"{index}. {item}." for index, item in enumerate(relief, start=1)]
        support_count = int(overview.get("supported_elements") or 0)
        missing_count = int(overview.get("missing_elements") or 0)
        evidence_count = len(testimony_items) + len(document_items)
        testimony_reference_lines = [
            f"Plaintiff testimony or witness account titled '{item.get('title') or 'Untitled testimony'}' supports {item.get('claim_element_id') or 'an identified claim element'}."
            for item in testimony_items[:3]
        ]
        document_reference_lines = [
            f"Documentary exhibit '{item.get('title') or 'Untitled document'}' is presently tied to {item.get('claim_element_id') or 'an identified claim element'}."
            for item in document_items[:3]
        ]
        testimony_summary = "; ".join(
            f"{item.get('title') or 'Untitled testimony'} ({item.get('claim_element_id') or 'unmapped'})"
            for item in testimony_items[:3]
        ) or "No witness or complainant testimony has been summarized yet"
        document_summary = "; ".join(
            f"{item.get('title') or 'Untitled document'} ({item.get('claim_element_id') or 'unmapped'})"
            for item in document_items[:3]
        ) or "No documentary exhibits have been summarized yet"
        complaint_heading = f"COMPLAINT FOR {claim_label.upper()}"
        nature_of_action = {
            "retaliation": (
                f"1. {plaintiff} brings this retaliation complaint against {defendant}. "
                f"This civil action arises from {defendant}'s retaliatory response after {plaintiff} {protected_activity}."
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
        count_heading = {
            "retaliation": "COUNT I - RETALIATION",
            "employment_discrimination": "COUNT I - EMPLOYMENT DISCRIMINATION",
            "housing_discrimination": "COUNT I - HOUSING DISCRIMINATION",
            "due_process_failure": "COUNT I - DUE PROCESS VIOLATION",
            "consumer_protection": "COUNT I - CONSUMER PROTECTION",
        }.get(claim_type, f"COUNT I - {claim_label.upper()}")
        claim_paragraphs = {
            "retaliation": [
                f"{plaintiff} engaged in protected activity by {protected_activity}, and Defendant knew or should have known of that protected conduct.",
                f"Defendant thereafter subjected Plaintiff to materially adverse action, including {adverse_action}, under circumstances supporting retaliatory motive and causation.",
                "The pleaded chronology, evidentiary record, and resulting harm support a plausible retaliation claim because protected activity was followed by materially adverse conduct and damages.",
            ],
            "employment_discrimination": [
                f"Plaintiff was subjected to adverse employment treatment, including {adverse_action}, in a manner that was discriminatory, disparate, or otherwise unlawful.",
                "The pleaded facts support an inference that Defendant's conduct was motivated by unlawful bias, protected status, protected conduct, or a prohibited employment practice.",
                "The evidentiary record and resulting harm support a plausible employment discrimination claim.",
            ],
            "housing_discrimination": [
                f"Defendant denied, limited, burdened, or interfered with housing-related rights, opportunities, services, or benefits, including conduct reflected in {adverse_action}.",
                "The pleaded facts support an inference that Defendant acted in a discriminatory manner or retaliated in connection with protected housing activity, status, or rights.",
                "The evidentiary record and resulting harm support a plausible housing discrimination claim.",
            ],
            "due_process_failure": [
                "Defendant imposed or maintained adverse consequences without the notice, review, hearing, or procedural protections required by law.",
                f"The resulting deprivation included {adverse_action} and related harms without adequate procedural safeguards.",
                "The pleaded facts and evidentiary record support a plausible due process claim.",
            ],
            "consumer_protection": [
                "Defendant engaged in unfair, deceptive, misleading, or unlawful conduct in connection with a consumer transaction or obligation.",
                f"That conduct resulted in {adverse_action} and caused economic or other compensable harm, including {harm}.",
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
        body = "\n\n".join(
            [
                "IN THE UNITED STATES DISTRICT COURT",
                "FOR THE DISTRICT AND DIVISION IN WHICH THE UNLAWFUL PRACTICES OCCURRED",
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
                    f"Plaintiff {plaintiff}, by and through this Complaint, alleges upon personal knowledge as to "
                    "their own acts and upon information and belief as to all other matters, as follows:"
                ),
                "",
                "NATURE OF THE ACTION",
                nature_of_action,
                (
                    f"2. Plaintiff seeks damages, equitable relief, and any further relief necessary to remedy the retaliatory "
                    f"conduct, restore lost compensation, and prevent additional harm flowing from {adverse_action}."
                ),
                "",
                "JURISDICTION AND VENUE",
                "3. Jurisdiction is alleged in this Court because the controversy arises under retaliation law and related remedial doctrines applicable to the challenged conduct.",
                "4. Venue is alleged to be proper because a substantial part of the events or omissions giving rise to these claims occurred in this forum and the resulting harm was felt here.",
                "",
                "PARTIES",
                f"5. Plaintiff {plaintiff} is the person harmed by the retaliation described below.",
                f"6. Defendant {defendant} is the party from whom relief is sought and is responsible for the retaliatory actions alleged in this pleading.",
                "",
                "FACTUAL ALLEGATIONS",
                f"7. {plaintiff} alleges that they {protected_activity}.",
                "8. Plaintiff provided or attempted to provide protected information, opposition, reporting, or participation activity that should not have triggered reprisal.",
                f"9. After that protected activity, {plaintiff} experienced {adverse_action}.",
                f"10. The chronology currently available in the record shows that {timeline}.",
                f"11. As a direct and proximate result of Defendant's conduct, {plaintiff} suffered {harm}.",
                "",
                "EVIDENTIARY SUPPORT AND NOTICE",
                (
                    f"12. The current complaint record includes {evidence_count} saved evidence items, including testimony such as {testimony_summary}."
                ),
                (
                    f"13. The current documentary record includes the following summarized exhibits or records: {document_summary}."
                ),
                (
                    f"14. The present support review reflects {support_count} supported claim elements and {missing_count} open support gaps, "
                    "which Plaintiff identifies so the pleading can be refined rather than to concede any deficiency in the claim."
                ),
                (
                    "15. Plaintiff incorporates the current testimony summaries, documentary exhibits, chronology notes, and support review findings "
                    "as the preliminary exhibit and notice record for this pleading."
                ),
                *[
                    f"{16 + index}. {line}"
                    for index, line in enumerate((testimony_reference_lines + document_reference_lines)[:2])
                ],
                "",
                "CLAIM FOR RELIEF",
                count_heading,
                f"18. {plaintiff} repeats and realleges the preceding paragraphs as if fully set forth herein.",
                *[f"{19 + index}. {line}" for index, line in enumerate(claim_paragraphs)],
                f"22. Plaintiff has suffered damages and other losses including {harm}.",
                "23. Defendant's acts were intentional, knowing, reckless, retaliatory, discriminatory, deceptive, or otherwise unlawful under the governing claim theory.",
                "",
                "PRAYER FOR RELIEF",
                "Wherefore, Plaintiff requests judgment against Defendant and the following relief:",
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
                "",
                "WORKING CASE SYNOPSIS",
                f"Working case synopsis: {case_synopsis}",
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
        return (
            "You are revising a generated complaint so it reads like a formal legal complaint rather than a workflow summary.\n"
            "Use only the facts already present in the complaint record. Do not invent statutes, parties, dates, courts, judges, or evidence.\n"
            "Keep the output in plain text with numbered factual paragraphs and a clear caption. Preserve the requested relief unless the record plainly requires a tighter phrasing.\n"
            f"Claim-specific filing guidance: {_claim_type_filing_guidance(payload['claim_type'])}\n"
            "Retain these exact section headings in the body:\n"
            f"{markers}\n\n"
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
            backend_kwargs.setdefault("id", backend_id or "complaint-draft")
            if provider:
                backend_kwargs["provider"] = provider
            if model:
                backend_kwargs["model"] = model
            backend = LLMRouterBackend(**backend_kwargs)
            raw_response = backend(self._build_formal_complaint_generation_prompt(state, base_draft))
        except Exception:
            return None

        parsed = _parse_json_object(raw_response)
        llm_body = str(parsed.get("body") or "").strip()
        if not llm_body:
            raw_text = _strip_code_fences(raw_response)
            if _has_required_formal_complaint_markers(raw_text):
                llm_body = raw_text
        if not _has_required_formal_complaint_markers(llm_body):
            return None

        requested_relief = [
            str(item).strip()
            for item in list(parsed.get("requested_relief") or base_draft.get("requested_relief") or [])
            if str(item).strip()
        ]
        return {
            **deepcopy(base_draft),
            "title": str(parsed.get("title") or base_draft.get("title") or "Complaint").strip(),
            "body": llm_body,
            "requested_relief": requested_relief or list(base_draft.get("requested_relief") or []),
            "draft_strategy": "llm_router",
            "draft_backend": {
                "id": getattr(backend, "id", backend_id or "complaint-draft"),
                "provider": getattr(backend, "provider", provider),
                "model": getattr(backend, "model", model),
            },
        }

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

    def _build_export_artifacts(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        draft = dict(packet.get("draft") or {})
        filename_root = _slugify_filename(draft.get("title") or packet.get("title") or "complaint-packet")
        markdown_text = self._build_packet_markdown(packet)
        pdf_bytes = self._build_packet_pdf_bytes(packet, markdown_text)
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
            "updated_at": None,
        }

    def get_workflow_capabilities(self, user_id: Optional[str]) -> Dict[str, Any]:
        session = self.get_session(user_id)
        review = session["review"]
        overview = dict(review.get("overview") or {})
        current_draft = (session.get("session") or {}).get("draft")
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
            "complaint_readiness": readiness,
            "ui_readiness": self.get_ui_readiness(user_id),
            "capabilities": capabilities,
        }

    def export_complaint_packet(self, user_id: Optional[str]) -> Dict[str, Any]:
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
        ui_feedback = self._analyze_complaint_output(packet, artifact_analysis)
        return {
            "packet": packet,
            "artifacts": artifacts,
            "artifact_analysis": artifact_analysis,
            "ui_feedback": ui_feedback,
            "packet_summary": {
                "question_count": len(packet["questions"]),
                "answered_question_count": len([item for item in packet["questions"] if item.get("is_answered")]),
                "supported_elements": int((review.get("overview") or {}).get("supported_elements") or 0),
                "missing_elements": int((review.get("overview") or {}).get("missing_elements") or 0),
                "testimony_items": int((review.get("overview") or {}).get("testimony_items") or 0),
                "document_items": int((review.get("overview") or {}).get("document_items") or 0),
                "has_draft": bool(state.get("draft")),
                "complaint_readiness": self.get_complaint_readiness(user_id),
                "artifact_formats": sorted(artifacts.keys()),
            },
        }

    def _analyze_complaint_output(self, packet: Dict[str, Any], artifact_analysis: Dict[str, Any]) -> Dict[str, Any]:
        from .ui_review import review_complaint_output_with_llm_router

        draft = dict(packet.get("draft") or {})
        review = dict(packet.get("review") or {})
        overview = dict(review.get("overview") or {})
        body = str(draft.get("body") or "").strip()
        case_synopsis = str(packet.get("case_synopsis") or "").strip()
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
            "working_case_synopsis": "WORKING CASE SYNOPSIS" in body,
        }

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
                notes=(
                    "Assess whether this output looks like a formal legal complaint and turn any filing-shape defects "
                    "into UI/UX repairs for intake, evidence, review, draft, and export surfaces."
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
        filing_shape_score = (
            round((heuristic_score + router_score) / 2)
            if router_score
            else heuristic_score
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

        return {
            "summary": (
                "The exported complaint artifact was analyzed to infer which UI steps may still be too weak, "
                "hidden, or permissive for a real complainant."
            ),
            "filing_shape_score": filing_shape_score,
            "formal_sections_present": formal_sections_present,
            "issues": issues,
            "ui_suggestions": suggestions,
            "draft_excerpt": body[:600],
            "complaint_strengths": [
                f"Supported elements: {int(overview.get('supported_elements') or 0)}",
                f"Evidence items: {int(overview.get('testimony_items') or 0) + int(overview.get('document_items') or 0)}",
                f"Requested relief items: {int(artifact_analysis.get('requested_relief_count') or 0)}",
                f"Formal sections present: {sum(1 for value in formal_sections_present.values() if value)}/{len(formal_sections_present)}",
            ],
            "router_review": router_review,
        }

    def analyze_complaint_output(self, user_id: Optional[str]) -> Dict[str, Any]:
        payload = self.export_complaint_packet(user_id)
        return {
            "user_id": ((payload.get("packet") or {}).get("user_id") or str(user_id or DEFAULT_USER_ID)),
            "packet_summary": deepcopy(payload.get("packet_summary") or {}),
            "artifact_analysis": deepcopy(payload.get("artifact_analysis") or {}),
            "ui_feedback": deepcopy(payload.get("ui_feedback") or {}),
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
                "text_excerpt": str(draft.get("body") or "").strip()[:600],
                "markdown_filename": str(markdown_artifact.get("filename") or ""),
                "pdf_filename": str(pdf_artifact.get("filename") or ""),
                "markdown_excerpt": str(markdown_artifact.get("excerpt") or markdown_artifact.get("content") or "").strip()[:2000],
                "pdf_header": str(pdf_artifact.get("content_type") or "application/pdf"),
                "ui_suggestions_excerpt": "\n".join(line for line in suggestion_lines if line),
            }
        ]

    def export_complaint_markdown(self, user_id: Optional[str]) -> Dict[str, Any]:
        artifact = self.build_export_artifact(user_id, "markdown")
        packet_payload = self.export_complaint_packet(user_id)
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
        packet_payload = self.export_complaint_packet(user_id)
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

    def build_export_artifact(self, user_id: Optional[str], output_format: str = "json") -> Dict[str, Any]:
        payload = self.export_complaint_packet(user_id)
        packet = payload.get("packet") or {}
        artifacts = payload.get("artifacts") or {}
        normalized_format = str(output_format or "json").strip().lower()
        if normalized_format == "json":
            filename = ((artifacts.get("json") or {}).get("filename")) or "complaint-packet.json"
            body = json.dumps(packet, indent=2, sort_keys=True).encode("utf-8")
            return {"filename": filename, "media_type": "application/json", "body": body}
        if normalized_format in {"markdown", "md"}:
            artifact = artifacts.get("markdown") or {}
            content = artifact.get("content") or self._build_packet_markdown(packet)
            return {
                "filename": artifact.get("filename") or "complaint-packet.md",
                "media_type": "text/markdown",
                "body": str(content).encode("utf-8"),
            }
        if normalized_format == "pdf":
            artifact = artifacts.get("markdown") or {}
            markdown_text = artifact.get("content") or self._build_packet_markdown(packet)
            pdf_bytes = self._build_packet_pdf_bytes(packet, str(markdown_text))
            return {
                "filename": ((artifacts.get("pdf") or {}).get("filename")) or "complaint-packet.pdf",
                "media_type": "application/pdf",
                "body": pdf_bytes,
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
                {"name": "complaint.review_case", "description": "Return the current support matrix and evidence review."},
                {"name": "complaint.build_mediator_prompt", "description": "Build a testimony-ready chat mediator prompt from the shared case synopsis and support gaps."},
                {"name": "complaint.get_complaint_readiness", "description": "Estimate whether the current complaint record is ready for drafting, still building, or already in draft refinement."},
                {"name": "complaint.get_ui_readiness", "description": "Return the latest cached actor/critic UI readiness verdict for this complaint session."},
                {"name": "complaint.get_workflow_capabilities", "description": "Summarize which complaint-workflow abilities are currently available for the session."},
                {"name": "complaint.generate_complaint", "description": "Generate a complaint draft from intake and evidence."},
                {"name": "complaint.update_draft", "description": "Persist edits to the generated complaint draft."},
                {"name": "complaint.export_complaint_packet", "description": "Export the current lawsuit complaint packet with intake, evidence, review, and draft content."},
                {"name": "complaint.export_complaint_markdown", "description": "Export the generated complaint as a downloadable Markdown artifact."},
                {"name": "complaint.export_complaint_pdf", "description": "Export the generated complaint as a downloadable PDF artifact."},
                {"name": "complaint.analyze_complaint_output", "description": "Analyze the generated complaint output and turn filing-shape gaps into concrete UI/UX suggestions."},
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
        if tool_name == "complaint.get_workflow_capabilities":
            return self.get_workflow_capabilities(args.get("user_id"))
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
        if tool_name == "complaint.export_complaint_pdf":
            return self.export_complaint_pdf(args.get("user_id"))
        if tool_name == "complaint.analyze_complaint_output":
            return self.analyze_complaint_output(args.get("user_id"))
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
