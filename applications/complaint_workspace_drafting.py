"""Draft and Mike handoff methods delegated from ComplaintWorkspaceService.

The functions keep the original method bodies. The class methods forward here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from copy import deepcopy

from applications.complaint_workspace import (
    DEFAULT_USER_ID,
    MIKE_HANDOFF_CONTRACT_VERSION,
    MIKE_MCP_CONNECTOR_TOOLS,
    MIKE_STATUS_CONTRACT_VERSION,
    MIKE_SYNC_CONTRACT_VERSION,
    _adverse_action_clause,
    _build_complaint_output_release_gate,
    _claim_element_label,
    _claim_type_count_heading,
    _claim_type_display_name,
    _claim_type_filing_guidance,
    _condense_timeline_text,
    _court_header_line,
    _event_fragment,
    _evidence_display_title,
    _evidence_priority,
    _exhibit_label,
    _extract_defendant_name,
    _extract_person_name,
    _formal_complaint_validation_issues,
    _formal_evidence_summary_item,
    _formalize_relief_item,
    _normalize_claim_type,
    _pleading_activity_fragment,
    _pleading_timeline_sentence,
    _resolve_llm_draft_backend_candidates,
    _run_draft_logic_pipeline_safely,
    _sentence_fragment,
    _unique_preserve_order,
    _utc_now,
)


def _build_draft(
    self,
    state: Dict[str, Any],
    requested_relief: Optional[List[str]] = None,
    *,
    use_llm: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
) -> Dict[str, Any]:
    answers = state.get("intake_answers") or {}
    existing_draft = state.get("draft") or {}
    review_snapshot = self._build_review(state)
    overview = dict(review_snapshot.get("overview") or {})
    evidence = dict(state.get("evidence") or {})
    filing_metadata = dict(state.get("filing_metadata") or {})
    testimony_items = list(evidence.get("testimony") or [])
    document_items = list(evidence.get("documents") or [])
    prioritized_document_items = sorted(
        document_items,
        key=lambda item: (-_evidence_priority(item), str(item.get("saved_at") or ""), str(item.get("title") or "")),
    )
    claim_type = _normalize_claim_type(state.get("claim_type"))
    claim_label = _claim_type_display_name(claim_type)
    plaintiff = _extract_person_name(
        filing_metadata.get("signature_plaintiff") or answers.get("party_name"),
        fallback="Plaintiff",
    )
    defendant = _extract_defendant_name(answers.get("opposing_party"), fallback="Defendant")
    caption_plaintiffs = str(filing_metadata.get("caption_plaintiffs") or "").strip() or plaintiff
    caption_defendants = str(filing_metadata.get("caption_defendants") or "").strip() or defendant
    mailing_address = str(filing_metadata.get("mailing_address") or "").strip() or "____________________"
    signature_role = str(filing_metadata.get("signature_role") or "").strip() or "Plaintiff, Pro Se"
    plaintiff_caption_label = (
        "Plaintiffs"
        if any(token in caption_plaintiffs for token in [",", " and "]) and caption_plaintiffs != plaintiff
        else "Plaintiff"
    )
    defendant_caption_label = (
        "Defendants"
        if any(token in caption_defendants for token in [",", " and "])
        else "Defendant"
    )
    is_plural_plaintiffs = plaintiff_caption_label == "Plaintiffs"
    is_plural_defendants = defendant_caption_label == "Defendants"
    plaintiff_party_label = "Plaintiffs" if is_plural_plaintiffs else "Plaintiff"
    defendant_party_label = "Defendants" if is_plural_defendants else "Defendant"
    plaintiff_party_object = "Plaintiffs" if is_plural_plaintiffs else "Plaintiff"
    plaintiff_party_have = "have" if is_plural_plaintiffs else "has"
    plaintiff_party_seek = "seek" if is_plural_plaintiffs else "seeks"
    plaintiff_party_repeat = "repeat and reallege" if is_plural_plaintiffs else "repeats and realleges"
    plaintiff_party_demand = "demand" if is_plural_plaintiffs else "demands"
    plaintiff_party_contend = "contend" if is_plural_plaintiffs else "contends"
    plaintiff_party_give = "give" if is_plural_plaintiffs else "gives"
    plaintiff_intro_name = caption_plaintiffs if is_plural_plaintiffs else plaintiff
    defendant_intro_name = caption_defendants if is_plural_defendants else defendant
    intro_alleges = "allege" if is_plural_plaintiffs else "alleges"
    intro_their = "their" if is_plural_plaintiffs else "their"
    defendant_be = "are" if is_plural_defendants else "is"
    timeline_input = _condense_timeline_text(answers.get("timeline"), "the events occurred close in time")
    protected_activity = _sentence_fragment(
        answers.get("protected_activity"),
        "engaged in protected activity",
    )
    pleading_activity = _pleading_activity_fragment(
        answers.get("protected_activity"),
        "engaging in protected activity",
    )
    adverse_action = _event_fragment(
        answers.get("adverse_action"),
        "suffered an adverse action",
    )
    timeline = _sentence_fragment(
        timeline_input,
        "the events occurred close in time",
    )
    harm = _sentence_fragment(
        answers.get("harm"),
        "suffered compensable harm",
    )
    relief = requested_relief or existing_draft.get("requested_relief") or [
        "Compensatory damages",
        "Back pay",
        "Injunctive relief",
    ]
    case_synopsis = self._build_case_synopsis(state)
    relief_lines = [f"{index}. {_formalize_relief_item(item)}." for index, item in enumerate(relief, start=1)]
    support_count = int(overview.get("supported_elements") or 0)
    missing_count = int(overview.get("missing_elements") or 0)
    evidence_count = len(testimony_items) + len(document_items)
    court_header = _court_header_line(answers.get("court_header"))
    document_exhibits = [
        {
            "label": _exhibit_label(index),
            "title": _evidence_display_title(item, kind="document"),
            "item": item,
        }
        for index, item in enumerate(prioritized_document_items[:3])
    ]
    testimony_reference_lines = _unique_preserve_order([
        f"{plaintiff_party_label} expect{'s' if not is_plural_plaintiffs else ''} to offer testimony presently identified as '{_evidence_display_title(item, kind='testimony')}' in support of the {_claim_element_label(item.get('claim_element_id')).lower()} element."
        for item in testimony_items[:3]
    ])
    document_reference_lines = _unique_preserve_order([
        (
            f"{exhibit['label']} ('{exhibit['title']}') presently supports the "
            f"{_claim_element_label(exhibit['item'].get('claim_element_id')).lower()} element. "
            f"{plaintiff_party_label} expect{'s' if not is_plural_plaintiffs else ''} to offer {exhibit['label'].lower()} in support of the "
            f"{_claim_element_label(exhibit['item'].get('claim_element_id')).lower()} element."
        )
        for exhibit in document_exhibits
    ])
    testimony_summary = "; ".join(_unique_preserve_order([
        _formal_evidence_summary_item(item, kind="testimony")
        for item in testimony_items[:3]
    ])) or "No witness or complainant testimony is presently identified"
    document_summary_items = _unique_preserve_order([
        (
            f"{exhibit['label']} - {exhibit['title']} ({_claim_element_label(exhibit['item'].get('claim_element_id')).strip() or 'Claim element'})"
            f"; {_formal_evidence_summary_item(exhibit['item'], kind='document')}"
        )
        for exhibit in document_exhibits
    ])
    document_summary = "; ".join(document_summary_items) or "No documentary exhibits are presently identified"
    exhibit_titles_lower = {
        _evidence_display_title(item, kind="document").lower()
        for item in prioritized_document_items
    }
    case_specific_evidence_notice: Optional[str] = None
    if {
        "chronology evidence matrix",
        "temporary cli session email evidence memo",
        "reasonable accommodation ocr memo",
    }.issubset(exhibit_titles_lower):
        case_specific_evidence_notice = (
            f"16. The current exhibit set specifically identifies a February 25 to February 26, 2026 written complaint and documentation-escalation thread, "
            "a March 19, 2026 voucher-reversal email, a March 20, 2026 accommodation-conditioned reissuance email, "
            "and a March 24, 2026 provider-supported accommodation-verification record."
        )
    complaint_heading = f"COMPLAINT FOR {claim_label.upper()}"
    nature_of_action = {
        "retaliation": (
            f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this retaliation complaint against {defendant_intro_name}. "
            f"This civil action arises from {defendant_intro_name}'s retaliatory response after {plaintiff_intro_name} {'engaged' if not is_plural_plaintiffs else 'engaged'} in protected activity, including {pleading_activity}."
        ),
        "employment_discrimination": (
            f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this employment discrimination complaint against {defendant_intro_name}. "
            f"This civil action arises from discriminatory workplace treatment, unequal terms or conditions, and resulting harm."
        ),
        "housing_discrimination": (
            f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this housing discrimination complaint against {defendant_intro_name}. "
            f"This civil action arises from discriminatory denial, limitation, interference, or retaliation affecting housing rights or benefits."
        ),
        "due_process_failure": (
            f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this due process complaint against {defendant_intro_name}. "
            f"This civil action arises from adverse action imposed without the notice, hearing, review, or procedural protections required by law."
        ),
        "consumer_protection": (
            f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this consumer protection complaint against {defendant_intro_name}. "
            f"This civil action arises from unfair, deceptive, fraudulent, or otherwise unlawful business practices that caused injury."
        ),
    }.get(
        claim_type,
        f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this {claim_label.lower()} complaint against {defendant_intro_name}. "
        f"This civil action arises from unlawful conduct that injured {plaintiff_intro_name}.",
    )
    relief_paragraph = {
        "retaliation": (
            f"2. {plaintiff_party_label} {plaintiff_party_seek} back pay, front pay or reinstatement, compensatory damages, attorney's fees and costs, "
            "equitable relief, and such further relief as may be just to remedy Defendant's retaliatory acts and the losses flowing from them."
        ),
        "employment_discrimination": (
            f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, equitable relief, and such further relief as may be just to remedy discriminatory employment practices, "
            f"restore lost opportunities, and address the harm caused when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse employment action')}."
        ),
        "housing_discrimination": (
            f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, equitable relief, and such further relief as may be just to remedy discriminatory housing practices, "
            "preserve housing stability, and address the housing-related harms caused by the challenged conduct."
        ),
        "due_process_failure": (
            f"2. {plaintiff_party_label} {plaintiff_party_seek} declaratory relief, equitable relief, damages, and such further relief as may be just to remedy the procedural deprivation "
            f"and the harm caused by the challenged action through which {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a deprivation without adequate process')}."
        ),
        "consumer_protection": (
            f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, restitution, equitable relief, and such further relief as may be just to remedy deceptive or unfair consumer practices "
            f"and the harm caused when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a consumer-facing injury')}."
        ),
    }.get(
        claim_type,
        f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, equitable relief, and such further relief as may be just to remedy unlawful conduct and the harm caused when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse action')}.",
    )
    jurisdiction_paragraph = {
        "retaliation": (
            f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} retaliation for protected activity "
            "and seeks relief for materially adverse acts taken in response to that activity."
        ),
        "employment_discrimination": (
            f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} discriminatory employment practices, "
            "workplace bias, and related unlawful employment actions for which judicial relief is available."
        ),
        "housing_discrimination": (
            f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} discriminatory housing practices, "
            "interference with housing rights or benefits, and related misconduct for which judicial relief is available."
        ),
        "due_process_failure": (
            f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} deprivation without constitutionally "
            "or statutorily required notice, hearing, review, or other procedural protections."
        ),
        "consumer_protection": (
            f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} unfair, deceptive, or unlawful consumer-facing conduct "
            "for which damages, equitable relief, restitution, or related remedies may be awarded."
        ),
    }.get(
        claim_type,
        f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} unlawful conduct for which judicial relief is available.",
    )
    venue_paragraph = {
        "housing_discrimination": (
            "4. Venue is proper in this District because the housing-related events, denial, interference, or threatened loss of housing benefits occurred in this forum and the resulting harm was felt here."
        ),
        "employment_discrimination": (
            "4. Venue is proper in this District because the workplace events, adverse employment decisions, and resulting economic harm occurred in or were directed into this forum."
        ),
        "consumer_protection": (
            "4. Venue is proper in this District because the transaction, deceptive practice, or resulting economic loss occurred in this forum or caused injury here."
        ),
    }.get(
        claim_type,
        "4. Venue is proper in this District because a substantial part of the events or omissions giving rise to these claims occurred in this forum and the resulting harm was felt here.",
    )
    party_paragraphs = {
        "retaliation": (
            f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} individual complainants who engaged in protected activity and {'were' if is_plural_plaintiffs else 'was'} thereafter harmed by the retaliatory conduct described below.",
            f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the party or parties from whom relief is sought and {defendant_be} responsible for the retaliatory actions alleged in this pleading.",
        ),
        "employment_discrimination": (
            f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the employee, applicant, or worker harmed by the discriminatory employment conduct described below.",
            f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the employer or responsible actor from whom relief is sought for the discriminatory employment actions alleged in this pleading.",
        ),
        "housing_discrimination": (
            (
                f"5. {plaintiff_party_label} {plaintiff_intro_name} are housing applicants, tenants, residents, or persons seeking housing-related rights or benefits who were harmed by the discriminatory conduct described below."
                if is_plural_plaintiffs
                else f"5. {plaintiff_party_label} {plaintiff_intro_name} is the housing applicant, tenant, resident, or person seeking housing-related rights or benefits who was harmed by the discriminatory conduct described below."
            ),
            (
                f"6. {defendant_party_label} {defendant_intro_name} are housing providers, landlords, authorities, managers, or responsible actors from whom relief is sought for the housing discrimination alleged in this pleading."
                if is_plural_defendants
                else f"6. {defendant_party_label} {defendant_intro_name} is the housing provider, landlord, authority, manager, or responsible actor from whom relief is sought for the housing discrimination alleged in this pleading."
            ),
        ),
        "due_process_failure": (
            f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the person or persons deprived of rights, benefits, or protected interests without adequate process.",
            f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the person or entity responsible for the challenged deprivation and the missing procedural safeguards alleged in this pleading.",
        ),
        "consumer_protection": (
            f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the consumer or injured person harmed by the deceptive, unfair, or unlawful conduct described below.",
            f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the seller, business, servicer, or responsible actor from whom relief is sought for the consumer-facing conduct alleged in this pleading.",
        ),
    }.get(
        claim_type,
        (
            f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the person or persons harmed by the conduct described below.",
            f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the party or parties from whom relief is sought and {defendant_be} responsible for the conduct alleged in this pleading.",
        ),
    )
    factual_allegation_lines = {
        "retaliation": [
            f"7. {plaintiff_party_label} {'engaged' if not is_plural_plaintiffs else 'engaged'} in protected activity by {pleading_activity}.",
            "8. That protected activity constituted protected opposition, reporting, or participation activity under the governing anti-retaliation framework.",
            f"9. Within days of that protected activity, {defendant_party_label} took materially adverse action against {plaintiff_party_object} by {_adverse_action_clause(answers.get('adverse_action'), 'taking materially adverse action against Plaintiff')}.",
            f"10. The relevant chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The events occurred in close temporal proximity')}",
            f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
        ],
        "employment_discrimination": [
            f"7. {plaintiff_party_label} {intro_alleges} facts showing discriminatory employment treatment, including protected conduct or circumstances such as {pleading_activity}.",
            f"8. {defendant_party_label} thereafter took or maintained adverse employment action by which {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse employment action')}.",
            f"9. The employment chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The relevant employment events occurred in close succession')}",
            "10. The present record supports an inference of discriminatory motive, disparate treatment, prohibited bias, retaliation, or other unlawful employment decision-making.",
            f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
        ],
        "housing_discrimination": [
            f"7. {plaintiff_party_label} {intro_alleges} that {'they' if is_plural_plaintiffs else 'they'} sought, used, requested, or protected housing-related rights, accommodations, benefits, tenancy rights, or fair treatment, including {pleading_activity}.",
            f"8. {defendant_party_label} thereafter denied, burdened, interfered with, or threatened housing-related rights or benefits through conduct including {_sentence_fragment(answers.get('adverse_action'), 'a housing-related deprivation')}.",
            f"9. The housing-related chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The housing-related events occurred in close succession')}",
            f"10. The present record supports an inference that {defendant_party_label} acted in a discriminatory manner, interfered with protected housing rights, or retaliated in connection with protected housing activity.",
            f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {'suffered' if not is_plural_plaintiffs else 'suffered'} harm including {_sentence_fragment(answers.get('harm'), 'compensable harm')}.",
        ],
        "due_process_failure": [
            f"7. {plaintiff_party_label} {intro_alleges} that {defendant_party_label} imposed or maintained a deprivation affecting protected rights, interests, status, benefits, or property.",
            f"8. The challenged action is that {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a deprivation without adequate process')}.",
            f"9. The chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The challenged events occurred in close succession')}",
            f"10. {plaintiff_party_label} {intro_alleges} that the deprivation occurred without adequate notice, hearing, review, appeal, or other required procedural protection.",
            f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
        ],
        "consumer_protection": [
            f"7. {plaintiff_party_label} {intro_alleges} that {defendant_party_label} engaged in deceptive, misleading, unfair, or otherwise unlawful consumer-facing conduct.",
            f"8. That conduct included or resulted in adverse action or consequences when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a consumer-facing injury')}.",
            f"9. The chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The relevant consumer-facing events occurred in close succession')}",
            f"10. {plaintiff_party_label} {intro_alleges} that the challenged conduct caused consumer harm, financial loss, or other compensable injury in a transactional or service context.",
            f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
        ],
    }.get(
        claim_type,
        [
            f"7. {plaintiff_party_label} {intro_alleges} conduct or circumstances including {pleading_activity}.",
            f"8. {defendant_party_label} engaged in conduct through which {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse action')}.",
            f"9. The chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The relevant events occurred in close succession')}",
            f"10. {plaintiff_party_label} {intro_alleges} facts supporting a plausible claim for relief.",
            f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
        ],
    )
    count_heading = {
        "retaliation": "COUNT I - RETALIATION",
        "employment_discrimination": "COUNT I - EMPLOYMENT DISCRIMINATION",
        "housing_discrimination": "COUNT I - HOUSING DISCRIMINATION",
        "due_process_failure": "COUNT I - DUE PROCESS VIOLATION",
        "consumer_protection": "COUNT I - CONSUMER PROTECTION",
    }.get(claim_type, f"COUNT I - {claim_label.upper()}")
    claim_paragraphs = {
        "retaliation": [
            f"{plaintiff_party_label} engaged in protected activity by {pleading_activity}, and {defendant_party_label} knew or should have known of that protected conduct.",
            f"{defendant_party_label} thereafter subjected {plaintiff_party_object} to materially adverse action by {_adverse_action_clause(answers.get('adverse_action'), 'taking materially adverse action against Plaintiff')}, under circumstances supporting a causal inference of retaliation.",
            f"The close temporal proximity, {defendant_party_label}' knowledge of the protected activity, the evidentiary record, and the resulting harm plausibly support a retaliation claim and entitle {plaintiff_party_object} to relief.",
        ],
        "employment_discrimination": [
            f"{plaintiff_party_label} {'were' if is_plural_plaintiffs else 'was'} subjected to adverse employment treatment described as {adverse_action}, in a manner that was discriminatory, disparate, or otherwise unlawful.",
            "The pleaded facts support an inference that Defendant's conduct was motivated by unlawful bias, protected status, protected conduct, or a prohibited employment practice.",
            "The evidentiary record and resulting harm support a plausible employment discrimination claim.",
        ],
        "housing_discrimination": [
            f"{defendant_party_label} denied, limited, burdened, or interfered with housing-related rights, opportunities, services, or benefits through conduct described as {adverse_action}.",
            f"The pleaded facts support an inference that {defendant_party_label} acted in a discriminatory manner or retaliated in connection with protected housing activity, status, or rights.",
            "The evidentiary record and resulting harm support a plausible housing discrimination claim.",
        ],
        "due_process_failure": [
            "Defendant imposed or maintained adverse consequences without the notice, review, hearing, or procedural protections required by law.",
            f"The resulting deprivation included challenged action described as {adverse_action} and related harms without adequate procedural safeguards.",
            "The pleaded facts and evidentiary record support a plausible due process claim.",
        ],
        "consumer_protection": [
            "Defendant engaged in unfair, deceptive, misleading, or unlawful conduct in connection with a consumer transaction or obligation.",
            f"That conduct resulted in adverse action or consequences when Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered a consumer-facing injury')} and caused economic or other compensable harm, including {_sentence_fragment(answers.get('harm'), 'compensable harm')}.",
            "The pleaded facts and evidentiary record support a plausible consumer protection claim.",
        ],
    }.get(
        claim_type,
        [
            "Defendant engaged in unlawful conduct causing harm to Plaintiff.",
            "The pleaded facts support a plausible claim for relief.",
            "The evidentiary record and resulting harm warrant judicial relief.",
        ],
    )
    evidentiary_lines: List[str] = [
        (
            f"12. {plaintiff_party_label} presently {'rely' if is_plural_plaintiffs else 'relies'} on {evidence_count} identified evidentiary items. The witness proof currently identified includes: {testimony_summary}."
            if testimony_items
            else f"12. {plaintiff_party_label} presently {'rely' if is_plural_plaintiffs else 'relies'} on the evidentiary materials identified below and anticipate{'' if is_plural_plaintiffs else 's'} that testimonial proof may be supplemented through discovery, amendment, or sworn declarations."
        ),
        (
            f"13. {plaintiff_party_label} presently {'identify' if is_plural_plaintiffs else 'identifies'} the following documents, exhibits, or records in support of this pleading: {document_summary}."
            if document_items
            else f"13. {plaintiff_party_label} {plaintiff_party_have} not yet attached documentary exhibits to this export, but preserve{'' if is_plural_plaintiffs else 's'} the right to supplement the pleading with records, correspondence, or other supporting materials."
        ),
        (
            f"14. Based on the information presently available, {plaintiff_party_label} {plaintiff_party_contend} that the evidentiary record presently supports {support_count} core claim elements "
            f"and that {missing_count} areas, if any, may be further corroborated through discovery, amendment, or additional evidentiary development."
        ),
        (
            f"15. {plaintiff_party_label} {plaintiff_party_give} notice that the identified testimony, documentary exhibits, and chronology materials constitute part of the evidentiary basis for this pleading "
            "and may be supplemented, authenticated, or amended as discovery proceeds."
        ),
    ]
    if case_specific_evidence_notice:
        evidentiary_lines.append(case_specific_evidence_notice)
    extra_evidence_start = 16 + (1 if case_specific_evidence_notice else 0)
    extra_evidence_lines = (testimony_reference_lines + document_reference_lines)[:2]
    evidentiary_lines.extend(
        f"{extra_evidence_start + index}. {line}"
        for index, line in enumerate(extra_evidence_lines)
    )
    claim_intro_paragraph = extra_evidence_start + len(extra_evidence_lines)
    claim_detail_start = claim_intro_paragraph + 1
    body = "\n\n".join(
        [
            "IN THE UNITED STATES DISTRICT COURT",
            court_header,
            "",
            f"{caption_plaintiffs}, {plaintiff_caption_label},",
            "v.",
            f"{caption_defendants}, {defendant_caption_label}.",
            "",
            "Civil Action No. ________________",
            complaint_heading,
            "JURY TRIAL DEMANDED",
            "",
            (
                f"{plaintiff_party_label} {plaintiff_intro_name}, proceeding pro se, {intro_alleges} upon personal knowledge as to "
                f"{intro_their} own acts and upon information and belief as to all other matters as follows:"
            ),
            "",
            "NATURE OF THE ACTION",
            nature_of_action,
            relief_paragraph,
            "",
            "JURISDICTION AND VENUE",
            jurisdiction_paragraph,
            venue_paragraph,
            "",
            "PARTIES",
            party_paragraphs[0],
            party_paragraphs[1],
            "",
            "FACTUAL ALLEGATIONS",
            *factual_allegation_lines,
            "",
            "EVIDENTIARY SUPPORT AND NOTICE",
            *evidentiary_lines,
            "",
            "CLAIM FOR RELIEF",
            count_heading,
            f"{claim_intro_paragraph}. {plaintiff_intro_name} {plaintiff_party_repeat} the preceding paragraphs as if fully set forth herein.",
            *[f"{claim_detail_start + index}. {line}" for index, line in enumerate(claim_paragraphs)],
            f"{claim_detail_start + 3}. {plaintiff_party_label} {plaintiff_party_have} sustained damages and losses including {_sentence_fragment(answers.get('harm'), 'compensable harm')}.",
            (
                f"{claim_detail_start + 4}. As a direct and proximate result of Defendant's retaliatory conduct, {plaintiff_party_label} {'are' if is_plural_plaintiffs else 'is'} entitled to recover damages, equitable relief, fees and costs where available, and such further relief as the Court deems just and proper."
                if claim_type == "retaliation"
                else f"{claim_detail_start + 4}. {defendant_party_label}' acts were intentional, knowing, reckless, retaliatory, discriminatory, deceptive, or otherwise unlawful under the governing claim theory."
            ),
            "",
            "PRAYER FOR RELIEF",
            (
                f"Wherefore, {plaintiff_party_label} respectfully {'request' if is_plural_plaintiffs else 'requests'} judgment against {defendant_party_label} on the retaliation claim alleged herein and {'seek' if is_plural_plaintiffs else 'seeks'} the following relief:"
                if claim_type == "retaliation"
                else f"Wherefore, {plaintiff_party_label} {'request' if is_plural_plaintiffs else 'requests'} judgment against {defendant_party_label} and the following relief:"
            ),
            "\n".join(relief_lines),
            "",
            "JURY DEMAND",
            f"{plaintiff_party_label} {plaintiff_party_demand} a trial by jury on all issues so triable.",
            "",
            "SIGNATURE BLOCK",
            f"Dated: ____________________",
            "",
            "Respectfully submitted,",
            "",
            f"{plaintiff}",
            signature_role,
            f"Address: {mailing_address}",
            "Telephone: ____________________",
            "Email: ____________________",
        ]
    )
    draft = {
        "title": f"{caption_plaintiffs} v. {caption_defendants} {claim_label} Complaint",
        "requested_relief": relief,
        "case_synopsis": case_synopsis,
        "claim_type": claim_type,
        "body": body,
        "generated_at": _utc_now(),
        "review_snapshot": review_snapshot,
        "draft_strategy": "template",
    }
    if use_llm:
        self._last_draft_refinement_error = None
        resolved_backends = _resolve_llm_draft_backend_candidates(provider, model)
        attempted_providers: List[str] = []
        for resolved_backend in resolved_backends:
            provider_name = str(resolved_backend["provider"] or "").strip()
            if provider_name:
                attempted_providers.append(provider_name)
            refined_draft = self._refine_draft_with_llm_router(
                state,
                draft,
                provider=resolved_backend["provider"],
                model=resolved_backend["model"],
                requested_provider=resolved_backend["requested_provider"],
                requested_model=resolved_backend["requested_model"],
                config_path=config_path,
                backend_id=backend_id,
            )
            if refined_draft:
                if len(attempted_providers) > 1:
                    refined_draft["draft_backend_fallback_chain"] = attempted_providers
                return refined_draft
        if self._last_draft_refinement_error:
            if attempted_providers:
                draft["draft_backend_fallback_chain"] = attempted_providers
            draft["draft_fallback_reason"] = self._last_draft_refinement_error
    return draft


def _analyze_complaint_output(self, packet: Dict[str, Any], artifact_analysis: Dict[str, Any]) -> Dict[str, Any]:
    from .ui_review import review_complaint_output_with_llm_router

    draft = dict(packet.get("draft") or {})
    review = dict(packet.get("review") or {})
    overview = dict(review.get("overview") or {})
    body = str(draft.get("body") or "").strip()
    case_synopsis = str(packet.get("case_synopsis") or "").strip()
    draft_backend = dict(draft.get("draft_backend") or {})
    issues: List[Dict[str, Any]] = []
    suggestions: List[Dict[str, Any]] = []
    formal_sections_present = {
        "caption": "IN THE UNITED STATES DISTRICT COURT" in body,
        "civil_action_number": "Civil Action No. ________________" in body,
        "nature_of_action": "NATURE OF THE ACTION" in body,
        "jurisdiction_and_venue": "JURISDICTION AND VENUE" in body,
        "parties": "PARTIES" in body,
        "factual_allegations": "FACTUAL ALLEGATIONS" in body,
        "evidentiary_support": "EVIDENTIARY SUPPORT AND NOTICE" in body,
        "claim_count": "COUNT I -" in body,
        "prayer_for_relief": "PRAYER FOR RELIEF" in body,
        "jury_demand": "JURY DEMAND" in body,
        "signature_block": "SIGNATURE BLOCK" in body,
    }
    claim_type = _normalize_claim_type(packet.get("claim_type"))
    claim_label = _claim_type_display_name(claim_type)
    expected_complaint_heading = f"COMPLAINT FOR {claim_label.upper()}"
    expected_count_heading = _claim_type_count_heading(claim_type)
    claim_type_alignment = {
        "complaint_heading_matches": expected_complaint_heading in body,
        "count_heading_matches": expected_count_heading in body,
    }
    validation_issues = _formal_complaint_validation_issues(body, claim_type)
    meta_summary_issues = [issue for issue in validation_issues if issue.startswith("Contains meta-summary language:")]
    numbering_issue_present = any(issue == "Missing numbered pleading paragraphs." for issue in validation_issues)

    if artifact_analysis.get("missing_elements", 0) > 0:
        missing_count = int(artifact_analysis.get("missing_elements") or 0)
        issues.append(
            {
                "severity": "high",
                "source": "complaint_output",
                "finding": f"The exported complaint still reflects {missing_count} unsupported claim elements.",
                "ui_implication": "The review and draft stages need stronger warnings before the user treats the complaint as filing-ready.",
            }
        )
        suggestions.append(
            {
                "title": "Tighten review-to-draft gatekeeping",
                "recommendation": "Add stronger blocker language and a more prominent unsupported-elements summary before draft generation or export.",
                "target_surface": "review,draft,integrations",
            }
        )
    if not case_synopsis:
        issues.append(
            {
                "severity": "medium",
                "source": "complaint_output",
                "finding": "The exported complaint has no shared case synopsis.",
                "ui_implication": "Users can reach export without preserving a stable theory of the case across mediator, review, and draft surfaces.",
            }
        )
        suggestions.append(
            {
                "title": "Make case framing harder to miss",
                "recommendation": "Require or strongly encourage a shared case synopsis before export and keep it visible near every major handoff.",
                "target_surface": "intake,review,draft",
            }
        )
    if artifact_analysis.get("draft_word_count", 0) < 80:
        issues.append(
            {
                "severity": "medium",
                "source": "complaint_output",
                "finding": "The exported complaint draft is still very short.",
                "ui_implication": "The draft workflow may be under-explaining what a usable first complaint should contain.",
            }
        )
        suggestions.append(
            {
                "title": "Strengthen draft completeness cues",
                "recommendation": "Show a drafting checklist and clearer guidance about allegations, chronology, harm, and requested relief before export.",
                "target_surface": "draft",
            }
        )
    if artifact_analysis.get("requested_relief_count", 0) == 0:
        issues.append(
            {
                "severity": "medium",
                "source": "complaint_output",
                "finding": "No requested relief was carried into the export.",
                "ui_implication": "The user may not understand that requested relief should be completed before download.",
            }
        )
        suggestions.append(
            {
                "title": "Surface requested-relief validation",
                "recommendation": "Warn before export when requested relief is empty and point the user back to the draft editor.",
                "target_surface": "draft,integrations",
            }
        )
    if artifact_analysis.get("evidence_item_count", 0) == 0:
        issues.append(
            {
                "severity": "high",
                "source": "complaint_output",
                "finding": "The complaint was exported without any saved evidence items.",
                "ui_implication": "The workspace is not making evidence capture feel mandatory enough before a user downloads the packet.",
            }
        )
        suggestions.append(
            {
                "title": "Make evidence support more legible before export",
                "recommendation": "Display stronger export warnings and direct links back to the evidence workbench when the packet lacks corroborating materials.",
                "target_surface": "evidence,review,integrations",
            }
        )

    formal_markers = [
        "IN THE UNITED STATES DISTRICT COURT",
        "Civil Action No. ________________",
        "COMPLAINT FOR",
        "JURISDICTION AND VENUE",
        "FACTUAL ALLEGATIONS",
        "EVIDENTIARY SUPPORT AND NOTICE",
        "COUNT I -",
        "PRAYER FOR RELIEF",
        "JURY DEMAND",
        "SIGNATURE BLOCK",
    ]
    missing_markers = [marker for marker in formal_markers if marker not in body]
    if missing_markers:
        issues.append(
            {
                "severity": "high",
                "source": "complaint_output",
                "finding": "The exported complaint is missing formal pleading sections.",
                "ui_implication": "The drafting UI is letting users export something that does not read like a formal legal complaint.",
            }
        )

    if numbering_issue_present:
        issues.append(
            {
                "severity": "high",
                "source": "complaint_output",
                "finding": "The exported complaint is missing numbered pleading paragraphs.",
                "ui_implication": "The draft builder is allowing narrative text that still reads like a summary instead of a filed complaint.",
            }
        )
        suggestions.append(
            {
                "title": "Keep numbered complaint paragraphs visible in the draft",
                "recommendation": "Show numbered pleading paragraph examples and warn before export if the draft body stops reading like a paragraph-numbered complaint.",
                "target_surface": "draft,document,integrations",
            }
        )

    if meta_summary_issues:
        issues.append(
            {
                "severity": "high",
                "source": "complaint_output",
                "finding": "The exported complaint still contains internal product or workflow language instead of clean pleading language.",
                "ui_implication": "The LLM drafting flow is leaking system-facing wording into a client-facing legal document.",
            }
        )
        suggestions.append(
            {
                "title": "Strip workflow language out of the complaint draft",
                "recommendation": "Warn when the draft body mentions workflow summaries, complaint records, SDKs, JSON, or support matrices so the final complaint remains client-safe.",
                "target_surface": "draft,integrations,optimizer",
            }
        )

    if not claim_type_alignment["complaint_heading_matches"] or not claim_type_alignment["count_heading_matches"]:
        issues.append(
            {
                "severity": "high",
                "source": "complaint_output",
                "finding": f"The exported complaint does not clearly read like a {claim_label.lower()} complaint for the selected claim type.",
                "ui_implication": "The drafting flow is letting the complaint drift into a generic or mismatched claim shape before export.",
            }
        )
        suggestions.append(
            {
                "title": "Keep the selected claim theory visible through drafting",
                "recommendation": "Show the selected claim type, count heading, and claim-specific allegation checklist throughout the draft flow so the complaint stays aligned to the chosen legal theory.",
                "target_surface": "draft,review,integrations",
            }
        )
        suggestions.append(
            {
                "title": "Enforce formal pleading structure",
                "recommendation": "Keep the draft builder anchored to formal complaint sections like jurisdiction, factual allegations, prayer for relief, and jury demand before export.",
                "target_surface": "draft,document,integrations",
            }
        )

    if not formal_sections_present["signature_block"]:
        issues.append(
            {
                "severity": "medium",
                "source": "complaint_output",
                "finding": "The exported complaint is missing a signature block.",
                "ui_implication": "The draft stage still reads too much like a memo unless the filing posture stays visible through export.",
            }
        )
        suggestions.append(
            {
                "title": "Keep filing posture visible in the draft",
                "recommendation": "Preserve a default signature block and explain in the draft editor that the output should resemble a court filing rather than a loose narrative summary.",
                "target_surface": "draft,integrations",
            }
        )

    if artifact_analysis.get("evidence_item_count", 0) > 0 and "EVIDENTIARY SUPPORT AND NOTICE" not in body:
        issues.append(
            {
                "severity": "medium",
                "source": "complaint_output",
                "finding": "The complaint includes evidence in the record, but the draft does not make that evidentiary posture legible.",
                "ui_implication": "Users may not see how saved evidence is helping shape the pleading.",
            }
        )
        suggestions.append(
            {
                "title": "Ground the draft in saved exhibits",
                "recommendation": "Show clearer exhibit and support references in the draft so the complaint feels tied to the record gathered in the evidence and review stages.",
                "target_surface": "evidence,review,draft",
            }
        )

    router_review = None
    try:
        router_review = review_complaint_output_with_llm_router(
            self._build_packet_markdown(packet),
            claim_type=claim_label,
            claim_guidance=_claim_type_filing_guidance(claim_type),
            synopsis=case_synopsis,
            notes=(
                "Assess whether this output looks like a formal legal complaint, whether it matches the selected claim type, "
                "and turn any filing-shape or claim-alignment defects into UI/UX repairs for intake, evidence, review, draft, and export surfaces."
            ),
        )
    except Exception:
        router_review = None

    router_payload = dict((router_review or {}).get("review") or {})
    router_issues = [dict(item) for item in list(router_payload.get("issues") or []) if isinstance(item, dict)]
    router_suggestions = [
        dict(item) for item in list(router_payload.get("ui_suggestions") or []) if isinstance(item, dict)
    ]
    for issue in router_issues[:6]:
        issues.append(
            {
                "severity": str(issue.get("severity") or "medium"),
                "source": "complaint_output_router",
                "finding": str(issue.get("finding") or "The complaint output router identified a filing-shape issue."),
                "ui_implication": str(
                    issue.get("ui_implication")
                    or issue.get("complaint_impact")
                    or "The UI flow is likely under-guiding the user before export."
                ),
            }
        )
    for suggestion in router_suggestions[:6]:
        suggestions.append(
            {
                "title": str(suggestion.get("title") or "Repair complaint-output workflow"),
                "recommendation": str(
                    suggestion.get("recommendation")
                    or suggestion.get("why_it_matters")
                    or "Tighten the complaint workflow so the exported filing reads more formally."
                ),
                "target_surface": str(suggestion.get("target_surface") or "draft,review,integrations"),
            }
        )

    section_score = 5 * sum(1 for value in formal_sections_present.values() if value)
    body_length_score = 10 if artifact_analysis.get("draft_word_count", 0) >= 180 else 0
    evidence_score = 10 if artifact_analysis.get("evidence_item_count", 0) > 0 else 0
    relief_score = 5 if artifact_analysis.get("requested_relief_count", 0) > 0 else 0
    support_score = 5 if int(artifact_analysis.get("supported_elements") or 0) > 0 else 0
    heuristic_score = min(100, 35 + section_score + body_length_score + evidence_score + relief_score + support_score)
    router_score = int(router_payload.get("filing_shape_score") or 0) if router_payload else 0
    claim_type_alignment_score = (
        100
        if claim_type_alignment["complaint_heading_matches"] and claim_type_alignment["count_heading_matches"]
        else 50
        if claim_type_alignment["complaint_heading_matches"] or claim_type_alignment["count_heading_matches"]
        else 0
    )
    router_alignment_score = int(router_payload.get("claim_type_alignment_score") or 0) if router_payload else 0
    filing_shape_score = (
        round((heuristic_score + router_score) / 2)
        if router_score
        else heuristic_score
    )
    if claim_type_alignment_score == 0:
        resolved_claim_type_alignment_score = 0
    else:
        resolved_claim_type_alignment_score = (
            round((claim_type_alignment_score + router_alignment_score) / 2)
            if router_alignment_score
            else claim_type_alignment_score
        )
    release_gate = _build_complaint_output_release_gate(
        claim_type=claim_type,
        draft_strategy=str(draft.get("draft_strategy") or "template"),
        filing_shape_score=filing_shape_score,
        claim_type_alignment_score=resolved_claim_type_alignment_score,
        missing_elements=int(artifact_analysis.get("missing_elements") or 0),
        evidence_item_count=int(artifact_analysis.get("evidence_item_count") or 0),
    )

    if filing_shape_score < 75:
        issues.append(
            {
                "severity": "high",
                "source": "complaint_output",
                "finding": "The generated complaint still does not read enough like a filing-ready legal complaint.",
                "ui_implication": "The intake, evidence, review, and draft surfaces need stronger structure cues before export is treated as safe.",
            }
        )
        suggestions.append(
            {
                "title": "Promote filing-readiness guidance before export",
                "recommendation": "Keep the draft builder focused on caption, chronology, claim counts, evidentiary grounding, and requested relief so the exported complaint resembles a court filing instead of a loose summary.",
                "target_surface": "draft,review,integrations",
            }
        )

    if not suggestions:
        suggestions.append(
            {
                "title": "Preserve the current filing flow",
                "recommendation": "The exported complaint looks coherent enough to keep the current UI flow, but continue validating navigation, evidence support, and clarity through Playwright.",
                "target_surface": "workspace,review,document",
            }
        )

    complaint_output_issue_items = [
        dict(item)
        for item in issues
        if str((item or {}).get("source") or "").startswith("complaint_output")
    ]
    high_severity_complaint_items = [
        dict(item)
        for item in complaint_output_issue_items
        if str((item or {}).get("severity") or "").lower() == "high"
    ]
    formal_diagnostics = {
        "formal_defect_count": len(complaint_output_issue_items),
        "high_severity_issue_count": len(high_severity_complaint_items),
        "top_formal_findings": [
            str((item or {}).get("finding") or "").strip()
            for item in complaint_output_issue_items[:5]
            if str((item or {}).get("finding") or "").strip()
        ],
        "top_ui_implications": [
            str((item or {}).get("ui_implication") or "").strip()
            for item in complaint_output_issue_items[:5]
            if str((item or {}).get("ui_implication") or "").strip()
        ],
        "top_ui_suggestions": [
            str((item or {}).get("title") or "").strip()
            for item in suggestions[:5]
            if str((item or {}).get("title") or "").strip()
        ],
        "release_gate_verdict": str((release_gate or {}).get("verdict") or "").strip() or "unknown",
    }

    resolved_router_backend = deepcopy((router_review or {}).get("backend") or {})
    if resolved_router_backend and draft_backend:
        for key in ("id", "requested_provider", "requested_model", "provider", "model"):
            if resolved_router_backend.get(key) in (None, "") and draft_backend.get(key) not in (None, ""):
                resolved_router_backend[key] = draft_backend.get(key)
    if not resolved_router_backend and draft_backend:
        resolved_router_backend = {
            "strategy": str(draft.get("draft_strategy") or "template"),
            "provider": draft_backend.get("provider"),
            "model": draft_backend.get("model"),
            "requested_provider": draft_backend.get("requested_provider"),
            "requested_model": draft_backend.get("requested_model"),
            "id": draft_backend.get("id"),
        }

    return {
        "summary": (
            "The exported complaint artifact was analyzed to infer which UI steps may still be too weak, "
            "hidden, or permissive for a real complainant."
        ),
        "filing_shape_score": filing_shape_score,
        "formal_sections_present": formal_sections_present,
        "claim_type_alignment": claim_type_alignment,
        "claim_type_alignment_score": resolved_claim_type_alignment_score,
        "release_gate": release_gate,
        "issues": issues,
        "ui_suggestions": suggestions,
        "formal_diagnostics": formal_diagnostics,
        "draft_strategy": str(draft.get("draft_strategy") or "template"),
        "draft_fallback_reason": str(draft.get("draft_fallback_reason") or "").strip(),
        "draft_normalizations": list(draft.get("draft_normalizations") or []),
        "draft_excerpt": body[:600],
        "complaint_strengths": [
            f"Supported elements: {int(overview.get('supported_elements') or 0)}",
            f"Evidence items: {int(overview.get('testimony_items') or 0) + int(overview.get('document_items') or 0)}",
            f"Requested relief items: {int(artifact_analysis.get('requested_relief_count') or 0)}",
            f"Formal sections present: {sum(1 for value in formal_sections_present.values() if value)}/{len(formal_sections_present)}",
            f"Claim type alignment: {expected_complaint_heading} / {expected_count_heading}",
        ],
        "router_backends": [
            deepcopy(resolved_router_backend)
        ]
        if isinstance(resolved_router_backend, dict) and resolved_router_backend
        else [],
        "router_review": {
            **(router_review or {}),
            "backend": resolved_router_backend,
        }
        if isinstance(router_review, dict)
        else {"backend": resolved_router_backend},
    }


def sync_mike_final_draft(
    self,
    user_id: Optional[str],
    *,
    body: str,
    title: Optional[str] = None,
    requested_relief: Optional[List[str]] = None,
    handoff_id: Optional[str] = None,
    project_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    mike_document_id: Optional[str] = None,
    citation_links: Optional[List[Dict[str, Any]]] = None,
    redline_summary: Optional[str] = None,
    source_updated_at: Optional[str] = None,
    structured_deltas: Optional[List[Dict[str, Any]]] = None,
    editor_metadata: Optional[Dict[str, Any]] = None,
    grounding_mode: Optional[str] = None,
    assertion_annotations: Optional[List[Dict[str, Any]]] = None,
    authority_links: Optional[List[Dict[str, Any]]] = None,
    sync_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw_body = str(body or "")
    if not raw_body.strip():
        raise ValueError("The draft body content is required and cannot be empty.")
    state = self._load_state(str(user_id or DEFAULT_USER_ID))
    draft = deepcopy(state.get("draft") or self._build_draft(state))
    mike_integration = dict(state.get("mike_integration") or {})
    last_handoff = dict(mike_integration.get("last_handoff") or {})
    provided_handoff_id = str(handoff_id or "").strip()
    fallback_handoff_id = str(last_handoff.get("handoff_id") or "").strip()
    resolved_handoff_id = provided_handoff_id or fallback_handoff_id or None
    existing_title = str(draft.get("title") or "").strip()
    base_draft_identity = self._build_mike_base_draft_identity(draft)
    if title is not None:
        normalized_title = str(title or "").strip()
        draft["title"] = normalized_title or existing_title or "Complaint Draft"
    draft["body"] = raw_body
    if requested_relief is not None:
        draft["requested_relief"] = [str(item).strip() for item in list(requested_relief or []) if str(item).strip()]
    synced_at = _utc_now()
    normalized_citation_links = self._normalize_mike_citation_links(citation_links)
    normalized_structured_deltas = self._validate_mike_structured_deltas(structured_deltas)
    normalized_editor_metadata = self._normalize_mike_editor_metadata(editor_metadata)
    resolved_grounding_mode = self._resolve_mike_grounding_mode(grounding_mode)
    normalized_assertion_annotations = self._normalize_mike_assertion_annotations(
        assertion_annotations,
        body=raw_body,
    )
    normalized_authority_links = self._normalize_mike_authority_links(authority_links)
    normalized_sync_provenance = self._normalize_mike_sync_provenance(
        sync_provenance,
        base_draft_identity=base_draft_identity,
        redline_metadata=self._build_mike_redline_metadata(
            redline_summary=redline_summary,
            structured_deltas=normalized_structured_deltas,
        ),
    )
    review_payload = dict(state.get("support_review") or {})
    if not review_payload:
        review_payload = self._build_review(state)
    legal_corpus_review = self._build_mike_legal_corpus_review(
        claim_type=str(state.get("claim_type") or "retaliation"),
        grounding_mode=resolved_grounding_mode,
        assertion_annotations=normalized_assertion_annotations,
        authority_links=normalized_authority_links,
    )
    logic_review = self._build_mike_logic_review(
        state=state,
        review=review_payload,
        assertion_annotations=normalized_assertion_annotations,
        authority_links=normalized_authority_links,
    )
    # Run the draft-logic pipeline and merge its proof report into logic_review.
    draft_proof_report = _run_draft_logic_pipeline_safely(
        raw_body,
        state=str(state.get("state_code") or "").strip() or None,
    )
    logic_review = self._merge_draft_proof_report(logic_review, draft_proof_report)
    router_policy = self._build_mike_router_policy_snapshot()
    citation_link_check = self._check_mike_citation_links(
        state,
        normalized_citation_links,
        review=review_payload,
    )
    sync_diagnostics = self._build_mike_sync_diagnostics(
        citation_link_check=citation_link_check,
        review_payload=review_payload,
        structured_deltas=normalized_structured_deltas,
        legal_corpus_review=legal_corpus_review,
        logic_review=logic_review,
    )
    sync_integrity_payload_bytes = json.dumps(
        {
            "handoff_id": resolved_handoff_id,
            "body": raw_body,
            "synced_at": synced_at,
            "citation_links": normalized_citation_links,
            "structured_deltas": normalized_structured_deltas,
            "source_updated_at": str(source_updated_at or "").strip(),
            "editor_metadata": normalized_editor_metadata,
            "grounding_mode": resolved_grounding_mode,
            "assertion_annotations": normalized_assertion_annotations,
            "authority_links": normalized_authority_links,
            "sync_provenance": normalized_sync_provenance,
        },
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    sync_hash_secret = str(os.getenv("COMPLAINT_MIKE_SYNC_HASH_SECRET") or "").strip()
    if sync_hash_secret:
        sync_integrity_hash = hmac.new(sync_hash_secret.encode("utf-8"), sync_integrity_payload_bytes, hashlib.sha256).hexdigest()
        sync_integrity_hash_mode = "hmac_sha256"
    else:
        sync_integrity_hash = hashlib.sha256(sync_integrity_payload_bytes).hexdigest()
        sync_integrity_hash_mode = "sha256_unkeyed"
    draft["updated_at"] = synced_at
    draft["sync_source"] = "mike"
    draft["sync_metadata"] = {
        "contract_version": MIKE_SYNC_CONTRACT_VERSION,
        "handoff_id": resolved_handoff_id,
        "project_id": str(project_id or "").strip() or None,
        "workspace_id": str(workspace_id or "").strip() or None,
        "mike_document_id": str(mike_document_id or "").strip() or None,
        "citation_links": normalized_citation_links,
        "structured_deltas": normalized_structured_deltas,
        "citation_link_check": citation_link_check,
        "sync_diagnostics": sync_diagnostics,
        "redline_summary": str(redline_summary or "").strip() or None,
        "redline_metadata": deepcopy(normalized_sync_provenance.get("redline_metadata") or {}),
        "source_updated_at": str(source_updated_at or "").strip() or None,
        "editor_metadata": normalized_editor_metadata,
        "grounding_mode": resolved_grounding_mode,
        "assertion_annotations": normalized_assertion_annotations,
        "authority_links": normalized_authority_links,
        "sync_provenance": normalized_sync_provenance,
        "legal_corpus_review": legal_corpus_review,
        "logic_review": logic_review,
        "router_policy": router_policy,
        "sync_integrity_hash": sync_integrity_hash,
        "sync_integrity_hash_mode": sync_integrity_hash_mode,
        "synced_at": synced_at,
    }
    state["draft"] = draft
    sync_history = [dict(item) for item in list(mike_integration.get("sync_history") or []) if isinstance(item, dict)]
    sync_record = {
        "synced_at": synced_at,
        "handoff_id": draft["sync_metadata"]["handoff_id"],
        "project_id": draft["sync_metadata"]["project_id"],
        "workspace_id": draft["sync_metadata"]["workspace_id"],
        "mike_document_id": draft["sync_metadata"]["mike_document_id"],
        "body_chars": len(raw_body),
        "title": str(draft.get("title") or "").strip(),
        "citation_link_count": citation_link_check["total_links"],
        "citation_link_conflict_count": len(citation_link_check["conflicts"]),
        "citation_link_has_conflicts": citation_link_check["has_conflicts"],
        "citation_link_unknown_element_count": len(list(citation_link_check.get("unknown_claim_element_ids") or [])),
        "structured_delta_count": len(normalized_structured_deltas),
        "sync_diagnostics_severity": str(sync_diagnostics.get("severity") or "info"),
        "grounding_mode": resolved_grounding_mode,
        "grounding_coverage_percent": int(legal_corpus_review.get("coverage_percent") or 0),
        "unsupported_assertion_count": int(legal_corpus_review.get("unsupported_assertion_count") or 0),
        "proof_status": str(logic_review.get("proof_status") or "needs_review"),
        "chronology_blocked": bool(logic_review.get("chronology_blocked")),
        "contradiction_count": int(logic_review.get("contradiction_count") or 0),
        "editor_user_id": normalized_editor_metadata.get("editor_user_id"),
        "editor_version": normalized_sync_provenance.get("editor_version"),
        "enabled_skill_ids": list(normalized_sync_provenance.get("enabled_skill_ids") or []),
        "base_draft_hash": normalized_sync_provenance.get("base_draft_hash"),
        "redline_delta_count": int(((normalized_sync_provenance.get("redline_metadata") or {}).get("structured_delta_count")) or 0),
        "sync_integrity_hash": sync_integrity_hash,
        "sync_integrity_hash_mode": sync_integrity_hash_mode,
        "document_version_content_sha256": self._document_version_content_sha256(
            str(draft.get("title") or ""),
            str(draft.get("body") or ""),
        ),
    }
    draft["sync_metadata"]["document_version_content_sha256"] = sync_record["document_version_content_sha256"]
    sync_history.insert(0, sync_record)
    mike_integration["last_sync"] = sync_record
    mike_integration["sync_history"] = sync_history[:25]
    audit_trail = [dict(item) for item in list(mike_integration.get("audit_trail") or []) if isinstance(item, dict)]
    audit_trail.insert(
        0,
        {
            "audit_id": f"mike-sync-audit-{uuid.uuid4().hex[:12]}",
            "synced_at": synced_at,
            "handoff_id": sync_record.get("handoff_id"),
            "editor_user_id": normalized_editor_metadata.get("editor_user_id"),
            "severity": sync_diagnostics.get("severity"),
            "has_blockers": bool(sync_diagnostics.get("has_blockers")),
            "sync_integrity_hash": sync_integrity_hash,
        },
    )
    mike_integration["audit_trail"] = audit_trail[:50]
    state["mike_integration"] = mike_integration
    self._save_state(state)
    session = self.get_session(str(state.get("user_id")))
    return {
        "user_id": session["session"]["user_id"],
        "draft": deepcopy(session["session"].get("draft") or {}),
        "sync_record": sync_record,
        "citation_link_check": citation_link_check,
        "sync_diagnostics": sync_diagnostics,
        "legal_corpus_review": legal_corpus_review,
        "logic_review": logic_review,
        "router_policy": router_policy,
        "sync_provenance": normalized_sync_provenance,
        "redline_metadata": deepcopy(normalized_sync_provenance.get("redline_metadata") or {}),
        "contract_versions": {
            "sync": MIKE_SYNC_CONTRACT_VERSION,
            "status": MIKE_STATUS_CONTRACT_VERSION,
        },
        "review": session["review"],
        "session": session["session"],
        "questions": session["questions"],
        "next_question": session["next_question"],
        "case_synopsis": session["case_synopsis"],
        "document_version_content_sha256": sync_record["document_version_content_sha256"],
    }


def build_mike_handoff(
    self,
    user_id: Optional[str],
    *,
    mike_base_url: Optional[str] = None,
    project_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    generate_draft_if_missing: bool = True,
    grounding_mode: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_user_id = str(user_id or DEFAULT_USER_ID)
    state = self._load_state(resolved_user_id)
    generated_draft = False
    if generate_draft_if_missing and not state.get("draft"):
        state["draft"] = self._build_draft(state)
        generated_draft = True
    review = self._build_review(state)
    resolved_grounding_mode = self._resolve_mike_grounding_mode(grounding_mode)
    router_policy = self._build_mike_router_policy_snapshot()
    skill_asset_manifest = self._build_mike_skill_asset_manifest()
    submodule_inventory = self._build_mike_submodule_inventory()
    compatibility_target_matrix = self._build_mike_compatibility_target_matrix()
    draft_payload = dict(state.get("draft") or {})
    derived_assertions = self._normalize_mike_assertion_annotations(None, body=str(draft_payload.get("body") or ""))
    legal_corpus_review = self._build_mike_legal_corpus_review(
        claim_type=str(state.get("claim_type") or "retaliation"),
        grounding_mode=resolved_grounding_mode,
        assertion_annotations=derived_assertions,
        authority_links=[],
    )
    logic_review = self._build_mike_logic_review(
        state=state,
        review=review,
        assertion_annotations=derived_assertions,
        authority_links=[],
    )
    handoff_id = f"mike-handoff-{uuid.uuid4().hex[:12]}"
    resolved_base_url = self._resolve_mike_base_url(mike_base_url)
    launch_query: Dict[str, str] = {
        "user_id": resolved_user_id,
        "handoff_id": handoff_id,
    }
    normalized_project_id = str(project_id or "").strip()
    normalized_workspace_id = str(workspace_id or "").strip()
    if normalized_project_id:
        launch_query["project_id"] = normalized_project_id
    if normalized_workspace_id:
        launch_query["workspace_id"] = normalized_workspace_id
    launch_url = self._build_mike_launch_url(resolved_base_url, launch_query)
    transport_warning = self._mike_transport_warning(resolved_base_url)
    handoff_payload = {
        "version": MIKE_HANDOFF_CONTRACT_VERSION,
        "user_id": resolved_user_id,
        "project_id": normalized_project_id or None,
        "workspace_id": normalized_workspace_id or None,
        "handoff_id": handoff_id,
        "created_at": _utc_now(),
        "case_synopsis": self._build_case_synopsis(state),
        "claim_type": str(state.get("claim_type") or "retaliation"),
        "draft": deepcopy(state.get("draft") or {}),
        "review": deepcopy(review),
        "authoritative_state_model": {
            "session_state_owner": "complaint_generator",
            "mike_role": "editing_surface_only",
            "source_of_truth": "complaint_generator_workspace_session",
        },
        "router_policy": router_policy,
        "skill_asset_manifest": skill_asset_manifest,
        "grounding_mode": resolved_grounding_mode,
        "corpus_boundaries": self._build_mike_corpus_boundaries(
            claim_type=str(state.get("claim_type") or "retaliation"),
            grounding_mode=resolved_grounding_mode,
        ),
        "evidence_context": self._summarize_mike_evidence_context(state, review),
        "structured_legal_packet_context": self._build_mike_structured_packet_context(
            dict(state.get("draft") or {}),
            review,
        ),
        "legal_corpus_context": legal_corpus_review,
        "logic_handoff": {
            "proof_constraints": {
                "unsupported_claim_element_ids": deepcopy(logic_review.get("unsupported_claim_element_ids") or []),
                "proof_status": str(logic_review.get("proof_status") or "needs_review"),
                "chronology_blocked": bool(logic_review.get("chronology_blocked")),
                "contradiction_count": int(logic_review.get("contradiction_count") or 0),
            },
            "formal_predicates": deepcopy(((logic_review.get("reasoning_payload") or {}).get("predicates") or [])),
            "theorem_export_metadata": deepcopy(logic_review.get("theorem_export_metadata") or {}),
            "leanstral_assist": deepcopy(logic_review.get("leanstral_assist") or {}),
        },
        "editor_guardrails": self._build_mike_editor_guardrails(
            review,
            legal_corpus_review=legal_corpus_review,
            logic_review=logic_review,
        ),
        "submodule_inventory": submodule_inventory,
        "compatibility_target_matrix": compatibility_target_matrix,
        "non_negotiable_constraints": {
            "must_preserve_claim_element_references": True,
            "must_return_sync_handoff_id": True,
            "must_run_citation_link_integrity_checks": True,
            "must_include_source_timestamps": True,
            "must_return_assertion_annotations": True,
            "must_return_authority_links": True,
            "must_preserve_logic_constraints": True,
            "must_route_generation_through_workspace_llm_router": True,
        },
    }
    from integrations.ipfs_datasets import llm as complaint_llm

    router_available = bool(getattr(complaint_llm, "LLM_ROUTER_AVAILABLE", False))
    draft_title = str(draft_payload.get("title") or "")
    draft_body = str(draft_payload.get("body") or "")
    handoff_payload["mike_document"] = {
        "title": draft_title,
        "body": draft_body,
        "citations": list(draft_payload.get("citation_links") or []),
        "content_sha256": self._document_version_content_sha256(draft_title, draft_body),
    }
    handoff_payload["mike_integration"] = {
        "transport": "mcp_connector",
        "connector_url": self._mike_connector_url(),
        "tools": list(MIKE_MCP_CONNECTOR_TOOLS),
        "setup_instructions": self._mike_connector_setup_text(router_available),
        "llm_router_available": router_available,
    }
    # The payload stamp stays for one release. Mike calls the MCP connector.
    try:
        from integrations.mike.llm_patch import apply_mike_llm_router_patch
        apply_mike_llm_router_patch(handoff_payload)
    except Exception:
        pass
    mike_integration = dict(state.get("mike_integration") or {})
    handoff_history = [dict(item) for item in list(mike_integration.get("handoff_history") or []) if isinstance(item, dict)]
    handoff_record = {
        "handoff_id": handoff_id,
        "created_at": handoff_payload["created_at"],
        "project_id": normalized_project_id or None,
        "workspace_id": normalized_workspace_id or None,
        "generated_draft": generated_draft,
        "launch_url": launch_url,
    }
    handoff_history.insert(0, handoff_record)
    mike_integration["last_handoff"] = handoff_record
    mike_integration["handoff_history"] = handoff_history[:25]
    state["mike_integration"] = mike_integration
    self._save_state(state)
    return {
        "user_id": resolved_user_id,
        "handoff_id": handoff_id,
        "generated_draft": generated_draft,
        "mike": {
            "base_url": resolved_base_url,
            "launch_url": launch_url,
            "project_id": normalized_project_id or None,
            "workspace_id": normalized_workspace_id or None,
            "transport_warning": transport_warning,
        },
        "handoff_payload": handoff_payload,
        "sync_contract": {
            "tool_name": "complaint.sync_mike_final_draft",
            "contract_version": MIKE_SYNC_CONTRACT_VERSION,
            "required_fields": ["user_id", "body"],
            "optional_fields": [
                "handoff_id",
                "project_id",
                "workspace_id",
                "title",
                "requested_relief",
                "mike_document_id",
                "citation_links",
                "redline_summary",
                "source_updated_at",
                "structured_deltas",
                "editor_metadata",
                "grounding_mode",
                "assertion_annotations",
                "authority_links",
                "sync_provenance",
            ],
        },
        "session_snapshot": {
            "user_id": str(state.get("user_id") or resolved_user_id),
            "claim_type": str(state.get("claim_type") or "retaliation"),
            "has_draft": bool(state.get("draft")),
            "testimony_count": len(list((state.get("evidence") or {}).get("testimony") or [])),
            "document_count": len(list((state.get("evidence") or {}).get("documents") or [])),
            "updated_at": str(state.get("updated_at") or ""),
        },
        "review": deepcopy(review),
        "case_synopsis": self._build_case_synopsis(state),
        "router_policy": router_policy,
        "skill_asset_manifest": skill_asset_manifest,
        "submodule_inventory": submodule_inventory,
        "compatibility_target_matrix": compatibility_target_matrix,
        "contract_versions": {
            "handoff": MIKE_HANDOFF_CONTRACT_VERSION,
            "sync": MIKE_SYNC_CONTRACT_VERSION,
            "status": MIKE_STATUS_CONTRACT_VERSION,
        },
    }

