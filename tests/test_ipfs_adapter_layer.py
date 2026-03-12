"""Tests for the complaint-generator ipfs_datasets adapter layer."""

import tempfile
from unittest.mock import Mock, patch

from integrations.ipfs_datasets.capabilities import (
    get_ipfs_datasets_capabilities,
    summarize_ipfs_datasets_capability_report,
    summarize_ipfs_datasets_capabilities,
)
from integrations.ipfs_datasets.documents import parse_document_bytes, parse_document_file
from integrations.ipfs_datasets.graphs import extract_graph_from_text, persist_graph_snapshot, query_graph_support
from integrations.ipfs_datasets.graphrag import build_ontology, run_refinement_cycle, validate_ontology
from integrations.ipfs_datasets.legal import (
    search_federal_register,
    search_recap_documents,
    search_us_code,
)
from integrations.ipfs_datasets.logic import check_contradictions, prove_claim_elements, text_to_fol
from integrations.ipfs_datasets.mcp_gateway import execute_gateway_tool, list_gateway_tools
from integrations.ipfs_datasets.scraper_daemon import ScraperDaemon, ScraperDaemonConfig
from integrations.ipfs_datasets.search import (
    evaluate_scraped_content,
    scrape_web_content,
    search_brave_web,
    search_multi_engine_web,
)
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


def test_capability_summary_returns_strings():
    summary = summarize_ipfs_datasets_capabilities()
    assert summary
    assert all(isinstance(value, str) for value in summary.values())


def test_capability_report_returns_counts_and_nested_statuses():
    report = summarize_ipfs_datasets_capability_report()

    assert report["status"] in {"available", "degraded"}
    assert report["available_count"] + report["degraded_count"] == len(report["capabilities"])
    assert isinstance(report["available_capabilities"], list)
    assert isinstance(report["degraded_capabilities"], dict)


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
    assert result['metadata']['transform_lineage']['source'] == 'bytes'
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
        assert result['metadata']['operation']
        assert result['metadata']['implementation_status']
        assert result['metadata']['backend_available'] in {True, False}

    assert refinement_result['metadata']['rounds'] == 2