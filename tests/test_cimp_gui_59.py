"""Bounded current-source GUI acceptance groups.

Local synthetic acceptance runs nonempty cases for identity, DOM, ASGI,
encryption, provenance, and negative access. Historical Native completions
and optional live model, corpus, prover, and replica qualification stay on
separate lanes. An unexecuted group is not a pass.

Known limits: WebSocket, SSE, and streaming stay unqualified. This module
does not execute live model, corpus, prover, or replica qualification and
does not complete the campaign.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from integrations.private_storage import ENVELOPE_MAGIC


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_ROOT = Path(__file__).resolve().parents[1]
_SOURCE = _ROOT / "scripts" / "validate_gui_collaboration.py"
_SPEC = importlib.util.spec_from_file_location("validate_gui_collaboration", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
acceptance = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(acceptance)


def _group(report, name):
    found = [row for row in report["groups"] if row["group"] == name]
    assert len(found) == 1
    return found[0]


def test_declared_groups_are_nonempty_and_lanes_stay_separate(tmp_path: Path) -> None:
    report = acceptance.run_bounded_acceptance(tmp_path / "lanes", include_browser=False)
    assert report["schema"] == acceptance.SCHEMA
    assert report["task_id"] == "CIMP-GUI-59"
    assert report["identity"]["source_baseline"] == acceptance.SOURCE_BASELINE
    assert set(report["identity"]["sdk_pins"]) == {"ipfs_accelerate_py", "ipfs_datasets_py", "ipfs_kit_py"}
    names = [row["group"] for row in report["groups"]]
    assert names == list(acceptance.DECLARED_GROUPS)
    for row in report["groups"]:
        assert row["cases"]
        acceptance.reject_unexecuted_pass(row)
    assert _group(report, "encryption")["lane"] == acceptance.LANE_LOCAL
    assert _group(report, "historical_native_completions")["lane"] == acceptance.LANE_HISTORICAL
    assert _group(report, "live_model")["lane"] == acceptance.LANE_OPTIONAL
    assert report["historical_counts_as_local_acceptance"] is False
    assert report["unexecuted_groups_count_as_passing"] is False
    assert "dom_asgi" in report["unexecuted_groups"]
    assert report["local_synthetic_acceptance_passed"] is False
    assert report["bounded_acceptance_ok"] is False
    assert report["campaign_completion"] is False


def test_unexecuted_optional_and_historical_completion_do_not_pass_as_local() -> None:
    for name in acceptance.OPTIONAL_GROUPS:
        case = acceptance.optional_live_case(name, None)
        assert case["executed"] is False
        assert case["passed"] is False
        assert case["counts_as_passing"] is False
    with pytest.raises(acceptance.AcceptanceSeparationError):
        acceptance.optional_live_case("live_prover", {"passed": True, "executed": False})
    old44 = {"program": "completed44", "status": "completed", "settled_merge_queue": True, "historical_native": True}
    old58 = {"program": "completed58", "status": "completed", "historical_native": True}
    assert acceptance.historical_completion_counts_as_local(old44) is False
    assert acceptance.historical_completion_counts_as_local(old58) is False
    with pytest.raises(acceptance.AcceptanceSeparationError):
        acceptance.historical_completion_counts_as_local({"program": "local_synthetic_gui", "status": "completed"})
    with pytest.raises(acceptance.AcceptanceSeparationError):
        acceptance.reject_unexecuted_pass({"group": "live_corpus", "executed": False, "passed": True, "cases": []})


def test_encryption_provenance_and_negative_access_execute(tmp_path: Path) -> None:
    report = acceptance.run_bounded_acceptance(tmp_path / "handlers", include_browser=False)
    encryption = _group(report, "encryption")
    provenance = _group(report, "provenance")
    negative = _group(report, "negative_access")
    identity = _group(report, "runtime_identity")
    for group in (encryption, provenance, negative, identity):
        assert group["executed"] is True
        assert group["passed"] is True
        assert all(case["executed"] and case["passed"] for case in group["cases"])
    assert encryption["cases"][1]["detail"]["magic"] == ENVELOPE_MAGIC.decode("ascii")
    assert provenance["cases"][1]["detail"]["reason"] == "graph_provenance_missing"
    assert negative["cases"][0]["detail"]["status"] == 401
    assert {row["group"] for row in report["groups"] if row["lane"] == acceptance.LANE_OPTIONAL} == set(acceptance.OPTIONAL_GROUPS)
    assert report["optional_future_live_passed"] is False
    assert report["all_declared_groups_passing"] is False
    assert report["historical_native_separated"] is True


def test_current_source_acceptance_runs_dom_asgi_and_keeps_optional_unexecuted(tmp_path: Path) -> None:
    report = acceptance.run_bounded_acceptance(tmp_path / "acceptance")
    dom = _group(report, "dom_asgi")
    assert dom["executed"] is True
    assert dom["passed"] is True, dom["cases"][0]["detail"]
    assert dom["counts_as_local_synthetic_acceptance"] is True
    case_ids = [case["case_id"] for case in dom["cases"]]
    assert case_ids == [
        "chromium_dom_pipe",
        "same_origin_asgi_health",
        "external_origin_aborted",
        "unsupported_transports_not_qualified",
    ]
    assert report["identity"]["python"].startswith("3.12.")
    assert all(len(digest) == 64 for digest in report["identity"]["source_file_sha256"].values())
    assert report["local_synthetic_acceptance_passed"] is True
    assert report["historical_native_separated"] is True
    assert report["optional_future_live_executed"] is False
    assert report["optional_future_live_passed"] is False
    assert set(report["unexecuted_groups"]) == set(acceptance.OPTIONAL_GROUPS)
    assert report["all_declared_groups_passing"] is False
    assert report["bounded_acceptance_ok"] is True
    assert "websocket_sse_and_streaming_are_not_qualified" in report["known_limitations"]
    forged = dict(report)
    forged["groups"] = [dict(row) for row in report["groups"]]
    forged["groups"][-1] = dict(forged["groups"][-1])
    forged["groups"][-1]["executed"] = False
    forged["groups"][-1]["passed"] = True
    with pytest.raises(acceptance.AcceptanceSeparationError):
        acceptance._rollup(report["identity"], forged["groups"])


def test_cli_report_matches_public_runner(tmp_path: Path) -> None:
    state = tmp_path / "cli-state"
    report_path = tmp_path / "report.json"
    code = acceptance.main(["--state-dir", str(state), "--report", str(report_path), "--skip-browser"])
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == 1
    assert written["bounded_acceptance_ok"] is False
    assert written["optional_future_live_passed"] is False
    assert _group(written, "negative_access")["passed"] is True
    full = tmp_path / "cli-full"
    full_report = tmp_path / "full.json"
    full_code = acceptance.main(["--state-dir", str(full), "--report", str(full_report)])
    body = json.loads(full_report.read_text(encoding="utf-8"))
    assert full_code == 0
    assert body["bounded_acceptance_ok"] is True
    assert body["local_synthetic_acceptance_passed"] is True
    assert body["optional_future_live_passed"] is False


def test_current_registry_is_mandatory_and_legacy_json_is_never_qualification():
    groups=acceptance.required_current_groups()
    assert len(groups)==12 and sum(len(v['selectors']) for v in groups.values())==49
    assert groups['root20_resume']['exact_cases']==17
    assert groups['root55_real_security']['exact_cases']==10
    assert groups['root57_unavailable']['exact_cases']==11
    assert groups['root58_monitoring']['exact_cases']==18
    assert groups['root56_owner_lawyer_journey']['exact_cases']==2
    assert all(v['selectors'] and 0<v['timeout_seconds']<=900 for v in groups.values())
    with pytest.raises(TypeError):
        acceptance._CURRENT_GROUPS['root20_resume']['selectors']=()
    with pytest.raises(acceptance.CurrentAcceptanceError,match='host_measurement_required'):
        acceptance.aggregate_current_groups([{'schema':acceptance.CURRENT_SCHEMA,'passed':True,'executed':True}])
    with pytest.raises(acceptance.CurrentAcceptanceError,match='unknown_required_group'):
        acceptance.run_current_group('unknown_group',Path('/never-created-for-unknown-group'))


def test_current_host_group_measures_real_owner_dom_and_refuses_counterfeit_partial_and_stale(tmp_path):
    # One real registered Host group, not the entire matrix in Native59's900s.
    # This executes actual56 owner-lawyer DOM/encryption and negative behavior.
    run=acceptance.run_current_group('root56_owner_lawyer_journey',tmp_path/'actual-host-group')
    body=run.to_dict()
    assert body['passed'] is True,body['reason']
    assert len(body['required_nodeids'])==2 and all(row['outcome']=='passed' for row in body['cases'])
    assert body['source_before']==body['source_after'] and body['source_unchanged'] is True
    assert body['host_metadata']['id']=='HOST-GUI-CURRENT:root56_owner_lawyer_journey'
    assert body['current_acceptance_passed'] is False and len(body['missing_groups'])==11
    assert body['measurement_record'] and Path(body['measurement_record']['path']).is_file()
    partial=acceptance.aggregate_current_groups([run])
    assert partial['current_acceptance_passed'] is False and len(partial['missing_groups'])==11
    assert acceptance.aggregate_current_groups([])['current_acceptance_passed'] is False
    with pytest.raises(acceptance.CurrentAcceptanceError,match='host_measurement_required'):
        acceptance.aggregate_current_groups([json.loads(Path(body['report_path']).read_text())])
    with pytest.raises(acceptance.CurrentAcceptanceError,match='duplicate_group'):
        acceptance.aggregate_current_groups([run,run])
    # A genuine observation cannot be relabeled as another registry group.
    relabeled=dict(body,group='root20_resume')
    wrapped=acceptance._CurrentGroupRun(acceptance._CURRENT_RUN_TOKEN,relabeled,body['source_before'],run._observation,run._metadata)
    with pytest.raises(acceptance.CurrentAcceptanceError,match='host_measurement_required'):
        acceptance.aggregate_current_groups([wrapped])
    acceptance._CURRENT_RUNS.add(wrapped)
    try:
        with pytest.raises(acceptance.CurrentAcceptanceError,match='group_contract_mismatch'):
            acceptance.aggregate_current_groups([wrapped])
    finally:
        acceptance._CURRENT_RUNS.discard(wrapped)
    # An observed real Host record's material is re-proved, never just its JSON
    # passed/admitted flags. Mutating that actual file invalidates the live run.
    record=Path(body['measurement_record']['path'])
    original=record.read_bytes()
    try:
        record.write_bytes(original+b' ')
        with pytest.raises(acceptance.CurrentAcceptanceError,match='stale_or_refused_host_evidence'):
            acceptance.aggregate_current_groups([run])
    finally:
        record.write_bytes(original)
    assert acceptance.aggregate_current_groups([run])['current_acceptance_passed'] is False


def test_current_output_refuses_source_control_state_aliases_and_parent_replacement(tmp_path):
    import os
    root=acceptance._repo_root()
    with pytest.raises(acceptance.CurrentAcceptanceError,match='overlaps_source'):
        acceptance._private_current_directory(root/'never-created-current-report')
    assert not (root/'never-created-current-report').exists()
    state=tmp_path/'campaign';state.mkdir(mode=0o700)
    with pytest.raises(acceptance.CurrentAcceptanceError,match='overlaps_control_state'):
        acceptance._private_current_directory(state/'never-created')
    assert not (state/'never-created').exists()
    parent=tmp_path/'private-parent';parent.mkdir(mode=0o700)
    alias=tmp_path/'alias';alias.symlink_to(parent,target_is_directory=True)
    with pytest.raises(acceptance.CurrentAcceptanceError,match='private_output_path'):
        acceptance._private_current_directory(alias/'never-created')
    assert not (parent/'never-created').exists()
    with acceptance._private_current_directory(parent/'owned') as held:
        receipt=acceptance._write_current_report(held,{'passed':False,'completion_authority':False})
        assert receipt.stat().st_mode & 0o777 == 0o600
    with acceptance._private_current_directory(parent/'moving') as held:
        moved=tmp_path/'original-parent';parent.rename(moved)
        parent.mkdir(mode=0o700);(parent/'moving').mkdir(mode=0o700)
        with pytest.raises(acceptance.CurrentAcceptanceError,match='private_output_custody'):
            acceptance._write_current_report(held,{'passed':True})
        assert not (parent/'moving'/'report.json').exists()
        assert not (moved/'moving'/'report.json').exists()
    with pytest.raises(acceptance.AcceptanceSeparationError):
        acceptance.optional_live_case('live_model',{'passed':True,'executed':True,'capability_checked':True,'observed':True})
