"""
Dependency Graph Builder

Tracks dependencies between claims, evidence, and legal requirements.
Used to ensure all elements of a claim are properly supported.
"""

import json
import logging
import re
from copy import deepcopy
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
_FACTUAL_CLARIFICATION_CLASS = "factual_clarification"
_LEGALLY_SOURCED_CLASS = "legally_sourced_requirement"
_LEGAL_SOURCE_GAP_CLASS = "legal_source_gap"
_UNRESOLVED_LEGAL_CLASS = "unresolved_legal_requirement"
_HEURISTIC_LAW_ORIGINS = {"heuristic", "heuristic_graph", "law_derived", "law-derived"}
_UNVERIFIED_REQUIREMENT_STATUSES = {"unverified_template", "unverified", "heuristic", "candidate"}
_VERIFIED_REQUIREMENT_STATUSES = {"verified", "source_bound", "applicable"}
_FACTUAL_CLARIFICATION_KEYS_BY_NAME = {
    "Timeline of events": ("timeline",),
    "Actor-by-actor decision timeline": ("decision_timeline", "actor", "timeline"),
    "Responsible party": ("actor", "responsible_party"),
    "Protected activity facts": ("protected_activity",),
    "Adverse action facts": ("adverse_action",),
    "Retaliation causation chronology": ("causation", "timeline"),
    "Retaliation causation link facts": ("causation",),
    "Written notice date": ("notice", "timeline"),
    "Hearing request date": ("hearing", "timeline"),
}


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
                if self.metadata.get('legal_requirement_mode') == 'verified_sources':
                    # The denoiser has a finite per-claim question budget. Keep
                    # current sourced obligations visible before generic facts.
                    def sourced_obligation(dependency):
                        source = self.get_node(dependency['source_node_id'])
                        return bool(source is not None
                            and source.attributes.get('dependency_class') == _LEGALLY_SOURCED_CLASS
                            and source.attributes.get('source_available') is True
                            and source.attributes.get('dependency_scope', {}).get('claim_id') == node.id)
                    check['missing_dependencies'].sort(key=lambda dependency: not sourced_obligation(dependency))
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

        def _modality_precision_fields(evidence_modality: str) -> List[str]:
            modality = _as_text(evidence_modality).lower()
            if modality == "policy_document":
                return ["document_name", "document_date", "issuing_actor"]
            if modality == "file_evidence":
                return ["document_name", "document_date", "issuing_actor"]
            return []

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

        def _ordered_unique(values: List[str]) -> List[str]:
            return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))

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

        def _requirement_update_tokens_for_field(field_name: str, requirement_key: str) -> List[str]:
            updates = [requirement_key] if requirement_key else []
            if field_name in {"event_date", "adverse_action_date", "hearing_request_date", "response_date", "protected_activity_date"}:
                updates.append("chronology_complete")
            if field_name in {"staff_name", "staff_role", "staff_title", "decision_actor"}:
                updates.append("staff_identity_complete")
            if field_name == "causation_link":
                updates.append("causation_link_complete")
            if field_name in {"document_name", "document_date", "issuing_actor"}:
                updates.append("document_traceability_complete")
            return _ordered_unique(updates)

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
            evidence_modality: str,
            weak_claim_focus: bool,
        ) -> Dict[str, Any]:
            required_fields = _ordered_unique(
                [
                    *_required_fields_for_gap(gap_type),
                    *_modality_precision_fields(evidence_modality),
                ]
            )
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
            missing_field_update_plan = []
            for field_name in required_fields:
                field_value = _field_value(source_attrs, field_name)
                field_present = bool(field_value and not _is_unspecified_value(field_value))
                requirement_updates = _requirement_update_tokens_for_field(field_name, requirement_key)
                entity_updates = _entity_updates_for_field(field_name)
                relationship_updates_for_field = _relation_updates_for_field(field_name)
                field_resolution_contract[field_name] = {
                    "field_present": field_present,
                    "field_value": field_value if field_present else "",
                    "entity_updates": entity_updates,
                    "relationship_updates": relationship_updates_for_field,
                    "requirement_updates": requirement_updates,
                    "satisfies_gap_when_present": field_name in missing_fields,
                }
                if not field_present:
                    missing_field_update_plan.append(
                        {
                            "field_name": field_name,
                            "resolution_key": f"{deterministic_update_key}:{field_name}" if deterministic_update_key else field_name,
                            "entity_updates": entity_updates,
                            "relationship_updates": relationship_updates_for_field,
                            "requirement_updates": requirement_updates,
                            "satisfies_gap_when_present": True,
                            "close_gap_after_update": len(missing_fields) == 1,
                        }
                    )

            core_structured = _core_structured_gap(gap_type)
            deterministic_update_operations = _ordered_unique(
                [
                    operation
                    for update in missing_field_update_plan
                    for operation in [
                        *(update.get("entity_updates") or []),
                        *(update.get("relationship_updates") or []),
                        *(update.get("requirement_updates") or []),
                    ]
                ]
            )
            deterministically_closable = bool(
                deterministic_update_key
                and missing_fields
                and all(_field_aliases(field_name) for field_name in missing_fields)
            )
            modality_precision_fields = _modality_precision_fields(evidence_modality)
            modality_precision_missing = [
                field_name for field_name in modality_precision_fields if field_name in missing_fields
            ]
            weak_focus_weight = 1.0 if weak_claim_focus else 0.0
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
                "missing_field_update_plan": missing_field_update_plan,
                "deterministic_update_operations": deterministic_update_operations,
                "closure_confidence": round(closure_confidence, 4),
                "single_turn_closable": len(missing_fields) <= 2,
                "single_field_closable": len(missing_fields) == 1,
                "deterministically_closable": deterministically_closable,
                "core_structured_gap": core_structured,
                "modality_precision_fields": modality_precision_fields,
                "modality_precision_missing_fields": modality_precision_missing,
                "modality_precision_complete": not modality_precision_missing,
                "weak_focus_weight": weak_focus_weight,
                "preferred_next_field": missing_fields[0] if missing_fields else "",
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
        single_turn_closure_candidate_count = 0
        deterministic_field_update_total = 0
        deterministic_field_update_ready = 0
        concrete_gap_candidates = 0
        weak_modality_precision_field_total = 0
        weak_modality_precision_field_ready = 0

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
                    evidence_modality=evidence_modality,
                    weak_claim_focus=weak_claim_focus,
                )
                missing_required_fields = list(answer_contract.get("missing_required_fields") or [])
                required_fields = list(answer_contract.get("required_fields") or [])
                completion_ratio = (
                    1.0 - (len(missing_required_fields) / len(required_fields))
                    if required_fields
                    else 1.0
                )
                missing_field_plan = list(answer_contract.get("missing_field_update_plan") or [])
                per_turn_closure_score = 0.0
                if answer_contract.get("single_field_closable"):
                    per_turn_closure_score = 1.0
                elif answer_contract.get("single_turn_closable"):
                    per_turn_closure_score = 0.8
                elif len(missing_required_fields) == 3:
                    per_turn_closure_score = 0.45
                elif missing_required_fields:
                    per_turn_closure_score = 0.2
                deterministic_plan_ratio = (
                    min(1.0, len(missing_field_plan) / max(1, len(missing_required_fields)))
                    if missing_required_fields
                    else 1.0
                )
                closure_expected_gain = round(
                    max(0.0, min(1.0, (per_turn_closure_score * 0.65) + (deterministic_plan_ratio * 0.35))),
                    4,
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
                actor_score += closure_expected_gain * 2.0
                if answer_contract.get("single_field_closable"):
                    actor_score += 1.4
                if answer_contract.get("deterministically_closable"):
                    actor_score += 1.2
                if weak_modality_focus and answer_contract.get("modality_precision_complete"):
                    actor_score += 0.8
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
                if answer_contract.get("single_field_closable"):
                    critic_score += 1.3
                if answer_contract.get("deterministically_closable"):
                    critic_score += 1.5
                if weak_modality_focus and answer_contract.get("modality_precision_complete"):
                    critic_score += 0.9
                critic_score += deterministic_plan_ratio * 1.2
                combined_priority = (actor_score * 0.55) + (critic_score * 0.45)
                concretely_answerable = not any(
                    _is_unspecified_value(source_attrs.get(field_name))
                    for field_name in ("question_hint", "placeholder", "expected_value")
                )
                if weak_claim_focus:
                    weak_claim_gap_count += 1
                if weak_modality_focus:
                    weak_modality_gap_count += 1
                    modality_precision_fields = list(answer_contract.get("modality_precision_fields") or [])
                    modality_precision_missing = list(answer_contract.get("modality_precision_missing_fields") or [])
                    weak_modality_precision_field_total += len(modality_precision_fields)
                    weak_modality_precision_field_ready += len(
                        [field for field in modality_precision_fields if field not in modality_precision_missing]
                    )
                if answer_contract.get("core_structured_gap"):
                    core_structured_gap_count += 1
                    if answer_contract.get("single_turn_closable"):
                        core_structured_single_turn_closable += 1
                if deterministic_update_key and answer_contract.get("single_turn_closable"):
                    concrete_gap_candidates += 1
                if answer_contract.get("single_turn_closable"):
                    single_turn_closure_candidate_count += 1
                deterministic_field_update_total += len(required_fields)
                deterministic_field_update_ready += len([field for field in required_fields if field not in missing_required_fields])
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
                        'closure_expected_gain': closure_expected_gain,
                        'deterministic_plan_ratio': round(max(0.0, min(1.0, deterministic_plan_ratio)), 4),
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
                    0 if item.get('answer_contract', {}).get('single_field_closable') else 1,
                    0 if item.get('answer_contract', {}).get('deterministically_closable') else 1,
                    0 if item.get('core_structured_gap') else 1,
                    0 if item.get('structured_gap') else 1,
                    _gap_type_rank(str(item.get('gap_type') or '').strip().lower()),
                    0 if item.get('answer_contract', {}).get('single_turn_closable') else 1,
                    -float(item.get('closure_expected_gain') or 0.0),
                    -float(item.get('deterministic_plan_ratio') or 0.0),
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
        deterministic_field_update_coverage = (
            deterministic_field_update_ready / deterministic_field_update_total
            if deterministic_field_update_total > 0
            else deterministic_gap_closure
        )
        concrete_gap_closure_ratio = (
            concrete_gap_candidates / total_missing_dependencies
            if total_missing_dependencies > 0
            else (1.0 if claims else 0.0)
        )
        weak_modality_precision_coverage = (
            weak_modality_precision_field_ready / weak_modality_precision_field_total
            if weak_modality_precision_field_total > 0
            else 1.0
        )
        gap_closure_efficiency = (
            core_structured_single_turn_closable / core_structured_gap_count
            if core_structured_gap_count > 0
            else 0.0
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
        if deterministic_field_update_coverage < 0.7 and total_required_dependencies > 0:
            recommended_actions.append(
                "Emit a missing_field_update_plan per gap and process answers by field-level entity/relationship/requirement updates."
            )
        if weak_modality_gap_count > 0 and weak_modality_precision_coverage < 0.7:
            recommended_actions.append(
                "For policy_document and file_evidence, require document_name, document_date, and issuing/source actor before advancing."
            )
        if concrete_gap_closure_ratio < 0.6 and total_missing_dependencies > 0:
            recommended_actions.append(
                "Select next_required_gap from single-field deterministic closures first so each turn closes one concrete graph gap."
            )
        if gap_closure_efficiency < 0.5 and core_structured_gap_count > 0:
            recommended_actions.append(
                "Bias questioning toward single-field or single-turn closure gaps to reduce stall sessions."
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
                0 if item.get('answer_contract', {}).get('single_field_closable') else 1,
                0 if item.get('answer_contract', {}).get('deterministically_closable') else 1,
                0 if item.get('core_structured_gap') else 1,
                0 if item.get('structured_gap') else 1,
                _gap_type_rank(str(item.get('gap_type') or '').strip().lower()),
                0 if item.get('answer_contract', {}).get('single_turn_closable') else 1,
                -float(item.get('closure_expected_gain') or 0.0),
                -float(item.get('deterministic_plan_ratio') or 0.0),
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
            'single_turn_closure_candidate_count': single_turn_closure_candidate_count,
            'deterministic_field_update_coverage': deterministic_field_update_coverage,
            'concrete_gap_closure_ratio': concrete_gap_closure_ratio,
            'gap_closure_efficiency': gap_closure_efficiency,
            'weak_modality_precision_coverage': weak_modality_precision_coverage,
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
                    'single_turn_closure_candidate_count': single_turn_closure_candidate_count,
                    'deterministic_field_update_coverage': deterministic_field_update_coverage,
                    'concrete_gap_closure_ratio': concrete_gap_closure_ratio,
                    'gap_closure_efficiency': gap_closure_efficiency,
                    'weak_modality_precision_coverage': weak_modality_precision_coverage,
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
        """Deserialize without changing the caller's versioned projection."""
        data = deepcopy(data)
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
                          legal_requirements: Optional[Dict[str, Any]] = None,
                          *,
                          require_verified_legal_sources: bool = False) -> DependencyGraph:
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
            # A user's explicit law-query date selects a legal version; it is
            # not an event date and cannot close a factual chronology gap.
            # Preserve the original claim/source text and all other dates.
            patterns = [
                r'\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+\d{4}\b',
                r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
                r'\b\d{4}-\d{2}-\d{2}\b',
            ]
            legal_date = (r'(?i:\b(?:applicable law date|law in effect on|law applicable on))\s*[: ]\s*(?:'
                          + '|'.join(patterns) + ')')
            text_value = re.sub(legal_date, '', text_value)
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

        self._mark_factual_clarifications(graph)
        graph.metadata["heuristic_law_derived_invoked"] = False
        graph.metadata["legal_requirement_mode"] = (
            "verified_sources" if require_verified_legal_sources else "caller_supplied"
        )
        graph.metadata["legal_source_gaps"] = []

        supplied_requirements = legal_requirements if isinstance(legal_requirements, dict) else {}
        # SummaryJudgmentHook returns dict[str, list[str]]. Those strings are
        # adapted to unresolved entries before this loop. A raw string still
        # must not be stored as a legal element.
        if any(
            isinstance(item, str)
            for items in supplied_requirements.values()
            if isinstance(items, list)
            for item in items
        ):
            from integrations.ipfs_datasets.legal import adapt_sourced_legal_requirements
            supplied_requirements = adapt_sourced_legal_requirements(supplied_requirements)

        # Add legal requirements for each claim. Verified intake never promotes
        # heuristic or template text into a law-derived element.
        if supplied_requirements:
            for claim_node in claim_nodes:
                claim_type = claim_node.attributes.get('claim_type')
                requirements = supplied_requirements.get(claim_type, [])
                if not isinstance(requirements, list):
                    requirements = []
                for req_data in requirements:
                    if not isinstance(req_data, dict):
                        self._add_unresolved_legal_requirement(
                            graph, claim_node, "ambiguous_authority",
                        )
                        continue
                    if self._is_user_law_assertion(req_data) or req_data.get("intake_requirement_status") == "unresolved" or req_data.get("proof_status") in {"unresolved", "not_authoritative"}:
                        self._add_unresolved_legal_requirement(
                            graph,
                            claim_node,
                            str(req_data.get("unresolved_reason") or "ambiguous_authority"),
                            req_data,
                        )
                        continue
                    if require_verified_legal_sources and not self._is_verified_legal_requirement(req_data):
                        self._add_unresolved_legal_requirement(
                            graph,
                            claim_node,
                            "ambiguous_or_unverified_authority",
                            req_data,
                        )
                        continue
                    self._add_legal_requirement_node(graph, claim_node, req_data)

        if require_verified_legal_sources:
            self._add_legal_source_gaps(graph, claim_nodes)
        
        logger.info(f"Built dependency graph: {graph.summary()}")
        return graph

    def build_grounded_hook_graph(
        self,
        claims: List[Dict[str, Any]],
        legal_requirements: Optional[Dict[str, Any]] = None,
        *,
        model_text: str = "",
        taxonomy_names: Optional[List[str]] = None,
        legal_context: Optional[Dict[str, Any]] = None,
    ) -> DependencyGraph:
        """Build a graph whose legal nodes come only from verified source entries.

        Model prose and default claim-taxonomy names are recorded as unresolved.
        They do not become legal elements. Factual clarification nodes stay
        labeled as complainant facts.
        """
        from integrations.ipfs_datasets.legal import adapt_sourced_legal_requirements

        supplied = legal_requirements if isinstance(legal_requirements, dict) else {}
        adapted = adapt_sourced_legal_requirements(supplied, legal_context=legal_context)
        blocked = {str(model_text).strip()} if str(model_text or "").strip() else set()
        blocked.update(str(name).strip() for name in (taxonomy_names or []) if str(name).strip())
        for claim_type, entries in list(adapted.items()):
            rewritten = []
            for entry in entries:
                if not isinstance(entry, dict):
                    rewritten.append(entry)
                    continue
                name = str(entry.get("name") or "").strip()
                description = str(entry.get("description") or "").strip()
                if (
                    name in blocked
                    or description in blocked
                    or entry.get("legacy_template") is True
                    or entry.get("template_kind") == "claim_keyword_template"
                ):
                    entry = dict(entry)
                    entry["intake_requirement_status"] = "unresolved"
                    entry["proof_status"] = "not_authoritative"
                    entry["derivation_status"] = "unresolved"
                    entry["unresolved_reason"] = "model_or_taxonomy_text_is_not_law"
                    entry["law_derived"] = False
                rewritten.append(entry)
            adapted[claim_type] = rewritten
        graph = self.build_from_claims(claims, adapted, require_verified_legal_sources=True)
        factual = []
        legal = []
        for node in graph.nodes.values():
            kind = str((node.attributes or {}).get("record_kind") or node.node_type.value)
            bucket = factual if node.node_type == NodeType.FACT or (node.attributes or {}).get("about_complainant") else legal
            bucket.append({
                "id": node.id,
                "name": node.name,
                "node_type": node.node_type.value,
                "record_kind": kind,
                "law_derived": bool((node.attributes or {}).get("law_derived")),
            })
        graph.metadata["factual_nodes"] = factual
        graph.metadata["legal_nodes"] = legal
        graph.metadata["model_text_created_law"] = False
        graph.metadata["default_taxonomy_created_law"] = False
        graph.metadata["factual_legal_separated"] = True
        return graph

    def _mark_factual_clarifications(self, graph: DependencyGraph) -> None:
        """Label complainant clarification nodes so they stay distinct from legal requirements."""
        for node in graph.get_nodes_by_type(NodeType.FACT):
            attributes = node.attributes if isinstance(node.attributes, dict) else {}
            if attributes.get("timeline_fact_node") or attributes.get("record_kind") == "factual_assertion":
                continue
            if attributes.get("dependency_class"):
                continue
            keys = list(_FACTUAL_CLARIFICATION_KEYS_BY_NAME.get(node.name, ("clarification",)))
            attributes.update({
                "record_kind": _FACTUAL_CLARIFICATION_CLASS,
                "dependency_class": _FACTUAL_CLARIFICATION_CLASS,
                "law_derived": False,
                "about_complainant": True,
                "clarification_keys": keys,
                "dependency_scope": {
                    "clarification_keys": list(keys),
                    "fact_ids": [str(item) for item in (attributes.get("fact_ids") or [])],
                },
                "satisfaction_revision": int(attributes.get("satisfaction_revision") or 0),
            })
            node.attributes = attributes

    @staticmethod
    def _bounded_source_record(record: Any) -> bool:
        """Bound the serialized source proof before the parser copies it."""
        remaining, characters = 8192, 262144
        def bounded(value, depth=0):
            nonlocal remaining, characters
            remaining -= 1
            if remaining < 0 or depth > 8:
                return False
            if isinstance(value, str):
                characters -= len(value)
                return len(value) <= 65536 and characters >= 0
            if value is None or type(value) in (bool, int, float):
                return True
            if isinstance(value, dict):
                return len(value) <= 128 and all(isinstance(key, str) and len(key) <= 128
                    and bounded(item, depth + 1) for key, item in value.items())
            if isinstance(value, list):
                return len(value) <= 256 and all(bounded(item, depth + 1) for item in value)
            return False
        return isinstance(record, dict) and bounded(record)

    @classmethod
    def _is_verified_legal_requirement(cls, requirement: Any) -> bool:
        """Re-derive source admission; serialized verification booleans are not proof."""
        if not isinstance(requirement, dict):
            return False
        source = requirement.get("source_record")
        if not cls._bounded_source_record(source):
            return False
        try:
            from integrations.ipfs_datasets.logic import extract_source_bound_rule_candidates
            admitted = extract_source_bound_rule_candidates(source).get("promoted_requirements", [])
        except Exception:
            return False
        keys = ("rule_text", "source_span", "source_hash", "span_sha256",
                "authority_text_sha256", "authority_id", "authority_version",
                "jurisdiction", "applicable_date", "temporal_applicability",
                "treatment_edges", "blocking_treatments")
        for candidate in admitted:
            if (candidate.get("applicable") is True and candidate.get("support_eligible") is True
                    and not candidate.get("treatment_blocks_support")
                    and all(requirement.get(key) == candidate.get(key) for key in keys)
                    and requirement.get("description") == candidate.get("rule_text")):
                return True
        return False

    def _heuristic_graph_law_derived(self, *args: Any, **kwargs: Any) -> None:
        """Heuristic law text is not a retrieved legal source."""
        raise RuntimeError("heuristic graph law-derived requirements are not a legal source")

    def _rule_identity(self, requirement: Dict[str, Any]) -> str:
        provenance = requirement.get("provenance") if isinstance(requirement.get("provenance"), dict) else {}
        return str(
            requirement.get("rule_id")
            or requirement.get("authority_id")
            or provenance.get("rule_id")
            or provenance.get("source_id")
            or requirement.get("name")
            or ""
        ).strip()

    @staticmethod
    def _is_user_law_assertion(requirement: Dict[str, Any]) -> bool:
        if requirement.get("user_asserted") is True:
            return True
        origin = str(requirement.get("origin") or requirement.get("source_kind") or "").strip().lower()
        if origin in {"user", "user_assertion", "complainant"}:
            return True
        return str(requirement.get("derivation_status") or "").strip().lower() == "user_assertion"

    def _add_unresolved_legal_requirement(
        self,
        graph: DependencyGraph,
        claim_node: DependencyNode,
        reason: str,
        req_data: Optional[Dict[str, Any]] = None,
    ) -> DependencyNode:
        """Record that authority was not selected. This node is not a legal rule."""
        payload = req_data if isinstance(req_data, dict) else {}
        jurisdiction = str(payload.get("jurisdiction") or graph.metadata.get("legal_context_jurisdiction") or "unknown")
        if not jurisdiction.strip():
            jurisdiction = "unknown"
        claim_type = str(claim_node.attributes.get("claim_type") or payload.get("claim_type") or "unknown")
        node = DependencyNode(
            id=self._get_namespaced_node_id("legal_requirement", {
                "gap": "unresolved_legal_requirement",
                "claim_type": claim_type,
                "claim_id": claim_node.id,
                "reason": reason,
                "authority_locator": str(payload.get("authority_locator") or ""),
            }),
            node_type=NodeType.REQUIREMENT,
            name="Unresolved legal requirement",
            description=(
                "No sourced legal requirement was selected. "
                "Missing or ambiguous authority was not replaced with an invented rule."
            ),
            satisfied=False,
            attributes={
                "record_kind": _UNRESOLVED_LEGAL_CLASS,
                "dependency_class": _UNRESOLVED_LEGAL_CLASS,
                "claim_type": claim_type,
                "jurisdiction": jurisdiction,
                "authority_locator": "",
                "source_locator": "",
                "authority_source_locator": "",
                "effective_date": "",
                "authority_version": "",
                "derivation_status": str(payload.get("derivation_status") or "unresolved"),
                "proof_status": "not_authoritative" if self._is_user_law_assertion(payload) or payload.get("proof_status") == "not_authoritative" else "unresolved",
                "unresolved_reason": reason,
                "asserted_text": str(payload.get("asserted_text") or "")[:500],
                "law_derived": False,
                "heuristic_law_derived": False,
                "source_available": False,
                "about_complainant": False,
                "user_assertion_is_not_law": True,
                "dependency_scope": {"claim_type": claim_type, "rule_id": "", "fact_ids": []},
            },
        )
        graph.add_node(node)
        graph.add_dependency(Dependency(
            id=self._get_dependency_id(),
            source_id=node.id,
            target_id=claim_node.id,
            dependency_type=DependencyType.REQUIRES,
            required=True,
        ))
        graph.metadata.setdefault("unresolved_legal_requirements", []).append({
            "claim_type": claim_type,
            "claim_id": claim_node.id,
            "node_id": node.id,
            "jurisdiction": jurisdiction,
            "reason": reason,
            "derivation_status": node.attributes["derivation_status"],
            "proof_status": node.attributes["proof_status"],
        })
        return node

    def _add_legal_requirement_node(
        self,
        graph: DependencyGraph,
        claim_node: DependencyNode,
        req_data: Dict[str, Any],
    ) -> DependencyNode:
        requirement_provenance = req_data.get("provenance") if isinstance(req_data.get("provenance"), dict) else {}
        claim_type = claim_node.attributes.get("claim_type")
        rule_id = self._rule_identity(req_data)
        req_node = DependencyNode(
            id=self._get_namespaced_node_id("legal_requirement", {
                "claim_type": claim_type,
                "claim_id": claim_node.id,
                "requirement": req_data,
            }),
            node_type=NodeType.LEGAL_ELEMENT,
            name=req_data.get("name", "Unnamed Requirement"),
            description=req_data.get("description", ""),
            satisfied=False,
            attributes={
                **deepcopy(req_data),
                "record_kind": "legal_requirement",
                "dependency_class": _LEGALLY_SOURCED_CLASS,
                "source_available": True,
                "source_fact_ids": list(req_data.get("fact_ids") or []),
                "law_derived": False,
                "about_complainant": False,
                "provenance": dict(requirement_provenance),
                "rule_id": rule_id,
                "verification_status": req_data.get("verification_status"),
                "source_bound": req_data.get("source_bound"),
                "dependency_scope": {
                    "claim_type": claim_type,
                    "claim_id": claim_node.id,
                    "rule_id": rule_id,
                    "jurisdiction": str(req_data.get("jurisdiction") or ""),
                    "fact_ids": [str(item) for item in (req_data.get("fact_ids") or []) if str(item).strip()],
                    "date_sensitive": True,
                },
                "satisfaction_revision": 0,
                "satisfaction_state": "unsatisfied",
            },
        )
        self._recompute_support_proof_and_question_targets(req_node)
        graph.add_node(req_node)
        graph.add_dependency(Dependency(
            id=self._get_dependency_id(),
            source_id=req_node.id,
            target_id=claim_node.id,
            dependency_type=DependencyType.REQUIRES,
            required=True,
        ))
        return req_node

    def _add_legal_source_gaps(self, graph: DependencyGraph, claim_nodes: List[DependencyNode]) -> None:
        """Record an explicit source gap when a claim has no retrieved verified requirement."""
        for claim_node in claim_nodes:
            if self._claim_has_sourced_requirement(graph, claim_node.id):
                continue
            claim_type = str(claim_node.attributes.get("claim_type") or "")
            gap = DependencyNode(
                id=self._get_namespaced_node_id("legal_requirement", {
                    "gap": "legal_context_source_gap",
                    "claim_type": claim_type,
                    "claim_id": claim_node.id,
                }),
                node_type=NodeType.REQUIREMENT,
                name="Legal context or source gap",
                description=(
                    "No retrieved verified legal requirement is available for this claim. "
                    "Heuristic law-derived elements were not substituted."
                ),
                satisfied=False,
                attributes={
                    "record_kind": _LEGAL_SOURCE_GAP_CLASS,
                    "dependency_class": _LEGAL_SOURCE_GAP_CLASS,
                    "gap_kind": "legal_context_source_gap",
                    "reason": "no_retrieved_requirements",
                    "law_derived": False,
                    "heuristic_law_derived": False,
                    "about_complainant": False,
                    "claim_type": claim_type,
                    "dependency_scope": {"claim_type": claim_type, "rule_id": "", "fact_ids": []},
                },
            )
            graph.add_node(gap)
            graph.add_dependency(Dependency(
                id=self._get_dependency_id(),
                source_id=gap.id,
                target_id=claim_node.id,
                dependency_type=DependencyType.REQUIRES,
                required=True,
            ))
            graph.metadata.setdefault("legal_source_gaps", []).append({
                "claim_type": claim_type,
                "claim_id": claim_node.id,
                "node_id": gap.id,
                "gap_kind": "legal_context_source_gap",
                "reason": "no_retrieved_requirements",
            })

    def _claim_has_sourced_requirement(self, graph: DependencyGraph, claim_id: str) -> bool:
        for dependency in graph.dependencies.values():
            if dependency.target_id != claim_id:
                continue
            source = graph.nodes.get(dependency.source_id)
            if source is None or not isinstance(source.attributes, dict):
                continue
            if (source.attributes.get("dependency_class") == _LEGALLY_SOURCED_CLASS
                    and source.attributes.get("source_available") is not False
                    and self._is_verified_legal_requirement(source.attributes)):
                return True
        return False

    def reconcile_verified_requirements(self, graph: DependencyGraph, grouped: Dict[str, Any]) -> Dict[str, Any]:
        """Keep unchanged source nodes; retire removed or changed source admissions."""
        claims = graph.get_nodes_by_type(NodeType.CLAIM)
        desired = {}
        for claim in claims:
            for requirement in grouped.get(claim.attributes.get("claim_type"), []) or []:
                if self._is_verified_legal_requirement(requirement):
                    key = self._get_namespaced_node_id("legal_requirement", {
                        "claim_type": claim.attributes.get("claim_type"),
                        "claim_id": claim.id, "requirement": requirement,
                    })
                    desired[key] = (claim, requirement)
        affected, added = [], []
        for node in list(graph.nodes.values()):
            if node.attributes.get("dependency_class") != _LEGALLY_SOURCED_CLASS:
                continue
            if node.id in desired and node.attributes.get("source_available") is not False:
                desired.pop(node.id)
                continue
            if node.attributes.get("source_available") is False:
                if node.satisfied:
                    affected.append(node.id)
                node.satisfied = False
                node.attributes.update(stale_satisfaction=True, satisfaction_state="invalidated")
                continue
            node.attributes["invalidated_satisfaction"] = {"satisfied": bool(node.satisfied), "confidence": node.confidence}
            node.satisfied = False
            node.attributes.update(source_available=False, stale_satisfaction=True,
                                   satisfaction_state="invalidated")
            retired = [edge for edge in graph.dependencies.values()
                       if edge.source_id == node.id or edge.target_id == node.id]
            node.attributes["retired_dependency_edges"] = [
                {"id": edge.id, "source_id": edge.source_id, "target_id": edge.target_id,
                 "dependency_type": edge.dependency_type.value, "required": edge.required}
                for edge in retired]
            graph.dependencies = {key: edge for key, edge in graph.dependencies.items()
                                  if edge.source_id != node.id and edge.target_id != node.id}
            node.attributes["satisfaction_revision"] = int(node.attributes.get("satisfaction_revision") or 0) + 1
            affected.append(node.id)
        for key, (claim, requirement) in desired.items():
            node = self._add_legal_requirement_node(graph, claim, requirement)
            node.attributes.update(stale_satisfaction=True, satisfaction_state="invalidated")
            added.append(node.id)
        self._refresh_legal_source_gaps(graph, claims)
        return {"affected_node_ids": affected + added, "added_node_ids": added,
                "preserved_node_ids": [key for key in graph.nodes if key not in set(affected + added)]}

    def apply_derived_dependency_requirements(self, graph: DependencyGraph, derivation: Dict[str, Any]) -> Dict[str, Any]:
        """Install SDK-derived requirements and visible unresolved research.

        Earlier nodes from this derivation are replaced. Fact support is stored
        on the requirement and does not change its rule text. Other graph
        nodes stay in place.
        """
        if not isinstance(derivation, dict):
            raise ValueError("derivation_invalid")
        task_id = "CIMP-UX-26"
        removed = []
        for node in list(graph.nodes.values()):
            attributes = node.attributes if isinstance(node.attributes, dict) else {}
            if attributes.get("derivation_task") == task_id:
                removed.append(node.id)
                graph.nodes.pop(node.id, None)
        if removed:
            removed_ids = set(removed)
            graph.dependencies = {key: edge for key, edge in graph.dependencies.items()
                                  if edge.source_id not in removed_ids and edge.target_id not in removed_ids}
        claims = graph.get_nodes_by_type(NodeType.CLAIM)
        installed = []
        for requirement in derivation.get("requirements") or []:
            if not isinstance(requirement, dict) or requirement.get("rule_text") != requirement.get("description"):
                continue
            node = self._add_legal_requirement_node(graph, claims[0] if claims else DependencyNode(
                id="case", node_type=NodeType.CLAIM, name="case", attributes={"claim_type": "unspecified"}), requirement)
            if not claims:
                graph.dependencies = {key: edge for key, edge in graph.dependencies.items() if edge.target_id != "case"}
                graph.nodes.pop("case", None)
            node.attributes["derivation_task"] = task_id
            node.attributes["derivation_lineage"] = deepcopy(requirement.get("derivation_lineage") or {})
            node.attributes["fact_support"] = list(requirement.get("fact_support") or [])
            node.attributes["support_state"] = requirement.get("support_state") or "unsupported"
            node.attributes["effective_date"] = requirement.get("effective_date") or ""
            node.attributes["authority_version"] = requirement.get("authority_version") or ""
            node.attributes["jurisdiction"] = requirement.get("jurisdiction") or ""
            node.attributes["admitted_law"] = True
            node.attributes["proof"] = False
            node.description = str(requirement.get("rule_text") or "")
            node.satisfied = False
            installed.append(node.id)
            for fact in node.attributes["fact_support"]:
                fact_node = next((item for item in graph.nodes.values()
                                  if item.node_type == NodeType.FACT and fact.get("fact_id") in {item.id, item.name}), None)
                if fact_node is None:
                    continue
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(), source_id=fact_node.id, target_id=node.id,
                    dependency_type=DependencyType.SUPPORTS, required=False,
                ))
        unresolved_ids = []
        for item in derivation.get("unresolved_research") or []:
            if not isinstance(item, dict):
                continue
            reason = str(item.get("reason") or "unresolved")
            node = DependencyNode(
                id=self._get_namespaced_node_id("legal_requirement", {"gap": "unresolved_research", "reason": reason,
                    "passage_id": str(item.get("passage_id") or ""), "task": task_id}),
                node_type=NodeType.REQUIREMENT,
                name="Unresolved legal research",
                description="Admitted authority did not yield a current requirement. No generic element was substituted.",
                satisfied=False,
                attributes={
                    "record_kind": "unresolved_research",
                    "dependency_class": "unresolved_research",
                    "derivation_task": task_id,
                    "unresolved_reason": reason,
                    "visible": True,
                    "law_derived": False,
                    "admitted_law": False,
                    "proof": False,
                    "review_reasons": list(item.get("review_reasons") or []),
                    "passage_id": str(item.get("passage_id") or ""),
                    "passage_ids": list(item.get("passage_ids") or []),
                },
            )
            graph.add_node(node)
            unresolved_ids.append(node.id)
            for claim in claims:
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(), source_id=node.id, target_id=claim.id,
                    dependency_type=DependencyType.REQUIRES, required=True,
                ))
        graph.metadata["derived_dependency_requirements"] = {
            "task_id": task_id,
            "status": derivation.get("status"),
            "requirement_ids": installed,
            "unresolved_ids": unresolved_ids,
            "hardcoded_elements_used": False,
        }
        return graph.metadata["derived_dependency_requirements"]

    def _refresh_legal_source_gaps(self, graph, claims=None):
        gap_ids = {node.id for node in graph.nodes.values()
                   if node.attributes.get("dependency_class") == _LEGAL_SOURCE_GAP_CLASS}
        for key in gap_ids:
            graph.nodes.pop(key, None)
        graph.dependencies = {key: edge for key, edge in graph.dependencies.items()
                              if edge.source_id not in gap_ids and edge.target_id not in gap_ids}
        graph.metadata["legal_source_gaps"] = []
        self._add_legal_source_gaps(graph, claims if claims is not None else graph.get_nodes_by_type(NodeType.CLAIM))

    def refresh_affected_dependencies(
        self,
        graph: DependencyGraph,
        change: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Recompute dependencies touched by a fact, jurisdiction, date, or rule change.

        Unaffected nodes keep their satisfaction and dependency ids. Affected
        legal satisfaction is marked stale instead of remaining trusted.
        """
        if not isinstance(graph, DependencyGraph):
            return {"affected_node_ids": [], "preserved_node_ids": [], "recomputed_dependency_ids": []}
        payload = change if isinstance(change, dict) else {}
        clarification_keys = {str(item) for item in (payload.get("clarification_keys") or []) if str(item).strip()}
        fact_ids = {str(item) for item in (payload.get("fact_ids") or []) if str(item).strip()}
        rule_ids = {str(item) for item in (payload.get("rule_ids") or []) if str(item).strip()}
        jurisdiction_changed = bool(payload.get("jurisdiction_changed"))
        date_changed = bool(payload.get("date_changed") or payload.get("date_roles"))
        forum_changed = bool(payload.get("forum_changed"))
        applicability_changed = bool(payload.get("applicability_changed"))
        context_changed = bool(payload.get("context_changed"))
        version_changed = bool(payload.get("version_changed") or payload.get("authority_version_changed"))
        treatment_changed = bool(payload.get("treatment_changed") or payload.get("adverse_treatment_changed"))
        definition_changed = bool(payload.get("definition_changed"))
        source_outage = bool(payload.get("source_outage"))
        fact_change = bool(payload.get("fact_change") or fact_ids or clarification_keys)
        updated_requirements = payload.get("updated_requirements") if isinstance(payload.get("updated_requirements"), dict) else {}
        user_facts = {
            node.id: (node.name, node.description, bool(node.satisfied), deepcopy(node.attributes))
            for node in graph.nodes.values()
            if node.node_type == NodeType.FACT or (isinstance(node.attributes, dict) and node.attributes.get("about_complainant") is True and node.attributes.get("dependency_class") != _LEGALLY_SOURCED_CLASS)
        }

        affected_ids = []
        preserved_ids = []
        invalidated = []
        for node in list(graph.nodes.values()):
            if self._dependency_change_affects(
                node, clarification_keys, fact_ids, rule_ids, jurisdiction_changed, date_changed, fact_change,
                version_changed=version_changed, treatment_changed=treatment_changed,
                source_outage=source_outage, definition_changed=definition_changed,
                definition_identity=payload.get("definition_identity"),
                premise_identity=payload.get("premise_identity"),
                adverse_treatment_identity=payload.get("adverse_treatment_identity"),
                forum_changed=forum_changed, applicability_changed=applicability_changed,
                context_changed=context_changed,
            ):
                affected_ids.append(node.id)
            else:
                preserved_ids.append(node.id)

        replaced_rule_ids = []
        if rule_ids and "updated_requirements" in payload:
            replaced_rule_ids = self._replace_changed_rules(graph, rule_ids, updated_requirements)
            affected_ids = [node_id for node_id in affected_ids if node_id in graph.nodes]
            for node in graph.nodes.values():
                scope = node.attributes.get("dependency_scope") if isinstance(node.attributes, dict) else {}
                if isinstance(scope, dict) and str(scope.get("rule_id") or "") in rule_ids and node.id not in affected_ids:
                    affected_ids.append(node.id)
            preserved_ids = [node_id for node_id in graph.nodes if node_id not in set(affected_ids)]

        recomputed = []
        preserved_dependency_ids = []
        affected_set = set(affected_ids)
        rewritten: Dict[str, Dependency] = {}
        for dependency_id, dependency in list(graph.dependencies.items()):
            touches = dependency.source_id in affected_set or dependency.target_id in affected_set
            if not touches:
                rewritten[dependency_id] = dependency
                preserved_dependency_ids.append(dependency_id)
                continue
            recomputed_id = self._get_dependency_id()
            rewritten[recomputed_id] = Dependency(
                id=recomputed_id,
                source_id=dependency.source_id,
                target_id=dependency.target_id,
                dependency_type=dependency.dependency_type,
                required=dependency.required,
                strength=dependency.strength,
            )
            recomputed.append({
                "previous_id": dependency_id,
                "id": recomputed_id,
                "source_id": dependency.source_id,
                "target_id": dependency.target_id,
            })
        if recomputed:
            graph.dependencies = rewritten

        for node_id in affected_ids:
            node = graph.nodes.get(node_id)
            if node is None or not isinstance(node.attributes, dict):
                continue
            prior_satisfied = bool(node.satisfied)
            if prior_satisfied or node.attributes.get("satisfaction_state") == "satisfied":
                node.attributes["invalidated_satisfaction"] = {
                    "satisfied": prior_satisfied,
                    "confidence": node.confidence,
                    "satisfaction_state": node.attributes.get("satisfaction_state"),
                }
                node.satisfied = False
                node.attributes["satisfaction_state"] = "invalidated"
                node.attributes["stale_satisfaction"] = True
                invalidated.append(node_id)
            node.attributes["satisfaction_revision"] = int(node.attributes.get("satisfaction_revision") or 0) + 1
            node.attributes["dependency_recomputed"] = True
            if (version_changed or treatment_changed or source_outage or definition_changed
                    or context_changed or forum_changed or applicability_changed):
                node.attributes["legal_support_invalidated"] = True
                node.attributes["support_eligible"] = False
                if source_outage:
                    node.attributes["invalidation_reason"] = "source_outage"
                    node.attributes["source_available"] = False
                elif version_changed:
                    node.attributes["invalidation_reason"] = "authority_version_changed"
                elif definition_changed:
                    node.attributes["invalidation_reason"] = "definition_changed"
                elif treatment_changed:
                    node.attributes["invalidation_reason"] = "treatment_changed"
                elif jurisdiction_changed:
                    node.attributes["invalidation_reason"] = "jurisdiction_changed"
                elif date_changed:
                    node.attributes["invalidation_reason"] = "date_changed"
                elif forum_changed:
                    node.attributes["invalidation_reason"] = "forum_changed"
                elif applicability_changed:
                    node.attributes["invalidation_reason"] = "applicability_changed"
                elif context_changed:
                    node.attributes["invalidation_reason"] = "legal_context_changed"
            if node.attributes.get("dependency_class") == _LEGALLY_SOURCED_CLASS:
                self._recompute_support_proof_and_question_targets(node)
            if node.attributes.get("proof_cache_identity"):
                node.attributes["rejected_proof_cache_identity"] = node.attributes.get("proof_cache_identity")
                node.attributes["proof_cache_reusable"] = False
                if isinstance(node.attributes.get("proof_cache"), dict):
                    node.attributes["proof_cache"]["reusable"] = False
                    node.attributes["proof_cache"]["satisfied"] = False

        chronology_issue = str(payload.get("chronology_issue") or "").strip().lower()
        if chronology_issue in {"contradictory_dates", "relative_only_ordering"}:
            from integrations.ipfs_datasets.logic import chronology_follow_ups

            follow_ups = chronology_follow_ups(chronology_issue)
            for node in graph.nodes.values():
                attributes = node.attributes if isinstance(node.attributes, dict) else {}
                scope = attributes.get("dependency_scope") if isinstance(attributes.get("dependency_scope"), dict) else {}
                if not (attributes.get("timeline_fact_node") or attributes.get("date_sensitive") or scope.get("date_sensitive")):
                    continue
                if node.satisfied or attributes.get("satisfaction_state") == "satisfied":
                    attributes["invalidated_satisfaction"] = {
                        "satisfied": bool(node.satisfied),
                        "confidence": node.confidence,
                        "satisfaction_state": attributes.get("satisfaction_state"),
                    }
                node.satisfied = False
                attributes["satisfaction_state"] = "uncertain"
                attributes["stale_satisfaction"] = True
                attributes["proof_cache_reusable"] = False
                attributes["chronology_issue"] = chronology_issue
                attributes["recommended_follow_ups"] = follow_ups
                if node.id not in affected_ids:
                    affected_ids.append(node.id)
                    invalidated.append(node.id)
            affected_set = set(affected_ids)

        report = {
            "affected_node_ids": list(affected_ids),
            "preserved_node_ids": [node_id for node_id in graph.nodes if node_id not in affected_set],
            "invalidated_node_ids": invalidated,
            "recomputed_dependencies": recomputed,
            "preserved_dependency_ids": preserved_dependency_ids,
            "replaced_rule_ids": replaced_rule_ids,
            "jurisdiction_changed": jurisdiction_changed,
            "date_changed": date_changed,
            "forum_changed": forum_changed,
            "applicability_changed": applicability_changed,
            "context_changed": context_changed,
            "fact_change": fact_change,
            "fact_ids": sorted(fact_ids),
            "factual_revision": payload.get("factual_revision"),
            "version_changed": version_changed,
            "treatment_changed": treatment_changed,
            "definition_changed": definition_changed,
            "source_outage": source_outage,
            "user_facts_modified": False,
            "graph_replaced": False,
            "empty_success": False,
        }
        if (version_changed or treatment_changed or source_outage or definition_changed) and not chronology_issue:
            for node_id, (name, description, satisfied, attributes) in user_facts.items():
                node = graph.nodes.get(node_id)
                if node is None:
                    report["user_facts_modified"] = True
                    continue
                if node.name != name or node.description != description or bool(node.satisfied) != satisfied or node.attributes != attributes:
                    node.name = name
                    node.description = description
                    node.satisfied = satisfied
                    node.attributes = attributes
                if node_id in report["affected_node_ids"]:
                    report["affected_node_ids"] = [item for item in report["affected_node_ids"] if item != node_id]
                    report["invalidated_node_ids"] = [item for item in report["invalidated_node_ids"] if item != node_id]
                    if node_id not in report["preserved_node_ids"]:
                        report["preserved_node_ids"].append(node_id)
        if graph.metadata.get("legal_requirement_mode") == "verified_sources":
            self._refresh_legal_source_gaps(graph)
        if source_outage:
            graph.metadata["source_outage"] = True
            graph.metadata["empty_success"] = False
            graph.metadata["admission_status"] = "unavailable"
        graph.metadata["last_dependency_refresh"] = {
            "affected_count": len(affected_ids),
            "preserved_count": len(report["preserved_node_ids"]),
            "recomputed_count": len(recomputed),
        }
        graph._update_metadata()
        return report

    def _dependency_change_affects(
        self,
        node: DependencyNode,
        clarification_keys: set,
        fact_ids: set,
        rule_ids: set,
        jurisdiction_changed: bool,
        date_changed: bool,
        fact_change: bool,
        version_changed: bool = False,
        treatment_changed: bool = False,
        source_outage: bool = False,
        definition_changed: bool = False,
        definition_identity: Any = None,
        premise_identity: Any = None,
        adverse_treatment_identity: Any = None,
        forum_changed: bool = False,
        applicability_changed: bool = False,
        context_changed: bool = False,
    ) -> bool:
        attributes = node.attributes if isinstance(node.attributes, dict) else {}
        dependency_class = attributes.get("dependency_class")
        scope = attributes.get("dependency_scope") if isinstance(attributes.get("dependency_scope"), dict) else {}
        if dependency_class == _FACTUAL_CLARIFICATION_CLASS and fact_change:
            node_keys = {str(item) for item in (attributes.get("clarification_keys") or scope.get("clarification_keys") or [])}
            node_facts = {str(item) for item in (scope.get("fact_ids") or [])}
            if clarification_keys and node_keys & clarification_keys:
                return True
            if fact_ids and node_facts & fact_ids:
                return True
            return False
        if dependency_class != _LEGALLY_SOURCED_CLASS:
            return False
        node_rule = str(scope.get("rule_id") or attributes.get("rule_id") or "")
        node_facts = {str(item) for item in (scope.get("fact_ids") or [])}
        if rule_ids and node_rule in rule_ids:
            return True
        if fact_ids and node_facts & fact_ids:
            return True
        if (jurisdiction_changed or date_changed or context_changed or forum_changed or applicability_changed
                or version_changed or treatment_changed or source_outage or definition_changed):
            return True
        if definition_identity is not None and attributes.get("definition_identity") not in (None, definition_identity):
            return True
        if premise_identity is not None and attributes.get("premise_identity") not in (None, premise_identity):
            return True
        if adverse_treatment_identity is not None and attributes.get("adverse_treatment_identity") not in (None, adverse_treatment_identity):
            return True
        return False

    @staticmethod
    def _recompute_support_proof_and_question_targets(node: DependencyNode) -> None:
        """Mint new support, proof, and question identities for one affected requirement."""
        import hashlib

        attributes = node.attributes if isinstance(node.attributes, dict) else {}
        scope = attributes.get("dependency_scope") if isinstance(attributes.get("dependency_scope"), dict) else {}
        basis = json.dumps({
            "authority_id": attributes.get("authority_id"),
            "authority_version": attributes.get("authority_version"),
            "jurisdiction": scope.get("jurisdiction") or attributes.get("jurisdiction"),
            "reason": attributes.get("invalidation_reason"),
            "rule_id": scope.get("rule_id") or attributes.get("rule_id"),
            "satisfaction_revision": attributes.get("satisfaction_revision"),
            "source_hash": attributes.get("source_hash"),
        }, sort_keys=True, default=str)
        digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
        previous_support = str(attributes.get("support_identity") or "")
        if previous_support and previous_support != digest:
            attributes["rejected_support_identity"] = previous_support
        attributes["support_identity"] = digest
        previous_proof = str(attributes.get("proof_identity") or attributes.get("proof_cache_identity") or "")
        if previous_proof:
            attributes["rejected_proof_identity"] = previous_proof
        attributes["proof_identity"] = ""
        attributes["proof_cache_reusable"] = False
        targets = attributes.get("inquiry_targets")
        if isinstance(targets, list):
            for inquiry in targets:
                if not isinstance(inquiry, dict):
                    continue
                inquiry["status"] = "reopened"
                inquiry["target_revision"] = digest[:16]
                inquiry["invalidation_reason"] = attributes.get("invalidation_reason") or "dependency_refresh"
        previous_target = str(attributes.get("question_target_id") or "")
        new_target = "qt_" + digest[:24]
        if previous_target and previous_target != new_target:
            attributes["rejected_question_target_id"] = previous_target
        attributes["question_target_id"] = new_target
        attributes["question_target_revision"] = digest[:16]
        node.attributes = attributes

    def _replace_changed_rules(
        self,
        graph: DependencyGraph,
        rule_ids: set,
        updated_requirements: Dict[str, Any],
    ) -> List[str]:
        """Replace only the sourced requirements whose rule identity changed."""
        removed = []
        claim_nodes = {
            node.id: node
            for node in graph.get_nodes_by_type(NodeType.CLAIM)
            if isinstance(node.attributes, dict)
        }
        for node in list(graph.nodes.values()):
            attributes = node.attributes if isinstance(node.attributes, dict) else {}
            if (attributes.get("dependency_class") != _LEGALLY_SOURCED_CLASS
                    or attributes.get("source_available") is False):
                continue
            scope = attributes.get("dependency_scope") if isinstance(attributes.get("dependency_scope"), dict) else {}
            rule_id = str(scope.get("rule_id") or attributes.get("rule_id") or "")
            if rule_id not in rule_ids:
                continue
            prior = {
                "satisfied": bool(node.satisfied),
                "confidence": node.confidence,
                "satisfaction_state": attributes.get("satisfaction_state"),
            }
            graph.dependencies = {
                dep_id: dep for dep_id, dep in graph.dependencies.items()
                if dep.source_id != node.id and dep.target_id != node.id
            }
            graph.nodes.pop(node.id, None)
            removed.append(rule_id)
            claim_node = claim_nodes.get(str(scope.get("claim_id") or ""))
            replacement = None
            for requirements in [updated_requirements.get(str(scope.get("claim_type") or ""), [])]:
                if not isinstance(requirements, list):
                    continue
                for requirement in requirements:
                    if isinstance(requirement, dict) and self._rule_identity(requirement) == rule_id:
                        replacement = requirement
                        break
            if claim_node is not None and isinstance(replacement, dict) and self._is_verified_legal_requirement(replacement):
                added = self._add_legal_requirement_node(graph, claim_node, replacement)
                added.attributes["stale_satisfaction"] = True
                added.attributes["satisfaction_state"] = "invalidated"
                added.attributes["invalidated_satisfaction"] = prior
                added.satisfied = False
        return removed

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
                satisfied=bool(
                    temporal_context.get('start_date')
                    or temporal_context.get('relative_markers')
                    or fact.get('event_date_or_range')
                ),
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
    
    def invalidate_factual_dependents(
        self,
        graph: DependencyGraph,
        fact_id: str,
        *,
        reason: str,
        event_id: str = "",
    ) -> Dict[str, Any]:
        """Drop proof caches and satisfaction only where this fact is a support input.

        Legal requirement text, source identity, and unrelated node ids stay.
        Contradiction edges remain. Affected inquiry targets are reopened.
        """
        if not isinstance(graph, DependencyGraph) or not fact_id:
            return {"invalidated_node_ids": [], "reopened_inquiry_ids": [], "preserved_node_ids": []}
        invalidated = []
        reopened = []
        for node in graph.nodes.values():
            attributes = node.attributes if isinstance(node.attributes, dict) else {}
            if not self._node_depends_on_fact(node, fact_id):
                continue
            if node.id == fact_id:
                continue
            preserved_text = {
                "name": node.name,
                "description": node.description,
                "rule_id": attributes.get("rule_id"),
                "authority_id": attributes.get("authority_id"),
                "source_hash": attributes.get("source_hash"),
                "source_span": deepcopy(attributes.get("source_span")) if isinstance(attributes.get("source_span"), dict) else attributes.get("source_span"),
                "provenance": deepcopy(attributes.get("provenance")) if isinstance(attributes.get("provenance"), dict) else attributes.get("provenance"),
            }
            if node.satisfied or attributes.get("satisfaction_state") == "satisfied" or attributes.get("proof_cache_identity") or isinstance(attributes.get("proof_cache"), dict):
                attributes["invalidated_satisfaction"] = {
                    "satisfied": bool(node.satisfied),
                    "confidence": node.confidence,
                    "satisfaction_state": attributes.get("satisfaction_state"),
                    "proof_cache_identity": attributes.get("proof_cache_identity"),
                }
                node.satisfied = False
                attributes["satisfaction_state"] = "invalidated"
                attributes["stale_satisfaction"] = True
            if attributes.get("proof_cache_identity"):
                attributes["rejected_proof_cache_identity"] = attributes.get("proof_cache_identity")
            attributes["proof_cache_reusable"] = False
            if isinstance(attributes.get("proof_cache"), dict):
                attributes["proof_cache"] = dict(attributes["proof_cache"])
                attributes["proof_cache"]["reusable"] = False
                attributes["proof_cache"]["satisfied"] = False
                attributes["proof_cache"]["invalidation_reason"] = reason
                attributes["proof_cache"]["invalidated_entity_id"] = fact_id
            attributes["invalidation_reason"] = reason
            attributes["invalidated_entity_id"] = fact_id
            for inquiry in attributes.get("inquiry_targets") or []:
                if not isinstance(inquiry, dict):
                    continue
                target = str(inquiry.get("entity_id") or inquiry.get("fact_id") or "")
                if target != fact_id:
                    continue
                inquiry["status"] = "reopened"
                inquiry["invalidation_reason"] = reason
                inquiry["event_id"] = event_id
                reopened.append(inquiry.get("inquiry_id"))
            node.name = preserved_text["name"]
            node.description = preserved_text["description"]
            attributes["rule_id"] = preserved_text["rule_id"]
            attributes["authority_id"] = preserved_text["authority_id"]
            attributes["source_hash"] = preserved_text["source_hash"]
            attributes["source_span"] = preserved_text["source_span"]
            attributes["provenance"] = preserved_text["provenance"]
            node.attributes = attributes
            invalidated.append(node.id)
        for dependency in graph.dependencies.values():
            if dependency.dependency_type == DependencyType.CONTRADICTS:
                continue
            if dependency.dependency_type != DependencyType.SUPPORTS:
                continue
            if fact_id not in {dependency.source_id, dependency.target_id}:
                continue
            graph.metadata.setdefault("invalidated_support_refs", [])
            ref = {
                "dependency_id": dependency.id,
                "source_id": dependency.source_id,
                "target_id": dependency.target_id,
                "fact_id": fact_id,
                "reason": reason,
                "event_id": event_id,
            }
            if ref not in graph.metadata["invalidated_support_refs"]:
                graph.metadata["invalidated_support_refs"].append(ref)
        graph._update_metadata()
        preserved = [node_id for node_id in graph.nodes if node_id not in set(invalidated)]
        return {
            "invalidated_node_ids": invalidated,
            "reopened_inquiry_ids": reopened,
            "preserved_node_ids": preserved,
        }

    @staticmethod
    def _node_depends_on_fact(node: DependencyNode, fact_id: str) -> bool:
        attributes = node.attributes if isinstance(node.attributes, dict) else {}
        scope = attributes.get("dependency_scope") if isinstance(attributes.get("dependency_scope"), dict) else {}
        listed = {str(item) for item in (scope.get("fact_ids") or []) if str(item).strip()}
        listed.update(str(item) for item in (attributes.get("source_fact_ids") or []) if str(item).strip())
        listed.update(str(item) for item in (attributes.get("support_fact_ids") or []) if str(item).strip())
        if attributes.get("support_fact_id"):
            listed.add(str(attributes.get("support_fact_id")))
        cache = attributes.get("proof_cache") if isinstance(attributes.get("proof_cache"), dict) else {}
        listed.update(str(item) for item in (cache.get("fact_ids") or []) if str(item).strip())
        if cache.get("fact_id"):
            listed.add(str(cache.get("fact_id")))
        for inquiry in attributes.get("inquiry_targets") or []:
            if isinstance(inquiry, dict) and str(inquiry.get("fact_id") or inquiry.get("entity_id") or "") == fact_id:
                listed.add(fact_id)
        return fact_id in listed

    def apply_retrieval_nomination(
        self,
        graph: DependencyGraph,
        payload: Dict[str, Any],
        *,
        claim_id: str = "",
        requirement_id: str = "",
        source_span: Optional[Dict[str, Any]] = None,
        allegation_id: str = "",
    ) -> Dict[str, Any]:
        """Admit retrieval output as a nomination until exact binding is rechecked.

        A bound nomination may support a factual allegation. It does not rewrite
        or satisfy the governing legal requirement.
        """
        from mediator.integrations.graph_tools import GraphRetrievalAugmentor

        if not isinstance(graph, DependencyGraph):
            return {"admitted": False, "reason": "dependency_graph_unavailable", "bound_support": False}
        augmentor = GraphRetrievalAugmentor()
        if claim_id or requirement_id or source_span is not None:
            checked = augmentor.recheck_support_binding(
                payload,
                claim_id=claim_id,
                requirement_id=requirement_id,
                source_span=source_span,
            )
        else:
            checked = dict(payload)
            checked["bound_support"] = False
            checked["support_status"] = checked.get("support_status") or "candidate_nomination"
            checked["satisfied_legal_requirement"] = False
        legal = graph.nodes.get(requirement_id) if requirement_id else None
        legal_before = None
        if legal is not None:
            legal_before = {
                "id": legal.id,
                "name": legal.name,
                "description": legal.description,
                "satisfied": legal.satisfied,
                "rule_id": (legal.attributes or {}).get("rule_id"),
                "authority_id": (legal.attributes or {}).get("authority_id"),
                "source_hash": (legal.attributes or {}).get("source_hash"),
                "source_span": deepcopy((legal.attributes or {}).get("source_span")),
                "provenance": deepcopy((legal.attributes or {}).get("provenance")),
            }
        record_id = str(checked.get("id") or "").strip()
        if record_id and graph.get_node(record_id) is None:
            graph.add_node(DependencyNode(
                id=record_id,
                node_type=NodeType.EVIDENCE,
                name=str(checked.get("name") or "Evidence"),
                description=str(checked.get("description") or ""),
                satisfied=False,
                confidence=float(checked.get("retrieval_confidence", checked.get("confidence", 0.0)) or 0.0),
                attributes={
                    "support_status": checked.get("support_status"),
                    "binding_status": checked.get("binding_status"),
                    "bound_support": bool(checked.get("bound_support")),
                    "retrieval_confidence": checked.get("retrieval_confidence", checked.get("confidence")),
                    "confidence_role": "retrieval_candidate",
                    "satisfied_legal_requirement": False,
                    "supports_claims": list(checked.get("supports_claims") or []),
                    "source_type": checked.get("source_type"),
                },
            ))
        if checked.get("bound_support") and allegation_id and allegation_id in graph.nodes and record_id in graph.nodes:
            dependency_id = f"supports:{record_id}:{allegation_id}"
            if dependency_id not in graph.dependencies:
                graph.add_dependency(Dependency(
                    id=dependency_id,
                    source_id=record_id,
                    target_id=allegation_id,
                    dependency_type=DependencyType.SUPPORTS,
                    required=False,
                    strength=0.0,
                ))
            allegation = graph.nodes[allegation_id]
            allegation_attributes = dict(allegation.attributes or {})
            refs = list(allegation_attributes.get("evidence_support_refs") or [])
            if record_id not in refs:
                refs.append(record_id)
            allegation_attributes["evidence_support_refs"] = refs
            allegation.attributes = allegation_attributes
        if legal is not None and legal_before is not None:
            legal.id = legal_before["id"]
            legal.name = legal_before["name"]
            legal.description = legal_before["description"]
            legal.satisfied = False if not legal_before["satisfied"] else legal_before["satisfied"]
            attributes = dict(legal.attributes or {})
            attributes["rule_id"] = legal_before["rule_id"]
            attributes["authority_id"] = legal_before["authority_id"]
            attributes["source_hash"] = legal_before["source_hash"]
            attributes["source_span"] = legal_before["source_span"]
            attributes["provenance"] = legal_before["provenance"]
            attributes["satisfied_by_retrieval"] = False
            legal.attributes = attributes
        graph._update_metadata()
        return {
            "admitted": bool(checked.get("bound_support")),
            "bound_support": bool(checked.get("bound_support")),
            "support_status": checked.get("support_status"),
            "binding_status": checked.get("binding_status"),
            "binding_reason": checked.get("binding_reason"),
            "satisfied_legal_requirement": False,
            "retrieval_confidence": checked.get("retrieval_confidence", checked.get("confidence")),
            "legal_requirement": legal_before,
        }

    def support_factual_allegation(
        self,
        graph: DependencyGraph,
        *,
        evidence_id: str,
        allegation_id: str,
        legal_requirement_id: str,
    ) -> Dict[str, Any]:
        """Let evidence support an allegation without editing the legal requirement."""
        evidence = graph.nodes.get(evidence_id)
        allegation = graph.nodes.get(allegation_id)
        legal = graph.nodes.get(legal_requirement_id)
        if evidence is None or allegation is None or legal is None:
            return {"supported": False, "reason": "endpoint_unavailable"}
        before = {
            "id": legal.id,
            "name": legal.name,
            "description": legal.description,
            "rule_id": (legal.attributes or {}).get("rule_id"),
            "authority_id": (legal.attributes or {}).get("authority_id"),
            "source_hash": (legal.attributes or {}).get("source_hash"),
            "source_span": deepcopy((legal.attributes or {}).get("source_span")),
            "provenance": deepcopy((legal.attributes or {}).get("provenance")),
            "satisfied": bool(legal.satisfied),
        }
        dependency_id = f"supports:{evidence_id}:{allegation_id}"
        if dependency_id not in graph.dependencies:
            graph.add_dependency(Dependency(
                id=dependency_id,
                source_id=evidence_id,
                target_id=allegation_id,
                dependency_type=DependencyType.SUPPORTS,
                required=False,
                strength=1.0,
            ))
        attributes = dict(allegation.attributes or {})
        refs = list(attributes.get("evidence_support_refs") or [])
        if evidence_id not in refs:
            refs.append(evidence_id)
        attributes["evidence_support_refs"] = refs
        attributes["epistemic_class"] = attributes.get("epistemic_class") or "allegation"
        allegation.attributes = attributes
        legal.name = before["name"]
        legal.description = before["description"]
        legal.satisfied = before["satisfied"]
        legal_attributes = dict(legal.attributes or {})
        legal_attributes["rule_id"] = before["rule_id"]
        legal_attributes["authority_id"] = before["authority_id"]
        legal_attributes["source_hash"] = before["source_hash"]
        legal_attributes["source_span"] = before["source_span"]
        legal_attributes["provenance"] = before["provenance"]
        legal.attributes = legal_attributes
        graph._update_metadata()
        return {"supported": True, "legal_requirement": before, "allegation_id": allegation_id}

    def record_visible_contradiction(
        self,
        graph: DependencyGraph,
        *,
        left_fact_id: str,
        right_fact_id: str,
        legal_requirement_id: str,
    ) -> Dict[str, Any]:
        """Keep both facts visible. Neither contradiction becomes a satisfied legal requirement."""
        left = graph.nodes.get(left_fact_id)
        right = graph.nodes.get(right_fact_id)
        legal = graph.nodes.get(legal_requirement_id)
        if left is None or right is None or legal is None:
            return {"visible": False, "reason": "endpoint_unavailable"}
        before = {
            "id": legal.id,
            "name": legal.name,
            "description": legal.description,
            "rule_id": (legal.attributes or {}).get("rule_id"),
            "source_hash": (legal.attributes or {}).get("source_hash"),
            "provenance": deepcopy((legal.attributes or {}).get("provenance")),
        }
        dependency_id = f"contradicts:{left_fact_id}:{right_fact_id}"
        if dependency_id not in graph.dependencies:
            graph.add_dependency(Dependency(
                id=dependency_id,
                source_id=left_fact_id,
                target_id=right_fact_id,
                dependency_type=DependencyType.CONTRADICTS,
                required=False,
                strength=1.0,
            ))
        legal.satisfied = False
        attributes = dict(legal.attributes or {})
        attributes["satisfaction_state"] = "unsatisfied"
        attributes["satisfied_by_contradiction"] = False
        attributes["rule_id"] = before["rule_id"]
        attributes["source_hash"] = before["source_hash"]
        attributes["provenance"] = before["provenance"]
        legal.attributes = attributes
        legal.name = before["name"]
        legal.description = before["description"]
        graph._update_metadata()
        return {
            "visible": left_fact_id in graph.nodes and right_fact_id in graph.nodes,
            "legal_requirement_satisfied": bool(legal.satisfied),
            "dependency_id": dependency_id,
            "legal_text": legal.name,
            "legal_source_hash": attributes.get("source_hash"),
        }

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
        nomination = str(evidence_data.get("support_status") or "") == "candidate_nomination" or evidence_data.get("binding_status") == "unbound"
        evidence_node = DependencyNode(
            id=self._get_node_id(),
            node_type=NodeType.EVIDENCE,
            name=evidence_data.get('name', 'Unnamed Evidence'),
            description=evidence_data.get('description', ''),
            satisfied=not nomination,
            confidence=evidence_data.get('confidence', 0.8),
            attributes=evidence_data.get('attributes', {})
        )
        if nomination:
            evidence_node.attributes = dict(evidence_node.attributes or {})
            evidence_node.attributes["support_status"] = "candidate_nomination"
            evidence_node.attributes["satisfied_legal_requirement"] = False
            evidence_node.satisfied = False
        graph.add_node(evidence_node)

        if nomination and not evidence_data.get("bound_support"):
            graph._update_metadata()
            return evidence_node.id

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

    def _get_namespaced_node_id(self, kind: str, identity: Optional[Dict[str, Any]] = None) -> str:
        """Mint a node id that cannot collide with fact, claim, or link ids."""
        from integrations.ipfs_datasets.graphs import mint_graph_record_id

        self.node_counter += 1
        if identity is not None:
            return mint_graph_record_id(kind, json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        return mint_graph_record_id(kind, kind, str(self.node_counter))
    
    def _get_dependency_id(self) -> str:
        """Generate unique dependency ID."""
        self.dependency_counter += 1
        return f"dep_{self.dependency_counter}"

    def apply_element_proof_cache(
        self,
        graph: DependencyGraph,
        node_id: str,
        evaluation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Bind a versioned element proof. A new identity drops the prior satisfied result."""

        node = graph.nodes.get(node_id)
        if node is None or not isinstance(node.attributes, dict):
            raise KeyError(node_id)
        from integrations.ipfs_datasets.logic import verify_element_proof_evaluation
        admission = verify_element_proof_evaluation(evaluation)
        admitted = bool(admission.get('verified'))
        observed = admission.get('evaluation') if admitted else {}
        evaluation = observed if isinstance(observed, dict) else {}
        identity = str(evaluation.get("cache_identity") or "")
        previous = str(node.attributes.get("proof_cache_identity") or "")
        if previous and previous != identity:
            node.attributes["rejected_proof_cache_identity"] = previous
            node.attributes["proof_cache_reusable"] = False
            if node.satisfied or node.attributes.get("satisfaction_state") == "satisfied":
                node.attributes["invalidated_satisfaction"] = {
                    "satisfied": bool(node.satisfied),
                    "confidence": node.confidence,
                    "satisfaction_state": node.attributes.get("satisfaction_state"),
                    "proof_cache_identity": previous,
                }
            node.satisfied = False
        # A current, issued evaluation remains nonsubstantive until an actual
        # checked kernel proof contract is configured and verified by the adapter.
        satisfied = admitted and admission.get('satisfied') is True
        node.attributes['proof_evaluation_verified'] = admitted
        node.attributes['proof_evaluation_reason'] = admission.get('reason')
        node.attributes["proof_cache_identity"] = identity
        node.attributes["proof_cache"] = {
            "cache_identity": identity,
            "satisfied": satisfied,
            "status": evaluation.get("status") or 'unknown',
            "reason": evaluation.get("reason") or admission.get('reason'),
            "reusable": satisfied,
            "result": deepcopy(evaluation.get("result")),
        }
        node.attributes["recommended_follow_ups"] = list(evaluation.get("recommended_follow_ups") or [])
        if satisfied:
            node.satisfied = True
            node.attributes["satisfaction_state"] = "satisfied"
            node.attributes["proof_cache_reusable"] = True
            node.attributes["stale_satisfaction"] = False
        else:
            node.satisfied = False
            node.attributes["satisfaction_state"] = str(evaluation.get("status") or "uncertain")
            node.attributes["proof_cache_reusable"] = False
            node.attributes["stale_satisfaction"] = True
        graph._update_metadata()
        return deepcopy(node.attributes)

    def add_fact_rule_link(
        self,
        graph: DependencyGraph,
        *,
        factual_assertion_id: str,
        rule_id: str,
        relation: str = "supports",
        factual_provenance: Optional[Dict[str, Any]] = None,
        rule_provenance: Optional[Dict[str, Any]] = None,
        factual_name: str = "",
        rule_name: str = "",
    ) -> Dict[str, Any]:
        """Record a support or contradiction edge across factual and rule namespaces.

        Each side keeps its own provenance chain. The link id is neither a fact
        id nor a rule id.
        """
        from integrations.ipfs_datasets.graphs import (
            FACTUAL_ASSERTION_KIND,
            build_namespaced_support_link,
            record_kind_from_id,
        )

        link = build_namespaced_support_link(
            factual_assertion_id=factual_assertion_id,
            rule_id=rule_id,
            relation=relation,
            factual_provenance=factual_provenance,
            rule_provenance=rule_provenance,
        )
        fact_chain = dict(link["provenance_chains"][FACTUAL_ASSERTION_KIND])
        rule_chain = dict(link["provenance_chains"]["rule"])
        fact_text = factual_name or factual_assertion_id
        if link["assertion_verified"]:
            # The flag verifies only the immutable assertion's content. A local
            # alias or caller display label cannot introduce another assertion.
            from integrations.ipfs_datasets.types import user_assertion_from_mapping
            asserted_text = user_assertion_from_mapping(fact_chain["user_assertion"]).source_span_text
            if factual_name and " ".join(factual_name.split()) != " ".join(asserted_text.split()):
                raise ValueError("factual label differs from the verified assertion span")
            fact_text = asserted_text
        fact_ref = link["factual_assertion_id"]
        rule_kind = record_kind_from_id(rule_id)
        # Validate both endpoints and any replay BEFORE mutating the graph.
        for endpoint, expected_type, expected_kind, chain in (
            (fact_ref, NodeType.FACT, FACTUAL_ASSERTION_KIND, fact_chain),
            (rule_id, NodeType.LEGAL_ELEMENT, rule_kind, rule_chain),
        ):
            node = graph.nodes.get(endpoint)
            if node is None:
                continue
            if node.id != endpoint or node.node_type != expected_type or node.attributes.get("record_kind") != expected_kind:
                raise ValueError("cross-graph endpoint has a conflicting type or namespace")
            if node.attributes.get("provenance", {}) != chain:
                raise ValueError("cross-graph endpoint has conflicting source provenance")
            if expected_type == NodeType.FACT and link["assertion_verified"] and (
                not isinstance(node.name, str) or " ".join(node.name.split()) != " ".join(fact_text.split())
            ):
                raise ValueError("stored factual text differs from its verified assertion span")
        if fact_ref != factual_assertion_id and factual_assertion_id in graph.nodes:
            node = graph.nodes[factual_assertion_id]
            if node.id != factual_assertion_id or node.node_type != NodeType.FACT or node.attributes.get("provenance", {}) != fact_chain:
                raise ValueError("local factual endpoint is ambiguous or has conflicting provenance")
            if link["assertion_verified"] and (
                not isinstance(node.name, str) or " ".join(node.name.split()) != " ".join(fact_text.split())
            ):
                raise ValueError("local factual text differs from its verified assertion span")
        dependency_type = (
            DependencyType.CONTRADICTS if link["link_type"] == "contradiction_link" else DependencyType.SUPPORTS
        )
        existing_dependency = graph.dependencies.get(link["link_id"])
        if existing_dependency is not None and (
            existing_dependency.id != link["link_id"]
            or existing_dependency.source_id != fact_ref or existing_dependency.target_id != rule_id
            or existing_dependency.dependency_type != dependency_type
            or existing_dependency.required or existing_dependency.strength != 1.0
        ):
            raise ValueError("cross-graph link identity conflicts with an existing dependency")
        existing_links = graph.metadata.get("cross_graph_links", [])
        if not isinstance(existing_links, list):
            raise ValueError("invalid cross-graph link registry")
        previous = [item for item in existing_links if isinstance(item, dict) and item.get("link_id") == link["link_id"]]
        if any(item != link for item in previous):
            raise ValueError("cross-graph link replay changed provenance")
        if fact_ref not in graph.nodes:
            graph.add_node(DependencyNode(
                id=fact_ref,
                node_type=NodeType.FACT,
                name=fact_text,
                attributes={
                    "record_kind": FACTUAL_ASSERTION_KIND,
                    "source_entity_id": factual_assertion_id,
                    "assertion_verified": link["assertion_verified"],
                    "provenance": deepcopy(fact_chain),
                },
            ))
        if rule_id not in graph.nodes:
            graph.add_node(DependencyNode(
                id=rule_id,
                node_type=NodeType.LEGAL_ELEMENT,
                name=rule_name or rule_id,
                attributes={
                    "record_kind": rule_kind,
                    "about_complainant": False,
                    "provenance": deepcopy(rule_chain),
                },
            ))
        graph.add_dependency(Dependency(
            id=link["link_id"],
            source_id=fact_ref,
            target_id=rule_id,
            dependency_type=dependency_type,
            required=False,
            strength=1.0,
        ))
        if not previous:
            graph.metadata.setdefault("cross_graph_links", []).append(deepcopy(link))
        return deepcopy(link)
