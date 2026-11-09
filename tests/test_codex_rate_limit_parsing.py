import json
import os
import pytest
from datetime import datetime, timezone

import importlib.util


def _load_codex_autopatch_module():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "examples", "codex_autopatch_from_run.py")
    spec = importlib.util.spec_from_file_location("codex_autopatch_from_run", path)
    assert spec and spec.loader, f"Failed to load spec for: {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


_codex_autopatch = _load_codex_autopatch_module()
_parse_iso_dt = _codex_autopatch._parse_iso_dt
_parse_codex_human_reset_at = _codex_autopatch._parse_codex_human_reset_at
_extract_rate_limit_reset_info = _codex_autopatch._extract_rate_limit_reset_info
_debug_extract_reset_info_from_message = _codex_autopatch._debug_extract_reset_info_from_message
_extract_first_error_message_from_exec_jsonl = _codex_autopatch._extract_first_error_message_from_exec_jsonl
_extract_rate_limit_reset_info_with_exec_fallback = _codex_autopatch._extract_rate_limit_reset_info_with_exec_fallback
_pick_reset_at_raw_from_rate_limit_artifact = _codex_autopatch._pick_reset_at_raw_from_rate_limit_artifact
_write_rate_limit_artifact_payload = _codex_autopatch._write_rate_limit_artifact_payload
_append_jsonl_best_effort = _codex_autopatch._append_jsonl_best_effort


def test_append_jsonl_best_effort_writes_event(tmp_path) -> None:
    transcript_path = tmp_path / "codex-chat.jsonl"
    event = {"event": "rate_limit", "will_retry": False}

    assert _append_jsonl_best_effort(str(transcript_path), event, event_name="rate-limit") is True
    assert json.loads(transcript_path.read_text(encoding="utf-8")) == event


def test_append_jsonl_best_effort_warns_on_expected_artifact_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_append(*_args, **_kwargs) -> None:
        raise OSError("transcript is read-only")

    monkeypatch.setattr(_codex_autopatch, "_append_jsonl", fail_append)

    assert _append_jsonl_best_effort("codex-chat.jsonl", {}, event_name="rate-limit") is False
    warning = capsys.readouterr().err
    assert "could not append rate-limit event" in warning
    assert "transcript is read-only" in warning


def test_append_jsonl_best_effort_does_not_swallow_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_append(*_args, **_kwargs) -> None:
        raise RuntimeError("unexpected transcript writer failure")

    monkeypatch.setattr(_codex_autopatch, "_append_jsonl", fail_append)

    with pytest.raises(RuntimeError, match="unexpected transcript writer failure"):
        _append_jsonl_best_effort("codex-chat.jsonl", {}, event_name="rate-limit")


def test_parse_iso_dt_rejects_malformed_provider_timestamp() -> None:
    assert _parse_iso_dt("not-an-iso-timestamp") is None


def test_parse_iso_dt_does_not_swallow_unexpected_parser_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingDateTime:
        @staticmethod
        def fromisoformat(_value: str) -> datetime:
            raise RuntimeError("unexpected datetime parser failure")

    monkeypatch.setattr(_codex_autopatch, "datetime", FailingDateTime)

    with pytest.raises(RuntimeError, match="unexpected datetime parser failure"):
        _parse_iso_dt("2026-07-22T12:00:00+00:00")


def test_parse_human_reset_at_rejects_malformed_provider_timestamp() -> None:
    assert _parse_codex_human_reset_at("try again at someday around lunch.") is None


def test_parse_human_reset_at_does_not_swallow_unexpected_parser_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingDateTime:
        @staticmethod
        def strptime(_value: str, _format: str) -> datetime:
            raise RuntimeError("unexpected datetime parser failure")

    monkeypatch.setattr(_codex_autopatch, "datetime", FailingDateTime)

    with pytest.raises(RuntimeError, match="unexpected datetime parser failure"):
        _parse_codex_human_reset_at("try again at Jul 22nd, 2026 12:00 PM.")


def test_parse_try_again_at_human_timestamp() -> None:
    def _ordinal_suffix(n: int) -> str:
        if 11 <= (n % 100) <= 13:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

    now = datetime.now(timezone.utc)
    future = datetime.fromtimestamp(now.timestamp() + 2 * 3600, tz=timezone.utc).replace(
        microsecond=0, second=0
    )
    expected_iso = future.isoformat()

    month = future.strftime("%b")
    day_i = int(future.strftime("%d"))
    day = f"{future.strftime('%d')}{_ordinal_suffix(day_i)}"
    year = future.strftime("%Y")
    time_part = future.strftime("%I:%M %p")
    human = f"{month} {day}, {year} {time_part}"

    msg = "You've hit your usage limit. Upgrade to Pro, or try again at " + human + "."
    info = _debug_extract_reset_info_from_message(msg)
    assert info["source"] == "try_again_at"
    assert info["reset_at_iso"] == expected_iso
    assert isinstance(info["resets_in_seconds"], int)
    assert info["resets_in_seconds"] > 0


def test_parse_iso_reset_at_and_derive_seconds() -> None:
    # Use a near-future timestamp so derived seconds are stable.
    now = datetime.now(timezone.utc)
    future = now.replace(microsecond=0)  # keep formatting stable
    future = future + (future - future)  # no-op to keep type checkers happy
    # Add ~30 seconds without importing timedelta to keep this test tiny.
    future = datetime.fromtimestamp(now.timestamp() + 30, tz=timezone.utc).replace(microsecond=0)

    msg = f"http 429 usage_limit reset_at={future.isoformat()}"
    info = _debug_extract_reset_info_from_message(msg)
    assert info["source"] == "reset_at"
    assert info["reset_at_iso"] == future.isoformat()
    assert isinstance(info["resets_in_seconds"], int)
    # Allow small clock skew.
    assert 0 < info["resets_in_seconds"] <= 35


def test_derive_reset_seconds_does_not_swallow_unexpected_clock_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_at = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)

    for message, expected_error, patch_parse_dt in (
        ("reset_at=2026-07-23T12:00:00+00:00", "unexpected clock failure", False),
        (
            "HTTP 429 reset_at=2026-07-22T12:00:00+00:00",
            "unexpected system clock failure",
            True,
        ),
    ):
        if patch_parse_dt:
            monkeypatch.setattr(_codex_autopatch, "_parse_iso_dt", lambda _value: reset_at)
        else:
            monkeypatch.setattr(_codex_autopatch, "_parse_iso_dt", _parse_iso_dt)

        class FailingDateTime:
            @staticmethod
            def fromisoformat(value: str) -> datetime:
                return datetime.fromisoformat(value)

            @staticmethod
            def now(_tz: timezone) -> datetime:
                raise RuntimeError(expected_error)

        monkeypatch.setattr(_codex_autopatch, "datetime", FailingDateTime)

        with pytest.raises(RuntimeError, match=expected_error):
            _extract_rate_limit_reset_info(message)


def test_parse_resets_in_seconds_jsonish() -> None:
    msg = json.dumps({"error": "usage_limit_reached", "resets_in_seconds": 123})
    info = _debug_extract_reset_info_from_message(msg)
    assert info["resets_in_seconds"] == 123


def test_parse_quota_exceeded_is_not_backoff() -> None:
    msg = "You exceeded your current quota, please check your plan and billing details."
    info = _debug_extract_reset_info_from_message(msg)
    assert info["source"] == "quota_exceeded"
    assert info["reset_at_iso"] is None
    assert info["resets_in_seconds"] is None


def test_extract_exec_error_message_tolerates_unreadable_artifact(tmp_path) -> None:
    missing_path = tmp_path / "missing.jsonl"
    invalid_utf8_path = tmp_path / "invalid-utf8.jsonl"
    invalid_utf8_path.write_bytes(b"\xff\xfe\n")

    assert _extract_first_error_message_from_exec_jsonl(str(missing_path)) is None
    assert _extract_first_error_message_from_exec_jsonl(str(invalid_utf8_path)) is None


def test_extract_exec_error_message_does_not_swallow_unexpected_open_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_open(*_args, **_kwargs):
        raise RuntimeError("unexpected artifact reader failure")

    monkeypatch.setattr("builtins.open", fail_open)

    with pytest.raises(RuntimeError, match="unexpected artifact reader failure"):
        _extract_first_error_message_from_exec_jsonl("codex_exec.jsonl")


def test_parse_real_codex_exec_jsonl_if_present() -> None:
    """Optional local test: verify parsing against a real Codex exec JSONL artifact.

    This is skipped in clean environments/CI where the artifact doesn't exist.
    """
    default_path = (
        "statefiles/_runs/autopatch_loop_0001_20260210_042146_run_00/_patches/"
        "codex_exec_gpt-5.3-codex_20260210_042449_2254399.jsonl"
    )
    jsonl_path = os.environ.get("CODEX_EXEC_JSONL_PATH", default_path)
    if not os.path.isfile(jsonl_path):
        pytest.skip(f"Codex exec JSONL not present: {jsonl_path}")

    message = None
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("type") == "error" and isinstance(obj.get("message"), str):
                message = obj["message"]
                break

    assert message, "No error.message found in JSONL"

    info = _debug_extract_reset_info_from_message(message)
    assert info["source"] in {"try_again_at", "reset_at", "resets_in_seconds"}
    # The known artifact contains a human 'try again at Feb 11th, 2026 11:46 PM' string.
    if info["source"] == "try_again_at":
        assert info["reset_at_iso"] == "2026-02-11T23:46:00+00:00"


def test_exec_jsonl_fallback_provides_reset_at() -> None:
    now = datetime.now(timezone.utc)
    future = datetime.fromtimestamp(now.timestamp() + 30, tz=timezone.utc).replace(microsecond=0)

    # Exception string lacks reset timing; exec JSONL has provider message with reset_at.
    msg = "HTTP 429 usage_limit"
    exec_jsonl = {
        "type": "error",
        "message": f"You've hit your usage limit. reset_at={future.isoformat()}"
    }

    # Write a minimal JSONL file.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "codex_exec_test.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps(exec_jsonl) + "\n")

        reset_s, reset_at, source = _extract_rate_limit_reset_info_with_exec_fallback(
            msg=msg,
            exec_jsonl_path=p,
        )
        assert source == "reset_at"
        assert isinstance(reset_at, datetime)
        assert reset_at.isoformat() == future.isoformat()
        assert isinstance(reset_s, int)
        assert 0 < reset_s <= 35


def test_exec_jsonl_fallback_provides_try_again_at_human_timestamp() -> None:
    def _ordinal_suffix(n: int) -> str:
        if 11 <= (n % 100) <= 13:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

    now = datetime.now(timezone.utc)
    # Use a near-future timestamp so derived seconds are stable.
    future = datetime.fromtimestamp(now.timestamp() + 2 * 3600, tz=timezone.utc).replace(
        microsecond=0, second=0
    )
    expected_iso = future.isoformat()

    month = future.strftime("%b")
    day_i = int(future.strftime("%d"))
    day = f"{future.strftime('%d')}{_ordinal_suffix(day_i)}"
    year = future.strftime("%Y")
    time_part = future.strftime("%I:%M %p")
    human = f"{month} {day}, {year} {time_part}"

    # Exception string lacks reset timing; exec JSONL has provider message with 'try again at ...'.
    msg = "HTTP 429 usage_limit"
    exec_jsonl = {
        "type": "error",
        "message": f"You've hit your usage limit. Upgrade to Pro, or try again at {human}.",
    }

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "codex_exec_test.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps(exec_jsonl) + "\n")

        reset_s, reset_at, source = _extract_rate_limit_reset_info_with_exec_fallback(
            msg=msg,
            exec_jsonl_path=p,
        )
        assert source == "try_again_at"
        assert isinstance(reset_at, datetime)
        assert reset_at.isoformat() == expected_iso
        assert isinstance(reset_s, int)
        assert 0 < reset_s <= 3 * 3600


def test_exec_jsonl_quota_exceeded_short_circuits() -> None:
    msg = "HTTP 429"
    exec_jsonl = {
        "type": "error",
        "message": "insufficient_quota: You exceeded your current quota, please check your plan and billing details.",
    }

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "codex_exec_test.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps(exec_jsonl) + "\n")

        reset_s, reset_at, source = _extract_rate_limit_reset_info_with_exec_fallback(
            msg=msg,
            exec_jsonl_path=p,
        )
        assert source == "quota_exceeded"
        assert reset_s is None
        assert reset_at is None


def test_pick_reset_at_prefers_provider_reset_at() -> None:
    data = {
        "reset_at": "2026-02-10T00:00:00+00:00",
        "provider_reset_at": "2026-02-11T23:46:00+00:00",
    }
    assert _pick_reset_at_raw_from_rate_limit_artifact(data) == "2026-02-11T23:46:00+00:00"


def test_write_rate_limit_artifact_payload_persists_metadata(tmp_path) -> None:
    artifact_path = tmp_path / "codex_rate_limit.json"
    payload = {"kind": "rate_limit", "will_retry": True, "sleep_seconds": 30}

    _write_rate_limit_artifact_payload(str(artifact_path), payload)

    assert json.loads(artifact_path.read_text(encoding="utf-8")) == payload


def test_write_rate_limit_artifact_payload_does_not_swallow_write_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_open(*_args, **_kwargs):
        raise OSError("rate-limit artifact is not writable")

    monkeypatch.setattr("builtins.open", fail_open)

    with pytest.raises(OSError, match="rate-limit artifact is not writable"):
        _write_rate_limit_artifact_payload("codex_rate_limit.json", {"kind": "rate_limit"})
