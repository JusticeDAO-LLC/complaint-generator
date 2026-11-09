from __future__ import annotations

from pathlib import Path
from typing import Any

from integrations.ipfs_datasets.legal_data import legal_module
from integrations.ipfs_datasets.multimedia import extract_attachment_text

_email_corpus = legal_module("email_corpus")

KnowledgeGraphBuilder = _email_corpus.KnowledgeGraphBuilder


def build_email_graphrag_artifacts(
    *,
    manifest_path: str | Path,
    output_dir: str | Path | None = None,
    emit_duckdb_index: bool = True,
    append_duckdb_index: bool = False,
    include_attachment_text_in_search: bool = True,
) -> dict[str, Any]:
    original_extractor = _email_corpus.extract_attachment_text
    _email_corpus.extract_attachment_text = extract_attachment_text
    try:
        return _email_corpus.build_email_graphrag_artifacts(
            manifest_path=manifest_path,
            output_dir=output_dir,
            emit_duckdb_index=emit_duckdb_index,
            append_duckdb_index=append_duckdb_index,
            include_attachment_text_in_search=include_attachment_text_in_search,
        )
    finally:
        _email_corpus.extract_attachment_text = original_extractor


def build_email_duckdb_artifacts(
    *,
    manifest_path: str | Path,
    output_dir: str | Path | None = None,
    include_attachment_text: bool = True,
    append: bool = False,
) -> dict[str, Any]:
    return _email_corpus.build_email_duckdb_artifacts(
        manifest_path=manifest_path,
        output_dir=output_dir,
        include_attachment_text=include_attachment_text,
        append=append,
    )


def search_email_graphrag_duckdb(
    *,
    index_path: str | Path,
    query: str,
    limit: int = 20,
    ranking: str = "bm25",
    bm25_k1: float = 1.2,
    bm25_b: float = 0.75,
) -> dict[str, Any]:
    return _email_corpus.search_email_graphrag_duckdb(
        index_path=index_path,
        query=query,
        limit=limit,
        ranking=ranking,
        bm25_k1=bm25_k1,
        bm25_b=bm25_b,
    )


__all__ = ["build_email_duckdb_artifacts", "build_email_graphrag_artifacts", "search_email_graphrag_duckdb"]
