from __future__ import annotations

from typing import Any

from integrations.ipfs_datasets.legal_data import legal_module

_email_agentic_search = legal_module("email_agentic_search")

from .email_graphrag import build_email_graphrag_artifacts


def search_email_corpus_agentic(*args: Any, **kwargs: Any) -> dict[str, Any]:
    original_graphrag = _email_agentic_search.build_email_graphrag_artifacts
    _email_agentic_search.build_email_graphrag_artifacts = build_email_graphrag_artifacts
    try:
        return _email_agentic_search.search_email_corpus_agentic(*args, **kwargs)
    finally:
        _email_agentic_search.build_email_graphrag_artifacts = original_graphrag


__all__ = ["search_email_corpus_agentic"]
