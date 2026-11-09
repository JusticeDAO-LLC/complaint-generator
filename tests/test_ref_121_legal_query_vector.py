from __future__ import annotations

import logging
from unittest.mock import Mock, patch

from integrations.ipfs_datasets import legal


def test_direct_embedding_failure_is_observable_before_router_fallback(caplog):
    direct_embedding = Mock(side_effect=ValueError("provider returned a malformed vector"))
    router = Mock()
    router.embed_text.return_value = (0.25, 0.5, 0.75)
    diagnostics = {}

    with (
        patch.object(legal, "EMBEDDINGS_AVAILABLE", True),
        patch.object(legal, "embed_query_text", direct_embedding),
        patch.object(legal, "get_embeddings_router", return_value=router),
        caplog.at_level(logging.WARNING, logger=legal.__name__),
    ):
        vector = legal._build_query_vector(
            "tenant retaliation",
            model_name="test-model",
            provider="test-provider",
            diagnostics=diagnostics,
        )

    assert vector == [0.25, 0.5, 0.75]
    direct_embedding.assert_called_once_with(
        "tenant retaliation",
        model_name="test-model",
        provider="test-provider",
    )
    router.embed_text.assert_called_once_with("tenant retaliation")
    assert diagnostics["direct_embedding_failure"] == {
        "backend": "embed_text",
        "error_type": "ValueError",
        "error_message": "provider returned a malformed vector",
        "fallback": "embeddings_router",
    }
    assert "falling back to the embeddings router" in caplog.text
    assert "ValueError: provider returned a malformed vector" in caplog.text


def test_successful_direct_embedding_does_not_emit_failure_diagnostics(caplog):
    diagnostics = {}

    with (
        patch.object(legal, "EMBEDDINGS_AVAILABLE", True),
        patch.object(legal, "embed_query_text", return_value=(0.1, 0.2)),
        patch.object(legal, "get_embeddings_router") as router_factory,
        caplog.at_level(logging.WARNING, logger=legal.__name__),
    ):
        vector = legal._build_query_vector("due process", diagnostics=diagnostics)

    assert vector == [0.1, 0.2]
    assert diagnostics == {}
    assert caplog.text == ""
    router_factory.assert_not_called()
