"""CIMP-UX-56: thirteen hook outcomes across the complaint lifecycle.

Each hook runs through ComplaintWorkspaceService.exercise_lifecycle_hook.
Bindings come from the saved source, runtime identity, owner, consent, and
graph revision. A static inventory row is not an effect.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService
from integrations.ipfs_datasets.logic import sha256_utf8
from mediator.hook_runtime import (
    LEGAL_EVIDENCE_OPERATIONS,
    LIFECYCLE_HOOKS,
    UNSUPPORTED_OPTIONAL_HOOKS,
    hook_runtime_identity,
    register_legal_evidence_operations,
)


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
RULE = "An employer shall not retaliate against an employee for opposing an unlawful practice."
OTHER = "An employer shall post a notice describing the retaliation remedy."
NOTE = b"Synthetic margin note that must stay an annotation."
USER = "synthetic-ux56-owner"
SESSION = "session-ux56"
SOURCE_ID = "src-ux56"
KEY = bytes(range(32))


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


def _open(root: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root)
    status = service.private_key_status()
    if status.get("protection") in {None, "", "missing"}:
        service.initialize_private_keys(protection="passphrase", passphrase="synthetic-ux56-passphrase")
    if service.private_key_status().get("unlocked") is not True:
        service.unlock_private_keys(passphrase="synthetic-ux56-passphrase")
    service.ensure_private_case_key(USER, USER)
    return service


def _prepare(tmp_path: Path, *, operation_consent: bool = True):
    service = _open(tmp_path / "workspace")
    service.set_privacy_policy(USER, "local")
    service.publish_case_host_entity(USER, "target.ux56")
    stored = service.store_case_private_source(USER, RULE.encode(), key=KEY, key_id="ux56-key")
    assert stored["verified"] is True
    bound = service.bind_case_mediator_owners(USER, key=KEY, key_id="ux56-key")
    assert bound["index_status"] == "available"
    if operation_consent:
        service.save_mediator_operation_consent(USER, list(LEGAL_EVIDENCE_OPERATIONS))
    service.save_local_public_legal_text(USER, "cite.ux56", RULE)
    bindings = service.bind_lifecycle_case(
        USER, source=RULE.encode(), source_id=SOURCE_ID, session_id=SESSION, session_revision=2,
    )
    assert bindings["runtime_id"] == hook_runtime_identity()
    assert bindings["content_hash"] == hashlib.sha256(RULE.encode()).hexdigest()
    return service, bindings


def _authority():
    return {
        "source_text": RULE,
        "jurisdiction": "OR",
        "authority_id": "ors:659A.030",
        "citation": "ORS 659A.030",
        "authority_version": "2024-edition",
        "source_hash": sha256_utf8(RULE),
        "effective_date": "2024-01-01",
        "as_of_date": "2024-06-01",
    }


def _legal_payload(**overrides):
    body = {
        "narrative": RULE,
        "jurisdiction": "OR",
        "applicable_law_date": "2024-06-01",
        "context_revision": 1,
        "claim_candidates": ["retaliation"],
        "admitted_authorities": [_authority()],
        "model_text": "The court must enter judgment for the plaintiff.",
        "model_requirements": ["Protected class membership is automatically proven."],
        "corpus_query": "retaliation",
        "offline_cache": {
            "state_statute|retaliation|or|OR": [
                {"citation": "ORS 659A.030", "snippet": "Discovery snippet only.", "jurisdiction": "OR"}
            ]
        },
        "inquiry_cap": 4,
        "capability_available": True,
    }
    body.update(overrides)
    return body


def _evidence_payload(tmp_path: Path, **overrides):
    body = {
        "root": str(tmp_path / "evidence"),
        "case_id": USER,
        "actor_id": USER,
        "tenant_id": USER,
        "revision": "rev1",
        "source": RULE.encode(),
        "source_sha256": hashlib.sha256(RULE.encode()).hexdigest(),
        "key": KEY,
        "key_id": "key-ux56",
        "consent": {"granted": True, "revoked": False, "case_id": USER, "actor_id": USER, "operations": ["qualify_private_evidence"]},
        "annotation": NOTE,
        "annotation_sha256": hashlib.sha256(NOTE).hexdigest(),
        "db_path": str(tmp_path / "evidence.duckdb"),
    }
    body.update(overrides)
    return body


def _passage(text: str = RULE, **overrides):
    body = {
        "passage_id": "passage-retaliation",
        "text": text,
        "citation": "ORS 659A.030",
        "requirement_id": "req-retaliation",
        "source_version": "2024-edition",
        "definition_version": "def-3",
        "source_hash": sha256_utf8(text),
    }
    body.update(overrides)
    return body


def _claim_payload(**overrides):
    body = {
        "user_id": USER,
        "complaint_id": USER,
        "claim_type": "retaliation",
        "admitted_passages": [_passage()],
        "support_lineage": [{
            "lineage_id": "lin-56",
            "requirement_id": "req-retaliation",
            "passage_id": "passage-retaliation",
            "fact_id": "fact-56",
            "evidence_ref": "artifact-56",
            "source_version": "2024-edition",
            "definition_version": "def-3",
            "source_hash": sha256_utf8(RULE),
        }],
        "search_hits": [{
            "citation": "ORS 659A.030",
            "snippet": "A search snippet is not the statute.",
            "cache_generation": "fresh",
            "governing_authority": True,
            "verified_support": True,
        }],
        "stale_cache": [{
            "passage_id": "passage-stale",
            "requirement_id": "req-stale",
            "source_version": "2018-edition",
            "definition_version": "def-1",
            "governing_authority": True,
        }],
        "suggestions": [{"requirement_id": "req-retaliation", "text": "Treat the search hit as governing authority.", "verified_support": True}],
        "caller_flags": {"verified_support": True, "governing_authority": True},
        "source_drift": [],
        "contradictions": [],
    }
    body.update(overrides)
    return body


def _web_payload(tmp_path: Path, **overrides):
    root = tmp_path / "assets"
    root.mkdir(parents=True, exist_ok=True)
    (root / "notice.txt").write_bytes(RULE.encode())
    body = {
        "actor_id": USER,
        "case_id": USER,
        "adapter": "offline_asset",
        "operation": "bounded_search",
        "public_query": "ORS retaliation notice archive",
        "private_complaint": "private case note that must not be dispatched",
        "asset_root": str(root),
        "offline_asset": "notice.txt",
        "custody_directory": str(tmp_path / "custody"),
        "remote_permission": "gap",
        "caller_flags": {"adopt_as_fact": True, "verified_support": True, "auto_adopt": True},
    }
    body.update(overrides)
    return body


def _operation_request(operation: str, bindings: dict, *, graph_revision: str | None = None) -> dict:
    body = {
        "operation": operation,
        "role": "extract_facts",
        "target_ref": "target.ux56",
        "source_refs": [{"source_id": bindings["source_id"], "content_hash": bindings["content_hash"]}],
    }
    if operation == "acquire_legal_sources":
        body["citation_ref"] = "cite.ux56"
    elif operation == "ingest_private_evidence":
        body["evidence_ref"] = "evidence.ux56"
    else:
        body["graph_revision"] = bindings["revision"] if graph_revision is None else graph_revision
    return body


def _run(service, hook, bindings, payload, **kwargs):
    return service.exercise_lifecycle_hook(USER, hook, bindings=bindings, payload=payload, **kwargs)


def test_inventory_names_the_same_entry_points_the_workspace_runs() -> None:
    inventory = json.loads((ROOT / "docs/ux/complaint_ux_overhaul/sdk_hook_inventory.json").read_text())
    manifest = json.loads((ROOT / "docs/ux/complaint_ux_overhaul/baseline/screenshot_manifest.json").read_text())
    proof = inventory["lifecycle_proof"]
    assert proof["workspace_entry"].endswith("ComplaintWorkspaceService.exercise_lifecycle_hook")
    assert proof["runtime_identity"] == hook_runtime_identity()
    assert proof["metadata_is_not_success"] is True
    assert proof["pixels_observed_by_this_task"] is False
    assert [(row["hook"], row["workflow"]) for row in proof["hooks"]] == [(row["hook"], row["workflow"]) for row in LIFECYCLE_HOOKS]
    by_hook = {row["hook"]: row for row in inventory["mediator_hooks"]}
    assert set(by_hook) == {row["hook"] for row in LIFECYCLE_HOOKS}
    for row in LIFECYCLE_HOOKS:
        assert by_hook[row["hook"]]["lifecycle_workflow"] == row["workflow"]
        assert by_hook[row["hook"]]["lifecycle_entry"] == "ComplaintWorkspaceService.exercise_lifecycle_hook"
    assert [row["operation"] for row in inventory["registered_operations"]] == list(LEGAL_EVIDENCE_OPERATIONS)
    assert all(row["handler_enabled"] is False for row in inventory["registered_operations"])
    assert proof["unsupported_optional"][0]["hook"] == UNSUPPORTED_OPTIONAL_HOOKS[0]["hook"]
    assert proof["unsupported_optional"][0]["activation"] is False
    workspace = next(item for item in manifest["screenshots"] if item["id"] == "02-workspace-desktop")
    assert workspace["state"] == proof["baseline_defect_preserved"]
    registered = register_legal_evidence_operations()
    assert registered["dispatch_enabled"] is False


def test_each_required_hook_has_a_real_effect_under_saved_bindings(tmp_path: Path) -> None:
    service, bindings = _prepare(tmp_path)
    legal = _legal_payload()
    classification = _run(service, "LegalClassificationHook", bindings, legal)
    statute = _run(service, "StatuteRetrievalHook", bindings, legal)
    judgment = _run(service, "SummaryJudgmentHook", bindings, legal)
    questions = _run(service, "QuestionGenerationHook", bindings, legal)
    assert classification["workflow_invoked"] is True and classification["effect"] is True
    assert classification["jurisdiction"] == "OR" and classification["creates_law"] is False
    assert classification["bindings"]["owner_id"] == USER
    assert classification["bindings"]["revision"] == bindings["revision"]
    assert statute["effect"] is True and statute["citations"] == ["ORS 659A.030"] and statute["discovery_only"] is True
    assert judgment["effect"] is True and judgment["legal_element_count"] == 1 and judgment["model_text_created_law"] is False
    assert questions["effect"] is True and questions["inquiry_count"] >= 1
    assert all(kind != "legal_requirement" for kind in questions["inquiry_record_kinds"])
    assert questions["legal_element_count"] == 1

    evidence = _evidence_payload(tmp_path / "storage")
    storage = _run(service, "EvidenceStorageHook", bindings, evidence)
    state_payload = _evidence_payload(tmp_path / "state")
    state = _run(service, "EvidenceStateHook", bindings, state_payload)
    analysis_payload = _evidence_payload(tmp_path / "analysis")
    analysis = _run(service, "EvidenceAnalysisHook", bindings, analysis_payload)
    assert storage["effect"] is True and storage["plaintext_persisted"] is False and storage["writes"] >= 1
    assert storage["evidence_record_id"]
    assert state["effect"] is True and state["evidence_count"] == 1 and state["state_owner"] == "EvidenceStateHook"
    assert analysis["effect"] is True and analysis["analysis_evidence_ids"] == ["ev-rev1"]
    assert analysis["annotation_converted_to_evidence"] is False
    for path in Path(evidence["root"]).rglob("*"):
        if path.is_file():
            assert RULE.encode() not in path.read_bytes()
            assert NOTE not in path.read_bytes()

    claim = _claim_payload()
    support = _run(service, "ClaimSupportHook", bindings, claim)
    search = _run(service, "LegalAuthoritySearchHook", bindings, claim)
    authority_storage = _run(service, "LegalAuthorityStorageHook", bindings, claim)
    authority_analysis = _run(service, "LegalAuthorityAnalysisHook", bindings, claim)
    assert support["effect"] is True and support["lineage_id"] == "lin-56" and support["record_id"] not in (None, -1)
    assert support["proof"] is False and support["legal_sufficiency"] is False
    assert search["effect"] is True and search["search_hit_governing"] is False and search["search_hit_count"] == 1
    assert authority_storage["effect"] is True and authority_storage["stored_status"] == "stored"
    assert authority_storage["search_hits_stored"] == 0 and authority_storage["stored_record_id"] not in (None, -1)
    assert authority_analysis["effect"] is True and authority_analysis["governing_count"] == 1
    assert authority_analysis["legal_sufficiency"] is False

    web = _web_payload(tmp_path / "web")
    found = _run(service, "WebEvidenceSearchHook", bindings, web)
    adopted_payload = dict(web)
    adopted_payload["caller_flags"] = {}
    adopted_payload["adoption"] = {"intent": "adopt_source_not_fact", "actor_id": USER, "custody_id": found["custody_id"]}
    adopted = _run(service, "WebEvidenceIntegrationHook", bindings, adopted_payload)
    assert found["effect"] is True and found["network_invoked"] is False and found["content_sha256"] == hashlib.sha256(RULE.encode()).hexdigest()
    assert adopted["effect"] is True and adopted["support_status"] == "explicit_support" and adopted["fact_adopted"] is False
    support_files = list(Path(web["custody_directory"]).glob("*.support.json"))
    assert len(support_files) == 1
    support_path = support_files[0]
    stored_support = json.loads(support_path.read_text())
    assert stored_support["fact_adopted"] is False
    assert "private case note" not in support_path.read_text()
    assert all(item["provider_invoked"] is False for item in (
        classification, statute, judgment, questions, storage, state, analysis, support, search, authority_storage, authority_analysis, found, adopted,
    ))


def test_each_hook_has_a_meaningful_negative_outcome(tmp_path: Path) -> None:
    service, bindings = _prepare(tmp_path)
    unknown = _legal_payload(jurisdiction="not-a-jurisdiction", applicable_law_date="", admitted_authorities=[], offline_cache={})
    classification = _run(service, "LegalClassificationHook", bindings, unknown)
    statute = _run(service, "StatuteRetrievalHook", bindings, unknown)
    judgment = _run(service, "SummaryJudgmentHook", bindings, unknown)
    questions = _run(service, "QuestionGenerationHook", bindings, unknown)
    assert classification["receipt_code"] == "unknown_legal_context"
    assert classification["jurisdiction"] == "unknown" and classification["creates_law"] is False
    assert statute["effect"] is False and statute["citations"] == [] and statute["activated"] is False
    assert judgment["effect"] is False and judgment["legal_element_count"] == 0 and judgment["model_text_created_law"] is False
    assert "unknown_legal_context" in questions["inquiry_record_kinds"]
    assert questions["legal_element_count"] == 0

    locked = _run(service, "EvidenceStorageHook", bindings, _evidence_payload(tmp_path / "locked", key=None, key_locked=True))
    assert locked["status"] == "refused" and locked["code"] == "key_locked" and locked["effect"] is False and locked["writes"] == 0
    assert list((tmp_path / "locked" / "evidence").rglob("*")) == []
    unsafe_note = b"Synthetic text <script>alert(1)</script> remains unsafe."
    unsafe = _run(service, "EvidenceStateHook", bindings, _evidence_payload(
        tmp_path / "unsafe", annotation=unsafe_note, annotation_sha256=hashlib.sha256(unsafe_note).hexdigest(),
    ))
    assert unsafe["status"] == "refused" and unsafe["code"] == "unsafe_content" and unsafe["effect"] is False and unsafe["writes"] == 0

    claim = _claim_payload(support_lineage=[])
    missing_lineage = _run(service, "ClaimSupportHook", bindings, claim)
    assert missing_lineage["effect"] is False and missing_lineage["verified_support"] is False and missing_lineage["receipt_code"] == "unverified"
    stale = _run(service, "LegalAuthoritySearchHook", bindings, _claim_payload(search_hits=[]))
    assert stale["effect"] is False and stale["search_hit_governing"] is False and stale["stale_retired"] is True
    drifted = _run(service, "LegalAuthorityStorageHook", bindings, _claim_payload(
        admitted_passages=[_passage(source_hash="0" * 64)], support_lineage=[],
    ))
    assert drifted["effect"] is False and drifted["stored_record_id"] is None
    contradicted = _run(service, "LegalAuthorityAnalysisHook", bindings, _claim_payload(admitted_passages=[
        _passage(), _passage(text=OTHER, passage_id="passage-notice", citation="ORS 659A.030 notice"),
    ]))
    assert contradicted["effect"] is False and contradicted["receipt_code"] == "retired" and contradicted["governing_count"] == 0

    missing_web = _web_payload(tmp_path / "missing-web", offline_asset="missing-notice.txt")
    missing = _run(service, "WebEvidenceSearchHook", bindings, missing_web)
    assert missing["status"] == "unavailable" and missing["code"] == "offline_asset_missing"
    assert missing["effect"] is False and missing["dependency_failure"] is True
    assert not Path(missing_web["custody_directory"]).exists()
    web = _web_payload(tmp_path / "adopt-web")
    found = _run(service, "WebEvidenceSearchHook", bindings, web)
    refused_adoption = dict(web)
    refused_adoption["caller_flags"] = {}
    refused_adoption["adoption"] = {
        "intent": "adopt_source_not_fact", "actor_id": USER, "custody_id": found["custody_id"], "adopt_as_fact": True,
    }
    refused = _run(service, "WebEvidenceIntegrationHook", bindings, refused_adoption)
    assert refused["effect"] is False and refused["fact_adopted"] is False
    assert refused["support_code"] == "automatic_fact_adoption_refused"
    assert list(Path(web["custody_directory"]).glob("*.support.json")) == []


def test_missing_evidence_capability_is_a_dependency_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, bindings = _prepare(tmp_path)
    monkeypatch.setattr(
        "integrations.private_storage.probe_kit_evidence_capability",
        lambda: {"available": False, "code": "missing_capability", "owner": "missing-kit"},
    )
    outcome = _run(service, "EvidenceAnalysisHook", bindings, _evidence_payload(tmp_path / "gap", capability_available=True))
    assert outcome["status"] == "unavailable" and outcome["code"] == "missing_capability"
    assert outcome["dependency_failure"] is True and outcome["effect"] is False and outcome["activated"] is False
    assert outcome["workflow_invoked"] is True
    assert list((tmp_path / "gap" / "evidence").rglob("*")) == []


def test_unsupported_optional_extractor_is_not_activation(tmp_path: Path) -> None:
    service, bindings = _prepare(tmp_path)
    outcome = _run(service, UNSUPPORTED_OPTIONAL_HOOKS[0]["hook"], bindings, _legal_payload())
    assert outcome["status"] == "unavailable" and outcome["code"] == "unsupported_optional"
    assert outcome["activated"] is False and outcome["effect"] is False and outcome["workflow_invoked"] is False
    assert outcome["qualification"] == "unsupported"


def test_registered_operations_write_and_refuse_for_real(tmp_path: Path) -> None:
    service, bindings = _prepare(tmp_path)
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    acquired = _run(service, "acquire_legal_sources", bindings, _operation_request("acquire_legal_sources", bindings), now=now, legal_context=_legal_context())
    ingested = _run(service, "ingest_private_evidence", bindings, _operation_request("ingest_private_evidence", bindings), now=now, legal_context=_legal_context())
    refreshed = _run(service, "refresh_grounding", bindings, _operation_request("refresh_grounding", bindings), now=now, legal_context=_legal_context())
    assert acquired["effect"] is True and acquired["writes"] == 1 and acquired["proof"] is False
    assert ingested["effect"] is True and ingested["storage_invoked"] is True and ingested["writes"] == 1
    assert refreshed["effect"] is True and refreshed["writes"] == 1
    assert acquired["workflow"] == "dispatch_public_mediator_operation"
    index = service.case_derived_index_owner("acquire_legal_sources", USER, USER)
    cached = [row for row in index._derived().public_law_cache.values() if row.get("text") == RULE]
    assert cached and cached[0]["citation"] == "cite.ux56"
    revealed = [entry for entry in index._derived().entries.values() if entry.get("kind") == "evidence"]
    assert revealed and revealed[0]["text"] == "sha256:" + hashlib.sha256(RULE.encode()).hexdigest()
    journal = service.mediator_operation_journal(USER)
    assert [item["operation"] for item in journal] == list(LEGAL_EVIDENCE_OPERATIONS)
    assert all(item["effect_dispatched"] is True and item["proof"] is False for item in journal)

    stale = _run(
        service, "refresh_grounding", bindings,
        _operation_request("refresh_grounding", bindings, graph_revision="gr-stale-token"),
        now=now, legal_context=_legal_context(),
    )
    assert stale["effect"] is False and stale["code"] == "stale_revision" and stale["writes"] == 0 and stale["workflow_invoked"] is True

    bare, bare_bindings = _prepare(tmp_path / "bare", operation_consent=False)
    refused = _run(
        bare, "acquire_legal_sources", bare_bindings,
        _operation_request("acquire_legal_sources", bare_bindings),
        now=now, legal_context=_legal_context(),
    )
    assert refused["code"] == "consent_missing" and refused["effect"] is False and refused["writes"] == 0
    assert bare.mediator_operation_journal(USER)[-1]["effect_dispatched"] is False

    wrong = dict(bindings)
    wrong["owner_id"] = "someone-else"
    blocked = _run(service, "ingest_private_evidence", wrong, _operation_request("ingest_private_evidence", bindings), now=now, legal_context=_legal_context())
    assert blocked["code"] == "wrong_owner" and blocked["workflow_invoked"] is False and blocked["effect"] is False

    revoked = dict(bindings)
    service.revoke_lifecycle_hook_consent(USER)
    consent_block = _run(service, "ClaimSupportHook", revoked, _claim_payload())
    assert consent_block["code"] == "consent_revoked" and consent_block["workflow_invoked"] is False and consent_block["effect"] is False


def test_binding_mismatches_do_not_reach_the_hook(tmp_path: Path) -> None:
    service, bindings = _prepare(tmp_path)
    stale = dict(bindings)
    stale["revision"] = "gr-not-current"
    outcome = _run(service, "SummaryJudgmentHook", stale, _legal_payload())
    assert outcome["code"] == "stale_revision" and outcome["workflow_invoked"] is False and outcome["effect"] is False
    drifted = dict(bindings)
    drifted["runtime_id"] = "caller-runtime"
    runtime = _run(service, "StatuteRetrievalHook", drifted, _legal_payload())
    assert runtime["code"] == "runtime_mismatch" and runtime["workflow_invoked"] is False
    foreign = _legal_payload(narrative=RULE + " extra")
    mismatch = _run(service, "LegalClassificationHook", bindings, foreign)
    assert mismatch["code"] == "source_binding_mismatch" and mismatch["workflow_invoked"] is False and mismatch["effect"] is False
