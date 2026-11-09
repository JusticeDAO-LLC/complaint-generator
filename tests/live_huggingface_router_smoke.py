"""Optional Hugging Face transport check; invoke this file explicitly.

Run with: python -m pytest --run-llm --run-network tests/live_huggingface_router_smoke.py
Requires an explicitly configured Hugging Face credential and may incur costs.
This external-provider smoke is separate from mandatory offline Grok campaign checks.
"""
import pytest
from tests.test_ipfs_llm_huggingface_router import (
    llm, _live_hf_token, _live_hf_bill_to_header, _run_live_hf_router_smoke,
)

pytestmark = pytest.mark.no_auto_network


@pytest.mark.llm
@pytest.mark.network
def test_generate_text_with_metadata_live_huggingface_router_smoke():
    if not llm.LLM_ROUTER_AVAILABLE:
        pytest.skip(f"llm_router unavailable: {llm.LLM_ROUTER_ERROR}")

    if not _live_hf_token():
        pytest.skip("Set a Hugging Face token in the environment or log in with huggingface_hub to run the live Hugging Face router smoke test")

    model_name, payload = _run_live_hf_router_smoke(
        "Reply with exactly OK.",
        headers={
            "X-Title": "Complaint Generator Smoke Test",
            **_live_hf_bill_to_header(),
        },
        max_tokens=8,
        temperature=0.0,
        timeout=45,
    )

    assert payload["status"] == "available", payload
    assert payload["effective_provider_name"] == "openrouter"
    assert payload["effective_model_name"] == model_name
    assert payload["router_base_url"] == llm.HF_ROUTER_DEFAULT_BASE_URL
    assert payload["text"].strip(), payload
