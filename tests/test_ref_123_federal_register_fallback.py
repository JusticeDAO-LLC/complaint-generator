import logging
from unittest.mock import Mock, patch

from integrations.ipfs_datasets.legal import (
    get_last_legal_search_diagnostic,
    search_federal_register,
)


def test_federal_register_index_failure_is_observable_during_api_fallback(caplog):
    upstream_payload = {
        "status": "success",
        "documents": [
            {
                "document_number": "2026-12345",
                "title": "Fallback Rule",
            }
        ],
    }
    hf_search = Mock(return_value=object())
    upstream_search = Mock(return_value=object())

    with patch(
        "integrations.ipfs_datasets.legal._search_federal_register_hf_index_async",
        new=hf_search,
    ):
        with patch(
            "integrations.ipfs_datasets.legal._search_federal_register_async",
            new=upstream_search,
        ):
            with patch(
                "integrations.ipfs_datasets.legal.run_async_compat",
                side_effect=[RuntimeError("index unavailable"), upstream_payload],
            ):
                with caplog.at_level(logging.WARNING, logger="integrations.ipfs_datasets.legal"):
                    results = search_federal_register(
                        "workplace safety",
                        start_date="2026-01-01",
                        end_date="2026-06-30",
                        max_results=3,
                    )

    assert [record["citation"] for record in results] == ["2026-12345"]
    assert results[0]["metadata"]["details"]["retrieval_backend"] == "upstream_api"
    hf_search.assert_called_once_with(
        {
            "query_text": "workplace safety",
            "top_k": 3,
            "auto_setup_venv": False,
        }
    )
    upstream_search.assert_called_once_with(
        keywords="workplace safety",
        start_date="2026-01-01",
        end_date="2026-06-30",
        limit=3,
    )

    diagnostic = get_last_legal_search_diagnostic("search_federal_register")
    assert diagnostic["attempted_backends"] == ["huggingface_index", "upstream_api"]
    assert diagnostic["selected_backend"] == "upstream_api"
    assert diagnostic["final_status"] == "success"
    assert diagnostic["warning_code"] == "hf_index_search_failed"
    assert diagnostic["hf_index_failure"] == {
        "backend": "huggingface_index",
        "error_type": "RuntimeError",
        "error_message": "index unavailable",
        "fallback": "upstream_api",
    }
    assert "falling back to the upstream API" in caplog.text


def test_federal_register_successful_index_has_clean_diagnostic(caplog):
    hf_payload = {
        "status": "success",
        "hits": [
            {
                "document_number": "2026-54321",
                "title": "Indexed Rule",
            }
        ],
    }
    upstream_search = Mock(return_value=object())

    with patch(
        "integrations.ipfs_datasets.legal._search_federal_register_hf_index_async",
        new=Mock(return_value=object()),
    ):
        with patch(
            "integrations.ipfs_datasets.legal._search_federal_register_async",
            new=upstream_search,
        ):
            with patch(
                "integrations.ipfs_datasets.legal.run_async_compat",
                return_value=hf_payload,
            ):
                with caplog.at_level(logging.WARNING, logger="integrations.ipfs_datasets.legal"):
                    results = search_federal_register("indexed rule", max_results=2)

    assert [record["citation"] for record in results] == ["2026-54321"]
    assert results[0]["metadata"]["details"]["retrieval_backend"] == "huggingface_index"
    upstream_search.assert_not_called()

    diagnostic = get_last_legal_search_diagnostic("search_federal_register")
    assert diagnostic["attempted_backends"] == ["huggingface_index"]
    assert diagnostic["selected_backend"] == "huggingface_index"
    assert diagnostic["final_status"] == "success"
    assert diagnostic["warning_code"] == ""
    assert "hf_index_failure" not in diagnostic
    assert caplog.records == []
