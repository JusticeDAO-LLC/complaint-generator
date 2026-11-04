from __future__ import annotations

import ast
import contextvars
import errno
import fcntl
import inspect
import json
import os
import re
import shutil
import stat
import subprocess
import threading
import tempfile
import tomllib
import uuid
import zipfile
import hashlib
import hmac
from base64 import b64encode
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Protocol, Sequence, Set
from urllib.parse import urlencode, urlsplit, urlunsplit
from xml.sax.saxutils import escape

from complaint_phases.legal_document import parse_legal_document
from integrations.ipfs_datasets.loader import import_attr_optional, import_failure_message
from lib.runtime_ownership import require_module_ownership


def _legal_source_availability_snapshot() -> Dict[str, Any]:
    if os.getenv("COMPLAINT_USE_IPFS_LEGAL_STATUS") == "1":
        try:
            from integrations.ipfs_datasets.legal import LEGAL_SOURCE_AVAILABILITY as availability

            return deepcopy(availability or {})
        except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    return {
        "federal_statutes": True,
        "federal_regulations": True,
        "case_law": True,
        "state_statutes": True,
        "administrative_rules": True,
    }


def _llm_router_status_snapshot() -> Dict[str, Any]:
    if os.getenv("COMPLAINT_USE_IPFS_LLM_ROUTER_STATUS") == "1":
        try:
            from integrations.ipfs_datasets.llm import LLM_ROUTER_AVAILABLE, llm_router_status

            status = llm_router_status(
                provider=os.getenv("COMPLAINT_LLM_PROVIDER") or DEFAULT_LLM_DRAFT_PROVIDER,
                model_name=os.getenv("COMPLAINT_LLM_MODEL") or DEFAULT_LLM_DRAFT_MODELS_BY_PROVIDER.get(DEFAULT_LLM_DRAFT_PROVIDER, ""),
                perform_probe=False,
            )
            status = dict(status or {})
            status.setdefault("backend_available", bool(LLM_ROUTER_AVAILABLE))
            status.setdefault("status", "available" if LLM_ROUTER_AVAILABLE else "unavailable")
            return status
        except Exception:
            pass
    return {
        "status": "policy_only",
        "operation": "llm_router_status",
        "backend_available": False,
        "implementation_status": "degraded_local",
    }


def _leanstral_status_snapshot() -> Dict[str, Any]:
    try:
        from integrations.ipfs_datasets.loader import import_module_optional

        module, error = import_module_optional("ipfs_accelerate_py")
        if module is not None:
            return {
                "status": "available",
                "backend_available": True,
                "module_path": str(getattr(module, "__file__", "") or ""),
                "model": "leanstral",
                "provider": "ipfs_accelerate_py",
            }
        return {
            "status": "unavailable",
            "backend_available": False,
            "error": str(error or ""),
            "model": "leanstral",
            "provider": "ipfs_accelerate_py",
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "backend_available": False,
            "error": str(exc),
            "model": "leanstral",
            "provider": "ipfs_accelerate_py",
        }


def _run_draft_logic_pipeline_safely(body: str, *, state: Optional[str] = None) -> Dict[str, Any]:
    """Run the draft logic pipeline if the integration layer is available.

    Gated behind ``COMPLAINT_USE_DRAFT_LOGIC_PIPELINE=1`` so that offline and
    test environments are not blocked by network calls.  Falls back to a
    minimal proof report dict on any import or runtime error.
    """
    if os.getenv("COMPLAINT_USE_DRAFT_LOGIC_PIPELINE") != "1":
        return {
            "proof_status": "needs_review",
            "contradiction_count": 0,
            "chronology_blocked": False,
            "ungrounded_assertions": [],
            "ungrounded_assertion_count": 0,
            "corpus_coverage_percent": None,
            "norms": [],
            "policy_violations": [],
            "policy_warnings": [],
            "has_blockers": False,
            "predicate_count": 0,
            "pipeline_version": "draft-logic-pipeline-disabled",
            "errors": [],
        }
    try:
        from integrations.ipfs_datasets.draft_logic_pipeline import run_pipeline

        return run_pipeline(body, state=state, allow_live_scrape_fallback=False)
    except Exception as exc:
        return {
            "proof_status": "needs_review",
            "contradiction_count": 0,
            "chronology_blocked": False,
            "ungrounded_assertions": [],
            "ungrounded_assertion_count": 0,
            "corpus_coverage_percent": None,
            "norms": [],
            "policy_violations": [],
            "policy_warnings": [],
            "has_blockers": False,
            "predicate_count": 0,
            "pipeline_version": "draft-logic-pipeline-unavailable",
            "errors": [str(exc)],
        }


def _run_hybrid_reasoning_safely(payload: Dict[str, Any]) -> Dict[str, Any]:
    predicates = [
        dict(item) for item in list(payload.get("predicates") or [])
        if isinstance(item, dict)
    ]
    claim_support_temporal_handoff = dict(payload.get("claim_support_temporal_handoff") or {})
    contradiction_count = sum(
        1
        for item in predicates
        if str(item.get("predicate_type") or "") in {"contradiction_candidate", "temporal_issue"}
    )
    unsupported_claim_elements = [
        item for item in predicates
        if str(item.get("predicate_type") or "") == "claim_element"
        and str(item.get("coverage_status") or "").strip().lower() != "supported"
    ]
    chronology_blocked = bool(
        claim_support_temporal_handoff.get("unresolved_temporal_issue_count")
        or claim_support_temporal_handoff.get("timeline_issue_ids")
        or claim_support_temporal_handoff.get("temporal_issue_ids")
    )
    proof_status = "passed" if not (unsupported_claim_elements or contradiction_count or chronology_blocked) else "needs_review"
    temporal_facts = [
        item for item in predicates
        if str(item.get("predicate_type") or "") == "temporal_fact"
    ]
    theorem_export_metadata = {
        "contract_version": "claim_support_temporal_handoff_v1",
        "claim_type": str(claim_support_temporal_handoff.get("claim_type") or ""),
        "claim_element_id": str(claim_support_temporal_handoff.get("claim_element_id") or ""),
        "chronology_blocked": chronology_blocked,
        "event_ids": list(claim_support_temporal_handoff.get("event_ids") or []),
        "temporal_issue_ids": list(claim_support_temporal_handoff.get("temporal_issue_ids") or []),
    }
    return {
        "status": "success",
        "backend_available": bool(os.getenv("COMPLAINT_USE_IPFS_LOGIC_BRIDGE") == "1"),
        "implementation_status": "degraded_local",
        "result": {
            "formalism": "tdfol_dcec_bridge_v1",
            "claim_types": sorted({str(item.get("claim_type") or "").strip() for item in predicates if str(item.get("claim_type") or "").strip()}),
            "tdfol_formulas": [f"Fact(event_{index})" for index, _ in enumerate(temporal_facts, start=1)],
            "dcec_formulas": [f"Happens(event_{index},t)" for index, _ in enumerate(temporal_facts, start=1)],
            "theorem_export_metadata": theorem_export_metadata,
            "timeline_event_count": len(temporal_facts),
            "temporal_relation_count": 0,
            "contradiction_signal_count": contradiction_count,
            "reasoning_mode": "local_bridge_fallback",
            "compiler_bridge_available": bool(os.getenv("COMPLAINT_USE_IPFS_LOGIC_BRIDGE") == "1"),
            "proof_artifact": {
                "available": True,
                "status": proof_status,
                "proof_status": proof_status,
                "violation_count": len(unsupported_claim_elements) + contradiction_count + int(chronology_blocked),
                "theorem_export_metadata": theorem_export_metadata,
            },
            "local_logic_snapshot": {
                "predicate_count": len(predicates),
                "unsupported_claim_element_count": len(unsupported_claim_elements),
            },
            "claim_reasoning_review": deepcopy(payload.get("claim_reasoning_review") or {}),
            "compiler_bridge_path": "complaint_workspace_local_bridge",
        },
        "payload_keys": sorted(payload.keys()),
        "predicate_count": len(predicates),
        "temporal_reasoning_payload": {
            "formalism": "tdfol_dcec_bridge_v1",
            "tdfol_formula_count": len(temporal_facts),
            "dcec_formula_count": len(temporal_facts),
            "timeline_events": deepcopy(temporal_facts),
            "theorem_export_metadata": theorem_export_metadata,
        },
    }

try:
    import anyio
except ModuleNotFoundError:
    class _AnyioFallback:
        @staticmethod
        def run(func: Any, *args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                raise RuntimeError("anyio is required for async complaint workspace operations in this environment.")
            return result

    anyio = _AnyioFallback()


def _require_ipfs_attr(module_name: str, attr_name: str) -> Any:
    value, error = import_attr_optional(module_name, attr_name)
    if value is not None and error is None:
        return value
    message = import_failure_message(error) or f"missing attribute {attr_name}"
    raise ImportError(f"Unable to import {module_name}.{attr_name}: {message}")


def _prefer_checkout(repo_root: Path, name: str) -> Path:
    external = repo_root / "external" / name
    if external.exists():
        return external
    return repo_root / name


MODULE_OWNERSHIP = require_module_ownership("applications.complaint_workspace")
RUNTIME_ENTRYPOINT_ROLE = MODULE_OWNERSHIP.role
DEFAULT_USER_ID = "did:key:anonymous"
DEFAULT_UI_UX_OPTIMIZER_METHOD = "actor_critic"
DEFAULT_UI_UX_OPTIMIZER_PRIORITY = 90
DEFAULT_LLM_DRAFT_PROVIDER = "codex_cli"
DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN: List[str] = [
    "codex_cli",
    "copilot_cli",
    "hf_inference_api",
]
DEFAULT_LLM_DRAFT_MODELS_BY_PROVIDER: Dict[str, str] = {
    "codex": "gpt-5.3-codex",
    "codex_cli": "gpt-5.3-codex",
    "copilot_cli": "gpt-5-mini",
}
DEFAULT_LLM_DRAFT_TIMEOUT_SECONDS = 20
DEFAULT_LLM_DRAFT_TIMEOUTS_BY_PROVIDER: Dict[str, int] = {
    "codex": 90,
    "codex_cli": 90,
    "copilot_cli": 45,
    "copilot_sdk": 45,
    "openai": 30,
    "openai_api": 30,
    "hf_inference_api": 30,
    "hf_inference": 30,
    "hf_api": 30,
}
# Citation-link identity precedence keeps explicit IDs stable before looser source/url fallback keys.
MIKE_CITATION_KEY_FIELD_PRECEDENCE: tuple[str, ...] = ("citation_id", "id", "source_id", "url")
# v3 adds router-policy, grounding, provenance, and logic-review fields on the
# existing Mike handoff/sync/status contracts while keeping the same route names.
MIKE_STATUS_CONTRACT_VERSION = "complaint-mike-status-v4"
MIKE_HANDOFF_CONTRACT_VERSION = "complaint-mike-handoff-v4"
MIKE_SYNC_CONTRACT_VERSION = "complaint-mike-sync-v4"
DEFAULT_COMPLAINT_MCP_CONNECTOR_URL = "http://localhost:8000/api/complaint-workspace/mcp/rpc"
MIKE_MCP_CONNECTOR_TOOLS: tuple[str, ...] = (
    "complaint.generate_grounded_text",
    "complaint.search_corpus",
    "complaint.get_handoff",
    "complaint.sync_draft",
)
MAX_MIKE_HANDOFF_PARAGRAPHS = 80
MAX_MIKE_WEAK_LINKS_DISPLAY = 3
VALID_MIKE_STRUCTURED_DELTA_OPS: Set[str] = {"insert", "delete", "replace", "edit", "move"}
DEFAULT_MIKE_GROUNDING_MODE = "legal_corpus_only"
STRICT_MIKE_GROUNDING_MODES: Set[str] = {"legal_corpus_only", "strict_legal_containment"}
MIN_MIKE_FACTUAL_ASSERTION_WORDS = 5
MAX_MIKE_GROUNDING_EXAMPLES = 8
MAX_MIKE_AUTHORITY_EXAMPLES = 12
MIKE_SUBSTANTIVE_ASSERTION_TYPES: Set[str] = {
    "factual_statement",
    "legal_conclusion",
    "temporal_assertion",
    "requested_relief",
}
MIKE_TEMPORAL_ASSERTION_KEYWORDS: tuple[str, ...] = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "before",
    "after",
    "later",
    "earlier",
    "timeline",
    "date",
)
MIKE_MISSING_TIMELINE_ISSUE_ID = "missing_timeline"
MIKE_WORKFLOW_STATE_LABELS: Dict[str, str] = {
    "not_handed_off": "Not handed off",
    "handoff_pending_sync": "Handoff pending sync",
    "synced_clean": "Synced clean",
    "synced_with_conflicts": "Synced with conflicts",
}
MIKE_SKILL_ASSET_MANIFEST_VERSION = "complaint-mike-skill-assets-v2"
DEFAULT_MIKE_SKILL_ASSET_MANIFEST: List[Dict[str, Any]] = [
    {
        "skill_asset_id": "complaint-grounding",
        "name": "Complaint grounding review",
        "capability": "legal_corpus_review",
        "adapter": "integrations/ipfs_datasets/legal.py",
        "required_for_grounding_modes": ["legal_corpus_only", "strict_legal_containment"],
    },
    {
        "skill_asset_id": "complaint-logic",
        "name": "Complaint theorem export",
        "capability": "formal_logic_review",
        "adapter": "integrations/ipfs_datasets/logic.py",
        "required_for_grounding_modes": ["legal_corpus_only", "strict_legal_containment"],
    },
    {
        "skill_asset_id": "complaint-corpus-search",
        "name": "Complaint legal corpus search",
        "capability": "legal_corpus_search",
        "adapter": "integrations/ipfs_datasets/search.py",
        "required_for_grounding_modes": ["legal_corpus_only", "strict_legal_containment"],
    },
    {
        "skill_asset_id": "complaint-policy-rules",
        "name": "Complaint containment policy rules",
        "capability": "strict_containment_policy",
        "adapter": "integrations/ipfs_datasets/policy_rules.py",
        "required_for_grounding_modes": ["legal_corpus_only", "strict_legal_containment"],
    },
    {
        "skill_asset_id": "complaint-authority-graphs",
        "name": "Complaint authority graph enrichment",
        "capability": "authority_graph_enrichment",
        "adapter": "integrations/ipfs_datasets/graphs.py",
        "required_for_grounding_modes": ["legal_corpus_only", "strict_legal_containment"],
    },
    {
        "skill_asset_id": "complaint-router",
        "name": "Complaint router policy",
        "capability": "workspace_llm_router",
        "adapter": "integrations/ipfs_datasets/llm.py",
        "required_for_grounding_modes": ["legal_corpus_only", "strict_legal_containment"],
    },
    {
        "skill_asset_id": "complaint-draft-logic-pipeline",
        "name": "Complaint draft-text → formal-logic → theorem-prover pipeline",
        "capability": "draft_logic_pipeline",
        "adapter": "integrations/ipfs_datasets/draft_logic_pipeline.py",
        "required_for_grounding_modes": ["legal_corpus_only", "strict_legal_containment"],
    },
    {
        "skill_asset_id": "complaint-corpus-containment",
        "name": "Complaint legal corpus containment (assertion grounding)",
        "capability": "legal_corpus_containment",
        "adapter": "integrations/ipfs_datasets/legal.py",
        "required_for_grounding_modes": ["legal_corpus_only", "strict_legal_containment"],
    },
    {
        "skill_asset_id": "complaint-mike-llm-patch",
        "name": "Mike LLM router monkey-patch",
        "capability": "mike_llm_router_patch",
        "adapter": "integrations/mike/llm_patch.py",
        "required_for_grounding_modes": ["legal_corpus_only", "strict_legal_containment"],
    },
]
DEFAULT_UI_UX_SCREENSHOT_TARGET = "playwright/tests/complaint-flow.spec.js"

_DATA_DIR = Path(__file__).resolve().parent.parent / ".complaint_workspace"
_SESSION_DIR = _DATA_DIR / "sessions"

_INTAKE_QUESTIONS: List[Dict[str, str]] = [
    {
        "id": "party_name",
        "label": "Your name",
        "prompt": "Who is bringing the complaint?",
        "placeholder": "Jane Doe",
    },
    {
        "id": "opposing_party",
        "label": "Opposing party",
        "prompt": "Who are you filing against?",
        "placeholder": "Acme Corporation",
    },
    {
        "id": "protected_activity",
        "label": "Protected activity",
        "prompt": "What did you report, oppose, or request before the retaliation happened?",
        "placeholder": "Reported discrimination to HR",
    },
    {
        "id": "adverse_action",
        "label": "Adverse action",
        "prompt": "What happened to you afterward?",
        "placeholder": "Termination two days later",
    },
    {
        "id": "timeline",
        "label": "Timeline",
        "prompt": "When did the key events happen?",
        "placeholder": "Complaint on March 8, termination on March 10",
    },
    {
        "id": "harm",
        "label": "Harm",
        "prompt": "What harm did you suffer?",
        "placeholder": "Lost wages, lost benefits, emotional distress",
    },
    {
        "id": "court_header",
        "label": "Court caption",
        "prompt": "If you know the court, what district caption should appear on the complaint?",
        "placeholder": "FOR THE NORTHERN DISTRICT OF CALIFORNIA",
    },
]

_CLAIM_ELEMENTS: List[Dict[str, str]] = [
    {"id": "protected_activity", "label": "Protected activity"},
    {"id": "employer_knowledge", "label": "Employer knowledge"},
    {"id": "adverse_action", "label": "Adverse action"},
    {"id": "causation", "label": "Causal link"},
    {"id": "harm", "label": "Damages"},
]
DEFAULT_INTAKE_QUESTIONS: List[Dict[str, str]] = deepcopy(_INTAKE_QUESTIONS)
DEFAULT_CLAIM_ELEMENTS: List[Dict[str, str]] = deepcopy(_CLAIM_ELEMENTS)
ORIGINAL_COMPLAINT_QUESTION_ID = "original_complaint"
ORIGINAL_COMPLAINT_SCHEMA = "complaint-generator.original-complaint.v1"
INTAKE_SESSION_SCHEMA = "complaint-generator.intake-session.v2"
_NARRATIVE_INQUIRY: Dict[str, str] = {
    "id": ORIGINAL_COMPLAINT_QUESTION_ID,
    "label": "Complaint narrative",
    "prompt": "What happened?",
    "placeholder": "Describe the events in your own words",
}


def _empty_original_complaint() -> Dict[str, Any]:
    return {
        "schema_version": ORIGINAL_COMPLAINT_SCHEMA,
        "text": "",
        "revision": 0,
        "revisions": [],
    }


def migrate_original_complaint(state: Dict[str, Any]) -> Dict[str, Any]:
    """Add the versioned narrative without rewriting a saved seven-field session.

    Existing ``intake_answers`` keys and values stay as stored. A missing or
    unversioned narrative becomes ``original_complaint`` and is not copied
    from ``party_name``.
    """

    answers = state.get("intake_answers")
    if not isinstance(answers, dict):
        state["intake_answers"] = {}
    current = state.get("original_complaint")
    if isinstance(current, str):
        text = current.strip()
        state["original_complaint"] = {
            "schema_version": ORIGINAL_COMPLAINT_SCHEMA,
            "text": text,
            "revision": 1 if text else 0,
            "revisions": (
                [
                    {
                        "revision": 1,
                        "text": text,
                        "captured_at": str(state.get("updated_at") or ""),
                        "source": "legacy_string",
                    }
                ]
                if text
                else []
            ),
        }
    elif isinstance(current, dict):
        text = str(current.get("text") or "").strip()
        revisions = current.get("revisions")
        if not isinstance(revisions, list):
            revisions = []
        else:
            revisions = [item for item in revisions if isinstance(item, dict)]
        try:
            revision = int(current.get("revision") or 0)
        except (TypeError, ValueError):
            revision = 0
        if text and revision <= 0:
            revision = len(revisions) or 1
        if text and not revisions:
            revisions = [
                {
                    "revision": revision or 1,
                    "text": text,
                    "captured_at": str(current.get("captured_at") or state.get("updated_at") or ""),
                    "source": "legacy_object",
                }
            ]
            revision = revision or 1
        current["schema_version"] = ORIGINAL_COMPLAINT_SCHEMA
        current["text"] = text
        current["revision"] = revision
        current["revisions"] = revisions
        state["original_complaint"] = current
    else:
        state["original_complaint"] = _empty_original_complaint()
    state["intake_session_schema"] = INTAKE_SESSION_SCHEMA
    return state


def _graph_revision_label(graph: Mapping[str, Any], fallback: str) -> str:
    for key in ("graph_revision", "revision", "graph_version"):
        value = graph.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _browser_resume_record(state: Mapping[str, Any]) -> Dict[str, Any]:
    """Exact interview fields sealed for a later process. This does not dispatch."""

    interview = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
    pending = interview.get("pending_inquiry") if isinstance(interview.get("pending_inquiry"), dict) else {}
    factual = interview.get("knowledge_graph") if isinstance(interview.get("knowledge_graph"), dict) else {}
    legal = interview.get("dependency_graph") if isinstance(interview.get("dependency_graph"), dict) else {}
    gaps = state.get("deferred_gaps")
    if not isinstance(gaps, list):
        gaps = interview.get("preserved_gaps") if isinstance(interview.get("preserved_gaps"), list) else interview.get("capped_reasons")
    if not isinstance(gaps, list):
        gaps = []
    corrections = state.get("factual_corrections") if isinstance(state.get("factual_corrections"), list) else []
    consent = state.get("operation_consent") if isinstance(state.get("operation_consent"), dict) else {}
    receipts: List[Dict[str, Any]] = []
    router = state.get("intake_router") if isinstance(state.get("intake_router"), dict) else {}
    for item in router.get("receipts") or []:
        if isinstance(item, dict):
            receipts.append(dict(item))
    history = [dict(item) for item in (state.get("intake_history") or []) if isinstance(item, dict)]
    return {
        "schema": "gui-encrypted-interview-resume-v1",
        "case_id": _state_case_id(state, str(state.get("user_id") or "")),
        "session_revision": interview.get("session_revision", 0),
        "pending_inquiry": dict(pending),
        "consent": dict(consent),
        "factual_graph": dict(factual),
        "legal_graph": dict(legal),
        "factual_graph_revision": _graph_revision_label(factual, "unknown"),
        "legal_graph_revision": _graph_revision_label(legal, "unknown"),
        "deferred_gaps": [dict(item) if isinstance(item, dict) else item for item in gaps],
        "corrections": [dict(item) if isinstance(item, dict) else item for item in corrections],
        "hook_receipts": receipts,
        "intake_history": history,
    }


def _browser_resume_record_complete(record: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(record, Mapping) or record.get("schema") != "gui-encrypted-interview-resume-v1":
        return False
    pending = record.get("pending_inquiry")
    required = ("case_id", "consent", "factual_graph", "legal_graph", "factual_graph_revision", "legal_graph_revision", "deferred_gaps", "corrections")
    if not isinstance(pending, Mapping) or not str(record.get("case_id") or "").strip():
        return False
    if not isinstance(record.get("consent"), Mapping):
        return False
    if not isinstance(record.get("factual_graph"), Mapping) or not isinstance(record.get("legal_graph"), Mapping):
        return False
    if not isinstance(record.get("deferred_gaps"), list) or not isinstance(record.get("corrections"), list):
        return False
    return all(key in record for key in required)


def _apply_browser_resume_record(state: Dict[str, Any], record: Mapping[str, Any]) -> None:
    pending = dict(record["pending_inquiry"])
    gaps = [dict(item) if isinstance(item, dict) else item for item in record["deferred_gaps"]]
    state["case_id"] = str(record["case_id"])
    state["operation_consent"] = dict(record["consent"])
    state["shared_interview"] = {
        "schema_version": "shared-interview-session-v1",
        "contract_version": "interview-transition-v1",
        "session_id": str(state.get("user_id") or record["case_id"]),
        "session_revision": record.get("session_revision", 0),
        "pending_inquiry": pending,
        "knowledge_graph": dict(record["factual_graph"]),
        "dependency_graph": dict(record["legal_graph"]),
        "preserved_gaps": gaps,
        "capped_reasons": gaps,
        "unknown_reasons": [],
        "legal_sufficiency": False,
    }
    state["deferred_gaps"] = gaps
    state["factual_corrections"] = [dict(item) if isinstance(item, dict) else item for item in record["corrections"]]
    state["factual_graph_binding"] = {
        "status": "bound",
        "revision": record["factual_graph_revision"],
        "graph_id": str((record["factual_graph"] or {}).get("graph_id") or ""),
    }
    state["legal_graph_binding"] = {
        "status": "bound",
        "revision": record["legal_graph_revision"],
        "graph_id": str((record["legal_graph"] or {}).get("graph_id") or ""),
    }
    state["intake_history"] = [dict(item) if isinstance(item, dict) else item for item in (record.get("intake_history") or [])]
    state["intake_router"] = {
        "receipts": [dict(item) if isinstance(item, dict) else item for item in (record.get("hook_receipts") or [])],
        "provider_replayed": False,
        "hooks_replayed": False,
    }
    state["explained_inquiry"] = {
        key: pending.get(key)
        for key in ("inquiry_id", "objective_id", "target_id", "target_revision", "question")
    }


def _encrypted_resume_refusal(user_id: Optional[str], receipt: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "status": receipt.get("status") or "refused",
        "message": str(receipt.get("code") or "refused"),
        "encrypted_resume": dict(receipt),
        "session": {"user_id": user_id},
        "stored_as_answer": False,
        "legal_sufficiency": False,
        "hooks_replayed": False,
        "messages_replayed": False,
        "browser_cache_used": False,
        "adaptive_inquiry": {
            "schema": "adaptive-inquiry-v1",
            "source": "encrypted_interview_snapshot",
            "pending": False,
            "from_fixed_intake_fields": False,
            "browser_cache_used": False,
        },
    }


def _grounded_owners_from_state(state: Mapping[str, Any]) -> Dict[str, Any]:
    """Read graph, receipt, inquiry, and stop owners already on the session."""

    interview = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
    factual = dict(state.get("factual_graph_binding") or {}) if isinstance(state.get("factual_graph_binding"), dict) else {}
    legal = dict(state.get("legal_graph_binding") or {}) if isinstance(state.get("legal_graph_binding"), dict) else {}
    knowledge = interview.get("knowledge_graph") if isinstance(interview.get("knowledge_graph"), dict) else {}
    dependency = interview.get("dependency_graph") if isinstance(interview.get("dependency_graph"), dict) else {}
    if not factual and knowledge:
        factual = {
            "revision": str(knowledge.get("graph_revision") or knowledge.get("graph_version") or ""),
            "graph_id": str(knowledge.get("graph_id") or ""),
            "content_hash": str(knowledge.get("content_hash") or ""),
        }
    if not legal and dependency:
        legal = {
            "revision": str(dependency.get("graph_revision") or dependency.get("revision") or dependency.get("graph_version") or ""),
            "graph_id": str(dependency.get("graph_id") or ""),
            "content_hash": str(dependency.get("content_hash") or ""),
        }
    pending = interview.get("pending_inquiry") if isinstance(interview.get("pending_inquiry"), dict) else None
    if pending is None and isinstance(state.get("explained_inquiry"), dict):
        pending = state.get("explained_inquiry")
    receipts: List[Dict[str, Any]] = []
    for container_name in ("intake_router", "router_trace"):
        container = state.get(container_name) if isinstance(state.get(container_name), dict) else {}
        pool = container.get("receipts")
        if isinstance(pool, list):
            receipts.extend(item for item in pool if isinstance(item, dict))
    sources: List[Any] = []
    if isinstance(pending, dict) and isinstance(pending.get("source_references"), list):
        sources = list(pending.get("source_references") or [])
    elif isinstance(state.get("source_references"), list):
        sources = list(state.get("source_references") or [])
    conditional = state.get("conditional_ir") if isinstance(state.get("conditional_ir"), dict) else interview.get("conditional_ir")
    external = state.get("external_dependencies") if isinstance(state.get("external_dependencies"), dict) else {
        "public_law": {"status": "external_unverified"},
        "ephemeral_index": {"status": "ephemeral"},
    }
    return {
        "factual_graph": factual,
        "legal_graph": legal,
        "source_references": sources,
        "conditional_ir": conditional if isinstance(conditional, dict) else {"status": "unknown"},
        "proof_statuses": [item for item in list(state.get("proof_history") or []) if isinstance(item, dict)] if isinstance(state.get("proof_history"), list) else [],
        "hook_receipts": receipts,
        "pending_inquiry": pending or {"status": "unknown"},
        "stop_policy": state.get("stop_policy") if isinstance(state.get("stop_policy"), dict) else None,
        "external_dependencies": external,
    }


def _narrative_record(state: Dict[str, Any]) -> Dict[str, Any]:
    migrate_original_complaint(state)
    record = state.get("original_complaint")
    if not isinstance(record, dict):
        record = _empty_original_complaint()
        state["original_complaint"] = record
    return record


def _structured_answers_present(state: Dict[str, Any]) -> bool:
    answers = state.get("intake_answers") or {}
    if not isinstance(answers, dict):
        return False
    return any(str(answers.get(question["id"]) or "").strip() for question in _INTAKE_QUESTIONS)


def _narrative_is_open(state: Dict[str, Any]) -> bool:
    """Ask for the story only at the start of a session that has no structured answers.

    Saved seven-field sessions stay on their next structured question. The
    narrative can still be revised by passing its own question id.
    """

    record = _narrative_record(state)
    if int(record.get("revision") or 0) > 0 or str(record.get("text") or "").strip():
        return False
    if _structured_answers_present(state):
        return False
    return True


_UNKNOWN_INTAKE_ANSWERS = {
    "unknown", "i do not know", "i don't know", "i dont know", "idk", "not sure",
    "unsure", "no idea", "do not know", "don't know", "n/a", "na", "none",
}


_NON_SOURCE_LABELS = {
    "",
    "intake",
    "assertion",
    "user",
    "user_assertion",
    "fixed_form",
    "narrative",
    "interview",
    "llm",
    "model",
    "unbound",
}
_FINITE_STOP_LABELS = {
    "paused": "paused",
    "cancelled": "cancelled",
    "provider_unavailable": "unavailable",
    "blocked_provider": "unavailable",
    "limit_reached": "capped",
    "saturated": "saturated",
    "needs_answer": "awaiting_user",
    "awaiting_user": "awaiting_user",
    "deferred_unknown": "unresolved",
    "deferred_needs_evidence": "unresolved",
    "needs_review": "unresolved",
    "no_progress": "capped",
    "complete": "saturated",
}


def _source_bound_evidence(item: Any) -> bool:
    """Support counts only when the item names a factual or legal source.

    A fixed-form answer, a bare testimony row, and a finished interview do not.
    """

    if not isinstance(item, Mapping):
        return False
    if item.get("source_bound") is False:
        return False
    for key in ("source_references", "source_refs"):
        refs = item.get(key)
        if isinstance(refs, list) and any(str(ref or "").strip() for ref in refs):
            return True
    for key in ("source_id", "citation_id", "authority_id", "legal_source_id"):
        if str(item.get(key) or "").strip():
            return True
    provenance = item.get("provenance") if isinstance(item.get("provenance"), Mapping) else {}
    for key in ("source_id", "citation_id", "authority_id", "source_reference"):
        if str(provenance.get(key) or "").strip():
            return True
    source = str(item.get("source") or "").strip()
    if source.lower() in _NON_SOURCE_LABELS:
        return False
    return bool(source)


def _pending_interview_question(state: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    shared = state.get("shared_interview") if isinstance(state.get("shared_interview"), Mapping) else {}
    pending = shared.get("pending_inquiry") if isinstance(shared.get("pending_inquiry"), Mapping) else None
    return dict(pending) if pending else None


def _user_is_waiting(state: Mapping[str, Any], active_question: Optional[Mapping[str, Any]] = None) -> bool:
    wait = state.get("intentional_user_wait") if isinstance(state.get("intentional_user_wait"), Mapping) else {}
    if bool(wait.get("paused")) and bool(wait.get("intentional", True)):
        return True
    if _pending_interview_question(state):
        return True
    return active_question is not None


def _open_question_for_stop(item: Mapping[str, Any]) -> Dict[str, Any]:
    target = str(item.get("target_id") or item.get("inquiry_id") or item.get("id") or "pending-user-question")
    revision = str(item.get("target_revision") or item.get("revision") or "1")
    return {
        "target_id": target,
        "question": str(item.get("question") or item.get("prompt") or ""),
        "unresolved_target": {
            "target_id": target,
            "target_revision": revision,
            "user_answerability": "user_observable",
            "target_kind": "user_question",
        },
    }


def _gap_dependencies(state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    shared = state.get("shared_interview") if isinstance(state.get("shared_interview"), Mapping) else {}
    dependencies: List[Dict[str, Any]] = []
    for gap in shared.get("preserved_gaps") or []:
        if not isinstance(gap, Mapping):
            continue
        dependencies.append({
            "lane": "review",
            "target_id": str(gap.get("target_id") or gap.get("inquiry_id") or "preserved-gap"),
            "target_kind": "review",
            "reason": str(gap.get("disposition") or "preserved_gap"),
        })
    for reason in list(shared.get("unknown_reasons") or []) + list(shared.get("unavailable_reasons") or []):
        text = str(reason or "").strip()
        if not text:
            continue
        lane = "source_research" if "unavailable" in text or "source" in text else "review"
        dependencies.append({
            "lane": lane,
            "target_id": text,
            "target_kind": lane,
            "reason": text,
        })
    if not dependencies:
        dependencies.append({
            "lane": "source_research",
            "target_id": "unresolved-legal-source",
            "target_kind": "legal_source",
            "reason": "source_bound_support_missing",
        })
    return dependencies


def _evaluate_finite_stop(state: Dict[str, Any], *, control: Optional[str] = None, active_question: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Ask the interview denoiser for one finite stop. Waiting is not a worker stall."""

    from complaint_phases.denoiser import ComplaintDenoiser

    shared = state.get("shared_interview") if isinstance(state.get("shared_interview"), Mapping) else {}
    pending = _pending_interview_question(state)
    waiting = _user_is_waiting(state, active_question)
    if control == "pause":
        waiting = True
    kwargs: Dict[str, Any] = {
        "worker_stalled": False if waiting or control in {"pause", "cancel", "cap", "unavailable", "saturate"} else bool(state.get("worker_stalled")),
        "paused": control == "pause",
        "cancelled": control == "cancel",
    }
    if control == "cap":
        kwargs["iteration_count"] = 1
        kwargs["iteration_cap"] = 1
        kwargs["budget_exhausted"] = False
    elif control == "unavailable":
        kwargs["provider_status"] = "unavailable"
    elif control == "saturate":
        kwargs["open_questions"] = []
        kwargs["open_dependencies"] = _gap_dependencies(state)
    elif control == "pause":
        question = pending or active_question or {"id": "user-pause", "prompt": "paused"}
        kwargs["open_questions"] = [_open_question_for_stop(question)]
    elif control == "cancel":
        question = pending or active_question
        kwargs["open_questions"] = [_open_question_for_stop(question)] if question else []
    elif pending or active_question is not None:
        kwargs["open_questions"] = [_open_question_for_stop(pending or active_question or {})]
    elif shared.get("capped_reasons") and not pending:
        kwargs["iteration_count"] = 1
        kwargs["iteration_cap"] = 1
    elif shared.get("unavailable_reasons"):
        kwargs["provider_status"] = "unavailable"
    elif shared.get("schema_version") and not pending:
        kwargs["open_questions"] = []
        kwargs["open_dependencies"] = _gap_dependencies(state)
    else:
        kwargs["needs_review"] = True
        kwargs["open_questions"] = []
        kwargs["open_dependencies"] = [{
            "lane": "review",
            "target_id": "fixed-form-assertions",
            "target_kind": "review",
            "reason": "fixed_form_answers_are_not_source_bound_support",
        }]
    stop = ComplaintDenoiser().evaluate_interview_stop(**kwargs)
    if control:
        stop = dict(stop)
        stop["control"] = control
    return stop


def _finite_reason_rows(stop: Mapping[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    seen = set()

    def add(code: str, detail: str) -> None:
        token = str(code or "").strip() or "unresolved"
        if token in seen:
            return
        seen.add(token)
        rows.append({"code": token, "detail": str(detail or token)})

    summary = stop.get("unresolved_issue_summary") if isinstance(stop.get("unresolved_issue_summary"), Mapping) else {}
    for item in list(summary.get("items") or []) + list(stop.get("remaining_issues") or []):
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("reason") or item.get("code") or item.get("dependency_lane") or item.get("disposition") or "unresolved")
        detail = str(item.get("message") or item.get("detail") or item.get("target_id") or code)
        add(code, detail)
    for shortcut in summary.get("rejected_shortcuts") or []:
        add(str(shortcut), f"Rejected shortcut: {shortcut}")
    state_name = str(stop.get("state") or "")
    outcome = str(stop.get("outcome") or "")
    if state_name == "cancelled" or outcome == "cancelled":
        add("cancellation", "The interview was cancelled. Unresolved issues stay open.")
    if state_name == "provider_unavailable" or outcome == "blocked_provider":
        add("capability_unavailable", "A required interview capability is unavailable.")
    if state_name == "limit_reached" or "iteration_cap" in seen or "question_count_limit" in seen or "budget_exhausted" in seen:
        add("cap", "A question, iteration, or budget cap stopped the interview.")
    if outcome == "paused" or state_name == "paused":
        add("user_pause", "The user paused the interview. This wait is not a development worker stall.")
    if outcome in {"awaiting_user", "needs_answer"} or state_name == "needs_answer":
        add("awaiting_user", "The interview is waiting for the user. That wait is not a development worker stall.")
    add("interview_completion_is_not_legal_sufficiency", "Finishing the interview does not establish legal sufficiency.")
    return rows


def finite_interview_outcome(
    state: Dict[str, Any],
    *,
    active_question: Optional[Mapping[str, Any]] = None,
    stop: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Public finite-stop view. Support and sufficiency stay false until evidence says otherwise."""

    from complaint_phases.denoiser import project_stopping_policy

    wait = state.get("intentional_user_wait") if isinstance(state.get("intentional_user_wait"), Mapping) else {}
    paused = bool(wait.get("paused")) and bool(wait.get("intentional", True))
    waiting = _user_is_waiting(state, active_question) or paused
    if stop is None:
        stored = state.get("interview_stop") if isinstance(state.get("interview_stop"), dict) else None
        shared = state.get("shared_interview") if isinstance(state.get("shared_interview"), Mapping) else {}
        if stored is None and isinstance(shared.get("interview_stop"), dict):
            stored = shared.get("interview_stop")
        control = str((stored or {}).get("control") or "")
        if isinstance(stored, dict) and stored.get("state") and control in {"pause", "cancel", "cap", "unavailable", "saturate"}:
            stop = stored
        else:
            stop = _evaluate_finite_stop(state, active_question=active_question)
    if waiting and str(stop.get("control") or "") not in {"cancel", "cap", "unavailable", "saturate"}:
        stop = dict(stop)
        stop["worker_stalled"] = False
    policy = project_stopping_policy(dict(stop), paused=paused or str(stop.get("control") or "") == "pause")
    if waiting and policy.get("outcome") == "no_progress" and str(stop.get("control") or "") not in {"cap", "cancel", "unavailable"}:
        policy = project_stopping_policy({**dict(stop), "state": "needs_answer", "worker_stalled": False}, paused=paused)
    outcome = str(policy.get("outcome") or stop.get("state") or "awaiting_user")
    label = _FINITE_STOP_LABELS.get(outcome, _FINITE_STOP_LABELS.get(str(stop.get("state") or ""), "unresolved"))
    if str(stop.get("control") or "") == "saturate":
        label = "saturated"
    elif str(stop.get("control") or "") == "cap":
        label = "capped"
    elif str(stop.get("control") or "") == "unavailable":
        label = "unavailable"
    elif str(stop.get("control") or "") == "cancel":
        label = "cancelled"
    elif str(stop.get("control") or "") == "pause":
        label = "paused"
    reasons = _finite_reason_rows({**dict(stop), "outcome": outcome})
    interview_complete = bool(stop.get("intake_complete")) or (
        isinstance(state.get("shared_interview"), Mapping) and _pending_interview_question(state) is None and bool(state.get("shared_interview"))
    )
    return {
        "schema": "finite-interview-outcome-v1",
        "stop": label,
        "outcome": outcome,
        "state": stop.get("state"),
        "unresolved_reasons": reasons,
        "reasons_visible": True,
        "user_waiting": bool(waiting or label in {"awaiting_user", "paused"}),
        "worker_stalled": False if waiting or label in {"awaiting_user", "paused", "saturated", "capped", "cancelled", "unavailable"} else bool(stop.get("worker_stalled")),
        "user_waiting_is_worker_stall": False,
        "legal_sufficiency": False,
        "interview_complete": bool(interview_complete) and label == "saturated",
        "interview_completion_means_legal_sufficiency": False,
        "filing_ready": False,
        "core_facts_complete": False,
        "proof_requirements_satisfied": False,
        "support_requires_source_bound_evidence": True,
    }


def _workspace_stopping_policy(
    state: Dict[str, Any],
    *,
    active_question: Optional[Dict[str, Any]],
    answers: Dict[str, Any],
) -> Dict[str, Any]:
    """Workspace view of the same stopping outcomes the interview denoiser returns."""
    from complaint_phases.denoiser import project_stopping_policy

    view = finite_interview_outcome(state, active_question=active_question)
    stored = state.get("interview_stop") if isinstance(state.get("interview_stop"), dict) else None
    if isinstance(stored, dict) and stored.get("state"):
        waiting = _user_is_waiting(state, active_question)
        payload = dict(stored)
        if waiting:
            payload["worker_stalled"] = False
        wait = state.get("intentional_user_wait") if isinstance(state.get("intentional_user_wait"), dict) else {}
        paused = bool(wait.get("paused")) and bool(wait.get("intentional", True))
        policy = project_stopping_policy(payload, paused=paused or view.get("stop") == "paused")
        if waiting and policy.get("outcome") == "no_progress" and view.get("stop") not in {"capped", "cancelled", "unavailable"}:
            policy = project_stopping_policy({**payload, "state": "needs_answer", "worker_stalled": False}, paused=paused)
        return policy

    values = [str(value or "").strip().lower() for value in (answers or {}).values() if str(value or "").strip()]
    unknown_only = bool(values) and all(value in _UNKNOWN_INTAKE_ANSWERS for value in values)
    if view.get("stop") == "paused":
        state_name = "paused"
    elif active_question is not None or view.get("user_waiting"):
        state_name = "needs_answer"
    elif unknown_only:
        state_name = "deferred_unknown"
    elif view.get("stop") == "saturated":
        state_name = "saturated"
    elif view.get("stop") == "capped":
        state_name = "limit_reached"
    elif view.get("stop") == "cancelled":
        state_name = "cancelled"
    elif view.get("stop") == "unavailable":
        state_name = "provider_unavailable"
    else:
        state_name = "needs_review"
    stop = {
        "state": state_name,
        "worker_stalled": False,
        "intake_complete": False,
        "filing_ready": False,
        "legal_sufficiency": False,
        "core_facts_complete": False,
        "unresolved_issue_summary": {
            "items": [{"reason": item["code"], "detail": item["detail"]} for item in view.get("unresolved_reasons") or []],
            "open_answerable_count": 1 if active_question is not None else 0,
            "legal_sufficiency": False,
            "core_facts_complete": False,
            "proof_requirements_satisfied": False,
            "rejected_shortcuts": ["empty_question_list", "fixed_form_completion"] if active_question is None else [],
        },
    }
    if unknown_only:
        stop["unresolved_issue_summary"]["items"].append({"reason": "unknown_only_session"})
    return project_stopping_policy(stop, paused=state_name == "paused")


def publish_workspace_dependency_action(state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Publish the stored interview's next source, evidence, or review action.

    The workspace reuses the denoiser projection. It does not start another
    stop engine, wait on stdin, or treat a hook receipt as sufficiency.
    """
    from complaint_phases.denoiser import dependency_lane_for, project_stopping_policy, publish_authorized_dependency_action

    session = state if isinstance(state, dict) else {}
    wait = session.get("intentional_user_wait") if isinstance(session.get("intentional_user_wait"), dict) else {}
    paused = bool(wait.get("paused")) and bool(wait.get("intentional", True))
    stored = session.get("interview_stop") if isinstance(session.get("interview_stop"), dict) else None
    dependencies = [item for item in (session.get("open_dependencies") or []) if isinstance(item, dict)]
    if stored is None and dependencies:
        lane = dependency_lane_for(dependencies[0])
        stored = {
            "state": "saturated" if lane == "source_research" else (
                "needs_review" if lane == "review" else "deferred_needs_evidence"
            ),
            "dependency_lane": lane,
            "intake_complete": False,
            "legal_sufficiency": False,
            "worker_stalled": bool(session.get("worker_stalled")),
            "unresolved_issue_summary": {
                "items": dependencies,
                "open_answerable_count": 0,
                "legal_sufficiency": False,
                "core_facts_complete": False,
                "proof_requirements_satisfied": False,
                "rejected_shortcuts": ["completed_hook"] if session.get("hook_completed") else [],
            },
        }
    policy = project_stopping_policy(stored or {"state": "needs_answer"}, paused=paused)
    pending_question = _pending_interview_question(session)
    user_waiting = paused or pending_question is not None
    if user_waiting:
        policy = project_stopping_policy(
            {**(stored or {"state": "needs_answer"}), "worker_stalled": False},
            paused=paused,
        )
    elif session.get("worker_stalled") and policy.get("outcome") in {"awaiting_user", "paused"}:
        policy = project_stopping_policy({**(stored or {}), "state": "no_progress", "worker_stalled": True}, paused=False)
    context = session.get("dependency_action_context") if isinstance(session.get("dependency_action_context"), dict) else {}
    if dependencies and not context.get("target_id"):
        context = {
            **context,
            "target_id": dependencies[0].get("target_id"),
            "target_revision": dependencies[0].get("target_revision"),
        }
    try:
        attempt = int(context.get("attempt") or 0)
    except (TypeError, ValueError):
        attempt = 0
    return publish_authorized_dependency_action(
        policy,
        attempt=attempt,
        context=context,
        hook_completed=bool(session.get("hook_completed")),
    )


_CLAIM_TYPE_LABELS: Dict[str, str] = {
    "retaliation": "Retaliation",
    "employment_discrimination": "Employment Discrimination",
    "housing_discrimination": "Housing Discrimination",
    "due_process_failure": "Due Process Violation",
    "consumer_protection": "Consumer Protection",
}
_PACKAGE_EXPORT_CONTRACT: List[str] = [
    "create_identity",
    "start_session",
    "submit_intake_answers",
    "run_intake_chat_turn",
    "save_evidence",
    "import_gmail_evidence",
    "run_gmail_duckdb_pipeline",
    "import_local_evidence",
    "search_email_duckdb_corpus",
    "review_case",
    "build_mediator_prompt",
    "get_complaint_readiness",
    "get_ui_readiness",
    "get_client_release_gate",
    "get_workflow_capabilities",
    "get_tooling_contract",
    "get_workspace_data_schema",
    "migrate_legacy_workspace_data",
    "search_workspace_dataset",
    "view_workspace_dataset",
    "build_mike_handoff",
    "get_mike_integration_status",
    "sync_mike_final_draft",
    "get_draft_proof_report",
    "render_draft_proof_report",
    "pin_draft_proof_report",
    "score_draft_quality",
    "improve_draft",
    "get_proof_history",
    "generate_complaint",
    "export_complaint_packet",
    "export_complaint_markdown",
    "export_complaint_docx",
    "export_complaint_pdf",
    "analyze_complaint_output",
    "get_formal_diagnostics",
    "get_filing_provenance",
    "get_provider_diagnostics",
    "view_docket_dataset",
    "search_docket_dataset",
    "get_docket_dataset_metadata",
    "get_docket_dataset_graph",
    "review_generated_exports",
    "update_claim_type",
    "update_case_synopsis",
    "review_ui",
    "optimize_ui",
    "run_browser_audit",
]
_CLI_COMMAND_CONTRACT: List[str] = [
    "identity",
    "session",
    "answer",
    "chat-turn",
    "add-evidence",
    "import-gmail-evidence",
    "run-gmail-duckdb-pipeline",
    "import-local-evidence",
    "search-email-duckdb",
    "review",
    "mediator-prompt",
    "complaint-readiness",
    "ui-readiness",
    "client-release-gate",
    "capabilities",
    "tooling-contract",
    "workspace-data-schema",
    "migrate-legacy-workspace-data",
    "search-workspace-data",
    "view-workspace-data",
    "build-mike-handoff",
    "mike-status",
    "sync-mike-draft",
    "draft-proof-report",
    "get-draft-proof-report",
    "render-draft-proof-report",
    "pin-draft-proof-report",
    "score-draft-quality",
    "improve-draft",
    "proof-history",
    "generate",
    "export-packet",
    "export-markdown",
    "export-docx",
    "export-pdf",
    "analyze-output",
    "formal-diagnostics",
    "filing-provenance",
    "provider-diagnostics",
    "docket-view",
    "docket-search",
    "docket-metadata",
    "docket-graph",
    "review-exports",
    "set-claim-type",
    "update-synopsis",
    "review-ui",
    "optimize-ui",
    "browser-audit",
]
_BROWSER_SDK_METHOD_CONTRACT: List[str] = [
    "createIdentity",
    "bootstrapWorkspace",
    "getSession",
    "submitIntake",
    "runIntakeChatTurn",
    "saveEvidence",
    "importGmailEvidence",
    "importLocalEvidence",
    "runGmailDuckdbPipeline",
    "searchEmailDuckdb",
    "reviewCase",
    "buildMediatorPrompt",
    "getComplaintReadiness",
    "getUiReadiness",
    "getClientReleaseGate",
    "getWorkflowCapabilities",
    "getToolingContract",
    "getWorkspaceDataSchema",
    "migrateLegacyWorkspaceData",
    "searchWorkspaceDataset",
    "viewWorkspaceDataset",
    "buildMikeHandoff",
    "getMikeIntegrationStatus",
    "syncMikeFinalDraft",
    "getDraftProofReport",
    "renderDraftProofReport",
    "pinDraftProofReport",
    "scoreDraftQuality",
    "improveDraft",
    "getProofHistory",
    "generateComplaint",
    "exportComplaintPacket",
    "exportComplaintMarkdown",
    "exportComplaintDocx",
    "exportComplaintPdf",
    "analyzeComplaintOutput",
    "getFormalDiagnostics",
    "getFilingProvenance",
    "getProviderDiagnostics",
    "reviewGeneratedExports",
    "updateClaimType",
    "updateCaseSynopsis",
    "reviewUiArtifacts",
    "optimizeUiArtifacts",
    "runBrowserAudit",
]

_DOCKET_ISSUE_ENTITY_KEYWORDS = (
    "issue",
    "legal_issue",
    "claim",
    "cause_of_action",
    "violation",
    "defense",
    "right",
    "duty",
)
_CORE_FLOW_CONTRACT: Dict[str, Dict[str, str]] = {
    "intake": {
        "package_export": "submit_intake_answers",
        "cli_command": "answer",
        "mcp_tool": "complaint.submit_intake",
        "browser_sdk_method": "submitIntake",
    },
    "intake_chat": {
        "package_export": "run_intake_chat_turn",
        "cli_command": "chat-turn",
        "mcp_tool": "complaint.run_intake_chat_turn",
        "browser_sdk_method": "runIntakeChatTurn",
    },
    "evidence_capture": {
        "package_export": "save_evidence",
        "cli_command": "add-evidence",
        "mcp_tool": "complaint.save_evidence",
        "browser_sdk_method": "saveEvidence",
    },
    "gmail_evidence_import": {
        "package_export": "import_gmail_evidence",
        "cli_command": "import-gmail-evidence",
        "mcp_tool": "complaint.import_gmail_evidence",
        "browser_sdk_method": "importGmailEvidence",
    },
    "gmail_duckdb_pipeline": {
        "package_export": "run_gmail_duckdb_pipeline",
        "cli_command": "run-gmail-duckdb-pipeline",
        "mcp_tool": "complaint.run_gmail_duckdb_pipeline",
        "browser_sdk_method": "runGmailDuckdbPipeline",
    },
    "local_evidence_import": {
        "package_export": "import_local_evidence",
        "cli_command": "import-local-evidence",
        "mcp_tool": "complaint.import_local_evidence",
        "browser_sdk_method": "importLocalEvidence",
    },
    "email_duckdb_search": {
        "package_export": "search_email_duckdb_corpus",
        "cli_command": "search-email-duckdb",
        "mcp_tool": "complaint.search_email_duckdb_corpus",
        "browser_sdk_method": "searchEmailDuckdb",
    },
    "support_review": {
        "package_export": "review_case",
        "cli_command": "review",
        "mcp_tool": "complaint.review_case",
        "browser_sdk_method": "reviewCase",
    },
    "mediator_handoff": {
        "package_export": "build_mediator_prompt",
        "cli_command": "mediator-prompt",
        "mcp_tool": "complaint.build_mediator_prompt",
        "browser_sdk_method": "buildMediatorPrompt",
    },
    "claim_type_alignment": {
        "package_export": "update_claim_type",
        "cli_command": "set-claim-type",
        "mcp_tool": "complaint.update_claim_type",
        "browser_sdk_method": "updateClaimType",
    },
    "case_synopsis_sync": {
        "package_export": "update_case_synopsis",
        "cli_command": "update-synopsis",
        "mcp_tool": "complaint.update_case_synopsis",
        "browser_sdk_method": "updateCaseSynopsis",
    },
    "draft_generation": {
        "package_export": "generate_complaint",
        "cli_command": "generate",
        "mcp_tool": "complaint.generate_complaint",
        "browser_sdk_method": "generateComplaint",
    },
    "complaint_export_markdown": {
        "package_export": "export_complaint_markdown",
        "cli_command": "export-markdown",
        "mcp_tool": "complaint.export_complaint_markdown",
        "browser_sdk_method": "exportComplaintMarkdown",
    },
    "complaint_export_pdf": {
        "package_export": "export_complaint_pdf",
        "cli_command": "export-pdf",
        "mcp_tool": "complaint.export_complaint_pdf",
        "browser_sdk_method": "exportComplaintPdf",
    },
    "complaint_export_docx": {
        "package_export": "export_complaint_docx",
        "cli_command": "export-docx",
        "mcp_tool": "complaint.export_complaint_docx",
        "browser_sdk_method": "exportComplaintDocx",
    },
    "complaint_output_analysis": {
        "package_export": "analyze_complaint_output",
        "cli_command": "analyze-output",
        "mcp_tool": "complaint.analyze_complaint_output",
        "browser_sdk_method": "analyzeComplaintOutput",
    },
    "formal_diagnostics": {
        "package_export": "get_formal_diagnostics",
        "cli_command": "formal-diagnostics",
        "mcp_tool": "complaint.get_formal_diagnostics",
        "browser_sdk_method": "getFormalDiagnostics",
    },
    "filing_provenance": {
        "package_export": "get_filing_provenance",
        "cli_command": "filing-provenance",
        "mcp_tool": "complaint.get_filing_provenance",
        "browser_sdk_method": "getFilingProvenance",
    },
    "provider_diagnostics": {
        "package_export": "get_provider_diagnostics",
        "cli_command": "provider-diagnostics",
        "mcp_tool": "complaint.get_provider_diagnostics",
        "browser_sdk_method": "getProviderDiagnostics",
    },
    "tooling_contract": {
        "package_export": "get_tooling_contract",
        "cli_command": "tooling-contract",
        "mcp_tool": "complaint.get_tooling_contract",
        "browser_sdk_method": "getToolingContract",
    },
    "workspace_data_schema": {
        "package_export": "get_workspace_data_schema",
        "cli_command": "workspace-data-schema",
        "mcp_tool": "complaint.get_workspace_data_schema",
        "browser_sdk_method": "getWorkspaceDataSchema",
    },
    "workspace_data_migration": {
        "package_export": "migrate_legacy_workspace_data",
        "cli_command": "migrate-legacy-workspace-data",
        "mcp_tool": "complaint.migrate_legacy_workspace_data",
        "browser_sdk_method": "migrateLegacyWorkspaceData",
    },
    "workspace_data_search": {
        "package_export": "search_workspace_dataset",
        "cli_command": "search-workspace-data",
        "mcp_tool": "complaint.search_workspace_dataset",
        "browser_sdk_method": "searchWorkspaceDataset",
    },
    "workspace_data_view": {
        "package_export": "view_workspace_dataset",
        "cli_command": "view-workspace-data",
        "mcp_tool": "complaint.view_workspace_dataset",
        "browser_sdk_method": "viewWorkspaceDataset",
    },
    "mike_editor_handoff": {
        "package_export": "build_mike_handoff",
        "cli_command": "build-mike-handoff",
        "mcp_tool": "complaint.build_mike_handoff",
        "browser_sdk_method": "buildMikeHandoff",
    },
    "mike_editor_status": {
        "package_export": "get_mike_integration_status",
        "cli_command": "mike-status",
        "mcp_tool": "complaint.get_mike_integration_status",
        "browser_sdk_method": "getMikeIntegrationStatus",
    },
    "mike_editor_sync": {
        "package_export": "sync_mike_final_draft",
        "cli_command": "sync-mike-draft",
        "mcp_tool": "complaint.sync_mike_final_draft",
        "browser_sdk_method": "syncMikeFinalDraft",
    },
    "draft_proof_report": {
        "package_export": "get_draft_proof_report",
        "cli_command": "draft-proof-report",
        "mcp_tool": "complaint.get_draft_proof_report",
        "browser_sdk_method": "getDraftProofReport",
    },
    "render_draft_proof_report": {
        "package_export": "render_draft_proof_report",
        "cli_command": "render-draft-proof-report",
        "mcp_tool": "complaint.render_draft_proof_report",
        "browser_sdk_method": "renderDraftProofReport",
    },
    "pin_draft_proof_report": {
        "package_export": "pin_draft_proof_report",
        "cli_command": "pin-draft-proof-report",
        "mcp_tool": "complaint.pin_draft_proof_report",
        "browser_sdk_method": "pinDraftProofReport",
    },
    "score_draft_quality": {
        "package_export": "score_draft_quality",
        "cli_command": "score-draft-quality",
        "mcp_tool": "complaint.score_draft_quality",
        "browser_sdk_method": "scoreDraftQuality",
    },
    "improve_draft": {
        "package_export": "improve_draft",
        "cli_command": "improve-draft",
        "mcp_tool": "complaint.improve_draft",
        "browser_sdk_method": "improveDraft",
    },
    "get_proof_history": {
        "package_export": "get_proof_history",
        "cli_command": "proof-history",
        "mcp_tool": "complaint.get_proof_history",
        "browser_sdk_method": "getProofHistory",
    },
    "export_critic": {
        "package_export": "review_generated_exports",
        "cli_command": "review-exports",
        "mcp_tool": "complaint.review_generated_exports",
        "browser_sdk_method": "reviewGeneratedExports",
    },
    "ui_actor_critic": {
        "package_export": "review_ui",
        "cli_command": "review-ui",
        "mcp_tool": "complaint.review_ui",
        "browser_sdk_method": "reviewUiArtifacts",
    },
    "ui_closed_loop_optimizer": {
        "package_export": "optimize_ui",
        "cli_command": "optimize-ui",
        "mcp_tool": "complaint.optimize_ui",
        "browser_sdk_method": "optimizeUiArtifacts",
    },
}


def format_legal_research_result(receipt: Dict[str, Any]) -> str:
    """Public counts and the next resumable step. Research is not proof."""

    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    retrieved = int(counts.get("retrieved") or 0)
    admitted = int(counts.get("admitted") or 0)
    rejected = int(counts.get("rejected") or 0)
    unavailable = int(counts.get("unavailable") or 0)
    next_action = str(receipt.get("next_action") or "continue_pending_inquiry")
    return (
        f"Legal research retrieved={retrieved} admitted={admitted} "
        f"rejected={rejected} unavailable={unavailable}. "
        f"Next action: {next_action}. The pending question is unchanged."
    )


def _public_why_inquiry(inquiry: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Show host bindings. Missing objective or target stays the word unknown."""
    if not isinstance(inquiry, dict):
        return None
    if not (str(inquiry.get("question") or "").strip() or str(inquiry.get("why_it_matters") or "").strip()):
        return None
    chosen = dict(inquiry)
    if not str(chosen.get("objective_id") or "").strip():
        chosen["objective_id"] = "unknown"
        chosen["grounding_status"] = "unknown"
    if not str(chosen.get("target_id") or "").strip():
        chosen["target_id"] = "unknown"
        chosen["grounding_status"] = "unknown"
    return chosen


def format_terminal_why(
    inquiry: Optional[Dict[str, Any]] = None,
    *,
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Explain the current gap question for a terminal /why command."""
    from complaint_phases.denoiser import format_terminal_why as render_terminal_why

    chosen = inquiry if isinstance(inquiry, dict) else None
    if chosen is None and isinstance(state, dict):
        projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
        pending = projection.get("pending_inquiry") if isinstance(projection.get("pending_inquiry"), dict) else None
        stored = state.get("explained_inquiry") if isinstance(state.get("explained_inquiry"), dict) else None
        phase_inquiry = None
        phase_data = state.get("phase_data") if isinstance(state.get("phase_data"), dict) else {}
        intake = phase_data.get("intake") if isinstance(phase_data.get("intake"), dict) else {}
        if isinstance(intake.get("current_explained_inquiry"), dict):
            phase_inquiry = intake.get("current_explained_inquiry")
        # The shared pending inquiry is the question the service is actually asking.
        chosen = pending or stored or phase_inquiry
    return render_terminal_why(_public_why_inquiry(chosen))


def publish_explained_inquiry(state: Dict[str, Any], selection: Dict[str, Any]) -> Dict[str, Any]:
    """Copy a phase-manager selection onto the workspace session without storing an answer."""
    current = selection.get("current") if isinstance(selection, dict) else None
    inquiries = selection.get("inquiries") if isinstance(selection, dict) else None
    state["explained_inquiry"] = current if isinstance(current, dict) else None
    state["explained_inquiries"] = list(inquiries or [])
    return state


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify_user_id(user_id: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(user_id or DEFAULT_USER_ID).strip())
    return normalized.strip("-") or DEFAULT_USER_ID


class WorkspaceAuthorizationDenied(PermissionError):
    """Private workspace operation refused for this principal or case.

    The message is a stable code. It must not echo session contents, markers,
    paths, or caller-supplied identifiers.
    """

    code = "authorization_denied"

    def __init__(self) -> None:
        super().__init__("authorization_denied")


class WorkspacePersistenceError(RuntimeError):
    """Existing session bytes could not be read or must not be replaced."""

    def __init__(self, message: str, *, code: str, public_status: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_status = public_status


class AuthorizationRequirement:
    """Resource/ability admission record.

    Mirrors the transport-neutral shape of
    ``ipfs_kit_py`` ``AuthorizationRequirement.protected(resource, ability)``
    without importing storage services. It does not authenticate a token or
    infer case ownership.
    """

    def __init__(self, resource: str, ability: str, *, protected: bool = True) -> None:
        self.resource = str(resource or "")
        self.ability = str(ability or "")
        self.protected = bool(protected)

    @classmethod
    def protected(cls, resource: str, ability: str) -> "AuthorizationRequirement":
        return cls(resource, ability, protected=True)

    @classmethod
    def public(cls, resource: str, ability: str) -> "AuthorizationRequirement":
        return cls(resource, ability, protected=False)


@dataclass(frozen=True)
class WorkspaceDispatchContext:
    """Transport-neutral principal context shared by service, facade, HTTP, and MCP.

    Compatible with ``ipfs_kit_py.core.service_router.DispatchContext``:
    ``principal`` is a non-empty string or None, and ``attributes`` is a mapping.
    """

    principal: Optional[str] = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.principal is not None and (not isinstance(self.principal, str) or not self.principal):
            raise ValueError("principal must be a non-empty string or None")
        if not isinstance(self.attributes, Mapping):
            raise ValueError("dispatch context attributes must be a mapping")
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))


@dataclass(frozen=True)
class WorkspaceAccess:
    """Authenticated principal binding. A supplied user id is not authorization."""

    trust: str
    principal_id: Optional[str] = None
    case_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.trust not in {"trusted_local", "authenticated", "unauthenticated"}:
            raise ValueError("unsupported workspace trust")
        if self.trust == "authenticated" and not self.principal_id:
            raise ValueError("authenticated workspace access requires a principal")

    @staticmethod
    def trusted_local(principal_id: Optional[str] = None, case_id: Optional[str] = None) -> "WorkspaceAccess":
        """Explicit local operator ownership. ``principal_id`` None selects the requested local id."""

        return WorkspaceAccess("trusted_local", principal_id or None, case_id or None)

    @staticmethod
    def authenticated(principal_id: str, case_id: Optional[str] = None) -> "WorkspaceAccess":
        return WorkspaceAccess("authenticated", str(principal_id), case_id or None)

    @staticmethod
    def unauthenticated() -> "WorkspaceAccess":
        return WorkspaceAccess("unauthenticated", None, None)

    def dispatch_context(self, *, user_id: Optional[str], case_id: Optional[str], ability: str) -> WorkspaceDispatchContext:
        principal = self.principal_id if self.trust == "authenticated" else None
        if self.trust == "trusted_local" and self.principal_id:
            principal = self.principal_id
        return WorkspaceDispatchContext(
            principal=principal,
            attributes={
                "trust": self.trust,
                "user_id": user_id,
                "bound_principal": self.principal_id,
                "case_id": case_id,
                "bound_case_id": self.case_id,
                "ability": ability,
                "resource": "workspace.case",
            },
        )


class WorkspaceAuthorizer:
    """Admit a protected workspace operation for the bound principal and case.

    A client-supplied user id is an identifier. Trusted-local admission must be
    an explicit ``trusted_local`` trust value. This object does not accept a
    process-wide bearer token as case ownership.
    """

    def __call__(self, requirement: AuthorizationRequirement, context: WorkspaceDispatchContext) -> bool:
        if not isinstance(requirement, AuthorizationRequirement):
            return False
        if not requirement.protected:
            return True
        attributes = context.attributes
        trust = str(attributes.get("trust") or "")
        requested_user = attributes.get("user_id")
        requested_case = attributes.get("case_id")
        bound_case = attributes.get("bound_case_id")
        if requested_case is not None and bound_case is not None and str(requested_case) != str(bound_case):
            return False
        record_case = attributes.get("record_case_id")
        if record_case is not None and bound_case is not None and str(record_case) != str(bound_case):
            return False
        if record_case is not None and requested_case is not None and str(record_case) != str(requested_case):
            return False
        if trust == "trusted_local":
            bound = attributes.get("bound_principal")
            if bound and requested_user is not None and str(requested_user) != str(bound):
                return False
            return True
        if trust != "authenticated" or not context.principal:
            return False
        if requested_user is None or str(requested_user) != context.principal:
            return False
        return True


class PrincipalRegistry:
    """Injectable bearer-token to principal map. Tokens are not interchangeable."""

    def __init__(self) -> None:
        self._tokens: Dict[str, WorkspaceAccess] = {}

    def register(self, token: str, principal_id: str, *, case_id: Optional[str] = None) -> None:
        normalized = str(token or "").strip()
        if not normalized:
            raise ValueError("principal token is required")
        self._tokens[normalized] = WorkspaceAccess.authenticated(principal_id, case_id=case_id)

    def resolve(self, token: Optional[str]) -> Optional[WorkspaceAccess]:
        normalized = str(token or "").strip()
        if not normalized:
            return None
        return self._tokens.get(normalized)


_REQUEST_ACCESS: contextvars.ContextVar[Optional[WorkspaceAccess]] = contextvars.ContextVar(
    "complaint_workspace_access",
    default=None,
)
_REQUEST_CASE: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "complaint_workspace_case",
    default=None,
)
_REQUEST_CID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "complaint_workspace_cid",
    default=None,
)
_REQUEST_STORAGE_KEY: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "complaint_workspace_storage_key",
    default=None,
)

_PUBLIC_MCP_TOOLS = frozenset(
    {
        "complaint.create_identity",
        "complaint.list_intake_questions",
        "complaint.list_claim_elements",
        "complaint.search_corpus",
    }
)
_LEGACY_MAP_NAME = "legacy-namespace-map.json"
_MCP_HOST_PATH_ARGUMENTS = frozenset({
    "input_path", "manifest_path", "statefile_path", "evidence_db_path",
    "legal_authority_db_path", "claim_support_db_path", "index_path", "paths",
    "artifact_path", "artifact_dir", "output_dir", "output_path", "evidence_root",
    "duckdb_output_dir", "screenshot_dir", "screenshot_paths", "config_path", "gmail_oauth_client_secrets",
    "gmail_oauth_token_cache",
})


def principal_namespace(principal_id: str) -> str:
    """Stable collision-resistant namespace for an exact principal identity."""

    material = str(principal_id if principal_id is not None else "").encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def namespace_filename(principal_id: str) -> str:
    return f"p-{principal_namespace(principal_id)}.json"


@contextmanager
def workspace_access_scope(access: Optional[WorkspaceAccess]) -> Iterator[None]:
    token = _REQUEST_ACCESS.set(access)
    try:
        yield
    finally:
        _REQUEST_ACCESS.reset(token)


@contextmanager
def _workspace_reference_scope(
    *,
    case_id: Optional[str] = None,
    cid: Optional[str] = None,
    storage_key: Optional[str] = None,
) -> Iterator[None]:
    case_token = _REQUEST_CASE.set(None if case_id is None or str(case_id).strip() == "" else str(case_id))
    cid_token = _REQUEST_CID.set(None if cid is None or str(cid).strip() == "" else str(cid))
    key_token = _REQUEST_STORAGE_KEY.set(
        None if storage_key is None or str(storage_key).strip() == "" else str(storage_key)
    )
    try:
        yield
    finally:
        _REQUEST_CASE.reset(case_token)
        _REQUEST_CID.reset(cid_token)
        _REQUEST_STORAGE_KEY.reset(key_token)


def _bearer_token_from_headers(headers: Mapping[str, str]) -> str:
    authorization = str(headers.get("authorization") or headers.get("Authorization") or "")
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return ""


def access_from_http_headers(
    headers: Mapping[str, str],
    *,
    principal_registry: Optional[PrincipalRegistry] = None,
    trusted_local: bool = False,
) -> WorkspaceAccess:
    """Resolve request trust. A generic bearer or supplied user id is not a principal."""

    token = _bearer_token_from_headers(headers)
    if principal_registry is not None and token:
        resolved = principal_registry.resolve(token)
        if resolved is not None:
            return resolved
    if trusted_local:
        return WorkspaceAccess.trusted_local()
    return WorkspaceAccess.unauthenticated()


def _split_lines(value: Optional[str]) -> List[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _unique_preserve_order(values: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in values:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _slugify_graph_id(value: Any) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower())
    return normalized.strip("-") or "unknown"


def _normalize_annotation_tags(tags: Any) -> List[str]:
    if isinstance(tags, str):
        raw_tags = re.split(r"[,;\n]+", tags)
    else:
        raw_tags = list(tags or [])
    return _unique_preserve_order([str(tag or "").strip() for tag in raw_tags if str(tag or "").strip()])


def _build_schema_guided_tooling_recommendations(schema_snapshot: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    snapshot = dict(schema_snapshot or {})
    if not snapshot:
        return []

    recommendations: List[Dict[str, Any]] = []
    hint_index = {
        str((item or {}).get("id") or "").strip(): str((item or {}).get("reason") or "").strip()
        for item in list(snapshot.get("ui_design_hints") or []) + list(snapshot.get("mcp_design_hints") or [])
        if isinstance(item, Mapping)
    }
    filter_dimensions = [str(item).strip() for item in list(snapshot.get("filter_dimensions") or []) if str(item).strip()]
    piece_ids = {
        str((piece or {}).get("piece_id") or "").strip()
        for piece in list(snapshot.get("piece_schemas") or [])
        if isinstance(piece, Mapping)
    }

    def add_recommendation(
        rec_id: str,
        *,
        tool_name: str,
        ui_surface: str,
        reason: str,
        priority: str = "medium",
    ) -> None:
        recommendations.append({
            "id": rec_id,
            "tool_name": tool_name,
            "ui_surface": ui_surface,
            "reason": reason,
            "priority": priority,
        })

    add_recommendation(
        "workspace_schema_refresh",
        tool_name="complaint.get_workspace_data_schema",
        ui_surface="workspace-data-operator-card",
        reason="Refresh the workspace parquet schema before designing MCP filters or navigation so the UI follows the stored dataset pieces.",
        priority="high",
    )
    add_recommendation(
        "workspace_migration_path",
        tool_name="complaint.migrate_legacy_workspace_data",
        ui_surface="workspace-data-operator-card",
        reason="Use the legacy migration flow to consolidate old complaint session and mediator stores into the packaged parquet workspace bundle.",
        priority="high",
    )
    if "schema_guided_filters" in hint_index and filter_dimensions:
        add_recommendation(
            "workspace_filter_design",
            tool_name="complaint.get_workspace_data_schema",
            ui_surface="workspace-data-schema-preview",
            reason=f"Prioritize MCP filters and browser chips for {', '.join(filter_dimensions)} because the dataset exposes those as useful selection dimensions.",
            priority="high",
        )
    if "dual_search_modes" in hint_index:
        add_recommendation(
            "dual_search_affordances",
            tool_name="complaint.search_docket_dataset",
            ui_surface="workspace-data-schema-hints-preview",
            reason=hint_index["dual_search_modes"],
            priority="medium",
        )
    if "claim_alignment_filters" in hint_index:
        add_recommendation(
            "claim_alignment_navigation",
            tool_name="complaint.review_case",
            ui_surface="review",
            reason=hint_index["claim_alignment_filters"],
            priority="medium",
        )
    if "knowledge_graph_presence" in hint_index or any(piece_id.startswith("knowledge_graph") for piece_id in piece_ids):
        add_recommendation(
            "graph_navigation",
            tool_name="complaint.get_docket_dataset_graph",
            ui_surface="packaged-docket-operator-card",
            reason=hint_index.get("knowledge_graph_presence") or "Graph entities are present in the packaged workspace and should inform related-issue exploration.",
            priority="medium",
        )
    return recommendations


def _normalize_fragment(value: Optional[str], fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"[.?!,;:]+$", "", text)
    return text or fallback


def _extract_person_name(value: Optional[str], fallback: str = "Plaintiff") -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return fallback
    text = re.sub(r"(?i)\bi am\s+", "", text)
    text = re.sub(r"(?i)\bmy address is\b.*$", "", text).strip(" ,.;:")
    text = re.sub(r"[^A-Za-z '\-]+", " ", text)
    candidates = []
    for segment in re.split(r"\s+and\s+|,|/|;", text):
        tokenized = [part.strip() for part in segment.split() if part.strip()]
        if len(tokenized) < 2:
            continue
        filtered = []
        for token in tokenized:
            lowered = token.lower()
            if lowered in {"plaintiff", "defendant", "vs", "v", "address"}:
                continue
            if token[:1].isalpha():
                filtered.append(token.strip(" .,:;"))
            if len(filtered) >= 4:
                break
        if len(filtered) >= 2:
            candidates.append(" ".join(filtered))
    if candidates:
        return candidates[0]
    compact = " ".join(text.split()[:4]).strip(" ,.;:")
    return compact or fallback


def _extract_defendant_name(value: Optional[str], fallback: str = "Defendant") -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return fallback
    if re.search(r"\bvs\b", text, flags=re.IGNORECASE):
        text = re.split(r"\bvs\b", text, flags=re.IGNORECASE, maxsplit=1)[-1].strip()
    text = re.sub(r"(?i)\b(defendant|plaintiff)s?\b", "", text).strip(" ,.;:")
    segments = [segment.strip(" ,.;:") for segment in re.split(r"\s+and\s+|;|/", text) if segment.strip()]
    normalized_segments: List[str] = []
    seen: set[str] = set()
    for segment in segments:
        cleaned = re.sub(r"[^A-Za-z0-9 '&().-]+", " ", segment)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized_segments.append(cleaned)
    if not normalized_segments:
        return fallback
    if len(normalized_segments) == 1:
        return normalized_segments[0]
    if len(normalized_segments) == 2:
        return f"{normalized_segments[0]} and {normalized_segments[1]}"
    return ", ".join(normalized_segments[:-1]) + f", and {normalized_segments[-1]}"


def _condense_timeline_text(value: Optional[str], fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return fallback
    if len(text) <= 360:
        return text
    sentence_parts = re.split(r"(?<=[.!?])\s+", text)
    date_pattern = re.compile(
        r"\b("
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
        r")\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}\b",
        flags=re.IGNORECASE,
    )
    focused = [part.strip() for part in sentence_parts if date_pattern.search(part or "")]
    if len(focused) >= 2:
        return " ".join(focused[:6]).strip()
    return " ".join(sentence_parts[:3]).strip()[:520]


def _sentence_fragment(value: Optional[str], fallback: str) -> str:
    text = _normalize_fragment(value, fallback)
    if not text:
        return fallback
    return f"{text[0].lower()}{text[1:]}" if text[:1].isalpha() else text


def _event_fragment(value: Optional[str], fallback: str) -> str:
    text = _sentence_fragment(value, fallback)
    if text.startswith("was "):
        return text[4:]
    return text


def _adverse_action_clause(value: Optional[str], fallback: str) -> str:
    text = _event_fragment(value, fallback)
    lowered = text.lower()
    replacements = {
        "terminated ": "terminating Plaintiff ",
        "fired ": "firing Plaintiff ",
        "suspended ": "suspending Plaintiff ",
        "disciplined ": "disciplining Plaintiff ",
        "demoted ": "demoting Plaintiff ",
        "evicted ": "evicting Plaintiff ",
        "denied ": "denying Plaintiff ",
        "threatened ": "threatening Plaintiff ",
    }
    for old, new in replacements.items():
        if lowered.startswith(old):
            return new + text[len(old):]
    return text


def _pleading_activity_fragment(value: Optional[str], fallback: str) -> str:
    text = _sentence_fragment(value, fallback)
    replacements = {
        "reported ": "reporting ",
        "requested ": "requesting ",
        "complained about ": "complaining about ",
        "complained to ": "complaining to ",
        "opposed ": "opposing ",
        "filed ": "filing ",
        "disclosed ": "disclosing ",
        "asked for ": "asking for ",
        "sought ": "seeking ",
    }
    lowered = text.lower()
    for old, new in replacements.items():
        if lowered.startswith(old):
            text = new + text[len(old):]
            break
    clause_replacements = {
        " and reported ": " and reporting ",
        " and requested ": " and requesting ",
        " and complained about ": " and complaining about ",
        " and complained to ": " and complaining to ",
        " and opposed ": " and opposing ",
        " and filed ": " and filing ",
        " and disclosed ": " and disclosing ",
        " and asked for ": " and asking for ",
        " and sought ": " and seeking ",
    }
    for old, new in clause_replacements.items():
        text = re.sub(re.escape(old), new, text, flags=re.IGNORECASE)
    return text


def _pleading_sentence(value: Optional[str], fallback: str) -> str:
    text = _normalize_fragment(value, fallback)
    if not text:
        return fallback
    text = re.sub(r"\s+", " ", text).strip()
    text = text[0].upper() + text[1:] if text[:1].isalpha() else text
    return f"{text}."


def _timeline_clause_fragment(value: str) -> str:
    text = _normalize_fragment(value, "the relevant event occurred")
    lowered = text.lower()
    replacements = {
        "report on ": "Plaintiff made the report on ",
        "complaint on ": "Plaintiff made the complaint on ",
        "accommodation request on ": "Plaintiff made the accommodation request on ",
        "requested accommodation in ": "Plaintiff requested an accommodation in ",
        "reported discrimination on ": "Plaintiff reported discrimination on ",
        "reported retaliation on ": "Plaintiff reported retaliation on ",
        "reported wage-and-hour violations on ": "Plaintiff reported wage-and-hour violations on ",
        "termination on ": "the termination occurred on ",
        "terminated on ": "Plaintiff was terminated on ",
        "was terminated on ": "Plaintiff was terminated on ",
        "threatened on ": "Plaintiff was threatened on ",
        "was threatened on ": "Plaintiff was threatened on ",
        "denial notice on ": "the denial notice issued on ",
        "eviction threat on ": "the eviction threat followed on ",
        "lost the housing opportunity in ": "the housing opportunity was lost in ",
    }
    for old, new in replacements.items():
        if lowered.startswith(old):
            return new + text[len(old):]
    return text


def _llm_draft_timeout_for_provider(provider: Optional[str]) -> int:
    explicit = str(os.getenv("COMPLAINT_GENERATOR_LLM_DRAFT_TIMEOUT_SECONDS", "") or "").strip()
    if explicit:
        try:
            return max(5, int(float(explicit)))
        except Exception:
            pass

    provider_key = str(provider or "").strip().lower()
    if provider_key:
        provider_override = str(
            os.getenv(f"COMPLAINT_GENERATOR_LLM_DRAFT_TIMEOUT_SECONDS_{provider_key.upper()}", "") or ""
        ).strip()
        if provider_override:
            try:
                return max(5, int(float(provider_override)))
            except Exception:
                pass
    return int(DEFAULT_LLM_DRAFT_TIMEOUTS_BY_PROVIDER.get(provider_key, DEFAULT_LLM_DRAFT_TIMEOUT_SECONDS))


def _resolve_llm_draft_backend(
    provider: Optional[str],
    model: Optional[str],
) -> Dict[str, Optional[str]]:
    requested_provider = str(provider or "").strip()
    requested_model = str(model or "").strip()

    env_default_provider = str(os.getenv("COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER", "") or "").strip()
    effective_provider = requested_provider or env_default_provider or DEFAULT_LLM_DRAFT_PROVIDER
    provider_key = effective_provider.lower()

    env_provider_model = str(
        os.getenv(f"COMPLAINT_GENERATOR_LLM_DRAFT_MODEL_{provider_key.upper()}", "") or ""
    ).strip()
    env_default_model = str(os.getenv("COMPLAINT_GENERATOR_LLM_DRAFT_MODEL", "") or "").strip()
    effective_model = (
        requested_model
        or env_provider_model
        or env_default_model
        or DEFAULT_LLM_DRAFT_MODELS_BY_PROVIDER.get(provider_key)
        or None
    )

    return {
        "provider": effective_provider,
        "model": effective_model,
        "requested_provider": requested_provider or None,
        "requested_model": requested_model or None,
    }


def _resolve_llm_draft_backend_candidates(
    provider: Optional[str],
    model: Optional[str],
) -> List[Dict[str, Optional[str]]]:
    requested_provider = str(provider or "").strip()
    requested_model = str(model or "").strip()
    env_default_provider = str(os.getenv("COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER", "") or "").strip()

    if requested_provider or env_default_provider:
        return [_resolve_llm_draft_backend(provider, model)]

    candidates: List[Dict[str, Optional[str]]] = []
    seen: set[str] = set()
    for fallback_provider in DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN:
        provider_key = str(fallback_provider or "").strip().lower()
        if not provider_key or provider_key in seen:
            continue
        seen.add(provider_key)
        candidate = _resolve_llm_draft_backend(
            fallback_provider,
            requested_model or None,
        )
        # An internal default is a selected provider, not an explicit request.
        candidate["requested_provider"] = None
        candidates.append(candidate)
    return candidates or [_resolve_llm_draft_backend(provider, model)]


def _pleading_timeline_sentence(value: Optional[str], fallback: str) -> str:
    text = _normalize_fragment(value, fallback)
    if not text:
        return _pleading_sentence(fallback, fallback)
    sentence_parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if len(sentence_parts) >= 2:
        fragments = []
        for part in sentence_parts[:6]:
            cleaned = re.sub(r"[.?!]+$", "", part).strip()
            if cleaned:
                fragments.append(_timeline_clause_fragment(cleaned))
        if not fragments:
            return _pleading_sentence(text, fallback)
        sentence = " ".join(
            f"{fragment.rstrip('.') }." if not str(fragment).rstrip().endswith(".") else str(fragment).rstrip()
            for fragment in fragments
        )
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if sentence[:1].isalpha():
            sentence = sentence[0].upper() + sentence[1:]
        return sentence
    parts = [part.strip() for part in re.split(r",|\band\b", text) if part.strip()]
    if not parts:
        return _pleading_sentence(text, fallback)
    fragments = [_timeline_clause_fragment(part) for part in parts]
    if len(fragments) == 1:
        sentence = fragments[0]
    elif len(fragments) == 2:
        sentence = f"{fragments[0]}, and {fragments[1]}"
    else:
        sentence = f"{', '.join(fragments[:-1])}, and {fragments[-1]}"
    sentence = re.sub(r"\s+", " ", sentence).strip()
    if sentence[:1].isalpha():
        sentence = sentence[0].upper() + sentence[1:]
    if not sentence.endswith("."):
        sentence = f"{sentence}."
    return sentence


def _formalize_relief_item(value: Optional[str]) -> str:
    text = _normalize_fragment(value, "Other appropriate relief")
    lowered = text.lower()
    replacements = {
        "back pay": "Back pay and lost benefits",
        "front pay": "Front pay in lieu of reinstatement",
        "injunctive relief": "Appropriate injunctive and equitable relief",
        "reinstatement": "Reinstatement to Plaintiff's former position or a comparable position",
        "attorney fees": "Reasonable attorney's fees and costs",
        "attorney's fees": "Reasonable attorney's fees and costs",
        "fees": "Reasonable fees and costs",
        "declaratory relief": "Declaratory relief as authorized by law",
        "compensatory damages": "Compensatory damages according to proof",
        "damages": "Damages according to proof",
    }
    return replacements.get(lowered, text)


def _court_header_line(value: Optional[str]) -> str:
    text = _normalize_fragment(value, "FOR THE APPROPRIATE JUDICIAL DISTRICT")
    upper = text.upper()
    if "UNITED STATES DISTRICT COURT" in upper:
        return "FOR THE APPROPRIATE JUDICIAL DISTRICT"
    if upper.startswith("FOR "):
        return upper
    if "DISTRICT OF" in upper:
        return f"FOR {upper}" if upper.startswith("THE ") else f"FOR THE {upper}"
    return "FOR THE APPROPRIATE JUDICIAL DISTRICT"


def _build_export_structure_summary(markdown_text: str) -> Dict[str, Any]:
    parsed = parse_legal_document(str(markdown_text or ""))
    payload = parsed.to_dict()
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []
    payload["summary"] = {
        "has_header": bool(header),
        "court_line_count": len(header.get("court_lines") or []),
        "party_line_count": len(header.get("party_lines") or []),
        "title_line_count": len(header.get("title_lines") or []),
        "section_count": len(sections),
        "section_kinds": [str(section.get("kind") or "") for section in sections[:20] if isinstance(section, dict)],
        "numbered_paragraph_count": int(payload.get("numbered_paragraph_count") or 0),
        "bullet_count": int(payload.get("bullet_count") or 0),
        "code_block_count": int(payload.get("code_block_count") or 0),
        "all_caps_heading_count": int(payload.get("all_caps_heading_count") or 0),
        "title": str(payload.get("title") or ""),
    }
    return payload


def _slugify_filename(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower())
    return normalized.strip("-") or "complaint-packet"


def _normalize_claim_type(value: Optional[str]) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized or "retaliation"


def _claim_type_display_name(value: Optional[str]) -> str:
    normalized = _normalize_claim_type(value)
    return _CLAIM_TYPE_LABELS.get(normalized, normalized.replace("_", " ").title())


def _claim_element_label(value: Optional[str]) -> str:
    normalized = str(value or "").strip()
    for element in _CLAIM_ELEMENTS:
        if str(element.get("id") or "").strip() == normalized:
            return str(element.get("label") or normalized).strip()
    return normalized.replace("_", " ").strip() or "an identified claim element"


def _formal_evidence_summary_item(item: Dict[str, Any], *, kind: str) -> str:
    title = _evidence_display_title(item, kind=kind)
    element_label = _claim_element_label(item.get("claim_element_id")).lower()
    if kind == "testimony":
        return f"testimony presently identified as '{title}' on the {element_label} element"
    return f"documentary exhibit presently identified as '{title}' on the {element_label} element"


def _compact_evidence_reference_item(item: Dict[str, Any]) -> str:
    title = _evidence_display_title(item, kind=str(item.get("kind") or "evidence"))
    element_label = _claim_element_label(item.get("claim_element_id")).strip() or "Claim element"
    return f"{title} ({element_label})"


def _exhibit_label(index: int) -> str:
    if index < 0:
        return "Exhibit ?"
    value = index
    letters = ""
    while True:
        value, remainder = divmod(value, 26)
        letters = chr(ord("A") + remainder) + letters
        if value == 0:
            break
        value -= 1
    return f"Exhibit {letters}"


def _evidence_display_title(item: Dict[str, Any], *, kind: str) -> str:
    raw_title = str(item.get("title") or f"Untitled {kind}").strip()
    if not raw_title.lower().startswith("local import:"):
        return raw_title

    source = str(item.get("source") or "")
    filename = raw_title.split(":", 1)[-1].strip()
    path_tail = source.split("local_artifact_import:", 1)[-1].strip() if "local_artifact_import:" in source else ""
    lowered_filename = filename.lower()
    lowered_path = path_tail.lower()

    explicit_mappings = {
        "a38c7914-ea37-4c2f-a815-711d4a97c92b.txt": "HACC ACOP policy",
        "8ee6f7d1-0c36-48e4-9677-336b95fb9858.txt": "HACC HCV Administrative Plan",
        "hud_fair_housing_act.html": "HUD Fair Housing Act materials",
        "ors_chapter_659a_discrimination_definitions_and_procedures.html": "ORS chapter 659A discrimination provisions",
        "ors_chapter_456_housing_authorities.html": "ORS chapter 456 housing-authority provisions",
        "945af141-c7d1-4973-88c0-b57024243114.txt": "HACC grievance and hearing policy text",
        "b53a0523-fa60-4df6-bba3-6ae34a47cb02.txt": "HACC reasonable-accommodation policy text",
        "exhibit_index.md": "Temporary CLI session exhibit index",
        "email_evidence_memo.md": "Temporary CLI session email evidence memo",
        "reasonable_accommodation_ocr_memo.md": "Reasonable accommodation OCR memo",
        "chronology_evidence_matrix.json": "Chronology evidence matrix",
        "summary.json": "HACC knowledge-graph summary",
        "engine.py": "HACC research engine source",
        "hacc_corpus.summary.json": "HACC corpus index summary",
        "hacc_enhanced_index_20260314_055513.summary.json": "HACC enhanced index summary",
        "evidence_review.md": "Prior evidence review memorandum",
        "evidence_review.json": "Prior evidence review data",
        "p1_critical_civil_rights_fair-housing.aspx": "Oregon fair-housing guidance",
        "p1_critical_civil_rights_racial-discrimination.aspx": "Oregon racial-discrimination guidance",
        "p2_procurement_&_rules_fair_housing_equal_opp": "Oregon fair-housing equal-opportunity rules",
        "p3_regulatory_find-affordable-housing.aspx": "Oregon affordable-housing guidance",
        "p3_regulatory_housing-counseling.aspx": "Oregon housing-counseling guidance",
        "p3_regulatory_housing-for-veterans.aspx": "Oregon housing-for-veterans guidance",
    }
    if lowered_filename in explicit_mappings:
        return explicit_mappings[lowered_filename]

    if "evidence_review_" in lowered_path and lowered_filename.endswith(".md"):
        return "Prior evidence review memorandum"
    if "evidence_review_" in lowered_path and lowered_filename.endswith(".json"):
        return "Prior evidence review data"
    if lowered_filename.endswith(".html") or lowered_filename.endswith(".aspx"):
        cleaned = re.sub(r"\.(html|aspx)$", "", filename, flags=re.IGNORECASE)
        cleaned = cleaned.replace("_", " ").replace("-", " ").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned[:1].upper() + cleaned[1:] if cleaned else raw_title
    cleaned = re.sub(r"\.[A-Za-z0-9]+$", "", filename)
    cleaned = cleaned.replace("_", " ").replace("-", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:1].upper() + cleaned[1:] if cleaned else raw_title


def _evidence_priority(item: Dict[str, Any]) -> int:
    title = _evidence_display_title(item, kind=str(item.get("kind") or "evidence")).lower()
    source = str(item.get("source") or "").lower()
    score = 0
    if "chronology evidence matrix" in title:
        score += 100
    if "email evidence memo" in title:
        score += 95
    if "reasonable accommodation ocr memo" in title:
        score += 90
    if "exhibit index" in title:
        score += 85
    if "evidence review" in title:
        score += 70
    if "acop" in title or "administrative plan" in title:
        score += 60
    if "fair housing act" in title or "659a" in title or "456" in title:
        score += 55
    if "temporary-cli-session-migration" in source or "workspace-generated" in source:
        score += 40
    if "migrated_sources/research_results/evidence_review_" in source:
        score += 20
    return score


def _claim_type_filing_guidance(value: Optional[str]) -> str:
    normalized = _normalize_claim_type(value)
    return {
        "retaliation": (
            "Emphasize protected activity, employer knowledge, temporal proximity, retaliatory motive, adverse action, "
            "and damages. Keep the chronology tight and make the causation theory explicit."
        ),
        "employment_discrimination": (
            "Emphasize protected status or protected conduct, discriminatory treatment, comparator or disparate-treatment logic "
            "when present, adverse employment action, damages, and requested relief tied to employment harm."
        ),
        "housing_discrimination": (
            "Emphasize housing rights, discriminatory denial or interference, protected status or protected housing activity, "
            "housing-related harm, and the requested equitable or damages relief."
        ),
        "due_process_failure": (
            "Emphasize the deprivation, missing notice or hearing protections, procedural defects, resulting harm, and the specific "
            "procedural relief or damages being sought."
        ),
        "consumer_protection": (
            "Emphasize the deceptive or unfair practice, reliance or transaction context when present, resulting economic harm, "
            "and restitutionary or injunctive relief."
        ),
    }.get(
        normalized,
        "Shape the complaint like a formal civil pleading with a clear chronology, concrete harm, and requested relief grounded in the record.",
    )


def _claim_type_count_heading(value: Optional[str]) -> str:
    normalized = _normalize_claim_type(value)
    return {
        "retaliation": "COUNT I - RETALIATION",
        "employment_discrimination": "COUNT I - EMPLOYMENT DISCRIMINATION",
        "housing_discrimination": "COUNT I - HOUSING DISCRIMINATION",
        "due_process_failure": "COUNT I - DUE PROCESS VIOLATION",
        "consumer_protection": "COUNT I - CONSUMER PROTECTION",
    }.get(normalized, f"COUNT I - {_claim_type_display_name(normalized).upper()}")


def _claim_type_required_allegations(value: Optional[str]) -> List[str]:
    normalized = _normalize_claim_type(value)
    return {
        "retaliation": [
            "Allege the protected activity with specificity.",
            "Allege defendant knowledge of the protected activity.",
            "Allege the adverse action and the chronology tying it to the protected activity.",
            "Allege resulting damages and requested relief.",
        ],
        "employment_discrimination": [
            "Allege the discriminatory treatment or adverse employment action with specificity.",
            "Allege the protected status, protected conduct, or prohibited motive that makes the treatment unlawful.",
            "Allege the chronology, comparators, disparate treatment, or surrounding facts supporting discriminatory inference when present.",
            "Allege resulting damages and requested relief tied to employment harm.",
        ],
        "housing_discrimination": [
            "Allege the housing-related denial, interference, limitation, or retaliation with specificity.",
            "Allege the protected housing status, rights, or protected housing activity that makes the conduct unlawful.",
            "Allege the property, housing benefit, tenancy, or housing opportunity context clearly enough to read like a real housing pleading.",
            "Allege resulting housing harm, economic harm, and requested equitable or damages relief.",
        ],
        "due_process_failure": [
            "Allege the deprivation or adverse action imposed by defendant.",
            "Allege the missing notice, hearing, review, appeal, or other procedural protection.",
            "Allege the chronology showing plaintiff was deprived without the required process.",
            "Allege resulting harm and requested procedural or damages relief.",
        ],
        "consumer_protection": [
            "Allege the unfair, deceptive, or unlawful practice with specificity.",
            "Allege the transaction, consumer relationship, or commercial context.",
            "Allege how plaintiff was misled, harmed, overcharged, or otherwise injured.",
            "Allege resulting damages, restitution, injunctive relief, or other requested relief.",
        ],
    }.get(
        normalized,
        [
            "Allege the unlawful conduct with specificity.",
            "Allege the chronology and resulting harm clearly.",
            "Allege why the pleaded facts support the claim for relief.",
        ],
    )


def _claim_type_formal_example_snippet(value: Optional[str]) -> str:
    normalized = _normalize_claim_type(value)
    return {
        "retaliation": (
            "7. Plaintiff engaged in protected activity by reporting discrimination to human resources.\n"
            "8. Defendant knew of Plaintiff's protected activity before imposing the challenged adverse action.\n"
            "9. Within days of that protected activity, Defendant terminated Plaintiff, supporting a strong inference of retaliatory motive."
        ),
        "employment_discrimination": (
            "7. Plaintiff is a member of a protected class and was performing the job in a satisfactory manner.\n"
            "8. Defendant nevertheless subjected Plaintiff to discriminatory terms, conditions, or termination.\n"
            "9. Comparable employees outside Plaintiff's protected group were treated more favorably under similar circumstances."
        ),
        "housing_discrimination": (
            "7. Plaintiff sought to rent, retain, or enjoy housing on equal terms protected by law.\n"
            "8. Defendant denied, limited, or interfered with that housing opportunity because of Plaintiff's protected housing status or activity.\n"
            "9. As a result, Plaintiff lost housing stability, incurred relocation-related harm, or was denied equal housing access."
        ),
        "due_process_failure": (
            "7. Defendant deprived Plaintiff of a protected interest without adequate notice.\n"
            "8. Defendant failed to provide the hearing, review, or procedural safeguards required before imposing that deprivation.\n"
            "9. Plaintiff suffered concrete harm because the challenged action occurred without constitutionally adequate process."
        ),
        "consumer_protection": (
            "7. Defendant made deceptive or unfair representations in connection with a consumer transaction.\n"
            "8. Plaintiff relied on or was exposed to those representations in the course of the transaction.\n"
            "9. Plaintiff suffered economic loss or other consumer harm as a result of Defendant's deceptive practice."
        ),
    }.get(
        normalized,
        "7. Plaintiff alleges specific unlawful conduct by Defendant.\n"
        "8. Defendant's conduct caused concrete harm to Plaintiff.\n"
        "9. Plaintiff seeks relief that remedies the pleaded misconduct."
    )


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


def _normalize_llm_complaint_body(body: str, claim_type: Optional[str] = None) -> tuple[str, List[str]]:
    normalized = str(body or "").replace("\r\n", "\n").strip()
    if not normalized:
        return "", []

    notes: List[str] = []

    court_caption_match = re.search(
        r"(?im)^\s{0,3}(?:#{1,6}\s+)?in the united states district court\s*$",
        normalized,
    )
    if court_caption_match and court_caption_match.start() > 0:
        normalized = normalized[court_caption_match.start() :].lstrip()
        notes.append("trimmed_leading_preamble")

    normalized_court_caption = re.sub(
        r"(?im)^\s{0,3}(?:#{1,6}\s+)?in the united states district court\s*$",
        "IN THE UNITED STATES DISTRICT COURT",
        normalized,
    )
    if normalized_court_caption != normalized:
        normalized = normalized_court_caption
        notes.append("normalized_court_caption")

    normalized_civil_action = re.sub(
        r"(?im)^civil action no\.\s*:\s*([_A-Z0-9.-]+)\s*$",
        r"Civil Action No. \1",
        normalized,
    )
    if normalized_civil_action != normalized:
        normalized = normalized_civil_action
        notes.append("normalized_civil_action_heading")

    heading_patterns = [
        r"IN THE UNITED STATES DISTRICT COURT",
        r"Civil Action No\.\s*[_A-Z0-9.-]+",
        r"COMPLAINT FOR .+",
        r"JURY TRIAL DEMANDED",
        r"NATURE OF THE ACTION",
        r"JURISDICTION AND VENUE",
        r"PARTIES",
        r"FACTUAL ALLEGATIONS",
        r"EVIDENTIARY SUPPORT AND NOTICE",
        r"CLAIM FOR RELIEF",
        r"COUNT I - .+",
        r"PRAYER FOR RELIEF",
        r"JURY DEMAND",
        r"SIGNATURE BLOCK",
    ]
    heading_pattern = "|".join(f"(?:{pattern})" for pattern in heading_patterns)
    without_markdown_headings = re.sub(
        rf"(?m)^\s{{0,3}}#{1,6}\s+({heading_pattern})\s*$",
        r"\1",
        normalized,
    )
    without_generic_heading_hashes = re.sub(
        r"(?m)^\s{0,3}#{1,6}\s+([A-Z][A-Z0-9 .:&'()/_-]+)\s*$",
        r"\1",
        without_markdown_headings,
    )
    without_heading_emphasis = re.sub(
        rf"(?m)^\s*(?:\*\*|__)\s*({heading_pattern}|[A-Z][A-Z0-9 .:&'()/_-]+)\s*(?:\*\*|__)\s*$",
        r"\1",
        without_generic_heading_hashes,
    )
    if without_heading_emphasis != normalized:
        normalized = without_heading_emphasis
        notes.append("removed_markdown_heading_markup")

    # Trim obvious non-pleading appendices or workspace scaffolding that can
    # appear after an otherwise-usable complaint body.
    trailing_section_markers = [
        "\nAPPENDIX A - ",
        "\nAPPENDIX B - ",
        "\nAPPENDIX C - ",
        "\nAPPENDIX D - ",
        "\nAPPENDIX E - ",
        "\nAPPENDIX F - ",
        "\nWORKING CASE SYNOPSIS",
        "\nCOMPLAINT RECORD",
        "\nWORKFLOW SUMMARY",
    ]
    cut_points = [normalized.find(marker) for marker in trailing_section_markers if normalized.find(marker) > 0]
    if cut_points:
        normalized = normalized[: min(cut_points)].rstrip()
        notes.append("trimmed_workspace_appendices")

    replacements = {
        "current complaint record": "present evidentiary record",
        "support review": "present evidentiary posture",
        "workflow summary": "pleading summary",
        "complaint record": "pleading record",
        "support matrix": "evidentiary posture",
        "json": "record",
        "sdk": "record",
    }
    for old, new in replacements.items():
        updated = re.sub(re.escape(old), new, normalized, flags=re.IGNORECASE)
        if updated != normalized:
            notes.append(f"replaced:{old}")
            normalized = updated

    normalized_paragraphs = re.sub(r"(?m)^(\s*)(\d+)\)\s+", r"\1\2. ", normalized)
    if normalized_paragraphs != normalized:
        normalized = normalized_paragraphs
        notes.append("normalized_numbered_paragraphs")

    canonical_heading_map = {
        "NATURE OF THE ACTION": "NATURE OF THE ACTION",
        "JURISDICTION AND VENUE": "JURISDICTION AND VENUE",
        "PARTIES": "PARTIES",
        "FACTUAL ALLEGATIONS": "FACTUAL ALLEGATIONS",
        "EVIDENTIARY SUPPORT AND NOTICE": "EVIDENTIARY SUPPORT AND NOTICE",
        "CLAIM FOR RELIEF": "CLAIM FOR RELIEF",
        "PRAYER FOR RELIEF": "PRAYER FOR RELIEF",
        "JURY DEMAND": "JURY DEMAND",
        "SIGNATURE BLOCK": "SIGNATURE BLOCK",
    }
    for variant, canonical in canonical_heading_map.items():
        updated = re.sub(rf"(?im)^{re.escape(variant)}\s*:\s*$", canonical, normalized)
        updated = re.sub(rf"(?im)^{re.escape(variant)}\s*$", canonical, updated)
        if updated != normalized:
            normalized = updated
            notes.append("normalized_section_heading_punctuation")

    updated_count_heading_variants = re.sub(
        r"(?im)^count\s+(?:one|1|i)\s*[-:]\s*",
        "COUNT I - ",
        normalized,
    )
    if updated_count_heading_variants != normalized:
        normalized = updated_count_heading_variants
        notes.append("normalized_count_heading")

    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()

    # If the model omitted the exact claim heading but otherwise produced a
    # usable pleading body, normalize the heading to the selected claim type.
    if claim_type:
        preferred_heading = f"COMPLAINT FOR {_claim_type_display_name(claim_type).upper()}"
        preferred_count_heading = _claim_type_count_heading(claim_type)
        if preferred_heading not in normalized:
            if _looks_like_formal_complaint_candidate(normalized):
                with_injected_heading = re.sub(
                    r"(?im)^(civil action no\.\s*[_\sA-Z0-9.-]+)\s*$",
                    rf"\1\n\n{preferred_heading}",
                    normalized,
                    count=1,
                )
                if with_injected_heading == normalized:
                    with_injected_heading = f"{preferred_heading}\n\n{normalized}"
                if with_injected_heading != normalized:
                    normalized = with_injected_heading
                    notes.append("injected_missing_complaint_heading")
        updated_heading = re.sub(
            r"(?im)^complaint for .+$",
            preferred_heading,
            normalized,
            count=1,
        )
        if updated_heading != normalized:
            notes.append("normalized_complaint_heading")
            normalized = updated_heading
        updated_count = re.sub(
            r"(?im)^count i - .+$",
            preferred_count_heading,
            normalized,
            count=1,
        )
        if updated_count != normalized:
            notes.append("normalized_count_heading")
            normalized = updated_count

    return normalized, sorted(set(notes))


def _parse_json_object(text: str) -> Dict[str, Any]:
    stripped = _strip_code_fences(text)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", stripped):
        start = match.start()
        try:
            parsed, end = decoder.raw_decode(stripped[start:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            trailing = stripped[start + end :].strip()
            if not trailing or trailing.startswith("```") or trailing.startswith("Thanks") or trailing.startswith("Note"):
                return parsed
    return {}


def _required_formal_complaint_markers() -> List[str]:
    return [
        "IN THE UNITED STATES DISTRICT COURT",
        "Civil Action No. ________________",
        "COMPLAINT FOR",
        "JURISDICTION AND VENUE",
        "FACTUAL ALLEGATIONS",
        "EVIDENTIARY SUPPORT AND NOTICE",
        "COUNT I -",
        "PRAYER FOR RELIEF",
        "JURY DEMAND",
        "SIGNATURE BLOCK",
    ]


def _formal_complaint_forbidden_meta_phrases() -> List[str]:
    return [
        "workflow summary",
        "complaint record",
        "support matrix",
        "mcp",
        "sdk",
        "product explanation",
        "json",
    ]


def _formal_complaint_validation_issues(body: str, claim_type: Optional[str] = None) -> List[str]:
    complaint_body = str(body or "").strip()
    issues: List[str] = []
    for marker in _required_formal_complaint_markers():
        if marker not in complaint_body:
            issues.append(f"Missing formal marker: {marker}")

    if not re.search(r"(?m)^\s*\d+\.\s+", complaint_body):
        issues.append("Missing numbered pleading paragraphs.")

    lowered = complaint_body.lower()
    for phrase in _formal_complaint_forbidden_meta_phrases():
        if phrase in lowered:
            issues.append(f"Contains meta-summary language: {phrase}")

    if claim_type:
        preferred_heading = f"COMPLAINT FOR {_claim_type_display_name(claim_type).upper()}"
        preferred_count_heading = _claim_type_count_heading(claim_type)
        if preferred_heading not in complaint_body:
            issues.append(f"Missing preferred complaint heading: {preferred_heading}")
        if preferred_count_heading not in complaint_body:
            issues.append(f"Missing preferred count heading: {preferred_count_heading}")
    return issues


def _build_complaint_output_release_gate(
    *,
    claim_type: str,
    draft_strategy: str,
    filing_shape_score: int,
    claim_type_alignment_score: int,
    missing_elements: int,
    evidence_item_count: int,
) -> Dict[str, Any]:
    normalized_claim_type = _normalize_claim_type(claim_type)
    normalized_strategy = str(draft_strategy or "template").strip() or "template"
    if filing_shape_score >= 85 and claim_type_alignment_score >= 85 and missing_elements == 0 and evidence_item_count > 0:
        verdict = "pass"
        reason = (
            "The exported complaint currently reads like a filing-ready "
            f"{_claim_type_display_name(normalized_claim_type).lower()} complaint and the record is materially supported."
        )
    elif filing_shape_score >= 75 and claim_type_alignment_score >= 75 and evidence_item_count > 0:
        verdict = "warning"
        reason = (
            "The exported complaint is moving in the right direction, but it still needs tighter proof posture, "
            "claim alignment, or filing polish before it should be treated as client-safe."
        )
    else:
        verdict = "blocked"
        reason = (
            "The exported complaint is not yet formal or well-aligned enough to treat the current UI flow as safe for real legal clients."
        )
    return {
        "verdict": verdict,
        "reason": reason,
        "claim_type": normalized_claim_type,
        "claim_type_label": _claim_type_display_name(normalized_claim_type),
        "draft_strategy": normalized_strategy,
        "filing_shape_score": int(filing_shape_score or 0),
        "claim_type_alignment_score": int(claim_type_alignment_score or 0),
        "missing_elements": int(missing_elements or 0),
        "evidence_item_count": int(evidence_item_count or 0),
    }


def _release_gate_score_from_verdict(verdict: Optional[str]) -> int:
    normalized = str(verdict or "").strip().lower()
    if normalized in {"pass", "client_safe"}:
        return 100
    if normalized == "warning":
        return 70
    if normalized == "blocked":
        return 20
    return 35


def _build_local_client_release_gate_for_state(state: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
    overview = dict(review.get("overview") or {})
    draft = dict(state.get("draft") or {})
    claim_type = _normalize_claim_type(state.get("claim_type"))
    if not draft:
        return {
            "verdict": "blocked",
            "reason": "No complaint draft exists yet, so the exported filing quality has not been validated.",
            "claim_type": claim_type,
            "claim_type_label": _claim_type_display_name(claim_type),
            "draft_strategy": None,
            "filing_shape_score": 0,
            "claim_type_alignment_score": 0,
            "missing_elements": int(overview.get("missing_elements") or 0),
            "evidence_item_count": int(overview.get("testimony_items") or 0) + int(overview.get("document_items") or 0),
            "status": "unavailable",
        }

    body = str(draft.get("body") or "")
    sync_metadata = dict(draft.get("sync_metadata") or {})
    legal_corpus_review = dict(sync_metadata.get("legal_corpus_review") or {})
    logic_review = dict(sync_metadata.get("logic_review") or {})
    validation_issues = _formal_complaint_validation_issues(body, claim_type)
    evidence_item_count = int(overview.get("testimony_items") or 0) + int(overview.get("document_items") or 0)
    filing_shape_score = max(0, min(100, 100 - (len(validation_issues) * 10)))
    expected_heading = f"COMPLAINT FOR {_claim_type_display_name(claim_type).upper()}"
    expected_count_heading = _claim_type_count_heading(claim_type)
    alignment_matches = int(expected_heading in body) + int(expected_count_heading in body)
    claim_type_alignment_score = 100 if alignment_matches == 2 else 50 if alignment_matches == 1 else 0
    gate = _build_complaint_output_release_gate(
        claim_type=claim_type,
        draft_strategy=str(draft.get("draft_strategy") or "template"),
        filing_shape_score=filing_shape_score,
        claim_type_alignment_score=claim_type_alignment_score,
        missing_elements=int(overview.get("missing_elements") or 0),
        evidence_item_count=evidence_item_count,
    )
    if bool(legal_corpus_review.get("has_blockers")) or bool(logic_review.get("has_blockers")):
        blockers: List[str] = []
        if bool(legal_corpus_review.get("has_blockers")):
            blockers.append(
                f"Legal-corpus-only mode still has {int(legal_corpus_review.get('unsupported_assertion_count') or 0)} unsupported assertion(s)."
            )
        if bool(logic_review.get("has_blockers")):
            blockers.append(
                "Formal proof coverage, contradiction, or chronology checks are still failing for the latest Mike sync."
            )
        gate.update(
            {
                "verdict": "blocked",
                "reason": " ".join(blockers).strip() or str(gate.get("reason") or ""),
                "grounding_mode": str(sync_metadata.get("grounding_mode") or DEFAULT_MIKE_GROUNDING_MODE),
                "grounding_coverage_percent": int(legal_corpus_review.get("coverage_percent") or 0),
                "proof_status": str(logic_review.get("proof_status") or "needs_review"),
            }
        )
    return gate


def _has_required_formal_complaint_markers(body: str) -> bool:
    return not _formal_complaint_validation_issues(body)


def _looks_like_formal_complaint_candidate(body: str) -> bool:
    text = str(body or "")
    if "IN THE UNITED STATES DISTRICT COURT" not in text:
        return False
    heuristic_markers = [
        "NATURE OF THE ACTION",
        "JURISDICTION AND VENUE",
        "FACTUAL ALLEGATIONS",
        "CLAIM FOR RELIEF",
        "PRAYER FOR RELIEF",
        "SIGNATURE BLOCK",
    ]
    matched = sum(1 for marker in heuristic_markers if marker in text)
    return matched >= 4


def generate_decentralized_id() -> Dict[str, Any]:
    try:
        UCANManager = _require_ipfs_attr(
            "ipfs_datasets_py.processors.auth.ucan",
            "UCANManager",
        )

        manager = UCANManager.get_instance()
        if manager.initialize():
            keypair = manager.generate_keypair()
            return {
                "did": keypair.did,
                "method": "did:key",
                "provider": "ipfs_datasets_py.processors.auth.ucan.UCANManager",
            }
    except Exception as exc:
        return {
            "did": f"did:key:fallback-{uuid.uuid4().hex}",
            "method": "did:key",
            "provider": "fallback",
            "warning": str(exc),
        }

    return {
        "did": f"did:key:fallback-{uuid.uuid4().hex}",
        "method": "did:key",
        "provider": "fallback",
        "warning": "UCAN manager did not initialize cleanly.",
    }


_PRIVACY_MODE_NOTICE = (
    "Processing choice is saved per case. Remote Grok processing requires explicit consent, "
    "and Grok can read submitted prompt content when you authorize it. "
    "Local encryption at rest is separate from remote processing. "
    "Use /privacy local to disable future remote calls, or /privacy grok to authorize them."
)


def _privacy_helpers():
    from integrations.ipfs_datasets.llm import (
        build_complaint_privacy_context,
        coerce_effective_privacy_policy,
        complaint_data_class_inventory,
        inspect_privacy_policy,
        privacy_policy_for_mode,
    )

    return {
        "build_complaint_privacy_context": build_complaint_privacy_context,
        "coerce_effective_privacy_policy": coerce_effective_privacy_policy,
        "complaint_data_class_inventory": complaint_data_class_inventory,
        "inspect_privacy_policy": inspect_privacy_policy,
        "privacy_policy_for_mode": privacy_policy_for_mode,
    }


def _state_case_id(state: Mapping[str, Any], user_id: str) -> str:
    case_id = str(state.get("case_id") or user_id or "").strip()
    return case_id or str(user_id or "")


def _sync_operation_consent_state(state: Dict[str, Any], user_id: str, case_id: str) -> None:
    """Bump the case consent generation when the saved processing choice changes."""

    from integrations.ipfs_datasets.llm import (
        OPERATION_CONSENT_CONTRACT,
        OPERATION_CONSENT_VERSION,
        PRIVACY_PROCESSING_GROK,
    )

    prior = state.get("operation_consent") if isinstance(state.get("operation_consent"), dict) else {}
    raw_generation = prior.get("generation")
    generation = raw_generation + 1 if type(raw_generation) is int and not isinstance(raw_generation, bool) and raw_generation >= 0 else 1
    mode = str((state.get("privacy_policy") or {}).get("processing_mode") or "")
    state["operation_consent"] = {
        "contract": OPERATION_CONSENT_CONTRACT,
        "version": OPERATION_CONSENT_VERSION,
        "user_id": user_id,
        "case_id": case_id,
        "generation": generation,
        "revoked": mode != PRIVACY_PROCESSING_GROK,
        "grants": [],
    }


def _apply_effective_privacy_policy(state: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    helpers = _privacy_helpers()
    case_id = _state_case_id(state, user_id)
    state["case_id"] = case_id
    raw_policy = state.get("privacy_policy")
    public_local = str(state.get("public_processing_mode") or "") == "local"
    if isinstance(raw_policy, dict) and str(raw_policy.get("processing_mode") or "") == "local":
        public_local = True
        raw_policy = dict(raw_policy)
        raw_policy["processing_mode"] = "local_private"
    inspection = helpers["inspect_privacy_policy"](
        raw_policy,
        user_id=user_id,
        case_id=case_id,
    )
    policy = inspection["policy"]
    if public_local and policy.get("cloud_processing_enabled") is not True:
        state["public_processing_mode"] = "local"
    state["privacy_policy"] = policy
    state["privacy_policy_load"] = {
        "admitted": bool(inspection["admitted"]),
        "reason": str(inspection["reason"] or ""),
        "cloud_processing_enabled": bool(inspection["cloud_processing_enabled"]),
    }
    state.setdefault("privacy_notice_shown", False)
    return state


def _default_state(user_id: str) -> Dict[str, Any]:
    state = {
        "user_id": user_id,
        "case_id": user_id,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "claim_type": _normalize_claim_type("retaliation"),
        "case_synopsis": "",
        "intake_session_schema": INTAKE_SESSION_SCHEMA,
        "original_complaint": _empty_original_complaint(),
        "intake_answers": {},
        "intake_history": [],
        "evidence": {"testimony": [], "documents": []},
        "document_annotations": [],
        "annotation_knowledge_graph": {"entities": [], "relationships": []},
        "workspace_annotation_index": {"by_tag": {}, "by_collection": {}, "by_document_type": {}},
        "filing_metadata": {},
        "draft": None,
        "latest_packet_export": None,
        "latest_export_critic": None,
        "ui_readiness": None,
        "privacy_notice_shown": False,
        "mike_integration": {
            "last_handoff": None,
            "last_sync": None,
            "handoff_history": [],
            "sync_history": [],
            "audit_trail": [],
        },
    }
    return _apply_effective_privacy_policy(state, user_id)


def _canonical_review_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class _ReviewFactAcceptance:
    """Private server context; no public wrapper or JSON field accepts it."""
    workspace: Any
    review_service: Any
    authority: Any
    actor: str
    canonical: str
    case_id: str
    proposal: Dict[str, Any]
    request_id: str
    request_sha256: str
    state_identity: Any
    graph_revision: str
    private_revision: str
    session_revision: int

    def check_preimage(self, state: Mapping[str, Any], *, workspace: Any, actor: str, case_id: str) -> None:
        if (workspace is not self.workspace or actor != self.actor or case_id != self.case_id
                or state.get("user_id") != self.canonical):
            raise WorkspaceAuthorizationDenied()
        if self.workspace._case_legal_context_identity(state) != self.state_identity:
            raise WorkspacePersistenceError("Acceptance source changed.", code="revision_conflict", public_status="conflict")
        self.authority.revalidate(actor_principal_id=self.actor, workspace=self.workspace, require_owner=True)

    def reprove_review(self) -> None:
        # The caller's canonical writer already owns the source lock. This
        # public service operation acquires ONLY its review lock, in that order.
        record = self.review_service.reprove_proposal_for_owner(self.actor,
            case_id=self.case_id, proposal_id=self.proposal["proposal_id"], authority=self.authority,
            expected_review_revision=self.proposal["review_revision"],
            expected_record_sha256=self.proposal["record_sha256"])
        if _canonical_review_sha(record) != self.proposal["record_sha256"]:
            raise WorkspacePersistenceError("Review changed before publication.", code="revision_conflict", public_status="conflict")

    def write_receipt(self, state: Dict[str, Any], correction: Mapping[str, Any], projection: Mapping[str, Any]) -> None:
        ledger = state.setdefault("canonical_review_acceptances", {})
        if not isinstance(ledger, dict) or self.request_id in ledger:
            raise WorkspacePersistenceError("Acceptance preimage changed.", code="revision_conflict", public_status="conflict")
        receipt = {"schema": "case-review-canonical-fact-acceptance@1", "task_id": "CIMP-GUI-47",
            "status": "accepted", "applied": True, "acceptance_persisted": True,
            "request_id": self.request_id, "request_sha256": self.request_sha256,
            "proposal_id": self.proposal["proposal_id"], "proposal_record_sha256": self.proposal["record_sha256"],
            "review_revision": self.proposal["review_revision"],
            "review_ledger_sha256": self.proposal["review_ledger_sha256"],
            "base_source": deepcopy(self.proposal["source_base"]),
            "accepting_owner_actor": self.actor, "canonical_owner_principal_id": self.canonical,
            "case_id": self.case_id, "target_stable_id": self.proposal["record"]["target_id"],
            "replacement_stable_id": correction.get("replacement_stable_id"),
            "base_graph_revision": self.graph_revision, "base_session_revision": self.session_revision,
            "base_private_revision": self.private_revision,
            "result_graph_revision": correction.get("graph_revision"),
            "result_session_revision": projection.get("session_revision"),
            "result_private_revision": str(int(self.private_revision) + 1),
            "invalidated_support_targets": deepcopy(correction.get("affected_support_targets") or []),
            "actual_factual_correction": deepcopy(dict(correction)),
            "review_status_repository_updated": False, "governing_legal_authority": False,
            "legal_sufficiency": False, "executed_proof": False}
        receipt["receipt_sha256"] = _canonical_review_sha(receipt)
        ledger[self.request_id] = receipt


class _ComplaintWorkspaceHandlerBackend(Protocol):
    """Narrow service contract required by the request-handler boundary."""

    def _load_state(self, user_id: str) -> Dict[str, Any]: ...

    def _save_state(self, state: Dict[str, Any], *, before_publish: Optional[Callable[[], Any]] = None) -> Dict[str, Any]: ...

    def _terminal_graph_edit_publication_guard(self, state: Mapping[str, Any], *, actor_principal_id: str,
                                             case_id: str) -> Optional[Callable[[], Any]]: ...

    def _build_question_status(self, answers: Dict[str, Any]) -> List[Dict[str, Any]]: ...

    def _next_question(self, answers: Dict[str, Any]) -> Optional[Dict[str, str]]: ...

    def _question_by_id(self, question_id: Optional[str]) -> Optional[Dict[str, str]]: ...

    def _build_review(self, state: Dict[str, Any]) -> Dict[str, Any]: ...

    def _build_case_synopsis(self, state: Dict[str, Any]) -> str: ...

    def _build_intake_chat_payload(
        self,
        state: Dict[str, Any],
        *,
        accepted_answer: Optional[Dict[str, Any]] = None,
        requested_question_id: Optional[str] = None,
    ) -> Dict[str, Any]: ...

    def _build_draft(
        self,
        state: Dict[str, Any],
        requested_relief: Optional[List[str]] = None,
        *,
        use_llm: bool = False,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config_path: Optional[str] = None,
        backend_id: Optional[str] = None,
    ) -> Dict[str, Any]: ...

    def import_local_evidence(
        self,
        user_id: Optional[str],
        *,
        paths: List[str],
        claim_element_id: str = "causation",
        kind: str = "document",
        evidence_root: Optional[str] = None,
    ) -> Dict[str, Any]: ...


def _encrypted_head(state: Mapping[str, Any]) -> Dict[str, Any]:
    """Public identity of the current encrypted case head.

    The ciphertext itself stays in private storage. Callers compare this
    revision to detect a reply that is older than the head they already show.
    """

    return {
        "schema": "encrypted-case-head-v1",
        "case_id": str(state.get("case_id") or ""),
        "private_revision": str(state.get("private_revision") or "0"),
    }


def _legal_graph_digest(graph: Any) -> str:
    if not isinstance(graph, Mapping):
        return ""
    try:
        body = json.dumps(graph, sort_keys=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _relationship_rows(graph: Any) -> List[Dict[str, str]]:
    raw = graph.get("relationships") if isinstance(graph, Mapping) else None
    values = raw.values() if isinstance(raw, Mapping) else list(raw or [])
    rows: List[Dict[str, str]] = []
    for rel in values:
        if not isinstance(rel, Mapping):
            continue
        attributes = rel.get("attributes") if isinstance(rel.get("attributes"), Mapping) else {}
        rows.append({
            "relationship_id": str(rel.get("id") or ""),
            "relation_type": str(rel.get("relation_type") or rel.get("type") or ""),
            "source_id": str(rel.get("source_id") or ""),
            "target_id": str(rel.get("target_id") or ""),
            "activity_status": str(attributes.get("activity_status") or ""),
        })
    rows.sort(key=lambda item: (item["relationship_id"], item["source_id"], item["target_id"], item["activity_status"]))
    return rows


def _record_support_projection(
    state: Dict[str, Any],
    *,
    effect_id: str,
    kind: str,
    inquiry_id: str,
    revision: Any,
    before_graph: Any,
    after_graph: Any,
    legal_digest: str,
    affected: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Append one support projection for an accepted answer or correction.

    The same effect id is a replay. It does not append a second row and it
    does not rewrite the legal-graph digest stored with the first row.
    """

    ledger = state.get("affected_support_projection")
    if not isinstance(ledger, list):
        ledger = []
        state["affected_support_projection"] = ledger
    for item in ledger:
        if isinstance(item, dict) and item.get("effect_id") == effect_id:
            return {"applied": False, "duplicate": True, "entry": item, "count": len(ledger)}
    before_rows = _relationship_rows(before_graph)
    after_rows = _relationship_rows(after_graph)
    before_keys = {(row["relationship_id"], row["activity_status"], row["source_id"], row["target_id"]) for row in before_rows}
    changed = [
        row for row in after_rows
        if (row["relationship_id"], row["activity_status"], row["source_id"], row["target_id"]) not in before_keys
    ]
    if isinstance(affected, list) and affected:
        changed = [dict(item) if isinstance(item, Mapping) else {"target_id": str(item)} for item in affected]
    after_mapping = after_graph if isinstance(after_graph, Mapping) else {}
    before_mapping = before_graph if isinstance(before_graph, Mapping) else {}
    entry = {
        "effect_id": effect_id,
        "kind": kind,
        "inquiry_id": str(inquiry_id or ""),
        "expected_question_revision": revision,
        "graph_version": str(after_mapping.get("graph_version") or ""),
        "previous_graph_version": str(before_mapping.get("graph_version") or ""),
        "factual_graph_changed": _legal_graph_digest(after_mapping) != _legal_graph_digest(before_mapping),
        "affected": changed,
        "legal_graph_sha256": legal_digest,
        "changes_law": False,
    }
    ledger.append(entry)
    return {"applied": True, "duplicate": False, "entry": entry, "count": len(ledger)}


def _pending_inquiry_copy(state: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), Mapping) else {}
    pending = projection.get("pending_inquiry") if isinstance(projection, Mapping) else None
    if isinstance(pending, Mapping):
        return dict(pending)
    controls = state.get("terminal_controls") if isinstance(state.get("terminal_controls"), Mapping) else {}
    stored = controls.get("pending_inquiry") if isinstance(controls, Mapping) else None
    return dict(stored) if isinstance(stored, Mapping) else None


def _terminal_edit_receipt(
    *,
    status: str,
    message: str,
    error_code: Optional[str] = None,
    pending_inquiry: Optional[Mapping[str, Any]] = None,
    pending_reselected: bool = False,
    correction: Optional[Mapping[str, Any]] = None,
    graph_revision: str = "",
    session_revision: int = 0,
    actor_principal_id: str = "",
    canonical_owner_principal_id: str = "",
) -> Dict[str, Any]:
    error = None
    if error_code:
        error = {"code": error_code, "resumable": error_code != "event_conflict", "legal_sufficiency": False}
    receipt = {
        "contract_version": "terminal-graph-edit-v1",
        "status": status,
        "message": message,
        "display_only": False,
        "legal_sufficiency": False,
        "awaiting_user": False,
        "worker_stalled": False,
        "pending_reselected": bool(pending_reselected),
        "pending_inquiry": dict(pending_inquiry) if isinstance(pending_inquiry, Mapping) else None,
        "graph_revision": graph_revision,
        "session_revision": session_revision,
        "correction": dict(correction) if isinstance(correction, Mapping) else None,
        "actor_principal_id": str(actor_principal_id or ""),
        "canonical_owner_principal_id": str(canonical_owner_principal_id or ""),
        "actor_matches_canonical_owner": bool(canonical_owner_principal_id) and str(actor_principal_id or "") == str(canonical_owner_principal_id),
        "error": error,
    }
    if error_code:
        receipt["error_code"] = error_code
    return receipt


def _edit_source_context(envelope: Mapping[str, Any], replacement: str, event_id: str) -> Dict[str, Any]:
    from integrations.ipfs_datasets.types import source_byte_hash

    message_id = f"edit-{event_id}"
    return {
        "source_text": replacement,
        "source_kind": str(envelope.get("source_kind") or "user_statement"),
        "source_id": message_id,
        "message_id": message_id,
        "assertion_status": "asserted",
        "extractor_version": str(envelope.get("extractor_version") or "complaint-mediator"),
        "source_hash": source_byte_hash(replacement),
        "source_span": {
            "start": 0,
            "end": len(replacement.encode("utf-8")),
            "text": replacement,
            "unit": "byte",
        },
        "subject_key": str(envelope.get("subject_key") or "fact"),
    }


def _active_assertion_matches(knowledge: Any, answer: str) -> list[tuple[int, str, Dict[str, Any]]]:
    ledger = knowledge.factual_ledger()
    states = ledger.get("assertion_states") if isinstance(ledger.get("assertion_states"), Mapping) else {}
    revisions = ledger.get("revisions") if isinstance(ledger.get("revisions"), list) else []
    indexes: Dict[str, int] = {}
    for record in revisions:
        if not isinstance(record, Mapping):
            continue
        stable = str(record.get("stable_id") or record.get("new_stable_id") or "")
        if stable:
            indexes[stable] = max(indexes.get(stable, 0), int(record.get("revision_index") or 0))
    matches: list[tuple[int, str, Dict[str, Any]]] = []
    for stable_id, record in states.items():
        if not isinstance(record, Mapping) or str(record.get("status") or "") != "active":
            continue
        envelope = record.get("envelope") if isinstance(record.get("envelope"), Mapping) else {}
        span = envelope.get("source_span") if isinstance(envelope.get("source_span"), Mapping) else {}
        text = str(span.get("text") or envelope.get("source_text") or "")
        if text != answer:
            continue
        matches.append((indexes.get(str(stable_id), 0), str(stable_id), dict(envelope)))
    return matches


def _contained_assertion_matches(knowledge: Any, answer: str) -> list[tuple[int, str, Dict[str, Any]]]:
    """One active source that contains the answer, or that the answer contains."""

    needle = str(answer or "").strip()
    if len(needle) < 4:
        return []
    ledger = knowledge.factual_ledger()
    states = ledger.get("assertion_states") if isinstance(ledger.get("assertion_states"), Mapping) else {}
    revisions = ledger.get("revisions") if isinstance(ledger.get("revisions"), list) else []
    indexes: Dict[str, int] = {}
    for record in revisions:
        if not isinstance(record, Mapping):
            continue
        stable = str(record.get("stable_id") or record.get("new_stable_id") or "")
        if stable:
            indexes[stable] = max(indexes.get(stable, 0), int(record.get("revision_index") or 0))
    matches: list[tuple[int, str, Dict[str, Any]]] = []
    for stable_id, record in states.items():
        if not isinstance(record, Mapping) or str(record.get("status") or "") != "active":
            continue
        envelope = record.get("envelope") if isinstance(record.get("envelope"), Mapping) else {}
        span = envelope.get("source_span") if isinstance(envelope.get("source_span"), Mapping) else {}
        text = str(span.get("text") or envelope.get("source_text") or "").strip()
        if not text or text == needle:
            continue
        if needle in text or text in needle:
            matches.append((indexes.get(str(stable_id), 0), str(stable_id), dict(envelope)))
    return matches


def _last_eligible_accepted_answer(state: Mapping[str, Any], knowledge: Any) -> Optional[Dict[str, Any]]:
    """Last accepted answer that still has one active assertion."""

    history = state.get("intake_history") if isinstance(state.get("intake_history"), list) else []
    ineligible = {"skipped", "unknown", "refused", "deferred"}
    for item in reversed(history):
        if not isinstance(item, Mapping):
            continue
        disposition = str(item.get("disposition") or "accepted").strip().lower()
        if disposition in ineligible:
            continue
        answer = str(item.get("answer") or "").strip()
        if not answer or answer.lower() in _UNKNOWN_INTAKE_ANSWERS:
            continue
        stable_id = str(item.get("target_stable_id") or item.get("stable_id") or "").strip()
        ledger = knowledge.factual_ledger()
        states = ledger.get("assertion_states") if isinstance(ledger.get("assertion_states"), Mapping) else {}
        if stable_id:
            record = states.get(stable_id) if isinstance(states.get(stable_id), Mapping) else {}
            if str(record.get("status") or "") == "active":
                envelope = record.get("envelope") if isinstance(record.get("envelope"), Mapping) else {}
                return {
                    "question_id": str(item.get("question_id") or ""),
                    "answer": answer,
                    "stable_id": stable_id,
                    "entity_id": str(record.get("entity_id") or ""),
                    "envelope": dict(envelope),
                    "history_audit": str(item.get("audit_id") or ""),
                }
        matches = _active_assertion_matches(knowledge, answer)
        if not matches:
            contained = _contained_assertion_matches(knowledge, answer)
            matches = contained if len(contained) == 1 else []
        if not matches:
            continue
        _index, matched_id, envelope = sorted(matches)[-1]
        record = states.get(matched_id) if isinstance(states.get(matched_id), Mapping) else {}
        return {
            "question_id": str(item.get("question_id") or ""),
            "answer": answer,
            "stable_id": matched_id,
            "entity_id": str(record.get("entity_id") or ""),
            "envelope": envelope,
            "history_audit": str(item.get("audit_id") or ""),
        }
    return None


def _correction_actor_ids(state: Mapping[str, Any]) -> tuple[str, str]:
    """Actual actor, then canonical owner. They are not copied from each other."""

    from .workspace_case_authority import current_workspace_case_authority

    authority = current_workspace_case_authority()
    if authority is not None:
        return str(authority.actor_principal_id or ""), str(authority.canonical_owner_principal_id or "")
    return str(state.get("user_id") or ""), ""


def _assertion_owner(state: Mapping[str, Any], stable_id: str, envelope: Mapping[str, Any]) -> tuple[str, bool]:
    env_actor = str((envelope or {}).get("actor") or "").strip()
    history_actor = ""
    history = state.get("intake_history") if isinstance(state.get("intake_history"), list) else []
    for item in history:
        if not isinstance(item, Mapping):
            continue
        linked = {str(item.get("target_stable_id") or ""), str(item.get("stable_id") or "")}
        if stable_id not in linked:
            continue
        actor = str(item.get("actor_principal_id") or "").strip()
        if actor:
            history_actor = actor
    if env_actor and history_actor and env_actor != history_actor:
        return "", True
    return env_actor or history_actor, False


def _target_from_stable(state: Mapping[str, Any], knowledge: Any, stable_id: str) -> Optional[Dict[str, Any]]:
    ledger = knowledge.factual_ledger()
    states = ledger.get("assertion_states") if isinstance(ledger.get("assertion_states"), Mapping) else {}
    record = states.get(stable_id) if isinstance(states.get(stable_id), Mapping) else {}
    if str(record.get("status") or "") != "active":
        return None
    envelope = record.get("envelope") if isinstance(record.get("envelope"), Mapping) else {}
    span = envelope.get("source_span") if isinstance(envelope.get("source_span"), Mapping) else {}
    text = str(span.get("text") or envelope.get("source_text") or "")
    question_id = ""
    history = state.get("intake_history") if isinstance(state.get("intake_history"), list) else []
    for item in history:
        if not isinstance(item, Mapping):
            continue
        if stable_id not in {str(item.get("target_stable_id") or ""), str(item.get("stable_id") or "")}:
            continue
        question_id = str(item.get("question_id") or question_id)
        if not text:
            text = str(item.get("answer") or "")
    return {
        "question_id": question_id,
        "answer": text,
        "stable_id": stable_id,
        "entity_id": str(record.get("entity_id") or ""),
        "envelope": dict(envelope),
    }


def _eligible_correction_for_actor(
    state: Mapping[str, Any],
    knowledge: Any,
    actor: str,
    target_stable_id: str,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """The caller's active assertion. Another participant's fact is not eligible."""

    requested = str(target_stable_id or "").strip()
    if requested:
        target = _target_from_stable(state, knowledge, requested)
        if target is None:
            return None, "missing_target"
        owner, conflict = _assertion_owner(state, requested, target.get("envelope") or {})
        if conflict or (owner and owner != actor):
            return None, "unauthorized_actor"
        return target, None
    history = state.get("intake_history") if isinstance(state.get("intake_history"), list) else []
    ineligible = {"skipped", "unknown", "refused", "deferred"}
    for item in reversed(history):
        if not isinstance(item, Mapping):
            continue
        disposition = str(item.get("disposition") or "accepted").strip().lower()
        if disposition in ineligible:
            continue
        answer = str(item.get("answer") or "").strip()
        if not answer or answer.lower() in _UNKNOWN_INTAKE_ANSWERS:
            continue
        stable_id = str(item.get("target_stable_id") or item.get("stable_id") or "").strip()
        owner, conflict = _assertion_owner(state, stable_id, {})
        if conflict or (owner and owner != actor):
            continue
        if stable_id:
            target = _target_from_stable(state, knowledge, stable_id)
            if target is not None:
                owner, conflict = _assertion_owner(state, stable_id, target.get("envelope") or {})
                if conflict or (owner and owner != actor):
                    continue
                return target, None
        matches = _active_assertion_matches(knowledge, answer)
        if len(matches) != 1:
            contained = _contained_assertion_matches(knowledge, answer)
            matches = contained if len(contained) == 1 else []
        if len(matches) != 1:
            continue
        _index, matched_id, envelope = matches[0]
        owner, conflict = _assertion_owner(state, matched_id, envelope)
        if conflict or (owner and owner != actor):
            continue
        ledger = knowledge.factual_ledger()
        states = ledger.get("assertion_states") if isinstance(ledger.get("assertion_states"), Mapping) else {}
        record = states.get(matched_id) if isinstance(states.get(matched_id), Mapping) else {}
        return {
            "question_id": str(item.get("question_id") or ""),
            "answer": answer,
            "stable_id": matched_id,
            "entity_id": str(record.get("entity_id") or ""),
            "envelope": envelope,
        }, None
    return None, "missing_target"


def _stored_graph_revision(state: Mapping[str, Any]) -> str:
    projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), Mapping) else {}
    raw = projection.get("knowledge_graph") if isinstance(projection, Mapping) else None
    if not isinstance(raw, Mapping):
        return ""
    try:
        from complaint_phases.knowledge_graph import KnowledgeGraph
        from mediator.hook_runtime import graph_revision_token

        return graph_revision_token(KnowledgeGraph.from_dict(dict(raw)))
    except Exception:
        return ""


def _factual_correction_offer(state: Mapping[str, Any]) -> Dict[str, Any]:
    """Revisions the browser must send back. This view does not change the graph."""

    projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), Mapping) else {}
    actor, canonical_owner = _correction_actor_ids(state)
    session_revision = int(projection.get("session_revision") or 0) if isinstance(projection, Mapping) else 0
    token = _stored_graph_revision(state)
    target: Optional[Dict[str, Any]] = None
    raw = projection.get("knowledge_graph") if isinstance(projection, Mapping) else None
    if isinstance(raw, Mapping) and actor:
        try:
            from complaint_phases.knowledge_graph import KnowledgeGraph

            target, _code = _eligible_correction_for_actor(state, KnowledgeGraph.from_dict(dict(raw)), actor, "")
        except Exception:
            target = None
    return {
        "schema": "gui-factual-correction-v1",
        "actor_principal_id": actor,
        "canonical_owner_principal_id": canonical_owner,
        "actor_matches_canonical_owner": bool(canonical_owner) and actor == canonical_owner,
        "expected_graph_revision": token,
        "expected_session_revision": session_revision,
        "target_stable_id": str((target or {}).get("stable_id") or ""),
        "prior_answer": str((target or {}).get("answer") or ""),
        "requires_expected_revision": True,
        "legal_sufficiency": False,
    }


def _parse_gui_correction_message(
    message: Optional[str],
    *,
    expected_graph_revision: Optional[str],
    expected_session_revision: Optional[int],
) -> Dict[str, Any]:
    raw = str(message or "").strip()
    body = raw[5:].strip() if raw.lower().startswith("/edit") else raw
    parsed: Dict[str, Any] = {}
    if body.startswith("{"):
        try:
            loaded = json.loads(body)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            parsed = loaded
    replacement = str(parsed.get("replacement") or "").strip() if parsed else body
    graph_value = parsed.get("expected_graph_revision", expected_graph_revision)
    session_value = parsed.get("expected_session_revision", expected_session_revision)
    conflict = ""
    if expected_graph_revision not in {None, ""} and parsed.get("expected_graph_revision") not in {None, ""}:
        if str(parsed.get("expected_graph_revision")) != str(expected_graph_revision):
            conflict = "stale_target"
    if expected_session_revision is not None and parsed.get("expected_session_revision") not in {None, ""}:
        if str(parsed.get("expected_session_revision")) != str(expected_session_revision):
            conflict = conflict or "stale_target"
    session_revision: Optional[int]
    if session_value in {None, ""}:
        session_revision = None
    else:
        try:
            session_revision = int(session_value)
        except (TypeError, ValueError):
            session_revision = None
            conflict = conflict or "stale_target"
    graph_revision = None if graph_value in {None, ""} else str(graph_value)
    return {
        "replacement": replacement,
        "expected_graph_revision": graph_revision,
        "expected_session_revision": session_revision,
        "actor_principal_id": str(parsed.get("actor_principal_id") or "").strip(),
        "target_stable_id": str(parsed.get("target_stable_id") or "").strip(),
        "conflict": conflict,
    }


def _append_correction_history(
    state: Dict[str, Any],
    target: Mapping[str, Any],
    replacement: str,
    receipt: Mapping[str, Any],
    *,
    actor_principal_id: str = "",
) -> None:
    question_id = str(target.get("question_id") or "")
    answers = state.setdefault("intake_answers", {})
    if not isinstance(answers, dict):
        answers = {}
        state["intake_answers"] = answers
    if question_id:
        answers[question_id] = replacement
    history = state.setdefault("intake_history", [])
    if not isinstance(history, list):
        history = []
        state["intake_history"] = history
    history.append({
        "question_id": question_id,
        "answer": replacement,
        "previous_answer": str(target.get("answer") or ""),
        "disposition": "corrected",
        "target_stable_id": str(receipt.get("replacement_stable_id") or ""),
        "supersedes_stable_id": str(target.get("stable_id") or ""),
        "captured_at": state.get("updated_at"),
        "display_only": False,
        "actor_principal_id": str(actor_principal_id or receipt.get("actor_principal_id") or ""),
    })


def _reselect_affected_pending(
    actions: Any,
    knowledge: Any,
    target: Mapping[str, Any],
    pending_before: Optional[Mapping[str, Any]],
) -> tuple[Dict[str, Any], bool]:
    meta = getattr(actions, "_interview_meta", None)
    if not isinstance(meta, dict):
        return dict(pending_before or {}), False
    pending = dict(meta.get("pending_inquiry") or pending_before or {})
    entity_id = str(target.get("entity_id") or "")
    stable_id = str(target.get("stable_id") or "")
    bound = str(pending.get("target_id") or "")
    affected = bound not in {"", "unknown"} and bound in {entity_id, stable_id}
    ledger = knowledge.factual_ledger()
    for inquiry in ledger.get("inquiry_targets") or []:
        if not isinstance(inquiry, Mapping):
            continue
        same_inquiry = str(inquiry.get("inquiry_id") or "") == str(pending.get("inquiry_id") or "")
        same_target = str(inquiry.get("entity_id") or "") == entity_id or str(inquiry.get("stable_id") or "") == stable_id
        if same_inquiry and same_target and str(inquiry.get("status") or "") == "reopened":
            affected = True
    if not affected:
        meta["pending_inquiry"] = pending
        return pending, False
    question_text = str(pending.get("question") or "")
    for question in ledger.get("reopened_questions") or []:
        if not isinstance(question, Mapping):
            continue
        context = question.get("context") if isinstance(question.get("context"), Mapping) else {}
        if str(context.get("inquiry_id") or "") == str(pending.get("inquiry_id") or ""):
            question_text = str(question.get("question") or question_text)
            break
    revision = int(meta.get("question_revision") or pending.get("revision") or 0) + 1
    meta["question_revision"] = revision
    pending["question"] = question_text
    pending["revision"] = revision
    pending["reopened"] = True
    pending["target_id"] = bound or entity_id
    meta["pending_inquiry"] = pending
    return pending, True


_ADAPTIVE_NON_FACT_ANSWERS = {
    "unknown": "unknown",
    "i do not know": "unknown",
    "i don't know": "unknown",
    "i dont know": "unknown",
    "idk": "unknown",
    "not sure": "unknown",
    "unsure": "unknown",
    "deferred": "deferred",
    "defer": "deferred",
    "later": "deferred",
    "not now": "deferred",
    "ask me later": "deferred",
}


def _adaptive_non_fact_kind(message: Optional[str]) -> Optional[str]:
    return _ADAPTIVE_NON_FACT_ANSWERS.get(str(message or "").strip().lower())


def _preserve_adaptive_gap(state: Dict[str, Any], message: Optional[str], prior: Mapping[str, Any]) -> None:
    """Keep an unknown or deferred answer as an open gap.

    The answered inquiry is recorded on the shared projection. It does not
    become a fact and it does not satisfy the graph target.
    """

    kind = _adaptive_non_fact_kind(message)
    inquiry_id = str(prior.get("inquiry_id") or "")
    if not kind or not inquiry_id:
        return
    projection = state.get("shared_interview")
    if not isinstance(projection, dict):
        return
    marker = "user_answer_unknown" if kind == "unknown" else "user_answer_deferred"
    reasons = [str(item) for item in (projection.get("unknown_reasons") or []) if str(item or "").strip()]
    if marker not in reasons:
        reasons.append(marker)
    projection["unknown_reasons"] = reasons
    gaps = [item for item in (projection.get("preserved_gaps") or []) if isinstance(item, dict)]
    gaps.append({
        "inquiry_id": inquiry_id,
        "target_id": prior.get("target_id"),
        "objective_id": prior.get("objective_id"),
        "target_revision": prior.get("target_revision"),
        "disposition": kind,
        "preserved": True,
        "creates_fact": False,
        "satisfies_requirement": False,
    })
    projection["preserved_gaps"] = gaps[-32:]


def _adaptive_inquiry_view(state: Mapping[str, Any]) -> Dict[str, Any]:
    """Pending question from the shared mediator, never the fixed intake list."""

    projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), Mapping) else {}
    pending = projection.get("pending_inquiry") if isinstance(projection.get("pending_inquiry"), Mapping) else None
    inquiry_id = str((pending or {}).get("inquiry_id") or "")
    pending_open = bool(inquiry_id)
    fixed_ids = [str(question["id"]) for question in _INTAKE_QUESTIONS]
    return {
        "schema": "adaptive-inquiry-v1",
        "source": "shared_mediator",
        "pending": pending_open,
        "inquiry_id": inquiry_id or None,
        "revision": (pending or {}).get("revision") if pending_open else None,
        "prompt": str((pending or {}).get("question") or "") if pending_open else "",
        "objective_id": (pending or {}).get("objective_id") if pending_open else None,
        "target_id": (pending or {}).get("target_id") if pending_open else None,
        "target_revision": (pending or {}).get("target_revision") if pending_open else None,
        "from_fixed_intake_fields": False,
        "fixed_intake_question_ids": fixed_ids,
        "unknown_reasons": [str(item) for item in (projection.get("unknown_reasons") or [])],
        "preserved_gaps": [dict(item) for item in (projection.get("preserved_gaps") or []) if isinstance(item, Mapping)],
        "legal_sufficiency": False,
        "factual_correction": _factual_correction_offer(state),
    }


def _note_terminal_edit_controls(
    state: Dict[str, Any],
    *,
    pending: Mapping[str, Any],
    question_id: str,
    previous: str,
    replacement: str,
    target_stable_id: str,
    replacement_stable_id: str,
    graph_token: str,
    session_revision: int,
) -> None:
    controls = state.get("terminal_controls")
    if not isinstance(controls, dict):
        controls = {}
        state["terminal_controls"] = controls
    controls.setdefault("schema", "terminal-controls-v1")
    controls["paused"] = False
    controls["pending_inquiry"] = dict(pending)
    controls["objective_id"] = pending.get("objective_id")
    controls["graph_revision"] = int(pending.get("revision") or 0)
    narrative = state.get("original_complaint") if isinstance(state.get("original_complaint"), Mapping) else {}
    controls["fingerprint"] = {
        "inquiry_id": str(pending.get("inquiry_id") or ""),
        "question_revision": int(pending.get("revision") or 0),
        "session_revision": int(session_revision),
        "history_len": len(state.get("intake_history") or []),
        "narrative_revision": int(narrative.get("revision") or 0),
        "objective_id": str(pending.get("objective_id") or ""),
        "graph_revision_token": graph_token,
    }
    edits = list(controls.get("edits") or [])
    edits.append({
        "question_id": question_id,
        "previous": previous,
        "replacement": replacement,
        "target_stable_id": target_stable_id,
        "replacement_stable_id": replacement_stable_id,
        "display_only": False,
    })
    controls["edits"] = edits


class ComplaintWorkspaceRequestHandlers:
    """Request-facing mutations isolated from workspace state-shaping helpers.

    ``ComplaintWorkspaceService`` retains its public methods as a compatibility
    facade. This class owns the request lifecycle and depends only on the narrow
    backend contract above, making the handler group independently testable while
    keeping the route, CLI, package, and MCP response shapes stable.
    """

    def __init__(
        self,
        workspace: _ComplaintWorkspaceHandlerBackend,
        *,
        now: Optional[Callable[[], str]] = None,
    ) -> None:
        self.workspace = workspace
        self._now = now

    @staticmethod
    def _normalize_user_id(user_id: Optional[str]) -> str:
        if user_id is None:
            from .workspace_case_authority import (WorkspaceCaseAuthorityError,
                current_workspace_case_authority)
            try:
                authority = current_workspace_case_authority()
            except WorkspaceCaseAuthorityError:
                raise WorkspaceAuthorizationDenied() from None
            if authority is not None:
                return authority.actor_principal_id
        return str(user_id or DEFAULT_USER_ID)

    def _load_state(self, user_id: Optional[str]) -> Dict[str, Any]:
        return self.workspace._load_state(self._normalize_user_id(user_id))

    def _timestamp(self) -> str:
        return self._now() if self._now is not None else _utc_now()

    def _build_session_payload(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Compose the stable session response shared by request entrypoints."""

        answers = state.get("intake_answers") or {}
        return {
            "session": deepcopy(state),
            "questions": self.workspace._build_question_status(answers),
            "next_question": self.workspace._next_question(answers),
            "review": self.workspace._build_review(state),
            "case_synopsis": self.workspace._build_case_synopsis(state),
            "adaptive_inquiry": _adaptive_inquiry_view(state),
            "finite_interview_outcome": finite_interview_outcome(
                state,
                active_question=self.workspace._next_question(answers),
            ),
            "legal_sufficiency": False,
            "changes_law": False,
            "encrypted_head": _encrypted_head(state),
            "affected_support_projection": [
                dict(item) for item in (state.get("affected_support_projection") or []) if isinstance(item, dict)
            ],
        }

    def get_session(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        state = self._load_state(user_id)
        authority = self.workspace._owner_case_authority()
        if authority is None or authority.action in {"case.update", "case.message.send", "case.processing.choose"}:
            state = self.workspace._save_state(state)
        return self._build_session_payload(state)

    def submit_intake_answers(self, user_id: Optional[str], answers: Dict[str, Any]) -> Dict[str, Any]:
        workspace = self.workspace
        state = self._load_state(user_id)
        answer_map = state.setdefault("intake_answers", {})
        history = state.setdefault("intake_history", [])
        for question in _INTAKE_QUESTIONS:
            value = str(answers.get(question["id"]) or "").strip()
            if not value:
                continue
            answer_map[question["id"]] = value
            history.append({"question_id": question["id"], "answer": value, "captured_at": self._timestamp()})
        workspace._save_state(state)
        return self.get_session(str(state.get("user_id")))

    def run_intake_chat_turn(
        self,
        user_id: Optional[str],
        *,
        message: Optional[str] = None,
        question_id: Optional[str] = None,
        expected_question_revision: Optional[int] = None,
        interview_action: Optional[str] = None,
        expected_graph_revision: Optional[str] = None,
        expected_session_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        workspace = self.workspace
        if str(interview_action or "").strip().lower() == "encrypted_resume":
            # Resume opens the encrypted snapshot before any session read so a
            # locked or missing key stays explicit and a browser cache is ignored.
            return workspace.resume_encrypted_browser_interview(user_id, browser_cache=message)
        state = self._load_state(user_id)
        normalized_message = str(message or "").strip()
        if normalized_message.lower() == "/why":
            why = format_terminal_why(state=state)
            payload = workspace._build_intake_chat_payload(state)
            payload["why"] = why
            payload["command"] = "/why"
            payload["stored_as_answer"] = False
            payload["awaiting_user"] = True
            payload["worker_stalled"] = False
            payload["legal_sufficiency"] = False
            payload["question_support"] = why.get("question_support")
            payload["diagnostic_receipt"] = why.get("diagnostic_receipt")
            payload["message"] = why["display"]
            return payload
        if normalized_message.lower() == "/research":
            research = workspace.run_legal_research(
                str(state.get("user_id") or user_id),
                expected_graph_revision=expected_graph_revision,
                expected_session_revision=expected_session_revision,
            )
            fresh = workspace._load_state(str(state.get("user_id") or user_id))
            payload = workspace._build_intake_chat_payload(fresh)
            payload["legal_research"] = research
            payload["command"] = "/research"
            payload["stored_as_answer"] = False
            payload["awaiting_user"] = research.get("error_code") != "stale_research"
            payload["legal_sufficiency"] = False
            payload["status"] = research.get("status")
            payload["message"] = str(research.get("display") or format_legal_research_result(research))
            return payload
        normalized_action = str(interview_action or "").strip().lower()
        if normalized_action in {"pause", "cancel", "cap", "unavailable", "saturate"}:
            return workspace.record_finite_interview_stop(state, normalized_action)
        if normalized_action == "correct" or normalized_message.lower().startswith("/edit"):
            return self._apply_gui_factual_correction(
                state,
                message=normalized_message,
                expected_graph_revision=expected_graph_revision,
                expected_session_revision=expected_session_revision,
            )
        if normalized_action == "resume":
            interview = workspace.apply_shared_interview(
                state,
                message=None,
                question_id=None,
                expected_question_revision=None,
                interview_action="resume",
                narrative_turn=False,
            )
            workspace._save_state(state)
            payload = workspace._build_intake_chat_payload(state)
            payload["interview"] = interview
            return payload
        normalized_question_id = str(question_id or "").strip()
        interview_projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
        before_factual = deepcopy(interview_projection.get("knowledge_graph") or {})
        before_legal_digest = _legal_graph_digest(interview_projection.get("dependency_graph"))
        narrative_turn = normalized_question_id == ORIGINAL_COMPLAINT_QUESTION_ID or (
            not normalized_question_id and _narrative_is_open(state)
        )
        if narrative_turn:
            target_question = dict(_NARRATIVE_INQUIRY)
        else:
            target_question = (
                workspace._question_by_id(normalized_question_id)
                if normalized_question_id
                else workspace._next_question(state.get("intake_answers") or {})
            )
        projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
        pending_graph = projection.get("pending_inquiry") if isinstance(projection.get("pending_inquiry"), dict) else {}
        if not normalized_question_id and not narrative_turn and message and pending_graph.get("inquiry_id"):
            normalized_question_id = str(pending_graph["inquiry_id"])
        graph_inquiry = normalized_question_id.startswith("inq-")
        if normalized_question_id and target_question is None and not graph_inquiry:
            raise ValueError(f"Unknown intake question_id: {question_id}")

        accepted_answer: Optional[Dict[str, Any]] = None
        normalized_message = str(message or "").strip()
        privacy_command = normalized_message.lower()
        if privacy_command in {"/privacy local", "/privacy grok"}:
            helpers = _privacy_helpers()
            mode = "grok" if privacy_command.endswith("grok") else "local"
            case_id = _state_case_id(state, str(state.get("user_id") or self._normalize_user_id(user_id)))
            state["case_id"] = case_id
            state["privacy_policy"] = helpers["privacy_policy_for_mode"](
                str(state.get("user_id") or case_id),
                case_id,
                mode,
            )
            state["public_processing_mode"] = "grok" if mode == "grok" else "local"
            state["privacy_notice_shown"] = True
            workspace._save_state(state)
            payload = workspace._build_intake_chat_payload(
                state,
                accepted_answer=None,
                requested_question_id=question_id,
            )
            payload["privacy_command"] = {
                "applied": True,
                "stored_as_answer": False,
                "processing_mode": state["privacy_policy"]["processing_mode"],
            }
            payload["privacy_notice"] = _PRIVACY_MODE_NOTICE
            pending = payload.get("message") or ""
            payload["message"] = f"Saved privacy mode for this case. The pending question is unchanged.\n{pending}".strip()
            return payload

        joined_effect = None
        if normalized_message and normalized_action not in {"status", "resume"}:
            identity_question = normalized_question_id or str((target_question or {}).get("id") or "")
            joined_effect = workspace._joined_chat_identity(state, identity_question, normalized_message,
                                                            expected_question_revision)
            if any(item.get("effect_id") == joined_effect for item in state.get("intake_history", []) if isinstance(item, dict)):
                payload = workspace._build_intake_chat_payload(state)
                payload["duplicate_answer_effect"] = True
                return payload
        show_privacy_notice = not bool(state.get("privacy_notice_shown"))
        if show_privacy_notice:
            state["privacy_notice_shown"] = True
        if normalized_message and not (graph_inquiry or normalized_action in {"answer", "status"}):
            if target_question is None:
                raise ValueError("The intake flow is already complete for this session.")
            if narrative_turn:
                record = _narrative_record(state)
                revision = int(record.get("revision") or 0) + 1
                captured_at = self._timestamp()
                revisions = list(record.get("revisions") or [])
                revisions.append(
                    {
                        "revision": revision,
                        "text": normalized_message,
                        "captured_at": captured_at,
                        "source": "intake_chat",
                    }
                )
                record["schema_version"] = ORIGINAL_COMPLAINT_SCHEMA
                record["text"] = normalized_message
                record["revision"] = revision
                record["revisions"] = revisions
                state["original_complaint"] = record
                accepted_answer = {
                    "question_id": ORIGINAL_COMPLAINT_QUESTION_ID,
                    "answer": normalized_message,
                    "captured_at": captured_at,
                    "kind": "narrative",
                    "revision": revision,
                }
            else:
                answer_map = state.setdefault("intake_answers", {})
                history = state.setdefault("intake_history", [])
                answer_map[target_question["id"]] = normalized_message
                accepted_answer = {
                    "question_id": target_question["id"],
                    "answer": normalized_message,
                    "captured_at": self._timestamp(),
                }
                history.append(deepcopy(accepted_answer))

        interview = workspace.apply_shared_interview(
            state,
            message=normalized_message or None,
            question_id=normalized_question_id or None,
            expected_question_revision=expected_question_revision,
            interview_action=normalized_action or None,
            narrative_turn=bool(normalized_message and narrative_turn),
        )
        if interview.get("status") == "refused":
            payload = workspace._build_intake_chat_payload(state)
            payload["interview"] = interview
            payload["support_projection_updated"] = False
            payload["changes_law"] = False
            return payload
        accepted_graph_answer = bool(
            normalized_message
            and interview.get("status") not in {"refused", "unavailable"}
            and (graph_inquiry or normalized_action == "answer")
            and normalized_action not in {"status", "resume", "review", "why"}
        )
        support_update = {"applied": False, "duplicate": False, "count": len(state.get("affected_support_projection") or [])}
        if accepted_graph_answer:
            after_interview = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
            support_update = _record_support_projection(
                state,
                effect_id=f"answer:{normalized_question_id}:{expected_question_revision}",
                kind="answer",
                inquiry_id=normalized_question_id,
                revision=expected_question_revision,
                before_graph=before_factual,
                after_graph=after_interview.get("knowledge_graph") or {},
                legal_digest=before_legal_digest,
            )
        if joined_effect is not None:
            workspace._commit_joined_snapshot(state, effect_id=joined_effect,
                question_id=identity_question, answer=normalized_message)
        else:
            workspace._save_state(state)
        payload = workspace._build_intake_chat_payload(
            state,
            accepted_answer=accepted_answer,
            requested_question_id=None if accepted_answer is not None or graph_inquiry else question_id,
        )
        payload["interview"] = interview
        payload["support_projection_updated"] = bool(support_update.get("applied"))
        payload["support_projection_duplicate"] = bool(support_update.get("duplicate"))
        payload["changes_law"] = False
        if show_privacy_notice:
            payload["privacy_notice"] = _PRIVACY_MODE_NOTICE
            if str(payload.get("message") or "").startswith("Let's start with the basics."):
                payload["message"] = f"{_PRIVACY_MODE_NOTICE}\n\n{payload['message']}"
        return payload

    def _apply_gui_factual_correction(
        self,
        state: Dict[str, Any],
        *,
        message: str,
        expected_graph_revision: Optional[str],
        expected_session_revision: Optional[int],
    ) -> Dict[str, Any]:
        """Correct one fact through the canonical mediator path.

        The browser sends the revisions it was shown. A stale revision or an
        edit of another participant's assertion is refused and does not write.
        """

        prior_support_effects = {
            str(item.get("effect_id") or "") for item in (state.get("affected_support_projection") or [])
            if isinstance(item, Mapping)
        }
        parsed = _parse_gui_correction_message(
            message,
            expected_graph_revision=expected_graph_revision,
            expected_session_revision=expected_session_revision,
        )
        pending = _pending_inquiry_copy(state)
        actor_id, canonical_owner = _correction_actor_ids(state)
        if parsed["conflict"]:
            receipt = _terminal_edit_receipt(
                status="refused",
                message="Stale concurrent edit rejected. The pending inquiry was kept.",
                error_code=parsed["conflict"],
                pending_inquiry=pending,
                actor_principal_id=actor_id,
                canonical_owner_principal_id=canonical_owner,
            )
        else:
            receipt = self.apply_terminal_graph_edit(
                str(state.get("user_id") or ""),
                parsed["replacement"],
                expected_graph_revision=parsed["expected_graph_revision"],
                expected_session_revision=parsed["expected_session_revision"],
                target_stable_id=parsed["target_stable_id"] or None,
                actor_principal_id=parsed["actor_principal_id"] or None,
                require_expected_revision=True,
            )
        try:
            fresh = self._load_state(str(state.get("user_id") or ""))
        except WorkspacePersistenceError:
            # An issued browser request cannot publish the old private DTO
            # after its live key/read boundary failed. Local legacy behavior
            # remains available only without an issued owner capability.
            if self.workspace._owner_case_authority() is not None:
                raise
            fresh = state
        payload = self.workspace._build_intake_chat_payload(fresh)
        payload["factual_correction"] = receipt
        new_correction_effects = [
            item for item in payload.get("affected_support_projection", [])
            if isinstance(item, Mapping) and item.get("kind") == "correction"
            and str(item.get("effect_id") or "") not in prior_support_effects
        ]
        payload["support_projection_updated"] = receipt.get("status") == "applied" and bool(new_correction_effects)
        correction = receipt.get("correction") if isinstance(receipt.get("correction"), Mapping) else {}
        payload["support_projection_duplicate"] = (
            receipt.get("status") == "applied" and correction.get("idempotent_replay") is True
            and not new_correction_effects
        )
        payload["stored_as_answer"] = receipt.get("status") == "applied"
        payload["command"] = "correct"
        payload["legal_sufficiency"] = False
        payload["message"] = str(receipt.get("message") or payload.get("message") or "")
        return payload

    def apply_terminal_graph_edit(
        self,
        user_id: Optional[str],
        replacement: str,
        *,
        expected_graph_revision: Optional[str] = None,
        expected_session_revision: Optional[int] = None,
        target_stable_id: Optional[str] = None,
        actor_principal_id: Optional[str] = None,
        require_expected_revision: bool = False,
        _review_acceptance: Optional[_ReviewFactAcceptance] = None,
    ) -> Dict[str, Any]:
        """Correct the last eligible accepted answer on the shared factual graph.

        Display history is not a second source of truth. The public correction
        keeps the previous assertion and appends a revision. An unrelated
        pending question stays pending. A pending question bound to the corrected
        target is reopened. A stale graph or session revision is refused.
        """

        text = str(replacement or "").strip()
        if not text:
            return _terminal_edit_receipt(
                status="refused",
                message="Edit needs replacement text. The pending question is unchanged.",
                error_code="correction_required",
            )
        try:
            state = self._load_state(user_id)
        except WorkspacePersistenceError as exc:
            return _terminal_edit_receipt(
                status="unavailable",
                message=f"Edit is unavailable ({exc.code or 'unavailable'}). The pending question is unchanged.",
                error_code=str(exc.code or "unavailable"),
            )
        user = str(state.get("user_id") or user_id or DEFAULT_USER_ID)
        case_id = _state_case_id(state, user)
        actor_id, canonical_owner = _correction_actor_ids(state)
        claimed_actor = str(actor_principal_id or "").strip()
        if _review_acceptance is not None:
            if type(_review_acceptance) is not _ReviewFactAcceptance:
                raise WorkspaceAuthorizationDenied()
            _review_acceptance.check_preimage(state, workspace=self.workspace, actor=actor_id, case_id=case_id)

        def finish(receipt: Dict[str, Any]) -> Dict[str, Any]:
            receipt["actor_principal_id"] = actor_id
            receipt["canonical_owner_principal_id"] = canonical_owner
            receipt["actor_matches_canonical_owner"] = bool(canonical_owner) and actor_id == canonical_owner
            if _review_acceptance is not None and receipt.get("status") == "applied":
                receipt["review_acceptance"] = deepcopy(state["canonical_review_acceptances"][_review_acceptance.request_id])
            return receipt

        if claimed_actor and claimed_actor != actor_id:
            return finish(_terminal_edit_receipt(
                status="refused",
                message="This actor cannot edit that answer. Other participants were left unchanged.",
                error_code="unauthorized_actor",
                pending_inquiry=_pending_inquiry_copy(state),
            ))
        if require_expected_revision and (
            expected_graph_revision is None or str(expected_graph_revision).strip() == "" or expected_session_revision is None
        ):
            return finish(_terminal_edit_receipt(
                status="refused",
                message="A correction needs the expected graph and session revisions. Nothing was changed.",
                error_code="stale_target",
                pending_inquiry=_pending_inquiry_copy(state),
            ))
        projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else None
        before_factual = deepcopy(projection.get("knowledge_graph") or {}) if isinstance(projection, dict) else {}
        legal_snapshot = deepcopy(projection.get("dependency_graph")) if isinstance(projection, dict) and isinstance(projection.get("dependency_graph"), dict) else None
        legal_digest = _legal_graph_digest(legal_snapshot)
        if not isinstance(projection, dict) or projection.get("schema_version") != "shared-interview-session-v1":
            return _terminal_edit_receipt(
                status="unavailable",
                message="Edit is unavailable (session_missing). The pending question is unchanged.",
                error_code="session_missing",
                pending_inquiry=_pending_inquiry_copy(state),
            )
        try:
            publication_guard = self.workspace._terminal_graph_edit_publication_guard(
                state, actor_principal_id=actor_id, case_id=case_id)
        except WorkspacePersistenceError as exc:
            return finish(_terminal_edit_receipt(status="unavailable",
                message="Edit is unavailable. The pending question is unchanged.",
                error_code=str(exc.code or "unavailable"), pending_inquiry=_pending_inquiry_copy(state)))
        before_case_publish = publication_guard
        if _review_acceptance is not None:
            if publication_guard is None:
                raise WorkspaceAuthorizationDenied()
            def before_case_publish():
                publication_guard()
                _review_acceptance.reprove_review()
        try:
            # Never publish a request-local draft through the shared cache,
            # even briefly between factory construction and its removal.
            mediator = self.workspace._mediator_for_shared_interview(user, case_id,
                **({"cache": False} if publication_guard is not None else {}))
            actions = mediator.workflow_actions
            if not actions.interview_started:
                restored = actions.restore_session_projection(projection)
                if restored.get("error"):
                    code = str((restored.get("error") or {}).get("code") or "session_missing")
                    return _terminal_edit_receipt(
                        status="unavailable",
                        message=f"Edit is unavailable ({code}). The pending question is unchanged.",
                        error_code=code,
                        pending_inquiry=_pending_inquiry_copy(state),
                    )
            actions.bind_interview_privacy(state.get("privacy_policy"), user_id=user, case_id=case_id)
            router_state = state.get("intake_router") if isinstance(state.get("intake_router"), dict) else {}
            router_session = str(router_state.get("session_id") or "")
            if not re.fullmatch(r"[0-9a-f]{32}", router_session):
                router_session = uuid.uuid4().hex
            begin_router = getattr(mediator, "begin_intake_router_action", None)
            if callable(begin_router):
                begin_router(
                    owner_id=user,
                    case_id=case_id,
                    session_id=router_session,
                    revision=int((actions._interview_meta or {}).get("session_revision") or 0),
                    previous=router_state,
                )
        except WorkspacePersistenceError as exc:
            return _terminal_edit_receipt(
                status="unavailable",
                message=f"Edit is unavailable ({exc.code or 'unavailable'}). The pending question is unchanged.",
                error_code=str(exc.code or "unavailable"),
                pending_inquiry=_pending_inquiry_copy(state),
            )
        except Exception as exc:
            return _terminal_edit_receipt(
                status="unavailable",
                message=f"Edit is unavailable ({type(exc).__name__}). The pending question is unchanged.",
                error_code="capability_unavailable",
                pending_inquiry=_pending_inquiry_copy(state),
            )
        from complaint_phases.phase_manager import ComplaintPhase

        knowledge = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
        if knowledge is None or not hasattr(knowledge, "factual_ledger"):
            return _terminal_edit_receipt(
                status="unavailable",
                message="Edit is unavailable (capability_unavailable). The pending question is unchanged.",
                error_code="capability_unavailable",
                pending_inquiry=_pending_inquiry_copy(state),
            )
        metadata = getattr(knowledge, "metadata", None)
        if isinstance(metadata, dict) and not str(metadata.get("case_id") or "").strip():
            metadata["case_id"] = case_id
        pending_before = _pending_inquiry_copy(state)
        from mediator.hook_runtime import graph_revision_token

        current_token = graph_revision_token(knowledge)
        current_session = int((actions._interview_meta or {}).get("session_revision") or 0)
        if require_expected_revision and (
            str(expected_graph_revision) != current_token or int(expected_session_revision or 0) != current_session
        ):
            return finish(_terminal_edit_receipt(
                status="refused",
                message="Stale concurrent edit rejected. The pending inquiry was kept.",
                error_code="stale_target",
                pending_inquiry=pending_before,
            ))
        if require_expected_revision:
            target, selection_code = _eligible_correction_for_actor(
                state, knowledge, actor_id, str(target_stable_id or ""),
            )
        else:
            target, selection_code = _last_eligible_accepted_answer(state, knowledge), None
        if target is None:
            code = selection_code or "missing_target"
            if code == "unauthorized_actor":
                message = "This actor cannot edit that answer. Other participants were left unchanged."
            else:
                message = "Nothing to edit yet. The pending question is unchanged."
            return finish(_terminal_edit_receipt(
                status="refused",
                message=message,
                error_code=code,
                pending_inquiry=pending_before,
            ))
        if require_expected_revision:
            graph_token = str(expected_graph_revision)
            session_revision = int(expected_session_revision or 0)
        else:
            graph_token = current_token if expected_graph_revision is None else str(expected_graph_revision)
            session_revision = current_session if expected_session_revision is None else int(expected_session_revision)
        event_id = "edit-" + hashlib.sha256(
            f"{target['stable_id']}|{text}".encode("utf-8")
        ).hexdigest()[:24]
        source_context = _edit_source_context(target.get("envelope") or {}, text, event_id)
        receipt = mediator.apply_factual_correction(
            action="correct",
            target_stable_id=target["stable_id"],
            replacement=text,
            source_context=source_context,
            event_id=event_id,
            case_id=case_id,
            expected_graph_revision=graph_token,
            expected_session_revision=session_revision,
        )
        status = str(receipt.get("status") or "")
        error = receipt.get("error") if isinstance(receipt.get("error"), dict) else {}
        error_code = str(error.get("code") or "")
        if status != "applied":
            if error_code == "stale_target":
                message = "Stale concurrent edit rejected. The pending inquiry was kept."
            elif error_code == "missing_target":
                message = "Nothing to edit yet. The pending question is unchanged."
            elif status == "unavailable":
                message = f"Edit is unavailable ({error_code or 'unavailable'}). The pending question is unchanged."
            else:
                message = f"Edit was refused ({error_code or status or 'refused'}). The pending question is unchanged."
            return finish(_terminal_edit_receipt(
                status=status or "refused",
                message=message,
                error_code=error_code or None,
                pending_inquiry=pending_before,
                correction=receipt,
            ))
        pending, reselected = _reselect_affected_pending(actions, knowledge, target, pending_before)
        exported = actions.export_session_projection()
        if isinstance(exported, dict) and legal_snapshot is not None:
            # A factual correction may invalidate support. It must not rewrite
            # the admitted legal dependency graph that was current at the edit.
            exported["dependency_graph"] = legal_snapshot
        if not isinstance(exported, dict):
            return finish(_terminal_edit_receipt(
                status="unavailable",
                message="Edit is unavailable (projection_invalid). The pending question is unchanged.",
                error_code="projection_invalid",
                pending_inquiry=pending_before,
                correction=receipt,
            ))
        state["shared_interview"] = exported
        if receipt.get("idempotent_replay") is not True:
            _append_correction_history(
                state, target, text, receipt,
                actor_principal_id=actor_id if require_expected_revision else "",
            )
            _record_support_projection(
                state,
                effect_id="correction:" + str(receipt.get("event_id") or target.get("stable_id") or ""),
                kind="correction",
                inquiry_id=str(target.get("question_id") or ""),
                revision=expected_session_revision,
                before_graph=before_factual,
                after_graph=exported.get("knowledge_graph") or {},
                legal_digest=legal_digest,
                affected=list(receipt.get("affected_support_targets") or []),
            )
        _note_terminal_edit_controls(
            state,
            pending=pending,
            question_id=str(target.get("question_id") or ""),
            previous=str(target.get("answer") or ""),
            replacement=text,
            target_stable_id=str(target.get("stable_id") or ""),
            replacement_stable_id=str(receipt.get("replacement_stable_id") or ""),
            graph_token=str(receipt.get("graph_revision") or ""),
            session_revision=int(exported.get("session_revision") or 0),
        )
        if _review_acceptance is not None:
            _review_acceptance.write_receipt(state, receipt, exported)
        try:
            if publication_guard is not None:
                publication_guard()
                self.workspace._save_state(state, before_publish=before_case_publish)
            else:
                self.workspace._save_state(state)
        except WorkspacePersistenceError as exc:
            return finish(_terminal_edit_receipt(
                status="unavailable",
                message=f"Edit is unavailable ({exc.code or 'durability_unproven'}). The pending question is unchanged.",
                error_code=str(exc.code or "durability_unproven"),
                pending_inquiry=pending_before,
                correction=receipt,
            ))
        finally:
            if publication_guard is not None:
                self.workspace._interview_mediators.pop((user, case_id), None)
        if reselected:
            message = "Edited the last recorded answer. The pending question was reopened because its target changed."
        else:
            message = "Edited the last recorded answer. The pending question is unchanged."
        return finish(_terminal_edit_receipt(
            status="applied",
            message=message,
            pending_inquiry=pending,
            pending_reselected=reselected,
            correction=receipt,
            graph_revision=str(receipt.get("graph_revision") or ""),
            session_revision=int(exported.get("session_revision") or 0),
        ))

    def save_evidence(
        self,
        user_id: Optional[str],
        *,
        kind: str,
        claim_element_id: str,
        title: str,
        content: str,
        source: Optional[str] = None,
        attachment_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        workspace = self.workspace
        state = self._load_state(user_id)
        evidence_store = state.setdefault("evidence", {"testimony": [], "documents": []})
        collection_key = "documents" if kind == "document" else "testimony"
        record = {
            "id": f"{collection_key}-{len(evidence_store.get(collection_key, [])) + 1}",
            "kind": kind,
            "claim_element_id": claim_element_id,
            "title": title,
            "content": content,
            "source": source or "",
            "attachment_names": [str(item).strip() for item in list(attachment_names or []) if str(item).strip()],
            "saved_at": self._timestamp(),
        }
        evidence_store.setdefault(collection_key, []).append(record)
        workspace._save_state(state)
        return {
            "saved": record,
            "review": workspace._build_review(state),
            "session": deepcopy(state),
            "case_synopsis": workspace._build_case_synopsis(state),
        }

    async def upload_local_evidence_files(
        self,
        user_id: Optional[str],
        *,
        files: List[Any],
        claim_element_id: str = "causation",
        kind: str = "document",
        evidence_root: Optional[str] = None,
        note: Optional[str] = None,
        note_title: Optional[str] = None,
        source: Optional[str] = "dashboard-chat-upload",
    ) -> Dict[str, Any]:
        if not files:
            raise ValueError("At least one file is required.")

        workspace = self.workspace
        upload_source = str(source or "dashboard-chat-upload").strip() or "dashboard-chat-upload"
        uploaded_files: List[Dict[str, Any]] = []
        memory_files: List[Dict[str, Any]] = []
        for index, file in enumerate(files, start=1):
            original_name = Path(str(getattr(file, "filename", None) or f"upload-{index}")).name or f"upload-{index}"
            file_bytes = file.read()
            if inspect.isawaitable(file_bytes):
                file_bytes = await file_bytes
            if isinstance(file_bytes, str):
                file_bytes = file_bytes.encode("utf-8")
            elif file_bytes is None:
                file_bytes = b""
            else:
                file_bytes = bytes(file_bytes)
            memory_files.append({"filename": original_name, "data": file_bytes})
            uploaded_files.append(
                {
                    "filename": original_name,
                    "content_type": str(getattr(file, "content_type", None) or "application/octet-stream"),
                    "size": len(file_bytes),
                    "storage": "ephemeral-memory",
                }
            )
        payload = workspace.ingest_memory_evidence(
            user_id,
            files=memory_files,
            claim_element_id=claim_element_id,
            kind=kind,
        )
        if payload.get("status") == "unlock_needed":
            payload["uploaded_files"] = uploaded_files
            payload["upload_source"] = upload_source
            return payload

        normalized_note = str(note or "").strip()
        if normalized_note:
            uploaded_names = [item["filename"] for item in uploaded_files if item.get("filename")]
            effective_claim_element_id = claim_element_id
            if claim_element_id in {"auto", "suggested"}:
                first_import = next(iter(payload.get("imported") or []), {})
                effective_claim_element_id = str(
                    first_import.get("effective_claim_element_id")
                    or first_import.get("suggested_claim_element_id")
                    or "causation"
                ).strip() or "causation"
            note_record = self.save_evidence(
                user_id,
                kind="testimony",
                claim_element_id=effective_claim_element_id,
                title=str(note_title or "Chat upload note").strip() or "Chat upload note",
                content=normalized_note,
                source=upload_source,
                attachment_names=uploaded_names,
            )
            payload["note_record"] = note_record.get("saved")
            payload["session"] = note_record.get("session")
            payload["review"] = note_record.get("review")
            payload["case_synopsis"] = note_record.get("case_synopsis")

        payload["uploaded_files"] = uploaded_files
        payload["upload_source"] = upload_source
        return payload

    def generate_complaint(
        self,
        user_id: Optional[str],
        *,
        requested_relief: Optional[List[str]] = None,
        title_override: Optional[str] = None,
        use_llm: bool = False,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config_path: Optional[str] = None,
        backend_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        workspace = self.workspace
        state = self._load_state(user_id)
        draft = workspace._build_draft(
            state,
            requested_relief=requested_relief,
            use_llm=use_llm,
            provider=provider,
            model=model,
            config_path=config_path,
            backend_id=backend_id,
        )
        if title_override:
            draft["title"] = title_override
        state["draft"] = draft
        workspace._save_state(state)
        return {
            "draft": deepcopy(draft),
            "review": workspace._build_review(state),
            "session": deepcopy(state),
            "case_synopsis": workspace._build_case_synopsis(state),
        }

    def update_draft(
        self,
        user_id: Optional[str],
        *,
        title: Optional[str] = None,
        body: Optional[str] = None,
        requested_relief: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        workspace = self.workspace
        state = self._load_state(user_id)
        draft = deepcopy(state.get("draft") or workspace._build_draft(state))
        if title is not None:
            draft["title"] = title
        if body is not None:
            draft["body"] = body
        if requested_relief is not None:
            draft["requested_relief"] = requested_relief
        draft["updated_at"] = self._timestamp()
        state["draft"] = draft
        workspace._save_state(state)
        return {
            "draft": deepcopy(draft),
            "review": workspace._build_review(state),
            "session": deepcopy(state),
            "case_synopsis": workspace._build_case_synopsis(state),
        }

    def update_case_synopsis(self, user_id: Optional[str], synopsis: Optional[str]) -> Dict[str, Any]:
        workspace = self.workspace
        state = self._load_state(user_id)
        state["case_synopsis"] = str(synopsis or "").strip()
        workspace._save_state(state)
        session = self.get_session(str(state.get("user_id")))
        return {
            "session": session["session"],
            "review": session["review"],
            "questions": session["questions"],
            "next_question": session["next_question"],
            "case_synopsis": session["case_synopsis"],
        }

    def update_claim_type(self, user_id: Optional[str], claim_type: Optional[str]) -> Dict[str, Any]:
        workspace = self.workspace
        state = self._load_state(user_id)
        state["claim_type"] = _normalize_claim_type(claim_type)
        workspace._save_state(state)
        session = self.get_session(str(state.get("user_id")))
        return {
            "session": session["session"],
            "review": session["review"],
            "questions": session["questions"],
            "next_question": session["next_question"],
            "case_synopsis": session["case_synopsis"],
            "claim_type": session["session"]["claim_type"],
            "claim_type_label": _claim_type_display_name(session["session"]["claim_type"]),
        }

    def reset_session(self, user_id: Optional[str]) -> Dict[str, Any]:
        workspace = self.workspace
        state = _default_state(self._normalize_user_id(user_id))
        workspace._save_state(state)
        result = self.get_session(str(state["user_id"]))
        retention = workspace.normal_reset_retention_receipt()
        result["private_retention"] = retention
        result["encryption_key_destroyed"] = False
        result["recovery_path_destroyed"] = False
        return result

    def delete_private_case(self, user_id: Optional[str], **options: Any) -> Dict[str, Any]:
        return self.workspace.delete_private_case(user_id, **options)


class _WorkspaceCaseKeyProvider:
    """Resolve through current request admission and the current unlocked store.

    The handle carries no key snapshot or request authority. Retaining it across
    requests or an operator lock does not retain either capability.
    """

    def __init__(self, workspace: "ComplaintWorkspaceService", *, request_authority: Any = None) -> None:
        self._workspace = workspace
        self._request_binding = (request_authority.canonical_owner_principal_id,
            request_authority.case_id, request_authority.resource_id) if request_authority is not None else None

    def resolve(self, binding):
        from integrations.private_storage import PrivateArtifactBinding, canonical_associated_data

        if not isinstance(binding, PrivateArtifactBinding):
            raise WorkspaceAuthorizationDenied()
        if self._request_binding is not None:
            current = self._workspace._owner_case_authority()
            if current is None or (current.canonical_owner_principal_id,
                    current.case_id, current.resource_id) != self._request_binding:
                raise WorkspaceAuthorizationDenied()
        self._workspace._require_private_case_key_access(
            binding.tenant_id, binding.case_id, principal_id=binding.principal_id
        )
        canonical_associated_data(binding)
        return self._workspace._private_key_session().provider().resolve(binding)



def case_legal_source_scope(state: Mapping[str, Any], *, case_id: str) -> str:
    """Hash canonical case sources; this pure value grants no access authority."""
    shared = state["shared_interview"]
    case_file = shared["intake_case_file"]
    context = case_file.get("legal_context") or {}
    selected_context = {name: context.get(name) for name in ("jurisdiction", "jurisdiction_explicit",
        "jurisdiction_applicability", "candidate_jurisdiction", "context_revision", "applicable_law_date",
        "event_date", "event_dates", "filing_reference_date", "corpus_retrieval_date")}
    return hashlib.sha256(json.dumps({"case_id": case_id, "session_id": shared.get("session_id"),
        "knowledge_graph": shared.get("knowledge_graph"), "narrative": _narrative_record(state),
        "legal_context": selected_context, "forum": case_file.get("legal_context_forum"),
        "applicability": case_file.get("legal_context_applicability")},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

class ComplaintWorkspaceService:
    def __init__(
        self,
        root_dir: Optional[Path] = None,
        *,
        access: Optional[WorkspaceAccess] = None,
        authorizer: Optional[WorkspaceAuthorizer] = None,
    ) -> None:
        base_dir = Path(root_dir) if root_dir is not None else _SESSION_DIR
        self._session_dir = Path(os.path.abspath(base_dir))
        if self._session_dir.resolve() != self._session_dir:
            raise WorkspaceAuthorizationDenied()
        self._session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_stat = self._session_dir.lstat()
        if not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != os.getuid():
            raise WorkspaceAuthorizationDenied()
        self._session_directory_identity = (root_stat.st_dev, root_stat.st_ino)
        self._last_draft_refinement_error: Optional[str] = None
        self._default_access = access if access is not None else WorkspaceAccess.trusted_local()
        self._authorizer = authorizer or WorkspaceAuthorizer()
        self.request_handlers = ComplaintWorkspaceRequestHandlers(self)
        self._interview_mediators: Dict[tuple[str, str], Any] = {}
        self._case_directory: Any = None

    def open_case_directory(self, *, key: bytes, key_id: str) -> Any:
        """Open the sealed case namespace index for the authenticated principal.

        The directory lives beside this workspace. Callers select cases by the
        authenticated principal and an explicit case id. A request ``user_id``
        is not a selector. The injected key is not written.
        """

        from applications.case_directory import CaseDirectory

        self._authenticated_case_actor()
        directory = CaseDirectory(self._session_dir / "case-namespaces", key=key, key_id=key_id)
        self._case_directory = directory
        return directory

    def create_independent_case(self, *, supplied_user_id: Optional[str] = None, unreadable_legacy_envelope: Optional[bytes] = None) -> Dict[str, Any]:
        """Mint one owner-only case under the authenticated principal."""

        actor = self._require_case_directory_actor()
        record = self._case_directory.create_case(
            actor_principal_id=actor,
            supplied_user_id=supplied_user_id,
            unreadable_legacy_envelope=unreadable_legacy_envelope,
        )
        return record.identity()

    def adopt_owner_only_case(self, envelope: bytes, *, supplied_user_id: Optional[str] = None) -> Dict[str, Any]:
        """Read a legacy owner-only envelope and record its namespace.

        Missing keys raise ``CaseDirectoryError`` and do not create a case.
        Session plaintext is not stored in the directory.
        """

        actor = self._require_case_directory_actor()
        record, payload = self._case_directory.adopt_owner_only_case(
            actor_principal_id=actor,
            envelope=envelope,
            supplied_user_id=supplied_user_id,
        )
        return {
            "case": record.identity(),
            "legacy_session": payload,
            "persisted_session_plaintext": False,
        }

    def read_owner_only_case(self, envelope: bytes, *, supplied_user_id: Optional[str] = None) -> Dict[str, Any]:
        """Open a legacy owner-only envelope without creating a case."""

        actor = self._require_case_directory_actor()
        return self._case_directory.read_owner_only_case(
            actor_principal_id=actor,
            envelope=envelope,
            supplied_user_id=supplied_user_id,
        )

    def list_independent_cases(self, *, supplied_user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        actor = self._require_case_directory_actor()
        records = self._case_directory.list_cases(actor_principal_id=actor, supplied_user_id=supplied_user_id)
        return [record.identity() for record in records]

    def select_independent_case(self, case_id: str, *, supplied_user_id: Optional[str] = None) -> Dict[str, Any]:
        actor = self._require_case_directory_actor()
        record = self._case_directory.select_case(
            actor_principal_id=actor,
            case_id=case_id,
            supplied_user_id=supplied_user_id,
        )
        return record.identity()

    def _authenticated_case_actor(self) -> str:
        access = self._effective_access()
        if access.trust != "authenticated" or not isinstance(access.principal_id, str) or not access.principal_id:
            raise WorkspaceAuthorizationDenied()
        return str(access.principal_id)

    def _require_case_directory_actor(self) -> str:
        actor = self._authenticated_case_actor()
        if self._case_directory is None:
            raise WorkspacePersistenceError(
                "Case directory is not open.",
                code="case_directory_closed",
                public_status="unavailable",
            )
        return actor

    def remember_invocation_associations(self, user_id: Optional[str], entries: Any) -> Dict[str, Any]:
        """Store invocation associations in the encrypted session without a provider call."""

        from mediator.hook_runtime import merge_router_trace

        state = self._load_state(user_id)
        state["router_trace"] = merge_router_trace(state.get("router_trace"), entries if isinstance(entries, list) else [])
        self._save_state(state)
        receipts = list((state.get("router_trace") or {}).get("receipts") or [])
        return {"provider_replayed": False, "receipts": receipts, "invocations": len(receipts)}

    def apply_shared_interview(
        self,
        state: Dict[str, Any],
        *,
        message: Optional[str],
        question_id: Optional[str],
        expected_question_revision: Optional[int],
        interview_action: Optional[str],
        narrative_turn: bool,
    ) -> Dict[str, Any]:
        """Delegate narrative start, graph answers, and resume to one mediator transition."""
        user_id = str(state.get("user_id") or DEFAULT_USER_ID)
        case_id = _state_case_id(state, user_id)
        self._check_access(user_id, ability="write", case_id=case_id, record_case_id=case_id)
        projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else None
        action = str(interview_action or "").strip().lower()
        graph_question = str(question_id or "").startswith("inq-")
        should_run = bool(narrative_turn or graph_question or action in {"resume", "status", "start", "answer"} or projection)
        if not should_run:
            return {
                "contract_version": "interview-transition-v1",
                "action": "deferred",
                "status": "awaiting_user",
                "awaiting_user": True,
                "legal_sufficiency": False,
                "error": None,
            }
        try:
            # GUI mutations operate on the authenticated DTO in this request.
            # A refused publication must not leave an advanced mediator in the
            # process cache and turn the next legitimate retry into stale input.
            mediator = (self._mediator_for_shared_interview(user_id, case_id, cache=False)
                if self._owner_case_authority() is not None
                else self._mediator_for_shared_interview(user_id, case_id))
            begin_router = getattr(mediator, "begin_intake_router_action", None)
            if callable(begin_router):
                previous_router = state.get("intake_router") if isinstance(state.get("intake_router"), dict) else {}
                router_session = str(previous_router.get("session_id") or "")
                if not re.fullmatch(r"[0-9a-f]{32}", router_session):
                    router_session = uuid.uuid4().hex
                begin_router(owner_id=user_id, case_id=case_id, session_id=router_session,
                             revision=int((projection or {}).get("session_revision") or 0), previous=previous_router)
            kwargs: Dict[str, Any] = {
                "privacy_policy": state.get("privacy_policy"),
                "user_id": user_id,
                "case_id": case_id,
            }
            # Rehydrate first, then apply this same request. A cold answer is
            # never silently consumed as a resume-only operation.
            if projection and not mediator.workflow_actions.interview_started:
                restored = mediator.transition_shared_interview(action="resume", session_projection=projection, **kwargs)
                if restored.get("error"):
                    return restored
            prior_pending = None
            legal_snapshot = None
            if graph_question or action == "answer":
                current_projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
                current_pending = current_projection.get("pending_inquiry") if isinstance(current_projection.get("pending_inquiry"), dict) else None
                prior_pending = dict(current_pending) if current_pending else None
                if isinstance(current_projection.get("dependency_graph"), dict):
                    legal_snapshot = deepcopy(current_projection.get("dependency_graph"))
            if action == "resume":
                receipt = mediator.transition_shared_interview(action="resume", **kwargs)
            elif narrative_turn or action == "start":
                receipt = mediator.transition_shared_interview(
                    action="start",
                    narrative=message or _narrative_record(state).get("text"),
                    **kwargs,
                )
            elif graph_question or action == "answer":
                receipt = mediator.transition_shared_interview(
                    action="answer",
                    answer=message,
                    inquiry_id=question_id,
                    expected_question_revision=expected_question_revision,
                    **kwargs,
                )
            else:
                receipt = mediator.transition_shared_interview(action="status", **kwargs)
            # Refusals are authoritative and have no accepted transition to
            # publish. In particular, an older provider-stage error must not
            # replace a stale-question receipt or change its saved projection.
            if receipt.get("status") == "refused":
                return receipt
            exported = mediator.workflow_actions.export_session_projection()
            if isinstance(exported, dict) and legal_snapshot is not None:
                exported["dependency_graph"] = legal_snapshot
            if exported:
                state["shared_interview"] = exported
                pending = exported.get("pending_inquiry") if isinstance(exported.get("pending_inquiry"), dict) else None
                if isinstance(pending, dict):
                    state["explained_inquiry"] = {
                        key: pending.get(key)
                        for key in (
                            "inquiry_id",
                            "objective_id",
                            "target_id",
                            "target_revision",
                            "why_it_matters",
                            "expected_answer_contract",
                            "expected_update_contract",
                            "source_references",
                            "source_references_status",
                            "grounding_status",
                            "question",
                        )
                    }
            snapshot_router = getattr(mediator, "intake_router_snapshot", None)
            if callable(snapshot_router):
                snapshot = snapshot_router()
                previous_router = state.get("intake_router") if isinstance(state.get("intake_router"), dict) else {}
                prior_receipts = []
                association_keys = {
                    "schema", "invocation_label", "purpose", "case_id", "session_id",
                    "accepted_graph_revision", "live_model_identity_verified", "prompt_logged",
                    "provider_replayed",
                }
                for item in previous_router.get("receipts") or []:
                    if not isinstance(item, dict):
                        continue
                    keys = set(item)
                    core = {"operation", "request_id", "binding_id", "status", "intake_complete"}
                    if not core <= keys or keys - core - association_keys:
                        continue
                    if (item.get("operation") in {"extract_facts", "propose_questions"}
                            and item.get("status") in {"available", "privacy_denied", "provider_unavailable", "malformed_output", "quota", "timeout", "cancelled", "stale_request"}
                            and all(isinstance(item.get(key), str) and re.fullmatch(r"[0-9a-f]{32}", item[key]) for key in ("request_id", "binding_id"))
                            and (item.get("invocation_label") in {None, "real", "fake"})):
                        prior_receipts.append(dict(item))
                seen = {item["request_id"] for item in prior_receipts}
                from mediator.hook_runtime import invocation_association, invocation_label_for_receipt

                graph_payload = exported.get("knowledge_graph") if isinstance(exported, dict) else None
                accepted_revision = ""
                if isinstance(graph_payload, dict):
                    try:
                        from complaint_phases.knowledge_graph import KnowledgeGraph
                        from mediator.hook_runtime import graph_revision_token
                        accepted_revision = graph_revision_token(KnowledgeGraph.from_dict(graph_payload))
                    except Exception:
                        accepted_revision = ""
                backend = getattr(mediator, "_terminal_router_backend", None)
                if backend is None:
                    backends = getattr(mediator, "backends", None) or []
                    backend = backends[0] if backends else None
                backend_by_request = {}
                for backend_receipt in getattr(backend, "task_receipts", []) or []:
                    if isinstance(backend_receipt, dict) and type(backend_receipt.get("request_id")) is str:
                        backend_by_request[backend_receipt["request_id"]] = backend_receipt
                for item in snapshot["receipts"]:
                    if item["request_id"] in seen:
                        continue
                    matched = backend_by_request.get(item["request_id"]) or {}
                    association = invocation_association(
                        invocation_label=invocation_label_for_receipt(matched) if matched else "fake",
                        purpose=item.get("operation"),
                        request_id=item.get("request_id"),
                        case_id=case_id,
                        session_id=router_session,
                        accepted_graph_revision=accepted_revision,
                        live_model_identity_verified=bool(matched.get("live_model_identity_verified")) if matched else False,
                    )
                    stored = dict(item)
                    stored.update(association)
                    prior_receipts.append(stored)
                    seen.add(item["request_id"])
                state["intake_router"] = {**snapshot, "session_id": router_session,
                                          "receipts": prior_receipts[-32:]}
                if snapshot["errors"] and not receipt.get("error"):
                    # Accepted user answers and their graph effects remain in
                    # this same transaction. An unresolved provider stage is
                    # explicit on resume and can never establish completion.
                    receipt["status"] = "awaiting_user" if receipt.get("inquiry") else "unavailable"
                    receipt["awaiting_user"] = bool(receipt.get("inquiry"))
                    receipt["intake_complete"] = False
                    receipt["readiness"] = {"ready_to_advance": False, "legal_sufficiency": False}
                    receipt["error"] = {"code": "provider_unavailable", "resumable": True,
                                        "router_failures": dict(snapshot["errors"]), "legal_sufficiency": False}
                receipt["intake_router"] = deepcopy(state["intake_router"])
            if prior_pending and receipt.get("status") != "refused":
                _preserve_adaptive_gap(state, message, prior_pending)
            return receipt
        except Exception as exc:
            return {
                "contract_version": "interview-transition-v1",
                "action": action or "status",
                "status": "unavailable",
                "awaiting_user": False,
                "legal_sufficiency": False,
                "error": {
                    "code": "capability_unavailable",
                    "resumable": True,
                    "error_type": type(exc).__name__,
                    "legal_sufficiency": False,
                },
            }

    def _mediator_for_shared_interview(self, user_id: str, case_id: str, *, cache: bool = True):
        self._check_access(user_id, ability="read", case_id=case_id, record_case_id=case_id)
        cache_key = (user_id, case_id)
        cached = self._interview_mediators.get(cache_key) if cache else None
        if cached is not None:
            return cached
        from mediator.mediator import Mediator

        # The cache and derived database namespace include both owner and
        # case. Raw caller identifiers never become filesystem components.
        identity = hashlib.sha256(json.dumps([user_id, case_id], separators=(",", ":")).encode()).hexdigest()
        db_dir = self._session_dir / "interview-db" / identity
        db_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        def _interview_backend(prompt, complaint_privacy_context=None, **kwargs):
            from integrations.ipfs_datasets.llm import generate_text_with_metadata
            from mediator.exceptions import UserPresentableException

            host_keys = {"intake_operation", "intake_source_text", "intake_target_refs", "intake_request_id"}
            generated = generate_text_with_metadata(
                prompt, provider="grok_cli", model_name="grok-4.7",
                complaint_privacy_context=complaint_privacy_context,
                **{key: value for key, value in kwargs.items() if key in host_keys},
            )
            if (not isinstance(generated, dict) or generated.get("status") not in {"available", "success"}
                    or generated.get("error") or not isinstance(generated.get("text"), str)):
                from backends.llm_router_backend import ProviderRouteError
                kind = generated.get("failure_kind") if isinstance(generated, dict) else ""
                code = {"malformed": "malformed_output", "quota": "quota", "timeout": "timeout", "cancelled": "cancelled"}.get(kind, "provider_unavailable")
                raise ProviderRouteError({"error_code": code, "intake_complete": False})
            return str(generated.get("text") or "")

        mediator = Mediator(
            [_interview_backend],
            evidence_db_path=str(db_dir / "evidence.db"),
            legal_authority_db_path=str(db_dir / "legal-authority.db"),
            claim_support_db_path=str(db_dir / "claim-support.db"),
        )
        mediator.state.username = user_id
        self.activate_private_evidence_hook(mediator, user_id, case_id)
        self.activate_private_derived_indexes(mediator, user_id, case_id)
        if cache:
            self._interview_mediators[cache_key] = mediator
        return mediator


    def activate_private_evidence_hook(self, mediator: Any, user_id: str, case_id: Optional[str] = None) -> Dict[str, Any]:
        """Inject the current private artifact context into a newly activated evidence hook.

        The Kit encryption owner stays in private storage. A missing key binds
        the hook shut instead of leaving a raw byte path open.
        """

        hook = mediator.evidence_storage
        try:
            context = self._private_artifact_context(user_id, case_id, revision="attachment-1")
        except WorkspacePersistenceError as exc:
            hook.bind_private_artifact_context(None, unavailable_code=str(exc.code or "key_unavailable"))
            return {"status": "unavailable", "code": exc.code, "private_route_bound": True, "plaintext_fallback": False}
        bound = {
            **context,
            "backend": self._private_local_backend(),
            "backend_name": "local_cache",
            "pin_content": False,
            "revision": "attachment-1",
        }
        hook.bind_private_artifact_context(bound)
        return {
            "status": "available",
            "private_route_bound": True,
            "tenant_id": bound["tenant_id"],
            "case_id": bound["case_id"],
            "principal_id": bound["principal_id"],
            "plaintext_fallback": False,
        }

    def activate_private_derived_indexes(self, mediator: Any, user_id: str, case_id: Optional[str] = None) -> Dict[str, Any]:
        """Bind hook derived text to the encrypted owner or leave persistence unavailable.

        An interview-db directory name or mode 0700 is not encryption. Missing
        keys do not open a plaintext preview path.
        """

        hooks = (
            getattr(mediator, "evidence_state", None),
            getattr(mediator, "claim_support", None),
            getattr(mediator, "legal_authority_storage", None),
        )
        present = [hook for hook in hooks if hook is not None and hasattr(hook, "bind_private_derived_index")]
        try:
            context = self._private_artifact_context(user_id, case_id, revision="index-1")
        except WorkspacePersistenceError as exc:
            for hook in present:
                hook.bind_private_derived_index(
                    None,
                    unavailable_code=str(exc.code or "key_unavailable"),
                    directory_mode_private=True,
                )
            return {
                "status": "unavailable",
                "code": exc.code,
                "encrypted": False,
                "encryption_from_path_or_mode_bits": False,
                "directory_mode_private": True,
                "plaintext_fallback": False,
                "index_mode": "unavailable",
            }
        bound = {
            **context,
            "backend": self._private_local_backend(),
            "backend_name": "local_cache",
            "pin_content": False,
            "index_mode": "durable",
            "revision": "index-1",
        }
        for hook in present:
            hook.bind_private_derived_index(bound, directory_mode_private=True)
        return {
            "status": "available",
            "encrypted": True,
            "encryption_from_path_or_mode_bits": False,
            "directory_mode_private": True,
            "plaintext_fallback": False,
            "index_mode": "durable",
            "case_id": bound["case_id"],
            "tenant_id": bound["tenant_id"],
            "remote_durable": False,
        }

    def _private_artifact_context(self, user_id: str, case_id: Optional[str] = None, *, revision: str = "session-v1") -> Dict[str, Any]:
        """Resolve current request admission and the live user-owned key session."""
        from integrations.private_storage import PrivateArtifactBinding, PrivateKeyMaterialError

        # A replaced or symlinked session root must fail closed before any key
        # lookup. Following it would surface unlock_needed instead of the
        # directory boundary refusal, and could read a foreign key store.
        descriptor = self._open_session_directory()
        os.close(descriptor)
        selected_case = str(case_id or _REQUEST_CASE.get() or self._effective_access().case_id or user_id)
        resolved = self._check_access(user_id, ability="read", case_id=selected_case, record_case_id=selected_case)
        self._require_private_case_key_access(resolved, selected_case, principal_id=resolved)
        binding = PrivateArtifactBinding(tenant_id=resolved, case_id=selected_case, artifact_kind="session", revision="session-v1", principal_id=resolved)
        try:
            provider = self.private_key_provider()
            provider.resolve(binding)
        except PrivateKeyMaterialError:
            raise WorkspacePersistenceError("Private workspace keys require unlock.", code="unlock_needed", public_status="unlock_needed") from None
        access = self._effective_access()
        authority = self._owner_case_authority()
        if authority is not None:
            authority.revalidate(actor_principal_id=authority.actor_principal_id, workspace=self, require_owner=True)
            if resolved != authority.canonical_owner_principal_id or selected_case != authority.case_id:
                raise WorkspaceAuthorizationDenied()
            # This is the case-scoped AAD/storage subject, never the request
            # actor or its authorization. The live provider retains the real
            # issued request binding and re-proves it on every resolve.
            access = WorkspaceAccess.authenticated(resolved, selected_case)
        elif access.trust == "trusted_local" and not access.principal_id and not access.case_id:
            access = WorkspaceAccess.trusted_local(resolved, selected_case)
        return {"access": access, "tenant_id": resolved, "case_id": selected_case,
                "principal_id": resolved, "key_provider": provider, "revision": revision}

    def _private_session_filename(self, user_id: str) -> str:
        base = self._namespace_filename(user_id)
        try:
            self._read_bytes_nofollow(base + ".cgpe")
        except FileNotFoundError:
            return base
        except WorkspaceAuthorizationDenied:
            raise
        except OSError:
            raise WorkspacePersistenceError("Private session storage is unavailable.", code="read_error", public_status="unavailable") from None
        return base + ".cgpe"

    def _open_private_session_bytes(self, user_id: str, filename: str, raw: bytes) -> Dict[str, Any]:
        from integrations.private_storage import PrivateArtifactBinding, PrivateArtifactIntegrityError, PrivateCryptoCapabilityError, PrivateStorageError, open_private_artifact

        context = self._private_artifact_context(user_id)
        binding = PrivateArtifactBinding(tenant_id=context["tenant_id"], case_id=context["case_id"], artifact_kind="session", revision="session-v1", principal_id=context["principal_id"])
        try:
            key_id, key = context["key_provider"].resolve(binding)
            body = open_private_artifact(raw, binding=binding, key=key, expected_key_id=key_id)
            payload = json.loads(body.decode("utf-8"))
        except PrivateCryptoCapabilityError:
            raise WorkspacePersistenceError("Private encryption is unavailable.", code="private_crypto_unavailable", public_status="unavailable") from None
        except (PrivateStorageError, json.JSONDecodeError, UnicodeDecodeError):
            raise WorkspacePersistenceError("Private session authentication failed; existing bytes were preserved.", code="authentication_failed", public_status="recoverable") from None
        if not isinstance(payload, dict):
            raise WorkspacePersistenceError("Private session is corrupt; existing bytes were preserved.", code="corrupt_session", public_status="recoverable")
        self._prepare_loaded_state(payload, user_id)
        payload.update(status="available", session_readable=True, missing_new_session=False, existing_unreadable=False, at_rest_protection="private_envelope")
        return payload

    def _save_private_state(self, state: Dict[str, Any], filename: str, existing_raw: Optional[bytes]) -> Dict[str, Any]:
        from integrations.private_storage import PrivateArtifactBinding, PrivateCryptoCapabilityError, PrivateStorageError, seal_private_artifact, open_private_artifact

        user_id = str(state["user_id"])
        case_id = _state_case_id(state, user_id)
        context = self._private_artifact_context(user_id, case_id)
        if existing_raw is not None:
            if not existing_raw.startswith(b"CGPE"):
                try:
                    legacy = json.loads(existing_raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise WorkspacePersistenceError("Existing session is corrupt and was preserved.", code="corrupt_session", public_status="recoverable") from None
                if not isinstance(legacy, dict):
                    raise WorkspacePersistenceError("Existing session is corrupt and was preserved.", code="corrupt_session", public_status="recoverable")
                self._prepare_loaded_state(legacy, user_id)
                raise WorkspacePersistenceError("Legacy data requires explicit migration.", code="migration_required", public_status="recoverable")
            self._open_private_session_bytes(user_id, filename, existing_raw)
        binding = PrivateArtifactBinding(tenant_id=context["tenant_id"], case_id=case_id, artifact_kind="session", revision="session-v1", principal_id=context["principal_id"])
        state["at_rest_protection"] = "private_envelope"
        body = json.dumps(state, sort_keys=True).encode("utf-8")
        root_fd = self._open_session_directory()
        temporary = "." + uuid.uuid4().hex + ".tmp"
        lock_fd = -1
        try:
            lock_flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
            lock_fd = os.open(".session-write.lock", lock_flags, 0o600, dir_fd=root_fd)
            os.fchmod(lock_fd, 0o600)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            key_id, key = context["key_provider"].resolve(binding)
            envelope = seal_private_artifact(body, binding=binding, key=key, key_id=key_id)
            self._write_bytes_nofollow(temporary, envelope, root_fd=root_fd, durable=True)
            staged = self._read_bytes_nofollow(temporary)
            if staged != envelope or open_private_artifact(staged, binding=binding, key=key, expected_key_id=key_id) != body:
                raise WorkspacePersistenceError("Private session readback failed.", code="readback_mismatch", public_status="recoverable")
            try:
                current = self._read_bytes_nofollow(filename)
            except FileNotFoundError:
                current = None
            if current != existing_raw:
                raise WorkspacePersistenceError("The private session changed; retry from its current revision.", code="revision_conflict", public_status="recoverable")
            if context["key_provider"].resolve(binding) != (key_id, key):
                raise WorkspacePersistenceError("Private workspace keys require unlock.", code="unlock_needed", public_status="unlock_needed")
            os.replace(temporary, filename, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            os.fsync(root_fd)
        except PrivateCryptoCapabilityError:
            raise WorkspacePersistenceError("Private encryption is unavailable.", code="private_crypto_unavailable", public_status="unavailable") from None
        except PrivateStorageError:
            raise WorkspacePersistenceError("Private session authentication failed.", code="authentication_failed", public_status="recoverable") from None
        except WorkspaceAuthorizationDenied:
            raise
        except OSError:
            raise WorkspacePersistenceError("Private session storage is unavailable; existing bytes were preserved.", code="write_error", public_status="unavailable") from None
        finally:
            try:
                os.unlink(temporary, dir_fd=root_fd)
            except FileNotFoundError:
                pass
            except OSError:
                pass
            if lock_fd >= 0:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(root_fd)
        return state

    def joined_revision_repository(self, user_id: Optional[str] = None, case_id: Optional[str] = None) -> Path:
        root = self._session_dir / "joined-revisions"
        if user_id is None:
            return root
        # An existing singleton repository is never hidden or treated as a
        # fresh namespace. Authentication/recovery must admit it explicitly.
        if any((root / name).exists() for name in ("head.cgpe", "wal", "owner.cgpe", "o")):
            return root
        # Reuse the workspace's opaque namespace convention; no identifying
        # caller label is a repository pathname.
        identity = json.dumps([str(user_id), str(case_id or user_id)], separators=(",", ":"))
        return root / ("p-" + principal_namespace(identity))

    def _joined_key(self, user_id: str, case_id: Optional[str] = None):
        from integrations.private_storage import PrivateArtifactBinding
        context = self._private_artifact_context(user_id, case_id)
        binding = PrivateArtifactBinding(tenant_id=context["tenant_id"], case_id=context["case_id"],
            principal_id=context["principal_id"], artifact_kind="session", revision="session-v1")
        key_id, key = context["key_provider"].resolve(binding)
        return context, key_id, key

    def _joined_key_resolver(self, user_id: str, case_id: str):
        """Resolve a retained envelope key through current owner admission.

        This handle retains no key bytes or admission. Each lookup rechecks the
        current issued owner, case binding and unlocked durable key session.
        """
        def lookup(key_id):
            context, _active_id, _active_key = self._joined_key(user_id, case_id)
            return self._private_key_session().lookup_data_key(
                context["tenant_id"], context["case_id"], key_id)
        return lookup

    def _joined_publication_scope(self, user_id: str, case_id: str, key_id: str, key: bytes):
        from contextlib import contextmanager
        @contextmanager
        def hold_epoch():
            context, current_id, current_key = self._joined_key(user_id, case_id)
            if current_id != key_id or current_key != key:
                raise WorkspaceAuthorizationDenied()
            if not isinstance(context["key_provider"], _WorkspaceCaseKeyProvider):
                # Explicit legacy host providers own their raw-key contract;
                # they have no UserOwnedKeySession epoch to lock. An issued
                # GUI owner cannot select this compatibility path.
                if self._owner_case_authority() is not None:
                    raise WorkspaceAuthorizationDenied()
                yield
                return
            session = self._private_key_session()
            with session.case_key_epoch_scope(user_id, case_id):
                _context, current_id, current_key = self._joined_key(user_id, case_id)
                if current_id != key_id or current_key != key:
                    raise WorkspaceAuthorizationDenied()
                yield
        return hold_epoch

    def _joined_chat_identity(self, state: Mapping[str, Any], question_id: str, answer: str,
                              question_revision: Optional[int] = None) -> str:
        import hmac
        user = str(state["user_id"])
        context, _, key = self._joined_key(user, _state_case_id(state, user))
        body = json.dumps([context["tenant_id"], context["case_id"], question_id,
                           question_revision, answer], separators=(",", ":")).encode("utf-8")
        return hmac.new(key, b"joined-intake-effect@1\x00" + body, hashlib.sha256).hexdigest()

    def _commit_joined_snapshot(self, state: Dict[str, Any], *, effect_id: Optional[str] = None,
                                question_id: Optional[str] = None, answer: Optional[str] = None,
                                before_publish: Optional[Callable[[], Any]] = None) -> Dict[str, Any]:
        from integrations.private_storage import commit_private_revision
        user = str(state["user_id"])
        context, key_id, key = self._joined_key(user, _state_case_id(state, user))
        expected = str(state.get("private_revision") or "0")
        revision = str(int(expected) + 1)
        transaction = uuid.uuid4().hex
        effect = effect_id or uuid.uuid4().hex
        if effect_id:
            history = state.setdefault("intake_history", [])
            if any(item.get("effect_id") == effect_id for item in history if isinstance(item, dict)):
                return state
            found = next((item for item in reversed(history) if isinstance(item, dict)
                          and item.get("question_id") == question_id and item.get("answer") == answer
                          and not item.get("effect_id")), None)
            if found is None:
                found = {"question_id": question_id, "answer": answer}
                history.append(found)
            found.update(effect_id=effect, transaction_id=transaction)
            graph = state.setdefault("annotation_knowledge_graph", {"entities": [], "relationships": []})
            graph.setdefault("relationships", []).append({"id": effect, "kind": "intake-answer",
                "question_id": question_id, "revision": revision})
            state.setdefault("proof_history", []).append({"effect_id": effect, "transaction_id": transaction,
                "kind": "intake-revision", "revision": revision})
        state.update(private_revision=revision, missing_new_session=False, session_readable=True,
                     at_rest_protection="private_envelope")
        publication = commit_private_revision(self.joined_revision_repository(user, context["case_id"]),
            tenant_id=context["tenant_id"], case_id=context["case_id"], principal_id=context["principal_id"],
            key=key, key_id=key_id, expected_revision=expected,
            session=json.dumps(state, sort_keys=True).encode("utf-8"),
            fact_graph=json.dumps({"relationships": state.get("annotation_knowledge_graph", {}).get("relationships", []),
                                   "revision": revision}, sort_keys=True).encode("utf-8"),
            proof=json.dumps({"entries": state.get("proof_history", []), "revision": revision}, sort_keys=True).encode("utf-8"),
            transaction_id=transaction, effect_id=effect,
               key_resolver=self._joined_key_resolver(context["tenant_id"], context["case_id"]), publication_scope=self._joined_publication_scope(context["tenant_id"], context["case_id"], key_id, key), **({"before_publish": before_publish} if before_publish is not None else {}),
           )
        if not publication.committed:
            raise WorkspacePersistenceError("joined revision did not commit", code="durability_unproven", public_status="recoverable")
        return state

    def commit_joined_intake_revision(
        self,
        user_id: str,
        *,
        question_id: str,
        answer: str,
        transaction_id: str,
        effect_id: str,
        case_id: Optional[str] = None,
        expected_revision: Optional[str] = None,
        crash_injector: Any = None,
        writer: Any = None,
        fsync_file: Any = None,
        fsync_directory: Any = None,
    ) -> Dict[str, Any]:
        """Commit one intake answer with its fact-graph edge and proof entry.

        The three payloads are sealed before the Kit WAL intent is written.
        The intent carries opaque ciphertext refs and the stable ids only.
        """

        from integrations.private_storage import commit_private_revision

        resolved = self._check_access(user_id, ability="write", case_id=case_id)
        context = self._private_artifact_context(resolved, case_id)
        binding_case = context["case_id"]
        state = self._load_state(resolved, case_id=binding_case)
        if str(state.get("user_id") or "") != resolved:
            raise WorkspaceAuthorizationDenied()
        if _state_case_id(state, resolved) != binding_case and state.get("missing_new_session") is not True:
            if case_id is not None and _state_case_id(state, resolved) != binding_case:
                raise WorkspaceAuthorizationDenied()
        current = str(state.get("private_revision") or "0")
        expected = "0" if expected_revision in {None, ""} else str(expected_revision)
        if current != expected:
            raise WorkspacePersistenceError(
                "stale revision",
                code="revision_conflict",
                public_status="recoverable",
            )
        next_revision = str(int(expected) + 1)
        answers = dict(state.get("intake_answers") or {})
        history = [item for item in list(state.get("intake_history") or []) if isinstance(item, dict)]
        if any(str(item.get("effect_id") or "") == effect_id for item in history):
            raise WorkspacePersistenceError(
                "effect already recorded",
                code="duplicate_effect",
                public_status="recoverable",
            )
        answers[str(question_id)] = str(answer)
        history.append({
            "question_id": str(question_id),
            "answer": str(answer),
            "effect_id": effect_id,
            "transaction_id": transaction_id,
        })
        state["intake_answers"] = answers
        state["intake_history"] = history
        state["private_revision"] = next_revision
        graph = state.get("annotation_knowledge_graph")
        if not isinstance(graph, dict):
            graph = {"entities": [], "relationships": []}
        relationships = [item for item in list(graph.get("relationships") or []) if isinstance(item, dict)]
        relationships.append({
            "id": effect_id,
            "kind": "intake-answer",
            "question_id": str(question_id),
            "revision": next_revision,
        })
        graph["relationships"] = relationships
        state["annotation_knowledge_graph"] = graph
        proofs = [item for item in list(state.get("proof_history") or []) if isinstance(item, dict)]
        proofs.append({
            "effect_id": effect_id,
            "transaction_id": transaction_id,
            "kind": "intake-revision",
            "revision": next_revision,
        })
        state["proof_history"] = proofs
        fact_document = {"relationships": relationships, "effect_id": effect_id, "revision": next_revision}
        proof_document = {"entries": proofs, "effect_id": effect_id, "revision": next_revision}
        from integrations.private_storage import PrivateArtifactBinding as _Binding
        binding = _Binding(
            tenant_id=resolved,
            case_id=binding_case,
            artifact_kind="session",
            revision="session-v1",
            principal_id=resolved,
        )
        key_id, key = context["key_provider"].resolve(binding)
        publication = commit_private_revision(
            self.joined_revision_repository(resolved, binding_case),
            tenant_id=resolved,
            case_id=binding_case,
            principal_id=resolved,
            key=key,
            key_id=key_id,
            expected_revision=expected,
            session=json.dumps(state, sort_keys=True).encode("utf-8"),
            fact_graph=json.dumps(fact_document, sort_keys=True).encode("utf-8"),
            proof=json.dumps(proof_document, sort_keys=True).encode("utf-8"),
            transaction_id=transaction_id,
            effect_id=effect_id,
            crash_injector=crash_injector,
            writer=writer,
            fsync_file=fsync_file,
            fsync_directory=fsync_directory,
            key_resolver=self._joined_key_resolver(resolved, binding_case),
        publication_scope=self._joined_publication_scope(resolved, binding_case, key_id, key))
        receipt = publication.as_dict()
        receipt["network_pinned"] = False
        receipt["question_id"] = str(question_id)
        return receipt

    def commit_factual_graph_revision(
        self,
        user_id: str,
        graph: Any,
        *,
        case_id: str,
        transaction_id: str,
        effect_id: str,
        expected_revision: Optional[str] = None,
        backend: Any = None,
    ) -> Dict[str, Any]:
        """Commit factual revision provenance inside the encrypted case transaction.

        The graph bytes are sealed by the automatic private-artifact owner.
        The transaction records that ciphertext id with the canonical document.
        A failed seal or commit does not replace the last committed head, and
        nothing is written as plaintext JSON, a plaintext CID, or a second graph store.
        """
        from integrations.ipfs_datasets.graphs import (
            FACTUAL_GRAPH_ARTIFACT_KIND,
            encode_factual_graph_artifact,
            seal_factual_graph_artifact,
        )
        from integrations.private_storage import PrivateRevisionError, PrivateStorageError, commit_private_revision

        resolved = self._check_access(user_id, ability="write", case_id=case_id)
        context = self._private_artifact_context(resolved, case_id)
        binding_case = str(context["case_id"])
        state = self._load_state(resolved, case_id=binding_case)
        if str(state.get("user_id") or "") != resolved:
            raise WorkspaceAuthorizationDenied()
        current = str(state.get("private_revision") or "0")
        expected = current if expected_revision in {None, ""} else str(expected_revision)
        if current != expected:
            raise WorkspacePersistenceError(
                "stale revision",
                code="revision_conflict",
                public_status="recoverable",
            )
        history = [item for item in list(state.get("intake_history") or []) if isinstance(item, dict)]
        if any(str(item.get("effect_id") or "") == effect_id for item in history):
            raise WorkspacePersistenceError(
                "effect already recorded",
                code="duplicate_effect",
                public_status="recoverable",
            )
        next_revision = str(int(expected) + 1)
        artifact_revision = f"fact-graph-{next_revision}"
        transport = backend if backend is not None else self._private_local_backend()
        backend_name = "local_cache" if backend is None else "kit"
        try:
            sealed = seal_factual_graph_artifact(
                graph,
                access=context["access"],
                tenant_id=str(context["tenant_id"]),
                case_id=binding_case,
                principal_id=str(context["principal_id"]),
                revision=artifact_revision,
                backend=transport,
                backend_name=backend_name,
                key_provider=context["key_provider"],
                pin_content=backend is not None,
            )
        except (PrivateStorageError, ValueError, TypeError) as exc:
            raise WorkspacePersistenceError(
                "Factual graph storage is unavailable.",
                code=str(getattr(exc, "code", "") or "artifact_unavailable"),
                public_status="unavailable",
            ) from None
        document = sealed["document"]
        if encode_factual_graph_artifact(document) != sealed["payload"]:
            raise WorkspacePersistenceError(
                "Factual graph artifact did not round-trip before commit.",
                code="readback_mismatch",
                public_status="recoverable",
            )
        annotation = state.get("annotation_knowledge_graph")
        if not isinstance(annotation, dict):
            annotation = {"entities": [], "relationships": []}
        relationships = [item for item in list(annotation.get("relationships") or []) if isinstance(item, dict)]
        annotation["relationships"] = relationships
        state["annotation_knowledge_graph"] = annotation
        proofs = [item for item in list(state.get("proof_history") or []) if isinstance(item, dict)]
        proofs.append({
            "effect_id": effect_id,
            "transaction_id": transaction_id,
            "kind": "factual-graph-revision",
            "revision": next_revision,
            "ciphertext_storage_id": sealed["ciphertext_storage_id"],
        })
        history.append({
            "question_id": "factual-graph",
            "answer": "",
            "effect_id": effect_id,
            "transaction_id": transaction_id,
            "kind": "factual-graph-revision",
        })
        state["intake_history"] = history
        state["proof_history"] = proofs
        state["private_revision"] = next_revision
        state["factual_graph_binding"] = {
            "artifact_kind": FACTUAL_GRAPH_ARTIFACT_KIND,
            "artifact_revision": artifact_revision,
            "ciphertext_storage_id": sealed["ciphertext_storage_id"],
            "case_id": binding_case,
            "owner": resolved,
        }
        state.update(missing_new_session=False, session_readable=True, at_rest_protection="private_envelope")
        fact_document = {
            "relationships": relationships,
            "effect_id": effect_id,
            "revision": next_revision,
            "artifact_kind": FACTUAL_GRAPH_ARTIFACT_KIND,
            "artifact_revision": artifact_revision,
            "ciphertext_storage_id": sealed["ciphertext_storage_id"],
            "factual_artifact": document,
        }
        proof_document = {"entries": proofs, "effect_id": effect_id, "revision": next_revision}
        _joined_context, key_id, key = self._joined_key(resolved, binding_case)
        try:
            publication = commit_private_revision(
                self.joined_revision_repository(resolved, binding_case),
                tenant_id=resolved,
                case_id=binding_case,
                principal_id=resolved,
                key=key,
                key_id=key_id,
                expected_revision=expected,
                session=json.dumps(state, sort_keys=True).encode("utf-8"),
                fact_graph=json.dumps(fact_document, sort_keys=True).encode("utf-8"),
                proof=json.dumps(proof_document, sort_keys=True).encode("utf-8"),
                transaction_id=transaction_id,
                effect_id=effect_id,
                key_resolver=self._joined_key_resolver(resolved, binding_case),
            publication_scope=self._joined_publication_scope(resolved, binding_case, key_id, key))
        except PrivateRevisionError as exc:
            raise WorkspacePersistenceError(
                "Factual graph revision did not commit.",
                code=str(exc.code or "transaction_failed"),
                public_status="recoverable",
            ) from None
        except PrivateStorageError as exc:
            raise WorkspacePersistenceError(
                "Factual graph revision did not commit.",
                code=str(exc.code or "artifact_unavailable"),
                public_status="recoverable",
            ) from None
        if not publication.committed:
            raise WorkspacePersistenceError(
                "Factual graph revision did not commit.",
                code="durability_unproven",
                public_status="recoverable",
            )
        receipt = publication.as_dict()
        receipt.update({
            "network_pinned": False,
            "private_artifact": True,
            "plaintext_fallback": False,
            "plaintext_catalog": False,
            "ciphertext_storage_id": sealed["ciphertext_storage_id"],
            "artifact_kind": FACTUAL_GRAPH_ARTIFACT_KIND,
            "artifact_revision": artifact_revision,
            "case_id": binding_case,
            "owner": resolved,
            "graph_registry_used": False,
        })
        return receipt

    def reload_factual_graph_revision(
        self,
        user_id: str,
        *,
        case_id: str,
        backend: Any = None,
    ) -> Dict[str, Any]:
        """Reload the committed factual graph for the same owner and case.

        The ciphertext artifact is required. A plaintext JSON, cache, or CID
        document is not accepted in its place. Authentication and corruption
        failures leave the committed head untouched.
        """
        from integrations.ipfs_datasets.graphs import (
            FACTUAL_GRAPH_ARTIFACT_KIND,
            encode_factual_graph_artifact,
            open_factual_graph_artifact,
        )
        from integrations.private_storage import (
            PrivateArtifactIntegrityError,
            PrivateRevisionError,
            PrivateStorageError,
            read_private_revision,
        )

        resolved = self._check_access(user_id, ability="read", case_id=case_id)
        context = self._private_artifact_context(resolved, case_id)
        binding_case = str(context["case_id"])
        _context, key_id, key = self._joined_key(resolved, binding_case)
        transport = backend if backend is not None else self._private_local_backend()
        backend_name = "local_cache" if backend is None else "kit"
        try:
            opened = read_private_revision(
                self.joined_revision_repository(resolved, binding_case),
                tenant_id=resolved,
                case_id=binding_case,
                principal_id=resolved,
                key=key,
                key_id=key_id,
                key_resolver=self._joined_key_resolver(resolved, binding_case),
            )
            if not isinstance(opened, dict):
                raise PrivateRevisionError("factual graph revision is missing", code="authentication_failed")
            fact = json.loads(opened["fact_graph"])
            if not isinstance(fact, dict):
                raise PrivateArtifactIntegrityError("malformed")
            storage_id = str(fact.get("ciphertext_storage_id") or "")
            artifact_revision = str(fact.get("artifact_revision") or "")
            embedded = fact.get("factual_artifact")
            if fact.get("artifact_kind") != FACTUAL_GRAPH_ARTIFACT_KIND or not isinstance(embedded, dict):
                raise PrivateArtifactIntegrityError("malformed")
            loaded = open_factual_graph_artifact(
                storage_id,
                access=context["access"],
                tenant_id=str(context["tenant_id"]),
                case_id=binding_case,
                principal_id=str(context["principal_id"]),
                revision=artifact_revision,
                backend=transport,
                backend_name=backend_name,
                key_provider=context["key_provider"],
            )
            if encode_factual_graph_artifact(loaded) != encode_factual_graph_artifact(embedded):
                raise PrivateStorageError("factual graph ciphertext mismatch", code="readback_mismatch")
        except (PrivateStorageError, PrivateRevisionError, PrivateArtifactIntegrityError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            raise WorkspacePersistenceError(
                "Factual graph did not authenticate; the last committed graph was preserved.",
                code="authentication_failed",
                public_status="recoverable",
            ) from None
        return {
            "status": "available",
            "owner": resolved,
            "case_id": binding_case,
            "tenant_id": str(context["tenant_id"]),
            "revision": str(opened["revision"]),
            "ciphertext_storage_id": storage_id,
            "artifact_kind": FACTUAL_GRAPH_ARTIFACT_KIND,
            "artifact_revision": artifact_revision,
            "artifact": loaded,
            "assertion_states": loaded.get("assertion_states") or {},
            "relationships": loaded.get("relationships") or {},
            "invalidations": list(loaded.get("invalidations") or []),
            "unresolved_conflicts": list(loaded.get("unresolved_conflicts") or []),
            "revisions": list(loaded.get("revisions") or []),
            "plaintext_fallback": False,
            "private_artifact": True,
        }

    def current_factual_graph_projection(
        self,
        user_id: Optional[str] = None,
        *,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Project the current encrypted session graph. This read does not write it."""
        from complaint_phases.knowledge_graph import project_current_factual_graph
        from mediator.integrations.graph_tools import FactualGraphProjectionError

        resolved = self._resolve_user_id(user_id)
        session = self.get_session(resolved, case_id=case_id)
        state = session.get("session") if isinstance(session, dict) else None
        if not isinstance(state, dict):
            raise WorkspacePersistenceError(
                "Factual graph is not available.",
                code="knowledge_graph_unavailable",
                public_status="recoverable",
            )
        binding_case = str(case_id or state.get("case_id") or "")
        if case_id and str(state.get("case_id") or "") != str(case_id):
            raise WorkspacePersistenceError(
                "Factual graph is bound to another case.",
                code="cross_case_id",
                public_status="recoverable",
            )
        interview = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
        raw = interview.get("knowledge_graph")
        if not isinstance(raw, dict) or not raw:
            raise WorkspacePersistenceError(
                "Factual graph is not available.",
                code="knowledge_graph_unavailable",
                public_status="recoverable",
            )
        try:
            projected = project_current_factual_graph(raw, case_id=binding_case)
        except FactualGraphProjectionError as exc:
            code = exc.code if exc.code in {
                "cross_case_id", "knowledge_graph_unavailable", "data_graph_owner_unavailable", "factual_ledger_invalid",
            } else "knowledge_graph_unavailable"
            raise WorkspacePersistenceError(
                "Factual graph projection was refused.",
                code=code,
                public_status="recoverable",
            ) from None
        projected["owner"] = resolved
        projected["session_case_id"] = str(state.get("case_id") or "")
        projected["private_revision"] = state.get("private_revision")
        projected["read_only"] = True
        return projected

    def recover_joined_intake_revision(self, user_id: str, *, case_id: Optional[str] = None) -> Dict[str, Any]:
        from integrations.private_storage import PrivateArtifactBinding, recover_private_revision

        resolved = self._check_access(user_id, ability="write", case_id=case_id)
        context = self._private_artifact_context(resolved, case_id)
        binding = PrivateArtifactBinding(
            tenant_id=resolved,
            case_id=context["case_id"],
            artifact_kind="session",
            revision="session-v1",
            principal_id=resolved,
        )
        key_id, key = context["key_provider"].resolve(binding)
        publication = recover_private_revision(
            self.joined_revision_repository(resolved, context["case_id"]),
            tenant_id=resolved,
            case_id=context["case_id"],
            principal_id=resolved,
            key=key,
            key_id=key_id,
            key_resolver=self._joined_key_resolver(resolved, context["case_id"]),
        )
        return publication.as_dict()

    def _private_local_backend(self):
        from integrations.ipfs_datasets.storage import LocalCacheIPFSBackend
        workspace = self
        class OwnedCiphertextBackend(LocalCacheIPFSBackend):
            measurement_label = "measured-local"
            def __init__(self):
                # All operations below use the admitted workspace descriptor.
                # Do not initialize the global/home fallback cache.
                pass
            def add_bytes(self, data, pin=True):
                blob = bytes(data)
                cid = "bafy" + hashlib.sha256(blob).hexdigest()[:55]
                workspace._write_bytes_nofollow("private-artifacts/" + cid, blob, create_parents=True)
                return {"success": True, "cid": cid, "pinned": False}
            def cat(self, cid):
                if not re.fullmatch(r"bafy[0-9a-f]{55}", str(cid)):
                    raise WorkspaceAuthorizationDenied()
                return workspace._read_bytes_nofollow("private-artifacts/" + str(cid))
            def pin(self, cid):
                return {"success": True, "cid": cid, "pinned": False}
        return OwnedCiphertextBackend()

    def ingest_memory_evidence(self, user_id: Optional[str], *, files: List[Dict[str, Any]], claim_element_id: str = "causation", kind: str = "document", backend: Any = None) -> Dict[str, Any]:
        """Keep attachment processing in memory and store only authenticated envelopes."""
        from integrations.ipfs_datasets.storage import store_automatic_private_artifact
        from integrations.private_storage import PrivateStorageError
        state = self._load_state(self._resolve_user_id(user_id))
        owner = str(state["user_id"])
        context = self._private_artifact_context(owner, _state_case_id(state, owner))
        transport = backend if backend is not None else self._private_local_backend()
        imported = []
        for index, item in enumerate(files, start=1):
            data = bytes(item.get("data") or b"")
            filename = str(item.get("filename") or f"upload-{index}")
            try:
                text = data.decode("utf-8")
                extraction = {"status": "available", "method": "ephemeral-memory"}
            except UnicodeDecodeError:
                text = None
                extraction = {"status": "limited", "code": "in_memory_extraction_unavailable", "method": "ephemeral-memory", "preserved_original": True}
            base = {**context, "backend": transport, "backend_name": "local_cache" if backend is None else "kit", "pin_content": backend is not None}
            try:
                attachment = store_automatic_private_artifact(data, artifact_kind="attachment", **{**base, "revision": f"attachment-{index}"})
                extracted = store_automatic_private_artifact(text.encode("utf-8"), artifact_kind="extracted-text", **{**base, "revision": f"extracted-text-{index}"}) if text is not None else None
            except PrivateStorageError:
                raise WorkspacePersistenceError("Private evidence storage is unavailable.", code="artifact_unavailable", public_status="unavailable") from None
            imported.append({"filename": filename, "extraction": extraction, "attachment_cid": attachment.get("cid"), "extracted_cid": (extracted or {}).get("cid"), "effective_claim_element_id": claim_element_id, "plaintext_disk": False})
            documents = state.setdefault("evidence", {"testimony": [], "documents": []}).setdefault("documents", [])
            documents.append({"id": f"documents-{len(documents)+1}", "kind": kind, "claim_element_id": claim_element_id, "title": filename, "content_cid": (extracted or {}).get("cid"), "attachment_cid": attachment.get("cid"), "extraction": extraction, "saved_at": _utc_now()})
        self._save_state(state)
        return {"status": "available", "imported": imported, "extraction_boundary": "ephemeral-memory", "plaintext_disk": False, "session": state}

    def persist_private_case_materials(self, user_id: str, materials: Dict[str, bytes], *, case_id: Optional[str] = None, backend: Any = None) -> Dict[str, Any]:
        from integrations.ipfs_datasets.storage import store_automatic_private_artifact
        from integrations.private_storage import PrivateStorageError
        context = self._private_artifact_context(user_id, case_id)
        transport = backend if backend is not None else self._private_local_backend()
        artifacts = {}
        try:
            for kind, payload in materials.items():
                artifacts[kind] = store_automatic_private_artifact(bytes(payload), artifact_kind=str(kind), **{**context, "revision": f"{kind}-1", "backend": transport, "backend_name": "local_cache" if backend is None else "kit", "pin_content": backend is not None})
        except (PrivateStorageError, ValueError):
            raise WorkspacePersistenceError("Private artifact storage is unavailable.", code="artifact_unavailable", public_status="unavailable") from None
        return {"status": "available", "written": True, "artifacts": artifacts, "plaintext_disk": False}

    def interview_snapshot_directory(self, user_id: str, case_id: Optional[str] = None) -> Path:
        resolved = self._check_access(user_id, ability="write")
        directory = self._session_dir / "interview-snapshots" / self._namespace_filename(resolved)
        # Preserve the existing default-case location; other cases have their
        # own head and revision clock beneath the private user namespace.
        case = str(case_id or resolved)
        if case != resolved:
            directory = directory / ("case-" + self._namespace_filename(case))
        return directory

    def _interview_snapshot_key(self, user_id: str, case_id: Optional[str] = None) -> Dict[str, Any]:
        from integrations.private_storage import PrivateArtifactBinding, PrivateKeyLockedError, PrivateKeyMaterialError
        try:
            context = self._private_artifact_context(user_id, case_id)
            binding_key = context["key_provider"].resolve(PrivateArtifactBinding(
                tenant_id=context["tenant_id"],
                case_id=context["case_id"],
                artifact_kind="interview-snapshot",
                revision="snapshot-rev-0",
                principal_id=context["principal_id"],
            ))
        except (PrivateKeyLockedError, PrivateKeyMaterialError):
            raise WorkspacePersistenceError(
                "Private interview keys require unlock.",
                code="unlock_needed",
                public_status="unlock_needed",
            ) from None
        context["key_id"], context["key"] = binding_key
        return context

    def persist_complete_interview_snapshot(
        self,
        user_id: str,
        snapshot: Mapping[str, Any],
        *,
        protection: str = "user_chosen_encrypted",
        case_id: Optional[str] = None,
        expected_revision: Optional[str] = None,
        migrate_plaintext: bool = False,
        fail_before_head: bool = False,
        before_head: Any = None,
    ) -> Dict[str, Any]:
        """Persist one complete interview snapshot inside the private session tree."""
        from integrations.ipfs_datasets.storage import InterviewSnapshotError, persist_interview_snapshot

        if protection == "user_chosen_encrypted":
            context = self._interview_snapshot_key(user_id, case_id)
        else:
            context = {"tenant_id": user_id, "case_id": str(case_id or user_id), "principal_id": user_id, "key": None, "key_id": None}
        directory = self.interview_snapshot_directory(str(context["tenant_id"]), str(context["case_id"]))
        try:
            result = persist_interview_snapshot(
                directory,
                snapshot,
                protection=protection,
                tenant_id=str(context["tenant_id"]),
                case_id=str(context["case_id"]),
                principal_id=str(context["principal_id"]),
                key=context.get("key"),
                key_id=context.get("key_id"),
                expected_revision=expected_revision,
                migrate_plaintext=migrate_plaintext,
                fail_before_head=fail_before_head,
                before_head=before_head,
            )
        except InterviewSnapshotError as exc:
            raise WorkspacePersistenceError(str(exc), code=exc.code, public_status=exc.public_status) from None
        receipt = dict(result["receipt"])
        receipt["plaintext_disk"] = protection != "user_chosen_encrypted"
        return {
            "snapshot": result["snapshot"],
            "receipt": receipt,
            "cold_read": {"narrative_reextracted": False, "hooks_replayed": False, "model_calls": 0, "bindings_from": "committed_snapshot"},
            "kit_durability": result.get("kit_durability") or {"status": "unavailable", "durable": False, "counts_as_replica": False, "network_durable": False},
        }

    def commit_complete_grounded_snapshot(
        self,
        user_id: str,
        *,
        case_id: Optional[str] = None,
        expected_revision: Optional[str] = None,
        fail_before_head: bool = False,
        before_head: Any = None,
        owners: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Seal the current grounded owners in one snapshot transaction.

        The commit reads state that is already stored. It does not extract a
        narrative, replay hook receipts, or call a model.
        """

        from integrations.ipfs_datasets.storage import assemble_interview_snapshot

        state = self._load_state(user_id, case_id=case_id)
        collected = _grounded_owners_from_state(state)
        if isinstance(owners, Mapping):
            for key, value in owners.items():
                if value is not None:
                    collected[key] = value
        interview = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
        pending = collected.get("pending_inquiry") if isinstance(collected.get("pending_inquiry"), dict) else {"status": "unknown"}
        stop = collected.get("stop_policy") if isinstance(collected.get("stop_policy"), dict) else {}
        if isinstance(stop.get("reason"), str) and stop.get("reason"):
            outcome = str(stop["reason"])
        elif pending.get("inquiry_id"):
            outcome = "awaiting_user"
        else:
            outcome = "unknown"
        factual = collected.get("factual_graph") if isinstance(collected.get("factual_graph"), dict) else {}
        narrative = _narrative_record(state)
        snapshot = assemble_interview_snapshot(
            session_id=str(interview.get("session_id") or state.get("user_id") or user_id),
            revision="0",
            outcome_reason=outcome,
            pending_inquiry=pending,
            knowledge_graph=interview.get("knowledge_graph") if isinstance(interview.get("knowledge_graph"), dict) else {"status": "unknown"},
            dependency_graph=interview.get("dependency_graph") if isinstance(interview.get("dependency_graph"), dict) else {"status": "unknown"},
            provenance={"source": "committed-state", "narrative_reextracted": False, "hooks_replayed": False, "model_calls": 0},
            unknown_items=list(interview.get("unknown_reasons") or []),
            deferred_items=list(interview.get("capped_reasons") or []),
            complaint_text=str(narrative.get("text") or ""),
            transcript=[],
            exports={"status": "not_filed"},
            durability_payload={"writer": "grounded-snapshot", "remote_replicas_claimed": False},
            revisions={
                "session_revision": interview.get("session_revision", "unknown"),
                "question_revision": pending.get("revision", "unknown"),
                "graph_revision": factual.get("revision", "unknown"),
            },
            grounding=collected,
        )
        saved = self.persist_complete_interview_snapshot(
            user_id,
            snapshot,
            case_id=case_id,
            expected_revision=expected_revision,
            fail_before_head=fail_before_head,
            before_head=before_head,
        )
        saved["provider_replayed"] = False
        saved["hooks_replayed"] = False
        kit = saved.get("kit_durability") if isinstance(saved.get("kit_durability"), dict) else {}
        saved["kit_durability_counts_as_replica"] = False
        saved["network_durable"] = False
        if kit.get("counts_as_replica") is True or kit.get("network_durable") is True:
            raise WorkspacePersistenceError(
                "A local durability receipt cannot claim replica durability.",
                code="durability_unproven",
                public_status="recoverable",
            )
        return saved

    def case_manifest_repository(self, user_id: str, case_id: Optional[str] = None) -> Path:
        """Private CAS root for complete encrypted case revisions."""

        return self.joined_revision_repository(user_id, case_id)

    def _case_manifest_identity(self, user_id: str, case_id: Optional[str] = None) -> Dict[str, Any]:
        context, key_id, key = self._joined_key(user_id, case_id)
        return {
            "tenant_id": str(context["tenant_id"]),
            "case_id": str(context["case_id"]),
            "principal_id": str(context["principal_id"]),
            "key": key,
            "key_id": key_id,
        }

    def _complete_case_artifacts(self, snapshot: Mapping[str, Any]) -> Dict[str, Any]:
        from integrations.private_storage import _COMPLETE_CASE_ROLES

        if not isinstance(snapshot, Mapping):
            raise WorkspacePersistenceError(
                "A complete case snapshot is required.",
                code="role_missing",
                public_status="recoverable",
            )
        artifacts: Dict[str, Any] = {}
        for public_name, _kind in _COMPLETE_CASE_ROLES:
            value = snapshot.get(public_name)
            if isinstance(value, (bytes, bytearray)):
                body = bytes(value)
                revision = public_name
            elif isinstance(value, Mapping) and isinstance(value.get("body"), (bytes, bytearray)):
                body = bytes(value["body"])
                revision = str(value.get("revision") or public_name)
            elif isinstance(value, Mapping) and value:
                body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
                revision = str(value.get("revision") or public_name)
            else:
                raise WorkspacePersistenceError(
                    "A complete case snapshot is missing a required owner.",
                    code="role_missing",
                    public_status="recoverable",
                )
            if not body or body in {b"{}", b"[]", b"null"}:
                raise WorkspacePersistenceError(
                    "A complete case snapshot is missing a required owner.",
                    code="role_missing",
                    public_status="recoverable",
                )
            artifacts[public_name] = {"body": body, "revision": revision}
        return artifacts

    def commit_complete_encrypted_case_revision(
        self,
        user_id: str,
        snapshot: Mapping[str, Any],
        *,
        case_id: Optional[str] = None,
        expected_head: Optional[str] = None,
        expected_hash: Optional[str] = None,
        fail_before_head: bool = False,
        private_names: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Publish one complete encrypted case revision through the existing CAS.

        Missing owners, a crashed head update, and a conflicting writer leave
        the acknowledged head unchanged. This method does not mint an empty case.
        """

        from integrations.private_storage import (
            CaseManifestConflict,
            PrivateRevisionError,
            publish_case_manifest,
        )

        artifacts = self._complete_case_artifacts(snapshot)
        try:
            self.ensure_private_case_key(user_id, str(case_id or user_id))
            identity = self._case_manifest_identity(user_id, case_id)
        except WorkspacePersistenceError:
            raise
        except Exception as exc:
            raise WorkspacePersistenceError(
                "Private workspace keys require unlock.",
                code="unlock_needed",
                public_status="unlock_needed",
            ) from exc
        repository = self.case_manifest_repository(identity["tenant_id"], identity["case_id"])
        try:
            publication = publish_case_manifest(
                repository,
                tenant_id=identity["tenant_id"],
                case_id=identity["case_id"],
                principal_id=identity["principal_id"],
                key=identity["key"],
                key_id=identity["key_id"],
                expected_head=expected_head,
                expected_hash=expected_hash,
                artifacts=artifacts,
                private_names=dict(private_names or {}),
                complete=True,
                fail_before_head=fail_before_head,
            )
        except CaseManifestConflict as exc:
            raise WorkspacePersistenceError(
                "case manifest head conflict",
                code="manifest_conflict",
                public_status="recoverable",
            ) from exc
        except PrivateRevisionError as exc:
            raise WorkspacePersistenceError(str(exc), code=exc.code, public_status=exc.state) from exc
        receipt = publication.as_dict()
        receipt["empty_replacement"] = False
        receipt["complete"] = True
        return receipt

    def read_complete_encrypted_case_revision(
        self,
        user_id: str,
        *,
        case_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        from integrations.private_storage import PrivateRevisionError, read_case_manifest

        identity = self._case_manifest_identity(user_id, case_id)
        repository = self.case_manifest_repository(identity["tenant_id"], identity["case_id"])
        try:
            opened = read_case_manifest(repository, **identity)
        except PrivateRevisionError as exc:
            raise WorkspacePersistenceError(str(exc), code=exc.code, public_status=exc.state) from exc
        if opened is None:
            return None
        if opened.get("complete") is not True:
            raise WorkspacePersistenceError(
                "case manifest blob is missing or stale",
                code="stale_head",
                public_status="recoverable",
            )
        return opened

    def replay_acknowledged_encrypted_case_revision(
        self,
        user_id: str,
        *,
        generation: str,
        manifest_hash: str,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        from integrations.private_storage import PrivateRevisionError, replay_acknowledged_case_revision

        identity = self._case_manifest_identity(user_id, case_id)
        repository = self.case_manifest_repository(identity["tenant_id"], identity["case_id"])
        try:
            publication = replay_acknowledged_case_revision(
                repository,
                generation=generation,
                manifest_hash=manifest_hash,
                **identity,
            )
        except PrivateRevisionError as exc:
            raise WorkspacePersistenceError(str(exc), code=exc.code, public_status=exc.state) from exc
        receipt = publication.as_dict()
        receipt["empty_replacement"] = False
        return receipt

    def _replica_identity(self, user_id: str, case_id: Optional[str]) -> Dict[str, Any]:
        context = self._interview_snapshot_key(user_id, case_id)
        return {
            "tenant_id": str(context["tenant_id"]),
            "case_id": str(context["case_id"]),
            "principal_id": str(context["principal_id"]),
            "key": context["key"],
            "key_id": context["key_id"],
        }

    def publish_encrypted_replicas(
        self,
        user_id: str,
        repository: Path,
        *,
        case_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Publish sealed workspace replicas with the unlocked case key.

        Callers cannot substitute another key. Fixture providers stay explicit
        arguments and are not contacted unless the policy asks for them.
        """

        from integrations.ipfs_datasets.storage import publish_encrypted_replicas

        identity = self._replica_identity(user_id, case_id)
        kwargs.pop("key", None)
        kwargs.pop("key_id", None)
        kwargs.pop("tenant_id", None)
        kwargs.pop("principal_id", None)
        return publish_encrypted_replicas(repository, **identity, **kwargs)

    def reconcile_encrypted_replicas(self, repository: Path, receipt: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
        from integrations.ipfs_datasets.storage import reconcile_encrypted_replicas

        return reconcile_encrypted_replicas(repository, receipt, **kwargs)

    def restore_encrypted_replicas(self, user_id: str, repository: Path, receipt: Mapping[str, Any], *, case_id: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        from integrations.ipfs_datasets.storage import restore_encrypted_replicas

        identity = self._replica_identity(user_id, case_id)
        kwargs.pop("key", None)
        kwargs.pop("key_id", None)
        kwargs.pop("tenant_id", None)
        kwargs.pop("principal_id", None)
        return restore_encrypted_replicas(repository, receipt, **identity, **kwargs)

    def restore_encrypted_workspace(self, user_id: str, repository: Path, *, case_id: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        from integrations.ipfs_datasets.storage import restore_encrypted_workspace

        identity = self._replica_identity(user_id, case_id)
        kwargs.pop("key", None)
        kwargs.pop("key_id", None)
        kwargs.pop("tenant_id", None)
        kwargs.pop("principal_id", None)
        return restore_encrypted_workspace(repository, **identity, **kwargs)

    def count_verified_ciphertext_replicas(self, observations: Sequence[Mapping[str, Any]], **kwargs: Any) -> Dict[str, Any]:
        from integrations.ipfs_datasets.storage import count_verified_ciphertext_replicas, label_ciphertext_replica_observations

        if kwargs:
            return label_ciphertext_replica_observations(observations, **kwargs)
        return count_verified_ciphertext_replicas(observations)

    def resume_encrypted_interview(self, user_id: Optional[str], *, browser_cache: Any = None) -> Dict[str, Any]:
        """Restore one interview from the encrypted revision without replaying it.

        A new process supplies the same unlocked case key. Pending inquiry, case
        identity, consent, graph revisions, deferred gaps, and corrections come
        from that revision. Browser caches and caller messages are ignored.
        Denied, revoked, and missing-key results name the failure and omit case
        plaintext. This read does not call mediator hooks or append history.
        """

        def denial(status: str, code: str) -> Dict[str, Any]:
            return {
                "schema": "encrypted-interview-resume-v1",
                "status": status,
                "code": code,
                "resumed": False,
                "hooks_replayed": False,
                "messages_replayed": False,
                "reconstructed_from_browser_cache": False,
                "browser_cache_ignored": True,
                "pending_inquiry": None,
                "case": None,
                "consent": None,
                "factual_graph_revision": None,
                "legal_graph_revision": None,
                "deferred_gaps": [],
                "corrections": [],
                "legal_sufficiency": False,
                "plaintext_case_state": None,
                "encrypted_resume": {
                    "status": status,
                    "code": code,
                    "resumed": False,
                    "hooks_replayed": False,
                    "messages_replayed": False,
                    "reconstructed_from_browser_cache": False,
                },
            }

        del browser_cache
        try:
            resolved = self._check_access(user_id, ability="read")
        except WorkspaceAuthorizationDenied:
            return denial("denied", "authorization_denied")
        try:
            keys = self._private_key_session()
        except WorkspaceAuthorizationDenied:
            return denial("denied", "authorization_denied")
        if not keys.unlocked:
            return denial("missing_key", "missing_key")
        try:
            state = self._load_state(resolved)
        except WorkspaceAuthorizationDenied:
            return denial("denied", "authorization_denied")
        except WorkspacePersistenceError as exc:
            code = str(exc.code or "")
            if code in {"unlock_needed", "key_unavailable"}:
                return denial("missing_key", "missing_key")
            if code in {"authentication_failed", "corrupt_session"}:
                return denial("missing_key", code)
            return denial("missing_key", code or "missing_key")
        case_id = _state_case_id(state, resolved)
        source_identity = self._case_legal_context_identity(state)
        try:
            _, source_key_id, source_key = self._joined_key(resolved, case_id)
        except WorkspaceAuthorizationDenied:
            return denial("denied", "authorization_denied")
        except WorkspacePersistenceError as exc:
            return denial("missing_key", str(exc.code or "missing_key"))
        grant = state.get("case_key_grant") if isinstance(state.get("case_key_grant"), dict) else {}
        consent = state.get("operation_consent") if isinstance(state.get("operation_consent"), dict) else {}
        if grant.get("revoked") is True or str(grant.get("status") or "") == "revoked":
            return denial("revoked", "key_revoked")
        if consent.get("revoked") is True:
            return denial("revoked", "consent_revoked")
        projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
        pending = projection.get("pending_inquiry") if isinstance(projection.get("pending_inquiry"), dict) else None
        gaps = [deepcopy(item) for item in (projection.get("preserved_gaps") or []) if isinstance(item, dict)]
        deferred = [item for item in gaps if str(item.get("disposition") or "") == "deferred"]
        history = [item for item in (state.get("intake_history") or []) if isinstance(item, dict)]
        corrections: List[Dict[str, Any]] = []
        for item in history:
            if str(item.get("disposition") or "") in {"corrected", "correction"}:
                corrections.append({"source": "intake_history", "record": deepcopy(item)})
        graph_payload = projection.get("knowledge_graph") if isinstance(projection.get("knowledge_graph"), dict) else {}
        legal_payload = projection.get("dependency_graph") if isinstance(projection.get("dependency_graph"), dict) else {}
        factual_revision = None
        if graph_payload:
            try:
                from complaint_phases.knowledge_graph import KnowledgeGraph
                from mediator.hook_runtime import graph_revision_token
                factual_revision = graph_revision_token(KnowledgeGraph.from_dict(graph_payload))
            except Exception:
                factual_revision = None
            metadata = graph_payload.get("metadata") if isinstance(graph_payload.get("metadata"), dict) else {}
            ledger = metadata.get("factual_ledger") if isinstance(metadata.get("factual_ledger"), dict) else {}
            revision_rows = list(graph_payload.get("revisions") or []) + list(ledger.get("revisions") or [])
            for revision in revision_rows:
                if isinstance(revision, dict) and str(revision.get("action") or "") in {"correct", "correction", "supersede", "edit"}:
                    corrections.append({"source": "factual_graph", "record": deepcopy(revision)})
        legal_revision = hashlib.sha256(
            json.dumps(legal_payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        view = {
            "schema": "encrypted-interview-resume-v1",
            "status": "resumed",
            "code": "resumed",
            "resumed": True,
            "hooks_replayed": False,
            "messages_replayed": False,
            "reconstructed_from_browser_cache": False,
            "browser_cache_ignored": True,
            "case": {
                "case_id": _state_case_id(state, resolved),
                "user_id": str(state.get("user_id") or resolved),
                "session_revision": projection.get("session_revision"),
                "private_revision": state.get("private_revision"),
            },
            "consent": deepcopy(consent) if consent else None,
            "pending_inquiry": deepcopy(pending) if pending else None,
            "factual_graph_revision": factual_revision,
            "legal_graph_revision": legal_revision,
            "deferred_gaps": deferred,
            "preserved_gaps": gaps,
            "corrections": corrections,
            "legal_sufficiency": False,
        }
        payload = self.request_handlers._build_session_payload(state)
        payload["encrypted_resume"] = view
        payload["interview"] = {
            "contract_version": "interview-transition-v1",
            "action": "encrypted_resume",
            "status": "resumed",
            "inquiry": deepcopy(pending) if pending else None,
            "hooks_replayed": False,
            "messages_replayed": False,
            "legal_sufficiency": False,
            "error": None,
        }
        payload.update({
            "schema": view["schema"],
            "status": "resumed",
            "code": "resumed",
            "resumed": True,
            "hooks_replayed": False,
            "messages_replayed": False,
            "reconstructed_from_browser_cache": False,
            "browser_cache_ignored": True,
            "legal_sufficiency": False,
        })
        # Projection is not delivery authority. Reopen the real current case
        # and resolve its live key after all projection work, then reprove the
        # issued cookie/case capability immediately before returning plaintext.
        try:
            current = self._load_state(resolved, case_id=case_id)
            _, current_key_id, current_key = self._joined_key(resolved, case_id)
            if (self._case_legal_context_identity(current) != source_identity
                    or (current_key_id, current_key) != (source_key_id, source_key)):
                return denial("stale", "revision_conflict")
            self._check_access(resolved, ability="read", case_id=case_id)
        except WorkspaceAuthorizationDenied:
            return denial("denied", "authorization_denied")
        except WorkspacePersistenceError as exc:
            return denial("missing_key", str(exc.code or "missing_key"))
        return payload

    def seal_encrypted_browser_interview(self, user_id: str, *, case_id: Optional[str] = None) -> Dict[str, Any]:
        """Seal the current interview into the encrypted snapshot. No hook or message is sent."""

        from integrations.ipfs_datasets.storage import assemble_interview_snapshot

        state = self._load_state(user_id, case_id=case_id)
        record = _browser_resume_record(state)
        interview = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
        pending = record["pending_inquiry"]
        snapshot = assemble_interview_snapshot(
            session_id=str(interview.get("session_id") or state.get("user_id") or user_id),
            revision="0",
            outcome_reason="awaiting_user" if pending.get("inquiry_id") else "unknown",
            pending_inquiry=pending,
            knowledge_graph=record["factual_graph"],
            dependency_graph=record["legal_graph"],
            provenance={"source": "encrypted-browser-resume", "narrative_reextracted": False, "hooks_replayed": False, "model_calls": 0},
            unknown_items=list(interview.get("unknown_reasons") or []),
            deferred_items=list(record["deferred_gaps"]),
            complaint_text=str((_narrative_record(state).get("text") or "")),
            transcript=[],
            exports={"status": "not_filed"},
            durability_payload={"writer": "encrypted-browser-resume", "remote_replicas_claimed": False},
            revisions={
                "session_revision": record["session_revision"],
                "question_revision": pending.get("revision", "unknown"),
                "graph_revision": record["factual_graph_revision"],
            },
        )
        snapshot["browser_resume"] = record
        saved = self.persist_complete_interview_snapshot(user_id, snapshot, case_id=case_id)
        saved["hooks_replayed"] = False
        saved["messages_replayed"] = False
        saved["browser_cache_used"] = False
        return saved

    def resume_encrypted_browser_interview(self, user_id: Optional[str], *, browser_cache: Any = None) -> Dict[str, Any]:
        """Restore one interview from the encrypted snapshot in a new process.

        The browser cache argument is ignored. Hook receipts and prior messages
        are copied as already-recorded state and are not dispatched again.
        Denied, revoked, and missing-key results stay explicit and do not invent
        a case from caller plaintext.
        """

        # Actual browser owners resume the current authenticated joined case
        # revision. The optional explicitly sealed legacy snapshot may be an
        # older version and cannot overwrite current GUI state or consent.
        from .workspace_case_authority import current_workspace_case_authority
        if current_workspace_case_authority() is not None:
            return self.resume_encrypted_interview(user_id, browser_cache=browser_cache)
        del browser_cache
        receipt: Dict[str, Any] = {
            "schema": "gui-encrypted-interview-resume-v1",
            "restored": False,
            "explicit": True,
            "hooks_replayed": False,
            "messages_replayed": False,
            "browser_cache_used": False,
            "source": "encrypted_interview_snapshot",
            "code": "",
            "status": "refused",
        }
        try:
            resolved = self._check_access(user_id, ability="read")
        except WorkspaceAuthorizationDenied:
            receipt["code"] = "authorization_denied"
            receipt["status"] = "denied"
            return _encrypted_resume_refusal(user_id, receipt)
        try:
            loaded = self.load_complete_interview_snapshot(resolved)
        except WorkspacePersistenceError as exc:
            code = str(exc.code or "unavailable")
            if code == "unlock_needed":
                public = self._private_key_session().public_state()
                if public.get("code") == "key_store_absent":
                    receipt["code"] = "missing_key"
                    receipt["status"] = "missing_key"
                else:
                    receipt["code"] = "unlock_needed"
                    receipt["status"] = "denied"
            elif code == "authentication_failed":
                receipt["code"] = "key_revoked"
                receipt["status"] = "revoked"
            elif code == "snapshot_missing":
                receipt["code"] = "snapshot_missing"
                receipt["status"] = "refused"
            else:
                receipt["code"] = code
                receipt["status"] = "refused"
            return _encrypted_resume_refusal(resolved, receipt)
        snapshot = loaded.get("snapshot") if isinstance(loaded.get("snapshot"), dict) else {}
        record = snapshot.get("browser_resume") if isinstance(snapshot.get("browser_resume"), dict) else None
        if not _browser_resume_record_complete(record):
            receipt["code"] = "snapshot_incomplete"
            receipt["status"] = "refused"
            return _encrypted_resume_refusal(resolved, receipt)
        assert record is not None
        state = self._load_state(resolved)
        _apply_browser_resume_record(state, record)
        state = self._save_state(state)
        receipt["restored"] = True
        receipt["status"] = "resumed"
        receipt["code"] = "resumed"
        receipt["case_id"] = record["case_id"]
        receipt["pending_inquiry_id"] = record["pending_inquiry"].get("inquiry_id")
        receipt["factual_graph_revision"] = record["factual_graph_revision"]
        receipt["legal_graph_revision"] = record["legal_graph_revision"]
        receipt["consent_generation"] = (record.get("consent") or {}).get("generation")
        receipt["deferred_gap_count"] = len(record.get("deferred_gaps") or [])
        receipt["correction_count"] = len(record.get("corrections") or [])
        payload = self._build_intake_chat_payload(state)
        payload["encrypted_resume"] = receipt
        payload["status"] = "resumed"
        payload["stored_as_answer"] = False
        payload["legal_sufficiency"] = False
        payload["hooks_replayed"] = False
        payload["messages_replayed"] = False
        payload["browser_cache_used"] = False
        return payload

    def load_complete_interview_snapshot(
        self,
        user_id: str,
        *,
        protection: str = "user_chosen_encrypted",
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        from integrations.ipfs_datasets.storage import InterviewSnapshotError, load_interview_snapshot

        if protection == "user_chosen_encrypted":
            context = self._interview_snapshot_key(user_id, case_id)
        else:
            context = {"tenant_id": user_id, "case_id": str(case_id or user_id), "principal_id": user_id, "key": None, "key_id": None}
        directory = self.interview_snapshot_directory(str(context["tenant_id"]), str(context["case_id"]))
        try:
            return load_interview_snapshot(
                directory,
                protection=protection,
                tenant_id=str(context["tenant_id"]),
                case_id=str(context["case_id"]),
                principal_id=str(context["principal_id"]),
                key=context.get("key"),
                key_id=context.get("key_id"),
            )
        except InterviewSnapshotError as exc:
            raise WorkspacePersistenceError(str(exc), code=exc.code, public_status=exc.public_status) from None

    def migrate_plaintext_interview_snapshot(self, user_id: str, *, case_id: Optional[str] = None) -> Dict[str, Any]:
        from integrations.ipfs_datasets.storage import InterviewSnapshotError, migrate_unencrypted_interview_snapshot

        context = self._interview_snapshot_key(user_id, case_id)
        directory = self.interview_snapshot_directory(str(context["tenant_id"]), str(context["case_id"]))
        try:
            return migrate_unencrypted_interview_snapshot(
                directory,
                tenant_id=str(context["tenant_id"]),
                case_id=str(context["case_id"]),
                principal_id=str(context["principal_id"]),
                key=context["key"],
                key_id=context["key_id"],
            )
        except InterviewSnapshotError as exc:
            raise WorkspacePersistenceError(str(exc), code=exc.code, public_status=exc.public_status) from None

    def preflight_legacy_hook_artifact(
        self,
        user_id: str,
        *,
        source_path: Path,
        source_preimage: str,
        destination: Path,
        revision: str,
        case_id: Optional[str] = None,
        retention_policy: str = "retain",
    ) -> Dict[str, Any]:
        """Preflight one explicit legacy hook artifact. Does not scan or rewrite."""

        return self._legacy_hook_migration(
            user_id,
            source_path=source_path,
            source_preimage=source_preimage,
            destination=destination,
            revision=revision,
            case_id=case_id,
            retention_policy=retention_policy,
            commit=False,
            interrupt_at=None,
        )

    def commit_legacy_hook_artifact(
        self,
        user_id: str,
        *,
        source_path: Path,
        source_preimage: str,
        destination: Path,
        revision: str,
        case_id: Optional[str] = None,
        retention_policy: str = "retain",
        interrupt_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Commit one explicit legacy hook artifact. Plaintext retirement follows the receipt."""

        return self._legacy_hook_migration(
            user_id,
            source_path=source_path,
            source_preimage=source_preimage,
            destination=destination,
            revision=revision,
            case_id=case_id,
            retention_policy=retention_policy,
            commit=True,
            interrupt_at=interrupt_at,
        )

    def _legacy_hook_migration(
        self,
        user_id: str,
        *,
        source_path: Path,
        source_preimage: str,
        destination: Path,
        revision: str,
        case_id: Optional[str],
        retention_policy: str,
        commit: bool,
        interrupt_at: Optional[str],
    ) -> Dict[str, Any]:
        from integrations.private_storage import (
            PrivateArtifactBindingError,
            PrivateArtifactIntegrityError,
            PrivateKeyMaterialError,
            commit_legacy_hook_migration,
            preflight_legacy_hook_migration,
        )

        if source_path is None or destination is None or not revision:
            raise WorkspacePersistenceError(
                "An explicit legacy hook source, destination, and revision are required.",
                code="selection_required",
                public_status="unavailable",
            )
        try:
            context = self._private_artifact_context(user_id, case_id, revision=revision)
        except WorkspacePersistenceError as exc:
            return {
                "schema": "legacy-hook-migration-receipt",
                "status": "unavailable",
                "code": exc.code,
                "encrypted": False,
                "pending": True,
                "pending_items": [{"pending": "encryption"}],
                "encrypted_items": [],
                "encryption_established": False,
                "verified_commit": False,
                "automatic_scan": False,
                "durable": False,
                "network_durable": False,
                "mode_bits_establish_encryption": False,
                "local_copy_establishes_encryption": False,
                "local_copy_establishes_durability": False,
                "plaintext_retired": False,
                "source_bytes_preserved": True,
                "last_valid_head_preserved": True,
            }
        operation = commit_legacy_hook_migration if commit else preflight_legacy_hook_migration
        kwargs = dict(
            source_preimage=source_preimage,
            destination=destination,
            access=context["access"],
            tenant_id=str(context["tenant_id"]),
            case_id=str(context["case_id"]),
            principal_id=str(context["principal_id"]),
            revision=revision,
            retention_policy=retention_policy,
            key_provider=context["key_provider"],
        )
        if commit:
            kwargs["interrupt_at"] = interrupt_at
        try:
            return operation(source_path, **kwargs)
        except (PrivateArtifactBindingError, PrivateArtifactIntegrityError, PrivateKeyMaterialError) as exc:
            code = getattr(exc, "reason", None) or getattr(exc, "code", "legacy_hook_rejected")
            raise WorkspacePersistenceError(str(exc), code=str(code), public_status="recoverable") from None

    def export_readable_filing(
        self,
        user_id: str,
        *,
        destination: Path,
        protection: str,
        content: bytes,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Write an explicit operator-chosen filing export."""
        self._require_local_filesystem_access()
        self._check_access(user_id, ability="write", case_id=case_id)
        if protection not in {"user_chosen_plaintext", "user_chosen_encrypted"}:
            raise WorkspacePersistenceError(
                "protection state required",
                code="protection_required",
                public_status="unavailable",
            )
        dest = Path(destination)
        if not dest.is_absolute():
            raise WorkspacePersistenceError(
                "user-chosen location required",
                code="destination_required",
                public_status="unavailable",
            )
        resolved_user = self._check_access(user_id, ability="read")
        session_root = self._session_dir.resolve()
        try:
            dest.resolve().relative_to(session_root)
            inside_session = True
        except ValueError:
            inside_session = False
        if inside_session:
            raise WorkspacePersistenceError(
                "filing export must not use the session cache",
                code="hidden_cache_rejected",
                public_status="unavailable",
            )
        from integrations.private_storage import PrivateArtifactBinding, PrivateStorageError, seal_private_artifact, open_private_artifact
        payload = bytes(content)
        if protection == "user_chosen_encrypted":
            context = self._private_artifact_context(resolved_user, case_id)
            binding = PrivateArtifactBinding(tenant_id=resolved_user, case_id=context["case_id"], artifact_kind="filing-export", revision="filing-export-v1", principal_id=resolved_user)
            try:
                key_id, key = context["key_provider"].resolve(binding)
                payload = seal_private_artifact(payload, binding=binding, key=key, key_id=key_id)
                if open_private_artifact(payload, binding=binding, key=key, expected_key_id=key_id) != bytes(content):
                    raise WorkspacePersistenceError("Filing encryption readback failed.", code="readback_mismatch", public_status="recoverable")
            except PrivateStorageError:
                raise WorkspacePersistenceError("Private filing encryption is unavailable.", code="private_export_unavailable", public_status="unavailable") from None
        temporary = None
        try:
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            parent = dest.parent.resolve(strict=True)
            if parent != dest.parent.absolute() or parent.stat().st_uid != os.getuid():
                raise WorkspaceAuthorizationDenied()
            temporary = parent / (".filing-" + uuid.uuid4().hex + ".tmp")
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
            if temporary.read_bytes() != payload:
                raise WorkspacePersistenceError("Filing readback failed.", code="readback_mismatch", public_status="recoverable")
            os.replace(temporary, dest)
        except WorkspaceAuthorizationDenied:
            raise
        except OSError:
            raise WorkspacePersistenceError("Filing output is unavailable.", code="write_error", public_status="unavailable") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {"user_id": resolved_user, "path": str(dest), "protection": protection, "automatic": False, "hidden_cache": False, "bytes": len(payload)}

    def migrate_legacy_private_artifacts(self, **kwargs: Any) -> Dict[str, Any]:
        self._require_local_filesystem_access()
        from complaint_generator.legacy_session_migration import migrate_private_workspace
        return migrate_private_workspace(**kwargs)

    def migrate_legacy_private_session(self, user_id: str) -> Dict[str, Any]:
        """Explicitly migrate an owned JSON session, retaining its original bytes."""
        from complaint_generator.legacy_session_migration import migrate_private_workspace
        context = self._private_artifact_context(user_id)
        private_name = self._namespace_filename(user_id) + ".cgpe"
        try:
            canonical = self._read_bytes_nofollow(private_name)
        except FileNotFoundError:
            canonical = None
        if canonical is not None:
            # An authenticated current successor outranks the retained legacy
            # snapshot. Rerunning migration must never roll back newer answers.
            self._open_private_session_bytes(user_id, private_name, canonical)
            return {"status": "complete", "complete": True, "private_session_verified": True,
                    "existing_private_preserved": True, "legacy_plaintext_retained": True,
                    "source_bytes_preserved": True, "cleanup_performed": False}
        source_name = self._namespace_filename(user_id)
        try:
            raw = self._read_bytes_nofollow(source_name)
        except FileNotFoundError:
            source_name = self._legacy_filename(user_id)
            if self._legacy_owner_conflict(source_name, user_id):
                raise WorkspaceAuthorizationDenied()
            try:
                raw = self._read_bytes_nofollow(source_name)
            except FileNotFoundError:
                raise WorkspacePersistenceError("No owned legacy session was found.", code="legacy_missing", public_status="recoverable") from None
        if raw.startswith(b"CGPE"):
            self._open_private_session_bytes(user_id, source_name, raw)
            return {"status": "complete", "complete": True, "legacy_plaintext_retained": False}
        try:
            state = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise WorkspacePersistenceError("Legacy session is corrupt and was preserved.", code="corrupt_session", public_status="recoverable") from None
        if not isinstance(state, dict):
            raise WorkspacePersistenceError("Legacy session is corrupt and was preserved.", code="corrupt_session", public_status="recoverable")
        self._prepare_loaded_state(state, user_id)
        artifact = {**context, "artifact_kind": "session", "revision": "session-v1", "source_path": self._session_dir / source_name, "owner_record": {"owner": user_id, "case_id": context["case_id"]}}
        result = migrate_private_workspace(source_root=self._session_dir, destination_root=self._session_dir / "private-migrations", artifacts=[artifact])
        if result.get("complete") is not True:
            return result
        private_name = self._namespace_filename(user_id) + ".cgpe"
        try:
            previous = self._read_bytes_nofollow(private_name)
        except FileNotFoundError:
            previous = None
        self._save_private_state(state, private_name, previous)
        return {**result, "legacy_plaintext_retained": True, "source_bytes_preserved": self._read_bytes_nofollow(source_name) == raw, "private_session_verified": True}

    def _effective_access(self) -> WorkspaceAccess:
        current = _REQUEST_ACCESS.get()
        if current is not None:
            return current
        return self._default_access

    def _owner_case_authority(self):
        from .workspace_case_authority import (WorkspaceCaseAuthorityError,
            current_workspace_case_authority)
        try:
            authority = current_workspace_case_authority()
            if authority is None:
                return None
            access = self._effective_access()
            if access.trust != "authenticated" or access.case_id != authority.case_id:
                raise WorkspaceCaseAuthorityError("workspace_case_access_mismatch")
            authority.revalidate(actor_principal_id=access.principal_id,
                workspace=self, require_owner=True)
            return authority
        except WorkspaceCaseAuthorityError:
            raise WorkspaceAuthorizationDenied() from None

    def _resolve_user_id(self, user_id: Optional[str]) -> str:
        access = self._effective_access()
        supplied = str(user_id).strip() if user_id is not None and str(user_id).strip() else ""
        authority = self._owner_case_authority()
        if authority is not None:
            # The browser principal remains the actor. Only this issued,
            # re-proved owner capability selects the encrypted storage owner.
            if supplied and supplied not in {authority.actor_principal_id, authority.canonical_owner_principal_id}:
                raise WorkspaceAuthorizationDenied()
            return authority.canonical_owner_principal_id
        if access.trust == "authenticated":
            if not supplied:
                return str(access.principal_id or "")
            return supplied
        if access.trust == "trusted_local":
            if not supplied:
                return str(access.principal_id or DEFAULT_USER_ID)
            return supplied
        return supplied or DEFAULT_USER_ID

    def _check_access(
        self,
        user_id: Optional[str],
        *,
        ability: str,
        case_id: Optional[str] = None,
        record_case_id: Optional[str] = None,
    ) -> str:
        access = self._effective_access()
        authority = self._owner_case_authority()
        if authority is not None:
            if ability not in {"read", "write", "private_key"}:
                raise WorkspaceAuthorizationDenied()
            if ability == "write" and authority.action not in {"case.update", "case.message.send", "case.processing.choose"}:
                raise WorkspaceAuthorizationDenied()
            for selected in (case_id, record_case_id, _REQUEST_CASE.get(), access.case_id):
                if selected is not None and str(selected) != authority.case_id:
                    raise WorkspaceAuthorizationDenied()
            return self._resolve_user_id(user_id)
        resolved_user = self._resolve_user_id(user_id)
        explicit_case = _REQUEST_CASE.get()
        selected_case = case_id if case_id is not None else explicit_case
        if selected_case is None:
            selected_case = access.case_id
        context = access.dispatch_context(user_id=resolved_user, case_id=selected_case, ability=ability)
        if record_case_id is not None:
            attributes = dict(context.attributes)
            attributes["record_case_id"] = record_case_id
            context = WorkspaceDispatchContext(principal=context.principal, attributes=attributes)
        requirement = AuthorizationRequirement.protected("workspace.case", ability)
        admitted = False
        try:
            admitted = bool(self._authorizer(requirement, context))
        except Exception:
            admitted = False
        if not admitted:
            raise WorkspaceAuthorizationDenied()
        return resolved_user

    def _namespace_filename(self, user_id: str) -> str:
        return namespace_filename(user_id)

    def _legacy_filename(self, user_id: str) -> str:
        return f"{_slugify_user_id(user_id)}.json"

    def _session_path(self, user_id: str) -> Path:
        return self._session_dir / self._namespace_filename(user_id)

    def _legacy_session_path(self, user_id: str) -> Path:
        return self._session_dir / self._legacy_filename(user_id)

    def _open_session_directory(self) -> int:
        try:
            if self._session_dir.resolve() != self._session_dir:
                raise WorkspaceAuthorizationDenied()
            descriptor = os.open(self._session_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            metadata = os.fstat(descriptor)
            if ((metadata.st_dev, metadata.st_ino) != self._session_directory_identity
                    or metadata.st_uid != os.getuid()):
                os.close(descriptor)
                raise WorkspaceAuthorizationDenied()
            return descriptor
        except OSError:
            raise WorkspaceAuthorizationDenied() from None

    def _require_local_filesystem_access(self) -> None:
        """Host paths are operator capabilities, not remote resource identifiers.

        Dataset/manifests and legacy import/export adapters can traverse more
        than their first file. Until they expose an owner-bound storage handle,
        only an explicitly unbound local operator may give them host paths.
        """
        access = self._effective_access()
        if access.trust != "trusted_local" or access.principal_id or access.case_id:
            raise WorkspaceAuthorizationDenied()
        self._check_access(None, ability="filesystem")

    def _open_relative(self, relative: str, flags: int, mode: int = 0o600, *,
                       root_fd: Optional[int] = None, create_parents: bool = False) -> int:
        if not isinstance(relative, str) or not relative or relative.startswith("/") or "\\" in relative or "\x00" in relative:
            raise WorkspaceAuthorizationDenied()
        parts = [part for part in relative.split("/") if part != ""]
        if not parts or any(part in {".", ".."} for part in parts):
            raise WorkspaceAuthorizationDenied()
        root_fd = self._open_session_directory() if root_fd is None else os.dup(root_fd)
        current = -1
        close_current = False
        try:
            for index, part in enumerate(parts):
                last = index == len(parts) - 1
                parent_fd = root_fd if not close_current else current
                if not last and create_parents:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=parent_fd)
                    except FileExistsError:
                        pass
                open_flags = os.O_NOFOLLOW | os.O_NONBLOCK | (flags if last else (os.O_RDONLY | os.O_DIRECTORY))
                try:
                    opened = os.open(part, open_flags, mode if last else 0, dir_fd=parent_fd)
                except OSError as exc:
                    if exc.errno in {errno.ELOOP, errno.ENOTDIR, errno.EPERM}:
                        raise WorkspaceAuthorizationDenied() from None
                    raise
                if close_current:
                    os.close(current)
                current = opened
                close_current = True
            metadata = os.fstat(current)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_uid != os.getuid()):
                raise WorkspaceAuthorizationDenied()
            owned = current
            current = -1
            close_current = False
            return owned
        finally:
            if close_current and current >= 0:
                os.close(current)
            os.close(root_fd)

    def _read_bytes_nofollow(self, relative: str) -> bytes:
        fd = self._open_relative(relative, os.O_RDONLY)
        try:
            chunks: List[bytes] = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)

    def _write_bytes_nofollow(self, relative: str, payload: bytes, *,
                              root_fd: Optional[int] = None, create_parents: bool = False,
                              durable: bool = False) -> None:
        # Validate the opened inode before truncation, including hard-link and
        # special-file refusal. Opening with O_TRUNC would already damage it.
        fd = self._open_relative(relative, os.O_WRONLY | os.O_CREAT,
                                 root_fd=root_fd, create_parents=create_parents)
        try:
            os.ftruncate(fd, 0)
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            if durable:
                os.fsync(fd)
        finally:
            os.close(fd)

    def _read_json_file(self, filename: str, *, strict: bool = False) -> Optional[Dict[str, Any]]:
        try:
            raw = self._read_bytes_nofollow(filename)
        except FileNotFoundError:
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            if strict:
                raise WorkspaceAuthorizationDenied() from None
            return None
        if not isinstance(payload, dict):
            if strict:
                raise WorkspaceAuthorizationDenied()
            return None
        return payload

    def _read_legacy_map(self) -> Dict[str, Any]:
        payload = self._read_json_file(_LEGACY_MAP_NAME)
        if not isinstance(payload, dict):
            return {"version": 1, "entries": {}}
        entries = payload.get("entries")
        if not isinstance(entries, dict):
            payload["entries"] = {}
        payload.setdefault("version", 1)
        return payload

    def _write_legacy_map(self, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self._write_bytes_nofollow(_LEGACY_MAP_NAME, body)

    def _record_legacy_owner(self, slug: str, owner: str) -> None:
        mapping = self._read_legacy_map()
        entries = dict(mapping.get("entries") or {})
        current = entries.get(slug)
        if isinstance(current, dict) and str(current.get("owner") or "") not in {"", owner}:
            return
        if isinstance(current, dict) and str(current.get("owner") or "") == owner:
            return
        entries[slug] = {"owner": owner, "namespace": principal_namespace(owner)}
        mapping["entries"] = entries
        self._write_legacy_map(mapping)

    def _legacy_owner_conflict(self, slug: str, owner: str) -> bool:
        entries = dict(self._read_legacy_map().get("entries") or {})
        current = entries.get(slug)
        if not isinstance(current, dict):
            return False
        recorded = str(current.get("owner") or "")
        return bool(recorded) and recorded != owner

    def _prepare_loaded_state(self, payload: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        owner = payload.get("user_id")
        if not isinstance(owner, str) or owner != user_id:
            raise WorkspaceAuthorizationDenied()
        record_case = _state_case_id(payload, user_id)
        self._check_access(user_id, ability="read", record_case_id=record_case)
        expected_case = _REQUEST_CASE.get() or self._effective_access().case_id
        if expected_case is not None and str(record_case) != str(expected_case):
            raise WorkspaceAuthorizationDenied()
        self._assert_bound_references(payload, record_case)
        payload["claim_type"] = _normalize_claim_type(payload.get("claim_type"))
        return payload

    def _assert_bound_references(self, payload: Mapping[str, Any], record_case: str) -> None:
        cid = _REQUEST_CID.get()
        storage_key = _REQUEST_STORAGE_KEY.get()
        if cid is None and storage_key is None:
            return
        references = [item for item in list(payload.get("private_references") or []) if isinstance(item, Mapping)]

        def _matches(item: Mapping[str, Any]) -> bool:
            if str(item.get("case_id") or record_case) != str(record_case):
                return False
            if cid is not None and str(item.get("cid") or "") != cid:
                return False
            if storage_key is not None and str(item.get("storage_key") or "") != storage_key:
                return False
            return True

        if not any(_matches(item) for item in references):
            raise WorkspaceAuthorizationDenied()

    def _load_owned_payload(self, user_id: str) -> Optional[Dict[str, Any]]:
        namespaced = self._read_json_file(self._namespace_filename(user_id), strict=True)
        if namespaced is not None:
            return self._prepare_loaded_state(namespaced, user_id)
        slug = self._legacy_filename(user_id)
        if self._legacy_owner_conflict(slug, user_id):
            return None
        legacy = self._read_json_file(slug)
        if legacy is None:
            return None
        legacy_owner = legacy.get("user_id")
        if legacy_owner is None or str(legacy_owner) != user_id:
            return None
        self._record_legacy_owner(slug, user_id)
        return self._prepare_loaded_state(legacy, user_id)

    def _private_file_relative(self, user_id: Optional[str], relative_name: str, *, ability: str) -> str:
        resolved = self._check_access(user_id, ability=ability)
        state = self._load_state(resolved)
        case_id = _state_case_id(state, resolved)
        if (not isinstance(relative_name, str) or not relative_name or relative_name.startswith("/")
                or "\\" in relative_name or "\x00" in relative_name
                or any(part in {"", ".", "..", _LEGACY_MAP_NAME}
                       or re.fullmatch(r"p-[0-9a-f]{64}\.json", part)
                       for part in relative_name.split("/"))):
            raise WorkspaceAuthorizationDenied()
        return f"private-files/p-{principal_namespace(resolved)}/c-{principal_namespace(case_id)}/{relative_name}"

    def _contained_file_binding(self, resolved: str, relative: str):
        from integrations.private_storage import PrivateArtifactBinding
        context = self._private_artifact_context(resolved)
        binding = PrivateArtifactBinding(tenant_id=resolved, case_id=context["case_id"],
            artifact_kind="contained-file", revision="file-" + hashlib.sha256(relative.encode("utf-8")).hexdigest(), principal_id=resolved)
        return context, binding

    def _open_private_file_parent(self, relative: str) -> tuple[int, str]:
        # relative was admitted by _private_file_relative; keep every parent
        # directory opened with no-follow through the final atomic publication.
        parts = relative.split("/")
        current = self._open_session_directory()
        try:
            for part in parts[:-1]:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                info = os.fstat(child)
                if info.st_uid != os.getuid():
                    os.close(child)
                    raise WorkspaceAuthorizationDenied()
                os.close(current)
                current = child
            return current, parts[-1]
        except (OSError, WorkspaceAuthorizationDenied):
            os.close(current)
            raise WorkspaceAuthorizationDenied() from None

    def read_contained_workspace_file(self, user_id: Optional[str], relative_name: str) -> bytes:
        from integrations.private_storage import PrivateStorageError, open_private_artifact
        resolved = self._check_access(user_id, ability="read")
        relative = self._private_file_relative(resolved, relative_name, ability="read")
        context, binding = self._contained_file_binding(resolved, relative)
        try:
            blob = self._read_bytes_nofollow(relative)
            key_id, key = context["key_provider"].resolve(binding)
            return open_private_artifact(blob, binding=binding, key=key, expected_key_id=key_id)
        except OSError:
            raise WorkspaceAuthorizationDenied() from None
        except PrivateStorageError:
            raise WorkspacePersistenceError("Private file authentication failed; existing bytes were preserved.", code="authentication_failed", public_status="recoverable") from None

    def write_contained_workspace_file(self, user_id: Optional[str], relative_name: str, content: bytes) -> Dict[str, Any]:
        from integrations.private_storage import PrivateStorageError, open_private_artifact, seal_private_artifact
        resolved = self._check_access(user_id, ability="write")
        relative = self._private_file_relative(resolved, relative_name, ability="write")
        context, binding = self._contained_file_binding(resolved, relative)
        parent_fd, filename = self._open_private_file_parent(relative)
        temporary = ".private-file-" + uuid.uuid4().hex + ".tmp"
        try:
            key_id, key = context["key_provider"].resolve(binding)
            try:
                previous = self._read_bytes_nofollow(relative)
            except FileNotFoundError:
                previous = None
            if previous is not None:
                open_private_artifact(previous, binding=binding, key=key, expected_key_id=key_id)
            body = bytes(content or b"")
            envelope = seal_private_artifact(body, binding=binding, key=key, key_id=key_id)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
            with os.fdopen(fd, "wb") as handle:
                handle.write(envelope)
                handle.flush()
            stage = self._read_bytes_nofollow("/".join(relative.split("/")[:-1] + [temporary]))
            if stage != envelope or open_private_artifact(stage, binding=binding, key=key, expected_key_id=key_id) != body:
                raise WorkspacePersistenceError("Private file readback failed.", code="readback_mismatch", public_status="recoverable")
            try:
                current = self._read_bytes_nofollow(relative)
            except FileNotFoundError:
                current = None
            if current != previous:
                raise WorkspacePersistenceError("Private file changed; current bytes were preserved.", code="revision_conflict", public_status="recoverable")
            if context["key_provider"].resolve(binding) != (key_id, key):
                raise WorkspacePersistenceError("Private workspace keys require unlock.", code="unlock_needed", public_status="unlock_needed")
            os.replace(temporary, filename, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        except OSError:
            raise WorkspaceAuthorizationDenied() from None
        except PrivateStorageError:
            raise WorkspacePersistenceError("Private file authentication failed; existing bytes were preserved.", code="authentication_failed", public_status="recoverable") from None
        finally:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            os.close(parent_fd)
        return {"user_id": resolved, "relative_name": str(relative_name or ""), "written": True, "at_rest_protection": "private_envelope"}

    def remember_private_reference(
        self,
        user_id: Optional[str],
        *,
        cid: Optional[str] = None,
        storage_key: Optional[str] = None,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved = self._resolve_user_id(user_id)
        with _workspace_reference_scope(case_id=case_id):
            state = self._load_state(resolved)
        record_case = _state_case_id(state, resolved)
        if case_id is not None and str(case_id) != record_case:
            raise WorkspaceAuthorizationDenied()
        if not cid and not storage_key:
            raise WorkspaceAuthorizationDenied()
        references = [item for item in list(state.get("private_references") or []) if isinstance(item, dict)]
        references.append(
            {
                "cid": None if cid is None else str(cid),
                "storage_key": None if storage_key is None else str(storage_key),
                "case_id": record_case,
            }
        )
        state["private_references"] = references
        self._save_state(state)
        return {
            "user_id": resolved,
            "case_id": record_case,
            "stored": True,
            "at_rest_protection": "private_envelope",
        }

    def resolve_private_reference(
        self,
        user_id: Optional[str],
        *,
        case_id: Optional[str] = None,
        cid: Optional[str] = None,
        storage_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved = self._resolve_user_id(user_id)
        with _workspace_reference_scope(case_id=case_id, cid=cid, storage_key=storage_key):
            state = self._load_state(resolved)
        return {
            "user_id": str(state.get("user_id") or resolved),
            "case_id": _state_case_id(state, resolved),
            "cid": None if cid is None else str(cid),
            "storage_key": None if storage_key is None else str(storage_key),
            "admitted": True,
            "at_rest_protection": "private_envelope",
        }

    def _load_state(self, user_id: str, *, case_id: Optional[str] = None) -> Dict[str, Any]:
        resolved_user = self._check_access(user_id, ability="read", case_id=case_id)
        context = self._private_artifact_context(resolved_user, case_id)
        repository = self.joined_revision_repository(resolved_user, context["case_id"])
        from integrations.private_storage import private_revision_readiness, PrivateStorageError
        _, readiness_key_id, readiness_key = self._joined_key(resolved_user, context["case_id"])
        try:
            readiness = private_revision_readiness(repository, tenant_id=resolved_user,
                case_id=context["case_id"], principal_id=context["principal_id"],
                key=readiness_key, key_id=readiness_key_id, key_resolver=self._joined_key_resolver(resolved_user, context["case_id"]))
        except PrivateStorageError as exc:
            raise WorkspacePersistenceError("Joined state requires authenticated recovery; original bytes were preserved.",
                code=exc.code, public_status="recoverable") from None
        if readiness == "committed":
            from integrations.private_storage import read_private_revision, PrivateStorageError
            _, key_id, key = self._joined_key(resolved_user, context["case_id"])
            try:
                opened = read_private_revision(repository, tenant_id=resolved_user, case_id=context["case_id"],
                    principal_id=context["principal_id"], key=key, key_id=key_id, key_resolver=self._joined_key_resolver(resolved_user, context["case_id"]))
                loaded = json.loads(opened["session"])
                graph = json.loads(opened["fact_graph"])
                proof = json.loads(opened["proof"])
                if (str(loaded.get("private_revision")) != opened["revision"]
                    or loaded.get("annotation_knowledge_graph", {}).get("relationships", []) != graph.get("relationships", [])
                    or loaded.get("proof_history", []) != proof.get("entries", [])):
                    raise ValueError("joined revision differs")
                self._prepare_loaded_state(loaded, resolved_user)
            except (PrivateStorageError, ValueError, TypeError, KeyError):
                raise WorkspacePersistenceError("Joined private state did not authenticate; original bytes were preserved.",
                    code="authentication_failed", public_status="recoverable") from None
            loaded.update(status="available", session_readable=True, missing_new_session=False,
                          existing_unreadable=False, at_rest_protection="private_envelope")
            return loaded
        filename = self._private_session_filename(resolved_user)
        try:
            raw = self._read_bytes_nofollow(filename)
        except FileNotFoundError:
            raw = None
        except WorkspaceAuthorizationDenied:
            raise
        except OSError:
            raise WorkspacePersistenceError("Private session storage is unavailable.", code="read_error", public_status="unavailable") from None
        if raw is not None:
            if raw.startswith(b"CGPE"):
                loaded = self._open_private_session_bytes(resolved_user, filename, raw)
            else:
                try:
                    legacy = json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise WorkspacePersistenceError("Existing session is corrupt and was preserved.", code="corrupt_session", public_status="recoverable") from None
                if not isinstance(legacy, dict):
                    raise WorkspacePersistenceError("Existing session is corrupt and was preserved.", code="corrupt_session", public_status="recoverable")
                self._prepare_loaded_state(legacy, resolved_user)
                raise WorkspacePersistenceError("Legacy data requires explicit migration.", code="migration_required", public_status="recoverable")
        else:
            legacy = None
            slug = self._legacy_filename(resolved_user)
            if not self._legacy_owner_conflict(slug, resolved_user):
                try:
                    legacy_raw = self._read_bytes_nofollow(slug)
                except FileNotFoundError:
                    legacy_raw = None
                except WorkspaceAuthorizationDenied:
                    raise
                except OSError:
                    raise WorkspacePersistenceError("Private session storage is unavailable.", code="read_error", public_status="unavailable") from None
                if legacy_raw is not None:
                    try:
                        legacy = json.loads(legacy_raw.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        raise WorkspacePersistenceError("Existing legacy session is corrupt and was preserved.", code="corrupt_session", public_status="recoverable") from None
                    if not isinstance(legacy, dict):
                        raise WorkspacePersistenceError("Existing legacy session is corrupt and was preserved.", code="corrupt_session", public_status="recoverable")
            if isinstance(legacy, dict) and legacy.get("user_id") == resolved_user:
                self._prepare_loaded_state(legacy, resolved_user)
                raise WorkspacePersistenceError("Legacy data requires explicit migration.", code="migration_required", public_status="recoverable")
            loaded = _default_state(resolved_user)
            loaded["case_id"] = context["case_id"]
            loaded.update(missing_new_session=True, session_readable=True, status="available")
            self._prepare_loaded_state(loaded, resolved_user)
        payload = loaded
        payload["claim_type"] = _normalize_claim_type(payload.get("claim_type"))
        payload.setdefault("case_synopsis", "")
        payload.setdefault("intake_answers", {})
        payload.setdefault("intake_history", [])
        migrate_original_complaint(payload)
        payload.setdefault("evidence", {"testimony": [], "documents": []})
        payload.setdefault("document_annotations", [])
        payload.setdefault("annotation_knowledge_graph", {"entities": [], "relationships": []})
        payload.setdefault("workspace_annotation_index", {"by_tag": {}, "by_collection": {}, "by_document_type": {}})
        payload.setdefault("filing_metadata", {})
        payload.setdefault("draft", None)
        payload.setdefault("latest_packet_export", None)
        payload.setdefault("latest_export_critic", None)
        payload.setdefault("ui_readiness", None)
        payload.setdefault("case_id", user_id)
        payload.setdefault("privacy_notice_shown", False)
        # Serialized identity fields cannot transfer another workspace's cloud
        # consent to the record selected by the caller. This binds policy only;
        # tenant authorization remains a separate requirement.
        _apply_effective_privacy_policy(payload, user_id)
        payload.setdefault(
            "mike_integration",
            {
                "last_handoff": None,
                "last_sync": None,
                "handoff_history": [],
                "sync_history": [],
                "audit_trail": [],
            },
        )
        if isinstance(payload.get("mike_integration"), dict):
            payload["mike_integration"].setdefault("audit_trail", [])
        return payload

    def _terminal_graph_edit_publication_guard(self, state: Mapping[str, Any], *, actor_principal_id: str,
                                             case_id: str) -> Optional[Callable[[], Any]]:
        """Capture current issued owner, private source and key before editing.

        This trusted callback is constructed inside the service, never from a
        request field. The joined writer invokes it at the final head replace.
        It grants no authority to callers without the current issued scope.
        """
        from .workspace_case_authority import WorkspaceCaseAuthorityError
        from integrations.private_storage import PrivateStorageError
        authority = self._owner_case_authority()
        if authority is None:
            return None
        actor, user = str(actor_principal_id), str(state.get("user_id") or "")

        def owner():
            try:
                decision = authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            except WorkspaceCaseAuthorityError:
                raise WorkspaceAuthorizationDenied() from None
            if (authority.action != "case.update" or authority.actor_principal_id != actor
                    or authority.case_id != case_id or user != decision.canonical_owner_principal_id
                    or state.get("case_id") != case_id):
                raise WorkspaceAuthorizationDenied()
            return decision

        def key():
            try:
                _context, key_id, material = self._joined_key(user, case_id)
            except PrivateStorageError:
                raise WorkspacePersistenceError("Private correction key is unavailable.",
                    code="unlock_needed", public_status="unavailable") from None
            return key_id, material

        owner()
        before = self._case_legal_context_identity(state)
        admitted_key = key()

        def revalidate_publication():
            owner()
            if key() != admitted_key:
                raise WorkspacePersistenceError("Correction key changed before publication.",
                    code="revision_conflict", public_status="conflict")
            current = self._load_state(user, case_id=case_id)
            if before != self._case_legal_context_identity(current):
                raise WorkspacePersistenceError("Correction source changed before publication.",
                    code="revision_conflict", public_status="conflict")
            owner()
            if key() != admitted_key:
                raise WorkspacePersistenceError("Correction key changed before publication.",
                    code="revision_conflict", public_status="conflict")

        return revalidate_publication

    def _save_state(self, state: Dict[str, Any], *, before_publish: Optional[Callable[[], Any]] = None) -> Dict[str, Any]:
        if state.get("session_readable") is False or state.get("existing_unreadable"):
            raise WorkspacePersistenceError(
                "refusing to replace an unreadable session",
                code="overwrite_blocked",
                public_status=str(state.get("status") or "recoverable"),
            )
        state["updated_at"] = _utc_now()
        user_id = str(state.get("user_id") or DEFAULT_USER_ID)
        state["user_id"] = user_id
        record_case = _state_case_id(state, user_id)
        self._check_access(user_id, ability="write", record_case_id=record_case)
        _apply_effective_privacy_policy(state, user_id)
        repository = self.joined_revision_repository(user_id, record_case)
        from integrations.private_storage import private_revision_readiness, PrivateStorageError
        context, readiness_key_id, readiness_key = self._joined_key(user_id, record_case)
        try:
            readiness = private_revision_readiness(repository, tenant_id=user_id,
                case_id=record_case, principal_id=context["principal_id"],
                key=readiness_key, key_id=readiness_key_id, key_resolver=self._joined_key_resolver(user_id, record_case))
        except PrivateStorageError as exc:
            raise WorkspacePersistenceError("Joined state requires authenticated recovery; original bytes were preserved.",
                code=exc.code, public_status="recoverable") from None
        if readiness == "committed":
            return self._commit_joined_snapshot(state,
                **({"before_publish": before_publish} if before_publish is not None else {}))
        if before_publish is not None:
            raise WorkspacePersistenceError("Guarded publication requires a committed joined revision.",
                code="joined_revision_required", public_status="recoverable")
        filename = self._private_session_filename(user_id)
        try:
            existing_raw = self._read_bytes_nofollow(filename)
        except FileNotFoundError:
            existing_raw = None
        except WorkspaceAuthorizationDenied:
            raise
        except OSError as exc:
            raise WorkspacePersistenceError("session unreadable", code="read_error", public_status="unavailable") from exc
        if existing_raw is not None and not existing_raw.startswith(b"CGPE"):
            try:
                json.loads(existing_raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise WorkspacePersistenceError(
                    "corrupt session preserved",
                    code="corrupt_session",
                    public_status="recoverable",
                ) from exc
        return self._save_private_state(state, filename, existing_raw)

    def _build_question_status(self, answers: Dict[str, Any]) -> List[Dict[str, Any]]:
        status = []
        for question in _INTAKE_QUESTIONS:
            answer = str(answers.get(question["id"]) or "").strip()
            status.append(
                {
                    **question,
                    "answer": answer,
                    "is_answered": bool(answer),
                }
            )
        return status

    def _next_question(self, answers: Dict[str, Any]) -> Optional[Dict[str, str]]:
        for question in _INTAKE_QUESTIONS:
            if not str(answers.get(question["id"]) or "").strip():
                return question
        return None

    def _question_by_id(self, question_id: Optional[str]) -> Optional[Dict[str, str]]:
        normalized_question_id = str(question_id or "").strip()
        if not normalized_question_id:
            return None
        for question in _INTAKE_QUESTIONS:
            if question["id"] == normalized_question_id:
                return question
        return None

    def _build_intake_chat_explanation(self, question: Dict[str, str], state: Dict[str, Any]) -> Dict[str, Any]:
        review = self._build_review(state)
        support_matrix = list(review.get("support_matrix") or [])
        first_gap = next((item for item in support_matrix if not item.get("supported")), None)
        focus_gap = (
            f"Current biggest support gap: {str(first_gap.get('label') or '').lower()}."
            if first_gap
            else "Core claim elements already have at least some recorded support."
        )
        guidance = {
            "original_complaint": {
                "why_this_matters": "The original complaint is the complainant's story. It stays separate from the structured name, party, and element answers.",
                "how_to_answer": "Describe what happened in plain language. You can use more than one line, paste a file, or revise this narrative later without changing your name.",
            },
            "party_name": {
                "why_this_matters": "This anchors who the complaint belongs to across the CLI, web workspace, and later evidence collection.",
                "how_to_answer": "Use the name that should appear in the complaint caption or intake record.",
            },
            "opposing_party": {
                "why_this_matters": "This identifies the target organization or person so the record, draft, and evidence search stay pointed at the right defendant.",
                "how_to_answer": "Name the employer, housing provider, agency, or other party you are complaining about.",
            },
            "protected_activity": {
                "why_this_matters": "This is usually the first element that explains why the later adverse action may have been unlawful retaliation or interference.",
                "how_to_answer": "Describe what you reported, opposed, requested, or disclosed before things got worse.",
            },
            "adverse_action": {
                "why_this_matters": "This captures what happened to you after the protected activity and helps define damages and liability.",
                "how_to_answer": "Describe the concrete action taken against you, such as termination, denial, discipline, or eviction threat.",
            },
            "timeline": {
                "why_this_matters": "Timing is often what connects the protected activity to the adverse action and exposes causation gaps.",
                "how_to_answer": "Give the key dates or sequence in plain language, even if you only know approximate timing.",
            },
            "harm": {
                "why_this_matters": "This clarifies damages and what relief the complaint should eventually request.",
                "how_to_answer": "List the practical harm you suffered, such as lost wages, housing instability, denied benefits, or emotional distress.",
            },
            "court_header": {
                "why_this_matters": "This helps format the eventual complaint draft correctly when you already know the court or forum.",
                "how_to_answer": "If you know the court caption, provide it. If not, you can say that you are unsure.",
            },
        }.get(question["id"], {})
        return {
            "question_id": question["id"],
            "why_this_matters": guidance.get("why_this_matters") or "This helps tighten the intake record before evidence and legal research begin.",
            "how_to_answer": guidance.get("how_to_answer") or "Answer in plain language with the most concrete facts you know right now.",
            "review_focus": focus_gap,
        }

    def _build_intake_chat_payload(
        self,
        state: Dict[str, Any],
        *,
        accepted_answer: Optional[Dict[str, Any]] = None,
        requested_question_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        answers = state.get("intake_answers") or {}
        review = self._build_review(state)
        questions = self._build_question_status(answers)
        requested_id = str(requested_question_id or "").strip()
        if requested_id == ORIGINAL_COMPLAINT_QUESTION_ID or (not requested_id and _narrative_is_open(state)):
            active_question = dict(_NARRATIVE_INQUIRY)
        elif requested_id:
            active_question = self._question_by_id(requested_id)
        else:
            active_question = self._next_question(answers)
        answered_count = len([item for item in questions if item.get("is_answered")])
        total_questions = len(questions)
        narrative_record = _narrative_record(state)
        if active_question:
            if active_question["id"] == ORIGINAL_COMPLAINT_QUESTION_ID:
                lead_in = "Let's start with the basics. Describe your complaint in plain language."
            elif answered_count == 0 and not str(narrative_record.get("text") or "").strip():
                lead_in = "Let's start with the basics."
            elif accepted_answer:
                lead_in = "I have that. Next:"
            else:
                lead_in = "Next question:"
            message = f"{lead_in} {active_question['prompt']}"
            explanation = self._build_intake_chat_explanation(active_question, state)
        else:
            message = (
                "No further answerable intake questions are waiting. That is interview saturation, "
                "not a finding that every fact, proof requirement, or legal element is satisfied."
            )
            explanation = {
                "question_id": None,
                "why_this_matters": "An empty question list does not establish legal sufficiency or complete core facts.",
                "how_to_answer": "Review the remaining issues, then add evidence or resume when there is something new to say.",
                "review_focus": "Unresolved proof and evidence gaps stay open until they are actually resolved.",
            }
        payload = {
            "user_id": str(state.get("user_id") or DEFAULT_USER_ID),
            "message": message,
            "inquiry": {
                "question_id": active_question["id"],
                "label": active_question["label"],
                "prompt": active_question["prompt"],
                "placeholder": active_question.get("placeholder") or "",
                "kind": "narrative" if active_question["id"] == ORIGINAL_COMPLAINT_QUESTION_ID else "structured",
            }
            if active_question
            else None,
            "original_complaint": deepcopy(narrative_record),
            "explanation": explanation,
            "accepted_answer": deepcopy(accepted_answer) if accepted_answer else None,
            "questions": questions,
            "next_question": (
                {
                    "id": active_question["id"],
                    "label": active_question["label"],
                    "prompt": active_question["prompt"],
                    "placeholder": active_question.get("placeholder") or "",
                }
                if active_question
                else self._next_question(answers)
            ),
            "review": review,
            "case_synopsis": self._build_case_synopsis(state),
            "session": deepcopy(state),
            "conversation_state": {
                "answered_question_count": answered_count,
                "total_question_count": total_questions,
                "is_complete": active_question is None,
                "narrative_captured": bool(str(narrative_record.get("text") or "").strip()),
                "narrative_revision": int(narrative_record.get("revision") or 0),
                "remaining_question_ids": [item["id"] for item in _INTAKE_QUESTIONS if not str(answers.get(item["id"]) or "").strip()],
            },
        }

        projection = state.get("shared_interview")
        if isinstance(projection, dict) and projection.get("schema_version") == "shared-interview-session-v1":
            pending = projection.get("pending_inquiry")
            payload["legacy_inquiry"] = deepcopy(payload["inquiry"])
            payload["legacy_conversation_state"] = deepcopy(payload["conversation_state"])
            if isinstance(pending, dict):
                inquiry = {
                    "question_id": pending.get("inquiry_id"), "inquiry_id": pending.get("inquiry_id"),
                    "label": "Complaint follow-up", "prompt": str(pending.get("question") or ""),
                    "placeholder": "", "kind": "graph", "revision": pending.get("revision"),
                }
                payload["inquiry"] = inquiry
                payload["next_question"] = {"id": inquiry["question_id"], **inquiry}
                payload["message"] = inquiry["prompt"]
                payload["expected_question_revision"] = pending.get("revision")
            else:
                payload["inquiry"] = None
                payload["next_question"] = None
                payload["expected_question_revision"] = None
                payload["message"] = "The shared interview has no pending question. Review its unknown, unavailable and capped reasons before proceeding."
            payload["conversation_state"]["is_complete"] = pending is None
            payload["conversation_state"]["active_engine"] = "shared_interview"
            payload["legal_sufficiency"] = False
        payload["stopping_policy"] = _workspace_stopping_policy(state, active_question=active_question, answers=answers)
        if state.get("open_dependencies") or state.get("dependency_action_context") or (
            isinstance(state.get("interview_stop"), dict) and state["interview_stop"].get("dependency_lane")
        ):
            payload["authorized_next_action"] = publish_workspace_dependency_action(state)
        payload["legal_sufficiency"] = False
        payload["core_facts_complete"] = False
        payload["filing_ready"] = False
        payload["adaptive_inquiry"] = _adaptive_inquiry_view(state)
        payload["gap_preserved"] = bool(payload["adaptive_inquiry"]["preserved_gaps"])
        payload["finite_interview_outcome"] = finite_interview_outcome(state, active_question=active_question)
        payload["worker_stalled"] = False if payload["finite_interview_outcome"].get("user_waiting") else bool(payload["finite_interview_outcome"].get("worker_stalled"))
        payload["user_waiting_is_worker_stall"] = False
        payload["changes_law"] = False
        payload["encrypted_head"] = _encrypted_head(state)
        payload["affected_support_projection"] = [
            dict(item) for item in (state.get("affected_support_projection") or []) if isinstance(item, dict)
        ]
        return payload

    def record_finite_interview_stop(self, state: Dict[str, Any], control: str) -> Dict[str, Any]:
        """Persist one denoiser stop for pause, cancel, cap, unavailable capability, or saturation.

        The user is not a stalled development worker. The saved stop keeps its
        unresolved reasons and never records legal sufficiency.
        """

        authority = self._owner_case_authority()
        user = str(state.get("user_id") or "")
        case_id = _state_case_id(state, user)
        publication_guard = None
        admitted_key = None
        if authority is not None:
            publication_guard = self._terminal_graph_edit_publication_guard(state,
                actor_principal_id=authority.actor_principal_id, case_id=case_id)
            _context, key_id, key = self._joined_key(user, case_id)
            admitted_key = (key_id, key)
        normalized = str(control or "").strip().lower()
        if normalized == "pause":
            state["intentional_user_wait"] = {
                "paused": True,
                "intentional": True,
                "reason": "user_pause",
            }
        else:
            state["intentional_user_wait"] = {
                "paused": False,
                "intentional": False,
                "reason": normalized,
            }
        state["worker_stalled"] = False
        answers = state.get("intake_answers") or {}
        active = None if normalized in {"saturate", "cap", "cancel", "unavailable"} else self._next_question(answers)
        stop = _evaluate_finite_stop(state, control=normalized, active_question=active)
        stop["legal_sufficiency"] = False
        stop["worker_stalled"] = False
        state["interview_stop"] = stop
        if publication_guard is not None:
            publication_guard()
            state = self._save_state(state, before_publish=publication_guard)
        else:
            state = self._save_state(state)

        def projection(current):
            payload = self._build_intake_chat_payload(current, accepted_answer=None, requested_question_id=None)
            payload["stored_as_answer"] = False
            payload["legal_sufficiency"] = False
            payload["worker_stalled"] = False
            payload["user_waiting_is_worker_stall"] = False
            payload["finite_interview_outcome"] = finite_interview_outcome(current, active_question=active, stop=stop)
            payload["message"] = (
                f"Interview stop: {payload['finite_interview_outcome']['stop']}. "
                "Unresolved reasons stay visible. This is not legal sufficiency."
            )
            return payload

        if authority is None:
            return projection(state)
        # Its own successful commit advances the head. Delivery authenticates
        # the current committed revision instead of replaying the old guard.
        from integrations.private_storage import private_revision_source_scope
        with private_revision_source_scope(self.joined_revision_repository(user, case_id)):
            current = self._load_state(user, case_id=case_id)
            if current.get("private_revision") != state.get("private_revision"):
                raise WorkspacePersistenceError("Finite-stop source changed before delivery.",
                    code="revision_conflict", public_status="conflict")
            payload = projection(current)
            _context, key_id, key = self._joined_key(user, case_id)
            if (key_id, key) != admitted_key:
                raise WorkspacePersistenceError("Finite-stop key changed before delivery.",
                    code="revision_conflict", public_status="conflict")
            authority.revalidate(actor_principal_id=authority.actor_principal_id, workspace=self, require_owner=True)
            return payload

    def _support_matrix(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        answers = state.get("intake_answers") or {}
        testimony = state.get("evidence", {}).get("testimony") or []
        documents = state.get("evidence", {}).get("documents") or []
        interview_complete = False
        shared = state.get("shared_interview") if isinstance(state.get("shared_interview"), Mapping) else {}
        if shared.get("schema_version") and not (shared.get("pending_inquiry") or {}):
            interview_complete = shared.get("pending_inquiry") is None and bool(shared.get("answered_inquiries") or shared.get("session_revision"))
        matrix: List[Dict[str, Any]] = []
        for element in _CLAIM_ELEMENTS:
            intake_asserted = bool(str(answers.get(element["id"]) or "").strip()) or (
                element["id"] == "employer_knowledge" and bool(str(answers.get("protected_activity") or "").strip())
            ) or (element["id"] == "causation" and bool(str(answers.get("timeline") or "").strip()))
            matching_testimony = [item for item in testimony if item.get("claim_element_id") == element["id"]]
            matching_documents = [item for item in documents if item.get("claim_element_id") == element["id"]]
            source_bound = [
                item for item in [*matching_testimony, *matching_documents]
                if _source_bound_evidence(item)
            ]
            matrix.append(
                {
                    "id": element["id"],
                    "label": element["label"],
                    "supported": bool(source_bound),
                    "intake_supported": False,
                    "intake_asserted": intake_asserted,
                    "interview_complete": bool(interview_complete),
                    "interview_completion_means_legal_sufficiency": False,
                    "legal_sufficiency": False,
                    "support_requires_source_bound_evidence": True,
                    "testimony_count": len(matching_testimony),
                    "document_count": len(matching_documents),
                    "source_bound_count": len(source_bound),
                    "support_count": len(source_bound),
                    "status": "supported" if source_bound else "needs_source_bound_evidence",
                }
            )
        return matrix

    def _build_review(self, state: Dict[str, Any]) -> Dict[str, Any]:
        matrix = self._support_matrix(state)
        supported = [item for item in matrix if item["supported"]]
        missing = [item for item in matrix if not item["supported"]]
        evidence = state.get("evidence") or {}
        case_synopsis = self._build_case_synopsis(state)
        return {
            "claim_type": state.get("claim_type", "retaliation"),
            "case_synopsis": case_synopsis,
            "legal_sufficiency": False,
            "interview_completion_means_legal_sufficiency": False,
            "support_matrix": matrix,
            "overview": {
                "supported_elements": len(supported),
                "missing_elements": len(missing),
                "testimony_items": len(evidence.get("testimony") or []),
                "document_items": len(evidence.get("documents") or []),
                "legal_sufficiency": False,
            },
            "recommended_actions": [
                {
                    "title": "Collect source-bound evidence",
                    "detail": "Add testimony or documents that name a factual or legal source. Intake answers and a finished interview are not support."
                    if missing
                    else "Source-bound evidence is recorded. That record is still not a finding of legal sufficiency.",
                },
                {
                    "title": "Check the timeline",
                    "detail": "Close timing between protected activity and adverse action strengthens causation.",
                },
            ],
            "testimony": deepcopy(evidence.get("testimony") or []),
            "documents": deepcopy(evidence.get("documents") or []),
        }

    def list_intake_questions(self) -> Dict[str, Any]:
        return {
            "questions": deepcopy(DEFAULT_INTAKE_QUESTIONS),
        }

    def list_claim_elements(self) -> Dict[str, Any]:
        return {
            "claim_elements": deepcopy(DEFAULT_CLAIM_ELEMENTS),
        }

    def _build_draft(
        self,
        state: Dict[str, Any],
        requested_relief: Optional[List[str]] = None,
        *,
        use_llm: bool = False,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config_path: Optional[str] = None,
        backend_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        answers = state.get("intake_answers") or {}
        existing_draft = state.get("draft") or {}
        review_snapshot = self._build_review(state)
        overview = dict(review_snapshot.get("overview") or {})
        evidence = dict(state.get("evidence") or {})
        filing_metadata = dict(state.get("filing_metadata") or {})
        testimony_items = list(evidence.get("testimony") or [])
        document_items = list(evidence.get("documents") or [])
        prioritized_document_items = sorted(
            document_items,
            key=lambda item: (-_evidence_priority(item), str(item.get("saved_at") or ""), str(item.get("title") or "")),
        )
        claim_type = _normalize_claim_type(state.get("claim_type"))
        claim_label = _claim_type_display_name(claim_type)
        plaintiff = _extract_person_name(
            filing_metadata.get("signature_plaintiff") or answers.get("party_name"),
            fallback="Plaintiff",
        )
        defendant = _extract_defendant_name(answers.get("opposing_party"), fallback="Defendant")
        caption_plaintiffs = str(filing_metadata.get("caption_plaintiffs") or "").strip() or plaintiff
        caption_defendants = str(filing_metadata.get("caption_defendants") or "").strip() or defendant
        mailing_address = str(filing_metadata.get("mailing_address") or "").strip() or "____________________"
        signature_role = str(filing_metadata.get("signature_role") or "").strip() or "Plaintiff, Pro Se"
        plaintiff_caption_label = (
            "Plaintiffs"
            if any(token in caption_plaintiffs for token in [",", " and "]) and caption_plaintiffs != plaintiff
            else "Plaintiff"
        )
        defendant_caption_label = (
            "Defendants"
            if any(token in caption_defendants for token in [",", " and "])
            else "Defendant"
        )
        is_plural_plaintiffs = plaintiff_caption_label == "Plaintiffs"
        is_plural_defendants = defendant_caption_label == "Defendants"
        plaintiff_party_label = "Plaintiffs" if is_plural_plaintiffs else "Plaintiff"
        defendant_party_label = "Defendants" if is_plural_defendants else "Defendant"
        plaintiff_party_object = "Plaintiffs" if is_plural_plaintiffs else "Plaintiff"
        plaintiff_party_have = "have" if is_plural_plaintiffs else "has"
        plaintiff_party_seek = "seek" if is_plural_plaintiffs else "seeks"
        plaintiff_party_repeat = "repeat and reallege" if is_plural_plaintiffs else "repeats and realleges"
        plaintiff_party_demand = "demand" if is_plural_plaintiffs else "demands"
        plaintiff_party_contend = "contend" if is_plural_plaintiffs else "contends"
        plaintiff_party_give = "give" if is_plural_plaintiffs else "gives"
        plaintiff_intro_name = caption_plaintiffs if is_plural_plaintiffs else plaintiff
        defendant_intro_name = caption_defendants if is_plural_defendants else defendant
        intro_alleges = "allege" if is_plural_plaintiffs else "alleges"
        intro_their = "their" if is_plural_plaintiffs else "their"
        defendant_be = "are" if is_plural_defendants else "is"
        timeline_input = _condense_timeline_text(answers.get("timeline"), "the events occurred close in time")
        protected_activity = _sentence_fragment(
            answers.get("protected_activity"),
            "engaged in protected activity",
        )
        pleading_activity = _pleading_activity_fragment(
            answers.get("protected_activity"),
            "engaging in protected activity",
        )
        adverse_action = _event_fragment(
            answers.get("adverse_action"),
            "suffered an adverse action",
        )
        timeline = _sentence_fragment(
            timeline_input,
            "the events occurred close in time",
        )
        harm = _sentence_fragment(
            answers.get("harm"),
            "suffered compensable harm",
        )
        relief = requested_relief or existing_draft.get("requested_relief") or [
            "Compensatory damages",
            "Back pay",
            "Injunctive relief",
        ]
        case_synopsis = self._build_case_synopsis(state)
        relief_lines = [f"{index}. {_formalize_relief_item(item)}." for index, item in enumerate(relief, start=1)]
        support_count = int(overview.get("supported_elements") or 0)
        missing_count = int(overview.get("missing_elements") or 0)
        evidence_count = len(testimony_items) + len(document_items)
        court_header = _court_header_line(answers.get("court_header"))
        document_exhibits = [
            {
                "label": _exhibit_label(index),
                "title": _evidence_display_title(item, kind="document"),
                "item": item,
            }
            for index, item in enumerate(prioritized_document_items[:3])
        ]
        testimony_reference_lines = _unique_preserve_order([
            f"{plaintiff_party_label} expect{'s' if not is_plural_plaintiffs else ''} to offer testimony presently identified as '{_evidence_display_title(item, kind='testimony')}' in support of the {_claim_element_label(item.get('claim_element_id')).lower()} element."
            for item in testimony_items[:3]
        ])
        document_reference_lines = _unique_preserve_order([
            (
                f"{exhibit['label']} ('{exhibit['title']}') presently supports the "
                f"{_claim_element_label(exhibit['item'].get('claim_element_id')).lower()} element. "
                f"{plaintiff_party_label} expect{'s' if not is_plural_plaintiffs else ''} to offer {exhibit['label'].lower()} in support of the "
                f"{_claim_element_label(exhibit['item'].get('claim_element_id')).lower()} element."
            )
            for exhibit in document_exhibits
        ])
        testimony_summary = "; ".join(_unique_preserve_order([
            _formal_evidence_summary_item(item, kind="testimony")
            for item in testimony_items[:3]
        ])) or "No witness or complainant testimony is presently identified"
        document_summary_items = _unique_preserve_order([
            (
                f"{exhibit['label']} - {exhibit['title']} ({_claim_element_label(exhibit['item'].get('claim_element_id')).strip() or 'Claim element'})"
                f"; {_formal_evidence_summary_item(exhibit['item'], kind='document')}"
            )
            for exhibit in document_exhibits
        ])
        document_summary = "; ".join(document_summary_items) or "No documentary exhibits are presently identified"
        exhibit_titles_lower = {
            _evidence_display_title(item, kind="document").lower()
            for item in prioritized_document_items
        }
        case_specific_evidence_notice: Optional[str] = None
        if {
            "chronology evidence matrix",
            "temporary cli session email evidence memo",
            "reasonable accommodation ocr memo",
        }.issubset(exhibit_titles_lower):
            case_specific_evidence_notice = (
                f"16. The current exhibit set specifically identifies a February 25 to February 26, 2026 written complaint and documentation-escalation thread, "
                "a March 19, 2026 voucher-reversal email, a March 20, 2026 accommodation-conditioned reissuance email, "
                "and a March 24, 2026 provider-supported accommodation-verification record."
            )
        complaint_heading = f"COMPLAINT FOR {claim_label.upper()}"
        nature_of_action = {
            "retaliation": (
                f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this retaliation complaint against {defendant_intro_name}. "
                f"This civil action arises from {defendant_intro_name}'s retaliatory response after {plaintiff_intro_name} {'engaged' if not is_plural_plaintiffs else 'engaged'} in protected activity, including {pleading_activity}."
            ),
            "employment_discrimination": (
                f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this employment discrimination complaint against {defendant_intro_name}. "
                f"This civil action arises from discriminatory workplace treatment, unequal terms or conditions, and resulting harm."
            ),
            "housing_discrimination": (
                f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this housing discrimination complaint against {defendant_intro_name}. "
                f"This civil action arises from discriminatory denial, limitation, interference, or retaliation affecting housing rights or benefits."
            ),
            "due_process_failure": (
                f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this due process complaint against {defendant_intro_name}. "
                f"This civil action arises from adverse action imposed without the notice, hearing, review, or procedural protections required by law."
            ),
            "consumer_protection": (
                f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this consumer protection complaint against {defendant_intro_name}. "
                f"This civil action arises from unfair, deceptive, fraudulent, or otherwise unlawful business practices that caused injury."
            ),
        }.get(
            claim_type,
            f"1. {plaintiff_intro_name} {'bring' if is_plural_plaintiffs else 'brings'} this {claim_label.lower()} complaint against {defendant_intro_name}. "
            f"This civil action arises from unlawful conduct that injured {plaintiff_intro_name}.",
        )
        relief_paragraph = {
            "retaliation": (
                f"2. {plaintiff_party_label} {plaintiff_party_seek} back pay, front pay or reinstatement, compensatory damages, attorney's fees and costs, "
                "equitable relief, and such further relief as may be just to remedy Defendant's retaliatory acts and the losses flowing from them."
            ),
            "employment_discrimination": (
                f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, equitable relief, and such further relief as may be just to remedy discriminatory employment practices, "
                f"restore lost opportunities, and address the harm caused when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse employment action')}."
            ),
            "housing_discrimination": (
                f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, equitable relief, and such further relief as may be just to remedy discriminatory housing practices, "
                "preserve housing stability, and address the housing-related harms caused by the challenged conduct."
            ),
            "due_process_failure": (
                f"2. {plaintiff_party_label} {plaintiff_party_seek} declaratory relief, equitable relief, damages, and such further relief as may be just to remedy the procedural deprivation "
                f"and the harm caused by the challenged action through which {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a deprivation without adequate process')}."
            ),
            "consumer_protection": (
                f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, restitution, equitable relief, and such further relief as may be just to remedy deceptive or unfair consumer practices "
                f"and the harm caused when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a consumer-facing injury')}."
            ),
        }.get(
            claim_type,
            f"2. {plaintiff_party_label} {plaintiff_party_seek} damages, equitable relief, and such further relief as may be just to remedy unlawful conduct and the harm caused when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse action')}.",
        )
        jurisdiction_paragraph = {
            "retaliation": (
                f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} retaliation for protected activity "
                "and seeks relief for materially adverse acts taken in response to that activity."
            ),
            "employment_discrimination": (
                f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} discriminatory employment practices, "
                "workplace bias, and related unlawful employment actions for which judicial relief is available."
            ),
            "housing_discrimination": (
                f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} discriminatory housing practices, "
                "interference with housing rights or benefits, and related misconduct for which judicial relief is available."
            ),
            "due_process_failure": (
                f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} deprivation without constitutionally "
                "or statutorily required notice, hearing, review, or other procedural protections."
            ),
            "consumer_protection": (
                f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} unfair, deceptive, or unlawful consumer-facing conduct "
                "for which damages, equitable relief, restitution, or related remedies may be awarded."
            ),
        }.get(
            claim_type,
            f"3. This Court has subject-matter jurisdiction over this action because {plaintiff_party_label} {intro_alleges} unlawful conduct for which judicial relief is available.",
        )
        venue_paragraph = {
            "housing_discrimination": (
                "4. Venue is proper in this District because the housing-related events, denial, interference, or threatened loss of housing benefits occurred in this forum and the resulting harm was felt here."
            ),
            "employment_discrimination": (
                "4. Venue is proper in this District because the workplace events, adverse employment decisions, and resulting economic harm occurred in or were directed into this forum."
            ),
            "consumer_protection": (
                "4. Venue is proper in this District because the transaction, deceptive practice, or resulting economic loss occurred in this forum or caused injury here."
            ),
        }.get(
            claim_type,
            "4. Venue is proper in this District because a substantial part of the events or omissions giving rise to these claims occurred in this forum and the resulting harm was felt here.",
        )
        party_paragraphs = {
            "retaliation": (
                f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} individual complainants who engaged in protected activity and {'were' if is_plural_plaintiffs else 'was'} thereafter harmed by the retaliatory conduct described below.",
                f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the party or parties from whom relief is sought and {defendant_be} responsible for the retaliatory actions alleged in this pleading.",
            ),
            "employment_discrimination": (
                f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the employee, applicant, or worker harmed by the discriminatory employment conduct described below.",
                f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the employer or responsible actor from whom relief is sought for the discriminatory employment actions alleged in this pleading.",
            ),
            "housing_discrimination": (
                (
                    f"5. {plaintiff_party_label} {plaintiff_intro_name} are housing applicants, tenants, residents, or persons seeking housing-related rights or benefits who were harmed by the discriminatory conduct described below."
                    if is_plural_plaintiffs
                    else f"5. {plaintiff_party_label} {plaintiff_intro_name} is the housing applicant, tenant, resident, or person seeking housing-related rights or benefits who was harmed by the discriminatory conduct described below."
                ),
                (
                    f"6. {defendant_party_label} {defendant_intro_name} are housing providers, landlords, authorities, managers, or responsible actors from whom relief is sought for the housing discrimination alleged in this pleading."
                    if is_plural_defendants
                    else f"6. {defendant_party_label} {defendant_intro_name} is the housing provider, landlord, authority, manager, or responsible actor from whom relief is sought for the housing discrimination alleged in this pleading."
                ),
            ),
            "due_process_failure": (
                f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the person or persons deprived of rights, benefits, or protected interests without adequate process.",
                f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the person or entity responsible for the challenged deprivation and the missing procedural safeguards alleged in this pleading.",
            ),
            "consumer_protection": (
                f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the consumer or injured person harmed by the deceptive, unfair, or unlawful conduct described below.",
                f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the seller, business, servicer, or responsible actor from whom relief is sought for the consumer-facing conduct alleged in this pleading.",
            ),
        }.get(
            claim_type,
            (
                f"5. {plaintiff_party_label} {plaintiff_intro_name} {'are' if is_plural_plaintiffs else 'is'} the person or persons harmed by the conduct described below.",
                f"6. {defendant_party_label} {defendant_intro_name} {defendant_be} the party or parties from whom relief is sought and {defendant_be} responsible for the conduct alleged in this pleading.",
            ),
        )
        factual_allegation_lines = {
            "retaliation": [
                f"7. {plaintiff_party_label} {'engaged' if not is_plural_plaintiffs else 'engaged'} in protected activity by {pleading_activity}.",
                "8. That protected activity constituted protected opposition, reporting, or participation activity under the governing anti-retaliation framework.",
                f"9. Within days of that protected activity, {defendant_party_label} took materially adverse action against {plaintiff_party_object} by {_adverse_action_clause(answers.get('adverse_action'), 'taking materially adverse action against Plaintiff')}.",
                f"10. The relevant chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The events occurred in close temporal proximity')}",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
            "employment_discrimination": [
                f"7. {plaintiff_party_label} {intro_alleges} facts showing discriminatory employment treatment, including protected conduct or circumstances such as {pleading_activity}.",
                f"8. {defendant_party_label} thereafter took or maintained adverse employment action by which {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse employment action')}.",
                f"9. The employment chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The relevant employment events occurred in close succession')}",
                "10. The present record supports an inference of discriminatory motive, disparate treatment, prohibited bias, retaliation, or other unlawful employment decision-making.",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
            "housing_discrimination": [
                f"7. {plaintiff_party_label} {intro_alleges} that {'they' if is_plural_plaintiffs else 'they'} sought, used, requested, or protected housing-related rights, accommodations, benefits, tenancy rights, or fair treatment, including {pleading_activity}.",
                f"8. {defendant_party_label} thereafter denied, burdened, interfered with, or threatened housing-related rights or benefits through conduct including {_sentence_fragment(answers.get('adverse_action'), 'a housing-related deprivation')}.",
                f"9. The housing-related chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The housing-related events occurred in close succession')}",
                f"10. The present record supports an inference that {defendant_party_label} acted in a discriminatory manner, interfered with protected housing rights, or retaliated in connection with protected housing activity.",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {'suffered' if not is_plural_plaintiffs else 'suffered'} harm including {_sentence_fragment(answers.get('harm'), 'compensable harm')}.",
            ],
            "due_process_failure": [
                f"7. {plaintiff_party_label} {intro_alleges} that {defendant_party_label} imposed or maintained a deprivation affecting protected rights, interests, status, benefits, or property.",
                f"8. The challenged action is that {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a deprivation without adequate process')}.",
                f"9. The chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The challenged events occurred in close succession')}",
                f"10. {plaintiff_party_label} {intro_alleges} that the deprivation occurred without adequate notice, hearing, review, appeal, or other required procedural protection.",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
            "consumer_protection": [
                f"7. {plaintiff_party_label} {intro_alleges} that {defendant_party_label} engaged in deceptive, misleading, unfair, or otherwise unlawful consumer-facing conduct.",
                f"8. That conduct included or resulted in adverse action or consequences when {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered a consumer-facing injury')}.",
                f"9. The chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The relevant consumer-facing events occurred in close succession')}",
                f"10. {plaintiff_party_label} {intro_alleges} that the challenged conduct caused consumer harm, financial loss, or other compensable injury in a transactional or service context.",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
        }.get(
            claim_type,
            [
                f"7. {plaintiff_party_label} {intro_alleges} conduct or circumstances including {pleading_activity}.",
                f"8. {defendant_party_label} engaged in conduct through which {plaintiff_party_label} {_sentence_fragment(answers.get('adverse_action'), 'suffered an adverse action')}.",
                f"9. The chronology is as follows: {_pleading_timeline_sentence(timeline_input, 'The relevant events occurred in close succession')}",
                f"10. {plaintiff_party_label} {intro_alleges} facts supporting a plausible claim for relief.",
                f"11. As a direct and proximate result of {defendant_party_label}' conduct, {plaintiff_party_label} {_sentence_fragment(answers.get('harm'), 'suffered compensable harm')}.",
            ],
        )
        count_heading = {
            "retaliation": "COUNT I - RETALIATION",
            "employment_discrimination": "COUNT I - EMPLOYMENT DISCRIMINATION",
            "housing_discrimination": "COUNT I - HOUSING DISCRIMINATION",
            "due_process_failure": "COUNT I - DUE PROCESS VIOLATION",
            "consumer_protection": "COUNT I - CONSUMER PROTECTION",
        }.get(claim_type, f"COUNT I - {claim_label.upper()}")
        claim_paragraphs = {
            "retaliation": [
                f"{plaintiff_party_label} engaged in protected activity by {pleading_activity}, and {defendant_party_label} knew or should have known of that protected conduct.",
                f"{defendant_party_label} thereafter subjected {plaintiff_party_object} to materially adverse action by {_adverse_action_clause(answers.get('adverse_action'), 'taking materially adverse action against Plaintiff')}, under circumstances supporting a causal inference of retaliation.",
                f"The close temporal proximity, {defendant_party_label}' knowledge of the protected activity, the evidentiary record, and the resulting harm plausibly support a retaliation claim and entitle {plaintiff_party_object} to relief.",
            ],
            "employment_discrimination": [
                f"{plaintiff_party_label} {'were' if is_plural_plaintiffs else 'was'} subjected to adverse employment treatment described as {adverse_action}, in a manner that was discriminatory, disparate, or otherwise unlawful.",
                "The pleaded facts support an inference that Defendant's conduct was motivated by unlawful bias, protected status, protected conduct, or a prohibited employment practice.",
                "The evidentiary record and resulting harm support a plausible employment discrimination claim.",
            ],
            "housing_discrimination": [
                f"{defendant_party_label} denied, limited, burdened, or interfered with housing-related rights, opportunities, services, or benefits through conduct described as {adverse_action}.",
                f"The pleaded facts support an inference that {defendant_party_label} acted in a discriminatory manner or retaliated in connection with protected housing activity, status, or rights.",
                "The evidentiary record and resulting harm support a plausible housing discrimination claim.",
            ],
            "due_process_failure": [
                "Defendant imposed or maintained adverse consequences without the notice, review, hearing, or procedural protections required by law.",
                f"The resulting deprivation included challenged action described as {adverse_action} and related harms without adequate procedural safeguards.",
                "The pleaded facts and evidentiary record support a plausible due process claim.",
            ],
            "consumer_protection": [
                "Defendant engaged in unfair, deceptive, misleading, or unlawful conduct in connection with a consumer transaction or obligation.",
                f"That conduct resulted in adverse action or consequences when Plaintiff {_sentence_fragment(answers.get('adverse_action'), 'suffered a consumer-facing injury')} and caused economic or other compensable harm, including {_sentence_fragment(answers.get('harm'), 'compensable harm')}.",
                "The pleaded facts and evidentiary record support a plausible consumer protection claim.",
            ],
        }.get(
            claim_type,
            [
                "Defendant engaged in unlawful conduct causing harm to Plaintiff.",
                "The pleaded facts support a plausible claim for relief.",
                "The evidentiary record and resulting harm warrant judicial relief.",
            ],
        )
        evidentiary_lines: List[str] = [
            (
                f"12. {plaintiff_party_label} presently {'rely' if is_plural_plaintiffs else 'relies'} on {evidence_count} identified evidentiary items. The witness proof currently identified includes: {testimony_summary}."
                if testimony_items
                else f"12. {plaintiff_party_label} presently {'rely' if is_plural_plaintiffs else 'relies'} on the evidentiary materials identified below and anticipate{'' if is_plural_plaintiffs else 's'} that testimonial proof may be supplemented through discovery, amendment, or sworn declarations."
            ),
            (
                f"13. {plaintiff_party_label} presently {'identify' if is_plural_plaintiffs else 'identifies'} the following documents, exhibits, or records in support of this pleading: {document_summary}."
                if document_items
                else f"13. {plaintiff_party_label} {plaintiff_party_have} not yet attached documentary exhibits to this export, but preserve{'' if is_plural_plaintiffs else 's'} the right to supplement the pleading with records, correspondence, or other supporting materials."
            ),
            (
                f"14. Based on the information presently available, {plaintiff_party_label} {plaintiff_party_contend} that the evidentiary record presently supports {support_count} core claim elements "
                f"and that {missing_count} areas, if any, may be further corroborated through discovery, amendment, or additional evidentiary development."
            ),
            (
                f"15. {plaintiff_party_label} {plaintiff_party_give} notice that the identified testimony, documentary exhibits, and chronology materials constitute part of the evidentiary basis for this pleading "
                "and may be supplemented, authenticated, or amended as discovery proceeds."
            ),
        ]
        if case_specific_evidence_notice:
            evidentiary_lines.append(case_specific_evidence_notice)
        extra_evidence_start = 16 + (1 if case_specific_evidence_notice else 0)
        extra_evidence_lines = (testimony_reference_lines + document_reference_lines)[:2]
        evidentiary_lines.extend(
            f"{extra_evidence_start + index}. {line}"
            for index, line in enumerate(extra_evidence_lines)
        )
        claim_intro_paragraph = extra_evidence_start + len(extra_evidence_lines)
        claim_detail_start = claim_intro_paragraph + 1
        body = "\n\n".join(
            [
                "IN THE UNITED STATES DISTRICT COURT",
                court_header,
                "",
                f"{caption_plaintiffs}, {plaintiff_caption_label},",
                "v.",
                f"{caption_defendants}, {defendant_caption_label}.",
                "",
                "Civil Action No. ________________",
                complaint_heading,
                "JURY TRIAL DEMANDED",
                "",
                (
                    f"{plaintiff_party_label} {plaintiff_intro_name}, proceeding pro se, {intro_alleges} upon personal knowledge as to "
                    f"{intro_their} own acts and upon information and belief as to all other matters as follows:"
                ),
                "",
                "NATURE OF THE ACTION",
                nature_of_action,
                relief_paragraph,
                "",
                "JURISDICTION AND VENUE",
                jurisdiction_paragraph,
                venue_paragraph,
                "",
                "PARTIES",
                party_paragraphs[0],
                party_paragraphs[1],
                "",
                "FACTUAL ALLEGATIONS",
                *factual_allegation_lines,
                "",
                "EVIDENTIARY SUPPORT AND NOTICE",
                *evidentiary_lines,
                "",
                "CLAIM FOR RELIEF",
                count_heading,
                f"{claim_intro_paragraph}. {plaintiff_intro_name} {plaintiff_party_repeat} the preceding paragraphs as if fully set forth herein.",
                *[f"{claim_detail_start + index}. {line}" for index, line in enumerate(claim_paragraphs)],
                f"{claim_detail_start + 3}. {plaintiff_party_label} {plaintiff_party_have} sustained damages and losses including {_sentence_fragment(answers.get('harm'), 'compensable harm')}.",
                (
                    f"{claim_detail_start + 4}. As a direct and proximate result of Defendant's retaliatory conduct, {plaintiff_party_label} {'are' if is_plural_plaintiffs else 'is'} entitled to recover damages, equitable relief, fees and costs where available, and such further relief as the Court deems just and proper."
                    if claim_type == "retaliation"
                    else f"{claim_detail_start + 4}. {defendant_party_label}' acts were intentional, knowing, reckless, retaliatory, discriminatory, deceptive, or otherwise unlawful under the governing claim theory."
                ),
                "",
                "PRAYER FOR RELIEF",
                (
                    f"Wherefore, {plaintiff_party_label} respectfully {'request' if is_plural_plaintiffs else 'requests'} judgment against {defendant_party_label} on the retaliation claim alleged herein and {'seek' if is_plural_plaintiffs else 'seeks'} the following relief:"
                    if claim_type == "retaliation"
                    else f"Wherefore, {plaintiff_party_label} {'request' if is_plural_plaintiffs else 'requests'} judgment against {defendant_party_label} and the following relief:"
                ),
                "\n".join(relief_lines),
                "",
                "JURY DEMAND",
                f"{plaintiff_party_label} {plaintiff_party_demand} a trial by jury on all issues so triable.",
                "",
                "SIGNATURE BLOCK",
                f"Dated: ____________________",
                "",
                "Respectfully submitted,",
                "",
                f"{plaintiff}",
                signature_role,
                f"Address: {mailing_address}",
                "Telephone: ____________________",
                "Email: ____________________",
            ]
        )
        draft = {
            "title": f"{caption_plaintiffs} v. {caption_defendants} {claim_label} Complaint",
            "requested_relief": relief,
            "case_synopsis": case_synopsis,
            "claim_type": claim_type,
            "body": body,
            "generated_at": _utc_now(),
            "review_snapshot": review_snapshot,
            "draft_strategy": "template",
        }
        if use_llm:
            self._last_draft_refinement_error = None
            resolved_backends = _resolve_llm_draft_backend_candidates(provider, model)
            attempted_providers: List[str] = []
            for resolved_backend in resolved_backends:
                provider_name = str(resolved_backend["provider"] or "").strip()
                if provider_name:
                    attempted_providers.append(provider_name)
                refined_draft = self._refine_draft_with_llm_router(
                    state,
                    draft,
                    provider=resolved_backend["provider"],
                    model=resolved_backend["model"],
                    requested_provider=resolved_backend["requested_provider"],
                    requested_model=resolved_backend["requested_model"],
                    config_path=config_path,
                    backend_id=backend_id,
                )
                if refined_draft:
                    if len(attempted_providers) > 1:
                        refined_draft["draft_backend_fallback_chain"] = attempted_providers
                    return refined_draft
            if self._last_draft_refinement_error:
                if attempted_providers:
                    draft["draft_backend_fallback_chain"] = attempted_providers
                draft["draft_fallback_reason"] = self._last_draft_refinement_error
        return draft

    def _build_case_synopsis(self, state: Dict[str, Any]) -> str:
        custom_synopsis = str(state.get("case_synopsis") or "").strip()
        if custom_synopsis:
            return custom_synopsis
        answers = state.get("intake_answers") or {}
        matrix = self._support_matrix(state)
        supported_elements = len([item for item in matrix if item.get("supported")])
        missing_elements = len([item for item in matrix if not item.get("supported")])
        evidence = state.get("evidence") or {}
        claim_type = str(state.get("claim_type") or "retaliation").replace("_", " ")
        party_name = _extract_person_name(answers.get("party_name"), fallback="The complainant")
        opposing_party = _extract_defendant_name(answers.get("opposing_party"), fallback="the opposing party")
        protected_activity = answers.get("protected_activity") or "an identified protected activity"
        adverse_action = answers.get("adverse_action") or "an adverse action"
        harm = answers.get("harm") or "described harm"
        timeline = _condense_timeline_text(answers.get("timeline"), "a still-developing timeline")
        evidence_count = len(evidence.get("testimony") or []) + len(evidence.get("documents") or [])
        return (
            f"{party_name} is pursuing a {claim_type} complaint against {opposing_party}. "
            f"The current theory is that {party_name} {protected_activity}, then experienced {adverse_action}. "
            f"The reported harm is {harm}. Timeline posture: {timeline}. "
            f"Current support posture: {supported_elements} supported elements, "
            f"{missing_elements} open gaps, {evidence_count} saved evidence items."
        )

    def _build_formal_complaint_generation_prompt(
        self,
        state: Dict[str, Any],
        base_draft: Dict[str, Any],
    ) -> str:
        answers = dict(state.get("intake_answers") or {})
        evidence = dict(state.get("evidence") or {})
        review_snapshot = dict(base_draft.get("review_snapshot") or self._build_review(state) or {})
        support_matrix = [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "supported": item.get("supported"),
                "support_count": item.get("support_count"),
            }
            for item in list(review_snapshot.get("support_matrix") or [])
        ]
        payload = {
            "claim_type": base_draft.get("claim_type") or _normalize_claim_type(state.get("claim_type")),
            "claim_label": _claim_type_display_name(base_draft.get("claim_type") or state.get("claim_type")),
            "case_synopsis": base_draft.get("case_synopsis") or self._build_case_synopsis(state),
            "intake_answers": answers,
            "requested_relief": list(base_draft.get("requested_relief") or []),
            "testimony": list(evidence.get("testimony") or [])[:4],
            "documents": list(evidence.get("documents") or [])[:4],
            "support_matrix": support_matrix,
            "base_draft": str(base_draft.get("body") or "")[:12000],
        }
        markers = "\n".join(f"- {marker}" for marker in _required_formal_complaint_markers())
        allegation_lines = "\n".join(
            f"- {line}" for line in _claim_type_required_allegations(payload["claim_type"])
        )
        example_snippet = _claim_type_formal_example_snippet(payload["claim_type"])
        preferred_count_heading = _claim_type_count_heading(payload["claim_type"])
        preferred_heading = f"COMPLAINT FOR {payload['claim_label'].upper()}"
        return (
            "You are revising a generated complaint so it reads like a formal legal complaint rather than a workflow summary.\n"
            "Use only the facts already present in the complaint record. Do not invent statutes, parties, dates, courts, judges, addresses, or evidence.\n"
            "Keep the output in plain text with a litigation-style caption, numbered factual paragraphs, a separate count heading, a prayer for relief, and a signature block.\n"
            "Number the factual allegations as pleading paragraphs like '1. ...', '2. ...', and keep that numbering visible in the final complaint body.\n"
            "Do not write a memo, case summary, product explanation, workflow note, JSON explanation, SDK explanation, or support-matrix summary. Write the text like a filed civil complaint.\n"
            "Preserve the requested relief unless the record plainly requires a tighter phrasing.\n"
            f"Claim-specific filing guidance: {_claim_type_filing_guidance(payload['claim_type'])}\n"
            f"Preferred complaint heading: {preferred_heading}\n"
            f"Preferred count heading: {preferred_count_heading}\n"
            "The complaint must expressly allege all of the following:\n"
            f"{allegation_lines}\n"
            "Match the tone and paragraph style of this example snippet for the selected claim type:\n"
            f"{example_snippet}\n"
            "Retain these exact section headings in the body:\n"
            f"{markers}\n\n"
            "Follow this pleading skeleton and keep the headings exactly as written:\n"
            "IN THE UNITED STATES DISTRICT COURT\n"
            "FOR THE APPROPRIATE JUDICIAL DISTRICT\n\n"
            "[Plaintiff caption]\n"
            "Civil Action No. ________________\n"
            f"{preferred_heading}\n"
            "JURY TRIAL DEMANDED\n"
            "NATURE OF THE ACTION\n"
            "JURISDICTION AND VENUE\n"
            "PARTIES\n"
            "FACTUAL ALLEGATIONS\n"
            "EVIDENTIARY SUPPORT AND NOTICE\n"
            "CLAIM FOR RELIEF\n"
            f"{preferred_count_heading}\n"
            "PRAYER FOR RELIEF\n"
            "JURY DEMAND\n"
            "SIGNATURE BLOCK\n\n"
            "Return strict JSON with this shape:\n"
            "{\n"
            '  "title": "draft title",\n'
            '  "body": "full complaint text",\n'
            '  "requested_relief": ["item 1", "item 2"]\n'
            "}\n\n"
            "Complaint record:\n"
            f"{json.dumps(payload, indent=2, sort_keys=True)}\n"
        )

    def _refine_draft_with_llm_router(
        self,
        state: Dict[str, Any],
        base_draft: Dict[str, Any],
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        requested_provider: Optional[str] = None,
        requested_model: Optional[str] = None,
        config_path: Optional[str] = None,
        backend_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        helpers = _privacy_helpers()
        case_id = _state_case_id(state, str(state.get("user_id") or DEFAULT_USER_ID))
        privacy_context = helpers["build_complaint_privacy_context"](
            state.get("privacy_policy"),
            user_id=str(state.get("user_id") or DEFAULT_USER_ID),
            case_id=case_id,
            data_class="drafts_proofs",
        )
        from integrations.ipfs_datasets.llm import _privacy_context_block_reason

        privacy_block = _privacy_context_block_reason(
            privacy_context,
            provider=provider,
            model_name=model,
        )
        if privacy_block:
            self._last_draft_refinement_error = privacy_block
            return None
        try:
            from backends import LLMRouterBackend
            from .ui_review import _load_backend_kwargs

            backend_kwargs = _load_backend_kwargs(config_path, backend_id)
            backend_kwargs["id"] = backend_id or "complaint-draft"
            if provider:
                backend_kwargs["provider"] = provider
            if model:
                backend_kwargs["model"] = model
            backend_kwargs["complaint_privacy_context"] = privacy_context
            backend = LLMRouterBackend(**backend_kwargs)
            prompt = self._build_formal_complaint_generation_prompt(state, base_draft)
            raw_response = self._invoke_llm_draft_backend_with_timeout(backend, prompt)
        except Exception:
            self._last_draft_refinement_error = "private_generation_failed"
            return None

        parsed = _parse_json_object(raw_response)
        llm_body = str(parsed.get("body") or "").strip()
        if not llm_body:
            raw_text = _strip_code_fences(raw_response)
            if _has_required_formal_complaint_markers(raw_text) or _looks_like_formal_complaint_candidate(raw_text):
                llm_body = raw_text
        llm_body, normalization_notes = _normalize_llm_complaint_body(
            llm_body,
            base_draft.get("claim_type") or state.get("claim_type"),
        )
        validation_issues = _formal_complaint_validation_issues(
            llm_body,
            base_draft.get("claim_type") or state.get("claim_type"),
        )
        if validation_issues:
            self._last_draft_refinement_error = "; ".join(validation_issues[:3])
            return None

        requested_relief = [
            str(item).strip()
            for item in list(parsed.get("requested_relief") or base_draft.get("requested_relief") or [])
            if str(item).strip()
        ]
        backend_metadata = dict(getattr(backend, "last_result_metadata", {}) or {})
        effective_provider = str(
            backend_metadata.get("effective_provider_name")
            or backend_metadata.get("provider_name")
            or getattr(backend, "provider", provider)
            or ""
        ).strip() or None
        effective_model = str(
            backend_metadata.get("effective_model_name")
            or backend_metadata.get("model_name")
            or getattr(backend, "model", model)
            or ""
        ).strip() or None
        return {
            **deepcopy(base_draft),
            "title": str(parsed.get("title") or base_draft.get("title") or "Complaint").strip(),
            "body": llm_body,
            "requested_relief": requested_relief or list(base_draft.get("requested_relief") or []),
            "draft_strategy": "llm_router",
            "draft_backend": {
                "id": getattr(backend, "id", backend_id or "complaint-draft"),
                "provider": effective_provider,
                "model": effective_model,
                "requested_provider": str(requested_provider or "").strip() or None,
                "requested_model": str(requested_model or "").strip() or None,
            },
            "draft_normalizations": normalization_notes,
        }

    def _invoke_llm_draft_backend_with_timeout(self, backend: Any, prompt: str) -> str:
        provider_name = str(getattr(backend, "provider", "") or "").strip().lower() or None
        timeout_seconds = _llm_draft_timeout_for_provider(provider_name)
        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, BaseException] = {}

        def _run_backend() -> None:
            try:
                result_holder["value"] = backend(prompt)
            except BaseException as exc:  # Preserve backend failures for the caller.
                error_holder["error"] = exc

        worker = threading.Thread(target=_run_backend, name="complaint-llm-draft", daemon=True)
        worker.start()
        worker.join(timeout_seconds)
        if worker.is_alive():
            label = provider_name or "default"
            raise TimeoutError(f"llm_router draft refinement timed out after {timeout_seconds}s ({label})")
        if "error" in error_holder:
            raise error_holder["error"]
        return str(result_holder.get("value") or "")

    def _build_packet_markdown(self, packet: Dict[str, Any]) -> str:
        draft = dict(packet.get("draft") or {})
        review = dict(packet.get("review") or {})
        overview = dict(review.get("overview") or {})
        evidence = dict(packet.get("evidence") or {})
        testimony = list(evidence.get("testimony") or [])
        documents = list(evidence.get("documents") or [])
        requested_relief = list(draft.get("requested_relief") or [])
        question_lines = [
            f"- **{item.get('label') or item.get('id') or 'Question'}:** {item.get('answer') or 'Not answered'}"
            for item in list(packet.get("questions") or [])
        ]
        testimony_lines = [
            f"- **{item.get('title') or 'Testimony'}** ({item.get('claim_element_id') or 'unmapped'}): {item.get('content') or ''}".strip()
            for item in testimony
        ]
        document_lines = [
            f"- **{item.get('title') or 'Document'}** ({item.get('claim_element_id') or 'unmapped'}): {item.get('content') or ''}".strip()
            for item in documents
        ]
        relief_lines = [f"- {item}" for item in requested_relief]
        sections = [
            draft.get("body") or "No complaint body available.",
            "",
            "APPENDIX A - CASE SYNOPSIS",
            packet.get("case_synopsis") or "No case synopsis recorded.",
            "",
            "APPENDIX B - REQUESTED RELIEF CHECKLIST",
            "\n".join(relief_lines) if relief_lines else "- No requested relief recorded.",
            "",
            "APPENDIX C - INTAKE ANSWERS",
            "\n".join(question_lines) if question_lines else "- No intake answers recorded.",
            "",
            "APPENDIX D - EVIDENCE SUMMARY",
            "### Testimony",
            "\n".join(testimony_lines) if testimony_lines else "- No testimony saved.",
            "",
            "### Documents",
            "\n".join(document_lines) if document_lines else "- No documents saved.",
            "",
            "APPENDIX E - REVIEW OVERVIEW",
            f"- Supported elements: {overview.get('supported_elements') or 0}",
            f"- Missing elements: {overview.get('missing_elements') or 0}",
            f"- Testimony items: {overview.get('testimony_items') or 0}",
            f"- Document items: {overview.get('document_items') or 0}",
            "",
            "APPENDIX F - EXPORT METADATA",
            f"- Claim type: {packet.get('claim_type') or 'retaliation'}",
            f"- User ID: {packet.get('user_id') or 'unknown'}",
            f"- Exported at: {packet.get('exported_at') or _utc_now()}",
        ]
        return "\n".join(sections).strip() + "\n"

    def _build_complaint_export_markdown(self, packet: Dict[str, Any]) -> str:
        draft = dict(packet.get("draft") or {})
        body = str(draft.get("body") or "").strip()
        return f"{body}\n" if body else "No complaint body available.\n"

    def _escape_pdf_text(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def _build_packet_pdf_bytes(self, packet: Dict[str, Any], markdown_text: str) -> bytes:
        title = str((packet.get("draft") or {}).get("title") or packet.get("title") or "Complaint Packet")
        lines = [title, ""] + [line[:100] for line in markdown_text.splitlines() if line.strip()]
        lines = lines[:38]
        content_lines = ["BT", "/F1 12 Tf", "72 780 Td"]
        for index, line in enumerate(lines):
            safe_line = self._escape_pdf_text(line)
            if index == 0:
                content_lines.append(f"({safe_line}) Tj")
            else:
                content_lines.append(f"0 -18 Td ({safe_line}) Tj")
        content_lines.append("ET")
        content_stream = "\n".join(content_lines).encode("utf-8")

        objects = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
            f"5 0 obj << /Length {len(content_stream)} >> stream\n".encode("utf-8") + content_stream + b"\nendstream endobj\n",
        ]

        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for obj in objects:
            offsets.append(len(output))
            output.extend(obj)
        xref_start = len(output)
        output.extend(f"xref\n0 {len(offsets)}\n".encode("utf-8"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
        output.extend(
            f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("utf-8")
        )
        return bytes(output)

    def _build_packet_docx_bytes(self, packet: Dict[str, Any], markdown_text: str) -> bytes:
        title = str((packet.get("draft") or {}).get("title") or packet.get("title") or "Complaint Packet")
        paragraphs = [title, ""] + str(markdown_text or "").replace("\r\n", "\n").split("\n")

        def _paragraph_xml(text: str) -> str:
            if not str(text or ""):
                return "<w:p/>"
            return (
                "<w:p><w:r><w:t xml:space=\"preserve\">"
                f"{escape(str(text))}"
                "</w:t></w:r></w:p>"
            )

        document_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
            "<w:body>"
            f"{''.join(_paragraph_xml(item) for item in paragraphs)}"
            "<w:sectPr><w:pgSz w:w=\"12240\" w:h=\"15840\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/></w:sectPr>"
            "</w:body></w:document>"
        )
        content_types_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
            "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
            "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
            "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
            "<Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/>"
            "<Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/>"
            "</Types>"
        )
        root_rels_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>"
            "<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/>"
            "<Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/>"
            "</Relationships>"
        )
        app_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\">"
            "<Application>Complaint Workspace</Application>"
            "</Properties>"
        )
        core_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\">"
            f"<dc:title>{escape(title)}</dc:title>"
            "<dc:creator>Complaint Workspace</dc:creator>"
            "</cp:coreProperties>"
        )
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types_xml)
            archive.writestr("_rels/.rels", root_rels_xml)
            archive.writestr("docProps/app.xml", app_xml)
            archive.writestr("docProps/core.xml", core_xml)
            archive.writestr("word/document.xml", document_xml)
        return buffer.getvalue()

    def _build_export_artifacts(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        draft = dict(packet.get("draft") or {})
        filename_root = _slugify_filename(draft.get("title") or packet.get("title") or "complaint-packet")
        markdown_text = self._build_complaint_export_markdown(packet)
        pdf_bytes = self._build_packet_pdf_bytes(packet, markdown_text)
        docx_bytes = self._build_packet_docx_bytes(packet, markdown_text)
        json_text = json.dumps(packet, indent=2, sort_keys=True)
        return {
            "json": {
                "filename": f"{filename_root}.json",
                "content_type": "application/json",
                "size_bytes": len(json_text.encode("utf-8")),
            },
            "markdown": {
                "filename": f"{filename_root}.md",
                "content_type": "text/markdown",
                "size_bytes": len(markdown_text.encode("utf-8")),
                "content": markdown_text,
                "excerpt": markdown_text[:2000],
            },
            "docx": {
                "filename": f"{filename_root}.docx",
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size_bytes": len(docx_bytes),
            },
            "pdf": {
                "filename": f"{filename_root}.pdf",
                "content_type": "application/pdf",
                "size_bytes": len(pdf_bytes),
                "header_b64": b64encode(pdf_bytes[:32]).decode("ascii"),
            },
        }

    def get_session(self, user_id: Optional[str] = None, case_id: Optional[str] = None) -> Dict[str, Any]:
        resolved = self._resolve_user_id(user_id)

        def _run() -> Dict[str, Any]:
            self._check_access(resolved, ability="read", case_id=case_id)
            return self.request_handlers.get_session(resolved)

        if case_id is None:
            return _run()
        with _workspace_reference_scope(case_id=case_id):
            return _run()

    def build_mediator_prompt(self, user_id: Optional[str]) -> Dict[str, Any]:
        session = self.get_session(user_id)
        review = session["review"]
        support_matrix = list(review.get("support_matrix") or [])
        first_gap = next((item for item in support_matrix if not item.get("supported")), None)
        synopsis = session["case_synopsis"]
        gap_focus = (
            f"Focus especially on clarifying {str(first_gap.get('label') or '').lower()} and what proof could corroborate it."
            if first_gap
            else "Focus on sharpening the strongest testimony, identifying corroboration, and confirming the cleanest sequence of events."
        )
        prefill_message = (
            f"{synopsis}\n\n"
            "Mediator, help turn this into testimony-ready narrative for the complaint record. "
            "Ask the single most useful next follow-up question, keep the tone calm, and explain what support would strengthen the case. "
            f"{gap_focus}"
        )
        return {
            "user_id": session["session"]["user_id"],
            "case_synopsis": synopsis,
            "target_gap": deepcopy(first_gap) if first_gap else None,
            "prefill_message": prefill_message,
            "return_target_tab": "review",
        }

    def get_complaint_readiness(self, user_id: Optional[str]) -> Dict[str, Any]:
        session = self.get_session(user_id)
        review = session["review"]
        overview = dict(review.get("overview") or {})
        current_session = dict(session.get("session") or {})
        questions = list(session.get("questions") or [])
        answered_count = len([item for item in questions if item.get("is_answered")])
        total_questions = len(questions)
        supported_elements = int(overview.get("supported_elements") or 0)
        missing_elements = int(overview.get("missing_elements") or 0)
        evidence_count = int(overview.get("testimony_items") or 0) + int(overview.get("document_items") or 0)
        current_draft = current_session.get("draft")

        score = 10
        if total_questions > 0:
            score += round((answered_count / total_questions) * 35)
        score += round((supported_elements / max(supported_elements + missing_elements, 1)) * 35)
        if evidence_count > 0:
            score += min(12, evidence_count * 4)
        if current_draft:
            score += 12
        score = max(0, min(100, score))

        verdict = "Not ready to draft"
        detail = "Finish intake and add support before relying on generated complaint text."
        recommended_route = "/workspace"
        recommended_action = "Continue the guided complaint workflow to complete intake and collect support."
        if current_draft:
            verdict = "Draft in progress"
            detail = (
                "A complaint draft already exists. Compare it against the supported facts, requested relief, "
                "and any remaining proof gaps before treating it as filing-ready."
            )
            recommended_route = "/document"
            recommended_action = "Refine the existing draft and reconcile it with the support review."
        elif total_questions > 0 and answered_count == total_questions and missing_elements == 0 and evidence_count > 0:
            verdict = "Ready for first draft"
            detail = "The intake record and support posture are coherent enough to generate a first complaint draft."
            recommended_route = "/document"
            recommended_action = "Generate the first complaint draft from the current record."
        elif answered_count > 0:
            verdict = "Still building the record"
            detail = (
                f"{missing_elements} claim elements still need support and "
                f"{max(total_questions - answered_count, 0)} intake answers may still be missing."
            )
            recommended_route = "/claim-support-review" if missing_elements > 0 else "/workspace"
            recommended_action = (
                "Review support gaps and attach stronger evidence before relying on generated complaint language."
            )

        return {
            "user_id": current_session.get("user_id"),
            "score": score,
            "verdict": verdict,
            "detail": detail,
            "recommended_route": recommended_route,
            "recommended_action": recommended_action,
            "answered_questions": answered_count,
            "total_questions": total_questions,
            "supported_elements": supported_elements,
            "missing_elements": missing_elements,
            "evidence_count": evidence_count,
            "has_draft": bool(current_draft),
        }

    def _summarize_ui_readiness_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        review = dict((result or {}).get("review") or {})
        complaint_journey = dict(review.get("complaint_journey") or (result or {}).get("complaint_journey") or {})
        critic_review = dict(review.get("critic_review") or (result or {}).get("critic_review") or {})
        actor_path_breaks = list(review.get("actor_path_breaks") or (result or {}).get("actor_path_breaks") or [])
        broken_controls = list(review.get("broken_controls") or (result or {}).get("broken_controls") or [])
        issues = list(review.get("issues") or (result or {}).get("issues") or [])
        recommended_changes = list(review.get("recommended_changes") or (result or {}).get("recommended_changes") or [])
        playwright_followups = list(review.get("playwright_followups") or (result or {}).get("playwright_followups") or [])
        screenshot_findings = list(review.get("screenshot_findings") or (result or {}).get("screenshot_findings") or [])
        optimization_targets = list(review.get("optimization_targets") or (result or {}).get("optimization_targets") or [])
        stage_findings = dict(review.get("stage_findings") or (result or {}).get("stage_findings") or {})
        carry_forward_assessment = dict(
            review.get("carry_forward_assessment") or (result or {}).get("carry_forward_assessment") or {}
        )
        release_blockers = list(complaint_journey.get("release_blockers") or [])
        acceptance_checks = list(critic_review.get("acceptance_checks") or [])
        tested_stages = list(complaint_journey.get("tested_stages") or [])
        sdk_invocations = list(complaint_journey.get("sdk_tool_invocations") or [])

        severity_counts = {"high": 0, "medium": 0, "low": 0}
        for item in issues:
            severity = str((item or {}).get("severity") or "").strip().lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        score = 100
        score -= len(release_blockers) * 14
        score -= len(actor_path_breaks) * 9
        score -= len(broken_controls) * 8
        score -= severity_counts["high"] * 12
        score -= severity_counts["medium"] * 6
        score -= severity_counts["low"] * 3
        critic_verdict = str(critic_review.get("verdict") or "warning").strip().lower()
        if critic_verdict == "fail":
            score -= 25
        elif critic_verdict == "warning":
            score -= 10
        if len(tested_stages) >= 6:
            score += 4
        if len(sdk_invocations) >= 2:
            score += 4
        if len(acceptance_checks) >= 3:
            score += 4
        score = max(0, min(100, score))

        verdict = "Needs repair"
        if score >= 85 and not release_blockers and critic_verdict != "fail":
            verdict = "Client-safe"
        elif score < 65 or len(release_blockers) > 1 or critic_verdict == "fail":
            verdict = "Do not send to clients yet"

        summary_text = str(
            (result or {}).get("latest_review")
            or review.get("summary")
            or (result or {}).get("summary")
            or ""
        ).strip()

        return {
            "score": score,
            "verdict": verdict,
            "critic_verdict": critic_verdict or "warning",
            "release_blockers": release_blockers,
            "acceptance_checks": acceptance_checks,
            "tested_stages": tested_stages,
            "sdk_invocations": sdk_invocations,
            "actor_path_breaks": actor_path_breaks,
            "broken_controls": broken_controls,
            "issues": issues,
            "recommended_changes": recommended_changes,
            "playwright_followups": playwright_followups,
            "stage_findings": stage_findings,
            "screenshot_findings": screenshot_findings,
            "optimization_targets": optimization_targets,
            "carry_forward_assessment": carry_forward_assessment,
            "issue_counts": severity_counts,
            "summary": summary_text,
            "workflow_type": str((result or {}).get("workflow_type") or (result or {}).get("backend", {}).get("strategy") or "review"),
            "review_backend": deepcopy((result or {}).get("backend") or {}),
            "latest_review_markdown_path": (result or {}).get("latest_review_markdown_path"),
            "latest_review_json_path": (result or {}).get("latest_review_json_path"),
            "runs": deepcopy((result or {}).get("runs") or []),
            "updated_at": _utc_now(),
        }

    def _persist_ui_readiness(self, user_id: Optional[str], result: Dict[str, Any]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        summarized = self._summarize_ui_readiness_result(result)
        state["ui_readiness"] = summarized
        self._save_state(state)
        return summarized

    def get_ui_readiness(self, user_id: Optional[str]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        cached = dict(state.get("ui_readiness") or {})
        if cached:
            cached.setdefault("status", "cached")
            cached["user_id"] = state["user_id"]
            return cached
        return {
            "user_id": state["user_id"],
            "status": "unavailable",
            "verdict": "No UI verdict cached",
            "score": None,
            "summary": "",
            "release_blockers": [],
            "acceptance_checks": [],
            "tested_stages": [],
            "sdk_invocations": [],
            "actor_path_breaks": [],
            "broken_controls": [],
            "issues": [],
            "recommended_changes": [],
            "playwright_followups": [],
            "stage_findings": {},
            "screenshot_findings": [],
            "optimization_targets": [],
            "carry_forward_assessment": {},
            "issue_counts": {"high": 0, "medium": 0, "low": 0},
            "workflow_type": None,
            "review_backend": {},
            "latest_review_markdown_path": None,
            "latest_review_json_path": None,
            "runs": [],
            "updated_at": None,
        }

    def get_filing_provenance(self, user_id: Optional[str]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        draft = dict(state.get("draft") or {})
        claim_type = str(state.get("claim_type") or "retaliation")
        cached_ui_readiness = dict(state.get("ui_readiness") or {})
        cached_export_critic = dict(state.get("latest_export_critic") or {})
        export_critic_feedback = dict(cached_export_critic.get("complaint_output_feedback") or {})
        export_critic_aggregate = dict(cached_export_critic.get("aggregate") or {})
        export_router_backends = [
            deepcopy(item)
            for item in list(export_critic_aggregate.get("router_backends") or export_critic_feedback.get("router_backends") or [])
            if isinstance(item, dict) and item
        ]
        draft_backend = deepcopy(draft.get("draft_backend") or {})
        complaint_output_router_backend = deepcopy(export_critic_feedback.get("router_backend") or {})
        if not complaint_output_router_backend and export_router_backends:
            complaint_output_router_backend = deepcopy(export_router_backends[0])
        if not complaint_output_router_backend and draft_backend:
            complaint_output_router_backend = {
                key: value
                for key, value in {
                    "strategy": draft.get("draft_strategy") or draft_backend.get("strategy") or "template",
                    "provider": draft_backend.get("provider"),
                    "model": draft_backend.get("model"),
                    "requested_provider": draft_backend.get("requested_provider"),
                    "requested_model": draft_backend.get("requested_model"),
                    "id": draft_backend.get("id"),
                }.items()
                if value not in (None, "")
            }
        complaint_output_router_backends = export_router_backends or (
            [deepcopy(complaint_output_router_backend)] if complaint_output_router_backend else []
        )
        artifact_formats = ["json", "markdown", "pdf", "docx"] if draft else ["json"]
        return {
            "user_id": str(state.get("user_id") or user_id or DEFAULT_USER_ID),
            "claim_type": claim_type,
            "draft_strategy": str(draft.get("draft_strategy") or "template"),
            "draft_backend": draft_backend,
            "complaint_output_router_backend": complaint_output_router_backend,
            "complaint_output_router_backends": complaint_output_router_backends,
            "export_critic_router_backends": export_router_backends,
            "ui_review_backend": deepcopy(cached_ui_readiness.get("review_backend") or {}),
            "ui_workflow_type": str(cached_ui_readiness.get("workflow_type") or "").strip() or "unavailable",
            "artifact_formats": artifact_formats,
            "has_draft": bool(draft),
        }

    def get_client_release_gate(self, user_id: Optional[str]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        resolved_user_id = str(state.get("user_id") or user_id or DEFAULT_USER_ID)
        complaint_readiness = self.get_complaint_readiness(resolved_user_id)
        ui_readiness = self.get_ui_readiness(resolved_user_id)
        current_draft = dict(state.get("draft") or {})
        complaint_output_gate = _build_local_client_release_gate_for_state(state, self._build_review(state))

        # Pull the most recent proof-quality run from proof_history if available.
        proof_history = list(state.get("proof_history") or [])
        latest_proof_entry = dict(proof_history[-1]) if proof_history else {}
        proof_overall_score: Optional[int] = latest_proof_entry.get("overall_score")
        proof_has_blockers: bool = bool(latest_proof_entry.get("has_blockers"))

        complaint_score = int(complaint_readiness.get("score") or 0)
        ui_score = int(ui_readiness.get("score") or 35) if ui_readiness.get("score") is not None else 35
        output_score = _release_gate_score_from_verdict(complaint_output_gate.get("verdict"))
        # Weight the proof quality score into the composite if it is available
        # (15 % proof quality, redistributed from the other three inputs).
        if proof_overall_score is not None:
            score = round(
                complaint_score * 0.25
                + ui_score * 0.25
                + output_score * 0.35
                + int(proof_overall_score) * 0.15
            )
        else:
            score = round((complaint_score * 0.3) + (ui_score * 0.3) + (output_score * 0.4))

        ui_verdict = str(ui_readiness.get("verdict") or "").strip().lower()
        output_verdict = str(complaint_output_gate.get("verdict") or "").strip().lower()
        complaint_verdict = str(complaint_readiness.get("verdict") or "").strip().lower()

        blockers: List[str] = []
        if output_verdict == "blocked":
            blockers.append(str(complaint_output_gate.get("reason") or "The exported complaint is not yet client-safe."))
        if ui_verdict in {"do not send to clients yet", "needs repair", "no ui verdict cached"}:
            ui_reason = str(ui_readiness.get("summary") or "").strip()
            if ui_verdict == "no ui verdict cached":
                blockers.append("No actor/critic UI verdict is cached yet. Run the UX Audit before sending legal clients here.")
            elif ui_reason:
                blockers.append(ui_reason)
            else:
                blockers.append("The dashboard UI still needs repair before it should be treated as client-safe.")
        if complaint_verdict in {"not ready to draft", "still building the record"}:
            blockers.append(str(complaint_readiness.get("detail") or "The complaint record is not ready for drafting."))
        if proof_has_blockers:
            blockers.append(
                "The latest proof-quality check found blockers (contradictions, policy violations, or ungrounded assertions). "
                "Run complaint.improve_draft or complaint.score_draft_quality for details."
            )

        if output_verdict == "pass" and ui_verdict == "client-safe" and complaint_verdict in {"ready for first draft", "draft in progress"}:
            verdict = "client_safe"
            detail = (
                "The complaint workflow has a client-safe UI verdict, a filing-shaped complaint export, "
                "and a complaint record strong enough to keep drafting or refinement on track."
            )
            recommended_route = str(complaint_readiness.get("recommended_route") or "/document")
            recommended_action = "Continue refining the complaint and review the export artifacts before filing."
        elif score >= 65 and output_verdict != "blocked":
            verdict = "warning"
            detail = (
                "The complaint workflow is usable, but either the UI audit, the complaint record, or the exported filing "
                "still needs more work before this should be treated as safe for legal clients."
            )
            recommended_route = (
                "/workspace"
                if ui_verdict == "no ui verdict cached"
                else str(complaint_readiness.get("recommended_route") or "/workspace")
            )
            recommended_action = (
                "Review the blockers, tighten the record, and rerun the UX Audit or export critic before relying on this flow."
            )
        else:
            verdict = "blocked"
            detail = (
                "The current combination of UI readiness, complaint readiness, and exported complaint quality is not safe enough "
                "to treat this workflow as client-ready."
            )
            recommended_route = (
                "/workspace"
                if ui_verdict == "no ui verdict cached"
                else "/document"
                if output_verdict == "blocked" and current_draft
                else str(complaint_readiness.get("recommended_route") or "/workspace")
            )
            recommended_action = (
                "Fix the highlighted complaint-output and UI blockers before sending legal clients through this workflow."
            )

        return {
            "user_id": resolved_user_id,
            "score": max(0, min(100, score)),
            "verdict": verdict,
            "detail": detail,
            "recommended_route": recommended_route,
            "recommended_action": recommended_action,
            "blockers": blockers[:6],
            "complaint_readiness": complaint_readiness,
            "ui_readiness": ui_readiness,
            "complaint_output_release_gate": complaint_output_gate,
            "proof_quality": {
                "overall_score": proof_overall_score,
                "grade": latest_proof_entry.get("grade"),
                "has_blockers": proof_has_blockers,
                "run_at": latest_proof_entry.get("run_at"),
                "proof_status": latest_proof_entry.get("proof_status"),
            },
            "mike_grounding": deepcopy(((current_draft.get("sync_metadata") or {}).get("legal_corpus_review") or {})),
            "mike_logic": deepcopy(((current_draft.get("sync_metadata") or {}).get("logic_review") or {})),
        }

    @classmethod
    def _tooling_contract_source_members(cls) -> Dict[str, Set[str]]:
        """Inspect shipped interfaces without importing CLI or executing SDK code."""

        root = cls._repo_root()
        unavailable_sources: Set[str] = set()

        def source(relative_path: str) -> str:
            try:
                return (root / relative_path).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                unavailable_sources.add(relative_path)
                return ""

        trees: Dict[str, ast.Module] = {}

        def python_tree(relative_path: str) -> ast.Module:
            if relative_path in trees:
                return trees[relative_path]
            try:
                tree = ast.parse(source(relative_path))
            except SyntaxError:
                unavailable_sources.add(relative_path)
                tree = ast.Module(body=[], type_ignores=[])
            trees[relative_path] = tree
            return tree

        def declared_members(relative_path: str) -> Set[str]:
            members: Set[str] = set()
            for node in python_tree(relative_path).body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    members.add(node.name)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    members.update(alias.asname or alias.name for alias in node.names)
            return members

        package_exports: Set[str] = set()
        package_bindings: Set[str] = set()
        for node in python_tree("complaint_generator/__init__.py").body:
            if isinstance(node, ast.ImportFrom) and node.module:
                module_path = (
                    ("complaint_generator/" if node.level == 1 else "")
                    + node.module.replace(".", "/") + ".py"
                )
                members = declared_members(module_path)
                package_bindings.update(
                    alias.asname or alias.name for alias in node.names if alias.name in members
                )
            if not isinstance(node, ast.Assign):
                continue
            targets = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if "__all__" in targets:
                try:
                    package_exports.update(
                        value for value in ast.literal_eval(node.value) if isinstance(value, str)
                    )
                except (TypeError, ValueError):
                    pass
            elif "_LAZY_EXPORTS" in targets:
                try:
                    lazy_exports = ast.literal_eval(node.value)
                    for name, (module_name, member_name) in lazy_exports.items():
                        module_path = (
                            "complaint_generator/" + module_name[1:].replace(".", "/") + ".py"
                            if module_name.startswith(".")
                            else module_name.replace(".", "/") + ".py"
                        )
                        if member_name in declared_members(module_path):
                            package_bindings.add(name)
                except (AttributeError, TypeError, ValueError):
                    pass
        cli_commands: Set[str] = set()
        for node in python_tree("applications/complaint_cli.py").body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "app"
                    and decorator.func.attr == "command"
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and isinstance(decorator.args[0].value, str)
                ):
                    cli_commands.add(decorator.args[0].value)
        sdk_methods = [
            set(re.findall(r"(?m)^    (?:async )?([A-Za-z_$][\w$]*)\s*\(", source(path)))
            for path in ("static/complaint_mcp_sdk.js", "static/complaint_mcp_sdk.mjs")
        ]
        return {
            "package_exports": package_exports & package_bindings,
            "cli_commands": cli_commands,
            "browser_sdk_methods": sdk_methods[0] & sdk_methods[1],
            "unavailable_sources": unavailable_sources,
        }

    def get_tooling_contract(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        mcp_tools = [tool.get("name") for tool in list(self.list_mcp_tools().get("tools") or []) if tool.get("name")]
        available = self._tooling_contract_source_members()
        package_exports = [name for name in _PACKAGE_EXPORT_CONTRACT if name in available["package_exports"]]
        cli_commands = [name for name in _CLI_COMMAND_CONTRACT if name in available["cli_commands"]]
        browser_sdk_methods = [name for name in _BROWSER_SDK_METHOD_CONTRACT if name in available["browser_sdk_methods"]]
        core_flow_steps: List[Dict[str, Any]] = []
        missing_exposures: List[str] = []
        for step_id, mapping in _CORE_FLOW_CONTRACT.items():
            exposed_everywhere = (
                mapping["package_export"] in package_exports
                and mapping["cli_command"] in cli_commands
                and mapping["mcp_tool"] in mcp_tools
                and mapping["browser_sdk_method"] in browser_sdk_methods
            )
            if not exposed_everywhere:
                missing_exposures.append(step_id)
            core_flow_steps.append({
                "id": step_id,
                "package_export": mapping["package_export"],
                "cli_command": mapping["cli_command"],
                "mcp_tool": mapping["mcp_tool"],
                "browser_sdk_method": mapping["browser_sdk_method"],
                "exposed_everywhere": exposed_everywhere,
            })
        payload = {
            "user_id": str(user_id or DEFAULT_USER_ID),
            "package_exports": package_exports,
            "cli_commands": cli_commands,
            "mcp_tools": mcp_tools,
            "browser_sdk_methods": browser_sdk_methods,
            "core_flow_steps": core_flow_steps,
            "missing_exposures": missing_exposures,
            "all_core_flow_steps_exposed": not missing_exposures,
            "surface_inventory": {
                "status": "unknown" if available["unavailable_sources"] else "verified",
                "unavailable_sources": sorted(available["unavailable_sources"]),
            },
        }
        if user_id:
            try:
                payload["workspace_data_schema"] = self.get_workspace_data_schema(user_id)
                payload["schema_guided_recommendations"] = _build_schema_guided_tooling_recommendations(
                    payload["workspace_data_schema"]
                )
            except Exception as exc:
                payload["workspace_data_schema_error"] = str(exc)
                payload["schema_guided_recommendations"] = []
        else:
            payload["schema_guided_recommendations"] = []
        return payload

    def get_workspace_data_schema(
        self,
        user_id: Optional[str] = None,
        *,
        manifest_path: Optional[str | Path] = None,
        statefile_path: Optional[str | Path] = None,
        evidence_db_path: Optional[str | Path] = None,
        legal_authority_db_path: Optional[str | Path] = None,
        claim_support_db_path: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        if any(value is not None for value in (manifest_path, statefile_path, evidence_db_path, legal_authority_db_path, claim_support_db_path)):
            self._require_local_filesystem_access()
        from complaint_generator.data_migration import inspect_workspace_data_schema

        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        if manifest_path is not None:
            snapshot = inspect_workspace_data_schema(manifest_path=manifest_path)
        else:
            state = self._load_state(resolved_user_id)
            snapshot = inspect_workspace_data_schema(
                state=state,
                statefile_path=statefile_path,
                evidence_db_path=evidence_db_path,
                legal_authority_db_path=legal_authority_db_path,
                claim_support_db_path=claim_support_db_path,
                user_id=resolved_user_id,
            )
        snapshot["user_id"] = resolved_user_id
        snapshot["source"] = str(snapshot.get("source") or "workspace_data_schema")
        return snapshot

    def migrate_legacy_workspace_data(
        self,
        user_id: Optional[str] = None,
        *,
        output_dir: Optional[str | Path] = None,
        statefile_path: Optional[str | Path] = None,
        evidence_db_path: Optional[str | Path] = None,
        legal_authority_db_path: Optional[str | Path] = None,
        claim_support_db_path: Optional[str | Path] = None,
        package_name: Optional[str] = None,
        include_car: bool = True,
    ) -> Dict[str, Any]:
        self._require_local_filesystem_access()
        from complaint_generator.data_migration import migrate_legacy_workspace_data

        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        target_output_dir = (
            Path(output_dir).expanduser().resolve()
            if output_dir is not None
            else (self._session_dir / "dataset_migrations" / _slugify_user_id(resolved_user_id)).resolve()
        )
        state = self._load_state(resolved_user_id)
        result = migrate_legacy_workspace_data(
            output_dir=target_output_dir,
            state=state,
            statefile_path=statefile_path,
            evidence_db_path=evidence_db_path,
            legal_authority_db_path=legal_authority_db_path,
            claim_support_db_path=claim_support_db_path,
            user_id=resolved_user_id,
            package_name=package_name,
            include_car=include_car,
        )
        result["user_id"] = resolved_user_id
        result["output_dir"] = str(target_output_dir)
        return result

    def get_workflow_capabilities(self, user_id: Optional[str]) -> Dict[str, Any]:
        session = self.get_session(user_id)
        review = session["review"]
        overview = dict(review.get("overview") or {})
        current_draft = (session.get("session") or {}).get("draft")
        claim_type = str((session.get("session") or {}).get("claim_type") or "retaliation")
        draft_strategy = str((current_draft or {}).get("draft_strategy") or "template")
        questions = list(session.get("questions") or [])
        answered_count = len([item for item in questions if item.get("is_answered")])
        total_questions = len(questions)
        readiness = self.get_complaint_readiness(user_id)
        mike_status = self.get_mike_integration_status(user_id)
        capabilities = [
            {
                "id": "intake_questions",
                "label": "Complaint intake questions",
                "available": total_questions > 0,
                "detail": f"{answered_count} of {total_questions} intake questions answered.",
            },
            {
                "id": "mediator_prompt",
                "label": "Chat mediator handoff",
                "available": True,
                "detail": "A testimony-ready mediator prompt can be generated from the shared case synopsis and support gaps.",
            },
            {
                "id": "evidence_capture",
                "label": "Evidence capture",
                "available": True,
                "detail": f"{int(overview.get('testimony_items') or 0) + int(overview.get('document_items') or 0)} evidence items saved.",
            },
            {
                "id": "support_review",
                "label": "Claim support review",
                "available": True,
                "detail": f"{overview.get('supported_elements') or 0} supported elements, {overview.get('missing_elements') or 0} gaps remaining.",
            },
            {
                "id": "complaint_draft",
                "label": "Complaint draft",
                "available": True,
                "detail": "A draft already exists and can be edited." if current_draft else "A draft can be generated from the current complaint record.",
            },
            {
                "id": "claim_type_alignment",
                "label": "Claim-type drafting alignment",
                "available": True,
                "detail": f"The current complaint type is {_claim_type_display_name(claim_type)}.",
            },
            {
                "id": "formal_complaint_generation",
                "label": "Formal complaint generation",
                "available": True,
                "detail": (
                    "The current draft uses llm_router-backed formal complaint generation."
                    if draft_strategy == "llm_router"
                    else "The current draft is using the deterministic template fallback."
                ),
            },
            {
                "id": "complaint_packet",
                "label": "Complaint packet export",
                "available": True,
                "detail": "The lawsuit packet can be exported as a structured browser, CLI, or MCP artifact.",
            },
            {
                "id": "mike_editor_handoff",
                "label": "Mike editor handoff and draft sync",
                "available": True,
                "detail": str(mike_status.get("recommended_action") or "").strip()
                or "No Mike integration activity yet. Start with complaint.build_mike_handoff.",
            },
        ]
        workspace_data_schema = self.get_workspace_data_schema(session["session"]["user_id"])
        return {
            "user_id": session["session"]["user_id"],
            "case_synopsis": session["case_synopsis"],
            "overview": overview,
            "claim_type": claim_type,
            "claim_type_label": _claim_type_display_name(claim_type),
            "draft_strategy": draft_strategy,
            "complaint_readiness": readiness,
            "ui_readiness": self.get_ui_readiness(user_id),
            "client_release_gate": self.get_client_release_gate(user_id),
            "mike_integration_status": mike_status,
            "tooling_contract": self.get_tooling_contract(user_id),
            "workspace_data_schema": workspace_data_schema,
            "schema_guided_recommendations": _build_schema_guided_tooling_recommendations(workspace_data_schema),
            "capabilities": capabilities,
        }

    def export_complaint_packet(self, user_id: Optional[str]) -> Dict[str, Any]:
        snapshot = self._build_packet_snapshot(user_id)
        packet = snapshot["packet"]
        artifacts = snapshot["artifacts"]
        artifact_analysis = snapshot["artifact_analysis"]
        packet_summary = snapshot["packet_summary"]
        draft = dict(packet.get("draft") or {})
        review = dict(packet.get("review") or {})
        state = dict(packet)
        state["draft"] = draft
        state["review"] = review
        state["artifacts"] = artifacts
        state["artifact_analysis"] = artifact_analysis
        session = self.get_session(user_id)
        ui_feedback = self._analyze_complaint_output(packet, artifact_analysis)
        draft_fallback_reason = str(draft.get("draft_fallback_reason") or "").strip()
        complaint_issues = list(ui_feedback.get("issues") or [])
        payload = {
            "packet": packet,
            "artifacts": artifacts,
            "artifact_analysis": artifact_analysis,
            "ui_feedback": ui_feedback,
            "packet_summary": {
                **packet_summary,
                "draft_fallback_reason": draft_fallback_reason,
                "filing_shape_score": int(ui_feedback.get("filing_shape_score") or 0),
                "claim_type_alignment_score": int(ui_feedback.get("claim_type_alignment_score") or 0),
                "formal_defect_count": len(
                    [item for item in complaint_issues if str((item or {}).get("source") or "").startswith("complaint_output")]
                ),
                "high_severity_issue_count": len(
                    [item for item in complaint_issues if str((item or {}).get("severity") or "").lower() == "high"]
                ),
                "release_gate": deepcopy(ui_feedback.get("release_gate") or {}),
                "formal_diagnostics": deepcopy(ui_feedback.get("formal_diagnostics") or {}),
                "complaint_output_router_backend": deepcopy(((ui_feedback.get("router_review") or {}).get("backend") or {})),
            },
        }
        persisted_state = self._load_state(str((session.get("session") or {}).get("user_id") or user_id or DEFAULT_USER_ID))
        persisted_state["latest_packet_export"] = {
            "packet": {
                "title": str(packet.get("title") or "").strip(),
                "claim_type": str(packet.get("claim_type") or "retaliation").strip() or "retaliation",
                "exported_at": str(packet.get("exported_at") or _utc_now()),
                "draft": {
                    "title": str(draft.get("title") or "").strip(),
                    "body": str(draft.get("body") or ""),
                    "draft_strategy": str(draft.get("draft_strategy") or "template"),
                    "draft_fallback_reason": draft_fallback_reason,
                    "draft_normalizations": list(draft.get("draft_normalizations") or []),
                },
            },
            "packet_summary": deepcopy(payload.get("packet_summary") or {}),
            "ui_feedback": deepcopy(ui_feedback),
        }
        self._save_state(persisted_state)
        return payload

    def _build_packet_snapshot(self, user_id: Optional[str]) -> Dict[str, Any]:
        session = self.get_session(user_id)
        state = session["session"]
        draft = deepcopy(state.get("draft") or self._build_draft(state))
        review = deepcopy(session["review"])
        packet = {
            "title": draft["title"],
            "user_id": state["user_id"],
            "claim_type": state.get("claim_type", "retaliation"),
            "case_synopsis": session["case_synopsis"],
            "questions": deepcopy(session["questions"]),
            "evidence": deepcopy(state.get("evidence") or {}),
            "review": review,
            "draft": draft,
            "exported_at": _utc_now(),
        }
        artifacts = self._build_export_artifacts(packet)
        artifact_analysis = {
            "draft_word_count": len(str(draft.get("body") or "").split()),
            "evidence_item_count": len((packet.get("evidence") or {}).get("testimony") or [])
            + len((packet.get("evidence") or {}).get("documents") or []),
            "requested_relief_count": len(list(draft.get("requested_relief") or [])),
            "supported_elements": int((review.get("overview") or {}).get("supported_elements") or 0),
            "missing_elements": int((review.get("overview") or {}).get("missing_elements") or 0),
            "has_case_synopsis": bool(str(packet.get("case_synopsis") or "").strip()),
        }
        packet_summary = {
            "question_count": len(packet["questions"]),
            "answered_question_count": len([item for item in packet["questions"] if item.get("is_answered")]),
            "supported_elements": int((review.get("overview") or {}).get("supported_elements") or 0),
            "missing_elements": int((review.get("overview") or {}).get("missing_elements") or 0),
            "testimony_items": int((review.get("overview") or {}).get("testimony_items") or 0),
            "document_items": int((review.get("overview") or {}).get("document_items") or 0),
            "has_draft": bool(state.get("draft")),
            "draft_strategy": str(draft.get("draft_strategy") or "template"),
            "draft_normalization_count": len(list(draft.get("draft_normalizations") or [])),
            "draft_normalizations": list(draft.get("draft_normalizations") or []),
            "complaint_readiness": self.get_complaint_readiness(user_id),
            "artifact_formats": sorted(artifacts.keys()),
        }
        return {
            "packet": packet,
            "artifacts": artifacts,
            "artifact_analysis": artifact_analysis,
            "packet_summary": packet_summary,
        }

    def _analyze_complaint_output(self, packet: Dict[str, Any], artifact_analysis: Dict[str, Any]) -> Dict[str, Any]:
        from .ui_review import review_complaint_output_with_llm_router

        draft = dict(packet.get("draft") or {})
        review = dict(packet.get("review") or {})
        overview = dict(review.get("overview") or {})
        body = str(draft.get("body") or "").strip()
        case_synopsis = str(packet.get("case_synopsis") or "").strip()
        draft_backend = dict(draft.get("draft_backend") or {})
        issues: List[Dict[str, Any]] = []
        suggestions: List[Dict[str, Any]] = []
        formal_sections_present = {
            "caption": "IN THE UNITED STATES DISTRICT COURT" in body,
            "civil_action_number": "Civil Action No. ________________" in body,
            "nature_of_action": "NATURE OF THE ACTION" in body,
            "jurisdiction_and_venue": "JURISDICTION AND VENUE" in body,
            "parties": "PARTIES" in body,
            "factual_allegations": "FACTUAL ALLEGATIONS" in body,
            "evidentiary_support": "EVIDENTIARY SUPPORT AND NOTICE" in body,
            "claim_count": "COUNT I -" in body,
            "prayer_for_relief": "PRAYER FOR RELIEF" in body,
            "jury_demand": "JURY DEMAND" in body,
            "signature_block": "SIGNATURE BLOCK" in body,
        }
        claim_type = _normalize_claim_type(packet.get("claim_type"))
        claim_label = _claim_type_display_name(claim_type)
        expected_complaint_heading = f"COMPLAINT FOR {claim_label.upper()}"
        expected_count_heading = _claim_type_count_heading(claim_type)
        claim_type_alignment = {
            "complaint_heading_matches": expected_complaint_heading in body,
            "count_heading_matches": expected_count_heading in body,
        }
        validation_issues = _formal_complaint_validation_issues(body, claim_type)
        meta_summary_issues = [issue for issue in validation_issues if issue.startswith("Contains meta-summary language:")]
        numbering_issue_present = any(issue == "Missing numbered pleading paragraphs." for issue in validation_issues)

        if artifact_analysis.get("missing_elements", 0) > 0:
            missing_count = int(artifact_analysis.get("missing_elements") or 0)
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": f"The exported complaint still reflects {missing_count} unsupported claim elements.",
                    "ui_implication": "The review and draft stages need stronger warnings before the user treats the complaint as filing-ready.",
                }
            )
            suggestions.append(
                {
                    "title": "Tighten review-to-draft gatekeeping",
                    "recommendation": "Add stronger blocker language and a more prominent unsupported-elements summary before draft generation or export.",
                    "target_surface": "review,draft,integrations",
                }
            )
        if not case_synopsis:
            issues.append(
                {
                    "severity": "medium",
                    "source": "complaint_output",
                    "finding": "The exported complaint has no shared case synopsis.",
                    "ui_implication": "Users can reach export without preserving a stable theory of the case across mediator, review, and draft surfaces.",
                }
            )
            suggestions.append(
                {
                    "title": "Make case framing harder to miss",
                    "recommendation": "Require or strongly encourage a shared case synopsis before export and keep it visible near every major handoff.",
                    "target_surface": "intake,review,draft",
                }
            )
        if artifact_analysis.get("draft_word_count", 0) < 80:
            issues.append(
                {
                    "severity": "medium",
                    "source": "complaint_output",
                    "finding": "The exported complaint draft is still very short.",
                    "ui_implication": "The draft workflow may be under-explaining what a usable first complaint should contain.",
                }
            )
            suggestions.append(
                {
                    "title": "Strengthen draft completeness cues",
                    "recommendation": "Show a drafting checklist and clearer guidance about allegations, chronology, harm, and requested relief before export.",
                    "target_surface": "draft",
                }
            )
        if artifact_analysis.get("requested_relief_count", 0) == 0:
            issues.append(
                {
                    "severity": "medium",
                    "source": "complaint_output",
                    "finding": "No requested relief was carried into the export.",
                    "ui_implication": "The user may not understand that requested relief should be completed before download.",
                }
            )
            suggestions.append(
                {
                    "title": "Surface requested-relief validation",
                    "recommendation": "Warn before export when requested relief is empty and point the user back to the draft editor.",
                    "target_surface": "draft,integrations",
                }
            )
        if artifact_analysis.get("evidence_item_count", 0) == 0:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": "The complaint was exported without any saved evidence items.",
                    "ui_implication": "The workspace is not making evidence capture feel mandatory enough before a user downloads the packet.",
                }
            )
            suggestions.append(
                {
                    "title": "Make evidence support more legible before export",
                    "recommendation": "Display stronger export warnings and direct links back to the evidence workbench when the packet lacks corroborating materials.",
                    "target_surface": "evidence,review,integrations",
                }
            )

        formal_markers = [
            "IN THE UNITED STATES DISTRICT COURT",
            "Civil Action No. ________________",
            "COMPLAINT FOR",
            "JURISDICTION AND VENUE",
            "FACTUAL ALLEGATIONS",
            "EVIDENTIARY SUPPORT AND NOTICE",
            "COUNT I -",
            "PRAYER FOR RELIEF",
            "JURY DEMAND",
            "SIGNATURE BLOCK",
        ]
        missing_markers = [marker for marker in formal_markers if marker not in body]
        if missing_markers:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": "The exported complaint is missing formal pleading sections.",
                    "ui_implication": "The drafting UI is letting users export something that does not read like a formal legal complaint.",
                }
            )

        if numbering_issue_present:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": "The exported complaint is missing numbered pleading paragraphs.",
                    "ui_implication": "The draft builder is allowing narrative text that still reads like a summary instead of a filed complaint.",
                }
            )
            suggestions.append(
                {
                    "title": "Keep numbered complaint paragraphs visible in the draft",
                    "recommendation": "Show numbered pleading paragraph examples and warn before export if the draft body stops reading like a paragraph-numbered complaint.",
                    "target_surface": "draft,document,integrations",
                }
            )

        if meta_summary_issues:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": "The exported complaint still contains internal product or workflow language instead of clean pleading language.",
                    "ui_implication": "The LLM drafting flow is leaking system-facing wording into a client-facing legal document.",
                }
            )
            suggestions.append(
                {
                    "title": "Strip workflow language out of the complaint draft",
                    "recommendation": "Warn when the draft body mentions workflow summaries, complaint records, SDKs, JSON, or support matrices so the final complaint remains client-safe.",
                    "target_surface": "draft,integrations,optimizer",
                }
            )

        if not claim_type_alignment["complaint_heading_matches"] or not claim_type_alignment["count_heading_matches"]:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": f"The exported complaint does not clearly read like a {claim_label.lower()} complaint for the selected claim type.",
                    "ui_implication": "The drafting flow is letting the complaint drift into a generic or mismatched claim shape before export.",
                }
            )
            suggestions.append(
                {
                    "title": "Keep the selected claim theory visible through drafting",
                    "recommendation": "Show the selected claim type, count heading, and claim-specific allegation checklist throughout the draft flow so the complaint stays aligned to the chosen legal theory.",
                    "target_surface": "draft,review,integrations",
                }
            )
            suggestions.append(
                {
                    "title": "Enforce formal pleading structure",
                    "recommendation": "Keep the draft builder anchored to formal complaint sections like jurisdiction, factual allegations, prayer for relief, and jury demand before export.",
                    "target_surface": "draft,document,integrations",
                }
            )

        if not formal_sections_present["signature_block"]:
            issues.append(
                {
                    "severity": "medium",
                    "source": "complaint_output",
                    "finding": "The exported complaint is missing a signature block.",
                    "ui_implication": "The draft stage still reads too much like a memo unless the filing posture stays visible through export.",
                }
            )
            suggestions.append(
                {
                    "title": "Keep filing posture visible in the draft",
                    "recommendation": "Preserve a default signature block and explain in the draft editor that the output should resemble a court filing rather than a loose narrative summary.",
                    "target_surface": "draft,integrations",
                }
            )

        if artifact_analysis.get("evidence_item_count", 0) > 0 and "EVIDENTIARY SUPPORT AND NOTICE" not in body:
            issues.append(
                {
                    "severity": "medium",
                    "source": "complaint_output",
                    "finding": "The complaint includes evidence in the record, but the draft does not make that evidentiary posture legible.",
                    "ui_implication": "Users may not see how saved evidence is helping shape the pleading.",
                }
            )
            suggestions.append(
                {
                    "title": "Ground the draft in saved exhibits",
                    "recommendation": "Show clearer exhibit and support references in the draft so the complaint feels tied to the record gathered in the evidence and review stages.",
                    "target_surface": "evidence,review,draft",
                }
            )

        router_review = None
        try:
            router_review = review_complaint_output_with_llm_router(
                self._build_packet_markdown(packet),
                claim_type=claim_label,
                claim_guidance=_claim_type_filing_guidance(claim_type),
                synopsis=case_synopsis,
                notes=(
                    "Assess whether this output looks like a formal legal complaint, whether it matches the selected claim type, "
                    "and turn any filing-shape or claim-alignment defects into UI/UX repairs for intake, evidence, review, draft, and export surfaces."
                ),
            )
        except Exception:
            router_review = None

        router_payload = dict((router_review or {}).get("review") or {})
        router_issues = [dict(item) for item in list(router_payload.get("issues") or []) if isinstance(item, dict)]
        router_suggestions = [
            dict(item) for item in list(router_payload.get("ui_suggestions") or []) if isinstance(item, dict)
        ]
        for issue in router_issues[:6]:
            issues.append(
                {
                    "severity": str(issue.get("severity") or "medium"),
                    "source": "complaint_output_router",
                    "finding": str(issue.get("finding") or "The complaint output router identified a filing-shape issue."),
                    "ui_implication": str(
                        issue.get("ui_implication")
                        or issue.get("complaint_impact")
                        or "The UI flow is likely under-guiding the user before export."
                    ),
                }
            )
        for suggestion in router_suggestions[:6]:
            suggestions.append(
                {
                    "title": str(suggestion.get("title") or "Repair complaint-output workflow"),
                    "recommendation": str(
                        suggestion.get("recommendation")
                        or suggestion.get("why_it_matters")
                        or "Tighten the complaint workflow so the exported filing reads more formally."
                    ),
                    "target_surface": str(suggestion.get("target_surface") or "draft,review,integrations"),
                }
            )

        section_score = 5 * sum(1 for value in formal_sections_present.values() if value)
        body_length_score = 10 if artifact_analysis.get("draft_word_count", 0) >= 180 else 0
        evidence_score = 10 if artifact_analysis.get("evidence_item_count", 0) > 0 else 0
        relief_score = 5 if artifact_analysis.get("requested_relief_count", 0) > 0 else 0
        support_score = 5 if int(artifact_analysis.get("supported_elements") or 0) > 0 else 0
        heuristic_score = min(100, 35 + section_score + body_length_score + evidence_score + relief_score + support_score)
        router_score = int(router_payload.get("filing_shape_score") or 0) if router_payload else 0
        claim_type_alignment_score = (
            100
            if claim_type_alignment["complaint_heading_matches"] and claim_type_alignment["count_heading_matches"]
            else 50
            if claim_type_alignment["complaint_heading_matches"] or claim_type_alignment["count_heading_matches"]
            else 0
        )
        router_alignment_score = int(router_payload.get("claim_type_alignment_score") or 0) if router_payload else 0
        filing_shape_score = (
            round((heuristic_score + router_score) / 2)
            if router_score
            else heuristic_score
        )
        if claim_type_alignment_score == 0:
            resolved_claim_type_alignment_score = 0
        else:
            resolved_claim_type_alignment_score = (
                round((claim_type_alignment_score + router_alignment_score) / 2)
                if router_alignment_score
                else claim_type_alignment_score
            )
        release_gate = _build_complaint_output_release_gate(
            claim_type=claim_type,
            draft_strategy=str(draft.get("draft_strategy") or "template"),
            filing_shape_score=filing_shape_score,
            claim_type_alignment_score=resolved_claim_type_alignment_score,
            missing_elements=int(artifact_analysis.get("missing_elements") or 0),
            evidence_item_count=int(artifact_analysis.get("evidence_item_count") or 0),
        )

        if filing_shape_score < 75:
            issues.append(
                {
                    "severity": "high",
                    "source": "complaint_output",
                    "finding": "The generated complaint still does not read enough like a filing-ready legal complaint.",
                    "ui_implication": "The intake, evidence, review, and draft surfaces need stronger structure cues before export is treated as safe.",
                }
            )
            suggestions.append(
                {
                    "title": "Promote filing-readiness guidance before export",
                    "recommendation": "Keep the draft builder focused on caption, chronology, claim counts, evidentiary grounding, and requested relief so the exported complaint resembles a court filing instead of a loose summary.",
                    "target_surface": "draft,review,integrations",
                }
            )

        if not suggestions:
            suggestions.append(
                {
                    "title": "Preserve the current filing flow",
                    "recommendation": "The exported complaint looks coherent enough to keep the current UI flow, but continue validating navigation, evidence support, and clarity through Playwright.",
                    "target_surface": "workspace,review,document",
                }
            )

        complaint_output_issue_items = [
            dict(item)
            for item in issues
            if str((item or {}).get("source") or "").startswith("complaint_output")
        ]
        high_severity_complaint_items = [
            dict(item)
            for item in complaint_output_issue_items
            if str((item or {}).get("severity") or "").lower() == "high"
        ]
        formal_diagnostics = {
            "formal_defect_count": len(complaint_output_issue_items),
            "high_severity_issue_count": len(high_severity_complaint_items),
            "top_formal_findings": [
                str((item or {}).get("finding") or "").strip()
                for item in complaint_output_issue_items[:5]
                if str((item or {}).get("finding") or "").strip()
            ],
            "top_ui_implications": [
                str((item or {}).get("ui_implication") or "").strip()
                for item in complaint_output_issue_items[:5]
                if str((item or {}).get("ui_implication") or "").strip()
            ],
            "top_ui_suggestions": [
                str((item or {}).get("title") or "").strip()
                for item in suggestions[:5]
                if str((item or {}).get("title") or "").strip()
            ],
            "release_gate_verdict": str((release_gate or {}).get("verdict") or "").strip() or "unknown",
        }

        resolved_router_backend = deepcopy((router_review or {}).get("backend") or {})
        if resolved_router_backend and draft_backend:
            for key in ("id", "requested_provider", "requested_model", "provider", "model"):
                if resolved_router_backend.get(key) in (None, "") and draft_backend.get(key) not in (None, ""):
                    resolved_router_backend[key] = draft_backend.get(key)
        if not resolved_router_backend and draft_backend:
            resolved_router_backend = {
                "strategy": str(draft.get("draft_strategy") or "template"),
                "provider": draft_backend.get("provider"),
                "model": draft_backend.get("model"),
                "requested_provider": draft_backend.get("requested_provider"),
                "requested_model": draft_backend.get("requested_model"),
                "id": draft_backend.get("id"),
            }

        return {
            "summary": (
                "The exported complaint artifact was analyzed to infer which UI steps may still be too weak, "
                "hidden, or permissive for a real complainant."
            ),
            "filing_shape_score": filing_shape_score,
            "formal_sections_present": formal_sections_present,
            "claim_type_alignment": claim_type_alignment,
            "claim_type_alignment_score": resolved_claim_type_alignment_score,
            "release_gate": release_gate,
            "issues": issues,
            "ui_suggestions": suggestions,
            "formal_diagnostics": formal_diagnostics,
            "draft_strategy": str(draft.get("draft_strategy") or "template"),
            "draft_fallback_reason": str(draft.get("draft_fallback_reason") or "").strip(),
            "draft_normalizations": list(draft.get("draft_normalizations") or []),
            "draft_excerpt": body[:600],
            "complaint_strengths": [
                f"Supported elements: {int(overview.get('supported_elements') or 0)}",
                f"Evidence items: {int(overview.get('testimony_items') or 0) + int(overview.get('document_items') or 0)}",
                f"Requested relief items: {int(artifact_analysis.get('requested_relief_count') or 0)}",
                f"Formal sections present: {sum(1 for value in formal_sections_present.values() if value)}/{len(formal_sections_present)}",
                f"Claim type alignment: {expected_complaint_heading} / {expected_count_heading}",
            ],
            "router_backends": [
                deepcopy(resolved_router_backend)
            ]
            if isinstance(resolved_router_backend, dict) and resolved_router_backend
            else [],
            "router_review": {
                **(router_review or {}),
                "backend": resolved_router_backend,
            }
            if isinstance(router_review, dict)
            else {"backend": resolved_router_backend},
        }

    def analyze_complaint_output(self, user_id: Optional[str]) -> Dict[str, Any]:
        payload = self.export_complaint_packet(user_id)
        return {
            "user_id": ((payload.get("packet") or {}).get("user_id") or str(user_id or DEFAULT_USER_ID)),
            "packet_summary": deepcopy(payload.get("packet_summary") or {}),
            "artifact_analysis": deepcopy(payload.get("artifact_analysis") or {}),
            "ui_feedback": deepcopy(payload.get("ui_feedback") or {}),
        }

    def get_formal_diagnostics(self, user_id: Optional[str]) -> Dict[str, Any]:
        analysis = self.analyze_complaint_output(user_id)
        ui_feedback = dict(analysis.get("ui_feedback") or {})
        diagnostics = dict(ui_feedback.get("formal_diagnostics") or {})
        packet_summary = dict(analysis.get("packet_summary") or {})
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        draft_sync_metadata = dict((state.get("draft") or {}).get("sync_metadata") or {})
        try:
            markdown_artifact = self.build_export_artifact(user_id, "markdown")
            markdown_text = markdown_artifact.get("body", b"").decode("utf-8", errors="replace")
            export_structure = _build_export_structure_summary(markdown_text)
        except Exception as exc:
            export_structure = {
                "error": str(exc),
                "summary": {
                    "has_header": False,
                    "court_line_count": 0,
                    "party_line_count": 0,
                    "title_line_count": 0,
                    "section_count": 0,
                    "section_kinds": [],
                    "numbered_paragraph_count": 0,
                    "bullet_count": 0,
                    "code_block_count": 0,
                    "all_caps_heading_count": 0,
                    "title": "",
                },
            }
        return {
            "user_id": str(analysis.get("user_id") or user_id or DEFAULT_USER_ID),
            "claim_type_alignment_score": int(ui_feedback.get("claim_type_alignment_score") or 0),
            "filing_shape_score": int(ui_feedback.get("filing_shape_score") or 0),
            "release_gate": deepcopy(ui_feedback.get("release_gate") or {}),
            "formal_diagnostics": diagnostics,
            "export_structure": export_structure,
            "router_backend": deepcopy(((ui_feedback.get("router_review") or {}).get("backend") or {})),
            "mike_grounding": deepcopy(draft_sync_metadata.get("legal_corpus_review") or {}),
            "mike_logic": deepcopy(draft_sync_metadata.get("logic_review") or {}),
            "mike_sync_diagnostics": deepcopy(draft_sync_metadata.get("sync_diagnostics") or {}),
            "packet_summary": {
                "has_draft": bool(packet_summary.get("has_draft")),
                "draft_strategy": str(packet_summary.get("draft_strategy") or "template"),
                "formal_defect_count": int(packet_summary.get("formal_defect_count") or 0),
                "high_severity_issue_count": int(packet_summary.get("high_severity_issue_count") or 0),
                "complaint_output_router_backend": deepcopy(packet_summary.get("complaint_output_router_backend") or {}),
            },
        }

    def get_provider_diagnostics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        def _vault_value(*names: str) -> str:
            if str(os.getenv("COMPLAINT_PROVIDER_DIAGNOSTICS_CHECK_SECRETS", "") or "").strip() != "1":
                return ""
            try:
                get_secrets_vault = _require_ipfs_attr(
                    "ipfs_datasets_py.mcp_server.secrets_vault",
                    "get_secrets_vault",
                )

                vault = get_secrets_vault()
                for name in names:
                    resolved = str(vault.get(name) or "").strip()
                    if resolved:
                        return resolved
            except Exception:
                pass
            return ""

        def _keyring_value(*names: str) -> str:
            if str(os.getenv("COMPLAINT_PROVIDER_DIAGNOSTICS_CHECK_SECRETS", "") or "").strip() != "1":
                return ""
            try:
                import keyring  # type: ignore

                for name in names:
                    resolved = str(keyring.get_password("ipfs_datasets_py", name) or "").strip()
                    if resolved:
                        return resolved
            except Exception:
                pass
            return ""

        def _first_env(*names: str) -> str:
            for name in names:
                resolved = str(os.getenv(name, "") or "").strip()
                if resolved:
                    return resolved
            return ""

        def _source_for_openai() -> str:
            if _first_env("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
                return "env"
            if _vault_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
                return "vault"
            if _keyring_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
                return "keyring"
            return "unavailable"

        def _resolve_openai_key() -> str:
            resolved = _first_env("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN")
            if resolved:
                return resolved

            resolved = _vault_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN")
            if resolved:
                return resolved

            resolved = _keyring_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN")
            if resolved:
                return resolved
            return ""

        def _source_for_hf() -> str:
            if _first_env(
                "IPFS_DATASETS_PY_HF_API_TOKEN",
                "HUGGINGFACEHUB_API_TOKEN",
                "HF_TOKEN",
                "HUGGINGFACE_HUB_TOKEN",
                "HUGGINGFACE_API_KEY",
                "HUGGINGFACE_API_TOKEN",
                "HF_API_TOKEN",
            ):
                return "env"
            if _vault_value(
                "IPFS_DATASETS_PY_HF_API_TOKEN",
                "HUGGINGFACEHUB_API_TOKEN",
                "HF_TOKEN",
                "HUGGINGFACE_HUB_TOKEN",
                "HUGGINGFACE_API_KEY",
                "HUGGINGFACE_API_TOKEN",
                "HF_API_TOKEN",
            ):
                return "vault"
            if _keyring_value(
                "IPFS_DATASETS_PY_HF_API_TOKEN",
                "HUGGINGFACEHUB_API_TOKEN",
                "HF_TOKEN",
                "HUGGINGFACE_HUB_TOKEN",
                "HUGGINGFACE_API_KEY",
                "HUGGINGFACE_API_TOKEN",
                "HF_API_TOKEN",
            ):
                return "keyring"
            return "unavailable"

        def _resolve_hf_token_for_diagnostics() -> str:
            resolved = _first_env(
                "IPFS_DATASETS_PY_HF_API_TOKEN",
                "HUGGINGFACEHUB_API_TOKEN",
                "HF_TOKEN",
                "HUGGINGFACE_HUB_TOKEN",
                "HUGGINGFACE_API_KEY",
                "HUGGINGFACE_API_TOKEN",
                "HF_API_TOKEN",
            )
            if resolved:
                return resolved
            resolved = _vault_value(
                "IPFS_DATASETS_PY_HF_API_TOKEN",
                "HUGGINGFACEHUB_API_TOKEN",
                "HF_TOKEN",
                "HUGGINGFACE_HUB_TOKEN",
                "HUGGINGFACE_API_KEY",
                "HUGGINGFACE_API_TOKEN",
                "HF_API_TOKEN",
            )
            if resolved:
                return resolved
            return _keyring_value(
                "IPFS_DATASETS_PY_HF_API_TOKEN",
                "HUGGINGFACEHUB_API_TOKEN",
                "HF_TOKEN",
                "HUGGINGFACE_HUB_TOKEN",
                "HUGGINGFACE_API_KEY",
                "HUGGINGFACE_API_TOKEN",
                "HF_API_TOKEN",
            )

        def _copilot_command_available(command: str) -> bool:
            parts = str(command or "").strip().split()
            if not parts:
                return False
            if parts[0] == "npx":
                return True
            return shutil.which(parts[0]) is not None

        def _copilot_supports_image_inputs_for_diagnostics() -> bool:
            explicit = str(os.getenv("IPFS_DATASETS_PY_COPILOT_CLI_SUPPORTS_IMAGE_INPUTS", "") or "").strip().lower()
            if explicit:
                return explicit in {"1", "true", "yes", "on"}
            # Avoid running `copilot --help` or `npx ... --help` here; provider diagnostics
            # must stay fast and should not spawn long-lived CLI probes from the browser UI.
            return False

        raw_default_order = [
            "codex_cli",
            "copilot_cli",
            "openai",
            "hf_inference_api",
            "openrouter",
            "gemini_cli",
            "claude_code",
            "claude_py",
            "gemini_py",
            "copilot_sdk",
        ]
        preferred_default_order = [
            "codex_cli",
            "copilot_cli",
            "openai",
            "hf_inference_api",
        ]
        default_order = [
            item
            for item in preferred_default_order
            if item in set(raw_default_order) or item in {"codex_cli", "copilot_cli", "openai", "hf_inference_api"}
        ]
        default_order.extend(
            item
            for item in raw_default_order
            if item and item not in default_order
        )
        forced_provider = str(os.getenv("IPFS_DATASETS_PY_LLM_PROVIDER", "") or "").strip()
        codex_path = shutil.which("codex") or ""
        copilot_path = shutil.which("copilot") or ""
        openai_key = _resolve_openai_key()
        copilot_command = os.getenv("IPFS_DATASETS_PY_COPILOT_CLI_CMD", "npx --yes @github/copilot -p {prompt}")
        hf_token = _resolve_hf_token_for_diagnostics()
        copilot_available = _copilot_command_available(copilot_command)
        copilot_supports_image_inputs = _copilot_supports_image_inputs_for_diagnostics()

        providers = [
            {
                "name": "codex_cli",
                "available": bool(codex_path),
                "reason": "Codex CLI is installed and available on PATH." if codex_path else "Codex CLI binary not found on PATH.",
                "binary_path": codex_path or None,
                "credential_source": "local_codex_auth" if codex_path else "unavailable",
                "supports_multimodal": bool(codex_path),
                "draft_timeout_seconds": _llm_draft_timeout_for_provider("codex_cli"),
            },
            {
                "name": "openai",
                "available": bool(openai_key),
                "reason": "OpenAI API key resolved for direct chat-completions use." if openai_key else "No OpenAI API key resolved from env, vault, keyring, or local CLI config.",
                "credential_source": _source_for_openai(),
                "base_url": str(os.getenv("IPFS_DATASETS_PY_OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/"),
                "draft_timeout_seconds": _llm_draft_timeout_for_provider("openai"),
            },
            {
                "name": "copilot_cli",
                "available": copilot_available,
                "reason": (
                    "Copilot CLI command template resolved and is available."
                    if copilot_available and copilot_path
                    else "Copilot fallback is available through the configured command template."
                    if copilot_available
                    else "Copilot CLI command is not currently available on this machine."
                ),
                "binary_path": copilot_path or None,
                "supports_multimodal": bool(copilot_path),
                "supports_multimodal_ui_review": copilot_supports_image_inputs,
                "credential_source": (
                    "github_copilot_cli"
                    if copilot_available and copilot_path
                    else "github_copilot_command_template"
                    if copilot_available
                    else "unavailable"
                ),
                "draft_timeout_seconds": _llm_draft_timeout_for_provider("copilot_cli"),
            },
            {
                "name": "hf_inference_api",
                "available": bool(hf_token),
                "reason": "Hugging Face token resolved for hosted inference/router use." if hf_token else "No Hugging Face token resolved from env, vault, keyring, or huggingface_hub CLI login.",
                "credential_source": _source_for_hf(),
                "base_url": str(os.getenv("IPFS_DATASETS_PY_HF_INFERENCE_BASE_URL", "https://router.huggingface.co/hf-inference/models")).rstrip("/"),
                "draft_timeout_seconds": _llm_draft_timeout_for_provider("hf_inference_api"),
                "ui_review_model": str(
                    os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL_HF_INFERENCE_API", "") or ""
                ).strip()
                or "Qwen/Qwen2.5-VL-7B-Instruct",
                "ui_review_timeout_seconds": _llm_draft_timeout_for_provider("hf_inference_api"),
            },
        ]

        effective_default = next((item["name"] for item in providers if item["available"]), None)
        return {
            "user_id": str(user_id or DEFAULT_USER_ID),
            "forced_provider": forced_provider or None,
            "default_order": default_order,
            "effective_default_provider": forced_provider or effective_default,
            "complaint_draft_default_order": list(DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN),
            "effective_complaint_draft_provider": (
                str(os.getenv("COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER", "") or "").strip()
                or DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN[0]
            ),
            "ui_review_default_provider": str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_PROVIDER", "") or "").strip()
            or "codex_cli",
            "ui_review_default_model": str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL_CODEX_CLI", "") or "").strip()
            or str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL", "") or "").strip()
            or "gpt-5.3-codex",
            "ui_review_multimodal_rate_limit_fallbacks": {
                "codex_cli": ["copilot_cli", "hf_inference_api"],
                "copilot_cli": ["hf_inference_api"],
            },
            "ui_review_hf_fallback_model": str(
                os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL_HF_INFERENCE_API", "") or ""
            ).strip()
            or "Qwen/Qwen2.5-VL-7B-Instruct",
            "providers": providers,
            "summary": {
                "codex_available": bool(codex_path),
                "openai_available": bool(openai_key),
                "copilot_available": copilot_available,
                "huggingface_available": bool(hf_token),
            },
        }

    def review_generated_exports(
        self,
        user_id: Optional[str],
        *,
        artifact_path: Optional[str] = None,
        artifact_dir: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config_path: Optional[str] = None,
        backend_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        if artifact_path or artifact_dir:
            self._require_local_filesystem_access()
        from .ui_review import review_complaint_export_artifacts

        artifact_metadata: List[Dict[str, Any]] = []
        if artifact_path:
            path = Path(str(artifact_path)).expanduser().resolve()
            if not path.exists():
                raise ValueError(f"Artifact path does not exist: {path}")
            payload = json.loads(path.read_text())
            if not isinstance(payload, dict):
                raise ValueError("Artifact path must point to a JSON object.")
            artifact_metadata.append(payload)
        elif artifact_dir:
            root = Path(str(artifact_dir)).expanduser().resolve()
            if not root.exists():
                raise ValueError(f"Artifact directory does not exist: {root}")
            for candidate in sorted(root.glob("*.json")):
                try:
                    payload = json.loads(candidate.read_text())
                except Exception:
                    continue
                if isinstance(payload, dict):
                    artifact_metadata.append(payload)
        else:
            artifact_metadata = self._build_complaint_output_review_artifacts(user_id)

        report = review_complaint_export_artifacts(
            artifact_metadata,
            provider=provider,
            model=model,
            config_path=config_path,
            backend_id=backend_id,
            notes=notes,
        )
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        state["latest_export_critic"] = deepcopy(report)
        self._save_state(state)
        return {
            "user_id": str(user_id or DEFAULT_USER_ID),
            **report,
        }

    def update_claim_type(self, user_id: Optional[str], claim_type: Optional[str]) -> Dict[str, Any]:
        return self.request_handlers.update_claim_type(user_id, claim_type)

    def _build_complaint_output_review_artifacts(self, user_id: Optional[str]) -> List[Dict[str, Any]]:
        if not user_id:
            return []
        packet_payload = self.export_complaint_packet(user_id)
        artifacts = dict(packet_payload.get("artifacts") or {})
        markdown_artifact = dict(artifacts.get("markdown") or {})
        pdf_artifact = dict(artifacts.get("pdf") or {})
        ui_feedback = dict(packet_payload.get("ui_feedback") or {})
        draft = dict((packet_payload.get("packet") or {}).get("draft") or {})
        suggestions = list(ui_feedback.get("ui_suggestions") or [])
        suggestion_lines = [str(ui_feedback.get("summary") or "").strip()]
        for item in suggestions[:5]:
            title = str((item or {}).get("title") or "").strip()
            recommendation = str((item or {}).get("recommendation") or "").strip()
            if title and recommendation:
                suggestion_lines.append(f"- {title}: {recommendation}")
            elif title:
                suggestion_lines.append(f"- {title}")
            elif recommendation:
                suggestion_lines.append(f"- {recommendation}")
        return [
            {
                "name": "workspace-export-artifacts",
                "url": "/workspace?target_tab=integrations",
                "title": "Unified Complaint Workspace",
                "artifact_type": "complaint_export",
                "claim_type": str(packet_payload.get("packet", {}).get("claim_type") or ""),
                "draft_strategy": str(draft.get("draft_strategy") or "template"),
                "draft_normalizations": list(draft.get("draft_normalizations") or []),
                "text_excerpt": str(draft.get("body") or "").strip()[:600],
                "markdown_filename": str(markdown_artifact.get("filename") or ""),
                "pdf_filename": str(pdf_artifact.get("filename") or ""),
                "markdown_excerpt": str(markdown_artifact.get("excerpt") or markdown_artifact.get("content") or "").strip()[:2000],
                "pdf_header": str(pdf_artifact.get("content_type") or "application/pdf"),
                "filing_shape_score": int(ui_feedback.get("filing_shape_score") or 0),
                "claim_type_alignment_score": int(ui_feedback.get("claim_type_alignment_score") or 0),
                "formal_section_gaps": [
                    key
                    for key, present in dict(ui_feedback.get("formal_sections_present") or {}).items()
                    if not present
                ],
                "formal_defect_count": len(
                    [
                        item
                        for item in list(ui_feedback.get("issues") or [])
                        if str((item or {}).get("source") or "").startswith("complaint_output")
                    ]
                ),
                "claim_type_alignment": dict(ui_feedback.get("claim_type_alignment") or {}),
                "release_gate": dict(ui_feedback.get("release_gate") or {}),
                "formal_diagnostics": dict(ui_feedback.get("formal_diagnostics") or {}),
                "router_export_critic": dict(((ui_feedback.get("router_review") or {}).get("review") or {})),
                "router_backend": dict(((ui_feedback.get("router_review") or {}).get("backend") or {})),
                "ui_suggestions_excerpt": "\n".join(line for line in suggestion_lines if line),
            }
        ]

    def _build_cached_ui_readiness_artifacts(self, user_id: Optional[str]) -> List[Dict[str, Any]]:
        if not user_id:
            return []
        ui_readiness = self.get_ui_readiness(user_id)
        if str(ui_readiness.get("status") or "").strip().lower() != "cached":
            return []
        screenshot_findings = [
            dict(item)
            for item in list(ui_readiness.get("screenshot_findings") or [])
            if isinstance(item, dict) and item
        ]
        optimization_targets = [
            dict(item)
            for item in list(ui_readiness.get("optimization_targets") or [])
            if isinstance(item, dict) and item
        ]
        playwright_followups = [str(item).strip() for item in list(ui_readiness.get("playwright_followups") or []) if str(item).strip()]
        recommended_changes = [str(item).strip() for item in list(ui_readiness.get("recommended_changes") or []) if str(item).strip()]
        if not (screenshot_findings or optimization_targets or playwright_followups or recommended_changes):
            return []

        finding_lines: List[str] = []
        for item in screenshot_findings[:4]:
            stage = str(item.get("stage") or item.get("name") or "unknown stage").strip()
            summary = str(item.get("summary") or item.get("stage_finding") or item.get("visible_text_excerpt") or "").strip()
            criticism_items = list(item.get("criticisms") or [])
            criticism_text: List[str] = []
            for criticism in criticism_items[:2]:
                if isinstance(criticism, dict):
                    text = str(criticism.get("problem") or criticism.get("recommended_fix") or "").strip()
                else:
                    text = str(criticism or "").strip()
                if text:
                    criticism_text.append(text)
            line = f"- {stage}: {summary or 'No summary returned.'}"
            if criticism_text:
                line += f" Criticisms: {'; '.join(criticism_text)}"
            finding_lines.append(line)

        target_lines = [
            f"- {str(item.get('title') or item.get('target') or item.get('target_surface') or 'optimization target').strip()}"
            + (
                f": {str(item.get('reason') or '').strip()}"
                if str(item.get("reason") or "").strip()
                else ""
            )
            for item in optimization_targets[:4]
        ]
        followup_lines = [f"- {item}" for item in playwright_followups[:4]]
        change_lines = [f"- {item}" for item in recommended_changes[:4]]
        excerpt_sections = [
            str(ui_readiness.get("summary") or "").strip(),
            "Screenshot findings:\n" + "\n".join(finding_lines) if finding_lines else "",
            "Optimization targets:\n" + "\n".join(target_lines) if target_lines else "",
            "Playwright follow-ups:\n" + "\n".join(followup_lines) if followup_lines else "",
            "Recommended changes:\n" + "\n".join(change_lines) if change_lines else "",
        ]

        return [
            {
                "name": "workspace-cached-ui-readiness",
                "url": "/workspace?target_tab=ux-review",
                "title": "Cached UX Audit Review",
                "artifact_type": "ui_readiness_review",
                "verdict": str(ui_readiness.get("verdict") or ""),
                "score": ui_readiness.get("score"),
                "critic_verdict": str(ui_readiness.get("critic_verdict") or ""),
                "workflow_type": str(ui_readiness.get("workflow_type") or ""),
                "review_backend": deepcopy(ui_readiness.get("review_backend") or {}),
                "tested_stages": list(ui_readiness.get("tested_stages") or []),
                "release_blockers": list(ui_readiness.get("release_blockers") or []),
                "screenshot_findings": screenshot_findings,
                "optimization_targets": optimization_targets,
                "playwright_followups": playwright_followups,
                "recommended_changes": recommended_changes,
                "review_excerpt": "\n\n".join(section for section in excerpt_sections if section).strip()[:3000],
                "latest_review_markdown_path": ui_readiness.get("latest_review_markdown_path"),
                "latest_review_json_path": ui_readiness.get("latest_review_json_path"),
            }
        ]

    def export_complaint_markdown(self, user_id: Optional[str]) -> Dict[str, Any]:
        artifact = self.build_export_artifact(user_id, "markdown")
        packet_payload = self._build_packet_snapshot(user_id)
        return {
            "artifact": {
                "format": "markdown",
                "filename": artifact["filename"],
                "media_type": artifact["media_type"],
                "size_bytes": len(artifact["body"]),
                "excerpt": artifact["body"].decode("utf-8", errors="replace")[:2000],
            },
            "packet_summary": deepcopy(packet_payload.get("packet_summary") or {}),
            "artifact_analysis": deepcopy(packet_payload.get("artifact_analysis") or {}),
        }

    def export_complaint_pdf(self, user_id: Optional[str]) -> Dict[str, Any]:
        artifact = self.build_export_artifact(user_id, "pdf")
        packet_payload = self._build_packet_snapshot(user_id)
        return {
            "artifact": {
                "format": "pdf",
                "filename": artifact["filename"],
                "media_type": artifact["media_type"],
                "size_bytes": len(artifact["body"]),
                "header_b64": b64encode(artifact["body"][:32]).decode("ascii"),
            },
            "packet_summary": deepcopy(packet_payload.get("packet_summary") or {}),
            "artifact_analysis": deepcopy(packet_payload.get("artifact_analysis") or {}),
        }

    def export_complaint_docx(self, user_id: Optional[str]) -> Dict[str, Any]:
        artifact = self.build_export_artifact(user_id, "docx")
        packet_payload = self._build_packet_snapshot(user_id)
        return {
            "artifact": {
                "format": "docx",
                "filename": artifact["filename"],
                "media_type": artifact["media_type"],
                "size_bytes": len(artifact["body"]),
                "header_b64": b64encode(artifact["body"][:32]).decode("ascii"),
            },
            "packet_summary": deepcopy(packet_payload.get("packet_summary") or {}),
            "artifact_analysis": deepcopy(packet_payload.get("artifact_analysis") or {}),
        }

    def build_export_artifact(self, user_id: Optional[str], output_format: str = "json") -> Dict[str, Any]:
        payload = self._build_packet_snapshot(user_id)
        packet = payload.get("packet") or {}
        artifacts = payload.get("artifacts") or {}
        normalized_format = str(output_format or "json").strip().lower()
        if normalized_format == "json":
            filename = ((artifacts.get("json") or {}).get("filename")) or "complaint-packet.json"
            body = json.dumps(packet, indent=2, sort_keys=True).encode("utf-8")
            return {"filename": filename, "media_type": "application/json", "body": body}
        if normalized_format in {"markdown", "md"}:
            artifact = artifacts.get("markdown") or {}
            content = artifact.get("content") or self._build_complaint_export_markdown(packet)
            return {
                "filename": artifact.get("filename") or "complaint-packet.md",
                "media_type": "text/markdown",
                "body": str(content).encode("utf-8"),
            }
        if normalized_format == "pdf":
            artifact = artifacts.get("markdown") or {}
            markdown_text = artifact.get("content") or self._build_complaint_export_markdown(packet)
            pdf_bytes = self._build_packet_pdf_bytes(packet, str(markdown_text))
            return {
                "filename": ((artifacts.get("pdf") or {}).get("filename")) or "complaint-packet.pdf",
                "media_type": "application/pdf",
                "body": pdf_bytes,
            }
        if normalized_format == "docx":
            artifact = artifacts.get("markdown") or {}
            markdown_text = artifact.get("content") or self._build_complaint_export_markdown(packet)
            docx_bytes = self._build_packet_docx_bytes(packet, str(markdown_text))
            return {
                "filename": ((artifacts.get("docx") or {}).get("filename")) or "complaint-packet.docx",
                "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "body": docx_bytes,
            }
        raise ValueError(f"Unsupported complaint export format: {output_format}")

    def submit_intake_answers(self, user_id: Optional[str], answers: Dict[str, Any]) -> Dict[str, Any]:
        return self.request_handlers.submit_intake_answers(user_id, answers)

    def run_intake_chat_turn(
        self,
        user_id: Optional[str],
        *,
        message: Optional[str] = None,
        question_id: Optional[str] = None,
        expected_question_revision: Optional[int] = None,
        interview_action: Optional[str] = None,
        expected_graph_revision: Optional[str] = None,
        expected_session_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.request_handlers.run_intake_chat_turn(
            user_id,
            message=message,
            question_id=question_id,
            expected_question_revision=expected_question_revision,
            interview_action=interview_action,
            expected_graph_revision=expected_graph_revision,
            expected_session_revision=expected_session_revision,
        )

    def apply_terminal_graph_edit(
        self,
        user_id: Optional[str],
        replacement: str,
        *,
        expected_graph_revision: Optional[str] = None,
        expected_session_revision: Optional[int] = None,
        target_stable_id: Optional[str] = None,
        actor_principal_id: Optional[str] = None,
        require_expected_revision: bool = False,
    ) -> Dict[str, Any]:
        return self.request_handlers.apply_terminal_graph_edit(
            user_id,
            replacement,
            expected_graph_revision=expected_graph_revision,
            expected_session_revision=expected_session_revision,
            target_stable_id=target_stable_id,
            actor_principal_id=actor_principal_id,
            require_expected_revision=require_expected_revision,
        )

    def review_case_factual_graph(self, user_id: Optional[str], *, case_id: str,
                                  updates: Mapping[str, Any]) -> Dict[str, Any]:
        """Publish one factual review only under current owner/key/source CAS.

        The graph route cannot save a decrypted DTO itself. The existing
        private revision writer rechecks this issued capability immediately
        before replacing the durable head, including after encryption/fsync.
        """
        from complaint_phases.knowledge_graph import KnowledgeGraph, FactualReviewError
        from mediator.integrations.graph_tools import FactualGraphProjectionError
        from integrations.private_storage import PrivateStorageError

        authority = self._owner_case_authority()
        if authority is None or authority.case_id != case_id or authority.action != "case.update":
            raise FactualReviewError("actor_authority_required")
        actor = authority.actor_principal_id
        decision = authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
        resolved = self._resolve_user_id(user_id)
        self._check_access(resolved, ability="write", case_id=case_id)
        state = self._load_state(resolved, case_id=case_id)
        if state.get("user_id") != decision.canonical_owner_principal_id or state.get("case_id") != case_id:
            raise FactualGraphProjectionError("cross_case_id")
        shared = state.get("shared_interview")
        payload = shared.get("knowledge_graph") if isinstance(shared, dict) else None
        if not isinstance(payload, dict) or not payload:
            raise FactualGraphProjectionError("knowledge_graph_unavailable")
        graph = KnowledgeGraph.from_dict(deepcopy(payload))
        # This existing identity binds the entire private shared interview,
        # including its KG, pending question and private revision.
        before = self._case_legal_context_identity(state)
        _context, admitted_key_id, admitted_key = self._joined_key(resolved, case_id)

        def revalidate_publication():
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _live, key_id, key = self._joined_key(resolved, case_id)
            if key_id != admitted_key_id or key != admitted_key:
                raise FactualGraphProjectionError("graph_revision_changed")
            current = self._load_state(resolved, case_id=case_id)
            if before != self._case_legal_context_identity(current):
                raise FactualGraphProjectionError("graph_revision_changed")
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _live, key_id, key = self._joined_key(resolved, case_id)
            if key_id != admitted_key_id or key != admitted_key:
                raise FactualGraphProjectionError("graph_revision_changed")

        result = graph.apply_factual_review(
            actor_role="user", actor_principal_id=actor, authority_granted=True,
            expected_revision=str(updates.get("expected_graph_revision") or ""),
            action=str(updates.get("review_action") or ""),
            text=updates.get("text") if isinstance(updates.get("text"), str) else "",
            source_text=updates.get("source_text") if isinstance(updates.get("source_text"), str) else "",
            message_id=str(updates.get("message_id") or ""),
            target_stable_id=str(updates.get("target_stable_id") or ""),
            proposal_id=str(updates.get("proposal_id") or ""),
            origin=str(updates.get("origin") or "actor"),
            event_id=str(updates.get("event_id") or ""), case_id=case_id,
            record_class=str(updates.get("record_class") or ""),
        )
        revalidate_publication()
        if result.get("graph_mutated") is True:
            draft = deepcopy(state)
            draft["shared_interview"]["knowledge_graph"] = graph.to_dict()
            draft["updated_at"] = _utc_now()
            try:
                self._commit_joined_snapshot(draft, before_publish=revalidate_publication)
            except PrivateStorageError as exc:
                raise WorkspacePersistenceError("Factual review did not commit.",
                    code=str(getattr(exc, "code", "") or "durability_unproven"), public_status="recoverable") from None
            self._interview_mediators.pop((resolved, case_id), None)
        authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
        return {**result, "case_id": case_id, "task_id": "CIMP-GUI-22"}

    def _case_legal_context_state(self, user_id, case_id, *, action):
        """Resolve the live issued owner and its current encrypted workflow DTO."""
        authority = self._owner_case_authority()
        if authority is None or authority.case_id != case_id or authority.action != action:
            raise WorkspaceAuthorizationDenied()
        actor = authority.actor_principal_id
        authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
        resolved = self._resolve_user_id(user_id)
        self._check_access(resolved, ability="write" if action == "case.update" else "read", case_id=case_id)
        state = self._load_state(resolved, case_id=case_id)
        shared = state.get("shared_interview")
        if (not isinstance(shared, dict) or not isinstance(shared.get("intake_case_file"), dict)
                or not isinstance(shared.get("dependency_graph"), dict)):
            raise WorkspacePersistenceError("A saved shared interview is required.",
                code="legal_context_unavailable", public_status="unavailable")
        authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
        return authority, resolved, state

    @staticmethod
    def _case_legal_context_identity(state):
        return hashlib.sha256(json.dumps({
            "user_id": state.get("user_id"), "case_id": state.get("case_id"),
            "private_revision": state.get("private_revision"),
            "shared_interview": state.get("shared_interview"),
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()

    def read_case_legal_context(self, user_id: Optional[str], *, case_id: str) -> Dict[str, Any]:
        """Read current encrypted context; neither a mediator cache nor GET writes."""
        from applications.legal_context_api import project_legal_context

        authority, resolved, state = self._case_legal_context_state(user_id, case_id, action="case.read")
        before = self._case_legal_context_identity(state)
        payload = project_legal_context(state["shared_interview"]["intake_case_file"])
        current = self._load_state(resolved, case_id=case_id)
        if before != self._case_legal_context_identity(current):
            raise WorkspacePersistenceError("Legal context changed during the read.",
                code="revision_conflict", public_status="conflict")
        authority.revalidate(actor_principal_id=authority.actor_principal_id, workspace=self, require_owner=True)
        return {**payload, "case_id": case_id, "private_revision": state.get("private_revision"),
            "session_revision": state["shared_interview"].get("session_revision"), "read_only": True}

    def update_case_legal_context(self, user_id: Optional[str], *, case_id: str,
                                 updates: Mapping[str, Any]) -> Dict[str, Any]:
        """Commit one explicit context/DG change using the existing encrypted CAS.

        All access/key/source bindings are derived here, not accepted in the
        request document. A refused or stale selection never mutates the live
        mediator cache. Successful publication evicts only this case's cache;
        the ordinary workflow resume then reads the new committed projection.
        """
        from applications.legal_context_selection import apply_legal_context_selection
        from complaint_phases.dependency_graph import DependencyGraph
        from integrations.private_storage import PrivateStorageError
        from mediator.workflow_service import WorkflowActionService

        authority, resolved, state = self._case_legal_context_state(user_id, case_id, action="case.update")
        actor = authority.actor_principal_id
        before = self._case_legal_context_identity(state)
        shared = state["shared_interview"]
        graph = DependencyGraph.from_dict(deepcopy(shared["dependency_graph"]))
        selected = apply_legal_context_selection(shared["intake_case_file"], updates, dependency_graph=graph)
        _context, admitted_key_id, admitted_key = self._joined_key(resolved, case_id)

        def revalidate_publication():
            # The revision writer already holds its CAS lock. _load_state is
            # read-only and takes no second revision writer lock; get_session
            # would be wrong here because a case.update scope may save it.
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _live, key_id, key = self._joined_key(resolved, case_id)
            if key_id != admitted_key_id or key != admitted_key:
                raise WorkspacePersistenceError("Private key changed before publication.",
                    code="revision_conflict", public_status="conflict")
            current = self._load_state(resolved, case_id=case_id)
            if before != self._case_legal_context_identity(current):
                raise WorkspacePersistenceError("Legal context changed before publication.",
                    code="revision_conflict", public_status="conflict")
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _live, key_id, key = self._joined_key(resolved, case_id)
            if key_id != admitted_key_id or key != admitted_key:
                raise WorkspacePersistenceError("Private key changed before publication.",
                    code="revision_conflict", public_status="conflict")

        if not selected["changed"]:
            revalidate_publication()
            return {**selected["projection"], "case_id": case_id, "changed": False,
                "private_revision": state.get("private_revision"), "session_revision": shared.get("session_revision")}
        projection = WorkflowActionService.project_legal_context_selection(shared,
            case_file=selected["case_file"], dependency_graph=selected["dependency_graph"])
        draft = deepcopy(state)
        draft["shared_interview"] = projection
        draft["updated_at"] = _utc_now()
        revalidate_publication()
        try:
            committed = self._commit_joined_snapshot(draft, before_publish=revalidate_publication)
        except PrivateStorageError as exc:
            raise WorkspacePersistenceError("Legal context did not commit.",
                code=str(getattr(exc, "code", "") or "durability_unproven"), public_status="recoverable") from None
        # No cache mutation occurs until the actual durable head succeeds.
        self._interview_mediators.pop((resolved, case_id), None)
        authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
        return {**selected["projection"], "case_id": case_id, "changed": True,
            "private_revision": committed.get("private_revision"), "session_revision": projection["session_revision"],
            "dependency_refresh": selected["dependency_refresh"]}

    def accept_case_review_fact_proposal(self, actor, *, case_id, review_service, proposal_id,
            expected_review_revision, expected_private_revision, expected_session_revision, request_id):
        """Accept server-owned proposed fact text through the real correction owner.

        The canonical receipt and KG correction share one encrypted case CAS.
        The review repository remains an immutable proposal/evidence source.
        """
        from applications.case_review_store import CaseReviewService, CaseReviewStoreError
        from integrations.private_storage import PrivateStorageError, private_revision_source_scope
        from complaint_phases.knowledge_graph import KnowledgeGraph
        from mediator.hook_runtime import graph_revision_token

        def text(value):
            return isinstance(value, str) and 0 < len(value) <= 80 and value == value.strip()
        if (not text(actor) or not text(case_id) or not text(proposal_id) or not text(request_id)
                or type(expected_review_revision) is not int or expected_review_revision < 0
                or type(expected_session_revision) is not int or expected_session_revision < 0
                or not isinstance(expected_private_revision, str)
                or not re.fullmatch(r"(?:0|[1-9][0-9]{0,31})", expected_private_revision)):
            raise CaseReviewStoreError("review_field")
        if type(review_service) is not CaseReviewService:
            raise CaseReviewStoreError("review_unavailable")
        try:
            authority = self._owner_case_authority()
            if authority is None or authority.action != "case.update":
                raise CaseReviewStoreError("lawyer_review_ungranted")
            authority, canonical, state = self._case_legal_context_state(actor, case_id, action="case.update")
            decision = authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            if decision.membership != "owner" or authority.actor_principal_id != actor:
                raise WorkspaceAuthorizationDenied()
            shared = state["shared_interview"]
            fingerprint = _canonical_review_sha({"actor": actor, "canonical": canonical, "case_id": case_id,
                "request_id": request_id, "proposal_id": proposal_id,
                "expected_review_revision": expected_review_revision,
                "expected_private_revision": expected_private_revision,
                "expected_session_revision": expected_session_revision})
            ledger = state.get("canonical_review_acceptances") or {}
            if not isinstance(ledger, dict):
                raise CaseReviewStoreError("review_integrity")
            def deliver(receipt, *, replayed):
                # A valid earlier commit is never rolled back by a delivery
                # refusal. Re-open current material and reprove both key
                # owners, review CAS and browser authority after projection.
                with private_revision_source_scope(self.joined_revision_repository(canonical, case_id)):
                    _context, key_id, key = self._joined_key(canonical, case_id)
                    current = self._load_state(canonical, case_id=case_id)
                    saved = (current.get("canonical_review_acceptances") or {}).get(request_id)
                    if not isinstance(saved, dict) or _canonical_review_sha(saved) != _canonical_review_sha(receipt):
                        raise CaseReviewStoreError("stale_revision")
                    graph = KnowledgeGraph.from_dict(current["shared_interview"]["knowledge_graph"])
                    current_result = (graph_revision_token(graph) == receipt["result_graph_revision"]
                        and current["shared_interview"]["session_revision"] == receipt["result_session_revision"]
                        and current["private_revision"] == receipt["result_private_revision"])
                    response = {**deepcopy(receipt), "applied": False if replayed else True,
                        "replayed": replayed, "historically_applied": True, "current_result": current_result,
                        "current_private_revision": current["private_revision"]}
                    review_service.reprove_proposal_for_owner(actor, case_id=case_id, proposal_id=proposal_id,
                        authority=authority, expected_review_revision=expected_review_revision,
                        expected_record_sha256=receipt["proposal_record_sha256"])
                    _context, current_key_id, current_key = self._joined_key(canonical, case_id)
                    if (key_id, key) != (current_key_id, current_key):
                        raise CaseReviewStoreError("revision_conflict")
                    authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
                    return response
            existing = ledger.get(request_id)
            if existing is not None:
                if (not isinstance(existing, dict) or existing.get("request_sha256") != fingerprint
                        or existing.get("proposal_id") != proposal_id
                        or existing.get("accepting_owner_actor") != actor):
                    raise CaseReviewStoreError("replay_mismatch")
                signed = {k: v for k, v in existing.items() if k != "receipt_sha256"}
                if existing.get("receipt_sha256") != _canonical_review_sha(signed):
                    raise CaseReviewStoreError("review_integrity")
                # Lost-response replay can outlive its own source revision,
                # but cannot outlive changed authority or a changed proposal.
                return deliver(existing, replayed=True)
            if any(isinstance(row, dict) and row.get("proposal_id") == proposal_id for row in ledger.values()):
                raise CaseReviewStoreError("proposal_already_accepted")
            if (state.get("private_revision") != expected_private_revision
                    or shared.get("session_revision") != expected_session_revision):
                raise CaseReviewStoreError("stale_revision")
            proposal = review_service.read_proposal_for_owner(actor,
                case_id=case_id, proposal_id=proposal_id, authority=authority)
            record, base = proposal.get("record"), proposal.get("source_base")
            if (proposal.get("schema") != "case-review-owner-proposal@1"
                    or proposal.get("case_id") != case_id or proposal.get("actor_principal_id") != actor
                    or proposal.get("canonical_owner_principal_id") != canonical
                    or proposal.get("review_revision") != expected_review_revision
                    or not isinstance(record, dict) or not isinstance(base, dict)
                    or record.get("item_type") != "review_proposal" or record.get("item_id") != proposal_id
                    or _canonical_review_sha(record) != proposal.get("record_sha256")
                    or base.get("private_revision") != expected_private_revision
                    or base.get("session_revision") != expected_session_revision):
                raise CaseReviewStoreError("stale_approval")
            if record.get("target_kind") not in {"fact", "answer"}:
                raise CaseReviewStoreError("review_target_capability_unavailable")
            target, replacement = record.get("target_id"), record.get("proposed_text")
            if not text(target) or not isinstance(replacement, str) or not 0 < len(replacement) <= 2000 or replacement != replacement.strip():
                raise CaseReviewStoreError("review_field")
            graph = KnowledgeGraph.from_dict(shared["knowledge_graph"])
            graph_revision = graph_revision_token(graph)
            context = _ReviewFactAcceptance(self, review_service, authority, actor, canonical, case_id,
                deepcopy(proposal), request_id, fingerprint, self._case_legal_context_identity(state),
                graph_revision, expected_private_revision, expected_session_revision)
            result = self.request_handlers.apply_terminal_graph_edit(actor, replacement,
                expected_graph_revision=graph_revision, expected_session_revision=expected_session_revision,
                target_stable_id=target, actor_principal_id=actor, require_expected_revision=True,
                _review_acceptance=context)
            if result.get("status") != "applied" or not isinstance(result.get("review_acceptance"), dict):
                raise CaseReviewStoreError(str((result.get("error") or {}).get("code") or "review_transition_refused"))
            return deliver(result["review_acceptance"], replayed=False)
        except WorkspaceAuthorizationDenied:
            raise CaseReviewStoreError("lawyer_review_ungranted") from None
        except (WorkspacePersistenceError, PrivateStorageError) as exc:
            raise CaseReviewStoreError(str(getattr(exc, "code", "") or "durability_unproven")) from None

    def read_case_legal_research_snapshot(self, user_id: Optional[str], *, case_id: str) -> Dict[str, Any]:
        """Read an authorized encrypted DTO, without GET/session-save or cache effects.

        This in-process owner API is not mounted as a raw-state HTTP endpoint.
        Its snapshot is a CAS preimage, not authorization supplied by a client.
        """
        authority = self._owner_case_authority()
        if authority is None or authority.action not in {"case.read", "case.update", "case.review"}:
            raise WorkspaceAuthorizationDenied()
        authority, resolved, state = self._case_legal_context_state(user_id, case_id, action=authority.action)
        identity = self._case_legal_context_identity(state)
        _context, key_id, key = self._joined_key(resolved, case_id)
        current = self._load_state(resolved, case_id=case_id)
        _live, current_key_id, current_key = self._joined_key(resolved, case_id)
        if identity != self._case_legal_context_identity(current) or (key_id, key) != (current_key_id, current_key):
            raise WorkspacePersistenceError("Research source changed during read.", code="revision_conflict", public_status="conflict")
        authority.revalidate(actor_principal_id=authority.actor_principal_id, workspace=self, require_owner=True)
        shared = state["shared_interview"]
        case_file = shared["intake_case_file"]
        source_scope = case_legal_source_scope(state, case_id=case_id)
        return {"state": deepcopy(state), "canonical_owner_principal_id": resolved,
            "actor_principal_id": authority.actor_principal_id, "case_id": case_id,
            "private_revision": state.get("private_revision"), "session_revision": shared.get("session_revision"),
            "source_identity": identity, "source_scope_sha256": source_scope, "key_id": key_id, "read_only": True}

    def read_case_legal_materials_snapshot(self, user_id: Optional[str], *, case_id: str) -> Dict[str, Any]:
        """Current copied legal materials for in-process legal/DG consumers."""
        from complaint_phases.dependency_graph import DependencyGraph
        snapshot = self.read_case_legal_research_snapshot(user_id, case_id=case_id)
        shared = snapshot["state"]["shared_interview"]
        return {**snapshot, "case_file": deepcopy(shared["intake_case_file"]),
            "dependency_graph": DependencyGraph.from_dict(deepcopy(shared["dependency_graph"]))}

    def read_case_legal_research(self, user_id: Optional[str], *, case_id: str, admissions: bool = False) -> Dict[str, Any]:
        from applications.legal_research_api import project_authority_admissions, project_legal_research
        authority = self._owner_case_authority()
        if authority is None or authority.action != "case.read":
            raise WorkspaceAuthorizationDenied()
        snapshot = self.read_case_legal_research_snapshot(user_id, case_id=case_id)
        case_file = snapshot["state"]["shared_interview"]["intake_case_file"]
        project = project_authority_admissions if admissions else project_legal_research
        return {**project(case_file), "case_id": case_id, "read_only": True,
            "private_revision": snapshot["private_revision"], "session_revision": snapshot["session_revision"]}

    def acquire_case_legal_research(self, user_id: Optional[str], *, case_id: str, request: Mapping[str, Any]) -> Dict[str, Any]:
        return self._run_case_legal_research(user_id, case_id=case_id, request=request, review=False)

    def review_case_legal_authority(self, user_id: Optional[str], *, case_id: str, request: Mapping[str, Any]) -> Dict[str, Any]:
        return self._run_case_legal_research(user_id, case_id=case_id, request=request, review=True)

    def _run_case_legal_research(self, user_id, *, case_id, request, review):
        from applications.legal_research_api import (LegalResearchError, _bounds, _purpose_decision,
            _require_purpose_consent, acquire_bounded_legal_sources, review_versioned_authority)
        from complaint_phases.phase_manager import ComplaintPhase
        from complaint_phases.dependency_graph import DependencyGraph
        from integrations.private_storage import PrivateStorageError
        from mediator.workflow_service import WorkflowActionService

        authority = self._owner_case_authority()
        expected_action = "case.review" if review else "case.update"
        if authority is None or authority.action != expected_action or not isinstance(request, Mapping):
            raise WorkspaceAuthorizationDenied()
        snapshot = self.read_case_legal_research_snapshot(user_id, case_id=case_id)
        actor, canonical = snapshot["actor_principal_id"], snapshot["canonical_owner_principal_id"]
        state = snapshot["state"]
        shared = state["shared_interview"]
        for field, actual in (("expected_private_revision", snapshot["private_revision"]),
                ("expected_session_revision", snapshot["session_revision"]),
                ("expected_source_scope_sha256", snapshot["source_scope_sha256"])):
            if field in request and request[field] != actual:
                raise WorkspacePersistenceError("Research precondition changed.", code="revision_conflict", public_status="conflict")
        if self._legal_research_stale(state, expected_graph_revision=request.get("expected_graph_revision"),
                expected_session_revision=request.get("expected_session_revision")) is not None:
            raise WorkspacePersistenceError("Research graph changed.", code="revision_conflict", public_status="conflict")
        _context, admitted_key_id, admitted_key = self._joined_key(canonical, case_id)
        if admitted_key_id != snapshot["key_id"]:
            raise WorkspacePersistenceError("Research key changed.", code="revision_conflict", public_status="conflict")
        if review:
            index = shared["intake_case_file"].get("legal_source_passage_index") or {}
            source = index.get(request.get("content_hash")) if isinstance(index, dict) else None
            acquisition_context = source.get("acquisition_context") if isinstance(source, dict) else None
            if not isinstance(acquisition_context, dict) or acquisition_context.get("source_scope_sha256") != snapshot["source_scope_sha256"]:
                raise LegalResearchError("legal_research_revision_conflict")
            purpose = acquisition_context.get("purpose")
            view = authority.processing_consent(purpose=purpose, actor_principal_id=actor, workspace=self)
            generation = _purpose_decision(view, purpose).get("generation")
        else:
            bounds = _bounds(request)
            purpose, generation = bounds["purpose"], bounds["expected_consent_generation"]
            # Grok consent and its transport are not corpus authorization.
            if bounds["retrieval_mode"] == "live":
                raise LegalResearchError("legal_corpus_unavailable")
        _require_purpose_consent(authority, self, purpose, generation, "cache")

        def revalidate_publication():
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _live, key_id, key = self._joined_key(canonical, case_id)
            if (key_id, key) != (admitted_key_id, admitted_key):
                raise WorkspacePersistenceError("Research key changed before publication.", code="revision_conflict", public_status="conflict")
            _require_purpose_consent(authority, self, purpose, generation, "cache")
            current = self._load_state(canonical, case_id=case_id)
            if self._case_legal_context_identity(current) != snapshot["source_identity"]:
                raise WorkspacePersistenceError("Research source changed before publication.", code="revision_conflict", public_status="conflict")
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _live, key_id, key = self._joined_key(canonical, case_id)
            if (key_id, key) != (admitted_key_id, admitted_key):
                raise WorkspacePersistenceError("Research key changed before publication.", code="revision_conflict", public_status="conflict")

        revalidate_publication()
        mediator = self._mediator_for_shared_interview(canonical, case_id, cache=False)
        mediator.workflow_actions.restore_session_projection(deepcopy(shared))
        if review:
            decision = authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            receipt = review_versioned_authority(mediator, self, authority, request,
                membership=decision.membership, canonical_owner_principal_id=canonical,
                actor_is_encrypted_owner=actor == canonical, source_scope_sha256=snapshot["source_scope_sha256"])
        else:
            receipt = acquire_bounded_legal_sources(mediator, self, authority, request,
                source_scope_sha256=snapshot["source_scope_sha256"])
        # Research stores source custody and review. The mediator's legacy
        # admission-time graph may include unrelated source-owner DB rows;
        # only the separate current-manifest refresh may promote dependencies.
        receipt = {**receipt, "graph_mutated": False, "dependency_refresh_status": "not_requested"}
        produced = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
        if not isinstance(produced, dict):
            raise WorkspacePersistenceError("Research source unavailable.", code="legal_research_unavailable", public_status="unavailable")
        case_file = deepcopy(shared["intake_case_file"])
        for field in ("legal_source_candidate_receipt", "legal_source_passage_index", "legal_authority_admissions",
                      "legal_source_operations", "legal_authority_review_operations"):
            if field in produced:
                case_file[field] = deepcopy(produced[field])
        revalidate_publication()
        if case_file == shared["intake_case_file"]:
            return {**receipt, "case_id": case_id, "private_revision": snapshot["private_revision"],
                "session_revision": snapshot["session_revision"]}
        graph = DependencyGraph.from_dict(deepcopy(shared["dependency_graph"]))
        projection = WorkflowActionService.project_legal_context_selection(shared, case_file=case_file, dependency_graph=graph)
        draft = deepcopy(state)
        draft["shared_interview"] = projection
        draft["updated_at"] = _utc_now()
        try:
            committed = self._commit_joined_snapshot(draft, before_publish=revalidate_publication)
        except PrivateStorageError as exc:
            raise WorkspacePersistenceError("Research did not commit.", code=str(getattr(exc, "code", "") or "durability_unproven"), public_status="recoverable") from None
        self._interview_mediators.pop((canonical, case_id), None)
        authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
        return {**receipt, "case_id": case_id, "private_revision": committed.get("private_revision"),
            "session_revision": projection["session_revision"]}

    def read_case_legal_analysis(self, user_id: Optional[str], *, case_id: str) -> Dict[str, Any]:
        """Project current encrypted IR only after live owner/key/source reproof."""
        from applications.legal_analysis_api import (project_canonical_legal_ir,
            current_case_legal_ir_source, LegalAnalysisError)
        authority = self._owner_case_authority()
        if authority is None or authority.action != "case.read":
            raise WorkspaceAuthorizationDenied()
        snapshot = self.read_case_legal_materials_snapshot(user_id, case_id=case_id)
        payload = project_canonical_legal_ir(snapshot["case_file"])
        binding = payload.get("source_binding")
        if payload.get("status") != "empty":
            source_current = (isinstance(binding, dict)
                and binding.get("source_scope_sha256") == snapshot["source_scope_sha256"])
            if source_current:
                try:
                    current_source = current_case_legal_ir_source(snapshot["case_file"],
                        binding.get("content_hash"), case_id=case_id)
                    source_current = (binding.get("source_record_sha256")
                        == hashlib.sha256(json.dumps(current_source["record"], sort_keys=True,
                            separators=(",", ":"), allow_nan=False).encode()).hexdigest())
                except LegalAnalysisError:
                    source_current = False
            payload["source_current"] = source_current
            if not source_current:
                payload.update(status="stale", reason="legal_case_sources_changed",
                    source_spans=[], typed_obligations=[])
            # A saved execution receipt is historical data. The adapter's
            # process-local registry alone can establish current execution
            # provenance; a cold read must never reconstruct that authority.
            from integrations.ipfs_datasets.logic import verify_canonical_formalization_receipt
            payload["recorded_receipt_verification"] = deepcopy(payload.get("receipt_verification"))
            audit = verify_canonical_formalization_receipt(str(payload.get("receipt_id") or ""),
                **({"source_text": current_source["text"]} if source_current else {}))
            payload["receipt_verification"] = {"status": audit.get("status"),
                "tampered": audit.get("tampered") is True,
                "execution_origin_verified": source_current and audit.get("execution_origin_verified") is True,
                "reason": str(audit.get("reason") or "")}
            payload["current_execution_verified"] = (source_current and audit.get("status") == "verified"
                and audit.get("execution_origin_verified") is True and audit.get("tampered") is not True)
            payload["recorded_compilation_is_proof"] = False
        current = self.read_case_legal_materials_snapshot(user_id, case_id=case_id)
        if (snapshot["source_identity"], snapshot["key_id"]) != (current["source_identity"], current["key_id"]):
            raise WorkspacePersistenceError("Legal analysis changed during read.", code="revision_conflict", public_status="conflict")
        authority.revalidate(actor_principal_id=snapshot["actor_principal_id"], workspace=self, require_owner=True)
        return {**payload, "case_id": case_id, "private_revision": snapshot["private_revision"],
            "session_revision": snapshot["session_revision"], "read_only": True}


    def read_case_proof_traces(self, user_id: Optional[str], *, case_id: str) -> Dict[str, Any]:
        """Read current encrypted source/IR and project only verified provenance.

        No compilation, proof engine, model, cache save or private CAS is
        performed. The existing IR owner verifies current source/receipt
        structure; compiler execution remains separate from checked proof.
        """
        from applications.legal_analysis_api import (current_case_legal_ir_source,
            project_current_case_proof_traces, LegalAnalysisError)
        authority = self._owner_case_authority()
        if authority is None or authority.action != "case.read":
            raise WorkspaceAuthorizationDenied()
        snapshot = self.read_case_legal_materials_snapshot(user_id, case_id=case_id)
        analysis = self.read_case_legal_analysis(user_id, case_id=case_id)
        if (analysis.get("private_revision"), analysis.get("session_revision")) != (
                snapshot["private_revision"], snapshot["session_revision"]):
            raise WorkspacePersistenceError("Proof source changed during read.", code="revision_conflict", public_status="conflict")
        text = None
        if analysis.get("source_current") is True:
            binding = analysis.get("source_binding") or {}
            if binding.get("source_scope_sha256") != snapshot["source_scope_sha256"]:
                raise WorkspacePersistenceError("Proof source scope changed.", code="revision_conflict", public_status="conflict")
            text = current_case_legal_ir_source(snapshot["case_file"], binding.get("content_hash"), case_id=case_id)["text"]
        result = project_current_case_proof_traces(analysis, source_text=text)
        current = self.read_case_legal_materials_snapshot(user_id, case_id=case_id)
        if (snapshot["source_identity"], snapshot["key_id"]) != (current["source_identity"], current["key_id"]):
            raise WorkspacePersistenceError("Proof source changed during read.", code="revision_conflict", public_status="conflict")
        authority.revalidate(actor_principal_id=snapshot["actor_principal_id"], workspace=self, require_owner=True)
        return {**result, "case_id": case_id, "read_only": True,
            "private_revision": snapshot["private_revision"], "session_revision": snapshot["session_revision"]}

    def attach_case_legal_analysis(self, user_id: Optional[str], *, case_id: str,
                                   request: Mapping[str, Any]) -> Dict[str, Any]:
        """Compile a current stored source and commit through the encrypted CAS.

        Request source/context/fact assertions are never the case's authority.
        Local compilation needs no model consent and performs no model egress.
        """
        from applications.legal_analysis_api import compile_current_case_legal_ir, LegalAnalysisError
        from integrations.private_storage import PrivateStorageError
        from mediator.workflow_service import WorkflowActionService

        authority = self._owner_case_authority()
        if authority is None or authority.action != "case.update" or not isinstance(request, Mapping):
            raise WorkspaceAuthorizationDenied()
        snapshot = self.read_case_legal_materials_snapshot(user_id, case_id=case_id)
        actor, canonical = snapshot["actor_principal_id"], snapshot["canonical_owner_principal_id"]
        for field, actual in (("expected_private_revision", snapshot["private_revision"]),
                              ("expected_session_revision", snapshot["session_revision"])):
            value = request.get(field)
            valid_type = (type(value) is str and 1 <= len(value) <= 19
                and value.isascii() and value.isdecimal() and (value == "0" or not value.startswith("0"))
                ) if field == "expected_private_revision" else type(value) is int
            if not valid_type or value != actual:
                raise WorkspacePersistenceError("Legal analysis precondition changed.", code="revision_conflict", public_status="conflict")
        _context, admitted_key_id, admitted_key = self._joined_key(canonical, case_id)
        if admitted_key_id != snapshot["key_id"]:
            raise WorkspacePersistenceError("Legal analysis key changed.", code="revision_conflict", public_status="conflict")

        def before_publish():
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _current, key_id, key = self._joined_key(canonical, case_id)
            if (key_id, key) != (admitted_key_id, admitted_key):
                raise WorkspacePersistenceError("Legal analysis key changed.", code="revision_conflict", public_status="conflict")
            current = self._load_state(canonical, case_id=case_id)
            if self._case_legal_context_identity(current) != snapshot["source_identity"]:
                raise WorkspacePersistenceError("Legal analysis source changed.", code="revision_conflict", public_status="conflict")
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _current, key_id, key = self._joined_key(canonical, case_id)
            if (key_id, key) != (admitted_key_id, admitted_key):
                raise WorkspacePersistenceError("Legal analysis key changed.", code="revision_conflict", public_status="conflict")

        state = snapshot["state"]
        shared = state["shared_interview"]
        payload = compile_current_case_legal_ir(snapshot["case_file"], shared["knowledge_graph"], request,
            case_id=case_id, source_scope_sha256=snapshot["source_scope_sha256"])
        before_publish()
        if payload.get("status") != "attached":
            return {**payload, "attachment_persisted": False,
                "private_revision": snapshot["private_revision"], "session_revision": snapshot["session_revision"]}
        case_file = deepcopy(snapshot["case_file"])
        case_file["canonical_legal_ir_attachment"] = deepcopy(payload)
        projection = WorkflowActionService.project_legal_context_selection(shared,
            case_file=case_file, dependency_graph=snapshot["dependency_graph"])
        draft = deepcopy(state)
        draft["shared_interview"] = projection
        draft["updated_at"] = _utc_now()
        try:
            committed = self._commit_joined_snapshot(draft, before_publish=before_publish)
        except PrivateStorageError as exc:
            raise WorkspacePersistenceError("Legal analysis did not commit.",
                code=str(getattr(exc, "code", "") or "durability_unproven"), public_status="recoverable") from None
        self._interview_mediators.pop((canonical, case_id), None)
        authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
        return {**payload, "attachment_persisted": True,
            "private_revision": committed.get("private_revision"), "session_revision": projection["session_revision"]}


    def read_case_definition_correspondence(self, user_id: Optional[str], *, case_id: str) -> Dict[str, Any]:
        """Project current encrypted IR only after live owner/key/source reproof."""
        from applications.legal_analysis_api import (project_definition_correspondence,
            current_case_legal_ir_source, LegalAnalysisError)
        authority = self._owner_case_authority()
        if authority is None or authority.action != "case.read":
            raise WorkspaceAuthorizationDenied()
        snapshot = self.read_case_legal_materials_snapshot(user_id, case_id=case_id)
        payload = deepcopy(project_definition_correspondence(snapshot["case_file"]))
        binding = payload.get("source_binding")
        if payload.get("status") != "empty":
            source_current = (isinstance(binding, dict)
                and binding.get("source_scope_sha256") == snapshot["source_scope_sha256"])
            if source_current:
                try:
                    current_source = current_case_legal_ir_source(snapshot["case_file"],
                        binding.get("content_hash"), case_id=case_id)
                    source_current = (binding.get("source_record_sha256")
                        == hashlib.sha256(json.dumps(current_source["record"], sort_keys=True,
                            separators=(",", ":"), allow_nan=False).encode()).hexdigest())
                except LegalAnalysisError:
                    source_current = False
            payload["source_current"] = source_current
            if not source_current:
                payload.update(status="stale", reason="legal_case_sources_changed",
                    owners={})
            payload["current_owner_replayed"] = False
            for family in payload.get("owners", {}).values():
                if isinstance(family, dict):
                    family["recorded_genuine_owner_receipt"] = family.get("genuine_current_owner_receipt") is True
                    family["genuine_current_owner_receipt"] = False
            payload["recorded_replay_is_proof"] = False
        current = self.read_case_legal_materials_snapshot(user_id, case_id=case_id)
        if (snapshot["source_identity"], snapshot["key_id"]) != (current["source_identity"], current["key_id"]):
            raise WorkspacePersistenceError("Legal analysis changed during read.", code="revision_conflict", public_status="conflict")
        authority.revalidate(actor_principal_id=snapshot["actor_principal_id"], workspace=self, require_owner=True)
        return {**payload, "case_id": case_id, "private_revision": snapshot["private_revision"],
            "session_revision": snapshot["session_revision"], "read_only": True}


    def bind_case_definition_correspondence(self, user_id: Optional[str], *, case_id: str,
                                   request: Mapping[str, Any]) -> Dict[str, Any]:
        """Replay current definition owners against a stored source and commit through the encrypted CAS.

        Request source/context/fact assertions are never the case's authority.
        Local compilation needs no model consent and performs no model egress.
        """
        from applications.legal_analysis_api import bind_current_case_definition_correspondence, LegalAnalysisError
        from integrations.private_storage import PrivateStorageError
        from mediator.workflow_service import WorkflowActionService

        authority = self._owner_case_authority()
        if authority is None or authority.action != "case.update" or not isinstance(request, Mapping):
            raise WorkspaceAuthorizationDenied()
        snapshot = self.read_case_legal_materials_snapshot(user_id, case_id=case_id)
        actor, canonical = snapshot["actor_principal_id"], snapshot["canonical_owner_principal_id"]
        for field, actual in (("expected_private_revision", snapshot["private_revision"]),
                              ("expected_session_revision", snapshot["session_revision"])):
            value = request.get(field)
            valid_type = (type(value) is str and 1 <= len(value) <= 19
                and value.isascii() and value.isdecimal() and (value == "0" or not value.startswith("0"))
                ) if field == "expected_private_revision" else type(value) is int
            if not valid_type or value != actual:
                raise WorkspacePersistenceError("Definition replay precondition changed.", code="revision_conflict", public_status="conflict")
        _context, admitted_key_id, admitted_key = self._joined_key(canonical, case_id)
        if admitted_key_id != snapshot["key_id"]:
            raise WorkspacePersistenceError("Definition replay key changed.", code="revision_conflict", public_status="conflict")

        def before_publish():
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _current, key_id, key = self._joined_key(canonical, case_id)
            if (key_id, key) != (admitted_key_id, admitted_key):
                raise WorkspacePersistenceError("Definition replay key changed.", code="revision_conflict", public_status="conflict")
            current = self._load_state(canonical, case_id=case_id)
            if self._case_legal_context_identity(current) != snapshot["source_identity"]:
                raise WorkspacePersistenceError("Definition replay source changed.", code="revision_conflict", public_status="conflict")
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _current, key_id, key = self._joined_key(canonical, case_id)
            if (key_id, key) != (admitted_key_id, admitted_key):
                raise WorkspacePersistenceError("Definition replay key changed.", code="revision_conflict", public_status="conflict")

        state = snapshot["state"]
        shared = state["shared_interview"]
        payload = bind_current_case_definition_correspondence(snapshot["case_file"], request,
            case_id=case_id, source_scope_sha256=snapshot["source_scope_sha256"])
        before_publish()
        if payload.get("status") != "bound":
            return {**payload, "binding_persisted": False,
                "private_revision": snapshot["private_revision"], "session_revision": snapshot["session_revision"]}
        case_file = deepcopy(snapshot["case_file"])
        case_file["definition_correspondence_binding"] = deepcopy(payload)
        projection = WorkflowActionService.project_legal_context_selection(shared,
            case_file=case_file, dependency_graph=snapshot["dependency_graph"])
        draft = deepcopy(state)
        draft["shared_interview"] = projection
        draft["updated_at"] = _utc_now()
        try:
            committed = self._commit_joined_snapshot(draft, before_publish=before_publish)
        except PrivateStorageError as exc:
            raise WorkspacePersistenceError("Definition replay did not commit.",
                code=str(getattr(exc, "code", "") or "durability_unproven"), public_status="recoverable") from None
        self._interview_mediators.pop((canonical, case_id), None)
        authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
        return {**payload, "binding_persisted": True,
            "private_revision": committed.get("private_revision"), "session_revision": projection["session_revision"]}


    def refresh_case_legal_dependency_graph(self, user_id, *, case_id, updates):
        return self._run_case_legal_dependency_refresh(user_id, case_id=case_id, updates=updates, late=False)

    def revalidate_case_legal_dependency_refresh(self, user_id, *, case_id, updates):
        return self._run_case_legal_dependency_refresh(user_id, case_id=case_id, updates=updates, late=True)

    def _run_case_legal_dependency_refresh(self, user_id, *, case_id, updates, late):
        """Run the canonical source/DG owner on a copied, current private DTO."""
        from applications.legal_research_api import (LegalResearchError, _purpose_decision,
            _require_purpose_consent, verified_reviewed_source_records)
        from complaint_phases.phase_manager import ComplaintPhase
        from complaint_phases.dependency_graph import DependencyGraph
        from integrations.private_storage import PrivateStorageError
        from mediator.workflow_service import WorkflowActionService

        authority = self._owner_case_authority()
        if authority is None or authority.action != "case.update" or not isinstance(updates, Mapping):
            raise WorkspaceAuthorizationDenied()
        # The server owns the source manifest and all graph-producing inputs.
        if any(name in updates for name in ("canonical_source_records", "source_records", "links", "questions",
                "proof_obligations", "successors", "model_output", "result")):
            raise LegalResearchError("caller_graph_rows_not_accepted")
        snapshot = self.read_case_legal_materials_snapshot(user_id, case_id=case_id)
        actor, canonical = snapshot["actor_principal_id"], snapshot["canonical_owner_principal_id"]
        decision = authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
        for field, actual in (("expected_private_revision", snapshot["private_revision"]),
                ("expected_session_revision", snapshot["session_revision"]),
                ("expected_source_scope_sha256", snapshot["source_scope_sha256"])):
            if field in updates and updates[field] != actual:
                raise WorkspacePersistenceError("Dependency source changed.", code="revision_conflict", public_status="conflict")
        records = verified_reviewed_source_records(snapshot["case_file"], source_scope_sha256=snapshot["source_scope_sha256"])
        hashes = sorted({record["metadata"]["source_hash"] for group in records.values() for record in group})
        if "legal_source_hashes" in updates and updates["legal_source_hashes"] != hashes:
            raise LegalResearchError("legal_research_revision_conflict")
        purpose = "citation_acquisition"
        view = authority.processing_consent(purpose=purpose, actor_principal_id=actor, workspace=self)
        generation = _purpose_decision(view, purpose).get("generation")
        _require_purpose_consent(authority, self, purpose, generation, "cache")
        _ctx, admitted_key_id, admitted_key = self._joined_key(canonical, case_id)
        if admitted_key_id != snapshot["key_id"]:
            raise WorkspacePersistenceError("Dependency key changed.", code="revision_conflict", public_status="conflict")

        def revalidate_publication():
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _live, key_id, key = self._joined_key(canonical, case_id)
            if (key_id, key) != (admitted_key_id, admitted_key):
                raise WorkspacePersistenceError("Dependency key changed.", code="revision_conflict", public_status="conflict")
            _require_purpose_consent(authority, self, purpose, generation, "cache")
            current = self._load_state(canonical, case_id=case_id)
            if self._case_legal_context_identity(current) != snapshot["source_identity"]:
                raise WorkspacePersistenceError("Dependency source changed.", code="revision_conflict", public_status="conflict")
            authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
            _live, key_id, key = self._joined_key(canonical, case_id)
            if (key_id, key) != (admitted_key_id, admitted_key):
                raise WorkspacePersistenceError("Dependency key changed.", code="revision_conflict", public_status="conflict")

        revalidate_publication()
        shared = snapshot["state"]["shared_interview"]
        mediator = self._mediator_for_shared_interview(canonical, case_id, cache=False)
        mediator.workflow_actions.restore_session_projection(deepcopy(shared))
        workflow = mediator.workflow_actions
        common = {"case_id": case_id, "actor_principal_id": actor, "case_revision": decision.revision,
            "consent_generation": generation, "consent_revoked": False,
            "grant_revision": decision.membership_revision, "granted_actions": ["case.update"],
            "legal_source_hashes": hashes, "operation_id": updates.get("operation_id")}
        if late:
            receipt = workflow.accept_legal_refresh_late_result(**common,
                dependency_generation=(snapshot["case_file"].get("legal_graph_refresh") or {}).get("dependency_generation", 0),
                claimed=deepcopy(dict(updates)))
            revalidate_publication()
            return {**receipt, "read_only": True, "private_revision": snapshot["private_revision"],
                "session_revision": snapshot["session_revision"]}
        receipt = workflow.refresh_legal_dependency_graph(**common,
            correction_kind=updates.get("correction_kind"),
            expected_case_revision=updates.get("expected_case_revision"),
            expected_consent_generation=updates.get("expected_consent_generation"),
            expected_grant_revision=updates.get("expected_grant_revision"),
            expected_dependency_generation=updates.get("expected_dependency_generation"),
            canonical_source_records=records)
        revalidate_publication()
        if receipt.get("status") != "applied" or receipt.get("replayed") is True:
            return {**receipt, "private_revision": snapshot["private_revision"], "session_revision": snapshot["session_revision"]}
        case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
        graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
        if not isinstance(case_file, dict) or not isinstance(graph, DependencyGraph):
            raise WorkspacePersistenceError("Dependency refresh unavailable.", code="legal_research_unavailable", public_status="unavailable")
        projection = WorkflowActionService.project_legal_context_selection(shared, case_file=case_file, dependency_graph=graph)
        draft = deepcopy(snapshot["state"])
        draft["shared_interview"] = projection
        draft["updated_at"] = _utc_now()
        try:
            committed = self._commit_joined_snapshot(draft, before_publish=revalidate_publication)
        except PrivateStorageError as exc:
            raise WorkspacePersistenceError("Dependency refresh did not commit.", code=str(getattr(exc, "code", "") or "durability_unproven"), public_status="recoverable") from None
        self._interview_mediators.pop((canonical, case_id), None)
        authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
        return {**receipt, "private_revision": committed.get("private_revision"), "session_revision": projection["session_revision"]}

    def run_legal_research(
        self,
        user_id: Optional[str],
        *,
        local_rows: Optional[Dict[str, Any]] = None,
        cancelled: bool = False,
        retrieval_mode: str = "cache",
        storage_available: Optional[bool] = None,
        context_updates: Optional[Dict[str, Any]] = None,
        dependency_change: Optional[Dict[str, Any]] = None,
        effect_receipt: Optional[Dict[str, Any]] = None,
        expected_graph_revision: Optional[str] = None,
        expected_session_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run one deliberate legal-research action for the saved case.

        Status and resume do not call this. Replaying the same action returns
        the stored receipt and does not acquire or admit again. The receipt is
        not an intake answer.
        """

        gui_authority = self._owner_case_authority()
        if gui_authority is not None:
            from applications.legal_research_api import LegalResearchError, _purpose_decision
            try:
                if context_updates or dependency_change or effect_receipt or storage_available is not None:
                    raise LegalResearchError("explicit_legal_research_request_required")
                actor, selected_case = gui_authority.actor_principal_id, gui_authority.case_id
                snapshot = self.read_case_legal_research_snapshot(actor, case_id=selected_case)
                case_file = snapshot["state"]["shared_interview"]["intake_case_file"]
                claims = case_file.get("candidate_claims") or []
                claim = next((str(row.get("claim_type") or "").strip() for row in claims
                    if isinstance(row, dict) and str(row.get("claim_type") or "").strip() not in {"", "unknown"}), "")
                if not claim:
                    raise LegalResearchError("legal_context_not_ready")
                view = gui_authority.processing_consent(purpose="citation_acquisition", actor_principal_id=actor, workspace=self)
                generation = _purpose_decision(view, "citation_acquisition").get("generation")
                request = {"purpose": "citation_acquisition", "query": claim.replace("_", " ") + " statute",
                    "retrieval_mode": retrieval_mode, "local_rows": local_rows,
                    "cancelled": bool(cancelled), "max_results": 5, "max_bytes": 4096, "deadline_seconds": 5.0,
                    "expected_consent_generation": generation}
                if local_rows is None:
                    prior_receipt = case_file.get("legal_source_candidate_receipt") or {}
                    operations = case_file.get("legal_source_operations") or {}
                    prior = operations.get(prior_receipt.get("operation_id")) if isinstance(operations, dict) else None
                    prior_request = prior.get("request") if isinstance(prior, dict) else None
                    if (isinstance(prior_request, dict) and prior.get("source_scope_sha256") == snapshot["source_scope_sha256"]
                            and all(prior_request.get(name) == request.get(name) for name in
                                ("purpose", "query", "retrieval_mode", "cancelled", "expected_consent_generation"))):
                        # An issued /research shortcut may replay an actual
                        # owned cache request. It never reconstructs source
                        # provenance or pretends an unavailable asset exists.
                        request = deepcopy(prior_request)
                if not request.get("operation_id"):
                    request["operation_id"] = hashlib.sha256(json.dumps({"source": snapshot["source_scope_sha256"],
                        "request": request}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
                if expected_graph_revision is not None:
                    request["expected_graph_revision"] = expected_graph_revision
                if expected_session_revision is not None:
                    request["expected_session_revision"] = expected_session_revision
                receipt = self.acquire_case_legal_research(actor, case_id=selected_case, request=request)
                counts = {"retrieved": int(receipt.get("candidate_count") or 0), "admitted": 0,
                    "rejected": int(receipt.get("research_gap_count") or 0),
                    "unavailable": int(receipt.get("status") in {"unavailable", "timeout", "error", "refused", "blocked"})}
                result = {**receipt, "action": "legal_research", "acquisition_status": receipt.get("status"),
                    "admission_status": "not_admitted", "counts": counts, "proves_complaint": False,
                    "stored_as_answer": False, "legal_sufficiency": False, "proof": False,
                    "fingerprint": request["operation_id"], "next_action": "continue_pending_inquiry"}
                result["display"] = format_legal_research_result(result)
                return result
            except LegalResearchError as exc:
                return self._legal_research_failure(exc.code, public_status="refused")
            except WorkspacePersistenceError as exc:
                return self._legal_research_failure("stale_research" if exc.code == "revision_conflict" else exc.code,
                    public_status="refused" if exc.code == "revision_conflict" else exc.public_status)

        resolved = self._check_access(str(user_id or DEFAULT_USER_ID), ability="write")
        try:
            state = self._load_state(resolved)
        except WorkspacePersistenceError as exc:
            return self._legal_research_failure(exc.code or "unavailable", public_status=exc.public_status)
        case_id = _state_case_id(state, resolved)
        narrative = _narrative_record(state)
        narrative_text = str(narrative.get("text") or "")
        claim_type = str(state.get("claim_type") or "termination")
        claims = [{"type": claim_type, "name": claim_type, "claim_type": claim_type}]
        case_file = {
            "source_complaint_text": narrative_text,
            "candidate_claims": list(claims),
        }
        storage_available = self._legal_research_storage_available() if storage_available is None else bool(storage_available)
        fingerprint = self._legal_research_fingerprint(
            case_id=case_id,
            narrative_text=narrative_text,
            claim_type=claim_type,
            local_rows=local_rows,
            storage_available=storage_available,
            cancelled=cancelled,
            retrieval_mode=retrieval_mode,
            context_updates=context_updates,
            dependency_change=dependency_change,
            effect_receipt=effect_receipt,
        )
        stored = state.get("legal_research") if isinstance(state.get("legal_research"), dict) else {}
        receipts = stored.get("receipts") if isinstance(stored.get("receipts"), dict) else {}
        stale = self._legal_research_stale(
            state,
            expected_graph_revision=expected_graph_revision,
            expected_session_revision=expected_session_revision,
        )
        if stale is not None:
            stale["fingerprint"] = fingerprint
            stale["display"] = "Stale concurrent research rejected. The pending inquiry was kept."
            return stale
        pending_operation = stored.get("pending_operation") if isinstance(stored.get("pending_operation"), dict) else None
        if (
            isinstance(pending_operation, dict)
            and pending_operation.get("fingerprint") == fingerprint
            and pending_operation.get("dispatched") is True
            and not isinstance(receipts.get(fingerprint), dict)
        ):
            receipt = self._legal_research_failure("interrupted_operation", public_status="unavailable")
            receipt["replayed"] = True
            receipt["dispatched"] = False
            receipt["fingerprint"] = fingerprint
            receipt["next_action"] = "continue_pending_inquiry"
            receipt["display"] = format_legal_research_result(receipt)
            self._store_legal_research_receipt(state, fingerprint, receipt)
            try:
                self._save_state(state)
            except WorkspacePersistenceError as exc:
                return self._legal_research_failure(exc.code or "durability_unproven", public_status=exc.public_status)
            return receipt
        previous = receipts.get(fingerprint)
        if isinstance(previous, dict):
            replay = dict(previous)
            replay["replayed"] = True
            replay["dispatched"] = False
            replay["stored_as_answer"] = False
            replay["proves_complaint"] = False
            replay["legal_sufficiency"] = False
            replay["proof"] = False
            replay["display"] = format_legal_research_result(replay)
            return replay
        answers_before = deepcopy(state.get("intake_answers") or {})
        history_before = deepcopy(state.get("intake_history") or [])
        legal_research = state.setdefault("legal_research", {})
        if not isinstance(legal_research, dict):
            legal_research = {}
            state["legal_research"] = legal_research
        legal_research["pending_operation"] = {
            "kind": "legal_research",
            "fingerprint": fingerprint,
            "status": "claimed",
            "dispatched": True,
        }
        legal_research["dispatch_count"] = int(legal_research.get("dispatch_count") or 0) + 1
        try:
            self._save_state(state)
        except WorkspacePersistenceError as exc:
            return self._legal_research_failure(exc.code or "durability_unproven", public_status=exc.public_status)
        mediator = None
        try:
            from complaint_phases.intake_case_file import apply_explicit_legal_context
            from complaint_phases.phase_manager import ComplaintPhase

            mediator = self._mediator_for_shared_interview(resolved, case_id)
            if isinstance(context_updates, dict) and context_updates:
                phase_case = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
                if isinstance(phase_case, dict) and phase_case:
                    mediator.apply_explicit_legal_context(phase_case, **context_updates)
                case_file = apply_explicit_legal_context(case_file, **context_updates)
            if isinstance(effect_receipt, dict):
                mediator._pending_legal_effect_receipt = dict(effect_receipt)
            if isinstance(dependency_change, dict):
                mediator._pending_legal_dependency_change = dict(dependency_change)
            receipt = mediator.workflow_actions.research_legal_source_gap(
                user_id=resolved,
                case_id=case_id,
                intake_case_file=case_file,
                claims=claims,
                query_terms=[f"{claim_type} statute"],
                local_rows=local_rows,
                retrieval_mode=retrieval_mode,
                storage_available=storage_available,
                cancelled=cancelled,
                operation_id=fingerprint,
            )
        except WorkspacePersistenceError as exc:
            return self._legal_research_failure(exc.code or "unavailable", public_status=exc.public_status)
        except Exception:
            receipt = self._legal_research_failure("acquisition_unavailable", public_status="unavailable")
        self._legal_research_dispatch_count = int(getattr(self, "_legal_research_dispatch_count", 0) or 0) + 1
        receipt = dict(receipt)
        receipt["stored_as_answer"] = False
        receipt["proves_complaint"] = False
        receipt["legal_sufficiency"] = False
        receipt["proof"] = False
        receipt["fingerprint"] = fingerprint
        receipt["display"] = format_legal_research_result(receipt)
        refresh = None
        if mediator is not None:
            from complaint_phases.phase_manager import ComplaintPhase

            refresh = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "verified_dependency_refresh")
            pending_change = getattr(mediator, "_pending_legal_dependency_change", None)
            if isinstance(pending_change, dict) and pending_change:
                mediator._pending_legal_dependency_change = None
                if pending_change.get("source_outage") or pending_change.get("version_changed") or pending_change.get("treatment_changed") or pending_change.get("jurisdiction_changed") or pending_change.get("date_changed"):
                    refresh = mediator.refresh_verified_legal_dependencies(pending_change)
        if isinstance(refresh, dict):
            receipt["dependency_refresh"] = {
                "affected_node_ids": list(refresh.get("affected_node_ids") or []),
                "preserved_node_ids": list(refresh.get("preserved_node_ids") or []),
                "case_revision": refresh.get("case_revision"),
                "atomic_case_revision": refresh.get("atomic_case_revision"),
                "source_outage": bool(refresh.get("source_outage")),
                "graph_replaced": False,
                "empty_success": False,
                "effect_request_id": refresh.get("effect_request_id") or "",
                "source_admission_reread": bool(refresh.get("source_admission_reread")),
            }
        state["intake_answers"] = answers_before
        state["intake_history"] = history_before
        self._store_legal_research_receipt(state, fingerprint, receipt)
        try:
            self._save_state(state)
        except WorkspacePersistenceError as exc:
            failed = self._legal_research_failure(exc.code or "durability_unproven", public_status=exc.public_status)
            failed["counts"] = dict(receipt.get("counts") or failed["counts"])
            failed["dispatched"] = True
            return failed
        return receipt

    def _store_legal_research_receipt(self, state: Dict[str, Any], fingerprint: str, receipt: Mapping[str, Any]) -> None:
        legal_research = state.setdefault("legal_research", {})
        if not isinstance(legal_research, dict):
            legal_research = {}
            state["legal_research"] = legal_research
        legal_receipts = legal_research.setdefault("receipts", {})
        if not isinstance(legal_receipts, dict):
            legal_receipts = {}
            legal_research["receipts"] = legal_receipts
        legal_receipts[fingerprint] = {key: value for key, value in dict(receipt).items() if key != "display"}
        legal_research["latest_fingerprint"] = fingerprint
        legal_research["pending_operation"] = None

    def _legal_research_stale(
        self,
        state: Mapping[str, Any],
        *,
        expected_graph_revision: Optional[str],
        expected_session_revision: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        if expected_graph_revision is None and expected_session_revision is None:
            return None
        projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), Mapping) else {}
        current_session = int(projection.get("session_revision") or 0) if isinstance(projection, Mapping) else 0
        current_token = ""
        graph = projection.get("knowledge_graph") if isinstance(projection, Mapping) else None
        if isinstance(graph, Mapping):
            try:
                from complaint_phases.knowledge_graph import KnowledgeGraph
                from mediator.hook_runtime import graph_revision_token

                current_token = graph_revision_token(KnowledgeGraph.from_dict(dict(graph)))
            except Exception:
                current_token = ""
        token_mismatch = expected_graph_revision is not None and str(expected_graph_revision) != current_token
        session_mismatch = expected_session_revision is not None and int(expected_session_revision) != current_session
        if not token_mismatch and not session_mismatch:
            return None
        receipt = self._legal_research_failure("stale_research", public_status="refused")
        receipt["status"] = "refused"
        receipt["error_code"] = "stale_research"
        receipt["dispatched"] = False
        receipt["replayed"] = False
        receipt["next_action"] = "continue_pending_inquiry"
        receipt["counts"] = {"retrieved": 0, "admitted": 0, "rejected": 0, "unavailable": 0}
        return receipt

    def _legal_research_storage_available(self) -> bool:
        cache = self._session_dir / "legal-source-cache"
        try:
            if cache.exists() and not cache.is_dir():
                return False
            if not cache.exists():
                cache.mkdir(mode=0o700)
            return cache.is_dir()
        except OSError:
            return False

    @staticmethod
    def _legal_research_fingerprint(
        *,
        case_id: str,
        narrative_text: str,
        claim_type: str,
        local_rows: Optional[Dict[str, Any]],
        storage_available: bool,
        cancelled: bool,
        retrieval_mode: str,
        context_updates: Optional[Dict[str, Any]] = None,
        dependency_change: Optional[Dict[str, Any]] = None,
        effect_receipt: Optional[Dict[str, Any]] = None,
    ) -> str:
        corpus = json.dumps(local_rows, sort_keys=True, default=str) if local_rows is not None else ""
        body = json.dumps(
            {
                "cancelled": bool(cancelled),
                "case_id": case_id,
                "claim_type": claim_type,
                "context_updates": context_updates or {},
                "corpus": corpus,
                "dependency_change": dependency_change or {},
                "effect_request_id": str((effect_receipt or {}).get("request_id") or ""),
                "narrative": narrative_text,
                "retrieval_mode": retrieval_mode,
                "storage_available": bool(storage_available),
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    @staticmethod
    def _legal_research_failure(code: str, *, public_status: str) -> Dict[str, Any]:
        next_action = "unlock_private_case" if public_status == "unlock_needed" else "retry_unavailable"
        receipt = {
            "action": "legal_research",
            "operation": "acquire_bounded_canonical_sources+admit_acquired_authorities",
            "stored_as_answer": False,
            "proves_complaint": False,
            "legal_sufficiency": False,
            "replayed": False,
            "dispatched": False,
            "status": "unavailable" if public_status != "unlock_needed" else "unlock_needed",
            "error_code": str(code or "unavailable"),
            "counts": {"retrieved": 0, "admitted": 0, "rejected": 0, "unavailable": 1},
            "next_action": next_action,
            "resumable": True,
            "worker_stalled": False,
            "proof": False,
        }
        receipt["display"] = format_legal_research_result(receipt)
        return receipt

    def save_evidence(
        self,
        user_id: Optional[str],
        *,
        kind: str,
        claim_element_id: str,
        title: str,
        content: str,
        source: Optional[str] = None,
        attachment_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self.request_handlers.save_evidence(
            user_id,
            kind=kind,
            claim_element_id=claim_element_id,
            title=title,
            content=content,
            source=source,
            attachment_names=attachment_names,
        )

    async def upload_local_evidence_files(
        self,
        user_id: Optional[str],
        *,
        files: List[Any],
        claim_element_id: str = "causation",
        kind: str = "document",
        evidence_root: Optional[str] = None,
        note: Optional[str] = None,
        note_title: Optional[str] = None,
        source: Optional[str] = "dashboard-chat-upload",
    ) -> Dict[str, Any]:
        self._require_local_filesystem_access()
        return await self.request_handlers.upload_local_evidence_files(
            user_id,
            files=files,
            claim_element_id=claim_element_id,
            kind=kind,
            evidence_root=evidence_root,
            note=note,
            note_title=note_title,
            source=source,
        )

    @classmethod
    def _build_document_annotation_knowledge_graph(cls, annotations: List[Dict[str, Any]]) -> Dict[str, Any]:
        entities: Dict[str, Dict[str, Any]] = {}
        relationships: Dict[str, Dict[str, Any]] = {}

        def add_entity(entity_id: str, entity_type: str, label: str, metadata: Optional[Dict[str, Any]] = None) -> None:
            current = entities.setdefault(
                entity_id,
                {
                    "id": entity_id,
                    "type": entity_type,
                    "label": label,
                    "metadata": {},
                },
            )
            current["label"] = current.get("label") or label
            current["metadata"].update(dict(metadata or {}))

        def add_relationship(
            relationship_id: str,
            relationship_type: str,
            source: str,
            target: str,
            metadata: Optional[Dict[str, Any]] = None,
        ) -> None:
            relationships[relationship_id] = {
                "id": relationship_id,
                "type": relationship_type,
                "source": source,
                "target": target,
                "metadata": dict(metadata or {}),
            }

        for annotation in annotations:
            annotation_id = str(annotation.get("id") or "").strip()
            if not annotation_id:
                continue
            document_id = str(annotation.get("document_id") or "").strip() or "unknown-document"
            claim_element_id = str(annotation.get("claim_element_id") or "").strip() or "causation"
            user_metadata = dict(annotation.get("user_metadata") or {})
            actor_user_id = str(user_metadata.get("user_id") or annotation.get("user_id") or DEFAULT_USER_ID)
            actor_label = str(user_metadata.get("display_name") or actor_user_id)
            annotation_node_id = f"annotation:{_slugify_graph_id(annotation_id)}"
            document_node_id = f"document:{_slugify_graph_id(document_id)}"
            user_node_id = f"user:{_slugify_graph_id(actor_user_id)}"
            claim_node_id = f"claim-element:{_slugify_graph_id(claim_element_id)}"

            add_entity(
                document_node_id,
                "document",
                str(annotation.get("document_title") or document_id),
                {
                    "document_id": document_id,
                    "dataset_kind": annotation.get("dataset_kind"),
                    "document_metadata": dict(annotation.get("document_metadata") or {}),
                },
            )
            add_entity(
                annotation_node_id,
                "annotation",
                str(annotation.get("title") or "Document annotation"),
                {
                    "annotation_id": annotation_id,
                    "note": annotation.get("note"),
                    "created_at": annotation.get("created_at"),
                    "evidence_id": annotation.get("evidence_id"),
                    "user_metadata": user_metadata,
                },
            )
            add_entity(user_node_id, "user", actor_label, user_metadata)
            add_entity(claim_node_id, "claim_element", claim_element_id.replace("_", " ").title(), {"claim_element_id": claim_element_id})
            add_relationship(
                f"{annotation_node_id}->annotates->{document_node_id}",
                "annotates",
                annotation_node_id,
                document_node_id,
                {"created_at": annotation.get("created_at")},
            )
            add_relationship(
                f"{annotation_node_id}->created_by->{user_node_id}",
                "created_by",
                annotation_node_id,
                user_node_id,
                {"created_at": annotation.get("created_at")},
            )
            add_relationship(
                f"{annotation_node_id}->supports_claim_element->{claim_node_id}",
                "supports_claim_element",
                annotation_node_id,
                claim_node_id,
                {"claim_element_id": claim_element_id},
            )

            for tag in _normalize_annotation_tags(annotation.get("tags") or []):
                tag_node_id = f"tag:{_slugify_graph_id(tag)}"
                add_entity(
                    tag_node_id,
                    "tag",
                    tag,
                    {
                        "tag": tag,
                        "tagged_by_user_id": actor_user_id,
                        "tagged_by": user_metadata,
                        "created_at": annotation.get("created_at"),
                    },
                )
                add_relationship(
                    f"{document_node_id}->tagged_with->{tag_node_id}",
                    "tagged_with",
                    document_node_id,
                    tag_node_id,
                    {"annotation_id": annotation_id, "created_at": annotation.get("created_at")},
                )
                add_relationship(
                    f"{tag_node_id}->applied_by->{user_node_id}",
                    "tag_applied_by",
                    tag_node_id,
                    user_node_id,
                    {"annotation_id": annotation_id, "created_at": annotation.get("created_at")},
                )

        return {
            "entities": list(entities.values()),
            "relationships": list(relationships.values()),
            "annotation_count": len([item for item in annotations if isinstance(item, dict)]),
            "tag_count": len([entity for entity in entities.values() if entity.get("type") == "tag"]),
            "source": "complaint_workspace_document_annotation_graph",
        }

    def tag_document_annotation(
        self,
        user_id: Optional[str],
        *,
        document_id: str,
        tags: Any,
        note: str,
        claim_element_id: str = "causation",
        title: str = "Dataset document annotation",
        dataset_kind: str = "dataset",
        document_title: Optional[str] = None,
        document_text_preview: Optional[str] = None,
        document_metadata: Optional[Dict[str, Any]] = None,
        user_metadata: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        normalized_document_id = str(document_id or "").strip()
        if not normalized_document_id:
            raise ValueError("document_id is required to tag or annotate a document.")
        normalized_note = str(note or "").strip()
        if not normalized_note:
            raise ValueError("note is required to tag or annotate a document.")

        normalized_tags = _normalize_annotation_tags(tags)
        state = self._load_state(resolved_user_id)
        evidence_store = state.setdefault("evidence", {"testimony": [], "documents": []})
        documents = evidence_store.setdefault("documents", [])
        created_at = _utc_now()
        evidence_record = {
            "id": f"documents-{len(documents) + 1}",
            "kind": "document",
            "claim_element_id": str(claim_element_id or "causation"),
            "title": str(title or "Dataset document annotation"),
            "content": [
                f"Dataset: {str(dataset_kind or 'dataset')}",
                f"Document ID: {normalized_document_id}",
                f"Document title: {document_title}" if document_title else "",
                f"Document text preview: {str(document_text_preview or '')[:500]}" if document_text_preview else "",
                f"Tags: {', '.join(normalized_tags)}" if normalized_tags else "",
                f"Review note: {normalized_note}",
            ],
            "source": source or f"dashboard-{str(dataset_kind or 'dataset')}-dataset-annotation",
            "attachment_names": [normalized_document_id],
            "saved_at": created_at,
            "metadata": {
                "document_id": normalized_document_id,
                "dataset_kind": str(dataset_kind or "dataset"),
                "tags": normalized_tags,
                "annotation_user_metadata": dict(user_metadata or {}),
                "document_metadata": dict(document_metadata or {}),
            },
        }
        evidence_record["content"] = "\n".join(part for part in evidence_record["content"] if part)
        documents.append(evidence_record)

        actor_metadata = {
            "user_id": resolved_user_id,
            **{key: value for key, value in dict(user_metadata or {}).items() if value not in (None, "")},
        }
        actor_metadata.setdefault("display_name", resolved_user_id)
        actor_metadata.setdefault("role", "workspace reviewer")
        annotation_record = {
            "id": f"document-annotation-{len(list(state.get('document_annotations') or [])) + 1}",
            "document_id": normalized_document_id,
            "dataset_kind": str(dataset_kind or "dataset"),
            "document_title": str(document_title or normalized_document_id),
            "document_text_preview": str(document_text_preview or "")[:500],
            "document_metadata": dict(document_metadata or {}),
            "claim_element_id": str(claim_element_id or "causation"),
            "title": str(title or "Dataset document annotation"),
            "note": normalized_note,
            "tags": normalized_tags,
            "user_id": resolved_user_id,
            "user_metadata": actor_metadata,
            "evidence_id": evidence_record["id"],
            "source": evidence_record["source"],
            "created_at": created_at,
        }
        annotations = state.setdefault("document_annotations", [])
        annotations.append(annotation_record)
        annotation_graph = self._build_document_annotation_knowledge_graph(list(annotations))
        workspace_index = self._build_workspace_annotation_index(list(annotations))
        state["annotation_knowledge_graph"] = annotation_graph
        state["workspace_annotation_index"] = workspace_index
        self._save_state(state)
        return {
            "saved": evidence_record,
            "annotation": annotation_record,
            "annotation_tags": normalized_tags,
            "annotation_knowledge_graph": annotation_graph,
            "workspace_annotation_index": workspace_index,
            "review": self._build_review(state),
            "session": deepcopy(state),
            "case_synopsis": self._build_case_synopsis(state),
            "source": "complaint_workspace_document_annotation_tags",
        }

    @classmethod
    def _build_workspace_annotation_index(cls, annotations: List[Dict[str, Any]]) -> Dict[str, Any]:
        index: Dict[str, Any] = {
            "by_tag": {},
            "by_collection": {},
            "by_document_type": {},
            "by_claim_element": {},
            "workspace_annotation_count": 0,
            "source": "complaint_workspace_dataset_annotation_index",
        }

        def add(bucket_name: str, key: Any, annotation: Dict[str, Any]) -> None:
            normalized_key = str(key or "").strip() or "unclassified"
            bucket = index.setdefault(bucket_name, {})
            bucket.setdefault(normalized_key, []).append(
                {
                    "annotation_id": annotation.get("id"),
                    "document_id": annotation.get("document_id"),
                    "document_title": annotation.get("document_title"),
                    "tags": list(annotation.get("tags") or []),
                    "user_metadata": dict(annotation.get("user_metadata") or {}),
                    "created_at": annotation.get("created_at"),
                }
            )

        for annotation in annotations:
            if not isinstance(annotation, dict) or str(annotation.get("dataset_kind") or "").lower() != "workspace":
                continue
            index["workspace_annotation_count"] += 1
            metadata = dict(annotation.get("document_metadata") or {})
            add("by_collection", metadata.get("collection_id") or annotation.get("collection_id"), annotation)
            add("by_document_type", metadata.get("document_type") or annotation.get("document_type"), annotation)
            add("by_claim_element", annotation.get("claim_element_id"), annotation)
            for tag in _normalize_annotation_tags(annotation.get("tags") or []):
                add("by_tag", tag, annotation)
        return index

    def tag_workspace_dataset_document(
        self,
        user_id: Optional[str],
        *,
        document_id: str,
        tags: Any,
        note: str,
        claim_element_id: str = "causation",
        title: str = "Workspace dataset document annotation",
        document_title: Optional[str] = None,
        document_text_preview: Optional[str] = None,
        collection_id: Optional[str] = None,
        document_type: Optional[str] = None,
        claim_type: Optional[str] = None,
        source_type: Optional[str] = None,
        document_metadata: Optional[Dict[str, Any]] = None,
        user_metadata: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        metadata = dict(document_metadata or {})
        for key, value in {
            "collection_id": collection_id,
            "document_type": document_type,
            "claim_type": claim_type,
            "source_type": source_type,
        }.items():
            if value not in (None, ""):
                metadata[key] = value
        payload = self.tag_document_annotation(
            user_id,
            document_id=document_id,
            tags=tags,
            note=note,
            claim_element_id=claim_element_id,
            title=title,
            dataset_kind="workspace",
            document_title=document_title,
            document_text_preview=document_text_preview,
            document_metadata=metadata,
            user_metadata=user_metadata,
            source=source or "dashboard-workspace-dataset-annotation",
        )
        state = dict(payload.get("session") or {})
        annotations = list(state.get("document_annotations") or [])
        workspace_index = self._build_workspace_annotation_index(annotations)
        state["workspace_annotation_index"] = workspace_index
        self._save_state(state)
        payload["session"] = deepcopy(state)
        payload["workspace_annotation_index"] = workspace_index
        payload["source"] = "complaint_workspace_dataset_document_annotation"
        return payload

    def get_document_annotation_graph(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        annotations = list(state.get("document_annotations") or [])
        annotation_graph = self._build_document_annotation_knowledge_graph(annotations)
        workspace_index = self._build_workspace_annotation_index(annotations)
        state["annotation_knowledge_graph"] = annotation_graph
        state["workspace_annotation_index"] = workspace_index
        self._save_state(state)
        return {
            "user_id": str(state.get("user_id") or user_id or DEFAULT_USER_ID),
            "document_annotations": annotations,
            "annotation_knowledge_graph": annotation_graph,
            "workspace_annotation_index": workspace_index,
            "source": "complaint_workspace_document_annotation_graph",
        }

    def get_workspace_dataset_annotation_index(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        annotations = list(state.get("document_annotations") or [])
        workspace_index = self._build_workspace_annotation_index(annotations)
        state["workspace_annotation_index"] = workspace_index
        self._save_state(state)
        return {
            "user_id": str(state.get("user_id") or user_id or DEFAULT_USER_ID),
            "workspace_annotations": [
                annotation
                for annotation in annotations
                if isinstance(annotation, dict) and str(annotation.get("dataset_kind") or "").lower() == "workspace"
            ],
            "workspace_annotation_index": workspace_index,
            "source": "complaint_workspace_dataset_annotation_index",
        }

    def import_gmail_evidence(
        self,
        user_id: Optional[str],
        *,
        addresses: List[str],
        collect_all_messages: bool = False,
        claim_element_id: str = "causation",
        folder: str = "INBOX",
        folders: Optional[List[str]] = None,
        limit: Optional[int] = None,
        date_after: Optional[str] = None,
        date_before: Optional[str] = None,
        years_back: Optional[int] = None,
        evidence_root: Optional[str] = None,
        gmail_user: Optional[str] = None,
        gmail_app_password: Optional[str] = None,
        use_gmail_oauth: bool = False,
        gmail_oauth_client_secrets: Optional[str] = None,
        gmail_oauth_token_cache: Optional[str] = None,
        gmail_oauth_open_browser: bool = True,
        complaint_query: Optional[str] = None,
        complaint_keywords: Optional[List[str]] = None,
        min_relevance_score: float = 0.0,
        use_uid_checkpoint: bool = False,
        checkpoint_name: Optional[str] = None,
        uid_window_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._require_local_filesystem_access()
        async def _run_import() -> Dict[str, Any]:
            from integrations.ipfs_datasets.legal_data import load_legal_symbol

            import_gmail_evidence_upstream = load_legal_symbol("import_gmail_evidence", module="email_import")

            return await import_gmail_evidence_upstream(
                addresses=addresses,
                collect_all_messages=collect_all_messages,
                user_id=str(user_id or DEFAULT_USER_ID),
                claim_element_id=claim_element_id,
                workspace_root=self._session_dir,
                evidence_root=Path(evidence_root) if evidence_root else None,
                folder=folder,
                folders=folders or [],
                limit=limit,
                date_after=date_after,
                date_before=date_before,
                years_back=years_back,
                gmail_user=gmail_user,
                gmail_app_password=gmail_app_password,
                use_gmail_oauth=use_gmail_oauth,
                gmail_oauth_client_secrets=gmail_oauth_client_secrets,
                gmail_oauth_token_cache=gmail_oauth_token_cache,
                gmail_oauth_open_browser=gmail_oauth_open_browser,
                complaint_query=complaint_query,
                complaint_keywords=complaint_keywords or [],
                min_relevance_score=min_relevance_score,
                use_uid_checkpoint=use_uid_checkpoint,
                checkpoint_name=checkpoint_name,
                uid_window_size=uid_window_size,
                service=self,
            )

        return anyio.run(_run_import)

    def run_gmail_duckdb_pipeline(
        self,
        user_id: Optional[str],
        *,
        addresses: List[str],
        collect_all_messages: bool = False,
        claim_element_id: str = "causation",
        folder: str = "INBOX",
        folders: Optional[List[str]] = None,
        years_back: Optional[int] = 2,
        date_after: Optional[str] = None,
        date_before: Optional[str] = None,
        complaint_query: Optional[str] = None,
        complaint_keywords: Optional[List[str]] = None,
        min_relevance_score: float = 0.0,
        evidence_root: Optional[str] = None,
        gmail_user: Optional[str] = None,
        gmail_app_password: Optional[str] = None,
        use_gmail_oauth: bool = False,
        gmail_oauth_client_secrets: Optional[str] = None,
        gmail_oauth_token_cache: Optional[str] = None,
        gmail_oauth_open_browser: bool = True,
        checkpoint_name: str = "gmail-duckdb-pipeline",
        uid_window_size: int = 500,
        duckdb_build_every_batches: int = 10,
        max_batches: int = 20,
        duckdb_output_dir: Optional[str] = None,
        append_to_existing_corpus: bool = False,
        bm25_search_query: Optional[str] = None,
        bm25_search_limit: int = 20,
    ) -> Dict[str, Any]:
        self._require_local_filesystem_access()
        async def _run_pipeline() -> Dict[str, Any]:
            from integrations.ipfs_datasets.legal_data import load_legal_symbol

            run_gmail_duckdb_pipeline_upstream = load_legal_symbol("run_gmail_duckdb_pipeline", module="email_pipeline")

            return await run_gmail_duckdb_pipeline_upstream(
                user_id=str(user_id or DEFAULT_USER_ID),
                addresses=addresses,
                collect_all_messages=collect_all_messages,
                claim_element_id=claim_element_id,
                folder=folder,
                folders=folders or [],
                years_back=years_back,
                date_after=date_after,
                date_before=date_before,
                complaint_query=complaint_query,
                complaint_keywords=complaint_keywords or [],
                min_relevance_score=min_relevance_score,
                workspace_root=self._session_dir,
                evidence_root=Path(evidence_root) if evidence_root else None,
                gmail_user=gmail_user,
                gmail_app_password=gmail_app_password,
                use_gmail_oauth=use_gmail_oauth,
                gmail_oauth_client_secrets=gmail_oauth_client_secrets,
                gmail_oauth_token_cache=gmail_oauth_token_cache,
                gmail_oauth_open_browser=gmail_oauth_open_browser,
                checkpoint_name=checkpoint_name,
                uid_window_size=uid_window_size,
                duckdb_build_every_batches=duckdb_build_every_batches,
                max_batches=max_batches,
                duckdb_output_dir=duckdb_output_dir,
                append_to_existing_corpus=append_to_existing_corpus,
                bm25_search_query=bm25_search_query,
                bm25_search_limit=bm25_search_limit,
            )

        return anyio.run(_run_pipeline)

    def search_email_duckdb_corpus(
        self,
        *,
        index_path: str,
        query: str,
        limit: int = 20,
        ranking: str = "bm25",
        bm25_k1: float = 1.2,
        bm25_b: float = 0.75,
    ) -> Dict[str, Any]:
        self._require_local_filesystem_access()
        from integrations.ipfs_datasets.legal_data import load_legal_symbol

        search_email_duckdb_corpus_upstream = load_legal_symbol("search_email_duckdb_corpus", module="email_pipeline")

        return search_email_duckdb_corpus_upstream(
            index_path=index_path,
            query=query,
            limit=limit,
            ranking=ranking,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b,
        )

    def import_local_evidence(
        self,
        user_id: Optional[str],
        *,
        paths: List[str],
        claim_element_id: str = "causation",
        kind: str = "document",
        evidence_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._require_local_filesystem_access()
        from complaint_generator.local_evidence_import import import_local_evidence

        return import_local_evidence(
            paths=paths,
            user_id=str(user_id or DEFAULT_USER_ID),
            claim_element_id=claim_element_id,
            kind=kind,
            workspace_root=self._session_dir,
            evidence_root=Path(evidence_root) if evidence_root else None,
            service=self,
        )

    def generate_complaint(
        self,
        user_id: Optional[str],
        *,
        requested_relief: Optional[List[str]] = None,
        title_override: Optional[str] = None,
        use_llm: bool = False,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config_path: Optional[str] = None,
        backend_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.request_handlers.generate_complaint(
            user_id,
            requested_relief=requested_relief,
            title_override=title_override,
            use_llm=use_llm,
            provider=provider,
            model=model,
            config_path=config_path,
            backend_id=backend_id,
        )

    def update_draft(
        self,
        user_id: Optional[str],
        *,
        title: Optional[str] = None,
        body: Optional[str] = None,
        requested_relief: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self.request_handlers.update_draft(
            user_id,
            title=title,
            body=body,
            requested_relief=requested_relief,
        )

    def update_case_synopsis(self, user_id: Optional[str], synopsis: Optional[str]) -> Dict[str, Any]:
        return self.request_handlers.update_case_synopsis(user_id, synopsis)

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parent.parent

    @staticmethod
    def _safe_read_json_file(path: Path) -> Dict[str, Any]:
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _safe_read_toml_file(path: Path) -> Dict[str, Any]:
        try:
            payload = tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _safe_read_git_ref(path: Path, ref: str) -> str:
        if not path.exists() or not path.is_dir():
            return "unavailable"
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", ref],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            repo_root = Path(__file__).resolve().parent.parent
            try:
                relative_path = path.resolve().relative_to(repo_root.resolve())
                fallback = subprocess.run(
                    ["git", "-C", str(repo_root), "ls-tree", "HEAD", str(relative_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                parts = [part for part in str(fallback.stdout or "").strip().split() if part]
                if len(parts) >= 3 and re.fullmatch(r"[0-9a-f]{40}", parts[2]):
                    return parts[2]
            except Exception:
                pass
            # Return unavailable if the path is not usable, the git ref is missing/non-git, or the command times out.
            return "unavailable"
        value = (result.stdout or "").strip()
        return value or "unavailable"

    @classmethod
    def _ipfs_project_file(cls, ipfs_root: Path) -> Path:
        # ipfs_datasets_py currently ships a non-standard "__pyproject.toml" file upstream.
        project_file = ipfs_root / "__pyproject.toml"
        if not project_file.exists():
            project_file = ipfs_root / "pyproject.toml"
        return project_file

    @classmethod
    def _resolve_mike_grounding_mode(cls, override: Optional[str] = None) -> str:
        candidate = str(override or os.getenv("COMPLAINT_MIKE_GROUNDING_MODE") or DEFAULT_MIKE_GROUNDING_MODE).strip().lower()
        return candidate or DEFAULT_MIKE_GROUNDING_MODE

    @staticmethod
    def _mike_connector_url() -> str:
        configured = str(os.getenv("COMPLAINT_MCP_CONNECTOR_URL") or "").strip()
        return configured or DEFAULT_COMPLAINT_MCP_CONNECTOR_URL

    @staticmethod
    def _mike_connector_setup_text(router_available: bool) -> str:
        connector_url = ComplaintWorkspaceService._mike_connector_url()
        registration = (
            "Mike registers this connector with Streamable HTTP on a public https URL. "
            "http://localhost and private addresses are rejected by Mike. "
            "Path: /api/complaint-workspace/mcp/rpc. "
            "Tools: complaint.generate_grounded_text, complaint.search_corpus, "
            "complaint.get_handoff, complaint.sync_draft. "
            "Set COMPLAINT_MCP_AUTH_TOKEN and put the same bearer token in the Mike connector auth config. "
            "The mike-llm-router-patch-v1 stamp is compatibility-only and does not intercept Mike LLM calls. "
            f"Connector URL: {connector_url}."
        )
        if router_available:
            availability = (
                "Register this complaint-generator MCP connector in Mike. "
                "Grounded drafting calls complaint.generate_grounded_text. "
                "The accelerate routers are available. "
            )
        else:
            availability = (
                "The MCP connector and accelerate routers are unavailable. "
                "Register the connector URL when the accelerate checkout can be imported. "
            )
        return f"{availability}{registration}"

    @staticmethod
    def _document_version_content_sha256(title: str, body: str) -> str:
        return hashlib.sha256((str(title or "") + str(body or "")).encode("utf-8")).hexdigest()

    @classmethod
    def _build_mike_router_policy_snapshot(cls) -> Dict[str, Any]:
        status = _llm_router_status_snapshot()
        return {
            "adapter": "complaint_generator.integrations.ipfs_datasets.llm.generate_text_with_metadata",
            "status": str(status.get("status") or "unavailable"),
            "backend_available": bool(status.get("backend_available")),
            "provider_policy_source": "complaint_generator",
            "requested_provider": os.getenv("COMPLAINT_LLM_PROVIDER") or DEFAULT_LLM_DRAFT_PROVIDER,
            "requested_model": os.getenv("COMPLAINT_LLM_MODEL") or DEFAULT_LLM_DRAFT_MODELS_BY_PROVIDER.get(DEFAULT_LLM_DRAFT_PROVIDER, ""),
            "fallback_chain": list(DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN),
            "provider_timeouts": deepcopy(DEFAULT_LLM_DRAFT_TIMEOUTS_BY_PROVIDER),
            "centralized_policy": {
                "router_selection_in_workspace": True,
                "model_selection_in_workspace": True,
                "safety_policy_in_workspace": True,
                "grounding_policy_in_workspace": True,
            },
            "narrow_adapter_boundary": {
                "mike_requests_generation_via_workspace": True,
                "mike_does_not_choose_provider": True,
                "mike_does_not_choose_model": True,
            },
        }

    @classmethod
    def _build_mike_skill_asset_manifest(cls) -> Dict[str, Any]:
        assets = [deepcopy(item) for item in DEFAULT_MIKE_SKILL_ASSET_MANIFEST]
        return {
            "version": MIKE_SKILL_ASSET_MANIFEST_VERSION,
            "asset_count": len(assets),
            "asset_ids": [str(item.get("skill_asset_id") or "").strip() for item in assets if str(item.get("skill_asset_id") or "").strip()],
            "assets": assets,
        }

    @classmethod
    def _build_mike_corpus_lane_adapters(cls) -> List[Dict[str, Any]]:
        capabilities = {
            "legal_corpus_review",
            "legal_corpus_search",
            "strict_containment_policy",
            "authority_graph_enrichment",
        }
        def _extract_manifest_field(item: Mapping[str, Any], key: str) -> str:
            return (item.get(key) or "").strip()

        adapters: List[Dict[str, Any]] = []
        for item in DEFAULT_MIKE_SKILL_ASSET_MANIFEST:
            adapter = _extract_manifest_field(item, "adapter")
            capability = _extract_manifest_field(item, "capability")
            if adapter and capability in capabilities:
                adapters.append(
                    {
                        "adapter": adapter,
                        "capability": capability,
                    }
                )
        return adapters

    @staticmethod
    def _build_mike_base_draft_identity(draft: Mapping[str, Any]) -> Dict[str, Any]:
        draft_payload = {
            "title": str((draft or {}).get("title") or "").strip() or None,
            "body": str((draft or {}).get("body") or ""),
            "updated_at": str((draft or {}).get("updated_at") or "").strip() or None,
            "draft_strategy": str((draft or {}).get("draft_strategy") or "").strip() or None,
            "sync_source": str((draft or {}).get("sync_source") or "").strip() or None,
        }
        hash_payload = json.dumps(draft_payload, sort_keys=True, default=str).encode("utf-8")
        return {
            **draft_payload,
            "hash": hashlib.sha256(hash_payload).hexdigest(),
        }

    @staticmethod
    def _build_mike_redline_metadata(
        *,
        redline_summary: Optional[str],
        structured_deltas: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        summary = str(redline_summary or "").strip() or None
        return {
            "summary": summary,
            "structured_delta_count": len(structured_deltas),
            "has_structured_redlines": bool(structured_deltas),
        }

    @classmethod
    def _build_mike_submodule_inventory(cls) -> Dict[str, Any]:
        repo_root = cls._repo_root()
        mike_root = _prefer_checkout(repo_root, "mike")
        ipfs_root = _prefer_checkout(repo_root, "ipfs_datasets_py")
        accelerate_root = _prefer_checkout(repo_root, "ipfs_accelerate_py")
        kit_root = _prefer_checkout(repo_root, "ipfs_kit_py")
        mike_frontend_package = cls._safe_read_json_file(mike_root / "frontend" / "package.json")
        mike_backend_package = cls._safe_read_json_file(mike_root / "backend" / "package.json")
        ipfs_pyproject = cls._safe_read_toml_file(cls._ipfs_project_file(ipfs_root))
        skill_asset_manifest = cls._build_mike_skill_asset_manifest()
        frontend_src = mike_root / "frontend" / "src"
        backend_src = mike_root / "backend" / "src"
        editor_modules = [
            "frontend/src/app/components/projects/ProjectWorkspace.tsx",
            "frontend/src/app/components/projects/ProjectDocumentsView.tsx",
            "frontend/src/app/components/assistant/CaseLawPanel.tsx",
            "frontend/src/app/components/shared/views/DocxView.tsx",
            "frontend/src/app/lib/mikeApi.ts",
            "backend/src/routes/documents.ts",
            "backend/src/routes/chat.ts",
            "backend/src/routes/caseLaw.ts",
            "backend/src/lib/mcp/client.ts",
        ]
        existing_editor_modules = [path for path in editor_modules if (mike_root / path).is_file()]
        editor_module_inventory = [
            {"path": path, "path_found": (mike_root / path).is_file()}
            for path in editor_modules
        ]
        return {
            "strategy": {
                "mike": "external/mike@origin/main",
                "ipfs_datasets_py": "external/ipfs_datasets_py@origin/main",
                "ipfs_accelerate_py": "external/ipfs_accelerate_py@origin/main",
                "ipfs_kit_py": "external/ipfs_kit_py@origin/main",
                "workspace_adapters": "promote_stable_contracts_inside_complaint_generator",
                "editor_assets_decoupled_from_legal_processors": True,
            },
            "mike": {
                "available": mike_root.is_dir() and (mike_root / "README.md").exists(),
                "root": str(mike_root),
                "commit": cls._safe_read_git_ref(mike_root, "HEAD"),
                "origin_main_commit": cls._safe_read_git_ref(mike_root, "origin/main"),
                "frontend_package_name": str(mike_frontend_package.get("name") or ""),
                "backend_package_name": str(mike_backend_package.get("name") or ""),
                "frontend_dependencies": sorted(dict(mike_frontend_package.get("dependencies") or {}).keys())[:20],
                "backend_dependencies": sorted(dict(mike_backend_package.get("dependencies") or {}).keys())[:20],
                "editor_modules": existing_editor_modules,
                "editor_module_inventory": editor_module_inventory,
                "editor_module_count": len(existing_editor_modules),
                "skill_assets": deepcopy(skill_asset_manifest.get("assets") or []),
                "skill_asset_count": int(skill_asset_manifest.get("asset_count") or 0),
                "skill_asset_manifest_version": str(skill_asset_manifest.get("version") or ""),
                "upgrade_path": [
                    "refresh_submodule",
                    "recompute_compatibility_matrix",
                    "verify_mike_contract_tests",
                    "re-run_release_gate_regression",
                ],
            },
            "ipfs_datasets_py": {
                "available": ipfs_root.is_dir() and (ipfs_root / "README.md").exists(),
                "root": str(ipfs_root),
                "commit": cls._safe_read_git_ref(ipfs_root, "HEAD"),
                "origin_main_commit": cls._safe_read_git_ref(ipfs_root, "origin/main"),
                "python_project_name": str(((ipfs_pyproject.get("project") or {}).get("name") or "")),
                "logic_bridge_present": (ipfs_root / "ipfs_datasets_py" / "logic").exists(),
                "legal_processors_present": (ipfs_root / "ipfs_datasets_py" / "processors" / "legal_data").exists(),
                "theorem_bridge_present": (ipfs_root / "ipfs_datasets_py" / "logic" / "external_provers").exists(),
                "legal_search_sources": _legal_source_availability_snapshot(),
                "upgrade_path": [
                    "refresh_submodule",
                    "verify_adapter_imports",
                    "run_workspace_logic_regression",
                    "re-run_strict_grounding_tests",
                ],
            },
            "ipfs_accelerate_py": {
                "available": accelerate_root.is_dir() and (accelerate_root / "README.md").exists(),
                "root": str(accelerate_root),
                "commit": cls._safe_read_git_ref(accelerate_root, "HEAD"),
                "origin_main_commit": cls._safe_read_git_ref(accelerate_root, "origin/main"),
            },
            "ipfs_kit_py": {
                "available": kit_root.is_dir() and (kit_root / "README.md").exists(),
                "root": str(kit_root),
                "commit": cls._safe_read_git_ref(kit_root, "HEAD"),
                "origin_main_commit": cls._safe_read_git_ref(kit_root, "origin/main"),
            },
            "workspace_adapter_boundary": {
                "router_adapter": "integrations/ipfs_datasets/llm.py",
                "legal_adapter": "integrations/ipfs_datasets/legal.py",
                "logic_adapter": "integrations/ipfs_datasets/logic.py",
                "storage_adapter": "integrations/ipfs_datasets/storage.py",
                "graph_adapter": "integrations/ipfs_datasets/graphs.py",
                "multimedia_adapter": "integrations/ipfs_datasets/multimedia.py",
                "accelerate_router_facade": "integrations/ipfs_accelerate/routers.py",
                "workspace_contract_owner": "applications/complaint_workspace.py",
            },
        }

    @classmethod
    def _build_mike_compatibility_target_matrix(cls) -> Dict[str, Any]:
        repo_root = cls._repo_root()
        mike_root = _prefer_checkout(repo_root, "mike")
        ipfs_root = _prefer_checkout(repo_root, "ipfs_datasets_py")
        accelerate_root = _prefer_checkout(repo_root, "ipfs_accelerate_py")
        kit_root = _prefer_checkout(repo_root, "ipfs_kit_py")
        complaint_pyproject = cls._safe_read_toml_file(repo_root / "pyproject.toml")
        mike_frontend_package = cls._safe_read_json_file(mike_root / "frontend" / "package.json")
        mike_backend_package = cls._safe_read_json_file(mike_root / "backend" / "package.json")
        ipfs_pyproject = cls._safe_read_toml_file(cls._ipfs_project_file(ipfs_root))
        complaint_project = dict(complaint_pyproject.get("project") or {})
        ipfs_project = dict(ipfs_pyproject.get("project") or {})
        return {
            "python": {
                "complaint_generator_requires_python": str(complaint_project.get("requires-python") or ""),
                "complaint_generator_dependencies": list(complaint_project.get("dependencies") or []),
                "ipfs_datasets_py_requires_python": str(ipfs_project.get("requires-python") or ""),
                "ipfs_datasets_py_dependencies": list(ipfs_project.get("dependencies") or [])[:20],
            },
            "node": {
                "mike_frontend_dependencies": dict(mike_frontend_package.get("dependencies") or {}),
                "mike_backend_dependencies": dict(mike_backend_package.get("dependencies") or {}),
            },
            "api_contracts": {
                "workspace_handoff_contract": MIKE_HANDOFF_CONTRACT_VERSION,
                "workspace_sync_contract": MIKE_SYNC_CONTRACT_VERSION,
                "workspace_status_contract": MIKE_STATUS_CONTRACT_VERSION,
                "mike_editor_role": "editing_surface_only",
                "workspace_source_of_truth": "complaint_generator_session_state",
            },
            "submodule_shas": {
                "mike_commit": cls._safe_read_git_ref(mike_root, "HEAD"),
                "mike_origin_main_commit": cls._safe_read_git_ref(mike_root, "origin/main"),
                "ipfs_datasets_py_commit": cls._safe_read_git_ref(ipfs_root, "HEAD"),
                "ipfs_datasets_py_origin_main_commit": cls._safe_read_git_ref(ipfs_root, "origin/main"),
                "ipfs_accelerate_py_commit": cls._safe_read_git_ref(accelerate_root, "HEAD"),
                "ipfs_accelerate_py_origin_main_commit": cls._safe_read_git_ref(accelerate_root, "origin/main"),
                "ipfs_kit_py_commit": cls._safe_read_git_ref(kit_root, "HEAD"),
                "ipfs_kit_py_origin_main_commit": cls._safe_read_git_ref(kit_root, "origin/main"),
            },
            "config_expectations": {
                "complaint_mike_base_url_env": "COMPLAINT_MIKE_BASE_URL",
                "complaint_mike_grounding_mode_env": "COMPLAINT_MIKE_GROUNDING_MODE",
                "complaint_mcp_connector_url_env": "COMPLAINT_MCP_CONNECTOR_URL",
                "workspace_router_provider_env": "COMPLAINT_LLM_PROVIDER",
                "workspace_router_model_env": "COMPLAINT_LLM_MODEL",
            },
            "skill_asset_manifest_version": MIKE_SKILL_ASSET_MANIFEST_VERSION,
        }

    @staticmethod
    def _classify_mike_assertion_type(text: str) -> str:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return "unsupported_rhetoric"
        if any(token in lowered for token in ("relief", "damages", "injunction", "fees", "declare", "prayer")):
            return "requested_relief"
        if any(token in lowered for token in MIKE_TEMPORAL_ASSERTION_KEYWORDS):
            return "temporal_assertion"
        if any(token in lowered for token in ("violat", "retaliat", "discriminat", "breach", "unlawful", "entitled", "liable")):
            return "legal_conclusion"
        if len(lowered.split()) < MIN_MIKE_FACTUAL_ASSERTION_WORDS:
            return "unsupported_rhetoric"
        return "factual_statement"

    @classmethod
    def _derive_mike_assertion_annotations(cls, body: str) -> List[Dict[str, Any]]:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(body or ""))
            if sentence.strip()
        ]
        annotations: List[Dict[str, Any]] = []
        for index, sentence in enumerate(sentences, start=1):
            assertion_type = cls._classify_mike_assertion_type(sentence)
            annotations.append(
                {
                    "assertion_id": f"assertion-{index:03d}",
                    "text": sentence,
                    "paragraph_id": f"paragraph-{index:03d}",
                    "assertion_type": assertion_type,
                    "grounded": False,
                    "authority_ids": [],
                    "fact_ids": [],
                    "support_strength": "unknown",
                    "extra_corpus": False,
                    "unsupported": assertion_type in MIKE_SUBSTANTIVE_ASSERTION_TYPES,
                }
            )
        return annotations

    @classmethod
    def _normalize_mike_assertion_annotations(
        cls,
        assertion_annotations: Optional[List[Dict[str, Any]]],
        *,
        body: str,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        source_items = list(assertion_annotations or []) or cls._derive_mike_assertion_annotations(body)
        for index, item in enumerate(source_items, start=1):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            assertion_type = str(item.get("assertion_type") or cls._classify_mike_assertion_type(text)).strip().lower() or "factual_statement"
            authority_ids = [str(value).strip() for value in list(item.get("authority_ids") or []) if str(value).strip()]
            fact_ids = [str(value).strip() for value in list(item.get("fact_ids") or []) if str(value).strip()]
            grounded = bool(item.get("grounded")) or bool(authority_ids or fact_ids)
            unsupported = bool(item.get("unsupported")) or (assertion_type in MIKE_SUBSTANTIVE_ASSERTION_TYPES and not grounded)
            normalized.append(
                {
                    "assertion_id": str(item.get("assertion_id") or f"assertion-{index:03d}").strip(),
                    "text": text,
                    "paragraph_id": str(item.get("paragraph_id") or f"paragraph-{index:03d}").strip(),
                    "assertion_type": assertion_type,
                    "grounded": grounded,
                    "authority_ids": authority_ids,
                    "fact_ids": fact_ids,
                    "support_strength": str(item.get("support_strength") or ("grounded" if grounded else "unknown")).strip().lower(),
                    "extra_corpus": bool(item.get("extra_corpus")),
                    "unsupported": unsupported,
                }
            )
        return normalized

    @staticmethod
    def _normalize_mike_authority_links(authority_links: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in list(authority_links or []):
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "authority_id": str(item.get("authority_id") or item.get("citation") or "").strip(),
                    "authority_type": str(item.get("authority_type") or item.get("type") or "").strip() or "authority",
                    "citation": str(item.get("citation") or "").strip(),
                    "source": str(item.get("source") or "").strip(),
                    "assertion_ids": [str(value).strip() for value in list(item.get("assertion_ids") or []) if str(value).strip()],
                    "provenance": deepcopy(item.get("provenance") or {}),
                }
            )
        return [item for item in normalized if item["authority_id"]]

    @classmethod
    def _normalize_mike_sync_provenance(
        cls,
        sync_provenance: Optional[Mapping[str, Any]],
        *,
        base_draft_identity: Optional[Mapping[str, Any]] = None,
        redline_metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = dict(sync_provenance or {})
        skill_asset_ids = [
            str(value).strip()
            for value in list(payload.get("skill_asset_ids") or payload.get("enabled_skill_ids") or [])
            if str(value).strip()
        ]
        known_skill_asset_ids = set(cls._build_mike_skill_asset_manifest().get("asset_ids") or [])
        enabled_skill_ids = [value for value in skill_asset_ids if value in known_skill_asset_ids]
        unknown_skill_asset_ids = [value for value in skill_asset_ids if value not in known_skill_asset_ids]
        base_identity = dict(base_draft_identity or {})
        payload_base_identity = payload.get("base_draft_identity")
        if isinstance(payload_base_identity, Mapping):
            base_identity.update(dict(payload_base_identity))
        base_draft_hash = str(payload.get("base_draft_hash") or base_identity.get("hash") or "").strip() or None
        normalized_redline_metadata = dict(redline_metadata or {})
        payload_redline_metadata = payload.get("redline_metadata")
        if isinstance(payload_redline_metadata, Mapping):
            normalized_redline_metadata.update(dict(payload_redline_metadata))
        return {
            "editor_version": str(payload.get("editor_version") or "").strip() or None,
            "skill_asset_ids": skill_asset_ids,
            "enabled_skill_ids": enabled_skill_ids,
            "unknown_skill_asset_ids": unknown_skill_asset_ids,
            "skill_asset_manifest_version": MIKE_SKILL_ASSET_MANIFEST_VERSION,
            "base_draft_hash": base_draft_hash,
            "base_draft_identity": {
                "title": str(base_identity.get("title") or "").strip() or None,
                "updated_at": str(base_identity.get("updated_at") or "").strip() or None,
                "draft_strategy": str(base_identity.get("draft_strategy") or "").strip() or None,
                "sync_source": str(base_identity.get("sync_source") or "").strip() or None,
                "hash": base_draft_hash,
            },
            "redline_metadata": {
                "summary": str(normalized_redline_metadata.get("summary") or "").strip() or None,
                "structured_delta_count": int(normalized_redline_metadata.get("structured_delta_count") or 0),
                "has_structured_redlines": bool(normalized_redline_metadata.get("has_structured_redlines")),
            },
            "source_transport": str(payload.get("source_transport") or "").strip() or None,
            "upstream_project": str(payload.get("upstream_project") or "mike").strip(),
        }

    @staticmethod
    def _resolve_mike_base_url(override: Optional[str] = None) -> str:
        candidate = str(override or os.getenv("COMPLAINT_MIKE_BASE_URL") or "").strip()
        if not candidate:
            candidate = "http://localhost:3000"
        return candidate.rstrip("/")

    @staticmethod
    def _build_mike_launch_url(base_url: str, query: Mapping[str, str]) -> str:
        parsed = urlsplit(str(base_url or "").strip())
        path = parsed.path or "/"
        return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(dict(query)), parsed.fragment))

    @staticmethod
    def _mike_transport_warning(base_url: str) -> Optional[str]:
        parsed = urlsplit(str(base_url or "").strip())
        hostname = str(parsed.hostname or "").strip().lower()
        if parsed.scheme == "http" and hostname not in {"localhost", "127.0.0.1", "::1"}:
            return (
                "Mike launch URL is using plain HTTP on a non-localhost host. "
                "Prefer HTTPS for production deployments."
            )
        return None

    @staticmethod
    def _summarize_mike_evidence_context(state: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
        evidence = dict(state.get("evidence") or {})
        testimony = list(evidence.get("testimony") or [])
        documents = list(evidence.get("documents") or [])
        support_matrix = list((review or {}).get("support_matrix") or [])
        testimony_by_element: Dict[str, List[Dict[str, Any]]] = {}
        for item in testimony:
            element_id = str((item or {}).get("claim_element_id") or "").strip()
            if not element_id:
                continue
            testimony_by_element.setdefault(element_id, []).append(item)
        documents_by_element: Dict[str, List[Dict[str, Any]]] = {}
        for item in documents:
            element_id = str((item or {}).get("claim_element_id") or "").strip()
            if not element_id:
                continue
            documents_by_element.setdefault(element_id, []).append(item)
        evidence_by_element: Dict[str, Dict[str, Any]] = {}
        for element in support_matrix:
            element_id = str((element or {}).get("id") or "").strip()
            if not element_id:
                continue
            matching_testimony = list(testimony_by_element.get(element_id) or [])
            matching_documents = list(documents_by_element.get(element_id) or [])
            samples = [
                str((item or {}).get("title") or "").strip()
                for item in (matching_testimony + matching_documents)
                if str((item or {}).get("title") or "").strip()
            ][:3]
            evidence_by_element[element_id] = {
                "label": str((element or {}).get("label") or element_id),
                "supported": bool((element or {}).get("supported")),
                "testimony_count": len(matching_testimony),
                "document_count": len(matching_documents),
                "sample_titles": samples,
            }
        return {
            "testimony_count": len(testimony),
            "document_count": len(documents),
            "elements": evidence_by_element,
            "missing_element_ids": [
                str((element or {}).get("id") or "").strip()
                for element in support_matrix
                if not bool((element or {}).get("supported"))
            ],
        }

    @classmethod
    def _build_mike_corpus_boundaries(
        cls,
        *,
        claim_type: str,
        grounding_mode: str,
    ) -> Dict[str, Any]:
        return {
            "claim_type": claim_type,
            "grounding_mode": grounding_mode,
            "strict_legal_containment": grounding_mode in STRICT_MIKE_GROUNDING_MODES,
            "allowed_authority_families": [
                "federal_statutes",
                "federal_regulations",
                "case_law",
                "state_statutes",
                "administrative_rules",
            ],
            "adapter_lane": cls._build_mike_corpus_lane_adapters(),
            "canonical_source_adapters": {
                "legal_search": "integrations/ipfs_datasets/legal.py",
                "corpus_search": "integrations/ipfs_datasets/search.py",
                "containment_policy": "integrations/ipfs_datasets/policy_rules.py",
                "authority_graph": "integrations/ipfs_datasets/graphs.py",
                "formal_logic": "integrations/ipfs_datasets/logic.py",
                "llm_router": "integrations/ipfs_datasets/llm.py",
            },
            "source_availability": _legal_source_availability_snapshot(),
        }

    @staticmethod
    def _build_claim_support_temporal_handoff_from_review(
        state: Mapping[str, Any],
        review: Mapping[str, Any],
    ) -> Dict[str, Any]:
        intake_answers = dict(state.get("intake_answers") or {})
        overview = dict(review.get("overview") or {})
        timeline_text = str(intake_answers.get("timeline") or "").strip()
        event_ids = [f"timeline-event-{index:03d}" for index, _ in enumerate(re.split(r"[;,]", timeline_text), start=1) if _.strip()]
        return {
            "contract_version": "claim_support_temporal_handoff_v1",
            "claim_type": str(review.get("claim_type") or state.get("claim_type") or "retaliation"),
            "claim_element_id": "case_timeline",
            "unresolved_temporal_issue_count": 0 if timeline_text else 1,
            "chronology_task_count": 0 if timeline_text else 1,
            "event_ids": event_ids,
            "temporal_fact_ids": event_ids,
            "timeline_issue_ids": [] if timeline_text else [MIKE_MISSING_TIMELINE_ISSUE_ID],
            "temporal_issue_ids": [] if timeline_text else [MIKE_MISSING_TIMELINE_ISSUE_ID],
            "temporal_proof_objectives": [
                "preserve chronology between protected activity and adverse action",
            ],
            "review_missing_elements": int(overview.get("missing_elements") or 0),
        }

    @staticmethod
    def _build_mike_reasoning_predicates(
        *,
        state: Mapping[str, Any],
        review: Mapping[str, Any],
        assertion_annotations: List[Dict[str, Any]],
        authority_links: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        claim_type = str(review.get("claim_type") or state.get("claim_type") or "retaliation")
        support_matrix = list((review or {}).get("support_matrix") or [])
        predicates: List[Dict[str, Any]] = []
        for item in support_matrix:
            element_id = str((item or {}).get("id") or "").strip()
            label = str((item or {}).get("label") or element_id).strip()
            if not element_id:
                continue
            predicates.append(
                {
                    "predicate_id": f"claim-{element_id}",
                    "predicate_text": label,
                    "predicate_type": "claim_element",
                    "claim_type": claim_type,
                    "claim_element_id": element_id,
                    "claim_element_text": label,
                    "coverage_status": "supported" if bool((item or {}).get("supported")) else "missing",
                }
            )
        authority_ids = {item["authority_id"] for item in authority_links if item.get("authority_id")}
        for index, item in enumerate(assertion_annotations, start=1):
            assertion_type = str(item.get("assertion_type") or "factual_statement").strip()
            predicate_type = {
                "factual_statement": "support_trace",
                "legal_conclusion": "claim_element",
                "temporal_assertion": "temporal_fact",
                "requested_relief": "support_trace",
                "unsupported_rhetoric": "contradiction_candidate",
            }.get(assertion_type, "support_trace")
            predicate: Dict[str, Any] = {
                "predicate_id": str(item.get("assertion_id") or f"assertion-{index:03d}"),
                "predicate_text": str(item.get("text") or "").strip(),
                "predicate_type": predicate_type,
                "claim_type": claim_type,
                "authority_ids": [value for value in list(item.get("authority_ids") or []) if value in authority_ids] or list(item.get("authority_ids") or []),
                "grounded_fact_ids": list(item.get("fact_ids") or []),
            }
            if predicate_type == "support_trace":
                predicate["support_ref"] = str(item.get("paragraph_id") or predicate["predicate_id"])
                predicate["support_kind"] = assertion_type
                predicate["text"] = predicate["predicate_text"]
            elif predicate_type == "temporal_fact":
                predicate["fact_id"] = str(item.get("assertion_id") or predicate["predicate_id"])
                predicate["text"] = predicate["predicate_text"]
                predicate["start_date"] = str(item.get("start_date") or "").strip() or None
                predicate["end_date"] = str(item.get("end_date") or "").strip() or None
            elif predicate_type == "claim_element":
                predicate["claim_element_id"] = str(item.get("claim_element_id") or "edited_claim").strip()
                predicate["claim_element_text"] = predicate["predicate_text"]
                predicate["coverage_status"] = "supported" if bool(item.get("grounded")) else "missing"
            else:
                predicate["summary"] = predicate["predicate_text"]
                predicate["severity"] = "warning" if bool(item.get("unsupported")) else "info"
            predicates.append(predicate)
        return predicates

    @classmethod
    def _build_mike_legal_corpus_review(
        cls,
        *,
        claim_type: str,
        grounding_mode: str,
        assertion_annotations: List[Dict[str, Any]],
        authority_links: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        substantive = [item for item in assertion_annotations if str(item.get("assertion_type") or "") in MIKE_SUBSTANTIVE_ASSERTION_TYPES]
        grounded = [item for item in substantive if bool(item.get("grounded"))]
        unsupported = [item for item in substantive if bool(item.get("unsupported"))]
        weak = [
            item for item in grounded
            if str(item.get("support_strength") or "").strip().lower() in {"weak", "low", "unknown"}
        ]
        extra_corpus = [item for item in substantive if bool(item.get("extra_corpus"))]
        coverage_percent = int(round((len(grounded) / len(substantive)) * 100)) if substantive else None
        return {
            "claim_type": claim_type,
            "grounding_mode": grounding_mode,
            "strict_mode": grounding_mode in STRICT_MIKE_GROUNDING_MODES,
            "coverage_percent": coverage_percent,
            "substantive_assertion_count": len(substantive),
            "grounded_assertion_count": len(grounded),
            "unsupported_assertion_count": len(unsupported),
            "weak_grounding_count": len(weak),
            "extra_corpus_assertion_count": len(extra_corpus),
            "unsupported_assertions": deepcopy(unsupported[:MAX_MIKE_GROUNDING_EXAMPLES]),
            "weakly_grounded_assertions": deepcopy(weak[:MAX_MIKE_GROUNDING_EXAMPLES]),
            "extra_corpus_assertions": deepcopy(extra_corpus[:MAX_MIKE_GROUNDING_EXAMPLES]),
            "authority_count": len(authority_links),
            "authorities": deepcopy(authority_links[:MAX_MIKE_AUTHORITY_EXAMPLES]),
            "has_blockers": grounding_mode in STRICT_MIKE_GROUNDING_MODES and bool(unsupported or extra_corpus),
            "adapter_lane": cls._build_mike_corpus_lane_adapters(),
            "canonical_sources": _legal_source_availability_snapshot(),
        }

    @classmethod
    def _build_mike_logic_review(
        cls,
        *,
        state: Mapping[str, Any],
        review: Mapping[str, Any],
        assertion_annotations: List[Dict[str, Any]],
        authority_links: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        reasoning_payload = {
            "predicates": cls._build_mike_reasoning_predicates(
                state=state,
                review=review,
                assertion_annotations=assertion_annotations,
                authority_links=authority_links,
            ),
            "claim_support_temporal_handoff": cls._build_claim_support_temporal_handoff_from_review(state, review),
            "claim_reasoning_review": {
                str(review.get("claim_type") or state.get("claim_type") or "retaliation"): {
                    "unsupported_claim_elements": [
                        str((item or {}).get("id") or "").strip()
                        for item in list((review or {}).get("support_matrix") or [])
                        if str((item or {}).get("id") or "").strip() and not bool((item or {}).get("supported"))
                    ]
                }
            },
        }
        hybrid_reasoning = _run_hybrid_reasoning_safely(reasoning_payload)
        temporal_reasoning_payload = dict(hybrid_reasoning.get("temporal_reasoning_payload") or {})
        result = dict(hybrid_reasoning.get("result") or {})
        proof_artifact = dict(result.get("proof_artifact") or {})
        contradiction_count = int(result.get("contradiction_signal_count") or 0)
        chronology_blocked = bool(dict(result.get("theorem_export_metadata") or {}).get("chronology_blocked"))
        unsupported_claim_elements = list(
            (reasoning_payload.get("claim_reasoning_review") or {})
            .get(str(review.get("claim_type") or state.get("claim_type") or "retaliation"), {})
            .get("unsupported_claim_elements", [])
        )
        proof_status = str(proof_artifact.get("proof_status") or proof_artifact.get("status") or "needs_review")
        has_blockers = bool(
            unsupported_claim_elements
            or contradiction_count
            or chronology_blocked
            or proof_status in {"error", "failed", "violation", "needs_review"}
        )
        theorem_export_metadata = deepcopy(result.get("theorem_export_metadata") or {})
        leanstral_status = _leanstral_status_snapshot()
        leanstral_assist = {
            "eligible": has_blockers,
            "status": (
                "ready"
                if has_blockers and bool(leanstral_status.get("backend_available"))
                else "not_needed"
                if not has_blockers
                else "unavailable"
            ),
            "provider": str(leanstral_status.get("provider") or "ipfs_accelerate_py"),
            "model": str(leanstral_status.get("model") or "leanstral"),
            "bypass_release_gate": False,
            "proof_objectives": list(theorem_export_metadata.get("temporal_proof_objectives") or []),
            "unresolved_claim_element_ids": unsupported_claim_elements,
            "proposed_steps": [
                f"Ground unsupported claim element `{claim_id}` with authority-backed proof predicates."
                for claim_id in unsupported_claim_elements[:3]
            ]
            + (
                ["Resolve chronology blockers before retrying theorem export."]
                if chronology_blocked
                else []
            )
            + (
                ["Review contradiction candidates before requesting additional prover assistance."]
                if contradiction_count
                else []
            ),
        }
        return {
            "reasoning_payload": reasoning_payload,
            "hybrid_reasoning": hybrid_reasoning,
            "proof_status": proof_status,
            "proof_passed": not has_blockers and proof_status not in {"error", "failed", "violation"},
            "contradiction_count": contradiction_count,
            "chronology_blocked": chronology_blocked,
            "unsupported_claim_element_count": len(unsupported_claim_elements),
            "unsupported_claim_element_ids": unsupported_claim_elements,
            "temporal_formula_count": int(temporal_reasoning_payload.get("tdfol_formula_count") or 0),
            "dcec_formula_count": int(temporal_reasoning_payload.get("dcec_formula_count") or 0),
            "has_blockers": has_blockers,
            "theorem_export_metadata": theorem_export_metadata,
            "proof_artifact": proof_artifact,
            "leanstral_assist": leanstral_assist,
        }

    @staticmethod
    def _merge_draft_proof_report(
        logic_review: Dict[str, Any],
        draft_proof_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge *draft_proof_report* (from the pipeline) into *logic_review*.

        Pipeline values take precedence when they carry richer information
        (e.g. a concrete ``corpus_coverage_percent``), but existing values
        are preserved when the pipeline falls back to defaults.
        """
        merged = deepcopy(logic_review)
        # Only upgrade proof_status if pipeline returned something more specific.
        pipeline_status = str(draft_proof_report.get("proof_status") or "").strip()
        if pipeline_status and pipeline_status not in {"needs_review", ""}:
            merged["proof_status"] = pipeline_status
        # Merge contradiction counts additively.  Note: both sources independently
        # detect contradictions, so the sum may over-count if the same contradiction
        # is reported by both the existing logic_review and the pipeline.  This is
        # intentional — callers should treat the count as an upper bound.
        pipeline_contradictions = int(draft_proof_report.get("contradiction_count") or 0)
        merged["contradiction_count"] = int(merged.get("contradiction_count") or 0) + pipeline_contradictions
        # Chronology blocked is sticky.
        if draft_proof_report.get("chronology_blocked"):
            merged["chronology_blocked"] = True
        # Attach pipeline-specific fields.
        merged["ungrounded_assertions"] = list(draft_proof_report.get("ungrounded_assertions") or [])
        merged["corpus_coverage_percent"] = draft_proof_report.get("corpus_coverage_percent")
        merged["pipeline_norms"] = list(draft_proof_report.get("norms") or [])
        merged["pipeline_policy_violations"] = list(draft_proof_report.get("policy_violations") or [])
        merged["pipeline_policy_warnings"] = list(draft_proof_report.get("policy_warnings") or [])
        merged["draft_proof_pipeline_version"] = str(
            draft_proof_report.get("pipeline_version") or ""
        )
        # Re-compute has_blockers after merge.
        merged["has_blockers"] = bool(
            merged.get("has_blockers")
            or draft_proof_report.get("has_blockers")
            or merged.get("contradiction_count")
            or merged.get("chronology_blocked")
        )
        return merged

    @staticmethod
    def _normalize_mike_citation_links(citation_links: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Normalize Mike citation links to mutable dict rows.

        Non-dict inputs are ignored and dict entries are shallow-copied so downstream
        mutation cannot alter caller-provided payload objects.
        """
        return [dict(item) for item in list(citation_links or []) if isinstance(item, dict)]

    @staticmethod
    def _extract_mike_claim_element_id(item: Mapping[str, Any]) -> str:
        # Support both Mike payload conventions while preferring claim_element_id.
        return str((item.get("claim_element_id") or item.get("element_id") or "")).strip()

    @staticmethod
    def _extract_mike_citation_key(item: Mapping[str, Any]) -> str:
        for field in MIKE_CITATION_KEY_FIELD_PRECEDENCE:
            candidate = str(item.get(field) or "").strip()
            if candidate:
                return candidate
        return ""

    def _check_mike_citation_links(
        self,
        state: Dict[str, Any],
        citation_links: List[Dict[str, Any]],
        *,
        review: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Validate Mike citation links against claim elements and detect citation conflicts.

        Args:
            state: Current workspace state payload.
            citation_links: Citation-link objects supplied on Mike sync.
            review: Optional precomputed review payload to avoid recomputing support_matrix.

        Returns:
            Dict with total link count, known/unknown claim elements, per-citation conflicts,
            and an aggregate has_conflicts boolean.
        """
        review_payload = dict(review or {})
        if not review_payload:
            review_payload = self._build_review(state)
        support_matrix = list((review_payload or {}).get("support_matrix") or [])

        known_element_ids: Set[str] = set()
        for item in support_matrix:
            element_id = str((item or {}).get("id") or "").strip()
            if element_id:
                known_element_ids.add(element_id)
        normalized_links = self._normalize_mike_citation_links(citation_links)
        unknown_claim_element_ids: Set[str] = set()
        for item in normalized_links:
            claim_element_id = self._extract_mike_claim_element_id(item)
            if claim_element_id and claim_element_id not in known_element_ids:
                unknown_claim_element_ids.add(claim_element_id)
        citation_to_elements: Dict[str, Set[str]] = {}
        for item in normalized_links:
            citation_key = self._extract_mike_citation_key(item)
            claim_element_id = self._extract_mike_claim_element_id(item)
            if not citation_key or not claim_element_id:
                continue
            citation_to_elements.setdefault(citation_key, set()).add(claim_element_id)
        conflicts = [
            {
                "citation_id": citation_id,
                # Keep deterministic claim-element ordering for tests and downstream diffs.
                "claim_element_ids": sorted(claim_element_ids),
            }
            for citation_id, claim_element_ids in sorted(citation_to_elements.items())
            if len(claim_element_ids) > 1
        ]
        return {
            "total_links": len(normalized_links),
            "known_claim_element_ids": sorted(known_element_ids),
            "unknown_claim_element_ids": sorted(unknown_claim_element_ids),
            "conflicts": conflicts,
            "has_conflicts": bool(conflicts or unknown_claim_element_ids),
        }

    @staticmethod
    def _build_mike_workflow_state(
        *,
        latest_handoff_id: str,
        pending_sync: bool,
        has_mike_synced_draft: bool,
        has_citation_link_conflicts: bool,
    ) -> Dict[str, str]:
        if not latest_handoff_id:
            key = "not_handed_off"
            severity = "warn"
        elif pending_sync:
            key = "handoff_pending_sync"
            severity = "warn"
        elif has_mike_synced_draft and has_citation_link_conflicts:
            key = "synced_with_conflicts"
            severity = "warn"
        elif has_mike_synced_draft:
            key = "synced_clean"
            severity = "good"
        else:
            key = "handoff_pending_sync"
            severity = "warn"
        return {
            "key": key,
            "label": MIKE_WORKFLOW_STATE_LABELS.get(key, "Unknown"),
            "severity": severity,
        }

    @staticmethod
    def _derive_mike_recommended_action(
        *,
        workflow_state_key: str,
        has_citation_link_conflicts: bool,
    ) -> str:
        if workflow_state_key == "synced_with_conflicts" and has_citation_link_conflicts:
            return "Resolve conflicts in Mike and sync again before export."
        if workflow_state_key == "handoff_pending_sync":
            return "Latest Mike handoff has not been synced yet. Import the edited draft with complaint.sync_mike_final_draft."
        if workflow_state_key == "not_handed_off":
            return "Start with complaint.build_mike_handoff to open Mike with the current draft and evidence context."
        if workflow_state_key == "synced_clean":
            return "Mike sync is current. Continue export review and release-gate checks for filing readiness."
        return "A handoff exists. Sync the finalized Mike draft back into complaint-generator before export."

    @staticmethod
    def _build_mike_structured_packet_context(
        draft: Mapping[str, Any],
        review: Mapping[str, Any],
    ) -> Dict[str, Any]:
        draft_body = str((draft or {}).get("body") or "")
        paragraphs = [line.strip() for line in draft_body.splitlines() if line.strip()]
        paragraph_count_truncated = len(paragraphs) > MAX_MIKE_HANDOFF_PARAGRAPHS
        section_cards: List[Dict[str, Any]] = []
        for index, paragraph in enumerate(paragraphs[:MAX_MIKE_HANDOFF_PARAGRAPHS], start=1):
            section_cards.append(
                {
                    "section_id": f"section-{index:03d}",
                    "section_type": "draft_paragraph",
                    "paragraph_ids": [f"paragraph-{index:03d}"],
                    "paragraphs": [
                        {
                            "paragraph_id": f"paragraph-{index:03d}",
                            "text": paragraph,
                        }
                    ],
                }
            )
        support_matrix = list((review or {}).get("support_matrix") or [])
        claim_elements = [
            {
                "claim_element_id": str((item or {}).get("id") or "").strip(),
                "label": str((item or {}).get("label") or "").strip(),
                "supported": bool((item or {}).get("supported")),
                "stable_claim_id": f"claim-element-{idx:03d}",
            }
            for idx, item in enumerate(support_matrix, start=1)
            if str((item or {}).get("id") or "").strip()
        ]
        return {
            "section_cards": section_cards,
            "claim_elements": claim_elements,
            "total_paragraph_count": len(paragraphs),
            "paragraph_count_truncated": paragraph_count_truncated,
            "stable_id_rules": {
                "sections": "section-###",
                "paragraphs": "paragraph-###",
                "claim_elements": "claim-element-###",
            },
        }

    @staticmethod
    def _build_mike_editor_guardrails(
        review: Mapping[str, Any],
        *,
        legal_corpus_review: Optional[Mapping[str, Any]] = None,
        logic_review: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        support_matrix = list((review or {}).get("support_matrix") or [])
        unsupported_ids = [
            str((item or {}).get("id") or "").strip()
            for item in support_matrix
            if str((item or {}).get("id") or "").strip() and not bool((item or {}).get("supported"))
        ]
        contradiction_candidates = list((review or {}).get("contradiction_candidates") or [])
        contradiction_ids = [
            str((item or {}).get("id") or item or "").strip()
            for item in contradiction_candidates
            if str((item or {}).get("id") or item or "").strip()
        ]
        corpus_review = dict(legal_corpus_review or {})
        reasoning_review = dict(logic_review or {})
        pipeline_corpus_coverage = reasoning_review.get("corpus_coverage_percent")
        corpus_grounding_coverage = (
            int(pipeline_corpus_coverage)
            if pipeline_corpus_coverage is not None
            else int(corpus_review.get("coverage_percent") or 0)
        )
        ungrounded_assertions = list(reasoning_review.get("ungrounded_assertions") or [])
        return {
            "unsupported_claim_elements": unsupported_ids,
            "weak_evidentiary_links": unsupported_ids[:MAX_MIKE_WEAK_LINKS_DISPLAY],
            "proof_readiness_flags": {
                "missing_support_count": len(unsupported_ids),
                "supported_count": len(support_matrix) - len(unsupported_ids),
                "corpus_grounding_coverage_percent": corpus_grounding_coverage,
                "proof_status": str(reasoning_review.get("proof_status") or "needs_review"),
                "ungrounded_assertion_count": len(ungrounded_assertions),
            },
            "contradiction_hotspots": contradiction_ids,
            "unsupported_legal_assertion_count": int(corpus_review.get("unsupported_assertion_count") or 0),
            "chronology_blocked": bool(reasoning_review.get("chronology_blocked")),
            "ungrounded_assertions": ungrounded_assertions[:10],
        }

    @staticmethod
    def _validate_mike_structured_deltas(structured_deltas: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Normalize structured deltas while intentionally ignoring malformed rows."""
        normalized: List[Dict[str, Any]] = []
        for item in list(structured_deltas or []):
            if not isinstance(item, dict):
                continue
            op = str(item.get("op") or "").strip().lower() or "edit"
            target = str(item.get("target") or "").strip()
            normalized_from_invalid_op = op not in VALID_MIKE_STRUCTURED_DELTA_OPS
            if op not in VALID_MIKE_STRUCTURED_DELTA_OPS:
                op = "edit"
            metadata = dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {}
            if normalized_from_invalid_op:
                metadata["normalized_from_invalid_op"] = True
            normalized.append(
                {
                    "op": op,
                    "target": target or "draft.body",
                    "before": item.get("before"),
                    "after": item.get("after"),
                    "metadata": metadata,
                }
            )
        return normalized

    @staticmethod
    def _normalize_mike_editor_metadata(editor_metadata: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        payload = dict(editor_metadata or {})
        return {
            "editor_user_id": str(payload.get("editor_user_id") or "").strip() or None,
            "editor_session_id": str(payload.get("editor_session_id") or "").strip() or None,
            "source_updated_at": str(payload.get("source_updated_at") or "").strip() or None,
            "source_transport": str(payload.get("source_transport") or "").strip() or None,
        }

    @staticmethod
    def _derive_mike_theorem_export_check_state(
        *,
        missing_count: int,
        contradiction_count: int,
        chronology_blocked: bool,
        proof_status: str,
    ) -> Dict[str, Any]:
        if chronology_blocked or contradiction_count:
            return {"severity": "error", "status": "failed", "needs_review": True}
        if missing_count or proof_status == "needs_review":
            return {"severity": "warning", "status": "needs_review", "needs_review": True}
        return {"severity": "info", "status": "passed", "needs_review": False}

    @staticmethod
    def _derive_mike_sync_overall_state(
        *,
        conflict_count: int,
        unknown_count: int,
        corpus_has_blockers: bool,
        chronology_blocked: bool,
        contradiction_count: int,
        missing_count: int,
        unsupported_assertion_count: int,
        proof_status: str,
    ) -> Dict[str, Any]:
        has_blockers = bool(conflict_count or unknown_count or corpus_has_blockers or chronology_blocked or contradiction_count)
        if has_blockers:
            severity = "error"
        elif missing_count or unsupported_assertion_count or proof_status == "needs_review":
            severity = "warning"
        else:
            severity = "info"
        return {
            "severity": severity,
            "has_blockers": has_blockers,
        }

    @staticmethod
    def _build_mike_sync_diagnostics(
        *,
        citation_link_check: Mapping[str, Any],
        review_payload: Mapping[str, Any],
        structured_deltas: List[Dict[str, Any]],
        legal_corpus_review: Mapping[str, Any],
        logic_review: Mapping[str, Any],
    ) -> Dict[str, Any]:
        conflict_count = len(list((citation_link_check or {}).get("conflicts") or []))
        unknown_count = len(list((citation_link_check or {}).get("unknown_claim_element_ids") or []))
        overview = dict((review_payload or {}).get("overview") or {})
        missing_count = int(overview.get("missing_elements") or 0)
        corpus_review = dict(legal_corpus_review or {})
        reasoning_review = dict(logic_review or {})
        unsupported_assertion_count = int(corpus_review.get("unsupported_assertion_count") or 0)
        extra_corpus_assertion_count = int(corpus_review.get("extra_corpus_assertion_count") or 0)
        contradiction_count = int(reasoning_review.get("contradiction_count") or 0)
        chronology_blocked = bool(reasoning_review.get("chronology_blocked"))
        proof_status = str(reasoning_review.get("proof_status") or "needs_review")
        theorem_check_state = ComplaintWorkspaceService._derive_mike_theorem_export_check_state(
            missing_count=missing_count,
            contradiction_count=contradiction_count,
            chronology_blocked=chronology_blocked,
            proof_status=proof_status,
        )
        sync_state = ComplaintWorkspaceService._derive_mike_sync_overall_state(
            conflict_count=conflict_count,
            unknown_count=unknown_count,
            corpus_has_blockers=bool(corpus_review.get("has_blockers")),
            chronology_blocked=chronology_blocked,
            contradiction_count=contradiction_count,
            missing_count=missing_count,
            unsupported_assertion_count=unsupported_assertion_count,
            proof_status=proof_status,
        )
        diagnostics = [
            {
                "id": "citation_link_integrity",
                "severity": "error" if (conflict_count or unknown_count) else "info",
                "status": "failed" if (conflict_count or unknown_count) else "passed",
                "message": (
                    f"Detected {conflict_count} citation-link conflict(s) and {unknown_count} unknown claim element link(s)."
                    if (conflict_count or unknown_count)
                    else "Citation-link integrity check passed."
                ),
                "remediation": "Resolve conflicts in Mike and sync again."
                if (conflict_count or unknown_count)
                else "No action required.",
            },
            {
                "id": "corpus_grounding_coverage",
                "severity": "error" if bool(corpus_review.get("has_blockers")) else ("warning" if unsupported_assertion_count else "info"),
                "status": "failed" if bool(corpus_review.get("has_blockers")) else ("needs_review" if unsupported_assertion_count else "passed"),
                "message": (
                    f"Legal-corpus grounding covers {int(corpus_review.get('coverage_percent') or 0)}% of substantive assertions with "
                    f"{unsupported_assertion_count} unsupported and {extra_corpus_assertion_count} extra-corpus assertion(s)."
                ),
                "remediation": "Ground each substantive legal assertion in ipfs_datasets_py legal authority results before export.",
            },
            {
                "id": "claim_proof_coverage",
                "severity": "warning" if missing_count else "info",
                "status": "needs_review" if missing_count else "passed",
                "message": (
                    f"Support review still reports {missing_count} missing claim element(s)."
                    if missing_count
                    else "Support review reports complete claim-element coverage."
                ),
                "remediation": "Collect additional corroboration before export." if missing_count else "No action required.",
            },
            {
                "id": "theorem_export_compatibility",
                "severity": str(theorem_check_state.get("severity") or "warning"),
                "status": str(theorem_check_state.get("status") or "needs_review"),
                "message": (
                    f"Theorem/export compatibility reports proof_status={proof_status}, contradiction_count={contradiction_count}, chronology_blocked={chronology_blocked}."
                    if bool(theorem_check_state.get("needs_review"))
                    else "No proof-gap regressions detected for theorem/export compatibility."
                ),
                "remediation": "Run complaint.review_case and complaint.get_client_release_gate before filing.",
            },
        ]
        normalized_invalid_op_count = sum(
            1
            for item in structured_deltas
            if bool(dict(item.get("metadata") or {}).get("normalized_from_invalid_op"))
        )
        return {
            "severity": str(sync_state.get("severity") or "warning"),
            "has_blockers": bool(sync_state.get("has_blockers")),
            "checks": diagnostics,
            "structured_delta_count": len(structured_deltas),
            "normalized_invalid_op_count": normalized_invalid_op_count,
            "grounding_coverage_percent": int(corpus_review.get("coverage_percent") or 0),
            "proof_status": proof_status,
            "contradiction_count": contradiction_count,
        }

    def build_mike_handoff(
        self,
        user_id: Optional[str],
        *,
        mike_base_url: Optional[str] = None,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        generate_draft_if_missing: bool = True,
        grounding_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._load_state(resolved_user_id)
        generated_draft = False
        if generate_draft_if_missing and not state.get("draft"):
            state["draft"] = self._build_draft(state)
            generated_draft = True
        review = self._build_review(state)
        resolved_grounding_mode = self._resolve_mike_grounding_mode(grounding_mode)
        router_policy = self._build_mike_router_policy_snapshot()
        skill_asset_manifest = self._build_mike_skill_asset_manifest()
        submodule_inventory = self._build_mike_submodule_inventory()
        compatibility_target_matrix = self._build_mike_compatibility_target_matrix()
        draft_payload = dict(state.get("draft") or {})
        derived_assertions = self._normalize_mike_assertion_annotations(None, body=str(draft_payload.get("body") or ""))
        legal_corpus_review = self._build_mike_legal_corpus_review(
            claim_type=str(state.get("claim_type") or "retaliation"),
            grounding_mode=resolved_grounding_mode,
            assertion_annotations=derived_assertions,
            authority_links=[],
        )
        logic_review = self._build_mike_logic_review(
            state=state,
            review=review,
            assertion_annotations=derived_assertions,
            authority_links=[],
        )
        handoff_id = f"mike-handoff-{uuid.uuid4().hex[:12]}"
        resolved_base_url = self._resolve_mike_base_url(mike_base_url)
        launch_query: Dict[str, str] = {
            "user_id": resolved_user_id,
            "handoff_id": handoff_id,
        }
        normalized_project_id = str(project_id or "").strip()
        normalized_workspace_id = str(workspace_id or "").strip()
        if normalized_project_id:
            launch_query["project_id"] = normalized_project_id
        if normalized_workspace_id:
            launch_query["workspace_id"] = normalized_workspace_id
        launch_url = self._build_mike_launch_url(resolved_base_url, launch_query)
        transport_warning = self._mike_transport_warning(resolved_base_url)
        handoff_payload = {
            "version": MIKE_HANDOFF_CONTRACT_VERSION,
            "user_id": resolved_user_id,
            "project_id": normalized_project_id or None,
            "workspace_id": normalized_workspace_id or None,
            "handoff_id": handoff_id,
            "created_at": _utc_now(),
            "case_synopsis": self._build_case_synopsis(state),
            "claim_type": str(state.get("claim_type") or "retaliation"),
            "draft": deepcopy(state.get("draft") or {}),
            "review": deepcopy(review),
            "authoritative_state_model": {
                "session_state_owner": "complaint_generator",
                "mike_role": "editing_surface_only",
                "source_of_truth": "complaint_generator_workspace_session",
            },
            "router_policy": router_policy,
            "skill_asset_manifest": skill_asset_manifest,
            "grounding_mode": resolved_grounding_mode,
            "corpus_boundaries": self._build_mike_corpus_boundaries(
                claim_type=str(state.get("claim_type") or "retaliation"),
                grounding_mode=resolved_grounding_mode,
            ),
            "evidence_context": self._summarize_mike_evidence_context(state, review),
            "structured_legal_packet_context": self._build_mike_structured_packet_context(
                dict(state.get("draft") or {}),
                review,
            ),
            "legal_corpus_context": legal_corpus_review,
            "logic_handoff": {
                "proof_constraints": {
                    "unsupported_claim_element_ids": deepcopy(logic_review.get("unsupported_claim_element_ids") or []),
                    "proof_status": str(logic_review.get("proof_status") or "needs_review"),
                    "chronology_blocked": bool(logic_review.get("chronology_blocked")),
                    "contradiction_count": int(logic_review.get("contradiction_count") or 0),
                },
                "formal_predicates": deepcopy(((logic_review.get("reasoning_payload") or {}).get("predicates") or [])),
                "theorem_export_metadata": deepcopy(logic_review.get("theorem_export_metadata") or {}),
                "leanstral_assist": deepcopy(logic_review.get("leanstral_assist") or {}),
            },
            "editor_guardrails": self._build_mike_editor_guardrails(
                review,
                legal_corpus_review=legal_corpus_review,
                logic_review=logic_review,
            ),
            "submodule_inventory": submodule_inventory,
            "compatibility_target_matrix": compatibility_target_matrix,
            "non_negotiable_constraints": {
                "must_preserve_claim_element_references": True,
                "must_return_sync_handoff_id": True,
                "must_run_citation_link_integrity_checks": True,
                "must_include_source_timestamps": True,
                "must_return_assertion_annotations": True,
                "must_return_authority_links": True,
                "must_preserve_logic_constraints": True,
                "must_route_generation_through_workspace_llm_router": True,
            },
        }
        from integrations.ipfs_datasets import llm as complaint_llm

        router_available = bool(getattr(complaint_llm, "LLM_ROUTER_AVAILABLE", False))
        draft_title = str(draft_payload.get("title") or "")
        draft_body = str(draft_payload.get("body") or "")
        handoff_payload["mike_document"] = {
            "title": draft_title,
            "body": draft_body,
            "citations": list(draft_payload.get("citation_links") or []),
            "content_sha256": self._document_version_content_sha256(draft_title, draft_body),
        }
        handoff_payload["mike_integration"] = {
            "transport": "mcp_connector",
            "connector_url": self._mike_connector_url(),
            "tools": list(MIKE_MCP_CONNECTOR_TOOLS),
            "setup_instructions": self._mike_connector_setup_text(router_available),
            "llm_router_available": router_available,
        }
        # The payload stamp stays for one release. Mike calls the MCP connector.
        try:
            from integrations.mike.llm_patch import apply_mike_llm_router_patch
            apply_mike_llm_router_patch(handoff_payload)
        except Exception:
            pass
        mike_integration = dict(state.get("mike_integration") or {})
        handoff_history = [dict(item) for item in list(mike_integration.get("handoff_history") or []) if isinstance(item, dict)]
        handoff_record = {
            "handoff_id": handoff_id,
            "created_at": handoff_payload["created_at"],
            "project_id": normalized_project_id or None,
            "workspace_id": normalized_workspace_id or None,
            "generated_draft": generated_draft,
            "launch_url": launch_url,
        }
        handoff_history.insert(0, handoff_record)
        mike_integration["last_handoff"] = handoff_record
        mike_integration["handoff_history"] = handoff_history[:25]
        state["mike_integration"] = mike_integration
        self._save_state(state)
        return {
            "user_id": resolved_user_id,
            "handoff_id": handoff_id,
            "generated_draft": generated_draft,
            "mike": {
                "base_url": resolved_base_url,
                "launch_url": launch_url,
                "project_id": normalized_project_id or None,
                "workspace_id": normalized_workspace_id or None,
                "transport_warning": transport_warning,
            },
            "handoff_payload": handoff_payload,
            "sync_contract": {
                "tool_name": "complaint.sync_mike_final_draft",
                "contract_version": MIKE_SYNC_CONTRACT_VERSION,
                "required_fields": ["user_id", "body"],
                "optional_fields": [
                    "handoff_id",
                    "project_id",
                    "workspace_id",
                    "title",
                    "requested_relief",
                    "mike_document_id",
                    "citation_links",
                    "redline_summary",
                    "source_updated_at",
                    "structured_deltas",
                    "editor_metadata",
                    "grounding_mode",
                    "assertion_annotations",
                    "authority_links",
                    "sync_provenance",
                ],
            },
            "session_snapshot": {
                "user_id": str(state.get("user_id") or resolved_user_id),
                "claim_type": str(state.get("claim_type") or "retaliation"),
                "has_draft": bool(state.get("draft")),
                "testimony_count": len(list((state.get("evidence") or {}).get("testimony") or [])),
                "document_count": len(list((state.get("evidence") or {}).get("documents") or [])),
                "updated_at": str(state.get("updated_at") or ""),
            },
            "review": deepcopy(review),
            "case_synopsis": self._build_case_synopsis(state),
            "router_policy": router_policy,
            "skill_asset_manifest": skill_asset_manifest,
            "submodule_inventory": submodule_inventory,
            "compatibility_target_matrix": compatibility_target_matrix,
            "contract_versions": {
                "handoff": MIKE_HANDOFF_CONTRACT_VERSION,
                "sync": MIKE_SYNC_CONTRACT_VERSION,
                "status": MIKE_STATUS_CONTRACT_VERSION,
            },
        }

    def sync_mike_final_draft(
        self,
        user_id: Optional[str],
        *,
        body: str,
        title: Optional[str] = None,
        requested_relief: Optional[List[str]] = None,
        handoff_id: Optional[str] = None,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        mike_document_id: Optional[str] = None,
        citation_links: Optional[List[Dict[str, Any]]] = None,
        redline_summary: Optional[str] = None,
        source_updated_at: Optional[str] = None,
        structured_deltas: Optional[List[Dict[str, Any]]] = None,
        editor_metadata: Optional[Dict[str, Any]] = None,
        grounding_mode: Optional[str] = None,
        assertion_annotations: Optional[List[Dict[str, Any]]] = None,
        authority_links: Optional[List[Dict[str, Any]]] = None,
        sync_provenance: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raw_body = str(body or "")
        if not raw_body.strip():
            raise ValueError("The draft body content is required and cannot be empty.")
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        draft = deepcopy(state.get("draft") or self._build_draft(state))
        mike_integration = dict(state.get("mike_integration") or {})
        last_handoff = dict(mike_integration.get("last_handoff") or {})
        provided_handoff_id = str(handoff_id or "").strip()
        fallback_handoff_id = str(last_handoff.get("handoff_id") or "").strip()
        resolved_handoff_id = provided_handoff_id or fallback_handoff_id or None
        existing_title = str(draft.get("title") or "").strip()
        base_draft_identity = self._build_mike_base_draft_identity(draft)
        if title is not None:
            normalized_title = str(title or "").strip()
            draft["title"] = normalized_title or existing_title or "Complaint Draft"
        draft["body"] = raw_body
        if requested_relief is not None:
            draft["requested_relief"] = [str(item).strip() for item in list(requested_relief or []) if str(item).strip()]
        synced_at = _utc_now()
        normalized_citation_links = self._normalize_mike_citation_links(citation_links)
        normalized_structured_deltas = self._validate_mike_structured_deltas(structured_deltas)
        normalized_editor_metadata = self._normalize_mike_editor_metadata(editor_metadata)
        resolved_grounding_mode = self._resolve_mike_grounding_mode(grounding_mode)
        normalized_assertion_annotations = self._normalize_mike_assertion_annotations(
            assertion_annotations,
            body=raw_body,
        )
        normalized_authority_links = self._normalize_mike_authority_links(authority_links)
        normalized_sync_provenance = self._normalize_mike_sync_provenance(
            sync_provenance,
            base_draft_identity=base_draft_identity,
            redline_metadata=self._build_mike_redline_metadata(
                redline_summary=redline_summary,
                structured_deltas=normalized_structured_deltas,
            ),
        )
        review_payload = dict(state.get("support_review") or {})
        if not review_payload:
            review_payload = self._build_review(state)
        legal_corpus_review = self._build_mike_legal_corpus_review(
            claim_type=str(state.get("claim_type") or "retaliation"),
            grounding_mode=resolved_grounding_mode,
            assertion_annotations=normalized_assertion_annotations,
            authority_links=normalized_authority_links,
        )
        logic_review = self._build_mike_logic_review(
            state=state,
            review=review_payload,
            assertion_annotations=normalized_assertion_annotations,
            authority_links=normalized_authority_links,
        )
        # Run the draft-logic pipeline and merge its proof report into logic_review.
        draft_proof_report = _run_draft_logic_pipeline_safely(
            raw_body,
            state=str(state.get("state_code") or "").strip() or None,
        )
        logic_review = self._merge_draft_proof_report(logic_review, draft_proof_report)
        router_policy = self._build_mike_router_policy_snapshot()
        citation_link_check = self._check_mike_citation_links(
            state,
            normalized_citation_links,
            review=review_payload,
        )
        sync_diagnostics = self._build_mike_sync_diagnostics(
            citation_link_check=citation_link_check,
            review_payload=review_payload,
            structured_deltas=normalized_structured_deltas,
            legal_corpus_review=legal_corpus_review,
            logic_review=logic_review,
        )
        sync_integrity_payload_bytes = json.dumps(
            {
                "handoff_id": resolved_handoff_id,
                "body": raw_body,
                "synced_at": synced_at,
                "citation_links": normalized_citation_links,
                "structured_deltas": normalized_structured_deltas,
                "source_updated_at": str(source_updated_at or "").strip(),
                "editor_metadata": normalized_editor_metadata,
                "grounding_mode": resolved_grounding_mode,
                "assertion_annotations": normalized_assertion_annotations,
                "authority_links": normalized_authority_links,
                "sync_provenance": normalized_sync_provenance,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        sync_hash_secret = str(os.getenv("COMPLAINT_MIKE_SYNC_HASH_SECRET") or "").strip()
        if sync_hash_secret:
            sync_integrity_hash = hmac.new(sync_hash_secret.encode("utf-8"), sync_integrity_payload_bytes, hashlib.sha256).hexdigest()
            sync_integrity_hash_mode = "hmac_sha256"
        else:
            sync_integrity_hash = hashlib.sha256(sync_integrity_payload_bytes).hexdigest()
            sync_integrity_hash_mode = "sha256_unkeyed"
        draft["updated_at"] = synced_at
        draft["sync_source"] = "mike"
        draft["sync_metadata"] = {
            "contract_version": MIKE_SYNC_CONTRACT_VERSION,
            "handoff_id": resolved_handoff_id,
            "project_id": str(project_id or "").strip() or None,
            "workspace_id": str(workspace_id or "").strip() or None,
            "mike_document_id": str(mike_document_id or "").strip() or None,
            "citation_links": normalized_citation_links,
            "structured_deltas": normalized_structured_deltas,
            "citation_link_check": citation_link_check,
            "sync_diagnostics": sync_diagnostics,
            "redline_summary": str(redline_summary or "").strip() or None,
            "redline_metadata": deepcopy(normalized_sync_provenance.get("redline_metadata") or {}),
            "source_updated_at": str(source_updated_at or "").strip() or None,
            "editor_metadata": normalized_editor_metadata,
            "grounding_mode": resolved_grounding_mode,
            "assertion_annotations": normalized_assertion_annotations,
            "authority_links": normalized_authority_links,
            "sync_provenance": normalized_sync_provenance,
            "legal_corpus_review": legal_corpus_review,
            "logic_review": logic_review,
            "router_policy": router_policy,
            "sync_integrity_hash": sync_integrity_hash,
            "sync_integrity_hash_mode": sync_integrity_hash_mode,
            "synced_at": synced_at,
        }
        state["draft"] = draft
        sync_history = [dict(item) for item in list(mike_integration.get("sync_history") or []) if isinstance(item, dict)]
        sync_record = {
            "synced_at": synced_at,
            "handoff_id": draft["sync_metadata"]["handoff_id"],
            "project_id": draft["sync_metadata"]["project_id"],
            "workspace_id": draft["sync_metadata"]["workspace_id"],
            "mike_document_id": draft["sync_metadata"]["mike_document_id"],
            "body_chars": len(raw_body),
            "title": str(draft.get("title") or "").strip(),
            "citation_link_count": citation_link_check["total_links"],
            "citation_link_conflict_count": len(citation_link_check["conflicts"]),
            "citation_link_has_conflicts": citation_link_check["has_conflicts"],
            "citation_link_unknown_element_count": len(list(citation_link_check.get("unknown_claim_element_ids") or [])),
            "structured_delta_count": len(normalized_structured_deltas),
            "sync_diagnostics_severity": str(sync_diagnostics.get("severity") or "info"),
            "grounding_mode": resolved_grounding_mode,
            "grounding_coverage_percent": int(legal_corpus_review.get("coverage_percent") or 0),
            "unsupported_assertion_count": int(legal_corpus_review.get("unsupported_assertion_count") or 0),
            "proof_status": str(logic_review.get("proof_status") or "needs_review"),
            "chronology_blocked": bool(logic_review.get("chronology_blocked")),
            "contradiction_count": int(logic_review.get("contradiction_count") or 0),
            "editor_user_id": normalized_editor_metadata.get("editor_user_id"),
            "editor_version": normalized_sync_provenance.get("editor_version"),
            "enabled_skill_ids": list(normalized_sync_provenance.get("enabled_skill_ids") or []),
            "base_draft_hash": normalized_sync_provenance.get("base_draft_hash"),
            "redline_delta_count": int(((normalized_sync_provenance.get("redline_metadata") or {}).get("structured_delta_count")) or 0),
            "sync_integrity_hash": sync_integrity_hash,
            "sync_integrity_hash_mode": sync_integrity_hash_mode,
            "document_version_content_sha256": self._document_version_content_sha256(
                str(draft.get("title") or ""),
                str(draft.get("body") or ""),
            ),
        }
        draft["sync_metadata"]["document_version_content_sha256"] = sync_record["document_version_content_sha256"]
        sync_history.insert(0, sync_record)
        mike_integration["last_sync"] = sync_record
        mike_integration["sync_history"] = sync_history[:25]
        audit_trail = [dict(item) for item in list(mike_integration.get("audit_trail") or []) if isinstance(item, dict)]
        audit_trail.insert(
            0,
            {
                "audit_id": f"mike-sync-audit-{uuid.uuid4().hex[:12]}",
                "synced_at": synced_at,
                "handoff_id": sync_record.get("handoff_id"),
                "editor_user_id": normalized_editor_metadata.get("editor_user_id"),
                "severity": sync_diagnostics.get("severity"),
                "has_blockers": bool(sync_diagnostics.get("has_blockers")),
                "sync_integrity_hash": sync_integrity_hash,
            },
        )
        mike_integration["audit_trail"] = audit_trail[:50]
        state["mike_integration"] = mike_integration
        self._save_state(state)
        session = self.get_session(str(state.get("user_id")))
        return {
            "user_id": session["session"]["user_id"],
            "draft": deepcopy(session["session"].get("draft") or {}),
            "sync_record": sync_record,
            "citation_link_check": citation_link_check,
            "sync_diagnostics": sync_diagnostics,
            "legal_corpus_review": legal_corpus_review,
            "logic_review": logic_review,
            "router_policy": router_policy,
            "sync_provenance": normalized_sync_provenance,
            "redline_metadata": deepcopy(normalized_sync_provenance.get("redline_metadata") or {}),
            "contract_versions": {
                "sync": MIKE_SYNC_CONTRACT_VERSION,
                "status": MIKE_STATUS_CONTRACT_VERSION,
            },
            "review": session["review"],
            "session": session["session"],
            "questions": session["questions"],
            "next_question": session["next_question"],
            "case_synopsis": session["case_synopsis"],
            "document_version_content_sha256": sync_record["document_version_content_sha256"],
        }

    def get_mike_integration_status(self, user_id: Optional[str]) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        mike_integration = dict(state.get("mike_integration") or {})
        last_handoff = dict(mike_integration.get("last_handoff") or {})
        last_sync = dict(mike_integration.get("last_sync") or {})
        handoff_history = [dict(item) for item in list(mike_integration.get("handoff_history") or []) if isinstance(item, dict)]
        sync_history = [dict(item) for item in list(mike_integration.get("sync_history") or []) if isinstance(item, dict)]
        draft = dict(state.get("draft") or {})
        draft_sync_source = str(draft.get("sync_source") or "").strip().lower()
        has_mike_synced_draft = draft_sync_source == "mike" and bool(str(draft.get("body") or "").strip())
        draft_updated_at_raw = str(draft.get("updated_at") or "").strip()
        latest_sync_timestamp_raw = str(last_sync.get("synced_at") or "").strip()
        if has_mike_synced_draft and draft_updated_at_raw and latest_sync_timestamp_raw:
            try:
                draft_updated_at = datetime.fromisoformat(draft_updated_at_raw)
                latest_sync_timestamp = datetime.fromisoformat(latest_sync_timestamp_raw)
                # Equality is intentional because Mike sync writes both timestamps in one operation.
                # If they differ, the draft changed after sync and should no longer be treated as current.
                has_mike_synced_draft = draft_updated_at == latest_sync_timestamp
            except ValueError:
                has_mike_synced_draft = draft_updated_at_raw == latest_sync_timestamp_raw
        draft_sync_metadata = dict(draft.get("sync_metadata") or {})
        raw_citation_link_check = dict(draft_sync_metadata.get("citation_link_check") or {})
        has_citation_link_conflicts = bool(raw_citation_link_check.get("has_conflicts"))
        citation_link_conflict_count = len(list(raw_citation_link_check.get("conflicts") or []))
        citation_link_unknown_element_count = len(list(raw_citation_link_check.get("unknown_claim_element_ids") or []))
        legal_corpus_review = dict(draft_sync_metadata.get("legal_corpus_review") or {})
        logic_review = dict(draft_sync_metadata.get("logic_review") or {})
        router_policy = dict(draft_sync_metadata.get("router_policy") or self._build_mike_router_policy_snapshot())
        latest_handoff_id = str(last_handoff.get("handoff_id") or "").strip()
        latest_sync_handoff_id = str(last_sync.get("handoff_id") or "").strip()
        # When latest_sync_handoff_id is empty, no Mike sync has been persisted yet for this session.
        pending_sync = bool(latest_handoff_id) and latest_handoff_id != latest_sync_handoff_id
        workflow_state = self._build_mike_workflow_state(
            latest_handoff_id=latest_handoff_id,
            pending_sync=pending_sync,
            has_mike_synced_draft=has_mike_synced_draft,
            has_citation_link_conflicts=has_citation_link_conflicts,
        )
        recommended_action = self._derive_mike_recommended_action(
            workflow_state_key=workflow_state["key"],
            has_citation_link_conflicts=has_citation_link_conflicts,
        )
        pending_sync_implies_handoff = (not pending_sync) or bool(latest_handoff_id)
        synced_handoff_never_pending = not (
            bool(latest_handoff_id)
            and latest_handoff_id == latest_sync_handoff_id
            and pending_sync
        )
        conflict_count_non_null = isinstance(citation_link_conflict_count, int) and citation_link_conflict_count >= 0
        unknown_count_non_null = isinstance(citation_link_unknown_element_count, int) and citation_link_unknown_element_count >= 0
        recommended_action_valid = bool(str(recommended_action or "").strip())
        conflict_component = {
            "conflict_count": int(citation_link_conflict_count),
            "unknown_element_count": int(citation_link_unknown_element_count),
            "impact_statement": (
                "Export readiness is blocked until Mike citation-link conflicts are resolved and synced again."
                if has_citation_link_conflicts
                else "No citation-link blockers are currently reported."
            ),
            "required_next_action": recommended_action,
            "why_blocked": (
                "Citation-link integrity checks found conflicts or unknown claim elements."
                if has_citation_link_conflicts
                else ""
            ),
        }
        grounding_component = {
            "grounding_mode": str(draft_sync_metadata.get("grounding_mode") or self._resolve_mike_grounding_mode()).strip(),
            "coverage_percent": int(legal_corpus_review.get("coverage_percent") or 0),
            "unsupported_assertion_count": int(legal_corpus_review.get("unsupported_assertion_count") or 0),
            "extra_corpus_assertion_count": int(legal_corpus_review.get("extra_corpus_assertion_count") or 0),
            "weak_grounding_count": int(legal_corpus_review.get("weak_grounding_count") or 0),
            "has_blockers": bool(legal_corpus_review.get("has_blockers")),
            "impact_statement": (
                "Strict legal-corpus containment is blocking export until unsupported or extra-corpus assertions are grounded."
                if bool(legal_corpus_review.get("has_blockers"))
                else "No strict legal-corpus grounding blockers are currently reported."
            ),
        }
        proof_component = {
            "proof_status": str(logic_review.get("proof_status") or "needs_review"),
            "proof_passed": bool(logic_review.get("proof_passed")),
            "contradiction_count": int(logic_review.get("contradiction_count") or 0),
            "chronology_blocked": bool(logic_review.get("chronology_blocked")),
            "unsupported_claim_element_count": int(logic_review.get("unsupported_claim_element_count") or 0),
            "has_blockers": bool(logic_review.get("has_blockers")),
            "impact_statement": (
                "Formal proof or chronology checks are blocking export until Mike edits preserve claim coverage."
                if bool(logic_review.get("has_blockers"))
                else "No formal proof blockers are currently reported."
            ),
        }
        return {
            "user_id": str(state.get("user_id") or DEFAULT_USER_ID),
            "status": "ok",
            "status_contract_version": MIKE_STATUS_CONTRACT_VERSION,
            "status_contract": {
                "version": MIKE_STATUS_CONTRACT_VERSION,
                "canonical_source": "/api/complaint-workspace/mike/status",
                "state_mapping": deepcopy(MIKE_WORKFLOW_STATE_LABELS),
            },
            "last_handoff": last_handoff or None,
            "last_sync": last_sync or None,
            "handoff_history_count": len(handoff_history),
            "sync_history_count": len(sync_history),
            "latest_handoff_id": latest_handoff_id or None,
            "latest_sync_handoff_id": latest_sync_handoff_id or None,
            "pending_sync": pending_sync,
            "workflow_state": workflow_state,
            "has_mike_synced_draft": has_mike_synced_draft,
            "has_citation_link_conflicts": has_citation_link_conflicts,
            "citation_link_conflict_count": citation_link_conflict_count,
            "citation_link_unknown_element_count": citation_link_unknown_element_count,
            "conflict_component": conflict_component,
            "grounding_component": grounding_component,
            "proof_component": proof_component,
            "router_policy": router_policy,
            "draft_sync_source": draft_sync_source or None,
            "recommended_action": recommended_action,
            "invariants": {
                "pending_sync_implies_handoff": pending_sync_implies_handoff,
                "synced_handoff_never_pending": synced_handoff_never_pending,
                "conflict_counters_non_null_numeric": bool(conflict_count_non_null and unknown_count_non_null),
                "recommended_action_present": recommended_action_valid,
            },
            "status_freshness": {
                "last_handoff_at": str(last_handoff.get("created_at") or "").strip() or None,
                "last_sync_at": str(last_sync.get("synced_at") or "").strip() or None,
                "latest_status_observed_at": _utc_now(),
            },
        }

    def get_draft_proof_report(
        self,
        user_id: Optional[str],
        *,
        state_code: Optional[str] = None,
        allow_live_scrape_fallback: bool = False,
    ) -> Dict[str, Any]:
        """Run the draft-logic pipeline on the current complaint draft.

        Returns the full ``DraftProofReport`` dict from
        :func:`~integrations.ipfs_datasets.draft_logic_pipeline.run_pipeline`,
        enriched with a quality score from
        :func:`~integrations.ipfs_datasets.quality.score_draft_quality`.

        Parameters
        ----------
        user_id:
            Workspace user identifier.
        state_code:
            Optional two-letter US state abbreviation to narrow state-law
            corpus searches.
        allow_live_scrape_fallback:
            Whether to permit live-scrape network calls during corpus grounding.
            Defaults to ``False`` to keep the tool fast in offline environments.
        """
        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._load_state(resolved_user_id)
        draft = dict(state.get("draft") or {})
        body = str(draft.get("body") or "").strip()
        if not body:
            return {
                "status": "no_draft",
                "message": "No complaint draft is available.  Run complaint.generate_complaint first.",
                "proof_report": None,
                "quality_score": None,
            }
        proof_report = _run_draft_logic_pipeline_safely(
            body,
            state=state_code or str(state.get("intake_answers", {}).get("state") or "").strip() or None,
        )
        quality_score: Optional[Dict[str, Any]] = None
        try:
            from integrations.ipfs_datasets.quality import score_draft_quality
            quality_score = score_draft_quality(proof_report, claim_id=resolved_user_id)
        except Exception:
            pass
        self._persist_proof_run(state, proof_report=proof_report, quality_score=quality_score)
        self._save_state(state)
        return {
            "status": "ok",
            "user_id": resolved_user_id,
            "proof_report": proof_report,
            "quality_score": quality_score,
            "draft_body_length": len(body),
        }

    def render_draft_proof_report(
        self,
        user_id: Optional[str],
        *,
        state_code: Optional[str] = None,
        claim_id: str = "",
    ) -> Dict[str, Any]:
        """Run the pipeline and render the proof report as Markdown.

        Returns a dict with a ``rendered`` key containing the Markdown string.
        """
        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        proof_result = self.get_draft_proof_report(
            resolved_user_id,
            state_code=state_code,
        )
        if proof_result.get("status") != "ok":
            return proof_result
        proof_report = dict(proof_result.get("proof_report") or {})
        rendered = ""
        try:
            from integrations.ipfs_datasets.draft_logic_pipeline import render_proof_report
            rendered = render_proof_report(
                proof_report,
                claim_id=claim_id or resolved_user_id,
            )
        except Exception as exc:
            rendered = f"# Proof Report (render error)\n\n`{exc}`\n"
        return {
            "status": "ok",
            "user_id": resolved_user_id,
            "rendered": rendered,
            "proof_report": proof_report,
            "quality_score": proof_result.get("quality_score"),
        }

    def pin_draft_proof_report(
        self,
        user_id: Optional[str],
        *,
        state_code: Optional[str] = None,
        claim_id: str = "",
    ) -> Dict[str, Any]:
        """Run the pipeline, then pin the proof report to IPFS.

        Returns the pin result from
        :func:`~integrations.ipfs_datasets.draft_logic_pipeline.pin_proof_report_to_ipfs`
        (``report_cid``, ``lean4_cid``, ``coq_cid``, ``pinned``, ``backend``,
        ``pinned_at``) plus the quality score.
        """
        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        proof_result = self.get_draft_proof_report(
            resolved_user_id,
            state_code=state_code,
        )
        if proof_result.get("status") != "ok":
            return proof_result
        proof_report = dict(proof_result.get("proof_report") or {})
        pin_result: Dict[str, Any] = {
            "report_cid": "",
            "lean4_cid": "",
            "coq_cid": "",
            "pinned": False,
            "backend": "unavailable",
            "pinned_at": "",
        }
        try:
            from integrations.ipfs_datasets.draft_logic_pipeline import pin_proof_report_to_ipfs
            context = self._private_artifact_context(resolved_user_id, revision="proof-1")
            context.update(backend=self._private_local_backend(), backend_name="local_cache", pin_content=False)
            pin_result = pin_proof_report_to_ipfs(proof_report, claim_id=claim_id or resolved_user_id, private_context=context)
        except WorkspacePersistenceError:
            raise
        except Exception:
            pin_result.update(status="unavailable", deferred=True, verified=False, error="private_proof_unavailable")
        return {
            "status": "ok",
            "user_id": resolved_user_id,
            "pin_result": pin_result,
            "proof_report": proof_report,
            "quality_score": proof_result.get("quality_score"),
        }

    # ------------------------------------------------------------------
    # Proof history persistence helpers
    # ------------------------------------------------------------------

    _PROOF_HISTORY_MAX_ENTRIES: int = 20

    def _persist_proof_run(
        self,
        state: Dict[str, Any],
        *,
        proof_report: Dict[str, Any],
        quality_score: Optional[Dict[str, Any]],
    ) -> None:
        """Append a compact proof-run summary to ``state["proof_history"]``."""
        import datetime as _dt

        history: List[Dict[str, Any]] = list(state.get("proof_history") or [])
        entry: Dict[str, Any] = {
            "run_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "proof_status": str(proof_report.get("proof_status") or "needs_review"),
            "contradiction_count": int(proof_report.get("contradiction_count") or 0),
            "corpus_coverage_percent": proof_report.get("corpus_coverage_percent"),
            "ungrounded_assertion_count": int(proof_report.get("ungrounded_assertion_count") or 0),
            "has_blockers": bool(proof_report.get("has_blockers")),
            "predicate_count": int(proof_report.get("predicate_count") or 0),
            "pipeline_version": str(proof_report.get("pipeline_version") or ""),
            "pipeline_errors": list(proof_report.get("errors") or []),
        }
        if quality_score:
            entry["overall_score"] = quality_score.get("overall_score")
            entry["grade"] = quality_score.get("grade")
            entry["dimensions"] = dict(quality_score.get("dimensions") or {})
        history.append(entry)
        # Keep only the most recent N entries.
        state["proof_history"] = history[-self._PROOF_HISTORY_MAX_ENTRIES:]

    # ------------------------------------------------------------------
    # score_draft_quality
    # ------------------------------------------------------------------

    def score_draft_quality(
        self,
        user_id: Optional[str],
        *,
        state_code: Optional[str] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Run the draft-logic pipeline and return a quality score.

        Unlike :meth:`get_draft_proof_report`, this method returns only the
        quality score (overall score, grade, dimension breakdown, and
        suggestions) — not the full proof report — making it lightweight enough
        to call on every draft save.  It also persists the run to proof history
        so progress can be tracked over time.

        Parameters
        ----------
        user_id:
            Workspace user identifier.
        state_code:
            Optional two-letter US state abbreviation for corpus searches.
        persist:
            Whether to append a compact proof-run summary to
            ``state["proof_history"]``.  Defaults to ``True``.
        """
        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._load_state(resolved_user_id)
        draft = dict(state.get("draft") or {})
        body = str(draft.get("body") or "").strip()
        if not body:
            return {
                "status": "no_draft",
                "message": "No complaint draft is available.  Run complaint.generate_complaint first.",
                "quality_score": None,
            }
        proof_report = _run_draft_logic_pipeline_safely(
            body,
            state=state_code or str(state.get("intake_answers", {}).get("state") or "").strip() or None,
        )
        quality_score: Optional[Dict[str, Any]] = None
        try:
            from integrations.ipfs_datasets.quality import score_draft_quality as _score
            quality_score = _score(proof_report, claim_id=resolved_user_id)
        except Exception:
            pass
        if persist:
            self._persist_proof_run(state, proof_report=proof_report, quality_score=quality_score)
            self._save_state(state)
        return {
            "status": "ok",
            "user_id": resolved_user_id,
            "quality_score": quality_score,
            "draft_body_length": len(body),
        }

    # ------------------------------------------------------------------
    # improve_draft
    # ------------------------------------------------------------------

    def improve_draft(
        self,
        user_id: Optional[str],
        *,
        state_code: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config_path: Optional[str] = None,
        backend_id: Optional[str] = None,
        max_suggestions: int = 3,
    ) -> Dict[str, Any]:
        """Apply quality-scorer suggestions to the draft via the LLM router.

        Runs the draft-logic pipeline, extracts the highest-priority suggestions
        from :func:`~integrations.ipfs_datasets.quality.score_draft_quality`,
        and sends a targeted improvement prompt through the workspace
        ``llm_router`` for each suggestion.  The improved draft body is
        persisted back to the workspace state.

        Parameters
        ----------
        user_id:
            Workspace user identifier.
        state_code:
            Optional two-letter US state abbreviation for corpus searches.
        provider / model / config_path / backend_id:
            LLM router provider overrides forwarded to
            :func:`~integrations.ipfs_datasets.llm.generate_text_with_metadata`.
        max_suggestions:
            Maximum number of suggestions to apply in a single call.
            Defaults to 3 to keep prompts focused.
        """
        from integrations.ipfs_datasets.llm import generate_text_with_metadata

        # Minimum character count for an LLM response to be treated as a valid
        # revised draft body.  Responses shorter than this are likely refusals,
        # error messages, or incomplete outputs and should be discarded.
        _MIN_REVISED_DRAFT_LENGTH = 50

        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._load_state(resolved_user_id)
        draft = dict(state.get("draft") or {})
        body = str(draft.get("body") or "").strip()
        if not body:
            return {
                "status": "no_draft",
                "message": "No complaint draft is available.  Run complaint.generate_complaint first.",
                "improved": False,
                "quality_before": None,
                "quality_after": None,
            }

        # 1. Score the current draft.
        proof_report = _run_draft_logic_pipeline_safely(
            body,
            state=state_code or str(state.get("intake_answers", {}).get("state") or "").strip() or None,
        )
        quality_before: Optional[Dict[str, Any]] = None
        suggestions: List[Dict[str, Any]] = []
        try:
            from integrations.ipfs_datasets.quality import score_draft_quality as _score
            quality_before = _score(proof_report, claim_id=resolved_user_id)
            suggestions = list(quality_before.get("suggestions") or [])
        except Exception:
            pass

        # 2. Apply the top N suggestions via the LLM router.
        high_priority = [s for s in suggestions if str(s.get("priority") or "") == "high"]
        medium_priority = [s for s in suggestions if str(s.get("priority") or "") == "medium"]
        ordered = (high_priority + medium_priority)[:max_suggestions]

        applied_suggestions: List[Dict[str, Any]] = []
        improved_body = body
        llm_errors: List[str] = []

        for suggestion in ordered:
            action = str(suggestion.get("action") or "").strip()
            dimension = str(suggestion.get("dimension") or "").strip()
            if not action:
                continue
            prompt = (
                "You are a legal document editor.  The following complaint draft has a quality issue.\n\n"
                f"Issue ({dimension}): {action}\n\n"
                "Please revise the draft to address this issue.  Keep the legal language, "
                "paragraph numbering, and filing-ready format intact.  Return ONLY the revised "
                "complaint body text, with no preamble, commentary, or markdown fences.\n\n"
                f"DRAFT:\n{improved_body}"
            )
            try:
                helpers = _privacy_helpers()
                case_id = _state_case_id(state, resolved_user_id)
                privacy_context = helpers["build_complaint_privacy_context"](
                    state.get("privacy_policy"),
                    user_id=resolved_user_id,
                    case_id=case_id,
                    data_class="drafts_proofs",
                )
                llm_result = generate_text_with_metadata(
                    prompt,
                    provider=provider,
                    model_name=model,
                    config_path=config_path,
                    backend_id=backend_id,
                    complaint_privacy_context=privacy_context,
                )
                if str((llm_result or {}).get("privacy_decision") or "") == "denied":
                    llm_errors.append(str((llm_result or {}).get("error") or "privacy_denied"))
                    continue
                revised = str((llm_result or {}).get("text") or "").strip()
                if revised and len(revised) > _MIN_REVISED_DRAFT_LENGTH:
                    improved_body = revised
                    applied_suggestions.append(suggestion)
            except Exception:
                llm_errors.append("private_generation_failed")

        improved = bool(applied_suggestions)
        if improved:
            import datetime as _dt
            draft["body"] = improved_body
            draft["updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
            draft["improvement_history"] = list(draft.get("improvement_history") or []) + [
                {
                    "improved_at": draft["updated_at"],
                    "applied_suggestions": applied_suggestions,
                    "quality_before_grade": str((quality_before or {}).get("grade") or ""),
                }
            ]
            state["draft"] = draft
            self._save_state(state)

        # 3. Re-score the improved draft.
        quality_after: Optional[Dict[str, Any]] = None
        if improved:
            after_report = _run_draft_logic_pipeline_safely(
                improved_body,
                state=state_code or str(state.get("intake_answers", {}).get("state") or "").strip() or None,
            )
            try:
                from integrations.ipfs_datasets.quality import score_draft_quality as _score
                quality_after = _score(after_report, claim_id=resolved_user_id)
            except Exception:
                pass
            if quality_after:
                self._persist_proof_run(state, proof_report=after_report, quality_score=quality_after)
                self._save_state(state)

        return {
            "status": "ok",
            "user_id": resolved_user_id,
            "improved": improved,
            "applied_suggestion_count": len(applied_suggestions),
            "applied_suggestions": applied_suggestions,
            "quality_before": quality_before,
            "quality_after": quality_after,
            "llm_errors": llm_errors,
            "draft_body_length": len(improved_body),
        }

    # ------------------------------------------------------------------
    # get_proof_history
    # ------------------------------------------------------------------

    def get_proof_history(
        self,
        user_id: Optional[str],
    ) -> Dict[str, Any]:
        """Return the history of proof-pipeline runs for this session.

        Each entry in ``history`` is a compact snapshot produced by
        :meth:`_persist_proof_run` and includes ``run_at``, ``proof_status``,
        ``contradiction_count``, ``corpus_coverage_percent``,
        ``overall_score``, and ``grade`` (when a quality score was computed).

        The most recent entry is last.
        """
        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._load_state(resolved_user_id)
        history = list(state.get("proof_history") or [])
        trend: Optional[str] = None
        if len(history) >= 2:
            first_score = history[0].get("overall_score")
            last_score = history[-1].get("overall_score")
            # Only compute trend when both endpoints have a numeric quality score.
            if first_score is not None and last_score is not None:
                if last_score > first_score + 5:
                    trend = "improving"
                elif last_score < first_score - 5:
                    trend = "declining"
                else:
                    trend = "stable"
        return {
            "status": "ok",
            "user_id": resolved_user_id,
            "history": history,
            "run_count": len(history),
            "trend": trend,
            "latest": history[-1] if history else None,
        }

    def update_filing_metadata(
        self,
        user_id: Optional[str],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        state = self._load_state(str(user_id or DEFAULT_USER_ID))
        filing_metadata = dict(state.get("filing_metadata") or {})
        for key in (
            "caption_plaintiffs",
            "caption_defendants",
            "signature_plaintiff",
            "signature_role",
            "mailing_address",
        ):
            value = str((metadata or {}).get(key) or "").strip()
            if value:
                filing_metadata[key] = value
        state["filing_metadata"] = filing_metadata
        state["draft"] = None
        self._save_state(state)
        session = self.get_session(str(state.get("user_id")))
        return {
            "session": session["session"],
            "review": session["review"],
            "questions": session["questions"],
            "next_question": session["next_question"],
            "case_synopsis": session["case_synopsis"],
            "filing_metadata": deepcopy(session["session"].get("filing_metadata") or {}),
        }

    def reset_session(self, user_id: Optional[str]) -> Dict[str, Any]:
        return self.request_handlers.reset_session(user_id)

    def normal_reset_retention_receipt(self) -> Dict[str, Any]:
        from integrations.private_storage import normal_reset_retention_receipt

        return normal_reset_retention_receipt()

    def delete_private_case(
        self,
        user_id: Optional[str],
        *,
        tenant_id: str,
        case_id: str,
        repository: str | Path,
        policy: str,
        legal_hold: bool = False,
        workspace_required: bool = False,
        providers: Optional[Mapping[str, Any]] = None,
        timeout_seconds: Optional[float] = None,
        crash_at: Optional[str] = None,
        principal_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """User-visible scoped deletion. Normal reset does not call this."""

        del principal_id
        self._require_local_filesystem_access()
        self._check_access(user_id or tenant_id, ability="write", case_id=case_id)
        from integrations.private_storage import delete_private_case as _delete

        return _delete(
            repository,
            self._private_key_session(),
            tenant_id=tenant_id,
            case_id=case_id,
            policy=policy,
            legal_hold=legal_hold,
            workspace_required=workspace_required,
            providers=providers,
            timeout_seconds=timeout_seconds,
            crash_at=crash_at,
        )

    def _resolve_docket_path(self, path_value: str | Path) -> str:
        self._require_local_filesystem_access()
        return str(Path(str(path_value)).expanduser().resolve())

    def _resolve_workspace_dataset_path(self, path_value: str | Path) -> str:
        self._require_local_filesystem_access()
        return str(Path(str(path_value)).expanduser().resolve())

    def _load_workspace_dataset_payload(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
    ) -> Dict[str, Any]:
        resolved_path = self._resolve_workspace_dataset_path(input_path)
        normalized_type = str(input_type or "packaged").strip().lower()
        if normalized_type in {"single", "single_parquet", "parquet"}:
            return self._load_workspace_single_parquet_payload(resolved_path)

        from integrations.ipfs_datasets.legal_data import load_legal_symbol

        WorkspaceDatasetBuilder = load_legal_symbol("WorkspaceDatasetBuilder")
        load_packaged_workspace_dataset = load_legal_symbol("load_packaged_workspace_dataset")

        if normalized_type == "packaged":
            dataset = load_packaged_workspace_dataset(resolved_path)
        elif normalized_type == "json":
            dataset = WorkspaceDatasetBuilder().build_from_json_file(resolved_path)
        else:
            raise ValueError(f"Unsupported workspace dataset input_type: {input_type}")
        return dict(dataset.to_dict() if hasattr(dataset, "to_dict") else dataset)

    @staticmethod
    def _load_workspace_single_parquet_payload(input_path: str | Path) -> Dict[str, Any]:
        import pyarrow.parquet as pq

        table = pq.read_table(
            str(input_path),
            columns=[
                "dataset_id",
                "workspace_id",
                "workspace_name",
                "source_type",
                "section",
                "row_id",
                "title",
                "text",
                "payload_json",
            ],
        )
        rows = table.to_pylist()
        sections: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            section = str(row.get("section") or "").strip()
            if not section:
                continue
            try:
                payload = json.loads(str(row.get("payload_json") or "{}"))
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            payload.setdefault("row_id", row.get("row_id"))
            if row.get("title") and not payload.get("title"):
                payload["title"] = row.get("title")
            if row.get("text") and not payload.get("text"):
                payload["text"] = row.get("text")
            sections.setdefault(section, []).append(payload)

        core = dict(sections.get("dataset_core", [{}])[0] or {})
        metadata = dict(core.get("metadata") or {})
        if sections.get("zkp_proof_certificates"):
            metadata.setdefault("zkp_proof_certificates", sections["zkp_proof_certificates"])
        formal_logic = dict(metadata.get("formal_logic") or {})
        proof_store = dict(formal_logic.get("proof_store") or {})
        if sections.get("zkp_proof_certificates"):
            proof_store.setdefault("zkp_proof_certificates", sections["zkp_proof_certificates"])
            formal_logic["proof_store"] = proof_store
            metadata["formal_logic"] = formal_logic

        return {
            **core,
            "dataset_id": core.get("dataset_id") or (rows[0].get("dataset_id") if rows else ""),
            "workspace_id": core.get("workspace_id") or (rows[0].get("workspace_id") if rows else ""),
            "workspace_name": core.get("workspace_name") or (rows[0].get("workspace_name") if rows else ""),
            "source_type": core.get("source_type") or (rows[0].get("source_type") if rows else ""),
            "documents": sections.get("documents", []),
            "collections": sections.get("collections", []),
            "knowledge_graph": {
                **dict(core.get("knowledge_graph") or {}),
                "entities": sections.get("knowledge_graph_entities", []),
                "relationships": sections.get("knowledge_graph_relationships", []),
            },
            "bm25_index": {
                **dict(core.get("bm25_index") or {}),
                "documents": sections.get("bm25_documents", []),
            },
            "vector_index": {
                **dict(core.get("vector_index") or {}),
                "items": sections.get("vector_items", []),
            },
            "metadata": metadata,
            "_single_parquet_sections": {key: len(value) for key, value in sections.items()},
        }

    @staticmethod
    def _summarize_workspace_dataset_payload(dataset_payload: Mapping[str, Any]) -> Dict[str, Any]:
        metadata = dict(dataset_payload.get("metadata") or {})
        formal_logic = dict(metadata.get("formal_logic") or {})
        summary = dict(metadata.get("formal_logic_summary") or formal_logic.get("summary") or {})
        proof_store = dict(formal_logic.get("proof_store") or {})
        knowledge_graph = dict(dataset_payload.get("knowledge_graph") or {})
        return {
            "document_count": len(list(dataset_payload.get("documents") or [])),
            "collection_count": len(list(dataset_payload.get("collections") or [])),
            "knowledge_graph_entity_count": len(list(knowledge_graph.get("entities") or [])),
            "knowledge_graph_relationship_count": len(list(knowledge_graph.get("relationships") or [])),
            "bm25_document_count": len(list((dataset_payload.get("bm25_index") or {}).get("documents") or [])),
            "vector_document_count": len(list((dataset_payload.get("vector_index") or {}).get("items") or [])),
            "first_order_formula_count": int(summary.get("first_order_formula_count") or summary.get("fol_formula_count") or 0),
            "temporal_deontic_formula_count": int(
                summary.get("temporal_deontic_formula_count")
                or summary.get("temporal_formula_count")
                or summary.get("tdfol_formula_count")
                or 0
            ),
            "deontic_cognitive_event_count": int(summary.get("deontic_cognitive_event_count") or summary.get("dcec_formula_count") or 0),
            "formal_proof_count": int(summary.get("formal_proof_count") or summary.get("proof_count") or len(list(proof_store.get("proofs") or []))),
            "proof_certificate_count": int(summary.get("proof_certificate_count") or len(list(proof_store.get("certificates") or []))),
            "zkp_certificate_count": int(
                summary.get("zkp_certificate_count")
                or len(list(proof_store.get("zkp_proof_certificates") or metadata.get("zkp_proof_certificates") or []))
            ),
        }

    @staticmethod
    def _search_workspace_dataset_local(
        dataset_payload: Mapping[str, Any],
        query: str,
        *,
        search_backend: str,
        top_k: int,
    ) -> Dict[str, Any]:
        terms = [term for term in re.findall(r"[A-Za-z0-9$%.-]+", str(query or "").lower()) if term]
        documents = [dict(item) for item in list(dataset_payload.get("documents") or []) if isinstance(item, dict)]
        rows = (
            list((dataset_payload.get("vector_index") or {}).get("items") or [])
            if str(search_backend or "").lower() == "vector"
            else list((dataset_payload.get("bm25_index") or {}).get("documents") or [])
        )
        document_by_id = {
            str(document.get("document_id") or document.get("id") or document.get("row_id") or ""): document
            for document in documents
        }
        scored: List[Dict[str, Any]] = []
        for row in rows or documents:
            item = dict(row) if isinstance(row, dict) else {}
            document_id = str(item.get("document_id") or item.get("id") or item.get("row_id") or "")
            document = dict(document_by_id.get(document_id) or item)
            haystack = " ".join(
                str(value or "")
                for value in [
                    item.get("title"),
                    item.get("text"),
                    item.get("content"),
                    item.get("payload_json"),
                    document.get("title"),
                    document.get("text"),
                    document.get("content"),
                    json.dumps(document, sort_keys=True),
                ]
            ).lower()
            score = float(sum(haystack.count(term) for term in terms)) if terms else 0.0
            if score <= 0:
                continue
            scored.append(
                {
                    "document_id": document_id or document.get("document_id") or document.get("id"),
                    "title": document.get("title") or item.get("title") or document_id,
                    "score": score,
                    "document": document,
                    "match_text": str(document.get("text") or item.get("text") or "")[:500],
                }
            )
        scored.sort(key=lambda item: (-float(item.get("score") or 0), str(item.get("title") or "")))
        return {
            "query": str(query or ""),
            "backend": f"local_{str(search_backend or 'bm25').lower()}",
            "results": scored[: max(1, int(top_k or 10))],
            "result_count": len(scored[: max(1, int(top_k or 10))]),
        }

    @staticmethod
    def _apply_workspace_dataset_filters(
        dataset_payload: Dict[str, Any],
        *,
        collection_id: Optional[str] = None,
        document_type: Optional[str] = None,
        claim_type: Optional[str] = None,
        claim_element_id: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_filters = {
            "collection_id": str(collection_id or "").strip(),
            "document_type": str(document_type or "").strip(),
            "claim_type": str(claim_type or "").strip(),
            "claim_element_id": str(claim_element_id or "").strip(),
            "source_type": str(source_type or "").strip(),
        }

        def _matches_document(document: Mapping[str, Any]) -> bool:
            metadata = dict(document.get("metadata") or {})
            for key, expected in normalized_filters.items():
                if not expected:
                    continue
                candidates = [
                    document.get(key),
                    metadata.get(key),
                    metadata.get(key.replace("_id", "")),
                ]
                if key == "source_type":
                    candidates.extend(
                        [
                            dataset_payload.get("source_type"),
                            metadata.get("source_family"),
                            metadata.get("source"),
                        ]
                    )
                values = {str(value).strip().lower() for value in candidates if str(value or "").strip()}
                expected_lower = expected.lower()
                if key == "source_type":
                    matched = any(
                        expected_lower == value
                        or expected_lower in value
                        or value in expected_lower
                        for value in values
                    )
                else:
                    matched = expected_lower in values
                if not matched:
                    return False
            return True

        documents = [dict(item) for item in list(dataset_payload.get("documents") or []) if isinstance(item, dict)]
        filtered_documents = [item for item in documents if _matches_document(item)]
        allowed_document_ids = {
            str(item.get("document_id") or "").strip()
            for item in filtered_documents
            if str(item.get("document_id") or "").strip()
        }

        def _filter_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            filtered: List[Dict[str, Any]] = []
            for row in rows:
                document_id = str(row.get("document_id") or "").strip()
                if not document_id or document_id in allowed_document_ids:
                    filtered.append(dict(row))
            return filtered

        collections = [dict(item) for item in list(dataset_payload.get("collections") or []) if isinstance(item, dict)]
        filtered_collections: List[Dict[str, Any]] = []
        for collection in collections:
            if normalized_filters["collection_id"]:
                candidate_id = str(collection.get("id") or collection.get("collection_id") or "").strip()
                if candidate_id.lower() != normalized_filters["collection_id"].lower():
                    continue
            document_ids = [str(item).strip() for item in list(collection.get("document_ids") or []) if str(item).strip()]
            if allowed_document_ids and document_ids and not any(item in allowed_document_ids for item in document_ids):
                continue
            filtered_collections.append(collection)

        return {
            **dict(dataset_payload),
            "documents": filtered_documents,
            "collections": filtered_collections,
            "bm25_index": {
                **dict(dataset_payload.get("bm25_index") or {}),
                "documents": _filter_rows([dict(item) for item in list((dataset_payload.get("bm25_index") or {}).get("documents") or []) if isinstance(item, dict)]),
            },
            "vector_index": {
                **dict(dataset_payload.get("vector_index") or {}),
                "items": _filter_rows([dict(item) for item in list((dataset_payload.get("vector_index") or {}).get("items") or []) if isinstance(item, dict)]),
            },
            "applied_filters": {key: value for key, value in normalized_filters.items() if value},
        }

    def _load_docket_dataset_payload(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
    ) -> Dict[str, Any]:
        from integrations.ipfs_datasets.legal_data import DocketDatasetBuilder, load_packaged_docket_dataset

        resolved_path = self._resolve_docket_path(input_path)
        normalized_type = str(input_type or "packaged").strip().lower()
        if normalized_type == "packaged":
            dataset = load_packaged_docket_dataset(resolved_path)
        elif normalized_type == "json":
            dataset = DocketDatasetBuilder().build_from_json_file(resolved_path)
        elif normalized_type == "single":
            dataset = self._load_docket_dataset_single_parquet(resolved_path)
        else:
            raise ValueError(f"Unsupported docket input_type: {input_type}")
        return dict(dataset.to_dict() if hasattr(dataset, "to_dict") else dataset)

    @staticmethod
    def _decode_parquet_bundle_section(rows: List[Dict[str, Any]], section: str) -> List[Dict[str, Any]]:
        decoded: List[Dict[str, Any]] = []
        for row in rows:
            if str(row.get("section") or "") != section:
                continue
            payload_json = str(row.get("payload_json") or "").strip()
            if not payload_json:
                continue
            decoded.append(dict(json.loads(payload_json)))
        return decoded

    @classmethod
    def _load_docket_dataset_single_parquet(cls, parquet_path: str | Path) -> Dict[str, Any]:
        import pyarrow.parquet as pq

        resolved_path = Path(str(parquet_path)).expanduser().resolve()
        rows = [dict(row) for row in pq.read_table(resolved_path).to_pylist()]
        dataset_core_rows = cls._decode_parquet_bundle_section(rows, "dataset_core")
        dataset_core = dict(dataset_core_rows[0]) if dataset_core_rows else {}
        documents = cls._decode_parquet_bundle_section(rows, "documents")
        knowledge_graph_entities = cls._decode_parquet_bundle_section(rows, "knowledge_graph_entities")
        knowledge_graph_relationships = cls._decode_parquet_bundle_section(rows, "knowledge_graph_relationships")
        deontic_nodes = cls._decode_parquet_bundle_section(rows, "deontic_nodes")
        deontic_rules = cls._decode_parquet_bundle_section(rows, "deontic_rules")
        proof_agenda = cls._decode_parquet_bundle_section(rows, "proof_agenda")
        proof_evidence_packets = cls._decode_parquet_bundle_section(rows, "proof_evidence_packets")
        proof_revalidation_runs = cls._decode_parquet_bundle_section(rows, "proof_revalidation_runs")
        bm25_documents = cls._decode_parquet_bundle_section(rows, "bm25_documents")
        vector_items = cls._decode_parquet_bundle_section(rows, "vector_items")
        return {
            "dataset_id": str(dataset_core.get("dataset_id") or ""),
            "docket_id": str(dataset_core.get("docket_id") or ""),
            "case_name": str(dataset_core.get("case_name") or ""),
            "court": str(dataset_core.get("court") or ""),
            "documents": documents,
            "plaintiff_docket": cls._decode_parquet_bundle_section(rows, "plaintiff_docket"),
            "defendant_docket": cls._decode_parquet_bundle_section(rows, "defendant_docket"),
            "authorities": cls._decode_parquet_bundle_section(rows, "authorities"),
            "knowledge_graph": {
                "entities": knowledge_graph_entities,
                "relationships": knowledge_graph_relationships,
            },
            "deontic_graph": {
                "nodes": {str(item.get("node_id") or item.get("id") or index): item for index, item in enumerate(deontic_nodes, start=1)},
                "rules": {str(item.get("rule_id") or item.get("id") or index): item for index, item in enumerate(deontic_rules, start=1)},
            },
            "proof_assistant": {
                "agenda": proof_agenda,
                "evidence_packets": proof_evidence_packets,
                "revalidation_runs": proof_revalidation_runs,
            },
            "bm25_index": {
                "backend": "local_bm25",
                "documents": bm25_documents,
                "document_count": len(bm25_documents),
            },
            "vector_index": {
                "backend": "local_hashed_term_projection",
                "items": vector_items,
                "document_count": len(vector_items),
            },
            "metadata": dict(dataset_core.get("metadata") or {}),
            "bundle": {
                "parquet_path": str(resolved_path),
                "row_count": len(rows),
                "sections": sorted({str(row.get("section") or "") for row in rows if str(row.get("section") or "")}),
            },
        }

    @staticmethod
    def _build_docket_document_view(
        dataset_payload: Dict[str, Any],
        *,
        include_document_text: bool,
        document_limit: Optional[int],
    ) -> List[Dict[str, Any]]:
        documents = list(dataset_payload.get("documents") or [])
        if document_limit is not None:
            documents = documents[: max(0, int(document_limit))]
        view: List[Dict[str, Any]] = []
        for document in documents:
            if not isinstance(document, dict):
                continue
            row = {
                "id": document.get("id"),
                "title": document.get("title"),
                "date_filed": document.get("date_filed"),
                "document_number": document.get("document_number"),
                "source_url": document.get("source_url"),
                "metadata": dict(document.get("metadata") or {}),
            }
            if include_document_text:
                row["text"] = document.get("text")
            view.append(row)
        return view

    @staticmethod
    def _issue_links_from_knowledge_graph(knowledge_graph: Dict[str, Any]) -> Dict[str, Any]:
        entities = [
            dict(entity)
            for entity in list((knowledge_graph or {}).get("entities") or [])
            if isinstance(entity, dict)
        ]
        relationships = [
            dict(relationship)
            for relationship in list((knowledge_graph or {}).get("relationships") or [])
            if isinstance(relationship, dict)
        ]
        entity_by_id = {
            str(entity.get("id") or ""): entity
            for entity in entities
            if str(entity.get("id") or "").strip()
        }

        def _entity_matches_issue(entity: Dict[str, Any]) -> bool:
            haystacks = [
                str(entity.get("type") or ""),
                str(entity.get("label") or ""),
                str(entity.get("name") or ""),
                str(entity.get("category") or ""),
                str((entity.get("metadata") or {}).get("type") or ""),
                str((entity.get("metadata") or {}).get("category") or ""),
            ]
            lowered = " ".join(haystacks).lower()
            return any(keyword in lowered for keyword in _DOCKET_ISSUE_ENTITY_KEYWORDS)

        issue_entities = [entity for entity in entities if _entity_matches_issue(entity)]
        issue_entity_ids = {
            str(entity.get("id") or "")
            for entity in issue_entities
            if str(entity.get("id") or "").strip()
        }
        issue_links: List[Dict[str, Any]] = []
        for relationship in relationships:
            source_id = str(
                relationship.get("source")
                or relationship.get("source_id")
                or relationship.get("from")
                or relationship.get("head")
                or ""
            ).strip()
            target_id = str(
                relationship.get("target")
                or relationship.get("target_id")
                or relationship.get("to")
                or relationship.get("tail")
                or ""
            ).strip()
            if not source_id or not target_id:
                continue
            if source_id not in issue_entity_ids and target_id not in issue_entity_ids:
                continue
            issue_links.append(
                {
                    "id": relationship.get("id"),
                    "type": relationship.get("type") or relationship.get("label"),
                    "source_id": source_id,
                    "target_id": target_id,
                    "source_entity": entity_by_id.get(source_id),
                    "target_entity": entity_by_id.get(target_id),
                    "metadata": dict(relationship.get("metadata") or {}),
                }
            )
        return {
            "entities": entities,
            "relationships": relationships,
            "issue_entities": issue_entities,
            "issue_links": issue_links,
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "issue_entity_count": len(issue_entities),
            "issue_link_count": len(issue_links),
        }

    def view_docket_dataset(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
        include_document_text: bool = False,
        document_limit: Optional[int] = 25,
    ) -> Dict[str, Any]:
        from integrations.ipfs_datasets.legal_data import summarize_docket_dataset

        resolved_path = self._resolve_docket_path(input_path)
        dataset_payload = self._load_docket_dataset_payload(resolved_path, input_type=input_type)
        summary = summarize_docket_dataset(dataset_payload)
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "summary": dict(summary),
            "documents": self._build_docket_document_view(
                dataset_payload,
                include_document_text=bool(include_document_text),
                document_limit=document_limit,
            ),
            "metadata": dict(dataset_payload.get("metadata") or {}),
            "source": "complaint_workspace_docket_view",
        }

    @staticmethod
    def _search_docket_dataset_local(
        dataset_payload: Mapping[str, Any],
        query: str,
        *,
        top_k: int,
    ) -> Dict[str, Any]:
        needle = str(query or "").strip().lower()
        matches: List[Dict[str, Any]] = []
        for document in list((dataset_payload or {}).get("documents") or []):
            if not isinstance(document, dict):
                continue
            haystack = " ".join(
                [
                    str(document.get("title") or ""),
                    str(document.get("text") or ""),
                    str(document.get("document_number") or ""),
                ]
            ).lower()
            if needle and needle not in haystack:
                continue
            matches.append(
                {
                    "document_id": str(document.get("id") or document.get("document_id") or ""),
                    "title": str(document.get("title") or ""),
                    "document_number": str(document.get("document_number") or ""),
                    "score": 1.0 if needle else 0.0,
                    "snippet": str(document.get("text") or "")[:280],
                }
            )
        matches = matches[: max(0, int(top_k or 10))]
        return {
            "query": str(query or ""),
            "result_count": len(matches),
            "items": matches,
        }

    @staticmethod
    def _build_workspace_document_view(
        dataset_payload: Dict[str, Any],
        *,
        include_document_text: bool,
        document_limit: Optional[int],
    ) -> List[Dict[str, Any]]:
        documents = list(dataset_payload.get("documents") or [])
        if document_limit is not None:
            documents = documents[: max(0, int(document_limit))]
        view: List[Dict[str, Any]] = []
        for document in documents:
            if not isinstance(document, dict):
                continue
            metadata = dict(document.get("metadata") or {})
            item = {
                "document_id": str(document.get("document_id") or ""),
                "title": str(document.get("title") or ""),
                "captured_at": str(document.get("captured_at") or ""),
                "document_number": str(document.get("document_number") or ""),
                "source_url": str(document.get("source_url") or ""),
                "collection_id": str(document.get("collection_id") or metadata.get("collection_id") or ""),
                "document_type": str(document.get("document_type") or metadata.get("document_type") or ""),
                "claim_type": str(document.get("claim_type") or metadata.get("claim_type") or ""),
                "claim_element_id": str(document.get("claim_element_id") or metadata.get("claim_element_id") or ""),
                "source_type": str(document.get("source_type") or metadata.get("source_type") or metadata.get("source_family") or ""),
                "metadata": metadata,
            }
            if include_document_text:
                item["text"] = str(document.get("text") or "")
            view.append(item)
        return view

    def view_workspace_dataset(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
        include_document_text: bool = False,
        document_limit: Optional[int] = 25,
        collection_id: Optional[str] = None,
        document_type: Optional[str] = None,
        claim_type: Optional[str] = None,
        claim_element_id: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_path = self._resolve_workspace_dataset_path(input_path)
        normalized_type = str(input_type or "packaged").strip().lower()
        dataset_payload = self._load_workspace_dataset_payload(resolved_path, input_type=input_type)
        filtered_payload = self._apply_workspace_dataset_filters(
            dataset_payload,
            collection_id=collection_id,
            document_type=document_type,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            source_type=source_type,
        )
        if normalized_type in {"single", "single_parquet", "parquet"}:
            summary = self._summarize_workspace_dataset_payload(filtered_payload)
        else:
            from integrations.ipfs_datasets.legal_data import load_legal_symbol

            summarize_workspace_dataset = load_legal_symbol("summarize_workspace_dataset")
            summary = dict(summarize_workspace_dataset(filtered_payload))
        return {
            "input_path": resolved_path,
            "input_type": normalized_type,
            "summary": summary,
            "documents": self._build_workspace_document_view(
                filtered_payload,
                include_document_text=bool(include_document_text),
                document_limit=document_limit,
            ),
            "collections": [dict(item) for item in list(filtered_payload.get("collections") or []) if isinstance(item, dict)],
            "metadata": dict(filtered_payload.get("metadata") or {}),
            "applied_filters": dict(filtered_payload.get("applied_filters") or {}),
            "source": "complaint_workspace_dataset_view",
        }

    @staticmethod
    def _workspace_graph_text(item: Dict[str, Any]) -> str:
        values = [
            item.get("id"),
            item.get("label"),
            item.get("name"),
            item.get("type"),
            item.get("document_id"),
            item.get("source_document"),
        ]
        properties = item.get("properties") or item.get("metadata") or {}
        if isinstance(properties, dict):
            values.extend(str(value) for value in properties.values() if isinstance(value, (str, int, float)))
        return " ".join(str(value or "") for value in values).lower()

    @staticmethod
    def _workspace_relationship_endpoints(relationship: Dict[str, Any]) -> tuple[str, str]:
        source_id = str(
            relationship.get("source")
            or relationship.get("source_id")
            or relationship.get("from")
            or relationship.get("head")
            or ""
        )
        target_id = str(
            relationship.get("target")
            or relationship.get("target_id")
            or relationship.get("to")
            or relationship.get("tail")
            or ""
        )
        return source_id, target_id

    @staticmethod
    def _compact_workspace_entity(entity: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(entity.get("id") or ""),
            "label": str(entity.get("label") or entity.get("name") or entity.get("id") or ""),
            "type": str(entity.get("type") or ""),
            "properties": dict(entity.get("properties") or entity.get("metadata") or {}),
            "confidence": entity.get("confidence"),
        }

    @classmethod
    def _compact_workspace_relationship(
        cls,
        relationship: Dict[str, Any],
        entity_by_id: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        source_id, target_id = cls._workspace_relationship_endpoints(relationship)
        return {
            "id": str(relationship.get("id") or ""),
            "type": str(relationship.get("type") or relationship.get("label") or ""),
            "source": source_id,
            "target": target_id,
            "source_label": str((entity_by_id.get(source_id) or {}).get("label") or source_id),
            "target_label": str((entity_by_id.get(target_id) or {}).get("label") or target_id),
            "properties": dict(relationship.get("properties") or relationship.get("metadata") or {}),
            "confidence": relationship.get("confidence"),
        }

    @staticmethod
    def _workspace_logic_statement_text(statement: Dict[str, Any]) -> str:
        return " ".join(
            str(statement.get(key) or "")
            for key in ("id", "entity", "modality", "action", "source_document", "source_text")
        ).lower()

    @staticmethod
    def _normalize_workspace_modality(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"permission", "permitted", "may", "allowed", "allowance"}:
            return "allowed"
        if text in {"obligation", "obligatory", "required", "requirement", "must", "shall", "duty"}:
            return "required"
        if text in {"prohibition", "prohibited", "forbidden", "disallowed", "cannot", "must_not"}:
            return "prohibited"
        if text in {"conditional", "condition", "if_then"}:
            return "conditional"
        return text or "unknown"

    @staticmethod
    def _statement_event_candidates(statement: Dict[str, Any], events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        statement_id = str(statement.get("id") or "")
        action = str(statement.get("action") or "").strip().lower()
        entity = str(statement.get("entity") or "").strip().lower()
        direct_matches: List[Dict[str, Any]] = []
        entity_matches: List[Dict[str, Any]] = []
        for event in events:
            event_id = str(event.get("id") or "")
            event_label = str(event.get("label") or "").strip().lower()
            event_agent = str(event.get("agent") or "").strip().lower()
            if statement_id and event_id.startswith(f"{statement_id}:"):
                direct_matches.append(event)
            elif action and (action in event_label or event_label in action):
                direct_matches.append(event)
            elif entity and event_agent == entity:
                entity_matches.append(event)
        return (direct_matches or entity_matches)[:5]

    @staticmethod
    def _workspace_formula_text(value: Any) -> str:
        if isinstance(value, dict):
            return " ".join(str(item or "") for item in value.values()).lower()
        return str(value or "").lower()

    @staticmethod
    def _compact_workspace_proof_certificate(certificate: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "certificate_id": str(certificate.get("certificate_id") or ""),
            "backend": str(certificate.get("backend") or ""),
            "format": str(certificate.get("format") or ""),
            "theorem": str(certificate.get("theorem") or "")[:500],
            "assumptions": [str(item)[:300] for item in list(certificate.get("assumptions") or [])[:5]],
        }

    @classmethod
    def _build_workspace_logic_systems(
        cls,
        formal_logic: Dict[str, Any],
        *,
        query: str = "",
        limit: int = 50,
    ) -> Dict[str, Any]:
        normalized_query = str(query or "").strip().lower()
        sample_limit = min(max(int(limit or 50), 1), 20)

        def formula_sample(system_payload: Any) -> List[Any]:
            if isinstance(system_payload, dict):
                formulas = list(system_payload.get("formulas") or [])
            elif isinstance(system_payload, list):
                formulas = list(system_payload)
            else:
                formulas = []
            if normalized_query:
                formulas = [
                    formula
                    for formula in formulas
                    if normalized_query in cls._workspace_formula_text(formula)
                ]
            return formulas[:sample_limit]

        temporal_payload = dict(formal_logic.get("temporal_fol") or {})
        dcec_payload = dict(formal_logic.get("deontic_cognitive_event_calculus") or {})
        fol_payload = dict(formal_logic.get("first_order_logic") or {})
        frame_logic_payload = dict(formal_logic.get("frame_logic") or {})
        document_frame_logic_payload = dict(formal_logic.get("document_frame_logic") or {})
        temporal_formulas = formula_sample(temporal_payload)
        dcec_formulas = formula_sample(dcec_payload)
        fol_formulas = formula_sample(fol_payload)
        frame_records = list(frame_logic_payload.values()) or list(document_frame_logic_payload.values())
        if normalized_query:
            frame_records = [
                record
                for record in frame_records
                if normalized_query in cls._workspace_formula_text(record)
            ]

        return {
            "deontic_temporal_first_order_logic": {
                "backend": str(temporal_payload.get("backend") or ""),
                "formula_count": int(temporal_payload.get("formula_count") or len(temporal_payload.get("formulas") or [])),
                "sample": temporal_formulas,
            },
            "first_order_logic": {
                "backend": str(fol_payload.get("backend") or temporal_payload.get("backend") or ""),
                "formula_count": int(fol_payload.get("formula_count") or len(fol_payload.get("formulas") or [])),
                "sample": fol_formulas,
            },
            "deontic_cognitive_event_calculus": {
                "backend": str(dcec_payload.get("backend") or ""),
                "formula_count": int(dcec_payload.get("formula_count") or len(dcec_payload.get("formulas") or [])),
                "sample": dcec_formulas,
            },
            "frame_logic": {
                "backend": str((frame_logic_payload.get("metadata") or {}).get("backend") or ""),
                "record_count": len(frame_logic_payload) or len(document_frame_logic_payload),
                "sample": frame_records[:sample_limit],
            },
        }

    @classmethod
    def _build_workspace_proof_system(
        cls,
        proof_store: Dict[str, Any],
        *,
        query: str = "",
        limit: int = 50,
    ) -> Dict[str, Any]:
        normalized_query = str(query or "").strip().lower()
        sample_limit = min(max(int(limit or 50), 1), 20)
        proof_summary = dict(proof_store.get("summary") or {})
        proof_metadata = dict(proof_store.get("metadata") or {})
        zkp_status = dict(proof_metadata.get("zkp_status") or {})
        proofs = {
            str(key): dict(value)
            for key, value in dict(proof_store.get("proofs") or {}).items()
            if isinstance(value, dict)
        }
        certificates = [dict(item) for item in list(proof_store.get("certificates") or []) if isinstance(item, dict)]
        if normalized_query:
            sample_proofs = [
                proof
                for proof in proofs.values()
                if normalized_query in json.dumps(proof, ensure_ascii=False).lower()
            ]
            sample_certificates = [
                certificate
                for certificate in certificates
                if normalized_query in json.dumps(certificate, ensure_ascii=False).lower()
            ]
        else:
            sample_proofs = list(proofs.values())
            sample_certificates = certificates

        certificate_backend_counts: Dict[str, int] = {}
        certificate_format_counts: Dict[str, int] = {}
        for certificate in certificates:
            backend = str(certificate.get("backend") or "unknown")
            proof_format = str(certificate.get("format") or "unknown")
            certificate_backend_counts[backend] = certificate_backend_counts.get(backend, 0) + 1
            certificate_format_counts[proof_format] = certificate_format_counts.get(proof_format, 0) + 1

        return {
            "backend": str(proof_metadata.get("backend") or ""),
            "summary": proof_summary,
            "proof_count": int(proof_summary.get("proof_count") or len(proofs)),
            "certificate_count": len(certificates),
            "certificate_backend_counts": certificate_backend_counts,
            "certificate_format_counts": certificate_format_counts,
            "zero_knowledge_proofs": {
                "available": bool(zkp_status.get("available")),
                "backend": str(zkp_status.get("backend") or ""),
                "backend_info": dict(zkp_status.get("backend_info") or {}),
                "certificate_count": certificate_backend_counts.get(str(zkp_status.get("backend") or "groth16"), 0),
            },
            "sample_proofs": [
                {
                    "proof_id": str(proof.get("proof_id") or ""),
                    "status": str(proof.get("status") or ""),
                    "query": str(proof.get("query") or "")[:500],
                    "root_conclusion": str(proof.get("root_conclusion") or "")[:500],
                    "proof_hash": str(proof.get("proof_hash") or ""),
                    "certificate_count": len(list(proof.get("certificates") or [])),
                }
                for proof in sample_proofs[:sample_limit]
            ],
            "sample_certificates": [
                cls._compact_workspace_proof_certificate(certificate)
                for certificate in sample_certificates[:sample_limit]
            ],
        }

    @classmethod
    def _build_workspace_logic_flow(
        cls,
        formal_logic: Dict[str, Any],
        *,
        entity_query: str = "",
        document_id: str = "",
        modality: str = "",
        limit: int = 50,
    ) -> Dict[str, Any]:
        normalized_query = str(entity_query or "").strip().lower()
        normalized_document_id = str(document_id or "").strip()
        normalized_modality = cls._normalize_workspace_modality(modality)
        apply_modality_filter = bool(str(modality or "").strip())
        document_analyses = {
            str(key): dict(value)
            for key, value in dict(formal_logic.get("document_analyses") or {}).items()
            if isinstance(value, dict)
        }
        proof_store = dict(formal_logic.get("proof_store") or {})
        certificates = [dict(item) for item in list(proof_store.get("certificates") or []) if isinstance(item, dict)]
        certificate_by_theorem: Dict[str, List[Dict[str, Any]]] = {}
        for certificate in certificates:
            theorem = str(certificate.get("theorem") or "").strip().lower()
            if theorem:
                certificate_by_theorem.setdefault(theorem, []).append(certificate)

        rows: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        deontic_analysis: List[Dict[str, Any]] = []
        event_rows: List[Dict[str, Any]] = []
        event_flow_edges: List[Dict[str, Any]] = []
        status_counts = {"allowed": 0, "required": 0, "prohibited": 0, "conditional": 0, "unknown": 0}
        for current_document_id, analysis in document_analyses.items():
            if normalized_document_id and normalized_document_id not in current_document_id:
                continue
            statements = [dict(item) for item in list(analysis.get("deontic_statements") or []) if isinstance(item, dict)]
            frames = [dict(item) for item in list(analysis.get("frames") or []) if isinstance(item, dict)]
            events = [dict(item) for item in list(analysis.get("events") or []) if isinstance(item, dict)]
            frame_by_statement_id = {
                str((frame.get("slots") or {}).get("statement_id") or frame.get("object_id") or frame.get("frame_id") or ""): frame
                for frame in frames
            }
            for statement in statements:
                if normalized_query and normalized_query not in cls._workspace_logic_statement_text(statement):
                    continue
                deontic_status = cls._normalize_workspace_modality(statement.get("modality"))
                if apply_modality_filter and deontic_status != normalized_modality:
                    continue
                statement_id = str(statement.get("id") or f"{current_document_id}:statement:{len(rows) + 1}")
                action = str(statement.get("action") or "")
                entity = str(statement.get("entity") or "")
                conditions = [str(item) for item in list(statement.get("conditions") or []) if str(item or "").strip()]
                exceptions = [str(item) for item in list(statement.get("exceptions") or []) if str(item or "").strip()]
                matched_events = cls._statement_event_candidates(statement, events)
                theorem_key = action.strip().lower()
                matching_certificates = [
                    dict(certificate)
                    for key, theorem_certificates in certificate_by_theorem.items()
                    if theorem_key and (theorem_key in key or key in theorem_key)
                    for certificate in theorem_certificates[:2]
                ]
                proof_backends = sorted({str(certificate.get("backend") or "") for certificate in matching_certificates if str(certificate.get("backend") or "").strip()})
                zkp_certificate_ids = [
                    str(certificate.get("certificate_id") or "")
                    for certificate in matching_certificates
                    if str(certificate.get("backend") or "").lower() == "groth16"
                    or "groth16" in str(certificate.get("format") or "").lower()
                ]
                frame = frame_by_statement_id.get(statement_id) or {}
                rows.append(
                    {
                        "document_id": current_document_id,
                        "statement_id": statement_id,
                        "entity": entity,
                        "modality": str(statement.get("modality") or ""),
                        "deontic_status": deontic_status,
                        "action": action,
                        "event_label": str((matched_events[0] if matched_events else {}).get("label") or action),
                        "conditions": conditions,
                        "exceptions": exceptions,
                        "source_text": str(statement.get("source_text") or "")[:500],
                        "frame_id": str(frame.get("frame_id") or frame.get("object_id") or ""),
                        "event_ids": [str(event.get("id") or "") for event in matched_events],
                        "proof_certificate_count": len(matching_certificates),
                        "proof_status": "proved" if matching_certificates else "unproved",
                        "proof_backends": proof_backends,
                        "zkp_certificate_ids": zkp_certificate_ids,
                        "proof_certificates": [
                            cls._compact_workspace_proof_certificate(certificate)
                            for certificate in matching_certificates[:2]
                        ],
                    }
                )
                status_counts[deontic_status if deontic_status in status_counts else "unknown"] += 1
                deontic_analysis.append(
                    {
                        "entity": entity,
                        "event": str((matched_events[0] if matched_events else {}).get("label") or action),
                        "status": deontic_status,
                        "modality": str(statement.get("modality") or ""),
                        "conditions": conditions,
                        "exceptions": exceptions,
                        "document_id": current_document_id,
                        "statement_id": statement_id,
                        "source_text": str(statement.get("source_text") or "")[:500],
                        "proof_certificate_count": len(matching_certificates),
                        "proof_status": "proved" if matching_certificates else "unproved",
                        "proof_backends": proof_backends,
                        "zkp_certificate_ids": zkp_certificate_ids,
                    }
                )
                for event in matched_events:
                    event_id = str(event.get("id") or "")
                    if event_id and not any(str(item.get("id") or "") == event_id for item in event_rows):
                        event_rows.append(
                            {
                                "id": event_id,
                                "label": str(event.get("label") or ""),
                                "agent": str(event.get("agent") or ""),
                                "time": str(event.get("time") or ""),
                                "document_id": current_document_id,
                            }
                        )
                edges.extend(
                    [
                        {
                            "source": current_document_id,
                            "target": statement_id,
                            "type": "EXTRACTED_STATEMENT",
                            "label": "document -> statement",
                        },
                        {
                            "source": statement_id,
                            "target": entity or "unknown_entity",
                            "type": deontic_status.upper(),
                            "label": "statement -> entity",
                        },
                    ]
                )
                for event in matched_events:
                    event_id = str(event.get("id") or "")
                    if event_id:
                        event_flow_edges.extend(
                            [
                                {
                                    "source": statement_id,
                                    "target": event_id,
                                    "type": "GOVERNS_EVENT",
                                    "label": f"{deontic_status} event",
                                },
                                {
                                    "source": entity or "unknown_entity",
                                    "target": event_id,
                                    "type": deontic_status.upper(),
                                    "label": f"{entity or 'entity'} is {deontic_status}",
                                },
                            ]
                        )
                for index, condition in enumerate(conditions, start=1):
                    event_flow_edges.append(
                        {
                            "source": f"{statement_id}:condition:{index}",
                            "target": statement_id,
                            "type": "CONDITION_FOR",
                            "label": condition,
                        }
                    )
                for index, exception in enumerate(exceptions, start=1):
                    event_flow_edges.append(
                        {
                            "source": f"{statement_id}:exception:{index}",
                            "target": statement_id,
                            "type": "EXCEPTION_TO",
                            "label": exception,
                        }
                    )
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break

        conflicts = [dict(item) for item in list(formal_logic.get("deontic_conflicts") or []) if isinstance(item, dict)]
        if normalized_query:
            conflicts = [
                conflict
                for conflict in conflicts
                if normalized_query in json.dumps(conflict, ensure_ascii=False).lower()
            ]
        formulas = {
            "temporal_fol": list((formal_logic.get("temporal_fol") or {}).get("formulas") or [])[: min(limit, 20)],
            "first_order_logic": list((formal_logic.get("first_order_logic") or {}).get("formulas") or [])[: min(limit, 20)],
            "dcec": list((formal_logic.get("deontic_cognitive_event_calculus") or {}).get("formulas") or [])[: min(limit, 20)],
            "frame_logic": list(dict(formal_logic.get("frame_logic") or {}).values())[: min(limit, 20)],
        }
        logic_systems = cls._build_workspace_logic_systems(formal_logic, query=entity_query, limit=limit)
        proof_system = cls._build_workspace_proof_system(proof_store, query=entity_query, limit=limit)
        return {
            "statements": rows,
            "flow_edges": edges[: limit * 2],
            "events": event_rows[:limit],
            "event_flow_edges": event_flow_edges[: limit * 3],
            "deontic_analysis": deontic_analysis[:limit],
            "deontic_status_counts": status_counts,
            "conflicts": conflicts[: min(limit, 20)],
            "formulas": formulas,
            "logic_systems": logic_systems,
            "proof_system": proof_system,
            "returned_statement_count": len(rows),
            "returned_flow_edge_count": min(len(edges), limit * 2),
            "returned_event_count": min(len(event_rows), limit),
            "returned_event_flow_edge_count": min(len(event_flow_edges), limit * 3),
            "returned_deontic_analysis_count": min(len(deontic_analysis), limit),
            "returned_conflict_count": min(len(conflicts), min(limit, 20)),
        }

    def get_workspace_dataset_graph(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
        entity_query: str = "",
        relationship_type: str = "",
        document_id: str = "",
        modality: str = "",
        limit: int = 50,
    ) -> Dict[str, Any]:
        resolved_path = self._resolve_workspace_dataset_path(input_path)
        normalized_type = str(input_type or "packaged").strip().lower()
        dataset_payload = self._load_workspace_dataset_payload(resolved_path, input_type=input_type)
        if normalized_type in {"single", "single_parquet", "parquet"}:
            summary = self._summarize_workspace_dataset_payload(dataset_payload)
        else:
            from integrations.ipfs_datasets.legal_data import load_legal_symbol

            summarize_workspace_dataset = load_legal_symbol("summarize_workspace_dataset")
            summary = dict(summarize_workspace_dataset(dataset_payload))
        knowledge_graph = dict(dataset_payload.get("knowledge_graph") or {})
        entities = [dict(item) for item in list(knowledge_graph.get("entities") or []) if isinstance(item, dict)]
        relationships = [dict(item) for item in list(knowledge_graph.get("relationships") or []) if isinstance(item, dict)]
        entity_by_id = {str(entity.get("id") or ""): entity for entity in entities if str(entity.get("id") or "").strip()}

        normalized_query = str(entity_query or "").strip().lower()
        normalized_relationship_type = str(relationship_type or "").strip().lower()
        normalized_document_id = str(document_id or "").strip().lower()
        bounded_limit = max(1, min(int(limit or 50), 500))

        matched_entities = []
        for entity in entities:
            entity_text = self._workspace_graph_text(entity)
            if normalized_query and normalized_query not in entity_text:
                continue
            matched_entities.append(entity)
        if not normalized_query and not normalized_document_id:
            matched_entities = entities
        matched_entity_ids = {str(entity.get("id") or "") for entity in matched_entities if str(entity.get("id") or "").strip()}

        matched_relationships = []
        for relationship in relationships:
            source_id, target_id = self._workspace_relationship_endpoints(relationship)
            relationship_type_text = str(relationship.get("type") or relationship.get("label") or "").lower()
            relationship_text = self._workspace_graph_text(relationship)
            touches_matched_entity = (
                (not normalized_query and not normalized_document_id)
                or source_id in matched_entity_ids
                or target_id in matched_entity_ids
            )
            if normalized_relationship_type and normalized_relationship_type not in relationship_type_text:
                continue
            if normalized_document_id and normalized_document_id not in relationship_text and normalized_document_id not in source_id.lower() and normalized_document_id not in target_id.lower():
                continue
            if normalized_query and not touches_matched_entity and normalized_query not in relationship_text:
                continue
            matched_relationships.append(relationship)

        neighbor_ids = set(matched_entity_ids)
        for relationship in matched_relationships:
            source_id, target_id = self._workspace_relationship_endpoints(relationship)
            if source_id:
                neighbor_ids.add(source_id)
            if target_id:
                neighbor_ids.add(target_id)
        neighborhood_entities = [entity_by_id[entity_id] for entity_id in neighbor_ids if entity_id in entity_by_id]

        metadata = dict(dataset_payload.get("metadata") or {})
        formal_logic = dict(metadata.get("formal_logic") or {})
        logic_flow = self._build_workspace_logic_flow(
            formal_logic,
            entity_query=entity_query,
            document_id=document_id,
            modality=modality,
            limit=bounded_limit,
        )
        formal_summary = dict(metadata.get("formal_logic_summary") or formal_logic.get("summary") or {})
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "dataset_id": dataset_payload.get("dataset_id"),
            "workspace_id": dataset_payload.get("workspace_id"),
            "workspace_name": dataset_payload.get("workspace_name"),
            "summary": summary,
            "filters": {
                "entity_query": str(entity_query or ""),
                "relationship_type": str(relationship_type or ""),
                "document_id": str(document_id or ""),
                "modality": str(modality or ""),
                "limit": bounded_limit,
            },
            "knowledge_graph": {
                "entity_count": len(entities),
                "relationship_count": len(relationships),
                "matched_entity_count": len(matched_entities),
                "matched_relationship_count": len(matched_relationships),
                "returned_entity_count": min(len(neighborhood_entities), bounded_limit),
                "returned_relationship_count": min(len(matched_relationships), bounded_limit),
                "entities": [self._compact_workspace_entity(entity) for entity in neighborhood_entities[:bounded_limit]],
                "relationships": [
                    self._compact_workspace_relationship(relationship, entity_by_id)
                    for relationship in matched_relationships[:bounded_limit]
                ],
            },
            "logical_flow": {
                **logic_flow,
                "summary": formal_summary,
            },
            "metadata": {
                "artifact_status": dict(metadata.get("artifact_status") or {}),
                "artifact_provenance": dict(metadata.get("artifact_provenance") or {}),
                "formal_logic_summary": formal_summary,
            },
            "source": "complaint_workspace_dataset_graph",
        }

    def search_workspace_dataset(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
        query: str,
        search_backend: str = "bm25",
        top_k: int = 10,
        vector_dimension: int = 32,
        collection_id: Optional[str] = None,
        document_type: Optional[str] = None,
        claim_type: Optional[str] = None,
        claim_element_id: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_path = self._resolve_workspace_dataset_path(input_path)
        normalized_backend = str(search_backend or "bm25").strip().lower()
        normalized_type = str(input_type or "packaged").strip().lower()
        dataset_payload = self._load_workspace_dataset_payload(resolved_path, input_type=input_type)
        filtered_payload = self._apply_workspace_dataset_filters(
            dataset_payload,
            collection_id=collection_id,
            document_type=document_type,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            source_type=source_type,
        )
        if normalized_backend not in {"bm25", "vector"}:
            raise ValueError(f"Unsupported workspace search backend: {search_backend}")
        if normalized_type in {"single", "single_parquet", "parquet"}:
            results = self._search_workspace_dataset_local(
                filtered_payload,
                query,
                search_backend=normalized_backend,
                top_k=int(top_k or 10),
            )
            summary = self._summarize_workspace_dataset_payload(filtered_payload)
        else:
            from integrations.ipfs_datasets.legal_data import load_legal_symbol

            search_workspace_dataset_bm25 = load_legal_symbol("search_workspace_dataset_bm25")
            search_workspace_dataset_vector = load_legal_symbol("search_workspace_dataset_vector")
            summarize_workspace_dataset = load_legal_symbol("summarize_workspace_dataset")

            if normalized_backend == "bm25":
                results = search_workspace_dataset_bm25(filtered_payload, query, top_k=int(top_k or 10))
            else:
                results = search_workspace_dataset_vector(
                    filtered_payload,
                    query,
                    top_k=int(top_k or 10),
                    vector_dimension=int(vector_dimension or 32),
                )
            summary = dict(summarize_workspace_dataset(filtered_payload))
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "query": str(query or ""),
            "search_backend": normalized_backend,
            "summary": summary,
            "search_results": dict(results),
            "applied_filters": dict(filtered_payload.get("applied_filters") or {}),
            "source": "complaint_workspace_dataset_search",
        }

    def search_docket_dataset(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
        query: str,
        search_backend: str = "bm25",
        top_k: int = 10,
        vector_dimension: int = 32,
    ) -> Dict[str, Any]:
        from integrations.ipfs_datasets.legal_data import summarize_docket_dataset

        resolved_path = self._resolve_docket_path(input_path)
        normalized_backend = str(search_backend or "bm25").strip().lower()
        normalized_type = str(input_type or "packaged").strip().lower()
        dataset_payload = self._load_docket_dataset_payload(resolved_path, input_type=input_type)
        if normalized_type in {"single", "single_parquet", "parquet"}:
            results = self._search_docket_dataset_local(
                dataset_payload,
                query,
                top_k=int(top_k or 10),
            )
        else:
            from integrations.ipfs_datasets.legal_data import load_legal_symbol

            search_docket_dataset_bm25 = load_legal_symbol("search_docket_dataset_bm25")
            search_docket_dataset_vector = load_legal_symbol("search_docket_dataset_vector")

            if normalized_backend == "bm25":
                results = search_docket_dataset_bm25(dataset_payload, query, top_k=int(top_k or 10))
            elif normalized_backend == "vector":
                results = search_docket_dataset_vector(
                    dataset_payload,
                    query,
                    top_k=int(top_k or 10),
                    vector_dimension=int(vector_dimension or 32),
                )
            else:
                raise ValueError(f"Unsupported docket search backend: {search_backend}")
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "query": str(query or ""),
            "search_backend": normalized_backend,
            "summary": dict(summarize_docket_dataset(dataset_payload)),
            "search_results": dict(results),
            "source": "complaint_workspace_docket_search",
        }

    def get_docket_dataset_metadata(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
    ) -> Dict[str, Any]:
        from integrations.ipfs_datasets.legal_data import summarize_docket_dataset

        resolved_path = self._resolve_docket_path(input_path)
        dataset_payload = self._load_docket_dataset_payload(resolved_path, input_type=input_type)
        summary = dict(summarize_docket_dataset(dataset_payload))
        metadata = dict(dataset_payload.get("metadata") or {})
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "dataset_id": dataset_payload.get("dataset_id"),
            "docket_id": dataset_payload.get("docket_id"),
            "case_name": dataset_payload.get("case_name"),
            "court": dataset_payload.get("court"),
            "summary": summary,
            "metadata": metadata,
            "document_count": len(list(dataset_payload.get("documents") or [])),
            "source": "complaint_workspace_docket_metadata",
        }

    def get_docket_dataset_graph(
        self,
        input_path: str | Path,
        *,
        input_type: str = "packaged",
    ) -> Dict[str, Any]:
        resolved_path = self._resolve_docket_path(input_path)
        dataset_payload = self._load_docket_dataset_payload(resolved_path, input_type=input_type)
        knowledge_graph = dict(dataset_payload.get("knowledge_graph") or {})
        graph_projection = self._issue_links_from_knowledge_graph(knowledge_graph)
        return {
            "input_path": resolved_path,
            "input_type": str(input_type or "packaged").strip().lower(),
            "dataset_id": dataset_payload.get("dataset_id"),
            "docket_id": dataset_payload.get("docket_id"),
            "case_name": dataset_payload.get("case_name"),
            "court": dataset_payload.get("court"),
            "metadata": dict(dataset_payload.get("metadata") or {}),
            "knowledge_graph": graph_projection,
            "source": "complaint_workspace_docket_graph",
        }

    def get_packaged_docket_operator_dashboard(self, manifest_path: str | Path) -> Dict[str, Any]:
        self._require_local_filesystem_access()
        from integrations.ipfs_datasets.legal_data import get_packaged_docket_operator_dashboard

        resolved_manifest = str(Path(str(manifest_path)).expanduser().resolve())
        dashboard = get_packaged_docket_operator_dashboard(resolved_manifest)
        return {
            **dict(dashboard),
            "manifest_path": resolved_manifest,
            "source": "complaint_workspace_packaged_operator_dashboard",
        }

    def load_packaged_docket_operator_dashboard_report(
        self,
        manifest_path: str | Path,
        *,
        report_format: str = "parsed",
    ) -> Dict[str, Any]:
        self._require_local_filesystem_access()
        from integrations.ipfs_datasets.legal_data import load_packaged_docket_operator_dashboard_report

        resolved_manifest = str(Path(str(manifest_path)).expanduser().resolve())
        normalized_format = str(report_format or "parsed").strip().lower()
        report = load_packaged_docket_operator_dashboard_report(
            resolved_manifest,
            report_format=normalized_format,
        )
        return {
            "manifest_path": resolved_manifest,
            "report_format": normalized_format,
            "report": report,
            "source": "complaint_workspace_packaged_operator_dashboard_report",
        }

    def execute_packaged_docket_proof_revalidation_queue(
        self,
        manifest_path: str | Path,
        *,
        top_k: int = 10,
        min_priority: str = "low",
        queue_limit: Optional[int] = None,
        execution_top_k: int = 10,
        chain_until_satisfied: bool = True,
        attach_refreshed_packets: bool = False,
    ) -> Dict[str, Any]:
        self._require_local_filesystem_access()
        from integrations.ipfs_datasets.legal_data import load_legal_symbol

        execute_packaged_docket_proof_revalidation_queue = load_legal_symbol(
            "execute_packaged_docket_proof_revalidation_queue"
        )

        resolved_manifest = str(Path(str(manifest_path)).expanduser().resolve())
        execution = execute_packaged_docket_proof_revalidation_queue(
            resolved_manifest,
            top_k=int(top_k or 10),
            min_priority=str(min_priority or "low"),
            queue_limit=int(queue_limit) if queue_limit is not None else None,
            execution_top_k=int(execution_top_k or 10),
            chain_until_satisfied=bool(chain_until_satisfied),
            attach_refreshed_packets=bool(attach_refreshed_packets),
        )
        return {
            **dict(execution),
            "manifest_path": resolved_manifest,
            "source": "complaint_workspace_packaged_proof_revalidation_queue_execution",
        }

    def persist_packaged_docket_proof_revalidation_queue(
        self,
        manifest_path: str | Path,
        output_dir: str | Path,
        *,
        package_name: Optional[str] = None,
        include_car: bool = True,
        top_k: int = 10,
        min_priority: str = "low",
        queue_limit: Optional[int] = None,
        execution_top_k: int = 10,
        chain_until_satisfied: bool = True,
    ) -> Dict[str, Any]:
        self._require_local_filesystem_access()
        from integrations.ipfs_datasets.legal_data import load_legal_symbol

        persist_packaged_docket_proof_revalidation_queue = load_legal_symbol(
            "persist_packaged_docket_proof_revalidation_queue"
        )

        resolved_manifest = str(Path(str(manifest_path)).expanduser().resolve())
        resolved_output_dir = str(Path(str(output_dir)).expanduser().resolve())
        persisted = persist_packaged_docket_proof_revalidation_queue(
            resolved_manifest,
            resolved_output_dir,
            package_name=str(package_name).strip() if package_name is not None and str(package_name).strip() else None,
            include_car=bool(include_car),
            top_k=int(top_k or 10),
            min_priority=str(min_priority or "low"),
            queue_limit=int(queue_limit) if queue_limit is not None else None,
            execution_top_k=int(execution_top_k or 10),
            chain_until_satisfied=bool(chain_until_satisfied),
        )
        return {
            **dict(persisted),
            "manifest_path": resolved_manifest,
            "output_dir": resolved_output_dir,
            "source": "complaint_workspace_packaged_proof_revalidation_queue_persist",
        }

    def get_privacy_policy(self, user_id: Optional[str] = None, case_id: Optional[str] = None) -> Dict[str, Any]:
        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._load_state(resolved_user_id)
        bound_case = _state_case_id(state, resolved_user_id)
        requested_case = str(case_id or bound_case)
        helpers = _privacy_helpers()
        if requested_case != bound_case:
            inspection = helpers["inspect_privacy_policy"](
                state.get("privacy_policy"),
                user_id=resolved_user_id,
                case_id=requested_case,
            )
            policy = inspection["policy"]
            load = {
                "admitted": False,
                "reason": "privacy_denied:case_binding",
                "cloud_processing_enabled": False,
            }
        else:
            policy = dict(state.get("privacy_policy") or {})
            load = dict(state.get("privacy_policy_load") or {})
        return {
            "user_id": resolved_user_id,
            "case_id": bound_case,
            "requested_case_id": requested_case,
            "policy": policy,
            "load": load,
            "at_rest_protection": "private_envelope",
            "encryption_at_rest_blocks_remote_llm": False,
            "authenticates_tenant": False,
            "authorization_note": "user_id selects a workspace record. Tenant authorization is PRIV002, not this policy.",
        }

    def set_privacy_policy(
        self,
        user_id: Optional[str],
        mode: str,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._load_state(resolved_user_id)
        bound_case = _state_case_id(state, resolved_user_id)
        requested_case = str(case_id or bound_case)
        if requested_case != bound_case:
            payload = self.get_privacy_policy(resolved_user_id, case_id=requested_case)
            payload["updated"] = False
            return payload
        helpers = _privacy_helpers()
        normalized_mode = str(mode or "").strip().lower()
        state["privacy_policy"] = helpers["privacy_policy_for_mode"](resolved_user_id, bound_case, mode)
        if normalized_mode == "local":
            state["public_processing_mode"] = "local"
        elif normalized_mode in {"grok", "grok_cloud"}:
            state["public_processing_mode"] = "grok"
        _sync_operation_consent_state(state, resolved_user_id, bound_case)
        self._save_state(state)
        payload = self.get_privacy_policy(resolved_user_id)
        payload["updated"] = True
        return payload

    def dispatch_private_llm_turn(
        self,
        user_id: Optional[str],
        *,
        relevant_facts: list,
        rule_gaps: list,
        unrelated_evidence: Optional[list] = None,
        sensitive_literals: Optional[list] = None,
        key: bytes,
        key_id: str,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Any = None,
        campaign_settings: Optional[Mapping[str, Any]] = None,
        stored_user_complaint: bool = False,
        turn_id: str = "",
        **options: Any,
    ) -> Dict[str, Any]:
        """Apply the persisted cloud choice, then the minimal-prompt router gate."""

        from integrations.ipfs_datasets.llm import dispatch_private_turn

        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._load_state(resolved_user_id)
        helpers = _privacy_helpers()
        case_id = _state_case_id(state, resolved_user_id)
        privacy_context = helpers["build_complaint_privacy_context"](
            state.get("privacy_policy"),
            user_id=resolved_user_id,
            case_id=case_id,
            data_class="raw_intake",
        )
        result = dispatch_private_turn(
            privacy_context=privacy_context,
            relevant_facts=relevant_facts,
            rule_gaps=rule_gaps,
            unrelated_evidence=unrelated_evidence,
            sensitive_literals=sensitive_literals,
            key=key,
            key_id=key_id,
            provider=provider,
            model_name=model_name,
            timeout=timeout,
            campaign_settings=campaign_settings,
            stored_user_complaint=stored_user_complaint,
            principal_id=resolved_user_id,
            turn_id=turn_id,
            **options,
        )
        result["user_id"] = resolved_user_id
        result["case_id"] = case_id
        return result

    def read_persisted_owner_case_policy(
        self,
        user_id: Optional[str] = None,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Load the saved owner/case policy. This does not open a provider."""

        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._load_state(resolved_user_id)
        bound_case = _state_case_id(state, resolved_user_id)
        requested_case = str(case_id or bound_case)
        matched = requested_case == bound_case
        return {
            "found": True,
            "policy_read": True,
            "user_id": resolved_user_id,
            "case_id": bound_case if matched else requested_case,
            "requested_case_id": requested_case,
            "case_match": matched,
            "privacy_policy": state.get("privacy_policy") if matched else None,
            "operation_consent": state.get("operation_consent") if matched else None,
        }

    def dispatch_consented_hook_query(
        self,
        user_id: Optional[str],
        *,
        purpose: str,
        provider_kind: str,
        data_class: str,
        provider_loader: Optional[Any] = None,
        query_submitter: Optional[Any] = None,
        case_id: Optional[str] = None,
        tools: bool = False,
        citation: Any = None,
        complaint_text: Any = None,
        private_fields: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Read the persisted case policy before a provider loader or hook query."""

        from mediator.hook_runtime import prepare_remote_hook_query

        resolved_user_id = str(user_id or DEFAULT_USER_ID)

        def reader() -> Dict[str, Any]:
            return self.read_persisted_owner_case_policy(resolved_user_id, case_id=case_id)

        return prepare_remote_hook_query(
            policy_reader=reader,
            provider_loader=provider_loader,
            query_submitter=query_submitter,
            owner_id=resolved_user_id,
            case_id=str(case_id or reader()["case_id"]) if case_id is None else str(case_id),
            purpose=purpose,
            provider_kind=provider_kind,
            data_class=data_class,
            tools=tools,
            citation=citation,
            complaint_text=complaint_text,
            private_fields=private_fields,
        )

    def accept_late_consented_hook_result(
        self,
        user_id: Optional[str],
        *,
        invocation_id: str,
        case_id: str,
        result_acceptor: Optional[Any] = None,
        bound_graph_revision: Optional[str] = None,
        current_graph_revision: Optional[str] = None,
        bound_session_revision: Optional[int] = None,
        current_session_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Load the current persisted policy again before accepting a late result.

        A supplied bound revision is compared with the saved graph and session.
        A mismatch is stale and does not call the result acceptor.
        """

        from mediator.hook_runtime import accept_late_hook_result

        resolved_user_id = str(user_id or DEFAULT_USER_ID)

        def reader() -> Dict[str, Any]:
            return self.read_persisted_owner_case_policy(resolved_user_id, case_id=case_id)

        if bound_graph_revision is not None or bound_session_revision is not None:
            anchor = self._adverse_public_anchor(resolved_user_id)
            if current_graph_revision is None:
                current_graph_revision = str(anchor.get("graph_revision") or "")
            if current_session_revision is None:
                current_session_revision = int(anchor.get("session_revision") or 0)
        return accept_late_hook_result(
            policy_reader=reader,
            invocation_id=invocation_id,
            owner_id=resolved_user_id,
            case_id=case_id,
            result_acceptor=result_acceptor,
            bound_graph_revision=bound_graph_revision,
            current_graph_revision=current_graph_revision,
            bound_session_revision=bound_session_revision,
            current_session_revision=current_session_revision,
        )

    def record_gui_inference_authority(self, user_id: Optional[str], **untrusted: Any) -> Dict[str, Any]:
        """Caller JSON is not a browser grant or a source/revision owner."""
        return {"recorded": False, "code": "server_case_authority_required",
                "live_model_identity_verified": False}

    def _gui_inference_snapshot(self, user_id: Optional[str], purpose: str) -> Dict[str, Any]:
        from mediator.hook_runtime import HookContextError, graph_revision_token, source_binding_hash
        from complaint_phases.knowledge_graph import KnowledgeGraph
        authority = self._owner_case_authority()
        if authority is None:
            raise HookContextError("server_case_authority_required")
        actor = authority.actor_principal_id
        decision = authority.revalidate(actor_principal_id=actor, workspace=self, require_owner=True)
        if user_id not in (None, "", actor, decision.canonical_owner_principal_id):
            raise HookContextError("wrong_case")
        view = authority.processing_consent(purpose=purpose, actor_principal_id=actor, workspace=self)
        choices = [item for item in view["decisions"] if item["purpose"] == purpose]
        if len(choices) != 1:
            raise HookContextError("consent_missing")
        choice = choices[0]
        # The legacy raw-intake/global-Grok fallback is never GUI authority.
        authorized = (choice.get("egress_authorized") is True and choice.get("explicit") is True
                      and choice.get("revoked") is False and choice.get("provider") == "grok_cli"
                      and choice.get("model") == "grok-4.7")
        if not authorized:
            raise HookContextError("consent_revoked" if choice.get("revoked") else "case_purpose_consent_required")
        canonical = decision.canonical_owner_principal_id
        state = self._load_state(canonical, case_id=decision.case_id)
        projection = state.get("shared_interview")
        if not isinstance(projection, dict) or not isinstance(projection.get("knowledge_graph"), dict):
            raise HookContextError("source_binding_missing")
        narrative = str(_narrative_record(state).get("text") or "")
        graph = projection["knowledge_graph"]
        if not narrative or not graph.get("entities"):
            raise HookContextError("source_binding_missing")
        revision = projection.get("session_revision")
        session = projection.get("session_id")
        if type(revision) is not int or revision < 0 or not isinstance(session, str) or not session:
            raise HookContextError("stale_request")
        graph_token = graph_revision_token(KnowledgeGraph.from_dict(graph))
        graph_raw = json.dumps(graph, sort_keys=True, separators=(",", ":")).encode()
        sources = [{"source_id": "original_complaint", "content_hash": hashlib.sha256(narrative.encode()).hexdigest()},
                   {"source_id": "factual_graph", "content_hash": hashlib.sha256(graph_raw).hexdigest()}]
        pending = projection.get("pending_inquiry") or {}
        dependencies = projection.get("dependency_graph") or {}
        targets = set(graph.get("entities", {})) | set(dependencies.get("nodes", {}))
        targets.update(str(pending[k]) for k in ("target_id", "objective_id") if pending.get(k))
        gap_codes = {str(item.get("code") or item.get("type") or "") if isinstance(item, dict) else str(item)
                     for item in projection.get("unknown_reasons", [])}
        gap_codes.update(str(pending[k]) for k in ("type", "grounding_status") if pending.get(k))
        key_id = self._interview_snapshot_key(canonical, decision.case_id)["key_id"]
        grant_fields = {"actor": actor, "tenant": decision.tenant_id, "case": decision.case_id,
                        "resource": decision.resource_id, "revision": decision.revision,
                        "membership_revision": decision.membership_revision, "key_id": key_id,
                        "browser_session": authority.inference_session_binding(actor_principal_id=actor, workspace=self)}
        grant_id = hashlib.sha256(json.dumps(grant_fields, sort_keys=True).encode()).hexdigest()
        source_revision = source_binding_hash(sources)
        consent = dict(view["operation_consent"])
        consent["grants"] = [g for g in consent["grants"] if g.get("purpose") == purpose]
        consent["revoked"] = False
        policy = {"found": True, "case_match": True, "user_id": actor, "case_id": decision.case_id,
                  "privacy_policy": _privacy_helpers()["privacy_policy_for_mode"](actor, decision.case_id, "grok"),
                  "operation_consent": consent}
        case_file = projection.get("intake_case_file") or {}
        legal = case_file.get("legal_context") if isinstance(case_file.get("legal_context"), dict) else {}
        return {"authority": authority, "actor": actor, "case_id": decision.case_id,
                "policy": policy, "grant": {"grant_id": grant_id, "case_id": decision.case_id,
                    "generation": max(1, decision.membership_revision), "revoked": False,
                    "source_revision": source_revision}, "source_bindings": sources,
                "graph_revision": graph_token, "session_revision": revision, "session_id": session,
                "legal_context": legal, "narrative": narrative, "targets": targets, "gap_codes": gap_codes}

    @staticmethod
    def _gui_inference_refusal(code: str) -> Dict[str, Any]:
        return {"status": "refused", "code": code, "accepted": False, "output": None,
                "model_dispatched": False, "live_model_identity_verified": False,
                "requirements_satisfied": False, "completion_authority": False}

    def dispatch_bounded_gui_inference(self, user_id: Optional[str], *, purpose: str,
            inputs: Mapping[str, Any], timeout_seconds: float = 30.0, **caller_context: Any) -> Dict[str, Any]:
        """Dispatch through fresh issued owner authority and exact persisted purpose.

        Source, graph/session, actor, grant, narrative and clock come from their
        server owners. Request bodies cannot supply replacement authority.
        """
        from datetime import timedelta
        import time
        from mediator.hook_runtime import (HookContextError, dispatch_gui_bounded_inference,
            discard_gui_inference_hold, MODEL_PURPOSE_IDS, native_gui_inference_transport)
        from .workspace_case_authority import WorkspaceCaseAuthorityError
        from .case_consent_api import CaseConsentError
        if caller_context:
            return self._gui_inference_refusal("caller_authority_not_accepted")
        if type(purpose) is not str or purpose not in MODEL_PURPOSE_IDS:
            return self._gui_inference_refusal("undeclared_purpose")
        if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 60:
            return self._gui_inference_refusal("invalid_deadline")
        started_monotonic = time.monotonic()
        now = datetime.now(timezone.utc)
        try:
            snapshot = self._gui_inference_snapshot(user_id, purpose)
            if not isinstance(inputs, Mapping):
                raise HookContextError("input_bounds")
            target = inputs.get("target_ref", inputs.get("candidate_ref"))
            if type(target) is not str or target not in snapshot["targets"]:
                raise HookContextError("source_binding_mismatch")
            if purpose == "extract_facts":
                fragment = inputs.get("source_text")
                if type(fragment) is not str or not fragment or fragment not in snapshot["narrative"]:
                    raise HookContextError("source_binding_mismatch")
                if fragment == snapshot["narrative"]:
                    raise HookContextError("query_not_minimized")
            elif type(inputs.get("gap_code")) is not str or inputs["gap_code"] not in snapshot["gap_codes"]:
                raise HookContextError("source_binding_mismatch")
            authority = snapshot["authority"]
            transport = authority.inference_transport(actor_principal_id=snapshot["actor"], workspace=self)
            if transport is None:
                return self._gui_inference_refusal("model_transport_unavailable")
            holds = getattr(self, "_gui_server_holds", {})
            for invocation, held in list(holds.items()):
                if now.timestamp() > held["deadline"]:
                    holds.pop(invocation, None)
                    discard_gui_inference_hold(invocation)
            self._gui_server_holds = holds
            if len(holds) >= 64:
                return self._gui_inference_refusal("inference_capacity_reached")
            boundary_code = None
            def current_revision():
                fresh = self._gui_inference_snapshot(user_id, purpose)
                for name in ("policy", "grant", "source_bindings", "graph_revision", "session_revision", "session_id"):
                    if fresh[name] != snapshot[name]:
                        raise HookContextError("stale_request")
                return {"record": fresh["policy"], "grant": fresh["grant"],
                        "graph_revision": fresh["graph_revision"], "session_revision": fresh["session_revision"]}
            def observed_transport(call):
                nonlocal boundary_code
                try:
                    current_revision()
                    remaining = timeout_seconds - (time.monotonic() - started_monotonic)
                    if remaining <= 0:
                        boundary_code = "deadline_expired"
                        return {"status": "unavailable"}
                    bounded_call = {**call, "timeout_seconds": remaining,
                        "deadline": (now + timedelta(seconds=timeout_seconds)).isoformat()}
                    return transport(bounded_call)
                except (HookContextError, WorkspaceCaseAuthorityError, CaseConsentError, WorkspaceAuthorizationDenied) as exc:
                    boundary_code = getattr(exc, "code", "authorization_denied")
                    return {"status": "unavailable"}
            remaining = timeout_seconds - (time.monotonic() - started_monotonic)
            if remaining <= 0:
                return {**self._gui_inference_refusal("deadline_expired"), "status": "timeout"}
            result = dispatch_gui_bounded_inference(policy_record=snapshot["policy"], grant=snapshot["grant"],
                purpose_id=purpose, inputs=inputs, source_bindings=snapshot["source_bindings"],
                legal_context=snapshot["legal_context"], owner_id=snapshot["actor"], case_id=snapshot["case_id"],
                session_id=snapshot["session_id"], session_revision=snapshot["session_revision"],
                graph_revision=snapshot["graph_revision"], deadline=now + timedelta(seconds=timeout_seconds), now=now,
                privacy_context=_privacy_helpers()["build_complaint_privacy_context"](snapshot["policy"]["privacy_policy"],
                    user_id=snapshot["actor"], case_id=snapshot["case_id"], data_class="raw_intake"),
                model_transport=(native_gui_inference_transport if transport is native_gui_inference_transport else observed_transport),
                complaint_text=snapshot["narrative"], revision_reader=current_revision,
                timeout=remaining)
            if boundary_code:
                return {**self._gui_inference_refusal(boundary_code),
                        "status": "timeout" if boundary_code == "deadline_expired" else "refused"}
            if time.monotonic() - started_monotonic > timeout_seconds:
                discard_gui_inference_hold(str(result.get("invocation_id") or ""))
                return {**self._gui_inference_refusal("deadline_expired"), "status": "timeout",
                        "model_dispatched": result.get("model_dispatched") is True}
            if result.get("status") == "held":
                holds = getattr(self, "_gui_server_holds", {})
                holds[result["invocation_id"]] = {"actor": snapshot["actor"], "case_id": snapshot["case_id"],
                    "purpose": purpose, "deadline": now.timestamp() + timeout_seconds}
                self._gui_server_holds = holds
            from integrations.ipfs_accelerate.routers import development_campaign_authorizes_user_complaint_egress

            result["actor_principal_id"] = snapshot["actor"]
            # A development-agent model grant is checked and then discarded.
            # It is never written into the case consent record.
            agent_permission = {
                "provider": "grok_cli",
                "model": "grok-4.7",
                "allow_local_fallback": False,
                "allow_cross_provider_fallback": False,
                "development_agent": True,
            }
            result["development_agent_grok_permission_is_complaint_consent"] = (
                development_campaign_authorizes_user_complaint_egress(agent_permission)
            )
            result["development_grok_authorization_ignored"] = (
                result["development_agent_grok_permission_is_complaint_consent"] is False
            )
            return result
        except (HookContextError, WorkspaceCaseAuthorityError, CaseConsentError, WorkspaceAuthorizationDenied,
                WorkspacePersistenceError) as exc:
            return self._gui_inference_refusal(getattr(exc, "code", "authorization_denied"))

    def admit_bounded_gui_inference(self, user_id: Optional[str], *, invocation_id: str) -> Dict[str, Any]:
        """Release only after fresh browser, case, purpose, key and source reproof."""
        from mediator.hook_runtime import HookContextError, admit_gui_bounded_inference, discard_gui_inference_hold
        from .workspace_case_authority import WorkspaceCaseAuthorityError
        from .case_consent_api import CaseConsentError
        holds = getattr(self, "_gui_server_holds", {})
        if type(invocation_id) is not str:
            return self._gui_inference_refusal("invocation_missing")
        held = holds.get(invocation_id)
        if held is None:
            return self._gui_inference_refusal("invocation_missing")
        try:
            snapshot = self._gui_inference_snapshot(user_id, held["purpose"])
            if (snapshot["actor"] != held["actor"] or snapshot["case_id"] != held["case_id"]):
                raise HookContextError("wrong_case")
            if datetime.now(timezone.utc).timestamp() > held["deadline"]:
                raise HookContextError("deadline_expired")
            result = admit_gui_bounded_inference(invocation_id=invocation_id, policy_record=snapshot["policy"],
                grant=snapshot["grant"], source_bindings=snapshot["source_bindings"], owner_id=snapshot["actor"],
                case_id=snapshot["case_id"], graph_revision=snapshot["graph_revision"],
                session_revision=snapshot["session_revision"])
            return result
        except (HookContextError, WorkspaceCaseAuthorityError, CaseConsentError, WorkspaceAuthorizationDenied,
                WorkspacePersistenceError) as exc:
            return self._gui_inference_refusal(getattr(exc, "code", "authorization_denied"))
        finally:
            holds.pop(invocation_id, None)
            discard_gui_inference_hold(invocation_id)

    def _adverse_public_anchor(self, user_id: str) -> Dict[str, Any]:
        """Graph token, pending inquiry, and snapshot head. Reads do not dispatch."""

        state = self._load_state(user_id)
        projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
        pending = projection.get("pending_inquiry") if isinstance(projection.get("pending_inquiry"), dict) else {}
        graph = projection.get("knowledge_graph") if isinstance(projection.get("knowledge_graph"), dict) else {}
        token = ""
        if graph:
            try:
                from complaint_phases.knowledge_graph import KnowledgeGraph
                from mediator.hook_runtime import graph_revision_token

                token = graph_revision_token(KnowledgeGraph.from_dict(graph))
            except Exception:
                token = ""
        head_revision = None
        head_code = "no_committed_head"
        try:
            loaded = self.load_complete_interview_snapshot(user_id)
            snapshot = loaded.get("snapshot") if isinstance(loaded.get("snapshot"), dict) else {}
            head_revision = snapshot.get("revision")
            head_code = "available" if head_revision else "no_committed_head"
        except WorkspacePersistenceError as exc:
            head_code = str(exc.code or "unavailable")
        return {
            "graph_revision": token,
            "session_revision": int(projection.get("session_revision") or 0),
            "pending_inquiry": {
                "inquiry_id": pending.get("inquiry_id"),
                "revision": pending.get("revision"),
                "question": pending.get("question"),
                "objective_id": pending.get("objective_id"),
                "target_id": pending.get("target_id"),
            },
            "head_revision": head_revision,
            "head_code": head_code,
        }

    def authenticate_interview_snapshot_key(
        self,
        user_id: str,
        *,
        key: bytes,
        key_id: str,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Try one caller key against the committed snapshot. A miss does not replace the head."""

        from integrations.ipfs_datasets.storage import InterviewSnapshotError, load_interview_snapshot

        context = self._interview_snapshot_key(user_id, case_id)
        directory = self.interview_snapshot_directory(str(context["tenant_id"]), str(context["case_id"]))
        try:
            load_interview_snapshot(
                directory,
                protection="user_chosen_encrypted",
                tenant_id=str(context["tenant_id"]),
                case_id=str(context["case_id"]),
                principal_id=str(context["principal_id"]),
                key=key,
                key_id=key_id,
            )
        except InterviewSnapshotError as exc:
            return {
                "authenticated": False,
                "code": str(exc.code or "authentication_failed"),
                "public_status": str(exc.public_status or "recoverable"),
                "head_replaced": False,
                "legal_completion": False,
            }
        return {"authenticated": True, "code": "authenticated", "head_replaced": False, "legal_completion": False}

    def run_public_adverse_outcome(
        self,
        user_id: Optional[str],
        kind: str,
        *,
        deadline_seconds: float = 30.0,
        repository: Optional[Path] = None,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exercise one adverse hook or storage outcome through public operations.

        The last committed graph token, pending inquiry, and snapshot head stay
        in place. Legal completion is never synthesized. Owned children are
        reaped; provider processes and the network are not started.
        """

        from mediator.hook_runtime import (
            PUBLIC_ADVERSE_OUTCOMES,
            OwnedProcessGuard,
            reject_public_model_proposal,
        )

        resolved = str(user_id or DEFAULT_USER_ID)
        guard = OwnedProcessGuard(deadline_seconds)
        before = self._adverse_public_anchor(resolved)
        outcome: Dict[str, Any] = {
            "kind": kind,
            "code": "unsupported_adverse_case",
            "status": "unavailable",
            "legal_completion": False,
            "proof": False,
            "legal_sufficiency": False,
            "requirements_satisfied": False,
            "backend_completed": False,
            "provider_invoked": False,
            "provider_process_started": False,
            "network_touched": False,
            "resume_possible": False,
            "nonrecoverable_boundary": "unsupported_adverse_case",
            "next_action": "report_unsupported_outcome",
        }
        try:
            guard.spawn_owned_idle_child()
            if guard.expired():
                outcome.update(code="deadline_elapsed", status="timeout", resume_possible=True,
                               nonrecoverable_boundary=None, next_action="retry_within_deadline")
            elif kind not in PUBLIC_ADVERSE_OUTCOMES:
                outcome["capability"] = "unavailable"
            elif kind == "malformed_model_proposal":
                rejected = reject_public_model_proposal({"requirements_satisfied": True, "tools": ["shell"]})
                outcome.update(rejected)
                outcome["status"] = "refused"
            elif kind in {"late_model_proposal", "consent_revocation"}:
                outcome.update(self._adverse_model_timing(resolved, kind, case_id=case_id))
            elif kind == "wrong_key":
                probed = self.authenticate_interview_snapshot_key(
                    resolved, key=os.urandom(32), key_id="wrong-key", case_id=case_id,
                )
                boundary = None if probed.get("code") == "authentication_failed" and before.get("head_revision") else "no_committed_head"
                outcome.update({
                    "code": probed.get("code") or "authentication_failed",
                    "status": "refused",
                    "resume_possible": before.get("head_revision") is not None,
                    "nonrecoverable_boundary": "wrong_key_cannot_open_head" if probed.get("code") == "authentication_failed" else boundary,
                    "next_action": "retry_with_case_key" if before.get("head_revision") else "commit_snapshot",
                    "head_replaced": False,
                })
            elif kind == "legal_source_outage":
                receipt = self.run_legal_research(
                    resolved,
                    storage_available=False,
                    retrieval_mode="cache",
                    dependency_change={"source_outage": True},
                )
                outcome.update({
                    "code": str(receipt.get("error_code") or "storage_unavailable"),
                    "status": str(receipt.get("status") or "unavailable"),
                    "proof": False,
                    "legal_sufficiency": False,
                    "requirements_satisfied": False,
                    "backend_completed": False,
                    "legal_completion": False,
                    "provider_invoked": False,
                    "resume_possible": True,
                    "nonrecoverable_boundary": None,
                    "next_action": str(receipt.get("next_action") or "retry_unavailable"),
                    "stored_as_answer": False,
                })
            elif kind == "interrupted_snapshot":
                try:
                    self.commit_complete_grounded_snapshot(
                    resolved,
                    case_id=case_id,
                    fail_before_head=True,
                    expected_revision=None if before.get("head_revision") is None else str(before.get("head_revision")),
                )
                    outcome.update(code="durability_unproven", status="unavailable")
                except WorkspacePersistenceError as exc:
                    outcome.update(code=str(exc.code or "durability_unproven"), status=str(exc.public_status or "recoverable"))
                outcome.update({
                    "resume_possible": True,
                    "nonrecoverable_boundary": None,
                    "next_action": "retry_snapshot_commit",
                    "head_replaced": False,
                    "legal_completion": False,
                })
            elif kind == "corrupt_replica":
                outcome.update(self._adverse_corrupt_replica(resolved, repository, case_id=case_id))
        except WorkspacePersistenceError as exc:
            outcome.update({
                "code": str(exc.code or "unavailable"),
                "status": str(exc.public_status or "unavailable"),
                "resume_possible": exc.public_status != "nonrecoverable",
                "nonrecoverable_boundary": None if exc.public_status != "nonrecoverable" else str(exc.code),
                "next_action": "retry_unavailable",
            })
        finally:
            children = guard.cleanup()
        after = self._adverse_public_anchor(resolved)
        preserved = {
            "graph_revision": before.get("graph_revision") == after.get("graph_revision"),
            "pending_inquiry": before.get("pending_inquiry") == after.get("pending_inquiry"),
            "head_revision": before.get("head_revision") == after.get("head_revision"),
            "session_revision": before.get("session_revision") == after.get("session_revision"),
        }
        outcome["before"] = before
        outcome["after"] = after
        outcome["preserved"] = preserved
        outcome["owned_children"] = children
        outcome["legal_completion"] = False
        outcome["proof"] = False
        outcome["legal_sufficiency"] = False
        outcome["requirements_satisfied"] = False
        outcome["backend_completed"] = False
        outcome["provider_process_started"] = False
        outcome["network_touched"] = False
        if children.get("status") == "unavailable" and not children.get("pids"):
            outcome["owned_child_capability"] = "unavailable"
        else:
            outcome["owned_child_capability"] = "reaped"
        return outcome

    def _adverse_model_timing(self, user_id: str, kind: str, *, case_id: Optional[str]) -> Dict[str, Any]:
        """Authorize a synthetic in-process loader, then refuse the late or revoked result."""

        policy = self.get_privacy_policy(user_id)
        bound_case = str(case_id or policy.get("case_id") or user_id)
        self.set_privacy_policy(user_id, "grok", case_id=bound_case)
        submitted: list[Any] = []

        def loader() -> Dict[str, Any]:
            return {"status": "available", "synthetic": True, "live_model_identity_verified": False}

        def submit(query: Mapping[str, Any]) -> None:
            submitted.append(dict(query))

        prepared = self.dispatch_consented_hook_query(
            user_id,
            purpose="extract_facts",
            provider_kind="grok_inference",
            data_class="raw_intake",
            provider_loader=loader,
            query_submitter=submit,
            case_id=bound_case,
            private_fields={"source_text": "synthetic gap", "target_ref": "target.adverse"},
        )
        invocation_id = str(prepared.get("invocation_id") or "")
        accepted: list[str] = []
        if kind == "consent_revocation":
            self.set_privacy_policy(user_id, "local", case_id=bound_case)
            late = self.accept_late_consented_hook_result(
                user_id,
                invocation_id=invocation_id,
                case_id=bound_case,
                result_acceptor=lambda: accepted.append("accepted"),
            )
            code = str(late.get("code") or "consent_revoked")
        else:
            late = self.accept_late_consented_hook_result(
                user_id,
                invocation_id=invocation_id,
                case_id=bound_case,
                result_acceptor=lambda: accepted.append("accepted"),
                bound_graph_revision="bound-revision-not-current",
                bound_session_revision=0,
            )
            code = str(late.get("code") or "stale_revision")
        return {
            "code": code,
            "status": "refused",
            "accepted": False,
            "acceptor_called": bool(accepted),
            "policy_read": bool(late.get("policy_read")),
            "live_model_identity_verified": False,
            "synthetic_transport": True,
            "query_count": len(submitted),
            "resume_possible": True,
            "nonrecoverable_boundary": None,
            "next_action": "continue_pending_inquiry",
            "legal_completion": False,
            "proof": False,
            "provider_invoked": False,
            "provider_process_started": False,
        }

    def _adverse_corrupt_replica(self, user_id: str, repository: Optional[Path], *, case_id: Optional[str]) -> Dict[str, Any]:
        """Publish one fixture replica that returns corrupt bytes and refuse to restore it."""

        from integrations.ipfs_datasets.storage import replica_policy
        from integrations.private_storage import PrivateStorageError

        if repository is None:
            return {
                "code": "replica_repository_required",
                "status": "unavailable",
                "capability": "unavailable",
                "resume_possible": True,
                "nonrecoverable_boundary": None,
                "next_action": "supply_private_repository",
                "legal_completion": False,
            }

        class _CorruptFixture:
            provider_class = "fixture"
            fixture_provider = True

            def __init__(self) -> None:
                self.frame = b""
                self.version = ""

            def place(self, *, digest: str, version: str, frame: bytes, timeout_seconds: float | None = None) -> Dict[str, Any]:
                del digest, timeout_seconds
                self.frame = b"\xff" + bytes(frame)
                self.version = version
                return {"status": "stored", "cid": "bafyfixturecorrupt"}

            def readback(self, *, digest: str, version: str, timeout_seconds: float | None = None) -> Dict[str, Any]:
                del digest, version, timeout_seconds
                return {"status": "available", "frame": self.frame, "version": self.version, "cid": "bafyfixturecorrupt"}

        corrupt = _CorruptFixture()
        policy = replica_policy(desired_replicas=1, minimum_replicas=1, mode="private_remote")
        state = self._load_state(user_id)
        narrative = _narrative_record(state)
        text = str(narrative.get("text") or "synthetic").encode("utf-8")
        try:
            published = self.publish_encrypted_replicas(
                user_id,
                repository,
                case_id=case_id,
                policy=policy,
                revision="adverse-r1",
                complaint=text,
                fact_graph=b"graph:last-valid",
                proof=b"proof:not-legal-completion",
                providers={"fixture-corrupt": corrupt},
                timeout_seconds=1,
            )
        except (PrivateStorageError, ValueError, WorkspacePersistenceError) as exc:
            code = getattr(exc, "code", None) or "replica_unavailable"
            return {
                "code": str(code),
                "status": "unavailable",
                "resume_possible": True,
                "nonrecoverable_boundary": None,
                "next_action": "retry_unavailable",
                "legal_completion": False,
                "published": False,
            }
        ledger = Path(repository) / "replica-ledger" / "primary.frame"
        primary_existed = ledger.is_file()
        primary_bytes = ledger.read_bytes() if primary_existed else b""
        if primary_existed:
            ledger.unlink()
        restored = None
        error_code = "replica_unavailable"
        try:
            restored = self.restore_encrypted_workspace(
                user_id,
                repository,
                case_id=case_id,
                providers={"fixture-corrupt": corrupt},
                timeout_seconds=1,
            )
            error_code = "replica_restored"
        except PrivateStorageError as exc:
            error_code = str(exc.code or "replica_unavailable")
        primary_after = ledger.read_bytes() if ledger.is_file() else b""
        corrupt_used = restored is not None and restored.get("source") == "replica"
        if corrupt_used or (primary_after and primary_after != primary_bytes):
            return {
                "code": "corrupt_replica_applied",
                "status": "unavailable",
                "published": bool(published),
                "corrupt_replica_used": True,
                "resume_possible": False,
                "nonrecoverable_boundary": "corrupt_replica_applied",
                "next_action": "do_not_treat_replica_as_legal_completion",
                "legal_completion": False,
                "proof": False,
                "network_durable": False,
            }
        if primary_existed and not ledger.is_file():
            ledger.write_bytes(primary_bytes)
        return {
            "code": error_code,
            "status": "unavailable",
            "published": bool(published),
            "corrupt_replica_used": False,
            "primary_preserved": (not primary_existed) or ledger.read_bytes() == primary_bytes,
            "resume_possible": True,
            "nonrecoverable_boundary": "corrupt_replica_not_a_restore_source",
            "next_action": "resume_from_local_snapshot_head",
            "legal_completion": False,
            "proof": False,
            "network_durable": False,
        }

    def inventory_private_data_classes(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Describe private case classes without reading other sessions, evidence, exports, or secrets."""

        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._load_state(resolved_user_id)
        helpers = _privacy_helpers()
        canonical = helpers["complaint_data_class_inventory"]()
        logical_locations = {
            "raw_intake": ["session.intake_answers", "session.intake_history"],
            "attachments": ["session.evidence.documents.attachment_names", "workspace.attachments"],
            "fact_kg": ["session.annotation_knowledge_graph"],
            "claim_dependency_evaluations": ["session.review.support_matrix", "session.proof_history"],
            "annotations": ["session.document_annotations", "session.workspace_annotation_index"],
            "drafts_proofs": ["session.draft", "session.proof_history", "session.latest_packet_export"],
            "embeddings": ["workspace.cache.embeddings"],
            "exports": ["workspace.exports"],
            "logs": ["workspace.logs"],
            "caches": ["workspace.cache"],
            "temporary_files": ["workspace.tmp"],
            "backups": ["workspace.backups"],
        }
        private_rows = []
        for item in list(canonical.get("private_claim_fact_graph") or []):
            class_id = str(item.get("id") or "")
            private_rows.append(
                {
                    **item,
                    "logical_locations": list(logical_locations.get(class_id) or []),
                    "graph": "private_claim_fact_graph",
                }
            )
        return {
            "user_id": resolved_user_id,
            "case_id": _state_case_id(state, resolved_user_id),
            "reads_existing_private_paths": False,
            "at_rest_protection": "private_envelope",
            "encryption_at_rest_blocks_remote_llm": False,
            "authenticates_tenant": False,
            "private_claim_fact_graph": private_rows,
            "public_legal_source_graph": dict(canonical.get("public_legal_source_graph") or {}),
            "agent_context": dict(canonical.get("agent_context") or {}),
            "present_state_keys": {
                "raw_intake": bool(state.get("intake_answers") or state.get("intake_history")),
                "attachments": any(
                    list(item.get("attachment_names") or [])
                    for item in list((state.get("evidence") or {}).get("documents") or [])
                    if isinstance(item, dict)
                ),
                "fact_kg": bool((state.get("annotation_knowledge_graph") or {}).get("entities")),
                "annotations": bool(state.get("document_annotations")),
                "drafts_proofs": bool(state.get("draft") or state.get("proof_history")),
            },
        }

    def metadata_residual_exposure(self) -> Dict[str, Any]:
        """Plain statement of size, timing, and access-pattern residuals."""

        from integrations.ipfs_datasets.storage import PADDING_POLICY, RESIDUAL_METADATA_EXPOSURE

        return {
            "residual_exposure": RESIDUAL_METADATA_EXPOSURE,
            "padding_policy": dict(PADDING_POLICY),
            "embeddings_classification": "private_derived",
        }

    def publish_case_public_reference(
        self,
        record: Mapping[str, Any],
        *,
        sensitive_literals: Optional[list] = None,
        document_filename: str = "",
    ) -> Dict[str, Any]:
        """Publish an opaque index row and filename. Private literals stay off both."""

        from integrations.ipfs_datasets.storage import (
            opaque_storage_filename,
            publish_public_index_entry,
        )

        literals = [str(item) for item in (sensitive_literals or []) if str(item or "")]
        if document_filename:
            literals.append(str(document_filename))
        filename = opaque_storage_filename(
            str(record.get("kind") or "object"),
            document_filename or str(record.get("cid") or "object"),
        )
        projected = publish_public_index_entry(
            {
                "cid": record.get("cid"),
                "cid_kind": record.get("cid_kind") or "opaque",
                "artifact_class": record.get("artifact_class") or "opaque_private_ref",
                "classification": record.get("classification") or "opaque",
                "status": record.get("status") or "stored",
                "opaque_name": filename,
                "user_name": record.get("user_name"),
                "case_name": record.get("case_name"),
                "complaint_text": record.get("complaint_text"),
                "filename": document_filename,
                "node_label": record.get("node_label"),
                "query": record.get("query"),
            },
            sensitive_literals=literals,
        )
        return {"filename": filename, "public_metadata": projected}

    def remember_case_alias(self, user_id: str, case_id: str, alias: str, canonical: str, *, key: bytes, key_id: str) -> Dict[str, Any]:
        from integrations.ipfs_datasets.llm import remember_case_alias

        self._check_access(str(user_id), ability="read", case_id=str(case_id))
        return remember_case_alias(
            user_id=str(user_id),
            case_id=str(case_id),
            alias=alias,
            canonical=canonical,
            key=key,
            key_id=key_id,
            principal_id=str(user_id),
        )

    def resolve_case_alias(self, user_id: str, case_id: str, alias: str, *, key: bytes, key_id: str) -> Dict[str, Any]:
        from integrations.ipfs_datasets.llm import resolve_case_alias

        self._check_access(str(user_id), ability="read", case_id=str(case_id))
        return resolve_case_alias(
            user_id=str(user_id),
            case_id=str(case_id),
            alias=alias,
            key=key,
            key_id=key_id,
            principal_id=str(user_id),
        )

    def store_case_embedding(
        self,
        user_id: str,
        case_id: str,
        vector: list,
        source_text: str,
        *,
        key: bytes,
        key_id: str,
        sensitive_literals: Optional[list] = None,
    ) -> Dict[str, Any]:
        from integrations.ipfs_datasets.llm import store_private_embedding

        self._check_access(str(user_id), ability="read", case_id=str(case_id))
        return store_private_embedding(
            user_id=str(user_id),
            case_id=str(case_id),
            vector=vector,
            source_text=source_text,
            key=key,
            key_id=key_id,
            principal_id=str(user_id),
            sensitive_literals=sensitive_literals,
        )

    def default_workspace_log(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        """Default workspace log line. Payloads and case text are not included."""

        from integrations.ipfs_datasets.storage import emit_default_storage_log

        return emit_default_storage_log(record)

    def _private_key_directory(self) -> Path:
        return self._session_dir / "private-keys"

    def _private_key_session(self):
        from integrations.private_storage import UserOwnedKeySession

        session = getattr(self, "_user_owned_keys", None)
        directory = self._private_key_directory()
        if session is None or Path(session.directory) != directory:
            session = UserOwnedKeySession(directory)
            self._user_owned_keys = session
        return session

    def _require_private_case_key_access(
        self, tenant_id: str, case_id: str, *, principal_id: Optional[str] = None
    ) -> None:
        """Admit one exact owner/case before any key-store lookup.

        The shared master store has an operator-only lifecycle. Once unlocked,
        authenticated users may use their bound case through this narrower seam.
        """

        if (not isinstance(tenant_id, str) or not tenant_id
                or not isinstance(case_id, str) or not case_id
                or (principal_id is not None and principal_id != tenant_id)):
            raise WorkspaceAuthorizationDenied()
        access = self._effective_access()
        authority = self._owner_case_authority()
        if authority is not None:
            if tenant_id != authority.canonical_owner_principal_id or case_id != authority.case_id:
                raise WorkspaceAuthorizationDenied()
            if _REQUEST_CASE.get() is not None and _REQUEST_CASE.get() != case_id:
                raise WorkspaceAuthorizationDenied()
            self._check_access(tenant_id, ability="private_key", case_id=case_id)
            return
        operator = access.trust == "trusted_local" and not access.principal_id and not access.case_id
        if not operator:
            if (access.trust not in {"authenticated", "trusted_local"}
                    or access.principal_id != tenant_id or access.case_id != case_id):
                raise WorkspaceAuthorizationDenied()
        explicit_case = _REQUEST_CASE.get()
        if explicit_case is not None and explicit_case != case_id:
            raise WorkspaceAuthorizationDenied()
        self._check_access(tenant_id, ability="private_key", case_id=case_id)

    def private_key_status(self) -> Dict[str, Any]:
        """Local operator view of the shared store, without case plaintext."""

        self._require_local_filesystem_access()

        from integrations.private_storage import task_key_receipt

        return task_key_receipt(self._private_key_session().public_state())

    def initialize_private_keys(
        self,
        *,
        protection: str,
        passphrase: Optional[str] = None,
        keyring: Any = None,
    ) -> Dict[str, Any]:
        """Local operator creates the shared store; cloud consent is unchanged."""

        self._require_local_filesystem_access()

        from integrations.private_storage import PrivateKeyLockedError, task_key_receipt

        session = self._private_key_session()
        try:
            state = session.create(protection=protection, passphrase=passphrase, keyring=keyring)
        except PrivateKeyLockedError as exc:
            return task_key_receipt(exc.public_state())
        self._user_owned_keys = session
        return task_key_receipt(state)

    def unlock_private_keys(
        self,
        *,
        passphrase: Optional[str] = None,
        keyring: Any = None,
    ) -> Dict[str, Any]:
        """Local operator unlocks the shared store; remote consent is unchanged."""

        self._require_local_filesystem_access()

        from integrations.private_storage import (
            PrivateArtifactIntegrityError,
            PrivateKeyLockedError,
            task_key_receipt,
        )

        session = self._private_key_session()
        try:
            if passphrase is not None:
                state = session.unlock_passphrase(passphrase)
            else:
                state = session.unlock_keyring(keyring)
        except PrivateKeyLockedError as exc:
            return task_key_receipt(exc.public_state())
        except PrivateArtifactIntegrityError:
            state = session.public_state()
            state["code"] = "authentication_failed"
            state["message"] = "The wrapped key did not authenticate. Encrypted state was not overwritten."
            state["awaiting_user"] = True
            state["status"] = "unlock_needed"
            return task_key_receipt(state)
        self._user_owned_keys = session
        return task_key_receipt(state)

    def lock_private_keys(self) -> Dict[str, Any]:
        """Local operator locks the shared store for all case handles."""

        self._require_local_filesystem_access()
        from integrations.private_storage import task_key_receipt

        return task_key_receipt(self._private_key_session().lock())

    def export_private_key_recovery(
        self,
        *,
        tenant_id: str,
        case_id: str,
        recovery_passphrase: str,
        destination: str,
    ) -> Dict[str, Any]:
        """Local operator performs an explicit recovery export to a host path."""

        self._require_local_filesystem_access()

        from integrations.private_storage import PrivateKeyLockedError, task_key_receipt

        session = self._private_key_session()
        try:
            exported = session.export_recovery(tenant_id, case_id, recovery_passphrase, destination)
        except PrivateKeyLockedError as exc:
            return task_key_receipt(exc.public_state())
        state = session.public_state()
        state["deliberate_export"] = True
        state["automatic_backup"] = False
        state["message"] = "Deliberate recovery export written. This is not an automatic case backup."
        state["case_count"] = session.public_state()["case_count"]
        if not exported.get("deliberate_export"):
            raise PrivateKeyLockedError(
                "Recovery export was not marked deliberate.",
                actions=("recovery_export",),
            )
        return task_key_receipt(state)

    def import_private_key_recovery(
        self,
        *,
        tenant_id: str,
        case_id: str,
        recovery_passphrase: str,
        payload: bytes,
        store_passphrase: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Local operator imports recovery material into the shared store."""

        self._require_local_filesystem_access()
        from integrations.private_storage import (
            PrivateArtifactBindingError,
            PrivateArtifactIntegrityError,
            PrivateKeyLockedError,
            task_key_receipt,
        )

        session = self._private_key_session()
        try:
            state = session.import_recovery(
                payload,
                tenant_id=tenant_id,
                case_id=case_id,
                recovery_passphrase=recovery_passphrase,
                store_passphrase=store_passphrase,
            )
        except PrivateKeyLockedError as exc:
            return task_key_receipt(exc.public_state())
        except PrivateArtifactBindingError:
            state = session.public_state()
            state["code"] = "foreign_case"
            state["message"] = "Recovery material belongs to another case and was not imported."
            state["status"] = "unlock_needed"
            state["awaiting_user"] = True
            return task_key_receipt(state)
        except PrivateArtifactIntegrityError:
            state = session.public_state()
            state["code"] = "authentication_failed"
            state["message"] = "Recovery material did not authenticate and was not imported."
            state["status"] = "unlock_needed"
            state["awaiting_user"] = True
            return task_key_receipt(state)
        self._user_owned_keys = session
        return task_key_receipt(state)

    def prepare_private_terminal_case(self, user_id: str) -> Dict[str, Any]:
        """Use an unlocked case key; initialize only a demonstrably new profile."""
        self._require_local_filesystem_access()
        user = self._resolve_user_id(user_id)
        self._require_private_case_key_access(user, user, principal_id=user)
        from integrations.private_storage import PrivateArtifactBinding, PrivateKeyMaterialError

        keys = self._private_key_session()
        if not keys.unlocked:
            raise WorkspacePersistenceError("Private workspace keys require unlock.", code="unlock_needed", public_status="unlock_needed")
        binding = PrivateArtifactBinding(tenant_id=user, case_id=user, principal_id=user,
                                         artifact_kind="session", revision="session-v1")
        try:
            self.private_key_provider().resolve(binding)
        except PrivateKeyMaterialError:
            # Missing keys for an existing profile mean recovery, never a new
            # identity. Unindexed ciphertext is also insufficient proof that
            # creating a fresh case key is safe.
            base = self._namespace_filename(user)
            existing = [self._session_dir / base, self._session_dir / (base + ".cgpe"),
                        self._legacy_session_path(user), self.joined_revision_repository(user, user),
                        self.interview_snapshot_directory(user, user),
                        self._session_dir / "private-artifacts", self._session_dir / "private-migrations"]
            if any(os.path.lexists(path) for path in existing):
                raise WorkspacePersistenceError("Recover the selected private case key before continuing.",
                                                code="key_unavailable", public_status="unlock_needed") from None
            ready = self.ensure_private_case_key(user, user)
            if ready.get("unlocked") is not True:
                raise WorkspacePersistenceError("Private workspace keys require unlock.", code="unlock_needed", public_status="unlock_needed")
        return {"status": "ready", "unlock_is_remote_consent": False, "data_reset": False}

    def ensure_private_case_key(self, tenant_id: str, case_id: str) -> Dict[str, Any]:
        """Mint or reload one case data key. The key id is opaque; bytes stay in memory."""

        self._require_private_case_key_access(tenant_id, case_id)

        from integrations.private_storage import PrivateKeyLockedError, task_key_receipt

        session = self._private_key_session()
        try:
            key_id = session.ensure_data_key(tenant_id, case_id)
        except PrivateKeyLockedError as exc:
            receipt = task_key_receipt(exc.public_state())
            receipt.pop("case_count", None)
            return receipt
        state = session.public_state()
        state["message"] = "Case data key is available in this unlocked session."
        receipt = task_key_receipt(state)
        receipt.pop("case_count", None)
        receipt["data_key_id"] = key_id
        return receipt

    def private_key_provider(self):
        """Request-checked lazy case provider; a handle retains no raw key map."""

        access = self._effective_access()
        authority = self._owner_case_authority()
        if authority is not None:
            self._require_private_case_key_access(authority.canonical_owner_principal_id, authority.case_id)
        elif access.trust == "trusted_local" and not access.principal_id and not access.case_id:
            self._require_local_filesystem_access()
        else:
            self._require_private_case_key_access(access.principal_id, access.case_id)
        session = self._private_key_session()
        if not session.unlocked:
            # Preserve the native typed construction failure without copying any
            # unlocked case keys into the returned, long-lived handle.
            session.provider()
        return _WorkspaceCaseKeyProvider(self, request_authority=authority)

    def continue_without_private_keys(self) -> Dict[str, Any]:
        """Let a coding supervisor proceed without user keys or a privacy bypass."""

        self._require_local_filesystem_access()

        from integrations.private_storage import task_key_receipt

        state = self._private_key_session().public_state()
        if not state.get("unlocked"):
            state["status"] = "awaiting_user"
            state["awaiting_user"] = True
        state["worker_state"] = "ready_for_independent_tasks"
        state["invented_key"] = False
        state["privacy_bypassed"] = False
        state["message"] = "Private keys stay locked until the user unlocks them. Other coding work can continue."
        return task_key_receipt(state)

    def generate_grounded_text(
        self,
        user_id: Optional[str],
        *,
        prompt: str,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        grounding_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        from integrations.ipfs_datasets.llm import generate_text_with_metadata

        resolved_user_id = str(user_id or DEFAULT_USER_ID)
        state = self._load_state(resolved_user_id)
        helpers = _privacy_helpers()
        privacy_context = helpers["build_complaint_privacy_context"](
            state.get("privacy_policy"),
            user_id=resolved_user_id,
            case_id=_state_case_id(state, resolved_user_id),
            data_class="raw_intake",
        )
        resolved_grounding_mode = self._resolve_mike_grounding_mode(grounding_mode or "legal_corpus_only")
        generated = generate_text_with_metadata(
            f"[grounding_mode={resolved_grounding_mode}]\n{prompt}",
            provider=provider,
            model_name=model_name,
            complaint_privacy_context=privacy_context,
        )
        if not isinstance(generated, dict):
            generated = {"status": "error", "text": "", "error": "privacy_denied:malformed_consent"}
        public_generation = dict(generated)
        if str(public_generation.get("privacy_decision") or "") == "denied":
            public_generation.pop("prompt", None)
        return {
            "user_id": resolved_user_id,
            "case_id": _state_case_id(state, resolved_user_id),
            "grounding_mode": resolved_grounding_mode,
            "text": str(public_generation.get("text") or ""),
            "generation": public_generation,
            "at_rest_protection": "private_envelope",
        }

    def search_corpus(self, *, query: str, max_results: int = 5) -> Dict[str, Any]:
        from integrations.ipfs_datasets.search import search_multi_engine_web

        try:
            results = search_multi_engine_web(str(query or ""), max_results=int(max_results or 5))
        except Exception as exc:
            return {
                "status": "degraded",
                "query": str(query or ""),
                "results": [],
                "error": str(exc),
            }
        return {
            "status": "available",
            "query": str(query or ""),
            "results": list(results or []),
        }

    def get_handoff(self, user_id: Optional[str], **kwargs: Any) -> Dict[str, Any]:
        return self.build_mike_handoff(user_id, **kwargs)

    def sync_draft(self, user_id: Optional[str], **kwargs: Any) -> Dict[str, Any]:
        return self.sync_mike_final_draft(user_id, **kwargs)

    def list_mcp_tools(self) -> Dict[str, Any]:
        return {
            "tools": [
                {"name": "complaint.create_identity", "description": "Create a decentralized identity for browser or CLI use."},
                {"name": "complaint.list_intake_questions", "description": "List the complaint intake questions used across browser, CLI, and MCP flows."},
                {"name": "complaint.list_claim_elements", "description": "List the tracked claim elements used for evidence and review."},
                {"name": "complaint.dispatch_bounded_gui_inference", "description": "Bound owner-case inference with fresh persisted purpose consent."},
                {"name": "complaint.admit_bounded_gui_inference", "description": "Revalidate current case consent, grant and source before release."},
                {"name": "complaint.start_session", "description": "Load or initialize a complaint workspace session."},
                {"name": "complaint.submit_intake", "description": "Save complaint intake answers."},
                {"name": "complaint.run_intake_chat_turn", "description": "Advance the shared mediator-style intake chat one turn and persist the captured answer."},
                {"name": "complaint.save_evidence", "description": "Save testimony or document evidence to the workspace."},
                {"name": "complaint.tag_document_annotation", "description": "Save a dataset document annotation with tags, annotator metadata, and knowledge-graph relationships."},
                {"name": "complaint.get_document_annotation_graph", "description": "Return document annotation, tag, user, and claim-element relationships for the current workspace."},
                {"name": "complaint.tag_workspace_dataset_document", "description": "Annotate and tag a workspace dataset document with collection/type indexing."},
                {"name": "complaint.get_workspace_dataset_annotation_index", "description": "Return workspace dataset annotations grouped by tag, collection, document type, and claim element."},
                {"name": "complaint.import_gmail_evidence", "description": "Import matching Gmail messages and attachments into the complaint evidence workspace."},
                {"name": "complaint.run_gmail_duckdb_pipeline", "description": "Run a checkpointed Gmail-to-DuckDB pipeline across many mailbox windows and optional BM25 search."},
                {"name": "complaint.import_local_evidence", "description": "Import local files or directories into the complaint evidence workspace."},
                {"name": "complaint.search_email_duckdb_corpus", "description": "Search an existing Gmail DuckDB corpus with BM25 or weighted keyword ranking."},
                {"name": "complaint.review_case", "description": "Return the current support matrix and evidence review."},
                {"name": "complaint.build_mediator_prompt", "description": "Build a testimony-ready chat mediator prompt from the shared case synopsis and support gaps."},
                {"name": "complaint.get_complaint_readiness", "description": "Estimate whether the current complaint record is ready for drafting, still building, or already in draft refinement."},
                {"name": "complaint.get_ui_readiness", "description": "Return the latest cached actor/critic UI readiness verdict for this complaint session."},
                {"name": "complaint.get_client_release_gate", "description": "Combine complaint readiness, UI readiness, and complaint-output quality into one client-safety release gate."},
                {"name": "complaint.get_workflow_capabilities", "description": "Summarize which complaint-workflow abilities are currently available for the session."},
                {"name": "complaint.get_tooling_contract", "description": "Show how the core complaint workflow is exposed across package exports, CLI commands, MCP tools, and browser SDK methods."},
                {"name": "complaint.get_workspace_data_schema", "description": "Inspect the current or packaged workspace dataset schema so MCP and UI surfaces can follow the actual parquet data model."},
                {"name": "complaint.migrate_legacy_workspace_data", "description": "Project legacy complaint session and mediator DuckDB state into a packaged workspace dataset stored as parquet pieces."},
                {"name": "complaint.view_workspace_dataset", "description": "Browse a packaged or single-file workspace dataset with schema-aligned filters and filtered document previews."},
                {"name": "complaint.search_workspace_dataset", "description": "Search a packaged or single-file workspace dataset using BM25 or vector retrieval plus schema-aligned filters."},
                {"name": "complaint.get_workspace_dataset_graph", "description": "Explore workspace dataset knowledge-graph entities, relationships, deontic logic flow, formulas, conflicts, and proof links."},
                {"name": "complaint.build_mike_handoff", "description": "Build a Mike editor handoff payload with prefilled complaint draft, review state, and evidence context."},
                {"name": "complaint.get_mike_integration_status", "description": "Return Mike handoff/sync status, correlation IDs, and recommended next integration action."},
                {"name": "complaint.sync_mike_final_draft", "description": "Sync an edited draft from Mike back into the complaint workspace and persist the merged draft state."},
                {"name": "complaint.generate_grounded_text", "description": "Generate grounded complaint text through the accelerate llm_router under the legal corpus grounding mode."},
                {"name": "complaint.search_corpus", "description": "Search the complaint corpus through the datasets search adapter."},
                {"name": "complaint.get_handoff", "description": "Build the Mike handoff payload, including the MCP connector contract."},
                {"name": "complaint.sync_draft", "description": "Sync a Mike document version back into the complaint workspace and return document_version_content_sha256."},
                {"name": "complaint.get_draft_proof_report", "description": "Run the draft-logic pipeline on the current complaint draft and return the full DraftProofReport with proof status, contradictions, corpus coverage, and deontic norms."},
                {"name": "complaint.render_draft_proof_report", "description": "Run the draft-logic pipeline on the current draft and render a human-readable Markdown proof report."},
                {"name": "complaint.pin_draft_proof_report", "description": "Run the draft-logic pipeline, then pin the DraftProofReport and its Lean 4 / Coq theorem exports to IPFS for immutable provenance."},
                {"name": "complaint.score_draft_quality", "description": "Score the current complaint draft across five quality dimensions (corpus grounding, proof completeness, policy compliance, contradiction-free, theorem readiness) and return a grade and prioritised improvement suggestions."},
                {"name": "complaint.improve_draft", "description": "Apply the top quality-scorer suggestions to the complaint draft via the LLM router and persist the improved body back to the workspace."},
                {"name": "complaint.get_proof_history", "description": "Return the history of draft proof-pipeline runs for this session showing proof status, quality score, and grade over time."},
                {"name": "complaint.generate_complaint", "description": "Generate a complaint draft from intake and evidence."},
                {"name": "complaint.update_draft", "description": "Persist edits to the generated complaint draft."},
                {"name": "complaint.export_complaint_packet", "description": "Export the current lawsuit complaint packet with intake, evidence, review, and draft content."},
                {"name": "complaint.export_complaint_markdown", "description": "Export the generated complaint as a downloadable Markdown artifact."},
                {"name": "complaint.export_complaint_docx", "description": "Export the generated complaint as a downloadable DOCX artifact."},
                {"name": "complaint.export_complaint_pdf", "description": "Export the generated complaint as a downloadable PDF artifact."},
                {"name": "complaint.analyze_complaint_output", "description": "Analyze the generated complaint output and turn filing-shape gaps into concrete UI/UX suggestions."},
                {"name": "complaint.get_formal_diagnostics", "description": "Return the compact formal-complaint diagnostics summary for the current complaint draft and export state."},
                {"name": "complaint.get_filing_provenance", "description": "Return the shared routing provenance for complaint generation, filing critique, export critique, and cached UI review workflows."},
                {"name": "complaint.get_provider_diagnostics", "description": "Report which llm_router providers are actually usable on this machine, in the same order the router will prefer them."},
                {"name": "complaint.view_docket_dataset", "description": "Load a docket dataset from packaged or source JSON input and return docket documents, summary, and metadata for dashboard viewing."},
                {"name": "complaint.search_docket_dataset", "description": "Search a docket dataset with bm25 or vector retrieval and return matching docket entries for dashboard exploration."},
                {"name": "complaint.get_docket_dataset_metadata", "description": "Return the docket dataset summary and metadata used by the complaint MCP dashboard."},
                {"name": "complaint.get_docket_dataset_graph", "description": "Return knowledge-graph entities, relationships, and extracted legal-issue links for a docket dataset."},
                {"name": "complaint.review_generated_exports", "description": "Review generated complaint export artifacts through llm_router and turn filing-output weaknesses into UI/UX repair suggestions."},
                {"name": "complaint.get_packaged_docket_operator_dashboard", "description": "Load the combined packaged docket operator dashboard for a docket bundle manifest."},
                {"name": "complaint.load_packaged_docket_operator_dashboard_report", "description": "Load the archived packaged docket operator dashboard report artifact for a docket bundle manifest."},
                {"name": "complaint.execute_packaged_docket_proof_revalidation_queue", "description": "Execute the packaged docket proof revalidation queue for a docket bundle manifest and return execution summaries."},
                {"name": "complaint.persist_packaged_docket_proof_revalidation_queue", "description": "Execute packaged docket proof revalidation and write a refreshed parquet/CAR bundle to an output directory."},
                {"name": "complaint.update_claim_type", "description": "Set the current complaint type so drafting and review stay aligned to the right legal claim shape."},
                {"name": "complaint.update_case_synopsis", "description": "Persist a shared case synopsis that stays visible across workspace, CLI, and MCP flows."},
                {"name": "complaint.reset_session", "description": "Clear the complaint workspace session."},
                {"name": "complaint.review_ui", "description": "Review Playwright screenshot artifacts, optionally run an iterative UI/UX workflow, and produce a router-backed MCP dashboard critique."},
                {"name": "complaint.optimize_ui", "description": "Run the closed-loop screenshot, llm_router, actor/critic optimizer, and revalidation workflow for the complaint dashboard UI."},
                {"name": "complaint.run_browser_audit", "description": "Run the Playwright end-to-end complaint browser audit that drives chat, intake, evidence, review, draft, and builder surfaces."},
            ]
        }

    def call_mcp_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = dict(arguments or {})
        if any(args.get(key) not in (None, "", []) for key in _MCP_HOST_PATH_ARGUMENTS):
            self._require_local_filesystem_access()
        if tool_name not in _PUBLIC_MCP_TOOLS:
            resolved = self._resolve_user_id(args.get("user_id"))
            case_id = args.get("case_id")
            selected_case = None if case_id is None or str(case_id).strip() == "" else str(case_id)
            cid_value = args.get("cid") if args.get("cid") is not None else args.get("content_id")
            key_value = args.get("storage_key") if args.get("storage_key") is not None else args.get("key")
            track_reference = tool_name == "complaint.resolve_private_reference" or cid_value is not None or key_value is not None
            self._check_access(resolved, ability="read", case_id=selected_case)
            args["user_id"] = resolved
            with _workspace_reference_scope(
                case_id=selected_case,
                cid=None if not track_reference or cid_value is None else str(cid_value),
                storage_key=None if not track_reference or key_value is None else str(key_value),
            ):
                return self._dispatch_mcp_tool(tool_name, args)
        return self._dispatch_mcp_tool(tool_name, args)

    def _dispatch_mcp_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "complaint.dispatch_bounded_gui_inference":
            if set(args) - {"user_id", "purpose", "inputs", "timeout_seconds"}:
                return self._gui_inference_refusal("caller_authority_not_accepted")
            return self.dispatch_bounded_gui_inference(args.get("user_id"), purpose=args.get("purpose"),
                inputs=args.get("inputs"), timeout_seconds=args.get("timeout_seconds", 30.0))
        if tool_name == "complaint.admit_bounded_gui_inference":
            if set(args) - {"user_id", "invocation_id"}:
                return self._gui_inference_refusal("caller_authority_not_accepted")
            return self.admit_bounded_gui_inference(args.get("user_id"), invocation_id=args.get("invocation_id"))
        if tool_name == "complaint.read_contained_file":
            data = self.read_contained_workspace_file(args.get("user_id"), str(args.get("relative_name") or ""))
            return {
                "content_b64": b64encode(data).decode("ascii"),
                "at_rest_protection": "private_envelope",
            }
        if tool_name == "complaint.write_contained_file":
            raw_content = args.get("content")
            if isinstance(raw_content, str):
                payload = raw_content.encode("utf-8")
            else:
                payload = bytes(raw_content or b"")
            return self.write_contained_workspace_file(args.get("user_id"), str(args.get("relative_name") or ""), payload)
        if tool_name == "complaint.remember_private_reference":
            return self.remember_private_reference(
                args.get("user_id"),
                cid=args.get("cid") or args.get("content_id"),
                storage_key=args.get("storage_key") or args.get("key"),
                case_id=args.get("case_id"),
            )
        if tool_name == "complaint.resolve_private_reference":
            return self.resolve_private_reference(
                args.get("user_id"),
                case_id=args.get("case_id"),
                cid=args.get("cid") or args.get("content_id"),
                storage_key=args.get("storage_key") or args.get("key"),
            )
        if tool_name == "complaint.create_identity":
            return generate_decentralized_id()
        if tool_name == "complaint.list_intake_questions":
            return self.list_intake_questions()
        if tool_name == "complaint.list_claim_elements":
            return self.list_claim_elements()
        if tool_name == "complaint.start_session":
            return self.get_session(args.get("user_id"), case_id=args.get("case_id"))
        if tool_name == "complaint.submit_intake":
            return self.submit_intake_answers(args.get("user_id"), args.get("answers") or {})
        if tool_name == "complaint.run_intake_chat_turn":
            return self.run_intake_chat_turn(
                args.get("user_id"),
                message=args.get("message"),
                question_id=args.get("question_id"),
                expected_question_revision=args.get("expected_question_revision"),
                interview_action=args.get("interview_action"),
                expected_graph_revision=args.get("expected_graph_revision"),
                expected_session_revision=args.get("expected_session_revision"),
            )
        if tool_name == "complaint.save_evidence":
            return self.save_evidence(
                args.get("user_id"),
                kind=str(args.get("kind") or "testimony"),
                claim_element_id=str(args.get("claim_element_id") or "causation"),
                title=str(args.get("title") or "Untitled evidence"),
                content=str(args.get("content") or ""),
                source=args.get("source"),
                attachment_names=args.get("attachment_names"),
            )
        if tool_name == "complaint.tag_document_annotation":
            return self.tag_document_annotation(
                args.get("user_id"),
                document_id=str(args.get("document_id") or ""),
                tags=args.get("tags") or [],
                note=str(args.get("note") or ""),
                claim_element_id=str(args.get("claim_element_id") or "causation"),
                title=str(args.get("title") or "Dataset document annotation"),
                dataset_kind=str(args.get("dataset_kind") or "dataset"),
                document_title=args.get("document_title"),
                document_text_preview=args.get("document_text_preview"),
                document_metadata=dict(args.get("document_metadata") or {}),
                user_metadata=dict(args.get("user_metadata") or {}),
                source=args.get("source"),
            )
        if tool_name == "complaint.get_document_annotation_graph":
            return self.get_document_annotation_graph(args.get("user_id"))
        if tool_name == "complaint.tag_workspace_dataset_document":
            return self.tag_workspace_dataset_document(
                args.get("user_id"),
                document_id=str(args.get("document_id") or ""),
                tags=args.get("tags") or [],
                note=str(args.get("note") or ""),
                claim_element_id=str(args.get("claim_element_id") or "causation"),
                title=str(args.get("title") or "Workspace dataset document annotation"),
                document_title=args.get("document_title"),
                document_text_preview=args.get("document_text_preview"),
                collection_id=args.get("collection_id"),
                document_type=args.get("document_type"),
                claim_type=args.get("claim_type"),
                source_type=args.get("source_type"),
                document_metadata=dict(args.get("document_metadata") or {}),
                user_metadata=dict(args.get("user_metadata") or {}),
                source=args.get("source"),
            )
        if tool_name == "complaint.get_workspace_dataset_annotation_index":
            return self.get_workspace_dataset_annotation_index(args.get("user_id"))
        if tool_name == "complaint.import_gmail_evidence":
            return self.import_gmail_evidence(
                args.get("user_id"),
                addresses=[str(item).strip() for item in list(args.get("addresses") or []) if str(item).strip()],
                claim_element_id=str(args.get("claim_element_id") or "causation"),
                folder=str(args.get("folder") or "INBOX"),
                folders=[str(item).strip() for item in list(args.get("folders") or []) if str(item).strip()],
                limit=int(args["limit"]) if args.get("limit") is not None else None,
                date_after=str(args.get("date_after") or "") or None,
                date_before=str(args.get("date_before") or "") or None,
                years_back=int(args["years_back"]) if args.get("years_back") is not None else None,
                evidence_root=str(args.get("evidence_root") or "") or None,
                gmail_user=str(args.get("gmail_user") or "") or None,
                gmail_app_password=str(args.get("gmail_app_password") or "") or None,
                use_gmail_oauth=bool(args.get("use_gmail_oauth") or False),
                gmail_oauth_client_secrets=str(args.get("gmail_oauth_client_secrets") or "") or None,
                gmail_oauth_token_cache=str(args.get("gmail_oauth_token_cache") or "") or None,
                gmail_oauth_open_browser=bool(True if args.get("gmail_oauth_open_browser") is None else args.get("gmail_oauth_open_browser")),
                complaint_query=str(args.get("complaint_query") or "") or None,
                complaint_keywords=[str(item).strip() for item in list(args.get("complaint_keywords") or []) if str(item).strip()],
                min_relevance_score=float(args.get("min_relevance_score") or 0.0),
                use_uid_checkpoint=bool(args.get("use_uid_checkpoint") or False),
                checkpoint_name=str(args.get("checkpoint_name") or "") or None,
                uid_window_size=int(args["uid_window_size"]) if args.get("uid_window_size") is not None else None,
            )
        if tool_name == "complaint.run_gmail_duckdb_pipeline":
            return self.run_gmail_duckdb_pipeline(
                args.get("user_id"),
                addresses=[str(item).strip() for item in list(args.get("addresses") or []) if str(item).strip()],
                claim_element_id=str(args.get("claim_element_id") or "causation"),
                folder=str(args.get("folder") or "INBOX"),
                folders=[str(item).strip() for item in list(args.get("folders") or []) if str(item).strip()],
                years_back=int(args["years_back"]) if args.get("years_back") is not None else 2,
                date_after=str(args.get("date_after") or "") or None,
                date_before=str(args.get("date_before") or "") or None,
                complaint_query=str(args.get("complaint_query") or "") or None,
                complaint_keywords=[str(item).strip() for item in list(args.get("complaint_keywords") or []) if str(item).strip()],
                min_relevance_score=float(args.get("min_relevance_score") or 0.0),
                evidence_root=str(args.get("evidence_root") or "") or None,
                gmail_user=str(args.get("gmail_user") or "") or None,
                gmail_app_password=str(args.get("gmail_app_password") or "") or None,
                use_gmail_oauth=bool(args.get("use_gmail_oauth") or False),
                gmail_oauth_client_secrets=str(args.get("gmail_oauth_client_secrets") or "") or None,
                gmail_oauth_token_cache=str(args.get("gmail_oauth_token_cache") or "") or None,
                gmail_oauth_open_browser=bool(True if args.get("gmail_oauth_open_browser") is None else args.get("gmail_oauth_open_browser")),
                checkpoint_name=str(args.get("checkpoint_name") or "gmail-duckdb-pipeline"),
                uid_window_size=int(args["uid_window_size"]) if args.get("uid_window_size") is not None else 500,
                max_batches=int(args["max_batches"]) if args.get("max_batches") is not None else 20,
                duckdb_output_dir=str(args.get("duckdb_output_dir") or "") or None,
                append_to_existing_corpus=bool(args.get("append_to_existing_corpus") or False),
                bm25_search_query=str(args.get("bm25_search_query") or "") or None,
                bm25_search_limit=int(args["bm25_search_limit"]) if args.get("bm25_search_limit") is not None else 20,
            )
        if tool_name == "complaint.import_local_evidence":
            return self.import_local_evidence(
                args.get("user_id"),
                paths=[str(item).strip() for item in list(args.get("paths") or []) if str(item).strip()],
                claim_element_id=str(args.get("claim_element_id") or "causation"),
                kind=str(args.get("kind") or "document"),
                evidence_root=str(args.get("evidence_root") or "") or None,
            )
        if tool_name == "complaint.search_email_duckdb_corpus":
            return self.search_email_duckdb_corpus(
                index_path=str(args.get("index_path") or ""),
                query=str(args.get("query") or ""),
                limit=int(args["limit"]) if args.get("limit") is not None else 20,
                ranking=str(args.get("ranking") or "bm25"),
                bm25_k1=float(args.get("bm25_k1") or 1.2),
                bm25_b=float(args.get("bm25_b") or 0.75),
            )
        if tool_name == "complaint.review_case":
            session = self.get_session(args.get("user_id"))
            return {
                "session": session["session"],
                "review": session["review"],
                "questions": session["questions"],
                "next_question": session["next_question"],
                "case_synopsis": session["case_synopsis"],
            }
        if tool_name == "complaint.build_mediator_prompt":
            return self.build_mediator_prompt(args.get("user_id"))
        if tool_name == "complaint.get_complaint_readiness":
            return self.get_complaint_readiness(args.get("user_id"))
        if tool_name == "complaint.get_ui_readiness":
            return self.get_ui_readiness(args.get("user_id"))
        if tool_name == "complaint.get_client_release_gate":
            return self.get_client_release_gate(args.get("user_id"))
        if tool_name == "complaint.get_workflow_capabilities":
            return self.get_workflow_capabilities(args.get("user_id"))
        if tool_name == "complaint.get_tooling_contract":
            return self.get_tooling_contract(args.get("user_id"))
        if tool_name == "complaint.get_workspace_data_schema":
            return self.get_workspace_data_schema(
                args.get("user_id"),
                manifest_path=args.get("manifest_path"),
                statefile_path=args.get("statefile_path"),
                evidence_db_path=args.get("evidence_db_path"),
                legal_authority_db_path=args.get("legal_authority_db_path"),
                claim_support_db_path=args.get("claim_support_db_path"),
            )
        if tool_name == "complaint.migrate_legacy_workspace_data":
            return self.migrate_legacy_workspace_data(
                args.get("user_id"),
                output_dir=args.get("output_dir"),
                statefile_path=args.get("statefile_path"),
                evidence_db_path=args.get("evidence_db_path"),
                legal_authority_db_path=args.get("legal_authority_db_path"),
                claim_support_db_path=args.get("claim_support_db_path"),
                package_name=args.get("package_name"),
                include_car=bool(args.get("include_car", True)),
            )
        if tool_name == "complaint.search_workspace_dataset":
            input_path = args.get("input_path") or args.get("manifest_path")
            if not input_path:
                raise ValueError("complaint.search_workspace_dataset requires input_path or manifest_path.")
            return self.search_workspace_dataset(
                input_path,
                input_type=args.get("input_type", "packaged"),
                query=str(args.get("query") or ""),
                search_backend=args.get("search_backend", "bm25"),
                top_k=int(args.get("top_k") or 10),
                vector_dimension=int(args.get("vector_dimension") or 32),
                collection_id=args.get("collection_id"),
                document_type=args.get("document_type"),
                claim_type=args.get("claim_type"),
                claim_element_id=args.get("claim_element_id"),
                source_type=args.get("source_type"),
            )
        if tool_name == "complaint.view_workspace_dataset":
            input_path = args.get("input_path") or args.get("manifest_path")
            if not input_path:
                raise ValueError("complaint.view_workspace_dataset requires input_path or manifest_path.")
            return self.view_workspace_dataset(
                input_path,
                input_type=args.get("input_type", "packaged"),
                include_document_text=bool(args.get("include_document_text")),
                document_limit=int(args.get("document_limit") or 25),
                collection_id=args.get("collection_id"),
                document_type=args.get("document_type"),
                claim_type=args.get("claim_type"),
                claim_element_id=args.get("claim_element_id"),
                source_type=args.get("source_type"),
            )
        if tool_name == "complaint.get_workspace_dataset_graph":
            input_path = args.get("input_path") or args.get("manifest_path")
            if not input_path:
                raise ValueError("complaint.get_workspace_dataset_graph requires input_path or manifest_path.")
            return self.get_workspace_dataset_graph(
                input_path,
                input_type=args.get("input_type", "packaged"),
                entity_query=str(args.get("entity_query") or ""),
                relationship_type=str(args.get("relationship_type") or ""),
                document_id=str(args.get("document_id") or ""),
                modality=str(args.get("modality") or args.get("deontic_status") or ""),
                limit=int(args.get("limit") or 50),
            )
        if tool_name == "complaint.build_mike_handoff":
            return self.build_mike_handoff(
                args.get("user_id"),
                mike_base_url=args.get("mike_base_url"),
                project_id=args.get("project_id"),
                workspace_id=args.get("workspace_id"),
                generate_draft_if_missing=bool(args.get("generate_draft_if_missing", True)),
                grounding_mode=args.get("grounding_mode"),
            )
        if tool_name == "complaint.get_mike_integration_status":
            return self.get_mike_integration_status(args.get("user_id"))
        if tool_name == "complaint.sync_mike_final_draft":
            requested_relief = args.get("requested_relief")
            if isinstance(requested_relief, str):
                requested_relief = _split_lines(requested_relief)
            return self.sync_mike_final_draft(
                args.get("user_id"),
                body=args.get("body"),
                title=args.get("title"),
                requested_relief=requested_relief,
                handoff_id=args.get("handoff_id"),
                project_id=args.get("project_id"),
                workspace_id=args.get("workspace_id"),
                mike_document_id=args.get("mike_document_id"),
                citation_links=args.get("citation_links"),
                redline_summary=args.get("redline_summary"),
                source_updated_at=args.get("source_updated_at"),
                structured_deltas=args.get("structured_deltas"),
                editor_metadata=args.get("editor_metadata"),
                grounding_mode=args.get("grounding_mode"),
                assertion_annotations=args.get("assertion_annotations"),
                authority_links=args.get("authority_links"),
                sync_provenance=args.get("sync_provenance"),
            )
        if tool_name == "complaint.generate_grounded_text":
            return self.generate_grounded_text(
                args.get("user_id"),
                prompt=str(args.get("prompt") or ""),
                provider=args.get("provider"),
                model_name=args.get("model_name") or args.get("model"),
                grounding_mode=args.get("grounding_mode"),
            )
        if tool_name == "complaint.search_corpus":
            return self.search_corpus(
                query=str(args.get("query") or ""),
                max_results=int(args.get("max_results") or 5),
            )
        if tool_name == "complaint.get_handoff":
            return self.get_handoff(
                args.get("user_id"),
                mike_base_url=args.get("mike_base_url"),
                project_id=args.get("project_id"),
                workspace_id=args.get("workspace_id"),
                generate_draft_if_missing=bool(args.get("generate_draft_if_missing", True)),
                grounding_mode=args.get("grounding_mode"),
            )
        if tool_name == "complaint.sync_draft":
            requested_relief = args.get("requested_relief")
            if isinstance(requested_relief, str):
                requested_relief = _split_lines(requested_relief)
            return self.sync_draft(
                args.get("user_id"),
                body=args.get("body"),
                title=args.get("title"),
                requested_relief=requested_relief,
                handoff_id=args.get("handoff_id"),
                project_id=args.get("project_id"),
                workspace_id=args.get("workspace_id"),
                mike_document_id=args.get("mike_document_id"),
                citation_links=args.get("citation_links"),
                redline_summary=args.get("redline_summary"),
                source_updated_at=args.get("source_updated_at"),
                structured_deltas=args.get("structured_deltas"),
                editor_metadata=args.get("editor_metadata"),
                grounding_mode=args.get("grounding_mode"),
                assertion_annotations=args.get("assertion_annotations"),
                authority_links=args.get("authority_links"),
                sync_provenance=args.get("sync_provenance"),
            )
        if tool_name == "complaint.get_draft_proof_report":
            return self.get_draft_proof_report(
                args.get("user_id"),
                state_code=args.get("state_code"),
                allow_live_scrape_fallback=bool(args.get("allow_live_scrape_fallback", False)),
            )
        if tool_name == "complaint.render_draft_proof_report":
            return self.render_draft_proof_report(
                args.get("user_id"),
                state_code=args.get("state_code"),
                claim_id=str(args.get("claim_id") or ""),
            )
        if tool_name == "complaint.pin_draft_proof_report":
            return self.pin_draft_proof_report(
                args.get("user_id"),
                state_code=args.get("state_code"),
                claim_id=str(args.get("claim_id") or ""),
            )
        if tool_name == "complaint.score_draft_quality":
            return self.score_draft_quality(
                args.get("user_id"),
                state_code=args.get("state_code"),
                persist=bool(args.get("persist", True)),
            )
        if tool_name == "complaint.improve_draft":
            return self.improve_draft(
                args.get("user_id"),
                state_code=args.get("state_code"),
                provider=args.get("provider"),
                model=args.get("model"),
                config_path=args.get("config_path"),
                backend_id=args.get("backend_id"),
                max_suggestions=int(args.get("max_suggestions") or 3),
            )
        if tool_name == "complaint.get_proof_history":
            return self.get_proof_history(args.get("user_id"))
        if tool_name == "complaint.generate_complaint":
            return self.generate_complaint(
                args.get("user_id"),
                requested_relief=_split_lines(args.get("requested_relief"))
                if isinstance(args.get("requested_relief"), str)
                else args.get("requested_relief"),
                title_override=args.get("title_override"),
                use_llm=bool(args.get("use_llm")),
                provider=args.get("provider"),
                model=args.get("model"),
                config_path=args.get("config_path"),
                backend_id=args.get("backend_id"),
            )
        if tool_name == "complaint.update_draft":
            requested_relief = args.get("requested_relief")
            if isinstance(requested_relief, str):
                requested_relief = _split_lines(requested_relief)
            return self.update_draft(
                args.get("user_id"),
                title=args.get("title"),
                body=args.get("body"),
                requested_relief=requested_relief,
            )
        if tool_name == "complaint.export_complaint_packet":
            return self.export_complaint_packet(args.get("user_id"))
        if tool_name == "complaint.export_complaint_markdown":
            return self.export_complaint_markdown(args.get("user_id"))
        if tool_name == "complaint.export_complaint_docx":
            return self.export_complaint_docx(args.get("user_id"))
        if tool_name == "complaint.export_complaint_pdf":
            return self.export_complaint_pdf(args.get("user_id"))
        if tool_name == "complaint.analyze_complaint_output":
            return self.analyze_complaint_output(args.get("user_id"))
        if tool_name == "complaint.get_formal_diagnostics":
            return self.get_formal_diagnostics(args.get("user_id"))
        if tool_name == "complaint.get_filing_provenance":
            return self.get_filing_provenance(args.get("user_id"))
        if tool_name == "complaint.get_provider_diagnostics":
            return self.get_provider_diagnostics(args.get("user_id"))
        if tool_name == "complaint.view_docket_dataset":
            input_path = str(args.get("input_path") or "").strip()
            if not input_path:
                raise ValueError("complaint.view_docket_dataset requires input_path.")
            return self.view_docket_dataset(
                input_path,
                input_type=str(args.get("input_type") or "packaged"),
                include_document_text=bool(args.get("include_document_text") or False),
                document_limit=int(args["document_limit"]) if args.get("document_limit") is not None else 25,
            )
        if tool_name == "complaint.search_docket_dataset":
            input_path = str(args.get("input_path") or "").strip()
            query = str(args.get("query") or "").strip()
            if not input_path:
                raise ValueError("complaint.search_docket_dataset requires input_path.")
            if not query:
                raise ValueError("complaint.search_docket_dataset requires query.")
            return self.search_docket_dataset(
                input_path,
                input_type=str(args.get("input_type") or "packaged"),
                query=query,
                search_backend=str(args.get("search_backend") or "bm25"),
                top_k=int(args.get("top_k") or 10),
                vector_dimension=int(args.get("vector_dimension") or 32),
            )
        if tool_name == "complaint.get_docket_dataset_metadata":
            input_path = str(args.get("input_path") or "").strip()
            if not input_path:
                raise ValueError("complaint.get_docket_dataset_metadata requires input_path.")
            return self.get_docket_dataset_metadata(
                input_path,
                input_type=str(args.get("input_type") or "packaged"),
            )
        if tool_name == "complaint.get_docket_dataset_graph":
            input_path = str(args.get("input_path") or "").strip()
            if not input_path:
                raise ValueError("complaint.get_docket_dataset_graph requires input_path.")
            return self.get_docket_dataset_graph(
                input_path,
                input_type=str(args.get("input_type") or "packaged"),
            )
        if tool_name == "complaint.review_generated_exports":
            return self.review_generated_exports(
                args.get("user_id"),
                artifact_path=args.get("artifact_path"),
                artifact_dir=args.get("artifact_dir"),
                provider=args.get("provider"),
                model=args.get("model"),
                config_path=args.get("config_path"),
                backend_id=args.get("backend_id"),
                notes=args.get("notes"),
            )
        if tool_name == "complaint.get_packaged_docket_operator_dashboard":
            manifest_path = str(args.get("manifest_path") or "").strip()
            if not manifest_path:
                raise ValueError("complaint.get_packaged_docket_operator_dashboard requires manifest_path.")
            return self.get_packaged_docket_operator_dashboard(manifest_path)
        if tool_name == "complaint.load_packaged_docket_operator_dashboard_report":
            manifest_path = str(args.get("manifest_path") or "").strip()
            if not manifest_path:
                raise ValueError("complaint.load_packaged_docket_operator_dashboard_report requires manifest_path.")
            return self.load_packaged_docket_operator_dashboard_report(
                manifest_path,
                report_format=str(args.get("report_format") or "parsed"),
            )
        if tool_name == "complaint.execute_packaged_docket_proof_revalidation_queue":
            manifest_path = str(args.get("manifest_path") or "").strip()
            if not manifest_path:
                raise ValueError("complaint.execute_packaged_docket_proof_revalidation_queue requires manifest_path.")
            return self.execute_packaged_docket_proof_revalidation_queue(
                manifest_path,
                top_k=int(args.get("top_k") or 10),
                min_priority=str(args.get("min_priority") or "low"),
                queue_limit=int(args["queue_limit"]) if args.get("queue_limit") is not None else None,
                execution_top_k=int(args.get("execution_top_k") or 10),
                chain_until_satisfied=bool(True if args.get("chain_until_satisfied") is None else args.get("chain_until_satisfied")),
                attach_refreshed_packets=bool(args.get("attach_refreshed_packets") or False),
            )
        if tool_name == "complaint.persist_packaged_docket_proof_revalidation_queue":
            manifest_path = str(args.get("manifest_path") or "").strip()
            output_dir = str(args.get("output_dir") or "").strip()
            if not manifest_path:
                raise ValueError("complaint.persist_packaged_docket_proof_revalidation_queue requires manifest_path.")
            if not output_dir:
                raise ValueError("complaint.persist_packaged_docket_proof_revalidation_queue requires output_dir.")
            return self.persist_packaged_docket_proof_revalidation_queue(
                manifest_path,
                output_dir,
                package_name=str(args.get("package_name") or "").strip() or None,
                include_car=bool(True if args.get("include_car") is None else args.get("include_car")),
                top_k=int(args.get("top_k") or 10),
                min_priority=str(args.get("min_priority") or "low"),
                queue_limit=int(args["queue_limit"]) if args.get("queue_limit") is not None else None,
                execution_top_k=int(args.get("execution_top_k") or 10),
                chain_until_satisfied=bool(True if args.get("chain_until_satisfied") is None else args.get("chain_until_satisfied")),
            )
        if tool_name == "complaint.update_claim_type":
            return self.update_claim_type(args.get("user_id"), args.get("claim_type"))
        if tool_name == "complaint.update_case_synopsis":
            return self.update_case_synopsis(
                args.get("user_id"),
                args.get("synopsis"),
            )
        if tool_name == "complaint.reset_session":
            return self.reset_session(args.get("user_id"))
        if tool_name == "complaint.review_ui":
            from .ui_review import create_ui_review_report, run_ui_review_workflow
            from complaint_generator.ui_ux_workflow import run_iterative_ui_ux_workflow

            screenshot_paths = args.get("screenshot_paths")
            screenshot_dir = args.get("screenshot_dir")
            iterations = int(args.get("iterations") or 0)
            pytest_target = args.get("pytest_target")
            reuse_existing_screenshots = bool(args.get("reuse_existing_screenshots"))
            supplemental_artifacts = (
                self._build_complaint_output_review_artifacts(args.get("user_id"))
                + self._build_cached_ui_readiness_artifacts(args.get("user_id"))
            )
            if isinstance(screenshot_paths, list):
                return create_ui_review_report(
                    [str(item) for item in screenshot_paths],
                    notes=args.get("notes"),
                    goals=args.get("goals"),
                    provider=args.get("provider"),
                    model=args.get("model"),
                    config_path=args.get("config_path"),
                    backend_id=args.get("backend_id"),
                    output_path=args.get("output_path"),
                )
            if screenshot_dir:
                if iterations > 0:
                    result = run_iterative_ui_ux_workflow(
                        screenshot_dir=str(screenshot_dir),
                        output_dir=args.get("output_path"),
                        iterations=iterations,
                        provider=args.get("provider"),
                        model=args.get("model"),
                        notes=args.get("notes"),
                        goals=args.get("goals"),
                        supplemental_artifacts=supplemental_artifacts,
                        pytest_target=str(pytest_target)
                        if pytest_target
                        else DEFAULT_UI_UX_SCREENSHOT_TARGET,
                        reuse_existing_screenshots=reuse_existing_screenshots,
                    )
                    self._persist_ui_readiness(args.get("user_id"), result)
                    return result
                result = run_ui_review_workflow(
                    str(screenshot_dir),
                    notes=args.get("notes"),
                    goals=args.get("goals"),
                    provider=args.get("provider"),
                    model=args.get("model"),
                    config_path=args.get("config_path"),
                    backend_id=args.get("backend_id"),
                    output_path=args.get("output_path"),
                )
                self._persist_ui_readiness(args.get("user_id"), result)
                return result
            raise ValueError("complaint.review_ui requires screenshot_paths or screenshot_dir.")
        if tool_name == "complaint.optimize_ui":
            from complaint_generator.ui_ux_workflow import run_closed_loop_ui_ux_improvement

            screenshot_dir = args.get("screenshot_dir")
            if not screenshot_dir:
                raise ValueError("complaint.optimize_ui requires screenshot_dir.")
            supplemental_artifacts = (
                self._build_complaint_output_review_artifacts(args.get("user_id"))
                + self._build_cached_ui_readiness_artifacts(args.get("user_id"))
            )
            result = run_closed_loop_ui_ux_improvement(
                screenshot_dir=str(screenshot_dir),
                output_dir=str(args.get("output_path") or Path(str(screenshot_dir)).expanduser().resolve() / "closed-loop"),
                pytest_target=str(args.get("pytest_target") or DEFAULT_UI_UX_SCREENSHOT_TARGET),
                max_rounds=int(args.get("max_rounds") or 2),
                review_iterations=int(args.get("iterations") or 1),
                provider=args.get("provider"),
                model=args.get("model"),
                method=str(args.get("method") or DEFAULT_UI_UX_OPTIMIZER_METHOD),
                priority=int(args.get("priority") or DEFAULT_UI_UX_OPTIMIZER_PRIORITY),
                notes=args.get("notes"),
                goals=args.get("goals"),
                supplemental_artifacts=supplemental_artifacts,
                reuse_existing_screenshots=bool(args.get("reuse_existing_screenshots")),
            )
            self._persist_ui_readiness(args.get("user_id"), result)
            return result
        if tool_name == "complaint.run_browser_audit":
            from complaint_generator.ui_ux_workflow import run_end_to_end_complaint_browser_audit

            screenshot_dir = args.get("screenshot_dir")
            if not screenshot_dir:
                raise ValueError("complaint.run_browser_audit requires screenshot_dir.")
            return run_end_to_end_complaint_browser_audit(
                screenshot_dir=str(screenshot_dir),
                pytest_target=str(args.get("pytest_target") or DEFAULT_UI_UX_SCREENSHOT_TARGET),
            )
        raise ValueError(f"Unknown complaint MCP tool: {tool_name}")
