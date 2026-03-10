"""Tests for the complaint-generator ipfs_datasets adapter layer."""

from unittest.mock import patch

from integrations.ipfs_datasets.capabilities import get_ipfs_datasets_capabilities
from integrations.ipfs_datasets.legal import (
    search_federal_register,
    search_recap_documents,
    search_us_code,
)
from integrations.ipfs_datasets.search import search_brave_web


def test_capability_registry_has_expected_keys():
    capabilities = get_ipfs_datasets_capabilities()
    assert {
        'llm_router',
        'ipfs_storage',
        'web_archiving',
        'common_crawl',
        'legal_scrapers',
        'graphrag',
        'logic_tools',
    }.issubset(capabilities.keys())


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
    with patch('integrations.ipfs_datasets.legal._search_us_code_async') as mock_search:
        mock_search.return_value = payload
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
    with patch('integrations.ipfs_datasets.search._search_brave') as mock_search:
        mock_search.return_value = payload
        with patch('integrations.ipfs_datasets.search.run_async_compat', return_value=payload):
            results = search_brave_web('example query', max_results=5)

    assert len(results) == 1
    assert results[0]['source_type'] == 'brave_search'
    assert results[0]['metadata']['language'] == 'en'