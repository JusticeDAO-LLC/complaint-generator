"""
Unit tests for Batch 220: KnowledgeGraphBuilder graph building analytics methods.

Tests the 10 graph building tracking and statistics methods added to KnowledgeGraphBuilder.
"""

import pytest
from complaint_phases.knowledge_graph import (
    KnowledgeGraphBuilder,
    KnowledgeGraph,
    Entity,
    Relationship
)


@pytest.fixture
def builder():
    """Create a KnowledgeGraphBuilder instance for testing."""
    return KnowledgeGraphBuilder()


def create_mock_graph(num_entities=3, num_relationships=2):
    """Helper to create a mock knowledge graph."""
    graph = KnowledgeGraph()
    
    for i in range(num_entities):
        entity = Entity(
            id=f'e{i+1}',
            type='person',
            name=f'Person {i+1}',
            attributes={},
            confidence=0.8,
            source='test'
        )
        graph.add_entity(entity)
    
    for i in range(num_relationships):
        source_index = (i % num_entities) + 1
        target_index = ((i + 1) % num_entities) + 1
        rel = Relationship(
            id=f'r{i+1}',
            source_id=f'e{source_index}',
            target_id=f'e{target_index}',
            relation_type='knows',
            attributes={},
            confidence=0.8,
            source='test'
        )
        graph.add_relationship(rel)
    
    return graph


# ============================================================================ #
# Test total_graphs_built()
# ============================================================================ #

class TestTotalGraphsBuilt:
    def test_no_graphs(self, builder):
        assert builder.total_graphs_built() == 0
    
    def test_single_graph(self, builder):
        builder._built_graphs.append(create_mock_graph())
        assert builder.total_graphs_built() == 1
    
    def test_multiple_graphs(self, builder):
        for i in range(5):
            builder._built_graphs.append(create_mock_graph())
        assert builder.total_graphs_built() == 5


# ============================================================================ #
# Test total_texts_processed()
# ============================================================================ #

class TestTotalTextsProcessed:
    def test_no_texts(self, builder):
        assert builder.total_texts_processed() == 0
    
    def test_single_text(self, builder):
        builder._text_processed_count = 1
        assert builder.total_texts_processed() == 1
    
    def test_multiple_texts(self, builder):
        builder._text_processed_count = 10
        assert builder.total_texts_processed() == 10


# ============================================================================ #
# Test average_entities_per_graph()
# ============================================================================ #

class TestAverageEntitiesPerGraph:
    def test_no_graphs(self, builder):
        assert builder.average_entities_per_graph() == 0.0
    
    def test_single_graph(self, builder):
        builder._built_graphs.append(create_mock_graph(num_entities=5))
        assert abs(builder.average_entities_per_graph() - 5.0) < 0.01
    
    def test_multiple_graphs(self, builder):
        builder._built_graphs.extend([
            create_mock_graph(num_entities=2),
            create_mock_graph(num_entities=4),
            create_mock_graph(num_entities=6),
        ])
        # Average: (2 + 4 + 6) / 3 = 4.0
        assert abs(builder.average_entities_per_graph() - 4.0) < 0.01


# ============================================================================ #
# Test average_relationships_per_graph()
# ============================================================================ #

class TestAverageRelationshipsPerGraph:
    def test_no_graphs(self, builder):
        assert builder.average_relationships_per_graph() == 0.0
    
    def test_single_graph(self, builder):
        builder._built_graphs.append(create_mock_graph(num_relationships=3))
        assert abs(builder.average_relationships_per_graph() - 3.0) < 0.01
    
    def test_multiple_graphs(self, builder):
        builder._built_graphs.extend([
            create_mock_graph(num_relationships=1),
            create_mock_graph(num_relationships=2),
            create_mock_graph(num_relationships=3),
        ])
        # Average: (1 + 2 + 3) / 3 = 2.0
        assert abs(builder.average_relationships_per_graph() - 2.0) < 0.01


# ============================================================================ #
# Test maximum_entities_in_graph()
# ============================================================================ #

class TestMaximumEntitiesInGraph:
    def test_no_graphs(self, builder):
        assert builder.maximum_entities_in_graph() == 0
    
    def test_single_graph(self, builder):
        builder._built_graphs.append(create_mock_graph(num_entities=7))
        assert builder.maximum_entities_in_graph() == 7
    
    def test_multiple_graphs(self, builder):
        builder._built_graphs.extend([
            create_mock_graph(num_entities=3),
            create_mock_graph(num_entities=8),
            create_mock_graph(num_entities=5),
        ])
        assert builder.maximum_entities_in_graph() == 8


# ============================================================================ #
# Test maximum_relationships_in_graph()
# ============================================================================ #

class TestMaximumRelationshipsInGraph:
    def test_no_graphs(self, builder):
        assert builder.maximum_relationships_in_graph() == 0
    
    def test_single_graph(self, builder):
        builder._built_graphs.append(create_mock_graph(num_relationships=6))
        assert builder.maximum_relationships_in_graph() == 6
    
    def test_multiple_graphs(self, builder):
        builder._built_graphs.extend([
            create_mock_graph(num_relationships=2),
            create_mock_graph(num_relationships=5),
            create_mock_graph(num_relationships=3),
        ])
        assert builder.maximum_relationships_in_graph() == 5


# ============================================================================ #
# Test total_entities_extracted()
# ============================================================================ #

class TestTotalEntitiesExtracted:
    def test_no_graphs(self, builder):
        assert builder.total_entities_extracted() == 0
    
    def test_single_graph(self, builder):
        builder._built_graphs.append(create_mock_graph(num_entities=4))
        assert builder.total_entities_extracted() == 4
    
    def test_multiple_graphs(self, builder):
        builder._built_graphs.extend([
            create_mock_graph(num_entities=2),
            create_mock_graph(num_entities=3),
            create_mock_graph(num_entities=5),
        ])
        # Total: 2 + 3 + 5 = 10
        assert builder.total_entities_extracted() == 10


# ============================================================================ #
# Test total_relationships_extracted()
# ============================================================================ #

class TestTotalRelationshipsExtracted:
    def test_no_graphs(self, builder):
        assert builder.total_relationships_extracted() == 0
    
    def test_single_graph(self, builder):
        builder._built_graphs.append(create_mock_graph(num_relationships=3))
        assert builder.total_relationships_extracted() == 3
    
    def test_multiple_graphs(self, builder):
        builder._built_graphs.extend([
            create_mock_graph(num_relationships=1),
            create_mock_graph(num_relationships=2),
            create_mock_graph(num_relationships=4),
        ])
        # Total: 1 + 2 + 4 = 7
        assert builder.total_relationships_extracted() == 7


# ============================================================================ #
# Test entity_extraction_rate()
# ============================================================================ #

class TestEntityExtractionRate:
    def test_no_texts(self, builder):
        assert builder.entity_extraction_rate() == 0.0
    
    def test_single_text(self, builder):
        builder._built_graphs.append(create_mock_graph(num_entities=5))
        builder._text_processed_count = 1
        assert abs(builder.entity_extraction_rate() - 5.0) < 0.01
    
    def test_multiple_texts(self, builder):
        builder._built_graphs.extend([
            create_mock_graph(num_entities=4),
            create_mock_graph(num_entities=6),
        ])
        builder._text_processed_count = 2
        # Total entities: 10, texts: 2, rate: 5.0
        assert abs(builder.entity_extraction_rate() - 5.0) < 0.01


# ============================================================================ #
# Test relationship_extraction_rate()
# ============================================================================ #

class TestRelationshipExtractionRate:
    def test_no_texts(self, builder):
        assert builder.relationship_extraction_rate() == 0.0
    
    def test_single_text(self, builder):
        builder._built_graphs.append(create_mock_graph(num_relationships=3))
        builder._text_processed_count = 1
        assert abs(builder.relationship_extraction_rate() - 3.0) < 0.01
    
    def test_multiple_texts(self, builder):
        builder._built_graphs.extend([
            create_mock_graph(num_relationships=2),
            create_mock_graph(num_relationships=4),
        ])
        builder._text_processed_count = 2
        # Total relationships: 6, texts: 2, rate: 3.0
        assert abs(builder.relationship_extraction_rate() - 3.0) < 0.01


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch220Integration:
    def test_comprehensive_graph_builder_analysis(self, builder):
        """Test that all Batch 220 methods work together correctly."""
        # Simulate building multiple graphs
        builder._built_graphs.extend([
            create_mock_graph(num_entities=3, num_relationships=2),
            create_mock_graph(num_entities=5, num_relationships=3),
            create_mock_graph(num_entities=4, num_relationships=1),
            create_mock_graph(num_entities=6, num_relationships=4),
        ])
        builder._text_processed_count = 4
        
        # Test all Batch 220 methods
        assert builder.total_graphs_built() == 4
        assert builder.total_texts_processed() == 4
        
        # Average entities: (3 + 5 + 4 + 6) / 4 = 4.5
        assert abs(builder.average_entities_per_graph() - 4.5) < 0.01
        
        # Average relationships: (2 + 3 + 1 + 4) / 4 = 2.5
        assert abs(builder.average_relationships_per_graph() - 2.5) < 0.01
        
        assert builder.maximum_entities_in_graph() == 6
        assert builder.maximum_relationships_in_graph() == 4
        
        # Total entities: 3 + 5 + 4 + 6 = 18
        assert builder.total_entities_extracted() == 18
        
        # Total relationships: 2 + 3 + 1 + 4 = 10
        assert builder.total_relationships_extracted() == 10
        
        # Entity rate: 18 / 4 = 4.5
        assert abs(builder.entity_extraction_rate() - 4.5) < 0.01
        
        # Relationship rate: 10 / 4 = 2.5
        assert abs(builder.relationship_extraction_rate() - 2.5) < 0.01
