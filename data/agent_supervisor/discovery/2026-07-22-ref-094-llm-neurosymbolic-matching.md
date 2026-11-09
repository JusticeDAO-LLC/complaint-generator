# REF-094 LLM Neurosymbolic Matching

Date: 2026-07-22
Source finding: `complaint_phases/neurosymbolic_matcher.py:269`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-094-codebase-scan-7bc1d7368daf.md`

## Decision

The annotation marked a functional runtime gap. `NeurosymbolicMatcher` accepted
a mediator and routed semantic checks through `_llm_semantic_match`, but that
method always returned an unsatisfied, zero-confidence placeholder. Configuring
an LLM backend therefore had no effect on requirement matching.

The matcher now calls the repository's synchronous `mediator.query_backend`
contract with a bounded, claim-first graph context and a strict JSON response
schema. Plain, Markdown-fenced, and prose-prefixed JSON responses are supported.
Satisfaction must be a JSON boolean, confidence is clamped to the closed unit
interval, evidence references are checked against the supplied graph, and a
positive assessment without evidence is rejected. Missing backends, backend
exceptions, and malformed responses are logged and fail closed so existing
symbolic results remain available.

## Focused Validation

`test_llm_semantic_matching_uses_grounded_fenced_json` verifies backend
invocation, prompt grounding, fenced-JSON parsing, evidence-reference
validation, and confidence clamping.
`test_match_claims_to_law_applies_llm_semantic_assessment` verifies that a
validated assessment affects the public matching workflow and preserves its
evidence in claim and flattened requirement results.
`test_llm_semantic_matching_fails_closed_when_backend_fails` verifies that a
backend exception is observable and returns the safe semantic fallback.

Required syntax validation:

```text
python3 -m py_compile complaint_phases/neurosymbolic_matcher.py
```
