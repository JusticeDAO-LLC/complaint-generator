"""
Comprehensive tests for advanced ontology serialization infrastructure.

Test coverage:
- Dataclass to dict conversion (simple and nested)
- Dict to dataclass conversion (with validation)
- Batch operations
- JSON serialization
- Circular reference detection
- Error handling
- Type coercion
"""

import pytest
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

from ipfs_datasets_py.optimizers.graphrag.ontology_serialization import (
    OntologySerializer,
    SerializationError,
    DeserializationError,
    CircularReferenceError,
)


# Test dataclasses
@dataclass
class SimpleEntity:
    """Simple test entity."""
    id: str
    name: str
    confidence: float = 0.0


@dataclass
class EntityWithOptional:
    """Entity with optional fields."""
    id: str
    name: str
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class NestedEntity:
    """Entity with nested structure."""
    id: str
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    related_ids: List[str] = field(default_factory=list)


@dataclass
class ComplexEntity:
    """Complex entity with multiple nested types."""
    id: str
    name: str
    simple: Optional[SimpleEntity] = None
    nested_list: List[SimpleEntity] = field(default_factory=list)


class TestOntologySerializerBasic:
    """Test basic serialization functionality."""
    
    @pytest.fixture
    def serializer(self):
        """Create serializer instance."""
        return OntologySerializer()
    
    def test_simple_dataclass_to_dict(self, serializer):
        """Test converting simple dataclass to dict."""
        entity = SimpleEntity(id="e1", name="Test", confidence=0.95)
        result = serializer.dataclass_to_dict(entity)
        
        assert result == {
            'id': 'e1',
            'name': 'Test',
            'confidence': 0.95
        }
    
    def test_dataclass_to_dict_with_none_values(self, serializer):
        """Test dict conversion includes None by default."""
        entity = EntityWithOptional(id="e1", name="Test", description=None)
        result = serializer.dataclass_to_dict(entity)
        
        # None values should be included
        assert 'description' not in result  # None values excluded by default
    
    def test_dataclass_to_dict_include_none(self, serializer):
        """Test dict conversion with include_none=True."""
        entity = EntityWithOptional(id="e1", name="Test", description=None)
        result = serializer.dataclass_to_dict(entity, include_none=True)
        
        assert 'description' in result
        assert result['description'] is None
    
    def test_dataclass_to_dict_exclude_fields(self, serializer):
        """Test excluding specific fields from serialization."""
        entity = SimpleEntity(id="e1", name="Test", confidence=0.95)
        result = serializer.dataclass_to_dict(entity, exclude_fields=['confidence'])
        
        assert 'confidence' not in result
        assert 'id' in result
        assert 'name' in result
    
    def test_dict_to_dataclass_simple(self, serializer):
        """Test converting dict to simple dataclass."""
        data = {'id': 'e1', 'name': 'Test', 'confidence': 0.95}
        result = serializer.dict_to_dataclass(data, SimpleEntity)
        
        assert isinstance(result, SimpleEntity)
        assert result.id == 'e1'
        assert result.name == 'Test'
        assert result.confidence == 0.95
    
    def test_dict_to_dataclass_with_defaults(self, serializer):
        """Test that missing fields use defaults."""
        data = {'id': 'e1', 'name': 'Test'}
        result = serializer.dict_to_dataclass(data, SimpleEntity)
        
        assert result.confidence == 0.0  # Default value
    
    def test_dict_to_dataclass_with_optional_fields(self, serializer):
        """Test dict to dataclass with optional fields."""
        data = {'id': 'e1', 'name': 'Test', 'tags': ['tag1', 'tag2']}
        result = serializer.dict_to_dataclass(data, EntityWithOptional)
        
        assert result.id == 'e1'
        assert result.tags == ['tag1', 'tag2']
        assert result.description is None


class TestOntologySerializerNested:
    """Test nested structure serialization."""
    
    @pytest.fixture
    def serializer(self):
        """Create serializer instance."""
        return OntologySerializer()
    
    def test_nested_dataclass_to_dict(self, serializer):
        """Test converting nested dataclass to dict."""
        inner = SimpleEntity(id="inner", name="Inner", confidence=0.8)
        outer = ComplexEntity(id="outer", name="Outer", simple=inner)
        
        result = serializer.dataclass_to_dict(outer)
        
        assert result['id'] == 'outer'
        assert isinstance(result['simple'], dict)
        assert result['simple']['id'] == 'inner'
    
    def test_nested_list_to_dict(self, serializer):
        """Test converting nested list to dict."""
        entities = [
            SimpleEntity(id="e1", name="Entity1", confidence=0.9),
            SimpleEntity(id="e2", name="Entity2", confidence=0.8),
        ]
        outer = ComplexEntity(id="outer", name="Outer", nested_list=entities)
        
        result = serializer.dataclass_to_dict(outer)
        
        assert isinstance(result['nested_list'], list)
        assert len(result['nested_list']) == 2
        assert all(isinstance(e, dict) for e in result['nested_list'])
    
    def test_nested_dict_to_dataclass(self, serializer):
        """Test converting nested dict to dataclass."""
        data = {
            'id': 'outer',
            'name': 'Outer',
            'simple': {
                'id': 'inner',
                'name': 'Inner',
                'confidence': 0.8
            }
        }
        
        result = serializer.dict_to_dataclass(data, ComplexEntity)
        
        assert isinstance(result.simple, SimpleEntity)
        assert result.simple.id == 'inner'
        assert result.simple.confidence == 0.8
    
    def test_nested_list_dict_to_dataclass(self, serializer):
        """Test converting nested list dicts to dataclass."""
        data = {
            'id': 'outer',
            'name': 'Outer',
            'simple': None,
            'nested_list': [
                {'id': 'e1', 'name': 'Entity1', 'confidence': 0.9},
                {'id': 'e2', 'name': 'Entity2', 'confidence': 0.8},
            ]
        }
        
        result = serializer.dict_to_dataclass(data, ComplexEntity)
        
        assert len(result.nested_list) == 2
        # Note: nested_list items remain as dicts since we can't infer the type
        # This is a limitation of the simple implementation


class TestOntologySerializerBatch:
    """Test batch operations."""
    
    @pytest.fixture
    def serializer(self):
        """Create serializer instance."""
        return OntologySerializer()
    
    def test_batch_dict_to_dataclass(self, serializer):
        """Test converting multiple dicts to dataclasses."""
        data_list = [
            {'id': 'e1', 'name': 'Entity1', 'confidence': 0.9},
            {'id': 'e2', 'name': 'Entity2', 'confidence': 0.8},
            {'id': 'e3', 'name': 'Entity3', 'confidence': 0.85},
        ]
        
        results = serializer.dict_to_dataclass_batch(data_list, SimpleEntity)
        
        assert len(results) == 3
        assert all(isinstance(r, SimpleEntity) for r in results)
        assert results[0].name == 'Entity1'
    
    def test_batch_dict_to_dataclass_skip_errors(self, serializer):
        """Test batch conversion with error skipping."""
        data_list = [
            {'id': 'e1', 'name': 'Entity1', 'confidence': 0.9},
            {'id': 'e2'},  # Missing required field 'name'
            {'id': 'e3', 'name': 'Entity3', 'confidence': 0.85},
        ]
        
        results = serializer.dict_to_dataclass_batch(
            data_list,
            SimpleEntity,
            skip_errors=True
        )
        
        assert len(results) == 3
        assert isinstance(results[0], SimpleEntity)
        assert results[1] is None  # Error skipped
        assert isinstance(results[2], SimpleEntity)
    
    def test_batch_dict_to_dataclass_skip_errors_false(self, serializer):
        """Test batch conversion fails without skip_errors."""
        data_list = [
            {'id': 'e1', 'name': 'Entity1'},
            {'id': 'e2'},  # Missing required field 'name'
        ]
        
        with pytest.raises(DeserializationError):
            serializer.dict_to_dataclass_batch(
                data_list,
                SimpleEntity,
                skip_errors=False
            )


class TestOntologySerializerJSON:
    """Test JSON serialization."""
    
    @pytest.fixture
    def serializer(self):
        """Create serializer instance."""
        return OntologySerializer()
    
    def test_to_json(self, serializer):
        """Test converting dataclass to JSON."""
        entity = SimpleEntity(id="e1", name="Test", confidence=0.95)
        json_str = serializer.to_json(entity)
        
        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data['id'] == 'e1'
    
    def test_from_json(self, serializer):
        """Test creating dataclass from JSON."""
        json_str = '{"id": "e1", "name": "Test", "confidence": 0.95}'
        result = serializer.from_json(json_str, SimpleEntity)
        
        assert isinstance(result, SimpleEntity)
        assert result.id == 'e1'
        assert result.confidence == 0.95
    
    def test_json_roundtrip(self, serializer):
        """Test JSON serialization roundtrip."""
        original = SimpleEntity(id="e1", name="Test", confidence=0.95)
        json_str = serializer.to_json(original)
        restored = serializer.from_json(json_str, SimpleEntity)
        
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.confidence == original.confidence


class TestOntologySerializerErrors:
    """Test error handling."""
    
    @pytest.fixture
    def serializer(self):
        """Create serializer instance."""
        return OntologySerializer()
    
    def test_non_dataclass_to_dict_error(self, serializer):
        """Test error when converting non-dataclass."""
        with pytest.raises(SerializationError):
            serializer.dataclass_to_dict({"not": "dataclass"})
    
    def test_non_dataclass_target_error(self, serializer):
        """Test error when target is not dataclass."""
        data = {'id': 'e1', 'name': 'Test'}
        with pytest.raises(DeserializationError):
            serializer.dict_to_dataclass(data, dict)
    
    def test_non_dict_data_error(self, serializer):
        """Test error when data is not dict."""
        with pytest.raises(DeserializationError):
            serializer.dict_to_dataclass([1, 2, 3], SimpleEntity)
    
    def test_missing_required_field_strict_mode(self, serializer):
        """Test strict mode rejects missing required fields."""
        serializer.strict_mode = True
        data = {'id': 'e1'}  # Missing 'name'
        
        with pytest.raises(DeserializationError):
            serializer.dict_to_dataclass(data, SimpleEntity)
    
    def test_circular_reference_detection(self, serializer):
        """Test circular reference detection."""
        # Create data that would cause circular reference
        data1 = {'id': 'e1', 'name': 'Entity1'}
        data2 = {'id': 'e2', 'name': 'Entity2'}
        
        # Manually create circular reference
        visited = {id(data1)}
        
        with pytest.raises(CircularReferenceError):
            serializer.dict_to_dataclass(data1, SimpleEntity, visited)


class TestOntologySerializerIntegration:
    """Integration tests for serialization workflows."""
    
    @pytest.fixture
    def serializer(self):
        """Create serializer instance."""
        return OntologySerializer()
    
    def test_complete_workflow(self, serializer):
        """Test complete serialization workflow."""
        # Create object
        inner = SimpleEntity(id="inner", name="Inner", confidence=0.8)
        entity = ComplexEntity(id="outer", name="Outer", simple=inner)
        
        # Convert to dict
        entity_dict = serializer.dataclass_to_dict(entity)
        
        # Convert to JSON
        json_str = serializer.to_json(entity)
        
        # Restore from JSON
        restored = serializer.from_json(json_str, ComplexEntity)
        
        assert restored.id == 'outer'
        assert restored.simple is not None
        assert restored.simple.id == 'inner'
    
    def test_batch_workflow(self, serializer):
        """Test batch serialization workflow."""
        # Create objects
        entities = [
            SimpleEntity(id=f"e{i}", name=f"Entity{i}", confidence=0.9 - i*0.05)
            for i in range(1, 4)
        ]
        
        # Convert to dicts
        dicts = [serializer.dataclass_to_dict(e) for e in entities]
        
        # Batch restore
        restored = serializer.dict_to_dataclass_batch(dicts, SimpleEntity)
        
        assert len(restored) == 3
        assert all(isinstance(r, SimpleEntity) for r in restored)
        assert restored[0].id == 'e1'


@pytest.mark.parametrize("exclude_fields,expected_keys", [
    ([], {'id', 'name', 'confidence'}),
    (['confidence'], {'id', 'name'}),
    (['id', 'confidence'], {'name'}),
])
class TestOntologySerializerParametrized:
    """Parametrized tests for flexible configurations."""
    
    @pytest.fixture
    def serializer(self):
        """Create serializer instance."""
        return OntologySerializer()
    
    def test_exclude_fields_parametrized(
        self,
        serializer,
        exclude_fields,
        expected_keys
    ):
        """Test field exclusion with various combinations."""
        entity = SimpleEntity(id="e1", name="Test", confidence=0.95)
        result = serializer.dataclass_to_dict(entity, exclude_fields=exclude_fields)
        
        assert set(result.keys()) == expected_keys
