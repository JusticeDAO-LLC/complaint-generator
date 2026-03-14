from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode

from complaint_phases import ComplaintPhase
from document_optimization import AgenticDocumentOptimizer


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "tmp" / "generated_documents"
DEFAULT_RELIEF = [
    "Compensatory damages in an amount to be proven at trial.",
    "Pre- and post-judgment interest as allowed by law.",
    "Reasonable attorney's fees and costs where authorized.",
    "Injunctive and declaratory relief sufficient to stop the unlawful conduct.",
    "Such other and further relief as the Court deems just and proper.",
]

STATE_DEFAULT_RELIEF = [
    "General and special damages according to proof.",
    "Costs of suit incurred herein.",
    "Such other and further relief as the Court deems just and proper.",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "document").strip().lower())
    return text.strip("-") or "document"


def _unique_preserving_order(values: Iterable[str]) -> List[str]:
    seen = set()
    unique: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def _coerce_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _extract_text_candidates(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        results: List[str] = []
        for item in value:
            results.extend(_extract_text_candidates(item))
        return results
    if isinstance(value, dict):
        keys = (
            "fact",
            "fact_text",
            "text",
            "summary",
            "description",
            "name",
            "parsed_text_preview",
            "claim_element",
            "claim_element_text",
            "answer",
            "question",
            "title",
            "relevance",
        )
        results = []
        for key in keys:
            if key in value and value.get(key):
                results.extend(_extract_text_candidates(value.get(key)))
        return results
    return []


def _roman(index: int) -> str:
    numerals = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    value = max(1, int(index))
    result = []
    for number, symbol in numerals:
        while value >= number:
            result.append(symbol)
            value -= number
    return "".join(result)


def _safe_call(target: Any, method_name: str, *args: Any, **kwargs: Any) -> Any:
    method = getattr(target, method_name, None)
    if not callable(method):
        return None
    try:
        return method(*args, **kwargs)
    except Exception:
        return None


def _merge_status(current: str, candidate: str) -> str:
    order = {
        "ready": 0,
        "warning": 1,
        "blocked": 2,
    }
    current_status = str(current or "ready")
    candidate_status = str(candidate or "ready")
    return candidate_status if order.get(candidate_status, 0) > order.get(current_status, 0) else current_status


class FormalComplaintDocumentBuilder:
    def __init__(self, mediator: Any):
        self.mediator = mediator

    def build_package(
        self,
        *,
        user_id: Optional[str] = None,
        court_name: str = "United States District Court",
        district: str = "",
        county: Optional[str] = None,
        division: Optional[str] = None,
        court_header_override: Optional[str] = None,
        case_number: Optional[str] = None,
        lead_case_number: Optional[str] = None,
        related_case_number: Optional[str] = None,
        assigned_judge: Optional[str] = None,
        courtroom: Optional[str] = None,
        title_override: Optional[str] = None,
        plaintiff_names: Optional[List[str]] = None,
        defendant_names: Optional[List[str]] = None,
        requested_relief: Optional[List[str]] = None,
        jury_demand: Optional[bool] = None,
        jury_demand_text: Optional[str] = None,
        signer_name: Optional[str] = None,
        signer_title: Optional[str] = None,
        signer_firm: Optional[str] = None,
        signer_bar_number: Optional[str] = None,
        signer_contact: Optional[str] = None,
        additional_signers: Optional[List[Dict[str, str]]] = None,
        declarant_name: Optional[str] = None,
        service_method: Optional[str] = None,
        service_recipients: Optional[List[str]] = None,
        service_recipient_details: Optional[List[Dict[str, str]]] = None,
        signature_date: Optional[str] = None,
        verification_date: Optional[str] = None,
        service_date: Optional[str] = None,
        affidavit_title: Optional[str] = None,
        affidavit_intro: Optional[str] = None,
        affidavit_facts: Optional[List[str]] = None,
        affidavit_supporting_exhibits: Optional[List[Dict[str, str]]] = None,
        affidavit_include_complaint_exhibits: Optional[bool] = None,
        affidavit_venue_lines: Optional[List[str]] = None,
        affidavit_jurat: Optional[str] = None,
        affidavit_notary_block: Optional[List[str]] = None,
        enable_agentic_optimization: bool = False,
        optimization_max_iterations: int = 2,
        optimization_target_score: float = 0.9,
        optimization_provider: Optional[str] = None,
        optimization_model_name: Optional[str] = None,
        optimization_llm_config: Optional[Dict[str, Any]] = None,
        optimization_persist_artifacts: bool = False,
        output_dir: Optional[str] = None,
        output_formats: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        resolved_user_id = self._resolve_user_id(user_id)
        formats = self._normalize_formats(output_formats)
        draft = self.build_draft(
            user_id=resolved_user_id,
            court_name=court_name,
            district=district,
            county=county,
            division=division,
            court_header_override=court_header_override,
            case_number=case_number,
            lead_case_number=lead_case_number,
            related_case_number=related_case_number,
            assigned_judge=assigned_judge,
            courtroom=courtroom,
            title_override=title_override,
            plaintiff_names=plaintiff_names,
            defendant_names=defendant_names,
            requested_relief=requested_relief,
            jury_demand=jury_demand,
            jury_demand_text=jury_demand_text,
            signer_name=signer_name,
            signer_title=signer_title,
            signer_firm=signer_firm,
            signer_bar_number=signer_bar_number,
            signer_contact=signer_contact,
            additional_signers=additional_signers,
            declarant_name=declarant_name,
            service_method=service_method,
            service_recipients=service_recipients,
            service_recipient_details=service_recipient_details,
            signature_date=signature_date,
            verification_date=verification_date,
            service_date=service_date,
            affidavit_title=affidavit_title,
            affidavit_intro=affidavit_intro,
            affidavit_facts=affidavit_facts,
            affidavit_supporting_exhibits=affidavit_supporting_exhibits,
            affidavit_include_complaint_exhibits=affidavit_include_complaint_exhibits,
            affidavit_venue_lines=affidavit_venue_lines,
            affidavit_jurat=affidavit_jurat,
            affidavit_notary_block=affidavit_notary_block,
        )
        document_optimization = None
        if enable_agentic_optimization:
            draft, document_optimization = self._optimize_draft(
                draft,
                max_iterations=optimization_max_iterations,
                target_score=optimization_target_score,
                provider=optimization_provider,
                model_name=optimization_model_name,
                llm_config=optimization_llm_config,
                persist_artifacts=optimization_persist_artifacts,
            )
        drafting_readiness = self._build_drafting_readiness(
            user_id=resolved_user_id,
            draft=draft,
        )
        filing_checklist = self._build_filing_checklist(drafting_readiness)
        self._annotate_filing_checklist_review_links(
            filing_checklist=filing_checklist,
            drafting_readiness=drafting_readiness,
            user_id=resolved_user_id,
        )
        draft["drafting_readiness"] = drafting_readiness
        draft["filing_checklist"] = filing_checklist
        draft["affidavit"] = self._build_affidavit(draft)
        artifacts = self.render_artifacts(
            draft,
            output_dir=output_dir,
            output_formats=formats,
        )
        return {
            "draft": draft,
            "drafting_readiness": drafting_readiness,
            "filing_checklist": filing_checklist,
            "artifacts": artifacts,
            "document_optimization": document_optimization,
            "output_formats": formats,
            "generated_at": _utcnow().isoformat(),
        }

    def build_draft(
        self,
        *,
        user_id: str,
        court_name: str,
        district: str,
        county: Optional[str],
        division: Optional[str],
        court_header_override: Optional[str],
        case_number: Optional[str],
        lead_case_number: Optional[str],
        related_case_number: Optional[str],
        assigned_judge: Optional[str],
        courtroom: Optional[str],
        title_override: Optional[str],
        plaintiff_names: Optional[List[str]],
        defendant_names: Optional[List[str]],
        requested_relief: Optional[List[str]],
        jury_demand: Optional[bool],
        jury_demand_text: Optional[str],
        signer_name: Optional[str],
        signer_title: Optional[str],
        signer_firm: Optional[str],
        signer_bar_number: Optional[str],
        signer_contact: Optional[str],
        additional_signers: Optional[List[Dict[str, str]]],
        declarant_name: Optional[str],
        service_method: Optional[str],
        service_recipients: Optional[List[str]],
        service_recipient_details: Optional[List[Dict[str, str]]],
        signature_date: Optional[str],
        verification_date: Optional[str],
        service_date: Optional[str],
        affidavit_title: Optional[str],
        affidavit_intro: Optional[str],
        affidavit_facts: Optional[List[str]],
        affidavit_supporting_exhibits: Optional[List[Dict[str, str]]],
        affidavit_include_complaint_exhibits: Optional[bool],
        affidavit_venue_lines: Optional[List[str]],
        affidavit_jurat: Optional[str],
        affidavit_notary_block: Optional[List[str]],
    ) -> Dict[str, Any]:
        affidavit_overrides = self._build_affidavit_overrides(
            affidavit_title=affidavit_title,
            affidavit_intro=affidavit_intro,
            affidavit_facts=affidavit_facts,
            affidavit_supporting_exhibits=affidavit_supporting_exhibits,
            affidavit_include_complaint_exhibits=affidavit_include_complaint_exhibits,
            affidavit_venue_lines=affidavit_venue_lines,
            affidavit_jurat=affidavit_jurat,
            affidavit_notary_block=affidavit_notary_block,
        )
        canonical_generate = getattr(self.mediator, "generate_formal_complaint", None)
        if callable(canonical_generate):
            try:
                result = canonical_generate(
                    user_id=user_id,
                    court_name=court_name,
                    district=district,
                    county=county,
                    division=division,
                    court_header_override=court_header_override,
                    case_number=case_number,
                    lead_case_number=lead_case_number,
                    related_case_number=related_case_number,
                    assigned_judge=assigned_judge,
                    courtroom=courtroom,
                    title_override=title_override,
                    plaintiff_names=plaintiff_names,
                    defendant_names=defendant_names,
                    requested_relief=requested_relief,
                    jury_demand=jury_demand,
                    jury_demand_text=jury_demand_text,
                    signer_name=signer_name,
                    signer_title=signer_title,
                    signer_firm=signer_firm,
                    signer_bar_number=signer_bar_number,
                    signer_contact=signer_contact,
                    additional_signers=additional_signers,
                    declarant_name=declarant_name,
                    service_method=service_method,
                    service_recipients=service_recipients,
                    service_recipient_details=service_recipient_details,
                    signature_date=signature_date,
                    verification_date=verification_date,
                    service_date=service_date,
                    affidavit_title=affidavit_title,
                    affidavit_intro=affidavit_intro,
                    affidavit_facts=affidavit_facts,
                    affidavit_supporting_exhibits=affidavit_supporting_exhibits,
                    affidavit_include_complaint_exhibits=affidavit_include_complaint_exhibits,
                    affidavit_venue_lines=affidavit_venue_lines,
                    affidavit_jurat=affidavit_jurat,
                    affidavit_notary_block=affidavit_notary_block,
                )
            except TypeError:
                result = None
            if isinstance(result, dict) and isinstance(result.get("formal_complaint"), dict):
                draft = self._adapt_formal_complaint_to_package_draft(result["formal_complaint"])
                draft["affidavit_overrides"] = affidavit_overrides
                draft["affidavit"] = self._build_affidavit(draft)
                draft["draft_text"] = self._render_draft_text(draft)
                return draft

        return self._build_legacy_draft(
            user_id=user_id,
            court_name=court_name,
            district=district,
            county=county,
            division=division,
            court_header_override=court_header_override,
            case_number=case_number,
            lead_case_number=lead_case_number,
            related_case_number=related_case_number,
            assigned_judge=assigned_judge,
            courtroom=courtroom,
            title_override=title_override,
            plaintiff_names=plaintiff_names,
            defendant_names=defendant_names,
            requested_relief=requested_relief,
            jury_demand=jury_demand,
            jury_demand_text=jury_demand_text,
            signer_name=signer_name,
            signer_title=signer_title,
            signer_firm=signer_firm,
            signer_bar_number=signer_bar_number,
            signer_contact=signer_contact,
            additional_signers=additional_signers,
            declarant_name=declarant_name,
            service_method=service_method,
            service_recipients=service_recipients,
            service_recipient_details=service_recipient_details,
            signature_date=signature_date,
            verification_date=verification_date,
            service_date=service_date,
            affidavit_title=affidavit_title,
            affidavit_intro=affidavit_intro,
            affidavit_facts=affidavit_facts,
            affidavit_supporting_exhibits=affidavit_supporting_exhibits,
            affidavit_include_complaint_exhibits=affidavit_include_complaint_exhibits,
            affidavit_venue_lines=affidavit_venue_lines,
            affidavit_jurat=affidavit_jurat,
            affidavit_notary_block=affidavit_notary_block,
        )

    def _build_legacy_draft(
        self,
        *,
        user_id: str,
        court_name: str,
        district: str,
        county: Optional[str],
        division: Optional[str],
        court_header_override: Optional[str],
        case_number: Optional[str],
        lead_case_number: Optional[str],
        related_case_number: Optional[str],
        assigned_judge: Optional[str],
        courtroom: Optional[str],
        title_override: Optional[str],
        plaintiff_names: Optional[List[str]],
        defendant_names: Optional[List[str]],
        requested_relief: Optional[List[str]],
        jury_demand: Optional[bool],
        jury_demand_text: Optional[str],
        signer_name: Optional[str],
        signer_title: Optional[str],
        signer_firm: Optional[str],
        signer_bar_number: Optional[str],
        signer_contact: Optional[str],
        additional_signers: Optional[List[Dict[str, str]]],
        declarant_name: Optional[str],
        service_method: Optional[str],
        service_recipients: Optional[List[str]],
        service_recipient_details: Optional[List[Dict[str, str]]],
        signature_date: Optional[str],
        verification_date: Optional[str],
        service_date: Optional[str],
        affidavit_title: Optional[str],
        affidavit_intro: Optional[str],
        affidavit_facts: Optional[List[str]],
        affidavit_supporting_exhibits: Optional[List[Dict[str, str]]],
        affidavit_include_complaint_exhibits: Optional[bool],
        affidavit_venue_lines: Optional[List[str]],
        affidavit_jurat: Optional[str],
        affidavit_notary_block: Optional[List[str]],
    ) -> Dict[str, Any]:
        state = getattr(self.mediator, "state", None)
        generated_complaint = self._get_existing_formal_complaint()
        classification = getattr(state, "legal_classification", {}) or {}
        statutes = _coerce_list(getattr(state, "applicable_statutes", []) or [])
        requirements = getattr(state, "summary_judgment_requirements", {}) or {}
        support_summary = _safe_call(self.mediator, "summarize_claim_support", user_id=user_id) or {}
        support_claims = support_summary.get("claims", {}) if isinstance(support_summary, dict) else {}
        claim_types = self._derive_claim_types(generated_complaint, classification, support_claims, requirements)
        plaintiffs, defendants = self._derive_parties(
            generated_complaint,
            plaintiff_names=plaintiff_names,
            defendant_names=defendant_names,
        )
        title = title_override or generated_complaint.get("title") or self._derive_title(plaintiffs, defendants)
        exhibits = self._collect_exhibits(user_id=user_id, claim_types=claim_types, support_claims=support_claims)
        facts = self._collect_general_facts(generated_complaint, classification, state)
        facts = self._annotate_lines_with_exhibits(facts, exhibits)
        claims_for_relief = self._build_claims_for_relief(
            user_id=user_id,
            claim_types=claim_types,
            requirements=requirements,
            statutes=statutes,
            support_claims=support_claims,
            exhibits=exhibits,
        )
        factual_allegations = self._build_factual_allegations(
            summary_of_facts=facts,
            claims_for_relief=claims_for_relief,
        )
        relief_items = _unique_preserving_order(
            list(requested_relief or [])
            + list(generated_complaint.get("prayer_for_relief", []) or [])
            + self._extract_requested_relief_from_facts(facts)
            + (STATE_DEFAULT_RELIEF if str(classification.get("jurisdiction") or "").strip().lower() == "state" else DEFAULT_RELIEF)
        )
        jury_demand_block = self._build_jury_demand(jury_demand=jury_demand, jury_demand_text=jury_demand_text)
        court_header = self._build_court_header(
            court_name=court_name,
            district=district,
            county=county,
            division=division,
            override=court_header_override,
        )
        jurisdiction_statement = self._build_jurisdiction_statement(
            classification=classification,
            statutes=statutes,
            court_name=court_name,
        )
        venue_statement = self._build_venue_statement(
            district=district,
            county=county,
            division=division,
            classification=classification,
            court_name=court_name,
        )
        nature_of_action = self._build_nature_of_action(
            claim_types=claim_types,
            classification=classification,
            statutes=statutes,
            court_name=court_name,
        )
        legal_standards = self._build_legal_standards_summary(statutes=statutes, requirements=requirements)
        signature_block = self._build_signature_block(
            plaintiffs,
            signer_name=signer_name,
            signer_title=signer_title,
            signer_firm=signer_firm,
            signer_bar_number=signer_bar_number,
            signer_contact=signer_contact,
            additional_signers=additional_signers,
            signature_date=signature_date,
        )
        verification = self._build_verification(
            plaintiffs,
            declarant_name=declarant_name,
            signer_name=signer_name,
            verification_date=verification_date,
            jurisdiction=classification.get("jurisdiction"),
        )
        certificate_of_service = self._build_certificate_of_service(
            plaintiffs,
            defendants,
            signer_name=signer_name,
            service_method=service_method,
            service_recipients=service_recipients,
            service_recipient_details=service_recipient_details,
            service_date=service_date,
            jurisdiction=classification.get("jurisdiction"),
        )

        draft = {
            "court_header": court_header,
            "case_caption": {
                "plaintiffs": plaintiffs,
                "defendants": defendants,
                "case_number": case_number or "________________",
                "county": county.strip().upper() if isinstance(county, str) and county.strip() else None,
                "lead_case_number": lead_case_number.strip() if isinstance(lead_case_number, str) and lead_case_number.strip() else None,
                "related_case_number": related_case_number.strip() if isinstance(related_case_number, str) and related_case_number.strip() else None,
                "assigned_judge": assigned_judge.strip() if isinstance(assigned_judge, str) and assigned_judge.strip() else None,
                "courtroom": courtroom.strip() if isinstance(courtroom, str) and courtroom.strip() else None,
                "jury_demand_notice": "JURY TRIAL DEMANDED" if jury_demand_block else None,
                "document_title": "COMPLAINT",
            },
            "title": title,
            "nature_of_action": nature_of_action,
            "parties": {
                "plaintiffs": plaintiffs,
                "defendants": defendants,
            },
            "jurisdiction_statement": jurisdiction_statement,
            "venue_statement": venue_statement,
            "factual_allegations": factual_allegations,
            "summary_of_facts": facts,
            "claims_for_relief": claims_for_relief,
            "legal_standards": legal_standards,
            "requested_relief": relief_items,
            "jury_demand": jury_demand_block,
            "exhibits": exhibits,
            "signature_block": signature_block,
            "verification": verification,
            "certificate_of_service": certificate_of_service,
            "source_context": {
                "user_id": user_id,
                "claim_types": claim_types,
                "district": district,
                "jurisdiction": classification.get("jurisdiction", "unknown"),
                "generated_at": _utcnow().isoformat(),
            },
            "affidavit_overrides": self._build_affidavit_overrides(
                affidavit_title=affidavit_title,
                affidavit_intro=affidavit_intro,
                affidavit_facts=affidavit_facts,
                affidavit_supporting_exhibits=affidavit_supporting_exhibits,
                affidavit_include_complaint_exhibits=affidavit_include_complaint_exhibits,
                affidavit_venue_lines=affidavit_venue_lines,
                affidavit_jurat=affidavit_jurat,
                affidavit_notary_block=affidavit_notary_block,
            ),
        }
        self._attach_allegation_references(draft)
        self._annotate_case_caption_display(draft)
        draft["affidavit"] = self._build_affidavit(draft)
        draft["draft_text"] = self._render_draft_text(draft)
        return draft

    def _optimize_draft(
        self,
        draft: Dict[str, Any],
        *,
        max_iterations: int,
        target_score: float,
        provider: Optional[str],
        model_name: Optional[str],
        llm_config: Optional[Dict[str, Any]],
        persist_artifacts: bool,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        optimizer = AgenticDocumentOptimizer(
            self.mediator,
            builder=self,
            provider=provider,
            model_name=model_name,
            max_iterations=max_iterations,
            target_score=target_score,
            persist_artifacts=persist_artifacts,
        )
        report = optimizer.optimize_draft(
            draft=draft,
            user_id=None,
            drafting_readiness={},
            config={
                "provider": provider,
                "model_name": model_name,
                "max_iterations": max_iterations,
                "target_score": target_score,
                "persist_artifacts": persist_artifacts,
                "llm_config": dict(llm_config or {}),
            },
        )
        optimized_draft = report.get("draft") or dict(draft)
        optimized_draft["summary_of_facts"] = self._normalize_text_lines(optimized_draft.get("summary_of_facts", []))
        optimized_draft["factual_allegations"] = self._expand_allegation_sources(
            optimized_draft.get("factual_allegations", []),
            limit=24,
        ) or self._expand_allegation_sources(draft.get("factual_allegations", []), limit=24)
        for claim in _coerce_list(optimized_draft.get("claims_for_relief")):
            if not isinstance(claim, dict):
                continue
            claim["supporting_facts"] = self._expand_allegation_sources(
                claim.get("supporting_facts", []),
                limit=10,
            ) or self._normalize_text_lines(claim.get("supporting_facts", []))
        self._attach_allegation_references(optimized_draft)
        self._annotate_case_caption_display(optimized_draft)
        optimized_draft["affidavit"] = self._build_affidavit(optimized_draft)
        optimized_draft["draft_text"] = self._render_draft_text(optimized_draft)
        return optimized_draft, report

    def _adapt_formal_complaint_to_package_draft(self, formal_complaint: Dict[str, Any]) -> Dict[str, Any]:
        caption = formal_complaint.get("caption", {}) if isinstance(formal_complaint.get("caption"), dict) else {}
        claims_for_relief = []
        for claim in _coerce_list(formal_complaint.get("legal_claims")):
            if not isinstance(claim, dict):
                continue
            claims_for_relief.append(
                {
                    "claim_type": claim.get("claim_type") or claim.get("claim_name") or claim.get("title") or "Claim",
                    "count_title": claim.get("claim_name") or claim.get("title") or "Claim",
                    "legal_standards": _unique_preserving_order(
                        [claim.get("legal_standard", "")]
                        + [
                            f"{item.get('citation')} - {item.get('element')}"
                            if item.get("citation")
                            else str(item.get("element") or "")
                            for item in _coerce_list(claim.get("legal_standard_elements"))
                            if isinstance(item, dict) and (item.get("element") or item.get("citation"))
                        ]
                    ),
                    "supporting_facts": _unique_preserving_order(_extract_text_candidates(claim.get("supporting_facts"))),
                    "missing_elements": _unique_preserving_order(
                        _extract_text_candidates(claim.get("missing_requirements"))
                    ),
                    "partially_supported_elements": [],
                    "support_summary": {
                        "elements_satisfied": claim.get("elements_satisfied", ""),
                        "authority_count": len(_coerce_list(claim.get("supporting_authorities"))),
                    },
                    "supporting_exhibits": [
                        {
                            "label": exhibit.get("label"),
                            "title": exhibit.get("title"),
                            "link": exhibit.get("reference") or exhibit.get("source_url") or exhibit.get("link"),
                        }
                        for exhibit in _coerce_list(claim.get("supporting_exhibits"))
                        if isinstance(exhibit, dict)
                    ],
                }
            )

        legal_standards = []
        for standard in _coerce_list(formal_complaint.get("legal_standards")):
            if isinstance(standard, dict):
                claim_name = str(standard.get("claim_name") or standard.get("claim_type") or "").strip()
                body = str(standard.get("standard") or "").strip()
                citations = ", ".join(_unique_preserving_order(_extract_text_candidates(standard.get("citations"))))
                if claim_name and body and citations:
                    legal_standards.append(f"{claim_name}: {body} ({citations})")
                elif claim_name and body:
                    legal_standards.append(f"{claim_name}: {body}")
                elif body:
                    legal_standards.append(body)
            else:
                text = str(standard or "").strip()
                if text:
                    legal_standards.append(text)

        exhibits = []
        for exhibit in _coerce_list(formal_complaint.get("exhibits")):
            if not isinstance(exhibit, dict):
                continue
            exhibits.append(
                {
                    "label": exhibit.get("label"),
                    "title": exhibit.get("title") or exhibit.get("description") or "Supporting exhibit",
                    "claim_type": exhibit.get("claim_type"),
                    "kind": exhibit.get("kind") or "evidence",
                    "link": exhibit.get("reference") or exhibit.get("source_url") or exhibit.get("link") or "",
                    "source_ref": exhibit.get("cid") or exhibit.get("reference") or "",
                    "summary": exhibit.get("summary") or exhibit.get("description") or "",
                }
            )

        nature_of_action = formal_complaint.get("nature_of_action")
        if isinstance(nature_of_action, str):
            nature_of_action = [nature_of_action]

        factual_allegations = _unique_preserving_order(
            _extract_text_candidates(formal_complaint.get("factual_allegations") or formal_complaint.get("summary_of_facts"))
        )
        if not factual_allegations:
            factual_allegations = self._build_factual_allegations(
                summary_of_facts=_extract_text_candidates(formal_complaint.get("summary_of_facts")),
                claims_for_relief=claims_for_relief,
            )

        draft = {
            "court_header": formal_complaint.get("court_header", ""),
            "case_caption": {
                "plaintiffs": _coerce_list(formal_complaint.get("parties", {}).get("plaintiffs", [])) if isinstance(formal_complaint.get("parties"), dict) else [],
                "defendants": _coerce_list(formal_complaint.get("parties", {}).get("defendants", [])) if isinstance(formal_complaint.get("parties"), dict) else [],
                "case_number": caption.get("case_number") or formal_complaint.get("case_number") or "________________",
                "county": caption.get("county_line") or ((formal_complaint.get("caption") or {}).get("county_line") if isinstance(formal_complaint.get("caption"), dict) else ""),
                "lead_case_number": caption.get("lead_case_number") or ((formal_complaint.get("caption") or {}).get("lead_case_number") if isinstance(formal_complaint.get("caption"), dict) else ""),
                "related_case_number": caption.get("related_case_number") or ((formal_complaint.get("caption") or {}).get("related_case_number") if isinstance(formal_complaint.get("caption"), dict) else ""),
                "assigned_judge": caption.get("assigned_judge") or ((formal_complaint.get("caption") or {}).get("assigned_judge") if isinstance(formal_complaint.get("caption"), dict) else ""),
                "courtroom": caption.get("courtroom") or ((formal_complaint.get("caption") or {}).get("courtroom") if isinstance(formal_complaint.get("caption"), dict) else ""),
                "jury_demand_notice": caption.get("jury_demand_notice") or ((formal_complaint.get("caption") or {}).get("jury_demand_notice") if isinstance(formal_complaint.get("caption"), dict) else ""),
                "document_title": "COMPLAINT",
            },
            "title": formal_complaint.get("title") or caption.get("case_title") or "Complaint",
            "nature_of_action": _unique_preserving_order(_extract_text_candidates(nature_of_action)),
            "parties": formal_complaint.get("parties", {}),
            "jurisdiction_statement": formal_complaint.get("jurisdiction_statement", ""),
            "venue_statement": formal_complaint.get("venue_statement", ""),
            "factual_allegations": factual_allegations,
            "summary_of_facts": _unique_preserving_order(_extract_text_candidates(formal_complaint.get("summary_of_facts") or formal_complaint.get("factual_allegations"))),
            "claims_for_relief": claims_for_relief,
            "legal_standards": _unique_preserving_order(legal_standards),
            "requested_relief": _unique_preserving_order(_extract_text_candidates(formal_complaint.get("requested_relief") or formal_complaint.get("prayer_for_relief"))),
            "jury_demand": formal_complaint.get("jury_demand", {}),
            "exhibits": exhibits,
            "signature_block": formal_complaint.get("signature_block", {}),
            "verification": formal_complaint.get("verification", {}),
            "certificate_of_service": formal_complaint.get("certificate_of_service", {}),
            "source_context": {
                "generated_at": formal_complaint.get("generated_at") or _utcnow().isoformat(),
                "district": formal_complaint.get("district") or caption.get("district") or "",
                "jurisdiction": formal_complaint.get("jurisdiction", "unknown"),
            },
        }
        self._attach_allegation_references(draft)
        self._annotate_case_caption_display(draft)
        built_affidavit = self._build_affidavit(draft)
        existing_affidavit = formal_complaint.get("affidavit", {}) if isinstance(formal_complaint.get("affidavit"), dict) else {}
        draft["affidavit"] = {**built_affidavit, **existing_affidavit}
        rendered_draft_text = self._render_draft_text(draft)
        supplied_draft_text = str(formal_complaint.get("draft_text") or "").strip()
        expected_case_line = (
            f"{draft['case_caption'].get('case_number_label', 'Civil Action No.')} "
            f"{draft['case_caption'].get('case_number', '________________')}"
        )
        draft["draft_text"] = (
            supplied_draft_text
            if supplied_draft_text and expected_case_line in supplied_draft_text
            else rendered_draft_text
        )
        return draft

    def _format_county_for_header(self, county: Optional[str]) -> str:
        county_text = str(county or "").strip().upper()
        if not county_text:
            return ""
        if county_text.startswith("COUNTY OF "):
            return county_text
        if county_text.endswith(" COUNTY"):
            return f"COUNTY OF {county_text[:-7].strip()}"
        return f"COUNTY OF {county_text}"

    def _annotate_case_caption_display(self, draft: Dict[str, Any]) -> None:
        caption = draft.get("case_caption")
        if not isinstance(caption, dict):
            return
        source_context = draft.get("source_context", {}) if isinstance(draft.get("source_context"), dict) else {}
        jurisdiction = str(source_context.get("jurisdiction") or "").strip()
        forum_type = self._infer_forum_type(
            classification={"jurisdiction": jurisdiction},
            court_name=str(draft.get("court_header") or ""),
        )
        caption["forum_type"] = forum_type
        caption["case_number_label"] = caption.get("case_number_label") or (
            "Case No." if forum_type == "state" else "Civil Action No."
        )
        caption["lead_case_number_label"] = caption.get("lead_case_number_label") or (
            "Related Proceeding No." if forum_type == "state" else "Lead Case No."
        )
        caption["related_case_number_label"] = caption.get("related_case_number_label") or (
            "Coordination No." if forum_type == "state" else "Related Case No."
        )
        caption["assigned_judge_label"] = caption.get("assigned_judge_label") or (
            "Judicial Officer" if forum_type == "state" else "Assigned Judge"
        )
        caption["courtroom_label"] = caption.get("courtroom_label") or (
            "Department" if forum_type == "state" else "Courtroom"
        )
        plaintiff_names = caption.get("plaintiffs") if isinstance(caption.get("plaintiffs"), list) else []
        defendant_names = caption.get("defendants") if isinstance(caption.get("defendants"), list) else []
        caption["plaintiff_caption_label"] = caption.get("plaintiff_caption_label") or (
            "Plaintiff" if len(plaintiff_names) == 1 else "Plaintiffs"
        )
        caption["defendant_caption_label"] = caption.get("defendant_caption_label") or (
            "Defendant" if len(defendant_names) == 1 else "Defendants"
        )
        caption["caption_party_lines"] = caption.get("caption_party_lines") or self._build_caption_party_lines(caption)

    def _build_caption_party_lines(self, caption: Dict[str, Any]) -> List[str]:
        plaintiffs = caption.get("plaintiffs") if isinstance(caption.get("plaintiffs"), list) else []
        defendants = caption.get("defendants") if isinstance(caption.get("defendants"), list) else []
        plaintiff_names = [str(name).strip() for name in plaintiffs if str(name).strip()] or ["Plaintiff"]
        defendant_names = [str(name).strip() for name in defendants if str(name).strip()] or ["Defendant"]
        plaintiff_label = str(
            caption.get("plaintiff_caption_label")
            or ("Plaintiff" if len(plaintiff_names) == 1 else "Plaintiffs")
        ).strip()
        defendant_label = str(
            caption.get("defendant_caption_label")
            or ("Defendant" if len(defendant_names) == 1 else "Defendants")
        ).strip()
        return [
            f"{'\n'.join(plaintiff_names)}, {plaintiff_label},",
            "v.",
            f"{'\n'.join(defendant_names)}, {defendant_label}.",
        ]

    def _resolve_draft_forum_type(self, draft: Dict[str, Any]) -> str:
        caption = draft.get("case_caption", {}) if isinstance(draft.get("case_caption"), dict) else {}
        forum_type = str(caption.get("forum_type") or "").strip().lower()
        if forum_type:
            return forum_type
        source_context = draft.get("source_context", {}) if isinstance(draft.get("source_context"), dict) else {}
        return self._infer_forum_type(
            classification={"jurisdiction": source_context.get("jurisdiction")},
            court_name=str(draft.get("court_header") or ""),
        )

    def _build_party_section_lines(
        self,
        *,
        plaintiffs: List[str],
        defendants: List[str],
        forum_type: str,
    ) -> List[str]:
        plaintiff_names = [str(name).strip() for name in _coerce_list(plaintiffs) if str(name).strip()] or ["Plaintiff"]
        defendant_names = [str(name).strip() for name in _coerce_list(defendants) if str(name).strip()] or ["Defendant"]
        plaintiff_label = "Plaintiff" if len(plaintiff_names) == 1 else "Plaintiffs"
        defendant_label = "Defendant" if len(defendant_names) == 1 else "Defendants"
        plaintiff_names_text = ", ".join(plaintiff_names)
        defendant_names_text = ", ".join(defendant_names)
        if forum_type == "state":
            plaintiff_verb = "is" if len(plaintiff_names) == 1 else "are"
            defendant_verb = "is" if len(defendant_names) == 1 else "are"
            return [
                f"{plaintiff_label} {plaintiff_names_text} {plaintiff_verb} a party bringing this civil action in this Court.",
                f"{defendant_label} {defendant_names_text} {defendant_verb} named as the party from whom relief is sought.",
            ]
        return [
            f"{plaintiff_label}: {plaintiff_names_text}.",
            f"{defendant_label}: {defendant_names_text}.",
        ]

    def _build_jurisdiction_statement(
        self,
        *,
        classification: Dict[str, Any],
        statutes: List[Dict[str, Any]],
        court_name: str,
    ) -> str:
        forum_type = self._infer_forum_type(classification=classification, court_name=court_name)
        first_citation = next(
            (
                str(statute.get("citation") or "").strip()
                for statute in statutes
                if isinstance(statute, dict) and statute.get("citation")
            ),
            "",
        )
        if forum_type == "federal":
            if first_citation:
                return (
                    "This Court has subject-matter jurisdiction under federal law, including "
                    f"{first_citation}, because Plaintiff alleges violations arising under the laws of the United States."
                )
            return "This Court has subject-matter jurisdiction under 28 U.S.C. § 1331 because Plaintiff alleges claims arising under federal law."
        if forum_type == "state":
            if first_citation:
                return (
                    "This Court has subject-matter jurisdiction because Plaintiff asserts claims arising under "
                    f"the governing state law, including {first_citation}, and seeks relief within this Court's authority."
                )
            return (
                "This Court has subject-matter jurisdiction because Plaintiff asserts claims arising under the "
                "governing state law and seeks relief within this Court's authority."
            )
        return "This Court has subject-matter jurisdiction because the claims arise under the governing law identified in this pleading."

    def _build_venue_statement(
        self,
        *,
        district: str,
        county: Optional[str],
        division: Optional[str],
        classification: Dict[str, Any],
        court_name: str,
    ) -> str:
        district_text = str(district or "").strip()
        county_text = str(county or "").strip()
        division_text = str(division or "").strip()
        forum_type = self._infer_forum_type(classification=classification, court_name=court_name)
        if forum_type == "state" and county_text:
            return (
                "Venue is proper in this Court because a substantial part of the events or omissions giving rise "
                f"to these claims occurred in {county_text}."
            )
        if forum_type == "federal" and district_text and division_text:
            return (
                f"Venue is proper in the {division_text} Division of the {district_text} because a substantial part of the events or omissions giving rise to these claims occurred there."
            )
        if forum_type == "federal" and district_text:
            return (
                f"Venue is proper in the {district_text} because a substantial part of the events or omissions giving rise to these claims occurred there."
            )
        if forum_type == "state" and district_text and division_text:
            return (
                "Venue is proper in this Court because a substantial part of the events or omissions giving rise "
                f"to these claims occurred in {division_text}, {district_text}."
            )
        if forum_type == "state" and district_text:
            return (
                "Venue is proper in this Court because a substantial part of the events or omissions giving rise "
                f"to these claims occurred in {district_text}."
            )
        return "Venue is proper in this Court because a substantial part of the events or omissions giving rise to these claims occurred in this judicial district."

    def _render_draft_text(self, draft: Dict[str, Any]) -> str:
        caption = draft.get("case_caption", {}) if isinstance(draft.get("case_caption"), dict) else {}
        parties = draft.get("parties", {}) if isinstance(draft.get("parties"), dict) else {}
        signature_block = draft.get("signature_block", {}) if isinstance(draft.get("signature_block"), dict) else {}
        plaintiff_list = parties.get("plaintiffs", []) or caption.get("plaintiffs", []) or ["Plaintiff"]
        defendant_list = parties.get("defendants", []) or caption.get("defendants", []) or ["Defendant"]
        plaintiffs = ", ".join(plaintiff_list)
        defendants = ", ".join(defendant_list)
        forum_type = self._resolve_draft_forum_type(draft)
        caption_party_lines = caption.get("caption_party_lines") if isinstance(caption.get("caption_party_lines"), list) else self._build_caption_party_lines(caption)
        party_section_lines = self._build_party_section_lines(
            plaintiffs=plaintiff_list,
            defendants=defendant_list,
            forum_type=forum_type,
        )
        case_number_label = str(caption.get("case_number_label") or "Civil Action No.")
        lead_case_number_label = str(caption.get("lead_case_number_label") or "Lead Case No.")
        related_case_number_label = str(caption.get("related_case_number_label") or "Related Case No.")
        assigned_judge_label = str(caption.get("assigned_judge_label") or "Assigned Judge")
        courtroom_label = str(caption.get("courtroom_label") or "Courtroom")
        lines = [
            str(draft.get("court_header") or "IN THE COURT OF COMPETENT JURISDICTION"),
            *([str(caption.get("county"))] if caption.get("county") else []),
            "",
            *caption_party_lines,
            f"{case_number_label} {caption.get('case_number', '________________')}",
            *([f"{lead_case_number_label} {caption.get('lead_case_number')}"] if caption.get('lead_case_number') else []),
            *([f"{related_case_number_label} {caption.get('related_case_number')}"] if caption.get('related_case_number') else []),
            *([f"{assigned_judge_label}: {caption.get('assigned_judge')}"] if caption.get('assigned_judge') else []),
            *([f"{courtroom_label}: {caption.get('courtroom')}"] if caption.get('courtroom') else []),
            "",
            str(caption.get("document_title") or "COMPLAINT"),
            *([str(caption.get("jury_demand_notice"))] if caption.get("jury_demand_notice") else []),
            "",
            "NATURE OF THE ACTION",
        ]
        lines.extend(self._normalize_text_lines(draft.get("nature_of_action", [])))
        lines.extend([
            "",
            "PARTIES",
            *party_section_lines,
            "",
            "JURISDICTION AND VENUE",
        ])
        if draft.get("jurisdiction_statement"):
            lines.append(str(draft["jurisdiction_statement"]))
        if draft.get("venue_statement"):
            lines.append(str(draft["venue_statement"]))
        lines.extend(["", "FACTUAL ALLEGATIONS"])
        lines.extend(self._grouped_allegation_text_lines(draft))
        claims = draft.get("claims_for_relief", []) if isinstance(draft.get("claims_for_relief"), list) else []
        if claims:
            lines.extend(["", "CLAIMS FOR RELIEF"])
        for index, claim in enumerate(claims, start=1):
            lines.extend([
                "",
                f"COUNT {_roman(index)} - {claim.get('count_title', claim.get('claim_type', 'Claim'))}",
                "Legal Standard:",
            ])
            lines.extend(self._bulletize_lines(claim.get("legal_standards", [])))
            incorporated_clause = self._format_incorporated_reference_clause(
                claim.get("allegation_references", []),
                claim.get("supporting_exhibits", []),
            )
            if incorporated_clause:
                lines.append(incorporated_clause)
            lines.append("Claim-Specific Support:")
            lines.extend(self._bulletize_lines(claim.get("supporting_facts", [])))
            missing = self._normalize_text_lines(claim.get("missing_elements", []))
            if missing:
                lines.append("Open Support Gaps:")
                lines.extend([f"- {line}" for line in missing])
        lines.extend(["", "REQUESTED RELIEF"])
        if forum_type == "state":
            lines.append("Wherefore, Plaintiff prays for judgment against Defendant as follows:")
        lines.extend(self._numbered_lines(draft.get("requested_relief", [])))
        jury_demand = draft.get("jury_demand", {}) if isinstance(draft.get("jury_demand"), dict) else {}
        if jury_demand:
            lines.extend(["", str(jury_demand.get("title") or "JURY DEMAND").upper()])
            if jury_demand.get("text"):
                lines.append(str(jury_demand.get("text")))
        exhibits = draft.get("exhibits", []) if isinstance(draft.get("exhibits"), list) else []
        if exhibits:
            lines.extend(["", "EXHIBITS"])
            for exhibit in exhibits:
                if not isinstance(exhibit, dict):
                    continue
                text = f"{exhibit.get('label', 'Exhibit')} - {exhibit.get('title', 'Supporting exhibit')}"
                if exhibit.get("link"):
                    text = f"{text} ({exhibit['link']})"
                lines.append(text)
                if exhibit.get("summary"):
                    lines.append(f"  {exhibit['summary']}")
        verification = draft.get("verification", {}) if isinstance(draft.get("verification"), dict) else {}
        if verification:
            lines.extend([
                "",
                str(verification.get("title") or "Verification").upper(),
                str(verification.get("text") or ""),
                str(verification.get("dated") or ""),
                str(verification.get("signature_line") or ""),
            ])
        certificate_of_service = draft.get("certificate_of_service", {}) if isinstance(draft.get("certificate_of_service"), dict) else {}
        if certificate_of_service:
            lines.extend([
                "",
                str(certificate_of_service.get("title") or "Certificate of Service").upper(),
                str(certificate_of_service.get("text") or ""),
                str(certificate_of_service.get("dated") or ""),
                str(certificate_of_service.get("signature_line") or ""),
            ])
        affidavit = draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else {}
        if affidavit:
            lines.extend([
                "",
                str(affidavit.get("title") or "AFFIDAVIT IN SUPPORT OF COMPLAINT"),
            ])
            lines.extend(str(line) for line in _coerce_list(affidavit.get("venue_lines")) if str(line or "").strip())
            lines.extend([
                "",
                str(affidavit.get("intro") or ""),
                str(affidavit.get("knowledge_graph_note") or ""),
                "",
                "Affiant states as follows:",
            ])
            lines.extend(self._numbered_lines(affidavit.get("facts", [])))
            supporting_exhibits = affidavit.get("supporting_exhibits") if isinstance(affidavit.get("supporting_exhibits"), list) else []
            if supporting_exhibits:
                lines.extend(["", "AFFIDAVIT SUPPORTING EXHIBITS"])
                for exhibit in supporting_exhibits:
                    if not isinstance(exhibit, dict):
                        continue
                    exhibit_text = f"{exhibit.get('label', 'Exhibit')} - {exhibit.get('title', 'Supporting exhibit')}"
                    if exhibit.get("link"):
                        exhibit_text = f"{exhibit_text} ({exhibit['link']})"
                    lines.append(exhibit_text)
            lines.extend([
                "",
                str(affidavit.get("dated") or ""),
                str(affidavit.get("signature_line") or ""),
                str(affidavit.get("jurat") or ""),
            ])
            lines.extend(str(line) for line in _coerce_list(affidavit.get("notary_block")) if str(line or "").strip())
        lines.extend(["", *self._build_signature_section_lines(signature_block, forum_type)])
        return "\n".join(line for line in lines if line is not None)

    def _normalize_text_lines(self, values: Any) -> List[str]:
        normalized = []
        for value in _unique_preserving_order(_extract_text_candidates(values)):
            text = re.sub(r"\s+", " ", value).strip()
            if text:
                normalized.append(text)
        return normalized

    def _split_allegation_fragments(self, value: Any) -> List[str]:
        text = re.sub(r"\s+", " ", str(value or "")).strip(" -;")
        if not text:
            return []
        if ": " in text:
            prefix, suffix = text.split(": ", 1)
            prefix_lower = prefix.strip().lower()
            if (
                prefix.strip().endswith("?")
                or prefix_lower.startswith(("what ", "when ", "where ", "why ", "how ", "who ", "describe ", "explain "))
                or prefix_lower in {"what happened", "what relief do you want"}
            ):
                text = suffix.strip()
        parts = [
            part.strip(" -;")
            for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
            if part.strip(" -;")
        ]
        return parts or [text]

    def _formalize_allegation_fragment(self, value: Any) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip(" -;")
        if not text:
            return ""
        replacements = (
            (r"^i was\b", "Plaintiff was"),
            (r"^i am\b", "Plaintiff is"),
            (r"^i need\b", "Plaintiff needs"),
            (r"^i needed\b", "Plaintiff needed"),
            (r"^i lost\b", "Plaintiff lost"),
            (r"^i asked\b", "Plaintiff asked"),
            (r"^i reported\b", "Plaintiff reported"),
            (r"^i complained\b", "Plaintiff complained"),
            (r"^i informed\b", "Plaintiff informed"),
            (r"^i notified\b", "Plaintiff notified"),
            (r"^i requested\b", "Plaintiff requested"),
            (r"^i sought\b", "Plaintiff sought"),
            (r"^i experienced\b", "Plaintiff experienced"),
            (r"^i suffered\b", "Plaintiff suffered"),
            (r"^i told\b", "Plaintiff told"),
            (r"^they\b", "Defendant"),
        )
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        clause_replacements = (
            (r"([,;]\s+)i was\b", r"\1Plaintiff was"),
            (r"([,;]\s+)i am\b", r"\1Plaintiff is"),
            (r"([,;]\s+)i need\b", r"\1Plaintiff needs"),
            (r"([,;]\s+)i needed\b", r"\1Plaintiff needed"),
            (r"([,;]\s+)i lost\b", r"\1Plaintiff lost"),
            (r"([,;]\s+)i asked\b", r"\1Plaintiff asked"),
            (r"([,;]\s+)i reported\b", r"\1Plaintiff reported"),
            (r"([,;]\s+)i complained\b", r"\1Plaintiff complained"),
            (r"([,;]\s+)i requested\b", r"\1Plaintiff requested"),
            (r"([,;]\s+)i informed\b", r"\1Plaintiff informed"),
            (r"([,;]\s+)i notified\b", r"\1Plaintiff notified"),
            (r"([,;]\s+)i suffered\b", r"\1Plaintiff suffered"),
            (r"([,;]\s+)i experienced\b", r"\1Plaintiff experienced"),
            (r"([,;]\s+)i told\b", r"\1Plaintiff told"),
            (r"(\band\s+)i was\b", r"\1Plaintiff was"),
            (r"(\band\s+)i am\b", r"\1Plaintiff is"),
            (r"(\band\s+)i need\b", r"\1Plaintiff needs"),
            (r"(\band\s+)i needed\b", r"\1Plaintiff needed"),
            (r"(\band\s+)i lost\b", r"\1Plaintiff lost"),
            (r"(\band\s+)i asked\b", r"\1Plaintiff asked"),
            (r"(\band\s+)i reported\b", r"\1Plaintiff reported"),
            (r"(\band\s+)i complained\b", r"\1Plaintiff complained"),
            (r"(\band\s+)i requested\b", r"\1Plaintiff requested"),
            (r"(\band\s+)i informed\b", r"\1Plaintiff informed"),
            (r"(\band\s+)i notified\b", r"\1Plaintiff notified"),
            (r"(\band\s+)i suffered\b", r"\1Plaintiff suffered"),
            (r"(\band\s+)i experienced\b", r"\1Plaintiff experienced"),
            (r"(\band\s+)i told\b", r"\1Plaintiff told"),
            (r"(\bafter\s+)i was\b", r"\1Plaintiff was"),
            (r"(\bafter\s+)i am\b", r"\1Plaintiff is"),
            (r"(\bafter\s+)i need\b", r"\1Plaintiff needs"),
            (r"(\bafter\s+)i needed\b", r"\1Plaintiff needed"),
            (r"(\bafter\s+)i lost\b", r"\1Plaintiff lost"),
            (r"(\bafter\s+)i asked\b", r"\1Plaintiff asked"),
            (r"(\bafter\s+)i reported\b", r"\1Plaintiff reported"),
            (r"(\bafter\s+)i complained\b", r"\1Plaintiff complained"),
            (r"(\bafter\s+)i requested\b", r"\1Plaintiff requested"),
            (r"(\bafter\s+)i informed\b", r"\1Plaintiff informed"),
            (r"(\bafter\s+)i notified\b", r"\1Plaintiff notified"),
            (r"(\bafter\s+)i suffered\b", r"\1Plaintiff suffered"),
            (r"(\bafter\s+)i experienced\b", r"\1Plaintiff experienced"),
            (r"(\bafter\s+)i told\b", r"\1Plaintiff told"),
            (r"(\bthat\s+)i am\b", r"\1Plaintiff is"),
            (r"(\bthat\s+)i need\b", r"\1Plaintiff needs"),
            (r"(\bthat\s+)i needed\b", r"\1Plaintiff needed"),
            (r"(\bthat\s+)i asked\b", r"\1Plaintiff asked"),
            (r"(\bthat\s+)i complained\b", r"\1Plaintiff complained"),
            (r"(\bthat\s+)i requested\b", r"\1Plaintiff requested"),
            (r"(\bthat\s+)i told\b", r"\1Plaintiff told"),
        )
        for pattern, replacement in clause_replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        text = re.sub(r"\bmy\b", "Plaintiff's", text, flags=re.IGNORECASE)
        text = re.sub(r"\bmine\b", "Plaintiff's", text, flags=re.IGNORECASE)
        text = re.sub(r"\bme\b", "Plaintiff", text, flags=re.IGNORECASE)
        text = re.sub(r"\blost Plaintiff's pay and benefits\b", "lost pay and benefits", text, flags=re.IGNORECASE)
        text = re.sub(r"\blost Plaintiff's (pay|wages|salary|income|benefits)\b", r"lost \1", text, flags=re.IGNORECASE)
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        if len(text) < 12:
            return ""
        return text if text.endswith((".", "?", "!")) else f"{text}."

    def _is_factual_allegation_candidate(self, value: Any) -> bool:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return False
        lowered = text.lower()
        if re.match(r"^(as to [^,]+, )?plaintiff (seeks|requests|asks|demands)\b", lowered):
            return False
        if lowered.startswith(("requested relief", "relief requested", "element supported:")):
            return False
        if lowered.startswith(("evidence shows facts supporting", "the intake record describes facts supporting")):
            return False
        if re.match(r"^(as to [^,]+, )?(title\s+[ivxlcdm0-9]+\b|\d+\s+u\.s\.c\.|\d+\s+c\.f\.r\.|[a-z]{2,6}\.\s+gov\.\s+code\b)", lowered):
            return False
        if not re.search(
            r"\b(was|were|is|are|reported|complained|terminated|fired|retaliated|denied|refused|told|informed|notified|requested|sought|experienced|suffered|lost|made|engaged|opposed|filed|sent|emailed|wrote|received|occurred|happened|subjected|demoted|suspended|disciplined|reduced)\b",
            lowered,
        ):
            return False
        return True

    def _is_generic_claim_support_text(self, value: Any) -> bool:
        lowered = re.sub(r"\s+", " ", str(value or "")).strip().lower()
        return lowered.startswith(("evidence shows facts supporting", "the intake record describes facts supporting"))

    def _expand_allegation_sources(self, values: Any, *, limit: Optional[int] = None) -> List[str]:
        expanded: List[str] = []
        for value in _extract_text_candidates(values):
            for fragment in self._split_allegation_fragments(value):
                sentence = self._formalize_allegation_fragment(fragment)
                if not sentence or not self._is_factual_allegation_candidate(sentence):
                    continue
                expanded.append(sentence)
        unique = _unique_preserving_order(expanded)
        return unique[:limit] if limit is not None else unique

    def _synthesize_narrative_allegations(self, allegations: List[str]) -> List[str]:
        cleaned = [str(item).strip() for item in allegations if str(item).strip()]
        if not cleaned:
            return []

        def _normalize_adverse_clause(clause: str) -> str:
            text = str(clause or "").strip().rstrip(".!?")
            if re.match(r"^(after|following)\b", text, flags=re.IGNORECASE) and "," in text:
                text = text.split(",", 1)[1].strip()
            return text

        def _normalize_harm_clause(clause: str) -> str:
            text = str(clause or "").strip().rstrip(".!?")
            text = re.sub(r",?\s+as a result$", "", text, flags=re.IGNORECASE)
            text = re.sub(r",?\s+as a direct result$", "", text, flags=re.IGNORECASE)
            return text.strip()

        def _pick(pattern: str, *, require_plaintiff: bool = False) -> str:
            for item in cleaned:
                lowered = item.lower()
                if require_plaintiff and "plaintiff" not in lowered:
                    continue
                if re.search(pattern, lowered):
                    return item.rstrip(".!?")
            return ""

        report_clause = _pick(r"\b(reported|complained|opposed|informed|notified|told|requested)\b", require_plaintiff=True)
        adverse_clause = _pick(r"\b(terminated|fired|demoted|suspended|disciplined|retaliated|denied)\b")
        harm_clause = _pick(r"\blost (pay|wages|salary|income|benefits)\b|\b(suffered|experienced)\b", require_plaintiff=True)
        harm_already_tied_to_adverse_action = any(
            re.search(r"\b(lost|suffered|experienced)\b", item.lower())
            and re.search(r"\b(terminated|fired|demoted|suspended|disciplined|retaliated|denied)\b", item.lower())
            for item in cleaned
        )

        synthesized: List[str] = []
        if report_clause and adverse_clause:
            synthesized.append(f"After {report_clause}, {_normalize_adverse_clause(adverse_clause)}.")
        if harm_clause and not harm_already_tied_to_adverse_action:
            normalized_harm_clause = _normalize_harm_clause(harm_clause)
            loss_match = re.search(r"\blost ([^.]+)", normalized_harm_clause, flags=re.IGNORECASE)
            if loss_match:
                synthesized.append(f"As a direct result of Defendant's conduct, Plaintiff lost {loss_match.group(1).strip()}." )
        return _unique_preserving_order(synthesized)

    def _prune_subsumed_narrative_clauses(self, allegations: List[str]) -> List[str]:
        cleaned = [str(item).strip() for item in allegations if str(item).strip()]
        if not cleaned:
            return []

        def _pick(pattern: str, *, require_plaintiff: bool = False) -> str:
            for item in cleaned:
                lowered = item.lower()
                if require_plaintiff and "plaintiff" not in lowered:
                    continue
                if re.search(pattern, lowered):
                    return item.strip()
            return ""

        report_clause = _pick(r"\b(reported|complained|opposed|informed|notified|told|requested)\b", require_plaintiff=True)
        adverse_clause = _pick(r"\b(terminated|fired|demoted|suspended|disciplined|retaliated|denied)\b")
        has_harm_tied_to_adverse_action = any(
            re.search(r"\b(lost|suffered|experienced)\b", item.lower())
            and re.search(r"\b(terminated|fired|demoted|suspended|disciplined|retaliated|denied)\b", item.lower())
            for item in cleaned
        )
        consumed = {item.lower() for item in (report_clause, adverse_clause) if item}
        if has_harm_tied_to_adverse_action:
            combined_clause = _pick(
                r"\b(reported|complained|opposed|informed|notified|told|requested)\b.*\b(terminated|fired|demoted|suspended|disciplined|retaliated|denied)\b"
                r"|\b(terminated|fired|demoted|suspended|disciplined|retaliated|denied)\b.*\b(reported|complained|opposed|informed|notified|told|requested)\b",
                require_plaintiff=True,
            )
            if combined_clause:
                consumed.add(combined_clause.lower())
        return [item for item in cleaned if item.lower() not in consumed]

    def _prune_near_duplicate_allegations(self, allegations: List[str]) -> List[str]:
        def _tokens(value: str) -> set[str]:
            scrubbed = re.sub(r"\(see exhibit [^)]+\)", "", value, flags=re.IGNORECASE)
            return {
                token
                for token in re.split(r"\W+", scrubbed.lower())
                if len(token) >= 4 and token not in {"plaintiff", "defendant", "exhibit", "after", "those", "this", "that"}
            }

        def _categories(value: str) -> set[str]:
            lowered = value.lower()
            flags = set()
            if re.search(r"\b(reported|complained|opposed|informed|notified|told|requested)\b", lowered):
                flags.add("report")
            if re.search(r"\b(terminated|fired|demoted|suspended|disciplined|retaliated|denied|removed|stripped)\b", lowered) or re.search(r"\b(end(?:ed|ing))\b[^.]{0,40}\bemployment\b", lowered):
                flags.add("adverse")
            if re.search(r"\b(lost|suffered|experienced|benefits|wages|salary|income|opportunities)\b", lowered):
                flags.add("harm")
            return flags

        def _features(value: str) -> set[str]:
            lowered = value.lower()
            flags = set()
            if re.search(r"\b(reported|complained|opposed|informed|notified|told|requested)\b", lowered):
                flags.add("report")
            if re.search(r"\b(human resources|hr)\b", lowered):
                flags.add("hr")
            if re.search(r"\bregional management|management\b", lowered):
                flags.add("management")
            if re.search(r"\b(key|major)\s+accounts?\b|\b(accounts?)\b[^.]{0,20}\b(removed|stripped|taken away)\b|\b(removed|stripped|took away)\b[^.]{0,20}\baccounts?\b", lowered):
                flags.add("accounts")
            if re.search(r"\bovertime\b", lowered):
                flags.add("overtime")
            if re.search(r"\bshift(s)?\b", lowered):
                flags.add("shifts")
            if re.search(r"\b(absences?|attendance|treatment-related absences?)\b", lowered):
                flags.add("absences")
            if re.search(r"\b(disciplined|discipline|wrote me up|write-up|write up)\b", lowered):
                flags.add("discipline")
            if re.search(r"\b(accommodation|accommodate|light duty|schedule flexibility|medical restrictions?|doctor-imposed restrictions?)\b", lowered):
                flags.add("accommodation")
            if re.search(r"\b(restrictions?|light duty|schedule flexibility)\b", lowered):
                flags.add("restrictions")
            if re.search(r"\b(terminated|fired)\b", lowered) or re.search(r"\b(end(?:ed|ing))\b[^.]{0,40}\bemployment\b", lowered):
                flags.add("termination")
            if re.search(r"\b(wages|pay|salary|income|benefits)\b", lowered):
                flags.add("economic_harm")
            if re.search(r"\b(career opportunities|future opportunities|opportunities)\b", lowered):
                flags.add("opportunities")
            return flags

        kept: List[str] = []
        for candidate in allegations:
            candidate_tokens = _tokens(candidate)
            candidate_categories = _categories(candidate)
            candidate_features = _features(candidate)
            skip = False
            for existing in kept:
                existing_tokens = _tokens(existing)
                existing_categories = _categories(existing)
                existing_features = _features(existing)
                if not candidate_tokens or not existing_tokens:
                    continue
                if not (candidate_categories & existing_categories):
                    continue
                overlap = len(candidate_tokens & existing_tokens) / max(1, min(len(candidate_tokens), len(existing_tokens)))
                shared_features = candidate_features & existing_features
                if overlap >= 0.7:
                    skip = True
                    break
                if "adverse" in candidate_categories and "adverse" in existing_categories and len(shared_features) >= 3:
                    skip = True
                    break
                if "report" in candidate_categories and "report" in existing_categories and "accommodation" in shared_features and len(shared_features) >= 2:
                    skip = True
                    break
            if not skip:
                kept.append(candidate)
        return kept

    def _is_near_duplicate_allegation(self, candidate: str, existing: List[str]) -> bool:
        if not candidate:
            return False
        pruned = self._prune_near_duplicate_allegations([*existing, candidate])
        return len(pruned) == len(existing)

    def _build_factual_allegations(
        self,
        *,
        summary_of_facts: Any,
        claims_for_relief: List[Dict[str, Any]],
    ) -> List[str]:
        base_allegations = list(self._expand_allegation_sources(summary_of_facts, limit=14))
        allegations = list(self._synthesize_narrative_allegations(base_allegations))
        for item in self._prune_subsumed_narrative_clauses(base_allegations):
            if item.lower() not in {entry.lower() for entry in allegations}:
                allegations.append(item)
        seen = {entry.lower() for entry in allegations}

        for claim in _coerce_list(claims_for_relief):
            if not isinstance(claim, dict):
                continue
            count_title = str(claim.get("count_title") or claim.get("claim_type") or "Claim").strip()
            for fact in self._expand_allegation_sources(claim.get("supporting_facts", []), limit=10):
                if not fact:
                    continue
                if self._is_near_duplicate_allegation(fact, allegations):
                    continue
                prefixed_fact = fact
                if count_title and not fact.lower().startswith("as to ") and fact.lower() not in seen:
                    lowered = fact
                    if not re.match(r"^(Plaintiff|Defendant)\b", fact):
                        lowered = fact[0].lower() + fact[1:] if len(fact) > 1 and fact[0].isalpha() else fact
                    prefixed_fact = f"As to {count_title}, {lowered}"
                    if not prefixed_fact.endswith((".", "?", "!")):
                        prefixed_fact = f"{prefixed_fact}."
                key = prefixed_fact.lower()
                if key in seen:
                    continue
                seen.add(key)
                allegations.append(prefixed_fact)
                if len(allegations) >= 24:
                    return self._prune_near_duplicate_allegations(allegations)

        pruned = self._prune_near_duplicate_allegations(allegations)
        return pruned or ["Additional factual development is required before filing."]

    def _attach_allegation_references(self, draft: Dict[str, Any]) -> None:
        allegation_lines = self._normalize_text_lines(
            draft.get("factual_allegations") or draft.get("summary_of_facts", [])
        )
        paragraph_entries = [
            {
                "number": index,
                "text": text,
            }
            for index, text in enumerate(allegation_lines, start=1)
        ]
        draft["factual_allegations"] = allegation_lines
        draft["factual_allegation_paragraphs"] = paragraph_entries
        draft["factual_allegation_groups"] = self._build_factual_allegation_groups(paragraph_entries)

        claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim["allegation_references"] = self._select_allegation_references_for_claim(
                claim=claim,
                allegation_paragraphs=paragraph_entries,
            )

    def _build_factual_allegation_groups(self, allegation_paragraphs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ordered_titles = [
            "Protected Activity and Complaints",
            "Adverse Action and Retaliatory Conduct",
            "Damages and Resulting Harm",
            "Additional Factual Support",
        ]
        groups: Dict[str, List[Dict[str, Any]]] = {title: [] for title in ordered_titles}

        for paragraph in allegation_paragraphs:
            if not isinstance(paragraph, dict):
                continue
            text = str(paragraph.get("text") or "").strip()
            lowered = text.lower()
            if re.search(r"\b(reported|complained|opposed|informed|notified|told|requested)\b", lowered):
                title = "Protected Activity and Complaints"
            elif re.search(r"\b(terminated|fired|demoted|suspended|disciplined|retaliated|denied)\b", lowered):
                title = "Adverse Action and Retaliatory Conduct"
            elif re.search(r"\b(lost|damages|harm|injur|suffered|experienced|benefits|wages|salary|income)\b", lowered):
                title = "Damages and Resulting Harm"
            else:
                title = "Additional Factual Support"
            groups[title].append(paragraph)

        return [
            {"title": title, "paragraphs": groups[title]}
            for title in ordered_titles
            if groups[title]
        ]

    def _grouped_allegation_text_lines(self, draft: Dict[str, Any]) -> List[str]:
        groups = draft.get("factual_allegation_groups") if isinstance(draft.get("factual_allegation_groups"), list) else []
        if not groups:
            return self._numbered_lines(draft.get("factual_allegations") or draft.get("summary_of_facts", []))

        lines: List[str] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            title = str(group.get("title") or "").strip()
            paragraphs = group.get("paragraphs") if isinstance(group.get("paragraphs"), list) else []
            if not paragraphs:
                continue
            if title:
                lines.append(title.upper())
            for paragraph in paragraphs:
                if not isinstance(paragraph, dict):
                    continue
                number = paragraph.get("number")
                text = str(paragraph.get("text") or "").strip()
                if text:
                    lines.append(f"{number}. {text}" if number else text)
        return lines

    def _select_allegation_references_for_claim(
        self,
        *,
        claim: Dict[str, Any],
        allegation_paragraphs: List[Dict[str, Any]],
    ) -> List[int]:
        references: List[int] = []
        supporting_facts = self._normalize_text_lines(claim.get("supporting_facts", []))
        count_title = str(claim.get("count_title") or claim.get("claim_type") or "").strip().lower()

        for fact in supporting_facts:
            fact_tokens = self._text_tokens(fact)
            if not fact_tokens:
                continue
            best_number: Optional[int] = None
            best_score = 0
            fact_lower = fact.lower()
            for paragraph in allegation_paragraphs:
                if not isinstance(paragraph, dict):
                    continue
                paragraph_text = str(paragraph.get("text") or "").strip()
                paragraph_lower = paragraph_text.lower()
                paragraph_tokens = self._text_tokens(paragraph_text)
                score = len(fact_tokens & paragraph_tokens)
                if fact_lower in paragraph_lower:
                    score += 100
                if count_title and count_title in paragraph_lower:
                    score += 5
                if score > best_score:
                    best_score = score
                    best_number = int(paragraph.get("number", 0) or 0)
            if best_number and best_number not in references:
                references.append(best_number)
                if len(references) >= 6:
                    break

        if references:
            return references

        fallback = []
        for paragraph in allegation_paragraphs:
            paragraph_text = str(paragraph.get("text") or "").lower()
            if count_title and count_title in paragraph_text:
                fallback.append(int(paragraph.get("number", 0) or 0))
        return fallback[:4]

    def _format_paragraph_reference_clause(self, references: Any) -> str:
        values = []
        for value in _coerce_list(references):
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number > 0 and number not in values:
                values.append(number)
        if not values:
            return ""
        citation = self._format_paragraph_citation(values)
        return f"Plaintiff repeats and realleges {citation} as if fully set forth herein."

    def _format_incorporated_reference_clause(self, references: Any, exhibits: Any) -> str:
        paragraph_citation = self._format_paragraph_citation(references)
        exhibit_phrase = self._format_exhibit_reference_phrase(exhibits)
        if paragraph_citation and exhibit_phrase:
            return (
                f"Plaintiff repeats and realleges {paragraph_citation} and incorporates {exhibit_phrase} "
                "as if fully set forth herein."
            )
        if paragraph_citation:
            return f"Plaintiff repeats and realleges {paragraph_citation} as if fully set forth herein."
        if exhibit_phrase:
            return f"Plaintiff incorporates {exhibit_phrase} as if fully set forth herein."
        return ""

    def _format_paragraph_citation(self, references: Any) -> str:
        values = []
        for value in _coerce_list(references):
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number > 0 and number not in values:
                values.append(number)
        if not values:
            return ""
        values.sort()
        ranges: List[str] = []
        range_start = values[0]
        range_end = values[0]
        for number in values[1:]:
            if number == range_end + 1:
                range_end = number
                continue
            ranges.append(self._format_paragraph_range(range_start, range_end))
            range_start = number
            range_end = number
        ranges.append(self._format_paragraph_range(range_start, range_end))
        marker = "¶" if len(values) == 1 else "¶¶"
        return f"{marker} {', '.join(ranges)}"

    def _format_exhibit_reference_phrase(self, exhibits: Any) -> str:
        labels = []
        for exhibit in _coerce_list(exhibits):
            if not isinstance(exhibit, dict):
                continue
            label = str(exhibit.get("label") or "").strip()
            if label and label not in labels:
                labels.append(label)
        if not labels:
            return ""
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            return f"{labels[0]} and {labels[1]}"
        return f"{', '.join(labels[:-1])}, and {labels[-1]}"

    def _format_paragraph_range(self, start: int, end: int) -> str:
        return str(start) if start == end else f"{start}-{end}"

    def _numbered_lines(self, values: Any) -> List[str]:
        return [f"{index}. {line}" for index, line in enumerate(self._normalize_text_lines(values), start=1)]

    def _bulletize_lines(self, values: Any) -> List[str]:
        return [f"- {line}" for line in self._normalize_text_lines(values)]

    def _build_signature_block(
        self,
        plaintiffs: List[str],
        *,
        signer_name: Optional[str] = None,
        signer_title: Optional[str] = None,
        signer_firm: Optional[str] = None,
        signer_bar_number: Optional[str] = None,
        signer_contact: Optional[str] = None,
        additional_signers: Optional[List[Dict[str, str]]] = None,
        signature_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        plaintiff_name = str(signer_name or "").strip() or (plaintiffs or ["Plaintiff"])[0]
        return {
            "name": plaintiff_name,
            "signature_line": f"/s/ {plaintiff_name}",
            "title": str(signer_title or "").strip() or "Plaintiff, Pro Se",
            "firm": str(signer_firm or "").strip() or "",
            "bar_number": str(signer_bar_number or "").strip(),
            "contact": str(signer_contact or "").strip() or "Mailing address, telephone number, and email address to be completed before filing.",
            "additional_signers": self._normalize_additional_signers(additional_signers),
            "dated": self._format_dated_line("Dated", signature_date),
        }

    def _normalize_additional_signers(self, values: Any) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for item in _coerce_list(values):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("signer_name") or "").strip()
            title = str(item.get("title") or item.get("signer_title") or "").strip()
            firm = str(item.get("firm") or item.get("signer_firm") or "").strip()
            bar_number = str(item.get("bar_number") or item.get("signer_bar_number") or "").strip()
            contact = str(item.get("contact") or item.get("signer_contact") or "").strip()
            if not any((name, title, firm, bar_number, contact)):
                continue
            key = (name, title, firm, bar_number, contact)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                {
                    "name": name or "Additional Counsel",
                    "signature_line": f"/s/ {name}" if name else "",
                    "title": title,
                    "firm": firm,
                    "bar_number": bar_number,
                    "contact": contact,
                }
            )
        return normalized

    def _signature_block_lines(self, signature_block: Dict[str, Any], *, include_dated: bool = True) -> List[str]:
        lines: List[str] = [
            str(signature_block.get("signature_line") or "/s/ Plaintiff"),
            str(signature_block.get("name") or "Plaintiff"),
        ]
        for key in ("title", "firm"):
            if signature_block.get(key):
                lines.append(str(signature_block[key]))
        if signature_block.get("bar_number"):
            lines.append(f"Bar No. {signature_block['bar_number']}")
        if signature_block.get("contact"):
            lines.append(str(signature_block["contact"]))
        for signer in _coerce_list(signature_block.get("additional_signers")):
            if not isinstance(signer, dict):
                continue
            lines.append("")
            if signer.get("signature_line"):
                lines.append(str(signer["signature_line"]))
            lines.append(str(signer.get("name") or "Additional Counsel"))
            for key in ("title", "firm"):
                if signer.get(key):
                    lines.append(str(signer[key]))
            if signer.get("bar_number"):
                lines.append(f"Bar No. {signer['bar_number']}")
            if signer.get("contact"):
                lines.append(str(signer["contact"]))
        if include_dated and signature_block.get("dated"):
            lines.append(str(signature_block["dated"]))
        return lines

    def _build_signature_section_lines(self, signature_block: Dict[str, Any], forum_type: str) -> List[str]:
        if forum_type == "state":
            lines: List[str] = []
            if signature_block.get("dated"):
                lines.append(str(signature_block["dated"]))
            lines.extend(["", "Respectfully submitted,", *self._signature_block_lines(signature_block, include_dated=False)])
            return lines
        return ["Respectfully submitted,", *self._signature_block_lines(signature_block)]

    def _build_jury_demand(
        self,
        *,
        jury_demand: Optional[bool] = None,
        jury_demand_text: Optional[str] = None,
    ) -> Dict[str, str]:
        text = str(jury_demand_text or "").strip()
        if text:
            return {
                "title": "Jury Demand",
                "text": text if text.endswith((".", "?", "!")) else f"{text}.",
            }
        if jury_demand:
            return {
                "title": "Jury Demand",
                "text": "Plaintiff demands a trial by jury on all issues so triable.",
            }
        return {}

    def _build_verification(
        self,
        plaintiffs: List[str],
        *,
        declarant_name: Optional[str] = None,
        signer_name: Optional[str] = None,
        verification_date: Optional[str] = None,
        jurisdiction: Optional[str] = None,
    ) -> Dict[str, str]:
        plaintiff_name = str(declarant_name or "").strip() or str(signer_name or "").strip() or (plaintiffs or ["Plaintiff"])[0]
        is_state = str(jurisdiction or "").strip().lower() == "state"
        return {
            "title": "Verification",
            "text": (
                f"I, {plaintiff_name}, verify that I have reviewed this Complaint and know its contents. "
                "The facts stated in this Complaint are true of my own knowledge, except as to those matters "
                "stated on information and belief, and as to those matters I believe them to be true."
                if is_state
                else (
                    f"I, {plaintiff_name}, declare under penalty of perjury that I have reviewed this Complaint "
                    "and that the factual allegations stated in it are true and correct to the best of my knowledge, "
                    "information, and belief."
                )
            ),
            "dated": self._format_dated_line("Verified on" if is_state else "Executed on", verification_date),
            "signature_line": f"/s/ {plaintiff_name}",
        }

    def _build_certificate_of_service(
        self,
        plaintiffs: List[str],
        defendants: List[str],
        *,
        signer_name: Optional[str] = None,
        service_method: Optional[str] = None,
        service_recipients: Optional[List[str]] = None,
        service_recipient_details: Optional[List[Dict[str, str]]] = None,
        service_date: Optional[str] = None,
        jurisdiction: Optional[str] = None,
    ) -> Dict[str, Any]:
        plaintiff_name = str(signer_name or "").strip() or (plaintiffs or ["Plaintiff"])[0]
        recipient_details = self._normalize_service_recipient_details(service_recipient_details)
        detail_recipients = [detail["recipient"] for detail in recipient_details if detail.get("recipient")]
        recipients_list = _unique_preserving_order([str(item or "").strip() for item in _coerce_list(service_recipients)] + detail_recipients) or defendants or ["all defendants"]
        recipients = ", ".join(recipients_list)
        method_text = str(service_method or "").strip() or "a method authorized by the applicable rules of civil procedure"
        detail_lines = [self._format_service_recipient_detail(detail) for detail in recipient_details]
        is_state = str(jurisdiction or "").strip().lower() == "state"
        return {
            "title": "Proof of Service" if is_state else "Certificate of Service",
            "text": (
                ("I declare that a true and correct copy of this Complaint will be served promptly after filing on the following recipients."
                if is_state
                else "I certify that a true and correct copy of this Complaint will be served promptly after filing on the following recipients.")
                if detail_lines
                else (("I declare that a true and correct copy of this Complaint will be served on "
                if is_state else "I certify that a true and correct copy of this Complaint will be served on ")
                + f"{recipients} using {method_text} promptly after filing.")
            ),
            "recipients": recipients_list,
            "recipient_details": recipient_details,
            "detail_lines": detail_lines,
            "dated": self._format_dated_line("Service date", service_date),
            "signature_line": f"/s/ {plaintiff_name}",
        }

    def _normalize_service_recipient_details(self, values: Any) -> List[Dict[str, str]]:
        details: List[Dict[str, str]] = []
        seen = set()
        for item in _coerce_list(values):
            if not isinstance(item, dict):
                continue
            detail = {
                "recipient": str(item.get("recipient") or "").strip(),
                "method": str(item.get("method") or "").strip(),
                "address": str(item.get("address") or "").strip(),
                "notes": str(item.get("notes") or "").strip(),
            }
            if not any(detail.values()):
                continue
            key = (detail["recipient"], detail["method"], detail["address"], detail["notes"])
            if key in seen:
                continue
            seen.add(key)
            details.append(detail)
        return details

    def _format_service_recipient_detail(self, detail: Dict[str, str]) -> str:
        segments = [detail.get("recipient") or "Recipient"]
        if detail.get("method"):
            segments.append(f"Method: {detail['method']}")
        if detail.get("address"):
            segments.append(f"Address: {detail['address']}")
        if detail.get("notes"):
            segments.append(f"Notes: {detail['notes']}")
        return " | ".join(segment for segment in segments if segment)

    def _format_dated_line(self, label: str, value: Optional[str]) -> str:
        cleaned = str(value or "").strip()
        return f"{label}: {cleaned}" if cleaned else f"{label}: __________________"

    def render_artifacts(
        self,
        draft: Dict[str, Any],
        *,
        output_dir: Optional[str],
        output_formats: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        output_root = Path(output_dir).expanduser() if output_dir else DEFAULT_OUTPUT_DIR
        output_root.mkdir(parents=True, exist_ok=True)
        timestamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
        file_stem = f"{_slugify(draft.get('title') or 'complaint')}-{timestamp}"
        artifacts: Dict[str, Dict[str, Any]] = {}

        for output_format in output_formats:
            if output_format == "packet":
                continue
            path = self._artifact_path(output_root, file_stem, output_format)
            if output_format == "docx":
                self._render_docx(draft, path)
                affidavit_path = self._artifact_path(output_root, file_stem, output_format, document_kind="affidavit")
                self._render_affidavit_docx(draft, affidavit_path)
                artifacts["affidavit_docx"] = {
                    "path": str(affidavit_path),
                    "filename": affidavit_path.name,
                    "size_bytes": affidavit_path.stat().st_size,
                }
            elif output_format == "pdf":
                self._render_pdf(draft, path)
                affidavit_path = self._artifact_path(output_root, file_stem, output_format, document_kind="affidavit")
                self._render_affidavit_pdf(draft, affidavit_path)
                artifacts["affidavit_pdf"] = {
                    "path": str(affidavit_path),
                    "filename": affidavit_path.name,
                    "size_bytes": affidavit_path.stat().st_size,
                }
            elif output_format == "txt":
                self._render_txt(draft, path)
                affidavit_path = self._artifact_path(output_root, file_stem, output_format, document_kind="affidavit")
                self._render_affidavit_txt(draft, affidavit_path)
                artifacts["affidavit_txt"] = {
                    "path": str(affidavit_path),
                    "filename": affidavit_path.name,
                    "size_bytes": affidavit_path.stat().st_size,
                }
            elif output_format == "checklist":
                self._render_checklist_txt(draft, path)
            artifacts[output_format] = {
                "path": str(path),
                "filename": path.name,
                "size_bytes": path.stat().st_size,
            }

        if "packet" in output_formats:
            path = self._artifact_path(output_root, file_stem, "packet")
            self._render_packet_json(draft, path, artifacts=artifacts)
            artifacts["packet"] = {
                "path": str(path),
                "filename": path.name,
                "size_bytes": path.stat().st_size,
            }

        return artifacts

    def _resolve_user_id(self, user_id: Optional[str]) -> str:
        if user_id:
            return user_id
        state = getattr(self.mediator, "state", None)
        return (
            getattr(state, "username", None)
            or getattr(state, "hashed_username", None)
            or "anonymous"
        )

    def _normalize_formats(self, output_formats: Optional[List[str]]) -> List[str]:
        values = output_formats or ["docx", "pdf"]
        normalized = []
        for value in values:
            current = str(value or "").strip().lower()
            if current in {"docx", "pdf", "txt", "checklist", "packet"} and current not in normalized:
                normalized.append(current)
        return normalized or ["docx", "pdf"]

    def _build_affidavit_overrides(
        self,
        *,
        affidavit_title: Optional[str],
        affidavit_intro: Optional[str],
        affidavit_facts: Optional[List[str]],
        affidavit_supporting_exhibits: Optional[List[Dict[str, str]]],
        affidavit_include_complaint_exhibits: Optional[bool],
        affidavit_venue_lines: Optional[List[str]],
        affidavit_jurat: Optional[str],
        affidavit_notary_block: Optional[List[str]],
    ) -> Dict[str, Any]:
        normalized_override_facts = []
        for value in affidavit_facts or []:
            cleaned = self._sanitize_affidavit_fact(value)
            if cleaned:
                normalized_override_facts.append(cleaned)
        normalized_supporting_exhibits = []
        for exhibit in _coerce_list(affidavit_supporting_exhibits):
            if not isinstance(exhibit, dict):
                continue
            normalized = {
                "label": str(exhibit.get("label") or "Exhibit").strip(),
                "title": str(exhibit.get("title") or exhibit.get("summary") or "Supporting exhibit").strip(),
                "link": str(exhibit.get("link") or exhibit.get("reference") or "").strip(),
                "summary": str(exhibit.get("summary") or "").strip(),
            }
            if any(normalized.values()):
                normalized_supporting_exhibits.append(normalized)
        return {
            "title": str(affidavit_title or "").strip() or None,
            "intro": str(affidavit_intro or "").strip() or None,
            "facts": normalized_override_facts,
            "supporting_exhibits": normalized_supporting_exhibits,
            "include_complaint_exhibits": affidavit_include_complaint_exhibits,
            "venue_lines": self._normalize_text_lines(affidavit_venue_lines or []),
            "jurat": str(affidavit_jurat or "").strip() or None,
            "notary_block": self._normalize_text_lines(affidavit_notary_block or []),
        }

    def _build_affidavit(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        verification = draft.get("verification", {}) if isinstance(draft.get("verification"), dict) else {}
        signature_block = draft.get("signature_block", {}) if isinstance(draft.get("signature_block"), dict) else {}
        case_caption = draft.get("case_caption", {}) if isinstance(draft.get("case_caption"), dict) else {}
        affidavit_overrides = draft.get("affidavit_overrides", {}) if isinstance(draft.get("affidavit_overrides"), dict) else {}
        declarant_name = self._derive_affidavit_declarant_name(draft)
        is_state = self._resolve_draft_forum_type(draft) == "state"
        exhibits = []
        for exhibit in _coerce_list(draft.get("exhibits")):
            if not isinstance(exhibit, dict):
                continue
            exhibits.append(
                {
                    "label": str(exhibit.get("label") or "Exhibit").strip(),
                    "title": str(exhibit.get("title") or exhibit.get("summary") or "Supporting exhibit").strip(),
                    "link": str(exhibit.get("link") or exhibit.get("reference") or "").strip(),
                    "summary": str(exhibit.get("summary") or "").strip(),
                }
            )
        return {
            "title": str(affidavit_overrides.get("title") or f"AFFIDAVIT OF {declarant_name.upper()} IN SUPPORT OF COMPLAINT"),
            "declarant_name": declarant_name,
            "intro": str(
                affidavit_overrides.get("intro")
                or (
                    (
                        f"I, {declarant_name}, being duly sworn, state that I am competent to testify to the matters stated below, "
                        "that these statements are based on my personal knowledge and the complaint intake knowledge graph assembled from the facts, records, and exhibits provided in support of this action, and that the following facts are true and correct."
                    )
                    if is_state
                    else (
                        f"I, {declarant_name}, declare under penalty of perjury that I am competent to testify to the matters stated below, "
                        "that these statements are based on my personal knowledge and the complaint intake knowledge graph assembled from the facts, records, and exhibits provided in support of this action, and that the following facts are true and correct."
                    )
                )
            ),
            "knowledge_graph_note": "This affidavit is generated from the complaint intake knowledge graph and supporting records rather than a turn-by-turn chat transcript.",
            "venue_lines": list(affidavit_overrides.get("venue_lines") or self._build_affidavit_venue_lines(draft)),
            "facts": list(affidavit_overrides.get("facts") or self._collect_affidavit_facts(draft)),
            "supporting_exhibits": list(
                affidavit_overrides.get("supporting_exhibits")
                or ([] if affidavit_overrides.get("include_complaint_exhibits") is False else exhibits)
            ),
            "dated": str(verification.get("dated") or signature_block.get("dated") or self._format_dated_line("Verified on" if is_state else "Executed on", None)),
            "signature_line": str(verification.get("signature_line") or signature_block.get("signature_line") or f"/s/ {declarant_name}"),
            "jurat": str(
                affidavit_overrides.get("jurat")
                or (
                    f"Subscribed and sworn to before me on __________________ by {declarant_name}."
                    if is_state
                    else f"Subscribed and sworn to (or affirmed) before me on __________________ by {declarant_name}."
                )
            ),
            "notary_block": list(
                affidavit_overrides.get("notary_block")
                or [
                    "__________________________________",
                    "Notary Public",
                    "My commission expires: __________________",
                ]
            ),
            "case_number": str(case_caption.get("case_number") or "________________"),
        }

    def _derive_affidavit_declarant_name(self, draft: Dict[str, Any]) -> str:
        verification = draft.get("verification", {}) if isinstance(draft.get("verification"), dict) else {}
        signature_block = draft.get("signature_block", {}) if isinstance(draft.get("signature_block"), dict) else {}
        parties = draft.get("parties", {}) if isinstance(draft.get("parties"), dict) else {}
        signature_line = str(verification.get("signature_line") or signature_block.get("signature_line") or "").strip()
        if signature_line.startswith("/s/ "):
            return signature_line[4:].strip() or str(signature_block.get("name") or "Plaintiff")
        plaintiffs = [str(name).strip() for name in _coerce_list(parties.get("plaintiffs")) if str(name).strip()]
        return str(signature_block.get("name") or (plaintiffs[0] if plaintiffs else "Plaintiff")).strip() or "Plaintiff"

    def _build_affidavit_venue_lines(self, draft: Dict[str, Any]) -> List[str]:
        caption = draft.get("case_caption", {}) if isinstance(draft.get("case_caption"), dict) else {}
        source_context = draft.get("source_context", {}) if isinstance(draft.get("source_context"), dict) else {}
        county = str(caption.get("county") or "").strip()
        district = str(source_context.get("district") or "").strip()
        jurisdiction = str(source_context.get("jurisdiction") or caption.get("forum_type") or "").strip().lower()
        lines: List[str] = []
        if district:
            lines.append(f"State/District: {district}")
        elif jurisdiction == "federal":
            lines.append("State/District: __________________")
        if county:
            lines.append(f"County: {county.title()}")
        elif jurisdiction == "state":
            lines.append("County: __________________")
        return lines or ["Venue: __________________"]

    def _collect_affidavit_facts(self, draft: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []
        parties = draft.get("parties", {}) if isinstance(draft.get("parties"), dict) else {}
        plaintiffs = [str(name).strip() for name in _coerce_list(parties.get("plaintiffs")) if str(name).strip()]
        if plaintiffs:
            candidates.append(f"I am {plaintiffs[0]}, the plaintiff in this action.")
        candidates.extend(self._normalize_text_lines(draft.get("factual_allegations", [])))

        facts: List[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            cleaned = self._sanitize_affidavit_fact(candidate)
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            facts.append(cleaned)
            if len(facts) >= 12:
                break
        return facts or ["Additional fact development is required before the affidavit can be finalized."]

    def _sanitize_affidavit_fact(self, value: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return ""
        text = re.sub(r"^As to [^,]+,\s*", "", text, flags=re.IGNORECASE)
        if ": " in text:
            prefix, suffix = text.split(": ", 1)
            prefix_lower = prefix.strip().lower()
            if (
                prefix.strip().endswith("?")
                or prefix_lower.startswith(("what ", "when ", "where ", "why ", "how ", "who ", "describe ", "explain "))
                or prefix_lower in {"what happened", "what relief do you want"}
            ):
                text = suffix.strip()
        lowered = text.lower()
        if lowered.startswith("plaintiff repeats and realleges"):
            return ""
        if not self._is_factual_allegation_candidate(text) and not lowered.startswith("i am "):
            return ""
        if len(text) < 12:
            return ""
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        if text[-1] not in ".!?":
            text = f"{text}."
        return text

    def _render_txt(self, draft: Dict[str, Any], path: Path) -> None:
        path.write_text(str(draft.get("draft_text") or self._render_draft_text(draft)), encoding="utf-8")

    def _render_affidavit_txt(self, draft: Dict[str, Any], path: Path) -> None:
        affidavit = draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else self._build_affidavit(draft)
        path.write_text(self._render_affidavit_text(draft, affidavit), encoding="utf-8")

    def _render_checklist_txt(self, draft: Dict[str, Any], path: Path) -> None:
        checklist = draft.get("filing_checklist") if isinstance(draft.get("filing_checklist"), list) else []
        title = str(draft.get("title") or draft.get("case_caption", {}).get("document_title") or "Complaint").strip()
        lines = [
            f"PRE-FILING CHECKLIST: {title}",
            "",
        ]
        if not checklist:
            lines.append("No pre-filing checklist items were generated.")
        else:
            for index, item in enumerate(checklist, start=1):
                if not isinstance(item, dict):
                    continue
                scope = str(item.get("scope") or "item").strip().upper()
                title_text = str(item.get("title") or "Checklist Item").strip()
                status = str(item.get("status") or "ready").strip().upper()
                summary = str(item.get("summary") or "").strip()
                detail = str(item.get("detail") or "").strip()
                review_url = str(item.get("review_url") or "").strip()
                lines.append(f"{index}. [{status}] {scope}: {title_text}")
                if summary:
                    lines.append(f"   Summary: {summary}")
                if detail:
                    lines.append(f"   Detail: {detail}")
                if review_url:
                    lines.append(f"   Review URL: {review_url}")
                lines.append("")
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _artifact_path(self, output_root: Path, file_stem: str, output_format: str, document_kind: str = "complaint") -> Path:
        suffix = "-affidavit" if document_kind == "affidavit" else ""
        if output_format == "checklist":
            return output_root / f"{file_stem}{suffix}-checklist.txt"
        if output_format == "packet":
            return output_root / f"{file_stem}-packet.json"
        return output_root / f"{file_stem}{suffix}.{output_format}"

    def _render_packet_json(
        self,
        draft: Dict[str, Any],
        path: Path,
        *,
        artifacts: Dict[str, Dict[str, Any]],
    ) -> None:
        payload = self._build_filing_packet_payload(draft, artifacts=artifacts)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _build_filing_packet_payload(
        self,
        draft: Dict[str, Any],
        *,
        artifacts: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        case_caption = draft.get("case_caption", {}) if isinstance(draft.get("case_caption"), dict) else {}
        source_context = draft.get("source_context", {}) if isinstance(draft.get("source_context"), dict) else {}
        packet_artifacts = {
            key: {
                "filename": value.get("filename"),
                "path": value.get("path"),
                "size_bytes": value.get("size_bytes"),
            }
            for key, value in artifacts.items()
            if isinstance(value, dict)
        }
        return {
            "title": draft.get("title"),
            "court_header": draft.get("court_header"),
            "generated_at": source_context.get("generated_at") or _utcnow().isoformat(),
            "case_caption": {
                "plaintiffs": case_caption.get("plaintiffs", []),
                "defendants": case_caption.get("defendants", []),
                "case_number": case_caption.get("case_number"),
                "document_title": case_caption.get("document_title"),
                "jury_demand_notice": case_caption.get("jury_demand_notice"),
            },
            "sections": {
                "nature_of_action": draft.get("nature_of_action", []),
                "summary_of_facts": draft.get("summary_of_facts", []),
                "factual_allegations": draft.get("factual_allegations", []),
                "claims_for_relief": draft.get("claims_for_relief", []),
                "legal_standards": draft.get("legal_standards", []),
                "requested_relief": draft.get("requested_relief", []),
            },
            "affidavit": draft.get("affidavit", {}),
            "verification": draft.get("verification", {}),
            "certificate_of_service": draft.get("certificate_of_service", {}),
            "exhibits": draft.get("exhibits", []),
            "filing_checklist": draft.get("filing_checklist", []),
            "drafting_readiness": draft.get("drafting_readiness", {}),
            "artifacts": packet_artifacts,
        }

    def _render_affidavit_text(self, draft: Dict[str, Any], affidavit: Dict[str, Any]) -> str:
        caption = draft.get("case_caption", {}) if isinstance(draft.get("case_caption"), dict) else {}
        caption_party_lines = caption.get("caption_party_lines") if isinstance(caption.get("caption_party_lines"), list) else self._build_caption_party_lines(caption)
        lines = [
            str(draft.get("court_header") or "IN THE COURT OF COMPETENT JURISDICTION"),
            *([str(caption.get("county"))] if caption.get("county") else []),
            "",
            *caption_party_lines,
            f"{caption.get('case_number_label', 'Civil Action No.')} {caption.get('case_number', '________________')}",
            "",
            str(affidavit.get("title") or "AFFIDAVIT IN SUPPORT OF COMPLAINT"),
            *[str(line) for line in _coerce_list(affidavit.get("venue_lines")) if str(line or "").strip()],
            "",
            str(affidavit.get("intro") or ""),
            str(affidavit.get("knowledge_graph_note") or ""),
            "",
            "Affiant states as follows:",
            *self._numbered_lines(affidavit.get("facts", [])),
        ]
        exhibits = affidavit.get("supporting_exhibits") if isinstance(affidavit.get("supporting_exhibits"), list) else []
        if exhibits:
            lines.extend(["", "SUPPORTING EXHIBITS"])
            for exhibit in exhibits:
                if not isinstance(exhibit, dict):
                    continue
                exhibit_text = f"{exhibit.get('label', 'Exhibit')} - {exhibit.get('title', 'Supporting exhibit')}"
                if exhibit.get("link"):
                    exhibit_text = f"{exhibit_text} ({exhibit['link']})"
                lines.append(exhibit_text)
        lines.extend(["", str(affidavit.get("dated") or ""), str(affidavit.get("signature_line") or ""), str(affidavit.get("jurat") or "")])
        lines.extend(str(line) for line in _coerce_list(affidavit.get("notary_block")) if str(line or "").strip())
        return "\n".join(line for line in lines if line is not None)

    def _render_affidavit_docx(self, draft: Dict[str, Any], path: Path) -> None:
        from docx import Document

        document = Document()
        for line in self._render_affidavit_text(
            draft,
            draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else self._build_affidavit(draft),
        ).split("\n"):
            document.add_paragraph(line)
        document.save(path)

    def _render_affidavit_pdf(self, draft: Dict[str, Any], path: Path) -> None:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        styles = getSampleStyleSheet()
        story = []
        for line in self._render_affidavit_text(
            draft,
            draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else self._build_affidavit(draft),
        ).split("\n"):
            story.append(Paragraph(escape(line or "&nbsp;"), styles["Normal"]))
            story.append(Spacer(1, 4))
        doc = SimpleDocTemplate(
            str(path),
            pagesize=LETTER,
            topMargin=inch,
            bottomMargin=inch,
            leftMargin=inch,
            rightMargin=inch,
        )
        doc.build(story)

    def _get_existing_formal_complaint(self) -> Dict[str, Any]:
        phase_manager = getattr(self.mediator, "phase_manager", None)
        if phase_manager is None:
            return {}
        existing = _safe_call(
            phase_manager,
            "get_phase_data",
            ComplaintPhase.FORMALIZATION,
            "formal_complaint",
        )
        if isinstance(existing, dict) and existing:
            return existing
        return {}

    def _derive_claim_types(
        self,
        generated_complaint: Dict[str, Any],
        classification: Dict[str, Any],
        support_claims: Dict[str, Any],
        requirements: Dict[str, Any],
    ) -> List[str]:
        claim_names = []
        claim_names.extend(_coerce_list(classification.get("claim_types")))
        claim_names.extend(list(support_claims.keys()))
        claim_names.extend(list(requirements.keys()))
        for claim in _coerce_list(generated_complaint.get("legal_claims")):
            if isinstance(claim, dict):
                claim_names.append(claim.get("title"))
        return _unique_preserving_order(claim_names) or ["General civil action"]

    def _derive_parties(
        self,
        generated_complaint: Dict[str, Any],
        *,
        plaintiff_names: Optional[List[str]],
        defendant_names: Optional[List[str]],
    ) -> tuple[List[str], List[str]]:
        parties = generated_complaint.get("parties", {}) if isinstance(generated_complaint, dict) else {}
        plaintiffs = _unique_preserving_order(
            list(plaintiff_names or []) + list(parties.get("plaintiffs", []) or [])
        ) or ["Plaintiff"]
        defendants = _unique_preserving_order(
            list(defendant_names or []) + list(parties.get("defendants", []) or [])
        ) or ["Defendant"]
        return plaintiffs, defendants

    def _derive_title(self, plaintiffs: List[str], defendants: List[str]) -> str:
        return f"{plaintiffs[0]} v. {defendants[0]}"

    def _build_court_header(
        self,
        *,
        court_name: str,
        district: str,
        county: Optional[str],
        division: Optional[str],
        override: Optional[str],
    ) -> str:
        if override:
            return override.strip().upper()
        court = str(court_name or "United States District Court").strip().upper()
        parts = [f"IN THE {court}"]
        forum_type = self._infer_forum_type(classification={}, court_name=court_name)
        county_text = self._format_county_for_header(county)
        if county_text and forum_type == "state":
            parts.append(f"FOR THE {county_text}")
        elif district:
            parts.append(f"FOR THE {str(district).strip().upper()}")
        if division:
            parts.append(str(division).strip().upper())
        return " ".join(parts)

    def _infer_forum_type(
        self,
        *,
        classification: Dict[str, Any],
        court_name: str,
    ) -> str:
        jurisdiction = str(classification.get("jurisdiction") or "").strip().lower()
        if jurisdiction in {"federal", "us", "united states"}:
            return "federal"
        if jurisdiction in {"state", "state court", "county", "local"}:
            return "state"

        court_name_text = str(court_name or "").strip().lower()
        if "united states" in court_name_text or "u.s." in court_name_text:
            return "federal"
        if any(
            marker in court_name_text
            for marker in ("superior court", "circuit court", "common pleas", "state of", "county")
        ):
            return "state"
        return "unknown"

    def _build_nature_of_action(
        self,
        *,
        claim_types: List[str],
        classification: Dict[str, Any],
        statutes: List[Dict[str, Any]],
        court_name: str,
    ) -> List[str]:
        claim_phrase = ", ".join(claim_types)
        legal_areas = ", ".join(_coerce_list(classification.get("legal_areas")))
        jurisdiction = str(classification.get("jurisdiction") or "the applicable court")
        forum_type = self._infer_forum_type(classification=classification, court_name=court_name)
        statute_refs = _unique_preserving_order(
            [s.get("citation") for s in statutes if isinstance(s, dict) and s.get("citation")]
        )
        if forum_type == "federal":
            paragraphs = [
                (
                    "This is a civil action arising under federal law and the facts disclosed during the "
                    f"complaint intake process. Plaintiff seeks relief for {claim_phrase} within {jurisdiction} jurisdiction."
                )
            ]
        elif forum_type == "state":
            paragraphs = [
                (
                    "This is a civil action brought in state court arising from the facts disclosed during "
                    f"the complaint intake process. Plaintiff seeks relief for {claim_phrase} under the governing state law."
                )
            ]
        else:
            paragraphs = [
                (
                    "This is a civil action arising from the facts disclosed during the complaint intake "
                    f"process. Plaintiff seeks relief for {claim_phrase} within {jurisdiction} jurisdiction."
                )
            ]
        if legal_areas:
            paragraphs.append(
                f"The action implicates the following areas of law: {legal_areas}."
            )
        if statute_refs:
            paragraphs.append(
                "The draft relies on the following principal legal authorities: "
                f"{', '.join(statute_refs[:5])}."
            )
        return paragraphs

    def _collect_general_facts(
        self,
        generated_complaint: Dict[str, Any],
        classification: Dict[str, Any],
        state: Any,
    ) -> List[str]:
        facts: List[str] = []
        for allegation in _coerce_list(generated_complaint.get("factual_allegations")):
            facts.extend(_extract_text_candidates(allegation))
        facts.extend(_extract_text_candidates(classification.get("key_facts")))
        for inquiry in _coerce_list(getattr(state, "inquiries", []) if state is not None else []):
            if isinstance(inquiry, dict):
                question = str(inquiry.get("question") or "").strip()
                answer = str(inquiry.get("answer") or "").strip()
                if answer:
                    if question:
                        facts.append(f"{question}: {answer}")
                    else:
                        facts.append(answer)
        complaint_text = getattr(state, "complaint", None) if state is not None else None
        original_text = getattr(state, "original_complaint", None) if state is not None else None
        if isinstance(complaint_text, dict):
            explicit_facts = _extract_text_candidates(complaint_text.get("facts"))
            if explicit_facts:
                facts.extend(explicit_facts)
            else:
                facts.extend(_extract_text_candidates(complaint_text.get("summary") or complaint_text))
        elif complaint_text:
            facts.extend(_extract_text_candidates(complaint_text))
        elif original_text:
            facts.extend(_extract_text_candidates(original_text))

        normalized = []
        for item in _unique_preserving_order(facts):
            text = re.sub(r"\s+", " ", item).strip()
            if len(text) < 12:
                continue
            normalized.append(text)
            if len(normalized) >= 12:
                break
        return normalized or ["Additional factual development is required before filing."]

    def _build_claims_for_relief(
        self,
        *,
        user_id: str,
        claim_types: List[str],
        requirements: Dict[str, Any],
        statutes: List[Dict[str, Any]],
        support_claims: Dict[str, Any],
        exhibits: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        claims: List[Dict[str, Any]] = []
        for claim_type in claim_types:
            support_claim = support_claims.get(claim_type, {}) if isinstance(support_claims, dict) else {}
            overview = _safe_call(
                self.mediator,
                "get_claim_overview",
                claim_type=claim_type,
                user_id=user_id,
                required_support_kinds=["evidence", "authority"],
            ) or {}
            overview_claim = overview.get("claims", {}).get(claim_type, {}) if isinstance(overview, dict) else {}
            related_exhibits = [
                exhibit for exhibit in exhibits if not exhibit.get("claim_type") or exhibit.get("claim_type") == claim_type
            ]
            claim_facts = self._collect_claim_facts(claim_type, user_id, support_claim)
            claim_facts = self._annotate_lines_with_exhibits(claim_facts, related_exhibits)
            source_context = self._extract_support_source_context_counts(support_claim)
            claims.append(
                {
                    "claim_type": claim_type,
                    "count_title": claim_type.title(),
                    "legal_standards": self._build_claim_legal_standards(
                        claim_type=claim_type,
                        requirements=requirements,
                        statutes=statutes,
                    ),
                    "supporting_facts": claim_facts,
                    "missing_elements": self._extract_overview_elements(overview_claim.get("missing")),
                    "partially_supported_elements": self._extract_overview_elements(
                        overview_claim.get("partially_supported")
                    ),
                    "support_summary": {
                        "total_elements": support_claim.get("total_elements", 0),
                        "covered_elements": support_claim.get("covered_elements", 0),
                        "uncovered_elements": support_claim.get("uncovered_elements", 0),
                        "support_by_kind": support_claim.get("support_by_kind", {}),
                        "support_by_source": source_context["support_by_source"],
                        "source_family_counts": source_context["source_family_counts"],
                        "record_scope_counts": source_context["record_scope_counts"],
                        "artifact_family_counts": source_context["artifact_family_counts"],
                        "corpus_family_counts": source_context["corpus_family_counts"],
                        "content_origin_counts": source_context["content_origin_counts"],
                    },
                    "supporting_exhibits": [
                        {
                            "label": exhibit.get("label"),
                            "title": exhibit.get("title"),
                            "link": exhibit.get("link"),
                        }
                        for exhibit in related_exhibits[:8]
                    ],
                }
            )
        return claims

    def _extract_support_source_context_counts(self, support_claim: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
        packet_summary = (
            support_claim.get("support_packet_summary", {})
            if isinstance(support_claim, dict) and isinstance(support_claim.get("support_packet_summary"), dict)
            else {}
        )

        def _normalized_counts(key: str) -> Dict[str, int]:
            primary = support_claim.get(key, {}) if isinstance(support_claim, dict) else {}
            fallback = packet_summary.get(key, {})
            source = primary if isinstance(primary, dict) and primary else fallback
            if not isinstance(source, dict):
                return {}
            counts: Dict[str, int] = {}
            for label, value in source.items():
                normalized_label = str(label or "").strip()
                if not normalized_label:
                    continue
                count = int(value or 0)
                if count <= 0:
                    continue
                counts[normalized_label] = count
            return counts

        return {
            "support_by_source": _normalized_counts("support_by_source"),
            "source_family_counts": _normalized_counts("source_family_counts"),
            "record_scope_counts": _normalized_counts("record_scope_counts"),
            "artifact_family_counts": _normalized_counts("artifact_family_counts"),
            "corpus_family_counts": _normalized_counts("corpus_family_counts"),
            "content_origin_counts": _normalized_counts("content_origin_counts"),
        }

    def _collect_claim_facts(
        self,
        claim_type: str,
        user_id: str,
        support_claim: Dict[str, Any],
    ) -> List[str]:
        facts: List[str] = []
        fact_rows = _safe_call(
            self.mediator,
            "get_claim_support_facts",
            claim_type=claim_type,
            user_id=user_id,
        ) or []
        for row in _coerce_list(fact_rows):
            facts.extend(_extract_text_candidates(row))

        for element in _coerce_list(support_claim.get("elements") if isinstance(support_claim, dict) else []):
            if not isinstance(element, dict):
                continue
            element_text = str(element.get("element_text") or element.get("claim_element") or "").strip()
            if element_text:
                facts.append(f"Element supported: {element_text}")
            for link in _coerce_list(element.get("links")):
                if isinstance(link, dict):
                    facts.extend(_extract_text_candidates(link))

        normalized = []
        for item in _unique_preserving_order(facts):
            text = re.sub(r"\s+", " ", item).strip()
            if len(text) < 10 or self._is_generic_claim_support_text(text):
                continue
            normalized.append(text)
            if len(normalized) >= 8:
                break
        return normalized or [f"The intake record describes facts supporting the {claim_type} claim."]

    def _build_claim_legal_standards(
        self,
        *,
        claim_type: str,
        requirements: Dict[str, Any],
        statutes: List[Dict[str, Any]],
    ) -> List[str]:
        standards = _unique_preserving_order(_extract_text_candidates(requirements.get(claim_type, [])))
        related_statutes = self._select_statutes_for_claim(claim_type, statutes)
        for statute in related_statutes:
            citation = statute.get("citation")
            title = statute.get("title")
            relevance = statute.get("relevance")
            parts = [part for part in [citation, title, relevance] if part]
            if parts:
                standards.append(" - ".join(parts))
        return standards or [f"Plaintiff must prove the elements of {claim_type} under the applicable law."]

    def _build_legal_standards_summary(
        self,
        *,
        statutes: List[Dict[str, Any]],
        requirements: Dict[str, Any],
    ) -> List[str]:
        summary = []
        for claim_type, elements in requirements.items():
            summary.append(
                f"{claim_type.title()}: {', '.join(_unique_preserving_order(_extract_text_candidates(elements))[:4])}"
            )
        for statute in statutes[:5]:
            if isinstance(statute, dict):
                parts = [statute.get("citation"), statute.get("title"), statute.get("relevance")]
                text = " - ".join([part for part in parts if part])
                if text:
                    summary.append(text)
        return _unique_preserving_order(summary)

    def _safe_mediator_dict(self, method_name: str, **kwargs: Any) -> Dict[str, Any]:
        method = getattr(self.mediator, method_name, None)
        if not callable(method):
            return {}
        try:
            result = method(**kwargs)
        except Exception:
            return {}
        return result if isinstance(result, dict) else {}

    def _build_drafting_readiness(
        self,
        *,
        user_id: str,
        draft: Dict[str, Any],
    ) -> Dict[str, Any]:
        support_summary = self._safe_mediator_dict("summarize_claim_support", user_id=user_id)
        gap_summary = self._safe_mediator_dict("get_claim_support_gaps", user_id=user_id)
        validation_summary = self._safe_mediator_dict("get_claim_support_validation", user_id=user_id)

        support_claims = support_summary.get("claims", {}) if isinstance(support_summary.get("claims"), dict) else {}
        gap_claims = gap_summary.get("claims", {}) if isinstance(gap_summary.get("claims"), dict) else {}
        validation_claims = validation_summary.get("claims", {}) if isinstance(validation_summary.get("claims"), dict) else {}

        claim_types = _unique_preserving_order(
            _extract_text_candidates((draft.get("source_context") or {}).get("claim_types"))
            + list(support_claims.keys())
            + list(validation_claims.keys())
            + [
                str(claim.get("claim_type") or "").strip()
                for claim in _coerce_list(draft.get("claims_for_relief"))
                if isinstance(claim, dict)
            ]
        )

        claim_readiness: List[Dict[str, Any]] = []
        aggregate_warning_count = 0
        overall_status = "ready"

        for claim_type in claim_types:
            support_claim = support_claims.get(claim_type, {}) if isinstance(support_claims.get(claim_type), dict) else {}
            gap_claim = gap_claims.get(claim_type, {}) if isinstance(gap_claims.get(claim_type), dict) else {}
            validation_claim = validation_claims.get(claim_type, {}) if isinstance(validation_claims.get(claim_type), dict) else {}
            overview_payload = self._safe_mediator_dict(
                "get_claim_overview",
                claim_type=claim_type,
                user_id=user_id,
                required_support_kinds=["evidence", "authority"],
            )
            overview_claim = overview_payload.get("claims", {}).get(claim_type, {}) if isinstance(overview_payload.get("claims"), dict) else {}
            treatment_summary = support_claim.get("authority_treatment_summary", {}) if isinstance(support_claim.get("authority_treatment_summary"), dict) else {}
            rule_summary = support_claim.get("authority_rule_candidate_summary", {}) if isinstance(support_claim.get("authority_rule_candidate_summary"), dict) else {}
            source_context = self._extract_support_source_context_counts(support_claim)

            claim_status = "ready"
            warnings: List[Dict[str, Any]] = []

            validation_status = str(validation_claim.get("validation_status") or "")
            if validation_status == "contradicted":
                claim_status = _merge_status(claim_status, "blocked")
                warnings.append(
                    {
                        "code": "claim_contradicted",
                        "severity": "blocked",
                        "message": f"{claim_type.title()} has contradiction signals that should be resolved before filing.",
                    }
                )
            elif validation_status in {"missing", "incomplete"}:
                claim_status = _merge_status(claim_status, "warning")

            if int(validation_claim.get("proof_gap_count", 0) or 0) > 0:
                claim_status = _merge_status(claim_status, "warning")
                warnings.append(
                    {
                        "code": "proof_gaps_present",
                        "severity": "warning",
                        "message": f"{claim_type.title()} still has proof or failed-premise gaps.",
                    }
                )

            if int(treatment_summary.get("adverse_authority_link_count", 0) or 0) > 0:
                claim_status = _merge_status(claim_status, "warning")
                warnings.append(
                    {
                        "code": "adverse_authority_present",
                        "severity": "warning",
                        "message": f"{claim_type.title()} includes adverse or limiting authority that should be reviewed before relying on it in the draft.",
                    }
                )

            uncertain_authority_count = int(treatment_summary.get("uncertain_authority_link_count", 0) or 0)
            uncertain_treatment_types = sorted(
                str(name)
                for name in (treatment_summary.get("treatment_type_counts", {}) or {}).keys()
                if str(name) in {"questioned", "limits", "superseded", "good_law_unconfirmed"}
            )
            if uncertain_authority_count > 0 or uncertain_treatment_types:
                claim_status = _merge_status(claim_status, "warning")
                warnings.append(
                    {
                        "code": "authority_reliability_uncertain",
                        "severity": "warning",
                        "message": f"{claim_type.title()} has authority support with unresolved treatment or good-law uncertainty.",
                    }
                )

            unresolved_elements = int(gap_claim.get("unresolved_count", 0) or 0)
            if unresolved_elements == 0:
                unresolved_elements = len(_coerce_list(overview_claim.get("missing"))) + len(_coerce_list(overview_claim.get("partially_supported")))
            if unresolved_elements > 0:
                claim_status = _merge_status(claim_status, "warning")
                warnings.append(
                    {
                        "code": "unresolved_elements",
                        "severity": "warning",
                        "message": f"{claim_type.title()} still has {unresolved_elements} unresolved claim element(s).",
                    }
                )

            claim_entry = {
                "claim_type": claim_type,
                "status": claim_status,
                "validation_status": validation_status or ("supported" if claim_status == "ready" else "incomplete"),
                "covered_elements": int(support_claim.get("covered_elements", 0) or 0),
                "total_elements": int(support_claim.get("total_elements", 0) or 0),
                "unresolved_element_count": unresolved_elements,
                "proof_gap_count": int(validation_claim.get("proof_gap_count", 0) or 0),
                "contradiction_candidate_count": int(validation_claim.get("contradiction_candidate_count", 0) or 0),
                "support_by_kind": support_claim.get("support_by_kind", {}),
                "support_by_source": source_context["support_by_source"],
                "source_family_counts": source_context["source_family_counts"],
                "record_scope_counts": source_context["record_scope_counts"],
                "artifact_family_counts": source_context["artifact_family_counts"],
                "corpus_family_counts": source_context["corpus_family_counts"],
                "content_origin_counts": source_context["content_origin_counts"],
                "authority_treatment_summary": treatment_summary,
                "authority_rule_candidate_summary": rule_summary,
                "warnings": warnings,
            }
            aggregate_warning_count += len(warnings)
            overall_status = _merge_status(overall_status, claim_status)
            claim_readiness.append(claim_entry)

        claims_section_status = "ready"
        for claim_entry in claim_readiness:
            claims_section_status = _merge_status(claims_section_status, claim_entry.get("status", "ready"))

        total_fact_count = sum(int(claim.get("total_facts", 0) or 0) for claim in support_claims.values() if isinstance(claim, dict))
        if total_fact_count <= 0:
            total_fact_count = sum(
                len(self._normalize_text_lines(claim.get("supporting_facts", [])))
                for claim in _coerce_list(draft.get("claims_for_relief"))
                if isinstance(claim, dict)
            )
        summary_fact_count = len(self._normalize_text_lines(draft.get("summary_of_facts", [])))
        exhibits = _coerce_list(draft.get("exhibits"))
        relief_items = self._normalize_text_lines(draft.get("requested_relief", []))

        sections: Dict[str, Dict[str, Any]] = {}

        facts_status = "ready" if total_fact_count > 0 and summary_fact_count > 0 else "warning"
        facts_warnings: List[Dict[str, Any]] = []
        if facts_status != "ready":
            facts_warnings.append(
                {
                    "code": "fact_support_thin",
                    "severity": "warning",
                    "message": "The factual allegations section has limited fact-backed support and should be reviewed before filing.",
                }
            )
        sections["summary_of_facts"] = {
            "title": "Summary of Facts",
            "status": facts_status,
            "metrics": {
                "summary_fact_count": summary_fact_count,
                "support_fact_count": total_fact_count,
            },
            "warnings": facts_warnings,
        }

        jurisdiction_status = "ready" if draft.get("jurisdiction_statement") and draft.get("venue_statement") else "warning"
        jurisdiction_warnings: List[Dict[str, Any]] = []
        procedural_rule_count = sum(
            int((entry.get("authority_rule_candidate_summary", {}).get("rule_type_counts", {}) or {}).get("procedural_prerequisite", 0) or 0)
            for entry in claim_readiness
            if isinstance(entry, dict)
        )
        if jurisdiction_status != "ready":
            jurisdiction_warnings.append(
                {
                    "code": "jurisdiction_or_venue_incomplete",
                    "severity": "warning",
                    "message": "Jurisdiction or venue language is incomplete and should be confirmed before export.",
                }
            )
        if procedural_rule_count > 0:
            jurisdiction_status = _merge_status(jurisdiction_status, "warning")
            jurisdiction_warnings.append(
                {
                    "code": "procedural_prerequisites_identified",
                    "severity": "warning",
                    "message": "Authority-derived procedural prerequisites were identified and should be checked against the current facts before filing.",
                }
            )
        sections["jurisdiction_and_venue"] = {
            "title": "Jurisdiction and Venue",
            "status": jurisdiction_status,
            "metrics": {
                "procedural_rule_count": procedural_rule_count,
            },
            "warnings": jurisdiction_warnings,
        }

        sections["claims_for_relief"] = {
            "title": "Claims for Relief",
            "status": claims_section_status,
            "metrics": {
                "claim_count": len(claim_readiness),
                "blocked_claim_count": len([entry for entry in claim_readiness if entry.get("status") == "blocked"]),
                "warning_claim_count": len([entry for entry in claim_readiness if entry.get("status") == "warning"]),
            },
            "warnings": [
                warning
                for entry in claim_readiness
                for warning in entry.get("warnings", [])
                if isinstance(warning, dict)
            ],
        }

        exhibits_status = "ready" if exhibits else "warning"
        exhibits_warnings: List[Dict[str, Any]] = []
        if not exhibits:
            exhibits_warnings.append(
                {
                    "code": "no_exhibits",
                    "severity": "warning",
                    "message": "No exhibits are currently attached to the draft package.",
                }
            )
        sections["exhibits"] = {
            "title": "Exhibits",
            "status": exhibits_status,
            "metrics": {
                "exhibit_count": len(exhibits),
            },
            "warnings": exhibits_warnings,
        }

        relief_status = "ready" if relief_items else "warning"
        relief_warnings: List[Dict[str, Any]] = []
        if not relief_items:
            relief_warnings.append(
                {
                    "code": "requested_relief_missing",
                    "severity": "warning",
                    "message": "Requested relief should be confirmed before filing.",
                }
            )
        sections["requested_relief"] = {
            "title": "Requested Relief",
            "status": relief_status,
            "metrics": {
                "requested_relief_count": len(relief_items),
            },
            "warnings": relief_warnings,
        }

        for section in sections.values():
            overall_status = _merge_status(overall_status, str(section.get("status") or "ready"))
            aggregate_warning_count += len(section.get("warnings", []) or [])

        return {
            "status": overall_status,
            "claim_types": claim_types,
            "warning_count": aggregate_warning_count,
            "claims": claim_readiness,
            "sections": sections,
        }

    def _build_filing_checklist(self, drafting_readiness: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(drafting_readiness, dict):
            return []

        checklist: List[Dict[str, Any]] = []
        sections = drafting_readiness.get("sections") if isinstance(drafting_readiness.get("sections"), dict) else {}
        claims = drafting_readiness.get("claims") if isinstance(drafting_readiness.get("claims"), list) else []

        for section_key, section in sections.items():
            if not isinstance(section, dict):
                continue
            status = str(section.get("status") or "ready")
            title = str(section.get("title") or section_key or "Section").strip()
            warnings = section.get("warnings") if isinstance(section.get("warnings"), list) else []
            metrics = section.get("metrics") if isinstance(section.get("metrics"), dict) else {}
            if status == "ready":
                checklist.append(
                    {
                        "scope": "section",
                        "key": str(section_key),
                        "title": title,
                        "status": "ready",
                        "summary": f"{title} is ready for filing review.",
                        "detail": self._summarize_metrics(metrics),
                    }
                )
                continue
            primary_warning = warnings[0] if warnings and isinstance(warnings[0], dict) else {}
            checklist.append(
                {
                    "scope": "section",
                    "key": str(section_key),
                    "title": title,
                    "status": status,
                    "summary": str(primary_warning.get("message") or f"Review {title} before filing."),
                    "detail": self._summarize_metrics(metrics),
                }
            )

        for claim in claims:
            if not isinstance(claim, dict):
                continue
            status = str(claim.get("status") or "ready")
            claim_type = str(claim.get("claim_type") or "claim").strip()
            warnings = claim.get("warnings") if isinstance(claim.get("warnings"), list) else []
            metrics = {
                "covered_elements": claim.get("covered_elements"),
                "total_elements": claim.get("total_elements"),
                "unresolved_element_count": claim.get("unresolved_element_count"),
                "proof_gap_count": claim.get("proof_gap_count"),
            }
            if status == "ready":
                checklist.append(
                    {
                        "scope": "claim",
                        "key": claim_type,
                        "title": claim_type.title(),
                        "status": "ready",
                        "summary": f"{claim_type.title()} is ready for filing review.",
                        "detail": self._summarize_metrics(metrics),
                    }
                )
                continue
            primary_warning = warnings[0] if warnings and isinstance(warnings[0], dict) else {}
            checklist.append(
                {
                    "scope": "claim",
                    "key": claim_type,
                    "title": claim_type.title(),
                    "status": status,
                    "summary": str(primary_warning.get("message") or f"Review {claim_type.title()} before filing."),
                    "detail": self._summarize_metrics(metrics),
                }
            )

        checklist.sort(key=lambda item: {"blocked": 0, "warning": 1, "ready": 2}.get(str(item.get("status")), 3))
        return checklist

    def _annotate_filing_checklist_review_links(
        self,
        *,
        filing_checklist: List[Dict[str, Any]],
        drafting_readiness: Dict[str, Any],
        user_id: Optional[str],
    ) -> None:
        if not filing_checklist or not isinstance(drafting_readiness, dict):
            return

        claim_map: Dict[str, Dict[str, Any]] = {}
        for claim in _coerce_list(drafting_readiness.get("claims")):
            if not isinstance(claim, dict):
                continue
            claim_type = str(claim.get("claim_type") or "").strip()
            if not claim_type:
                continue
            claim_map[claim_type] = {
                "review_url": self._build_review_url(user_id=user_id, claim_type=claim_type),
                "review_context": {
                    "user_id": user_id,
                    "claim_type": claim_type,
                },
            }

        section_map: Dict[str, Dict[str, Any]] = {}
        for section_key, section in (drafting_readiness.get("sections") or {}).items():
            if not isinstance(section, dict):
                continue
            resolved_key = str(section_key or "").strip()
            if not resolved_key:
                continue
            section_map[resolved_key] = {
                "review_url": self._build_review_url(user_id=user_id, section=resolved_key),
                "review_context": {
                    "user_id": user_id,
                    "section": resolved_key,
                    "claim_type": None,
                },
            }

        dashboard_url = self._build_review_url(user_id=user_id)
        for item in filing_checklist:
            if not isinstance(item, dict):
                continue
            scope = str(item.get("scope") or "").strip().lower()
            key = str(item.get("key") or "").strip()
            target = None
            if scope == "claim":
                target = claim_map.get(key)
            elif scope == "section":
                target = section_map.get(key)
            if target:
                item["review_url"] = target["review_url"]
                item["review_context"] = target["review_context"]
            else:
                item["review_url"] = dashboard_url
                item["review_context"] = {"user_id": user_id}

    def _build_review_url(
        self,
        *,
        user_id: Optional[str] = None,
        claim_type: Optional[str] = None,
        section: Optional[str] = None,
    ) -> str:
        params = {}
        if user_id:
            params["user_id"] = user_id
        if claim_type:
            params["claim_type"] = claim_type
        if section:
            params["section"] = section
        query = urlencode(params)
        return f"/claim-support-review?{query}" if query else "/claim-support-review"

    def _summarize_metrics(self, metrics: Dict[str, Any]) -> str:
        parts = []
        for key, value in metrics.items():
            if value in (None, "", []):
                continue
            parts.append(f"{key.replace('_', ' ')}={value}")
            if len(parts) >= 3:
                break
        return "; ".join(parts)

    def _select_statutes_for_claim(
        self,
        claim_type: str,
        statutes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        tokens = {token for token in re.split(r"\W+", claim_type.lower()) if token}
        scored = []
        for statute in statutes:
            if not isinstance(statute, dict):
                continue
            haystack = " ".join(
                str(statute.get(field) or "") for field in ("citation", "title", "relevance")
            ).lower()
            score = sum(1 for token in tokens if token in haystack)
            scored.append((score, statute))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [statute for score, statute in scored if score > 0][:3]
        return selected or [statute for _, statute in scored[:3]]

    def _extract_overview_elements(self, elements: Any) -> List[str]:
        names = []
        for element in _coerce_list(elements):
            if isinstance(element, dict):
                names.extend(_extract_text_candidates(element.get("element_text") or element.get("claim_element") or element))
            else:
                names.extend(_extract_text_candidates(element))
        return _unique_preserving_order(names)

    def _extract_requested_relief_from_facts(self, facts: List[str]) -> List[str]:
        remedies = []
        for fact in facts:
            lower = fact.lower()
            if "reinstat" in lower:
                remedies.append("Reinstatement or front pay in lieu of reinstatement.")
            if "back pay" in lower or "lost wages" in lower:
                remedies.append("Back pay, front pay, and lost benefits.")
            if "injunct" in lower:
                remedies.append("Injunctive relief to prevent continuing violations.")
        return remedies

    def _collect_exhibits(
        self,
        *,
        user_id: str,
        claim_types: List[str],
        support_claims: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        exhibits: List[Dict[str, Any]] = []
        evidence_records = _safe_call(self.mediator, "get_user_evidence", user_id=user_id) or []
        for record in _coerce_list(evidence_records):
            if not isinstance(record, dict):
                continue
            claim_type = record.get("claim_type")
            if claim_type and claim_types and claim_type not in claim_types:
                continue
            exhibits.append(
                {
                    "label": f"Exhibit {chr(65 + len(exhibits))}",
                    "title": record.get("description") or record.get("type") or record.get("cid") or "Supporting exhibit",
                    "claim_type": claim_type,
                    "kind": "evidence",
                    "link": self._build_exhibit_link(record),
                    "source_ref": record.get("cid") or record.get("source_url") or "",
                    "summary": record.get("parsed_text_preview") or record.get("description") or "",
                }
            )

        for claim_type, claim_summary in (support_claims or {}).items():
            if not isinstance(claim_summary, dict):
                continue
            for element in _coerce_list(claim_summary.get("elements")):
                if not isinstance(element, dict):
                    continue
                for link in _coerce_list(element.get("links")):
                    if not isinstance(link, dict):
                        continue
                    support_kind = str(link.get("support_kind") or "").strip().lower()
                    if support_kind != "authority":
                        continue
                    link_url = self._build_exhibit_link(link)
                    title = link.get("support_label") or link.get("title") or link.get("citation") or element.get("element_text")
                    source_ref = link.get("support_ref") or link.get("citation") or link_url or ""
                    if not title and not source_ref:
                        continue
                    exhibits.append(
                        {
                            "label": f"Exhibit {chr(65 + len(exhibits))}",
                            "title": title or "Authority support",
                            "claim_type": claim_type,
                            "kind": "authority",
                            "link": link_url,
                            "source_ref": source_ref,
                            "summary": link.get("relevance") or link.get("description") or "",
                        }
                    )

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for exhibit in exhibits:
            key = (exhibit.get("kind"), exhibit.get("title"), exhibit.get("source_ref"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(exhibit)
            if len(deduped) >= 20:
                break
        return deduped

    def _build_exhibit_link(self, record: Dict[str, Any]) -> str:
        source_url = str(record.get("source_url") or "").strip()
        if source_url:
            return source_url
        support_ref = str(record.get("support_ref") or record.get("cid") or "").strip()
        if support_ref.startswith("http://") or support_ref.startswith("https://"):
            return support_ref
        if support_ref:
            return f"https://ipfs.io/ipfs/{support_ref}"
        return ""

    def _annotate_lines_with_exhibits(
        self,
        lines: List[str],
        exhibits: List[Dict[str, Any]],
    ) -> List[str]:
        if not lines or not exhibits:
            return lines
        annotated: List[str] = []
        for index, line in enumerate(lines):
            exhibit = self._select_exhibit_for_line(line, exhibits)
            if exhibit is None and index == 0:
                exhibit = exhibits[0]
            annotated.append(self._append_exhibit_citation(line, exhibit))
        return annotated

    def _select_exhibit_for_line(
        self,
        line: str,
        exhibits: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        line_tokens = self._text_tokens(line)
        if not line_tokens:
            return exhibits[0] if exhibits else None

        best_match: Optional[Dict[str, Any]] = None
        best_score = 0
        for exhibit in exhibits:
            if not isinstance(exhibit, dict):
                continue
            exhibit_tokens = self._text_tokens(
                " ".join(
                    str(exhibit.get(field) or "")
                    for field in ("title", "summary", "source_ref", "claim_type")
                )
            )
            score = len(line_tokens & exhibit_tokens)
            if score > best_score:
                best_score = score
                best_match = exhibit

        return best_match if best_score > 0 else None

    def _append_exhibit_citation(
        self,
        line: str,
        exhibit: Optional[Dict[str, Any]],
    ) -> str:
        text = str(line or "").strip()
        if not text or exhibit is None:
            return text
        label = str(exhibit.get("label") or "").strip()
        if not label:
            return text
        if label.lower() in text.lower():
            return text
        punctuation = "." if text.endswith(".") else ""
        base = text[:-1] if punctuation else text
        return f"{base} (See {label}){punctuation}"

    def _text_tokens(self, value: str) -> set[str]:
        return {
            token
            for token in re.split(r"\W+", str(value or "").lower())
            if len(token) >= 4
        }

    def _render_docx(self, draft: Dict[str, Any], path: Path) -> None:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.opc.constants import RELATIONSHIP_TYPE
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt, RGBColor

        document = Document()
        section = document.sections[0]
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

        normal_style = document.styles["Normal"]
        normal_style.font.name = "Times New Roman"
        normal_style.font.size = Pt(12)

        heading = document.add_paragraph()
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = heading.add_run(draft.get("court_header", ""))
        run.bold = True
        run.font.size = Pt(12)

        case_caption = draft.get("case_caption", {}) if isinstance(draft.get("case_caption"), dict) else {}
        caption_party_lines = case_caption.get("caption_party_lines") if isinstance(case_caption.get("caption_party_lines"), list) else self._build_caption_party_lines(case_caption)
        caption = document.add_paragraph()
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption.add_run("\n\n".join(caption_party_lines) + "\n")

        case_no = document.add_paragraph()
        case_no.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        case_no.add_run(
            f"{case_caption.get('case_number_label', 'Civil Action No.')} {case_caption.get('case_number', '________________')}"
        ).bold = True
        if case_caption.get("lead_case_number"):
            lead_case = document.add_paragraph()
            lead_case.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            lead_case.add_run(
                f"{case_caption.get('lead_case_number_label', 'Lead Case No.')} {case_caption['lead_case_number']}"
            ).bold = True
        if case_caption.get("related_case_number"):
            related_case = document.add_paragraph()
            related_case.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            related_case.add_run(
                f"{case_caption.get('related_case_number_label', 'Related Case No.')} {case_caption['related_case_number']}"
            ).bold = True
        if case_caption.get("assigned_judge"):
            judge = document.add_paragraph()
            judge.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            judge.add_run(
                f"{case_caption.get('assigned_judge_label', 'Assigned Judge')}: {case_caption['assigned_judge']}"
            ).bold = True
        if case_caption.get("courtroom"):
            courtroom = document.add_paragraph()
            courtroom.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            courtroom.add_run(
                f"{case_caption.get('courtroom_label', 'Courtroom')}: {case_caption['courtroom']}"
            ).bold = True

        title = document.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title.add_run(draft.get("case_caption", {}).get("document_title", "COMPLAINT"))
        title_run.bold = True
        title_run.font.size = Pt(14)
        if draft.get("case_caption", {}).get("jury_demand_notice"):
            jury_notice = document.add_paragraph()
            jury_notice.alignment = WD_ALIGN_PARAGRAPH.CENTER
            jury_notice_run = jury_notice.add_run(draft["case_caption"]["jury_demand_notice"])
            jury_notice_run.bold = True
            jury_notice_run.font.size = Pt(12)

        self._add_docx_section(document, "Nature of the Action", draft.get("nature_of_action", []))
        self._add_docx_section(
            document,
            "Parties",
            [
                f"Plaintiff: {', '.join(draft.get('parties', {}).get('plaintiffs', []))}.",
                f"Defendant: {', '.join(draft.get('parties', {}).get('defendants', []))}.",
            ],
        )
        self._add_docx_section(
            document,
            "Jurisdiction and Venue",
            [draft.get("jurisdiction_statement"), draft.get("venue_statement")],
        )
        self._add_docx_numbered_facts(document, "Summary of Facts", draft.get("summary_of_facts", []))
        self._add_docx_numbered_facts(
            document,
            "Factual Allegations",
            draft.get("factual_allegations") or draft.get("summary_of_facts", []),
            groups=draft.get("factual_allegation_groups") if isinstance(draft.get("factual_allegation_groups"), list) else None,
        )

        legal_standards = draft.get("legal_standards", [])
        if legal_standards:
            self._add_docx_section(document, "Applicable Legal Standards", legal_standards)

        document.add_heading("Claims for Relief", level=1)
        for index, claim in enumerate(draft.get("claims_for_relief", []), start=1):
            document.add_heading(f"Count {_roman(index)} - {claim.get('count_title', 'Claim')}", level=2)
            self._add_docx_subsection(document, "Legal Standard", claim.get("legal_standards", []))
            incorporated_clause = self._format_incorporated_reference_clause(
                claim.get("allegation_references", []),
                claim.get("supporting_exhibits", []),
            )
            if incorporated_clause:
                self._add_docx_subsection(document, "Incorporated Support", [incorporated_clause])
            self._add_docx_subsection(document, "Claim-Specific Support", claim.get("supporting_facts", []))
            missing = claim.get("missing_elements", [])
            if missing:
                self._add_docx_subsection(document, "Open Support Gaps", missing)
            exhibits = claim.get("supporting_exhibits", [])
            if exhibits:
                document.add_paragraph("Supporting Exhibits:")
                for exhibit in exhibits:
                    paragraph = document.add_paragraph(style="List Bullet")
                    paragraph.add_run(f"{exhibit.get('label')}. {exhibit.get('title')}")
                    if exhibit.get("link"):
                        paragraph.add_run(" ")
                        self._append_docx_hyperlink(
                            paragraph,
                            exhibit["link"],
                            "Open exhibit",
                            RELATIONSHIP_TYPE,
                            OxmlElement,
                            qn,
                            RGBColor,
                        )

        self._add_docx_subsection(document, "Requested Relief", draft.get("requested_relief", []), numbered=True)
        jury_demand = draft.get("jury_demand", {}) if isinstance(draft.get("jury_demand"), dict) else {}
        if jury_demand:
            self._add_docx_section(document, jury_demand.get("title") or "Jury Demand", [jury_demand.get("text")])

        document.add_heading("Supporting Exhibits", level=1)
        for exhibit in draft.get("exhibits", []):
            paragraph = document.add_paragraph(style="List Bullet")
            paragraph.add_run(f"{exhibit.get('label')}. {exhibit.get('title')}")
            if exhibit.get("summary"):
                paragraph.add_run(f" - {exhibit.get('summary')}")
            if exhibit.get("link"):
                paragraph.add_run(" ")
                self._append_docx_hyperlink(
                    paragraph,
                    exhibit["link"],
                    "Open exhibit",
                    RELATIONSHIP_TYPE,
                    OxmlElement,
                    qn,
                    RGBColor,
                )

        affidavit = draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else {}
        if affidavit:
            self._add_docx_section(
                document,
                affidavit.get("title") or "Affidavit in Support of Complaint",
                list(_coerce_list(affidavit.get("venue_lines")))
                + [affidavit.get("intro"), affidavit.get("knowledge_graph_note")],
            )
            self._add_docx_numbered_facts(document, "Affiant States as Follows", affidavit.get("facts", []))
            supporting_exhibits = affidavit.get("supporting_exhibits") if isinstance(affidavit.get("supporting_exhibits"), list) else []
            if supporting_exhibits:
                document.add_heading("Affidavit Supporting Exhibits", level=2)
                for exhibit in supporting_exhibits:
                    if not isinstance(exhibit, dict):
                        continue
                    paragraph = document.add_paragraph(style="List Bullet")
                    paragraph.add_run(f"{exhibit.get('label')}. {exhibit.get('title')}")
                    if exhibit.get("link"):
                        paragraph.add_run(f" ({exhibit['link']})")
            self._add_docx_section(
                document,
                "Affidavit Execution",
                [affidavit.get("dated"), affidavit.get("signature_line"), affidavit.get("jurat"), *_coerce_list(affidavit.get("notary_block"))],
            )

        verification = draft.get("verification", {}) if isinstance(draft.get("verification"), dict) else {}
        if verification:
            self._add_docx_section(
                document,
                verification.get("title") or "Verification",
                [verification.get("text"), verification.get("dated"), verification.get("signature_line")],
            )
        certificate_of_service = draft.get("certificate_of_service", {}) if isinstance(draft.get("certificate_of_service"), dict) else {}
        if certificate_of_service:
            self._add_docx_section(
                document,
                certificate_of_service.get("title") or "Certificate of Service",
                [certificate_of_service.get("text")]
                + _coerce_list(certificate_of_service.get("detail_lines"))
                + [certificate_of_service.get("dated"), certificate_of_service.get("signature_line")],
            )
        signature_block = draft.get("signature_block", {}) if isinstance(draft.get("signature_block"), dict) else {}
        self._add_docx_section(
            document,
            "Signature Block",
            self._build_signature_section_lines(signature_block, self._resolve_draft_forum_type(draft)),
        )

        document.save(path)

    def _add_docx_section(self, document: Any, title: str, paragraphs: List[str]) -> None:
        document.add_heading(title, level=1)
        for paragraph in paragraphs:
            if paragraph:
                document.add_paragraph(str(paragraph))

    def _add_docx_numbered_facts(self, document: Any, title: str, facts: List[str], groups: Optional[List[Dict[str, Any]]] = None) -> None:
        document.add_heading(title, level=1)
        if groups:
            for group in groups:
                if not isinstance(group, dict):
                    continue
                heading = str(group.get("title") or "").strip()
                paragraphs = group.get("paragraphs") if isinstance(group.get("paragraphs"), list) else []
                if heading:
                    document.add_paragraph(heading)
                for paragraph in paragraphs:
                    if not isinstance(paragraph, dict):
                        continue
                    number = paragraph.get("number")
                    text = str(paragraph.get("text") or "").strip()
                    if text:
                        document.add_paragraph(f"{number}. {text}" if number else text)
            return
        for index, fact in enumerate(facts, start=1):
            document.add_paragraph(f"{index}. {fact}")

    def _add_docx_subsection(
        self,
        document: Any,
        title: str,
        lines: List[str],
        numbered: bool = False,
    ) -> None:
        document.add_paragraph(title)
        for index, line in enumerate(lines, start=1):
            prefix = f"{index}. " if numbered else ""
            document.add_paragraph(f"{prefix}{line}", style="List Bullet")

    def _append_docx_hyperlink(
        self,
        paragraph: Any,
        url: str,
        text: str,
        relationship_type: Any,
        oxml_element: Any,
        qn: Any,
        rgb_color: Any,
    ) -> None:
        part = paragraph.part
        rel_id = part.relate_to(url, relationship_type.HYPERLINK, is_external=True)
        hyperlink = oxml_element("w:hyperlink")
        hyperlink.set(qn("r:id"), rel_id)
        run = oxml_element("w:r")
        properties = oxml_element("w:rPr")
        color = oxml_element("w:color")
        color.set(qn("w:val"), "0563C1")
        underline = oxml_element("w:u")
        underline.set(qn("w:val"), "single")
        properties.append(color)
        properties.append(underline)
        run.append(properties)
        text_element = oxml_element("w:t")
        text_element.text = text
        run.append(text_element)
        hyperlink.append(run)
        paragraph._p.append(hyperlink)

    def _render_pdf(self, draft: Dict[str, Any], path: Path) -> None:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="CourtHeader",
                parent=styles["Normal"],
                fontName="Times-Bold",
                fontSize=12,
                leading=14,
                alignment=TA_CENTER,
                spaceAfter=12,
            )
        )
        styles.add(
            ParagraphStyle(
                name="Caption",
                parent=styles["Normal"],
                fontName="Times-Roman",
                fontSize=12,
                leading=14,
                alignment=TA_CENTER,
                spaceAfter=12,
            )
        )
        styles.add(
            ParagraphStyle(
                name="SectionHeading",
                parent=styles["Heading1"],
                fontName="Times-Bold",
                fontSize=13,
                leading=15,
                textColor=colors.black,
                alignment=TA_LEFT,
                spaceBefore=10,
                spaceAfter=6,
            )
        )
        styles.add(
            ParagraphStyle(
                name="RightAligned",
                parent=styles["Normal"],
                fontName="Times-Bold",
                fontSize=12,
                leading=14,
                alignment=TA_RIGHT,
                spaceAfter=8,
            )
        )

        doc = SimpleDocTemplate(
            str(path),
            pagesize=LETTER,
            topMargin=inch,
            bottomMargin=inch,
            leftMargin=inch,
            rightMargin=inch,
        )
        case_caption = draft.get("case_caption", {}) if isinstance(draft.get("case_caption"), dict) else {}
        caption_party_lines = case_caption.get("caption_party_lines") if isinstance(case_caption.get("caption_party_lines"), list) else self._build_caption_party_lines(case_caption)
        story = [
            Paragraph(escape(draft.get("court_header", "")), styles["CourtHeader"]),
            Paragraph(
                "<br/><br/>".join(escape(line).replace("\n", "<br/>") for line in caption_party_lines),
                styles["Caption"],
            ),
            Paragraph(
                escape(
                    f"{case_caption.get('case_number_label', 'Civil Action No.')} {case_caption.get('case_number', '________________')}"
                    + (
                        f"\n{case_caption.get('lead_case_number_label', 'Lead Case No.')} {case_caption.get('lead_case_number')}"
                        if case_caption.get('lead_case_number')
                        else ""
                    )
                    + (
                        f"\n{case_caption.get('related_case_number_label', 'Related Case No.')} {case_caption.get('related_case_number')}"
                        if case_caption.get('related_case_number')
                        else ""
                    )
                    + (
                        f"\n{case_caption.get('assigned_judge_label', 'Assigned Judge')}: {case_caption.get('assigned_judge')}"
                        if case_caption.get('assigned_judge')
                        else ""
                    )
                    + (
                        f"\n{case_caption.get('courtroom_label', 'Courtroom')}: {case_caption.get('courtroom')}"
                        if case_caption.get('courtroom')
                        else ""
                    )
                ),
                styles["RightAligned"],
            ),
            Paragraph(
                escape(draft.get("case_caption", {}).get("document_title", "COMPLAINT")),
                styles["CourtHeader"],
            ),
            *(
                [
                    Paragraph(
                        escape(draft["case_caption"]["jury_demand_notice"]),
                        styles["CourtHeader"],
                    )
                ]
                if draft.get("case_caption", {}).get("jury_demand_notice")
                else []
            ),
            Spacer(1, 8),
        ]

        self._append_pdf_section(story, styles, "Nature of the Action", draft.get("nature_of_action", []))
        self._append_pdf_section(
            story,
            styles,
            "Parties",
            [
                f"Plaintiff: {', '.join(draft.get('parties', {}).get('plaintiffs', []))}.",
                f"Defendant: {', '.join(draft.get('parties', {}).get('defendants', []))}.",
            ],
        )
        self._append_pdf_section(
            story,
            styles,
            "Jurisdiction and Venue",
            [draft.get("jurisdiction_statement"), draft.get("venue_statement")],
        )
        self._append_pdf_numbered_section(story, styles, "Summary of Facts", draft.get("summary_of_facts", []))
        self._append_pdf_numbered_section(
            story,
            styles,
            "Factual Allegations",
            draft.get("factual_allegations") or draft.get("summary_of_facts", []),
            groups=draft.get("factual_allegation_groups") if isinstance(draft.get("factual_allegation_groups"), list) else None,
        )
        self._append_pdf_section(
            story,
            styles,
            "Applicable Legal Standards",
            draft.get("legal_standards", []),
        )

        story.append(Paragraph("Claims for Relief", styles["SectionHeading"]))
        for index, claim in enumerate(draft.get("claims_for_relief", []), start=1):
            story.append(
                Paragraph(
                    escape(f"Count {_roman(index)} - {claim.get('count_title', 'Claim')}"),
                    styles["Heading2"],
                )
            )
            self._append_pdf_section(story, styles, "Legal Standard", claim.get("legal_standards", []), heading_style="Heading3")
            incorporated_clause = self._format_incorporated_reference_clause(
                claim.get("allegation_references", []),
                claim.get("supporting_exhibits", []),
            )
            if incorporated_clause:
                self._append_pdf_section(story, styles, "Incorporated Support", [incorporated_clause], heading_style="Heading3")
            self._append_pdf_section(story, styles, "Claim-Specific Support", claim.get("supporting_facts", []), heading_style="Heading3")
            if claim.get("missing_elements"):
                self._append_pdf_section(story, styles, "Open Support Gaps", claim.get("missing_elements", []), heading_style="Heading3")
            if claim.get("supporting_exhibits"):
                story.append(Paragraph("Supporting Exhibits", styles["Heading3"]))
                for exhibit in claim.get("supporting_exhibits", []):
                    story.append(
                        Paragraph(
                            self._pdf_exhibit_markup(exhibit),
                            styles["Normal"],
                        )
                    )

        self._append_pdf_numbered_section(story, styles, "Requested Relief", draft.get("requested_relief", []))
        jury_demand = draft.get("jury_demand", {}) if isinstance(draft.get("jury_demand"), dict) else {}
        if jury_demand:
            self._append_pdf_section(story, styles, jury_demand.get("title") or "Jury Demand", [jury_demand.get("text")])
        story.append(Paragraph("Supporting Exhibits", styles["SectionHeading"]))
        for exhibit in draft.get("exhibits", []):
            story.append(Paragraph(self._pdf_exhibit_markup(exhibit), styles["Normal"]))

        affidavit = draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else {}
        if affidavit:
            self._append_pdf_section(
                story,
                styles,
                affidavit.get("title") or "Affidavit in Support of Complaint",
                list(_coerce_list(affidavit.get("venue_lines"))) + [affidavit.get("intro"), affidavit.get("knowledge_graph_note")],
            )
            self._append_pdf_numbered_section(story, styles, "Affiant States as Follows", affidavit.get("facts", []))
            supporting_exhibits = affidavit.get("supporting_exhibits") if isinstance(affidavit.get("supporting_exhibits"), list) else []
            if supporting_exhibits:
                story.append(Paragraph("Affidavit Supporting Exhibits", styles["Heading3"]))
                for exhibit in supporting_exhibits:
                    if not isinstance(exhibit, dict):
                        continue
                    story.append(Paragraph(self._pdf_exhibit_markup(exhibit), styles["Normal"]))
            self._append_pdf_section(
                story,
                styles,
                "Affidavit Execution",
                [affidavit.get("dated"), affidavit.get("signature_line"), affidavit.get("jurat"), *_coerce_list(affidavit.get("notary_block"))],
            )

        verification = draft.get("verification", {}) if isinstance(draft.get("verification"), dict) else {}
        if verification:
            self._append_pdf_section(
                story,
                styles,
                verification.get("title") or "Verification",
                [verification.get("text"), verification.get("dated"), verification.get("signature_line")],
            )
        certificate_of_service = draft.get("certificate_of_service", {}) if isinstance(draft.get("certificate_of_service"), dict) else {}
        if certificate_of_service:
            self._append_pdf_section(
                story,
                styles,
                certificate_of_service.get("title") or "Certificate of Service",
                [certificate_of_service.get("text")]
                + _coerce_list(certificate_of_service.get("detail_lines"))
                + [certificate_of_service.get("dated"), certificate_of_service.get("signature_line")],
            )
        signature_block = draft.get("signature_block", {}) if isinstance(draft.get("signature_block"), dict) else {}
        self._append_pdf_section(
            story,
            styles,
            "Signature Block",
            self._build_signature_section_lines(signature_block, self._resolve_draft_forum_type(draft)),
        )

        doc.build(story)

    def _append_pdf_section(
        self,
        story: List[Any],
        styles: Any,
        title: str,
        paragraphs: List[str],
        heading_style: str = "SectionHeading",
    ) -> None:
        from reportlab.platypus import Paragraph

        if not paragraphs:
            return
        story.append(Paragraph(escape(title), styles[heading_style]))
        for paragraph in paragraphs:
            story.append(Paragraph(escape(str(paragraph)), styles["Normal"]))

    def _append_pdf_numbered_section(
        self,
        story: List[Any],
        styles: Any,
        title: str,
        paragraphs: List[str],
        heading_style: str = "SectionHeading",
        groups: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        from reportlab.platypus import Paragraph

        if not paragraphs and not groups:
            return
        story.append(Paragraph(escape(title), styles[heading_style]))
        if groups:
            for group in groups:
                if not isinstance(group, dict):
                    continue
                group_title = str(group.get("title") or "").strip()
                entries = group.get("paragraphs") if isinstance(group.get("paragraphs"), list) else []
                if group_title:
                    story.append(Paragraph(escape(group_title), styles["Heading3"]))
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    number = entry.get("number")
                    text = str(entry.get("text") or "").strip()
                    if text:
                        prefix = f"{number}. " if number else ""
                        story.append(Paragraph(escape(f"{prefix}{text}"), styles["Normal"]))
            return
        for index, paragraph in enumerate(paragraphs, start=1):
            story.append(Paragraph(escape(f"{index}. {paragraph}"), styles["Normal"]))

    def _pdf_exhibit_markup(self, exhibit: Dict[str, Any]) -> str:
        title = escape(f"{exhibit.get('label')}. {exhibit.get('title')}")
        summary = escape(str(exhibit.get("summary") or ""))
        link = str(exhibit.get("link") or "").strip()
        if link:
            link_markup = f'<link href="{escape(link)}">Open exhibit</link>'
            if summary:
                return f"{title} - {summary} ({link_markup})"
            return f"{title} ({link_markup})"
        if summary:
            return f"{title} - {summary}"
        return title