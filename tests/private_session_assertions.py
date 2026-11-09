"""Assertions for the real encrypted session formats used by terminal tests."""
from pathlib import Path
from integrations.private_storage import parse_private_envelope


def private_session_path(directory: Path, user_id: str) -> Path:
    from applications.complaint_workspace import namespace_filename
    from applications.complaint_workspace import ComplaintWorkspaceService
    joined = ComplaintWorkspaceService(root_dir=directory).joined_revision_repository(user_id, user_id) / "head.cgpe"
    if joined.is_file():
        return joined
    base = directory / namespace_filename(user_id)
    successor = base.with_name(base.name + ".cgpe")
    return successor if successor.exists() else base


def assert_private_session_frame(raw: bytes, *plaintext: str) -> None:
    assert all(value.encode() not in raw for value in plaintext)
    frame = raw
    if frame.startswith(b"CGJH\x01"):
        length = int.from_bytes(frame[5:7], "big")
        assert 0 < length <= 128
        revision = frame[7:7 + length]
        assert revision.isascii() and revision.isdigit()
        frame = frame[7 + length:]
    envelope = parse_private_envelope(frame)
    assert envelope["schema_version"] == 2
    assert len(envelope["nonce"]) == 12
    assert len(envelope["ciphertext"]) >= 16
