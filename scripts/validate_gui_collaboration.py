#!/usr/bin/env python3
"""Bounded current-source GUI acceptance groups.

Local synthetic acceptance, historical Native completions, and optional future
live model, corpus, prover, and replica qualification are separate lanes.
A group that was not executed is never passing. Historical completion and an
unexecuted live lane do not satisfy local synthetic acceptance.

Legacy compatibility helpers are foundation probes, never current release
closure. The default CLI below measures the immutable current registry with
canonical Host collection/run seals; legacy probes require --legacy-probes.

The legacy probe runner uses the shared ASGI application through the Task 02 same-origin
pipe bridge, the private-artifact seal, and the synthetic graph provenance
check. It does not install packages, read private campaigns, or call a live
model, corpus, prover, or replica.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from integrations.ipfs_accelerate.supervisor_terminal_acceptance import default_graph_acceptance
from integrations.ipfs_datasets.capabilities import DECLARED_OWNER_PINS
from integrations.private_storage import (
    ENVELOPE_MAGIC,
    PrivateArtifactBinding,
    PrivateArtifactBindingError,
    PrivateArtifactIntegrityError,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)
from tests.gui_native_browser import (
    SAME_ORIGIN,
    BrowserCapabilityError,
    BrowserHttpRequest,
    SameOriginAsgiBridge,
    build_qualification_app,
    qualify_native_browser,
)


SOURCE_BASELINE = "2c1439a7029eb9035338133210d8b43319add8a4"
SCHEMA = "complaint-gui-acceptance-groups/v1"
TASK_ID = "CIMP-GUI-59"
PLAINTEXT = b"synthetic-cimp-gui-59-note"
KEY = bytes(range(32))
KEY_ID = "synthetic-cimp-gui-59-key"
LANE_LOCAL = "local_synthetic_gui"
LANE_HISTORICAL = "historical_native"
LANE_OPTIONAL = "optional_future_live"
OPTIONAL_GROUPS = ("live_model", "live_corpus", "live_prover", "live_replica")
LOCAL_GROUPS = ("runtime_identity", "dom_asgi", "encryption", "provenance", "negative_access")
HISTORICAL_GROUP = "historical_native_completions"
DECLARED_GROUPS = LOCAL_GROUPS + (HISTORICAL_GROUP,) + OPTIONAL_GROUPS
_IDENTITY_FILES = (
    "applications/server.py",
    "integrations/private_storage.py",
    "tests/gui_native_browser.py",
    "scripts/validate_gui_collaboration.py",
)
_HISTORICAL_PROGRAMS = frozenset({
    "completed44",
    "completed58",
    "old44",
    "old58",
    "mediator-44",
    "intake-58",
})


class AcceptanceSeparationError(ValueError):
    """A lane was counted as a pass without its own executed evidence."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def current_runtime_identity() -> dict[str, Any]:
    """Bind this run to the source baseline, declared SDK pins, and this interpreter."""

    root = _repo_root()
    files: dict[str, str] = {}
    for relative in _IDENTITY_FILES:
        path = root / relative
        files[relative] = _sha256(path) if path.is_file() else ""
    return {
        "source_baseline": SOURCE_BASELINE,
        "source_file_sha256": files,
        "sdk_pins": {name: DECLARED_OWNER_PINS[name] for name in ("ipfs_accelerate_py", "ipfs_datasets_py", "ipfs_kit_py")},
        "python": platform.python_version(),
        "executable": sys.executable,
        "implementation": platform.python_implementation(),
        "packages_installed": False,
        "live_egress": False,
    }


def _case(case_id: str, *, executed: bool, passed: bool, detail: Mapping[str, Any]) -> dict[str, Any]:
    if passed and not executed:
        raise AcceptanceSeparationError(f"{case_id} cannot pass without execution")
    return {
        "case_id": case_id,
        "executed": executed,
        "passed": passed,
        "counts_as_passing": executed and passed,
        "detail": dict(detail),
    }


def _group(name: str, lane: str, cases: Sequence[Mapping[str, Any]], *, mandatory: bool) -> dict[str, Any]:
    if not cases:
        raise AcceptanceSeparationError(f"{name} has no cases")
    executed = [row for row in cases if row["executed"]]
    if mandatory and not executed:
        raise AcceptanceSeparationError(f"mandatory group {name} did not execute")
    passed = bool(executed) and all(row["passed"] for row in executed) and len(executed) == len(cases)
    return {
        "group": name,
        "lane": lane,
        "mandatory": mandatory,
        "cases": list(cases),
        "executed": len(executed) == len(cases) and bool(executed),
        "passed": passed,
        "counts_as_passing": passed,
        "counts_as_local_synthetic_acceptance": lane == LANE_LOCAL and passed,
    }


def _binding(principal: str = "synthetic-owner") -> PrivateArtifactBinding:
    return PrivateArtifactBinding(
        tenant_id="synthetic-tenant-59",
        case_id="synthetic-case-59",
        artifact_kind="gui-acceptance-note",
        revision="1",
        principal_id=principal,
    )


class _Access:
    def __init__(self, principal_id: str, case_id: str, trust: str = "authenticated") -> None:
        self.principal_id = principal_id
        self.case_id = case_id
        self.trust = trust


def _identity_cases(identity: Mapping[str, Any]) -> list[dict[str, Any]]:
    pins = identity["sdk_pins"]
    files = identity["source_file_sha256"]
    pin_ok = all(isinstance(pins.get(name), str) and len(pins[name]) == 40 for name in DECLARED_OWNER_PINS)
    files_ok = all(isinstance(files.get(name), str) and len(files[name]) == 64 for name in _IDENTITY_FILES)
    python_ok = str(identity["python"]).startswith("3.12.")
    return [
        _case("source_baseline_bound", executed=True, passed=identity["source_baseline"] == SOURCE_BASELINE and files_ok, detail={"baseline": identity["source_baseline"]}),
        _case("sdk_pins_bound", executed=True, passed=pin_ok, detail={"owners": sorted(pins)}),
        _case("python_runtime_recorded", executed=True, passed=python_ok and bool(identity["executable"]), detail={"python": identity["python"], "executable": identity["executable"]}),
    ]


def _encryption_cases() -> list[dict[str, Any]]:
    binding = _binding()
    envelope = seal_private_artifact(PLAINTEXT, binding=binding, key=KEY, key_id=KEY_ID)
    opened = open_private_artifact(envelope, binding=binding, key=KEY, expected_key_id=KEY_ID)
    hidden = PLAINTEXT not in envelope and envelope.startswith(ENVELOPE_MAGIC)
    wrong = _binding("synthetic-stranger")
    denied = False
    try:
        open_private_artifact(envelope, binding=wrong, key=KEY, expected_key_id=KEY_ID)
    except PrivateArtifactIntegrityError:
        denied = True
    return [
        _case("seal_open_roundtrip", executed=True, passed=opened == PLAINTEXT, detail={"bytes": len(envelope)}),
        _case("ciphertext_hides_plaintext", executed=True, passed=hidden, detail={"magic": ENVELOPE_MAGIC.decode("ascii")}),
        _case("wrong_binding_denied", executed=True, passed=denied, detail={"principal": wrong.principal_id}),
    ]


def _provenance_cases() -> list[dict[str, Any]]:
    present = default_graph_acceptance({
        "nodes": [{
            "id": "synthetic-event-59",
            "provenance": {"source_kind": "user_statement", "source_id": "msg-synthetic-59"},
        }],
    })
    missing = default_graph_acceptance({"nodes": [{"id": "synthetic-event-59"}]})
    return [
        _case("synthetic_node_with_provenance_passes", executed=True, passed=present["status"] == "passed" and present["executed"] is True, detail={"reason": present["reason"]}),
        _case("missing_provenance_fails", executed=True, passed=missing["status"] == "failed" and missing["executed"] is True, detail={"reason": missing["reason"]}),
    ]


def _negative_access_cases(state_dir: Path) -> list[dict[str, Any]]:
    application, _fixture = build_qualification_app(state_dir)
    bridge = SameOriginAsgiBridge(application)
    download = bridge.handle(BrowserHttpRequest("GET", f"{SAME_ORIGIN}/__cimp_gui_02__/download", []))
    external = bridge.handle(BrowserHttpRequest("GET", "https://example.invalid/health", []))
    health = bridge.handle(BrowserHttpRequest("GET", f"{SAME_ORIGIN}/health", [("accept", "application/json")]))
    websocket = bridge.handle(BrowserHttpRequest("GET", f"{SAME_ORIGIN}/socket", [("upgrade", "websocket")]))
    stranger_denied = False
    try:
        assert_access_matches_binding(_Access("synthetic-stranger", "synthetic-case-59"), _binding())
    except PrivateArtifactBindingError:
        stranger_denied = True
    asgi_ok = bridge.asgi_calls >= 2 and health.status == 200 and health.action == "fulfill"
    return [
        _case("anonymous_download_denied", executed=True, passed=download.status == 401 and download.action == "fulfill", detail={"status": download.status}),
        _case("external_origin_not_fulfilled", executed=True, passed=external.action == "abort" and external.reason == "external-origin" and asgi_ok, detail={"asgi_calls": bridge.asgi_calls, "health": health.status}),
        _case("stranger_principal_binding_denied", executed=True, passed=stranger_denied and websocket.action == "abort", detail={"websocket": websocket.reason}),
    ]


def _dom_cases(state_dir: Path) -> list[dict[str, Any]]:
    try:
        report = qualify_native_browser(state_dir / "browser-profiles")
    except BrowserCapabilityError as exc:
        detail = {"error": str(exc), "capability": "missing"}
        return [
            _case("chromium_dom_pipe", executed=True, passed=False, detail=detail),
            _case("same_origin_asgi_health", executed=True, passed=False, detail=detail),
            _case("external_origin_aborted", executed=True, passed=False, detail=detail),
            _case("unsupported_transports_not_qualified", executed=True, passed=False, detail=detail),
        ]
    transports = report.qualified_transports
    unsupported = all(transports.get(name) is False for name in ("websocket", "sse", "streaming"))
    return [
        _case("chromium_dom_pipe", executed=True, passed=report.pipe_transport is True and bool(report.chromium.sha256), detail={"pipe_transport": report.pipe_transport, "chromium_sha256": report.chromium.sha256}),
        _case("same_origin_asgi_health", executed=True, passed=report.health_status == 200 and "/health" in report.same_origin_paths and report.persisted_note == "synthetic-note-02", detail={"health": report.health_status, "note": report.persisted_note}),
        _case("external_origin_aborted", executed=True, passed=bool(report.aborted_external) and report.cookie_replayed_by_bridge is False, detail={"aborted": len(report.aborted_external)}),
        _case("unsupported_transports_not_qualified", executed=True, passed=unsupported, detail={"qualified_transports": dict(transports)}),
    ]


def historical_completion_counts_as_local(record: Mapping[str, Any]) -> bool:
    """Historical Native completions stay on their own lane.

    A completed old 44 or old 58 record is recognized and still does not
    count as local synthetic acceptance. Other records are not this lane.
    """

    program = str(record.get("program") or record.get("kind") or "")
    historical = program in _HISTORICAL_PROGRAMS or record.get("historical_native") is True or record.get("lane") == LANE_HISTORICAL
    if not historical:
        raise AcceptanceSeparationError("record is not a historical native completion")
    return False


def _historical_cases() -> list[dict[str, Any]]:
    old44 = {"program": "completed44", "status": "completed", "settled_merge_queue": True, "historical_native": True}
    old58 = {"program": "completed58", "status": "completed", "canonical_callback": True, "historical_native": True}
    return [
        _case("old44_completion_is_not_local_acceptance", executed=True, passed=historical_completion_counts_as_local(old44) is False, detail={"program": "completed44"}),
        _case("old58_completion_is_not_local_acceptance", executed=True, passed=historical_completion_counts_as_local(old58) is False and old58["status"] == "completed", detail={"program": "completed58"}),
    ]


def optional_live_case(group: str, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Record one future live qualification. Absent evidence stays unexecuted."""

    case_id = f"{group}_qualification"
    if evidence is None:
        return _case(case_id, executed=False, passed=False, detail={"status": "unexecuted", "reason": "not_run"})
    # A descriptor is not a live-provider/corpus/kernel/replica receipt.
    # Keep compatibility negatives without accepting arbitrary positive flags.
    if evidence.get("passed") is True:
        raise AcceptanceSeparationError("optional live qualification requires an issued producer")
    return _case(case_id, executed=False, passed=False,
        detail={"status":"unexecuted","reason":"unverified_descriptor"})


def run_bounded_acceptance(state_dir: Path, *, include_browser: bool = True, optional_evidence: Mapping[str, Mapping[str, Any] | None] | None = None) -> dict[str, Any]:
    """Run every mandatory local and historical case and record optional live groups."""

    state_dir.mkdir(parents=True, exist_ok=True)
    identity = current_runtime_identity()
    if include_browser:
        dom = _group("dom_asgi", LANE_LOCAL, _dom_cases(state_dir), mandatory=True)
    else:
        dom = _group("dom_asgi", LANE_LOCAL, [_case("chromium_dom_pipe", executed=False, passed=False, detail={"status": "unexecuted"})], mandatory=False)
    groups = [
        _group("runtime_identity", LANE_LOCAL, _identity_cases(identity), mandatory=True),
        dom,
        _group("encryption", LANE_LOCAL, _encryption_cases(), mandatory=True),
        _group("provenance", LANE_LOCAL, _provenance_cases(), mandatory=True),
        _group("negative_access", LANE_LOCAL, _negative_access_cases(state_dir / "asgi"), mandatory=True),
        _group(HISTORICAL_GROUP, LANE_HISTORICAL, _historical_cases(), mandatory=True),
    ]
    supplied = optional_evidence or {}
    for name in OPTIONAL_GROUPS:
        groups.append(_group(name, LANE_OPTIONAL, [optional_live_case(name, supplied.get(name))], mandatory=False))
    return _rollup(identity, groups)


def _rollup(identity: Mapping[str, Any], groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_name = {str(row["group"]): row for row in groups}
    missing = [name for name in DECLARED_GROUPS if name not in by_name]
    if missing:
        raise AcceptanceSeparationError("undeclared or missing groups: " + ",".join(missing))
    local = [by_name[name] for name in LOCAL_GROUPS]
    historical = by_name[HISTORICAL_GROUP]
    optional = [by_name[name] for name in OPTIONAL_GROUPS]
    if any(row["passed"] and not row["executed"] for row in groups):
        raise AcceptanceSeparationError("unexecuted group counted as passing")
    if historical["counts_as_local_synthetic_acceptance"]:
        raise AcceptanceSeparationError("historical native completion counted as local acceptance")
    if any(row["counts_as_local_synthetic_acceptance"] for row in optional):
        raise AcceptanceSeparationError("optional live qualification counted as local acceptance")
    local_passed = all(row["mandatory"] and row["executed"] and row["passed"] for row in local)
    historical_separated = bool(historical["executed"] and historical["passed"] and not historical["counts_as_local_synthetic_acceptance"])
    optional_executed = all(row["executed"] for row in optional)
    optional_passed = optional_executed and all(row["passed"] for row in optional)
    unexecuted = [str(row["group"]) for row in groups if not row["executed"]]
    return {
        "schema": SCHEMA,
        "qualification_scope": "legacy_foundation_probes_only",
        "current_acceptance_passed": False,
        "release_acceptance": False,
        "task_id": TASK_ID,
        "identity": dict(identity),
        "groups": [dict(row) for row in groups],
        "local_synthetic_acceptance_passed": local_passed,
        "historical_native_separated": historical_separated,
        "historical_counts_as_local_acceptance": False,
        "optional_future_live_executed": optional_executed,
        "optional_future_live_passed": optional_passed,
        "unexecuted_groups": unexecuted,
        "unexecuted_groups_count_as_passing": False,
        "all_declared_groups_passing": local_passed and historical_separated and optional_passed,
        "bounded_acceptance_ok": local_passed and historical_separated and not any(row["passed"] for row in optional if not row["executed"]),
        "campaign_completion": False,
        "known_limitations": [
            "websocket_sse_and_streaming_are_not_qualified",
            "historical_native_completions_are_a_separate_lane",
            "unexecuted_live_model_corpus_prover_and_replica_groups_are_not_passing",
            "this_report_does_not_complete_the_campaign",
        ],
    }


def reject_unexecuted_pass(group: Mapping[str, Any]) -> None:
    """Public guard used by tests. An unexecuted group is not a pass."""

    if group.get("passed") is True and group.get("executed") is not True:
        raise AcceptanceSeparationError("unexecuted group counted as passing")
    for case in group.get("cases") or []:
        if isinstance(case, Mapping) and case.get("passed") is True and case.get("executed") is not True:
            raise AcceptanceSeparationError("unexecuted case counted as passing")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded current-source GUI acceptance groups")
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--skip-browser", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run_bounded_acceptance(args.state_dir, include_browser=not args.skip_browser)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0 if report["bounded_acceptance_ok"] else 1


_CURRENT_GROUPS = {'root20_resume': {'selectors': ['tests/test_cimp_gui_20.py'],
                   'minimum_cases': 17,
                   'timeout_seconds': 300,
                   'exact_cases': 17},
 'root55_real_security': {'selectors': ['tests/test_cimp_gui_55.py',
                                        'tests/test_gui43_44_private_journey.py::test_real_recipient_key_opens_thread_attachment_without_unlocked_owner',
                                        'tests/test_gui43_44_private_journey.py::test_cold_recipient_and_services_preserve_durable_thread_attachment_binding'],
                          'minimum_cases': 10,
                          'timeout_seconds': 300,
                          'exact_cases': 10},
 'root57_unavailable': {'selectors': ['tests/test_cimp_gui_57.py'],
                        'minimum_cases': 11,
                        'timeout_seconds': 300,
                        'exact_cases': 11},
 'root58_monitoring': {'selectors': ['tests/test_cimp_gui_58.py'],
                       'minimum_cases': 18,
                       'timeout_seconds': 300,
                       'exact_cases': 18},
 'root56_owner_lawyer_journey': {'selectors': ['tests/test_cimp_gui_56.py'],
                                 'minimum_cases': 2,
                                 'timeout_seconds': 600,
                                 'exact_cases': 2},
 'authenticated_dom_and_finite_stop': {'selectors': ['tests/test_cimp_gui_15.py::test_typed_owner_cookie_case_scope_uses_actor_and_real_canonical_encrypted_service',
                                                     'tests/test_gui16_current_privacy.py::test_real_owner_adaptive_dom_is_closed_at_actual_private_boundary',
                                                     'tests/test_gui16_current_privacy.py::test_real_sdk_completion_clear_cannot_repaint_adaptive_question',
                                                     'tests/test_gui1923_private_browser_audit.py::test_actual_finite_buttons_keep_unresolved_nonproof_outcomes_visible',
                                                     'tests/test_gui1923_private_browser_audit.py::test_actual_graph_response_cannot_repaint_after_real_private_boundary'],
                                       'minimum_cases': 5,
                                       'timeout_seconds': 300},
 'factual_graph_and_origin': {'selectors': ['tests/test_gui21_factual_graph_http.py::test_factual_graph_reads_real_encrypted_workspace_for_distinct_actor_and_tenant',
                                            'tests/test_gui21_factual_graph_http.py::test_late_live_authority_key_or_source_change_refuses_graph_publication',
                                            'tests/test_gui21_factual_graph_http.py::test_policy_membership_cannot_borrow_owner_master_for_graph_read',
                                            'tests/test_gui21_factual_provenance.py::test_real_validated_envelope_ignores_cached_claim_and_keeps_assertion_identity',
                                            'tests/test_gui21_factual_provenance.py::test_raw_fact_and_cached_boolean_do_not_mint_verified_user_authority'],
                              'minimum_cases': 5,
                              'timeout_seconds': 300},
 'legal_context_sources_and_dependency_graph': {'selectors': ['tests/test_gui24_private_context.py::test_context_update_is_encrypted_cas_and_preserves_actual_workflow_facts',
                                                              'tests/test_gui24_private_context.py::test_real_crypto_late_refusal_terminally_aborts_and_recovery_never_publishes',
                                                              'tests/test_gui25_26_private_owner_http.py::test_exact_review_admits_real_source_without_inventing_applicability_and_cold_reads_it',
                                                              'tests/test_gui26_source_admission_scope.py::test_review_persists_exact_source_custody_without_promoting_orphan_database_graph_rows',
                                                              'tests/test_gui28_private_dependency_refresh.py::test_actual_reviewed_source_refreshes_real_private_graph_and_cold_replays_current_scope',
                                                              'tests/test_gui27_typed_law_projection.py::test_actual_current_source_requirements_are_projected_from_typed_dependency_nodes',
                                                              'tests/test_gui27_typed_law_projection.py::test_unresolved_current_applicability_cannot_reuse_previously_admitted_nodes'],
                                                'minimum_cases': 7,
                                                'timeout_seconds': 300},
 'canonical_ir_definition_and_nonproof': {'selectors': ['tests/test_gui29_private_legal_analysis.py::test_actual_reviewed_source_compiles_and_cold_reopens_without_promoting_law',
                                                        'tests/test_gui29_private_legal_analysis.py::test_http_cannot_replace_current_case_source_context_or_premises',
                                                        'tests/test_gui30_private_owner.py::test_current_definition_owner_replay_persists_under_actual_reviewed_source_and_cold_key',
                                                        'tests/test_gui31_private_proof_trace.py::test_real_current_encrypted_ir_projects_as_unexecuted_without_write_or_new_compilation',
                                                        'tests/test_gui31_private_proof_trace.py::test_cold_compiler_registry_loss_does_not_remove_source_obligations_or_create_proof',
                                                        'tests/test_gui31_private_proof_trace.py::test_client_proof_post_requires_unavailable_issued_producer_and_never_writes',
                                                        'tests/test_gui3031_private_panels.py::test_real_proof_rows_clear_when_actual_encrypted_key_is_locked'],
                                          'minimum_cases': 7,
                                          'timeout_seconds': 600},
 'recipient_review_and_owner_acceptance': {'selectors': ['tests/test_gui32_review_browser.py::test_real_owner_shares_in_gui_then_locked_owner_recipient_submits_and_logs_out',
                                                         'tests/test_gui32_review_browser.py::test_real_delivered_review_response_cannot_repaint_after_actual_clear',
                                                         'tests/test_gui32_review_boundaries.py::test_actual_shared_source_drift_requires_owner_reshare_and_old_approval_stays_stale',
                                                         'tests/test_gui32_review_boundaries.py::test_real_review_head_publication_rechecks_late_recipient_boundary',
                                                         'tests/test_gui47_private_acceptance.py::test_public_review_acceptance_supersedes_private_fact_and_replays_without_another_commit',
                                                         'tests/test_gui47_private_acceptance.py::test_real_review_cas_change_during_correction_prevents_canonical_publication',
                                                         'tests/test_gui47_response_delivery.py::test_legitimate_committed_owner_acceptance_refuses_late_private_response_and_replays'],
                                           'minimum_cases': 7,
                                           'timeout_seconds': 300},
 'key_epochs_and_wal_recovery': {'selectors': ['tests/test_gui46_inflight_epoch_boundary.py::test_actual_inflight_owner_answer_cannot_publish_old_dek_after_revocation',
                                               'tests/test_cimp_gui_12.py::test_fresh_dek_protects_future_owner_and_survivor_writes_but_preserves_history',
                                               'tests/test_cimp_gui_12.py::test_interrupted_cross_store_rotation_reopens_and_resumes_same_dek',
                                               'tests/test_private_workspace_recovery.py::test_commit_publishes_one_revision_without_plaintext_journal',
                                               'tests/test_private_workspace_recovery.py::test_ack_lost_after_effect_does_not_duplicate_on_second_recovery',
                                               'tests/test_private_workspace_recovery.py::test_recovery_authenticates_before_any_replay_or_compensation'],
                                 'minimum_cases': 6,
                                 'timeout_seconds': 300},
 'messaging_admin_export_and_privacy': {'selectors': ['tests/test_gui43_44_private_journey.py::test_revocation_after_real_encryption_prevents_new_publication',
                                                      'tests/test_gui44_private_inbox.py::test_actual_cookie_logout_then_refresh_clears_private_rows_and_counters',
                                                      'tests/test_gui44_private_inbox.py::test_real_successful_old_page_cannot_repaint_after_case_input_changes',
                                                      'tests/test_cimp_gui_52.py::test_actual_public_export_reopen_refuses_after_real_cookie_revoked_during_crypto',
                                                      'tests/test_cimp_gui_52.py::test_actual_reopened_metadata_export_cannot_ignore_membership_removed_during_crypto'],
                                        'minimum_cases': 5,
                                        'timeout_seconds': 300}}

# Strict current acceptance. Legacy helpers above are foundation probes only.
from types import MappingProxyType as _CurrentMappingProxy
_CURRENT_GROUPS = _CurrentMappingProxy({name:_CurrentMappingProxy(dict(spec,selectors=tuple(spec['selectors'])))
    for name,spec in _CURRENT_GROUPS.items()})
CURRENT_SCHEMA = 'complaint-gui-current-host-groups@1'
GUI_SPEC_RELATIVE = 'docs/task_boards/complaint_gui_collaboration_spec.json'


class CurrentAcceptanceError(ValueError):
    pass


def required_current_groups():
    """Return a copy; external JSON and legacy reports cannot alter this registry."""
    return {name:dict(spec,selectors=list(spec['selectors'])) for name,spec in _CURRENT_GROUPS.items()}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest_current(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _git_bytes_current(root, *args):
    """Read local Git only, with a ten-second and two-MiB combined-output cap."""
    import os, selectors, subprocess, time
    env = {'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8',
           'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_SYSTEM':'/dev/null','GIT_CONFIG_NOSYSTEM':'1',
           'GIT_OPTIONAL_LOCKS':'0','GIT_TERMINAL_PROMPT':'0'}
    process = subprocess.Popen(['/usr/bin/git','--no-replace-objects','--no-optional-locks','--no-pager',
        '-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null',*args],cwd=root,env=env,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    output = bytearray(); total = 0; deadline = time.monotonic()+10
    try:
        with selectors.DefaultSelector() as pending:
            pending.register(process.stdout,selectors.EVENT_READ,True)
            pending.register(process.stderr,selectors.EVENT_READ,False)
            while pending.get_map():
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise CurrentAcceptanceError('git_deadline_exceeded')
                for key,_ in pending.select(min(remaining,0.1)):
                    block = os.read(key.fileobj.fileno(),min(65536,2*1024*1024-total+1))
                    if not block:
                        pending.unregister(key.fileobj)
                        continue
                    total += len(block)
                    if total > 2*1024*1024:
                        raise CurrentAcceptanceError('git_output_bound')
                    if key.data:
                        output.extend(block)
        if process.wait(timeout=max(0.001,deadline-time.monotonic())) != 0:
            raise CurrentAcceptanceError('git_source_unavailable')
        return bytes(output)
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=2)
        process.stdout.close(); process.stderr.close()


def _git_current(root, *args):
    return _git_bytes_current(root,*args).decode('utf-8',errors='strict').strip()


def _source_paths(root):
    prefixes = ('applications/', 'integrations/', 'mediator/', 'complaint_phases/', 'templates/',
                'static/', 'tests/', 'scripts/')
    suffixes = ('.py', '.js', '.mjs', '.html', '.css', '.json', '.toml', '.ini')
    paths = _git_current(root, 'ls-files', '-z').split('\0')
    selected = {p for p in paths if p and p.startswith(prefixes) and p.endswith(suffixes)}
    selected.update((GUI_SPEC_RELATIVE, 'pytest.ini', 'pyproject.toml'))
    selected = sorted(p for p in selected if (root / p).is_file())
    if not selected or len(selected) > 10000:
        raise CurrentAcceptanceError('source_scope_unavailable')
    return selected


def current_source_identity():
    """Observe Git/source, actual imported pinned SDKs and actual executable bytes."""
    import importlib
    import os
    from integrations.ipfs_accelerate.improvement_runner import _source_freeze
    root = _repo_root()
    if sys.version_info[:2] != (3,12):
        raise CurrentAcceptanceError('runtime_python_version')
    if Path(_git_current(root, 'rev-parse', '--show-toplevel')).resolve() != root:
        raise CurrentAcceptanceError('source_root_mismatch')
    paths = _source_paths(root)
    freeze = _source_freeze(root, paths)
    source = {name:item['sha256'] for name,item in freeze['files'].items()}
    if any(not isinstance(value, str) or len(value) != 64 for value in source.values()):
        raise CurrentAcceptanceError('source_file_unavailable')
    sdks = {}
    for name in ('ipfs_accelerate_py', 'ipfs_datasets_py', 'ipfs_kit_py'):
        module = importlib.import_module(name)
        origin = Path(module.__file__).resolve(strict=True)
        sdk = Path(_git_current(origin.parent, 'rev-parse', '--show-toplevel')).resolve()
        expected = _git_current(root, 'rev-parse', 'HEAD:external/' + name)
        head = _git_current(sdk, 'rev-parse', 'HEAD')
        if freeze['dependencies'].get('external/'+name,{}).get('gitlink') != expected:
            raise CurrentAcceptanceError('declared_sdk_gitlink_changed:'+name)
        if head != expected or _git_current(sdk, 'status', '--porcelain', '--untracked-files=normal', '--ignore-submodules=all'):
            raise CurrentAcceptanceError('sdk_source_mismatch:' + name)
        relative = origin.relative_to(sdk).as_posix()
        blob = _git_bytes_current(sdk,'show',head+':'+relative)
        if hashlib.sha256(blob).hexdigest() != _sha256(origin):
            raise CurrentAcceptanceError('sdk_import_mismatch:' + name)
        sdks[name] = {'root': str(sdk), 'head': head, 'declared_gitlink': expected,
                      'import_path': str(origin), 'import_sha256': _sha256(origin)}
    node, chromium = __import__('tests.gui_native_browser', fromlist=['pin_executables']).pin_executables()
    python = Path(sys.executable).resolve(strict=True)
    return {'root': str(root), 'head': _git_current(root, 'rev-parse', 'HEAD'),
        'working_tree_status': _git_current(root, 'status', '--porcelain', '--untracked-files=normal', '--ignore-submodules=all'),
        'source_files': source, 'source_freeze': freeze, 'source_tree_sha256': freeze['digest'], 'sdks': sdks,
        'runtime': {'python': str(python), 'python_sha256': _sha256(python), 'version': platform.python_version(),
            'node': node.path, 'node_sha256': node.sha256, 'chromium': chromium.path,
            'chromium_sha256': chromium.sha256}, 'completion_authority': False}


class _CurrentOutput:
    """Hold the private parent and named output inode through report delivery."""
    def __init__(self, path):
        import os, stat
        self.path = Path(path)
        self.parent_fd = self.child_fd = None
        if (not self.path.is_absolute() or self.path.parent.resolve(strict=True) != self.path.parent
                or self.path.name in ('', '.', '..')):
            raise CurrentAcceptanceError('private_output_path')
        root = _repo_root()
        common = Path(_git_current(root, 'rev-parse', '--path-format=absolute', '--git-common-dir'))
        if any(self.path == forbidden or self.path.is_relative_to(forbidden) or forbidden.is_relative_to(self.path)
               for forbidden in (root, common)):
            raise CurrentAcceptanceError('private_output_overlaps_source')
        reserved = {'.git', 'campaign', 'campaigns', 'worker-worktrees', 'claims', 'watchdog', 'control_plane', 'control-plane'}
        for parent in (self.path.parent, *self.path.parent.parents):
            if (parent.name in reserved or (parent/'launcher.json').exists()
                    or (parent/'.git').exists() and not root.is_relative_to(parent)):
                raise CurrentAcceptanceError('private_output_overlaps_control_state')
        try:
            self.parent_fd = os.open(self.path.parent, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NONBLOCK)
            parent = os.fstat(self.parent_fd)
            if parent.st_uid != os.getuid() or parent.st_mode & 0o077:
                raise CurrentAcceptanceError('private_output_parent')
            os.mkdir(self.path.name, 0o700, dir_fd=self.parent_fd)
            self.child_fd = os.open(self.path.name, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NONBLOCK,
                                    dir_fd=self.parent_fd)
            self.reprove()
        except BaseException:
            self.close()
            raise

    def reprove(self):
        import os, stat
        try:
            if self.path.parent.resolve(strict=True) != self.path.parent:
                raise CurrentAcceptanceError('private_output_custody')
            for held, named in ((os.fstat(self.parent_fd), os.stat(self.path.parent, follow_symlinks=False)),
                    (os.fstat(self.child_fd), os.stat(self.path.name, dir_fd=self.parent_fd, follow_symlinks=False))):
                if (not stat.S_ISDIR(held.st_mode) or held.st_uid != os.getuid() or held.st_mode & 0o077
                        or (held.st_dev,held.st_ino) != (named.st_dev,named.st_ino)):
                    raise CurrentAcceptanceError('private_output_custody')
        except OSError as exc:
            raise CurrentAcceptanceError('private_output_custody') from exc

    def close(self):
        import os
        for name in ('child_fd','parent_fd'):
            fd = getattr(self,name)
            if fd is not None:
                setattr(self,name,None)
                os.close(fd)

    def __enter__(self):
        self.reprove()
        return self

    def __exit__(self, *_):
        self.close()


def _private_current_directory(path):
    return _CurrentOutput(path)


def _write_current_report(directory, body):
    import os
    if type(directory) is not _CurrentOutput:
        raise CurrentAcceptanceError('private_output_custody')
    directory.reprove()
    data = (_canonical(body)+'\n').encode()
    fd = os.open('report.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,
                 dir_fd=directory.child_fd)
    with os.fdopen(fd,'wb') as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())
    directory.reprove()
    os.fsync(directory.child_fd)
    return directory.path/'report.json'

import weakref as _current_weakref
_CURRENT_RUNS = _current_weakref.WeakSet()
_CURRENT_RUN_TOKEN = object()


class _CurrentGroupRun:
    __slots__ = ('_json', '_identity', '_observation', '_metadata', '__weakref__')

    def __init__(self, token, body, identity, observation, metadata):
        if token is not _CURRENT_RUN_TOKEN:
            raise CurrentAcceptanceError('host_measurement_required')
        object.__setattr__(self, '_json', _canonical(body))
        object.__setattr__(self, '_identity', _canonical(identity))
        object.__setattr__(self, '_observation', observation)
        object.__setattr__(self, '_metadata', metadata)

    def __setattr__(self, name, value):
        raise CurrentAcceptanceError('immutable_host_run')

    def to_dict(self):
        return json.loads(self._json)


def _current_environment(root, directory, identity):
    import os
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import build_validation_environment, validation_environment_for_runner
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
    for name in ('home', 'tmp', 'cache', 'config', 'data', 'state', 'runtime'):
        (directory / name).mkdir(mode=0o700)
    source = {
        'HOME': str(directory/'home'), 'TMPDIR': str(directory/'tmp'), 'XDG_CACHE_HOME': str(directory/'cache'),
        'XDG_CONFIG_HOME': str(directory/'config'), 'XDG_DATA_HOME': str(directory/'data'),
        'XDG_STATE_HOME': str(directory/'state'), 'XDG_RUNTIME_DIR': str(directory/'runtime'),
        'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
        'COMMON_CRAWL_AUTO_CLONE_SOURCE': '0', 'IPFS_DATASETS_PY_MINIMAL_IMPORTS': '1',
        'IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD': '0', 'PYTHONDONTWRITEBYTECODE': '1',
        'TODO_DAEMON_LLM_ALLOW_LOCAL_FALLBACK': '0', 'TODO_DAEMON_LLM_ALLOW_CROSS_PROVIDER_FALLBACK': '0',
        'IPFS_ACCELERATE_AGENT_VALIDATION_PLAYWRIGHT_BROWSERS_PATH': os.environ.get(
            'IPFS_ACCELERATE_AGENT_VALIDATION_PLAYWRIGHT_BROWSERS_PATH', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', ''))}
    roots = [str(root)] + [identity['sdks'][name]['root'] for name in ('ipfs_accelerate_py', 'ipfs_datasets_py', 'ipfs_kit_py')]
    import pytest as actual_pytest
    roots.append(str(Path(actual_pytest.__file__).resolve().parents[1]))
    source['PYTHONPATH'] = os.pathsep.join(roots)
    environment = build_validation_environment(source)
    # Trusted Host bindings after the Native allowlist; no ambient secrets.
    # These private paths and denial flags are passed to the canonical runner.
    for key in ('HOME','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_RUNTIME_DIR',
                'TODO_DAEMON_LLM_ALLOW_LOCAL_FALLBACK','TODO_DAEMON_LLM_ALLOW_CROSS_PROVIDER_FALLBACK'):
        environment[key]=source[key]
    (directory/'orchestrator').mkdir(mode=0o700)
    environment['IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR']=str(directory/'orchestrator')
    environment['PYTHONPATH'] = source['PYTHONPATH']
    import shutil
    if shutil.which('grok', path=environment['PATH']) is not None:
        raise CurrentAcceptanceError('provider_executable_exposed')
    return validation_environment_for_runner(environment, PortalImplementationDaemon._validation_command_runner)


def _validate_current_observation(observation, metadata, spec):
    from integrations.ipfs_accelerate.improvement_plan import _host_evidence_reason
    reason = _host_evidence_reason(observation, metadata)
    if reason:
        raise CurrentAcceptanceError(reason)
    measured = observation['host_measurement']
    nodes = measured['required_nodeids']
    if not nodes or len(nodes) != len(set(nodes)) or len(nodes) < spec['minimum_cases']:
        raise CurrentAcceptanceError('empty_or_missing_required_cases')
    if spec.get('exact_cases') is not None and len(nodes) != spec['exact_cases']:
        raise CurrentAcceptanceError('mandatory_case_count_changed')
    for selector in spec['selectors']:
        if not any(node == selector or node.startswith(selector + '[') or
                   '::' not in selector and node.startswith(selector + '::') for node in nodes):
            raise CurrentAcceptanceError('mandatory_selector_missing')
    if [case['nodeid'] for case in measured['cases']] != nodes or any(case['outcome'] != 'passed' for case in measured['cases']):
        raise CurrentAcceptanceError('required_case_not_passed')
    return measured


def run_current_group(group_id, output_directory):
    """Execute ONE declared Host group; never publish Native task/budget state."""
    import shlex
    import time
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
    from integrations.ipfs_accelerate.improvement_runner import measure_behavioral_command
    if group_id not in _CURRENT_GROUPS:
        raise CurrentAcceptanceError('unknown_required_group')
    spec = _CURRENT_GROUPS[group_id]
    if not spec['selectors'] or len(spec['selectors']) != len(set(spec['selectors'])):
        raise CurrentAcceptanceError('empty_or_duplicate_selectors')
    start = time.monotonic()
    with _private_current_directory(output_directory) as custody:
        directory = custody.path
        before = current_source_identity()
        root = Path(before['root'])
        command = 'python -m pytest -q --run-llm --run-network --run-heavy ' + ' '.join(shlex.quote(value) for value in spec['selectors'])
        metadata = {'id': 'HOST-GUI-CURRENT:' + group_id, 'targets': sorted(before['source_files']),
                    'validation_commands': [command], 'depends_on': []}
        environment = _current_environment(root, directory, before)
        custody.reprove()
        actual_command = 'PYTHONPATH=' + shlex.quote(environment['PYTHONPATH']) + ' ' + command + ' --basetemp=' + shlex.quote(str(directory/'owned-cases'))
        if time.monotonic()-start >= spec['timeout_seconds']:
            raise CurrentAcceptanceError('group_deadline_exceeded')
        observation = measure_behavioral_command(root, directory/'measurements', metadata, actual_command,
            runner=PortalImplementationDaemon._validation_command_runner, environment=environment,
            timeout_seconds=max(0.001, spec['timeout_seconds'] - (time.monotonic()-start)), declared_command=command,
            context={'campaign_spec_relative': GUI_SPEC_RELATIVE})
        custody.reprove()
        reason = ''
        try:
            measured = _validate_current_observation(observation, metadata, spec)
        except CurrentAcceptanceError as exc:
            reason = str(exc)
            measured = observation.get('host_measurement', {})
        after = current_source_identity()
        if before != after:
            reason = 'stale_current_source_or_runtime'
        if time.monotonic() - start > spec['timeout_seconds']:
            reason = 'group_deadline_exceeded'
        record = getattr(observation, 'measurement_record', None)
        body = {'schema': CURRENT_SCHEMA, 'scope': 'one_bounded_current_host_group', 'group': group_id,
            'selectors': list(spec['selectors']), 'command': command, 'host_metadata': metadata,
            'executed': bool(measured.get('required_nodeids')), 'passed': not reason, 'reason': reason,
            'required_nodeids': measured.get('required_nodeids', []), 'cases': measured.get('cases', []),
            'source_before': before, 'source_after': after, 'source_unchanged': before == after,
            'measurement_record': record, 'elapsed_seconds': time.monotonic()-start,
            'missing_groups': [name for name in _CURRENT_GROUPS if name != group_id],
            'current_acceptance_passed': False, 'historical_native_completions_verified': False,
            'optional_live_qualified': False, 'provider_invoked': False, 'completion_authority': False}
        path = _write_current_report(custody, body)
        body['report_path'] = str(path)
        issued = _CurrentGroupRun(_CURRENT_RUN_TOKEN,body,before,observation,metadata)
        _CURRENT_RUNS.add(issued)
        return issued

def aggregate_current_groups(runs):
    """Aggregate ONLY live Host-issued results in this process, never saved JSON."""
    from integrations.ipfs_accelerate.improvement_plan import _host_evidence_reason
    runs = tuple(runs)
    if any(type(result) is not _CurrentGroupRun or result not in _CURRENT_RUNS for result in runs):
        raise CurrentAcceptanceError('host_measurement_required')
    current = current_source_identity()
    seen = {}
    for result in runs:
        if type(result) is not _CurrentGroupRun or result not in _CURRENT_RUNS:
            raise CurrentAcceptanceError('host_measurement_required')
        body = result.to_dict()
        if body['group'] in seen:
            raise CurrentAcceptanceError('duplicate_group')
        if result._identity != _canonical(current) or body['source_before'] != body['source_after']:
            raise CurrentAcceptanceError('stale_current_source_or_runtime')
        if _host_evidence_reason(result._observation, result._metadata):
            raise CurrentAcceptanceError('stale_or_refused_host_evidence')
        spec=_CURRENT_GROUPS.get(body['group'])
        if spec is None:
            raise CurrentAcceptanceError('group_contract_mismatch')
        import shlex
        command='python -m pytest -q --run-llm --run-network --run-heavy '+' '.join(shlex.quote(v) for v in spec['selectors'])
        expected={'id':'HOST-GUI-CURRENT:'+body['group'],'targets':sorted(current['source_files']),
                  'validation_commands':[command],'depends_on':[]}
        if (result._metadata!=expected or body['host_metadata']!=expected or body['selectors']!=list(spec['selectors'])
                or body['command']!=command or body['measurement_record']!=result._observation.measurement_record):
            raise CurrentAcceptanceError('group_contract_mismatch')
        measured=_validate_current_observation(result._observation,expected,spec)
        if body['required_nodeids']!=measured['required_nodeids'] or body['cases']!=measured['cases']:
            raise CurrentAcceptanceError('group_case_identity_mismatch')
        seen[body['group']] = body
    missing = [name for name in _CURRENT_GROUPS if name not in seen]
    passed = not missing and all(body['passed'] for body in seen.values())
    return {'schema': CURRENT_SCHEMA, 'scope': 'current_local_synthetic_acceptance',
        'groups': list(seen.values()), 'missing_groups': missing,
        'current_acceptance_passed': passed, 'executed_groups': len(seen),
        'unique_nodeids': sorted({node for body in seen.values() for node in body['required_nodeids']}),
        'historical_native_completions_verified': False, 'optional_live_qualified': False,
        'completion_authority': False}


def current_main(argv=None):
    """Strict default CLI. Each group uses its own bounded collect/run children.

    The all-group mode is an operator action outside Native59's900-second
    validation. Its focused test executes one group, never this entire matrix.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if '--legacy-probes' in args:
        args.remove('--legacy-probes')
        return main(args)
    parser = argparse.ArgumentParser(description='Fresh current-source Host acceptance, with no Native completion authority')
    parser.add_argument('--output-root', required=True, type=Path)
    parser.add_argument('--group', choices=tuple(_CURRENT_GROUPS))
    options = parser.parse_args(args)
    with _private_current_directory(options.output_root) as root:
        selected = [options.group] if options.group else list(_CURRENT_GROUPS)
        runs = [run_current_group(name, root.path/name) for name in selected]
        summary = aggregate_current_groups(runs)
        _write_current_report(root, summary)
        print(json.dumps({'report': str(root.path/'report.json'), 'current_acceptance_passed': summary['current_acceptance_passed'],
                          'missing_groups': summary['missing_groups']}, sort_keys=True))
        return 0 if summary['current_acceptance_passed'] else 1

if __name__ == "__main__":
    raise SystemExit(current_main())
