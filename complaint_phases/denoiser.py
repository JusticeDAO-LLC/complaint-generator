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
        # Keep this minimal so we don't overwhelm the prompt.
        text = (question_text or "").strip()
        if not text:
            return text
        prefix = ""
        if question_type in {'clarification', 'relationship', 'requirement'}:
            prefix = "To make sure I understand, "
        elif question_type in {'evidence'}:
            prefix = "So we can support your claim, "
        if prefix and not text.lower().startswith(prefix.strip().lower()):
            return prefix + text[0].lower() + text[1:] if len(text) > 1 else prefix + text.lower()
        return text

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

        return defaults

    def _build_phase1_question(
        self,
        *,
        question_type: str,
        question_text: str,
        context: Optional[Dict[str, Any]] = None,
        priority: str = 'medium',
        question_intent: Optional[Dict[str, Any]] = None,
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
        payload.update(self._phase1_question_targeting(question_type, payload['context']))
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
        )
        question_payload['candidate_source'] = source
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
        }
        return question_payload

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

        for claim in candidate_claims:
            if not isinstance(claim, dict):
                continue
            claim_type = str(claim.get('claim_type') or '').strip()
            claim_label = str(claim.get('label') or claim_type or 'this claim').strip()
            for element in claim.get('required_elements', []) or []:
                if not isinstance(element, dict):
                    continue
                if str(element.get('status') or '').strip().lower() == 'present':
                    continue
                element_id = str(element.get('element_id') or '').strip()
                element_label = str(element.get('label') or element_id or 'this missing element').strip()
                question_key = f"{claim_type}:{element_id}:{element_label}".lower()
                if question_key in seen_keys:
                    continue
                seen_keys.add(question_key)
                question_intent = build_claim_element_question_intent(
                    claim_type,
                    claim_label,
                    {
                        'element_id': element_id,
                        'label': element_label,
                        'blocking': bool(element.get('blocking', False)),
                        'actor_roles': list(element.get('actor_roles', []) or []),
                        'evidence_classes': list(element.get('evidence_classes', []) or []),
                    },
                )
                question_text = build_claim_element_question_text(
                    claim_type,
                    claim_label,
                    element_id,
                    element_label,
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
                        },
                        priority='high' if bool(element.get('blocking', False)) else 'medium',
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
        if isinstance(proof_leads, list) and proof_leads:
            return []

        questions: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()
        candidate_claims = intake_case_file.get('candidate_claims', [])
        if not isinstance(candidate_claims, list):
            return []

        for claim in candidate_claims:
            if not isinstance(claim, dict):
                continue
            claim_type = str(claim.get('claim_type') or '').strip()
            claim_label = str(claim.get('label') or claim_type or 'this claim').strip()
            question_key = f"{claim_type}:{claim_label}:proof_leads".lower()
            if question_key in seen_keys:
                continue
            seen_keys.add(question_key)
            question_intent = build_proof_lead_question_intent(claim_type, claim_label)
            question_text = build_proof_lead_question_text(claim_type, claim_label)
            if not self._already_asked(question_text):
                questions.append(self._question_candidate(
                    source='intake_proof_gap',
                    question_type='evidence',
                    question_text=question_text,
                    context={
                        'claim_type': claim_type,
                        'claim_name': claim_label,
                    },
                    priority='high',
                    question_intent=question_intent,
                ))
            if len(questions) >= max_questions:
                return questions[:max_questions]

        return questions

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
                    },
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

        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        questions.sort(
            key=lambda q: (
                int(q.get('proof_priority', self._phase1_proof_priority(q.get('type', '')))),
                priority_order.get(q.get('priority', 'low'), 3),
            )
        )
        return questions[:max_questions]

    def _default_candidate_sort_key(self, candidate: Dict[str, Any]) -> Tuple[int, int]:
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        if not isinstance(candidate, dict):
            return (99, 99)
        return (
            int(candidate.get('proof_priority', self._phase1_proof_priority(candidate.get('type', '')))),
            priority_order.get(candidate.get('priority', 'low'), 3),
        )

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
                return normalized_selected

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
                    added.append(self._build_phase1_question(
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
                    added.append(self._build_phase1_question(
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
                        added.append(self._build_phase1_question(
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

        question_type = question.get('type')
        context = question.get('context', {})
        answer_text = str(answer or '').strip()
        timeline_enrichment_types = {'clarification', 'evidence', 'impact', 'relationship', 'remedy', 'requirement', 'responsible_party', 'timeline'}
        responsible_party_enrichment_types = {'clarification', 'evidence', 'relationship', 'requirement', 'responsible_party', 'timeline'}
        fallback_timeline_fact_types = {'clarification', 'evidence', 'relationship', 'requirement', 'responsible_party', 'timeline'}

        def _single_claim_id() -> Optional[str]:
            claims = knowledge_graph.get_entities_by_type('claim')
            return claims[0].id if len(claims) == 1 else None

        def _apply_timeline_enrichment() -> None:
            nonlocal updates
            if question_type not in timeline_enrichment_types or not answer_text:
                return
            claim_id = _single_claim_id()
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
                return
            if question_type not in fallback_timeline_fact_types:
                return
            claim_id = _single_claim_id()
            snippet = self._short_description(answer_text, 120)
            fact_name = f"Timeline detail: {self._short_description(answer_text, 60)}"
            fact_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                fact_name,
                {'fact_type': 'timeline', 'description': snippet},
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

        if question_type == 'clarification':
            entity_id = context.get('entity_id')
            entity = knowledge_graph.get_entity(entity_id)
            if entity:
                entity.confidence = min(1.0, entity.confidence + 0.2)
                entity.attributes['clarification'] = answer
                updates['entities_updated'] += 1

        elif question_type == 'relationship':
            entity_id = context.get('entity_id')
            if entity_id and len(answer_text) > 10:
                entity = knowledge_graph.get_entity(entity_id)
                if entity:
                    entity.attributes['relationship_described'] = True
                    updates['entities_updated'] += 1

        elif question_type == 'responsible_party':
            pass

        elif question_type == 'evidence':
            claim_id = context.get('claim_id')
            entity = knowledge_graph.get_entity(claim_id)
            if entity:
                if 'evidence_descriptions' not in entity.attributes:
                    entity.attributes['evidence_descriptions'] = []
                entity.attributes['evidence_descriptions'].append(answer)
                updates['entities_updated'] += 1
            if not claim_id:
                claim_id = _single_claim_id()
            if claim_id and len(answer_text) > 10:
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

        elif question_type == 'timeline':
            pass

        elif question_type in {'impact', 'remedy'}:
            if answer_text:
                claim_id = _single_claim_id()
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
            if dependency_graph:
                req_id = context.get('requirement_id')
                req_node = dependency_graph.get_node(req_id)
                if req_node and len(answer_text) > 10:
                    req_node.satisfied = True
                    req_node.confidence = 0.7
                    updates['requirements_satisfied'] += 1

        if question_type in responsible_party_enrichment_types and answer_text:
            updates = self._update_responsible_parties_from_answer(answer_text, knowledge_graph, updates)

        if question_type in timeline_enrichment_types and answer_text:
            _apply_timeline_enrichment()

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
            total_confidence = sum(e.confidence for e in knowledge_graph.entities.values())
            kg_confidence = total_confidence / len(knowledge_graph.entities)
        
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
                                   max_questions: int = 5) -> List[Dict[str, Any]]:
        """
        Generate denoising questions for evidence phase.
        
        Args:
            knowledge_graph: Current knowledge graph
            dependency_graph: Current dependency graph
            evidence_gaps: Identified evidence gaps
            alignment_evidence_tasks: Shared intake/evidence element tasks to prioritize
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
