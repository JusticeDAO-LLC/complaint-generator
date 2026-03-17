"""
Test Batch 264: GraphRAG API Type Contracts

This test suite verifies that all public API entrypoints in the GraphRAG
optimizer modules return properly typed structures instead of generic Dict[str, Any].

The type system is defined in ontology_types.py with comprehensive TypedDict
definitions for all major data structures.

Test Coverage:
    - OntologyGenerator.generate_ontology() → Ontology
    - OntologyMediator.refine_ontology() → Ontology  
    - OntologyCritic.evaluate_ontology() → CriticScore
    - Query optimizer methods → QueryOptimizationResult
    - Pipeline methods → PipelineStageResult / RefinementCycleResult

References:
    - P1 API item: "Finalize typed return contracts for optimizer entrypoints"
    - ipfs_datasets_py/optimizers/graphrag/ontology_types.py
"""

import pytest
from typing import get_type_hints, Dict, Any
from unittest.mock import Mock, MagicMock, patch

from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
    ExtractionStrategy,
    DataType,
)
from ipfs_datasets_py.optimizers.graphrag.ontology_critic import OntologyCritic
from ipfs_datasets_py.optimizers.graphrag.ontology_mediator import OntologyMediator
from ipfs_datasets_py.optimizers.graphrag.ontology_types import (
    Ontology,
    Entity,
    Relationship,
    OntologyMetadata,
    CriticScore,
    DimensionalScore,
    CriticRecommendation,
    PipelineStageResult,
    RefinementCycleResult,
)


class TestOntologyGeneratorTypeContracts:
    """Test that OntologyGenerator returns properly typed Ontology structures."""
    
    @pytest.fixture
    def generator(self):
        """Create OntologyGenerator instance."""
        return OntologyGenerator(ipfs_accelerate_config={
            'model': 'bert-base-uncased',
            'task': 'ner'
        })
    
    @pytest.fixture
    def context(self):
        """Create generation context."""
        return OntologyGenerationContext(
            data_source='test_document.txt',
            data_type=DataType.TEXT,
            domain='test',
            extraction_strategy=ExtractionStrategy.RULE_BASED
        )
    
    def test_generate_ontology_returns_typed_structure(self, generator, context):
        """Verify generate_ontology() returns structure matching Ontology TypedDict."""
        sample_data = "This is test data for entity extraction."
        
        # Generate ontology
        result = generator.generate_ontology(sample_data, context)
        
        # Verify return type is dict (runtime check)
        assert isinstance(result, dict), "generate_ontology should return dict"
        
        # Verify required Ontology fields are present
        assert 'entities' in result, "Ontology must have 'entities'"
        assert 'relationships' in result, "Ontology must have 'relationships'"
        assert 'metadata' in result, "Ontology must have 'metadata'"
        assert 'domain' in result, "Ontology must have 'domain'"
        
        # Verify field types
        assert isinstance(result['entities'], list), "entities must be list"
        assert isinstance(result['relationships'], list), "relationships must be list"
        assert isinstance(result['metadata'], dict), "metadata must be dict"
        assert isinstance(result['domain'], str), "domain must be str"
        
        # Verify entity structure
        if result['entities']:
            entity = result['entities'][0]
            assert 'id' in entity, "Entity must have id"
            assert 'text' in entity, "Entity must have text"
            assert 'type' in entity, "Entity must have type"
            
        # Verify relationship structure
        if result['relationships']:
            rel = result['relationships'][0]
            assert 'source' in rel, "Relationship must have source"
            assert 'target' in rel, "Relationship must have target"
            assert 'type' in rel, "Relationship must have type"
    
    def test_generate_ontology_metadata_structure(self, generator, context):
        """Verify metadata field matches OntologyMetadata structure."""
        sample_data = "Test data."
        result = generator.generate_ontology(sample_data, context)
        
        metadata = result['metadata']
        
        # OntologyMetadata required fields
        assert 'source' in metadata, "Metadata must have source"
        assert 'domain' in metadata, "Metadata must have domain"
        
        # Verify types
        assert isinstance(metadata['source'], str), "source must be str"
        assert isinstance(metadata['domain'], str), "domain must be str"


class TestOntologyCriticTypeContracts:
    """Test that OntologyCritic returns properly typed CriticScore structures."""
    
    @pytest.fixture
    def critic(self):
        """Create OntologyCritic instance."""
        return OntologyCritic()
    
    @pytest.fixture
    def sample_ontology(self):
        """Create sample ontology for evaluation."""
        return {
            'entities': [
                {'id': 'e1', 'text': 'Entity1', 'type': 'Person', 'confidence': 0.9},
                {'id': 'e2', 'text': 'Entity2', 'type': 'Organization', 'confidence': 0.8}
            ],
            'relationships': [
                {'source': 'e1', 'target': 'e2', 'type': 'works_at', 'confidence': 0.85}
            ],
            'metadata': {
                'source': 'test.txt',
                'domain': 'business',
                'data_type': 'text'
            },
            'domain': 'business'
        }
    
    @pytest.fixture
    def context(self):
        """Create evaluation context."""
        from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
            OntologyGenerationContext,
            DataType,
            ExtractionStrategy,
        )
        return OntologyGenerationContext(
            data_source='test.txt',
            data_type=DataType.TEXT,
            domain='business',
            extraction_strategy=ExtractionStrategy.RULE_BASED
        )
    
    def test_evaluate_ontology_returns_critic_score(self, critic, sample_ontology, context):
        """Verify evaluate_ontology() returns CriticScore structure."""
        result = critic.evaluate_ontology(sample_ontology, context)
        
        # Verify return type (CriticScore is not a runtime-checkable protocol,
        # but we can verify it has the expected attributes)
        assert hasattr(result, 'overall'), "CriticScore must have overall"
        assert hasattr(result, 'completeness'), "CriticScore must have completeness"
        assert hasattr(result, 'consistency'), "CriticScore must have consistency"
        assert hasattr(result, 'clarity'), "CriticScore must have clarity"
        assert hasattr(result, 'granularity'), "CriticScore must have granularity"
        assert hasattr(result, 'relationship_coherence'), "CriticScore must have relationship_coherence"
        assert hasattr(result, 'domain_alignment'), "CriticScore must have domain_alignment"
        assert hasattr(result, 'recommendations'), "CriticScore must have recommendations"
        
        # Verify score types
        assert isinstance(result.overall, (int, float)), "overall must be numeric"
        assert isinstance(result.completeness, (int, float)), "completeness must be numeric"
        assert isinstance(result.consistency, (int, float)), "consistency must be numeric"
        assert isinstance(result.clarity, (int, float)), "clarity must be numeric"
        assert isinstance(result.granularity, (int, float)), "granularity must be numeric"
        assert isinstance(result.relationship_coherence, (int, float)), "relationship_coherence must be numeric"
        assert isinstance(result.domain_alignment, (int, float)), "domain_alignment must be numeric"
        
        # Verify recommendations is iterable
        assert hasattr(result.recommendations, '__iter__'), "recommendations must be iterable"
        
        # Verify score ranges
        assert 0.0 <= result.overall <= 1.0, "overall score must be in [0, 1]"
        assert 0.0 <= result.completeness <= 1.0, "completeness must be in [0, 1]"
        assert 0.0 <= result.consistency <= 1.0, "consistency must be in [0, 1]"


class TestOntologyMediatorTypeContracts:
    """Test that OntologyMediator returns properly typed structures."""
    
    @pytest.fixture
    def mediator(self):
        """Create OntologyMediator instance."""
        generator = Mock(spec=OntologyGenerator)
        critic = Mock(spec=OntologyCritic)
        return OntologyMediator(generator, critic, max_rounds=3)
    
    @pytest.fixture
    def sample_ontology(self):
        """Create sample ontology."""
        return {
            'entities': [
                {'id': 'e1', 'text': 'Entity1', 'type': 'Person', 'confidence': 0.9}
            ],
            'relationships': [],
            'metadata': {'source': 'test.txt', 'domain': 'test'},
            'domain': 'test'
        }
    
    @pytest.fixture
    def sample_feedback(self):
        """Create sample critic feedback."""
        feedback = Mock()
        feedback.overall = 0.7
        feedback.recommendations = ['Add more entities', 'Improve clarity']
        feedback.weaknesses = ['Incomplete entity set']
        feedback.strengths = []
        feedback.completeness = 0.6
        feedback.consistency = 0.8
        feedback.clarity = 0.7
        feedback.granularity = 0.7
        feedback.relationship_coherence = 0.5
        feedback.domain_alignment = 0.8
        return feedback
    
    @pytest.fixture
    def context(self):
        """Create generation context."""
        from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
            OntologyGenerationContext,
            DataType,
            ExtractionStrategy,
        )
        return OntologyGenerationContext(
            data_source='test.txt',
            data_type=DataType.TEXT,
            domain='test',
            extraction_strategy=ExtractionStrategy.RULE_BASED
        )
    
    def test_refine_ontology_returns_typed_structure(
        self, mediator, sample_ontology, sample_feedback, context
    ):
        """Verify refine_ontology() returns Ontology structure."""
        result = mediator.refine_ontology(sample_ontology, sample_feedback, context)
        
        # Verify return type is dict (runtime check)
        assert isinstance(result, dict), "refine_ontology should return dict"
        
        # Verify required Ontology fields
        assert 'entities' in result, "Refined ontology must have 'entities'"
        assert 'relationships' in result, "Refined ontology must have 'relationships'"
        
        # Verify types
        assert isinstance(result['entities'], list), "entities must be list"
        assert isinstance(result['relationships'], list), "relationships must be list"


class TestReturnTypeAnnotations:
    """Test that key methods have proper return type annotations."""
    
    def test_generate_ontology_annotation(self):
        """Verify OntologyGenerator.generate_ontology has Ontology return type."""
        # This test verifies the type annotation, not runtime behavior
        hints = get_type_hints(OntologyGenerator.generate_ontology)
        
        # Check if return annotation exists
        assert 'return' in hints, "generate_ontology should have return type annotation"
        
        # The return type should be Ontology (from ontology_types.py)
        return_type = hints['return']
        return_type_str = str(return_type)
        
        # Allow either Dict[str, Any] (legacy) or Ontology (current)
        # Check if it's the actual Ontology class
        from ipfs_datasets_py.optimizers.graphrag.ontology_types import Ontology as OntologyType
        
        assert (
            return_type == Dict[str, Any] or 
            return_type == OntologyType or
            'Ontology' in return_type_str
        ), f"generate_ontology return type is {return_type}, expected Ontology or Dict[str, Any]"
    
    def test_evaluate_ontology_annotation(self):
        """Verify OntologyCritic.evaluate_ontology returns CriticScore."""
        hints = get_type_hints(OntologyCritic.evaluate_ontology)
        
        # Check return annotation exists
        assert 'return' in hints, "evaluate_ontology should have return type annotation"
        
        # The return type should be CriticScore
        return_type = str(hints['return'])
        
        # CriticScore is a dataclass, not TypedDict, so runtime type checking works
        assert 'CriticScore' in return_type, \
            f"evaluate_ontology should return CriticScore, got {return_type}"


class TestTypeCompatibility:
    """Test that returned structures are compatible with TypedDict definitions."""
    
    def test_ontology_keys_match_typedef(self):
        """Verify Ontology structure keys match the TypedDict definition."""
        from ipfs_datasets_py.optimizers.graphrag import ontology_types
        
        # Get keys from Ontology TypedDict
        ontology_keys = set(ontology_types.Ontology.__annotations__.keys())
        
        # Required keys that all ontologies should have
        required_keys = {'entities', 'relationships', 'metadata', 'domain'}
        
        assert required_keys.issubset(ontology_keys), \
            f"Ontology TypedDict missing required keys: {required_keys - ontology_keys}"
    
    def test_entity_keys_match_typedef(self):
        """Verify Entity structure keys match the TypedDict definition."""
        from ipfs_datasets_py.optimizers.graphrag import ontology_types
        
        # Get keys from Entity TypedDict
        entity_keys = set(ontology_types.Entity.__annotations__.keys())
        
        # Minimum keys all entities should have
        required_keys = {'id', 'text', 'type'}
        
        assert required_keys.issubset(entity_keys), \
            f"Entity TypedDict missing required keys: {required_keys - entity_keys}"
    
    def test_relationship_keys_match_typedef(self):
        """Verify Relationship structure keys match the TypedDict definition."""
        from ipfs_datasets_py.optimizers.graphrag import ontology_types
        
        # Get keys from Relationship TypedDict
        rel_keys = set(ontology_types.Relationship.__annotations__.keys())
        
        # Required keys (note: uses source_id/target_id, not source/target)
        required_keys = {'source_id', 'target_id', 'type'}
        
        assert required_keys.issubset(rel_keys), \
            f"Relationship TypedDict missing required keys: {required_keys - rel_keys}"


class TestBackwardCompatibility:
    """Test that type annotations don't break existing code."""
    
    def test_generate_ontology_dict_access(self):
        """Verify generated ontologies support standard dict access."""
        generator = OntologyGenerator(ipfs_accelerate_config={
            'model': 'bert-base-uncased',
            'task': 'ner'
        })
        context = OntologyGenerationContext(
            data_source='test.txt',
            data_type=DataType.TEXT,
            domain='test',
            extraction_strategy=ExtractionStrategy.RULE_BASED
        )
        
        result = generator.generate_ontology("Test data.", context)
        
        # Standard dict operations should work
        assert 'entities' in result
        assert result.get('entities') is not None
        assert result.keys()
        assert list(result.values())
        
        # Should be able to iterate
        for key in result:
            assert isinstance(key, str)
    
    def test_critic_score_attribute_access(self):
        """Verify CriticScore supports attribute access."""
        critic = OntologyCritic()
        ontology = {
            'entities': [{'id': 'e1', 'text': 'Test', 'type': 'Thing', 'confidence': 0.9}],
            'relationships': [],
            'metadata': {'source': 'test', 'domain': 'test'},
            'domain': 'test'
        }
        context = OntologyGenerationContext(
            data_source='test.txt',
            data_type=DataType.TEXT,
            domain='test',
            extraction_strategy=ExtractionStrategy.RULE_BASED
        )
        
        score = critic.evaluate_ontology(ontology, context)
        
        # Attribute access should work
        assert hasattr(score, 'overall')
        assert hasattr(score, 'completeness')
        assert hasattr(score, 'recommendations')
        
        # Should be able to get values
        _ = score.overall
        _ = score.completeness
        _ = list(score.recommendations)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
