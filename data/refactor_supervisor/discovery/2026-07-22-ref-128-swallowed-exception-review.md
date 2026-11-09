# REF-128 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/llm.py:331`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-128-codebase-scan-878fee469cd6.md`

## Decision

The Arch Router response parser intentionally accepts malformed JSON and plain
text because model responses can fail to follow the JSON-only instruction. Its
regex and plain-text fallbacks are therefore required behavior. The flagged
handler was nevertheless too broad: catching `Exception` also concealed
unexpected failures in the JSON parser or route extraction and made those
failures look like ordinary non-JSON model output.

The handler now catches only `json.JSONDecodeError`, the failure that represents
an invalid JSON response. Malformed model output still uses the existing
fallbacks, while unexpected parser/runtime failures propagate to the existing
Arch Router error boundary. That boundary records `arch_router_status` as
`fallback_error` and includes `arch_router_error` in adapter metadata, preserving
the primary generation fallback without silently discarding the cause.

## Focused Validation

`tests/test_ref_128_llm_arch_router_parsing.py` verifies valid JSON, fenced JSON,
malformed-JSON regex recovery, and plain-text responses. It also injects an
unexpected parser failure and verifies that `_parse_arch_router_route` does not
swallow it.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/llm.py
```

Validation results:

- PASS — `python3 -m py_compile integrations/ipfs_datasets/llm.py`
- PASS — `python3 -m pytest tests/test_ref_128_llm_arch_router_parsing.py -q`
  (6 passed)
- PASS — `RUN_LLM_TESTS=1 python3 -m pytest` with the two existing mocked Arch
  Router selection and unknown-route fallback cases selected (2 passed)
