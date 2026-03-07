import importlib
from typing import Any, Dict, Iterable, List, Optional


def _tokenize(text: str) -> set[str]:
    cleaned = ''.join(ch.lower() if ch.isalnum() or ch.isspace() else ' ' for ch in text)
    return {part for part in cleaned.split() if part}


class VectorRetrievalAugmentor:
    """Lightweight vector-ready score augmentation.

    This Phase 2 starter does not require a hard dependency on a vector DB.
    It uses optional capability detection and lexical-overlap hints to provide
    stable ranking improvements when `enhanced_vector` is enabled.
    """

    def __init__(self):
        self.embeddings_available = self._module_available(
            "ipfs_datasets_py.embeddings_router"
        ) or self._module_available("ipfs_datasets_py.search.search_embeddings")

    @staticmethod
    def _module_available(module_name: str) -> bool:
        try:
            importlib.import_module(module_name)
            return True
        except Exception:
            return False

    def capabilities(self) -> Dict[str, Any]:
        return {
            "embeddings_available": self.embeddings_available,
            "mode": "heuristic-vector-hints",
        }

    def augment_normalized_records(
        self,
        records: List[Dict[str, Any]],
        query: str,
        context_texts: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        query_tokens = _tokenize(query)
        context_tokens = set()
        for item in context_texts or []:
            context_tokens.update(_tokenize(str(item or "")))

        if not query_tokens and not context_tokens:
            return records

        augmented: List[Dict[str, Any]] = []
        for record in records:
            merged_text = " ".join(
                [
                    str(record.get("title", "") or ""),
                    str(record.get("snippet", "") or ""),
                    str(record.get("content", "") or ""),
                    str(record.get("citation", "") or ""),
                ]
            )
            text_tokens = _tokenize(merged_text)
            overlap = len(query_tokens & text_tokens)
            overlap_ratio = overlap / max(1, len(query_tokens))
            boost = min(0.15, overlap_ratio * 0.15)

            context_overlap = len(context_tokens & text_tokens)
            context_overlap_ratio = context_overlap / max(1, len(context_tokens)) if context_tokens else 0.0
            context_boost = min(0.18, max(context_overlap_ratio * 0.12, context_overlap * 0.03))
            boost += context_boost

            candidate = dict(record)
            base_score = float(candidate.get("score", 0.0) or 0.0)
            base_confidence = float(candidate.get("confidence", base_score) or 0.0)
            candidate["score"] = min(1.0, base_score + boost)
            candidate["confidence"] = min(1.0, max(base_confidence, candidate["score"]))

            metadata = dict(candidate.get("metadata", {}) or {})
            metadata.update(
                {
                    "vector_augmented": True,
                    "vector_hint_overlap": overlap,
                    "vector_hint_ratio": round(overlap_ratio, 4),
                    "evidence_similarity_overlap": context_overlap,
                    "evidence_similarity_score": round(context_overlap_ratio, 4),
                    "evidence_similarity_boost": round(context_boost, 6),
                    "evidence_similarity_applied": bool(context_tokens),
                    "vector_embeddings_available": self.embeddings_available,
                }
            )
            candidate["metadata"] = metadata
            augmented.append(candidate)

        return augmented
