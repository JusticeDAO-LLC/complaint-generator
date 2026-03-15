import subprocess
from unittest.mock import patch

import pytest


def test_codex_cli_timeout_raises_helpful_error():
    from ipfs_datasets_py.llm_router import LLMRouterError, generate_text

    with patch("ipfs_datasets_py.llm_router.shutil.which", return_value="/usr/local/bin/codex"):
        with patch(
            "ipfs_datasets_py.llm_router.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["codex", "exec"], timeout=12),
        ):
            with pytest.raises(LLMRouterError) as exc_info:
                generate_text(
                    prompt="Hello",
                    provider="codex_cli",
                    model_name="gpt-5.2-codex",
                    timeout=12,
                )

    assert "timed out" in str(exc_info.value).lower()
    assert "12" in str(exc_info.value)
