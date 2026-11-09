# REF-215 Codebase Scan Finding

Date: 2026-07-22
Fingerprint: 262ec5d876de373d7f6bc9d2de4d9353830bbbff
Kind: swallowed_exception
Source: mediator/evidence_hooks.py:1398
Priority: P1
Track: runtime

## Evidence

```text
except Exception as e:
```

## Suggested Handling

Review the finding in context, decide whether it represents a bug, missing test,
maintenance risk, or false positive, and land a small fix with validation. If the
finding is a false positive, document why in the changed code or discovery notes
so the supervisor does not keep re-adding the same work.

## Resolution

The handler represented a runtime bug: `get_evidence_by_cid` returned `None` for
both a valid missing record and a failed DuckDB query or record decode, so callers
could silently treat unavailable evidence state as absent evidence. The lookup now
logs structured operation and error-type context, closes its connection on query
failure, and raises `EvidenceQueryError` with the original exception chained.
`None` is reserved for a successful query with no matching CID. A focused unit
test covers the typed failure, cause, log context, and connection cleanup.
