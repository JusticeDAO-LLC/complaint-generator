# REF-118 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/sweep_ranker.py:20`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-118-codebase-scan-5f056c29355d.md`

## Decision

The helper converts optional metrics from persisted sweep results. Missing or
malformed values are expected input problems and should continue to produce
`None`; `float` reports those conversion failures with `TypeError`, `ValueError`,
or `OverflowError`.

The broad `Exception` handler also concealed unexpected failures raised by
custom numeric conversion logic, making runtime defects indistinguishable from
malformed sweep data. The handler now catches only the expected conversion
exceptions so unexpected failures remain visible for diagnosis. The related
weight parser now catches only `ValueError`, the expected failure for its
normalized string tokens.

## Focused Validation

`tests/test_sweep_ranker.py` verifies that missing, malformed, incompatible, and
overflowing values remain non-fatal and that unexpected conversion failures are
no longer swallowed. It also covers malformed command-line weights and
unexpected failures in weight conversion.

Required syntax validation:

```text
python3 -m py_compile examples/sweep_ranker.py
```
