import json
import sys
from types import SimpleNamespace

import pytest

from adversarial_harness.harness import AdversarialHarness


def test_initialize_session_databases_opens_and_closes_each_configured_path(monkeypatch):
    events = []

    class Connection:
        def __init__(self, path):
            self.path = path

        def close(self):
            events.append(("close", self.path))

    def connect(path):
        events.append(("connect", path))
        return Connection(path)

    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=connect))

    AdversarialHarness._initialize_session_databases(
        "/sessions/ref-055/evidence.duckdb",
        None,
        "/sessions/ref-055/claim-support.duckdb",
    )

    assert events == [
        ("connect", "/sessions/ref-055/evidence.duckdb"),
        ("close", "/sessions/ref-055/evidence.duckdb"),
        ("connect", "/sessions/ref-055/claim-support.duckdb"),
        ("close", "/sessions/ref-055/claim-support.duckdb"),
    ]


def test_initialize_session_databases_skips_import_when_no_paths(monkeypatch):
    monkeypatch.setitem(sys.modules, "duckdb", None)

    AdversarialHarness._initialize_session_databases(None, None, None)


def test_initialize_session_databases_does_not_swallow_connection_failure(monkeypatch):
    def connect(path):
        raise PermissionError(f"cannot create {path}")

    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=connect))

    with pytest.raises(PermissionError, match="cannot create /read-only/evidence.duckdb"):
        AdversarialHarness._initialize_session_databases("/read-only/evidence.duckdb")


def test_session_runner_records_database_initialization_failure(monkeypatch, tmp_path, caplog):
    mediator_calls = []

    def mediator_factory():
        mediator_calls.append(True)
        return object()

    harness = AdversarialHarness(
        llm_backend_complainant=object(),
        llm_backend_critic=object(),
        mediator_factory=mediator_factory,
        session_state_dir=str(tmp_path),
    )

    def fail_initialization(*database_paths):
        assert database_paths == (
            str(tmp_path / "session-ref-055" / "evidence.duckdb"),
            str(tmp_path / "session-ref-055" / "legal_authorities.duckdb"),
            str(tmp_path / "session-ref-055" / "claim_support.duckdb"),
        )
        raise PermissionError("session database directory is read-only")

    monkeypatch.setattr(harness, "_initialize_session_databases", fail_initialization)

    with caplog.at_level("ERROR", logger="adversarial_harness.harness"):
        result = harness._run_single_session(
            {
                "session_id": "session-ref-055",
                "seed": {"type": "housing_discrimination", "key_facts": {}},
                "personality": "cooperative",
                "max_turns": 1,
            }
        )

    assert result.success is False
    assert result.error == "session database directory is read-only"
    assert result.seed_complaint["type"] == "housing_discrimination"
    assert mediator_calls == []
    assert "Error running session session-ref-055" in caplog.text
    assert "PermissionError: session database directory is read-only" in caplog.text

    progress = json.loads(
        (tmp_path / "session-ref-055" / "progress.json").read_text(encoding="utf-8")
    )
    assert progress["stage"] == "failed"
    assert progress["status"] == "failed"
    assert progress["metadata"] == {"error": "session database directory is read-only"}
