"""Checker tests for the versioned module-interface contract (CIMP-MOD-03).

Fixtures are temporary modules. These tests do not import application packages.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "docs" / "architecture" / "module_interface_schema.json"
CHECKER = REPO_ROOT / "scripts" / "check_module_interface.py"
SCHEMA_ID = "complaint-generator/module-interface-schema@1"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
REQUIRED = ["schema", "module", "version", "owner_modules", "public_symbols"]


def _write(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")


def _run_checker(tmp_path: Path, module_name: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(CHECKER), module_name],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


def _plant_owner(tmp_path: Path, package: str, body: str) -> None:
    _write(tmp_path / package / "__init__.py", "")
    _write(tmp_path / package / "owner.py", body)


def _plant_interface(tmp_path: Path, package: str, body: str) -> None:
    _write(tmp_path / package / "__init__.py", "")
    _write(tmp_path / package / "interface.py", body)


def test_schema_requires_versioned_interface_fields() -> None:
    document = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert document["schema"] == SCHEMA_ID
    assert document["interface_schema"] == INTERFACE_SCHEMA
    assert document["describes"]["INTERFACE_SCHEMA"] == INTERFACE_SCHEMA
    assert document["required"] == REQUIRED
    pattern = document["properties"]["version"]["pattern"]
    import re

    assert re.fullmatch(pattern, "1.0.0")
    assert re.fullmatch(pattern, "1.0") is None
    assert re.fullmatch(pattern, "1") is None
    for field in REQUIRED:
        assert field in document["properties"]


def test_checker_accepts_conforming_interface(tmp_path: Path) -> None:
    package = "cimp_mod03_ok"
    _plant_owner(
        tmp_path,
        package,
        '''
        def public_entry(value):
            """Owner symbol. Importing this module is not part of the check."""
            return value

        class PublicRecord:
            pass

        raise RuntimeError("owner module must be parsed, not imported")
        ''',
    )
    _plant_interface(
        tmp_path,
        package,
        f'''
        INTERFACE_SCHEMA = "{INTERFACE_SCHEMA}"
        INTERFACE_VERSION = "1.0.0"
        OWNER_MODULES = ("{package}.owner",)
        PUBLIC_SYMBOLS = ("public_entry", "PublicRecord")
        ''',
    )
    result = _run_checker(tmp_path, f"{package}.interface")
    assert result.returncode == 0, result.stderr
    assert f"module-interface ok: {package}.interface" in result.stdout


def test_checker_accepts_empty_surface_when_facade_only(tmp_path: Path) -> None:
    package = "cimp_mod03_facade"
    _plant_interface(
        tmp_path,
        package,
        f'''
        INTERFACE_SCHEMA = "{INTERFACE_SCHEMA}"
        INTERFACE_VERSION = "1.0.0"
        OWNER_MODULES = ()
        PUBLIC_SYMBOLS = ()
        STATUS = "facade-only"
        ''',
    )
    result = _run_checker(tmp_path, f"{package}.interface")
    assert result.returncode == 0, result.stderr
    assert "module-interface ok:" in result.stdout


def test_checker_rejects_empty_surface_without_facade_status(tmp_path: Path) -> None:
    package = "cimp_mod03_empty"
    _plant_interface(
        tmp_path,
        package,
        f'''
        INTERFACE_SCHEMA = "{INTERFACE_SCHEMA}"
        INTERFACE_VERSION = "1.0.0"
        OWNER_MODULES = ()
        PUBLIC_SYMBOLS = ()
        ''',
    )
    result = _run_checker(tmp_path, f"{package}.interface")
    assert result.returncode != 0
    assert "empty public surface requires STATUS facade-only" in result.stderr


def test_checker_rejects_missing_version(tmp_path: Path) -> None:
    package = "cimp_mod03_noversion"
    _plant_owner(
        tmp_path,
        package,
        '''
        def public_entry():
            return None
        ''',
    )
    _plant_interface(
        tmp_path,
        package,
        f'''
        INTERFACE_SCHEMA = "{INTERFACE_SCHEMA}"
        OWNER_MODULES = ("{package}.owner",)
        PUBLIC_SYMBOLS = ("public_entry",)
        ''',
    )
    result = _run_checker(tmp_path, f"{package}.interface")
    assert result.returncode != 0
    assert "missing version" in result.stderr


def test_checker_rejects_partial_version(tmp_path: Path) -> None:
    package = "cimp_mod03_badversion"
    _plant_interface(
        tmp_path,
        package,
        f'''
        INTERFACE_SCHEMA = "{INTERFACE_SCHEMA}"
        INTERFACE_VERSION = "1.0"
        OWNER_MODULES = ()
        PUBLIC_SYMBOLS = ()
        STATUS = "facade-only"
        ''',
    )
    result = _run_checker(tmp_path, f"{package}.interface")
    assert result.returncode != 0
    assert "major.minor.patch" in result.stderr


def test_checker_rejects_server_starting_import(tmp_path: Path) -> None:
    package = "cimp_mod03_server"
    _write(tmp_path / package / "__init__.py", "")
    _write(
        tmp_path / package / "boot_server.py",
        '''
        from http.server import BaseHTTPRequestHandler, HTTPServer

        HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler).serve_forever()
        ''',
    )
    _plant_interface(
        tmp_path,
        package,
        f'''
        import {package}.boot_server

        INTERFACE_SCHEMA = "{INTERFACE_SCHEMA}"
        INTERFACE_VERSION = "1.0.0"
        OWNER_MODULES = ()
        PUBLIC_SYMBOLS = ()
        STATUS = "facade-only"
        ''',
    )
    result = _run_checker(tmp_path, f"{package}.interface")
    assert result.returncode != 0
    assert "server-starting import" in result.stderr
    assert "boot_server" in result.stderr


def test_checker_rejects_public_symbol_missing_from_owner(tmp_path: Path) -> None:
    package = "cimp_mod03_missing_symbol"
    _plant_owner(
        tmp_path,
        package,
        '''
        def other_entry():
            return "present"
        ''',
    )
    _plant_interface(
        tmp_path,
        package,
        f'''
        INTERFACE_SCHEMA = "{INTERFACE_SCHEMA}"
        INTERFACE_VERSION = "1.0.0"
        OWNER_MODULES = ("{package}.owner",)
        PUBLIC_SYMBOLS = ("not_defined",)
        ''',
    )
    result = _run_checker(tmp_path, f"{package}.interface")
    assert result.returncode != 0
    assert "public symbol 'not_defined' is not defined in an owner module" in result.stderr


def test_checker_requires_a_module_name() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode != 0


@pytest.mark.parametrize("field", REQUIRED)
def test_schema_properties_cover_required_field(field: str) -> None:
    document = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert document["properties"][field]["type"] in {"string", "array"}
