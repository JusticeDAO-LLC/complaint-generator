# GraphRAG API Type Contracts

**Status:** Complete (2026-02-25)  
**Priority:** P1  
**Category:** API Stability

## Overview

All public API entrypoints in the GraphRAG optimizer modules now return properly typed structures defined as TypedDict definitions in [ontology_types.py](../../ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/ontology_types.py).

This provides:
- **Static type checking** via mypy/pyright
- **IDE autocomplete** for return value fields
- **Runtime documentation** of expected structures
- **Backward compatibility** with existing dict-based code

## Type System Architecture

### Core Ontology Types

**Ontology** - Complete ontology representation:
```python
class Ontology(TypedDict):
    entities: List[Entity]
    relationships: List[Relationship]
    metadata: NotRequired[OntologyMetadata]
    domain: NotRequired[str]
    version: NotRequired[str]
    statistics: NotRequired[Dict[str, Any]]
```

**Entity** - Extracted entity:
```python
class Entity(TypedDict):
    id: str
    text: str
    type: str
    confidence: float
    properties: NotRequired[Dict[str, Any]]
    context: NotRequired[str]
    source_span: NotRequired[Tuple[int, int]]
```

**Relationship** - Inferred relationship between entities:
```python
class Relationship(TypedDict):
    id: str
    source_id: str  # Note: uses source_id/target_id, not source/target
    target_id: str
    type: str
    confidence: float
    properties: NotRequired[Dict[str, Any]]
    context: NotRequired[str]
    distance: NotRequired[int]
```

### Evaluation Types

**CriticScore** - Ontology evaluation results (dataclass, not TypedDict):
```python
@dataclass
class CriticScore:
    overall: float
    completeness: float
    consistency: float
    clarity: float
    granularity: float
    relationship_coherence: float
    domain_alignment: float
    recommendations: List[str]
    strengths: List[str]
    weaknesses: List[str]
    metadata: Dict[str, Any]
```

### Pipeline Types

**PipelineStageResult** - Result from a pipeline stage:
```python
class PipelineStageResult(TypedDict):
    stage_name: str
    status: Literal["success", "partial", "failed"]
    ontology: NotRequired[Ontology]
    score: NotRequired[CriticScore]
    errors: NotRequired[List[str]]
    warnings: NotRequired[List[str]]
```

**RefinementCycleResult** - Complete refinement cycle result:
```python
class RefinementCycleResult(TypedDict):
    session_id: str
    initial_ontology: NotRequired[Ontology]
    final_ontology: Ontology
    rounds_completed: int
    convergence_achieved: bool
    initial_score: NotRequired[CriticScore]
    final_score: CriticScore
    improvement: NotRequired[float]
```

## Updated Method Signatures

### OntologyGenerator

**generate_ontology()** - Main generation entrypoint:
```python
def generate_ontology(
    self,
    data: Any,
    context: OntologyGenerationContext
) -> Ontology:  # Changed from Dict[str, Any]
    """Generate complete ontology from data."""
```

### OntologyMediator

**refine_ontology()** - Refinement based on feedback:
```python
def refine_ontology(
    self,
    ontology: Dict[str, Any],
    feedback: Any,  # CriticScore
    context: Any  # OntologyGenerationContext
) -> Ontology:  # Changed from Dict[str, Any]
    """Refine ontology based on critic feedback."""
```

### OntologyCritic

**evaluate_ontology()** - Already properly typed:
```python
def evaluate_ontology(
    self,
    ontology: Dict[str, Any],
    context: Any,
    source_data: Optional[Any] = None,
) -> CriticScore:  # Already returned CriticScore
    """Evaluate ontology across all quality dimensions."""
```

## Backward Compatibility

All typed return values are **fully backward compatible** with existing code:

### Dict Operations Still Work

```python
# Generate ontology (returns Ontology TypedDict, which is a dict subclass)
ontology = generator.generate_ontology(data, context)

# Standard dict operations work
assert 'entities' in ontology
entities = ontology.get('entities', [])
for key, value in ontology.items():
    print(f"{key}: {value}")
```

### Attribute Access for CriticScore

```python
# Evaluate ontology (returns CriticScore dataclass)
score = critic.evaluate_ontology(ontology, context)

# Attribute access works
print(f"Overall: {score.overall}")
print(f"Recommendations: {score.recommendations}")
```

## Testing

Comprehensive test suite in [test_batch_264_api_type_contracts.py](../../../tests/test_batch_264_api_type_contracts.py):

- ✅ **Structure validation** - Verify returned dicts match TypedDict fields
- ✅ **Type annotation checks** - Verify method signatures have proper return types
- ✅ **TypedDict definition verification** - Ensure TypedDicts have required keys
- ✅ **Backward compatibility** - Verify dict operations still work
- ✅ **Attribute access** - Verify CriticScore attribute access works

**Test Results:** 11/11 tests passing (2026-02-25)

## Migration Guide

### For Existing Code

No changes needed! All code using dict operations continues to work:

```python
# Before (still works)
ontology = generator.generate_ontology(data, context)
entities = ontology['entities']

# After (type-checked but functionally identical)
ontology = generator.generate_ontology(data, context)
entities = ontology['entities']
```

### For New Code with Type Checking

```python
from ipfs_datasets_py.optimizers.graphrag.ontology_types import (
    Ontology,
    Entity,
    Relationship,
    CriticScore,
)

def process_ontology(data: Any) -> Ontology:
    generator = OntologyGenerator()
    context = OntologyGenerationContext(
        data_source='input.txt',
        data_type=DataType.TEXT,
        domain='example',
        extraction_strategy=ExtractionStrategy.RULE_BASED
    )
    
    # Return type is now Ontology (type-checked)
    result: Ontology = generator.generate_ontology(data, context)
    
    # IDE autocomplete knows these fields exist
    entities: List[Entity] = result['entities']
    relationships: List[Relationship] = result['relationships']
    
    return result
```

## Static Type Checking

With mypy or pyright:

```bash
# Check types
mypy ipfs_datasets_py/optimizers/graphrag/ontology_generator.py
pyright ipfs_datasets_py/optimizers/graphrag/ontology_generator.py
```

## Known Limitations

1. **Runtime TypedDict validation** - TypedDict provides static type hints but no runtime validation. Use validation libraries like `pydantic` or `typeguard` if needed.

2. **Dict[str, Any] input types** - Input parameters still accept `Dict[str, Any]` for flexibility. Consider typed inputs in future work.

3. **Partial TypedDict support** - Some complex nested structures still use `Dict[str, Any]` (e.g., `properties` fields).

## Related Documentation

- [ontology_types.py](../../ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/ontology_types.py) - Complete type definitions
- [API Reference](./API_REFERENCE.md) - Public API documentation
- [GraphRAG Quick Start](./OPTIMIZERS_QUICK_START.md) - Usage examples

## Future Improvements

### P2 Enhancements

- Add runtime type validation with `typeguard`
- Create Pydantic models for strict validation
- Type input parameters (e.g., `context: OntologyGenerationContext`)
- Add generic type parameters for extensibility

### P3 Enhancements

- Generate OpenAPI/JSON Schema from TypedDicts
- Create type stubs (`.pyi`) for better IDE support
- Add exhaustiveness checking for `Literal` types
- Explore `dataclass_transform` for factory functions

## Changelog

### 2026-02-25: Initial Implementation

- ✅ Updated `Ontology` TypedDict to include `domain` and `version` fields
- ✅ Updated `OntologyGenerator.generate_ontology()` return type → `Ontology`
- ✅ Updated `OntologyMediator.refine_ontology()` return type → `Ontology`
- ✅ Created comprehensive test suite (11 tests, 100% passing)
- ✅ Verified backward compatibility (38 existing tests still pass)
- ✅ Updated conftest.py exclusion list for type contract tests
- ✅ Documented type system in this file

## Contributors

Type contracts implementation by GitHub Copilot (Claude Sonnet 4.5) on 2026-02-25 as part of P1 API stability work.
