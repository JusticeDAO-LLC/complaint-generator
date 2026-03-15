"""
Complaint Phases Module

This module implements a three-phase complaint processing system:
1. Initial Intake & Denoising - Generate knowledge/dependency graphs, ask questions
2. Evidence Gathering - Enhance graphs with evidence, fill gaps
3. Neurosymbolic Representation - Match against law graphs, generate formal complaint
"""

from .knowledge_graph import (
    KnowledgeGraphBuilder, 
    KnowledgeGraph, 
    Entity, 
    Relationship
)
from .dependency_graph import (
    DependencyGraphBuilder, 
    DependencyGraph,
    DependencyNode,
    Dependency,
    NodeType,
    DependencyType
)
from .denoiser import ComplaintDenoiser
from .intake_case_file import build_intake_case_file, refresh_intake_sections
from .intake_claim_registry import (
    CLAIM_INTAKE_REQUIREMENTS,
    build_claim_element_question_intent,
    build_claim_element_question_text,
    build_proof_lead_question_intent,
    build_proof_lead_question_text,
    match_required_element_id,
    normalize_claim_type,
    render_question_text_from_intent,
)
from .phase_manager import PhaseManager, ComplaintPhase
from .legal_graph import (
    LegalGraphBuilder, 
    LegalGraph,
    LegalElement,
    LegalRelation
)
from .neurosymbolic_matcher import NeurosymbolicMatcher

__all__ = [
    'KnowledgeGraphBuilder',
    'KnowledgeGraph',
    'Entity',
    'Relationship',
    'DependencyGraphBuilder',
    'DependencyGraph',
    'DependencyNode',
    'Dependency',
    'NodeType',
    'DependencyType',
    'ComplaintDenoiser',
    'build_intake_case_file',
    'refresh_intake_sections',
    'CLAIM_INTAKE_REQUIREMENTS',
    'build_claim_element_question_intent',
    'build_claim_element_question_text',
    'build_proof_lead_question_intent',
    'build_proof_lead_question_text',
    'match_required_element_id',
    'normalize_claim_type',
    'render_question_text_from_intent',
    'PhaseManager',
    'ComplaintPhase',
    'LegalGraphBuilder',
    'LegalGraph',
    'LegalElement',
    'LegalRelation',
    'NeurosymbolicMatcher',
]
