"""Tests for the complaint-generator ipfs_datasets adapter layer."""

import importlib
from io import BytesIO
import json
import os
import tempfile
import integrations.ipfs_datasets.capabilities as capabilities_module
import integrations.ipfs_datasets.legal as legal_module
import integrations.ipfs_datasets.loader as loader_module
import integrations.ipfs_datasets.vector_store as vector_store_module
import integrations.ipfs_datasets as adapter
from pathlib import Path
import pytest
from unittest.mock import Mock, patch
import zipfile

from integrations.ipfs_datasets.capabilities import (
    CAPABILITY_NAMES,
    CAPABILITY_SCHEMA_VERSION,
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
    summarize_document_parse,
)
from integrations.ipfs_datasets.graphs import (
    GraphPersistence,
    GraphQuery,
    extract_graph_from_text,
    persist_graph_snapshot,
    query_graph_snapshot,
    query_graph_support,
)
from integrations.ipfs_datasets.graphrag import (
    analyze_pdf_relationships,
    batch_process_pdfs,
    build_validate_score_ontology,
    build_ontology,
    create_ontology_generator,
    cross_analyze_pdf_documents,
    extract_pdf_entities,
    ingest_pdf_to_graphrag,
    query_pdf_knowledge_graph,
    run_refinement_cycle,
    validate_ontology,
)
from integrations.ipfs_datasets.legal import (
    LEGAL_SOURCE_AVAILABILITY,
    get_last_legal_search_diagnostic,
    search_federal_register,
    search_recap_documents,
    search_legal_authority_program,
    search_state_administrative_rules,
    search_state_laws,
    search_us_code,
)
from integrations.ipfs_datasets.llm import generate_text_with_metadata
from integrations.ipfs_datasets.logic import check_contradictions, prove_claim_elements, text_to_fol
from integrations.ipfs_datasets.mcp_gateway import execute_gateway_tool, list_gateway_tools
from integrations.ipfs_datasets.scraper_daemon import ScraperDaemon, ScraperDaemonConfig
from integrations.ipfs_datasets.search import (
    DegradedSearchResults,
    archive_url_snapshot,
    download_url,
    download_with_recovery,
    evaluate_scraped_content,
    recover_manifest_downloads,
    rank_search_results,
    scrape_web_content,
    search_brave_web,
    search_multi_engine_web,
)
from integrations.ipfs_datasets.router_status import get_router_status_report
from integrations.ipfs_datasets.storage import pin_cid, retrieve_bytes, storage_backend_status, store_bytes
from integrations.ipfs_datasets import vector_store as vector_store_module
from integrations.ipfs_datasets.vector_store import (
    create_vector_index,
    embeddings_backend_status,
    search_vector_index,
)
from integrations.ipfs_datasets.storage import LocalCacheIPFSBackend, ensure_ipfs_backend
from mediator.integrations import adapter as mediator_adapter_module


pytestmark = [
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def test_loader_discovers_nested_provider_layout(tmp_path: Path):
    compatibility_package = "ipfs_" + "acceler" + "ate_py"
    package_dir = (
        tmp_path
        / compatibility_package
        / "ipfs_datasets_py"
        / "ipfs_datasets_py"
    )
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")

    with patch.object(loader_module, "_candidate_ipfs_source_roots", return_value=[tmp_path]):
        resolved = loader_module._package_dir_for_root("ipfs_datasets_py")

    assert resolved == package_dir


def test_mediator_adapter_capability_detection_uses_module_paths_without_importing():
    with tempfile.TemporaryDirectory() as tmpdir:
        package_root = Path(tmpdir) / "ipfs_datasets_py"
        search_root = package_root / "search"
        package_root.mkdir()
        search_root.mkdir()
        (package_root / "__init__.py").write_text("", encoding="utf-8")
        (search_root / "__init__.py").write_text("", encoding="utf-8")
        (search_root / "search_embeddings.py").write_text("", encoding="utf-8")

        fake_spec = type(
            "FakeSpec",
            (),
            {"submodule_search_locations": [str(package_root)]},
        )()

        with patch("mediator.integrations.adapter.importlib.util.find_spec", return_value=fake_spec):
            status = mediator_adapter_module._module_available(
                ["ipfs_datasets_py.search.search_embeddings"]
            )

    assert status.available is True
    assert status.name == "ipfs_datasets_py.search.search_embeddings"


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
    assert callable(adapter.query_graph_snapshot)
    assert callable(adapter.create_vector_index)
    assert callable(adapter.search_vector_index)


def test_adapter_root_exports_document_parse_entrypoints():
    assert adapter.parse_document_bytes is parse_document_bytes
    assert callable(adapter.parse_document_file)
    assert callable(adapter.parse_document_text)
    assert callable(adapter.should_parse_document_input)
    assert callable(adapter.detect_document_input_format)
    assert callable(adapter.summarize_document_parse)


def test_capability_summary_returns_strings():
    summary = summarize_ipfs_datasets_capabilities()
    assert summary
    assert all(isinstance(value, str) for value in summary.values())


def test_capability_registry_exposes_common_contract_fields():
    capabilities = get_ipfs_datasets_capabilities()

    for name, status in capabilities.items():
        payload = status.as_dict()
        assert payload["provider"] in {"ipfs_datasets_py", "ipfs_accelerate_py", "ipfs_kit_py"}
        assert payload["module_path"].split(".", 1)[0] in {"ipfs_datasets_py", "ipfs_accelerate_py", "ipfs_kit_py"}
        assert payload["details"]["owner"] == payload["provider"]
        assert payload["details"]["capability"] == name
        assert "error_type" in payload["details"]
        assert payload["details"]["adapter_module"].startswith(("integrations.ipfs_datasets", "integrations.ipfs_accelerate"))
        assert payload["details"]["contract_family"]


def test_capability_registry_keys_are_stable_across_runtime_modes():
    status_keys = {
        "status",
        "available",
        "module_path",
        "degraded_reason",
        "provider",
        "details",
    }
    detail_keys = {
        "owner",
        "bridge",
        "public_adapter",
        "canonical_modules",
        "deprecated_upstream",
        "capability",
        "adapter_module",
        "contract_family",
        "install_extra",
        "reason_code",
        "degraded_reason",
        "error_type",
        "error_message",
        "missing_module",
        "remediation",
    }
    missing_extra = ModuleNotFoundError("No module named 'optional_parser'")
    missing_extra.name = "optional_parser"

    try:
        get_ipfs_datasets_capabilities.cache_clear()
        with patch.object(
            capabilities_module,
            "import_module_optional",
            return_value=(object(), None),
        ):
            available = get_ipfs_datasets_capabilities()

        get_ipfs_datasets_capabilities.cache_clear()
        with patch.object(
            capabilities_module,
            "import_module_optional",
            return_value=(None, missing_extra),
        ):
            degraded = get_ipfs_datasets_capabilities()
    finally:
        get_ipfs_datasets_capabilities.cache_clear()

    assert tuple(available) == CAPABILITY_NAMES
    assert tuple(degraded) == CAPABILITY_NAMES
    for name in CAPABILITY_NAMES:
        available_payload = available[name].as_dict()
        degraded_payload = degraded[name].as_dict()
        assert set(available_payload) == status_keys
        assert set(degraded_payload) == status_keys
        assert set(available_payload["details"]) == detail_keys
        assert set(degraded_payload["details"]) == detail_keys


def test_capability_degraded_reason_identifies_extra_and_recovery_action():
    missing_extra = ModuleNotFoundError("No module named 'symbolicai'")
    missing_extra.name = "symbolicai"

    try:
        get_ipfs_datasets_capabilities.cache_clear()
        with patch.object(
            capabilities_module,
            "import_module_optional",
            side_effect=lambda module_name: (
                (None, missing_extra)
                if module_name == "ipfs_datasets_py.logic"
                else (object(), None)
            ),
        ):
            report = summarize_ipfs_datasets_capability_report()
    finally:
        get_ipfs_datasets_capabilities.cache_clear()

    logic_status = report["capabilities"]["logic_tools"]
    reason = logic_status["degraded_reason"]
    assert report["schema_version"] == CAPABILITY_SCHEMA_VERSION
    assert report["capability_keys"] == list(CAPABILITY_NAMES)
    assert report["degraded_capabilities"] == {"logic_tools": reason}
    assert logic_status["status"] == "degraded"
    assert logic_status["available"] is False
    assert logic_status["details"]["reason_code"] == "missing_optional_dependency"
    assert logic_status["details"]["missing_module"] == "symbolicai"
    assert "logic_tools" in reason
    assert "symbolicai" in reason
    assert 'python -m pip install "ipfs_datasets_py[logic]"' in reason


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
    assert all(
        payload["provider"] in {"ipfs_datasets_py", "ipfs_accelerate_py", "ipfs_kit_py"}
        and payload["details"]["owner"] == payload["provider"]
        for payload in startup_payload["capabilities"].values()
    )


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


def test_legal_adapter_import_helper_tries_current_scraper_fallback_paths():
    legal_module = importlib.import_module('integrations.ipfs_datasets.legal')
    sentinel = object()

    with patch.object(
        legal_module,
        'import_attr_optional',
        side_effect=[
            (None, ModuleNotFoundError('legacy path missing')),
            (sentinel, None),
        ],
    ) as import_mock:
        resolved, error = legal_module._import_attr_from_candidates(
            [
                'ipfs_datasets_py.processors.legal_scrapers.us_code_scraper',
                'ipfs_datasets_py.processors.legal_scrapers.federal_scrapers.us_code_scraper',
            ],
            'search_us_code',
        )

    assert resolved is sentinel
    assert error is None
    assert import_mock.call_count == 2
    assert import_mock.call_args_list[1].args == (
        'ipfs_datasets_py.processors.legal_scrapers.federal_scrapers.us_code_scraper',
        'search_us_code',
    )


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
    with patch('integrations.ipfs_datasets.legal._search_federal_register_hf_index_async', new=None):
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
    assert results[0]['metadata']['details']['hf_dataset_id'] == 'justicedao/ipfs_federal_register'
    assert results[0]['metadata']['details']['retrieval_backend'] == 'upstream_api'


def test_search_federal_register_prefers_huggingface_index_results():
    payload = {
        'status': 'success',
        'hits': [
            {
                'identifier': '2026-0002',
                'name': 'HF Indexed Rule',
                'snippet': 'Indexed via Hugging Face.',
            }
        ],
    }
    with patch('integrations.ipfs_datasets.legal._search_federal_register_hf_index_async', new=Mock(return_value=object())):
        with patch('integrations.ipfs_datasets.legal.run_async_compat', return_value=payload):
            results = search_federal_register('indexed rule', max_results=5)

    assert len(results) == 1
    assert results[0]['citation'] == '2026-0002'
    assert results[0]['title'] == 'HF Indexed Rule'
    assert results[0]['metadata']['details']['operation'] == 'search_federal_register_hf_index'
    assert results[0]['metadata']['details']['hf_dataset_id'] == 'justicedao/ipfs_federal_register'
    assert results[0]['metadata']['details']['retrieval_backend'] == 'huggingface_index'


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


def test_search_state_laws_normalizes_vector_results():
    payload = {
        'status': 'success',
        'results': [
            {
                'title': 'ORS 90.385',
                'content': 'A landlord may not retaliate against a tenant.',
                'url': 'https://example.com/ors/90.385',
                'metadata': {'state': 'OR'},
            }
        ],
    }
    with patch('integrations.ipfs_datasets.legal._build_query_vector', return_value=[0.1, 0.2, 0.3]):
        with patch('integrations.ipfs_datasets.legal._search_state_law_corpus_async', new=Mock(return_value=object())):
            with patch('integrations.ipfs_datasets.legal.run_async_compat', return_value=payload):
                results = search_state_laws('tenant retaliation', state='OR', max_results=5)

    assert len(results) == 1
    assert results[0]['source'] == 'state_law'
    assert results[0]['type'] == 'statute'
    assert results[0]['url'] == 'https://example.com/ors/90.385'
    assert results[0]['metadata']['details']['operation'] == 'search_state_laws'
    assert results[0]['metadata']['details']['hf_dataset_id'] == 'justicedao/ipfs_state_laws'
    assert results[0]['metadata']['details']['retrieval_backend'] == 'huggingface_corpus'


def test_search_state_administrative_rules_normalizes_vector_results():
    payload = {
        'status': 'success',
        'results': [
            {
                'title': 'OAR 839-003-0001',
                'content': 'Administrative enforcement rule text.',
                'url': 'https://example.com/oar/839-003-0001',
                'metadata': {'state': 'OR'},
            }
        ],
    }
    with patch('integrations.ipfs_datasets.legal._build_query_vector', return_value=[0.1, 0.2, 0.3]):
        with patch('integrations.ipfs_datasets.legal._search_state_law_corpus_async', new=Mock(return_value=object())):
            with patch('integrations.ipfs_datasets.legal.run_async_compat', return_value=payload):
                results = search_state_administrative_rules('housing rule', state='OR', max_results=5)

    assert len(results) == 1
    assert results[0]['source'] == 'state_admin_rules'
    assert results[0]['type'] == 'administrative_rule'
    assert results[0]['metadata']['details']['operation'] == 'search_state_administrative_rules'
    assert results[0]['metadata']['details']['hf_dataset_id'] == 'justicedao/ipfs_state_admin_rules'
    assert results[0]['metadata']['details']['retrieval_backend'] == 'huggingface_corpus'


def test_search_state_laws_reports_router_embedding_failure(caplog):
    router = Mock()
    router.embed_text.side_effect = RuntimeError('embedding provider unavailable')

    with patch.object(legal_module, 'EMBEDDINGS_AVAILABLE', True), patch.object(
        legal_module,
        'embed_query_text',
        new=None,
    ), patch.object(legal_module, 'get_embeddings_router', return_value=router), patch.object(
        legal_module,
        '_search_state_law_corpus_async',
        new=Mock(return_value=object()),
    ), patch.object(legal_module, '_search_hf_parquet_text', return_value=[]):
        with caplog.at_level('WARNING', logger=legal_module.__name__):
            results = search_state_laws(
                'tenant retaliation',
                state='OR',
                embedding_model='test-model',
                embedding_provider='test-provider',
                allow_live_scrape_fallback=False,
            )

    assert results == []
    diagnostics = get_last_legal_search_diagnostic('search_state_laws')
    assert diagnostics['embedding'] == {
        'status': 'error',
        'stage': 'router_embed_text',
        'provider': 'test-provider',
        'model_name': 'test-model',
        'error_type': 'RuntimeError',
        'error': 'embedding provider unavailable',
    }
    assert 'continuing with text-search fallbacks' in caplog.text
    assert 'embedding provider unavailable' in caplog.text


def test_search_state_laws_can_skip_live_scrape_fallback():
    payload = {'status': 'success', 'results': []}
    with patch('integrations.ipfs_datasets.legal._build_query_vector', return_value=[0.1, 0.2, 0.3]):
        with patch('integrations.ipfs_datasets.legal._search_state_law_corpus_async', new=Mock(return_value=object())):
            with patch('integrations.ipfs_datasets.legal.run_async_compat', return_value=payload):
                with patch('integrations.ipfs_datasets.legal._scrape_state_laws_async', new=Mock(return_value=object())) as scrape_mock:
                    results = search_state_laws(
                        'tenant retaliation',
                        state='OR',
                        max_results=5,
                        allow_live_scrape_fallback=False,
                    )

    assert results == []
    scrape_mock.assert_not_called()


def test_search_state_laws_uses_hf_parquet_fallback_before_live_scrape():
    payload = {'status': 'success', 'results': []}
    parquet_results = [
        {
            'citation': 'ORS 90.385',
            'title': 'Retaliatory conduct by landlord',
            'metadata': {
                'details': {
                    'operation': 'search_state_laws_hf_parquet',
                    'hf_dataset_id': 'justicedao/ipfs_state_laws',
                    'retrieval_backend': 'huggingface_parquet',
                }
            },
        }
    ]
    with patch('integrations.ipfs_datasets.legal._build_query_vector', return_value=[0.1, 0.2, 0.3]):
        with patch('integrations.ipfs_datasets.legal._search_state_law_corpus_async', new=Mock(return_value=object())):
            with patch('integrations.ipfs_datasets.legal.run_async_compat', return_value=payload):
                with patch('integrations.ipfs_datasets.legal._search_hf_parquet_text', return_value=parquet_results) as parquet_mock:
                    with patch('integrations.ipfs_datasets.legal._scrape_state_laws_async', new=Mock(return_value=object())) as scrape_mock:
                        results = search_state_laws('tenant retaliation', state='OR', max_results=5)

    assert results == parquet_results
    parquet_mock.assert_called_once()
    scrape_mock.assert_not_called()


def test_search_state_laws_records_hf_coverage_diagnostic_for_missing_state_rows():
    payload = {'status': 'success', 'results': []}

    def _parquet_side_effect(**kwargs):
        kwargs['diagnostics'].update({
            'warning_code': 'hf_state_rows_missing',
            'warning_message': 'Hugging Face dataset justicedao/ipfs_state_laws does not currently expose rows for requested state OR.',
        })
        kwargs['diagnostics'].setdefault('parquet', {})['state_row_count'] = 0
        return []

    with patch('integrations.ipfs_datasets.legal._build_query_vector', return_value=[0.1, 0.2, 0.3]):
        with patch('integrations.ipfs_datasets.legal._search_state_law_corpus_async', new=Mock(return_value=object())):
            with patch('integrations.ipfs_datasets.legal.run_async_compat', return_value=payload):
                with patch('integrations.ipfs_datasets.legal._search_hf_parquet_text', side_effect=_parquet_side_effect):
                    results = search_state_laws(
                        'tenant retaliation',
                        state='OR',
                        max_results=5,
                        allow_live_scrape_fallback=False,
                    )

    assert results == []
    diagnostic = get_last_legal_search_diagnostic('search_state_laws')
    assert diagnostic['warning_code'] == 'hf_state_rows_missing'
    assert diagnostic['state_code'] == 'OR'
    assert diagnostic['hf_dataset_id'] == 'justicedao/ipfs_state_laws'
    assert diagnostic['parquet']['state_row_count'] == 0


def test_legal_source_availability_exposes_state_families():
    assert 'state_statutes' in LEGAL_SOURCE_AVAILABILITY
    assert 'administrative_rules' in LEGAL_SOURCE_AVAILABILITY


def test_search_legal_authority_program_routes_by_authority_family():
    program = {
        'program_id': 'legal_search_program:test',
        'program_type': 'adverse_authority_search',
        'authority_intent': 'oppose',
        'query_text': 'retaliation adverse authority exception',
        'jurisdiction': 'OR',
        'authority_families': ['case_law', 'docket_material'],
    }

    with patch('integrations.ipfs_datasets.legal.search_recap_documents', return_value=[
        {'citation': 'Example v. Agency', 'type': 'case_law'},
    ]) as recap_search:
        with patch('integrations.ipfs_datasets.legal.search_us_code') as us_code_search:
            result = search_legal_authority_program(program, max_results=2)

    assert recap_search.call_count == 2
    recap_search.assert_any_call('retaliation adverse authority exception', max_results=2)
    us_code_search.assert_not_called()
    assert result['result_count'] == 2
    assert result['results']['case_law'][0]['citation'] == 'Example v. Agency'
    assert result['results']['docket_materials'][0]['citation'] == 'Example v. Agency'
    assert result['metadata']['details']['operation'] == 'search_legal_authority_program'
    assert result['metadata']['details']['authority_intent'] == 'oppose'


def test_mediator_adapter_detects_current_legal_scraper_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        package_root = Path(tmpdir) / 'ipfs_datasets_py'
        processors_root = package_root / 'processors'
        legal_root = processors_root / 'legal_scrapers'
        package_root.mkdir()
        processors_root.mkdir()
        legal_root.mkdir()
        (package_root / '__init__.py').write_text('', encoding='utf-8')
        (processors_root / '__init__.py').write_text('', encoding='utf-8')
        (legal_root / '__init__.py').write_text('', encoding='utf-8')
        (legal_root / 'legal_dataset_api.py').write_text('', encoding='utf-8')

        fake_spec = type(
            'FakeSpec',
            (),
            {'submodule_search_locations': [str(package_root)]},
        )()

        with patch('mediator.integrations.adapter.importlib.util.find_spec', return_value=fake_spec):
            status = mediator_adapter_module.detect_ipfs_datasets_capabilities().legal_datasets

    assert status.available is True
    assert status.name == 'ipfs_datasets_py.processors.legal_scrapers'


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


def test_search_multi_engine_web_returns_typed_degradation_on_orchestrator_failure():
    fallback_records = [{'url': 'https://example.com/fallback', 'source_type': 'brave_search'}]

    with patch('integrations.ipfs_datasets.search.MULTI_ENGINE_SEARCH_AVAILABLE', True):
        with patch('integrations.ipfs_datasets.search.OrchestratorConfig', return_value=object()):
            with patch(
                'integrations.ipfs_datasets.search.MultiEngineOrchestrator',
                side_effect=RuntimeError('orchestrator offline'),
            ):
                with patch(
                    'integrations.ipfs_datasets.search.search_brave_web',
                    return_value=fallback_records,
                ):
                    results = search_multi_engine_web('agency guidance', max_results=5)

    assert isinstance(results, DegradedSearchResults)
    assert results == fallback_records
    assert results.status == 'degraded'
    assert results.operation == 'search_multi_engine_web'
    assert results.error_type == 'RuntimeError'
    assert results.fallback_provider == 'brave'
    assert results.as_dict() == {
        'status': 'degraded',
        'operation': 'search_multi_engine_web',
        'degraded_reason': 'orchestrator offline',
        'error_type': 'RuntimeError',
        'fallback_provider': 'brave',
        'result_count': 1,
        'results': fallback_records,
    }


def test_rank_search_results_explains_claim_element_and_archive_priority():
    results = rank_search_results(
        [
            {
                'title': 'Generic workplace result',
                'description': 'General workplace article',
                'source_type': 'web',
                'metadata': {'score': 0.4},
            },
            {
                'title': 'Archived retaliation termination memo',
                'description': 'Adverse action after protected complaint within 180 days',
                'source_type': 'web_archive',
                'metadata': {
                    'score': 0.25,
                    'content_origin': 'historical_archive_capture',
                    'quality_score': 0.9,
                    'published_date': '2025-03-15',
                    'graph_trace_summary': {'traced_link_count': 2},
                    'support_quality_summary': {'dominant_quality_tier': 'strong_support'},
                },
            },
        ],
        query='retaliation termination 2025',
        claim_element_text='Adverse action after protected complaint',
        temporal_context='within 180 days in 2025',
        max_results=2,
    )

    assert results[0]['source_type'] == 'web_archive'
    factors = results[0]['metadata']['search_ranking_factors']
    assert factors['claim_element_fit_weight'] > 0.0
    assert factors['source_quality_weight'] > 0.0
    assert factors['temporal_relevance_weight'] > 0.0
    assert factors['graph_signal_weight'] > 0.0
    assert factors['archive_signal_weight'] > 0.0
    assert results[0]['metadata']['search_ranking_explanation']


def test_archive_url_snapshot_normalizes_wayback_capture_metadata():
    response = Mock()
    response.status_code = 302
    response.headers = {
        'Content-Location': '/web/20260719010101/https://example.com/policy',
    }
    response.url = 'https://web.archive.org/save/https://example.com/policy'
    session = Mock()
    session.get = Mock(return_value=response)

    result = archive_url_snapshot('https://example.com/policy', session=session)

    assert result['archived'] is True
    assert result['archive_url'] == 'https://web.archive.org/web/20260719010101/https://example.com/policy'
    assert result['captured_at'] == '20260719010101'
    assert result['content_origin'] == 'historical_archive_capture'
    assert result['metadata']['details']['operation'] == 'archive_url_snapshot'


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
    assert result['status'] == 'completed'
    assert result['pid'] == os.getpid()
    assert result['updated_at']
    assert result['artifacts']['final_result_count'] == len(result['final_results'])
    assert result['last_error'] is None
    assert daemon.status_payload() == {
        key: result[key]
        for key in ('status', 'pid', 'updated_at', 'artifacts', 'last_error')
    }
    assert result['final_results']
    assert 'https://example.com/policy' in result['coverage_ledger']
    assert result['tactic_history']['multi_engine_search']


def test_parse_document_bytes_returns_normalized_shape():
    from integrations.ipfs_datasets.provenance import build_document_parse_contract

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
    assert result['chunks'][0]['metadata']['source'] == 'bytes'
    assert result['chunks'][0]['metadata']['input_format'] == 'text'
    assert result['chunks'][0]['metadata']['parser_version'] == 'documents-adapter:1'
    assert result['chunks'][0]['metadata']['source_span']['char_start'] == 0
    assert result['chunks'][0]['metadata']['source_span']['char_end'] == len('Hello world')
    assert result['chunks'][0]['metadata']['source_span']['page_start'] == 1
    assert result['chunks'][0]['metadata']['source_span']['page_end'] == 1
    assert result['chunks'][0]['metadata']['section_label'] == ''
    assert result['metadata']['operation'] == 'parse_document_text'
    assert result['metadata']['implementation_status'] in {'implemented', 'fallback'}
    contract = build_document_parse_contract(result, default_source='bytes')
    assert contract['chunks'][0]['chunk_id'] == result['chunks'][0]['chunk_id']
    assert contract['chunks'][0]['metadata']['source_span']['char_end'] == len('Hello world')


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
    assert result['chunks'][0]['metadata']['input_format'] == 'html'
    assert result['chunks'][0]['metadata']['extraction_method'] == 'html_to_text'


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
    assert result['chunks'][0]['metadata']['input_format'] == 'docx'
    assert result['chunks'][0]['metadata']['source_span']['page_count'] == 1


def test_parse_document_bytes_extracts_xlsx_shared_strings():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(
            '[Content_Types].xml',
            '<?xml version="1.0" encoding="UTF-8"?>',
        )
        archive.writestr(
            'xl/sharedStrings.xml',
            (
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<si><t>Intake Date</t></si>'
                '<si><t>March 5 discrimination complaint</t></si>'
                '</sst>'
            ),
        )
        archive.writestr(
            'xl/worksheets/sheet1.xml',
            '<worksheet><sheetData><row><c><v>1</v></c></row></sheetData></worksheet>',
        )

    result = parse_document_bytes(
        buffer.getvalue(),
        filename='timeline.xlsx',
        mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )

    assert 'Intake Date' in result['text']
    assert 'March 5 discrimination complaint' in result['text']
    assert result['metadata']['input_format'] == 'xlsx'
    assert result['summary']['input_format'] == 'xlsx'
    assert result['lineage']['normalization'] == 'xlsx_xml_to_text'
    assert result['summary']['quality_tier'] == 'medium'
    assert result['chunks'][0]['metadata']['extraction_method'] == 'xlsx_xml_to_text'


def test_parse_document_bytes_extracts_pptx_slide_text():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(
            '[Content_Types].xml',
            '<?xml version="1.0" encoding="UTF-8"?>',
        )
        archive.writestr(
            'ppt/slides/slide1.xml',
            (
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                '<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Board presentation</a:t></a:r></a:p>'
                '<a:p><a:r><a:t>Reasonable accommodation timeline</a:t></a:r></a:p>'
                '</p:txBody></p:sp></p:spTree></p:cSld></p:sld>'
            ),
        )

    result = parse_document_bytes(
        buffer.getvalue(),
        filename='presentation.pptx',
        mime_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
    )

    assert 'Board presentation' in result['text']
    assert 'Reasonable accommodation timeline' in result['text']
    assert result['metadata']['input_format'] == 'pptx'
    assert result['lineage']['normalization'] == 'pptx_xml_to_text'
    assert result['summary']['quality_tier'] == 'medium'


def test_parse_document_bytes_extracts_opendocument_content_xml():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('mimetype', 'application/vnd.oasis.opendocument.spreadsheet')
        archive.writestr(
            'content.xml',
            (
                '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
                '<office:body><office:spreadsheet><text:p>Voucher record</text:p>'
                '<text:p>Payment interruption evidence</text:p></office:spreadsheet></office:body>'
                '</office:document-content>'
            ),
        )

    result = parse_document_bytes(
        buffer.getvalue(),
        filename='records.ods',
        mime_type='application/vnd.oasis.opendocument.spreadsheet',
    )

    assert 'Voucher record' in result['text']
    assert 'Payment interruption evidence' in result['text']
    assert result['metadata']['input_format'] == 'ods'
    assert result['lineage']['normalization'] == 'opendocument_xml_to_text'


def test_parse_document_bytes_normalizes_csv_input():
    result = parse_document_bytes(
        b'date,event\n2026-03-05,Reported discrimination\n',
        filename='events.csv',
        mime_type='text/csv',
    )

    assert 'Reported discrimination' in result['text']
    assert result['metadata']['input_format'] == 'csv'
    assert result['lineage']['normalization'] == 'csv_to_text'
    assert result['summary']['quality_tier'] == 'high'


def test_parse_document_bytes_reports_legacy_doc_degraded_contract():
    result = parse_document_bytes(
        b'\xd0\xcf\x11\xe0 legacy office binary',
        filename='statement.doc',
        mime_type='application/msword',
    )

    assert result['metadata']['input_format'] == 'doc'
    assert result['summary']['input_format'] == 'doc'
    assert result['summary']['extraction_method'] in {'office_binary_text_fallback', 'office_binary_unparsed'}
    assert 'legacy_office_binary_fallback' in result['metadata']['parse_quality']['quality_flags']


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
    assert should_parse_document_input(evidence_type='attachment', filename='events.csv', mime_type='text/csv') is True
    assert should_parse_document_input(evidence_type='attachment', filename='records.xlsx', mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') is True
    assert should_parse_document_input(evidence_type='attachment', filename='slides.pptx', mime_type='application/vnd.openxmlformats-officedocument.presentationml.presentation') is True
    assert should_parse_document_input(evidence_type='attachment', filename='records.ods', mime_type='application/vnd.oasis.opendocument.spreadsheet') is True
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


def test_summarize_document_parse_preserves_quality_fields():
    result = parse_document_bytes(
        b'<html><body><p>Employment discrimination is prohibited.</p></body></html>',
        filename='policy.html',
        mime_type='text/html',
        source='web_document',
    )

    summary = summarize_document_parse(result)

    assert summary['status'] == result['summary']['status']
    assert summary['input_format'] == 'html'
    assert summary['extraction_method'] == 'html_to_text'
    assert summary['quality_tier'] == 'high'
    assert summary['quality_score'] == 95.0
    assert summary['page_count'] == 1
    assert summary['source'] == 'web_document'


def test_summarize_document_parse_handles_metadata_only_contract():
    summary = summarize_document_parse({
        'status': 'fallback',
        'text': 'Email body',
        'chunks': [{'chunk_id': 'chunk-0', 'text': 'Email body'}],
        'metadata': {
            'parser_version': 'documents-adapter:1',
            'input_format': 'email',
            'paragraph_count': 1,
            'source': 'bytes',
            'extraction_method': 'email_to_text',
            'parse_quality': {
                'quality_tier': 'high',
                'quality_score': 93.0,
            },
            'source_span': {
                'page_count': 1,
            },
        },
    })

    assert summary['status'] == 'fallback'
    assert summary['chunk_count'] == 1
    assert summary['text_length'] == len('Email body')
    assert summary['input_format'] == 'email'
    assert summary['extraction_method'] == 'email_to_text'
    assert summary['quality_tier'] == 'high'
    assert summary['quality_score'] == 93.0
    assert summary['page_count'] == 1
    assert summary['source'] == 'bytes'


def test_extract_graph_from_text_returns_normalized_shape():
    result = extract_graph_from_text('Example complaint text', source_id='artifact-1')

    assert result['source_id'] == 'artifact-1'
    assert result['entities'][0]['id'] == 'artifact-1'
    assert result['status'] in {'available', 'degraded', 'unavailable'}
    assert result['metadata']['private_extraction']['status'] in {'available', 'degraded', 'unavailable'}
    assert all(entity['type'] in {'artifact', 'model_suggestion'} for entity in result['entities'])
    assert all(entity.get('assertion', {}).get('assertion_status') != 'asserted' for entity in result['entities'])
    assert not any(relationship['relation_type'] in {'has_fact', 'supports', 'supported_by'} for relationship in result['relationships'])
    assert result['metadata']['operation'] == 'extract_graph_from_text'


def test_build_validate_score_ontology_returns_compact_workflow_gap_summary():
    with patch('integrations.ipfs_datasets.graphrag.GRAPHRAG_AVAILABLE', False):
        with patch('integrations.ipfs_datasets.graphrag.GRAPHRAG_ERROR', 'GraphRAG extras missing'):
            result = build_validate_score_ontology(
                'I complained to HR and was fired the next week.',
                claim_type='retaliation',
            )

    quality = result['ontology_quality']

    assert quality['workflow_operation'] == 'build_validate_score_ontology'
    assert quality['workflow_backend_available'] is False
    assert quality['workflow_implementation_status'] == 'implemented'
    assert quality['workflow_degraded_reason'] == 'GraphRAG extras missing'
    assert quality['gap_count'] == len(result['gaps']['gaps'])
    assert quality['gap_type_counts']
    assert quality['gap_severity_counts']
    assert quality['gap_follow_up_action_counts']
    assert 'entity_count' in quality
    assert quality['relation_count'] >= 0
    assert quality['concept_count'] >= 0


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
    # Persistence preserves a real unavailable/suggestion payload; it must not
    # depend on optional extraction inventing a fact or an edge for this test.
    graph_payload = {
        'status': 'unavailable', 'source_id': 'artifact-1',
        'entities': [{'id': 'artifact-1', 'type': 'artifact', 'name': 'Example complaint text'}],
        'relationships': [],
        'metadata': {'private_extraction': {'status': 'unavailable', 'diagnostic': 'extractor_unavailable'}},
    }

    result = persist_graph_snapshot(
        graph_payload,
        graph_id='graph:test-stable-contract',
        graph_changed=True,
        existing_graph=False,
        persistence_metadata={'projection_target': 'complaint_phase_knowledge_graph'},
    )

    assert result['status'] == 'stored-fallback'
    assert result['graph_id'] == 'graph:test-stable-contract'
    assert result['persisted'] is True
    assert result['created'] is True
    assert result['reused'] is False
    assert result['node_count'] == 1
    assert result['edge_count'] == 0
    assert result['metadata']['source_id'] == 'artifact-1'
    assert result['metadata']['projection_target'] == 'complaint_phase_knowledge_graph'
    assert result['metadata']['lineage']['status'] == graph_payload['status']
    assert result['metadata']['persistence_scope'] == 'adapter_memory'
    assert result['metadata']['operation'] == 'persist_graph_snapshot'


def test_graph_persistence_interface_receives_versioned_provenance_contract():
    class RecordingPersistence:
        def __init__(self):
            self.request = None

        def persist_snapshot(self, request):
            self.request = request
            return {'status': 'persisted', 'persisted': True, 'created': True}

        def get_snapshot(self, graph_id, *, graph_version=None):
            return self.request

    backend = RecordingPersistence()
    assert isinstance(backend, GraphPersistence)
    graph_payload = extract_graph_from_text(
        'A dated notice supports the claim.',
        source_id='artifact-9',
        metadata={
            'provenance': {
                'source_type': 'evidence',
                'source_record_id': 9,
                'content_hash': 'source-hash',
            }
        },
    )

    result = persist_graph_snapshot(graph_payload, persistence=backend)

    assert result['status'] == 'persisted'
    assert result['persisted'] is True
    assert result['graph_version'].startswith('sha256:')
    assert result['snapshot_id'].startswith('graph-snapshot:')
    assert result['content_hash'] == backend.request['content_hash']
    assert backend.request['graph_id'] == result['graph_id']
    assert backend.request['provenance']['source_id'] == 'artifact-9'
    assert backend.request['provenance']['source_type'] == 'evidence'
    assert backend.request['provenance']['source_record_id'] == 9


def test_graph_query_interface_receives_query_and_provenance_fields():
    class RecordingQuery:
        def __init__(self):
            self.query = None

        def query_support(self, query):
            self.query = query
            return {
                'results': [{'fact_id': 'fact:backend', 'text': 'Backend result'}],
                'summary': {'result_count': 1},
            }

    backend = RecordingQuery()
    assert isinstance(backend, GraphQuery)

    result = query_graph_support(
        'employment:1',
        graph_id='case:1',
        graph_version='7',
        claim_type='employment',
        claim_element_text='Protected activity',
        filters={'source_type': 'evidence'},
        provenance={'source_system': 'complaint-generator'},
        query_backend=backend,
    )

    assert result['results'][0]['fact_id'] == 'fact:backend'
    assert result['metadata']['implementation_status'] == 'backend'
    assert backend.query['graph_id'] == 'case:1'
    assert backend.query['graph_version'] == '7'
    assert backend.query['filters'] == {'source_type': 'evidence'}
    assert backend.query['provenance']['source_system'] == 'complaint-generator'


def test_query_graph_snapshot_returns_persisted_adapter_record():
    graph_payload = {
        **extract_graph_from_text('Protected activity appears in the complaint.', source_id='artifact-query-1'),
        'support_facts': [
            {
                'fact_id': 'fact:registry-1',
                'text': 'Protected activity appears in the complaint.',
                'source_family': 'evidence',
                'source_record_id': 12,
                'source_ref': 'bafy-evidence',
                'record_scope': 'evidence',
                'artifact_family': 'archived_web_page',
                'corpus_family': 'web_page',
                'content_origin': 'historical_archive_capture',
                'parse_source': 'web_document',
                'input_format': 'html',
                'quality_tier': 'high',
                'chunk_id': 'chunk-0',
                'source_passage': {'chunk_id': 'chunk-0', 'text': 'Protected activity'},
            }
        ],
    }
    persisted = persist_graph_snapshot(
        graph_payload,
        graph_id='graph:test-query-contract',
        graph_changed=True,
        existing_graph=False,
        persistence_metadata={'record_scope': 'evidence', 'record_key': '12'},
    )
    reused = persist_graph_snapshot(
        graph_payload,
        graph_id='graph:test-query-contract',
        graph_changed=True,
        existing_graph=False,
        persistence_metadata={'record_scope': 'evidence', 'record_key': '12'},
    )

    by_id = query_graph_snapshot('graph:test-query-contract')
    by_source = query_graph_snapshot(source_id='artifact-query-1')

    assert persisted['created'] is True
    assert reused['created'] is False
    assert reused['reused'] is True
    assert by_id['status'] == 'found'
    assert by_id['found'] is True
    assert by_id['snapshot_count'] == 1
    assert by_id['fact_registry_summary']['aggregation_scope'] == 'graph_snapshot_query'
    assert by_id['fact_registry_summary']['snapshot_count'] == 1
    assert by_id['fact_registry_summary']['fact_count'] == 1
    assert by_id['fact_registry_summary']['source_family_counts'] == {'evidence': 1}
    assert by_id['fact_registry_summary']['source_ref_counts'] == {'bafy-evidence': 1}
    assert by_id['fact_registry_summary']['passage_anchored_count'] == 1
    assert by_id['snapshots'][0]['graph_id'] == 'graph:test-query-contract'
    assert by_id['snapshots'][0]['source_id'] == 'artifact-query-1'
    assert by_id['snapshots'][0]['metadata']['record_scope'] == 'evidence'
    assert by_id['snapshots'][0]['metadata']['record_key'] == '12'
    assert by_id['snapshots'][0]['fact_registry_summary']['fact_count'] == 1
    assert by_id['snapshots'][0]['fact_registry_summary']['source_family_counts'] == {'evidence': 1}
    assert by_id['snapshots'][0]['fact_registry_summary']['artifact_family_counts'] == {'archived_web_page': 1}
    assert by_id['snapshots'][0]['fact_registry_summary']['passage_anchored_count'] == 1
    assert by_id['snapshots'][0]['metadata']['fact_registry_summary'] == by_id['snapshots'][0]['fact_registry_summary']
    assert by_id['snapshots'][0]['entities']
    assert by_id['metadata']['operation'] == 'query_graph_snapshot'
    assert any(snapshot['graph_id'] == 'graph:test-query-contract' for snapshot in by_source['snapshots'])


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


def test_create_ontology_generator_does_not_swallow_initialization_failure():
    class FailingOntologyGenerator:
        def __init__(self):
            raise RuntimeError('ontology model initialization failed')

    with patch(
        'integrations.ipfs_datasets.graphrag.OntologyGenerator',
        FailingOntologyGenerator,
    ), pytest.raises(RuntimeError, match='ontology model initialization failed'):
        create_ontology_generator()


def test_build_ontology_reports_generator_initialization_failure():
    class FailingOntologyGenerator:
        def __init__(self):
            raise RuntimeError('ontology model initialization failed')

    with patch(
        'integrations.ipfs_datasets.graphrag.OntologyGenerator',
        FailingOntologyGenerator,
    ):
        result = build_ontology('Employment retaliation policy.')

    assert result['status'] == 'error'
    assert result['ontology'] is None
    assert result['metadata']['text_length'] == 30
    assert result['metadata']['error'] == 'ontology model initialization failed'
    assert result['metadata']['operation'] == 'build_ontology'
    assert result['metadata']['backend_available'] is True
    assert result['metadata']['implementation_status'] == 'error'
    assert result['metadata']['details'] == {
        'operation': 'build_ontology',
        'backend_available': True,
        'implementation_status': 'error',
    }


def test_logic_stubbed_adapters_summarize_temporal_predicate_shapes():
    predicates = [
        {'predicate_type': 'claim_element', 'claim_type': 'retaliation', 'predicate_id': 'retaliation:1'},
        {'predicate_type': 'support_trace', 'claim_type': 'retaliation', 'predicate_id': 'fact:support'},
        {'predicate_type': 'temporal_fact', 'claim_type': 'retaliation', 'predicate_id': 'temporal_fact:fact_1'},
        {'predicate_type': 'temporal_proof_lead', 'claim_type': 'retaliation', 'predicate_id': 'temporal_proof_lead:lead_1'},
        {'predicate_type': 'temporal_relation', 'claim_type': 'retaliation', 'predicate_id': 'timeline_relation_001'},
        {'predicate_type': 'temporal_issue', 'claim_type': 'retaliation', 'predicate_id': 'temporal_reverse_before_001'},
        {'predicate_type': 'contradiction_candidate', 'claim_type': 'retaliation', 'predicate_id': 'contradiction:retaliation:1:0'},
    ]

    proof_result = prove_claim_elements(predicates)
    contradiction_result = check_contradictions(predicates)

    for result in (proof_result, contradiction_result):
        assert result['predicate_count'] == 7
        assert result['predicate_type_counts'] == {
            'claim_element': 1,
            'contradiction_candidate': 1,
            'support_trace': 1,
            'temporal_fact': 1,
            'temporal_issue': 1,
            'temporal_proof_lead': 1,
            'temporal_relation': 1,
        }
        assert result['claim_type_counts'] == {'retaliation': 7}
        assert result['temporal_predicate_count'] == 4
        assert result['temporal_relation_count'] == 1
        assert result['contradiction_signal_count'] == 2
        assert result['metadata']['predicate_type_counts'] == result['predicate_type_counts']
        assert result['metadata']['details']['predicate_type_counts'] == result['predicate_type_counts']
        assert result['metadata']['details']['temporal_predicate_count'] == 4
        assert result['metadata']['details']['contradiction_signal_count'] == 2


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


def test_storage_backend_reports_unavailable_when_kubo_cli_missing():
    fake_backend = type('KuboCLIBackend', (), {'_cmd': 'ipfs'})()

    with patch.dict('os.environ', {'IPFS_DATASETS_PY_KUBO_CMD': '', 'KUBO_CMD': ''}):
        with patch('integrations.ipfs_datasets.storage.get_ipfs_backend', return_value=fake_backend):
            with patch('integrations.ipfs_datasets.storage.shutil.which', return_value=None):
                stored = store_bytes(b'complaint text', pin_content=False)
                backend_status = storage_backend_status()

    assert stored['status'] == 'unavailable'
    assert 'missing ipfs CLI binary' in stored['metadata']['degraded_reason']
    assert backend_status['status'] == 'unavailable'
    assert backend_status['backend_name'] == 'KuboCLIBackend'
    assert 'missing ipfs CLI binary' in backend_status['metadata']['degraded_reason']


def test_storage_backend_auto_discovers_repo_local_kubo_install(tmp_path: Path):
    fake_backend = type('KuboCLIBackend', (), {'_cmd': 'ipfs'})()
    local_root = tmp_path / 'ipfs_kit_py'
    bin_dir = local_root / 'bin'
    repo_dir = local_root / '.ipfs'
    bin_dir.mkdir(parents=True)
    repo_dir.mkdir(parents=True)
    (bin_dir / 'ipfs').write_text('#!/bin/sh\nexit 0\n')
    (repo_dir / 'config').write_text('{}')

    with patch.dict('os.environ', {'IPFS_DATASETS_PY_KUBO_CMD': '', 'KUBO_CMD': ''}, clear=False):
        with patch('integrations.ipfs_datasets.storage._repo_local_ipfs_kit_root', return_value=local_root):
            with patch('integrations.ipfs_datasets.storage.get_ipfs_backend', return_value=fake_backend):
                with patch('integrations.ipfs_datasets.storage.shutil.which', return_value=None):
                    backend_status = storage_backend_status()

    assert backend_status['status'] == 'available'
    assert backend_status['backend_name'] == 'KuboCLIBackend'
    assert fake_backend._cmd == str(bin_dir / 'ipfs')


def test_get_embeddings_router_falls_back_to_module_facade():
    with patch.object(vector_store_module, "embed_text", Mock(return_value=[0.1, 0.2, 0.3])):
        router = vector_store_module.get_embeddings_router(provider="hf_inference_api")
        result = router.embed_text("HACC evidence")

    assert router is not None
    assert type(router).__name__ == "EmbeddingsRouter"
    assert result == [0.1, 0.2, 0.3]


def test_embeddings_backend_status_reports_probe_success():
    with patch.object(vector_store_module, "embed_text", Mock(return_value=[0.1, 0.2, 0.3])):
        payload = embeddings_backend_status(perform_probe=True, provider="hf_inference_api")

    assert payload["status"] == "available"
    assert payload["probe_performed"] is True
    assert payload["probe_status"] == "available"
    assert payload["vector_length"] == 3
    assert "embed_text" in payload["available_methods"]


def test_vector_index_backend_status_reports_numpy_requirement_over_stale_import_error():
    with patch.object(vector_store_module, 'np', None), patch.object(
        vector_store_module,
        '_numpy_error',
        "No module named 'numpy'",
    ), patch.object(
        vector_store_module,
        'embed_texts_batched',
        Mock(return_value=[[0.1, 0.2, 0.3]]),
    ), patch.object(
        vector_store_module,
        'EMBEDDINGS_ERROR',
        '',
    ), patch.object(
        vector_store_module,
        'VECTOR_STORE_ERROR',
        "module 'ipfs_datasets_py.embeddings_router' has no attribute 'EmbeddingsRouter'",
    ):
        payload = vector_store_module.vector_index_backend_status(require_local_persistence=True)

    assert payload['status'] == 'unavailable'
    assert payload['error'] == 'numpy is required for local vector persistence and search'
    assert payload['metadata']['degraded_reason'] == "No module named 'numpy'"
    assert payload['available_methods'] == ['embed_texts_batched']


def test_router_status_report_combines_llm_ipfs_and_embeddings():
    with patch(
        "integrations.ipfs_datasets.router_status.llm_router_status",
        return_value={"status": "available", "error": ""},
    ), patch(
        "integrations.ipfs_datasets.router_status.storage_backend_status",
        return_value={"status": "available", "error": ""},
    ), patch(
        "integrations.ipfs_datasets.router_status.embeddings_backend_status",
        return_value={"status": "degraded", "error": "missing token"},
    ):
        report = get_router_status_report()

    assert report["status"] == "degraded"
    assert report["components"]["llm_router"]["status"] == "available"
    assert report["components"]["ipfs_router"]["status"] == "available"
    assert report["components"]["embeddings_router"]["status"] == "degraded"
    assert report["unavailable_components"]["embeddings_router"] == "missing token"


def test_local_cache_ipfs_backend_roundtrips_bytes(tmp_path):
    backend = LocalCacheIPFSBackend(cache_dir=str(tmp_path))
    cid = backend.add_bytes(b"HACC evidence blob", pin=True)

    assert cid.startswith("bafy")
    assert backend.cat(cid) == b"HACC evidence blob"


def test_ensure_ipfs_backend_uses_local_fallback_when_kubo_missing():
    fake_backend = type('KuboCLIBackend', (), {'_cmd': 'ipfs'})()
    with patch('integrations.ipfs_datasets.storage.get_ipfs_backend', return_value=fake_backend), patch(
        'integrations.ipfs_datasets.storage.shutil.which',
        return_value=None,
    ), patch(
        'integrations.ipfs_datasets.storage.set_default_ipfs_backend',
    ) as mock_set_default, patch(
        'integrations.ipfs_datasets.storage.clear_ipfs_backend_router_caches',
    ) as mock_clear:
        backend = ensure_ipfs_backend(prefer_local_fallback=True)

    assert isinstance(backend, LocalCacheIPFSBackend)
    mock_set_default.assert_called_once()
    mock_clear.assert_called_once()


# ---------------------------------------------------------------------------
# extraction_method_for_format and quality_score_for_format helpers
# ---------------------------------------------------------------------------

def test_extraction_method_for_format_returns_canonical_labels():
    from integrations.ipfs_datasets.documents import extraction_method_for_format

    assert extraction_method_for_format("html") == "html_to_text"
    assert extraction_method_for_format("email") == "email_to_text"
    assert extraction_method_for_format("rtf") == "rtf_to_text"
    assert extraction_method_for_format("docx") == "docx_xml_to_text"
    assert extraction_method_for_format("xlsx") == "xlsx_xml_to_text"
    assert extraction_method_for_format("pptx") == "pptx_xml_to_text"
    assert extraction_method_for_format("ods") == "opendocument_xml_to_text"
    assert extraction_method_for_format("csv") == "csv_to_text"
    assert extraction_method_for_format("doc", text_present=False) == "office_binary_unparsed"
    assert extraction_method_for_format("pdf", text_present=True) == "pdf_text_fallback"
    assert extraction_method_for_format("pdf", text_present=False) == "pdf_unparsed"
    assert extraction_method_for_format("text") == "text_normalization"
    assert extraction_method_for_format("unknown") == "text_normalization"


def test_quality_score_for_format_returns_expected_scores():
    from integrations.ipfs_datasets.documents import quality_score_for_format

    html_qs = quality_score_for_format("html")
    assert html_qs["quality_score"] == 95.0
    assert html_qs["quality_tier"] == "high"

    email_qs = quality_score_for_format("email")
    assert email_qs["quality_score"] == 93.0
    assert email_qs["quality_tier"] == "high"

    docx_qs = quality_score_for_format("docx")
    assert docx_qs["quality_score"] == 88.0
    assert docx_qs["quality_tier"] == "medium"

    xlsx_qs = quality_score_for_format("xlsx")
    assert xlsx_qs["quality_score"] == 84.0
    assert xlsx_qs["quality_tier"] == "medium"

    csv_qs = quality_score_for_format("csv")
    assert csv_qs["quality_score"] == 90.0
    assert csv_qs["quality_tier"] == "high"

    rtf_qs = quality_score_for_format("rtf")
    assert rtf_qs["quality_score"] == 82.0
    assert rtf_qs["quality_tier"] == "medium"

    pdf_qs = quality_score_for_format("pdf")
    assert pdf_qs["quality_score"] == 68.0
    assert pdf_qs["quality_tier"] == "low"

    empty_qs = quality_score_for_format("pdf", text_present=False)
    assert empty_qs["quality_score"] == 0.0
    assert empty_qs["quality_tier"] == "empty"


def test_extraction_method_for_format_matches_parse_document_bytes_output():
    """extraction_method_for_format must agree with the value embedded in parse results."""
    from integrations.ipfs_datasets.documents import (
        extraction_method_for_format,
        parse_document_bytes,
    )

    for fmt, payload, mime in [
        ("html", b"<html><body><p>Hello</p></body></html>", "text/html"),
        ("text", b"Plain text evidence.", "text/plain"),
    ]:
        parse_result = parse_document_bytes(payload, mime_type=mime)
        expected = extraction_method_for_format(fmt, text_present=True)
        assert parse_result["summary"]["extraction_method"] == expected


def test_quality_score_for_format_matches_parse_document_bytes_output():
    """quality_score_for_format must agree with the quality_score in parse results."""
    from integrations.ipfs_datasets.documents import (
        quality_score_for_format,
        parse_document_bytes,
    )

    html_payload = b"<html><body><p>Evidence content.</p></body></html>"
    parse_result = parse_document_bytes(html_payload, mime_type="text/html")
    expected = quality_score_for_format("html", text_present=True)
    assert parse_result["summary"]["quality_score"] == expected["quality_score"]
    assert parse_result["summary"]["quality_tier"] == expected["quality_tier"]
