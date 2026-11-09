from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
import os
import tempfile
import threading
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional

from backends import LLMRouterBackend, MultimodalRouterBackend


logger = logging.getLogger(__name__)


DEFAULT_COMPLAINT_OUTPUT_REVIEW_TIMEOUT_S = 8
DEFAULT_UI_REVIEW_TIMEOUT_S = 10
DEFAULT_UI_REVIEW_PROVIDER = "codex_cli"
DEFAULT_UI_REVIEW_MODELS_BY_PROVIDER = {
    "codex": "gpt-5.3-codex",
    "codex_cli": "gpt-5.3-codex",
    "hf_inference_api": "Qwen/Qwen2.5-VL-7B-Instruct",
}
_TEXT_ONLY_UI_REVIEW_PROVIDERS = {
    "codex",
    "copilot_cli",
    "copilot_sdk",
}
_TEXT_UI_REVIEW_TIMEOUTS = {
    "codex": 120,
    "codex_cli": 120,
    "copilot_cli": 25,
    "copilot_sdk": 25,
    "hf_inference_api": 60,
}
_MULTIMODAL_RATE_LIMIT_FALLBACKS = {
    "codex": ("copilot_cli", "hf_inference_api"),
    "codex_cli": ("copilot_cli", "hf_inference_api"),
    "copilot_cli": ("hf_inference_api",),
}
_UI_REVIEW_TEXT_ITEM_LIMIT = 280
_UI_REVIEW_SUGGESTION_COUNT_LIMIT = 4
_UI_REVIEW_METADATA_LIST_LIMIT = 4
_UI_REVIEW_PROVIDER_IMAGE_LIMITS = {
    "hf_inference_api": {"max_bytes": 900_000, "max_dimension": 1280, "jpeg_quality": 72},
    "codex": {"max_bytes": 1_800_000, "max_dimension": 1600, "jpeg_quality": 78},
    "codex_cli": {"max_bytes": 1_800_000, "max_dimension": 1600, "jpeg_quality": 78},
}
_UI_REVIEW_ROUTE_PROVIDER_ALIASES = {"llm_router", "multimodal_router"}
_UI_REVIEW_ROUTE_MODEL_ALIASES = {"llm_router", "multimodal_router"}


_UI_REVIEW_LIST_FIELDS = (
    "actor_path_breaks",
    "broken_controls",
    "button_audit",
    "critic_test_obligations",
    "issues",
    "page_reviews",
    "playwright_followups",
    "recommended_changes",
    "route_handoffs",
    "workflow_gaps",
)
_UI_REVIEW_MAPPING_FIELDS = (
    "actor_plan",
    "complaint_journey",
    "critic_review",
    "stage_findings",
)


@dataclass(frozen=True)
class UIReviewPayloadDTO:
    """DTO for model-produced review data before it reaches UI consumers.

    Unknown extension fields pass through unchanged.  Known collection fields are
    guarded at this boundary so templates and report readers do not each need
    their own defensive normalization.
    """

    values: Dict[str, Any]

    @classmethod
    def from_value(cls, value: Any) -> "UIReviewPayloadDTO":
        normalized = dict(value) if isinstance(value, Mapping) else {}
        for field in _UI_REVIEW_LIST_FIELDS:
            if field in normalized and not isinstance(normalized[field], list):
                normalized[field] = []
        for field in _UI_REVIEW_MAPPING_FIELDS:
            if field in normalized:
                normalized[field] = (
                    dict(normalized[field])
                    if isinstance(normalized[field], Mapping)
                    else {}
                )
        return cls(normalized)

    def to_payload(self) -> Dict[str, Any]:
        return dict(self.values)


def normalize_ui_review_payload_dto(value: Any) -> Dict[str, Any]:
    """Normalize one UI review payload through its explicit response DTO."""

    return UIReviewPayloadDTO.from_value(value).to_payload()


def _format_router_backend_path(backend: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("strategy", "provider", "model"):
        value = str((backend or {}).get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return " / ".join(parts)


def _expand_surface_targets(priority_repairs: Iterable[Dict[str, Any]]) -> List[str]:
    targets: List[str] = []
    for item in list(priority_repairs or []):
        raw_target = str((item or {}).get("target_surface") or "").strip()
        if not raw_target:
            continue
        for target in raw_target.split(","):
            normalized = str(target or "").strip().lower()
            if normalized and normalized not in targets:
                targets.append(normalized)
    return targets


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_code_fences(text: str) -> str:
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        parts = stripped.splitlines()
        if parts:
            parts = parts[1:]
        while parts and parts[-1].strip().startswith("```"):
            parts = parts[:-1]
        stripped = "\n".join(parts).strip()
    return stripped


def _truncate_text(value: Any, *, limit: int = _UI_REVIEW_TEXT_ITEM_LIMIT) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 16)].rstrip() + "...[truncated]"


def _parse_json_response(text: str) -> Dict[str, Any]:
    stripped = _strip_code_fences(text)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError) as exc:
        logger.debug("UI review response was not valid JSON; using the structured fallback: %s", exc)
    except Exception:
        logger.warning("Unexpected failure while decoding the UI review response; using the structured fallback", exc_info=True)
    else:
        logger.debug(
            "UI review response decoded as %s instead of an object; using the structured fallback",
            type(parsed).__name__,
        )
    return {
        "summary": "The UI review response was not valid JSON.",
        "issues": [],
        "recommended_changes": [],
        "broken_controls": [],
        "button_audit": [],
        "route_handoffs": [],
        "complaint_journey": {},
        "actor_plan": {},
        "critic_review": {},
        "actor_summary": "",
        "critic_summary": "",
        "actor_path_breaks": [],
        "critic_test_obligations": [],
        "stage_findings": {},
        "raw_response": stripped,
    }


def _normalize_paths(paths: Iterable[str]) -> List[Path]:
    normalized: List[Path] = []
    for item in paths:
        path = Path(str(item)).expanduser().resolve()
        if path.exists():
            normalized.append(path)
    return normalized


def _list_screenshots(screenshot_dir: str) -> List[Path]:
    root = Path(screenshot_dir).expanduser().resolve()
    if not root.exists():
        return []
    candidates: List[Path] = []
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        candidates.extend(sorted(root.glob(pattern)))
    return [item for item in candidates if item.is_file()]


def _screenshot_payload(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for path in paths:
        stat = path.stat()
        payload.append(
            {
                "path": str(path),
                "name": path.name,
                "stem": path.stem,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return payload


def _list_artifact_metadata(screenshot_dir: str) -> List[Dict[str, Any]]:
    root = Path(screenshot_dir).expanduser().resolve()
    if not root.exists():
        return []
    payloads: List[Dict[str, Any]] = []
    for candidate in sorted(root.glob("*.json")):
        try:
            payload = json.loads(candidate.read_text())
        except (OSError, UnicodeError, json.JSONDecodeError):
            logger.debug("Ignoring unreadable UI review artifact metadata at %s", candidate, exc_info=True)
            continue
        except Exception:
            logger.warning("Unexpected failure while reading UI review artifact metadata at %s", candidate, exc_info=True)
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _normalize_artifact_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(Path(text).expanduser().resolve())
    except (OSError, RuntimeError):
        logger.debug("Could not normalize artifact path %r; preserving the original value", text, exc_info=True)
        return text
    except Exception:
        logger.warning("Unexpected failure while normalizing artifact path %r; preserving it", text, exc_info=True)
        return text


def _artifact_matches_screenshot(artifact: Dict[str, Any], screenshot: Path) -> bool:
    screenshot_path = str(screenshot.resolve())
    screenshot_name = screenshot.name
    screenshot_stem = screenshot.stem
    artifact_path = _normalize_artifact_path(artifact.get("screenshot_path"))
    if artifact_path and artifact_path == screenshot_path:
        return True
    for candidate in (
        artifact.get("name"),
        artifact.get("surface"),
        artifact.get("page"),
        artifact.get("artifact_name"),
        artifact.get("title"),
    ):
        text = str(candidate or "").strip()
        if not text:
            continue
        if text == screenshot_name or text == screenshot_stem:
            return True
    return False


def _filter_artifacts_for_page(
    screenshot: Path,
    artifact_metadata: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    page_artifacts: List[Dict[str, Any]] = []
    global_artifacts: List[Dict[str, Any]] = []
    for item in list(artifact_metadata or []):
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        if _artifact_matches_screenshot(copied, screenshot):
            page_artifacts.append(copied)
            continue
        if str(copied.get("artifact_type") or "").strip() == "complaint_export":
            global_artifacts.append(copied)
    return page_artifacts + global_artifacts


def _page_review_unit_label(screenshot: Path, artifact_metadata: Iterable[Dict[str, Any]]) -> str:
    for item in list(artifact_metadata or []):
        if not isinstance(item, dict):
            continue
        for key in ("name", "surface", "page", "artifact_name", "title"):
            value = str(item.get(key) or "").strip()
            if value:
                return value
    return screenshot.stem


def _artifact_priority_score(screenshot: Path, artifact_metadata: Iterable[Dict[str, Any]]) -> int:
    page_artifacts = _filter_artifacts_for_page(screenshot, artifact_metadata)
    score = 0
    artifact_context = " ".join(
        [
            str(((page_artifacts[0] if page_artifacts else {}).get("name") or screenshot.stem)),
            str(((page_artifacts[0] if page_artifacts else {}).get("title") or screenshot.stem)),
            str(((page_artifacts[0] if page_artifacts else {}).get("url") or "")),
            str(((page_artifacts[0] if page_artifacts else {}).get("text_excerpt") or "")),
        ]
    ).lower()
    if "intake" in artifact_context or "chat" in artifact_context:
        stage = "Intake"
    elif "evidence" in artifact_context or "document" in artifact_context:
        stage = "Evidence"
    elif "review" in artifact_context or "support" in artifact_context:
        stage = "Review"
    elif "draft" in artifact_context or "builder" in artifact_context:
        stage = "Draft"
    elif "integration" in artifact_context or "sdk" in artifact_context or "tool" in artifact_context:
        stage = "Integration Discovery"
    else:
        stage = "Workspace"
    stage_bonus = {
        "Intake": 60,
        "Evidence": 55,
        "Review": 50,
        "Draft": 65,
        "Integration Discovery": 45,
        "Workspace": 35,
    }
    score += stage_bonus.get(stage, 20)
    for item in page_artifacts:
        artifact_type = str(item.get("artifact_type") or "").strip()
        if artifact_type == "complaint_export":
            score += 40
        if str(item.get("name") or "").strip().lower().startswith("workspace-"):
            score += 8
        text_excerpt = str(item.get("text_excerpt") or "")
        if "release gate" in text_excerpt.lower():
            score += 20
        if "draft" in text_excerpt.lower():
            score += 12
        if "evidence" in text_excerpt.lower():
            score += 10
        if "review" in text_excerpt.lower():
            score += 8
    return score


def _max_page_reviews_for_provider(provider: Optional[str]) -> int:
    override = str(os.getenv("COMPLAINT_UI_REVIEW_MAX_PAGES", "") or "").strip()
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            logger.debug(
                "Invalid COMPLAINT_UI_REVIEW_MAX_PAGES=%r; using the provider default",
                override,
            )
    normalized = str(provider or "").strip().lower()
    if normalized in {"codex_cli", "codex"}:
        return 4
    return 12


def _select_screenshots_for_review(
    screenshots: List[Path],
    *,
    artifact_metadata: Iterable[Dict[str, Any]],
    provider: Optional[str],
) -> tuple[List[Path], Dict[str, Any]]:
    if len(screenshots) <= 1:
        return list(screenshots), {
            "selected_screenshot_count": len(screenshots),
            "skipped_screenshot_count": 0,
            "selected_screenshots": [path.name for path in screenshots],
            "skipped_screenshots": [],
        }

    max_pages = _max_page_reviews_for_provider(provider)
    ranked = sorted(
        screenshots,
        key=lambda path: (
            -_artifact_priority_score(path, artifact_metadata),
            path.name,
        ),
    )
    selected = ranked[:max_pages]
    skipped = ranked[max_pages:]
    return selected, {
        "selected_screenshot_count": len(selected),
        "skipped_screenshot_count": len(skipped),
        "selected_screenshots": [path.name for path in selected],
        "skipped_screenshots": [path.name for path in skipped],
    }


def _merge_string_list(items: Iterable[Any]) -> List[str]:
    merged: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in merged:
            merged.append(text)
    return merged


def _compact_complaint_output_feedback(
    complaint_output_feedback: Dict[str, Any],
    *,
    suggestion_limit: int = _UI_REVIEW_SUGGESTION_COUNT_LIMIT,
    metadata_limit: int = _UI_REVIEW_METADATA_LIST_LIMIT,
) -> Dict[str, Any]:
    feedback = dict(complaint_output_feedback or {})
    return {
        "export_artifact_count": int(feedback.get("export_artifact_count") or 0),
        "claim_types": [str(item).strip() for item in list(feedback.get("claim_types") or [])[:metadata_limit] if str(item).strip()],
        "draft_strategies": [str(item).strip() for item in list(feedback.get("draft_strategies") or [])[:metadata_limit] if str(item).strip()],
        "filing_shape_scores": [int(item) for item in list(feedback.get("filing_shape_scores") or [])[:metadata_limit]],
        "markdown_filenames": [str(item).strip() for item in list(feedback.get("markdown_filenames") or [])[:metadata_limit] if str(item).strip()],
        "pdf_filenames": [str(item).strip() for item in list(feedback.get("pdf_filenames") or [])[:metadata_limit] if str(item).strip()],
        "release_gate_verdicts": [str(item).strip() for item in list(feedback.get("release_gate_verdicts") or [])[:metadata_limit] if str(item).strip()],
        "formal_section_gaps": [_truncate_text(item, limit=120) for item in list(feedback.get("formal_section_gaps") or [])[:metadata_limit] if str(item).strip()],
        "ui_suggestions": [_truncate_text(item) for item in list(feedback.get("ui_suggestions") or [])[:suggestion_limit] if str(item).strip()],
        "router_backends": [
            {
                "provider": str((item or {}).get("provider") or "").strip(),
                "model": str((item or {}).get("model") or "").strip(),
                "strategy": str((item or {}).get("strategy") or "").strip(),
            }
            for item in list(feedback.get("router_backends") or [])[:metadata_limit]
            if isinstance(item, dict)
        ],
    }


def _provider_image_limits(provider: Optional[str]) -> Dict[str, int]:
    normalized = str(provider or "").strip().lower()
    return dict(_UI_REVIEW_PROVIDER_IMAGE_LIMITS.get(normalized, {}))


def _build_tall_image_review_board(
    image,
    *,
    max_dimension: int,
):
    try:
        from PIL import Image
    except ImportError:
        logger.debug("Pillow is unavailable; skipping tall-image review-board preparation")
        return image
    except Exception:
        logger.warning("Pillow could not be initialized; skipping tall-image review-board preparation", exc_info=True)
        return image

    width, height = image.size
    if max_dimension <= 0 or width <= 0 or height <= 0:
        return image

    ratio = height / float(width)
    if ratio < 2.5 or height <= max_dimension:
        return image

    board_columns = 2
    board_rows = 2
    gutter = 16
    cell_width = max(280, (max_dimension - gutter * (board_columns + 1)) // board_columns)
    segment_height = max(int(width * 0.78), 720)
    max_top = max(0, height - segment_height)
    anchors = [0, max_top // 3, (max_top * 2) // 3, max_top]

    segments = []
    seen = set()
    for anchor in anchors:
        top = min(max(0, int(anchor)), max_top)
        if top in seen:
            continue
        seen.add(top)
        bottom = min(height, top + segment_height)
        crop = image.crop((0, top, width, bottom))
        if crop.mode not in {"RGB", "L"}:
            flattened = Image.new("RGB", crop.size, (255, 255, 255))
            flattened.paste(crop, mask=crop.split()[-1] if "A" in crop.getbands() else None)
            crop = flattened
        elif crop.mode == "L":
            crop = crop.convert("RGB")
        scaled_height = max(1, int(round(crop.height * (cell_width / float(crop.width)))))
        crop = crop.resize((cell_width, scaled_height))
        segments.append(crop)
        if len(segments) >= board_columns * board_rows:
            break

    if len(segments) < 2:
        return image

    row_heights = []
    for row in range(board_rows):
        row_items = segments[row * board_columns : (row + 1) * board_columns]
        if not row_items:
            break
        row_heights.append(max(item.height for item in row_items))

    board_height = gutter
    for row_height in row_heights:
        board_height += row_height + gutter
    board_width = gutter + (cell_width * board_columns) + (gutter * (board_columns - 1)) + gutter
    board = Image.new("RGB", (board_width, board_height), (250, 250, 252))

    y = gutter
    for row, row_height in enumerate(row_heights):
        x = gutter
        row_items = segments[row * board_columns : (row + 1) * board_columns]
        for item in row_items:
            board.paste(item, (x, y))
            x += cell_width + gutter
        y += row_height + gutter
    return board


def _prepare_review_image_copy(
    image_path: Path,
    *,
    output_dir: Path,
    provider: Optional[str],
) -> Path:
    limits = _provider_image_limits(provider)
    if not limits:
        return image_path
    try:
        from PIL import Image
    except ImportError:
        logger.debug("Pillow is unavailable; reviewing the original image at %s", image_path)
        return image_path
    except Exception:
        logger.warning("Pillow could not be initialized; reviewing the original image at %s", image_path, exc_info=True)
        return image_path

    max_bytes = int(limits.get("max_bytes") or 0)
    max_dimension = int(limits.get("max_dimension") or 0)
    jpeg_quality = int(limits.get("jpeg_quality") or 75)

    stat = image_path.stat()
    try:
        with Image.open(image_path) as image:
            width, height = image.size
            if (
                (not max_bytes or stat.st_size <= max_bytes)
                and (not max_dimension or (width <= max_dimension and height <= max_dimension))
            ):
                return image_path

            candidate = image.copy()
            if max_dimension:
                candidate = _build_tall_image_review_board(candidate, max_dimension=max_dimension)
                candidate.thumbnail((max_dimension, max_dimension))
            if candidate.mode not in {"RGB", "L"}:
                flattened = Image.new("RGB", candidate.size, (255, 255, 255))
                flattened.paste(candidate, mask=candidate.split()[-1] if "A" in candidate.getbands() else None)
                candidate = flattened
            elif candidate.mode == "L":
                candidate = candidate.convert("RGB")

            output_dir.mkdir(parents=True, exist_ok=True)
            prepared_path = output_dir / f"{image_path.stem}.review.jpg"
            for quality in (jpeg_quality, max(jpeg_quality - 10, 45), 40):
                candidate.save(prepared_path, format="JPEG", optimize=True, quality=quality)
                if not max_bytes or prepared_path.stat().st_size <= max_bytes:
                    return prepared_path
            if prepared_path.exists() and prepared_path.stat().st_size < stat.st_size:
                return prepared_path
    except Exception:
        logger.warning(
            "Could not prepare optimized UI review image %s; using the original image",
            image_path,
            exc_info=True,
        )
        return image_path
    return image_path


def _prepare_multimodal_image_paths(
    screenshots: List[Path],
    *,
    provider: Optional[str],
    diagnostics_dir: Optional[str],
) -> tuple[List[Path], Dict[str, Any]]:
    prepared_paths: List[Path] = []
    changed_paths: List[str] = []
    limits = _provider_image_limits(provider)
    if not limits:
        return list(screenshots), {"prepared_image_count": 0, "original_screenshot_count": len(screenshots)}

    if diagnostics_dir:
        output_dir = Path(diagnostics_dir).expanduser().resolve() / "prepared-images"
    else:
        output_dir = Path(tempfile.mkdtemp(prefix="complaint-ui-review-images-"))

    for screenshot in list(screenshots or []):
        prepared = _prepare_review_image_copy(
            screenshot,
            output_dir=output_dir,
            provider=provider,
        )
        prepared_paths.append(prepared)
        if prepared != screenshot:
            changed_paths.append(str(prepared))
    return prepared_paths, {
        "prepared_image_count": len(changed_paths),
        "prepared_image_paths": changed_paths,
        "original_screenshot_count": len(screenshots),
    }


def _aggregate_page_review_reports(page_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    summaries = [
        str(((report.get("review") or {}) if isinstance(report.get("review"), dict) else {}).get("summary") or "").strip()
        for report in page_reports
    ]
    summaries = [item for item in summaries if item]
    issues: List[Dict[str, Any]] = []
    recommended_changes: List[Dict[str, Any]] = []
    broken_controls: List[Dict[str, Any]] = []
    button_audit: List[Dict[str, Any]] = []
    route_handoffs: List[Dict[str, Any]] = []
    workflow_gaps: List[str] = []
    playwright_followups: List[str] = []
    actor_path_breaks: List[str] = []
    critic_test_obligations: List[str] = []
    page_backend_paths: List[str] = []
    stage_findings: Dict[str, List[str]] = {}
    tested_stages: List[str] = []
    journey_gaps: List[str] = []
    sdk_tool_invocations: List[str] = []
    release_blockers: List[str] = []

    for report in page_reports:
        review = dict(report.get("review") or {})
        page_label = str(report.get("page_label") or "").strip() or "unknown-page"
        backend = dict(report.get("backend") or {})
        backend_path = _format_router_backend_path(backend)
        if backend_path:
            page_backend_paths.append(f"{page_label}: {backend_path}")

        for collection_name, sink in (
            ("issues", issues),
            ("recommended_changes", recommended_changes),
            ("broken_controls", broken_controls),
        ):
            for item in list(review.get(collection_name) or []):
                if not isinstance(item, dict):
                    continue
                enriched = dict(item)
                enriched.setdefault("page", page_label)
                sink.append(enriched)

        for item in list(review.get("button_audit") or []):
            if not isinstance(item, dict):
                continue
            enriched = dict(item)
            enriched.setdefault("page", page_label)
            button_audit.append(enriched)

        for item in list(review.get("route_handoffs") or []):
            if not isinstance(item, dict):
                continue
            enriched = dict(item)
            enriched.setdefault("page", page_label)
            route_handoffs.append(enriched)

        workflow_gaps.extend(_merge_string_list(review.get("workflow_gaps") or []))
        playwright_followups.extend(_merge_string_list(review.get("playwright_followups") or []))
        actor_path_breaks.extend(_merge_string_list(review.get("actor_path_breaks") or []))
        critic_test_obligations.extend(_merge_string_list(review.get("critic_test_obligations") or []))
        complaint_journey = dict(review.get("complaint_journey") or {})
        tested_stages.extend(_merge_string_list(complaint_journey.get("tested_stages") or []))
        journey_gaps.extend(_merge_string_list(complaint_journey.get("journey_gaps") or []))
        sdk_tool_invocations.extend(_merge_string_list(complaint_journey.get("sdk_tool_invocations") or []))
        release_blockers.extend(_merge_string_list(complaint_journey.get("release_blockers") or []))
        for stage_name, stage_text in dict(review.get("stage_findings") or {}).items():
            cleaned = str(stage_text or "").strip()
            if cleaned:
                stage_findings.setdefault(str(stage_name), []).append(f"{page_label}: {cleaned}")

    stage_findings_payload = {
        stage: " | ".join(entries)
        for stage, entries in stage_findings.items()
        if entries
    }
    aggregate_summary = (
        f"Aggregated {len(page_reports)} page-level screenshot reviews. "
        + (" ".join(summaries[:3]) if summaries else "No page-level summaries were returned.")
    ).strip()
    return {
        "summary": aggregate_summary,
        "issues": issues,
        "recommended_changes": recommended_changes,
        "broken_controls": broken_controls,
        "button_audit": button_audit,
        "route_handoffs": route_handoffs,
        "complaint_journey": {
            "tested_stages": _merge_string_list(tested_stages),
            "journey_gaps": _merge_string_list(journey_gaps),
            "sdk_tool_invocations": _merge_string_list(sdk_tool_invocations),
            "release_blockers": _merge_string_list(release_blockers),
            "page_reviews": [
                {
                    "page": str(report.get("page_label") or "").strip() or "unknown-page",
                    "summary": str((dict(report.get("review") or {})).get("summary") or "").strip(),
                    "backend": dict(report.get("backend") or {}),
                }
                for report in page_reports
            ],
            "router_paths": page_backend_paths,
        },
        "actor_plan": {
            "page_repair_sequence": [
                {
                    "page": str(report.get("page_label") or "").strip() or "unknown-page",
                    "top_recommendations": [
                        str((item or {}).get("title") or (item or {}).get("recommended_fix") or "").strip()
                        for item in list((dict(report.get("review") or {})).get("recommended_changes") or [])[:3]
                        if isinstance(item, dict)
                    ],
                }
                for report in page_reports
            ]
        },
        "critic_review": {
            "verdict": "warning" if issues or broken_controls else "pass",
            "blocking_findings": _merge_string_list(
                item.get("problem") or item.get("failure_mode") or ""
                for item in issues + broken_controls
                if isinstance(item, dict)
            )[:8],
            "acceptance_checks": _merge_string_list(critic_test_obligations or playwright_followups)[:8],
        },
        "actor_summary": aggregate_summary,
        "critic_summary": (
            f"Parallel page review completed across {len(page_reports)} page calls. "
            f"Collected {len(issues)} issues and {len(recommended_changes)} recommended changes."
        ),
        "actor_path_breaks": _merge_string_list(actor_path_breaks),
        "critic_test_obligations": _merge_string_list(critic_test_obligations),
        "stage_findings": stage_findings_payload,
        "workflow_gaps": _merge_string_list(workflow_gaps),
        "playwright_followups": _merge_string_list(playwright_followups),
        "page_reviews": [
            {
                "page": str(report.get("page_label") or "").strip() or "unknown-page",
                "backend": dict(report.get("backend") or {}),
                "summary": str((dict(report.get("review") or {})).get("summary") or "").strip(),
                "issues_count": len(list((dict(report.get("review") or {})).get("issues") or [])),
                "recommended_changes_count": len(list((dict(report.get("review") or {})).get("recommended_changes") or [])),
            }
            for report in page_reports
        ],
    }


def _run_page_review_task(task: Dict[str, Any]) -> Dict[str, Any]:
    screenshot = str(task.get("screenshot") or "").strip()
    if not screenshot:
        raise ValueError("Page review task is missing screenshot")
    page_report = create_ui_review_report(
        [screenshot],
        notes=task.get("notes"),
        goals=list(task.get("goals") or []),
        provider=task.get("provider"),
        model=task.get("model"),
        config_path=task.get("config_path"),
        backend_id=task.get("backend_id"),
        output_path=None,
        diagnostics_dir=task.get("diagnostics_dir"),
        artifact_metadata=list(task.get("artifact_metadata") or []),
        compact_page_prompt=bool(task.get("compact_page_prompt", True)),
        page_review_executor="inline",
    )
    payload = dict(page_report or {})
    payload["page_label"] = str(task.get("page_label") or "").strip() or Path(screenshot).stem
    return payload


def _summarize_complaint_output_feedback(artifact_metadata: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    exports = [
        dict(item)
        for item in list(artifact_metadata or [])
        if isinstance(item, dict) and str(item.get("artifact_type") or "") == "complaint_export"
    ]
    suggestions = [
        str(item.get("ui_suggestions_excerpt") or "").strip()
        for item in exports
        if str(item.get("ui_suggestions_excerpt") or "").strip()
    ]
    router_backends = [
        dict(item.get("router_backend") or {})
        for item in exports
        if isinstance(item.get("router_backend"), dict) and item.get("router_backend")
    ]
    return {
        "export_artifact_count": len(exports),
        "claim_types": [
            str(item.get("claim_type") or "").strip()
            for item in exports
            if str(item.get("claim_type") or "").strip()
        ],
        "draft_strategies": [
            str(item.get("draft_strategy") or "").strip()
            for item in exports
            if str(item.get("draft_strategy") or "").strip()
        ],
        "filing_shape_scores": [
            int(item.get("filing_shape_score") or 0)
            for item in exports
            if item.get("filing_shape_score") is not None
        ],
        "markdown_filenames": [
            str(item.get("markdown_filename") or "").strip()
            for item in exports
            if str(item.get("markdown_filename") or "").strip()
        ],
        "pdf_filenames": [
            str(item.get("pdf_filename") or "").strip()
            for item in exports
            if str(item.get("pdf_filename") or "").strip()
        ],
        "release_gate_verdicts": [
            str(((item.get("release_gate") or {}) if isinstance(item.get("release_gate"), dict) else {}).get("verdict") or "").strip()
            for item in exports
            if str(((item.get("release_gate") or {}) if isinstance(item.get("release_gate"), dict) else {}).get("verdict") or "").strip()
        ],
        "formal_section_gaps": [
            str(item)
            for export in exports
            for item in list(export.get("formal_section_gaps") or [])
            if str(item).strip()
        ],
        "ui_suggestions": suggestions,
        "router_backends": router_backends,
    }


def _fallback_complaint_output_review(export: Dict[str, Any], error: Exception) -> Dict[str, Any]:
    router_review = dict(export.get("router_export_critic") or {}) if isinstance(export.get("router_export_critic"), dict) else {}
    missing_formal_sections = [
        str(item).strip()
        for item in list(export.get("formal_section_gaps") or [])
        if str(item).strip()
    ]
    issue_findings = [
        {
            "severity": "high" if int(export.get("filing_shape_score") or 0) < 75 else "medium",
            "finding": str(router_review.get("summary") or "Router-backed complaint-output review was unavailable, so the export metadata is being used as the fallback critic.").strip(),
            "complaint_impact": str(((export.get("release_gate") or {}) if isinstance(export.get("release_gate"), dict) else {}).get("blocking_reason") or "The complaint export may still have filing-shape defects that should remain visible in the UI.").strip(),
            "ui_implication": "Draft and export surfaces should keep filing-shape warnings visible when router review is unavailable.",
        }
    ]
    ui_suggestions = [
        dict(item)
        for item in list(router_review.get("ui_suggestions") or [])
        if isinstance(item, dict)
    ]
    if not ui_suggestions:
        ui_suggestions = [
            {
                "title": "Keep complaint-output warnings visible before download",
                "target_surface": "draft",
                "recommendation": str(export.get("ui_suggestions_excerpt") or "Preserve filing-shape warnings, release-gate status, and export guidance whenever router review is unavailable.").strip(),
                "why_it_matters": "The generated complaint should not look filing-ready if the export metadata already shows unresolved structural gaps.",
            }
        ]
    ui_priority_repairs = [
        dict(item)
        for item in list(router_review.get("ui_priority_repairs") or [])
        if isinstance(item, dict)
    ]
    if not ui_priority_repairs and missing_formal_sections:
        ui_priority_repairs = [
            {
                "priority": "high",
                "target_surface": "draft",
                "repair": f"Keep {missing_formal_sections[0]} guidance visible before export.",
                "filing_benefit": "The complaint stays closer to a formal filing even when router critique is temporarily unavailable.",
            }
        ]
    release_gate = dict(export.get("release_gate") or {}) if isinstance(export.get("release_gate"), dict) else {}
    critic_gate = dict(router_review.get("critic_gate") or {}) if isinstance(router_review.get("critic_gate"), dict) else {}
    if not critic_gate:
        critic_gate = {
            "verdict": str(release_gate.get("verdict") or ("warning" if missing_formal_sections else "pass")).strip() or "warning",
            "blocking_reason": str(release_gate.get("blocking_reason") or str(error) or "Router-backed complaint review was unavailable.").strip(),
            "required_repairs": list(release_gate.get("required_repairs") or []) if isinstance(release_gate.get("required_repairs"), list) else [],
        }
    summary = str(router_review.get("summary") or "Complaint export review used artifact metadata fallback because router-backed critique was unavailable.").strip()
    actor_risk_summary = str(router_review.get("actor_risk_summary") or critic_gate.get("blocking_reason") or "A complainant could mistake the export for a filing-ready complaint while router-backed QA is offline.").strip()
    return {
        "backend": {
            "id": "complaint-output-review-fallback",
            "provider": "artifact_metadata",
            "model": "deterministic-fallback",
            "strategy": "artifact_metadata_fallback",
            "fallback_from": "llm_router",
            "error": str(error),
        },
        "review": {
            "summary": summary,
            "filing_shape_score": int(export.get("filing_shape_score") or 0),
            "claim_type_alignment_score": int(export.get("claim_type_alignment_score") or 0),
            "strengths": [
                str(item).strip()
                for item in list(router_review.get("strengths") or [])
                if str(item).strip()
            ],
            "missing_formal_sections": missing_formal_sections,
            "issues": issue_findings,
            "ui_suggestions": ui_suggestions,
            "ui_priority_repairs": ui_priority_repairs,
            "actor_risk_summary": actor_risk_summary,
            "critic_gate": critic_gate,
            "raw_response": str(error),
        },
    }


def _deterministic_ui_review_fallback(
    *,
    screenshots: List[Path],
    artifact_metadata: List[Dict[str, Any]],
    complaint_output_feedback: Dict[str, Any],
    multimodal_error: Exception | None,
    fallback_error: Exception,
) -> Dict[str, Any]:
    def _compact_hint(value: str, fallback: str) -> str:
        text = str(value or "").strip()
        if not text:
            return fallback
        first_block = text.split("{", 1)[0].strip()
        first_line = first_block.splitlines()[0].strip() if first_block else ""
        compact = first_line or text[:220].strip()
        return compact[:220].rstrip() or fallback

    screenshot_labels = [
        _page_review_unit_label(path, _filter_artifacts_for_page(path, artifact_metadata))
        for path in screenshots[:6]
    ]
    screenshot_labels = [label for label in screenshot_labels if label]
    export_artifacts = [
        dict(item)
        for item in list(artifact_metadata or [])
        if isinstance(item, dict) and str(item.get("artifact_type") or "").strip() == "complaint_export"
    ]
    release_verdicts = [
        verdict
        for verdict in list(complaint_output_feedback.get("release_gate_verdicts") or [])
        if str(verdict).strip()
    ]
    formal_section_gaps = [
        str(item).strip()
        for item in list(complaint_output_feedback.get("formal_section_gaps") or [])
        if str(item).strip()
    ]
    ui_suggestion_hints = [
        str(item).strip()
        for item in list(complaint_output_feedback.get("ui_suggestions") or [])
        if str(item).strip()
    ]
    avg_shape = 0
    shape_scores = [int(item) for item in list(complaint_output_feedback.get("filing_shape_scores") or []) if int(item or 0) > 0]
    if shape_scores:
        avg_shape = round(sum(shape_scores) / len(shape_scores))

    if export_artifacts:
        summary = (
            "Router-driven UI review timed out, so an artifact-backed actor/critic fallback was created from the audited complaint exports "
            "and page screenshots."
        )
        primary_fix = _compact_hint(ui_suggestion_hints[0], (
            "Keep filing-shape warnings, release-gate status, and export guidance visible before download."
        )) if ui_suggestion_hints else (
            "Keep filing-shape warnings, release-gate status, and export guidance visible before download."
        )
        issues = [
            {
                "severity": "medium" if avg_shape >= 75 else "high",
                "surface": "draft/export",
                "problem": "Live screenshot critique timed out before the actor/critic loop could validate the final complaint surfaces.",
                "user_impact": "A complainant could move toward export without seeing the strongest filing-shape warnings or next-step guidance.",
                "recommended_fix": primary_fix,
            }
        ]
        recommended_changes = [
            {
                "title": "Use complaint-output signals as the first fallback UX critic",
                "implementation_notes": (
                    "When router-backed screenshot review is slow, surface filing-shape scores, release-gate verdicts, "
                    "and export guidance directly in the UI review report instead of falling back to a generic timeout warning."
                ),
                "shared_code_path": "applications/ui_review.py",
                "sdk_considerations": "Preserve complaint.review_ui and complaint.optimize_ui so the browser SDK can still return actionable guidance.",
            }
        ]
        recommended_changes.extend(
            {
                "title": f"Keep {gap.replace('_', ' ')} guidance visible before export",
                "implementation_notes": f"Expose a persistent warning in the draft/export surfaces when {gap.replace('_', ' ')} is still weak or missing.",
                "shared_code_path": "templates/workspace.html",
                "sdk_considerations": "Keep the release gate and export analysis panels visible beside SDK-triggered download actions.",
            }
            for gap in formal_section_gaps[:2]
        )
        broken_controls = [
            {
                "surface": "draft/export",
                "control": "UI review automation",
                "failure_mode": "Live multimodal/text router review timed out for the screenshot set.",
                "repair": "Use export-artifact guidance as the immediate fallback and keep the actor/critic loop attached to the audited complaint packet.",
            }
        ]
        broken_controls.extend(
            {
                "surface": label,
                "control": "release gate / export guidance",
                "failure_mode": "This surface needs a stronger visible handoff into filing-quality warnings when router review is slow.",
                "repair": primary_fix,
            }
            for label in screenshot_labels[:3]
        )
        return {
            "summary": summary,
            "issues": issues,
            "recommended_changes": recommended_changes,
            "broken_controls": broken_controls,
            "complaint_journey": {
                "tested_stages": ["intake", "evidence", "review", "draft", "integrations", "optimizer"],
                "journey_gaps": [
                    "Live screenshot critique timed out, so the fallback is relying on audited complaint-output signals instead of fresh visual reasoning.",
                ],
                "sdk_tool_invocations": ["complaint.review_ui", "complaint.optimize_ui", "complaint.run_browser_audit"],
                "release_blockers": [
                    primary_fix,
                    *[f"Keep {gap.replace('_', ' ')} guidance visible before export." for gap in formal_section_gaps[:2]],
                ],
            },
            "actor_plan": {
                "primary_objective": "Keep export and filing-quality warnings visible even when screenshot review is slow.",
                "repair_sequence": [
                    primary_fix,
                    *[f"Surface {gap.replace('_', ' ')} status in the draft/export sidebar." for gap in formal_section_gaps[:2]],
                    "Retry multimodal screenshot review after the audited export artifacts are attached.",
                ],
                "playwright_objectives": [
                    "Keep end-to-end assertions for complaint generation, markdown/pdf/docx download, and release-gate visibility before export.",
                ],
                "mcp_sdk_expectations": [
                    "The browser UI should continue to expose complaint.review_ui, complaint.optimize_ui, and export/download SDK actions as first-class controls.",
                ],
            },
            "actor_summary": "The actor can still complete the complaint journey, but the optimizer had to fall back to complaint-output evidence instead of live screenshot reasoning.",
            "critic_summary": "The critic accepts the audited journey data, while flagging router latency as the main remaining risk to the actor/critic loop.",
            "actor_path_breaks": [
                "The screenshot review loop can time out before returning page-specific UX findings.",
            ],
            "critic_test_obligations": [
                "Keep a Playwright flow that proves the release gate and filing-shape guidance stay visible before markdown/pdf/docx download.",
            ],
            "stage_findings": {
                "Intake": "The intake route is covered by the browser audit, but live screenshot critique timed out before it could produce page-specific findings.",
                "Evidence": "Evidence capture appears connected in the browser audit; preserve that continuity when export warnings are shown.",
                "Review": "Support review should continue to surface claim gaps before users rely on the generated complaint.",
                "Draft": primary_fix,
                "Integration Discovery": "Keep MCP/SDK tooling visibility tied to the same release-gate and export-quality diagnostics.",
            },
            "workflow_gaps": [
                "Live screenshot review timed out and had to rely on complaint-output artifacts.",
            ],
            "playwright_followups": [
                "Capture and assert the release gate, filing-shape score, and export guidance in the final draft/export view.",
            ],
            "ui_suggestions": [
                {
                    "title": "Keep filing-quality cues visible when router review is slow",
                    "target_surface": "draft,integrations",
                    "recommendation": primary_fix,
                    "why_it_matters": "The actor should still see filing-shape and release-gate guidance before export even if the screenshot critic is unavailable.",
                }
            ],
        }

    return {
        "summary": "Router-driven UI review was unavailable, so a fallback implementation report was created.",
        "issues": [
            {
                "severity": "medium",
                "surface": "shared complaint workflow",
                "problem": "No live router critique was available for the screenshots.",
                "user_impact": "UI review can stall unless there is a safe fallback path.",
                "recommended_fix": "Restore multimodal router access or provide richer page context so screenshot review remains actionable.",
            }
        ],
        "recommended_changes": [
            {
                "title": "Keep the review loop artifact-driven",
                "implementation_notes": "Continue generating Playwright screenshots and route them through this workflow so UI changes stay evidence-based.",
                "shared_code_path": "applications/ui_review.py",
                "sdk_considerations": "Preserve MCP SDK usage in the first-class app surfaces while the visuals evolve.",
            }
        ],
        "broken_controls": [
            {
                "surface": "shared complaint workflow",
                "control": "UI review automation",
                "failure_mode": "No live router critique was returned for the screenshot set.",
                "repair": "Restore multimodal or text router access so screenshot-driven actor/critic review can run.",
            }
        ],
        "complaint_journey": {
            "tested_stages": ["optimizer"],
            "journey_gaps": ["No live router response was available to assess the end-to-end complaint journey."],
            "sdk_tool_invocations": ["complaint.review_ui", "complaint.optimize_ui"],
            "release_blockers": ["Restore screenshot review routing before trusting the automated UI gate."],
        },
        "actor_plan": {
            "primary_objective": "Keep the screenshot-driven UI loop alive with artifact-backed reviews.",
            "repair_sequence": [
                "Restore multimodal router access.",
                "Fallback to text router when images are unavailable.",
                "Keep Playwright screenshot artifacts attached to each review cycle.",
            ],
            "playwright_objectives": [
                "Capture landing, chat, workspace, review, and builder screens after each UI pass.",
            ],
            "mcp_sdk_expectations": [
                "Preserve the complaint.review_ui and complaint.optimize_ui MCP SDK path.",
            ],
        },
        "actor_summary": "The actor journey cannot be validated from screenshots until router-backed review returns.",
        "critic_summary": "The critic sees the missing router response itself as a release blocker for the UI optimization loop.",
        "actor_path_breaks": [
            "The review loop cannot confirm that a user can move from intake to evidence to review to draft without getting lost.",
        ],
        "critic_test_obligations": [
            "Keep a Playwright journey that covers testimony, evidence upload, support review, and final complaint generation.",
        ],
        "stage_findings": {
            "Intake": "No live actor/critic screenshot review was available for intake.",
            "Evidence": "No live actor/critic screenshot review was available for evidence handling.",
            "Review": "No live actor/critic screenshot review was available for support review.",
            "Draft": "No live actor/critic screenshot review was available for drafting.",
            "Integration Discovery": "No live actor/critic screenshot review was available for the shared MCP SDK tooling surfaces.",
        },
        "critic_review": {
            "verdict": "warning",
            "blocking_findings": [
                "The actor/critic optimizer cannot fully evaluate the complaint UI until router review is restored.",
            ],
            "acceptance_checks": [
                "A screenshot set can be reviewed through multimodal or text router fallback.",
            ],
        },
        "workflow_gaps": [
            "No automated multimodal or text router response was returned for the screenshot set.",
        ],
        "playwright_followups": [
            "Capture screenshots for workspace, document builder, review dashboard, and editor after each UI pass.",
        ],
        "ui_suggestions": [],
    }


def review_complaint_export_artifacts(
    artifact_metadata: Iterable[Dict[str, Any]],
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    exports = [
        dict(item)
        for item in list(artifact_metadata or [])
        if isinstance(item, dict) and str(item.get("artifact_type") or "") == "complaint_export"
    ]
    if not exports:
        raise ValueError("No complaint_export artifacts were provided for complaint-output review.")

    reviews: List[Dict[str, Any]] = []
    filing_shape_scores: List[int] = []
    alignment_scores: List[int] = []
    aggregate_issue_findings: List[str] = []
    aggregate_ui_suggestions: List[Dict[str, Any]] = []
    aggregate_missing_formal_sections: List[str] = []
    aggregate_priority_repairs: List[Dict[str, Any]] = []
    actor_risk_summaries: List[str] = []
    critic_gates: List[Dict[str, Any]] = []
    router_backends: List[Dict[str, Any]] = []

    for export in exports:
        markdown_text = str(export.get("markdown_excerpt") or export.get("text_excerpt") or "").strip()
        if not markdown_text:
            continue
        try:
            review_payload = review_complaint_output_with_llm_router(
                markdown_text,
                claim_type=str(export.get("claim_type") or "").strip() or None,
                claim_guidance=None,
                synopsis=str(export.get("case_synopsis") or "").strip() or None,
                provider=provider,
                model=model,
                config_path=config_path,
                backend_id=backend_id,
                notes=notes,
            )
        except Exception as error:
            logger.warning(
                "Complaint-output review failed for export %r; using deterministic review feedback",
                export.get("name") or export.get("filename") or export.get("claim_type") or "unknown",
                exc_info=True,
            )
            review_payload = _fallback_complaint_output_review(export, error)
        review = dict(review_payload.get("review") or {})
        filing_shape_scores.append(int(review.get("filing_shape_score") or 0))
        alignment_scores.append(int(review.get("claim_type_alignment_score") or 0))
        aggregate_issue_findings.extend(
            str(item.get("finding") or "").strip()
            for item in list(review.get("issues") or [])
            if isinstance(item, dict) and str(item.get("finding") or "").strip()
        )
        aggregate_missing_formal_sections.extend(
            str(item).strip()
            for item in list(review.get("missing_formal_sections") or [])
            if str(item).strip()
        )
        aggregate_ui_suggestions.extend(
            [dict(item) for item in list(review.get("ui_suggestions") or []) if isinstance(item, dict)]
        )
        aggregate_priority_repairs.extend(
            [dict(item) for item in list(review.get("ui_priority_repairs") or []) if isinstance(item, dict)]
        )
        if str(review.get("actor_risk_summary") or "").strip():
            actor_risk_summaries.append(str(review.get("actor_risk_summary") or "").strip())
        if isinstance(review.get("critic_gate"), dict):
            critic_gates.append(dict(review.get("critic_gate") or {}))
        backend_payload = dict(review_payload.get("backend") or {})
        if backend_payload:
            router_backends.append(backend_payload)
        reviews.append(
            {
                "artifact": {
                    "claim_type": export.get("claim_type"),
                    "draft_strategy": export.get("draft_strategy"),
                    "markdown_filename": export.get("markdown_filename"),
                    "pdf_filename": export.get("pdf_filename"),
                },
                "backend": dict(review_payload.get("backend") or {}),
                "review": review,
            }
        )

    return {
        "generated_at": _utc_now(),
        "artifact_count": len(exports),
        "artifact_metadata": exports,
        "complaint_output_feedback": _summarize_complaint_output_feedback(exports),
        "reviews": reviews,
        "aggregate": {
            "average_filing_shape_score": round(sum(filing_shape_scores) / len(filing_shape_scores))
            if filing_shape_scores
            else 0,
            "average_claim_type_alignment_score": round(sum(alignment_scores) / len(alignment_scores))
            if alignment_scores
            else 0,
            "issue_findings": aggregate_issue_findings,
            "missing_formal_sections": sorted({item for item in aggregate_missing_formal_sections if item}),
            "ui_suggestions": aggregate_ui_suggestions,
            "ui_priority_repairs": aggregate_priority_repairs,
            "actor_risk_summaries": actor_risk_summaries,
            "critic_gates": critic_gates,
            "router_backends": router_backends,
            "optimizer_repair_brief": {
                "top_formal_section_gaps": sorted({item for item in aggregate_missing_formal_sections if item})[:6],
                "top_issue_findings": aggregate_issue_findings[:6],
                "recommended_surface_targets": _expand_surface_targets(aggregate_priority_repairs[:6]),
                "actor_risk_summary": actor_risk_summaries[0] if actor_risk_summaries else "",
                "critic_gate_verdict": str((critic_gates[0] or {}).get("verdict") or "").strip() if critic_gates else "",
                "router_path_summary": (
                    " | ".join(
                        path
                        for path in (_format_router_backend_path(item) for item in router_backends[:3])
                        if path
                    )
                    if router_backends
                    else ""
                ),
            },
        },
    }


def _parse_complaint_output_json_response(text: str) -> Dict[str, Any]:
    parsed = _parse_json_response(text)
    return {
        "summary": str(parsed.get("summary") or "No router summary returned."),
        "filing_shape_score": int(parsed.get("filing_shape_score") or 0),
        "claim_type_alignment_score": int(parsed.get("claim_type_alignment_score") or 0),
        "strengths": [str(item) for item in list(parsed.get("strengths") or []) if str(item).strip()],
        "missing_formal_sections": [str(item) for item in list(parsed.get("missing_formal_sections") or []) if str(item).strip()],
        "issues": [dict(item) for item in list(parsed.get("issues") or []) if isinstance(item, dict)],
        "ui_suggestions": [dict(item) for item in list(parsed.get("ui_suggestions") or []) if isinstance(item, dict)],
        "ui_priority_repairs": [dict(item) for item in list(parsed.get("ui_priority_repairs") or []) if isinstance(item, dict)],
        "actor_risk_summary": str(parsed.get("actor_risk_summary") or "").strip(),
        "critic_gate": dict(parsed.get("critic_gate") or {}) if isinstance(parsed.get("critic_gate"), dict) else {},
        "raw_response": parsed.get("raw_response"),
    }


def build_complaint_output_review_prompt(
    markdown_text: str,
    *,
    claim_type: Optional[str] = None,
    claim_guidance: Optional[str] = None,
    synopsis: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    excerpt = str(markdown_text or "").strip()
    if len(excerpt) > 12000:
        excerpt = excerpt[:12000] + "\n...[truncated]..."
    return (
        "You are reviewing a generated lawsuit complaint draft and must decide whether it actually reads like a formal legal complaint.\n"
        "Use the complaint text as the primary artifact.\n"
        "Focus on formal complaint structure, caption quality, jurisdiction and venue allegations, party allegations, factual chronology, claim counts, prayer for relief, jury demand, signature posture, and exhibit grounding.\n"
        "Also decide whether the complaint actually reads like the selected claim type, instead of a generic complaint template.\n"
        f"Selected claim type:\n{claim_type or 'Not provided.'}\n\n"
        f"Claim-type filing guidance:\n{claim_guidance or 'No claim-specific guidance was provided.'}\n\n"
        f"Shared case synopsis:\n{synopsis or 'No case synopsis was provided.'}\n\n"
        "Then turn those filing-shape defects into concrete UI/UX repair suggestions for the complaint generator.\n\n"
        f"Additional notes:\n{notes or 'No additional notes were provided.'}\n\n"
        "Return strict JSON with this shape:\n"
        "{\n"
        '  "summary": "short paragraph",\n'
        '  "filing_shape_score": 0,\n'
        '  "claim_type_alignment_score": 0,\n'
        '  "strengths": ["what already feels filing-shaped"],\n'
        '  "missing_formal_sections": ["caption|jurisdiction_and_venue|factual_allegations|claim_count|prayer_for_relief|signature_block"],\n'
        '  "issues": [\n'
        "    {\n"
        '      "severity": "high|medium|low",\n'
        '      "finding": "what makes the complaint feel non-formal or weak",\n'
        '      "complaint_impact": "why this harms the filing artifact",\n'
        '      "ui_implication": "which UI stage likely caused the weakness"\n'
        "    }\n"
        "  ],\n"
        '  "ui_suggestions": [\n'
        "    {\n"
        '      "title": "repair title",\n'
        '      "target_surface": "intake|evidence|review|draft|integrations",\n'
        '      "recommendation": "what UI/UX should change to produce a stronger complaint",\n'
        '      "why_it_matters": "how this improves the final filing"\n'
        "    }\n"
        "  ],\n"
        '  "ui_priority_repairs": [\n'
        "    {\n"
        '      "priority": "high|medium|low",\n'
        '      "target_surface": "intake|evidence|review|draft|integrations",\n'
        '      "repair": "most important UI change to strengthen the filing",\n'
        '      "filing_benefit": "how the complaint artifact improves"\n'
        "    }\n"
        "  ],\n"
        '  "actor_risk_summary": "how a real complainant ends up with a weak filing because of the current UI",\n'
        '  "critic_gate": {\n'
        '    "verdict": "pass|warning|fail",\n'
        '    "blocking_reason": "why the export should or should not be trusted",\n'
        '    "required_repairs": ["what must be fixed before treating the export as client-safe"]\n'
        "  }\n"
        "}\n\n"
        "Complaint draft:\n"
        f"{excerpt}\n"
    )


def review_complaint_output_with_llm_router(
    markdown_text: str,
    *,
    claim_type: Optional[str] = None,
    claim_guidance: Optional[str] = None,
    synopsis: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    prompt = build_complaint_output_review_prompt(
        markdown_text,
        claim_type=claim_type,
        claim_guidance=claim_guidance,
        synopsis=synopsis,
        notes=notes,
    )
    backend_kwargs = _load_backend_kwargs(config_path, backend_id)
    if provider:
        backend_kwargs["provider"] = provider
    if model:
        backend_kwargs["model"] = model
    backend_kwargs.setdefault(
        "timeout",
        _complaint_output_review_timeout_for_provider(backend_kwargs.get("provider")),
    )
    backend_kwargs.setdefault("allow_local_fallback", False)
    backend_kwargs.setdefault("retry_max_attempts", 1)
    backend = LLMRouterBackend(**backend_kwargs)
    raw_response = backend(prompt)
    return {
        "review": _parse_complaint_output_json_response(raw_response),
        "backend": {
            "id": backend.id,
            "provider": backend.provider,
            "model": backend.model,
            "strategy": "llm_router",
        },
    }


def build_ui_review_prompt(
    screenshots: Iterable[Path],
    *,
    notes: Optional[str] = None,
    goals: Optional[List[str]] = None,
    artifact_metadata: Optional[List[Dict[str, Any]]] = None,
    include_full_contract_context: bool = True,
) -> str:
    screenshot_list = _screenshot_payload(screenshots)
    goal_lines = goals or [
        "Make the complaint generator easier for a first-time complainant to complete without legal jargon fatigue.",
        "Prefer one shared application framework and common code paths across the first-class pages.",
        "Use the JavaScript MCP SDK rather than page-specific ad hoc fetch logic whenever possible.",
        "Make the intake, evidence, support review, and draft editing journey feel linear and trustworthy.",
    ]
    complaint_feedback = _compact_complaint_output_feedback(
        _summarize_complaint_output_feedback(artifact_metadata or [])
    )
    if not include_full_contract_context:
        screenshot_names = ", ".join(item.get("name", "") for item in screenshot_list if item.get("name")) or "single-page-screenshot"
        feedback_excerpt = ", ".join(_merge_string_list(complaint_feedback.get("ui_suggestions") or [])[:3])
        return (
            "Look at this complaint-generator page screenshot and return strict JSON.\n"
            "Focus only on visible UI/UX problems in this single page.\n"
            "Preserve the shared ComplaintMcpClient / MCP workflow when suggesting repairs.\n\n"
            "Screenshot artifacts:\n"
            f"- Screenshot file(s): {screenshot_names}\n"
            f"Additional notes: {notes or 'None.'}\n"
            f"Complaint-output hints: {feedback_excerpt or 'None.'}\n\n"
            "Return strict JSON with this shape:\n"
            "{\n"
            '  "summary": "short paragraph",\n'
            '  "issues": [\n'
            "    {\n"
            '      "severity": "high|medium|low",\n'
            '      "surface": "page guess",\n'
            '      "problem": "visible issue",\n'
            '      "user_impact": "why it hurts the actor",\n'
            '      "recommended_fix": "specific repair"\n'
            "    }\n"
            "  ],\n"
            '  "recommended_changes": [\n'
            "    {\n"
            '      "title": "repair title",\n'
            '      "implementation_notes": "specific implementation guidance",\n'
            '      "shared_code_path": "likely code path",\n'
            '      "sdk_considerations": "how to preserve ComplaintMcpClient / MCP flow"\n'
            "    }\n"
            "  ],\n"
            '  "broken_controls": [\n'
            "    {\n"
            '      "surface": "page guess",\n'
            '      "control": "button or link label",\n'
            '      "failure_mode": "what looks broken or misleading",\n'
            '      "repair": "how to fix it"\n'
            "    }\n"
            "  ],\n"
            '  "workflow_gaps": ["missing affordance"],\n'
            '  "playwright_followups": ["assertion or screenshot to add"],\n'
            '  "stage_findings": {\n'
            '    "Intake": "finding",\n'
            '    "Evidence": "finding",\n'
            '    "Review": "finding",\n'
            '    "Draft": "finding",\n'
            '    "Integration Discovery": "finding"\n'
            "  }\n"
            "}\n"
        )
    contract_surfaces = (
        "Contract surfaces that must remain coherent:\n"
        "- Package exports in complaint_generator, including start_session, submit_intake_answers, save_evidence, review_case, build_mediator_prompt, generate_complaint, update_draft, export_complaint_packet, export_complaint_markdown, export_complaint_pdf, and update_case_synopsis\n"
        "- CLI tools like complaint-generator and complaint-workspace, including review-ui, optimize-ui, and browser-audit\n"
        "- MCP server tools such as complaint.start_session, complaint.build_mediator_prompt, complaint.export_complaint_packet, complaint.export_complaint_markdown, complaint.export_complaint_pdf, complaint.review_ui, complaint.optimize_ui, and complaint.run_browser_audit\n"
        "- Browser SDK usage through window.ComplaintMcpSdk.ComplaintMcpClient, including optimizeUiArtifacts() and runBrowserAudit()\n\n"
    )
    compact_contract_surfaces = (
        "Keep the MCP/browser contract visible while reviewing this page:\n"
        "- preserve ComplaintMcpClient usage\n"
        "- preserve complaint.review_ui / complaint.optimize_ui / complaint.run_browser_audit paths\n"
        "- record any button or handoff that looks actionable but breaks the complaint journey\n\n"
    )
    prompt_prefix = (
        "You are reviewing the UI/UX of a complaint-generator web application for real complainants.\n"
        "The screenshots below were created by Playwright during regression testing.\n"
        "Use the screenshots as the primary source artifacts for review.\n"
        "Pay special attention to trauma-informed language, complaint-intake clarity, evidence capture, next-step guidance, layout coherence, and whether the site visibly uses a shared JavaScript MCP SDK workflow.\n\n"
        "Apply an explicit actor / critic method.\n"
        "Actor: a real complainant or complaint operator trying to complete intake, provide testimony, upload evidence, review claims, and finish the complaint.\n"
        "Critic: a hostile QA reviewer looking for broken buttons, dead navigation, hidden MCP SDK flows, and missing Playwright assertions.\n\n"
        f"Goals:\n- " + "\n- ".join(goal_lines) + "\n\n"
        f"Additional notes:\n{notes or 'No additional notes were provided.'}\n\n"
    )
    prompt_prefix += contract_surfaces if include_full_contract_context else compact_contract_surfaces
    return (
        prompt_prefix
        +
        "Treat every visible button, tab, CTA, and handoff link as part of the release contract. If a control looks actionable but does not move the user to the next valid complaint step, record it as broken.\n\n"
        "Screenshot artifacts:\n"
        f"{json.dumps(screenshot_list, indent=2, sort_keys=True)}\n\n"
        "Complaint export artifacts:\n"
        f"{json.dumps(complaint_feedback, indent=2, sort_keys=True)}\n\n"
        "If complaint export artifacts are present, use them to explain how the generated filing exposes missing warnings, weak validation, confusing handoffs, or unclear drafting guidance in the UI.\n\n"
        "Return strict JSON with this shape:\n"
        "{\n"
        '  "summary": "short paragraph",\n'
        '  "issues": [\n'
        "    {\n"
        '      "severity": "high|medium|low",\n'
        '      "surface": "page or route guess",\n'
        '      "problem": "what is confusing or broken",\n'
        '      "user_impact": "why it matters for complainants",\n'
        '      "recommended_fix": "concrete implementation direction"\n'
        "    }\n"
        "  ],\n"
        '  "recommended_changes": [\n'
        "    {\n"
        '      "title": "change name",\n'
        '      "implementation_notes": "specific code-level guidance",\n'
        '      "shared_code_path": "where to centralize the logic",\n'
        '      "sdk_considerations": "how to keep or improve MCP SDK usage"\n'
        "    }\n"
        "  ],\n"
        '  "broken_controls": [\n'
        "    {\n"
        '      "surface": "page or route guess",\n'
        '      "control": "button, link, form control, or panel",\n'
        '      "failure_mode": "what appears broken, misleading, or disconnected",\n'
        '      "repair": "what to change in code or behavior"\n'
        "    }\n"
        "  ],\n"
        '  "button_audit": [\n'
        "    {\n"
        '      "surface": "page or route guess",\n'
        '      "control": "button, link, or tab label",\n'
        '      "expected_outcome": "route, state change, or visible confirmation",\n'
        '      "status": "pass|warning|fail",\n'
        '      "notes": "why it passes or fails"\n'
        "    }\n"
        "  ],\n"
        '  "route_handoffs": [\n'
        "    {\n"
        '      "from_surface": "source page",\n'
        '      "to_surface": "destination page",\n'
        '      "trigger": "clicked control or action",\n'
        '      "state_requirements": ["shared DID, synopsis, draft state, etc."],\n'
        '      "status": "pass|warning|fail"\n'
        "    }\n"
        "  ],\n"
        '  "complaint_journey": {\n'
        '    "tested_stages": ["chat|intake|evidence|review|draft|integrations|optimizer"],\n'
        '    "journey_gaps": ["where a user can fail or lose context"],\n'
        '    "sdk_tool_invocations": ["which MCP SDK tool calls should remain visible in the UI"],\n'
        '    "release_blockers": ["what must be fixed before sending legal clients here"]\n'
        "  },\n"
        '  "actor_plan": {\n'
        '    "primary_objective": "highest-value UI objective",\n'
        '    "repair_sequence": ["ordered UI/UX repairs"],\n'
        '    "playwright_objectives": ["browser assertions to prove the flow works"],\n'
        '    "mcp_sdk_expectations": ["which SDK-backed actions must stay first-class"]\n'
        "  },\n"
        '  "critic_review": {\n'
        '    "verdict": "pass|warning|fail",\n'
        '    "blocking_findings": ["what still blocks a real complaint journey"],\n'
        '    "acceptance_checks": ["what must pass before the UI is acceptable"]\n'
        "  },\n"
        '  "actor_summary": "how the actor experiences the overall complaint journey",\n'
        '  "critic_summary": "the critic verdict on structural UX risk",\n'
        '  "actor_path_breaks": ["specific points where the actor gets stuck or loses context"],\n'
        '  "critic_test_obligations": ["specific end-to-end assertions Playwright must enforce"],\n'
        '  "stage_findings": {\n'
        '    "Intake": "actor/critic finding",\n'
        '    "Evidence": "actor/critic finding",\n'
        '    "Review": "actor/critic finding",\n'
        '    "Draft": "actor/critic finding",\n'
        '    "Integration Discovery": "actor/critic finding"\n'
        "  },\n"
        '  "workflow_gaps": ["list of missing workflow affordances"],\n'
        '  "playwright_followups": ["tests or screenshots to add next"]\n'
        "}\n"
    )


def _load_backend_kwargs(config_path: Optional[str], backend_id: Optional[str]) -> Dict[str, Any]:
    if not config_path:
        return {"id": backend_id or "ui-review"}
    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        return {"id": backend_id or "ui-review"}
    try:
        payload = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.warning("Could not load UI review backend configuration from %s; using defaults", path, exc_info=True)
        return {"id": backend_id or "ui-review"}
    except Exception:
        logger.exception("Unexpected failure loading UI review backend configuration from %s; using defaults", path)
        return {"id": backend_id or "ui-review"}
    backends = payload.get("BACKENDS") or payload.get("backends") or []
    if not isinstance(backends, list):
        return {"id": backend_id or "ui-review"}
    target = None
    for item in backends:
        if not isinstance(item, dict):
            continue
        if backend_id and str(item.get("id")) == backend_id:
            target = item
            break
        if target is None and str(item.get("type")) == "llm_router":
            target = item
    if not isinstance(target, dict):
        return {"id": backend_id or "ui-review"}
    config = dict(target)
    config.setdefault("id", backend_id or config.get("id") or "ui-review")
    return config


def _slugify_path_label(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
    normalized = "-".join(part for part in cleaned.split("-") if part)
    return normalized or "ui-review"


def _default_ui_review_diagnostics_dir(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    destination = Path(output_path).expanduser().resolve()
    stem = destination.stem or "ui-review"
    return destination.parent / f"{stem}-codex-diagnostics"


def _ui_review_codex_trace_kwargs(
    *,
    provider: Optional[str],
    screenshots: Iterable[Path],
    diagnostics_dir: Optional[str],
) -> Dict[str, Any]:
    provider_name = str(provider or "").strip().lower()
    if provider_name not in {"codex_cli", "codex"}:
        return {}
    if not diagnostics_dir:
        return {}

    root = Path(diagnostics_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    screenshot_names = [_slugify_path_label(path.stem) for path in list(screenshots or []) if isinstance(path, Path)]
    label = screenshot_names[0] if len(screenshot_names) == 1 else "multi-page-review"
    trace_jsonl_path = root / f"{label}.codex.jsonl"
    return {
        "trace": True,
        "trace_dir": str(root),
        "trace_jsonl_path": str(trace_jsonl_path),
        "trace_stderr_path": str(trace_jsonl_path).replace(".jsonl", ".stderr.log"),
        "trace_metadata_path": str(trace_jsonl_path).replace(".jsonl", ".metadata.json"),
    }


def _resolve_ui_review_backend(
    provider: Optional[str],
    model: Optional[str],
    *,
    config_path: Optional[str],
    backend_id: Optional[str],
) -> Dict[str, Any]:
    backend_kwargs = _load_backend_kwargs(config_path, backend_id)

    requested_provider = str(provider or "").strip()
    requested_model = str(model or "").strip()
    requested_provider_key = requested_provider.lower()
    requested_model_key = requested_model.lower()

    if requested_provider_key in _UI_REVIEW_ROUTE_PROVIDER_ALIASES:
        configured_provider = str(backend_kwargs.get("provider") or "").strip()
        if configured_provider.lower() in _UI_REVIEW_ROUTE_PROVIDER_ALIASES:
            configured_provider = ""
        backend_kwargs["provider"] = (
            configured_provider
            or str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_ROUTER_PROVIDER", "") or "").strip()
            or str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_PROVIDER", "") or "").strip()
            or DEFAULT_UI_REVIEW_PROVIDER
        )
        backend_kwargs["_requested_provider_alias"] = requested_provider
    elif requested_provider:
        backend_kwargs["provider"] = requested_provider
    else:
        backend_kwargs.setdefault(
            "provider",
            str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_PROVIDER", "") or "").strip() or DEFAULT_UI_REVIEW_PROVIDER,
        )

    provider_name = str(backend_kwargs.get("provider") or "").strip().lower()
    if requested_model_key in _UI_REVIEW_ROUTE_MODEL_ALIASES:
        backend_kwargs["_requested_model_alias"] = requested_model
        backend_kwargs.pop("model", None)
        backend_kwargs["model"] = (
            str(os.getenv(f"COMPLAINT_GENERATOR_UI_REVIEW_MODEL_{provider_name.upper()}", "") or "").strip()
            or str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL", "") or "").strip()
            or DEFAULT_UI_REVIEW_MODELS_BY_PROVIDER.get(provider_name)
        )
    elif requested_model:
        backend_kwargs["model"] = requested_model
    else:
        backend_kwargs.setdefault(
            "model",
            str(os.getenv(f"COMPLAINT_GENERATOR_UI_REVIEW_MODEL_{provider_name.upper()}", "") or "").strip()
            or str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL", "") or "").strip()
            or DEFAULT_UI_REVIEW_MODELS_BY_PROVIDER.get(provider_name),
        )

    backend_kwargs.setdefault(
        "timeout",
        _ui_review_timeout_for_provider(backend_kwargs.get("provider")),
    )
    backend_kwargs.setdefault("retry_max_attempts", 1)
    backend_kwargs.setdefault("allow_local_fallback", False)
    return backend_kwargs


def _backend_runtime_kwargs(backend_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in dict(backend_kwargs or {}).items()
        if not str(key).startswith("_")
    }


def _router_alias_metadata(backend_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    provider_alias = str((backend_kwargs or {}).get("_requested_provider_alias") or "").strip()
    model_alias = str((backend_kwargs or {}).get("_requested_model_alias") or "").strip()
    if provider_alias:
        metadata["requested_provider_alias"] = provider_alias
    if model_alias:
        metadata["requested_model_alias"] = model_alias
    if provider_alias or model_alias:
        metadata["route_alias_resolved"] = True
    return metadata


def _ui_review_heartbeat_seconds() -> float:
    raw_value = str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_HEARTBEAT_SECONDS", "") or "").strip()
    if not raw_value:
        raw_value = str(os.getenv("COMPLAINT_UI_REVIEW_HEARTBEAT_SECONDS", "") or "").strip()
    if not raw_value:
        return 0.0
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        logger.debug("Invalid UI review heartbeat interval %r; disabling heartbeat output", raw_value)
        return 0.0


def _emit_ui_review_heartbeat(label: str, *, elapsed_s: float, timeout_s: float) -> None:
    safe_label = str(label or "ui_review").strip() or "ui_review"
    print(
        f"[ui_review] stage={safe_label} elapsed={elapsed_s:.1f}s timeout={timeout_s:g}s",
        flush=True,
    )


def _call_with_timeout(fn, *, timeout_s: float, label: str = "ui_review"):
    result_queue: Queue[tuple[str, Any]] = Queue(maxsize=1)

    def _runner():
        try:
            result_queue.put(("ok", fn()))
        except Exception as exc:
            result_queue.put(("err", exc))

    worker = threading.Thread(target=_runner, name="ui-review-timeout-worker", daemon=True)
    worker.start()
    timeout_value = max(0.001, float(timeout_s))
    heartbeat_s = _ui_review_heartbeat_seconds()
    started_at = perf_counter()
    next_heartbeat_at = heartbeat_s if heartbeat_s > 0 else timeout_value
    while worker.is_alive():
        elapsed_s = perf_counter() - started_at
        remaining_s = timeout_value - elapsed_s
        if remaining_s <= 0:
            break
        wait_s = min(remaining_s, max(0.001, next_heartbeat_at - elapsed_s))
        worker.join(timeout=wait_s)
        elapsed_s = perf_counter() - started_at
        if heartbeat_s > 0 and worker.is_alive() and elapsed_s >= next_heartbeat_at:
            _emit_ui_review_heartbeat(label, elapsed_s=elapsed_s, timeout_s=timeout_value)
            next_heartbeat_at += heartbeat_s
    if worker.is_alive():
        raise TimeoutError(f"{label} timed out after {float(timeout_s):g}s")
    status, payload = result_queue.get_nowait()
    if status == "err":
        raise payload
    return payload


def _provider_prefers_text_ui_review(provider: Optional[str]) -> bool:
    normalized = str(provider or "").strip().lower()
    return normalized in _TEXT_ONLY_UI_REVIEW_PROVIDERS


def _complaint_output_review_timeout_for_provider(provider: Optional[str]) -> float:
    explicit = str(os.getenv("COMPLAINT_OUTPUT_REVIEW_TIMEOUT_SECONDS", "") or "").strip()
    if explicit:
        try:
            return max(5.0, float(explicit))
        except ValueError:
            logger.debug(
                "Invalid COMPLAINT_OUTPUT_REVIEW_TIMEOUT_SECONDS=%r; using the provider default",
                explicit,
            )
    normalized = str(provider or "").strip().lower()
    if normalized:
        provider_override = str(os.getenv(f"COMPLAINT_OUTPUT_REVIEW_TIMEOUT_SECONDS_{normalized.upper()}", "") or "").strip()
        if provider_override:
            try:
                return max(5.0, float(provider_override))
            except ValueError:
                logger.debug(
                    "Invalid complaint-output timeout override for provider %s: %r; using the provider default",
                    normalized,
                    provider_override,
                )
        return max(float(DEFAULT_COMPLAINT_OUTPUT_REVIEW_TIMEOUT_S), _ui_review_timeout_for_provider(provider))
    return float(DEFAULT_COMPLAINT_OUTPUT_REVIEW_TIMEOUT_S)


def _ui_review_timeout_for_provider(provider: Optional[str]) -> float:
    normalized = str(provider or "").strip().lower()
    provider_env = str(os.getenv(f"COMPLAINT_GENERATOR_UI_REVIEW_TIMEOUT_SECONDS_{normalized.upper()}", "") or "").strip()
    global_env = str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_TIMEOUT_SECONDS", "") or "").strip()
    legacy_env = str(os.getenv("COMPLAINT_UI_REVIEW_TIMEOUT_SECONDS", "") or "").strip()
    for candidate in (provider_env, global_env, legacy_env):
        if not candidate:
            continue
        try:
            return max(1.0, float(candidate))
        except ValueError:
            logger.debug("Invalid UI review timeout override %r; trying the next configured value", candidate)
            continue
    return float(_TEXT_UI_REVIEW_TIMEOUTS.get(normalized, DEFAULT_UI_REVIEW_TIMEOUT_S))


def _ui_review_page_executor_for_provider(provider: Optional[str]) -> str:
    override = str(os.getenv("COMPLAINT_UI_REVIEW_PAGE_EXECUTOR", "") or "").strip().lower()
    if override in {"inline", "process"}:
        return override
    normalized = str(provider or "").strip().lower()
    if normalized in {"codex_cli", "codex"}:
        return "inline"
    return "process"


def _ui_review_model_for_provider(provider: Optional[str]) -> Optional[str]:
    normalized = str(provider or "").strip().lower()
    if not normalized:
        return None
    env_key = f"COMPLAINT_GENERATOR_UI_REVIEW_MODEL_{normalized.upper()}"
    value = str(os.getenv(env_key, "") or "").strip()
    if value:
        return value
    generic = str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL", "") or "").strip()
    if generic:
        return generic
    return DEFAULT_UI_REVIEW_MODELS_BY_PROVIDER.get(normalized)


def _is_rate_limit_router_error(error: Exception) -> bool:
    message = str(error or "").strip().lower()
    return any(
        token in message
        for token in (
            "rate limit",
            "usage limit",
            "quota exceeded",
            "too many requests",
            "429",
        )
    )


def _multimodal_rate_limit_fallback_chain(provider: Optional[str]) -> List[str]:
    normalized = str(provider or "").strip().lower()
    return list(_MULTIMODAL_RATE_LIMIT_FALLBACKS.get(normalized, ()))


def _fallback_backend_kwargs(
    backend_kwargs: Dict[str, Any],
    *,
    provider: str,
) -> Dict[str, Any]:
    updated = dict(backend_kwargs or {})
    updated["provider"] = provider
    fallback_model = _ui_review_model_for_provider(provider)
    if fallback_model:
        updated["model"] = fallback_model
    else:
        updated.pop("model", None)
    return updated


def _should_use_compact_ui_review_prompt(
    *,
    provider: Optional[str],
    screenshot_count: int,
    compact_page_prompt: bool,
) -> bool:
    if compact_page_prompt:
        return True
    if str(os.getenv("COMPLAINT_UI_REVIEW_FULL_SINGLE_PAGE_PROMPT", "") or "").strip() == "1":
        return False
    normalized = str(provider or "").strip().lower()
    return screenshot_count <= 1 and normalized in {"codex_cli", "codex"}


def _review_with_multimodal_router(
    *,
    screenshots: List[Path],
    prompt: str,
    backend_kwargs: Dict[str, Any],
    diagnostics_dir: Optional[str],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    prepared_screenshots, preparation_metadata = _prepare_multimodal_image_paths(
        screenshots,
        provider=backend_kwargs.get("provider"),
        diagnostics_dir=diagnostics_dir,
    )
    backend = MultimodalRouterBackend(**_backend_runtime_kwargs(backend_kwargs))
    timeout_s = float(backend_kwargs.get("timeout") or DEFAULT_UI_REVIEW_TIMEOUT_S)
    review_label = "multimodal_router:" + ",".join(path.stem for path in prepared_screenshots[:3])
    started_at = perf_counter()
    raw_response = _call_with_timeout(
        lambda: backend(
            prompt,
            image_paths=prepared_screenshots,
            system_prompt=(
                "Review complaint UI screenshots and produce strict JSON. "
                "Prioritize actionable fixes that preserve the shared MCP JavaScript SDK workflow."
            ),
        ),
        timeout_s=timeout_s,
        label=review_label,
    )
    elapsed_s = perf_counter() - started_at
    return (
        _parse_json_response(raw_response),
        {
            "id": backend.id,
            "provider": backend.provider,
            "model": backend.model,
            "strategy": "multimodal_router",
            "elapsed_seconds": round(float(elapsed_s), 3),
            "prompt_chars": len(prompt),
            "screenshot_count": len(prepared_screenshots),
            **preparation_metadata,
            **_router_alias_metadata(backend_kwargs),
        },
    )


def _review_with_text_router(
    *,
    prompt: str,
    backend_kwargs: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    backend = LLMRouterBackend(**_backend_runtime_kwargs(backend_kwargs))
    timeout_s = float(backend_kwargs.get("timeout") or DEFAULT_UI_REVIEW_TIMEOUT_S)
    started_at = perf_counter()
    raw_response = _call_with_timeout(lambda: backend(prompt), timeout_s=timeout_s, label="llm_router:text_ui_review")
    elapsed_s = perf_counter() - started_at
    return (
        _parse_json_response(raw_response),
        {
            "id": backend.id,
            "provider": backend.provider,
            "model": backend.model,
            "strategy": "llm_router",
            "elapsed_seconds": round(float(elapsed_s), 3),
            "prompt_chars": len(prompt),
            "screenshot_count": 0,
            **_router_alias_metadata(backend_kwargs),
        },
    )


def create_ui_review_report(
    screenshot_paths: Iterable[str],
    *,
    notes: Optional[str] = None,
    goals: Optional[List[str]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    output_path: Optional[str] = None,
    diagnostics_dir: Optional[str] = None,
    artifact_metadata: Optional[List[Dict[str, Any]]] = None,
    compact_page_prompt: bool = False,
    page_review_executor: str = "inline",
) -> Dict[str, Any]:
    screenshots = _normalize_paths(screenshot_paths)
    if not screenshots and not list(artifact_metadata or []):
        raise ValueError("No screenshot files were found for UI review.")

    complaint_output_feedback = _summarize_complaint_output_feedback(artifact_metadata or [])
    backend_kwargs = _resolve_ui_review_backend(
        provider,
        model,
        config_path=config_path,
        backend_id=backend_id,
    )
    resolved_diagnostics_dir = diagnostics_dir
    if resolved_diagnostics_dir is None:
        default_diagnostics_dir = _default_ui_review_diagnostics_dir(output_path)
        resolved_diagnostics_dir = str(default_diagnostics_dir) if default_diagnostics_dir else None
    backend_kwargs.update(
        _ui_review_codex_trace_kwargs(
            provider=backend_kwargs.get("provider"),
            screenshots=screenshots,
            diagnostics_dir=resolved_diagnostics_dir,
        )
    )
    use_compact_prompt = _should_use_compact_ui_review_prompt(
        provider=backend_kwargs.get("provider"),
        screenshot_count=len(screenshots),
        compact_page_prompt=compact_page_prompt,
    )
    prompt = build_ui_review_prompt(
        screenshots,
        notes=notes,
        goals=goals,
        artifact_metadata=artifact_metadata,
        include_full_contract_context=not use_compact_prompt,
    )

    if len(screenshots) > 1:
        selected_screenshots, selection_metadata = _select_screenshots_for_review(
            screenshots,
            artifact_metadata=artifact_metadata or [],
            provider=backend_kwargs.get("provider"),
        )
        page_reports: List[Dict[str, Any]] = []
        task_payloads: List[Dict[str, Any]] = []
        for screenshot in selected_screenshots:
            page_artifacts = _filter_artifacts_for_page(screenshot, artifact_metadata or [])
            task_payloads.append(
                {
                    "screenshot": str(screenshot),
                    "page_label": _page_review_unit_label(screenshot, page_artifacts),
                    "notes": notes,
                    "goals": list(goals or []),
                    "provider": provider,
                    "model": model,
                    "config_path": config_path,
                    "backend_id": backend_id,
                    "artifact_metadata": page_artifacts,
                    "compact_page_prompt": True,
                    "diagnostics_dir": (
                        str(Path(resolved_diagnostics_dir).expanduser().resolve() / "pages")
                        if resolved_diagnostics_dir
                        else None
                    ),
                }
            )

        executor_mode = str(page_review_executor or "inline").strip().lower()
        if executor_mode == "process":
            max_workers = max(
                1,
                min(
                    len(task_payloads),
                    int(os.getenv("COMPLAINT_UI_REVIEW_PAGE_WORKERS", "4") or "4"),
                ),
            )
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_run_page_review_task, payload) for payload in task_payloads]
                for future in as_completed(futures):
                    page_reports.append(dict(future.result() or {}))
        else:
            for payload in task_payloads:
                page_reports.append(_run_page_review_task(payload))

        page_reports.sort(key=lambda item: str(item.get("page_label") or "").strip())
        review_payload = normalize_ui_review_payload_dto(
            _aggregate_page_review_reports(page_reports)
        )
        backend_metadata = {
            "id": backend_kwargs.get("id", "ui-review"),
            "provider": backend_kwargs.get("provider"),
            "model": backend_kwargs.get("model"),
            "strategy": "page_reviews",
            "page_review_count": len(page_reports),
            "page_review_executor": executor_mode,
            "prompt_mode": "compact" if use_compact_prompt else "full",
            "page_review_backends": [dict(item.get("backend") or {}) for item in page_reports],
            **_router_alias_metadata(backend_kwargs),
            **selection_metadata,
        }
        report = {
            "generated_at": _utc_now(),
            "backend": backend_metadata,
            "screenshots": _screenshot_payload(selected_screenshots),
            "artifact_metadata": list(artifact_metadata or []),
            "complaint_output_feedback": complaint_output_feedback,
            "notes": notes or "",
            "review": review_payload,
            "page_reviews": page_reports,
        }
        if output_path:
            destination = Path(output_path).expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report, indent=2, sort_keys=True))
        return report

    review_payload: Dict[str, Any]
    backend_metadata: Dict[str, Any]

    provider_name = str(backend_kwargs.get("provider") or "").strip()
    skip_multimodal = _provider_prefers_text_ui_review(provider_name)
    fallback_attempts: List[Dict[str, Any]] = []

    multimodal_exc: Exception | None = None
    try:
        if skip_multimodal:
            raise RuntimeError(
                f"Skipping multimodal screenshot review for text-only provider: {provider_name or 'unspecified'}"
            )
        review_payload, backend_metadata = _review_with_multimodal_router(
            screenshots=screenshots,
            prompt=prompt,
            backend_kwargs=backend_kwargs,
            diagnostics_dir=resolved_diagnostics_dir,
        )
    except Exception as exc:
        multimodal_exc = exc
        if skip_multimodal:
            logger.debug("Using text UI review for text-only provider %s", provider_name or "unspecified")
        else:
            logger.warning("Multimodal UI review failed; attempting configured fallbacks", exc_info=True)
        if _is_rate_limit_router_error(exc):
            for fallback_provider in _multimodal_rate_limit_fallback_chain(provider_name):
                candidate_kwargs = _fallback_backend_kwargs(backend_kwargs, provider=fallback_provider)
                candidate_kwargs.update(
                    _ui_review_codex_trace_kwargs(
                        provider=fallback_provider,
                        screenshots=screenshots,
                        diagnostics_dir=resolved_diagnostics_dir,
                    )
                )
                try:
                    review_payload, backend_metadata = _review_with_multimodal_router(
                        screenshots=screenshots,
                        prompt=prompt,
                        backend_kwargs=candidate_kwargs,
                        diagnostics_dir=resolved_diagnostics_dir,
                    )
                    backend_metadata["fallback_from"] = "multimodal_router"
                    backend_metadata["provider_fallback_from"] = provider_name or None
                    backend_metadata["fallback_error"] = str(multimodal_exc)
                    if fallback_attempts:
                        backend_metadata["fallback_attempts"] = list(fallback_attempts)
                    break
                except Exception as fallback_exc:
                    logger.warning(
                        "Multimodal UI review fallback provider %s failed",
                        fallback_provider,
                        exc_info=True,
                    )
                    fallback_attempts.append(
                        {
                            "provider": fallback_provider,
                            "model": candidate_kwargs.get("model"),
                            "error": str(fallback_exc),
                        }
                    )
            else:
                review_payload = {}
                backend_metadata = {}
        else:
            review_payload = {}
            backend_metadata = {}
        if not backend_metadata:
            try:
                review_payload, backend_metadata = _review_with_text_router(
                    prompt=prompt,
                    backend_kwargs=backend_kwargs,
                )
                backend_metadata["fallback_from"] = "multimodal_router"
                backend_metadata["fallback_error"] = str(multimodal_exc)
                if fallback_attempts:
                    backend_metadata["fallback_attempts"] = list(fallback_attempts)
                if skip_multimodal:
                    backend_metadata["multimodal_skipped"] = True
            except Exception as exc:
                logger.warning(
                    "Text UI review fallback failed; using deterministic UI review output",
                    exc_info=True,
                )
                review_payload = _deterministic_ui_review_fallback(
                    screenshots=screenshots,
                    artifact_metadata=list(artifact_metadata or []),
                    complaint_output_feedback=complaint_output_feedback,
                    multimodal_error=multimodal_exc,
                    fallback_error=exc,
                )
                backend_metadata = {
                    "id": backend_kwargs.get("id", "ui-review"),
                    "provider": backend_kwargs.get("provider"),
                    "model": backend_kwargs.get("model"),
                    "strategy": "fallback",
                    "multimodal_error": str(multimodal_exc),
                    "fallback_error": str(exc),
                    **_router_alias_metadata(backend_kwargs),
                }
                if fallback_attempts:
                    backend_metadata["fallback_attempts"] = list(fallback_attempts)
    backend_metadata.setdefault("prompt_mode", "compact" if use_compact_prompt else "full")

    review_payload = normalize_ui_review_payload_dto(review_payload)
    report = {
        "generated_at": _utc_now(),
        "backend": backend_metadata,
        "screenshots": _screenshot_payload(screenshots),
        "artifact_metadata": list(artifact_metadata or []),
        "complaint_output_feedback": complaint_output_feedback,
        "notes": notes or "",
        "review": review_payload,
        "page_reviews": [],
    }
    if output_path:
        destination = Path(output_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def run_ui_review_workflow(
    screenshot_dir: str,
    *,
    notes: Optional[str] = None,
    goals: Optional[List[str]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    screenshots = _list_screenshots(screenshot_dir)
    artifact_metadata = _list_artifact_metadata(screenshot_dir)
    resolved_backend = _resolve_ui_review_backend(
        provider,
        model,
        config_path=config_path,
        backend_id=backend_id,
    )
    return create_ui_review_report(
        [str(path) for path in screenshots],
        notes=notes,
        goals=goals,
        provider=resolved_backend.get("provider"),
        model=resolved_backend.get("model"),
        config_path=config_path,
        backend_id=backend_id,
        output_path=output_path,
        artifact_metadata=artifact_metadata,
        page_review_executor=_ui_review_page_executor_for_provider(resolved_backend.get("provider")),
    )
