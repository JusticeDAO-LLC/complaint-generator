from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional

from .loader import import_module_optional
from .types import (
    GraphEntity,
    GraphPayload,
    GraphRelationship,
    GraphSnapshotResult,
    GraphSupportMatch,
    GraphSupportResult,
    GraphSupportSummary,
)


_knowledge_graphs_module, _knowledge_graphs_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs"
)
_graph_extraction_module, _graph_extraction_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.extraction"
)
_graph_query_module, _graph_query_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.query"
)
_graph_storage_module, _graph_storage_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.storage"
)
_graph_lineage_module, _graph_lineage_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.lineage"
)

KNOWLEDGE_GRAPHS_AVAILABLE = any(
    value is not None
    for value in (
        _knowledge_graphs_module,
        _graph_extraction_module,
        _graph_query_module,
        _graph_storage_module,
    )
)
GRAPHS_ERROR = (
    _knowledge_graphs_error
    or _graph_extraction_error
    or _graph_query_error
    or _graph_storage_error
    or _graph_lineage_error
)


def _stable_identifier(prefix: str, *parts: str) -> str:
    normalized = "|".join(part.strip() for part in parts if part and part.strip())
    if not normalized:
        return ""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _split_sentences(text: str) -> List[str]:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    return [part.strip() for part in parts if part and part.strip()]


def _tokenize(value: str) -> List[str]:
    return [token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if token]


def _normalize_semantic_token(token: str) -> str:
    normalized = (token or "").lower().strip()
    if not normalized:
        return ""

    canonical_map = {
        "complained": "complain",
        "complaint": "complain",
        "complaints": "complain",
        "filing": "file",
        "filed": "file",
        "files": "file",
        "engaged": "engage",
        "engaging": "engage",
    }
    if normalized in canonical_map:
        return canonical_map[normalized]

    for suffix in ("ing", "ed", "es", "s"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 2:
            return normalized[: -len(suffix)]
    return normalized


def _semantic_token_set(value: str) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "about",
        "by",
        "in",
        "of",
        "the",
        "to",
    }
    return {
        normalized
        for normalized in (_normalize_semantic_token(token) for token in _tokenize(value))
        if normalized and normalized not in stopwords
    }


def _score_fact_match(fact: Dict[str, Any], claim_element_id: str, claim_element_text: str) -> float:
    score = float(fact.get("confidence", 0.0) or 0.0)
    fact_tokens = set(_tokenize(str(fact.get("text") or "")))
    target_tokens = set(_tokenize(claim_element_text))

    if claim_element_id and str(fact.get("claim_element_id") or "") == claim_element_id:
        score += 1.0
    if claim_element_text and str(fact.get("claim_element_text") or "") == claim_element_text:
        score += 1.0
    if fact_tokens and target_tokens:
        overlap = len(fact_tokens & target_tokens)
        score += overlap / max(len(target_tokens), 1)
    return round(score, 4)


def _fact_dedup_key(fact: Dict[str, Any]) -> str:
    text = " ".join(str(fact.get("text") or "").lower().split())
    claim_element_id = str(fact.get("claim_element_id") or "")
    claim_element_text = " ".join(str(fact.get("claim_element_text") or "").lower().split())
    return "|".join([claim_element_id, claim_element_text, text])


def _texts_semantically_similar(left: str, right: str) -> bool:
    left_normalized = " ".join((left or "").lower().split())
    right_normalized = " ".join((right or "").lower().split())
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return True

    left_tokens = _semantic_token_set(left_normalized)
    right_tokens = _semantic_token_set(right_normalized)
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    containment = overlap / max(min(len(left_tokens), len(right_tokens)), 1)
    jaccard = overlap / max(union, 1)
    return containment >= 0.6 or jaccard >= 0.45


def _cluster_semantically_similar_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clusters: List[Dict[str, Any]] = []
    for result in results:
        matched_cluster: Optional[Dict[str, Any]] = None
        for cluster in clusters:
            same_element = (
                str(cluster.get("claim_element_id") or "") == str(result.get("claim_element_id") or "")
                and str(cluster.get("claim_element_text") or "") == str(result.get("claim_element_text") or "")
            )
            if not same_element:
                continue
            if _texts_semantically_similar(str(cluster.get("text") or ""), str(result.get("text") or "")):
                matched_cluster = cluster
                break

        if matched_cluster is None:
            clusters.append(
                {
                    **result,
                    "cluster_size": int(result.get("duplicate_count", 1) or 1),
                    "cluster_texts": [str(result.get("text") or "")],
                }
            )
            continue

        matched_cluster["duplicate_count"] = int(matched_cluster.get("duplicate_count", 1) or 1) + int(result.get("duplicate_count", 1) or 1)
        matched_cluster["cluster_size"] = int(matched_cluster.get("cluster_size", 1) or 1) + int(result.get("duplicate_count", 1) or 1)
        matched_cluster["score"] = max(float(matched_cluster.get("score", 0.0) or 0.0), float(result.get("score", 0.0) or 0.0))
        matched_cluster["confidence"] = max(float(matched_cluster.get("confidence", 0.0) or 0.0), float(result.get("confidence", 0.0) or 0.0))
        if result.get("matched_claim_element"):
            matched_cluster["matched_claim_element"] = True
        if str(result.get("text") or "") not in matched_cluster["cluster_texts"]:
            matched_cluster["cluster_texts"].append(str(result.get("text") or ""))
        for support_kind in result.get("support_kind_set", []) or []:
            if support_kind not in matched_cluster.get("support_kind_set", []):
                matched_cluster.setdefault("support_kind_set", []).append(support_kind)
        for source_table in result.get("source_table_set", []) or []:
            if source_table not in matched_cluster.get("source_table_set", []):
                matched_cluster.setdefault("source_table_set", []).append(source_table)
    return clusters


def extract_graph_from_text(
    text: str,
    *,
    source_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = metadata or {}
    entities: List[GraphEntity] = []
    relationships: List[GraphRelationship] = []
    artifact_id = source_id or metadata.get("artifact_id") or ""
    claim_element_id = str(metadata.get("claim_element_id") or "").strip()
    claim_element_text = str(metadata.get("claim_element_text") or metadata.get("claim_element") or "").strip()

    if artifact_id:
        entities.append(
            GraphEntity(
                entity_id=artifact_id,
                entity_type="artifact",
                name=str(metadata.get("title") or metadata.get("filename") or artifact_id),
                confidence=1.0,
                attributes={
                    "source_id": artifact_id,
                    "source_url": metadata.get("source_url", ""),
                    "mime_type": metadata.get("mime_type", ""),
                },
            )
        )

    claim_node_id = ""
    if claim_element_id or claim_element_text:
        claim_node_id = claim_element_id or _stable_identifier("claim_element", claim_element_text)
        entities.append(
            GraphEntity(
                entity_id=claim_node_id,
                entity_type="claim_element",
                name=claim_element_text or claim_element_id,
                confidence=1.0,
                attributes={
                    "claim_element_id": claim_element_id,
                    "claim_element_text": claim_element_text,
                    "claim_type": metadata.get("claim_type", ""),
                },
            )
        )

    sentences = _split_sentences(text)
    if not sentences and text.strip():
        sentences = [text.strip()]

    for index, sentence in enumerate(sentences[:25]):
        fact_id = _stable_identifier("fact", artifact_id or source_id or "text", str(index), sentence)
        entities.append(
            GraphEntity(
                entity_id=fact_id,
                entity_type="fact",
                name=sentence[:120],
                confidence=0.6,
                attributes={
                    "text": sentence,
                    "sentence_index": index,
                    "source_id": artifact_id,
                },
            )
        )
        if artifact_id:
            relationships.append(
                GraphRelationship(
                    relationship_id=_stable_identifier("rel", artifact_id, fact_id, "has_fact"),
                    source_id=artifact_id,
                    target_id=fact_id,
                    relation_type="has_fact",
                    confidence=1.0,
                    attributes={"sentence_index": index},
                )
            )
        if claim_node_id:
            relationships.append(
                GraphRelationship(
                    relationship_id=_stable_identifier("rel", fact_id, claim_node_id, "supports"),
                    source_id=fact_id,
                    target_id=claim_node_id,
                    relation_type="supports",
                    confidence=0.6,
                    attributes={"sentence_index": index},
                )
            )

    return GraphPayload(
        status="available-fallback" if KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable",
        source_id=source_id or "",
        entities=entities,
        relationships=relationships,
        metadata={
            **metadata,
            "text_length": len(text),
            "sentence_count": len(sentences),
            "backend_available": KNOWLEDGE_GRAPHS_AVAILABLE,
        },
    ).as_dict()


def query_graph_support(
    claim_element_id: str,
    *,
    graph_id: Optional[str] = None,
    support_facts: Optional[List[Dict[str, Any]]] = None,
    claim_type: Optional[str] = None,
    claim_element_text: Optional[str] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    facts = support_facts or []
    ranked_results = []
    support_by_kind: Dict[str, int] = {}
    support_by_source: Dict[str, int] = {}
    deduped_results: Dict[str, Dict[str, Any]] = {}

    for fact in facts:
        score = _score_fact_match(fact, claim_element_id, claim_element_text or "")
        result = {
            **fact,
            "score": score,
            "matched_claim_element": bool(
                (claim_element_id and str(fact.get("claim_element_id") or "") == claim_element_id)
                or (claim_element_text and str(fact.get("claim_element_text") or "") == claim_element_text)
            ),
            "duplicate_count": 1,
        }
        support_kind = str(fact.get("support_kind") or "unknown")
        source_table = str(fact.get("source_table") or "unknown")
        support_by_kind[support_kind] = support_by_kind.get(support_kind, 0) + 1
        support_by_source[source_table] = support_by_source.get(source_table, 0) + 1

        dedup_key = _fact_dedup_key(result)
        existing = deduped_results.get(dedup_key)
        if existing is None:
            deduped_results[dedup_key] = {
                **result,
                "support_kind_set": [support_kind],
                "source_table_set": [source_table],
            }
            continue

        existing["duplicate_count"] += 1
        existing["score"] = max(existing.get("score", 0.0), result["score"])
        existing["confidence"] = max(existing.get("confidence", 0.0), result.get("confidence", 0.0))
        if support_kind not in existing["support_kind_set"]:
            existing["support_kind_set"].append(support_kind)
        if source_table not in existing["source_table_set"]:
            existing["source_table_set"].append(source_table)

    ranked_results = _cluster_semantically_similar_results(list(deduped_results.values()))

    ranked_results.sort(
        key=lambda item: (
            item.get("score", 0.0),
            item.get("matched_claim_element", False),
            item.get("confidence", 0.0),
            item.get("duplicate_count", 0),
        ),
        reverse=True,
    )

    limited_results = ranked_results[:max_results]
    unique_fact_count = len(deduped_results)
    duplicate_fact_count = max(len(facts) - unique_fact_count, 0)
    semantic_cluster_count = len(ranked_results)
    semantic_duplicate_count = max(unique_fact_count - semantic_cluster_count, 0)

    typed_results = [
        GraphSupportMatch(
            fact_id=str(item.get("fact_id") or ""),
            text=str(item.get("text") or ""),
            score=float(item.get("score", 0.0) or 0.0),
            confidence=float(item.get("confidence", 0.0) or 0.0),
            matched_claim_element=bool(item.get("matched_claim_element", False)),
            duplicate_count=int(item.get("duplicate_count", 1) or 1),
            cluster_size=int(item.get("cluster_size", item.get("duplicate_count", 1)) or 1),
            cluster_texts=[str(text) for text in item.get("cluster_texts", []) or []],
            support_kind=str(item.get("support_kind") or ""),
            source_table=str(item.get("source_table") or ""),
            support_kind_set=[str(kind) for kind in item.get("support_kind_set", []) or []],
            source_table_set=[str(source) for source in item.get("source_table_set", []) or []],
            claim_element_id=str(item.get("claim_element_id") or ""),
            claim_element_text=str(item.get("claim_element_text") or ""),
            support_ref=str(item.get("support_ref") or ""),
            support_label=str(item.get("support_label") or ""),
            evidence_record_id=item.get("evidence_record_id"),
            authority_record_id=item.get("authority_record_id"),
            metadata={
                key: value
                for key, value in item.items()
                if key not in {
                    "fact_id",
                    "text",
                    "score",
                    "confidence",
                    "matched_claim_element",
                    "duplicate_count",
                    "cluster_size",
                    "cluster_texts",
                    "support_kind",
                    "source_table",
                    "support_kind_set",
                    "source_table_set",
                    "claim_element_id",
                    "claim_element_text",
                    "support_ref",
                    "support_label",
                    "evidence_record_id",
                    "authority_record_id",
                }
            },
        )
        for item in limited_results
    ]

    return GraphSupportResult(
        status="available-fallback" if KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable",
        claim_element_id=claim_element_id,
        claim_type=claim_type or "",
        claim_element_text=claim_element_text or "",
        graph_id=graph_id or "",
        results=typed_results,
        summary=GraphSupportSummary(
            result_count=len(limited_results),
            total_fact_count=len(facts),
            unique_fact_count=unique_fact_count,
            duplicate_fact_count=duplicate_fact_count,
            semantic_cluster_count=semantic_cluster_count,
            semantic_duplicate_count=semantic_duplicate_count,
            support_by_kind=support_by_kind,
            support_by_source=support_by_source,
            max_score=ranked_results[0]["score"] if ranked_results else 0.0,
        ),
        metadata={
            "backend_available": KNOWLEDGE_GRAPHS_AVAILABLE,
        },
    ).as_dict()


def persist_graph_snapshot(
    graph_payload: Dict[str, Any],
    *,
    graph_id: Optional[str] = None,
    graph_changed: Optional[bool] = None,
    existing_graph: bool = False,
    persistence_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    entity_count = len(graph_payload.get("entities", []) or []) if isinstance(graph_payload, dict) else 0
    relationship_count = len(graph_payload.get("relationships", []) or []) if isinstance(graph_payload, dict) else 0
    source_id = str(graph_payload.get("source_id") or "") if isinstance(graph_payload, dict) else ""
    metadata = graph_payload.get("metadata", {}) if isinstance(graph_payload, dict) and isinstance(graph_payload.get("metadata"), dict) else {}
    derived_graph_changed = bool(graph_changed) if graph_changed is not None else bool(entity_count or relationship_count) and not existing_graph
    created = bool(derived_graph_changed and not existing_graph)
    reused = bool(existing_graph and not created)
    stable_graph_id = graph_id or _stable_identifier(
        "graph",
        source_id,
        str(entity_count),
        str(relationship_count),
        str(metadata.get("text_length") or ""),
    )
    return GraphSnapshotResult(
        status="pending" if _graph_storage_module is not None else "noop",
        graph_id=stable_graph_id,
        persisted=False,
        created=created,
        reused=reused,
        node_count=entity_count,
        edge_count=relationship_count,
        metadata={
            "source_id": source_id,
            "backend_available": _graph_storage_module is not None,
            **(persistence_metadata or {}),
            "lineage": {
                "status": str(graph_payload.get("status") or "") if isinstance(graph_payload, dict) else "",
                "text_length": metadata.get("text_length", 0),
                "sentence_count": metadata.get("sentence_count", 0),
            },
        },
    ).as_dict()


__all__ = [
    "KNOWLEDGE_GRAPHS_AVAILABLE",
    "GRAPHS_ERROR",
    "extract_graph_from_text",
    "query_graph_support",
    "persist_graph_snapshot",
]