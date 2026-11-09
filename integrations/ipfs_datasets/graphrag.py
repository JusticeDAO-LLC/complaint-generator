from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .loader import import_attr_optional, run_async_compat
from .types import with_adapter_metadata


OntologyGenerator, _generator_error = import_attr_optional(
    "ipfs_datasets_py.optimizers.graphrag",
    "OntologyGenerator",
)
LogicValidator, _validator_error = import_attr_optional(
    "ipfs_datasets_py.optimizers.graphrag",
    "LogicValidator",
)
OntologyMediator, _mediator_error = import_attr_optional(
    "ipfs_datasets_py.optimizers.graphrag",
    "OntologyMediator",
)
OntologyPipeline, _pipeline_error = import_attr_optional(
    "ipfs_datasets_py.optimizers.graphrag",
    "OntologyPipeline",
)
_pdf_ingest_to_graphrag_async, _pdf_ingest_error = import_attr_optional(
    "ipfs_datasets_py.mcp_server.tools.pdf_tools.pdf_ingest_to_graphrag",
    "pdf_ingest_to_graphrag",
)
_pdf_extract_entities_async, _pdf_extract_entities_error = import_attr_optional(
    "ipfs_datasets_py.mcp_server.tools.pdf_tools.pdf_extract_entities",
    "pdf_extract_entities",
)
_pdf_analyze_relationships_async, _pdf_relationships_error = import_attr_optional(
    "ipfs_datasets_py.mcp_server.tools.pdf_tools.pdf_analyze_relationships",
    "pdf_analyze_relationships",
)
_pdf_cross_document_analysis_async, _pdf_cross_document_error = import_attr_optional(
    "ipfs_datasets_py.mcp_server.tools.pdf_tools.pdf_cross_document_analysis",
    "pdf_cross_document_analysis",
)
_pdf_batch_process_async, _pdf_batch_error = import_attr_optional(
    "ipfs_datasets_py.mcp_server.tools.pdf_tools.pdf_batch_process",
    "pdf_batch_process",
)
_pdf_query_knowledge_graph_async, _pdf_query_error = import_attr_optional(
    "ipfs_datasets_py.mcp_server.tools.pdf_tools.pdf_query_knowledge_graph",
    "pdf_query_knowledge_graph",
)

GRAPHRAG_AVAILABLE = any(
    value is not None
    for value in (
        OntologyGenerator,
        LogicValidator,
        OntologyMediator,
        OntologyPipeline,
        _pdf_ingest_to_graphrag_async,
        _pdf_extract_entities_async,
        _pdf_analyze_relationships_async,
        _pdf_cross_document_analysis_async,
        _pdf_batch_process_async,
        _pdf_query_knowledge_graph_async,
    )
)
GRAPHRAG_ERROR = (
    _generator_error
    or _validator_error
    or _mediator_error
    or _pipeline_error
    or _pdf_ingest_error
    or _pdf_extract_entities_error
    or _pdf_relationships_error
    or _pdf_cross_document_error
    or _pdf_batch_error
    or _pdf_query_error
)


def _run_pdf_facade(
    operation: str,
    backend: Any | None,
    *,
    payload: Optional[Dict[str, Any]] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if backend is None:
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "result": None,
            },
            operation=operation,
            backend_available=False,
            degraded_reason=GRAPHRAG_ERROR,
            implementation_status="unavailable",
            extra_metadata=extra_metadata,
        )
    try:
        result = run_async_compat(backend(**(payload or {})))
    except Exception as exc:
        return with_adapter_metadata(
            {
                "status": "error",
                "result": None,
                "error": str(exc),
            },
            operation=operation,
            backend_available=True,
            implementation_status="error",
            extra_metadata=extra_metadata,
        )

    normalized = result if isinstance(result, dict) else {"status": "success", "result": result}
    return with_adapter_metadata(
        normalized,
        operation=operation,
        backend_available=True,
        implementation_status="implemented",
        extra_metadata=extra_metadata,
    )


# ---------------------------------------------------------------------------
# Local ontology extraction helpers (used when the upstream backend is absent
# or when it returns "not_implemented" because it lacks the expected methods).
# ---------------------------------------------------------------------------

_ENTITY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")
_RELATION_VERB_RE = re.compile(
    r"\b(report(?:ed)?|terminat(?:ed)?|discriminat(?:ed)?|retaliat(?:ed)?|"
    r"violat(?:ed)?|breach(?:ed)?|fail(?:ed)?|notif(?:ied)?|request(?:ed)?|"
    r"discriminat(?:ed)?|employ(?:ed)?|harass(?:ed)?|demot(?:ed)?|"
    r"harm(?:ed)?|seek(?:s)?|allege(?:s)?|file[ds]?)\b",
    re.IGNORECASE,
)
_CONCEPT_KEYWORDS = frozenset(
    [
        "discrimination", "retaliation", "harassment", "termination", "demotion",
        "hostile", "complaint", "violation", "damages", "relief", "employment",
        "protected", "class", "disability", "race", "gender", "age", "religion",
        "whistleblower", "safety", "duty", "obligation", "prohibition",
    ]
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _build_local_ontology(text: str) -> Dict[str, Any]:
    """Build a minimal ontology from *text* using regex heuristics.

    Returns a dict with ``entities``, ``relations``, ``concepts``, and
    ``metadata`` keys compatible with the standard ontology schema used
    elsewhere in the pipeline.
    """
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    seen_entities: Dict[str, int] = {}
    relations: List[Dict[str, Any]] = []
    seen_concepts: Dict[str, int] = {}

    for sentence in sentences:
        entities = _ENTITY_RE.findall(sentence)
        verbs = _RELATION_VERB_RE.findall(sentence)

        for entity in entities:
            seen_entities[entity] = seen_entities.get(entity, 0) + 1

        if len(entities) >= 2 and verbs:
            for verb in verbs:
                relations.append(
                    {
                        "subject": entities[0],
                        "predicate": verb.lower(),
                        "object": entities[1],
                        "source_sentence": sentence,
                    }
                )

        lowered = sentence.lower()
        for keyword in _CONCEPT_KEYWORDS:
            if keyword in lowered:
                seen_concepts[keyword] = seen_concepts.get(keyword, 0) + 1

    entities_list = [
        {"name": name, "frequency": count, "type": "named_entity"}
        for name, count in sorted(seen_entities.items(), key=lambda kv: -kv[1])
    ]
    concepts_list = [
        {"name": name, "frequency": count, "type": "legal_concept"}
        for name, count in sorted(seen_concepts.items(), key=lambda kv: -kv[1])
    ]

    return {
        "entities": entities_list,
        "relations": relations,
        "concepts": concepts_list,
        "entity_count": len(entities_list),
        "relation_count": len(relations),
        "concept_count": len(concepts_list),
        "source": "local_regex_fallback",
    }


def _validate_ontology_locally(ontology: Any) -> Dict[str, Any]:
    """Apply basic structural validation to *ontology*.

    Checks that the ontology is a non-empty mapping with at least one of the
    standard top-level keys (``entities``, ``relations``, ``concepts``).
    Returns a validation result dict with ``valid``, ``issues``, and
    ``field_presence`` keys.
    """
    issues: List[str] = []
    field_presence: Dict[str, bool] = {}

    if not isinstance(ontology, dict):
        return {
            "valid": False,
            "issues": ["ontology must be a dict"],
            "field_presence": {},
        }
    if not ontology:
        return {
            "valid": False,
            "issues": ["ontology is empty"],
            "field_presence": {},
        }

    for field in ("entities", "relations", "concepts"):
        field_presence[field] = field in ontology

    if not any(field_presence.values()):
        issues.append("ontology is missing required keys: entities, relations, or concepts")

    entities = ontology.get("entities")
    if entities is not None and not isinstance(entities, list):
        issues.append("'entities' must be a list")

    relations = ontology.get("relations")
    if relations is not None and not isinstance(relations, list):
        issues.append("'relations' must be a list")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "field_presence": field_presence,
        "entity_count": len(ontology.get("entities") or []),
        "relation_count": len(ontology.get("relations") or []),
        "concept_count": len(ontology.get("concepts") or []),
    }


def _refine_ontology_locally(ontology: Any, *, rounds: int = 1) -> Dict[str, Any]:
    """Apply lightweight local refinement to *ontology*.

    Each round deduplicates entity and concept lists by normalised name and
    merges duplicate (subject, predicate, object) relation triples.  The
    refined ontology is returned as a new dict.
    """
    if not isinstance(ontology, dict):
        return {"status": "skipped", "reason": "ontology is not a dict", "refined": ontology}

    entities = list(ontology.get("entities") or [])
    relations = list(ontology.get("relations") or [])
    concepts = list(ontology.get("concepts") or [])

    for _round in range(max(rounds, 1)):
        # Deduplicate entities by normalised name
        seen_entity_names: Dict[str, Dict[str, Any]] = {}
        for entity in entities:
            key = str(entity.get("name") or "").strip().lower()
            if key:
                if key in seen_entity_names:
                    existing = seen_entity_names[key]
                    existing["frequency"] = int(existing.get("frequency") or 1) + int(entity.get("frequency") or 1)
                else:
                    seen_entity_names[key] = dict(entity)
        entities = list(seen_entity_names.values())

        # Deduplicate relations by (subject, predicate, object) triple
        seen_relation_keys: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for relation in relations:
            key = (
                str(relation.get("subject") or "").strip().lower(),
                str(relation.get("predicate") or "").strip().lower(),
                str(relation.get("object") or "").strip().lower(),
            )
            if key not in seen_relation_keys:
                seen_relation_keys[key] = dict(relation)
        relations = list(seen_relation_keys.values())

        # Deduplicate concepts
        seen_concept_names: Dict[str, Dict[str, Any]] = {}
        for concept in concepts:
            key = str(concept.get("name") or "").strip().lower()
            if key:
                if key in seen_concept_names:
                    existing = seen_concept_names[key]
                    existing["frequency"] = int(existing.get("frequency") or 1) + int(concept.get("frequency") or 1)
                else:
                    seen_concept_names[key] = dict(concept)
        concepts = list(seen_concept_names.values())

    refined = dict(ontology)
    refined["entities"] = entities
    refined["relations"] = relations
    refined["concepts"] = concepts
    refined["entity_count"] = len(entities)
    refined["relation_count"] = len(relations)
    refined["concept_count"] = len(concepts)
    refined["refined_rounds"] = rounds
    refined["source"] = refined.get("source", "unknown") + "+local_refinement"
    return refined


def create_ontology_generator() -> Any:
    if OntologyGenerator is None:
        return None
    return OntologyGenerator()


def build_ontology(text: str, config: Any | None = None) -> Dict[str, Any]:
    try:
        generator = create_ontology_generator()
    except Exception as exc:
        return with_adapter_metadata(
            {
                "status": "error",
                "ontology": None,
                "metadata": {"text_length": len(text), "error": str(exc)},
            },
            operation="build_ontology",
            backend_available=True,
            implementation_status="error",
        )
    if generator is None:
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "ontology": None,
                "metadata": {"text_length": len(text)},
            },
            operation="build_ontology",
            backend_available=False,
            degraded_reason=GRAPHRAG_ERROR,
            implementation_status="unavailable",
        )
    if hasattr(generator, "generate"):
        try:
            result = generator.generate(text, config=config) if config is not None else generator.generate(text)
            return with_adapter_metadata(
                {
                    "status": "success",
                    "ontology": result,
                    "metadata": {"text_length": len(text)},
                },
                operation="build_ontology",
                backend_available=True,
                implementation_status="implemented",
            )
        except Exception as exc:
            return with_adapter_metadata(
                {
                    "status": "error",
                    "ontology": None,
                    "metadata": {"text_length": len(text), "error": str(exc)},
                },
                operation="build_ontology",
                backend_available=True,
                implementation_status="error",
            )
    return with_adapter_metadata(
        {
            "status": "success",
            "ontology": _build_local_ontology(str(text or "")),
            "metadata": {"text_length": len(text), "source": "local_regex_fallback"},
        },
        operation="build_ontology",
        backend_available=True,
        implementation_status="implemented",
    )


def validate_ontology(ontology: Any) -> Dict[str, Any]:
    if LogicValidator is None:
        return with_adapter_metadata(
            {"status": "unavailable", "result": None},
            operation="validate_ontology",
            backend_available=False,
            degraded_reason=GRAPHRAG_ERROR,
            implementation_status="unavailable",
        )
    try:
        validator = LogicValidator()
    except Exception as exc:
        return with_adapter_metadata(
            {"status": "error", "result": None, "error": str(exc)},
            operation="validate_ontology",
            backend_available=True,
            implementation_status="error",
        )

    for method_name in ("validate_ontology", "validate"):
        method = getattr(validator, method_name, None)
        if callable(method):
            try:
                return with_adapter_metadata(
                    {"status": "success", "result": method(ontology)},
                    operation="validate_ontology",
                    backend_available=True,
                    implementation_status="implemented",
                )
            except Exception as exc:
                return with_adapter_metadata(
                    {"status": "error", "result": None, "error": str(exc)},
                    operation="validate_ontology",
                    backend_available=True,
                    implementation_status="error",
                )
    validation_result = _validate_ontology_locally(ontology)
    return with_adapter_metadata(
        {
            "status": "success",
            "result": validation_result,
            "valid": validation_result["valid"],
        },
        operation="validate_ontology",
        backend_available=True,
        implementation_status="implemented",
    )


def run_refinement_cycle(ontology: Any, *, rounds: int = 1) -> Dict[str, Any]:
    if OntologyMediator is None:
        return with_adapter_metadata(
            {"status": "unavailable", "result": None},
            operation="run_refinement_cycle",
            backend_available=False,
            degraded_reason=GRAPHRAG_ERROR,
            implementation_status="unavailable",
            extra_metadata={"rounds": rounds},
        )
    try:
        mediator = OntologyMediator()
    except Exception as exc:
        return with_adapter_metadata(
            {"status": "error", "result": None, "error": str(exc)},
            operation="run_refinement_cycle",
            backend_available=True,
            implementation_status="error",
            extra_metadata={"rounds": rounds},
        )

    for method_name in ("run_agentic_refinement_cycle", "refine_ontology"):
        method = getattr(mediator, method_name, None)
        if callable(method):
            try:
                if method_name == "run_agentic_refinement_cycle":
                    return with_adapter_metadata(
                        {"status": "success", "result": method(ontology, rounds=rounds)},
                        operation="run_refinement_cycle",
                        backend_available=True,
                        implementation_status="implemented",
                        extra_metadata={"rounds": rounds},
                    )
                return with_adapter_metadata(
                    {"status": "success", "result": method(ontology)},
                    operation="run_refinement_cycle",
                    backend_available=True,
                    implementation_status="implemented",
                    extra_metadata={"rounds": rounds},
                )
            except Exception as exc:
                return with_adapter_metadata(
                    {"status": "error", "result": None, "error": str(exc)},
                    operation="run_refinement_cycle",
                    backend_available=True,
                    implementation_status="error",
                    extra_metadata={"rounds": rounds},
                )
    refined = _refine_ontology_locally(ontology, rounds=rounds)
    return with_adapter_metadata(
        {"status": "success", "result": refined},
        operation="run_refinement_cycle",
        backend_available=True,
        implementation_status="implemented",
        extra_metadata={"rounds": rounds},
    )


def ingest_pdf_to_graphrag(
    pdf_source: Any,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    enable_ocr: bool = True,
    target_llm: str = "gpt-5.3-codex",
    chunk_strategy: str = "semantic",
    enable_cross_document: bool = True,
) -> Dict[str, Any]:
    return _run_pdf_facade(
        "ingest_pdf_to_graphrag",
        _pdf_ingest_to_graphrag_async,
        payload={
            "pdf_source": pdf_source,
            "metadata": metadata,
            "enable_ocr": enable_ocr,
            "target_llm": target_llm,
            "chunk_strategy": chunk_strategy,
            "enable_cross_document": enable_cross_document,
        },
        extra_metadata={
            "pdf_source": str(pdf_source),
            "enable_ocr": enable_ocr,
            "target_llm": target_llm,
            "chunk_strategy": chunk_strategy,
            "enable_cross_document": enable_cross_document,
        },
    )


def extract_pdf_entities(
    pdf_source: Any,
    *,
    entity_types: Optional[list[str]] = None,
    extraction_method: str = "hybrid",
    confidence_threshold: float = 0.7,
    include_relationships: bool = True,
    context_window: int = 3,
    custom_patterns: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    return _run_pdf_facade(
        "extract_pdf_entities",
        _pdf_extract_entities_async,
        payload={
            "pdf_source": pdf_source,
            "entity_types": entity_types,
            "extraction_method": extraction_method,
            "confidence_threshold": confidence_threshold,
            "include_relationships": include_relationships,
            "context_window": context_window,
            "custom_patterns": custom_patterns,
        },
        extra_metadata={
            "pdf_source": str(pdf_source),
            "entity_types": list(entity_types or []),
            "extraction_method": extraction_method,
        },
    )


def analyze_pdf_relationships(
    document_id: str,
    *,
    analysis_type: str = "comprehensive",
    include_cross_document: bool = True,
    relationship_types: Optional[list[str]] = None,
    min_confidence: float = 0.6,
    max_relationships: int = 100,
) -> Dict[str, Any]:
    return _run_pdf_facade(
        "analyze_pdf_relationships",
        _pdf_analyze_relationships_async,
        payload={
            "document_id": document_id,
            "analysis_type": analysis_type,
            "include_cross_document": include_cross_document,
            "relationship_types": relationship_types,
            "min_confidence": min_confidence,
            "max_relationships": max_relationships,
        },
        extra_metadata={
            "document_id": document_id,
            "analysis_type": analysis_type,
        },
    )


def cross_analyze_pdf_documents(
    document_ids: list[str],
    *,
    analysis_types: Optional[list[str]] = None,
    similarity_threshold: float = 0.75,
    max_connections: int = 100,
    temporal_analysis: bool = True,
    include_visualizations: bool = False,
    output_format: str = "detailed",
) -> Dict[str, Any]:
    return _run_pdf_facade(
        "cross_analyze_pdf_documents",
        _pdf_cross_document_analysis_async,
        payload={
            "document_ids": document_ids,
            "analysis_types": analysis_types or ["entities", "themes", "citations"],
            "similarity_threshold": similarity_threshold,
            "max_connections": max_connections,
            "temporal_analysis": temporal_analysis,
            "include_visualizations": include_visualizations,
            "output_format": output_format,
        },
        extra_metadata={
            "document_count": len(document_ids),
            "output_format": output_format,
        },
    )


def batch_process_pdfs(
    pdf_sources: list[Any],
    *,
    batch_size: int = 5,
    parallel_workers: int = 3,
    enable_ocr: bool = True,
    target_llm: str = "gpt-5.3-codex",
    chunk_strategy: str = "semantic",
    enable_cross_document: bool = True,
    output_format: str = "detailed",
) -> Dict[str, Any]:
    return _run_pdf_facade(
        "batch_process_pdfs",
        _pdf_batch_process_async,
        payload={
            "pdf_sources": pdf_sources,
            "batch_size": batch_size,
            "parallel_workers": parallel_workers,
            "enable_ocr": enable_ocr,
            "target_llm": target_llm,
            "chunk_strategy": chunk_strategy,
            "enable_cross_document": enable_cross_document,
            "output_format": output_format,
        },
        extra_metadata={
            "pdf_count": len(pdf_sources),
            "batch_size": batch_size,
            "parallel_workers": parallel_workers,
        },
    )


def query_pdf_knowledge_graph(
    graph_id: str,
    query: str,
    *,
    query_type: str = "sparql",
    max_results: int = 100,
    include_metadata: bool = True,
    return_subgraph: bool = False,
) -> Dict[str, Any]:
    return _run_pdf_facade(
        "query_pdf_knowledge_graph",
        _pdf_query_knowledge_graph_async,
        payload={
            "graph_id": graph_id,
            "query": query,
            "query_type": query_type,
            "max_results": max_results,
            "include_metadata": include_metadata,
            "return_subgraph": return_subgraph,
        },
        extra_metadata={
            "graph_id": graph_id,
            "query_type": query_type,
        },
    )


# ---------------------------------------------------------------------------
# Claim-type ontology quality profiles
# Maps complaint type to expected entity keywords, relation predicates, and
# legal concept keywords used for scoring and gap detection.
# ---------------------------------------------------------------------------

_CLAIM_ONTOLOGY_PROFILES: Dict[str, Dict[str, Any]] = {
    "employment_discrimination": {
        "expected_entity_keywords": [
            "employee", "employer", "supervisor", "manager", "hr",
            "complainant", "company", "coworker", "plaintiff", "defendant",
        ],
        "expected_relation_predicates": [
            "terminated", "discriminated", "harassed", "demoted",
            "reported", "employed", "notified", "violated",
        ],
        "expected_concept_keywords": [
            "discrimination", "retaliation", "harassment", "termination",
            "demotion", "protected", "race", "gender", "disability",
            "religion", "age", "employment", "adverse",
        ],
    },
    "housing_discrimination": {
        "expected_entity_keywords": [
            "tenant", "landlord", "property", "applicant", "complainant",
            "housing", "manager", "unit", "plaintiff", "defendant",
        ],
        "expected_relation_predicates": [
            "denied", "evicted", "discriminated", "violated", "refused",
            "harassed", "reported", "notified",
        ],
        "expected_concept_keywords": [
            "discrimination", "housing", "eviction", "protected", "race",
            "disability", "familial", "religion", "national origin",
            "lease", "denial", "accommodation",
        ],
    },
    "retaliation": {
        "expected_entity_keywords": [
            "employee", "employer", "complainant", "supervisor", "plaintiff",
            "defendant", "manager", "company",
        ],
        "expected_relation_predicates": [
            "retaliated", "terminated", "demoted", "reported", "complained",
            "violated", "harassed", "notified",
        ],
        "expected_concept_keywords": [
            "retaliation", "protected", "complaint", "termination",
            "discrimination", "whistleblower", "adverse", "causation",
        ],
    },
    "fair_housing": {
        "expected_entity_keywords": [
            "tenant", "landlord", "applicant", "housing", "complainant",
            "property", "unit",
        ],
        "expected_relation_predicates": [
            "denied", "discriminated", "violated", "refused",
            "harassed", "reported",
        ],
        "expected_concept_keywords": [
            "fair housing", "discrimination", "protected", "accommodation",
            "disability", "familial", "race", "national origin",
        ],
    },
}

_DEFAULT_CLAIM_PROFILE: Dict[str, Any] = {
    "expected_entity_keywords": [
        "complainant", "defendant", "respondent", "plaintiff",
    ],
    "expected_relation_predicates": [
        "violated", "harassed", "discriminated", "reported",
    ],
    "expected_concept_keywords": [
        "discrimination", "violation", "complaint", "protected",
    ],
}

_QUALITY_GRADE_THRESHOLDS = [
    (0.85, "A"),
    (0.70, "B"),
    (0.55, "C"),
    (0.40, "D"),
    (0.0,  "F"),
]


def _ontology_quality_grade(score: float) -> str:
    for threshold, grade in _QUALITY_GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _score_coverage(
    items: List[str],
    expected_keywords: List[str],
) -> Tuple[float, List[str], List[str]]:
    """Return (coverage_ratio, matched, missing) for *items* against *expected_keywords*."""
    if not expected_keywords:
        return 1.0, [], []
    lowered = [str(i).lower() for i in items]
    matched = []
    missing = []
    for keyword in expected_keywords:
        kl = keyword.lower()
        if any(kl in item for item in lowered):
            matched.append(keyword)
        else:
            missing.append(keyword)
    return len(matched) / len(expected_keywords), matched, missing


def score_ontology_support_paths(
    ontology: Any,
    claim_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Score an ontology's support quality for *claim_type*.

    Returns a mediator-consumable quality payload with per-dimension scores
    (entity coverage, relation density, concept completeness), an
    ``overall_quality_score`` (0.0–1.0), a letter ``grade``, and a list of
    ``gap_signals`` identifying weak areas.

    Works in degraded mode — passes through to the local ontology helpers
    when the upstream GraphRAG backend is unavailable.
    """
    operation = "score_ontology_support_paths"
    if not isinstance(ontology, dict) or not ontology:
        return with_adapter_metadata(
            {
                "status": "error",
                "error": "ontology must be a non-empty dict",
                "overall_quality_score": 0.0,
                "grade": "F",
                "gap_signals": [
                    {
                        "gap_type": "empty_ontology",
                        "description": "Ontology is empty or not a dict",
                        "follow_up_action": "build_ontology_from_evidence",
                    }
                ],
            },
            operation=operation,
            backend_available=GRAPHRAG_AVAILABLE,
            degraded_reason=GRAPHRAG_ERROR if not GRAPHRAG_AVAILABLE else None,
            implementation_status="implemented",
        )

    profile = _CLAIM_ONTOLOGY_PROFILES.get(str(claim_type or "").lower(), _DEFAULT_CLAIM_PROFILE)

    entities = ontology.get("entities") or []
    relations = ontology.get("relations") or []
    concepts = ontology.get("concepts") or []

    entity_names = [str(e.get("name") or e) for e in entities if e]
    relation_predicates = [str(r.get("predicate") or r) for r in relations if r]
    concept_names = [str(c.get("name") or c) for c in concepts if c]

    entity_score, entity_matched, entity_missing = _score_coverage(
        entity_names, profile["expected_entity_keywords"]
    )
    relation_score, relation_matched, relation_missing = _score_coverage(
        relation_predicates, profile["expected_relation_predicates"]
    )
    concept_score, concept_matched, concept_missing = _score_coverage(
        concept_names, profile["expected_concept_keywords"]
    )

    # Relation density: ratio of actual relation triples to all possible ordered entity
    # pairs (excluding self-loops), treating the graph as directed.  Self-loops are
    # excluded because an entity pointing to itself carries no meaningful relational
    # information in a legal ontology.  A directed model is used because legal-ontology
    # relations (e.g. "employer→employee", "policy→violation") are inherently
    # asymmetric, so the directed pair count (n*(n-1)) better reflects the space of
    # meaningful predicate assertions than the undirected formula (n*(n-1)/2).  The
    # score is capped at 1.0 for outlier inputs.
    entity_count = max(len(entities), 1)
    max_pairs = max(entity_count * (entity_count - 1), 1)
    relation_density_raw = len(relations) / max_pairs
    relation_density_score = min(relation_density_raw, 1.0)

    # Weighted composite score: entity 35%, concept 35%, relation quality 20%, density 10%
    overall_quality_score = round(
        entity_score * 0.35
        + concept_score * 0.35
        + relation_score * 0.20
        + relation_density_score * 0.10,
        4,
    )
    grade = _ontology_quality_grade(overall_quality_score)

    # Build gap signals
    gap_signals: List[Dict[str, Any]] = []
    if entity_missing:
        gap_signals.append({
            "gap_type": "missing_entity_coverage",
            "description": f"Ontology is missing expected entity types: {', '.join(entity_missing[:5])}",
            "missing_keywords": entity_missing,
            "follow_up_action": "enrich_entities_from_evidence",
        })
    if concept_missing:
        gap_signals.append({
            "gap_type": "missing_concept_coverage",
            "description": f"Ontology is missing expected legal concepts: {', '.join(concept_missing[:5])}",
            "missing_keywords": concept_missing,
            "follow_up_action": "acquire_legal_authority_for_concept",
        })
    if relation_missing:
        gap_signals.append({
            "gap_type": "missing_relation_predicates",
            "description": f"Ontology is missing expected relation predicates: {', '.join(relation_missing[:5])}",
            "missing_keywords": relation_missing,
            "follow_up_action": "extract_relations_from_evidence",
        })
    if relation_density_score < 0.1 and len(entities) > 1:
        gap_signals.append({
            "gap_type": "low_relation_density",
            "description": "Ontology has very few relations relative to entity count; graph is sparse",
            "follow_up_action": "run_graphrag_relation_extraction",
        })

    return with_adapter_metadata(
        {
            "status": "success",
            "claim_type": claim_type,
            "entity_coverage_score": round(entity_score, 4),
            "relation_score": round(relation_score, 4),
            "concept_completeness_score": round(concept_score, 4),
            "relation_density_score": round(relation_density_score, 4),
            "overall_quality_score": overall_quality_score,
            "grade": grade,
            "entity_matched": entity_matched,
            "entity_missing": entity_missing,
            "relation_matched": relation_matched,
            "relation_missing": relation_missing,
            "concept_matched": concept_matched,
            "concept_missing": concept_missing,
            "gap_signal_count": len(gap_signals),
            "gap_signals": gap_signals,
            "entity_count": len(entities),
            "relation_count": len(relations),
            "concept_count": len(concepts),
        },
        operation=operation,
        backend_available=GRAPHRAG_AVAILABLE,
        degraded_reason=GRAPHRAG_ERROR if not GRAPHRAG_AVAILABLE else None,
        implementation_status="implemented",
        extra_metadata={"claim_type": claim_type},
    )


def identify_ontology_gaps(
    ontology: Any,
    claim_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Identify gaps in *ontology* relative to the expected profile for *claim_type*.

    Returns a structured payload with a ``gaps`` list suitable for consumption
    by follow-up planning.  Each gap entry carries ``gap_type``, ``description``,
    ``severity`` (blocking/moderate/minor), and ``follow_up_action``.
    """
    operation = "identify_ontology_gaps"
    scored = score_ontology_support_paths(ontology, claim_type=claim_type)

    gap_signals = scored.get("gap_signals") or []
    overall_score = float(scored.get("overall_quality_score") or 0.0)

    enriched_gaps: List[Dict[str, Any]] = []
    for signal in gap_signals:
        gap_type = signal.get("gap_type", "unknown")
        if gap_type in ("empty_ontology", "missing_entity_coverage") and overall_score < 0.3:
            severity = "blocking"
        elif gap_type in ("missing_concept_coverage", "missing_relation_predicates"):
            severity = "moderate"
        else:
            severity = "minor"
        enriched_gaps.append({
            "gap_type": gap_type,
            "description": signal.get("description", ""),
            "severity": severity,
            "follow_up_action": signal.get("follow_up_action", ""),
            "missing_keywords": signal.get("missing_keywords", []),
        })

    return with_adapter_metadata(
        {
            "status": "success",
            "claim_type": claim_type,
            "overall_quality_score": overall_score,
            "grade": scored.get("grade", "F"),
            "gap_count": len(enriched_gaps),
            "gaps": enriched_gaps,
            "has_blocking_gaps": any(g["severity"] == "blocking" for g in enriched_gaps),
            "has_gaps": len(enriched_gaps) > 0,
            "entity_coverage_score": scored.get("entity_coverage_score", 0.0),
            "concept_completeness_score": scored.get("concept_completeness_score", 0.0),
            "relation_density_score": scored.get("relation_density_score", 0.0),
        },
        operation=operation,
        backend_available=GRAPHRAG_AVAILABLE,
        degraded_reason=GRAPHRAG_ERROR if not GRAPHRAG_AVAILABLE else None,
        implementation_status="implemented",
        extra_metadata={"claim_type": claim_type},
    )


def _clamp_score(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def _support_quality_tier(score: float, *, duplicate_ratio: float, structurally_missing: bool) -> str:
    if structurally_missing:
        return "structurally_missing"
    if duplicate_ratio >= 0.5 and score < 0.75:
        return "duplicate_support"
    if score >= 0.80:
        return "strong_support"
    if score >= 0.55:
        return "moderate_support"
    return "weak_support"


def score_support_path_quality(
    support_path: Any,
    *,
    ontology: Optional[Dict[str, Any]] = None,
    required_support_kinds: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Score one support path using source quality, graph connectivity, and ontology shape."""
    operation = "score_support_path_quality"
    if not isinstance(support_path, dict) or not support_path:
        return with_adapter_metadata(
            {
                "status": "error",
                "error": "support_path must be a non-empty dict",
                "support_quality_score": 0.0,
                "support_quality_tier": "structurally_missing",
                "quality_signals": [],
            },
            operation=operation,
            backend_available=GRAPHRAG_AVAILABLE,
            degraded_reason=GRAPHRAG_ERROR if not GRAPHRAG_AVAILABLE else None,
            implementation_status="implemented",
        )

    metadata = support_path.get("metadata", {}) if isinstance(support_path.get("metadata"), dict) else {}
    support_trace_summary = (
        metadata.get("support_trace_summary", {})
        if isinstance(metadata.get("support_trace_summary"), dict)
        else {}
    )
    graph_trace_summary = (
        metadata.get("graph_trace_summary", {})
        if isinstance(metadata.get("graph_trace_summary"), dict)
        else {}
    )

    fact_ids = support_path.get("fact_ids", []) if isinstance(support_path.get("fact_ids"), list) else []
    support_refs = support_path.get("support_refs", []) if isinstance(support_path.get("support_refs"), list) else []
    support_kinds = support_path.get("support_kinds", []) if isinstance(support_path.get("support_kinds"), list) else []
    if not support_kinds:
        support_kinds = list((support_trace_summary.get("support_by_kind") or {}).keys())
    source_families = support_path.get("source_families", []) if isinstance(support_path.get("source_families"), list) else []

    fact_count = int(support_path.get("fact_count") or len(fact_ids) or support_trace_summary.get("fact_trace_count") or 0)
    support_ref_count = int(support_path.get("support_ref_count") or len(support_refs) or 0)
    trace_count = int(support_path.get("trace_count") or support_trace_summary.get("trace_count") or 0)
    unique_trace_basis = max(len(set(str(ref) for ref in support_refs if ref)), len(set(str(fid) for fid in fact_ids if fid)))
    duplicate_ratio = 0.0
    if trace_count > 1 and unique_trace_basis:
        duplicate_ratio = _clamp_score(1.0 - (unique_trace_basis / trace_count))

    required = [str(kind) for kind in (required_support_kinds or []) if str(kind or "").strip()]
    support_kind_set = {str(kind) for kind in support_kinds if str(kind or "").strip()}
    if required:
        missing_required = [kind for kind in required if kind not in support_kind_set]
        support_kind_score = 1.0 - (len(missing_required) / max(len(required), 1))
    else:
        missing_required = []
        support_kind_score = min(len(support_kind_set) / 2.0, 1.0) if support_kind_set else 0.0

    avg_parse_quality = float(support_trace_summary.get("avg_parse_quality_score") or 0.0)
    if avg_parse_quality > 0:
        source_quality_score = _clamp_score(avg_parse_quality / 100.0)
    elif fact_count:
        source_quality_score = 0.70
    elif support_ref_count:
        source_quality_score = 0.45
    else:
        source_quality_score = 0.0

    graph_id_count = int(support_path.get("graph_id_count") or len(support_path.get("graph_ids", []) or []) or 0)
    graph_trace_count = int(support_path.get("graph_trace_count") or graph_trace_summary.get("traced_link_count") or 0)
    graph_density = graph_trace_count / max(trace_count, 1)
    graph_connectivity_score = _clamp_score((0.60 if graph_id_count else 0.0) + min(graph_density, 1.0) * 0.40)
    if graph_connectivity_score == 0.0 and fact_count:
        graph_connectivity_score = 0.35

    ontology_shape_score = 0.50
    ontology_alignment_score = 0.50
    if isinstance(ontology, dict) and ontology:
        entities = ontology.get("entities") or []
        relations = ontology.get("relations") or ontology.get("relationships") or []
        concepts = ontology.get("concepts") or []
        ontology_shape_score = _clamp_score(
            min(len(entities), 5) / 5.0 * 0.35
            + min(len(relations), 5) / 5.0 * 0.35
            + min(len(concepts), 5) / 5.0 * 0.30
        )
        ontology_terms: List[str] = []
        for item in list(entities) + list(concepts):
            if isinstance(item, dict):
                ontology_terms.append(str(item.get("name") or item.get("label") or ""))
            else:
                ontology_terms.append(str(item))
        relation_terms = [
            str(rel.get("predicate") or rel.get("type") or "")
            for rel in relations
            if isinstance(rel, dict)
        ]
        ontology_terms.extend(relation_terms)
        haystack = " ".join(term.lower() for term in ontology_terms if term)
        path_terms = [*support_kind_set, *[str(family) for family in source_families if family]]
        matched_terms = [term for term in path_terms if term and term.lower() in haystack]
        ontology_alignment_score = _clamp_score(len(matched_terms) / max(len(path_terms), 1)) if path_terms else ontology_shape_score

    raw_score = (
        source_quality_score * 0.35
        + graph_connectivity_score * 0.25
        + support_kind_score * 0.20
        + ontology_shape_score * 0.10
        + ontology_alignment_score * 0.10
    )
    duplicate_penalty = min(duplicate_ratio * 0.25, 0.25)
    support_quality_score = round(_clamp_score(raw_score - duplicate_penalty), 4)
    structurally_missing = fact_count == 0 and support_ref_count == 0
    tier = _support_quality_tier(
        support_quality_score,
        duplicate_ratio=duplicate_ratio,
        structurally_missing=structurally_missing,
    )

    quality_signals: List[Dict[str, Any]] = []
    if missing_required:
        quality_signals.append({
            "signal_type": "missing_required_support_kind",
            "severity": "moderate",
            "missing_support_kinds": missing_required,
            "follow_up_action": "collect_missing_support_kind",
        })
    if graph_connectivity_score < 0.4:
        quality_signals.append({
            "signal_type": "weak_graph_connectivity",
            "severity": "minor",
            "follow_up_action": "persist_or_query_graph_support",
        })
    if source_quality_score < 0.5:
        quality_signals.append({
            "signal_type": "weak_source_quality",
            "severity": "moderate",
            "follow_up_action": "improve_source_parse_quality",
        })
    if duplicate_ratio >= 0.5:
        quality_signals.append({
            "signal_type": "duplicate_support",
            "severity": "minor",
            "duplicate_ratio": round(duplicate_ratio, 4),
            "follow_up_action": "collect_independent_support",
        })
    if structurally_missing:
        quality_signals.append({
            "signal_type": "structurally_missing_support",
            "severity": "blocking",
            "follow_up_action": "collect_initial_support",
        })

    return with_adapter_metadata(
        {
            "status": "success",
            "proof_path_id": str(support_path.get("proof_path_id") or ""),
            "support_quality_score": support_quality_score,
            "support_quality_tier": tier,
            "source_quality_score": round(source_quality_score, 4),
            "graph_connectivity_score": round(graph_connectivity_score, 4),
            "support_kind_score": round(support_kind_score, 4),
            "ontology_shape_score": round(ontology_shape_score, 4),
            "ontology_alignment_score": round(ontology_alignment_score, 4),
            "duplicate_ratio": round(duplicate_ratio, 4),
            "missing_required_support_kinds": missing_required,
            "quality_signals": quality_signals,
            "quality_signal_count": len(quality_signals),
            "fact_count": fact_count,
            "support_ref_count": support_ref_count,
            "trace_count": trace_count,
            "graph_id_count": graph_id_count,
            "graph_trace_count": graph_trace_count,
        },
        operation=operation,
        backend_available=GRAPHRAG_AVAILABLE,
        degraded_reason=GRAPHRAG_ERROR if not GRAPHRAG_AVAILABLE else None,
        implementation_status="implemented",
        extra_metadata={"required_support_kinds": required},
    )


def build_validate_score_ontology(
    text: str,
    *,
    claim_type: Optional[str] = None,
    config: Any | None = None,
    refinement_rounds: int = 1,
) -> Dict[str, Any]:
    """Build, validate, refine, and score an ontology in one adapter call.

    This is the normalized W5.1 workflow surface for complaint phases: callers
    do not need to know whether the upstream GraphRAG backend or local fallback
    produced the ontology, and they always receive validation, quality, and gap
    payloads with adapter metadata.
    """
    operation = "build_validate_score_ontology"
    build_result = build_ontology(text, config=config)
    ontology = build_result.get("ontology") if isinstance(build_result, dict) else None
    if ontology is None:
        ontology = _build_local_ontology(str(text or ""))
        build_result = with_adapter_metadata(
            {
                "status": "success",
                "ontology": ontology,
                "metadata": {
                    "text_length": len(text or ""),
                    "source": "local_regex_fallback",
                    "fallback_reason": "graphrag_backend_unavailable",
                },
            },
            operation="build_ontology",
            backend_available=GRAPHRAG_AVAILABLE,
            degraded_reason=GRAPHRAG_ERROR if not GRAPHRAG_AVAILABLE else None,
            implementation_status="implemented",
        )

    validation_result = validate_ontology(ontology)
    validation_payload = (
        validation_result.get("result")
        if isinstance(validation_result, dict) and isinstance(validation_result.get("result"), dict)
        else {}
    )
    if not validation_payload:
        validation_payload = _validate_ontology_locally(ontology)
        validation_result = with_adapter_metadata(
            {
                "status": "success",
                "result": validation_payload,
                "valid": validation_payload["valid"],
                "metadata": {"source": "local_validation_fallback"},
            },
            operation="validate_ontology",
            backend_available=GRAPHRAG_AVAILABLE,
            degraded_reason=GRAPHRAG_ERROR if not GRAPHRAG_AVAILABLE else None,
            implementation_status="implemented",
        )
    valid = bool(
        validation_result.get("valid")
        if isinstance(validation_result, dict) and validation_result.get("valid") is not None
        else validation_payload.get("valid")
    )

    refinement_result = run_refinement_cycle(
        ontology,
        rounds=refinement_rounds,
    ) if valid else with_adapter_metadata(
        {
            "status": "skipped",
            "result": ontology,
            "reason": "ontology_validation_failed",
        },
        operation="run_refinement_cycle",
        backend_available=GRAPHRAG_AVAILABLE,
        degraded_reason=GRAPHRAG_ERROR if not GRAPHRAG_AVAILABLE else None,
        implementation_status="skipped",
        extra_metadata={"rounds": refinement_rounds},
    )
    refined_ontology = (
        refinement_result.get("result")
        if isinstance(refinement_result, dict) and refinement_result.get("result") is not None
        else ontology
    )
    if valid and refined_ontology is ontology and (
        not isinstance(refinement_result, dict)
        or refinement_result.get("status") == "unavailable"
        or refinement_result.get("result") is None
    ):
        refined_ontology = _refine_ontology_locally(ontology, rounds=refinement_rounds)
        refinement_result = with_adapter_metadata(
            {
                "status": "success",
                "result": refined_ontology,
                "metadata": {"source": "local_refinement_fallback"},
            },
            operation="run_refinement_cycle",
            backend_available=GRAPHRAG_AVAILABLE,
            degraded_reason=GRAPHRAG_ERROR if not GRAPHRAG_AVAILABLE else None,
            implementation_status="implemented",
            extra_metadata={"rounds": refinement_rounds},
        )

    quality_result = score_ontology_support_paths(
        refined_ontology,
        claim_type=claim_type,
    )
    gap_result = identify_ontology_gaps(
        refined_ontology,
        claim_type=claim_type,
    )
    ontology_gaps = (
        gap_result.get("gaps", [])
        if isinstance(gap_result, dict) and isinstance(gap_result.get("gaps"), list)
        else []
    )
    gap_type_counts: Dict[str, int] = {}
    gap_severity_counts: Dict[str, int] = {}
    gap_follow_up_action_counts: Dict[str, int] = {}
    for gap in ontology_gaps:
        if not isinstance(gap, dict):
            continue
        gap_type = str(gap.get("gap_type") or gap.get("type") or "unknown").strip()
        severity = str(gap.get("severity") or "unknown").strip()
        follow_up_action = str(gap.get("follow_up_action") or "").strip()
        if gap_type:
            gap_type_counts[gap_type] = gap_type_counts.get(gap_type, 0) + 1
        if severity:
            gap_severity_counts[severity] = gap_severity_counts.get(severity, 0) + 1
        if follow_up_action:
            gap_follow_up_action_counts[follow_up_action] = gap_follow_up_action_counts.get(follow_up_action, 0) + 1
    workflow_degraded_reason = GRAPHRAG_ERROR if not GRAPHRAG_AVAILABLE else ""

    ontology_quality = {
        "valid": valid,
        "validation_status": validation_result.get("status") if isinstance(validation_result, dict) else "",
        "validation_issues": validation_payload.get("issues", []),
        "overall_quality_score": float(quality_result.get("overall_quality_score", 0.0) or 0.0),
        "grade": quality_result.get("grade", "F"),
        "entity_coverage_score": quality_result.get("entity_coverage_score", 0.0),
        "concept_completeness_score": quality_result.get("concept_completeness_score", 0.0),
        "relation_score": quality_result.get("relation_score", 0.0),
        "relation_density_score": quality_result.get("relation_density_score", 0.0),
        "gap_count": int(gap_result.get("gap_count", 0) or 0),
        "has_gaps": bool(gap_result.get("has_gaps", False)),
        "has_blocking_gaps": bool(gap_result.get("has_blocking_gaps", False)),
        "gap_type_counts": dict(sorted(gap_type_counts.items())),
        "gap_severity_counts": dict(sorted(gap_severity_counts.items())),
        "gap_follow_up_action_counts": dict(sorted(gap_follow_up_action_counts.items())),
        "entity_count": int(quality_result.get("entity_count", 0) or 0),
        "relation_count": int(quality_result.get("relation_count", 0) or 0),
        "concept_count": int(quality_result.get("concept_count", 0) or 0),
        "workflow_operation": operation,
        "workflow_status": "success" if ontology is not None and valid else "degraded",
        "workflow_backend_available": bool(GRAPHRAG_AVAILABLE),
        "workflow_implementation_status": "implemented",
        "workflow_degraded_reason": workflow_degraded_reason,
        "refinement_rounds": refinement_rounds,
    }
    status = "success" if ontology is not None and valid else "degraded"

    return with_adapter_metadata(
        {
            "status": status,
            "claim_type": claim_type or "",
            "ontology": refined_ontology,
            "build": build_result,
            "validation": validation_result,
            "refinement": refinement_result,
            "quality": quality_result,
            "gaps": gap_result,
            "ontology_quality": ontology_quality,
            "metadata": {
                "text_length": len(text or ""),
                "refinement_rounds": refinement_rounds,
            },
        },
        operation=operation,
        backend_available=GRAPHRAG_AVAILABLE,
        degraded_reason=GRAPHRAG_ERROR if not GRAPHRAG_AVAILABLE else None,
        implementation_status="implemented",
        extra_metadata={"claim_type": claim_type, "refinement_rounds": refinement_rounds},
    )


__all__ = [
    "OntologyGenerator",
    "LogicValidator",
    "OntologyMediator",
    "OntologyPipeline",
    "GRAPHRAG_AVAILABLE",
    "GRAPHRAG_ERROR",
    "build_ontology",
    "validate_ontology",
    "run_refinement_cycle",
    "ingest_pdf_to_graphrag",
    "extract_pdf_entities",
    "analyze_pdf_relationships",
    "cross_analyze_pdf_documents",
    "batch_process_pdfs",
    "query_pdf_knowledge_graph",
    "score_ontology_support_paths",
    "identify_ontology_gaps",
    "score_support_path_quality",
    "build_validate_score_ontology",
    "_CLAIM_ONTOLOGY_PROFILES",
]
