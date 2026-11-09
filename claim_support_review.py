"""Compatibility shim. The claim-support review body lives in mediator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_path = Path(__file__).resolve().parent / "mediator" / "claim_support_review.py"
_spec = importlib.util.spec_from_file_location("mediator.claim_support_review", _path)
_implementation = importlib.util.module_from_spec(_spec)
sys.modules["mediator.claim_support_review"] = _implementation
_parent = sys.modules.get("mediator")
if _parent is not None:
    setattr(_parent, "claim_support_review", _implementation)
_spec.loader.exec_module(_implementation)
globals().update(
    {
        _name: _value
        for _name, _value in vars(_implementation).items()
        if not _name.startswith("__")
    }
)
__all__ = [name for name in globals() if not name.startswith("_")]
