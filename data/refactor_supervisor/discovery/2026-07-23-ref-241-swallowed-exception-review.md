# REF-241 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:298`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-241-codebase-scan-9ed9c2dc563c.md`

## Decision

The flagged bare exception handler silently discarded every failure while
deleting a property test's temporary log. The test also left its `FileHandler`
open and attached to a process-wide named logger at the end of each Hypothesis
example. That leaked file descriptors and made cleanup platform-dependent.

The test now owns the log through a temporary-directory context and explicitly
detaches and closes the handler in a `finally` block before the directory is
removed. Cleanup failures propagate to pytest, and handler closure is still
attempted if detaching the handler fails.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/mcp/unit/test_mcplusplus_v39_session84_properties.py::TestStructuredLoggingProperties::test_json_output_always_parses -q
```

Validation results:

- PASS — `python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_properties.py`
- PASS — focused JSON logging property test (1 passed)
- PASS — full property-test module (10 passed)

The pytest run emitted the repository's existing `pytest-asyncio` configuration
deprecation warning; this change introduced no test warnings.
