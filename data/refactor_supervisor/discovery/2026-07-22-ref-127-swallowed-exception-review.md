# REF-127 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/llm.py:137`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-127-codebase-scan-16bcf37c319c.md`

## Decision

The OpenAI API-key resolver checks environment variables, the
`ipfs_datasets_py` secrets vault, keyring, and common local configuration files
in that order. Continuing to common-file lookup when keyring is unavailable or
its backend fails is an intentional availability fallback. The flagged handler
was nevertheless a defect because it silently hid the failed credential source,
making degraded resolution indistinguishable from a configured but empty
keyring.

The handler now emits a warning with the original exception before continuing
to common-file lookup. The message identifies the failed backend and the
selected fallback without logging an API key, a candidate environment value,
or another secret. Successful keyring lookups retain the existing behavior and
do not emit a warning.

## Focused Validation

`tests/test_ref_127_openai_keyring_fallback.py` verifies that a keyring backend
failure and its exception context are observable while common-file lookup still
supplies the key. It also verifies that no key value reaches the warning and
that a successful keyring lookup remains silent.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/llm.py
```

Validation results:

- PASS — `python3 -m py_compile integrations/ipfs_datasets/llm.py`
- PASS — `python3 -m pytest tests/test_ref_127_openai_keyring_fallback.py tests/test_ref_126_openai_vault_fallback.py -q`
  (4 passed)
