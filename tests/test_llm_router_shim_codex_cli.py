import signal
import subprocess
from pathlib import Path
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


def test_codex_cli_can_disable_model_retry():
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
        with patch("ipfs_datasets_py.llm_router.subprocess.Popen", return_value=FakePopen()) as popen_mock:
            with patch("ipfs_datasets_py.llm_router.os.killpg"):
                with pytest.raises(LLMRouterError):
                    generate_text(
                        prompt="Hello",
                        provider="codex_cli",
                        model_name="gpt-5.2-codex",
                        timeout=12,
                        disable_model_retry=True,
                    )

    assert popen_mock.call_count == 1


def test_codex_cli_multimodal_passes_image_flags(tmp_path: Path):
    from ipfs_datasets_py.multimodal_router import generate_multimodal_text

    image_path = tmp_path / "icon.png"
    image_path.write_bytes(b"fake-image")

    class FakePopen:
        def __init__(self, args, *popen_args, **popen_kwargs):
            self.args = args
            self.pid = 98765
            self.returncode = 0
            output_index = self.args.index("--output-last-message") + 1
            Path(self.args[output_index]).write_text("codex multimodal ok", encoding="utf-8")

        def communicate(self, input=None, timeout=None):
            return ('{"type":"message","role":"assistant","text":"codex multimodal ok"}\n', "")

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

    with patch("ipfs_datasets_py.llm_router.shutil.which", return_value="/usr/local/bin/codex"):
        with patch("ipfs_datasets_py.llm_router.subprocess.Popen", side_effect=FakePopen) as popen_mock:
            result = generate_multimodal_text(
                "Review this image.",
                provider="codex_cli",
                model_name="gpt-5.3-codex",
                image_paths=[image_path],
                system_prompt="Describe the screenshot.",
            )

    assert result == "codex multimodal ok"
    cmd = popen_mock.call_args.args[0]
    assert "--image" in cmd
    assert str(image_path) in cmd
