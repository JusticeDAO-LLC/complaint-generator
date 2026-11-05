"""Handoff checks for the screenshot-led UX campaign.

The review and operator guide have to agree with the measured manifest,
findings, SDK inventory, and the public supervisor ceilings. A historical
60-task completion or the PNG files alone cannot close this program.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "docs/ux/complaint_ux_overhaul/before_after_review.md"
GUIDE = ROOT / "docs/task_boards/complaint_gui_ux_overhaul_operator_guide.md"
MANIFEST = ROOT / "docs/ux/complaint_ux_overhaul/baseline/screenshot_manifest.json"
FINDINGS = ROOT / "docs/ux/complaint_ux_overhaul/screenshot_driven_findings.json"
INVENTORY = ROOT / "docs/ux/complaint_ux_overhaul/sdk_hook_inventory.json"
RUNNER = ROOT / "integrations/ipfs_accelerate/improvement_runner.py"
WATCHDOG = ROOT / "integrations/ipfs_accelerate/campaign_watchdog.py"
SUPERVISOR = ROOT / "scripts/run_complaint_improvement_supervisor.py"

_COMMAND_RE = re.compile(
    r"run_complaint_improvement_supervisor\.py\"\s+([A-Za-z0-9_-]+)"
)
def _historical_overclaim(text: str) -> bool:
    """True when a sentence treats the old program as closure, ignoring denials."""
    for sentence in re.split(r"[.\n]", text):
        lowered = sentence.lower()
        if " not " in f" {lowered} ":
            continue
        mentions_old = any(token in lowered for token in ("gui60", "cimp-gui-60", "132-case", "60-task"))
        if mentions_old and "complete" in lowered:
            return True
    return False


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json(path: Path) -> dict:
    return json.loads(_load(path))


def _int_assignments(path: Path) -> dict[str, int]:
    tree = ast.parse(_load(path))
    found: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant) and type(node.value.value) is int:
            found[target.id] = node.value.value
    return found


def _dict_ints(path: Path, name: str) -> dict[str, int]:
    tree = ast.parse(_load(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        values: dict[str, int] = {}
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and isinstance(value, ast.Constant) and type(value.value) is int:
                values[key.value] = value.value
        return values
    raise AssertionError(f"{name} not found in {path}")


def _string_dict(path: Path, name: str) -> dict[str, str]:
    tree = ast.parse(_load(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        values: dict[str, str] = {}
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(key, ast.Constant) and isinstance(value, ast.Constant) and isinstance(key.value, str) and isinstance(value.value, str):
                values[key.value] = value.value
        return values
    raise AssertionError(f"{name} not found in {path}")


def _env_default(path: Path, key: str) -> str:
    tree = ast.parse(_load(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for item_key, item_value in zip(node.keys, node.values):
            if isinstance(item_key, ast.Constant) and item_key.value == key and isinstance(item_value, ast.Constant):
                return str(item_value.value)
    raise AssertionError(f"{key} default not found")


def public_supervisor_commands(source: str) -> set[str]:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.For) or not isinstance(node.iter, ast.Tuple):
            continue
        values = []
        for elt in node.iter.elts:
            if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
                values = []
                break
            values.append(elt.value)
        if "prepare" in values and "recover" in values and "watchdog" in values:
            return set(values)
    raise AssertionError("public supervisor commands were not found")


def measured_screenshots() -> list[dict]:
    manifest = _json(MANIFEST)
    measured = []
    for shot in manifest["screenshots"]:
        file_path = MANIFEST.parent / shot["path"]
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        measured.append({
            "id": shot["id"],
            "path": shot["path"],
            "route": shot["route"],
            "state": shot["state"],
            "sha256": digest,
            "manifest_sha256": shot["sha256"],
            "bytes": file_path.stat().st_size,
            "viewport": shot["viewport"],
        })
    return measured


def campaign_ceilings() -> dict[str, int]:
    assigned = _int_assignments(RUNNER)
    preserved = _dict_ints(WATCHDOG, "_PRESERVED_BUDGETS")
    profile = _string_dict(SUPERVISOR, "PROFILE_FLAGS")
    turns = int(_env_default(RUNNER, "IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS"))
    ceilings = {
        "startup_seconds": assigned["STARTUP_SECONDS"],
        "stall_seconds": assigned["STALL_SECONDS"],
        "implementation_timeout_seconds": assigned["TIMEOUT_SECONDS"],
        "max_turns": turns,
        "max_task_attempts": int(profile["--max-task-attempts"]),
        "max_recoveries_per_incident": preserved["max_recoveries_per_incident"],
        "watchdog_action_deadline_ms": preserved["watchdog_action_deadline_ms"],
    }
    if preserved["startup_seconds"] != ceilings["startup_seconds"]:
        raise AssertionError("startup ceiling drifted between runner and watchdog")
    if preserved["stall_seconds"] != ceilings["stall_seconds"]:
        raise AssertionError("stall ceiling drifted between runner and watchdog")
    if preserved["implementation_timeout_seconds"] != ceilings["implementation_timeout_seconds"]:
        raise AssertionError("timeout ceiling drifted between runner and watchdog")
    if int(profile["--implementation-timeout"]) != ceilings["implementation_timeout_seconds"]:
        raise AssertionError("supervisor timeout flag drifted")
    if int(profile["--implementation-log-stall-seconds"]) != ceilings["stall_seconds"]:
        raise AssertionError("supervisor stall flag drifted")
    return ceilings


def assess_handoff(review: str, guide: str, measured: dict) -> dict:
    """Decide whether the two documents are a usable handoff.

    Usable means the documents cite the measured bytes and refuse the claims
    this campaign has not earned. Usable does not mean the program is complete.
    """
    reasons: list[str] = []
    combined = review + "\n" + guide
    for shot in measured["screenshots"]:
        if shot["sha256"] != shot["manifest_sha256"] or shot["bytes"] != shot["manifest_bytes"]:
            reasons.append(f"file_hash_mismatch:{shot['id']}")
        if shot["id"] not in review or shot["sha256"] not in review or shot["state"] not in review:
            reasons.append(f"screenshot_unbound:{shot['id']}")
    for finding in measured["findings"]:
        if finding["id"] not in review or finding["observed"] not in review:
            reasons.append(f"finding_unbound:{finding['id']}")
    for limit in measured["observed_limits"]:
        if limit not in review:
            reasons.append("capture_limit_missing")
    for pin in measured["declared_pins"]:
        if pin not in review or pin not in guide:
            reasons.append(f"pin_unrecorded:{pin}")
    if measured["application_base_commit"] not in review or measured["application_base_commit"] not in guide:
        reasons.append("baseline_commit_unrecorded")
    for digest in (measured["node_sha256"], measured["chromium_sha256"]):
        if digest not in review or digest not in guide:
            reasons.append("runtime_hash_unrecorded")
    ceilings = measured["ceilings"]
    for label, value in ceilings.items():
        if str(value) not in guide:
            reasons.append(f"ceiling_unrecorded:{label}")
    commands = set(_COMMAND_RE.findall(guide))
    required = {"prepare", "doctor", "start", "status", "stop", "recover", "watchdog"}
    if not required <= commands:
        reasons.append("recovery_command_missing")
    if commands - measured["public_commands"]:
        reasons.append("undocumented_public_command")
    if "_run" in commands:
        reasons.append("internal_command_exposed")
    if "--once" not in guide or "--install-user-timer" not in guide:
        reasons.append("watchdog_mode_missing")
    if measured["provider_invoked"] is not False or "provider_invoked" not in review:
        reasons.append("live_model_overclaim")
    if "false" not in review.lower() and "`provider_invoked` is false" not in review:
        reasons.append("live_model_not_denied")
    corpus = measured["corpus"]
    if corpus["symbol"] not in review or corpus["effect_qualification"] != "unavailable":
        reasons.append("corpus_effect_misstated")
    if "unavailable" not in review or "prover result" not in review:
        reasons.append("prover_not_limited")
    if measured["kit_network_enabled"] is not False or "kit_network_enabled" not in review:
        reasons.append("remote_durability_overclaim")
    if "not verified remote durability" not in review or "not verified remote durability" not in guide:
        reasons.append("remote_durability_unrecorded")
    if "lawyer role alone grants no case content" not in review or "lawyer role alone grants no case content" not in guide:
        reasons.append("role_boundary_missing")
    lowered_review = review.lower()
    if "not new evidence" not in lowered_review or "not an intake answer" not in lowered_review:
        reasons.append("adoption_boundary_missing")
    if "factual graph" not in review.lower() or "legal dependency graph" not in review.lower():
        reasons.append("graph_provenance_missing")
    if "No case selected" not in review:
        reasons.append("stale_header_story_missing")
    if _historical_overclaim(combined):
        reasons.append("historical_program_overclaim")
    if "do not complete" not in review or "does not complete" not in guide:
        reasons.append("non_completion_unrecorded")
    if "pixels" not in review:
        reasons.append("pixel_limit_unrecorded")
    unique = sorted(set(reasons))
    return {
        "status": "usable" if not unique else "refused",
        "reasons": unique,
        "closes_program": False,
        "screenshot_files_complete_program": False,
        "old60_completes_program": False,
    }


def _measured_bundle() -> dict:
    manifest = _json(MANIFEST)
    findings = _json(FINDINGS)
    inventory = _json(INVENTORY)
    screenshots = measured_screenshots()
    for shot, declared in zip(screenshots, manifest["screenshots"]):
        shot["manifest_bytes"] = declared["bytes"]
    corpus = next(
        item for item in inventory["callable_symbols"]
        if item["symbol"] == "search_us_code_corpus_from_parameters"
    )
    return {
        "screenshots": screenshots,
        "findings": findings["findings"],
        "observed_limits": manifest["observed_limits"],
        "application_base_commit": manifest["application_base_commit"],
        "declared_pins": [owner["declared_pin"] for owner in inventory["owners"]],
        "node_sha256": manifest["runtime"]["node"]["sha256"],
        "chromium_sha256": manifest["runtime"]["chromium"]["sha256"],
        "provider_invoked": manifest["provider_invoked"],
        "kit_network_enabled": inventory["private_storage_probe"]["kit_network_enabled"]
        if "private_storage_probe" in inventory else _kit_network(inventory),
        "corpus": corpus,
        "ceilings": campaign_ceilings(),
        "public_commands": public_supervisor_commands(_load(RUNNER)),
    }


def _kit_network(inventory: dict) -> bool:
    for value in _walk(inventory):
        if isinstance(value, dict) and "kit_network_enabled" in value:
            return value["kit_network_enabled"]
    raise AssertionError("kit_network_enabled was not measured")


def _walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_measured_png_bytes_match_the_manifest_and_the_review() -> None:
    review = _load(REVIEW)
    bundle = _measured_bundle()
    assert len(bundle["screenshots"]) == 13
    for shot in bundle["screenshots"]:
        assert shot["sha256"] == shot["manifest_sha256"]
        assert shot["bytes"] == shot["manifest_bytes"]
        assert shot["sha256"] in review
        assert shot["id"] in review
        assert shot["state"] in review
        assert f"{shot['viewport']['width']}x{shot['viewport']['height']}" in review
    outcome = assess_handoff(review, _load(GUIDE), bundle)
    assert outcome["status"] == "usable"
    assert outcome["reasons"] == []
    assert outcome["closes_program"] is False


def test_findings_and_capture_limits_keep_the_source_bound_story() -> None:
    review = _load(REVIEW)
    findings = _json(FINDINGS)
    manifest = _json(MANIFEST)
    assert findings["application_base_commit"] == manifest["application_base_commit"]
    assert len(findings["findings"]) == 8
    for finding in findings["findings"]:
        assert finding["observed"] in review
        for screen in finding["screens"]:
            assert screen in review
    for limit in manifest["observed_limits"]:
        assert limit in review
    assert "authenticated_backend_with_existing_stale_workspace_header" in review
    assert "actual_assigned_lawyer_scope_content_not_shared" in review
    assert "actual_draft_not_generated_readiness_visible" in review


def test_public_recovery_commands_match_the_runner_parser() -> None:
    guide = _load(GUIDE)
    commands = public_supervisor_commands(_load(RUNNER))
    documented = set(_COMMAND_RE.findall(guide))
    assert documented <= commands
    assert {"prepare", "doctor", "start", "status", "stop", "recover", "watchdog"} <= documented
    assert "_run" not in documented
    assert "--repo-root" in guide and "--spec" in guide and "--state-dir" in guide
    recover_block = guide.split("recover \\", 1)[1].split("```", 1)[0]
    assert "--state-dir" in recover_block and "UX_STATE" in recover_block
    ceilings = campaign_ceilings()
    assert ceilings["startup_seconds"] == 90
    assert ceilings["stall_seconds"] == 180
    assert ceilings["implementation_timeout_seconds"] == 900
    assert ceilings["max_turns"] == 64
    assert ceilings["max_task_attempts"] == 3
    assert ceilings["max_recoveries_per_incident"] == 2
    for value in ceilings.values():
        assert str(value) in guide


def test_inventory_limitations_are_recorded_as_unavailable() -> None:
    review = _load(REVIEW)
    guide = _load(GUIDE)
    inventory = _json(INVENTORY)
    manifest = _json(MANIFEST)
    corpus = next(
        item for item in inventory["callable_symbols"]
        if item["symbol"] == "search_us_code_corpus_from_parameters"
    )
    assert corpus["effect_qualification"] == "unavailable"
    assert corpus["symbol"] in review
    assert manifest["provider_invoked"] is False
    assert "provider_invoked" in review
    assert _kit_network(inventory) is False
    assert "kit_network_enabled" in review
    assert "not verified remote durability" in review
    assert "not verified remote durability" in guide
    assert "unexecuted proof" in review
    for owner in inventory["owners"]:
        assert owner["declared_pin"] in review
        assert owner["declared_pin"] in guide
        assert owner["pin_is_observed_head"] is False


def test_screenshot_only_and_historical_completion_do_not_close_the_program() -> None:
    bundle = _measured_bundle()
    review = _load(REVIEW)
    guide = _load(GUIDE)
    real = assess_handoff(review, guide, bundle)
    assert real["status"] == "usable"
    assert real["old60_completes_program"] is False
    assert real["screenshot_files_complete_program"] is False

    names_only = "\n".join(shot["path"] for shot in bundle["screenshots"])
    files_only = assess_handoff(names_only, names_only, bundle)
    assert files_only["status"] == "refused"
    assert files_only["closes_program"] is False
    assert "screenshot_unbound:01-home-desktop" in files_only["reasons"]

    historical = review + "\nThe GUI60 completion completes this program.\n"
    refused = assess_handoff(historical, guide, bundle)
    assert refused["status"] == "refused"
    assert "historical_program_overclaim" in refused["reasons"]
    assert refused["closes_program"] is False

    wrong_hash = review.replace(bundle["screenshots"][0]["sha256"], "0" * 64)
    mismatched = assess_handoff(wrong_hash, guide, bundle)
    assert mismatched["status"] == "refused"
    assert any(reason.startswith("screenshot_unbound:") for reason in mismatched["reasons"])

    durable = review.replace(
        "A local write, a queue, or a content address is not verified remote durability.",
        "A local write is verified remote durability.",
    )
    assert assess_handoff(durable, guide, bundle)["status"] == "refused"

    adopted = review.replace("Not new evidence and not an intake answer by default.", "An annotation is new evidence.")
    assert assess_handoff(adopted, guide, bundle)["status"] == "refused"


def test_role_grant_and_stale_header_cannot_be_rewritten_as_success() -> None:
    bundle = _measured_bundle()
    review = _load(REVIEW)
    guide = _load(GUIDE)
    lawyer_grant = guide.replace(
        "A lawyer role alone grants no case content.",
        "A lawyer role alone grants every case.",
    )
    # The negative guide still has to fail even when the review is intact,
    # because the operator surface would authorize the wrong actor.
    assert "lawyer role alone grants no case content" in review
    assert assess_handoff(review, lawyer_grant, bundle)["status"] == "refused"

    header_hidden = review.replace("No case selected", "case ready")
    hidden = assess_handoff(header_hidden, guide, bundle)
    assert hidden["status"] == "refused"
    assert "stale_header_story_missing" in hidden["reasons"] or "finding_unbound:UX-01" in hidden["reasons"]
