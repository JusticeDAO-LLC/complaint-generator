import json
from email.message import EmailMessage
from pathlib import Path

import anyio

from complaint_generator.email_import import import_gmail_evidence
from complaint_generator.workspace import ComplaintWorkspaceService


def _build_email_bytes(*, subject: str, sender: str, recipient: str, body: str, attachment_name: str | None = None, attachment_content: bytes | None = None) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message["Date"] = "Tue, 23 Mar 2026 10:00:00 +0000"
    message["Message-ID"] = f"<{subject.replace(' ', '.')}@example.test>"
    message.set_content(body)
    if attachment_name and attachment_content is not None:
        message.add_attachment(
            attachment_content,
            maintype="application",
            subtype="octet-stream",
            filename=attachment_name,
        )
    return message.as_bytes()


class _FakeConnection:
    def __init__(self, messages: list[bytes]) -> None:
        self._messages = messages

    def select(self, folder: str, readonly: bool = True):
        return "OK", [b""]

    def search(self, charset, *criteria):
        message_ids = b" ".join(str(index + 1).encode("ascii") for index in range(len(self._messages)))
        return "OK", [message_ids]

    def fetch(self, message_id: bytes, query: str):
        index = int(message_id.decode("ascii")) - 1
        return "OK", [(b"RFC822", self._messages[index])]

    def logout(self):
        return "BYE", [b""]


class _FakeProcessor:
    def __init__(self, messages: list[bytes]) -> None:
        self.connection = _FakeConnection(messages)
        self.connected = False

    async def connect(self):
        self.connected = True
        return {"status": "success"}

    async def disconnect(self):
        self.connected = False
        return {"status": "success"}


def test_import_gmail_evidence_saves_matching_emails_and_attachments(tmp_path, monkeypatch):
    matching_message = _build_email_bytes(
        subject="Termination email",
        sender="hr@example.com",
        recipient="employee@example.com",
        body="Your employment is terminated effective immediately.",
        attachment_name="termination.pdf",
        attachment_content=b"fake-pdf-bytes",
    )
    unrelated_message = _build_email_bytes(
        subject="Newsletter",
        sender="news@example.com",
        recipient="someone@example.com",
        body="This message should be skipped.",
    )

    monkeypatch.setattr(
        "complaint_generator.email_import.create_email_processor",
        lambda **kwargs: _FakeProcessor([matching_message, unrelated_message]),
    )

    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    async def _run_import():
        return await import_gmail_evidence(
            addresses=["hr@example.com", "employee@example.com"],
            user_id="case-user",
            claim_element_id="causation",
            workspace_root=workspace_root,
            evidence_root=evidence_root,
            folder="INBOX",
            limit=20,
            gmail_user="user@gmail.com",
            gmail_app_password="app-password",
            service=service,
        )

    payload = anyio.run(_run_import)

    assert payload["status"] == "success"
    assert payload["searched_message_count"] == 2
    assert payload["imported_count"] == 1
    imported = payload["imported"][0]

    message_dir = Path(imported["artifact_dir"])
    assert (message_dir / "message.eml").exists()
    assert (message_dir / "message.json").exists()
    assert (message_dir / "attachments" / "termination.pdf").read_bytes() == b"fake-pdf-bytes"

    metadata = json.loads((message_dir / "message.json").read_text())
    assert metadata["subject"] == "Termination email"
    assert metadata["matched_addresses"] == ["hr@example.com", "employee@example.com"]

    session = service.get_session("case-user")["session"]
    documents = session["evidence"]["documents"]
    assert len(documents) == 1
    assert documents[0]["title"] == "Email import: Termination email"
    assert "message.eml" in documents[0]["attachment_names"]
    assert "termination.pdf" in documents[0]["attachment_names"]
    assert "message.json" in documents[0]["attachment_names"]


def test_import_gmail_evidence_filters_by_complaint_relevance(tmp_path, monkeypatch):
    relevant_message = _build_email_bytes(
        subject="Termination hearing request",
        sender="manager@example.com",
        recipient="tenant@example.com",
        body="Retaliation and grievance hearing details are below.",
    )
    irrelevant_message = _build_email_bytes(
        subject="Weekly deals",
        sender="store@example.com",
        recipient="tenant@example.com",
        body="This message should be filtered.",
    )

    monkeypatch.setattr(
        "complaint_generator.email_import.create_email_processor",
        lambda **kwargs: _FakeProcessor([relevant_message, irrelevant_message]),
    )

    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    async def _run_import():
        return await import_gmail_evidence(
            addresses=["tenant@example.com"],
            user_id="case-user",
            claim_element_id="causation",
            workspace_root=workspace_root,
            evidence_root=evidence_root,
            folder="INBOX",
            limit=20,
            gmail_user="user@gmail.com",
            gmail_app_password="app-password",
            complaint_query="termination hearing retaliation grievance",
            min_relevance_score=2.0,
            service=service,
        )

    payload = anyio.run(_run_import)

    assert payload["searched_message_count"] == 2
    assert payload["imported_count"] == 1
    assert payload["relevance_filtered_count"] == 1
    assert payload["imported"][0]["subject"] == "Termination hearing request"
    assert payload["imported"][0]["relevance_score"] >= 2.0
