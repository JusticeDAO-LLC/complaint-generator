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
from .intake_claim_registry import normalize_claim_type

logger = logging.getLogger(__name__)

_NAME_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
_CONFIRMATION_PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:needs?\s+confirmation|to\s+be\s+confirmed|confirm(?:ed|ation)?\s+pending|tbd|unknown|not\s+sure|unclear|pending)\b",
    flags=re.IGNORECASE,
)
_DATE_TOKEN_PATTERN = re.compile(
    r"(?:\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+\d{1,2}(?:,\s*\d{4})?\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b|\b(?:19|20)\d{2}\b)",
    flags=re.IGNORECASE,
)
_ACTOR_CRITIC_PHASE_FOCUS_ORDER = ("graph_analysis", "document_generation", "intake_questioning")
_ACTOR_CRITIC_PRIORITY = 70
_ACTOR_CRITIC_FOCUS_METRICS = {
    "empathy": 0.22,
    "question_quality": 0.58,
    "information_extraction": 0.72,
    "coverage": 0.69,
    "patchability": 0.74,
}
_ACTOR_CRITIC_WEAK_CLAIM_TYPES = {"housing_discrimination", "hacc_research_engine"}
_ACTOR_CRITIC_WEAK_EVIDENCE_MODALITIES = {"policy_document", "file_evidence"}


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
        def _normalize_key_fragment(value: Any) -> str:
            normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
            normalized = re.sub(r"_+", "_", normalized).strip("_")
            return normalized

        def _as_text(value: Any) -> str:
            return str(value or "").strip()

        def _is_unspecified_value(value: Any) -> bool:
            text = _as_text(value)
            if not text:
                return True
            return bool(_CONFIRMATION_PLACEHOLDER_PATTERN.search(text))

        def _contains_name(text: str) -> bool:
            if not text:
                return False
            if _NAME_PATTERN.search(text):
                return True
            if any(token in text.lower() for token in {"manager", "director", "officer", "agent", "supervisor"}):
                return True
            return False

        def _contains_date_token(text: str) -> bool:
            if not text:
                return False
            return bool(_DATE_TOKEN_PATTERN.search(text))

        def _core_structured_gap(gap_type: str) -> bool:
            return gap_type in {
                "missing_exact_action_dates",
                "missing_hearing_request_date",
                "missing_response_dates",
                "missing_hearing_timing",
                "missing_staff_identity",
                "missing_staff_title",
                "retaliation_missing_causation_link",
                "retaliation_missing_causation",
                "retaliation_missing_sequencing_dates",
                "retaliation_missing_sequence",
                "missing_decision_timeline",
            }

        def _infer_gap_type(
            claim_type: str,
            source_name: str,
            source_description: str,
            source_attrs: Dict[str, Any],
            requirement_key: str,
            evidence_modality: str,
        ) -> str:
            explicit = _as_text(source_attrs.get("gap_type")).lower()
            if explicit:
                return explicit
            corpus = " ".join(
                [
                    claim_type,
                    source_name,
                    source_description,
                    requirement_key,
                    _as_text(source_attrs.get("requirement_label")),
                    _as_text(source_attrs.get("question_hint")),
                ]
            ).lower()
            if "hearing request" in corpus and "date" in corpus:
                return "missing_hearing_request_date"
            if "hearing" in corpus and any(token in corpus for token in {"timing", "deadline", "within", "days", "date"}):
                return "missing_hearing_timing"
            if any(token in corpus for token in {"response date", "response timing", "reply date", "date of response", "responded on"}):
                return "missing_response_dates"
            if "written notice" in corpus or ("notice" in corpus and "written" in corpus):
                return "missing_written_notice"
            if any(token in corpus for token in {"staff name", "decision maker", "who denied", "who approved", "who decided", "responsible staff", "manager name", "director name"}):
                return "missing_staff_identity"
            if any(token in corpus for token in {"staff title", "job title", "position title", "role of"}):
                return "missing_staff_title"
            if "retaliat" in corpus and any(token in corpus for token in {"causation", "because", "in response to", "motivated by"}):
                return "retaliation_missing_causation_link"
            if "retaliat" in corpus and any(token in corpus for token in {"sequence", "timeline", "before", "after", "chronology"}):
                return "retaliation_missing_sequencing_dates"
            if any(token in corpus for token in {"timeline", "chronology", "date", "dated", "when", "before", "after"}):
                return "missing_exact_action_dates"
            if evidence_modality == "policy_document":
                return "missing_written_notice"
            if evidence_modality == "file_evidence":
                return "missing_response_dates"
            return "missing_claim_element"

        def _required_fields_for_gap(gap_type: str) -> List[str]:
            mapping = {
                "missing_exact_action_dates": ["event_date", "adverse_action"],
                "missing_hearing_request_date": ["hearing_request_date", "hearing_request_actor"],
                "missing_response_dates": ["response_date", "response_actor"],
                "missing_hearing_timing": ["adverse_action_date", "hearing_request_date"],
                "missing_staff_identity": ["staff_name", "staff_role"],
                "missing_staff_title": ["staff_name", "staff_title"],
                "retaliation_missing_causation": ["protected_activity", "adverse_action", "causation_link"],
                "retaliation_missing_causation_link": ["protected_activity", "adverse_action", "causation_link"],
                "retaliation_missing_sequence": ["protected_activity_date", "adverse_action_date"],
                "retaliation_missing_sequencing_dates": ["protected_activity_date", "adverse_action_date"],
                "missing_written_notice": ["document_name", "document_date", "issuing_actor"],
                "missing_decision_timeline": ["decision_date", "decision_actor"],
                "missing_claim_element": ["supporting_fact"],
            }
            return list(mapping.get(gap_type, ["supporting_fact"]))

        def _field_aliases(field_name: str) -> List[str]:
            aliases = {
                "event_date": ["event_date", "date", "incident_date", "action_date"],
                "adverse_action": ["adverse_action", "action", "decision", "denial_reason"],
                "hearing_request_date": ["hearing_request_date", "appeal_date", "hearing_date_requested"],
                "hearing_request_actor": ["hearing_request_actor", "requestor", "requesting_party"],
                "response_date": ["response_date", "reply_date", "decision_date", "response_timing_date"],
                "response_actor": ["response_actor", "responding_staff", "decision_maker", "staff_name"],
                "adverse_action_date": ["adverse_action_date", "adverse_date", "denial_date", "decision_date"],
                "staff_name": ["staff_name", "decision_maker", "actor_name", "employee_name"],
                "staff_role": ["staff_role", "role", "position", "job_title", "staff_title"],
                "staff_title": ["staff_title", "job_title", "position_title", "title"],
                "protected_activity": ["protected_activity", "complaint_activity", "report_activity"],
                "causation_link": ["causation_link", "causal_statement", "retaliation_link", "motive"],
                "protected_activity_date": ["protected_activity_date", "activity_date", "complaint_date"],
                "document_name": ["document_name", "file_name", "policy_name", "notice_name"],
                "document_date": ["document_date", "notice_date", "file_date", "issued_date"],
                "issuing_actor": ["issuing_actor", "issuer", "author", "issuing_staff"],
                "decision_date": ["decision_date", "adverse_action_date", "response_date"],
                "decision_actor": ["decision_actor", "decision_maker", "staff_name", "actor_name"],
                "supporting_fact": ["supporting_fact", "fact", "detail", "narrative_detail"],
            }
            canonical = str(field_name or "").strip()
            return list(dict.fromkeys([canonical, *aliases.get(canonical, [])]))

        def _first_value(attrs: Dict[str, Any], keys: List[str]) -> str:
            for key in keys:
                if key in attrs and not _is_unspecified_value(attrs.get(key)):
                    return _as_text(attrs.get(key))
            return ""

        def _field_value(attrs: Dict[str, Any], field_name: str) -> str:
            return _first_value(attrs, _field_aliases(field_name))

        def _missing_required_fields(required_fields: List[str], source_attrs: Dict[str, Any]) -> List[str]:
            missing: List[str] = []
            for field_name in required_fields:
                aliases = _field_aliases(field_name)
                if not _first_value(source_attrs, aliases):
                    missing.append(field_name)
            return missing

        def _satisfaction_rules_for_gap(gap_type: str, requirement_key: str) -> Dict[str, Any]:
            rules = {
                "satisfy_when": "all_required_fields_present",
                "mark_requirement_keys": [requirement_key] if requirement_key else [],
                "mark_evidence_modalities": [],
                "promote_to_graph_first": [],
                "sequence_checks": [],
            }
            if gap_type in {"missing_exact_action_dates", "missing_hearing_request_date", "missing_response_dates", "missing_hearing_timing", "retaliation_missing_sequence", "retaliation_missing_sequencing_dates", "missing_decision_timeline"}:
                rules["promote_to_graph_first"].append("timeline")
                rules["sequence_checks"].append("validate_chronology")
            if gap_type in {"missing_staff_identity", "missing_staff_title", "missing_decision_timeline"}:
                rules["promote_to_graph_first"].append("staff_identity")
            if gap_type in {"missing_written_notice", "missing_response_dates"}:
                rules["mark_evidence_modalities"].append("policy_document_or_file_evidence")
            if gap_type in {"retaliation_missing_causation", "retaliation_missing_causation_link"}:
                rules["promote_to_graph_first"].append("causation_edge")
                rules["sequence_checks"].append("protected_activity_before_adverse_action")
            return rules

        def _critical_gap_signal(gap_type: str) -> float:
            critical = {
                "missing_exact_action_dates": 1.0,
                "missing_hearing_request_date": 1.0,
                "missing_response_dates": 1.0,
                "missing_hearing_timing": 0.95,
                "missing_staff_identity": 0.95,
                "missing_staff_title": 0.85,
                "retaliation_missing_causation_link": 1.0,
                "retaliation_missing_causation": 0.95,
                "retaliation_missing_sequencing_dates": 0.95,
                "retaliation_missing_sequence": 0.9,
                "missing_decision_timeline": 0.9,
                "missing_written_notice": 0.85,
            }
            return float(critical.get(gap_type, 0.6))

        def _extraction_targets_for_gap(gap_type: str) -> List[str]:
            mapping = {
                "missing_exact_action_dates": ["exact_dates", "event_order", "adverse_action"],
                "missing_hearing_request_date": ["exact_dates", "hearing_request", "decision_maker"],
                "missing_response_dates": ["exact_dates", "response_timing", "notice_chain"],
                "missing_hearing_timing": ["exact_dates", "event_order", "response_timing"],
                "missing_staff_identity": ["actor_name", "actor_role", "decision_maker"],
                "missing_staff_title": ["actor_name", "actor_role"],
                "retaliation_missing_causation": ["protected_activity", "adverse_action", "causation_link"],
                "retaliation_missing_causation_link": ["protected_activity", "adverse_action", "causation_link"],
                "retaliation_missing_sequence": ["exact_dates", "event_order", "causation_link"],
                "retaliation_missing_sequencing_dates": ["exact_dates", "event_order", "causation_link"],
                "missing_written_notice": ["document_type", "document_date", "document_owner"],
                "missing_decision_timeline": ["exact_dates", "event_order", "decision_maker"],
                "missing_claim_element": ["supporting_fact"],
            }
            return list(mapping.get(gap_type, ["supporting_fact"]))

        def _relation_updates_for_field(field_name: str) -> List[str]:
            mapping = {
                "event_date": ["link_event_sequence", "validate_temporal_order"],
                "adverse_action_date": ["link_event_sequence", "validate_temporal_order"],
                "hearing_request_date": ["link_response_to_hearing_or_action", "validate_temporal_order"],
                "response_date": ["link_response_to_hearing_or_action", "validate_temporal_order"],
                "protected_activity_date": ["link_causation_chain", "validate_temporal_order"],
                "staff_name": ["link_staff_to_action"],
                "staff_role": ["link_staff_to_action"],
                "staff_title": ["link_staff_to_action"],
                "decision_actor": ["link_staff_to_action"],
                "causation_link": ["link_causation_chain"],
                "document_name": ["link_document_to_claim"],
                "document_date": ["link_document_to_claim", "link_event_sequence"],
                "issuing_actor": ["link_document_to_claim", "link_staff_to_action"],
            }
            return list(mapping.get(field_name, []))

        def _entity_updates_for_field(field_name: str) -> List[str]:
            mapping = {
                "event_date": ["timeline_fact"],
                "adverse_action_date": ["timeline_fact"],
                "hearing_request_date": ["timeline_fact"],
                "response_date": ["timeline_fact"],
                "protected_activity_date": ["timeline_fact"],
                "staff_name": ["staff_actor"],
                "staff_role": ["staff_actor"],
                "staff_title": ["staff_actor"],
                "decision_actor": ["staff_actor"],
                "causation_link": ["causation_fact"],
                "document_name": ["document_evidence"],
                "document_date": ["document_evidence", "timeline_fact"],
                "issuing_actor": ["document_evidence", "staff_actor"],
            }
            return list(mapping.get(field_name, ["claim_fact"]))

        def _gap_type_rank(gap_type: str) -> int:
            order = [
                "missing_exact_action_dates",
                "missing_hearing_request_date",
                "missing_response_dates",
                "missing_hearing_timing",
                "missing_staff_identity",
                "missing_staff_title",
                "retaliation_missing_causation_link",
                "retaliation_missing_causation",
                "retaliation_missing_sequencing_dates",
                "retaliation_missing_sequence",
                "missing_decision_timeline",
                "missing_written_notice",
                "missing_claim_element",
                "missing_proof_leads",
            ]
            if gap_type in order:
                return order.index(gap_type)
            return len(order)

        def _build_answer_contract(
            gap_type: str,
            deterministic_update_key: str,
            requirement_key: str,
            source_attrs: Dict[str, Any],
        ) -> Dict[str, Any]:
            required_fields = _required_fields_for_gap(gap_type)
            missing_fields = _missing_required_fields(required_fields, source_attrs)
            present_fields = [field_name for field_name in required_fields if field_name not in missing_fields]
            relationship_updates: List[str] = []
            if "actor_name" in _extraction_targets_for_gap(gap_type):
                relationship_updates.append("link_staff_to_action")
            if "exact_dates" in _extraction_targets_for_gap(gap_type):
                relationship_updates.append("link_event_sequence")
            if "document_type" in _extraction_targets_for_gap(gap_type):
                relationship_updates.append("link_document_to_claim")
            if "causation_link" in _extraction_targets_for_gap(gap_type):
                relationship_updates.append("link_causation_chain")
            if "event_order" in _extraction_targets_for_gap(gap_type):
                relationship_updates.append("validate_temporal_order")
            if "response_timing" in _extraction_targets_for_gap(gap_type):
                relationship_updates.append("link_response_to_hearing_or_action")

            entity_updates = ["claim_fact"]
            if "exact_dates" in _extraction_targets_for_gap(gap_type):
                entity_updates.append("timeline_fact")
            if "actor_name" in _extraction_targets_for_gap(gap_type):
                entity_updates.append("staff_actor")
            if "document_type" in _extraction_targets_for_gap(gap_type):
                entity_updates.append("document_evidence")

            satisfaction_rules = _satisfaction_rules_for_gap(gap_type=gap_type, requirement_key=requirement_key)
            closure_confidence = 0.0
            if required_fields:
                closure_confidence = max(0.0, min(1.0, len(present_fields) / len(required_fields)))

            field_resolution_contract = {}
            for field_name in required_fields:
                field_value = _field_value(source_attrs, field_name)
                field_present = bool(field_value and not _is_unspecified_value(field_value))
                requirement_updates = [requirement_key] if requirement_key else []
                if field_present and field_name in {"event_date", "adverse_action_date", "hearing_request_date", "response_date", "protected_activity_date"}:
                    requirement_updates = list(dict.fromkeys([*requirement_updates, "chronology_complete"]))
                if field_present and field_name in {"staff_name", "staff_role", "staff_title", "decision_actor"}:
                    requirement_updates = list(dict.fromkeys([*requirement_updates, "staff_identity_complete"]))
                if field_present and field_name == "causation_link":
                    requirement_updates = list(dict.fromkeys([*requirement_updates, "causation_link_complete"]))
                field_resolution_contract[field_name] = {
                    "field_present": field_present,
                    "field_value": field_value if field_present else "",
                    "entity_updates": _entity_updates_for_field(field_name),
                    "relationship_updates": _relation_updates_for_field(field_name),
                    "requirement_updates": requirement_updates,
                    "satisfies_gap_when_present": field_name in missing_fields,
                }

            core_structured = _core_structured_gap(gap_type)
            return {
                "required_fields": required_fields,
                "missing_required_fields": missing_fields,
                "present_required_fields": present_fields,
                "entity_updates": entity_updates,
                "relationship_updates": relationship_updates,
                "requirement_updates": [requirement_key] if requirement_key else [],
                "resolution_key": deterministic_update_key,
                "satisfaction_rules": satisfaction_rules,
                "field_resolution_contract": field_resolution_contract,
                "closure_confidence": round(closure_confidence, 4),
                "single_turn_closable": len(missing_fields) <= 2,
                "single_field_closable": len(missing_fields) == 1,
                "core_structured_gap": core_structured,
                "question_strategy": (
                    "single_gap_closure"
                    if core_structured and missing_fields
                    else "collect_supporting_context"
                ),
            }

        def _build_deterministic_update_key(
            claim_id: str,
            claim_type: str,
            source_node: Optional[DependencyNode],
            source_attrs: Dict[str, Any],
            gap_type: str = "",
            requirement_key: str = "",
        ) -> str:
            explicit_gap_key = str(source_attrs.get("gap_key") or "").strip()
            if explicit_gap_key:
                return explicit_gap_key
            req_key = str(requirement_key or source_attrs.get("requirement_key") or "").strip()
            if req_key:
                type_fragment = _normalize_key_fragment(claim_type) or "claim"
                req_fragment = _normalize_key_fragment(req_key) or "requirement"
                return f"{type_fragment}:{req_fragment}"
            if gap_type:
                type_fragment = _normalize_key_fragment(claim_type) or "claim"
                gap_fragment = _normalize_key_fragment(gap_type) or "gap"
                return f"{type_fragment}:{gap_fragment}"

            source_fragment = _normalize_key_fragment(source_node.id if source_node else "") or "unknown_source"
            claim_fragment = _normalize_key_fragment(claim_type) or _normalize_key_fragment(claim_id) or "claim"
            return f"{claim_fragment}:{source_fragment}"

        claims = self.get_nodes_by_type(NodeType.CLAIM)
        nodes_by_id = self.nodes
        incoming_required_by_target: Dict[str, List[Dependency]] = {}
        for dep in self.dependencies.values():
            if dep.required:
                incoming_required_by_target.setdefault(dep.target_id, []).append(dep)
        
        ready_claims = []
        incomplete_claims = []
        total_missing_dependencies = 0
        total_satisfaction_ratio = 0.0
        recommended_next_gaps = []
        total_required_dependencies = 0
        total_satisfied_required_dependencies = 0
        underspecified_claims = 0
        weak_claim_gap_count = 0
        weak_modality_gap_count = 0
        structured_required_dependencies = 0
        structured_satisfied_dependencies = 0
        deterministic_gap_targets = 0
        deterministic_gap_targets_satisfied = 0
        core_structured_gap_count = 0
        core_structured_single_turn_closable = 0

        for claim in claims:
            required_deps = incoming_required_by_target.get(claim.id, [])
            satisfied_count = 0
            missing_dependencies = []
            for dep in required_deps:
                source_node = nodes_by_id.get(dep.source_id)
                if source_node and source_node.satisfied:
                    satisfied_count += 1
                else:
                    missing_dependencies.append(
                        {
                            'dependency_id': dep.id,
                            'source_node_id': dep.source_id,
                            'source_name': source_node.name if source_node else 'Unknown',
                            'dependency_type': dep.dependency_type.value,
                        }
                    )
            claim_type = str((claim.attributes or {}).get('claim_type') or '').strip().lower()
            total_required_for_claim = len(required_deps)
            claim_satisfaction_ratio = (
                satisfied_count / total_required_for_claim if total_required_for_claim > 0 else 1.0
            )
            claim_is_satisfied = claim_satisfaction_ratio >= 1.0
            claim_is_underspecified = total_required_for_claim == 0
            if claim_is_underspecified:
                underspecified_claims += 1

            total_required_dependencies += total_required_for_claim
            total_satisfied_required_dependencies += satisfied_count

            ranked_missing_dependencies = []
            claim_structured_required_count = 0
            claim_structured_satisfied_count = 0
            claim_deterministic_target_count = 0
            claim_deterministic_target_satisfied_count = 0
            missing_by_source_id = {str(dep.get("source_node_id") or "") for dep in missing_dependencies}
            for dep in required_deps:
                source_node = nodes_by_id.get(dep.source_id)
                source_attrs = source_node.attributes if source_node and isinstance(source_node.attributes, dict) else {}
                source_node_type = source_node.node_type.value if source_node else "unknown"
                requirement_key = str(source_attrs.get("requirement_key") or "").strip().lower()
                expected_modality = str(source_attrs.get("expected_evidence_modality") or "").strip().lower()
                has_structured_target = bool(
                    requirement_key
                    or expected_modality
                    or source_node_type in {"legal_element", "requirement", "fact", "evidence"}
                )
                if has_structured_target:
                    claim_structured_required_count += 1
                inferred_gap_type = _infer_gap_type(
                    claim_type=claim_type,
                    source_name=source_node.name if source_node else "",
                    source_description=source_node.description if source_node else "",
                    source_attrs=source_attrs,
                    requirement_key=requirement_key,
                    evidence_modality=expected_modality,
                )
                deterministic_key = _build_deterministic_update_key(
                    claim_id=claim.id,
                    claim_type=claim_type,
                    source_node=source_node,
                    source_attrs=source_attrs,
                    gap_type=inferred_gap_type,
                    requirement_key=requirement_key,
                )
                has_deterministic_key = bool(deterministic_key)
                if has_deterministic_key:
                    claim_deterministic_target_count += 1
                if dep.source_id not in missing_by_source_id:
                    if has_structured_target:
                        claim_structured_satisfied_count += 1
                    if has_deterministic_key:
                        claim_deterministic_target_satisfied_count += 1

            structured_required_dependencies += claim_structured_required_count
            structured_satisfied_dependencies += claim_structured_satisfied_count
            deterministic_gap_targets += claim_deterministic_target_count
            deterministic_gap_targets_satisfied += claim_deterministic_target_satisfied_count

            for dep in missing_dependencies:
                source_node = self.get_node(str(dep.get('source_node_id') or ''))
                source_attrs = source_node.attributes if source_node and isinstance(source_node.attributes, dict) else {}
                blocking = bool(source_attrs.get('blocking', source_node.node_type in {NodeType.REQUIREMENT, NodeType.LEGAL_ELEMENT} if source_node else False))
                source_node_type = source_node.node_type.value if source_node else 'unknown'
                requirement_key = str(source_attrs.get('requirement_key') or '').strip().lower()
                evidence_modality = str(source_attrs.get('expected_evidence_modality') or '').strip().lower()
                gap_type = _infer_gap_type(
                    claim_type=claim_type,
                    source_name=source_node.name if source_node else "",
                    source_description=source_node.description if source_node else "",
                    source_attrs=source_attrs,
                    requirement_key=requirement_key,
                    evidence_modality=evidence_modality,
                )
                deterministic_update_key = _build_deterministic_update_key(
                    claim_id=claim.id,
                    claim_type=claim_type,
                    source_node=source_node,
                    source_attrs=source_attrs,
                    gap_type=gap_type,
                    requirement_key=requirement_key,
                )
                gap_id = deterministic_update_key or str(source_attrs.get('gap_key') or f"{claim.id}:{dep.get('source_node_id')}")
                structured_gap = bool(
                    requirement_key
                    or evidence_modality
                    or source_node_type in {'legal_element', 'requirement', 'fact', 'evidence'}
                )
                weak_claim_focus = claim_type in _ACTOR_CRITIC_WEAK_CLAIM_TYPES
                weak_modality_focus = evidence_modality in _ACTOR_CRITIC_WEAK_EVIDENCE_MODALITIES
                source_text = " ".join(
                    [
                        source_node.name if source_node else "",
                        source_node.description if source_node else "",
                        requirement_key,
                        str(source_attrs.get("question_hint") or ""),
                    ]
                )
                contains_date = _contains_date_token(source_text)
                contains_name = _contains_name(source_text)
                extraction_targets = _extraction_targets_for_gap(gap_type)
                answer_contract = _build_answer_contract(
                    gap_type=gap_type,
                    deterministic_update_key=deterministic_update_key,
                    requirement_key=requirement_key,
                    source_attrs=source_attrs,
                )
                missing_required_fields = list(answer_contract.get("missing_required_fields") or [])
                required_fields = list(answer_contract.get("required_fields") or [])
                completion_ratio = (
                    1.0 - (len(missing_required_fields) / len(required_fields))
                    if required_fields
                    else 1.0
                )
                actor_score = 0.0
                if blocking:
                    actor_score += 4.0
                if weak_claim_focus:
                    actor_score += 2.5
                if weak_modality_focus:
                    actor_score += 2.0
                actor_score += max(0.0, 2.5 - (0.2 * _gap_type_rank(gap_type)))
                if structured_gap:
                    actor_score += 1.5
                if contains_date:
                    actor_score += 1.1
                if contains_name:
                    actor_score += 0.9
                actor_score += _critical_gap_signal(gap_type) * 1.8
                critic_score = 0.0
                if structured_gap:
                    critic_score += 3.5
                if deterministic_update_key:
                    critic_score += 3.0
                if source_node_type in {'legal_element', 'requirement'}:
                    critic_score += 1.8
                if evidence_modality in _ACTOR_CRITIC_WEAK_EVIDENCE_MODALITIES:
                    critic_score += 1.2
                if dep.get('dependency_type') == DependencyType.REQUIRES.value:
                    critic_score += 0.8
                if completion_ratio >= 0.5:
                    critic_score += 1.2
                if answer_contract.get("single_turn_closable"):
                    critic_score += 1.0
                combined_priority = (actor_score * 0.55) + (critic_score * 0.45)
                concretely_answerable = not any(
                    _is_unspecified_value(source_attrs.get(field_name))
                    for field_name in ("question_hint", "placeholder", "expected_value")
                )
                if weak_claim_focus:
                    weak_claim_gap_count += 1
                if weak_modality_focus:
                    weak_modality_gap_count += 1
                if answer_contract.get("core_structured_gap"):
                    core_structured_gap_count += 1
                    if answer_contract.get("single_turn_closable"):
                        core_structured_single_turn_closable += 1
                ranked_missing_dependencies.append(
                    {
                        **dep,
                        'gap_id': gap_id,
                        'claim_type': claim_type,
                        'source_node_type': source_node_type,
                        'source_description': source_node.description if source_node else '',
                        'requirement_key': requirement_key,
                        'gap_type': gap_type,
                        'evidence_modality': evidence_modality,
                        'structured_gap': structured_gap,
                        'deterministic_update_key': deterministic_update_key,
                        'weak_claim_focus': weak_claim_focus,
                        'weak_modality_focus': weak_modality_focus,
                        'contains_date_signal': contains_date,
                        'contains_name_signal': contains_name,
                        'extraction_targets': extraction_targets,
                        'required_fields': required_fields,
                        'missing_required_fields': missing_required_fields,
                        'field_completion_ratio': round(max(0.0, min(1.0, completion_ratio)), 4),
                        'answer_contract': answer_contract,
                        'concretely_answerable': concretely_answerable,
                        'core_structured_gap': bool(answer_contract.get("core_structured_gap")),
                        'actor_score': round(actor_score, 4),
                        'critic_score': round(critic_score, 4),
                        'priority_score': round(combined_priority, 4),
                        'blocking': blocking,
                    }
                )

            ranked_missing_dependencies.sort(
                key=lambda item: (
                    0 if item.get('blocking') else 1,
                    0 if item.get('weak_claim_focus') else 1,
                    0 if item.get('weak_modality_focus') else 1,
                    0 if item.get('core_structured_gap') else 1,
                    0 if item.get('structured_gap') else 1,
                    _gap_type_rank(str(item.get('gap_type') or '').strip().lower()),
                    0 if item.get('answer_contract', {}).get('single_field_closable') else 1,
                    0 if item.get('answer_contract', {}).get('single_turn_closable') else 1,
                    -float(item.get('field_completion_ratio') or 0.0),
                    0 if item.get('concretely_answerable') else 1,
                    -float(item.get('priority_score') or 0.0),
                    0 if str(item.get('source_node_type') or '') in {'legal_element', 'requirement'} else 1,
                    str(item.get('source_name') or '').lower(),
                )
            )

            total_missing_dependencies += len(ranked_missing_dependencies)
            total_satisfaction_ratio += claim_satisfaction_ratio
            next_gap = ranked_missing_dependencies[0] if ranked_missing_dependencies else None
            if claim_is_satisfied:
                ready_claims.append({
                    'claim_id': claim.id,
                    'claim_name': claim.name,
                    'confidence': claim.confidence,
                    'claim_type': claim_type,
                    'dependency_satisfaction': 1.0,
                    'underspecified': claim_is_underspecified,
                    'required_dependency_count': total_required_for_claim,
                    'structured_required_count': claim_structured_required_count,
                    'structured_satisfied_count': claim_structured_satisfied_count,
                    'deterministic_target_count': claim_deterministic_target_count,
                    'deterministic_target_satisfied_count': claim_deterministic_target_satisfied_count,
                })
            else:
                incomplete_claims.append({
                    'claim_id': claim.id,
                    'claim_name': claim.name,
                    'claim_type': claim_type,
                    'satisfaction_ratio': claim_satisfaction_ratio,
                    'dependency_satisfaction': claim_satisfaction_ratio,
                    'missing_count': len(ranked_missing_dependencies),
                    'missing_dependencies': ranked_missing_dependencies,
                    'next_required_gap': next_gap,
                    'underspecified': claim_is_underspecified,
                    'required_dependency_count': total_required_for_claim,
                    'structured_required_count': claim_structured_required_count,
                    'structured_satisfied_count': claim_structured_satisfied_count,
                    'deterministic_target_count': claim_deterministic_target_count,
                    'deterministic_target_satisfied_count': claim_deterministic_target_satisfied_count,
                })
                if next_gap:
                    recommended_next_gaps.append(
                        {
                            'claim_id': claim.id,
                            'claim_name': claim.name,
                            'claim_type': claim_type,
                            **next_gap,
                        }
                    )

        claim_level_satisfaction = (
            total_satisfaction_ratio / len(claims) if claims else 0.0
        )

        dependency_coverage = (
            total_satisfied_required_dependencies / total_required_dependencies
            if total_required_dependencies > 0
            else (1.0 if claims else 0.0)
        )
        overall_dependency_satisfaction = (
            claim_level_satisfaction * 0.45 + dependency_coverage * 0.55
        ) if claims else 0.0
        structured_dependency_coverage = (
            structured_satisfied_dependencies / structured_required_dependencies
            if structured_required_dependencies > 0
            else dependency_coverage
        )
        deterministic_gap_closure = (
            deterministic_gap_targets_satisfied / deterministic_gap_targets
            if deterministic_gap_targets > 0
            else dependency_coverage
        )
        graph_population_score = (
            (
                ((len(claims) - underspecified_claims) / len(claims)) * 0.55
                + structured_dependency_coverage * 0.45
            )
            if claims
            else 0.0
        )
        graph_analysis_confidence = max(
            0.0,
            min(
                1.0,
                dependency_coverage * 0.35
                + structured_dependency_coverage * 0.30
                + deterministic_gap_closure * 0.20
                + graph_population_score * 0.15,
            ),
        )
        avg_gaps = total_missing_dependencies / len(claims) if claims else 0.0

        readiness_history = self.metadata.setdefault('readiness_history', {})
        previous_avg_gaps = float(readiness_history.get('avg_gaps', avg_gaps))
        gap_delta_per_iter = avg_gaps - previous_avg_gaps
        previous_stall_count = int(readiness_history.get('gap_stall_sessions', 0))
        if avg_gaps > 0.0 and gap_delta_per_iter >= -1e-9:
            gap_stall_sessions = previous_stall_count + 1
        else:
            gap_stall_sessions = 0
        readiness_history.update(
            {
                'avg_gaps': avg_gaps,
                'gap_stall_sessions': gap_stall_sessions,
                'updated_at': _utc_now_isoformat(),
            }
        )
        self.metadata['readiness_history'] = readiness_history

        recommended_actions = []
        if not claims:
            recommended_actions.append(
                "Restore a stable adversarial session flow before tuning graph extraction and dependency tracking."
            )
        if total_required_dependencies == 0 and claims:
            recommended_actions.append(
                "No required dependencies are linked to claims; populate requirement/evidence edges before denoising."
            )
        if gap_stall_sessions >= 2 and avg_gaps > 0.0:
            recommended_actions.append(
                "Gap count is not improving across iterations; prioritize blocker-focused follow-ups in graph_analysis."
            )
        if weak_claim_gap_count > 0:
            recommended_actions.append(
                "Prioritize deterministic requirement closure for housing_discrimination and hacc_research_engine gaps."
            )
        if weak_modality_gap_count > 0:
            recommended_actions.append(
                "Request policy_document and file_evidence fields with exact document name, date, and issuing/source actor."
            )
        if deterministic_gap_closure < 0.6 and total_required_dependencies > 0:
            recommended_actions.append(
                "Map each follow-up question to a deterministic_update_key so each answer closes a concrete graph requirement."
            )
        if core_structured_gap_count > 0:
            recommended_actions.append(
                "Close exact date, staff identity/title, hearing timing, response date, and causation sequencing gaps before broader narrative prompts."
            )

        recommended_next_gaps.sort(
            key=lambda item: (
                0 if item.get('blocking') else 1,
                0 if item.get('weak_claim_focus') else 1,
                0 if item.get('weak_modality_focus') else 1,
                0 if item.get('core_structured_gap') else 1,
                0 if item.get('structured_gap') else 1,
                _gap_type_rank(str(item.get('gap_type') or '').strip().lower()),
                0 if item.get('answer_contract', {}).get('single_field_closable') else 1,
                0 if item.get('answer_contract', {}).get('single_turn_closable') else 1,
                -float(item.get('field_completion_ratio') or 0.0),
                -float(item.get('priority_score') or 0.0),
                str(item.get('claim_name') or '').lower(),
                str(item.get('source_name') or '').lower(),
            )
        )
        
        return {
            'total_claims': len(claims),
            'ready_claims': len(ready_claims),
            'incomplete_claims': len(incomplete_claims),
            'ready_claim_details': ready_claims,
            'incomplete_claim_details': incomplete_claims,
            'overall_readiness': overall_dependency_satisfaction,
            'overall_dependency_satisfaction': overall_dependency_satisfaction,
            'dependency_satisfaction': overall_dependency_satisfaction,
            'claim_level_dependency_satisfaction': claim_level_satisfaction,
            'dependency_coverage': dependency_coverage,
            'structured_dependency_coverage': structured_dependency_coverage,
            'deterministic_gap_closure': deterministic_gap_closure,
            'graph_population_score': graph_population_score,
            'graph_analysis_confidence': graph_analysis_confidence,
            'total_missing_dependencies': total_missing_dependencies,
            'avg_gaps': avg_gaps,
            'gap_delta_per_iter': gap_delta_per_iter,
            'gap_stall_sessions': gap_stall_sessions,
            'underspecified_claims': underspecified_claims,
            'weak_claim_gap_count': weak_claim_gap_count,
            'weak_modality_gap_count': weak_modality_gap_count,
            'core_structured_gap_count': core_structured_gap_count,
            'core_structured_single_turn_closable': core_structured_single_turn_closable,
            'recommended_actions': recommended_actions,
            'recommended_next_gaps': recommended_next_gaps,
            'actor_critic': {
                'optimizer': 'actor_critic',
                'priority': _ACTOR_CRITIC_PRIORITY,
                'phase_focus_order': list(_ACTOR_CRITIC_PHASE_FOCUS_ORDER),
                'focus_metrics': dict(_ACTOR_CRITIC_FOCUS_METRICS),
                'graph_analysis': {
                    'dependency_coverage': dependency_coverage,
                    'structured_dependency_coverage': structured_dependency_coverage,
                    'deterministic_gap_closure': deterministic_gap_closure,
                    'graph_population_score': graph_population_score,
                    'graph_analysis_confidence': graph_analysis_confidence,
                    'avg_gaps': avg_gaps,
                    'gap_delta_per_iter': gap_delta_per_iter,
                    'gap_stall_sessions': gap_stall_sessions,
                    'weak_claim_types': sorted(_ACTOR_CRITIC_WEAK_CLAIM_TYPES),
                    'weak_evidence_modalities': sorted(_ACTOR_CRITIC_WEAK_EVIDENCE_MODALITIES),
                    'weak_claim_gap_count': weak_claim_gap_count,
                    'weak_modality_gap_count': weak_modality_gap_count,
                    'core_structured_gap_count': core_structured_gap_count,
                    'core_structured_single_turn_closable': core_structured_single_turn_closable,
                    'recommended_actions': recommended_actions,
                },
            },
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

    def get_blocker_follow_up_issues(self) -> List[Dict[str, Any]]:
        """Return follow-up blocker issues for intake questioning and patch routing."""
        issues: List[Dict[str, Any]] = []
        node_text_by_id = {
            node_id: f"{node.name} {node.description}".strip().lower()
            for node_id, node in self.nodes.items()
        }
        node_rich_text_by_id = {
            node_id: self._node_rich_text(node)
            for node_id, node in self.nodes.items()
        }

        # Hearing/appeal timing blockers: hearing references without explicit temporal edges.
        hearing_node_ids = [
            node_id
            for node_id, text_value in node_text_by_id.items()
            if any(token in text_value for token in ("hearing", "appeal", "grievance"))
        ]
        for node_id in hearing_node_ids:
            temporal_links = [
                dep for dep in self.get_dependencies_for_node(node_id)
                if dep.dependency_type in {DependencyType.BEFORE, DependencyType.SAME_TIME, DependencyType.OVERLAPS}
            ]
            if temporal_links:
                continue
            node = self.get_node(node_id)
            issues.append(
                {
                    "issue_id": f"blocker_hearing_timing_{node_id}",
                    "issue_type": "missing_hearing_timing",
                    "severity": "blocking",
                    "question_type": "timeline",
                    "recommended_resolution_lane": "request_document",
                    "workflow_phase": "graph_analysis",
                    "workflow_phase_rank": 0,
                    "node_id": node_id,
                    "node_name": node.name if node else node_id,
                    "summary": "Hearing or appeal activity lacks dated sequencing in dependency graph.",
                    "extraction_targets": ["exact_dates", "event_order", "actor_name", "document_owner"],
                    "patchability_markers": ["chronology_patch_anchor", "notice_chain_patch_anchor"],
                    "suggested_question": (
                        "Please walk me through the hearing or appeal timeline with exact dates, who handled each step, and any notice, email, or letter tied to each response."
                    ),
                }
            )

        # Chronology closure blockers: timeline-critical events without exact dates or response timing.
        chronology_focus_tokens = (
            "hearing",
            "appeal",
            "grievance",
            "notice",
            "response",
            "reply",
            "decision",
            "protected activity",
            "complained",
            "reported",
            "adverse action",
            "terminated",
            "disciplined",
            "evicted",
            "suspended",
        )
        chronology_focus_node_ids = [
            node_id
            for node_id, text_value in node_text_by_id.items()
            if any(token in text_value for token in chronology_focus_tokens)
        ]
        chronology_missing_date_nodes = [
            self.get_node(node_id)
            for node_id in chronology_focus_node_ids
            if not self._contains_date_anchor(node_rich_text_by_id.get(node_id, ""))
        ]
        chronology_missing_date_nodes = [node for node in chronology_missing_date_nodes if node is not None]
        if chronology_missing_date_nodes:
            sample_labels = ", ".join(node.name for node in chronology_missing_date_nodes[:3])
            issues.append(
                {
                    "issue_id": "blocker_chronology_exact_dates_missing",
                    "issue_type": "chronology_exact_dates_missing",
                    "severity": "blocking",
                    "question_type": "timeline",
                    "recommended_resolution_lane": "request_document",
                    "workflow_phase": "graph_analysis",
                    "workflow_phase_rank": 0,
                    "summary": "Chronology-critical events are missing exact date anchors and response timing closure.",
                    "node_ids": [node.id for node in chronology_missing_date_nodes],
                    "node_names": [node.name for node in chronology_missing_date_nodes],
                    "extraction_targets": [
                        "exact_dates",
                        "response_timing",
                        "event_order",
                        "actor_name",
                        "decision_maker",
                        "document_date",
                    ],
                    "patchability_markers": [
                        "chronology_patch_anchor",
                        "notice_chain_patch_anchor",
                        "decision_actor_patch_anchor",
                    ],
                    "suggested_question": (
                        f"For chronology items such as {sample_labels}, what exact date did each event occur, "
                        "who handled each step, and how long after each event the next response or decision occurred?"
                    ),
                }
            )

        chronology_with_dates = [
            node_id
            for node_id in chronology_focus_node_ids
            if self._contains_date_anchor(node_rich_text_by_id.get(node_id, ""))
        ]
        has_chronology_sequence = any(
            dep.dependency_type in {DependencyType.BEFORE, DependencyType.SAME_TIME, DependencyType.OVERLAPS}
            and dep.source_id in chronology_with_dates
            and dep.target_id in chronology_with_dates
            for dep in self.dependencies.values()
        )
        if len(chronology_with_dates) >= 2 and not has_chronology_sequence:
            issues.append(
                {
                    "issue_id": "blocker_chronology_sequence_missing",
                    "issue_type": "chronology_sequence_missing",
                    "severity": "blocking",
                    "question_type": "timeline",
                    "recommended_resolution_lane": "request_document",
                    "workflow_phase": "graph_analysis",
                    "workflow_phase_rank": 0,
                    "summary": "Dated chronology events exist but are not connected into a clear sequence in the graph.",
                    "node_ids": list(chronology_with_dates),
                    "extraction_targets": ["exact_dates", "event_order", "response_timing", "causation_link"],
                    "patchability_markers": ["chronology_patch_anchor", "causation_patch_anchor"],
                    "suggested_question": (
                        "Using exact dates, what happened first, second, and third, and what was the response timing between each step?"
                    ),
                }
            )

        # Staff identity blockers: staff-role references without a concrete named actor node.
        staff_like_nodes = [
            node for node in self.nodes.values()
            if any(token in f"{node.name} {node.description}".lower() for token in ("manager", "supervisor", "hr", "landlord", "officer", "staff"))
        ]
        has_named_actor = any(
            node.node_type in {NodeType.FACT, NodeType.EVIDENCE, NodeType.REQUIREMENT, NodeType.CLAIM}
            and bool(_NAME_PATTERN.search(node.name))
            for node in self.nodes.values()
        )
        if staff_like_nodes and not has_named_actor:
            issues.append(
                {
                    "issue_id": "blocker_staff_identity_missing",
                    "issue_type": "missing_staff_identity",
                    "severity": "blocking",
                    "question_type": "responsible_party",
                    "recommended_resolution_lane": "clarify_with_complainant",
                    "workflow_phase": "graph_analysis",
                    "workflow_phase_rank": 0,
                    "summary": "Staff-role references exist but no named actor is linked in the dependency graph.",
                    "extraction_targets": ["actor_name", "actor_role", "organization_unit"],
                    "patchability_markers": ["actor_link_patch_anchor"],
                    "suggested_question": "Who specifically took each action (full name and title), what team or office they were in, and how they were connected to your case?",
                }
            )

        # Decision detail blockers: adverse action mentions without precision on decision-maker and action specifics.
        general_adverse_ids = [
            node_id
            for node_id, text_value in node_text_by_id.items()
            if any(
                token in text_value
                for token in (
                    "fired",
                    "terminated",
                    "demoted",
                    "disciplined",
                    "suspended",
                    "adverse action",
                    "evicted",
                    "reduced hours",
                    "cut hours",
                    "denied",
                )
            )
        ]
        adverse_nodes_missing_actor_precision = [
            node_id
            for node_id in general_adverse_ids
            if not (
                _NAME_PATTERN.search(node_rich_text_by_id.get(node_id, ""))
                or any(
                    token in node_text_by_id.get(node_id, "")
                    for token in ("manager", "supervisor", "director", "hr", "officer", "landlord", "administrator")
                )
            )
        ]
        if adverse_nodes_missing_actor_precision:
            issues.append(
                {
                    "issue_id": "blocker_adverse_action_decision_precision_missing",
                    "issue_type": "adverse_action_decision_precision_missing",
                    "severity": "blocking",
                    "question_type": "responsible_party",
                    "recommended_resolution_lane": "clarify_with_complainant",
                    "workflow_phase": "graph_analysis",
                    "workflow_phase_rank": 0,
                    "summary": "Adverse action facts lack specific decision-maker identity, role, and action detail precision.",
                    "node_ids": list(adverse_nodes_missing_actor_precision),
                    "extraction_targets": [
                        "decision_maker",
                        "actor_name",
                        "actor_role",
                        "adverse_action",
                        "exact_dates",
                        "organization_unit",
                    ],
                    "patchability_markers": [
                        "actor_link_patch_anchor",
                        "decision_actor_patch_anchor",
                        "chronology_patch_anchor",
                    ],
                    "suggested_question": (
                        "For each adverse action, who made or approved it (full name, title, and office), "
                        "what exactly was decided or imposed, and on what exact date?"
                    ),
                }
            )

        # Documentary precision blockers: records exist but lack sender/recipient/subject/ID anchors.
        document_like_nodes = [
            node_id
            for node_id, text_value in node_text_by_id.items()
            if any(token in text_value for token in ("notice", "letter", "email", "message", "text", "memo", "record"))
        ]
        has_document_precision = any(
            self._contains_document_precision_marker(node_rich_text_by_id.get(node_id, ""))
            for node_id in document_like_nodes
        )
        if document_like_nodes and not has_document_precision:
            issues.append(
                {
                    "issue_id": "blocker_document_artifact_precision_missing",
                    "issue_type": "document_artifact_precision_missing",
                    "severity": "blocking",
                    "question_type": "evidence",
                    "recommended_resolution_lane": "request_document",
                    "workflow_phase": "document_generation",
                    "workflow_phase_rank": 1,
                    "summary": "Document artifacts are referenced but missing citation-grade identifiers for patch-ready drafting.",
                    "node_ids": list(document_like_nodes),
                    "extraction_targets": [
                        "document_type",
                        "document_date",
                        "document_owner",
                        "document_sender",
                        "document_recipient",
                        "document_subject",
                        "document_identifier",
                    ],
                    "patchability_markers": [
                        "support_patch_anchor",
                        "notice_chain_patch_anchor",
                        "decision_actor_patch_anchor",
                    ],
                    "suggested_question": (
                        "For each relevant notice/email/message, what is the exact date, sender, recipient, subject line, "
                        "and any case number or document ID we should cite?"
                    ),
                }
            )

        # Retaliation sequencing blockers: protected activity and adverse action nodes without BEFORE ordering.
        retaliation_claim_nodes = [
            node for node in self.get_nodes_by_type(NodeType.CLAIM)
            if (
                "retaliat" in node.name.lower()
                or str((node.attributes or {}).get("claim_type") or "").strip().lower() == "retaliation"
            )
        ]
        if retaliation_claim_nodes:
            protected_ids = [
                node_id for node_id, text_value in node_text_by_id.items()
                if any(token in text_value for token in ("protected activity", "complained", "reported", "grievance", "accommodation"))
            ]
            adverse_ids = [
                node_id for node_id, text_value in node_text_by_id.items()
                if any(token in text_value for token in ("fired", "terminated", "demoted", "disciplined", "suspended", "adverse action", "evicted", "reduced hours", "cut hours"))
            ]
            has_ordering = any(
                dep.dependency_type == DependencyType.BEFORE
                and dep.source_id in protected_ids
                and dep.target_id in adverse_ids
                for dep in self.dependencies.values()
            )
            if protected_ids and adverse_ids and not has_ordering:
                issues.append(
                    {
                        "issue_id": "blocker_retaliation_sequence_missing",
                        "issue_type": "retaliation_missing_sequence",
                        "severity": "blocking",
                        "question_type": "timeline",
                        "recommended_resolution_lane": "request_document",
                        "workflow_phase": "graph_analysis",
                        "workflow_phase_rank": 0,
                        "summary": "Retaliation theory has protected activity and adverse action nodes but lacks temporal ordering.",
                        "extraction_targets": ["protected_activity", "adverse_action", "exact_dates", "actor_name", "causation_link"],
                        "patchability_markers": ["chronology_patch_anchor", "causation_patch_anchor"],
                        "suggested_question": (
                            "What was your protected activity, on what exact date did it occur, who knew about it, and what adverse actions followed afterward with dates, actor names, and any supporting notice or message?"
                        ),
                    }
                )

            # Retaliation issues also need explicit decision-maker identity and rationale.
            decision_terms = ("decid", "approved", "denied", "terminated", "disciplined", "recommended", "ordered")
            role_terms = ("manager", "supervisor", "director", "hr", "officer", "landlord", "administrator", "staff")
            has_decision_maker_signal = any(
                any(term in text_value for term in decision_terms)
                and (bool(_NAME_PATTERN.search(node_rich_text_by_id.get(node_id, ""))) or any(role in text_value for role in role_terms))
                for node_id, text_value in node_text_by_id.items()
            )
            if adverse_ids and not has_decision_maker_signal:
                issues.append(
                    {
                        "issue_id": "blocker_retaliation_decision_maker_missing",
                        "issue_type": "retaliation_missing_decision_maker",
                        "severity": "blocking",
                        "question_type": "responsible_party",
                        "recommended_resolution_lane": "clarify_with_complainant",
                        "workflow_phase": "graph_analysis",
                        "workflow_phase_rank": 0,
                        "summary": "Retaliation adverse-action path lacks a named decision-maker identity and role.",
                        "extraction_targets": ["decision_maker", "actor_name", "actor_role", "organization_unit", "exact_dates"],
                        "patchability_markers": ["actor_link_patch_anchor", "decision_actor_patch_anchor", "chronology_patch_anchor"],
                        "suggested_question": (
                            "Who made or approved each adverse decision (full name, title, and office), on what exact date each decision was made, and who communicated it to you?"
                        ),
                    }
                )

            # Improve document-generation coverage for causation corroboration.
            has_causation_documents = any(
                any(token in text_value for token in ("notice", "letter", "email", "message", "record", "memo"))
                and any(token in text_value for token in ("protected activity", "complained", "reported", "adverse action", "terminated", "disciplined"))
                for text_value in node_text_by_id.values()
            )
            if (adverse_ids or protected_ids) and not has_causation_documents:
                issues.append(
                    {
                        "issue_id": "blocker_retaliation_causation_documents_missing",
                        "issue_type": "retaliation_missing_causation_documents",
                        "severity": "blocking",
                        "question_type": "evidence",
                        "recommended_resolution_lane": "request_document",
                        "workflow_phase": "document_generation",
                        "workflow_phase_rank": 1,
                        "summary": "Causation path lacks anchored records linking protected activity knowledge to adverse action.",
                        "extraction_targets": ["document_type", "document_date", "document_owner", "decision_maker", "causation_link"],
                        "patchability_markers": ["support_patch_anchor", "notice_chain_patch_anchor", "causation_patch_anchor"],
                        "suggested_question": (
                            "Which notice, email, text, meeting record, or memo shows decision-makers knew about your protected activity before the adverse action, and what date and sender/recipient details are on each record?"
                        ),
                    }
                )

        # Convert placeholder facts into concrete, draft-ready anchors with phase-ordered follow-up.
        placeholder_nodes = self._nodes_with_confirmation_placeholders(node_rich_text_by_id)
        if placeholder_nodes:
            placeholder_labels = ", ".join(node.name for node in placeholder_nodes[:3])
            issues.append(
                {
                    "issue_id": "blocker_confirmation_placeholders_specificity",
                    "issue_type": "confirmation_placeholders_needing_specific_facts",
                    "severity": "blocking",
                    "question_type": "timeline",
                    "recommended_resolution_lane": "clarify_with_complainant",
                    "workflow_phase": "graph_analysis",
                    "workflow_phase_rank": 0,
                    "summary": "One or more graph facts still contain confirmation placeholders instead of concrete anchors.",
                    "placeholder_node_ids": [node.id for node in placeholder_nodes],
                    "placeholder_node_names": [node.name for node in placeholder_nodes],
                    "extraction_targets": ["exact_dates", "actor_name", "actor_role", "decision_maker", "event_order"],
                    "patchability_markers": ["chronology_patch_anchor", "actor_link_patch_anchor", "decision_actor_patch_anchor"],
                    "suggested_question": (
                        f"For each placeholder item ({placeholder_labels}), what are the exact dates, who took each action (full name and title), and what happened immediately before and after?"
                    ),
                }
            )
            issues.append(
                {
                    "issue_id": "blocker_confirmation_placeholders_document_anchor",
                    "issue_type": "confirmation_placeholders_missing_document_anchor",
                    "severity": "blocking",
                    "question_type": "evidence",
                    "recommended_resolution_lane": "request_document",
                    "workflow_phase": "document_generation",
                    "workflow_phase_rank": 2,
                    "summary": "Placeholder facts are not anchored to specific records for patch-ready drafting.",
                    "placeholder_node_ids": [node.id for node in placeholder_nodes],
                    "placeholder_node_names": [node.name for node in placeholder_nodes],
                    "extraction_targets": ["document_type", "document_date", "document_owner", "actor_name"],
                    "patchability_markers": ["support_patch_anchor", "notice_chain_patch_anchor"],
                    "suggested_question": (
                        "What specific documents, notices, emails, or messages confirm each placeholder fact, and what date, sender, recipient, and subject line should we cite for each one?"
                    ),
                }
            )
            issues.append(
                {
                    "issue_id": "blocker_confirmation_placeholders_intake_closure",
                    "issue_type": "confirmation_placeholders_intake_closure",
                    "severity": "important",
                    "question_type": "clarification",
                    "recommended_resolution_lane": "clarify_with_complainant",
                    "workflow_phase": "intake_questioning",
                    "workflow_phase_rank": 1,
                    "summary": "Intake record still has unresolved placeholders requiring a best-estimate fallback for closure.",
                    "placeholder_node_ids": [node.id for node in placeholder_nodes],
                    "placeholder_node_names": [node.name for node in placeholder_nodes],
                    "extraction_targets": ["date_estimate", "confidence_level", "verification_source", "actor_name"],
                    "patchability_markers": ["intake_follow_up_patch_anchor"],
                    "suggested_question": (
                        "If any exact detail is still uncertain, give your best date range, who can verify it, and where that verification can be found so we can close the intake gap."
                    ),
                }
            )

        return self._optimize_blocker_issues_for_actor_critic(issues)

    def _node_rich_text(self, node: DependencyNode) -> str:
        """Build searchable text including node attributes for blocker diagnostics."""
        values = [str(node.name or ""), str(node.description or "")]
        attrs = node.attributes if isinstance(node.attributes, dict) else {}
        for value in attrs.values():
            if isinstance(value, (str, int, float, bool)):
                values.append(str(value))
            elif isinstance(value, list):
                values.extend(str(item) for item in value if isinstance(item, (str, int, float, bool)))
            elif isinstance(value, dict):
                values.extend(
                    str(item)
                    for item in value.values()
                    if isinstance(item, (str, int, float, bool))
                )
        return " ".join(item for item in values if item).strip()

    def _nodes_with_confirmation_placeholders(
        self,
        node_rich_text_by_id: Dict[str, str],
    ) -> List[DependencyNode]:
        """Identify nodes that still contain 'needs confirmation'-style placeholders."""
        placeholder_nodes: List[DependencyNode] = []
        for node_id, text_value in node_rich_text_by_id.items():
            if not text_value:
                continue
            if _CONFIRMATION_PLACEHOLDER_PATTERN.search(text_value):
                node = self.get_node(node_id)
                if node is not None:
                    placeholder_nodes.append(node)
        return placeholder_nodes

    def _contains_date_anchor(self, text_value: str) -> bool:
        """Return whether text includes an explicit or parseable date anchor."""
        if not text_value:
            return False
        return bool(_DATE_TOKEN_PATTERN.search(text_value))

    def _contains_document_precision_marker(self, text_value: str) -> bool:
        """Return whether text includes document-level precision markers."""
        if not text_value:
            return False
        lowered = text_value.lower()
        precision_tokens = (
            "subject line",
            "sender",
            "recipient",
            "from:",
            "to:",
            "reference number",
            "case number",
            "tracking number",
            "message id",
            "document id",
            "attachment",
        )
        return any(token in lowered for token in precision_tokens)

    def _phase_focus_rank_for_actor_critic(self, workflow_phase: str) -> int:
        phase = str(workflow_phase or "").strip().lower()
        if phase in _ACTOR_CRITIC_PHASE_FOCUS_ORDER:
            return _ACTOR_CRITIC_PHASE_FOCUS_ORDER.index(phase)
        return len(_ACTOR_CRITIC_PHASE_FOCUS_ORDER)

    def _dedupe_preserve_order(self, values: List[str]) -> List[str]:
        deduped: List[str] = []
        seen = set()
        for value in values:
            token = str(value or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            deduped.append(token)
        return deduped

    def _optimize_issue_question_text(
        self,
        *,
        question_text: str,
        question_type: str,
        extraction_targets: List[str],
    ) -> str:
        base = str(question_text or "").strip()
        qtype = str(question_type or "").strip().lower()
        targets = [str(item or "").strip().lower() for item in extraction_targets if str(item or "").strip()]
        lower = base.lower()

        empathy_prefix = "To make sure I understand, "
        if qtype in {"timeline", "responsible_party"}:
            empathy_prefix = "I know this may be stressful, and this helps keep your record accurate: "
        elif qtype in {"evidence"}:
            empathy_prefix = "So we can support your claim clearly, "

        if not lower.startswith((
            "to make sure i understand",
            "i know this may be stressful",
            "so we can support your claim",
        )):
            if base:
                first = base[0].lower() + base[1:] if len(base) > 1 else base.lower()
            else:
                first = "can you share the missing details"
            base = f"{empathy_prefix}{first}"
            lower = base.lower()

        quality_prompts: List[str] = []
        if any(item in targets for item in {"exact_dates", "event_order"}) and not any(
            token in lower for token in ("exact date", "on what date", "what date", "when")
        ):
            quality_prompts.append("the exact date for each step")
        if "response_timing" in targets and not any(
            token in lower for token in ("response", "responded", "reply", "how long", "time between", "delay")
        ):
            quality_prompts.append("how long each response took after the prior event")
        if any(item in targets for item in {"actor_name", "actor_role", "decision_maker"}) and not any(
            token in lower for token in ("who", "full name", "title", "role")
        ):
            quality_prompts.append("who took each action (full name and title)")
        if "adverse_action" in targets and not any(
            token in lower for token in ("adverse action", "terminated", "fired", "disciplined", "evicted", "suspended", "what exactly")
        ):
            quality_prompts.append("what exact adverse action occurred at each step")
        if any(item in targets for item in {"document_type", "document_date", "document_owner"}) and not any(
            token in lower for token in ("document", "notice", "letter", "email", "record", "message")
        ):
            quality_prompts.append("which document or message supports each point")
        if any(item in targets for item in {"document_sender", "document_recipient", "document_subject", "document_identifier"}) and not any(
            token in lower for token in ("sender", "recipient", "subject", "reference", "case number", "document id")
        ):
            quality_prompts.append("the document sender, recipient, subject line, and any case/document ID")
        if "causation_link" in targets and not any(token in lower for token in ("because", "after", "before", "led to")):
            quality_prompts.append("how each step led to the next")

        if quality_prompts:
            detail_clause = " Please include " + "; ".join(self._dedupe_preserve_order(quality_prompts))
            if not base.endswith((".", "?", "!")):
                base = f"{base}."
            base = f"{base}{detail_clause}"

        cleaned = base.rstrip(" .!?")
        if not cleaned:
            cleaned = "To make sure I understand, can you share the missing details"
        optimized = f"{cleaned}?"
        if len(optimized) > 280:
            optimized = optimized[:277].rstrip(" ,;:.!?") + "?"
        return optimized

    def _optimize_blocker_issues_for_actor_critic(
        self,
        issues: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        optimized: List[Dict[str, Any]] = []
        objective_map = {
            "timeline": "establish_chronology",
            "responsible_party": "identify_responsible_party",
            "evidence": "identify_supporting_evidence",
            "clarification": "clarify_low_confidence_fact",
            "requirement": "satisfy_claim_requirement",
        }

        for issue in issues:
            if not isinstance(issue, dict):
                continue
            enriched = dict(issue)
            workflow_phase = str(enriched.get("workflow_phase") or "graph_analysis").strip().lower()
            question_type = str(enriched.get("question_type") or "timeline").strip().lower()
            severity = str(enriched.get("severity") or "").strip().lower()
            extraction_targets = self._dedupe_preserve_order([
                str(target).strip()
                for target in (enriched.get("extraction_targets") or [])
                if str(target).strip()
            ])
            patchability_markers = self._dedupe_preserve_order([
                str(marker).strip()
                for marker in (enriched.get("patchability_markers") or [])
                if str(marker).strip()
            ])

            if question_type == "timeline":
                extraction_targets = self._dedupe_preserve_order(
                    extraction_targets + ["exact_dates", "event_order", "response_timing"]
                )
                patchability_markers = self._dedupe_preserve_order(
                    patchability_markers + ["chronology_patch_anchor"]
                )
            elif question_type == "responsible_party":
                extraction_targets = self._dedupe_preserve_order(
                    extraction_targets + ["actor_name", "actor_role", "decision_maker"]
                )
                patchability_markers = self._dedupe_preserve_order(
                    patchability_markers + ["actor_link_patch_anchor", "decision_actor_patch_anchor"]
                )
            elif question_type == "evidence":
                extraction_targets = self._dedupe_preserve_order(
                    extraction_targets
                    + ["document_type", "document_date", "document_owner", "document_sender", "document_recipient"]
                )
                patchability_markers = self._dedupe_preserve_order(
                    patchability_markers + ["support_patch_anchor", "notice_chain_patch_anchor"]
                )

            enriched["workflow_phase"] = workflow_phase
            enriched["workflow_phase_rank"] = self._phase_focus_rank_for_actor_critic(workflow_phase)
            enriched["extraction_targets"] = extraction_targets
            enriched["patchability_markers"] = patchability_markers
            enriched.setdefault("question_objective", objective_map.get(question_type, "general_intake_clarification"))
            enriched.setdefault("expected_proof_gain", "high" if severity == "blocking" else "medium")
            enriched.setdefault("router_backed_question_quality", True)
            enriched.setdefault("actor_critic_priority", _ACTOR_CRITIC_PRIORITY)
            enriched.setdefault("phase_focus_order", list(_ACTOR_CRITIC_PHASE_FOCUS_ORDER))
            enriched.setdefault("actor_critic_focus_metrics", dict(_ACTOR_CRITIC_FOCUS_METRICS))
            enriched.setdefault(
                "actor_critic_quality_dimensions",
                {
                    "chronology_closure": bool(
                        any(target in {"exact_dates", "event_order", "response_timing"} for target in extraction_targets)
                    ),
                    "decision_precision": bool(
                        any(target in {"decision_maker", "actor_name", "actor_role"} for target in extraction_targets)
                    ),
                    "document_precision": bool(
                        any(
                            target in {
                                "document_type",
                                "document_date",
                                "document_owner",
                                "document_sender",
                                "document_recipient",
                                "document_subject",
                                "document_identifier",
                            }
                            for target in extraction_targets
                        )
                    ),
                    "patchability_coverage": len(patchability_markers),
                },
            )
            enriched["suggested_question"] = self._optimize_issue_question_text(
                question_text=str(enriched.get("suggested_question") or ""),
                question_type=question_type,
                extraction_targets=extraction_targets,
            )
            optimized.append(enriched)
        return optimized


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
