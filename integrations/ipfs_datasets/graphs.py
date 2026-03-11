from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional

from .loader import import_module_optional


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


def extract_graph_from_text(
    text: str,
    *,
    source_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = metadata or {}
    entities: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []
    artifact_id = source_id or metadata.get("artifact_id") or ""
    claim_element_id = str(metadata.get("claim_element_id") or "").strip()
    claim_element_text = str(metadata.get("claim_element_text") or metadata.get("claim_element") or "").strip()

    if artifact_id:
        entities.append(
            {
                "id": artifact_id,
                "type": "artifact",
                "name": str(metadata.get("title") or metadata.get("filename") or artifact_id),
                "confidence": 1.0,
                "attributes": {
                    "source_id": artifact_id,
                    "source_url": metadata.get("source_url", ""),
                    "mime_type": metadata.get("mime_type", ""),
                },
            }
        )

    claim_node_id = ""
    if claim_element_id or claim_element_text:
        claim_node_id = claim_element_id or _stable_identifier("claim_element", claim_element_text)
        entities.append(
            {
                "id": claim_node_id,
                "type": "claim_element",
                "name": claim_element_text or claim_element_id,
                "confidence": 1.0,
                "attributes": {
                    "claim_element_id": claim_element_id,
                    "claim_element_text": claim_element_text,
                    "claim_type": metadata.get("claim_type", ""),
                },
            }
        )

    sentences = _split_sentences(text)
    if not sentences and text.strip():
        sentences = [text.strip()]

    for index, sentence in enumerate(sentences[:25]):
        fact_id = _stable_identifier("fact", artifact_id or source_id or "text", str(index), sentence)
        entities.append(
            {
                "id": fact_id,
                "type": "fact",
                "name": sentence[:120],
                "confidence": 0.6,
                "attributes": {
                    "text": sentence,
                    "sentence_index": index,
                    "source_id": artifact_id,
                },
            }
        )
        if artifact_id:
            relationships.append(
                {
                    "id": _stable_identifier("rel", artifact_id, fact_id, "has_fact"),
                    "source_id": artifact_id,
                    "target_id": fact_id,
                    "relation_type": "has_fact",
                    "confidence": 1.0,
                    "attributes": {"sentence_index": index},
                }
            )
        if claim_node_id:
            relationships.append(
                {
                    "id": _stable_identifier("rel", fact_id, claim_node_id, "supports"),
                    "source_id": fact_id,
                    "target_id": claim_node_id,
                    "relation_type": "supports",
                    "confidence": 0.6,
                    "attributes": {"sentence_index": index},
                }
            )

    return {
        "status": "available-fallback" if KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable",
        "source_id": source_id or "",
        "entities": entities,
        "relationships": relationships,
        "metadata": {
            **metadata,
            "text_length": len(text),
            "sentence_count": len(sentences),
            "backend_available": KNOWLEDGE_GRAPHS_AVAILABLE,
        },
    }


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

    ranked_results = list(deduped_results.values())

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
    duplicate_fact_count = max(len(facts) - len(ranked_results), 0)

    return {
        "status": "available-fallback" if KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable",
        "claim_element_id": claim_element_id,
        "claim_type": claim_type or "",
        "claim_element_text": claim_element_text or "",
        "graph_id": graph_id or "",
        "results": limited_results,
        "summary": {
            "result_count": len(limited_results),
            "total_fact_count": len(facts),
            "unique_fact_count": len(ranked_results),
            "duplicate_fact_count": duplicate_fact_count,
            "support_by_kind": support_by_kind,
            "support_by_source": support_by_source,
            "max_score": ranked_results[0]["score"] if ranked_results else 0.0,
        },
    }


def persist_graph_snapshot(
    graph_payload: Dict[str, Any],
    *,
    graph_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": "pending" if _graph_storage_module is not None else "noop",
        "graph_id": graph_id or "",
        "persisted": False,
        "node_count": len(graph_payload.get("entities", []) or []),
        "edge_count": len(graph_payload.get("relationships", []) or []),
    }


__all__ = [
    "KNOWLEDGE_GRAPHS_AVAILABLE",
    "GRAPHS_ERROR",
    "extract_graph_from_text",
    "query_graph_support",
    "persist_graph_snapshot",
]