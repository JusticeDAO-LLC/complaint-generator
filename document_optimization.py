from __future__ import annotations

from copy import deepcopy
import json
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

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

try:
    from integrations.ipfs_datasets.loader import import_attr_optional
except Exception:
    def import_attr_optional(*args, **kwargs):
        return None, None


OptimizerLLMRouter, _optimizer_router_error = import_attr_optional(
    "ipfs_datasets_py.optimizers.agentic",
    "OptimizerLLMRouter",
)
ControlLoopConfig, _control_loop_error = import_attr_optional(
    "ipfs_datasets_py.optimizers.agentic",
    "ControlLoopConfig",
)
OptimizationMethod, _optimization_method_error = import_attr_optional(
    "ipfs_datasets_py.optimizers.agentic",
    "OptimizationMethod",
)

LLM_ROUTER_AVAILABLE = callable(generate_text_with_metadata)
UPSTREAM_AGENTIC_AVAILABLE = any(
    value is not None for value in (OptimizerLLMRouter, ControlLoopConfig, OptimizationMethod)
)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _unique_preserving_order(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(text)
    return ordered


class AgenticDocumentOptimizer:
    CRITIC_PROMPT_TAG = "[DOC_OPT_CRITIC]"
    ACTOR_PROMPT_TAG = "[DOC_OPT_ACTOR]"
    VALID_FOCUS_SECTIONS = {
        "factual_allegations",
        "claims_for_relief",
        "affidavit",
        "certificate_of_service",
    }

    def __init__(
        self,
        mediator: Any,
        builder: Any = None,
        *,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        max_iterations: int = 2,
        target_score: float = 0.9,
        persist_artifacts: bool = False,
    ) -> None:
        self.mediator = mediator
        self.builder = builder
        self.provider = provider
        self.model_name = model_name
        self.max_iterations = max(1, int(max_iterations or 1))
        self.target_score = float(target_score or 0.9)
        self.persist_artifacts = bool(persist_artifacts)
        self.llm_config: Dict[str, Any] = {}
        self._embeddings_router = None

    def optimize(self, draft: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        result = self.optimize_draft(draft=draft, user_id=None, drafting_readiness={}, config={})
        return result.get("draft") or deepcopy(draft), result

    def optimize_draft(
        self,
        *,
        draft: Dict[str, Any],
        user_id: Optional[str] = None,
        drafting_readiness: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._apply_config(config or {})
        working_draft = self._refresh_dependent_sections(deepcopy(draft))
        readiness = drafting_readiness or {}
        support_context = self._build_support_context(
            user_id=user_id,
            draft=working_draft,
            drafting_readiness=readiness,
        )
        upstream_optimizer = self._build_upstream_optimizer_metadata()
        initial_review = self._run_critic(
            draft=working_draft,
            drafting_readiness=readiness,
            support_context=support_context,
        )
        current_review = initial_review
        iterations: List[Dict[str, Any]] = []
        accepted_iterations = 0
        optimized_sections: List[str] = []

        for iteration in range(1, self.max_iterations + 1):
            if float(current_review.get("overall_score") or 0.0) >= self.target_score:
                break

            focus_section = self._choose_focus_section(
                current_review=current_review,
                draft=working_draft,
                drafting_readiness=readiness,
                support_context=support_context,
            )
            actor_payload = self._run_actor(
                draft=working_draft,
                critic_review=current_review,
                support_context=support_context,
                focus_section=focus_section,
            )
            candidate_draft = self._apply_actor_payload(
                draft=working_draft,
                actor_payload=actor_payload,
                focus_section=focus_section,
            )
            candidate_review = self._run_critic(
                draft=candidate_draft,
                drafting_readiness=readiness,
                support_context=support_context,
            )
            accepted = float(candidate_review.get("overall_score") or 0.0) > float(current_review.get("overall_score") or 0.0)
            selected_support_context = self._select_support_context(
                focus_section=focus_section,
                draft=working_draft,
                support_context=support_context,
            )
            iterations.append(
                {
                    "iteration": iteration,
                    "focus_section": focus_section,
                    "accepted": accepted,
                    "critic": candidate_review,
                    "actor_payload": actor_payload,
                    "selected_support_context": selected_support_context,
                    "packet_projection": dict(support_context.get("packet_projection") or {}),
                }
            )
            if accepted:
                working_draft = candidate_draft
                current_review = candidate_review
                accepted_iterations += 1
                if focus_section not in optimized_sections:
                    optimized_sections.append(focus_section)

        trace_storage = self._store_trace(
            {
                "user_id": user_id or "",
                "config": {
                    "provider": self.provider or "",
                    "model_name": self.model_name or "",
                    "llm_config": self._sanitized_llm_config(),
                    "max_iterations": self.max_iterations,
                    "target_score": self.target_score,
                    "persist_artifacts": self.persist_artifacts,
                    "upstream_optimizer": upstream_optimizer,
                },
                "support_context": support_context,
                "initial_review": initial_review,
                "final_review": current_review,
                "iterations": iterations,
            }
        )
        return {
            "status": "optimized" if accepted_iterations else "completed",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic" if UPSTREAM_AGENTIC_AVAILABLE else "local_fallback",
            "initial_score": float(initial_review.get("overall_score") or 0.0),
            "final_score": float(current_review.get("overall_score") or 0.0),
            "iteration_count": len(iterations),
            "accepted_iterations": accepted_iterations,
            "optimized_sections": optimized_sections,
            "artifact_cid": str(trace_storage.get("cid") or ""),
            "trace_storage": trace_storage,
            "router_status": self._router_status(),
            "upstream_optimizer": upstream_optimizer,
            "packet_projection": dict(support_context.get("packet_projection") or {}),
            "section_history": [
                {
                    "iteration": int(entry.get("iteration") or 0),
                    "focus_section": str(entry.get("focus_section") or ""),
                    "accepted": bool(entry.get("accepted")),
                    "overall_score": float((entry.get("critic") or {}).get("overall_score") or 0.0),
                    "critic_llm_metadata": dict((entry.get("critic") or {}).get("llm_metadata") or {}),
                    "actor_llm_metadata": dict((entry.get("actor_payload") or {}).get("llm_metadata") or {}),
                    "selected_support_context": dict(entry.get("selected_support_context") or {}),
                }
                for entry in iterations
            ],
            "initial_review": self._serialize_review(initial_review),
            "final_review": self._serialize_review(current_review),
            "draft": working_draft,
        }

    def _apply_config(self, config: Dict[str, Any]) -> None:
        provider = config.get("llm_provider") or config.get("provider")
        model_name = config.get("llm_model_name") or config.get("model_name")
        max_iterations = config.get("max_iterations")
        target_score = config.get("target_score")
        persist_artifacts = config.get("use_ipfs")
        if persist_artifacts is None:
            persist_artifacts = config.get("persist_artifacts")
        llm_config = config.get("llm_config") or config.get("optimization_llm_config")

        if provider is not None:
            self.provider = str(provider or "").strip() or None
        if model_name is not None:
            self.model_name = str(model_name or "").strip() or None
        if max_iterations is not None:
            self.max_iterations = max(1, int(max_iterations or 1))
        if target_score is not None:
            self.target_score = float(target_score or self.target_score)
        if persist_artifacts is not None:
            self.persist_artifacts = bool(persist_artifacts)
        if isinstance(llm_config, dict):
            self.llm_config = {str(key): value for key, value in llm_config.items()}

    def _build_support_context(
        self,
        *,
        user_id: Optional[str],
        draft: Dict[str, Any],
        drafting_readiness: Dict[str, Any],
    ) -> Dict[str, Any]:
        claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
        claim_entries = drafting_readiness.get("claims") if isinstance(drafting_readiness.get("claims"), list) else []
        readiness_by_claim = {}
        for entry in claim_entries:
            if not isinstance(entry, dict):
                continue
            claim_type = str(entry.get("claim_type") or "").strip()
            if claim_type:
                readiness_by_claim[claim_type] = entry

        support_summary_payload = self._call_mediator("summarize_claim_support", user_id=user_id) or {}
        support_summary_claims = support_summary_payload.get("claims") if isinstance(support_summary_payload, dict) else {}
        support_summary_claims = support_summary_claims if isinstance(support_summary_claims, dict) else {}

        evidence_rows = self._call_mediator("get_user_evidence", user_id=user_id) or []
        evidence_summaries = []
        for row in evidence_rows if isinstance(evidence_rows, list) else []:
            if not isinstance(row, dict):
                continue
            text = str(row.get("parsed_text_preview") or row.get("description") or row.get("title") or "").strip()
            if not text:
                continue
            evidence_summaries.append(
                {
                    "claim_type": str(row.get("claim_type") or "").strip(),
                    "text": text,
                    "cid": str(row.get("cid") or "").strip(),
                    "type": str(row.get("type") or "").strip(),
                }
            )

        claim_contexts = []
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_type = str(claim.get("claim_type") or claim.get("count_title") or "").strip()
            support_facts = self._call_mediator("get_claim_support_facts", claim_type=claim_type, user_id=user_id) or []
            overview = self._call_mediator("get_claim_overview", claim_type=claim_type, user_id=user_id) or {}
            overview_claim = {}
            if isinstance(overview, dict):
                overview_claims = overview.get("claims") if isinstance(overview.get("claims"), dict) else {}
                overview_claim = overview_claims.get(claim_type) if isinstance(overview_claims.get(claim_type), dict) else {}
            support_summary = support_summary_claims.get(claim_type) if isinstance(support_summary_claims.get(claim_type), dict) else {}
            readiness_entry = readiness_by_claim.get(claim_type, {})
            support_texts = self._extract_support_texts(support_facts)
            claim_contexts.append(
                {
                    "claim_type": claim_type,
                    "missing_elements": self._extract_element_texts(overview_claim.get("missing")),
                    "partially_supported_elements": self._extract_element_texts(overview_claim.get("partially_supported")),
                    "support_summary": {
                        "total_elements": int(support_summary.get("total_elements") or claim.get("support_summary", {}).get("total_elements") or 0),
                        "covered_elements": int(support_summary.get("covered_elements") or claim.get("support_summary", {}).get("covered_elements") or 0),
                        "uncovered_elements": int(support_summary.get("uncovered_elements") or claim.get("support_summary", {}).get("uncovered_elements") or 0),
                        "source_family_counts": dict(support_summary.get("support_packet_summary", {}).get("source_family_counts") or claim.get("support_summary", {}).get("source_family_counts") or {}),
                    },
                    "support_facts": support_texts[:8],
                    "readiness_warnings": [
                        str(item.get("message") or "").strip()
                        for item in readiness_entry.get("warnings", [])
                        if isinstance(item, dict) and str(item.get("message") or "").strip()
                    ],
                }
            )

        return {
            "claims": claim_contexts,
            "evidence": evidence_summaries[:10],
            "sections": dict(drafting_readiness.get("sections") or {}) if isinstance(drafting_readiness, dict) else {},
            "packet_projection": self._build_packet_projection(draft),
            "capabilities": self._router_status(),
        }

    def _run_critic(
        self,
        *,
        draft: Dict[str, Any],
        drafting_readiness: Dict[str, Any],
        support_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        heuristic_review = self._heuristic_review(
            draft=draft,
            drafting_readiness=drafting_readiness,
            support_context=support_context,
        )
        if not LLM_ROUTER_AVAILABLE:
            return heuristic_review

        payload = generate_text_with_metadata(
            f"{self.CRITIC_PROMPT_TAG}\n{json.dumps({'draft': draft, 'drafting_readiness': drafting_readiness, 'support_context': support_context, 'heuristic_review': heuristic_review}, ensure_ascii=True, default=str)}",
            provider=self.provider,
            model_name=self.model_name,
            **self.llm_config,
        )
        text = payload.get("text") if isinstance(payload, dict) else payload
        parsed = self._parse_json_payload(text)
        merged = self._merge_review_payload(parsed, heuristic_review)
        llm_metadata = self._extract_llm_metadata(payload)
        if llm_metadata:
            merged["llm_metadata"] = llm_metadata
        return merged

    def _run_actor(
        self,
        *,
        draft: Dict[str, Any],
        critic_review: Dict[str, Any],
        support_context: Dict[str, Any],
        focus_section: str,
    ) -> Dict[str, Any]:
        selected_support_context = self._select_support_context(
            focus_section=focus_section,
            draft=draft,
            support_context=support_context,
        )
        fallback_payload = self._build_fallback_actor_payload(
            draft=draft,
            focus_section=focus_section,
            support_context=selected_support_context,
        )
        if not LLM_ROUTER_AVAILABLE:
            return fallback_payload

        payload = generate_text_with_metadata(
            f"{self.ACTOR_PROMPT_TAG}\n{json.dumps({'focus_section': focus_section, 'draft': draft, 'critic_review': critic_review, 'support_context': selected_support_context, 'fallback_payload': fallback_payload}, ensure_ascii=True, default=str)}",
            provider=self.provider,
            model_name=self.model_name,
            **self.llm_config,
        )
        text = payload.get("text") if isinstance(payload, dict) else payload
        parsed = self._parse_json_payload(text) or {}
        if "focus_section" not in parsed:
            parsed["focus_section"] = focus_section
        merged = {**fallback_payload, **parsed}
        llm_metadata = self._extract_llm_metadata(payload)
        if llm_metadata:
            merged["llm_metadata"] = llm_metadata
        return merged

    def _apply_actor_payload(
        self,
        *,
        draft: Dict[str, Any],
        actor_payload: Dict[str, Any],
        focus_section: str,
    ) -> Dict[str, Any]:
        updated = deepcopy(draft)
        factual_allegations = actor_payload.get("factual_allegations")
        if isinstance(factual_allegations, list):
            updated["factual_allegations"] = self._normalize_lines(factual_allegations)

        claim_supporting_facts = actor_payload.get("claim_supporting_facts")
        if isinstance(claim_supporting_facts, dict):
            claims = updated.get("claims_for_relief") if isinstance(updated.get("claims_for_relief"), list) else []
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                claim_type = str(claim.get("claim_type") or "").strip()
                payload_facts = claim_supporting_facts.get(claim_type)
                if isinstance(payload_facts, list):
                    claim["supporting_facts"] = self._normalize_lines(payload_facts)

        if focus_section == "affidavit" or any(
            key in actor_payload for key in ("affidavit_intro", "affidavit_facts", "affidavit_supporting_exhibits")
        ):
            overrides = updated.get("affidavit_overrides") if isinstance(updated.get("affidavit_overrides"), dict) else {}
            updated["affidavit_overrides"] = overrides
            if actor_payload.get("affidavit_intro"):
                overrides["intro"] = str(actor_payload.get("affidavit_intro") or "").strip()
            if isinstance(actor_payload.get("affidavit_facts"), list):
                overrides["facts"] = self._normalize_affidavit_facts(actor_payload.get("affidavit_facts") or [])
            if isinstance(actor_payload.get("affidavit_supporting_exhibits"), list):
                overrides["supporting_exhibits"] = self._normalize_exhibits(actor_payload.get("affidavit_supporting_exhibits") or [])

        if focus_section == "certificate_of_service" or any(
            key in actor_payload for key in ("service_text", "service_recipients", "service_recipient_details")
        ):
            certificate = updated.get("certificate_of_service") if isinstance(updated.get("certificate_of_service"), dict) else {}
            updated["certificate_of_service"] = certificate
            if actor_payload.get("service_text"):
                certificate["text"] = str(actor_payload.get("service_text") or "").strip()
            if isinstance(actor_payload.get("service_recipients"), list):
                certificate["recipients"] = self._normalize_lines(actor_payload.get("service_recipients") or [])
            if isinstance(actor_payload.get("service_recipient_details"), list):
                details = self._normalize_service_recipient_details(actor_payload.get("service_recipient_details") or [])
                certificate["recipient_details"] = details
                certificate["detail_lines"] = [self._format_service_recipient_detail(detail) for detail in details]
                if details and not certificate.get("recipients"):
                    certificate["recipients"] = _unique_preserving_order(detail.get("recipient") for detail in details)

        return self._refresh_dependent_sections(updated)

    def _heuristic_review(
        self,
        *,
        draft: Dict[str, Any],
        drafting_readiness: Dict[str, Any],
        support_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        factual_allegations = self._normalize_lines(draft.get("factual_allegations") or draft.get("summary_of_facts") or [])
        claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
        affidavit = draft.get("affidavit") if isinstance(draft.get("affidavit"), dict) else {}
        certificate = draft.get("certificate_of_service") if isinstance(draft.get("certificate_of_service"), dict) else {}
        exhibits = draft.get("exhibits") if isinstance(draft.get("exhibits"), list) else []

        section_scores = {
            "factual_allegations": self._score_factual_allegations(factual_allegations, claims),
            "claims_for_relief": self._score_claims_section(claims, support_context),
            "affidavit": self._score_affidavit_section(affidavit, exhibits),
            "certificate_of_service": self._score_certificate_section(certificate),
            "packet_projection": self._score_packet_projection(
                support_context.get("packet_projection") if isinstance(support_context.get("packet_projection"), dict) else {}
            ),
        }
        ordered_sections = sorted(
            ((name, score) for name, score in section_scores.items() if name in self.VALID_FOCUS_SECTIONS),
            key=lambda item: item[1],
        )
        recommended_focus = ordered_sections[0][0] if ordered_sections else "factual_allegations"

        weaknesses: List[str] = []
        suggestions: List[str] = []
        for section_name, score in ordered_sections:
            if score >= 0.8:
                continue
            if section_name == "factual_allegations":
                weaknesses.append("Factual allegations should read like pleading-ready declarative paragraphs grounded in the support record.")
                suggestions.append("Rewrite factual allegations into short declarative prose anchored to the support packet.")
            elif section_name == "claims_for_relief":
                weaknesses.append("Claims for relief still contain support gaps or thin claim-specific fact statements.")
                suggestions.append("Backfill claim-specific support facts for the weakest claim before rendering artifacts.")
            elif section_name == "affidavit":
                weaknesses.append("The affidavit is missing completeness or exhibit-consistency signals needed for a filing-ready packet.")
                suggestions.append("Revise affidavit facts and mirrored exhibit support so the affidavit matches the complaint record.")
            elif section_name == "certificate_of_service":
                weaknesses.append("The certificate of service is thin on recipient detail or service metadata.")
                suggestions.append("Add structured recipient details and method-specific service language before export.")

        readiness_status = str(drafting_readiness.get("status") or "ready").strip().lower()
        procedural_score = 0.95 if readiness_status == "ready" else 0.75 if readiness_status == "warning" else 0.45
        completeness_score = sum(section_scores.values()) / max(len(section_scores), 1)
        grounding_score = self._score_grounding(support_context)
        coherence_score = self._score_coherence(factual_allegations)
        renderability_score = (
            section_scores["affidavit"]
            + section_scores["certificate_of_service"]
            + section_scores["packet_projection"]
        ) / 3.0

        overall_score = _clamp(
            (completeness_score * 0.35)
            + (grounding_score * 0.2)
            + (coherence_score * 0.2)
            + (procedural_score * 0.15)
            + (renderability_score * 0.1)
        )
        strengths = []
        if support_context.get("claims"):
            strengths.append("Support packets are available.")
        if section_scores["affidavit"] >= 0.85:
            strengths.append("Affidavit content is structurally complete.")
        if section_scores["certificate_of_service"] >= 0.85:
            strengths.append("Service metadata is present for export.")
        if section_scores["packet_projection"] >= 0.85:
            strengths.append("Render-target packet projection is structurally complete.")

        return {
            "overall_score": overall_score,
            "dimension_scores": {
                "completeness": completeness_score,
                "grounding": grounding_score,
                "coherence": coherence_score,
                "procedural": procedural_score,
                "renderability": renderability_score,
            },
            "section_scores": section_scores,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "suggestions": suggestions,
            "recommended_focus": recommended_focus,
        }

    def _score_factual_allegations(self, allegations: List[str], claims: List[Dict[str, Any]]) -> float:
        base = min(len(allegations), 4) / 4.0
        claim_support_count = 0
        for claim in claims:
            if isinstance(claim, dict) and claim.get("supporting_facts"):
                claim_support_count += 1
        support_bonus = min(claim_support_count, 3) / 6.0
        variety_bonus = 0.15 if len({text.lower() for text in allegations}) == len(allegations) else 0.0
        return _clamp(base * 0.55 + support_bonus + variety_bonus)

    def _score_claims_section(self, claims: List[Dict[str, Any]], support_context: Dict[str, Any]) -> float:
        if not claims:
            return 0.0
        supported_claims = 0
        unresolved_penalty = 0.0
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            facts = self._normalize_lines(claim.get("supporting_facts") or [])
            if facts:
                supported_claims += 1
            claim_type = str(claim.get("claim_type") or "").strip()
            for context in support_context.get("claims", []):
                if isinstance(context, dict) and str(context.get("claim_type") or "").strip() == claim_type:
                    unresolved_penalty += 0.08 * len(context.get("missing_elements") or [])
        coverage = supported_claims / max(len(claims), 1)
        return _clamp(coverage - unresolved_penalty + 0.2)

    def _score_affidavit_section(self, affidavit: Dict[str, Any], exhibits: List[Dict[str, Any]]) -> float:
        facts = self._normalize_lines(affidavit.get("facts") or [])
        intro_score = 0.2 if str(affidavit.get("intro") or "").strip() else 0.0
        jurat_score = 0.15 if str(affidavit.get("jurat") or "").strip() else 0.0
        fact_score = min(len(facts), 4) / 4.0 * 0.45
        supporting_exhibits = affidavit.get("supporting_exhibits") if isinstance(affidavit.get("supporting_exhibits"), list) else []
        exhibit_score = 0.2 if supporting_exhibits or exhibits else 0.0
        return _clamp(intro_score + jurat_score + fact_score + exhibit_score)

    def _score_certificate_section(self, certificate: Dict[str, Any]) -> float:
        recipients = self._normalize_lines(certificate.get("recipients") or [])
        recipient_details = certificate.get("recipient_details") if isinstance(certificate.get("recipient_details"), list) else []
        text_score = 0.3 if str(certificate.get("text") or "").strip() else 0.0
        recipient_score = min(len(recipients), 2) / 2.0 * 0.25
        detail_score = min(len(recipient_details), 2) / 2.0 * 0.3
        dated_score = 0.15 if str(certificate.get("dated") or "").strip() else 0.0
        return _clamp(text_score + recipient_score + detail_score + dated_score)

    def _score_packet_projection(self, packet_projection: Dict[str, Any]) -> float:
        section_presence = packet_projection.get("section_presence") if isinstance(packet_projection.get("section_presence"), dict) else {}
        section_counts = packet_projection.get("section_counts") if isinstance(packet_projection.get("section_counts"), dict) else {}
        required_sections = ("nature_of_action", "summary_of_facts", "factual_allegations", "claims_for_relief")
        required_score = sum(1.0 for key in required_sections if section_presence.get(key)) / max(len(required_sections), 1)
        affidavit_score = 1.0 if packet_projection.get("has_affidavit") else 0.0
        certificate_score = 1.0 if packet_projection.get("has_certificate_of_service") else 0.0
        allegation_depth = min(int(section_counts.get("factual_allegations") or 0), 4) / 4.0
        claim_depth = min(int(section_counts.get("claims_for_relief") or 0), 2) / 2.0
        return _clamp((required_score * 0.35) + (affidavit_score * 0.2) + (certificate_score * 0.2) + (allegation_depth * 0.15) + (claim_depth * 0.1))

    def _score_grounding(self, support_context: Dict[str, Any]) -> float:
        claim_contexts = support_context.get("claims") if isinstance(support_context.get("claims"), list) else []
        evidence = support_context.get("evidence") if isinstance(support_context.get("evidence"), list) else []
        claim_bonus = min(len(claim_contexts), 3) / 4.0
        evidence_bonus = min(len(evidence), 3) / 6.0
        return _clamp(claim_bonus + evidence_bonus)

    def _score_coherence(self, allegations: List[str]) -> float:
        if not allegations:
            return 0.0
        dedup_ratio = len({value.lower() for value in allegations}) / max(len(allegations), 1)
        punctuation_ratio = sum(1 for value in allegations if value.endswith((".", "!", "?"))) / max(len(allegations), 1)
        return _clamp((dedup_ratio * 0.6) + (punctuation_ratio * 0.4))

    def _merge_review_payload(self, parsed: Optional[Dict[str, Any]], heuristic_review: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(parsed, dict):
            return heuristic_review
        merged = deepcopy(heuristic_review)
        for key in ("overall_score", "strengths", "weaknesses", "suggestions"):
            if key in parsed:
                merged[key] = parsed[key]
        if isinstance(parsed.get("dimension_scores"), dict):
            merged["dimension_scores"] = {**merged.get("dimension_scores", {}), **parsed["dimension_scores"]}
        if isinstance(parsed.get("section_scores"), dict):
            merged["section_scores"] = {**merged.get("section_scores", {}), **parsed["section_scores"]}
        recommended_focus = str(parsed.get("recommended_focus") or "").strip()
        if recommended_focus in self.VALID_FOCUS_SECTIONS:
            merged["recommended_focus"] = recommended_focus
        merged["overall_score"] = _clamp(float(merged.get("overall_score") or 0.0))
        return merged

    def _serialize_review(self, review: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(review, dict):
            return {}
        serialized = {
            "overall_score": float(review.get("overall_score") or 0.0),
            "dimension_scores": dict(review.get("dimension_scores") or {}),
            "section_scores": dict(review.get("section_scores") or {}),
            "strengths": list(review.get("strengths") or []),
            "weaknesses": list(review.get("weaknesses") or []),
            "suggestions": list(review.get("suggestions") or []),
            "recommended_focus": str(review.get("recommended_focus") or ""),
        }
        llm_metadata = dict(review.get("llm_metadata") or {})
        if llm_metadata:
            serialized["llm_metadata"] = llm_metadata
        return serialized

    def _extract_llm_metadata(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        allowed_keys = (
            "status",
            "provider_name",
            "model_name",
            "effective_provider_name",
            "effective_model_name",
            "router_base_url",
            "arch_router_status",
            "arch_router_selected_route",
            "arch_router_selected_model",
            "arch_router_model_name",
            "error",
        )
        metadata = {}
        for key in allowed_keys:
            value = payload.get(key)
            if value in (None, "", []):
                continue
            metadata[key] = value
        return metadata

    def _choose_focus_section(
        self,
        *,
        current_review: Dict[str, Any],
        draft: Dict[str, Any],
        drafting_readiness: Dict[str, Any],
        support_context: Dict[str, Any],
    ) -> str:
        recommended_focus = str(current_review.get("recommended_focus") or "").strip()
        if recommended_focus in self.VALID_FOCUS_SECTIONS:
            return recommended_focus
        return self._heuristic_review(
            draft=draft,
            drafting_readiness=drafting_readiness,
            support_context=support_context,
        ).get("recommended_focus", "factual_allegations")

    def _select_support_context(
        self,
        *,
        focus_section: str,
        draft: Dict[str, Any],
        support_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        query = self._focus_query_text(focus_section, draft)
        claim_rows = support_context.get("claims") if isinstance(support_context.get("claims"), list) else []
        candidate_rows = []
        for claim_row in claim_rows:
            if not isinstance(claim_row, dict):
                continue
            claim_type = str(claim_row.get("claim_type") or "").strip()
            for text in claim_row.get("support_facts") or []:
                candidate_rows.append({"claim_type": claim_type, "text": str(text)})
            for text in claim_row.get("missing_elements") or []:
                candidate_rows.append({"claim_type": claim_type, "text": str(text), "kind": "missing_element"})
        for evidence_row in support_context.get("evidence") or []:
            if isinstance(evidence_row, dict) and evidence_row.get("text"):
                candidate_rows.append(dict(evidence_row))

        ranked_rows = self._rank_candidates(query=query, candidates=candidate_rows)
        return {
            "focus_section": focus_section,
            "query": query,
            "top_support": ranked_rows[:6],
        }

    def _build_fallback_actor_payload(
        self,
        *,
        draft: Dict[str, Any],
        focus_section: str,
        support_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"focus_section": focus_section}
        top_support = support_context.get("top_support") if isinstance(support_context.get("top_support"), list) else []
        support_texts = self._normalize_lines([row.get("text") for row in top_support if isinstance(row, dict)])

        if focus_section == "factual_allegations":
            factual_candidates = self._normalize_lines(draft.get("summary_of_facts") or [])
            factual_candidates.extend(support_texts)
            for claim in draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []:
                if isinstance(claim, dict):
                    factual_candidates.extend(self._normalize_lines(claim.get("supporting_facts") or []))
            payload["factual_allegations"] = self._normalize_lines(factual_candidates)[:8]
        elif focus_section == "claims_for_relief":
            claim_supporting_facts: Dict[str, List[str]] = {}
            for claim in draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []:
                if not isinstance(claim, dict):
                    continue
                claim_type = str(claim.get("claim_type") or "").strip()
                claim_supporting_facts[claim_type] = self._normalize_lines(
                    list(claim.get("supporting_facts") or []) + support_texts
                )[:6]
            payload["claim_supporting_facts"] = claim_supporting_facts
        elif focus_section == "affidavit":
            affidavit = draft.get("affidavit") if isinstance(draft.get("affidavit"), dict) else {}
            payload["affidavit_intro"] = str(
                affidavit.get("intro")
                or f"I, {affidavit.get('declarant_name') or 'Plaintiff'}, make this affidavit from personal knowledge and the supporting records assembled for this complaint."
            ).strip()
            affidavit_facts = self._normalize_affidavit_facts(
                list(affidavit.get("facts") or []) + list(draft.get("factual_allegations") or []) + support_texts
            )[:8]
            payload["affidavit_facts"] = affidavit_facts
            supporting_exhibits = affidavit.get("supporting_exhibits") if isinstance(affidavit.get("supporting_exhibits"), list) else []
            if not supporting_exhibits:
                supporting_exhibits = self._normalize_exhibits(draft.get("exhibits") or [])[:4]
            payload["affidavit_supporting_exhibits"] = supporting_exhibits
        elif focus_section == "certificate_of_service":
            certificate = draft.get("certificate_of_service") if isinstance(draft.get("certificate_of_service"), dict) else {}
            recipients = self._normalize_lines(certificate.get("recipients") or [])
            method = "promptly after filing"
            details = certificate.get("recipient_details") if isinstance(certificate.get("recipient_details"), list) else []
            if not details and recipients:
                details = [{"recipient": recipient, "method": "Service method to be confirmed", "address": "", "notes": ""} for recipient in recipients]
            payload["service_recipients"] = recipients
            payload["service_recipient_details"] = details
            payload["service_text"] = str(
                certificate.get("text")
                or f"I certify that a true and correct copy of this Complaint will be served on the following recipients {method}."
            ).strip()
        return payload

    def _focus_query_text(self, focus_section: str, draft: Dict[str, Any]) -> str:
        if focus_section == "factual_allegations":
            return "factual allegations pleading-ready support record"
        if focus_section == "claims_for_relief":
            claim_titles = []
            for claim in draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []:
                if isinstance(claim, dict):
                    claim_titles.append(str(claim.get("claim_type") or claim.get("count_title") or ""))
            return "claims for relief " + " ".join(title for title in claim_titles if title)
        if focus_section == "affidavit":
            return "affidavit facts exhibits personal knowledge"
        if focus_section == "certificate_of_service":
            return "certificate of service recipients method address"
        return focus_section.replace("_", " ")

    def _rank_candidates(self, *, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        router = self._get_embeddings_router()
        if router is None:
            query_terms = set(query.lower().split())
            ranked = []
            for row in candidates:
                text = str(row.get("text") or "")
                score = len(query_terms & set(text.lower().split()))
                ranked.append({**row, "score": float(score), "ranking_method": "lexical_fallback"})
            return sorted(ranked, key=lambda row: row.get("score", 0.0), reverse=True)

        query_vector = self._embed_text(router, query)
        ranked = []
        for row in candidates:
            text = str(row.get("text") or "")
            candidate_vector = self._embed_text(router, text)
            score = self._cosine_similarity(query_vector, candidate_vector)
            ranked.append({**row, "score": score, "ranking_method": "embeddings_router"})
        return sorted(ranked, key=lambda row: row.get("score", 0.0), reverse=True)

    def _get_embeddings_router(self) -> Any:
        if not EMBEDDINGS_AVAILABLE:
            return None
        if self._embeddings_router is None:
            try:
                self._embeddings_router = get_embeddings_router()
            except Exception:
                self._embeddings_router = None
        return self._embeddings_router

    def _embed_text(self, router: Any, text: str) -> List[float]:
        for method_name in ("embed_text", "encode", "embed"):
            method = getattr(router, method_name, None)
            if callable(method):
                try:
                    vector = method(text)
                except Exception:
                    continue
                if isinstance(vector, list):
                    return [float(value) for value in vector]
                if isinstance(vector, tuple):
                    return [float(value) for value in vector]
        return []

    def _cosine_similarity(self, left: List[float], right: List[float]) -> float:
        if not left or not right:
            return 0.0
        length = min(len(left), len(right))
        if length <= 0:
            return 0.0
        dot = sum(float(left[index]) * float(right[index]) for index in range(length))
        left_norm = math.sqrt(sum(float(left[index]) ** 2 for index in range(length)))
        right_norm = math.sqrt(sum(float(right[index]) ** 2 for index in range(length)))
        if left_norm <= 0.0 or right_norm <= 0.0:
            return 0.0
        return dot / (left_norm * right_norm)

    def _refresh_dependent_sections(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        refreshed = deepcopy(draft)
        if self.builder is not None:
            build_affidavit = getattr(self.builder, "_build_affidavit", None)
            if callable(build_affidavit):
                refreshed["affidavit"] = build_affidavit(refreshed)
            render_draft_text = getattr(self.builder, "_render_draft_text", None)
            if callable(render_draft_text):
                refreshed["draft_text"] = render_draft_text(refreshed)
        return refreshed

    def _router_status(self) -> Dict[str, str]:
        return {
            "llm_router": "available" if LLM_ROUTER_AVAILABLE else "unavailable",
            "embeddings_router": "available" if EMBEDDINGS_AVAILABLE else "unavailable",
            "ipfs_router": "available" if IPFS_AVAILABLE else "unavailable",
            "optimizers_agentic": "available" if UPSTREAM_AGENTIC_AVAILABLE else "unavailable",
        }

    def _build_packet_projection(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        if self.builder is not None:
            build_packet = getattr(self.builder, "_build_filing_packet_payload", None)
            if callable(build_packet):
                try:
                    packet = build_packet(draft, artifacts={})
                except Exception:
                    packet = {}
                if isinstance(packet, dict):
                    sections = packet.get("sections") if isinstance(packet.get("sections"), dict) else {}
                    return {
                        "title": str(packet.get("title") or draft.get("title") or "").strip(),
                        "section_presence": {
                            key: bool(sections.get(key))
                            for key in ("nature_of_action", "summary_of_facts", "factual_allegations", "claims_for_relief", "requested_relief")
                        },
                        "section_counts": {
                            key: len(sections.get(key) or []) if isinstance(sections.get(key), list) else int(bool(sections.get(key)))
                            for key in ("nature_of_action", "summary_of_facts", "factual_allegations", "claims_for_relief", "requested_relief")
                        },
                        "has_affidavit": bool(packet.get("affidavit")),
                        "has_certificate_of_service": bool(packet.get("certificate_of_service")),
                        "exhibit_count": len(packet.get("exhibits") or []) if isinstance(packet.get("exhibits"), list) else 0,
                        "checklist_item_count": len(packet.get("filing_checklist") or []) if isinstance(packet.get("filing_checklist"), list) else 0,
                        "preview": {
                            "factual_allegations": list(sections.get("factual_allegations") or [])[:4],
                            "affidavit_facts": list((packet.get("affidavit") or {}).get("facts") or [])[:4] if isinstance(packet.get("affidavit"), dict) else [],
                            "service_recipients": list((packet.get("certificate_of_service") or {}).get("recipients") or [])[:4] if isinstance(packet.get("certificate_of_service"), dict) else [],
                        },
                    }
        return {
            "title": str(draft.get("title") or "").strip(),
            "section_presence": {
                "nature_of_action": bool(draft.get("nature_of_action")),
                "summary_of_facts": bool(draft.get("summary_of_facts")),
                "factual_allegations": bool(draft.get("factual_allegations")),
                "claims_for_relief": bool(draft.get("claims_for_relief")),
                "requested_relief": bool(draft.get("requested_relief")),
            },
            "section_counts": {
                "nature_of_action": len(draft.get("nature_of_action") or []) if isinstance(draft.get("nature_of_action"), list) else int(bool(draft.get("nature_of_action"))),
                "summary_of_facts": len(draft.get("summary_of_facts") or []) if isinstance(draft.get("summary_of_facts"), list) else int(bool(draft.get("summary_of_facts"))),
                "factual_allegations": len(draft.get("factual_allegations") or []) if isinstance(draft.get("factual_allegations"), list) else int(bool(draft.get("factual_allegations"))),
                "claims_for_relief": len(draft.get("claims_for_relief") or []) if isinstance(draft.get("claims_for_relief"), list) else int(bool(draft.get("claims_for_relief"))),
                "requested_relief": len(draft.get("requested_relief") or []) if isinstance(draft.get("requested_relief"), list) else int(bool(draft.get("requested_relief"))),
            },
            "has_affidavit": bool(draft.get("affidavit")),
            "has_certificate_of_service": bool(draft.get("certificate_of_service")),
            "exhibit_count": len(draft.get("exhibits") or []) if isinstance(draft.get("exhibits"), list) else 0,
            "checklist_item_count": len(draft.get("filing_checklist") or []) if isinstance(draft.get("filing_checklist"), list) else 0,
            "preview": {
                "factual_allegations": list(draft.get("factual_allegations") or [])[:4] if isinstance(draft.get("factual_allegations"), list) else [],
                "affidavit_facts": list((draft.get("affidavit") or {}).get("facts") or [])[:4] if isinstance(draft.get("affidavit"), dict) else [],
                "service_recipients": list((draft.get("certificate_of_service") or {}).get("recipients") or [])[:4] if isinstance(draft.get("certificate_of_service"), dict) else [],
            },
        }

    def _build_upstream_optimizer_metadata(self) -> Dict[str, Any]:
        metadata = {
            "available": bool(UPSTREAM_AGENTIC_AVAILABLE),
            "selected_provider": "",
            "selected_method": "",
            "control_loop": {},
        }
        if not UPSTREAM_AGENTIC_AVAILABLE:
            return metadata
        try:
            method_name = "ACTOR_CRITIC"
            selected_method = getattr(OptimizationMethod, method_name, None)
            metadata["selected_method"] = getattr(selected_method, "value", "actor_critic")
            if ControlLoopConfig is not None:
                config = ControlLoopConfig(
                    max_iterations=self.max_iterations,
                    target_score=self.target_score,
                )
                metadata["control_loop"] = {
                    "max_iterations": int(getattr(config, "max_iterations", self.max_iterations)),
                    "target_score": float(getattr(config, "target_score", self.target_score)),
                }
            if OptimizerLLMRouter is not None and selected_method is not None:
                router = OptimizerLLMRouter(enable_tracking=False, enable_caching=False)
                selected_provider = router.select_provider(selected_method, complexity="complex")
                metadata["selected_provider"] = str(getattr(selected_provider, "value", selected_provider) or "")
        except Exception:
            return metadata
        return metadata

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

    def _sanitized_llm_config(self) -> Dict[str, Any]:
        sanitized: Dict[str, Any] = {}
        for key, value in self.llm_config.items():
            lowered = str(key).lower()
            if lowered in {"api_key", "token", "access_token", "authorization"}:
                sanitized[str(key)] = "[redacted]"
            elif lowered == "headers" and isinstance(value, dict):
                sanitized[str(key)] = {
                    str(header_key): ("[redacted]" if str(header_key).lower() == "authorization" else header_value)
                    for header_key, header_value in value.items()
                }
            else:
                sanitized[str(key)] = value
        return sanitized

    def _call_mediator(self, method_name: str, **kwargs: Any) -> Any:
        method = getattr(self.mediator, method_name, None)
        if not callable(method):
            return None
        try:
            return method(**kwargs)
        except Exception:
            return None

    def _extract_support_texts(self, values: Any) -> List[str]:
        texts: List[str] = []
        for value in values if isinstance(values, list) else []:
            if isinstance(value, str):
                texts.append(value)
                continue
            if not isinstance(value, dict):
                continue
            for key in ("fact_text", "summary", "text", "description", "parsed_text_preview", "title"):
                if value.get(key):
                    texts.append(str(value.get(key)))
        return self._normalize_lines(texts)

    def _extract_element_texts(self, values: Any) -> List[str]:
        elements = []
        for value in values if isinstance(values, list) else []:
            if isinstance(value, dict) and value.get("element_text"):
                elements.append(str(value.get("element_text")))
            elif isinstance(value, str):
                elements.append(value)
        return self._normalize_lines(elements)

    def _normalize_lines(self, values: Any) -> List[str]:
        if isinstance(values, list):
            iterable = values
        elif isinstance(values, tuple):
            iterable = list(values)
        else:
            iterable = [values]
        normalized = []
        for value in iterable:
            text = " ".join(str(value or "").strip().split())
            if not text:
                continue
            if text[-1] not in ".!?":
                text = f"{text}."
            normalized.append(text)
        return _unique_preserving_order(normalized)

    def _normalize_affidavit_facts(self, values: Any) -> List[str]:
        sanitized: List[str] = []
        for value in values if isinstance(values, list) else []:
            text = " ".join(str(value or "").strip().split())
            if not text:
                continue
            if text.lower().startswith("as to ") and "," in text:
                text = text.split(",", 1)[1].strip()
            if len(text) < 12:
                continue
            if text[-1] not in ".!?":
                text = f"{text}."
            sanitized.append(text)
        return _unique_preserving_order(sanitized)

    def _normalize_exhibits(self, values: Any) -> List[Dict[str, str]]:
        exhibits: List[Dict[str, str]] = []
        seen = set()
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            normalized = {
                "label": str(item.get("label") or "Exhibit").strip(),
                "title": str(item.get("title") or item.get("summary") or "Supporting exhibit").strip(),
                "link": str(item.get("link") or item.get("reference") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
            }
            key = (normalized["label"], normalized["title"], normalized["link"], normalized["summary"])
            if key in seen:
                continue
            seen.add(key)
            exhibits.append(normalized)
        return exhibits

    def _normalize_service_recipient_details(self, values: Any) -> List[Dict[str, str]]:
        details: List[Dict[str, str]] = []
        seen = set()
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            detail = {
                "recipient": str(item.get("recipient") or "").strip(),
                "method": str(item.get("method") or "").strip(),
                "address": str(item.get("address") or "").strip(),
                "notes": str(item.get("notes") or "").strip(),
            }
            key = (detail["recipient"], detail["method"], detail["address"], detail["notes"])
            if key in seen or not any(detail.values()):
                continue
            seen.add(key)
            details.append(detail)
        return details

    def _format_service_recipient_detail(self, detail: Dict[str, str]) -> str:
        segments = [detail.get("recipient") or "Unknown recipient"]
        if detail.get("method"):
            segments.append(f"Method: {detail['method']}")
        if detail.get("address"):
            segments.append(f"Address: {detail['address']}")
        if detail.get("notes"):
            segments.append(f"Notes: {detail['notes']}")
        return " | ".join(segment for segment in segments if segment)

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


__all__ = [
    "AgenticDocumentOptimizer",
    "LLM_ROUTER_AVAILABLE",
    "EMBEDDINGS_AVAILABLE",
    "IPFS_AVAILABLE",
    "UPSTREAM_AGENTIC_AVAILABLE",
    "generate_text_with_metadata",
    "get_embeddings_router",
    "store_bytes",
]
