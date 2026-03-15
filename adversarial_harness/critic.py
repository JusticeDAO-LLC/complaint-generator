"""
Critic Module

LLM-based critic that evaluates mediator-complainant interactions.
"""

import logging
from typing import Dict, Any, List
from dataclasses import dataclass, field
import json
import re

logger = logging.getLogger(__name__)


@dataclass
class CriticScore:
    """Score from critic evaluation."""
    overall_score: float  # 0.0 to 1.0
    question_quality: float  # How good were the mediator's questions
    information_extraction: float  # How much info was extracted
    empathy: float  # How empathetic was the mediator
    efficiency: float  # How efficiently was info gathered
    coverage: float  # How well did questions cover important topics
    
    feedback: str = ""  # Detailed textual feedback
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    anchor_sections_expected: List[str] = field(default_factory=list)
    anchor_sections_covered: List[str] = field(default_factory=list)
    anchor_sections_missing: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'overall_score': self.overall_score,
            'question_quality': self.question_quality,
            'information_extraction': self.information_extraction,
            'empathy': self.empathy,
            'efficiency': self.efficiency,
            'coverage': self.coverage,
            'feedback': self.feedback,
            'strengths': self.strengths,
            'weaknesses': self.weaknesses,
            'suggestions': self.suggestions,
            'anchor_sections_expected': self.anchor_sections_expected,
            'anchor_sections_covered': self.anchor_sections_covered,
            'anchor_sections_missing': self.anchor_sections_missing,
        }


class Critic:
    """
    LLM-based critic that evaluates mediator-complainant interactions.
    
    The critic assesses:
    - Quality of questions asked
    - Information extraction effectiveness
    - Empathy and rapport building
    - Efficiency of the process
    - Coverage of important topics
    """
    
    def __init__(self, llm_backend, criteria_weights: Dict[str, float] = None):
        """
        Initialize critic with LLM backend.
        
        Args:
            llm_backend: LLM backend for generating evaluations
            criteria_weights: Optional weights for different criteria
        """
        self.llm_backend = llm_backend
        self.criteria_weights = criteria_weights or {
            'question_quality': 0.25,
            'information_extraction': 0.25,
            'empathy': 0.15,
            'efficiency': 0.15,
            'coverage': 0.20
        }
    
    def evaluate_session(self, 
                        initial_complaint: str,
                        conversation_history: List[Dict[str, Any]],
                        final_state: Dict[str, Any],
                        context: Dict[str, Any] = None) -> CriticScore:
        """
        Evaluate a complete mediator-complainant session.
        
        Args:
            initial_complaint: The original complaint text
            conversation_history: Full conversation between mediator and complainant
            final_state: Final state of complaint processing
            context: Optional ground truth context
            
        Returns:
            CriticScore with detailed evaluation
        """
        anchor_coverage = self._analyze_anchor_section_coverage(conversation_history, context)
        prompt = self._build_evaluation_prompt(
            initial_complaint,
            conversation_history,
            final_state,
            context,
            anchor_coverage,
        )
        
        try:
            response = self.llm_backend(prompt)
            score = self._parse_evaluation(response)
            self._apply_anchor_coverage(score, anchor_coverage)
            return score
        except Exception as e:
            logger.error(f"Error evaluating session: {e}")
            return self._fallback_score(conversation_history, context=context)
    
    def evaluate_question(self, 
                         question: str,
                         context_so_far: List[Dict[str, Any]],
                         response: str = None) -> float:
        """
        Evaluate a single question in isolation.
        
        Args:
            question: The question to evaluate
            context_so_far: Conversation history up to this point
            response: Optional response from complainant
            
        Returns:
            Score from 0.0 to 1.0
        """
        prompt = f"""Evaluate the quality of this mediator question in the context of a legal complaint intake.

Context so far:
{self._format_context(context_so_far[-3:])}

Mediator's question: "{question}"

{f'Complainant response: "{response}"' if response else ''}

Rate the question on a scale of 0.0 to 1.0 based on:
1. Relevance to the complaint
2. Clarity and specificity
3. Likelihood to extract useful information
4. Empathy and rapport building
5. Efficiency (not redundant)

Provide score as a number between 0.0 and 1.0:
Score:"""
        
        try:
            response = self.llm_backend(prompt)
            score = self._extract_score(response)
            return score
        except Exception as e:
            logger.error(f"Error evaluating question: {e}")
            return 0.5  # Neutral fallback
    
    def _build_evaluation_prompt(self,
                                 initial_complaint: str,
                                 conversation_history: List[Dict[str, Any]],
                                 final_state: Dict[str, Any],
                                 context: Dict[str, Any] = None,
                                 anchor_coverage: Dict[str, List[str]] | None = None) -> str:
        """Build comprehensive evaluation prompt."""
        
        # Format conversation
        conversation_text = self._format_conversation(conversation_history)
        
        # Build evaluation criteria
        criteria_text = """
1. Question Quality (0-1): How well-crafted were the mediator's questions?
2. Information Extraction (0-1): How effectively was relevant information gathered?
3. Empathy (0-1): How empathetic and rapport-building was the interaction?
4. Efficiency (0-1): How efficiently was the information gathered (not repetitive)?
5. Coverage (0-1): How comprehensively were important topics covered?
"""
        
        anchor_text = self._format_anchor_coverage(anchor_coverage or {})

        prompt = f"""You are an expert evaluator assessing a legal complaint intake session between a mediator and a complainant.

INITIAL COMPLAINT:
{initial_complaint}

CONVERSATION:
{conversation_text}

FINAL STATE:
{json.dumps(final_state, indent=2)}

{f'GROUND TRUTH CONTEXT:\n{json.dumps(context, indent=2)}\n' if context else ''}
{anchor_text}

Evaluate the mediator's performance on these criteria:
{criteria_text}

Provide your evaluation in the following format:

SCORES:
question_quality: [0.0-1.0]
information_extraction: [0.0-1.0]
empathy: [0.0-1.0]
efficiency: [0.0-1.0]
coverage: [0.0-1.0]

FEEDBACK:
[Detailed feedback paragraph]

STRENGTHS:
- [Strength 1]
- [Strength 2]

WEAKNESSES:
- [Weakness 1]
- [Weakness 2]

SUGGESTIONS:
- [Suggestion 1]
- [Suggestion 2]

Evaluation:"""
        
        return prompt
    
    def _parse_evaluation(self, response: str) -> CriticScore:
        """Parse evaluation response into CriticScore."""
        scores = {}
        feedback = ""
        strengths = []
        weaknesses = []
        suggestions = []
        
        try:
            lines = response.split('\n')
            current_section = None
            
            for line in lines:
                line = line.strip()
                
                # Check for section headers
                if line.startswith('SCORES:'):
                    current_section = 'scores'
                elif line.startswith('FEEDBACK:'):
                    current_section = 'feedback'
                elif line.startswith('STRENGTHS:'):
                    current_section = 'strengths'
                elif line.startswith('WEAKNESSES:'):
                    current_section = 'weaknesses'
                elif line.startswith('SUGGESTIONS:'):
                    current_section = 'suggestions'
                elif current_section == 'scores' and ':' in line:
                    # Parse score line
                    key, value = line.split(':', 1)
                    try:
                        scores[key.strip()] = float(value.strip())
                    except ValueError:
                        # Ignore malformed score values and rely on default weights
                        logger.debug(
                            "Could not parse score value '%s' for key '%s'",
                            value.strip(), key.strip()
                        )
                elif current_section == 'feedback' and line:
                    feedback += line + " "
                elif current_section == 'strengths' and line.startswith('-'):
                    strengths.append(line[1:].strip())
                elif current_section == 'weaknesses' and line.startswith('-'):
                    weaknesses.append(line[1:].strip())
                elif current_section == 'suggestions' and line.startswith('-'):
                    suggestions.append(line[1:].strip())
            
            # Calculate overall score as weighted average
            overall = sum(
                scores.get(k, 0.5) * w
                for k, w in self.criteria_weights.items()
            )
            
            return CriticScore(
                overall_score=overall,
                question_quality=scores.get('question_quality', 0.5),
                information_extraction=scores.get('information_extraction', 0.5),
                empathy=scores.get('empathy', 0.5),
                efficiency=scores.get('efficiency', 0.5),
                coverage=scores.get('coverage', 0.5),
                feedback=feedback.strip(),
                strengths=strengths,
                weaknesses=weaknesses,
                suggestions=suggestions
            )
        
        except Exception as e:
            logger.error(f"Error parsing evaluation: {e}")
            return self._fallback_score([])
    
    def _extract_score(self, response: str) -> float:
        """Extract a single score from response."""
        try:
            # Look for numbers between 0 and 1
            import re
            matches = re.findall(r'0\.\d+|1\.0|0|1', response)
            if matches:
                return float(matches[0])
        except (ValueError, TypeError) as exc:
            # If parsing fails, log and fall back to a neutral score
            logger.debug("Failed to extract score from response: %s", exc)
        return 0.5
    
    def _format_conversation(self, history: List[Dict[str, Any]]) -> str:
        """Format conversation history for prompt."""
        lines = []
        for msg in history:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            msg_type = msg.get('type', '')
            lines.append(f"[{role.upper()} - {msg_type}]: {content}")
        return '\n'.join(lines)
    
    def _format_context(self, context: List[Dict[str, Any]]) -> str:
        """Format context messages."""
        return self._format_conversation(context)
    
    def _fallback_score(self, conversation_history: List[Dict[str, Any]], context: Dict[str, Any] = None) -> CriticScore:
        """Fallback score if evaluation fails."""
        # Simple heuristic: more questions = potentially better
        num_questions = sum(1 for msg in conversation_history if msg.get('type') == 'question')
        score = min(0.5 + (num_questions * 0.05), 0.9)
        
        result = CriticScore(
            overall_score=score,
            question_quality=score,
            information_extraction=score,
            empathy=0.5,
            efficiency=0.5,
            coverage=score,
            feedback="Evaluation fallback - LLM unavailable",
            strengths=["Session completed"],
            weaknesses=["Could not perform detailed evaluation"],
            suggestions=["Review LLM backend configuration"]
        )
        self._apply_anchor_coverage(result, self._analyze_anchor_section_coverage(conversation_history, context))
        return result

    def _analyze_anchor_section_coverage(
        self,
        conversation_history: List[Dict[str, Any]],
        context: Dict[str, Any] = None,
    ) -> Dict[str, List[str]]:
        key_facts = context.get('key_facts') if isinstance(context, dict) and isinstance(context.get('key_facts'), dict) else {}
        expected = [str(value) for value in list(key_facts.get('anchor_sections') or []) if str(value)]
        if not expected:
            return {'expected': [], 'covered': [], 'missing': []}

        transcript = " ".join(str(msg.get('content') or '') for msg in conversation_history).lower()
        label_patterns = {
            'grievance_hearing': ('grievance', 'hearing', 'impartial person', 'informal hearing'),
            'appeal_rights': ('appeal', 'review', 'due process', 'right'),
            'reasonable_accommodation': ('reasonable accommodation', 'disability', 'accommodation'),
            'adverse_action': ('termination', 'denial', 'adverse action', 'admission'),
            'selection_criteria': ('selection', 'screening', 'criteria', 'evaluation', 'priority'),
        }
        covered: List[str] = []
        for label in expected:
            patterns = label_patterns.get(label, (label.replace('_', ' '),))
            if any(re.search(rf"\b{re.escape(pattern)}\b", transcript) for pattern in patterns):
                covered.append(label)
        missing = [label for label in expected if label not in covered]
        return {'expected': expected, 'covered': covered, 'missing': missing}

    def _format_anchor_coverage(self, coverage: Dict[str, List[str]]) -> str:
        expected = list(coverage.get('expected') or [])
        if not expected:
            return ''
        covered = list(coverage.get('covered') or [])
        missing = list(coverage.get('missing') or [])
        return (
            "ANCHOR SECTION COVERAGE:\n"
            f"Expected sections: {', '.join(expected)}\n"
            f"Already covered in conversation: {', '.join(covered) if covered else 'none'}\n"
            f"Still missing from conversation: {', '.join(missing) if missing else 'none'}\n"
        )

    def _apply_anchor_coverage(self, score: CriticScore, coverage: Dict[str, List[str]]) -> None:
        expected = list(coverage.get('expected') or [])
        covered = list(coverage.get('covered') or [])
        missing = list(coverage.get('missing') or [])
        score.anchor_sections_expected = expected
        score.anchor_sections_covered = covered
        score.anchor_sections_missing = missing
        if expected:
            coverage_ratio = len(covered) / len(expected)
            score.coverage = (score.coverage + coverage_ratio) / 2.0
            score.overall_score = (
                (score.question_quality * self.criteria_weights.get('question_quality', 0.0))
                + (score.information_extraction * self.criteria_weights.get('information_extraction', 0.0))
                + (score.empathy * self.criteria_weights.get('empathy', 0.0))
                + (score.efficiency * self.criteria_weights.get('efficiency', 0.0))
                + (score.coverage * self.criteria_weights.get('coverage', 0.0))
            )
        if missing:
            missing_text = ", ".join(missing)
            if f"Missed anchor sections: {missing_text}" not in score.weaknesses:
                score.weaknesses = list(score.weaknesses) + [f"Missed anchor sections: {missing_text}"]
            suggestion = f"Add questions covering: {missing_text}"
            if suggestion not in score.suggestions:
                score.suggestions = list(score.suggestions) + [suggestion]
            feedback_note = f"Anchor-section coverage was incomplete ({len(covered)}/{len(expected)} covered)."
            if feedback_note not in score.feedback:
                score.feedback = f"{score.feedback} {feedback_note}".strip()
        elif expected:
            strength = f"Covered all seeded anchor sections: {', '.join(covered)}"
            if strength not in score.strengths:
                score.strengths = list(score.strengths) + [strength]
