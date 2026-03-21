"""
Complainant Module

LLM-based complainant that generates complaints and responds to mediator questions.
"""

import logging
from typing import Dict, Any, List
from dataclasses import dataclass, field
import json
import re

logger = logging.getLogger(__name__)

_ACTOR_CRITIC_PHASE_FOCUS_ORDER: List[str] = [
    "graph_analysis",
    "document_generation",
    "intake_questioning",
]

_ACTOR_CRITIC_OBJECTIVE_PRIORITY: List[str] = [
    "exact_dates",
    "staff_names_titles",
    "causation_sequence",
    "response_dates",
    "hearing_request_timing",
    "evidence_identifiers",
    "adverse_action_specificity",
]

_CONFIRMATION_PLACEHOLDER_TERMS = (
    "needs confirmation",
    "need confirmation",
    "to be confirmed",
    "tbd",
    "unknown",
    "not sure",
    "unclear",
    "pending confirmation",
)

_EMPATHY_HEAVY_STATES = {"distressed", "upset", "angry", "anxious", "overwhelmed"}

_CHRONOLOGY_TERMS = (
    "when",
    "date",
    "timeline",
    "chronolog",
    "sequence",
    "step by step",
    "before",
    "after",
    "notice",
    "decision",
)
_DECISION_MAKER_TERMS = (
    "who",
    "decision-maker",
    "decision maker",
    "manager",
    "supervisor",
    "director",
    "officer",
    "specialist",
    "staff",
)
_ROLE_TITLE_TERMS = ("title", "role", "position", "job title", "department", "team")
_ADVERSE_ACTION_TERMS = (
    "adverse action",
    "retaliat",
    "termination",
    "denial",
    "disciplin",
    "evict",
    "reduced hours",
    "cut hours",
    "transfer",
    "suspension",
)
_DOCUMENT_ARTIFACT_TERMS = (
    "document id",
    "notice id",
    "case number",
    "tracking number",
    "email subject",
    "exhibit",
    "attachment",
    "letter",
    "message id",
    "ticket id",
)


def _unique_strings(values: List[Any]) -> List[str]:
    items: List[str] = []
    for value in values if isinstance(values, list) else []:
        normalized = str(value or "").strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _ordered_priority_subset(
    values: List[str],
    priority_order: List[str],
) -> List[str]:
    normalized_values = _unique_strings(values)
    ordered = [item for item in priority_order if item in normalized_values]
    ordered.extend(item for item in normalized_values if item not in ordered)
    return ordered


def _objective_to_phase(objective: str) -> str:
    normalized = str(objective or "").strip().lower()
    if normalized in {"evidence_identifiers"}:
        return "document_generation"
    if normalized in {
        "exact_dates",
        "staff_names_titles",
        "causation_sequence",
        "response_dates",
        "hearing_request_timing",
        "adverse_action_specificity",
    }:
        return "graph_analysis"
    return "intake_questioning"


def _contains_confirmation_placeholder(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(term in text for term in _CONFIRMATION_PLACEHOLDER_TERMS)


def _classify_confirmation_objective(path: str, value: Any) -> str:
    signal_text = f"{path} {value}".lower()
    if any(token in signal_text for token in ("date", "when", "timeline", "chronolog", "sequence", "before", "after", "timing")):
        return "exact_dates"
    if any(token in signal_text for token in ("decision-maker", "decision maker", "staff", "manager", "supervisor", "director", "role", "title", "who")):
        return "staff_names_titles"
    if any(token in signal_text for token in ("hearing", "appeal request", "grievance request")):
        return "hearing_request_timing"
    if any(token in signal_text for token in ("response", "notice", "reply", "decision date", "decision timing", "how long", "days later")):
        return "response_dates"
    if any(token in signal_text for token in ("protected activity", "retaliat", "adverse action", "because", "after")):
        return "causation_sequence"
    if any(token in signal_text for token in ("adverse action", "termination", "denial", "disciplin", "suspension", "evict", "what happened")):
        return "adverse_action_specificity"
    if any(token in signal_text for token in ("document", "letter", "email", "record", "id", "tracking")):
        return "evidence_identifiers"
    return ""


def _extract_confirmation_placeholders(payload: Any, *, base_path: str = "") -> List[Dict[str, str]]:
    placeholders: List[Dict[str, str]] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_str = str(key).strip()
                next_path = f"{path}.{key_str}" if path else key_str
                walk(nested, next_path)
            return
        if isinstance(value, list):
            for idx, nested in enumerate(value):
                next_path = f"{path}[{idx}]" if path else f"[{idx}]"
                walk(nested, next_path)
            return
        text = str(value or "").strip()
        if not text or not _contains_confirmation_placeholder(text):
            return
        objective = _classify_confirmation_objective(path, text)
        placeholders.append(
            {
                "path": path or "unscoped",
                "value": text,
                "objective": objective,
                "phase": _objective_to_phase(objective),
            }
        )

    walk(payload, base_path)

    deduped: List[Dict[str, str]] = []
    seen = set()
    for item in placeholders:
        key = (item.get("path", ""), item.get("value", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _order_objectives_for_actor_critic(
    objectives: List[str],
    phase_focus_order: List[str] | None = None,
) -> List[str]:
    ordered_unique = _unique_strings(objectives)
    focus_order = _ordered_workflow_phases(
        phase_focus_order or _ACTOR_CRITIC_PHASE_FOCUS_ORDER,
        explicit_phase_order=_ACTOR_CRITIC_PHASE_FOCUS_ORDER,
    )
    phase_rank = {phase: idx for idx, phase in enumerate(focus_order)}
    objective_rank = {objective: idx for idx, objective in enumerate(_ACTOR_CRITIC_OBJECTIVE_PRIORITY)}
    ordered_unique.sort(
        key=lambda objective: (
            phase_rank.get(_objective_to_phase(objective), len(phase_rank)),
            objective_rank.get(objective, len(objective_rank)),
            objective,
        )
    )
    return ordered_unique


def _objective_follow_up_prompt(objective: str) -> str:
    normalized = str(objective or "").strip().lower()
    if normalized == "exact_dates":
        return "Can you walk me through the event dates in order, even if some are estimates?"
    if normalized == "staff_names_titles":
        return "Who made each decision, and what were their titles or roles?"
    if normalized == "hearing_request_timing":
        return "When and how did you request the hearing or appeal?"
    if normalized == "response_dates":
        return "When did you receive each response, notice, or decision?"
    if normalized == "causation_sequence":
        return "What happened before and after your protected activity that suggests retaliation?"
    if normalized == "evidence_identifiers":
        return "Which specific records, notices, or message identifiers support this point?"
    if normalized == "adverse_action_specificity":
        return "What exact adverse action was taken, by whom, and when?"
    return ""


def _ordered_workflow_phases(
    phases: List[str],
    explicit_phase_order: List[str] | None = None,
) -> List[str]:
    recognized = list(_ACTOR_CRITIC_PHASE_FOCUS_ORDER)
    normalized_phases = _unique_strings(phases)
    explicit_order = [
        item for item in _unique_strings(explicit_phase_order or [])
        if item in recognized
    ]
    if explicit_order:
        ordered = [item for item in explicit_order if item in normalized_phases]
        ordered.extend(
            item for item in recognized
            if item in normalized_phases and item not in ordered
        )
    else:
        ordered = [item for item in recognized if item in normalized_phases]
    ordered.extend(item for item in normalized_phases if item not in ordered)
    return ordered


def _derive_context_signals(
    seed: Dict[str, Any],
    key_facts: Dict[str, Any],
    evidence_items: List[Dict[str, Any]],
    synthetic_prompts: Dict[str, Any],
    story_facts: List[str],
) -> Dict[str, List[str]]:
    combined_text_parts: List[str] = [
        seed.get("type") or "",
        seed.get("summary") or "",
        key_facts.get("incident_summary") or "",
        key_facts.get("evidence_summary") or "",
        synthetic_prompts.get("complaint_chatbot_prompt") or "",
        synthetic_prompts.get("intake_questionnaire_prompt") or "",
    ]
    combined_text_parts.extend(str(item or "") for item in list(synthetic_prompts.get("intake_questions") or []))
    combined_text_parts.extend(str(item or "") for item in list(story_facts or []))
    for item in evidence_items if isinstance(evidence_items, list) else []:
        if not isinstance(item, dict):
            continue
        combined_text_parts.append(str(item.get("title") or ""))
        combined_text_parts.append(str(item.get("snippet") or ""))
    combined_text = " ".join(part.strip() for part in combined_text_parts if str(part or "").strip())
    lower_text = combined_text.lower()

    blocker_objectives = _unique_strings(
        list(key_facts.get("blocker_objectives") or [])
        + list(synthetic_prompts.get("blocker_objectives") or [])
    )
    extraction_targets = _unique_strings(
        list(key_facts.get("extraction_targets") or [])
        + list(synthetic_prompts.get("extraction_targets") or [])
    )
    explicit_phase_priorities = _unique_strings(
        list(key_facts.get("workflow_phase_priorities") or [])
        + list(synthetic_prompts.get("workflow_phase_priorities") or [])
    )
    workflow_phase_priorities = list(explicit_phase_priorities)

    timeline_terms = _CHRONOLOGY_TERMS + ("termination", "critical chronology", "event order")
    hearing_terms = ("hearing", "appeal", "grievance", "review")
    response_terms = ("response", "responded", "replied", "reply", "denied", "approved", "ignored", "no response", "days later")
    actor_terms = _DECISION_MAKER_TERMS
    title_terms = _ROLE_TITLE_TERMS
    retaliation_terms = ("protected activity", "complain", "reported", "grievance", "accommodation", "appeal")
    adverse_terms = _ADVERSE_ACTION_TERMS + ("fired",)
    adverse_specificity_terms = (
        "adverse action",
        "what happened",
        "exact action",
        "specific action",
        "discipline",
        "denied",
        "termination",
        "what did they do",
        "what exactly",
    )
    document_identifier_terms = _DOCUMENT_ARTIFACT_TERMS

    if any(term in lower_text for term in timeline_terms) or re.search(r"\b(?:19|20)\d{2}\b", lower_text):
        blocker_objectives.append("exact_dates")
        extraction_targets.append("timeline_anchors")
    if any(term in lower_text for term in hearing_terms):
        blocker_objectives.append("hearing_request_timing")
        extraction_targets.extend(["timeline_anchors", "hearing_process"])
    if any(term in lower_text for term in response_terms):
        blocker_objectives.append("response_dates")
        extraction_targets.extend(["timeline_anchors", "response_timeline"])
    if any(term in lower_text for term in ("critical chronology", "chronology gap", "follow up", "follow-up")):
        blocker_objectives.extend(["exact_dates", "response_dates"])
        extraction_targets.extend(["timeline_anchors", "response_timeline"])
    has_named_staff = bool(re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b", combined_text))
    if has_named_staff or any(term in lower_text for term in actor_terms):
        blocker_objectives.append("staff_names_titles")
        extraction_targets.append("actor_role_mapping")
    if any(term in lower_text for term in title_terms) and "staff_names_titles" not in blocker_objectives:
        blocker_objectives.append("staff_names_titles")
        extraction_targets.append("actor_role_mapping")
    if any(term in lower_text for term in retaliation_terms) and any(term in lower_text for term in adverse_terms):
        blocker_objectives.append("causation_sequence")
        extraction_targets.extend(["retaliation_sequence", "timeline_anchors", "actor_role_mapping"])
    if any(term in lower_text for term in adverse_specificity_terms):
        blocker_objectives.append("adverse_action_specificity")
        extraction_targets.extend(["adverse_action_definition", "timeline_anchors", "actor_role_mapping"])
    if any(term in lower_text for term in document_identifier_terms):
        blocker_objectives.append("evidence_identifiers")
        extraction_targets.append("document_identifier_mapping")
    if any(term in lower_text for term in ("documentary artifact", "document artifact", "adverse action detail", "decision-maker")):
        blocker_objectives.extend(["staff_names_titles", "adverse_action_specificity", "evidence_identifiers"])
        extraction_targets.extend(["actor_role_mapping", "adverse_action_definition", "document_identifier_mapping"])

    if blocker_objectives:
        workflow_phase_priorities.extend(["graph_analysis", "document_generation", "intake_questioning"])
    if evidence_items or any(token in lower_text for token in ("document", "email", "text", "notice", "letter", "policy", "photo")):
        workflow_phase_priorities.append("document_generation")

    ordered_blocker_objectives = _ordered_priority_subset(
        blocker_objectives,
        [
            "exact_dates",
            "staff_names_titles",
            "adverse_action_specificity",
            "hearing_request_timing",
            "response_dates",
            "causation_sequence",
            "evidence_identifiers",
        ],
    )
    ordered_extraction_targets = _ordered_priority_subset(
        extraction_targets,
        [
            "timeline_anchors",
            "actor_role_mapping",
            "hearing_process",
            "response_timeline",
            "retaliation_sequence",
            "adverse_action_definition",
            "document_identifier_mapping",
        ],
    )
    ordered_workflow_phases = _ordered_workflow_phases(
        workflow_phase_priorities,
        explicit_phase_order=explicit_phase_priorities,
    )
    return {
        "blocker_objectives": ordered_blocker_objectives,
        "extraction_targets": ordered_extraction_targets,
        "workflow_phase_priorities": ordered_workflow_phases,
    }


def _resolve_dynamic_hacc_evidence(question: str, context: "ComplaintContext") -> Dict[str, Any]:
    try:
        from .hacc_evidence import resolve_hacc_question_evidence
    except Exception as exc:
        logger.debug("Dynamic HACC evidence lookup unavailable: %s", exc)
        return {}

    key_facts = context.key_facts if isinstance(context.key_facts, dict) else {}
    if not key_facts.get("evidence_query") and not key_facts.get("anchor_terms") and not context.evidence_items:
        return {}
    return resolve_hacc_question_evidence(
        question=question,
        key_facts=key_facts,
        existing_evidence=context.evidence_items,
    )


def _normalize_personality(value: str) -> str:
    if not value:
        return "cooperative"
    return str(value).strip().lower().replace(" ", "_")


_PERSONALITY_PROFILES: Dict[str, Dict[str, Any]] = {
    # Keep legacy personalities stable.
    "cooperative": {
        "emotional_state": "distressed",
        "cooperation_level": 0.8,
        "context_depth": 2,
        "instructions": [
            "Be candid and answer directly.",
            "Volunteer relevant details even if not explicitly asked.",
        ],
    },
    "defensive": {
        "emotional_state": "guarded",
        "cooperation_level": 0.5,
        "context_depth": 1,
        "instructions": [
            "Be wary and somewhat resistant to sharing details.",
            "You may ask why a question matters before answering fully.",
        ],
    },
    "vague": {
        "emotional_state": "overwhelmed",
        "cooperation_level": 0.55,
        "context_depth": 1,
        "instructions": [
            "Answer in broad strokes and avoid specifics unless pressed.",
            "Use imprecise language when you don't remember exact details.",
        ],
    },
    "detailed": {
        "emotional_state": "focused",
        "cooperation_level": 0.85,
        "context_depth": 3,
        "instructions": [
            "Provide concrete details (dates, names, locations) when known.",
            "Organize your answer as a short narrative, not a legal filing.",
        ],
    },
    "emotional": {
        "emotional_state": "upset",
        "cooperation_level": 0.75,
        "context_depth": 2,
        "instructions": [
            "Express feelings strongly.",
            "You may include subjective impact and stress.",
        ],
    },
    # Additional personalities for broader adversarial coverage.
    "hostile": {
        "emotional_state": "angry",
        "cooperation_level": 0.3,
        "context_depth": 1,
        "instructions": [
            "Be irritated and reluctant to cooperate.",
            "Answer briefly; you may refuse to answer some questions.",
        ],
    },
    "confused": {
        "emotional_state": "confused",
        "cooperation_level": 0.6,
        "context_depth": 1,
        "instructions": [
            "Admit uncertainty when you are not sure.",
            "Ask for clarification if a question is complex.",
        ],
    },
    "anxious": {
        "emotional_state": "anxious",
        "cooperation_level": 0.65,
        "context_depth": 2,
        "instructions": [
            "Sound worried and hesitant.",
            "You may ramble slightly but still try to answer.",
        ],
    },
    "legalistic": {
        "emotional_state": "determined",
        "cooperation_level": 0.7,
        "context_depth": 2,
        "instructions": [
            "Use semi-formal language and reference rights/obligations in plain terms.",
            "Avoid making up statute names or citations.",
        ],
    },
}


@dataclass
class ComplaintContext:
    """Context information for a complaint."""
    complaint_type: str
    key_facts: Dict[str, Any]
    emotional_state: str = "distressed"
    cooperation_level: float = 0.8  # 0.0 to 1.0, how willing to provide info
    context_depth: int = 1  # How much detail complainant has
    evidence_items: List[Dict[str, Any]] = field(default_factory=list)
    evidence_summary: str = ""
    dynamic_evidence_items: List[Dict[str, Any]] = field(default_factory=list)
    dynamic_evidence_summary: str = ""
    dynamic_anchor_passages: List[Dict[str, Any]] = field(default_factory=list)
    dynamic_anchor_sections: List[str] = field(default_factory=list)
    repository_evidence_candidates: List[Dict[str, Any]] = field(default_factory=list)
    synthetic_prompts: Dict[str, Any] = field(default_factory=dict)
    complainant_story_facts: List[str] = field(default_factory=list)
    blocker_objectives: List[str] = field(default_factory=list)
    extraction_targets: List[str] = field(default_factory=list)
    workflow_phase_priorities: List[str] = field(default_factory=list)


class Complainant:
    """
    LLM-based complainant that generates and responds to questions.
    
    This class simulates a real complainant by:
    - Generating initial complaints from seed data
    - Responding to mediator questions based on context
    - Simulating various emotional states and cooperation levels
    """
    
    def __init__(self, llm_backend, personality: str = "cooperative"):
        """
        Initialize complainant with LLM backend.
        
        Args:
            llm_backend: LLM backend for generating responses
            personality: Type of complainant (cooperative, defensive, vague, etc.)
        """
        self.llm_backend = llm_backend
        self.personality = _normalize_personality(personality)
        self.personality_profile = _PERSONALITY_PROFILES.get(self.personality) or _PERSONALITY_PROFILES["cooperative"]
        self.context = None
        self.conversation_history = []

    @staticmethod
    def build_default_context(seed: Dict[str, Any], personality: str) -> ComplaintContext:
        p = _normalize_personality(personality)
        profile = _PERSONALITY_PROFILES.get(p) or _PERSONALITY_PROFILES["cooperative"]
        seed_payload = dict(seed) if isinstance(seed, dict) else {}

        raw_key_facts = seed_payload.get("key_facts")
        key_facts = dict(raw_key_facts) if isinstance(raw_key_facts, dict) else {}

        def _as_string_list(value: Any) -> List[str]:
            if isinstance(value, str):
                return [value.strip()] if value.strip() else []
            return [str(item).strip() for item in list(value or []) if str(item).strip()]

        raw_seed_evidence = seed_payload.get("hacc_evidence")
        raw_key_evidence = key_facts.get("hacc_evidence")
        evidence_items: List[Dict[str, Any]] = []
        for item in list(raw_seed_evidence or raw_key_evidence or []):
            if isinstance(item, dict):
                evidence_items.append(dict(item))

        raw_prompts = key_facts.get("synthetic_prompts")
        if not isinstance(raw_prompts, dict):
            raw_prompts = seed_payload.get("synthetic_prompts")
        synthetic_prompts: Dict[str, Any] = dict(raw_prompts) if isinstance(raw_prompts, dict) else {}

        raw_story_facts = key_facts.get("complainant_story_facts")
        if isinstance(raw_story_facts, str):
            story_facts = [raw_story_facts]
        else:
            story_facts = [str(item).strip() for item in list(raw_story_facts or []) if str(item).strip()]

        # Pull actor-critic optimization hints directly into complainant context so the
        # intake phase can push stronger factual, evidentiary, and anchor coverage.
        optimizer_containers = [
            seed_payload,
            seed_payload.get("_meta") if isinstance(seed_payload.get("_meta"), dict) else None,
            seed_payload.get("actor_critic_optimizer") if isinstance(seed_payload.get("actor_critic_optimizer"), dict) else None,
            seed_payload.get("optimization_guidance") if isinstance(seed_payload.get("optimization_guidance"), dict) else None,
            seed_payload.get("document_optimization") if isinstance(seed_payload.get("document_optimization"), dict) else None,
            key_facts,
            key_facts.get("actor_critic_optimizer") if isinstance(key_facts.get("actor_critic_optimizer"), dict) else None,
        ]
        weak_complaint_types = set()
        weak_evidence_modalities = set()
        unresolved_intake_objectives = set()
        question_quality_signal = None
        empathy_signal = None
        efficiency_signal = None
        num_sessions_signal = None
        successful_sessions_signal = None
        no_successful_sessions_hint = False

        for payload in optimizer_containers:
            if not isinstance(payload, dict):
                continue
            for key in ("weak_complaint_types", "complaint_type_targets", "generalization_targets"):
                for value in _as_string_list(payload.get(key)):
                    weak_complaint_types.add(value.lower())
            for key in ("weak_evidence_modalities", "evidence_modality_targets"):
                for value in _as_string_list(payload.get(key)):
                    weak_evidence_modalities.add(value.lower())
            for key in (
                "unresolved_intake_objectives",
                "weakest_unresolved_intake_objectives",
                "intake_objective_gaps",
                "priority_unresolved_intake_objectives",
            ):
                for value in _as_string_list(payload.get(key)):
                    unresolved_intake_objectives.add(value.lower())
            for key in ("question_quality_avg", "question_quality"):
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    question_quality_signal = float(value)
            for key in ("empathy_avg", "empathy"):
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    empathy_signal = float(value)
            for key in ("efficiency_avg", "efficiency"):
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    efficiency_signal = float(value)
            for key in ("num_sessions_analyzed", "sessions_analyzed", "num_runs_analyzed"):
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    num_sessions_signal = int(value)
            for key in ("num_successful_sessions", "successful_sessions", "successful_runs"):
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    successful_sessions_signal = int(value)
            if str(payload.get("summary") or "").strip().lower().find("no successful sessions") >= 0:
                no_successful_sessions_hint = True
            if str(payload.get("message") or "").strip().lower().find("no successful sessions") >= 0:
                no_successful_sessions_hint = True
            phase_signals = payload.get("phase_signal_context")
            if isinstance(phase_signals, dict):
                for key in ("question_quality_avg", "question_quality"):
                    value = phase_signals.get(key)
                    if isinstance(value, (int, float)):
                        question_quality_signal = float(value)
                for key in ("empathy_avg", "empathy"):
                    value = phase_signals.get(key)
                    if isinstance(value, (int, float)):
                        empathy_signal = float(value)
                for key in ("efficiency_avg", "efficiency"):
                    value = phase_signals.get(key)
                    if isinstance(value, (int, float)):
                        efficiency_signal = float(value)
                if bool(phase_signals.get("no_successful_sessions")):
                    no_successful_sessions_hint = True
                for key in (
                    "unresolved_intake_objectives",
                    "weakest_unresolved_intake_objectives",
                    "intake_objective_gaps",
                ):
                    for value in _as_string_list(phase_signals.get(key)):
                        unresolved_intake_objectives.add(value.lower())
                for key in ("num_sessions_analyzed", "sessions_analyzed"):
                    value = phase_signals.get(key)
                    if isinstance(value, (int, float)):
                        num_sessions_signal = int(value)
                for key in ("num_successful_sessions", "successful_sessions"):
                    value = phase_signals.get(key)
                    if isinstance(value, (int, float)):
                        successful_sessions_signal = int(value)

        signal_values = [question_quality_signal, empathy_signal, efficiency_signal]
        has_intake_signals = any(isinstance(value, float) for value in signal_values)
        all_intake_signals_zero = (
            all(isinstance(value, float) for value in signal_values)
            and all(float(value) <= 0.01 for value in signal_values)
        )
        no_successful_sessions = bool(
            no_successful_sessions_hint
            or num_sessions_signal == 0
            or successful_sessions_signal == 0
        )
        stability_recovery_mode = no_successful_sessions or all_intake_signals_zero

        complaint_type = str(seed_payload.get("type") or key_facts.get("complaint_type") or "").strip().lower()
        source = str(
            seed_payload.get("source")
            or (seed_payload.get("_meta") or {}).get("seed_source")
            or key_facts.get("source")
            or ""
        ).strip().lower()
        if complaint_type:
            weak_complaint_types.add(complaint_type)
        if source:
            weak_complaint_types.add(source)

        for evidence in evidence_items:
            if not isinstance(evidence, dict):
                continue
            source_path = str(
                evidence.get("source_path")
                or evidence.get("path")
                or evidence.get("file_path")
                or ""
            ).strip().lower()
            title = str(evidence.get("title") or evidence.get("document_id") or "").strip().lower()
            snippet = str(evidence.get("snippet") or "").strip().lower()
            joined = f"{title} {snippet} {source_path}".strip()
            if "policy" in joined or "administrative plan" in joined or "acop" in joined:
                weak_evidence_modalities.add("policy_document")
            if source_path:
                weak_evidence_modalities.add("file_evidence")
        modality_signal_text = " ".join(
            part
            for part in [
                str(seed_payload.get("summary") or ""),
                str(key_facts.get("incident_summary") or ""),
                str(key_facts.get("evidence_summary") or ""),
                str(synthetic_prompts.get("intake_questionnaire_prompt") or ""),
                " ".join(_as_string_list(synthetic_prompts.get("intake_questions"))),
                " ".join(story_facts),
            ]
            if str(part).strip()
        ).lower()
        if any(token in modality_signal_text for token in ("policy", "procedure", "administrative plan", "acop")):
            weak_evidence_modalities.add("policy_document")
        if any(token in modality_signal_text for token in ("file", "upload", "attachment", "screenshot", "pdf", "docx")):
            weak_evidence_modalities.add("file_evidence")

        is_housing_discrimination = "housing_discrimination" in weak_complaint_types
        is_hacc_research_seed = "hacc_research_engine" in weak_complaint_types
        weak_policy_or_file_evidence = bool(
            weak_evidence_modalities.intersection({"policy_document", "file_evidence"})
        )
        should_frontload_anchor_grievance_hearing = bool(
            is_housing_discrimination
            or is_hacc_research_seed
            or "anchor_grievance_hearing" in unresolved_intake_objectives
        )
        should_frontload_anchor_selection = bool(
            weak_policy_or_file_evidence
            or "anchor_selection_criteria" in unresolved_intake_objectives
        )
        selection_anchor_probe = (
            "For the unresolved selection-criteria basis, what exact screening factor or threshold was used, "
            "where is it written (policy title and section), and what is the strongest file/notice anchor "
            "(filename or notice ID, date, and sender) showing how staff applied it to your case?"
        )
        needs_intake_boost = (
            is_housing_discrimination
            or is_hacc_research_seed
            or weak_policy_or_file_evidence
            or (isinstance(question_quality_signal, float) and question_quality_signal < 0.86)
            or stability_recovery_mode
        )
        empathy_recovery_mode = isinstance(empathy_signal, float) and empathy_signal < 0.8

        # Normalize frequently-consumed list fields so prompt assembly and scoring logic
        # don't degrade on malformed optimizer payloads.
        key_facts["blocker_objectives"] = _unique_strings(_as_string_list(key_facts.get("blocker_objectives")))
        key_facts["extraction_targets"] = _unique_strings(_as_string_list(key_facts.get("extraction_targets")))
        key_facts["workflow_phase_priorities"] = _unique_strings(_as_string_list(key_facts.get("workflow_phase_priorities")))
        key_facts["unresolved_intake_objectives"] = _unique_strings(
            _as_string_list(key_facts.get("unresolved_intake_objectives"))
            + list(unresolved_intake_objectives)
        )
        key_facts["complainant_story_facts"] = list(story_facts)
        key_facts["hacc_evidence"] = list(evidence_items)
        has_seed_intake_prompts = bool(
            _as_string_list(synthetic_prompts.get("intake_questions"))
            or str(synthetic_prompts.get("intake_questionnaire_prompt") or "").strip()
        )
        if stability_recovery_mode or (not has_intake_signals and not has_seed_intake_prompts):
            key_facts["actor_critic_session_stability"] = {
                "mode": "recovery",
                "reason": (
                    "no_successful_sessions"
                    if no_successful_sessions
                    else "missing_intake_signals"
                ),
                "num_sessions_analyzed": num_sessions_signal,
                "num_successful_sessions": successful_sessions_signal,
                "question_quality": question_quality_signal,
                "empathy": empathy_signal,
                "efficiency": efficiency_signal,
            }
            stability_prompt = (
                "Use a stable intake flow: acknowledge impact briefly, gather chronology and decision-maker facts, "
                "capture document anchors, then confirm requested remedy."
            )
            existing_intake_prompt = str(synthetic_prompts.get("intake_questionnaire_prompt") or "").strip()
            if not existing_intake_prompt:
                synthetic_prompts["intake_questionnaire_prompt"] = stability_prompt
            elif stability_prompt.lower() not in existing_intake_prompt.lower():
                synthetic_prompts["intake_questionnaire_prompt"] = f"{existing_intake_prompt} {stability_prompt}".strip()
            existing_questions = _as_string_list(synthetic_prompts.get("intake_questions"))
            stability_questions = [
                "Before we get into details, what impact has this had on your housing, finances, health, or family?",
                "What happened first, what happened next, and what happened most recently? Include date anchors even if approximate.",
                "Who made or communicated each decision, and what were their roles?",
                "What exact adverse action happened, what reason was given, and when did you learn about it?",
                "What notices, emails, texts, letters, or other files support your account, and what does each one show?",
                "What remedy are you asking for right now?",
            ]
            anchor_fallbacks: List[str] = []
            if should_frontload_anchor_selection:
                anchor_fallbacks.append(selection_anchor_probe)
            if should_frontload_anchor_grievance_hearing:
                anchor_fallbacks.append(
                    "For the unresolved grievance-hearing gap, what date did you request a hearing/review, how did you submit it (portal/email/form/phone/in person), when did HACC respond, and which request record plus response notice date is your strongest evidence anchor?"
                )
            synthetic_prompts["intake_questions"] = _unique_strings(existing_questions + stability_questions)[:8]
            if anchor_fallbacks:
                synthetic_prompts["intake_questions"] = _unique_strings(
                    anchor_fallbacks + list(synthetic_prompts.get("intake_questions") or [])
                )[:10]
            key_facts["workflow_phase_priorities"] = _ordered_workflow_phases(
                list(key_facts.get("workflow_phase_priorities") or [])
                + ["intake_questioning", "graph_analysis", "document_generation"],
                explicit_phase_order=["intake_questioning", "graph_analysis", "document_generation"],
            )
        if needs_intake_boost:
            key_facts["actor_critic_intake_focus"] = {
                "weak_complaint_types": sorted(weak_complaint_types),
                "weak_evidence_modalities": sorted(weak_evidence_modalities),
                "question_quality": question_quality_signal,
                "empathy": empathy_signal,
                "efficiency": efficiency_signal,
                "priority": "intake_questioning",
            }
            anchor_sections: List[str] = [
                "adverse_action",
                "selection_criteria",
            ]
            if should_frontload_anchor_grievance_hearing:
                anchor_sections.extend(
                    [
                        "grievance_hearing",
                        "appeal_rights",
                        "reasonable_accommodation",
                    ]
                )
            key_facts["anchor_sections"] = _unique_strings(
                list(key_facts.get("anchor_sections") or []) + anchor_sections
            )
            boosted_objectives = [
                "exact_dates",
                "staff_names_titles",
                "causation_sequence",
                "response_dates",
                "adverse_action_specificity",
                "adverse_action_details",
                "evidence_identifiers",
            ]
            if is_housing_discrimination or is_hacc_research_seed:
                boosted_objectives.insert(3, "hearing_request_timing")
            key_facts["blocker_objectives"] = _ordered_priority_subset(
                list(key_facts.get("blocker_objectives") or []) + boosted_objectives,
                _ACTOR_CRITIC_OBJECTIVE_PRIORITY,
            )
            key_facts["extraction_targets"] = _ordered_priority_subset(
                list(key_facts.get("extraction_targets") or [])
                + [
                    "timeline_anchors",
                    "actor_role_mapping",
                    "hearing_process",
                    "response_timeline",
                    "retaliation_sequence",
                    "adverse_action_details",
                    "adverse_action_definition",
                    "document_identifier_mapping",
                ],
                [
                    "timeline_anchors",
                    "actor_role_mapping",
                    "hearing_process",
                    "response_timeline",
                    "retaliation_sequence",
                    "adverse_action_definition",
                    "document_identifier_mapping",
                ],
            )
            key_facts["workflow_phase_priorities"] = _ordered_workflow_phases(
                list(key_facts.get("workflow_phase_priorities") or [])
                + ["intake_questioning", "graph_analysis", "document_generation"],
                explicit_phase_order=["intake_questioning", "graph_analysis", "document_generation"],
            )

            existing_intake_questions = _as_string_list(synthetic_prompts.get("intake_questions"))
            anchor_specific_fallbacks: List[str] = []
            if should_frontload_anchor_selection:
                anchor_specific_fallbacks.append(selection_anchor_probe)
            if should_frontload_anchor_grievance_hearing:
                anchor_specific_fallbacks.append(
                    "For the unresolved grievance-hearing process, what rights were explained to you, what exact date did you request a hearing/review, how did you submit it, when did HACC respond, and what request record plus response notice date are your strongest evidence anchors?"
                )
            targeted_questions = [
                "For the unresolved chronology gap, walk through each event in order with the strongest available date anchor (exact date, or month/year if approximate).",
                "For the unresolved decision-maker gap, identify who made or communicated each decision, each person's role/title, and the strongest notice/email anchor naming them.",
                "For the unresolved adverse-action gap, state the exact action, the first date you learned it, the stated reason, and the strongest supporting notice or communication anchor.",
                "For the unresolved policy-application gap, name the specific policy/procedure section cited and the strongest document anchor showing how it was applied.",
                "For the unresolved documentary-evidence gap, list each supporting file (notice/email/text/letter/upload) with date, sender/source, filename or ID, and the fact it proves.",
                "For the unresolved hearing-timing gap, when did you request a grievance/hearing/appeal, how did you request it, when did HACC respond, and what record anchors each date?",
                "For the unresolved causation gap, sequence protected activity -> staff awareness -> adverse action, and cite the strongest dated record for each step.",
            ]
            catch_all_questions = [
                "What harm did this cause and what remedy are you asking for right now?",
            ]
            if empathy_recovery_mode:
                targeted_questions.insert(
                    0,
                    "Before details, what impact has this had on your housing stability, finances, health, or family?",
                )
            synthetic_prompts["intake_questions"] = _unique_strings(
                anchor_specific_fallbacks + targeted_questions + existing_intake_questions + catch_all_questions
            )[:14]

            intake_prompt_seed = str(synthetic_prompts.get("intake_questionnaire_prompt") or "").strip()
            boost_clause = (
                "Ask one unresolved factual gap at a time, make each question specific to that gap, and require the strongest available "
                "evidence anchor in the same turn (policy title/section, notice/email/text metadata, or file artifact with filename/ID and date). "
                "Resolve anchor-selection criteria evidence before generic catch-all prompts."
            )
            if not intake_prompt_seed:
                synthetic_prompts["intake_questionnaire_prompt"] = boost_clause
            elif boost_clause.lower() not in intake_prompt_seed.lower():
                synthetic_prompts["intake_questionnaire_prompt"] = f"{intake_prompt_seed} {boost_clause}".strip()

            chatbot_prompt_seed = str(synthetic_prompts.get("complaint_chatbot_prompt") or "").strip()
            chatbot_clause = (
                "Keep responses concise but fact-dense: who, action, date, policy/file artifact, and requested remedy."
            )
            if not chatbot_prompt_seed:
                synthetic_prompts["complaint_chatbot_prompt"] = chatbot_clause
            elif chatbot_clause.lower() not in chatbot_prompt_seed.lower():
                synthetic_prompts["complaint_chatbot_prompt"] = f"{chatbot_prompt_seed} {chatbot_clause}".strip()

        derived_signals = _derive_context_signals(
            seed_payload,
            key_facts,
            evidence_items,
            synthetic_prompts,
            story_facts,
        )

        blocker_objectives = list(derived_signals.get("blocker_objectives") or [])
        extraction_targets = list(derived_signals.get("extraction_targets") or [])
        workflow_phase_priorities = list(derived_signals.get("workflow_phase_priorities") or [])

        if blocker_objectives:
            key_facts["blocker_objectives"] = _ordered_priority_subset(
                list(key_facts.get("blocker_objectives") or []) + blocker_objectives,
                _ACTOR_CRITIC_OBJECTIVE_PRIORITY,
            )
        if extraction_targets:
            key_facts["extraction_targets"] = _unique_strings(
                list(key_facts.get("extraction_targets") or []) + extraction_targets
            )
        if workflow_phase_priorities:
            key_facts["workflow_phase_priorities"] = _ordered_workflow_phases(
                list(key_facts.get("workflow_phase_priorities") or []) + workflow_phase_priorities,
                explicit_phase_order=_ACTOR_CRITIC_PHASE_FOCUS_ORDER,
            )

        # If optimizer signals produced blocker objectives but no intake prompt artifacts,
        # synthesize lightweight follow-up guidance to keep intake flow actionable.
        intake_prompt_text = str(synthetic_prompts.get("intake_questionnaire_prompt") or "").strip()
        raw_intake_questions = synthetic_prompts.get("intake_questions")
        if isinstance(raw_intake_questions, str):
            intake_questions = [raw_intake_questions.strip()] if raw_intake_questions.strip() else []
        else:
            intake_questions = [
                str(item).strip()
                for item in list(raw_intake_questions or [])
                if str(item).strip()
            ]
        if blocker_objectives and not intake_prompt_text:
            synthetic_prompts["intake_questionnaire_prompt"] = (
                "Prioritize one unresolved factual gap per question, and request the strongest available evidence anchor for that same gap before drafting."
            )
        if blocker_objectives and not intake_questions:
            synthesized_anchor_fallbacks: List[str] = []
            if should_frontload_anchor_selection:
                synthesized_anchor_fallbacks.append(selection_anchor_probe)
            if should_frontload_anchor_grievance_hearing:
                synthesized_anchor_fallbacks.append(
                    "For the unresolved grievance-hearing process, what date did you request a hearing/review, how did you submit it, when did HACC respond, and what request record plus response notice date is your strongest evidence anchor?"
                )
            synthesized_questions = [
                prompt
                for prompt in (_objective_follow_up_prompt(objective) for objective in blocker_objectives)
                if prompt
            ]
            synthesized_questions = synthesized_anchor_fallbacks + synthesized_questions
            if synthesized_questions:
                synthetic_prompts["intake_questions"] = _unique_strings(synthesized_questions)[:8]

        evidence_summary = str(
            key_facts.get("evidence_summary")
            or seed_payload.get("summary")
            or ""
        )

        cooperation_level = float(profile.get("cooperation_level", 0.8))
        context_depth = int(profile.get("context_depth", 1))
        if stability_recovery_mode:
            # Keep adversarial personas realistic, but avoid dead-end responses when
            # recovering from zero-signal/no-session optimizer runs.
            cooperation_level = max(cooperation_level, 0.62)
            context_depth = max(context_depth, 2)
        cooperation_level = min(1.0, max(0.0, cooperation_level))
        context_depth = max(1, context_depth)

        return ComplaintContext(
            complaint_type=str(seed_payload.get("type", "unknown") or "unknown"),
            key_facts=key_facts,
            emotional_state=str(profile.get("emotional_state", "distressed")),
            cooperation_level=cooperation_level,
            context_depth=context_depth,
            evidence_items=evidence_items,
            evidence_summary=evidence_summary,
            repository_evidence_candidates=list(key_facts.get("repository_evidence_candidates") or []),
            synthetic_prompts=synthetic_prompts,
            complainant_story_facts=story_facts,
            blocker_objectives=blocker_objectives,
            extraction_targets=extraction_targets,
            workflow_phase_priorities=workflow_phase_priorities,
        )
    
    def set_context(self, context: ComplaintContext):
        """Set the complaint context for this session."""
        self.context = context
        self.conversation_history = []
    
    def generate_initial_complaint(self, seed_data: Dict[str, Any]) -> str:
        """
        Generate an initial complaint from seed data.
        
        Args:
            seed_data: Seed information for complaint generation
            
        Returns:
            Generated complaint text
        """
        prompt = self._build_complaint_prompt(seed_data)
        
        try:
            response = self.llm_backend(prompt)
            self.conversation_history.append({
                'role': 'complainant',
                'type': 'initial_complaint',
                'content': response
            })
            return response
        except Exception as e:
            logger.error(f"Error generating complaint: {e}")
            return self._fallback_complaint(seed_data)
    
    def respond_to_question(self, question: str) -> str:
        """
        Respond to a mediator's question based on context and personality.
        
        Args:
            question: Question from mediator
            
        Returns:
            Complainant's response
        """
        if not self.context:
            raise ValueError("Context must be set before responding to questions")

        self._refresh_dynamic_evidence(question)
        
        prompt = self._build_response_prompt(question)
        
        try:
            response = self.llm_backend(prompt)
            self.conversation_history.append({
                'role': 'mediator',
                'type': 'question',
                'content': question
            })
            self.conversation_history.append({
                'role': 'complainant',
                'type': 'response',
                'content': response,
                'evidence_context': self._serialize_dynamic_evidence_context(),
            })
            return response
        except Exception as e:
            logger.error(f"Error responding to question: {e}")
            return self._fallback_response(question)
    
    def _build_complaint_prompt(self, seed_data: Dict[str, Any]) -> str:
        """Build prompt for generating initial complaint."""
        instructions = "\n".join([f"- {x}" for x in (self.personality_profile.get("instructions") or [])])
        evidence_text = self._format_seed_evidence(seed_data)
        grounded_facts_text = self._format_grounded_case_digest(
            key_facts=seed_data.get("key_facts") if isinstance(seed_data.get("key_facts"), dict) else {},
            story_facts=((seed_data.get("key_facts") or {}).get("complainant_story_facts") if isinstance(seed_data.get("key_facts"), dict) else None),
            repository_candidates=((seed_data.get("key_facts") or {}).get("repository_evidence_candidates") if isinstance(seed_data.get("key_facts"), dict) else None),
            synthetic_prompts=((seed_data.get("key_facts") or {}).get("synthetic_prompts") if isinstance(seed_data.get("key_facts"), dict) else None),
            blocker_objectives=((seed_data.get("key_facts") or {}).get("blocker_objectives") if isinstance(seed_data.get("key_facts"), dict) else None),
            extraction_targets=((seed_data.get("key_facts") or {}).get("extraction_targets") if isinstance(seed_data.get("key_facts"), dict) else None),
            workflow_phase_priorities=((seed_data.get("key_facts") or {}).get("workflow_phase_priorities") if isinstance(seed_data.get("key_facts"), dict) else None),
        )
        prompt = f"""You are a person filing a complaint. Based on the following situation, write a detailed but natural complaint as if you were experiencing this issue.

Situation:
{json.dumps(seed_data, indent=2)}

Grounded complainant facts:
{grounded_facts_text}

Evidence grounding:
{evidence_text}

Personality: {self.personality}

Behavioral constraints:
{instructions}

Generate a complaint that:
1. Describes what happened in your own words
2. Expresses how this affected you
3. Mentions key facts but doesn't over-explain
4. Sounds like a real person telling their story
5. Prefer the grounded complainant facts and anchor passages over generic filler
6. When evidence is provided, use it as grounding without sounding like a brief
7. If a detail is not shown directly in the evidence, phrase it as your understanding or concern rather than as certain fact
8. If the grounded digest includes missing-facts intake questions, surface the most important unanswered facts naturally so the mediator knows what still needs to be asked

Complaint:"""
        return prompt
    
    def _build_response_prompt(self, question: str) -> str:
        """Build prompt for responding to mediator question."""
        # Include conversation history for context
        history_text = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in self.conversation_history[-5:]  # Last 5 messages
        ])
        
        cooperation_desc = "very cooperative" if self.context.cooperation_level > 0.7 else \
                          "somewhat cooperative" if self.context.cooperation_level > 0.4 else \
                          "defensive"

        instructions = "\n".join([f"- {x}" for x in (self.personality_profile.get("instructions") or [])])
        evidence_text = self._format_context_evidence()
        question_lower = str(question or "").lower()
        focus_guidance: List[str] = []
        if any(token in question_lower for token in _CHRONOLOGY_TERMS + ("decision timeline",)):
            focus_guidance.append(
                "Give the most specific date anchors you know (exact date, month/year, or relative anchors) and keep events in order."
            )
            focus_guidance.append(
                "If multiple people acted, describe the timeline actor-by-actor (who acted, what they did, and when)."
            )
        if any(token in question_lower for token in ("exact date", "specific date", "date anchor", "month/year")):
            focus_guidance.append(
                "Prefer exact dates. If you do not know an exact date, give your best month/year estimate and explain why it is approximate."
            )
        if (
            any(token in question_lower for token in _DECISION_MAKER_TERMS + ("name",))
            and any(token in question_lower for token in _ROLE_TITLE_TERMS)
        ):
            focus_guidance.append(
                "Name each person involved and include their title or role; if a name is unknown, give the best-known title."
            )
        if any(token in question_lower for token in ("hearing", "grievance", "appeal", "review")) and any(
            token in question_lower for token in ("when", "date", "timing", "requested", "deadline")
        ):
            focus_guidance.append(
                "State when you requested a hearing or appeal, how you requested it, and what happened next."
            )
        if any(token in question_lower for token in ("response", "respond", "notice", "decision", "outcome")) and any(
            token in question_lower for token in ("when", "date", "dated", "days later")
        ):
            focus_guidance.append(
                "Include response dates for notices, hearing/review requests, and final decision communications when known."
            )
        if any(token in question_lower for token in _ADVERSE_ACTION_TERMS):
            focus_guidance.append(
                "Specify the exact adverse action (what changed), who authorized it, and the first date you learned of it."
            )
        if any(token in question_lower for token in _DOCUMENT_ARTIFACT_TERMS):
            focus_guidance.append(
                "Identify documentary artifacts precisely: document type, date, sender/recipient, and any ID or subject line."
            )
        if (
            any(token in question_lower for token in ("protected activity", "complaint", "reported", "accommodation", "grievance", "appeal"))
            and any(token in question_lower for token in ("adverse", "retaliat", "termination", "denial", "disciplin"))
        ):
            focus_guidance.append(
                "State what protected activity you did, what adverse action followed, and the facts that make you think they are connected."
            )
            focus_guidance.append(
                "Include names/roles of decision-makers and any notice/message dates if known."
            )
        if (
            any(token in question_lower for token in ("protected activity", "complaint", "reported", "accommodation", "grievance", "appeal"))
            and any(token in question_lower for token in ("adverse", "retaliat", "termination", "denial", "disciplin"))
            and any(token in question_lower for token in ("before", "after", "sequence", "timeline", "step by step"))
        ):
            focus_guidance.append(
                "Answer in sequence: protected activity, who learned about it, adverse action, and what timing or statements link them."
            )
        focus_guidance_text = "\n".join([f"- {item}" for item in focus_guidance]) if focus_guidance else "- Answer naturally in your own words."
        response_schema_guidance_text = self._build_response_schema_guidance(question)
        actor_critic_guidance_text = self._build_actor_critic_guidance(question)
        grounded_facts_text = self._format_grounded_case_digest(
            key_facts=self.context.key_facts if isinstance(self.context.key_facts, dict) else {},
            story_facts=self.context.complainant_story_facts,
            repository_candidates=self.context.repository_evidence_candidates,
            synthetic_prompts=self.context.synthetic_prompts,
            blocker_objectives=self.context.blocker_objectives,
            extraction_targets=self.context.extraction_targets,
            workflow_phase_priorities=self.context.workflow_phase_priorities,
        )
        
        prompt = f"""You are a complainant in a legal matter. You are {cooperation_desc} and your personality is {self.personality}.

Your situation involves:
{json.dumps(self.context.key_facts, indent=2)}

Grounded complainant facts:
{grounded_facts_text}

Evidence you can draw from:
{evidence_text}

Recent conversation:
{history_text}

The mediator asks: "{question}"

Question focus guidance:
{focus_guidance_text}

Response packaging guidance:
{response_schema_guidance_text}

Actor-critic optimization guidance:
{actor_critic_guidance_text}

Respond naturally as this person would. Your response should:
1. Answer the question based on your knowledge
2. Match your personality ({self.personality}) and cooperation level ({cooperation_desc})
3. Be honest but not overly detailed unless asked
4. Sound like a real person, not a legal document
5. Use the evidence when it supports the answer, and say when something is only an inference
6. Prefer grounded complainant facts, anchor passages, and repository evidence when answering
7. If the grounded digest includes missing-facts intake questions and the mediator has not yet covered them, be clear about which important facts still need confirmation
8. If asked for key blockers, prioritize exact dates, staff names/titles, hearing-request timing, response dates, and protected-activity/adverse-action sequencing

Behavioral constraints:
{instructions}

If you don't know something, say so. If your cooperation level is low, it's okay to be brief or refuse minor details.

Response:"""
        return prompt

    def _build_response_schema_guidance(self, question: str) -> str:
        question_lower = str(question or "").lower()
        guidance: List[str] = [
            "Start with a direct answer sentence, then add short supporting facts.",
            "Prefer concrete facts over general impressions (dates, names/roles, actions, notices, documents).",
            "If a detail is uncertain, label it clearly as an estimate or memory gap.",
            "Do not repeat unrelated background; focus on the unresolved factual gap in the question.",
            "When multiple topics are requested, prioritize in this order: graph analysis facts first, then document artifacts, then intake blockers.",
            "Keep facts patchable by using compact fact slots: who, action, date, artifact.",
        ]
        if any(token in question_lower for token in _CHRONOLOGY_TERMS):
            guidance.append("Use chronological order and include one date anchor per event when possible.")
        if any(token in question_lower for token in _DECISION_MAKER_TERMS + ("name",)):
            guidance.append("List each person with their role/title and what they did.")
        if any(token in question_lower for token in ("document", "email", "notice", "message", "record", "paperwork")):
            guidance.append("Identify the strongest document first, then add one to two secondary records if relevant.")
        if any(token in question_lower for token in _DOCUMENT_ARTIFACT_TERMS):
            guidance.append("For each document, include one precision marker (ID, subject line, exhibit label, or send date).")
        if any(token in question_lower for token in _ADVERSE_ACTION_TERMS):
            guidance.append("Describe the adverse action with one concrete operational detail (status change, benefit loss, restriction, or penalty).")
        if (
            any(token in question_lower for token in ("protected activity", "complaint", "reported", "accommodation", "grievance", "appeal"))
            and any(token in question_lower for token in ("adverse", "retaliat", "termination", "denial", "disciplin"))
        ):
            guidance.append("Explicitly connect protected activity to adverse action using timing, statements, or decision-maker behavior.")
        if "?" in question and question.count("?") > 1:
            guidance.append("If the mediator asked multiple questions at once, answer in numbered order to keep facts patchable.")
        if len(question.split()) > 28:
            guidance.append("If the question is broad, answer the core fact first, then add one brief clarification request.")
        return "\n".join([f"- {item}" for item in guidance])

    def _build_actor_critic_guidance(self, question: str) -> str:
        question_text = str(question or "").strip()
        question_lower = question_text.lower()
        context = self.context or ComplaintContext(complaint_type="unknown", key_facts={})

        phase_focus = _ordered_workflow_phases(
            list(context.workflow_phase_priorities or _ACTOR_CRITIC_PHASE_FOCUS_ORDER),
            explicit_phase_order=_ACTOR_CRITIC_PHASE_FOCUS_ORDER,
        )

        placeholder_objectives = [
            str(item.get("objective") or "").strip()
            for item in _extract_confirmation_placeholders(context.key_facts)
            if isinstance(item, dict)
        ]
        unresolved_objectives = _order_objectives_for_actor_critic(
            list(context.blocker_objectives or []) + placeholder_objectives,
            phase_focus_order=phase_focus,
        )

        guidance: List[str] = []
        guidance.append("Keep your answer short, factual, and easy for the mediator to act on in the next question.")
        if str(context.emotional_state).lower() in _EMPATHY_HEAVY_STATES:
            guidance.append("Open with one brief impact/emotion sentence, then provide concrete facts.")
        if any(token in question_lower for token in ("how did that affect you", "impact", "harm", "stress", "feeling", "feel")):
            guidance.append("Name one concrete impact (housing/work/health/financial) and one emotional impact.")
        if any(token in question_lower for token in ("why", "explain", "tell me more", "what happened")) and len(question_text.split()) < 10:
            guidance.append("If the question is vague, provide the best direct answer and add one precise clarification need.")

        if unresolved_objectives:
            prioritized = unresolved_objectives[:3]
            guidance.append(
                "When facts remain unresolved, end with a short 'still needs confirmation' line for: "
                + ", ".join(prioritized)
                + "."
            )
            follow_up_prompts = [
                prompt
                for prompt in (_objective_follow_up_prompt(item) for item in prioritized)
                if prompt
            ]
            if follow_up_prompts:
                guidance.append("Suggested high-yield follow-up prompts: " + " | ".join(follow_up_prompts))
        else:
            guidance.append("If chronology or decision-maker precision still feels vague, ask one explicit follow-up prompt before ending.")

        if any(token in question_lower for token in _CHRONOLOGY_TERMS):
            guidance.append("Close chronology gaps by providing event sequence with dates and response timing, even if approximate.")
        if any(token in question_lower for token in _DECISION_MAKER_TERMS):
            guidance.append("Pin down each decision-maker and role; if uncertain, provide the best known role and source context.")
        if any(token in question_lower for token in _DOCUMENT_ARTIFACT_TERMS):
            guidance.append("Name documentary artifacts precisely (letter/email/notice), including IDs or subject lines when available.")

        guidance.append(
            "Phase focus order: "
            + " -> ".join(phase_focus[:3] if phase_focus else list(_ACTOR_CRITIC_PHASE_FOCUS_ORDER))
            + "."
        )
        return "\n".join(f"- {item}" for item in guidance)
    
    def _fallback_complaint(self, seed_data: Dict[str, Any]) -> str:
        """Fallback complaint if LLM fails."""
        return f"I need to file a complaint about {seed_data.get('type', 'an issue')}. {seed_data.get('summary', 'Something happened that I need help with.')}"
    
    def _fallback_response(self, question: str) -> str:
        """Fallback response if LLM fails."""
        return "I'm not sure how to answer that right now. Can you rephrase the question?"

    def _format_seed_evidence(self, seed_data: Dict[str, Any]) -> str:
        key_facts = seed_data.get("key_facts") if isinstance(seed_data.get("key_facts"), dict) else {}
        summary = str(key_facts.get("evidence_summary") or seed_data.get("summary") or "").strip()
        evidence_items = list(seed_data.get("hacc_evidence") or key_facts.get("hacc_evidence") or [])
        anchor_passages = list(key_facts.get("anchor_passages") or [])
        anchor_sections = list(key_facts.get("anchor_sections") or [])
        return self._format_evidence_block(summary, evidence_items, anchor_passages, anchor_sections)

    def _format_context_evidence(self) -> str:
        anchor_passages = []
        anchor_sections = []
        if isinstance(self.context.key_facts, dict):
            anchor_passages = list(self.context.key_facts.get("anchor_passages") or [])
            anchor_sections = list(self.context.key_facts.get("anchor_sections") or [])
        base_block = self._format_evidence_block(
            self.context.evidence_summary,
            self.context.evidence_items,
            anchor_passages,
            anchor_sections,
        )
        dynamic_block = self._format_evidence_block(
            self.context.dynamic_evidence_summary,
            self.context.dynamic_evidence_items,
            self.context.dynamic_anchor_passages,
            self.context.dynamic_anchor_sections,
        )
        if self.context.dynamic_evidence_items or self.context.dynamic_anchor_passages:
            return f"Seed evidence:\n{base_block}\n\nQuestion-focused HACC evidence:\n{dynamic_block}"
        return base_block

    def _format_evidence_block(
        self,
        summary: str,
        evidence_items: List[Dict[str, Any]],
        anchor_passages: List[Dict[str, Any]],
        anchor_sections: List[str],
    ) -> str:
        lines: List[str] = []
        if summary:
            lines.append(f"Summary: {summary}")
        if anchor_sections:
            lines.append(f"Decision-tree sections: {', '.join(anchor_sections)}")
        for index, passage in enumerate(anchor_passages[:3], start=1):
            title = str(passage.get("title") or f"anchor_{index}")
            snippet = str(passage.get("snippet") or "").strip()
            section_labels = ", ".join(list(passage.get("section_labels") or []))
            if snippet:
                if section_labels:
                    lines.append(f"Passage {index} [{section_labels}] from {title}: {snippet}")
                else:
                    lines.append(f"Passage {index} from {title}: {snippet}")
        for index, item in enumerate(evidence_items[:3], start=1):
            title = str(item.get("title") or item.get("document_id") or f"evidence_{index}")
            snippet = str(item.get("snippet") or "").strip()
            source_path = str(item.get("source_path") or "").strip()
            line = f"{index}. {title}"
            if snippet:
                line += f" - {snippet}"
            if source_path:
                line += f" (source: {source_path})"
            lines.append(line)
        return "\n".join(lines) if lines else "No external evidence was provided."

    def _format_grounded_case_digest(
        self,
        *,
        key_facts: Dict[str, Any],
        story_facts: List[str] | None,
        repository_candidates: List[Dict[str, Any]] | None,
        synthetic_prompts: Dict[str, Any] | None,
        blocker_objectives: List[str] | None = None,
        extraction_targets: List[str] | None = None,
        workflow_phase_priorities: List[str] | None = None,
    ) -> str:
        lines: List[str] = []
        incident_summary = str((key_facts or {}).get("incident_summary") or "").strip()
        if incident_summary:
            lines.append(f"Incident summary: {incident_summary}")

        priority_objectives = _unique_strings(
            list(blocker_objectives or []) + list((key_facts or {}).get("blocker_objectives") or [])
        )
        if priority_objectives:
            lines.append(f"Priority intake objectives: {', '.join(priority_objectives)}")

        derived_extraction_targets = _unique_strings(
            list(extraction_targets or []) + list((key_facts or {}).get("extraction_targets") or [])
        )
        if derived_extraction_targets:
            lines.append(f"Graph extraction targets: {', '.join(derived_extraction_targets)}")

        prioritized_workflow_phases = _unique_strings(
            list(workflow_phase_priorities or []) + list((key_facts or {}).get("workflow_phase_priorities") or [])
        )
        if prioritized_workflow_phases:
            lines.append(f"Priority workflow phases: {', '.join(prioritized_workflow_phases)}")

        for index, fact in enumerate(list(story_facts or [])[:5], start=1):
            cleaned = str(fact).strip()
            if cleaned:
                lines.append(f"Fact {index}: {cleaned}")

        for index, candidate in enumerate(list(repository_candidates or [])[:2], start=1):
            title = str(candidate.get("title") or candidate.get("relative_path") or f"candidate_{index}").strip()
            snippet = str(candidate.get("snippet") or "").strip()
            line = f"Repository evidence {index}: {title}"
            if snippet:
                line += f" - {snippet}"
            lines.append(line)

        synthetic_prompt_text = str((synthetic_prompts or {}).get("complaint_chatbot_prompt") or "").strip()
        if synthetic_prompt_text:
            lines.append(f"Prompt guidance: {synthetic_prompt_text}")
        intake_prompt_text = str((synthetic_prompts or {}).get("intake_questionnaire_prompt") or "").strip()
        if intake_prompt_text:
            lines.append(f"Intake questionnaire: {intake_prompt_text}")
        intake_questions = [str(item).strip() for item in list((synthetic_prompts or {}).get("intake_questions") or []) if str(item).strip()]
        for index, question in enumerate(intake_questions[:6], start=1):
            lines.append(f"Missing fact question {index}: {question}")

        return "\n".join(lines) if lines else "No grounded case digest was provided."

    def _refresh_dynamic_evidence(self, question: str) -> None:
        if not self.context:
            return
        payload = _resolve_dynamic_hacc_evidence(question, self.context)
        self.context.dynamic_evidence_items = list(payload.get("evidence_items") or [])
        self.context.dynamic_evidence_summary = str(payload.get("evidence_summary") or "")
        self.context.dynamic_anchor_passages = list(payload.get("anchor_passages") or [])
        self.context.dynamic_anchor_sections = list(payload.get("anchor_sections") or [])

    def _serialize_dynamic_evidence_context(self) -> Dict[str, Any]:
        if not self.context:
            return {}
        return {
            "dynamic_evidence_summary": self.context.dynamic_evidence_summary,
            "dynamic_evidence_items": list(self.context.dynamic_evidence_items),
            "dynamic_anchor_passages": list(self.context.dynamic_anchor_passages),
            "dynamic_anchor_sections": list(self.context.dynamic_anchor_sections),
        }
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get the full conversation history."""
        return self.conversation_history.copy()


class ComplaintGenerator:
    """
    Generates varied complaints from seed templates.
    
    This class creates diverse complaint scenarios by:
    - Using seed templates
    - Varying details and circumstances
    - Generating different personality types
    """
    
    def __init__(self, llm_backend):
        """
        Initialize complaint generator.
        
        Args:
            llm_backend: LLM backend for generating variations
        """
        self.llm_backend = llm_backend
    
    def generate_variations(self, seed: Dict[str, Any], count: int = 5) -> List[Dict[str, Any]]:
        """
        Generate variations of a seed complaint.
        
        Args:
            seed: Seed complaint template
            count: Number of variations to generate
            
        Returns:
            List of complaint variations
        """
        variations = []
        
        for i in range(count):
            prompt = f"""Based on this seed complaint scenario, generate a variation with different specific details but the same type of issue.

Seed scenario:
{json.dumps(seed, indent=2)}

Generate variation #{i+1} with:
- Different names/locations
- Different specific circumstances
- Same type of legal issue
- Realistic details

Return as JSON with fields: type, key_facts, summary

Variation:"""
            
            try:
                response = self.llm_backend(prompt)
                # Try to parse as JSON
                variation = self._parse_variation(response)
                variations.append(variation)
            except Exception as e:
                logger.warning(f"Error generating variation {i}: {e}")
                # Use seed with small modifications
                variations.append(self._simple_variation(seed, i))
        
        return variations
    
    def _parse_variation(self, response: str) -> Dict[str, Any]:
        """Parse LLM response as JSON variation."""
        try:
            # Try to extract JSON from response
            if '{' in response:
                json_start = response.index('{')
                json_end = response.rindex('}') + 1
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
        except Exception as e:
            logger.error(f"Error parsing variation: {e}")
            return {
                'type': 'unknown',
                'key_facts': {},
                'summary': response[:200]
            }
    
    def _simple_variation(self, seed: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Create simple variation of seed."""
        variation = seed.copy()
        variation['variation_id'] = index
        return variation
