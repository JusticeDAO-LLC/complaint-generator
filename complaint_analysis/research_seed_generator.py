"""
Research seed generation helpers for KG- and audit-driven discovery workflows.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SITES = [
    "clackamas.us",
    "www.clackamas.us",
    "oregon.gov",
    "www.oregon.gov",
    "state.or.us",
    "oregonlegislature.gov",
    "oregonbuys.gov",
    "hud.gov",
    "www.hud.gov",
    "hudexchange.info",
    "www.hudexchange.info",
    "quantumresidential.com",
    "www.quantumresidential.com",
    "paycom.com",
    "paycomonline.net",
]

ENTITY_TYPE_ALLOW = {
    "government_body",
    "policy_or_law",
    "program",
    "organization",
    "entity",
}

STOP_LABELS = {
    "fax",
    "phone",
    "suite",
    "ne suite",
    "summer st",
    "summer street ne",
    "center st",
    "capitol street ne",
    "salem",
    "page",
    "section",
    "initial",
    "continue to",
    "due to",
    "try our",
    "marketplace catalog manager",
    "all rights reserved",
}

ACRONYM_ALLOW = {
    "OHCS",
    "HUD",
    "ORS",
    "OAR",
    "ORCA",
    "NSF",
    "OED",
    "ODOE",
    "OBO",
    "PSH",
    "AMI",
    "COBID",
    "MWESB",
    "DBE",
    "LIHTC",
    "NTIA",
    "OHA",
    "ODE",
    "DCBS",
    "DEQ",
    "DLCD",
    "OREA",
    "HACC",
    "EIC",
    "VBE",
    "WBE",
    "MBE",
    "GINA",
    "USC",
    "ADA",
    "BIPOC",
    "LGBTQ",
    "LGBTQIA",
    "DEI",
    "STEM",
}

CATEGORY_TERMS: dict[str, list[str]] = {
    "preferential_treatment": [
        "quota",
        "set-aside",
        "preference",
        "race-based",
        "sex-based",
        "affirmative action",
        "prioritize",
        "eligibility",
        "scoring criteria",
    ],
    "proxies": [
        "equity lens",
        "racial equity framework",
        "cultural competence",
        "lived experience",
        "targeted universalism",
        "equity impact",
    ],
    "selection_contracting": [
        "procurement",
        "contract",
        "RFP",
        "RFQ",
        "bid",
        "solicitation",
        "subaward",
        "monitoring",
        "nondiscrimination clause",
        "COBID",
        "MWESB",
        "DBE",
    ],
    "training_hostile_environment": [
        "mandatory training",
        "anti-racist training",
        "implicit bias",
        "unconscious bias",
        "hostile environment",
        "harassment",
    ],
    "third_party_funding_monitoring": [
        "subrecipient",
        "subaward",
        "grant agreement",
        "contract compliance",
        "certification",
        "reporting requirements",
        "self-report",
    ],
    "retaliation_protections": [
        "retaliation",
        "anti-retaliation",
        "whistleblower",
        "complaint procedure",
        "grievance",
        "investigation",
    ],
    "segregation_exclusion": [
        "segregation",
        "separate",
        "exclusion",
        "restricted to",
        "race-specific",
    ],
}

LEGAL_TERMS = [
    "policy",
    "rule",
    "statute",
    "ORS",
    "OAR",
    "Title VI",
    "Civil Rights Act",
    "nondiscrimination",
    "complaint",
]


@dataclass(frozen=True)
class Entity:
    label: str
    type: str
    score: int


def entity_label_ok(label: str) -> bool:
    s = (label or "").strip()
    if not s:
        return False
    if len(s) > 90:
        return False
    sl = s.lower()
    if sl in STOP_LABELS:
        return False
    if re.search(r"\b(initial|materials?|packet|mtg|agenda)\b", sl):
        return False
    if re.fullmatch(r"[A-Z]{2,6}", s) and s not in ACRONYM_ALLOW:
        return False
    if not re.search(r"[A-Za-z]", s):
        return False
    if re.search(r"\b(street|\bst\b|ave|avenue|blvd|suite|ste\b|\bne\b|\bnw\b|\bse\b|\bsw\b)\b", sl):
        if sl not in {"ors", "oar"}:
            return False
    if sl in {"pdf", "html", "get", "post", "iso"}:
        return False
    return True


def load_kg_nodes(kg_path: Path) -> dict[str, dict[str, Any]]:
    kg = json.loads(kg_path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for node in kg.get("nodes", []):
        if not isinstance(node, dict):
            continue
        label = (node.get("label") or "").strip()
        if not label:
            continue
        out[label.lower()] = node
    return out


def parse_top_entities(cell: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    if not cell:
        return out
    for part in cell.split(";"):
        s = part.strip()
        if not s:
            continue
        match = re.match(r"^(.*)\((\d+)\)\s*$", s)
        if not match:
            continue
        label = match.group(1).strip()
        try:
            count = int(match.group(2))
        except ValueError:
            count = 1
        if label:
            out.append((label, count))
    return out


def row_is_violation_relevant(row: dict[str, str], min_checklist_score: int) -> bool:
    try:
        max_score = int(row.get("max_checklist_score") or 0)
    except ValueError:
        max_score = 0
    assessment = (row.get("assessment") or "").lower()
    if "likely-violation-indicator" in assessment:
        return True
    return max_score >= min_checklist_score


def build_entity_pool(
    reviews_path: Path,
    kg_nodes_by_label: dict[str, dict[str, Any]],
    min_checklist_score: int,
    max_docs: int | None,
) -> tuple[list[dict[str, str]], Counter[str], dict[str, list[str]]]:
    selected_rows: list[dict[str, str]] = []
    entity_scores: Counter[str] = Counter()
    doc_categories: dict[str, list[str]] = {}

    with reviews_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not row_is_violation_relevant(row, min_checklist_score=min_checklist_score):
                continue
            selected_rows.append(row)
            if max_docs is not None and len(selected_rows) >= max_docs:
                break

    for row in selected_rows:
        doc_id = row.get("document_id") or ""
        category = (row.get("max_checklist_category") or "").strip()
        if doc_id:
            doc_categories[doc_id] = [category] if category else []

        for label, count in parse_top_entities(row.get("top_entities") or ""):
            if not entity_label_ok(label):
                continue
            node = kg_nodes_by_label.get(label.lower())
            node_type = (node.get("type") if node else None) or "entity"
            if node_type not in ENTITY_TYPE_ALLOW:
                continue
            entity_scores[label] += count

    return selected_rows, entity_scores, doc_categories


def quote_if_needed(s: str) -> str:
    if re.search(r"\s", s):
        return f'"{s}"'
    return s


def make_queries(
    entities: list[Entity],
    sites: list[str],
    include_sites: bool,
    max_queries: int,
    category_focus_terms: list[str],
    *,
    max_query_chars: int = 280,
    terms_per_query: int = 3,
    max_focus_terms: int = 12,
    legal_terms_per_query: int = 1,
) -> list[str]:
    queries: list[str] = []

    def dedupe_preserve(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            s = (item or "").strip()
            if not s:
                continue
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out

    def chunk_terms(items: list[str], size: int) -> list[list[str]]:
        if size <= 0:
            return []
        return [items[i : i + size] for i in range(0, len(items), size)]

    def add(q: str) -> None:
        qn = re.sub(r"\s+", " ", q).strip()
        if not qn:
            return
        if len(qn) > max_query_chars:
            qn = qn[:max_query_chars].rsplit(" ", 1)[0].strip()
            if not qn:
                return
        queries.append(qn)

    focus_terms = dedupe_preserve(category_focus_terms)[:max_focus_terms]
    legal_terms = dedupe_preserve(LEGAL_TERMS)
    focus_bundles = chunk_terms(focus_terms, max(1, terms_per_query))
    legal_bundle = legal_terms[: max(0, legal_terms_per_query)]

    if include_sites:
        for site in sites:
            site_prefix = f"site:{site}"
            for entity in entities:
                if not focus_bundles:
                    add(f"{site_prefix} {quote_if_needed(entity.label)} {' '.join([quote_if_needed(t) for t in legal_bundle])}")
                    continue
                for bundle in focus_bundles:
                    parts = [site_prefix, quote_if_needed(entity.label)]
                    parts.extend(quote_if_needed(t) for t in bundle)
                    parts.extend(quote_if_needed(t) for t in legal_bundle)
                    add(" ".join(p for p in parts if p))
    else:
        for entity in entities:
            if not focus_bundles:
                add(f"{quote_if_needed(entity.label)} {' '.join([quote_if_needed(t) for t in legal_bundle])}")
                continue
            for bundle in focus_bundles:
                parts = [quote_if_needed(entity.label)]
                parts.extend(quote_if_needed(t) for t in bundle)
                parts.extend(quote_if_needed(t) for t in legal_bundle)
                add(" ".join(p for p in parts if p))

    out: list[str] = []
    seen: set[str] = set()
    for query in queries:
        if query in seen:
            continue
        seen.add(query)
        out.append(query)
        if len(out) >= max_queries:
            break
    return out


__all__ = [
    "ACRONYM_ALLOW",
    "CATEGORY_TERMS",
    "DEFAULT_SITES",
    "ENTITY_TYPE_ALLOW",
    "Entity",
    "LEGAL_TERMS",
    "STOP_LABELS",
    "build_entity_pool",
    "entity_label_ok",
    "load_kg_nodes",
    "make_queries",
    "parse_top_entities",
    "quote_if_needed",
    "row_is_violation_relevant",
]
