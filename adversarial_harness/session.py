"""
Adversarial Session Module

Manages a single adversarial training session between complainant and mediator.
"""

import logging
import re
from contextlib import contextmanager
from typing import Dict, Any, List, Set, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import time

logger = logging.getLogger(__name__)


@dataclass
class SessionResult:
    """Result of an adversarial session."""
    session_id: str
    timestamp: str
    
    # Input
    seed_complaint: Dict[str, Any]
    initial_complaint_text: str
    
    # Conversation
    conversation_history: List[Dict[str, Any]]
    num_questions: int
    num_turns: int
    
    # Outputs
    final_state: Dict[str, Any]
    knowledge_graph_summary: Dict[str, Any] = None
    dependency_graph_summary: Dict[str, Any] = None

    # Optional full graph snapshots (may be large); persisted as separate JSON files.
    knowledge_graph: Dict[str, Any] | None = None
    dependency_graph: Dict[str, Any] | None = None
    
    # Evaluation
    critic_score: Any = None  # CriticScore object
    
    # Timing
    duration_seconds: float = 0.0
    
    # Status
    success: bool = True
    error: str = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        critic_payload = self.critic_score.to_dict() if self.critic_score else None
        result = {
            'session_id': self.session_id,
            'timestamp': self.timestamp,
            'seed_complaint': self.seed_complaint,
            'initial_complaint_text': self.initial_complaint_text,
            'conversation_history': self.conversation_history,
            'num_questions': self.num_questions,
            'num_turns': self.num_turns,
            'final_state': self.final_state,
            'knowledge_graph_summary': self.knowledge_graph_summary,
            'dependency_graph_summary': self.dependency_graph_summary,
            'knowledge_graph': self.knowledge_graph,
            'dependency_graph': self.dependency_graph,
            'critic_score': critic_payload,
            'anchor_section_summary': {
                'expected': list((critic_payload or {}).get('anchor_sections_expected', []) or []),
                'covered': list((critic_payload or {}).get('anchor_sections_covered', []) or []),
                'missing': list((critic_payload or {}).get('anchor_sections_missing', []) or []),
            },
            'duration_seconds': self.duration_seconds,
            'success': self.success,
            'error': self.error
        }
        return result


class AdversarialSession:
    """
    Manages a single adversarial training session.
    
    A session consists of:
    1. Complainant generates initial complaint from seed
    2. Mediator processes complaint and asks questions
    3. Complainant responds to questions
    4. Repeat until completion (convergence or max turns)
    5. Critic evaluates the session
    """
    
    def __init__(self,
                  session_id: str,
                  complainant: Any,  # Complainant instance
                  mediator: Any,  # Mediator instance
                  critic: Any,  # Critic instance
                max_turns: int = 12):
        """
        Initialize adversarial session.
        
        Args:
            session_id: Unique session identifier
            complainant: Complainant instance
            mediator: Mediator instance
            critic: Critic instance
            max_turns: Maximum number of question-answer turns
        """
        self.session_id = session_id
        self.complainant = complainant
        self.mediator = mediator
        self.critic = critic
        self.max_turns = max_turns
        
        self.conversation_history = []
        self.start_time = None
        self.end_time = None

    @staticmethod
    def _extract_question_text(question: Any) -> str:
        if isinstance(question, dict):
            for key in ('question', 'text', 'prompt', 'content'):
                value = question.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            nested_question = question.get('question')
            if isinstance(nested_question, dict):
                for key in ('text', 'content'):
                    value = nested_question.get(key)
                    if isinstance(value, str) and value.strip():
                        return value
            return ''
        return str(question)

    @staticmethod
    def _extract_question_objective(question: Any) -> str:
        if not isinstance(question, dict):
            return ''
        objective = question.get('question_objective')
        if isinstance(objective, str) and objective.strip():
            return objective.strip().lower()
        nested_question = question.get('question')
        if isinstance(nested_question, dict):
            nested_objective = nested_question.get('question_objective')
            if isinstance(nested_objective, str) and nested_objective.strip():
                return nested_objective.strip().lower()
        return ''

    @staticmethod
    def _extract_question_type(question: Any) -> str:
        if not isinstance(question, dict):
            return ''
        question_type = question.get('type')
        if isinstance(question_type, str) and question_type.strip():
            return question_type.strip().lower()
        nested_question = question.get('question')
        if isinstance(nested_question, dict):
            nested_type = nested_question.get('type')
            if isinstance(nested_type, str) and nested_type.strip():
                return nested_type.strip().lower()
        return ''

    @staticmethod
    def _normalize_question(question_text: str) -> str:
        return " ".join(question_text.lower().strip().split())

    @staticmethod
    def _strip_leading_wrapper_clauses(question_text: str) -> str:
        """Remove conversational lead-ins that often vary across rephrases."""
        cleaned = question_text.strip()
        wrapper_patterns = (
            r"i (?:understand|am sorry|know|appreciate)[^,]*,\s*",
            r"(?:thanks|thank you)[^,]*,\s*",
            r"(?:before we continue|to clarify|just to clarify|to better understand|so i can help)[^,]*,\s*",
        )
        changed = True
        while cleaned and changed:
            changed = False
            for pattern in wrapper_patterns:
                updated = re.sub(rf"^\s*{pattern}", "", cleaned)
                if updated != cleaned:
                    cleaned = updated.strip()
                    changed = True
        return cleaned

    @staticmethod
    def _question_dedupe_key(question_text: str) -> str:
        normalized = AdversarialSession._normalize_question(question_text)
        normalized = AdversarialSession._strip_leading_wrapper_clauses(normalized)
        # Strip common numbering/list prefixes.
        normalized = re.sub(r"^(?:q(?:uestion)?\s*\d+[:.)-]\s*|\d+[:.)-]\s*)", "", normalized)
        # Strip conversational wrappers so semantically identical prompts
        # map to a stable key when politeness/empathy phrasing varies.
        normalized = re.sub(
            r"^(i (?:understand|am sorry|know|appreciate)[^,]*,\s*)",
            "",
            normalized,
        )
        normalized = re.sub(
            r"^(can you|could you|would you|please|just|let me ask|help me understand)\s+",
            "",
            normalized,
        )
        normalized = re.sub(
            r"^(?:can|could|would)\s+you\s+(?:tell me|share|describe|explain|clarify|walk me through)\s+",
            "",
            normalized,
        )
        normalized = re.sub(
            r"^(?:tell me|share|describe|explain|clarify|walk me through)\s+",
            "",
            normalized,
        )
        normalized = re.sub(r"\s+(please|thanks?)$", "", normalized)
        normalized = re.sub(r"\s+(?:if you can|if possible|when you can)$", "", normalized)
        # Remove punctuation differences so "when did X happen?" and "when did X happen"
        # map to the same dedupe key.
        return " ".join(re.sub(r"[^a-z0-9\s]", " ", normalized).split())

    @staticmethod
    def _question_tokens(question_text: str) -> Set[str]:
        key = AdversarialSession._question_dedupe_key(question_text)
        tokens = set(key.split())
        # Ignore low-information tokens so overlap focuses on intent/content.
        stopwords = {
            "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "at",
            "is", "are", "was", "were", "be", "been", "it", "this", "that", "your",
            "you", "can", "could", "would", "did", "do", "does", "please", "about",
            "what", "when", "where", "who", "how", "why", "any",
        }
        return {t for t in tokens if t and t not in stopwords}

    @staticmethod
    def _question_similarity(question_a: str, question_b: str) -> float:
        tokens_a = AdversarialSession._question_tokens(question_a)
        tokens_b = AdversarialSession._question_tokens(question_b)
        if not tokens_a and not tokens_b:
            return 1.0
        if not tokens_a or not tokens_b:
            return 0.0
        overlap = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(overlap) / len(union)

    @staticmethod
    def _question_intent_key(question_text: str, question: Any = None) -> str:
        objective = AdversarialSession._extract_question_objective(question)
        if objective:
            context = question.get('context', {}) if isinstance(question, dict) and isinstance(question.get('context'), dict) else {}
            context_segments = []
            for key in ('requirement_id', 'claim_id', 'entity_id'):
                value = context.get(key)
                if value:
                    context_segments.append(str(value))
            question_type = AdversarialSession._extract_question_type(question)
            base = objective if not question_type else f"{objective}:{question_type}"
            if context_segments:
                return base + ':' + ':'.join(context_segments)
            return base
        normalized = AdversarialSession._question_dedupe_key(question_text)
        stop_words = {
            'a', 'an', 'and', 'are', 'can', 'could', 'did', 'do', 'for', 'from',
            'have', 'how', 'i', 'if', 'in', 'is', 'it', 'me', 'of', 'on', 'or',
            'please', 'share', 'tell', 'that', 'the', 'to', 'was', 'what', 'when',
            'where', 'which', 'who', 'why', 'with', 'would', 'you', 'your',
        }
        tokens = []
        for token in normalized.split():
            if token in stop_words:
                continue
            if token.endswith('ing') and len(token) > 5:
                token = token[:-3]
            elif token.endswith('ed') and len(token) > 4:
                token = token[:-2]
            elif token.endswith('s') and len(token) > 3:
                token = token[:-1]
            tokens.append(token)
        if not tokens:
            return normalized
        return " ".join(tokens)

    @staticmethod
    def _is_redundant_candidate(
        key: str,
        intent_key: str,
        asked_count: int,
        intent_count: int,
        similarity_to_seen: float,
        last_question_key: str | None,
        last_question_intent_key: str | None,
        recent_intent_keys: Set[str] | None = None,
    ) -> bool:
        # Never ask the exact same question back-to-back.
        if key == last_question_key:
            return True
        # Avoid asking the same normalized question more than once.
        if asked_count > 0:
            return True
        # Treat near-identical rephrasings as redundant even when intent bucketing differs.
        if similarity_to_seen >= 0.9:
            return True
        # Avoid immediate intent repetition when it's already substantially similar.
        if (
            last_question_intent_key
            and intent_key == last_question_intent_key
            and similarity_to_seen >= 0.5
        ):
            return True
        # Avoid repeatedly circling the same intent across nearby turns.
        if recent_intent_keys and intent_key in recent_intent_keys and similarity_to_seen >= 0.5:
            return True
        # De-prioritize high-overlap variants once an intent has been asked.
        if intent_count > 0 and similarity_to_seen >= 0.68:
            return True
        return False

    @staticmethod
    def _is_timeline_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        if objective == 'establish_chronology' or question_type == 'timeline':
            return True
        text = AdversarialSession._extract_question_text(question).lower()
        timeline_terms = (
            'when',
            'date',
            'timeline',
            'chronolog',
            'sequence',
            'what happened first',
            'before',
            'after',
            'when did',
            'date range',
            'how long',
            'start date',
            'end date',
            'first happened',
            'step by step',
            'walk me through',
            'date anchor',
            'decision timeline',
            'actor by actor',
            'actor-by-actor',
        )
        return any(term in text for term in timeline_terms)

    @staticmethod
    def _is_harm_or_remedy_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        if objective == 'capture_harm_and_requested_remedy' or question_type in {'impact', 'remedy'}:
            return True
        text = AdversarialSession._extract_question_text(question).lower()
        harm_remedy_terms = (
            'harm',
            'impact',
            'affected',
            'damag',
            'loss',
            'distress',
            'remedy',
            'resolve',
            'outcome',
            'seeking',
            'requesting',
            'want',
            'relief',
            'fix',
            'refund',
            'reimburse',
            'compensation',
            'cost',
            'out of pocket',
            'financial',
            'lost wages',
            'make you whole',
            'repair',
            'replace',
            'accommodation',
        )
        return any(term in text for term in harm_remedy_terms)

    @staticmethod
    def _is_actor_or_decisionmaker_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        if objective == 'identify_responsible_party' or question_type == 'responsible_party':
            return True
        text = AdversarialSession._extract_question_text(question).lower()
        actor_terms = (
            'who',
            'manager',
            'supervisor',
            'decision',
            'hr',
            'human resources',
            'person',
            'individual',
            'name',
            'landlord',
            'owner',
            'employer',
            'staff',
            'employee',
            'representative',
            'agent',
            'contractor',
            'provider',
            'point of contact',
            'contact person',
        )
        return any(term in text for term in actor_terms)

    @staticmethod
    def _is_protected_activity_causation_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        if objective in {'establish_causation', 'link_protected_activity_to_adverse_action'}:
            return True
        if question_type in {'causation', 'retaliation'}:
            return True
        text = AdversarialSession._extract_question_text(question).lower()
        protected_activity_terms = (
            'protected activity',
            'complaint',
            'reported',
            'accommodation request',
            'grievance',
            'appeal',
        )
        adverse_terms = (
            'adverse action',
            'retaliat',
            'termination',
            'denial',
            'disciplin',
        )
        causation_terms = (
            'because',
            'after',
            'linked',
            'caus',
            'reason',
            'connection',
        )
        return (
            any(term in text for term in protected_activity_terms)
            and any(term in text for term in adverse_terms)
            and any(term in text for term in causation_terms)
        )

    @staticmethod
    def _is_documentary_evidence_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        text = AdversarialSession._extract_question_text(question).lower()
        if objective == 'identify_supporting_evidence' and question_type == 'evidence':
            return True
        document_terms = (
            'document',
            'email',
            'text message',
            'notice',
            'letter',
            'written',
            'record',
            'records',
            'screenshot',
            'attachment',
            'paperwork',
            'file',
            'contract',
            'agreement',
            'estimate',
            'invoice',
            'receipt',
            'lease',
            'application',
            'screening criteria',
            'policy',
            'warranty',
            'change order',
            'work order',
            'photo',
            'photos',
            'picture',
            'video',
            'payment',
            'check',
            'bank statement',
            'message',
            'messages',
            'chat',
            'communication',
            'communications',
            'call',
            'call log',
            'voicemail',
            'report',
        )
        return any(term in text for term in document_terms)

    @staticmethod
    def _is_witness_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        witness_terms = (
            'witness',
            'anyone else',
            'who else',
            'present',
            'saw',
            'heard',
            'observer',
            'coworker',
            'anyone with you',
            'anyone there',
            'others there',
            'bystander',
        )
        return any(term in text for term in witness_terms)

    @staticmethod
    def _is_contradiction_resolution_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        if objective == 'resolve_factual_contradiction' or question_type == 'contradiction':
            return True
        text = AdversarialSession._extract_question_text(question).lower()
        contradiction_terms = (
            'conflicting information',
            'which version is correct',
            'contradiction',
            'inconsistent',
            'conflict',
        )
        return any(term in text for term in contradiction_terms)

    @staticmethod
    def _extract_phase1_section(question: Any) -> str:
        if not isinstance(question, dict):
            return ''
        phase1_section = question.get('phase1_section')
        if isinstance(phase1_section, str) and phase1_section.strip():
            return phase1_section.strip().lower()
        explanation = question.get('ranking_explanation')
        if isinstance(explanation, dict):
            nested = explanation.get('phase1_section')
            if isinstance(nested, str) and nested.strip():
                return nested.strip().lower()
        return ''

    @staticmethod
    def _phase_focus_rank_for_candidate(question: Any) -> int:
        phase1_section = AdversarialSession._extract_phase1_section(question)
        return {
            'graph_analysis': 0,
            'intake_questioning': 1,
            'document_generation': 2,
            # Compatibility with denoiser section labels.
            'contradictions': 0,
            'chronology': 0,
            'actors': 0,
            'claim_elements': 0,
            'proof_leads': 0,
            'harm_remedy': 1,
            'general': 1,
        }.get(phase1_section, 3)

    @staticmethod
    def _is_exact_dates_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        if AdversarialSession._is_timeline_question(question):
            return True
        date_tokens = (
            'exact date',
            'specific date',
            'what date',
            'on what date',
            'date did',
            'date was',
            'month and year',
            'mm/dd',
            'date anchor',
        )
        return any(token in text for token in date_tokens)

    @staticmethod
    def _is_staff_names_titles_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        if not any(token in text for token in ('who', 'name', 'staff', 'person', 'manager', 'supervisor', 'decision')):
            return False
        title_tokens = ('title', 'job title', 'role', 'position')
        return any(token in text for token in title_tokens) or AdversarialSession._is_actor_or_decisionmaker_question(question)

    @staticmethod
    def _is_hearing_request_timing_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        hearing_tokens = ('hearing', 'grievance', 'appeal', 'review')
        timing_tokens = ('when', 'date', 'timing', 'timeline', 'after', 'before', 'deadline', 'requested')
        return any(token in text for token in hearing_tokens) and any(token in text for token in timing_tokens)

    @staticmethod
    def _is_response_dates_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        response_tokens = ('respond', 'response', 'notice', 'decision', 'outcome', 'reply', 'letter')
        date_tokens = ('when', 'date', 'dated', 'timeline', 'how long', 'days later')
        return any(token in text for token in response_tokens) and any(token in text for token in date_tokens)

    @staticmethod
    def _is_causation_sequence_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        if AdversarialSession._is_protected_activity_causation_question(question):
            return True
        protected_activity_tokens = ('protected activity', 'complaint', 'reported', 'accommodation', 'grievance', 'appeal')
        adverse_tokens = ('adverse', 'retaliat', 'denial', 'termination', 'disciplin')
        sequencing_tokens = ('before', 'after', 'sequence', 'timeline', 'what happened first', 'step by step')
        return (
            any(token in text for token in protected_activity_tokens)
            and any(token in text for token in adverse_tokens)
            and any(token in text for token in sequencing_tokens)
        )

    @staticmethod
    def _coverage_gap_rank(
        question: Any,
        need_timeline: bool,
        need_harm_remedy: bool,
        need_actor_decisionmaker: bool,
        need_causation: bool,
        need_documentary_evidence: bool,
        need_witness: bool,
        need_exact_dates: bool = False,
        need_staff_names_titles: bool = False,
        need_hearing_request_timing: bool = False,
        need_response_dates: bool = False,
        need_causation_sequence: bool = False,
        missing_anchor_sections: Set[str] | None = None,
    ) -> int:
        question_text = AdversarialSession._extract_question_text(question)
        if AdversarialSession._is_contradiction_resolution_question(question):
            return -2
        if missing_anchor_sections and AdversarialSession._question_targets_missing_anchor_section(
            question_text,
            missing_anchor_sections,
        ):
            return -1
        if need_exact_dates and AdversarialSession._is_exact_dates_question(question):
            return 0
        if need_staff_names_titles and AdversarialSession._is_staff_names_titles_question(question):
            return 1
        if need_hearing_request_timing and AdversarialSession._is_hearing_request_timing_question(question):
            return 2
        if need_response_dates and AdversarialSession._is_response_dates_question(question):
            return 3
        if need_causation_sequence and AdversarialSession._is_causation_sequence_question(question):
            return 4
        if need_harm_remedy and AdversarialSession._is_harm_or_remedy_question(question):
            return 5
        if need_timeline and AdversarialSession._is_timeline_question(question):
            return 6
        if need_actor_decisionmaker and AdversarialSession._is_actor_or_decisionmaker_question(question):
            return 7
        if need_causation and AdversarialSession._is_protected_activity_causation_question(question):
            return 8
        if need_documentary_evidence and AdversarialSession._is_documentary_evidence_question(question):
            return 9
        if need_witness and AdversarialSession._is_witness_question(question):
            return 10
        return 11

    @staticmethod
    def _extract_actor_critic_score(question: Any) -> float:
        if not isinstance(question, dict):
            return 0.0
        direct = question.get('actor_critic_score')
        if isinstance(direct, (int, float)):
            return float(direct)
        explanation = question.get('ranking_explanation')
        if isinstance(explanation, dict):
            nested = explanation.get('actor_critic_score')
            if isinstance(nested, (int, float)):
                return float(nested)
        return 0.0

    @staticmethod
    def _extract_selector_score(question: Any) -> float:
        if not isinstance(question, dict):
            return 0.0
        direct = question.get('selector_score')
        if isinstance(direct, (int, float)):
            return float(direct)
        explanation = question.get('ranking_explanation')
        if isinstance(explanation, dict):
            nested = explanation.get('selector_score')
            if isinstance(nested, (int, float)):
                return float(nested)
        return 0.0

    @staticmethod
    def _extract_selector_signals(question: Any) -> Dict[str, Any]:
        if not isinstance(question, dict):
            return {}
        direct = question.get('selector_signals')
        if isinstance(direct, dict):
            return dict(direct)
        explanation = question.get('ranking_explanation')
        if isinstance(explanation, dict):
            nested = explanation.get('selector_signals')
            if isinstance(nested, dict):
                return dict(nested)
        return {}

    @classmethod
    def _extract_blocker_closure_match_count(cls, question: Any) -> int:
        signals = cls._extract_selector_signals(question)
        direct = signals.get('blocker_closure_match_count')
        if isinstance(direct, (int, float)):
            return int(direct)
        fallback = signals.get('blocker_match_count')
        if isinstance(fallback, (int, float)):
            return int(fallback)
        return 0

    @staticmethod
    def _question_specificity_score(question_text: str) -> float:
        normalized = AdversarialSession._question_dedupe_key(question_text)
        if not normalized:
            return 0.0
        tokens = normalized.split()
        token_count = len(tokens)
        has_interrogative = bool(
            tokens
            and tokens[0]
            in {
                'who',
                'what',
                'when',
                'where',
                'why',
                'how',
                'which',
                'did',
                'does',
                'do',
                'is',
                'are',
                'can',
                'could',
                'would',
            }
        )
        legal_context_tokens = {
            'date',
            'timeline',
            'notice',
            'decision',
            'hearing',
            'appeal',
            'grievance',
            'adverse',
            'accommodation',
            'protected',
            'document',
            'email',
            'message',
            'witness',
            'harm',
            'remedy',
            'staff',
            'title',
        }
        legal_context_hits = sum(1 for token in tokens if token in legal_context_tokens)
        score = 0.0
        if has_interrogative:
            score += 0.35
        score += min(0.45, token_count / 20.0)
        score += min(0.20, legal_context_hits * 0.05)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _question_targets_anchor_section(question_text: str, section: str) -> bool:
        text = question_text.lower()
        section_terms = {
            'grievance_hearing': ('grievance', 'hearing', 'impartial', 'informal hearing'),
            'appeal_rights': ('appeal', 'review', 'due process', 'rights'),
            'reasonable_accommodation': ('reasonable accommodation', 'accommodation', 'disability'),
            'adverse_action': ('termination', 'denial', 'adverse', 'admission', 'occupancy'),
            'selection_criteria': ('selection', 'screening', 'criteria', 'evaluation', 'priority'),
        }
        return any(term in text for term in section_terms.get(section, (section.replace('_', ' '),)))

    @classmethod
    def _question_targets_missing_anchor_section(
        cls,
        question_text: str,
        missing_anchor_sections: Set[str],
    ) -> bool:
        return any(cls._question_targets_anchor_section(question_text, section) for section in missing_anchor_sections)

    @staticmethod
    def _anchor_probe_map() -> Dict[str, tuple[str, str]]:
        return {
            'grievance_hearing': (
                "What grievance or informal hearing process were you told was available, whether you requested it, and who was supposed to handle it?",
                "anchor_grievance_hearing",
            ),
            'appeal_rights': (
                "Were you told you could request a grievance hearing, appeal, review, or other due-process rights, and did you try to use them?",
                "anchor_appeal_rights",
            ),
            'reasonable_accommodation': (
                "Did you request a reasonable accommodation or raise a disability-related need, and how did HACC respond?",
                "anchor_reasonable_accommodation",
            ),
            'adverse_action': (
                "What adverse action happened to you exactly, such as a denial, termination, or other loss of housing benefits?",
                "anchor_adverse_action",
            ),
            'selection_criteria': (
                "What screening, selection, or evaluation criteria were you told were being used in your case?",
                "anchor_selection_criteria",
            ),
        }

    @classmethod
    def _question_objectives_from_prompt(cls, question_text: str) -> List[str]:
        lowered = question_text.lower()
        objectives: List[str] = []
        if any(token in lowered for token in ('exact date', 'specific date', 'what date', 'date anchor', 'month and year')):
            objectives.append('exact_dates')
        if (
            any(token in lowered for token in ('staff', 'name', 'who', 'person', 'manager', 'supervisor', 'decision-maker', 'decision maker'))
            and any(token in lowered for token in ('title', 'role', 'position', 'job title'))
        ):
            objectives.append('staff_names_titles')
        if (
            any(token in lowered for token in ('hearing', 'grievance', 'appeal', 'review'))
            and any(token in lowered for token in ('when', 'date', 'timing', 'requested', 'deadline'))
        ):
            objectives.append('hearing_request_timing')
        if (
            any(token in lowered for token in ('response', 'respond', 'notice', 'decision', 'outcome'))
            and any(token in lowered for token in ('when', 'date', 'dated', 'days later', 'timeline'))
        ):
            objectives.append('response_dates')
        if any(token in lowered for token in ('when', 'date', 'timeline', 'chronology', 'sequence', 'decision timeline')):
            objectives.append('timeline')
        if any(token in lowered for token in ('harm', 'remedy', 'loss', 'relief')):
            objectives.append('harm_remedy')
        if any(token in lowered for token in ('who', 'which person', 'made, communicated', 'carried out')):
            objectives.append('actors')
        if (
            any(token in lowered for token in ('protected activity', 'complaint', 'reported', 'accommodation', 'grievance', 'appeal'))
            and any(token in lowered for token in ('adverse', 'retaliat', 'denial', 'termination'))
            and any(token in lowered for token in ('because', 'after', 'caus', 'reason', 'link'))
        ):
            objectives.append('causation')
        if (
            any(token in lowered for token in ('protected activity', 'complaint', 'reported', 'accommodation', 'grievance', 'appeal'))
            and any(token in lowered for token in ('adverse', 'retaliat', 'denial', 'termination'))
            and any(token in lowered for token in ('before', 'after', 'sequence', 'timeline', 'what happened first'))
        ):
            objectives.append('causation_sequence')
        if any(token in lowered for token in ('email', 'emails', 'document', 'documents', 'notice', 'records', 'messages', 'written')):
            objectives.append('documents')
        if any(token in lowered for token in ('witness', 'witnesses', 'saw or heard')):
            objectives.append('witnesses')

        for section, (_, objective) in cls._anchor_probe_map().items():
            if cls._question_targets_anchor_section(question_text, section):
                objectives.append(objective)

        if not objectives:
            objectives.append('intake_follow_up')

        deduped: List[str] = []
        seen = set()
        for objective in objectives:
            if objective not in seen:
                seen.add(objective)
                deduped.append(objective)
        return deduped

    @staticmethod
    def _extract_anchor_sections(seed_complaint: Dict[str, Any]) -> Set[str]:
        key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
        return {
            str(value) for value in list(key_facts.get('anchor_sections') or []) if str(value)
        }

    @classmethod
    def _covered_anchor_sections_from_questions(
        cls,
        question_keys: Sequence[str],
        expected_anchor_sections: Set[str],
    ) -> Set[str]:
        covered: Set[str] = set()
        for key in question_keys:
            for section in expected_anchor_sections:
                if cls._question_targets_anchor_section(key, section):
                    covered.add(section)
        return covered

    @staticmethod
    def _extract_intake_prompt_candidates(seed_complaint: Dict[str, Any]) -> List[tuple[str, str]]:
        key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
        synthetic_prompts = key_facts.get('synthetic_prompts') if isinstance(key_facts, dict) else {}
        candidates: List[tuple[str, str]] = []
        if isinstance(synthetic_prompts, dict):
            for raw_question in list(synthetic_prompts.get('intake_questions') or []):
                question_text = str(raw_question or '').strip()
                if not question_text:
                    continue
                for objective in AdversarialSession._question_objectives_from_prompt(question_text):
                    candidates.append((question_text, objective))

        expected_anchor_sections = [
            str(value) for value in list(key_facts.get('anchor_sections') or []) if str(value)
        ]
        covered_anchor_objectives = {objective for _, objective in candidates if objective.startswith('anchor_')}
        for section in expected_anchor_sections:
            probe = AdversarialSession._anchor_probe_map().get(section)
            if not probe:
                continue
            probe_text, probe_type = probe
            if probe_type not in covered_anchor_objectives:
                candidates.append((probe_text, probe_type))

        if not candidates:
            return []

        priority = {
            'exact_dates': 0,
            'staff_names_titles': 1,
            'hearing_request_timing': 2,
            'response_dates': 3,
            'anchor_adverse_action': 0,
            'anchor_grievance_hearing': 1,
            'anchor_appeal_rights': 2,
            'anchor_reasonable_accommodation': 3,
            'anchor_selection_criteria': 4,
            'timeline': 6,
            'actors': 7,
            'causation': 8,
            'causation_sequence': 9,
            'documents': 10,
            'witnesses': 11,
            'harm_remedy': 12,
            'intake_follow_up': 13,
        }
        candidates.sort(key=lambda item: (priority.get(item[1], 99), item[0].lower(), item[1]))
        deduped: List[tuple[str, str]] = []
        seen = set()
        for item in candidates:
            key = (item[0].strip().lower(), item[1])
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped

    @staticmethod
    def _seed_requires_causation_probe(seed_complaint: Dict[str, Any]) -> bool:
        key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
        seed_text = " ".join(
            [
                str(seed_complaint.get('summary') or ''),
                str(key_facts.get('incident_summary') or ''),
                " ".join(str(item or '') for item in list(key_facts.get('complainant_story_facts') or [])),
                " ".join(str(item or '') for item in list(key_facts.get('anchor_sections') or [])),
            ]
        ).lower()
        protected_activity_terms = (
            'protected activity',
            'complaint',
            'reported',
            'accommodation',
            'grievance',
            'appeal',
            'retaliat',
        )
        adverse_terms = (
            'adverse',
            'termination',
            'denial',
            'disciplin',
            'evict',
            'nonrenew',
            'suspension',
        )
        return any(term in seed_text for term in protected_activity_terms) and any(
            term in seed_text for term in adverse_terms
        )

    @classmethod
    def _questions_substantially_overlap(cls, question_a: Any, question_b: Any) -> bool:
        text_a = cls._extract_question_text(question_a)
        text_b = cls._extract_question_text(question_b)
        if not text_a or not text_b:
            return False
        key_a = cls._question_dedupe_key(text_a)
        key_b = cls._question_dedupe_key(text_b)
        if key_a and key_a == key_b:
            return True
        intent_a = cls._question_intent_key(text_a, question_a)
        intent_b = cls._question_intent_key(text_b, question_b)
        similarity = cls._question_similarity(text_a, text_b)
        if intent_a and intent_b and intent_a == intent_b and similarity >= 0.35:
            return True
        if cls._is_timeline_question(question_a) and cls._is_timeline_question(question_b) and similarity >= 0.35:
            return True
        return similarity >= 0.72

    @classmethod
    def _inject_intake_prompt_questions(
        cls,
        seed_complaint: Dict[str, Any],
        questions: Sequence[Any],
    ) -> List[Any]:
        merged: List[Any] = []
        seen = set()
        skipped = set()
        existing_questions = list(questions or [])
        for probe_text, probe_type in cls._extract_intake_prompt_candidates(seed_complaint):
            key = cls._question_dedupe_key(probe_text)
            if key and (key in seen or key in skipped):
                continue
            synthetic_question = {
                "question": probe_text,
                "type": probe_type,
                "question_objective": probe_type,
                "question_reason": "Structured intake prompt imported from the grounding bundle.",
                "source": "synthetic_intake_prompt",
            }
            if any(
                cls._questions_substantially_overlap(synthetic_question, existing_question)
                for existing_question in existing_questions
            ):
                if key:
                    skipped.add(key)
                continue
            if key and key not in seen:
                seen.add(key)
                merged.append(synthetic_question)
        for question in existing_questions:
            key = cls._question_dedupe_key(cls._extract_question_text(question))
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            merged.append(question)
        return merged

    @classmethod
    def _candidate_matches_intake_objective(cls, candidate: Any, objective: str) -> bool:
        question_text = cls._extract_question_text(candidate)
        if not question_text:
            return False
        if objective == 'exact_dates':
            return cls._is_exact_dates_question(candidate)
        if objective == 'staff_names_titles':
            return cls._is_staff_names_titles_question(candidate)
        if objective == 'hearing_request_timing':
            return cls._is_hearing_request_timing_question(candidate)
        if objective == 'response_dates':
            return cls._is_response_dates_question(candidate)
        if objective == 'timeline':
            return cls._is_timeline_question(candidate)
        if objective == 'actors':
            return cls._is_actor_or_decisionmaker_question(candidate)
        if objective == 'causation':
            return cls._is_protected_activity_causation_question(candidate)
        if objective == 'causation_sequence':
            return cls._is_causation_sequence_question(candidate)
        if objective == 'harm_remedy':
            return cls._is_harm_or_remedy_question(candidate)
        if objective == 'documents':
            return cls._is_documentary_evidence_question(candidate)
        if objective == 'witnesses':
            return cls._is_witness_question(candidate)
        if objective.startswith('anchor_'):
            return cls._question_targets_anchor_section(question_text, objective.replace('anchor_', '', 1))
        return False

    @classmethod
    def _reprioritize_candidates_for_intake_objectives(
        cls,
        candidates: Sequence[Any],
        seed_complaint: Dict[str, Any],
        *,
        max_questions: int,
    ) -> List[Any]:
        intake_candidates = cls._extract_intake_prompt_candidates(seed_complaint)
        if not intake_candidates:
            return list(candidates or [])[:max_questions]

        objective_priority: Dict[str, int] = {}
        for _, objective in intake_candidates:
            objective_priority.setdefault(objective, len(objective_priority))

        ranked: List[tuple[tuple[Any, ...], Any]] = []
        for index, candidate in enumerate(list(candidates or [])):
            best_priority = len(objective_priority) + 1
            matched_objectives: List[str] = []
            for objective, priority in objective_priority.items():
                if cls._candidate_matches_intake_objective(candidate, objective):
                    matched_objectives.append(objective)
                    if priority < best_priority:
                        best_priority = priority
            selector_score = 0.0
            if isinstance(candidate, dict):
                selector_score = float(candidate.get('selector_score', 0.0) or 0.0)
            proof_priority = 99
            if isinstance(candidate, dict):
                proof_priority = int(candidate.get('proof_priority', 99) or 99)
            phase_focus_rank = cls._phase_focus_rank_for_candidate(candidate)
            actor_critic_score = cls._extract_actor_critic_score(candidate)
            blocker_match_count = 0
            for objective in matched_objectives:
                if objective in {
                    'exact_dates',
                    'staff_names_titles',
                    'hearing_request_timing',
                    'response_dates',
                    'causation_sequence',
                }:
                    blocker_match_count += 1

            annotated_candidate = candidate
            if isinstance(candidate, dict):
                annotated_candidate = dict(candidate)
                explanation = dict(
                    annotated_candidate.get('ranking_explanation', {})
                    if isinstance(annotated_candidate.get('ranking_explanation'), dict)
                    else {}
                )
                selector_signals = dict(
                    annotated_candidate.get('selector_signals', {})
                    if isinstance(annotated_candidate.get('selector_signals'), dict)
                    else {}
                )
                selector_signals['intake_priority_match'] = matched_objectives
                selector_signals['intake_priority_rank'] = None if not matched_objectives else best_priority
                selector_signals['phase_focus_rank'] = phase_focus_rank
                selector_signals['actor_critic_score'] = actor_critic_score
                selector_signals['blocker_match_count'] = blocker_match_count
                annotated_candidate['selector_signals'] = selector_signals
                explanation['intake_priority_match'] = matched_objectives
                explanation['intake_priority_rank'] = None if not matched_objectives else best_priority
                explanation['phase_focus_rank'] = phase_focus_rank
                explanation['actor_critic_score'] = actor_critic_score
                explanation['blocker_match_count'] = blocker_match_count
                annotated_candidate['ranking_explanation'] = explanation

            ranked.append(
                (
                    (
                        best_priority,
                        phase_focus_rank,
                        -blocker_match_count,
                        -selector_score,
                        -actor_critic_score,
                        proof_priority,
                        index,
                    ),
                    annotated_candidate,
                )
            )

        ranked.sort(key=lambda item: item[0])
        return [candidate for _, candidate in ranked[:max_questions]]

    @classmethod
    def _summarize_intake_priority_coverage(
        cls,
        questions: Sequence[Any],
        seed_complaint: Dict[str, Any],
    ) -> Dict[str, Any]:
        intake_candidates = cls._extract_intake_prompt_candidates(seed_complaint)
        expected_objectives: List[str] = []
        for _, objective in intake_candidates:
            if objective not in expected_objectives:
                expected_objectives.append(objective)

        coverage_counts: Dict[str, int] = {}
        for objective in expected_objectives:
            coverage_counts[objective] = 0

        for question in list(questions or []):
            for objective in expected_objectives:
                if cls._candidate_matches_intake_objective(question, objective):
                    coverage_counts[objective] = coverage_counts.get(objective, 0) + 1

        covered_objectives = [
            objective for objective in expected_objectives if coverage_counts.get(objective, 0) > 0
        ]
        uncovered_objectives = [
            objective for objective in expected_objectives if coverage_counts.get(objective, 0) <= 0
        ]
        return {
            "expected_objectives": expected_objectives,
            "covered_objectives": covered_objectives,
            "uncovered_objectives": uncovered_objectives,
            "objective_question_counts": coverage_counts,
        }

    def _persist_intake_priority_summary(
        self,
        seed_complaint: Dict[str, Any],
        initial_questions: Sequence[Any],
    ) -> None:
        phase_manager = getattr(self.mediator, "phase_manager", None)
        update_phase_data = getattr(phase_manager, "update_phase_data", None)
        if not callable(update_phase_data):
            return
        try:
            from complaint_phases import ComplaintPhase
        except Exception:
            return

        summary = self._summarize_intake_priority_coverage(initial_questions, seed_complaint)
        try:
            update_phase_data(ComplaintPhase.INTAKE, "current_questions", list(initial_questions or []))
            update_phase_data(ComplaintPhase.INTAKE, "adversarial_intake_priority_summary", summary)
        except Exception:
            logger.debug("Could not persist intake-priority summary into mediator phase state", exc_info=True)

    @contextmanager
    def _temporarily_prioritize_mediator_intake_objectives(self, seed_complaint: Dict[str, Any]):
        original_selector = getattr(self.mediator, 'select_intake_question_candidates', None)
        if not callable(original_selector):
            yield
            return

        def selector_with_intake_priority(candidates: List[Dict[str, Any]], *, max_questions: int = 10):
            try:
                selected = original_selector(candidates, max_questions=len(candidates or []))
            except TypeError:
                selected = original_selector(candidates)
            if not isinstance(selected, list):
                selected = list(candidates or [])
            return self._reprioritize_candidates_for_intake_objectives(
                selected,
                seed_complaint,
                max_questions=max_questions,
            )

        setattr(self.mediator, 'select_intake_question_candidates', selector_with_intake_priority)
        try:
            yield
        finally:
            setattr(self.mediator, 'select_intake_question_candidates', original_selector)

    def _build_fallback_probe(
        self,
        seed_complaint: Dict[str, Any],
        asked_question_counts: Dict[str, int],
        asked_intent_counts: Dict[str, int],
        need_timeline: bool,
        need_harm_remedy: bool,
        need_actor_decisionmaker: bool,
        need_causation: bool,
        need_documentary_evidence: bool,
        need_witness: bool,
        need_exact_dates: bool,
        need_staff_names_titles: bool,
        need_hearing_request_timing: bool,
        need_response_dates: bool,
        need_causation_sequence: bool,
        last_question_key: str | None,
        last_question_intent_key: str | None,
        recent_intent_keys: Set[str],
        missing_anchor_sections: Set[str],
    ) -> Dict[str, Any] | None:
        probe_candidates: List[tuple[str, str]] = []
        intake_prompt_candidates = self._extract_intake_prompt_candidates(seed_complaint)
        for probe_text, probe_type in intake_prompt_candidates:
            if probe_type == 'timeline' and not need_timeline:
                continue
            if probe_type == 'harm_remedy' and not need_harm_remedy:
                continue
            if probe_type == 'actors' and not need_actor_decisionmaker:
                continue
            if probe_type == 'causation' and not need_causation:
                continue
            if probe_type == 'documents' and not need_documentary_evidence:
                continue
            if probe_type == 'witnesses' and not need_witness:
                continue
            if probe_type == 'anchor_appeal_rights' and 'appeal_rights' not in missing_anchor_sections:
                continue
            if probe_type == 'anchor_grievance_hearing' and 'grievance_hearing' not in missing_anchor_sections:
                continue
            if probe_type == 'anchor_reasonable_accommodation' and 'reasonable_accommodation' not in missing_anchor_sections:
                continue
            if probe_type == 'anchor_adverse_action' and 'adverse_action' not in missing_anchor_sections:
                continue
            if probe_type == 'anchor_selection_criteria' and 'selection_criteria' not in missing_anchor_sections:
                continue
            probe_candidates.append((probe_text, probe_type))
        for section in sorted(missing_anchor_sections):
            probe = self._anchor_probe_map().get(section)
            if probe:
                probe_candidates.append(probe)
        if need_exact_dates:
            probe_candidates.append((
                "What exact dates or best month/year anchors do you have for each key event, including notices and decisions?",
                "exact_dates",
            ))
        if need_staff_names_titles:
            probe_candidates.append((
                "Which HACC staff members were involved at each step, and what were their names and titles or roles?",
                "staff_names_titles",
            ))
        if need_hearing_request_timing:
            probe_candidates.append((
                "When did you request a grievance hearing or appeal, how did you request it, and what was the timing relative to the adverse action?",
                "hearing_request_timing",
            ))
        if need_response_dates:
            probe_candidates.append((
                "What response dates did you receive for notices, hearing or appeal requests, and the final decision?",
                "response_dates",
            ))
        if need_harm_remedy:
            probe_candidates.append((
                "What concrete harms did this cause you, and what specific remedy are you requesting?",
                "harm_remedy",
            ))
        if need_timeline:
            probe_candidates.append((
                "What are the most precise dates or date ranges for each key event, starting with the first incident?",
                "timeline",
            ))
        if need_actor_decisionmaker:
            probe_candidates.append((
                "Who specifically made each decision or statement, and what exactly was said or done?",
                "actors",
            ))
        if need_causation:
            probe_candidates.append((
                "What protected activity happened first, what adverse action followed, who made each decision, and what facts show the adverse action happened because of that protected activity?",
                "causation",
            ))
        if need_causation_sequence:
            probe_candidates.append((
                "Please walk through the sequence step by step: protected activity, who learned about it, adverse action, and how timing or statements link them.",
                "causation_sequence",
            ))
        if need_documentary_evidence:
            probe_candidates.append((
                "Do you have any supporting records such as emails, messages, notices, or other written documents?",
                "documents",
            ))
        if need_witness:
            probe_candidates.append((
                "Were there any witnesses who saw or heard these events, and how can they be identified?",
                "witnesses",
            ))

        if not probe_candidates:
            return None

        seen_question_keys = [k for k, count in asked_question_counts.items() if count > 0]
        for probe_text, probe_type in probe_candidates:
            key = self._question_dedupe_key(probe_text)
            intent_key = self._question_intent_key(probe_text)
            asked_count = asked_question_counts.get(key, 0)
            intent_count = asked_intent_counts.get(intent_key, 0)
            similarity_to_seen = 0.0
            if seen_question_keys:
                similarity_to_seen = max(
                    self._question_similarity(probe_text, seen_key)
                    for seen_key in seen_question_keys
                )
            if self._is_redundant_candidate(
                key=key,
                intent_key=intent_key,
                asked_count=asked_count,
                intent_count=intent_count,
                similarity_to_seen=similarity_to_seen,
                last_question_key=last_question_key,
                last_question_intent_key=last_question_intent_key,
                recent_intent_keys=recent_intent_keys,
            ):
                continue
            return {
                "question": probe_text,
                "type": probe_type,
                "question_objective": probe_type,
                "question_reason": "Harness fallback probe to cover a missing intake objective.",
                "source": "harness_fallback",
            }
        return None

    @staticmethod
    def _has_empathy_prefix(question_text: str) -> bool:
        text = question_text.lower()
        empathy_markers = (
            "i understand",
            "i'm sorry",
            "i am sorry",
            "i know this is",
            "that sounds",
            "i appreciate",
            "thank you for sharing",
        )
        return any(marker in text for marker in empathy_markers)

    @staticmethod
    def _with_empathy_prefix(question_text: str) -> str:
        text = question_text.strip()
        if not text:
            return text
        if AdversarialSession._has_empathy_prefix(text):
            return text
        return (
            "I understand this can be stressful, and these details help me support you. "
            + text
        )

    @classmethod
    def _should_apply_empathy_prefix(cls, turn_index: int, question: Any) -> bool:
        if turn_index <= 1:
            return True
        return (
            cls._is_harm_or_remedy_question(question)
            or cls._is_protected_activity_causation_question(question)
            or cls._is_contradiction_resolution_question(question)
        )

    def _select_next_question(
        self,
        questions: List[Any],
        asked_question_counts: Dict[str, int],
        asked_intent_counts: Dict[str, int],
        need_timeline: bool,
        need_harm_remedy: bool,
        need_actor_decisionmaker: bool,
        need_causation: bool,
        need_documentary_evidence: bool,
        need_witness: bool,
        need_exact_dates: bool,
        need_staff_names_titles: bool,
        need_hearing_request_timing: bool,
        need_response_dates: bool,
        need_causation_sequence: bool,
        last_question_key: str | None,
        last_question_intent_key: str | None,
        recent_intent_keys: Set[str],
        missing_anchor_sections: Set[str],
    ) -> Any:
        if not questions:
            return None

        seen_question_keys = [k for k, count in asked_question_counts.items() if count > 0]
        candidate_keys_in_turn: Set[str] = set()
        novel_similarity_threshold = 0.7
        rephrase_similarity_threshold = 0.65
        candidates = []
        for q in questions:
            text = self._extract_question_text(q)
            key = self._question_dedupe_key(text)
            if not key or key in candidate_keys_in_turn:
                # Skip empty and duplicate prompts emitted in the same mediator step.
                continue
            candidate_keys_in_turn.add(key)
            intent_key = self._question_intent_key(text, q)
            asked_count = asked_question_counts.get(key, 0)
            intent_count = asked_intent_counts.get(intent_key, 0)
            similarity_to_seen = 0.0
            if seen_question_keys:
                similarity_to_seen = max(
                    self._question_similarity(text, seen_key)
                    for seen_key in seen_question_keys
                )
            candidates.append((
                q,
                text,
                key,
                intent_key,
                asked_count,
                intent_count,
                similarity_to_seen,
            ))

        if not candidates:
            return None

        non_redundant_candidates = [
            c for c in candidates
            if not self._is_redundant_candidate(
                key=c[2],
                intent_key=c[3],
                asked_count=c[4],
                intent_count=c[5],
                similarity_to_seen=c[6],
                last_question_key=last_question_key,
                last_question_intent_key=last_question_intent_key,
                recent_intent_keys=recent_intent_keys,
            )
        ]
        for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                self._is_contradiction_resolution_question(q)
                and asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
            ):
                return q
        if need_timeline:
            has_timeline_candidate = any(
                self._is_timeline_question(c[0]) for c in non_redundant_candidates
            )
            if not has_timeline_candidate:
                return None

        if need_documentary_evidence:
            has_document_candidate = any(
                self._is_documentary_evidence_question(c[0]) for c in non_redundant_candidates
            )
            if not has_document_candidate:
                return None
        # Prefer filling high-value information gaps before exploring lower-value variants.
        high_quality_candidates = [
            c
            for c in non_redundant_candidates
            if (
                self._question_specificity_score(c[1]) >= 0.4
                or self._extract_actor_critic_score(c[0]) >= 0.2
                or self._extract_selector_score(c[0]) > 0.0
            )
        ]
        if high_quality_candidates:
            non_redundant_candidates = high_quality_candidates
        non_redundant_candidates.sort(
            key=lambda c: (
                self._coverage_gap_rank(
                    c[0],
                    need_timeline=need_timeline,
                    need_harm_remedy=need_harm_remedy,
                    need_actor_decisionmaker=need_actor_decisionmaker,
                    need_causation=need_causation,
                    need_documentary_evidence=need_documentary_evidence,
                    need_witness=need_witness,
                    need_exact_dates=need_exact_dates,
                    need_staff_names_titles=need_staff_names_titles,
                    need_hearing_request_timing=need_hearing_request_timing,
                    need_response_dates=need_response_dates,
                    need_causation_sequence=need_causation_sequence,
                    missing_anchor_sections=missing_anchor_sections,
                ),
                self._phase_focus_rank_for_candidate(c[0]),
                -self._extract_blocker_closure_match_count(c[0]),
                -self._extract_selector_score(c[0]),
                -self._extract_actor_critic_score(c[0]),
                c[5],
                c[4],
                c[6],
            )
        )
        if need_exact_dates:
            for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_exact_dates_question(q)
                ):
                    return q
        if need_staff_names_titles:
            for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_staff_names_titles_question(q)
                ):
                    return q
        if need_hearing_request_timing:
            for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_hearing_request_timing_question(q)
                ):
                    return q
        if need_response_dates:
            for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_response_dates_question(q)
                ):
                    return q
        if need_causation_sequence:
            for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_causation_sequence_question(q)
                ):
                    return q

        if need_harm_remedy:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_harm_or_remedy_question(q)
                ):
                    return q

        if need_timeline:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_timeline_question(q)
                ):
                    return q

        if need_actor_decisionmaker:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_actor_or_decisionmaker_question(q)
                ):
                    return q

        if need_causation:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_protected_activity_causation_question(q)
                ):
                    return q

        if need_documentary_evidence:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_documentary_evidence_question(q)
                ):
                    return q

        if need_witness:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_witness_question(q)
                ):
                    return q

        for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
            ):
                return q

        # Fall back to any unseen question if all options are close in wording.
        for q, _, _, _, asked_count, intent_count, _ in non_redundant_candidates:
            if asked_count == 0 and intent_count == 0:
                return q

        if need_timeline or need_harm_remedy:
            for q, text, key, _, asked_count, _, _ in candidates:
                if asked_count > 0 or key == last_question_key:
                    continue
                if need_timeline and self._is_timeline_question(q):
                    return q
                if need_harm_remedy and self._is_harm_or_remedy_question(q):
                    return q

        # As a last resort, allow one rephrase on a covered intent only if we still
        # need timeline or harm/remedy coverage and the wording is meaningfully different.
        for q, text, key, _, asked_count, intent_count, similarity_to_seen in candidates:
            if (
                asked_count == 0
                and intent_count == 1
                and key != last_question_key
                and similarity_to_seen < rephrase_similarity_threshold
                and (
                    (need_timeline and self._is_timeline_question(q))
                    or (need_harm_remedy and self._is_harm_or_remedy_question(q))
                )
            ):
                return q

        return None
    
    def run(self, seed_complaint: Dict[str, Any]) -> SessionResult:
        """
        Run a complete session.
        
        Args:
            seed_complaint: Seed data for complaint generation
            
        Returns:
            SessionResult with complete session data
        """
        logger.info(f"Starting session {self.session_id}")
        self.start_time = time.time()
        
        try:
            # Step 1: Generate initial complaint
            initial_complaint = self.complainant.generate_initial_complaint(seed_complaint)
            logger.debug(f"Initial complaint generated: {initial_complaint[:100]}...")
            
            # Step 2: Initialize mediator with complaint
            with self._temporarily_prioritize_mediator_intake_objectives(seed_complaint):
                result = self.mediator.start_three_phase_process(initial_complaint)
            if isinstance(result, dict):
                result['initial_questions'] = self._inject_intake_prompt_questions(
                    seed_complaint,
                    result.get('initial_questions', []),
                )
                self._persist_intake_priority_summary(
                    seed_complaint,
                    result.get('initial_questions', []),
                )
            
            # Step 3: Iteratively ask and answer questions
            questions_asked = 0
            turns = 0
            asked_question_keys: Set[str] = set()
            asked_question_counts: Dict[str, int] = {}
            asked_intent_counts: Dict[str, int] = {}
            last_question_key: str | None = None
            last_question_intent_key: str | None = None
            recent_intent_keys: List[str] = []
            recent_intent_window = 3
            has_timeline_question = False
            has_harm_remedy_question = False
            has_actor_or_decisionmaker_question = False
            has_causation_question = False
            has_documentary_evidence_question = False
            has_witness_question = False
            has_exact_dates_question = False
            has_staff_names_titles_question = False
            has_hearing_request_timing_question = False
            has_response_dates_question = False
            has_causation_sequence_question = False
            expected_anchor_sections = self._extract_anchor_sections(seed_complaint)
            require_causation_probe = self._seed_requires_causation_probe(seed_complaint)
            require_hearing_timing_probe = bool(expected_anchor_sections & {'grievance_hearing', 'appeal_rights'})
            require_response_dates_probe = bool(expected_anchor_sections & {'grievance_hearing', 'appeal_rights', 'adverse_action'})
            
            while turns < self.max_turns:
                # Get questions from mediator
                questions = result.get('initial_questions', []) if turns == 0 else \
                           result.get('next_questions', [])
                covered_anchor_sections = self._covered_anchor_sections_from_questions(
                    asked_question_keys,
                    expected_anchor_sections,
                )
                missing_anchor_sections = expected_anchor_sections - covered_anchor_sections

                need_timeline = not has_timeline_question
                need_harm_remedy = not has_harm_remedy_question
                need_actor_decisionmaker = not has_actor_or_decisionmaker_question
                need_causation = require_causation_probe and not has_causation_question
                need_documentary_evidence = not has_documentary_evidence_question
                need_witness = not has_witness_question
                need_exact_dates = not has_exact_dates_question
                need_staff_names_titles = not has_staff_names_titles_question
                need_hearing_request_timing = require_hearing_timing_probe and not has_hearing_request_timing_question
                need_response_dates = require_response_dates_probe and not has_response_dates_question
                need_causation_sequence = require_causation_probe and not has_causation_sequence_question

                question = None
                if questions:
                    # Ask a non-repeated question when available and prioritize key coverage gaps.
                    question = self._select_next_question(
                        questions=questions,
                        asked_question_counts=asked_question_counts,
                        asked_intent_counts=asked_intent_counts,
                        need_timeline=need_timeline,
                        need_harm_remedy=need_harm_remedy,
                        need_actor_decisionmaker=need_actor_decisionmaker,
                        need_causation=need_causation,
                        need_documentary_evidence=need_documentary_evidence,
                        need_witness=need_witness,
                        need_exact_dates=need_exact_dates,
                        need_staff_names_titles=need_staff_names_titles,
                        need_hearing_request_timing=need_hearing_request_timing,
                        need_response_dates=need_response_dates,
                        need_causation_sequence=need_causation_sequence,
                        last_question_key=last_question_key,
                        last_question_intent_key=last_question_intent_key,
                        recent_intent_keys=set(recent_intent_keys),
                        missing_anchor_sections=missing_anchor_sections,
                    )

                if question is None:
                    question = self._build_fallback_probe(
                        seed_complaint,
                        asked_question_counts=asked_question_counts,
                        asked_intent_counts=asked_intent_counts,
                        need_timeline=need_timeline,
                        need_harm_remedy=need_harm_remedy,
                        need_actor_decisionmaker=need_actor_decisionmaker,
                        need_causation=need_causation,
                        need_documentary_evidence=need_documentary_evidence,
                        need_witness=need_witness,
                        need_exact_dates=need_exact_dates,
                        need_staff_names_titles=need_staff_names_titles,
                        need_hearing_request_timing=need_hearing_request_timing,
                        need_response_dates=need_response_dates,
                        need_causation_sequence=need_causation_sequence,
                        last_question_key=last_question_key,
                        last_question_intent_key=last_question_intent_key,
                        recent_intent_keys=set(recent_intent_keys),
                        missing_anchor_sections=missing_anchor_sections,
                    )
                    if question is not None:
                        logger.debug("Using harness fallback probe for missing coverage")

                if question is None:
                    if not questions:
                        logger.info(f"No more questions, session complete after {turns} turns")
                    else:
                        logger.info(
                            "Only repeated questions remain and no useful fallback probe was available; ending session at turn %s",
                            turns,
                        )
                    break
                question_text = self._extract_question_text(question)
                question_objective = self._extract_question_objective(question)
                question_reason = ''
                if isinstance(question, dict):
                    question_reason = str(question.get('question_reason') or '').strip()
                expected_proof_gain = ''
                if isinstance(question, dict):
                    expected_proof_gain = str(question.get('expected_proof_gain') or '').strip()
                question_key = self._question_dedupe_key(question_text)
                question_intent_key = self._question_intent_key(question_text, question)
                if question_key in asked_question_keys:
                    logger.debug("Mediator repeated question (no non-repeated alternative available)")
                logger.debug(f"Mediator asks: {question_text}")

                # Get response from complainant
                complainant_prompt = question_text
                if self._should_apply_empathy_prefix(turns, question):
                    complainant_prompt = self._with_empathy_prefix(question_text)
                answer = self.complainant.respond_to_question(
                    complainant_prompt
                )
                logger.debug(f"Complainant answers: {answer[:100]}...")

                mediator_turn = {
                    'role': 'mediator',
                    'type': 'question',
                    'content': question_text,
                }
                if question_objective:
                    mediator_turn['question_objective'] = question_objective
                if question_reason:
                    mediator_turn['question_reason'] = question_reason
                if expected_proof_gain:
                    mediator_turn['expected_proof_gain'] = expected_proof_gain
                selector_score = self._extract_selector_score(question)
                if selector_score:
                    mediator_turn['selector_score'] = selector_score
                actor_critic_score = self._extract_actor_critic_score(question)
                if actor_critic_score:
                    mediator_turn['actor_critic_score'] = actor_critic_score
                phase1_section = self._extract_phase1_section(question)
                if phase1_section:
                    mediator_turn['phase1_section'] = phase1_section
                selector_signals = self._extract_selector_signals(question)
                if selector_signals:
                    candidate_source = str(selector_signals.get('candidate_source') or '').strip()
                    if candidate_source:
                        mediator_turn['candidate_source'] = candidate_source
                    intake_matches = selector_signals.get('intake_priority_match')
                    if isinstance(intake_matches, list) and intake_matches:
                        mediator_turn['intake_priority_match'] = list(intake_matches)
                self.conversation_history.append(mediator_turn)

                self.conversation_history.append(
                    {
                        'role': 'complainant',
                        'type': 'answer',
                        'content': answer,
                    }
                )
                
                # Process answer with mediator
                result = self.mediator.process_denoising_answer(question, answer)

                asked_question_keys.add(question_key)
                asked_question_counts[question_key] = asked_question_counts.get(question_key, 0) + 1
                asked_intent_counts[question_intent_key] = asked_intent_counts.get(question_intent_key, 0) + 1
                last_question_key = question_key
                last_question_intent_key = question_intent_key
                if question_intent_key:
                    recent_intent_keys.append(question_intent_key)
                    if len(recent_intent_keys) > recent_intent_window:
                        recent_intent_keys = recent_intent_keys[-recent_intent_window:]
                if self._is_timeline_question(question):
                    has_timeline_question = True
                if self._is_harm_or_remedy_question(question):
                    has_harm_remedy_question = True
                if self._is_actor_or_decisionmaker_question(question):
                    has_actor_or_decisionmaker_question = True
                if self._is_protected_activity_causation_question(question):
                    has_causation_question = True
                if self._is_documentary_evidence_question(question):
                    has_documentary_evidence_question = True
                if self._is_witness_question(question):
                    has_witness_question = True
                if self._is_exact_dates_question(question):
                    has_exact_dates_question = True
                if self._is_staff_names_titles_question(question):
                    has_staff_names_titles_question = True
                if self._is_hearing_request_timing_question(question):
                    has_hearing_request_timing_question = True
                if self._is_response_dates_question(question):
                    has_response_dates_question = True
                if self._is_causation_sequence_question(question):
                    has_causation_sequence_question = True
                
                questions_asked += 1
                turns += 1
                
                # Check if converged
                converged = result.get('converged', False) or result.get('ready_for_evidence_phase', False)
                has_core_coverage = has_timeline_question and has_harm_remedy_question
                has_evidence_coverage = (
                    has_actor_or_decisionmaker_question
                    or has_causation_question
                    or has_documentary_evidence_question
                    or has_witness_question
                )
                has_causation_coverage = (not require_causation_probe) or has_causation_question
                has_blocker_coverage = (
                    has_exact_dates_question
                    and has_staff_names_titles_question
                    and ((not require_hearing_timing_probe) or has_hearing_request_timing_question)
                    and ((not require_response_dates_probe) or has_response_dates_question)
                    and ((not require_causation_probe) or has_causation_sequence_question)
                )
                if converged and has_core_coverage and has_evidence_coverage and has_causation_coverage and has_blocker_coverage:
                    logger.info(f"Session converged after {turns} turns")
                    break
            
            # Step 4: Get final state
            final_state = self.mediator.get_three_phase_status()
            
            # Get graph summaries if available
            kg_summary = None
            dg_summary = None
            kg_dict = None
            dg_dict = None
            try:
                from complaint_phases import ComplaintPhase
                kg = self.mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
                dg = self.mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
                if kg:
                    kg_summary = kg.summary()
                    try:
                        kg_dict = kg.to_dict()
                    except Exception:
                        kg_dict = None
                if dg:
                    dg_summary = dg.summary()
                    try:
                        dg_dict = dg.to_dict()
                    except Exception:
                        dg_dict = None
            except Exception as e:
                logger.warning(f"Could not get graph summaries: {e}")
            
            # Step 5: Evaluate with critic
            conversation_history = self.complainant.get_conversation_history()
            critic_score = self.critic.evaluate_session(
                initial_complaint,
                conversation_history,
                final_state,
                context=seed_complaint
            )
            
            self.end_time = time.time()
            duration = self.end_time - self.start_time
            
            # Build result
            result = SessionResult(
                session_id=self.session_id,
                timestamp=datetime.now(UTC).isoformat(),
                seed_complaint=seed_complaint,
                initial_complaint_text=initial_complaint,
                conversation_history=conversation_history,
                num_questions=questions_asked,
                num_turns=turns,
                final_state=final_state,
                knowledge_graph_summary=kg_summary,
                dependency_graph_summary=dg_summary,
                knowledge_graph=kg_dict,
                dependency_graph=dg_dict,
                critic_score=critic_score,
                duration_seconds=duration,
                success=True
            )
            
            logger.info(f"Session {self.session_id} completed successfully. "
                       f"Score: {critic_score.overall_score:.3f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Session {self.session_id} failed: {e}", exc_info=True)
            self.end_time = time.time()
            duration = self.end_time - self.start_time if self.start_time else 0
            
            return SessionResult(
                session_id=self.session_id,
                timestamp=datetime.now(UTC).isoformat(),
                seed_complaint=seed_complaint,
                initial_complaint_text="",
                conversation_history=[],
                num_questions=0,
                num_turns=0,
                final_state={},
                duration_seconds=duration,
                success=False,
                error=str(e)
            )
