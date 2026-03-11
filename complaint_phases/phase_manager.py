"""
Phase Manager

Manages the three-phase complaint process and transitions between phases.
"""

import logging
from enum import Enum
from typing import Dict, Any
from datetime import datetime, UTC

logger = logging.getLogger(__name__)


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
            logger.info(f"Advanced to phase: {phase.value}")
            return True
        else:
            logger.warning(f"Cannot advance to phase {phase.value} - requirements not met")
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
        if phase == ComplaintPhase.INTAKE:
            return self._is_intake_complete()
        elif phase == ComplaintPhase.EVIDENCE:
            return self._is_evidence_complete()
        elif phase == ComplaintPhase.FORMALIZATION:
            return self._is_formalization_complete()
        return False
    
    def _is_intake_complete(self) -> bool:
        """
        Check if intake phase is complete.
        
        Intake is complete when:
        - Knowledge graph has been built
        - Dependency graph has been built
        - Gaps have been identified and addressed (or exhausted)
        - Denoising iterations have converged
        """
        data = self.phase_data[ComplaintPhase.INTAKE]
        
        has_knowledge_graph = 'knowledge_graph' in data
        has_dependency_graph = 'dependency_graph' in data
        gaps_addressed = data.get('remaining_gaps', float('inf')) <= 3
        converged = data.get('denoising_converged', False)
        
        # Require both gaps to be addressed AND convergence
        return has_knowledge_graph and has_dependency_graph and gaps_addressed and converged
    
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
        
        return evidence_gathered and kg_enhanced and gap_ratio < 0.3
    
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
        logger.debug(f"Updated {phase.value} data: {key} = {value}")
    
    def get_phase_data(self, phase: ComplaintPhase, key: str = None) -> Any:
        """Get data for a specific phase."""
        if key:
            return self.phase_data[phase].get(key)
        return self.phase_data[phase]
    
    def record_iteration(self, loss: float, metrics: Dict[str, Any]):
        """
        Record an iteration with loss/noise metric.
        
        Args:
            loss: Current loss/noise value (lower is better)
            metrics: Additional metrics for this iteration
        """
        self.iteration_count += 1
        self.loss_history.append({
            'iteration': self.iteration_count,
            'loss': loss,
            'phase': self.current_phase.value,
            'metrics': metrics,
            'timestamp': _utc_now_isoformat()
        })
        logger.info(f"Iteration {self.iteration_count}: loss={loss:.4f}, phase={self.current_phase.value}")
    
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
        
        recent_losses = [h['loss'] for h in self.loss_history[-window:]]
        max_loss = max(recent_losses)
        min_loss = min(recent_losses)
        change = max_loss - min_loss
        
        return change < threshold
    
    def get_next_action(self) -> Dict[str, Any]:
        """
        Get the next recommended action based on current phase and state.
        
        Returns:
            Dictionary with action type and parameters
        """
        if self.current_phase == ComplaintPhase.INTAKE:
            return self._get_intake_action()
        elif self.current_phase == ComplaintPhase.EVIDENCE:
            return self._get_evidence_action()
        elif self.current_phase == ComplaintPhase.FORMALIZATION:
            return self._get_formalization_action()
        
        return {'action': 'unknown'}
    
    def _get_intake_action(self) -> Dict[str, Any]:
        """Get next action for intake phase."""
        data = self.phase_data[ComplaintPhase.INTAKE]
        
        if not data.get('knowledge_graph'):
            return {'action': 'build_knowledge_graph'}
        
        if not data.get('dependency_graph'):
            return {'action': 'build_dependency_graph'}
        
        gaps = data.get('current_gaps', [])
        if gaps and len(gaps) > 0:
            return {'action': 'address_gaps', 'gaps': gaps}
        
        if not data.get('denoising_converged', False) and self.iteration_count < 20:
            return {'action': 'continue_denoising'}
        
        return {'action': 'complete_intake'}
    
    def _get_evidence_action(self) -> Dict[str, Any]:
        """Get next action for evidence phase."""
        data = self.phase_data[ComplaintPhase.EVIDENCE]
        
        if data.get('evidence_count', 0) == 0:
            return {'action': 'gather_evidence'}
        
        if not data.get('knowledge_graph_enhanced', False):
            return {'action': 'enhance_knowledge_graph'}
        
        gap_ratio = data.get('evidence_gap_ratio', 1.0)
        if gap_ratio > 0.3:
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
        return sum(1 for t in self.phase_history if t.get('to_phase') == phase.value)
    
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
        return sum(1 for h in self.loss_history if h.get('phase') == phase.value)
    
    def average_loss(self) -> float:
        """Calculate the average loss across all recorded iterations.
        
        Returns:
            Mean loss value, or 0.0 if no iterations.
        """
        if not self.loss_history:
            return 0.0
        total_loss = sum(h.get('loss', 0.0) for h in self.loss_history)
        return total_loss / len(self.loss_history)
    
    def minimum_loss(self) -> float:
        """Find the minimum loss value across all iterations.
        
        Returns:
            Minimum loss achieved, or float('inf') if no iterations.
        """
        if not self.loss_history:
            return float('inf')
        return min(h.get('loss', float('inf')) for h in self.loss_history)
    
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
