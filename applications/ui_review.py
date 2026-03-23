from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from backends import LLMRouterBackend, MultimodalRouterBackend


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


def _parse_json_response(text: str) -> Dict[str, Any]:
    stripped = _strip_code_fences(text)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {
        "summary": "The UI review response was not valid JSON.",
        "issues": [],
        "recommended_changes": [],
        "broken_controls": [],
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


def build_ui_review_prompt(
    screenshots: Iterable[Path],
    *,
    notes: Optional[str] = None,
    goals: Optional[List[str]] = None,
) -> str:
    screenshot_list = _screenshot_payload(screenshots)
    goal_lines = goals or [
        "Make the complaint generator easier for a first-time complainant to complete without legal jargon fatigue.",
        "Prefer one shared application framework and common code paths across the first-class pages.",
        "Use the JavaScript MCP SDK rather than page-specific ad hoc fetch logic whenever possible.",
        "Make the intake, evidence, support review, and draft editing journey feel linear and trustworthy.",
    ]
    return (
        "You are reviewing the UI/UX of a complaint-generator web application for real complainants.\n"
        "The screenshots below were created by Playwright during regression testing.\n"
        "Use the screenshots as the primary source artifacts for review.\n"
        "Pay special attention to trauma-informed language, complaint-intake clarity, evidence capture, next-step guidance, layout coherence, and whether the site visibly uses a shared JavaScript MCP SDK workflow.\n\n"
        "Apply an explicit actor / critic method.\n"
        "Actor: a real complainant or complaint operator trying to complete intake, provide testimony, upload evidence, review claims, and finish the complaint.\n"
        "Critic: a hostile QA reviewer looking for broken buttons, dead navigation, hidden MCP SDK flows, and missing Playwright assertions.\n\n"
        f"Goals:\n- " + "\n- ".join(goal_lines) + "\n\n"
        f"Additional notes:\n{notes or 'No additional notes were provided.'}\n\n"
        "Contract surfaces that must remain coherent:\n"
        "- Package exports in complaint_generator\n"
        "- CLI tools like complaint-generator and complaint-workspace\n"
        "- MCP server tools such as complaint.start_session and complaint.review_ui\n"
        "- Browser SDK usage through window.ComplaintMcpSdk.ComplaintMcpClient\n\n"
        "Screenshot artifacts:\n"
        f"{json.dumps(screenshot_list, indent=2, sort_keys=True)}\n\n"
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
    except Exception:
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


def _review_with_multimodal_router(
    *,
    screenshots: List[Path],
    prompt: str,
    backend_kwargs: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    backend = MultimodalRouterBackend(**backend_kwargs)
    raw_response = backend(
        prompt,
        image_paths=screenshots,
        system_prompt=(
            "Review complaint UI screenshots and produce strict JSON. "
            "Prioritize actionable fixes that preserve the shared MCP JavaScript SDK workflow."
        ),
    )
    return (
        _parse_json_response(raw_response),
        {
            "id": backend.id,
            "provider": backend.provider,
            "model": backend.model,
            "strategy": "multimodal_router",
        },
    )


def _review_with_text_router(
    *,
    prompt: str,
    backend_kwargs: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    backend = LLMRouterBackend(**backend_kwargs)
    raw_response = backend(prompt)
    return (
        _parse_json_response(raw_response),
        {
            "id": backend.id,
            "provider": backend.provider,
            "model": backend.model,
            "strategy": "llm_router",
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
) -> Dict[str, Any]:
    screenshots = _normalize_paths(screenshot_paths)
    if not screenshots:
        raise ValueError("No screenshot files were found for UI review.")

    prompt = build_ui_review_prompt(screenshots, notes=notes, goals=goals)
    review_payload: Dict[str, Any]
    backend_metadata: Dict[str, Any]

    backend_kwargs = _load_backend_kwargs(config_path, backend_id)
    if provider:
        backend_kwargs["provider"] = provider
    if model:
        backend_kwargs["model"] = model

    try:
        review_payload, backend_metadata = _review_with_multimodal_router(
            screenshots=screenshots,
            prompt=prompt,
            backend_kwargs=backend_kwargs,
        )
    except Exception as multimodal_exc:
        try:
            review_payload, backend_metadata = _review_with_text_router(
                prompt=prompt,
                backend_kwargs=backend_kwargs,
            )
            backend_metadata["fallback_from"] = "multimodal_router"
            backend_metadata["fallback_error"] = str(multimodal_exc)
        except Exception as exc:
            review_payload = {
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
            }
            backend_metadata = {
                "id": backend_kwargs.get("id", "ui-review"),
                "provider": backend_kwargs.get("provider"),
                "model": backend_kwargs.get("model"),
                "strategy": "fallback",
                "multimodal_error": str(multimodal_exc),
                "fallback_error": str(exc),
            }

    report = {
        "generated_at": _utc_now(),
        "backend": backend_metadata,
        "screenshots": _screenshot_payload(screenshots),
        "notes": notes or "",
        "review": review_payload,
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
    return create_ui_review_report(
        [str(path) for path in screenshots],
        notes=notes,
        goals=goals,
        provider=provider,
        model=model,
        config_path=config_path,
        backend_id=backend_id,
        output_path=output_path,
    )
