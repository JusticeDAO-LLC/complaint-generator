from __future__ import annotations

from datetime import datetime
from typing import Any

from integrations.ipfs_datasets.legal_data import legal_module

_email_import = legal_module("email_import")

build_complaint_terms = _email_import.build_complaint_terms
build_xoauth2_bytes = _email_import.build_xoauth2_bytes
create_email_processor = _email_import.create_email_processor
resolve_gmail_oauth_access_token = _email_import.resolve_gmail_oauth_access_token
score_email_relevance = _email_import.score_email_relevance

_imap_mailbox_name = _email_import._imap_mailbox_name
_message_artifact_dir = _email_import._message_artifact_dir


async def _connect_processor_with_xoauth2(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return await _email_import._connect_processor_with_xoauth2(*args, **kwargs)


async def import_gmail_evidence(*args: Any, **kwargs: Any) -> dict[str, Any]:
    original_build_terms = _email_import.build_complaint_terms
    original_build_xoauth2 = _email_import.build_xoauth2_bytes
    original_create_processor = _email_import.create_email_processor
    original_datetime = _email_import.datetime
    original_connect_xoauth2 = _email_import._connect_processor_with_xoauth2
    original_resolve_oauth = _email_import.resolve_gmail_oauth_access_token
    original_score_relevance = _email_import.score_email_relevance
    _email_import.build_complaint_terms = build_complaint_terms
    _email_import.build_xoauth2_bytes = build_xoauth2_bytes
    _email_import.create_email_processor = create_email_processor
    _email_import.datetime = datetime
    _email_import._connect_processor_with_xoauth2 = _connect_processor_with_xoauth2
    _email_import.resolve_gmail_oauth_access_token = resolve_gmail_oauth_access_token
    _email_import.score_email_relevance = score_email_relevance
    try:
        return await _email_import.import_gmail_evidence(*args, **kwargs)
    finally:
        _email_import.build_complaint_terms = original_build_terms
        _email_import.build_xoauth2_bytes = original_build_xoauth2
        _email_import.create_email_processor = original_create_processor
        _email_import.datetime = original_datetime
        _email_import._connect_processor_with_xoauth2 = original_connect_xoauth2
        _email_import.resolve_gmail_oauth_access_token = original_resolve_oauth
        _email_import.score_email_relevance = original_score_relevance


__all__ = [
    "_connect_processor_with_xoauth2",
    "_imap_mailbox_name",
    "_message_artifact_dir",
    "import_gmail_evidence",
]
