"""
HACC evidence-backed seed generation for the adversarial harness.
"""

from __future__ import annotations

import logging
import re
import importlib
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)
_ENGINE_CACHE: Dict[str, Any] = {}


ANCHOR_SECTION_PATTERNS: Dict[str, Sequence[str]] = {
    "grievance_hearing": (
        "grievance hearing",
        "informal hearing",
        "impartial person",
        "hearing process",
        "hearing procedures",
        "request a grievance hearing",
    ),
    "appeal_rights": (
        "appeal",
        "review",
        "right to appeal",
        "right to request",
        "due process",
        "due process rights",
        "final decision",
        "written notice",
    ),
    "reasonable_accommodation": ("reasonable accommodation", "person with a disability", "disability", "accommodation"),
    "adverse_action": (
        "termination",
        "termination decision",
        "denial",
        "adverse action",
        "admission",
        "occupancy",
        "terminate assistance",
        "discontinued",
        "notice of adverse action",
    ),
    "selection_criteria": ("selection", "screening", "criteria", "evaluation", "prioritization"),
}

ANCHOR_SECTION_HINT_TERMS: Dict[str, Sequence[str]] = {
    "grievance_hearing": ("grievance", "hearing", "informal hearing", "impartial person"),
    "appeal_rights": ("appeal", "review", "due process", "written notice", "right to appeal"),
    "reasonable_accommodation": ("reasonable accommodation", "accommodation", "disability"),
    "adverse_action": ("adverse action", "denial", "termination", "terminate assistance", "notice of adverse action"),
    "selection_criteria": ("selection", "screening", "criteria", "evaluation", "prioritization"),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_hacc_engine() -> Any:
    repo_root = _repo_root()
    engine_path = repo_root / "hacc_research" / "engine.py"
    if not engine_path.exists():
        raise ModuleNotFoundError(f"HACCResearchEngine not found at {engine_path}")

    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    module = importlib.import_module("hacc_research")
    return getattr(module, "HACCResearchEngine")


def _get_hacc_engine_instance(repo_root: Optional[str | Path] = None) -> Any:
    cache_key = str(Path(repo_root).resolve()) if repo_root else "default"
    if cache_key not in _ENGINE_CACHE:
        engine_cls = _load_hacc_engine()
        _ENGINE_CACHE[cache_key] = engine_cls(repo_root=repo_root) if repo_root else engine_cls()
    return _ENGINE_CACHE[cache_key]


DEFAULT_HACC_QUERY_SPECS: List[Dict[str, Any]] = [
    {
        "query": "proxy language DEI equity inclusion housing policy admissions occupancy tenant selection",
        "type": "housing_discrimination",
        "category": "housing",
        "description": "Housing complaint seeded from proxy-language evidence in HACC policy materials",
        "theory_labels": ["disparate_treatment", "proxy_discrimination"],
        "authority_hints": ["Fair Housing Act, 42 U.S.C. 3604", "24 C.F.R. Part 100"],
    },
    {
        "query": "preferential treatment protected class prioritization scoring preferences housing program admissions",
        "type": "civil_rights_violation",
        "category": "civil_rights",
        "description": "Preferential-treatment complaint grounded in HACC evidence",
        "theory_labels": ["disparate_treatment", "protected_class_preferences"],
        "authority_hints": ["Fair Housing Act, 42 U.S.C. 3604", "24 C.F.R. Part 100"],
    },
    {
        "query": "retaliation protections grievance complaint appeal hearing due process tenant policy adverse action",
        "type": "housing_discrimination",
        "category": "housing",
        "description": "Retaliation or grievance-process complaint grounded in HACC evidence",
        "theory_labels": ["retaliation", "due_process_failure"],
        "authority_hints": ["Fair Housing Act anti-retaliation provisions", "24 C.F.R. Part 100"],
    },
    {
        "query": "selection contracting procurement MWESB COBID vendor evaluation criteria equity policy",
        "type": "civil_rights_violation",
        "category": "civil_rights",
        "description": "Contracting or selection complaint seeded from HACC procurement evidence",
        "theory_labels": ["selection_criteria", "preferential_treatment"],
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
            "theory_labels": ["retaliation", "due_process_failure"],
            "authority_hints": ["Fair Housing Act anti-retaliation provisions", "24 C.F.R. Part 100"],
        },
    ],
    "contracting_focus": [
        DEFAULT_HACC_QUERY_SPECS[1],
        DEFAULT_HACC_QUERY_SPECS[3],
        DEFAULT_HACC_QUERY_SPECS[4],
    ],
    "administrative_plan_retaliation": [
        {
            "query": "administrative plan retaliation grievance hearing appeal due process notice of adverse action right to appeal termination decision vawa complaint",
            "type": "housing_discrimination",
            "category": "housing",
            "description": "Retaliation and grievance complaint anchored to the HACC Administrative Plan",
            "theory_labels": ["retaliation", "due_process_failure", "adverse_action"],
            "authority_hints": ["Fair Housing Act anti-retaliation provisions", "24 C.F.R. Part 100"],
            "anchor_titles": ["ADMINISTRATIVE PLAN"],
            "anchor_terms": [
                "grievance hearing",
                "informal hearing",
                "right to appeal",
                "due process rights",
                "written notice",
                "notice of adverse action",
                "termination decision",
                "retaliation",
            ],
        },
    ],
    "acop_due_process": [
        {
            "query": "admissions occupancy policy informal hearing due process denial termination tenant complaint",
            "type": "housing_discrimination",
            "category": "housing",
            "description": "Admissions and due-process complaint anchored to the Admissions and Continued Occupancy Policy",
            "theory_labels": ["due_process_failure", "adverse_action"],
            "authority_hints": ["Fair Housing Act, 42 U.S.C. 3604", "24 C.F.R. Part 100"],
            "anchor_titles": ["ADMISSIONS AND CONTINUED OCCUPANCY POLICY"],
            "anchor_terms": ["informal hearing", "grievance hearing", "impartial person", "due process"],
        },
    ],
    "accommodation_focus": [
        {
            "query": "reasonable accommodation disability denial adverse action informal hearing right to appeal housing authority",
            "type": "housing_discrimination",
            "category": "housing",
            "description": "Reasonable-accommodation complaint anchored to HACC policy language",
            "theory_labels": ["reasonable_accommodation", "disability_discrimination"],
            "protected_bases": ["disability"],
            "authority_hints": ["Fair Housing Act reasonable accommodation requirements", "Section 504 of the Rehabilitation Act", "Americans with Disabilities Act"],
            "anchor_titles": ["ADMINISTRATIVE PLAN", "ADMISSIONS AND CONTINUED OCCUPANCY POLICY"],
            "anchor_terms": [
                "reasonable accommodation",
                "person with a disability",
                "notices of adverse action",
                "right to appeal",
                "informal hearing",
            ],
        },
    ],
    "core_hacc_policies": [
        {
            "query": "retaliation grievance complaint appeal hearing due process tenant policy adverse action",
            "type": "housing_discrimination",
            "category": "housing",
            "description": "Retaliation complaint anchored to HACC core housing policies",
            "theory_labels": ["retaliation", "due_process_failure"],
            "authority_hints": ["Fair Housing Act anti-retaliation provisions", "24 C.F.R. Part 100"],
            "anchor_titles": ["ADMINISTRATIVE PLAN", "ADMISSIONS AND CONTINUED OCCUPANCY POLICY"],
            "anchor_terms": ["grievance", "hearing", "appeal", "informal hearing", "due process"],
        },
        {
            "query": "proxy language DEI equity inclusion housing policy admissions occupancy tenant selection",
            "type": "housing_discrimination",
            "category": "housing",
            "description": "Proxy-language complaint anchored to HACC core housing policies",
            "theory_labels": ["proxy_discrimination", "disparate_treatment"],
            "authority_hints": ["Fair Housing Act, 42 U.S.C. 3604", "24 C.F.R. Part 100"],
            "anchor_titles": ["ADMINISTRATIVE PLAN", "ADMISSIONS AND CONTINUED OCCUPANCY POLICY"],
        },
        {
            "query": "reasonable accommodation disability interactive process denial housing authority",
            "type": "housing_discrimination",
            "category": "housing",
            "description": "Accommodation complaint anchored to HACC core housing policies",
            "theory_labels": ["reasonable_accommodation", "disability_discrimination"],
            "protected_bases": ["disability"],
            "authority_hints": ["Fair Housing Act reasonable accommodation requirements", "Section 504 of the Rehabilitation Act", "Americans with Disabilities Act"],
            "anchor_titles": ["ADMINISTRATIVE PLAN", "ADMISSIONS AND CONTINUED OCCUPANCY POLICY"],
            "anchor_terms": ["reasonable accommodation", "disability", "applicant", "accommodation"],
        },
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
    if _is_probably_toc_text(snippet):
        snippet = _best_rule_text(hit) or snippet
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


def _is_probably_toc_text(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    dotted_leaders = len(re.findall(r"\.{8,}", normalized))
    page_refs = len(re.findall(r"\b\d{1,3}-\d{1,3}\b", normalized))
    heading_hits = len(re.findall(r"\b(?:PART|SECTION|INTRODUCTION|OVERVIEW|PROCEDURES?|APPEALS?)\b", normalized, flags=re.IGNORECASE))
    return dotted_leaders >= 2 or page_refs >= 4 or (heading_hits >= 3 and dotted_leaders >= 1)


def _is_substantive_policy_text(text: str) -> bool:
    normalized = _normalize_match_text(text)
    if not normalized or _is_probably_toc_text(normalized):
        return False

    word_count = len(re.findall(r"\b\w+\b", normalized))
    if word_count < 12:
        return False

    if re.search(r"\bHACC Policy\b", normalized, flags=re.IGNORECASE):
        return True
    if re.search(r"[.!?]", normalized) and re.search(r"\b(?:must|shall|will|may|should)\b", normalized, flags=re.IGNORECASE):
        return True
    if re.search(r"\b(?:provide|request|deliver|schedule|notify|deny|terminate|review|hearing|appeal)\b", normalized, flags=re.IGNORECASE):
        return True
    return False


def _best_rule_text(hit: Dict[str, Any]) -> str:
    scored_rules: List[tuple[int, str]] = []
    for rule in list(hit.get("matched_rules") or []):
        rule_text = " ".join(str(rule.get("text") or "").split()).strip()
        if len(rule_text) < 30:
            continue
        score = len(rule_text)
        lowered = rule_text.lower()
        if any(token in lowered for token in ("written notice", "informal review", "informal hearing", "hearing", "appeal", "grievance", "due process", "termination", "adverse action", "reasonable accommodation")):
            score += 40
        if str(rule.get("rule_type") or "").lower() == "obligation":
            score += 25
        if str(rule.get("modality") or "").lower() == "required":
            score += 20
        scored_rules.append((score, rule_text))
    if scored_rules:
        scored_rules.sort(key=lambda item: (-item[0], item[1]))
        return scored_rules[0][1]
    for entity in list(hit.get("matched_entities") or []):
        entity_text = " ".join(str(entity.get("name") or "").split()).strip()
        if len(entity_text) >= 40:
            return entity_text
    return ""


def _filter_hits(
    hits: Sequence[Dict[str, Any]],
    *,
    anchor_titles: Optional[Sequence[str]] = None,
    anchor_source_paths: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    normalized_titles = {str(value).strip().lower() for value in (anchor_titles or []) if str(value).strip()}
    normalized_paths = {str(value).strip().lower() for value in (anchor_source_paths or []) if str(value).strip()}
    if not normalized_titles and not normalized_paths:
        return list(hits)

    filtered: List[Dict[str, Any]] = []
    for hit in hits:
        title = str(hit.get("title") or "").strip().lower()
        source_path = str(hit.get("source_path") or "").strip().lower()
        title_match = title in normalized_titles if normalized_titles else False
        path_match = any(path and path in source_path for path in normalized_paths)
        if title_match or path_match:
            filtered.append(hit)
    return filtered


def _extract_anchor_passages(
    hits: Sequence[Dict[str, Any]],
    *,
    anchor_terms: Optional[Sequence[str]] = None,
    max_passages: int = 3,
) -> List[Dict[str, Any]]:
    normalized_terms = [str(value).strip().lower() for value in (anchor_terms or []) if str(value).strip()]
    ranked_passages: List[Dict[str, Any]] = []

    for hit in hits:
        snippet = str(hit.get("snippet") or "").strip()
        snippet_lower = snippet.lower()
        if normalized_terms and not any(term in snippet_lower for term in normalized_terms):
            continue
        if not snippet:
            continue
        passage_text = _extract_source_window(
            source_path=str(hit.get("source_path") or ""),
            anchor_terms=normalized_terms,
            fallback_snippet=snippet,
        )
        section_labels = _filter_section_labels_for_anchor_terms(
            _classify_anchor_sections(passage_text),
            normalized_terms,
        )
        matched_terms = [term for term in normalized_terms if term in snippet_lower]
        ranked_passages.append(
            {
                "title": str(hit.get("title") or ""),
                "source_path": str(hit.get("source_path") or ""),
                "snippet": passage_text,
                "section_labels": section_labels,
                "_match_count": len(matched_terms),
                "_specificity": 0 if section_labels == ["general_policy"] else len(section_labels),
                "_score": float(hit.get("score") or 0.0),
            }
        )

    ranked_passages.sort(
        key=lambda item: (
            -int(item.get("_match_count") or 0),
            -int(item.get("_specificity") or 0),
            -float(item.get("_score") or 0.0),
        )
    )
    passages = [
        {
            "title": str(item.get("title") or ""),
            "source_path": str(item.get("source_path") or ""),
            "snippet": str(item.get("snippet") or ""),
            "section_labels": list(item.get("section_labels") or []),
        }
        for item in ranked_passages[:max_passages]
    ]

    if passages or not hits:
        return passages

    for hit in hits[:max_passages]:
        snippet = str(hit.get("snippet") or "").strip()
        if not snippet:
            continue
        passage_text = _extract_source_window(
            source_path=str(hit.get("source_path") or ""),
            anchor_terms=normalized_terms,
            fallback_snippet=snippet,
        )
        section_labels = _filter_section_labels_for_anchor_terms(
            _classify_anchor_sections(passage_text),
            normalized_terms,
        )
        passages.append(
            {
                "title": str(hit.get("title") or ""),
                "source_path": str(hit.get("source_path") or ""),
                "snippet": passage_text,
                "section_labels": section_labels,
            }
        )
    return passages


def _normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clean_extracted_excerpt(text: str) -> str:
    cleaned = _normalize_match_text(text)
    if not cleaned:
        return cleaned

    cleaned = re.sub(
        r'^(?:[A-Z0-9 /&()\-]+\s+\.{4,}\s*\d{1,3}-\d{1,3}\s*)+',
        '',
        cleaned,
        flags=re.IGNORECASE,
    )

    boilerplate_patterns = (
        r"\s*©\s*Copyright\b.*$",
        r"\s*Copyright\s+\d{4}\b.*$",
        r"\s*Unlimited copies may be made for internal use\..*$",
        r"\s*Page\s+\d+(?:-\d+)?\b.*$",
    )
    for pattern in boilerplate_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    heading_markers = (
        r"\bAbsorbing a Portable Family\b",
        r"\bAdminplan\s+\d{1,2}/\d{1,2}/\d{4}\b",
    )
    cut_positions = [match.start() for marker in heading_markers for match in [re.search(marker, cleaned, flags=re.IGNORECASE)] if match]
    if cut_positions:
        cleaned = cleaned[: min(cut_positions)].rstrip(" ,;:-")

    return _normalize_match_text(cleaned)


def _score_excerpt_match(excerpt: str, anchor_terms: Sequence[str]) -> tuple[int, int, int, int]:
    normalized_excerpt = _clean_extracted_excerpt(excerpt)
    if not normalized_excerpt:
        return (0, 0, 0, 0)

    lowered = normalized_excerpt.lower()
    normalized_terms = [str(term).strip().lower() for term in anchor_terms if str(term).strip()]
    matched_terms = {term for term in normalized_terms if term in lowered}
    substantive = 1 if _is_substantive_policy_text(normalized_excerpt) else 0
    non_toc = 1 if not _is_probably_toc_text(normalized_excerpt) else 0
    return (substantive, non_toc, len(matched_terms), len(normalized_excerpt))


def _candidate_text_paths(source_path: str) -> List[Path]:
    path = Path(source_path)
    candidates: List[Path] = []
    alternate_text_candidates: List[Path] = []
    if source_path:
        alternate_text_candidates.append(Path(f"{source_path}.txt"))
        knowledge_graph_text = _repo_root() / "hacc_website" / "knowledge_graph" / "texts" / f"{path.name}.txt"
        alternate_text_candidates.append(knowledge_graph_text)
        candidates.extend(alternate_text_candidates)
        raw_path_is_probably_blob = not path.suffix
        if not raw_path_is_probably_blob or not any(candidate.exists() for candidate in alternate_text_candidates):
            candidates.append(path)

    deduped: List[Path] = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key and key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


@lru_cache(maxsize=64)
def _load_candidate_source_text(path_str: str) -> tuple[str, str]:
    path = Path(path_str)
    try:
        source_text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ("", "")
    return (source_text, _normalize_match_text(source_text))


def _extract_paragraph_excerpt(
    raw_text: str,
    *,
    match_index: int,
    max_chars: int = 520,
) -> str:
    if not raw_text:
        return ""

    paragraph_matches = list(re.finditer(r"\S(?:.*?\S)?(?:\n\s*\n|$)", raw_text, flags=re.DOTALL))
    if not paragraph_matches:
        return ""

    selected_index = None
    for index, match in enumerate(paragraph_matches):
        if match.start() <= match_index < match.end():
            selected_index = index
            break
    if selected_index is None:
        return ""

    combined_parts: List[str] = []
    total_length = 0
    for match in paragraph_matches[selected_index : selected_index + 5]:
        part = _clean_extracted_excerpt(match.group(0))
        if not part:
            continue
        combined_parts.append(part)
        total_length += len(part)
        combined_text = " ".join(combined_parts)
        definitions_context = "definitions applicable to the grievance procedure" in combined_text.lower()
        if total_length >= max_chars:
            break
        if re.search(r"[.!?]$", part):
            if definitions_context and "elements of due process" not in combined_text.lower():
                continue
            break

    excerpt = " ".join(combined_parts).strip()
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max_chars - 3].rstrip(" ,;:.") + "..."
    return excerpt


def _extract_source_window(
    *,
    source_path: str,
    anchor_terms: Sequence[str],
    fallback_snippet: str,
    window_chars: int = 520,
    max_matches_per_needle: int = 12,
) -> str:
    normalized_fallback = _clean_extracted_excerpt(fallback_snippet)
    if not source_path:
        return normalized_fallback

    best_excerpt = ""
    best_score = (0, 0, 0, 0)

    def consider_excerpt(candidate: str) -> None:
        nonlocal best_excerpt, best_score
        candidate_score = _score_excerpt_match(candidate, anchor_terms)
        if candidate_score > best_score:
            best_excerpt = _clean_extracted_excerpt(candidate)
            best_score = candidate_score

    search_needles = sorted(
        [term for term in anchor_terms if term],
        key=len,
        reverse=True,
    )
    fallback_phrase = " ".join(normalized_fallback.split()[:10]).strip()
    if fallback_phrase:
        search_needles.append(fallback_phrase)

    for path in _candidate_text_paths(source_path):
        if not path.exists():
            continue
        source_text, normalized_source = _load_candidate_source_text(str(path))
        if not source_text or not normalized_source:
            continue

        source_text_lower = source_text.lower()
        normalized_source_lower = normalized_source.lower()
        for needle in search_needles:
            needle_lower = str(needle).lower()
            search_from = 0
            matches_seen = 0
            while True:
                raw_idx = source_text_lower.find(needle_lower, search_from)
                if raw_idx >= 0:
                    paragraph_excerpt = _extract_paragraph_excerpt(
                        source_text,
                        match_index=raw_idx,
                        max_chars=window_chars,
                    )
                    consider_excerpt(paragraph_excerpt)
                idx = normalized_source_lower.find(needle_lower, search_from)
                if idx < 0:
                    break
                start = max(0, idx - (window_chars // 3))
                end = min(len(normalized_source), idx + window_chars)
                if start > 0:
                    sentence_start = max(
                        normalized_source.rfind(". ", max(0, start - 200), start),
                        normalized_source.rfind("! ", max(0, start - 200), start),
                        normalized_source.rfind("? ", max(0, start - 200), start),
                    )
                    if sentence_start >= 0:
                        start = sentence_start + 2
                    elif normalized_source[start - 1].isalnum():
                        next_space = normalized_source.find(" ", start)
                        if next_space > start:
                            start = next_space + 1
                if end < len(normalized_source):
                    sentence_end_candidates = [
                        pos for pos in (
                            normalized_source.find(". ", end, min(len(normalized_source), end + 200)),
                            normalized_source.find("! ", end, min(len(normalized_source), end + 200)),
                            normalized_source.find("? ", end, min(len(normalized_source), end + 200)),
                        )
                        if pos >= 0
                    ]
                    if sentence_end_candidates:
                        end = min(sentence_end_candidates) + 1
                    elif normalized_source[end - 1].isalnum():
                        last_space = normalized_source.rfind(" ", start, end)
                        if last_space > start:
                            end = last_space
                excerpt = _clean_extracted_excerpt(normalized_source[start:end])
                consider_excerpt(excerpt)
                if excerpt:
                    trimmed_excerpt = _clean_extracted_excerpt(normalized_source[idx:end])
                    consider_excerpt(trimmed_excerpt)
                search_from = max(idx, raw_idx if raw_idx >= 0 else idx) + max(1, len(needle_lower))
                matches_seen += 1
                if matches_seen >= max_matches_per_needle:
                    break

    if best_excerpt:
        return best_excerpt

    return normalized_fallback


def _expand_hit_with_source_window(
    hit: Dict[str, Any],
    *,
    anchor_terms: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    expanded_hit = dict(hit)
    snippet = str(hit.get("snippet") or "").strip()
    if not snippet:
        return expanded_hit
    fallback_snippet = _best_rule_text(hit) if _is_probably_toc_text(snippet) else snippet
    anchor_needles = [str(term).strip().lower() for term in (anchor_terms or []) if str(term).strip()]
    best_rule = _best_rule_text(hit)
    if best_rule:
        anchor_needles = [best_rule.lower(), *anchor_needles]

    expanded_hit["snippet"] = _extract_source_window(
        source_path=str(hit.get("source_path") or ""),
        anchor_terms=anchor_needles,
        fallback_snippet=fallback_snippet,
    )
    return expanded_hit


def _expand_hits_with_source_windows(
    hits: Sequence[Dict[str, Any]],
    *,
    anchor_terms: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    return [
        _expand_hit_with_source_window(hit, anchor_terms=anchor_terms)
        for hit in hits
    ]


def _classify_anchor_sections(snippet: str) -> List[str]:
    normalized = str(snippet or "").strip().lower()
    labels: List[str] = []
    for label, patterns in ANCHOR_SECTION_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            labels.append(label)
    return labels or ["general_policy"]


def _filter_section_labels_for_anchor_terms(
    section_labels: Sequence[str],
    anchor_terms: Optional[Sequence[str]],
) -> List[str]:
    normalized_terms = [str(term).strip().lower() for term in (anchor_terms or []) if str(term).strip()]
    if not normalized_terms:
        return list(section_labels)

    filtered: List[str] = []
    for label in section_labels:
        hints = ANCHOR_SECTION_HINT_TERMS.get(label, ())
        if not hints:
            filtered.append(label)
            continue
        if any(hint in term or term in hint for hint in hints for term in normalized_terms):
            filtered.append(label)
    return filtered or list(section_labels)


def _summarize_section_labels(anchor_passages: Sequence[Dict[str, Any]]) -> List[str]:
    labels: List[str] = []
    seen = set()
    for passage in anchor_passages:
        for label in list(passage.get("section_labels") or []):
            if label not in seen:
                seen.add(label)
                labels.append(label)
    return labels


def _condense_evidence_snippet(text: str, max_chars: int = 220) -> str:
    cleaned = _normalize_match_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,;:.") + "..."


def _build_repository_candidates(
    grounding_bundle: Optional[Dict[str, Any]],
    *,
    max_candidates: int = 3,
) -> List[Dict[str, Any]]:
    candidates = list((grounding_bundle or {}).get("upload_candidates") or [])
    simplified: List[Dict[str, Any]] = []
    for candidate in candidates[:max_candidates]:
        simplified.append(
            {
                "title": str(candidate.get("title") or ""),
                "relative_path": str(candidate.get("relative_path") or ""),
                "source_path": str(candidate.get("source_path") or ""),
                "snippet": _condense_evidence_snippet(str(candidate.get("snippet") or "")),
                "score": float(candidate.get("score") or 0.0),
                "source_type": str(candidate.get("source_type") or ""),
                "metadata": dict(candidate.get("metadata") or {}),
            }
        )
    return simplified


def _build_seed_mediator_packets(
    engine: Any,
    grounding_bundle: Optional[Dict[str, Any]],
    *,
    max_documents: int = 3,
) -> List[Dict[str, Any]]:
    upload_candidates = list((grounding_bundle or {}).get("upload_candidates") or [])[:max_documents]
    if not upload_candidates:
        return []

    base_packets = list((grounding_bundle or {}).get("mediator_evidence_packets") or [])[:max_documents]
    packets_by_path = {
        str(packet.get("source_path") or "").strip(): dict(packet)
        for packet in base_packets
        if str(packet.get("source_path") or "").strip()
    }

    enriched_packets: List[Dict[str, Any]] = []
    for candidate in upload_candidates:
        source_path = str(candidate.get("source_path") or "").strip()
        if not source_path:
            continue
        packet = dict(packets_by_path.get(source_path) or {})
        if not packet:
            path = Path(source_path)
            packet = {
                "document_label": str(candidate.get("title") or path.name),
                "source_path": source_path,
                "relative_path": str(candidate.get("relative_path") or path.name),
                "filename": path.name,
                "mime_type": "text/plain",
                "metadata": {},
            }
        metadata = dict(packet.get("metadata") or {})
        try:
            document_text = str(engine._resolve_candidate_upload_text(candidate) or "")
        except Exception:
            document_text = str(candidate.get("snippet") or "")
        packet["document_text"] = document_text
        metadata.setdefault("relative_path", str(candidate.get("relative_path") or ""))
        metadata.setdefault("source_type", str(candidate.get("source_type") or ""))
        metadata.setdefault("upload_strategy", "snippet_only" if not document_text else "seed_packet")
        packet["metadata"] = metadata
        enriched_packets.append(packet)
    return enriched_packets


def _build_complainant_story_facts(
    *,
    description: str,
    evidence_summary: str,
    anchor_passages: Sequence[Dict[str, Any]],
    hits: Sequence[Dict[str, Any]],
    repository_candidates: Sequence[Dict[str, Any]],
    max_facts: int = 6,
) -> List[str]:
    facts: List[str] = []

    if description:
        facts.append(f"Complaint theory: {description}")
    if evidence_summary:
        facts.append(f"Primary evidence summary: {_condense_evidence_snippet(evidence_summary, max_chars=260)}")

    for passage in list(anchor_passages or [])[:3]:
        title = str(passage.get("title") or "policy document").strip()
        snippet = _condense_evidence_snippet(str(passage.get("snippet") or ""), max_chars=240)
        labels = ", ".join(list(passage.get("section_labels") or []))
        if not snippet:
            continue
        if labels:
            facts.append(f"Anchor from {title} [{labels}]: {snippet}")
        else:
            facts.append(f"Anchor from {title}: {snippet}")

    for candidate in list(repository_candidates or [])[:2]:
        title = str(candidate.get("title") or candidate.get("relative_path") or "repository evidence").strip()
        snippet = _condense_evidence_snippet(str(candidate.get("snippet") or ""), max_chars=220)
        if snippet:
            facts.append(f"Repository evidence {title}: {snippet}")

    for hit in list(hits or [])[:2]:
        title = str(hit.get("title") or hit.get("document_id") or "supporting evidence").strip()
        snippet = _condense_evidence_snippet(str(hit.get("snippet") or ""), max_chars=220)
        if snippet:
            facts.append(f"Supporting document {title}: {snippet}")

    deduped: List[str] = []
    seen = set()
    for fact in facts:
        normalized = re.sub(r"[^a-z0-9]+", " ", fact.lower()).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(fact)
        if len(deduped) >= max_facts:
            break
    return deduped


def build_hacc_evidence_seed(
    search_payload: Dict[str, Any],
    *,
    query: str,
    complaint_type: str,
    category: str,
    description: str,
    anchor_titles: Optional[Sequence[str]] = None,
    anchor_source_paths: Optional[Sequence[str]] = None,
    anchor_terms: Optional[Sequence[str]] = None,
    theory_labels: Optional[Sequence[str]] = None,
    protected_bases: Optional[Sequence[str]] = None,
    authority_hints: Optional[Sequence[str]] = None,
    grounding_bundle: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    raw_hits = [_summarize_hit(hit) for hit in list(search_payload.get("results", []) or [])]
    hits = _filter_hits(
        raw_hits,
        anchor_titles=anchor_titles,
        anchor_source_paths=anchor_source_paths,
    ) or raw_hits
    hits = _expand_hits_with_source_windows(hits, anchor_terms=anchor_terms)
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
    anchor_passages = _extract_anchor_passages(hits, anchor_terms=anchor_terms)
    anchor_sections = _summarize_section_labels(anchor_passages)
    repository_candidates = _build_repository_candidates(grounding_bundle)
    synthetic_prompts = dict((grounding_bundle or {}).get("synthetic_prompts") or {})
    mediator_evidence_packets = list((grounding_bundle or {}).get("mediator_evidence_packets") or [])
    complainant_story_facts = _build_complainant_story_facts(
        description=description,
        evidence_summary=evidence_summary,
        anchor_passages=anchor_passages,
        hits=hits,
        repository_candidates=repository_candidates,
    )

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
            "anchor_titles": list(anchor_titles or []),
            "anchor_source_paths": list(anchor_source_paths or []),
            "anchor_terms": list(anchor_terms or []),
            "anchor_passages": anchor_passages,
            "anchor_sections": anchor_sections,
            "theory_labels": [str(item) for item in list(theory_labels or []) if str(item).strip()],
            "protected_bases": [str(item) for item in list(protected_bases or []) if str(item).strip()],
            "authority_hints": [str(item) for item in list(authority_hints or []) if str(item).strip()],
            "repository_evidence_candidates": repository_candidates,
            "synthetic_prompts": synthetic_prompts,
            "mediator_evidence_packets": mediator_evidence_packets,
            "complainant_story_facts": complainant_story_facts,
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
        query = str(spec.get("query") or "")
        complaint_type = str(spec.get("type") or "civil_rights_violation")
        payload = engine.search(
            query,
            top_k=search_top_k,
            use_vector=use_vector,
        )
        grounding_bundle = engine.build_grounding_bundle(
            query,
            top_k=max(1, search_top_k),
            claim_type=complaint_type,
            use_vector=use_vector,
        )
        if isinstance(grounding_bundle, dict):
            grounding_bundle["mediator_evidence_packets"] = _build_seed_mediator_packets(
                engine,
                grounding_bundle,
                max_documents=max(1, search_top_k),
            )
        seed = build_hacc_evidence_seed(
            payload,
            query=query,
            complaint_type=complaint_type,
            category=str(spec.get("category") or "civil_rights"),
            description=str(spec.get("description") or "Evidence-backed complaint seed from HACC corpus"),
            anchor_titles=spec.get("anchor_titles"),
            anchor_source_paths=spec.get("anchor_source_paths"),
            anchor_terms=spec.get("anchor_terms"),
            theory_labels=spec.get("theory_labels"),
            protected_bases=spec.get("protected_bases"),
            authority_hints=spec.get("authority_hints"),
            grounding_bundle=grounding_bundle,
        )
        if seed:
            seeds.append(seed)
        if len(seeds) >= count:
            break
    return seeds[:count]


def resolve_hacc_question_evidence(
    *,
    question: str,
    key_facts: Optional[Dict[str, Any]] = None,
    existing_evidence: Optional[Sequence[Dict[str, Any]]] = None,
    repo_root: Optional[str | Path] = None,
    use_vector: bool = False,
    top_k: int = 4,
) -> Dict[str, Any]:
    normalized_question = str(question or "").strip()
    facts = dict(key_facts or {})
    if not normalized_question:
        return {
            "question": normalized_question,
            "query": "",
            "evidence_summary": "",
            "evidence_items": [],
            "anchor_passages": [],
            "anchor_sections": [],
        }

    try:
        engine = _get_hacc_engine_instance(repo_root=repo_root)
    except Exception as exc:
        logger.warning("Unable to initialize HACCResearchEngine for question evidence lookup: %s", exc)
        return {
            "question": normalized_question,
            "query": normalized_question,
            "evidence_summary": "",
            "evidence_items": [],
            "anchor_passages": [],
            "anchor_sections": [],
            "error": str(exc),
        }

    anchor_terms = [str(item).strip() for item in list(facts.get("anchor_terms") or []) if str(item).strip()]
    query_parts: List[str] = [normalized_question]
    if facts.get("evidence_query"):
        query_parts.append(str(facts.get("evidence_query")))
    if anchor_terms:
        query_parts.append(" ".join(anchor_terms[:4]))
    search_query = " ".join(part for part in query_parts if part).strip()

    payload = engine.search(search_query, top_k=top_k, use_vector=use_vector)
    raw_hits = [_summarize_hit(hit) for hit in list(payload.get("results", []) or [])]
    hits = _filter_hits(
        raw_hits,
        anchor_titles=facts.get("anchor_titles"),
        anchor_source_paths=facts.get("anchor_source_paths"),
    ) or raw_hits
    hits = _expand_hits_with_source_windows(hits, anchor_terms=anchor_terms)

    merged_hits: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    for item in list(existing_evidence or []) + hits:
        key = str(item.get("document_id") or "") or str(item.get("source_path") or "") or str(item.get("title") or "")
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        merged_hits.append(item)

    anchor_passages = _extract_anchor_passages(hits, anchor_terms=anchor_terms)
    anchor_sections = _summarize_section_labels(anchor_passages)
    lead = hits[0] if hits else {}
    evidence_summary = " ".join(
        part
        for part in [
            f"For this question, the strongest supporting material is '{lead.get('title')}'." if lead.get("title") else "",
            str(lead.get("snippet") or "").strip(),
        ]
        if part
    ).strip()

    return {
        "question": normalized_question,
        "query": search_query,
        "evidence_summary": evidence_summary,
        "evidence_items": merged_hits[: max(top_k, 3)],
        "anchor_passages": anchor_passages,
        "anchor_sections": anchor_sections,
    }


def build_hacc_mediator_evidence_packet(
    seed: Dict[str, Any],
    *,
    max_documents: int = 3,
) -> List[Dict[str, Any]]:
    key_facts = dict(seed.get("key_facts") or {})
    grounded_packets = list(key_facts.get("mediator_evidence_packets") or [])
    evidence_items = list(seed.get("hacc_evidence") or [])
    repository_candidates = list(key_facts.get("repository_evidence_candidates") or [])

    packets: List[Dict[str, Any]] = []
    for packet in grounded_packets[:max_documents]:
        document_text = str(packet.get("document_text") or "").strip()
        if not document_text:
            continue
        packets.append(
            {
                "document_text": document_text,
                "document_label": str(packet.get("document_label") or "HACC evidence"),
                "source_path": str(packet.get("source_path") or ""),
                "filename": str(packet.get("filename") or ""),
                "mime_type": str(packet.get("mime_type") or "text/plain"),
                "metadata": dict(packet.get("metadata") or {}),
            }
        )
    if packets:
        return packets

    source_paths: List[str] = []
    for candidate in repository_candidates:
        candidate_path = str(candidate.get("source_path") or "").strip()
        if candidate_path:
            source_paths.append(candidate_path)
    for item in list(key_facts.get("source_paths") or []):
        item_path = str(item).strip()
        if item_path:
            source_paths.append(item_path)
    seen_paths: set[str] = set()

    for source_path in source_paths[:max_documents]:
        path = Path(source_path)
        if not path.exists() or str(path) in seen_paths:
            continue
        try:
            document_text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        seen_paths.add(str(path))
        matching_item = next((item for item in evidence_items if str(item.get("source_path") or "") == str(path)), {})
        matching_candidate = next(
            (item for item in repository_candidates if str(item.get("source_path") or "") == str(path)),
            {},
        )
        packets.append(
            {
                "document_text": document_text,
                "document_label": str(
                    matching_candidate.get("title")
                    or matching_item.get("title")
                    or path.name
                ),
                "source_path": str(path),
                "filename": path.name,
                "mime_type": "text/plain",
                "metadata": {
                    "source_path": str(path),
                    "hacc_seed_type": str(seed.get("type") or ""),
                    "evidence_query": str(key_facts.get("evidence_query") or ""),
                    "anchor_sections": list(key_facts.get("anchor_sections") or []),
                    "anchor_terms": list(key_facts.get("anchor_terms") or []),
                    "relative_path": str(matching_candidate.get("relative_path") or ""),
                    "repository_candidate": bool(matching_candidate),
                },
            }
        )

    if packets:
        return packets

    for candidate in repository_candidates[:max_documents]:
        snippet = str(candidate.get("snippet") or "").strip()
        if not snippet:
            continue
        packets.append(
            {
                "document_text": snippet,
                "document_label": str(candidate.get("title") or candidate.get("relative_path") or "repository_evidence_snippet"),
                "source_path": str(candidate.get("source_path") or ""),
                "filename": str(candidate.get("relative_path") or ""),
                "mime_type": "text/plain",
                "metadata": {
                    "source_path": str(candidate.get("source_path") or ""),
                    "relative_path": str(candidate.get("relative_path") or ""),
                    "hacc_seed_type": str(seed.get("type") or ""),
                    "evidence_query": str(key_facts.get("evidence_query") or ""),
                    "anchor_sections": list(key_facts.get("anchor_sections") or []),
                    "anchor_terms": list(key_facts.get("anchor_terms") or []),
                    "snippet_only": True,
                    "repository_candidate": True,
                },
            }
        )

    if packets:
        return packets

    for item in evidence_items[:max_documents]:
        snippet = str(item.get("snippet") or "").strip()
        if not snippet:
            continue
        packets.append(
            {
                "document_text": snippet,
                "document_label": str(item.get("title") or item.get("document_id") or "hacc_evidence_snippet"),
                "source_path": str(item.get("source_path") or ""),
                "filename": "",
                "mime_type": "text/plain",
                "metadata": {
                    "source_path": str(item.get("source_path") or ""),
                    "hacc_seed_type": str(seed.get("type") or ""),
                    "evidence_query": str(key_facts.get("evidence_query") or ""),
                    "anchor_sections": list(key_facts.get("anchor_sections") or []),
                    "anchor_terms": list(key_facts.get("anchor_terms") or []),
                    "snippet_only": True,
                },
            }
        )
    return packets
