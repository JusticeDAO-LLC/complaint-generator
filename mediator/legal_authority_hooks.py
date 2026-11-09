"""Legal authority retrieval hooks for mediator."""

import os
import hashlib
import json
import re
from contextlib import closing
from html import unescape
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

import requests

from integrations.ipfs_datasets.provenance import (
    build_document_parse_contract,
    build_fact_lineage_metadata,
    build_provenance,
    enrich_document_parse,
)
from integrations.ipfs_datasets.documents import detect_document_input_format, parse_document
from integrations.ipfs_datasets.graphs import extract_graph_from_text, persist_graph_snapshot
from integrations.ipfs_datasets.types import (
    AuthorityTreatmentEdge,
    AuthorityTreatmentRecord,
    CaseAuthority,
    CaseFact,
    LegalSearchProgram,
    ProvenanceRecord,
    RuleCandidate,
)
from mediator.evidence_hooks import PrivateDerivedIndexMixin
from integrations.ipfs_datasets.legal import (
    LEGAL_SCRAPERS_AVAILABLE,
    LEGAL_SOURCE_AVAILABILITY,
    get_last_legal_search_diagnostic,
    lookup_bounded_legal_corpus,
    search_federal_register,
    search_recap_documents,
    search_state_administrative_rules,
    search_state_laws,
    search_us_code,
)
from claim_support_review import _merge_intake_summary_handoff_metadata
from integrations.ipfs_datasets.search import (
    COMMON_CRAWL_AVAILABLE as WEB_ARCHIVING_AVAILABLE,
    CommonCrawlSearchEngine,
)

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None


_CONTENT_ORIGIN_ARTIFACT_FAMILY = {
    'historical_archive_capture': 'archived_web_page',
    'live_web_capture': 'live_web_page',
    'authority_full_text': 'legal_authority_text',
    'authority_reference_fallback': 'legal_authority_reference',
}

_ARTIFACT_FAMILY_CORPUS_FAMILY = {
    'archived_web_page': 'web_page',
    'live_web_page': 'web_page',
    'legal_authority_text': 'legal_authority',
    'legal_authority_reference': 'legal_authority',
}

_LEGAL_AUTHORITY_FACT_DURABLE_COLUMNS = {
    'source_family': 'VARCHAR',
    'source_record_id': 'BIGINT',
    'source_ref': 'VARCHAR',
    'record_scope': 'VARCHAR',
    'artifact_family': 'VARCHAR',
    'corpus_family': 'VARCHAR',
    'content_origin': 'VARCHAR',
    'parse_source': 'VARCHAR',
    'input_format': 'VARCHAR',
    'quality_tier': 'VARCHAR',
    'quality_score': 'DOUBLE',
    'page_count': 'INTEGER',
    'chunk_id': 'VARCHAR',
    'chunk_index': 'INTEGER',
    'source_passage': 'JSON',
}

_MAX_SOURCE_PASSAGE_TEXT_LENGTH = 500

_LEGAL_SEARCH_USER_AGENT = 'complaint-generator/1.0'
_HOUSING_QUERY_HINTS = {
    'housing',
    'voucher',
    'hud',
    'pha',
    'public',
    'authority',
    'accommodation',
    'termination',
    'hearing',
    'retaliation',
    'disability',
    'fraud',
    'orientation',
    'informal',
    'review',
}
_OREGON_STATUTE_REFERENCE_CATALOG = [
    {
        'citation': 'ORS 659A.145',
        'title': 'Discrimination against individual with disability in real property transactions prohibited',
        'url': 'https://oregon.public.law/statutes/ors_659a.145',
        'topics': ['disability', 'accommodation', 'housing', 'retaliation', 'reasonable'],
    },
    {
        'citation': 'ORS Chapter 456',
        'title': 'Oregon Housing Authorities Law',
        'url': 'https://www.oregonlegislature.gov/bills_laws/ors/ors456.html',
        'topics': ['housing', 'authority', 'clackamas', 'public', 'voucher'],
    },
]
_FEDERAL_STATUTE_REFERENCE_CATALOG = [
    {
        'citation': '42 U.S.C. § 3604(f)(3)(B)',
        'title': 'Fair Housing Act reasonable accommodations',
        'url': 'https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title42-section3604&num=0&edition=prelim',
        'topics': ['fair', 'housing', 'reasonable', 'accommodation', 'disability', 'dwelling'],
    },
    {
        'citation': '42 U.S.C. § 1437d(k)',
        'title': 'Public housing grievance procedures',
        'url': 'https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title42-section1437d&num=0&edition=prelim',
        'topics': ['grievance', 'hearing', 'termination', 'public', 'housing', 'procedure'],
    },
    {
        'citation': '42 U.S.C. § 1437f',
        'title': 'Low-income housing assistance',
        'url': 'https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title42-section1437f&num=0&edition=prelim',
        'topics': ['voucher', 'section', 'housing', 'assistance', 'termination', 'participant'],
    },
]
_AGENCY_GUIDANCE_REFERENCE_CATALOG = [
    {
        'domain': 'hud.gov',
        'source': 'hud_guidance_fallback',
        'title': 'Housing Choice Voucher Program Guidebook',
        'url': 'https://www.hud.gov/helping-americans/housing-choice-vouchers-guidebook',
        'summary': 'HUD guidebook with chapters on informal hearings, reviews, terminations, fair housing, and reasonable accommodation requirements.',
        'topics': ['voucher', 'housing', 'guidebook', 'informal', 'hearing', 'review', 'termination', 'reasonable', 'accommodation'],
    },
    {
        'domain': 'hud.gov',
        'source': 'hud_guidance_fallback',
        'title': 'Housing Choice Vouchers Guidance and Notices',
        'url': 'https://www.hud.gov/helping-americans/housing-choice-vouchers-guidance',
        'summary': 'HUD page collecting HCV guidance, notices, and administrative resources for PHAs.',
        'topics': ['voucher', 'housing', 'guidance', 'notice', 'pha', 'administrative'],
    },
    {
        'domain': 'hud.gov',
        'source': 'hud_guidance_fallback',
        'title': 'HUD/DOJ Joint Statement on Reasonable Accommodations under the Fair Housing Act',
        'url': 'https://www.hud.gov/sites/documents/JOINTSTATEMENT.PDF',
        'summary': 'Joint federal guidance on reasonable accommodations for people with disabilities under the Fair Housing Act.',
        'topics': ['reasonable', 'accommodation', 'fair', 'housing', 'disability'],
    },
    {
        'domain': 'clackamas.us',
        'source': 'clackamas_guidance_fallback',
        'title': 'Housing Choice Voucher Programs | Clackamas County',
        'url': 'https://www.clackamas.us/housingauthority/section8.html',
        'summary': 'Clackamas HACC program page describing voucher processes and reasonable accommodation availability for applicants and participants.',
        'topics': ['clackamas', 'housing', 'voucher', 'reasonable', 'accommodation', 'participant', 'applicant'],
    },
    {
        'domain': 'clackamas.us',
        'source': 'clackamas_guidance_fallback',
        'title': 'Housing Authority of Clackamas County Administrative Plan',
        'url': 'https://dochub.clackamas.us/documents/drupal/76861a83-9a1a-43ee-becb-f8556827f676',
        'summary': 'Administrative plan material for the Housing Authority of Clackamas County, including Housing Choice Voucher program procedures.',
        'topics': ['clackamas', 'administrative', 'plan', 'housing', 'authority', 'voucher', 'hearing', 'procedure'],
    },
]


def _strip_html(value: str) -> str:
    return re.sub(r'<[^>]+>', ' ', unescape(str(value or ''))).replace('\xa0', ' ').strip()


def _query_terms(value: str) -> List[str]:
    return [
        token.lower()
        for token in re.findall(r'[a-zA-Z0-9\.]+', str(value or ''))
        if len(token) >= 3
    ]


def _text_overlap_score(query: str, *values: str) -> float:
    query_tokens = set(_query_terms(query))
    if not query_tokens:
        return 0.0
    haystack_tokens = set()
    for value in values:
        haystack_tokens.update(_query_terms(value))
    if not haystack_tokens:
        return 0.0
    overlap = query_tokens & haystack_tokens
    hint_overlap = query_tokens & _HOUSING_QUERY_HINTS
    score = len(overlap) / max(len(query_tokens), 1)
    if overlap & _HOUSING_QUERY_HINTS:
        score += 0.25
    elif hint_overlap and haystack_tokens & _HOUSING_QUERY_HINTS:
        score += 0.15
    return score


def _extract_cfr_sections(query: str) -> List[str]:
    sections: List[str] = []
    for match in re.findall(r'(?:\b\d+\s*cfr\s*)?(\d{2,4}\.\d{1,4})', str(query or ''), flags=re.IGNORECASE):
        section = str(match).strip()
        if not section or section in sections:
            continue
        sections.append(section)
    return sections


def _resolve_artifact_identity(*, content_origin: str = '', artifact_family: str = '', corpus_family: str = '') -> Dict[str, str]:
    resolved_artifact_family = artifact_family or _CONTENT_ORIGIN_ARTIFACT_FAMILY.get(content_origin, '')
    resolved_corpus_family = corpus_family or _ARTIFACT_FAMILY_CORPUS_FAMILY.get(resolved_artifact_family, '')
    return {
        'artifact_family': resolved_artifact_family,
        'corpus_family': resolved_corpus_family,
    }


def _ensure_legal_authority_fact_schema(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS legal_authority_facts (
            authority_id BIGINT,
            fact_id VARCHAR,
            fact_text TEXT,
            source_authority_id VARCHAR,
            confidence FLOAT,
            metadata JSON,
            provenance JSON
        )
    """)
    for column_name, column_type in _LEGAL_AUTHORITY_FACT_DURABLE_COLUMNS.items():
        conn.execute(
            f"ALTER TABLE legal_authority_facts ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
        )


def _list_table_columns(conn: Any, table_name: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return [str(row[1]) for row in rows]


def _normalize_authority_fact_row(row: Any, *, authority_id: int) -> Dict[str, Any]:
    metadata = json.loads(row[4]) if row[4] else {}
    provenance = json.loads(row[5]) if row[5] else {}
    durable_values = dict(row[6]) if len(row) > 6 and isinstance(row[6], dict) else {}
    parse_lineage = metadata.get('parse_lineage', {}) if isinstance(metadata.get('parse_lineage'), dict) else {}
    transform_lineage = parse_lineage.get('transform_lineage', {}) if isinstance(parse_lineage.get('transform_lineage'), dict) else {}
    parse_quality = parse_lineage.get('parse_quality', {}) if isinstance(parse_lineage.get('parse_quality'), dict) else {}
    source_span = parse_lineage.get('source_span', {}) if isinstance(parse_lineage.get('source_span'), dict) else {}
    provenance_metadata = provenance.get('metadata', {}) if isinstance(provenance.get('metadata'), dict) else {}
    content_origin = str(
        durable_values.get('content_origin')
        or transform_lineage.get('content_origin')
        or parse_lineage.get('content_origin')
        or provenance_metadata.get('content_origin')
        or ''
    )
    artifact_identity = _resolve_artifact_identity(
        content_origin=content_origin,
        artifact_family=str(
            durable_values.get('artifact_family')
            or transform_lineage.get('artifact_family')
            or parse_lineage.get('artifact_family')
            or provenance_metadata.get('artifact_family')
            or ''
        ),
        corpus_family=str(
            durable_values.get('corpus_family')
            or transform_lineage.get('corpus_family')
            or parse_lineage.get('corpus_family')
            or provenance_metadata.get('corpus_family')
            or ''
        ),
    )
    durable_source_passage = durable_values.get('source_passage')
    if isinstance(durable_source_passage, str) and durable_source_passage:
        try:
            durable_source_passage = json.loads(durable_source_passage)
        except json.JSONDecodeError:
            durable_source_passage = {}
    source_passage = durable_source_passage if isinstance(durable_source_passage, dict) else {}
    if not source_passage:
        source_passage = dict(metadata.get('source_passage') or {})
    source_ref = str(durable_values.get('source_ref') or row[2] or parse_lineage.get('source_ref') or '')
    return {
        'fact_id': row[0],
        'text': row[1],
        'source_authority_id': row[2],
        'confidence': row[3] or 0.0,
        'metadata': metadata,
        'provenance': provenance,
        'source_family': str(durable_values.get('source_family') or 'legal_authority'),
        'source_record_id': int(durable_values.get('source_record_id') or authority_id),
        'source_ref': source_ref,
        'record_scope': str(durable_values.get('record_scope') or parse_lineage.get('record_scope') or 'legal_authority'),
        'artifact_family': artifact_identity['artifact_family'],
        'corpus_family': artifact_identity['corpus_family'],
        'content_origin': content_origin,
        'parse_source': str(durable_values.get('parse_source') or parse_lineage.get('source') or ''),
        'input_format': str(durable_values.get('input_format') or parse_lineage.get('input_format') or ''),
        'quality_tier': str(durable_values.get('quality_tier') or parse_lineage.get('quality_tier') or ''),
        'quality_score': float(durable_values.get('quality_score') or parse_lineage.get('quality_score') or parse_quality.get('quality_score') or 0.0),
        'page_count': int(durable_values.get('page_count') or parse_lineage.get('page_count') or source_span.get('page_count') or 0),
        'chunk_id': str(durable_values.get('chunk_id') or metadata.get('chunk_id') or ''),
        'chunk_index': int(durable_values.get('chunk_index') or metadata.get('chunk_index') or 0),
        'source_passage': source_passage,
    }


def _clone_provenance_record(provenance) -> Any:
    return build_provenance(
        source_url=str(provenance.source_url or ''),
        acquisition_method=str(provenance.acquisition_method or ''),
        source_type=str(provenance.source_type or ''),
        acquired_at=str(provenance.acquired_at or ''),
        content_hash=str(provenance.content_hash or ''),
        source_system=str(provenance.source_system or ''),
        jurisdiction=str(provenance.jurisdiction or ''),
        metadata=dict(getattr(provenance, 'metadata', {}) or {}),
    )


def _merge_handoff_into_provenance_record(provenance, mediator) -> Any:
    return build_provenance(
        source_url=str(provenance.source_url or ''),
        acquisition_method=str(provenance.acquisition_method or ''),
        source_type=str(provenance.source_type or ''),
        acquired_at=str(provenance.acquired_at or ''),
        content_hash=str(provenance.content_hash or ''),
        source_system=str(provenance.source_system or ''),
        jurisdiction=str(provenance.jurisdiction or ''),
        metadata=_merge_intake_summary_handoff_metadata(
            dict(getattr(provenance, 'metadata', {}) or {}),
            mediator,
        ),
    )


def _normalize_lineage_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _clip_source_passage_text(value: str) -> str:
    text = str(value or '').strip()
    if len(text) <= _MAX_SOURCE_PASSAGE_TEXT_LENGTH:
        return text
    return text[:_MAX_SOURCE_PASSAGE_TEXT_LENGTH].rstrip()


class LegalAuthoritySearchHook:
    """
    Hook for searching relevant legal authorities.
    
    Uses web archiving tools and legal scrapers to locate statutes,
    regulations, case law, and other legal authorities relevant to the case.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
        self._check_availability()
        self._init_web_archiving()
    
    def _check_availability(self):
        """Check availability of legal search tools."""
        if not LEGAL_SCRAPERS_AVAILABLE:
            self.mediator.log('legal_authority_warning',
                message='Legal scrapers not fully available - some features may be limited')
        elif not all(bool(value) for value in LEGAL_SOURCE_AVAILABILITY.values()):
            self.mediator.log(
                'legal_authority_warning',
                message='Some legal scraper families are degraded',
                source_availability=dict(LEGAL_SOURCE_AVAILABILITY),
            )
        if not WEB_ARCHIVING_AVAILABLE:
            self.mediator.log('legal_authority_warning',
                message='Web archiving not available - web search disabled')
    
    def _init_web_archiving(self):
        """Initialize web archiving engine if available."""
        if WEB_ARCHIVING_AVAILABLE:
            try:
                self.web_search = CommonCrawlSearchEngine(mode='local')
                self.mediator.log('legal_authority_init', 
                    message='Web archiving search engine initialized')
            except Exception as e:
                self.web_search = None
                self.mediator.log('legal_authority_warning',
                    message=f'Failed to initialize web archiving: {e}')
        else:
            self.web_search = None

    def _log_hf_coverage_warning(
        self,
        *,
        search_type: str,
        query: str,
        state: Optional[str],
        results: List[Dict[str, Any]],
        diagnostic_key: str,
    ) -> None:
        diagnostic = get_last_legal_search_diagnostic(diagnostic_key)
        if not diagnostic or results:
            return
        warning_code = str(diagnostic.get('warning_code') or '').strip()
        warning_message = str(diagnostic.get('warning_message') or '').strip()
        if not warning_code or not warning_message:
            return
        self.mediator.log(
            'legal_authority_warning',
            message=warning_message,
            warning_code=warning_code,
            search_type=search_type,
            query=query,
            state=state,
            search_diagnostic=diagnostic,
        )

    def _collect_search_diagnostics(
        self,
        *,
        query: str,
        state: Optional[str],
    ) -> Dict[str, Any]:
        diagnostics: Dict[str, Any] = {
            'source_availability': dict(LEGAL_SOURCE_AVAILABILITY),
        }

        # Default Mediator list-returning calls publish only this query's
        # actual bounded outcomes, never stale module-global legacy diagnostics.
        if getattr(self, '_bounded_diagnostic_query', None) == query:
            diagnostics.update(getattr(self, '_bounded_diagnostics', {}))

        return diagnostics
    def _http_get_json(self, url: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = requests.get(
            url,
            params=params or {},
            timeout=20,
            headers={'User-Agent': _LEGAL_SEARCH_USER_AGENT},
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _http_get_text(self, url: str) -> str:
        response = requests.get(
            url,
            timeout=20,
            headers={'User-Agent': _LEGAL_SEARCH_USER_AGENT},
        )
        response.raise_for_status()
        return response.text or ''

    def _dedupe_authority_rows(self, rows: List[Dict[str, Any]], *, max_results: int) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = (
                str(row.get('url') or '').strip().lower(),
                str(row.get('citation') or '').strip().lower(),
                str(row.get('title') or '').strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
            if len(deduped) >= max_results:
                break
        return deduped

    def _normalize_ecfr_result(self, item: Dict[str, Any], *, query: str) -> Dict[str, Any]:
        hierarchy = item.get('hierarchy') if isinstance(item.get('hierarchy'), dict) else {}
        section = str(hierarchy.get('section') or '').strip()
        title_number = str(hierarchy.get('title') or '').strip()
        citation = ''
        if title_number and section:
            citation = f"{title_number} C.F.R. § {section}"
        headings = item.get('headings') if isinstance(item.get('headings'), dict) else {}
        part_heading = str(headings.get('part') or '').strip()
        section_heading = str(headings.get('section') or '').strip()
        title = section_heading or part_heading or citation or 'eCFR regulation'
        excerpt = _strip_html(item.get('full_text_excerpt') or '')
        url = (
            f"https://www.ecfr.gov/current/title-{title_number}/subtitle-B/chapter-IX/part-{hierarchy.get('part')}/"
            f"subpart-{hierarchy.get('subpart')}/section-{section}"
            if title_number and hierarchy.get('part') and hierarchy.get('subpart') and section
            else ''
        )
        relevance = float(item.get('score') or 0.0)
        if relevance <= 0:
            relevance = max(_text_overlap_score(query, title, excerpt, citation), 0.25)
        return {
            'type': 'regulation',
            'source': 'ecfr',
            'citation': citation or item.get('label') or 'C.F.R. result',
            'title': title,
            'content': excerpt,
            'url': url,
            'metadata': {
                'hierarchy': hierarchy,
                'headings': headings,
                'search_backend': 'ecfr_api',
            },
            'relevance_score': relevance,
        }

    def _search_ecfr_fallback(self, query: str, *, max_results: int = 10) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        search_queries = _extract_cfr_sections(query) or [query]
        if query not in search_queries:
            search_queries.append(query)
        for search_query in search_queries[:3]:
            try:
                payload = self._http_get_json(
                    'https://www.ecfr.gov/api/search/v1/results',
                    params={
                        'query': search_query,
                        'per_page': max_results,
                        'order': 'relevance',
                    },
                )
            except Exception as exc:
                self.mediator.log(
                    'legal_authority_search_error',
                    search_type='ecfr_fallback',
                    query=search_query,
                    error=str(exc),
                )
                continue

            items = payload.get('results')
            if not isinstance(items, list):
                continue
            rows.extend(
                self._normalize_ecfr_result(item, query=query)
                for item in items
                if isinstance(item, dict)
            )
        rows = [row for row in rows if _text_overlap_score(query, row.get('title', ''), row.get('content', ''), row.get('citation', '')) >= 0.18]
        return self._dedupe_authority_rows(sorted(rows, key=lambda item: float(item.get('relevance_score') or 0.0), reverse=True), max_results=max_results)

    def _normalize_courtlistener_result(self, item: Dict[str, Any], *, query: str) -> Dict[str, Any]:
        citations = item.get('citation')
        citation_text = ''
        if isinstance(citations, list) and citations:
            first = citations[0]
            if isinstance(first, dict):
                citation_text = str(first.get('cite') or first.get('volume') or '').strip()
            else:
                citation_text = str(first).strip()
        if not citation_text:
            citation_text = str(item.get('caseName') or item.get('caseNameFull') or item.get('docketNumber') or '').strip()
        absolute_url = str(item.get('absolute_url') or '').strip()
        if absolute_url and absolute_url.startswith('/'):
            absolute_url = f"https://www.courtlistener.com{absolute_url}"
        title = str(item.get('caseNameFull') or item.get('caseName') or citation_text or 'Case law result').strip()
        court = str(item.get('court') or item.get('court_citation_string') or '').strip()
        date_filed = str(item.get('dateFiled') or '').strip()
        content = ' '.join(part for part in [court, date_filed, str(item.get('snippet') or '').strip()] if part).strip()
        score = 0.0
        meta = item.get('meta') if isinstance(item.get('meta'), dict) else {}
        meta_score = meta.get('score') if isinstance(meta.get('score'), dict) else {}
        try:
            score = float(meta_score.get('bm25') or 0.0)
        except Exception:
            score = 0.0
        if score <= 0:
            score = max(_text_overlap_score(query, title, content, citation_text), 0.25)
        return {
            'type': 'case_law',
            'source': 'courtlistener',
            'citation': citation_text or title,
            'title': title,
            'content': content,
            'url': absolute_url,
            'metadata': {
                'court': court,
                'court_id': item.get('court_id'),
                'date_filed': date_filed,
                'cluster_id': item.get('cluster_id'),
                'search_backend': 'courtlistener_api',
            },
            'relevance_score': score,
        }

    def _search_courtlistener_fallback(self, query: str, jurisdiction: Optional[str] = None,
                                       *, max_results: int = 10) -> List[Dict[str, Any]]:
        normalized: List[tuple[bool, Dict[str, Any]]] = []
        jurisdiction_text = str(jurisdiction or '').lower().strip()
        query_tokens = set(_query_terms(query))
        simplified_parts: List[str] = []
        if 'housing' in query_tokens and 'authority' in query_tokens:
            simplified_parts.append('housing authority')
        if 'voucher' in query_tokens:
            simplified_parts.append('voucher')
        if 'termination' in query_tokens:
            simplified_parts.append('termination')
        if 'family' in query_tokens and 'obligations' in query_tokens:
            simplified_parts.append('family obligations')
        if 'informal' in query_tokens or 'hearing' in query_tokens or 'review' in query_tokens:
            simplified_parts.append('informal hearing')
        if 'reasonable' in query_tokens or 'accommodation' in query_tokens:
            simplified_parts.append('reasonable accommodation')
        if 'retaliation' in query_tokens:
            simplified_parts.append('retaliation')
        search_queries = [query]
        simplified_query = ' '.join(simplified_parts).strip()
        if simplified_query and simplified_query.lower() != query.lower():
            search_queries.append(simplified_query)
        if 'housing authority' in simplified_query and 'voucher' in query_tokens:
            search_queries.append('housing authority voucher termination')

        for search_query in search_queries[:3]:
            params: Dict[str, Any] = {
                'q': search_query,
                'page_size': max_results,
                'type': 'o',
            }
            try:
                payload = self._http_get_json(
                    'https://www.courtlistener.com/api/rest/v4/search/',
                    params=params,
                )
            except Exception as exc:
                self.mediator.log(
                    'legal_authority_search_error',
                    search_type='courtlistener_fallback',
                    query=search_query,
                    error=str(exc),
                )
                continue

            items = payload.get('results')
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                row = self._normalize_courtlistener_result(item, query=query)
                court_blob = ' '.join(
                    [
                        str(item.get('court') or ''),
                        str(item.get('court_citation_string') or ''),
                        str(item.get('court_id') or ''),
                    ]
                ).lower()
                if _text_overlap_score(query, row.get('title', ''), row.get('content', ''), row.get('citation', '')) < 0.12:
                    continue
                jurisdiction_match = (
                    not jurisdiction_text
                    or jurisdiction_text in court_blob
                    or jurisdiction_text in row['content'].lower()
                    or (
                        jurisdiction_text in {'or', 'oregon'}
                        and ('oregon' in court_blob or 'or.' in court_blob)
                    )
                    or (
                        jurisdiction_text in {'9th', 'ninth circuit'}
                        and ('9th' in court_blob or 'ninth' in court_blob)
                    )
                )
                normalized.append((jurisdiction_match, row))
        normalized.sort(
            key=lambda item: (
                1 if item[0] else 0,
                float(item[1].get('relevance_score') or 0.0),
            ),
            reverse=True,
        )
        return self._dedupe_authority_rows([row for _, row in normalized], max_results=max_results)

    def _search_oregon_statutes_fallback(self, query: str, *, max_results: int = 10) -> List[Dict[str, Any]]:
        query_lower = str(query or '').lower()
        if 'oregon' not in query_lower and 'ors' not in query_lower and 'clackamas' not in query_lower:
            return []
        rows: List[Dict[str, Any]] = []
        for item in _OREGON_STATUTE_REFERENCE_CATALOG:
            overlap = _text_overlap_score(query, item.get('citation', ''), item.get('title', ''), ' '.join(item.get('topics') or []))
            if overlap < 0.12:
                continue
            content = ''
            try:
                text = self._http_get_text(item['url'])
                title_match = re.search(r'<title>(.*?)</title>', text, flags=re.IGNORECASE | re.DOTALL)
                meta_match = re.search(r'<meta[^>]+name=[\'"]description[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', text, flags=re.IGNORECASE)
                title = _strip_html(title_match.group(1)) if title_match else str(item.get('title') or '')
                content = _strip_html(meta_match.group(1)) if meta_match else ''
            except Exception as exc:
                self.mediator.log(
                    'legal_authority_search_error',
                    search_type='oregon_statute_fallback',
                    query=query,
                    citation=item.get('citation'),
                    error=str(exc),
                )
                title = str(item.get('title') or '')
            rows.append(
                {
                    'type': 'state_statute',
                    'source': 'oregon_public_law' if 'public.law' in item['url'] else 'oregon_legislature',
                    'citation': str(item.get('citation') or ''),
                    'title': title,
                    'content': content,
                    'url': item['url'],
                    'metadata': {
                        'topics': list(item.get('topics') or []),
                        'search_backend': 'oregon_statute_fallback',
                    },
                    'relevance_score': max(overlap, 0.2),
                }
            )
        rows.sort(key=lambda item: float(item.get('relevance_score') or 0.0), reverse=True)
        return self._dedupe_authority_rows(rows, max_results=max_results)

    def _search_federal_statutes_fallback(self, query: str, *, max_results: int = 10) -> List[Dict[str, Any]]:
        query_lower = str(query or '').lower()
        if not any(token in query_lower for token in ('fair housing', 'reasonable accommodation', 'voucher', 'section 8', 'housing', 'termination', 'hearing', 'grievance', '1437', '3604')):
            return []
        rows: List[Dict[str, Any]] = []
        for item in _FEDERAL_STATUTE_REFERENCE_CATALOG:
            overlap = _text_overlap_score(query, item.get('citation', ''), item.get('title', ''), ' '.join(item.get('topics') or []))
            if overlap < 0.12:
                continue
            content = ''
            title = str(item.get('title') or '')
            try:
                text = self._http_get_text(item['url'])
                title_match = re.search(r'<title>(.*?)</title>', text, flags=re.IGNORECASE | re.DOTALL)
                if title_match:
                    title = _strip_html(title_match.group(1))
            except Exception as exc:
                self.mediator.log(
                    'legal_authority_search_error',
                    search_type='federal_statute_fallback',
                    query=query,
                    citation=item.get('citation'),
                    error=str(exc),
                )
            rows.append(
                {
                    'type': 'statute',
                    'source': 'uscode_house',
                    'citation': str(item.get('citation') or ''),
                    'title': title,
                    'content': content,
                    'url': item['url'],
                    'metadata': {
                        'topics': list(item.get('topics') or []),
                        'search_backend': 'federal_statute_fallback',
                    },
                    'relevance_score': max(overlap, 0.2),
                }
            )
        rows.sort(key=lambda item: float(item.get('relevance_score') or 0.0), reverse=True)
        return self._dedupe_authority_rows(rows, max_results=max_results)

    def _search_agency_guidance_fallback(self, domain: str, query: Optional[str] = None,
                                         *, max_results: int = 20) -> List[Dict[str, Any]]:
        domain_text = str(domain or '').strip().lower()
        query_text = str(query or '').strip()
        rows: List[Dict[str, Any]] = []
        for item in _AGENCY_GUIDANCE_REFERENCE_CATALOG:
            if str(item.get('domain') or '').strip().lower() != domain_text:
                continue
            overlap = _text_overlap_score(
                query_text,
                item.get('title', ''),
                item.get('summary', ''),
                ' '.join(item.get('topics') or []),
            ) if query_text else 0.25
            if query_text and overlap < 0.10:
                continue
            rows.append(
                {
                    'type': 'agency_guidance',
                    'source': str(item.get('source') or 'agency_guidance_fallback'),
                    'citation': str(item.get('title') or ''),
                    'title': str(item.get('title') or ''),
                    'content': str(item.get('summary') or ''),
                    'url': str(item.get('url') or ''),
                    'metadata': {
                        'domain': domain_text,
                        'topics': list(item.get('topics') or []),
                        'search_backend': 'agency_guidance_fallback',
                    },
                    'relevance_score': max(overlap, 0.2),
                }
            )
        rows.sort(key=lambda item: float(item.get('relevance_score') or 0.0), reverse=True)
        return self._dedupe_authority_rows(rows, max_results=max_results)

    def _filter_regulation_results(self, query: str, rows: List[Dict[str, Any]], *, max_results: int) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(row.get('title') or '')
            content = str(row.get('content') or row.get('abstract') or '')
            citation = str(row.get('citation') or '')
            source = str(row.get('source') or '').lower()
            score = _text_overlap_score(query, title, content, citation)
            if source == 'federal_register' and score < 0.12:
                continue
            normalized = dict(row)
            normalized['relevance_score'] = float(normalized.get('relevance_score') or score or 0.25)
            filtered.append(normalized)
        filtered.sort(key=lambda item: float(item.get('relevance_score') or 0.0), reverse=True)
        return self._dedupe_authority_rows(filtered, max_results=max_results)
    
    def search_us_code(self, query: str, title: Optional[str] = None,
                      max_results: int = 10, **lookup_options: Any) -> List[Dict[str, Any]]:
        """Return explicit bounded federal candidates; no generated search terms."""
        return self._bounded_authority_rows('us_code', query, max_results,
            titles=[title] if title else None, **lookup_options)

    def search_federal_register(self, query: str, start_date: Optional[str] = None,
                               end_date: Optional[str] = None, max_results: int = 10,
                               **lookup_options: Any) -> List[Dict[str, Any]]:
        return self._bounded_authority_rows('federal_register', query, max_results,
            start_date=start_date, end_date=end_date, **lookup_options)

    def search_state_laws(self, query: str, state: Optional[str] = None,
                          max_results: int = 10, allow_live_scrape_fallback: bool = False,
                          **lookup_options: Any) -> List[Dict[str, Any]]:
        # A historical scraper opt-in is not authority to set up or scrape.
        return self._bounded_authority_rows('state_statute', query, max_results,
            state=state, **lookup_options)

    def search_administrative_law(self, query: str, state: Optional[str] = None,
                                  max_results: int = 10, allow_live_scrape_fallback: bool = False,
                                  **lookup_options: Any) -> List[Dict[str, Any]]:
        return self._bounded_authority_rows('state_administrative_rule', query, max_results,
            state=state, **lookup_options)

    def _bounded_authority_rows(self, family: str, query: str, max_results: int,
                                **lookup_options: Any) -> List[Dict[str, Any]]:
        options = dict(lookup_options)
        options.setdefault('retrieval_mode', 'offline')
        envelope = self.lookup_bounded_corpus(source_family=family, query=query,
            max_results=max_results, **options)
        if getattr(self, '_bounded_diagnostic_query', None) != query:
            self._bounded_diagnostic_query = query
            self._bounded_diagnostics = {}
        bucket = {'us_code':'statutes','state_statute':'state_statutes',
            'federal_register':'regulations','state_administrative_rule':'administrative_rules'}[family]
        diagnostic = {key: envelope.get(key) for key in
            ('status','capability','error_code','retrieval_mode','applicability')}
        if envelope.get('status') in {'unavailable','error','timeout'}:
            diagnostic.update(warning_code=envelope.get('error_code') or 'backend_unavailable',
                warning_message='Legal corpus search is unavailable; intake can continue.')
        self._bounded_diagnostics[bucket] = diagnostic
        return list(envelope.get('results') or [])

    def search_case_law(self, query: str, jurisdiction: Optional[str] = None,
                       max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search case law using RECAP archive.
        
        Args:
            query: Search query
            jurisdiction: Optional jurisdiction filter
            max_results: Maximum number of results
            
        Returns:
            List of case law documents
        """
        if not LEGAL_SCRAPERS_AVAILABLE or search_recap_documents is None:
            self.mediator.log('legal_authority_unavailable',
                search_type='case_law', query=query)
            return self._search_courtlistener_fallback(
                query,
                jurisdiction=jurisdiction,
                max_results=max_results,
            )
        
        try:
            results = search_recap_documents(
                query=query,
                court=jurisdiction,
                max_results=max_results
            )
            normalized_results = self._dedupe_authority_rows(
                [
                    {
                        **result,
                        'source': result.get('source', 'recap'),
                    }
                    for result in results
                    if isinstance(result, dict)
                ],
                max_results=max_results,
            )
            fallback_results: List[Dict[str, Any]] = []
            if not normalized_results:
                fallback_results = self._search_courtlistener_fallback(
                    query,
                    jurisdiction=jurisdiction,
                    max_results=max_results,
                )
            combined = self._dedupe_authority_rows(
                normalized_results + fallback_results,
                max_results=max_results,
            )
            
            self.mediator.log('legal_authority_search',
                search_type='case_law', query=query, found=len(combined))
            
            return combined
            
        except Exception as e:
            self.mediator.log('legal_authority_search_error',
                search_type='case_law', error=str(e))
            return []
    
    def search_web_archives(self, domain: str, query: Optional[str] = None,
                           max_results: int = 20) -> List[Dict[str, Any]]:
        """
        Search web archives for legal information.
        
        Args:
            domain: Domain to search (e.g., "law.cornell.edu")
            query: Optional search query
            max_results: Maximum number of results
            
        Returns:
            List of archived web pages with legal content
        """
        if not self.web_search:
            self.mediator.log('legal_authority_unavailable',
                search_type='web_archive', domain=domain)
            return self._search_agency_guidance_fallback(domain, query=query, max_results=max_results)
        
        try:
            results = self.web_search.search_domain(
                domain=domain,
                max_matches=max_results
            )
            normalized_results = [dict(item) for item in results if isinstance(item, dict)]
            if not normalized_results:
                normalized_results = self._search_agency_guidance_fallback(domain, query=query, max_results=max_results)
            
            self.mediator.log('legal_authority_search',
                search_type='web_archive', domain=domain, found=len(normalized_results))
            
            return normalized_results
            
        except Exception as e:
            self.mediator.log('legal_authority_search_error',
                search_type='web_archive', error=str(e))
            return self._search_agency_guidance_fallback(domain, query=query, max_results=max_results)
    
    def _generate_search_terms(self, query: str) -> List[str]:
        """Generate search terms from query using LLM."""
        try:
            prompt = f"""Given the legal query: "{query}"
            
Generate 3 specific search terms for finding relevant US Code statutes.
Return only the search terms, one per line."""
            
            response = self.mediator.query_backend(prompt)
            terms = [line.strip() for line in response.split('\n') if line.strip()]
            return terms[:3] or [query]
        except Exception:
            return [query]

    def build_search_programs(
        self,
        query: str,
        claim_type: Optional[str] = None,
        claim_elements: Optional[List[Dict[str, Any]]] = None,
        jurisdiction: Optional[str] = None,
        forum: Optional[str] = None,
        time_window: Optional[Dict[str, Any]] = None,
        defense_themes: Optional[List[str]] = None,
        authority_families: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build claim-aware legal search programs for support, procedure, and adverse authority.

        The current output is intentionally deterministic and mediator-friendly so it can
        be persisted or attached to follow-up tasks before richer search-program logic lands.
        """
        base_query = str(query or "").strip()
        if not base_query:
            return []

        normalized_claim_type = str(claim_type or "").strip()
        normalized_jurisdiction = str(jurisdiction or "").strip()
        normalized_forum = str(forum or "").strip()
        generated_terms = self._generate_search_terms(base_query)
        normalized_time_window = time_window if isinstance(time_window, dict) else {}
        time_window_start = str(
            normalized_time_window.get('start')
            or normalized_time_window.get('time_window_start')
            or normalized_time_window.get('from')
            or ''
        ).strip()
        time_window_end = str(
            normalized_time_window.get('end')
            or normalized_time_window.get('time_window_end')
            or normalized_time_window.get('to')
            or ''
        ).strip()
        time_window_terms = [
            str(term).strip()
            for term in (normalized_time_window.get('query_terms') or [])
            if str(term).strip()
        ]
        normalized_defense_themes = list(dict.fromkeys([
            str(theme).strip()
            for theme in (defense_themes or [])
            if str(theme).strip()
        ]))
        requested_authority_families = list(dict.fromkeys([
            str(family).strip()
            for family in (authority_families or [])
            if str(family).strip()
        ]))

        normalized_elements: List[Dict[str, str]] = []
        for element in claim_elements or []:
            if not isinstance(element, dict):
                continue
            element_text = str(
                element.get('claim_element_text')
                or element.get('element_text')
                or element.get('claim_element')
                or ''
            ).strip()
            if not element_text:
                continue
            normalized_elements.append(
                {
                    'claim_element_id': str(element.get('claim_element_id') or element.get('element_id') or '').strip(),
                    'claim_element_text': element_text,
                }
            )

        if not normalized_elements:
            normalized_elements = [
                {
                    'claim_element_id': '',
                    'claim_element_text': normalized_claim_type or base_query,
                }
            ]

        program_templates = [
            {
                'program_type': 'element_definition_search',
                'authority_intent': 'support',
                'authority_families': ['statute', 'regulation', 'administrative_rule'],
                'query_suffix': 'element definition statute regulation rule',
                'defense_theme': 'element_standard',
            },
            {
                'program_type': 'fact_pattern_search',
                'authority_intent': 'support',
                'authority_families': ['case_law', 'agency_guidance'],
                'query_suffix': 'fact pattern application authority',
                'defense_theme': 'fact_application',
            },
            {
                'program_type': 'procedural_search',
                'authority_intent': 'procedural',
                'authority_families': ['regulation', 'administrative_rule', 'agency_guidance'],
                'query_suffix': 'timeliness exhaustion venue notice procedure',
                'defense_theme': 'procedural_prerequisite',
            },
            {
                'program_type': 'adverse_authority_search',
                'authority_intent': 'oppose',
                'authority_families': ['case_law', 'statute', 'regulation'],
                'query_suffix': 'adverse authority defense exception limitation',
                'defense_theme': 'defense_or_exception',
            },
            {
                'program_type': 'treatment_check_search',
                'authority_intent': 'confirm_good_law',
                'authority_families': ['case_law', 'administrative_rule', 'agency_guidance'],
                'query_suffix': 'citation history later treatment good law',
                'defense_theme': 'authority_treatment',
            },
        ]

        programs: List[Dict[str, Any]] = []
        for element in normalized_elements:
            element_text = element['claim_element_text']
            for template in program_templates:
                template_families = list(template['authority_families'])
                if requested_authority_families:
                    filtered_families = [
                        family for family in template_families
                        if family in requested_authority_families
                    ]
                    if filtered_families:
                        template_families = filtered_families
                search_terms = [
                    term
                    for term in [element_text, normalized_claim_type, *generated_terms]
                    if term
                ]
                search_terms.extend(time_window_terms)
                program = LegalSearchProgram(
                    program_type=template['program_type'],
                    claim_type=normalized_claim_type or base_query,
                    authority_intent=template['authority_intent'],
                    query_text=' '.join(
                        part
                        for part in [
                            base_query,
                            element_text,
                            normalized_jurisdiction,
                            template['query_suffix'],
                            ' '.join(time_window_terms[:3]),
                        ]
                        if part
                    ),
                    claim_element_id=element['claim_element_id'],
                    claim_element_text=element_text,
                    jurisdiction=normalized_jurisdiction,
                    forum=normalized_forum,
                    time_window_start=time_window_start,
                    time_window_end=time_window_end,
                    authority_families=template_families,
                    search_terms=search_terms[:6],
                    metadata={
                        'base_query': base_query,
                        'claim_type': normalized_claim_type,
                        'jurisdiction': normalized_jurisdiction,
                        'forum': normalized_forum,
                        'time_window': dict(normalized_time_window),
                        'time_window_start': time_window_start,
                        'time_window_end': time_window_end,
                        'time_window_terms': time_window_terms[:8],
                        'defense_theme': template['defense_theme'],
                        'defense_themes': normalized_defense_themes,
                        'authority_family_focus': template_families,
                    },
                )
                programs.append(program.as_dict())

        self.mediator.log(
            'legal_authority_search_programs_built',
            query=base_query,
            claim_type=normalized_claim_type,
            claim_element_count=len(normalized_elements),
            program_count=len(programs),
        )
        return programs
    
    def search_all_sources(self, query: str, claim_type: Optional[str] = None,
                          jurisdiction: Optional[str] = None,
                          authority_families: Optional[List[str]] = None,
                          **lookup_options: Any) -> Dict[str, Any]:
        """Actual mediator discovery path, offline unless explicitly configured.

        Retrieved candidates never choose a jurisdiction or applicability. Cases,
        dockets and web archival discovery require their separate explicit APIs.
        """
        from integrations.ipfs_datasets.legal import resolve_explicit_jurisdiction
        resolved = resolve_explicit_jurisdiction(jurisdiction)
        families = set(authority_families or ('statute', 'regulation', 'administrative_rule', 'court_rule'))
        results = {key: [] for key in ('statutes', 'state_statutes', 'regulations',
            'administrative_rules', 'court_rules', 'case_law', 'web_archives')}
        diagnostics = {'source_availability': dict(LEGAL_SOURCE_AVAILABILITY)}
        if resolved != 'unknown':
            selection = [('statutes', 'us_code', 'statute' in families and resolved == 'federal'),
                ('state_statutes', 'state_statute', 'statute' in families and resolved != 'federal'),
                ('regulations', 'federal_register', 'regulation' in families and resolved == 'federal'),
                ('administrative_rules', 'state_administrative_rule',
                    'administrative_rule' in families and resolved != 'federal'),
                ('court_rules', 'court_rule', 'court_rule' in families)]
            for bucket, family, enabled in selection:
                if not enabled: continue
                options = dict(lookup_options)
                options.setdefault('retrieval_mode', 'offline')
                options.update(jurisdiction=resolved, state=None if resolved == 'federal' else resolved)
                if family == 'court_rule':
                    options.setdefault('court_jurisdiction', 'federal' if resolved == 'federal' else 'state')
                envelope = self.lookup_bounded_corpus(source_family=family, query=query,
                    max_results=5, **options)
                results[bucket] = list(envelope.get('results') or [])
                diagnostics[bucket] = {key: envelope.get(key) for key in
                    ('status', 'capability', 'error_code', 'retrieval_mode', 'applicability')}
        results['search_diagnostics'] = diagnostics
        self.mediator.log('legal_authority_search_all', total_found=sum(len(v) for v in results.values() if isinstance(v,list)),
            context_status='unknown' if resolved == 'unknown' else 'explicit')
        return results

    def lookup_bounded_corpus(self, **kwargs: Any) -> Dict[str, Any]:
        """Bounded corpus lookup.

        This path does not add Oregon or federal fallback rows. An unavailable
        backend returns the adapter envelope so intake can continue.
        """
        try:
            envelope = lookup_bounded_legal_corpus(**kwargs)
        except Exception as exc:
            envelope = {
                'status': 'error',
                'source_family': str(kwargs.get('source_family') or ''),
                'retrieval_mode': str(kwargs.get('retrieval_mode') or ''),
                'capability': 'backend_error',
                'error_code': 'backend_error',
                'error_message': 'Legal corpus lookup failed.',
                'results': [],
                'result_count': 0,
                'bounded': True,
                'network_used': False,
                'setup_invoked': False,
                'applicability': 'unknown',
                'selected_rule_applicability': 'unknown',
            }
        if not isinstance(envelope, dict):
            envelope = {
                'status': 'error',
                'error_code': 'malformed_payload',
                'results': [],
                'result_count': 0,
                'applicability': 'unknown',
            }
        self.mediator.log(
            'legal_corpus_candidate_lookup',
            search_type=str(envelope.get('source_family') or ''),
            status=str(envelope.get('status') or ''),
            capability=str(envelope.get('capability') or ''),
            error_code=str(envelope.get('error_code') or ''),
            found=int(envelope.get('result_count') or 0),
            retrieval_mode=str(envelope.get('retrieval_mode') or ''),
        )
        return envelope

    def acquire_bounded_canonical_sources(self, binding: Any, **kwargs: Any) -> Dict[str, Any]:
        """Acquire owned source candidates. This does not initialize CommonCrawl."""
        from integrations.ipfs_datasets.legal import acquire_bounded_canonical_legal_sources

        result = acquire_bounded_canonical_legal_sources(binding, **kwargs)
        self.mediator.log(
            'legal_source_candidate_acquisition',
            status=str(result.get('status') or ''),
            error_code=str(result.get('error_code') or ''),
            found=int(result.get('result_count') or 0),
            remote_dispatched=bool(result.get('remote_dispatched')),
            model_inference_used=bool(result.get('model_inference_used')),
            commoncrawl_initialized=False,
        )
        result['commoncrawl_initialized'] = False
        result['corpus_download_started'] = False
        return result


class LegalAuthorityStorageHook(PrivateDerivedIndexMixin):
    """
    Hook for storing legal authorities in DuckDB.
    
    Manages a database of legal authorities found during research,
    indexed by case, claim type, and authority type.
    """
    
    def __init__(self, mediator, db_path: Optional[str] = None):
        self.mediator = mediator
        self.db_path = db_path or self._get_default_db_path()
        self._check_duckdb_availability()
        if DUCKDB_AVAILABLE:
            self._prepare_duckdb_path()
            self._initialize_schema()

    def _prepare_duckdb_path(self):
        """Prepare DuckDB path for connect().

        DuckDB errors if the file exists but is not a valid DuckDB database.
        Tests often pass a NamedTemporaryFile() path which is an empty file.
        Delete empty files so DuckDB can initialize the database. Filesystem
        preparation remains best-effort because ``_initialize_schema`` owns
        the connection error path, but failures are logged for diagnosis.
        """
        try:
            path = Path(self.db_path)
            if path.parent and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.is_file() and path.stat().st_size == 0:
                path.unlink()
        except OSError as exc:
            self.mediator.log(
                'legal_authority_db_path_prepare_error',
                db_path=self.db_path,
                error=str(exc),
                error_type=type(exc).__name__,
            )
    
    def _get_default_db_path(self) -> str:
        """Get default DuckDB database path."""
        state_dir = Path(__file__).parent.parent / 'statefiles'
        if not state_dir.exists():
            state_dir = Path('.')
        return str(state_dir / 'legal_authorities.duckdb')
    
    def _check_duckdb_availability(self):
        """Check if DuckDB is available."""
        if not DUCKDB_AVAILABLE:
            self.mediator.log('legal_authority_warning',
                message='DuckDB not available - legal authorities will not be persisted')
    
    def _initialize_schema(self):
        """Initialize DuckDB schema for legal authorities."""
        try:
            conn = duckdb.connect(self.db_path)
            
            # Create sequence for auto-incrementing IDs
            conn.execute("""
                CREATE SEQUENCE IF NOT EXISTS legal_authorities_id_seq START 1
            """)
            
            # Create legal_authorities table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authorities (
                    id BIGINT PRIMARY KEY DEFAULT nextval('legal_authorities_id_seq'),
                    user_id VARCHAR,
                    complaint_id VARCHAR,
                    claim_type VARCHAR,
                    authority_type VARCHAR NOT NULL,  -- statute, regulation, case_law, web_archive
                    source VARCHAR NOT NULL,          -- us_code, federal_register, recap, web
                    citation VARCHAR,                 -- Legal citation (e.g., "42 U.S.C. § 1983")
                    title TEXT,
                    content TEXT,
                    url VARCHAR,
                    metadata JSON,
                    relevance_score FLOAT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    search_query VARCHAR
                )
            """)

            _ensure_legal_authority_fact_schema(conn)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authority_chunks (
                    authority_id BIGINT,
                    chunk_id VARCHAR,
                    chunk_index INTEGER,
                    start_offset INTEGER,
                    end_offset INTEGER,
                    chunk_text TEXT,
                    metadata JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authority_graph_entities (
                    authority_id BIGINT,
                    entity_id VARCHAR,
                    entity_type VARCHAR,
                    entity_name TEXT,
                    confidence FLOAT,
                    metadata JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authority_graph_relationships (
                    authority_id BIGINT,
                    relationship_id VARCHAR,
                    source_id VARCHAR,
                    target_id VARCHAR,
                    relation_type VARCHAR,
                    confidence FLOAT,
                    metadata JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authority_treatments (
                    authority_id BIGINT,
                    treatment_id VARCHAR,
                    treatment_type VARCHAR,
                    treated_by_authority_id VARCHAR,
                    treated_by_citation VARCHAR,
                    treatment_source VARCHAR,
                    treatment_confidence FLOAT,
                    treatment_date VARCHAR,
                    treatment_explanation TEXT,
                    metadata JSON,
                    provenance JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authority_search_programs (
                    authority_id BIGINT,
                    program_id VARCHAR,
                    program_type VARCHAR,
                    claim_type VARCHAR,
                    authority_intent VARCHAR,
                    query_text TEXT,
                    claim_element_id VARCHAR,
                    claim_element_text TEXT,
                    jurisdiction VARCHAR,
                    forum VARCHAR,
                    authority_families JSON,
                    search_terms JSON,
                    metadata JSON,
                    provenance JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authority_rule_candidates (
                    authority_id BIGINT,
                    rule_id VARCHAR,
                    rule_text TEXT,
                    rule_type VARCHAR,
                    claim_element_id VARCHAR,
                    claim_element_text TEXT,
                    predicate_template VARCHAR,
                    jurisdiction VARCHAR,
                    temporal_scope VARCHAR,
                    extraction_confidence FLOAT,
                    metadata JSON,
                    provenance JSON
                )
            """)

            for statement in [
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS jurisdiction VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS source_system VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS provenance JSON",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS claim_element_id VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS claim_element TEXT",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS parse_status VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS chunk_count INTEGER",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS parsed_text_preview TEXT",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS parse_metadata JSON",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_status VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_entity_count INTEGER",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_relationship_count INTEGER",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_metadata JSON",
            ]:
                conn.execute(statement)
            
            # Create indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_authorities_user
                ON legal_authorities(user_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_authorities_claim
                ON legal_authorities(claim_type)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_authorities_citation
                ON legal_authorities(citation)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_authority_treatments_authority
                ON legal_authority_treatments(authority_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_authority_search_programs_authority
                ON legal_authority_search_programs(authority_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_authority_rule_candidates_authority
                ON legal_authority_rule_candidates(authority_id)
            """)
            
            conn.close()
            self.mediator.log('legal_authority_schema_initialized',
                db_path=self.db_path)
            
        except Exception as e:
            self.mediator.log('legal_authority_schema_error', error=str(e))

    def _parse_authority_text(self, authority: Dict[str, Any]) -> Dict[str, Any]:
        authority_metadata = authority.get('metadata', {}) if isinstance(authority.get('metadata'), dict) else {}
        content_field = ''
        authority_text = ''
        for candidate in ('content', 'text', 'html_body', 'raw_html'):
            candidate_value = str(authority.get(candidate) or '')
            if candidate_value:
                content_field = candidate
                authority_text = candidate_value
                break
        used_reference_fallback = False
        if not authority_text:
            used_reference_fallback = True
            content_field = 'citation_title_fallback'
            authority_text = '\n\n'.join(
                part for part in [authority.get('title') or '', authority.get('citation') or ''] if part
            )

        filename = str(authority.get('citation') or authority.get('title') or authority.get('url') or 'authority.txt')
        input_format = detect_document_input_format(
            text=str(authority_text),
            filename=filename,
            mime_type=str(authority_metadata.get('mime_type') or authority.get('mime_type') or ''),
        )
        mime_type_map = {
            'html': 'text/html',
            'text': 'text/plain',
            'email': 'message/rfc822',
            'rtf': 'application/rtf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'pdf': 'application/pdf',
        }

        parsed = parse_document(
            text=str(authority_text),
            filename=filename,
            mime_type=mime_type_map.get(input_format, 'text/plain'),
            source='legal_authority',
        )
        content_origin = 'authority_reference_fallback' if used_reference_fallback else 'authority_full_text'
        fallback_mode = 'citation_title_only' if used_reference_fallback else ''
        parsed = enrich_document_parse(
            parsed,
            default_source='legal_authority',
            extra_metadata={
                'content_origin': content_origin,
                'content_source_field': content_field,
                'authority_type': str(authority.get('type') or ''),
                'authority_source': str(authority.get('source') or ''),
                'citation': str(authority.get('citation') or ''),
                'title': str(authority.get('title') or ''),
                'source_url': str(authority.get('url') or ''),
                'fallback_mode': fallback_mode,
            },
            extra_lineage={
                'content_origin': content_origin,
                'content_source_field': content_field,
                'authority_type': str(authority.get('type') or ''),
                'authority_source': str(authority.get('source') or ''),
                'citation': str(authority.get('citation') or ''),
                'title': str(authority.get('title') or ''),
                'source_url': str(authority.get('url') or ''),
                'fallback_mode': fallback_mode,
            },
        )
        parse_contract = build_document_parse_contract(parsed, default_source='legal_authority')
        authority_metadata['document_parse_summary'] = parse_contract['summary']
        authority_metadata['document_parse_contract'] = parse_contract
        authority['metadata'] = authority_metadata
        return parsed

    def _build_authority_provenance_metadata(
        self,
        authority_data: Dict[str, Any],
        document_parse: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        authority_metadata = authority_data.get('metadata', {}) if isinstance(authority_data.get('metadata'), dict) else {}
        parse_contract = build_document_parse_contract(document_parse or {}, default_source='legal_authority')
        parse_lineage = parse_contract.get('lineage', {}) if isinstance(parse_contract.get('lineage'), dict) else {}
        parse_summary = parse_contract.get('summary', {}) if isinstance(parse_contract.get('summary'), dict) else {}
        content_origin = str(parse_lineage.get('content_origin') or authority_metadata.get('content_origin') or '')
        content_source_field = str(parse_lineage.get('content_source_field') or authority_metadata.get('content_source_field') or '')
        fallback_mode = str(parse_lineage.get('fallback_mode') or authority_metadata.get('fallback_mode') or '')
        metadata = {
            'corpus_family': 'legal_authority',
            'artifact_family': 'legal_authority_text' if content_origin == 'authority_full_text' else 'legal_authority_reference',
            'content_origin': content_origin,
            'content_source_field': content_source_field,
            'fallback_mode': fallback_mode,
            'text_available': content_origin == 'authority_full_text',
            'authority_type': str(authority_data.get('type') or ''),
            'authority_source': str(authority_data.get('source') or ''),
            'citation': str(authority_data.get('citation') or ''),
            'title': str(authority_data.get('title') or ''),
            'input_format': str(parse_summary.get('input_format') or parse_lineage.get('input_format') or ''),
        }
        url = str(authority_data.get('url') or '').strip()
        if url:
            metadata['source_url'] = url
        return {key: value for key, value in metadata.items() if value not in ('', None)}

    def _store_authority_chunks(self, conn, authority_id: int, document_parse: Dict[str, Any]) -> None:
        chunks = document_parse.get('chunks', []) or []
        if not chunks:
            return

        parse_contract = build_document_parse_contract(document_parse, default_source='legal_authority')
        for chunk in chunks:
            chunk_metadata = dict(chunk.get('metadata') or {})
            chunk_metadata.update({
                'length': chunk.get('length', 0),
                'parser_version': chunk_metadata.get('parser_version') or parse_contract.get('summary', {}).get('parser_version', ''),
                'source': chunk_metadata.get('source') or parse_contract.get('source', 'legal_authority'),
                'input_format': chunk_metadata.get('input_format') or parse_contract.get('summary', {}).get('input_format', ''),
            })
            page_count = int(parse_contract.get('summary', {}).get('page_count') or (1 if parse_contract.get('text') else 0))
            chunk_metadata.setdefault('page_start', 1 if page_count else 0)
            chunk_metadata.setdefault('page_end', chunk_metadata.get('page_start', 0))
            chunk_metadata.setdefault('section_label', '')
            chunk_metadata.setdefault('source_span', {
                'char_start': int(chunk.get('start', 0) or 0),
                'char_end': int(chunk.get('end', 0) or 0),
                'text_length': len(str(parse_contract.get('text') or '')),
                'page_start': int(chunk_metadata.get('page_start', 0) or 0),
                'page_end': int(chunk_metadata.get('page_end', 0) or 0),
                'page_count': page_count,
            })
            conn.execute(
                """
                INSERT INTO legal_authority_chunks (
                    authority_id, chunk_id, chunk_index, start_offset, end_offset, chunk_text, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    authority_id,
                    chunk.get('chunk_id'),
                    chunk.get('index'),
                    chunk.get('start'),
                    chunk.get('end'),
                    '' if getattr(self, '_suppress_authority_plaintext', False) else self._seal_column(chunk.get('text'), 'chunk_text'),
                    self._seal_json(_merge_intake_summary_handoff_metadata(chunk_metadata, self.mediator)),
                ],
            )

    def _store_authority_facts(
        self,
        conn,
        authority_id: int,
        graph_payload: Dict[str, Any],
        provenance,
        document_parse: Dict[str, Any],
    ) -> None:
        parse_contract = build_document_parse_contract(document_parse, default_source='legal_authority')
        chunks = [
            chunk
            for chunk in (document_parse.get('chunks', []) or [])
            if isinstance(chunk, dict)
        ]
        for entity in graph_payload.get('entities', []) or []:
            if entity.get('type') != 'fact':
                continue
            attributes = entity.get('attributes', {}) if isinstance(entity.get('attributes'), dict) else {}
            fact_text = str(attributes.get('text') or entity.get('name') or '')
            fact_chunk_lineage = self._build_fact_chunk_lineage(
                fact_text,
                int(attributes.get('sentence_index', 0) or 0),
                chunks,
            )
            fact = CaseFact(
                fact_id=str(entity.get('id') or ''),
                text=fact_text,
                source_authority_id=f'authority:{authority_id}',
                source_family='legal_authority',
                source_record_id=authority_id,
                source_ref=f'authority:{authority_id}',
                record_scope='legal_authority',
                confidence=float(entity.get('confidence', 0.0) or 0.0),
                metadata=_merge_intake_summary_handoff_metadata(
                    build_fact_lineage_metadata(
                        {
                            **attributes,
                            **fact_chunk_lineage,
                        },
                        parse_contract=parse_contract,
                        record_scope='legal_authority',
                        source_ref=f'authority:{authority_id}',
                    ),
                    self.mediator,
                ),
                provenance=_merge_handoff_into_provenance_record(provenance, self.mediator),
            )
            conn.execute(
                """
                INSERT INTO legal_authority_facts (
                    authority_id, fact_id, fact_text, source_authority_id, confidence, metadata, provenance,
                    source_family, source_record_id, source_ref, record_scope, artifact_family,
                    corpus_family, content_origin, parse_source, input_format, quality_tier,
                    quality_score, page_count, chunk_id, chunk_index, source_passage
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    authority_id,
                    fact.fact_id,
                    '' if getattr(self, '_suppress_authority_plaintext', False) else self._seal_column(fact.text, 'fact_text'),
                    fact.source_authority_id,
                    fact.confidence,
                    json.dumps(fact.metadata),
                    json.dumps(fact.provenance.as_dict()),
                    fact.source_family,
                    fact.source_record_id,
                    fact.source_ref,
                    fact.record_scope,
                    fact.artifact_family,
                    fact.corpus_family,
                    fact.content_origin,
                    fact.parse_source,
                    fact.input_format,
                    fact.quality_tier,
                    fact.quality_score,
                    fact.page_count,
                    str(fact.metadata.get('chunk_id') or ''),
                    int(fact.metadata.get('chunk_index') or 0),
                    json.dumps(fact.metadata.get('source_passage') or {}),
                ],
            )

    def _build_fact_chunk_lineage(
        self,
        fact_text: str,
        sentence_index: int,
        chunks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not chunks:
            return {
                'sentence_index': sentence_index,
                'source_passage': {
                    'chunk_id': '',
                    'chunk_index': sentence_index,
                    'start': 0,
                    'end': 0,
                    'text': _clip_source_passage_text(fact_text),
                },
            }

        normalized_fact_text = _normalize_lineage_text(fact_text)
        selected_chunk: Dict[str, Any] = {}
        for chunk in chunks:
            chunk_text = str(chunk.get('text') or '')
            normalized_chunk_text = _normalize_lineage_text(chunk_text)
            if normalized_fact_text and normalized_fact_text in normalized_chunk_text:
                selected_chunk = chunk
                break

        if not selected_chunk:
            selected_chunk = chunks[min(max(sentence_index, 0), len(chunks) - 1)]

        chunk_start = int(selected_chunk.get('start', 0) or 0)
        chunk_text = str(selected_chunk.get('text') or '')
        local_start = chunk_text.find(fact_text) if fact_text else -1
        if local_start < 0 and normalized_fact_text:
            local_start = _normalize_lineage_text(chunk_text).find(normalized_fact_text)
        absolute_start = chunk_start + local_start if local_start >= 0 else chunk_start
        absolute_end = (
            absolute_start + len(fact_text)
            if local_start >= 0 and fact_text
            else int(selected_chunk.get('end', absolute_start) or absolute_start)
        )
        passage_text = (
            chunk_text[local_start:local_start + len(fact_text)]
            if local_start >= 0 and fact_text
            else fact_text or chunk_text
        )
        source_passage = {
            'chunk_id': str(selected_chunk.get('chunk_id') or ''),
            'chunk_index': int(selected_chunk.get('index', 0) or 0),
            'start': absolute_start,
            'end': absolute_end,
            'text': _clip_source_passage_text(passage_text),
        }
        return {
            'sentence_index': sentence_index,
            'chunk_id': source_passage['chunk_id'],
            'chunk_index': source_passage['chunk_index'],
            'source_passage': source_passage,
        }

    def _extract_authority_graph(
        self,
        authority_id: int,
        authority: Dict[str, Any],
        claim_type: Optional[str],
        document_parse: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        parsed_text = ''
        if isinstance(document_parse, dict):
            parsed_text = document_parse.get('text', '') or ''
        authority_text = parsed_text or authority.get('content') or authority.get('title') or authority.get('citation') or ''
        if not authority_text:
            return {'status': 'unavailable', 'entities': [], 'relationships': [], 'metadata': {}}

        return extract_graph_from_text(
            authority_text,
            source_id=f'authority:{authority_id}',
            metadata={
                'legal_passage': True,
                'source_family': 'legal_authority',
                'record_scope': 'legal_authority',
                'artifact_family': 'legal_authority_text',
                'artifact_id': f'authority:{authority_id}',
                'title': authority.get('title', ''),
                'source_url': authority.get('url', ''),
                'claim_type': claim_type or '',
                'claim_element_id': authority.get('claim_element_id', ''),
                'claim_element_text': authority.get('claim_element', ''),
                'parse_status': document_parse.get('status', '') if isinstance(document_parse, dict) else '',
            },
        )

    def _store_authority_graph(self, conn, authority_id: int, graph_payload: Dict[str, Any]) -> None:
        for entity in graph_payload.get('entities', []) or []:
            conn.execute(
                """
                INSERT INTO legal_authority_graph_entities (
                    authority_id, entity_id, entity_type, entity_name, confidence, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    authority_id,
                    entity.get('id'),
                    entity.get('type'),
                    entity.get('name'),
                    entity.get('confidence', 0.0),
                    json.dumps(_merge_intake_summary_handoff_metadata(
                        entity.get('attributes', {}),
                        self.mediator,
                    )),
                ],
            )

        for relationship in graph_payload.get('relationships', []) or []:
            conn.execute(
                """
                INSERT INTO legal_authority_graph_relationships (
                    authority_id, relationship_id, source_id, target_id, relation_type, confidence, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    authority_id,
                    relationship.get('id'),
                    relationship.get('source_id'),
                    relationship.get('target_id'),
                    relationship.get('relation_type'),
                    relationship.get('confidence', 0.0),
                    json.dumps(_merge_intake_summary_handoff_metadata(
                        relationship.get('attributes', {}),
                        self.mediator,
                    )),
                ],
            )

    def _normalize_search_programs(self, authority_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_programs = authority_data.get('search_programs')
        if raw_programs is None:
            metadata = authority_data.get('metadata', {}) if isinstance(authority_data.get('metadata'), dict) else {}
            raw_programs = metadata.get('search_programs')

        if isinstance(raw_programs, dict):
            raw_programs = [raw_programs]
        if not isinstance(raw_programs, list):
            return []

        normalized_programs: List[Dict[str, Any]] = []
        for program in raw_programs:
            if not isinstance(program, dict):
                continue
            normalized_programs.append(
                {
                    'program_id': str(program.get('program_id') or ''),
                    'program_type': str(program.get('program_type') or ''),
                    'claim_type': str(program.get('claim_type') or ''),
                    'authority_intent': str(program.get('authority_intent') or ''),
                    'query_text': str(program.get('query_text') or ''),
                    'claim_element_id': str(program.get('claim_element_id') or ''),
                    'claim_element_text': str(program.get('claim_element_text') or ''),
                    'jurisdiction': str(program.get('jurisdiction') or ''),
                    'forum': str(program.get('forum') or ''),
                    'authority_families': list(program.get('authority_families', []) or []),
                    'search_terms': list(program.get('search_terms', []) or []),
                    'metadata': dict(program.get('metadata', {}) or {}),
                    'provenance': dict(program.get('provenance', {}) or {}),
                }
            )
        return normalized_programs

    def _build_search_program_records(
        self,
        authority_id: int,
        authority_data: Dict[str, Any],
        provenance,
        claim_type: Optional[str],
    ) -> List[LegalSearchProgram]:
        program_records: List[LegalSearchProgram] = []
        for program in self._normalize_search_programs(authority_data):
            program_type = str(program.get('program_type') or '').strip()
            query_text = str(program.get('query_text') or '').strip()
            if not program_type or not query_text:
                continue
            metadata = _merge_intake_summary_handoff_metadata(
                {
                    **(program.get('metadata', {}) if isinstance(program.get('metadata'), dict) else {}),
                    'authority_id': authority_id,
                    'authority_citation': str(authority_data.get('citation') or ''),
                    'authority_title': str(authority_data.get('title') or ''),
                    'authority_source': str(authority_data.get('source') or ''),
                    'authority_type': str(authority_data.get('type') or ''),
                },
                self.mediator,
            )
            program_records.append(
                LegalSearchProgram(
                    program_id=str(program.get('program_id') or ''),
                    program_type=program_type,
                    claim_type=str(program.get('claim_type') or claim_type or ''),
                    authority_intent=str(program.get('authority_intent') or ''),
                    query_text=query_text,
                    claim_element_id=str(program.get('claim_element_id') or ''),
                    claim_element_text=str(program.get('claim_element_text') or ''),
                    jurisdiction=str(program.get('jurisdiction') or getattr(provenance, 'jurisdiction', '') or ''),
                    forum=str(program.get('forum') or ''),
                    authority_families=list(program.get('authority_families') or []),
                    search_terms=list(program.get('search_terms') or []),
                    metadata=metadata,
                    provenance=_merge_handoff_into_provenance_record(provenance, self.mediator),
                )
            )
        return program_records

    def _store_authority_search_programs(
        self,
        conn,
        authority_id: int,
        search_programs: List[LegalSearchProgram],
    ) -> None:
        for program in search_programs:
            conn.execute(
                """
                DELETE FROM legal_authority_search_programs
                WHERE authority_id = ? AND program_id = ?
                """,
                [authority_id, program.program_id],
            )
            conn.execute(
                """
                INSERT INTO legal_authority_search_programs (
                    authority_id, program_id, program_type, claim_type, authority_intent,
                    query_text, claim_element_id, claim_element_text, jurisdiction, forum,
                    authority_families, search_terms, metadata, provenance
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    authority_id,
                    program.program_id,
                    program.program_type,
                    program.claim_type,
                    program.authority_intent,
                    program.query_text,
                    program.claim_element_id,
                    program.claim_element_text,
                    program.jurisdiction,
                    program.forum,
                    json.dumps(program.authority_families),
                    json.dumps(program.search_terms),
                    json.dumps(program.metadata),
                    json.dumps(program.provenance.as_dict()),
                ],
            )

    def _build_treatment_records(
        self,
        authority_id: int,
        authority_data: Dict[str, Any],
        provenance,
    ) -> List[AuthorityTreatmentRecord]:
        raw_records = authority_data.get('treatment_records')
        if raw_records is None:
            metadata = authority_data.get('metadata', {}) if isinstance(authority_data.get('metadata'), dict) else {}
            raw_records = metadata.get('treatment_records')

        if isinstance(raw_records, dict):
            raw_records = [raw_records]
        if not isinstance(raw_records, list):
            return []

        treatment_records: List[AuthorityTreatmentRecord] = []
        for record in raw_records:
            if not isinstance(record, dict):
                continue
            treatment_type = str(record.get('treatment_type') or record.get('type') or '').strip()
            if not treatment_type:
                continue
            metadata = _merge_intake_summary_handoff_metadata(
                dict(record.get('metadata', {}) or {}),
                self.mediator,
            )
            treatment_records.append(
                AuthorityTreatmentRecord(
                    authority_id=f'authority:{authority_id}',
                    treatment_type=treatment_type,
                    treated_by_authority_id=str(record.get('treated_by_authority_id') or ''),
                    treated_by_citation=str(record.get('treated_by_citation') or record.get('citation') or ''),
                    treatment_source=str(record.get('treatment_source') or 'authority_metadata'),
                    treatment_confidence=float(record.get('treatment_confidence', 0.0) or 0.0),
                    treatment_date=str(record.get('treatment_date') or ''),
                    treatment_explanation=str(record.get('treatment_explanation') or record.get('explanation') or ''),
                    metadata=metadata,
                    provenance=_merge_handoff_into_provenance_record(provenance, self.mediator),
                )
            )
        return treatment_records

    def _store_authority_treatments(
        self,
        conn,
        authority_id: int,
        treatment_records: List[AuthorityTreatmentRecord],
    ) -> None:
        for record in treatment_records:
            conn.execute(
                """
                DELETE FROM legal_authority_treatments
                WHERE authority_id = ? AND treatment_id = ?
                """,
                [authority_id, record.treatment_id],
            )
            conn.execute(
                """
                INSERT INTO legal_authority_treatments (
                    authority_id, treatment_id, treatment_type, treated_by_authority_id,
                    treated_by_citation, treatment_source, treatment_confidence,
                    treatment_date, treatment_explanation, metadata, provenance
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    authority_id,
                    record.treatment_id,
                    record.treatment_type,
                    record.treated_by_authority_id,
                    record.treated_by_citation,
                    record.treatment_source,
                    record.treatment_confidence,
                    record.treatment_date,
                    record.treatment_explanation,
                    json.dumps(record.metadata),
                    json.dumps(record.provenance.as_dict()),
                ],
            )

    def _split_rule_candidate_sentences(self, value: str) -> List[str]:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            return []
        parts = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
        return [part.strip() for part in parts if part and part.strip()]

    def _classify_rule_candidate_type(self, sentence: str) -> str:
        normalized = str(sentence or "").lower()
        if any(keyword in normalized for keyword in ("except", "unless", "however", "provided that")):
            return 'exception'
        if any(keyword in normalized for keyword in ("within ", "deadline", "timely", "exhaust", "notice", "venue", "filed", "preserve records", "procedure")):
            return 'procedural_prerequisite'
        if any(keyword in normalized for keyword in ("defense", "immunity", "safe harbor", "preempt")):
            return 'defense'
        if any(keyword in normalized for keyword in ("damages", "injunction", "relief", "remedy")):
            return 'remedy'
        return 'element'

    def _rule_candidate_confidence(self, sentence: str, claim_element_text: str) -> float:
        normalized = str(sentence or "").lower()
        confidence = 0.55
        if any(keyword in normalized for keyword in ("must", "shall", "required", "prohibited", "may not")):
            confidence += 0.2
        if claim_element_text and claim_element_text.lower() in normalized:
            confidence += 0.15
        if len(normalized.split()) >= 6:
            confidence += 0.05
        return min(round(confidence, 2), 0.95)

    def _build_grounded_rule_metadata(
        self,
        sentence: str,
        rule_type: str,
        *,
        authority_id: int,
        authority: Dict[str, Any],
        claim_element: Dict[str, Optional[str]],
        provenance,
        treatment_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized = str(sentence or '').lower()
        if any(marker in normalized for marker in ('may not', 'must not', 'shall not', 'prohibited', 'prohibit')):
            deontic_operator = 'prohibition'
            operator_family = 'negative_duty'
        elif any(marker in normalized for marker in ('must', 'shall', 'required', 'requires', 'within')):
            deontic_operator = 'obligation'
            operator_family = 'affirmative_duty'
        elif any(marker in normalized for marker in ('may ', 'authorized', 'permitted', 'can ')):
            deontic_operator = 'permission'
            operator_family = 'discretionary_authority'
        elif str(rule_type or '') in {'exception', 'defense'}:
            deontic_operator = 'exception'
            operator_family = 'limitation_or_defense'
        else:
            deontic_operator = 'condition'
            operator_family = 'element_or_condition'

        adverse_types = {'adverse', 'limits', 'distinguishes', 'questioned', 'superseded', 'overruled', 'reversed'}
        treatment_counts = (
            treatment_summary.get('by_type', {})
            if isinstance(treatment_summary, dict) and isinstance(treatment_summary.get('by_type'), dict)
            else {}
        )
        adverse_count = sum(int(treatment_counts.get(treatment_type, 0) or 0) for treatment_type in adverse_types)
        treatment_record_count = (
            int(treatment_summary.get('record_count', 0) or 0)
            if isinstance(treatment_summary, dict)
            else 0
        )
        max_treatment_confidence = (
            float(treatment_summary.get('max_confidence', 0.0) or 0.0)
            if isinstance(treatment_summary, dict)
            else 0.0
        )

        if adverse_count:
            treatment_influence = 'weakened'
            grounding_status = 'adverse_treatment'
        elif treatment_record_count:
            treatment_influence = 'treated'
            grounding_status = 'grounded_with_treatment'
        else:
            treatment_influence = 'untreated'
            grounding_status = 'grounded'

        return {
            'rule_id_authority_scope': f'authority:{authority_id}',
            'authority_id': f'authority:{authority_id}',
            'authority_citation': str(authority.get('citation') or ''),
            'authority_title': str(authority.get('title') or ''),
            'authority_type': str(authority.get('type') or ''),
            'authority_source': str(authority.get('source') or ''),
            'deontic_operator': deontic_operator,
            'deontic_operator_source': 'keyword_heuristic',
            'deontic_operator_is_proof': False,
            'operator_family': operator_family,
            'premise_type': 'legal_rule',
            'rule_type': str(rule_type or ''),
            'claim_element_id': str(claim_element.get('claim_element_id') or ''),
            'claim_element_text': str(claim_element.get('claim_element') or ''),
            'jurisdiction': str(getattr(provenance, 'jurisdiction', '') or ''),
            'temporal_scope': str(authority.get('metadata', {}).get('effective_date') or ''),
            # grounding_status is extraction provenance for this sentence, not
            # logical entailment and not a complete adverse-treatment analysis.
            # Downstream code must not treat it as a proof shortcut.
            'grounding_status': grounding_status,
            'grounding_status_semantics': 'extraction_provenance_not_entailment',
            'entailment_status': 'unsupported',
            'entailment_reason': 'no_bound_entailment_prover',
            'logical_entailment': False,
            'adverse_treatment_analysis': 'incomplete_heuristic',
            'treatment_influence_semantics': 'extraction_provenance_not_complete_adverse_analysis',
            'premise_failure_category': 'adverse_authority' if adverse_count else '',
            'treatment_influence': treatment_influence,
            'adverse_treatment_count': adverse_count,
            'treatment_record_count': treatment_record_count,
            'max_treatment_confidence': max_treatment_confidence,
        }

    def _extract_rule_candidates(
        self,
        authority_id: int,
        authority: Dict[str, Any],
        claim_type: Optional[str],
        document_parse: Dict[str, Any],
        provenance,
        claim_element: Dict[str, Optional[str]],
    ) -> List[RuleCandidate]:
        parsed_text = str((document_parse or {}).get('text') or '')
        chunks = (document_parse or {}).get('chunks', []) or []
        parse_contract = build_document_parse_contract(document_parse or {}, default_source='legal_authority')
        base_lineage_metadata = build_fact_lineage_metadata(
            {},
            parse_contract=parse_contract,
            record_scope='legal_authority',
            source_ref=f'authority:{authority_id}',
        )
        candidate_rows: List[Dict[str, Any]] = []

        if chunks:
            for chunk in chunks:
                if not isinstance(chunk, dict):
                    continue
                chunk_text = str(chunk.get('text') or '')
                chunk_start = int(chunk.get('start', 0) or 0)
                for sentence in self._split_rule_candidate_sentences(chunk_text):
                    local_start = chunk_text.find(sentence)
                    absolute_start = chunk_start + local_start if local_start >= 0 else chunk_start
                    absolute_end = absolute_start + len(sentence)
                    candidate_rows.append(
                        {
                            'text': sentence,
                            'chunk_id': str(chunk.get('chunk_id') or ''),
                            'chunk_index': int(chunk.get('index', 0) or 0),
                            'start': absolute_start,
                            'end': absolute_end,
                            'source_passage': {
                                'chunk_id': str(chunk.get('chunk_id') or ''),
                                'chunk_index': int(chunk.get('index', 0) or 0),
                                'start': absolute_start,
                                'end': absolute_end,
                                'text': _clip_source_passage_text(sentence),
                            },
                        }
                    )
        else:
            search_start = 0
            for index, sentence in enumerate(self._split_rule_candidate_sentences(parsed_text)):
                local_start = parsed_text.find(sentence, search_start)
                absolute_start = local_start if local_start >= 0 else 0
                absolute_end = absolute_start + len(sentence)
                search_start = absolute_end
                candidate_rows.append(
                    {
                        'text': sentence,
                        'chunk_id': '',
                        'chunk_index': index,
                        'start': absolute_start,
                        'end': absolute_end,
                        'source_passage': {
                            'chunk_id': '',
                            'chunk_index': index,
                            'start': absolute_start,
                            'end': absolute_end,
                            'text': _clip_source_passage_text(sentence),
                        },
                    }
                )

        rule_candidates: List[RuleCandidate] = []
        seen_rule_texts = set()
        for row in candidate_rows:
            sentence = str(row.get('text') or '').strip()
            if len(sentence.split()) < 4:
                continue
            normalized_text = sentence.lower()
            if normalized_text in seen_rule_texts:
                continue
            seen_rule_texts.add(normalized_text)

            rule_type = self._classify_rule_candidate_type(sentence)
            claim_element_text = str(claim_element.get('claim_element') or '')
            predicate_template = claim_element_text or str(claim_type or '')
            grounded_rule = self._build_grounded_rule_metadata(
                sentence,
                rule_type,
                authority_id=authority_id,
                authority=authority,
                claim_element=claim_element,
                provenance=provenance,
            )
            rule_candidates.append(
                RuleCandidate(
                    authority_id=f'authority:{authority_id}',
                    rule_text=sentence,
                    rule_type=rule_type,
                    claim_element_id=str(claim_element.get('claim_element_id') or ''),
                    claim_element_text=claim_element_text,
                    predicate_template=predicate_template,
                    jurisdiction=str(provenance.jurisdiction or ''),
                    temporal_scope=str(authority.get('metadata', {}).get('effective_date') or ''),
                    extraction_confidence=self._rule_candidate_confidence(sentence, claim_element_text),
                    metadata=_merge_intake_summary_handoff_metadata(
                        {
                            **base_lineage_metadata,
                            'chunk_id': row.get('chunk_id', ''),
                            'chunk_index': row.get('chunk_index', 0),
                            'source_span': {
                                'start': row.get('start', 0),
                                'end': row.get('end', 0),
                            },
                            'source_passage': row.get('source_passage', {}),
                            'claim_type': claim_type or '',
                            'authority_type': authority.get('type', ''),
                            'authority_source': authority.get('source', ''),
                            'grounded_rule': grounded_rule,
                        },
                        self.mediator,
                    ),
                    provenance=_merge_handoff_into_provenance_record(provenance, self.mediator),
                )
            )

        return rule_candidates[:25]

    def _store_authority_rule_candidates(
        self,
        conn,
        authority_id: int,
        rule_candidates: List[RuleCandidate],
    ) -> None:
        for record in rule_candidates:
            conn.execute(
                "DELETE FROM legal_authority_rule_candidates WHERE authority_id = ? AND rule_id = ?",
                [authority_id, record.rule_id],
            )
            conn.execute(
                """
                INSERT INTO legal_authority_rule_candidates (
                    authority_id, rule_id, rule_text, rule_type, claim_element_id,
                    claim_element_text, predicate_template, jurisdiction, temporal_scope,
                    extraction_confidence, metadata, provenance
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    authority_id,
                    record.rule_id,
                    record.rule_text,
                    record.rule_type,
                    record.claim_element_id,
                    record.claim_element_text,
                    record.predicate_template,
                    record.jurisdiction,
                    record.temporal_scope,
                    record.extraction_confidence,
                    json.dumps(record.metadata),
                    json.dumps(record.provenance.as_dict()),
                ],
            )

    def _get_authority_treatments(self, conn, authority_id: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT treatment_id, treatment_type, treated_by_authority_id, treated_by_citation,
                   treatment_source, treatment_confidence, treatment_date, treatment_explanation,
                   metadata, provenance
            FROM legal_authority_treatments
            WHERE authority_id = ?
            ORDER BY treatment_confidence DESC, treatment_id ASC
            """,
            [authority_id],
        ).fetchall()
        return [
            {
                'treatment_id': row[0],
                'treatment_type': row[1],
                'treated_by_authority_id': row[2],
                'treated_authority_id': row[2],
                'target_authority_id': row[2],
                'treated_by_citation': row[3],
                'target_citation': row[3],
                'treatment_source': row[4],
                'treatment_confidence': row[5] or 0.0,
                'treatment_date': row[6] or '',
                'treatment_explanation': row[7] or '',
                'metadata': json.loads(row[8]) if row[8] else {},
                'provenance': json.loads(row[9]) if row[9] else {},
            }
            for row in rows
        ]

    def _get_authority_search_programs(self, conn, authority_id: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT program_id, program_type, claim_type, authority_intent, query_text,
                   claim_element_id, claim_element_text, jurisdiction, forum,
                   authority_families, search_terms, metadata, provenance
            FROM legal_authority_search_programs
            WHERE authority_id = ?
            ORDER BY program_type ASC, program_id ASC
            """,
            [authority_id],
        ).fetchall()
        return [
            {
                'program_id': row[0],
                'program_type': row[1],
                'claim_type': row[2],
                'authority_intent': row[3],
                'query_text': row[4],
                'claim_element_id': row[5],
                'claim_element_text': row[6],
                'jurisdiction': row[7],
                'forum': row[8],
                'authority_families': json.loads(row[9]) if row[9] else [],
                'search_terms': json.loads(row[10]) if row[10] else [],
                'metadata': json.loads(row[11]) if row[11] else {},
                'provenance': json.loads(row[12]) if row[12] else {},
            }
            for row in rows
        ]

    def _get_authority_rule_candidates(self, conn, authority_id: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT rule_id, rule_text, rule_type, claim_element_id, claim_element_text,
                   predicate_template, jurisdiction, temporal_scope, extraction_confidence,
                   metadata, provenance
            FROM legal_authority_rule_candidates
            WHERE authority_id = ?
            ORDER BY extraction_confidence DESC, rule_id ASC
            """,
            [authority_id],
        ).fetchall()
        candidates: List[Dict[str, Any]] = []
        for row in rows:
            metadata = json.loads(row[9]) if row[9] else {}
            grounded_rule = metadata.get('grounded_rule', {}) if isinstance(metadata, dict) else {}
            source_passage = metadata.get('source_passage', {}) if isinstance(metadata, dict) else {}
            parse_lineage = metadata.get('parse_lineage', {}) if isinstance(metadata, dict) else {}
            record = {
                'rule_id': row[0],
                'rule_text': row[1],
                'rule_type': row[2],
                'claim_element_id': row[3],
                'claim_element_text': row[4],
                'predicate_template': row[5],
                'jurisdiction': row[6],
                'temporal_scope': row[7],
                'extraction_confidence': row[8] or 0.0,
                'metadata': metadata,
                'grounded_rule': grounded_rule if isinstance(grounded_rule, dict) else {},
                'source_passage': source_passage if isinstance(source_passage, dict) else {},
                'parse_lineage': parse_lineage if isinstance(parse_lineage, dict) else {},
                'provenance': json.loads(row[10]) if row[10] else {},
            }
            candidates.append(record)
        return candidates

    def _build_treatment_summary(self, treatment_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        max_confidence = 0.0
        for record in treatment_records:
            treatment_type = str(record.get('treatment_type') or '')
            if treatment_type:
                counts[treatment_type] = counts.get(treatment_type, 0) + 1
            max_confidence = max(max_confidence, float(record.get('treatment_confidence', 0.0) or 0.0))
        return {
            'record_count': len(treatment_records),
            'by_type': counts,
            'max_confidence': max_confidence,
        }

    def _build_citation_history_summary(self, treatment_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        related_authority_ids = set()
        related_citations = set()
        treatment_dates: List[str] = []
        source_counts: Dict[str, int] = {}
        for record in treatment_records:
            related_id = str(
                record.get('treated_by_authority_id')
                or record.get('treated_authority_id')
                or record.get('target_authority_id')
                or ''
            ).strip()
            if related_id:
                related_authority_ids.add(related_id)
            related_citation = str(
                record.get('treated_by_citation')
                or record.get('target_citation')
                or ''
            ).strip()
            if related_citation:
                related_citations.add(related_citation)
            treatment_date = str(record.get('treatment_date') or '').strip()
            if treatment_date:
                treatment_dates.append(treatment_date)
            source = str(record.get('treatment_source') or '').strip()
            if source:
                source_counts[source] = source_counts.get(source, 0) + 1

        treatment_dates.sort()
        return {
            'record_count': len(treatment_records),
            'related_authority_count': len(related_authority_ids),
            'related_citation_count': len(related_citations),
            'related_authority_ids': sorted(related_authority_ids),
            'related_citations': sorted(related_citations),
            'earliest_treatment_date': treatment_dates[0] if treatment_dates else '',
            'latest_treatment_date': treatment_dates[-1] if treatment_dates else '',
            'source_counts': source_counts,
        }

    def _build_authority_treatment_edges(
        self,
        authority_record: Dict[str, Any],
        treatment_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        target_authority_id = str(authority_record.get('authority_id') or f"authority:{authority_record.get('id', '')}").strip()
        target_citation = str(authority_record.get('citation') or '').strip()
        edges: List[Dict[str, Any]] = []
        for record in treatment_records:
            if not isinstance(record, dict):
                continue
            relation_type = str(record.get('treatment_type') or '').strip()
            if not relation_type:
                continue
            metadata = dict(record.get('metadata') or {})
            metadata.update({
                'source_record_treatment_id': str(record.get('treatment_id') or ''),
                'source_record_authority_id': str(authority_record.get('id') or ''),
            })
            edge = AuthorityTreatmentEdge(
                edge_id=str(record.get('treatment_id') or ''),
                source_authority_id=str(record.get('treated_by_authority_id') or ''),
                source_citation=str(record.get('treated_by_citation') or ''),
                target_authority_id=target_authority_id,
                target_citation=target_citation,
                relation_type=relation_type,
                confidence=float(record.get('treatment_confidence', 0.0) or 0.0),
                treatment_source=str(record.get('treatment_source') or ''),
                treatment_date=str(record.get('treatment_date') or ''),
                explanation=str(record.get('treatment_explanation') or ''),
                metadata=metadata,
                # This is a stored ProvenanceRecord, including its separate
                # assertion envelope, rather than input to the source builder.
                provenance=ProvenanceRecord(**(record.get('provenance') or {})),
            ).as_dict()
            edges.append(edge)
        return edges

    def _build_search_program_summary(self, search_programs: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        by_intent: Dict[str, int] = {}
        claim_element_ids = set()
        for record in search_programs:
            program_type = str(record.get('program_type') or '')
            if program_type:
                by_type[program_type] = by_type.get(program_type, 0) + 1
            authority_intent = str(record.get('authority_intent') or '')
            if authority_intent:
                by_intent[authority_intent] = by_intent.get(authority_intent, 0) + 1
            claim_element_id = str(record.get('claim_element_id') or '')
            if claim_element_id:
                claim_element_ids.add(claim_element_id)
        return {
            'record_count': len(search_programs),
            'by_type': by_type,
            'by_intent': by_intent,
            'claim_element_count': len(claim_element_ids),
        }

    def _build_rule_candidate_summary(self, rule_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        deontic_counts: Dict[str, int] = {}
        operator_family_counts: Dict[str, int] = {}
        grounding_status_counts: Dict[str, int] = {}
        adverse_treatment_count = 0
        max_confidence = 0.0
        for record in rule_candidates:
            rule_type = str(record.get('rule_type') or '')
            if rule_type:
                counts[rule_type] = counts.get(rule_type, 0) + 1
            grounded_rule = record.get('grounded_rule', {}) if isinstance(record.get('grounded_rule'), dict) else {}
            deontic_operator = str(grounded_rule.get('deontic_operator') or '')
            if deontic_operator:
                deontic_counts[deontic_operator] = deontic_counts.get(deontic_operator, 0) + 1
            operator_family = str(grounded_rule.get('operator_family') or '')
            if operator_family:
                operator_family_counts[operator_family] = operator_family_counts.get(operator_family, 0) + 1
            grounding_status = str(grounded_rule.get('grounding_status') or '')
            if grounding_status:
                grounding_status_counts[grounding_status] = grounding_status_counts.get(grounding_status, 0) + 1
            adverse_treatment_count += int(grounded_rule.get('adverse_treatment_count', 0) or 0)
            max_confidence = max(max_confidence, float(record.get('extraction_confidence', 0.0) or 0.0))
        return {
            'record_count': len(rule_candidates),
            'by_type': counts,
            'by_deontic_operator': deontic_counts,
            'by_operator_family': operator_family_counts,
            'by_grounding_status': grounding_status_counts,
            'adverse_treatment_count': adverse_treatment_count,
            'max_confidence': max_confidence,
        }

    def _attach_treatment_payloads(self, conn, record: Dict[str, Any]) -> Dict[str, Any]:
        search_programs = self._get_authority_search_programs(conn, record['id'])
        record['search_programs'] = search_programs
        record['search_program_summary'] = self._build_search_program_summary(search_programs)
        treatment_records = self._get_authority_treatments(conn, record['id'])
        record['treatment_records'] = treatment_records
        record['authority_treatment_edges'] = self._build_authority_treatment_edges(record, treatment_records)
        record['treatment_summary'] = self._build_treatment_summary(treatment_records)
        record['citation_history_summary'] = self._build_citation_history_summary(treatment_records)
        rule_candidates = self._get_authority_rule_candidates(conn, record['id'])
        for candidate in rule_candidates:
            grounded_rule = candidate.get('grounded_rule', {})
            if not isinstance(grounded_rule, dict):
                grounded_rule = {}
            grounded_rule = {
                **grounded_rule,
                **self._build_grounded_rule_metadata(
                    str(candidate.get('rule_text') or ''),
                    str(candidate.get('rule_type') or ''),
                    authority_id=record['id'],
                    authority=record,
                    claim_element={
                        'claim_element_id': str(candidate.get('claim_element_id') or ''),
                        'claim_element': str(candidate.get('claim_element_text') or ''),
                    },
                    provenance=type('ProvenanceView', (), {'jurisdiction': candidate.get('jurisdiction') or ''})(),
                    treatment_summary=record['treatment_summary'],
                ),
            }
            candidate['grounded_rule'] = grounded_rule
            if isinstance(candidate.get('metadata'), dict):
                candidate['metadata']['grounded_rule'] = grounded_rule
        record['rule_candidates'] = rule_candidates
        record['rule_candidate_summary'] = self._build_rule_candidate_summary(rule_candidates)
        return record

    def _authority_record_from_row(self, row, *, include_claim_type: bool = False) -> Dict[str, Any]:
        offset = 1 if include_claim_type else 0
        record = {
            'id': row[0],
            'type': row[1 + offset],
            'source': row[2 + offset],
            'citation': row[3 + offset],
            'title': row[4 + offset],
            'content': row[5 + offset],
            'url': row[6 + offset],
            'metadata': json.loads(row[7 + offset]) if row[7 + offset] else {},
            'relevance_score': row[8 + offset],
            'timestamp': row[9 + offset],
            'jurisdiction': row[10 + offset],
            'source_system': row[11 + offset],
            'provenance': json.loads(row[12 + offset]) if row[12 + offset] else {},
            'claim_element_id': row[13 + offset],
            'claim_element': row[14 + offset],
            'parse_status': row[15 + offset],
            'chunk_count': row[16 + offset] or 0,
            'parsed_text_preview': row[17 + offset] or '',
            'parse_metadata': json.loads(row[18 + offset]) if row[18 + offset] else {},
            'graph_status': row[19 + offset],
            'graph_entity_count': row[20 + offset] or 0,
            'graph_relationship_count': row[21 + offset] or 0,
            'graph_metadata': json.loads(row[22 + offset]) if row[22 + offset] else {},
            'fact_count': row[23 + offset] or 0,
        }
        if include_claim_type:
            record['claim_type'] = row[1]
        return record

    def _resolve_claim_element(
        self,
        user_id: str,
        claim_type: Optional[str],
        authority_data: Dict[str, Any],
    ) -> Dict[str, Optional[str]]:
        claim_support = getattr(self.mediator, 'claim_support', None)
        if not claim_type or claim_support is None:
            return {
                'claim_element_id': authority_data.get('claim_element_id'),
                'claim_element': authority_data.get('claim_element'),
            }

        metadata = authority_data.get('metadata', {})
        if not isinstance(metadata, dict):
            metadata = {}
        resolution = claim_support.resolve_claim_element(
            user_id,
            claim_type,
            claim_element_text=authority_data.get('claim_element'),
            support_label=authority_data.get('title') or authority_data.get('citation'),
            metadata={
                **metadata,
                'title': authority_data.get('title'),
                'description': authority_data.get('content') or authority_data.get('text'),
                'summary': authority_data.get('summary'),
                'content_excerpt': authority_data.get('content') or authority_data.get('text'),
                'source_url': authority_data.get('url'),
            },
        )
        if not isinstance(resolution, dict):
            resolution = {}
        return {
            'claim_element_id': authority_data.get('claim_element_id') or resolution.get('claim_element_id'),
            'claim_element': authority_data.get('claim_element') or resolution.get('claim_element_text'),
        }

    def _find_existing_authority_record(
        self,
        conn,
        user_id: str,
        complaint_id: Optional[str],
        claim_type: Optional[str],
        authority: Dict[str, Any],
    ) -> Optional[int]:
        citation = authority.get('citation')
        url = authority.get('url')
        title = authority.get('title')
        authority_type = authority.get('type')
        source = authority.get('source')
        claim_element_id = authority.get('claim_element_id')

        if citation:
            existing = conn.execute(
                """
                SELECT id
                FROM legal_authorities
                WHERE user_id = ?
                  AND citation = ?
                  AND COALESCE(complaint_id, '') = COALESCE(?, '')
                  AND COALESCE(claim_type, '') = COALESCE(?, '')
                  AND COALESCE(claim_element_id, '') = COALESCE(?, '')
                ORDER BY id ASC
                LIMIT 1
                """,
                [user_id, citation, complaint_id, claim_type, claim_element_id],
            ).fetchone()
            if existing:
                return existing[0]

        if url:
            existing = conn.execute(
                """
                SELECT id
                FROM legal_authorities
                WHERE user_id = ?
                  AND url = ?
                  AND COALESCE(complaint_id, '') = COALESCE(?, '')
                  AND COALESCE(claim_type, '') = COALESCE(?, '')
                  AND COALESCE(claim_element_id, '') = COALESCE(?, '')
                ORDER BY id ASC
                LIMIT 1
                """,
                [user_id, url, complaint_id, claim_type, claim_element_id],
            ).fetchone()
            if existing:
                return existing[0]

        if authority_type and source and title:
            existing = conn.execute(
                """
                SELECT id
                FROM legal_authorities
                WHERE user_id = ?
                  AND authority_type = ?
                  AND source = ?
                  AND title = ?
                  AND COALESCE(complaint_id, '') = COALESCE(?, '')
                  AND COALESCE(claim_type, '') = COALESCE(?, '')
                  AND COALESCE(claim_element_id, '') = COALESCE(?, '')
                ORDER BY id ASC
                LIMIT 1
                """,
                [user_id, authority_type, source, title, complaint_id, claim_type, claim_element_id],
            ).fetchone()
            if existing:
                return existing[0]

        return None
    
    def store_acquired_authority(self, authority_data: Dict[str, Any],
                                user_id: str, complaint_id: Optional[str] = None,
                                claim_type: Optional[str] = None) -> Dict[str, Any]:
        """Store one canonical acquired record through upsert_authority.

        Caller verification flags are refused here. This method does not add
        dependency-graph nodes and does not treat storage as proof.
        """
        refused = {'record_id': -1, 'created': False, 'reused': False, 'status': 'rejected'}
        if not isinstance(authority_data, dict):
            return dict(refused, reason='malformed_record')
        metadata = authority_data.get('metadata') if isinstance(authority_data.get('metadata'), dict) else {}
        for key in ('verified', 'applicable', 'support_eligible', 'promoted', 'proof'):
            if authority_data.get(key) is True or metadata.get(key) is True:
                return dict(refused, reason='caller_verification_flag')
        content = authority_data.get('content')
        if not isinstance(content, str) or not content:
            return dict(refused, reason='source_text_missing')
        for key in ('source_text', 'text', 'source_passage'):
            alternate = metadata.get(key)
            if isinstance(alternate, str) and alternate and alternate != content:
                return dict(refused, reason='substituted_metadata_text')
        result = self.upsert_authority(
            authority_data,
            user_id,
            complaint_id=complaint_id,
            claim_type=claim_type,
            search_query=None,
        )
        stored = dict(result)
        if stored.get('record_id') in (None, -1):
            stored['status'] = 'unavailable'
            stored['reason'] = 'storage_unavailable'
        else:
            stored['status'] = 'stored'
            stored['reason'] = 'upsert_authority'
        return stored

    def add_authority(self, authority_data: Dict[str, Any],
                     user_id: str, complaint_id: Optional[str] = None,
                     claim_type: Optional[str] = None,
                     search_query: Optional[str] = None) -> int:
        result = self.upsert_authority(
            authority_data,
            user_id,
            complaint_id=complaint_id,
            claim_type=claim_type,
            search_query=search_query,
        )
        return result['record_id']

    def upsert_authority(self, authority_data: Dict[str, Any],
                        user_id: str, complaint_id: Optional[str] = None,
                        claim_type: Optional[str] = None,
                        search_query: Optional[str] = None) -> Dict[str, Any]:
        """
        Add a legal authority to the database.
        
        Args:
            authority_data: Authority information from search
            user_id: User identifier
            complaint_id: Optional complaint ID
            claim_type: Optional claim type
            search_query: Original search query
            
        Returns:
            Dictionary describing whether the authority was newly inserted or reused.
        """
        if not DUCKDB_AVAILABLE:
            self.mediator.log('legal_authority_storage_unavailable')
            return {'record_id': -1, 'created': False, 'reused': False}
        
        try:
            conn = duckdb.connect(self.db_path)
            claim_element = self._resolve_claim_element(user_id, claim_type, authority_data)
            document_parse = self._parse_authority_text(authority_data)
            parse_contract = build_document_parse_contract(document_parse, default_source='legal_authority')
            parse_storage_metadata = _merge_intake_summary_handoff_metadata(
                parse_contract.get('storage_metadata', {}),
                self.mediator,
            )
            parsed_text = parse_contract.get('text', '')
            parsed_text_preview = parse_contract.get('text_preview', '')
            authority_record_metadata = _merge_intake_summary_handoff_metadata(
                {
                    **(authority_data.get('metadata', {}) if isinstance(authority_data.get('metadata', {}), dict) else {}),
                    'claim_element_id': claim_element.get('claim_element_id'),
                    'claim_element': claim_element.get('claim_element'),
                    'search_programs': self._normalize_search_programs(authority_data),
                },
                self.mediator,
            )
            provenance = build_provenance(
                source_url=str(authority_data.get('url', '')),
                acquisition_method='legal_search',
                source_type=str(authority_data.get('type', 'unknown')),
                acquired_at=datetime.now().isoformat(),
                source_system=str(authority_data.get('source', 'unknown')),
                jurisdiction=str(authority_data.get('jurisdiction', '')),
                metadata=_merge_intake_summary_handoff_metadata(
                    self._build_authority_provenance_metadata(authority_data, document_parse),
                    self.mediator,
                ),
            )
            authority = CaseAuthority(
                authority_type=authority_data.get('type', 'unknown'),
                source=authority_data.get('source', 'unknown'),
                citation=authority_data.get('citation') or '',
                title=authority_data.get('title') or '',
                content=(
                    authority_data.get('content')
                    or authority_data.get('text')
                    or authority_data.get('html_body')
                    or authority_data.get('raw_html')
                    or ''
                ),
                url=authority_data.get('url') or '',
                jurisdiction=provenance.jurisdiction,
                source_system=provenance.source_system,
                claim_element_id=claim_element.get('claim_element_id') or '',
                claim_element=claim_element.get('claim_element') or '',
                relevance_score=authority_data.get('relevance_score', 0.5),
                metadata=authority_record_metadata,
                provenance=provenance,
            )
            normalized_authority = authority.as_dict()

            existing_record_id = self._find_existing_authority_record(
                conn,
                user_id,
                complaint_id,
                claim_type,
                normalized_authority,
            )
            if existing_record_id is not None:
                self._store_authority_search_programs(
                    conn,
                    existing_record_id,
                    self._build_search_program_records(existing_record_id, authority_data, provenance, claim_type),
                )
                self._store_authority_treatments(
                    conn,
                    existing_record_id,
                    self._build_treatment_records(existing_record_id, authority_data, provenance),
                )
                self._store_authority_rule_candidates(
                    conn,
                    existing_record_id,
                    self._extract_rule_candidates(
                        existing_record_id,
                        normalized_authority,
                        claim_type,
                        document_parse,
                        provenance,
                        claim_element,
                    ),
                )
                conn.close()
                self.mediator.log(
                    'legal_authority_duplicate',
                    record_id=existing_record_id,
                    citation=normalized_authority.get('citation'),
                    url=normalized_authority.get('url'),
                    claim_type=claim_type,
                    claim_element_id=normalized_authority.get('claim_element_id'),
                )
                return {'record_id': existing_record_id, 'created': False, 'reused': True}

            stored_content = normalized_authority.get('content')
            stored_preview = parsed_text_preview
            stored_title = normalized_authority.get('title')
            stored_claim_element = claim_element.get('claim_element')
            authority_meta = authority_data.get('metadata') if isinstance(authority_data.get('metadata'), dict) else {}
            is_public_law = (
                authority_data.get('storage_class') == 'public_legal_corpus'
                or authority_data.get('classification') == 'public_legal_corpus'
                or authority_meta.get('storage_class') == 'public_legal_corpus'
            )
            if is_public_law and self._private_columns_sealed():
                cached = self.cache_public_law_source(
                    citation=str(normalized_authority.get('citation') or ''),
                    text=str(stored_content or stored_preview or ''),
                )
                authority_record_metadata = dict(authority_record_metadata)
                authority_record_metadata['public_cache_id'] = cached['cache_id']
                authority_record_metadata['storage_class'] = 'public_legal_corpus'
                stored_content = ''
                stored_preview = ''
            if self._private_columns_sealed() and not is_public_law:
                stored_content = self._seal_column(stored_content, 'content')
                stored_preview = self._seal_column(stored_preview, 'parsed_text_preview')
                stored_title = self._seal_column(stored_title, 'title')
            if self._private_columns_sealed():
                stored_claim_element = self._seal_column(stored_claim_element, 'claim_element')
                search_query = self._seal_column(search_query, 'search_query')

            result = conn.execute("""
                INSERT INTO legal_authorities (
                    user_id, complaint_id, claim_type, authority_type,
                    source, citation, title, content, url, metadata,
                    relevance_score, search_query, jurisdiction,
                    source_system, provenance, claim_element_id, claim_element,
                    parse_status, chunk_count, parsed_text_preview, parse_metadata,
                    graph_status, graph_entity_count, graph_relationship_count, graph_metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, [
                user_id,
                complaint_id,
                claim_type,
                normalized_authority.get('type', 'unknown'),
                normalized_authority.get('source', 'unknown'),
                normalized_authority.get('citation'),
                stored_title,
                stored_content,
                normalized_authority.get('url'),
                self._seal_json(authority_record_metadata),
                normalized_authority.get('relevance_score', 0.5),
                search_query,
                provenance.jurisdiction,
                provenance.source_system,
                self._seal_json(provenance.as_dict()),
                claim_element.get('claim_element_id'),
                stored_claim_element,
                parse_contract.get('status'),
                parse_contract.get('chunk_count', 0),
                stored_preview,
                self._seal_json(parse_storage_metadata),
                None,
                0,
                0,
                json.dumps({}),
            ]).fetchone()
            
            record_id = result[0]
            graph_payload = self._extract_authority_graph(
                record_id,
                normalized_authority,
                claim_type,
                document_parse=document_parse,
            )
            graph_snapshot_scope = '|'.join(
                [
                    str(Path(self.db_path).resolve()),
                    str(user_id or ''),
                    str(complaint_id or ''),
                    str(record_id),
                ]
            )
            conn.execute(
                """
                UPDATE legal_authorities
                SET graph_status = ?,
                    graph_entity_count = ?,
                    graph_relationship_count = ?,
                    graph_metadata = ?
                WHERE id = ?
                """,
                [
                    graph_payload.get('status'),
                    len(graph_payload.get('entities', []) or []),
                    len(graph_payload.get('relationships', []) or []),
                    json.dumps({
                        **(graph_payload.get('metadata', {}) or {}),
                        'graph_snapshot': persist_graph_snapshot(
                            graph_payload,
                            graph_id=f"legal-authority-record:{hashlib.sha256(graph_snapshot_scope.encode('utf-8')).hexdigest()[:16]}",
                            graph_changed=bool(graph_payload.get('entities') or graph_payload.get('relationships')),
                            existing_graph=False,
                            persistence_metadata=_merge_intake_summary_handoff_metadata(
                                {
                                    'record_scope': 'legal_authority',
                                    'record_key': str(record_id),
                                },
                                self.mediator,
                            ),
                        ),
                    }),
                    record_id,
                ],
            )
            self._suppress_authority_plaintext = bool(is_public_law and self._private_columns_sealed())
            self._store_authority_chunks(conn, record_id, document_parse)
            self._store_authority_graph(conn, record_id, graph_payload)
            self._store_authority_facts(
                conn,
                record_id,
                graph_payload,
                provenance,
                document_parse,
            )
            self._suppress_authority_plaintext = False
            self._store_authority_search_programs(
                conn,
                record_id,
                self._build_search_program_records(record_id, authority_data, provenance, claim_type),
            )
            self._store_authority_treatments(
                conn,
                record_id,
                self._build_treatment_records(record_id, authority_data, provenance),
            )
            self._store_authority_rule_candidates(
                conn,
                record_id,
                self._extract_rule_candidates(
                    record_id,
                    normalized_authority,
                    claim_type,
                    document_parse,
                    provenance,
                    claim_element,
                ),
            )
            conn.close()
            
            self.mediator.log('legal_authority_added',
                record_id=record_id, citation=authority_data.get('citation'))
            
            return {'record_id': record_id, 'created': True, 'reused': False}
            
        except Exception as e:
            self.mediator.log('legal_authority_storage_error', error=str(e))
            raise Exception(f'Failed to store legal authority: {str(e)}')
    
    def add_authorities_bulk(self, authorities: List[Dict[str, Any]],
                            user_id: str, complaint_id: Optional[str] = None,
                            claim_type: Optional[str] = None,
                            search_query: Optional[str] = None) -> List[int]:
        """
        Add multiple legal authorities at once.
        
        Args:
            authorities: List of authority dictionaries
            user_id: User identifier
            complaint_id: Optional complaint ID
            claim_type: Optional claim type
            search_query: Original search query
            
        Returns:
            List of record IDs
        """
        record_ids = []
        for authority in authorities:
            try:
                record_id = self.add_authority(
                    authority, user_id, complaint_id, claim_type, search_query
                )
                record_ids.append(record_id)
            except Exception as e:
                self.mediator.log('legal_authority_bulk_error',
                    error=str(e), authority=authority.get('citation'))
        
        return record_ids
    
    def get_authorities_by_claim(self, user_id: str, claim_type: str) -> List[Dict[str, Any]]:
        """
        Get all authorities for a specific claim type.
        
        Args:
            user_id: User identifier
            claim_type: Claim type
            
        Returns:
            List of authority records
        """
        if not DUCKDB_AVAILABLE:
            return []
        
        try:
            conn = duckdb.connect(self.db_path)
            
            results = conn.execute("""
                SELECT id, authority_type, source, citation, title,
                      content, url, metadata, relevance_score, timestamp,
                        jurisdiction, source_system, provenance, claim_element_id, claim_element,
                                                parse_status, chunk_count, parsed_text_preview, parse_metadata,
                                                graph_status, graph_entity_count, graph_relationship_count, graph_metadata,
                      (
                          SELECT COUNT(*) FROM legal_authority_facts laf WHERE laf.authority_id = legal_authorities.id
                      ) AS fact_count
                FROM legal_authorities
                WHERE user_id = ? AND claim_type = ?
                ORDER BY relevance_score DESC, timestamp DESC
            """, [user_id, claim_type]).fetchall()
            
            records = [self._authority_record_from_row(row) for row in results]
            records = [self._attach_treatment_payloads(conn, record) for record in records]
            conn.close()
            
            return records
            
        except Exception as e:
            self.mediator.log('legal_authority_query_error', error=str(e))
            return []
    
    def get_all_authorities(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all authorities for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of all authority records
        """
        if not DUCKDB_AVAILABLE:
            return []
        
        try:
            conn = duckdb.connect(self.db_path)
            
            results = conn.execute("""
                SELECT id, claim_type, authority_type, source, citation,
                      title, content, url, metadata, relevance_score, timestamp,
                        jurisdiction, source_system, provenance, claim_element_id, claim_element,
                                                parse_status, chunk_count, parsed_text_preview, parse_metadata,
                                                graph_status, graph_entity_count, graph_relationship_count, graph_metadata,
                      (
                          SELECT COUNT(*) FROM legal_authority_facts laf WHERE laf.authority_id = legal_authorities.id
                      ) AS fact_count
                FROM legal_authorities
                WHERE user_id = ?
                ORDER BY timestamp DESC
            """, [user_id]).fetchall()
            
            records = [self._authority_record_from_row(row, include_claim_type=True) for row in results]
            records = [self._attach_treatment_payloads(conn, record) for record in records]
            conn.close()
            
            return records
            
        except Exception as e:
            self.mediator.log('legal_authority_query_error', error=str(e))
            return []

    def get_authority_by_id(self, authority_id: int) -> Optional[Dict[str, Any]]:
        """Get a single authority record by its DuckDB ID.

        ``None`` means the query completed successfully but the record does not
        exist. Database and record-decoding failures are logged and propagated
        so callers do not mistake an unavailable lookup for a missing record.
        """
        if not DUCKDB_AVAILABLE:
            return None

        try:
            with closing(duckdb.connect(self.db_path)) as conn:
                row = conn.execute(
                    """
                    SELECT id, claim_type, authority_type, source, citation,
                          title, content, url, metadata, relevance_score, timestamp,
                            jurisdiction, source_system, provenance, claim_element_id, claim_element,
                                                    parse_status, chunk_count, parsed_text_preview, parse_metadata,
                                                    graph_status, graph_entity_count, graph_relationship_count, graph_metadata,
                          (
                              SELECT COUNT(*) FROM legal_authority_facts laf WHERE laf.authority_id = legal_authorities.id
                          ) AS fact_count
                    FROM legal_authorities
                    WHERE id = ?
                    LIMIT 1
                    """,
                    [authority_id],
                ).fetchone()
                if row is None:
                    return None
                record = self._authority_record_from_row(row, include_claim_type=True)
                return self._attach_treatment_payloads(conn, record)
        except Exception as exc:
            self.mediator.log(
                'legal_authority_query_error',
                error=str(exc),
                error_type=type(exc).__name__,
                authority_id=authority_id,
            )
            raise

    def get_authority_treatments(self, authority_id: int) -> List[Dict[str, Any]]:
        """Get persisted treatment records for a stored legal authority."""
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            records = self._get_authority_treatments(conn, authority_id)
            conn.close()
            return records
        except Exception as e:
            self.mediator.log('legal_authority_treatment_query_error', error=str(e), authority_id=authority_id)
            return []

    def get_authority_search_programs(self, authority_id: int) -> List[Dict[str, Any]]:
        """Get persisted search-program records for a stored legal authority."""
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            records = self._get_authority_search_programs(conn, authority_id)
            conn.close()
            return records
        except Exception as e:
            self.mediator.log('legal_authority_search_program_query_error', error=str(e), authority_id=authority_id)
            return []

    def get_authority_rule_candidates(self, authority_id: int) -> List[Dict[str, Any]]:
        """Get persisted rule candidate records for a stored legal authority."""
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            records = self._get_authority_rule_candidates(conn, authority_id)
            conn.close()
            return records
        except Exception as e:
            self.mediator.log('legal_authority_rule_candidate_query_error', error=str(e), authority_id=authority_id)
            return []

    def get_authority_facts(self, authority_id: int) -> List[Dict[str, Any]]:
        """Get persisted fact records for a stored legal authority."""
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            columns = set(_list_table_columns(conn, 'legal_authority_facts'))
            durable_select = []
            for column_name in _LEGAL_AUTHORITY_FACT_DURABLE_COLUMNS:
                if column_name == 'source_passage':
                    expression = (
                        "CASE WHEN source_passage IS NULL THEN NULL "
                        "ELSE CAST(source_passage AS VARCHAR) END AS source_passage"
                        if column_name in columns
                        else "NULL AS source_passage"
                    )
                else:
                    expression = column_name if column_name in columns else f"NULL AS {column_name}"
                durable_select.append(expression)
            durable_struct = ', '.join(
                f'{column_name} := {column_name}'
                for column_name in _LEGAL_AUTHORITY_FACT_DURABLE_COLUMNS
            )
            rows = conn.execute(
                f"""
                SELECT fact_id, fact_text, source_authority_id, confidence, metadata, provenance,
                       struct_pack({durable_struct})
                FROM (
                    SELECT fact_id, fact_text, source_authority_id, confidence, metadata, provenance,
                           {', '.join(durable_select)}
                    FROM legal_authority_facts
                    WHERE authority_id = ?
                ) facts
                ORDER BY fact_id ASC
                """,
                [authority_id],
            ).fetchall()
            conn.close()
            return [
                _normalize_authority_fact_row(row, authority_id=authority_id)
                for row in rows
            ]
        except Exception as e:
            self.mediator.log('legal_authority_fact_query_error', error=str(e), authority_id=authority_id)
            return []

    def get_authority_chunks(self, authority_id: int) -> List[Dict[str, Any]]:
        """Get parsed chunk records for a stored legal authority."""
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            rows = conn.execute(
                """
                SELECT chunk_id, chunk_index, start_offset, end_offset, chunk_text, metadata
                FROM legal_authority_chunks
                WHERE authority_id = ?
                ORDER BY chunk_index ASC
                """,
                [authority_id],
            ).fetchall()
            conn.close()
            return [
                {
                    'chunk_id': row[0],
                    'index': row[1],
                    'start': row[2],
                    'end': row[3],
                    'text': row[4],
                    'metadata': json.loads(row[5]) if row[5] else {},
                }
                for row in rows
            ]
        except Exception as e:
            self.mediator.log('legal_authority_chunk_query_error', error=str(e), authority_id=authority_id)
            return []

    def get_authority_graph(self, authority_id: int) -> Dict[str, Any]:
        """Get normalized graph entities and relationships for a stored legal authority."""
        if not DUCKDB_AVAILABLE:
            return {'status': 'unavailable', 'entities': [], 'relationships': []}

        try:
            conn = duckdb.connect(self.db_path)
            entity_rows = conn.execute(
                """
                SELECT entity_id, entity_type, entity_name, confidence, metadata
                FROM legal_authority_graph_entities
                WHERE authority_id = ?
                ORDER BY entity_id ASC
                """,
                [authority_id],
            ).fetchall()
            relationship_rows = conn.execute(
                """
                SELECT relationship_id, source_id, target_id, relation_type, confidence, metadata
                FROM legal_authority_graph_relationships
                WHERE authority_id = ?
                ORDER BY relationship_id ASC
                """,
                [authority_id],
            ).fetchall()
            conn.close()
            return {
                'status': 'available',
                'entities': [
                    {
                        'id': row[0],
                        'type': row[1],
                        'name': row[2],
                        'confidence': row[3],
                        'attributes': json.loads(row[4]) if row[4] else {},
                    }
                    for row in entity_rows
                ],
                'relationships': [
                    {
                        'id': row[0],
                        'source_id': row[1],
                        'target_id': row[2],
                        'relation_type': row[3],
                        'confidence': row[4],
                        'attributes': json.loads(row[5]) if row[5] else {},
                    }
                    for row in relationship_rows
                ],
            }
        except Exception as e:
            self.mediator.log('legal_authority_graph_query_error', error=str(e), authority_id=authority_id)
            return {'status': 'error', 'entities': [], 'relationships': [], 'error': str(e)}
    
    def get_statistics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics about stored legal authorities.
        
        Args:
            user_id: Optional user ID to filter by
            
        Returns:
            Dictionary with statistics
        """
        if not DUCKDB_AVAILABLE:
            return {'available': False}
        
        try:
            conn = duckdb.connect(self.db_path)
            
            if user_id:
                result = conn.execute("""
                    SELECT 
                        COUNT(*) as total_count,
                        COUNT(DISTINCT authority_type) as type_count,
                        COUNT(DISTINCT claim_type) as claim_count,
                        COALESCE((SELECT COUNT(*) FROM legal_authority_facts laf JOIN legal_authorities la ON laf.authority_id = la.id WHERE la.user_id = ?), 0) as total_facts
                    FROM legal_authorities
                    WHERE user_id = ?
                """, [user_id, user_id]).fetchone()
            else:
                result = conn.execute("""
                    SELECT 
                        COUNT(*) as total_count,
                        COUNT(DISTINCT authority_type) as type_count,
                        COUNT(DISTINCT user_id) as user_count,
                        COALESCE((SELECT COUNT(*) FROM legal_authority_facts), 0) as total_facts
                    FROM legal_authorities
                """).fetchone()
            
            conn.close()
            
            stats = {
                'available': True,
                'total_count': result[0],
                'type_count': result[1],
                'total_facts': result[3] if user_id else result[3],
            }
            
            if user_id:
                stats['claim_count'] = result[2]
            else:
                stats['user_count'] = result[2]
            
            return stats
            
        except Exception as e:
            self.mediator.log('legal_authority_stats_error', error=str(e))
            return {'available': False, 'error': str(e)}


def gate_rule_use_by_temporal_authority(
    authority: Dict[str, Any],
    query_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Gate requirement support with LegalIR temporal applicability and treatment edges.

    Treatment rows stay in the result. Adverse and unconfirmed-good-law treatment
    removes support eligibility. Unknown version or date stays unavailable and
    does not select another version as the current rule.
    """
    from integrations.ipfs_datasets.logic import (
        evaluate_temporal_requirement_applicability,
        requirement_treatment_support,
    )

    temporal = evaluate_temporal_requirement_applicability(authority, query_context=query_context)
    treatment = requirement_treatment_support(authority)
    support_eligible = bool(temporal.get('applicable')) and bool(treatment.get('support_eligible'))
    return {
        'temporal_applicability': temporal,
        'applicability_status': temporal.get('applicability_status'),
        'applicable': bool(temporal.get('applicable')),
        'available': bool(temporal.get('available')),
        'guessed_current_rule': False,
        'treatment_edges': list(treatment.get('treatment_edges') or []),
        'treatment_edges_visible': True,
        'blocking_treatments': list(treatment.get('blocking_treatments') or []),
        'treatment_blocks_support': bool(treatment.get('treatment_blocks_support')),
        'support_eligible': support_eligible,
    }


class LegalAuthorityAnalysisHook:
    """
    Hook for analyzing stored legal authorities.
    
    Provides methods to analyze, rank, and generate insights from
    stored legal authorities.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator

    def gate_rule_use(self, authority: Dict[str, Any], query_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return temporal applicability and whether treatment still allows support."""
        return gate_rule_use_by_temporal_authority(authority, query_context=query_context)
    
    def analyze_authorities_for_claim(self, user_id: str, claim_type: str) -> Dict[str, Any]:
        """
        Analyze legal authorities for a specific claim.
        
        Args:
            user_id: User identifier
            claim_type: Claim type to analyze
            
        Returns:
            Analysis with authority summary and recommendations
        """
        if not hasattr(self.mediator, 'legal_authority_storage'):
            return {'error': 'Legal authority storage not available'}
        
        try:
            authorities = self.mediator.legal_authority_storage.get_authorities_by_claim(
                user_id, claim_type
            )
            
            if not authorities:
                return {
                    'claim_type': claim_type,
                    'total_authorities': 0,
                    'recommendation': f'No legal authorities found for {claim_type}. Run a search to find relevant laws and regulations.'
                }
            
            # Group by type
            by_type = {}
            for auth in authorities:
                auth_type = auth['type']
                by_type[auth_type] = by_type.get(auth_type, 0) + 1
            
            # Generate analysis using LLM
            analysis = {
                'claim_type': claim_type,
                'total_authorities': len(authorities),
                'by_type': by_type,
                'authorities': authorities[:10],  # Top 10
                'recommendation': self._generate_authority_recommendations(
                    claim_type, authorities
                )
            }
            
            return analysis
            
        except Exception as e:
            self.mediator.log('legal_authority_analysis_error', error=str(e))
            return {'error': str(e)}
    
    def _generate_authority_recommendations(self, claim_type: str,
                                           authorities: List[Dict[str, Any]]) -> str:
        """Generate recommendations using LLM."""
        authority_summary = '\n'.join([
            f"- {a['type']}: {a.get('citation', 'N/A')} - {a.get('title', 'No title')}"
            for a in authorities[:5]
        ])
        
        prompt = f"""Based on these legal authorities for a {claim_type} claim:

{authority_summary}

Provide brief analysis of:
1. Strength of legal foundation
2. Key authorities to cite
3. Any gaps in legal research
"""
        
        try:
            response = self.mediator.query_backend(prompt)
            return response
        except Exception:
            return f'Found {len(authorities)} legal authorities. Review citations for strongest support.'

    def bind_support_projections(self, projections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Record analysis ownership on projections already decided by this hook's rules.

        The decision itself is ``project_authority_support``. This method does
        not promote a search hit, suggestion, or caller flag.
        """
        bound = []
        for item in projections:
            row = dict(item)
            row["owner"] = "LegalAuthorityAnalysisHook"
            if row.get("governing_authority") is True and not row.get("lineage"):
                row["governing_authority"] = False
                row["verified_support"] = False
                row["projection_status"] = "unverified"
            bound.append(row)
        if hasattr(self.mediator, "log"):
            self.mediator.log(
                "authority_support_projected",
                governing_count=sum(1 for row in bound if row.get("governing_authority") is True),
                retired_count=sum(1 for row in bound if row.get("projection_status") == "retired"),
            )
        return bound

    def derive_dependency_requirements(self, case_file: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
        """Public workflow entry: derive requirements from admitted passages.

        The effect is the returned derivation. It is produced by the Dataset
        corpus lookup and the source-bound rule extractor. This method does
        not invent elements when authority is missing or in conflict.
        """
        result = derive_admitted_dependency_requirements(case_file, body)
        if hasattr(self.mediator, "log"):
            self.mediator.log(
                "derived_dependency_requirements",
                status=str(result.get("status") or ""),
                requirement_count=len(result.get("requirements") or []),
                unresolved_count=len(result.get("unresolved_research") or []),
            )
        return result


DEPENDENCY_REQUIREMENT_TASK_ID = "CIMP-UX-26"
_DERIVATION_TOOL = "extract_source_bound_rule_candidates"
_CORPUS_TOOL = "lookup_bounded_legal_corpus"


def _passage_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "source_text", "content", "full_text"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item
    return ""


def _case_coordinate(case_file: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, str]:
    context = case_file.get("legal_context") if isinstance(case_file.get("legal_context"), dict) else {}
    law_date = context.get("applicable_law_date") if isinstance(context.get("applicable_law_date"), dict) else {}
    event_date = context.get("event_date") if isinstance(context.get("event_date"), dict) else {}
    effective = str(law_date.get("precise_date") or law_date.get("raw_text") or "")
    as_of = str(event_date.get("precise_date") or effective or "")
    version = body.get("authority_version")
    return {
        "jurisdiction": str(context.get("jurisdiction") or ""),
        "effective_date": effective,
        "as_of_date": as_of,
        "authority_version": version.strip() if isinstance(version, str) else "",
    }


def _support_facts(body: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = body.get("facts") if isinstance(body.get("facts"), list) else []
    facts: List[Dict[str, str]] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        fact_id = str(item.get("fact_id") or "").strip()
        text = str(item.get("text") or "").strip()
        if fact_id and text and len(fact_id) <= 80 and len(text) <= 500:
            facts.append({"fact_id": fact_id, "text": text})
    return facts


def _authority_for_passage(passage: Dict[str, Any], coordinates: Dict[str, str]) -> Dict[str, Any]:
    from integrations.ipfs_datasets.logic import sha256_utf8

    text = passage["text"]
    authority_id = str(passage.get("citation") or passage.get("passage_id") or "admitted-passage")
    version = coordinates["authority_version"]
    return {
        "source_text": text,
        "source_hash": sha256_utf8(text),
        "content_hash_scope": "authority_text",
        "jurisdiction": coordinates["jurisdiction"],
        "authority_id": authority_id,
        "citation": str(passage.get("citation") or ""),
        "authority_version": version,
        "effective_date": coordinates["effective_date"],
        "as_of_date": coordinates["as_of_date"] or coordinates["effective_date"],
        "law_version_id": authority_id + ":" + version,
        "law_versions": [{
            "law_version_id": authority_id + ":" + version,
            "authority_id": authority_id,
            "citation": str(passage.get("citation") or ""),
            "jurisdiction": coordinates["jurisdiction"],
            "version": version,
            "effective_date": coordinates["effective_date"],
        }],
    }


def _lineage(candidate: Dict[str, Any], passage: Dict[str, Any], coordinates: Dict[str, str]) -> Dict[str, Any]:
    temporal = candidate.get("temporal_applicability") if isinstance(candidate.get("temporal_applicability"), dict) else {}
    return {
        "tool": _DERIVATION_TOOL,
        "module": "integrations.ipfs_datasets.logic",
        "contract": str(candidate.get("contract") or ""),
        "corpus_tool": _CORPUS_TOOL,
        "temporal_api": str(temporal.get("api") or ""),
        "temporal_graph_id": str(temporal.get("temporal_authority_graph_id") or ""),
        "passage_id": passage.get("passage_id") or "",
        "jurisdiction": str(candidate.get("jurisdiction") or coordinates["jurisdiction"]),
        "effective_date": coordinates["effective_date"],
        "authority_version": str(candidate.get("authority_version") or coordinates["authority_version"]),
        "source_hash": str(candidate.get("source_hash") or ""),
        "span_sha256": str(candidate.get("span_sha256") or ""),
        "authority_text_sha256": str(candidate.get("authority_text_sha256") or ""),
    }


def _attach_fact_support(requirement: Dict[str, Any], facts: List[Dict[str, str]]) -> None:
    """Facts may be recorded against a requirement. They do not edit the rule."""
    frozen = (
        requirement.get("rule_text"),
        requirement.get("jurisdiction"),
        requirement.get("authority_version"),
        requirement.get("effective_date"),
        json.dumps(requirement.get("source_span"), sort_keys=True),
    )
    words = {word.lower() for word in str(requirement.get("rule_text") or "").split() if len(word) > 4}
    support = []
    for fact in facts:
        tokens = {word.lower().strip(".,") for word in fact["text"].split()}
        support.append({
            "fact_id": fact["fact_id"],
            "affects": "support",
            "rewrites_law": False,
            "overlap": sorted(words & tokens),
        })
    requirement["fact_support"] = support
    requirement["support_state"] = "fact_recorded" if any(item["overlap"] for item in support) else "unsupported"
    requirement["satisfied"] = False
    requirement["proof"] = False
    requirement["legal_sufficiency"] = False
    assert (
        requirement.get("rule_text"),
        requirement.get("jurisdiction"),
        requirement.get("authority_version"),
        requirement.get("effective_date"),
        json.dumps(requirement.get("source_span"), sort_keys=True),
    ) == frozen


def derive_admitted_dependency_requirements(case_file: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    """Build current requirements from admitted passages through the real SDK tools.

    A fact can change only the support record. Missing coordinates and
    conflicting full texts stay unresolved research. Keyword templates are
    not substituted.
    """
    from applications.legal_context_api import LegalContextError, conduct_legal_source_flow
    from integrations.ipfs_datasets.logic import extract_source_bound_rule_candidates

    if not isinstance(case_file, dict) or not isinstance(body, dict):
        raise LegalContextError("legal_context_field")
    flow = conduct_legal_source_flow(case_file, body)
    coordinates = _case_coordinate(case_file, body)
    facts = _support_facts(body)
    base = {
        "task_id": DEPENDENCY_REQUIREMENT_TASK_ID,
        "tools": [_CORPUS_TOOL, _DERIVATION_TOOL],
        "admitted_law": False,
        "proof": False,
        "legal_sufficiency": False,
        "hardcoded_elements_used": False,
        "fact_rewrites_ignored": any(isinstance(item, dict) and "rule_text" in item for item in (body.get("facts") or []) if isinstance(body.get("facts"), list)),
        "coordinates": coordinates,
        "source_flow_status": flow.get("status"),
        "requirements": [],
        "unresolved_research": [],
        "derivation_lineage": [],
    }
    if flow.get("status") == "questions_open" or flow.get("tool") == "not_called":
        base["status"] = "unresolved_research"
        base["unresolved_research"] = [{
            "reason": "missing_legal_context",
            "questions": list(flow.get("questions") or []),
            "visible": True,
        }]
        return base
    passages = []
    citations: Dict[str, List[str]] = {}
    for item in (flow.get("decisions") or {}).get("custody") or []:
        if not isinstance(item, dict):
            continue
        text = _passage_text(item.get("source_passage"))
        discovery = next((row for row in (flow.get("decisions") or {}).get("discovery") or []
                          if isinstance(row, dict) and row.get("passage_id") == item.get("passage_id")), {})
        citation = str(discovery.get("citation") or "")
        passage = {"passage_id": str(item.get("passage_id") or ""), "text": text, "citation": citation}
        passages.append(passage)
        citations.setdefault(citation or passage["passage_id"], []).append(text)
    conflicts = [key for key, texts in citations.items() if len({text for text in texts if text}) > 1]
    admitted_ids = set(flow.get("admitted_passage_ids") or [])
    admitted = [passage for passage in passages if passage["passage_id"] in admitted_ids and passage["text"]]
    if conflicts:
        for passage in passages:
            if not passage["text"]:
                continue
            authority = _authority_for_passage(passage, coordinates)
            extracted = extract_source_bound_rule_candidates(authority)
            base["derivation_lineage"].append({
                "tool": _DERIVATION_TOOL,
                "module": "integrations.ipfs_datasets.logic",
                "contract": extracted.get("contract"),
                "passage_id": passage["passage_id"],
                "promoted_count": extracted.get("promoted_count"),
                "withheld_because": "conflicting_authority",
            })
        base["status"] = "unresolved_research"
        base["unresolved_research"] = [{
            "reason": "conflicting_authority",
            "citations": conflicts,
            "passage_ids": [passage["passage_id"] for passage in passages],
            "visible": True,
        }]
        return base
    if not admitted:
        base["status"] = "unresolved_research"
        base["unresolved_research"] = [{
            "reason": "no_admitted_passage",
            "visible": True,
            "discovery_admitted": False,
        }]
        return base
    requirements = []
    unresolved = []
    for passage in admitted:
        authority = _authority_for_passage(passage, coordinates)
        extracted = extract_source_bound_rule_candidates(authority)
        promoted = list(extracted.get("promoted_requirements") or [])
        if not promoted:
            candidate = (extracted.get("candidates") or [{}])[0]
            unresolved.append({
                "reason": "authority_not_promoted",
                "visible": True,
                "passage_id": passage["passage_id"],
                "review_reasons": list(candidate.get("review_reasons") or []),
                "temporal_reason": str((candidate.get("temporal_applicability") or {}).get("reason") or ""),
                "rule_text": "",
            })
            base["derivation_lineage"].append(_lineage(candidate if isinstance(candidate, dict) else {}, passage, coordinates))
            continue
        for candidate in promoted:
            if candidate.get("applicable") is not True or candidate.get("support_eligible") is not True:
                unresolved.append({
                    "reason": "authority_not_current",
                    "visible": True,
                    "passage_id": passage["passage_id"],
                    "review_reasons": list(candidate.get("review_reasons") or []),
                })
                continue
            requirement = {
                "name": str(candidate.get("citation") or passage["citation"] or "Admitted requirement"),
                "description": candidate.get("rule_text") or "",
                "rule_text": candidate.get("rule_text") or "",
                "source_span": candidate.get("source_span"),
                "source_hash": candidate.get("source_hash"),
                "span_sha256": candidate.get("span_sha256"),
                "authority_text_sha256": candidate.get("authority_text_sha256"),
                "authority_id": candidate.get("authority_id"),
                "authority_version": candidate.get("authority_version"),
                "jurisdiction": candidate.get("jurisdiction"),
                "effective_date": coordinates["effective_date"],
                "applicable_date": coordinates["as_of_date"],
                "temporal_applicability": candidate.get("temporal_applicability"),
                "treatment_edges": candidate.get("treatment_edges"),
                "blocking_treatments": candidate.get("blocking_treatments"),
                "applicable": True,
                "support_eligible": True,
                "treatment_blocks_support": False,
                "source_record": authority,
                "passage_id": passage["passage_id"],
                "citation": candidate.get("citation") or passage["citation"],
                "verification_status": "promoted",
                "source_bound": True,
                "admitted_law": True,
                "proof": False,
                "legal_sufficiency": False,
                "derivation_lineage": _lineage(candidate, passage, coordinates),
                "derivation_task": DEPENDENCY_REQUIREMENT_TASK_ID,
            }
            _attach_fact_support(requirement, facts)
            requirements.append(requirement)
            base["derivation_lineage"].append(requirement["derivation_lineage"])
    base["requirements"] = requirements
    base["unresolved_research"] = unresolved
    base["status"] = "current" if requirements and not unresolved else "unresolved_research" if not requirements else "current_with_gaps"
    base["admitted_law"] = bool(requirements)
    return base


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def classify_non_governing_materials(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Search hits, stale caches, suggestions, and caller flags are not authority.

    LegalAuthoritySearchHook owns this classification. Nothing here is stored
    as governing law or verified support.
    """
    caller = _mapping(payload.get("caller_flags"))
    hits = []
    for item in payload.get("search_hits") or []:
        if not isinstance(item, dict):
            continue
        hits.append({
            "record_kind": "search_hit",
            "citation": _text(item.get("citation")),
            "snippet": _text(item.get("snippet") or item.get("text")),
            "cache_generation": _text(item.get("cache_generation")),
            "governing_authority": False,
            "verified_support": False,
            "creates_law": False,
            "caller_flag_ignored": True,
        })
    stale = []
    for item in payload.get("stale_cache") or []:
        if not isinstance(item, dict):
            continue
        stale.append({
            "record_kind": "stale_cache",
            "passage_id": _text(item.get("passage_id")),
            "requirement_id": _text(item.get("requirement_id")),
            "source_version": _text(item.get("source_version")),
            "definition_version": _text(item.get("definition_version")),
            "projection_status": "retired",
            "retirement_reason": "stale_cache",
            "governing_authority": False,
            "verified_support": False,
            "creates_law": False,
        })
    suggestions = []
    for item in payload.get("suggestions") or []:
        if not isinstance(item, dict):
            continue
        suggestions.append({
            "record_kind": "suggestion",
            "requirement_id": _text(item.get("requirement_id")),
            "text": _text(item.get("text")),
            "governing_authority": False,
            "verified_support": False,
            "creates_law": False,
        })
    return {
        "owner": "LegalAuthoritySearchHook",
        "search_hits": hits,
        "stale_cache": stale,
        "suggestions": suggestions,
        "caller_flags_seen": {
            "verified_support": caller.get("verified_support") is True,
            "governing_authority": caller.get("governing_authority") is True,
        },
        "caller_flags_applied": False,
        "governing_authority": False,
        "verified_support": False,
    }


def _passage_record(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from integrations.ipfs_datasets.logic import sha256_utf8

    text = _text(item.get("text") or item.get("source_text"))
    passage_id = _text(item.get("passage_id"))
    requirement_id = _text(item.get("requirement_id"))
    source_version = _text(item.get("source_version"))
    definition_version = _text(item.get("definition_version"))
    if not (text and passage_id and requirement_id and source_version and definition_version):
        return None
    digest = sha256_utf8(text)
    supplied = _text(item.get("source_hash"))
    if supplied and supplied != digest:
        return {
            "passage_id": passage_id,
            "requirement_id": requirement_id,
            "text": text,
            "citation": _text(item.get("citation")),
            "source_version": source_version,
            "definition_version": definition_version,
            "source_hash": digest,
            "supplied_hash": supplied,
            "admitted": False,
            "integrity": "source_hash_mismatch",
        }
    return {
        "passage_id": passage_id,
        "requirement_id": requirement_id,
        "text": text,
        "citation": _text(item.get("citation")) or passage_id,
        "source_version": source_version,
        "definition_version": definition_version,
        "source_hash": digest,
        "supplied_hash": supplied or digest,
        "admitted": True,
        "integrity": "matched",
    }


def project_authority_support(payload: Dict[str, Any], passages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """LegalAuthorityAnalysisHook: governing authority needs an admitted passage and lineage.

    Source drift and contradictions retire every projection that uses the
    affected passage or requirement. Caller support flags are not read.
    """
    admitted = [row for row in passages if row.get("admitted") is True]
    by_requirement: Dict[str, List[Dict[str, Any]]] = {}
    for row in admitted:
        by_requirement.setdefault(row["requirement_id"], []).append(row)
    contradicted = set()
    for requirement_id, rows in by_requirement.items():
        texts = {row["text"] for row in rows}
        if len(texts) > 1:
            contradicted.add(requirement_id)
    for item in payload.get("contradictions") or []:
        if isinstance(item, dict) and _text(item.get("requirement_id")):
            contradicted.add(_text(item.get("requirement_id")))
    drift_ids = set()
    drift_requirements = set()
    for item in payload.get("source_drift") or []:
        if not isinstance(item, dict):
            continue
        passage_id = _text(item.get("passage_id"))
        requirement_id = _text(item.get("requirement_id"))
        if passage_id:
            drift_ids.add(passage_id)
        if requirement_id:
            drift_requirements.add(requirement_id)
    lineage_rows = [row for row in (payload.get("support_lineage") or []) if isinstance(row, dict)]

    projections = []
    for row in passages:
        requirement_id = row["requirement_id"]
        passage_id = row["passage_id"]
        reason = ""
        if row.get("admitted") is not True:
            reason = "source_drift" if row.get("integrity") == "source_hash_mismatch" else "not_admitted"
        elif requirement_id in contradicted:
            reason = "contradiction"
        elif passage_id in drift_ids or requirement_id in drift_requirements:
            reason = "source_drift"
        matches = []
        if not reason:
            for link in lineage_rows:
                if _text(link.get("passage_id")) != passage_id:
                    continue
                if _text(link.get("requirement_id")) != requirement_id:
                    continue
                if _text(link.get("source_version")) != row["source_version"]:
                    continue
                if _text(link.get("definition_version")) != row["definition_version"]:
                    continue
                if _text(link.get("source_hash")) != row["source_hash"]:
                    continue
                fact_id = _text(link.get("fact_id"))
                evidence_ref = _text(link.get("evidence_ref"))
                lineage_id = _text(link.get("lineage_id"))
                if not (fact_id and evidence_ref and lineage_id):
                    continue
                matches.append({
                    "lineage_id": lineage_id,
                    "fact_id": fact_id,
                    "evidence_ref": evidence_ref,
                })
        verified = bool(matches) and not reason
        projections.append({
            "owner": "LegalAuthorityAnalysisHook",
            "passage_id": passage_id,
            "requirement_id": requirement_id,
            "citation": row.get("citation") or "",
            "source_version": row["source_version"],
            "definition_version": row["definition_version"],
            "source_hash": row["source_hash"],
            "lineage": matches,
            "governing_authority": verified,
            "verified_support": verified,
            "projection_status": "retired" if reason in {"source_drift", "contradiction", "stale_cache"} else ("current" if verified else "unverified"),
            "retirement_reason": reason if reason in {"source_drift", "contradiction", "stale_cache"} else "",
            "admission_reason": reason if reason == "not_admitted" else "",
            "creates_law": False,
            "proof": False,
            "legal_sufficiency": False,
        })
    return projections


def store_admitted_authority_passages(storage: Any, payload: Dict[str, Any], passages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Persist admitted passage text. Search hits are refused, including caller-verified hits."""
    user_id = _text(payload.get("user_id")) or "actor"
    complaint_id = _text(payload.get("complaint_id")) or "case"
    claim_type = _text(payload.get("claim_type")) or "claim"
    stored = []
    for row in passages:
        if row.get("admitted") is not True:
            continue
        result = storage.store_acquired_authority(
            {
                "type": "statute",
                "source": "admitted_passage",
                "citation": row["citation"],
                "title": row["requirement_id"],
                "content": row["text"],
                "metadata": {
                    "passage_id": row["passage_id"],
                    "requirement_id": row["requirement_id"],
                    "source_version": row["source_version"],
                    "definition_version": row["definition_version"],
                    "source_hash": row["source_hash"],
                    "admitted": True,
                    "governing_authority": False,
                    "verified_support": False,
                },
            },
            user_id,
            complaint_id=complaint_id,
            claim_type=claim_type,
        )
        stored.append({
            "passage_id": row["passage_id"],
            "requirement_id": row["requirement_id"],
            "record_id": result.get("record_id"),
            "status": result.get("status"),
            "reason": result.get("reason"),
            "source": "admitted_passage",
        })
    refused_hits = []
    for item in payload.get("search_hits") or []:
        if not isinstance(item, dict):
            continue
        snippet = _text(item.get("snippet") or item.get("text")) or "search hit"
        refused = storage.store_acquired_authority(
            {
                "type": "statute",
                "source": "search_hit",
                "citation": _text(item.get("citation")) or "search-hit",
                "title": "search hit",
                "content": snippet,
                "verified": True,
                "metadata": {"verified": True, "governing_authority": True, "record_kind": "search_hit"},
            },
            user_id,
            complaint_id=complaint_id,
            claim_type=claim_type,
        )
        refused_hits.append({
            "status": refused.get("status"),
            "reason": refused.get("reason"),
            "record_id": refused.get("record_id"),
            "stored": False,
        })
    return {
        "owner": "LegalAuthorityStorageHook",
        "stored_passages": stored,
        "refused_search_hits": refused_hits,
        "search_hits_stored": 0,
    }
