"""Cold imports must work without initializing optional backend stacks."""

from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
ROOT = Path(__file__).resolve().parents[1]


def _cold_import(source: str, *, allowed_adapters: tuple[str, ...] = ()) -> None:
    setup = f"""
import sys
from importlib.abc import MetaPathFinder

sys.path.insert(0, {str(ROOT)!r})
allowed_adapters = {allowed_adapters!r}
attempted = []
backend_roots = (
    "ipfs_datasets_py", "ipfs_accelerate_py", "ipfs_kit_py",
    "torch", "numpy", "spacy", "pypdf", "pdfplumber", "transformers",
)

def forbidden(name):
    if name.startswith("integrations.ipfs_datasets."):
        adapter = name.split(".")[2]
        return adapter not in allowed_adapters
    return any(name == root or name.startswith(root + ".") for root in backend_roots)

class BackendGuard(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if forbidden(fullname):
            attempted.append(fullname)
            raise RuntimeError("Optional backend imported during startup: " + fullname)

sys.meta_path.insert(0, BackendGuard())
"""
    program = setup + "\n" + textwrap.dedent(source) + "\n" + textwrap.dedent("""
        assert not attempted, attempted
        assert not [name for name in sys.modules if forbidden(name)]
        print("cold import passed")
    """)
    result = subprocess.run(
        [sys.executable, "-I", "-c", program],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "cold import passed"


@pytest.mark.parametrize(
    ("source", "allowed_adapters"),
    [
        (
            "import integrations\nassert 'integrations.ipfs_datasets' not in sys.modules",
            (),
        ),
        (
            "from integrations import ipfs_datasets\n"
            "assert ipfs_datasets.__name__ == 'integrations.ipfs_datasets'\n"
            "assert 'store_bytes' in dir(ipfs_datasets)",
            (),
        ),
        ("import integrations.ipfs_datasets.loader", ("loader",)),
        ("import integrations.ipfs_accelerate.watchdog", ("loader",)),
    ],
    ids=["integration-package", "datasets-public-import", "adapter-loader", "watchdog"],
)
def test_cold_import_avoids_optional_backends(source, allowed_adapters):
    _cold_import(source, allowed_adapters=allowed_adapters)


def test_public_type_exports_resolve_to_the_original_objects():
    _cold_import(
        """
        from integrations import ipfs_datasets
        from integrations.ipfs_datasets import CaseArtifact, normalize_degraded_reason
        from integrations.ipfs_datasets.types import CaseArtifact as DirectCaseArtifact

        assert CaseArtifact is DirectCaseArtifact
        assert ipfs_datasets.CaseArtifact is DirectCaseArtifact
        assert normalize_degraded_reason(" reason ") == "reason"
        assert 'integrations.ipfs_datasets.types' in sys.modules
        """,
        allowed_adapters=("types",),
    )


def test_renamed_export_and_unknown_attribute_keep_public_import_behavior():
    _cold_import(
        """
        from types import ModuleType
        import integrations
        from integrations import ipfs_datasets

        pipeline = ModuleType('integrations.ipfs_datasets.draft_logic_pipeline')
        pipeline.run_pipeline = lambda: 'pipeline result'
        sys.modules[pipeline.__name__] = pipeline
        from integrations.ipfs_datasets import run_draft_logic_pipeline

        assert run_draft_logic_pipeline is pipeline.run_pipeline
        assert run_draft_logic_pipeline() == 'pipeline result'
        for package in (integrations, ipfs_datasets):
            try:
                package.nonexistent_export
            except AttributeError as exc:
                assert 'nonexistent_export' in str(exc)
            else:
                raise AssertionError('Unknown export did not raise AttributeError')
        del sys.modules[pipeline.__name__]
        """,
    )
