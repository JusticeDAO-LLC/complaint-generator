# REF-126 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/llm.py:127`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-126-codebase-scan-5ad6e5b2a62e.md`

## Decision

The OpenAI API-key resolver checks environment variables, the
`ipfs_datasets_py` secrets vault, keyring, and common local configuration files
in that order. Continuing to keyring and common-file lookup when the optional
vault fails is an intentional availability fallback. The flagged handler was
nevertheless a defect because it silently discarded vault initialization and
access failures, making a degraded credential lookup indistinguishable from a
working, empty vault.

The resolver now emits a warning with exception information before continuing
through the existing fallback chain. The message identifies only the failed
credential source and the fallback sources; it never includes an API key, a
candidate environment-variable value, or another secret. Successful vault
lookups retain the existing behavior and do not emit a warning.

## Focused Validation

`tests/test_ref_126_openai_vault_fallback.py` verifies that a vault failure is
observable while keyring still supplies the requested key, that exception
context is retained, and that the resolved key is absent from the log. It also
verifies that a successful vault lookup has a clean warning log.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/llm.py
```

Validation results:

- PASS — `python3 -m py_compile integrations/ipfs_datasets/llm.py`
- PASS — `python3 -m pytest tests/test_ref_126_openai_vault_fallback.py -q`
  (2 passed)
- PASS — `python3 -m pytest tests/test_ref_126_openai_vault_fallback.py tests/test_ref_124_llm_vault_fallback.py -q`
  (4 passed)
