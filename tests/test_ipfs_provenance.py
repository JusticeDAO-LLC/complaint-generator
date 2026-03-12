from integrations.ipfs_datasets.provenance import (
    build_document_parse_summary_metadata,
    build_storage_parse_metadata,
)


def test_build_document_parse_summary_metadata_carries_source():
    document_parse = {
        "summary": {
            "status": "fallback",
            "chunk_count": 2,
            "text_length": 24,
            "parser_version": "documents-adapter:1",
            "input_format": "text",
            "paragraph_count": 1,
        },
        "metadata": {
            "source": "legal_authority",
        },
    }

    payload = build_document_parse_summary_metadata(document_parse)

    assert payload["status"] == "fallback"
    assert payload["chunk_count"] == 2
    assert payload["source"] == "legal_authority"


def test_build_storage_parse_metadata_merges_summary_and_lineage_defaults():
    document_parse = {
        "summary": {
            "status": "fallback",
            "chunk_count": 2,
            "text_length": 24,
            "parser_version": "documents-adapter:1",
            "input_format": "text",
            "paragraph_count": 1,
        },
        "metadata": {
            "filename": "evidence.txt",
            "transform_lineage": {
                "parser_version": "documents-adapter:1",
                "input_format": "text",
            },
        },
    }

    payload = build_storage_parse_metadata(document_parse, default_source="bytes")

    assert payload["filename"] == "evidence.txt"
    assert payload["status"] == "fallback"
    assert payload["chunk_count"] == 2
    assert payload["source"] == "bytes"
    assert payload["transform_lineage"]["source"] == "bytes"