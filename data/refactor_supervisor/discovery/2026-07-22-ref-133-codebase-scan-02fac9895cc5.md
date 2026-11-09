# REF-133 Codebase Scan Finding

Date: 2026-07-22
Fingerprint: 02fac9895cc5b40e5a02e9bcf355230bf472d7da
Kind: placeholder_runtime_path
Source: lib/formal_logic/core.py:112
Priority: P1
Track: runtime

## Evidence

```text
raise NotImplementedError
```

## Resolution

`Proposition.__str__` is an abstract interface, so `ABC` prevents instances that
do not provide the method and the explicit `NotImplementedError` was not a
reachable fallback for a valid proposition. The placeholder body was replaced
with a contract docstring requiring a canonical representation suitable for
model lookup. This preserves abstract-class enforcement while avoiding a
redundant runtime exception and explaining the requirement to implementers.

`Proposition.evaluate` is tracked independently by REF-134 and is intentionally
outside this finding.
