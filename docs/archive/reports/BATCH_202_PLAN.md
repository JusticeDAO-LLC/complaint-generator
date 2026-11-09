# Batch 202 Selection & Implementation Plan

**Date:** 2026-02-21 ~21:30
**Status:** Planning phase

## Selected Tasks (5 items, balanced across tracks)

### 1. Profile infer_relationships() optimization (PERF - P2)
- **Goal:** Validate and benchmark the Batch 198 infer_relationships() optimization
- **Deliverable:** Performance profiling report with metrics (before/after timings, optimization delta)
- **Dependencies:** ontology_generator.py (already has optimizations)
- **Tests:** Create test_profile_infer_relationships.py with timing benchmarks
- **Estimated LOC:** ~300-400 lines (profiling framework + benchmarks)

### 2. OntologyCritic.explain_score() (API - P3)
- **Goal:** Add method to explain/decompose CriticScore computation
- **Deliverable:** Method that returns readable explanation of score components
- **Dependencies:** OntologyCritic class, CriticScore dataclass
- **Tests:** Create test_critic_explain_score.py with explanation validation
- **Estimated LOC:** ~150-200 lines (method + tests)

### 3. test_critic_score_distribution.py (TESTS - P2)
- **Goal:** Validate CriticScore distribution across large sample set (1000+ samples)
- **Deliverable:** Test suite validating score statistics and distributions
- **Dependencies:** CriticScore, OntologyCritic
- **Tests:** Statistical tests on score means, stdevs, percentiles, and distributions
- **Estimated LOC:** ~250-350 lines (statistical test cases)

### 4. OntologyGenerator.generate_with_feedback() (API - P2)
- **Goal:** Add method to accept initial feedback loop during generation
- **Deliverable:** Method accepting feedback and iteratively refining ontology
- **Dependencies:** OntologyGenerator, OntologyCritic
- **Tests:** Create test_generate_with_feedback.py validating feedback incorporation
- **Estimated LOC:** ~200-300 lines (method + tests)

### 5. Implement .lower() caching for stopwords (PERF - P2)
- **Goal:** Quick optimization: cache lowercased stopwords to avoid repeated .lower() calls
- **Deliverable:** Modified stopword matching logic with cached normalized versions
- **Dependencies:** ExtractionConfig, extraction rule-based matching
- **Tests:** Validate performance improvement and correctness of matching
- **Estimated LOC:** ~50-100 lines (caching logic, minimal churn)

## Implementation Order

1. **Task 5 (PERF - Quick Win):** ~30-50 min - Implement .lower() caching for stopwords
   - Smallest/quickest to implement
   - Builds momentum
   - High confidence success

2. **Task 1 (PERF - Medium):** ~60-90 min - Profile infer_relationships() optimization
   - Validate Batch 198 work
   - Create benchmarking framework
   - Document performance delta

3. **Task 3 (TESTS - Medium):** ~45-75 min - CriticScore distribution tests
   - Use profiling framework from Task 1
   - Statistical validation
   - Large sample set generation

4. **Task 2 (API - Medium):** ~40-60 min - OntologyCritic.explain_score()
   - Simple decomposition logic
   - Readable formatting
   - Test coverage

5. **Task 4 (API - Complex):** ~60-90 min - OntologyGenerator.generate_with_feedback()
   - More complex integration
   - Multiple test scenarios
   - Feedback loop validation

## Testing Strategy

- **Unit tests:** ~80-100 tests total across all tasks
- **Integration tests:** Feedback loop validation (Task 4)
- **Performance tests:** Benchmarking (Task 1, Task 5)
- **Statistical tests:** Distribution analysis (Task 3)

## Commit Strategy

**Option A:** Single commit per task (5 commits, ~1-2 hours)
**Option B:** Group by track (2-3 commits, PERF + API + TESTS)
**Option C:** Single Batch 202 commit (~5 commits squashed)

Recommended: Option B for clarity and history tracking

## Success Criteria

- [ ] All 5 tasks implemented with full docstrings
- [ ] 80+ comprehensive tests created (target: 85-100)
- [ ] All tests passing (100% pass rate)
- [ ] Performance improvements documented (Tasks 1, 5)
- [ ] Code follows existing patterns (type hints, formatting, structure)
- [ ] Batch 202 committed and pushed to master

## Estimated Total Time

- Implementation + Testing: 4.5-6 hours
- Code review/validation: 30-45 min
- Commit/push: 10-15 min
- **Total: 5-7 hours** (full batch completion)

## Notes

- Tasks are independently implementable (minimal cross-dependencies)
- PERF tasks (1, 5) can validate existing optimization work
- API tasks (2, 4) build complementary functionality
- TESTS task (3) provides observability into scoring behavior
