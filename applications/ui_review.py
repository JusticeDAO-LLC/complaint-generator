from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from backends import LLMRouterBackend, MultimodalRouterBackend


DEFAULT_COMPLAINT_OUTPUT_REVIEW_TIMEOUT_S = 8
DEFAULT_UI_REVIEW_TIMEOUT_S = 10


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
        except Exception:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


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
    backend_kwargs.setdefault("timeout", DEFAULT_COMPLAINT_OUTPUT_REVIEW_TIMEOUT_S)
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
) -> str:
    screenshot_list = _screenshot_payload(screenshots)
    goal_lines = goals or [
        "Make the complaint generator easier for a first-time complainant to complete without legal jargon fatigue.",
        "Prefer one shared application framework and common code paths across the first-class pages.",
        "Use the JavaScript MCP SDK rather than page-specific ad hoc fetch logic whenever possible.",
        "Make the intake, evidence, support review, and draft editing journey feel linear and trustworthy.",
    ]
    complaint_feedback = _summarize_complaint_output_feedback(artifact_metadata or [])
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
        "- Package exports in complaint_generator, including start_session, submit_intake_answers, save_evidence, review_case, build_mediator_prompt, generate_complaint, update_draft, export_complaint_packet, export_complaint_markdown, export_complaint_pdf, and update_case_synopsis\n"
        "- CLI tools like complaint-generator and complaint-workspace, including review-ui, optimize-ui, and browser-audit\n"
        "- MCP server tools such as complaint.start_session, complaint.build_mediator_prompt, complaint.export_complaint_packet, complaint.export_complaint_markdown, complaint.export_complaint_pdf, complaint.review_ui, complaint.optimize_ui, and complaint.run_browser_audit\n"
        "- Browser SDK usage through window.ComplaintMcpSdk.ComplaintMcpClient, including optimizeUiArtifacts() and runBrowserAudit()\n\n"
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


def _call_with_timeout(fn, *, timeout_s: float):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn)
    try:
        return future.result(timeout=max(0.001, float(timeout_s)))
    except FuturesTimeoutError as exc:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise TimeoutError(f"UI review timed out after {float(timeout_s):g}s") from exc
    finally:
        if not future.cancelled() and future.done():
            executor.shutdown(wait=False, cancel_futures=True)


def _review_with_multimodal_router(
    *,
    screenshots: List[Path],
    prompt: str,
    backend_kwargs: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    backend = MultimodalRouterBackend(**backend_kwargs)
    timeout_s = float(backend_kwargs.get("timeout") or DEFAULT_UI_REVIEW_TIMEOUT_S)
    raw_response = _call_with_timeout(
        lambda: backend(
            prompt,
            image_paths=screenshots,
            system_prompt=(
                "Review complaint UI screenshots and produce strict JSON. "
                "Prioritize actionable fixes that preserve the shared MCP JavaScript SDK workflow."
            ),
        ),
        timeout_s=timeout_s,
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
    timeout_s = float(backend_kwargs.get("timeout") or DEFAULT_UI_REVIEW_TIMEOUT_S)
    raw_response = _call_with_timeout(lambda: backend(prompt), timeout_s=timeout_s)
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
    artifact_metadata: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    screenshots = _normalize_paths(screenshot_paths)
    if not screenshots:
        raise ValueError("No screenshot files were found for UI review.")

    complaint_output_feedback = _summarize_complaint_output_feedback(artifact_metadata or [])
    prompt = build_ui_review_prompt(
        screenshots,
        notes=notes,
        goals=goals,
        artifact_metadata=artifact_metadata,
    )
    review_payload: Dict[str, Any]
    backend_metadata: Dict[str, Any]

    backend_kwargs = _load_backend_kwargs(config_path, backend_id)
    if provider:
        backend_kwargs["provider"] = provider
    if model:
        backend_kwargs["model"] = model
    backend_kwargs.setdefault("timeout", DEFAULT_UI_REVIEW_TIMEOUT_S)
    backend_kwargs.setdefault("retry_max_attempts", 1)
    backend_kwargs.setdefault("allow_local_fallback", False)

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
        "artifact_metadata": list(artifact_metadata or []),
        "complaint_output_feedback": complaint_output_feedback,
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
    artifact_metadata = _list_artifact_metadata(screenshot_dir)
    return create_ui_review_report(
        [str(path) for path in screenshots],
        notes=notes,
        goals=goals,
        provider=provider,
        model=model,
        config_path=config_path,
        backend_id=backend_id,
        output_path=output_path,
        artifact_metadata=artifact_metadata,
    )
