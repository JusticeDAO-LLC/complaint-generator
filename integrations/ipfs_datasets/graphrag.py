from __future__ import annotations

from typing import Any, Dict, Optional

from .loader import import_attr_optional
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

GRAPHRAG_AVAILABLE = any(
    value is not None
    for value in (OntologyGenerator, LogicValidator, OntologyMediator, OntologyPipeline)
)
GRAPHRAG_ERROR = _generator_error or _validator_error or _mediator_error or _pipeline_error


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
]