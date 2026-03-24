from __future__ import annotations

import anyio
import email
import email.policy
import imaplib
import json
import re
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence

from ipfs_datasets_py.processors.multimedia.email_processor import create_email_processor
from .evidence_relevance import build_complaint_terms, score_email_relevance

if TYPE_CHECKING:
    from applications.complaint_workspace import ComplaintWorkspaceService


def _slugify_fragment(value: str, *, fallback: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return text[:80] or fallback


def _normalize_addresses(addresses: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in addresses:
        value = str(item or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _extract_header_addresses(message: email.message.EmailMessage) -> set[str]:
    header_values = [
        str(message.get("From", "") or ""),
        str(message.get("To", "") or ""),
        str(message.get("Cc", "") or ""),
        str(message.get("Bcc", "") or ""),
        str(message.get("Reply-To", "") or ""),
    ]
    addresses: set[str] = set()
    for value in header_values:
        for _, addr in getaddresses([value]):
            normalized = str(addr or "").strip().lower()
            if normalized:
                addresses.add(normalized)
    return addresses


def _extract_header_addresses_from_raw(raw_message: bytes) -> set[str]:
    try:
        parsed = BytesParser(policy=policy.default).parsebytes(raw_message)
    except Exception:
        return set()
    addresses: set[str] = set()
    for header_name in ("from", "to", "cc", "bcc", "reply-to", "sender"):
        header = parsed.get(header_name)
        header_addresses = getattr(header, "addresses", ()) or ()
        for entry in header_addresses:
            username = str(getattr(entry, "username", "") or "").strip()
            domain = str(getattr(entry, "domain", "") or "").strip()
            if username and domain:
                addresses.add(f"{username}@{domain}".lower())
    return addresses


def _message_matches_addresses(message: email.message.EmailMessage, addresses: Sequence[str]) -> bool:
    if not addresses:
        return True
    header_addresses = _extract_header_addresses(message)
    return any(address in header_addresses for address in addresses)


def _extract_body_text(message: email.message.EmailMessage) -> str:
    body_parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if (part.get_content_disposition() or "").lower() == "attachment":
                continue
            if part.get_content_type() != "text/plain":
                continue
            try:
                body_parts.append(part.get_content())
            except (UnicodeDecodeError, LookupError, AttributeError):
                payload = part.get_payload(decode=True) or b""
                body_parts.append(payload.decode("utf-8", errors="ignore"))
    else:
        try:
            body_parts.append(message.get_content())
        except (UnicodeDecodeError, LookupError, AttributeError):
            payload = message.get_payload(decode=True) or b""
            body_parts.append(payload.decode("utf-8", errors="ignore"))
    return "\n".join(part.strip() for part in body_parts if str(part or "").strip()).strip()


def _extract_attachment_payloads(message: email.message.EmailMessage) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        disposition = (part.get_content_disposition() or "").lower()
        if not filename and disposition != "attachment":
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            {
                "filename": _slugify_fragment(str(filename or "attachment.bin"), fallback="attachment.bin"),
                "content_type": str(part.get_content_type() or "application/octet-stream"),
                "size": len(payload),
                "data": payload,
            }
        )
    return attachments


def _default_evidence_root(workspace_root: Path) -> Path:
    if workspace_root.name == "sessions":
        return workspace_root.parent / "evidence"
    return workspace_root / "evidence"


async def _search_message_ids(
    connection: Any,
    *,
    folder: str,
    date_after: Optional[str],
    date_before: Optional[str],
) -> list[bytes]:
    def _run() -> list[bytes]:
        status, _ = connection.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError(f"failed to open IMAP folder {folder!r}: {status}")
        criteria: list[str] = []
        if date_after:
            after_value = datetime.fromisoformat(str(date_after)).strftime("%d-%b-%Y")
            criteria.extend(["SINCE", after_value])
        if date_before:
            before_value = datetime.fromisoformat(str(date_before)).strftime("%d-%b-%Y")
            criteria.extend(["BEFORE", before_value])
        if not criteria:
            criteria = ["ALL"]
        status, data = connection.search(None, *criteria)
        if status != "OK":
            raise RuntimeError(f"failed to search IMAP folder {folder!r}: {status}")
        raw_ids = data[0] if data else b""
        return [item for item in raw_ids.split() if item]

    return await anyio.to_thread.run_sync(_run)


async def _fetch_recent_message_ids(connection: Any, *, folder: str, limit: int) -> list[bytes]:
    def _run() -> list[bytes]:
        status, count_data = connection.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError(f"failed to open IMAP folder {folder!r}: {status}")
        total_messages = int((count_data or [b"0"])[0] or b"0")
        start = max(1, total_messages - max(0, int(limit)) + 1)
        return [str(index).encode("ascii") for index in range(start, total_messages + 1)]

    return await anyio.to_thread.run_sync(_run)


async def _fetch_raw_message(connection: Any, message_id: bytes) -> bytes:
    def _run() -> bytes:
        status, data = connection.fetch(message_id, "(RFC822)")
        if status != "OK":
            raise RuntimeError(f"failed to fetch IMAP message {message_id!r}: {status}")
        for item in data or []:
            if isinstance(item, tuple) and len(item) >= 2:
                return bytes(item[1] or b"")
        raise RuntimeError(f"missing RFC822 payload for IMAP message {message_id!r}")

    return await anyio.to_thread.run_sync(_run)


async def import_gmail_evidence(
    *,
    addresses: Sequence[str],
    user_id: str,
    claim_element_id: str,
    workspace_root: str | Path = ".complaint_workspace/sessions",
    evidence_root: str | Path | None = None,
    folder: str = "INBOX",
    limit: Optional[int] = None,
    date_after: Optional[str] = None,
    date_before: Optional[str] = None,
    gmail_user: Optional[str] = None,
    gmail_app_password: Optional[str] = None,
    complaint_query: Optional[str] = None,
    complaint_keywords: Sequence[str] = (),
    complaint_keyword_files: Sequence[str] = (),
    min_relevance_score: float = 0.0,
    service: "ComplaintWorkspaceService" | None = None,
) -> dict[str, Any]:
    normalized_addresses = _normalize_addresses(addresses)
    if not normalized_addresses:
        raise ValueError("At least one target email address is required")
    complaint_terms = build_complaint_terms(
        complaint_query=complaint_query,
        complaint_keywords=complaint_keywords,
        complaint_keyword_files=complaint_keyword_files,
    )

    workspace_root_path = Path(workspace_root)
    evidence_root_path = Path(evidence_root) if evidence_root is not None else _default_evidence_root(workspace_root_path)
    if service is None:
        from applications.complaint_workspace import ComplaintWorkspaceService

        service = ComplaintWorkspaceService(root_dir=workspace_root_path)

    processor = create_email_processor(
        protocol="imap",
        server="imap.gmail.com",
        username=gmail_user,
        password=gmail_app_password,
        use_ssl=True,
    )

    artifact_root = evidence_root_path / _slugify_fragment(user_id, fallback="anonymous-user") / "gmail-import"
    artifact_root.mkdir(parents=True, exist_ok=True)

    await processor.connect()
    try:
        try:
            message_ids = await _search_message_ids(
                processor.connection,
                folder=folder,
                date_after=date_after,
                date_before=date_before,
            )
            if limit is not None and limit > 0:
                message_ids = message_ids[-int(limit) :]
        except imaplib.IMAP4.error as exc:
            if not (limit is not None and limit > 0 and "got more than 1000000 bytes" in str(exc)):
                raise
            message_ids = await _fetch_recent_message_ids(processor.connection, folder=folder, limit=int(limit))

        imported: list[dict[str, Any]] = []
        skipped_count = 0
        relevance_filtered_count = 0
        for index, message_id in enumerate(reversed(message_ids), start=1):
            raw_message = await _fetch_raw_message(processor.connection, message_id)
            parsed_message = email.message_from_bytes(raw_message, policy=email.policy.default)
            header_addresses = _extract_header_addresses(parsed_message) | _extract_header_addresses_from_raw(raw_message)
            if normalized_addresses and not any(address in header_addresses for address in normalized_addresses):
                skipped_count += 1
                continue

            subject = str(parsed_message.get("Subject") or "").strip() or "Untitled email"
            sender = str(parsed_message.get("From") or "").strip()
            recipient = str(parsed_message.get("To") or "").strip()
            email_date = str(parsed_message.get("Date") or "").strip()
            body_text = _extract_body_text(parsed_message)
            attachments = _extract_attachment_payloads(parsed_message)
            relevance = score_email_relevance(
                complaint_terms=complaint_terms,
                subject=subject,
                sender=sender,
                recipient=recipient,
                cc=str(parsed_message.get("Cc") or "").strip(),
                reply_to=str(parsed_message.get("Reply-To") or "").strip(),
                body_text=body_text,
                attachment_names=[str(item.get("filename") or "") for item in attachments],
            )
            if complaint_terms and float(relevance["score"]) < float(min_relevance_score):
                relevance_filtered_count += 1
                continue

            date_fragment = "undated"
            try:
                if email_date:
                    date_fragment = parsedate_to_datetime(email_date).strftime("%Y%m%d")
            except Exception:
                pass
            message_dir = artifact_root / f"{index:04d}_{date_fragment}_{_slugify_fragment(subject, fallback='email')}"
            message_dir.mkdir(parents=True, exist_ok=True)

            eml_path = message_dir / "message.eml"
            eml_path.write_bytes(raw_message)

            saved_attachments: list[dict[str, Any]] = []
            attachment_names: list[str] = [eml_path.name]
            attachments_dir = message_dir / "attachments"
            for attachment in attachments:
                attachments_dir.mkdir(parents=True, exist_ok=True)
                attachment_path = attachments_dir / attachment["filename"]
                attachment_path.write_bytes(bytes(attachment["data"]))
                saved_attachments.append(
                    {
                        "filename": attachment["filename"],
                        "path": str(attachment_path),
                        "content_type": attachment["content_type"],
                        "size": int(attachment["size"] or 0),
                    }
                )
                attachment_names.append(attachment["filename"])

            metadata_payload = {
                "subject": subject,
                "from": sender,
                "to": recipient,
                "cc": str(parsed_message.get("Cc") or "").strip(),
                "date": email_date,
                "message_id_header": str(parsed_message.get("Message-ID") or "").strip(),
                "matched_addresses": normalized_addresses,
                "relevance_score": float(relevance["score"]),
                "matched_terms": list(relevance["matched_terms"]),
                "matched_fields": list(relevance["matched_fields"]),
                "attachment_count": len(saved_attachments),
                "attachments": saved_attachments,
                "artifact_dir": str(message_dir),
                "eml_path": str(eml_path),
            }
            metadata_path = message_dir / "message.json"
            metadata_path.write_text(json.dumps(metadata_payload, indent=2, sort_keys=True))
            attachment_names.append(metadata_path.name)

            summary_lines = [
                f"Subject: {subject}",
                f"From: {sender}",
                f"To: {recipient}",
                f"Date: {email_date}",
                f"Matched addresses: {', '.join(normalized_addresses)}",
                f"Artifact directory: {message_dir}",
            ]
            if body_text:
                summary_lines.extend(["", body_text[:4000]])

            workspace_record = service.save_evidence(
                user_id,
                kind="document",
                claim_element_id=claim_element_id,
                title=f"Email import: {subject}",
                content="\n".join(summary_lines).strip(),
                source="gmail_imap_import",
                attachment_names=attachment_names,
            )

            imported.append(
                {
                    "message_id": message_id.decode("utf-8", errors="ignore"),
                    "subject": subject,
                    "from": sender,
                    "to": recipient,
                    "date": email_date,
                    "relevance_score": float(relevance["score"]),
                    "matched_terms": list(relevance["matched_terms"]),
                    "matched_fields": list(relevance["matched_fields"]),
                    "artifact_dir": str(message_dir),
                    "eml_path": str(eml_path),
                    "attachment_paths": [item["path"] for item in saved_attachments],
                    "workspace_evidence_id": ((workspace_record.get("saved") or {}).get("id")),
                }
            )

        return {
            "status": "success",
            "gmail_user": gmail_user or "",
            "folder": folder,
            "claim_element_id": claim_element_id,
            "user_id": user_id,
            "workspace_root": str(workspace_root_path),
            "evidence_root": str(evidence_root_path),
            "matched_addresses": normalized_addresses,
            "complaint_terms": complaint_terms,
            "min_relevance_score": float(min_relevance_score),
            "searched_message_count": len(message_ids),
            "imported_count": len(imported),
            "skipped_count": skipped_count,
            "relevance_filtered_count": relevance_filtered_count,
            "imported": imported,
        }
    finally:
        await processor.disconnect()


__all__ = ["import_gmail_evidence"]
