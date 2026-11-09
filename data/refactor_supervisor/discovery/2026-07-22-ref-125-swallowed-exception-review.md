# REF-125 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/llm.py:96`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-125-codebase-scan-9d6be93589b3.md`

## Decision

The keyring lookup is one step in a deliberate Hugging Face token-resolution
chain: environment variables and the IPFS datasets secrets vault take
precedence, while the Hugging Face client token cache follows keyring. A
keyring backend can be installed but unavailable at runtime, so retaining the
fallback is necessary. The broad exception handler was nevertheless a defect
because it silently hid that credential lookup had degraded.

The handler now emits a warning with the original exception before consulting
the Hugging Face client token cache. The message identifies both the failed
backend and selected fallback without logging a token value. Successful
keyring lookups remain silent, and the token-resolution precedence and return
shape are unchanged.

## Focused Validation

`tests/test_ref_125_hf_keyring_fallback.py` verifies that a keyring backend
failure and its cause are observable while the Hugging Face client cache still
supplies the token. It also verifies that a successful keyring lookup does not
emit a fallback warning.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/llm.py
```

Validation results:

- PASS — `python3 -m py_compile integrations/ipfs_datasets/llm.py`
- PASS — `python3 -m pytest tests/test_ref_125_hf_keyring_fallback.py -q`
  (2 passed)
- PASS — `RUN_LLM_TESTS=1 python3 -m pytest -q` with the three existing
  Hugging Face cache, vault, and keyring token-resolution cases selected
  (3 passed)

An additional gated run of the complete Hugging Face router module produced 12
passes and one expected network skip. Its remaining failure is outside REF-125:
an existing OpenAI preflight test asserts an older error string than the current
implementation returns.
