"""Inventory pinned A/Data/Kit origins against the thirteen mediator hooks.

The JSON inventory is historical evidence. Current checkout visibility and
operation registration are observed independently; neither availability flags
nor the historical snapshot authorize a case effect. Probes use synthetic
sources and local ciphertext storage, without qualifying Kit durability.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from applications.complaint_workspace import WorkspaceAccess
from integrations.ipfs_accelerate.routers import pinned_grok47_dispatch_kwargs
from integrations.ipfs_datasets.capabilities import DECLARED_OWNER_PINS, record_sdk_owner_identities
from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode
from integrations.ipfs_datasets.storage import LocalCacheIPFSBackend
from integrations.private_storage import (
    PrivateArtifactBindingError,
    PrivateArtifactIntegrityError,
    retrieve_private_artifact,
    store_private_artifact,
)
from mediator.claim_support_hooks import ClaimSupportHook
from mediator.evidence_hooks import EvidenceAnalysisHook, EvidenceStateHook, EvidenceStorageHook
from mediator.hook_runtime import (
    LEGAL_EVIDENCE_OPERATIONS,
    bind_hook_execution_context,
    dispatch_registered_hook_operation,
    operation_handler_call_count,
    register_legal_evidence_operations,
)
from mediator.legal_authority_hooks import (
    LegalAuthorityAnalysisHook,
    LegalAuthoritySearchHook,
    LegalAuthorityStorageHook,
)
from mediator.legal_hooks import (
    LegalClassificationHook,
    QuestionGenerationHook,
    StatuteRetrievalHook,
    SummaryJudgmentHook,
)
from mediator.web_evidence_hooks import WebEvidenceIntegrationHook, WebEvidenceSearchHook
from mediator.mediator import Mediator


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "ux" / "complaint_ux_overhaul" / "sdk_hook_inventory.json"
_COMMIT = __import__("re").compile(r"^[0-9a-f]{40}$")
_PLAINTEXT = b"synthetic-cimp-ux-02-private-source"
_SENTENCE = "Ada Lovelace met Bob Smith at the office."

_HOOKS = (
    (LegalClassificationHook, "classify_complaint", "legal_classifier"),
    (StatuteRetrievalHook, "retrieve_statutes", "statute_retriever"),
    (SummaryJudgmentHook, "generate_requirements", "summary_judgment"),
    (QuestionGenerationHook, "generate_questions", "question_generator"),
    (EvidenceStorageHook, "store_evidence", "evidence_storage"),
    (EvidenceStateHook, "upsert_evidence_record", "evidence_state"),
    (EvidenceAnalysisHook, "analyze_evidence_for_claim", "evidence_analysis"),
    (ClaimSupportHook, "get_claim_support_gaps", "claim_support"),
    (LegalAuthoritySearchHook, "lookup_bounded_corpus", "legal_authority_search"),
    (LegalAuthorityStorageHook, "store_acquired_authority", "legal_authority_storage"),
    (LegalAuthorityAnalysisHook, "analyze_authorities_for_claim", "legal_authority_analysis"),
    (WebEvidenceSearchHook, "search_for_evidence", "web_evidence_search"),
    (WebEvidenceIntegrationHook, "discover_and_store_evidence", "web_evidence_integration"),
)


def _inventory() -> dict:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def preserve_historical_inventory():
    before = INVENTORY_PATH.read_bytes()
    yield
    assert INVENTORY_PATH.read_bytes() == before


def _git(path: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(path), *args],
        stderr=subprocess.PIPE, text=True, timeout=5,
    ).strip()


def _prefer_pinned_checkout(owner: str) -> None:
    checkout = ROOT / "external" / owner
    entry = str(checkout)
    if checkout.is_dir() and entry not in sys.path:
        sys.path.insert(0, entry)
    loaded = sys.modules.get(owner)
    origin = str(getattr(loaded, "__file__", "") or "")
    if loaded is not None and f"/external/{owner}/" not in origin.replace("\\", "/"):
        for name in list(sys.modules):
            if name == owner or name.startswith(owner + "."):
                del sys.modules[name]
        if entry not in sys.path:
            sys.path.insert(0, entry)


def _legal_context() -> dict:
    empty = {"role": "event_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True}
    return {
        "status": "unknown",
        "jurisdiction": "unknown",
        "jurisdiction_explicit": False,
        "context_revision": 1,
        "applicable_law_date": dict(empty, role="applicable_law_date"),
        "event_date": empty,
        "filing_reference_date": dict(empty, role="filing_reference_date"),
        "corpus_retrieval_date": dict(empty, role="corpus_retrieval_date"),
    }


def _privacy(owner_id: str, case_id: str) -> dict:
    policy = privacy_policy_for_mode(owner_id, case_id, "local")
    return build_complaint_privacy_context(policy, user_id=owner_id, case_id=case_id, data_class="fact_kg")


def _authorized_request(operation: str, now: datetime) -> tuple[object, dict, dict]:
    owner_id = "synthetic-ux02-owner"
    case_id = "synthetic-ux02-case"
    privacy = _privacy(owner_id, case_id)
    source_hash = "ab" * 32
    context = bind_hook_execution_context(
        operation=operation,
        owner_id=owner_id,
        case_id=case_id,
        session_id="session-ux02",
        session_revision=1,
        graph_revision="gr-ux02-1",
        legal_context=_legal_context(),
        purpose=operation,
        deadline=now + timedelta(minutes=1),
        source_bindings=[{"source_id": "src-ux02", "content_hash": source_hash}],
        privacy_context=privacy,
    )
    request = {
        "operation": operation,
        "role": "extract_facts",
        "target_ref": "target.ux02",
        "source_refs": [{"source_id": "src-ux02", "content_hash": source_hash}],
    }
    if operation == "acquire_legal_sources":
        request["citation_ref"] = "citation.ux02"
    elif operation == "ingest_private_evidence":
        request["evidence_ref"] = "evidence.ux02"
    else:
        request["graph_revision"] = "gr-ux02-1"
    return context, request, privacy


def test_inventory_is_a_historical_observation_not_a_live_availability_policy() -> None:
    inventory = _inventory()
    assert inventory["schema"] == "complaint-ux-sdk-hook-inventory@1"
    assert inventory["task_id"] == "CIMP-UX-02"
    assert [row["name"] for row in inventory["owners"]] == ["ipfs_accelerate_py", "ipfs_datasets_py", "ipfs_kit_py"]
    for row in inventory["owners"]:
        assert _COMMIT.fullmatch(row["declared_pin"])
        if row["checked_out_commit_status"] == "available":
            assert _COMMIT.fullmatch(row["checked_out_commit"])
            assert row["checked_out_commit_error_type"] == ""
        else:
            assert row["checked_out_commit_status"] == "unavailable"
            assert row["checked_out_commit"] == "" and row["checked_out_commit_error_type"]
    assert len(inventory["mediator_hooks"]) == 13
    assert {row["operation"] for row in inventory["registered_operations"]} == {
        "acquire_legal_sources", "ingest_private_evidence", "refresh_grounding",
    }


def test_current_owner_reports_match_real_checkouts_and_typed_revision_visibility() -> None:
    observed = record_sdk_owner_identities()
    assert {row["name"] for row in observed} == set(DECLARED_OWNER_PINS)
    for live in observed:
        assert live["declared_pin"] == DECLARED_OWNER_PINS[live["name"]]
        assert _COMMIT.fullmatch(live["declared_pin"])
        canonical = ROOT / live["canonical_source_path"]
        assert canonical.is_file() is live["populated"]
        expected_kind = "populated_checkout" if live["populated"] else (
            "opaque_gitlink" if live["declared_submodule"] else "missing_checkout"
        )
        assert live["checkout_kind"] == expected_kind
        if live["checked_out_commit_status"] == "available":
            head = _git(ROOT / live["relative_path"], "rev-parse", "--verify", "HEAD")
            assert _COMMIT.fullmatch(head)
            assert live["checked_out_commit"] == head
            assert live["checked_out_commit_error_type"] == ""
        else:
            assert live["checked_out_commit_status"] == "unavailable"
            assert live["checked_out_commit"] == "" and live["checked_out_commit_error_type"]
        assert live["pin_is_observed_head"] is (
            live["checked_out_commit_status"] == "available"
            and live["checked_out_commit"] == live["declared_pin"]
        )


def test_revision_observer_reads_a_real_commit_and_refuses_missing_git_metadata(tmp_path) -> None:
    from integrations.ipfs_datasets.loader import observe_checked_out_commit
    checkout = tmp_path / "readable-checkout"
    checkout.mkdir()
    _git(checkout, "init", "--quiet")
    _git(checkout, "-c", "user.name=Synthetic inventory fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "--quiet", "--allow-empty", "-m", "Synthetic revision observation")
    head = _git(checkout, "rev-parse", "HEAD")
    assert observe_checked_out_commit(checkout) == {"status": "available", "error_type": "", "commit": head}
    missing = tmp_path / "no-git-metadata"
    missing.mkdir()
    refused = observe_checked_out_commit(missing)
    assert refused["status"] == "unavailable" and refused["commit"] == ""
    assert isinstance(refused["error_type"], str) and refused["error_type"]


def test_thirteen_hooks_are_bound_to_the_actual_mediator(tmp_path) -> None:
    inventory = _inventory()
    rows = inventory["mediator_hooks"]
    assert len(rows) == 13
    assert len({row["hook"] for row in rows}) == 13
    assert [row["mediator_attribute"] for row in rows] == [item[2] for item in _HOOKS]
    mediator = Mediator([], evidence_db_path=str(tmp_path / "evidence.duckdb"),
        legal_authority_db_path=str(tmp_path / "authorities.duckdb"),
        claim_support_db_path=str(tmp_path / "support.duckdb"))
    for recorded, (cls, method_name, attribute) in zip(rows, _HOOKS):
        method = getattr(cls, method_name)
        assert callable(method)
        assert recorded["hook"] == cls.__name__
        assert recorded["method"] == method_name
        instance = getattr(mediator, attribute)
        assert isinstance(instance, cls) and instance.mediator is mediator
        assert getattr(instance, method_name).__self__ is instance
        origin = Path(inspect.getfile(cls)).resolve()
        assert origin.is_relative_to(ROOT)
        assert recorded["owner"] == origin.relative_to(ROOT).as_posix()


def test_bounded_adapter_probes_use_synthetic_sources_and_local_ciphertext_storage(tmp_path) -> None:
    inventory = _inventory()
    _prefer_pinned_checkout("ipfs_datasets_py")
    from ipfs_datasets_py.knowledge_graphs.extraction.extractor import KnowledgeGraphExtractor
    from ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api import (
        search_us_code_corpus_from_parameters,
    )

    extractor_origin = Path(inspect.getfile(KnowledgeGraphExtractor)).resolve()
    assert "external/ipfs_datasets_py/" in extractor_origin.as_posix()
    basic = getattr(KnowledgeGraphExtractor, "extract_knowledge_graph")
    enhanced = getattr(KnowledgeGraphExtractor, "extract_enhanced_knowledge_graph")
    symbols = {row["symbol"]: row for row in inventory["callable_symbols"]}
    assert callable(basic) and callable(enhanced)
    extractor = KnowledgeGraphExtractor(use_spacy=False, use_transformers=False, use_tracer=False, use_srl=False,
        relation_patterns=[{"pattern": r"(Ada Lovelace) met (Bob Smith)", "name": "met", "confidence": 0.9}])
    assert not any((extractor.use_spacy, extractor.use_transformers, extractor.use_tracer, extractor.use_srl))
    assert extractor.tracer is None
    graph = extractor.extract_knowledge_graph(_SENTENCE, 0.7, 0.5)
    assert type(graph).__name__ == "KnowledgeGraph"
    assert {"Ada Lovelace", "Bob Smith"} <= {entity.name for entity in graph.entities.values()}
    assert all(entity.name in entity.source_text for entity in graph.entities.values())
    assert any(relation.relationship_type == "met" and relation.source_entity.name == "Ada Lovelace"
        and relation.target_entity.name == "Bob Smith" and _SENTENCE in relation.source_text
        for relation in graph.relationships.values())
    assert inventory["adapter_probes"]["knowledge_graph"]["enhanced_called"] is False

    legal = asyncio.run(search_us_code_corpus_from_parameters({}))
    assert Path(inspect.getfile(search_us_code_corpus_from_parameters)).resolve().is_relative_to(
        ROOT / "external" / "ipfs_datasets_py"
    )
    assert legal["status"] in {"error", "unavailable", "refused"}
    assert any(isinstance(legal.get(key), str) and legal[key] for key in ("error", "code"))
    assert not legal.get("results")
    assert inventory["adapter_probes"]["legal_search"]["effect_qualification"] == "unavailable"
    backend = LocalCacheIPFSBackend(cache_dir=str(tmp_path / "ciphertext"))
    access = WorkspaceAccess.authenticated("tenant-ux02", case_id="case-ux02")
    receipt = store_private_artifact(
        _PLAINTEXT,
        access=access,
        tenant_id="tenant-ux02",
        case_id="case-ux02",
        artifact_kind="intake-note",
        revision="rev-ux02",
        key=bytes(range(32)),
        key_id="case-key-ux02",
        backend=backend,
        pin_content=True,
    )
    assert receipt["verified"] is True
    assert receipt["stored_local"] is True and receipt["receipt"]["network_durable"] is False
    ciphertext = backend.cat(receipt["cid"])
    assert _PLAINTEXT not in ciphertext and ciphertext != _PLAINTEXT
    assert _PLAINTEXT not in b"".join(path.read_bytes() for path in (tmp_path / "ciphertext").rglob("*") if path.is_file())
    read_args = dict(access=access, tenant_id="tenant-ux02", case_id="case-ux02",
        artifact_kind="intake-note", revision="rev-ux02", key=bytes(range(32)),
        key_id="case-key-ux02", backend=backend)
    assert retrieve_private_artifact(receipt["cid"], **read_args)["data"] == _PLAINTEXT
    with pytest.raises(PrivateArtifactIntegrityError):
        retrieve_private_artifact(receipt["cid"], **{**read_args, "key": bytes(range(1, 33))})
    with pytest.raises(PrivateArtifactBindingError):
        retrieve_private_artifact(receipt["cid"], **{**read_args,
            "access": WorkspaceAccess.authenticated("foreign-tenant", case_id="case-ux02")})
    assert symbols["store_private_artifact"]["qualification"] == "active"
    assert inventory["adapter_probes"]["private_storage"]["plaintext_left_backend"] is False
    assert inventory["adapter_probes"]["private_storage"]["kit_network_enabled"] is False


def test_current_operation_registration_does_not_substitute_for_qualified_effects() -> None:
    before = operation_handler_call_count()
    registered = register_legal_evidence_operations()
    assert [row["operation"] for row in registered["operations"]] == list(LEGAL_EVIDENCE_OPERATIONS)
    assert type(registered["dispatch_enabled"]) is bool
    for row in registered["operations"]:
        for flag in ("handler_bound", "handler_enabled", "effect_enabled", "writes_enabled"):
            assert type(row[flag]) is bool
        assert not row["effect_enabled"] or row["handler_enabled"]
        assert not row["writes_enabled"] or row["effect_enabled"]
        prerequisites = row["prerequisites"]
        assert {item["id"] for item in prerequisites} >= {
            "persisted_operation_consent", "encrypted_private_artifact_store", "derived_index_boundary",
        }
        for item in prerequisites:
            assert type(item["implemented"]) is bool and type(item["verified"]) is bool
            assert not item["verified"] or item["implemented"]
        if row["handler_enabled"]:
            assert all(item["implemented"] for item in prerequisites)
        # Resolve the actual registered owner, rather than freezing its
        # historical qualification or treating a flag as an observed effect.
        parts = row["owner"].split(".")
        for boundary in range(len(parts)-1, 0, -1):
            try:
                owner = importlib.import_module(".".join(parts[:boundary]))
            except ModuleNotFoundError:
                continue
            for part in parts[boundary:]:
                owner = getattr(owner, part)
            break
        else:
            pytest.fail("Registered operation owner is not importable")
        assert callable(owner) and Path(inspect.getfile(owner)).resolve().is_relative_to(ROOT)
    assert operation_handler_call_count() == before


@pytest.mark.parametrize("operation", LEGAL_EVIDENCE_OPERATIONS)
@pytest.mark.parametrize("missing,expected_status,expected_code", [
    ("key", "unavailable", "key_unavailable"),
    ("private_store", "unavailable", "private_store_unavailable"),
    ("derived_index", "unavailable", "derived_index_unready"),
    ("binding", "refused", "binding_missing"),
    ("host_target", "refused", "target_not_host_owned"),
])
def test_registered_operations_refuse_real_authorization_and_prerequisite_gaps(
    operation, missing, expected_status, expected_code,
) -> None:
    now = datetime.now(timezone.utc)
    context, request, privacy = _authorized_request(operation, now)
    before = operation_handler_call_count()
    calls = []
    if missing == "host_target":
        request["target_ref"] = "foreign.target"
    result = dispatch_registered_hook_operation(
        request, context=None if missing == "binding" else context,
        host_targets=("target.ux02",), owner_id=context.owner_id,
        case_id=context.case_id, session_id=context.session_id,
        session_revision=context.session_revision, graph_revision=context.graph_revision,
        legal_context=_legal_context(), purpose=context.purpose,
        source_bindings=[{"source_id": "src-ux02", "content_hash": "ab" * 32}],
        privacy_context=privacy, now=now,
        key_available=missing != "key", private_store_available=missing != "private_store",
        derived_index_ready=missing != "derived_index", persisted_consent_verified=True,
        effect=lambda _receipt: calls.append("effect"), handler=lambda _request: calls.append("handler"),
    )
    assert result["status"] == expected_status and result["code"] == expected_code
    assert result["effect_dispatched"] is False and result["handler_invoked"] is False
    assert result["storage_invoked"] is False and result["provider_invoked"] is False
    assert result["writes"] == 0 and calls == []
    assert operation_handler_call_count() == before


def test_unknown_operation_cannot_invoke_a_caller_effect() -> None:
    calls = []
    before = operation_handler_call_count()
    unknown = dispatch_registered_hook_operation(
        {"operation": "float_upstream_pin", "role": "extract_facts", "target_ref": "target.ux02", "source_refs": []},
        context=None,
        host_targets=("target.ux02",),
        owner_id="synthetic-ux02-owner",
        case_id="synthetic-ux02-case",
        session_id="session-ux02",
        session_revision=1,
        graph_revision="gr-ux02-1",
        legal_context=_legal_context(),
        purpose="float_upstream_pin",
        source_bindings=[],
        privacy_context=None,
        now=datetime.now(timezone.utc),
        effect=lambda _receipt: calls.append("effect"),
    )
    assert unknown["status"] == "refused"
    assert unknown["code"] == "unsupported_operation"
    assert calls == []
    assert operation_handler_call_count() == before


def test_kit_router_rejects_unsupported_and_unbound_operations() -> None:
    inventory = _inventory()
    _prefer_pinned_checkout("ipfs_kit_py")
    from ipfs_kit_py.core.operation_registry import (
        AuthorizationRequirement,
        CapabilityTier,
        OperationDefinition,
        OperationRegistry,
        UnsupportedOperationError,
    )
    from ipfs_kit_py.core.service_router import HandlerNotBoundError, ServiceRouter

    origin = Path(inspect.getfile(ServiceRouter)).resolve().as_posix()
    assert "/external/ipfs_kit_py/" in origin
    recorded = next(row for row in inventory["callable_symbols"] if row["symbol"] == "ServiceRouter.dispatch")
    assert callable(ServiceRouter.dispatch)

    def definition(operation_id: str, tier: CapabilityTier) -> OperationDefinition:
        return OperationDefinition(
            operation_id=operation_id,
            version=1,
            request_schema=f"{operation_id}.request",
            result_schema=f"{operation_id}.result",
            error_schema=f"{operation_id}.error",
            capability=f"{operation_id}.capability",
            authorization=AuthorizationRequirement.public(),
            handler_route=f"{operation_id}.route",
            support_tier=tier,
        )

    router = ServiceRouter(OperationRegistry((
        definition("storage.object.experimental", CapabilityTier.UNSUPPORTED),
        definition("storage.object.read", CapabilityTier.PRODUCTION),
    )))
    touched: list[str] = []
    with pytest.raises(UnsupportedOperationError):
        router.dispatch("storage.object.experimental", {"body": _PLAINTEXT})
    with pytest.raises(HandlerNotBoundError):
        router.dispatch("storage.object.read", {"body": _PLAINTEXT})
    assert touched == []
    assert recorded["unsupported_operation_qualification"] == "unsupported"
    assert recorded["unbound_operation_qualification"] == "unavailable"


def test_historical_decision_does_not_hide_a_now_visible_pinned_router() -> None:
    inventory = _inventory()
    decision = inventory["compatibility_decision"]
    assert decision["policy"] == "exact_declared_pins"
    assert decision["floating_pins"] is False
    assert decision["submodule_update"] is False
    assert decision["branch_or_tag_pins"] is False
    assert decision["adopted_newer_capabilities"] == []
    deferred = {row["capability"]: row for row in decision["deferred"]}
    assert deferred["KnowledgeGraphExtractor.extract_enhanced_knowledge_graph"]["qualification"] == "unsupported"
    assert deferred["site_packages_ipfs_accelerate_py"]["qualification"] == "unsupported"
    accelerate_router = ROOT / "external" / "ipfs_accelerate_py" / "ipfs_accelerate_py" / "llm_router.py"
    kwargs = pinned_grok47_dispatch_kwargs()
    facade = next(row for row in inventory["callable_symbols"] if row["symbol"] == "pinned_grok47_dispatch_kwargs")
    assert facade["provider"] == kwargs["provider"] == "grok_cli"
    assert facade["model_name"] == kwargs["model_name"] == "grok-4.7"
    assert kwargs["allow_local_fallback"] is False
    assert kwargs["allow_cross_provider_fallback"] is False
    if accelerate_router.is_file():
        _prefer_pinned_checkout("ipfs_accelerate_py")
        router = importlib.import_module("ipfs_accelerate_py.llm_router")
        assert Path(inspect.getfile(router)).resolve() == accelerate_router.resolve()
        assert callable(router.generate_text)
        # Check the actual API accepts the pinned route, without invoking a
        # provider or interpreting module presence as consent/activation.
        inspect.signature(router.generate_text).bind("Synthetic API binding only", **kwargs)
    assert facade["qualification"] == "callable"
    manifest = json.loads((ROOT / inventory["experience_binding"]["baseline_manifest"]).read_text(encoding="utf-8"))
    workspace = next(row for row in manifest["screenshots"] if row["id"] == "02-workspace-desktop")
    assert workspace["state"] == inventory["experience_binding"]["preserved_baseline_state"]
    assert inventory["experience_binding"]["pixels_observed_by_this_inventory"] is False
    assert "No case selected" in inventory["experience_binding"]["preserved_defect"]
