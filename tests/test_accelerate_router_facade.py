import pytest
from unittest.mock import patch

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

from integrations.ipfs_accelerate.routers import (
    accelerate_provider_name,
    normalize_accelerate_provider,
    router_symbol_status,
)


def test_provider_aliases_keep_complaint_names_and_map_accelerate_names():
    assert accelerate_provider_name("huggingface") == "hf_inference_api"
    assert accelerate_provider_name("local") == "local_hf"
    assert accelerate_provider_name("copilot_cli") == "copilot_cli"
    assert accelerate_provider_name("") == ""
    assert normalize_accelerate_provider("local_hf") == "huggingface"
    assert normalize_accelerate_provider("hf_inference_api") == "huggingface"
    assert normalize_accelerate_provider("system_one") == "typesafe"
    assert normalize_accelerate_provider("openai_vision") == "openai"
    assert normalize_accelerate_provider("copilot_cli") == "copilot_cli"
    assert normalize_accelerate_provider("") is None
    assert normalize_accelerate_provider("p2p_task_queue") == "p2p_task_queue"


def test_router_symbol_status_uses_the_facade_loader():
    with patch(
        "integrations.ipfs_accelerate.routers.load_llm_symbols",
        return_value=(lambda **kwargs: "ok", None, None),
    ):
        status = router_symbol_status("llm_router")
    assert status["available"] is True
    assert status["error"] == ""
