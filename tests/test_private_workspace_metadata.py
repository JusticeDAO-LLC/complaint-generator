"""Public identifiers and default logs must not carry private case metadata.

Synthetic fixtures only. Encryption is not treated as a hide-all-metadata claim.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

USER_NAME = "Jordan Hale"
CASE_NAME = "Hale v. Northwind Clinic"
COMPLAINT = "On March 3 the clinic billed Jordan Hale twice for the same visit."
FILENAME = "hale-visit-invoice.pdf"
NODE_LABEL = "double-billing-of-Jordan-Hale"
QUERY = "elements of unjust enrichment against Northwind Clinic"
TOKEN = "sk-synthetic-metadata-token-priv005"
PAYLOAD = "payload:" + COMPLAINT
KEY_TEXT = "data-key-material-should-not-leak"


def _literals() -> list[str]:
    return [USER_NAME, CASE_NAME, COMPLAINT, FILENAME, NODE_LABEL, QUERY, TOKEN, PAYLOAD, KEY_TEXT]


def _assert_absent(blob: str) -> None:
    for literal in _literals():
        assert literal not in blob


def test_public_cid_metadata_filenames_and_index_omit_private_literals() -> None:
    from integrations.ipfs_datasets.storage import (
        clear_public_index,
        opaque_storage_filename,
        project_public_cid_metadata,
        public_index_snapshot,
        publish_public_index_entry,
    )

    clear_public_index()
    raw = {
        "cid": "bafy-opaque",
        "cid_kind": "opaque",
        "artifact_class": "opaque_private_ref",
        "status": "stored",
        "user_name": USER_NAME,
        "case_name": CASE_NAME,
        "complaint_text": COMPLAINT,
        "filename": FILENAME,
        "node_label": NODE_LABEL,
        "query": QUERY,
        "token": TOKEN,
        "payload": PAYLOAD,
    }
    projected = project_public_cid_metadata(raw, sensitive_literals=_literals())
    filename = opaque_storage_filename("attachment", FILENAME)
    projected["opaque_name"] = filename
    stored = publish_public_index_entry(projected, sensitive_literals=_literals())
    blob = json.dumps({"projected": projected, "stored": stored, "index": public_index_snapshot()})
    _assert_absent(blob)
    assert FILENAME not in filename
    assert stored["artifact_class"] == "opaque_private_ref"
    assert "user_name" not in stored
    assert "query" not in stored


def test_private_diagnostics_keep_operation_identity_and_drop_secrets() -> None:
    from integrations.ipfs_datasets.llm import redact_generation_diagnostic
    from integrations.ipfs_datasets.storage import emit_default_storage_log

    record = {
        "operation_id": "store-private-artifact",
        "status": "degraded",
        "error_category": "backend_unavailable",
        "duration_ms": 18,
        "synthetic_source": "fixture-source-a",
        "payload": PAYLOAD,
        "token": TOKEN,
        "api_key": KEY_TEXT,
        "complaint_text": COMPLAINT,
        "filename": FILENAME,
        "query": QUERY,
        "user_name": USER_NAME,
    }
    diagnostic = redact_generation_diagnostic(record)
    assert diagnostic == {
        "operation_id": "store-private-artifact",
        "status": "degraded",
        "error_category": "backend_unavailable",
        "duration_ms": 18,
        "synthetic_source": "fixture-source-a",
    }
    captured: list[str] = []

    class _Handler(logging.Handler):
        def emit(self, log_record: logging.LogRecord) -> None:
            captured.append(log_record.getMessage())

    logger = logging.getLogger("integrations.ipfs_datasets.storage")
    handler = _Handler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logged = emit_default_storage_log(record)
    finally:
        logger.removeHandler(handler)
    assert logged == diagnostic
    _assert_absent("\n".join(captured))
    assert "fixture-source-a" in captured[0]
    assert "backend_unavailable" in captured[0]


def test_case_aliases_stay_encrypted_and_do_not_cross_caches() -> None:
    from integrations.ipfs_datasets.llm import (
        case_alias_cache_public_view,
        clear_case_private_caches,
        remember_case_alias,
        resolve_case_alias,
    )

    clear_case_private_caches()
    key_a = os.urandom(32)
    key_b = os.urandom(32)
    remember_case_alias(
        user_id="user-a",
        case_id="case-a",
        alias="party-1",
        canonical=USER_NAME,
        key=key_a,
        key_id="key-a",
    )
    view = case_alias_cache_public_view("user-a", "case-a")
    assert view["encrypted"] is True
    assert USER_NAME not in view["joined_ciphertext"]
    assert CASE_NAME not in view["joined_ciphertext"]
    opened = resolve_case_alias(
        user_id="user-a",
        case_id="case-a",
        alias="party-1",
        key=key_a,
        key_id="key-a",
    )
    assert opened["canonical"] == USER_NAME
    other = resolve_case_alias(
        user_id="user-b",
        case_id="case-a",
        alias="party-1",
        key=key_b,
        key_id="key-b",
    )
    assert other["found"] is False
    other_case = resolve_case_alias(
        user_id="user-a",
        case_id="case-b",
        alias="party-1",
        key=key_a,
        key_id="key-a",
    )
    assert other_case["found"] is False
    with pytest.raises(Exception):
        resolve_case_alias(
            user_id="user-a",
            case_id="case-a",
            alias="party-1",
            key=key_b,
            key_id="key-a",
        )


def test_embeddings_are_private_derived_data(tmp_path: Path) -> None:
    from applications.complaint_workspace import ComplaintWorkspaceService
    from integrations.ipfs_datasets.llm import clear_case_private_caches, open_private_embedding
    from integrations.ipfs_datasets.storage import clear_public_index, public_index_snapshot

    clear_case_private_caches()
    clear_public_index()
    key = os.urandom(32)
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    stored = service.store_case_embedding(
        "user-a",
        "case-a",
        [0.25, 0.5],
        COMPLAINT,
        key=key,
        key_id="embed-key",
        sensitive_literals=_literals(),
    )
    assert stored["classification"] == "private_derived"
    assert stored["public_index"]["classification"] == "private_derived"
    blob = json.dumps(public_index_snapshot())
    _assert_absent(blob)
    assert "0.25" not in blob
    opened = open_private_embedding(
        user_id="user-a",
        case_id="case-a",
        embedding_id=stored["embedding_id"],
        key=key,
        key_id="embed-key",
    )
    assert opened["found"] is True
    assert opened["source_text"] == COMPLAINT
    missing = open_private_embedding(
        user_id="user-b",
        case_id="case-b",
        embedding_id=stored["embedding_id"],
        key=key,
        key_id="embed-key",
    )
    assert missing["found"] is False


def test_workspace_public_reference_and_default_log(tmp_path: Path) -> None:
    from applications.complaint_workspace import ComplaintWorkspaceService
    from integrations.ipfs_datasets.storage import clear_public_index, public_index_snapshot

    clear_public_index()
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    published = service.publish_case_public_reference(
        {
            "cid": "bafy-case-ref",
            "user_name": USER_NAME,
            "case_name": CASE_NAME,
            "complaint_text": COMPLAINT,
            "node_label": NODE_LABEL,
            "query": QUERY,
            "kind": "attachment",
        },
        sensitive_literals=_literals(),
        document_filename=FILENAME,
    )
    logged = service.default_workspace_log(
        {
            "operation_id": "publish-reference",
            "status": "available",
            "error_category": "",
            "duration_ms": 4,
            "synthetic_source": "fixture-source-a",
            "complaint_text": COMPLAINT,
            "token": TOKEN,
            "filename": FILENAME,
        }
    )
    blob = json.dumps({"published": published, "index": public_index_snapshot(), "log": logged})
    _assert_absent(blob)
    assert published["filename"].endswith(".bin")
    assert FILENAME not in published["filename"]
    assert logged["synthetic_source"] == "fixture-source-a"
    assert logged["operation_id"] == "publish-reference"
    exposure = service.metadata_residual_exposure()
    text = exposure["residual_exposure"]
    assert "size" in text
    assert "timing" in text
    assert "access pattern" in text
    assert exposure["padding_policy"]["optional"] is True
    assert exposure["padding_policy"]["hides_all_metadata"] is False
    assert "not a promise" in text


def test_padding_is_optional_and_bounded() -> None:
    from integrations.ipfs_datasets.storage import (
        PADDING_POLICY,
        RESIDUAL_METADATA_EXPOSURE,
        optional_size_padding,
    )

    raw = b"abc"
    skipped = optional_size_padding(raw, enabled=False, block_size=256)
    assert skipped["applied"] is False
    assert skipped["data"] == raw
    assert skipped["policy"]["hides_all_metadata"] is False
    assert skipped["policy"]["residual_exposure"] == RESIDUAL_METADATA_EXPOSURE
    padded = optional_size_padding(raw, enabled=True, block_size=256)
    assert padded["applied"] is True
    assert len(padded["data"]) % 256 == 0
    assert padded["policy"] == PADDING_POLICY
    with pytest.raises(ValueError, match="padding_block_out_of_bounds"):
        optional_size_padding(raw, enabled=True, block_size=16)
    with pytest.raises(ValueError, match="padding_block_out_of_bounds"):
        optional_size_padding(raw, enabled=True, block_size=2 ** 20)


def test_daemon_default_log_redacts_case_material(tmp_path: Path) -> None:
    from complaint_generator.ui_optimizer_daemon import _write_status, redact_daemon_default_log
    import argparse

    log_file = tmp_path / "daemon.log"
    status_file = tmp_path / "status.json"
    pid_file = tmp_path / "daemon.pid"
    args = argparse.Namespace(
        user_id=USER_NAME,
        artifact_root=str(tmp_path),
        workspace_root=str(tmp_path),
        pytest_target="synthetic",
        max_rounds=1,
        iterations=1,
        poll_seconds=1.0,
        retry_seconds=1.0,
        max_cycles=1,
        max_consecutive_errors=1,
        method="actor_critic",
        priority=1,
        provider="",
        model="",
        use_llm_draft=False,
    )
    secret_result = {
        "draft_title": COMPLAINT,
        "markdown_export": {"filename": FILENAME},
        "summary": {"export_review_excerpt": QUERY, "node_label": NODE_LABEL},
        "token": TOKEN,
    }
    payload = _write_status(
        args=args,
        pid_file=pid_file,
        status_file=status_file,
        log_file=log_file,
        state="degraded",
        phase="export",
        cycle_count=1,
        consecutive_errors=1,
        last_result=secret_result,
        error=COMPLAINT,
        error_kind="export_failed",
        error_summary=QUERY,
        phase_started_at=None,
    )
    assert payload["status"] == "degraded"
    log_text = log_file.read_text(encoding="utf-8")
    _assert_absent(log_text)
    assert USER_NAME not in log_text
    diagnostic = redact_daemon_default_log(json.loads(log_text.strip().splitlines()[-1]))
    assert diagnostic["operation_id"] == "export"
    assert diagnostic["status"] == "degraded"
    assert diagnostic["error_category"] == "export_failed"
    assert diagnostic["synthetic_source"] == "ui-optimizer-daemon"
    query_ref_blob = log_text
    assert QUERY not in query_ref_blob


@pytest.mark.parametrize("field", ["operation_id", "status", "error_category", "synthetic_source", "source_identity"])
def test_untrusted_diagnostic_field_values_cannot_carry_private_text(field):
    from integrations.ipfs_datasets.storage import redact_private_diagnostic
    private = "private-synthetic-clinic-case"
    assert private not in json.dumps(redact_private_diagnostic({field: private}))


@pytest.mark.parametrize("field", ["cid", "cid_kind", "schema", "status", "classification", "opaque_name"])
def test_public_metadata_values_are_checked_without_sensitive_literal_hints(field):
    from integrations.ipfs_datasets.storage import project_public_cid_metadata
    private = "private-synthetic-clinic-case"
    assert private not in json.dumps(project_public_cid_metadata({field: private}))


def test_public_index_rejects_private_text_in_allowed_field_values_by_default():
    from integrations.ipfs_datasets.storage import clear_public_index, publish_public_index_entry, public_index_snapshot
    clear_public_index()
    private = "private-synthetic-clinic-case"
    result = publish_public_index_entry({name: private for name in ("cid", "status", "schema", "cid_kind", "opaque_name")})
    assert private not in json.dumps([result, public_index_snapshot()])


def test_public_filename_kind_and_repeated_name_do_not_reveal_private_filename():
    import hashlib
    from integrations.ipfs_datasets.storage import opaque_storage_filename
    private = "private-synthetic-clinic-case"
    first, second = opaque_storage_filename(private, FILENAME), opaque_storage_filename(private, FILENAME)
    assert private[:24] not in first and FILENAME not in first and first != second
    assert hashlib.sha256(FILENAME.encode()).hexdigest()[:32] not in first
    assert first.startswith("object-") and first.endswith(".bin")


def test_public_metadata_retains_valid_ciphertext_content_references():
    import base64
    import hashlib
    from integrations.ipfs_datasets.storage import project_public_cid_metadata
    digest = hashlib.sha256(b"synthetic ciphertext").digest()
    cid = "b" + base64.b32encode(b"\x01\x55\x12\x20" + digest).decode().lower().rstrip("=")
    result = project_public_cid_metadata({"cid": cid, "cid_kind": "ipfs", "status": "stored"})
    assert result["cid"] == cid and result["cid_kind"] == "ipfs" and result["status"] == "stored"
    assert "cid" not in project_public_cid_metadata({"cid": cid[:-1] + "!"})


def test_public_metadata_malformed_values_fail_closed_without_exposing_objects():
    from integrations.ipfs_datasets.storage import project_public_cid_metadata
    private = {"complaint": COMPLAINT}
    result = project_public_cid_metadata({name: private for name in ("artifact_class", "classification", "cid", "cid_kind", "status", "opaque_name")})
    _assert_absent(json.dumps(result))
    assert result["artifact_class"] == "opaque_private_ref"


def test_diagnostic_unknown_identifiers_are_opaque_and_separated_by_case():
    from integrations.ipfs_datasets.storage import redact_private_diagnostic
    record = {"operation_id": COMPLAINT, "synthetic_source": USER_NAME, "user_id": "user-a", "case_id": "case-a"}
    first = redact_private_diagnostic(record)
    assert first == redact_private_diagnostic(record)
    other = redact_private_diagnostic({**record, "case_id": "case-b"})
    assert first["operation_id"] != other["operation_id"] and first["synthetic_source"] != other["synthetic_source"]
    _assert_absent(json.dumps([first, other]))


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), -1, True, "private-duration", 10**500])
def test_diagnostic_duration_is_finite_bounded_numeric_metadata(duration):
    from integrations.ipfs_datasets.storage import redact_private_diagnostic
    value = redact_private_diagnostic({"duration_ms": duration})
    assert value["duration_ms"] is None
    json.dumps(value, allow_nan=False)


def test_diagnostic_seconds_are_reported_in_milliseconds():
    from integrations.ipfs_datasets.storage import redact_private_diagnostic
    assert redact_private_diagnostic({"phase_elapsed_seconds": 1.25})["duration_ms"] == 1250


def test_public_alias_inspection_withholds_private_scope_names_and_envelope_headers():
    from integrations.ipfs_datasets.llm import clear_case_private_caches, remember_case_alias, case_alias_cache_public_view
    clear_case_private_caches()
    user, case = "private-synthetic-user", "private-synthetic-case"
    remember_case_alias(user_id=user, case_id=case, alias="party-1", canonical=USER_NAME,
        key=os.urandom(32), key_id="private-synthetic-key-id")
    view = case_alias_cache_public_view(user, case)
    encoded = json.dumps(view)
    assert all(value not in encoded for value in (user, case, USER_NAME, "private-synthetic-key-id"))
    assert view["entry_count"] == 1 and view["encrypted"] is True


def test_public_query_references_cannot_be_matched_by_hashing_a_guessed_query():
    import hashlib
    from integrations.ipfs_datasets.llm import public_query_reference
    first, second = public_query_reference(QUERY), public_query_reference(QUERY)
    assert first["query_ref"] != second["query_ref"]
    assert first["query_ref"] != hashlib.sha256(QUERY.encode()).hexdigest()
    assert QUERY not in json.dumps([first, second])


def test_identical_private_embeddings_receive_independent_public_references():
    from integrations.ipfs_datasets.llm import clear_case_private_caches, store_private_embedding, open_private_embedding
    from integrations.ipfs_datasets.storage import clear_public_index
    clear_case_private_caches(); clear_public_index()
    key = os.urandom(32)
    kwargs = dict(user_id="user-a", case_id="case-a", vector=[0.25,0.5], source_text=COMPLAINT, key=key, key_id="key-a")
    first, second = store_private_embedding(**kwargs), store_private_embedding(**kwargs)
    assert first["embedding_id"] != second["embedding_id"]
    for stored in (first, second):
        opened = open_private_embedding(user_id="user-a", case_id="case-a", embedding_id=stored["embedding_id"], key=key, key_id="key-a")
        assert opened["vector"] == kwargs["vector"] and opened["source_text"] == COMPLAINT
