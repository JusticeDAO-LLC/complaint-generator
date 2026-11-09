from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import warnings
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, TypedDict, runtime_checkable

from .loader import import_module_optional
from .types import (
    GraphEntity,
    GraphPayload,
    GraphRelationship,
    GraphSnapshotResult,
    GraphSupportMatch,
    GraphSupportResult,
    GraphSupportSummary,
    locate_unique_byte_span,
    with_adapter_metadata,
)


_knowledge_graphs_module, _knowledge_graphs_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs"
)
# The private extractor is resolved only inside the owned deadline worker.
# Importing the optional extraction package here would run its cold imports
# before that boundary and cannot establish extraction capability.
_graph_extraction_module, _graph_extraction_error = None, "private_extractor_not_probed_in_parent"
_graph_query_module, _graph_query_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.query"
)
_graph_storage_module, _graph_storage_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.storage"
)
_graph_lineage_module, _graph_lineage_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.lineage"
)

KNOWLEDGE_GRAPHS_AVAILABLE = any(
    value is not None
    for value in (
        _knowledge_graphs_module,
        _graph_extraction_module,
        _graph_query_module,
        _graph_storage_module,
    )
)
GRAPHS_ERROR = (
    _knowledge_graphs_error
    or _graph_extraction_error
    or _graph_query_error
    or _graph_storage_error
    or _graph_lineage_error
)

_GRAPH_SNAPSHOT_REGISTRY: Dict[str, Dict[str, Any]] = {}
_GRAPH_CLIENT: Any = None
_GRAPH_CLIENT_VERSIONS: Dict[str, str] = {}


def _graph_query_contract(graph_id: Optional[str]) -> Dict[str, Any]:
    contract = _graph_client_contract()
    if _knowledge_graphs_module is not None:
        contract["client_api_version"] = contract.get("client_api_version") or str(
            getattr(_knowledge_graphs_module, "CLIENT_API_VERSION", "") or ""
        )
        contract["contract_version"] = contract.get("contract_version") or str(
            getattr(_knowledge_graphs_module, "CONTRACT_VERSION", "") or ""
        )
    contract["graph_persist_path"] = "knowledge_graphs.Client"
    contract["queried_graph_id"] = str(graph_id or "")
    try:
        _graph_client()
        contract.update(_graph_client_contract())
    except Exception as exc:
        contract["client_error"] = str(exc)
    return contract


def _graph_client_contract() -> Dict[str, Any]:
    versions = dict(_GRAPH_CLIENT_VERSIONS)
    return {
        "graph_persist_path": "knowledge_graphs.Client",
        "client_api_version": versions.get("client_api_version") or "",
        "contract_version": versions.get("contract_version") or "",
    }


def _graph_client() -> Any:
    global _GRAPH_CLIENT, _GRAPH_CLIENT_VERSIONS
    if _GRAPH_CLIENT is not None:
        return _GRAPH_CLIENT
    from .loader import import_module_optional

    module, error = import_module_optional("ipfs_datasets_py.knowledge_graphs")
    if module is None:
        raise ImportError(str(error or "knowledge_graphs unavailable"))
    client_cls = getattr(module, "Client", None)
    graph_target = getattr(module, "GraphTarget", None)
    if client_cls is None or graph_target is None:
        raise ImportError("knowledge_graphs.Client is unavailable")
    catalog_root = os.environ.get("COMPLAINT_GENERATOR_GRAPH_CATALOG", "").strip()
    catalog = Path(catalog_root) if catalog_root else Path(tempfile.mkdtemp(prefix="complaint-kg-"))
    catalog.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        client = client_cls.open(catalog / "catalog", storage_path=catalog / "store", raise_on_error=False)
    for item in caught:
        message = str(item.message)
        if "GraphEngine" in message or "GraphDatabase" in message:
            warnings.warn(message, DeprecationWarning, stacklevel=2)
    _GRAPH_CLIENT = client
    _GRAPH_CLIENT_VERSIONS = {
        "client_api_version": str(getattr(module, "CLIENT_API_VERSION", "") or ""),
        "contract_version": str(getattr(module, "CONTRACT_VERSION", "") or ""),
    }
    return client


def _client_graph_id(graph_id: str) -> str:
    """Map an adapter id onto the slug GraphTarget accepts."""
    identifier = str(graph_id or "complaint")
    if re.fullmatch(r"[a-z0-9]([a-z0-9_-]{0,62}[a-z0-9])?", identifier):
        return identifier
    return "graph-" + hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:48]


def _graph_target_for(graph_id: str) -> Any:
    from .loader import import_attr_optional

    graph_target, error = import_attr_optional("ipfs_datasets_py.knowledge_graphs", "GraphTarget")
    if graph_target is None:
        raise ImportError(str(error or "GraphTarget unavailable"))
    return graph_target(tenant="complaint-generator", graph_id=_client_graph_id(graph_id), branch="main")


def _write_already_committed(client: Any, write_key: str) -> bool:
    """True when this write key already committed a branch head.

    ``Client.write`` mints a fresh revision nonce on every call, so a second
    CAS for the same idempotency key conflicts. The catalog record is the
    durable proof that the first commit landed.
    """
    service = getattr(client, "_service", None)
    catalog = getattr(service, "catalog", None) if service is not None else None
    getter = getattr(catalog, "get_idempotency", None)
    if getter is None:
        return False
    try:
        return getter(write_key) is not None
    except Exception:
        return False


def _entity_key(entity: Mapping[str, Any]) -> str:
    return str(entity.get("id") or entity.get("entity_id") or "")


def _is_cross_graph_link(relationship: Mapping[str, Any]) -> bool:
    if relationship.get("cross_graph") is True:
        return True
    kind = str(relationship.get("link_type") or relationship.get("type") or relationship.get("relation") or "")
    if kind in {SUPPORT_LINK_KIND, CONTRADICTION_LINK_KIND, "cross_graph_link", "supports", "contradicts"}:
        return True
    return "rule_id" in relationship and (
        "factual_assertion_id" in relationship or "source_entity_id" in relationship
    )


def resume_graph_revisions(graph_id: str) -> Dict[str, Any]:
    """Reopen the durable client and rebuild revision, provenance, and links.

    Head scans keep the latest entity rows. Older revisions stay in payload
    storage, so a fresh client can still see superseded facts and cross-graph
    links. Plaintext publication is not part of this read.
    """
    client = _graph_client()
    target = _graph_target_for(graph_id)
    service = getattr(client, "_service", None)
    catalog = getattr(service, "catalog", None) if service is not None else None
    storage = getattr(service, "storage", None) if service is not None else None
    if catalog is None or storage is None:
        raise RuntimeError("knowledge_graphs.Client catalog is unavailable")
    records = catalog.list_revisions(target.tenant, target.graph_id)
    revisions: List[Dict[str, Any]] = []
    for record in records or []:
        revision_id = str(getattr(record, "revision_id", "") or "")
        if not revision_id:
            continue
        snapshot = storage.get_snapshot(target.tenant, target.graph_id, revision_id)
        if snapshot is None:
            continue
        entities = [dict(item) for item in (getattr(snapshot, "entities", None) or []) if isinstance(item, Mapping)]
        relationships = [
            dict(item) for item in (getattr(snapshot, "relationships", None) or []) if isinstance(item, Mapping)
        ]
        metadata = dict(getattr(snapshot, "metadata", None) or {})
        if metadata.get("bootstrap") and not entities and not relationships:
            continue
        revisions.append({
            "revision_id": revision_id,
            "parent_revision": getattr(record, "parent_revision", None),
            "entities": entities,
            "relationships": relationships,
            "provenance": [
                dict(item.get("provenance"))
                for item in [*entities, *relationships]
                if isinstance(item.get("provenance"), Mapping) and item.get("provenance")
            ],
            "cross_graph_links": [item for item in relationships if _is_cross_graph_link(item)],
        })
    head_entities = { _entity_key(item): item for item in (revisions[-1]["entities"] if revisions else []) if _entity_key(item) }
    superseded: List[Dict[str, Any]] = []
    seen_facts = set()
    for revision in revisions[:-1]:
        for entity in revision["entities"]:
            key = _entity_key(entity)
            current = head_entities.get(key)
            if current == entity:
                continue
            fingerprint = json.dumps(entity, sort_keys=True, default=str)
            if fingerprint in seen_facts:
                continue
            seen_facts.add(fingerprint)
            superseded.append(dict(entity))
    provenance: List[Dict[str, Any]] = []
    seen_provenance = set()
    links: List[Dict[str, Any]] = []
    seen_links = set()
    for revision in revisions:
        for item in revision["provenance"]:
            fingerprint = json.dumps(item, sort_keys=True, default=str)
            if fingerprint in seen_provenance:
                continue
            seen_provenance.add(fingerprint)
            provenance.append(item)
        for link in revision["cross_graph_links"]:
            fingerprint = json.dumps(link, sort_keys=True, default=str)
            if fingerprint in seen_links:
                continue
            seen_links.add(fingerprint)
            links.append(link)
    return {
        "graph_id": str(graph_id or ""),
        "client_graph_id": target.graph_id,
        "graph_persist_path": "knowledge_graphs.Client",
        "revision_count": len(revisions),
        "revisions": revisions,
        "provenance": provenance,
        "superseded_facts": superseded,
        "cross_graph_links": links,
        "plaintext_publication": False,
    }


def _persist_nodes_through_client(graph_id: str, graph_payload: Dict[str, Any]) -> Dict[str, Any]:
    contract = _graph_client_contract()
    try:
        client = _graph_client()
        identifier = str(graph_id or "complaint")
        target = _graph_target_for(identifier)
        mutations = {
            "entities": list(graph_payload.get("entities") or []),
            "relationships": list(graph_payload.get("relationships") or []),
        }
        if not mutations["entities"] and not mutations["relationships"]:
            mutations = {**mutations, "force_empty": True}
        write_identity = json.dumps([identifier, mutations], sort_keys=True, default=str)
        write_key = "write-" + hashlib.sha256(write_identity.encode("utf-8")).hexdigest()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            client.create(target, idempotency_key=f"create-{target.graph_id}", raise_on_error=False)
            if _write_already_committed(client, write_key):
                written = type("IdempotentWrite", (), {"ok": True, "status": "success", "result": {"idempotent_retry": True}})()
            else:
                written = client.write(
                    target,
                    idempotency_key=write_key,
                    params=mutations,
                    raise_on_error=False,
                )
        for item in caught:
            message = str(item.message)
            if "GraphEngine" in message or "GraphDatabase" in message:
                warnings.warn(message, DeprecationWarning, stacklevel=2)
        contract.update(_graph_client_contract())
        write_ok = bool(getattr(written, "ok", False) or getattr(written, "status", "") == "success")
        if not write_ok and _write_already_committed(client, write_key):
            write_ok = True
        contract["client_write_ok"] = write_ok
        result_payload = getattr(written, "result", None)
        if isinstance(result_payload, Mapping):
            contract["client_revision"] = str(result_payload.get("revision") or "")
            contract["idempotent_retry"] = bool(result_payload.get("idempotent_retry"))
        elif write_ok and _write_already_committed(client, write_key):
            contract["idempotent_retry"] = True
        contract["plaintext_publication"] = False
    except Exception as exc:
        contract["client_write_ok"] = False
        contract["client_error"] = str(exc)
        contract["plaintext_publication"] = False
    return contract


class GraphProvenance(TypedDict, total=False):
    """Source and transformation lineage carried by graph snapshots and queries.

    All fields are optional so older graph payloads remain valid.  Backends must
    preserve fields they do not understand instead of dropping them.
    """

    source_id: str
    source_type: str
    source_record_id: str | int
    source_ref: str
    source_url: str
    source_system: str
    content_hash: str
    acquired_at: str
    parser_version: str
    extraction_version: str
    transform_lineage: Dict[str, Any]
    metadata: Dict[str, Any]


class GraphPersistenceRequest(TypedDict):
    """Canonical write contract passed to a graph persistence backend."""

    graph_id: str
    graph_version: str
    snapshot_id: str
    content_hash: str
    entities: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    provenance: GraphProvenance
    metadata: Dict[str, Any]


class GraphSupportQuery(TypedDict):
    """Canonical claim-support lookup contract passed to a graph query backend."""

    graph_id: str
    graph_version: str
    claim_element_id: str
    claim_type: str
    claim_element_text: str
    max_results: int
    filters: Dict[str, Any]
    provenance: GraphProvenance


@runtime_checkable
class GraphPersistence(Protocol):
    """Port implemented by durable graph stores.

    ``persist_snapshot`` must be idempotent for a request's ``snapshot_id``.
    ``get_snapshot`` returns that same canonical request shape, or ``None`` when
    the requested graph/version is unknown.
    """

    def persist_snapshot(self, request: GraphPersistenceRequest) -> Mapping[str, Any]:
        """Persist one immutable graph version and return write semantics."""
        ...

    def get_snapshot(
        self,
        graph_id: str,
        *,
        graph_version: Optional[str] = None,
    ) -> Optional[Mapping[str, Any]]:
        """Load the latest or requested immutable graph snapshot."""
        ...


@runtime_checkable
class GraphQuery(Protocol):
    """Port implemented by graph engines capable of support retrieval."""

    def query_support(self, query: GraphSupportQuery) -> Mapping[str, Any]:
        """Return support matches for a canonical claim-element query."""
        ...


@runtime_checkable
class GraphRepository(GraphPersistence, GraphQuery, Protocol):
    """Combined persistence and query plane used by full graph backends."""


def _canonical_graph_content(graph_payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the immutable graph content used for version identifiers."""
    entities = [
        dict(item)
        for item in graph_payload.get("entities", []) or []
        if isinstance(item, Mapping)
    ]
    relationships = [
        dict(item)
        for item in graph_payload.get("relationships", []) or []
        if isinstance(item, Mapping)
    ]
    entities.sort(key=lambda item: str(item.get("id") or item.get("entity_id") or ""))
    relationships.sort(
        key=lambda item: str(item.get("id") or item.get("relationship_id") or "")
    )
    content = {
        "entities": entities,
        "relationships": relationships,
    }
    # A declared domain changes the meaning of otherwise identical nodes. Keep
    # legacy unlabelled hashes, but bind explicit (including nested) domains.
    labels = _label_set(graph_payload)
    identity_labels = sorted(labels & (_LEGAL_NORM_LABELS | _USER_TESTIMONY_LABELS))
    if identity_labels:
        content["namespace_identity"] = identity_labels
    return content


def _graph_content_hash(graph_payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonical_graph_content(graph_payload),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_graph_provenance(
    graph_payload: Mapping[str, Any],
    explicit: Optional[Mapping[str, Any]] = None,
) -> GraphProvenance:
    metadata = graph_payload.get("metadata")
    graph_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    embedded = graph_metadata.get("provenance")
    provenance: Dict[str, Any] = dict(embedded) if isinstance(embedded, Mapping) else {}

    source_id = str(graph_payload.get("source_id") or provenance.get("source_id") or "")
    if source_id:
        provenance["source_id"] = source_id
    lineage = graph_metadata.get("transform_lineage") or graph_metadata.get("lineage")
    if isinstance(lineage, Mapping) and "transform_lineage" not in provenance:
        provenance["transform_lineage"] = dict(lineage)
    if explicit:
        for key, value in explicit.items():
            if value not in (None, "", [], (), {}):
                provenance[str(key)] = value
    return GraphProvenance(**provenance)


def build_graph_persistence_request(
    graph_payload: Mapping[str, Any],
    *,
    graph_id: Optional[str] = None,
    graph_version: Optional[str] = None,
    provenance: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> GraphPersistenceRequest:
    """Normalize a graph payload into the backend-independent write contract."""
    payload_metadata = graph_payload.get("metadata")
    normalized_metadata = dict(payload_metadata) if isinstance(payload_metadata, Mapping) else {}
    if metadata:
        normalized_metadata.update(metadata)

    content_hash = _graph_content_hash(graph_payload)
    source_id = str(graph_payload.get("source_id") or "")
    stable_graph_id = str(
        graph_id
        or normalized_metadata.get("graph_id")
        or _stable_identifier("graph", source_id or content_hash)
    )
    stable_graph_version = str(
        graph_version
        or normalized_metadata.get("graph_version")
        or f"sha256:{content_hash[:16]}"
    )
    snapshot_id = _stable_identifier("graph-snapshot", stable_graph_id, stable_graph_version, content_hash)
    return GraphPersistenceRequest(
        graph_id=stable_graph_id,
        graph_version=stable_graph_version,
        snapshot_id=snapshot_id,
        content_hash=content_hash,
        entities=[dict(item) for item in graph_payload.get("entities", []) or [] if isinstance(item, Mapping)],
        relationships=[
            dict(item)
            for item in graph_payload.get("relationships", []) or []
            if isinstance(item, Mapping)
        ],
        provenance=_normalize_graph_provenance(graph_payload, provenance),
        metadata=normalized_metadata,
    )


def build_graph_support_query(
    claim_element_id: str,
    *,
    graph_id: Optional[str] = None,
    graph_version: Optional[str] = None,
    claim_type: Optional[str] = None,
    claim_element_text: Optional[str] = None,
    max_results: int = 10,
    filters: Optional[Mapping[str, Any]] = None,
    provenance: Optional[Mapping[str, Any]] = None,
) -> GraphSupportQuery:
    """Normalize user input into the backend-independent query contract."""
    if max_results < 0:
        raise ValueError("max_results must be greater than or equal to zero")
    return GraphSupportQuery(
        graph_id=str(graph_id or ""),
        graph_version=str(graph_version or ""),
        claim_element_id=str(claim_element_id or ""),
        claim_type=str(claim_type or ""),
        claim_element_text=str(claim_element_text or ""),
        max_results=int(max_results),
        filters=dict(filters or {}),
        provenance=GraphProvenance(**dict(provenance or {})),
    )


def _stable_identifier(prefix: str, *parts: str) -> str:
    normalized = "|".join(part.strip() for part in parts if part and part.strip())
    if not normalized:
        return ""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


FACTUAL_ASSERTION_KIND = "factual_assertion"
AUTHORITY_SOURCE_KIND = "authority_source"
RULE_CANDIDATE_KIND = "rule_candidate"
LEGAL_REQUIREMENT_KIND = "legal_requirement"
SUPPORT_LINK_KIND = "support_link"
CONTRADICTION_LINK_KIND = "contradiction_link"

DISTINCT_GRAPH_RECORD_KINDS = (
    FACTUAL_ASSERTION_KIND,
    AUTHORITY_SOURCE_KIND,
    RULE_CANDIDATE_KIND,
    LEGAL_REQUIREMENT_KIND,
    SUPPORT_LINK_KIND,
    CONTRADICTION_LINK_KIND,
)

_LEGAL_NORM_LABELS = frozenset({
    "law",
    "legal",
    "legal_norm",
    "legal_text",
    "legal_passage",
    "authority",
    "authority_source",
    "rule",
    "rule_candidate",
    "legal_requirement",
    "requirement",
    "procedural_requirement",
    "statute",
    "regulation",
    "case_law",
    "case",
})
_USER_TESTIMONY_LABELS = frozenset({
    "testimony",
    "user",
    "user_testimony",
    "user_statement",
    "user_document",
    "user_uploaded_document",
    "complainant",
    "interview",
    "factual_assertion",
    "user_assertion",
})
_RULE_ID_KINDS = frozenset({RULE_CANDIDATE_KIND, LEGAL_REQUIREMENT_KIND})


def record_kind_from_id(record_id: str) -> str:
    """Return the namespace prefix of a graph id, or an empty string."""
    text = str(record_id or "").strip()
    prefix, separator, _rest = text.partition(":")
    if separator and _rest.strip() and prefix in DISTINCT_GRAPH_RECORD_KINDS:
        return prefix
    return ""


def mint_graph_record_id(kind: str, *parts: str) -> str:
    """Mint an id whose prefix is exactly one graph namespace."""
    normalized_kind = str(kind or "").strip()
    if normalized_kind not in DISTINCT_GRAPH_RECORD_KINDS:
        raise ValueError(f"unknown graph record kind: {normalized_kind}")
    values = [str(part) for part in parts]
    if not any(value.strip() for value in values):
        raise ValueError("graph record id requires at least one non-empty part")
    encoded = json.dumps([normalized_kind, values], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"{normalized_kind}:{hashlib.sha256(encoded).hexdigest()}"


def _label_set(record: Mapping[str, Any], _seen=None, _depth=0) -> set:
    """Inspect only known provenance containers, with bounded cyclic traversal."""
    labels: set = set()
    if not isinstance(record, Mapping) or _depth > 8:
        return labels
    seen = set() if _seen is None else _seen
    if id(record) in seen:
        return labels
    seen.add(id(record))
    for key in (
        "resolution_namespace",
        "namespace",
        "record_kind",
        "record_type",
        "element_type",
        "entity_type",
        "node_type",
        "source_kind",
        "source_type",
        "passage_role",
        "content_origin",
        "type",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            labels.add(value.strip().lower())
    if record.get("legal_passage") is True:
        labels.add("legal_passage")
    for key in ("id", "entity_id", "fact_id", "rule_id"):
        kind = record_kind_from_id(record.get(key))
        if kind:
            labels.add(kind)
    for key in ("attributes", "provenance", "user_assertion", "metadata", "source_passage", "extractor"):
        nested = record.get(key)
        if isinstance(nested, Mapping):
            labels.update(_label_set(nested, seen, _depth + 1))
    return labels


def source_is_legal_norm(record: Optional[Mapping[str, Any]]) -> bool:
    """True when a record is a legal norm rather than complainant testimony."""
    if not isinstance(record, Mapping):
        return False
    if record.get("legal_passage") is True:
        return True
    return bool(_label_set(record) & _LEGAL_NORM_LABELS)


def legal_namespace_kind(record: Optional[Mapping[str, Any]]) -> str:
    """Pick the legal namespace for a passage. Never returns a factual kind."""
    record = record if isinstance(record, Mapping) else {}
    # A requirement's inherited rule provenance does not make the requirement
    # itself a rule. Explicit current-record taxonomy precedes ancestry labels.
    aliases = {"rule": RULE_CANDIDATE_KIND, "requirement": LEGAL_REQUIREMENT_KIND,
               "procedural_requirement": LEGAL_REQUIREMENT_KIND}
    for scope in (record, record.get("attributes"), record.get("metadata")):
        if not isinstance(scope, Mapping):
            continue
        for key in ("record_kind", "namespace", "passage_role", "element_type", "record_type", "type"):
            label = str(scope.get(key) or "").strip().lower()
            kind = aliases.get(label, label)
            if kind in {AUTHORITY_SOURCE_KIND, RULE_CANDIDATE_KIND, LEGAL_REQUIREMENT_KIND}:
                return kind
    labels = _label_set(record or {})
    if labels & {RULE_CANDIDATE_KIND, "rule"}:
        return RULE_CANDIDATE_KIND
    if labels & {LEGAL_REQUIREMENT_KIND, "requirement", "procedural_requirement"}:
        return LEGAL_REQUIREMENT_KIND
    return AUTHORITY_SOURCE_KIND


def _resolution_namespace(entity: Mapping[str, Any]) -> str:
    labels = _label_set(entity)
    if labels & _LEGAL_NORM_LABELS:
        return "legal_norm"
    if labels & (_USER_TESTIMONY_LABELS | {"user_statement", "document", "evidence"}):
        return "user_testimony"
    return "world"


def _resolution_namespaces_compatible(left: str, right: str) -> bool:
    if left == right:
        return True
    return False


def _record_domain(record: Mapping[str, Any]) -> str:
    """Domain separation for resolution/query, independent of a display label."""
    if source_is_legal_norm(record):
        return legal_namespace_kind(record)
    return _resolution_namespace(record)


def build_namespaced_support_link(
    *,
    factual_assertion_id: str,
    rule_id: str,
    relation: str = "supports",
    factual_provenance: Optional[Mapping[str, Any]] = None,
    rule_provenance: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Link a factual assertion to a rule without collapsing their provenance.

    ``rule_id`` must already be a rule-candidate or legal-requirement id.
    The link id uses its own support or contradiction namespace.
    """
    factual_id = str(factual_assertion_id or "").strip()
    normalized_rule_id = str(rule_id or "").strip()
    supplied_prefix = factual_id.partition(":")[0]
    if (not factual_id or record_kind_from_id(factual_id) not in {"", FACTUAL_ASSERTION_KIND}
            or (supplied_prefix in DISTINCT_GRAPH_RECORD_KINDS and record_kind_from_id(factual_id) != FACTUAL_ASSERTION_KIND)):
        raise ValueError("factual endpoint cannot use another record namespace")
    factual_chain = deepcopy(dict(factual_provenance or {}))
    rule_chain = deepcopy(dict(rule_provenance or {}))
    if source_is_legal_norm(factual_chain):
        raise ValueError("legal provenance cannot be a factual endpoint")
    # Local graph IDs remain unchanged. A verified immutable assertion supplies
    # the source-bound external namespace used only by the cross-graph link.
    # source_entity_id is a local alias, not proof of any additional content.
    from .types import user_assertion_from_mapping
    raw_assertion = factual_chain.get("user_assertion")
    asserted = user_assertion_from_mapping(raw_assertion) if isinstance(raw_assertion, Mapping) else None
    source_entity_id = factual_id
    if asserted is not None:
        if not asserted.is_asserted_user_fact:
            raise ValueError("support endpoint contains an unverified user assertion")
        canonical_id = mint_graph_record_id(FACTUAL_ASSERTION_KIND, asserted.stable_id)
        if record_kind_from_id(factual_id) == FACTUAL_ASSERTION_KIND and factual_id != canonical_id:
            raise ValueError("factual endpoint does not match its assertion identity")
        factual_id = canonical_id
    elif record_kind_from_id(factual_id) != FACTUAL_ASSERTION_KIND:
        raise ValueError("local factual endpoint requires a verified user assertion")
    if record_kind_from_id(normalized_rule_id) not in _RULE_ID_KINDS:
        raise ValueError("support links require a rule_candidate or legal_requirement id")
    if _label_set(rule_chain) & _USER_TESTIMONY_LABELS and not source_is_legal_norm(rule_chain):
        raise ValueError("user provenance cannot be the legal rule endpoint")
    normalized_relation = str(relation or "supports").strip().lower()
    if normalized_relation not in {"supports", "support", "support_link", "contradicts", "contradiction", "contradiction_link"}:
        raise ValueError("unsupported cross-graph relation")
    link_kind = (
        CONTRADICTION_LINK_KIND
        if normalized_relation in {"contradicts", "contradiction", "contradiction_link"}
        else SUPPORT_LINK_KIND
    )
    return {
        "link_id": mint_graph_record_id(link_kind, factual_id, normalized_rule_id, link_kind),
        "link_type": link_kind,
        "relation": "contradicts" if link_kind == CONTRADICTION_LINK_KIND else "supports",
        "factual_assertion_id": factual_id,
        "source_entity_id": source_entity_id,
        "assertion_verified": bool(asserted is not None and asserted.is_asserted_user_fact),
        "rule_id": normalized_rule_id,
        "provenance_chains": {
            FACTUAL_ASSERTION_KIND: factual_chain,
            "rule": rule_chain,
        },
    }


USER_ALLEGATION_CLASS = "user_allegation"
CORROBORATING_EVIDENCE_CLASS = "corroborating_evidence"
INFERRED_HYPOTHESIS_CLASS = "inferred_hypothesis"
LEGAL_AUTHORITY_CLASS = "legal_authority"
EPISTEMIC_CLASSES = frozenset({
    USER_ALLEGATION_CLASS,
    CORROBORATING_EVIDENCE_CLASS,
    INFERRED_HYPOTHESIS_CLASS,
    LEGAL_AUTHORITY_CLASS,
})
REQUIREMENT_DEFINITION_FIELDS = (
    "description",
    "authority_locator",
    "source_locator",
    "jurisdiction",
    "effective_date",
    "authority_version",
    "derivation_status",
    "proof_status",
    "asserted_text",
    "citation",
    "authority_text",
    "rule_text",
)
_UNKNOWN_STATEMENTS = frozenset({
    "", "n/a", "na", "none", "unknown", "not sure", "unsure", "no idea",
    "i do not know", "i don't know", "idk",
})
_REFUSED_STATEMENTS = frozenset({
    "i refuse", "i refuse to answer", "refused", "refuse", "i decline",
    "i decline to answer", "declined", "decline", "prefer not to say",
    "skip", "skipped", "ask me later", "later",
})
_HYPOTHESIS_MARKERS = (
    "i think", "i believe", "maybe", "might have", "possibly", "hypothesis", "i guess",
)
_EVIDENCE_MARKERS = (
    "attached", "exhibit", "witness", "the email", "email shows", "document",
    "photograph", "photo shows", "receipt", "corroborat", "recording", "screenshot",
)
_CONTRADICTION_MARKERS = (
    "that is wrong", "i contradict", "the opposite", "not true", "i was wrong",
    "correction:", "that contradicts",
)
_DATE_IN_SENTENCE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}\b"
)
_PERSON_NAME = r"([A-Z][a-z]+(?: [A-Z][a-z]+)+)"
_PERSON_PATTERNS = (
    re.compile(r"(?i:\bmy name is )" + _PERSON_NAME),
    re.compile(r"\bI am " + _PERSON_NAME),
    re.compile(r"(?i:\b(?:manager|supervisor|landlord|owner) )" + _PERSON_NAME),
)
_ALLEGATION_MARKERS = (
    "fired", "discriminat", "denied", "retaliat", "harass", "evict", "allege",
    "not stated", "unresolved",
)


def classify_epistemic_class(text: str, *, explicit: Optional[str] = None, legal: bool = False) -> str:
    """Separate allegation, corroboration, hypothesis, and legal authority.

    A legal flag wins over user wording. Marker checks do not invent a fact.
    """
    supplied = str(explicit or "").strip().lower()
    if supplied in EPISTEMIC_CLASSES:
        return supplied
    if legal:
        return LEGAL_AUTHORITY_CLASS
    normalized = " ".join(str(text or "").split()).lower()
    if any(marker in normalized for marker in _HYPOTHESIS_MARKERS):
        return INFERRED_HYPOTHESIS_CLASS
    if any(marker in normalized for marker in _EVIDENCE_MARKERS):
        return CORROBORATING_EVIDENCE_CLASS
    return USER_ALLEGATION_CLASS


def statement_value_status(text: str) -> str:
    """Keep unknown and contradiction answers visible as values, not deletions."""
    normalized = " ".join(str(text or "").split()).lower()
    if normalized in _REFUSED_STATEMENTS:
        return "refused"
    if normalized in _UNKNOWN_STATEMENTS:
        return "unknown"
    if any(marker in normalized for marker in _CONTRADICTION_MARKERS):
        return "contradiction"
    return "stated"


def exact_statement_provenance(source_text: str, statement: str) -> Dict[str, Any]:
    """Bind a revision to the exact user statement bytes when the span is unique."""
    source = source_text if isinstance(source_text, str) else ""
    located = locate_unique_byte_span(source, statement if isinstance(statement, str) else "")
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest() if source else ""
    if located.deficiency or located.start is None or located.end is None:
        return {
            "statement": statement if isinstance(statement, str) else "",
            "source_text": source,
            "source_hash": source_hash,
            "source_span": None,
            "deficiency": located.deficiency or "missing_source_span",
        }
    return {
        "statement": located.text,
        "source_text": source,
        "source_hash": source_hash,
        "source_span": {"start": located.start, "end": located.end, "text": located.text, "unit": "byte"},
        "deficiency": "",
    }


def narrative_source_records(text: str) -> List[Dict[str, Any]]:
    """People, events, and allegations whose labels are exact narrative spans."""
    source = text if isinstance(text, str) else ""
    records: List[Dict[str, Any]] = []
    seen = set()

    def _add(kind: str, label: str) -> None:
        cleaned = " ".join(str(label or "").split())
        if not cleaned:
            return
        located = locate_unique_byte_span(source, cleaned)
        if located.deficiency or located.start is None:
            return
        key = (kind, located.start, located.end)
        if key in seen:
            return
        seen.add(key)
        records.append({
            "narrative_kind": kind,
            "name": located.text if kind == "person" else located.text,
            "description": located.text,
            "epistemic_class": USER_ALLEGATION_CLASS,
            "source_span": {"start": located.start, "end": located.end, "text": located.text},
        })

    for pattern in _PERSON_PATTERNS:
        for match in pattern.finditer(source):
            _add("person", match.group(1))
    sentences = _split_sentences(source)
    counts: Dict[str, int] = {}
    for sentence in sentences:
        counts[sentence] = counts.get(sentence, 0) + 1
    for sentence in sentences:
        if counts[sentence] != 1:
            continue
        lower = sentence.lower()
        if _DATE_IN_SENTENCE.search(sentence):
            _add("event", sentence)
        if any(marker in lower for marker in _ALLEGATION_MARKERS):
            _add("allegation", sentence)
    return records


def build_epistemic_support_edge(
    *,
    factual_assertion_id: str,
    rule_id: str,
    epistemic_class: str,
    statement: str,
    factual_provenance: Optional[Mapping[str, Any]] = None,
    rule_provenance: Optional[Mapping[str, Any]] = None,
    relation: str = "supports",
) -> Dict[str, Any]:
    """Support or contradict a legal element without treating authority as a user fact."""
    kind = classify_epistemic_class(statement, explicit=epistemic_class)
    if kind == LEGAL_AUTHORITY_CLASS:
        raise ValueError("legal authority cannot be the factual endpoint of a support edge")
    link = build_namespaced_support_link(
        factual_assertion_id=factual_assertion_id,
        rule_id=rule_id,
        relation=relation,
        factual_provenance=factual_provenance,
        rule_provenance=rule_provenance,
    )
    link["epistemic_class"] = kind
    link["statement"] = statement
    link["requirement_definition_unchanged"] = True
    return link


def requirement_definition_snapshot(node: Any) -> Dict[str, Any]:
    """Copy the authority-derived definition fields an answer must not edit."""
    attributes = getattr(node, "attributes", None)
    attributes = dict(attributes) if isinstance(attributes, Mapping) else {}
    return {
        "name": getattr(node, "name", ""),
        "description": getattr(node, "description", ""),
        "fields": {key: deepcopy(attributes[key]) for key in REQUIREMENT_DEFINITION_FIELDS if key in attributes},
    }


def restore_requirement_definition(node: Any, snapshot: Mapping[str, Any]) -> None:
    """Put the requirement definition back after an answer changes only support."""
    node.name = snapshot.get("name", getattr(node, "name", ""))
    node.description = snapshot.get("description", getattr(node, "description", ""))
    attributes = node.attributes if isinstance(getattr(node, "attributes", None), dict) else {}
    node.attributes = attributes
    for key, value in dict(snapshot.get("fields") or {}).items():
        attributes[key] = deepcopy(value)


def _split_sentences(text: str) -> List[str]:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    return [part.strip() for part in parts if part and part.strip()]


def _tokenize(value: str) -> List[str]:
    return [token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if token]


def _normalize_semantic_token(token: str) -> str:
    normalized = (token or "").lower().strip()
    if not normalized:
        return ""

    canonical_map = {
        "complained": "complain",
        "complaint": "complain",
        "complaints": "complain",
        "filing": "file",
        "filed": "file",
        "files": "file",
        "engaged": "engage",
        "engaging": "engage",
    }
    if normalized in canonical_map:
        return canonical_map[normalized]

    for suffix in ("ing", "ed", "es", "s"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 2:
            return normalized[: -len(suffix)]
    return normalized


def _semantic_token_set(value: str) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "about",
        "by",
        "in",
        "of",
        "the",
        "to",
    }
    return {
        normalized
        for normalized in (_normalize_semantic_token(token) for token in _tokenize(value))
        if normalized and normalized not in stopwords
    }


def _count_values(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows or []:
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _summarize_fact_registry_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    unique_source_refs = {
        str(row.get("source_ref") or "").strip()
        for row in rows or []
        if str(row.get("source_ref") or "").strip()
    }
    unique_source_records = {
        str(row.get("source_record_id") or "").strip()
        for row in rows or []
        if str(row.get("source_record_id") or "").strip()
    }
    passage_anchored_count = 0
    for row in rows or []:
        source_passage = row.get("source_passage") if isinstance(row.get("source_passage"), dict) else {}
        if source_passage.get("chunk_id") or row.get("chunk_id"):
            passage_anchored_count += 1
    return {
        "registry_version": "claim_fact_registry_summary.v1",
        "fact_count": len(rows or []),
        "unique_source_ref_count": len(unique_source_refs),
        "unique_source_record_count": len(unique_source_records),
        "passage_anchored_count": passage_anchored_count,
        "source_family_counts": _count_values(rows, "source_family"),
        "source_ref_counts": _count_values(rows, "source_ref"),
        "source_record_id_counts": _count_values(rows, "source_record_id"),
        "record_scope_counts": _count_values(rows, "record_scope"),
        "artifact_family_counts": _count_values(rows, "artifact_family"),
        "corpus_family_counts": _count_values(rows, "corpus_family"),
        "content_origin_counts": _count_values(rows, "content_origin"),
        "parse_source_counts": _count_values(rows, "parse_source"),
        "input_format_counts": _count_values(rows, "input_format"),
        "quality_tier_counts": _count_values(rows, "quality_tier"),
    }


def _extract_fact_registry_summary(
    graph_payload: Dict[str, Any],
    metadata: Dict[str, Any],
    persistence_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if isinstance(persistence_metadata, dict) and isinstance(persistence_metadata.get("fact_registry_summary"), dict):
        return dict(persistence_metadata["fact_registry_summary"])
    if isinstance(graph_payload, dict) and isinstance(graph_payload.get("fact_registry_summary"), dict):
        return dict(graph_payload["fact_registry_summary"])
    if isinstance(metadata, dict) and isinstance(metadata.get("fact_registry_summary"), dict):
        return dict(metadata["fact_registry_summary"])
    support_facts = graph_payload.get("support_facts") if isinstance(graph_payload, dict) else []
    if isinstance(support_facts, list):
        return _summarize_fact_registry_rows([row for row in support_facts if isinstance(row, dict)])
    return _summarize_fact_registry_rows([])


_FACT_REGISTRY_NUMERIC_FIELDS = (
    "fact_count",
    "unique_source_ref_count",
    "unique_source_record_count",
    "passage_anchored_count",
)

_FACT_REGISTRY_COUNT_FIELDS = (
    "source_family_counts",
    "source_ref_counts",
    "source_record_id_counts",
    "record_scope_counts",
    "artifact_family_counts",
    "corpus_family_counts",
    "content_origin_counts",
    "parse_source_counts",
    "input_format_counts",
    "quality_tier_counts",
)


def _merge_count_maps(existing: Dict[str, int], incoming: Dict[str, Any]) -> Dict[str, int]:
    for key, value in incoming.items():
        try:
            increment = int(value)
        except (TypeError, ValueError):
            continue
        existing[str(key)] = existing.get(str(key), 0) + increment
    return existing


def _merge_fact_registry_summaries(summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {
        "registry_version": "claim_fact_registry_summary.v1",
        "aggregation_scope": "graph_snapshot_query",
        "snapshot_count": len(summaries),
    }
    for field in _FACT_REGISTRY_NUMERIC_FIELDS:
        merged[field] = sum(
            int(summary.get(field) or 0)
            for summary in summaries
            if isinstance(summary, dict)
        )
    for field in _FACT_REGISTRY_COUNT_FIELDS:
        counts: Dict[str, int] = {}
        for summary in summaries:
            if isinstance(summary, dict) and isinstance(summary.get(field), dict):
                _merge_count_maps(counts, summary[field])
        merged[field] = counts
    if merged["source_ref_counts"]:
        merged["unique_source_ref_count"] = len(merged["source_ref_counts"])
    if merged["source_record_id_counts"]:
        merged["unique_source_record_count"] = len(merged["source_record_id_counts"])
    return merged


def _score_fact_match(fact: Dict[str, Any], claim_element_id: str, claim_element_text: str) -> float:
    score = float(fact.get("confidence", 0.0) or 0.0)
    fact_tokens = set(_tokenize(str(fact.get("text") or "")))
    target_tokens = set(_tokenize(claim_element_text))

    if claim_element_id and str(fact.get("claim_element_id") or "") == claim_element_id:
        score += 1.0
    if claim_element_text and str(fact.get("claim_element_text") or "") == claim_element_text:
        score += 1.0
    if fact_tokens and target_tokens:
        overlap = len(fact_tokens & target_tokens)
        score += overlap / max(len(target_tokens), 1)
    return round(score, 4)


def _fact_dedup_key(fact: Dict[str, Any]) -> str:
    text = " ".join(str(fact.get("text") or "").lower().split())
    claim_element_id = str(fact.get("claim_element_id") or "")
    claim_element_text = " ".join(str(fact.get("claim_element_text") or "").lower().split())
    return json.dumps([_record_domain(fact), claim_element_id, claim_element_text, text], separators=(",", ":"))


def _fact_matches_filters(fact: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    for key, expected in filters.items():
        actual: Any = fact.get(key)
        if actual is None and isinstance(fact.get("provenance"), Mapping):
            actual = fact["provenance"].get(key)
        if isinstance(expected, (list, tuple, set, frozenset)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _texts_semantically_similar(left: str, right: str) -> bool:
    left_normalized = " ".join((left or "").lower().split())
    right_normalized = " ".join((right or "").lower().split())
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return True

    left_tokens = _semantic_token_set(left_normalized)
    right_tokens = _semantic_token_set(right_normalized)
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    containment = overlap / max(min(len(left_tokens), len(right_tokens)), 1)
    jaccard = overlap / max(union, 1)
    return containment >= 0.6 or jaccard >= 0.45


def _cluster_semantically_similar_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clusters: List[Dict[str, Any]] = []
    for result in results:
        matched_cluster: Optional[Dict[str, Any]] = None
        for cluster in clusters:
            same_element = (
                str(cluster.get("claim_element_id") or "") == str(result.get("claim_element_id") or "")
                and str(cluster.get("claim_element_text") or "") == str(result.get("claim_element_text") or "")
            )
            if not same_element:
                continue
            if _record_domain(cluster) != _record_domain(result):
                continue
            if _texts_semantically_similar(str(cluster.get("text") or ""), str(result.get("text") or "")):
                matched_cluster = cluster
                break

        if matched_cluster is None:
            clusters.append(
                {
                    **result,
                    "cluster_size": int(result.get("duplicate_count", 1) or 1),
                    "cluster_texts": [str(result.get("text") or "")],
                }
            )
            continue

        matched_cluster["duplicate_count"] = int(matched_cluster.get("duplicate_count", 1) or 1) + int(result.get("duplicate_count", 1) or 1)
        matched_cluster["cluster_size"] = int(matched_cluster.get("cluster_size", 1) or 1) + int(result.get("duplicate_count", 1) or 1)
        matched_cluster["score"] = max(float(matched_cluster.get("score", 0.0) or 0.0), float(result.get("score", 0.0) or 0.0))
        matched_cluster["confidence"] = max(float(matched_cluster.get("confidence", 0.0) or 0.0), float(result.get("confidence", 0.0) or 0.0))
        if result.get("matched_claim_element"):
            matched_cluster["matched_claim_element"] = True
        if str(result.get("text") or "") not in matched_cluster["cluster_texts"]:
            matched_cluster["cluster_texts"].append(str(result.get("text") or ""))
        for support_kind in result.get("support_kind_set", []) or []:
            if support_kind not in matched_cluster.get("support_kind_set", []):
                matched_cluster.setdefault("support_kind_set", []).append(support_kind)
        for source_table in result.get("source_table_set", []) or []:
            if source_table not in matched_cluster.get("source_table_set", []):
                matched_cluster.setdefault("source_table_set", []).append(source_table)
    return clusters


_PRIVATE_EXTRACTOR_OPTIONS = {
    "use_spacy": False,
    "use_transformers": False,
    "use_tracer": False,
    "use_srl": False,
}
_PRIVATE_EXTRACTION_TEXT_LIMIT = 20000
_PRIVATE_EXTRACTION_RESULT_LIMIT = 40
_PRIVATE_EXTRACTION_TIMEOUT_SECONDS = 5.0
_ASSERTABLE_UPSTREAM_TYPES = frozenset({"person", "organization", "date", "fact"})
_PRIVATE_EXTRACTOR_MODULE = "ipfs_datasets_py.knowledge_graphs.extraction.extractor"
SELECTED_KG_EXTRACTION_PATH = "KnowledgeGraphExtractor.extract_knowledge_graph"
_EXTERNAL_NON_USER_TOKENS = ("wikidata", "wikipedia")


_PRIVATE_EXTRACTOR_CALL_SOURCE = r"""
import ctypes, importlib, itertools, json, math, os, signal, socket, sys
# -I ignores PYTHONDONTWRITEBYTECODE; suppress source-cache writes explicitly.
sys.dont_write_bytecode = True
request = json.loads(sys.stdin.buffer.read(1048577))
if request.get('schema') != 'complaint-private-graph-call@1': raise SystemExit(2)
manager = request.get('expected_manager_pid')
if type(manager) is not int or manager <= 1 or os.getppid() != manager: raise SystemExit(2)
if ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) != 0: raise SystemExit(2)
if os.getppid() != manager: raise SystemExit(2)
roots = request.get('roots')
if not isinstance(roots, list) or not roots or not all(type(p) is str for p in roots): raise SystemExit(2)
text = request.get('text')
options = {'use_spacy':False,'use_transformers':False,'use_tracer':False,'use_srl':False}
if type(text) is not str or len(text) > 20000 or request.get('options') != options: raise SystemExit(2)
# No inherited provider credentials, user home, executable model helpers, or
# private-query network. This is a Python effect fence, not an OS sandbox.
socket.has_ipv6 = False
denials = {}
class PrivateEffectDenied(PermissionError): pass
def effect_guard(event, args):
    network = (event == 'socket.__new__' and args[1] in (socket.AF_INET,socket.AF_INET6))
    network = network or event in ('socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo')
    network = network or (event in ('socket.connect','socket.sendto') and args[0].family in (socket.AF_INET,socket.AF_INET6))
    if network or event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','os.spawn'):
        denials[event] = denials.get(event,0)+1
        raise PrivateEffectDenied('private_extractor_effect_denied')
sys.addaudithook(effect_guard)
sys.path[:0] = roots
budget = [4096]
def safe(value, depth=0):
    budget[0] -= 1
    if budget[0] < 0 or depth > 8: raise ValueError()
    if value is None or type(value) in (bool,int): return value
    if type(value) is float:
        if not math.isfinite(value): raise ValueError()
        return value
    if type(value) is str:
        if len(value)>20000: raise ValueError()
        value.encode('utf-8')
        return value
    if isinstance(value,dict):
        if len(value)>128 or any(type(k) is not str or len(k)>200 for k in value): raise ValueError()
        return {k:safe(v,depth+1) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        if len(value)>128: raise ValueError()
        return [safe(v,depth+1) for v in value]
    raise ValueError()
def get(record,*names):
    for name in names:
        value = record.get(name) if isinstance(record,dict) else getattr(record,name,None)
        if value is not None and value != '': return value
    return None
def endpoint(value):
    if value is None or type(value) is str: return value
    return {'entity_id':get(value,'entity_id','id'),'name':get(value,'name')}
def records(values, relationship=False):
    if isinstance(values,dict): items=values.items()
    elif isinstance(values,list): items=enumerate(values)
    else: raise ValueError()
    truncated = len(values)>40
    result=[]
    for key,record in itertools.islice(items,40):
        if relationship:
            row={'relationship_id':get(record,'relationship_id','id') or str(key),
                 'relationship_type':get(record,'relationship_type','relation_type','type'),
                 'source_entity':endpoint(get(record,'source_entity','source')),
                 'target_entity':endpoint(get(record,'target_entity','target')),
                 'source_id':get(record,'source_id'),'target_id':get(record,'target_id')}
        else:
            row={'entity_id':get(record,'entity_id','id') or str(key),
                 'entity_type':get(record,'entity_type','type'),'name':get(record,'name')}
        row.update({name:get(record,name) for name in ('properties','source_text','confidence','extraction_method')})
        result.append(safe(row))
    return result,truncated
executed=False
enabled=''
result={'status':'extractor_error','entities':[],'relationships':[],'path_executed':False,'enabled_path':''}
try:
    module = importlib.import_module('ipfs_datasets_py.knowledge_graphs.extraction.extractor')
    cls = getattr(module,'KnowledgeGraphExtractor')
    if not callable(getattr(cls,'extract_knowledge_graph',None)): raise AttributeError()
    extractor = cls(**options)
    graph = extractor.extract_knowledge_graph(text)
    # Importing the class is not execution. This flag is set only after the
    # selected method returns.
    executed=True
    enabled='KnowledgeGraphExtractor.extract_knowledge_graph'
    entities,truncated_entities = records(get(graph,'entities'))
    relationships,truncated_relationships = records(get(graph,'relationships') or {},True)
    result={'status':'ok','entities':entities,'relationships':relationships,
            'entity_result_bound':truncated_entities,'relationship_result_bound':truncated_relationships,
            'path_executed':True,'enabled_path':enabled}
except (ImportError,AttributeError,FileNotFoundError):
    result={'status':'extractor_unavailable','entities':[],'relationships':[],'path_executed':executed,'enabled_path':enabled if executed else ''}
except PrivateEffectDenied:
    result={'status':'extractor_effect_denied','entities':[],'relationships':[],'path_executed':executed,'enabled_path':enabled if executed else ''}
except (ValueError,TypeError,UnicodeError,RecursionError):
    result={'status':'extractor_invalid_result','entities':[],'relationships':[],'path_executed':executed,'enabled_path':enabled if executed else ''}
except BaseException:
    result={'status':'extractor_error','entities':[],'relationships':[],'path_executed':executed,'enabled_path':enabled if executed else ''}
# Optional imports can catch PermissionError; an attempted forbidden effect
# still makes the whole private extraction unavailable, never a valid result.
if denials:
    result={'status':'extractor_effect_denied','entities':[],'relationships':[],'path_executed':executed,'enabled_path':enabled if executed else ''}
result['denied_effect_counts'] = denials
try:
    encoded=json.dumps(result,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
    if len(encoded)>524288: raise ValueError()
except BaseException:
    encoded=json.dumps({'status':'extractor_output_limit','entities':[],'relationships':[],'denied_effect_counts':{},'path_executed':executed,'enabled_path':enabled if executed else ''},ensure_ascii=True,separators=(',',':')).encode()
sys.stdout.buffer.write(encoded);sys.stdout.buffer.flush()
"""

_PRIVATE_EXTRACTOR_MANAGER_SOURCE = r"""
import ctypes, errno, json, os, selectors, signal, subprocess, sys, time
# This isolated manager, never the application process, adopts orphaned call descendants.
if sys.platform != 'linux': raise SystemExit(2)
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(36, 1, 0, 0, 0) != 0: raise SystemExit(2)
request = json.loads(sys.stdin.buffer.read(1048577))
call_source = CALL_SOURCE_LITERAL
cancelled = False
process = None
cleanup_confirmed = False
def cancel(_signal, _frame):
 global cancelled
 cancelled = True
signal.signal(signal.SIGTERM,cancel)
signal.signal(signal.SIGINT,cancel)
def cleanup():
 # First stop the sole call group. Then reap its adopted descendants, including
 # an upstream subprocess left behind when an AnyIO worker's parent exits.
 if process is not None:
  try: os.killpg(process.pid,signal.SIGKILL)
  except ProcessLookupError: pass
  except OSError: return False
  try: process.wait(timeout=.25)
  except subprocess.TimeoutExpired: return False
 deadline=time.monotonic()+.75
 while time.monotonic()<deadline:
  try:
   children=[int(p) for p in open('/proc/self/task/'+str(os.getpid())+'/children').read().split()]
  except (OSError,ValueError): return False
  for pid in children:
   # A direct, unreaped child cannot have its PID reused until this manager waits.
   try: os.kill(pid,signal.SIGKILL)
   except ProcessLookupError: pass
  try:
   while True:
    pid,_=os.waitpid(-1,os.WNOHANG)
    if pid==0: break
  except ChildProcessError:
   return True
  time.sleep(.005)
 return False
result={'outcome':'error','cleanup_confirmed':False}
try:
 deadline=time.monotonic()+float(request['timeout_seconds'])
 call=dict(request['call']);call['expected_manager_pid']=os.getpid()
 raw=json.dumps(call,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
 process=subprocess.Popen([sys.executable,'-I','-c',call_source],stdin=subprocess.PIPE,
  stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ),process_group=0)
 process.stdin.write(raw);process.stdin.close()
 selector=selectors.DefaultSelector()
 for stream in (process.stdout,process.stderr):
  os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ)
 output=bytearray();total=0
 outcome='ok'
 while selector.get_map():
  if cancelled: outcome='cancelled';break
  remaining=deadline-time.monotonic()
  if remaining<=0: outcome='timeout';break
  for key,_ in selector.select(min(.02,remaining)):
   chunk=os.read(key.fileobj.fileno(),65536)
   if not chunk: selector.unregister(key.fileobj);continue
   total+=len(chunk)
   if total>524288: outcome='output_limit';break
   if key.fileobj is process.stdout: output.extend(chunk)
  if outcome!='ok':break
 result={'outcome':outcome,'cleanup_confirmed':False}
 if outcome=='ok':
  try:result['payload']=json.loads(output)
  except (ValueError,UnicodeError):result={'outcome':'error','cleanup_confirmed':False}
except BaseException:
 result={'outcome':'error','cleanup_confirmed':False}
finally:
 cleanup_confirmed=cleanup()
 result['cleanup_confirmed']=cleanup_confirmed
 if result.get('outcome')=='ok' and process is not None and process.returncode!=0:
  result={'outcome':'error','cleanup_confirmed':cleanup_confirmed}
 if not cleanup_confirmed:result={'outcome':'cleanup_unconfirmed','cleanup_confirmed':False}
 for stream in (() if process is None else (process.stdin,process.stdout,process.stderr)):
  try:stream.close()
  except (OSError,ValueError):pass
 sys.stdout.write(json.dumps(result,ensure_ascii=True,allow_nan=False,separators=(',',':')))
 sys.stdout.flush()
"""


def _private_extractor_roots() -> List[str]:
    """Use configured source checkouts; never substitute an installed dataset."""
    import site
    import sys
    from .loader import get_repo_paths
    paths = get_repo_paths()
    roots: List[str] = []
    datasets_present = False
    for package, candidate in (("ipfs_datasets_py", paths.ipfs_datasets_repo),
                               ("ipfs_accelerate_py", paths.ipfs_accelerate_repo)):
        root = Path(candidate).resolve() if candidate is not None else None
        if root is not None and (root / package / "__init__.py").is_file():
            roots.append(str(root))
            datasets_present = datasets_present or package == "ipfs_datasets_py"
            continue
        loaded = sys.modules.get(package)
        source = getattr(loaded, "__file__", None)
        if source:
            root = Path(source).resolve().parent.parent
            if root.name == package and (root / ".git").exists() and (root / package / "__init__.py").is_file():
                roots.append(str(root))
                datasets_present = datasets_present or package == "ipfs_datasets_py"
    if not datasets_present:
        return []
    candidates = [*site.getsitepackages(), *(value for value in sys.path
        if isinstance(value, str) and Path(value).name in {"site-packages", "dist-packages"})]
    for root in candidates:
        if Path(root).is_dir() and root not in roots:
            roots.append(root)
    return roots


def _run_owned_private_extractor(text: str, timeout_seconds: float) -> tuple[str, Any]:
    """Own cold import, construction, extraction, serialization and cleanup.

    The Linux manager adopts and reaps the fixed call's orphaned descendants.
    Missing or abnormal cleanup acknowledgement is never a bounded timeout.
    The deadline covers upstream work; process custody cleanup may add up to
    the bounded manager grace. No private text enters argv, logs or files.
    """
    import signal
    import subprocess
    import sys
    if sys.platform != "linux":
        return "custody_unavailable", None
    process = None
    try:
        roots = _private_extractor_roots()
        if not roots:
            return "extractor_unavailable", None
        call = {"schema": "complaint-private-graph-call@1", "text": text,
                "options": dict(_PRIVATE_EXTRACTOR_OPTIONS), "roots": roots}
        try:
            encoded = json.dumps({"call": call, "timeout_seconds": timeout_seconds},
                                 ensure_ascii=True, allow_nan=False).encode()
        except (TypeError, ValueError, UnicodeError):
            return "invalid_parameters", None
        if len(encoded) > 1048576:
            return "invalid_parameters", None
        source = _PRIVATE_EXTRACTOR_MANAGER_SOURCE.replace("CALL_SOURCE_LITERAL", repr(_PRIVATE_EXTRACTOR_CALL_SOURCE), 1)
        process = None
        with tempfile.TemporaryDirectory(prefix="complaint-private-graph-") as temporary:
            private_root = Path(temporary)
            private_root.chmod(0o700)
            home, cache = private_root / "home", private_root / "temporary"
            home.mkdir(mode=0o700)
            cache.mkdir(mode=0o700)
            environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
            environment.update({"HOME": str(home), "TMPDIR": str(cache),
                "HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "COMMON_CRAWL_AUTO_CLONE_SOURCE": "0", "IPFS_DATASETS_PY_MINIMAL_IMPORTS": "1",
                "IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD": "0", "PYTHONDONTWRITEBYTECODE": "1"})
            try:
                process = subprocess.Popen([sys.executable, "-I", "-c", source], cwd=private_root,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    env=environment, start_new_session=True)
                output, _ = process.communicate(encoded, timeout=timeout_seconds + 1.5)
                if process.returncode != 0 or len(output) > 600000:
                    return "cleanup_unconfirmed", None
                result = json.loads(output)
                if not isinstance(result, dict) or result.get("cleanup_confirmed") is not True:
                    return "cleanup_unconfirmed", None
                outcome = result.get("outcome")
                return (outcome, result.get("payload")) if outcome in {"ok", "timeout", "cancelled", "output_limit", "error"} else ("error", None)
            except subprocess.TimeoutExpired:
                process.send_signal(signal.SIGTERM)
                try:
                    process.communicate(timeout=1.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=.25)
                return "cleanup_unconfirmed", None
            except BaseException as exc:
                if process is not None and process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:
                        process.communicate(timeout=1.5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=.25)
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                return ("cleanup_unconfirmed" if process is not None else "custody_unavailable"), None
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        return ("cleanup_unconfirmed" if process is not None else "custody_unavailable"), None


def _mapping_or_empty(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _upstream_records(graph: Any) -> tuple[List[Any], List[Any], Optional[str]]:
    entities = graph.get("entities") if isinstance(graph, Mapping) else getattr(graph, "entities", None)
    relationships = graph.get("relationships") if isinstance(graph, Mapping) else getattr(graph, "relationships", None)
    if isinstance(entities, Mapping):
        entity_records = list(entities.values())
    elif isinstance(entities, list):
        entity_records = list(entities)
    else:
        return [], [], "extractor_invalid_result"
    if isinstance(relationships, Mapping):
        relationship_records = list(relationships.values())
    elif isinstance(relationships, list):
        relationship_records = list(relationships)
    elif relationships is None:
        relationship_records = []
    else:
        return [], [], "extractor_invalid_result"
    return entity_records, relationship_records, None


def _record_get(record: Any, *names: str) -> Any:
    if isinstance(record, Mapping):
        for name in names:
            if name in record and record.get(name) not in (None, ""):
                return record.get(name)
        return None
    for name in names:
        value = getattr(record, name, None)
        if value not in (None, ""):
            return value
    return None


def _endpoint_identity(endpoint: Any) -> str:
    if endpoint is None:
        return ""
    if isinstance(endpoint, str):
        return endpoint.strip()
    if isinstance(endpoint, Mapping):
        return str(endpoint.get("entity_id") or endpoint.get("id") or endpoint.get("name") or "").strip()
    return str(getattr(endpoint, "entity_id", None) or getattr(endpoint, "name", None) or "").strip()


def _caller_source_context(source_id: Optional[str], metadata: Mapping[str, Any]) -> Dict[str, Any]:
    """Copy only explicit caller identity. Extractor labels are not authorization."""
    context: Dict[str, Any] = {}
    if source_id:
        context["source_id"] = str(source_id)
    for key in (
        "source_kind",
        "source_id",
        "message_id",
        "document_id",
        "source_hash",
        "assertion_status",
        "extractor_version",
        "jurisdiction",
        "actor",
        "name",
        "event_date",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            context[key] = value.strip()
    return context


def executed_extraction_path(payload: Any) -> str:
    """Return the selected extractor path only after that method has returned.

    A successful import of KnowledgeGraphExtractor is not execution.
    """
    if not isinstance(payload, Mapping):
        return ""
    if payload.get("path_executed") is not True:
        return ""
    enabled = payload.get("enabled_path")
    if enabled != SELECTED_KG_EXTRACTION_PATH:
        return ""
    return SELECTED_KG_EXTRACTION_PATH


def _non_user_extraction_kind(record: Any, properties: Mapping[str, Any], extraction_method: Any, entity_type: str) -> str:
    """Legal text, retrieved graph claims, and encyclopedia facts are not user assertions."""
    parts = [
        str(extraction_method or ""),
        str(entity_type or ""),
        str(_record_get(record, "source", "graph_source") or ""),
    ]
    for key, value in properties.items():
        parts.append(str(key))
        if isinstance(value, str):
            parts.append(value)
    blob = " ".join(parts).lower()
    if any(token in blob for token in _EXTERNAL_NON_USER_TOKENS):
        return "wikidata_wikipedia"
    if "retrieved" in blob and "graph" in blob:
        return "retrieved_graph_claim"
    if entity_type.lower() in {"legal", "authority", "statute", "regulation", "case_law", "legal_text"}:
        return "legal_text"
    return ""


def _normalize_upstream_entity(record: Any, index: int, source_text: str) -> Optional[Dict[str, Any]]:
    name = str(_record_get(record, "name") or "").strip()
    entity_type = str(_record_get(record, "entity_type", "type") or "").strip()
    if not name or not entity_type:
        return None
    upstream_id = str(_record_get(record, "entity_id", "id") or "").strip()
    properties = _mapping_or_empty(_record_get(record, "properties"))
    extraction_method = _record_get(record, "extraction_method")
    upstream_source = _record_get(record, "source_text")
    confidence = _record_get(record, "confidence")
    extractor_key = f"upstream-entity:{index}:{entity_type}:{name}"
    attributes: Dict[str, Any] = {
        "upstream_extraction": True,
        "upstream_entity_id": upstream_id,
        "properties": properties,
    }
    span_status = "missing_source_span"
    if name and name != source_text and not (isinstance(upstream_source, str) and upstream_source == source_text and name == upstream_source):
        lookup = locate_unique_byte_span(source_text, name)
        if lookup.deficiency == "" and lookup.start is not None and lookup.end is not None:
            span_status = "unique"
            attributes["description"] = lookup.text
            attributes["source_span"] = {"start": lookup.start, "end": lookup.end, "text": lookup.text, "unit": "byte"}
        elif lookup.deficiency == "ambiguous_source_span":
            span_status = "ambiguous_source_span"
            attributes["description"] = name
        else:
            span_status = lookup.deficiency or "missing_source_span"
    elif isinstance(upstream_source, str) and upstream_source == source_text:
        span_status = "source_text_not_a_span"
    attributes["span_status"] = span_status
    non_user_kind = _non_user_extraction_kind(record, properties, extraction_method, entity_type)
    if non_user_kind:
        attributes["non_user_kind"] = non_user_kind
        attributes["record_type"] = "legal_text" if non_user_kind == "legal_text" else "model_suggestion"
        origin = "model"
    else:
        rule_based = extraction_method in (None, "", "rule_based", "rule-based", "heuristic")
        origin = "heuristic" if rule_based and span_status == "unique" and entity_type.lower() in _ASSERTABLE_UPSTREAM_TYPES else "model"
    provenance = {
        "extractor": "KnowledgeGraphExtractor",
        "upstream_entity_id": upstream_id,
        "extraction_method": "" if extraction_method is None else str(extraction_method),
        "span_status": span_status,
    }
    payload: Dict[str, Any] = {
        "name": name,
        "type": entity_type,
        "origin": origin,
        "extractor_key": extractor_key,
        "attributes": attributes,
        "provenance": provenance,
        "source_span": attributes.get("source_span"),
    }
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        payload["confidence"] = float(confidence)
    return payload


def _normalize_upstream_relationship(
    record: Any,
    index: int,
    key_by_upstream_id: Mapping[str, str],
) -> Optional[Dict[str, Any]]:
    relation_type = str(_record_get(record, "relationship_type", "relation_type", "type") or "").strip()
    if not relation_type:
        return None
    properties = _mapping_or_empty(_record_get(record, "properties"))
    source_endpoint = _record_get(record, "source_entity", "source")
    target_endpoint = _record_get(record, "target_entity", "target")
    source_upstream = _endpoint_identity(source_endpoint) or str(properties.get("source_id") or _record_get(record, "source_id") or "").strip()
    target_upstream = _endpoint_identity(target_endpoint) or str(properties.get("target_id") or _record_get(record, "target_id") or "").strip()
    source_key = key_by_upstream_id.get(source_upstream, "")
    target_key = key_by_upstream_id.get(target_upstream, "")
    if not source_key or not target_key:
        return None
    extraction_method = _record_get(record, "extraction_method")
    upstream_id = str(_record_get(record, "relationship_id", "id") or "").strip()
    confidence = _record_get(record, "confidence")
    non_user_kind = _non_user_extraction_kind(record, properties, extraction_method, relation_type)
    payload: Dict[str, Any] = {
        "type": relation_type,
        "relation_type": relation_type,
        "origin": "model",
        "source_key": source_key,
        "target_key": target_key,
        "attributes": {
            "upstream_extraction": True,
            "upstream_relationship_id": upstream_id,
            "properties": properties,
            "inferred": True,
            **({"non_user_kind": non_user_kind, "record_type": "legal_text" if non_user_kind == "legal_text" else "model_suggestion"} if non_user_kind else {}),
        },
        "provenance": {
            "extractor": "KnowledgeGraphExtractor",
            "upstream_relationship_id": upstream_id,
            "extraction_method": "" if extraction_method is None else str(extraction_method),
        },
    }
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        payload["confidence"] = float(confidence)
    return payload


def _normalize_private_records(
    text: str,
    entity_records: List[Any],
    relationship_records: List[Any],
    caller_context: Mapping[str, Any],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Prepare records without constructing another graph or granting authority."""
    normalized_entities: List[Dict[str, Any]] = []
    key_by_upstream_id: Dict[str, str] = {}
    diagnostics: List[str] = []
    for index, record in enumerate(entity_records[:_PRIVATE_EXTRACTION_RESULT_LIMIT]):
        normalized = _normalize_upstream_entity(record, index, text)
        if normalized is None:
            diagnostics.append("skipped_malformed_entity")
            continue
        normalized_entities.append(normalized)
        upstream_id = str(normalized["provenance"].get("upstream_entity_id") or "")
        if upstream_id:
            key_by_upstream_id[upstream_id] = str(normalized["extractor_key"])
        key_by_upstream_id[str(normalized["extractor_key"])] = str(normalized["extractor_key"])
    if len(entity_records) > _PRIVATE_EXTRACTION_RESULT_LIMIT:
        diagnostics.append("entity_result_bound")
    normalized_relationships: List[Dict[str, Any]] = []
    for index, record in enumerate(relationship_records[:_PRIVATE_EXTRACTION_RESULT_LIMIT]):
        normalized = _normalize_upstream_relationship(record, index, key_by_upstream_id)
        if normalized is None:
            diagnostics.append("skipped_unbound_relationship")
            continue
        normalized_relationships.append(normalized)
    if len(relationship_records) > _PRIVATE_EXTRACTION_RESULT_LIMIT:
        diagnostics.append("relationship_result_bound")
    if not normalized_entities and not normalized_relationships:
        diagnostics.append("extractor_empty")
    kind = str(caller_context.get("source_kind") or "")
    identity = caller_context.get("document_id") if kind == "user_uploaded_document" else caller_context.get("message_id")
    caller_authorized = (
        kind in {"user_statement", "user_uploaded_document"}
        and caller_context.get("assertion_status") == "asserted"
        and bool(caller_context.get("extractor_version"))
        and bool(caller_context.get("source_hash"))
        and bool(identity or caller_context.get("source_id"))
    )
    if not caller_authorized:
        diagnostics.append("caller_source_not_authorized")
        for entity in normalized_entities:
            entity["origin"] = "model"
    return normalized_entities, normalized_relationships, diagnostics


def _candidate_source_binding(
    entities: Sequence[Mapping[str, Any]],
    diagnostics: Sequence[str],
    caller_context: Mapping[str, Any],
) -> Dict[str, Any]:
    """Keep extractor output a candidate until one exact user span is bound."""
    caller_authorized = "caller_source_not_authorized" not in diagnostics
    non_user = [
        str((entity.get("attributes") or {}).get("non_user_kind") or "")
        for entity in entities
        if isinstance(entity, Mapping) and (entity.get("attributes") or {}).get("non_user_kind")
    ]
    bound = []
    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        attributes = entity.get("attributes") if isinstance(entity.get("attributes"), Mapping) else {}
        if attributes.get("non_user_kind") or entity.get("origin") == "model":
            continue
        span = entity.get("source_span") if isinstance(entity.get("source_span"), Mapping) else {}
        if attributes.get("span_status") == "unique" and isinstance(span.get("start"), int) and isinstance(span.get("end"), int):
            bound.append(span)
    source_hash = str(caller_context.get("source_hash") or "")
    source_id = str(caller_context.get("source_id") or caller_context.get("message_id") or "")
    source_version = str(caller_context.get("extractor_version") or "")
    if entities and non_user and len(non_user) == len(list(entities)):
        decision = "withheld"
    elif (
        caller_authorized
        and len(bound) == 1
        and not non_user
        and bool(source_hash)
        and bool(source_id)
        and bool(source_version)
    ):
        decision = "admitted"
    else:
        decision = "unknown"
    return {
        "source_decision": decision,
        "checked": True,
        "withheld": sorted({item for item in non_user if item}),
        "source_id": source_id,
        "source_version": source_version,
        "content_hash": source_hash,
        "span_start": bound[0]["start"] if decision == "admitted" else None,
        "span_end": bound[0]["end"] if decision == "admitted" else None,
    }


def bind_factual_candidate_roles(
    extraction: Mapping[str, Any],
    caller_context: Mapping[str, Any],
) -> Dict[str, Any]:
    """Admit one extracted_candidate role for a path that actually returned.

    The role stays extracted_candidate. It does not become a user assertion,
    and import availability cannot supply candidate_extractor_ref.
    """
    provenance = extraction.get("provenance") if isinstance(extraction.get("provenance"), Mapping) else {}
    enabled = executed_extraction_path(provenance)
    entities = extraction.get("entities") if isinstance(extraction.get("entities"), list) else []
    diagnostics = extraction.get("diagnostics") if isinstance(extraction.get("diagnostics"), list) else []
    binding = _candidate_source_binding(entities, diagnostics, caller_context or {})
    roles: List[Dict[str, Any]] = []
    if enabled:
        from mediator.integrations.contracts import (
            GROUNDING_ROLE_CONTRACT_VERSION,
            ROLE_EXTRACTED_CANDIDATE,
            admit_grounding_role,
        )
        payload: Dict[str, Any] = {
            "contract_version": GROUNDING_ROLE_CONTRACT_VERSION,
            "role": ROLE_EXTRACTED_CANDIDATE,
            "owner_id": "ipfs_datasets_py",
            "case_id": binding["source_id"] or "private-case",
            "graph_revision": "private-kg-extraction",
            "candidate_extractor_ref": enabled,
            "source_decision": binding["source_decision"],
            "source_id": binding["source_id"],
            "source_version": binding["source_version"],
        }
        if binding["source_decision"] == "admitted":
            payload["content_hash"] = binding["content_hash"]
            payload["span_start"] = binding["span_start"]
            payload["span_end"] = binding["span_end"]
        roles.append(admit_grounding_role(payload).as_dict())
    return {
        "path_executed": bool(enabled),
        "enabled_path": enabled,
        "import_available_is_execution": False,
        "source_binding": binding["source_decision"] if enabled else "unknown",
        "binding_checked": bool(enabled),
        "withheld_non_user": binding["withheld"] if enabled else [],
        "roles": roles,
    }


def legal_candidate_role_handoff() -> Dict[str, Any]:
    """Legal passages are not user assertions and do not run the private extractor."""
    return {
        "path_executed": False,
        "enabled_path": "",
        "import_available_is_execution": False,
        "source_binding": "withheld",
        "binding_checked": True,
        "withheld_non_user": ["legal_text"],
        "roles": [],
        "reason": "legal_passage_not_private_extraction",
    }


def _finish_private_extraction(
    payload: Dict[str, Any],
    caller_context: Mapping[str, Any],
    graph_payload: Any,
) -> Dict[str, Any]:
    provenance = dict(payload.get("provenance") or {})
    enabled = executed_extraction_path(graph_payload)
    provenance["path_executed"] = bool(enabled)
    provenance["enabled_path"] = enabled
    provenance["import_available_is_execution"] = False
    payload["provenance"] = provenance
    payload["factual_candidate_roles"] = bind_factual_candidate_roles(payload, caller_context)
    return payload


def prepare_private_extraction(
    text: str,
    caller_context: Mapping[str, Any],
    timeout_seconds: float = _PRIVATE_EXTRACTION_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Return bounded normalized records for both the adapter and canonical builder.

    These records do not carry authority unless the caller supplied the original
    scoped source context. Graph construction remains the caller's single pass.
    """
    provenance = {
        "extractor": "KnowledgeGraphExtractor", "module": _PRIVATE_EXTRACTOR_MODULE,
        "options": dict(_PRIVATE_EXTRACTOR_OPTIONS), "method": "extract_knowledge_graph",
    }
    if not isinstance(text, str) or not text.strip() or len(text) > _PRIVATE_EXTRACTION_TEXT_LIMIT:
        diagnostic = "input_empty" if isinstance(text, str) and not text.strip() else "input_bound_exceeded"
        return _finish_private_extraction(
            {"status": "degraded", "diagnostic": diagnostic, "entities": [], "relationships": [],
             "diagnostics": [diagnostic], "provenance": provenance, "backend_available": False, "bounded": True},
            caller_context, None,
        )
    import math
    try:
        timeout_seconds = float(timeout_seconds)
        if not math.isfinite(timeout_seconds):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        timeout_seconds = _PRIVATE_EXTRACTION_TIMEOUT_SECONDS
    timeout_seconds = min(max(timeout_seconds, .01), _PRIVATE_EXTRACTION_TIMEOUT_SECONDS)
    outcome, graph = _run_owned_private_extractor(text, timeout_seconds)
    diagnostic = ""
    if outcome != "ok":
        diagnostic = {"timeout": "extractor_timeout", "cleanup_unconfirmed": "extractor_cleanup_unconfirmed",
                      "custody_unavailable": "extractor_custody_unavailable", "extractor_unavailable": "extractor_unavailable",
                      "cancelled": "extractor_cancelled", "output_limit": "extractor_output_limit"}.get(outcome, "extractor_error")
    elif not isinstance(graph, dict) or graph.get("status") != "ok":
        status = graph.get("status") if isinstance(graph, dict) else None
        diagnostic = status if type(status) is str and status in {"extractor_unavailable", "extractor_effect_denied", "extractor_invalid_result", "extractor_output_limit", "extractor_error"} else "extractor_invalid_result"
    if diagnostic:
        status = "unavailable" if diagnostic in {"extractor_unavailable", "extractor_custody_unavailable"} else "degraded"
        return _finish_private_extraction(
            {"status": status, "diagnostic": diagnostic, "entities": [], "relationships": [],
             "diagnostics": [diagnostic], "provenance": provenance, "backend_available": False,
             "bounded": diagnostic != "extractor_cleanup_unconfirmed"},
            caller_context, graph if isinstance(graph, dict) else None,
        )
    entity_records, relationship_records, invalid = _upstream_records(graph)
    if invalid:
        return _finish_private_extraction({
            "status": "degraded",
            "diagnostic": invalid,
            "entities": [],
            "relationships": [],
            "diagnostics": [invalid],
            "provenance": provenance,
            "backend_available": False,
            "bounded": True,
        }, caller_context, graph)
    entities, relationships, diagnostics = _normalize_private_records(
        text, entity_records, relationship_records, caller_context,
    )
    if graph.get("entity_result_bound") is True:
        diagnostics.append("entity_result_bound")
    if graph.get("relationship_result_bound") is True:
        diagnostics.append("relationship_result_bound")
    if not entities and not relationships and "extractor_empty" not in diagnostics:
        diagnostics.append("extractor_empty")
    return _finish_private_extraction({
        "status": "available",
        "diagnostic": "",
        "entities": entities,
        "relationships": relationships,
        "diagnostics": diagnostics,
        "provenance": provenance,
        "backend_available": True,
        "bounded": True,
    }, caller_context, graph)


def _run_private_extraction(
    text: str,
    caller_context: Mapping[str, Any],
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Project prepared records through the canonical assertion builder once."""
    extraction = prepare_private_extraction(text, caller_context, timeout_seconds)
    if extraction["status"] != "available":
        return extraction
    from complaint_phases.knowledge_graph import (
        KnowledgeGraphBuilder, entity_to_graph_entity, relationship_to_graph_relationship,
    )
    built = KnowledgeGraphBuilder().build_from_text(
        text, source_context=caller_context,
        extracted_entities=extraction["entities"],
        extracted_relationships=extraction["relationships"],
        extractor_provenance=extraction["provenance"],
        include_local_heuristics=False,
    )
    return {**extraction,
        "entities": [entity_to_graph_entity(entity) for entity in built.entities.values()
                     if (entity.attributes or {}).get("upstream_extraction") is True],
        "relationships": [relationship_to_graph_relationship(relationship) for relationship in built.relationships.values()
                          if (relationship.attributes or {}).get("upstream_extraction") is True]}


def extract_graph_from_text(
    text: str,
    *,
    source_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = metadata or {}
    entities: List[GraphEntity] = []
    relationships: List[GraphRelationship] = []
    artifact_id = source_id or metadata.get("artifact_id") or ""
    claim_element_id = str(metadata.get("claim_element_id") or "").strip()
    claim_element_text = str(metadata.get("claim_element_text") or metadata.get("claim_element") or "").strip()
    legal_passage = source_is_legal_norm(metadata)
    embedded_provenance = metadata.get("provenance")
    graph_provenance: Dict[str, Any] = (
        dict(embedded_provenance) if isinstance(embedded_provenance, Mapping) else {}
    )
    if artifact_id:
        graph_provenance.setdefault("source_id", str(artifact_id))
    for provenance_key in (
        "source_type",
        "source_record_id",
        "source_ref",
        "source_url",
        "source_system",
        "content_hash",
        "acquired_at",
        "parser_version",
        "extraction_version",
    ):
        if metadata.get(provenance_key) not in (None, ""):
            graph_provenance.setdefault(provenance_key, metadata[provenance_key])

    if artifact_id:
        entities.append(
            GraphEntity(
                entity_id=artifact_id,
                entity_type="artifact",
                name=str(metadata.get("title") or metadata.get("filename") or artifact_id),
                confidence=1.0,
                attributes={
                    "source_id": artifact_id,
                    "source_url": metadata.get("source_url", ""),
                    "mime_type": metadata.get("mime_type", ""),
                    "provenance": graph_provenance,
                },
            )
        )

    claim_node_id = ""
    if claim_element_id or claim_element_text:
        claim_node_id = claim_element_id or _stable_identifier("claim_element", claim_element_text)
        entities.append(
            GraphEntity(
                entity_id=claim_node_id,
                entity_type="claim_element",
                name=claim_element_text or claim_element_id,
                confidence=1.0,
                attributes={
                    "claim_element_id": claim_element_id,
                    "claim_element_text": claim_element_text,
                    "claim_type": metadata.get("claim_type", ""),
                    "provenance": graph_provenance,
                },
            )
        )

    submitted = text if isinstance(text, str) else ""
    timeout_raw = metadata.get("extraction_timeout_seconds", _PRIVATE_EXTRACTION_TIMEOUT_SECONDS)
    try:
        timeout_seconds = float(timeout_raw)
    except (TypeError, ValueError):
        timeout_seconds = _PRIVATE_EXTRACTION_TIMEOUT_SECONDS
    timeout_seconds = min(max(timeout_seconds, 0.01), _PRIVATE_EXTRACTION_TIMEOUT_SECONDS)
    private_extraction: Dict[str, Any] = {
        "method": "extract_knowledge_graph",
        "options": dict(_PRIVATE_EXTRACTOR_OPTIONS),
        "diagnostics": [],
    }
    sentences: List[str] = []
    payload_status = "unavailable"
    backend_available = False
    degraded_reason: Optional[str] = None
    implementation_status = "unavailable"

    if not submitted.strip():
        private_extraction["status"] = "degraded"
        private_extraction["diagnostic"] = "input_empty"
        private_extraction["diagnostics"] = ["input_empty"]
        payload_status = "degraded"
        degraded_reason = "input_empty"
        implementation_status = "degraded"
    elif len(submitted) > _PRIVATE_EXTRACTION_TEXT_LIMIT:
        private_extraction["status"] = "degraded"
        private_extraction["diagnostic"] = "input_bound_exceeded"
        private_extraction["diagnostics"] = ["input_bound_exceeded"]
        payload_status = "degraded"
        degraded_reason = "input_bound_exceeded"
        implementation_status = "degraded"
    elif legal_passage:
        sentences = _split_sentences(submitted)
        if not sentences and submitted.strip():
            sentences = [submitted.strip()]
        passage_kind = legal_namespace_kind(metadata)
        for index, sentence in enumerate(sentences[:25]):
            fact_id = mint_graph_record_id(
                passage_kind, artifact_id or source_id or "legal", str(index), sentence,
            )
            entities.append(
                GraphEntity(
                    entity_id=fact_id,
                    entity_type=passage_kind,
                    name=sentence[:120],
                    confidence=0.6,
                    attributes={
                        "text": sentence,
                        "sentence_index": index,
                        "source_id": artifact_id,
                        "record_kind": passage_kind,
                        "about_complainant": False,
                        "extraction_mode": "legal_heuristic",
                        "provenance": graph_provenance,
                    },
                )
            )
            if artifact_id:
                relationships.append(
                    GraphRelationship(
                        relationship_id=_stable_identifier("rel", artifact_id, fact_id, "cites_authority"),
                        source_id=artifact_id,
                        target_id=fact_id,
                        relation_type="cites_authority",
                        confidence=1.0,
                        attributes={"sentence_index": index, "provenance": graph_provenance, "extraction_mode": "legal_heuristic"},
                    )
                )
        private_extraction["status"] = "legal_heuristic"
        private_extraction["diagnostic"] = "legal_passage_not_private_extraction"
        private_extraction["diagnostics"] = ["legal_passage_not_private_extraction"]
        payload_status = "available-fallback"
        implementation_status = "legal_heuristic"
        backend_available = False
    else:
        caller_context = _caller_source_context(str(artifact_id or source_id or ""), metadata)
        extraction = _run_private_extraction(submitted, caller_context, timeout_seconds)
        private_extraction.update({
            "status": extraction["status"],
            "diagnostic": extraction["diagnostic"],
            "diagnostics": list(extraction["diagnostics"]),
            "provenance": extraction["provenance"],
            "bounded": extraction.get("bounded", True),
            "factual_candidate_roles": extraction.get("factual_candidate_roles"),
        })
        if extraction["status"] == "available":
            entities.extend(extraction["entities"])
            relationships.extend(extraction["relationships"])
            sentences = _split_sentences(submitted)
            if not sentences and submitted.strip():
                sentences = [submitted.strip()]
            payload_status = "available"
            backend_available = True
            implementation_status = "upstream"
        else:
            degraded_reason = str(extraction["diagnostic"] or extraction["status"])
            payload_status = extraction["status"]
            backend_available = False
            implementation_status = extraction["status"]

    return with_adapter_metadata(
        GraphPayload(
            status=payload_status,
            source_id=source_id or "",
            entities=entities,
            relationships=relationships,
            metadata={
                **metadata,
                "text_length": len(submitted),
                "sentence_count": len(sentences),
                "provenance": graph_provenance,
                "private_extraction": private_extraction,
            },
        ).as_dict(),
        operation="extract_graph_from_text",
        backend_available=backend_available,
        degraded_reason=degraded_reason,
        implementation_status=implementation_status,
        extra_metadata={"private_extraction": private_extraction},
    )


def query_graph_support(
    claim_element_id: str,
    *,
    graph_id: Optional[str] = None,
    graph_version: Optional[str] = None,
    support_facts: Optional[List[Dict[str, Any]]] = None,
    claim_type: Optional[str] = None,
    claim_element_text: Optional[str] = None,
    max_results: int = 10,
    filters: Optional[Mapping[str, Any]] = None,
    provenance: Optional[Mapping[str, Any]] = None,
    query_backend: Optional[GraphQuery] = None,
) -> Dict[str, Any]:
    query = build_graph_support_query(
        claim_element_id,
        graph_id=graph_id,
        graph_version=graph_version,
        claim_type=claim_type,
        claim_element_text=claim_element_text,
        max_results=max_results,
        filters=filters,
        provenance=provenance,
    )
    backend_error: Optional[Exception] = None
    if query_backend is not None:
        try:
            backend_response = query_backend.query_support(query)
            if not isinstance(backend_response, Mapping):
                raise TypeError("graph query backend must return a mapping")
            normalized_response = dict(backend_response)
            normalized_response.setdefault("status", "available")
            normalized_response.setdefault("graph_id", query["graph_id"])
            normalized_response.setdefault("graph_version", query["graph_version"])
            normalized_response.setdefault("claim_element_id", query["claim_element_id"])
            normalized_response.setdefault("claim_type", query["claim_type"])
            normalized_response.setdefault("claim_element_text", query["claim_element_text"])
            normalized_response.setdefault("results", [])
            normalized_response.setdefault("summary", {"result_count": len(normalized_response["results"])})
            normalized_response.setdefault("provenance", query["provenance"])
            normalized_response["query"] = query
            return with_adapter_metadata(
                normalized_response,
                operation="query_graph_support",
                backend_available=True,
                implementation_status="backend",
                extra_metadata={
                    "graph_id": query["graph_id"],
                    "graph_version": query["graph_version"],
                },
            )
        except Exception as exc:  # A backend failure must not remove local support review.
            backend_error = exc

    facts = [
        fact
        for fact in support_facts or []
        if isinstance(fact, Mapping) and _fact_matches_filters(fact, query["filters"])
    ]
    ranked_results = []
    support_by_kind: Dict[str, int] = {}
    support_by_source: Dict[str, int] = {}
    source_family_counts: Dict[str, int] = {}
    record_scope_counts: Dict[str, int] = {}
    artifact_family_counts: Dict[str, int] = {}
    corpus_family_counts: Dict[str, int] = {}
    content_origin_counts: Dict[str, int] = {}
    parse_source_counts: Dict[str, int] = {}
    input_format_counts: Dict[str, int] = {}
    quality_tier_counts: Dict[str, int] = {}
    unique_source_refs = set()
    unique_source_records = set()
    passage_anchored_count = 0
    deduped_results: Dict[str, Dict[str, Any]] = {}

    def _count(target: Dict[str, int], value: Any) -> None:
        text = str(value or "").strip()
        if text:
            target[text] = target.get(text, 0) + 1

    for fact in facts:
        score = _score_fact_match(fact, claim_element_id, claim_element_text or "")
        result = {
            **fact,
            "score": score,
            "matched_claim_element": bool(
                (claim_element_id and str(fact.get("claim_element_id") or "") == claim_element_id)
                or (claim_element_text and str(fact.get("claim_element_text") or "") == claim_element_text)
            ),
            "duplicate_count": 1,
        }
        support_kind = str(fact.get("support_kind") or "unknown")
        source_table = str(fact.get("source_table") or "unknown")
        support_by_kind[support_kind] = support_by_kind.get(support_kind, 0) + 1
        support_by_source[source_table] = support_by_source.get(source_table, 0) + 1
        source_family = str(fact.get("source_family") or "").strip()
        source_record_id = fact.get("source_record_id")
        source_ref = str(fact.get("source_ref") or "").strip()
        source_passage = fact.get("source_passage") if isinstance(fact.get("source_passage"), dict) else {}
        if source_ref:
            unique_source_refs.add(source_ref)
        if source_family and source_record_id not in (None, ""):
            unique_source_records.add((source_family, str(source_record_id)))
        if source_passage.get("chunk_id") or fact.get("chunk_id"):
            passage_anchored_count += 1
        _count(source_family_counts, source_family)
        _count(record_scope_counts, fact.get("record_scope"))
        _count(artifact_family_counts, fact.get("artifact_family"))
        _count(corpus_family_counts, fact.get("corpus_family"))
        _count(content_origin_counts, fact.get("content_origin"))
        _count(parse_source_counts, fact.get("parse_source"))
        _count(input_format_counts, fact.get("input_format"))
        _count(quality_tier_counts, fact.get("quality_tier"))

        dedup_key = _fact_dedup_key(result)
        existing = deduped_results.get(dedup_key)
        if existing is None:
            deduped_results[dedup_key] = {
                **result,
                "support_kind_set": [support_kind],
                "source_table_set": [source_table],
            }
            continue

        existing["duplicate_count"] += 1
        existing["score"] = max(existing.get("score", 0.0), result["score"])
        existing["confidence"] = max(existing.get("confidence", 0.0), result.get("confidence", 0.0))
        if support_kind not in existing["support_kind_set"]:
            existing["support_kind_set"].append(support_kind)
        if source_table not in existing["source_table_set"]:
            existing["source_table_set"].append(source_table)

    ranked_results = _cluster_semantically_similar_results(list(deduped_results.values()))

    ranked_results.sort(
        key=lambda item: (
            item.get("score", 0.0),
            item.get("matched_claim_element", False),
            item.get("confidence", 0.0),
            item.get("duplicate_count", 0),
        ),
        reverse=True,
    )

    limited_results = ranked_results[:max_results]
    unique_fact_count = len(deduped_results)
    duplicate_fact_count = max(len(facts) - unique_fact_count, 0)
    semantic_cluster_count = len(ranked_results)
    semantic_duplicate_count = max(unique_fact_count - semantic_cluster_count, 0)

    typed_results = [
        GraphSupportMatch(
            fact_id=str(item.get("fact_id") or ""),
            text=str(item.get("text") or ""),
            score=float(item.get("score", 0.0) or 0.0),
            confidence=float(item.get("confidence", 0.0) or 0.0),
            matched_claim_element=bool(item.get("matched_claim_element", False)),
            duplicate_count=int(item.get("duplicate_count", 1) or 1),
            cluster_size=int(item.get("cluster_size", item.get("duplicate_count", 1)) or 1),
            cluster_texts=[str(text) for text in item.get("cluster_texts", []) or []],
            support_kind=str(item.get("support_kind") or ""),
            source_table=str(item.get("source_table") or ""),
            support_kind_set=[str(kind) for kind in item.get("support_kind_set", []) or []],
            source_table_set=[str(source) for source in item.get("source_table_set", []) or []],
            claim_element_id=str(item.get("claim_element_id") or ""),
            claim_element_text=str(item.get("claim_element_text") or ""),
            support_ref=str(item.get("support_ref") or ""),
            support_label=str(item.get("support_label") or ""),
            source_family=str(item.get("source_family") or ""),
            source_record_id=item.get("source_record_id"),
            source_ref=str(item.get("source_ref") or ""),
            record_scope=str(item.get("record_scope") or ""),
            artifact_family=str(item.get("artifact_family") or ""),
            corpus_family=str(item.get("corpus_family") or ""),
            content_origin=str(item.get("content_origin") or ""),
            parse_source=str(item.get("parse_source") or ""),
            input_format=str(item.get("input_format") or ""),
            quality_tier=str(item.get("quality_tier") or ""),
            quality_score=float(item.get("quality_score", 0.0) or 0.0),
            evidence_record_id=item.get("evidence_record_id"),
            authority_record_id=item.get("authority_record_id"),
            metadata={
                key: value
                for key, value in item.items()
                if key not in {
                    "fact_id",
                    "text",
                    "score",
                    "confidence",
                    "matched_claim_element",
                    "duplicate_count",
                    "cluster_size",
                    "cluster_texts",
                    "support_kind",
                    "source_table",
                    "support_kind_set",
                    "source_table_set",
                    "claim_element_id",
                    "claim_element_text",
                    "support_ref",
                    "support_label",
                    "source_family",
                    "source_record_id",
                    "source_ref",
                    "record_scope",
                    "artifact_family",
                    "corpus_family",
                    "content_origin",
                    "parse_source",
                    "input_format",
                    "quality_tier",
                    "quality_score",
                    "evidence_record_id",
                    "authority_record_id",
                }
            },
        )
        for item in limited_results
    ]

    graph_contract = _graph_query_contract(graph_id)
    payload = with_adapter_metadata(
        GraphSupportResult(
            status="available-fallback" if KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable",
            claim_element_id=claim_element_id,
            claim_type=claim_type or "",
            claim_element_text=claim_element_text or "",
            graph_id=graph_id or "",
            results=typed_results,
            summary=GraphSupportSummary(
                result_count=len(limited_results),
                total_fact_count=len(facts),
                unique_fact_count=unique_fact_count,
                duplicate_fact_count=duplicate_fact_count,
                semantic_cluster_count=semantic_cluster_count,
                semantic_duplicate_count=semantic_duplicate_count,
                unique_source_ref_count=len(unique_source_refs),
                unique_source_record_count=len(unique_source_records),
                passage_anchored_count=passage_anchored_count,
                support_by_kind=support_by_kind,
                support_by_source=support_by_source,
                source_family_counts=source_family_counts,
                record_scope_counts=record_scope_counts,
                artifact_family_counts=artifact_family_counts,
                corpus_family_counts=corpus_family_counts,
                content_origin_counts=content_origin_counts,
                parse_source_counts=parse_source_counts,
                input_format_counts=input_format_counts,
                quality_tier_counts=quality_tier_counts,
                max_score=ranked_results[0]["score"] if ranked_results else 0.0,
            ),
            metadata={},
        ).as_dict(),
        operation="query_graph_support",
        backend_available=KNOWLEDGE_GRAPHS_AVAILABLE,
        degraded_reason=(
            backend_error
            or (GRAPHS_ERROR if not KNOWLEDGE_GRAPHS_AVAILABLE else None)
        ),
        implementation_status="fallback" if facts or KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable",
        extra_metadata={
            **graph_contract,
            "graph_id": query["graph_id"],
            "graph_version": query["graph_version"],
            "query_filters": query["filters"],
        },
    )
    payload["graph_version"] = query["graph_version"]
    payload["provenance"] = query["provenance"]
    payload["query"] = query
    for result in payload.get("results", []):
        result_metadata = result.get("metadata") if isinstance(result, dict) else None
        if isinstance(result_metadata, dict) and isinstance(result_metadata.get("provenance"), dict):
            result["provenance"] = dict(result_metadata["provenance"])
    return payload


def _write_private_graph_ciphertext(destination: Any, name: str, envelope: bytes) -> None:
    """Publish only authenticated ciphertext, privately and without replacement."""
    import secrets
    import stat

    root = Path(os.path.abspath(destination))
    if root.resolve() != root:
        raise ValueError("private_graph_destination_alias")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".private-graph-" + secrets.token_hex(16)
    try:
        metadata = os.fstat(descriptor)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise ValueError("private_graph_destination_permissions")
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=descriptor)
        with os.fdopen(handle, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(envelope)
            output.flush()
            os.fsync(output.fileno())
        current = root.lstat()
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise ValueError("private_graph_destination_changed")
        try:
            os.link(temporary, name, src_dir_fd=descriptor, dst_dir_fd=descriptor, follow_symlinks=False)
        except FileExistsError:
            existing = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            with os.fdopen(existing, "rb") as source:
                item = os.fstat(source.fileno())
                if (not stat.S_ISREG(item.st_mode) or item.st_uid != os.getuid()
                        or stat.S_IMODE(item.st_mode) != 0o600 or item.st_size != len(envelope)
                        or source.read(len(envelope) + 1) != envelope):
                    raise ValueError("private_graph_destination_exists")
        os.fsync(descriptor)
    finally:
        try:
            os.unlink(temporary, dir_fd=descriptor)
        except FileNotFoundError:
            pass
        os.close(descriptor)


def publish_private_graph_case_manifest(
    graph_payload: Dict[str, Any],
    private_context: Mapping[str, Any],
) -> Dict[str, Any]:
    """Bind a private graph into the case manifest. Public names stay opaque hashes.

    The filename, node labels, and provenance travel only inside the encrypted
    manifest and the sealed fact-graph envelope. The destination filename is the
    manifest generation.
    """
    from integrations.private_storage import (
        CaseManifestConflict,
        PrivateRevisionError,
        PrivateStorageError,
        publish_case_manifest,
        read_case_manifest,
    )

    if not isinstance(graph_payload, Mapping):
        raise TypeError("graph_payload must be a mapping")
    repository = private_context.get("case_manifest_repository")
    if not repository:
        raise PrivateRevisionError("case manifest repository is missing", code="role_missing", state="recoverable")
    supplied = private_context.get("case_artifacts")
    if not isinstance(supplied, Mapping):
        raise PrivateRevisionError("case artifacts are missing", code="role_missing", state="recoverable")
    graph_body = json.dumps(dict(graph_payload), sort_keys=True, default=str).encode("utf-8")
    artifacts: Dict[str, Any] = {}
    for role in ("answer", "fact_graph", "legal_rule_source", "evaluation", "proof"):
        item = supplied.get(role)
        if role == "fact_graph":
            revision = role
            if isinstance(item, Mapping) and item.get("revision"):
                revision = str(item["revision"])
            artifacts[role] = {"body": graph_body, "revision": revision}
            continue
        if isinstance(item, (bytes, bytearray)):
            artifacts[role] = {"body": bytes(item), "revision": role}
        elif isinstance(item, Mapping) and isinstance(item.get("body"), (bytes, bytearray)):
            artifacts[role] = {
                "body": bytes(item["body"]),
                "revision": str(item.get("revision") or role),
            }
        else:
            raise PrivateRevisionError("case role is missing", code="role_missing", state="recoverable")
    labels = private_context.get("labels")
    if labels is None:
        labels = []
        for entity in graph_payload.get("entities") or []:
            if isinstance(entity, Mapping):
                labels.append(str(entity.get("label") or entity.get("text") or ""))
    provenance = private_context.get("provenance")
    if not isinstance(provenance, Mapping):
        raw_provenance = graph_payload.get("provenance")
        provenance = dict(raw_provenance) if isinstance(raw_provenance, Mapping) else {}
    filename = str(private_context.get("filename") or "")
    try:
        publication = publish_case_manifest(
            repository,
            tenant_id=str(private_context["tenant_id"]),
            case_id=str(private_context["case_id"]),
            principal_id=str(private_context.get("principal_id") or private_context["tenant_id"]),
            key=private_context.get("key"),
            key_id=private_context.get("key_id"),
            expected_head=str(private_context.get("expected_head") or ""),
            expected_hash=str(private_context.get("expected_hash") or ""),
            artifacts=artifacts,
            private_names={"filename": filename, "labels": list(labels), "provenance": dict(provenance)},
            backend=str(private_context.get("case_backend") or "local"),
            iroh_store=private_context.get("iroh_store"),
        )
    except CaseManifestConflict:
        return {
            "status": "conflict",
            "persisted": False,
            "committed": False,
            "verified": False,
            "private_artifact": True,
            "private_indexing": "unsupported",
            "plaintext_catalog": False,
            "plaintext_index": False,
            "code": "manifest_conflict",
            "overwrites_existing": False,
            "minted_completion": False,
        }
    except PrivateStorageError as exc:
        return {
            "status": "unlock_needed" if getattr(exc, "code", "") == "key_unavailable" else "recoverable",
            "persisted": False,
            "committed": False,
            "verified": False,
            "private_artifact": True,
            "private_indexing": "unsupported",
            "plaintext_catalog": False,
            "code": str(getattr(exc, "code", "") or "private_graph_failed"),
            "overwrites_existing": False,
            "minted_completion": False,
        }
    destination = private_context.get("destination_dir")
    if destination is not None:
        opened = read_case_manifest(
            repository,
            tenant_id=str(private_context["tenant_id"]),
            case_id=str(private_context["case_id"]),
            principal_id=str(private_context.get("principal_id") or private_context["tenant_id"]),
            key=private_context.get("key"),
            key_id=private_context.get("key_id"),
        )
        envelope = (opened or {}).get("envelopes", {}).get("fact_graph")
        if not isinstance(envelope, (bytes, bytearray)) or not publication.generation:
            return {
                "status": "recoverable",
                "persisted": False,
                "verified": False,
                "private_artifact": True,
                "plaintext_catalog": False,
                "code": "readback_mismatch",
                "overwrites_existing": False,
                "minted_completion": False,
            }
        _write_private_graph_ciphertext(destination, publication.generation + ".bin", bytes(envelope))
    public = publication.as_dict()
    public.update({
        "status": "stored-private",
        "persisted": True,
        "verified": True,
        "private_artifact": True,
        "private_indexing": "unsupported",
        "plaintext_catalog": False,
        "plaintext_index": False,
        "opaque_ref": publication.generation,
        "overwrites_existing": False,
    })
    return public


def _private_material_parts(graph_payload: Mapping[str, Any]) -> List[tuple]:
    """Split private graph bytes that must be sealed before replication."""
    parts: List[tuple] = []
    source_text = graph_payload.get("source_text")
    if isinstance(source_text, str) and source_text:
        parts.append(("assertion-envelope", "source-text", source_text.encode("utf-8")))
    elif isinstance(source_text, (bytes, bytearray)) and source_text:
        parts.append(("assertion-envelope", "source-text", bytes(source_text)))
    for kind, revision, key in (
        ("index", "embeddings", "embeddings"),
        ("index", "indexes", "indexes"),
    ):
        value = graph_payload.get(key)
        if value in (None, "", [], (), {}):
            continue
        if isinstance(value, (bytes, bytearray)):
            body = bytes(value)
        else:
            body = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
        parts.append((kind, revision, body))
    return parts


def _seal_private_materials(graph_payload: Mapping[str, Any], private_context: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Encrypt source text, embeddings, and indexes before any replicate call."""
    from integrations.private_storage import store_private_artifact

    replicate = private_context.get("replicate")
    receipts: List[Dict[str, Any]] = []
    for kind, revision, body in _private_material_parts(graph_payload):
        receipts.append(store_private_artifact(
            body,
            access=private_context["access"],
            tenant_id=str(private_context["tenant_id"]),
            case_id=str(private_context["case_id"]),
            principal_id=str(private_context.get("principal_id") or private_context["tenant_id"]),
            artifact_kind=kind,
            revision=str(revision),
            key=private_context.get("key"),
            key_id=private_context.get("key_id"),
            key_provider=private_context.get("key_provider"),
            backend=private_context.get("backend"),
            backend_name=private_context.get("backend_name"),
            pin_content=bool(private_context.get("pin_content", True)),
            replicate=replicate if callable(replicate) else None,
        ))
    return receipts


FACTUAL_GRAPH_ARTIFACT_SCHEMA = "cimp-mgnd-14-factual-graph-v1"
FACTUAL_GRAPH_ARTIFACT_KIND = "fact-graph"
_FACTUAL_ID_KEYS = frozenset({
    "id",
    "stable_id",
    "source_id",
    "entity_id",
    "message_id",
    "source_identity",
    "graph_id",
    "previous_stable_id",
    "new_stable_id",
    "previous_entity_id",
    "new_entity_id",
    "invalidated_entity_id",
    "superseded_by",
    "retracted_by",
})


def _factual_raw_graph(graph: Any) -> Dict[str, Any]:
    if hasattr(graph, "to_dict") and callable(graph.to_dict):
        raw = graph.to_dict()
    elif isinstance(graph, Mapping):
        raw = dict(graph)
    else:
        raise TypeError("factual graph must be a mapping or knowledge graph")
    if not isinstance(raw, Mapping):
        raise TypeError("factual graph document must be a mapping")
    return dict(raw)


def _factual_pairs(value: Any) -> List[tuple]:
    if isinstance(value, Mapping):
        return [(str(key), item) for key, item in value.items() if isinstance(item, Mapping)]
    if isinstance(value, list):
        return [(str(item.get("id") or ""), item) for item in value if isinstance(item, Mapping)]
    return []


def factual_graph_invalidations(raw: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Support that a revision marked stale. Contradiction rows are not included."""
    found: List[Dict[str, Any]] = []
    for record_id, relationship in _factual_pairs(raw.get("relationships")):
        attributes = relationship.get("attributes") if isinstance(relationship.get("attributes"), Mapping) else {}
        if attributes.get("activity_status") != "invalidated" and attributes.get("support_invalidated") is not True:
            continue
        found.append({
            "id": str(record_id or relationship.get("id") or ""),
            "kind": "relationship",
            "activity_status": str(attributes.get("activity_status") or "invalidated"),
            "reason": str(attributes.get("invalidation_reason") or ""),
            "invalidated_entity_id": str(attributes.get("invalidated_entity_id") or ""),
        })
    for record_id, entity in _factual_pairs(raw.get("entities")):
        attributes = entity.get("attributes") if isinstance(entity.get("attributes"), Mapping) else {}
        if attributes.get("support_invalidated") is not True:
            continue
        found.append({
            "id": str(record_id or entity.get("id") or ""),
            "kind": "entity",
            "activity_status": "invalidated",
            "reason": "support_invalidated",
            "invalidated_entity_id": str(record_id or entity.get("id") or ""),
        })
    found.sort(key=lambda item: (item["kind"], item["id"], item["reason"]))
    return found


def factual_graph_plaintext_ids(document: Mapping[str, Any]) -> set[str]:
    """Source and assertion identities that must not be reused as storage ids."""
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in _FACTUAL_ID_KEYS and isinstance(item, str) and item:
                    found.add(item)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(document)
    return found


def build_factual_graph_artifact(graph: Any) -> Dict[str, Any]:
    """Canonical factual revision document. It carries no ciphertext storage id."""
    raw = _factual_raw_graph(graph)
    metadata = dict(raw.get("metadata") or {}) if isinstance(raw.get("metadata"), Mapping) else {}
    ledger = metadata.get("factual_ledger") if isinstance(metadata.get("factual_ledger"), Mapping) else {}
    revisions = [dict(item) for item in list(ledger.get("revisions") or []) if isinstance(item, Mapping)]
    states = ledger.get("assertion_states") if isinstance(ledger.get("assertion_states"), Mapping) else {}
    conflicts = []
    for item in list(ledger.get("conflicts") or []):
        if isinstance(item, Mapping) and str(item.get("status") or "unresolved") == "unresolved":
            conflicts.append(dict(item))
    provenance = dict(raw.get("provenance") or {}) if isinstance(raw.get("provenance"), Mapping) else {}
    return {
        "schema": FACTUAL_GRAPH_ARTIFACT_SCHEMA,
        "graph_id": str(raw.get("graph_id") or metadata.get("graph_id") or ""),
        "graph_version": str(raw.get("graph_version") or metadata.get("graph_version") or "0"),
        "provenance": provenance,
        "revisions": revisions,
        "assertion_states": {str(key): dict(value) for key, value in states.items() if isinstance(value, Mapping)},
        "entities": dict(raw.get("entities") or {}) if isinstance(raw.get("entities"), Mapping) else list(raw.get("entities") or []),
        "relationships": dict(raw.get("relationships") or {}) if isinstance(raw.get("relationships"), Mapping) else list(raw.get("relationships") or []),
        "invalidations": factual_graph_invalidations(raw),
        "unresolved_conflicts": conflicts,
        "metadata": metadata,
    }


def encode_factual_graph_artifact(document: Mapping[str, Any]) -> bytes:
    if str(document.get("schema") or "") != FACTUAL_GRAPH_ARTIFACT_SCHEMA:
        raise ValueError("factual graph artifact schema mismatch")
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def seal_factual_graph_artifact(
    graph: Any,
    *,
    access: Any,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    revision: str,
    backend: Any,
    backend_name: str,
    key: Optional[bytes] = None,
    key_id: Optional[str] = None,
    key_provider: Any = None,
    pin_content: bool = False,
) -> Dict[str, Any]:
    """Seal one factual graph through the automatic private-artifact owner.

    There is no plaintext CID, local-cache, or JSON fallback. A rejected
    backend leaves no graph document behind. The returned storage id is the
    ciphertext address, never a source or assertion id.
    """
    if backend is None:
        raise ValueError("factual graph storage requires the bound private backend")
    document = build_factual_graph_artifact(graph)
    payload = encode_factual_graph_artifact(document)
    plaintext_ids = factual_graph_plaintext_ids(document)
    from integrations.ipfs_datasets.storage import store_automatic_private_artifact
    from integrations.private_storage import PrivateStorageError

    try:
        receipt = store_automatic_private_artifact(
            payload,
            access=access,
            tenant_id=str(tenant_id),
            case_id=str(case_id),
            principal_id=str(principal_id),
            artifact_kind=FACTUAL_GRAPH_ARTIFACT_KIND,
            revision=str(revision),
            key=key,
            key_id=key_id,
            key_provider=key_provider,
            backend=backend,
            backend_name=str(backend_name),
            pin_content=bool(pin_content),
        )
    except PrivateStorageError:
        raise
    except Exception as exc:
        raise PrivateStorageError(
            "factual graph artifact store failed",
            code="artifact_unavailable",
        ) from exc
    storage_id = str(receipt.get("cid") or "")
    if not storage_id or storage_id in plaintext_ids or storage_id.startswith("assertion:"):
        raise PrivateStorageError(
            "ciphertext storage id collided with a plaintext identifier",
            code="storage_id_rejected",
        )
    if receipt.get("verified") is not True or receipt.get("private_artifact") is False:
        raise PrivateStorageError("factual graph ciphertext was not verified", code="readback_mismatch")
    return {
        "status": "stored-private",
        "persisted": True,
        "private_artifact": True,
        "plaintext_fallback": False,
        "plaintext_catalog": False,
        "plaintext_cache": False,
        "plaintext_publication": False,
        "graph_registry_used": False,
        "artifact_kind": FACTUAL_GRAPH_ARTIFACT_KIND,
        "artifact_revision": str(revision),
        "ciphertext_storage_id": storage_id,
        "key_id": str(receipt.get("key_id") or ""),
        "document": document,
        "payload": payload,
        "receipt": receipt,
    }


def open_factual_graph_artifact(
    storage_id: str,
    *,
    access: Any,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    revision: str,
    backend: Any,
    backend_name: str,
    key: Optional[bytes] = None,
    key_id: Optional[str] = None,
    key_provider: Any = None,
) -> Dict[str, Any]:
    """Open one sealed factual graph for the same owner and case binding.

    Wrong key, wrong case, and corrupt ciphertext raise. This function does
    not read a plaintext JSON document and does not write a replacement graph.
    """
    if backend is None:
        raise ValueError("factual graph reload requires the bound private backend")
    if not isinstance(storage_id, str) or not storage_id or storage_id.startswith("assertion:"):
        raise ValueError("ciphertext storage id is required")
    from integrations.ipfs_datasets.storage import retrieve_private_artifact

    opened = retrieve_private_artifact(
        storage_id,
        access=access,
        tenant_id=str(tenant_id),
        case_id=str(case_id),
        principal_id=str(principal_id),
        artifact_kind=FACTUAL_GRAPH_ARTIFACT_KIND,
        revision=str(revision),
        key=key,
        key_id=key_id,
        key_provider=key_provider,
        backend=backend,
        backend_name=str(backend_name),
    )
    data = opened.get("data")
    if opened.get("status") != "available" or not isinstance(data, (bytes, bytearray)):
        from integrations.private_storage import PrivateStorageError
        raise PrivateStorageError("factual graph ciphertext is unavailable", code="artifact_unavailable")
    try:
        document = json.loads(bytes(data).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        from integrations.private_storage import PrivateArtifactIntegrityError
        raise PrivateArtifactIntegrityError("malformed") from exc
    if not isinstance(document, dict) or document.get("schema") != FACTUAL_GRAPH_ARTIFACT_SCHEMA:
        from integrations.private_storage import PrivateArtifactIntegrityError
        raise PrivateArtifactIntegrityError("malformed")
    if encode_factual_graph_artifact(document) != bytes(data):
        from integrations.private_storage import PrivateArtifactIntegrityError
        raise PrivateArtifactIntegrityError("malformed")
    return document


def persist_private_graph_snapshot(
    graph_payload: Dict[str, Any],
    private_context: Mapping[str, Any],
    *,
    graph_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Seal a case graph; never create a plaintext catalog or client index."""
    if not isinstance(graph_payload, Mapping):
        raise TypeError("graph_payload must be a mapping")
    if not isinstance(private_context, Mapping):
        raise TypeError("private_context must be a mapping")
    if private_context.get("case_manifest_repository"):
        published = publish_private_graph_case_manifest(dict(graph_payload), private_context)
        published["plaintext_publication"] = False
        return published
    missing_key = private_context.get("key") is None and private_context.get("key_provider") is None
    if private_context.get("locked") or missing_key:
        return {"status": "unlock_needed", "persisted": False, "private_artifact": True,
                "private_indexing": "unsupported", "plaintext_catalog": False,
                "overwrites_existing": False}
    from integrations.ipfs_datasets.storage import retrieve_bytes
    from integrations.private_storage import (
        PrivateArtifactBinding, PrivateKeyLockedError, PrivateStorageError,
        _resolve_key, assert_access_matches_binding, open_private_artifact,
    )
    try:
        material_receipts = _seal_private_materials(graph_payload, private_context)
        body = json.dumps(dict(graph_payload), sort_keys=True, default=str).encode("utf-8")
        binding = PrivateArtifactBinding(
            tenant_id=str(private_context["tenant_id"]), case_id=str(private_context["case_id"]),
            principal_id=str(private_context.get("principal_id") or private_context["tenant_id"]),
            artifact_kind="fact-graph", revision=str(private_context.get("revision") or "fact-graph-1"),
        )
        from integrations.private_storage import store_private_artifact
        replicate = private_context.get("replicate")
        receipt = store_private_artifact(
            body, access=private_context["access"], tenant_id=binding.tenant_id,
            case_id=binding.case_id, principal_id=binding.principal_id,
            artifact_kind=binding.artifact_kind, revision=binding.revision,
            key=private_context.get("key"), key_id=private_context.get("key_id"),
            key_provider=private_context.get("key_provider"), backend=private_context.get("backend"),
            backend_name=private_context.get("backend_name"), pin_content=bool(private_context.get("pin_content", True)),
            replicate=replicate if callable(replicate) else None,
        )
        destination = private_context.get("destination_dir")
        if destination is not None:
            loaded = retrieve_bytes(str(receipt.get("cid") or ""), backend=private_context.get("backend"),
                                    backend_name=private_context.get("backend_name"))
            blob = loaded.get("data")
            if loaded.get("status") not in {"available", "degraded"} or not isinstance(blob, (bytes, bytearray)):
                raise PrivateStorageError("private graph ciphertext unavailable", code="readback_mismatch")
            assert_access_matches_binding(private_context["access"], binding)
            key_id, key = _resolve_key(binding, key=private_context.get("key"), key_id=private_context.get("key_id"),
                                       key_provider=private_context.get("key_provider"))
            if key_id != receipt.get("key_id") or open_private_artifact(bytes(blob), binding=binding, key=key, expected_key_id=key_id) != body:
                raise PrivateStorageError("private graph ciphertext mismatch", code="readback_mismatch")
            name = "".join(ch if ch.isalnum() else "-" for ch in str(receipt.get("cid") or ""))[:80] or "fact-graph"
            _write_private_graph_ciphertext(destination, name + ".bin", bytes(blob))
    except Exception as exc:
        return {"status": "unlock_needed" if isinstance(exc, PrivateKeyLockedError) else "recoverable",
                "persisted": False, "verified": False, "private_artifact": True,
                "private_indexing": "unsupported", "plaintext_catalog": False,
                "error": type(exc).__name__, "code": str(getattr(exc, "code", "") or "private_graph_failed"),
                "overwrites_existing": False}
    return {"status": "stored-private", "persisted": True, "private_artifact": True,
            "private_indexing": "unsupported", "plaintext_catalog": False, "plaintext_index": False,
            "plaintext_publication": False, "replication_plaintext": False,
            "graph_id": str(graph_id or ""), "cid": receipt.get("cid"), "verified": receipt.get("verified") is True,
            "deferred": receipt.get("deferred") is True, "receipt": receipt,
            "material_receipts": material_receipts, "overwrites_existing": False}


def persist_graph_snapshot(
    graph_payload: Dict[str, Any],
    *,
    graph_id: Optional[str] = None,
    graph_version: Optional[str] = None,
    graph_changed: Optional[bool] = None,
    existing_graph: bool = False,
    persistence_metadata: Optional[Dict[str, Any]] = None,
    provenance: Optional[Mapping[str, Any]] = None,
    persistence: Optional[GraphPersistence] = None,
    private_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if private_context is not None:
        return persist_private_graph_snapshot(graph_payload, private_context, graph_id=graph_id)
    if not isinstance(graph_payload, Mapping):
        raise TypeError("graph_payload must be a mapping")

    request = build_graph_persistence_request(
        graph_payload,
        graph_id=graph_id,
        graph_version=graph_version,
        provenance=provenance,
        metadata=persistence_metadata,
    )
    entity_count = len(request["entities"])
    relationship_count = len(request["relationships"])
    source_id = str(graph_payload.get("source_id") or "")
    metadata = graph_payload.get("metadata", {}) if isinstance(graph_payload.get("metadata"), dict) else {}
    derived_graph_changed = bool(graph_changed) if graph_changed is not None else bool(entity_count or relationship_count) and not existing_graph
    created = bool(derived_graph_changed and not existing_graph)
    reused = bool(existing_graph and not created)
    stable_graph_id = request["graph_id"]
    fact_registry_summary = _extract_fact_registry_summary(
        dict(graph_payload),
        metadata,
        persistence_metadata,
    )
    backend_result: Dict[str, Any] = {}
    persistence_error: Optional[Exception] = None
    if persistence is not None:
        try:
            raw_result = persistence.persist_snapshot(request)
            if not isinstance(raw_result, Mapping):
                raise TypeError("graph persistence backend must return a mapping")
            backend_result = dict(raw_result)
        except Exception as exc:  # Keep snapshot metadata available in degraded mode.
            persistence_error = exc

    backend_used = persistence is not None and persistence_error is None
    snapshot_metadata = {
        "source_id": source_id,
        **(persistence_metadata or {}),
        "fact_registry_summary": fact_registry_summary,
        "lineage": {
            "status": str(graph_payload.get("status") or ""),
            "text_length": metadata.get("text_length", 0),
            "sentence_count": metadata.get("sentence_count", 0),
        },
    }

    if persistence is None:
        client_contract = _persist_nodes_through_client(stable_graph_id, request)
        existing_snapshot = _GRAPH_SNAPSHOT_REGISTRY.get(stable_graph_id)
        local_created = existing_snapshot is None and not existing_graph
        local_reused = existing_snapshot is not None or existing_graph
        snapshot_metadata.update(
            {
                "persistence_scope": "adapter_memory",
                "backend_storage_available": _graph_storage_module is not None,
                **client_contract,
            }
        )
        snapshot_record = {
            "graph_id": stable_graph_id,
            "source_id": source_id,
            "status": "stored-fallback",
            "node_count": entity_count,
            "edge_count": relationship_count,
            "entities": list(request["entities"]),
            "relationships": list(request["relationships"]),
            "fact_registry_summary": fact_registry_summary,
            "metadata": snapshot_metadata,
            "graph_version": request["graph_version"],
            "snapshot_id": request["snapshot_id"],
            "content_hash": request["content_hash"],
            "provenance": dict(request["provenance"]),
        }
        if client_contract.get("client_write_ok"):
            try:
                resumed = resume_graph_revisions(stable_graph_id)
            except Exception:
                resumed = {}
            if resumed:
                snapshot_record["revisions"] = list(resumed.get("revisions") or [])
                snapshot_record["superseded_facts"] = list(resumed.get("superseded_facts") or [])
                snapshot_record["cross_graph_links"] = list(resumed.get("cross_graph_links") or [])
                snapshot_record["provenance_chain"] = list(resumed.get("provenance") or [])
        snapshot_record["plaintext_publication"] = False
        _GRAPH_SNAPSHOT_REGISTRY[stable_graph_id] = snapshot_record
        payload = with_adapter_metadata(
            GraphSnapshotResult(
                status="stored-fallback",
                graph_id=stable_graph_id,
                persisted=True,
                created=(
                    local_created
                    if graph_changed is None
                    else bool(created and not existing_snapshot)
                ),
                reused=(
                    local_reused
                    if graph_changed is None
                    else bool(reused or existing_snapshot)
                ),
                node_count=entity_count,
                edge_count=relationship_count,
                metadata=snapshot_metadata,
            ).as_dict(),
            operation="persist_graph_snapshot",
            backend_available=_graph_storage_module is not None,
            degraded_reason=_graph_storage_error,
            implementation_status="fallback",
            extra_metadata={
                "graph_version": request["graph_version"],
                "snapshot_id": request["snapshot_id"],
                "content_hash": request["content_hash"],
                **client_contract,
                "persistence_scope": "adapter_memory",
            },
        )
    else:
        base_payload = GraphSnapshotResult(
            status=(
                str(backend_result.get("status") or "persisted")
                if backend_used
                else "degraded"
            ),
            graph_id=stable_graph_id,
            persisted=(
                bool(backend_result.get("persisted", True))
                if backend_used
                else False
            ),
            created=(
                bool(backend_result.get("created", created))
                if backend_used
                else created
            ),
            reused=(
                bool(backend_result.get("reused", reused))
                if backend_used
                else reused
            ),
            node_count=(
                int(backend_result.get("node_count", entity_count) or 0)
                if backend_used
                else entity_count
            ),
            edge_count=(
                int(backend_result.get("edge_count", relationship_count) or 0)
                if backend_used
                else relationship_count
            ),
            metadata=snapshot_metadata,
        ).as_dict()
        if backend_result:
            for key, value in backend_result.items():
                if key != "metadata":
                    base_payload[key] = value
            if isinstance(backend_result.get("metadata"), Mapping):
                base_payload["metadata"].update(backend_result["metadata"])
        payload = with_adapter_metadata(
            base_payload,
            operation="persist_graph_snapshot",
            backend_available=backend_used,
            degraded_reason=persistence_error,
            implementation_status="backend" if backend_used else "degraded",
            extra_metadata={
                "graph_version": request["graph_version"],
                "snapshot_id": request["snapshot_id"],
                "content_hash": request["content_hash"],
            },
        )
    payload["graph_version"] = request["graph_version"]
    payload["snapshot_id"] = request["snapshot_id"]
    payload["content_hash"] = request["content_hash"]
    backend_provenance = backend_result.get("provenance")
    merged_provenance = dict(request["provenance"])
    if isinstance(backend_provenance, Mapping):
        merged_provenance.update(
            {
                str(key): value
                for key, value in backend_provenance.items()
                if value not in (None, "", [], (), {})
            }
        )
    payload["graph_id"] = request["graph_id"]
    payload["provenance"] = merged_provenance
    return payload


def query_graph_snapshot(
    graph_id: Optional[str] = None,
    *,
    source_id: Optional[str] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    """Return adapter-level graph snapshots by graph id or source id.

    The current adapter keeps a deterministic in-process fallback registry so
    graph projections remain queryable even when an upstream graph store is not
    installed.
    """
    normalized_limit = max(0, int(limit or 0))
    snapshots = list(_GRAPH_SNAPSHOT_REGISTRY.values())
    if graph_id:
        snapshots = [snapshot for snapshot in snapshots if snapshot.get("graph_id") == graph_id]
    if source_id:
        snapshots = [snapshot for snapshot in snapshots if snapshot.get("source_id") == source_id]
    snapshots = snapshots[:normalized_limit] if normalized_limit else []
    fact_registry_summary = _merge_fact_registry_summaries([
        snapshot.get("fact_registry_summary", {})
        for snapshot in snapshots
        if isinstance(snapshot.get("fact_registry_summary"), dict)
    ])
    return with_adapter_metadata(
        {
            "status": "found" if snapshots else "missing",
            "found": bool(snapshots),
            "graph_id": graph_id or "",
            "source_id": source_id or "",
            "snapshot_count": len(snapshots),
            "snapshots": [dict(snapshot) for snapshot in snapshots],
            "fact_registry_summary": fact_registry_summary,
        },
        operation="query_graph_snapshot",
        backend_available=_graph_storage_module is not None,
        degraded_reason=_graph_storage_error,
        implementation_status="fallback",
    )


def resolve_duplicate_entities(
    entities: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Resolve near-duplicate actors and entities across testimony and document graphs.

    Groups entities by normalised name using :func:`_texts_semantically_similar`.
    Returns a mapping of canonical entity IDs to the merged entity record plus
    a list of absorbed duplicates, and a summary of how many were merged.

    ``entities`` should be dicts with at least ``entity_id`` (or ``id``) and
    ``name`` (or ``text``) keys.  The ``source_kind`` field is used to label
    whether the entity came from ``testimony``, ``evidence``, or ``law``.
    """
    clusters: List[Dict[str, Any]] = []

    for entity in entities or []:
        name = str(entity.get("name") or entity.get("text") or "")
        eid = str(entity.get("entity_id") or entity.get("id") or "")
        source_kind = str(entity.get("source_kind") or "unknown")
        namespace = _resolution_namespace(entity)
        domain = _record_domain(entity)

        matched: Optional[Dict[str, Any]] = None
        for cluster in clusters:
            if not _resolution_namespaces_compatible(cluster["resolution_namespace"], namespace):
                continue
            if cluster["resolution_kind"] != domain:
                continue
            if _texts_semantically_similar(cluster["canonical_name"], name):
                matched = cluster
                break

        if matched is None:
            clusters.append(
                {
                    "canonical_entity_id": eid or _stable_identifier("entity", name, namespace),
                    "canonical_name": name,
                    "resolution_namespace": namespace,
                    "resolution_kind": domain,
                    "source_kinds": [source_kind] if source_kind else [],
                    "entity_ids": [eid] if eid else [],
                    "names": [name] if name else [],
                    "duplicate_count": 1,
                    "absorbed": [],
                }
            )
            continue

        matched["duplicate_count"] += 1
        if eid and eid not in matched["entity_ids"]:
            matched["entity_ids"].append(eid)
        if name and name not in matched["names"]:
            matched["names"].append(name)
        if source_kind and source_kind not in matched["source_kinds"]:
            matched["source_kinds"].append(source_kind)
        matched["absorbed"].append(
            {
                "entity_id": eid,
                "name": name,
                "source_kind": source_kind,
            }
        )

    # Legacy IDs are not globally namespaced. Preserve them as source IDs and
    # prevent a dictionary overwrite when distinct domains reused the same ID.
    counts: Dict[str, int] = {}
    for cluster in clusters:
        cid = cluster["canonical_entity_id"]
        counts[cid] = counts.get(cid, 0) + 1
    for cluster in clusters:
        if counts[cluster["canonical_entity_id"]] > 1:
            cluster["canonical_entity_id"] = "resolved:" + hashlib.sha256(json.dumps(
                [cluster["resolution_kind"], cluster["canonical_name"], sorted(cluster["entity_ids"])],
                ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    entity_map: Dict[str, Dict[str, Any]] = {c["canonical_entity_id"]: c for c in clusters}
    merged_count = sum(len(c["absorbed"]) for c in clusters)

    return {
        "resolved": True,
        "entity_count": len(clusters),
        "input_count": len(entities or []),
        "merged_count": merged_count,
        "entity_map": entity_map,
        "clusters": clusters,
    }


def attach_provenance_edges(
    facts: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    artifacts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build provenance edges linking facts → chunks → artifacts.

    Each edge has a stable ``edge_id``, ``from_id``, ``to_id``, and
    ``edge_kind`` (``fact_to_chunk`` or ``chunk_to_artifact``).  Only edges
    where both ends are present are emitted.

    Returns ``{edges, fact_to_chunk_count, chunk_to_artifact_count,
    unresolved_fact_count, unresolved_chunk_count}``.
    """
    chunk_by_ref: Dict[str, Dict[str, Any]] = {}
    for chunk in chunks or []:
        cref = str(chunk.get("chunk_ref") or chunk.get("chunk_id") or chunk.get("id") or "")
        if cref:
            chunk_by_ref[cref] = chunk

    artifact_by_id: Dict[str, Dict[str, Any]] = {}
    for artifact in artifacts or []:
        aid = str(artifact.get("artifact_id") or artifact.get("id") or "")
        if aid:
            artifact_by_id[aid] = artifact

    edges: List[Dict[str, Any]] = []
    fact_to_chunk_count = 0
    chunk_to_artifact_count = 0
    unresolved_fact_count = 0
    unresolved_chunk_count = 0
    seen_chunk_artifact_edges: set = set()

    for fact in facts or []:
        fid = str(fact.get("fact_id") or fact.get("id") or "")
        cref = str(fact.get("chunk_ref") or "")

        if not cref or cref not in chunk_by_ref:
            unresolved_fact_count += 1
            continue

        edge_id = _stable_identifier("edge_fc", fid, cref)
        edges.append(
            {
                "edge_id": edge_id,
                "edge_kind": "fact_to_chunk",
                "from_id": fid,
                "from_kind": "fact",
                "to_id": cref,
                "to_kind": "chunk",
            }
        )
        fact_to_chunk_count += 1

        chunk = chunk_by_ref[cref]
        aid = str(chunk.get("artifact_id") or chunk.get("source_artifact_id") or "")
        if not aid or aid not in artifact_by_id:
            unresolved_chunk_count += 1
            continue

        ca_key = f"{cref}|{aid}"
        if ca_key in seen_chunk_artifact_edges:
            continue
        seen_chunk_artifact_edges.add(ca_key)
        ca_edge_id = _stable_identifier("edge_ca", cref, aid)
        edges.append(
            {
                "edge_id": ca_edge_id,
                "edge_kind": "chunk_to_artifact",
                "from_id": cref,
                "from_kind": "chunk",
                "to_id": aid,
                "to_kind": "artifact",
            }
        )
        chunk_to_artifact_count += 1

    return {
        "attached": True,
        "edge_count": len(edges),
        "fact_to_chunk_count": fact_to_chunk_count,
        "chunk_to_artifact_count": chunk_to_artifact_count,
        "unresolved_fact_count": unresolved_fact_count,
        "unresolved_chunk_count": unresolved_chunk_count,
        "edges": edges,
    }


def get_authority_graph_api_version() -> Dict[str, Any]:
    """Return a snapshot of the authority graph API version information.

    Reflects the refreshed ``ipfs_datasets_py`` submodule layout so that the
    workspace can verify compatibility at runtime.
    """
    modules_available = {
        "knowledge_graphs": _knowledge_graphs_module is not None,
        "graph_extraction": _graph_extraction_module is not None,
        "graph_query": _graph_query_module is not None,
        "graph_storage": _graph_storage_module is not None,
        "graph_lineage": _graph_lineage_module is not None,
    }
    module_paths = {
        name: getattr(mod, "__file__", "") or ""
        for name, mod in {
            "knowledge_graphs": _knowledge_graphs_module,
            "graph_extraction": _graph_extraction_module,
            "graph_query": _graph_query_module,
            "graph_storage": _graph_storage_module,
            "graph_lineage": _graph_lineage_module,
        }.items()
        if mod is not None
    }
    return {
        "api_version": "authority-graph-v1",
        "backend_available": KNOWLEDGE_GRAPHS_AVAILABLE,
        "modules_available": modules_available,
        "module_paths": module_paths,
        "error": str(GRAPHS_ERROR or "") or None,
        "submodule": "ipfs_datasets_py",
    }


__all__ = [
    "KNOWLEDGE_GRAPHS_AVAILABLE",
    "GRAPHS_ERROR",
    "GraphProvenance",
    "GraphPersistenceRequest",
    "GraphSupportQuery",
    "GraphPersistence",
    "GraphQuery",
    "GraphRepository",
    "build_graph_persistence_request",
    "build_graph_support_query",
    "extract_graph_from_text",
    "prepare_private_extraction",
    "SELECTED_KG_EXTRACTION_PATH",
    "executed_extraction_path",
    "bind_factual_candidate_roles",
    "legal_candidate_role_handoff",
    "query_graph_support",
    "persist_graph_snapshot",
    "persist_private_graph_snapshot",
    "resume_graph_revisions",
    "query_graph_snapshot",
    "resolve_duplicate_entities",
    "attach_provenance_edges",
    "get_authority_graph_api_version",
    "FACTUAL_ASSERTION_KIND",
    "AUTHORITY_SOURCE_KIND",
    "RULE_CANDIDATE_KIND",
    "LEGAL_REQUIREMENT_KIND",
    "SUPPORT_LINK_KIND",
    "CONTRADICTION_LINK_KIND",
    "DISTINCT_GRAPH_RECORD_KINDS",
    "record_kind_from_id",
    "mint_graph_record_id",
    "source_is_legal_norm",
    "legal_namespace_kind",
    "build_namespaced_support_link",
]
