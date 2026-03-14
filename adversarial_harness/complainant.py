"""
Complainant Module

LLM-based complainant that generates complaints and responds to mediator questions.
"""

import logging
from typing import Dict, Any, List
from dataclasses import dataclass, field
import json

logger = logging.getLogger(__name__)


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
        key_facts = dict(seed.get("key_facts", {}))
        evidence_items = list(seed.get("hacc_evidence") or key_facts.get("hacc_evidence") or [])
        evidence_summary = str(
            key_facts.get("evidence_summary")
            or seed.get("summary")
            or ""
        )
        return ComplaintContext(
            complaint_type=seed.get("type", "unknown"),
            key_facts=key_facts,
            emotional_state=str(profile.get("emotional_state", "distressed")),
            cooperation_level=float(profile.get("cooperation_level", 0.8)),
            context_depth=int(profile.get("context_depth", 1)),
            evidence_items=evidence_items,
            evidence_summary=evidence_summary,
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
                'content': response
            })
            return response
        except Exception as e:
            logger.error(f"Error responding to question: {e}")
            return self._fallback_response(question)
    
    def _build_complaint_prompt(self, seed_data: Dict[str, Any]) -> str:
        """Build prompt for generating initial complaint."""
        instructions = "\n".join([f"- {x}" for x in (self.personality_profile.get("instructions") or [])])
        evidence_text = self._format_seed_evidence(seed_data)
        prompt = f"""You are a person filing a complaint. Based on the following situation, write a detailed but natural complaint as if you were experiencing this issue.

Situation:
{json.dumps(seed_data, indent=2)}

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
5. When evidence is provided, use it as grounding without sounding like a brief

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
        
        prompt = f"""You are a complainant in a legal matter. You are {cooperation_desc} and your personality is {self.personality}.

Your situation involves:
{json.dumps(self.context.key_facts, indent=2)}

Evidence you can draw from:
{evidence_text}

Recent conversation:
{history_text}

The mediator asks: "{question}"

Respond naturally as this person would. Your response should:
1. Answer the question based on your knowledge
2. Match your personality ({self.personality}) and cooperation level ({cooperation_desc})
3. Be honest but not overly detailed unless asked
4. Sound like a real person, not a legal document
5. Use the evidence when it supports the answer, and say when something is only an inference

Behavioral constraints:
{instructions}

If you don't know something, say so. If your cooperation level is low, it's okay to be brief or refuse minor details.

Response:"""
        return prompt
    
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
        return self._format_evidence_block(summary, evidence_items)

    def _format_context_evidence(self) -> str:
        return self._format_evidence_block(
            self.context.evidence_summary,
            self.context.evidence_items,
        )

    def _format_evidence_block(self, summary: str, evidence_items: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        if summary:
            lines.append(f"Summary: {summary}")
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
