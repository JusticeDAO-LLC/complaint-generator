"""
Adversarial Session Module

Manages a single adversarial training session between complainant and mediator.
"""

import logging
import re
from typing import Dict, Any, List, Set
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
            'critic_score': self.critic_score.to_dict() if self.critic_score else None,
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
    def _question_intent_key(question_text: str) -> str:
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
    def _is_timeline_question(question_text: str) -> bool:
        text = question_text.lower()
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
        )
        return any(term in text for term in timeline_terms)

    @staticmethod
    def _is_harm_or_remedy_question(question_text: str) -> bool:
        text = question_text.lower()
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
    def _is_actor_or_decisionmaker_question(question_text: str) -> bool:
        text = question_text.lower()
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
    def _is_documentary_evidence_question(question_text: str) -> bool:
        text = question_text.lower()
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
    def _is_witness_question(question_text: str) -> bool:
        text = question_text.lower()
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
    def _coverage_gap_rank(
        question_text: str,
        need_timeline: bool,
        need_harm_remedy: bool,
        need_actor_decisionmaker: bool,
        need_documentary_evidence: bool,
        need_witness: bool,
    ) -> int:
        if need_harm_remedy and AdversarialSession._is_harm_or_remedy_question(question_text):
            return 0
        if need_timeline and AdversarialSession._is_timeline_question(question_text):
            return 1
        if need_actor_decisionmaker and AdversarialSession._is_actor_or_decisionmaker_question(question_text):
            return 2
        if need_documentary_evidence and AdversarialSession._is_documentary_evidence_question(question_text):
            return 3
        if need_witness and AdversarialSession._is_witness_question(question_text):
            return 4
        return 5

    def _build_fallback_probe(
        self,
        asked_question_counts: Dict[str, int],
        asked_intent_counts: Dict[str, int],
        need_timeline: bool,
        need_harm_remedy: bool,
        need_actor_decisionmaker: bool,
        need_documentary_evidence: bool,
        need_witness: bool,
        last_question_key: str | None,
        last_question_intent_key: str | None,
        recent_intent_keys: Set[str],
    ) -> Dict[str, Any] | None:
        probe_candidates: List[tuple[str, str]] = []
        if need_timeline:
            probe_candidates.append((
                "What are the most precise dates or date ranges for each key event, starting with the first incident?",
                "timeline",
            ))
        if need_harm_remedy:
            probe_candidates.append((
                "What concrete harms did this cause you, and what specific remedy are you requesting?",
                "harm_remedy",
            ))
        if need_actor_decisionmaker:
            probe_candidates.append((
                "Who specifically made each decision or statement, and what exactly was said or done?",
                "actors",
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

    def _select_next_question(
        self,
        questions: List[Any],
        asked_question_counts: Dict[str, int],
        asked_intent_counts: Dict[str, int],
        need_timeline: bool,
        need_harm_remedy: bool,
        need_actor_decisionmaker: bool,
        need_documentary_evidence: bool,
        need_witness: bool,
        last_question_key: str | None,
        last_question_intent_key: str | None,
        recent_intent_keys: Set[str],
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
            intent_key = self._question_intent_key(text)
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
        if need_timeline:
            has_timeline_candidate = any(
                self._is_timeline_question(c[1]) for c in non_redundant_candidates
            )
            if not has_timeline_candidate:
                return None

        if need_documentary_evidence:
            has_document_candidate = any(
                self._is_documentary_evidence_question(c[1]) for c in non_redundant_candidates
            )
            if not has_document_candidate:
                return None
        # Prefer filling high-value information gaps before exploring lower-value variants.
        non_redundant_candidates.sort(
            key=lambda c: (
                self._coverage_gap_rank(
                    c[1],
                    need_timeline=need_timeline,
                    need_harm_remedy=need_harm_remedy,
                    need_actor_decisionmaker=need_actor_decisionmaker,
                    need_documentary_evidence=need_documentary_evidence,
                    need_witness=need_witness,
                ),
                c[5],
                c[4],
                c[6],
            )
        )

        if need_harm_remedy:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_harm_or_remedy_question(text)
                ):
                    return q

        if need_timeline:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_timeline_question(text)
                ):
                    return q

        if need_actor_decisionmaker:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_actor_or_decisionmaker_question(text)
                ):
                    return q

        if need_documentary_evidence:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_documentary_evidence_question(text)
                ):
                    return q

        if need_witness:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_witness_question(text)
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
                if need_timeline and self._is_timeline_question(text):
                    return q
                if need_harm_remedy and self._is_harm_or_remedy_question(text):
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
                    (need_timeline and self._is_timeline_question(text))
                    or (need_harm_remedy and self._is_harm_or_remedy_question(text))
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
            result = self.mediator.start_three_phase_process(initial_complaint)
            
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
            has_documentary_evidence_question = False
            has_witness_question = False
            
            while turns < self.max_turns:
                # Get questions from mediator
                questions = result.get('initial_questions', []) if turns == 0 else \
                           result.get('next_questions', [])

                need_timeline = not has_timeline_question
                need_harm_remedy = not has_harm_remedy_question
                need_actor_decisionmaker = not has_actor_or_decisionmaker_question
                need_documentary_evidence = not has_documentary_evidence_question
                need_witness = not has_witness_question

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
                        need_documentary_evidence=need_documentary_evidence,
                        need_witness=need_witness,
                        last_question_key=last_question_key,
                        last_question_intent_key=last_question_intent_key,
                        recent_intent_keys=set(recent_intent_keys),
                    )

                if question is None:
                    question = self._build_fallback_probe(
                        asked_question_counts=asked_question_counts,
                        asked_intent_counts=asked_intent_counts,
                        need_timeline=need_timeline,
                        need_harm_remedy=need_harm_remedy,
                        need_actor_decisionmaker=need_actor_decisionmaker,
                        need_documentary_evidence=need_documentary_evidence,
                        need_witness=need_witness,
                        last_question_key=last_question_key,
                        last_question_intent_key=last_question_intent_key,
                        recent_intent_keys=set(recent_intent_keys),
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
                question_key = self._question_dedupe_key(question_text)
                question_intent_key = self._question_intent_key(question_text)
                if question_key in asked_question_keys:
                    logger.debug("Mediator repeated question (no non-repeated alternative available)")
                logger.debug(f"Mediator asks: {question_text}")

                # Get response from complainant
                complainant_prompt = question_text
                if turns == 0:
                    complainant_prompt = self._with_empathy_prefix(question_text)
                answer = self.complainant.respond_to_question(
                    complainant_prompt
                )
                logger.debug(f"Complainant answers: {answer[:100]}...")
                
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
                if self._is_timeline_question(question_text):
                    has_timeline_question = True
                if self._is_harm_or_remedy_question(question_text):
                    has_harm_remedy_question = True
                if self._is_actor_or_decisionmaker_question(question_text):
                    has_actor_or_decisionmaker_question = True
                if self._is_documentary_evidence_question(question_text):
                    has_documentary_evidence_question = True
                if self._is_witness_question(question_text):
                    has_witness_question = True
                
                questions_asked += 1
                turns += 1
                
                # Check if converged
                converged = result.get('converged', False) or result.get('ready_for_evidence_phase', False)
                has_core_coverage = has_timeline_question and has_harm_remedy_question
                has_evidence_coverage = (
                    has_actor_or_decisionmaker_question
                    or has_documentary_evidence_question
                    or has_witness_question
                )
                if converged and has_core_coverage and has_evidence_coverage:
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
