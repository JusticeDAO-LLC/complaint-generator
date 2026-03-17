# Backend Resilience Policy Inventory

_Last updated: 2026-02-25_

Scope: `ipfs_datasets_py/ipfs_datasets_py/optimizers`

Goal: track timeout/retry/circuit-breaker policy coverage for external/backend calls.

## Canonical Policy Primitive
- `optimizers/common/backend_resilience.py`
  - `BackendCallPolicy`
  - `execute_with_resilience(...)`
- Common exceptions used by wrappers:
  - `OptimizerTimeoutError`
  - `RetryableBackendError`
  - `CircuitBreakerOpenError`

## Current Coverage Matrix

### Covered by shared resilience wrapper
- `graphrag/ontology_generator.py`
  - `_invoke_llm_extraction_backend(...)` wraps callable/generate/complete backend calls.
- `graphrag/ontology_refinement_agent.py`
  - `propose_feedback(...)` wraps LLM backend invocation.
- `agentic/llm_integration.py`
  - `OptimizerLLMRouter.generate(...)` wraps provider calls with per-provider policy + breaker.
- `logic_theorem_optimizer/logic_extractor.py`
  - `_query_llm(...)` uses shared wrapper around backend adapter calls.
- `logic_theorem_optimizer/llm_backend.py`
  - `LLMBackendAdapter.generate(...)` uses per-backend policy + persistent breaker map.
- `logic_theorem_optimizer/formula_translation.py`
  - Translator parse and NL-generation backend calls route through shared wrapper.
- `llm_lazy_loader.py`
  - Lazy loader call surfaces (`__call__`, wrapped `__getattr__` methods) route through
    `execute_with_resilience(...)` with explicit `BackendCallPolicy` and circuit-breaker.

## Gaps / Follow-Ups
- Verify all remaining external-call surfaces that do not currently route through:
  - `execute_with_resilience(...)`, or
  - an equivalent policy object with explicit timeout/retry/breaker settings.
- Keep policy-conformance tests enforcing:
  - wrapper usage,
  - policy/breaker wiring markers, and
  - service-name convention markers on critical backend modules.
- Keep resilience outcome conformance checks enforcing that timeout/retry/circuit-open
  exception paths map to explicit fallback/error-accounting behavior.
- Document default policy values per optimizer type and define allowed overrides.
- Ensure error code mapping for timeout/retry/circuit-open outcomes is consistent in logs/metrics.

## Suggested Next Execution Order
1. Keep conformance tests enforcing policy defaults and resilience outcome mappings.
2. Add troubleshooting docs section mapping resilience exceptions to operator actions (docs/obs lane).
3. Validate log/metric status mapping consistency for timeout/retry/circuit-open outcomes.
