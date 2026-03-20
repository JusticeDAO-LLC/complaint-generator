"""
Knowledge Graph Builder

Extracts entities, relationships, and facts from complaint text to build
a knowledge graph representation for denoising and evidence gathering.
"""

import json
import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC


def _utc_now_isoformat() -> str:
    return datetime.now(UTC).isoformat()

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """Represents an entity in the knowledge graph."""
    id: str
    type: str  # person, organization, location, date, claim, fact, etc.
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "complaint"  # complaint, evidence, inference
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Relationship:
    """Represents a relationship between entities."""
    id: str
    source_id: str
    target_id: str
    relation_type: str  # caused_by, employed_by, located_at, occurred_on, etc.
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "complaint"
    
    def to_dict(self) -> dict:
        return asdict(self)


class KnowledgeGraph:
    """
    Knowledge graph representation of complaint information.
    
    Stores entities (people, organizations, facts, claims) and their relationships
    to enable reasoning, gap detection, and iterative denoising.
    """
    
    def __init__(self):
        self.entities: Dict[str, Entity] = {}
        self.relationships: Dict[str, Relationship] = {}
        self.metadata = {
            'created_at': _utc_now_isoformat(),
            'last_updated': _utc_now_isoformat(),
            'version': '1.0'
        }
    
    def add_entity(self, entity: Entity) -> str:
        """Add an entity to the graph."""
        self.entities[entity.id] = entity
        self._update_metadata()
        return entity.id
    
    def add_relationship(self, relationship: Relationship) -> str:
        """Add a relationship to the graph."""
        self.relationships[relationship.id] = relationship
        self._update_metadata()
        return relationship.id
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        return self.entities.get(entity_id)
    
    def get_relationships_for_entity(self, entity_id: str) -> List[Relationship]:
        """Get all relationships involving an entity."""
        return [
            rel for rel in self.relationships.values()
            if rel.source_id == entity_id or rel.target_id == entity_id
        ]
    
    def get_entities_by_type(self, entity_type: str) -> List[Entity]:
        """Get all entities of a specific type."""
        return [e for e in self.entities.values() if e.type == entity_type]
    
    def find_gaps(self) -> List[Dict[str, Any]]:
        """
        Identify gaps in the knowledge graph that need more information.
        
        Returns a list of gaps with suggested questions.
        """
        gaps = []

        def _entity_text(entity: Entity) -> str:
            attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
            parts = [
                str(entity.name or ""),
                str(attributes.get("description") or ""),
                str(attributes.get("event_label") or ""),
                str(attributes.get("event_date_or_range") or ""),
            ]
            return " ".join(part.strip() for part in parts if str(part).strip()).lower()

        def _has_date_signal(text_value: str) -> bool:
            if not text_value:
                return False
            return bool(
                re.search(
                    r"\b(?:19|20)\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b",
                    text_value,
                )
            )

        def _has_exact_date_signal(text_value: str) -> bool:
            if not text_value:
                return False
            return bool(
                re.search(
                    (
                        r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|"
                        r"jul|july|aug|august|sep|sept|september|oct|october|nov|november|"
                        r"dec|december)\s+\d{1,2},\s+\d{4}\b"
                        r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
                        r"|\b\d{4}-\d{2}-\d{2}\b"
                    ),
                    text_value,
                    flags=re.IGNORECASE,
                )
            )
        
        # Check for entities with low confidence
        for entity in self.entities.values():
            if entity.confidence < 0.7:
                gaps.append({
                    'type': 'low_confidence_entity',
                    'entity_id': entity.id,
                    'entity_type': entity.type,
                    'entity_name': entity.name,
                    'confidence': entity.confidence,
                    'suggested_question': f"Can you provide more details about {entity.name}?"
                })
        
        # Check for incomplete relationships
        for entity in self.entities.values():
            rels = self.get_relationships_for_entity(entity.id)
            if len(rels) == 0 and entity.type in ['person', 'organization']:
                gaps.append({
                    'type': 'isolated_entity',
                    'entity_id': entity.id,
                    'entity_type': entity.type,
                    'entity_name': entity.name,
                    'suggested_question': f"What is the relationship between {entity.name} and the complaint?"
                })
        
        # Check for claims without evidence
        claims = self.get_entities_by_type('claim')
        for claim in claims:
            evidence_rels = [
                rel for rel in self.get_relationships_for_entity(claim.id)
                if rel.relation_type == 'supported_by'
            ]
            if len(evidence_rels) == 0:
                gaps.append({
                    'type': 'unsupported_claim',
                    'entity_id': claim.id,
                    'claim_name': claim.name,
                    'suggested_question': f"What evidence supports the claim: {claim.name}?"
                })

        # Check for missing timeline details
        has_dates = any(e.type == 'date' for e in self.entities.values())
        has_timeline_rel = any(
            rel.relation_type in {'occurred_on', 'has_timeline_detail'}
            for rel in self.relationships.values()
        )
        has_timeline_fact = any(
            e.type == 'fact' and e.attributes.get('fact_type') == 'timeline'
            for e in self.entities.values()
        )
        if not has_dates and not has_timeline_rel and not has_timeline_fact:
            gaps.append({
                'type': 'missing_timeline',
                'suggested_question': "When did the key events happen? Please share dates or a brief timeline."
            })

        timeline_fact_texts = [
            _entity_text(entity)
            for entity in self.entities.values()
            if entity.type == "fact" and (entity.attributes or {}).get("fact_type") == "timeline"
        ]
        decision_timeline_terms = (
            "decision",
            "decided",
            "approved",
            "denied",
            "terminated",
            "disciplined",
            "evicted",
            "notice",
            "email",
            "letter",
            "message",
        )
        has_decision_timeline_detail = any(
            any(term in text_value for term in decision_timeline_terms) and _has_date_signal(text_value)
            for text_value in timeline_fact_texts
        )
        if not has_decision_timeline_detail:
            gaps.append({
                'type': 'missing_decision_timeline',
                'suggested_question': (
                    "Please walk through an actor-by-actor decision timeline: who took each action, "
                    "what they did, and the exact date (or best estimate) for each step."
                ),
            })

        # Check for missing responsible party (no orgs or respondent roles captured)
        has_org = any(e.type == 'organization' for e in self.entities.values())
        has_respondent_person = any(
            e.type == 'person' and e.attributes.get('role', '').lower() in {'respondent', 'manager', 'supervisor', 'employer', 'owner', 'landlord'}
            for e in self.entities.values()
        )
        if not has_org and not has_respondent_person:
            gaps.append({
                'type': 'missing_responsible_party',
                'suggested_question': "Who is the person or organization you believe is responsible (e.g., employer, manager, agency)?"
            })

        # Check for missing impact/remedy details
        has_impact = any(
            e.type == 'fact' and e.attributes.get('fact_type') == 'impact'
            for e in self.entities.values()
        )
        has_remedy = any(
            e.type == 'fact' and e.attributes.get('fact_type') == 'remedy'
            for e in self.entities.values()
        )
        if not has_impact or not has_remedy:
            gaps.append({
                'type': 'missing_impact_remedy',
                'missing_impact': not has_impact,
                'missing_remedy': not has_remedy,
                'suggested_question': "What harm did you experience, and what outcome or remedy are you seeking?"
            })

        # Blocker checks: written notices, hearing request dates, and identifiable staff actors.
        all_entity_text = " ".join(_entity_text(entity) for entity in self.entities.values())
        notice_terms = ("notice", "letter", "email", "message", "termination letter", "denial notice")
        has_notice_reference = any(term in all_entity_text for term in notice_terms)
        has_notice_evidence = any(
            entity.type == "evidence" and any(term in _entity_text(entity) for term in notice_terms)
            for entity in self.entities.values()
        )
        if has_notice_reference and not has_notice_evidence:
            gaps.append({
                'type': 'missing_written_notice',
                'suggested_question': "What written notice, letter, email, or message did you receive, who sent it, and what date is on it?"
            })

        hearing_terms = ("hearing", "grievance", "appeal")
        has_hearing_reference = any(term in all_entity_text for term in hearing_terms)
        hearing_has_date = False
        for entity in self.entities.values():
            text_value = _entity_text(entity)
            if not any(term in text_value for term in hearing_terms):
                continue
            if entity.type == "date":
                hearing_has_date = True
                break
            if re.search(r"\b(?:19|20)\d{2}\b", text_value):
                hearing_has_date = True
                break
        if has_hearing_reference and not hearing_has_date:
            gaps.append({
                'type': 'missing_hearing_request_date',
                'suggested_question': "When did you request a hearing, grievance, or appeal, and when (if ever) did they respond?"
            })

        response_terms = ("respond", "response", "replied", "reply", "denied", "approved", "ignored", "no response")
        has_response_reference = any(term in all_entity_text for term in response_terms)
        has_response_date = False
        for entity in self.entities.values():
            text_value = _entity_text(entity)
            if not any(term in text_value for term in response_terms):
                continue
            if _has_date_signal(text_value):
                has_response_date = True
                break
            if entity.type == "date":
                has_response_date = True
                break
        if has_response_reference and not has_response_date:
            gaps.append({
                'type': 'missing_response_dates',
                'suggested_question': "When did each response occur (including any non-response), who gave it, and what exactly did they say?"
            })

        named_staff_entities = [
            entity for entity in self.entities.values()
            if entity.type == "person" and len((entity.name or "").split()) >= 2
        ]
        has_staff_role = any(
            entity.type == "person" and (entity.attributes or {}).get("role")
            for entity in self.entities.values()
        )
        if has_staff_role and not named_staff_entities:
            gaps.append({
                'type': 'missing_staff_identity',
                'suggested_question': "Who specifically took the action (full name, role, and team/department if known)?"
            })

        staff_missing_title = [
            entity for entity in named_staff_entities
            if not str((entity.attributes or {}).get("role") or "").strip()
        ]
        if staff_missing_title:
            gaps.append({
                'type': 'missing_staff_title',
                'suggested_question': (
                    "For each staff member involved, what was their title/role at the time "
                    "(for example manager, HR specialist, hearing officer)?"
                ),
            })

        timeline_action_terms = ("decided", "decision", "denied", "approved", "terminated", "disciplined", "evicted", "notice", "letter", "email")
        has_action_without_exact_date = any(
            entity.type in {"fact", "claim", "evidence"}
            and any(term in _entity_text(entity) for term in timeline_action_terms)
            and not _has_exact_date_signal(_entity_text(entity))
            for entity in self.entities.values()
        )
        if has_action_without_exact_date:
            gaps.append({
                'type': 'missing_exact_action_dates',
                'suggested_question': (
                    "What are the exact dates for each key action (or your best day-level estimate), "
                    "including decisions, notices, and responses?"
                ),
            })

        retaliation_claims = [
            entity for entity in claims
            if str((entity.attributes or {}).get("claim_type") or "").strip().lower() == "retaliation"
        ]
        if retaliation_claims:
            has_protected_activity_fact = any(
                entity.type == "fact"
                and any(
                    token in _entity_text(entity)
                    for token in ("protected activity", "complained", "reported", "grievance", "requested accommodation")
                )
                for entity in self.entities.values()
            )
            has_adverse_action_fact = any(
                entity.type in {"fact", "claim"}
                and any(
                    token in _entity_text(entity)
                    for token in ("fired", "terminated", "demoted", "disciplined", "suspended", "reduced")
                )
                for entity in self.entities.values()
            )
            has_retaliation_timeline = any(
                rel.relation_type in {"occurred_on", "has_timeline_detail"}
                for rel in self.relationships.values()
            ) or any(entity.type == "date" for entity in self.entities.values())
            has_protected_activity_date = any(
                entity.type == "fact"
                and "protected" in _entity_text(entity)
                and _has_date_signal(_entity_text(entity))
                for entity in self.entities.values()
            )
            has_adverse_action_date = any(
                entity.type == "fact"
                and any(token in _entity_text(entity) for token in ("fired", "terminated", "demoted", "disciplined", "suspended", "reduced", "adverse"))
                and _has_date_signal(_entity_text(entity))
                for entity in self.entities.values()
            )
            has_causation_link_signal = any(
                rel.relation_type in {"caused_by", "causal_link", "follows_protected_activity", "occurred_after"}
                for rel in self.relationships.values()
            ) or any(
                "because" in _entity_text(entity)
                or "after" in _entity_text(entity)
                or "soon after" in _entity_text(entity)
                for entity in self.entities.values()
                if entity.type == "fact"
            )
            if not (
                has_protected_activity_fact
                and has_adverse_action_fact
                and has_retaliation_timeline
                and has_causation_link_signal
            ):
                gaps.append({
                    'type': 'retaliation_missing_causation',
                    'suggested_question': (
                        "What happened immediately after your protected activity, who did it, and on what date "
                        "did each step occur?"
                    )
                })
            if not has_causation_link_signal:
                gaps.append({
                    'type': 'retaliation_missing_causation_link',
                    'suggested_question': (
                        "What protected activity did you engage in, who received it, and what adverse treatment "
                        "followed because of that activity, with dates for each event?"
                    ),
                })
            if not (has_protected_activity_date and has_adverse_action_date):
                gaps.append({
                    'type': 'retaliation_missing_sequencing_dates',
                    'suggested_question': (
                        "Please give the exact date of your protected activity and the exact date of each adverse action, "
                        "plus who took each action."
                    ),
                })
        
        return gaps
    
    def merge_with(self, other_graph: 'KnowledgeGraph'):
        """Merge another knowledge graph into this one."""
        for entity in other_graph.entities.values():
            if entity.id not in self.entities:
                self.add_entity(entity)
            else:
                # Update confidence if higher
                existing = self.entities[entity.id]
                if entity.confidence > existing.confidence:
                    existing.confidence = entity.confidence
                    existing.attributes.update(entity.attributes)
        
        for rel in other_graph.relationships.values():
            if rel.id not in self.relationships:
                self.add_relationship(rel)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'metadata': self.metadata,
            'entities': {eid: e.to_dict() for eid, e in self.entities.items()},
            'relationships': {rid: r.to_dict() for rid, r in self.relationships.items()}
        }
    
    def to_json(self, filepath: str):
        """Save to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Knowledge graph saved to {filepath}")
    
    @classmethod
    def from_dict(cls, data: dict) -> 'KnowledgeGraph':
        """Deserialize from dictionary."""
        graph = cls()
        graph.metadata = data['metadata']
        
        for eid, edata in data['entities'].items():
            entity = Entity(**edata)
            graph.entities[eid] = entity
        
        for rid, rdata in data['relationships'].items():
            rel = Relationship(**rdata)
            graph.relationships[rid] = rel
        
        return graph
    
    @classmethod
    def from_json(cls, filepath: str) -> 'KnowledgeGraph':
        """Load from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        logger.info(f"Knowledge graph loaded from {filepath}")
        return cls.from_dict(data)
    
    def _update_metadata(self):
        """Update last_updated timestamp."""
        self.metadata['last_updated'] = _utc_now_isoformat()
    
    def summary(self) -> Dict[str, Any]:
        """Get a summary of the knowledge graph."""
        entity_counts = {}
        for entity in self.entities.values():
            entity_counts[entity.type] = entity_counts.get(entity.type, 0) + 1
        
        rel_counts = {}
        for rel in self.relationships.values():
            rel_counts[rel.relation_type] = rel_counts.get(rel.relation_type, 0) + 1
        
        return {
            'total_entities': len(self.entities),
            'total_relationships': len(self.relationships),
            'entity_types': entity_counts,
            'relationship_types': rel_counts,
            'gaps': len(self.find_gaps())
        }


    # ------------------------------------------------------------------ #
    # Batch 208: Knowledge graph analysis and statistics methods         #
    # ------------------------------------------------------------------ #

    def total_entities(self) -> int:
        """Return total number of entities in the graph.

        Returns:
            Count of entities.
        """
        return len(self.entities)

    def total_relationships(self) -> int:
        """Return total number of relationships in the graph.

        Returns:
            Count of relationships.
        """
        return len(self.relationships)

    def entity_type_distribution(self) -> dict:
        """Calculate frequency distribution of entity types.

        Returns:
            Dict mapping entity types to counts.
        """
        type_counts: dict = {}
        for entity in self.entities.values():
            etype = entity.type
            type_counts[etype] = type_counts.get(etype, 0) + 1
        return type_counts

    def most_common_entity_type(self) -> str:
        """Identify the most common entity type.

        Returns:
            Most frequent entity type, or 'none' if no entities.
        """
        dist = self.entity_type_distribution()
        if not dist:
            return 'none'
        return max(dist.items(), key=lambda x: x[1])[0]

    def relationship_type_distribution(self) -> dict:
        """Calculate frequency distribution of relationship types.

        Returns:
            Dict mapping relationship types to counts.
        """
        type_counts: dict = {}
        for rel in self.relationships.values():
            rtype = rel.relation_type
            type_counts[rtype] = type_counts.get(rtype, 0) + 1
        return type_counts

    def average_confidence(self) -> float:
        """Calculate average confidence across all entities.

        Returns:
            Mean confidence score, or 0.0 if no entities.
        """
        if not self.entities:
            return 0.0
        return sum(e.confidence for e in self.entities.values()) / len(self.entities)

    def low_confidence_entity_count(self, threshold: float = 0.7) -> int:
        """Count entities below confidence threshold.

        Args:
            threshold: Confidence threshold (default: 0.7).

        Returns:
            Number of entities with confidence < threshold.
        """
        return sum(1 for e in self.entities.values() if e.confidence < threshold)

    def isolated_entity_count(self) -> int:
        """Count entities with no relationships.

        Returns:
            Number of entities not involved in any relationships.
        """
        count = 0
        for entity_id in self.entities.keys():
            if len(self.get_relationships_for_entity(entity_id)) == 0:
                count += 1
        return count

    def average_relationships_per_entity(self) -> float:
        """Calculate average number of relationships per entity.

        Returns:
            Mean relationship count, or 0.0 if no entities.
        """
        if not self.entities:
            return 0.0
        total_connections = sum(
            len(self.get_relationships_for_entity(eid))
            for eid in self.entities.keys()
        )
        # Each relationship is counted twice (source and target), so divide by 2
        return (total_connections / 2) / len(self.entities)

    def most_connected_entity(self) -> str:
        """Find entity ID with the most relationships.

        Returns:
            Entity ID with most relationships, or 'none' if no entities.
        """
        if not self.entities:
            return 'none'
        
        connection_counts: dict = {}
        for entity_id in self.entities.keys():
            connection_counts[entity_id] = len(self.get_relationships_for_entity(entity_id))
        
        if not connection_counts:
            return 'none'
        
        return max(connection_counts.items(), key=lambda x: x[1])[0]


class KnowledgeGraphBuilder:
    """
    Builds knowledge graphs from complaint text using LLM extraction.
    
    This builder uses the mediator's LLM backend to extract entities and
    relationships from text, progressively building a knowledge graph.
    """
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.entity_counter = 0
        self.relationship_counter = 0
        
        # Batch 220: Track graph building operations
        self._built_graphs: List[KnowledgeGraph] = []
        self._text_processed_count = 0
    
    def build_from_text(self, text: str) -> KnowledgeGraph:
        """
        Build a knowledge graph from complaint text.
        
        Args:
            text: The complaint text to analyze
            
        Returns:
            A KnowledgeGraph instance
        """
        graph = KnowledgeGraph()
        
        # Extract entities
        entities = self._extract_entities(text)
        for entity_data in entities:
            entity = Entity(
                id=self._get_entity_id(),
                type=entity_data['type'],
                name=entity_data['name'],
                attributes=entity_data.get('attributes', {}),
                confidence=entity_data.get('confidence', 0.8),
                source='complaint'
            )
            graph.add_entity(entity)
        
        # Extract relationships
        relationships = self._extract_relationships(text, graph)
        for rel_data in relationships:
            rel = Relationship(
                id=self._get_relationship_id(),
                source_id=rel_data['source_id'],
                target_id=rel_data['target_id'],
                relation_type=rel_data['type'],
                attributes=rel_data.get('attributes', {}),
                confidence=rel_data.get('confidence', 0.8),
                source='complaint'
            )
            graph.add_relationship(rel)
        
        logger.info(f"Built knowledge graph: {graph.summary()}")
        
        # Batch 220: Track graph building
        self._built_graphs.append(graph)
        self._text_processed_count += 1
        
        return graph
    
    def _extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract entities from text using LLM or rule-based extraction.
        
        This is a simplified implementation. In production, this would use
        the mediator's LLM backend to do sophisticated entity extraction.
        """
        entities = []
        seen: Set[Tuple[str, str]] = set()

        def add_entity(entity: Dict[str, Any]) -> None:
            if not isinstance(entity, dict):
                return
            name = (entity.get("name") or "").strip()
            etype = (entity.get("type") or "").strip()
            if not name or not etype:
                return
            key = (etype.lower(), name.lower())
            if key in seen:
                return
            seen.add(key)
            entities.append(entity)

        def short_description(text_value: str, limit: int = 240) -> str:
            snippet = " ".join((text_value or "").strip().split())
            if len(snippet) > limit:
                return snippet[: limit - 3] + "..."
            return snippet

        lower_text = (text or "").lower()
        employment_context_terms = (
            'employer',
            'job',
            'work',
            'workplace',
            'supervisor',
            'manager',
            'hr',
            'human resources',
            'coworker',
            'company',
            'shift',
            'promotion',
        )
        housing_context_terms = (
            'landlord',
            'tenant',
            'lease',
            'apartment',
            'housing',
            'rent',
            'property manager',
            'property management',
            'evict',
            'unit',
            'section 8',
        )
        
        # For now, use simple keyword-based extraction
        # In production, this would use LLM prompts like:
        # "Extract all people, organizations, dates, locations, and claims from: {text}"
        
        # Extract simple entities (this is a placeholder)
        discrimination_terms = (
            'discrimination',
            'discriminated',
            'discriminatory',
            'harassment',
            'harassed',
        )
        if any(term in lower_text for term in discrimination_terms):
            employment_context = any(term in lower_text for term in employment_context_terms)
            housing_context = any(term in lower_text for term in housing_context_terms)
            if employment_context and not housing_context:
                claim_type = 'employment_discrimination'
                claim_name = 'Employment Discrimination Claim'
            elif housing_context and not employment_context:
                claim_type = 'housing_discrimination'
                claim_name = 'Housing Discrimination Claim'
            else:
                claim_type = 'discrimination'
                claim_name = 'Discrimination Claim'
            add_entity({
                'type': 'claim',
                'name': claim_name,
                'attributes': {
                    'claim_type': claim_type,
                    'description': short_description(text),
                },
                'confidence': 0.9
            })

        if any(term in lower_text for term in ['accommodation', 'accommodate', 'reasonable accommodation']):
            add_entity({
                'type': 'claim',
                'name': 'Accommodation Request',
                'attributes': {
                    'claim_type': 'accommodation',
                    'description': short_description(text),
                },
                'confidence': 0.8
            })

        if any(k in lower_text for k in ['denied', 'refused', 'rejected', 'declined']):
            add_entity({
                'type': 'claim',
                'name': 'Denial/Refusal Claim',
                'attributes': {
                    'claim_type': 'denial',
                    'description': short_description(text),
                },
                'confidence': 0.7
            })

        retaliation_terms = (
            'retaliation',
            'retaliated',
            'retaliatory',
            'retaliat',
        )
        retaliation_context_terms = (
            'complained',
            'reported',
            'grievance',
            'hr',
            'human resources',
            'requested accommodation',
            'whistlebl',
        )
        adverse_action_terms = (
            'fired',
            'terminated',
            'demoted',
            'suspended',
            'cut my hours',
            'reduced my hours',
            'evicted',
            'disciplined',
        )
        if (
            any(term in lower_text for term in retaliation_terms)
            or (
                any(term in lower_text for term in retaliation_context_terms)
                and any(term in lower_text for term in adverse_action_terms)
                and any(term in lower_text for term in ['after', 'because', 'later', 'soon after'])
            )
        ):
            add_entity({
                'type': 'claim',
                'name': 'Retaliation Claim',
                'attributes': {
                    'claim_type': 'retaliation',
                    'description': short_description(text),
                },
                'confidence': 0.85
            })
        
        if 'employer' in lower_text:
            add_entity({
                'type': 'organization',
                'name': 'Employer',
                'attributes': {'role': 'respondent'},
                'confidence': 0.7
            })
        
        if 'employee' in lower_text or 'complainant' in lower_text:
            add_entity({
                'type': 'person',
                'name': 'Complainant',
                'attributes': {'role': 'complainant'},
                'confidence': 0.9
            })

        # Housing/property management role heuristics
        if 'landlord' in lower_text:
            add_entity({
                'type': 'person',
                'name': 'Landlord',
                'attributes': {'role': 'landlord'},
                'confidence': 0.6
            })

        if any(k in lower_text for k in ['property management', 'property manager', 'management company', 'leasing office', 'housing authority', 'housing office']):
            add_entity({
                'type': 'organization',
                'name': 'Property Management',
                'attributes': {'role': 'respondent'},
                'confidence': 0.6
            })

        # Additional heuristic extraction for dates (timeline) and common claims
        date_patterns = [
            r'\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+\d{4}\b',
            r'\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{4}\b',
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
            r'\b\d{4}-\d{2}-\d{2}\b',
            r'\b(?:in|on|since|during|around|by|from)\s+(?:19|20)\d{2}\b',
        ]
        relative_patterns = [
            r'\b(?:today|yesterday|tonight|last night|this morning|this afternoon|this evening)\b',
            r'\b(?:last|this|next)\s+(?:week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
            r'\b\d+\s+(?:day|week|month|year)s?\s+ago\b',
            r'\b(?:a|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:day|week|month|year)s?\s+ago\b',
            r'\b\d+\s+(?:day|week|month|year)s?\s+(?:after|before|later|earlier)\b',
            r'\b(?:a|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:day|week|month|year)s?\s+(?:after|before|later|earlier)\b',
        ]
        found_dates: set[str] = set()
        for pattern in date_patterns:
            for match in re.findall(pattern, text):
                found_dates.add(match.strip())
        for pattern in relative_patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                found_dates.add(match.strip())

        for date_str in found_dates:
            add_entity({
                'type': 'date',
                'name': date_str,
                'attributes': {},
                'confidence': 0.8
            })

        sentence_parts = [
            sentence.strip(" \t\r\n,;:-")
            for sentence in re.split(r'(?<=[.!?])\s+|[\r\n]+', text or '')
            if sentence and sentence.strip()
        ]

        def _extract_event_date_reference(text_value: str) -> Optional[str]:
            for pattern in date_patterns:
                match = re.search(pattern, text_value or '')
                if match:
                    return match.group(0).strip()
            for pattern in relative_patterns:
                match = re.search(pattern, text_value or '', flags=re.IGNORECASE)
                if match:
                    return match.group(0).strip()
            return None

        def add_timeline_event_fact(
            sentence: str,
            *,
            predicate_family: str,
            event_label: str,
            name_prefix: str,
            confidence: float,
        ) -> None:
            description = short_description(sentence)
            attributes: Dict[str, Any] = {
                'fact_type': 'timeline',
                'predicate_family': predicate_family,
                'event_label': event_label,
                'description': description,
            }
            event_date = _extract_event_date_reference(sentence)
            if event_date:
                attributes['event_date_or_range'] = event_date
            add_entity({
                'type': 'fact',
                'name': f"{name_prefix}: {short_description(sentence, 60)}",
                'attributes': attributes,
                'confidence': confidence,
            })

        protected_activity_event_count = 0
        adverse_action_event_count = 0
        causation_event_count = 0
        notice_event_count = 0
        hearing_event_count = 0
        response_event_count = 0
        protected_activity_markers = (
            'complained',
            'complaint',
            'reported',
            'grievance',
            'hr',
            'human resources',
            'requested accommodation',
            'whistlebl',
        )
        notice_sentence_markers = (
            'notice',
            'letter',
            'email',
            'emailed',
            'text',
            'message',
            'voicemail',
            'mailed',
            'sent',
        )
        hearing_sentence_markers = (
            'hearing',
            'appeal',
            'grievance',
            'review',
        )
        hearing_request_markers = (
            'requested',
            'request',
            'asked for',
            'filed',
            'submitted',
            'sought',
        )
        response_sentence_markers = (
            'response',
            'responded',
            'reply',
            'replied',
            'denied',
            'approved',
            'ignored',
            'decision',
            'upheld',
            'rejected',
            'no response',
        )
        causation_markers = (
            'after',
            'because',
            'due to',
            'soon after',
            'in response to',
            'later',
        )
        for sentence in sentence_parts:
            lowered_sentence = sentence.lower()
            has_protected_marker = any(marker in lowered_sentence for marker in protected_activity_markers)
            has_adverse_marker = any(marker in lowered_sentence for marker in adverse_action_terms)
            has_causation_marker = any(marker in lowered_sentence for marker in causation_markers)
            if has_protected_marker:
                add_timeline_event_fact(
                    sentence,
                    predicate_family='protected_activity',
                    event_label='Protected activity',
                    name_prefix='Protected activity event',
                    confidence=0.63,
                )
                protected_activity_event_count += 1
            if has_adverse_marker:
                add_timeline_event_fact(
                    sentence,
                    predicate_family='adverse_action',
                    event_label='Adverse action',
                    name_prefix='Adverse action event',
                    confidence=0.63,
                )
                adverse_action_event_count += 1
            if has_causation_marker and (
                (has_protected_marker and has_adverse_marker)
                or (has_adverse_marker and any(marker in lower_text for marker in protected_activity_markers))
                or (has_protected_marker and any(marker in lower_text for marker in adverse_action_terms))
            ):
                add_timeline_event_fact(
                    sentence,
                    predicate_family='causation',
                    event_label='Causation sequence',
                    name_prefix='Retaliation causation event',
                    confidence=0.64,
                )
                causation_event_count += 1
            if any(marker in lowered_sentence for marker in notice_sentence_markers):
                add_timeline_event_fact(
                    sentence,
                    predicate_family='notice_chain',
                    event_label='Notice communication',
                    name_prefix='Notice event',
                    confidence=0.62,
                )
                notice_event_count += 1
            if any(marker in lowered_sentence for marker in hearing_sentence_markers) and any(
                marker in lowered_sentence for marker in hearing_request_markers
            ):
                add_timeline_event_fact(
                    sentence,
                    predicate_family='hearing_process',
                    event_label='Hearing request event',
                    name_prefix='Hearing request event',
                    confidence=0.64,
                )
                hearing_event_count += 1
            elif any(marker in lowered_sentence for marker in hearing_sentence_markers):
                add_timeline_event_fact(
                    sentence,
                    predicate_family='hearing_process',
                    event_label='Hearing/appeal event',
                    name_prefix='Hearing event',
                    confidence=0.61,
                )
                hearing_event_count += 1
            if any(marker in lowered_sentence for marker in response_sentence_markers):
                add_timeline_event_fact(
                    sentence,
                    predicate_family='response_timeline',
                    event_label='Response event',
                    name_prefix='Response event',
                    confidence=0.63,
                )
                response_event_count += 1

        # Add a termination-related claim if relevant keywords appear
        if 'terminated' in lower_text or 'fired' in lower_text:
            add_entity({
                'type': 'claim',
                'name': 'Termination Claim',
                'attributes': {
                    'claim_type': 'termination',
                    'description': short_description(text),
                },
                'confidence': 0.8
            })

        # Heuristic extraction for organization names
        org_candidates: Set[str] = set()
        org_suffixes = (
            r"(?:Inc\.?|LLC|Ltd\.?|Co\.?|Corp\.?|Corporation|Company|University|"
            r"Hospital|School|Department|Dept\.?|Agency|Clinic|Bank|Foundation|"
            r"Association|Partners|Group|Systems|Services)"
        )
        for match in re.findall(rf"\b([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){{0,4}}\s+{org_suffixes})\b", text or ""):
            org_candidates.add(match.strip())

        for match in re.findall(r"\b(?:at|for|with|from)\s+([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,4})\b", text or ""):
            org_candidates.add(match.strip())

        months = {
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
            "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        }
        banned = {"i", "we", "they", "he", "she", "it", "my", "our", "their", "the", "a", "an"}

        for candidate in sorted(org_candidates):
            cleaned = re.sub(r"[^\w&.\-\s]", "", candidate).strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in banned or lowered in months:
                continue
            tokens = cleaned.split()
            if len(tokens) == 1 and len(cleaned) < 4:
                continue
            add_entity({
                'type': 'organization',
                'name': cleaned,
                'attributes': {'role': 'respondent'},
                'confidence': 0.6
            })

        # Evidence-related entities from common document/communication mentions
        evidence_keywords = {
            'email': 'Email communication',
            'emails': 'Email communication',
            'text message': 'Text messages',
            'texts': 'Text messages',
            'letter': 'Letter',
            'notice': 'Notice',
            'application': 'Application',
            'receipt': 'Receipt',
            'lease': 'Lease',
            'voicemail': 'Voicemail',
            'meeting notes': 'Meeting notes',
            'contract': 'Contract',
            'agreement': 'Agreement',
            'estimate': 'Estimate',
            'invoice': 'Invoice',
            'change order': 'Change order',
            'work order': 'Work order',
            'warranty': 'Warranty',
            'screening criteria': 'Screening criteria',
            'policy': 'Policy',
            'photo': 'Photos',
            'photos': 'Photos',
            'picture': 'Photos',
            'video': 'Video',
            'payment': 'Payment record',
            'check': 'Payment record',
            'bank statement': 'Bank statement',
        }
        for keyword, label in evidence_keywords.items():
            if keyword in lower_text:
                add_entity({
                    'type': 'evidence',
                    'name': label,
                    'attributes': {
                        'evidence_type': label.lower(),
                        'description': short_description(text),
                    },
                    'confidence': 0.55
                })

        impact_keywords = [
            'harm',
            'damages',
            'injury',
            'emotional',
            'stress',
            'anxiety',
            'financial',
            'lost wages',
            'lost pay',
            'missed work',
            'out of pocket',
            'medical',
            'evicted',
            'unsafe',
            'retaliation',
        ]
        if any(k in lower_text for k in impact_keywords):
            add_entity({
                'type': 'fact',
                'name': f"Impact: {short_description(text, 60)}",
                'attributes': {
                    'fact_type': 'impact',
                    'description': short_description(text),
                },
                'confidence': 0.55
            })

        remedy_keywords = [
            'seeking',
            'seek',
            'would like',
            'looking for',
            'request',
            'asking for',
            'refund',
            'reimbursement',
            'compensation',
            'back pay',
            'repair',
            'fix',
            'replacement',
            'apology',
            'policy change',
            'accommodation',
        ]
        if any(k in lower_text for k in remedy_keywords):
            add_entity({
                'type': 'fact',
                'name': f"Requested remedy: {short_description(text, 60)}",
                'attributes': {
                    'fact_type': 'remedy',
                    'description': short_description(text),
                },
                'confidence': 0.55
            })

        if hearing_event_count == 0 and any(token in lower_text for token in ('hearing', 'appeal', 'grievance')):
            add_entity({
                'type': 'fact',
                'name': 'Hearing or appeal process event',
                'attributes': {
                    'fact_type': 'timeline',
                    'predicate_family': 'hearing_process',
                    'event_label': 'Hearing/appeal event',
                    'description': short_description(text),
                },
                'confidence': 0.58,
            })
        if notice_event_count == 0 and any(token in lower_text for token in ('notice', 'letter', 'email', 'message', 'text', 'voicemail')):
            add_entity({
                'type': 'fact',
                'name': 'Written notice or communication event',
                'attributes': {
                    'fact_type': 'timeline',
                    'predicate_family': 'notice_chain',
                    'event_label': 'Notice communication',
                    'description': short_description(text),
                },
                'confidence': 0.58,
            })
        if response_event_count == 0 and any(token in lower_text for token in ('response', 'responded', 'replied', 'denied', 'approved', 'ignored', 'no response')):
            add_entity({
                'type': 'fact',
                'name': 'Agency/employer response event',
                'attributes': {
                    'fact_type': 'timeline',
                    'predicate_family': 'response_timeline',
                    'event_label': 'Response event',
                    'description': short_description(text),
                },
                'confidence': 0.58,
            })
        if protected_activity_event_count == 0 and any(term in lower_text for term in retaliation_context_terms):
            add_entity({
                'type': 'fact',
                'name': 'Protected activity event',
                'attributes': {
                    'fact_type': 'timeline',
                    'predicate_family': 'protected_activity',
                    'event_label': 'Protected activity',
                    'description': short_description(text),
                },
                'confidence': 0.6,
            })
        if adverse_action_event_count == 0 and any(term in lower_text for term in adverse_action_terms):
            add_entity({
                'type': 'fact',
                'name': 'Adverse action event',
                'attributes': {
                    'fact_type': 'timeline',
                    'predicate_family': 'adverse_action',
                    'event_label': 'Adverse action',
                    'description': short_description(text),
                },
                'confidence': 0.6,
            })
        if causation_event_count == 0 and any(token in lower_text for token in ('after', 'because', 'due to', 'soon after', 'in response to', 'later')):
            add_entity({
                'type': 'fact',
                'name': 'Retaliation causation link',
                'attributes': {
                    'fact_type': 'timeline',
                    'predicate_family': 'causation',
                    'event_label': 'Causation sequence',
                    'description': short_description(text),
                },
                'confidence': 0.6,
            })

        # If we still don't have any organization, add a generic employer when text implies one.
        has_org = any(e.get("type") == "organization" for e in entities if isinstance(e, dict))
        if not has_org and any(k in lower_text for k in ["company", "workplace", "organization", "business", "agency", "department", "school", "university", "hospital", "clinic"]):
            add_entity({
                'type': 'organization',
                'name': 'Organization',
                'attributes': {'role': 'respondent'},
                'confidence': 0.5
            })

        # Heuristic extraction for named individuals in role contexts
        role_keywords = (
            r"manager|supervisor|boss|coworker|co-worker|hr|human resources|director|"
            r"owner|principal|teacher|professor|doctor|nurse|attorney|lawyer|agent|"
            r"officer|landlord|neighbor|representative"
        )
        for match in re.finditer(
            rf"\b(?:my|the|a|an)\s+(?P<role>{role_keywords})\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}})(?=\s+(?:denied|approved|replied|responded|emailed|called|told|said|was|is|did)\b|[.,;]|$)",
            text or "",
            re.IGNORECASE
        ):
            role = (match.group("role") or "").strip().lower()
            name = (match.group("name") or "").strip()
            if name and all(part[:1].isupper() for part in name.split() if part):
                add_entity({
                    'type': 'person',
                    'name': name,
                    'attributes': {'role': role},
                    'confidence': 0.7
                })

        expanded_title_keywords = (
            r"regional manager|property manager|case manager|program manager|leasing manager|"
            r"hearing officer|appeals officer|hr manager|human resources manager|director|"
            r"assistant director|supervisor|coordinator|specialist|officer|landlord|owner"
        )
        for match in re.finditer(
            rf"\b(?P<title>{expanded_title_keywords})\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,2}})(?=\s+(?:denied|approved|replied|responded|emailed|called|told|said|was|is|did)\b|[.,;]|$)",
            text or "",
            re.IGNORECASE,
        ):
            title = (match.group("title") or "").strip().lower()
            name = (match.group("name") or "").strip()
            if not name or not title or not all(part[:1].isupper() for part in name.split() if part):
                continue
            add_entity({
                'type': 'person',
                'name': name,
                'attributes': {'role': title},
                'confidence': 0.74,
            })

        for match in re.finditer(
            rf"\b(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,2}})\s+(?:was|is|served as|acted as|worked as)\s+(?:the\s+)?(?P<title>{expanded_title_keywords})\b",
            text or "",
            re.IGNORECASE,
        ):
            name = (match.group("name") or "").strip()
            title = (match.group("title") or "").strip().lower()
            if not name or not title or not all(part[:1].isupper() for part in name.split() if part):
                continue
            add_entity({
                'type': 'person',
                'name': name,
                'attributes': {'role': title},
                'confidence': 0.72,
            })

        for match in re.finditer(
            r"\b(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*,\s*(?P<title>[A-Za-z][A-Za-z\s/&-]{2,60})\b",
            text or "",
        ):
            name = (match.group("name") or "").strip()
            title = (match.group("title") or "").strip().lower()
            if not name or not title:
                continue
            add_entity({
                'type': 'person',
                'name': name,
                'attributes': {'role': title},
                'confidence': 0.68
            })

        # Use LLM if available
        if self.mediator:
            llm_entities = self._llm_extract_entities(text)
            for ent in llm_entities:
                if isinstance(ent, dict):
                    add_entity(ent)

        # Fallback: ensure we have at least one claim to drive downstream graphs.
        # Many parts of the pipeline (dependency graph, denoiser questions) assume
        # there's at least one claim-like entity.
        has_claim = any(e.get("type") == "claim" for e in entities if isinstance(e, dict))
        if not has_claim:
            description = short_description(text)
            add_entity(
                {
                    "type": "claim",
                    "name": "Complaint Claim",
                    "attributes": {
                        "claim_type": "unknown",
                        "description": description,
                    },
                    "confidence": 0.5,
                }
            )
        
        return entities
    
    def _extract_relationships(self, text: str, graph: KnowledgeGraph) -> List[Dict[str, Any]]:
        """
        Extract relationships between entities.
        
        This is a simplified implementation. In production, this would use
        the mediator's LLM backend.
        """
        relationships = []
        
        # Find entities to relate
        persons = graph.get_entities_by_type('person')
        orgs = graph.get_entities_by_type('organization')
        claims = graph.get_entities_by_type('claim')
        
        # Create employment relationships
        for person in persons:
            for org in orgs:
                if (
                    'employer' in org.name.lower()
                    or org.attributes.get('role') == 'respondent'
                ):
                    relationships.append({
                        'source_id': person.id,
                        'target_id': org.id,
                        'type': 'employed_by',
                        'confidence': 0.7
                    })
        
        # Link claims to complainants
        for claim in claims:
            for person in persons:
                if 'complainant' in person.attributes.get('role', '').lower():
                    relationships.append({
                        'source_id': person.id,
                        'target_id': claim.id,
                        'type': 'makes_claim',
                        'confidence': 0.9
                    })

        # Link claims to respondent organizations when unambiguous
        if claims and orgs:
            if len(claims) == 1:
                claim = claims[0]
                for org in orgs:
                    relationships.append({
                        'source_id': claim.id,
                        'target_id': org.id,
                        'type': 'involves',
                        'confidence': 0.6
                    })
            elif len(orgs) == 1:
                org = orgs[0]
                for claim in claims:
                    relationships.append({
                        'source_id': claim.id,
                        'target_id': org.id,
                        'type': 'involves',
                        'confidence': 0.6
                    })

        # Link claims to respondent-role people when unambiguous
        respondent_roles = {'manager', 'supervisor', 'boss', 'owner', 'landlord', 'hr', 'human resources'}
        respondent_people = [
            person for person in persons
            if person.attributes.get('role', '').lower() in respondent_roles
        ]
        if claims and respondent_people:
            if len(claims) == 1:
                claim = claims[0]
                for person in respondent_people:
                    relationships.append({
                        'source_id': claim.id,
                        'target_id': person.id,
                        'type': 'involves',
                        'confidence': 0.6
                    })
            elif len(respondent_people) == 1:
                person = respondent_people[0]
                for claim in claims:
                    relationships.append({
                        'source_id': claim.id,
                        'target_id': person.id,
                        'type': 'involves',
                        'confidence': 0.6
                    })
        
        # Link claims to extracted dates to build a timeline
        dates = graph.get_entities_by_type('date')
        for claim in claims:
            for date_ent in dates:
                relationships.append({
                    'source_id': claim.id,
                    'target_id': date_ent.id,
                    'type': 'occurred_on',
                    'confidence': 0.6
                })

        # Add explicit causation/sequencing links for retaliation contexts.
        retaliation_claims = [
            claim for claim in claims
            if str((claim.attributes or {}).get('claim_type') or '').strip().lower() == 'retaliation'
        ]
        if retaliation_claims:
            fact_entities = graph.get_entities_by_type('fact')
            protected_activity_facts = [
                fact for fact in fact_entities
                if str((fact.attributes or {}).get('predicate_family') or '').strip().lower() == 'protected_activity'
            ]
            adverse_action_facts = [
                fact for fact in fact_entities
                if str((fact.attributes or {}).get('predicate_family') or '').strip().lower() == 'adverse_action'
            ]
            for protected_fact in protected_activity_facts:
                for adverse_fact in adverse_action_facts:
                    relationships.append({
                        'source_id': adverse_fact.id,
                        'target_id': protected_fact.id,
                        'type': 'follows_protected_activity',
                        'confidence': 0.55,
                    })
                    relationships.append({
                        'source_id': adverse_fact.id,
                        'target_id': protected_fact.id,
                        'type': 'occurred_after',
                        'confidence': 0.52,
                    })
            if any(token in (text or '').lower() for token in ('because', 'due to', 'in response to', 'soon after', 'after')):
                for claim in retaliation_claims:
                    for fact in protected_activity_facts + adverse_action_facts:
                        relationships.append({
                            'source_id': claim.id,
                            'target_id': fact.id,
                            'type': 'causal_link',
                            'confidence': 0.5,
                        })

        # Link claims to evidence entities when unambiguous
        evidence_entities = graph.get_entities_by_type('evidence')
        if claims and evidence_entities:
            if len(claims) == 1:
                claim = claims[0]
                for evidence in evidence_entities:
                    relationships.append({
                        'source_id': claim.id,
                        'target_id': evidence.id,
                        'type': 'supported_by',
                        'confidence': 0.55
                    })
            elif len(evidence_entities) == 1:
                evidence = evidence_entities[0]
                for claim in claims:
                    relationships.append({
                        'source_id': claim.id,
                        'target_id': evidence.id,
                        'type': 'supported_by',
                        'confidence': 0.55
                    })

        # Link evidence to a single respondent party when unambiguous.
        respondent_orgs = [
            org for org in orgs
            if org.attributes.get('role') == 'respondent' or 'employer' in org.name.lower()
        ]
        if evidence_entities:
            if len(respondent_orgs) == 1:
                org = respondent_orgs[0]
                for evidence in evidence_entities:
                    relationships.append({
                        'source_id': evidence.id,
                        'target_id': org.id,
                        'type': 'associated_with',
                        'confidence': 0.5
                    })
            elif len(respondent_people) == 1:
                person = respondent_people[0]
                for evidence in evidence_entities:
                    relationships.append({
                        'source_id': evidence.id,
                        'target_id': person.id,
                        'type': 'associated_with',
                        'confidence': 0.5
                    })

        # Add a communication edge when evidence suggests contact and parties are clear.
        complainants = [
            person for person in persons
            if 'complainant' in person.attributes.get('role', '').lower()
        ]
        if evidence_entities and complainants:
            if len(respondent_orgs) == 1:
                org = respondent_orgs[0]
                for complainant in complainants:
                    relationships.append({
                        'source_id': complainant.id,
                        'target_id': org.id,
                        'type': 'communicated_with',
                        'confidence': 0.55
                    })
            elif len(respondent_people) == 1:
                person = respondent_people[0]
                for complainant in complainants:
                    relationships.append({
                        'source_id': complainant.id,
                        'target_id': person.id,
                        'type': 'communicated_with',
                        'confidence': 0.55
                    })

        # Use LLM if available
        if self.mediator:
            llm_rels = self._llm_extract_relationships(text, graph)
            for rel in llm_rels:
                if not isinstance(rel, dict):
                    continue
                if rel.get('source_id') and rel.get('target_id') and rel.get('type'):
                    relationships.append(rel)
        
        unique_relationships = {}
        for rel in relationships:
            key = (rel.get('source_id'), rel.get('target_id'), rel.get('type'))
            if not all(key):
                continue
            current = unique_relationships.get(key)
            if current is None or rel.get('confidence', 0.0) > current.get('confidence', 0.0):
                unique_relationships[key] = rel

        return list(unique_relationships.values())
    
    def _llm_extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """Use LLM to extract entities (placeholder for LLM integration)."""
        # TODO: Implement LLM-based extraction
        return []
    
    def _llm_extract_relationships(self, text: str, graph: KnowledgeGraph) -> List[Dict[str, Any]]:
        """Use LLM to extract relationships (placeholder for LLM integration).

        IMPORTANT: This method must not call back into `_extract_relationships`,
        because `_extract_relationships` already calls this method when a
        mediator is present.
        """
        # TODO: Implement LLM-based extraction
        return []
    
    def _get_entity_id(self) -> str:
        """Generate unique entity ID."""
        self.entity_counter += 1
        return f"entity_{self.entity_counter}"
    
    def _get_relationship_id(self) -> str:
        """Generate unique relationship ID."""
        self.relationship_counter += 1
        return f"rel_{self.relationship_counter}"


    # =====================================================================
    # Batch 220: Graph building analytics methods
    # =====================================================================
    
    def total_graphs_built(self) -> int:
        """Return total number of knowledge graphs built.
        
        Returns:
            Count of graphs in _built_graphs.
        """
        return len(self._built_graphs)
    
    def total_texts_processed(self) -> int:
        """Return total number of texts processed.
        
        Returns:
            Count of build_from_text calls.
        """
        return self._text_processed_count
    
    def average_entities_per_graph(self) -> float:
        """Calculate average number of entities per graph.
        
        Returns:
            Mean entity count, or 0.0 if no graphs.
        """
        if not self._built_graphs:
            return 0.0
        total = sum(g.total_entities() for g in self._built_graphs)
        return total / len(self._built_graphs)
    
    def average_relationships_per_graph(self) -> float:
        """Calculate average number of relationships per graph.
        
        Returns:
            Mean relationship count, or 0.0 if no graphs.
        """
        if not self._built_graphs:
            return 0.0
        total = sum(g.total_relationships() for g in self._built_graphs)
        return total / len(self._built_graphs)
    
    def maximum_entities_in_graph(self) -> int:
        """Find maximum number of entities in any graph.
        
        Returns:
            Max entity count, or 0 if no graphs.
        """
        if not self._built_graphs:
            return 0
        return max(g.total_entities() for g in self._built_graphs)
    
    def maximum_relationships_in_graph(self) -> int:
        """Find maximum number of relationships in any graph.
        
        Returns:
            Max relationship count, or 0 if no graphs.
        """
        if not self._built_graphs:
            return 0
        return max(g.total_relationships() for g in self._built_graphs)
    
    def total_entities_extracted(self) -> int:
        """Sum total entities across all built graphs.
        
        Returns:
            Total entity count.
        """
        return sum(g.total_entities() for g in self._built_graphs)
    
    def total_relationships_extracted(self) -> int:
        """Sum total relationships across all built graphs.
        
        Returns:
            Total relationship count.
        """
        return sum(g.total_relationships() for g in self._built_graphs)
    
    def entity_extraction_rate(self) -> float:
        """Calculate average entities extracted per text.
        
        Returns:
            Entities per text, or 0.0 if no texts processed.
        """
        if self._text_processed_count == 0:
            return 0.0
        return self.total_entities_extracted() / self._text_processed_count
    
    def relationship_extraction_rate(self) -> float:
        """Calculate average relationships extracted per text.
        
        Returns:
            Relationships per text, or 0.0 if no texts processed.
        """
        if self._text_processed_count == 0:
            return 0.0
        return self.total_relationships_extracted() / self._text_processed_count
