"""Pure explicit legal-context selection on an authenticated owner's snapshot.

Access, keys, persistence and publication belong to the workspace owner. This
module copies its inputs and performs no I/O, model dispatch or authorization.
"""
from copy import deepcopy
from typing import Any, Mapping

from applications.legal_context_api import (
    APPLICABILITY_VALUES, LegalContextError, _DATE_FIELDS, _DISPUTED_TOKENS,
    _REJECTED_DEFAULTS, _UNKNOWN_TOKENS, _applicability_token, _current_context,
    _mark_dependencies_invalid, _snapshot_version, _token, project_legal_context,
)
from complaint_phases.dependency_graph import DependencyGraph, DependencyGraphBuilder
from complaint_phases.intake_case_file import apply_explicit_legal_context
from integrations.ipfs_datasets.legal import empty_legal_context


def _semantic_context(case_file):
    context = _current_context(case_file)
    jurisdiction = str(context.get("jurisdiction") or "unknown")
    empty = empty_legal_context()
    return {
        "jurisdiction": jurisdiction,
        "jurisdiction_explicit": bool(context.get("jurisdiction_explicit")),
        "jurisdiction_applicability": str(context.get("jurisdiction_applicability")
            or ("explicit" if context.get("jurisdiction_explicit") else "unknown")),
        "candidate_jurisdiction": context.get("candidate_jurisdiction"),
        "forum": deepcopy(case_file.get("legal_context_forum") or
            {"value": "unknown", "applicability": "unknown"}),
        "applicability": str(case_file.get("legal_context_applicability") or "unknown"),
        "applicability_selected": "legal_context_applicability" in case_file,
        **{field: deepcopy(context.get(field, empty[field])) for field in _DATE_FIELDS},
    }


def apply_legal_context_selection(
    case_file: Mapping[str, Any], updates: Mapping[str, Any], *,
    dependency_graph: DependencyGraph | None = None,
) -> dict:
    """Return a copied context/DG transition; never mutate the supplied snapshot."""
    if not isinstance(case_file, dict) or not isinstance(updates, Mapping):
        raise LegalContextError("legal_context_field")
    body = dict(updates)
    if any(str(key) in _REJECTED_DEFAULTS or str(key).startswith("governing_") for key in body):
        raise LegalContextError("governing_law_not_admitted")
    allowed = {"expected_context_revision", "jurisdiction", "forum", "applicability", *_DATE_FIELDS}
    if set(body) - allowed:
        raise LegalContextError("legal_context_field")
    for field in ("jurisdiction", "forum", "applicability"):
        if field in body and body[field] is not None and not isinstance(body[field], str):
            raise LegalContextError("legal_context_field")
    for field in _DATE_FIELDS:
        if field not in body:
            continue
        values = body[field]
        if field == "event_dates":
            if not isinstance(values, list):
                raise LegalContextError("legal_context_field")
        else:
            values = [values]
        if any(value is not None and not isinstance(value, (str, dict)) for value in values):
            raise LegalContextError("legal_context_field")
    previous = _current_context(case_file)
    revision = previous.get("context_revision", 0)
    expected = body.get("expected_context_revision")
    if type(revision) is not int or revision < 0 or type(expected) is not int or expected != revision:
        raise LegalContextError("legal_context_revision_conflict")
    if dependency_graph is not None and not isinstance(dependency_graph, DependencyGraph):
        raise LegalContextError("legal_dependency_refresh_unavailable")
    draft = deepcopy(case_file)
    graph = DependencyGraph.from_dict(deepcopy(dependency_graph.to_dict())) if dependency_graph is not None else None
    before = _semantic_context(draft)
    if len(body) == 1:
        return {"case_file": draft, "projection": project_legal_context(draft), "changed": False,
            "change": {}, "dependency_graph": graph, "dependency_refresh": None}
    for key in ("jurisdiction", "forum", "applicability"):
        if key in body and _token(body[key]).lower() in _REJECTED_DEFAULTS:
            raise LegalContextError("governing_law_not_admitted")
    if "applicability" in body:
        token = _token(body["applicability"]).lower()
        if token not in set(APPLICABILITY_VALUES) | _UNKNOWN_TOKENS | _DISPUTED_TOKENS:
            raise LegalContextError("applicability_not_admitted")
        overall = _applicability_token(token)
    else:
        overall = before["applicability"] if before["applicability"] in APPLICABILITY_VALUES else "unknown"

    jurisdiction_mode = _applicability_token(body["jurisdiction"]) if "jurisdiction" in body else "unchanged"
    forum_mode = _applicability_token(body["forum"]) if "forum" in body else "unchanged"
    if overall == "disputed":
        jurisdiction_mode = "disputed" if jurisdiction_mode == "explicit" else jurisdiction_mode
        forum_mode = "disputed" if forum_mode == "explicit" else forum_mode
    if overall == "unknown" and "applicability" in body:
        jurisdiction_mode = "unknown" if jurisdiction_mode == "explicit" else jurisdiction_mode
        forum_mode = "unknown" if forum_mode == "explicit" else forum_mode

    _snapshot_version(draft)
    law_updates = {field: body[field] for field in _DATE_FIELDS if field in body}
    if jurisdiction_mode != "unchanged":
        law_updates["jurisdiction"] = _token(body["jurisdiction"]) if jurisdiction_mode == "explicit" else ""
    if law_updates:
        # Call the canonical pure intake owner, not Mediator's side-effecting
        # wrapper (which would refresh a live graph before transaction admission).
        apply_explicit_legal_context(draft, **law_updates)
    context = _current_context(draft)
    if jurisdiction_mode == "explicit":
        known = str(context.get("jurisdiction") or "unknown") != "unknown"
        context["jurisdiction_applicability"] = "explicit" if known else "unknown"
        context.pop("candidate_jurisdiction", None)
    elif jurisdiction_mode in {"unknown", "disputed"}:
        context.update(jurisdiction="unknown", jurisdiction_explicit=False,
            jurisdiction_applicability=jurisdiction_mode,
            candidate_jurisdiction=_token(body["jurisdiction"]) or jurisdiction_mode)
    forum = deepcopy(draft.get("legal_context_forum") or {"value": "unknown", "applicability": "unknown"})
    if forum_mode == "explicit":
        forum = {"value": _token(body["forum"]), "applicability": "explicit"}
    elif forum_mode == "disputed":
        forum = {"value": "disputed", "applicability": "disputed", "candidate": _token(body["forum"])}
    elif forum_mode == "unknown":
        forum = {"value": "unknown", "applicability": "unknown"}
    jurisdiction_applicability = str(context.get("jurisdiction_applicability")
        or ("explicit" if context.get("jurisdiction_explicit") else "unknown"))
    if overall == "explicit" and (jurisdiction_applicability == "disputed" or forum.get("applicability") == "disputed"):
        overall = "disputed"
    elif overall == "explicit" and jurisdiction_applicability != "explicit":
        overall = "unknown"
    context["status"] = overall if overall in {"unknown", "disputed"} else (
        "explicit" if str(context.get("jurisdiction") or "unknown") != "unknown" else "unknown")
    draft["legal_context"] = context
    draft["legal_context_forum"] = forum
    draft["legal_context_applicability"] = overall
    after = _semantic_context(draft)
    if before == after:
        original = deepcopy(case_file)
        return {"case_file": original, "projection": project_legal_context(original), "changed": False,
            "change": {}, "dependency_graph": graph, "dependency_refresh": None}

    changed_fields = [field for field in after if before[field] != after[field]]
    _mark_dependencies_invalid(draft, bump=False, reason="legal_context_change")
    context = _current_context(draft)
    context["context_revision"] = revision + 1
    context["changed_fields"] = changed_fields
    draft["legal_context"] = context
    # This transition invalidates the prior snapshot without acquiring or
    # re-admitting authority sources. Existing mediator refreshes can still
    # re-admit sources in the same call under their separate owner contract.
    change = {"context_changed": True}
    if any(field.startswith("jurisdiction") or field == "candidate_jurisdiction" for field in changed_fields):
        change["jurisdiction_changed"] = True
    changed_dates = [field for field in _DATE_FIELDS if field in changed_fields]
    if changed_dates:
        change.update(date_changed=True, date_roles=changed_dates)
    if "forum" in changed_fields:
        change["forum_changed"] = True
    if "applicability" in changed_fields or "applicability_selected" in changed_fields:
        change["applicability_changed"] = True
    try:
        report = DependencyGraphBuilder().refresh_affected_dependencies(graph, change) if graph is not None else None
    except Exception as exc:
        raise LegalContextError("legal_dependency_refresh_unavailable") from exc
    return {"case_file": draft, "projection": project_legal_context(draft), "changed": True,
        "change": change, "dependency_graph": graph, "dependency_refresh": report}

