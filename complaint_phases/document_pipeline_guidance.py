"""Drafting guidance extracted from the document pipeline.

The public and private entry points below keep their original bodies. Private
helpers that still live on the document-pipeline owner are resolved when a
function runs, after both modules have finished loading.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from intake_status import build_intake_case_review_summary


def _pipeline_helper(name: str):
    """Return a helper that remains defined on the document-pipeline owner."""
    from complaint_phases import document_pipeline as owner

    return getattr(owner, name)


def _dedupe_text_values(values: Iterable[Any]) -> List[str]:
    return _pipeline_helper("_dedupe_text_values")(values)


def _slugify(value: str) -> str:
    return _pipeline_helper("_slugify")(value)


def _format_timeline_date(value: Any) -> str:
    return _pipeline_helper("_format_timeline_date")(value)


def _chronology_fact_label(fact: Dict[str, Any]) -> str:
    return _pipeline_helper("_chronology_fact_label")(fact)


def _join_chronology_segments(segments: List[str]) -> str:
    return _pipeline_helper("_join_chronology_segments")(segments)


def _coerce_list(value: Any) -> List[Any]:
    return _pipeline_helper("_coerce_list")(value)


def _unique_preserving_order(values: Iterable[str]) -> List[str]:
    return _pipeline_helper("_unique_preserving_order")(values)


def build_drafting_support_bundles(claim_support_packets: Dict[str, Any]) -> Dict[str, Any]:
    """Build section-level drafting support bundles from mediator claim packets."""
    section_bundles: Dict[str, Dict[str, Any]] = {
        "factual_allegations": {
            "section_id": "factual_allegations",
            "support_status": "unsupported",
            "claim_elements": [],
            "source_refs": [],
            "explicit_gaps": [],
        },
        "jurisdiction_and_venue": {
            "section_id": "jurisdiction_and_venue",
            "support_status": "unsupported",
            "claim_elements": [],
            "source_refs": [],
            "explicit_gaps": [],
        },
        "claims_for_relief": {
            "section_id": "claims_for_relief",
            "support_status": "unsupported",
            "claim_elements": [],
            "source_refs": [],
            "explicit_gaps": [],
        },
        "requested_relief": {
            "section_id": "requested_relief",
            "support_status": "unsupported",
            "claim_elements": [],
            "source_refs": [],
            "explicit_gaps": ["Confirm requested relief is supported by facts and authority."],
        },
    }

    status_rank = {
        "unsupported": 0,
        "contradicted": 0,
        "partially_supported": 1,
        "supported": 2,
    }

    def _merge_status(current: str, candidate: str) -> str:
        if candidate == "contradicted":
            return "contradicted"
        return candidate if status_rank.get(candidate, 0) > status_rank.get(current, 0) else current

    def _add_source_refs(bundle: Dict[str, Any], manifest: Dict[str, Any]) -> None:
        existing = set(bundle["source_refs"])
        for entry in manifest.get("entries", []) if isinstance(manifest, dict) else []:
            if not isinstance(entry, dict):
                continue
            ref = str(entry.get("id") or entry.get("source_ref") or "").strip()
            if ref and ref not in existing:
                existing.add(ref)
                bundle["source_refs"].append(ref)

    for claim_type, packet in (claim_support_packets or {}).items():
        if not isinstance(packet, dict):
            continue
        for element in packet.get("elements", []) or []:
            if not isinstance(element, dict):
                continue
            support_status = str(element.get("support_status") or "unsupported").strip() or "unsupported"
            element_ref = {
                "claim_type": claim_type,
                "element_id": element.get("element_id"),
                "element_text": element.get("element_text"),
                "support_status": support_status,
                "support_quality": element.get("support_quality", ""),
                "support_lane_label": element.get("support_lane_label", ""),
                "missing_support_report": element.get("missing_support_report", {}),
                "authority_treatment_summary": element.get("authority_treatment_summary", {}),
                "authority_rule_candidate_summary": element.get("authority_rule_candidate_summary", {}),
                "validation_summary": {
                    "contradiction_count": int((element.get("contradiction_report") or {}).get("contradiction_count", 0) or 0),
                    "temporal_rule_status": element.get("temporal_rule_status", ""),
                },
            }
            factual_bundle = section_bundles["factual_allegations"]
            factual_bundle["claim_elements"].append(element_ref)
            factual_bundle["support_status"] = _merge_status(factual_bundle["support_status"], support_status)
            _add_source_refs(factual_bundle, element.get("bundle_manifest") or {})

            claims_bundle = section_bundles["claims_for_relief"]
            claims_bundle["claim_elements"].append(element_ref)
            claims_bundle["support_status"] = _merge_status(claims_bundle["support_status"], support_status)
            _add_source_refs(claims_bundle, element.get("bundle_manifest") or {})

            missing_report = element.get("missing_support_report") if isinstance(element.get("missing_support_report"), dict) else {}
            for gap in list(missing_report.get("missing_support_kinds") or []) + list(missing_report.get("missing_fact_bundle") or []):
                gap_text = str(gap or "").strip()
                if gap_text:
                    for section_id in ("factual_allegations", "claims_for_relief"):
                        section_bundles[section_id]["explicit_gaps"].append(gap_text)

            temporal_status = str(element.get("temporal_rule_status") or "").strip()
            if temporal_status:
                jurisdiction_bundle = section_bundles["jurisdiction_and_venue"]
                jurisdiction_bundle["claim_elements"].append(element_ref)
                jurisdiction_bundle["support_status"] = _merge_status(jurisdiction_bundle["support_status"], support_status)
                if temporal_status not in {"satisfied", "passed"}:
                    jurisdiction_bundle["explicit_gaps"].append(f"Temporal rule status: {temporal_status}")

    for bundle in section_bundles.values():
        bundle["explicit_gaps"] = _dedupe_text_values(bundle["explicit_gaps"])
        bundle["source_refs"] = _dedupe_text_values(bundle["source_refs"])
        bundle["claim_element_count"] = len(bundle["claim_elements"])
    return {
        "available": True,
        "sections": section_bundles,
        "section_count": len(section_bundles),
    }


def build_drafting_guardrails(drafting_support_bundles: Dict[str, Any]) -> Dict[str, Any]:
    """Build stable drafting-time guardrail warnings from section support bundles."""
    bundles = drafting_support_bundles if isinstance(drafting_support_bundles, dict) else {}
    sections = bundles.get("sections") if isinstance(bundles.get("sections"), dict) else {}
    warning_index: Dict[str, Dict[str, Any]] = {}

    def _add_warning(
        *,
        section_id: str,
        warning_type: str,
        message: str,
        severity: str = "warning",
        source: str = "drafting_support_bundle",
        recommended_action: str = "Review support before export.",
        claim_type: str = "",
        element_id: Any = "",
        source_refs: Iterable[Any] = (),
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        normalized_section = str(section_id or "document").strip() or "document"
        normalized_type = str(warning_type or "drafting_guardrail").strip() or "drafting_guardrail"
        normalized_claim = str(claim_type or "").strip()
        normalized_element = str(element_id or "").strip()
        normalized_severity = str(severity or "warning").strip().lower()
        if normalized_severity == "blocked":
            normalized_severity = "blocker"
        warning_id = "drafting-guardrail-" + _slugify(
            "-".join(
                item
                for item in [
                    normalized_section,
                    normalized_claim,
                    normalized_element,
                    normalized_type,
                ]
                if item
            )
        )
        if warning_id in warning_index:
            return
        warning = {
            "warning_id": warning_id,
            "section_id": normalized_section,
            "claim_type": normalized_claim,
            "element_id": normalized_element,
            "severity": "blocker" if normalized_severity in {"blocker", "critical"} else "warning",
            "warning_type": normalized_type,
            "message": str(message or "").strip(),
            "source": str(source or "drafting_support_bundle").strip() or "drafting_support_bundle",
            "recommended_action": str(recommended_action or "").strip() or "Review support before export.",
            "source_refs": _dedupe_text_values(source_refs),
        }
        if details:
            warning["details"] = dict(details)
        warning_index[warning_id] = warning

    for section_id, section in sections.items():
        if not isinstance(section, dict):
            continue
        normalized_section_id = str(section.get("section_id") or section_id or "document").strip() or "document"
        section_status = str(section.get("support_status") or "").strip().lower()
        section_source_refs = _dedupe_text_values(section.get("source_refs") or [])
        explicit_gaps = _dedupe_text_values(section.get("explicit_gaps") or [])
        if section_status in {"unsupported", "contradicted"} and normalized_section_id != "requested_relief":
            _add_warning(
                section_id=normalized_section_id,
                warning_type="unsupported_section",
                severity="blocker",
                message=f"{normalized_section_id.replace('_', ' ').title()} lacks support sufficient for drafting export.",
                recommended_action="Attach evidence and authority support before relying on this section.",
                source_refs=section_source_refs,
                details={"support_status": section_status, "explicit_gaps": explicit_gaps[:8]},
            )
        for gap in explicit_gaps:
            _add_warning(
                section_id=normalized_section_id,
                warning_type="explicit_section_gap",
                message=str(gap),
                recommended_action="Resolve the explicit drafting gap or document why degraded drafting is acceptable.",
                source_refs=section_source_refs,
            )

        for element in section.get("claim_elements", []) or []:
            if not isinstance(element, dict):
                continue
            claim_type = str(element.get("claim_type") or "").strip()
            element_id = element.get("element_id")
            element_label = str(element.get("element_text") or element_id or "claim element").strip()
            support_status = str(element.get("support_status") or "").strip().lower()
            missing_support_report = (
                element.get("missing_support_report")
                if isinstance(element.get("missing_support_report"), dict)
                else {}
            )
            missing_support_kinds = _dedupe_text_values(missing_support_report.get("missing_support_kinds") or [])
            missing_fact_bundle = _dedupe_text_values(missing_support_report.get("missing_fact_bundle") or [])
            if support_status in {"unsupported", "contradicted"}:
                _add_warning(
                    section_id=normalized_section_id,
                    claim_type=claim_type,
                    element_id=element_id,
                    warning_type="unsupported_element",
                    severity="blocker",
                    message=f"{claim_type or 'Claim'} element '{element_label}' is {support_status or 'unsupported'}.",
                    recommended_action="Add source-backed facts and authority or omit the unsupported allegation before export.",
                    source_refs=section_source_refs,
                    details={
                        "support_status": support_status,
                        "missing_support_kinds": missing_support_kinds,
                        "missing_fact_bundle": missing_fact_bundle[:8],
                    },
                )
            elif support_status == "partially_supported":
                _add_warning(
                    section_id=normalized_section_id,
                    claim_type=claim_type,
                    element_id=element_id,
                    warning_type="partially_supported_element",
                    message=f"{claim_type or 'Claim'} element '{element_label}' is only partially supported.",
                    recommended_action="Strengthen the element with additional support before final drafting.",
                    source_refs=section_source_refs,
                    details={"missing_support_kinds": missing_support_kinds, "missing_fact_bundle": missing_fact_bundle[:8]},
                )
            if missing_support_kinds or missing_fact_bundle:
                _add_warning(
                    section_id=normalized_section_id,
                    claim_type=claim_type,
                    element_id=element_id,
                    warning_type="proof_support_gap",
                    severity="blocker" if support_status in {"unsupported", "contradicted"} else "warning",
                    message=f"{claim_type or 'Claim'} element '{element_label}' has unresolved proof-support gaps.",
                    recommended_action="Close missing evidence, authority, or fact-bundle gaps before export.",
                    source_refs=section_source_refs,
                    details={
                        "missing_support_kinds": missing_support_kinds,
                        "missing_fact_bundle": missing_fact_bundle[:8],
                    },
                )

            validation_summary = (
                element.get("validation_summary")
                if isinstance(element.get("validation_summary"), dict)
                else {}
            )
            contradiction_count = int(validation_summary.get("contradiction_count") or 0)
            if contradiction_count > 0:
                _add_warning(
                    section_id=normalized_section_id,
                    claim_type=claim_type,
                    element_id=element_id,
                    warning_type="contradiction",
                    severity="blocker",
                    message=f"{claim_type or 'Claim'} element '{element_label}' has contradiction signals.",
                    recommended_action="Resolve contradictory facts or authority before relying on this element.",
                    source_refs=section_source_refs,
                    details={"contradiction_count": contradiction_count},
                )
            temporal_rule_status = str(validation_summary.get("temporal_rule_status") or "").strip().lower()
            if temporal_rule_status and temporal_rule_status not in {"ready", "supported", "satisfied", "pass", "passed"}:
                _add_warning(
                    section_id=normalized_section_id,
                    claim_type=claim_type,
                    element_id=element_id,
                    warning_type="temporal_or_procedural_gap",
                    message=f"{claim_type or 'Claim'} element '{element_label}' has temporal-rule status '{temporal_rule_status}'.",
                    recommended_action="Resolve timeline predicates and procedural timing before final drafting.",
                    source_refs=section_source_refs,
                    details={"temporal_rule_status": temporal_rule_status},
                )

            treatment_summary = (
                element.get("authority_treatment_summary")
                if isinstance(element.get("authority_treatment_summary"), dict)
                else {}
            )
            adverse_authority_count = int(treatment_summary.get("adverse_authority_link_count") or 0)
            if adverse_authority_count > 0:
                _add_warning(
                    section_id=normalized_section_id,
                    claim_type=claim_type,
                    element_id=element_id,
                    warning_type="adverse_authority",
                    message=f"{claim_type or 'Claim'} element '{element_label}' includes adverse or limiting authority.",
                    recommended_action="Review treatment and either distinguish the authority or avoid relying on it.",
                    source_refs=section_source_refs,
                    details={"adverse_authority_link_count": adverse_authority_count},
                )
            uncertain_authority_count = int(treatment_summary.get("uncertain_authority_link_count") or 0)
            treatment_type_counts = (
                treatment_summary.get("treatment_type_counts")
                if isinstance(treatment_summary.get("treatment_type_counts"), dict)
                else {}
            )
            unresolved_treatments = sorted(
                str(name)
                for name, count in treatment_type_counts.items()
                if int(count or 0) > 0 and str(name) in {"questioned", "limits", "superseded", "good_law_unconfirmed"}
            )
            if uncertain_authority_count > 0 or unresolved_treatments:
                _add_warning(
                    section_id=normalized_section_id,
                    claim_type=claim_type,
                    element_id=element_id,
                    warning_type="weak_treatment_confidence",
                    message=f"{claim_type or 'Claim'} element '{element_label}' has unresolved authority treatment or good-law confidence.",
                    recommended_action="Run or review good-law/treatment checks before export.",
                    source_refs=section_source_refs,
                    details={
                        "uncertain_authority_link_count": uncertain_authority_count,
                        "unresolved_treatment_types": unresolved_treatments,
                    },
                )

            rule_summary = (
                element.get("authority_rule_candidate_summary")
                if isinstance(element.get("authority_rule_candidate_summary"), dict)
                else {}
            )
            rule_type_counts = (
                rule_summary.get("rule_type_counts")
                if isinstance(rule_summary.get("rule_type_counts"), dict)
                else {}
            )
            procedural_rule_count = int(rule_type_counts.get("procedural_prerequisite") or 0)
            fact_unsatisfied_rule_count = int(rule_summary.get("fact_unsatisfied_rule_count") or 0)
            if procedural_rule_count > 0:
                _add_warning(
                    section_id=normalized_section_id,
                    claim_type=claim_type,
                    element_id=element_id,
                    warning_type="missing_procedural_prerequisite",
                    severity="blocker" if fact_unsatisfied_rule_count > 0 else "warning",
                    message=f"{claim_type or 'Claim'} element '{element_label}' has procedural prerequisite rules to satisfy.",
                    recommended_action="Confirm prerequisite facts, timing, notices, and exhaustion requirements before export.",
                    source_refs=section_source_refs,
                    details={
                        "procedural_rule_count": procedural_rule_count,
                        "fact_unsatisfied_rule_count": fact_unsatisfied_rule_count,
                    },
                )
            elif fact_unsatisfied_rule_count > 0:
                _add_warning(
                    section_id=normalized_section_id,
                    claim_type=claim_type,
                    element_id=element_id,
                    warning_type="failed_premise",
                    severity="blocker",
                    message=f"{claim_type or 'Claim'} element '{element_label}' has unsatisfied rule premises.",
                    recommended_action="Resolve failed or unsupported premises before export.",
                    source_refs=section_source_refs,
                    details={"fact_unsatisfied_rule_count": fact_unsatisfied_rule_count},
                )

    warnings = list(warning_index.values())
    blocker_count = sum(1 for warning in warnings if warning.get("severity") == "blocker")
    return {
        "available": bool(sections),
        "status": "blocked" if blocker_count else ("warning" if warnings else "ready"),
        "warning_count": len(warnings),
        "blocker_count": blocker_count,
        "warnings": warnings,
    }


def _build_anchored_chronology_summary_from_case_file(intake_case_file: Dict[str, Any], *, limit: int = 3) -> List[str]:
    case_file = intake_case_file if isinstance(intake_case_file, dict) else {}
    facts = [dict(item) for item in list(case_file.get("canonical_facts") or []) if isinstance(item, dict)]
    relations = [dict(item) for item in list(case_file.get("timeline_relations") or []) if isinstance(item, dict)]
    if not facts or not relations:
        return []

    fact_by_id = {
        str(fact.get("fact_id") or "").strip(): fact
        for fact in facts
        if str(fact.get("fact_id") or "").strip()
    }
    relation_records = []
    for relation in relations:
        if str(relation.get("relation_type") or "").strip().lower() != "before":
            continue
        source_id = str(relation.get("source_fact_id") or "").strip()
        target_id = str(relation.get("target_fact_id") or "").strip()
        source_fact = fact_by_id.get(source_id)
        target_fact = fact_by_id.get(target_id)
        if not source_fact or not target_fact:
            continue
        source_date = _format_timeline_date((source_fact.get("temporal_context") or {}).get("start_date") or relation.get("source_start_date"))
        target_date = _format_timeline_date((target_fact.get("temporal_context") or {}).get("start_date") or relation.get("target_start_date"))
        if not source_date or not target_date:
            continue
        relation_records.append(
            {
                "key": (source_id, target_id),
                "source_id": source_id,
                "target_id": target_id,
                "source_fact": source_fact,
                "target_fact": target_fact,
                "source_date": source_date,
                "target_date": target_date,
            }
        )
    if not relation_records:
        return []

    outgoing: Dict[str, List[Dict[str, Any]]] = {}
    incoming_count: Dict[str, int] = {}
    for record in relation_records:
        outgoing.setdefault(record["source_id"], []).append(record)
        incoming_count[record["target_id"]] = incoming_count.get(record["target_id"], 0) + 1
        incoming_count.setdefault(record["source_id"], incoming_count.get(record["source_id"], 0))

    lines: List[str] = []
    seen = set()
    used_keys = set()
    for record in relation_records:
        if len(lines) >= limit:
            break
        if record["key"] in used_keys:
            continue
        if incoming_count.get(record["source_id"], 0) != 0 or len(outgoing.get(record["source_id"], [])) != 1:
            continue
        chain = [record]
        next_id = record["target_id"]
        temp_used = {record["key"]}
        while len(outgoing.get(next_id, [])) == 1 and incoming_count.get(next_id, 0) == 1:
            next_record = outgoing[next_id][0]
            if next_record["key"] in temp_used:
                break
            chain.append(next_record)
            temp_used.add(next_record["key"])
            next_id = next_record["target_id"]
        if len(chain) < 2:
            continue
        segments = [
            f"{_chronology_fact_label(chain[0]['source_fact'])} on {chain[0]['source_date']}"
        ]
        segments.extend(
            f"{_chronology_fact_label(item['target_fact'])} on {item['target_date']}"
            for item in chain
        )
        line = f"{_join_chronology_segments(segments)} occurred in sequence."
        last_target = chain[-1]["target_fact"]
        target_context = last_target.get("temporal_context") if isinstance(last_target.get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f". The later date is currently derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        used_keys.update(temp_used)
        lines.append(line)

    for record in relation_records:
        if len(lines) >= limit:
            break
        if record["key"] in used_keys:
            continue
        source_label = _chronology_fact_label(record["source_fact"])
        target_label = _chronology_fact_label(record["target_fact"])
        line = f"{source_label} on {record['source_date']} preceded {target_label.lower()} on {record['target_date']}."
        target_context = record["target_fact"].get("temporal_context") if isinstance(record["target_fact"].get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f". The later date is currently derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines


def _build_runtime_workflow_optimization_guidance(
    *,
    mediator: Any,
    drafting_readiness: Dict[str, Any],
    workflow_phase_plan: Dict[str, Any],
    document_optimization: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    optimization_report = document_optimization if isinstance(document_optimization, dict) else {}
    existing_guidance = (
        optimization_report.get("workflow_optimization_guidance")
        if isinstance(optimization_report.get("workflow_optimization_guidance"), dict)
        else {}
    )
    if existing_guidance:
        guidance = dict(existing_guidance)
        if workflow_phase_plan and "workflow_phase_plan" not in guidance:
            guidance["workflow_phase_plan"] = dict(workflow_phase_plan)
        intake_case_summary = build_intake_case_review_summary(mediator)
        document_drafting_next_action = (
            intake_case_summary.get("document_drafting_next_action")
            if isinstance(intake_case_summary.get("document_drafting_next_action"), dict)
            else {}
        )
        workflow_targeting_summary = (
            optimization_report.get("workflow_targeting_summary")
            if isinstance(optimization_report.get("workflow_targeting_summary"), dict)
            else intake_case_summary.get("workflow_targeting_summary")
        )
        document_workflow_execution_summary = (
            optimization_report.get("document_workflow_execution_summary")
            if isinstance(optimization_report.get("document_workflow_execution_summary"), dict)
            else intake_case_summary.get("document_workflow_execution_summary")
        )
        document_execution_drift_summary = (
            optimization_report.get("document_execution_drift_summary")
            if isinstance(optimization_report.get("document_execution_drift_summary"), dict)
            else intake_case_summary.get("document_execution_drift_summary")
        )
        document_grounding_improvement_summary = (
            optimization_report.get("document_grounding_improvement_summary")
            if isinstance(optimization_report.get("document_grounding_improvement_summary"), dict)
            else intake_case_summary.get("document_grounding_improvement_summary")
        )
        document_grounding_lane_outcome_summary = (
            optimization_report.get("document_grounding_lane_outcome_summary")
            if isinstance(optimization_report.get("document_grounding_lane_outcome_summary"), dict)
            else intake_case_summary.get("document_grounding_lane_outcome_summary")
        )
        evidence_workflow_action_queue = (
            intake_case_summary.get("evidence_workflow_action_queue")
            if isinstance(intake_case_summary.get("evidence_workflow_action_queue"), list)
            else []
        )
        evidence_workflow_action_summary = (
            intake_case_summary.get("evidence_workflow_action_summary")
            if isinstance(intake_case_summary.get("evidence_workflow_action_summary"), dict)
            else {}
        )
        if "evidence_workflow_action_queue" not in guidance:
            guidance["evidence_workflow_action_queue"] = list(evidence_workflow_action_queue)
        if "evidence_workflow_action_summary" not in guidance:
            guidance["evidence_workflow_action_summary"] = dict(evidence_workflow_action_summary)
        if (
            "workflow_targeting_summary" not in guidance
            and isinstance(workflow_targeting_summary, dict)
        ):
            guidance["workflow_targeting_summary"] = dict(workflow_targeting_summary)
        if (
            "document_workflow_execution_summary" not in guidance
            and isinstance(document_workflow_execution_summary, dict)
        ):
            guidance["document_workflow_execution_summary"] = dict(document_workflow_execution_summary)
        if (
            "document_execution_drift_summary" not in guidance
            and isinstance(document_execution_drift_summary, dict)
        ):
            guidance["document_execution_drift_summary"] = dict(document_execution_drift_summary)
        if (
            "document_grounding_improvement_summary" not in guidance
            and isinstance(document_grounding_improvement_summary, dict)
        ):
            guidance["document_grounding_improvement_summary"] = dict(document_grounding_improvement_summary)
        if (
            "document_grounding_lane_outcome_summary" not in guidance
            and isinstance(document_grounding_lane_outcome_summary, dict)
        ):
            guidance["document_grounding_lane_outcome_summary"] = dict(document_grounding_lane_outcome_summary)
        if (
            "document_drafting_next_action" not in guidance
            and isinstance(document_drafting_next_action, dict)
            and document_drafting_next_action
        ):
            guidance["document_drafting_next_action"] = dict(document_drafting_next_action)
        existing_queue = (
            guidance.get("workflow_action_queue")
            if isinstance(guidance.get("workflow_action_queue"), list)
            else []
        )
        drift_flag = bool((document_execution_drift_summary or {}).get("drift_flag"))
        if drift_flag:
            top_targeted_claim_element = str(
                (document_execution_drift_summary or {}).get("top_targeted_claim_element") or ""
            ).strip()
            first_executed_claim_element = str(
                (document_execution_drift_summary or {}).get("first_executed_claim_element") or ""
            ).strip()
            drift_action = {
                "rank": 1,
                "phase_name": "document_generation",
                "status": "warning",
                "action": "Realign drafting to the top targeted claim element before further revisions.",
                "focus_areas": [
                    item
                    for item in [top_targeted_claim_element, first_executed_claim_element]
                    if item
                ][:3],
                "top_targeted_claim_element": top_targeted_claim_element,
                "first_executed_claim_element": first_executed_claim_element,
            }
            if not any(
                isinstance(item, dict)
                and str(item.get("action") or "").strip().lower()
                == drift_action["action"].strip().lower()
                for item in existing_queue
            ):
                guidance["workflow_action_queue"] = [drift_action, *existing_queue]
                existing_queue = guidance["workflow_action_queue"]
        if evidence_workflow_action_queue and not existing_queue:
            guidance["workflow_action_queue"] = [
                {
                    "rank": int(action.get("rank") or index + 1),
                    "phase_name": str(action.get("phase_name") or "graph_analysis").strip() or "graph_analysis",
                    "status": str(action.get("status") or "warning").strip().lower() or "warning",
                    "action": str(action.get("action") or "").strip(),
                    "focus_areas": list(action.get("focus_areas") or [])[:3],
                }
                for index, action in enumerate(evidence_workflow_action_queue)
                if isinstance(action, dict) and str(action.get("action") or "").strip()
            ]
        return guidance

    intake_case_summary = build_intake_case_review_summary(mediator)
    optimization_workflow_targeting_summary = (
        optimization_report.get("workflow_targeting_summary")
        if isinstance(optimization_report.get("workflow_targeting_summary"), dict)
        else {}
    )
    intake_sections = (
        intake_case_summary.get("intake_sections")
        if isinstance(intake_case_summary.get("intake_sections"), dict)
        else {}
    )
    question_summary = (
        intake_case_summary.get("question_candidate_summary")
        if isinstance(intake_case_summary.get("question_candidate_summary"), dict)
        else {}
    )
    claim_packet_summary = (
        intake_case_summary.get("claim_support_packet_summary")
        if isinstance(intake_case_summary.get("claim_support_packet_summary"), dict)
        else {}
    )
    evidence_workflow_action_queue = (
        intake_case_summary.get("evidence_workflow_action_queue")
        if isinstance(intake_case_summary.get("evidence_workflow_action_queue"), list)
        else []
    )
    evidence_workflow_action_summary = (
        intake_case_summary.get("evidence_workflow_action_summary")
        if isinstance(intake_case_summary.get("evidence_workflow_action_summary"), dict)
        else {}
    )
    workflow_targeting_summary = (
        optimization_workflow_targeting_summary
        if optimization_workflow_targeting_summary
        else (
            intake_case_summary.get("workflow_targeting_summary")
            if isinstance(intake_case_summary.get("workflow_targeting_summary"), dict)
            else {}
        )
    )
    document_workflow_execution_summary = (
        optimization_report.get("document_workflow_execution_summary")
        if isinstance(optimization_report.get("document_workflow_execution_summary"), dict)
        else (
            intake_case_summary.get("document_workflow_execution_summary")
            if isinstance(intake_case_summary.get("document_workflow_execution_summary"), dict)
            else {}
        )
    )
    document_execution_drift_summary = (
        optimization_report.get("document_execution_drift_summary")
        if isinstance(optimization_report.get("document_execution_drift_summary"), dict)
        else (
            intake_case_summary.get("document_execution_drift_summary")
            if isinstance(intake_case_summary.get("document_execution_drift_summary"), dict)
            else {}
        )
    )
    document_grounding_improvement_summary = (
        optimization_report.get("document_grounding_improvement_summary")
        if isinstance(optimization_report.get("document_grounding_improvement_summary"), dict)
        else (
            intake_case_summary.get("document_grounding_improvement_summary")
            if isinstance(intake_case_summary.get("document_grounding_improvement_summary"), dict)
            else {}
        )
    )
    document_grounding_lane_outcome_summary = (
        optimization_report.get("document_grounding_lane_outcome_summary")
        if isinstance(optimization_report.get("document_grounding_lane_outcome_summary"), dict)
        else (
            intake_case_summary.get("document_grounding_lane_outcome_summary")
            if isinstance(intake_case_summary.get("document_grounding_lane_outcome_summary"), dict)
            else {}
        )
    )
    document_drafting_next_action = (
        intake_case_summary.get("document_drafting_next_action")
        if isinstance(intake_case_summary.get("document_drafting_next_action"), dict)
        else {}
    )
    candidate_claims = _coerce_list(intake_case_summary.get("candidate_claims"))
    claim_types = _unique_preserving_order(
        str((claim or {}).get("claim_type") or "").strip()
        for claim in candidate_claims
        if isinstance(claim, dict)
    )
    intake_focus_areas = _unique_preserving_order(
        str(section_name)
        for section_name, payload in intake_sections.items()
        if isinstance(payload, dict) and str(payload.get("status") or "").strip().lower() != "complete"
    )
    graph_focus_areas = _unique_preserving_order(
        [
            *claim_types,
            *[
                "claim_support_packets"
                if int(claim_packet_summary.get("unsupported_element_count") or 0) > 0
                else ""
            ],
            *[
                str((action or {}).get("claim_element_label") or (action or {}).get("claim_element_id") or "").strip()
                for action in evidence_workflow_action_queue
                if isinstance(action, dict)
            ],
        ]
    )
    document_focus_areas = _unique_preserving_order(
        [
            str(section_name)
            for section_name, payload in dict(drafting_readiness.get("sections") or {}).items()
            if isinstance(payload, dict) and str(payload.get("status") or "").strip().lower() != "ready"
        ]
    )
    cross_phase_findings = []
    if intake_focus_areas and graph_focus_areas:
        cross_phase_findings.append(
            "Intake follow-up gaps remain linked to graph support gaps, so unresolved intake sections should be closed before final drafting."
        )
    if graph_focus_areas and document_focus_areas:
        cross_phase_findings.append(
            "Graph support issues are still affecting drafting readiness, especially in claims-for-relief and chronology-dependent allegations."
        )
    workflow_action_queue: List[Dict[str, Any]] = []
    if bool(document_execution_drift_summary.get("drift_flag")):
        top_targeted_claim_element = str(
            document_execution_drift_summary.get("top_targeted_claim_element") or ""
        ).strip()
        first_executed_claim_element = str(
            document_execution_drift_summary.get("first_executed_claim_element") or ""
        ).strip()
        workflow_action_queue.append(
            {
                "rank": 1,
                "phase_name": "document_generation",
                "status": "warning",
                "action": "Realign drafting to the top targeted claim element before further revisions.",
                "focus_areas": [
                    item
                    for item in [top_targeted_claim_element, first_executed_claim_element]
                    if item
                ][:3],
                "top_targeted_claim_element": top_targeted_claim_element,
                "first_executed_claim_element": first_executed_claim_element,
            }
        )
    workflow_action_queue.extend(
        [
            *[
                {
                    "rank": int(action.get("rank") or index + 1),
                    "phase_name": str(action.get("phase_name") or "graph_analysis").strip() or "graph_analysis",
                    "status": str(action.get("status") or "warning").strip().lower() or "warning",
                    "action": str(action.get("action") or "").strip(),
                    "focus_areas": list(action.get("focus_areas") or [])[:3],
                    "claim_type": str(action.get("claim_type") or "").strip(),
                    "claim_element_id": str(action.get("claim_element_id") or "").strip(),
                }
                for index, action in enumerate(evidence_workflow_action_queue[:2])
                if isinstance(action, dict) and str(action.get("action") or "").strip()
            ],
            *[
                item
                for item in [
                    {
                        "rank": 100,
                        "phase_name": "graph_analysis",
                        "status": "warning" if graph_focus_areas else "ready",
                        "action": "Close graph and claim-support gaps before final drafting.",
                        "focus_areas": graph_focus_areas[:3],
                    },
                    {
                        "rank": 101,
                        "phase_name": "intake_questioning",
                        "status": "warning" if intake_focus_areas else "ready",
                        "action": "Target remaining intake gaps that block graph-supported drafting.",
                        "focus_areas": intake_focus_areas[:3],
                    },
                    {
                        "rank": 102,
                        "phase_name": "document_generation",
                        "status": str(drafting_readiness.get("status") or "ready").strip().lower() or "ready",
                        "action": "Revise complaint sections still flagged by drafting readiness.",
                        "focus_areas": document_focus_areas[:3],
                    },
                ]
                if not (
                    item["phase_name"] == "graph_analysis"
                    and evidence_workflow_action_queue
                )
            ],
        ]
    )
    return {
        "workflow_phase_plan": dict(workflow_phase_plan or {}),
        "phase_scorecards": {
            "intake_questioning": {
                "status": "warning" if intake_focus_areas else "ready",
                "focus_areas": intake_focus_areas,
                "question_candidate_count": int(question_summary.get("count") or 0),
            },
            "graph_analysis": {
                "status": "warning" if graph_focus_areas else "ready",
                "focus_areas": graph_focus_areas,
                "unsupported_element_count": int(claim_packet_summary.get("unsupported_element_count") or 0),
                "evidence_workflow_action_count": int(evidence_workflow_action_summary.get("count") or 0),
            },
            "document_generation": {
                "status": str(drafting_readiness.get("status") or "ready").strip().lower() or "ready",
                "focus_areas": document_focus_areas,
                "warning_count": int(drafting_readiness.get("warning_count") or 0),
            },
        },
        "cross_phase_findings": cross_phase_findings,
        "workflow_action_queue": workflow_action_queue,
        "evidence_workflow_action_queue": list(evidence_workflow_action_queue),
        "evidence_workflow_action_summary": dict(evidence_workflow_action_summary),
        "workflow_targeting_summary": dict(workflow_targeting_summary),
        "document_workflow_execution_summary": dict(document_workflow_execution_summary),
        "document_execution_drift_summary": dict(document_execution_drift_summary),
        "document_grounding_improvement_summary": dict(document_grounding_improvement_summary),
        "document_grounding_lane_outcome_summary": dict(document_grounding_lane_outcome_summary),
        "document_drafting_next_action": dict(document_drafting_next_action),
        "complaint_type_generalization_summary": {
            "complaint_types": claim_types,
            "complaint_type_count": len(claim_types),
        },
        "document_handoff_summary": {
            "ready_for_document_optimization": str(drafting_readiness.get("status") or "").strip().lower() == "ready",
            "drafting_status": str(drafting_readiness.get("status") or "ready").strip().lower() or "ready",
            "blocking_warning_count": int(drafting_readiness.get("warning_count") or 0),
        },
    }
