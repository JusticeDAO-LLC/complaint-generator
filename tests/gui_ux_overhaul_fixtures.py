"""Synthetic capture recipes for the complaint UX screenshot matrix.

Screenshots are produced through the public ASGI app and the pinned
Chromium/Node harness. This module does not read operator profiles, invent
evidence bytes, or leave a browser running.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from applications.admin_api import OperationalAdminService
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "ux" / "complaint_ux_overhaul" / "capture_contract.json"
BASELINE_DIR = ROOT / "docs" / "ux" / "complaint_ux_overhaul" / "baseline"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ADMIN_CREDENTIAL = "synthetic-admin-credential"
CHAT_FACT = "Synthetic chat fact about a fictional employer and no real person."
DRAFT_NOTE = "Synthetic correspondence that stays in the composer until a real send."
OWNER_CREDENTIAL = "synthetic-owner-credential"
LAWYER_CREDENTIAL = "synthetic-lawyer-credential"


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix_cells(contract: dict | None = None) -> list[dict]:
    """One cell per surface, phase, and declared viewport."""

    contract = load_contract() if contract is None else contract
    cells = []
    for surface in contract["surfaces"]:
        for phase in contract["phases"]:
            for name, size in contract["viewports"].items():
                cells.append({
                    "surface": surface["id"],
                    "role": surface["role"],
                    "route": surface["route"],
                    "phase": phase,
                    "viewport": name,
                    "width": size["width"],
                    "height": size["height"],
                    "dom": surface["before_dom"] if phase == "before" else surface["after_dom"],
                    "baseline_ids": list(surface["baseline_ids"]),
                })
    return cells


def synthetic_capture_world(tmp_path: Path):
    """Journey owners plus a separate operational-admin principal.

    The admin credential is an operator fixture secret. It is not read from a
    request body and it does not grant case content.
    """

    world = owner_lawyer_journey_world(tmp_path)
    admin = world.principals.install_server_role(role="operational_admin")
    world.sessions._adapter._credentials[ADMIN_CREDENTIAL] = admin.principal_id
    world.app.state.operational_admin = OperationalAdminService(
        principals=world.principals,
        sessions=world.sessions,
        clock=lambda: int(world.now["t"]),
        audit_principal_ids=(admin.principal_id,),
        memberships=world.memberships,
        cases=world.cases,
        assignments=world.assignments,
    )
    world.admin = admin
    world.admin_credential = ADMIN_CREDENTIAL
    return world


def refuse_invented_evidence(record: dict) -> None:
    """A capture may describe a surface. It may not supply evidence bytes."""

    if not isinstance(record, dict):
        raise ValueError("capture_record_required")
    if record.get("invented_evidence") or record.get("evidence_bytes") or record.get("real_user_data"):
        raise ValueError("invented_or_real_evidence_refused")
    source = record.get("source")
    if source not in {"public_asgi_handler", "pinned_chromium_pipe"}:
        raise ValueError("capture_source_refused")
    if record.get("mock_api_used") or record.get("diagnostic_test_panels_mounted"):
        raise ValueError("diagnostic_capture_refused")
    route = record.get("route")
    if not isinstance(route, str) or not route.startswith("/"):
        raise ValueError("capture_route_refused")


def assert_png(payload: bytes, *, minimum: int = 800) -> str:
    if not isinstance(payload, (bytes, bytearray)) or not bytes(payload).startswith(PNG_MAGIC):
        raise ValueError("screenshot_not_png")
    if len(payload) < minimum:
        raise ValueError("screenshot_blank_or_truncated")
    return hashlib.sha256(payload).hexdigest()


# Experience contract reflow width. The capture matrix records 1440, 768, and 390.
EXPERIENCE_REFLOW_WIDTH = 320
VISUAL_STATE_VARIANTS = ("loading", "empty", "error", "locked", "stale", "revoked")


def declared_visual_widths(contract: dict | None = None) -> list[dict]:
    """Capture-contract viewports plus the experience-contract 320px reflow."""

    contract = load_contract() if contract is None else contract
    widths = []
    for name, size in contract["viewports"].items():
        widths.append({"name": name, "width": int(size["width"]), "height": int(size["height"]), "source": "capture_contract"})
    widths.append({
        "name": "reflow-320",
        "width": EXPERIENCE_REFLOW_WIDTH,
        "height": 800,
        "source": "experience_contract",
    })
    return widths


def baseline_manifest() -> dict:
    return json.loads((BASELINE_DIR / "screenshot_manifest.json").read_text(encoding="utf-8"))


# Synthetic journey copy. These strings are not real people, filings, or evidence.
JOURNEY_NARRATIVE = (
    "On March 4, 2024 a fictional clerk named Alex Rivera refused a garden-level transfer "
    "after a safety report. No real person or filing is described."
)
JOURNEY_ANSWER = "Alex Rivera ended the assignment on March 4, 2024 after the safety report."
JOURNEY_REPLACEMENT = "Alex Rivera ended the assignment on March 5, 2024 after the safety report."
JOURNEY_NOTE = "Synthetic margin note. This note is not an exhibit and is not a filing."
JOURNEY_MESSAGE = "Synthetic lawyer note. Conversation only; not adopted as a fact."
JOURNEY_CITATION = "ORS 659A.030"
JOURNEY_RULE = "An employer shall not retaliate against an employee for opposing an unlawful practice."
JOURNEY_STALE = "This stale sentence must not become the fact."


def journey_case_body(case) -> dict:
    return {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "expected_case_revision": case.revision,
        "expected_revision": case.revision,
    }


def attach_private_evidence_workspace(world, root: Path):
    """Mount the qualified evidence owner on the journey app.

    The annotation store lives under the private evidence root. A note is not
    evidence until an explicit adopt, which this helper does not perform.
    """

    from integrations.evidence_workspace import EvidenceWorkspace, MemoryByteBackend

    backend = MemoryByteBackend()
    workspace = EvidenceWorkspace(
        world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        backend,
        root,
    )
    world.app.state.evidence_workspace = workspace
    world.evidence_backend = backend
    return workspace


def cited_draft_text(*, citation: str, fact: str) -> str:
    """A draft sentence that names its source. It is not a filing or a proof."""

    return (
        f"The corrected account is: {fact} "
        f"The source-bound requirement is cited as {citation}. "
        "This draft is not a court filing and is not a finding of legal sufficiency."
    )
