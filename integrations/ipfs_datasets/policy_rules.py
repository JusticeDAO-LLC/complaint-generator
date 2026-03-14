from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .loader import import_attr_optional, run_async_compat
from .types import GraphEntity, GraphPayload, GraphRelationship, with_adapter_metadata


FileConverter, _file_converter_error = import_attr_optional(
    "ipfs_datasets_py.processors.file_converter.converter",
    "FileConverter",
)
KnowledgeGraphExtractor, _kg_extractor_error = import_attr_optional(
    "ipfs_datasets_py.knowledge_graphs.extraction.extractor",
    "KnowledgeGraphExtractor",
)

POLICY_RULES_AVAILABLE = FileConverter is not None and KnowledgeGraphExtractor is not None
POLICY_RULES_ERROR = _file_converter_error or _kg_extractor_error

_HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?\s+)?[A-Z][A-Za-z0-9/(),:& -]{2,}$")
_SECTION_PREFIX_RE = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_PDF_RULE_PATTERNS: List[Tuple[str, str, re.Pattern[str]]] = [
    ("prohibition", "forbidden", re.compile(r"\b(must not|shall not|may not|cannot|can not|will not|not be able to)\b", re.I)),
    ("deadline", "time_bound", re.compile(r"\b(within\s+\d+\s+(?:calendar\s+|business\s+)?days?|no later than|by\s+[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|annually|monthly|weekly)\b", re.I)),
    ("eligibility", "eligibility", re.compile(r"\b(eligible|eligibility|qualify|qualified|income at or below|income between|required income|applicant)\b", re.I)),
    ("obligation", "required", re.compile(r"\b(must|shall|required to|is required to|are required to|will|needs to|need to)\b", re.I)),
    ("discretion", "discretionary", re.compile(r"\b(may|may be considered|at (?:the )?discretion|can be paid|flexibility)\b", re.I)),
]


def _stable_identifier(prefix: str, *parts: str) -> str:
    from hashlib import sha256

    normalized = "|".join(part.strip() for part in parts if part and part.strip())
    if not normalized:
        return ""
    return f"{prefix}:{sha256(normalized.encode('utf-8')).hexdigest()[:16]}"


def _clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", (text or "").replace("\x00", " ")).strip()


def _split_sentences(text: str) -> List[str]:
    parts = _SENTENCE_RE.split(text or "")
    return [_clean_text(part) for part in parts if _clean_text(part)]


def _looks_like_heading(line: str) -> bool:
    line = _clean_text(line)
    if not line or len(line) > 140:
        return False
    if len(line.split()) > 10:
        return False
    if line.endswith(".") and not _SECTION_PREFIX_RE.match(line):
        return False
    return bool(_HEADING_RE.match(line))


def _section_title_from_line(line: str) -> str:
    cleaned = _clean_text(line)
    return _SECTION_PREFIX_RE.sub("", cleaned).strip() or cleaned


def _detect_rule(sentence: str) -> tuple[str, str] | None:
    candidate = _clean_text(sentence)
    if len(candidate) < 35:
        return None
    for rule_type, modality, pattern in _PDF_RULE_PATTERNS:
        if pattern.search(candidate):
            return rule_type, modality
    return None


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def _serialize_upstream_entity(entity: Any) -> tuple[str, str, float, Dict[str, Any]]:
    entity_type = str(getattr(entity, "entity_type", "concept") or "concept")
    name = str(getattr(entity, "name", "") or "").strip()
    confidence = float(getattr(entity, "confidence", 0.5) or 0.5)
    attributes = {
        "source_text": str(getattr(entity, "source_text", "") or ""),
        "provider_entity_id": str(getattr(entity, "entity_id", "") or ""),
    }
    return entity_type, name, confidence, attributes


def _serialize_upstream_relationship(relationship: Any) -> tuple[str, str, str, float]:
    return (
        str(getattr(relationship, "source_id", "") or ""),
        str(getattr(relationship, "target_id", "") or ""),
        str(getattr(relationship, "relationship_type", "related_to") or "related_to"),
        float(getattr(relationship, "confidence", 0.5) or 0.5),
    )


def _extract_sections_and_rules(text: str) -> tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    lines = [_clean_text(line) for line in (text or "").splitlines()]
    non_empty_lines = [line for line in lines if line]
    title = non_empty_lines[0] if non_empty_lines else "Untitled PDF"

    sections: List[Dict[str, Any]] = []
    rules: List[Dict[str, Any]] = []

    current_section_title = "Document Overview"
    current_section_id = _stable_identifier("section", title, current_section_title)
    sections.append({"section_id": current_section_id, "title": current_section_title, "ordinal": 0})
    section_index = 1
    rule_index = 0

    for raw_line in lines:
        line = _clean_text(raw_line)
        if not line:
            continue
        if _looks_like_heading(line):
            current_section_title = _section_title_from_line(line)
            current_section_id = _stable_identifier("section", title, current_section_title)
            sections.append(
                {
                    "section_id": current_section_id,
                    "title": current_section_title,
                    "ordinal": section_index,
                }
            )
            section_index += 1
            continue

        for sentence in _split_sentences(line):
            rule_match = _detect_rule(sentence)
            if rule_match is None:
                continue
            rule_type, modality = rule_match
            rule_id = _stable_identifier("rule", title, current_section_id, str(rule_index), sentence)
            rules.append(
                {
                    "rule_id": rule_id,
                    "text": sentence,
                    "rule_type": rule_type,
                    "modality": modality,
                    "section_id": current_section_id,
                    "section_title": current_section_title,
                    "ordinal": rule_index,
                }
            )
            rule_index += 1

    return title, sections, rules


def extract_policy_rules_from_pdf(
    pdf_path: str,
    *,
    backend: str = "markitdown",
    title: Optional[str] = None,
    include_text: bool = True,
) -> Dict[str, Any]:
    if not POLICY_RULES_AVAILABLE:
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "result": None,
            },
            operation="extract_policy_rules_from_pdf",
            backend_available=False,
            degraded_reason=POLICY_RULES_ERROR,
            implementation_status="unavailable",
        )

    source_path = Path(pdf_path)
    if not source_path.exists():
        return with_adapter_metadata(
            {
                "status": "error",
                "error": f"PDF file not found: {source_path}",
                "result": None,
            },
            operation="extract_policy_rules_from_pdf",
            backend_available=True,
            implementation_status="error",
        )

    try:
        converter = FileConverter(backend=backend)
        conversion = run_async_compat(converter.convert(str(source_path)))
    except Exception as exc:
        return with_adapter_metadata(
            {
                "status": "error",
                "error": f"Failed to convert PDF: {exc}",
                "result": None,
            },
            operation="extract_policy_rules_from_pdf",
            backend_available=True,
            implementation_status="error",
        )

    if not getattr(conversion, "success", False):
        return with_adapter_metadata(
            {
                "status": "error",
                "error": str(getattr(conversion, "error", "") or "Unknown PDF conversion failure"),
                "result": None,
            },
            operation="extract_policy_rules_from_pdf",
            backend_available=True,
            implementation_status="error",
        )

    text = str(getattr(conversion, "text", "") or "")
    resolved_title, sections, rules = _extract_sections_and_rules(text)
    resolved_title = title or resolved_title or source_path.name
    document_id = _stable_identifier("document", str(source_path.resolve()))

    entities: List[GraphEntity] = [
        GraphEntity(
            entity_id=document_id,
            entity_type="policy_document",
            name=resolved_title,
            confidence=1.0,
            attributes={
                "source_path": str(source_path.resolve()),
                "backend": backend,
                "file_name": source_path.name,
            },
        )
    ]
    relationships: List[GraphRelationship] = []

    extractor = KnowledgeGraphExtractor(use_spacy=False, use_transformers=False, use_tracer=False)
    concept_ids: Dict[Tuple[str, str], str] = {}

    for section in sections:
        section_id = section["section_id"]
        entities.append(
            GraphEntity(
                entity_id=section_id,
                entity_type="policy_section",
                name=section["title"],
                confidence=1.0,
                attributes={"ordinal": section["ordinal"], "document_id": document_id},
            )
        )
        relationships.append(
            GraphRelationship(
                relationship_id=_stable_identifier("rel", document_id, section_id, "has_section"),
                source_id=document_id,
                target_id=section_id,
                relation_type="has_section",
                confidence=1.0,
                attributes={"ordinal": section["ordinal"]},
            )
        )

    for rule in rules:
        rule_id = rule["rule_id"]
        section_id = rule["section_id"]
        entities.append(
            GraphEntity(
                entity_id=rule_id,
                entity_type="policy_rule",
                name=rule["text"][:120],
                confidence=0.9,
                attributes={
                    "text": rule["text"],
                    "rule_type": rule["rule_type"],
                    "modality": rule["modality"],
                    "section_id": section_id,
                    "section_title": rule["section_title"],
                    "ordinal": rule["ordinal"],
                    "document_id": document_id,
                },
            )
        )
        relationships.extend(
            [
                GraphRelationship(
                    relationship_id=_stable_identifier("rel", section_id, rule_id, "contains_rule"),
                    source_id=section_id,
                    target_id=rule_id,
                    relation_type="contains_rule",
                    confidence=1.0,
                    attributes={"ordinal": rule["ordinal"]},
                ),
                GraphRelationship(
                    relationship_id=_stable_identifier("rel", document_id, rule_id, "has_rule"),
                    source_id=document_id,
                    target_id=rule_id,
                    relation_type="has_rule",
                    confidence=1.0,
                    attributes={"rule_type": rule["rule_type"]},
                ),
            ]
        )

        upstream_entities = extractor.extract_entities(rule["text"])
        concepts_for_rule: List[str] = []

        for upstream_entity in upstream_entities:
            entity_type, name, confidence, attributes = _serialize_upstream_entity(upstream_entity)
            if not name:
                continue
            dedupe_key = (entity_type, _normalize_name(name))
            concept_id = concept_ids.get(dedupe_key)
            if concept_id is None:
                concept_id = _stable_identifier("concept", entity_type, name)
                concept_ids[dedupe_key] = concept_id
                entities.append(
                    GraphEntity(
                        entity_id=concept_id,
                        entity_type=entity_type or "concept",
                        name=name,
                        confidence=confidence,
                        attributes=attributes,
                    )
                )
            concepts_for_rule.append(concept_id)
            relationships.append(
                GraphRelationship(
                    relationship_id=_stable_identifier("rel", rule_id, concept_id, "mentions"),
                    source_id=rule_id,
                    target_id=concept_id,
                    relation_type="mentions",
                    confidence=confidence,
                    attributes={"section_title": rule["section_title"]},
                )
            )

        unique_concepts_for_rule: List[str] = []
        for concept_id in concepts_for_rule:
            if concept_id not in unique_concepts_for_rule:
                unique_concepts_for_rule.append(concept_id)
        for source_id, target_id in zip(unique_concepts_for_rule, unique_concepts_for_rule[1:]):
            relationships.append(
                GraphRelationship(
                    relationship_id=_stable_identifier("rel", source_id, target_id, "co_mentioned_in_rule", rule_id),
                    source_id=source_id,
                    target_id=target_id,
                    relation_type="co_mentioned_in_rule",
                    confidence=0.6,
                    attributes={"derived_from_rule_id": rule_id},
                )
            )

    payload = GraphPayload(
        status="success",
        source_id=document_id,
        entities=entities,
        relationships=relationships,
        metadata={
            "document_id": document_id,
            "document_title": resolved_title,
            "source_path": str(source_path.resolve()),
            "backend": backend,
            "text_length": len(text),
            "section_count": len(sections),
            "rule_count": len(rules),
        },
    ).as_dict()
    payload["document"] = {
        "document_id": document_id,
        "title": resolved_title,
        "source_path": str(source_path.resolve()),
        "backend": backend,
    }
    payload["rules"] = rules
    if include_text:
        payload["text"] = text

    return with_adapter_metadata(
        payload,
        operation="extract_policy_rules_from_pdf",
        backend_available=True,
        implementation_status="implemented",
        extra_metadata={"backend": backend, "source_path": str(source_path.resolve())},
    )


def build_policy_rule_corpus(
    pdf_paths: Iterable[str],
    *,
    backend: str = "markitdown",
    include_text: bool = False,
) -> Dict[str, Any]:
    pdf_paths = list(pdf_paths)
    document_results: List[Dict[str, Any]] = []
    merged_entities: Dict[str, Dict[str, Any]] = {}
    merged_relationships: Dict[str, Dict[str, Any]] = {}
    errors: List[Dict[str, Any]] = []

    for pdf_path in pdf_paths:
        document_result = extract_policy_rules_from_pdf(pdf_path, backend=backend, include_text=include_text)
        document_results.append(document_result)
        if document_result.get("status") != "success":
            errors.append({"pdf_path": pdf_path, "error": document_result.get("error", "")})
            continue
        for entity in document_result.get("entities", []) or []:
            entity_id = str(entity.get("id") or "")
            if entity_id and entity_id not in merged_entities:
                merged_entities[entity_id] = entity
        for relationship in document_result.get("relationships", []) or []:
            relationship_id = str(relationship.get("id") or "")
            if relationship_id and relationship_id not in merged_relationships:
                merged_relationships[relationship_id] = relationship

    corpus_id = _stable_identifier("corpus", *[str(Path(path).resolve()) for path in pdf_paths])
    corpus_payload = GraphPayload(
        status="success" if not errors else "partial_success",
        source_id=corpus_id,
        entities=[
            GraphEntity(
                entity_id=corpus_id,
                entity_type="policy_corpus",
                name="HACC Policy Corpus",
                confidence=1.0,
                attributes={"document_count": len(document_results)},
            )
        ]
        + [
            GraphEntity(
                entity_id=entity["id"],
                entity_type=entity["type"],
                name=entity.get("name", ""),
                confidence=float(entity.get("confidence", 0.0) or 0.0),
                attributes=dict(entity.get("attributes", {}) or {}),
            )
            for entity in merged_entities.values()
        ],
        relationships=[
            GraphRelationship(
                relationship_id=_stable_identifier("rel", corpus_id, result.get("source_id", ""), "contains_document"),
                source_id=corpus_id,
                target_id=str(result.get("source_id", "") or ""),
                relation_type="contains_document",
                confidence=1.0,
                attributes={},
            )
            for result in document_results
            if result.get("status") == "success" and result.get("source_id")
        ]
        + [
            GraphRelationship(
                relationship_id=relationship["id"],
                source_id=relationship["source_id"],
                target_id=relationship["target_id"],
                relation_type=relationship["relation_type"],
                confidence=float(relationship.get("confidence", 0.0) or 0.0),
                attributes=dict(relationship.get("attributes", {}) or {}),
            )
            for relationship in merged_relationships.values()
        ],
        metadata={
            "document_count": len(document_results),
            "successful_documents": sum(1 for result in document_results if result.get("status") == "success"),
            "failed_documents": len(errors),
        },
    ).as_dict()

    return with_adapter_metadata(
        {
            "status": "success" if not errors else "partial_success",
            "documents": document_results,
            "errors": errors,
            "corpus_graph": corpus_payload,
        },
        operation="build_policy_rule_corpus",
        backend_available=POLICY_RULES_AVAILABLE,
        degraded_reason=POLICY_RULES_ERROR if not POLICY_RULES_AVAILABLE else None,
        implementation_status="implemented" if POLICY_RULES_AVAILABLE else "unavailable",
        extra_metadata={"backend": backend},
    )
