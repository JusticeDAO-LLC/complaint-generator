"""
Phase Manager

Manages the three-phase complaint process and transitions between phases.
"""

import logging
from enum import Enum
from typing import Dict, Any, Callable, List
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

_INTAKE_GAPS_THRESHOLD = 3
_EVIDENCE_GAP_RATIO_THRESHOLD = 0.3
_DENOISING_MAX_ITERATIONS = 20


def _utc_now_isoformat() -> str:
    return datetime.now(UTC).isoformat()


class ComplaintPhase(Enum):
    """The three phases of complaint processing."""
    INTAKE = "intake"  # Phase 1: Initial intake and denoising
    EVIDENCE = "evidence"  # Phase 2: Evidence gathering
    FORMALIZATION = "formalization"  # Phase 3: Neurosymbolic matching and formalization


class PhaseManager:
    """
    Manages complaint processing phases and transitions.
    
    Tracks which phase the complaint is in, completion criteria for each phase,
    and orchestrates transitions between phases.
    """

    _PHASE_ACTION_GETTERS = {
        ComplaintPhase.INTAKE: '_get_intake_action',
        ComplaintPhase.EVIDENCE: '_get_evidence_action',
        ComplaintPhase.FORMALIZATION: '_get_formalization_action',
    }

    _PHASE_COMPLETION_CHECKS = {
        ComplaintPhase.INTAKE: '_is_intake_complete',
        ComplaintPhase.EVIDENCE: '_is_evidence_complete',
        ComplaintPhase.FORMALIZATION: '_is_formalization_complete',
    }
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.current_phase = ComplaintPhase.INTAKE
        self.phase_history = []
        self.phase_data = {
            ComplaintPhase.INTAKE: {},
            ComplaintPhase.EVIDENCE: {},
            ComplaintPhase.FORMALIZATION: {}
        }
        self.iteration_count = 0
        self.loss_history = []  # Track loss/noise over iterations
        self._phase_action_getters: Dict[ComplaintPhase, Callable[[], Dict[str, Any]]] = {
            ComplaintPhase.INTAKE: self._get_intake_action,
            ComplaintPhase.EVIDENCE: self._get_evidence_action,
            ComplaintPhase.FORMALIZATION: self._get_formalization_action,
        }
        self._phase_completion_checks: Dict[ComplaintPhase, Callable[[], bool]] = {
            ComplaintPhase.INTAKE: self._is_intake_complete,
            ComplaintPhase.EVIDENCE: self._is_evidence_complete,
            ComplaintPhase.FORMALIZATION: self._is_formalization_complete,
        }

    def _extract_intake_gap_types(self, data: Dict[str, Any]) -> List[str]:
        """Collect normalized intake gap types from stored phase state."""
        gap_types: List[str] = []

        explicit_gap_types = data.get('intake_gap_types') or []
        for gap_type in explicit_gap_types:
            normalized = str(gap_type or '').strip()
            if normalized and normalized not in gap_types:
                gap_types.append(normalized)

        current_gaps = data.get('current_gaps') or []
        for gap in current_gaps:
            if not isinstance(gap, dict):
                continue
            normalized = str(gap.get('type') or '').strip()
            if normalized and normalized not in gap_types:
                gap_types.append(normalized)

        return gap_types

    def _extract_intake_contradictions(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Normalize stored intake contradiction diagnostics into a candidate list."""
        contradictions = data.get('intake_contradictions')
        if isinstance(contradictions, dict):
            candidates = contradictions.get('candidates')
            if isinstance(candidates, list):
                return [candidate for candidate in candidates if isinstance(candidate, dict)]
            if contradictions:
                return [contradictions]
            return []
        if isinstance(contradictions, list):
            return [candidate for candidate in contradictions if isinstance(candidate, dict)]
        return []

    def _extract_intake_case_file(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Return the structured intake case file when present."""
        intake_case_file = data.get('intake_case_file')
        if isinstance(intake_case_file, dict):
            return intake_case_file
        return {}

    def _collect_intake_section_blockers(self, intake_case_file: Dict[str, Any]) -> Dict[str, Any]:
        """Derive blockers and counters from structured intake sections."""
        sections = intake_case_file.get('intake_sections')
        if not isinstance(sections, dict):
            sections = {}

        normalized_sections: Dict[str, Dict[str, Any]] = {}
        blockers: List[str] = []

        section_to_blocker = {
            'chronology': 'missing_core_chronology',
            'actors': 'missing_core_actor',
            'conduct': 'missing_conduct_details',
            'harm': 'missing_harm',
            'remedy': 'missing_remedy',
            'proof_leads': 'missing_proof_leads',
            'claim_elements': 'missing_claim_element_facts',
        }
        for name, raw_section in sections.items():
            if not isinstance(raw_section, dict):
                continue
            status = str(raw_section.get('status') or 'missing').strip().lower() or 'missing'
            missing_items = raw_section.get('missing_items')
            normalized_sections[name] = {
                'status': status,
                'missing_items': list(missing_items) if isinstance(missing_items, list) else [],
            }
            if status == 'missing':
                blocker = section_to_blocker.get(name)
                if blocker and blocker not in blockers:
                    blockers.append(blocker)

        contradiction_queue = intake_case_file.get('contradiction_queue')
        if not isinstance(contradiction_queue, list):
            contradiction_queue = []
        blocking_contradictions = [
            item for item in contradiction_queue
            if isinstance(item, dict)
            and str(item.get('status') or 'open').strip().lower() != 'resolved'
            and str(item.get('severity') or 'important').strip().lower() == 'blocking'
        ]
        if blocking_contradictions:
            blockers.append('blocking_contradiction')

        candidate_claims = intake_case_file.get('candidate_claims')
        if not isinstance(candidate_claims, list):
            candidate_claims = []
        canonical_facts = intake_case_file.get('canonical_facts')
        if not isinstance(canonical_facts, list):
            canonical_facts = []
        proof_leads = intake_case_file.get('proof_leads')
        if not isinstance(proof_leads, list):
            proof_leads = []

        criteria = {
            'candidate_claim_identified': bool(candidate_claims),
            'core_chronology_present': normalized_sections.get('chronology', {}).get('status') != 'missing',
            'core_actors_identified': normalized_sections.get('actors', {}).get('status') != 'missing',
            'conduct_described': normalized_sections.get('conduct', {}).get('status') != 'missing',
            'harm_captured': normalized_sections.get('harm', {}).get('status') != 'missing',
            'remedy_captured': normalized_sections.get('remedy', {}).get('status') != 'missing',
            'proof_leads_captured': normalized_sections.get('proof_leads', {}).get('status') != 'missing',
            'claim_elements_captured': normalized_sections.get('claim_elements', {}).get('status') != 'missing',
            'blocking_contradictions_resolved': not bool(blocking_contradictions),
        }

        return {
            'sections': normalized_sections,
            'blockers': blockers,
            'criteria': criteria,
            'candidate_claim_count': len(candidate_claims),
            'canonical_fact_count': len(canonical_facts),
            'proof_lead_count': len(proof_leads),
            'blocking_contradictions': blocking_contradictions,
        }

    def _build_intake_readiness(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Derive intake readiness metrics and blockers from intake state."""
        has_knowledge_graph = 'knowledge_graph' in data
        has_dependency_graph = 'dependency_graph' in data
        gaps_addressed = data.get('remaining_gaps', float('inf')) <= 3
        converged = data.get('denoising_converged', False)
        gap_types = self._extract_intake_gap_types(data)
        contradiction_candidates = self._extract_intake_contradictions(data)
        contradiction_count = len(contradiction_candidates)
        has_contradictions = bool(data.get('contradictions_unresolved') or contradiction_count)
        intake_case_file = self._extract_intake_case_file(data)
        structured_readiness = self._collect_intake_section_blockers(intake_case_file) if intake_case_file else None

        criteria: Dict[str, bool] = {
            'knowledge_graph_ready': has_knowledge_graph,
            'dependency_graph_ready': has_dependency_graph,
            'gaps_within_threshold': gaps_addressed,
            'denoising_converged': converged,
        }
        if gap_types:
            criteria['timeline_captured'] = 'missing_timeline' not in gap_types
            criteria['responsible_party_identified'] = 'missing_responsible_party' not in gap_types
            criteria['impact_or_remedy_captured'] = 'missing_impact_remedy' not in gap_types
            criteria['proof_leads_present'] = 'unsupported_claim' not in gap_types
        if has_contradictions or 'contradictions_resolved' in data:
            criteria['contradictions_resolved'] = not has_contradictions
        if structured_readiness:
            criteria.update(structured_readiness['criteria'])

        blockers: List[str] = []
        if not has_knowledge_graph:
            blockers.append('missing_knowledge_graph')
        if not has_dependency_graph:
            blockers.append('missing_dependency_graph')
        if not gaps_addressed:
            blockers.append('unresolved_gaps')
        if not converged:
            blockers.append('denoising_not_converged')
        if 'missing_timeline' in gap_types:
            blockers.append('missing_timeline')
        if 'missing_responsible_party' in gap_types:
            blockers.append('missing_actor')
        if 'missing_impact_remedy' in gap_types:
            blockers.append('missing_impact_or_remedy')
        if 'unsupported_claim' in gap_types:
            blockers.append('missing_proof_leads')
        if has_contradictions:
            blockers.append('contradiction_unresolved')
        if structured_readiness:
            for blocker in structured_readiness['blockers']:
                if blocker not in blockers:
                    blockers.append(blocker)

        for blocker in data.get('intake_blockers', []) or []:
            normalized = str(blocker or '').strip()
            if normalized and normalized not in blockers:
                blockers.append(normalized)

        total_criteria = len(criteria)
        satisfied_criteria = sum(1 for satisfied in criteria.values() if satisfied)
        readiness_score = round(satisfied_criteria / total_criteria, 3) if total_criteria else 0.0

        return {
            'intake_readiness_score': readiness_score,
            'intake_readiness_blockers': blockers,
            'intake_readiness_criteria': criteria,
            'intake_ready': len(blockers) == 0,
            'intake_contradiction_count': contradiction_count,
            'intake_contradictions': contradiction_candidates,
            'intake_sections': structured_readiness['sections'] if structured_readiness else {},
            'candidate_claim_count': structured_readiness['candidate_claim_count'] if structured_readiness else 0,
            'canonical_fact_count': structured_readiness['canonical_fact_count'] if structured_readiness else 0,
            'proof_lead_count': structured_readiness['proof_lead_count'] if structured_readiness else 0,
            'blocking_contradictions': structured_readiness['blocking_contradictions'] if structured_readiness else [],
        }

    def _refresh_phase_derived_state(self, phase: ComplaintPhase):
        """Refresh derived readiness state after phase data changes."""
        if phase == ComplaintPhase.INTAKE:
            self.phase_data[phase].update(self._build_intake_readiness(self.phase_data[phase]))

    def get_intake_readiness(self) -> Dict[str, Any]:
        """Return derived intake readiness state."""
        self._refresh_phase_derived_state(ComplaintPhase.INTAKE)
        data = self.phase_data[ComplaintPhase.INTAKE]
        return {
            'score': data.get('intake_readiness_score', 0.0),
            'blockers': list(data.get('intake_readiness_blockers', [])),
            'criteria': dict(data.get('intake_readiness_criteria', {})),
            'ready': bool(data.get('intake_ready', False)),
            'contradiction_count': int(data.get('intake_contradiction_count', 0) or 0),
            'contradictions': list(data.get('intake_contradictions', [])),
            'intake_sections': dict(data.get('intake_sections', {})),
            'candidate_claim_count': int(data.get('candidate_claim_count', 0) or 0),
            'canonical_fact_count': int(data.get('canonical_fact_count', 0) or 0),
            'proof_lead_count': int(data.get('proof_lead_count', 0) or 0),
            'blocking_contradictions': list(data.get('blocking_contradictions', [])),
        }
    
    def get_current_phase(self) -> ComplaintPhase:
        """Get the current phase."""
        return self.current_phase
    
    def advance_to_phase(self, phase: ComplaintPhase) -> bool:
        """
        Advance to a new phase.
        
        Args:
            phase: The phase to advance to
            
        Returns:
            True if transition was successful, False otherwise
        """
        if self._can_advance_to(phase):
            self.phase_history.append({
                'from_phase': self.current_phase.value,
                'to_phase': phase.value,
                'timestamp': _utc_now_isoformat(),
                'iteration': self.iteration_count
            })
            self.current_phase = phase
            logger.info("Advanced to phase: %s", phase.value)
            return True
        else:
            logger.warning("Cannot advance to phase %s - requirements not met", phase.value)
            return False
    
    def _can_advance_to(self, phase: ComplaintPhase) -> bool:
        """Check if we can advance to a given phase."""
        if phase == ComplaintPhase.INTAKE:
            return True  # Can always go back to intake
        
        if phase == ComplaintPhase.EVIDENCE:
            # Can advance to evidence if intake is complete
            return self.is_phase_complete(ComplaintPhase.INTAKE)
        
        if phase == ComplaintPhase.FORMALIZATION:
            # Can advance to formalization if evidence gathering is sufficient
            return self.is_phase_complete(ComplaintPhase.EVIDENCE)
        
        return False
    
    def is_phase_complete(self, phase: ComplaintPhase) -> bool:
        """
        Check if a phase is complete.
        
        Args:
            phase: The phase to check
            
        Returns:
            True if phase is complete, False otherwise
        """
        completion_check = self._phase_completion_checks.get(phase)
        if completion_check is not None:
            return completion_check()
        method_name = self._PHASE_COMPLETION_CHECKS.get(phase)
        if method_name is None:
            return False
        return getattr(self, method_name)()
    
    def _is_intake_complete(self) -> bool:
        """
        Check if intake phase is complete.
        
        Intake is complete when:
        - Knowledge graph has been built
        - Dependency graph has been built
        - Gaps have been identified and addressed (or exhausted)
        - Denoising iterations have converged
        """
        readiness = self.get_intake_readiness()
        return readiness['ready']
    
    def _is_evidence_complete(self) -> bool:
        """
        Check if evidence gathering phase is complete.
        
        Evidence phase is complete when:
        - Evidence has been gathered for key claims
        - Knowledge graph has been enhanced with evidence
        - Critical evidence gaps are below threshold
        """
        data = self.phase_data[ComplaintPhase.EVIDENCE]
        
        evidence_gathered = data.get('evidence_count', 0) > 0
        kg_enhanced = data.get('knowledge_graph_enhanced', False)
        gap_ratio = data.get('evidence_gap_ratio', 1.0)
        
        return evidence_gathered and kg_enhanced and gap_ratio < _EVIDENCE_GAP_RATIO_THRESHOLD
    
    def _is_formalization_complete(self) -> bool:
        """
        Check if formalization phase is complete.
        
        Formalization is complete when:
        - Legal graph has been created
        - Neurosymbolic matching is done
        - Formal complaint has been generated
        """
        data = self.phase_data[ComplaintPhase.FORMALIZATION]
        
        has_legal_graph = 'legal_graph' in data
        matching_done = data.get('matching_complete', False)
        complaint_generated = data.get('formal_complaint', None) is not None
        
        return has_legal_graph and matching_done and complaint_generated
    
    def update_phase_data(self, phase: ComplaintPhase, key: str, value: Any):
        """Update data for a specific phase."""
        self.phase_data[phase][key] = value
        self._refresh_phase_derived_state(phase)
        logger.debug("Updated %s data: %s = %s", phase.value, key, value)
    
    def get_phase_data(self, phase: ComplaintPhase, key: str = None) -> Any:
        """Get data for a specific phase."""
        data = self.phase_data[phase]
        if key:
            return data.get(key)
        return data
    
    def record_iteration(self, loss: float, metrics: Dict[str, Any]):
        """
        Record an iteration with loss/noise metric.
        
        Args:
            loss: Current loss/noise value (lower is better)
            metrics: Additional metrics for this iteration
        """
        self.iteration_count += 1
        phase_value = self.current_phase.value
        self.loss_history.append({
            'iteration': self.iteration_count,
            'loss': loss,
            'phase': phase_value,
            'metrics': metrics,
            'timestamp': _utc_now_isoformat()
        })
        logger.info(
            "Iteration %s: loss=%.4f, phase=%s",
            self.iteration_count,
            loss,
            phase_value,
        )
    
    def has_converged(self, window: int = 5, threshold: float = 0.01) -> bool:
        """
        Check if iterations have converged.
        
        Args:
            window: Number of recent iterations to check
            threshold: Maximum change in loss to consider converged
            
        Returns:
            True if converged, False otherwise
        """
        if len(self.loss_history) < window:
            return False
        
        recent = self.loss_history[-window:]
        losses = [entry.get('loss', 0.0) for entry in recent]
        return (max(losses) - min(losses)) < threshold
    
    def get_next_action(self) -> Dict[str, Any]:
        """
        Get the next recommended action based on current phase and state.
        
        Returns:
            Dictionary with action type and parameters
        """
        action_getter = self._phase_action_getters.get(self.current_phase)
        if action_getter is not None:
            return action_getter()
        method_name = self._PHASE_ACTION_GETTERS.get(self.current_phase)
        if method_name is None:
            return {'action': 'unknown'}
        return getattr(self, method_name)()
    
    def _get_intake_action(self) -> Dict[str, Any]:
        """Get next action for intake phase."""
        data = self.phase_data[ComplaintPhase.INTAKE]
        readiness = self.get_intake_readiness()
        
        if 'knowledge_graph' not in data:
            return {
                'action': 'build_knowledge_graph',
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }
        
        if 'dependency_graph' not in data:
            return {
                'action': 'build_dependency_graph',
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }
        
        gaps = data.get('current_gaps', [])
        if gaps and len(gaps) > 0:
            return {
                'action': 'address_gaps',
                'gaps': gaps,
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }

        remaining_gaps = data.get('remaining_gaps', float('inf'))
        if remaining_gaps > _INTAKE_GAPS_THRESHOLD:
            return {
                'action': 'address_gaps',
                'gaps': gaps,
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }

        semantic_blockers = [
            blocker for blocker in readiness['blockers']
            if blocker not in {
                'missing_knowledge_graph',
                'missing_dependency_graph',
                'unresolved_gaps',
                'denoising_not_converged',
            }
        ]
        if semantic_blockers:
            return {
                'action': 'address_gaps',
                'gaps': gaps,
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }
        
        if not data.get('denoising_converged', False) and self.iteration_count < _DENOISING_MAX_ITERATIONS:
            return {
                'action': 'continue_denoising',
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }
        
        return {
            'action': 'complete_intake',
            'intake_readiness_score': readiness['score'],
            'intake_blockers': readiness['blockers'],
        }
    
    def _get_evidence_action(self) -> Dict[str, Any]:
        """Get next action for evidence phase."""
        data = self.phase_data[ComplaintPhase.EVIDENCE]
        
        if data.get('evidence_count', 0) == 0:
            return {'action': 'gather_evidence'}
        
        if not data.get('knowledge_graph_enhanced', False):
            return {'action': 'enhance_knowledge_graph'}
        
        gap_ratio = data.get('evidence_gap_ratio', 1.0)
        if gap_ratio > _EVIDENCE_GAP_RATIO_THRESHOLD:
            return {'action': 'fill_evidence_gaps', 'gap_ratio': gap_ratio}
        
        return {'action': 'complete_evidence'}
    
    def _get_formalization_action(self) -> Dict[str, Any]:
        """Get next action for formalization phase."""
        data = self.phase_data[ComplaintPhase.FORMALIZATION]
        
        if not data.get('legal_graph'):
            return {'action': 'build_legal_graph'}
        
        if not data.get('matching_complete', False):
            return {'action': 'perform_neurosymbolic_matching'}
        
        if not data.get('formal_complaint'):
            return {'action': 'generate_formal_complaint'}
        
        return {'action': 'complete_formalization'}
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'current_phase': self.current_phase.value,
            'phase_history': self.phase_history,
            'phase_data': {
                phase.value: data for phase, data in self.phase_data.items()
            },
            'iteration_count': self.iteration_count,
            'loss_history': self.loss_history
        }
    
    @classmethod
    def from_dict(cls, data: dict, mediator=None) -> 'PhaseManager':
        """Deserialize from dictionary."""
        manager = cls(mediator)
        manager.current_phase = ComplaintPhase(data['current_phase'])
        manager.phase_history = data['phase_history']
        manager.phase_data = {
            ComplaintPhase(phase_str): phase_data 
            for phase_str, phase_data in data['phase_data'].items()
        }
        manager.iteration_count = data['iteration_count']
        manager.loss_history = data['loss_history']
        return manager

    # ============================================================================
    # Batch 211: PhaseManager Analysis Methods
    # ============================================================================
    
    def total_phase_transitions(self) -> int:
        """Return the total number of phase transitions recorded.
        
        Returns:
            Count of phase transitions in history.
        """
        return len(self.phase_history)
    
    def transitions_to_phase(self, phase: ComplaintPhase) -> int:
        """Count transitions to a specific phase.
        
        Args:
            phase: The phase to count transitions to.
            
        Returns:
            Number of times transitioned to this phase.
        """
        phase_value = phase.value
        return sum(1 for t in self.phase_history if t.get('to_phase') == phase_value)
    
    def phase_transition_frequency(self) -> Dict[str, int]:
        """Calculate frequency distribution of phase transitions.
        
        Returns:
            Dict mapping phase names to transition counts.
        """
        freq = {}
        for transition in self.phase_history:
            to_phase = transition.get('to_phase')
            freq[to_phase] = freq.get(to_phase, 0) + 1
        return freq
    
    def most_visited_phase(self) -> str:
        """Find the phase that has been transitioned to most often.
        
        Returns:
            Phase name with most transitions, or 'none' if no transitions.
        """
        if not self.phase_history:
            return 'none'
        freq = self.phase_transition_frequency()
        return max(freq, key=freq.get)
    
    def total_iterations(self) -> int:
        """Return the total number of iterations recorded.
        
        Returns:
            Current iteration count.
        """
        return self.iteration_count
    
    def iterations_in_phase(self, phase: ComplaintPhase) -> int:
        """Count iterations that occurred in a specific phase.
        
        Args:
            phase: The phase to count iterations for.
            
        Returns:
            Number of iterations in this phase.
        """
        phase_value = phase.value
        return sum(1 for h in self.loss_history if h.get('phase') == phase_value)
    
    def average_loss(self) -> float:
        """Calculate the average loss across all recorded iterations.
        
        Returns:
            Mean loss value, or 0.0 if no iterations.
        """
        if not self.loss_history:
            return 0.0
        total_loss = sum(entry.get('loss', 0.0) for entry in self.loss_history)
        return total_loss / len(self.loss_history)
    
    def minimum_loss(self) -> float:
        """Find the minimum loss value across all iterations.
        
        Returns:
            Minimum loss achieved, or float('inf') if no iterations.
        """
        if not self.loss_history:
            return float('inf')
        return min(entry.get('loss', float('inf')) for entry in self.loss_history)
    
    def has_phase_data_key(self, phase: ComplaintPhase, key: str) -> bool:
        """Check if a specific data key exists for a phase.
        
        Args:
            phase: The phase to check.
            key: The data key to look for.
            
        Returns:
            True if the key exists in phase data, False otherwise.
        """
        return key in self.phase_data.get(phase, {})
    
    def phase_data_coverage(self) -> float:
        """Calculate what fraction of phases have any data recorded.
        
        Returns:
            Ratio of phases with data (0.0 to 1.0).
        """
        total_phases = len(self.phase_data)
        if total_phases == 0:
            return 0.0
        phases_with_data = sum(1 for data in self.phase_data.values() if data)
        return phases_with_data / total_phases
