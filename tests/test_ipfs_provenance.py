from integrations.ipfs_datasets.provenance import (
    build_document_parse_contract,
    build_document_parse_summary_metadata,
    build_fact_lineage_metadata,
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


def test_build_document_parse_contract_exposes_shared_parse_bundle():
    document_parse = {
        "status": "fallback",
        "text": "alpha beta gamma",
        "summary": {
            "status": "fallback",
            "chunk_count": 1,
            "text_length": 16,
            "parser_version": "documents-adapter:1",
            "input_format": "text",
            "paragraph_count": 1,
        },
        "metadata": {
            "source": "web_document",
            "transform_lineage": {
                "source": "web_document",
                "parser_version": "documents-adapter:1",
                "input_format": "text",
            },
        },
    }

    payload = build_document_parse_contract(document_parse, default_source="web_document")

    assert payload["status"] == "fallback"
    assert payload["source"] == "web_document"
    assert payload["chunk_count"] == 1
    assert payload["summary"]["parser_version"] == "documents-adapter:1"
    assert payload["storage_metadata"]["transform_lineage"]["source"] == "web_document"
    assert payload["text_preview"] == "alpha beta gamma"


def test_build_fact_lineage_metadata_embeds_parse_contract_fields():
    metadata = build_fact_lineage_metadata(
        {"sentence_index": 0},
        parse_contract={
            "status": "fallback",
            "source": "legal_authority",
            "summary": {
                "parser_version": "documents-adapter:1",
                "input_format": "text",
            },
            "lineage": {
                "source": "legal_authority",
                "parser_version": "documents-adapter:1",
                "input_format": "text",
            },
        },
        record_scope="legal_authority",
        source_ref="authority:7",
    )

    assert metadata["sentence_index"] == 0
    assert metadata["parse_lineage"]["status"] == "fallback"
    assert metadata["parse_lineage"]["source"] == "legal_authority"
    assert metadata["parse_lineage"]["parser_version"] == "documents-adapter:1"
    assert metadata["parse_lineage"]["record_scope"] == "legal_authority"
    assert metadata["parse_lineage"]["source_ref"] == "authority:7"