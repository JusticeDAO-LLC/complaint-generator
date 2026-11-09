# REF-120 Codebase Scan Finding

Date: 2026-07-22
Fingerprint: 1026e36dfbd6f72bd8b7a2f888fa3d200d825c60
Kind: swallowed_exception
Source: integrations/ipfs_datasets/graphrag.py:128
Priority: P1
Track: runtime

## Evidence

```text
except Exception:
```

## Suggested Handling

Review the finding in context, decide whether it represents a bug, missing test,
maintenance risk, or false positive, and land a small fix with validation. If the
finding is a false positive, document why in the changed code or discovery notes
so the supervisor does not keep re-adding the same work.
