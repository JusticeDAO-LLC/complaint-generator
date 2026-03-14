"""Tests for the complaint-generator ipfs_datasets adapter layer."""

from io import BytesIO
import json
import integrations.ipfs_datasets.vector_store as vector_store_module
import integrations.ipfs_datasets as adapter
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch
import zipfile

from integrations.ipfs_datasets.capabilities import (
    get_ipfs_datasets_capabilities,
    summarize_ipfs_datasets_capability_report,
    summarize_ipfs_datasets_capabilities,
    summarize_ipfs_datasets_startup_payload,
)
from integrations.ipfs_datasets.documents import (
    ingest_download_manifest,
    ingest_local_document,
    parse_document_bytes,
    parse_document_file,
    parse_pdf_to_record,
    should_parse_document_input,
)
from integrations.ipfs_datasets.graphs import extract_graph_from_text, persist_graph_snapshot, query_graph_support
from integrations.ipfs_datasets.graphrag import (
    analyze_pdf_relationships,
    batch_process_pdfs,
    build_ontology,
    cross_analyze_pdf_documents,
    extract_pdf_entities,
    ingest_pdf_to_graphrag,
    query_pdf_knowledge_graph,
    run_refinement_cycle,
    validate_ontology,
)
from integrations.ipfs_datasets.legal import (
    search_federal_register,
    search_recap_documents,
    search_us_code,
)
from integrations.ipfs_datasets.llm import generate_text_with_metadata
from integrations.ipfs_datasets.logic import check_contradictions, prove_claim_elements, text_to_fol
from integrations.ipfs_datasets.mcp_gateway import execute_gateway_tool, list_gateway_tools
from integrations.ipfs_datasets.scraper_daemon import ScraperDaemon, ScraperDaemonConfig
from integrations.ipfs_datasets.search import (
    download_url,
    download_with_recovery,
    evaluate_scraped_content,
    recover_manifest_downloads,
    scrape_web_content,
    search_brave_web,
    search_multi_engine_web,
)
from integrations.ipfs_datasets.storage import pin_cid, retrieve_bytes, storage_backend_status, store_bytes
from integrations.ipfs_datasets import vector_store as vector_store_module
from integrations.ipfs_datasets.vector_store import create_vector_index, search_vector_index


def test_capability_registry_has_expected_keys():
    capabilities = get_ipfs_datasets_capabilities()
    assert {
        'llm_router',
        'ipfs_storage',
        'web_archiving',
        'common_crawl',
        'documents',
        'legal_scrapers',
        'knowledge_graphs',
        'graphrag',
        'logic_tools',
        'vector_store',
        'mcp_gateway',
    }.issubset(capabilities.keys())


def test_adapter_root_exports_search_and_vector_entrypoints():
    assert callable(adapter.search_brave_web)
    assert callable(adapter.search_multi_engine_web)
    assert callable(adapter.scrape_web_content)
    assert callable(adapter.download_with_recovery)
    assert callable(adapter.parse_pdf_to_record)
    assert callable(adapter.create_vector_index)
    assert callable(adapter.search_vector_index)


def test_capability_summary_returns_strings():
    summary = summarize_ipfs_datasets_capabilities()
    assert summary
    assert all(isinstance(value, str) for value in summary.values())


def test_capability_registry_exposes_common_contract_fields():
    capabilities = get_ipfs_datasets_capabilities()

    for name, status in capabilities.items():
        payload = status.as_dict()
        assert payload["provider"] == "ipfs_datasets_py"
        assert payload["module_path"].startswith("ipfs_datasets_py")
        assert payload["details"]["capability"] == name
        assert "error_type" in payload["details"]
        assert payload["details"]["adapter_module"].startswith("integrations.ipfs_datasets")
        assert payload["details"]["contract_family"]


def test_capability_report_returns_counts_and_nested_statuses():
    report = summarize_ipfs_datasets_capability_report()

    assert report["status"] in {"available", "degraded"}
    assert report["available_count"] + report["degraded_count"] == len(report["capabilities"])
    assert isinstance(report["available_capabilities"], list)
    assert isinstance(report["degraded_capabilities"], dict)
    assert isinstance(report["family_counts"], dict)
    assert all("provider" in payload for payload in report["capabilities"].values())
    assert all("details" in payload for payload in report["capabilities"].values())


def test_startup_payload_reuses_canonical_capability_summary_contract():
    startup_payload = summarize_ipfs_datasets_startup_payload()

    assert startup_payload["capability_report"]["capabilities"] == startup_payload["capabilities"]
    assert startup_payload["capability_report"]["status"] in {"available", "degraded"}
    assert all(payload["provider"] == "ipfs_datasets_py" for payload in startup_payload["capabilities"].values())


def test_search_us_code_normalizes_results():
    payload = {
        'status': 'success',
        'results': [
            {
                'title': '42 U.S.C. 1983',
                'snippet': 'civil rights',
                'url': 'https://example.com/usc/1983',
            }
        ],
    }
    with patch('integrations.ipfs_datasets.legal._search_us_code_async', new=Mock(return_value=object())):
        with patch('integrations.ipfs_datasets.legal.run_async_compat', return_value=payload):
            results = search_us_code('civil rights', max_results=5)

    assert len(results) == 1
    assert results[0]['source'] == 'us_code'
    assert results[0]['type'] == 'statute'
    assert results[0]['url'] == 'https://example.com/usc/1983'
    assert results[0]['provider'] == 'ipfs_datasets_py'
    assert results[0]['metadata']['provider'] == 'ipfs_datasets_py'
    assert results[0]['metadata']['details']['operation'] == 'search_us_code'
    assert results[0]['metadata']['details']['query'] == 'civil rights'
    assert results[0]['metadata']['details']['source'] == 'us_code'


def test_search_federal_register_normalizes_documents():
    payload = {
        'status': 'success',
        'documents': [
            {
                'document_number': '2026-0001',
                'title': 'Test Rule',
                'html_url': 'https://example.com/fr/2026-0001',
            }
        ],
    }
    with patch('integrations.ipfs_datasets.legal._search_federal_register_async', new=Mock(return_value=object())):
        with patch('integrations.ipfs_datasets.legal.run_async_compat', return_value=payload):
            results = search_federal_register('test rule', max_results=5)

    assert len(results) == 1
    assert results[0]['source'] == 'federal_register'
    assert results[0]['type'] == 'regulation'
    assert results[0]['citation'] == '2026-0001'
    assert results[0]['provider'] == 'ipfs_datasets_py'
    assert results[0]['metadata']['details']['operation'] == 'search_federal_register'
    assert results[0]['metadata']['details']['upstream_collection'] == 'documents'


def test_search_recap_normalizes_documents():
    payload = {
        'status': 'success',
        'documents': [
            {
                'id': 'recap-1',
                'case_name': 'Test v. Example',
                'absolute_url': 'https://example.com/recap/1',
            }
        ],
    }
    with patch('integrations.ipfs_datasets.legal._search_recap_documents_async', new=Mock(return_value=object())):
        with patch('integrations.ipfs_datasets.legal.run_async_compat', return_value=payload):
            results = search_recap_documents('test case', max_results=5)

    assert len(results) == 1
    assert results[0]['source'] == 'recap'
    assert results[0]['type'] == 'case_law'
    assert results[0]['title'] == 'Test v. Example'
    assert results[0]['url'] == 'https://example.com/recap/1'
    assert results[0]['provider'] == 'ipfs_datasets_py'
    assert results[0]['metadata']['details']['operation'] == 'search_recap_documents'


def test_search_brave_web_normalizes_results():
    payload = {
        'status': 'success',
        'results': [
            {
                'title': 'Example Result',
                'url': 'https://example.com',
                'description': 'Example description',
                'language': 'en',
                'published_date': '1 day ago',
            }
        ],
    }
    with patch('integrations.ipfs_datasets.search._search_brave', new=Mock(return_value=object())):
        with patch('integrations.ipfs_datasets.search.run_async_compat', return_value=payload):
            results = search_brave_web('example query', max_results=5)

    assert len(results) == 1
    assert results[0]['source_type'] == 'brave_search'
    assert results[0]['metadata']['language'] == 'en'
    assert results[0]['provider'] == 'ipfs_datasets_py'
    assert results[0]['metadata']['provider'] == 'ipfs_datasets_py'
    assert results[0]['metadata']['details']['operation'] == 'search_brave_search'
    assert results[0]['metadata']['details']['query'] == 'example query'
    assert results[0]['metadata']['details']['engine'] == 'brave'


def test_search_multi_engine_web_normalizes_orchestrated_results():
    response = Mock()
    response.results = [
        Mock(
            title='Agency Guidance',
            url='https://example.com/guidance',
            snippet='Current agency guidance',
            engine='duckduckgo',
            score=0.88,
            domain='example.com',
            metadata={'rank': 1},
        )
    ]

    with patch('integrations.ipfs_datasets.search.MULTI_ENGINE_SEARCH_AVAILABLE', True):
        with patch('integrations.ipfs_datasets.search.OrchestratorConfig', side_effect=lambda **kwargs: kwargs):
            with patch('integrations.ipfs_datasets.search.MultiEngineOrchestrator') as orchestrator_cls:
                orchestrator_cls.return_value.search.return_value = response
                results = search_multi_engine_web('agency guidance', max_results=5)

    assert len(results) == 1
    assert results[0]['source_type'] == 'multi_engine_search'
    assert results[0]['metadata']['engine'] == 'duckduckgo'
    assert results[0]['metadata']['domain'] == 'example.com'
    assert results[0]['provider'] == 'ipfs_datasets_py'
    assert results[0]['metadata']['details']['operation'] == 'search_multi_engine_search'
    assert results[0]['metadata']['details']['query'] == 'agency guidance'


def test_download_url_persists_bytes_and_normalizes_metadata():
    response = Mock()
    response.content = b"%PDF-1.7 fake pdf"
    response.url = "https://example.com/final.pdf"
    response.headers = {"content-type": "application/pdf"}
    response.raise_for_status = Mock()

    with tempfile.TemporaryDirectory() as tmpdir:
        destination = Path(tmpdir) / "download.pdf"
        with patch("integrations.ipfs_datasets.search.requests.get", return_value=response):
            payload = download_url("https://example.com/file.pdf", output_path=destination)

        assert payload["status"] == "success"
        assert payload["is_pdf"] is True
        assert destination.exists()
        assert payload["saved_path"] == str(destination)


def test_download_with_recovery_uses_search_fallback_when_direct_download_is_not_pdf():
    direct_payload = {"status": "non_pdf", "is_pdf": False, "content_type": "text/html", "saved_path": "/tmp/fake.pdf"}
    recovered_payload = {"status": "success", "is_pdf": True, "content_type": "application/pdf", "saved_path": "/tmp/fake.pdf"}

    with patch("integrations.ipfs_datasets.search.download_url", side_effect=[direct_payload, recovered_payload]):
        with patch("integrations.ipfs_datasets.search.search_brave_web", return_value=[{"url": "https://example.com/recovered.pdf"}]):
            payload = download_with_recovery("https://example.com/file", use_playwright=False)

    assert payload["status"] == "success"
    assert payload["recovery_strategy"] == "search_fallback"


def test_recover_manifest_downloads_updates_problematic_entries():
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "download_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "downloads": [
                        {
                            "url": "https://example.com/file.pdf",
                            "filepath": str(Path(tmpdir) / "missing.pdf"),
                            "content_type": "text/html",
                            "file_size": 20,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        recovered_path = Path(tmpdir) / "recovered.pdf"
        recovered_path.write_bytes(b"%PDF-1.7 recovered")
        with patch(
            "integrations.ipfs_datasets.search.download_with_recovery",
            return_value={"status": "success", "content_type": "application/pdf", "saved_path": str(recovered_path)},
        ):
            payload = recover_manifest_downloads(manifest_path, output_dir=tmpdir)

        persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["status"] == "success"
        assert payload["recovered"] == 1
        assert persisted["downloads"][0]["content_type"] == "application/pdf"


def test_parse_pdf_to_record_writes_text_and_metadata_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.7 sample")
        output_dir = Path(tmpdir) / "parsed"
        with patch("integrations.ipfs_datasets.documents.parse_document_file") as parse_file:
            parse_file.return_value = {
                "status": "available-fallback",
                "text": "Example PDF text",
                "metadata": {
                    "mime_type": "application/pdf",
                    "extraction_method": "pdf_text_fallback",
                    "parse_quality": {"quality_flags": []},
                },
            }
            payload = parse_pdf_to_record(pdf_path, output_dir=output_dir, enable_ocr=False)

        assert payload["status"] == "success"
        assert Path(payload["parsed_text_path"]).exists()
        assert Path(payload["metadata_path"]).exists()


def test_ingest_download_manifest_processes_ok_rows():
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "example.html"
        html_path.write_text("<html><body>Hello world</body></html>", encoding="utf-8")
        manifest_path = Path(tmpdir) / "manifest.json"
        manifest_path.write_text(
            json.dumps([{"status": "ok", "saved_path": str(html_path), "content_type": "text/html"}]),
            encoding="utf-8",
        )
        payload = ingest_download_manifest(manifest_path, output_dir=Path(tmpdir) / "parsed")

        assert payload["status"] == "success"
        assert payload["record_count"] == 1
        assert payload["records"][0]["status"] == "success"


def test_vector_functions_return_unavailable_without_optional_backends():
    original_np = vector_store_module.np
    original_embed = vector_store_module.embed_texts_batched
    original_error = vector_store_module.VECTOR_STORE_ERROR
    try:
        vector_store_module.np = None
        vector_store_module.embed_texts_batched = None
        vector_store_module.VECTOR_STORE_ERROR = "numpy unavailable"

        create_payload = create_vector_index([{"id": "doc-1", "text": "test document"}], output_dir="/tmp")
        search_payload = search_vector_index("test query", index_dir="/tmp")
    finally:
        vector_store_module.np = original_np
        vector_store_module.embed_texts_batched = original_embed
        vector_store_module.VECTOR_STORE_ERROR = original_error

    assert create_payload["status"] == "unavailable"
    assert search_payload["status"] == "unavailable"
    assert create_payload["metadata"]["operation"] == "create_vector_index"
    assert search_payload["metadata"]["operation"] == "search_vector_index"


def test_vector_index_can_write_and_search_local_payloads(tmp_path):
    original_embed = vector_store_module.embed_texts_batched
    try:
        def fake_embed_texts_batched(texts, **kwargs):
            vectors = []
            for text in texts:
                lowered = text.lower()
                if "rent" in lowered:
                    vectors.append([1.0, 0.0, 0.0])
                elif "inspection" in lowered:
                    vectors.append([0.0, 1.0, 0.0])
                else:
                    vectors.append([0.0, 0.0, 1.0])
            return vectors

        vector_store_module.embed_texts_batched = fake_embed_texts_batched

        output_dir = tmp_path / "vectors"
        create_payload = create_vector_index(
            [
                {"id": "rule-1", "text": "Rent contribution policy rule", "metadata": {"kind": "rule"}},
                {"id": "section-1", "text": "Inspection standards overview", "metadata": {"kind": "section"}},
            ],
            index_name="test-index",
            output_dir=str(output_dir),
            batch_size=2,
        )

        search_payload = search_vector_index(
            "rent policy",
            index_name="test-index",
            index_dir=str(output_dir),
            top_k=2,
        )
    finally:
        vector_store_module.embed_texts_batched = original_embed

    assert create_payload["status"] == "success"
    assert create_payload["dimension"] == 3
    assert Path(create_payload["files"]["vectors_path"]).exists()
    assert Path(create_payload["files"]["records_path"]).exists()
    assert Path(create_payload["files"]["manifest_path"]).exists()

    assert search_payload["status"] == "success"
    assert len(search_payload["results"]) == 2
    assert search_payload["results"][0]["id"] == "rule-1"
    assert search_payload["results"][0]["metadata"]["kind"] == "rule"


def test_scrape_web_content_normalizes_scraper_result():
    scraper_result = Mock(
        url='https://example.com/page',
        title='Archived policy',
        text='Relevant employment policy text',
        content='Relevant employment policy text',
        html='<html></html>',
        links=[{'url': 'https://example.com/next', 'text': 'Next'}],
        metadata={'archive_url': 'https://archive.example.com/page'},
        method_used=Mock(value='wayback_machine'),
        success=True,
        errors=[],
        extraction_time=0.5,
    )

    with patch('integrations.ipfs_datasets.search.UNIFIED_WEB_SCRAPER_AVAILABLE', True):
        with patch('integrations.ipfs_datasets.search.ScraperConfig', side_effect=lambda **kwargs: Mock(**kwargs)):
            with patch('integrations.ipfs_datasets.search.UnifiedWebScraper') as scraper_cls:
                scraper_cls.return_value.scrape_sync.return_value = scraper_result
                result = scrape_web_content('https://example.com/page')

    assert result['source_type'] == 'web_scrape'
    assert result['success'] is True
    assert result['metadata']['method_used'] == 'wayback_machine'
    assert 'Relevant employment policy text' in result['content']
    assert result['provider'] == 'ipfs_datasets_py'
    assert result['metadata']['details']['operation'] == 'scrape_web_scrape'
    assert result['metadata']['details']['source_type'] == 'web_scrape'


def test_scrape_web_content_unavailable_uses_shared_degraded_contract():
    with patch('integrations.ipfs_datasets.search.UNIFIED_WEB_SCRAPER_AVAILABLE', False):
        result = scrape_web_content('https://example.com/page')

    assert result['success'] is False
    assert result['provider'] == 'ipfs_datasets_py'
    assert result['degraded_reason'] == 'UnifiedWebScraper unavailable'
    assert result['metadata']['provider'] == 'ipfs_datasets_py'
    assert result['metadata']['details']['operation'] == 'scrape_web_scrape'
    assert result['metadata']['details']['backend_available'] is False


def test_evaluate_scraped_content_fallback_scores_non_empty_records():
    records = [
        {'title': 'A', 'content': 'substantial content'},
        {'title': 'B', 'content': ''},
    ]

    with patch('integrations.ipfs_datasets.search.SCRAPER_VALIDATION_AVAILABLE', False):
        result = evaluate_scraped_content(records, scraper_name='test-scraper')

    assert result['scraper_name'] == 'test-scraper'
    assert result['records_scraped'] == 2
    assert 0.0 < result['data_quality_score'] < 100.0


def test_scraper_daemon_optimizes_tactics_across_iterations():
    daemon = ScraperDaemon(ScraperDaemonConfig(iterations=2, max_results_per_tactic=2, max_scrapes_per_tactic=1))

    multi_engine_results = [
        {
            'title': 'Policy Update',
            'url': 'https://example.com/policy',
            'description': 'Policy update',
            'content': 'Policy update',
            'source_type': 'multi_engine_search',
            'metadata': {},
        }
    ]
    brave_results = [
        {
            'title': 'Press Release',
            'url': 'https://example.com/press',
            'description': 'Press release',
            'content': 'Press release',
            'source_type': 'brave_search',
            'metadata': {},
        }
    ]

    def fake_search_multi_engine(query, max_results=10, engines=None):
        return multi_engine_results

    def fake_search_brave(query, max_results=10, freshness=None, api_key=None):
        return brave_results

    def fake_scrape(url, methods=None, timeout=30):
        return {
            'url': url,
            'title': 'Scraped',
            'description': 'Scraped description',
            'content': 'Scraped content with legal evidence',
            'source_type': 'web_scrape',
            'success': True,
            'errors': [],
            'metadata': {'method_used': 'beautifulsoup'},
        }

    def fake_eval(records, scraper_name='unknown', domain='caselaw'):
        return {
            'scraper_name': scraper_name,
            'domain': domain,
            'status': 'success',
            'records_scraped': len(records),
            'data_quality_score': 82.0,
            'quality_issues': [],
            'sample_data': list(records[:3]),
        }

    with patch('integrations.ipfs_datasets.scraper_daemon.search_multi_engine_web', side_effect=fake_search_multi_engine):
        with patch('integrations.ipfs_datasets.scraper_daemon.search_brave_web', side_effect=fake_search_brave):
            with patch('integrations.ipfs_datasets.scraper_daemon.scrape_web_content', side_effect=fake_scrape):
                with patch('integrations.ipfs_datasets.scraper_daemon.scrape_archived_domain', return_value=[]):
                    with patch('integrations.ipfs_datasets.scraper_daemon.evaluate_scraped_content', side_effect=fake_eval):
                        result = daemon.run(keywords=['employment discrimination'], domains=['example.com'])

    assert len(result['iterations']) >= 1
    assert result['final_results']
    assert 'https://example.com/policy' in result['coverage_ledger']
    assert result['tactic_history']['multi_engine_search']


def test_parse_document_bytes_returns_normalized_shape():
    result = parse_document_bytes(b'Hello world', filename='note.txt', mime_type='text/plain')

    assert result['text'] == 'Hello world'
    assert result['metadata']['filename'] == 'note.txt'
    assert 'chunks' in result
    assert result['summary']['chunk_count'] == len(result['chunks'])
    assert result['summary']['parser_version'] == 'documents-adapter:1'
    assert result['summary']['extraction_method'] == 'text_normalization'
    assert result['summary']['quality_tier'] == 'high'
    assert result['summary']['quality_score'] > 90.0
    assert result['metadata']['transform_lineage']['source'] == 'bytes'
    assert result['metadata']['source_span']['char_end'] == len('Hello world')
    assert result['lineage']['extraction']['method'] == 'text_normalization'
    assert result['metadata']['operation'] == 'parse_document_text'
    assert result['metadata']['implementation_status'] in {'implemented', 'fallback'}


def test_parse_document_bytes_normalizes_html_input():
    payload = b'<html><body><h1>Policy</h1><p>Employment discrimination is prohibited.</p></body></html>'

    result = parse_document_bytes(payload, filename='policy.html', mime_type='text/html')

    assert 'Policy' in result['text']
    assert 'Employment discrimination is prohibited.' in result['text']
    assert '<h1>' not in result['text']
    assert result['metadata']['input_format'] == 'html'
    assert result['metadata']['chunk_count'] >= 1
    assert result['summary']['input_format'] == 'html'
    assert result['lineage']['normalization'] == 'html_to_text'
    assert result['summary']['extraction_method'] == 'html_to_text'
    assert result['metadata']['parse_quality']['quality_tier'] == 'high'


def test_parse_document_bytes_normalizes_email_input():
    payload = (
        b"Subject: HR Complaint\n"
        b"From: employee@example.com\n"
        b"To: hr@example.com\n\n"
        b"I reported discrimination on March 5."
    )

    result = parse_document_bytes(payload, filename='complaint.eml', mime_type='message/rfc822')

    assert 'Subject: HR Complaint' in result['text']
    assert 'I reported discrimination on March 5.' in result['text']
    assert result['metadata']['input_format'] == 'email'
    assert result['summary']['input_format'] == 'email'
    assert result['lineage']['normalization'] == 'email_to_text'


def test_parse_document_bytes_normalizes_rtf_input():
    payload = b'{\\rtf1\\ansi This is \\b important\\b0 evidence.\\par Next paragraph.}'

    result = parse_document_bytes(payload, filename='timeline.rtf', mime_type='application/rtf')

    assert 'important evidence.' in result['text']
    assert 'Next paragraph.' in result['text']
    assert '\\rtf1' not in result['text']
    assert result['metadata']['input_format'] == 'rtf'
    assert result['lineage']['normalization'] == 'rtf_to_text'


def test_parse_document_bytes_extracts_docx_xml_text():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(
            '[Content_Types].xml',
            '<?xml version="1.0" encoding="UTF-8"?>',
        )
        archive.writestr(
            'word/document.xml',
            (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body><w:p><w:r><w:t>Witness statement</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>Retaliation followed two days later.</w:t></w:r></w:p>'
                '</w:body></w:document>'
            ),
        )

    result = parse_document_bytes(
        buffer.getvalue(),
        filename='statement.docx',
        mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )

    assert 'Witness statement' in result['text']
    assert 'Retaliation followed two days later.' in result['text']
    assert result['metadata']['input_format'] == 'docx'
    assert result['summary']['input_format'] == 'docx'
    assert result['lineage']['normalization'] == 'docx_xml_to_text'
    assert result['summary']['quality_tier'] in {'medium', 'high'}
    assert result['metadata']['source_span']['page_count'] == 1


def test_parse_document_bytes_reports_low_quality_for_unparsed_pdf():
    result = parse_document_bytes(b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n', filename='scan.pdf', mime_type='application/pdf')

    assert result['summary']['input_format'] == 'pdf'
    assert result['summary']['extraction_method'] == 'pdf_unparsed'
    assert result['summary']['quality_tier'] == 'empty'
    assert result['summary']['quality_score'] == 0.0
    assert 'requires_ocr_or_binary_pdf' in result['metadata']['parse_quality']['quality_flags']
    assert result['metadata']['source_span']['raw_size'] == len(b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n')


def test_should_parse_document_input_covers_adapter_supported_formats():
    assert should_parse_document_input(evidence_type='attachment', filename='message.eml', mime_type='message/rfc822') is True
    assert should_parse_document_input(evidence_type='attachment', filename='notes.docx', mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document') is True
    assert should_parse_document_input(evidence_type='image', filename='photo.png', mime_type='image/png') is False


def test_parse_document_file_reads_and_normalizes_file():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as handle:
        handle.write('alpha beta gamma')
        file_path = handle.name

    try:
        result = parse_document_file(file_path)
    finally:
        import os
        os.unlink(file_path)

    assert result['text'] == 'alpha beta gamma'
    assert result['metadata']['filename'].endswith('.txt')
    assert result['metadata']['mime_type'] == 'text/plain'
    assert result['chunks'][0]['chunk_id'] == 'chunk-0'
    assert result['metadata']['transform_lineage']['source'] == 'file'


def test_extract_graph_from_text_returns_normalized_shape():
    result = extract_graph_from_text('Example complaint text', source_id='artifact-1')

    assert result['source_id'] == 'artifact-1'
    assert result['entities'][0]['id'] == 'artifact-1'
    assert any(entity['type'] == 'fact' for entity in result['entities'])
    assert any(relationship['relation_type'] == 'has_fact' for relationship in result['relationships'])
    assert result['metadata']['operation'] == 'extract_graph_from_text'


def test_ingest_pdf_to_graphrag_delegates_to_upstream_pdf_tool():
    payload = {"status": "success", "document_id": "doc-1", "entities_added": 7}

    with patch('integrations.ipfs_datasets.graphrag._pdf_ingest_to_graphrag_async', new=Mock(return_value=object())):
        with patch('integrations.ipfs_datasets.graphrag.run_async_compat', return_value=payload):
            result = ingest_pdf_to_graphrag("/tmp/policy.pdf", target_llm="gpt-4o-mini")

    assert result["status"] == "success"
    assert result["document_id"] == "doc-1"
    assert result["provider"] == "ipfs_datasets_py"
    assert result["metadata"]["details"]["operation"] == "ingest_pdf_to_graphrag"
    assert result["metadata"]["details"]["pdf_source"] == "/tmp/policy.pdf"


def test_extract_pdf_entities_degrades_cleanly_when_unavailable():
    with patch('integrations.ipfs_datasets.graphrag._pdf_extract_entities_async', None):
        result = extract_pdf_entities("/tmp/policy.pdf")

    assert result["status"] == "unavailable"
    assert result["provider"] == "ipfs_datasets_py"
    assert result["metadata"]["details"]["operation"] == "extract_pdf_entities"
    assert result["metadata"]["details"]["backend_available"] is False


def test_batch_process_pdfs_delegates_to_upstream_pdf_tool():
    payload = {"status": "success", "documents_processed": 3}

    with patch('integrations.ipfs_datasets.graphrag._pdf_batch_process_async', new=Mock(return_value=object())):
        with patch('integrations.ipfs_datasets.graphrag.run_async_compat', return_value=payload):
            result = batch_process_pdfs(["a.pdf", "b.pdf", "c.pdf"], batch_size=2, parallel_workers=4)

    assert result["status"] == "success"
    assert result["documents_processed"] == 3
    assert result["metadata"]["details"]["operation"] == "batch_process_pdfs"
    assert result["metadata"]["details"]["pdf_count"] == 3
    assert result["metadata"]["details"]["parallel_workers"] == 4


def test_query_pdf_knowledge_graph_delegates_to_upstream_pdf_tool():
    payload = {"status": "success", "results": [{"id": "entity-1"}]}

    with patch('integrations.ipfs_datasets.graphrag._pdf_query_knowledge_graph_async', new=Mock(return_value=object())):
        with patch('integrations.ipfs_datasets.graphrag.run_async_compat', return_value=payload):
            result = query_pdf_knowledge_graph("housing-rules", "eligibility", query_type="natural_language")

    assert result["status"] == "success"
    assert result["results"][0]["id"] == "entity-1"
    assert result["metadata"]["details"]["operation"] == "query_pdf_knowledge_graph"
    assert result["metadata"]["details"]["graph_id"] == "housing-rules"
    assert result["metadata"]["details"]["query_type"] == "natural_language"


def test_analyze_pdf_relationships_and_cross_document_delegate_to_upstream_tools():
    rel_payload = {"status": "success", "relationships": [{"type": "references"}]}
    cross_payload = {"status": "success", "connections": [{"source": "doc-1", "target": "doc-2"}]}

    with patch('integrations.ipfs_datasets.graphrag._pdf_analyze_relationships_async', new=Mock(return_value=object())):
        with patch('integrations.ipfs_datasets.graphrag.run_async_compat', return_value=rel_payload):
            rel_result = analyze_pdf_relationships("doc-1", analysis_type="rules")

    with patch('integrations.ipfs_datasets.graphrag._pdf_cross_document_analysis_async', new=Mock(return_value=object())):
        with patch('integrations.ipfs_datasets.graphrag.run_async_compat', return_value=cross_payload):
            cross_result = cross_analyze_pdf_documents(["doc-1", "doc-2"], output_format="summary")

    assert rel_result["status"] == "success"
    assert rel_result["metadata"]["details"]["analysis_type"] == "rules"
    assert cross_result["status"] == "success"
    assert cross_result["metadata"]["details"]["document_count"] == 2
    assert cross_result["metadata"]["details"]["output_format"] == "summary"


def test_persist_graph_snapshot_returns_stable_contract():
    graph_payload = extract_graph_from_text('Example complaint text', source_id='artifact-1')

    result = persist_graph_snapshot(
        graph_payload,
        graph_changed=True,
        existing_graph=False,
        persistence_metadata={'projection_target': 'complaint_phase_knowledge_graph'},
    )

    assert result['status'] in {'pending', 'noop'}
    assert result['graph_id'].startswith('graph:')
    assert result['persisted'] is False
    assert result['created'] is True
    assert result['reused'] is False
    assert result['node_count'] >= 1
    assert result['edge_count'] >= 1
    assert result['metadata']['source_id'] == 'artifact-1'
    assert result['metadata']['projection_target'] == 'complaint_phase_knowledge_graph'
    assert result['metadata']['lineage']['status'] == graph_payload['status']
    assert result['metadata']['operation'] == 'persist_graph_snapshot'


def test_query_graph_support_ranks_fact_backed_results():
    result = query_graph_support(
        'employment:1',
        graph_id='intake-knowledge-graph',
        claim_type='employment',
        claim_element_text='Protected activity',
        support_facts=[
            {
                'fact_id': 'fact:1',
                'text': 'Employee engaged in protected activity by complaining to HR.',
                'claim_element_id': 'employment:1',
                'claim_element_text': 'Protected activity',
                'support_kind': 'evidence',
                'source_table': 'evidence',
                'confidence': 0.6,
            },
            {
                'fact_id': 'fact:1b',
                'text': 'Employee engaged in protected activity by complaining to HR.',
                'claim_element_id': 'employment:1',
                'claim_element_text': 'Protected activity',
                'support_kind': 'authority',
                'source_table': 'legal_authorities',
                'confidence': 0.7,
            },
            {
                'fact_id': 'fact:2',
                'text': 'Termination happened later.',
                'claim_element_id': 'employment:2',
                'claim_element_text': 'Adverse action',
                'support_kind': 'evidence',
                'source_table': 'evidence',
                'confidence': 0.6,
            },
        ],
    )

    assert result['claim_element_id'] == 'employment:1'
    assert result['summary']['total_fact_count'] == 3
    assert result['summary']['unique_fact_count'] == 2
    assert result['summary']['duplicate_fact_count'] == 1
    assert result['summary']['support_by_kind']['evidence'] == 2
    assert result['summary']['support_by_kind']['authority'] == 1
    assert result['metadata']['backend_available'] in {True, False}
    assert result['metadata']['operation'] == 'query_graph_support'
    assert result['results'][0]['fact_id'] == 'fact:1'
    assert result['results'][0]['matched_claim_element'] is True
    assert result['results'][0]['duplicate_count'] == 2
    assert result['results'][0]['score'] >= result['results'][1]['score']


def test_query_graph_support_clusters_semantically_similar_facts():
    result = query_graph_support(
        'employment:1',
        graph_id='intake-knowledge-graph',
        claim_type='employment',
        claim_element_text='Protected activity',
        support_facts=[
            {
                'fact_id': 'fact:1',
                'text': 'Employee complained to HR about discrimination and engaged in protected activity.',
                'claim_element_id': 'employment:1',
                'claim_element_text': 'Protected activity',
                'support_kind': 'evidence',
                'source_table': 'evidence',
                'confidence': 0.6,
            },
            {
                'fact_id': 'fact:2',
                'text': 'Employee engaged in protected activity by filing an HR discrimination complaint.',
                'claim_element_id': 'employment:1',
                'claim_element_text': 'Protected activity',
                'support_kind': 'authority',
                'source_table': 'legal_authorities',
                'confidence': 0.7,
            },
        ],
    )

    assert result['summary']['total_fact_count'] == 2
    assert result['summary']['unique_fact_count'] == 2
    assert result['summary']['semantic_cluster_count'] == 1
    assert result['summary']['semantic_duplicate_count'] == 1
    assert result['results'][0]['cluster_size'] == 2
    assert len(result['results'][0]['cluster_texts']) == 2


def test_stubbed_adapters_expose_canonical_operation_metadata():
    logic_result = text_to_fol('All employees are protected.')
    proof_result = prove_claim_elements([{'predicate_type': 'claim_element', 'text': 'Protected activity'}])
    contradiction_result = check_contradictions([{'predicate_type': 'support_trace', 'text': 'No adverse action occurred.'}])
    vector_create = create_vector_index([{'text': 'A'}], index_name='test-index')
    vector_search = search_vector_index('employees', index_name='test-index')
    gateway_list = list_gateway_tools()
    gateway_exec = execute_gateway_tool('search_cases', {'query': 'retaliation'})
    ontology_result = build_ontology('Employment retaliation policy.')
    validation_result = validate_ontology({'entities': [], 'relationships': []})
    refinement_result = run_refinement_cycle({'entities': []}, rounds=2)

    results = [
        logic_result,
        proof_result,
        contradiction_result,
        vector_create,
        vector_search,
        gateway_list,
        gateway_exec,
        ontology_result,
        validation_result,
        refinement_result,
    ]

    for result in results:
        assert 'metadata' in result
        assert result['provider'] == 'ipfs_datasets_py'
        assert result['metadata']['operation']
        assert result['metadata']['implementation_status']
        assert result['metadata']['backend_available'] in {True, False}
        assert result['metadata']['provider'] == 'ipfs_datasets_py'
        assert result['metadata']['details']['operation'] == result['metadata']['operation']
        assert result['metadata']['details']['backend_available'] == result['metadata']['backend_available']
        assert result['metadata']['details']['implementation_status'] == result['metadata']['implementation_status']

    assert refinement_result['metadata']['rounds'] == 2
    assert refinement_result['metadata']['details']['rounds'] == 2


def test_create_vector_index_succeeds_without_numpy_when_not_persisting_locally():
    with patch.object(vector_store_module, 'np', None), patch.object(
        vector_store_module,
        '_numpy_error',
        "No module named 'numpy'",
    ), patch.object(
        vector_store_module,
        'embed_texts_batched',
        Mock(return_value=[[0.1, 0.2, 0.3]]),
    ):
        result = create_vector_index(
            [{'id': 'doc-1', 'text': 'Protected activity complaint'}],
            index_name='test-index',
        )

    assert result['status'] == 'success'
    assert result['index_name'] == 'test-index'
    assert result['document_count'] == 1
    assert result['dimension'] == 3
    assert result['metadata']['operation'] == 'create_vector_index'
    assert result['metadata']['backend_available'] is True
    assert result['metadata']['implementation_status'] == 'implemented'


def test_create_vector_index_returns_structured_unavailable_when_numpy_missing_for_local_persistence():
    with tempfile.TemporaryDirectory() as tmp_dir, patch.object(vector_store_module, 'np', None), patch.object(
        vector_store_module,
        '_numpy_error',
        "No module named 'numpy'",
    ), patch.object(
        vector_store_module,
        'embed_texts_batched',
        Mock(return_value=[[0.1, 0.2, 0.3]]),
    ):
        result = create_vector_index(
            [{'id': 'doc-1', 'text': 'Protected activity complaint'}],
            index_name='test-index',
            output_dir=tmp_dir,
        )

    assert result['status'] == 'unavailable'
    assert result['error'] == 'numpy is required for local vector persistence and search'
    assert result['index_name'] == 'test-index'
    assert result['document_count'] == 1
    assert result['metadata']['operation'] == 'create_vector_index'
    assert result['metadata']['backend_available'] is False
    assert result['metadata']['implementation_status'] == 'unavailable'
    assert result['metadata']['degraded_reason'] == "No module named 'numpy'"


def test_search_vector_index_returns_structured_unavailable_when_numpy_missing():
    with patch.object(vector_store_module, 'np', None), patch.object(
        vector_store_module,
        '_numpy_error',
        "No module named 'numpy'",
    ), patch.object(
        vector_store_module,
        'embed_texts_batched',
        Mock(return_value=[[0.1, 0.2, 0.3]]),
    ):
        result = search_vector_index(
            'protected activity',
            index_name='test-index',
            index_dir='/tmp/vector-index',
        )

    assert result['status'] == 'unavailable'
    assert result['index_name'] == 'test-index'
    assert result['query'] == 'protected activity'
    assert result['results'] == []
    assert result['metadata']['operation'] == 'search_vector_index'
    assert result['metadata']['backend_available'] is False
    assert result['metadata']['implementation_status'] == 'unavailable'
    assert result['metadata']['degraded_reason'] == "No module named 'numpy'"


def test_generate_text_with_metadata_wraps_success_response():
    with patch('integrations.ipfs_datasets.llm.generate_text', return_value='adapter response'):
        result = generate_text_with_metadata(
            'Summarize the complaint.',
            provider='copilot_cli',
            model_name='gpt-5-mini',
        )

    assert result['status'] == 'available'
    assert result['text'] == 'adapter response'
    assert result['provider'] == 'ipfs_datasets_py'
    assert result['metadata']['operation'] == 'generate_text'
    assert result['metadata']['backend_available'] is True
    assert result['metadata']['implementation_status'] == 'available'


def test_storage_wrappers_expose_canonical_operation_metadata():
    backend = object()

    with patch('integrations.ipfs_datasets.storage.add_bytes', return_value='QmStored'):
        stored = store_bytes(b'complaint text', pin_content=True)
    with patch('integrations.ipfs_datasets.storage.cat', return_value=b'complaint text'):
        retrieved = retrieve_bytes('QmStored')
    with patch('integrations.ipfs_datasets.storage.pin', return_value={'Pins': ['QmStored']}):
        pinned = pin_cid('QmStored')
    with patch('integrations.ipfs_datasets.storage.get_ipfs_backend', return_value=backend):
        backend_status = storage_backend_status()

    assert stored['status'] == 'available'
    assert stored['cid'] == 'QmStored'
    assert stored['metadata']['operation'] == 'store_bytes'
    assert stored['metadata']['backend_available'] is True

    assert retrieved['status'] == 'available'
    assert retrieved['cid'] == 'QmStored'
    assert retrieved['data'] == b'complaint text'
    assert retrieved['metadata']['operation'] == 'retrieve_bytes'

    assert pinned['status'] == 'available'
    assert pinned['cid'] == 'QmStored'
    assert pinned['pinned'] is True
    assert pinned['metadata']['operation'] == 'pin_cid'

    assert backend_status['status'] in {'available', 'unavailable'}
    assert backend_status['metadata']['operation'] == 'storage_backend_status'
    assert 'backend_present' in backend_status
