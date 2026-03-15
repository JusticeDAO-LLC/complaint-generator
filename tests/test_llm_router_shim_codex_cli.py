import signal
import subprocess
from unittest.mock import patch

import pytest


def test_codex_cli_timeout_raises_helpful_error():
    from ipfs_datasets_py.llm_router import LLMRouterError, generate_text

    class FakePopen:
        def __init__(self, *args, **kwargs):
            self.pid = 43210
            self.returncode = None

        def communicate(self, input=None, timeout=None):
            raise subprocess.TimeoutExpired(cmd=["codex", "exec"], timeout=timeout)

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            self.returncode = -9
            return self.returncode

    with patch("ipfs_datasets_py.llm_router.shutil.which", return_value="/usr/local/bin/codex"):
        with patch("ipfs_datasets_py.llm_router.subprocess.Popen", return_value=FakePopen()):
            with patch("ipfs_datasets_py.llm_router.os.killpg") as killpg_mock:
                with pytest.raises(LLMRouterError) as exc_info:
                    generate_text(
                        prompt="Hello",
                        provider="codex_cli",
                        model_name="gpt-5.2-codex",
                        timeout=12,
                    )

    assert killpg_mock.call_count >= 1
    assert killpg_mock.call_args_list[-1].args == (43210, signal.SIGKILL)
    assert "timed out" in str(exc_info.value).lower()
    assert "12" in str(exc_info.value)
