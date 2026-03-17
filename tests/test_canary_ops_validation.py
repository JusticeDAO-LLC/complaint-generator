import subprocess
import sys
from pathlib import Path


def test_validate_canary_ops_script_passes():
    repo_root = Path(__file__).resolve().parents[1]
    validator = repo_root / "scripts" / "validate_canary_ops.py"

    result = subprocess.run(
        [sys.executable, str(validator)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"validator failed with code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "Canary ops validation passed" in result.stdout
