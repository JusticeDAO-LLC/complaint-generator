from integrations.ipfs_datasets.provenance import (
    build_provenance,
    build_document_parse_contract,
    build_document_parse_summary_metadata,
    build_fact_lineage_metadata,
    merge_metadata_with_provenance,
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


def test_build_provenance_preserves_normalized_source_context_metadata():
    provenance = build_provenance(
        source_url="https://web.archive.org/web/20240101120000/https://example.com/policy",
        acquisition_method="web_discovery",
        source_type="archived_domain_scrape",
        source_system="ipfs_datasets_py",
        metadata={
            "content_origin": "historical_archive_capture",
            "archive_url": "https://web.archive.org/web/20240101120000/https://example.com/policy",
            "version_of": "https://example.com/policy",
            "captured_at": "2024-01-01T12:00:00Z",
        },
    )

    assert provenance.as_dict()["metadata"]["content_origin"] == "historical_archive_capture"
    assert provenance.as_dict()["metadata"]["version_of"] == "https://example.com/policy"


def test_merge_metadata_with_provenance_updates_existing_provenance_payload():
    payload = merge_metadata_with_provenance(
        {
            "provenance": {
                "source_url": "https://example.com/policy",
                "metadata": {"observed_at": "2024-01-02T00:00:00Z"},
            }
        },
        build_provenance(
            source_url="https://web.archive.org/web/20240101120000/https://example.com/policy",
            acquisition_method="web_discovery",
            source_type="archived_domain_scrape",
            metadata={"archive_url": "https://web.archive.org/web/20240101120000/https://example.com/policy"},
        ),
    )

    assert payload["provenance"]["source_url"] == "https://web.archive.org/web/20240101120000/https://example.com/policy"
    assert payload["provenance"]["metadata"]["observed_at"] == "2024-01-02T00:00:00Z"
    assert payload["provenance"]["metadata"]["archive_url"] == "https://web.archive.org/web/20240101120000/https://example.com/policy"