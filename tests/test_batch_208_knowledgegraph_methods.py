"""
Unit tests for Batch 208: KnowledgeGraph analysis methods.

Tests the 10 knowledge graph analysis and statistics methods added to KnowledgeGraph.
"""

import pytest
from complaint_phases.knowledge_graph import KnowledgeGraph, Entity, Relationship


@pytest.fixture
def kg():
    """Create an empty KnowledgeGraph instance for testing."""
    return KnowledgeGraph()


def create_entity(entity_id, entity_type='person', name='Test Entity', 
                  confidence=1.0, attributes=None):
    """Helper to create an Entity."""
    if attributes is None:
        attributes = {}
    return Entity(
        id=entity_id,
        type=entity_type,
        name=name,
        confidence=confidence,
        attributes=attributes
    )


def create_relationship(rel_id, source_id, target_id, relation_type='related_to'):
    """Helper to create a Relationship."""
    return Relationship(
        id=rel_id,
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        attributes={}
    )


# ============================================================================ #
# Test total_entities()
# ============================================================================ #

class TestTotalEntities:
    def test_empty_graph(self, kg):
        assert kg.total_entities() == 0
    
    def test_single_entity(self, kg):
        kg.add_entity(create_entity('e1'))
        assert kg.total_entities() == 1
    
    def test_multiple_entities(self, kg):
        for i in range(5):
            kg.add_entity(create_entity(f'e{i}'))
        assert kg.total_entities() == 5


# ============================================================================ #
# Test total_relationships()
# ============================================================================ #

class TestTotalRelationships:
    def test_empty_graph(self, kg):
        assert kg.total_relationships() == 0
    
    def test_single_relationship(self, kg):
        kg.add_entity(create_entity('e1'))
        kg.add_entity(create_entity('e2'))
        kg.add_relationship(create_relationship('r1', 'e1', 'e2'))
        assert kg.total_relationships() == 1
    
    def test_multiple_relationships(self, kg):
        for i in range(4):
            kg.add_entity(create_entity(f'e{i}'))
        for i in range(3):
            kg.add_relationship(create_relationship(f'r{i}', f'e{i}', f'e{i+1}'))
        assert kg.total_relationships() == 3


# ============================================================================ #
# Test entity_type_distribution()
# ============================================================================ #

class TestEntityTypeDistribution:
    def test_empty_graph(self, kg):
        assert kg.entity_type_distribution() == {}
    
    def test_single_type(self, kg):
        kg.add_entity(create_entity('e1', entity_type='person'))
        kg.add_entity(create_entity('e2', entity_type='person'))
        dist = kg.entity_type_distribution()
        assert dist == {'person': 2}
    
    def test_multiple_types(self, kg):
        kg.add_entity(create_entity('e1', entity_type='person'))
        kg.add_entity(create_entity('e2', entity_type='organization'))
        kg.add_entity(create_entity('e3', entity_type='person'))
        kg.add_entity(create_entity('e4', entity_type='claim'))
        kg.add_entity(create_entity('e5', entity_type='claim'))
        kg.add_entity(create_entity('e6', entity_type='claim'))
        dist = kg.entity_type_distribution()
        assert dist == {'person': 2, 'organization': 1, 'claim': 3}


# ============================================================================ #
# Test most_common_entity_type()
# ============================================================================ #

class TestMostCommonEntityType:
    def test_empty_graph(self, kg):
        assert kg.most_common_entity_type() == 'none'
    
    def test_single_entity(self, kg):
        kg.add_entity(create_entity('e1', entity_type='organization'))
        assert kg.most_common_entity_type() == 'organization'
    
    def test_clear_winner(self, kg):
        types = ['person', 'claim', 'person', 'person', 'organization']
        for i, etype in enumerate(types):
            kg.add_entity(create_entity(f'e{i}', entity_type=etype))
        assert kg.most_common_entity_type() == 'person'


# ============================================================================ #
# Test relationship_type_distribution()
# ============================================================================ #

class TestRelationshipTypeDistribution:
    def test_empty_graph(self, kg):
        assert kg.relationship_type_distribution() == {}
    
    def test_single_type(self, kg):
        for i in range(3):
            kg.add_entity(create_entity(f'e{i}'))
        kg.add_relationship(create_relationship('r1', 'e0', 'e1', 'employed_by'))
        kg.add_relationship(create_relationship('r2', 'e1', 'e2', 'employed_by'))
        dist = kg.relationship_type_distribution()
        assert dist == {'employed_by': 2}
    
    def test_multiple_types(self, kg):
        for i in range(4):
            kg.add_entity(create_entity(f'e{i}'))
        kg.add_relationship(create_relationship('r1', 'e0', 'e1', 'employed_by'))
        kg.add_relationship(create_relationship('r2', 'e1', 'e2', 'supported_by'))
        kg.add_relationship(create_relationship('r3', 'e2', 'e3', 'employed_by'))
        dist = kg.relationship_type_distribution()
        assert dist == {'employed_by': 2, 'supported_by': 1}


# ============================================================================ #
# Test average_confidence()
# ============================================================================ #

class TestAverageConfidence:
    def test_empty_graph(self, kg):
        assert kg.average_confidence() == 0.0
    
    def test_single_entity(self, kg):
        kg.add_entity(create_entity('e1', confidence=0.75))
        assert kg.average_confidence() == 0.75
    
    def test_multiple_entities(self, kg):
        kg.add_entity(create_entity('e1', confidence=0.6))
        kg.add_entity(create_entity('e2', confidence=0.8))
        kg.add_entity(create_entity('e3', confidence=0.7))
        avg = kg.average_confidence()
        assert abs(avg - 0.7) < 0.01
    
    def test_perfect_confidence(self, kg):
        kg.add_entity(create_entity('e1', confidence=1.0))
        kg.add_entity(create_entity('e2', confidence=1.0))
        assert kg.average_confidence() == 1.0


# ============================================================================ #
# Test low_confidence_entity_count()
# ============================================================================ #

class TestLowConfidenceEntityCount:
    def test_empty_graph(self, kg):
        assert kg.low_confidence_entity_count() == 0
    
    def test_all_high_confidence(self, kg):
        kg.add_entity(create_entity('e1', confidence=0.9))
        kg.add_entity(create_entity('e2', confidence=0.85))
        kg.add_entity(create_entity('e3', confidence=1.0))
        assert kg.low_confidence_entity_count() == 0
    
    def test_all_low_confidence(self, kg):
        kg.add_entity(create_entity('e1', confidence=0.3))
        kg.add_entity(create_entity('e2', confidence=0.5))
        assert kg.low_confidence_entity_count() == 2
    
    def test_mixed_confidence(self, kg):
        kg.add_entity(create_entity('e1', confidence=0.9))
        kg.add_entity(create_entity('e2', confidence=0.5))
        kg.add_entity(create_entity('e3', confidence=0.65))
        kg.add_entity(create_entity('e4', confidence=0.3))
        # Default threshold is 0.7, so e2, e3, e4 are below
        assert kg.low_confidence_entity_count() == 3
    
    def test_custom_threshold(self, kg):
        kg.add_entity(create_entity('e1', confidence=0.95))
        kg.add_entity(create_entity('e2', confidence=0.85))
        kg.add_entity(create_entity('e3', confidence=0.75))
        # With threshold=0.9, only e2 and e3 are below
        assert kg.low_confidence_entity_count(threshold=0.9) == 2


# ============================================================================ #
# Test isolated_entity_count()
# ============================================================================ #

class TestIsolatedEntityCount:
    def test_empty_graph(self, kg):
        assert kg.isolated_entity_count() == 0
    
    def test_all_isolated(self, kg):
        kg.add_entity(create_entity('e1'))
        kg.add_entity(create_entity('e2'))
        kg.add_entity(create_entity('e3'))
        assert kg.isolated_entity_count() == 3
    
    def test_none_isolated(self, kg):
        kg.add_entity(create_entity('e1'))
        kg.add_entity(create_entity('e2'))
        kg.add_relationship(create_relationship('r1', 'e1', 'e2'))
        assert kg.isolated_entity_count() == 0
    
    def test_mixed_connectivity(self, kg):
        for i in range(5):
            kg.add_entity(create_entity(f'e{i}'))
        kg.add_relationship(create_relationship('r1', 'e0', 'e1'))
        kg.add_relationship(create_relationship('r2', 'e2', 'e3'))
        # e4 is isolated
        assert kg.isolated_entity_count() == 1


# ============================================================================ #
# Test average_relationships_per_entity()
# ============================================================================ #

class TestAverageRelationshipsPerEntity:
    def test_empty_graph(self, kg):
        assert kg.average_relationships_per_entity() == 0.0
    
    def test_no_relationships(self, kg):
        kg.add_entity(create_entity('e1'))
        kg.add_entity(create_entity('e2'))
        assert kg.average_relationships_per_entity() == 0.0
    
    def test_linear_chain(self, kg):
        # e0 -> e1 -> e2 (2 relationships, 3 entities)
        for i in range(3):
            kg.add_entity(create_entity(f'e{i}'))
        kg.add_relationship(create_relationship('r1', 'e0', 'e1'))
        kg.add_relationship(create_relationship('r2', 'e1', 'e2'))
        avg = kg.average_relationships_per_entity()
        # e0: 1 rel, e1: 2 rels, e2: 1 rel -> total 4 / 2 = 2, avg = 2/3
        assert abs(avg - (2/3)) < 0.01


class TestFindGapsHeuristics:
    def test_detects_notice_hearing_staff_and_retaliation_gaps(self, kg):
        claim = create_entity(
            'claim1',
            entity_type='claim',
            name='Retaliation claim',
            confidence=0.95,
            attributes={'claim_type': 'retaliation'},
        )
        person = create_entity(
            'person1',
            entity_type='person',
            name='Supervisor',
            confidence=0.9,
            attributes={'role': 'manager', 'description': 'Supervisor sent denial notice and blocked grievance hearing'},
        )
        notice_fact = create_entity(
            'fact1',
            entity_type='fact',
            name='Denial notice',
            confidence=0.9,
            attributes={'description': 'I received a denial notice by email after I complained'},
        )

        kg.add_entity(claim)
        kg.add_entity(person)
        kg.add_entity(notice_fact)

        gap_types = {gap['type'] for gap in kg.find_gaps()}

        assert 'missing_written_notice' in gap_types
        assert 'missing_hearing_request_date' in gap_types
        assert 'missing_staff_identity' in gap_types
        assert 'retaliation_missing_causation' in gap_types
    
    def test_star_topology(self, kg):
        # e0 connected to e1, e2, e3
        for i in range(4):
            kg.add_entity(create_entity(f'e{i}'))
        kg.add_relationship(create_relationship('r1', 'e0', 'e1'))
        kg.add_relationship(create_relationship('r2', 'e0', 'e2'))
        kg.add_relationship(create_relationship('r3', 'e0', 'e3'))
        avg = kg.average_relationships_per_entity()
        # e0: 3, e1: 1, e2: 1, e3: 1 -> total 6 / 2 = 3, avg = 3/4
        assert abs(avg - 0.75) < 0.01


# ============================================================================ #
# Test most_connected_entity()
# ============================================================================ #

class TestMostConnectedEntity:
    def test_empty_graph(self, kg):
        assert kg.most_connected_entity() == 'none'
    
    def test_no_relationships(self, kg):
        kg.add_entity(create_entity('e1'))
        kg.add_entity(create_entity('e2'))
        # Should return one of them (all have 0 connections)
        result = kg.most_connected_entity()
        assert result in ['e1', 'e2']
    
    def test_clear_hub(self, kg):
        # e0 is the hub connected to e1, e2, e3
        for i in range(4):
            kg.add_entity(create_entity(f'e{i}'))
        kg.add_relationship(create_relationship('r1', 'e0', 'e1'))
        kg.add_relationship(create_relationship('r2', 'e0', 'e2'))
        kg.add_relationship(create_relationship('r3', 'e0', 'e3'))
        assert kg.most_connected_entity() == 'e0'
    
    def test_tied_connectivity(self, kg):
        # e0 and e1 both have 2 connections
        for i in range(4):
            kg.add_entity(create_entity(f'e{i}'))
        kg.add_relationship(create_relationship('r1', 'e0', 'e2'))
        kg.add_relationship(create_relationship('r2', 'e0', 'e3'))
        kg.add_relationship(create_relationship('r3', 'e1', 'e2'))
        kg.add_relationship(create_relationship('r4', 'e1', 'e3'))
        result = kg.most_connected_entity()
        # e2 and e3 also have 2 connections each, so any could be returned
        assert result in ['e0', 'e1', 'e2', 'e3']


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch208Integration:
    def test_comprehensive_knowledge_graph_analysis(self, kg):
        """Test that all Batch 208 methods work together correctly."""
        # Build a realistic knowledge graph
        # Add people
        kg.add_entity(create_entity('p1', entity_type='person', name='John Doe', confidence=0.9))
        kg.add_entity(create_entity('p2', entity_type='person', name='Jane Smith', confidence=0.6))
        
        # Add organizations
        kg.add_entity(create_entity('o1', entity_type='organization', name='Acme Corp', confidence=1.0))
        
        # Add claims
        kg.add_entity(create_entity('c1', entity_type='claim', name='Discrimination claim', confidence=0.85))
        kg.add_entity(create_entity('c2', entity_type='claim', name='Retaliation claim', confidence=0.5))
        
        # Add evidence
        kg.add_entity(create_entity('ev1', entity_type='evidence', name='Email thread', confidence=0.95))
        
        # Add relationships
        kg.add_relationship(create_relationship('r1', 'p1', 'o1', 'employed_by'))
        kg.add_relationship(create_relationship('r2', 'p2', 'o1', 'employed_by'))
        kg.add_relationship(create_relationship('r3', 'c1', 'p1', 'involves'))
        kg.add_relationship(create_relationship('r4', 'c1', 'ev1', 'supported_by'))
        kg.add_relationship(create_relationship('r5', 'c2', 'p1', 'involves'))
        
        # Test all methods
        assert kg.total_entities() == 6
        assert kg.total_relationships() == 5
        
        entity_dist = kg.entity_type_distribution()
        assert entity_dist == {'person': 2, 'organization': 1, 'claim': 2, 'evidence': 1}
        assert kg.most_common_entity_type() in ['person', 'claim']
        
        rel_dist = kg.relationship_type_distribution()
        assert rel_dist == {'employed_by': 2, 'involves': 2, 'supported_by': 1}
        
        avg_conf = kg.average_confidence()
        # (0.9 + 0.6 + 1.0 + 0.85 + 0.5 + 0.95) / 6 = 4.8 / 6 = 0.8
        assert abs(avg_conf - 0.8) < 0.01
        
        # p2 (0.6) and c2 (0.5) are below 0.7
        assert kg.low_confidence_entity_count() == 2
        
        # No isolated entities (all have at least one relationship)
        assert kg.isolated_entity_count() == 0
        
        avg_rel = kg.average_relationships_per_entity()
        # p1: 3, p2: 1, o1: 2, c1: 2, c2: 1, ev1: 1 = 10 connections / 2 = 5, avg = 5/6
        assert abs(avg_rel - (5/6)) < 0.01
        
        # p1 has 3 connections, should be most connected
        assert kg.most_connected_entity() == 'p1'
