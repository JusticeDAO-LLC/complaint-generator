import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_PREFIX = Path("integrations/ipfs_datasets")
EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "examples",
    "ipfs_datasets_py",
    "tests",
    "tmp",
}
EXCLUDED_TOP_LEVEL_FILES = {
    "batch_230_benchmark.py",
    "batch_231_llm_fallback_profile.py",
    "profile_generate_10k.py",
    "test_criticscor_comparisons.py",
    "test_extraction_config_validation.py",
    "test_parallel_validation_fix.py",
    "test_pipeline_error_recovery.py",
    "test_probate_integration.py",
    "test_legal_authority_hooks.py",
    "test_review_api.py",
    "test_web_evidence_hooks.py",
}


def _is_excluded(relative_path: Path) -> bool:
    if relative_path.parts and relative_path.parts[0] in EXCLUDED_DIR_NAMES:
        return True
    if any(part in EXCLUDED_DIR_NAMES for part in relative_path.parts[:-1]):
        return True
    return relative_path.name in EXCLUDED_TOP_LEVEL_FILES


def _imports_ipfs_datasets_py(file_path: Path) -> bool:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "ipfs_datasets_py" or alias.name.startswith("ipfs_datasets_py.") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "ipfs_datasets_py" or module.startswith("ipfs_datasets_py."):
                return True
    return False


def test_production_code_imports_ipfs_datasets_only_via_adapters():
    violating_paths = []

    for file_path in REPO_ROOT.rglob("*.py"):
        relative_path = file_path.relative_to(REPO_ROOT)
        if _is_excluded(relative_path):
            continue
        if relative_path.is_relative_to(ALLOWED_PREFIX):
            continue
        if _imports_ipfs_datasets_py(file_path):
            violating_paths.append(relative_path.as_posix())

    assert not violating_paths, (
        "Direct ipfs_datasets_py imports are only allowed under integrations/ipfs_datasets/. "
        f"Found violations: {violating_paths}"
    )