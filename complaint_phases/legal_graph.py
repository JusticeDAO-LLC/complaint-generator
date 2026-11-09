"""
Legal Graph Builder

Creates graph representations of legal requirements, statutes, and rules
to enable neurosymbolic matching against complaint graphs.
"""

import json
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class LegalElement:
    """Represents a legal element or requirement."""
    id: str
    element_type: str  # statute, regulation, case_law, element, requirement
    name: str
    description: str = ""
    citation: str = ""
    jurisdiction: str = ""
    required: bool = True
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LegalRelation:
    """Represents a relationship between legal elements."""
    id: str
    source_id: str
    target_id: str
    relation_type: str  # requires, implies, contradicts, supersedes, cites
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


class LegalGraph:
    """
    Graph representation of legal requirements and their relationships.
    
    Stores legal elements (statutes, regulations, requirements) and their
    relationships to enable matching against complaint facts.
    """
    
    def __init__(self):
        self.elements: Dict[str, LegalElement] = {}
        self.relations: Dict[str, LegalRelation] = {}
        self.metadata = {
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'version': '1.0'
        }
    
    def add_element(self, element: LegalElement) -> str:
        """Add a legal element to the graph."""
        self.elements[element.id] = element
        self._update_metadata()
        return element.id
    
    def add_relation(self, relation: LegalRelation) -> str:
        """Add a legal relation to the graph."""
        self.relations[relation.id] = relation
        self._update_metadata()
        return relation.id
    
    def get_element(self, element_id: str) -> Optional[LegalElement]:
        """Get a legal element by ID."""
        return self.elements.get(element_id)
    
    def get_relations_for_element(self, element_id: str) -> List[LegalRelation]:
        """Get all relations involving an element."""
        return [
            rel for rel in self.relations.values()
            if rel.source_id == element_id or rel.target_id == element_id
        ]
    
    def get_elements_by_type(self, element_type: str) -> List[LegalElement]:
        """Get all elements of a specific type."""
        return [e for e in self.elements.values() if e.element_type == element_type]
    
    def get_requirements_for_claim_type(self, claim_type: str) -> List[LegalElement]:
        """
        Get all legal requirements for a specific claim type.
        
        Args:
            claim_type: Type of legal claim (e.g., 'discrimination', 'wrongful_termination')
            
        Returns:
            List of required legal elements (both 'requirement' and 'procedural_requirement')
        """
        requirements = []
        
        # Find elements tagged with this claim type
        # Include both regular requirements and procedural requirements
        from integrations.ipfs_datasets.logic import is_applicable_legal_requirement

        for element in self.elements.values():
            if element.element_type in ('requirement', 'procedural_requirement', 'legal_requirement'):
                if not is_applicable_legal_requirement(element.attributes):
                    continue
                applicable_claims = element.attributes.get('applicable_claim_types', [])
                if claim_type in applicable_claims:
                    requirements.append(element)
        
        return requirements
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'metadata': self.metadata,
            'elements': {eid: e.to_dict() for eid, e in self.elements.items()},
            'relations': {rid: r.to_dict() for rid, r in self.relations.items()}
        }
    
    def to_json(self, filepath: str):
        """Save to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Legal graph saved to {filepath}")
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LegalGraph':
        """Deserialize from dictionary."""
        graph = cls()
        graph.metadata = data['metadata']
        
        for eid, edata in data['elements'].items():
            element = LegalElement(**edata)
            graph.elements[eid] = element
        
        for rid, rdata in data['relations'].items():
            rel = LegalRelation(**rdata)
            graph.relations[rid] = rel
        
        return graph
    
    @classmethod
    def from_json(cls, filepath: str) -> 'LegalGraph':
        """Load from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        logger.info(f"Legal graph loaded from {filepath}")
        return cls.from_dict(data)
    
    def _update_metadata(self):
        """Update last_updated timestamp."""
        self.metadata['last_updated'] = datetime.now(timezone.utc).isoformat()
    
    def summary(self) -> Dict[str, Any]:
        """Get a summary of the legal graph."""
        element_counts = {}
        for element in self.elements.values():
            element_counts[element.element_type] = element_counts.get(element.element_type, 0) + 1
        
        rel_counts = {}
        for rel in self.relations.values():
            rel_counts[rel.relation_type] = rel_counts.get(rel.relation_type, 0) + 1
        
        return {
            'total_elements': len(self.elements),
            'total_relations': len(self.relations),
            'element_types': element_counts,
            'relation_types': rel_counts
        }


    # ------------------------------------------------------------------ #
    # Batch 207: Legal graph analysis and statistics methods             #
    # ------------------------------------------------------------------ #

    def total_elements(self) -> int:
        """Return total number of legal elements in the graph.

        Returns:
            Count of elements.
        """
        return len(self.elements)

    def total_relations(self) -> int:
        """Return total number of legal relations in the graph.

        Returns:
            Count of relations.
        """
        return len(self.relations)

    def element_type_frequency(self) -> dict:
        """Count frequency of each element type.

        Returns:
            Dict mapping element types to counts.
        """
        type_counts: dict = {}
        for element in self.elements.values():
            etype = element.element_type
            type_counts[etype] = type_counts.get(etype, 0) + 1
        return type_counts

    def most_common_element_type(self) -> str:
        """Identify the most common element type.

        Returns:
            Most frequent element type, or 'none' if no elements.
        """
        freq = self.element_type_frequency()
        if not freq:
            return 'none'
        return max(freq.items(), key=lambda x: x[1])[0]

    def relation_type_frequency(self) -> dict:
        """Count frequency of each relation type.

        Returns:
            Dict mapping relation types to counts.
        """
        type_counts: dict = {}
        for relation in self.relations.values():
            rtype = relation.relation_type
            type_counts[rtype] = type_counts.get(rtype, 0) + 1
        return type_counts

    def most_connected_element(self) -> str:
        """Find element ID with the most relations.

        Returns:
            Element ID with most relations, or 'none' if no elements.
        """
        if not self.elements:
            return 'none'
        
        connection_counts: dict = {}
        for element_id in self.elements.keys():
            connection_counts[element_id] = len(self.get_relations_for_element(element_id))
        
        if not connection_counts:
            return 'none'
        
        return max(connection_counts.items(), key=lambda x: x[1])[0]

    def average_relations_per_element(self) -> float:
        """Calculate average number of relations per element.

        Returns:
            Mean relation count, or 0.0 if no elements.
        """
        if not self.elements:
            return 0.0
        total_connections = sum(
            len(self.get_relations_for_element(eid))
            for eid in self.elements.keys()
        )
        # Each relation is counted twice (source and target), so divide by 2
        return (total_connections / 2) / len(self.elements)

    def requirements_coverage(self) -> dict:
        """Analyze requirement coverage across claim types.

        Returns:
            Dict with 'total_requirements', 'claim_types_covered', 'avg_requirements_per_claim'.
        """
        requirements = [e for e in self.elements.values() 
                       if e.element_type in ('requirement', 'procedural_requirement', 'legal_requirement')]
        
        claim_types_with_reqs: set = set()
        for req in requirements:
            applicable_claims = req.attributes.get('applicable_claim_types', [])
            claim_types_with_reqs.update(applicable_claims)
        
        avg_per_claim = 0.0
        if claim_types_with_reqs:
            total_req_mappings = sum(
                len(req.attributes.get('applicable_claim_types', []))
                for req in requirements
            )
            avg_per_claim = total_req_mappings / len(claim_types_with_reqs)
        
        return {
            'total_requirements': len(requirements),
            'claim_types_covered': len(claim_types_with_reqs),
            'avg_requirements_per_claim': avg_per_claim
        }

    def elements_with_citations(self) -> int:
        """Count elements that have citation information.

        Returns:
            Number of elements with non-empty citation field.
        """
        return sum(
            1 for element in self.elements.values()
            if element.citation and len(element.citation) > 0
        )

    def graph_density(self) -> float:
        """Calculate graph density (ratio of existing to possible relations).

        Returns:
            Density ratio (0.0-1.0), or 0.0 if fewer than 2 elements.
        """
        n = len(self.elements)
        if n < 2:
            return 0.0
        
        max_possible_relations = n * (n - 1) / 2  # Undirected graph
        actual_relations = len(self.relations)
        
        return actual_relations / max_possible_relations


    # ------------------------------------------------------------------ #
    # Batch 222: Legal graph analysis and statistics methods             #
    # ------------------------------------------------------------------ #

    def element_jurisdiction_frequency(self) -> dict:
        """Count frequency of elements by jurisdiction.

        Returns:
            Dict mapping jurisdiction to element counts.
        """
        counts: dict = {}
        for element in self.elements.values():
            jurisdiction = element.jurisdiction or ""
            counts[jurisdiction] = counts.get(jurisdiction, 0) + 1
        return counts

    def required_elements_count(self) -> int:
        """Count required elements in the graph.

        Returns:
            Number of elements marked as required.
        """
        return sum(1 for element in self.elements.values() if element.required)

    def optional_elements_count(self) -> int:
        """Count optional (non-required) elements in the graph.

        Returns:
            Number of elements marked as optional.
        """
        return sum(1 for element in self.elements.values() if not element.required)

    def elements_with_attributes_count(self) -> int:
        """Count elements that have non-empty attributes.

        Returns:
            Number of elements with attributes.
        """
        return sum(1 for element in self.elements.values() if element.attributes)

    def elements_missing_citation_count(self) -> int:
        """Count elements missing citation information.

        Returns:
            Number of elements with empty citation fields.
        """
        return sum(1 for element in self.elements.values() if not element.citation)

    def relation_type_set(self) -> List[str]:
        """Return sorted list of unique relation types.

        Returns:
            Sorted list of relation type strings.
        """
        return sorted({rel.relation_type for rel in self.relations.values()})

    def average_elements_per_type(self) -> float:
        """Calculate average number of elements per element type.

        Returns:
            Mean elements per type, or 0.0 if no elements.
        """
        if not self.elements:
            return 0.0
        type_counts = self.element_type_frequency()
        if not type_counts:
            return 0.0
        return len(self.elements) / len(type_counts)

    def elements_by_jurisdiction(self, jurisdiction: str) -> List[LegalElement]:
        """Get elements that match a jurisdiction string.

        Args:
            jurisdiction: Jurisdiction value to match

        Returns:
            List of matching legal elements.
        """
        return [
            element for element in self.elements.values()
            if element.jurisdiction == jurisdiction
        ]

    def relation_count_for_element(self, element_id: str) -> int:
        """Count relations involving a specific element.

        Args:
            element_id: Element identifier

        Returns:
            Number of relations involving the element.
        """
        return len(self.get_relations_for_element(element_id))

    def claim_type_requirement_counts(self) -> dict:
        """Count requirements per claim type.

        Returns:
            Dict mapping claim type to requirement counts.
        """
        counts: dict = {}
        for element in self.elements.values():
            if element.element_type not in ('requirement', 'procedural_requirement', 'legal_requirement'):
                continue
            claim_types = element.attributes.get('applicable_claim_types', [])
            for claim_type in claim_types:
                counts[claim_type] = counts.get(claim_type, 0) + 1
        return counts


class LegalGraphBuilder:
    """
    Builds legal requirement graphs from statutes, regulations, and case law.
    
    Creates structured graph representations of legal requirements that can
    be matched against complaint facts.
    """
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.element_counter = 0
        self.relation_counter = 0
    
    def build_from_statutes(self, statutes: List[Dict[str, Any]],
                           claim_types: List[str]) -> LegalGraph:
        """
        Build a legal graph from statutes and claim types.
        
        Args:
            statutes: List of statute dictionaries
            claim_types: List of claim types these statutes apply to
            
        Returns:
            A LegalGraph instance
        """
        graph = LegalGraph()
        
        # Add statutes as elements
        statute_elements = []
        for statute in statutes:
            statute_attributes = {
                'text': statute.get('text', ''),
                'source_text': statute.get('source_text', '') or statute.get('text', ''),
            }
            for key in (
                'authority_id', 'authority_version', 'version', 'source_hash', 'content_hash',
                'content_hash_scope', 'effective_date', 'as_of_date', 'applicable_date', 'expiration_date',
                'sunset_date', 'repeal_date', 'superseded_date', 'law_versions', 'changes',
                'query_context', 'temporal_query_context', 'authority_treatment_edges',
                'treatment_records', 'treatment_summary',
            ):
                if key in statute:
                    statute_attributes[key] = statute.get(key)
            element = LegalElement(
                id=self._get_element_id(),
                element_type='statute',
                name=statute.get('name', 'Unnamed Statute'),
                description=statute.get('description', ''),
                citation=statute.get('citation', ''),
                jurisdiction=(statute.get('jurisdiction')
                              if isinstance(statute.get('jurisdiction'), str) else ''),
                attributes=statute_attributes,
            )
            graph.add_element(element)
            statute_elements.append(element)
        
        # Extract requirements from statutes
        for statute_elem in statute_elements:
            requirements = self._extract_requirements_from_statute(statute_elem, claim_types)
            
            for req_data in requirements:
                element_type = str(req_data.get('element_type') or 'legal_requirement')
                record_kind = 'rule_candidate' if element_type == 'rule_candidate' else 'legal_requirement'
                attributes = {
                    'applicable_claim_types': claim_types,
                    'source_statute': statute_elem.id,
                    'record_kind': record_kind,
                    'about_complainant': False,
                }
                extra = req_data.get('attributes') if isinstance(req_data.get('attributes'), dict) else {}
                attributes.update(extra)
                for key in (
                    'verification_status', 'promotion_status', 'applicable', 'legacy_template',
                    'template_kind', 'review_reason', 'review_reasons', 'source_bound',
                    'source_span', 'source_hash', 'authority_id', 'authority_identity',
                    'authority_version', 'jurisdiction', 'applicable_date', 'structure',
                    'rule_character', 'promoted', 'span_sha256', 'authority_text_sha256',
                    'temporal_applicability', 'support_eligible', 'treatment_blocks_support',
                    'treatment_edges', 'blocking_treatments',
                ):
                    if key in req_data:
                        attributes[key] = req_data[key]
                req_element = LegalElement(
                    id=self._get_element_id(element_type if element_type == 'rule_candidate' else 'legal_requirement', {
                        'statute': {key: value for key, value in statute_elem.to_dict().items() if key != 'id'}, 'requirement': req_data,
                        'claim_types': sorted(claim_types),
                    }),
                    element_type=element_type,
                    name=req_data['name'],
                    description=req_data.get('description', ''),
                    citation=req_data.get('citation') or statute_elem.citation,
                    jurisdiction=str(req_data.get('jurisdiction') or statute_elem.jurisdiction or ''),
                    required=req_data.get('required', True),
                    attributes=attributes,
                )
                graph.add_element(req_element)
                
                # Create relation: statute provides requirement
                rel = LegalRelation(
                    id=self._get_relation_id(),
                    source_id=statute_elem.id,
                    target_id=req_element.id,
                    relation_type='provides'
                )
                graph.add_relation(rel)
        
        logger.info(f"Built legal graph: {graph.summary()}")
        return graph
    
    def build_rules_of_procedure(self, jurisdiction: str = 'federal') -> LegalGraph:
        """
        Build a legal graph for rules of civil procedure.
        
        Args:
            jurisdiction: 'federal' or specific state
            
        Returns:
            A LegalGraph with procedural requirements
        """
        graph = LegalGraph()
        
        # Common procedural requirements (simplified)
        procedural_reqs = [
            {
                'name': 'Statement of Jurisdiction',
                'description': 'Must state the basis for the court\'s jurisdiction',
                'rule': 'FRCP 8(a)(1)'
            },
            {
                'name': 'Statement of Claim',
                'description': 'Must contain a short and plain statement of the claim showing entitlement to relief',
                'rule': 'FRCP 8(a)(2)'
            },
            {
                'name': 'Demand for Relief',
                'description': 'Must state the relief sought',
                'rule': 'FRCP 8(a)(3)'
            },
            {
                'name': 'Plausible Claim',
                'description': 'Facts must plausibly suggest entitlement to relief',
                'rule': 'Twombly/Iqbal Standard'
            }
        ]
        
        for req_data in procedural_reqs:
            element = LegalElement(
                id=self._get_element_id('legal_requirement', {'jurisdiction': jurisdiction, 'requirement': req_data}),
                element_type='procedural_requirement',
                name=req_data['name'],
                description=req_data['description'],
                citation=req_data['rule'],
                jurisdiction=jurisdiction,
                required=True,
                attributes=self._unverified_procedural_attributes()
            )
            graph.add_element(element)
        
        logger.info(f"Built procedural rules graph: {graph.summary()}")
        return graph
    
    def _unverified_procedural_attributes(self) -> Dict[str, Any]:
        from integrations.ipfs_datasets.logic import legacy_procedural_template_attributes
        return legacy_procedural_template_attributes()

    def _extract_requirements_from_statute(self, statute: LegalElement,
                                          claim_types: List[str]) -> List[Dict[str, Any]]:
        """Extract source-bound candidates and keep keyword templates unverified.

        Statute text yields candidates linked to exact UTF-8 spans. A candidate
        becomes a legal requirement only when promotion retains jurisdiction,
        authority identity/version, source hash, span, and applicable date.
        Claim-keyword templates stay explicit unverified templates.
        """
        from integrations.ipfs_datasets.logic import (
            extract_source_bound_rule_candidates,
            legacy_unverified_requirement_templates,
        )

        requirements: List[Dict[str, Any]] = []
        source_text = statute.attributes.get('source_text')
        if not isinstance(source_text, str) or source_text == '':
            source_text = statute.attributes.get('text') if isinstance(statute.attributes.get('text'), str) else ''
        if source_text:
            authority = {
                'source_text': source_text,
                'jurisdiction': statute.jurisdiction,
                'citation': statute.citation,
                'authority_id': statute.attributes.get('authority_id') or statute.citation,
                'authority_version': statute.attributes.get('authority_version') or statute.attributes.get('version') or '',
                'source_hash': statute.attributes.get('source_hash') or statute.attributes.get('content_hash') or '',
                'content_hash_scope': statute.attributes.get('content_hash_scope') or '',
                'effective_date': statute.attributes.get('effective_date') or '',
                'as_of_date': statute.attributes.get('as_of_date') or statute.attributes.get('applicable_date') or '',
                'expiration_date': statute.attributes.get('expiration_date') or '',
                'sunset_date': statute.attributes.get('sunset_date') or '',
                'repeal_date': statute.attributes.get('repeal_date') or '',
                'superseded_date': statute.attributes.get('superseded_date') or '',
                'law_versions': statute.attributes.get('law_versions') or [],
                'changes': statute.attributes.get('changes') or [],
                'query_context': statute.attributes.get('query_context') or statute.attributes.get('temporal_query_context') or {},
                'authority_treatment_edges': statute.attributes.get('authority_treatment_edges') or [],
                'treatment_records': statute.attributes.get('treatment_records') or [],
                'treatment_summary': statute.attributes.get('treatment_summary') or {},
            }
            extracted = extract_source_bound_rule_candidates(authority)
            for candidate in extracted['candidates']:
                promoted = bool(candidate.get('promoted'))
                requirements.append({
                    'name': (candidate.get('rule_text') or 'unparsed authority text')[:self._MAX_RULE_NAME_LENGTH],
                    'description': candidate.get('rule_text') or '',
                    'required': True,
                    'element_type': 'legal_requirement' if promoted else 'rule_candidate',
                    'citation': candidate.get('citation') or statute.citation,
                    'jurisdiction': candidate.get('jurisdiction') or statute.jurisdiction,
                    'verification_status': candidate.get('verification_status'),
                    'promotion_status': candidate.get('promotion_status'),
                    'applicable': candidate.get('applicable'),
                    'legacy_template': False,
                    'review_reason': candidate.get('review_reason') or '',
                    'review_reasons': list(candidate.get('review_reasons') or []),
                    'source_bound': True,
                    'source_span': candidate.get('source_span'),
                    'source_hash': candidate.get('source_hash'),
                    'authority_id': candidate.get('authority_id'),
                    'authority_identity': candidate.get('authority_identity'),
                    'authority_version': candidate.get('authority_version'),
                    'applicable_date': candidate.get('applicable_date'),
                    'structure': candidate.get('structure'),
                    'rule_character': candidate.get('rule_character'),
                    'promoted': promoted,
                    'span_sha256': candidate.get('span_sha256'),
                    'authority_text_sha256': candidate.get('authority_text_sha256'),
                    'temporal_applicability': candidate.get('temporal_applicability'),
                    'support_eligible': candidate.get('support_eligible'),
                    'treatment_blocks_support': candidate.get('treatment_blocks_support'),
                    'treatment_edges': candidate.get('treatment_edges'),
                    'blocking_treatments': candidate.get('blocking_treatments'),
                    'attributes': {
                        'source_bound_candidate': candidate,
                    },
                })
        requirements.extend(legacy_unverified_requirement_templates(claim_types))
        return requirements
    
    def _get_element_id(self, element_type: str = "", identity: Optional[Dict[str, Any]] = None) -> str:
        """Generate a unique element ID in that record's namespace."""
        self.element_counter += 1
        prefix = {
            "authority_source": "authority_source",
            "rule_candidate": "rule_candidate",
            "requirement": "legal_requirement",
            "procedural_requirement": "legal_requirement",
            "legal_requirement": "legal_requirement",
        }.get(element_type)
        if prefix:
            if identity is not None:
                from integrations.ipfs_datasets.graphs import mint_graph_record_id
                return mint_graph_record_id(prefix, json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
            return f"{prefix}:{self.element_counter}"
        return f"legal_elem_{self.element_counter}"

    def project_legal_passage(self, passage: Dict[str, Any]) -> LegalElement:
        """Project a legal passage into a legal namespace, never a complainant fact.

        The returned element is not added to a graph so callers can attach the
        passage provenance before insertion.
        """
        from integrations.ipfs_datasets.graphs import legal_namespace_kind

        payload = dict(passage or {})
        payload["legal_passage"] = True
        kind = legal_namespace_kind(payload)
        text = str(payload.get("text") or payload.get("name") or payload.get("description") or "").strip()
        provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
        return LegalElement(
            id=self._get_element_id(kind, {
                "text": text, "source_passage_id": payload.get("passage_id") or payload.get("source_id") or "",
                "citation": payload.get("citation") or "", "jurisdiction": payload.get("jurisdiction") or "",
                "provenance": provenance,
            }),
            element_type=kind,
            name=(text or kind)[: self._MAX_RULE_NAME_LENGTH],
            description=text,
            citation=str(payload.get("citation") or ""),
            jurisdiction=str(payload.get("jurisdiction") or ""),
            attributes={
                "record_kind": kind,
                "about_complainant": False,
                "source_passage_id": str(payload.get("passage_id") or payload.get("source_id") or ""),
                "provenance": dict(provenance),
            },
        )
    
    def _get_relation_id(self) -> str:
        """Generate unique relation ID."""
        self.relation_counter += 1
        return f"legal_rel_{self.relation_counter}"

    # ------------------------------------------------------------------ #
    # W9.4: Authority graph integration                                   #
    # ------------------------------------------------------------------ #

    _MAX_RULE_NAME_LENGTH = 120

    def build_from_authorities(
        self,
        authorities: List[Dict[str, Any]],
        claim_elements: Optional[List[Dict[str, Any]]] = None,
    ) -> 'LegalGraph':
        """Build a LegalGraph from stored authority records with treatment edges.

        Creates three layers of graph structure:
        1. Authority elements (``authority_source``) for each record.
        2. Authority-to-authority treatment edges (``supports``, ``adverse``,
           ``limits``, ``distinguishes``, ``questioned``, ``superseded``,
           ``good_law_unconfirmed``) derived from each authority's
           graph-ready ``authority_treatment_edges``, ``treatment_records``,
           or ``treatment_summary``.
        3. Rule-to-claim-element edges (``governs``) linking extracted rule
           candidates to the claim elements they cover.

        Args:
            authorities: Authority dicts as returned by legal-authority hooks.
                Each dict should have at minimum ``authority_id`` or ``id``,
                ``name`` or ``title``, and optionally
                ``authority_treatment_edges``, ``treatment_records``,
                ``treatment_summary``, and ``rule_candidates``.
            claim_elements: Optional list of claim-element dicts with
                ``element_id`` / ``claim_element_id`` and ``element_text`` /
                ``claim_element_text``.  When provided, rule candidates whose
                ``claim_element_id`` matches will have a ``governs`` edge added.

        Returns:
            A populated :class:`LegalGraph` instance.
        """
        graph = LegalGraph()

        # Index claim elements by ID for fast lookup
        element_id_to_graph_id: Dict[str, str] = {}
        for elem in claim_elements or []:
            if not isinstance(elem, dict):
                continue
            elem_id = str(elem.get('element_id') or elem.get('claim_element_id') or '').strip()
            elem_text = str(
                elem.get('element_text') or elem.get('claim_element_text') or ''
            ).strip()
            if not elem_id and not elem_text:
                continue
            node = LegalElement(
                id=self._get_element_id(),
                element_type='claim_element',
                name=elem_text or f'Element {elem_id}',
                description=elem_text,
                attributes={'source_element_id': elem_id},
            )
            graph.add_element(node)
            if elem_id:
                element_id_to_graph_id[elem_id] = node.id

        # Build authority nodes and treatment edges
        authority_node_ids: Dict[str, str] = {}
        for authority in authorities or []:
            if not isinstance(authority, dict):
                continue
            raw_id = str(
                authority.get('authority_id')
                or authority.get('id')
                or ''
            ).strip()
            name = str(
                authority.get('name') or authority.get('title') or authority.get('authority_name') or ''
            ).strip() or raw_id or 'unknown_authority'
            citation = str(authority.get('citation') or authority.get('cite') or '').strip()
            jurisdiction = str(authority.get('jurisdiction') or '').strip()
            authority_family = str(
                authority.get('authority_family') or authority.get('source_type') or ''
            ).strip()
            authority_version = str(
                authority.get('authority_version') or authority.get('version') or ''
            ).strip()
            law_version_id = str(authority.get('law_version_id') or '').strip()
            if not law_version_id and raw_id and authority_version:
                law_version_id = f'{raw_id}:{authority_version}'
            from integrations.ipfs_datasets.legal import retain_acquired_treatment_records
            retained_treatments = retain_acquired_treatment_records(authority)
            identity = {
                'source_authority_id': raw_id, 'name': name, 'citation': citation,
                'jurisdiction': jurisdiction, 'authority_family': authority_family,
                'provenance': authority.get('provenance') if isinstance(authority.get('provenance'), dict) else {},
            }
            if authority_version:
                identity['authority_version'] = authority_version
            if law_version_id:
                identity['law_version_id'] = law_version_id

            node = LegalElement(
                id=self._get_element_id('authority_source', identity),
                element_type='authority_source',
                name=name,
                citation=citation,
                jurisdiction=jurisdiction,
                attributes={
                    'source_authority_id': raw_id,
                    'authority_family': authority_family,
                    'authority_version': authority_version,
                    'law_version_id': law_version_id,
                    'retrieved_at': authority.get('retrieved_at') or '',
                    'applicable_law_date': authority.get('applicable_law_date') or '',
                    'effective_date': authority.get('effective_date') or '',
                    'treatment_records': retained_treatments,
                    'record_kind': 'authority_source',
                    'about_complainant': False,
                    'provenance': dict(authority.get('provenance') or {}) if isinstance(authority.get('provenance'), dict) else {},
                },
            )
            graph.add_element(node)
            if law_version_id:
                authority_node_ids[law_version_id] = node.id
            if raw_id:
                previous = authority_node_ids.get(raw_id)
                if previous is None:
                    authority_node_ids[raw_id] = node.id
                elif previous != node.id:
                    authority_node_ids.pop(raw_id, None)
                    authority_node_ids.pop(raw_id.removeprefix('authority:') if raw_id.startswith('authority:') else f'authority:{raw_id}', None)
                if raw_id.startswith('authority:') and raw_id in authority_node_ids:
                    authority_node_ids.setdefault(raw_id.removeprefix('authority:'), node.id)
                elif raw_id in authority_node_ids:
                    authority_node_ids.setdefault(f'authority:{raw_id}', node.id)

        # Second pass: add treatment edges and rule candidate edges now that all
        # authority nodes are registered (so cross-authority treatment targets resolve).
        for authority in authorities or []:
            if not isinstance(authority, dict):
                continue
            raw_id = str(
                authority.get('authority_id') or authority.get('id') or ''
            ).strip()
            authority_version = str(authority.get('authority_version') or authority.get('version') or '').strip()
            law_version_id = str(authority.get('law_version_id') or '').strip()
            if not law_version_id and raw_id and authority_version:
                law_version_id = f'{raw_id}:{authority_version}'
            source_node_id = authority_node_ids.get(law_version_id) or authority_node_ids.get(raw_id)
            if not source_node_id:
                continue

            # Treatment edges: authority → authority
            self._add_treatment_edges(graph, source_node_id, authority, authority_node_ids)

            # Rule candidate → claim element edges
            self._add_rule_candidate_edges(
                graph, source_node_id, authority, element_id_to_graph_id
            )

        self._apply_visible_treatment_support(graph)

        logger.debug(
            "built authority legal graph: %d elements, %d relations",
            len(graph.elements),
            len(graph.relations),
        )
        return graph

    def _apply_visible_treatment_support(self, graph: 'LegalGraph') -> None:
        """Keep treatment edges and stop them from supporting a requirement."""
        blocking_types = {
            'adverse', 'good_law_unconfirmed', 'questioned', 'limits', 'distinguishes', 'superseded',
            'superseding', 'repealed', 'repealing', 'repeal',
        }
        visible_types = blocking_types | {'supports'}
        treatments_by_authority: Dict[str, List[LegalRelation]] = {}
        for relation in graph.relations.values():
            if relation.relation_type in visible_types:
                treatments_by_authority.setdefault(relation.target_id, []).append(relation)
        rule_to_authority = {
            relation.source_id: relation.target_id
            for relation in graph.relations.values()
            if relation.relation_type == 'extracted_from'
        }
        requirement_to_rule = {
            relation.source_id: relation.target_id
            for relation in graph.relations.values()
            if relation.relation_type == 'promoted_from'
        }
        for element in graph.elements.values():
            authority_node = rule_to_authority.get(element.id)
            if authority_node is None and element.id in requirement_to_rule:
                authority_node = rule_to_authority.get(requirement_to_rule[element.id])
            if not authority_node:
                continue
            relations = treatments_by_authority.get(authority_node, [])
            treatment_types = [relation.relation_type for relation in relations]
            blocking = [name for name in treatment_types if name in blocking_types]
            element.attributes['treatment_edges_visible'] = True
            element.attributes['visible_treatment_types'] = treatment_types
            element.attributes['blocking_treatments'] = list(dict.fromkeys(blocking))
            if blocking:
                element.attributes['treatment_blocks_support'] = True
                element.attributes['support_eligible'] = False
                element.attributes['applicable'] = False
            elif element.attributes.get('promotion_status') == 'promoted':
                temporal = element.attributes.get('temporal_applicability')
                temporal_ok = not isinstance(temporal, dict) or temporal.get('applicable') is True
                element.attributes['support_eligible'] = bool(temporal_ok and element.attributes.get('applicable') is not False)
                element.attributes['treatment_blocks_support'] = False

    def _add_treatment_edges(
        self,
        graph: 'LegalGraph',
        source_node_id: str,
        authority: Dict[str, Any],
        authority_node_ids: Dict[str, str],
    ) -> None:
        """Add authority-to-authority treatment relation edges.

        Reads graph-ready ``authority_treatment_edges`` first, then falls back
        to ``treatment_records`` or ``treatment_summary`` from *authority* and
        inserts a :class:`LegalRelation` for each valid treatment pair.
        """
        _VALID_TREATMENT_TYPES = {
            'supports', 'adverse', 'limits', 'distinguishes',
            'questioned', 'superseded', 'superseding', 'good_law_unconfirmed',
            'repealed', 'repealing', 'repeal',
        }
        emitted: Set[Tuple[str, str, str]] = set()

        def add_edge_from_record(
            record: Dict[str, Any],
            *,
            source_ref: str,
            target_ref: str,
            relation_type: str,
        ) -> None:
            if relation_type not in _VALID_TREATMENT_TYPES:
                return
            edge_source_node_id = authority_node_ids.get(source_ref) if source_ref else source_node_id
            target_node_id = authority_node_ids.get(target_ref)
            if not edge_source_node_id or not target_node_id:
                return
            signature = (edge_source_node_id, target_node_id, relation_type)
            if signature in emitted:
                return
            emitted.add(signature)
            confidence = float(
                record.get('confidence')
                or record.get('treatment_confidence')
                or 0.0
            )
            rel = LegalRelation(
                id=self._get_relation_id(),
                source_id=edge_source_node_id,
                target_id=target_node_id,
                relation_type=relation_type,
                attributes={
                    'confidence': confidence,
                    'explanation': str(record.get('explanation') or record.get('treatment_explanation') or ''),
                    'treatment_date': str(record.get('treatment_date') or ''),
                    'treatment_source': str(record.get('treatment_source') or ''),
                    'source_authority_id': source_ref,
                    'target_authority_id': target_ref,
                    'source_citation': str(record.get('source_citation') or record.get('treated_by_citation') or ''),
                    'target_citation': str(record.get('target_citation') or ''),
                    'treatment_id': str(record.get('edge_id') or record.get('treatment_id') or ''),
                    'metadata': record.get('metadata') if isinstance(record.get('metadata'), dict) else {},
                },
            )
            graph.add_relation(rel)

        authority_edges = authority.get('authority_treatment_edges')
        has_graph_ready_edges = isinstance(authority_edges, list) and len(authority_edges) > 0
        if has_graph_ready_edges:
            for record in authority_edges:
                if not isinstance(record, dict):
                    continue
                add_edge_from_record(
                    record,
                    source_ref=str(
                        record.get('source_authority_id')
                        or record.get('treated_by_authority_id')
                        or ''
                    ).strip(),
                    target_ref=str(
                        record.get('target_authority_id')
                        or record.get('treated_authority_id')
                        or record.get('treated_by_authority_id')
                        or record.get('target_id')
                        or ''
                    ).strip(),
                    relation_type=str(
                        record.get('relation_type')
                        or record.get('treatment_type')
                        or record.get('type')
                        or record.get('treatment')
                        or record.get('effect')
                        or ''
                    ).strip(),
                )

        from integrations.ipfs_datasets.legal import retain_acquired_treatment_records
        extra_records = retain_acquired_treatment_records(authority)
        for record in extra_records:
            if not isinstance(record, dict):
                continue
            treatment_type = str(
                record.get('relation_type')
                or record.get('treatment_type')
                or record.get('type')
                or record.get('treatment')
                or record.get('effect')
                or ''
            ).strip()
            treated_id = str(
                record.get('target_authority_id')
                or record.get('treated_authority_id')
                or record.get('law_version_id')
                or record.get('target_id')
                or ''
            ).strip()
            source_ref = str(
                record.get('source_authority_id')
                or record.get('treated_by_authority_id')
                or ''
            ).strip()
            add_edge_from_record(
                record,
                source_ref=source_ref,
                target_ref=treated_id,
                relation_type=treatment_type,
            )

    def _add_rule_candidate_edges(
        self,
        graph: 'LegalGraph',
        authority_node_id: str,
        authority: Dict[str, Any],
        element_id_to_graph_id: Dict[str, str],
    ) -> None:
        """Add rule-to-claim-element ``governs`` edges from rule candidates.

        Reads ``rule_candidates`` from *authority*.  For each candidate, adds a
        ``rule_candidate`` element and, when the candidate's
        ``claim_element_id`` is in *element_id_to_graph_id*, adds a
        ``governs`` edge from the rule to the matched claim-element node.
        An ``extracted_from`` edge is always added from the rule candidate to the
        authority node (rule *extracted_from* authority).
        """
        for candidate in authority.get('rule_candidates') or []:
            if not isinstance(candidate, dict):
                continue
            rule_text = str(candidate.get('rule_text') or candidate.get('text') or '').strip()
            if not rule_text:
                continue
            rule_type = str(candidate.get('rule_type') or 'rule').strip()
            confidence = float(candidate.get('extraction_confidence', 0.0) or 0.0)
            grounded_rule = candidate.get('grounded_rule', {})
            if not isinstance(grounded_rule, dict):
                metadata = candidate.get('metadata', {}) if isinstance(candidate.get('metadata'), dict) else {}
                grounded_rule = metadata.get('grounded_rule', {}) if isinstance(metadata.get('grounded_rule'), dict) else {}
            from integrations.ipfs_datasets.logic import extract_source_bound_rule_candidates

            promotion_input = dict(candidate)
            # Normalize the supported text alias before source admission. The
            # exact candidate text, rather than a different authority sentence,
            # must own every promoted requirement's source span.
            promotion_input['rule_text'] = rule_text
            for key in (
                'source_text', 'text', 'source_hash', 'content_hash', 'content_hash_scope',
                'authority_version', 'version', 'jurisdiction', 'citation', 'authority_id',
                'effective_date', 'as_of_date', 'applicable_date', 'expiration_date',
                'sunset_date', 'repeal_date', 'superseded_date', 'law_versions', 'changes',
                'query_context', 'temporal_query_context', 'authority_treatment_edges',
                'treatment_records', 'treatment_summary', 'law_version_id',
            ):
                if key not in promotion_input and key in authority:
                    promotion_input[key] = authority.get(key)
            if not promotion_input.get('authority_id'):
                promotion_input['authority_id'] = str(authority.get('authority_id') or authority.get('id') or '')
            extraction = extract_source_bound_rule_candidates(promotion_input)
            promoted_candidate = next(
                (item for item in extraction['candidates'] if item.get('rule_text') == rule_text),
                {},
            )
            rule_node = LegalElement(
                id=self._get_element_id('rule_candidate', {
                    'source_authority_node': authority_node_id, 'rule_text': rule_text, 'rule_type': rule_type,
                    'provenance': candidate.get('provenance') if isinstance(candidate.get('provenance'), dict) else {},
                }),
                element_type='rule_candidate',
                name=rule_text[:self._MAX_RULE_NAME_LENGTH],
                description=rule_text,
                attributes={
                    'rule_type': rule_type,
                    'record_kind': 'rule_candidate',
                    'about_complainant': False,
                    'extraction_confidence': confidence,
                    'source_authority_node': authority_node_id,
                    'provenance': dict(candidate.get('provenance') or {}) if isinstance(candidate.get('provenance'), dict) else {},
                    'grounded_rule': grounded_rule,
                    'deontic_operator': grounded_rule.get('deontic_operator', '') or promoted_candidate.get('deontic_operator', ''),
                    'operator_family': grounded_rule.get('operator_family', ''),
                    'grounding_status': grounded_rule.get('grounding_status', ''),
                    'treatment_influence': grounded_rule.get('treatment_influence', ''),
                    'premise_failure_category': grounded_rule.get('premise_failure_category', ''),
                    'promotion_status': 'candidate',
                    'verification_status': 'candidate',
                    'applicable': False,
                    'promoted_to_requirement': bool(promoted_candidate.get('promoted')),
                    'review_reason': '' if promoted_candidate.get('promoted') else promoted_candidate.get('review_reason', ''),
                    'review_reasons': list(promoted_candidate.get('review_reasons') or []),
                    'source_span': promoted_candidate.get('source_span'),
                    'structure': promoted_candidate.get('structure'),
                    'rule_character': promoted_candidate.get('rule_character'),
                    'jurisdiction': promoted_candidate.get('jurisdiction') or authority.get('jurisdiction') or '',
                    'authority_id': promoted_candidate.get('authority_id') or '',
                    'authority_version': promoted_candidate.get('authority_version') or '',
                    'source_hash': promoted_candidate.get('source_hash') or '',
                    'applicable_date': promoted_candidate.get('applicable_date') or {},
                    'temporal_applicability': promoted_candidate.get('temporal_applicability') or {},
                    'support_eligible': promoted_candidate.get('support_eligible'),
                    'treatment_blocks_support': promoted_candidate.get('treatment_blocks_support'),
                    'treatment_edges': list(promoted_candidate.get('treatment_edges') or []),
                    'blocking_treatments': list(promoted_candidate.get('blocking_treatments') or []),
                },
            )
            graph.add_element(rule_node)
            if promoted_candidate.get('promoted'):
                requirement = LegalElement(
                    id=self._get_element_id('legal_requirement', {
                        'source_authority_node': authority_node_id,
                        'promoted_from_rule': rule_text,
                        'source_span': promoted_candidate.get('source_span'),
                        'source_hash': promoted_candidate.get('source_hash'),
                        'authority_version': promoted_candidate.get('authority_version'),
                    }),
                    element_type='legal_requirement',
                    name=rule_text[:self._MAX_RULE_NAME_LENGTH],
                    description=rule_text,
                    citation=str(promoted_candidate.get('citation') or authority.get('citation') or ''),
                    jurisdiction=str(promoted_candidate.get('jurisdiction') or ''),
                    attributes={
                        'record_kind': 'legal_requirement',
                        'about_complainant': False,
                        'applicable': bool(promoted_candidate.get('applicable')),
                        'support_eligible': bool(promoted_candidate.get('support_eligible')),
                        'treatment_blocks_support': bool(promoted_candidate.get('treatment_blocks_support')),
                        'treatment_edges': list(promoted_candidate.get('treatment_edges') or []),
                        'blocking_treatments': list(promoted_candidate.get('blocking_treatments') or []),
                        'temporal_applicability': promoted_candidate.get('temporal_applicability') or {},
                        'promoted': True,
                        'promotion_status': 'promoted',
                        'verification_status': 'promoted',
                        'legacy_template': False,
                        'review_reason': '',
                        'source_span': promoted_candidate.get('source_span'),
                        'source_hash': promoted_candidate.get('source_hash'),
                        'span_sha256': promoted_candidate.get('span_sha256'),
                        'authority_text_sha256': promoted_candidate.get('authority_text_sha256'),
                        'authority_id': promoted_candidate.get('authority_id'),
                        'authority_identity': promoted_candidate.get('authority_identity'),
                        'authority_version': promoted_candidate.get('authority_version'),
                        'applicable_date': promoted_candidate.get('applicable_date'),
                        'structure': promoted_candidate.get('structure'),
                        'rule_character': promoted_candidate.get('rule_character'),
                        'jurisdiction': promoted_candidate.get('jurisdiction'),
                        'applicable_claim_types': [
                            item for item in [
                                str(candidate.get('claim_type') or authority.get('claim_type') or '')
                            ] if item
                        ],
                    },
                )
                graph.add_element(requirement)
                graph.add_relation(
                    LegalRelation(
                        id=self._get_relation_id(),
                        source_id=requirement.id,
                        target_id=rule_node.id,
                        relation_type='promoted_from',
                    )
                )
            # rule candidate extracted_from authority (rule → authority direction)
            graph.add_relation(
                LegalRelation(
                    id=self._get_relation_id(),
                    source_id=rule_node.id,
                    target_id=authority_node_id,
                    relation_type='extracted_from',
                    attributes={'confidence': confidence},
                )
            )
            # rule candidate → claim element (governs) when linked
            claim_element_id = str(
                candidate.get('claim_element_id') or candidate.get('element_id') or ''
            ).strip()
            target_elem_graph_id = element_id_to_graph_id.get(claim_element_id)
            if target_elem_graph_id:
                graph.add_relation(
                    LegalRelation(
                        id=self._get_relation_id(),
                        source_id=rule_node.id,
                        target_id=target_elem_graph_id,
                        relation_type='governs',
                        attributes={
                            'confidence': confidence,
                            'rule_type': rule_type,
                        },
                    )
                )
