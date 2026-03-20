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
    BEFORE = "before"
    SAME_TIME = "same_time"
    OVERLAPS = "overlaps"


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

    def get_temporal_dependencies(self) -> List[Dependency]:
        """Return temporal ordering dependencies present in the graph."""
        temporal_types = {
            DependencyType.BEFORE,
            DependencyType.SAME_TIME,
            DependencyType.OVERLAPS,
        }
        return [
            dep for dep in self.dependencies.values()
            if dep.dependency_type in temporal_types
        ]

    def detect_temporal_cycles(self) -> List[List[str]]:
        """Detect cycles among BEFORE dependencies and return node-id cycles."""
        adjacency: Dict[str, List[str]] = {}
        for dep in self.dependencies.values():
            if dep.dependency_type != DependencyType.BEFORE:
                continue
            adjacency.setdefault(dep.source_id, []).append(dep.target_id)

        cycles: List[List[str]] = []
        seen_cycle_keys = set()

        def _canonical_cycle_key(path: List[str]) -> tuple[str, ...]:
            core = path[:-1] if len(path) > 1 and path[0] == path[-1] else path
            if not core:
                return tuple()
            rotations = [tuple(core[index:] + core[:index]) for index in range(len(core))]
            reversed_core = list(reversed(core))
            rotations.extend(tuple(reversed_core[index:] + reversed_core[:index]) for index in range(len(reversed_core)))
            return min(rotations)

        def _visit(node_id: str, stack: List[str], visiting: set[str]) -> None:
            visiting.add(node_id)
            stack.append(node_id)
            for neighbor_id in adjacency.get(node_id, []):
                if neighbor_id in visiting:
                    cycle_start = stack.index(neighbor_id)
                    cycle_path = stack[cycle_start:] + [neighbor_id]
                    cycle_key = _canonical_cycle_key(cycle_path)
                    if cycle_key and cycle_key not in seen_cycle_keys:
                        seen_cycle_keys.add(cycle_key)
                        cycles.append(cycle_path)
                    continue
                if neighbor_id in stack:
                    continue
                _visit(neighbor_id, stack, visiting)
            stack.pop()
            visiting.remove(node_id)

        for node_id in list(adjacency.keys()):
            _visit(node_id, [], set())

        return cycles

    def get_temporal_inconsistency_issues(self) -> List[Dict[str, Any]]:
        """Return temporal inconsistency diagnostics derived from temporal edges."""
        issues: List[Dict[str, Any]] = []
        pair_type_map: Dict[tuple[str, str], set[str]] = {}
        directional_before_pairs = set()

        for dep in self.get_temporal_dependencies():
            source_id = str(dep.source_id)
            target_id = str(dep.target_id)
            relation_type = dep.dependency_type.value
            pair_key = tuple(sorted((source_id, target_id)))
            pair_type_map.setdefault(pair_key, set()).add(relation_type)
            if dep.dependency_type == DependencyType.BEFORE:
                directional_before_pairs.add((source_id, target_id))

        for cycle_index, cycle in enumerate(self.detect_temporal_cycles(), start=1):
            node_names = [self.get_node(node_id).name if self.get_node(node_id) else node_id for node_id in cycle[:-1]]
            summary = f"Temporal cycle detected: {' -> '.join(node_names + [node_names[0]])}"
            issues.append({
                'issue_id': f'temporal_cycle_{cycle_index:03d}',
                'issue_type': 'temporal_cycle',
                'summary': summary,
                'severity': 'blocking',
                'recommended_resolution_lane': 'request_document',
                'current_resolution_status': 'open',
                'external_corroboration_required': True,
                'node_ids': cycle[:-1],
                'node_names': node_names,
            })

        for pair_index, (pair_key, relation_types) in enumerate(sorted(pair_type_map.items()), start=1):
            left_id, right_id = pair_key
            left_node = self.get_node(left_id)
            right_node = self.get_node(right_id)
            left_name = left_node.name if left_node else left_id
            right_name = right_node.name if right_node else right_id

            if 'before' in relation_types and 'same_time' in relation_types:
                issues.append({
                    'issue_id': f'temporal_conflict_{pair_index:03d}',
                    'issue_type': 'temporal_relation_conflict',
                    'summary': f'Temporal relation conflict: {left_name} cannot be both before and simultaneous with {right_name}',
                    'severity': 'blocking',
                    'recommended_resolution_lane': 'request_document',
                    'current_resolution_status': 'open',
                    'external_corroboration_required': True,
                    'left_node_id': left_id,
                    'right_node_id': right_id,
                    'left_node_name': left_name,
                    'right_node_name': right_name,
                    'relation_types': sorted(relation_types),
                })

            if (left_id, right_id) in directional_before_pairs and (right_id, left_id) in directional_before_pairs:
                issues.append({
                    'issue_id': f'temporal_reverse_before_{pair_index:03d}',
                    'issue_type': 'temporal_reverse_before',
                    'summary': f'Temporal ordering conflict: {left_name} is marked before {right_name} and {right_name} is marked before {left_name}',
                    'severity': 'blocking',
                    'recommended_resolution_lane': 'request_document',
                    'current_resolution_status': 'open',
                    'external_corroboration_required': True,
                    'left_node_id': left_id,
                    'right_node_id': right_id,
                    'left_node_name': left_name,
                    'right_node_name': right_name,
                    'relation_types': ['before'],
                })

        return issues


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

        def has_protected_activity_signal(text_value: str) -> bool:
            if not text_value:
                return False
            lower = text_value.lower()
            return any(
                token in lower
                for token in [
                    "protected activity",
                    "complained",
                    "reported",
                    "grievance",
                    "whistle",
                    "requested accommodation",
                    "requested help",
                ]
            )

        def has_adverse_action_signal(text_value: str) -> bool:
            if not text_value:
                return False
            lower = text_value.lower()
            return any(
                token in lower
                for token in [
                    "fired",
                    "terminated",
                    "demoted",
                    "suspended",
                    "disciplined",
                    "reduced hours",
                    "cut hours",
                    "evicted",
                ]
            )

        def has_notice_signal(text_value: str) -> bool:
            if not text_value:
                return False
            lower = text_value.lower()
            return any(token in lower for token in ["notice", "letter", "email", "message"])

        def has_hearing_signal(text_value: str) -> bool:
            if not text_value:
                return False
            lower = text_value.lower()
            return any(token in lower for token in ["hearing", "grievance", "appeal"])

        def has_causation_signal(text_value: str) -> bool:
            if not text_value:
                return False
            lower = text_value.lower()
            has_connector = any(
                token in lower
                for token in ["because", "due to", "in response to", "soon after", "after", "as a result"]
            )
            return has_connector and has_protected_activity_signal(text_value) and has_adverse_action_signal(text_value)
        
        # Add lightweight fact dependencies to avoid empty graphs when legal requirements are absent.
        for claim_node in claim_nodes:
            claim_text = f"{claim_node.name} {claim_node.description}".strip()
            claim_type = str(claim_node.attributes.get("claim_type") or "").strip().lower()

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
            if not (has_date(claim_text) and has_actor_signal(claim_text)):
                decision_timeline_node = DependencyNode(
                    id=self._get_node_id(),
                    node_type=NodeType.FACT,
                    name="Actor-by-actor decision timeline",
                    description=(
                        "For each actor, identify the decision/action taken and the date anchor "
                        "(or best estimate) for that step"
                    ),
                    satisfied=False,
                    confidence=0.0,
                )
                graph.add_node(decision_timeline_node)
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(),
                    source_id=decision_timeline_node.id,
                    target_id=claim_node.id,
                    dependency_type=DependencyType.DEPENDS_ON,
                    required=True,
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

            # Retaliation claims need explicit causation sequencing (protected activity -> adverse action).
            retaliation_like = "retaliat" in claim_type or "retaliat" in claim_text.lower()
            if retaliation_like:
                if not has_protected_activity_signal(claim_text):
                    protected_activity_node = DependencyNode(
                        id=self._get_node_id(),
                        node_type=NodeType.FACT,
                        name="Protected activity facts",
                        description="What protected activity occurred, to whom it was reported, and when",
                        satisfied=False,
                        confidence=0.0,
                    )
                    graph.add_node(protected_activity_node)
                    graph.add_dependency(Dependency(
                        id=self._get_dependency_id(),
                        source_id=protected_activity_node.id,
                        target_id=claim_node.id,
                        dependency_type=DependencyType.DEPENDS_ON,
                        required=True,
                    ))

                if not has_adverse_action_signal(claim_text):
                    adverse_action_node = DependencyNode(
                        id=self._get_node_id(),
                        node_type=NodeType.FACT,
                        name="Adverse action facts",
                        description="What happened after protected activity, by whom, and on what date",
                        satisfied=False,
                        confidence=0.0,
                    )
                    graph.add_node(adverse_action_node)
                    graph.add_dependency(Dependency(
                        id=self._get_dependency_id(),
                        source_id=adverse_action_node.id,
                        target_id=claim_node.id,
                        dependency_type=DependencyType.DEPENDS_ON,
                        required=True,
                    ))

                if not (has_date(claim_text) and has_actor_signal(claim_text)):
                    causation_node = DependencyNode(
                        id=self._get_node_id(),
                        node_type=NodeType.FACT,
                        name="Retaliation causation chronology",
                        description="Sequence from protected activity to adverse action with dates and actor identities",
                        satisfied=False,
                        confidence=0.0,
                    )
                    graph.add_node(causation_node)
                    graph.add_dependency(Dependency(
                        id=self._get_dependency_id(),
                        source_id=causation_node.id,
                        target_id=claim_node.id,
                        dependency_type=DependencyType.DEPENDS_ON,
                        required=True,
                    ))
                if not has_causation_signal(claim_text):
                    causation_link_node = DependencyNode(
                        id=self._get_node_id(),
                        node_type=NodeType.FACT,
                        name="Retaliation causation link facts",
                        description=(
                            "Facts that directly connect protected activity to the adverse treatment, "
                            "including actors and date anchors for each step"
                        ),
                        satisfied=False,
                        confidence=0.0,
                    )
                    graph.add_node(causation_link_node)
                    graph.add_dependency(Dependency(
                        id=self._get_dependency_id(),
                        source_id=causation_link_node.id,
                        target_id=claim_node.id,
                        dependency_type=DependencyType.DEPENDS_ON,
                        required=True,
                    ))

            if has_notice_signal(claim_text) and not has_date(claim_text):
                notice_node = DependencyNode(
                    id=self._get_node_id(),
                    node_type=NodeType.FACT,
                    name="Written notice date",
                    description="Date and sender of any written notice, letter, email, or message",
                    satisfied=False,
                    confidence=0.0,
                )
                graph.add_node(notice_node)
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(),
                    source_id=notice_node.id,
                    target_id=claim_node.id,
                    dependency_type=DependencyType.DEPENDS_ON,
                    required=True,
                ))

            if has_hearing_signal(claim_text) and not has_date(claim_text):
                hearing_node = DependencyNode(
                    id=self._get_node_id(),
                    node_type=NodeType.FACT,
                    name="Hearing request date",
                    description="Date a hearing/grievance/appeal was requested and any response date",
                    satisfied=False,
                    confidence=0.0,
                )
                graph.add_node(hearing_node)
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(),
                    source_id=hearing_node.id,
                    target_id=claim_node.id,
                    dependency_type=DependencyType.DEPENDS_ON,
                    required=True,
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

    def sync_intake_timeline_to_graph(
        self,
        graph: DependencyGraph,
        intake_case_file: Optional[Dict[str, Any]],
    ) -> DependencyGraph:
        """Synchronize structured intake timeline facts and temporal edges into a dependency graph."""
        if not isinstance(graph, DependencyGraph):
            return graph

        case_file = intake_case_file if isinstance(intake_case_file, dict) else {}
        canonical_facts = case_file.get('canonical_facts') if isinstance(case_file.get('canonical_facts'), list) else []
        timeline_relations = case_file.get('timeline_relations') if isinstance(case_file.get('timeline_relations'), list) else []

        temporal_node_ids = [
            node_id
            for node_id, node in graph.nodes.items()
            if isinstance(node.attributes, dict) and node.attributes.get('timeline_fact_node')
        ]
        if temporal_node_ids:
            temporal_node_id_set = set(temporal_node_ids)
            graph.dependencies = {
                dep_id: dep
                for dep_id, dep in graph.dependencies.items()
                if dep.source_id not in temporal_node_id_set and dep.target_id not in temporal_node_id_set
            }
            for node_id in temporal_node_ids:
                graph.nodes.pop(node_id, None)

        claim_nodes = graph.get_nodes_by_type(NodeType.CLAIM)
        claim_nodes_by_type = {
            str(node.attributes.get('claim_type') or '').strip(): node
            for node in claim_nodes
            if isinstance(node.attributes, dict)
        }
        timeline_node_ids_by_fact_id: Dict[str, str] = {}

        for fact in canonical_facts:
            if not isinstance(fact, dict):
                continue
            temporal_context = fact.get('temporal_context') if isinstance(fact.get('temporal_context'), dict) else {}
            if (
                str(fact.get('fact_type') or '').strip().lower() != 'timeline'
                and not temporal_context.get('start_date')
                and not temporal_context.get('relative_markers')
            ):
                continue

            fact_id = str(fact.get('fact_id') or '').strip()
            if not fact_id:
                continue
            node_id = self._get_node_id()
            timeline_node = DependencyNode(
                id=node_id,
                node_type=NodeType.FACT,
                name=str(fact.get('text') or fact_id),
                description=str(fact.get('event_date_or_range') or fact.get('text') or ''),
                satisfied=bool(temporal_context.get('start_date')),
                confidence=float(fact.get('confidence', 0.0) or 0.0),
                attributes={
                    'timeline_fact_node': True,
                    'source_fact_id': fact_id,
                    'fact_type': fact.get('fact_type'),
                    'event_date_or_range': fact.get('event_date_or_range'),
                    'temporal_context': temporal_context,
                    'claim_types': list(fact.get('claim_types') or []),
                    'element_tags': list(fact.get('element_tags') or []),
                },
            )
            graph.add_node(timeline_node)
            timeline_node_ids_by_fact_id[fact_id] = node_id

            target_claim_nodes = []
            claim_types = [str(item).strip() for item in (fact.get('claim_types') or []) if str(item).strip()]
            for claim_type in claim_types:
                claim_node = claim_nodes_by_type.get(claim_type)
                if claim_node is not None:
                    target_claim_nodes.append(claim_node)
            if not target_claim_nodes:
                target_claim_nodes = claim_nodes

            for claim_node in target_claim_nodes:
                graph.add_dependency(
                    Dependency(
                        id=self._get_dependency_id(),
                        source_id=timeline_node.id,
                        target_id=claim_node.id,
                        dependency_type=DependencyType.SUPPORTS,
                        required=False,
                        strength=max(0.1, min(1.0, float(fact.get('confidence', 0.0) or 0.0))),
                    )
                )

        relation_type_map = {
            'before': DependencyType.BEFORE,
            'same_time': DependencyType.SAME_TIME,
            'overlaps': DependencyType.OVERLAPS,
        }
        for relation in timeline_relations:
            if not isinstance(relation, dict):
                continue
            source_fact_id = str(relation.get('source_fact_id') or '').strip()
            target_fact_id = str(relation.get('target_fact_id') or '').strip()
            dependency_type = relation_type_map.get(str(relation.get('relation_type') or '').strip())
            source_node_id = timeline_node_ids_by_fact_id.get(source_fact_id)
            target_node_id = timeline_node_ids_by_fact_id.get(target_fact_id)
            if not dependency_type or not source_node_id or not target_node_id:
                continue
            confidence = str(relation.get('confidence') or '').strip().lower()
            strength = 0.7 if confidence == 'high' else 0.55 if confidence == 'medium' else 0.4
            graph.add_dependency(
                Dependency(
                    id=self._get_dependency_id(),
                    source_id=source_node_id,
                    target_id=target_node_id,
                    dependency_type=dependency_type,
                    required=False,
                    strength=strength,
                )
            )

        graph._update_metadata()
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
