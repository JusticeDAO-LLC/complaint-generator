"""CIMP-CON-06: root maintenance scripts live under scripts/maintenance."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "scripts" / "maintenance"
MODULE_NAMES = {
    "add_dedup_factory",
    "add_init_vars",
    "add_optimization_methods",
    "batch_230_benchmark",
    "batch_231_llm_fallback_profile",
    "complete_optimizer_integration",
    "profile_generate_10k",
    "update_detect_graph_type",
}
SKIP_PARTS = {".git", ".venv", "__pycache__", "external", "node_modules"}


def test_maintenance_scripts_leave_the_repository_root() -> None:
    for module_name in MODULE_NAMES:
        filename = f"{module_name}.py"
        assert not (ROOT / filename).exists(), filename
        destination = DESTINATION / filename
        assert destination.is_file(), filename
        assert destination.stat().st_size > 0, filename
    assert (ROOT / "main.py").is_file()


def test_no_python_file_imports_maintenance_scripts_as_top_level_modules() -> None:
    offenders: list[str] = []
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError) as exc:
            offenders.append(f"{relative}: {exc}")
            continue
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported.extend(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.append(node.module.split(".", 1)[0])
            for name in imported:
                if name in MODULE_NAMES:
                    offenders.append(f"{relative} imports {name}")
    assert offenders == []
