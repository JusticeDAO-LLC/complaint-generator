import builtins
import logging
from unittest.mock import patch

import pytest

from mediator.integrations.graph_tools import GraphAwareRetrievalReranker


class _Mediator:
    phase_manager = object()


def _fail_complaint_phases_import(error):
    real_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "complaint_phases":
            raise error
        return real_import(name, globals, locals, fromlist, level)

    return patch("builtins.__import__", side_effect=_import)


def test_missing_graph_types_are_logged_and_use_empty_fallback(caplog):
    error = ImportError("complaint phase graph types unavailable")

    with _fail_complaint_phases_import(error), caplog.at_level(
        logging.WARNING,
        logger="mediator.integrations.graph_tools",
    ):
        terms = GraphAwareRetrievalReranker().extract_graph_terms(_Mediator())

    assert terms == []
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "continuing without graph-derived retrieval terms" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[1] is error


def test_non_import_error_during_graph_type_import_is_not_swallowed(caplog):
    error = RuntimeError("complaint phase initialization failed")

    with _fail_complaint_phases_import(error), pytest.raises(RuntimeError) as caught:
        GraphAwareRetrievalReranker().extract_graph_terms(_Mediator())

    assert caught.value is error
    assert caplog.records == []
