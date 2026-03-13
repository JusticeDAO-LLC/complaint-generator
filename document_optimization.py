from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Dict, List, Optional, Tuple

try:
    from integrations.ipfs_datasets.llm import generate_text_with_metadata
except Exception:
    def generate_text_with_metadata(*args, **kwargs):
        return {"status": "unavailable", "text": ""}

try:
    from integrations.ipfs_datasets.storage import IPFS_AVAILABLE, store_bytes
except Exception:
    IPFS_AVAILABLE = False

    def store_bytes(data: bytes, *, pin_content: bool = True):
        return {"status": "disabled", "cid": "", "size": len(data), "pinned": False}

try:
    from integrations.ipfs_datasets.vector_store import EMBEDDINGS_AVAILABLE, get_embeddings_router
except Exception:
    EMBEDDINGS_AVAILABLE = False

    def get_embeddings_router(*args, **kwargs):
        return None


LLM_ROUTER_AVAILABLE = callable(generate_text_with_metadata)


class AgenticDocumentOptimizer:
    CRITIC_PROMPT_TAG = "[DOC_OPT_CRITIC]"
    ACTOR_PROMPT_TAG = "[DOC_OPT_ACTOR]"

    def __init__(
        self,
        mediator: Any,
        *,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        max_iterations: int = 2,
        target_score: float = 0.9,
        persist_artifacts: bool = False,
    ) -> None:
        self.mediator = mediator
        self.provider = provider
        self.model_name = model_name
        self.max_iterations = max(1, int(max_iterations or 1))
        self.target_score = float(target_score or 0.9)
        self.persist_artifacts = bool(persist_artifacts)

    def optimize(self, draft: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        working_draft = deepcopy(draft)
        initial_review = self._run_critic(working_draft)
        current_review = initial_review
        iterations: List[Dict[str, Any]] = []
        accepted_iterations = 0

        for iteration in range(1, self.max_iterations + 1):
            if float(current_review.get("overall_score") or 0.0) >= self.target_score:
                break
            actor_payload = self._run_actor(working_draft, current_review)
            candidate_draft = self._apply_actor_payload(working_draft, actor_payload)
            candidate_review = self._run_critic(candidate_draft)
            accepted = float(candidate_review.get("overall_score") or 0.0) > float(current_review.get("overall_score") or 0.0)
            iterations.append(
                {
                    "iteration": iteration,
                    "accepted": accepted,
                    "critic": candidate_review,
                    "actor_payload": actor_payload,
                }
            )
            if accepted:
                working_draft = candidate_draft
                current_review = candidate_review
                accepted_iterations += 1

        artifact = self._store_trace(
            {
                "initial_review": initial_review,
                "final_review": current_review,
                "iterations": iterations,
            }
        )
        report = {
            "status": "optimized" if accepted_iterations else "completed",
            "initial_score": float(initial_review.get("overall_score") or 0.0),
            "final_score": float(current_review.get("overall_score") or 0.0),
            "accepted_iterations": accepted_iterations,
            "iterations": iterations,
            "artifact_cid": str(artifact.get("cid") or ""),
            "artifact": artifact,
        }
        return working_draft, report

    def _run_critic(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        if not LLM_ROUTER_AVAILABLE:
            return self._default_review()
        payload = generate_text_with_metadata(
            f"{self.CRITIC_PROMPT_TAG}\n{json.dumps(draft, ensure_ascii=True, default=str)}",
            provider=self.provider,
            model_name=self.model_name,
        )
        text = payload.get("text") if isinstance(payload, dict) else payload
        return self._parse_json_payload(text) or self._default_review()

    def _run_actor(self, draft: Dict[str, Any], critic_review: Dict[str, Any]) -> Dict[str, Any]:
        if not LLM_ROUTER_AVAILABLE:
            return {}
        payload = generate_text_with_metadata(
            f"{self.ACTOR_PROMPT_TAG}\n{json.dumps({'draft': draft, 'critic_review': critic_review}, ensure_ascii=True, default=str)}",
            provider=self.provider,
            model_name=self.model_name,
        )
        text = payload.get("text") if isinstance(payload, dict) else payload
        return self._parse_json_payload(text) or {}

    def _apply_actor_payload(self, draft: Dict[str, Any], actor_payload: Dict[str, Any]) -> Dict[str, Any]:
        updated = deepcopy(draft)
        factual_allegations = actor_payload.get("factual_allegations")
        if isinstance(factual_allegations, list):
            updated["factual_allegations"] = [str(item).strip() for item in factual_allegations if str(item).strip()]
        claim_supporting_facts = actor_payload.get("claim_supporting_facts")
        if isinstance(claim_supporting_facts, dict):
            claims = updated.get("claims_for_relief") if isinstance(updated.get("claims_for_relief"), list) else []
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                claim_type = str(claim.get("claim_type") or "").strip()
                payload_facts = claim_supporting_facts.get(claim_type)
                if isinstance(payload_facts, list):
                    claim["supporting_facts"] = [str(item).strip() for item in payload_facts if str(item).strip()]
        return updated

    def _parse_json_payload(self, text: Any) -> Optional[Dict[str, Any]]:
        raw = str(text or "").strip()
        if not raw:
            return None
        candidates = [raw]
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(raw[start : end + 1])
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def _default_review(self) -> Dict[str, Any]:
        return {
            "overall_score": 0.0,
            "dimension_scores": {},
            "strengths": [],
            "weaknesses": ["No critic response available."],
            "suggestions": [],
            "recommended_focus": "factual_allegations",
        }

    def _store_trace(self, trace_payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.persist_artifacts or not IPFS_AVAILABLE:
            return {"status": "disabled", "cid": "", "size": 0, "pinned": False}
        encoded = json.dumps(trace_payload, ensure_ascii=True, sort_keys=True, default=str).encode("utf-8")
        result = store_bytes(encoded, pin_content=True)
        return {
            "status": result.get("status") or "",
            "cid": result.get("cid") or "",
            "size": int(result.get("size") or len(encoded)),
            "pinned": bool(result.get("pinned")),
        }


__all__ = [
    "AgenticDocumentOptimizer",
    "LLM_ROUTER_AVAILABLE",
    "EMBEDDINGS_AVAILABLE",
    "IPFS_AVAILABLE",
    "generate_text_with_metadata",
    "get_embeddings_router",
    "store_bytes",
]
