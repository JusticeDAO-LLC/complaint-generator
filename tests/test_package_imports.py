from __future__ import annotations

import ast
import importlib
import runpy
import sys
import tomllib
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from lib.runtime_ownership import (
    RUNTIME_ENTRYPOINT_GROUPS,
    VALID_RUNTIME_ROLES,
    entrypoint_groups_by_role,
    module_ownership_summary,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = REPO_ROOT
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
ARCHITECTURE_PATH = REPO_ROOT / "docs" / "ARCHITECTURE.md"

PRODUCTION_IMPORT_MODULES = [
    "applications.complaint_workspace",
    "applications.document_api",
    "integrations.ipfs_datasets.loader",
]

SCRIPT_ENTRYPOINTS = [
    "scripts/agentic_complaint_evidence_scraper.py",
    "scripts/agentic_scraper_cli.py",
    "scripts/backfill_claim_testimony_links.py",
    "scripts/check_hacc_routers.py",
    "scripts/enrich_email_timeline_authorities.py",
    "scripts/generate_decision_trees.py",
    "scripts/generate_email_search_plan.py",
    "scripts/generate_hacc_email_seed_plan.py",
    "scripts/gmail_duckdb_daemon.py",
]

PATH_STABLE_ENTRYPOINT_FILES = [
    "applications/complaint_workspace.py",
    "applications/document_api.py",
    "integrations/ipfs_datasets/loader.py",
    *SCRIPT_ENTRYPOINTS,
    "scripts/graphrag_email_manifest.py",
    "scripts/import_gmail_evidence.py",
    "scripts/import_local_eml_directory.py",
    "scripts/master_case_email.py",
    "scripts/process_hacc_pdfs_to_kg.py",
    "scripts/run_gmail_duckdb_pipeline.py",
    "scripts/run_hacc_adversarial_report.py",
    "scripts/run_hacc_grounded_pipeline.py",
    "scripts/run_hacc_preset_matrix.py",
    "scripts/synthesize_hacc_complaint.py",
]

ADAPTER_LOADED_ENTRYPOINTS = [
    "scripts/graphrag_email_manifest.py",
    "scripts/import_gmail_evidence.py",
    "scripts/import_local_eml_directory.py",
    "scripts/master_case_email.py",
    "scripts/run_gmail_duckdb_pipeline.py",
]


def test_runtime_entrypoint_groups_cover_required_roles() -> None:
    assert set(RUNTIME_ENTRYPOINT_GROUPS) == set(VALID_RUNTIME_ROLES)
    assert set(entrypoint_groups_by_role()) == {"cli", "web", "mediator", "workflow"}
    for role in VALID_RUNTIME_ROLES:
        assert RUNTIME_ENTRYPOINT_GROUPS[role], f"missing runtime entrypoints for role {role}"


def test_largest_runtime_modules_have_ownership_records() -> None:
    modules = {row["module_path"]: row for row in module_ownership_summary()}

    for module_path in (
        "applications.complaint_workspace",
        "scripts.synthesize_hacc_complaint",
        "mediator.mediator",
        "complaint_phases.denoiser",
    ):
        record = modules[module_path]
        assert record["owner"]
        assert record["primary_responsibility"]
        assert record["entrypoints"], f"missing entrypoints for {module_path}"


@dataclass(frozen=True, order=True)
class RestrictedImportViolation:
    """One statically discoverable production import that bypasses an adapter."""

    relative_path: str
    line_number: int
    imported_module: str
    restricted_module: str

    def describe(self) -> str:
        return f"{self.relative_path}:{self.line_number}: imports {self.imported_module}"


def _load_boundary_config() -> dict[str, Any]:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    return dict(pyproject["tool"]["complaint_generator"]["import_boundaries"])


def _python_files(package_name: str) -> Iterable[Path]:
    package_dir = REPO_ROOT / package_name
    return sorted(path for path in package_dir.rglob("*.py") if path.is_file())


def _absolute_import_roots(file_path: Path) -> set[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    import_roots: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            import_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            import_roots.add(node.module.split(".", 1)[0])

    return import_roots


def _imported_modules(file_path: Path) -> list[tuple[int, str]]:
    """Return static imports, including common literal dynamic-import forms."""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))

    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names)
            continue
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append((node.lineno, node.module))
            continue
        if not isinstance(node, ast.Call) or not node.args:
            continue

        first_argument = node.args[0]
        if not isinstance(first_argument, ast.Constant) or not isinstance(first_argument.value, str):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            imports.append((node.lineno, first_argument.value))
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "importlib"
        ):
            imports.append((node.lineno, first_argument.value))

    return imports


def _module_matches(imported_module: str, restricted_module: str) -> bool:
    return imported_module == restricted_module or imported_module.startswith(f"{restricted_module}.")


def _path_is_within(relative_path: Path, configured_path: str) -> bool:
    allowed_path = Path(configured_path)
    return relative_path == allowed_path or relative_path.is_relative_to(allowed_path)


def _restricted_import_violations(
    repo_root: Path,
    production_packages: Sequence[str],
    restricted_imports: Mapping[str, Mapping[str, Any]],
) -> list[RestrictedImportViolation]:
    """Scan configured production packages; tests and other repo files stay out of scope."""

    violations: list[RestrictedImportViolation] = []
    for package_name in production_packages:
        for file_path in sorted((repo_root / package_name).rglob("*.py")):
            relative_path = file_path.relative_to(repo_root)
            imported_modules = _imported_modules(file_path)
            for restricted_module, rule in restricted_imports.items():
                adapter_paths = list(rule["allowed_adapter_paths"])
                if any(_path_is_within(relative_path, path) for path in adapter_paths):
                    continue
                for line_number, imported_module in imported_modules:
                    if _module_matches(imported_module, restricted_module):
                        violations.append(
                            RestrictedImportViolation(
                                relative_path=relative_path.as_posix(),
                                line_number=line_number,
                                imported_module=imported_module,
                                restricted_module=restricted_module,
                            )
                        )

    return sorted(violations)


def test_configured_package_import_boundaries_are_enforced():
    boundary_config = _load_boundary_config()
    enforced_packages = list(boundary_config["enforced_packages"])
    allowed_imports = dict(boundary_config["allowed_imports"])
    enforced_package_set = set(enforced_packages)
    violations: list[str] = []

    for package_name in enforced_packages:
        allowed_for_package = set(allowed_imports[package_name])
        for file_path in _python_files(package_name):
            imported_roots = _absolute_import_roots(file_path)
            disallowed_roots = sorted(
                imported_root
                for imported_root in imported_roots & enforced_package_set
                if imported_root not in allowed_for_package
            )
            if disallowed_roots:
                relative_path = file_path.relative_to(REPO_ROOT).as_posix()
                violations.append(f"{relative_path}: {', '.join(disallowed_roots)}")

    assert not violations, (
        "Package import boundary violations found. Update the code or the documented "
        f"architecture contract before proceeding: {violations}"
    )


def test_import_boundary_config_covers_distributed_production_packages():
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    boundary_config = dict(pyproject["tool"]["complaint_generator"]["import_boundaries"])
    production_packages = list(boundary_config["production_packages"])
    operator_packages = list(boundary_config["operator_packages"])
    package_includes = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]
    distributed_package_roots = {pattern.split(".", 1)[0] for pattern in package_includes}

    assert len(production_packages) == len(set(production_packages))
    assert len(operator_packages) == len(set(operator_packages))
    assert set(production_packages).isdisjoint(operator_packages)
    assert set(production_packages) | set(operator_packages) == distributed_package_roots
    assert "tests" not in production_packages
    assert operator_packages == ["scripts"]
    for package_name in production_packages:
        assert (REPO_ROOT / package_name / "__init__.py").is_file()
    for package_name in operator_packages:
        assert (REPO_ROOT / package_name / "__init__.py").is_file()

    enforced_packages = set(boundary_config["enforced_packages"])
    allowed_imports = dict(boundary_config["allowed_imports"])
    assert set(allowed_imports) == enforced_packages
    for package_name, allowed_packages in allowed_imports.items():
        assert package_name in allowed_packages
        assert set(allowed_packages) <= enforced_packages

    for restricted_module, rule in dict(boundary_config["restricted_imports"]).items():
        adapter_paths = list(rule["allowed_adapter_paths"])
        assert adapter_paths, f"{restricted_module} has no adapter path"
        for configured_path in adapter_paths:
            path = Path(configured_path)
            assert not path.is_absolute() and ".." not in path.parts and len(path.parts) >= 2
            assert path.parts[0] in production_packages
            assert (REPO_ROOT / path).is_dir()

        for configured_path, imported_modules in dict(rule.get("temporary_exceptions", {})).items():
            path = Path(configured_path)
            assert path.parts and path.suffix == ".py"
            assert not path.is_absolute() and ".." not in path.parts
            assert path.parts[0] in production_packages
            assert (REPO_ROOT / path).is_file()
            assert imported_modules
            assert all(_module_matches(module, restricted_module) for module in imported_modules)


def test_import_boundary_config_is_documented():
    boundary_config = _load_boundary_config()
    enforced_packages = list(boundary_config["enforced_packages"])
    allowed_imports = dict(boundary_config["allowed_imports"])
    architecture = ARCHITECTURE_PATH.read_text(encoding="utf-8")

    assert "### Allowed Import Direction" in architecture
    assert "### Shared Code Rule" in architecture

    for package_name in enforced_packages:
        expected_imports = ", ".join(f"`{import_name}/`" for import_name in allowed_imports[package_name])
        assert f"| `{package_name}/` | {expected_imports} |" in architecture


def test_restricted_production_imports_use_configured_adapters():
    boundary_config = _load_boundary_config()
    restricted_imports = dict(boundary_config["restricted_imports"])
    violations = _restricted_import_violations(
        REPO_ROOT,
        list(boundary_config["production_packages"]),
        restricted_imports,
    )

    unexpected = []
    for violation in violations:
        rule = restricted_imports[violation.restricted_module]
        exceptions = dict(rule.get("temporary_exceptions", {}))
        allowed_modules = set(exceptions.get(violation.relative_path, []))
        if violation.imported_module not in allowed_modules:
            unexpected.append(violation.describe())

    assert not unexpected, (
        "Production modules must import restricted optional dependencies through their "
        f"configured adapter paths. Found direct imports: {unexpected}"
    )


def test_restricted_import_exceptions_are_precise_and_current():
    boundary_config = _load_boundary_config()
    restricted_imports = dict(boundary_config["restricted_imports"])
    violations = _restricted_import_violations(
        REPO_ROOT,
        list(boundary_config["production_packages"]),
        restricted_imports,
    )

    violations_by_module: dict[str, set[tuple[str, str]]] = {}
    for violation in violations:
        violations_by_module.setdefault(violation.restricted_module, set()).add(
            (violation.relative_path, violation.imported_module)
        )

    for restricted_module, rule in restricted_imports.items():
        exception_map = dict(rule.get("temporary_exceptions", {}))
        exception_pairs = {
            (relative_path, imported_module)
            for relative_path, imported_modules in exception_map.items()
            for imported_module in imported_modules
        }
        assert all(len(modules) == len(set(modules)) for modules in exception_map.values()), (
            f"duplicate exception modules for {restricted_module}"
        )
        assert exception_pairs == violations_by_module.get(restricted_module, set()), (
            f"Exceptions for {restricted_module} must exactly describe current production debt. "
            "Route removed imports through the adapter and delete their exception; add no broad "
            "or stale exemptions."
        )


def test_restricted_import_detector_excludes_tests_but_catches_production(tmp_path: Path):
    production_file = tmp_path / "applications" / "direct.py"
    adapter_file = tmp_path / "integrations" / "ipfs_datasets" / "adapter.py"
    test_file = tmp_path / "tests" / "test_upstream_contract.py"
    for file_path in (production_file, adapter_file, test_file):
        file_path.parent.mkdir(parents=True, exist_ok=True)
    production_file.write_text(
        "import ipfs_datasets_py\n"
        "from ipfs_datasets_py.logic import prove\n"
        "import importlib\n"
        "dynamic = importlib.import_module('ipfs_datasets_py.dynamic')\n"
        "legacy = __import__('ipfs_datasets_py.legacy')\n",
        encoding="utf-8",
    )
    adapter_file.write_text("import ipfs_datasets_py.logic\n", encoding="utf-8")
    test_file.write_text("from ipfs_datasets_py import optimizers\n", encoding="utf-8")

    violations = _restricted_import_violations(
        tmp_path,
        ["applications", "integrations"],
        {
            "ipfs_datasets_py": {
                "allowed_adapter_paths": ["integrations/ipfs_datasets"],
                "temporary_exceptions": {},
            }
        },
    )

    assert [violation.describe() for violation in violations] == [
        "applications/direct.py:1: imports ipfs_datasets_py",
        "applications/direct.py:2: imports ipfs_datasets_py.logic",
        "applications/direct.py:4: imports ipfs_datasets_py.dynamic",
        "applications/direct.py:5: imports ipfs_datasets_py.legacy",
    ]


def _is_sys_path_mutator_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in {"append", "extend", "insert", "remove", "pop", "clear"}:
        return False
    value = func.value
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "path"
        and isinstance(value.value, ast.Name)
        and value.value.id == "sys"
    )


def test_expected_entrypoints_do_not_mutate_sys_path_statically():
    offenders: list[str] = []
    for relative_path in PATH_STABLE_ENTRYPOINT_FILES:
        path = PROJECT_ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if _is_sys_path_mutator_call(node):
                offenders.append(f"{relative_path}:{node.lineno}")

    assert offenders == []


def test_optional_dependency_entrypoints_prime_the_adapter_before_direct_imports():
    offenders: list[str] = []
    for relative_path in ADAPTER_LOADED_ENTRYPOINTS:
        path = PROJECT_ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        adapter_calls = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ensure_import_paths"
        ]
        provider_imports = [
            node.lineno
            for node in ast.walk(tree)
            if (
                isinstance(node, ast.ImportFrom)
                and str(node.module or "").startswith("ipfs_datasets_py")
            )
            or (
                isinstance(node, ast.Import)
                and any(alias.name.startswith("ipfs_datasets_py") for alias in node.names)
            )
        ]
        if not adapter_calls or not provider_imports or min(adapter_calls) >= min(provider_imports):
            offenders.append(relative_path)

    assert offenders == [], (
        "Optional-dependency entrypoints must initialize the repository-owned adapter "
        f"loader before provider imports: {offenders}"
    )


def test_production_package_imports_do_not_change_sys_path():
    before = list(sys.path)

    for module_name in PRODUCTION_IMPORT_MODULES:
        module_path_before = list(sys.path)
        importlib.import_module(module_name)
        assert sys.path == module_path_before, f"{module_name} changed sys.path during import"

    assert sys.path == before


def test_script_entrypoints_load_without_changing_sys_path():
    before = list(sys.path)

    for relative_path in SCRIPT_ENTRYPOINTS:
        runpy.run_path(str(PROJECT_ROOT / relative_path), run_name=f"test_import_{relative_path}")

    assert sys.path == before
