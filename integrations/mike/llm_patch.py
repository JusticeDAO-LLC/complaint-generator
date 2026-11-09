"""Compatibility stamp for Mike handoff payloads.

Mike remains the editor. This module does not rewrite Mike TypeScript and does
not intercept ``backend/src/lib/llm/index.ts``. The stamp records that grounded
drafting belongs to the complaint-generator MCP connector
(``mike_integration.transport = "mcp_connector"``). Mike's own LLM may still
run UI chores.

``apply_mike_llm_router_patch`` keeps ``mike-llm-router-patch-v1`` so older
handoff readers still see the centralized-policy flags. New callers should use
the connector tools ``complaint.generate_grounded_text``,
``complaint.search_corpus``, ``complaint.get_handoff``, and
``complaint.sync_draft``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from integrations.ipfs_datasets.llm import (
    LLM_ROUTER_AVAILABLE,
    LLM_ROUTER_ERROR,
    generate_text_with_metadata,
)

MIKE_LLM_PATCH_VERSION = "mike-llm-router-patch-v1"

MIKE_LLM_PATCH_DESCRIPTOR: Dict[str, Any] = {
    "patch_version": MIKE_LLM_PATCH_VERSION,
    "patch_module": "integrations.mike.llm_patch",
    "compatibility_only": True,
    "transport": "mcp_connector",
    "enforcement_boundary": "workspace_mcp_server",
    "generation_adapter": "integrations.ipfs_datasets.llm.generate_text_with_metadata",
    "router_owned_by": "complaint_generator",
    "mike_role": "editing_surface_only",
    "policy_fields_enforced": [
        "router_policy.centralized_policy.*",
        "router_policy.narrow_adapter_boundary.*",
        "non_negotiable_constraints.must_route_generation_through_workspace_llm_router",
    ],
}


def apply_mike_llm_router_patch(handoff_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Inject workspace llm_router ownership into *handoff_payload* in-place.

    The function:

    * Ensures every ``centralized_policy`` flag inside ``router_policy`` is True.
    * Ensures every ``narrow_adapter_boundary`` flag is True.
    * Records patch metadata (version, timestamp, router availability).
    * Sets ``must_route_generation_through_workspace_llm_router`` in
      ``non_negotiable_constraints``.

    Returns the same dict (mutated) for fluent chaining.
    """
    patched_at = datetime.now(tz=timezone.utc).isoformat()

    router_policy = handoff_payload.setdefault("router_policy", {})
    centralized_policy = router_policy.setdefault("centralized_policy", {})
    centralized_policy["router_selection_in_workspace"] = True
    centralized_policy["model_selection_in_workspace"] = True
    centralized_policy["safety_policy_in_workspace"] = True
    centralized_policy["grounding_policy_in_workspace"] = True

    narrow = router_policy.setdefault("narrow_adapter_boundary", {})
    narrow["mike_requests_generation_via_workspace"] = True
    narrow["mike_does_not_choose_provider"] = True
    narrow["mike_does_not_choose_model"] = True

    router_policy["patched_by"] = MIKE_LLM_PATCH_VERSION
    router_policy["patched_at"] = patched_at
    router_policy["llm_router_available"] = LLM_ROUTER_AVAILABLE
    router_policy["llm_router_error"] = str(LLM_ROUTER_ERROR or "") or None

    constraints = handoff_payload.setdefault("non_negotiable_constraints", {})
    constraints["must_route_generation_through_workspace_llm_router"] = True

    handoff_payload.setdefault("mike_llm_patch", {}).update(
        {
            **MIKE_LLM_PATCH_DESCRIPTOR,
            "patched_at": patched_at,
            "llm_router_available": LLM_ROUTER_AVAILABLE,
        }
    )

    return handoff_payload


def get_router_generate_fn():
    """Return the workspace generation function for callers that want a handle."""
    return generate_text_with_metadata


__all__ = [
    "MIKE_LLM_PATCH_VERSION",
    "MIKE_LLM_PATCH_DESCRIPTOR",
    "apply_mike_llm_router_patch",
    "get_router_generate_fn",
]
