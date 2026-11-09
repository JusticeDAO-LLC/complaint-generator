"""Trace and lineage payload helpers for claim support orchestration."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


CONTENT_ORIGIN_ARTIFACT_FAMILY = {
    'historical_archive_capture': 'archived_web_page',
    'live_web_capture': 'live_web_page',
    'authority_full_text': 'legal_authority_text',
    'authority_reference_fallback': 'legal_authority_reference',
}

ARTIFACT_FAMILY_CORPUS_FAMILY = {
    'archived_web_page': 'web_page',
    'live_web_page': 'web_page',
    'legal_authority_text': 'legal_authority',
    'legal_authority_reference': 'legal_authority',
}


def resolve_artifact_identity(
    *,
    content_origin: str = '',
    artifact_family: str = '',
    corpus_family: str = '',
    content_origin_artifact_family: Optional[Dict[str, str]] = None,
    artifact_family_corpus_family: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    content_origin_map = content_origin_artifact_family or CONTENT_ORIGIN_ARTIFACT_FAMILY
    corpus_family_map = artifact_family_corpus_family or ARTIFACT_FAMILY_CORPUS_FAMILY
    resolved_artifact_family = artifact_family or content_origin_map.get(content_origin, '')
    resolved_corpus_family = corpus_family or corpus_family_map.get(resolved_artifact_family, '')
    return {
        'artifact_family': resolved_artifact_family,
        'corpus_family': resolved_corpus_family,
    }


def normalize_graph_summary(
    *,
    graph_payload: Optional[Dict[str, Any]] = None,
    default_status: str = '',
    default_entity_count: int = 0,
    default_relationship_count: int = 0,
) -> Dict[str, Any]:
    if isinstance(graph_payload, dict):
        return {
            'status': graph_payload.get('status', default_status),
            'entity_count': len(graph_payload.get('entities', []) or []),
            'relationship_count': len(graph_payload.get('relationships', []) or []),
        }
    return {
        'status': default_status,
        'entity_count': default_entity_count,
        'relationship_count': default_relationship_count,
    }


def build_graph_trace(
    *,
    source_table: Optional[str],
    support_ref: Optional[str],
    record_id: Optional[int],
    graph_summary: Dict[str, Any],
    graph_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_metadata = graph_metadata if isinstance(graph_metadata, dict) else {}
    snapshot = normalized_metadata.get('graph_snapshot', {})
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    adapter_metadata = {
        key: value
        for key, value in normalized_metadata.items()
        if key != 'graph_snapshot'
    }
    lineage = snapshot.get('metadata', {}) if isinstance(snapshot.get('metadata'), dict) else {}
    return {
        'source_table': source_table or '',
        'support_ref': support_ref or '',
        'record_id': record_id,
        'summary': graph_summary,
        'snapshot': snapshot,
        'metadata': adapter_metadata,
        'lineage': lineage.get('lineage', {}) if isinstance(lineage.get('lineage'), dict) else {},
    }


def summarize_graph_traces(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    traced_link_count = 0
    snapshot_created_count = 0
    snapshot_reused_count = 0
    source_table_counts: Dict[str, int] = {}
    graph_status_counts: Dict[str, int] = {}
    seen_graph_ids = set()

    for item in items or []:
        if not isinstance(item, dict):
            continue
        graph_trace = item.get('graph_trace', {})
        if not isinstance(graph_trace, dict) or not graph_trace:
            continue
        traced_link_count += 1

        source_table = str(graph_trace.get('source_table') or 'unknown')
        source_table_counts[source_table] = source_table_counts.get(source_table, 0) + 1

        summary = graph_trace.get('summary', {})
        if isinstance(summary, dict):
            graph_status = str(summary.get('status') or 'unknown')
            graph_status_counts[graph_status] = graph_status_counts.get(graph_status, 0) + 1

        snapshot = graph_trace.get('snapshot', {})
        if isinstance(snapshot, dict):
            if bool(snapshot.get('created')):
                snapshot_created_count += 1
            if bool(snapshot.get('reused')):
                snapshot_reused_count += 1
            graph_id = str(snapshot.get('graph_id') or '')
            if graph_id:
                seen_graph_ids.add(graph_id)

    return {
        'traced_link_count': traced_link_count,
        'snapshot_created_count': snapshot_created_count,
        'snapshot_reused_count': snapshot_reused_count,
        'source_table_counts': source_table_counts,
        'graph_status_counts': graph_status_counts,
        'graph_id_count': len(seen_graph_ids),
    }


def build_support_trace(
    *,
    link: Dict[str, Any],
    fact: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    fact = fact if isinstance(fact, dict) else {}
    graph_trace = link.get('graph_trace', {}) if isinstance(link.get('graph_trace'), dict) else {}
    graph_summary = link.get('graph_summary', {}) if isinstance(link.get('graph_summary'), dict) else {}
    record_summary = link.get('record_summary', {}) if isinstance(link.get('record_summary'), dict) else {}
    record_parse_summary = record_summary.get('parse_summary', {}) if isinstance(record_summary.get('parse_summary'), dict) else {}
    fact_metadata = fact.get('metadata', {}) if isinstance(fact.get('metadata'), dict) else {}
    parse_lineage = fact_metadata.get('parse_lineage', {}) if isinstance(fact_metadata.get('parse_lineage'), dict) else {}
    snapshot = graph_trace.get('snapshot', {}) if isinstance(graph_trace.get('snapshot'), dict) else {}
    source_ref = link.get('support_ref') or parse_lineage.get('source_ref') or ''
    source_table = str(link.get('source_table') or '')
    source_family = str(fact.get('source_family') or parse_lineage.get('record_scope') or '')
    if not source_family:
        source_family = 'legal_authority' if source_table == 'legal_authorities' else source_table or str(link.get('support_kind') or '')
    source_record_id = fact.get('source_record_id')
    if source_record_id is None:
        if source_family == 'legal_authority':
            source_record_id = link.get('authority_record_id')
        elif source_family == 'claim_testimony':
            source_record_id = link.get('testimony_record_id')
        else:
            source_record_id = link.get('evidence_record_id')
    artifact_family = str(fact.get('artifact_family') or parse_lineage.get('artifact_family') or record_parse_summary.get('artifact_family') or '')
    corpus_family = str(fact.get('corpus_family') or parse_lineage.get('corpus_family') or record_parse_summary.get('corpus_family') or '')
    content_origin = str(fact.get('content_origin') or parse_lineage.get('content_origin') or record_parse_summary.get('content_origin') or '')
    parse_quality = parse_lineage.get('parse_quality', {}) if isinstance(parse_lineage.get('parse_quality'), dict) else {}
    source_span = parse_lineage.get('source_span', {}) if isinstance(parse_lineage.get('source_span'), dict) else {}

    return {
        'claim_type': link.get('claim_type'),
        'claim_element_id': link.get('claim_element_id'),
        'claim_element_text': link.get('claim_element_text'),
        'support_kind': link.get('support_kind'),
        'support_ref': link.get('support_ref'),
        'support_label': link.get('support_label'),
        'source_table': link.get('source_table'),
        'source_family': source_family,
        'source_record_id': source_record_id,
        'source_ref': str(fact.get('source_ref') or parse_lineage.get('source_ref') or source_ref),
        'record_scope': str(fact.get('record_scope') or parse_lineage.get('record_scope') or source_family),
        'artifact_family': artifact_family,
        'corpus_family': corpus_family,
        'content_origin': content_origin,
        'parse_source': str(fact.get('parse_source') or parse_lineage.get('source') or record_parse_summary.get('source') or ''),
        'input_format': str(fact.get('input_format') or parse_lineage.get('input_format') or record_parse_summary.get('input_format') or ''),
        'quality_tier': str(fact.get('quality_tier') or parse_lineage.get('quality_tier') or record_parse_summary.get('quality_tier') or ''),
        'quality_score': float(fact.get('quality_score') or parse_lineage.get('quality_score') or record_parse_summary.get('quality_score') or parse_quality.get('quality_score') or 0.0),
        'page_count': int(fact.get('page_count') or parse_lineage.get('page_count') or record_parse_summary.get('page_count') or source_span.get('page_count') or 0),
        'support_strength': link.get('support_strength', 0.0),
        'record_id': graph_trace.get('record_id') or link.get('evidence_record_id') or link.get('authority_record_id') or link.get('testimony_record_id'),
        'fact_id': fact.get('fact_id', ''),
        'fact_text': fact.get('text', ''),
        'confidence': fact.get('confidence', 0.0),
        'trace_kind': 'fact' if fact.get('fact_id') else 'link',
        'parse_lineage': parse_lineage,
        'source_lineage_ref': source_ref,
        'record_summary': record_summary,
        'graph_summary': graph_summary,
        'graph_trace': graph_trace,
        'graph_id': snapshot.get('graph_id', ''),
        'evidence_record_id': link.get('evidence_record_id'),
        'authority_record_id': link.get('authority_record_id'),
        'testimony_record_id': link.get('testimony_record_id'),
    }


def extract_record_parse_summary(
    record: Optional[Dict[str, Any]],
    *,
    artifact_identity_resolver: Callable[..., Dict[str, str]] = resolve_artifact_identity,
) -> Dict[str, Any]:
    payload = record if isinstance(record, dict) else {}
    parse_metadata = payload.get('parse_metadata', {}) if isinstance(payload.get('parse_metadata'), dict) else {}
    transform_lineage = parse_metadata.get('transform_lineage', {}) if isinstance(parse_metadata.get('transform_lineage'), dict) else {}
    provenance_payload = payload.get('provenance', {}) if isinstance(payload.get('provenance'), dict) else {}
    if not provenance_payload and isinstance(payload.get('metadata'), dict):
        metadata_provenance = payload['metadata'].get('provenance')
        if isinstance(metadata_provenance, dict):
            provenance_payload = metadata_provenance
    provenance_metadata = provenance_payload.get('metadata', {}) if isinstance(provenance_payload.get('metadata'), dict) else {}
    source_span = parse_metadata.get('source_span', {}) if isinstance(parse_metadata.get('source_span'), dict) else {}
    parse_quality = parse_metadata.get('parse_quality', {}) if isinstance(parse_metadata.get('parse_quality'), dict) else {}

    input_format = str(parse_metadata.get('input_format') or transform_lineage.get('input_format') or provenance_metadata.get('input_format') or '')
    extraction_method = str(parse_metadata.get('extraction_method') or transform_lineage.get('normalization') or '')
    quality_tier = str(parse_metadata.get('quality_tier') or parse_quality.get('quality_tier') or '')
    quality_score = float(parse_metadata.get('quality_score') or parse_quality.get('quality_score') or 0.0)
    page_count = int(parse_metadata.get('page_count', source_span.get('page_count', 0)) or 0)
    content_origin = str(parse_metadata.get('content_origin') or transform_lineage.get('content_origin') or provenance_metadata.get('content_origin') or '')
    artifact_family = str(parse_metadata.get('artifact_family') or transform_lineage.get('artifact_family') or provenance_metadata.get('artifact_family') or '')
    corpus_family = str(parse_metadata.get('corpus_family') or transform_lineage.get('corpus_family') or provenance_metadata.get('corpus_family') or '')

    artifact_identity = artifact_identity_resolver(
        content_origin=content_origin,
        artifact_family=artifact_family,
        corpus_family=corpus_family,
    )
    artifact_family = artifact_identity['artifact_family']
    corpus_family = artifact_identity['corpus_family']

    return {
        'parse_status': payload.get('parse_status'),
        'chunk_count': int(payload.get('chunk_count', 0) or 0),
        'corpus_family': corpus_family,
        'artifact_family': artifact_family,
        'input_format': input_format,
        'extraction_method': extraction_method,
        'quality_tier': quality_tier,
        'quality_score': quality_score,
        'page_count': page_count,
        'source': str(parse_metadata.get('source') or transform_lineage.get('source') or ''),
        'content_origin': content_origin,
        'historical_capture': bool(parse_metadata.get('historical_capture', transform_lineage.get('historical_capture', provenance_metadata.get('historical_capture', False)))),
        'capture_source': str(parse_metadata.get('capture_source') or transform_lineage.get('capture_source') or provenance_metadata.get('capture_source') or ''),
        'archive_url': str(parse_metadata.get('archive_url') or transform_lineage.get('archive_url') or provenance_metadata.get('archive_url') or ''),
        'original_url': str(parse_metadata.get('original_url') or transform_lineage.get('original_url') or provenance_metadata.get('original_url') or ''),
        'version_of': str(parse_metadata.get('version_of') or transform_lineage.get('version_of') or provenance_metadata.get('version_of') or ''),
        'captured_at': str(parse_metadata.get('captured_at') or transform_lineage.get('captured_at') or provenance_metadata.get('captured_at') or ''),
        'observed_at': str(parse_metadata.get('observed_at') or transform_lineage.get('observed_at') or provenance_metadata.get('observed_at') or ''),
        'content_source_field': str(parse_metadata.get('content_source_field') or transform_lineage.get('content_source_field') or provenance_metadata.get('content_source_field') or ''),
        'fallback_mode': str(parse_metadata.get('fallback_mode') or transform_lineage.get('fallback_mode') or provenance_metadata.get('fallback_mode') or ''),
        'parsed_text_preview': str(payload.get('parsed_text_preview') or ''),
        'source_span': dict(source_span),
    }


def build_support_packet_lineage_summary(
    *,
    trace: Dict[str, Any],
) -> Dict[str, Any]:
    parse_lineage = trace.get('parse_lineage', {}) if isinstance(trace.get('parse_lineage'), dict) else {}
    record_summary = trace.get('record_summary', {}) if isinstance(trace.get('record_summary'), dict) else {}
    record_parse_summary = record_summary.get('parse_summary', {}) if isinstance(record_summary.get('parse_summary'), dict) else {}
    source_span = parse_lineage.get('source_span') if isinstance(parse_lineage.get('source_span'), dict) else record_parse_summary.get('source_span', {}) if isinstance(record_parse_summary.get('source_span'), dict) else {}

    return {
        'corpus_family': str(parse_lineage.get('corpus_family') or record_parse_summary.get('corpus_family') or ''),
        'artifact_family': str(parse_lineage.get('artifact_family') or record_parse_summary.get('artifact_family') or ''),
        'source': str(parse_lineage.get('source') or record_parse_summary.get('source') or ''),
        'input_format': str(parse_lineage.get('input_format') or record_parse_summary.get('input_format') or ''),
        'parser_version': str(parse_lineage.get('parser_version') or ''),
        'content_origin': str(parse_lineage.get('content_origin') or record_parse_summary.get('content_origin') or ''),
        'historical_capture': bool(parse_lineage.get('historical_capture', record_parse_summary.get('historical_capture', False))),
        'capture_source': str(parse_lineage.get('capture_source') or record_parse_summary.get('capture_source') or ''),
        'archive_url': str(parse_lineage.get('archive_url') or record_parse_summary.get('archive_url') or ''),
        'original_url': str(parse_lineage.get('original_url') or record_parse_summary.get('original_url') or ''),
        'version_of': str(parse_lineage.get('version_of') or record_parse_summary.get('version_of') or ''),
        'captured_at': str(parse_lineage.get('captured_at') or record_parse_summary.get('captured_at') or ''),
        'observed_at': str(parse_lineage.get('observed_at') or record_parse_summary.get('observed_at') or ''),
        'content_source_field': str(parse_lineage.get('content_source_field') or record_parse_summary.get('content_source_field') or ''),
        'fallback_mode': str(parse_lineage.get('fallback_mode') or record_parse_summary.get('fallback_mode') or ''),
        'quality_tier': str(record_parse_summary.get('quality_tier') or parse_lineage.get('quality_tier') or ''),
        'quality_score': float(record_parse_summary.get('quality_score') or parse_lineage.get('quality_score') or 0.0),
        'page_count': int(record_parse_summary.get('page_count', 0) or 0),
        'source_span': dict(source_span),
    }
