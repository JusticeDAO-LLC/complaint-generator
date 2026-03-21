"""
Complaint Denoiser

Iteratively asks questions to fill gaps in the knowledge graph and reduce
noise/ambiguity in the complaint information.
"""

import hashlib
import logging
import re
from typing import Dict, List, Any, Optional, Tuple, Set
import os
import random
from .knowledge_graph import KnowledgeGraph, Entity, Relationship
from .dependency_graph import DependencyGraph
from .intake_claim_registry import (
    build_claim_element_question_intent,
    build_claim_element_question_text,
    build_proof_lead_question_intent,
    build_proof_lead_question_text,
    normalize_claim_type,
    render_question_text_from_intent,
)

logger = logging.getLogger(__name__)


class ComplaintDenoiser:
    """
    Denoises complaint information through iterative questioning.
    
    Uses knowledge graph gaps and dependency graph requirements to generate
    targeted questions that help clarify and complete the complaint.
    """
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.questions_asked = []
        self.questions_pool = []

        # Optional “policy” knobs for SGD-style exploration.
        # Default is deterministic/no-randomness.
        self.exploration_epsilon = self._env_float("CG_DENOISER_EXPLORATION_EPSILON", 0.0)
        self.momentum_beta = self._env_float("CG_DENOISER_MOMENTUM_BETA", 0.85)
        self.momentum_enabled = self._env_bool("CG_DENOISER_MOMENTUM_ENABLED", False)
        self.exploration_enabled = self._env_bool("CG_DENOISER_EXPLORATION_ENABLED", False)
        self.exploration_top_k = int(self._env_float("CG_DENOISER_EXPLORATION_TOP_K", 3) or 3)
        self.stagnation_window = int(self._env_float("CG_DENOISER_STAGNATION_WINDOW", 4) or 4)
        self.stagnation_gain_threshold = float(self._env_float("CG_DENOISER_STAGNATION_GAIN_THRESHOLD", 0.5) or 0.5)
        self.actor_critic_enabled = self._env_bool("CG_DENOISER_ACTOR_CRITIC_ENABLED", True)
        self.actor_weight = self._env_float("CG_DENOISER_ACTOR_WEIGHT", 1.0)
        self.critic_weight = self._env_float("CG_DENOISER_CRITIC_WEIGHT", 1.0)
        self.question_quality_weight = self._env_float("CG_DENOISER_QUESTION_QUALITY_WEIGHT", 1.0)
        self.empathy_weight = self._env_float("CG_DENOISER_EMPATHY_WEIGHT", 1.0)
        self.selector_quality_guard_enabled = self._env_bool("CG_DENOISER_SELECTOR_QUALITY_GUARD_ENABLED", True)
        self.phase_focus_order = self._env_csv(
            "CG_DENOISER_PHASE_FOCUS_ORDER",
            ["graph_analysis", "document_generation", "intake_questioning"],
        )

        seed = os.getenv("CG_DENOISER_SEED")
        self._rng = random.Random(int(seed)) if seed and seed.isdigit() else random.Random()

        # Momentum state: EMA of “gain” by question type.
        self._type_gain_ema: Dict[str, float] = {}
        self._recent_gains: List[float] = []


    def _env_bool(self, key: str, default: bool) -> bool:
        raw = os.getenv(key)
        if raw is None:
            return default
        val = raw.strip().lower()
        if val in {"1", "true", "yes", "y", "on"}:
            return True
        if val in {"0", "false", "no", "n", "off"}:
            return False
        return default


    def _env_float(self, key: str, default: float) -> float:
        raw = os.getenv(key)
        if raw is None:
            return default
        try:
            return float(raw.strip())
        except Exception:
            return default


    def _env_csv(self, key: str, default: List[str]) -> List[str]:
        raw = os.getenv(key)
        if raw is None:
            return list(default)
        values = [str(item).strip().lower() for item in raw.split(",")]
        cleaned = [item for item in values if item]
        return cleaned or list(default)


    def _workflow_phase_for_question(
        self,
        question_type: str,
        context: Optional[Dict[str, Any]] = None,
        source: str = "",
    ) -> str:
        qtype = (question_type or "").strip().lower()
        source_name = (source or "").strip().lower()
        context = context if isinstance(context, dict) else {}
        gap_type = str(context.get("gap_type") or "").strip().lower()
        follow_up_focus = {
            "missing_exact_action_dates",
            "missing_hearing_request_date",
            "missing_response_dates",
            "missing_hearing_timing",
            "retaliation_missing_causation",
            "retaliation_missing_causation_link",
            "retaliation_missing_sequencing_dates",
            "retaliation_missing_sequence",
        }
        if (
            qtype in {"timeline", "contradiction", "responsible_party"}
            or gap_type in follow_up_focus
            or source_name in {"dependency_graph_contradiction", "dependency_graph_requirement"}
        ):
            return "graph_analysis"
        if qtype in {"evidence", "remedy"} or gap_type in {"missing_written_notice"}:
            return "document_generation"
        return "intake_questioning"


    def _phase_focus_rank(self, workflow_phase: str) -> int:
        phase = (workflow_phase or "").strip().lower()
        if phase in self.phase_focus_order:
            return self.phase_focus_order.index(phase)
        return len(self.phase_focus_order)


    def _derive_extraction_targets(
        self,
        question_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        qtype = (question_type or "").strip().lower()
        context = context if isinstance(context, dict) else {}
        targets: List[str] = []
        if qtype in {"timeline", "contradiction"}:
            targets.extend(["exact_dates", "event_order"])
        if qtype in {"responsible_party", "relationship", "requirement"}:
            targets.extend(["actor_name", "actor_role"])
        if qtype in {"evidence", "requirement"}:
            targets.extend(["document_type", "document_date", "document_owner"])
        if qtype in {"timeline", "responsible_party", "contradiction"}:
            targets.extend(["decision_maker", "adverse_action"])
        if qtype in {"impact", "remedy"}:
            targets.extend(["harm_type", "requested_outcome"])
        gap_type = str(context.get("gap_type") or "").strip().lower()
        if gap_type in {"missing_written_notice", "missing_response_dates"}:
            targets.extend(["notice_chain", "notice_date", "response_timing"])
        if gap_type in {"retaliation_missing_causation", "retaliation_missing_sequence", "retaliation_missing_sequencing_dates"}:
            targets.extend(["protected_activity", "adverse_action", "causation_link"])
        if gap_type in {"missing_decision_timeline", "missing_exact_action_dates", "missing_hearing_timing"}:
            targets.extend(["exact_dates", "event_order", "response_timing"])
        if gap_type in {"missing_staff_identity", "missing_staff_title"}:
            targets.extend(["actor_name", "actor_role", "decision_maker"])
        deduped: List[str] = []
        for target in targets:
            if target and target not in deduped:
                deduped.append(target)
        return deduped


    def _derive_patchability_markers(
        self,
        question_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        qtype = (question_type or "").strip().lower()
        context = context if isinstance(context, dict) else {}
        markers: List[str] = []
        if qtype in {"timeline", "contradiction"}:
            markers.append("chronology_patch_anchor")
        if qtype in {"responsible_party", "relationship"}:
            markers.append("actor_link_patch_anchor")
        if qtype in {"evidence", "requirement"}:
            markers.append("support_patch_anchor")
            markers.append("documentary_artifact_patch_anchor")
        if qtype in {"impact", "remedy"}:
            markers.append("relief_patch_anchor")
        if str(context.get("gap_type") or "").strip().lower() in {"missing_written_notice", "missing_response_dates"}:
            markers.append("notice_chain_patch_anchor")
            markers.append("chronology_response_patch_anchor")
        if qtype in {"responsible_party", "timeline"}:
            markers.append("decision_actor_patch_anchor")
        if qtype in {"timeline", "contradiction"}:
            markers.append("adverse_action_patch_anchor")
        return markers


    def _short_description(self, text_value: str, limit: int = 160) -> str:
        snippet = " ".join((text_value or "").strip().split())
        if len(snippet) > limit:
            return snippet[: limit - 3] + "..."
        return snippet


    def _extract_date_strings(self, text: str) -> List[str]:
        if not text:
            return []
        date_patterns = [
            r'\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+\d{4}\b',
            r'\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{4}\b',
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
            r'\b\d{4}-\d{2}-\d{2}\b',
            r'\b(?:in|on|since|during|around|by|from)\s+((?:19|20)\d{2})\b',
        ]
        found: List[str] = []
        for pattern in date_patterns:
            for match in re.findall(pattern, text):
                if isinstance(match, tuple):
                    match = match[0]
                value = (match or "").strip()
                if value and value not in found:
                    found.append(value)
        return found


    def _extract_org_candidates(self, text: str) -> List[str]:
        if not text:
            return []
        candidates: Set[str] = set()
        org_suffixes = (
            r"(?:Inc\.?|LLC|Ltd\.?|Co\.?|Corp\.?|Corporation|Company|University|"
            r"Hospital|School|Department|Dept\.?|Agency|Clinic|Bank|Foundation|"
            r"Association|Partners|Group|Systems|Services)"
        )
        for match in re.findall(
            rf"\b([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){{0,4}}\s+{org_suffixes})\b",
            text,
        ):
            candidates.add(match.strip())
        for match in re.findall(
            r"\b(?:at|for|with|from)\s+([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,4})\b",
            text or "",
        ):
            candidates.add(match.strip())

        lower_text = text.lower()
        if any(
            k in lower_text
            for k in [
                "property management",
                "property manager",
                "management company",
                "leasing office",
                "housing authority",
                "housing office",
            ]
        ):
            candidates.add("Property Management")
        if "employer" in lower_text:
            candidates.add("Employer")
        if any(
            k in lower_text
            for k in [
                "company",
                "organization",
                "business",
                "agency",
                "department",
                "school",
                "university",
                "hospital",
                "clinic",
            ]
        ):
            candidates.add("Organization")

        months = {
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
            "jan",
            "feb",
            "mar",
            "apr",
            "jun",
            "jul",
            "aug",
            "sep",
            "sept",
            "oct",
            "nov",
            "dec",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }
        banned = {"i", "we", "they", "he", "she", "it", "my", "our", "their", "the", "a", "an"}

        results: List[str] = []
        for candidate in sorted(candidates):
            cleaned = re.sub(r"[^\w&.\-\s]", "", candidate).strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in banned or lowered in months:
                continue
            tokens = cleaned.split()
            if len(tokens) == 1 and len(cleaned) < 4:
                continue
            results.append(cleaned)
        return results


    def _extract_named_role_people(self, text: str) -> List[Tuple[str, str]]:
        if not text:
            return []
        role_keywords = (
            r"manager|supervisor|boss|coworker|co-worker|hr|human resources|director|"
            r"owner|principal|teacher|professor|doctor|nurse|attorney|lawyer|agent|"
            r"officer|landlord|neighbor|representative"
        )
        results: List[Tuple[str, str]] = []
        for match in re.finditer(
            rf"\b(?:my|the|a|an)\s+(?P<role>{role_keywords})\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}})\b",
            text or "",
            re.IGNORECASE,
        ):
            role = (match.group("role") or "").strip().lower()
            name = (match.group("name") or "").strip()
            if name and role:
                results.append((name, role))
        return results


    def _extract_generic_roles(self, text: str) -> List[str]:
        if not text:
            return []
        lower_text = text.lower()
        roles = [
            "manager",
            "supervisor",
            "boss",
            "owner",
            "landlord",
            "hr",
            "human resources",
            "director",
            "agent",
            "representative",
            "officer",
            "employer",
            "company",
            "organization",
            "agency",
            "department",
            "school",
            "university",
            "hospital",
            "clinic",
        ]
        found: List[str] = []
        for role in roles:
            if role in lower_text and role not in found:
                found.append(role)
        return found


    def _contains_remedy_cue(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        cues = [
            "seeking",
            "seek",
            "would like",
            "looking for",
            "request",
            "asking for",
            "refund",
            "reimbursement",
            "compensation",
            "back pay",
            "repair",
            "fix",
            "replacement",
            "apology",
            "policy change",
        ]
        return any(cue in lowered for cue in cues)


    def _contains_confirmation_placeholder(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        placeholder_cues = [
            "needs confirmation",
            "need confirmation",
            "to be confirmed",
            "tbd",
            "unknown",
            "not sure",
            "unsure",
            "can't remember",
            "cannot remember",
            "i think",
            "maybe",
            "possibly",
        ]
        return any(cue in lowered for cue in placeholder_cues)


    def _contains_causation_signal(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        sequencing_terms = [
            "because",
            "after",
            "soon after",
            "due to",
            "in retaliation",
            "as a result",
            "right after",
        ]
        return any(term in lowered for term in sequencing_terms)

    def _contains_sequence_signal(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        sequence_terms = [
            "before",
            "after",
            "then",
            "next",
            "later",
            "earlier",
            "same day",
            "the next day",
            "following day",
            "in sequence",
            "timeline",
        ]
        return any(term in lowered for term in sequence_terms)

    def _extract_response_timing_phrases(self, text: str) -> List[str]:
        if not text:
            return []
        patterns = [
            r"\b(?:within|after|in)\s+\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)\b",
            r"\b\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+(?:later|after|before)\b",
            r"\b(?:same day|next day|following day|immediately|right away|no response|never responded)\b",
        ]
        found: List[str] = []
        for pattern in patterns:
            for match in re.findall(pattern, text.lower()):
                normalized = str(match or "").strip()
                if normalized and normalized not in found:
                    found.append(normalized)
        return found

    def _contains_adverse_action_signal(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        signals = [
            "terminated",
            "fired",
            "demoted",
            "disciplined",
            "suspended",
            "evicted",
            "denied",
            "rejected",
            "written up",
            "write-up",
            "adverse action",
        ]
        return any(token in lowered for token in signals)

    def _contains_document_precision_signal(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        has_doc = any(token in lowered for token in ("notice", "letter", "email", "message", "record", "memo"))
        has_sender = any(token in lowered for token in ("from ", "sent by", "signed by", "authored by", "issued by"))
        has_date = bool(self._extract_date_strings(text))
        return bool(has_doc and has_sender and has_date)


    def _contains_retaliation_context(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        retaliation_terms = [
            "retaliation",
            "protected activity",
            "complained",
            "reported",
            "adverse action",
            "discipline",
            "fired",
            "terminated",
            "demoted",
        ]
        return any(term in lowered for term in retaliation_terms)


    def _extract_document_mentions(self, text: str) -> List[str]:
        if not text:
            return []
        lowered = text.lower()
        documents = []
        doc_tokens = [
            ("termination letter", "Termination letter"),
            ("notice", "Notice"),
            ("letter", "Letter"),
            ("email", "Email"),
            ("text message", "Text message"),
            ("message", "Message"),
            ("voicemail", "Voicemail"),
            ("record", "Record"),
            ("policy", "Policy"),
            ("handbook", "Handbook"),
            ("write-up", "Write-up"),
            ("write up", "Write-up"),
            ("memo", "Memo"),
        ]
        for token, label in doc_tokens:
            if token in lowered and label not in documents:
                documents.append(label)
        return documents


    def _append_unique_text_item(self, values: Any, text_value: str) -> List[str]:
        normalized_value = str(text_value or "").strip()
        if not normalized_value:
            return list(values) if isinstance(values, list) else []
        normalized_lower = normalized_value.lower()
        existing = [str(item).strip() for item in values] if isinstance(values, list) else []
        if normalized_lower not in {item.lower() for item in existing if item}:
            existing.append(normalized_value)
        return existing


    def _extract_named_people_with_titles(self, text: str) -> List[Tuple[str, str]]:
        if not text:
            return []
        results: List[Tuple[str, str]] = []
        patterns = [
            r"\b(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*,\s*(?P<title>[A-Za-z][A-Za-z\s/&-]{2,60})\b",
            r"\b(?P<title>manager|supervisor|director|hr manager|hr specialist|hearing officer|appeals officer|landlord|owner)\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text or "", flags=re.IGNORECASE):
                name = (match.group("name") or "").strip()
                title = (match.group("title") or "").strip().lower()
                if name and title:
                    results.append((name, title))
        deduped: List[Tuple[str, str]] = []
        seen = set()
        for name, title in results:
            key = (name.lower(), title.lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append((name, title))
        return deduped


    def _update_responsible_parties_from_answer(self,
                                               answer: str,
                                               knowledge_graph: KnowledgeGraph,
                                               updates: Dict[str, Any]) -> Dict[str, Any]:
        if not answer:
            return updates
        claims = knowledge_graph.get_entities_by_type("claim")
        claim_id = claims[0].id if len(claims) == 1 else None
        added_any = False

        for name, role in self._extract_named_role_people(answer):
            person, created = self._add_entity_if_missing(
                knowledge_graph,
                "person",
                name,
                {"role": role},
                0.7,
            )
            if created:
                updates["entities_updated"] += 1
            if claim_id and person:
                _, rel_created = self._add_relationship_if_missing(
                    knowledge_graph,
                    claim_id,
                    person.id,
                    "involves",
                    0.6,
                )
                if rel_created:
                    updates["relationships_added"] += 1
            added_any = True

        for name, title in self._extract_named_people_with_titles(answer):
            person, created = self._add_entity_if_missing(
                knowledge_graph,
                "person",
                name,
                {"role": title},
                0.72,
            )
            if created:
                updates["entities_updated"] += 1
            elif person and not str((person.attributes or {}).get("role") or "").strip():
                person.attributes["role"] = title
                updates["entities_updated"] += 1
            if claim_id and person:
                _, rel_created = self._add_relationship_if_missing(
                    knowledge_graph,
                    claim_id,
                    person.id,
                    "involves",
                    0.62,
                )
                if rel_created:
                    updates["relationships_added"] += 1
            added_any = True

        for org_name in self._extract_org_candidates(answer):
            org, created = self._add_entity_if_missing(
                knowledge_graph,
                "organization",
                org_name,
                {"role": "respondent"},
                0.6,
            )
            if created:
                updates["entities_updated"] += 1
            if claim_id and org:
                _, rel_created = self._add_relationship_if_missing(
                    knowledge_graph,
                    claim_id,
                    org.id,
                    "involves",
                    0.6,
                )
                if rel_created:
                    updates["relationships_added"] += 1
            added_any = True

        if not added_any:
            for role in self._extract_generic_roles(answer):
                role_norm = role.strip().lower()
                if role_norm in {"employer", "company", "organization", "agency", "department", "school", "university", "hospital", "clinic"}:
                    etype = "organization"
                    name = "Employer" if role_norm == "employer" else role_norm.title()
                    attrs = {"role": "respondent"}
                    confidence = 0.55
                else:
                    etype = "person"
                    name = "HR" if role_norm == "hr" else role_norm.title()
                    attrs = {"role": role_norm if role_norm != "human resources" else "hr"}
                    confidence = 0.55
                entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    etype,
                    name,
                    attrs,
                    confidence,
                )
                if created:
                    updates["entities_updated"] += 1
                if claim_id and entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        entity.id,
                        "involves",
                        0.55,
                    )
                    if rel_created:
                        updates["relationships_added"] += 1
        return updates


    def _find_entity(self, knowledge_graph: KnowledgeGraph, etype: str, name: str) -> Optional[Entity]:
        etype_norm = (etype or "").strip().lower()
        name_norm = (name or "").strip().lower()
        if not etype_norm or not name_norm:
            return None
        for entity in knowledge_graph.entities.values():
            if entity.type.lower() == etype_norm and entity.name.strip().lower() == name_norm:
                return entity
        return None


    def _next_entity_id(self, knowledge_graph: KnowledgeGraph) -> str:
        max_id = 0
        for entity_id in knowledge_graph.entities.keys():
            match = re.match(r"entity_(\d+)$", str(entity_id))
            if match:
                max_id = max(max_id, int(match.group(1)))
        return f"entity_{max_id + 1}"


    def _next_relationship_id(self, knowledge_graph: KnowledgeGraph) -> str:
        max_id = 0
        for rel_id in knowledge_graph.relationships.keys():
            match = re.match(r"rel_(\d+)$", str(rel_id))
            if match:
                max_id = max(max_id, int(match.group(1)))
        return f"rel_{max_id + 1}"


    def _add_entity_if_missing(self,
                               knowledge_graph: KnowledgeGraph,
                               etype: str,
                               name: str,
                               attributes: Dict[str, Any],
                               confidence: float) -> Tuple[Optional[Entity], bool]:
        existing = self._find_entity(knowledge_graph, etype, name)
        if existing:
            return existing, False
        entity = Entity(
            id=self._next_entity_id(knowledge_graph),
            type=etype,
            name=name,
            attributes=attributes,
            confidence=confidence,
            source='complaint'
        )
        knowledge_graph.add_entity(entity)
        return entity, True


    def _add_relationship_if_missing(self,
                                    knowledge_graph: KnowledgeGraph,
                                    source_id: str,
                                    target_id: str,
                                    relation_type: str,
                                    confidence: float) -> Tuple[Optional[Relationship], bool]:
        if not (source_id and target_id and relation_type):
            return None, False
        for rel in knowledge_graph.relationships.values():
            if rel.source_id == source_id and rel.target_id == target_id and rel.relation_type == relation_type:
                return rel, False
        relationship = Relationship(
            id=self._next_relationship_id(knowledge_graph),
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            attributes={},
            confidence=confidence,
            source='complaint'
        )
        knowledge_graph.add_relationship(relationship)
        return relationship, True


    def get_policy_state(self) -> Dict[str, Any]:
        return {
            "exploration_enabled": bool(self.exploration_enabled),
            "exploration_epsilon": float(self.exploration_epsilon),
            "exploration_top_k": int(self.exploration_top_k),
            "momentum_enabled": bool(self.momentum_enabled),
            "momentum_beta": float(self.momentum_beta),
            "stagnation_window": int(self.stagnation_window),
            "stagnation_gain_threshold": float(self.stagnation_gain_threshold),
            "type_gain_ema": dict(self._type_gain_ema),
            "recent_gains": list(self._recent_gains[-10:]),
            "actor_critic_enabled": bool(self.actor_critic_enabled),
            "actor_weight": float(self.actor_weight),
            "critic_weight": float(self.critic_weight),
            "question_quality_weight": float(self.question_quality_weight),
            "empathy_weight": float(self.empathy_weight),
            "selector_quality_guard_enabled": bool(self.selector_quality_guard_enabled),
            "phase_focus_order": list(self.phase_focus_order),
        }


    def _compute_gain(self, updates: Dict[str, Any]) -> float:
        # A small heuristic: “did this question produce useful structured updates?”
        return float(
            (updates.get('entities_updated') or 0)
            + (updates.get('relationships_added') or 0)
            + (updates.get('requirements_satisfied') or 0)
        )


    def _update_momentum(self, question_type: str, gain: float) -> None:
        qtype = (question_type or "unknown").strip() or "unknown"
        prev = float(self._type_gain_ema.get(qtype, gain))
        beta = float(self.momentum_beta)
        beta = min(max(beta, 0.0), 0.999)
        self._type_gain_ema[qtype] = beta * prev + (1.0 - beta) * float(gain)


    def _maybe_increase_exploration_when_stuck(self) -> float:
        # If recent gains are consistently low, boost epsilon slightly.
        if self.stagnation_window <= 0:
            return float(self.exploration_epsilon)
        window = self._recent_gains[-self.stagnation_window :]
        if len(window) < self.stagnation_window:
            return float(self.exploration_epsilon)
        avg_gain = sum(window) / max(len(window), 1)
        if avg_gain <= self.stagnation_gain_threshold:
            return min(0.5, float(self.exploration_epsilon) + 0.1)
        return float(self.exploration_epsilon)


    def is_stagnating(self) -> bool:
        if self.stagnation_window <= 0:
            return False
        window = self._recent_gains[-self.stagnation_window :]
        if len(window) < self.stagnation_window:
            return False
        avg_gain = sum(window) / max(len(window), 1)
        return avg_gain <= self.stagnation_gain_threshold


    def _apply_exploration_and_momentum(self, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not questions:
            return questions

        # Keep deterministic behavior unless explicitly enabled.
        if not (self.momentum_enabled or self.exploration_enabled):
            return questions

        # Momentum: reorder within the same priority bucket by EMA gain.
        priority_order = {'high': 0, 'medium': 1, 'low': 2}

        def score(q: Dict[str, Any]) -> float:
            qtype = (q.get('type') or 'unknown')
            return float(self._type_gain_ema.get(qtype, 0.0))

        # Group by priority to preserve the high/medium/low structure.
        grouped: Dict[int, List[Dict[str, Any]]] = {0: [], 1: [], 2: [], 3: []}
        for q in questions:
            grouped[priority_order.get(q.get('priority', 'low'), 3)].append(q)

        if self.momentum_enabled:
            for k in list(grouped.keys()):
                grouped[k].sort(key=score, reverse=True)

        merged: List[Dict[str, Any]] = []
        for k in sorted(grouped.keys()):
            merged.extend(grouped[k])

        # Exploration: with probability epsilon, swap the top question with another
        # from the top-K to encourage exploration.
        if self.exploration_enabled and self.exploration_top_k > 1:
            epsilon = self._maybe_increase_exploration_when_stuck()
            if self._rng.random() < max(0.0, min(1.0, epsilon)):
                k = min(int(self.exploration_top_k), len(merged))
                if k > 1:
                    j = self._rng.randrange(0, k)
                    merged[0], merged[j] = merged[j], merged[0]

        return merged

    def _normalize_question_text(self, text: str) -> str:
        return (text or "").strip().lower()

    def _already_asked(self, question_text: str) -> bool:
        norm = self._normalize_question_text(question_text)
        for item in self.questions_asked:
            q = item.get('question') or {}
            if isinstance(q, dict):
                asked_text = q.get('question', '')
            else:
                asked_text = str(q)
            if self._normalize_question_text(asked_text) == norm:
                return True
        return False

    def _with_empathy(self, question_text: str, question_type: str) -> str:
        # Keep this lightweight so we improve tone without bloating prompts.
        text = (question_text or "").strip()
        if not text:
            return text
        normalized = text.lower()
        empathy_openers = (
            "to make sure i understand, ",
            "i know this may be stressful, and this helps keep your record accurate: ",
            "so we can support your claim clearly, ",
            "thanks for sharing this. ",
            "i hear you. ",
        )
        if normalized.startswith(empathy_openers):
            return text

        prefix = ""
        qtype = (question_type or "").strip().lower()
        if qtype in {'clarification', 'relationship', 'requirement'}:
            prefix = "To make sure I understand, "
        elif qtype in {'timeline', 'contradiction', 'responsible_party'}:
            prefix = "I know this may be stressful, and this helps keep your record accurate: "
        elif qtype in {'evidence'}:
            prefix = "So we can support your claim clearly, "
        elif qtype in {'impact', 'remedy'}:
            prefix = "Thanks for sharing this. "

        if prefix:
            if prefix.endswith(": "):
                return prefix + text[0].lower() + text[1:] if len(text) > 1 else prefix + text.lower()
            return prefix + text
        return text

    def _question_quality_bonus_candidate(self, candidate: Dict[str, Any]) -> float:
        if not isinstance(candidate, dict):
            return 0.0
        question_text = str(candidate.get('question') or '').strip().lower()
        follow_up_tags = [str(tag).strip().lower() for tag in (candidate.get('follow_up_tags') or []) if str(tag).strip()]
        extraction_targets = [str(target).strip().lower() for target in (candidate.get('extraction_targets') or []) if str(target).strip()]
        workflow_phase = str(candidate.get('workflow_phase') or '').strip().lower()
        score = 0.0
        if not question_text:
            return score
        if question_text.endswith("?"):
            score += 0.35
        if question_text.count("?") <= 1:
            score += 0.35
        if any(question_text.startswith(prefix) for prefix in ("what ", "when ", "who ", "which ", "where ", "how ")):
            score += 0.4
        if 45 <= len(question_text) <= 240:
            score += 0.35
        if 'exact_dates' in follow_up_tags and any(token in question_text for token in ('exact date', 'what date', 'when')):
            score += 0.5
        if 'staff_identity' in follow_up_tags and any(token in question_text for token in ('full name', 'title', 'role', 'who')):
            score += 0.5
        if 'notice_chain' in follow_up_tags and any(token in question_text for token in ('notice', 'letter', 'email', 'message', 'document')):
            score += 0.4
        if 'retaliation_sequence' in follow_up_tags and any(token in question_text for token in ('protected activity', 'adverse', 'because', 'after')):
            score += 0.5
        if 'chronology_gap' in follow_up_tags and any(token in question_text for token in ('exact date', 'in order', 'before', 'after', 'sequence', 'how long')):
            score += 0.55
        if 'decision_precision' in follow_up_tags and any(token in question_text for token in ('who exactly', 'full name', 'title', 'organization', 'adverse action')):
            score += 0.55
        if 'documentary_precision' in follow_up_tags and any(token in question_text for token in ('document type', 'date', 'sender', 'recipient', 'delivered')):
            score += 0.55
        if 'response_timing' in follow_up_tags and any(token in question_text for token in ('how long', 'within', 'response', 'responded')):
            score += 0.55
        if extraction_targets:
            covered = 0
            keyword_map = {
                'exact_dates': ('date', 'when'),
                'event_order': ('before', 'after', 'timeline', 'sequence'),
                'actor_name': ('who', 'name'),
                'actor_role': ('title', 'role'),
                'document_type': ('document', 'notice', 'letter', 'email', 'message', 'record'),
                'document_date': ('date', 'dated', 'when'),
                'document_owner': ('who sent', 'who wrote', 'who owns', 'from'),
                'protected_activity': ('protected activity', 'complained', 'reported'),
                'adverse_action': ('adverse action', 'adverse', 'discipline', 'fired', 'terminated', 'denied'),
                'causation_link': ('because', 'as a result', 'why'),
                'harm_type': ('harm', 'impact'),
                'requested_outcome': ('remedy', 'seeking', 'outcome'),
                'notice_chain': ('notice', 'letter', 'email', 'message'),
                'response_timing': ('how long', 'within', 'response', 'responded'),
                'decision_maker': ('who made', 'who approved', 'decision-maker', 'decision maker'),
            }
            for target in extraction_targets:
                target_tokens = keyword_map.get(target, ())
                if target_tokens and any(token in question_text for token in target_tokens):
                    covered += 1
            if covered:
                score += min(1.0, 0.25 * float(covered))
        score += max(0.0, 0.7 - 0.25 * float(self._phase_focus_rank(workflow_phase)))
        return score

    def _empathy_bonus_candidate(self, candidate: Dict[str, Any]) -> float:
        if not isinstance(candidate, dict):
            return 0.0
        qtype = str(candidate.get('type') or '').strip().lower()
        question_text = str(candidate.get('question') or '').strip().lower()
        empathy_openers = (
            "to make sure i understand, ",
            "i know this may be stressful, and this helps keep your record accurate: ",
            "so we can support your claim clearly, ",
            "thanks for sharing this. ",
            "i hear you. ",
        )
        has_empathy_frame = question_text.startswith(empathy_openers)
        if has_empathy_frame:
            if qtype in {'timeline', 'contradiction', 'responsible_party', 'impact', 'remedy', 'evidence'}:
                return 0.8
            return 0.5
        if qtype in {'timeline', 'contradiction', 'responsible_party', 'impact', 'remedy'}:
            return -0.25
        return 0.0

    def _phase1_proof_priority(self, question_type: str) -> int:
        objective_order = {
            'contradiction': 0,
            'timeline': 0,
            'responsible_party': 2,
            'impact': 3,
            'requirement': 4,
            'evidence': 5,
            'clarification': 6,
            'relationship': 7,
        }
        return objective_order.get((question_type or '').strip().lower(), 7)

    def _phase1_question_metadata(
        self,
        question_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        qtype = (question_type or '').strip().lower()

        if qtype == 'timeline':
            return {
                'question_objective': 'establish_chronology',
                'question_reason': 'Chronology is necessary to determine sequence, notice, and causation.',
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'contradiction':
            contradiction_label = str(context.get('contradiction_label') or 'the conflicting facts')
            return {
                'question_objective': 'resolve_factual_contradiction',
                'question_reason': f"The intake record contains conflicting information about {contradiction_label} that should be reconciled before relying on it.",
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'responsible_party':
            return {
                'question_objective': 'identify_responsible_party',
                'question_reason': 'The complaint needs a concrete actor or organization tied to the alleged conduct.',
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'impact':
            return {
                'question_objective': 'capture_harm_and_requested_remedy',
                'question_reason': 'The intake record should state both the harm suffered and the outcome being sought.',
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'requirement':
            requirement_name = str(context.get('requirement_name') or 'this claim element')
            claim_name = str(context.get('claim_name') or 'the claim')
            return {
                'question_objective': 'satisfy_claim_requirement',
                'question_reason': f"{requirement_name} is still missing for {claim_name}.",
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'evidence':
            claim_name = str(context.get('claim_name') or 'the claim')
            return {
                'question_objective': 'identify_supporting_evidence',
                'question_reason': f"{claim_name} still needs supporting proof leads or corroborating evidence.",
                'expected_proof_gain': 'high',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'clarification':
            entity_name = str(context.get('entity_name') or 'this fact')
            return {
                'question_objective': 'clarify_low_confidence_fact',
                'question_reason': f"The current record about {entity_name} is too uncertain to rely on safely.",
                'expected_proof_gain': 'medium',
                'proof_priority': self._phase1_proof_priority(qtype),
            }
        if qtype == 'relationship':
            entity_name = str(context.get('entity_name') or 'this entity')
            return {
                'question_objective': 'connect_parties_and_facts',
                'question_reason': f"{entity_name} needs clearer linkage to the complaint narrative.",
                'expected_proof_gain': 'medium',
                'proof_priority': self._phase1_proof_priority(qtype),
            }

        return {
            'question_objective': 'general_intake_clarification',
            'question_reason': 'This question helps fill a remaining intake gap.',
            'expected_proof_gain': 'medium',
            'proof_priority': self._phase1_proof_priority(qtype),
        }

    def _phase1_question_targeting(
        self,
        question_type: str,
        context: Optional[Dict[str, Any]] = None,
        source: str = '',
    ) -> Dict[str, Any]:
        """Attach section-aware routing metadata to phase-1 intake questions."""
        context = context or {}
        qtype = (question_type or '').strip().lower()

        defaults = {
            'phase1_section': 'general',
            'target_claim_type': str(context.get('claim_type') or ''),
            'target_element_id': str(context.get('requirement_id') or context.get('target_element_id') or ''),
            'target_fact_type': '',
            'blocking_level': 'important',
            'expected_update_kind': 'clarify_record',
        }

        if qtype == 'contradiction':
            defaults.update({
                'phase1_section': 'contradictions',
                'target_fact_type': 'contradicted_fact',
                'blocking_level': 'blocking',
                'expected_update_kind': 'resolve_contradiction',
            })
        elif qtype == 'timeline':
            defaults.update({
                'phase1_section': 'chronology',
                'target_fact_type': 'timeline',
                'blocking_level': 'blocking',
                'expected_update_kind': 'add_timeline_fact',
            })
        elif qtype == 'responsible_party':
            defaults.update({
                'phase1_section': 'actors',
                'target_fact_type': 'responsible_party',
                'blocking_level': 'blocking',
                'expected_update_kind': 'identify_actor',
            })
        elif qtype == 'impact':
            defaults.update({
                'phase1_section': 'harm_remedy',
                'target_fact_type': 'impact_or_remedy',
                'blocking_level': 'important',
                'expected_update_kind': 'capture_harm_or_remedy',
            })
        elif qtype == 'requirement':
            defaults.update({
                'phase1_section': 'claim_elements',
                'target_fact_type': 'claim_element',
                'blocking_level': 'blocking',
                'expected_update_kind': 'satisfy_claim_element',
            })
        elif qtype == 'evidence':
            defaults.update({
                'phase1_section': 'proof_leads',
                'target_fact_type': 'proof_lead',
                'blocking_level': 'important',
                'expected_update_kind': 'capture_proof_lead',
            })
        elif qtype == 'relationship':
            defaults.update({
                'phase1_section': 'actors',
                'target_fact_type': 'relationship',
                'blocking_level': 'important',
                'expected_update_kind': 'link_parties',
            })
        elif qtype == 'clarification':
            defaults.update({
                'phase1_section': 'general',
                'target_fact_type': 'uncertain_fact',
                'blocking_level': 'informational',
                'expected_update_kind': 'clarify_fact',
            })

        if not defaults['target_claim_type']:
            defaults['target_claim_type'] = str(context.get('claim_name') or '')
        workflow_phase = str(context.get('workflow_phase') or '').strip().lower() or self._workflow_phase_for_question(qtype, context=context, source=source)
        defaults['workflow_phase'] = workflow_phase
        defaults['workflow_phase_rank'] = int(context.get('workflow_phase_rank', self._phase_focus_rank(workflow_phase)) or self._phase_focus_rank(workflow_phase))
        context_targets = [str(target).strip() for target in (context.get('extraction_targets') or []) if str(target).strip()]
        context_markers = [str(marker).strip() for marker in (context.get('patchability_markers') or []) if str(marker).strip()]
        defaults['extraction_targets'] = context_targets or self._derive_extraction_targets(qtype, context=context)
        defaults['patchability_markers'] = context_markers or self._derive_patchability_markers(qtype, context=context)
        if context.get('recommended_resolution_lane'):
            defaults['recommended_resolution_lane'] = str(context.get('recommended_resolution_lane') or '')

        return defaults

    def _build_phase1_question(
        self,
        *,
        question_type: str,
        question_text: str,
        context: Optional[Dict[str, Any]] = None,
        priority: str = 'medium',
        question_intent: Optional[Dict[str, Any]] = None,
        source: str = '',
    ) -> Dict[str, Any]:
        normalized_intent = question_intent if isinstance(question_intent, dict) else None
        payload = {
            'type': question_type,
            'question': render_question_text_from_intent(normalized_intent) if normalized_intent else question_text,
            'context': context or {},
            'priority': priority,
        }
        if normalized_intent:
            payload['question_intent'] = normalized_intent
            payload['question_goal'] = str(normalized_intent.get('question_goal') or '')
            payload['question_strategy'] = str(normalized_intent.get('question_strategy') or '')
        payload.update(self._phase1_question_metadata(question_type, payload['context']))
        payload.update(self._phase1_question_targeting(question_type, payload['context'], source=source))
        return payload

    def _question_candidate(
        self,
        *,
        source: str,
        question_type: str,
        question_text: str,
        context: Optional[Dict[str, Any]] = None,
        priority: str = 'medium',
        question_intent: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        question_payload = self._build_phase1_question(
            question_type=question_type,
            question_text=question_text,
            context=context,
            priority=priority,
            question_intent=question_intent,
            source=source,
        )
        question_payload['candidate_source'] = source
        follow_up_tags = self._question_follow_up_tags(
            question_type=question_type,
            question_text=str(question_payload.get('question') or question_text or ''),
            context=question_payload.get('context'),
        )
        question_payload['follow_up_tags'] = follow_up_tags
        question_payload['ranking_explanation'] = {
            'candidate_source': source,
            'priority': str(question_payload.get('priority') or priority or 'medium'),
            'proof_priority': int(question_payload.get('proof_priority', self._phase1_proof_priority(question_type))),
            'blocking_level': str(question_payload.get('blocking_level') or ''),
            'phase1_section': str(question_payload.get('phase1_section') or ''),
            'question_goal': str(question_payload.get('question_goal') or question_payload.get('question_objective') or ''),
            'question_strategy': str(question_payload.get('question_strategy') or 'default_generation'),
            'target_claim_type': str(question_payload.get('target_claim_type') or ''),
            'target_element_id': str(question_payload.get('target_element_id') or ''),
            'target_fact_type': str(question_payload.get('target_fact_type') or ''),
            'expected_update_kind': str(question_payload.get('expected_update_kind') or ''),
            'recommended_resolution_lane': str(question_payload.get('recommended_resolution_lane') or ''),
            'workflow_phase': str(question_payload.get('workflow_phase') or ''),
            'workflow_phase_rank': int(question_payload.get('workflow_phase_rank')) if question_payload.get('workflow_phase_rank') is not None else 99,
            'extraction_targets': list(question_payload.get('extraction_targets') or []),
            'patchability_markers': list(question_payload.get('patchability_markers') or []),
            'follow_up_tags': list(follow_up_tags),
        }
        return question_payload

    def _question_follow_up_tags(
        self,
        *,
        question_type: str,
        question_text: str,
        context: Optional[Dict[str, Any]],
    ) -> List[str]:
        tags: List[str] = []
        normalized_text = (question_text or "").lower()
        context = context if isinstance(context, dict) else {}
        gap_type = str(context.get('gap_type') or '').strip().lower()

        if gap_type in {'missing_exact_action_dates', 'missing_hearing_request_date', 'missing_response_dates', 'missing_hearing_timing'}:
            tags.append('exact_dates')
        if gap_type in {'missing_staff_identity', 'missing_staff_title'}:
            tags.append('staff_identity')
        if gap_type in {'missing_written_notice'}:
            tags.append('notice_chain')
        if gap_type in {'retaliation_missing_causation', 'retaliation_missing_causation_link', 'retaliation_missing_sequencing_dates', 'retaliation_missing_sequence'}:
            tags.append('retaliation_sequence')
        if gap_type in {'missing_exact_action_dates', 'missing_decision_timeline', 'missing_hearing_timing', 'missing_response_dates'}:
            tags.append('chronology_gap')
        if gap_type in {'missing_staff_identity', 'missing_staff_title'}:
            tags.append('decision_precision')
        if gap_type in {'missing_written_notice', 'missing_response_dates'}:
            tags.append('documentary_precision')

        if any(token in normalized_text for token in ('exact date', 'on what date', 'when did')):
            tags.append('exact_dates')
        if any(token in normalized_text for token in ('full name', 'title', 'role', 'who specifically')):
            tags.append('staff_identity')
        if any(token in normalized_text for token in ('notice', 'letter', 'email', 'message')):
            tags.append('notice_chain')
        if any(token in normalized_text for token in ('protected activity', 'adverse action', 'because of', 'soon after')):
            tags.append('retaliation_sequence')
        if any(token in normalized_text for token in ('sequence', 'before', 'after', 'timeline', 'order')):
            tags.append('chronology_gap')
        if any(token in normalized_text for token in ('decision-maker', 'decision maker', 'approved', 'communicated it')):
            tags.append('decision_precision')
        if any(token in normalized_text for token in ('document', 'message', 'email', 'who sent', 'dated')):
            tags.append('documentary_precision')
        if any(token in normalized_text for token in ('how long', 'within how many', 'response time', 'responded')):
            tags.append('response_timing')

        if question_type in {'timeline'} and 'exact_dates' not in tags:
            tags.append('timeline')
        deduped: List[str] = []
        for tag in tags:
            if tag and tag not in deduped:
                deduped.append(tag)
        return deduped

    def _build_contradiction_questions(
        self,
        dependency_graph: DependencyGraph,
        max_questions: int,
    ) -> List[Dict[str, Any]]:
        questions: List[Dict[str, Any]] = []
        seen_pairs: Set[str] = set()

        for dependency in dependency_graph.dependencies.values():
            dependency_type = getattr(dependency, 'dependency_type', None)
            dependency_type_value = getattr(dependency_type, 'value', str(dependency_type or '')).lower()
            if dependency_type_value != 'contradicts':
                continue

            left_node = dependency_graph.get_node(dependency.source_id)
            right_node = dependency_graph.get_node(dependency.target_id)
            left_name = left_node.name if left_node else dependency.source_id
            right_name = right_node.name if right_node else dependency.target_id
            pair_key = '|'.join(sorted([str(left_name), str(right_name)]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            contradiction_label = f"{left_name} and {right_name}"
            questions.append(self._question_candidate(
                source='dependency_graph_contradiction',
                question_type='contradiction',
                question_text=(
                    f"I have conflicting information about {left_name} and {right_name}. "
                    "Which version is correct, and what details or records support it?"
                ),
                context={
                    'left_node_id': dependency.source_id,
                    'right_node_id': dependency.target_id,
                    'left_node_name': left_name,
                    'right_node_name': right_name,
                    'contradiction_label': contradiction_label,
                },
                priority='high',
            ))
            if len(questions) >= max_questions:
                break

        return questions

    def _build_claim_element_questions(
        self,
        intake_case_file: Optional[Dict[str, Any]],
        max_questions: int,
    ) -> List[Dict[str, Any]]:
        """Build questions from missing registry-backed claim elements in the intake case file."""
        if not isinstance(intake_case_file, dict):
            return []

        questions: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()
        candidate_claims = intake_case_file.get('candidate_claims', [])
        if not isinstance(candidate_claims, list):
            return []

        def _expected_modalities(evidence_classes: List[str]) -> List[str]:
            values = [str(item or '').strip().lower() for item in evidence_classes if str(item or '').strip()]
            modalities: List[str] = []
            if any(token in values for token in ('policy', 'handbook')):
                modalities.append('policy_document')
            if any(
                token in values
                for token in (
                    'lease', 'denial_notice', 'termination_notice', 'eviction_notice', 'application_record',
                    'inspection_record', 'maintenance_record', 'rent_record', 'personnel_record',
                )
            ):
                modalities.append('file_evidence')
            if any(token in values for token in ('email', 'text_message', 'landlord_message', 'denial_message')):
                if 'file_evidence' not in modalities:
                    modalities.append('file_evidence')
            return modalities

        def _targets_for_element(element_id: str, modalities: List[str]) -> List[str]:
            normalized_element = str(element_id or '').strip().lower()
            targets: List[str] = ['actor_name', 'actor_role']
            element_target_map = {
                'protected_trait': ['harm_type'],
                'housing_context': ['actor_name', 'actor_role', 'decision_maker'],
                'employment_relationship': ['actor_name', 'actor_role', 'decision_maker'],
                'adverse_action': ['adverse_action', 'exact_dates', 'event_order'],
                'discriminatory_motive': ['causation_link', 'event_order'],
                'causation': ['protected_activity', 'adverse_action', 'causation_link', 'exact_dates', 'event_order'],
            }
            targets.extend(element_target_map.get(normalized_element, []))
            if 'policy_document' in modalities:
                targets.extend(['document_type', 'document_owner'])
            if 'file_evidence' in modalities:
                targets.extend(['document_type', 'document_date', 'document_owner'])
            deduped: List[str] = []
            for item in targets:
                if item and item not in deduped:
                    deduped.append(item)
            return deduped

        def _patchability_for_element(element_id: str, modalities: List[str]) -> List[str]:
            normalized_element = str(element_id or '').strip().lower()
            markers = ['claim_element_patch_anchor', 'support_patch_anchor']
            if normalized_element in {'housing_context', 'employment_relationship'}:
                markers.append('actor_link_patch_anchor')
            if normalized_element in {'adverse_action', 'causation'}:
                markers.append('chronology_patch_anchor')
            if 'policy_document' in modalities:
                markers.append('policy_document_patch_anchor')
            if 'file_evidence' in modalities:
                markers.append('documentary_artifact_patch_anchor')
            deduped: List[str] = []
            for item in markers:
                if item and item not in deduped:
                    deduped.append(item)
            return deduped

        for claim in candidate_claims:
            if not isinstance(claim, dict):
                continue
            claim_type = normalize_claim_type(str(claim.get('claim_type') or '').strip())
            claim_label = str(claim.get('label') or claim_type or 'this claim').strip()
            weak_claim_focus = claim_type in {'housing_discrimination', 'hacc_research_engine'}
            for element in claim.get('required_elements', []) or []:
                if not isinstance(element, dict):
                    continue
                element_status = str(element.get('status') or '').strip().lower()
                if element_status in {'present', 'satisfied', 'complete'}:
                    continue
                element_id = str(element.get('element_id') or '').strip()
                element_label = str(element.get('label') or element_id or 'this missing element').strip()
                question_key = f"{claim_type}:{element_id}:{element_label}".lower()
                if question_key in seen_keys:
                    continue
                seen_keys.add(question_key)
                evidence_classes = list(element.get('evidence_classes', []) or [])
                actor_roles = list(element.get('actor_roles', []) or [])
                expected_modalities = _expected_modalities(evidence_classes)
                extraction_targets = _targets_for_element(element_id, expected_modalities)
                patchability_markers = _patchability_for_element(element_id, expected_modalities)
                gap_id = f"{claim_type}:{element_id}".lower()
                question_intent = build_claim_element_question_intent(
                    claim_type,
                    claim_label,
                    {
                        'element_id': element_id,
                        'label': element_label,
                        'blocking': bool(element.get('blocking', False)),
                        'actor_roles': actor_roles,
                        'evidence_classes': evidence_classes,
                    },
                )
                question_text = build_claim_element_question_text(
                    claim_type,
                    claim_label,
                    element_id,
                    element_label,
                )
                if 'policy_document' in expected_modalities and 'file_evidence' in expected_modalities:
                    question_text = (
                        f"{question_text} If available, identify one policy document and one file record "
                        "(notice, lease, email, or upload) with date and sender."
                    )
                elif 'policy_document' in expected_modalities:
                    question_text = (
                        f"{question_text} If available, identify the policy document (name/section) and who issued it."
                    )
                elif 'file_evidence' in expected_modalities:
                    question_text = (
                        f"{question_text} If available, identify one file record (notice, lease, email, or upload) with date and sender."
                    )
                if not self._already_asked(question_text):
                    questions.append(self._question_candidate(
                        source='intake_claim_element_gap',
                        question_type='requirement',
                        question_text=question_text,
                        context={
                            'claim_type': claim_type,
                            'claim_name': claim_label,
                            'requirement_id': element_id,
                            'requirement_name': element_label,
                            'target_element_id': element_id,
                            'gap_id': gap_id,
                            'gap_type': 'missing_claim_element',
                            'requirement_key': element_id,
                            'actor_roles': actor_roles,
                            'evidence_classes': evidence_classes,
                            'expected_evidence_modalities': expected_modalities,
                            'deterministic_update_key': gap_id,
                            'workflow_phase': 'graph_analysis' if (bool(element.get('blocking', False)) or weak_claim_focus) else 'intake_questioning',
                            'recommended_resolution_lane': 'structured_requirement_capture',
                            'extraction_targets': extraction_targets,
                            'patchability_markers': patchability_markers,
                        },
                        priority='high' if (bool(element.get('blocking', False)) or weak_claim_focus) else 'medium',
                        question_intent=question_intent,
                    ))
                if len(questions) >= max_questions:
                    return questions[:max_questions]

        return questions

    def _build_proof_lead_questions(
        self,
        intake_case_file: Optional[Dict[str, Any]],
        max_questions: int,
    ) -> List[Dict[str, Any]]:
        """Build claim-aware proof-lead questions when the intake still lacks support sources."""
        if not isinstance(intake_case_file, dict) or max_questions <= 0:
            return []

        proof_leads = intake_case_file.get('proof_leads', [])
        existing_policy_doc = False
        existing_file_evidence = False
        if isinstance(proof_leads, list):
            for lead in proof_leads:
                if not isinstance(lead, dict):
                    continue
                lead_text = " ".join(
                    str(lead.get(field) or '').strip().lower()
                    for field in ('lead_type', 'description', 'expected_format', 'recommended_support_kind', 'source_quality_target')
                )
                if any(token in lead_text for token in ('policy', 'handbook', 'rule', 'criteria')):
                    existing_policy_doc = True
                if any(token in lead_text for token in ('file', 'pdf', 'upload', 'notice', 'lease', 'record', 'email', 'message', 'document')):
                    existing_file_evidence = True
            if proof_leads and existing_policy_doc and existing_file_evidence:
                return []

        questions: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()
        candidate_claims = intake_case_file.get('candidate_claims', [])
        if not isinstance(candidate_claims, list):
            return []

        for claim in candidate_claims:
            if not isinstance(claim, dict):
                continue
            claim_type = normalize_claim_type(str(claim.get('claim_type') or '').strip())
            claim_label = str(claim.get('label') or claim_type or 'this claim').strip()
            weak_claim_focus = claim_type in {'housing_discrimination', 'hacc_research_engine'}
            missing_modalities: List[str] = []
            if not existing_policy_doc:
                missing_modalities.append('policy_document')
            if not existing_file_evidence:
                missing_modalities.append('file_evidence')
            if not missing_modalities:
                continue
            question_key = f"{claim_type}:{claim_label}:proof_leads".lower()
            if question_key in seen_keys:
                continue
            seen_keys.add(question_key)
            question_intent = build_proof_lead_question_intent(claim_type, claim_label)
            question_text = build_proof_lead_question_text(claim_type, claim_label)
            if missing_modalities == ['policy_document', 'file_evidence'] or missing_modalities == ['file_evidence', 'policy_document']:
                question_text = (
                    f"{question_text} Please name at least one policy document and one file record "
                    "(notice, lease, email, or attachment) with date, sender, and where it can be obtained."
                )
            elif missing_modalities == ['policy_document']:
                question_text = (
                    f"{question_text} Please identify any policy document (name/section) relevant to this claim and who issued it."
                )
            elif missing_modalities == ['file_evidence']:
                question_text = (
                    f"{question_text} Please identify one file record (notice, lease, email, message, or attachment) with date, sender, and where it can be obtained."
                )
            if not self._already_asked(question_text):
                questions.append(self._question_candidate(
                    source='intake_proof_gap',
                    question_type='evidence',
                    question_text=question_text,
                    context={
                        'claim_type': claim_type,
                        'claim_name': claim_label,
                        'gap_id': f"{claim_type}:proof_leads",
                        'gap_type': 'missing_proof_leads',
                        'expected_evidence_modalities': list(missing_modalities),
                        'deterministic_update_key': f"{claim_type}:proof_leads:{'-'.join(missing_modalities)}",
                        'workflow_phase': 'graph_analysis' if weak_claim_focus else 'document_generation',
                        'recommended_resolution_lane': 'structured_proof_capture',
                        'extraction_targets': ['document_type', 'document_date', 'document_owner', 'actor_name'],
                        'patchability_markers': ['support_patch_anchor', 'documentary_artifact_patch_anchor', 'notice_chain_patch_anchor'],
                    },
                    priority='high',
                    question_intent=question_intent,
                ))
            if len(questions) >= max_questions:
                return questions[:max_questions]

        return questions

    def _temporal_issue_question_type(self, issue_type: str) -> str:
        normalized_issue_type = str(issue_type or '').strip().lower()
        if normalized_issue_type in {'missing_staff_identity', 'missing_staff_title'}:
            return 'responsible_party'
        if normalized_issue_type in {'missing_written_notice'}:
            return 'evidence'
        return 'timeline'

    def _temporal_issue_extraction_targets(
        self,
        issue_type: str,
        *,
        element_tags: List[str],
        question_type: str,
    ) -> List[str]:
        normalized_issue_type = str(issue_type or '').strip().lower()
        normalized_element_tags = [str(tag or '').strip().lower() for tag in (element_tags or []) if str(tag or '').strip()]
        targets = self._derive_extraction_targets(question_type, context={'gap_type': normalized_issue_type})
        if normalized_issue_type == 'relative_only_ordering' or normalized_issue_type.startswith('temporal_reverse_'):
            targets.extend(['exact_dates', 'event_order'])
        if normalized_issue_type in {
            'retaliation_missing_causation',
            'retaliation_missing_causation_link',
            'retaliation_missing_sequence',
            'retaliation_missing_sequencing_dates',
        } or 'causation' in normalized_element_tags:
            targets.extend(['protected_activity', 'adverse_action', 'causation_link', 'exact_dates', 'event_order'])
        if normalized_issue_type in {'missing_hearing_request_date', 'missing_hearing_timing'}:
            targets.extend(['exact_dates', 'response_timing', 'notice_chain', 'actor_name', 'actor_role'])
        if normalized_issue_type in {'missing_response_dates', 'missing_decision_timeline'}:
            targets.extend(['exact_dates', 'response_timing', 'notice_chain', 'document_date', 'document_owner'])
        if normalized_issue_type == 'missing_written_notice':
            targets.extend(['document_type', 'document_date', 'document_owner', 'notice_chain'])
        if normalized_issue_type in {'missing_staff_identity', 'missing_staff_title'}:
            targets.extend(['actor_name', 'actor_role', 'decision_maker', 'adverse_action'])
        deduped: List[str] = []
        for target in targets:
            if target and target not in deduped:
                deduped.append(target)
        return deduped

    def _temporal_issue_patchability_markers(
        self,
        issue_type: str,
        *,
        element_tags: List[str],
        question_type: str,
    ) -> List[str]:
        normalized_issue_type = str(issue_type or '').strip().lower()
        normalized_element_tags = [str(tag or '').strip().lower() for tag in (element_tags or []) if str(tag or '').strip()]
        markers = self._derive_patchability_markers(question_type, context={'gap_type': normalized_issue_type})
        if normalized_issue_type == 'relative_only_ordering' or normalized_issue_type.startswith('temporal_reverse_'):
            markers.extend(['chronology_patch_anchor', 'adverse_action_patch_anchor'])
        if normalized_issue_type in {
            'retaliation_missing_causation',
            'retaliation_missing_causation_link',
            'retaliation_missing_sequence',
            'retaliation_missing_sequencing_dates',
        } or 'causation' in normalized_element_tags:
            markers.extend(['chronology_patch_anchor', 'adverse_action_patch_anchor'])
        if normalized_issue_type in {'missing_hearing_request_date', 'missing_hearing_timing', 'missing_response_dates', 'missing_decision_timeline'}:
            markers.extend(['chronology_response_patch_anchor', 'notice_chain_patch_anchor'])
        if normalized_issue_type in {'missing_staff_identity', 'missing_staff_title'}:
            markers.extend(['actor_link_patch_anchor', 'decision_actor_patch_anchor'])
        if normalized_issue_type == 'missing_written_notice':
            markers.extend(['support_patch_anchor', 'documentary_artifact_patch_anchor', 'notice_chain_patch_anchor'])
        deduped: List[str] = []
        for marker in markers:
            if marker and marker not in deduped:
                deduped.append(marker)
        return deduped

    def _build_claim_temporal_gap_question_text(
        self,
        issue_type: str,
        *,
        claim_label: str,
        summary: str,
        left_node_name: str,
        right_node_name: str,
        relative_markers: List[str],
    ) -> str:
        normalized_issue_type = str(issue_type or '').strip().lower()
        claim_reference = str(claim_label or '').strip() or 'this claim'
        if claim_reference.lower() == 'this claim':
            claim_reference = 'claim'
        if normalized_issue_type == 'relative_only_ordering':
            relative_phrase = ''
            if relative_markers:
                relative_phrase = f" using the reported {', '.join(relative_markers)} sequence"
            anchor_subject = left_node_name or 'the event you described'
            relative_context = " ".join(
                part
                for part in (
                    claim_reference,
                    summary,
                    left_node_name,
                    right_node_name,
                    " ".join(relative_markers or []),
                )
                if isinstance(part, str) and part.strip()
            ).lower()
            if any(
                token in relative_context
                for token in (
                    'retaliat',
                    'adverse',
                    'complaint',
                    'grievance',
                    'hearing',
                    'appeal',
                    'housing status',
                )
            ):
                return (
                    f"For your {claim_reference}, what protected activity happened first, what exact adverse action "
                    "followed, on what date or timeframe did it happen, who communicated it, and what notice, "
                    "message, or decision record proves that action?"
                )
            return (
                f"For your {claim_reference} claim, what is the most specific date or timeframe for {anchor_subject}, "
                f"and what happened immediately before and after it{relative_phrase}?"
            )
        if normalized_issue_type.startswith('temporal_reverse_'):
            left_label = left_node_name or 'the first event'
            right_label = right_node_name or 'the second event'
            return (
                f"For your {claim_reference} claim, which happened first: {left_label} or {right_label}, "
                "and what is the most specific date or timeframe for each event?"
            )
        if normalized_issue_type in {
            'retaliation_missing_causation',
            'retaliation_missing_causation_link',
            'retaliation_missing_sequence',
            'retaliation_missing_sequencing_dates',
        }:
            return (
                f"For your {claim_reference} claim, what protected activity happened first, what adverse action followed, "
                "who was involved in each step, and on what exact dates or timeframes did those events occur?"
            )
        if normalized_issue_type in {'missing_hearing_request_date', 'missing_hearing_timing'}:
            return (
                f"For your {claim_reference} claim, on what date did you request the hearing, grievance, or review, "
                "who received it, and do you have any notice, email, or letter confirming that request?"
            )
        if normalized_issue_type in {'missing_response_dates', 'missing_decision_timeline'}:
            return (
                f"For your {claim_reference} claim, when did you receive each response or decision, who sent it, "
                "and do you have any notice, email, or letter showing that timeline?"
            )
        if normalized_issue_type == 'missing_written_notice':
            return (
                f"For your {claim_reference} claim, do you have any written notice, email, text, letter, or upload "
                "showing the decision, including the date and sender?"
            )
        if normalized_issue_type in {'missing_staff_identity', 'missing_staff_title'}:
            return (
                f"For your {claim_reference} claim, who specifically made or communicated the decision, "
                "and what were that person's full name, title, and role?"
            )
        summary_clause = f" This appears unresolved because {summary}" if summary else ''
        return (
            f"For your {claim_reference} claim, what exact dates, sequence details, and decision-maker information "
            f"would anchor this timeline gap clearly?{summary_clause}"
        )

    def _build_claim_temporal_gap_questions(
        self,
        intake_case_file: Optional[Dict[str, Any]],
        max_questions: int,
    ) -> List[Dict[str, Any]]:
        if not isinstance(intake_case_file, dict) or max_questions <= 0:
            return []

        temporal_issue_registry = intake_case_file.get('temporal_issue_registry', [])
        if not isinstance(temporal_issue_registry, list) or not temporal_issue_registry:
            return []

        claim_label_map: Dict[str, str] = {}
        for claim in intake_case_file.get('candidate_claims', []) or []:
            if not isinstance(claim, dict):
                continue
            claim_type = normalize_claim_type(str(claim.get('claim_type') or '').strip())
            if not claim_type:
                continue
            claim_label_map[claim_type] = str(claim.get('label') or claim_type).strip()

        questions: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()
        for issue in temporal_issue_registry:
            if len(questions) >= max_questions:
                break
            if not isinstance(issue, dict):
                continue
            status = str(issue.get('status') or '').strip().lower()
            if status in {'resolved', 'closed', 'fixed'}:
                continue
            claim_types = [
                normalize_claim_type(str(value or '').strip())
                for value in (issue.get('claim_types') or issue.get('affected_claim_types') or [])
                if str(value or '').strip()
            ]
            claim_types = [claim_type for claim_type in claim_types if claim_type]
            claim_type = claim_types[0] if claim_types else ''
            claim_label = claim_label_map.get(claim_type) or (claim_type.replace('_', ' ') if claim_type else 'this claim')
            issue_id = str(issue.get('issue_id') or issue.get('source_ref') or issue.get('issue_type') or '').strip()
            issue_type = str(issue.get('issue_type') or issue.get('category') or '').strip().lower()
            element_tags = [str(tag or '').strip() for tag in (issue.get('element_tags') or issue.get('affected_element_ids') or []) if str(tag or '').strip()]
            target_element_id = str(element_tags[0] or '').strip().lower() if element_tags else ''
            question_key = '|'.join(filter(None, [issue_id.lower(), claim_type, issue_type, target_element_id]))
            if question_key in seen_keys:
                continue
            seen_keys.add(question_key)
            question_type = self._temporal_issue_question_type(issue_type)
            relative_markers = [str(marker or '').strip().lower() for marker in (issue.get('relative_markers') or []) if str(marker or '').strip()]
            question_text = self._build_claim_temporal_gap_question_text(
                issue_type,
                claim_label=claim_label,
                summary=self._short_description(str(issue.get('summary') or '').strip(), limit=120),
                left_node_name=str(issue.get('left_node_name') or '').strip(),
                right_node_name=str(issue.get('right_node_name') or '').strip(),
                relative_markers=relative_markers,
            )
            if self._already_asked(question_text):
                continue
            extraction_targets = self._temporal_issue_extraction_targets(
                issue_type,
                element_tags=element_tags,
                question_type=question_type,
            )
            patchability_markers = self._temporal_issue_patchability_markers(
                issue_type,
                element_tags=element_tags,
                question_type=question_type,
            )
            question = self._question_candidate(
                source='intake_claim_temporal_gap',
                question_type=question_type,
                question_text=question_text,
                context={
                    'claim_type': claim_type,
                    'claim_name': claim_label,
                    'gap_id': issue_id or f'{claim_type}:{issue_type}',
                    'gap_type': issue_type,
                    'requirement_id': target_element_id,
                    'target_element_id': target_element_id,
                    'temporal_issue_id': issue_id,
                    'temporal_issue_category': str(issue.get('category') or issue_type),
                    'temporal_issue_summary': str(issue.get('summary') or ''),
                    'temporal_issue_status': status or 'open',
                    'left_node_name': str(issue.get('left_node_name') or ''),
                    'right_node_name': str(issue.get('right_node_name') or ''),
                    'fact_ids': list(issue.get('fact_ids') or []),
                    'relative_markers': list(relative_markers),
                    'deterministic_update_key': issue_id or f'{claim_type}:{issue_type}:{target_element_id}',
                    'workflow_phase': 'document_generation' if question_type == 'evidence' else 'graph_analysis',
                    'recommended_resolution_lane': str(issue.get('recommended_resolution_lane') or 'clarify_with_complainant'),
                    'extraction_targets': extraction_targets,
                    'patchability_markers': patchability_markers,
                },
                priority='high' if bool(issue.get('blocking')) or str(issue.get('severity') or '').strip().lower() == 'blocking' else 'medium',
            )
            question_objective = 'identify_supporting_proof' if question_type == 'evidence' else 'establish_chronology'
            question_goal = 'identify_supporting_proof' if question_type == 'evidence' else 'establish_element'
            if issue_type in {
                'retaliation_missing_causation',
                'retaliation_missing_causation_link',
                'retaliation_missing_sequence',
                'retaliation_missing_sequencing_dates',
            }:
                question_objective = 'establish_causation'
            elif question_type == 'responsible_party':
                question_objective = 'identify_responsible_actor'
            question['question_objective'] = question_objective
            question['question_goal'] = question_goal
            ranking_explanation = question.get('ranking_explanation') if isinstance(question.get('ranking_explanation'), dict) else {}
            ranking_explanation['question_objective'] = question_objective
            ranking_explanation['question_goal'] = question_goal
            question['ranking_explanation'] = ranking_explanation
            questions.append(question)

        return questions[:max_questions]

    def _build_history_follow_up_questions(
        self,
        max_questions: int,
    ) -> List[Dict[str, Any]]:
        """Generate follow-up questions from prior low-specificity answers."""
        if max_questions <= 0 or not self.questions_asked:
            return []

        questions: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()
        recent_history = list(reversed(self.questions_asked[-12:]))

        for entry in recent_history:
            if len(questions) >= max_questions:
                break
            if not isinstance(entry, dict):
                continue
            question = entry.get('question')
            question = question if isinstance(question, dict) else {}
            answer_text = str(entry.get('answer') or '').strip()
            if not answer_text:
                continue

            qtype = str(question.get('type') or '').strip().lower()
            needs_confirmation = self._contains_confirmation_placeholder(answer_text)
            retaliation_context = self._contains_retaliation_context(answer_text)
            causation_signal = self._contains_causation_signal(answer_text)
            has_dates = bool(self._extract_date_strings(answer_text))
            has_named_actors = bool(self._extract_named_role_people(answer_text) or self._extract_named_people_with_titles(answer_text))
            has_documents = bool(self._extract_document_mentions(answer_text))
            has_sequence = self._contains_sequence_signal(answer_text)
            response_timings = self._extract_response_timing_phrases(answer_text)
            has_document_precision = self._contains_document_precision_signal(answer_text)
            has_adverse_action = self._contains_adverse_action_signal(answer_text)

            if needs_confirmation:
                follow_ups = [
                    (
                        'timeline',
                        "You noted details that still need confirmation. What is the most specific date (month/day/year) for the event, and who took the action on that date?",
                        {
                            'gap_type': 'missing_exact_action_dates',
                            'follow_up_reason': 'needs_confirmation_placeholder',
                            'workflow_phase': 'graph_analysis',
                            'extraction_targets': ['exact_dates', 'actor_name', 'actor_role', 'event_order'],
                            'patchability_markers': ['chronology_patch_anchor', 'actor_link_patch_anchor'],
                        },
                    ),
                    (
                        'evidence',
                        "Which exact document, message, email, or notice can confirm that event, and what date appears on it?",
                        {
                            'gap_type': 'missing_written_notice',
                            'follow_up_reason': 'needs_confirmation_placeholder',
                            'workflow_phase': 'document_generation',
                            'extraction_targets': ['document_type', 'document_date', 'document_owner'],
                            'patchability_markers': ['support_patch_anchor', 'notice_chain_patch_anchor'],
                        },
                    ),
                ]
                for follow_type, follow_text, follow_context in follow_ups:
                    key = f"{follow_type}:{self._normalize_question_text(follow_text)}"
                    if key in seen_keys or self._already_asked(follow_text):
                        continue
                    seen_keys.add(key)
                    questions.append(self._question_candidate(
                        source='history_follow_up',
                        question_type=follow_type,
                        question_text=follow_text,
                        context=follow_context,
                        priority='high',
                    ))
                    if len(questions) >= max_questions:
                        break

            if len(questions) >= max_questions:
                break

            chronology_gap = (
                qtype in {'timeline', 'responsible_party', 'clarification', 'relationship', 'requirement'}
                and (not has_dates or not has_sequence or not response_timings)
            )
            if chronology_gap and len(questions) < max_questions:
                chronology_text = (
                    "Please list each key event in order with the exact date (month/day/year), "
                    "who acted, and how long it took for the next response after your request or report."
                )
                key = f"timeline:{self._normalize_question_text(chronology_text)}"
                if key not in seen_keys and not self._already_asked(chronology_text):
                    seen_keys.add(key)
                    questions.append(self._question_candidate(
                        source='history_follow_up',
                        question_type='timeline',
                        question_text=chronology_text,
                        context={
                            'gap_type': 'missing_decision_timeline',
                            'follow_up_reason': 'chronology_gap_closeout',
                            'workflow_phase': 'graph_analysis',
                            'extraction_targets': ['exact_dates', 'event_order', 'response_timing', 'actor_name', 'actor_role'],
                            'patchability_markers': ['chronology_patch_anchor', 'chronology_response_patch_anchor', 'actor_link_patch_anchor'],
                        },
                        priority='high',
                    ))

            should_probe_causation = (
                retaliation_context
                and (qtype in {'timeline', 'responsible_party', 'clarification', 'requirement', 'relationship'} or needs_confirmation)
                and (not causation_signal or not has_dates or not has_named_actors)
            )
            if should_probe_causation:
                causation_text = (
                    "Please identify the protected activity, the adverse action, the exact dates for each, "
                    "and why you believe the adverse action happened because of the protected activity."
                )
                decision_actor_text = (
                    "Who specifically made or approved the adverse decision (full name, title, and organization), "
                    "and who communicated it to you?"
                )
                causation_items = [
                    (
                        'timeline',
                        causation_text,
                        {
                            'gap_type': 'retaliation_missing_causation_link',
                            'follow_up_reason': 'retaliation_causation_probe',
                            'workflow_phase': 'graph_analysis',
                            'extraction_targets': ['protected_activity', 'adverse_action', 'exact_dates', 'causation_link'],
                            'patchability_markers': ['chronology_patch_anchor', 'causation_patch_anchor'],
                        },
                    ),
                    (
                        'responsible_party',
                        decision_actor_text,
                        {
                            'gap_type': 'missing_staff_identity',
                            'follow_up_reason': 'retaliation_decision_maker_probe',
                            'workflow_phase': 'graph_analysis',
                            'extraction_targets': ['actor_name', 'actor_role', 'decision_maker'],
                            'patchability_markers': ['actor_link_patch_anchor', 'decision_actor_patch_anchor'],
                        },
                    ),
                ]
                for follow_type, follow_text, follow_context in causation_items:
                    key = f"{follow_type}:{self._normalize_question_text(follow_text)}"
                    if key in seen_keys or self._already_asked(follow_text):
                        continue
                    seen_keys.add(key)
                    questions.append(self._question_candidate(
                        source='history_follow_up',
                        question_type=follow_type,
                        question_text=follow_text,
                        context=follow_context,
                        priority='high',
                    ))
                    if len(questions) >= max_questions:
                        break

            if len(questions) >= max_questions:
                break

            needs_decision_precision = (
                qtype in {'timeline', 'responsible_party', 'relationship', 'clarification', 'requirement'}
                and (not has_named_actors or not has_adverse_action)
            )
            if needs_decision_precision and len(questions) < max_questions:
                decision_precision_text = (
                    "Who exactly made the adverse decision, what was the specific adverse action, "
                    "and what title and organization did that person have at the time?"
                )
                key = f"responsible_party:{self._normalize_question_text(decision_precision_text)}"
                if key not in seen_keys and not self._already_asked(decision_precision_text):
                    seen_keys.add(key)
                    questions.append(self._question_candidate(
                        source='history_follow_up',
                        question_type='responsible_party',
                        question_text=decision_precision_text,
                        context={
                            'gap_type': 'missing_staff_identity',
                            'follow_up_reason': 'decision_precision_closeout',
                            'workflow_phase': 'graph_analysis',
                            'extraction_targets': ['actor_name', 'actor_role', 'decision_maker', 'adverse_action'],
                            'patchability_markers': ['actor_link_patch_anchor', 'decision_actor_patch_anchor', 'adverse_action_patch_anchor'],
                        },
                        priority='high',
                    ))

            if len(questions) >= max_questions:
                break

            # Ask for concrete documentary anchors if narrative detail exists but sources are absent.
            if (retaliation_context or needs_confirmation or chronology_gap) and (not has_documents or not has_document_precision) and len(questions) < max_questions:
                doc_text = (
                    "What exact document or message records the decision (document type, date, sender, recipient, and how it was delivered)?"
                )
                key = f"evidence:{self._normalize_question_text(doc_text)}"
                if key not in seen_keys and not self._already_asked(doc_text):
                    seen_keys.add(key)
                    questions.append(self._question_candidate(
                        source='history_follow_up',
                        question_type='evidence',
                        question_text=doc_text,
                        context={
                            'gap_type': 'missing_written_notice',
                            'follow_up_reason': 'document_anchor_probe',
                            'workflow_phase': 'document_generation',
                            'extraction_targets': ['document_type', 'document_date', 'document_owner', 'actor_name', 'actor_role'],
                            'patchability_markers': ['support_patch_anchor', 'notice_chain_patch_anchor', 'decision_actor_patch_anchor', 'documentary_artifact_patch_anchor'],
                        },
                        priority='high',
                    ))

        return questions[:max_questions]

    def collect_question_candidates(
        self,
        knowledge_graph: KnowledgeGraph,
        dependency_graph: DependencyGraph,
        max_questions: int = 10,
        intake_case_file: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Collect ranked question candidates before final rendering/exploration."""
        questions: List[Dict[str, Any]] = []

        contradiction_questions = self._build_contradiction_questions(dependency_graph, max_questions)
        questions.extend(contradiction_questions)

        claim_element_questions = self._build_claim_element_questions(
            intake_case_file,
            max(0, max_questions - len(questions)),
        )
        questions.extend(claim_element_questions[:max(0, max_questions - len(questions))])

        proof_lead_questions = self._build_proof_lead_questions(
            intake_case_file,
            max(0, max_questions - len(questions)),
        )
        questions.extend(proof_lead_questions[:max(0, max_questions - len(questions))])

        temporal_gap_questions = self._build_claim_temporal_gap_questions(
            intake_case_file,
            max(0, max_questions - len(questions)),
        )
        questions.extend(temporal_gap_questions[:max(0, max_questions - len(questions))])

        history_follow_up_questions = self._build_history_follow_up_questions(
            max(0, max_questions - len(questions)),
        )
        questions.extend(history_follow_up_questions[:max(0, max_questions - len(questions))])

        kg_gaps = knowledge_graph.find_gaps()
        for gap in kg_gaps[:max(0, max_questions - len(questions))]:
            if gap['type'] == 'low_confidence_entity':
                questions.append(self._question_candidate(
                    source='knowledge_graph_gap',
                    question_type='clarification',
                    question_text=gap['suggested_question'],
                    context={
                        'entity_id': gap['entity_id'],
                        'entity_name': gap['entity_name'],
                        'confidence': gap['confidence']
                    },
                    priority='medium',
                ))
            elif gap['type'] == 'unsupported_claim':
                questions.append(self._question_candidate(
                    source='knowledge_graph_gap',
                    question_type='evidence',
                    question_text=gap['suggested_question'],
                    context={
                        'claim_id': gap['entity_id'],
                        'claim_name': gap['claim_name']
                    },
                    priority='high',
                ))
            elif gap['type'] == 'isolated_entity':
                questions.append(self._question_candidate(
                    source='knowledge_graph_gap',
                    question_type='relationship',
                    question_text=gap['suggested_question'],
                    context={
                        'entity_id': gap['entity_id'],
                        'entity_name': gap['entity_name']
                    },
                    priority='low',
                ))
            elif gap['type'] == 'missing_timeline':
                questions.append(self._question_candidate(
                    source='knowledge_graph_gap',
                    question_type='timeline',
                    question_text=gap['suggested_question'],
                    context={},
                    priority='high',
                ))
            elif gap['type'] == 'missing_responsible_party':
                questions.append(self._question_candidate(
                    source='knowledge_graph_gap',
                    question_type='responsible_party',
                    question_text=gap['suggested_question'],
                    context={},
                    priority='high',
                ))
            elif gap['type'] == 'missing_impact_remedy':
                questions.append(self._question_candidate(
                    source='knowledge_graph_gap',
                    question_type='impact',
                    question_text=gap['suggested_question'],
                    context={
                        'missing_impact': gap.get('missing_impact'),
                        'missing_remedy': gap.get('missing_remedy'),
                        'gap_type': gap.get('type'),
                    },
                    priority='high',
                ))
            elif gap['type'] in {'missing_written_notice', 'missing_response_dates'}:
                questions.append(self._question_candidate(
                    source='knowledge_graph_gap',
                    question_type='evidence',
                    question_text=gap['suggested_question'],
                    context={'gap_type': gap.get('type')},
                    priority='high',
                ))
            elif gap['type'] in {'missing_hearing_request_date', 'missing_decision_timeline', 'missing_exact_action_dates'}:
                questions.append(self._question_candidate(
                    source='knowledge_graph_gap',
                    question_type='timeline',
                    question_text=gap['suggested_question'],
                    context={'gap_type': gap.get('type')},
                    priority='high',
                ))
            elif gap['type'] in {'missing_staff_identity', 'missing_staff_title'}:
                questions.append(self._question_candidate(
                    source='knowledge_graph_gap',
                    question_type='responsible_party',
                    question_text=gap['suggested_question'],
                    context={'gap_type': gap.get('type')},
                    priority='high',
                ))
            elif gap['type'] in {'retaliation_missing_causation', 'retaliation_missing_causation_link', 'retaliation_missing_sequencing_dates'}:
                questions.append(self._question_candidate(
                    source='knowledge_graph_gap',
                    question_type='timeline',
                    question_text=gap['suggested_question'],
                    context={'gap_type': gap.get('type')},
                    priority='high',
                ))

        unsatisfied = dependency_graph.find_unsatisfied_requirements()
        for req in unsatisfied[:max(0, max_questions - len(questions))]:
            missing_deps = req.get('missing_dependencies', [])
            for dep in missing_deps[:2]:
                questions.append(self._question_candidate(
                    source='dependency_graph_requirement',
                    question_type='requirement',
                    question_text=f"To support the claim '{req['node_name']}', can you provide information about: {dep['source_name']}?",
                    context={
                        'claim_id': req['node_id'],
                        'claim_name': req['node_name'],
                        'requirement_id': dep['source_node_id'],
                        'requirement_name': dep['source_name']
                    },
                    priority='high',
                ))
                if len(questions) >= max_questions:
                    break
            if len(questions) >= max_questions:
                break

        blocker_issues = []
        if hasattr(dependency_graph, 'get_blocker_follow_up_issues'):
            try:
                blocker_issues = dependency_graph.get_blocker_follow_up_issues()
            except Exception:
                blocker_issues = []
        for issue in blocker_issues[:max(0, max_questions - len(questions))]:
            if not isinstance(issue, dict):
                continue
            questions.append(self._question_candidate(
                source='dependency_graph_requirement',
                question_type=str(issue.get('question_type') or 'timeline'),
                question_text=str(issue.get('suggested_question') or 'Can you provide the missing follow-up details for this blocker?'),
                context={
                    'issue_id': issue.get('issue_id'),
                    'issue_type': issue.get('issue_type'),
                    'node_id': issue.get('node_id'),
                    'node_name': issue.get('node_name'),
                    'gap_type': issue.get('issue_type'),
                    'recommended_resolution_lane': issue.get('recommended_resolution_lane'),
                    'workflow_phase': issue.get('workflow_phase'),
                    'workflow_phase_rank': issue.get('workflow_phase_rank'),
                    'extraction_targets': list(issue.get('extraction_targets') or []),
                    'patchability_markers': list(issue.get('patchability_markers') or []),
                },
                priority='high' if str(issue.get('severity') or '').lower() == 'blocking' else 'medium',
            ))
            if len(questions) >= max_questions:
                break

        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        questions.sort(
            key=lambda q: (
                int(q.get('proof_priority', self._phase1_proof_priority(q.get('type', '')))),
                priority_order.get(q.get('priority', 'low'), 3),
            )
        )
        return questions[:max_questions]

    def _default_candidate_sort_key(self, candidate: Dict[str, Any]) -> Tuple[int, int, int]:
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        if not isinstance(candidate, dict):
            return (99, 99, 99)
        return (
            int(candidate.get('proof_priority', self._phase1_proof_priority(candidate.get('type', '')))),
            priority_order.get(candidate.get('priority', 'low'), 3),
            int(candidate.get('workflow_phase_rank', 99) or 99),
        )

    def _actor_score_candidate(self, candidate: Dict[str, Any]) -> float:
        if not isinstance(candidate, dict):
            return 0.0
        priority_map = {'high': 3.0, 'medium': 2.0, 'low': 1.0}
        blocking_map = {'blocking': 3.0, 'important': 2.0, 'informational': 1.0}
        qtype = str(candidate.get('type') or '').strip().lower()
        question_text = str(candidate.get('question') or '').strip().lower()
        follow_up_tags = [str(tag).strip().lower() for tag in (candidate.get('follow_up_tags') or []) if str(tag).strip()]
        extraction_targets = [str(target).strip().lower() for target in (candidate.get('extraction_targets') or []) if str(target).strip()]
        workflow_phase = str(candidate.get('workflow_phase') or '').strip().lower()
        patchability_markers = [str(marker).strip().lower() for marker in (candidate.get('patchability_markers') or []) if str(marker).strip()]
        proof_priority = int(candidate.get('proof_priority', self._phase1_proof_priority(qtype)) or 0)
        blocking_level = str(candidate.get('blocking_level') or '').strip().lower()
        score = 0.0
        score += max(0.0, 8.0 - float(proof_priority))
        score += priority_map.get(str(candidate.get('priority') or 'low').strip().lower(), 1.0)
        score += blocking_map.get(blocking_level, 0.0)
        if qtype in {'timeline', 'contradiction', 'responsible_party', 'requirement'}:
            score += 1.5
        if qtype == 'contradiction':
            # Preserve contradiction-first behavior for clearly conflicting records.
            score += 6.5
        if any(token in question_text for token in ('when', 'date', 'timeline', 'chronology', 'anchor')):
            score += 1.25
        if any(token in question_text for token in ('who', 'actor', 'manager', 'supervisor', 'organization')):
            score += 1.25
        if any(token in question_text for token in ('protected activity', 'adverse', 'retaliation', 'because', 'after')):
            score += 1.25
        if 'exact_dates' in follow_up_tags:
            score += 1.5
        if 'staff_identity' in follow_up_tags:
            score += 1.5
        if 'notice_chain' in follow_up_tags:
            score += 1.0
        if 'retaliation_sequence' in follow_up_tags:
            score += 2.0
        if 'chronology_gap' in follow_up_tags:
            score += 1.8
        if 'decision_precision' in follow_up_tags:
            score += 1.8
        if 'documentary_precision' in follow_up_tags:
            score += 1.4
        if 'response_timing' in follow_up_tags:
            score += 1.4
        if extraction_targets:
            score += min(2.0, 0.4 * float(len(extraction_targets)))
        if patchability_markers:
            score += min(1.5, 0.5 * float(len(patchability_markers)))
        score += max(0.0, 2.0 - float(self._phase_focus_rank(workflow_phase)) * 0.5)

        score += float(self.question_quality_weight) * float(self._question_quality_bonus_candidate(candidate))
        score += float(self.empathy_weight) * float(self._empathy_bonus_candidate(candidate))

        asked_count_for_type = sum(
            1
            for asked in self.questions_asked
            if isinstance(asked, dict)
            and isinstance(asked.get('question'), dict)
            and str(asked.get('question', {}).get('type') or '').strip().lower() == qtype
        )
        if asked_count_for_type == 0:
            score += 0.75
        elif asked_count_for_type >= 3:
            score -= 0.5
        return score

    def _critic_penalty_candidate(self, candidate: Dict[str, Any]) -> float:
        if not isinstance(candidate, dict):
            return 0.0
        qtype = str(candidate.get('type') or '').strip().lower()
        question_text = str(candidate.get('question') or '').strip().lower()
        context = candidate.get('context') if isinstance(candidate.get('context'), dict) else {}
        follow_up_tags = [str(tag).strip().lower() for tag in (candidate.get('follow_up_tags') or []) if str(tag).strip()]
        extraction_targets = [str(target).strip().lower() for target in (candidate.get('extraction_targets') or []) if str(target).strip()]
        workflow_phase = str(candidate.get('workflow_phase') or '').strip().lower()
        penalty = 0.0
        if not question_text:
            return 5.0
        generic_phrases = (
            "can you provide more details",
            "additional information",
            "this claim",
            "this evidence",
        )
        if any(phrase in question_text for phrase in generic_phrases):
            penalty += 1.25
        if len(question_text) < 35:
            penalty += 0.5
        if len(question_text) > 280:
            penalty += 0.5
        if question_text and not question_text.endswith('?'):
            penalty += 0.4
        if not context:
            penalty += 0.5
        if (
            ('retaliation' in question_text or 'protected activity' in question_text)
            and not any(token in question_text for token in ('when', 'date', 'who'))
        ):
            penalty += 1.0
        if 'exact_dates' in follow_up_tags and not any(token in question_text for token in ('exact date', 'on what date', 'what date', 'when')):
            penalty += 1.0
        if 'staff_identity' in follow_up_tags and not any(token in question_text for token in ('full name', 'title', 'role', 'who')):
            penalty += 1.0
        if 'retaliation_sequence' in follow_up_tags and not any(token in question_text for token in ('protected activity', 'adverse', 'because', 'after')):
            penalty += 1.0
        if 'chronology_gap' in follow_up_tags and not any(token in question_text for token in ('exact date', 'before', 'after', 'sequence', 'how long', 'response')):
            penalty += 1.1
        if 'decision_precision' in follow_up_tags and not any(token in question_text for token in ('who exactly', 'full name', 'title', 'organization', 'adverse action')):
            penalty += 1.1
        if 'documentary_precision' in follow_up_tags and not any(token in question_text for token in ('document type', 'date', 'sender', 'recipient', 'delivered')):
            penalty += 1.1
        if 'response_timing' in follow_up_tags and not any(token in question_text for token in ('how long', 'within', 'response', 'responded')):
            penalty += 1.1
        if question_text.count('?') > 1:
            penalty += 0.4
        if workflow_phase == 'graph_analysis' and not any(token in question_text for token in ('when', 'date', 'who', 'what happened')):
            penalty += 0.6
        if workflow_phase == 'document_generation' and not any(token in question_text for token in ('document', 'notice', 'letter', 'email', 'record', 'message')):
            penalty += 0.6
        if qtype in {'timeline', 'contradiction', 'responsible_party', 'impact', 'remedy'}:
            empathy_openers = (
                "to make sure i understand, ",
                "i know this may be stressful, and this helps keep your record accurate: ",
                "so we can support your claim clearly, ",
                "thanks for sharing this. ",
                "i hear you. ",
            )
            if not question_text.startswith(empathy_openers):
                penalty += 0.45
        if extraction_targets and not any(token in question_text for token in ('who', 'when', 'date', 'name', 'title', 'document', 'notice', 'record', 'because', 'after')):
            penalty += 0.5
        return penalty

    def _coverage_adjustment(
        self,
        candidate: Dict[str, Any],
        *,
        type_counts: Dict[str, int],
        phase_counts: Dict[str, int],
    ) -> float:
        if not isinstance(candidate, dict):
            return 0.0
        qtype = str(candidate.get('type') or '').strip().lower()
        workflow_phase = str(candidate.get('workflow_phase') or '').strip().lower()
        type_count = int(type_counts.get(qtype, 0))
        phase_count = int(phase_counts.get(workflow_phase, 0))
        bonus = 0.0
        if type_count <= 1:
            bonus += 0.5
        elif type_count >= 4:
            bonus -= 0.5
        if phase_count <= 1:
            bonus += 0.35
        elif phase_count >= 4:
            bonus -= 0.35
        phase_rank = self._phase_focus_rank(workflow_phase)
        if phase_rank == 0:
            bonus += 0.5
        elif phase_rank == 1:
            bonus += 0.25
        elif phase_rank == 2:
            bonus += 0.1
        return bonus

    def _annotate_actor_critic_scores(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        type_counts: Dict[str, int] = {}
        phase_counts: Dict[str, int] = {}
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            qtype = str(candidate.get('type') or '').strip().lower()
            phase = str(candidate.get('workflow_phase') or '').strip().lower()
            if qtype:
                type_counts[qtype] = type_counts.get(qtype, 0) + 1
            if phase:
                phase_counts[phase] = phase_counts.get(phase, 0) + 1

        annotated: List[Dict[str, Any]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            enriched = dict(candidate)
            actor_score = self._actor_score_candidate(enriched)
            critic_penalty = self._critic_penalty_candidate(enriched)
            coverage_adjustment = self._coverage_adjustment(
                enriched,
                type_counts=type_counts,
                phase_counts=phase_counts,
            )
            actor_critic_score = (
                float(self.actor_weight) * actor_score
                - float(self.critic_weight) * critic_penalty
                + float(coverage_adjustment)
            )
            enriched['actor_score'] = float(actor_score)
            enriched['critic_penalty'] = float(critic_penalty)
            enriched['coverage_adjustment'] = float(coverage_adjustment)
            enriched['actor_critic_score'] = float(actor_critic_score)
            explanation = (
                dict(enriched.get('ranking_explanation', {}))
                if isinstance(enriched.get('ranking_explanation'), dict)
                else {}
            )
            explanation['actor_score'] = float(actor_score)
            explanation['critic_penalty'] = float(critic_penalty)
            explanation['coverage_adjustment'] = float(coverage_adjustment)
            explanation['actor_critic_score'] = float(actor_critic_score)
            enriched['ranking_explanation'] = explanation
            annotated.append(enriched)
        return annotated

    def _is_low_quality_selected_candidate(
        self,
        candidate: Dict[str, Any],
        *,
        pool_score_floor: float,
    ) -> bool:
        if not isinstance(candidate, dict):
            return True
        score = float(candidate.get('actor_critic_score', 0.0) or 0.0)
        critic_penalty = float(candidate.get('critic_penalty', 0.0) or 0.0)
        text = str(candidate.get('question') or '').strip()
        extraction_targets = list(candidate.get('extraction_targets') or [])
        patchability_markers = list(candidate.get('patchability_markers') or [])
        if not text:
            return True
        if score < pool_score_floor and critic_penalty > 2.25:
            return True
        if len(text) < 24:
            return True
        if not extraction_targets and not patchability_markers and critic_penalty > 2.0:
            return True
        return False

    def select_question_candidates(
        self,
        candidates: List[Dict[str, Any]],
        *,
        max_questions: int = 10,
        selector: Any = None,
    ) -> List[Dict[str, Any]]:
        """Select final question candidates, allowing a router/prover override."""
        normalized_candidates = [candidate for candidate in (candidates or []) if isinstance(candidate, dict)]
        if not normalized_candidates or max_questions <= 0:
            return []
        normalized_candidates = self._annotate_actor_critic_scores(normalized_candidates)

        def _finalize(items: Any, *, dedupe: bool) -> List[Dict[str, Any]]:
            normalized_items = [candidate for candidate in (items or []) if isinstance(candidate, dict)]
            if not dedupe:
                return normalized_items[:max_questions]
            seen_keys = set()
            finalized: List[Dict[str, Any]] = []
            for candidate in normalized_items:
                candidate_key = (
                    self._normalize_question_text(str(candidate.get('question', ''))),
                    str(candidate.get('type', '')).strip().lower(),
                )
                if candidate_key in seen_keys:
                    continue
                seen_keys.add(candidate_key)
                finalized.append(candidate)
                if len(finalized) >= max_questions:
                    break
            return finalized

        selected: Any = None
        if callable(selector):
            try:
                selected = selector(normalized_candidates, max_questions=max_questions)
            except TypeError:
                selected = selector(normalized_candidates)
            except Exception:
                selected = None

        if isinstance(selected, list):
            normalized_selected = _finalize(selected, dedupe=True)
            if normalized_selected:
                if self.selector_quality_guard_enabled:
                    normalized_selected = self._annotate_actor_critic_scores(normalized_selected)
                if len(normalized_selected) >= max_questions:
                    if not self.selector_quality_guard_enabled:
                        return normalized_selected[:max_questions]
                    pool_scores = [
                        float(candidate.get('actor_critic_score', 0.0) or 0.0)
                        for candidate in normalized_candidates
                    ]
                    if pool_scores:
                        sorted_pool_scores = sorted(pool_scores, reverse=True)
                        anchor_index = min(len(sorted_pool_scores) - 1, max(0, max_questions - 1))
                        pool_score_floor = float(sorted_pool_scores[anchor_index]) - 0.75
                    else:
                        pool_score_floor = -999.0
                    selected_keys = {
                        (
                            self._normalize_question_text(str(candidate.get('question', ''))),
                            str(candidate.get('type', '')).strip().lower(),
                        )
                        for candidate in normalized_selected
                    }
                    fallback_candidates = [
                        candidate for candidate in normalized_candidates
                        if (
                            self._normalize_question_text(str(candidate.get('question', ''))),
                            str(candidate.get('type', '')).strip().lower(),
                        ) not in selected_keys
                    ]
                    fallback_candidates.sort(
                        key=lambda candidate: (
                            -float(candidate.get('actor_critic_score', 0.0) or 0.0),
                            self._default_candidate_sort_key(candidate),
                        )
                    )
                    replacement_queue = list(fallback_candidates)
                    upgraded_selected: List[Dict[str, Any]] = []
                    for candidate in normalized_selected[:max_questions]:
                        if self._is_low_quality_selected_candidate(candidate, pool_score_floor=pool_score_floor) and replacement_queue:
                            upgraded_selected.append(replacement_queue.pop(0))
                        else:
                            upgraded_selected.append(candidate)
                    return _finalize(upgraded_selected, dedupe=True)
                selected_keys = {
                    (
                        self._normalize_question_text(str(candidate.get('question', ''))),
                        str(candidate.get('type', '')).strip().lower(),
                    )
                    for candidate in normalized_selected
                }
                fallback_candidates = [
                    candidate for candidate in normalized_candidates
                    if (
                        self._normalize_question_text(str(candidate.get('question', ''))),
                        str(candidate.get('type', '')).strip().lower(),
                    ) not in selected_keys
                ]
                fallback_candidates.sort(
                    key=lambda candidate: (
                        -float(candidate.get('actor_critic_score', 0.0) or 0.0),
                        self._default_candidate_sort_key(candidate),
                    )
                )
                return _finalize(normalized_selected + fallback_candidates, dedupe=True)

        if self.actor_critic_enabled:
            normalized_candidates.sort(
                key=lambda candidate: (
                    -float(candidate.get('actor_critic_score', 0.0) or 0.0),
                    self._default_candidate_sort_key(candidate),
                )
            )
        else:
            normalized_candidates.sort(key=self._default_candidate_sort_key)
        return _finalize(normalized_candidates, dedupe=True)

    def _ensure_standard_intake_questions(self, questions: List[Dict[str, Any]], max_questions: int) -> List[Dict[str, Any]]:
        if len(questions) >= max_questions:
            return questions

        existing_text = " ".join([q.get('question', '') for q in questions]).lower()
        added: List[Dict[str, Any]] = []

        timeline_text = (
            'What is the timeline of key events, including dates, who made each decision, what notice or communication you received, and when you requested help or accommodation?'
        )
        if len(questions) + len(added) < max_questions:
            if not any(q.get('type') == 'timeline' for q in questions) and not any(k in existing_text for k in ['timeline', 'when did', 'what date', 'dates', 'notice', 'who made']):
                if not self._already_asked(timeline_text):
                    added.append(self._question_candidate(
                        source='standard_intake_backstop',
                        question_type='timeline',
                        question_text=timeline_text,
                        context={},
                        priority='high',
                    ))

        impact_text = (
            'What harm did you experience (financial, emotional, professional), what outcome or remedy are you seeking, and what notices, letters, or messages document that harm?'
        )
        if len(questions) + len(added) < max_questions:
            if not any(q.get('type') in {'impact', 'remedy'} for q in questions) and not any(k in existing_text for k in ['harm', 'damages', 'remedy', 'seeking', 'notice', 'letter', 'message']):
                if not self._already_asked(impact_text):
                    added.append(self._question_candidate(
                        source='standard_intake_backstop',
                        question_type='impact',
                        question_text=impact_text,
                        context={},
                        priority='high',
                    ))

            notice_text = (
                "What exact notice, letter, email, or message did you receive, on what date, and who sent it?"
            )
            if len(questions) + len(added) < max_questions:
                if not any(q.get('type') == 'evidence' for q in questions) and not any(k in existing_text for k in ['notice', 'letter', 'email', 'message', 'sent it']):
                    if not self._already_asked(notice_text):
                        added.append(self._question_candidate(
                            source='standard_intake_backstop',
                            question_type='evidence',
                            question_text=notice_text,
                            context={},
                            priority='high',
                        ))

        if not added:
            return questions

        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        combined = questions + added
        combined.sort(
            key=lambda q: (
                int(q.get('proof_priority', self._phase1_proof_priority(q.get('type', '')))),
                priority_order.get(q.get('priority', 'low'), 3),
            )
        )
        return combined[:max_questions]

    def _make_question_recommendation_id(
        self,
        claim_type: str,
        lane: str,
        target_claim_element_id: str,
        question_text: str,
    ) -> str:
        normalized_claim = re.sub(r'[^a-z0-9]+', '_', (claim_type or 'claim').lower()).strip('_') or 'claim'
        digest = hashlib.sha1(
            f"{normalized_claim}|{lane}|{target_claim_element_id}|{question_text}".encode('utf-8')
        ).hexdigest()[:12]
        return f"question:{normalized_claim}:{digest}"

    def _build_review_question_recommendation(
        self,
        *,
        claim_type: str,
        lane: str,
        target_claim_element_id: str,
        target_claim_element_text: str,
        question_text: str,
        question_reason: str,
        expected_proof_gain: str,
        supporting_evidence_summary: str,
        current_status: str,
        missing_support_kinds: Optional[List[str]] = None,
        contradiction_fact_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized_text = self._with_empathy(question_text, lane)
        return {
            'question_id': self._make_question_recommendation_id(
                claim_type,
                lane,
                target_claim_element_id,
                normalized_text,
            ),
            'question_text': normalized_text,
            'target_claim_type': claim_type,
            'target_claim_element_id': target_claim_element_id,
            'target_claim_element_text': target_claim_element_text,
            'question_lane': lane,
            'question_reason': question_reason,
            'expected_proof_gain': expected_proof_gain,
            'supporting_evidence_summary': supporting_evidence_summary,
            'current_status': current_status,
            'missing_support_kinds': list(missing_support_kinds or []),
            'contradiction_fact_ids': list(contradiction_fact_ids or []),
            'suppression_key': self._normalize_question_text(normalized_text),
        }

    def generate_review_question_recommendations(
        self,
        claim_type: str,
        gap_claim: Optional[Dict[str, Any]] = None,
        contradiction_claim: Optional[Dict[str, Any]] = None,
        max_questions: int = 6,
    ) -> List[Dict[str, Any]]:
        recommendations: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()
        normalized_claim_type = (claim_type or 'claim').strip() or 'claim'

        contradiction_candidates = []
        if isinstance(contradiction_claim, dict):
            contradiction_candidates = contradiction_claim.get('candidates', []) or []
        for candidate in contradiction_candidates:
            if not isinstance(candidate, dict):
                continue
            element_id = str(candidate.get('claim_element_id') or '')
            element_text = str(candidate.get('claim_element_text') or element_id or 'this element')
            overlap_terms = list(candidate.get('overlap_terms', []) or [])
            overlap_snippet = ', '.join(overlap_terms[:3]) if overlap_terms else 'the current support record'
            recommendation = self._build_review_question_recommendation(
                claim_type=normalized_claim_type,
                lane='contradiction_resolution',
                target_claim_element_id=element_id,
                target_claim_element_text=element_text,
                question_text=(
                    f"The current support for {element_text} conflicts. Which version is correct, "
                    "and what source best supports it?"
                ),
                question_reason=(
                    f"Resolve a contradiction before collecting more support for {element_text}. "
                    f"The conflicting records overlap on {overlap_snippet}."
                ),
                expected_proof_gain='high',
                supporting_evidence_summary=(
                    f"Conflicting facts: {len(candidate.get('fact_ids', []) or [])}"
                ),
                current_status='contradicted',
                contradiction_fact_ids=candidate.get('fact_ids', []),
            )
            if recommendation['suppression_key'] in seen_keys:
                continue
            seen_keys.add(recommendation['suppression_key'])
            recommendations.append(recommendation)
            if len(recommendations) >= max_questions:
                return recommendations[:max_questions]

        unresolved_elements = []
        if isinstance(gap_claim, dict):
            unresolved_elements = gap_claim.get('unresolved_elements', []) or []
        for element in unresolved_elements:
            if not isinstance(element, dict):
                continue
            element_id = str(element.get('element_id') or '')
            element_text = str(element.get('element_text') or element_id or 'this element')
            status = str(element.get('status') or 'missing')
            missing_support_kinds = [
                str(kind) for kind in (element.get('missing_support_kinds', []) or []) if kind
            ]
            total_links = int(element.get('total_links', 0) or 0)
            fact_count = int(element.get('fact_count', 0) or 0)
            recommended_action = str(element.get('recommended_action') or '')

            lane = 'testimony'
            if recommended_action == 'improve_parse_quality':
                lane = 'document_request'
            elif missing_support_kinds == ['authority']:
                lane = 'authority_clarification'
            elif 'evidence' in missing_support_kinds or total_links == 0 or fact_count == 0:
                lane = 'testimony'
            elif 'authority' in missing_support_kinds:
                lane = 'authority_clarification'

            if lane == 'document_request':
                question_text = f"Do you have a document, message, timeline, or record that supports {element_text}?"
                question_reason = (
                    f"{element_text} has some support, but the current records indicate a parse or source-quality gap."
                )
            elif lane == 'authority_clarification':
                question_text = f"Is there a rule, policy, statute, or case that clearly supports {element_text}?"
                question_reason = (
                    f"{element_text} is still missing authority support needed for legal review."
                )
            else:
                question_text = f"What specific facts can you provide to support {element_text}?"
                question_reason = (
                    f"{element_text} is unresolved and needs clearer testimony or factual detail."
                )

            recommendation = self._build_review_question_recommendation(
                claim_type=normalized_claim_type,
                lane=lane,
                target_claim_element_id=element_id,
                target_claim_element_text=element_text,
                question_text=question_text,
                question_reason=question_reason,
                expected_proof_gain='high' if status == 'missing' else 'medium',
                supporting_evidence_summary=(
                    f"Current support: {total_links} links, {fact_count} facts"
                    + (f"; missing {', '.join(missing_support_kinds)}" if missing_support_kinds else '')
                ),
                current_status=status,
                missing_support_kinds=missing_support_kinds,
            )
            if recommendation['suppression_key'] in seen_keys:
                continue
            seen_keys.add(recommendation['suppression_key'])
            recommendations.append(recommendation)
            if len(recommendations) >= max_questions:
                break

        return recommendations[:max_questions]
    
    def generate_questions(self, 
                          knowledge_graph: KnowledgeGraph,
                          dependency_graph: DependencyGraph,
                          max_questions: int = 10,
                          intake_case_file: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Generate questions to denoise the complaint.
        
        Args:
            knowledge_graph: Current knowledge graph
            dependency_graph: Current dependency graph
            max_questions: Maximum number of questions to generate
            
        Returns:
            List of question dictionaries with type, question text, and context
        """
        questions = self.collect_question_candidates(
            knowledge_graph,
            dependency_graph,
            max_questions=max_questions,
            intake_case_file=intake_case_file,
        )
        selector = getattr(self.mediator, 'select_intake_question_candidates', None) if self.mediator else None
        questions = self.select_question_candidates(
            questions,
            max_questions=max_questions,
            selector=selector,
        )

        # Ensure we cover basic intake dimensions beyond evidence-only prompts.
        questions = self._ensure_standard_intake_questions(questions, max_questions)

        # Optional exploration/momentum policy (reorders questions only).
        questions = self._apply_exploration_and_momentum(questions)

        # Light empathy / framing tweaks (text-only; doesn't change structure).
        for q in questions:
            qtype = q.get('type', '')
            qtext = q.get('question', '')
            q['question'] = self._with_empathy(qtext, qtype)
        
        # Track questions in pool
        self.questions_pool.extend(questions[:max_questions])
        
        return questions[:max_questions]
    
    def process_answer(self, question: Dict[str, Any], answer: str,
                      knowledge_graph: KnowledgeGraph,
                      dependency_graph: Optional[DependencyGraph] = None) -> Dict[str, Any]:
        """
        Process an answer to a denoising question.

        Args:
            question: The question that was asked
            answer: The user's answer
            knowledge_graph: Knowledge graph to update
            dependency_graph: Optional dependency graph to update

        Returns:
            Information about what was updated
        """
        self.questions_asked.append({
            'question': question,
            'answer': answer
        })

        updates = {
            'entities_updated': 0,
            'relationships_added': 0,
            'requirements_satisfied': 0
        }

        question_type = str(question.get('type') or '').strip().lower()
        context = question.get('context', {})
        context = context if isinstance(context, dict) else {}
        answer_text = str(answer or '').strip()
        workflow_phase = str(
            context.get('workflow_phase')
            or question.get('workflow_phase')
            or self._workflow_phase_for_question(question_type, context, str(question.get('candidate_source') or ''))
        ).strip().lower()
        question_objective = str(
            question.get('question_objective')
            or context.get('question_objective')
            or ''
        ).strip().lower()
        expected_update_kind = str(
            question.get('expected_update_kind')
            or context.get('expected_update_kind')
            or ''
        ).strip().lower()
        target_element_id = str(
            question.get('target_element_id')
            or context.get('target_element_id')
            or context.get('requirement_id')
            or ''
        ).strip().lower()
        extraction_targets = {
            str(item).strip().lower()
            for item in (
                context.get('extraction_targets')
                or question.get('extraction_targets')
                or []
            )
            if str(item).strip()
        }
        patchability_markers = {
            str(item).strip().lower()
            for item in (
                context.get('patchability_markers')
                or question.get('patchability_markers')
                or []
            )
            if str(item).strip()
        }
        timeline_enrichment_types = {'clarification', 'evidence', 'impact', 'relationship', 'remedy', 'requirement', 'responsible_party', 'timeline'}
        responsible_party_enrichment_types = {'clarification', 'evidence', 'relationship', 'requirement', 'responsible_party', 'timeline'}
        fallback_timeline_fact_types = {'clarification', 'evidence', 'relationship', 'requirement', 'responsible_party', 'timeline'}
        low_information_tokens = {
            '', 'n/a', 'na', 'none', 'unknown', 'not sure', 'unsure', 'no idea', 'i do not know', "i don't know",
        }
        gap_type = str(context.get('gap_type') or '').strip().lower()
        answer_contract = context.get('answer_contract') if isinstance(context.get('answer_contract'), dict) else {}
        contract_required_fields = [
            str(field).strip().lower()
            for field in (
                answer_contract.get('required_fields')
                or context.get('required_fields')
                or []
            )
            if str(field).strip()
        ]
        contract_required_fields = list(dict.fromkeys(contract_required_fields))
        contract_missing_required_fields = {
            str(field).strip().lower()
            for field in (
                answer_contract.get('missing_required_fields')
                or context.get('missing_required_fields')
                or []
            )
            if str(field).strip()
        }
        contract_requirement_updates = {
            str(field).strip().lower()
            for field in (
                answer_contract.get('requirement_updates')
                or context.get('requirement_updates')
                or []
            )
            if str(field).strip()
        }
        contract_entity_updates = {
            str(field).strip().lower()
            for field in (
                answer_contract.get('entity_updates')
                or context.get('entity_updates')
                or []
            )
            if str(field).strip()
        }
        contract_relationship_updates = {
            str(field).strip().lower()
            for field in (
                answer_contract.get('relationship_updates')
                or context.get('relationship_updates')
                or []
            )
            if str(field).strip()
        }
        contract_single_turn_closable = bool(
            answer_contract.get('single_turn_closable')
            or context.get('single_turn_closable')
        )
        contract_single_field_closable = bool(
            answer_contract.get('single_field_closable')
            or context.get('single_field_closable')
        )
        contract_deterministically_closable = bool(
            answer_contract.get('deterministically_closable')
            or context.get('deterministically_closable')
        )
        deterministic_requirement_tokens_updated: Set[str] = set()
        deterministic_relationship_tokens_updated: Set[str] = set()
        deterministic_entity_tokens_updated: Set[str] = set()
        deterministic_plan_fields_captured: Set[str] = set()
        expected_modalities = {
            str(item).strip().lower()
            for item in (context.get('expected_evidence_modalities') or [])
            if str(item).strip()
        }
        weak_modalities = {
            str(item).strip().lower()
            for item in (context.get('weak_evidence_modalities') or [])
            if str(item).strip()
        }
        answer_lower = answer_text.lower()
        extracted_dates = self._extract_date_strings(answer_text)
        response_timing_phrases = self._extract_response_timing_phrases(answer_text)
        document_mentions = self._extract_document_mentions(answer_text)
        named_role_people = self._extract_named_role_people(answer_text)
        named_title_people = self._extract_named_people_with_titles(answer_text)
        org_candidates = self._extract_org_candidates(answer_text)
        generic_roles = self._extract_generic_roles(answer_text)
        has_sequence_signal = self._contains_sequence_signal(answer_text)
        has_causation_signal = self._contains_causation_signal(answer_text)
        has_adverse_action_signal = self._contains_adverse_action_signal(answer_text)
        has_document_precision_signal = self._contains_document_precision_signal(answer_text)
        deterministic_fields_updated: Set[str] = set()

        def _extract_contextual_dates(text_value: str) -> Dict[str, List[str]]:
            buckets: Dict[str, List[str]] = {
                'hearing_request_dates': [],
                'response_dates': [],
                'adverse_action_dates': [],
                'protected_activity_dates': [],
                'decision_dates': [],
                'document_dates': [],
            }
            if not text_value:
                return buckets
            segments = re.split(r'(?<=[.!?;])\s+|\n+', text_value)
            for segment in segments:
                snippet = str(segment or '').strip()
                if not snippet:
                    continue
                dates_in_segment = self._extract_date_strings(snippet)
                if not dates_in_segment:
                    continue
                lower_segment = snippet.lower()
                for date_value in dates_in_segment:
                    if any(token in lower_segment for token in ('hearing', 'appeal', 'requested hearing', 'request hearing', 'grievance hearing')):
                        buckets['hearing_request_dates'] = self._append_unique_text_item(
                            buckets.get('hearing_request_dates'),
                            date_value,
                        )
                    if any(token in lower_segment for token in ('responded', 'response', 'replied', 'reply', 'ignored', 'no response', 'never responded')):
                        buckets['response_dates'] = self._append_unique_text_item(
                            buckets.get('response_dates'),
                            date_value,
                        )
                    if any(token in lower_segment for token in ('denied', 'evicted', 'terminated', 'fired', 'adverse action', 'decision', 'notice', 'rejected')):
                        buckets['adverse_action_dates'] = self._append_unique_text_item(
                            buckets.get('adverse_action_dates'),
                            date_value,
                        )
                    if any(token in lower_segment for token in ('complained', 'reported', 'protected activity', 'grievance', 'accommodation', 'discrimination complaint')):
                        buckets['protected_activity_dates'] = self._append_unique_text_item(
                            buckets.get('protected_activity_dates'),
                            date_value,
                        )
                    if any(token in lower_segment for token in ('decision', 'determination', 'final decision', 'ruling')):
                        buckets['decision_dates'] = self._append_unique_text_item(
                            buckets.get('decision_dates'),
                            date_value,
                        )
                    if any(token in lower_segment for token in ('notice', 'letter', 'email', 'message', 'memo', 'policy', 'document')):
                        buckets['document_dates'] = self._append_unique_text_item(
                            buckets.get('document_dates'),
                            date_value,
                        )
            return buckets

        contextual_dates = _extract_contextual_dates(answer_text)

        def _single_claim_id() -> Optional[str]:
            claims = knowledge_graph.get_entities_by_type('claim')
            return claims[0].id if len(claims) == 1 else None

        def _single_claim_entity() -> Optional[Entity]:
            claim_id = _single_claim_id()
            return knowledge_graph.get_entity(claim_id) if claim_id else None

        def _answer_is_substantive(text_value: str) -> bool:
            normalized = " ".join(str(text_value or '').strip().lower().split())
            if not normalized:
                return False
            if normalized in low_information_tokens:
                return False
            if len(normalized) < 8:
                return False
            if self._contains_confirmation_placeholder(normalized):
                return False
            return True

        def _extract_file_references(text_value: str) -> List[str]:
            if not text_value:
                return []
            refs: List[str] = []
            for pattern in (
                r"\b[\w\-./]+\.(?:pdf|docx?|xlsx?|csv|txt|jpg|jpeg|png|gif|msg|eml)\b",
                r"\"([^\"]+\.(?:pdf|docx?|xlsx?|csv|txt|jpg|jpeg|png|gif|msg|eml))\"",
                r"'([^']+\.(?:pdf|docx?|xlsx?|csv|txt|jpg|jpeg|png|gif|msg|eml))'",
            ):
                for match in re.findall(pattern, text_value, flags=re.IGNORECASE):
                    candidate = str(match or "").strip()
                    if candidate and candidate not in refs:
                        refs.append(candidate)
            return refs[:6]

        def _extract_policy_references(text_value: str) -> List[str]:
            if not text_value:
                return []
            refs: List[str] = []
            for match in re.findall(
                r"\b([A-Z][A-Za-z0-9/&\-\s]{2,80}(?:Policy|Handbook|Manual|Rule|Procedure|Guideline|Code))\b",
                text_value,
            ):
                candidate = str(match or "").strip()
                if candidate and candidate not in refs:
                    refs.append(candidate)
            for match in re.findall(r"\b(section\s+\d+(?:\.\d+)*)\b", text_value, flags=re.IGNORECASE):
                candidate = str(match or "").strip()
                if candidate and candidate not in refs:
                    refs.append(candidate)
            return refs[:6]

        extracted_file_refs = _extract_file_references(answer_text)
        extracted_policy_refs = _extract_policy_references(answer_text)
        contract_missing_field_plan = [
            plan
            for plan in (answer_contract.get('missing_field_update_plan') or context.get('missing_field_update_plan') or [])
            if isinstance(plan, dict)
        ]
        policy_signal = any(token in answer_lower for token in ('policy', 'handbook', 'rule', 'criteria', 'section', 'guideline')) or bool(extracted_policy_refs)
        file_signal = bool(extracted_file_refs) or bool(document_mentions) or any(token in answer_lower for token in ('file', 'upload', 'attachment', 'exhibit', 'pdf', 'screenshot', 'scan'))
        staff_signal = bool(named_role_people or named_title_people or generic_roles)

        def _has_structured_signal() -> bool:
            return bool(
                extracted_dates
                or response_timing_phrases
                or staff_signal
                or has_sequence_signal
                or has_causation_signal
                or has_adverse_action_signal
                or policy_signal
                or file_signal
            )

        def _find_claim_entity_from_context() -> Optional[Entity]:
            for key in ('claim_entity_id', 'claim_id'):
                candidate_id = str(context.get(key) or '').strip()
                if not candidate_id:
                    continue
                entity = knowledge_graph.get_entity(candidate_id)
                if entity and entity.type == 'claim':
                    return entity
            claim_name = str(context.get('claim_name') or '').strip().lower()
            if claim_name:
                for entity in knowledge_graph.get_entities_by_type('claim'):
                    entity_name = str(entity.name or '').strip().lower()
                    if entity_name == claim_name or claim_name in entity_name or entity_name in claim_name:
                        return entity
            return _single_claim_entity()

        def _append_attr_list(entity: Optional[Entity], key: str, value: str) -> bool:
            if not entity:
                return False
            updated = self._append_unique_text_item((entity.attributes or {}).get(key), value)
            previous = (entity.attributes or {}).get(key)
            if previous != updated:
                entity.attributes[key] = updated
                return True
            return False

        def _mark_resolved_gap(claim_entity: Optional[Entity]) -> None:
            nonlocal updates
            if not claim_entity:
                return
            deterministic_key = str(context.get('deterministic_update_key') or '').strip().lower()
            gap_id = str(context.get('gap_id') or '').strip().lower()
            requirement_id = str(context.get('requirement_id') or context.get('target_element_id') or '').strip().lower()
            resolution_key = deterministic_key or gap_id or requirement_id
            if not resolution_key:
                return
            changed = _append_attr_list(claim_entity, 'resolved_gaps', resolution_key)
            if changed:
                updates['entities_updated'] += 1

        def _append_claim_signal(claim_entity: Optional[Entity], key: str, value: str) -> None:
            nonlocal updates
            if not value:
                return
            if _append_attr_list(claim_entity, key, value):
                updates['entities_updated'] += 1

        def _required_fields_for_gap(current_gap_type: str) -> List[str]:
            mapping = {
                'missing_exact_action_dates': ['event_date', 'adverse_action'],
                'missing_hearing_request_date': ['hearing_request_date', 'hearing_request_actor'],
                'missing_response_dates': ['response_date', 'response_actor'],
                'missing_hearing_timing': ['adverse_action_date', 'hearing_request_date'],
                'missing_staff_identity': ['staff_name', 'staff_role'],
                'missing_staff_title': ['staff_name', 'staff_title'],
                'retaliation_missing_causation': ['protected_activity', 'adverse_action', 'causation_link'],
                'retaliation_missing_causation_link': ['protected_activity', 'adverse_action', 'causation_link'],
                'retaliation_missing_sequence': ['protected_activity_date', 'adverse_action_date'],
                'retaliation_missing_sequencing_dates': ['protected_activity_date', 'adverse_action_date'],
                'missing_written_notice': ['document_name', 'document_date', 'issuing_actor'],
                'missing_decision_timeline': ['decision_date', 'decision_actor'],
                'missing_claim_element': ['supporting_fact'],
                'missing_proof_leads': ['supporting_fact'],
            }
            fields: List[str] = list(mapping.get(str(current_gap_type or '').strip().lower(), []))
            for contract_field in contract_required_fields:
                if contract_field not in fields:
                    fields.append(contract_field)
            return fields

        def _store_required_field_value(claim_entity: Optional[Entity], field_name: str, value: str) -> None:
            nonlocal updates
            if not claim_entity:
                return
            normalized_field = str(field_name or '').strip().lower()
            normalized_value = str(value or '').strip()
            if not normalized_field or not normalized_value:
                return
            attrs = claim_entity.attributes if isinstance(claim_entity.attributes, dict) else {}
            field_values = attrs.get('required_field_values')
            field_values = dict(field_values) if isinstance(field_values, dict) else {}
            existing_values = field_values.get(normalized_field)
            updated_values = self._append_unique_text_item(existing_values, normalized_value)
            if existing_values != updated_values:
                field_values[normalized_field] = updated_values
                attrs['required_field_values'] = field_values
                claim_entity.attributes = attrs
                updates['entities_updated'] += 1
                deterministic_fields_updated.add(normalized_field)
                _append_claim_signal(claim_entity, 'satisfied_requirements', normalized_field)

        def _link_claim_to_entity(claim_entity: Optional[Entity], target_entity: Optional[Entity], relation_type: str, confidence: float = 0.62) -> None:
            nonlocal updates
            if not claim_entity or not target_entity or not relation_type:
                return
            _, rel_created = self._add_relationship_if_missing(
                knowledge_graph,
                claim_entity.id,
                target_entity.id,
                relation_type,
                confidence,
            )
            if rel_created:
                updates['relationships_added'] += 1

        def _required_field_has_value(claim_entity: Optional[Entity], field_name: str) -> bool:
            if not claim_entity or not field_name:
                return False
            attrs = claim_entity.attributes if isinstance(claim_entity.attributes, dict) else {}
            field_values = attrs.get('required_field_values')
            field_values = field_values if isinstance(field_values, dict) else {}
            value = field_values.get(str(field_name or '').strip().lower())
            if isinstance(value, list):
                return any(str(item).strip() for item in value)
            return bool(str(value or '').strip())

        def _candidate_value_for_required_field(field_name: str) -> str:
            normalized = str(field_name or '').strip().lower()
            if not normalized:
                return ''
            if normalized in {'event_date', 'hearing_request_date', 'response_date', 'adverse_action_date', 'decision_date', 'protected_activity_date', 'document_date'}:
                if normalized == 'hearing_request_date' and contextual_dates.get('hearing_request_dates'):
                    return str((contextual_dates.get('hearing_request_dates') or [''])[0]).strip()
                if normalized == 'response_date' and contextual_dates.get('response_dates'):
                    return str((contextual_dates.get('response_dates') or [''])[0]).strip()
                if normalized == 'adverse_action_date' and contextual_dates.get('adverse_action_dates'):
                    return str((contextual_dates.get('adverse_action_dates') or [''])[0]).strip()
                if normalized == 'decision_date' and contextual_dates.get('decision_dates'):
                    return str((contextual_dates.get('decision_dates') or [''])[0]).strip()
                if normalized == 'protected_activity_date' and contextual_dates.get('protected_activity_dates'):
                    return str((contextual_dates.get('protected_activity_dates') or [''])[0]).strip()
                if normalized == 'document_date' and contextual_dates.get('document_dates'):
                    return str((contextual_dates.get('document_dates') or [''])[0]).strip()
                return str((extracted_dates or [''])[0]).strip()
            if normalized in {'staff_name', 'decision_actor', 'response_actor', 'hearing_request_actor', 'issuing_actor'}:
                if named_role_people:
                    name, role = named_role_people[0]
                    if normalized == 'staff_name':
                        return str(name or '').strip()
                    return f"{name} ({role})".strip()
                if named_title_people:
                    name, role = named_title_people[0]
                    if normalized == 'staff_name':
                        return str(name or '').strip()
                    return f"{name} ({role})".strip()
                return str((org_candidates or [''])[0]).strip()
            if normalized in {'staff_role', 'staff_title'}:
                if named_role_people:
                    return str(named_role_people[0][1] or '').strip()
                if named_title_people:
                    return str(named_title_people[0][1] or '').strip()
                return str((generic_roles or [''])[0]).strip()
            if normalized == 'document_name':
                if document_mentions:
                    return str(document_mentions[0]).strip()
                if extracted_file_refs:
                    return str(extracted_file_refs[0]).strip()
                if extracted_policy_refs:
                    return str(extracted_policy_refs[0]).strip()
                return ''
            if normalized == 'protected_activity' and has_causation_signal:
                return self._short_description(answer_text, 160)
            if normalized == 'adverse_action' and (has_adverse_action_signal or has_causation_signal):
                return self._short_description(answer_text, 160)
            if normalized == 'causation_link' and has_causation_signal:
                return self._short_description(answer_text, 160)
            if normalized == 'supporting_fact' and _has_structured_signal():
                return self._short_description(answer_text, 180)
            return ''

        def _apply_contract_gap_updates(claim_entity: Optional[Entity]) -> None:
            if not claim_entity or not _answer_is_substantive(answer_text):
                return

            # Force deterministic closure attempts for contract-identified missing fields.
            for field_name in contract_required_fields:
                if field_name in deterministic_fields_updated:
                    continue
                if field_name in contract_missing_required_fields or not _required_field_has_value(claim_entity, field_name):
                    candidate_value = _candidate_value_for_required_field(field_name)
                    if candidate_value:
                        _store_required_field_value(claim_entity, field_name, candidate_value)

            for plan in contract_missing_field_plan:
                field_name = str(plan.get('field_name') or '').strip().lower()
                if not field_name:
                    continue
                # Only execute deterministic field-level updates when this turn captured the field.
                if field_name not in deterministic_fields_updated:
                    continue
                deterministic_plan_fields_captured.add(field_name)
                for req_key in plan.get('requirement_updates') or []:
                    normalized_req = str(req_key or '').strip().lower()
                    if not normalized_req:
                        continue
                    deterministic_requirement_tokens_updated.add(normalized_req)
                    _append_claim_signal(claim_entity, 'satisfied_requirements', normalized_req)
                for rel_key in plan.get('relationship_updates') or []:
                    normalized_rel = str(rel_key or '').strip().lower()
                    if normalized_rel:
                        deterministic_relationship_tokens_updated.add(normalized_rel)
                for entity_key in plan.get('entity_updates') or []:
                    normalized_entity = str(entity_key or '').strip().lower()
                    if normalized_entity:
                        deterministic_entity_tokens_updated.add(normalized_entity)

            captured_contract_fields = deterministic_fields_updated.intersection(contract_missing_required_fields)
            if captured_contract_fields or (not contract_missing_required_fields and deterministic_fields_updated):
                deterministic_requirement_tokens_updated.update(contract_requirement_updates)
                deterministic_relationship_tokens_updated.update(contract_relationship_updates)
                deterministic_entity_tokens_updated.update(contract_entity_updates)

        def _deterministic_gap_field_updates(claim_entity: Optional[Entity]) -> None:
            if not claim_entity or not _answer_is_substantive(answer_text):
                return

            required_fields = _required_fields_for_gap(gap_type)
            if not required_fields:
                # Fall back to extraction targets to keep updates deterministic for registry-driven gaps.
                target_map = {
                    'exact_dates': 'event_date',
                    'event_order': 'supporting_fact',
                    'actor_name': 'staff_name',
                    'actor_role': 'staff_role',
                    'decision_maker': 'decision_actor',
                    'document_type': 'document_name',
                    'document_date': 'document_date',
                    'document_owner': 'issuing_actor',
                    'protected_activity': 'protected_activity',
                    'adverse_action': 'adverse_action',
                    'causation_link': 'causation_link',
                    'response_timing': 'response_date',
                }
                required_fields = [
                    target_map[target]
                    for target in extraction_targets
                    if target in target_map
                ]
                deduped_fields: List[str] = []
                for field_name in required_fields:
                    if field_name not in deduped_fields:
                        deduped_fields.append(field_name)
                required_fields = deduped_fields

            if extracted_dates:
                primary_date = extracted_dates[0]
                hearing_date = (contextual_dates.get('hearing_request_dates') or [primary_date])[0]
                response_date = (contextual_dates.get('response_dates') or [primary_date])[0]
                adverse_date = (contextual_dates.get('adverse_action_dates') or [primary_date])[0]
                decision_date = (contextual_dates.get('decision_dates') or [adverse_date])[0]
                protected_activity_date = (
                    (contextual_dates.get('protected_activity_dates') or [primary_date])[0]
                )
                if 'event_date' in required_fields:
                    _store_required_field_value(claim_entity, 'event_date', primary_date)
                if 'hearing_request_date' in required_fields:
                    _store_required_field_value(claim_entity, 'hearing_request_date', hearing_date)
                if 'response_date' in required_fields:
                    _store_required_field_value(claim_entity, 'response_date', response_date)
                if 'adverse_action_date' in required_fields:
                    _store_required_field_value(claim_entity, 'adverse_action_date', adverse_date)
                if 'decision_date' in required_fields:
                    _store_required_field_value(claim_entity, 'decision_date', decision_date)
                if 'protected_activity_date' in required_fields:
                    _store_required_field_value(claim_entity, 'protected_activity_date', protected_activity_date)

            staff_pairs: List[Tuple[str, str]] = []
            staff_pairs.extend(named_role_people)
            staff_pairs.extend(named_title_people)
            if staff_pairs:
                if 'staff_name' in required_fields:
                    _store_required_field_value(claim_entity, 'staff_name', staff_pairs[0][0])
                if 'staff_role' in required_fields:
                    _store_required_field_value(claim_entity, 'staff_role', staff_pairs[0][1])
                if 'staff_title' in required_fields:
                    _store_required_field_value(claim_entity, 'staff_title', staff_pairs[0][1])
                if 'decision_actor' in required_fields:
                    _store_required_field_value(claim_entity, 'decision_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
                if 'issuing_actor' in required_fields:
                    _store_required_field_value(claim_entity, 'issuing_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
                for person_name, person_role in staff_pairs[:4]:
                    person_entity, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'person',
                        person_name,
                        {
                            'role': person_role,
                            'title': person_role,
                            'source': 'deterministic_gap_update',
                            'gap_type': gap_type,
                        },
                        0.78,
                    )
                    if created:
                        updates['entities_updated'] += 1
                    _link_claim_to_entity(claim_entity, person_entity, 'involves', 0.67)
                    if any(token in person_role for token in ('manager', 'director', 'officer', 'landlord', 'owner', 'supervisor', 'agent')):
                        _link_claim_to_entity(claim_entity, person_entity, 'has_decision_maker', 0.66)
            elif org_candidates and ('decision_actor' in required_fields or 'issuing_actor' in required_fields):
                if 'decision_actor' in required_fields:
                    _store_required_field_value(claim_entity, 'decision_actor', org_candidates[0])
                if 'issuing_actor' in required_fields:
                    _store_required_field_value(claim_entity, 'issuing_actor', org_candidates[0])
                org_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'organization',
                    org_candidates[0],
                    {
                        'role': 'respondent',
                        'source': 'deterministic_gap_update',
                        'gap_type': gap_type,
                    },
                    0.72,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, org_entity, 'involves', 0.65)

            if ('document_name' in required_fields or 'supporting_fact' in required_fields) and (document_mentions or extracted_file_refs or extracted_policy_refs):
                document_value = (
                    document_mentions[0]
                    if document_mentions
                    else extracted_file_refs[0]
                    if extracted_file_refs
                    else extracted_policy_refs[0]
                )
                if 'document_name' in required_fields:
                    _store_required_field_value(claim_entity, 'document_name', document_value)
                if 'supporting_fact' in required_fields:
                    _store_required_field_value(claim_entity, 'supporting_fact', self._short_description(answer_text, 160))

            if 'document_date' in required_fields and extracted_dates:
                document_date = (
                    (contextual_dates.get('document_dates') or extracted_dates)[0]
                )
                _store_required_field_value(claim_entity, 'document_date', document_date)

            if 'response_actor' in required_fields and (staff_pairs or org_candidates):
                if staff_pairs:
                    _store_required_field_value(claim_entity, 'response_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
                elif org_candidates:
                    _store_required_field_value(claim_entity, 'response_actor', org_candidates[0])

            if 'hearing_request_actor' in required_fields and (staff_pairs or org_candidates):
                if staff_pairs:
                    _store_required_field_value(claim_entity, 'hearing_request_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
                elif org_candidates:
                    _store_required_field_value(claim_entity, 'hearing_request_actor', org_candidates[0])

            if 'protected_activity' in required_fields and has_causation_signal:
                _store_required_field_value(claim_entity, 'protected_activity', self._short_description(answer_text, 160))
            if 'adverse_action' in required_fields and (has_adverse_action_signal or has_causation_signal):
                _store_required_field_value(claim_entity, 'adverse_action', self._short_description(answer_text, 160))
            if 'causation_link' in required_fields and has_causation_signal:
                _store_required_field_value(claim_entity, 'causation_link', self._short_description(answer_text, 160))

            if 'supporting_fact' in required_fields and _has_structured_signal():
                _store_required_field_value(claim_entity, 'supporting_fact', self._short_description(answer_text, 180))

            # Promote concrete hearing/response/causation sequencing fields even when not explicitly required.
            if gap_type in {'missing_hearing_request_date', 'missing_hearing_timing'} and extracted_dates:
                hearing_candidate = (
                    (contextual_dates.get('hearing_request_dates') or extracted_dates)[0]
                )
                _store_required_field_value(claim_entity, 'hearing_request_date', hearing_candidate)
            if gap_type in {'missing_response_dates', 'missing_decision_timeline'} and (extracted_dates or response_timing_phrases):
                if extracted_dates:
                    response_candidate = (
                        (contextual_dates.get('response_dates') or extracted_dates)[0]
                    )
                    _store_required_field_value(claim_entity, 'response_date', response_candidate)
                elif response_timing_phrases:
                    _store_required_field_value(claim_entity, 'response_date', response_timing_phrases[0])
            if gap_type in {'retaliation_missing_causation', 'retaliation_missing_causation_link', 'retaliation_missing_sequence', 'retaliation_missing_sequencing_dates'}:
                if has_causation_signal:
                    _store_required_field_value(claim_entity, 'causation_link', self._short_description(answer_text, 160))
                if extracted_dates:
                    protected_candidate = (
                        (contextual_dates.get('protected_activity_dates') or extracted_dates)[0]
                    )
                    adverse_candidates = contextual_dates.get('adverse_action_dates') or extracted_dates
                    _store_required_field_value(claim_entity, 'protected_activity_date', protected_candidate)
                    if len(adverse_candidates) > 1 and adverse_candidates[0] == protected_candidate:
                        _store_required_field_value(claim_entity, 'adverse_action_date', adverse_candidates[1])
                    else:
                        _store_required_field_value(claim_entity, 'adverse_action_date', adverse_candidates[0])

        def _deterministic_requirement_fact(claim_entity: Optional[Entity]) -> None:
            nonlocal updates
            if not claim_entity or not _answer_is_substantive(answer_text):
                return
            requirement_id = str(context.get('requirement_id') or context.get('target_element_id') or '').strip()
            requirement_name = str(context.get('requirement_name') or requirement_id or 'claim element').strip()
            claim_type = normalize_claim_type(str(context.get('claim_type') or claim_entity.attributes.get('claim_type') or '').strip())
            snippet = self._short_description(answer_text, 140)
            fact_name = f"Requirement {requirement_name}: {self._short_description(answer_text, 72)}"
            fact_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                fact_name,
                {
                    'fact_type': 'requirement_support',
                    'description': snippet,
                    'requirement_id': requirement_id,
                    'requirement_name': requirement_name,
                    'claim_type': claim_type,
                    'source_question_type': question_type,
                    'gap_id': str(context.get('gap_id') or ''),
                },
                0.68,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, fact_entity, 'has_requirement_fact', 0.64)

            if requirement_id:
                changed = _append_attr_list(claim_entity, 'satisfied_requirements', requirement_id.lower())
                if changed:
                    updates['entities_updated'] += 1
            if str(context.get('requirement_name') or '').strip():
                changed = _append_attr_list(claim_entity, 'satisfied_requirement_labels', requirement_name)
                if changed:
                    updates['entities_updated'] += 1

        def _upsert_structured_evidence(claim_entity: Optional[Entity],
                                        claim_id: Optional[str],
                                        evidence_type: str,
                                        confidence: float,
                                        extra_attrs: Optional[Dict[str, Any]] = None) -> None:
            nonlocal updates
            if not claim_id or not _answer_is_substantive(answer_text):
                return
            snippet = self._short_description(answer_text, 140)
            prefix = "Policy document" if evidence_type == 'policy_document' else "File evidence"
            evidence_name = f"{prefix}: {self._short_description(answer_text, 80)}"
            attrs = {
                'description': snippet,
                'evidence_type': evidence_type,
                'gap_type': gap_type,
                'gap_id': str(context.get('gap_id') or ''),
            }
            if extra_attrs:
                attrs.update(extra_attrs)
            evidence_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'evidence',
                evidence_name,
                attrs,
                confidence,
            )
            if created:
                updates['entities_updated'] += 1
            if evidence_entity:
                _, rel_created = self._add_relationship_if_missing(
                    knowledge_graph,
                    claim_id,
                    evidence_entity.id,
                    'supported_by',
                    max(0.6, confidence - 0.01),
                )
                if rel_created:
                    updates['relationships_added'] += 1
            _append_claim_signal(claim_entity, 'satisfied_evidence_modalities', evidence_type)
            if evidence_type == 'policy_document':
                for ref in extracted_policy_refs[:3]:
                    _append_claim_signal(claim_entity, 'policy_document_refs', ref)
            if evidence_type == 'file_evidence':
                for ref in extracted_file_refs[:3]:
                    _append_claim_signal(claim_entity, 'file_evidence_refs', ref)

        def _mark_dependency_requirement_satisfied() -> None:
            nonlocal updates
            if not dependency_graph or not _answer_is_substantive(answer_text):
                return
            required_fields = _required_fields_for_gap(gap_type)
            captured_missing_required = deterministic_fields_updated.intersection(contract_missing_required_fields)
            if (
                required_fields
                and not deterministic_fields_updated.intersection(set(required_fields))
                and not deterministic_requirement_tokens_updated
            ):
                return
            if (
                workflow_phase == 'graph_analysis'
                and contract_missing_required_fields
                and not captured_missing_required
                and not deterministic_plan_fields_captured
            ):
                return
            candidate_ids = {
                str(context.get('requirement_id') or '').strip(),
                str(context.get('node_id') or '').strip(),
                str(context.get('target_element_id') or '').strip(),
            }
            requirement_name = str(context.get('requirement_name') or context.get('node_name') or '').strip().lower()
            requirement_key = str(context.get('requirement_key') or context.get('target_element_id') or '').strip().lower()
            requirement_aliases = {
                token
                for token in (
                    [requirement_key]
                    + list(deterministic_requirement_tokens_updated)
                    + list(contract_requirement_updates)
                )
                if str(token or '').strip()
            }

            matched_nodes = []
            for node_id in [item for item in candidate_ids if item]:
                node = dependency_graph.get_node(node_id)
                if node:
                    matched_nodes.append(node)
            if not matched_nodes:
                for node in dependency_graph.nodes.values():
                    node_name = str(node.name or '').strip().lower()
                    attrs = node.attributes if isinstance(node.attributes, dict) else {}
                    node_requirement_key = str(attrs.get('requirement_key') or '').strip().lower()
                    if requirement_name and node_name == requirement_name:
                        matched_nodes.append(node)
                    elif requirement_aliases and node_requirement_key and node_requirement_key in requirement_aliases:
                        matched_nodes.append(node)

            seen_node_ids: Set[str] = set()
            for node in matched_nodes:
                if not node or node.id in seen_node_ids:
                    continue
                seen_node_ids.add(node.id)
                if not node.satisfied:
                    node.satisfied = True
                    updates['requirements_satisfied'] += 1
                node.confidence = max(float(node.confidence or 0.0), 0.78)
                attrs = node.attributes if isinstance(node.attributes, dict) else {}
                attrs['satisfied_via_denoiser'] = True
                attrs['satisfied_answer_text'] = self._short_description(answer_text, 180)
                if str(context.get('gap_id') or '').strip():
                    attrs['satisfied_gap_id'] = str(context.get('gap_id'))
                if requirement_key:
                    attrs['requirement_key'] = requirement_key
                node.attributes = attrs

        def _mark_dependency_gap_satisfied() -> None:
            nonlocal updates
            if not dependency_graph or not _answer_is_substantive(answer_text):
                return
            required_fields = _required_fields_for_gap(gap_type)
            relevant_required = set(contract_missing_required_fields or required_fields)
            captured_required = deterministic_fields_updated.intersection(relevant_required)
            if (
                workflow_phase == 'graph_analysis'
                and relevant_required
                and not captured_required
                and not deterministic_requirement_tokens_updated
                and not deterministic_plan_fields_captured
            ):
                return
            gap_id = str(context.get('gap_id') or '').strip().lower()
            deterministic_key = str(context.get('deterministic_update_key') or '').strip().lower()
            target_keys = {
                item
                for item in [
                    gap_id,
                    deterministic_key,
                    str(context.get('target_element_id') or '').strip().lower(),
                    str(context.get('requirement_key') or '').strip().lower(),
                ]
                if item
            }
            if not target_keys and not gap_type:
                return
            for node in dependency_graph.nodes.values():
                attrs = node.attributes if isinstance(node.attributes, dict) else {}
                node_keys = {
                    str(node.id or '').strip().lower(),
                    str(node.name or '').strip().lower(),
                    str(attrs.get('gap_id') or '').strip().lower(),
                    str(attrs.get('gap_key') or '').strip().lower(),
                    str(attrs.get('requirement_key') or '').strip().lower(),
                    str(attrs.get('target_element_id') or '').strip().lower(),
                }
                node_gap_type = str(attrs.get('gap_type') or '').strip().lower()
                matched = bool(target_keys.intersection({item for item in node_keys if item}))
                if not matched and gap_type and node_gap_type == gap_type:
                    matched = True
                if not matched:
                    continue
                if not node.satisfied:
                    node.satisfied = True
                    updates['requirements_satisfied'] += 1
                node.confidence = max(float(node.confidence or 0.0), 0.8)
                attrs['satisfied_via_denoiser'] = True
                attrs['satisfied_answer_text'] = self._short_description(answer_text, 180)
                if gap_id:
                    attrs['satisfied_gap_id'] = gap_id
                if gap_type:
                    attrs['gap_type'] = gap_type
                node.attributes = attrs

        def _add_structured_graph_analysis_updates(claim_entity: Optional[Entity]) -> None:
            nonlocal updates
            if not claim_entity or not _answer_is_substantive(answer_text):
                return
            claim_id = claim_entity.id

            if extracted_dates:
                for date_str in extracted_dates[:5]:
                    date_entity, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'date',
                        date_str,
                        {
                            'date_context_gap_type': gap_type,
                            'source_question_type': question_type,
                        },
                        0.74,
                    )
                    if created:
                        updates['entities_updated'] += 1
                    if date_entity:
                        _, rel_created = self._add_relationship_if_missing(
                            knowledge_graph,
                            claim_id,
                            date_entity.id,
                            'occurred_on',
                            0.66,
                        )
                        if rel_created:
                            updates['relationships_added'] += 1
                _append_claim_signal(claim_entity, 'exact_dates', ", ".join(extracted_dates[:5]))

            if response_timing_phrases:
                timing_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Response timing: {self._short_description(answer_text, 72)}",
                    {
                        'fact_type': 'response_timing',
                        'timing_phrases': list(response_timing_phrases[:4]),
                        'gap_type': gap_type,
                        'target_element_id': target_element_id,
                        'description': self._short_description(answer_text, 160),
                    },
                    0.72,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, timing_fact, 'has_timeline_detail', 0.64)
                for phrase in response_timing_phrases[:4]:
                    _append_claim_signal(claim_entity, 'response_timing_phrases', phrase)

            people_with_roles: List[Tuple[str, str]] = []
            seen_people_roles: Set[Tuple[str, str]] = set()
            for pair in named_title_people + named_role_people:
                key = (str(pair[0] or '').strip().lower(), str(pair[1] or '').strip().lower())
                if not key[0] or not key[1]:
                    continue
                if key not in seen_people_roles:
                    seen_people_roles.add(key)
                    people_with_roles.append((pair[0], pair[1]))

            for name, title in people_with_roles[:8]:
                person, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'person',
                    name,
                    {'role': title, 'title': title, 'source': 'denoiser_answer'},
                    0.74,
                )
                if created:
                    updates['entities_updated'] += 1
                elif person:
                    previous_title = str((person.attributes or {}).get('title') or '').strip().lower()
                    if not previous_title and title:
                        person.attributes['title'] = title
                        updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, person, 'involves', 0.64)
                if person and any(token in title for token in ('manager', 'director', 'officer', 'landlord', 'owner', 'supervisor', 'agent')):
                    _link_claim_to_entity(claim_entity, person, 'has_decision_maker', 0.62)
                    _append_claim_signal(claim_entity, 'decision_makers', f"{name} ({title})")

            for key, claim_attr in (
                ('hearing_request_dates', 'hearing_request_dates'),
                ('response_dates', 'response_dates'),
                ('adverse_action_dates', 'adverse_action_dates'),
                ('protected_activity_dates', 'protected_activity_dates'),
                ('decision_dates', 'decision_dates'),
            ):
                for date_token in (contextual_dates.get(key) or [])[:4]:
                    _append_claim_signal(claim_entity, claim_attr, date_token)

            if has_causation_signal or has_sequence_signal:
                causation_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Causation sequence: {self._short_description(answer_text, 72)}",
                    {
                        'fact_type': 'causation_sequence',
                        'has_causation_signal': bool(has_causation_signal),
                        'has_sequence_signal': bool(has_sequence_signal),
                        'has_adverse_action_signal': bool(has_adverse_action_signal),
                        'captured_dates': list(extracted_dates[:4]),
                        'target_element_id': target_element_id,
                        'description': self._short_description(answer_text, 160),
                    },
                    0.7,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, causation_fact, 'has_causation_detail', 0.63)
                if has_causation_signal:
                    _append_claim_signal(claim_entity, 'causation_sequences', self._short_description(answer_text, 180))

            should_force_policy = (
                'documentary_artifact_patch_anchor' in patchability_markers
                or 'document_type' in extraction_targets
                or gap_type in {'missing_claim_element', 'missing_proof_leads', 'missing_written_notice'}
                or expected_update_kind in {'proof_lead', 'documentary_support'}
                or 'policy_document' in expected_modalities
                or 'policy_document' in weak_modalities
            )
            should_force_file = (
                should_force_policy
                or 'document_owner' in extraction_targets
                or 'file_evidence' in expected_modalities
                or 'file_evidence' in weak_modalities
            )
            if policy_signal and should_force_policy:
                _upsert_structured_evidence(
                    claim_entity,
                    claim_id,
                    'policy_document',
                    0.72,
                    {
                        'policy_refs': list(extracted_policy_refs[:4]),
                        'document_mentions': list(document_mentions[:4]),
                        'question_objective': question_objective,
                        'expected_update_kind': expected_update_kind,
                    },
                )
            if file_signal and should_force_file:
                _upsert_structured_evidence(
                    claim_entity,
                    claim_id,
                    'file_evidence',
                    0.72,
                    {
                        'file_refs': list(extracted_file_refs[:4]),
                        'document_mentions': list(document_mentions[:4]),
                        'question_objective': question_objective,
                        'expected_update_kind': expected_update_kind,
                    },
                )

            if gap_type in {'missing_hearing_request_date', 'missing_hearing_timing'} and (extracted_dates or response_timing_phrases):
                _append_claim_signal(claim_entity, 'hearing_request_timing', self._short_description(answer_text, 180))
                _append_claim_signal(claim_entity, 'satisfied_requirements', 'hearing_request_timing')
                hearing_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Hearing request timing: {self._short_description(answer_text, 70)}",
                    {
                        'fact_type': 'hearing_request_timing',
                        'captured_dates': list(extracted_dates[:3]),
                        'response_timing': list(response_timing_phrases[:3]),
                        'description': self._short_description(answer_text, 180),
                    },
                    0.73,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, hearing_fact, 'has_timeline_detail', 0.66)
            if gap_type in {'missing_response_dates', 'missing_decision_timeline'} and (extracted_dates or response_timing_phrases):
                _append_claim_signal(claim_entity, 'response_dates', ", ".join(extracted_dates[:5]) or "; ".join(response_timing_phrases[:4]))
                _append_claim_signal(claim_entity, 'satisfied_requirements', 'response_dates')
                response_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Response dates: {self._short_description(answer_text, 70)}",
                    {
                        'fact_type': 'response_dates',
                        'captured_dates': list(extracted_dates[:4]),
                        'response_timing': list(response_timing_phrases[:4]),
                        'description': self._short_description(answer_text, 180),
                    },
                    0.74,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, response_fact, 'has_timeline_detail', 0.66)
            if gap_type in {'missing_staff_identity', 'missing_staff_title'} and staff_signal:
                _append_claim_signal(claim_entity, 'staff_names_titles', self._short_description(answer_text, 180))
                _append_claim_signal(claim_entity, 'satisfied_requirements', 'staff_identity')
                for name, role in (named_title_people or named_role_people)[:4]:
                    person, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'person',
                        name,
                        {'role': role, 'title': role, 'source': 'denoiser_answer'},
                        0.76,
                    )
                    if created:
                        updates['entities_updated'] += 1
                    _link_claim_to_entity(claim_entity, person, 'has_decision_maker', 0.68)
            if gap_type in {'retaliation_missing_causation', 'retaliation_missing_causation_link', 'retaliation_missing_sequence', 'retaliation_missing_sequencing_dates'} and (has_causation_signal or has_sequence_signal):
                _append_claim_signal(claim_entity, 'causation_timeline', self._short_description(answer_text, 180))
                _append_claim_signal(claim_entity, 'satisfied_requirements', 'causation_sequence')
                sequence_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Causation sequencing: {self._short_description(answer_text, 70)}",
                    {
                        'fact_type': 'causation_sequence',
                        'captured_dates': list(extracted_dates[:4]),
                        'has_causation_signal': bool(has_causation_signal),
                        'has_sequence_signal': bool(has_sequence_signal),
                        'description': self._short_description(answer_text, 180),
                    },
                    0.74,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, sequence_fact, 'has_causation_detail', 0.67)

        def _apply_contract_entity_relationship_updates(claim_entity: Optional[Entity]) -> None:
            nonlocal updates
            if not claim_entity or not _answer_is_substantive(answer_text):
                return
            claim_id = claim_entity.id

            if (
                'staff_actor' in deterministic_entity_tokens_updated
                or 'link_staff_to_action' in deterministic_relationship_tokens_updated
            ) and (named_title_people or named_role_people or org_candidates):
                people = list(named_title_people) + list(named_role_people)
                if not people and org_candidates:
                    org_entity, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'organization',
                        org_candidates[0],
                        {'role': 'respondent', 'source': 'answer_contract'},
                        0.76,
                    )
                    if created:
                        updates['entities_updated'] += 1
                    _link_claim_to_entity(claim_entity, org_entity, 'involves', 0.67)
                for name, title in people[:4]:
                    person, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'person',
                        name,
                        {'role': title, 'title': title, 'source': 'answer_contract'},
                        0.78,
                    )
                    if created:
                        updates['entities_updated'] += 1
                    _link_claim_to_entity(claim_entity, person, 'involves', 0.67)
                    _link_claim_to_entity(claim_entity, person, 'has_decision_maker', 0.66)

            if (
                'document_evidence' in deterministic_entity_tokens_updated
                or 'link_document_to_claim' in deterministic_relationship_tokens_updated
            ):
                if policy_signal or extracted_policy_refs:
                    _upsert_structured_evidence(
                        claim_entity,
                        claim_id,
                        'policy_document',
                        0.72,
                        {
                            'policy_refs': list(extracted_policy_refs[:4]),
                            'document_mentions': list(document_mentions[:4]),
                            'source': 'answer_contract',
                        },
                    )
                if file_signal or extracted_file_refs:
                    _upsert_structured_evidence(
                        claim_entity,
                        claim_id,
                        'file_evidence',
                        0.72,
                        {
                            'file_refs': list(extracted_file_refs[:4]),
                            'document_mentions': list(document_mentions[:4]),
                            'source': 'answer_contract',
                        },
                    )

            if (
                'timeline_fact' in deterministic_entity_tokens_updated
                or 'link_event_sequence' in deterministic_relationship_tokens_updated
                or 'validate_temporal_order' in deterministic_relationship_tokens_updated
                or 'link_response_to_hearing_or_action' in deterministic_relationship_tokens_updated
            ) and (extracted_dates or response_timing_phrases or has_sequence_signal):
                timeline_fact, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Timeline contract detail: {self._short_description(answer_text, 72)}",
                    {
                        'fact_type': 'timeline_contract_detail',
                        'captured_dates': list(extracted_dates[:4]),
                        'response_timing': list(response_timing_phrases[:4]),
                        'has_sequence_signal': bool(has_sequence_signal),
                        'gap_type': gap_type,
                    },
                    0.73,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, timeline_fact, 'has_timeline_detail', 0.66)

            if (
                'claim_fact' in deterministic_entity_tokens_updated
                or 'link_causation_chain' in deterministic_relationship_tokens_updated
            ) and _has_structured_signal():
                fact_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"Structured gap fact: {self._short_description(answer_text, 72)}",
                    {
                        'fact_type': 'structured_gap_fact',
                        'gap_type': gap_type,
                        'description': self._short_description(answer_text, 180),
                        'source': 'answer_contract',
                    },
                    0.72,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, fact_entity, 'has_requirement_fact', 0.65)

        def _actor_critic_gap_confidence() -> float:
            if not _answer_is_substantive(answer_text):
                return 0.0
            claim_type_hint = normalize_claim_type(
                str(context.get('claim_type') or context.get('claim_name') or '').strip()
            )
            weak_claim_focus = claim_type_hint in {'housing_discrimination', 'hacc_research_engine'}
            weak_modality_focus = bool({'policy_document', 'file_evidence'}.intersection(weak_modalities))
            target_checks = {
                'exact_dates': bool(extracted_dates),
                'event_order': bool(has_sequence_signal),
                'response_timing': bool(response_timing_phrases),
                'decision_maker': bool(staff_signal),
                'actor_name': bool(staff_signal),
                'actor_role': bool(staff_signal),
                'adverse_action': bool(has_adverse_action_signal),
                'causation_link': bool(has_causation_signal),
                'document_type': bool(document_mentions),
                'document_date': bool(extracted_dates),
                'document_owner': bool(named_title_people or named_role_people or org_candidates),
                'hearing_request_timing': bool(contextual_dates.get('hearing_request_dates')),
                'response_dates': bool(contextual_dates.get('response_dates') or response_timing_phrases),
                'staff_names_titles': bool(staff_signal),
            }
            requested_targets = set(extraction_targets)
            if not requested_targets and target_element_id:
                if 'timing' in target_element_id or 'date' in target_element_id:
                    requested_targets.update({'exact_dates', 'event_order'})
                if any(token in target_element_id for token in ('actor', 'staff', 'identity', 'title', 'party')):
                    requested_targets.update({'actor_name', 'actor_role'})
                if any(token in target_element_id for token in ('causation', 'retaliation', 'sequence')):
                    requested_targets.update({'causation_link', 'event_order'})
            if requested_targets:
                hits = sum(1 for target in requested_targets if target_checks.get(target, False))
                actor_score = hits / max(len(requested_targets), 1)
            elif contract_required_fields:
                contract_hits = sum(
                    1
                    for field_name in contract_required_fields
                    if field_name in deterministic_fields_updated
                )
                actor_score = contract_hits / max(len(contract_required_fields), 1)
            else:
                actor_score = 1.0 if _has_structured_signal() else 0.35
            contract_capture_ratio = (
                len(deterministic_fields_updated.intersection(contract_missing_required_fields))
                / max(len(contract_missing_required_fields), 1)
                if contract_missing_required_fields
                else 1.0
            )
            critic_components = [
                1.0 if _has_structured_signal() else 0.0,
                1.0 if (policy_signal or file_signal) else 0.0,
                1.0 if (has_sequence_signal or has_causation_signal) else 0.0,
                1.0 if (extracted_dates or response_timing_phrases) else 0.0,
                1.0 if deterministic_fields_updated else 0.0,
                1.0 if deterministic_requirement_tokens_updated else 0.0,
                1.0 if (contextual_dates.get('response_dates') or contextual_dates.get('hearing_request_dates')) else 0.0,
                contract_capture_ratio,
            ]
            critic_score = sum(critic_components) / float(len(critic_components))
            weighted = (
                float(self.actor_weight or 1.0) * float(actor_score)
                + float(self.critic_weight or 1.0) * float(critic_score)
            ) / max(float(self.actor_weight or 1.0) + float(self.critic_weight or 1.0), 1e-6)
            if weak_claim_focus and bool(deterministic_fields_updated):
                weighted = min(1.0, weighted + 0.07)
            if weak_modality_focus and bool(policy_signal or file_signal):
                weighted = min(1.0, weighted + 0.05)
            return max(0.0, min(1.0, weighted))

        def _context_gap_is_closed() -> bool:
            if not _answer_is_substantive(answer_text):
                return False
            closure_confidence = _actor_critic_gap_confidence()
            if bool(self.actor_critic_enabled) and workflow_phase == 'graph_analysis' and closure_confidence < 0.5:
                return False

            claim_entity = _find_claim_entity_from_context()
            claim_attrs = claim_entity.attributes if (claim_entity and isinstance(claim_entity.attributes, dict)) else {}
            field_values = claim_attrs.get('required_field_values')
            field_values = field_values if isinstance(field_values, dict) else {}

            def _field_has_value(field_name: str) -> bool:
                value = field_values.get(field_name)
                if isinstance(value, list):
                    return any(str(item).strip() for item in value)
                return bool(str(value or '').strip())

            required_fields = _required_fields_for_gap(gap_type)
            if required_fields:
                matched_fields = 0
                for field_name in required_fields:
                    if field_name in deterministic_fields_updated or _field_has_value(field_name):
                        matched_fields += 1
                coverage = matched_fields / max(len(required_fields), 1)
                newly_captured_required = bool(deterministic_fields_updated.intersection(set(required_fields)))
                strict_gaps = {
                    'missing_staff_identity',
                    'missing_staff_title',
                    'missing_written_notice',
                    'missing_response_dates',
                    'missing_hearing_request_date',
                    'missing_decision_timeline',
                    'retaliation_missing_causation_link',
                    'retaliation_missing_sequencing_dates',
                }
                if gap_type in strict_gaps:
                    return coverage >= 1.0 and newly_captured_required
                if workflow_phase == 'graph_analysis' and contract_missing_required_fields:
                    captured_missing = deterministic_fields_updated.intersection(contract_missing_required_fields)
                    captured_ratio = len(captured_missing) / max(len(contract_missing_required_fields), 1)
                    if contract_single_field_closable:
                        return bool(captured_missing)
                    if contract_single_turn_closable:
                        return bool(captured_missing) and coverage >= 1.0 and captured_ratio >= 1.0
                    if contract_deterministically_closable:
                        return bool(captured_missing) and captured_ratio >= 0.5 and coverage >= 0.67
                # Require a concrete field capture in this turn before considering the gap closed.
                return newly_captured_required and coverage >= 0.5

            if not gap_type:
                return bool(_has_structured_signal() or question_type in {'requirement', 'evidence', 'timeline', 'responsible_party', 'relationship'})
            missing_claim_element_closed = bool(_has_structured_signal() or target_element_id)
            if target_element_id:
                if any(token in target_element_id for token in ('date', 'timeline', 'timing')):
                    missing_claim_element_closed = missing_claim_element_closed and bool(extracted_dates or response_timing_phrases)
                if any(token in target_element_id for token in ('staff', 'actor', 'party', 'title', 'identity')):
                    missing_claim_element_closed = missing_claim_element_closed and bool(staff_signal)
                if any(token in target_element_id for token in ('causation', 'retaliation', 'sequence')):
                    missing_claim_element_closed = missing_claim_element_closed and bool(has_causation_signal or has_sequence_signal)
            checks = {
                'missing_exact_action_dates': bool(extracted_dates),
                'missing_hearing_request_date': bool(extracted_dates),
                'missing_response_dates': bool(extracted_dates or response_timing_phrases),
                'missing_hearing_timing': bool(extracted_dates or response_timing_phrases),
                'missing_decision_timeline': bool(extracted_dates) and bool(has_sequence_signal or response_timing_phrases or has_adverse_action_signal),
                'missing_staff_identity': bool(named_role_people or named_title_people or org_candidates),
                'missing_staff_title': bool(named_role_people or named_title_people or generic_roles),
                'missing_written_notice': bool(file_signal or has_document_precision_signal),
                'retaliation_missing_causation': bool(has_causation_signal) and bool(has_adverse_action_signal or has_sequence_signal or extracted_dates),
                'retaliation_missing_causation_link': bool(has_causation_signal) and bool(has_adverse_action_signal or has_sequence_signal or extracted_dates),
                'retaliation_missing_sequence': bool(has_sequence_signal) and bool(extracted_dates or response_timing_phrases),
                'retaliation_missing_sequencing_dates': bool(has_sequence_signal) and bool(extracted_dates or response_timing_phrases),
                'missing_claim_element': missing_claim_element_closed,
                'missing_proof_leads': bool(policy_signal or file_signal or extracted_file_refs or extracted_policy_refs),
            }
            return bool(checks.get(gap_type, True))

        def _record_gap_resolution(claim_entity: Optional[Entity]) -> None:
            nonlocal updates
            if not claim_entity or not _answer_is_substantive(answer_text):
                return
            if not gap_type:
                return
            fact_name = f"Gap resolved ({gap_type}): {self._short_description(answer_text, 68)}"
            attrs: Dict[str, Any] = {
                'fact_type': 'gap_resolution',
                'gap_type': gap_type,
                'gap_id': str(context.get('gap_id') or ''),
                'description': self._short_description(answer_text, 140),
                'source_question_type': question_type,
            }
            if extracted_dates:
                attrs['captured_dates'] = list(extracted_dates[:4])
            if response_timing_phrases:
                attrs['captured_response_timing'] = list(response_timing_phrases[:3])
            if extracted_policy_refs:
                attrs['captured_policy_refs'] = list(extracted_policy_refs[:3])
            if extracted_file_refs:
                attrs['captured_file_refs'] = list(extracted_file_refs[:3])
            fact_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                fact_name,
                attrs,
                0.68,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, fact_entity, 'has_gap_resolution', 0.64)

        def _apply_timeline_enrichment() -> None:
            nonlocal updates
            if question_type not in timeline_enrichment_types or not answer_text:
                return
            claim_entity = _find_claim_entity_from_context()
            claim_id = claim_entity.id if claim_entity else _single_claim_id()
            dates = self._extract_date_strings(answer_text)
            if dates:
                for date_str in dates:
                    date_entity, created = self._add_entity_if_missing(
                        knowledge_graph,
                        'date',
                        date_str,
                        {},
                        0.7
                    )
                    if created:
                        updates['entities_updated'] += 1
                    if claim_id and date_entity:
                        _, rel_created = self._add_relationship_if_missing(
                            knowledge_graph,
                            claim_id,
                            date_entity.id,
                            'occurred_on',
                            0.6
                        )
                        if rel_created:
                            updates['relationships_added'] += 1

            response_timing_phrases = self._extract_response_timing_phrases(answer_text)
            has_sequence = self._contains_sequence_signal(answer_text)
            should_add_timeline_fact = (
                question_type in fallback_timeline_fact_types
                and (not dates or has_sequence or bool(response_timing_phrases))
            )
            if should_add_timeline_fact:
                snippet = self._short_description(answer_text, 120)
                fact_name = f"Timeline detail: {self._short_description(answer_text, 60)}"
                fact_attrs: Dict[str, Any] = {'fact_type': 'timeline', 'description': snippet}
                if response_timing_phrases:
                    fact_attrs['response_timing'] = list(response_timing_phrases[:3])
                if has_sequence:
                    fact_attrs['event_order'] = 'captured'
                fact_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    fact_name,
                    fact_attrs,
                    0.6
                )
                if created:
                    updates['entities_updated'] += 1
                if claim_id and fact_entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        fact_entity.id,
                        'has_timeline_detail',
                        0.6
                    )
                    if rel_created:
                        updates['relationships_added'] += 1

            if question_type in {'evidence', 'timeline', 'responsible_party', 'requirement'}:
                document_mentions = self._extract_document_mentions(answer_text)
                for document_label in document_mentions[:3]:
                    artifact_name = f"{document_label}: {self._short_description(answer_text, 64)}"
                    artifact_entity, artifact_created = self._add_entity_if_missing(
                        knowledge_graph,
                        'fact',
                        artifact_name,
                        {
                            'fact_type': 'documentary_artifact',
                            'document_type': document_label,
                            'description': self._short_description(answer_text, 120),
                        },
                        0.58
                    )
                    if artifact_created:
                        updates['entities_updated'] += 1
                    if claim_id and artifact_entity:
                        _, rel_created = self._add_relationship_if_missing(
                            knowledge_graph,
                            claim_id,
                            artifact_entity.id,
                            'has_documentary_artifact',
                            0.58
                        )
                        if rel_created:
                            updates['relationships_added'] += 1

        if question_type == 'clarification':
            entity_id = context.get('entity_id')
            entity = knowledge_graph.get_entity(entity_id)
            if entity:
                entity.confidence = min(1.0, entity.confidence + 0.2)
                entity.attributes['clarification'] = answer
                updates['entities_updated'] += 1

        elif question_type == 'relationship':
            entity_id = context.get('entity_id')
            if entity_id and _answer_is_substantive(answer_text):
                entity = knowledge_graph.get_entity(entity_id)
                if entity:
                    entity.attributes['relationship_described'] = True
                    entity.attributes['relationship_description'] = self._short_description(answer_text, 180)
                    updates['entities_updated'] += 1
                    _link_claim_to_entity(_find_claim_entity_from_context(), entity, 'involves', 0.63)

        elif question_type == 'responsible_party':
            pass

        elif question_type == 'evidence':
            claim_entity = _find_claim_entity_from_context()
            if claim_entity:
                claim_entity.attributes['evidence_descriptions'] = self._append_unique_text_item(
                    claim_entity.attributes.get('evidence_descriptions'),
                    answer,
                )
                updates['entities_updated'] += 1
            claim_id = claim_entity.id if claim_entity else _single_claim_id()
            if claim_id and _answer_is_substantive(answer_text):
                snippet = self._short_description(answer_text, 120)
                evidence_name = f"Evidence: {self._short_description(answer_text, 80)}"
                evidence_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'evidence',
                    evidence_name,
                    {'description': snippet},
                    0.6
                )
                if created:
                    updates['entities_updated'] += 1
                if evidence_entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        evidence_entity.id,
                        'supported_by',
                        0.6
                    )
                    if rel_created:
                        updates['relationships_added'] += 1

            modality_targets = expected_modalities.union(weak_modalities)
            should_capture_policy = bool(policy_signal) and (
                'policy_document' in modality_targets
                or gap_type in {'missing_claim_element', 'missing_proof_leads', 'missing_written_notice'}
            )
            should_capture_file = bool(file_signal) and (
                'file_evidence' in modality_targets
                or gap_type in {'missing_claim_element', 'missing_proof_leads', 'missing_written_notice'}
            )
            if claim_id and _answer_is_substantive(answer_text):
                if should_capture_policy:
                    _upsert_structured_evidence(
                        claim_entity,
                        claim_id,
                        'policy_document',
                        0.7,
                        {
                            'policy_refs': list(extracted_policy_refs[:4]),
                            'document_mentions': list(document_mentions[:3]),
                            'document_date_candidates': list(extracted_dates[:3]),
                        },
                    )
                if should_capture_file:
                    _upsert_structured_evidence(
                        claim_entity,
                        claim_id,
                        'file_evidence',
                        0.7,
                        {
                            'file_refs': list(extracted_file_refs[:4]),
                            'document_mentions': list(document_mentions[:3]),
                            'document_date_candidates': list(extracted_dates[:3]),
                        },
                    )

        elif question_type == 'timeline':
            pass

        elif question_type in {'impact', 'remedy'}:
            if answer_text:
                claim_entity = _find_claim_entity_from_context()
                claim_id = claim_entity.id if claim_entity else _single_claim_id()
                snippet = self._short_description(answer_text, 120)
                if question_type == 'remedy':
                    fact_type = 'remedy'
                    fact_name = f"Requested remedy: {self._short_description(answer_text, 60)}"
                    rel_type = 'seeks_remedy'
                else:
                    fact_type = 'impact'
                    fact_name = f"Impact: {self._short_description(answer_text, 60)}"
                    rel_type = 'has_impact'
                fact_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    fact_name,
                    {'fact_type': fact_type, 'description': snippet},
                    0.6
                )
                if created:
                    updates['entities_updated'] += 1
                if claim_id and fact_entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        fact_entity.id,
                        rel_type,
                        0.6
                    )
                    if rel_created:
                        updates['relationships_added'] += 1
                if question_type == 'impact' and self._contains_remedy_cue(answer_text):
                    remedy_name = f"Requested remedy: {self._short_description(answer_text, 60)}"
                    remedy_entity, remedy_created = self._add_entity_if_missing(
                        knowledge_graph,
                        'fact',
                        remedy_name,
                        {'fact_type': 'remedy', 'description': snippet},
                        0.55
                    )
                    if remedy_created:
                        updates['entities_updated'] += 1
                    if claim_id and remedy_entity:
                        _, rel_created = self._add_relationship_if_missing(
                            knowledge_graph,
                            claim_id,
                            remedy_entity.id,
                            'seeks_remedy',
                            0.55
                        )
                        if rel_created:
                            updates['relationships_added'] += 1

        elif question_type == 'requirement':
            claim_entity = _find_claim_entity_from_context()
            _deterministic_requirement_fact(claim_entity)
            _mark_dependency_requirement_satisfied()
            _append_claim_signal(claim_entity, 'answered_requirement_questions', str(context.get('requirement_id') or context.get('target_element_id') or '').strip().lower())

        if question_type in responsible_party_enrichment_types and answer_text:
            updates = self._update_responsible_parties_from_answer(answer_text, knowledge_graph, updates)

        if question_type in timeline_enrichment_types and answer_text:
            _apply_timeline_enrichment()

        claim_entity_for_gap = _find_claim_entity_from_context()
        _deterministic_gap_field_updates(claim_entity_for_gap)
        _apply_contract_gap_updates(claim_entity_for_gap)
        _add_structured_graph_analysis_updates(claim_entity_for_gap)
        _apply_contract_entity_relationship_updates(claim_entity_for_gap)
        _mark_dependency_requirement_satisfied()

        if _context_gap_is_closed():
            _record_gap_resolution(claim_entity_for_gap)
            _mark_resolved_gap(claim_entity_for_gap)
            _mark_dependency_gap_satisfied()

        logger.info(f"Processed answer: {updates}")

        try:
            gain = self._compute_gain(updates)
            self._recent_gains.append(gain)
            if len(self._recent_gains) > 50:
                self._recent_gains = self._recent_gains[-50:]
            qtype = question.get('type') if isinstance(question, dict) else 'unknown'
            self._update_momentum(str(qtype or 'unknown'), gain)
        except Exception:
            pass

        return updates
    
    def calculate_noise_level(self, 
                             knowledge_graph: KnowledgeGraph,
                             dependency_graph: DependencyGraph) -> float:
        """
        Calculate current noise/uncertainty level.
        
        Lower values indicate less noise (more complete, confident information).
        
        Args:
            knowledge_graph: Current knowledge graph
            dependency_graph: Current dependency graph
            
        Returns:
            Noise level from 0.0 (no noise) to 1.0 (maximum noise)
        """
        # Calculate knowledge graph confidence
        kg_confidence = 0.0
        if knowledge_graph.entities:
            confidence_entities = [
                entity for entity in knowledge_graph.entities.values()
                if str(entity.type or '').strip().lower() != 'evidence'
            ]
            if not confidence_entities:
                confidence_entities = list(knowledge_graph.entities.values())
            total_confidence = sum(entity.confidence for entity in confidence_entities)
            kg_confidence = total_confidence / len(confidence_entities)
        
        # Calculate dependency satisfaction
        readiness = dependency_graph.get_claim_readiness()
        dep_satisfaction = readiness.get('overall_readiness', 0.0)
        
        # Calculate gap ratio
        kg_gaps = len(knowledge_graph.find_gaps())
        kg_entities = len(knowledge_graph.entities)
        gap_ratio = kg_gaps / max(kg_entities, 1)
        
        # Combine metrics (lower is better)
        noise = (
            (1.0 - kg_confidence) * 0.4 +  # 40% weight on entity confidence
            (1.0 - dep_satisfaction) * 0.4 +  # 40% weight on dependency satisfaction
            min(gap_ratio, 1.0) * 0.2  # 20% weight on gaps
        )
        
        return noise
    
    def is_exhausted(self) -> bool:
        """
        Check if we've exhausted the question pool.
        
        Returns:
            True if no more questions can be asked
        """
        return len(self.questions_pool) == 0 or len(self.questions_asked) > 50
    
    def generate_evidence_questions(self,
                                   knowledge_graph: KnowledgeGraph,
                                   dependency_graph: DependencyGraph,
                                   evidence_gaps: List[Dict[str, Any]],
                                   alignment_evidence_tasks: Optional[List[Dict[str, Any]]] = None,
                                   evidence_workflow_action_queue: Optional[List[Dict[str, Any]]] = None,
                                   max_questions: int = 5) -> List[Dict[str, Any]]:
        """
        Generate denoising questions for evidence phase.
        
        Args:
            knowledge_graph: Current knowledge graph
            dependency_graph: Current dependency graph
            evidence_gaps: Identified evidence gaps
            alignment_evidence_tasks: Shared intake/evidence element tasks to prioritize
            evidence_workflow_action_queue: Ranked workflow steering actions for evidence follow-up
            max_questions: Maximum questions to generate
            
        Returns:
            List of evidence-focused denoising questions
        """
        questions = []

        prioritized_tasks = (
            alignment_evidence_tasks
            if isinstance(alignment_evidence_tasks, list)
            else []
        )
        workflow_actions = (
            evidence_workflow_action_queue
            if isinstance(evidence_workflow_action_queue, list)
            else []
        )

        for task in prioritized_tasks[:max_questions]:
            if not isinstance(task, dict):
                continue
            claim_type = str(task.get('claim_type') or 'this claim').strip()
            claim_element_id = str(task.get('claim_element_id') or '').strip()
            claim_element_label = str(
                task.get('claim_element_label')
                or claim_element_id
                or 'this issue'
            ).strip()
            support_status = str(task.get('support_status') or '').strip().lower()
            action = str(task.get('action') or 'fill_evidence_gaps').strip().lower()
            preferred_support_kind = str(task.get('preferred_support_kind') or '').strip().lower()
            preferred_evidence_classes = [
                str(item).strip().replace('_', ' ')
                for item in (task.get('preferred_evidence_classes') or [])
                if str(item).strip()
            ]
            missing_fact_bundle = [
                str(item).strip()
                for item in (task.get('missing_fact_bundle') or [])
                if str(item).strip()
            ]
            recommended_queries = [
                str(item).strip()
                for item in (task.get('recommended_queries') or [])
                if str(item).strip()
            ]
            evidence_hint = ''
            if preferred_evidence_classes:
                evidence_hint = f" such as {', '.join(preferred_evidence_classes[:3])}"
            bundle_hint = f" I still need facts about {missing_fact_bundle[0]}." if missing_fact_bundle else ''
            if support_status == 'contradicted' or action == 'resolve_support_conflicts':
                question_text = (
                    f"What evidence best resolves the conflict around {claim_element_label} "
                    f"for {claim_type}?{bundle_hint}"
                )
                question_type = 'evidence_conflict'
                priority = 'high'
            else:
                if preferred_support_kind == 'authority':
                    question_text = (
                        f"What legal authority or official policy material do you have to support "
                        f"{claim_element_label} for {claim_type}?{bundle_hint}"
                    )
                elif preferred_support_kind == 'testimony':
                    question_text = (
                        f"What first-hand testimony or witness account can support {claim_element_label} "
                        f"for {claim_type}?{bundle_hint}"
                    )
                else:
                    question_text = (
                        f"What evidence{evidence_hint} do you have to support {claim_element_label} "
                        f"for {claim_type}?{bundle_hint}"
                    )
                question_type = 'evidence_clarification'
                priority = 'high' if bool(task.get('blocking')) else 'medium'
            questions.append({
                'type': question_type,
                'question': question_text,
                'context': {
                    'claim_type': claim_type,
                    'claim_element_id': claim_element_id,
                    'claim_element_label': claim_element_label,
                    'support_status': support_status,
                    'alignment_task': True,
                    'preferred_support_kind': preferred_support_kind,
                    'preferred_evidence_classes': list(task.get('preferred_evidence_classes') or []),
                    'missing_fact_bundle': list(task.get('missing_fact_bundle') or []),
                    'success_criteria': list(task.get('success_criteria') or []),
                    'recommended_queries': recommended_queries,
                },
                'priority': priority,
            })

        for action in workflow_actions:
            if len(questions) >= max_questions:
                break
            if not isinstance(action, dict):
                continue
            phase_name = str(action.get('phase_name') or '').strip().lower()
            if phase_name not in {'graph_analysis', 'document_generation', 'evidence_collection', 'cross_phase'}:
                continue
            action_code = str(action.get('action_code') or '').strip().lower()
            focus_areas = [
                str(item).strip()
                for item in (action.get('focus_areas') or [])
                if str(item).strip()
            ]
            action_text = str(action.get('action') or '').strip()
            if not action_text:
                continue
            claim_type = str(action.get('claim_type') or 'this claim').strip()
            claim_element_id = str(action.get('claim_element_id') or '').strip()
            claim_element_label = str(
                action.get('claim_element_label')
                or claim_element_id
                or (focus_areas[0] if focus_areas else 'this issue')
            ).strip()
            preferred_support_kind = str(action.get('preferred_support_kind') or '').strip().lower()
            missing_fact_bundle = [
                str(item).strip()
                for item in (action.get('missing_fact_bundle') or [])
                if str(item).strip()
            ]
            if action_code == 'recover_document_grounding':
                bundle_hint = (
                    f" I still need grounding facts about {missing_fact_bundle[0]}."
                    if missing_fact_bundle
                    else ''
                )
                if preferred_support_kind == 'authority':
                    question_text = (
                        f"What legal authority, policy, or official document can ground "
                        f"{claim_element_label} for {claim_type}?{bundle_hint}"
                    )
                elif preferred_support_kind == 'testimony':
                    question_text = (
                        f"What first-hand testimony or witness detail can ground "
                        f"{claim_element_label} for {claim_type}?{bundle_hint}"
                    )
                else:
                    question_text = (
                        f"What evidence would best ground {claim_element_label} for {claim_type}?{bundle_hint}"
                    )
            elif action_code == 'refine_document_grounding_strategy':
                suggested_support_kind = str(action.get('suggested_support_kind') or '').strip().lower()
                alternate_support_kinds = [
                    str(item).strip().lower()
                    for item in (action.get('alternate_support_kinds') or [])
                    if str(item).strip()
                ]
                next_lane = suggested_support_kind or (alternate_support_kinds[0] if alternate_support_kinds else '')
                if next_lane == 'authority':
                    question_text = (
                        f"The last grounding pass did not improve enough. What legal authority, policy, or official document can better ground "
                        f"{claim_element_label} for {claim_type}?"
                    )
                elif next_lane == 'testimony':
                    question_text = (
                        f"The last grounding pass did not improve enough. What first-hand testimony or witness detail can better ground "
                        f"{claim_element_label} for {claim_type}?"
                    )
                else:
                    question_text = (
                        f"The last grounding pass did not improve enough. What stronger evidence can better ground "
                        f"{claim_element_label} for {claim_type}?"
                    )
            else:
                question_text = (
                    f"What evidence would best help us {action_text.lower()}"
                    + (f" Focus first on {focus_areas[0]}." if focus_areas else "")
                )
            questions.append({
                'question': self._with_empathy(question_text, 'evidence_clarification'),
                'type': 'evidence_clarification',
                'context': {
                    'workflow_action': True,
                    'workflow_phase': phase_name,
                    'workflow_rank': int(action.get('rank', 0) or 0),
                    'workflow_focus_areas': focus_areas,
                    'action_code': action_code,
                    'claim_type': claim_type,
                    'claim_element_id': claim_element_id,
                    'claim_element_label': claim_element_label,
                    'preferred_support_kind': preferred_support_kind,
                    'suggested_support_kind': str(action.get('suggested_support_kind') or '').strip().lower(),
                    'alternate_support_kinds': list(action.get('alternate_support_kinds') or []),
                    'missing_fact_bundle': missing_fact_bundle,
                    'document_grounding_recovery': action_code == 'recover_document_grounding',
                    'document_grounding_strategy_refinement': action_code == 'refine_document_grounding_strategy',
                },
                'priority': 'high',
                'proof_priority': 0,
            })

        # Questions about missing evidence
        remaining_slots = max(0, max_questions - len(questions))
        for gap in evidence_gaps[:remaining_slots]:
            questions.append({
                'type': 'evidence_clarification',
                'question': f"Do you have evidence to support: {gap.get('name', 'this claim')}?",
                'context': {
                    'gap_id': gap.get('id'),
                    'claim_id': gap.get('related_claim'),
                    'gap_type': gap.get('type', 'missing_evidence')
                },
                'priority': 'high'
            })
        
        # Questions about evidence quality/completeness
        evidence_entities = knowledge_graph.get_entities_by_type('evidence')
        for evidence in evidence_entities[:max(0, max_questions - len(questions))]:
            if evidence.confidence < 0.7:
                questions.append({
                    'type': 'evidence_quality',
                    'question': f"Can you provide more details about this evidence: {evidence.name}?",
                    'context': {
                        'evidence_id': evidence.id,
                        'evidence_name': evidence.name,
                        'confidence': evidence.confidence
                    },
                    'priority': 'medium'
                })
        
        return questions[:max_questions]
    
    def generate_legal_matching_questions(self,
                                         matching_results: Dict[str, Any],
                                         max_questions: int = 5) -> List[Dict[str, Any]]:
        """
        Generate denoising questions for legal matching phase.
        
        Args:
            matching_results: Results from neurosymbolic matching
            max_questions: Maximum questions to generate
            
        Returns:
            List of legal-focused denoising questions
        """
        questions = []
        
        # Questions about unsatisfied legal requirements
        unmatched = matching_results.get('unmatched_requirements', [])
        for req in unmatched[:max_questions]:
            questions.append({
                'type': 'legal_requirement',
                'question': f"To satisfy the legal requirement '{req.get('name')}', can you provide: {req.get('missing_info', 'additional information')}?",
                'context': {
                    'requirement_id': req.get('id'),
                    'requirement_name': req.get('name'),
                    'legal_element': req.get('element_type')
                },
                'priority': 'high'
            })
        
        # Questions about weak matches
        weak_matches = [m for m in matching_results.get('matches', []) 
                       if m.get('confidence', 1.0) < 0.6]
        for match in weak_matches[:max(0, max_questions - len(questions))]:
            questions.append({
                'type': 'legal_strengthening',
                'question': f"Can you provide more information to strengthen the claim for: {match.get('claim_name')}?",
                'context': {
                    'claim_id': match.get('claim_id'),
                    'legal_requirement': match.get('requirement_name'),
                    'confidence': match.get('confidence')
                },
                'priority': 'medium'
            })
        
        return questions[:max_questions]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of denoising progress."""
        return {
            'questions_asked': len(self.questions_asked),
            'questions_remaining': len(self.questions_pool),
            'exhausted': self.is_exhausted()
        }
    
    def synthesize_complaint_summary(self,
                                    knowledge_graph: KnowledgeGraph,
                                    conversation_history: List[Dict[str, Any]],
                                    evidence_list: List[Dict[str, Any]] = None) -> str:
        """
        Synthesize a human-readable summary from knowledge graph, chat transcripts, 
        and evidence without exposing raw graph structures.
        
        This implements the denoising diffusion pattern by progressively refining
        the narrative from structured data.
        
        Args:
            knowledge_graph: The complaint knowledge graph
            conversation_history: List of conversation exchanges
            evidence_list: Optional list of evidence items
            
        Returns:
            Human-readable complaint summary
        """
        summary_parts = []
        
        # Extract key entities
        people = knowledge_graph.get_entities_by_type('person')
        organizations = knowledge_graph.get_entities_by_type('organization')
        claims = knowledge_graph.get_entities_by_type('claim')
        facts = knowledge_graph.get_entities_by_type('fact')
        
        # Build narrative introduction
        if people or organizations:
            summary_parts.append("## Parties Involved")
            for person in people[:5]:  # Limit to key people
                summary_parts.append(f"- {person.name}: {person.attributes.get('role', 'individual')}")
            for org in organizations[:5]:
                summary_parts.append(f"- {org.name}: {org.attributes.get('role', 'organization')}")
            summary_parts.append("")
        
        # Summarize the complaint nature
        if claims:
            summary_parts.append("## Nature of Complaint")
            for claim in claims:
                claim_type = claim.attributes.get('claim_type', 'general')
                description = claim.attributes.get('description', claim.name)
                summary_parts.append(f"- **{claim.name}** ({claim_type}): {description}")
            summary_parts.append("")
        
        # Key facts from graph
        if facts:
            summary_parts.append("## Key Facts")
            high_conf_facts = [f for f in facts if f.confidence > 0.7]
            for fact in high_conf_facts[:10]:  # Top 10 confident facts
                summary_parts.append(f"- {fact.name}")
            summary_parts.append("")
        
        # Evidence summary
        if evidence_list and len(evidence_list) > 0:
            summary_parts.append("## Available Evidence")
            for evidence in evidence_list[:10]:
                ename = evidence.get('name', 'Evidence item')
                etype = evidence.get('type', 'document')
                summary_parts.append(f"- {ename} ({etype})")
            summary_parts.append("")
        
        # Key insights from conversation
        if conversation_history and len(conversation_history) > 0:
            summary_parts.append("## Additional Context from Discussion")
            # Extract key clarifications
            clarifications = [msg for msg in conversation_history 
                            if msg.get('type') == 'response' and len(msg.get('content', '')) > 50]
            for clarif in clarifications[:5]:  # Top 5 meaningful clarifications
                content = clarif.get('content', '')[:200]  # Limit length
                if len(clarif.get('content', '')) > 200:
                    content += "..."
                summary_parts.append(f"- {content}")
            summary_parts.append("")
        
        # Completeness assessment
        kg_summary = knowledge_graph.summary()
        completeness = "high" if kg_summary['total_entities'] > 10 else "moderate" if kg_summary['total_entities'] > 5 else "developing"
        summary_parts.append(f"**Complaint Status:** Information gathering {completeness}ly complete with {kg_summary['total_entities']} key elements identified.")
        
        return "\n".join(summary_parts)


    # ------------------------------------------------------------------ #
    # Batch 206: Question history and policy analysis methods            #
    # ------------------------------------------------------------------ #

    def total_questions_asked(self) -> int:
        """Return total number of questions asked during denoising.

        Returns:
            Count of questions in history.
        """
        return len(self.questions_asked)

    def question_pool_size(self) -> int:
        """Return current size of the question pool.

        Returns:
            Number of candidate questions available.
        """
        return len(self.questions_pool)

    def question_type_frequency(self) -> dict:
        """Count frequency of each question type asked.

        Returns:
            Dict mapping question types to occurrence counts.
        """
        type_counts: dict = {}
        for q in self.questions_asked:
            qtype = q.get('type', 'unknown')
            type_counts[qtype] = type_counts.get(qtype, 0) + 1
        return type_counts

    def most_frequent_question_type(self) -> str:
        """Identify the most frequently asked question type.

        Returns:
            Name of most common question type, or 'none' if no questions asked.
        """
        freq = self.question_type_frequency()
        if not freq:
            return 'none'
        return max(freq.items(), key=lambda x: x[1])[0]

    def average_gain_per_question(self) -> float:
        """Calculate average gain across recent questions.

        Returns:
            Mean of recent gains, or 0.0 if no gains recorded.
        """
        if not self._recent_gains:
            return 0.0
        return sum(self._recent_gains) / len(self._recent_gains)

    def gain_variance(self) -> float:
        """Calculate variance of gains across recent questions.

        Returns:
            Variance of _recent_gains, or 0.0 if fewer than 2 gains.
        """
        if len(self._recent_gains) < 2:
            return 0.0
        mean = sum(self._recent_gains) / len(self._recent_gains)
        variance = sum((g - mean) ** 2 for g in self._recent_gains) / len(self._recent_gains)
        return variance

    def momentum_enabled_for_types(self) -> list:
        """List question types with momentum tracking enabled.

        Returns:
            List of question types with EMA state.
        """
        return list(self._type_gain_ema.keys())

    def highest_momentum_type(self) -> str:
        """Identify question type with highest momentum (EMA gain).

        Returns:
            Question type with max EMA, or 'none' if no momentum tracked.
        """
        if not self._type_gain_ema:
            return 'none'
        return max(self._type_gain_ema.items(), key=lambda x: x[1])[0]

    def is_exploration_active(self) -> bool:
        """Check if exploration mode is currently enabled.

        Returns:
            True if exploration_enabled is True.
        """
        return self.exploration_enabled

    def stagnation_detection_window(self) -> int:
        """Return the configured stagnation detection window size.

        Returns:
            Number of recent gains to check for stagnation.
        """
        return self.stagnation_window


    # =====================================================================
    # Batch 219: Question-answer interaction analysis methods
    # =====================================================================
    
    def total_answers_received(self) -> int:
        """Return total number of answers received.
        
        Returns:
            Count of questions with answers in history.
        """
        return len(self.questions_asked)
    
    def questions_by_priority(self, priority: str) -> int:
        """Count questions asked with a specific priority level.
        
        Args:
            priority: Priority level to filter by (e.g., 'high', 'medium', 'low')
            
        Returns:
            Number of questions with that priority.
        """
        count = 0
        for item in self.questions_asked:
            q = item.get('question', {})
            if q.get('priority') == priority:
                count += 1
        return count
    
    def priority_distribution(self) -> Dict[str, int]:
        """Get frequency distribution of question priorities.
        
        Returns:
            Dict mapping priority levels to occurrence counts.
        """
        dist: Dict[str, int] = {}
        for item in self.questions_asked:
            q = item.get('question', {})
            priority = q.get('priority', 'unknown')
            dist[priority] = dist.get(priority, 0) + 1
        return dist
    
    def unanswered_pool_questions(self) -> int:
        """Return count of questions in pool waiting to be asked.
        
        Returns:
            Size of the questions_pool.
        """
        return len(self.questions_pool)
    
    def questions_with_context(self) -> int:
        """Count questions that have context information.
        
        Returns:
            Number of asked questions with non-empty context dict.
        """
        count = 0
        for item in self.questions_asked:
            q = item.get('question', {})
            context = q.get('context', {})
            if context:
                count += 1
        return count
    
    def average_answer_length(self) -> float:
        """Calculate average length of answers received.
        
        Returns:
            Mean normalized character count of answers, or 0.0 if none.
        """
        if not self.questions_asked:
            return 0.0

        total_length = sum(
            self._normalized_answer_length(item.get('answer', ''))
            for item in self.questions_asked
        )
        return total_length / len(self.questions_asked)

    @staticmethod
    def _normalized_answer_length(answer: str) -> int:
        """Return the raw character length for an answer."""
        if not answer:
            return 0
        return len(str(answer))
    
    def shortest_answer(self) -> int:
        """Find the length of the shortest answer received.
        
        Returns:
            Minimum answer length, or 0 if no answers.
        """
        if not self.questions_asked:
            return 0
        return min(
            self._normalized_answer_length(item.get('answer', ''))
            for item in self.questions_asked
        )
    
    def longest_answer(self) -> int:
        """Find the length of the longest answer received.
        
        Returns:
            Maximum answer length, or 0 if no answers.
        """
        if not self.questions_asked:
            return 0
        return max(
            self._normalized_answer_length(item.get('answer', ''))
            for item in self.questions_asked
        )
    
    def question_type_priority_matrix(self) -> Dict[str, Dict[str, int]]:
        """Build matrix showing priority distribution per question type.
        
        Returns:
            Nested dict: {question_type: {priority: count}}
        """
        matrix: Dict[str, Dict[str, int]] = {}
        for item in self.questions_asked:
            q = item.get('question', {})
            qtype = q.get('type', 'unknown')
            priority = q.get('priority', 'unknown')
            
            if qtype not in matrix:
                matrix[qtype] = {}
            matrix[qtype][priority] = matrix[qtype].get(priority, 0) + 1
        
        return matrix
    
    def recent_question_types(self, n: int = 5) -> List[str]:
        """Get the types of the most recent n questions.
        
        Args:
            n: Number of recent questions to examine
            
        Returns:
            List of question types in reverse chronological order.
        """
        recent = self.questions_asked[-n:] if n <= len(self.questions_asked) else self.questions_asked
        return [item.get('question', {}).get('type', 'unknown') for item in reversed(recent)]
