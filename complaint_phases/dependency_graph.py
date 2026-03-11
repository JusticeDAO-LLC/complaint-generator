"""
Dependency Graph Builder

Tracks dependencies between claims, evidence, and legal requirements.
Used to ensure all elements of a claim are properly supported.
"""

import json
import logging
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from enum import Enum

logger = logging.getLogger(__name__)


def _utc_now_isoformat() -> str:
    return datetime.now(UTC).isoformat()


class NodeType(Enum):
    """Types of nodes in the dependency graph."""
    CLAIM = "claim"
    EVIDENCE = "evidence"
    REQUIREMENT = "requirement"
    FACT = "fact"
    LEGAL_ELEMENT = "legal_element"


class DependencyType(Enum):
    """Types of dependencies between nodes."""
    REQUIRES = "requires"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    IMPLIES = "implies"
    DEPENDS_ON = "depends_on"


@dataclass
class DependencyNode:
    """Represents a node in the dependency graph."""
    id: str
    node_type: NodeType
    name: str
    description: str = ""
    satisfied: bool = False
    confidence: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['node_type'] = self.node_type.value
        return data


@dataclass
class Dependency:
    """Represents a dependency edge in the graph."""
    id: str
    source_id: str
    target_id: str
    dependency_type: DependencyType
    required: bool = True
    strength: float = 1.0  # 0.0 to 1.0
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['dependency_type'] = self.dependency_type.value
        return data


class DependencyGraph:
    """
    Dependency graph for tracking claim requirements and evidence.
    
    This graph tracks what each claim requires (legal elements, facts, evidence)
    and whether those requirements are satisfied.
    """
    
    def __init__(self):
        self.nodes: Dict[str, DependencyNode] = {}
        self.dependencies: Dict[str, Dependency] = {}
        self.metadata = {
            'created_at': _utc_now_isoformat(),
            'last_updated': _utc_now_isoformat(),
            'version': '1.0'
        }
    
    def add_node(self, node: DependencyNode) -> str:
        """Add a node to the graph."""
        self.nodes[node.id] = node
        self._update_metadata()
        return node.id
    
    def add_dependency(self, dependency: Dependency) -> str:
        """Add a dependency to the graph."""
        if dependency.source_id not in self.nodes:
            raise ValueError(f"Source node {dependency.source_id} not found")
        if dependency.target_id not in self.nodes:
            raise ValueError(f"Target node {dependency.target_id} not found")
        
        self.dependencies[dependency.id] = dependency
        self._update_metadata()
        return dependency.id
    
    def get_node(self, node_id: str) -> Optional[DependencyNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)
    
    def get_dependencies_for_node(self, node_id: str, 
                                   direction: str = 'both') -> List[Dependency]:
        """
        Get dependencies for a node.
        
        Args:
            node_id: Node ID
            direction: 'incoming', 'outgoing', or 'both'
        """
        deps = []
        for dep in self.dependencies.values():
            if direction in ['incoming', 'both'] and dep.target_id == node_id:
                deps.append(dep)
            if direction in ['outgoing', 'both'] and dep.source_id == node_id:
                deps.append(dep)
        return deps
    
    def get_nodes_by_type(self, node_type: NodeType) -> List[DependencyNode]:
        """Get all nodes of a specific type."""
        return [n for n in self.nodes.values() if n.node_type == node_type]
    
    def check_satisfaction(self, node_id: str) -> Dict[str, Any]:
        """
        Check if a node's requirements are satisfied.
        
        Returns information about satisfaction status and missing dependencies.
        """
        node = self.get_node(node_id)
        if not node:
            return {'error': 'Node not found'}
        
        # Get all requirements (incoming dependencies)
        requirements = self.get_dependencies_for_node(node_id, direction='incoming')
        required_deps = [d for d in requirements if d.required]
        
        satisfied_count = 0
        missing = []
        
        for dep in required_deps:
            source_node = self.get_node(dep.source_id)
            if source_node and source_node.satisfied:
                satisfied_count += 1
            else:
                missing.append({
                    'dependency_id': dep.id,
                    'source_node_id': dep.source_id,
                    'source_name': source_node.name if source_node else 'Unknown',
                    'dependency_type': dep.dependency_type.value
                })
        
        total_required = len(required_deps)
        satisfaction_ratio = satisfied_count / total_required if total_required > 0 else 1.0
        
        return {
            'node_id': node_id,
            'node_name': node.name,
            'satisfied': satisfaction_ratio >= 1.0,
            'satisfaction_ratio': satisfaction_ratio,
            'satisfied_count': satisfied_count,
            'total_required': total_required,
            'missing_dependencies': missing
        }
    
    def find_unsatisfied_requirements(self) -> List[Dict[str, Any]]:
        """Find all nodes with unsatisfied requirements."""
        unsatisfied = []
        
        for node in self.nodes.values():
            check = self.check_satisfaction(node.id)
            if not check.get('satisfied', False) and check.get('total_required', 0) > 0:
                unsatisfied.append(check)
        
        return unsatisfied
    
    def get_claim_readiness(self) -> Dict[str, Any]:
        """
        Assess overall readiness of all claims.
        
        Returns summary of which claims are ready to file and which need work.
        """
        claims = self.get_nodes_by_type(NodeType.CLAIM)
        
        ready_claims = []
        incomplete_claims = []
        
        for claim in claims:
            check = self.check_satisfaction(claim.id)
            if check.get('satisfied', False):
                ready_claims.append({
                    'claim_id': claim.id,
                    'claim_name': claim.name,
                    'confidence': claim.confidence
                })
            else:
                incomplete_claims.append({
                    'claim_id': claim.id,
                    'claim_name': claim.name,
                    'satisfaction_ratio': check.get('satisfaction_ratio', 0.0),
                    'missing_count': len(check.get('missing_dependencies', []))
                })
        
        return {
            'total_claims': len(claims),
            'ready_claims': len(ready_claims),
            'incomplete_claims': len(incomplete_claims),
            'ready_claim_details': ready_claims,
            'incomplete_claim_details': incomplete_claims,
            'overall_readiness': len(ready_claims) / len(claims) if claims else 0.0
        }
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'metadata': self.metadata,
            'nodes': {nid: n.to_dict() for nid, n in self.nodes.items()},
            'dependencies': {did: d.to_dict() for did, d in self.dependencies.items()}
        }
    
    def to_json(self, filepath: str):
        """Save to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Dependency graph saved to {filepath}")
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DependencyGraph':
        """Deserialize from dictionary."""
        graph = cls()
        graph.metadata = data['metadata']
        
        for nid, ndata in data['nodes'].items():
            ndata['node_type'] = NodeType(ndata['node_type'])
            node = DependencyNode(**ndata)
            graph.nodes[nid] = node
        
        for did, ddata in data['dependencies'].items():
            ddata['dependency_type'] = DependencyType(ddata['dependency_type'])
            dep = Dependency(**ddata)
            graph.dependencies[did] = dep
        
        return graph
    
    @classmethod
    def from_json(cls, filepath: str) -> 'DependencyGraph':
        """Load from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        logger.info(f"Dependency graph loaded from {filepath}")
        return cls.from_dict(data)
    
    def _update_metadata(self):
        """Update last_updated timestamp."""
        self.metadata['last_updated'] = _utc_now_isoformat()
    
    def summary(self) -> Dict[str, Any]:
        """Get a summary of the dependency graph."""
        node_counts = {}
        for node in self.nodes.values():
            node_type_str = node.node_type.value
            node_counts[node_type_str] = node_counts.get(node_type_str, 0) + 1
        
        dep_counts = {}
        for dep in self.dependencies.values():
            dep_type_str = dep.dependency_type.value
            dep_counts[dep_type_str] = dep_counts.get(dep_type_str, 0) + 1
        
        satisfied_nodes = sum(1 for n in self.nodes.values() if n.satisfied)
        
        return {
            'total_nodes': len(self.nodes),
            'total_dependencies': len(self.dependencies),
            'node_types': node_counts,
            'dependency_types': dep_counts,
            'satisfied_nodes': satisfied_nodes,
            'satisfaction_rate': satisfied_nodes / len(self.nodes) if self.nodes else 0.0
        }


    # ------------------------------------------------------------------ #
    # Batch 209: Dependency graph analysis and statistics methods        #
    # ------------------------------------------------------------------ #

    def total_nodes(self) -> int:
        """Return total number of nodes in the graph.

        Returns:
            Count of nodes.
        """
        return len(self.nodes)

    def total_dependencies(self) -> int:
        """Return total number of dependencies in the graph.

        Returns:
            Count of dependencies.
        """
        return len(self.dependencies)

    def node_type_distribution(self) -> dict:
        """Calculate frequency distribution of node types.

        Returns:
            Dict mapping node type names to counts.
        """
        type_counts: dict = {}
        for node in self.nodes.values():
            ntype = node.node_type.value  # Get enum value (string)
            type_counts[ntype] = type_counts.get(ntype, 0) + 1
        return type_counts

    def dependency_type_distribution(self) -> dict:
        """Calculate frequency distribution of dependency types.

        Returns:
            Dict mapping dependency type names to counts.
        """
        type_counts: dict = {}
        for dep in self.dependencies.values():
            dtype = dep.dependency_type.value  # Get enum value (string)
            type_counts[dtype] = type_counts.get(dtype, 0) + 1
        return type_counts

    def satisfied_node_count(self) -> int:
        """Count nodes marked as satisfied.

        Returns:
            Number of satisfied nodes.
        """
        return sum(1 for node in self.nodes.values() if node.satisfied)

    def unsatisfied_node_count(self) -> int:
        """Count nodes not marked as satisfied.

        Returns:
            Number of unsatisfied nodes.
        """
        return sum(1 for node in self.nodes.values() if not node.satisfied)

    def average_confidence(self) -> float:
        """Calculate average confidence across all nodes.

        Returns:
            Mean confidence score, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        return sum(n.confidence for n in self.nodes.values()) / len(self.nodes)

    def required_dependency_count(self) -> int:
        """Count dependencies marked as required.

        Returns:
            Number of required dependencies.
        """
        return sum(1 for dep in self.dependencies.values() if dep.required)

    def average_dependencies_per_node(self) -> float:
        """Calculate average number of dependencies per node.

        Returns:
            Mean dependency count, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        total_connections = sum(
            len(self.get_dependencies_for_node(nid))
            for nid in self.nodes.keys()
        )
        # Each dependency is counted twice (source and target), so divide by 2
        return (total_connections / 2) / len(self.nodes)

    def most_dependent_node(self) -> str:
        """Find node ID with the most dependencies.

        Returns:
            Node ID with most dependencies, or 'none' if no nodes.
        """
        if not self.nodes:
            return 'none'
        
        dependency_counts: dict = {}
        for node_id in self.nodes.keys():
            dependency_counts[node_id] = len(self.get_dependencies_for_node(node_id))
        
        if not dependency_counts:
            return 'none'
        
        return max(dependency_counts.items(), key=lambda x: x[1])[0]


    # ------------------------------------------------------------------ #
    # Batch 223: Dependency graph analysis and statistics methods        #
    # ------------------------------------------------------------------ #

    def node_type_set(self) -> List[str]:
        """Return sorted list of unique node types.

        Returns:
            Sorted list of node type strings.
        """
        return sorted({node.node_type.value for node in self.nodes.values()})

    def dependency_type_set(self) -> List[str]:
        """Return sorted list of unique dependency types.

        Returns:
            Sorted list of dependency type strings.
        """
        return sorted({dep.dependency_type.value for dep in self.dependencies.values()})

    def nodes_with_attributes_count(self) -> int:
        """Count nodes with non-empty attributes.

        Returns:
            Number of nodes with attributes.
        """
        return sum(1 for node in self.nodes.values() if node.attributes)

    def nodes_with_description_count(self) -> int:
        """Count nodes with non-empty description.

        Returns:
            Number of nodes with descriptions.
        """
        return sum(1 for node in self.nodes.values() if node.description)

    def nodes_missing_description_count(self) -> int:
        """Count nodes missing a description.

        Returns:
            Number of nodes with empty description fields.
        """
        return sum(1 for node in self.nodes.values() if not node.description)

    def nodes_by_satisfaction(self, satisfied: bool = True) -> List[DependencyNode]:
        """Get nodes filtered by satisfaction flag.

        Args:
            satisfied: Whether to return satisfied or unsatisfied nodes

        Returns:
            List of dependency nodes matching the flag.
        """
        return [node for node in self.nodes.values() if node.satisfied == satisfied]

    def dependency_count_for_node(self, node_id: str) -> int:
        """Count dependencies involving a specific node.

        Args:
            node_id: Node identifier

        Returns:
            Number of dependencies involving the node.
        """
        return len(self.get_dependencies_for_node(node_id))

    def dependencies_required_ratio(self) -> float:
        """Calculate ratio of required dependencies.

        Returns:
            Ratio of required dependencies (0.0 to 1.0).
        """
        if not self.dependencies:
            return 0.0
        required = sum(1 for dep in self.dependencies.values() if dep.required)
        return required / len(self.dependencies)

    def dependency_strength_stats(self) -> Dict[str, float]:
        """Calculate average, min, and max dependency strengths.

        Returns:
            Dict with avg, min, and max strength values.
        """
        if not self.dependencies:
            return {"avg": 0.0, "min": 0.0, "max": 0.0}
        strengths = [dep.strength for dep in self.dependencies.values()]
        return {
            "avg": sum(strengths) / len(strengths),
            "min": min(strengths),
            "max": max(strengths),
        }

    def average_required_dependencies_per_node(self) -> float:
        """Calculate average required dependencies per node.

        Returns:
            Mean required dependency count, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        required_connections = sum(
            len([dep for dep in self.get_dependencies_for_node(nid) if dep.required])
            for nid in self.nodes.keys()
        )
        return (required_connections / 2) / len(self.nodes)


    # ------------------------------------------------------------------ #
    # Batch 224: Dependency graph analysis and statistics methods        #
    # ------------------------------------------------------------------ #

    def node_confidence_min(self) -> float:
        """Get minimum confidence across nodes.

        Returns:
            Minimum confidence, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        return min(node.confidence for node in self.nodes.values())

    def node_confidence_max(self) -> float:
        """Get maximum confidence across nodes.

        Returns:
            Maximum confidence, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        return max(node.confidence for node in self.nodes.values())

    def node_confidence_range(self) -> float:
        """Get range of confidence values across nodes.

        Returns:
            Max minus min confidence, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        return self.node_confidence_max() - self.node_confidence_min()

    def average_satisfied_confidence(self) -> float:
        """Calculate average confidence for satisfied nodes.

        Returns:
            Mean confidence for satisfied nodes, or 0.0 if none.
        """
        satisfied = [node.confidence for node in self.nodes.values() if node.satisfied]
        if not satisfied:
            return 0.0
        return sum(satisfied) / len(satisfied)

    def average_unsatisfied_confidence(self) -> float:
        """Calculate average confidence for unsatisfied nodes.

        Returns:
            Mean confidence for unsatisfied nodes, or 0.0 if none.
        """
        unsatisfied = [node.confidence for node in self.nodes.values() if not node.satisfied]
        if not unsatisfied:
            return 0.0
        return sum(unsatisfied) / len(unsatisfied)

    def optional_dependency_count(self) -> int:
        """Count dependencies marked as optional.

        Returns:
            Number of optional dependencies.
        """
        return sum(1 for dep in self.dependencies.values() if not dep.required)

    def required_dependency_count_for_node(self, node_id: str) -> int:
        """Count required dependencies involving a node.

        Args:
            node_id: Node identifier

        Returns:
            Number of required dependencies involving the node.
        """
        return len([dep for dep in self.get_dependencies_for_node(node_id) if dep.required])

    def nodes_without_dependencies_count(self) -> int:
        """Count nodes that have no dependencies.

        Returns:
            Number of nodes with zero dependencies.
        """
        return sum(1 for node_id in self.nodes.keys() if not self.get_dependencies_for_node(node_id))

    def dependency_strength_average_required(self) -> float:
        """Calculate average strength of required dependencies.

        Returns:
            Mean strength of required dependencies, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if dep.required]
        if not strengths:
            return 0.0
        return sum(strengths) / len(strengths)

    def dependency_strength_average_optional(self) -> float:
        """Calculate average strength of optional dependencies.

        Returns:
            Mean strength of optional dependencies, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if not dep.required]
        if not strengths:
            return 0.0
        return sum(strengths) / len(strengths)


    # ------------------------------------------------------------------ #
    # Batch 227: Dependency graph analysis and statistics methods        #
    # ------------------------------------------------------------------ #

    def node_ids(self) -> List[str]:
        """Return sorted list of node IDs.

        Returns:
            Sorted list of node identifiers.
        """
        return sorted(self.nodes.keys())

    def dependency_ids(self) -> List[str]:
        """Return sorted list of dependency IDs.

        Returns:
            Sorted list of dependency identifiers.
        """
        return sorted(self.dependencies.keys())

    def satisfied_node_ratio(self) -> float:
        """Calculate ratio of satisfied nodes.

        Returns:
            Ratio of satisfied nodes, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        return self.satisfied_node_count() / len(self.nodes)

    def dependency_density(self) -> float:
        """Calculate dependency density for directed graph.

        Returns:
            Density ratio (0.0 to 1.0), or 0.0 if fewer than 2 nodes.
        """
        n = len(self.nodes)
        if n < 2:
            return 0.0
        max_possible = n * (n - 1)
        return len(self.dependencies) / max_possible

    def average_dependencies_per_satisfied_node(self) -> float:
        """Calculate average dependencies per satisfied node.

        Returns:
            Mean dependency count, or 0.0 if no satisfied nodes.
        """
        satisfied_nodes = [node_id for node_id, node in self.nodes.items() if node.satisfied]
        if not satisfied_nodes:
            return 0.0
        total = sum(len(self.get_dependencies_for_node(node_id)) for node_id in satisfied_nodes)
        return total / len(satisfied_nodes)

    def average_dependencies_per_unsatisfied_node(self) -> float:
        """Calculate average dependencies per unsatisfied node.

        Returns:
            Mean dependency count, or 0.0 if no unsatisfied nodes.
        """
        unsatisfied_nodes = [node_id for node_id, node in self.nodes.items() if not node.satisfied]
        if not unsatisfied_nodes:
            return 0.0
        total = sum(len(self.get_dependencies_for_node(node_id)) for node_id in unsatisfied_nodes)
        return total / len(unsatisfied_nodes)

    def dependency_strength_min_required(self) -> float:
        """Get minimum strength among required dependencies.

        Returns:
            Minimum strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if dep.required]
        if not strengths:
            return 0.0
        return min(strengths)

    def dependency_strength_max_required(self) -> float:
        """Get maximum strength among required dependencies.

        Returns:
            Maximum strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if dep.required]
        if not strengths:
            return 0.0
        return max(strengths)

    def dependency_strength_min_optional(self) -> float:
        """Get minimum strength among optional dependencies.

        Returns:
            Minimum strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if not dep.required]
        if not strengths:
            return 0.0
        return min(strengths)

    def dependency_strength_max_optional(self) -> float:
        """Get maximum strength among optional dependencies.

        Returns:
            Maximum strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if not dep.required]
        if not strengths:
            return 0.0
        return max(strengths)


    # ------------------------------------------------------------------ #
    # Batch 228: Dependency graph analysis and statistics methods        #
    # ------------------------------------------------------------------ #

    def nodes_with_confidence_above(self, threshold: float) -> int:
        """Count nodes with confidence above a threshold.

        Args:
            threshold: Confidence threshold

        Returns:
            Number of nodes with confidence above threshold.
        """
        return sum(1 for node in self.nodes.values() if node.confidence > threshold)

    def nodes_with_confidence_below(self, threshold: float) -> int:
        """Count nodes with confidence below a threshold.

        Args:
            threshold: Confidence threshold

        Returns:
            Number of nodes with confidence below threshold.
        """
        return sum(1 for node in self.nodes.values() if node.confidence < threshold)

    def dependency_strength_range(self) -> float:
        """Calculate range of dependency strengths.

        Returns:
            Max minus min strength, or 0.0 if no dependencies.
        """
        if not self.dependencies:
            return 0.0
        strengths = [dep.strength for dep in self.dependencies.values()]
        return max(strengths) - min(strengths)

    def dependency_strength_range_required(self) -> float:
        """Calculate range of strengths for required dependencies.

        Returns:
            Max minus min strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if dep.required]
        if not strengths:
            return 0.0
        return max(strengths) - min(strengths)

    def dependency_strength_range_optional(self) -> float:
        """Calculate range of strengths for optional dependencies.

        Returns:
            Max minus min strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if not dep.required]
        if not strengths:
            return 0.0
        return max(strengths) - min(strengths)

    def average_dependencies_per_claim_node(self) -> float:
        """Calculate average dependencies per claim node.

        Returns:
            Mean dependency count for claim nodes, or 0.0 if none.
        """
        claim_nodes = [node.id for node in self.get_nodes_by_type(NodeType.CLAIM)]
        if not claim_nodes:
            return 0.0
        total = sum(len(self.get_dependencies_for_node(node_id)) for node_id in claim_nodes)
        return total / len(claim_nodes)

    def average_dependencies_per_evidence_node(self) -> float:
        """Calculate average dependencies per evidence node.

        Returns:
            Mean dependency count for evidence nodes, or 0.0 if none.
        """
        evidence_nodes = [node.id for node in self.get_nodes_by_type(NodeType.EVIDENCE)]
        if not evidence_nodes:
            return 0.0
        total = sum(len(self.get_dependencies_for_node(node_id)) for node_id in evidence_nodes)
        return total / len(evidence_nodes)

    def average_dependencies_per_requirement_node(self) -> float:
        """Calculate average dependencies per requirement node.

        Returns:
            Mean dependency count for requirement nodes, or 0.0 if none.
        """
        requirement_nodes = [node.id for node in self.get_nodes_by_type(NodeType.REQUIREMENT)]
        if not requirement_nodes:
            return 0.0
        total = sum(len(self.get_dependencies_for_node(node_id)) for node_id in requirement_nodes)
        return total / len(requirement_nodes)

    def node_type_distribution_for_satisfaction(self, satisfied: bool = True) -> Dict[str, int]:
        """Get node type distribution for satisfied or unsatisfied nodes.

        Args:
            satisfied: Whether to count satisfied or unsatisfied nodes

        Returns:
            Dict mapping node types to counts.
        """
        counts: Dict[str, int] = {}
        for node in self.nodes.values():
            if node.satisfied != satisfied:
                continue
            ntype = node.node_type.value
            counts[ntype] = counts.get(ntype, 0) + 1
        return counts

    def dependency_strength_median(self) -> float:
        """Calculate median dependency strength.

        Returns:
            Median strength, or 0.0 if no dependencies.
        """
        if not self.dependencies:
            return 0.0
        strengths = sorted(dep.strength for dep in self.dependencies.values())
        mid = len(strengths) // 2
        if len(strengths) % 2 == 1:
            return strengths[mid]
        return (strengths[mid - 1] + strengths[mid]) / 2


class DependencyGraphBuilder:
    """
    Builds dependency graphs from claims and requirements.
    
    This builder creates the dependency structure showing what each claim
    requires and tracks satisfaction as evidence is gathered.
    """
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.node_counter = 0
        self.dependency_counter = 0
    
    def build_from_claims(self, claims: List[Dict[str, Any]], 
                          legal_requirements: Optional[Dict[str, Any]] = None) -> DependencyGraph:
        """
        Build a dependency graph from claims and legal requirements.
        
        Args:
            claims: List of claim dictionaries with name, type, description
            legal_requirements: Optional legal requirement mappings
            
        Returns:
            A DependencyGraph instance
        """
        graph = DependencyGraph()
        
        # Create claim nodes
        claim_nodes = []
        for claim_data in claims:
            node = DependencyNode(
                id=self._get_node_id(),
                node_type=NodeType.CLAIM,
                name=claim_data.get('name', 'Unnamed Claim'),
                description=claim_data.get('description', ''),
                attributes={'claim_type': claim_data.get('type', 'unknown')}
            )
            graph.add_node(node)
            claim_nodes.append(node)

        def has_date(text_value: str) -> bool:
            if not text_value:
                return False
            patterns = [
                r'\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+\d{4}\b',
                r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
                r'\b\d{4}-\d{2}-\d{2}\b',
            ]
            return any(re.search(p, text_value) for p in patterns)

        def has_actor_signal(text_value: str) -> bool:
            if not text_value:
                return False
            lower = text_value.lower()
            actor_keywords = [
                "employer", "company", "organization", "business", "manager", "supervisor",
                "boss", "hr", "human resources", "landlord", "owner", "agency", "department",
                "school", "university", "hospital", "clinic", "doctor", "nurse", "teacher",
                "principal", "officer", "agent", "neighbor", "coworker", "co-worker",
                "colleague", "respondent",
            ]
            return any(k in lower for k in actor_keywords)
        
        # Add lightweight fact dependencies to avoid empty graphs when legal requirements are absent.
        for claim_node in claim_nodes:
            claim_text = f"{claim_node.name} {claim_node.description}".strip()

            if not has_date(claim_text):
                timeline_node = DependencyNode(
                    id=self._get_node_id(),
                    node_type=NodeType.FACT,
                    name="Timeline of events",
                    description="Dates or sequence of key events related to this claim",
                    satisfied=False,
                    confidence=0.0
                )
                graph.add_node(timeline_node)
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(),
                    source_id=timeline_node.id,
                    target_id=claim_node.id,
                    dependency_type=DependencyType.DEPENDS_ON,
                    required=True
                ))

            if not has_actor_signal(claim_text):
                actor_node = DependencyNode(
                    id=self._get_node_id(),
                    node_type=NodeType.FACT,
                    name="Responsible party",
                    description="Who took the action or decision tied to this claim",
                    satisfied=False,
                    confidence=0.0
                )
                graph.add_node(actor_node)
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(),
                    source_id=actor_node.id,
                    target_id=claim_node.id,
                    dependency_type=DependencyType.DEPENDS_ON,
                    required=True
                ))

        # Add legal requirements for each claim
        if legal_requirements:
            for claim_node in claim_nodes:
                claim_type = claim_node.attributes.get('claim_type')
                requirements = legal_requirements.get(claim_type, [])
                
                for req_data in requirements:
                    req_node = DependencyNode(
                        id=self._get_node_id(),
                        node_type=NodeType.LEGAL_ELEMENT,
                        name=req_data.get('name', 'Unnamed Requirement'),
                        description=req_data.get('description', ''),
                        satisfied=False
                    )
                    graph.add_node(req_node)
                    
                    # Create dependency: claim requires legal element
                    dep = Dependency(
                        id=self._get_dependency_id(),
                        source_id=req_node.id,
                        target_id=claim_node.id,
                        dependency_type=DependencyType.REQUIRES,
                        required=True
                    )
                    graph.add_dependency(dep)
        
        logger.info(f"Built dependency graph: {graph.summary()}")
        return graph
    
    def add_evidence_to_graph(self, graph: DependencyGraph, 
                             evidence_data: Dict[str, Any],
                             supports_claim_id: str) -> str:
        """
        Add evidence to the dependency graph.
        
        Args:
            graph: The dependency graph to update
            evidence_data: Evidence information
            supports_claim_id: ID of claim this evidence supports
            
        Returns:
            The ID of the created evidence node
        """
        evidence_node = DependencyNode(
            id=self._get_node_id(),
            node_type=NodeType.EVIDENCE,
            name=evidence_data.get('name', 'Unnamed Evidence'),
            description=evidence_data.get('description', ''),
            satisfied=True,  # Evidence is inherently satisfied once provided
            confidence=evidence_data.get('confidence', 0.8),
            attributes=evidence_data.get('attributes', {})
        )
        graph.add_node(evidence_node)
        
        # Create support relationship
        dep = Dependency(
            id=self._get_dependency_id(),
            source_id=evidence_node.id,
            target_id=supports_claim_id,
            dependency_type=DependencyType.SUPPORTS,
            required=False,
            strength=evidence_data.get('strength', 0.7)
        )
        graph.add_dependency(dep)
        
        return evidence_node.id
    
    def _get_node_id(self) -> str:
        """Generate unique node ID."""
        self.node_counter += 1
        return f"node_{self.node_counter}"
    
    def _get_dependency_id(self) -> str:
        """Generate unique dependency ID."""
        self.dependency_counter += 1
        return f"dep_{self.dependency_counter}"
