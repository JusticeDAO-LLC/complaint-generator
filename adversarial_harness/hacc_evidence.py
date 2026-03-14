"""
HACC evidence-backed seed generation for the adversarial harness.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_hacc_engine() -> Any:
    repo_root = _repo_root()
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    from hacc_research.engine import HACCResearchEngine

    return HACCResearchEngine


DEFAULT_HACC_QUERY_SPECS: List[Dict[str, Any]] = [
    {
        "query": "proxy language DEI equity inclusion housing policy admissions occupancy tenant selection",
        "type": "housing_discrimination",
        "category": "housing",
        "description": "Housing complaint seeded from proxy-language evidence in HACC policy materials",
    },
    {
        "query": "preferential treatment protected class prioritization scoring preferences housing program admissions",
        "type": "civil_rights_violation",
        "category": "civil_rights",
        "description": "Preferential-treatment complaint grounded in HACC evidence",
    },
    {
        "query": "retaliation protections grievance complaint appeal hearing due process tenant policy adverse action",
        "type": "housing_discrimination",
        "category": "housing",
        "description": "Retaliation or grievance-process complaint grounded in HACC evidence",
    },
    {
        "query": "selection contracting procurement MWESB COBID vendor evaluation criteria equity policy",
        "type": "civil_rights_violation",
        "category": "civil_rights",
        "description": "Contracting or selection complaint seeded from HACC procurement evidence",
    },
    {
        "query": "third party funding monitoring reporting compliance equity requirements housing partner oversight",
        "type": "civil_rights_violation",
        "category": "civil_rights",
        "description": "Third-party monitoring complaint grounded in HACC evidence",
    },
    {
        "query": "training hostile environment DEI cultural competency bias staff training housing",
        "type": "civil_rights_violation",
        "category": "civil_rights",
        "description": "Training or hostile-environment complaint grounded in HACC evidence",
    },
]

HACC_QUERY_PRESETS: Dict[str, List[Dict[str, Any]]] = {
    "full_audit": DEFAULT_HACC_QUERY_SPECS,
    "housing_focus": [
        DEFAULT_HACC_QUERY_SPECS[0],
        DEFAULT_HACC_QUERY_SPECS[2],
    ],
    "proxy_focus": [
        DEFAULT_HACC_QUERY_SPECS[0],
        {
            "query": "accessibility equitable inclusive fair housing policy requirements tenant services",
            "type": "housing_discrimination",
            "category": "housing",
            "description": "Housing complaint focused on accessibility and proxy-language obligations",
        },
    ],
    "retaliation_focus": [
        DEFAULT_HACC_QUERY_SPECS[2],
        {
            "query": "complaint grievance retaliation adverse action hearing informal review housing authority",
            "type": "housing_discrimination",
            "category": "housing",
            "description": "Retaliation complaint focused on grievance handling and post-complaint conduct",
        },
    ],
    "contracting_focus": [
        DEFAULT_HACC_QUERY_SPECS[1],
        DEFAULT_HACC_QUERY_SPECS[3],
        DEFAULT_HACC_QUERY_SPECS[4],
    ],
}


def get_hacc_query_specs(
    *,
    preset: Optional[str] = None,
    query_specs: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    if query_specs is not None:
        return list(query_specs)
    if preset:
        return list(HACC_QUERY_PRESETS.get(preset, DEFAULT_HACC_QUERY_SPECS))
    return list(DEFAULT_HACC_QUERY_SPECS)


def _summarize_hit(hit: Dict[str, Any], max_snippet_chars: int = 240) -> Dict[str, Any]:
    snippet = str(hit.get("snippet") or "").strip()
    return {
        "document_id": str(hit.get("document_id") or ""),
        "title": str(hit.get("title") or ""),
        "source_type": str(hit.get("source_type") or ""),
        "source_path": str(hit.get("source_path") or ""),
        "score": float(hit.get("score") or 0.0),
        "snippet": snippet[:max_snippet_chars],
        "matched_rules": list(hit.get("matched_rules") or []),
        "matched_entities": list(hit.get("matched_entities") or []),
        "metadata": dict(hit.get("metadata") or {}),
    }


def build_hacc_evidence_seed(
    search_payload: Dict[str, Any],
    *,
    query: str,
    complaint_type: str,
    category: str,
    description: str,
) -> Optional[Dict[str, Any]]:
    hits = [_summarize_hit(hit) for hit in list(search_payload.get("results", []) or [])]
    if not hits:
        return None

    lead = hits[0]
    evidence_summary = " ".join(
        part
        for part in [
            f"The strongest supporting material is '{lead['title']}'." if lead.get("title") else "",
            lead.get("snippet", ""),
        ]
        if part
    ).strip()
    source_paths = [hit["source_path"] for hit in hits if hit.get("source_path")]
    evidence_titles = [hit["title"] for hit in hits if hit.get("title")]

    return {
        "template_id": f"hacc::{complaint_type}::{query[:40]}",
        "type": complaint_type,
        "category": category,
        "description": description,
        "summary": evidence_summary or description,
        "key_facts": {
            "incident_summary": description,
            "evidence_query": query,
            "evidence_summary": evidence_summary,
            "evidence_documents": evidence_titles,
            "source_paths": source_paths,
            "grounding_note": "Use the evidence as factual grounding and identify missing case-specific facts during questioning.",
        },
        "keywords": [],
        "legal_patterns": [],
        "hacc_evidence": hits,
        "source": "hacc_research_engine",
    }


def build_hacc_evidence_seeds(
    *,
    count: int = 5,
    preset: Optional[str] = None,
    query_specs: Optional[Sequence[Dict[str, Any]]] = None,
    repo_root: Optional[str | Path] = None,
    use_vector: bool = False,
    search_top_k: int = 3,
) -> List[Dict[str, Any]]:
    try:
        engine_cls = _load_hacc_engine()
        engine = engine_cls(repo_root=repo_root) if repo_root else engine_cls()
    except Exception as exc:
        logger.warning("Unable to initialize HACCResearchEngine for seed generation: %s", exc)
        return []

    specs = get_hacc_query_specs(preset=preset, query_specs=query_specs)
    seeds: List[Dict[str, Any]] = []
    for spec in specs:
        payload = engine.search(
            str(spec.get("query") or ""),
            top_k=search_top_k,
            use_vector=use_vector,
        )
        seed = build_hacc_evidence_seed(
            payload,
            query=str(spec.get("query") or ""),
            complaint_type=str(spec.get("type") or "civil_rights_violation"),
            category=str(spec.get("category") or "civil_rights"),
            description=str(spec.get("description") or "Evidence-backed complaint seed from HACC corpus"),
        )
        if seed:
            seeds.append(seed)
        if len(seeds) >= count:
            break
    return seeds[:count]
