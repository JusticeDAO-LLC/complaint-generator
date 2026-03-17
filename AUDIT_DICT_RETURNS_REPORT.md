# Audit: Dict[str, Any] Return Contracts in Optimizer Module

**Date**: Phase 2, Item 5
**Status**: AUDIT REPORT (identifies migration candidates)

## Summary

Total methods returning `Dict[str, Any]` in graphrag optimizers: **139 methods**

This audit identifies high-impact targets for type contract migration based on:
- Public API surface (not private/internal methods)
- Call frequency (methods called by many other functions)
- Critical path (query optimization, entity extraction)
- Domain (focus on query_unified_optimizer and ontology_generator)

## High-Impact Migration Targets (Priority Order)

### TIER 1: Critical Query Optimization Methods (10 methods)

These are the core methods in the query optimization pipeline that should have type contracts.

**File: query_unified_optimizer.py**
- `optimize_query(query: Dict[str, Any], priority: str, graph_processor: Any) -> QueryOptimizationResult` ✅ DONE (Item 4)
- `get_execution_plan(query: Dict[str, Any], priority: str, graph_processor: Any) -> QueryOptimizationPlan` ✅ DONE (Item 4)
- `optimize_wikipedia_traversal(query: Dict[str, Any], entity_scores) -> WikipediaTraversalOptimization` ✅ DONE (Item 4)
- `optimize_ipld_traversal(query: Dict[str, Any], entity_scores) -> IPLDTraversalOptimization` ✅ DONE (Item 4)
- `_validate_query_parameters(query: Dict[str, Any]) -> Dict[str, Any]` ❌ **TARGET**
- `_create_fallback_plan(query: Dict[str, Any], priority: str, error: Optional[str]) -> Dict[str, Any]` ❌ **TARGET**
- `_optimize_wikipedia_fact_verification(query: Dict[str, Any], traversal: Dict[str, Any]) -> Dict[str, Any]` ❌ **TARGET**

### TIER 2: Ontology Generation Methods (8 methods)

**File: ontology_generator.py**
- `to_dict() -> Dict[str, Any]` (multiple classes) ❌ **TARGET (multiple classes)**
- `extraction_statistics() -> Dict[str, Any]` ❌ **TARGET**
- `relationship_coherence_issues() -> Dict[str, Any]` ❌ **TARGET**
- `generate_synthetic_ontology(domain: str, n_entities: int) -> Dict[str, Any]` ❌ **TARGET**

### TIER 3: Metrics and Analysis Methods (6 methods)

**File: ontology_generator.py**
- `confidence_histogram(result, bins: int) -> dict` ❌ **TARGET**
- `entity_type_distribution(result) -> dict` ❌ **TARGET**
- `entity_count_by_type(result) -> dict` ❌ **TARGET**
- `relationship_type_counts(result) -> dict` ❌ **TARGET**

### TIER 4: Logic Validation Methods (5 methods)

**File: logic_validator.py**
- `summary_dict(ontology: Dict[str, Any]) -> Dict[str, Any]` ❌ **TARGET**
- `relationship_type_distribution(ontology: dict) -> dict` ❌ **TARGET**
- `node_degree_histogram(ontology: dict) -> dict` ❌ **TARGET**

## Recommended Next Steps

### Phase 2 (Current - Item 5)
1. ✅ Create TypedDict contracts for TIER 1 methods remaining (3 methods)
2. ✅ Create tests validating these contracts
3. ✅ Apply type annotations to method signatures

### Phase 3 (Future)
1. Migrate TIER 2 methods (ontology generation)
2. Migrate TIER 3 methods (metrics/analysis)
3. Migrate TIER 4 methods (logic validation)

## Contract Design Strategy

For each method, create a specific TypedDict:
```python
class ValidatedQueryParameters(TypedDict):
    query_text: str
    max_vector_results: int
    min_similarity: float
    traversal: Dict[str, Any]
    # ... other validated fields
```

## Implementation Notes

- 139 methods is too large for single sprint
- Focusing on public/critical methods first (TIER 1)
- Each type contract should:
  - Describe expected structure
  - Include type hints for nested fields where possible
  - Have corresponding test coverage
  - Document in docstring

## Test Coverage Plan

For each migrated method:
1. Create TypedDict contract
2. Add 1-2 unit tests validating return structure
3. Add property-based tests if applicable
4. Update docstring with contract reference

---
**Phase 2 Item 4 Completion**: 4/4 core query optimizer methods now have TypedDict contracts
**Phase 2 Item 5 Target**: 3+ additional high-value methods
