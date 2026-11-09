"""Bounded legal corpus candidate contract.

Parameter tests use explicit synthetic transport fakes. Separate guarded real
process cases exercise the fixed manager and actual inner-child cleanup. No
corpora are downloaded or case facts sent to a network service.
"""
import asyncio
from unittest.mock import Mock, patch

import pytest

from integrations.ipfs_datasets.legal import (
    DEFAULT_STATE_ADMIN_RULES_DATASET_ID,
    DEFAULT_STATE_LAWS_DATASET_ID,
    lookup_bounded_legal_corpus,
    search_legal_authority_program,
)


pytestmark = pytest.mark.no_auto_network

_VECTOR = [0.1, 0.2, 0.3]


def _row(**overrides):
    payload = {
        "citation": "42 U.S.C. § 1983",
        "uri": "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title42-section1983",
        "text": "Every person who, under color of any statute, subjects another to the deprivation of rights.",
        "snippet": "under color of any statute",
        "cid": "bafyuscode1983",
        "corpus_id": "justicedao/ipfs_uscode",
        "corpus_version": "prelim",
        "jurisdiction": "federal",
        "publication_date": "2024-01-02",
    }
    payload.update(overrides)
    return payload


def _install(monkeypatch, name, func):
    import integrations.ipfs_datasets.legal as legal
    monkeypatch.setattr(legal, name, func)
    async_symbols = {
        'us_code_corpus': '_search_us_code_corpus_async',
        'state_statute_corpus': '_search_state_law_corpus_async',
        'state_admin_corpus': '_search_state_law_corpus_async',
        'federal_register_corpus': '_search_federal_register_corpus_async',
        'court_rules_corpus': '_search_court_rules_corpus_async',
        'federal_register_direct': '_search_federal_register_async',
        'local_us_code_index': '_search_us_code_async',
    }
    def transport(api, parameters, timeout):
        target = getattr(legal, async_symbols[api])
        async def invoke():
            result = target(**parameters) if api in {'local_us_code_index', 'federal_register_direct'} else target(parameters)
            return await asyncio.wait_for(result, timeout)
        try:
            return 'ok', asyncio.run(invoke())
        except asyncio.TimeoutError:
            return 'timeout', None
        except Exception:
            return 'error', None
    monkeypatch.setattr(legal, '_run_owned_deadline', transport)


def _async_returning(payload, captured):
    async def _fake(parameters):
        captured.append(parameters)
        return payload

    return _fake


def test_live_parameter_dictionaries_cover_each_source_family(monkeypatch):
    captured = []
    families = [
        ("us_code", "_search_us_code_corpus_async", {}, "us_code_corpus"),
        (
            "state_statute",
            "_search_state_law_corpus_async",
            {"state": "WA"},
            "state_statute_corpus",
        ),
        (
            "state_administrative_rule",
            "_search_state_law_corpus_async",
            {"state": "WA"},
            "state_admin_corpus",
        ),
        (
            "federal_register",
            "_search_federal_register_corpus_async",
            {},
            "federal_register_corpus",
        ),
        (
            "court_rule",
            "_search_court_rules_corpus_async",
            {"court_jurisdiction": "federal"},
            "court_rules_corpus",
        ),
    ]
    for family, symbol, extra, _backend in families:
        captured.clear()
        _install(
            monkeypatch,
            symbol,
            _async_returning({"status": "success", "results": [_row(jurisdiction="WA" if extra.get("state") else "federal")]}, captured),
        )
        envelope = lookup_bounded_legal_corpus(
            source_family=family,
            query="color of statute",
            retrieval_mode="live",
            collection_name="legal_test",
            query_vector=_VECTOR,
            max_results=2,
            timeout_seconds=2,
            contains_private_facts=False,
            **extra,
        )
        assert envelope["status"] == "success"
        assert envelope["network_used"] is None
        assert envelope["setup_invoked"] is False
        assert envelope["applicability"] == "unknown"
        assert captured[0]["auto_setup_venv"] is False
        assert captured[0]["collection_name"] == "legal_test"
        assert captured[0]["query_vector"] == _VECTOR
        assert captured[0]["top_k"] == 2
        assert captured[0]["chunk_lookup_enabled"] is False
        assert "query_text" not in captured[0]
        candidate = envelope["results"][0]
        assert candidate["source_family"] == family
        assert candidate["uri_status"] == "source"
        assert candidate["citation_status"] == "source"
        assert candidate["content_hash"].startswith("sha256:")
        assert candidate["content_hash_scope"] == "source_passage"
        assert candidate["cid"] == "bafyuscode1983"
        assert candidate["corpus_version"] == "prelim"
        assert candidate["retrieved_at"]
        assert candidate["source_passage"]
        assert candidate["snippet"]
        assert candidate["snippet"] != candidate["source_passage"]
        assert candidate["applicability"] == "unknown"

    statute_params = []
    _install(
        monkeypatch,
        "_search_state_law_corpus_async",
        _async_returning({"status": "success", "results": []}, statute_params),
    )
    lookup_bounded_legal_corpus(
        source_family="state_statute",
        query="landlord",
        retrieval_mode="live",
        state="WA",
        collection_name="statutes",
        query_vector=_VECTOR,
        contains_private_facts=False,
    )
    assert statute_params[0]["hf_dataset_id"] == DEFAULT_STATE_LAWS_DATASET_ID
    assert statute_params[0]["hf_dataset_ids"] == [DEFAULT_STATE_LAWS_DATASET_ID]
    assert statute_params[0]["state"] == "WA"
    assert statute_params[0]["enrich_with_cases"] is False

    admin_params = []
    _install(
        monkeypatch,
        "_search_state_law_corpus_async",
        _async_returning({"status": "success", "results": []}, admin_params),
    )
    lookup_bounded_legal_corpus(
        source_family="state_administrative_rule",
        query="hearing",
        retrieval_mode="live",
        state="WA",
        collection_name="admin",
        query_vector=_VECTOR,
        contains_private_facts=False,
    )
    assert admin_params[0]["hf_dataset_ids"] == [DEFAULT_STATE_ADMIN_RULES_DATASET_ID]
    assert DEFAULT_STATE_LAWS_DATASET_ID not in admin_params[0]["hf_dataset_ids"]

    court_params = []
    _install(
        monkeypatch,
        "_search_court_rules_corpus_async",
        _async_returning({"status": "success", "results": []}, court_params),
    )
    lookup_bounded_legal_corpus(
        source_family="court_rule",
        query="time to answer",
        retrieval_mode="live",
        court_jurisdiction="state",
        state="WA",
        collection_name="courts",
        query_vector=_VECTOR,
        contains_private_facts=False,
    )
    assert court_params[0]["jurisdiction"] == "state"
    assert court_params[0]["state"] == "WA"
    assert court_params[0]["enrich_with_cases"] is False


def test_missing_and_corrupted_provenance_stay_unknown():
    missing = lookup_bounded_legal_corpus(
        source_family="us_code",
        retrieval_mode="cache",
        offline_cache={"us_code|||": [{}]},
        contains_private_facts=False,
    )
    row = missing["results"][0]
    assert row["provenance_status"] == "missing"
    assert row["uri_status"] == "missing"
    assert row["citation_status"] == "missing"
    assert row["jurisdiction"] == "unknown"
    assert row["effective_date"] is None
    assert row["content_hash_scope"] == "unavailable"

    corrupted = lookup_bounded_legal_corpus(
        source_family="us_code",
        retrieval_mode="cache",
        offline_cache={
            "us_code|||": [
                {
                    "text": "A real passage about venue.",
                    "cid": 12,
                    "generated_url": "https://example.invalid/generated",
                    "content_hash": "sha256:not-the-passage",
                }
            ]
        },
    )
    bad = corrupted["results"][0]
    assert bad["provenance_status"] == "corrupted"
    assert bad["uri_status"] == "unverified_generated"
    assert bad["cid"] is None
    assert bad["content_hash_mismatch"] is True
    assert bad["snippet"] != bad["source_passage"]


def test_cross_jurisdiction_hit_is_not_treated_as_a_match():
    keyed = lookup_bounded_legal_corpus(
        source_family="state_statute",
        query="",
        retrieval_mode="cache",
        state="WA",
        offline_cache={
            "state_statute|||WA": [
                {
                    "text": "California tenant text that is longer than the snippet.",
                    "snippet": "California tenant text",
                    "citation": "Cal. Civ. Code § 1940",
                    "state": "CA",
                    "uri": "https://leginfo.legislature.ca.gov/example",
                }
            ]
        },
    )
    assert keyed["status"] == "success"
    hit = keyed["results"][0]
    assert hit["jurisdiction"] == "CA"
    assert hit["jurisdiction_status"] == "mismatch"
    assert hit["applicability"] == "unknown"


def test_unavailable_empty_error_and_timeout_are_distinct(monkeypatch):
    calls = []

    async def _empty(parameters):
        calls.append(parameters)
        return {"status": "success", "results": []}

    async def _error(parameters):
        calls.append(parameters)
        raise RuntimeError("index backend failed")

    async def _slow(parameters):
        calls.append("slow")
        await asyncio.sleep(1)
        return {"status": "success", "results": [_row()]}

    _install(monkeypatch, "_search_us_code_corpus_async", _empty)
    empty = lookup_bounded_legal_corpus(
        source_family="us_code",
        query="venue",
        retrieval_mode="live",
        collection_name="legal_test",
        query_vector=_VECTOR,
        contains_private_facts=False,
        timeout_seconds=2,
    )
    assert empty["status"] == "empty"
    assert empty["results"] == []

    _install(monkeypatch, "_search_us_code_corpus_async", _error)
    failed = lookup_bounded_legal_corpus(
        source_family="us_code",
        query="venue",
        retrieval_mode="live",
        collection_name="legal_test",
        query_vector=_VECTOR,
        contains_private_facts=False,
        timeout_seconds=2,
    )
    assert failed["status"] == "error"
    assert failed["error_code"] == "backend_error"

    _install(monkeypatch, "_search_us_code_corpus_async", _slow)
    timed_out = lookup_bounded_legal_corpus(
        source_family="us_code",
        query="venue",
        retrieval_mode="live",
        collection_name="legal_test",
        query_vector=_VECTOR,
        contains_private_facts=False,
        timeout_seconds=0.05,
    )
    assert timed_out["status"] == "timeout"
    assert timed_out["error_code"] == "timeout"
    assert timed_out["results"] == []

    blocked = lookup_bounded_legal_corpus(
        source_family="us_code",
        query="private facts about a person",
        retrieval_mode="live",
        collection_name="legal_test",
        query_vector=_VECTOR,
        contains_private_facts=True,
        privacy_policy_accepted=False,
    )
    assert blocked["status"] == "unavailable"
    assert blocked["error_code"] == "privacy_policy_required"
    assert "slow" not in calls or calls[-1] != "private"

    missing_vector = lookup_bounded_legal_corpus(
        source_family="court_rule",
        query="answer",
        retrieval_mode="live",
        court_jurisdiction="both",
        contains_private_facts=False,
    )
    assert missing_vector["error_code"] == "query_vector_required"

    missing_state = lookup_bounded_legal_corpus(
        source_family="court_rule",
        query="answer",
        retrieval_mode="live",
        court_jurisdiction="state",
        collection_name="courts",
        query_vector=_VECTOR,
        contains_private_facts=False,
    )
    assert missing_state["error_code"] == "explicit_state_required"


def test_offline_us_code_missing_index_does_not_scrape(tmp_path, monkeypatch):
    scraped = []

    async def _scrape(parameters):
        scraped.append(parameters)
        return {"status": "success", "data": []}

    searched = []

    async def _search(**kwargs):
        searched.append(kwargs)
        return {"status": "success", "results": []}

    _install(monkeypatch, "_scrape_state_laws_async", _scrape)
    _install(monkeypatch, "_search_us_code_async", _search)
    missing = lookup_bounded_legal_corpus(
        source_family="us_code",
        query="venue",
        retrieval_mode="offline",
        index_path=str(tmp_path / "absent.jsonl"),
    )
    assert missing["status"] == "unavailable"
    assert missing["capability"] == "local_us_code_index_missing"
    assert missing["setup_invoked"] is False
    assert missing["network_used"] is False
    assert searched == []
    assert scraped == []

    index_path = tmp_path / "uscode.jsonl"
    index_path.write_text("{}\n", encoding="utf-8")

    async def _found(**kwargs):
        searched.append(kwargs)
        return {"status": "success", "results": [_row()]}

    _install(monkeypatch, "_search_us_code_async", _found)
    found = lookup_bounded_legal_corpus(
        source_family="us_code",
        query="color of statute",
        retrieval_mode="offline",
        index_path=str(index_path),
        max_results=1,
        timeout_seconds=2,
    )
    assert found["status"] == "success"
    assert found["network_used"] is False
    assert searched[0]["index_path"] == str(index_path)
    assert searched[0]["max_results"] == 1
    assert scraped == []


def test_result_count_is_bounded_and_direct_register_dates_are_publication_filters(monkeypatch):
    captured = []

    async def _many(parameters):
        captured.append(parameters)
        return {"status": "success", "results": [_row(citation=f"cite-{index}") for index in range(6)]}

    _install(monkeypatch, "_search_federal_register_corpus_async", _many)
    envelope = lookup_bounded_legal_corpus(
        source_family="federal_register",
        query="housing",
        retrieval_mode="live",
        collection_name="fr",
        query_vector=_VECTOR,
        max_results=2,
        contains_private_facts=False,
    )
    assert envelope["result_count"] == 2
    assert captured[0]["top_k"] == 2

    direct_calls = []

    async def _direct(**kwargs):
        direct_calls.append(kwargs)
        return {
            "status": "success",
            "documents": [
                {
                    "document_number": "2024-01001",
                    "html_url": "https://www.federalregister.gov/documents/2024/01/02/2024-01001",
                    "text": "This notice was published in the Federal Register and is not an effective-date determination.",
                    "snippet": "published in the Federal Register",
                    "publication_date": "2024-01-02",
                }
            ],
        }

    _install(monkeypatch, "_search_federal_register_async", _direct)
    direct = lookup_bounded_legal_corpus(
        source_family="federal_register",
        query="fair housing",
        retrieval_mode="live",
        live_backend="direct",
        start_date="2024-01-01",
        end_date="2024-01-31",
        contains_private_facts=False,
        max_results=3,
        timeout_seconds=2,
    )
    assert direct_calls[0]["fetch_all"] is False
    assert direct_calls[0]["max_pages"] == 1
    assert direct_calls[0]["keywords"] == "fair housing"
    assert direct_calls[0]["start_date"] == "2024-01-01"
    assert direct["date_filter_role"] == "publication"
    assert direct["date_filter_is_effective_date"] is False
    assert direct["results"][0]["effective_date"] is None
    assert direct["results"][0]["effective_date_status"] == "not_publication_date"
    assert direct["results"][0]["publication_date"] == "2024-01-02"


def test_running_loop_uses_owned_process_transport(monkeypatch):
    import integrations.ipfs_datasets.legal as legal
    captured = []
    async def present(_parameters):
        raise AssertionError('parent must not execute coroutine')
    monkeypatch.setattr(legal, '_search_us_code_corpus_async', present)
    def transport(api, parameters, timeout):
        captured.append((api, parameters, timeout))
        return 'ok', {'status': 'success', 'results': []}
    monkeypatch.setattr(legal, '_run_owned_deadline', transport)
    async def inside():
        return lookup_bounded_legal_corpus(source_family='us_code', query='venue',
            retrieval_mode='live', collection_name='synthetic', query_vector=_VECTOR,
            contains_private_facts=False)
    result = asyncio.run(inside())
    assert result['status'] == 'empty'
    assert captured[0][0] == 'us_code_corpus'


def test_authority_program_routes_explicit_case_requests_and_not_unknown_context():
    program = {
        "program_id": "legal_search_program:test",
        "program_type": "adverse_authority_search",
        "authority_intent": "oppose",
        "query_text": "retaliation adverse authority exception",
        "jurisdiction": "OR",
        "authority_families": ["case_law", "docket_material"],
    }
    with patch("integrations.ipfs_datasets.legal.search_recap_documents", return_value=[{"citation": "Example v. Agency", "type": "case_law"}]) as recap_search:
        with patch("integrations.ipfs_datasets.legal.search_us_code") as us_code_search:
            result = search_legal_authority_program(program, max_results=2)
    assert recap_search.call_count == 2
    us_code_search.assert_not_called()
    assert result["metadata"]["details"]["selected_rule_applicability"] == "unselected"
    assert result["results"]["case_law"][0]["citation"] == "Example v. Agency"

    unknown = {
        "query_text": "retaliation",
        "authority_families": ["case_law", "statute", "court_rule"],
    }
    with patch("integrations.ipfs_datasets.legal.search_recap_documents") as recap_search:
        with patch("integrations.ipfs_datasets.legal.search_us_code") as us_code_search:
            with patch("integrations.ipfs_datasets.legal.search_state_laws") as state_search:
                with patch("integrations.ipfs_datasets.legal.lookup_bounded_legal_corpus") as bounded:
                    negative = search_legal_authority_program(unknown, max_results=2)
    recap_search.assert_not_called()
    us_code_search.assert_not_called()
    state_search.assert_not_called()
    bounded.assert_not_called()
    assert negative["result_count"] == 0
    assert negative["metadata"]["details"]["jurisdiction"] == "unknown"
    assert negative["metadata"]["details"]["selected_rule_applicability"] == "unknown"


def test_mediator_hooks_do_not_add_oregon_defaults_or_stall():
    from mediator.legal_authority_hooks import LegalAuthoritySearchHook
    from mediator.legal_corpus_hooks import LegalCorpusRAGHook

    mediator = Mock()
    mediator.log = Mock()
    hook = LegalAuthoritySearchHook(mediator)
    hook._search_oregon_statutes_fallback = Mock(return_value=[{"citation": "ORS 1.1"}])
    with patch("mediator.legal_authority_hooks.lookup_bounded_legal_corpus", return_value={
        "status": "unavailable",
        "source_family": "state_statute",
        "retrieval_mode": "offline",
        "capability": "offline_asset_missing",
        "error_code": "offline_asset_missing",
        "results": [],
        "result_count": 0,
        "applicability": "unknown",
    }) as lookup:
        envelope = hook.lookup_bounded_corpus(
            source_family="state_statute",
            query="housing",
            retrieval_mode="offline",
        )
    lookup.assert_called_once()
    hook._search_oregon_statutes_fallback.assert_not_called()
    assert envelope["status"] == "unavailable"
    assert envelope["results"] == []

    rag = LegalCorpusRAGHook(mediator)
    with patch(
        "integrations.ipfs_datasets.legal.lookup_bounded_legal_corpus",
        side_effect=RuntimeError("optional backend down"),
    ):
        failed = rag.lookup_bounded_authority_candidates(
            source_family="court_rule",
            query="private medical detail",
            retrieval_mode="live",
            contains_private_facts=True,
        )
    assert failed["status"] == "error"
    assert failed["results"] == []
    assert failed["applicability"] == "unknown"
    logged = mediator.log.call_args_list[-1]
    assert logged.args[0] == "legal_corpus_bounded_lookup"
    assert "private medical detail" not in str(logged.kwargs)


def test_cache_mode_does_not_call_live_backends(monkeypatch):
    async def _forbidden(*_args, **_kwargs):
        raise AssertionError("live backend called during cache lookup")

    for symbol in (
        "_search_us_code_corpus_async",
        "_search_state_law_corpus_async",
        "_search_federal_register_corpus_async",
        "_search_court_rules_corpus_async",
        "_search_federal_register_async",
        "_search_us_code_async",
    ):
        _install(monkeypatch, symbol, _forbidden)
    envelope = lookup_bounded_legal_corpus(
        source_family="federal_register",
        query="notice",
        retrieval_mode="cache",
        offline_cache={
            "federal_register|notice||": [
                {
                    "text": "A cached Federal Register passage about notices.",
                    "snippet": "cached Federal Register passage",
                    "citation": "89 FR 100",
                    "uri": "https://www.federalregister.gov/documents/example",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        },
    )
    assert envelope["status"] == "success"
    assert envelope["network_used"] is False
    assert envelope["results"][0]["retrieved_at"] == "2026-01-01T00:00:00+00:00"
    assert envelope["results"][0]["corpus_id"] is None

@pytest.mark.parametrize('hook_kind', ['authority', 'corpus'])
def test_public_lookup_errors_do_not_echo_private_exception(monkeypatch, hook_kind):
    import integrations.ipfs_datasets.legal as legal
    from mediator.legal_authority_hooks import LegalAuthoritySearchHook
    from mediator.legal_corpus_hooks import LegalCorpusRAGHook
    marker = 'SYNTHETIC_PRIVATE_QUERY_OR_PATH'
    def failed(**kwargs):
        raise RuntimeError(marker)
    mediator = Mock()
    if hook_kind == 'authority':
        hook = LegalAuthoritySearchHook.__new__(LegalAuthoritySearchHook)
        hook.mediator = mediator
        monkeypatch.setattr('mediator.legal_authority_hooks.lookup_bounded_legal_corpus', failed)
        result = hook.lookup_bounded_corpus(source_family='us_code', query=marker, retrieval_mode='live')
    else:
        hook = LegalCorpusRAGHook.__new__(LegalCorpusRAGHook)
        hook.mediator = mediator
        monkeypatch.setattr(legal, 'lookup_bounded_legal_corpus', failed)
        result = hook.lookup_bounded_authority_candidates(source_family='us_code', query=marker, retrieval_mode='live')
    assert result['status'] == 'error' and result['results'] == []
    assert marker not in str(result)
    assert marker not in str(mediator.log.call_args_list)


@pytest.mark.parametrize('method,family,options', [
    ('search_us_code', 'us_code', {}),
    ('search_state_laws', 'state_statute', {'state': 'WA'}),
    ('search_federal_register', 'federal_register', {}),
    ('search_administrative_law', 'state_administrative_rule', {'state': 'WA'}),
])
def test_actual_default_hook_methods_use_bounded_offline_candidates(monkeypatch, method, family, options):
    from mediator.legal_authority_hooks import LegalAuthoritySearchHook
    hook = LegalAuthoritySearchHook.__new__(LegalAuthoritySearchHook)
    hook.mediator = Mock()
    row = _row(source_family=family, applicability='unknown', content_hash='sha256:synthetic')
    hook.lookup_bounded_corpus = Mock(return_value={'status':'success','results':[row]})
    for name in ('_generate_search_terms', '_search_oregon_statutes_fallback', '_search_federal_statutes_fallback', '_search_ecfr_fallback'):
        setattr(hook, name, Mock(side_effect=AssertionError('implicit legacy fallback')))
    assert getattr(hook, method)('synthetic query', max_results=2, **options) == [row]
    call = hook.lookup_bounded_corpus.call_args.kwargs
    assert call['source_family'] == family and call['retrieval_mode'] == 'offline'
    assert call['query'] == 'synthetic query' and call['max_results'] == 2
    assert row['applicability'] == 'unknown'


def test_actual_all_sources_requires_context_and_preserves_bounded_provenance():
    from mediator.legal_authority_hooks import LegalAuthoritySearchHook
    hook = LegalAuthoritySearchHook.__new__(LegalAuthoritySearchHook)
    hook.mediator = Mock()
    row = _row(source_family='state_statute', jurisdiction='WA', applicability='unknown')
    hook.lookup_bounded_corpus = Mock(return_value={'status':'success','results':[row], 'applicability':'unknown'})
    hook._search_oregon_statutes_fallback = Mock(side_effect=AssertionError('implicit OR fallback'))
    unknown = hook.search_all_sources('synthetic query', authority_families=['statute'])
    hook.lookup_bounded_corpus.assert_not_called()
    assert unknown['statutes'] == unknown['state_statutes'] == []
    result = hook.search_all_sources('synthetic query', jurisdiction='WA', authority_families=['statute'])
    assert result['statutes'] == [] and result['state_statutes'] == [row]
    assert hook.lookup_bounded_corpus.call_args.kwargs['state'] == 'WA'
    assert hook.lookup_bounded_corpus.call_args.kwargs['retrieval_mode'] == 'offline'
    hook._search_oregon_statutes_fallback.assert_not_called()


@pytest.mark.parametrize('family,jurisdiction,bucket,expected', [
    ('statute','federal','statutes','us_code'),
    ('statute','WA','state_statutes','state_statute'),
    ('regulation','federal','regulations','federal_register'),
    ('administrative_rule','WA','administrative_rules','state_administrative_rule'),
    ('court_rule','WA','court_rules','court_rule'),
])
def test_real_program_routes_each_declared_corpus_family_to_bounded_adapter(monkeypatch, family, jurisdiction, bucket, expected):
    import integrations.ipfs_datasets.legal as legal
    row = _row(source_family=expected, jurisdiction=jurisdiction, applicability='unknown')
    bounded = Mock(return_value={'status':'success','results':[row], 'applicability':'unknown'})
    monkeypatch.setattr(legal, 'lookup_bounded_legal_corpus', bounded)
    for name in ('search_us_code','search_state_laws','search_federal_register','search_state_administrative_rules'):
        monkeypatch.setattr(legal, name, Mock(side_effect=AssertionError('legacy corpus route')))
    result = legal.search_legal_authority_program({'query_text':'synthetic query','authority_families':[family],
        'jurisdiction':jurisdiction,'contains_private_facts':False})
    assert result['results'][bucket] == [row]
    assert any(c.kwargs['source_family'] == expected for c in bounded.call_args_list)
    assert all(c.kwargs['retrieval_mode'] == 'offline' for c in bounded.call_args_list)
    assert result['metadata']['details']['selected_rule_applicability'] == 'unselected'


def test_rag_actual_normalizer_retains_source_provenance():
    from mediator.legal_corpus_hooks import LegalCorpusRAGHook
    from mediator.integrations import IPFSDatasetsAdapter, IntegrationFeatureFlags
    hook = LegalCorpusRAGHook.__new__(LegalCorpusRAGHook)
    hook.integration_adapter = IPFSDatasetsAdapter(feature_flags=IntegrationFeatureFlags.from_env())
    row = _row(source_family='us_code', content_hash='sha256:synthetic', content_hash_scope='source_passage',
        source_passage='Synthetic complete source passage.', retrieved_at='2026-01-01T00:00:00Z',
        applicability='unknown', effective_date=None)
    normalized = hook._normalize_records([row], 'synthetic query', 'legal_corpus', 'synthetic')
    assert len(normalized) == 1
    output = normalized[0]
    assert output['url'] == row['uri'] and output['citation'] == row['citation']
    provenance = output['metadata']['corpus_provenance']
    for key in ('uri','citation','content_hash','content_hash_scope','corpus_id','corpus_version','cid',
                'retrieved_at','source_passage','jurisdiction','applicability','effective_date'):
        assert provenance[key] == row[key]


@pytest.mark.parametrize('options,code', [
    ({'timeout_seconds':float('nan')},'invalid_timeout'),
    ({'timeout_seconds':float('inf')},'invalid_timeout'),
    ({'max_results':[]},'invalid_result_limit'),
    ({'max_results':True},'invalid_result_limit'),
    ({'privacy_policy_accepted':'yes'},'invalid_privacy_policy'),
    ({'contains_private_facts':0},'invalid_privacy_policy'),
])
def test_malformed_limits_and_policy_refuse_before_transport(monkeypatch, options, code):
    import integrations.ipfs_datasets.legal as legal
    transport = Mock(side_effect=AssertionError('transport entered'))
    monkeypatch.setattr(legal, '_run_owned_deadline', transport)
    result = legal.lookup_bounded_legal_corpus(source_family='us_code', query='synthetic',
        retrieval_mode='live', collection_name='synthetic', query_vector=_VECTOR, **options)
    assert result['status'] == 'unavailable' and result['error_code'] == code
    transport.assert_not_called()

# Executed only by the real owned-worker test. The fake upstream package installs
# this before its API module is imported; the manager itself is fixed stdlib-only
# code. No inherited provider credentials, network access or arbitrary child.
PROCESS_FIXTURE_GUARD = r'''
import hashlib, json, os, pathlib, socket, subprocess, sys
fixture = pathlib.Path(__file__).resolve().parents[1]
assert fixture.name == 'legal-owned-process' and fixture.stat().st_uid == os.getuid()
assert fixture.stat().st_mode & 0o077 == 0
inner = "import os,time; time.sleep(30)"
original = subprocess.Popen
class GuardedPopen:
 @classmethod
 def __class_getitem__(cls, value): return cls
 def __new__(cls, command, *args, **kwargs):
  if list(command) != [sys.executable,'-I','-c',inner] or kwargs.get('shell'):
   raise PermissionError('synthetic_legal_process_denied')
  assert pathlib.Path.cwd().resolve() == fixture
  return original(command,*args,**kwargs)
subprocess.Popen = GuardedPopen
original_socket = socket.socket
class ClosedSocket(original_socket):
 def __init__(self, family=socket.AF_INET, *args, **kwargs):
  if family in (socket.AF_INET,socket.AF_INET6):raise PermissionError('synthetic_legal_network_denied')
  super().__init__(family,*args,**kwargs)
 def connect(self,*args,**kwargs):raise PermissionError('synthetic_legal_network_denied')
 def connect_ex(self,*args,**kwargs):raise PermissionError('synthetic_legal_network_denied')
 def sendto(self,*args,**kwargs):raise PermissionError('synthetic_legal_network_denied')
socket.socket=ClosedSocket
socket.create_connection=socket.getaddrinfo=lambda *a,**k:(_ for _ in ()).throw(PermissionError('synthetic_legal_network_denied'))
'''

PROCESS_FIXTURE_API = r'''
import json, os, pathlib, subprocess, sys
root=pathlib.Path.cwd()
async def search_us_code_corpus_from_parameters(parameters):
 assert all(key not in os.environ for key in ('XAI_API_KEY','GROK_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'))
 assert os.environ.get('IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD')=='0'
 (root/'worker.json').write_text(json.dumps({'pid':os.getpid(),'guard_active':subprocess.Popen.__name__=='GuardedPopen',
  'nltk_auto_download':os.environ['IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD']}))
 mode=parameters['collection_name']
 if mode=='inner-block':
  child=subprocess.Popen([sys.executable,'-I','-c',"import os,time; time.sleep(30)"],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  (root/'inner.json').write_text(json.dumps({'pid':child.pid}))
  child.wait()
 if mode=='private-error':raise RuntimeError('SYNTHETIC_PRIVATE_QUERY_OR_PATH')
 if mode=='oversize':return {'status':'success','results':[{'text':'a'*600000}]}
 return {'status':'success','results':[{'citation':'Synthetic Act 1','uri':'https://example.invalid/synthetic-act',
  'text':'Synthetic public legal source passage.','jurisdiction':'federal','corpus_id':'synthetic-corpus'}]}
'''


@pytest.mark.parametrize('mode,expected', [
    ('success','success'),('inner-block','timeout'),('private-error','error'),('oversize','error'),
])
def test_real_owned_deadline_reaps_blocking_upstream_inner_child(tmp_path, monkeypatch, mode, expected):
    import json
    import os
    import time
    from pathlib import Path
    import integrations.ipfs_datasets.legal as legal
    assert os.name == 'posix' and Path('/proc/self/task').is_dir()
    root=tmp_path/'legal-owned-process'
    root.mkdir(mode=0o700)
    for directory in ('home','temporary','ipfs_datasets_py','ipfs_datasets_py/processors',
                      'ipfs_datasets_py/processors/legal_scrapers'):
        (root/directory).mkdir(mode=0o700,parents=True,exist_ok=True)
    (root/'ipfs_datasets_py/__init__.py').write_text(PROCESS_FIXTURE_GUARD)
    (root/'ipfs_datasets_py/processors/__init__.py').write_text('')
    (root/'ipfs_datasets_py/processors/legal_scrapers/__init__.py').write_text('')
    (root/'ipfs_datasets_py/processors/legal_scrapers/legal_dataset_api.py').write_text(PROCESS_FIXTURE_API)
    for file in root.rglob('*.py'):file.chmod(0o600)
    before={str(file.relative_to(root)):file.read_bytes() for file in root.rglob('*.py')}
    monkeypatch.chdir(root)
    monkeypatch.setenv('HOME',str(root/'home'))
    monkeypatch.setenv('TMPDIR',str(root/'temporary'))
    monkeypatch.setenv('XAI_API_KEY','SYNTHETIC_UNFORWARDED_SECRET')
    monkeypatch.setattr(legal,'_owned_corpus_roots',lambda:[str(root)])
    async def parent_must_not_call(_parameters):
        raise AssertionError('parent called upstream function')
    monkeypatch.setattr(legal,'_search_us_code_corpus_async',parent_must_not_call)
    started=time.monotonic()
    result=legal.lookup_bounded_legal_corpus(source_family='us_code',query='synthetic public token',
        retrieval_mode='live',collection_name=mode,query_vector=_VECTOR,contains_private_facts=False,
        timeout_seconds=.6)
    elapsed=time.monotonic()-started
    assert result['status']==expected and elapsed < 3
    assert result['bounded'] is True and result['setup_invoked'] is False
    assert 'SYNTHETIC_PRIVATE_QUERY_OR_PATH' not in str(result)
    assert 'SYNTHETIC_UNFORWARDED_SECRET' not in str(result)
    worker=json.loads((root/'worker.json').read_text())
    assert worker['guard_active'] is True
    assert worker['nltk_auto_download']=='0'
    assert not Path('/proc',str(worker['pid'])).exists()
    if mode=='inner-block':
        inner=json.loads((root/'inner.json').read_text())
        assert not Path('/proc',str(inner['pid'])).exists()
        assert result['error_code']=='timeout' and result['results']==[]
    if mode=='success':
        assert result['results'][0]['corpus_id']=='synthetic-corpus'
        assert result['results'][0]['applicability']=='unknown'
    assert {str(file.relative_to(root)):file.read_bytes() for file in root.rglob('*.py')}==before


def test_owned_worker_cold_package_resolution_uses_firstparty_registry(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    import integrations.ipfs_datasets.legal as legal
    import integrations.ipfs_datasets.loader as loader
    root=tmp_path/'checked-out-datasets'
    (root/'ipfs_datasets_py').mkdir(parents=True)
    (root/'ipfs_datasets_py/__init__.py').write_text('# inert checked-out synthetic source\n')
    monkeypatch.setattr(loader,'get_repo_paths',lambda:SimpleNamespace(ipfs_datasets_repo=root,
        ipfs_accelerate_repo=tmp_path/'missing-native',ipfs_kit_repo=None))
    monkeypatch.delitem(sys.modules,'ipfs_datasets_py',raising=False)
    roots=legal._owned_corpus_roots()
    assert roots[0]==str(root)
    assert 'ipfs_datasets_py' not in sys.modules
    monkeypatch.setattr(loader,'get_repo_paths',lambda:SimpleNamespace(ipfs_datasets_repo=tmp_path/'missing',
        ipfs_accelerate_repo=tmp_path/'missing-native',ipfs_kit_repo=None))
    assert legal._owned_corpus_roots()==[]


@pytest.mark.parametrize('returncode,output', [
    (1,b''),(0,b'not JSON'),(0,b'{}'),(0,b'{"outcome":"ok","payload":{}}'),
    (0,b'{"outcome":"ok","cleanup_confirmed":false}'),(0,b'x'*600001),
], ids=['nonzero','malformed','missing','missing-cleanup','false-cleanup','oversize'])
def test_abnormal_manager_ack_never_claims_bounded_cleanup(monkeypatch, returncode, output):
    import integrations.ipfs_datasets.legal as legal
    class BrokenManager:
        def __init__(self,*args,**kwargs):self.returncode=returncode
        def communicate(self,*args,**kwargs):return output,None
        def poll(self):return self.returncode
    monkeypatch.setattr('subprocess.Popen',BrokenManager)
    monkeypatch.setattr(legal,'_owned_corpus_roots',lambda:['/synthetic-checked-out-source'])
    async def available(_parameters):raise AssertionError('parent executed upstream')
    monkeypatch.setattr(legal,'_search_us_code_corpus_async',available)
    result=legal.lookup_bounded_legal_corpus(source_family='us_code',query='synthetic',retrieval_mode='live',
        collection_name='synthetic',query_vector=_VECTOR,contains_private_facts=False)
    assert result['status']=='unavailable' and result['error_code']=='cleanup_unconfirmed'
    assert result['bounded'] is False and result['results']==[]


def test_backend_errors_are_sanitized_and_partial_success_is_retained(monkeypatch):
    import integrations.ipfs_datasets.legal as legal
    async def available(_parameters):raise AssertionError('parent executed upstream')
    monkeypatch.setattr(legal,'_search_us_code_corpus_async',available)
    monkeypatch.setattr(legal,'_run_owned_deadline',lambda *args:('ok',{'status':'error','error':'SYNTHETIC_PRIVATE_QUERY_OR_PATH'}))
    failed=legal.lookup_bounded_legal_corpus(source_family='us_code',query='synthetic',retrieval_mode='live',
        collection_name='synthetic',query_vector=_VECTOR,contains_private_facts=False)
    assert failed['status']=='error' and 'SYNTHETIC_PRIVATE_QUERY_OR_PATH' not in str(failed)
    monkeypatch.setattr(legal,'_run_owned_deadline',lambda *args:('ok',{'status':'partial_success','results':[_row()]}))
    partial=legal.lookup_bounded_legal_corpus(source_family='us_code',query='synthetic',retrieval_mode='live',
        collection_name='synthetic',query_vector=_VECTOR,contains_private_facts=False)
    assert partial['status']=='partial_success' and partial['result_count']==1
    assert partial['results'][0]['effective_date'] is None
    assert partial['results'][0]['applicability']=='unknown'
    assert partial['network_used'] is None


def test_actual_mediator_default_path_keeps_typed_unavailable_diagnostics():
    from types import SimpleNamespace
    from mediator.mediator import Mediator
    from mediator.legal_authority_hooks import LegalAuthoritySearchHook
    hook=LegalAuthoritySearchHook.__new__(LegalAuthoritySearchHook)
    hook.mediator=Mock()
    hook.lookup_bounded_corpus=Mock(return_value={'status':'unavailable','capability':'offline_asset_missing',
        'error_code':'offline_asset_missing','retrieval_mode':'offline','results':[],'applicability':'unknown'})
    host=SimpleNamespace(legal_authority_search=hook)
    result=Mediator.search_legal_authorities(host,'SYNTHETIC_PRIVATE_QUERY',jurisdiction='WA')
    assert hook.lookup_bounded_corpus.call_count==3
    assert result['statutes']==result['state_statutes']==result['administrative_rules']==[]
    for family in ('statutes','state_statutes','administrative_rules'):
        assert result['search_diagnostics'][family]['status']=='unavailable'
        assert result['search_diagnostics'][family]['error_code']=='offline_asset_missing'
    assert len(result['search_warning_summary'])==3
    assert 'SYNTHETIC_PRIVATE_QUERY' not in str(result['search_diagnostics'])
    assert 'SYNTHETIC_PRIVATE_QUERY' not in str(result['search_warning_summary'])
    assert 'SYNTHETIC_PRIVATE_QUERY' not in str(hook.mediator.log.call_args_list)


@pytest.mark.parametrize('with_assertion', [False, True])
def test_treatment_edge_roundtrips_complete_provenance_without_asserting_user_fact(with_assertion):
    import copy
    import hashlib
    from integrations.ipfs_datasets.types import ProvenanceRecord, build_user_assertion_envelope
    from mediator.legal_authority_hooks import LegalAuthorityStorageHook

    passage = 'Synthetic § authority passage; no user allegation is established.'
    assertion = build_user_assertion_envelope(
        source_text=passage, source_kind='legal_text', source_id='synthetic-authority',
        source_span={'start': 0, 'end': len(passage.encode('utf-8')), 'text': passage},
        record_type='legal_text', extractor_version='synthetic-law02',
    ).as_dict() if with_assertion else {}
    provenance = ProvenanceRecord(
        source_url='https://example.invalid/synthetic-authority', acquisition_method='offline_fixture',
        source_type='case_law', acquired_at='2026-10-21T00:00:00+00:00',
        content_hash=hashlib.sha256(passage.encode('utf-8')).hexdigest(),
        source_system='synthetic-corpus', jurisdiction='OR',
        metadata={'corpus_id': 'synthetic-laws', 'corpus_version': 'v1',
                  'source_passage': passage, 'effective_date': None, 'nested': {'source_verified': False}},
        assertion=assertion,
    ).as_dict()
    records = [{'treatment_id': 'synthetic-treatment', 'treatment_type': 'questioned',
        'treated_by_authority_id': 'synthetic-later-authority', 'treated_by_citation': 'Synthetic Later 2',
        'treatment_source': 'offline_fixture', 'treatment_confidence': 0.7, 'provenance': provenance}]
    original = copy.deepcopy(records)
    hook = LegalAuthorityStorageHook.__new__(LegalAuthorityStorageHook)
    edges = hook._build_authority_treatment_edges(
        {'id': 1, 'authority_id': 'synthetic-authority', 'citation': 'Synthetic Authority 1'}, records)

    assert len(edges) == 1 and edges[0]['relation_type'] == 'questioned'
    assert edges[0]['provenance'] == provenance
    assert records == original
    restored = ProvenanceRecord(**edges[0]['provenance'])
    assert restored.assertion == assertion
    assert restored.assertion_envelope().is_asserted_user_fact is False
    if with_assertion:
        assert restored.assertion['record_type'] == 'legal_text'
        assert restored.assertion['assertion_status'] == 'legal_text'


def test_cold_legal_import_disables_nltk_bootstrap_before_optional_imports(monkeypatch):
    import builtins
    import importlib.util
    import os
    import sys
    from integrations.ipfs_datasets import legal

    name = 'integrations.ipfs_datasets._law02_cold_policy_probe'
    spec = importlib.util.spec_from_file_location(name, legal.__file__)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv('IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD', '1')
    original_import = builtins.__import__
    observed = []

    def observe_optional_import(module_name, globals=None, locals=None, fromlist=(), level=0):
        if globals and globals.get('__name__') == name and level == 1:
            value = os.environ.get('IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD')
            observed.append((module_name, value))
            assert value == '0'
        return original_import(module_name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', observe_optional_import)
    spec.loader.exec_module(module)
    assert {'loader', 'types', 'vector_store'} <= {item[0] for item in observed}
    assert all(value == '0' for _, value in observed)
    assert os.environ['IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD'] == '0'
    assert callable(module.lookup_bounded_legal_corpus)


# LAW03: retrieval relevance is not entailment or applicability.

_LAW03_PASSAGE = (
    "Every person who, under color of any statute, subjects another to the deprivation of rights."
)
_LAW03_CONTEXT = {
    "jurisdiction": "federal",
    "applicable_law_date": "2024-06-01",
    "court": "U.S. District Court for the District of Oregon",
    "corpus_version": "prelim",
}


def _law03_hit(**overrides):
    payload = {
        "citation": "42 U.S.C. § 1983",
        "uri": "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title42-section1983",
        "text": _LAW03_PASSAGE,
        "source_passage": _LAW03_PASSAGE,
        "jurisdiction": "federal",
        "corpus_version": "prelim",
        "effective_date": "1871-04-20",
        "court": "U.S. District Court for the District of Oregon",
        "cid": "bafyuscode1983",
        "corpus_id": "justicedao/ipfs_uscode",
    }
    payload.update(overrides)
    return payload


def _law03_search(monkeypatch, hits=None, exc=None):
    import integrations.ipfs_datasets.legal as legal

    calls = []

    def bounded(**kwargs):
        family = kwargs["source_family"]
        calls.append((family, kwargs["query"]))
        if exc is not None:
            raise exc
        rows = list(hits or []) if family == legal.CORPUS_FAMILY_US_CODE else []
        return {"status": "success" if rows else "empty", "results": rows, "bounded": True}

    monkeypatch.setattr(legal, "lookup_bounded_legal_corpus", bounded)
    return calls


def _law03_result(monkeypatch, text, hits=None, exc=None, **kwargs):
    from integrations.ipfs_datasets.legal import constrain_assertions_to_corpus

    _law03_search(monkeypatch, hits=hits, exc=exc)
    assertion = {"assertion_id": "a-1", "text": text}
    extra = kwargs.pop("assertion", {})
    assertion.update(extra)
    graph = kwargs.pop("factual_graph", None)
    if graph is not None:
        assertion["factual_graph"] = graph
    return constrain_assertions_to_corpus(
        [assertion],
        legal_context=kwargs.pop("legal_context", _LAW03_CONTEXT),
        legal_vector_index_dir=kwargs.pop("legal_vector_index_dir", None),
        **kwargs,
    )


def test_mapped_source_is_candidate_verified_and_applicable_but_not_entailed(monkeypatch):
    result = _law03_result(
        monkeypatch,
        "42 U.S.C. § 1983 supplies a civil action.",
        hits=[_law03_hit()],
    )
    detail = result["details"][0]
    assert detail["retrieved_candidate"] is True
    assert detail["source_verified"] is True
    assert detail["applicable"] is True
    assert detail["entails"] is False
    assert detail["dispositions"]["entailment"] == "unsupported"
    assert detail["grounded"] is False
    assert result["grounded_count"] == 0
    assert result["candidate_count"] == 1
    assert result["source_verified_count"] == 1
    assert result["applicable_count"] == 1
    assert result["entailed_count"] == 0
    assert result["corpus_coverage_semantics"] == "retrieval_only"
    assert result["corpus_coverage_percent"] == 100
    assert result["entailment_prover"] == "unsupported"
    assert result["compatibility"]["grounded_semantics"]
    assert detail["no_applicable_law"] is False
    assert detail["allegation_false"] is False


def test_unrelated_high_score_hit_does_not_ground_or_verify_a_fact(monkeypatch):
    graph = {"nodes": [{"id": "fact-1", "status": "alleged"}]}
    snapshot = {"nodes": [{"id": "fact-1", "status": "alleged"}]}
    result = _law03_result(
        monkeypatch,
        "The officer arrested the plaintiff on May 1.",
        hits=[_law03_hit(score=0.99, citation="16 U.S.C. § 1538", text="It is unlawful to take an endangered species.", source_passage="It is unlawful to take an endangered species.")],
        assertion={"assertion_kind": "factual_allegation", "grounded": True, "entailed": True, "fact_verified": True},
        factual_graph=graph,
    )
    detail = result["details"][0]
    assert detail["retrieved_candidate"] is True
    assert detail["source_verified"] is False or detail["applicable"] is False
    assert detail["applicable"] is False
    assert detail["entails"] is False
    assert detail["grounded"] is False
    assert detail["fact_verified"] is False
    assert detail["allegation_status"] == "unknown"
    assert detail["allegation_false"] is False
    assert detail["no_applicable_law"] is False
    assert "grounded" in detail["ignored_caller_labels"]
    assert "entailed" in detail["ignored_caller_labels"]
    assert graph == snapshot
    assert result["fact_graph_mutated"] is False
    assert result["ungrounded"][0]["fact_verified"] is False


def test_official_url_without_passage_is_only_a_candidate(monkeypatch):
    result = _law03_result(
        monkeypatch,
        "42 U.S.C. § 1983 supplies a civil action.",
        hits=[{
            "citation": "42 U.S.C. § 1983",
            "uri": "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title42-section1983",
            "jurisdiction": "federal",
            "corpus_version": "prelim",
            "score": 0.91,
        }],
    )
    detail = result["details"][0]
    hit = detail["corpus_hits"][0]
    assert detail["retrieved_candidate"] is True
    assert detail["source_verified"] is False
    assert "absent_source_passage" in hit["disposition_reasons"]
    assert detail["applicable"] is False
    assert detail["entails"] is False
    assert detail["grounded"] is False


def test_same_citation_with_wrong_hash_version_jurisdiction_or_date_is_not_applicable(monkeypatch):
    text = "42 U.S.C. § 1983 supplies a civil action."
    wrong_hash = _law03_result(
        monkeypatch,
        text,
        hits=[_law03_hit(content_hash="sha256:not-the-passage")],
    )
    assert wrong_hash["details"][0]["source_verified"] is False
    assert "content_hash_mismatch" in wrong_hash["details"][0]["corpus_hits"][0]["disposition_reasons"]
    assert wrong_hash["details"][0]["grounded"] is False

    wrong_version = _law03_result(
        monkeypatch,
        text,
        hits=[_law03_hit(corpus_version="enacted-1871-reprint")],
    )
    assert wrong_version["details"][0]["dispositions"]["applicability"] == "not_applicable"
    assert "version_mismatch" in wrong_version["details"][0]["corpus_hits"][0]["disposition_reasons"]

    wrong_jurisdiction = _law03_result(
        monkeypatch,
        text,
        hits=[_law03_hit(jurisdiction="OR")],
    )
    assert wrong_jurisdiction["details"][0]["dispositions"]["applicability"] == "not_applicable"
    assert wrong_jurisdiction["details"][0]["applicable_law_conclusion"] == "unknown"
    assert wrong_jurisdiction["details"][0]["no_applicable_law"] is False

    wrong_date = _law03_result(
        monkeypatch,
        text,
        hits=[_law03_hit(effective_date="2025-01-01")],
    )
    assert "effective_after_applicable_date" in wrong_date["details"][0]["corpus_hits"][0]["disposition_reasons"]
    assert wrong_date["details"][0]["entails"] is False


def test_empty_success_is_distinct_from_backend_failure_and_timeout(monkeypatch):
    empty = _law03_result(monkeypatch, "42 U.S.C. § 1983 supplies a civil action.", hits=[])
    empty_detail = empty["details"][0]
    assert empty_detail["dispositions"]["retrieval"] == "empty"
    assert empty_detail["reason"] == "empty_success"
    assert empty_detail["retrieved_candidate"] is False
    assert empty_detail["dispositions"]["applicability"] == "unknown"
    assert empty_detail["dispositions"]["entailment"] == "unsupported"
    assert empty_detail["no_applicable_law"] is False
    assert empty_detail["allegation_false"] is False
    assert empty["corpus_coverage_percent"] == 0
    assert empty["corpus_coverage_semantics"] == "retrieval_only"

    failed = _law03_result(
        monkeypatch,
        "42 U.S.C. § 1983 supplies a civil action.",
        exc=RuntimeError("secret backend detail"),
    )
    failed_detail = failed["details"][0]
    assert failed_detail["dispositions"]["retrieval"] == "backend_error"
    assert failed_detail["reason"] == "backend_error"
    assert "secret" not in str(failed_detail["diagnostics"])
    assert failed_detail["applicable_law_conclusion"] == "unknown"
    assert failed_detail["allegation_false"] is False

    timed_out = _law03_result(
        monkeypatch,
        "42 U.S.C. § 1983 supplies a civil action.",
        exc=TimeoutError("timed out internally"),
    )
    assert timed_out["details"][0]["dispositions"]["retrieval"] == "timeout"
    assert timed_out["details"][0]["reason"] == "timeout"
    assert timed_out["details"][0]["dispositions"]["source_verification"] == "unknown"
    assert timed_out["details"][0]["entails"] is False


def test_unknown_jurisdiction_does_not_search_or_imply_no_law(monkeypatch):
    calls = _law03_search(monkeypatch, hits=[_law03_hit()])
    from integrations.ipfs_datasets.legal import constrain_assertions_to_corpus

    result = constrain_assertions_to_corpus(
        [{"assertion_id": "a-1", "text": "42 U.S.C. § 1983 supplies a civil action."}],
        legal_context={"applicable_law_date": "2024-06-01", "court": "U.S. District Court for the District of Oregon"},
    )
    assert calls == []
    detail = result["details"][0]
    assert detail == {
        "assertion_id": "a-1",
        "text": "42 U.S.C. § 1983 supplies a civil action.",
        "grounded": False,
        "applicability": "unknown",
        "reason": "unresolved_legal_context",
        "corpus_hits": [],
    }
    assert result["grounded_count"] == 0
    assert result["context_status"] == "unknown"
    assert result["entailment_prover"] == "unsupported"
    assert result["ungrounded"][0]["grounded"] is False
    assert result["ungrounded"][0]["applicability"] == "unknown"


def test_similarity_edge_is_not_upgraded_to_legal_authority(monkeypatch):
    import integrations.ipfs_datasets.legal as legal

    text = "42 U.S.C. § 1983 supplies a civil action."
    cache = {legal._cache_key('us_code', text, 'federal', ''):
             [_law03_hit(score=0.98, source="vector_index", edge_class="similarity")]}
    result = legal.constrain_assertions_to_corpus(
        [{"assertion_id": "a-1", "text": text}],
        legal_context=_LAW03_CONTEXT, retrieval_mode='cache', offline_cache=cache,
    )
    hit = result["details"][0]["corpus_hits"][0]
    assert hit["authority_label"] == "similarity_not_legal_authority"
    assert hit["similarity_cannot_establish_legal_authority"] is True
    assert hit["source_verified"] is False
    assert result["details"][0]["applicable"] is False
    assert result["details"][0]["grounded"] is False
    assert result["details"][0]["entails"] is False


def test_injected_proof_route_stays_unsupported(monkeypatch):
    result = _law03_result(
        monkeypatch,
        "42 U.S.C. § 1983 supplies a civil action.",
        hits=[_law03_hit(entailed=True, grounded=True, proof={"status": "proved"})],
        assertion={"entails": True, "proof_status": "entailed", "model_label": "entailed"},
    )
    detail = result["details"][0]
    assert detail["dispositions"]["entailment"] == "unsupported"
    assert detail["entails"] is False
    assert detail["entailment_reason"] == "no_bound_entailment_prover"
    assert result["entailed_count"] == 0
    assert detail["grounded"] is False


def test_rule_metadata_labels_are_extraction_provenance_not_entailment():
    from mediator.legal_authority_hooks import LegalAuthorityStorageHook

    hook = LegalAuthorityStorageHook.__new__(LegalAuthorityStorageHook)
    metadata = hook._build_grounded_rule_metadata(
        "The agency must provide notice within 30 days.",
        "procedural_prerequisite",
        authority_id=1,
        authority={"citation": "Synthetic Rule 1", "title": "Notice", "type": "rule", "source": "fixture", "metadata": {}},
        claim_element={"claim_element_id": "e-1", "claim_element": "notice"},
        provenance=type("P", (), {"jurisdiction": "federal"})(),
    )
    assert metadata["grounding_status"] == "grounded"
    assert metadata["grounding_status_semantics"] == "extraction_provenance_not_entailment"
    assert metadata["entailment_status"] == "unsupported"
    assert metadata["logical_entailment"] is False
    assert metadata["deontic_operator_source"] == "keyword_heuristic"
    assert metadata["deontic_operator_is_proof"] is False
    assert metadata["adverse_treatment_analysis"] == "incomplete_heuristic"


@pytest.mark.parametrize('expiry_field', ['sunset_date', 'repealed_date', 'effective_end'])
def test_sourced_expiry_survives_bounded_cache_before_applicability(expiry_field):
    import integrations.ipfs_datasets.legal as legal
    text = '42 U.S.C. § 1983 supplies a civil action.'
    hit = _law03_hit(**{expiry_field: '2020-12-31'})
    cache = {legal._cache_key('us_code', text, 'federal', ''): [hit]}
    result = legal.constrain_assertions_to_corpus(
        [{'text': text}], legal_context=_LAW03_CONTEXT,
        retrieval_mode='cache', offline_cache=cache,
    )
    detail = result['details'][0]
    source = detail['corpus_hits'][0]
    assert source[expiry_field] == '2020-12-31'
    assert source['source_verified'] is True
    assert source['applicability'] == 'not_applicable'
    assert 'version_expired' in source['disposition_reasons']
    assert detail['applicable'] is False
    assert detail['grounded'] is False
    assert detail['fact_verified'] is False
    assert detail['no_applicable_law'] is False


@pytest.mark.parametrize('invalid', ['expiry', 'hash', 'similarity'])
def test_bounded_normalization_cannot_launder_source_refusals(invalid):
    import integrations.ipfs_datasets.legal as legal
    text = '42 U.S.C. § 1983 supplies a civil action.'
    changes = {'expiry': {'sunset_date': ['2020-12-31']},
               'hash': {'content_hash': 'sha256:wrong'},
               'similarity': {'edge_class': 'similarity'}}[invalid]
    cache = {legal._cache_key('us_code', text, 'federal', ''): [_law03_hit(**changes)]}
    result = legal.constrain_assertions_to_corpus(
        [{'text': text, 'entailed': True, 'fact_verified': True}],
        legal_context=_LAW03_CONTEXT, retrieval_mode='cache', offline_cache=cache,
    )
    detail = result['details'][0]
    assert detail['retrieved_candidate'] is True
    assert detail['source_verified'] is False
    assert detail['applicable'] is False
    assert detail['grounded'] is False
    assert detail['fact_verified'] is False
    assert detail['entails'] is False
    if invalid == 'hash':
        assert detail['corpus_hits'][0]['content_hash_mismatch'] is True
    if invalid == 'similarity':
        assert detail['corpus_hits'][0]['similarity_cannot_establish_legal_authority'] is True


@pytest.mark.parametrize('outcome, expected', [('absent', 'unavailable'), ('error', 'backend_error'), ('timeout', 'timeout')])
def test_actual_bounded_constraint_path_retains_backend_failure_diagnostics(tmp_path, monkeypatch, outcome, expected):
    import integrations.ipfs_datasets.legal as legal
    index = tmp_path / 'synthetic-us-code.jsonl'
    index.write_text('')
    def legacy_forbidden(*args, **kwargs):
        raise AssertionError('Unbounded legacy lookup must not run')
    for name in ('search_us_code', 'search_federal_register', 'search_state_laws'):
        monkeypatch.setattr(legal, name, legacy_forbidden)
    monkeypatch.setattr(legal, '_search_us_code_async', None if outcome == 'absent' else object())
    transports = []
    def transport(backend, parameters, timeout):
        transports.append((backend, timeout))
        return outcome, None
    monkeypatch.setattr(legal, '_run_owned_deadline', transport)
    result = legal.constrain_assertions_to_corpus(
        [{'text': '42 U.S.C. § 1983 applies.'}], legal_context=_LAW03_CONTEXT,
        index_path=str(index), timeout_seconds=.5,
    )
    detail = result['details'][0]
    assert detail['diagnostics'][0]['backend'] == 'us_code'
    assert detail['diagnostics'][0]['status'] == expected
    assert detail['dispositions']['source_verification'] == 'unknown'
    assert detail['dispositions']['applicability'] == 'unknown'
    assert detail['retrieved_candidate'] is False
    assert detail['grounded'] is False
    assert detail['fact_verified'] is False
    assert detail['allegation_false'] is False
    assert detail['no_applicable_law'] is False
    assert transports == ([] if outcome == 'absent' else [('local_us_code_index', .5)])


def test_actual_bounded_empty_success_is_not_backend_unavailability(monkeypatch):
    import integrations.ipfs_datasets.legal as legal
    def forbidden(*args, **kwargs):
        raise AssertionError('An explicit empty cache requires no backend')
    monkeypatch.setattr(legal, '_run_owned_deadline', forbidden)
    result = legal.constrain_assertions_to_corpus(
        [{'text': '42 U.S.C. § 1983 applies.'}], legal_context=_LAW03_CONTEXT,
        retrieval_mode='cache', offline_cache={},
    )
    detail = result['details'][0]
    assert detail['dispositions']['retrieval'] == 'empty'
    assert detail['reason'] == 'empty_success'
    assert all(row['status'] == 'ok' and row['result_count'] == 0 for row in detail['diagnostics'])
    assert detail['dispositions']['source_verification'] == 'unknown'
    assert detail['dispositions']['applicability'] == 'unknown'
    assert detail['grounded'] is False
    assert detail['no_applicable_law'] is False
    assert detail['allegation_false'] is False


@pytest.mark.parametrize('boundary', ['effective_date', 'sunset_date'])
def test_applicable_date_range_crossing_sourced_version_boundary_stays_unknown(boundary):
    import integrations.ipfs_datasets.legal as legal
    text = '42 U.S.C. § 1983 supplies a civil action.'
    context = {**_LAW03_CONTEXT, 'applicable_law_date': '2020'}
    cache = {legal._cache_key('us_code', text, 'federal', ''): [_law03_hit(**{boundary: '2020-06-01'})]}
    result = legal.constrain_assertions_to_corpus(
        [{'text': text}], legal_context=context, retrieval_mode='cache', offline_cache=cache,
    )
    detail = result['details'][0]
    assert 'date_range_crosses_rule_version' in detail['corpus_hits'][0]['disposition_reasons']
    assert detail['dispositions']['applicability'] == 'unknown'
    assert detail['applicable'] is False
    assert detail['grounded'] is False
    assert detail['no_applicable_law'] is False


@pytest.mark.parametrize('index_source', ['argument', 'environment'])
def test_legacy_semantic_index_cannot_authorize_ambient_embedding(monkeypatch, index_source):
    import integrations.ipfs_datasets.legal as legal
    from integrations.ipfs_datasets import vector_store
    calls = []
    def forbidden(*args, **kwargs):
        calls.append('unowned_embedding_route')
        raise AssertionError('No index read or ambient embedding is authorized')
    monkeypatch.setattr(legal, '_search_legal_vector_index', forbidden)
    monkeypatch.setattr(vector_store, 'search_vector_index', forbidden)
    monkeypatch.delenv('COMPLAINT_LEGAL_VECTOR_INDEX_DIR', raising=False)
    arguments = {'legal_vector_index_dir': '/synthetic/private-index'}
    if index_source == 'environment':
        monkeypatch.setenv('COMPLAINT_LEGAL_VECTOR_INDEX_DIR', '/synthetic/private-index')
        arguments = {}
    text = 'SYNTHETIC_PRIVATE_ASSERTION with 42 U.S.C. § 1983'
    result = legal.constrain_assertions_to_corpus(
        [{'text': text}], legal_context=_LAW03_CONTEXT,
        retrieval_mode='cache', offline_cache={}, **arguments,
    )
    detail = result['details'][0]
    assert calls == []
    assert detail['retrieved_candidate'] is False
    assert result['candidate_count'] == 0
    assert detail['dispositions']['retrieval'] == 'unavailable'
    assert detail['source_verified'] is False
    assert detail['applicable'] is False
    assert detail['entails'] is False
    assert detail['fact_verified'] is False
    assert detail['no_applicable_law'] is False
    assert any(row['backend'] == 'legal_vector_index'
               and row['error_code'] == 'owned_vector_lookup_unavailable'
               for row in detail['diagnostics'])
    assert text not in str(detail['diagnostics'])


@pytest.mark.parametrize('jurisdiction', ['unknown', 'federal'])
def test_caller_proof_labels_cannot_survive_as_verified_output(jurisdiction):
    import copy
    import integrations.ipfs_datasets.legal as legal
    labels = ('grounded', 'entailed', 'entails', 'source_verified',
              'applicable', 'fact_verified', 'verified', 'legal_grounding')
    assertion = {'text': 'Synthetic factual allegation.', **{label: True for label in labels}}
    before = copy.deepcopy(assertion)
    result = legal.constrain_assertions_to_corpus(
        [assertion], legal_context={**_LAW03_CONTEXT, 'jurisdiction': jurisdiction},
        retrieval_mode='cache', offline_cache={},
    )
    carried = result['ungrounded'][0]
    assert assertion == before
    assert all(carried[label] is False for label in labels)
    assert carried['applicability'] == 'unknown'
    assert result['grounded_count'] == 0
    assert result['entailed_count'] == 0
    assert result['source_verified_count'] == 0
