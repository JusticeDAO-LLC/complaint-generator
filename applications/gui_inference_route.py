"""Finite operator selection for GUI inference; never a case-consent grant."""
from __future__ import annotations

from typing import Any

NATIVE_OBSERVED_GROK47 = "native_observed_grok47"


def resolve_gui_inference_route(route: Any = None, *, synthetic_transport: Any = None):
    """Resolve trusted constructor/config values without importing caller paths.

    The selected function still requires the issued browser/case authority and
    persisted exact-purpose consent in ComplaintWorkspaceService.
    """
    if route is not None and (type(route) is not str or route != NATIVE_OBSERVED_GROK47):
        raise ValueError("unknown_gui_inference_route")
    if synthetic_transport is not None and not callable(synthetic_transport):
        raise ValueError("invalid_gui_synthetic_transport")
    if route is not None and synthetic_transport is not None:
        raise ValueError("ambiguous_gui_inference_route")
    if route is None and synthetic_transport is None:
        return None
    try:
        from mediator.hook_runtime import native_gui_inference_transport
    except ImportError:
        if route is not None:
            raise ValueError("gui_native_route_unavailable") from None
        return synthetic_transport
    if route is not None:
        return native_gui_inference_transport
    if synthetic_transport is native_gui_inference_transport:
        raise ValueError("native_gui_route_requires_explicit_selector")
    return synthetic_transport
