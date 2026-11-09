from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from applications.complaint_workspace import ComplaintWorkspaceService
from complaint_generator.ui_ux_workflow import (
    DEFAULT_OPTIMIZER_METHOD,
    DEFAULT_OPTIMIZER_PRIORITY,
    DEFAULT_SCREENSHOT_TEST,
    DEFAULT_UI_UX_REVIEW_GOALS,
    run_end_to_end_complaint_browser_audit,
)
from complaint_generator.workspace import optimize_ui


_STOP_REQUESTED = False
PROJECT_ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


def _slugify_user_id(user_id: str) -> str:
    normalized = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in str(user_id or "ui-optimizer-daemon"))
    normalized = normalized.strip("-")
    return normalized or "ui-optimizer-daemon"


def _default_artifact_root(user_id: str) -> Path:
    return PROJECT_ROOT / "artifacts" / "ui-optimizer-daemon" / _slugify_user_id(user_id)


def _default_pid_file(artifact_root: Path) -> Path:
    return artifact_root / "ui_optimizer_daemon.pid"


def _default_status_file(artifact_root: Path) -> Path:
    return artifact_root / "ui_optimizer_daemon_status.json"


def _default_log_file(artifact_root: Path) -> Path:
    return artifact_root / "ui_optimizer_daemon.log"


def _signal_stop(_signum, _frame) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def _pid_is_running(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    try:
        completed = subprocess.run(
            ["ps", "-p", str(int(pid)), "-o", "stat="],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        logger.debug("Could not inspect process %s; treating it as stopped", pid, exc_info=True)
        return False
    stat = str(completed.stdout or "").strip()
    if not stat:
        return False
    return "Z" not in stat.upper()


def _matching_daemon_pids(*, user_id: str, artifact_root: Path) -> list[int]:
    target_user = str(user_id or "").strip()
    target_artifact_root = str(artifact_root).strip()
    if not target_user or not target_artifact_root:
        return []
    try:
        completed = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        logger.warning("Could not enumerate UI optimizer daemon processes", exc_info=True)
        return []
    except Exception:
        logger.exception("Unexpected failure while enumerating UI optimizer daemon processes")
        return []
    matches: list[int] = []
    for raw_line in str(completed.stdout or "").splitlines():
        line = raw_line.strip()
        if not line or "complaint_generator.ui_optimizer_daemon run" not in line:
            continue
        if f"--user-id {target_user}" not in line:
            continue
        if f"--artifact-root {target_artifact_root}" not in line:
            continue
        parts = line.split(None, 1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            logger.debug("Ignoring malformed PID in process listing line %r", raw_line)
            continue
        if _pid_is_running(pid):
            matches.append(pid)
    return sorted(set(matches))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def redact_daemon_default_log(record: dict[str, Any] | None) -> dict[str, Any]:
    """Default daemon log projection. Case text, filenames, keys, and tokens stay out."""

    from integrations.ipfs_datasets.storage import redact_private_diagnostic

    return redact_private_diagnostic(record)


def append_default_daemon_log(log_file: Path, record: dict[str, Any] | None) -> dict[str, Any]:
    diagnostic = redact_daemon_default_log(record)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(diagnostic, sort_keys=True) + "\n")
    return diagnostic


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.warning("Could not load daemon JSON state from %s; using an empty state", path, exc_info=True)
        return {}
    except Exception:
        logger.exception("Unexpected failure while loading daemon JSON state from %s; using an empty state", path)
        return {}
    if not isinstance(payload, dict):
        logger.warning(
            "Daemon JSON state at %s is %s, not an object; using an empty state",
            path,
            type(payload).__name__,
        )
        return {}
    return payload


def _unique_nonempty(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _derive_adversarial_goals(
    service: ComplaintWorkspaceService,
    *,
    user_id: str,
    export_review: dict[str, Any] | None = None,
    seed_goals: list[str] | None = None,
) -> list[str]:
    goals: list[str] = []

    export_artifacts = []
    if hasattr(service, "_build_complaint_output_review_artifacts"):
        export_artifacts = list(service._build_complaint_output_review_artifacts(user_id) or [])
    for artifact in export_artifacts:
        if not isinstance(artifact, dict):
            continue
        release_gate = dict(artifact.get("release_gate") or {})
        release_verdict = str(release_gate.get("verdict") or "").strip().lower()
        blocking_reason = str(release_gate.get("blocking_reason") or "").strip()
        if release_verdict and release_verdict != "pass":
            goals.append(
                "Resolve the complaint-output release blockers surfaced by the adversarial review"
                + (f": {blocking_reason}" if blocking_reason else ".")
            )
        formal_gaps = [str(item).strip() for item in list(artifact.get("formal_section_gaps") or []) if str(item).strip()]
        if formal_gaps:
            goals.append(
                "Repair the drafting and export flow so generated complaints consistently include these formal pleading sections: "
                + ", ".join(formal_gaps[:6])
            )
        alignment_failures = [
            str(key).strip()
            for key, value in dict(artifact.get("claim_type_alignment") or {}).items()
            if value is False and str(key).strip()
        ]
        if alignment_failures:
            goals.append(
                "Prevent claim-type drift so the UI and draft builder stop producing the wrong complaint posture for: "
                + ", ".join(alignment_failures[:6])
            )
        suggestion_excerpt = str(artifact.get("ui_suggestions_excerpt") or "").strip()
        if suggestion_excerpt:
            first_line = suggestion_excerpt.splitlines()[0].lstrip("- ").strip()
            if first_line:
                goals.append(f"Apply the strongest complaint-output-guided UI repair: {first_line}")

    cached_ui_artifacts = []
    if hasattr(service, "_build_cached_ui_readiness_artifacts"):
        cached_ui_artifacts = list(service._build_cached_ui_readiness_artifacts(user_id) or [])
    for artifact in cached_ui_artifacts:
        if not isinstance(artifact, dict):
            continue
        for item in list(artifact.get("optimization_targets") or [])[:4]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("target") or item.get("target_surface") or "").strip()
            reason = str(item.get("reason") or "").strip()
            if title and reason:
                goals.append(f"Complete this adversarial optimization target: {title}. {reason}")
            elif title:
                goals.append(f"Complete this adversarial optimization target: {title}")
        for item in list(artifact.get("screenshot_findings") or [])[:4]:
            if not isinstance(item, dict):
                continue
            stage = str(item.get("stage") or item.get("surface") or "workspace").strip()
            summary = str(item.get("summary") or item.get("stage_finding") or "").strip()
            if summary:
                goals.append(f"Fix the {stage} breakdown surfaced by the screenshot critic: {summary}")
        for item in list(artifact.get("recommended_changes") or [])[:4]:
            text = str(item).strip()
            if text:
                goals.append(f"Implement this critic-directed change: {text}")
        for item in list(artifact.get("playwright_followups") or [])[:4]:
            text = str(item).strip()
            if text:
                goals.append(f"Harden the UI until this Playwright obligation passes: {text}")

    aggregate = dict((export_review or {}).get("aggregate") or {})
    for item in list(aggregate.get("issue_findings") or [])[:4]:
        text = str(item).strip()
        if text:
            goals.append(f"Address this export-review issue before the next client-facing cycle: {text}")
    for item in list(aggregate.get("ui_suggestions") or [])[:4]:
        if isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            recommendation = str(item.get("recommendation") or "").strip()
            if title and recommendation:
                goals.append(f"Apply this export-review recommendation: {title}. {recommendation}")
            elif title:
                goals.append(f"Apply this export-review recommendation: {title}")
            elif recommendation:
                goals.append(f"Apply this export-review recommendation: {recommendation}")
        else:
            text = str(item).strip()
            if text:
                goals.append(f"Apply this export-review recommendation: {text}")

    goals.extend([str(item).strip() for item in list(seed_goals or []) if str(item).strip()])
    resolved = _unique_nonempty(goals)
    return resolved or list(DEFAULT_UI_UX_REVIEW_GOALS)


def _resolve_runtime_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    artifact_root = Path(getattr(args, "artifact_root", None) or _default_artifact_root(args.user_id)).expanduser().resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    args.artifact_root = str(artifact_root)
    pid_file = Path(getattr(args, "pid_file", None) or _default_pid_file(artifact_root)).expanduser().resolve()
    status_file = Path(getattr(args, "status_file", None) or _default_status_file(artifact_root)).expanduser().resolve()
    log_file = Path(getattr(args, "log_file", None) or _default_log_file(artifact_root)).expanduser().resolve()
    workspace_root = Path(getattr(args, "workspace_root", None) or (PROJECT_ROOT / ".complaint_workspace" / "sessions")).expanduser().resolve()
    args.workspace_root = str(workspace_root)
    return artifact_root, pid_file, status_file, log_file


def _cycle_dir(artifact_root: Path, cycle_number: int) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return artifact_root / "cycles" / f"cycle-{cycle_number:03d}-{timestamp}"


def _prune_old_cycle_artifacts(artifact_root: Path, *, keep_latest: int = 6) -> None:
    cycles_root = artifact_root / "cycles"
    if not cycles_root.exists():
        return
    cycle_dirs = sorted(
        [path for path in cycles_root.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in cycle_dirs[max(0, int(keep_latest)):]:
        subprocess.run(["rm", "-rf", str(stale)], check=False)


def _status_artifacts(
    *,
    args: argparse.Namespace,
    pid_file: Path,
    status_file: Path,
    log_file: Path,
    last_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the stable artifact manifest shared by persisted and CLI status."""

    artifacts: dict[str, Any] = {
        "artifact_root": str(Path(args.artifact_root).expanduser().resolve()),
        "workspace_root": str(Path(args.workspace_root).expanduser().resolve()),
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
    }
    if isinstance(last_result, dict):
        for key in (
            "cycle_root",
            "screenshot_dir",
            "optimizer_output_dir",
            "export_review_path",
            "cycle_manifest_path",
        ):
            value = last_result.get(key)
            if value:
                artifacts[key] = str(value)
    return artifacts


def _build_status_payload(
    *,
    args: argparse.Namespace,
    pid_file: Path,
    status_file: Path,
    log_file: Path,
    state: str,
    phase: str,
    cycle_count: int,
    consecutive_errors: int,
    last_result: dict[str, Any] | None = None,
    error: str | None = None,
    phase_started_at: str | None = None,
    retry_started_at: str | None = None,
    next_retry_at: str | None = None,
    error_kind: str | None = None,
    error_summary: str | None = None,
) -> dict[str, Any]:
    pid = None
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            logger.debug("Could not read daemon PID from %s; reporting no PID", pid_file, exc_info=True)
            pid = None
    recommendation_coverage: dict[str, Any] = {}
    if isinstance(last_result, dict):
        recommendation_coverage = dict(last_result.get("recommendation_coverage") or {})
        if not recommendation_coverage:
            recommendation_coverage = _extract_optimizer_recommendation_coverage(last_result.get("optimizer_result"))
    now = datetime.now(UTC)
    phase_started_dt = _parse_iso_datetime(phase_started_at)
    retry_started_dt = _parse_iso_datetime(retry_started_at)
    next_retry_dt = _parse_iso_datetime(next_retry_at)
    artifacts = _status_artifacts(
        args=args,
        pid_file=pid_file,
        status_file=status_file,
        log_file=log_file,
        last_result=last_result,
    )
    return {
        "status": state,
        "pid": pid,
        "updated_at": now.isoformat(),
        "artifacts": artifacts,
        "last_error": error,
        "phase": phase,
        "phase_started_at": phase_started_at,
        "phase_elapsed_seconds": _elapsed_seconds(phase_started_dt, now=now),
        "retry_started_at": retry_started_at,
        "retry_elapsed_seconds": _elapsed_seconds(retry_started_dt, now=now),
        "next_retry_at": next_retry_at,
        "seconds_until_next_retry": _seconds_until(next_retry_dt, now=now),
        "user_id": args.user_id,
        "artifact_root": str(Path(args.artifact_root).expanduser().resolve()),
        "workspace_root": str(Path(args.workspace_root).expanduser().resolve()),
        "pytest_target": args.pytest_target,
        "max_rounds": int(args.max_rounds),
        "iterations": int(args.iterations),
        "poll_seconds": float(args.poll_seconds),
        "retry_seconds": float(args.retry_seconds),
        "max_cycles": int(args.max_cycles),
        "max_consecutive_errors": int(args.max_consecutive_errors),
        "method": str(args.method),
        "priority": int(args.priority),
        "provider": str(args.provider or ""),
        "model": str(args.model or ""),
        "use_llm_draft": bool(args.use_llm_draft),
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
        "cycle_count": int(cycle_count),
        "consecutive_errors": int(consecutive_errors),
        "last_result": last_result,
        "recommendation_coverage": recommendation_coverage,
        "error_kind": error_kind,
        "error_summary": error_summary,
        "error": error,
    }


def _write_status(
    *,
    args: argparse.Namespace,
    pid_file: Path,
    status_file: Path,
    log_file: Path,
    state: str,
    phase: str,
    cycle_count: int,
    consecutive_errors: int,
    last_result: dict[str, Any] | None = None,
    error: str | None = None,
    phase_started_at: str | None = None,
    retry_started_at: str | None = None,
    next_retry_at: str | None = None,
    error_kind: str | None = None,
    error_summary: str | None = None,
) -> dict[str, Any]:
    payload = _build_status_payload(
        args=args,
        pid_file=pid_file,
        status_file=status_file,
        log_file=log_file,
        state=state,
        phase=phase,
        cycle_count=cycle_count,
        consecutive_errors=consecutive_errors,
        last_result=last_result,
        error=error,
        phase_started_at=phase_started_at,
        retry_started_at=retry_started_at,
        next_retry_at=next_retry_at,
        error_kind=error_kind,
        error_summary=error_summary,
    )
    _write_json(status_file, payload)
    append_default_daemon_log(
        log_file,
        {
            "operation_id": str(payload.get("phase") or "daemon"),
            "status": str(payload.get("status") or ""),
            "error_category": str(payload.get("error_kind") or ""),
            "duration_ms": payload.get("phase_elapsed_seconds"),
            "synthetic_source": "ui-optimizer-daemon",
            "user_id": getattr(args, "user_id", ""),
            "error": payload.get("error"),
            "last_result": payload.get("last_result"),
        },
    )
    return payload


def _cleanup_pid_file(pid_file: Path) -> None:
    if not pid_file.exists():
        return
    try:
        recorded_pid = int(pid_file.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        logger.debug("Could not read daemon PID from %s during cleanup", pid_file, exc_info=True)
        recorded_pid = 0
    if recorded_pid == os.getpid():
        try:
            pid_file.unlink()
        except FileNotFoundError:
            logger.debug("Daemon PID file %s was already removed", pid_file)
        except OSError:
            logger.warning("Could not remove daemon PID file %s", pid_file, exc_info=True)


def _review_json_excerpt(review_payload: dict[str, Any]) -> str:
    summary = str((review_payload.get("aggregate") or {}).get("summary") or review_payload.get("summary") or "").strip()
    if summary:
        return summary[:400]
    findings = list((review_payload.get("aggregate") or {}).get("issue_findings") or [])
    if findings:
        return str(findings[0])[:400]
    return ""


def _parse_iso_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _elapsed_seconds(started_at: datetime | None, *, now: datetime) -> float | None:
    if started_at is None:
        return None
    return max((now - started_at).total_seconds(), 0.0)


def _seconds_until(target_at: datetime | None, *, now: datetime) -> float | None:
    if target_at is None:
        return None
    return max((target_at - now).total_seconds(), 0.0)


def _classify_error(error: str | None) -> tuple[str | None, str | None]:
    text = str(error or "").strip()
    if not text:
        return None, None
    lowered = text.lower()
    if any(token in lowered for token in ("rate limit", "rate-limit", "too many requests", "429")):
        return "rate_limited", "Provider rate limit encountered; backing off before retry."
    if any(token in lowered for token in ("timed out", "timeout", "deadline exceeded")):
        return "timeout", "A long-running step timed out; backing off before retry."
    if any(token in lowered for token in ("service unavailable", "temporarily unavailable", "503", "connection reset")):
        return "provider_unavailable", "Provider unavailable; backing off before retry."
    return "error", text.splitlines()[0][:240]


def _extract_optimizer_recommendation_coverage(optimizer_result: dict[str, Any] | None) -> dict[str, Any]:
    cycles = list((optimizer_result or {}).get("cycles") or [])
    selected_total = 0
    covered_total = 0
    rounds_with_selected = 0
    latest_selected_titles: list[str] = []
    latest_covered_titles: list[str] = []
    latest_uncovered_titles: list[str] = []
    latest_changed_files: list[str] = []
    latest_status = ""
    ratios: list[float] = []

    for cycle in cycles:
        optimizer_cycle = cycle.get("optimizer_result") or {}
        metadata = optimizer_cycle.get("metadata") or {}
        selected_titles = [str(item).strip() for item in list(metadata.get("selected_patch_brief_titles") or []) if str(item).strip()]
        covered_titles = [str(item).strip() for item in list(metadata.get("covered_patch_brief_titles") or []) if str(item).strip()]
        uncovered_titles = [
            str(item).strip() for item in list(metadata.get("uncovered_selected_patch_brief_titles") or []) if str(item).strip()
        ]
        ratio = float(metadata.get("selected_patch_brief_coverage_ratio") or 0.0)
        changed_files = [str(item).strip() for item in list(optimizer_cycle.get("changed_files") or []) if str(item).strip()]
        status = str(optimizer_cycle.get("status") or "").strip()

        if selected_titles:
            rounds_with_selected += 1
            selected_total += len(selected_titles)
            covered_total += len(covered_titles)
            ratios.append(ratio)
            latest_selected_titles = selected_titles
            latest_covered_titles = covered_titles
            latest_uncovered_titles = uncovered_titles
            latest_changed_files = changed_files
            latest_status = status

    overall_ratio = (covered_total / selected_total) if selected_total else 0.0
    average_ratio = (sum(ratios) / len(ratios)) if ratios else 0.0
    return {
        "rounds_with_selected_patch_briefs": rounds_with_selected,
        "selected_patch_briefs_total": selected_total,
        "covered_patch_briefs_total": covered_total,
        "overall_selected_patch_brief_coverage_ratio": overall_ratio,
        "average_selected_patch_brief_coverage_ratio": average_ratio,
        "latest_selected_patch_brief_titles": latest_selected_titles,
        "latest_covered_patch_brief_titles": latest_covered_titles,
        "latest_uncovered_selected_patch_brief_titles": latest_uncovered_titles,
        "latest_changed_files": latest_changed_files,
        "latest_optimizer_status": latest_status,
    }


def _extract_optimizer_changed_files(optimizer_result: dict[str, Any] | None) -> list[str]:
    if not isinstance(optimizer_result, dict):
        return []
    direct = _unique_nonempty(list(optimizer_result.get("changed_files") or []))
    if direct:
        return direct
    nested: list[str] = []
    for cycle in list(optimizer_result.get("cycles") or []):
        if not isinstance(cycle, dict):
            continue
        optimizer_cycle = dict(cycle.get("optimizer_result") or {})
        nested.extend(list(optimizer_cycle.get("changed_files") or []))
    return _unique_nonempty(nested)


def _run_cycle(
    args: argparse.Namespace,
    *,
    artifact_root: Path,
    cycle_number: int,
    phase_hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    service = ComplaintWorkspaceService(root_dir=Path(args.workspace_root))
    cycle_root = _cycle_dir(artifact_root, cycle_number)
    screenshot_dir = cycle_root / "screens"
    optimize_output_dir = cycle_root / "closed-loop"
    export_review_path = cycle_root / "export-review.json"
    cycle_manifest_path = cycle_root / "cycle-result.json"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    optimize_output_dir.mkdir(parents=True, exist_ok=True)

    if phase_hook:
        phase_hook("running_cycle.generate_draft")
    draft_payload = service.generate_complaint(
        args.user_id,
        use_llm=bool(args.use_llm_draft),
        provider=args.provider,
        model=args.model,
        config_path=args.config_path,
        backend_id=args.backend_id,
    )
    markdown_export = service.export_complaint_markdown(args.user_id)
    pdf_export = service.export_complaint_pdf(args.user_id)
    if phase_hook:
        phase_hook("running_cycle.review_exports")
    pre_export_review = service.review_generated_exports(
        args.user_id,
        provider=args.provider,
        model=args.model,
        config_path=args.config_path,
        backend_id=args.backend_id,
        notes=args.notes,
    )
    adversarial_goals = _derive_adversarial_goals(
        service,
        user_id=args.user_id,
        export_review=pre_export_review,
        seed_goals=list(args.goals or []),
    )

    browser_audit_attempts: list[dict[str, Any]] = []
    browser_audit: dict[str, Any] = {}
    if phase_hook:
        phase_hook("running_cycle.browser_audit")
    for attempt in range(1, 3):
        browser_audit = run_end_to_end_complaint_browser_audit(
            screenshot_dir=screenshot_dir,
            pytest_target=args.pytest_target,
        )
        browser_audit_attempt = dict(browser_audit)
        browser_audit_attempt["attempt"] = attempt
        browser_audit_attempts.append(browser_audit_attempt)
        if int(browser_audit.get("returncode") or 0) == 0:
            break
        if attempt < 2:
            time.sleep(3.0)
    if int(browser_audit.get("returncode") or 0) != 0:
        raise RuntimeError(
            "Browser audit failed before optimization after 2 attempts.\n"
            f"stdout:\n{browser_audit.get('stdout', '')}\n\nstderr:\n{browser_audit.get('stderr', '')}"
        )

    if phase_hook:
        phase_hook("running_cycle.optimize_ui")
    optimizer_result = optimize_ui(
        screenshot_dir=screenshot_dir,
        user_id=args.user_id,
        output_path=optimize_output_dir,
        max_rounds=args.max_rounds,
        iterations=args.iterations,
        notes=args.notes,
        goals=adversarial_goals,
        provider=args.provider,
        model=args.model,
        method=args.method,
        priority=args.priority,
        pytest_target=args.pytest_target,
        reuse_existing_screenshots=True,
        service=service,
    )

    if phase_hook:
        phase_hook("running_cycle.review_exports.final")
    export_review = service.review_generated_exports(
        args.user_id,
        provider=args.provider,
        model=args.model,
        config_path=args.config_path,
        backend_id=args.backend_id,
        notes=args.notes,
    )
    _write_json(export_review_path, export_review)

    result = {
        "cycle_number": cycle_number,
        "cycle_root": str(cycle_root),
        "screenshot_dir": str(screenshot_dir),
        "optimizer_output_dir": str(optimize_output_dir),
        "export_review_path": str(export_review_path),
        "cycle_manifest_path": str(cycle_manifest_path),
        "browser_audit": browser_audit,
        "browser_audit_attempts": browser_audit_attempts,
        "optimizer_result": optimizer_result,
        "optimizer_changed_files": _extract_optimizer_changed_files(optimizer_result),
        "adversarial_goals": adversarial_goals,
        "goal_source": "adversarial_feedback",
        "pre_export_review": pre_export_review,
        "export_review": export_review,
        "draft_title": str((draft_payload.get("draft") or {}).get("title") or ""),
        "markdown_export": {
            "filename": str(((markdown_export.get("artifact") or {}).get("filename") or "")),
            "size_bytes": int(((markdown_export.get("artifact") or {}).get("size_bytes") or 0)),
        },
        "pdf_export": {
            "filename": str(((pdf_export.get("artifact") or {}).get("filename") or "")),
            "size_bytes": int(((pdf_export.get("artifact") or {}).get("size_bytes") or 0)),
        },
        "summary": {
            "browser_artifact_count": int(browser_audit.get("artifact_count") or 0),
            "optimizer_workflow_type": str(optimizer_result.get("workflow_type") or ""),
            "optimizer_rounds_executed": int(optimizer_result.get("rounds_executed") or 0),
            "optimizer_stop_reason": str(optimizer_result.get("stop_reason") or ""),
            "optimizer_changed_file_count": len(_extract_optimizer_changed_files(optimizer_result)),
            "filing_shape_score": int(((export_review.get("aggregate") or {}).get("average_filing_shape_score") or 0)),
            "claim_type_alignment_score": int(((export_review.get("aggregate") or {}).get("average_claim_type_alignment_score") or 0)),
            "export_review_excerpt": _review_json_excerpt(export_review),
            "adversarial_goal_count": len(adversarial_goals),
        },
    }
    result["recommendation_coverage"] = _extract_optimizer_recommendation_coverage(optimizer_result)
    result["summary"]["recommendation_coverage"] = dict(result["recommendation_coverage"])
    _write_json(cycle_manifest_path, result)
    return result


def _run_daemon(args: argparse.Namespace) -> dict[str, Any]:
    global _STOP_REQUESTED
    _STOP_REQUESTED = False
    signal.signal(signal.SIGTERM, _signal_stop)
    signal.signal(signal.SIGINT, _signal_stop)

    artifact_root, pid_file, status_file, log_file = _resolve_runtime_paths(args)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")

    cycle_count = 0
    consecutive_errors = 0
    last_result: dict[str, Any] | None = None
    state: dict[str, Any] = {
        "phase": "starting",
        "phase_started_at": datetime.now(UTC).isoformat(),
        "cycle_count": 0,
        "consecutive_errors": 0,
        "last_result": None,
        "error": None,
        "retry_started_at": None,
        "next_retry_at": None,
        "error_kind": None,
        "error_summary": None,
    }

    def _heartbeat() -> None:
        while not _STOP_REQUESTED:
            _write_status(
                args=args,
                pid_file=pid_file,
                status_file=status_file,
                log_file=log_file,
                state="running",
                phase=str(state.get("phase") or "running"),
                cycle_count=int(state.get("cycle_count") or 0),
                consecutive_errors=int(state.get("consecutive_errors") or 0),
                last_result=state.get("last_result"),
                error=state.get("error"),
                phase_started_at=state.get("phase_started_at"),
                retry_started_at=state.get("retry_started_at"),
                next_retry_at=state.get("next_retry_at"),
                error_kind=state.get("error_kind"),
                error_summary=state.get("error_summary"),
            )
            time.sleep(15.0)

    _write_status(
        args=args,
        pid_file=pid_file,
        status_file=status_file,
        log_file=log_file,
        state="running",
        phase="starting",
        cycle_count=0,
        consecutive_errors=0,
        phase_started_at=state.get("phase_started_at"),
    )
    heartbeat = threading.Thread(target=_heartbeat, name="ui-optimizer-daemon-heartbeat", daemon=True)
    heartbeat.start()

    try:
        def _set_phase(phase: str, *, error: str | None = None) -> None:
            if str(state.get("phase") or "") != phase:
                state["phase_started_at"] = datetime.now(UTC).isoformat()
            state["phase"] = phase
            _write_status(
                args=args,
                pid_file=pid_file,
                status_file=status_file,
                log_file=log_file,
                state="running",
                phase=phase,
                cycle_count=cycle_count,
                consecutive_errors=consecutive_errors,
                last_result=last_result,
                error=error if error is not None else state.get("error"),
                phase_started_at=state.get("phase_started_at"),
                retry_started_at=state.get("retry_started_at"),
                next_retry_at=state.get("next_retry_at"),
                error_kind=state.get("error_kind"),
                error_summary=state.get("error_summary"),
            )

        while not _STOP_REQUESTED:
            _prune_old_cycle_artifacts(artifact_root)
            cycle_count += 1
            state["cycle_count"] = cycle_count
            _set_phase("running_cycle.prepare")
            try:
                state["retry_started_at"] = None
                state["next_retry_at"] = None
                state["error_kind"] = None
                state["error_summary"] = None
                last_result = _run_cycle(
                    args,
                    artifact_root=artifact_root,
                    cycle_number=cycle_count,
                    phase_hook=_set_phase,
                )
                consecutive_errors = 0
                state["last_result"] = last_result
                state["error"] = None
                state["consecutive_errors"] = 0
                state["retry_started_at"] = None
                state["next_retry_at"] = None
                state["error_kind"] = None
                state["error_summary"] = None
                state["phase"] = "sleeping"
                state["phase_started_at"] = datetime.now(UTC).isoformat()
                _write_status(
                    args=args,
                    pid_file=pid_file,
                    status_file=status_file,
                    log_file=log_file,
                    state="running",
                    phase="sleeping",
                    cycle_count=cycle_count,
                    consecutive_errors=0,
                    last_result=last_result,
                    phase_started_at=state.get("phase_started_at"),
                )
            except Exception as exc:
                logger.exception("UI optimizer daemon cycle %s failed", cycle_count)
                error_text = str(exc)
                error_kind, error_summary = _classify_error(error_text)
                consecutive_errors += 1
                state["error"] = error_text
                state["consecutive_errors"] = consecutive_errors
                state["phase"] = "error"
                state["phase_started_at"] = datetime.now(UTC).isoformat()
                state["error_kind"] = error_kind
                state["error_summary"] = error_summary
                _write_status(
                    args=args,
                    pid_file=pid_file,
                    status_file=status_file,
                    log_file=log_file,
                    state="error",
                    phase="error",
                    cycle_count=cycle_count,
                    consecutive_errors=consecutive_errors,
                    last_result=last_result,
                    error=error_text,
                    phase_started_at=state.get("phase_started_at"),
                    retry_started_at=state.get("retry_started_at"),
                    next_retry_at=state.get("next_retry_at"),
                    error_kind=state.get("error_kind"),
                    error_summary=state.get("error_summary"),
                )
                if _STOP_REQUESTED:
                    break
                if int(args.max_consecutive_errors or 0) > 0 and consecutive_errors >= int(args.max_consecutive_errors):
                    raise
                retry_seconds = max(float(args.retry_seconds or 0.0), 0.0)
                retry_started_at = datetime.now(UTC)
                next_retry_at = retry_started_at.timestamp() + retry_seconds
                state["retry_started_at"] = retry_started_at.isoformat()
                state["next_retry_at"] = datetime.fromtimestamp(next_retry_at, tz=UTC).isoformat()
                if error_kind == "rate_limited":
                    retry_phase = "backing_off.rate_limited"
                elif error_kind == "timeout":
                    retry_phase = "backing_off.timeout"
                elif error_kind == "provider_unavailable":
                    retry_phase = "backing_off.provider_unavailable"
                else:
                    retry_phase = "retrying_after_error"
                state["phase"] = retry_phase
                state["phase_started_at"] = retry_started_at.isoformat()
                _write_status(
                    args=args,
                    pid_file=pid_file,
                    status_file=status_file,
                    log_file=log_file,
                    state="running",
                    phase=retry_phase,
                    cycle_count=cycle_count,
                    consecutive_errors=consecutive_errors,
                    last_result=last_result,
                    error=error_text,
                    phase_started_at=state.get("phase_started_at"),
                    retry_started_at=state.get("retry_started_at"),
                    next_retry_at=state.get("next_retry_at"),
                    error_kind=state.get("error_kind"),
                    error_summary=state.get("error_summary"),
                )
                time.sleep(retry_seconds)
                continue
            if _STOP_REQUESTED:
                break
            if int(args.max_cycles or 0) > 0 and cycle_count >= int(args.max_cycles):
                break
            time.sleep(max(float(args.poll_seconds or 0.0), 0.0))
    finally:
        final_state = "stopped" if _STOP_REQUESTED else "completed"
        _write_status(
            args=args,
            pid_file=pid_file,
            status_file=status_file,
            log_file=log_file,
            state=final_state,
            phase=final_state,
            cycle_count=cycle_count,
            consecutive_errors=consecutive_errors,
            last_result=last_result,
            error=state.get("error"),
            phase_started_at=state.get("phase_started_at"),
            retry_started_at=state.get("retry_started_at"),
            next_retry_at=state.get("next_retry_at"),
            error_kind=state.get("error_kind"),
            error_summary=state.get("error_summary"),
        )
        _cleanup_pid_file(pid_file)
    return {
        "status": "success",
        "daemon_state": final_state,
        "artifact_root": str(artifact_root),
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
        "cycle_count": cycle_count,
        "last_result": last_result,
    }


def _build_run_command(
    args: argparse.Namespace,
    *,
    pid_file: Path,
    status_file: Path,
    log_file: Path,
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "complaint_generator.ui_optimizer_daemon",
        "run",
        "--user-id",
        args.user_id,
        "--workspace-root",
        str(args.workspace_root),
        "--artifact-root",
        str(args.artifact_root),
        "--pytest-target",
        str(args.pytest_target),
        "--max-rounds",
        str(args.max_rounds),
        "--iterations",
        str(args.iterations),
        "--method",
        str(args.method),
        "--priority",
        str(args.priority),
        "--poll-seconds",
        str(args.poll_seconds),
        "--retry-seconds",
        str(args.retry_seconds),
        "--max-consecutive-errors",
        str(args.max_consecutive_errors),
        "--max-cycles",
        str(args.max_cycles),
        "--pid-file",
        str(pid_file),
        "--status-file",
        str(status_file),
        "--log-file",
        str(log_file),
    ]
    if args.notes:
        cmd.extend(["--notes", str(args.notes)])
    for goal in list(args.goals or []):
        cmd.extend(["--goal", goal])
    if args.provider:
        cmd.extend(["--provider", str(args.provider)])
    if args.model:
        cmd.extend(["--model", str(args.model)])
    if args.config_path:
        cmd.extend(["--config-path", str(args.config_path)])
    if args.backend_id:
        cmd.extend(["--backend-id", str(args.backend_id)])
    if args.use_llm_draft:
        cmd.append("--use-llm-draft")
    return cmd


def _start_daemon(args: argparse.Namespace) -> dict[str, Any]:
    artifact_root, pid_file, status_file, log_file = _resolve_runtime_paths(args)
    matching_pids = _matching_daemon_pids(user_id=args.user_id, artifact_root=artifact_root)
    if pid_file.exists():
        try:
            existing_pid = int(pid_file.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            logger.warning(
                "Could not read existing daemon PID from %s; checking live processes instead",
                pid_file,
                exc_info=True,
            )
            existing_pid = 0
        if _pid_is_running(existing_pid):
            return {
                "status": "already_running",
                "pid": existing_pid,
                "matching_pids": matching_pids or [existing_pid],
                "artifact_root": str(artifact_root),
                "pid_file": str(pid_file),
                "status_file": str(status_file),
                "log_file": str(log_file),
            }
    if matching_pids:
        return {
            "status": "already_running",
            "pid": int(matching_pids[0]),
            "matching_pids": matching_pids,
            "artifact_root": str(artifact_root),
            "pid_file": str(pid_file),
            "status_file": str(status_file),
            "log_file": str(log_file),
        }

    cmd = _build_run_command(args, pid_file=pid_file, status_file=status_file, log_file=log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=dict(os.environ),
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
        )
    time.sleep(0.2)
    return {
        "status": "started",
        "pid": int(process.pid),
        "artifact_root": str(artifact_root),
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
        "command": cmd,
    }


def _status_payload(args: argparse.Namespace) -> dict[str, Any]:
    artifact_root, pid_file, status_file, log_file = _resolve_runtime_paths(args)
    pid = 0
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            logger.warning(
                "Could not read daemon PID from %s; checking live processes instead",
                pid_file,
                exc_info=True,
            )
            pid = 0
    matching_pids = _matching_daemon_pids(user_id=args.user_id, artifact_root=artifact_root)
    live_pid = int(matching_pids[0]) if matching_pids else pid
    status_payload = _load_json(status_file)
    last_result = status_payload.get("last_result") if isinstance(status_payload, dict) else None
    recommendation_coverage = {}
    if isinstance(last_result, dict):
        recommendation_coverage = dict(last_result.get("recommendation_coverage") or {})
        if not recommendation_coverage:
            recommendation_coverage = _extract_optimizer_recommendation_coverage(last_result.get("optimizer_result"))
    artifacts = dict(status_payload.get("artifacts") or {})
    if not artifacts:
        artifacts = _status_artifacts(
            args=args,
            pid_file=pid_file,
            status_file=status_file,
            log_file=log_file,
            last_result=last_result if isinstance(last_result, dict) else None,
        )
    updated_at = str(status_payload.get("updated_at") or datetime.now(UTC).isoformat())
    last_error = status_payload.get("last_error", status_payload.get("error"))
    return {
        "status": "ok",
        "pid": live_pid,
        "updated_at": updated_at,
        "artifacts": artifacts,
        "last_error": last_error,
        "artifact_root": str(artifact_root),
        "running": _pid_is_running(live_pid),
        "matching_pids": matching_pids,
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
        "status_payload": status_payload,
        "recommendation_coverage": recommendation_coverage,
    }


def _stop_daemon(args: argparse.Namespace) -> dict[str, Any]:
    artifact_root, pid_file, status_file, log_file = _resolve_runtime_paths(args)
    pid = 0
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            logger.warning(
                "Could not read daemon PID from %s before stopping; checking live processes instead",
                pid_file,
                exc_info=True,
            )
            pid = 0
    matching_pids = _matching_daemon_pids(user_id=args.user_id, artifact_root=artifact_root)
    target_pids = sorted(set(([pid] if pid > 0 and _pid_is_running(pid) else []) + matching_pids))
    if not target_pids:
        return {
            "status": "not_running",
            "artifact_root": str(artifact_root),
            "pid_file": str(pid_file),
            "status_file": str(status_file),
            "log_file": str(log_file),
        }
    for target_pid in target_pids:
        try:
            os.kill(target_pid, signal.SIGTERM)
        except ProcessLookupError:
            logger.debug("Daemon process %s exited before it could be stopped", target_pid)
            continue
        except OSError:
            logger.warning("Could not send SIGTERM to daemon process %s", target_pid, exc_info=True)
            continue
    return {
        "status": "stopping",
        "pid": int(target_pids[0]),
        "matching_pids": target_pids,
        "artifact_root": str(artifact_root),
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
    }


def _add_shared_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--user-id", required=True, help="Complaint workspace user id to optimize around.")
    parser.add_argument("--workspace-root", default=None, help="Complaint workspace root directory.")
    parser.add_argument("--artifact-root", default=None, help="Root directory for daemon artifacts, screenshots, and reviews.")
    parser.add_argument("--pytest-target", default=DEFAULT_SCREENSHOT_TEST, help="Playwright target used for browser audits.")
    parser.add_argument("--max-rounds", type=int, default=2, help="Maximum closed-loop optimizer rounds per cycle.")
    parser.add_argument("--iterations", type=int, default=1, help="Review iterations passed to the closed-loop optimizer.")
    parser.add_argument("--notes", default=None, help="Shared operator notes passed into export review and optimizer runs.")
    parser.add_argument("--goal", dest="goals", action="append", default=[], help="Optional seed objective. The daemon primarily derives goals from adversarial review artifacts each cycle.")
    parser.add_argument("--provider", default=None, help="Optional provider override for router-backed review steps.")
    parser.add_argument("--model", default=None, help="Optional model override for router-backed review steps.")
    parser.add_argument("--config-path", default="config.llm_router.json", help="LLM router config path used for complaint output review.")
    parser.add_argument("--backend-id", default=None, help="Optional backend id override for complaint output review.")
    parser.add_argument("--method", default=DEFAULT_OPTIMIZER_METHOD, help="Optimizer method, such as actor_critic or adversarial.")
    parser.add_argument("--priority", type=int, default=DEFAULT_OPTIMIZER_PRIORITY, help="Optimizer priority score.")
    parser.add_argument("--use-llm-draft", action="store_true", help="Refresh the complaint draft with llm_router before each cycle.")
    parser.add_argument("--poll-seconds", type=float, default=1800.0, help="Delay between successful cycles.")
    parser.add_argument("--retry-seconds", type=float, default=300.0, help="Delay before retrying after a failed cycle.")
    parser.add_argument("--max-consecutive-errors", type=int, default=0, help="Maximum consecutive errors before exit. 0 retries forever.")
    parser.add_argument("--max-cycles", type=int, default=0, help="Maximum cycles before exit. 0 runs until stopped.")
    parser.add_argument("--pid-file", default=None, help="Optional PID file path.")
    parser.add_argument("--status-file", default=None, help="Optional daemon status JSON path.")
    parser.add_argument("--log-file", default=None, help="Optional daemon log path.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the complaint UI/UX actor-critic optimizer daemon.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the optimizer daemon in the foreground.")
    _add_shared_args(run_parser)

    start_parser = subparsers.add_parser("start", help="Start the optimizer daemon in the background.")
    _add_shared_args(start_parser)

    status_parser = subparsers.add_parser("status", help="Show optimizer daemon status.")
    status_parser.add_argument("--user-id", required=True, help="Complaint workspace user id.")
    status_parser.add_argument("--workspace-root", default=None, help="Complaint workspace root directory.")
    status_parser.add_argument("--artifact-root", default=None, help="Root directory for daemon artifacts.")
    status_parser.add_argument("--pid-file", default=None, help="Optional PID file path.")
    status_parser.add_argument("--status-file", default=None, help="Optional daemon status JSON path.")
    status_parser.add_argument("--log-file", default=None, help="Optional daemon log path.")
    status_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    stop_parser = subparsers.add_parser("stop", help="Stop the optimizer daemon.")
    stop_parser.add_argument("--user-id", required=True, help="Complaint workspace user id.")
    stop_parser.add_argument("--workspace-root", default=None, help="Complaint workspace root directory.")
    stop_parser.add_argument("--artifact-root", default=None, help="Root directory for daemon artifacts.")
    stop_parser.add_argument("--pid-file", default=None, help="Optional PID file path.")
    stop_parser.add_argument("--status-file", default=None, help="Optional daemon status JSON path.")
    stop_parser.add_argument("--log-file", default=None, help="Optional daemon log path.")
    stop_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        payload = _run_daemon(args)
    elif args.command == "start":
        payload = _start_daemon(args)
    elif args.command == "status":
        payload = _status_payload(args)
    elif args.command == "stop":
        payload = _stop_daemon(args)
    else:
        parser.error(f"Unsupported command: {args.command}")
        return 2

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = [
    "build_parser",
    "main",
    "_run_daemon",
    "_start_daemon",
    "_status_payload",
    "_stop_daemon",
]


if __name__ == "__main__":
    raise SystemExit(main())
