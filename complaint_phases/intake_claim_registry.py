"""
Claim-type intake requirements for structured intake coverage.
"""

from __future__ import annotations

from typing import Any, Dict, List


CLAIM_INTAKE_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "employment_discrimination": {
        "label": "Employment Discrimination",
        "elements": [
            {
                "element_id": "protected_trait",
                "label": "Protected trait or class",
                "blocking": True,
                "keywords": ["race", "sex", "gender", "disability", "religion", "pregnan", "national origin", "age", "black", "white", "latino", "hispanic", "asian"],
                "fact_types": [],
            },
            {
                "element_id": "employment_relationship",
                "label": "Employment relationship or workplace context",
                "blocking": True,
                "keywords": ["employer", "job", "work", "workplace", "supervisor", "manager", "hr", "human resources", "coworker", "company"],
                "fact_types": ["responsible_party"],
            },
            {
                "element_id": "adverse_action",
                "label": "Adverse employment action or harassment",
                "blocking": True,
                "keywords": ["fired", "terminated", "demoted", "harass", "disciplined", "suspended", "cut hours", "reduced my hours", "promot"],
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
    "housing_discrimination": {
        "label": "Housing Discrimination",
        "elements": [
            {
                "element_id": "protected_trait",
                "label": "Protected trait or class",
                "blocking": True,
                "keywords": ["race", "sex", "gender", "disability", "religion", "familial status", "national origin", "age", "black", "white", "latino", "hispanic", "asian", "children", "pregnan"],
                "fact_types": [],
            },
            {
                "element_id": "housing_context",
                "label": "Housing relationship or tenancy context",
                "blocking": True,
                "keywords": ["landlord", "tenant", "lease", "apartment", "housing", "rent", "property manager", "evict", "unit"],
                "fact_types": ["responsible_party"],
            },
            {
                "element_id": "adverse_action",
                "label": "Discriminatory housing action",
                "blocking": True,
                "keywords": ["denied", "refused", "evict", "raised rent", "steered", "harass", "failed to repair"],
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
    "discrimination": {
        "label": "Discrimination",
        "elements": [
            {
                "element_id": "protected_trait",
                "label": "Protected trait or class",
                "blocking": True,
                "keywords": ["race", "sex", "gender", "disability", "religion", "pregnan", "national origin", "age", "black", "white", "latino", "hispanic", "asian"],
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
    "wrongful_termination": "termination",
    "fair_housing_discrimination": "housing_discrimination",
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
        tagged_present = any(
            str(element.get("element_id") or "").strip().lower() in {
                str(tag).strip().lower()
                for tag in (fact.get("element_tags") or [])
            }
            for fact in canonical_facts
            if isinstance(fact, dict)
        )
        present = tagged_present or any(keyword in combined_text for keyword in keywords) or _has_fact_type(canonical_facts, fact_types)
        required_elements.append(
            {
                "element_id": element.get("element_id"),
                "label": element.get("label"),
                "blocking": bool(element.get("blocking", False)),
                "status": "present" if present else "missing",
            }
        )
    return required_elements


def match_required_element_id(claim_type: Any, text: Any) -> str:
    registry = registry_for_claim_type(claim_type)
    normalized_text = str(text or "").strip().lower()
    if not normalized_text:
        return ""
    for element in registry.get("elements", []):
        element_id = str(element.get("element_id") or "").strip()
        label = str(element.get("label") or "").strip().lower()
        if not element_id:
            continue
        if element_id.lower() in normalized_text or label in normalized_text:
            return element_id
        label_terms = [term for term in label.replace("/", " ").split() if len(term) > 3]
        if label_terms and any(term in normalized_text for term in label_terms):
            return element_id
    return ""


def build_claim_element_question_text(claim_type: Any, claim_label: Any, element_id: Any, element_label: Any) -> str:
    normalized_claim_type = normalize_claim_type(claim_type)
    normalized_claim_label = str(claim_label or normalized_claim_type or "this claim").strip() or "this claim"
    normalized_element_id = str(element_id or "").strip().lower()
    normalized_element_label = str(element_label or normalized_element_id or "this missing element").strip()

    prompt_map = {
        ("employment_discrimination", "protected_trait"): (
            "For {claim_label}, what protected trait or class applies here, and how do you want it described?"
        ),
        ("employment_discrimination", "employment_relationship"): (
            "For {claim_label}, who was the employer or supervisor involved, and what was your workplace relationship to them?"
        ),
        ("employment_discrimination", "adverse_action"): (
            "For {claim_label}, what adverse job action or workplace harassment happened to you?"
        ),
        ("employment_discrimination", "discriminatory_motive"): (
            "For {claim_label}, what facts suggest the employer acted because of your protected trait, such as comments, unequal treatment, or timing?"
        ),
        ("housing_discrimination", "protected_trait"): (
            "For {claim_label}, what protected trait or class is involved, and how should it be described?"
        ),
        ("housing_discrimination", "housing_context"): (
            "For {claim_label}, who was the landlord, property manager, or housing provider, and what was your housing or tenancy situation?"
        ),
        ("housing_discrimination", "adverse_action"): (
            "For {claim_label}, what housing decision or treatment happened, such as a denial, eviction step, refusal, or unequal terms?"
        ),
        ("housing_discrimination", "discriminatory_motive"): (
            "For {claim_label}, what facts suggest the housing decision was because of your protected trait, such as statements, unequal treatment, or policy explanations?"
        ),
    }

    template = prompt_map.get((normalized_claim_type, normalized_element_id))
    if template:
        return template.format(claim_label=normalized_claim_label)
    return f"For {normalized_claim_label}, what facts show {normalized_element_label.lower()}?"


def build_proof_lead_question_text(claim_type: Any, claim_label: Any) -> str:
    normalized_claim_type = normalize_claim_type(claim_type)
    normalized_claim_label = str(claim_label or normalized_claim_type or "this claim").strip() or "this claim"

    prompt_map = {
        "employment_discrimination": (
            "For {claim_label}, what proof do you have, such as emails or texts, an HR complaint, a termination or discipline notice, witness names, or comparator records?"
        ),
        "housing_discrimination": (
            "For {claim_label}, what proof do you have, such as a lease, denial notice, accommodation request, landlord messages, inspection records, or witness names?"
        ),
        "retaliation": (
            "For {claim_label}, what proof do you have of the protected complaint and what happened after it, such as emails, reports, timing records, or witness names?"
        ),
        "accommodation": (
            "For {claim_label}, what proof do you have, such as an accommodation request, medical note, denial message, policy, or witness names?"
        ),
    }

    template = prompt_map.get(normalized_claim_type)
    if template:
        return template.format(claim_label=normalized_claim_label)
    return f"For {normalized_claim_label}, what documents, messages, witnesses, or other proof leads support your account?"
