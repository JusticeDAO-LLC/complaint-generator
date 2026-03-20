from __future__ import annotations

from typing import Any, Dict, Optional

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


def create_ontology_generator() -> Any:
    if OntologyGenerator is None:
        return None
    try:
        return OntologyGenerator()
    except Exception:
        return None


def build_ontology(text: str, config: Any | None = None) -> Dict[str, Any]:
    generator = create_ontology_generator()
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
            "status": "not_implemented",
            "ontology": None,
        },
        operation="build_ontology",
        backend_available=True,
        implementation_status="not_implemented",
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
    return with_adapter_metadata(
        {"status": "not_implemented", "result": None},
        operation="validate_ontology",
        backend_available=True,
        implementation_status="not_implemented",
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
    return with_adapter_metadata(
        {"status": "not_implemented", "result": None},
        operation="run_refinement_cycle",
        backend_available=True,
        implementation_status="not_implemented",
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
]
