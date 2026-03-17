import os
from dataclasses import dataclass
from typing import Any, Dict


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class IntegrationFeatureFlags:
    enhanced_legal: bool = False
    enhanced_search: bool = False
    enhanced_graph: bool = False
    enhanced_vector: bool = False
    enhanced_optimizer: bool = False
    reranker_mode: str = "off"
    reranker_canary_percent: int = 100
    reranker_metrics_window: int = 0
    retrieval_max_latency_ms: int = 1500

    @classmethod
    def from_env(cls) -> "IntegrationFeatureFlags":
        return cls(
            enhanced_legal=_parse_bool(os.getenv("IPFS_DATASETS_ENHANCED_LEGAL"), False),
            enhanced_search=_parse_bool(os.getenv("IPFS_DATASETS_ENHANCED_SEARCH"), False),
            enhanced_graph=_parse_bool(os.getenv("IPFS_DATASETS_ENHANCED_GRAPH"), False),
            enhanced_vector=_parse_bool(os.getenv("IPFS_DATASETS_ENHANCED_VECTOR"), False),
            enhanced_optimizer=_parse_bool(os.getenv("IPFS_DATASETS_ENHANCED_OPTIMIZER"), False),
            reranker_mode=os.getenv("RETRIEVAL_RERANKER_MODE", "off").strip().lower(),
            reranker_canary_percent=int(os.getenv("RETRIEVAL_RERANKER_CANARY_PERCENT", "100")),
            reranker_metrics_window=int(os.getenv("RETRIEVAL_RERANKER_METRICS_WINDOW", "0")),
            retrieval_max_latency_ms=int(os.getenv("RETRIEVAL_MAX_LATENCY_MS", "1500")),
        )

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "IntegrationFeatureFlags":
        mediator_cfg = config.get("MEDIATOR", {}) if isinstance(config, dict) else {}
        integrations = mediator_cfg.get("integrations", {}) if isinstance(mediator_cfg, dict) else {}
        return cls(
            enhanced_legal=_parse_bool(integrations.get("enhanced_legal"), False),
            enhanced_search=_parse_bool(integrations.get("enhanced_search"), False),
            enhanced_graph=_parse_bool(integrations.get("enhanced_graph"), False),
            enhanced_vector=_parse_bool(integrations.get("enhanced_vector"), False),
            enhanced_optimizer=_parse_bool(integrations.get("enhanced_optimizer"), False),
            reranker_mode=str(integrations.get("reranker_mode", "off")).strip().lower(),
            reranker_canary_percent=int(integrations.get("reranker_canary_percent", 100)),
            reranker_metrics_window=int(integrations.get("reranker_metrics_window", 0)),
            retrieval_max_latency_ms=int(integrations.get("retrieval_max_latency_ms", 1500)),
        )
