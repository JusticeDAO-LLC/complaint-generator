"""Reusable guarded synthetic cases for mediator grounding tests.

Narratives, public-law bytes, and evidence markers are authored fixtures.
Session, key, index, and receipt paths stay under the caller's temporary
root. Provider executables and remote sockets are blocked. Subprocess
``Popen`` stays a real subclass of the original class. Source admission
uses the production bounded-record and source-bound extractors. These
helpers do not seed a satisfied legal graph, a fake backend, or a Native
completion. A synthetic transport record is not a live route observation.
"""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


PROVIDER_BASENAMES = frozenset({
    "grok",
    "grok-cli",
    "codex",
    "claude",
    "openai",
    "curl",
    "wget",
    "ssh",
    "nc",
    "ncat",
    "socat",
})

CASE_LABELS = (
    "baseline",
    "missing_authority",
    "contradiction",
    "unknown",
    "cancellation",
    "storage_outage",
)

PASSPHRASE = "synthetic-mgnd-04-passphrase"
USER_ID = "synthetic-mgnd-04"
_BASELINE_TEXT = "A covered employer must keep a written record of a safety report for four years."
_KEEP_TEXT = "A covered employer must retain the safety report."
_DISCARD_TEXT = "A covered employer must not retain the safety report."


@dataclass(frozen=True)
class EvidenceMarker:
    marker_id: str
    field: str
    value: str


@dataclass(frozen=True)
class AuthoredNarrative:
    narrative_id: str
    text: str
    jurisdiction: str
    event_date: str
    evidence_markers: tuple[EvidenceMarker, ...]


@dataclass(frozen=True)
class PublicLawSource:
    authority_id: str
    citation: str
    jurisdiction: str
    version: str
    law_version_id: str
    effective_date: str
    as_of_date: str
    source_bytes: bytes

    @property
    def source_text(self) -> str:
        return self.source_bytes.decode("utf-8")

    @property
    def source_sha256(self) -> str:
        return hashlib.sha256(self.source_bytes).hexdigest()


@dataclass(frozen=True)
class SyntheticCase:
    case_id: str
    label: str
    narrative: AuthoredNarrative
    sources: tuple[PublicLawSource, ...]
    outcome: str
    storage_available: bool
    notes: str


@dataclass(frozen=True)
class PrivateFixtureRoot:
    root: Path
    sessions: Path
    keys: Path
    index: Path
    receipts: Path

    def contained_paths(self) -> tuple[Path, ...]:
        return (self.sessions, self.keys, self.index, self.receipts)


@dataclass(frozen=True)
class ProviderGuard:
    original_popen: type
    guarded_popen: type


@dataclass(frozen=True)
class StorageStatus:
    available: bool
    reason: str
    live_route_observation: bool = False


@dataclass(frozen=True)
class MaterializedCase:
    case: SyntheticCase
    root: PrivateFixtureRoot
    service: Any
    terminal: Any
    storage: StorageStatus
    transport: dict[str, Any]
    admissions: tuple[dict[str, Any], ...]
    native_completion: bool = False
    legal_graph: None = None
    awaiting_user: bool = False
    worker_stalled: bool = False


def _marker(marker_id: str, field: str, value: str) -> EvidenceMarker:
    return EvidenceMarker(marker_id=marker_id, field=field, value=value)


def _law(
    authority_id: str,
    citation: str,
    text: str,
    *,
    jurisdiction: str = "US-OR",
    version: str = "2024-edition",
    effective_date: str = "2024-01-01",
    as_of_date: str = "2024-06-01",
) -> PublicLawSource:
    raw = text.encode("utf-8")
    if raw.decode("utf-8") != text:
        raise ValueError("public_law_bytes_are_not_complete")
    return PublicLawSource(
        authority_id=authority_id,
        citation=citation,
        jurisdiction=jurisdiction,
        version=version,
        law_version_id=authority_id + ":" + version,
        effective_date=effective_date,
        as_of_date=as_of_date,
        source_bytes=raw,
    )


def case_catalog() -> tuple[SyntheticCase, ...]:
    """Small authored set later modules can import."""

    baseline = SyntheticCase(
        case_id="mgnd-04-baseline",
        label="baseline",
        narrative=AuthoredNarrative(
            narrative_id="narrative-baseline",
            text=(
                "On 2024-03-04 Alex Rivera ended the warehouse job after a safety report. "
                "Evidence marker safety-report-2024-03-01 is the written report. "
                "Evidence marker jurisdiction-us-or names Oregon. "
                "Evidence marker event-date-2024-03-04 is the end date."
            ),
            jurisdiction="US-OR",
            event_date="2024-03-04",
            evidence_markers=(
                _marker("safety-report-2024-03-01", "document", "safety report"),
                _marker("jurisdiction-us-or", "jurisdiction", "US-OR"),
                _marker("event-date-2024-03-04", "event_date", "2024-03-04"),
            ),
        ),
        sources=(_law("synth-or-safety-1", "Synth. Or. Safety 1", _BASELINE_TEXT),),
        outcome="review",
        storage_available=True,
        notes="Complete local statute bytes. No legal sufficiency is claimed.",
    )
    missing = SyntheticCase(
        case_id="mgnd-04-missing-authority",
        label="missing_authority",
        narrative=AuthoredNarrative(
            narrative_id="narrative-missing-authority",
            text=(
                "On 2024-03-04 the same warehouse job ended. "
                "Evidence marker missing-authority-gap records that no statute bytes were supplied. "
                "Evidence marker event-date-2024-03-04 is the end date."
            ),
            jurisdiction="US-OR",
            event_date="2024-03-04",
            evidence_markers=(
                _marker("missing-authority-gap", "authority", "absent"),
                _marker("event-date-2024-03-04", "event_date", "2024-03-04"),
            ),
        ),
        sources=(),
        outcome="missing_authority",
        storage_available=True,
        notes="Dates and jurisdiction are present. Public-law bytes are absent.",
    )
    contradiction = SyntheticCase(
        case_id="mgnd-04-contradiction",
        label="contradiction",
        narrative=AuthoredNarrative(
            narrative_id="narrative-contradiction",
            text=(
                "The end date was recorded as 2024-03-04 and also as 2024-03-11. "
                "Evidence marker end-date-2024-03-04 and evidence marker end-date-2024-03-11 conflict."
            ),
            jurisdiction="US-OR",
            event_date="2024-03-04",
            evidence_markers=(
                _marker("end-date-2024-03-04", "event_date", "2024-03-04"),
                _marker("end-date-2024-03-11", "event_date", "2024-03-11"),
            ),
        ),
        sources=(
            _law("synth-or-retain", "Synth. Or. Retain 1", _KEEP_TEXT),
            _law("synth-or-discard", "Synth. Or. Discard 1", _DISCARD_TEXT),
        ),
        outcome="contradiction",
        storage_available=True,
        notes="Two complete local texts disagree. The fixture does not pick a winner.",
    )
    unknown = SyntheticCase(
        case_id="mgnd-04-unknown",
        label="unknown",
        narrative=AuthoredNarrative(
            narrative_id="narrative-unknown",
            text=(
                "The forum and the event date were not stated. "
                "Evidence marker unknown-jurisdiction and evidence marker unknown-event-date stay unresolved."
            ),
            jurisdiction="unknown",
            event_date="",
            evidence_markers=(
                _marker("unknown-jurisdiction", "jurisdiction", "unknown"),
                _marker("unknown-event-date", "event_date", ""),
            ),
        ),
        sources=(
            _law(
                "synth-unknown-1",
                "Synth. Unknown 1",
                _BASELINE_TEXT,
                jurisdiction="unknown",
                as_of_date="",
            ),
        ),
        outcome="unknown",
        storage_available=True,
        notes="Unknown jurisdiction and date stay unknown.",
    )
    cancellation = SyntheticCase(
        case_id="mgnd-04-cancellation",
        label="cancellation",
        narrative=AuthoredNarrative(
            narrative_id="narrative-cancellation",
            text=(
                "On 2024-03-04 the intake stopped because the operator cancelled it. "
                "Evidence marker operator-cancel records the stop. "
                "Evidence marker event-date-2024-03-04 is the end date."
            ),
            jurisdiction="US-OR",
            event_date="2024-03-04",
            evidence_markers=(
                _marker("operator-cancel", "outcome", "cancelled"),
                _marker("event-date-2024-03-04", "event_date", "2024-03-04"),
            ),
        ),
        sources=(_law("synth-or-safety-1", "Synth. Or. Safety 1", _BASELINE_TEXT),),
        outcome="cancelled",
        storage_available=True,
        notes="Cancellation is an application outcome, not a stalled worker.",
    )
    outage = SyntheticCase(
        case_id="mgnd-04-storage-outage",
        label="storage_outage",
        narrative=AuthoredNarrative(
            narrative_id="narrative-storage-outage",
            text=(
                "On 2024-03-04 the private index could not be created. "
                "Evidence marker storage-outage records the local storage failure. "
                "Evidence marker event-date-2024-03-04 is the end date."
            ),
            jurisdiction="US-OR",
            event_date="2024-03-04",
            evidence_markers=(
                _marker("storage-outage", "storage", "unavailable"),
                _marker("event-date-2024-03-04", "event_date", "2024-03-04"),
            ),
        ),
        sources=(_law("synth-or-safety-1", "Synth. Or. Safety 1", _BASELINE_TEXT),),
        outcome="storage_outage",
        storage_available=False,
        notes="The index path is a file, so directory creation fails closed.",
    )
    cases = (baseline, missing, contradiction, unknown, cancellation, outage)
    labels = tuple(case.label for case in cases)
    if labels != CASE_LABELS:
        raise RuntimeError("case_catalog_labels_drifted")
    return cases


def case_by_label(label: str) -> SyntheticCase:
    for case in case_catalog():
        if case.label == label:
            return case
    raise KeyError(label)


def _command_basename(args: tuple, kwargs: Mapping[str, Any]) -> str:
    command = args[0] if args else kwargs.get("args")
    if command is None:
        return ""
    if isinstance(command, (str, bytes)):
        token = os.fsdecode(command).split()
        token = token[0] if token else ""
    else:
        token = os.fsdecode(command[0]) if command else ""
    return Path(token).name.lower()


def install_provider_guards(monkeypatch: Any) -> ProviderGuard:
    """Block provider executables and remote sockets.

    ``subprocess.Popen`` remains a subclass of the class that was installed
    when the guard was applied. Benign commands still construct that class.
    """

    def blocked_socket(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("network socket blocked")

    monkeypatch.setattr(socket.socket, "connect", blocked_socket)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked_socket)
    monkeypatch.setattr(socket, "create_connection", blocked_socket)
    original_popen = subprocess.Popen

    class GuardedPopen(original_popen):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if _command_basename(args, kwargs) in PROVIDER_BASENAMES:
                raise RuntimeError("provider subprocess blocked")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", GuardedPopen)

    def guarded(real: Any) -> Any:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if _command_basename(args, kwargs) in PROVIDER_BASENAMES:
                raise RuntimeError("provider subprocess blocked")
            return real(*args, **kwargs)

        return wrapped

    monkeypatch.setattr(subprocess, "run", guarded(subprocess.run))
    monkeypatch.setattr(subprocess, "call", guarded(subprocess.call))
    monkeypatch.setattr(subprocess, "check_call", guarded(subprocess.check_call))
    monkeypatch.setattr(subprocess, "check_output", guarded(subprocess.check_output))
    return ProviderGuard(original_popen=original_popen, guarded_popen=GuardedPopen)


def assert_remote_socket_blocked() -> None:
    try:
        socket.create_connection(("127.0.0.1", 9), timeout=0.2)
    except RuntimeError as exc:
        if str(exc) != "network socket blocked":
            raise
        return
    raise AssertionError("remote_socket_was_not_blocked")


def synthetic_transport_record(*, case_id: str, outcome: str) -> dict[str, Any]:
    """Label a fixture transport. This is not a live Grok route observation."""

    return {
        "kind": "synthetic_private_fixture",
        "case_id": case_id,
        "outcome": outcome,
        "live_route_observation": False,
        "verifies_live_grok_identity": False,
        "native_completion": False,
        "fake_backend": False,
        "provider_reported_model": "",
        "evidence_class": "synthetic_fixture",
    }


def prepare_private_root(tmp_path: Path, *, storage_available: bool) -> PrivateFixtureRoot:
    """Create session, key, index, and receipt paths under ``tmp_path`` only."""

    root = (tmp_path / "mgnd-private").resolve()
    if not str(root).startswith(str(tmp_path.resolve())):
        raise RuntimeError("private_root_escaped_tmp")
    root.mkdir(parents=True, mode=0o700)
    sessions = root / "sessions"
    sessions.mkdir(mode=0o700)
    keys = sessions / "private-keys"
    index = root / "index"
    receipts = root / "receipts"
    receipts.mkdir(mode=0o700)
    if storage_available:
        index.mkdir(mode=0o700)
        keys.mkdir(mode=0o700)
    else:
        index.write_bytes(b"storage-outage")
        keys.mkdir(mode=0o700)
    prepared = PrivateFixtureRoot(root=root, sessions=sessions, keys=keys, index=index, receipts=receipts)
    for path in prepared.contained_paths():
        path.resolve().relative_to(root)
    return prepared


def storage_status(root: PrivateFixtureRoot) -> StorageStatus:
    if root.index.is_dir():
        return StorageStatus(available=True, reason="")
    if root.index.is_file():
        return StorageStatus(available=False, reason="storage_outage")
    return StorageStatus(available=False, reason="storage_missing")


def require_index_directory(root: PrivateFixtureRoot) -> Path:
    status = storage_status(root)
    if not status.available:
        raise OSError(status.reason or "storage_unavailable")
    return root.index


def public_service_factory(session_dir: Path) -> Any:
    """Return the real public workspace service bound to ``session_dir``."""

    from applications.complaint_workspace import ComplaintWorkspaceService

    return ComplaintWorkspaceService(root_dir=session_dir)


def terminal_factory(session_dir: Path) -> Any:
    """Return the real terminal workspace service bound to ``session_dir``."""

    from applications.complaint_cli import TerminalComplaintWorkspaceService

    return TerminalComplaintWorkspaceService(root_dir=session_dir)


def bind_private_keys(service: Any, *, user_id: str = USER_ID, passphrase: str = PASSPHRASE) -> dict[str, Any]:
    created = service.initialize_private_keys(protection="passphrase", passphrase=passphrase)
    if created.get("unlocked") is not True:
        raise RuntimeError("private_keys_unavailable:" + str(created.get("code") or created.get("status") or "locked"))
    ensured = service.ensure_private_case_key(user_id, user_id)
    if ensured.get("unlocked") is not True:
        raise RuntimeError("case_key_unavailable:" + str(ensured.get("code") or ensured.get("status") or "locked"))
    return {"store": created, "case_key": {key: value for key, value in ensured.items() if key != "data_key_id"}, "data_key_id_present": bool(ensured.get("data_key_id"))}


def source_record_payload(source: PublicLawSource) -> dict[str, Any]:
    """Build the stored-authority record the production extractor accepts.

    The payload carries bytes-derived text and hash. It does not carry a
    satisfied flag or a caller verification flag.
    """

    text = source.source_text
    if text.encode("utf-8") != source.source_bytes:
        raise ValueError("public_law_bytes_are_not_complete")
    return {
        "authority_id": source.authority_id,
        "citation": source.citation,
        "jurisdiction": source.jurisdiction,
        "authority_version": source.version,
        "source_text": text,
        "source_hash": source.source_sha256,
        "content_hash_scope": "authority_text",
        "effective_date": source.effective_date,
        "as_of_date": source.as_of_date,
        "law_version_id": source.law_version_id,
        "law_versions": [{
            "law_version_id": source.law_version_id,
            "version": source.version,
            "effective_date": source.effective_date,
            "jurisdiction": source.jurisdiction,
        }],
        "changes": [],
    }


def admit_source_record(payload: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Admit one source record through the production helpers.

    A missing record stays missing. A bounded record is passed to
    ``extract_source_bound_rule_candidates``. No legal graph is built and no
    Native completion is synthesized.
    """

    from complaint_phases.dependency_graph import DependencyGraphBuilder
    from integrations.ipfs_datasets.logic import extract_source_bound_rule_candidates

    base = {
        "legal_graph": None,
        "native_completion": False,
        "satisfied_seeded": False,
        "fake_backend": False,
        "live_route_observation": False,
    }
    if payload is None:
        return {**base, "admitted": False, "bounded": False, "reason": "missing_authority", "extraction": None}
    if not isinstance(payload, Mapping):
        return {**base, "admitted": False, "bounded": False, "reason": "source_record_malformed", "extraction": None}
    record = dict(payload)
    if "satisfied" in record or record.get("verified") is True:
        return {**base, "admitted": False, "bounded": False, "reason": "spoofed_satisfaction", "extraction": None}
    bounded = bool(DependencyGraphBuilder._bounded_source_record(record))
    if not bounded:
        return {**base, "admitted": False, "bounded": False, "reason": "source_record_unbounded", "extraction": None}
    extraction = extract_source_bound_rule_candidates(record)
    return {
        **base,
        "admitted": True,
        "bounded": True,
        "reason": "bounded_source_record",
        "extraction": extraction,
    }


def write_synthetic_receipt(root: PrivateFixtureRoot, transport: Mapping[str, Any]) -> Path:
    path = root.receipts / "synthetic-transport.json"
    import json
    path.write_text(json.dumps(dict(transport), sort_keys=True), encoding="utf-8")
    return path


def materialize_case(tmp_path: Path, monkeypatch: Any, case: SyntheticCase) -> MaterializedCase:
    """Build one guarded private case. Nothing is written outside ``tmp_path``."""

    install_provider_guards(monkeypatch)
    root = prepare_private_root(tmp_path, storage_available=case.storage_available)
    service = public_service_factory(root.sessions)
    if Path(service._session_dir) != root.sessions:
        raise RuntimeError("public_service_left_private_root")
    keys = bind_private_keys(service)
    if not keys["data_key_id_present"]:
        raise RuntimeError("case_key_id_missing")
    key_dir = Path(service._private_key_directory())
    if key_dir != root.keys or not key_dir.is_dir():
        raise RuntimeError("private_key_directory_missing")
    terminal = terminal_factory(root.sessions)
    if Path(terminal._session_dir) != root.sessions:
        raise RuntimeError("terminal_left_private_root")
    status = storage_status(root)
    if status.available != case.storage_available:
        raise RuntimeError("storage_status_disagrees_with_case")
    if status.available:
        require_index_directory(root)
    transport = synthetic_transport_record(case_id=case.case_id, outcome=case.outcome)
    write_synthetic_receipt(root, transport)
    if case.sources:
        admissions = tuple(admit_source_record(source_record_payload(source)) for source in case.sources)
    else:
        admissions = (admit_source_record(None),)
    return MaterializedCase(
        case=case,
        root=root,
        service=service,
        terminal=terminal,
        storage=status,
        transport=transport,
        admissions=admissions,
        native_completion=False,
        legal_graph=None,
        awaiting_user=False,
        worker_stalled=False,
    )


def meaningful_cases() -> tuple[SyntheticCase, ...]:
    cases = case_catalog()
    if not cases:
        raise RuntimeError("case_catalog_empty")
    return cases


def marker_values_in_narrative(narrative: AuthoredNarrative) -> Sequence[str]:
    missing = [marker.marker_id for marker in narrative.evidence_markers if marker.marker_id not in narrative.text]
    if missing:
        raise ValueError("evidence_marker_absent:" + ",".join(missing))
    return tuple(marker.marker_id for marker in narrative.evidence_markers)
