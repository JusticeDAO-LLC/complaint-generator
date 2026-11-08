"""Compatibility shim. Implementation lives in complaint_phases.workflow_phase_guidance."""

from __future__ import annotations

import importlib as _importlib

_implementation = _importlib.import_module("complaint_phases.workflow_phase_guidance")
globals().update(
    {
        _name: _value
        for _name, _value in vars(_implementation).items()
        if not _name.startswith("__")
    }
)
__all__ = [name for name in globals() if not name.startswith("_")]
