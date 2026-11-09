from __future__ import annotations

import importlib
import importlib.util
import sys
from email.message import EmailMessage
from pathlib import Path

import anyio


def _email_processor_module_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    current = repo_root
    while True:
        module_path = (
            current
            / "ipfs_datasets_py"
            / "ipfs_datasets_py"
            / "processors"
            / "multimedia"
            / "email_processor.py"
        )
        if module_path.is_file():
            return module_path
        if current.parent == current:
            raise FileNotFoundError("Could not locate ipfs_datasets_py email_processor.py")
        current = current.parent


module_path = _email_processor_module_path()
spec = importlib.util.spec_from_file_location("email_processor_window_module", module_path)
email_processor_module = importlib.util.module_from_spec(spec)
assert spec is not None
assert spec.loader is not None
spec.loader.exec_module(email_processor_module)
EmailProcessor = email_processor_module.EmailProcessor


def _build_email_bytes(subject: str) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = "hr@example.com"
    message["To"] = "employee@example.com"
    message["Date"] = "Tue, 23 Mar 2026 10:00:00 +0000"
    message["Message-ID"] = f"<{subject.replace(' ', '.')}@example.test>"
    message.set_content(f"Body for {subject}")
    return message.as_bytes()


class _FakeConnection:
    def __init__(self, messages: list[bytes]) -> None:
        self._messages = messages
        self.search_called = False

    def select(self, folder: str, readonly: bool = True):
        return "OK", [str(len(self._messages)).encode("ascii")]

    def search(self, charset, *criteria):
        self.search_called = True
        message_ids = b" ".join(str(index + 1).encode("ascii") for index in range(len(self._messages)))
        return "OK", [message_ids]

    def fetch(self, message_id: bytes, query: str):
        index = int(message_id.decode("ascii")) - 1
        return "OK", [(b"RFC822", self._messages[index])]

    def logout(self):
        return "BYE", [b""]


def test_fetch_imap_window_uses_recent_sequence_window_without_search():
    processor = EmailProcessor(protocol="imap", server="imap.gmail.com", username="user@gmail.com", password="app-password")
    processor.connection = _FakeConnection([
        _build_email_bytes("Oldest"),
        _build_email_bytes("Middle"),
        _build_email_bytes("Newest"),
    ])
    processor.connected = True

    async def _run_window():
        return await processor.fetch_imap_window(
            folder="INBOX",
            window_size=2,
            start_offset=0,
            include_attachments=True,
        )

    payload = anyio.run(_run_window)

    assert payload["status"] == "success"
    assert payload["email_count"] == 2
    assert [item["subject"] for item in payload["emails"]] == ["Middle", "Newest"]
    assert payload["next_start_offset"] == 2
    assert processor.connection.search_called is False
