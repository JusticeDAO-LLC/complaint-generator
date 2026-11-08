"""Compatibility shim. Implementation lives in complaint_phases.intake_status."""

from __future__ import annotations

import importlib as _importlib

_implementation = _importlib.import_module("complaint_phases.intake_status")
globals().update(
    {
        _name: _value
        for _name, _value in vars(_implementation).items()
        if not _name.startswith("__")
    }
)
__all__ = [name for name in globals() if not name.startswith("_")]
