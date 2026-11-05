#!/usr/bin/env python3
"""Qualify complaint UX screenshots against layout, keyboard, and state evidence.

A matching image hash is recorded and never treated as a pass. Each required
case must carry a layout landmark or a keyboard/interaction result plus the
backend or privacy result that the pixels cannot prove. A reviewed baseline
change needs a written reason. Required cases are nonempty and cannot be skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any, Mapping

from tests.gui_ux_overhaul_fixtures import (
    BASELINE_DIR,
    VISUAL_STATE_VARIANTS,
    assert_png,
    baseline_manifest,
    declared_visual_widths,
    file_sha256,
    load_contract,
)


SCHEMA = "complaint-ux-visual-qualification@1"
TASK_ID = "CIMP-UX-62"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_GENERIC_REASONS = frozenset({
    "",
    "updated",
    "updated baseline",
    "n/a",
    "na",
    "none",
    "pixel match",
    "image similarity",
})


class VisualQualificationError(ValueError):
    """The report missed a required landmark, interaction, or privacy check."""


def png_dimensions(payload: bytes) -> tuple[int, int]:
    """Read width and height from a PNG IHDR. This is not a similarity score."""

    blob = bytes(payload)
    if not blob.startswith(PNG_MAGIC) or blob[12:16] != b"IHDR" or len(blob) < 24:
        raise ValueError("screenshot_not_png")
    width, height = struct.unpack(">II", blob[16:24])
    if width < 1 or height < 1:
        raise ValueError("screenshot_blank_or_truncated")
    return int(width), int(height)


def image_similarity(left: bytes, right: bytes) -> float:
    """Byte agreement on a short prefix. Callers must not use this as a pass."""

    if left == right and left:
        return 1.0
    sample = 4096
    paired = min(len(left), len(right), sample)
    if paired == 0:
        return 0.0
    same = sum(1 for index in range(paired) if left[index] == right[index])
    return same / float(sample)


def required_case_ids(contract: Mapping[str, Any] | None = None) -> list[str]:
    contract = load_contract() if contract is None else contract
    ids = [f"width-{item['width']}" for item in declared_visual_widths(contract)]
    ids.append("keyboard-case-path")
    ids.extend(f"state-{name}" for name in VISUAL_STATE_VARIANTS)
    if len(ids) != len(set(ids)):
        raise VisualQualificationError("duplicate_required_case")
    return ids


def _reason_documents_change(reason: object) -> bool:
    if not isinstance(reason, str):
        return False
    text = " ".join(reason.split())
    if len(text) < 40 or text.casefold() in _GENERIC_REASONS:
        return False
    lowered = text.casefold()
    return "baseline" in lowered or "pixel" in lowered or "similarity" in lowered


def _fail(failures: list[str], case_id: str, code: str) -> None:
    failures.append(f"{case_id}:{code}")


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    return None


def audit_repository_baseline() -> dict[str, Any]:
    """Compare committed baseline bytes with the manifest viewport and digest.

    IHDR size is a layout fact. Digest equality is identity, not a product pass.
    """

    contract = load_contract()
    manifest_path = BASELINE_DIR / "screenshot_manifest.json"
    manifest = baseline_manifest()
    failures: list[str] = []
    if file_sha256(manifest_path) != contract["baseline_manifest_sha256"]:
        failures.append("manifest:digest_drift")
    experience = Path(__file__).resolve().parents[1] / str(contract["experience_contract"])
    if file_sha256(experience) != contract["experience_contract_sha256"]:
        failures.append("experience_contract:digest_drift")
    story = contract.get("preserved_baseline_story")
    if not isinstance(story, list) or not any("No case selected" in item for item in story):
        failures.append("baseline_story:missing_defect_record")
    shots = manifest.get("screenshots")
    if not isinstance(shots, list) or not shots:
        failures.append("manifest:empty")
        shots = []
    seen_widths: set[int] = set()
    for shot in shots:
        if not isinstance(shot, Mapping):
            failures.append("manifest:shot_not_object")
            continue
        shot_id = str(shot.get("id") or "")
        path = BASELINE_DIR / str(shot.get("path") or "")
        if not path.is_file():
            failures.append(f"{shot_id}:missing_file")
            continue
        blob = path.read_bytes()
        try:
            digest = assert_png(blob, minimum=800)
            width, height = png_dimensions(blob)
        except ValueError as exc:
            failures.append(f"{shot_id}:{exc}")
            continue
        if digest != shot.get("sha256"):
            failures.append(f"{shot_id}:sha256_mismatch")
        viewport = shot.get("viewport") if isinstance(shot.get("viewport"), Mapping) else {}
        if int(viewport.get("width") or 0) != width or int(viewport.get("height") or 0) != height:
            failures.append(f"{shot_id}:ihdr_viewport_mismatch")
        seen_widths.add(width)
        if shot.get("synthetic") is not True or shot.get("diagnostic_test_panels_mounted") is not False:
            failures.append(f"{shot_id}:not_synthetic")
    # The historical baseline records desktop and mobile. Tablet 768 and the
    # 320px reflow are capture/experience widths, not files in that manifest.
    if 1440 not in seen_widths or 390 not in seen_widths:
        failures.append("manifest:missing_declared_width")
    return {
        "ok": not failures,
        "failures": failures,
        "screenshot_count": len(shots),
        "widths": sorted(seen_widths),
        "image_similarity_is_pass": False,
    }


def qualify_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless every required case has interaction and backend evidence."""

    failures: list[str] = []
    if report.get("schema") != SCHEMA or report.get("task_id") != TASK_ID:
        failures.append("report:identity")
    if report.get("image_similarity_is_pass") is True or report.get("pass_basis") == "image_similarity":
        failures.append("report:image_similarity_is_not_a_pass")
    fence = report.get("network_fence")
    if not isinstance(fence, Mapping) or fence.get("af_unix", {}).get("opened") is not True:
        failures.append("report:network_fence")
    elif fence.get("af_unix_only") is True and fence.get("af_inet", {}).get("opened") is True:
        failures.append("report:network_fence_lie")
    elif fence.get("af_unix_only") is not True and fence.get("af_inet", {}).get("opened") is not True:
        failures.append("report:network_fence")
    contract = load_contract()
    story = report.get("preserved_baseline_story")
    if story != contract.get("preserved_baseline_story"):
        failures.append("report:baseline_story_not_preserved")
    expected = required_case_ids(contract)
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise VisualQualificationError("required_cases_empty")
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in cases:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
            failures.append("report:case_shape")
            continue
        if item["id"] in by_id:
            failures.append(f"{item['id']}:duplicate")
        by_id[item["id"]] = item
    for case_id in expected:
        item = by_id.get(case_id)
        if item is None:
            _fail(failures, case_id, "missing")
            continue
        _qualify_case(item, failures)
    extra = sorted(set(by_id) - set(expected))
    if extra:
        failures.append("report:undeclared_case:" + ",".join(extra))
    skipped = [case_id for case_id, item in by_id.items() if item.get("skipped") is True or item.get("status") == "skipped"]
    if skipped:
        failures.append("report:skipped:" + ",".join(skipped))
    passed = not failures
    if not passed:
        raise VisualQualificationError(";".join(failures))
    return {
        "ok": True,
        "task_id": TASK_ID,
        "case_count": len(expected),
        "skipped": 0,
        "image_similarity_is_pass": False,
        "failures": [],
    }


def _qualify_case(item: Mapping[str, Any], failures: list[str]) -> None:
    case_id = str(item.get("id"))
    if item.get("skipped") is True or item.get("status") == "skipped":
        _fail(failures, case_id, "skipped")
        return
    if item.get("pass_basis") == "image_similarity":
        _fail(failures, case_id, "image_similarity_pass")
    interaction = _as_mapping(item.get("interaction"))
    backend = _as_mapping(item.get("backend"))
    if interaction is None or not _interaction_has_result(interaction):
        _fail(failures, case_id, "interaction_missing")
    if backend is None or not isinstance(backend.get("status"), int):
        _fail(failures, case_id, "backend_missing")
    if isinstance(item.get("image_similarity"), (int, float)) and float(item["image_similarity"]) >= 0.99:
        if interaction is None or backend is None or backend.get("checked") is not True:
            _fail(failures, case_id, "similarity_without_state")
    baseline_sha = item.get("baseline_sha256")
    observed_sha = item.get("screenshot_sha256")
    changed = item.get("baseline_changed")
    if isinstance(baseline_sha, str) and isinstance(observed_sha, str) and baseline_sha != observed_sha:
        changed = True
    if changed is True and not _reason_documents_change(item.get("review_reason")):
        _fail(failures, case_id, "baseline_change_without_reason")
    if case_id.startswith("width-"):
        _qualify_width(item, failures)
    elif case_id == "keyboard-case-path":
        if not interaction or interaction.get("activated") is not True or not interaction.get("focus_returned"):
            _fail(failures, case_id, "keyboard_path")
    elif case_id == "state-loading":
        if not interaction or interaction.get("loading_visible") is not True:
            _fail(failures, case_id, "loading_not_visible")
        if not backend or backend.get("settled") is not True:
            _fail(failures, case_id, "loading_not_settled")
    elif case_id == "state-empty":
        if not interaction or interaction.get("empty_visible") is not True:
            _fail(failures, case_id, "empty_not_visible")
        if not backend or backend.get("count") != 0 or backend.get("invented_evidence") is not False:
            _fail(failures, case_id, "empty_backend")
    elif case_id == "state-error":
        if not interaction or not isinstance(interaction.get("denied_text"), str) or "denied" not in interaction["denied_text"].casefold():
            _fail(failures, case_id, "error_text")
        if not backend or int(backend.get("status") or 0) < 400:
            _fail(failures, case_id, "error_status")
    elif case_id == "state-locked":
        _qualify_locked(item, failures)
    elif case_id == "state-revoked":
        _qualify_revoked(item, failures)
    elif case_id == "state-stale":
        if not interaction or interaction.get("unchanged") is not True:
            _fail(failures, case_id, "stale_mutated_view")
        if not backend or backend.get("code") != "encrypted_revision_conflict" or int(backend.get("status") or 0) != 409:
            _fail(failures, case_id, "stale_not_refused")
        if backend and backend.get("label_after") != backend.get("label_before"):
            _fail(failures, case_id, "stale_wrote_label")


def _interaction_has_result(interaction: Mapping[str, Any]) -> bool:
    ignored = {"image_similarity", "screenshot_sha256", "pass_basis"}
    for key, value in interaction.items():
        if key in ignored:
            continue
        if value is True or (isinstance(value, str) and value.strip()) or isinstance(value, (int, float)) and key != "image_similarity":
            return True
    return False


def _qualify_width(item: Mapping[str, Any], failures: list[str]) -> None:
    case_id = str(item["id"])
    viewport = _as_mapping(item.get("viewport")) or {}
    landmarks = _as_mapping(item.get("landmarks")) or {}
    width = viewport.get("width")
    height = viewport.get("height")
    if not isinstance(width, int) or not isinstance(height, int):
        _fail(failures, case_id, "viewport")
        return
    if case_id != f"width-{width}":
        _fail(failures, case_id, "width_name")
    if landmarks.get("visible") is not True or landmarks.get("labelled") is not True:
        _fail(failures, case_id, "landmark_hidden")
    right = landmarks.get("right")
    scroll = landmarks.get("scroll_width")
    if not isinstance(right, (int, float)) or not isinstance(scroll, (int, float)):
        _fail(failures, case_id, "landmark_box")
    elif right > width + 1 or scroll > width + 1:
        _fail(failures, case_id, "clipped_or_overflow")
    if landmarks.get("png_width") != width or landmarks.get("png_height") != height:
        _fail(failures, case_id, "screenshot_viewport")
    if landmarks.get("essential_action_visible") is not True:
        _fail(failures, case_id, "essential_action_hidden")
    if width == 320 and landmarks.get("reduced_motion_keeps_action") is not True:
        _fail(failures, case_id, "reduced_motion")


def _privacy_closed(item: Mapping[str, Any], failures: list[str]) -> Mapping[str, Any]:
    privacy = _as_mapping(item.get("privacy")) or {}
    if privacy.get("plaintext_present") is not False or privacy.get("owner_label_visible") is not False:
        _fail(failures, str(item.get("id")), "privacy")
    return privacy


def _qualify_locked(item: Mapping[str, Any], failures: list[str]) -> None:
    case_id = str(item["id"])
    interaction = _as_mapping(item.get("interaction")) or {}
    backend = _as_mapping(item.get("backend")) or {}
    _privacy_closed(item, failures)
    if interaction.get("entry") != "missing-key":
        _fail(failures, case_id, "locked_entry")
    if backend.get("error") != "unlock_needed" or int(backend.get("status") or 0) != 503:
        _fail(failures, case_id, "locked_backend")
    if backend.get("session_readable") is not False or backend.get("checked") is not True:
        _fail(failures, case_id, "locked_readable")


def _qualify_revoked(item: Mapping[str, Any], failures: list[str]) -> None:
    case_id = str(item["id"])
    interaction = _as_mapping(item.get("interaction")) or {}
    backend = _as_mapping(item.get("backend")) or {}
    _privacy_closed(item, failures)
    if interaction.get("content_withheld") is not True or interaction.get("owner_label_in_page") is not False:
        _fail(failures, case_id, "revoked_visible_content")
    if backend.get("revoked") is not True or int(backend.get("status") or 0) != 403:
        _fail(failures, case_id, "revoked_backend")
    if backend.get("checked") is not True:
        _fail(failures, case_id, "revoked_unchecked")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qualify a complaint UX visual report. Image similarity is not a pass.")
    parser.add_argument("report", type=Path, help="JSON report produced from a live synthetic capture")
    parser.add_argument("--audit-baseline", action="store_true", help="Also compare repository baseline bytes with the manifest")
    args = parser.parse_args(argv)
    if args.audit_baseline:
        audit = audit_repository_baseline()
        if not audit["ok"]:
            print(json.dumps(audit, sort_keys=True))
            return 1
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        result = qualify_report(report)
    except (OSError, json.JSONDecodeError, VisualQualificationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    digest = hashlib.sha256(args.report.read_bytes()).hexdigest()
    print(json.dumps({**result, "report_sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
