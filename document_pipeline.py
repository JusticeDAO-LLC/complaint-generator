from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional

from complaint_phases import ComplaintPhase


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "tmp" / "generated_documents"
DEFAULT_RELIEF = [
    "Compensatory damages in an amount to be proven at trial.",
    "Pre- and post-judgment interest as allowed by law.",
    "Reasonable attorney's fees and costs where authorized.",
    "Injunctive and declaratory relief sufficient to stop the unlawful conduct.",
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


class FormalComplaintDocumentBuilder:
    def __init__(self, mediator: Any):
        self.mediator = mediator

    def build_package(
        self,
        *,
        user_id: Optional[str] = None,
        court_name: str = "United States District Court",
        district: str = "",
        division: Optional[str] = None,
        court_header_override: Optional[str] = None,
        case_number: Optional[str] = None,
        title_override: Optional[str] = None,
        plaintiff_names: Optional[List[str]] = None,
        defendant_names: Optional[List[str]] = None,
        requested_relief: Optional[List[str]] = None,
        output_dir: Optional[str] = None,
        output_formats: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        resolved_user_id = self._resolve_user_id(user_id)
        formats = self._normalize_formats(output_formats)
        draft = self.build_draft(
            user_id=resolved_user_id,
            court_name=court_name,
            district=district,
            division=division,
            court_header_override=court_header_override,
            case_number=case_number,
            title_override=title_override,
            plaintiff_names=plaintiff_names,
            defendant_names=defendant_names,
            requested_relief=requested_relief,
        )
        artifacts = self.render_artifacts(
            draft,
            output_dir=output_dir,
            output_formats=formats,
        )
        return {
            "draft": draft,
            "artifacts": artifacts,
            "output_formats": formats,
            "generated_at": _utcnow().isoformat(),
        }

    def build_draft(
        self,
        *,
        user_id: str,
        court_name: str,
        district: str,
        division: Optional[str],
        court_header_override: Optional[str],
        case_number: Optional[str],
        title_override: Optional[str],
        plaintiff_names: Optional[List[str]],
        defendant_names: Optional[List[str]],
        requested_relief: Optional[List[str]],
    ) -> Dict[str, Any]:
        canonical_generate = getattr(self.mediator, "generate_formal_complaint", None)
        if callable(canonical_generate):
            try:
                result = canonical_generate(
                    user_id=user_id,
                    court_name=court_name,
                    district=district,
                    division=division,
                    court_header_override=court_header_override,
                    case_number=case_number,
                    title_override=title_override,
                    plaintiff_names=plaintiff_names,
                    defendant_names=defendant_names,
                    requested_relief=requested_relief,
                )
            except TypeError:
                result = None
            if isinstance(result, dict) and isinstance(result.get("formal_complaint"), dict):
                return self._adapt_formal_complaint_to_package_draft(result["formal_complaint"])

        return self._build_legacy_draft(
            user_id=user_id,
            court_name=court_name,
            district=district,
            division=division,
            court_header_override=court_header_override,
            case_number=case_number,
            title_override=title_override,
            plaintiff_names=plaintiff_names,
            defendant_names=defendant_names,
            requested_relief=requested_relief,
        )

    def _build_legacy_draft(
        self,
        *,
        user_id: str,
        court_name: str,
        district: str,
        division: Optional[str],
        court_header_override: Optional[str],
        case_number: Optional[str],
        title_override: Optional[str],
        plaintiff_names: Optional[List[str]],
        defendant_names: Optional[List[str]],
        requested_relief: Optional[List[str]],
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
        claims_for_relief = self._build_claims_for_relief(
            user_id=user_id,
            claim_types=claim_types,
            requirements=requirements,
            statutes=statutes,
            support_claims=support_claims,
            exhibits=exhibits,
        )
        relief_items = _unique_preserving_order(
            list(requested_relief or [])
            + list(generated_complaint.get("prayer_for_relief", []) or [])
            + self._extract_requested_relief_from_facts(facts)
            + DEFAULT_RELIEF
        )
        court_header = self._build_court_header(
            court_name=court_name,
            district=district,
            division=division,
            override=court_header_override,
        )
        nature_of_action = self._build_nature_of_action(
            claim_types=claim_types,
            classification=classification,
            statutes=statutes,
        )
        legal_standards = self._build_legal_standards_summary(statutes=statutes, requirements=requirements)

        return {
            "court_header": court_header,
            "case_caption": {
                "plaintiffs": plaintiffs,
                "defendants": defendants,
                "case_number": case_number or "________________",
                "document_title": "COMPLAINT",
            },
            "title": title,
            "nature_of_action": nature_of_action,
            "parties": {
                "plaintiffs": plaintiffs,
                "defendants": defendants,
            },
            "summary_of_facts": facts,
            "claims_for_relief": claims_for_relief,
            "legal_standards": legal_standards,
            "requested_relief": relief_items,
            "exhibits": exhibits,
            "source_context": {
                "user_id": user_id,
                "claim_types": claim_types,
                "jurisdiction": classification.get("jurisdiction", "unknown"),
                "generated_at": _utcnow().isoformat(),
            },
        }

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

        return {
            "court_header": formal_complaint.get("court_header", ""),
            "case_caption": {
                "plaintiffs": _coerce_list(formal_complaint.get("parties", {}).get("plaintiffs", [])) if isinstance(formal_complaint.get("parties"), dict) else [],
                "defendants": _coerce_list(formal_complaint.get("parties", {}).get("defendants", [])) if isinstance(formal_complaint.get("parties"), dict) else [],
                "case_number": caption.get("case_number") or formal_complaint.get("case_number") or "________________",
                "document_title": "COMPLAINT",
            },
            "title": formal_complaint.get("title") or caption.get("case_title") or "Complaint",
            "nature_of_action": _unique_preserving_order(_extract_text_candidates(nature_of_action)),
            "parties": formal_complaint.get("parties", {}),
            "summary_of_facts": _unique_preserving_order(_extract_text_candidates(formal_complaint.get("summary_of_facts") or formal_complaint.get("factual_allegations"))),
            "claims_for_relief": claims_for_relief,
            "legal_standards": _unique_preserving_order(legal_standards),
            "requested_relief": _unique_preserving_order(_extract_text_candidates(formal_complaint.get("requested_relief") or formal_complaint.get("prayer_for_relief"))),
            "exhibits": exhibits,
            "source_context": {
                "generated_at": formal_complaint.get("generated_at") or _utcnow().isoformat(),
                "jurisdiction": formal_complaint.get("jurisdiction", "unknown"),
            },
        }

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
            path = output_root / f"{file_stem}.{output_format}"
            if output_format == "docx":
                self._render_docx(draft, path)
            elif output_format == "pdf":
                self._render_pdf(draft, path)
            artifacts[output_format] = {
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
            if current in {"docx", "pdf"} and current not in normalized:
                normalized.append(current)
        return normalized or ["docx", "pdf"]

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
        division: Optional[str],
        override: Optional[str],
    ) -> str:
        if override:
            return override.strip().upper()
        court = str(court_name or "United States District Court").strip().upper()
        parts = [f"IN THE {court}"]
        if district:
            parts.append(f"FOR THE {str(district).strip().upper()}")
        if division:
            parts.append(str(division).strip().upper())
        return " ".join(parts)

    def _build_nature_of_action(
        self,
        *,
        claim_types: List[str],
        classification: Dict[str, Any],
        statutes: List[Dict[str, Any]],
    ) -> List[str]:
        claim_phrase = ", ".join(claim_types)
        legal_areas = ", ".join(_coerce_list(classification.get("legal_areas")))
        jurisdiction = str(classification.get("jurisdiction") or "the applicable court")
        statute_refs = _unique_preserving_order(
            [s.get("citation") for s in statutes if isinstance(s, dict) and s.get("citation")]
        )
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
        if complaint_text:
            facts.append(str(complaint_text))
        elif original_text:
            facts.append(str(original_text))

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
            claim_facts = self._collect_claim_facts(claim_type, user_id, support_claim)
            related_exhibits = [
                exhibit for exhibit in exhibits if not exhibit.get("claim_type") or exhibit.get("claim_type") == claim_type
            ]
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
            if len(text) < 10:
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

        caption = document.add_paragraph()
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption.add_run("\n".join(draft.get("case_caption", {}).get("plaintiffs", ["Plaintiff"])))
        caption.add_run("\nPlaintiff,\n\nv.\n\n")
        caption.add_run("\n".join(draft.get("case_caption", {}).get("defendants", ["Defendant"])))
        caption.add_run("\nDefendant.\n")

        case_no = document.add_paragraph()
        case_no.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        case_no.add_run(
            f"Civil Action No. {draft.get('case_caption', {}).get('case_number', '________________')}"
        ).bold = True

        title = document.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title.add_run(draft.get("case_caption", {}).get("document_title", "COMPLAINT"))
        title_run.bold = True
        title_run.font.size = Pt(14)

        self._add_docx_section(document, "Nature of the Action", draft.get("nature_of_action", []))
        self._add_docx_section(
            document,
            "Parties",
            [
                f"Plaintiff: {', '.join(draft.get('parties', {}).get('plaintiffs', []))}.",
                f"Defendant: {', '.join(draft.get('parties', {}).get('defendants', []))}.",
            ],
        )
        self._add_docx_numbered_facts(document, "Summary of Facts", draft.get("summary_of_facts", []))

        legal_standards = draft.get("legal_standards", [])
        if legal_standards:
            self._add_docx_section(document, "Applicable Legal Standards", legal_standards)

        document.add_heading("Claims for Relief", level=1)
        for index, claim in enumerate(draft.get("claims_for_relief", []), start=1):
            document.add_heading(f"Count {_roman(index)} - {claim.get('count_title', 'Claim')}", level=2)
            self._add_docx_subsection(document, "Legal Standard", claim.get("legal_standards", []))
            self._add_docx_subsection(document, "Supporting Facts", claim.get("supporting_facts", []), numbered=True)
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

        document.save(path)

    def _add_docx_section(self, document: Any, title: str, paragraphs: List[str]) -> None:
        document.add_heading(title, level=1)
        for paragraph in paragraphs:
            document.add_paragraph(str(paragraph))

    def _add_docx_numbered_facts(self, document: Any, title: str, facts: List[str]) -> None:
        document.add_heading(title, level=1)
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
        story = [
            Paragraph(escape(draft.get("court_header", "")), styles["CourtHeader"]),
            Paragraph(
                escape("\n".join(draft.get("case_caption", {}).get("plaintiffs", ["Plaintiff"])))
                + "<br/>Plaintiff,<br/><br/>v.<br/><br/>"
                + escape("\n".join(draft.get("case_caption", {}).get("defendants", ["Defendant"])))
                + "<br/>Defendant.",
                styles["Caption"],
            ),
            Paragraph(
                escape(
                    f"Civil Action No. {draft.get('case_caption', {}).get('case_number', '________________')}"
                ),
                styles["RightAligned"],
            ),
            Paragraph(
                escape(draft.get("case_caption", {}).get("document_title", "COMPLAINT")),
                styles["CourtHeader"],
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
        self._append_pdf_numbered_section(story, styles, "Summary of Facts", draft.get("summary_of_facts", []))
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
            self._append_pdf_numbered_section(story, styles, "Supporting Facts", claim.get("supporting_facts", []), heading_style="Heading3")
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
        story.append(Paragraph("Supporting Exhibits", styles["SectionHeading"]))
        for exhibit in draft.get("exhibits", []):
            story.append(Paragraph(self._pdf_exhibit_markup(exhibit), styles["Normal"]))

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
    ) -> None:
        from reportlab.platypus import Paragraph

        if not paragraphs:
            return
        story.append(Paragraph(escape(title), styles[heading_style]))
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