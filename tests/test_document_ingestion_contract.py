from io import BytesIO, StringIO
from unittest.mock import Mock, patch

import pytest

from integrations.ipfs_datasets.documents import parse_document, parse_document_bytes


def test_shared_parse_contract_preserves_legacy_bytes_behavior():
    payload = b"Notice of adverse action\nThe hearing request was denied."

    legacy = parse_document_bytes(
        payload,
        filename="notice.txt",
        mime_type="text/plain",
        source="evidence",
        chunk_size=24,
        overlap=4,
    )
    shared = parse_document(
        data=payload,
        filename="notice.txt",
        mime_type="text/plain",
        source="evidence",
        chunk_size=24,
        overlap=4,
    )

    assert shared == legacy


@pytest.mark.parametrize(
    ("value", "expected_source"),
    [
        (b"Uploaded evidence", "bytes"),
        ("Fetched web page", "text"),
        (BytesIO(b"Authority text"), "stream"),
        (StringIO("Archived page text"), "stream"),
    ],
)
def test_shared_parse_contract_accepts_ingestion_input_kinds(value, expected_source):
    result = parse_document(value, filename="source.txt", mime_type="text/plain")

    assert result["text"]
    assert result["summary"]["input_format"] == "text"
    assert result["metadata"]["source"] == expected_source
    assert result["lineage"]["source"] == expected_source
    assert result["metadata"]["transform_lineage"] == result["lineage"]
    assert result["chunks"][0]["metadata"]["source"] == expected_source
    assert result["chunks"][0]["metadata"]["input_format"] == "text"
    assert result["chunks"][0]["metadata"]["source_span"]["char_start"] == 0


def test_shared_parse_contract_reads_explicit_file_and_applies_ingestion_context(tmp_path):
    source_path = tmp_path / "authority.html"
    source_path.write_text("<h1>Rule</h1><p>A hearing is required.</p>", encoding="utf-8")

    result = parse_document(
        file_path=source_path,
        source="legal_authority",
        metadata={"content_origin": "authority_full_text", "parser_version": "caller-value"},
        lineage={"corpus_family": "legal_authority", "input_format": "caller-value"},
    )

    assert result["text"] == "Rule\nA hearing is required."
    assert result["summary"]["input_format"] == "html"
    assert result["metadata"]["source"] == "legal_authority"
    assert result["metadata"]["content_origin"] == "authority_full_text"
    assert result["metadata"]["parser_version"] != "caller-value"
    assert result["lineage"]["input_format"] == "html"
    assert result["lineage"]["corpus_family"] == "legal_authority"


def test_shared_parse_contract_requires_exactly_one_input():
    with pytest.raises(ValueError, match="exactly one"):
        parse_document()

    with pytest.raises(ValueError, match="exactly one"):
        parse_document(data=b"bytes", text="text")


def test_shared_parse_contract_rejects_invalid_explicit_input_types():
    with pytest.raises(TypeError, match="bytes-like"):
        parse_document(data="not bytes")

    with pytest.raises(TypeError, match="must be a string"):
        parse_document(text=b"not text")


def test_shared_parse_contract_keeps_fallback_status(monkeypatch):
    monkeypatch.setattr("integrations.ipfs_datasets.documents.DOCUMENTS_AVAILABLE", False)

    result = parse_document(data=b"Fallback evidence", filename="evidence.txt")

    assert result["status"] == "fallback"
    assert result["metadata"]["implementation_status"] == "fallback"
    assert result["text"] == "Fallback evidence"


def test_shared_parse_contract_is_exported_from_adapter_package():
    from integrations.ipfs_datasets import parse_document as exported_parse_document

    assert exported_parse_document is parse_document


def test_evidence_storage_routes_document_inputs_through_shared_contract():
    from mediator.evidence_hooks import EvidenceStorageHook

    mediator = Mock()
    mediator.log = Mock()
    hook = EvidenceStorageHook(mediator)

    with patch("mediator.evidence_hooks.parse_document", wraps=parse_document) as shared_parser:
        result = hook.store_evidence(
            b"The agency denied the written hearing request.",
            "document",
            {
                "filename": "denial.txt",
                "mime_type": "text/plain",
                "parse_source": "uploaded_evidence",
            },
        )

    shared_parser.assert_called_once_with(
        data=b"The agency denied the written hearing request.",
        filename="denial.txt",
        mime_type="text/plain",
        source="uploaded_evidence",
    )
    assert result["document_parse"]["metadata"]["source"] == "uploaded_evidence"
    assert result["metadata"]["document_parse_contract"]["source"] == "uploaded_evidence"


def test_legal_authority_routes_text_through_shared_contract():
    from mediator.legal_authority_hooks import LegalAuthorityStorageHook

    authority = {
        "type": "regulation",
        "source": "federal_register",
        "citation": "92 Fed. Reg. 67890",
        "title": "Workplace investigations",
        "html_body": (
            "<html><body><h1>Investigation duties</h1>"
            "<p>Employers must investigate complaints promptly.</p></body></html>"
        ),
    }
    hook = object.__new__(LegalAuthorityStorageHook)

    with patch(
        "mediator.legal_authority_hooks.parse_document",
        wraps=parse_document,
    ) as shared_parser:
        result = hook._parse_authority_text(authority)

    shared_parser.assert_called_once_with(
        text=authority["html_body"],
        filename=authority["citation"],
        mime_type="text/html",
        source="legal_authority",
    )
    assert result["text"].startswith("Investigation duties")
    assert result["summary"]["input_format"] == "html"
    assert result["metadata"]["source"] == "legal_authority"
    assert result["lineage"]["content_origin"] == "authority_full_text"
