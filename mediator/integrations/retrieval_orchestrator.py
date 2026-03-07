import re
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .contracts import NormalizedRetrievalRecord


class RetrievalOrchestrator:
    _STOP_WORDS: Set[str] = {
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'in',
        'into', 'is', 'of', 'on', 'or', 'that', 'the', 'to', 'with', 'your',
        'case', 'claim', 'claims', 'matter', 'issue', 'issues', 'analysis',
    }

    _SOURCE_TYPE_WEIGHTS: Dict[str, float] = {
        'statute': 0.22,
        'regulation': 0.18,
        'case_law': 0.16,
        'legal_corpus': 0.08,
        'legal_term': 0.08,
        'legal_pattern': 0.08,
        'keyword': 0.05,
        'web_archive': 0.02,
    }

    _SOURCE_NAME_WEIGHTS: Dict[str, float] = {
        'us_code': 0.08,
        'federal_register': 0.06,
        'recap': 0.05,
        'complaint_analysis': 0.02,
        'common_crawl': 0.0,
        'llm_statute_retrieval': 0.03,
    }

    _FUSION_LEGAL_TYPES: Set[str] = {'statute', 'regulation', 'case_law', 'legal_corpus', 'legal_term', 'legal_pattern'}
    _FUSION_EVIDENCE_TYPES: Set[str] = {'web', 'web_archive', 'evidence'}

    def _record_payload(self, record: NormalizedRetrievalRecord) -> Dict[str, Any]:
        return {
            'source_type': record.source_type,
            'source_name': record.source_name,
            'query': record.query,
            'retrieved_at': record.retrieved_at,
            'title': record.title,
            'url': record.url,
            'citation': record.citation,
            'snippet': record.snippet,
            'content': record.content,
            'score': record.score,
            'confidence': record.confidence,
            'metadata': dict(record.metadata or {}),
        }

    def _is_authority_record(self, record: NormalizedRetrievalRecord) -> bool:
        return str(record.source_type or '').strip().lower() in self._FUSION_LEGAL_TYPES

    def _is_evidence_record(self, record: NormalizedRetrievalRecord) -> bool:
        return str(record.source_type or '').strip().lower() in self._FUSION_EVIDENCE_TYPES

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r"[a-z0-9_]+", str(text or '').lower())
        return [token for token in tokens if token and token not in self._STOP_WORDS]

    def _record_text(self, record: NormalizedRetrievalRecord) -> str:
        metadata = dict(record.metadata or {})
        return " ".join([
            str(record.title or ''),
            str(record.snippet or ''),
            str(record.content or ''),
            str(record.citation or ''),
            str(metadata.get('source') or ''),
            str(metadata.get('complaint_type') or ''),
        ]).lower()

    def _ordered_unique_tokens(self, values: Iterable[str]) -> List[str]:
        seen: Set[str] = set()
        ordered: List[str] = []
        for value in values:
            token = str(value or '').strip().lower()
            if not token or token in seen:
                continue
            seen.add(token)
            ordered.append(token)
        return ordered

    def _fusion_keys(
        self,
        record: NormalizedRetrievalRecord,
        query_context: Optional[Dict[str, Any]],
    ) -> List[str]:
        keys: List[str] = []
        citation = re.sub(r'\s+', ' ', str(record.citation or '').strip().lower())
        if citation:
            keys.append(f'citation:{citation}')

        record_terms = self._ordered_unique_tokens(self._tokenize(self._record_text(record)))
        if not record_terms:
            return keys

        query_terms = set(query_context.get('query_terms') or set()) if query_context else set()
        prioritized_terms = [term for term in record_terms if term in query_terms]
        fallback_terms = [term for term in record_terms if term not in prioritized_terms]
        if len(prioritized_terms) >= 2:
            query_key = f"query:{' '.join(prioritized_terms[:2])}"
            if query_key not in keys:
                keys.append(query_key)
        key_terms = self._ordered_unique_tokens([*prioritized_terms, *fallback_terms])[:4]
        if len(key_terms) < 2:
            title_terms = self._ordered_unique_tokens(self._tokenize(str(record.title or '')))[:4]
            key_terms = title_terms or key_terms
        if len(key_terms) < 2:
            return keys
        term_key = f"terms:{' '.join(key_terms)}"
        if term_key not in keys:
            keys.append(term_key)
        return keys

    def _build_fusion_context(
        self,
        records: Iterable[NormalizedRetrievalRecord],
        query_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        clusters: Dict[str, Dict[str, Any]] = {}

        for index, record in enumerate(records):
            fusion_keys = self._fusion_keys(record, query_context)
            if not fusion_keys:
                continue

            dedupe_key = record.dedupe_key() or f'anonymous:{index}'
            for fusion_key in fusion_keys:
                cluster = clusters.setdefault(fusion_key, {
                    'record_keys': set(),
                    'source_types': set(),
                    'source_names': set(),
                })
                cluster['record_keys'].add(dedupe_key)
                cluster['source_types'].add(str(record.source_type or '').strip().lower())
                cluster['source_names'].add(str(record.source_name or '').strip().lower())

        for cluster in clusters.values():
            source_types = set(cluster.get('source_types', set()))
            cluster['cross_source_type_count'] = len(source_types)
            cluster['cross_source_name_count'] = len(set(cluster.get('source_names', set())))
            cluster['corroborating_record_count'] = len(set(cluster.get('record_keys', set())))
            cluster['legal_support_count'] = len(source_types & self._FUSION_LEGAL_TYPES)
            cluster['evidence_support_count'] = len(source_types & self._FUSION_EVIDENCE_TYPES)
            cluster['hybrid_legal_evidence'] = bool(
                cluster['legal_support_count'] and cluster['evidence_support_count']
            )

        return clusters

    def decompose_query(
        self,
        query: str,
        claim_type: Optional[str] = None,
        complaint_type: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        max_queries: int = 4,
    ) -> Dict[str, Any]:
        primary_query = str(query or '').strip()
        candidates: List[str] = []

        def _add(candidate: Optional[str]):
            value = str(candidate or '').strip()
            if not value:
                return
            if value not in candidates:
                candidates.append(value)

        _add(primary_query)

        for segment in re.split(r'[;,]', primary_query):
            _add(segment)

        claim_phrase = str(claim_type or '').replace('_', ' ').strip()
        complaint_phrase = str(complaint_type or '').replace('_', ' ').strip()
        jurisdiction_phrase = str(jurisdiction or '').replace('_', ' ').strip()

        if claim_phrase:
            _add(claim_phrase)
            if primary_query:
                _add(f"{claim_phrase} {primary_query}")

        if complaint_phrase and complaint_phrase != claim_phrase:
            _add(complaint_phrase)

        if jurisdiction_phrase and primary_query:
            _add(f"{jurisdiction_phrase} {primary_query}")

        focus_terms = self._tokenize(" ".join(filter(None, [claim_phrase, complaint_phrase])))
        if focus_terms and primary_query:
            _add(" ".join(focus_terms[:4] + self._tokenize(primary_query)[:4]))

        return {
            'primary_query': primary_query,
            'queries': candidates[:max(1, int(max_queries or 1))],
            'claim_type': claim_phrase,
            'complaint_type': complaint_phrase,
            'preferred_jurisdiction': jurisdiction_phrase.lower(),
        }

    def build_query_context(
        self,
        query: str,
        claim_type: Optional[str] = None,
        complaint_type: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        max_queries: int = 4,
    ) -> Dict[str, Any]:
        decomposition = self.decompose_query(
            query=query,
            claim_type=claim_type,
            complaint_type=complaint_type,
            jurisdiction=jurisdiction,
            max_queries=max_queries,
        )
        decomposed_queries = list(decomposition.get('queries', []))
        query_terms: Set[str] = set()
        for item in decomposed_queries:
            query_terms.update(self._tokenize(item))

        return {
            **decomposition,
            'query_terms': query_terms,
        }

    def _infer_jurisdiction(self, record: NormalizedRetrievalRecord) -> str:
        metadata = dict(record.metadata or {})
        jurisdiction = str(metadata.get('jurisdiction') or '').strip().lower()
        if jurisdiction:
            return jurisdiction

        source_name = str(record.source_name or '').strip().lower()
        if source_name in {'us_code', 'federal_register'}:
            return 'federal'
        return ''

    def _score_record(
        self,
        record: NormalizedRetrievalRecord,
        query_context: Optional[Dict[str, Any]],
        fusion_context: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[float, Dict[str, float]]:
        if not query_context:
            source_weight = 0.0
            jurisdiction_weight = 0.0
            query_weight = 0.0
        else:
            metadata = dict(record.metadata or {})
            source_weight = self._SOURCE_TYPE_WEIGHTS.get(str(record.source_type or '').lower(), 0.0)
            source_weight += self._SOURCE_NAME_WEIGHTS.get(str(record.source_name or '').lower(), 0.0)

            jurisdiction_weight = 0.0
            preferred_jurisdiction = str(query_context.get('preferred_jurisdiction') or '').strip().lower()
            record_jurisdiction = self._infer_jurisdiction(record)
            if preferred_jurisdiction and record_jurisdiction:
                if preferred_jurisdiction == record_jurisdiction:
                    jurisdiction_weight += 0.15
                elif preferred_jurisdiction in record_jurisdiction or record_jurisdiction in preferred_jurisdiction:
                    jurisdiction_weight += 0.08

            text_terms = set(self._tokenize(self._record_text(record)))
            query_terms = set(query_context.get('query_terms') or set())
            overlap = len(query_terms & text_terms)
            query_weight = min(0.24, overlap * 0.03)
            for decomposed in query_context.get('queries', [])[1:]:
                fragment = str(decomposed or '').strip().lower()
                if fragment and fragment in self._record_text(record):
                    query_weight += 0.05
            query_weight = min(query_weight, 0.30)

        fusion_weight = 0.0
        fusion_key = ''
        fusion_cluster = None
        for candidate_key in self._fusion_keys(record, query_context):
            candidate_cluster = (fusion_context or {}).get(candidate_key or '') if candidate_key else None
            if not candidate_cluster:
                continue
            candidate_weight = 0.0
            corroborating_record_count = max(0, int(candidate_cluster.get('corroborating_record_count', 0)) - 1)
            cross_source_type_count = max(0, int(candidate_cluster.get('cross_source_type_count', 0)) - 1)
            cross_source_name_count = max(0, int(candidate_cluster.get('cross_source_name_count', 0)) - 1)
            candidate_weight += min(0.12, corroborating_record_count * 0.04)
            candidate_weight += min(0.08, cross_source_type_count * 0.04)
            candidate_weight += min(0.04, cross_source_name_count * 0.02)
            if candidate_cluster.get('hybrid_legal_evidence'):
                candidate_weight += 0.06
            candidate_weight = min(candidate_weight, 0.20)
            if candidate_weight > fusion_weight:
                fusion_weight = candidate_weight
                fusion_key = candidate_key
                fusion_cluster = candidate_cluster

        if fusion_cluster:
            fusion_weight = min(fusion_weight, 0.20)

        composite_score = (
            float(record.score)
            + float(record.confidence) * 0.05
            + source_weight
            + jurisdiction_weight
            + query_weight
            + fusion_weight
        )
        return composite_score, {
            'source_weight': round(source_weight, 6),
            'jurisdiction_weight': round(jurisdiction_weight, 6),
            'query_weight': round(query_weight, 6),
            'fusion_weight': round(fusion_weight, 6),
        }

    def _annotate_record(
        self,
        record: NormalizedRetrievalRecord,
        query_context: Optional[Dict[str, Any]],
        composite_score: float,
        breakdown: Dict[str, float],
        fusion_context: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> NormalizedRetrievalRecord:
        metadata = dict(record.metadata or {})
        metadata.update({
            'orchestrator_composite_score': round(composite_score, 6),
            'orchestrator_source_weight': breakdown.get('source_weight', 0.0),
            'orchestrator_jurisdiction_weight': breakdown.get('jurisdiction_weight', 0.0),
            'orchestrator_query_weight': breakdown.get('query_weight', 0.0),
            'orchestrator_fusion_weight': breakdown.get('fusion_weight', 0.0),
        })

        if query_context:
            metadata.update({
                'query_decomposition_applied': True,
                'query_decomposition_count': len(query_context.get('queries', []) or []),
                'preferred_jurisdiction': query_context.get('preferred_jurisdiction') or '',
            })

        fusion_key = ''
        fusion_cluster = None
        for candidate_key in self._fusion_keys(record, query_context):
            candidate_cluster = (fusion_context or {}).get(candidate_key or '') if candidate_key else None
            if not candidate_cluster:
                continue
            if fusion_cluster is None or int(candidate_cluster.get('corroborating_record_count', 0)) > int(fusion_cluster.get('corroborating_record_count', 0)):
                fusion_key = candidate_key
                fusion_cluster = candidate_cluster
        if fusion_cluster:
            metadata.update({
                'cross_source_fusion_applied': breakdown.get('fusion_weight', 0.0) > 0.0,
                'cross_source_fusion_key': fusion_key,
                'cross_source_record_count': fusion_cluster.get('corroborating_record_count', 0),
                'cross_source_type_count': fusion_cluster.get('cross_source_type_count', 0),
                'cross_source_name_count': fusion_cluster.get('cross_source_name_count', 0),
                'cross_source_hybrid_legal_evidence': fusion_cluster.get('hybrid_legal_evidence', False),
            })
        return replace(record, metadata=metadata)

    def merge_and_rank(
        self,
        records: Iterable[NormalizedRetrievalRecord],
        max_results: int = 20,
        query_context: Optional[Dict[str, Any]] = None,
    ) -> List[NormalizedRetrievalRecord]:
        materialized_records = list(records)
        fusion_context = self._build_fusion_context(materialized_records, query_context)
        merged: Dict[str, NormalizedRetrievalRecord] = {}
        rank_scores: Dict[str, Tuple[float, float]] = {}

        for record in materialized_records:
            key = record.dedupe_key()
            if not key:
                key = f"anonymous:{len(merged)}"
            composite_score, breakdown = self._score_record(record, query_context, fusion_context=fusion_context)
            annotated = self._annotate_record(
                record,
                query_context,
                composite_score,
                breakdown,
                fusion_context=fusion_context,
            )
            rank_tuple = (composite_score, annotated.confidence)
            existing = merged.get(key)
            if existing is None:
                merged[key] = annotated
                rank_scores[key] = rank_tuple
                continue
            if rank_tuple > rank_scores.get(key, (existing.score, existing.confidence)):
                merged[key] = annotated
                rank_scores[key] = rank_tuple

        ranked = sorted(
            merged.values(),
            key=lambda r: rank_scores.get(r.dedupe_key() or '', (r.score, r.confidence)),
            reverse=True,
        )
        return ranked[:max_results]

    def build_support_bundle(
        self,
        records: Iterable[NormalizedRetrievalRecord],
        max_items_per_bucket: int = 5,
    ) -> Dict[str, Any]:
        ranked_records = list(records)
        authorities = [record for record in ranked_records if self._is_authority_record(record)]
        evidence = [record for record in ranked_records if self._is_evidence_record(record)]
        cross_supported = [
            record for record in ranked_records
            if bool(dict(record.metadata or {}).get('cross_source_fusion_applied'))
        ]
        hybrid_supported = [
            record for record in cross_supported
            if bool(dict(record.metadata or {}).get('cross_source_hybrid_legal_evidence'))
        ]

        limit = max(1, int(max_items_per_bucket or 1))
        return {
            'top_mixed': [self._record_payload(record) for record in ranked_records[:limit]],
            'top_authorities': [self._record_payload(record) for record in authorities[:limit]],
            'top_evidence': [self._record_payload(record) for record in evidence[:limit]],
            'cross_supported': [self._record_payload(record) for record in cross_supported[:limit]],
            'hybrid_cross_supported': [self._record_payload(record) for record in hybrid_supported[:limit]],
            'summary': {
                'total_records': len(ranked_records),
                'authority_count': len(authorities),
                'evidence_count': len(evidence),
                'cross_supported_count': len(cross_supported),
                'hybrid_cross_supported_count': len(hybrid_supported),
            },
        }
