import hashlib
import re
import time
from typing import Any, Dict, List, Set


class GraphRetrievalAugmentor:
    """Builds graph-ingestable evidence payloads from normalized retrieval artifacts."""

    def build_evidence_payloads(
        self,
        legal_normalized: List[Dict[str, Any]],
        web_normalized: List[Dict[str, Any]],
        claim_ids: List[str],
        max_items: int = 20,
    ) -> List[Dict[str, Any]]:
        payloads: List[Dict[str, Any]] = []
        seen_ids = set()

        def _make_id(prefix: str, value: str, index: int) -> str:
            cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)[:48]
            return f"{prefix}_{cleaned}_{index}"

        for index, item in enumerate(legal_normalized[:max_items]):
            title = str(item.get("title", "") or item.get("citation", "") or "Legal authority")
            record_id = _make_id("legal", title, index)
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)

            confidence = float(item.get("confidence", item.get("score", 0.6)) or 0.6)
            payloads.append(
                {
                    "id": record_id,
                    "name": title,
                    "type": "legal_authority",
                    "description": str(item.get("snippet", "") or item.get("content", "") or ""),
                    "confidence": confidence,
                    "relevance": confidence,
                    "supports_claims": claim_ids,
                    "source_type": "normalized_legal_authority",
                    "metadata": dict(item.get("metadata", {}) or {}),
                }
            )

        remaining = max(0, max_items - len(payloads))
        for index, item in enumerate(web_normalized[:remaining]):
            title = str(item.get("title", "") or item.get("url", "") or "Web evidence")
            record_id = _make_id("web", title, index)
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)

            confidence = float(item.get("confidence", item.get("score", 0.5)) or 0.5)
            payloads.append(
                {
                    "id": record_id,
                    "name": title,
                    "type": "web_evidence",
                    "description": str(item.get("snippet", "") or item.get("content", "") or ""),
                    "confidence": confidence,
                    "relevance": confidence,
                    "supports_claims": claim_ids,
                    "source_type": "normalized_web_evidence",
                    "metadata": dict(item.get("metadata", {}) or {}),
                }
            )

        return payloads


class GraphAwareRetrievalReranker:
    """Applies graph-context-aware score adjustments to normalized retrieval records."""

    _TOKEN_RE = re.compile(r"[a-z0-9_]+")

    def _tokenize(self, text: str) -> Set[str]:
        return {tok for tok in self._TOKEN_RE.findall((text or "").lower()) if len(tok) > 2}

    def should_apply_canary(self, seed: str, percent: int) -> bool:
        pct = max(0, min(100, int(percent)))
        if pct <= 0:
            return False
        if pct >= 100:
            return True

        digest = hashlib.sha256((seed or "").encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 100
        return bucket < pct

    def _extract_readiness_context(self, mediator: Any) -> Dict[str, Any]:
        phase_manager = getattr(mediator, "phase_manager", None)
        if phase_manager is None:
            return {
                "overall_readiness": 1.0,
                "priority_terms": [],
            }

        try:
            from complaint_phases import ComplaintPhase
        except Exception:
            return {
                "overall_readiness": 1.0,
                "priority_terms": [],
            }

        dg = None
        try:
            dg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
        except Exception:
            dg = None

        if dg is None:
            return {
                "overall_readiness": 1.0,
                "priority_terms": [],
            }

        overall_readiness = 1.0
        priority_terms: List[str] = []

        try:
            readiness = dg.get_claim_readiness() if hasattr(dg, "get_claim_readiness") else {}
            if isinstance(readiness, dict):
                readiness_value = readiness.get("overall_readiness", 1.0)
                overall_readiness = 1.0 if readiness_value is None else float(readiness_value)
                for claim in readiness.get("incomplete_claim_details", []) or []:
                    if not isinstance(claim, dict):
                        continue
                    claim_name = str(claim.get("claim_name", "") or "")
                    if claim_name:
                        priority_terms.append(claim_name)
        except Exception:
            pass

        try:
            unsatisfied = (
                dg.find_unsatisfied_requirements()
                if hasattr(dg, "find_unsatisfied_requirements")
                else []
            )
            for item in unsatisfied or []:
                if not isinstance(item, dict):
                    continue
                node_name = str(item.get("node_name", "") or "")
                if node_name:
                    priority_terms.append(node_name)
                for missing in item.get("missing_dependencies", []) or []:
                    if not isinstance(missing, dict):
                        continue
                    source_name = str(missing.get("source_name", "") or "")
                    if source_name and source_name.lower() != "unknown":
                        priority_terms.append(source_name)
        except Exception:
            pass

        return {
            "overall_readiness": max(0.0, min(1.0, overall_readiness)),
            "priority_terms": priority_terms,
        }

    def extract_graph_terms(self, mediator: Any, max_terms: int = 200) -> List[str]:
        phase_manager = getattr(mediator, "phase_manager", None)
        if phase_manager is None:
            return []

        try:
            from complaint_phases import ComplaintPhase, NodeType
        except Exception:
            return []

        terms: List[str] = []

        try:
            kg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
            if kg is not None and hasattr(kg, "get_entities_by_type"):
                for entity_type in ("claim", "fact", "organization"):
                    entities = kg.get_entities_by_type(entity_type) or []
                    for entity in entities:
                        name = str(getattr(entity, "name", "") or "")
                        if name:
                            terms.append(name)
                        attrs = getattr(entity, "attributes", {}) or {}
                        for value in attrs.values():
                            if isinstance(value, str):
                                terms.append(value)
        except Exception:
            pass

        try:
            dg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
            if dg is not None and hasattr(dg, "get_nodes_by_type"):
                claim_nodes = dg.get_nodes_by_type(NodeType.CLAIM) or []
                for node in claim_nodes:
                    node_name = str(getattr(node, "name", "") or "")
                    node_description = str(getattr(node, "description", "") or "")
                    if node_name:
                        terms.append(node_name)
                    if node_description:
                        terms.append(node_description)
        except Exception:
            pass

        try:
            legal_graph = phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, "legal_graph")
            if legal_graph is not None and hasattr(legal_graph, "elements"):
                for element in list(getattr(legal_graph, "elements", {}).values())[:50]:
                    element_name = str(getattr(element, "name", "") or "")
                    element_description = str(getattr(element, "description", "") or "")
                    if element_name:
                        terms.append(element_name)
                    if element_description:
                        terms.append(element_description)
        except Exception:
            pass

        deduped: List[str] = []
        seen = set()
        for term in terms:
            cleaned = " ".join(term.strip().split())
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(cleaned)
            if len(deduped) >= max_terms:
                break

        return deduped

    def augment_normalized_records(
        self,
        records: List[Dict[str, Any]],
        query: str,
        mediator: Any,
        max_boost: float = 0.12,
        enable_optimizer: bool = False,
        retrieval_max_latency_ms: int = 1500,
    ) -> List[Dict[str, Any]]:
        started = time.perf_counter()
        graph_terms = self.extract_graph_terms(mediator=mediator)
        if not graph_terms:
            return records

        graph_tokens = set()
        for term in graph_terms:
            graph_tokens.update(self._tokenize(term))

        if not graph_tokens:
            return records

        query_tokens = self._tokenize(query)
        effective_graph_tokens = graph_tokens | query_tokens
        readiness_context = self._extract_readiness_context(mediator=mediator)
        readiness_value = readiness_context.get("overall_readiness", 1.0)
        overall_readiness = 1.0 if readiness_value is None else float(readiness_value)
        readiness_gap = max(0.0, min(1.0, 1.0 - overall_readiness))

        priority_tokens = set()
        for term in readiness_context.get("priority_terms", []) or []:
            priority_tokens.update(self._tokenize(str(term)))

        effective_priority_tokens = priority_tokens | query_tokens if priority_tokens else query_tokens
        effective_max_boost = max_boost
        if enable_optimizer:
            priority_term_count = len(readiness_context.get("priority_terms", []) or [])
            tuned = max_boost * (1.0 + (0.5 * readiness_gap))
            tuned += min(0.04, priority_term_count * 0.002)
            effective_max_boost = min(0.2, tuned)

        latency_guard_applied = False
        latency_scale = 1.0
        if retrieval_max_latency_ms <= 100:
            latency_scale = 0.5
            latency_guard_applied = True
        elif retrieval_max_latency_ms <= 250:
            latency_scale = 0.7
            latency_guard_applied = True
        elif retrieval_max_latency_ms <= 500 and len(records) > 20:
            latency_scale = 0.85
            latency_guard_applied = True

        effective_max_boost *= latency_scale

        boost_values: List[float] = []

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
            text_tokens = self._tokenize(merged_text)
            overlap = len(text_tokens & effective_graph_tokens)
            overlap_ratio = overlap / max(1, len(effective_graph_tokens))
            priority_overlap = len(text_tokens & effective_priority_tokens)
            priority_ratio = priority_overlap / max(1, len(effective_priority_tokens))

            graph_boost = overlap_ratio * effective_max_boost * 3
            readiness_boost = priority_ratio * effective_max_boost * (1.0 + readiness_gap)
            boost = min(effective_max_boost, graph_boost + readiness_boost)
            boost_values.append(boost)

            candidate = dict(record)
            base_score = float(candidate.get("score", 0.0) or 0.0)
            base_confidence = float(candidate.get("confidence", base_score) or 0.0)
            candidate["score"] = min(1.0, base_score + boost)
            candidate["confidence"] = min(1.0, max(base_confidence, candidate["score"]))

            metadata = dict(candidate.get("metadata", {}) or {})
            metadata.update(
                {
                    "graph_reranked": True,
                    "graph_overlap": overlap,
                    "graph_overlap_ratio": round(overlap_ratio, 4),
                    "graph_terms_count": len(graph_terms),
                    "graph_priority_overlap": priority_overlap,
                    "graph_priority_ratio": round(priority_ratio, 4),
                    "graph_priority_terms_count": len(readiness_context.get("priority_terms", []) or []),
                    "graph_readiness_gap": round(readiness_gap, 4),
                    "graph_optimizer_tuned": bool(enable_optimizer),
                    "graph_effective_max_boost": round(effective_max_boost, 4),
                    "graph_applied_boost": round(boost, 4),
                    "graph_latency_budget_ms": int(retrieval_max_latency_ms),
                    "graph_latency_guard_applied": latency_guard_applied,
                }
            )
            candidate["metadata"] = metadata
            augmented.append(candidate)

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        avg_boost = (sum(boost_values) / len(boost_values)) if boost_values else 0.0
        boosted_count = sum(1 for value in boost_values if value > 0.0)
        for candidate in augmented:
            metadata = dict(candidate.get("metadata", {}) or {})
            metadata.update(
                {
                    "graph_run_elapsed_ms": round(elapsed_ms, 3),
                    "graph_run_avg_boost": round(avg_boost, 4),
                    "graph_run_boosted_count": boosted_count,
                }
            )
            candidate["metadata"] = metadata

        return augmented
