"""
Helpers for building and summarizing the structured intake case file.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .intake_claim_registry import normalize_claim_type, refresh_required_elements, registry_for_claim_type


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _status(has_value: bool) -> str:
    return "complete" if has_value else "missing"


def _coerce_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _coerce_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _contradiction_support_kind(resolution_lane: str) -> str:
    normalized = _normalize_text(resolution_lane).lower()
    if normalized == "capture_testimony":
        return "testimony"
    if normalized in {"request_document", "seek_external_record"}:
        return "evidence"
    if normalized == "manual_review":
        return "manual_review"
    return "intake_clarification"


def _derive_expected_format(lead_type: str) -> str:
    normalized = _normalize_text(lead_type).lower()
    if "email" in normalized:
        return "email"
    if "text" in normalized or "message" in normalized:
        return "message export"
    if "photo" in normalized or "image" in normalized or "picture" in normalized:
        return "image"
    if "witness" in normalized:
        return "testimony"
    if "letter" in normalized or "notice" in normalized:
        return "document"
    return "document or testimony"


def _derive_retrieval_path(lead_type: str) -> str:
    normalized = _normalize_text(lead_type).lower()
    if "email" in normalized:
        return "complainant_email_account"
    if "text" in normalized or "message" in normalized:
        return "complainant_mobile_device"
    if "witness" in normalized:
        return "witness_follow_up"
    if "photo" in normalized or "image" in normalized:
        return "complainant_device_gallery"
    return "complainant_possession"


def _derive_lead_priority(lead_type: str) -> str:
    normalized = _normalize_text(lead_type).lower()
    if any(token in normalized for token in ("termination", "notice", "email", "text", "message", "letter")):
        return "high"
    if "witness" in normalized:
        return "medium"
    return "medium"


def build_candidate_claims(knowledge_graph) -> List[Dict[str, Any]]:
    """Build initial candidate claim records from claim entities."""
    if knowledge_graph is None:
        return []

    candidates: List[Dict[str, Any]] = []
    for entity in knowledge_graph.get_entities_by_type("claim"):
        claim_type = normalize_claim_type(entity.attributes.get("claim_type") or "unknown")
        registry = registry_for_claim_type(claim_type)
        candidates.append(
            {
                "claim_id": entity.id,
                "claim_type": claim_type,
                "label": _normalize_text(entity.name or registry.get("label") or claim_type.replace("_", " ").title()),
                "description": _normalize_text(entity.attributes.get("description") or entity.name),
                "confidence": float(entity.confidence),
                "source": entity.source,
                "required_elements": [],
            }
        )
    return candidates


def build_canonical_facts(knowledge_graph) -> List[Dict[str, Any]]:
    """Build initial canonical facts from fact entities already extracted into the graph."""
    if knowledge_graph is None:
        return []

    canonical_facts: List[Dict[str, Any]] = []
    for entity in knowledge_graph.get_entities_by_type("fact"):
        fact_text = _normalize_text(entity.attributes.get("description") or entity.name)
        if not fact_text:
            continue
        canonical_facts.append(
            {
                "fact_id": entity.id,
                "text": fact_text,
                "fact_type": _normalize_text(entity.attributes.get("fact_type") or "general").lower() or "general",
                "claim_types": [],
                "element_tags": [],
                "event_date_or_range": None,
                "actor_ids": [],
                "target_ids": [],
                "location": None,
                "source_kind": "knowledge_graph_entity",
                "source_ref": entity.id,
                "confidence": float(entity.confidence),
                "status": "accepted",
                "needs_corroboration": entity.confidence < 0.85,
                "corroboration_priority": "high" if entity.confidence < 0.7 else "medium",
                "materiality": "medium",
                "fact_participants": {},
                "contradiction_group_id": None,
            }
        )
    return canonical_facts


def build_proof_leads(knowledge_graph) -> List[Dict[str, Any]]:
    """Build initial proof leads from evidence entities already extracted into the graph."""
    if knowledge_graph is None:
        return []

    proof_leads: List[Dict[str, Any]] = []
    for entity in knowledge_graph.get_entities_by_type("evidence"):
        description = _normalize_text(entity.attributes.get("description") or entity.name)
        evidence_type = _normalize_text(entity.attributes.get("evidence_type") or entity.name).lower() or "evidence"
        proof_leads.append(
            {
                "lead_id": entity.id,
                "lead_type": evidence_type,
                "description": description,
                "related_fact_ids": [],
                "fact_targets": [],
                "element_targets": [],
                "availability": "mentioned_in_initial_complaint",
                "availability_details": "Referenced in initial complaint narrative",
                "owner": "complainant",
                "custodian": "complainant",
                "expected_format": _derive_expected_format(evidence_type),
                "retrieval_path": _derive_retrieval_path(evidence_type),
                "authenticity_risk": "unknown",
                "privacy_risk": "review_required",
                "priority": _derive_lead_priority(evidence_type),
                "recommended_support_kind": "testimony" if "witness" in evidence_type else "evidence",
                "source_quality_target": "credible" if "witness" in evidence_type else "high_quality_document",
                "acquisition_notes": "Needs complainant confirmation and collection path review",
                "source_kind": "knowledge_graph_entity",
                "source_ref": entity.id,
            }
        )
    return proof_leads


def build_open_items(intake_case_file: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the unresolved-work queue for the current intake record."""
    case_file = _coerce_dict(intake_case_file)
    sections = _coerce_dict(case_file.get("intake_sections"))
    candidate_claims = _coerce_list(case_file.get("candidate_claims"))
    contradiction_queue = _coerce_list(case_file.get("contradiction_queue"))
    open_items: List[Dict[str, Any]] = []

    for section_name, section in sections.items():
        section_dict = _coerce_dict(section)
        status = _normalize_text(section_dict.get("status")).lower() or "missing"
        if status == "complete":
            continue
        open_items.append(
            {
                "open_item_id": f"section:{section_name}",
                "kind": "section_gap",
                "status": "open",
                "blocking_level": "blocking" if section_name in {"chronology", "actors", "conduct", "claim_elements"} else "important",
                "section": section_name,
                "reason": "; ".join(_coerce_list(section_dict.get("missing_items"))) or f"{section_name} is incomplete",
                "target_claim_type": "",
                "target_element_id": "",
                "next_question_strategy": f"fill_{section_name}",
                "recommended_support_kind": "evidence" if section_name == "proof_leads" else "intake_clarification",
                "proof_path_status": "missing",
            }
        )

    for claim in candidate_claims:
        claim_dict = _coerce_dict(claim)
        claim_type = _normalize_text(claim_dict.get("claim_type"))
        claim_label = _normalize_text(claim_dict.get("label") or claim_type)
        for element in _coerce_list(claim_dict.get("required_elements")):
            element_dict = _coerce_dict(element)
            if _normalize_text(element_dict.get("status")).lower() == "present":
                continue
            element_id = _normalize_text(element_dict.get("element_id"))
            element_label = _normalize_text(element_dict.get("label") or element_id)
            open_items.append(
                {
                    "open_item_id": f"element:{claim_type}:{element_id}",
                    "kind": "claim_element_gap",
                    "status": "open",
                    "blocking_level": "blocking" if bool(element_dict.get("blocking", False)) else "important",
                    "section": "claim_elements",
                    "reason": f"{claim_label} is still missing {element_label}.",
                    "target_claim_type": claim_type,
                    "target_element_id": element_id,
                    "next_question_strategy": "satisfy_claim_element",
                    "evidence_classes": list(element_dict.get("evidence_classes", []) or []),
                    "recommended_support_kind": "testimony" if any("testimony" in str(item).lower() for item in (element_dict.get("evidence_classes", []) or [])) else "evidence",
                    "proof_path_status": "missing",
                }
            )

    for contradiction in contradiction_queue:
        contradiction_dict = _coerce_dict(contradiction)
        if _normalize_text(contradiction_dict.get("status") or "open").lower() == "resolved":
            continue
        contradiction_id = _normalize_text(contradiction_dict.get("contradiction_id") or "contradiction")
        topic = _normalize_text(contradiction_dict.get("topic") or "intake contradiction")
        resolution_lane = _normalize_text(
            contradiction_dict.get("recommended_resolution_lane") or "clarify_with_complainant"
        ).lower() or "clarify_with_complainant"
        external_corroboration_required = bool(
            contradiction_dict.get("external_corroboration_required", False)
        )
        open_items.append(
            {
                "open_item_id": f"contradiction:{contradiction_id}",
                "kind": "contradiction",
                "status": "open",
                "blocking_level": _normalize_text(contradiction_dict.get("severity") or "important").lower() or "important",
                "section": "contradictions",
                "reason": f"Resolve contradiction about {topic}.",
                "target_claim_type": "",
                "target_element_id": "",
                "next_question_strategy": resolution_lane,
                "recommended_support_kind": _contradiction_support_kind(resolution_lane),
                "recommended_resolution_lane": resolution_lane,
                "external_corroboration_required": external_corroboration_required,
                "proof_path_status": "conflicted_external_corroboration_required" if external_corroboration_required else "conflicted",
            }
        )

    seen_ids = set()
    deduped_items: List[Dict[str, Any]] = []
    for item in open_items:
        item_id = _normalize_text(item.get("open_item_id"))
        if not item_id or item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        deduped_items.append(item)
    return deduped_items


def build_summary_snapshot(intake_case_file: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact summary snapshot for the current intake record."""
    case_file = _coerce_dict(intake_case_file)
    candidate_claims = _coerce_list(case_file.get("candidate_claims"))
    canonical_facts = _coerce_list(case_file.get("canonical_facts"))
    proof_leads = _coerce_list(case_file.get("proof_leads"))
    timeline_anchors = _coerce_list(case_file.get("timeline_anchors"))
    open_items = _coerce_list(case_file.get("open_items"))
    contradiction_queue = _coerce_list(case_file.get("contradiction_queue"))
    harm_profile = _coerce_dict(case_file.get("harm_profile"))
    remedy_profile = _coerce_dict(case_file.get("remedy_profile"))
    sections = _coerce_dict(case_file.get("intake_sections"))
    unresolved_contradictions = [
        item for item in contradiction_queue
        if isinstance(item, dict) and _normalize_text(item.get("status") or "open").lower() != "resolved"
    ]
    return {
        "candidate_claim_count": len(candidate_claims),
        "canonical_fact_count": len(canonical_facts),
        "proof_lead_count": len(proof_leads),
        "timeline_anchor_count": len(timeline_anchors),
        "open_item_count": len(open_items),
        "unresolved_contradiction_count": len(unresolved_contradictions),
        "harm_category_count": len(_coerce_list(harm_profile.get("categories"))),
        "remedy_category_count": len(_coerce_list(remedy_profile.get("categories"))),
        "section_statuses": {
            name: _normalize_text(_coerce_dict(section).get("status") or "missing").lower() or "missing"
            for name, section in sections.items()
        },
    }


def build_timeline_anchors(canonical_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    anchors: List[Dict[str, Any]] = []
    seen_keys = set()
    for fact in canonical_facts if isinstance(canonical_facts, list) else []:
        if not isinstance(fact, dict):
            continue
        fact_type = _normalize_text(fact.get("fact_type") or "").lower()
        event_date = _normalize_text(fact.get("event_date_or_range") or "")
        if fact_type != "timeline" and not event_date:
            continue
        anchor_text = event_date or _normalize_text(fact.get("text") or "")
        if not anchor_text:
            continue
        key = (anchor_text.lower(), _normalize_text(fact.get("location") or "").lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        anchors.append(
            {
                "anchor_id": f"timeline_anchor_{len(anchors) + 1:03d}",
                "fact_id": _normalize_text(fact.get("fact_id") or ""),
                "anchor_text": anchor_text,
                "location": _normalize_text(fact.get("location") or "") or None,
                "fact_type": fact_type or "timeline",
            }
        )
    return anchors


def _classify_harm_text(text: str) -> List[str]:
    normalized = _normalize_text(text).lower()
    categories: List[str] = []
    if any(token in normalized for token in ("wages", "salary", "pay", "income", "money", "rent", "cost")):
        categories.append("economic")
    if any(token in normalized for token in ("job", "career", "promotion", "termination", "fired", "discipline")):
        categories.append("professional")
    if any(token in normalized for token in ("stress", "anxiety", "humiliation", "emotional", "distress")):
        categories.append("emotional")
    if any(token in normalized for token in ("injury", "pain", "medical", "hospital", "physical")):
        categories.append("physical")
    if any(token in normalized for token in ("process", "hearing", "appeal", "complaint handling", "procedure")):
        categories.append("procedural")
    return categories or ["general"]


def build_harm_profile(canonical_facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    impact_facts = [
        fact for fact in (canonical_facts if isinstance(canonical_facts, list) else [])
        if isinstance(fact, dict) and _normalize_text(fact.get("fact_type") or "").lower() == "impact"
    ]
    categories: List[str] = []
    for fact in impact_facts:
        for category in _classify_harm_text(_normalize_text(fact.get("text") or "")):
            if category not in categories:
                categories.append(category)
    return {
        "count": len(impact_facts),
        "categories": categories,
        "fact_ids": [
            _normalize_text(fact.get("fact_id") or "")
            for fact in impact_facts
            if _normalize_text(fact.get("fact_id") or "")
        ],
    }


def _classify_remedy_text(text: str) -> List[str]:
    normalized = _normalize_text(text).lower()
    categories: List[str] = []
    if any(token in normalized for token in ("damages", "compensation", "money", "lost wages", "refund")):
        categories.append("monetary")
    if any(token in normalized for token in ("reinstatement", "job back", "return to work")):
        categories.append("reinstatement")
    if any(token in normalized for token in ("injunction", "stop", "prevent", "order")):
        categories.append("injunctive")
    if any(token in normalized for token in ("correct", "records", "expunge", "remove discipline")):
        categories.append("records_correction")
    if any(token in normalized for token in ("declare", "declaratory", "finding")):
        categories.append("declaratory")
    return categories or ["general"]


def build_remedy_profile(canonical_facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    remedy_facts = [
        fact for fact in (canonical_facts if isinstance(canonical_facts, list) else [])
        if isinstance(fact, dict) and _normalize_text(fact.get("fact_type") or "").lower() == "remedy"
    ]
    categories: List[str] = []
    for fact in remedy_facts:
        for category in _classify_remedy_text(_normalize_text(fact.get("text") or "")):
            if category not in categories:
                categories.append(category)
    return {
        "count": len(remedy_facts),
        "categories": categories,
        "fact_ids": [
            _normalize_text(fact.get("fact_id") or "")
            for fact in remedy_facts
            if _normalize_text(fact.get("fact_id") or "")
        ],
    }


def build_intake_sections(
    knowledge_graph,
    *,
    candidate_claims: List[Dict[str, Any]],
    canonical_facts: List[Dict[str, Any]],
    proof_leads: List[Dict[str, Any]],
    source_text: str = "",
) -> Dict[str, Dict[str, Any]]:
    """Build a lightweight first-pass section coverage snapshot."""
    has_dates = False
    has_people = False
    has_organizations = False
    if knowledge_graph is not None:
        has_dates = bool(knowledge_graph.get_entities_by_type("date"))
        has_people = bool(knowledge_graph.get_entities_by_type("person"))
        has_organizations = bool(knowledge_graph.get_entities_by_type("organization"))

    has_impact = any(fact.get("fact_type") == "impact" for fact in canonical_facts)
    has_remedy = any(fact.get("fact_type") == "remedy" for fact in canonical_facts)
    missing_claim_elements: List[str] = []
    claim_elements_present = False
    for claim in candidate_claims:
        if not isinstance(claim, dict):
            continue
        required_elements = refresh_required_elements(claim, canonical_facts, source_text)
        claim["required_elements"] = required_elements
        if required_elements:
            if any(str(element.get("status") or "").strip().lower() == "present" for element in required_elements):
                claim_elements_present = True
            for element in required_elements:
                if str(element.get("status") or "").strip().lower() != "present":
                    label = _normalize_text(element.get("label") or element.get("element_id"))
                    if label and label not in missing_claim_elements:
                        missing_claim_elements.append(label)

    return {
        "chronology": {
            "status": _status(has_dates),
            "missing_items": [] if has_dates else ["event dates or timeline anchors"],
        },
        "actors": {
            "status": _status(has_people or has_organizations),
            "missing_items": [] if (has_people or has_organizations) else ["people or organizations involved"],
        },
        "conduct": {
            "status": _status(bool(candidate_claims)),
            "missing_items": [] if candidate_claims else ["core alleged conduct"],
        },
        "harm": {
            "status": _status(has_impact),
            "missing_items": [] if has_impact else ["harm suffered"],
        },
        "remedy": {
            "status": _status(has_remedy),
            "missing_items": [] if has_remedy else ["requested outcome or remedy"],
        },
        "proof_leads": {
            "status": _status(bool(proof_leads)),
            "missing_items": [] if proof_leads else ["documents, witnesses, or other supporting proof leads"],
        },
        "claim_elements": {
            "status": "complete" if candidate_claims and not missing_claim_elements else ("partial" if claim_elements_present else "missing"),
            "missing_items": missing_claim_elements if missing_claim_elements else [],
        },
    }


def build_intake_case_file(knowledge_graph, complaint_text: str = "") -> Dict[str, Any]:
    """Build the initial structured intake case file from current graph state."""
    candidate_claims = build_candidate_claims(knowledge_graph)
    canonical_facts = build_canonical_facts(knowledge_graph)
    proof_leads = build_proof_leads(knowledge_graph)
    intake_sections = build_intake_sections(
        knowledge_graph,
        candidate_claims=candidate_claims,
        canonical_facts=canonical_facts,
        proof_leads=proof_leads,
        source_text=complaint_text,
    )

    normalized_complaint_text = _normalize_text(complaint_text)
    intake_case_file = {
        "candidate_claims": candidate_claims,
        "intake_sections": intake_sections,
        "canonical_facts": canonical_facts,
        "timeline_anchors": build_timeline_anchors(canonical_facts),
        "harm_profile": build_harm_profile(canonical_facts),
        "remedy_profile": build_remedy_profile(canonical_facts),
        "proof_leads": proof_leads,
        "contradiction_queue": [],
        "open_items": [],
        "summary_snapshots": [],
        "source_complaint_text": normalized_complaint_text,
    }
    intake_case_file["open_items"] = build_open_items(intake_case_file)
    intake_case_file["summary_snapshots"] = [build_summary_snapshot(intake_case_file)]
    return intake_case_file


def refresh_intake_sections(intake_case_file: Dict[str, Any], knowledge_graph) -> Dict[str, Dict[str, Any]]:
    """Recompute section coverage from the latest structured intake state."""
    candidate_claims = intake_case_file.get("candidate_claims", [])
    canonical_facts = intake_case_file.get("canonical_facts", [])
    proof_leads = intake_case_file.get("proof_leads", [])
    source_text = intake_case_file.get("source_complaint_text", "")
    return build_intake_sections(
        knowledge_graph,
        candidate_claims=candidate_claims if isinstance(candidate_claims, list) else [],
        canonical_facts=canonical_facts if isinstance(canonical_facts, list) else [],
        proof_leads=proof_leads if isinstance(proof_leads, list) else [],
        source_text=str(source_text or ""),
    )


def refresh_intake_case_file(intake_case_file: Dict[str, Any], knowledge_graph, *, append_snapshot: bool = False) -> Dict[str, Any]:
    """Refresh derived intake sections, open items, and summary snapshots."""
    case_file = _coerce_dict(intake_case_file)
    case_file["intake_sections"] = refresh_intake_sections(case_file, knowledge_graph)
    case_file["timeline_anchors"] = build_timeline_anchors(_coerce_list(case_file.get("canonical_facts")))
    case_file["harm_profile"] = build_harm_profile(_coerce_list(case_file.get("canonical_facts")))
    case_file["remedy_profile"] = build_remedy_profile(_coerce_list(case_file.get("canonical_facts")))
    case_file["open_items"] = build_open_items(case_file)

    summary_snapshots = _coerce_list(case_file.get("summary_snapshots"))
    snapshot = build_summary_snapshot(case_file)
    if append_snapshot:
        if not summary_snapshots or summary_snapshots[-1] != snapshot:
            summary_snapshots.append(snapshot)
    elif not summary_snapshots:
        summary_snapshots.append(snapshot)
    else:
        summary_snapshots[-1] = snapshot
    case_file["summary_snapshots"] = summary_snapshots
    return case_file
