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
                "availability": "mentioned_in_initial_complaint",
                "source_kind": "knowledge_graph_entity",
                "source_ref": entity.id,
            }
        )
    return proof_leads


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
    return {
        "candidate_claims": candidate_claims,
        "intake_sections": intake_sections,
        "canonical_facts": canonical_facts,
        "proof_leads": proof_leads,
        "contradiction_queue": [],
        "open_items": [],
        "summary_snapshots": [],
        "source_complaint_text": normalized_complaint_text,
    }


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
