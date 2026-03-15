"""
Claim-type intake requirements for structured intake coverage.
"""

from __future__ import annotations

from typing import Any, Dict, List


CLAIM_INTAKE_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "discrimination": {
        "label": "Discrimination",
        "elements": [
            {
                "element_id": "protected_trait",
                "label": "Protected trait or class",
                "blocking": True,
                "keywords": ["race", "sex", "gender", "disability", "religion", "pregnan", "national origin", "age"],
                "fact_types": [],
            },
            {
                "element_id": "adverse_action",
                "label": "Adverse action or discriminatory conduct",
                "blocking": True,
                "keywords": ["fired", "terminated", "demoted", "harass", "denied", "disciplined", "evict"],
                "fact_types": ["impact"],
            },
            {
                "element_id": "discriminatory_motive",
                "label": "Facts suggesting discriminatory motive",
                "blocking": True,
                "keywords": ["because of", "discrimination", "treated differently", "bias", "slur"],
                "fact_types": [],
            },
        ],
    },
    "retaliation": {
        "label": "Retaliation",
        "elements": [
            {
                "element_id": "protected_activity",
                "label": "Protected activity",
                "blocking": True,
                "keywords": ["complained", "reported", "requested accommodation", "opposed", "grievance", "hr"],
                "fact_types": [],
            },
            {
                "element_id": "adverse_action",
                "label": "Adverse action",
                "blocking": True,
                "keywords": ["fired", "terminated", "suspended", "cut hours", "evict", "retaliat"],
                "fact_types": ["impact"],
            },
            {
                "element_id": "causation",
                "label": "Timing or facts connecting activity to retaliation",
                "blocking": True,
                "keywords": ["after i complained", "after i reported", "shortly after", "because i reported"],
                "fact_types": ["timeline"],
            },
        ],
    },
    "accommodation": {
        "label": "Accommodation",
        "elements": [
            {
                "element_id": "accommodation_request",
                "label": "Accommodation request",
                "blocking": True,
                "keywords": ["accommodation", "requested", "asked for", "service animal", "modified"],
                "fact_types": [],
            },
            {
                "element_id": "disability_or_need",
                "label": "Disability or need for accommodation",
                "blocking": True,
                "keywords": ["disability", "medical", "mobility", "service animal", "wheelchair"],
                "fact_types": [],
            },
            {
                "element_id": "denial_or_failure",
                "label": "Denial or failure to accommodate",
                "blocking": True,
                "keywords": ["denied", "refused", "ignored", "failed to provide"],
                "fact_types": [],
            },
        ],
    },
    "denial": {
        "label": "Denial or Refusal",
        "elements": [
            {
                "element_id": "request_or_application",
                "label": "Request or application",
                "blocking": True,
                "keywords": ["applied", "application", "requested", "submitted"],
                "fact_types": [],
            },
            {
                "element_id": "denial_event",
                "label": "Denial event",
                "blocking": True,
                "keywords": ["denied", "refused", "rejected", "declined"],
                "fact_types": [],
            },
            {
                "element_id": "context_or_reason",
                "label": "Reason or surrounding context",
                "blocking": False,
                "keywords": ["because", "reason", "policy", "criteria"],
                "fact_types": [],
            },
        ],
    },
    "termination": {
        "label": "Termination",
        "elements": [
            {
                "element_id": "termination_event",
                "label": "Termination event",
                "blocking": True,
                "keywords": ["fired", "terminated", "let go", "dismissed"],
                "fact_types": ["impact"],
            },
            {
                "element_id": "responsible_actor",
                "label": "Responsible actor or employer",
                "blocking": True,
                "keywords": ["employer", "manager", "supervisor", "company", "landlord"],
                "fact_types": ["responsible_party"],
            },
            {
                "element_id": "timing_or_reason",
                "label": "Timing or stated reason",
                "blocking": False,
                "keywords": ["after", "because", "on", "date", "timeline"],
                "fact_types": ["timeline"],
            },
        ],
    },
}


CLAIM_TYPE_ALIASES = {
    "employment_discrimination": "discrimination",
    "wrongful_termination": "termination",
}


def normalize_claim_type(claim_type: Any) -> str:
    normalized = "".join(ch.lower() if str(ch).isalnum() else "_" for ch in str(claim_type or "")).strip("_")
    return CLAIM_TYPE_ALIASES.get(normalized, normalized or "unknown")


def registry_for_claim_type(claim_type: Any) -> Dict[str, Any]:
    normalized = normalize_claim_type(claim_type)
    return CLAIM_INTAKE_REQUIREMENTS.get(normalized, {"label": normalized.replace("_", " ").title(), "elements": []})


def _combined_case_text(candidate_claim: Dict[str, Any], canonical_facts: List[Dict[str, Any]], source_text: str) -> str:
    parts = [str(source_text or ""), str(candidate_claim.get("description") or ""), str(candidate_claim.get("label") or "")]
    for fact in canonical_facts:
        if isinstance(fact, dict):
            parts.append(str(fact.get("text") or ""))
    return " ".join(part for part in parts if part).lower()


def _has_fact_type(canonical_facts: List[Dict[str, Any]], fact_types: List[str]) -> bool:
    normalized_fact_types = {str(item or "").strip().lower() for item in fact_types if item}
    if not normalized_fact_types:
        return False
    for fact in canonical_facts:
        if not isinstance(fact, dict):
            continue
        if str(fact.get("fact_type") or "").strip().lower() in normalized_fact_types:
            return True
    return False


def refresh_required_elements(candidate_claim: Dict[str, Any], canonical_facts: List[Dict[str, Any]], source_text: str) -> List[Dict[str, Any]]:
    registry = registry_for_claim_type(candidate_claim.get("claim_type"))
    combined_text = _combined_case_text(candidate_claim, canonical_facts, source_text)
    required_elements: List[Dict[str, Any]] = []
    for element in registry.get("elements", []):
        keywords = [str(keyword).lower() for keyword in (element.get("keywords") or []) if keyword]
        fact_types = [str(fact_type).lower() for fact_type in (element.get("fact_types") or []) if fact_type]
        present = any(keyword in combined_text for keyword in keywords) or _has_fact_type(canonical_facts, fact_types)
        required_elements.append(
            {
                "element_id": element.get("element_id"),
                "label": element.get("label"),
                "blocking": bool(element.get("blocking", False)),
                "status": "present" if present else "missing",
            }
        )
    return required_elements
