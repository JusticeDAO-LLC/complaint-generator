from __future__ import annotations

from typing import Any, Dict, Optional

from .loader import import_attr_optional


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
        return {
            "status": "unavailable",
            "ontology": None,
            "metadata": {"backend_available": False, "text_length": len(text)},
        }
    if hasattr(generator, "generate"):
        try:
            result = generator.generate(text, config=config) if config is not None else generator.generate(text)
            return {
                "status": "success",
                "ontology": result,
                "metadata": {"backend_available": True, "text_length": len(text)},
            }
        except Exception as exc:
            return {
                "status": "error",
                "ontology": None,
                "metadata": {"backend_available": True, "error": str(exc)},
            }
    return {
        "status": "not_implemented",
        "ontology": None,
        "metadata": {"backend_available": True},
    }


def validate_ontology(ontology: Any) -> Dict[str, Any]:
    if LogicValidator is None:
        return {"status": "unavailable", "result": None}
    try:
        validator = LogicValidator()
    except Exception as exc:
        return {"status": "error", "result": None, "error": str(exc)}

    for method_name in ("validate_ontology", "validate"):
        method = getattr(validator, method_name, None)
        if callable(method):
            try:
                return {"status": "success", "result": method(ontology)}
            except Exception as exc:
                return {"status": "error", "result": None, "error": str(exc)}
    return {"status": "not_implemented", "result": None}


def run_refinement_cycle(ontology: Any, *, rounds: int = 1) -> Dict[str, Any]:
    if OntologyMediator is None:
        return {"status": "unavailable", "result": None}
    try:
        mediator = OntologyMediator()
    except Exception as exc:
        return {"status": "error", "result": None, "error": str(exc)}

    for method_name in ("run_agentic_refinement_cycle", "refine_ontology"):
        method = getattr(mediator, method_name, None)
        if callable(method):
            try:
                if method_name == "run_agentic_refinement_cycle":
                    return {"status": "success", "result": method(ontology, rounds=rounds)}
                return {"status": "success", "result": method(ontology)}
            except Exception as exc:
                return {"status": "error", "result": None, "error": str(exc)}
    return {"status": "not_implemented", "result": None}


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