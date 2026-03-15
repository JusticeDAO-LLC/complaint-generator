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
    'PhaseManager',
    'ComplaintPhase',
    'LegalGraphBuilder',
    'LegalGraph',
    'LegalElement',
    'LegalRelation',
    'NeurosymbolicMatcher',
]
