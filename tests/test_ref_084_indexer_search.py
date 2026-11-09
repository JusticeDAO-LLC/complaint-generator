"""Focused regression coverage for REF-084 hybrid indexer search."""

import logging

import pytest

from complaint_analysis.indexer import HybridDocumentIndexer


def _document(*, source, relevance=0.0, embedding=None, applicability=None):
    return {
        "metadata": {"source": source},
        "keywords": {},
        "applicability": applicability or [],
        "legal_provisions": {},
        "relevance_score": relevance,
        "embedding": embedding,
        "embedding_available": embedding is not None,
    }


@pytest.mark.asyncio
async def test_search_ranks_private_source_text_and_does_not_mutate_documents():
    indexer = HybridDocumentIndexer(enable_embeddings=False)
    exact = _document(source="intake", relevance=0.2)
    partial = _document(source="intake", relevance=0.9)
    unrelated = _document(source="intake")
    indexer._indexed_documents.extend([partial, unrelated, exact])
    indexer._search_text_by_document_id.update({
        id(exact): "Landlord refused a reasonable accommodation request.",
        id(partial): "The requested accommodation was delayed.",
        id(unrelated): "An overtime wage dispute.",
    })

    results = await indexer.search("reasonable accommodation", top_k=2)

    assert [result["metadata"]["source"] for result in results] == [
        "intake",
        "intake",
    ]
    assert results[0]["keyword_score"] > results[1]["keyword_score"]
    assert results[0]["relevance_score"] == 0.2
    assert results[0]["search_score"] == results[0]["keyword_score"]
    assert results[0]["vector_score"] is None
    assert "search_score" not in exact
    assert unrelated not in results


@pytest.mark.asyncio
async def test_search_filters_top_level_metadata_and_dotted_fields():
    indexer = HybridDocumentIndexer(enable_embeddings=False)
    housing = _document(
        source="complaint_form",
        applicability=["housing", "civil_rights"],
    )
    employment = _document(source="email", applicability=["employment"])
    indexer._indexed_documents.extend([housing, employment])
    indexer._search_text_by_document_id.update({
        id(housing): "discrimination evidence",
        id(employment): "discrimination evidence",
    })

    results = await indexer.search(
        "discrimination",
        filter_by={
            "source": "complaint_form",
            "metadata.source": "complaint_form",
            "applicability": "housing",
        },
    )

    assert len(results) == 1
    assert results[0]["metadata"]["source"] == "complaint_form"


@pytest.mark.asyncio
async def test_search_blends_sync_query_embedding_with_keyword_score():
    class SyncRouter:
        def embed_text(self, _text):
            return [1.0, 0.0]

    indexer = HybridDocumentIndexer(enable_embeddings=False)
    indexer.enable_embeddings = True
    indexer.embeddings_router = SyncRouter()
    semantic = _document(source="semantic", embedding=[1.0, 0.0])
    opposite = _document(source="opposite", embedding=[-1.0, 0.0])
    indexer._indexed_documents.extend([opposite, semantic])

    results = await indexer.search("housing")

    assert [result["metadata"]["source"] for result in results] == ["semantic"]
    assert results[0]["vector_score"] == pytest.approx(1.0)
    assert results[0]["search_score"] == pytest.approx(0.65)


@pytest.mark.asyncio
async def test_search_logs_query_embedding_failure_and_uses_keywords(caplog):
    class FailingRouter:
        def embed_text(self, _text):
            raise RuntimeError("embedding service offline")

    indexer = HybridDocumentIndexer(enable_embeddings=False)
    indexer.enable_embeddings = True
    indexer.embeddings_router = FailingRouter()
    document = _document(source="intake")
    indexer._indexed_documents.append(document)
    indexer._search_text_by_document_id[id(document)] = "housing discrimination"

    with caplog.at_level(logging.WARNING):
        results = await indexer.search("housing")

    assert len(results) == 1
    assert results[0]["vector_score"] is None
    assert "embedding service offline" in caplog.text
    assert "keyword-only search" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "top_k", "filter_by", "error"),
    [
        ("", 10, None, ValueError),
        ("housing", -1, None, ValueError),
        ("housing", True, None, TypeError),
        ("housing", 10, ["housing"], TypeError),
    ],
)
async def test_search_rejects_invalid_arguments(query, top_k, filter_by, error):
    indexer = HybridDocumentIndexer(enable_embeddings=False)

    with pytest.raises(error):
        await indexer.search(query, top_k=top_k, filter_by=filter_by)
