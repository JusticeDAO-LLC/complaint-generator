"""Versioned facade for complaint-phase legal-document symbols.

Version 1.0.0 re-exports only names already defined in
``complaint_phases/legal_document.py``. ``lib/legal_document.py`` and
``mediator/formal_document.py`` stay separate owners. This module does not
import them, does not import ``mediator.mediator``, and does not copy their
implementation bodies.

The sibling source is loaded from its file path so this import does not run
``complaint_phases/__init__.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
MODULE = "complaint_phases.legal_document_facade"

# Compatibility module whose public names this facade re-exports.
FACADE_SOURCE_MODULE = "complaint_phases.legal_document"
FACADE_SOURCE_PATH = "complaint_phases/legal_document.py"

# Recorded owners that are not merged into this facade and are not imported.
SEPARATE_OWNERS = (
    "lib.legal_document",
    "mediator.formal_document",
)
SEPARATE_OWNER_PATHS = (
    "lib/legal_document.py",
    "mediator/formal_document.py",
)

# Names defined at import scope by complaint_phases/legal_document.py.
PUBLIC_SYMBOLS = (
    "DocumentSection",
    "ParsedLegalDocument",
    "PleadingCaption",
    "PleadingHeader",
    "build_pleading_caption",
    "extract_pleading_header",
    "paginate_pleading_lines",
    "parse_legal_document",
    "render_pleading_caption_block",
)

_SOURCE_LOADER_NAME = "_complaint_phases_legal_document_facade_source"


def _source_path() -> Path:
    return Path(__file__).resolve().with_name("legal_document.py")


def load_facade_source() -> ModuleType:
    """Load ``complaint_phases/legal_document.py`` without importing mediator.

    A missing source file raises ``ImportError``. That failure is not treated
    as an empty successful facade.
    """
    path = _source_path()
    if not path.is_file():
        raise ImportError(f"legal-document facade source is missing: {path}")
    spec = importlib.util.spec_from_file_location(_SOURCE_LOADER_NAME, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"legal-document facade source cannot be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_SOURCE_LOADER_NAME] = module
    spec.loader.exec_module(module)
    return module


def _bind_public_symbols(source: ModuleType) -> None:
    missing = [name for name in PUBLIC_SYMBOLS if not hasattr(source, name)]
    if missing:
        joined = ", ".join(missing)
        raise ImportError(
            "legal-document facade source does not define public symbols: " + joined
        )
    for name in PUBLIC_SYMBOLS:
        globals()[name] = getattr(source, name)


_bind_public_symbols(load_facade_source())

__all__ = list(PUBLIC_SYMBOLS)
