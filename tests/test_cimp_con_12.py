"""CIMP-CON-12: applications.interface lazily exports its public symbols."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_interface_lazy_exports_do_not_import_complaint_workspace() -> None:
    script = textwrap.dedent(
        """
        import pathlib
        import sys

        _exists = pathlib.Path.exists

        def _exists_or_missing(self, *, follow_symlinks=True):
            try:
                return _exists(self, follow_symlinks=follow_symlinks)
            except PermissionError:
                return False

        pathlib.Path.exists = _exists_or_missing

        import applications.interface as interface

        assert "applications.complaint_workspace" not in sys.modules
        assert "mediator.mediator" not in sys.modules
        assert "document_pipeline" not in sys.modules
        assert interface.INTERFACE_SCHEMA == "complaint-generator/module-interface@1"
        assert interface.INTERFACE_VERSION == "1.0.0"
        assert interface.INTERFACE_VERSION != "2.0.0"
        assert "applications.complaint_workspace" not in interface.OWNER_MODULES

        import applications.server as server

        assert interface.SERVER is server.SERVER
        try:
            interface.missing_attribute_for_cimp_con_12
        except AttributeError:
            pass
        else:
            raise SystemExit("missing attribute did not raise AttributeError")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
