"""Versioned encrypt-before-addressing boundary for private workspace artifacts.

Public legal-source storage stays on ``integrations.ipfs_datasets.storage.store_bytes``
and is not reclassified as private. This module seals private bytes with
AES-256-GCM before any content identifier, hash, pin, replication, cache, or
durable journal sees them.

The wire envelope carries only opaque routing: schema version, key id, a fresh
96-bit nonce, and ciphertext (including the GCM tag). Tenant, case, principal,
artifact kind, and revision are authenticated as associated data and are not
stored beside the ciphertext. Decrypt uses the caller-expected binding, so a
whole authentic envelope from another case does not open under the caller's
binding.

Artifact sealing takes an injected per-case data key. User ownership lives in
``UserOwnedKeySession``: high-entropy master and data keys stay unwrapped only
in an unlocked session. Disk receives authenticated wrapped keys plus salt,
KDF, schema, and opaque key ids, under owner-only directory and file modes.
Wrapping is a user passphrase or an explicitly supplied OS keyring. A missing
or locked keyring is an actionable unlock state with a passphrase or recovery
import path. It never writes a raw ``.key`` file, derives a key from
machine-id, hostname, or a constant, or copies key bytes into the environment.
FILE, ENVIRONMENT, HSM, VAULT, and TPM backends stay unused.

Dependency contract (not a Kit package version):

* Root ``pyproject.toml`` and ``requirements.txt`` require ``cryptography>=41.0.0``.
* Upstream ``external/ipfs_kit_py/requirements.txt`` floors ``cryptography>=38.0.0``.
  That floor is the Kit library requirement, not the Kit release version.
* Optional ``keyring`` is declared as an extra and is not installed by default.
* ``ipfs_kit_py.aes_encryption.AESEncryption`` encrypts strings with PBKDF2 and
  has no caller associated data, so it is not the bytes contract.
* ``EncryptionManager`` plus an injected MEMORY ``KeyManager`` can apply
  AES-256-GCM with associated data, but ``EncryptedData.to_dict`` exposes
  original size and other rich fields. The canonical envelope does not
  serialize that object. Kit is not started as a daemon.

Existing sessions and artifacts are not migrated automatically. Coverage of
historical bytes is DUR002. One explicit legacy private hook artifact can be
preflighted and committed by the caller; that path does not scan sessions,
user trees, campaign artifacts, or historical qualifiers. A missing
``cryptography`` install raises ``PrivateCryptoCapabilityError`` and writes
nothing. There is no XOR, plaintext tempfile, or fake encrypted-success path.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager, ExitStack
from functools import wraps
import hashlib
import hmac
import json
import logging
import os
import re
import stat
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SCHEMA_NAME = "private-artifact-aad"
SCHEMA_VERSION = 2
ENVELOPE_AAD_DOMAIN = b"complaint-generator/private-artifact/AES-256-GCM/header@2\x00"
ENVELOPE_MAGIC = b"CGPE"
NONCE_BYTES = 12
TAG_BYTES = 16
DATA_KEY_BYTES = 32
MAX_LABEL_BYTES = 256
MAX_KEY_ID_BYTES = 128
MAX_ENVELOPE_BYTES = 8 * 1024 * 1024
ALGORITHM_NAME = "AES-256-GCM"

# Root contract versus the Kit floor. 38.0.0 is not a Kit package version.
ROOT_CRYPTOGRAPHY_SPEC = "cryptography>=41.0.0"
KIT_CRYPTOGRAPHY_FLOOR = "cryptography>=38.0.0"
KIT_CRYPTOGRAPHY_FLOOR_IS_PACKAGE_VERSION = False

_FORBIDDEN_RECEIPT_FIELDS = frozenset({
    "plaintext",
    "plaintext_length",
    "original_size",
    "size",
    "filename",
    "file_name",
    "description",
    "source_text",
    "complaint_hash",
    "content_hash",
    "name",
    "metadata",
    "content_type",
    "aad",
    "additional_authenticated_data",
    "key",
    "data_key",
    "master_key",
})


class PrivateStorageError(Exception):
    """Base error for the private artifact boundary."""

    code = "private_storage_error"
    recoverable = False

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class PrivateCryptoCapabilityError(PrivateStorageError):
    """Cryptography cannot perform AES-256-GCM. Callers can recover by retrying later.

    No ciphertext, plaintext fallback, or backend write is produced.
    """

    code = "private_crypto_unavailable"
    recoverable = True
    capability = "aes-256-gcm"

    def __init__(self, message: str = "AES-256-GCM is unavailable") -> None:
        super().__init__(message, code=self.code)


class PrivateArtifactIntegrityError(PrivateStorageError):
    """Envelope authentication, version, or structure check failed."""

    code = "private_artifact_integrity"
    recoverable = False

    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "authentication_failed")
        super().__init__(f"private artifact rejected: {self.reason}", code=self.reason)


class PrivateArtifactBindingError(PrivateStorageError):
    """Caller access does not match the expected principal and case binding."""

    code = "private_artifact_binding"
    recoverable = False

    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "binding_rejected")
        super().__init__(f"private artifact binding rejected: {self.reason}", code=self.reason)


class PrivateKeyMaterialError(PrivateStorageError):
    """Injected per-case key material is missing or the wrong width.

    This is not a license to generate or persist a key.
    """

    code = "private_key_material"
    recoverable = True

    def __init__(self, reason: str = "key_unavailable") -> None:
        self.reason = str(reason or "key_unavailable")
        super().__init__(f"private data key rejected: {self.reason}", code=self.reason)


@dataclass(frozen=True)
class PrivateArtifactBinding:
    """Caller-expected identity bound into AES-GCM associated data."""

    tenant_id: str
    case_id: str
    artifact_kind: str
    revision: str
    principal_id: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise PrivateArtifactIntegrityError("unsupported_version")
        for label in (
            self.tenant_id,
            self.case_id,
            self.artifact_kind,
            self.revision,
            self.principal_id,
        ):
            _require_label(label)


def _require_label(value: str) -> None:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise PrivateArtifactBindingError("empty_label")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise PrivateArtifactBindingError("illegal_label")
    if len(value.encode("utf-8")) > MAX_LABEL_BYTES:
        raise PrivateArtifactBindingError("label_too_long")


def canonical_associated_data(binding: PrivateArtifactBinding) -> bytes:
    """Length-prefixed associated data for the expected binding.

    The envelope does not carry this byte string. Decrypt rebuilds it from the
    caller's expected binding and passes it to AES-GCM.
    """

    if not isinstance(binding, PrivateArtifactBinding):
        raise PrivateArtifactBindingError("binding_type")
    fields: Sequence[str] = (
        SCHEMA_NAME,
        str(binding.schema_version),
        binding.tenant_id,
        binding.case_id,
        binding.principal_id,
        binding.artifact_kind,
        binding.revision,
    )
    chunks: list[bytes] = []
    for field in fields:
        raw = field.encode("utf-8")
        chunks.append(len(raw).to_bytes(4, "big"))
        chunks.append(raw)
    return b"".join(chunks)



def _envelope_associated_data(binding: PrivateArtifactBinding, header: bytes) -> bytes:
    """Version2 binds exact routing bytes as well as the caller's case context.

    Version1 did not authenticate key_id. It is rejected, never silently opened
    with the new scheme; no persisted-session migration is claimed here.
    """
    return ENVELOPE_AAD_DOMAIN + len(header).to_bytes(4, "big") + header + canonical_associated_data(binding)


def cryptography_available() -> bool:
    try:
        load_aesgcm()
    except PrivateCryptoCapabilityError:
        return False
    return True


def load_aesgcm() -> Any:
    """Return ``cryptography`` AESGCM or raise a typed capability error."""

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception as exc:
        raise PrivateCryptoCapabilityError(
            "AES-256-GCM is unavailable because the cryptography package cannot be imported"
        ) from None
    if AESGCM is None:
        raise PrivateCryptoCapabilityError("AES-256-GCM is unavailable")
    return AESGCM



def _aesgcm_context(key: bytes) -> Any:
    try:
        return load_aesgcm()(key)
    except Exception:
        raise PrivateCryptoCapabilityError("AES-256-GCM backend unavailable") from None


def _unsupported_crypto_operation(error: Exception) -> bool:
    if isinstance(error, (ImportError, NotImplementedError, PrivateCryptoCapabilityError)):
        return True
    try:
        from cryptography.exceptions import UnsupportedAlgorithm
    except Exception:
        return False
    return isinstance(error, UnsupportedAlgorithm)


def _require_data_key(key: bytes) -> bytes:
    if not isinstance(key, (bytes, bytearray)) or len(key) != DATA_KEY_BYTES:
        raise PrivateKeyMaterialError("key_width")
    return bytes(key)


def _require_key_id(key_id: str) -> bytes:
    if not isinstance(key_id, str) or key_id.strip() == "" or key_id != key_id.strip():
        raise PrivateKeyMaterialError("key_id")
    raw = key_id.encode("utf-8")
    if len(raw) > MAX_KEY_ID_BYTES or any(byte < 32 or byte > 126 for byte in raw):
        raise PrivateKeyMaterialError("key_id")
    return raw


class InjectedCaseKeyProvider:
    """In-memory map of per-tenant/case data keys supplied by the caller.

    Nothing is written to disk, the environment, or a keyring. Missing entries
    are not replaced with a generated key.
    """

    def __init__(self, material: Mapping[tuple[str, str], tuple[str, bytes]]) -> None:
        stored: dict[tuple[str, str], tuple[str, bytes]] = {}
        for pair, item in dict(material).items():
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not isinstance(item, tuple)
                or len(item) != 2
            ):
                raise PrivateKeyMaterialError("provider_entry")
            tenant, case = pair
            key_id, key = item
            _require_label(str(tenant))
            _require_label(str(case))
            key_bytes = _require_data_key(key)
            _require_key_id(str(key_id))
            stored[(str(tenant), str(case))] = (str(key_id), key_bytes)
        self._material = stored

    def resolve(self, binding: PrivateArtifactBinding) -> tuple[str, bytes]:
        found = self._material.get((binding.tenant_id, binding.case_id))
        if found is None:
            raise PrivateKeyMaterialError("key_unavailable")
        return found


def assert_access_matches_binding(access: Any, binding: PrivateArtifactBinding) -> None:
    """Require an authenticated or explicit trusted-local principal and case.

    A caller-supplied user id on some other object is not authorization. The
    access object's own principal and case must equal the expected binding.
    """

    trust = str(getattr(access, "trust", "") or "")
    if trust not in {"authenticated", "trusted_local"}:
        raise PrivateArtifactBindingError("access_denied")
    principal = getattr(access, "principal_id", None)
    case_id = getattr(access, "case_id", None)
    if not isinstance(principal, str) or principal != binding.principal_id:
        raise PrivateArtifactBindingError("principal_mismatch")
    if not isinstance(case_id, str) or case_id != binding.case_id:
        raise PrivateArtifactBindingError("case_mismatch")


def seal_private_artifact(
    plaintext: bytes,
    *,
    binding: PrivateArtifactBinding,
    key: bytes,
    key_id: str,
) -> bytes:
    """Encrypt ``plaintext`` into a versioned opaque envelope. No I/O."""

    if not isinstance(plaintext, (bytes, bytearray)):
        raise PrivateArtifactIntegrityError("malformed")
    payload = bytes(plaintext)
    overhead = len(ENVELOPE_MAGIC) + 2 + MAX_KEY_ID_BYTES + NONCE_BYTES + TAG_BYTES
    if len(payload) > MAX_ENVELOPE_BYTES - overhead:
        raise PrivateArtifactIntegrityError("oversized")
    key_bytes = _require_data_key(key)
    key_id_raw = _require_key_id(key_id)
    cipher = _aesgcm_context(key_bytes)
    try:
        nonce = os.urandom(NONCE_BYTES)
    except Exception:
        raise PrivateCryptoCapabilityError("AES-256-GCM secure nonce source unavailable") from None
    if not isinstance(nonce, bytes) or len(nonce) != NONCE_BYTES:
        raise PrivateCryptoCapabilityError("AES-256-GCM nonce source failed")
    header = ENVELOPE_MAGIC + bytes((SCHEMA_VERSION, len(key_id_raw))) + key_id_raw
    associated = _envelope_associated_data(binding, header)
    try:
        ciphertext = cipher.encrypt(nonce, payload, associated)
    except Exception:
        raise PrivateCryptoCapabilityError("AES-256-GCM encrypt failed") from None
    if not isinstance(ciphertext, (bytes, bytearray)) or len(ciphertext) < TAG_BYTES:
        raise PrivateCryptoCapabilityError("AES-256-GCM encrypt returned no ciphertext")
    envelope = b"".join((
        header,
        nonce,
        bytes(ciphertext),
    ))
    if len(envelope) > MAX_ENVELOPE_BYTES:
        raise PrivateArtifactIntegrityError("oversized")
    return envelope


def open_private_artifact(
    envelope: bytes,
    *,
    binding: PrivateArtifactBinding,
    key: bytes,
    expected_key_id: str | None = None,
) -> bytes:
    """Decrypt using caller-expected associated data. Stored headers are not trusted as AAD."""

    parsed = parse_private_envelope(envelope)
    if expected_key_id is not None and parsed["key_id"] != expected_key_id:
        raise PrivateArtifactIntegrityError("authentication_failed")
    key_bytes = _require_data_key(key)
    cipher = _aesgcm_context(key_bytes)
    header = bytes(envelope)[:6 + len(parsed["key_id"].encode("ascii"))]
    associated = _envelope_associated_data(binding, header)
    try:
        plaintext = cipher.decrypt(parsed["nonce"], parsed["ciphertext"], associated)
    except Exception as exc:
        if _unsupported_crypto_operation(exc):
            raise PrivateCryptoCapabilityError("AES-256-GCM decrypt unavailable") from None
        raise PrivateArtifactIntegrityError("authentication_failed") from None
    if not isinstance(plaintext, (bytes, bytearray)):
        raise PrivateArtifactIntegrityError("authentication_failed")
    return bytes(plaintext)


def parse_private_envelope(envelope: bytes) -> dict[str, Any]:
    """Split opaque routing fields. Does not decrypt or return associated data."""

    if not isinstance(envelope, (bytes, bytearray)):
        raise PrivateArtifactIntegrityError("malformed")
    blob = bytes(envelope)
    if len(blob) > MAX_ENVELOPE_BYTES:
        raise PrivateArtifactIntegrityError("oversized")
    minimum = len(ENVELOPE_MAGIC) + 2 + 1 + NONCE_BYTES + TAG_BYTES
    if len(blob) < minimum:
        raise PrivateArtifactIntegrityError("malformed")
    if blob[: len(ENVELOPE_MAGIC)] != ENVELOPE_MAGIC:
        raise PrivateArtifactIntegrityError("malformed")
    version = blob[4]
    if version != SCHEMA_VERSION:
        raise PrivateArtifactIntegrityError("unsupported_version")
    key_id_len = blob[5]
    if key_id_len < 1 or key_id_len > MAX_KEY_ID_BYTES:
        raise PrivateArtifactIntegrityError("malformed")
    cursor = 6
    key_id_end = cursor + key_id_len
    nonce_end = key_id_end + NONCE_BYTES
    if nonce_end + TAG_BYTES > len(blob):
        raise PrivateArtifactIntegrityError("malformed")
    try:
        key_id = blob[cursor:key_id_end].decode("ascii")
    except UnicodeDecodeError as exc:
        raise PrivateArtifactIntegrityError("malformed") from exc
    _require_key_id(key_id)
    nonce = blob[key_id_end:nonce_end]
    ciphertext = blob[nonce_end:]
    return {
        "schema_version": version,
        "key_id": key_id,
        "nonce": nonce,
        "ciphertext": ciphertext,
    }


def _resolve_key(
    binding: PrivateArtifactBinding,
    *,
    key: bytes | None,
    key_id: str | None,
    key_provider: InjectedCaseKeyProvider | None,
) -> tuple[str, bytes]:
    if key is not None or key_id is not None:
        if key is None or key_id is None:
            raise PrivateKeyMaterialError("key_unavailable")
        if key_provider is not None:
            provided_id, provided_key = key_provider.resolve(binding)
            if provided_id != key_id or provided_key != _require_data_key(key):
                raise PrivateKeyMaterialError("key_mismatch")
        return key_id, _require_data_key(key)
    if key_provider is None:
        raise PrivateKeyMaterialError("key_unavailable")
    return key_provider.resolve(binding)


def _opaque_receipt(*, cid: str, key_id: str, pinned: bool, status: str) -> dict[str, Any]:
    receipt = {
        "status": status,
        "cid": cid,
        "schema_version": SCHEMA_VERSION,
        "key_id": key_id,
        "algorithm": ALGORITHM_NAME,
        "pinned": bool(pinned),
        "private_artifact": True,
    }
    leaked = _FORBIDDEN_RECEIPT_FIELDS.intersection(receipt)
    if leaked:
        raise PrivateArtifactIntegrityError("malformed")
    return receipt


def store_private_artifact(
    data: bytes,
    *,
    access: Any,
    tenant_id: str,
    case_id: str,
    artifact_kind: str,
    revision: str,
    principal_id: str | None = None,
    key: bytes | None = None,
    key_id: str | None = None,
    key_provider: InjectedCaseKeyProvider | None = None,
    backend: Any = None,
    backend_name: str | None = None,
    pin_content: bool = True,
    replicate: Callable[[bytes], None] | None = None,
    journal: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Seal ``data`` and only then address, pin, replicate, cache, or journal it.

    ``store_bytes`` remains the public plaintext path. This function never
    writes the original bytes, a raw key, or an unencrypted tempfile.
    """

    load_aesgcm()
    binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=artifact_kind,
        revision=revision,
        principal_id=principal_id if principal_id is not None else tenant_id,
    )
    assert_access_matches_binding(access, binding)
    resolved_id, resolved_key = _resolve_key(
        binding, key=key, key_id=key_id, key_provider=key_provider
    )
    envelope = seal_private_artifact(
        data, binding=binding, key=resolved_key, key_id=resolved_id
    )
    from integrations.ipfs_datasets.storage import retrieve_bytes, store_bytes

    stored = store_bytes(
        envelope,
        pin_content=pin_content,
        backend=backend,
        backend_name=backend_name,
    )
    status = str(stored.get("status") or "error")
    cid = str(stored.get("cid") or "")
    if status not in {"available", "degraded"} or not cid:
        raise PrivateStorageError(
            "private artifact backend rejected ciphertext",
            code="backend_rejected",
        )
    loaded = retrieve_bytes(cid, backend=backend, backend_name=backend_name)
    readback = loaded.get("data")
    if loaded.get("status") not in {"available", "degraded"} or not isinstance(readback, (bytes, bytearray)) or bytes(readback) != bytes(envelope):
        raise PrivateStorageError(
            "private artifact ciphertext readback mismatch",
            code="readback_mismatch",
        )
    local_only = bool(stored.get("stored_local")) or stored.get("cid_kind") in {"pseudo_cid", "sha256_fallback"}
    pinned = bool(stored.get("pinned") is True) and not local_only
    if replicate is not None:
        replicate(envelope)
    receipt = _opaque_receipt(
        cid=cid,
        key_id=resolved_id,
        pinned=pinned,
        status=status,
    )
    receipt["stored_local"] = bool(stored.get("stored_local"))
    receipt["uploaded"] = bool(stored.get("uploaded")) and not local_only
    receipt["verified"] = True
    receipt["replicated"] = False
    receipt["deferred"] = bool(stored.get("deferred"))
    receipt["backend"] = str(stored.get("backend_name") or "")
    receipt["verification"] = {"matched": True, "method": "ciphertext-readback"}
    receipt["receipt"] = {
        "cid": cid,
        "backend_name": receipt["backend"],
        "cid_kind": stored.get("cid_kind") or "",
        "network_durable": bool(stored.get("network_durable")) and pinned and not local_only,
        "measurement": stored.get("measurement") or "",
    }
    if journal is not None:
        journal(dict(receipt))
    return receipt


def retrieve_private_artifact(
    cid: str,
    *,
    access: Any,
    tenant_id: str,
    case_id: str,
    artifact_kind: str,
    revision: str,
    principal_id: str | None = None,
    key: bytes | None = None,
    key_id: str | None = None,
    key_provider: InjectedCaseKeyProvider | None = None,
    backend: Any = None,
    backend_name: str | None = None,
) -> dict[str, Any]:
    """Load ciphertext by CID and open it only for the caller-expected binding."""

    load_aesgcm()
    if not isinstance(cid, str) or not cid:
        raise PrivateArtifactIntegrityError("malformed")
    binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=artifact_kind,
        revision=revision,
        principal_id=principal_id if principal_id is not None else tenant_id,
    )
    assert_access_matches_binding(access, binding)
    resolved_id, resolved_key = _resolve_key(
        binding, key=key, key_id=key_id, key_provider=key_provider
    )
    from integrations.ipfs_datasets.storage import retrieve_bytes

    loaded = retrieve_bytes(cid, backend=backend, backend_name=backend_name)
    status = str(loaded.get("status") or "error")
    blob = loaded.get("data")
    if status not in {"available", "degraded"} or not isinstance(blob, (bytes, bytearray)):
        raise PrivateStorageError("private artifact ciphertext is unavailable", code="backend_rejected")
    plaintext = open_private_artifact(
        bytes(blob),
        binding=binding,
        key=resolved_key,
        expected_key_id=resolved_id,
    )
    return {
        "status": "available",
        "cid": cid,
        "data": plaintext,
        "schema_version": SCHEMA_VERSION,
        "key_id": resolved_id,
        "algorithm": ALGORITHM_NAME,
        "private_artifact": True,
    }


def kit_crypto_contract() -> dict[str, Any]:
    """Document the Kit versus root cryptography contract without starting Kit."""

    return {
        "root_cryptography_spec": ROOT_CRYPTOGRAPHY_SPEC,
        "kit_cryptography_floor": KIT_CRYPTOGRAPHY_FLOOR,
        "kit_cryptography_floor_is_package_version": KIT_CRYPTOGRAPHY_FLOOR_IS_PACKAGE_VERSION,
        "canonical_algorithm": ALGORITHM_NAME,
        "canonical_implementation": "cryptography.hazmat.primitives.ciphers.aead.AESGCM",
        "aes_encryption_string_api_sufficient": False,
        "encrypted_data_to_dict_used_on_wire": False,
        "key_storage_backends_used": ["injected-memory"],
        "key_storage_backends_rejected": ["file", "environment", "hsm", "vault", "tpm"],
        "keyring_installed_by_default": False,
        "default_key_generated": False,
        "historical_sessions_migrated": False,
        "migration_task": "CIMP-DUR-002",
    }


def kit_memory_gcm_associated_data_probe(
    plaintext: bytes,
    key: bytes,
    associated: bytes,
) -> dict[str, Any]:
    """Optional probe of Kit's MEMORY EncryptionManager. Not used for the envelope.

    Failure or absence is a compatibility note. It does not authorize XOR,
    ``AESEncryption``, rich ``to_dict`` persistence, or a successful private store.
    """

    report: dict[str, Any] = {
        "status": "unavailable",
        "passed": False,
        "substitutes_for_first_party": False,
        "used_on_canonical_envelope": False,
        "reason": "",
    }
    try:
        from ipfs_kit_py.mcp.enterprise.encryption import (
            EncryptionAlgorithm,
            EncryptionManager,
            KeyManager,
            KeyStorageType,
            KeyType,
        )
    except Exception as exc:
        report["reason"] = f"kit encryption manager import failed: {type(exc).__name__}"
        return report
    try:
        manager_key = KeyManager(storage_type=KeyStorageType.MEMORY)
        metadata = manager_key.generate_key(
            KeyType.DATA,
            EncryptionAlgorithm.AES_256_GCM,
            description="probe",
        )
        key_id = str(metadata.id)
        manager_key._key_cache[key_id] = _require_data_key(key)
        encrypted = EncryptionManager(manager_key).encrypt(
            bytes(plaintext),
            key_id=key_id,
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            additional_authenticated_data=bytes(associated),
        )
        opened = EncryptionManager(manager_key).decrypt(encrypted)
        rich = encrypted.to_dict()
        report["rich_to_dict_has_original_size"] = "original_size" in rich
        report["opened"] = opened == bytes(plaintext)
        report["status"] = "qualified" if opened == bytes(plaintext) else "failed"
        report["passed"] = False
        report["reason"] = (
            "Kit MEMORY AES-256-GCM accepts associated data, but EncryptedData.to_dict "
            "is richer than the private envelope and is not the canonical wire format. "
            "AESEncryption remains insufficient because it has no caller associated data."
        )
    except Exception as exc:
        report["status"] = "unavailable"
        report["passed"] = False
        report["reason"] = f"kit memory probe failed: {type(exc).__name__}"
    return report


KEY_STORE_SCHEMA = "complaint-generator/private-key-store"
KEY_STORE_VERSION = 1
KEY_RECOVERY_SCHEMA = "complaint-generator/private-key-recovery"
KEY_RECOVERY_VERSION = 1
KEY_STORE_FILENAME = "keystore.json"
PORTABILITY_SCHEMA = "complaint-generator/private-workspace-export"
PORTABILITY_VERSION = 1
ROTATION_SCHEMA = "complaint-generator/private-key-rotation"
ROTATION_VERSION = 1
WRAP_ROTATION_PHASES = ("prepared", "candidate", "committed")
DATA_ROTATION_PHASES = ("prepared", "sealed", "committed")
RETENTION_POLICIES = ("retain", "revoke_after_verified_migration")
UNRECOVERED_KEY_EXPLANATION = (
    "An unrecovered encryption key cannot be reconstructed by the system. "
    "Encrypted state was not reset."
)
_PORTABILITY_LOG = logging.getLogger("integrations.private_storage.portability")
MASTER_WRAP_AAD = b"complaint-generator/private-key/master-wrap@1\x00"
DATA_WRAP_DOMAIN = b"complaint-generator/private-key/data-wrap@1\x00"
RECOVERY_WRAP_DOMAIN = b"complaint-generator/private-key/recovery@1\x00"
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
_KEYRING_SERVICE = "complaint-generator.private-keys"
_RECEIPT_FIELDS = (
    "status",
    "code",
    "protection",
    "unlocked",
    "actions",
    "message",
    "awaiting_user",
    "worker_may_continue",
    "worker_state",
    "unlock_is_remote_consent",
    "cloud_processing_enabled",
    "overwrites_encrypted_state",
    "raw_key_persisted",
    "protection_downgrade",
    "case_count",
    "invented_key",
    "privacy_bypassed",
    "deliberate_export",
    "automatic_backup",
    "operation",
    "rotation_phase",
    "reencrypt",
    "previous_wrapping_retained",
    "previous_data_key_retained",
    "data_key_changed",
    "recovery_separated",
    "unwrapped_master_included",
    "manifest_version",
    "revision",
    "imported",
    "data_reset",
    "keys_reconstructed",
    "retention_policy",
    "revoked",
    "verified_backup_migration",
    "only_recovery_path_erased",
)


class PrivatePortabilityError(PrivateStorageError):
    """Export, import, or rotation failed without resetting encrypted state."""

    def __init__(self, message: str, *, code: str, actions: Sequence[str] = ("retry", "recovery_import")) -> None:
        super().__init__(str(message), code=code)
        self.message = str(message)
        self.actions = tuple(actions)
        self.data_reset = False
        self.keys_reconstructed = False
        self.overwrites_encrypted_state = False

    def public_state(self) -> dict[str, Any]:
        return {
            "status": "portability_failed",
            "code": self.code,
            "message": self.message,
            "actions": list(self.actions),
            "awaiting_user": True,
            "worker_may_continue": True,
            "worker_state": "ready_for_independent_tasks",
            "data_reset": False,
            "keys_reconstructed": False,
            "overwrites_encrypted_state": False,
            "raw_key_persisted": False,
            "unwrapped_master_included": False,
            "only_recovery_path_erased": False,
            "cloud_processing_enabled": False,
            "unlock_is_remote_consent": False,
        }


class PrivateKeyLockedError(PrivateKeyMaterialError):
    """Existing wrapped keys cannot be used or replaced until the user unlocks.

    The coding supervisor is not asked to invent a key. Independent work can
    continue while this state is waiting on the user.
    """

    def __init__(
        self,
        message: str,
        *,
        actions: Sequence[str],
        protection: str | None = None,
        code: str = "unlock_needed",
    ) -> None:
        super().__init__(code)
        self.message = str(message)
        self.actions = tuple(actions)
        self.protection = protection
        self.public_code = code

    def public_state(self) -> dict[str, Any]:
        return _public_key_state(
            status="unlock_needed" if self.public_code == "unlock_needed" else "keyring_unavailable",
            code=self.public_code,
            protection=self.protection,
            unlocked=False,
            actions=self.actions,
            message=self.message,
            awaiting_user=True,
        )


def _public_key_state(
    *,
    status: str,
    code: str,
    protection: str | None,
    unlocked: bool,
    actions: Sequence[str],
    message: str,
    awaiting_user: bool,
    case_count: int = 0,
) -> dict[str, Any]:
    return {
        "status": status,
        "code": code,
        "protection": protection,
        "unlocked": unlocked,
        "actions": list(actions),
        "message": message,
        "awaiting_user": awaiting_user,
        "worker_may_continue": True,
        "worker_state": "ready_for_independent_tasks",
        "unlock_is_remote_consent": False,
        "cloud_processing_enabled": False,
        "overwrites_encrypted_state": False,
        "raw_key_persisted": False,
        "protection_downgrade": False,
        "case_count": case_count,
        "invented_key": False,
        "privacy_bypassed": False,
    }


def task_key_receipt(state: Mapping[str, Any]) -> dict[str, Any]:
    """Fields safe for a task receipt. Passphrases and key bytes are omitted."""

    receipt = {field: state[field] for field in _RECEIPT_FIELDS if field in state}
    leaked = {"passphrase", "password", "master_key", "data_key", "wrapping_key", "salt", "ciphertext"}
    if leaked.intersection(receipt):
        raise PrivateKeyMaterialError("receipt_leak")
    return receipt


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise PrivateArtifactIntegrityError("malformed")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise PrivateArtifactIntegrityError("malformed") from exc


def _random_secret() -> bytes:
    try:
        material = os.urandom(DATA_KEY_BYTES)
    except Exception as exc:
        raise PrivateCryptoCapabilityError("secure random source unavailable") from exc
    if not isinstance(material, bytes) or len(material) != DATA_KEY_BYTES or material == bytes(DATA_KEY_BYTES):
        raise PrivateCryptoCapabilityError("secure random source failed")
    return material


def _opaque_key_id(prefix: str) -> str:
    return prefix + os.urandom(16).hex()


def _require_passphrase(passphrase: Any) -> str:
    if not isinstance(passphrase, str) or passphrase == "":
        raise PrivateKeyMaterialError("passphrase_required")
    return passphrase


def _kdf_bytes(passphrase: str, salt: bytes) -> bytes:
    _require_passphrase(passphrase)
    if not isinstance(salt, bytes) or len(salt) < 16:
        raise PrivateArtifactIntegrityError("malformed")
    try:
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except Exception as exc:
        raise PrivateCryptoCapabilityError("scrypt is unavailable") from exc
    try:
        derived = Scrypt(salt=salt, length=DATA_KEY_BYTES, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(
            passphrase.encode("utf-8")
        )
    except Exception as exc:
        raise PrivateCryptoCapabilityError("scrypt failed") from exc
    return _require_data_key(derived)


def _wrap_secret(wrapping_key: bytes, plaintext: bytes, aad: bytes) -> dict[str, str]:
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = _aesgcm_context(wrapping_key).encrypt(nonce, plaintext, aad)
    return {"nonce": _b64e(nonce), "ciphertext": _b64e(ciphertext)}


def _unwrap_secret(wrapping_key: bytes, wrapped: Mapping[str, Any], aad: bytes) -> bytes:
    if not isinstance(wrapped, Mapping):
        raise PrivateArtifactIntegrityError("malformed")
    nonce = _b64d(str(wrapped.get("nonce") or ""))
    ciphertext = _b64d(str(wrapped.get("ciphertext") or ""))
    if len(nonce) != NONCE_BYTES or len(ciphertext) < TAG_BYTES:
        raise PrivateArtifactIntegrityError("malformed")
    try:
        opened = _aesgcm_context(wrapping_key).decrypt(nonce, ciphertext, aad)
    except Exception as exc:
        raise PrivateArtifactIntegrityError("authentication_failed") from exc
    return _require_data_key(opened)


def _data_aad(tenant_id: str, case_id: str, key_id: str) -> bytes:
    _require_label(tenant_id)
    _require_label(case_id)
    _require_key_id(key_id)
    return DATA_WRAP_DOMAIN + tenant_id.encode("utf-8") + b"\x00" + case_id.encode("utf-8") + b"\x00" + key_id.encode("utf-8")


def _recovery_aad(tenant_id: str, case_id: str, key_id: str) -> bytes:
    return RECOVERY_WRAP_DOMAIN + _data_aad(tenant_id, case_id, key_id)


RESOURCE_GRANT_SCHEMA = "complaint-generator/resource-key-grant"
RESOURCE_GRANT_VERSION = 1
RESOURCE_GRANT_WRAP_DOMAIN = b"complaint-generator/private-key/resource-grant@1\x00"
RECIPIENT_WRAP_DOMAIN = b"complaint-generator/private-key/recipient-wrap@1\x00"


def _recipient_wrap_aad(wrap_key_id: str) -> bytes:
    _require_key_id(wrap_key_id)
    return RECIPIENT_WRAP_DOMAIN + wrap_key_id.encode("utf-8")


def resource_grant_associated_data(
    *,
    tenant_id: str,
    case_id: str,
    canonical_principal_id: str,
    revision: str,
    recipient_principal_id: str,
    artifact_kind: str,
    resource_id: str,
    membership_grant_id: str,
    membership_version: int,
    data_key_id: str,
    recipient_wrap_key_id: str,
) -> bytes:
    """AAD for a recipient-wrapped case key.

    The authenticated actor is not a field. The principal is the canonical
    artifact owner, which is the case tenant, plus the recipient who may unwrap.
    """

    if type(membership_version) is not int or membership_version < 1:
        raise PrivateArtifactBindingError("revision")
    if canonical_principal_id != tenant_id:
        raise PrivateArtifactBindingError("canonical_owner")
    fields = (
        RESOURCE_GRANT_SCHEMA,
        str(RESOURCE_GRANT_VERSION),
        tenant_id,
        case_id,
        canonical_principal_id,
        revision,
        recipient_principal_id,
        artifact_kind,
        resource_id,
        membership_grant_id,
        str(membership_version),
        data_key_id,
        recipient_wrap_key_id,
    )
    chunks = [RESOURCE_GRANT_WRAP_DOMAIN]
    for field in fields:
        if field in {data_key_id, recipient_wrap_key_id}:
            raw = _require_key_id(field)
        else:
            _require_label(field)
            raw = field.encode("utf-8")
        chunks.append(len(raw).to_bytes(4, "big"))
        chunks.append(raw)
    return b"".join(chunks)


def wrap_resource_key_for_recipient(
    data_key: bytes,
    recipient_wrap_key: bytes,
    associated_data: bytes,
) -> dict[str, str]:
    """Wrap a case data key to a recipient wrap key. The data key is not returned."""

    key_bytes = _require_data_key(data_key)
    wrap_key = _require_data_key(recipient_wrap_key)
    if wrap_key == key_bytes:
        raise PrivateKeyMaterialError("owner_key_not_a_grant")
    if not isinstance(associated_data, (bytes, bytearray)) or len(associated_data) < len(RESOURCE_GRANT_WRAP_DOMAIN):
        raise PrivateArtifactBindingError("grant_aad")
    if not bytes(associated_data).startswith(RESOURCE_GRANT_WRAP_DOMAIN):
        raise PrivateArtifactBindingError("grant_aad")
    wrapped = _wrap_secret(wrap_key, key_bytes, bytes(associated_data))
    return {"nonce": wrapped["nonce"], "ciphertext": wrapped["ciphertext"]}


def unwrap_resource_key_for_recipient(
    wrapped: Mapping[str, Any],
    recipient_wrap_key: bytes,
    associated_data: bytes,
) -> bytes:
    """Open a recipient-bound wrap. A master key or browser key is not accepted here."""

    wrap_key = _require_data_key(recipient_wrap_key)
    if not isinstance(associated_data, (bytes, bytearray)) or not bytes(associated_data).startswith(RESOURCE_GRANT_WRAP_DOMAIN):
        raise PrivateArtifactBindingError("grant_aad")
    return _unwrap_secret(wrap_key, wrapped, bytes(associated_data))


def _kdf_metadata(salt: bytes) -> dict[str, Any]:
    return {
        "name": "scrypt",
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "length": DATA_KEY_BYTES,
        "salt": _b64e(salt),
    }


def _reject_secret_path(path: Path) -> None:
    name = path.name.lower()
    if name.endswith(".key") or name in {"master.key", "data.key"}:
        raise PrivateKeyMaterialError("raw_key_path")
    lowered = {part.lower() for part in path.parts}
    if "backups" in lowered or "backup" in lowered:
        raise PrivateKeyMaterialError("recovery_is_not_a_backup")


def _assert_owner_mode(path: Path, expected: int) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != expected:
        raise PrivateKeyMaterialError("permissions")


def _write_private_bytes(path: Path, payload: bytes, *, protect_parent: bool) -> None:
    _reject_secret_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if protect_parent:
        os.chmod(path.parent, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = payload
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PrivateStorageError("key store write failed", code="key_store_io")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)
    if protect_parent:
        _assert_owner_mode(path.parent, 0o700)
    _assert_owner_mode(path, 0o600)


def _read_private_bytes(path: Path) -> bytes:
    _assert_owner_mode(path.parent, 0o700)
    _assert_owner_mode(path, 0o600)
    return path.read_bytes()


def _key_session_operation(*, authenticate: bool = True):
    """Serialize a session operation and refresh its authenticated disk state."""
    def decorate(function):
        @wraps(function)
        def invoke(self, *args, **kwargs):
            with self._key_operation(authenticate=authenticate):
                return function(self, *args, **kwargs)
        return invoke
    return decorate


_CASE_EPOCH_LOCKS: dict[tuple[int, str], threading.RLock] = {}
_CASE_EPOCH_LOCKS_GUARD = threading.Lock()
_CASE_EPOCH_HELD = threading.local()


class UserOwnedKeySession:
    """Passphrase- or keyring-wrapped master key with per-case data keys.

    Unwrapped keys exist only in this object. ``lock`` drops them. A fresh
    process starts locked. Creating or importing over an existing store while
    locked is refused.
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        _reject_secret_path(self.directory)
        self.path = self.directory / KEY_STORE_FILENAME
        self._document: dict[str, Any] | None = None
        self._master: bytes | None = None
        self._master_id: str | None = None
        self._data_keys: dict[tuple[str, str], tuple[str, bytes]] = {}
        self._retained_data_keys: dict[tuple[str, str], list[tuple[str, bytes]]] = {}
        self._pending_data_keys: dict[tuple[str, str], tuple[str, bytes]] = {}
        self._recipient_wrap: tuple[str, bytes] | None = None
        self._case_grant_state = {"schema": "case-grant-key-state@1", "resources": {}, "rotations": {}}
        self._operation_lock = threading.RLock()
        self._session_epoch = 0
        self._operation_depth = 0
        self._store_lock_fd: int | None = None
        self._store_directory_fd: int | None = None
        if self.path.exists():
            self._document = self._load_document()

    @property
    def unlocked(self) -> bool:
        return self._master is not None

    @property
    def session_epoch(self) -> int:
        """Volatile session lifetime, without key material or access authority.

        Explicit create/unlock and every lock retire an earlier operation.
        Ordinary authenticated key-store refreshes preserve this lifetime.
        """
        with self._operation_lock:
            return self._session_epoch

    def public_state(self) -> dict[str, Any]:
        document = self._document
        if document is None:
            return _public_key_state(
                status="absent",
                code="key_store_absent",
                protection=None,
                unlocked=False,
                actions=("create_with_passphrase", "create_with_keyring", "recovery_import"),
                message="No wrapped key store exists. Create one with a passphrase or an available keyring, or import recovery material.",
                awaiting_user=True,
            )
        protection = str(document.get("protection") or "")
        case_count = len(document.get("cases") or {})
        if self.unlocked:
            return _public_key_state(
                status="unlocked",
                code="unlocked",
                protection=protection,
                unlocked=True,
                actions=("lock", "recovery_export"),
                message="Keys are unwrapped in this session only.",
                awaiting_user=False,
                case_count=case_count,
            )
        actions = ["recovery_import"]
        if protection == "passphrase":
            actions.insert(0, "passphrase_unlock")
        elif protection == "keyring":
            actions.insert(0, "keyring_unlock")
            actions.append("passphrase_or_recovery_instead_of_raw_file")
        return _public_key_state(
            status="unlock_needed",
            code="unlock_needed",
            protection=protection,
            unlocked=False,
            actions=actions,
            message="Wrapped keys are locked. Unlock with the configured method or import a deliberate recovery export. No raw key file will be written.",
            awaiting_user=True,
            case_count=case_count,
        )

    @_key_session_operation(authenticate=False)
    def create(
        self,
        *,
        protection: str,
        passphrase: str | None = None,
        keyring: Any = None,
    ) -> dict[str, Any]:
        if protection not in {"passphrase", "keyring"}:
            raise PrivateKeyMaterialError("protection_mode")
        if self.path.exists():
            raise PrivateKeyLockedError(
                "A wrapped key store already exists and will not be replaced.",
                actions=self.public_state()["actions"],
                protection=str((self._document or {}).get("protection") or protection),
            )
        if protection == "passphrase":
            _require_passphrase(passphrase)
        master = _random_secret()
        master_id = _opaque_key_id("m-")
        if protection == "passphrase":
            salt = os.urandom(16)
            wrapped = _wrap_secret(_kdf_bytes(passphrase, salt), master, MASTER_WRAP_AAD)
            document = self._new_document(
                protection="passphrase",
                master_id=master_id,
                wrapped=wrapped,
                kdf=_kdf_metadata(salt),
            )
        else:
            adapter = _require_keyring(keyring)
            wrapping = _random_secret()
            account = _opaque_key_id("kr-")
            try:
                adapter.set_password(_KEYRING_SERVICE, account, _b64e(wrapping))
            except Exception as exc:
                raise PrivateKeyLockedError(
                    "The OS keyring is unavailable or locked. Use a passphrase or import recovery material. A raw key file was not written.",
                    actions=("create_with_passphrase", "recovery_import"),
                    code="keyring_unavailable",
                ) from exc
            document = self._new_document(
                protection="keyring",
                master_id=master_id,
                wrapped=_wrap_secret(wrapping, master, MASTER_WRAP_AAD),
                kdf=None,
                keyring_account=account,
            )
        self._write_document(document)
        self._document = document
        self._master = master
        self._master_id = master_id
        self._session_epoch += 1
        return self.public_state()

    @_key_session_operation(authenticate=False)
    def unlock_passphrase(self, passphrase: str) -> dict[str, Any]:
        document = self._require_document()
        if document.get("protection") != "passphrase":
            raise PrivateKeyLockedError(
                "This store is not passphrase-wrapped. Retry the keyring or import a deliberate recovery export into a new store.",
                actions=("keyring_unlock", "recovery_import"),
                protection=str(document.get("protection") or ""),
                code="keyring_unavailable" if document.get("protection") == "keyring" else "unlock_needed",
            )
        kdf = document.get("kdf")
        if not isinstance(kdf, Mapping) or kdf.get("name") != "scrypt":
            raise PrivateArtifactIntegrityError("malformed")
        if int(kdf.get("n") or 0) != SCRYPT_N or int(kdf.get("r") or 0) != SCRYPT_R or int(kdf.get("p") or 0) != SCRYPT_P:
            raise PrivateArtifactIntegrityError("malformed")
        try:
            master = self._open_master_with_passphrase(document, passphrase)
        except PrivateArtifactIntegrityError as exc:
            self.lock()
            raise PrivateArtifactIntegrityError(exc.reason) from None
        self._install_master(document, master)
        self._session_epoch += 1
        return self.public_state()

    @_key_session_operation(authenticate=False)
    def unlock_keyring(self, keyring: Any = None) -> dict[str, Any]:
        document = self._require_document()
        if document.get("protection") != "keyring":
            raise PrivateKeyLockedError(
                "This store is passphrase-wrapped. A keyring unlock was not attempted and no raw key file was written.",
                actions=("passphrase_unlock", "recovery_import"),
                protection="passphrase",
            )
        adapter = keyring if keyring is not None else _optional_system_keyring()
        if adapter is None:
            raise PrivateKeyLockedError(
                "No OS keyring is available. Unlock by importing a deliberate recovery export or creating a new passphrase-protected store. The existing store was not rewritten.",
                actions=("recovery_import", "create_with_passphrase"),
                protection="keyring",
                code="keyring_unavailable",
            )
        account = str(document.get("keyring_account") or "")
        try:
            stored = adapter.get_password(_KEYRING_SERVICE, account)
        except Exception as exc:
            raise PrivateKeyLockedError(
                "The OS keyring is locked. Enter a recovery export or retry the keyring. The wrapped store was not replaced with a raw key.",
                actions=("recovery_import", "keyring_unlock"),
                protection="keyring",
            ) from exc
        if not isinstance(stored, str) or stored == "":
            raise PrivateKeyLockedError(
                "The OS keyring did not return the wrapping key. Import recovery material or retry the keyring.",
                actions=("recovery_import", "keyring_unlock"),
                protection="keyring",
            )
        try:
            wrapping = _b64d(stored)
            master = _unwrap_secret(wrapping, document.get("wrapped_master") or {}, MASTER_WRAP_AAD)
        except PrivateArtifactIntegrityError as exc:
            self.lock()
            raise PrivateArtifactIntegrityError(exc.reason) from None
        self._install_master(document, master)
        self._session_epoch += 1
        return self.public_state()

    def lock(self) -> dict[str, Any]:
        with self._operation_lock:
            self._session_epoch += 1
            if self._master is not None:
                self._master = bytes(DATA_KEY_BYTES)
                self._master = None
            self._data_keys.clear()
            self._retained_data_keys.clear()
            self._pending_data_keys.clear()
            self._recipient_wrap = None
            self._case_grant_state = {"schema": "case-grant-key-state@1", "resources": {}, "rotations": {}}
            self._master_id = None
            return self.public_state()

    @_key_session_operation()
    def ensure_data_key(self, tenant_id: str, case_id: str) -> str:
        _require_label(tenant_id)
        _require_label(case_id)
        if self._case_was_destroyed(tenant_id, case_id):
            raise PrivateKeyMaterialError("case_key_destroyed")
        if not self.unlocked or self._master is None or self._document is None:
            raise PrivateKeyLockedError(
                "The case key is locked, so encrypted state was left unchanged.",
                actions=self.public_state()["actions"],
                protection=(self._document or {}).get("protection") if isinstance(self._document, dict) else None,
            )
        found = self._data_keys.get((tenant_id, case_id))
        if found is not None:
            return found[0]
        key_id = _opaque_key_id("d-")
        data_key = _random_secret()
        cases = dict(self._document.get("cases") or {})
        cases[f"{tenant_id}\n{case_id}"] = {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "data_key_id": key_id,
            "wrapped_data_key": _wrap_secret(self._master, data_key, _data_aad(tenant_id, case_id, key_id)),
        }
        updated = dict(self._document)
        updated["cases"] = cases
        self._write_document(updated)
        self._document = updated
        self._data_keys[(tenant_id, case_id)] = (key_id, data_key)
        return key_id

    @_key_session_operation()
    def ensure_recipient_wrap_key(self) -> str:
        """Create the session wrap key used only to receive case key grants.

        The wrap key stays inside this unlocked session. Callers cannot submit
        a browser key, a raw ``.key`` file, or the master key in its place.
        """

        if not self.unlocked or self._master is None or self._document is None:
            raise PrivateKeyLockedError(
                "The recipient wrap key is locked, so no key grant was written.",
                actions=self.public_state()["actions"],
                protection=(self._document or {}).get("protection") if isinstance(self._document, dict) else None,
            )
        if self._recipient_wrap is not None:
            return self._recipient_wrap[0]
        key_id = _opaque_key_id("r-")
        material = _random_secret()
        if material == self._master:
            raise PrivateKeyMaterialError("owner_key_not_a_grant")
        document = dict(self._document)
        document["recipient_wrap"] = {
            "wrap_key_id": key_id,
            "wrapped_wrap_key": _wrap_secret(self._master, material, _recipient_wrap_aad(key_id)),
        }
        document["raw_key_persisted"] = False
        self._write_document(document)
        self._document = document
        self._recipient_wrap = (key_id, material)
        return key_id

    @contextmanager
    def case_key_epoch_scope(self, tenant_id: str, case_id: str):
        """Hold one case key epoch before Grant, Member or key-store locks.

        No key material or authority is yielded. Callers must acquire this
        scope before entering key RMW operations. Independent unlocked handles
        for this same owned store share the lock; nested same-thread calls are
        reentrant. The lock is separate from Keys so publication callbacks can
        retain their established Grant -> Member -> Keys order.
        """
        _require_label(tenant_id)
        _require_label(case_id)
        directory = self.directory
        if directory.resolve(strict=True) != directory:
            raise PrivateKeyMaterialError("permissions")
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptor = None
        try:
            info = os.fstat(directory_fd)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o700):
                raise PrivateKeyMaterialError("permissions")
            digest = hashlib.sha256(json.dumps([tenant_id, case_id], separators=(",", ":")).encode()).hexdigest()
            name = ".case-epoch-" + digest + ".lock"
            identity = (os.getpid(), str(directory / name))
            with _CASE_EPOCH_LOCKS_GUARD:
                lock = _CASE_EPOCH_LOCKS.setdefault(identity, threading.RLock())
            with lock:
                held = getattr(_CASE_EPOCH_HELD, "locks", None)
                if held is None:
                    held = _CASE_EPOCH_HELD.locks = {}
                # A fork must not reuse a parent's reentrancy or keep its copied
                # descriptor alive while attempting a second flock.
                for inherited, handle in list(held.items()):
                    if inherited[0] != os.getpid():
                        os.close(handle)
                        del held[inherited]
                if identity in held:
                    yield
                    return
                descriptor = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                                     0o600, dir_fd=directory_fd)
                before = os.fstat(descriptor)
                def reprove():
                    named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    parent = directory.lstat()
                    if (not stat.S_ISREG(named.st_mode) or named.st_uid != os.getuid()
                            or stat.S_IMODE(named.st_mode) != 0o600 or named.st_nlink != 1
                            or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)
                            or (info.st_dev, info.st_ino) != (parent.st_dev, parent.st_ino)
                            or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700):
                        raise PrivateKeyMaterialError("permissions")
                reprove()
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                reprove()
                held[identity] = descriptor
                try:
                    yield
                finally:
                    del held[identity]
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(directory_fd)

    def rotate_case_grant_data_key(self, tenant_id: str, case_id: str, *,
                                   resource_id: str, expected_data_key_id: str,
                                   operation_id: str,
                                   before_publish: Callable[[], Any] | None = None) -> dict[str, Any]:
        # Epoch must precede the Keys decorator, including direct trusted calls.
        with self.case_key_epoch_scope(tenant_id, case_id):
            return self._rotate_case_grant_data_key(tenant_id, case_id, resource_id=resource_id,
                expected_data_key_id=expected_data_key_id, operation_id=operation_id,
                **({"before_publish":before_publish} if before_publish is not None else {}))

    @_key_session_operation()
    def _rotate_case_grant_data_key(self, tenant_id: str, case_id: str, *,
                                   resource_id: str, expected_data_key_id: str,
                                   operation_id: str,
                                   before_publish: Callable[[], Any] | None = None) -> dict[str, Any]:
        """Rotate the active case DEK under a verified canonical resource scope.

        CaseDirectory currently has one canonical resource per case. This is
        the same DEK selected by provider().resolve for ordinary owner writes;
        it is not a grant-only key or a workspace ciphertext migration.
        """
        self._require_unlocked("Case key rotation requires an unlocked session. Nothing was changed.")
        _require_label(tenant_id)
        _require_label(case_id)
        _require_label(resource_id)
        _require_label(operation_id)
        operation_hash = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
        current = self._data_keys.get((tenant_id, case_id))
        if current is None:
            raise PrivateKeyMaterialError("key_unavailable")
        current_id, current_key = current
        prior_rotation = self._case_grant_state["rotations"].get(operation_hash)
        if prior_rotation is not None:
            if (prior_rotation.get("tenant_id"), prior_rotation.get("case_id"), prior_rotation.get("resource_id"),
                    prior_rotation.get("old_data_key_id")) != (tenant_id, case_id, resource_id, expected_data_key_id):
                raise PrivateKeyMaterialError("key_rotation_replay_mismatch")
            if current_id != prior_rotation.get("new_data_key_id"):
                raise PrivateKeyMaterialError("key_rotation_superseded")
            return {**prior_rotation, "rotated": False, "replayed": True,
                    "workspace_ciphertext_migrated": False}
        if current_id != expected_data_key_id:
            raise PrivateKeyMaterialError("key_revision_conflict")
        assert self._document is not None
        associations = dict(self._case_grant_state["resources"])
        slot = f"{tenant_id}\n{case_id}"
        if associations.get(slot) not in {None, resource_id}:
            raise PrivateArtifactBindingError("resource_mismatch")
        slot, record = self._case_record(tenant_id, case_id)
        if record.get("pending_data_key") is not None:
            raise PrivateKeyMaterialError("key_rotation_in_progress")
        assert self._master is not None
        new_id, new_key = _opaque_key_id("d-"), _random_secret()
        retained = [dict(item) for item in record.get("retained_data_keys") or []]
        retained.append({"data_key_id": current_id,
                         "wrapped_data_key": dict(record["wrapped_data_key"]), "status": "retained"})
        record.update(data_key_id=new_id,
            wrapped_data_key=_wrap_secret(self._master, new_key, _data_aad(tenant_id, case_id, new_id)),
            retained_data_keys=retained)
        document = dict(self._document)
        cases = dict(document.get("cases") or {})
        cases[slot] = record
        associations[slot] = resource_id
        receipt = {"old_data_key_id": current_id, "new_data_key_id": new_id,
                   "tenant_id": tenant_id, "case_id": case_id, "resource_id": resource_id,
                   "operation_id_sha256": operation_hash}
        rotations = dict(self._case_grant_state["rotations"])
        rotations[operation_hash] = receipt
        state = {"schema": "case-grant-key-state@1", "resources": associations, "rotations": rotations}
        document["cases"] = cases
        self._seal_case_grant_state(document, state)
        self._write_document(document, **({"before_publish":before_publish} if before_publish is not None else {}))
        self._document = document
        self._case_grant_state = state
        self._data_keys[(tenant_id, case_id)] = (new_id, new_key)
        self._retained_data_keys.setdefault((tenant_id, case_id), []).append((current_id, current_key))
        return {**receipt, "rotated": True, "replayed": False, "workspace_ciphertext_migrated": False}

    def _bind_case_grant_resource(self, tenant_id: str, case_id: str, resource_id: str) -> None:
        _require_label(tenant_id)
        _require_label(case_id)
        _require_label(resource_id)
        self._require_unlocked("Resource key binding requires an unlocked session.")
        assert self._document is not None
        associations = dict(self._case_grant_state["resources"])
        slot = f"{tenant_id}\n{case_id}"
        prior = associations.get(slot)
        if prior is not None and prior != resource_id:
            raise PrivateArtifactBindingError("resource_mismatch")
        if prior is None:
            associations[slot] = resource_id
            document = dict(self._document)
            state = {**self._case_grant_state, "resources": associations}
            self._seal_case_grant_state(document, state)
            self._write_document(document)
            self._document = document
            self._case_grant_state = state

    def _case_grant_state_binding(self, master_id: str) -> PrivateArtifactBinding:
        return PrivateArtifactBinding(tenant_id=master_id, case_id="key-store-grants",
            principal_id=master_id, artifact_kind="case-grant-key-state", revision="1")

    def _seal_case_grant_state(self, document: dict[str, Any], state: Mapping[str, Any]) -> None:
        assert self._master is not None and self._master_id is not None
        envelope = seal_private_artifact(json.dumps(state, sort_keys=True, separators=(",", ":")).encode(),
            binding=self._case_grant_state_binding(self._master_id), key=self._master, key_id=self._master_id)
        document["case_grant_state"] = _b64e(envelope)

    @_key_session_operation()
    def recipient_wrap_key(self) -> tuple[str, bytes]:
        """Return the in-process wrap key. Locked sessions and raw files fail."""

        if not self.unlocked or self._recipient_wrap is None:
            raise PrivateKeyLockedError(
                "The recipient wrap key is unavailable. Unlock the session and create it there.",
                actions=self.public_state()["actions"],
                protection=(self._document or {}).get("protection") if isinstance(self._document, dict) else None,
            )
        self.assert_no_raw_key_files()
        return self._recipient_wrap

    @_key_session_operation()
    def wrap_case_key_for_recipient(
        self,
        *,
        tenant_id: str,
        case_id: str,
        recipient_wrap_key: bytes,
        recipient_wrap_key_id: str,
        canonical_principal_id: str,
        revision: str,
        recipient_principal_id: str,
        artifact_kind: str,
        resource_id: str,
        membership_grant_id: str,
        membership_version: int,
    ) -> dict[str, str]:
        """Wrap this session's case data key. The master key is not a grant key."""

        if not self.unlocked or self._master is None:
            raise PrivateKeyLockedError(
                "The case key is locked, so it was not wrapped for a recipient.",
                actions=self.public_state()["actions"],
                protection=(self._document or {}).get("protection") if isinstance(self._document, dict) else None,
            )
        self._bind_case_grant_resource(tenant_id, case_id, resource_id)
        found = self._data_keys.get((tenant_id, case_id))
        if found is None:
            raise PrivateKeyMaterialError("key_unavailable")
        data_key_id, data_key = found
        wrap_key = _require_data_key(recipient_wrap_key)
        if wrap_key == self._master or wrap_key == data_key:
            raise PrivateKeyMaterialError("owner_key_not_a_grant")
        associated = resource_grant_associated_data(
            tenant_id=tenant_id,
            case_id=case_id,
            canonical_principal_id=canonical_principal_id,
            revision=revision,
            recipient_principal_id=recipient_principal_id,
            artifact_kind=artifact_kind,
            resource_id=resource_id,
            membership_grant_id=membership_grant_id,
            membership_version=membership_version,
            data_key_id=data_key_id,
            recipient_wrap_key_id=recipient_wrap_key_id,
        )
        wrapped = wrap_resource_key_for_recipient(data_key, wrap_key, associated)
        wrapped["data_key_id"] = data_key_id
        wrapped["recipient_wrap_key_id"] = recipient_wrap_key_id
        return wrapped

    @_key_session_operation()
    def unwrap_granted_resource_key(
        self,
        wrapped: Mapping[str, Any],
        *,
        tenant_id: str,
        case_id: str,
        canonical_principal_id: str,
        revision: str,
        recipient_principal_id: str,
        artifact_kind: str,
        resource_id: str,
        membership_grant_id: str,
        membership_version: int,
        data_key_id: str,
        recipient_wrap_key_id: str,
    ) -> bytes:
        """Unwrap with this session's recipient wrap key, never the master key."""

        wrap_id, wrap_key = self.recipient_wrap_key()
        if wrap_id != recipient_wrap_key_id:
            raise PrivateKeyMaterialError("recipient_mismatch")
        if self._master is not None and wrap_key == self._master:
            raise PrivateKeyMaterialError("admin_master_rejected")
        associated = resource_grant_associated_data(
            tenant_id=tenant_id,
            case_id=case_id,
            canonical_principal_id=canonical_principal_id,
            revision=revision,
            recipient_principal_id=recipient_principal_id,
            artifact_kind=artifact_kind,
            resource_id=resource_id,
            membership_grant_id=membership_grant_id,
            membership_version=membership_version,
            data_key_id=data_key_id,
            recipient_wrap_key_id=recipient_wrap_key_id,
        )
        return unwrap_resource_key_for_recipient(wrapped, wrap_key, associated)

    def provider(self) -> InjectedCaseKeyProvider:
        if not self.unlocked:
            raise PrivateKeyLockedError(
                "Cannot build an in-memory key provider while locked.",
                actions=self.public_state()["actions"],
                protection=(self._document or {}).get("protection") if isinstance(self._document, dict) else None,
            )
        session = self

        class SessionKeyProvider(InjectedCaseKeyProvider):
            """A retained handle cannot bypass a later session lock."""

            def __init__(self) -> None:
                # Keep the session handle, never a snapshot of unwrapped keys.
                super().__init__({})

            def resolve(self, binding: PrivateArtifactBinding) -> tuple[str, bytes]:
                with session._key_operation():
                    if not session.unlocked:
                        raise PrivateKeyLockedError(
                            "The key session is locked. Unlock it before resolving a case key.",
                            actions=session.public_state()["actions"],
                            protection=(session._document or {}).get("protection"),
                        )
                    return InjectedCaseKeyProvider(session._data_keys).resolve(binding)

        return SessionKeyProvider()

    @_key_session_operation()
    def export_recovery(self, tenant_id: str, case_id: str, recovery_passphrase: str, destination: str | Path | None = None) -> dict[str, Any]:
        if not self.unlocked:
            raise PrivateKeyLockedError(
                "Recovery export requires an unlocked session. Nothing was written.",
                actions=self.public_state()["actions"],
                protection=(self._document or {}).get("protection") if isinstance(self._document, dict) else None,
            )
        _require_passphrase(recovery_passphrase)
        key_id = self.ensure_data_key(tenant_id, case_id)
        _key_id, data_key = self._data_keys[(tenant_id, case_id)]
        salt = os.urandom(16)
        payload = {
            "schema": KEY_RECOVERY_SCHEMA,
            "schema_version": KEY_RECOVERY_VERSION,
            "deliberate_export": True,
            "automatic_backup": False,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "data_key_id": key_id,
            "kdf": _kdf_metadata(salt),
            "wrapped_data_key": _wrap_secret(
                _kdf_bytes(recovery_passphrase, salt),
                data_key,
                _recovery_aad(tenant_id, case_id, key_id),
            ),
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        if destination is not None:
            target = Path(destination)
            _reject_secret_path(target)
            if target.is_dir():
                raise PrivateKeyMaterialError("recovery_destination")
            _write_private_bytes(target, encoded, protect_parent=False)
        return {
            "deliberate_export": True,
            "automatic_backup": False,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "data_key_id": key_id,
            "bytes": encoded,
            "unlock_is_remote_consent": False,
        }

    @_key_session_operation()
    def import_recovery(
        self,
        payload: bytes | str | Mapping[str, Any],
        *,
        tenant_id: str,
        case_id: str,
        recovery_passphrase: str,
        store_passphrase: str | None = None,
    ) -> dict[str, Any]:
        _require_label(tenant_id)
        _require_label(case_id)
        document_in = _parse_recovery(payload)
        if document_in.get("automatic_backup") is not False or document_in.get("deliberate_export") is not True:
            raise PrivateKeyMaterialError("recovery_not_deliberate")
        declared_tenant = str(document_in.get("tenant_id") or "")
        declared_case = str(document_in.get("case_id") or "")
        if declared_tenant != tenant_id or declared_case != case_id:
            raise PrivateArtifactBindingError("foreign_case")
        if self._case_was_destroyed(tenant_id, case_id):
            raise PrivateKeyMaterialError("case_key_destroyed")
        key_id = str(document_in.get("data_key_id") or "")
        kdf = document_in.get("kdf")
        if not isinstance(kdf, Mapping):
            raise PrivateArtifactIntegrityError("malformed")
        data_key = _unwrap_secret(
            _kdf_bytes(recovery_passphrase, _b64d(str(kdf.get("salt") or ""))),
            document_in.get("wrapped_data_key") or {},
            _recovery_aad(tenant_id, case_id, key_id),
        )
        if self.path.exists() and not self.unlocked:
            raise PrivateKeyLockedError(
                "The existing wrapped store is locked, so recovery import did not overwrite it.",
                actions=self.public_state()["actions"],
                protection=str((self._document or {}).get("protection") or ""),
            )
        if self._document is None:
            chosen = store_passphrase if store_passphrase is not None else recovery_passphrase
            self.create(protection="passphrase", passphrase=chosen)
        assert self._master is not None and self._document is not None
        cases = dict(self._document.get("cases") or {})
        slot = f"{tenant_id}\n{case_id}"
        current = cases.get(slot)
        if isinstance(current, Mapping) and current.get("data_key_id") not in {None, key_id}:
            raise PrivateKeyLockedError(
                "This case already has a different data key. The existing wrapped key was kept.",
                actions=("unlock", "recovery_export"),
                protection=str(self._document.get("protection") or ""),
            )
        cases[slot] = {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "data_key_id": key_id,
            "wrapped_data_key": _wrap_secret(self._master, data_key, _data_aad(tenant_id, case_id, key_id)),
        }
        updated = dict(self._document)
        updated["cases"] = cases
        self._write_document(updated)
        self._document = updated
        self._data_keys[(tenant_id, case_id)] = (key_id, data_key)
        state = self.public_state()
        state["imported"] = True
        state["deliberate_export"] = True
        state["automatic_backup"] = False
        state["keys_reconstructed"] = False
        state["data_reset"] = False
        return state

    @_key_session_operation()
    def lookup_data_key(self, tenant_id: str, case_id: str, key_id: str) -> bytes | None:
        """Return an unlocked active, pending, or retained data key."""

        active = self._data_keys.get((tenant_id, case_id))
        if active is not None and active[0] == key_id:
            return active[1]
        pending = self._pending_data_keys.get((tenant_id, case_id))
        if pending is not None and pending[0] == key_id:
            return pending[1]
        for retained_id, retained_key in self._retained_data_keys.get((tenant_id, case_id), []):
            if retained_id == key_id:
                return retained_key
        return None

    @_key_session_operation()
    def rotate_wrapping_key(
        self,
        new_passphrase: str,
        *,
        policy: str = "retain",
        crash_at: str | None = None,
    ) -> dict[str, Any]:
        """Rewrap the same master key. Ciphertext and data keys stay in place.

        ``crash_at`` persists that phase and then raises. Each phase leaves a
        passphrase that still opens the current generation. This does not revoke
        the previous wrapping.
        """

        self._require_unlocked("Wrapping rotation requires an unlocked session. Nothing was written.")
        if policy not in RETENTION_POLICIES:
            raise PrivateKeyMaterialError("retention_policy")
        if crash_at not in {None, *WRAP_ROTATION_PHASES}:
            raise PrivateKeyMaterialError("rotation_phase")
        _require_passphrase(new_passphrase)
        if self._master is None or self._document is None:
            raise PrivateKeyMaterialError("key_unavailable")
        token = _opaque_key_id("rot-")
        prepared = {
            "schema": ROTATION_SCHEMA,
            "schema_version": ROTATION_VERSION,
            "kind": "rewrap",
            "operation": "rewrap",
            "reencrypt": False,
            "phase": "prepared",
            "rotation_id": token,
            "retention_policy": policy,
            "readable_generation": "previous",
            "data_key_changed": False,
        }
        self._write_rotation_journal(prepared)
        self._interrupt(crash_at, "prepared", token)
        salt = os.urandom(16)
        candidate = {
            "wrapping_id": _opaque_key_id("w-"),
            "protection": "passphrase",
            "kdf": _kdf_metadata(salt),
            "wrapped_master": _wrap_secret(_kdf_bytes(new_passphrase, salt), self._master, MASTER_WRAP_AAD),
            "status": "candidate",
        }
        staged = dict(prepared)
        staged["phase"] = "candidate"
        staged["candidate"] = candidate
        self._write_rotation_journal(staged)
        self._interrupt(crash_at, "candidate", token)
        document = dict(self._document)
        previous = {
            "wrapping_id": str(document.get("active_wrapping_id") or "initial"),
            "protection": document.get("protection"),
            "kdf": document.get("kdf"),
            "wrapped_master": dict(document.get("wrapped_master") or {}),
            "status": "retained",
        }
        if document.get("keyring_account"):
            previous["keyring_account"] = document.get("keyring_account")
        retained = [dict(item) for item in document.get("retained_wrappings") or []]
        retained.append(previous)
        document["retained_wrappings"] = retained
        document["protection"] = "passphrase"
        document["kdf"] = dict(candidate["kdf"])
        document["wrapped_master"] = dict(candidate["wrapped_master"])
        document["active_wrapping_id"] = candidate["wrapping_id"]
        document["retention_policy"] = policy
        document.pop("keyring_account", None)
        document.pop("keyring_service", None)
        self._write_document(document)
        self._document = document
        committed = dict(prepared)
        committed["phase"] = "committed"
        committed["previous_wrapping_retained"] = True
        self._write_rotation_journal(committed)
        self._interrupt(crash_at, "committed", token)
        state = self.public_state()
        state.update({
            "operation": "rewrap",
            "reencrypt": False,
            "rotation_phase": "committed",
            "previous_wrapping_retained": True,
            "data_key_changed": False,
            "retention_policy": policy,
            "revoked": False,
            "keys_reconstructed": False,
            "data_reset": False,
            "only_recovery_path_erased": False,
            "unwrapped_master_included": False,
        })
        _PORTABILITY_LOG.info("wrapping key rewrapped; data keys were not reencrypted")
        return state

    @_key_session_operation()
    def rotate_data_key(
        self,
        tenant_id: str,
        case_id: str,
        repository: str | Path,
        principal_id: str,
        *,
        policy: str = "retain",
        crash_at: str | None = None,
    ) -> dict[str, Any]:
        """Reencrypt workspace ciphertext under a new data key.

        The previous data key and its ciphertext generation stay until an
        explicit verified revocation. A crash after any phase still leaves one
        intact generation.
        """

        self._require_unlocked("Data-key rotation requires an unlocked session. Nothing was written.")
        if policy not in RETENTION_POLICIES:
            raise PrivateKeyMaterialError("retention_policy")
        if crash_at not in {None, *DATA_ROTATION_PHASES}:
            raise PrivateKeyMaterialError("rotation_phase")
        _require_label(tenant_id)
        _require_label(case_id)
        _require_label(principal_id)
        if self._master is None or self._document is None:
            raise PrivateKeyMaterialError("key_unavailable")
        current_id, current_key = self._require_case_key(tenant_id, case_id)
        opened = read_private_workspace_generation(
            repository,
            self,
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
        )
        token = _opaque_key_id("rot-")
        new_id = _opaque_key_id("d-")
        new_key = _random_secret()
        slot, record = self._case_record(tenant_id, case_id)
        record["pending_data_key"] = {
            "data_key_id": new_id,
            "wrapped_data_key": _wrap_secret(self._master, new_key, _data_aad(tenant_id, case_id, new_id)),
            "status": "pending",
        }
        self._store_case_record(slot, record)
        self._pending_data_keys[(tenant_id, case_id)] = (new_id, new_key)
        ledger = _workspace_ledger(repository)
        generations = ledger / "generations"
        generations.mkdir(parents=True, exist_ok=True)
        primary = _read_exact(ledger / _WORKSPACE_FRAME)
        if primary is None:
            raise PrivatePortabilityError(
                "No ciphertext generation is available to rotate.",
                code="ciphertext_missing",
                actions=("export_retry", "restore_generation"),
            )
        retained_frame = generations / f"{current_id}.frame"
        if not retained_frame.exists():
            _write_mode600(retained_frame, primary)
        journal = {
            "schema": ROTATION_SCHEMA,
            "schema_version": ROTATION_VERSION,
            "kind": "reencrypt",
            "operation": "reencrypt",
            "reencrypt": True,
            "phase": "prepared",
            "rotation_id": token,
            "retention_policy": policy,
            "previous_key_id": current_id,
            "pending_key_id": new_id,
            "readable_generation": "previous",
        }
        _write_mode600(ledger / "rotation-data.json", _json_bytes(journal))
        self._interrupt(crash_at, "prepared", token)
        sealed = _seal_workspace_frame(
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            key=new_key,
            key_id=new_id,
            revision=str(opened["revision"]),
            complaint=bytes(opened["complaint"]),
            fact_graph=bytes(opened["fact_graph"]),
            proof=bytes(opened["proof"]),
        )
        _write_mode600(generations / f"{new_id}.frame", sealed)
        journal["phase"] = "sealed"
        journal["pending_digest"] = _replica_digest(sealed)
        _write_mode600(ledger / "rotation-data.json", _json_bytes(journal))
        self._interrupt(crash_at, "sealed", token)
        retained_keys = [dict(item) for item in record.get("retained_data_keys") or []]
        retained_keys.append({
            "data_key_id": current_id,
            "wrapped_data_key": dict(record.get("wrapped_data_key") or {}),
            "status": "retained",
        })
        record["retained_data_keys"] = retained_keys
        record["data_key_id"] = new_id
        record["wrapped_data_key"] = dict(record["pending_data_key"]["wrapped_data_key"])
        record.pop("pending_data_key", None)
        self._store_case_record(slot, record)
        self._data_keys[(tenant_id, case_id)] = (new_id, new_key)
        self._retained_data_keys.setdefault((tenant_id, case_id), []).append((current_id, current_key))
        self._pending_data_keys.pop((tenant_id, case_id), None)
        catalog = {
            "digest": _replica_digest(sealed),
            "version": str(opened["revision"]),
            "revision": str(opened["revision"]),
            "desired": 1,
            "minimum": 1,
            "mode": "local_private",
            "providers": [],
        }
        previous_catalog = _read_exact(ledger / _WORKSPACE_CATALOG) or b""
        intent = {"previous_catalog_sha256": _replica_digest(previous_catalog), "catalog": catalog}
        _write_workspace_bytes(ledger, _WORKSPACE_PENDING, _json_bytes(intent))
        _write_workspace_bytes(ledger, _WORKSPACE_FRAME, sealed)
        _write_workspace_bytes(ledger, _WORKSPACE_CATALOG, _json_bytes(catalog))
        journal["phase"] = "committed"
        journal["previous_data_key_retained"] = True
        _write_mode600(ledger / "rotation-data.json", _json_bytes(journal))
        self._interrupt(crash_at, "committed", token)
        state = self.public_state()
        state.update({
            "operation": "reencrypt",
            "reencrypt": True,
            "rotation_phase": "committed",
            "previous_data_key_retained": True,
            "data_key_changed": True,
            "retention_policy": policy,
            "revoked": False,
            "revision": opened["revision"],
            "keys_reconstructed": False,
            "data_reset": False,
            "only_recovery_path_erased": False,
            "unwrapped_master_included": False,
        })
        _PORTABILITY_LOG.info("data key reencrypted; previous generation retained")
        return state

    @_key_session_operation()
    def revoke_retained_keys(
        self,
        tenant_id: str,
        case_id: str,
        repository: str | Path,
        *,
        policy: str,
        verified_backup_migration: bool,
        export_dir: str | Path | None = None,
        recovery_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Revoke retained keys only after a verified migration of the active generation.

        Rotation never calls this. A missing verified backup, or a recovery file
        that is the only path to the active key, leaves every retained key in place.
        """

        self._require_unlocked("Revocation requires an unlocked session. Nothing was erased.")
        if policy != "revoke_after_verified_migration":
            raise PrivatePortabilityError(
                "Old keys stay retained until revocation is an explicit verified-migration policy. Nothing was erased.",
                code="retention_policy",
                actions=("retain", "revoke_after_verified_migration"),
            )
        if verified_backup_migration is not True:
            raise PrivatePortabilityError(
                "Old keys stay retained until a verified backup migration. Nothing was erased.",
                code="revocation_requires_verified_migration",
                actions=("retain", "export_then_verify"),
            )
        if export_dir is None or recovery_path is None:
            raise PrivatePortabilityError(
                "Refusing to erase the only recovery path. Export a separate recovery file and verify it. " + UNRECOVERED_KEY_EXPLANATION,
                code="only_recovery_path",
                actions=("recovery_export", "retain"),
            )
        recovery_file = Path(recovery_path)
        if not recovery_file.is_file():
            raise PrivatePortabilityError(
                "Recovery material is missing, so retained keys were not erased. " + UNRECOVERED_KEY_EXPLANATION,
                code="recovery_key_missing",
                actions=("recovery_import", "retain"),
            )
        _assert_recovery_separated(export_dir, recovery_file)
        manifest = _load_portability_manifest(Path(export_dir))
        frame = _read_exact(Path(export_dir) / str(manifest["ciphertext"]))
        active_frame = _read_exact(_workspace_ledger(repository) / _WORKSPACE_FRAME)
        if frame is None or active_frame is None or frame != active_frame:
            raise PrivatePortabilityError(
                "The export archive does not match the active ciphertext. Retained keys were kept.",
                code="migration_not_verified",
                actions=("export_then_verify", "retain"),
            )
        if manifest.get("ciphertext_sha256") != _replica_digest(active_frame):
            raise PrivatePortabilityError(
                "The export manifest digest does not match the active ciphertext. Retained keys were kept.",
                code="migration_not_verified",
                actions=("export_then_verify", "retain"),
            )
        recovery = _parse_recovery(recovery_file.read_bytes())
        active_id = self._require_case_key(tenant_id, case_id)[0]
        if str(recovery.get("data_key_id") or "") != active_id or str(manifest.get("data_key_id") or "") != active_id:
            raise PrivatePortabilityError(
                "The recovery file does not protect the active data key. Refusing to erase the only recovery path.",
                code="only_recovery_path",
                actions=("recovery_export", "retain"),
            )
        if self._document is None:
            raise PrivateKeyMaterialError("key_store_absent")
        document = dict(self._document)
        retained_wrappings = []
        for item in document.get("retained_wrappings") or []:
            if isinstance(item, Mapping):
                updated = dict(item)
                updated["status"] = "revoked"
                retained_wrappings.append(updated)
        document["retained_wrappings"] = retained_wrappings
        document["retention_policy"] = policy
        slot, record = self._case_record(tenant_id, case_id)
        retained_keys = []
        for item in record.get("retained_data_keys") or []:
            if isinstance(item, Mapping):
                updated = dict(item)
                updated["status"] = "revoked"
                retained_keys.append(updated)
        record["retained_data_keys"] = retained_keys
        cases = dict(document.get("cases") or {})
        cases[slot] = record
        document["cases"] = cases
        self._write_document(document)
        self._document = document
        self._retained_data_keys[(tenant_id, case_id)] = []
        state = self.public_state()
        state.update({
            "operation": "revoke_retained",
            "retention_policy": policy,
            "verified_backup_migration": True,
            "revoked": True,
            "only_recovery_path_erased": False,
            "data_reset": False,
            "keys_reconstructed": False,
            "unwrapped_master_included": False,
        })
        _PORTABILITY_LOG.info("retained keys revoked after verified backup migration")
        return state

    def _case_was_destroyed(self, tenant_id: str, case_id: str) -> bool:
        document = self._document
        if not isinstance(document, dict):
            return False
        destroyed = document.get("destroyed_cases") or {}
        if not isinstance(destroyed, Mapping):
            return False
        item = destroyed.get(f"{tenant_id}\n{case_id}")
        return isinstance(item, Mapping) and item.get("status") == "destroyed"

    @_key_session_operation()
    def destroy_case_keys(self, tenant_id: str, case_id: str) -> dict[str, Any]:
        """Destroy one case's data keys. The master key and other cases stay."""

        _require_label(tenant_id)
        _require_label(case_id)
        if self._document is None:
            raise PrivateKeyMaterialError("key_store_absent")
        slot = f"{tenant_id}\n{case_id}"
        if self._case_was_destroyed(tenant_id, case_id):
            prior = dict((self._document.get("destroyed_cases") or {}).get(slot) or {})
            return {
                "destroyed": True,
                "idempotent": True,
                "master_key_destroyed": False,
                "other_cases_retained": True,
                "data_key_ids": list(prior.get("data_key_ids") or []),
            }
        self._require_unlocked("Destroying a case key requires an unlocked session. Nothing was erased.")
        document = dict(self._document)
        cases = dict(document.get("cases") or {})
        record = cases.pop(slot, None)
        key_ids: list[str] = []
        if isinstance(record, Mapping):
            active = str(record.get("data_key_id") or "")
            if active:
                key_ids.append(active)
            pending = record.get("pending_data_key")
            if isinstance(pending, Mapping) and pending.get("data_key_id"):
                key_ids.append(str(pending.get("data_key_id")))
            for item in record.get("retained_data_keys") or []:
                if isinstance(item, Mapping) and item.get("data_key_id"):
                    key_ids.append(str(item.get("data_key_id")))
        destroyed = dict(document.get("destroyed_cases") or {})
        destroyed[slot] = {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "status": "destroyed",
            "data_key_ids": key_ids,
        }
        document["cases"] = cases
        document["destroyed_cases"] = destroyed
        self._write_document(document)
        self._document = document
        self._zero_case_keys(tenant_id, case_id)
        return {
            "destroyed": True,
            "idempotent": False,
            "master_key_destroyed": False,
            "other_cases_retained": True,
            "data_key_ids": key_ids,
        }

    def _zero_case_keys(self, tenant_id: str, case_id: str) -> None:
        identity = (tenant_id, case_id)
        for pool in (self._data_keys, self._pending_data_keys):
            found = pool.pop(identity, None)
            if found is not None:
                buffer = bytearray(found[1])
                buffer[:] = b"\x00" * len(buffer)
        for _key_id, key in self._retained_data_keys.pop(identity, []):
            buffer = bytearray(key)
            buffer[:] = b"\x00" * len(buffer)

    def assert_no_raw_key_files(self) -> None:
        if not self.directory.exists():
            return
        for path in self.directory.rglob("*"):
            if path.is_file() and path.name.lower().endswith(".key"):
                raise PrivateKeyMaterialError("raw_key_persisted")

    def _require_document(self) -> dict[str, Any]:
        if self._document is None:
            raise PrivateKeyMaterialError("key_store_absent")
        return self._document

    def _install_master(self, document: Mapping[str, Any], master: bytes) -> None:
        loaded: dict[tuple[str, str], tuple[str, bytes]] = {}
        retained: dict[tuple[str, str], list[tuple[str, bytes]]] = {}
        pending: dict[tuple[str, str], tuple[str, bytes]] = {}
        cases = document.get("cases") or {}
        if not isinstance(cases, Mapping):
            raise PrivateArtifactIntegrityError("malformed")
        for item in cases.values():
            if not isinstance(item, Mapping):
                raise PrivateArtifactIntegrityError("malformed")
            tenant = str(item.get("tenant_id") or "")
            case = str(item.get("case_id") or "")
            key_id = str(item.get("data_key_id") or "")
            opened = _unwrap_secret(master, item.get("wrapped_data_key") or {}, _data_aad(tenant, case, key_id))
            loaded[(tenant, case)] = (key_id, opened)
            kept: list[tuple[str, bytes]] = []
            for prior in item.get("retained_data_keys") or []:
                if not isinstance(prior, Mapping) or prior.get("status") == "revoked":
                    continue
                prior_id = str(prior.get("data_key_id") or "")
                kept.append((
                    prior_id,
                    _unwrap_secret(master, prior.get("wrapped_data_key") or {}, _data_aad(tenant, case, prior_id)),
                ))
            retained[(tenant, case)] = kept
            pending_doc = item.get("pending_data_key")
            if isinstance(pending_doc, Mapping) and pending_doc.get("status") != "revoked":
                pending_id = str(pending_doc.get("data_key_id") or "")
                pending[(tenant, case)] = (
                    pending_id,
                    _unwrap_secret(master, pending_doc.get("wrapped_data_key") or {}, _data_aad(tenant, case, pending_id)),
                )
        recipient_wrap: tuple[str, bytes] | None = None
        wrap_document = document.get("recipient_wrap")
        if wrap_document is not None:
            if not isinstance(wrap_document, Mapping):
                raise PrivateArtifactIntegrityError("malformed")
            wrap_id = str(wrap_document.get("wrap_key_id") or "")
            opened_wrap = _unwrap_secret(
                master,
                wrap_document.get("wrapped_wrap_key") or {},
                _recipient_wrap_aad(wrap_id),
            )
            recipient_wrap = (wrap_id, opened_wrap)
        grant_state = {"schema": "case-grant-key-state@1", "resources": {}, "rotations": {}}
        if document.get("case_grant_state") is not None:
            master_id = str(document.get("master_key_id") or "")
            opened_state = open_private_artifact(_b64d(document["case_grant_state"]),
                binding=self._case_grant_state_binding(master_id), key=master, expected_key_id=master_id)
            try:
                grant_state = json.loads(opened_state)
                if (not isinstance(grant_state, dict) or set(grant_state) != {"schema", "resources", "rotations"}
                        or grant_state["schema"] != "case-grant-key-state@1"
                        or not isinstance(grant_state["resources"], dict) or not isinstance(grant_state["rotations"], dict)):
                    raise ValueError("invalid grant state")
            except (ValueError, TypeError):
                raise PrivateArtifactIntegrityError("malformed") from None
        self._master = master
        self._master_id = str(document.get("master_key_id") or "")
        self._data_keys = loaded
        self._retained_data_keys = retained
        self._pending_data_keys = pending
        self._recipient_wrap = recipient_wrap
        self._case_grant_state = grant_state

    def _new_document(
        self,
        *,
        protection: str,
        master_id: str,
        wrapped: Mapping[str, str],
        kdf: Mapping[str, Any] | None,
        keyring_account: str | None = None,
    ) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema": KEY_STORE_SCHEMA,
            "schema_version": KEY_STORE_VERSION,
            "protection": protection,
            "algorithm": ALGORITHM_NAME,
            "master_key_id": master_id,
            "wrapped_master": dict(wrapped),
            "cases": {},
            "raw_key_persisted": False,
        }
        if kdf is not None:
            document["kdf"] = dict(kdf)
        if keyring_account is not None:
            document["keyring_service"] = _KEYRING_SERVICE
            document["keyring_account"] = keyring_account
        return document

    @contextmanager
    def _key_operation(self, *, authenticate: bool = True):
        with self._operation_lock:
            outer = self._operation_depth == 0
            self._operation_depth += 1
            try:
                if outer:
                    if self.path.exists():
                        self._acquire_store_lock()
                        try:
                            document = self._load_document()
                            if authenticate and self._master is not None:
                                if document.get("master_key_id") != self._master_id:
                                    raise PrivateKeyMaterialError("key_store_changed")
                                self._install_master(document, self._master)
                            self._document = document
                        except Exception:
                            self.lock()
                            raise
                    elif self._document is not None:
                        self.lock()
                        raise PrivateKeyMaterialError("key_store_missing")
                yield
            finally:
                self._operation_depth -= 1
                if outer:
                    if self._store_lock_fd is not None:
                        os.close(self._store_lock_fd)
                        self._store_lock_fd = None
                    if self._store_directory_fd is not None:
                        os.close(self._store_directory_fd)
                        self._store_directory_fd = None

    def _acquire_store_lock(self) -> None:
        if self._store_lock_fd is not None:
            return
        import fcntl
        root = self.directory.absolute()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.resolve() != root:
            raise PrivateKeyMaterialError("permissions")
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptor = None
        try:
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise PrivateKeyMaterialError("permissions")
            descriptor = os.open(".keystore.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 0o600, dir_fd=directory)
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600):
                raise PrivateKeyMaterialError("permissions")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            named = os.stat(".keystore.lock", dir_fd=directory, follow_symlinks=False)
            if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
                raise PrivateKeyMaterialError("permissions")
            self._store_lock_fd, self._store_directory_fd = descriptor, directory
        except BaseException:
            if descriptor is not None:
                os.close(descriptor)
            os.close(directory)
            raise

    def _write_document(self, document: Mapping[str, Any], *, before_publish: Callable[[], Any] | None = None) -> None:
        if self._operation_depth < 1:
            raise PrivateKeyMaterialError("key_store_transaction_required")
        self._acquire_store_lock()
        if self._document is None and self.path.exists():
            raise PrivateKeyMaterialError("key_store_changed")
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        temporary = self.directory / f".{KEY_STORE_FILENAME}.tmp"
        _write_private_bytes(temporary, encoded, protect_parent=True)
        try:
            if before_publish is not None and before_publish() is False:
                raise PrivateKeyMaterialError("publication_denied")
            os.replace(temporary, self.path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        os.chmod(self.path, 0o600)
        _assert_owner_mode(self.path, 0o600)
        assert self._store_directory_fd is not None
        os.fsync(self._store_directory_fd)

    def _load_document(self) -> dict[str, Any]:
        raw = _read_private_bytes(self.path)
        try:
            document = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise PrivateArtifactIntegrityError("malformed") from exc
        if not isinstance(document, dict):
            raise PrivateArtifactIntegrityError("malformed")
        if document.get("schema") != KEY_STORE_SCHEMA or document.get("schema_version") != KEY_STORE_VERSION:
            raise PrivateArtifactIntegrityError("unsupported_version")
        if document.get("protection") not in {"passphrase", "keyring"}:
            raise PrivateArtifactIntegrityError("malformed")
        if document.get("raw_key_persisted") is not False:
            raise PrivateKeyMaterialError("raw_key_persisted")
        return document

    def _require_unlocked(self, message: str) -> None:
        if not self.unlocked:
            raise PrivateKeyLockedError(
                message,
                actions=self.public_state()["actions"],
                protection=(self._document or {}).get("protection") if isinstance(self._document, dict) else None,
            )

    def _require_case_key(self, tenant_id: str, case_id: str) -> tuple[str, bytes]:
        found = self._data_keys.get((tenant_id, case_id))
        if found is None:
            self.ensure_data_key(tenant_id, case_id)
            found = self._data_keys.get((tenant_id, case_id))
        if found is None:
            raise PrivateKeyMaterialError("key_unavailable")
        return found

    def _case_record(self, tenant_id: str, case_id: str) -> tuple[str, dict[str, Any]]:
        if self._document is None:
            raise PrivateKeyMaterialError("key_store_absent")
        slot = f"{tenant_id}\n{case_id}"
        cases = self._document.get("cases") or {}
        current = cases.get(slot)
        if not isinstance(current, Mapping):
            raise PrivateKeyMaterialError("key_unavailable")
        return slot, dict(current)

    def _store_case_record(self, slot: str, record: Mapping[str, Any]) -> None:
        if self._document is None:
            raise PrivateKeyMaterialError("key_store_absent")
        document = dict(self._document)
        cases = dict(document.get("cases") or {})
        cases[slot] = dict(record)
        document["cases"] = cases
        self._write_document(document)
        self._document = document

    def _rotation_journal_path(self) -> Path:
        return self.directory / "rotation-wrapping.json"

    def _write_rotation_journal(self, document: Mapping[str, Any]) -> None:
        _write_mode600(self._rotation_journal_path(), _json_bytes(document))

    def _open_master_with_passphrase(self, document: Mapping[str, Any], passphrase: str) -> bytes:
        candidates: list[Mapping[str, Any]] = [{
            "kdf": document.get("kdf"),
            "wrapped_master": document.get("wrapped_master"),
            "status": "active",
            "protection": document.get("protection"),
        }]
        for item in document.get("retained_wrappings") or []:
            if isinstance(item, Mapping):
                candidates.append(item)
        authenticated = False
        for item in candidates:
            if item.get("status") == "revoked":
                continue
            if item.get("protection") not in {"passphrase", None}:
                continue
            kdf = item.get("kdf")
            if not isinstance(kdf, Mapping) or kdf.get("name") != "scrypt":
                continue
            if int(kdf.get("n") or 0) != SCRYPT_N or int(kdf.get("r") or 0) != SCRYPT_R or int(kdf.get("p") or 0) != SCRYPT_P:
                continue
            try:
                return _unwrap_secret(
                    _kdf_bytes(passphrase, _b64d(str(kdf.get("salt") or ""))),
                    item.get("wrapped_master") or {},
                    MASTER_WRAP_AAD,
                )
            except PrivateArtifactIntegrityError:
                authenticated = True
                continue
        if authenticated:
            raise PrivateArtifactIntegrityError("authentication_failed")
        raise PrivateArtifactIntegrityError("malformed")

    @staticmethod
    def _interrupt(crash_at: str | None, phase: str, token: str) -> None:
        if crash_at == phase:
            raise PrivateRevisionInterrupted(phase, token)


def _parse_recovery(payload: bytes | str | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if isinstance(payload, (bytes, bytearray)):
        try:
            parsed = json.loads(bytes(payload).decode("utf-8"))
        except Exception as exc:
            raise PrivateArtifactIntegrityError("malformed") from exc
    elif isinstance(payload, Mapping):
        parsed = dict(payload)
    else:
        raise PrivateArtifactIntegrityError("malformed")
    if not isinstance(parsed, dict):
        raise PrivateArtifactIntegrityError("malformed")
    if parsed.get("schema") != KEY_RECOVERY_SCHEMA or parsed.get("schema_version") != KEY_RECOVERY_VERSION:
        raise PrivateArtifactIntegrityError("unsupported_version")
    return parsed


def _require_keyring(keyring: Any) -> Any:
    if keyring is None:
        keyring = _optional_system_keyring()
    if keyring is None or not hasattr(keyring, "set_password") or not hasattr(keyring, "get_password"):
        raise PrivateKeyLockedError(
            "The OS keyring is unavailable. Choose passphrase protection or import recovery material. No raw key file was written.",
            actions=("create_with_passphrase", "recovery_import"),
            code="keyring_unavailable",
        )
    return keyring


def _optional_system_keyring() -> Any:
    try:
        import keyring
    except Exception:
        return None
    if not hasattr(keyring, "get_password") or not hasattr(keyring, "set_password"):
        return None
    return keyring


def read_unlock_passphrase(prompt: str = "Private key passphrase", *, getpass_fn: Callable[[str], str] | None = None) -> str:
    """Read a passphrase without echoing it and without accepting argv values."""

    import sys

    for token in sys.argv:
        if not token.startswith("-"):
            continue
        name = token.split("=", 1)[0].lower()
        if name in {"--passphrase", "--password", "--master-key", "--data-key", "--wrapping-key"}:
            raise PrivateKeyMaterialError("secret_in_argv")
    reader = getpass_fn
    try:
        if reader is None:
            import getpass
            import warnings

            # stdlib warns before falling back to echoed stdin. Refuse that
            # fallback before it can consume a passphrase.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                value = getpass.getpass(f"{prompt}: ")
        else:
            value = reader(f"{prompt}: ")
    except Exception:
        raise PrivateKeyMaterialError("passphrase_prompt_failed") from None
    if not isinstance(value, str) or value == "":
        raise PrivateKeyMaterialError("passphrase_required")
    return value


# --- Joined revision WAL (CIMP-DUR-003) ------------------------------------
# Ciphertext objects are sealed before any journal write. The Kit coordinator
# stores the intent document in plaintext, so the intent carries only opaque
# refs and stable ids. Local WAL commit is not a network pin.

_REVISION_SCHEMA = "cg-revision-manifest-v1"
_INTENT_SCHEMA = "cg-revision-intent-v2"
_HEAD_NAME = "head.cgpe"
_HEAD_RECORD_MAGIC = b"CGJH\x01"
_OWNER_NAME = "owner.cgpe"
_RECOVERY_STATUS_NAME = "recovery.cgpe"
_LOCK_NAME = ".owner.lock"
_ROLE_NAMES = ("session", "fact_graph", "proof")
_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_LOCK_GUARD = threading.Lock()


def _process_lock(root: Path) -> threading.Lock:
    """Serialize owners inside one process. flock alone does not block threads."""

    key = str(root.resolve())
    with _PROCESS_LOCK_GUARD:
        lock = _PROCESS_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PROCESS_LOCKS[key] = lock
        return lock


class PrivateRevisionError(PrivateStorageError):
    """Joined session, fact-graph, and proof publication did not commit."""

    code = "private_revision_error"
    recoverable = True

    def __init__(self, message: str, *, code: str, state: str = "recoverable") -> None:
        super().__init__(message, code=code)
        self.recoverable = True
        self.state = state
        self.committed = False
        self.network_pinned = False


class PrivateRevisionInterrupted(PrivateRevisionError):
    """A crash boundary fired. Reopen and recover; do not treat this as commit."""

    def __init__(self, boundary: str, transaction_id: str) -> None:
        super().__init__(
            f"revision transaction interrupted at {boundary}",
            code="interrupted",
            state="recoverable",
        )
        self.boundary = boundary
        self.transaction_id = transaction_id


@dataclass(frozen=True)
class RevisionPublication:
    """Outcome of one joined revision attempt or recovery pass."""

    committed: bool
    state: str
    transaction_id: str
    effect_id: str
    revision: str | None
    acknowledgement_mode: str | None
    receipt_count: int
    network_pinned: bool = False
    local_only: bool = True
    replayed: int = 0
    rolled_back: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "committed": self.committed,
            "state": self.state,
            "transaction_id": self.transaction_id,
            "effect_id": self.effect_id,
            "revision": self.revision,
            "acknowledgement_mode": self.acknowledgement_mode,
            "receipt_count": self.receipt_count,
            "network_pinned": False,
            "local_only": True,
            "replication": "not_claimed",
            "replayed": self.replayed,
            "rolled_back": self.rolled_back,
        }


def _prefer_vendored_kit() -> None:
    """Import WAL from the pinned submodule, not a broken site-packages copy."""

    root = Path(__file__).resolve().parents[1] / "external" / "ipfs_kit_py"
    if not (root / "ipfs_kit_py" / "core" / "wal" / "writer.py").is_file():
        return
    entry = str(root)
    if entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)
    loaded = sys.modules.get("ipfs_kit_py")
    loaded_file = Path(getattr(loaded, "__file__", "") or "")
    if loaded is not None and root not in loaded_file.parents:
        for name in list(sys.modules):
            if name == "ipfs_kit_py" or name.startswith("ipfs_kit_py."):
                del sys.modules[name]


def _load_wal():
    _prefer_vendored_kit()
    try:
        from ipfs_kit_py.core.wal.contracts import (
            WALAcknowledgementMode,
            WALCorruptionDisposition,
            ack_requirements_for,
        )
        from ipfs_kit_py.core.wal.coordinator import (
            WALTransactionCoordinator,
            WALTransactionCrash,
            WALTransactionError,
        )
        from ipfs_kit_py.core.wal.segments import recover_segment
        from ipfs_kit_py.core.wal.writer import WALQueueFullError, WALWriterError
    except Exception as exc:
        raise PrivateRevisionError(
            "Kit WAL is unavailable",
            code="wal_unavailable",
            state="unavailable",
        ) from exc
    return {
        "WALAcknowledgementMode": WALAcknowledgementMode,
        "WALCorruptionDisposition": WALCorruptionDisposition,
        "ack_requirements_for": ack_requirements_for,
        "WALTransactionCoordinator": WALTransactionCoordinator,
        "WALTransactionCrash": WALTransactionCrash,
        "WALTransactionError": WALTransactionError,
        "recover_segment": recover_segment,
        "WALQueueFullError": WALQueueFullError,
        "WALWriterError": WALWriterError,
    }


def commit_acknowledged_by_receipt(result: Any) -> bool:
    """True only when a real Kit receipt meets a durable acknowledgement mode.

    Buffered and queued results are not commits. A caller-supplied ``durable``
    flag is ignored; the receipt must satisfy ``ack_requirements_for``.
    """

    wal = _load_wal()
    mode = getattr(result, "acknowledgement_mode", None)
    receipt = getattr(result, "fsync_receipt", None)
    if mode is None or receipt is None:
        return False
    requirements = wal["ack_requirements_for"](mode)
    if not requirements.may_claim_committed:
        return False
    if not (requirements.requires_file_fsync and requirements.requires_parent_directory_fsync):
        return False
    try:
        return bool(receipt.satisfies(requirements))
    except Exception:
        return False


class _ReceiptWriter:
    """Forward appends and keep only receipts the Kit writer actually returned."""

    def __init__(self, writer: Any) -> None:
        self._writer = writer
        self.receipts: list[Any] = []

    def append(self, *args: Any, **kwargs: Any) -> Any:
        result = self._writer.append(*args, **kwargs)
        if not commit_acknowledged_by_receipt(result):
            raise PrivateRevisionError(
                "WAL acknowledgement is not a durable commit receipt",
                code="durability_unproven",
                state="recoverable",
            )
        self.receipts.append(result)
        return result

    def close(self) -> None:
        close = getattr(self._writer, "close", None)
        if callable(close):
            close()


def _fsync_file(fd: int, fsync_file: Callable[[int], None] | None) -> None:
    operation = fsync_file or os.fsync
    try:
        operation(fd)
    except OSError as exc:
        raise PrivateRevisionError(
            "file fsync failed; revision was not published",
            code="file_fsync_failed",
            state="recoverable",
        ) from exc


def _fsync_directory(path: Path, fsync_directory: Callable[[int], None] | None) -> None:
    """Fsync a directory. Opening the directory must succeed; failure is not success."""

    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise PrivateRevisionError(
            "directory fsync could not be opened",
            code="directory_fsync_failed",
            state="unknown_durability",
        ) from exc
    try:
        operation = fsync_directory or os.fsync
        try:
            operation(descriptor)
        except OSError as exc:
            raise PrivateRevisionError(
                "directory fsync failed",
                code="directory_fsync_failed",
                state="unknown_durability",
            ) from exc
    finally:
        os.close(descriptor)


def _reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise PrivateRevisionError(
            "revision journal path is a symlink",
            code="journal_untrusted",
            state="recoverable",
        )


def _opaque_ref(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_write(
    directory: Path,
    name: str,
    payload: bytes,
    *,
    fsync_file: Callable[[int], None] | None,
    fsync_directory: Callable[[int], None] | None,
    before_replace: Callable[[], Any] | None = None,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    temporary = directory / ("." + uuid.uuid4().hex + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PrivateRevisionError("short write", code="write_error", state="recoverable")
            view = view[written:]
        _fsync_file(descriptor, fsync_file)
    except Exception:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    os.close(descriptor)
    _fsync_directory(directory, fsync_directory)
    try:
        if before_replace is not None and before_replace() is False:
            raise PrivateRevisionError("Publication admission refused.",
                code="publication_denied", state="aborted")
        os.replace(temporary, directory / name)
    except Exception:
        temporary.unlink(missing_ok=True)
        _fsync_directory(directory, fsync_directory)
        raise
    _fsync_directory(directory, fsync_directory)


def _read_exact(path: Path) -> bytes | None:
    if not path.exists():
        return None
    _reject_symlink(path)
    return path.read_bytes()


def _seal_role(
    payload: bytes,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    kind: str,
    revision: str,
    key: bytes,
    key_id: str,
    key_resolver: Callable[[str], bytes | None] | None = None,
) -> bytes:
    binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=kind,
        revision=revision,
        principal_id=principal_id,
    )
    return seal_private_artifact(payload, binding=binding, key=key, key_id=key_id)


def _open_role(
    envelope: bytes,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    kind: str,
    revision: str,
    key: bytes,
    key_id: str,
    key_resolver: Callable[[str], bytes | None] | None = None,
) -> bytes:
    binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=kind,
        revision=revision,
        principal_id=principal_id,
    )
    actual_id = parse_private_envelope(envelope)["key_id"]
    if actual_id != key_id and key_resolver is not None:
        key = key_resolver(actual_id)
        if key is None:
            raise PrivateArtifactIntegrityError("authentication_failed")
        key_id = actual_id
    return open_private_artifact(envelope, binding=binding, key=key, expected_key_id=key_id)


def _manifest_bytes(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _open_manifest(
    envelope: bytes,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    revision: str,
    key: bytes,
    key_id: str,
    key_resolver: Callable[[str], bytes | None] | None = None,
) -> dict[str, Any]:
    body = _open_role(
        envelope,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
        kind="revision-manifest",
        revision=revision,
        key=key,
        key_id=key_id,
        key_resolver=key_resolver,
    )
    document = json.loads(body.decode("utf-8"))
    if not isinstance(document, dict) or document.get("schema") != _REVISION_SCHEMA:
        raise PrivateRevisionError("revision manifest is not authentic", code="corrupt_manifest", state="recoverable")
    return document


def _journal_text_issue(path: Path) -> str | None:
    if not path.exists():
        return None
    _reject_symlink(path)
    data = path.read_bytes()
    if not data:
        return None
    lines = data.splitlines(keepends=True)
    for index, line in enumerate(lines):
        last = index == len(lines) - 1
        stripped = line.strip()
        if not stripped:
            if last:
                continue
            return "interior_invalid"
        try:
            value = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            if last and not line.endswith(b"\n"):
                return None
            return "interior_invalid"
        if not isinstance(value, dict):
            return "interior_invalid"
    return None


def _segment_issue(path: Path) -> str | None:
    wal = _load_wal()
    recovery = wal["recover_segment"](
        path,
        disposition=wal["WALCorruptionDisposition"].BOUND_AND_REPORT,
    )
    if not recovery.tail_corrupt:
        return None
    original = path.read_bytes()
    remainder = original[recovery.valid_bytes :]
    if b"IWAL1" in remainder[1:]:
        return "interior_invalid"
    # A torn tail is recoverable by the Kit prefix reader. Interior damage is not.
    if recovery.valid_bytes == 0 and len(original) > 8:
        return "interior_invalid"
    return None


def inspect_revision_journal(repository: str | Path) -> str | None:
    """Return a corruption code, or None when the journal is safe to replay.

    This never truncates, quarantines, or rewrites journal bytes.
    """

    root = Path(repository)
    before = _snapshot_bytes(root)
    try:
        wal_dir = root / "wal"
        if wal_dir.exists() and wal_dir.is_symlink():
            return "journal_untrusted"
        for name in ("transaction-decisions.jsonl", "transaction-replay.jsonl"):
            issue = _journal_text_issue(wal_dir / name)
            if issue:
                return issue
        records = wal_dir / "records"
        if records.is_symlink():
            return "journal_untrusted"
        if records.exists():
            for path in sorted(records.iterdir()):
                if not path.is_file() or path.is_symlink():
                    continue
                if path.suffix == ".corrupt":
                    return "interior_invalid"
                issue = _segment_issue(path)
                if issue:
                    return issue
        return None
    finally:
        after = _snapshot_bytes(root)
        if before != after:
            raise PrivateRevisionError(
                "journal inspection changed bytes",
                code="journal_mutated",
                state="recoverable",
            )


def _snapshot_bytes(root: Path) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    if not root.exists():
        return found
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            found[str(path.relative_to(root))] = path.read_bytes()
    return found


def _acquire_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    lock_path = root / _LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    import fcntl

    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except OSError as exc:
        os.close(descriptor)
        raise PrivateRevisionError(
            "revision owner lock failed",
            code="lock_unavailable",
            state="recoverable",
        ) from exc
    return descriptor


def _release_lock(descriptor: int) -> None:
    import fcntl

    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _store_object(
    root: Path,
    payload: bytes,
    *,
    fsync_file: Callable[[int], None] | None,
    fsync_directory: Callable[[int], None] | None,
) -> str:
    ref = _opaque_ref(payload)
    directory = root / "o"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / ref
    if destination.exists():
        if destination.read_bytes() != payload:
            raise PrivateRevisionError("opaque object collision", code="object_collision", state="recoverable")
        return ref
    _atomic_write(directory, ref, payload, fsync_file=fsync_file, fsync_directory=fsync_directory)
    return ref


def _object_bytes(root: Path, ref: str) -> bytes:
    if not isinstance(ref, str) or len(ref) != 64 or any(char not in "0123456789abcdef" for char in ref):
        raise PrivateRevisionError("opaque ref rejected", code="bad_ref", state="recoverable")
    path = root / "o" / ref
    data = _read_exact(path)
    if data is None or _opaque_ref(data) != ref:
        raise PrivateRevisionError("opaque object missing", code="missing_object", state="recoverable")
    return data


def _head_record(root: Path) -> tuple[bytes | None, str | None]:
    """Read one atomic head; the legacy pointer is consulted only for legacy bytes."""
    raw = _read_exact(root / _HEAD_NAME)
    if raw is None:
        return None, None
    if raw.startswith(_HEAD_RECORD_MAGIC):
        offset = len(_HEAD_RECORD_MAGIC)
        if len(raw) < offset + 2:
            raise PrivateRevisionError("head record is incomplete", code="corrupt_manifest")
        length = int.from_bytes(raw[offset:offset + 2], "big")
        try:
            revision = raw[offset + 2:offset + 2 + length].decode("ascii")
        except UnicodeError:
            raise PrivateRevisionError("head revision is invalid", code="corrupt_manifest") from None
        envelope = raw[offset + 2 + length:]
        if not 0 < length <= 128 or not revision.isdigit() or not envelope.startswith(ENVELOPE_MAGIC):
            raise PrivateRevisionError("head record is invalid", code="corrupt_manifest")
        return envelope, revision
    pointer = _read_exact(root / "head.rev")
    try:
        revision = pointer.decode("ascii").strip() if pointer else ""
    except UnicodeError:
        revision = ""
    if not raw.startswith(ENVELOPE_MAGIC) or not revision.isdigit():
        raise PrivateRevisionError("legacy head needs authenticated recovery", code="corrupt_manifest")
    return raw, revision


def _open_head(
    root: Path, *, tenant_id: str, case_id: str, principal_id: str,
    key: bytes, key_id: str, revision_hint: str | None = None,
    key_resolver: Callable[[str], bytes | None] | None = None,
) -> dict[str, Any] | None:
    envelope, revision = _head_record(root)
    if envelope is None:
        return None
    if revision_hint is not None and revision != revision_hint:
        raise PrivateRevisionError("head revision changed", code="revision_conflict")
    try:
        manifest = _open_manifest(envelope, tenant_id=tenant_id, case_id=case_id,
                                  principal_id=principal_id, key=key, key_id=key_id,
                                  revision=str(revision), key_resolver=key_resolver)
    except PrivateStorageError:
        raise PrivateRevisionError("revision head did not authenticate", code="authentication_failed") from None
    if str(manifest.get("revision")) != revision:
        raise PrivateRevisionError("authenticated revision differs", code="corrupt_manifest")
    return manifest


def _publish_head(
    root: Path, envelope: bytes, revision: str, *,
    fsync_file: Callable[[int], None] | None,
    fsync_directory: Callable[[int], None] | None,
    before_publish: Callable[[], Any] | None = None,
) -> None:
    encoded = str(revision).encode("ascii")
    if not 0 < len(encoded) <= 128 or not str(revision).isdigit():
        raise PrivateRevisionError("head revision is invalid", code="bad_revision")
    record = _HEAD_RECORD_MAGIC + len(encoded).to_bytes(2, "big") + encoded + envelope
    _atomic_write(root, _HEAD_NAME, record, fsync_file=fsync_file, fsync_directory=fsync_directory,
        **({"before_replace": before_publish} if before_publish is not None else {}))


def _authenticate_revision_owner(
    root: Path, *, tenant_id: str, case_id: str, principal_id: str, key: bytes,
    key_id: str, create: bool = False, fsync_file=None, fsync_directory=None,
    key_resolver: Callable[[str], bytes | None] | None = None,
) -> None:
    """Authenticate the caller before any WAL writer, replay, or compensation."""
    raw = _read_exact(root / _OWNER_NAME)
    options = dict(tenant_id=tenant_id, case_id=case_id, principal_id=principal_id,
                   key=key, key_id=key_id, kind="revision-owner", revision="1", key_resolver=key_resolver)
    marker = b"complaint-private-revision-owner@1"
    if raw is not None:
        try:
            if _open_role(raw, **options) != marker:
                raise PrivateArtifactIntegrityError("authentication_failed")
        except PrivateStorageError:
            raise PrivateRevisionError("revision owner did not authenticate", code="authentication_failed") from None
        return
    if not create:
        raise PrivateRevisionError("legacy repository owner proof is unavailable", code="owner_binding_unavailable")
    # Legacy committed heads can be admitted only by successful caller-bound
    # decryption. Uncommitted legacy debris has no safe ownership proof.
    if _read_exact(root / _HEAD_NAME) is not None:
        _open_head(root, tenant_id=tenant_id, case_id=case_id, principal_id=principal_id,
                   key=key, key_id=key_id, key_resolver=key_resolver)
    elif (root / "wal").exists() or (root / "o").exists():
        raise PrivateRevisionError("legacy repository owner proof is unavailable", code="owner_binding_unavailable")
    _atomic_write(root, _OWNER_NAME, _seal_role(marker, **options),
                  fsync_file=fsync_file, fsync_directory=fsync_directory)


def _recovery_generation(root: Path) -> str:
    entries = []
    aggregate = 0
    journal = root / "wal"
    if journal.exists():
        for path in sorted(journal.rglob("*")):
            if path.is_symlink():
                raise PrivateRevisionError("journal is untrusted", code="journal_untrusted")
            if not path.is_file():
                continue
            size = path.stat().st_size
            aggregate += size
            if size > 16 * 1024 * 1024 or aggregate > 64 * 1024 * 1024:
                raise PrivateRevisionError("journal exceeds its bound", code="journal_oversized")
            entries.append((str(path.relative_to(journal)), _opaque_ref(path.read_bytes())))
    return _opaque_ref(_manifest_bytes({"files": entries}))


def _recovery_status(root: Path, *, options: Mapping[str, Any], phase: str | None = None,
                     fsync_file=None, fsync_directory=None) -> Mapping[str, Any] | None:
    context = dict(options, kind="revision-recovery", revision="1")
    raw = _read_exact(root / _RECOVERY_STATUS_NAME)
    old = None
    if raw is not None:
        try:
            old = json.loads(_open_role(raw, **context))
        except (PrivateStorageError, ValueError, TypeError):
            raise PrivateRevisionError("recovery status did not authenticate", code="authentication_failed") from None
    if phase is None:
        return old
    document = {"phase": phase, "journal_generation": _recovery_generation(root)}
    if old != document:
        _atomic_write(root, _RECOVERY_STATUS_NAME, _seal_role(_manifest_bytes(document), **context),
                      fsync_file=fsync_file, fsync_directory=fsync_directory)
    return document


def private_revision_readiness(repository: str | Path, *, tenant_id: str, case_id: str,
                               principal_id: str, key: bytes, key_id: str, key_resolver: Callable[[str], bytes | None] | None = None) -> str:
    """Pure admission for canonical readers/writers, including a missing head.

    Owner/objects alone never prove an empty committed state. A first-commit
    crash must be authenticated and reconciled before the old session is used.
    """
    root = Path(repository)
    if not any((root / name).exists() for name in (_OWNER_NAME, _HEAD_NAME, "wal", "o")):
        return "new"
    options = dict(tenant_id=tenant_id, case_id=case_id, principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
    if (root / _HEAD_NAME).exists():
        manifest = _open_head(root, **options)
        if manifest is None:
            raise PrivateRevisionError("revision head changed", code="recovery_required")
        _require_committed_revision(root, manifest, **options)
        return "committed"
    _authenticate_revision_owner(root, **options)
    status = _recovery_status(root, options=options)
    if (isinstance(status, Mapping) and status.get("phase") == "recovered_empty"
        and status.get("journal_generation") == _recovery_generation(root)):
        return "empty"
    raise PrivateRevisionError("initialized revision needs authenticated recovery", code="recovery_required")


def _wal_identity(key: bytes, domain: bytes, value: str) -> str:
    # A keyed digest is an opaque stable identifier, not a plaintext digest of
    # an answer or an identifying caller label exposed in the WAL.
    return hmac.new(_require_data_key(key), b"cg-private-wal@1\x00" + domain + value.encode("utf-8"), hashlib.sha256).hexdigest()


def _intent_document(
    *,
    transaction_id: str,
    effect_id: str,
    expected_revision: str,
    revision: str,
    previous_head_ref: str,
    manifest_ref: str,
    objects: Mapping[str, str],
) -> dict[str, str]:
    document = {
        "schema": _INTENT_SCHEMA,
        "transaction_id": transaction_id,
        "effect_id": effect_id,
        "expected_revision": expected_revision,
        "revision": revision,
        "previous_head_ref": previous_head_ref,
        "manifest_ref": manifest_ref,
        "session_ref": objects["session"],
        "fact_graph_ref": objects["fact_graph"],
        "proof_ref": objects["proof"],
    }
    encoded = json.dumps(document)
    forbidden = ("answer", "source_span", "passphrase", "plaintext", "/", "\\")
    lowered = encoded.lower()
    for token in forbidden:
        if token in {"/", "\\"}:
            continue
        if token in lowered:
            raise PrivateRevisionError("intent rejected sensitive field", code="intent_rejected", state="recoverable")
    return document


def _apply_intent(root: Path, intent: Mapping[str, Any], *, install: bool, fsync_file, fsync_directory,
                  lineage: Mapping[str, Any] | None = None,
                  before_publish: Callable[[], Any] | None = None) -> bool:
    revision = str(intent.get("revision") or "")
    effect_id = str(intent.get("effect_id") or "")
    current_envelope, current_revision = _head_record(root)
    current = current_revision or ""
    current_ref = _opaque_ref(current_envelope) if current_envelope is not None else ""
    if install:
        if current == revision:
            return current_ref == intent.get("manifest_ref")
        if current.isdigit() and revision.isdigit() and int(current) > int(revision):
            # A later authenticated snapshot supersedes this committed effect.
            # Walk exact ciphertext-parent references; a number alone never
            # authorizes installing an older head or sharing an unrelated fork.
            reference = current_ref
            seen = set()
            intents = (lineage or {}).get("intents", {})
            while reference and reference not in seen and len(seen) < 4096:
                if reference == intent.get("manifest_ref"):
                    return True
                seen.add(reference)
                ancestor = intents.get(reference)
                if ancestor is None:
                    return False
                reference = str(ancestor.get("previous_head_ref") or "")
            return False
        expected = str(intent.get("expected_revision") or "")
        if current != expected and not (current == "" and expected in {"", "0"}):
            return False
        if current_ref != str(intent.get("previous_head_ref") or ""):
            return False
        envelope = _object_bytes(root, str(intent["manifest_ref"]))
        _publish_head(root, envelope, revision, fsync_file=fsync_file, fsync_directory=fsync_directory,
            **({"before_publish": before_publish} if before_publish is not None else {}))
        return True
    if current != revision:
        return True
    if current_ref != intent.get("manifest_ref"):
        return False
    previous = str(intent.get("previous_head_ref") or "")
    expected = str(intent.get("expected_revision") or "")
    if not previous:
        head = root / _HEAD_NAME
        rev = root / "head.rev"
        if head.exists():
            head.unlink()
        if rev.exists():
            rev.unlink()
        _fsync_directory(root, fsync_directory)
        return True
    envelope = _object_bytes(root, previous)
    _publish_head(root, envelope, expected, fsync_file=fsync_file, fsync_directory=fsync_directory)
    return True


def _authenticate_intent(root: Path, intent: Mapping[str, Any], *, tenant_id: str,
                         case_id: str, principal_id: str, key: bytes, key_id: str, key_resolver: Callable[[str], bytes | None] | None = None) -> None:
    """Bind every replay/rollback reference to an authenticated caller-owned revision."""
    revision = str(intent.get("revision") or "")
    expected = str(intent.get("expected_revision") or "")
    options = dict(tenant_id=tenant_id, case_id=case_id, principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
    try:
        manifest_envelope = _object_bytes(root, str(intent["manifest_ref"]))
        manifest_key_id = parse_private_envelope(manifest_envelope)["key_id"]
        identity_key = key if manifest_key_id == key_id else (
            key_resolver(manifest_key_id) if key_resolver is not None else None)
        if identity_key is None:
            raise PrivateArtifactIntegrityError("authentication_failed")
        manifest = _open_manifest(manifest_envelope,
                                  revision=revision, **options)
        objects = manifest.get("objects") or {}
        keyed = (intent.get("transaction_id") == _wal_identity(identity_key, b"transaction\x00", str(manifest.get("transaction_id") or ""))
                 and intent.get("effect_id") == _wal_identity(identity_key, b"effect\x00", str(manifest.get("effect_id") or "")))
        legacy = (intent.get("schema") == "cg-revision-intent-v1"
                  and intent.get("transaction_id") == manifest.get("transaction_id")
                  and intent.get("effect_id") == manifest.get("effect_id"))
        valid = (intent.get("schema") in {_INTENT_SCHEMA, "cg-revision-intent-v1"}
                 and str(manifest.get("revision")) == revision
                 and str(manifest.get("parent_revision")) == expected
                 and (keyed or legacy))
        for role in _ROLE_NAMES:
            ref = str(objects.get(role) or "")
            valid = valid and intent.get(role + "_ref") == ref
            _open_role(_object_bytes(root, ref), kind=role, revision=revision, **options)
        previous = str(intent.get("previous_head_ref") or "")
        if expected == "0":
            valid = valid and not previous
        else:
            parent = _open_manifest(_object_bytes(root, previous), revision=expected, **options)
            valid = valid and str(parent.get("revision")) == expected
        if not valid:
            raise PrivateRevisionError("intent identity differs", code="authentication_failed")
    except (PrivateStorageError, KeyError, TypeError, ValueError):
        raise PrivateRevisionError("revision intent did not authenticate", code="authentication_failed") from None


def _native_commit_transactions(root: Path) -> set[str]:
    """Read actual checksum-verified Kit markers; never construct receipt flags."""
    observed: set[str] = set()
    wal = _load_wal()
    records = root / "wal" / "records"
    if records.exists():
        for path in sorted(records.glob("*.wal")):
            _reject_symlink(path)
            if _segment_issue(path):
                raise PrivateRevisionError("native WAL is corrupt", code="journal_corrupt")
            recovered = wal["recover_segment"](path, disposition=wal["WALCorruptionDisposition"].BOUND_AND_REPORT)
            for record in recovered.records:
                if (getattr(record.kind, "value", "") == "commit"
                    and record.acknowledgement_mode == wal["WALAcknowledgementMode"].WAL_FSYNC_PARENT
                    and record.fsync_receipt_id):
                    observed.add(record.transaction_id)
    return observed


def _authenticate_recovery_journal(root: Path, **options) -> dict[str, Any]:
    intents: dict[str, Any] = {}
    committed: set[str] = set()
    path = root / "wal" / "transaction-decisions.jsonl"
    raw = _read_exact(path)
    if raw is None:
        return {"intents": intents, "committed": committed}
    if len(raw) > 16 * 1024 * 1024:
        raise PrivateRevisionError("recovery journal exceeds its bound", code="journal_oversized")
    lines = raw.splitlines(keepends=True)
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except (ValueError, UnicodeError):
            if index == len(lines) - 1 and not line.endswith(b"\n"):
                break
            raise PrivateRevisionError("recovery journal is corrupt", code="journal_corrupt") from None
        if not isinstance(record, Mapping):
            raise PrivateRevisionError("recovery journal is corrupt", code="journal_corrupt")
        if record.get("kind") == "commit":
            committed.add(str(record.get("transaction_id") or ""))
        if record.get("kind") == "intent":
            intent = record.get("intent")
            if not isinstance(intent, Mapping) or record.get("transaction_id") != intent.get("transaction_id") or record.get("effect_id") != intent.get("effect_id"):
                raise PrivateRevisionError("recovery identity differs", code="authentication_failed")
            _authenticate_intent(root, intent, **options)
            reference = str(intent["manifest_ref"])
            if reference in intents and intents[reference] != intent:
                raise PrivateRevisionError("recovery lineage differs", code="authentication_failed")
            intents[reference] = dict(intent)
    native_commits = _native_commit_transactions(root)
    intent_transactions = {item["transaction_id"] for item in intents.values()}
    if committed - native_commits or (native_commits - committed) & intent_transactions:
        raise PrivateRevisionError("native commit and coordinator decision need reconciliation", code="recovery_required")
    return {"intents": intents, "committed": committed}


def _require_committed_revision(root: Path, manifest: Mapping[str, Any], **options) -> None:
    """Require the real coordinator decision and checksum-verified Kit commit marker.

    A published effect without the later acknowledged commit is recovery-required,
    never a visible committed revision. No writer or replay is constructed here.
    """
    lineage = _authenticate_recovery_journal(root, **options)
    envelope, revision = _head_record(root)
    reference = _opaque_ref(envelope) if envelope is not None else ""
    intent = lineage["intents"].get(reference)
    if intent is None or str(manifest.get("revision")) != revision or intent["transaction_id"] not in lineage["committed"]:
        raise PrivateRevisionError("revision needs recovery before it is readable", code="recovery_required")
    # _authenticate_recovery_journal has independently reconciled every
    # committed decision against the actual framed Native Kit marker.
    if intent["transaction_id"] not in _native_commit_transactions(root):
        raise PrivateRevisionError("native commit receipt marker is unavailable", code="recovery_required")


def _identity_args(transaction_id: str | None, effect_id: str | None) -> tuple[str, str]:
    transaction = str(transaction_id or "").strip() or uuid.uuid4().hex
    effect = str(effect_id or "").strip() or uuid.uuid4().hex
    for value in (transaction, effect):
        if len(value) > 128 or any(char in value for char in "\n\r/\x00"):
            raise PrivateRevisionError("unstable identifier rejected", code="bad_id", state="recoverable")
    return transaction, effect


def commit_private_revision(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    expected_revision: str | None,
    session: bytes,
    fact_graph: bytes,
    proof: bytes,
    transaction_id: str | None = None,
    effect_id: str | None = None,
    crash_injector: Callable[..., Any] | None = None,
    writer: Any | None = None,
    fsync_file: Callable[[int], None] | None = None,
    fsync_directory: Callable[[int], None] | None = None,
    before_publish: Callable[[], Any] | None = None,
    key_resolver: Callable[[str], bytes | None] | None = None,
    publication_scope: Callable[[], Any] | None = None,
) -> RevisionPublication:
    """Publish one answer revision across session, fact graph, and proof.

    Objects are sealed first. The visible head changes only inside the effect,
    after the intent is durable. ``network_pinned`` stays false.

    ``before_publish`` is a trusted in-process late admission check. It runs
    after authenticated encryption and head staging/fsync, inside the revision
    CAS effect immediately before replacing the visible head. A refusal raises through the normal terminal
    WAL abort path; recovery cannot replay that refused transaction. Readers
    and key/session reproofs may be used by the callback, but it must not start
    another revision write under this same lock.
    """

    if before_publish is not None and not callable(before_publish):
        raise TypeError("before_publish must be a trusted callable")
    if publication_scope is not None and not callable(publication_scope):
        raise TypeError("publication_scope must be a trusted scope factory")
    wal = _load_wal()
    root = Path(repository)
    transaction_id, effect_id = _identity_args(transaction_id, effect_id)
    process_lock = _process_lock(root)
    process_lock.acquire()
    lock = None
    coordinator = None
    inner = None
    owns_writer = writer is None
    try:
        issue = inspect_revision_journal(root) if root.exists() else None
        if issue:
            raise PrivateRevisionError(
                f"revision journal is corrupt ({issue}); original bytes were preserved",
                code="journal_corrupt",
                state="recoverable",
            )
        lock = _acquire_lock(root)
        expected = "0" if expected_revision in {None, ""} else str(expected_revision)
        _authenticate_revision_owner(root, tenant_id=tenant_id, case_id=case_id,
            principal_id=principal_id, key=key, key_id=key_id, create=True,
            fsync_file=fsync_file, fsync_directory=fsync_directory, key_resolver=key_resolver)
        head_raw, recorded_revision = _head_record(root)
        current = recorded_revision or "0"
        if current in {"",}:
            current = "0"
        if current != expected:
            raise PrivateRevisionError(
                "stale revision",
                code="revision_conflict",
                state="conflict",
            )
        if expected != "0":
            current_manifest = _open_manifest(
                head_raw or b"",
                tenant_id=tenant_id,
                case_id=case_id,
                principal_id=principal_id,
                revision=expected,
                key=key,
                key_id=key_id,
                key_resolver=key_resolver,
            )
            _require_committed_revision(root, current_manifest, tenant_id=tenant_id,
                case_id=case_id, principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
            if current_manifest.get("effect_id") == effect_id and current_manifest.get("transaction_id") == transaction_id:
                return RevisionPublication(
                    True, "committed", transaction_id, effect_id, expected,
                    wal["WALAcknowledgementMode"].WAL_FSYNC_PARENT.value, 0,
                )
        else:
            if head_raw not in {None, b""}:
                raise PrivateRevisionError("unexpected head", code="revision_conflict", state="conflict")
        _recovery_status(root, options=dict(tenant_id=tenant_id, case_id=case_id,
            principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver), phase="pending",
            fsync_file=fsync_file, fsync_directory=fsync_directory)
        next_revision = str(int(expected) + 1) if expected.isdigit() else uuid.uuid4().hex
        sealed = {}
        for role, payload in (("session", session), ("fact_graph", fact_graph), ("proof", proof)):
            sealed[role] = _seal_role(
                payload,
                tenant_id=tenant_id,
                case_id=case_id,
                principal_id=principal_id,
                kind=role,
                revision=next_revision,
                key=key,
                key_id=key_id,
            )
        previous_head_ref = ""
        if head_raw:
            previous_head_ref = _store_object(root, head_raw, fsync_file=fsync_file, fsync_directory=fsync_directory)
        object_refs = {
            role: _store_object(root, blob, fsync_file=fsync_file, fsync_directory=fsync_directory)
            for role, blob in sealed.items()
        }
        manifest = {
            "schema": _REVISION_SCHEMA,
            "revision": next_revision,
            "parent_revision": expected,
            "transaction_id": transaction_id,
            "effect_id": effect_id,
            "objects": object_refs,
        }
        manifest_envelope = _seal_role(
            _manifest_bytes(manifest),
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            kind="revision-manifest",
            revision=next_revision,
            key=key,
            key_id=key_id,
        )
        manifest_ref = _store_object(
            root, manifest_envelope, fsync_file=fsync_file, fsync_directory=fsync_directory,
        )
        wal_transaction_id = _wal_identity(key, b"transaction\x00", transaction_id)
        wal_effect_id = _wal_identity(key, b"effect\x00", effect_id)
        intent = _intent_document(
            transaction_id=wal_transaction_id,
            effect_id=wal_effect_id,
            expected_revision=expected,
            revision=next_revision,
            previous_head_ref=previous_head_ref,
            manifest_ref=manifest_ref,
            objects=object_refs,
        )
        inner = writer
        if inner is None:
            inner = __import__(
                "ipfs_kit_py.core.wal.writer", fromlist=["WALWriter"]
            ).WALWriter(root / "wal" / "records")
        bridge = _ReceiptWriter(inner)
        coordinator = wal["WALTransactionCoordinator"](
            root / "wal",
            writer=bridge,
            crash_injector=crash_injector,
        )

        publication_hold = ExitStack()
        publication_entered = False
        def admit_publication():
            nonlocal publication_entered
            if publication_scope is not None and not publication_entered:
                publication_hold.enter_context(publication_scope())
                publication_entered = True
            if before_publish is not None:
                return before_publish()

        def effect() -> bool:
            _authenticate_intent(root, intent, tenant_id=tenant_id, case_id=case_id,
                                 principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
            return _apply_intent(
                root, intent, install=True, fsync_file=fsync_file, fsync_directory=fsync_directory,
                **({"before_publish": admit_publication} if before_publish is not None or publication_scope is not None else {}),
            )

        def compensate() -> bool:
            _authenticate_intent(root, intent, tenant_id=tenant_id, case_id=case_id,
                                 principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
            return _apply_intent(
                root, intent, install=False, fsync_file=fsync_file, fsync_directory=fsync_directory,
            )

        with publication_hold:
            try:
                result = coordinator.execute(
                    intent,
                    effect,
                    compensate,
                    transaction_id=wal_transaction_id,
                    effect_id=wal_effect_id,
                )
            except wal["WALTransactionCrash"] as exc:
                raise PrivateRevisionInterrupted(str(getattr(exc, "args", ["crash"])[0]), transaction_id) from exc
            except wal["WALQueueFullError"] as exc:
                raise PrivateRevisionError("WAL backpressure", code="wal_backpressure", state="recoverable") from exc
            except wal["WALWriterError"] as exc:
                raise PrivateRevisionError("WAL writer is closed", code="wal_closed", state="recoverable") from exc
            except wal["WALTransactionError"] as exc:
                raise PrivateRevisionError(str(exc), code="transaction_failed", state="recoverable") from exc
            except PrivateRevisionError:
                raise
            if not result.committed or not bridge.receipts:
                raise PrivateRevisionError("commit receipt missing", code="durability_unproven", state="recoverable")
            mode = bridge.receipts[-1].acknowledgement_mode
            return RevisionPublication(
                True,
                "committed",
                transaction_id,
                effect_id,
                next_revision,
                getattr(mode, "value", str(mode)),
                len(bridge.receipts),
            )
    finally:
        if coordinator is not None:
            coordinator.close()
        if owns_writer and inner is not None:
            inner.close()
        if lock is not None:
            _release_lock(lock)
        process_lock.release()


def recover_private_revision(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    fsync_file: Callable[[int], None] | None = None,
    fsync_directory: Callable[[int], None] | None = None,
    key_resolver: Callable[[str], bytes | None] | None = None,
) -> RevisionPublication:
    """Replay a committed revision or compensate an open one. A second call is a no-op."""

    wal = _load_wal()
    root = Path(repository)
    issue = inspect_revision_journal(root)
    if issue:
        raise PrivateRevisionError(
            f"revision journal is corrupt ({issue}); original bytes were preserved",
            code="journal_corrupt",
            state="recoverable",
        )
    process_lock = _process_lock(root)
    process_lock.acquire()
    lock = None
    coordinator = None
    writer = None
    try:
        lock = _acquire_lock(root)
        _authenticate_revision_owner(root, tenant_id=tenant_id, case_id=case_id,
            principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
        _open_head(root, tenant_id=tenant_id, case_id=case_id,
                   principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
        lineage = _authenticate_recovery_journal(root, tenant_id=tenant_id, case_id=case_id,
                   principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
        writer = __import__(
            "ipfs_kit_py.core.wal.writer", fromlist=["WALWriter"]
        ).WALWriter(root / "wal" / "records")
        bridge = _ReceiptWriter(writer)
        coordinator = wal["WALTransactionCoordinator"](root / "wal", writer=bridge)

        def replay(intent: Mapping[str, Any], effect_id: str) -> bool:
            if str(intent.get("effect_id") or "") != effect_id:
                return False
            _authenticate_intent(root, intent, tenant_id=tenant_id, case_id=case_id,
                                 principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
            return _apply_intent(root, intent, install=True, fsync_file=fsync_file, fsync_directory=fsync_directory, lineage=lineage)

        def rollback(intent: Mapping[str, Any], effect_id: str) -> bool:
            if str(intent.get("effect_id") or "") != effect_id:
                return False
            _authenticate_intent(root, intent, tenant_id=tenant_id, case_id=case_id,
                                 principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
            return _apply_intent(root, intent, install=False, fsync_file=fsync_file, fsync_directory=fsync_directory, lineage=lineage)

        try:
            counts = coordinator.recover(replay, rollback)
        except wal["WALTransactionError"] as exc:
            raise PrivateRevisionError(str(exc), code="recovery_failed", state="recoverable") from exc
        _, revision = _head_record(root)
        manifest = None
        if revision:
            try:
                manifest = _open_head(
                    root,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    principal_id=principal_id,
                    key=key,
                    key_id=key_id,
                    revision_hint=revision,
                    key_resolver=key_resolver,
                )
            except PrivateRevisionError:
                raise
        if manifest is not None:
            _require_committed_revision(root, manifest, tenant_id=tenant_id, case_id=case_id,
                                       principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
        committed = bool(manifest) and counts["rolled_back"] == 0 and (
            counts["replayed"] > 0 or revision is not None
        )
        # A rollback that restored a parent still has a head. Distinguish by
        # whether this recovery invoked rollback.
        if counts["rolled_back"]:
            state = "compensated"
            committed = False
        elif manifest is None:
            state = "compensated"
            committed = False
        else:
            state = "committed"
            committed = True
        if manifest is None:
            _recovery_status(root, options=dict(tenant_id=tenant_id, case_id=case_id,
                principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver), phase="recovered_empty",
                fsync_file=fsync_file, fsync_directory=fsync_directory)
        effect = str((manifest or {}).get("effect_id") or "")
        transaction = str((manifest or {}).get("transaction_id") or "")
        return RevisionPublication(
            committed,
            state,
            transaction,
            effect,
            revision if committed or manifest else None,
            wal["WALAcknowledgementMode"].WAL_FSYNC_PARENT.value if bridge.receipts else None,
            len(bridge.receipts),
            replayed=counts["replayed"],
            rolled_back=counts["rolled_back"],
        )
    finally:
        if coordinator is not None:
            coordinator.close()
        if writer is not None:
            writer.close()
        if lock is not None:
            _release_lock(lock)
        process_lock.release()


def read_private_revision(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    key_resolver: Callable[[str], bytes | None] | None = None,
) -> dict[str, Any] | None:
    """Open the published head. Wrong key or case raises; nothing is rewritten."""

    root = Path(repository)
    readiness = private_revision_readiness(root, tenant_id=tenant_id, case_id=case_id,
        principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
    if readiness in {"new", "empty"}:
        return None
    manifest = _open_head(
        root,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
        key=key,
        key_id=key_id,
        key_resolver=key_resolver,
    )
    if manifest is None:
        raise PrivateRevisionError("committed revision head changed during read", code="recovery_required")
    _require_committed_revision(root, manifest, tenant_id=tenant_id, case_id=case_id,
                               principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
    revision = str(manifest["revision"])
    opened: dict[str, Any] = {"manifest": manifest, "revision": revision}
    for role in _ROLE_NAMES:
        ref = str((manifest.get("objects") or {})[role])
        envelope = _object_bytes(root, ref)
        opened[role] = _open_role(
            envelope,
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            kind=role,
            revision=revision,
            key=key,
            key_id=key_id,
            key_resolver=key_resolver,
        )
    opened["network_pinned"] = False
    return opened


@contextmanager
def private_revision_source_scope(repository: str | Path):
    """Hold an existing joined source against its normal CAS writers.

    The yielded hash identifies opaque ciphertext only. It grants no read,
    key, source, law or proof authority. Trusted provisioning must authenticate
    the actual snapshot with ``read_private_revision`` while this hold lasts.
    No repository or ownership marker is created by this observer.
    """
    root = Path(os.path.abspath(repository))
    if root.resolve(strict=True) != root:
        raise PrivateRevisionError("Source path is aliased.", code="source_unavailable")
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise PrivateRevisionError("Source is not privately owned.", code="source_unavailable")
    lock = _process_lock(root)
    lock.acquire()
    descriptor = -1
    try:
        descriptor = os.open(root / _LOCK_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600:
            raise PrivateRevisionError("Source lock changed.", code="source_unavailable")
        import fcntl
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        def opaque_identity():
            material = {}
            for name in (_HEAD_NAME, "head.rev"):
                try:
                    fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
                except FileNotFoundError:
                    if name == _HEAD_NAME:
                        raise PrivateRevisionError("Source head is missing.", code="source_unavailable") from None
                    continue
                try:
                    item = os.fstat(fd)
                    if (not stat.S_ISREG(item.st_mode) or item.st_uid != os.getuid() or item.st_nlink != 1
                            or stat.S_IMODE(item.st_mode) != 0o600 or not 0 < item.st_size <= 8 * 1024 * 1024):
                        raise PrivateRevisionError("Source head is untrusted.", code="source_unavailable")
                    raw = bytearray()
                    while len(raw) <= item.st_size:
                        chunk = os.read(fd, min(65536, item.st_size + 1 - len(raw)))
                        if not chunk:
                            break
                        raw.extend(chunk)
                    after = os.fstat(fd)
                    signature = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
                    if len(raw) != item.st_size or signature(item) != signature(after):
                        raise PrivateRevisionError("Source changed while read.", code="revision_conflict")
                    material[name] = hashlib.sha256(raw).hexdigest()
                finally:
                    os.close(fd)
            return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        identity = opaque_identity()
        yield {"head_sha256": identity, "opaque_ciphertext_only": True, "authority": False}
        current = (root / _LOCK_NAME).lstat()
        current_root = root.lstat()
        if (root.resolve(strict=True) != root
                or (current_root.st_dev, current_root.st_ino) != (info.st_dev, info.st_ino)
                or not stat.S_ISDIR(current_root.st_mode) or current_root.st_uid != os.getuid()
                or stat.S_IMODE(current_root.st_mode) & 0o077
                or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
                or not stat.S_ISREG(current.st_mode) or current.st_uid != os.getuid()
                or current.st_nlink != 1 or stat.S_IMODE(current.st_mode) != 0o600
                or opaque_identity() != identity):
            raise PrivateRevisionError("Source changed during admission.", code="revision_conflict")
    finally:
        if descriptor >= 0:
            try:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        lock.release()


# --- Case manifest CAS (CIMP-DUR-004) --------------------------------------
# One encrypted manifest binds answer, fact-graph, legal-rule-source,
# evaluation, and proof revisions to an opaque parent generation. The public
# head is only that generation and the manifest hash. Filenames, labels, and
# provenance stay inside the envelope. Local publication is compare-and-swap.
# IrohManifestStore.compare_and_swap is used only when the caller selects the
# Iroh backend and supplies a store; importing this module does not start Iroh.

_CASE_SCHEMA = "cg-case-manifest-v1"
_CASE_ROLES = (
    ("answer", "answer"),
    ("fact_graph", "fact-graph"),
    ("legal_rule_source", "legal-rule-source"),
    ("evaluation", "evaluation"),
    ("proof", "proof"),
)
# Complete case snapshots add the owners a later reader must see together.
# A partial set is not published and is not treated as a new empty case.
_COMPLETE_CASE_ROLES = _CASE_ROLES + (
    ("knowledge_graph", "knowledge-graph"),
    ("dependency_graph", "dependency-graph"),
    ("inquiries", "inquiries"),
    ("proof_references", "proof-references"),
    ("grants", "grants"),
    ("workflow_revisions", "workflow-revisions"),
)
_CASE_HEAD_NAME = "case-head"
_CASE_GENERATIONS = "generations"
_CASE_STAMP = "2026-01-01T00:00:00Z"


class CaseManifestConflict(PrivateRevisionError):
    """The expected head and hash were not the current head. Nothing was replaced."""

    def __init__(self) -> None:
        super().__init__(
            "case manifest head conflict",
            code="manifest_conflict",
            state="conflict",
        )


@dataclass(frozen=True)
class CaseManifestPublication:
    """In-memory result of a case-manifest publish or recovery. Not a new receipt file."""

    committed: bool
    state: str
    generation: str | None
    parent_generation: str | None
    manifest_hash: str | None
    parent_hash: str | None
    minted_completion: bool
    backend: str
    code: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "committed": self.committed,
            "state": self.state,
            "generation": self.generation,
            "parent_generation": self.parent_generation,
            "manifest_hash": self.manifest_hash,
            "parent_hash": self.parent_hash,
            "minted_completion": self.minted_completion,
            "backend": self.backend,
            "code": self.code,
            "network_pinned": False,
            "local_only": self.backend == "local",
        }


def _case_root(repository: str | Path) -> Path:
    return Path(repository) / "case-manifest"


def _hex_generation(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise PrivateRevisionError(f"{label} is not an opaque ref", code="bad_ref", state="recoverable")
    return value


def _expected_ref(value: str | None, label: str) -> str:
    if value in {None, ""}:
        return ""
    return _hex_generation(str(value), label)


def _parse_case_head(raw: bytes | None) -> tuple[str, str]:
    if raw is None or raw == b"":
        return "", ""
    try:
        text = raw.decode("ascii")
    except UnicodeError as exc:
        raise PrivateRevisionError("case head is unreadable", code="corrupt_manifest", state="recoverable") from exc
    if text.endswith("\n"):
        text = text[:-1]
    generation, separator, manifest_hash = text.partition(" ")
    if separator != " " or not generation or not manifest_hash or " " in manifest_hash:
        raise PrivateRevisionError("case head is unreadable", code="corrupt_manifest", state="recoverable")
    return _hex_generation(generation, "generation"), _hex_generation(manifest_hash, "manifest_hash")


def _case_head(root: Path) -> tuple[str, str]:
    return _parse_case_head(_read_exact(root / _CASE_HEAD_NAME))


def _write_case_head(root: Path, generation: str, manifest_hash: str, *, fsync_file, fsync_directory) -> None:
    payload = f"{generation} {manifest_hash}\n".encode("ascii")
    _atomic_write(root, _CASE_HEAD_NAME, payload, fsync_file=fsync_file, fsync_directory=fsync_directory)


def _append_generation(root: Path, generation: str, manifest_hash: str, *, fsync_file, fsync_directory) -> None:
    line = f"{generation} {manifest_hash}\n".encode("ascii")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(root / _CASE_GENERATIONS, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(line)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PrivateRevisionError("generation log write failed", code="write_error", state="recoverable")
            view = view[written:]
        _fsync_file(descriptor, fsync_file)
    finally:
        os.close(descriptor)
    _fsync_directory(root, fsync_directory)


def _generation_index(root: Path) -> list[tuple[str, str]]:
    raw = _read_exact(root / _CASE_GENERATIONS)
    if raw is None or raw == b"":
        return []
    if not raw.endswith(b"\n"):
        raw = raw.rsplit(b"\n", 1)[0]
        if raw and not raw.endswith(b"\n"):
            raw += b"\n"
        if not raw:
            return []
    found: list[tuple[str, str]] = []
    for line in raw.splitlines():
        try:
            generation, manifest_hash = _parse_case_head(line)
        except PrivateRevisionError as exc:
            raise PrivateRevisionError(
                "generation log is corrupt",
                code="corrupt_manifest",
                state="recoverable",
            ) from exc
        if generation:
            found.append((generation, manifest_hash))
    return found


def _role_payload(artifacts: Mapping[str, Any], name: str) -> tuple[bytes, str]:
    if name not in artifacts:
        raise PrivateRevisionError("case role is missing", code="role_missing", state="recoverable")
    value = artifacts[name]
    if isinstance(value, (bytes, bytearray)):
        body = bytes(value)
        revision = name
    elif isinstance(value, Mapping) and isinstance(value.get("body"), (bytes, bytearray)):
        body = bytes(value["body"])
        revision = str(value.get("revision") or name)
    else:
        raise PrivateRevisionError("case role payload is unusable", code="role_missing", state="recoverable")
    if not body:
        raise PrivateRevisionError("case role payload is empty", code="role_missing", state="recoverable")
    _require_label(revision)
    return body, revision


def _open_case_document(
    root: Path,
    generation: str,
    manifest_hash: str,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
) -> dict[str, Any] | None:
    """Return the authenticated document, or None when the blob is missing or stale."""

    if not generation:
        return None
    path = root / "o" / generation
    raw = _read_exact(path)
    if raw is None or _opaque_ref(raw) != generation:
        return None
    try:
        body = _open_role(
            raw,
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            kind="case-manifest",
            revision=manifest_hash,
            key=key,
            key_id=key_id,
        )
        document = json.loads(body.decode("utf-8"))
    except (PrivateStorageError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(document, dict) or document.get("schema") != _CASE_SCHEMA:
        return None
    if document.get("complete") is True and not _complete_role_index(document.get("roles")):
        return None
    if _opaque_ref(_manifest_bytes(document)) != manifest_hash:
        return None
    if document.get("parent_generation") in {None, ""}:
        if document.get("parent_hash") not in {None, ""}:
            return None
    else:
        try:
            _hex_generation(str(document.get("parent_generation")), "parent")
            _hex_generation(str(document.get("parent_hash")), "parent_hash")
        except PrivateRevisionError:
            return None
    return document


def _chain_complete(root: Path, generation: str, manifest_hash: str, **options: Any) -> dict[str, Any] | None:
    seen: set[str] = set()
    current_generation = generation
    current_hash = manifest_hash
    document = None
    while current_generation:
        if current_generation in seen or len(seen) > 4096:
            return None
        seen.add(current_generation)
        document = _open_case_document(root, current_generation, current_hash, **options)
        if document is None:
            return None
        parent = str(document.get("parent_generation") or "")
        parent_hash = str(document.get("parent_hash") or "")
        if not parent:
            return document if current_generation == generation else _open_case_document(root, generation, manifest_hash, **options)
        current_generation = parent
        current_hash = parent_hash
    return None


def _case_options(tenant_id: str, case_id: str, principal_id: str, key: bytes, key_id: str) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "case_id": case_id,
        "principal_id": principal_id,
        "key": key,
        "key_id": key_id,
    }


def _publish_iroh_cas(
    store: Any,
    *,
    namespace_id: str,
    writer_id: str,
    envelope: bytes,
    parent_revision: int | None,
    parent_manifest_hash: str,
) -> tuple[int, str]:
    """Delegate head publication to Kit IrohManifestStore. Does not start a sidecar."""

    try:
        import asyncio

        from blake3 import blake3
        from ipfs_kit_py.iroh.errors import IrohConflictError
        from ipfs_kit_py.iroh.manifest import DirectoryManifest, IrohManifestStore, ManifestEntry, ParentRevision
    except Exception as exc:
        raise PrivateRevisionError(
            "Iroh manifest store is unavailable",
            code="iroh_unavailable",
            state="unavailable",
        ) from exc
    if not isinstance(store, IrohManifestStore):
        raise PrivateRevisionError(
            "Iroh manifest store is unavailable",
            code="iroh_unavailable",
            state="unavailable",
        )
    ref = _opaque_ref(envelope)
    entries = [
        ManifestEntry.root(mtime=_CASE_STAMP),
        ManifestEntry(
            ref,
            "file",
            False,
            0o600,
            _CASE_STAMP,
            {},
            blake3(envelope).hexdigest(),
            len(envelope),
        ),
    ]
    if parent_manifest_hash == "":
        async def run():
            return await store.create_namespace(
                namespace_id,
                writer_id,
                entries,
                created_at=_CASE_STAMP,
            )
    else:
        if parent_revision is None:
            raise PrivateRevisionError(
                "Iroh parent head is unavailable",
                code="iroh_parent_unavailable",
                state="recoverable",
            )
        manifest = DirectoryManifest.create(
            namespace_id,
            writer_id,
            int(parent_revision) + 1,
            entries,
            parent_revision=ParentRevision(int(parent_revision), parent_manifest_hash),
            created_at=_CASE_STAMP,
        )

        async def run():
            return await store.publish(
                manifest,
                expected_revision=int(parent_revision),
                expected_manifest_hash=parent_manifest_hash,
            )

    try:
        snapshot = asyncio.run(run())
    except IrohConflictError as exc:
        raise CaseManifestConflict() from exc
    return int(snapshot.head.revision), str(snapshot.head.manifest_hash)


def _complete_role_index(roles: Any) -> bool:
    if not isinstance(roles, Mapping):
        return False
    for public_name, kind in _COMPLETE_CASE_ROLES:
        slot = roles.get(public_name)
        if not isinstance(slot, Mapping):
            return False
        if slot.get("kind") != kind or not slot.get("ref") or not slot.get("revision"):
            return False
    return True


def publish_case_manifest(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    expected_head: str | None,
    expected_hash: str | None,
    artifacts: Mapping[str, Any],
    private_names: Mapping[str, Any] | None = None,
    backend: str = "local",
    iroh_store: Any = None,
    complete: bool = False,
    fail_before_head: bool = False,
    fsync_file: Callable[[int], None] | None = None,
    fsync_directory: Callable[[int], None] | None = None,
) -> CaseManifestPublication:
    """Seal one case manifest and publish it only when the expected head still matches.

    ``expected_head`` is the opaque parent generation. ``expected_hash`` is that
    generation's manifest hash. A mismatch raises :class:`CaseManifestConflict`
    and leaves the published head unchanged.
    """

    if backend not in {"local", "iroh"}:
        raise PrivateRevisionError("case manifest backend is unknown", code="backend_rejected", state="unavailable")
    root = _case_root(repository)
    expected_generation = _expected_ref(expected_head, "expected_head")
    expected_manifest_hash = _expected_ref(expected_hash, "expected_hash")
    options = _case_options(tenant_id, case_id, principal_id, key, key_id)
    names = dict(private_names or {})
    sealed_roles: dict[str, bytes] = {}
    role_index: dict[str, dict[str, str]] = {}
    role_table = _COMPLETE_CASE_ROLES if complete else _CASE_ROLES
    for public_name, kind in role_table:
        body, revision = _role_payload(artifacts, public_name)
        envelope = _seal_role(body, kind=kind, revision=revision, **options)
        sealed_roles[public_name] = envelope
        role_index[public_name] = {"revision": revision, "ref": _opaque_ref(envelope), "kind": kind}
    process_lock = _process_lock(root)
    process_lock.acquire()
    lock = None
    try:
        lock = _acquire_lock(root)
        try:
            current_generation, current_hash = _case_head(root)
        except PrivateRevisionError as exc:
            raise PrivateRevisionError(str(exc), code="corrupt_manifest", state="recoverable") from exc
        if current_generation != expected_generation or current_hash != expected_manifest_hash:
            raise CaseManifestConflict()
        parent = None
        if current_generation:
            parent = _chain_complete(root, current_generation, current_hash, **options)
            if parent is None:
                raise PrivateRevisionError(
                    "current case head is not a verified complete manifest",
                    code="stale_head",
                    state="recoverable",
                )
        iroh_revision = None
        iroh_hash = ""
        if backend == "iroh":
            parent_revision = None if parent is None else parent.get("iroh_revision")
            parent_hash = "" if parent is None else str(parent.get("iroh_manifest_hash") or "")
            if parent is not None and (not isinstance(parent_revision, int) or not parent_hash):
                raise PrivateRevisionError(
                    "Iroh parent head is unavailable",
                    code="iroh_parent_unavailable",
                    state="recoverable",
                )
            namespace_id = hmac.new(
                _require_data_key(key),
                b"cg-case-manifest-namespace\x00" + tenant_id.encode("utf-8") + b"\x00" + case_id.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            writer_id = hmac.new(
                _require_data_key(key),
                b"cg-case-manifest-writer\x00" + principal_id.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            # The Iroh document receives only the opaque ciphertext ref. The
            # envelope is sealed below; this call happens before the local head
            # moves so a conflict cannot hide the previous generation.
            placeholder = _seal_role(
                _manifest_bytes({"schema": _CASE_SCHEMA, "preview": role_index, "names": names, "parent": current_generation}),
                kind="case-manifest",
                revision=current_hash or "0",
                **options,
            )
            iroh_revision, iroh_hash = _publish_iroh_cas(
                iroh_store,
                namespace_id=namespace_id,
                writer_id=writer_id,
                envelope=placeholder,
                parent_revision=None if parent is None else int(parent_revision),
                parent_manifest_hash=parent_hash,
            )
        for envelope in sealed_roles.values():
            _store_object(root, envelope, fsync_file=fsync_file, fsync_directory=fsync_directory)
        document = {
            "schema": _CASE_SCHEMA,
            "parent_generation": current_generation,
            "parent_hash": current_hash,
            "roles": role_index,
            "private_names": names,
            "iroh_revision": iroh_revision,
            "iroh_manifest_hash": iroh_hash,
            "backend": backend,
        }
        if complete:
            document["complete"] = True
            if not _complete_role_index(role_index):
                raise PrivateRevisionError("case role is missing", code="role_missing", state="recoverable")
        manifest_hash = _opaque_ref(_manifest_bytes(document))
        manifest_envelope = _seal_role(
            _manifest_bytes(document),
            kind="case-manifest",
            revision=manifest_hash,
            **options,
        )
        generation = _store_object(root, manifest_envelope, fsync_file=fsync_file, fsync_directory=fsync_directory)
        verified = _open_case_document(root, generation, manifest_hash, **options)
        if verified != document:
            raise PrivateRevisionError("case manifest readback failed", code="readback_mismatch", state="recoverable")
        if fail_before_head:
            raise PrivateRevisionInterrupted("case-head", generation)
        _write_case_head(root, generation, manifest_hash, fsync_file=fsync_file, fsync_directory=fsync_directory)
        _append_generation(root, generation, manifest_hash, fsync_file=fsync_file, fsync_directory=fsync_directory)
        return CaseManifestPublication(
            True,
            "committed",
            generation,
            current_generation or None,
            manifest_hash,
            current_hash or None,
            True,
            backend,
        )
    finally:
        if lock is not None:
            _release_lock(lock)
        process_lock.release()


def read_case_manifest(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
) -> dict[str, Any] | None:
    """Open the current head. A missing or stale blob is recoverable and writes nothing."""

    root = _case_root(repository)
    before = _snapshot_bytes(root)
    try:
        if not (root / _CASE_HEAD_NAME).exists():
            return None
        generation, manifest_hash = _case_head(root)
        options = _case_options(tenant_id, case_id, principal_id, key, key_id)
        document = _chain_complete(root, generation, manifest_hash, **options)
        if document is None:
            raise PrivateRevisionError(
                "case manifest blob is missing or stale",
                code="stale_head",
                state="recoverable",
            )
        opened: dict[str, Any] = {
            "manifest": document,
            "generation": generation,
            "manifest_hash": manifest_hash,
            "parent_generation": document.get("parent_generation") or None,
            "roles": {},
            "envelopes": {},
            "private_names": document.get("private_names") or {},
            "complete": document.get("complete") is True,
            "minted_completion": False,
        }
        role_table = _COMPLETE_CASE_ROLES if document.get("complete") is True else _CASE_ROLES
        if document.get("complete") is True and not _complete_role_index(document.get("roles")):
            raise PrivateRevisionError(
                "case manifest blob is missing or stale",
                code="stale_head",
                state="recoverable",
            )
        for public_name, kind in role_table:
            slot = (document.get("roles") or {}).get(public_name) or {}
            ref = str(slot.get("ref") or "")
            revision = str(slot.get("revision") or "")
            envelope = _object_bytes(root, ref)
            opened["envelopes"][public_name] = envelope
            opened["roles"][public_name] = _open_role(
                envelope,
                kind=kind,
                revision=revision,
                **options,
            )
        return opened
    finally:
        if _snapshot_bytes(root) != before:
            raise PrivateRevisionError("case manifest read changed bytes", code="journal_mutated", state="recoverable")


def recover_case_manifest(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    fsync_file: Callable[[int], None] | None = None,
    fsync_directory: Callable[[int], None] | None = None,
) -> CaseManifestPublication:
    """Point the head at the newest verified complete generation already on disk.

    Recovery never seals a replacement manifest and never mints a completed
    publication for a missing or stale blob.
    """

    root = _case_root(repository)
    options = _case_options(tenant_id, case_id, principal_id, key, key_id)
    process_lock = _process_lock(root)
    process_lock.acquire()
    lock = None
    try:
        if not root.exists():
            return CaseManifestPublication(False, "recoverable", None, None, None, None, False, "local", "missing_repository")
        lock = _acquire_lock(root)
        candidates = _generation_index(root)
        try:
            head = _case_head(root)
        except PrivateRevisionError:
            head = ("", "")
        if head[0] and head not in candidates:
            candidates.append(head)
        chosen: tuple[str, str] | None = None
        chosen_document: dict[str, Any] | None = None
        for generation, manifest_hash in candidates:
            document = _chain_complete(root, generation, manifest_hash, **options)
            if document is not None:
                chosen = (generation, manifest_hash)
                chosen_document = document
        if chosen is None or chosen_document is None:
            return CaseManifestPublication(
                False, "recoverable", None, None, None, None, False, "local", "stale_head",
            )
        if head != chosen:
            _write_case_head(root, chosen[0], chosen[1], fsync_file=fsync_file, fsync_directory=fsync_directory)
        return CaseManifestPublication(
            False,
            "recovered",
            chosen[0],
            str(chosen_document.get("parent_generation") or "") or None,
            chosen[1],
            str(chosen_document.get("parent_hash") or "") or None,
            False,
            str(chosen_document.get("backend") or "local"),
            "stale_head",
        )
    finally:
        if lock is not None:
            _release_lock(lock)
        process_lock.release()


def replay_acknowledged_case_revision(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    generation: str,
    manifest_hash: str,
) -> CaseManifestPublication:
    """Confirm an acknowledged generation without publishing a replacement.

    Replay reads the current head. It does not seal a new manifest, move the
    head backward, or create a case when the acknowledged blob is missing.
    """

    root = _case_root(repository)
    before = _snapshot_bytes(root)
    try:
        acknowledged = _hex_generation(generation, "generation")
        acknowledged_hash = _hex_generation(manifest_hash, "manifest_hash")
        options = _case_options(tenant_id, case_id, principal_id, key, key_id)
        if not (root / _CASE_HEAD_NAME).exists():
            return CaseManifestPublication(
                False, "recoverable", None, None, None, None, False, "local", "missing_repository",
            )
        try:
            head_generation, head_hash = _case_head(root)
        except PrivateRevisionError:
            return CaseManifestPublication(
                False, "recoverable", None, None, None, None, False, "local", "corrupt_manifest",
            )
        document = _chain_complete(root, acknowledged, acknowledged_hash, **options)
        if document is None or (document.get("complete") is True and not _complete_role_index(document.get("roles"))):
            return CaseManifestPublication(
                False, "recoverable", head_generation or None, None, head_hash or None, None, False, "local", "stale_head",
            )
        if head_generation == acknowledged and head_hash == acknowledged_hash:
            return CaseManifestPublication(
                False,
                "replayed",
                acknowledged,
                str(document.get("parent_generation") or "") or None,
                acknowledged_hash,
                str(document.get("parent_hash") or "") or None,
                False,
                str(document.get("backend") or "local"),
            )
        return CaseManifestPublication(
            False,
            "preserved",
            head_generation,
            str(document.get("parent_generation") or "") or None,
            head_hash,
            str(document.get("parent_hash") or "") or None,
            False,
            str(document.get("backend") or "local"),
            "manifest_conflict",
        )
    finally:
        if _snapshot_bytes(root) != before:
            raise PrivateRevisionError("case manifest replay changed bytes", code="journal_mutated", state="recoverable")


# Replica policy is explicit. Importing this module, publishing in local private
# mode, and ordinary case reads do not open a remote provider. A replica counts
# only after readback matches the ciphertext digest and the requested version.
# Queued, deferred, and offline pin acknowledgements stay uncounted. An
# unavailable provider returns a reconciliation receipt with the next retry and
# does not sleep on the caller.

_REMOTE_STORAGE_ACTIVATIONS = 0
_REPLICA_MODES = frozenset({"local_private", "private_remote"})
_UNCOUNTED_REPLICA_STATES = frozenset({"queued", "deferred", "offline", "unavailable", "pin_requested"})
_REPLICA_NAME = re.compile(r"^(?:o/[0-9a-f]{64}|case-head|generations)$")


def remote_storage_activation_count() -> int:
    """How many times this process invoked a remote replica provider."""

    return _REMOTE_STORAGE_ACTIVATIONS


@dataclass(frozen=True)
class ReplicaPolicy:
    """Desired and minimum verified ciphertext replicas, including the local primary."""

    desired: int
    minimum: int
    mode: str = "local_private"
    max_attempts: int = 3
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0

    def __post_init__(self) -> None:
        if type(self.desired) is not int or type(self.minimum) is not int:
            raise ValueError("replica_policy_not_integral")
        if self.desired < 1 or self.minimum < 1 or self.minimum > self.desired:
            raise ValueError("replica_policy_bounds")
        if self.mode not in _REPLICA_MODES:
            raise ValueError("replica_policy_mode")
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("replica_policy_attempts")
        if (
            isinstance(self.base_backoff_seconds, bool)
            or isinstance(self.max_backoff_seconds, bool)
            or not isinstance(self.base_backoff_seconds, (int, float))
            or not isinstance(self.max_backoff_seconds, (int, float))
            or self.base_backoff_seconds < 0
            or self.max_backoff_seconds < self.base_backoff_seconds
        ):
            raise ValueError("replica_policy_backoff")


def configure_replica_policy(
    *,
    desired: int,
    minimum: int,
    mode: str = "local_private",
    max_attempts: int = 3,
    base_backoff_seconds: float = 1.0,
    max_backoff_seconds: float = 30.0,
) -> ReplicaPolicy:
    """Build a replica policy. ``local_private`` never contacts remote providers."""

    return ReplicaPolicy(
        desired=desired,
        minimum=minimum,
        mode=mode,
        max_attempts=max_attempts,
        base_backoff_seconds=base_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
    )


def select_private_storage_mode(mode: str) -> ReplicaPolicy:
    """Choose local private storage without constructing a remote client."""

    if mode != "local_private":
        raise ValueError("remote_mode_requires_explicit_policy")
    return configure_replica_policy(desired=1, minimum=1, mode="local_private")


def _replica_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _replica_clock(clock: Callable[[], float] | None) -> float:
    if clock is None:
        return time.time()
    value = clock()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("replica_clock")
    return float(value)


def _backoff_seconds(policy: ReplicaPolicy, attempts: int) -> float:
    shift = max(0, attempts - 1)
    delay = float(policy.base_backoff_seconds) * (2 ** min(shift, 20))
    return min(float(policy.max_backoff_seconds), delay)


def _ciphertext_catalog(root: Path, version: str) -> list[dict[str, str]]:
    catalog: list[dict[str, str]] = []
    objects = root / "o"
    names: list[Path] = []
    if objects.is_dir():
        names.extend(path for path in objects.iterdir() if path.is_file() and not path.is_symlink())
    for label in (_CASE_HEAD_NAME, _CASE_GENERATIONS):
        path = root / label
        if path.is_file() and not path.is_symlink():
            names.append(path)
    for path in sorted(names, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if _REPLICA_NAME.fullmatch(relative) is None:
            continue
        payload = path.read_bytes()
        catalog.append({"name": relative, "digest": _replica_digest(payload), "version": version})
    return catalog


def _catalog_bytes(root: Path, entry: Mapping[str, str]) -> bytes:
    relative = str(entry.get("name") or "")
    if _REPLICA_NAME.fullmatch(relative) is None:
        raise PrivateRevisionError("replica name rejected", code="bad_ref", state="recoverable")
    path = root.joinpath(*relative.split("/"))
    payload = _read_exact(path)
    if payload is None or _replica_digest(payload) != entry.get("digest"):
        raise PrivateRevisionError("replica source missing", code="missing_object", state="recoverable")
    return payload


def _local_replica_observations(root: Path, catalog: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in catalog:
        relative = str(entry["name"])
        payload = root.joinpath(*relative.split("/")).read_bytes()
        matched = _replica_digest(payload) == entry["digest"]
        rows.append({
            "provider_id": "local-primary",
            "role": "primary",
            "name": relative,
            "state": "verified" if matched else "readback_mismatch",
            "counted": matched,
            "digest_match": matched,
            "version_match": True,
            "version": entry["version"],
        })
    return rows


def _provider_id(provider: Any, index: int) -> str:
    value = getattr(provider, "provider_id", None)
    if isinstance(value, str) and value and value != "local-primary" and "/" not in value and "\\" not in value:
        return value
    return f"remote-{index}"


def _observe_remote_provider(
    provider: Any,
    provider_id: str,
    root: Path,
    catalog: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    global _REMOTE_STORAGE_ACTIVATIONS
    rows: list[dict[str, Any]] = []
    try:
        for entry in catalog:
            payload = _catalog_bytes(root, entry)
            _REMOTE_STORAGE_ACTIVATIONS += 1
            acknowledgement = provider.put(
                entry["name"],
                payload,
                digest=entry["digest"],
                version=entry["version"],
            )
            if not isinstance(acknowledgement, Mapping):
                acknowledgement = {}
            state = str(acknowledgement.get("state") or "unavailable")
            digest_match = acknowledgement.get("digest") == entry["digest"]
            version_match = acknowledgement.get("version") == entry["version"]
            readback_match = False
            if state == "verified" and digest_match and version_match:
                try:
                    loaded = provider.get(entry["name"])
                except Exception:
                    loaded = None
                    state = "unavailable"
                readback_match = isinstance(loaded, (bytes, bytearray)) and bytes(loaded) == payload
            counted = state == "verified" and digest_match and version_match and readback_match
            if state in _UNCOUNTED_REPLICA_STATES:
                counted = False
            rows.append({
                "provider_id": provider_id,
                "role": "remote",
                "name": entry["name"],
                "state": state,
                "counted": counted,
                "digest_match": digest_match and readback_match,
                "version_match": version_match,
                "version": entry["version"],
            })
    except Exception:
        return [], {
            "provider_id": provider_id,
            "error_category": "unavailable",
            "attempts": 1,
            "exhausted": False,
        }
    return rows, None


def _replica_receipt(
    policy: ReplicaPolicy,
    catalog: Sequence[Mapping[str, str]],
    observations: Sequence[Mapping[str, Any]],
    unavailable: Sequence[Mapping[str, Any]],
    *,
    now: float,
    generation: str | None,
    manifest_hash: str | None,
    network_sharing_started: bool,
) -> dict[str, Any]:
    by_provider: dict[str, list[Mapping[str, Any]]] = {}
    for row in observations:
        by_provider.setdefault(str(row["provider_id"]), []).append(row)
    verified = [
        provider_id
        for provider_id, rows in by_provider.items()
        if rows and all(bool(item.get("counted")) for item in rows) and len(rows) == len(catalog)
    ]
    uncounted = [
        {"provider_id": row["provider_id"], "name": row["name"], "state": row["state"]}
        for row in observations
        if not row.get("counted")
    ]
    pending = []
    for item in unavailable:
        attempts = int(item["attempts"])
        exhausted = bool(item.get("exhausted")) or attempts >= policy.max_attempts
        if item.get("preserve_schedule"):
            next_at = None if exhausted else item.get("next_retry_at")
        else:
            delay = None if exhausted else _backoff_seconds(policy, attempts)
            next_at = None if delay is None else now + delay
        pending.append({
            "provider_id": item["provider_id"],
            "error_category": "unavailable",
            "attempts": attempts,
            "exhausted": exhausted,
            "next_retry_at": next_at,
        })
    verified_count = len(verified)
    return {
        "status": "reconciliation_required" if pending else "ready",
        "mode": policy.mode,
        "desired": policy.desired,
        "minimum": policy.minimum,
        "verified_replicas": verified_count,
        "verified_providers": verified,
        "meets_minimum": verified_count >= policy.minimum,
        "meets_desired": verified_count >= policy.desired,
        "uncounted": uncounted,
        "unavailable_providers": pending,
        "catalog": [dict(entry) for entry in catalog],
        "generation": generation,
        "manifest_hash": manifest_hash,
        "network_sharing_started": bool(network_sharing_started),
        "synchronous_wait_seconds": 0,
        "waited": False,
    }


_WORKSPACE_LEDGER = "replica-ledger"
_WORKSPACE_FRAME = "primary.frame"
_WORKSPACE_OWNER = "owner.json"
_WORKSPACE_CATALOG = "catalog.json"
_WORKSPACE_PENDING = "publication.json"
_WORKSPACE_KIND = "workspace-replica"
_WORKSPACE_BINDING_REVISION = "current"
_UPSTREAM_REPLICATION_SUITES = (
    "tests/runtime_readiness/replication/test_replica_contracts.py",
    "tests/runtime_readiness/replication/test_reconciler.py",
    "tests/runtime_readiness/replication/test_joined_convergence.py",
)
_PLACED_REPLICA_STATES = frozenset({"stored", "pinned", "available", "verified"})


def replica_policy(
    *,
    desired_replicas: int,
    minimum_replicas: int,
    mode: str = "local_private",
    remote_providers: Sequence[str] = (),
    max_attempts: int = 3,
    base_backoff_seconds: float = 1.0,
    max_backoff_seconds: float = 30.0,
) -> ReplicaPolicy:
    """Explicit workspace replica policy. Naming providers does not contact them."""

    del remote_providers
    return configure_replica_policy(
        desired=desired_replicas,
        minimum=minimum_replicas,
        mode=mode,
        max_attempts=max_attempts,
        base_backoff_seconds=base_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
    )


def _workspace_root(repository: str | Path) -> Path:
    return Path(repository)


def _workspace_ledger(repository: str | Path) -> Path:
    return _workspace_root(repository) / _WORKSPACE_LEDGER


def _pack_workspace_generation(revision: str, complaint: bytes, fact_graph: bytes, proof: bytes) -> bytes:
    if not isinstance(revision, str) or not revision or len(revision) > 128:
        raise PrivateStorageError("replica revision rejected", code="bad_ref")

    def _part(blob: bytes) -> bytes:
        if not isinstance(blob, (bytes, bytearray)) or isinstance(blob, memoryview):
            raise PrivateStorageError("replica payload rejected", code="bad_ref")
        payload = bytes(blob)
        if len(payload) > 8_000_000:
            raise PrivateStorageError("replica payload rejected", code="bad_ref")
        return len(payload).to_bytes(4, "big") + payload

    return _part(revision.encode("utf-8")) + _part(complaint) + _part(fact_graph) + _part(proof)


def _unpack_workspace_generation(payload: bytes) -> dict[str, Any]:
    view = memoryview(payload)
    parts: list[bytes] = []
    for _ in range(4):
        if len(view) < 4:
            raise PrivateStorageError("replica generation is incomplete", code="readback_mismatch")
        size = int.from_bytes(view[:4], "big")
        view = view[4:]
        if size > len(view):
            raise PrivateStorageError("replica generation is incomplete", code="readback_mismatch")
        parts.append(bytes(view[:size]))
        view = view[size:]
    if view:
        raise PrivateStorageError("replica generation is incomplete", code="readback_mismatch")
    try:
        revision = parts[0].decode("utf-8")
    except UnicodeError as exc:
        raise PrivateStorageError("replica generation is incomplete", code="readback_mismatch") from exc
    return {
        "revision": revision,
        "complaint": parts[1],
        "fact_graph": parts[2],
        "proof": parts[3],
    }


def _seal_workspace_frame(
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    revision: str,
    complaint: bytes,
    fact_graph: bytes,
    proof: bytes,
) -> bytes:
    return _seal_role(
        _pack_workspace_generation(revision, complaint, fact_graph, proof),
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
        kind=_WORKSPACE_KIND,
        revision=_WORKSPACE_BINDING_REVISION,
        key=key,
        key_id=key_id,
    )


def _open_workspace_frame(
    frame: bytes,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
) -> dict[str, Any]:
    try:
        opened = _open_role(
            frame,
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            kind=_WORKSPACE_KIND,
            revision=_WORKSPACE_BINDING_REVISION,
            key=key,
            key_id=key_id,
        )
        return _unpack_workspace_generation(opened)
    except PrivateStorageError:
        raise
    except Exception as exc:
        raise PrivateStorageError("replica generation is unreadable", code="readback_mismatch") from exc


def _read_json_file(path: Path) -> dict[str, Any] | None:
    raw = _read_exact(path)
    if raw is None:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PrivateStorageError("replica ledger is unreadable", code="corrupt_manifest") from exc
    if not isinstance(value, dict):
        raise PrivateStorageError("replica ledger is unreadable", code="corrupt_manifest")
    return value


def _workspace_identity(tenant_id: str, case_id: str, principal_id: str, key_id: str) -> dict[str, str]:
    return {
        "tenant_id": tenant_id,
        "case_id": case_id,
        "principal_id": principal_id,
        "key_id": key_id,
    }


def _assert_workspace_owner(ledger: Path, identity: Mapping[str, str]) -> None:
    current = _read_json_file(ledger / _WORKSPACE_OWNER)
    if current is None:
        return
    for field in ("tenant_id", "case_id", "principal_id"):
        if current.get(field) != identity[field]:
            raise PrivateStorageError("replica owner mismatch", code="owner_conflict")


def _bounded_provider_call(method: Callable[..., Any], timeout_seconds: float | None, **kwargs: Any) -> Any:
    call_kwargs = dict(kwargs)
    call_kwargs["timeout_seconds"] = timeout_seconds

    def _invoke() -> Any:
        try:
            return method(**call_kwargs)
        except Exception as exc:
            return {"status": "unavailable", "error_category": type(exc).__name__}

    if timeout_seconds is None:
        timeout_seconds = 5.0
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= 60):
        raise PrivateStorageError("replica timeout rejected", code="replica_timeout")
    box: dict[str, Any] = {}

    def _run() -> None:
        box["value"] = _invoke()

    worker = threading.Thread(target=_run, name="replica-provider-call", daemon=True)
    started = time.monotonic()
    worker.start()
    worker.join(float(timeout_seconds))
    if worker.is_alive() or "value" not in box:
        return {"status": "unavailable", "error_category": "timeout", "elapsed": time.monotonic() - started}
    return box["value"]


def _workspace_receipt(
    policy: ReplicaPolicy,
    *,
    primary_verified: bool,
    placements: list[dict[str, Any]],
) -> dict[str, Any]:
    verified = sum(1 for row in placements if row.get("counted"))
    unavailable = [str(row["provider"]) for row in placements if row.get("provider") != "local-primary" and not row.get("counted")]
    if not primary_verified or verified < policy.minimum:
        status = "unavailable"
    elif verified < policy.desired or unavailable:
        status = "degraded"
    else:
        status = "ready"
    return {
        "status": status,
        "primary_verified": primary_verified,
        "verified_replica_count": verified,
        "meets_minimum": verified >= policy.minimum and primary_verified,
        "meets_desired": verified >= policy.desired and primary_verified,
        "unavailable_providers": unavailable,
        "placements": placements,
        "synchronous_wait_seconds": 0,
        "waited": False,
        "mode": policy.mode,
    }


def _local_frame_placement(ledger: Path, digest: str) -> tuple[bool, dict[str, Any]]:
    path = ledger / _WORKSPACE_FRAME
    payload = _read_exact(path)
    matched = payload is not None and _replica_digest(payload) == digest
    return matched, {
        "provider": "local-primary",
        "counted": matched,
        "state": "verified" if matched else "readback_mismatch",
        "digest_match": matched,
    }


def _observe_workspace_provider(
    name: str,
    provider: Any,
    *,
    digest: str,
    version: str,
    frame: bytes,
    timeout_seconds: float | None,
    place: bool,
) -> dict[str, Any]:
    global _REMOTE_STORAGE_ACTIVATIONS
    _REMOTE_STORAGE_ACTIVATIONS += 1
    state = "unavailable"
    if place:
        placed = _bounded_provider_call(
            provider.place,
            timeout_seconds,
            digest=digest,
            version=version,
            frame=frame,
        )
        if not isinstance(placed, Mapping):
            placed = {}
        state = str(placed.get("status") or placed.get("state") or "unavailable")
        if state not in _PLACED_REPLICA_STATES or state in _UNCOUNTED_REPLICA_STATES:
            return {"provider": name, "counted": False, "state": state, "digest_match": False, "version_match": False}
    loaded = _bounded_provider_call(provider.readback, timeout_seconds, digest=digest, version=version)
    if not isinstance(loaded, Mapping):
        loaded = {}
    remote_frame = loaded.get("frame")
    digest_match = isinstance(remote_frame, (bytes, bytearray)) and _replica_digest(bytes(remote_frame)) == digest and bytes(remote_frame) == frame
    version_match = loaded.get("version") == version
    status = str(loaded.get("status") or "unavailable")
    counted = status == "available" and digest_match and version_match and status not in _UNCOUNTED_REPLICA_STATES
    return {
        "provider": name,
        "counted": counted,
        "state": status if not counted else "verified",
        "digest_match": digest_match,
        "version_match": version_match,
    }


def _write_workspace_bytes(ledger: Path, name: str, payload: bytes) -> None:
    _atomic_write(ledger, name, payload, fsync_file=None, fsync_directory=None)


def _publish_workspace_replica(
    repository: str | Path,
    *,
    policy: ReplicaPolicy,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    revision: str,
    complaint: bytes,
    fact_graph: bytes,
    proof: bytes,
    providers: Mapping[str, Any] | None,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    if not isinstance(policy, ReplicaPolicy):
        raise ValueError("replica_policy_required")
    if not isinstance(complaint, (bytes, bytearray)) or not isinstance(fact_graph, (bytes, bytearray)) or not isinstance(proof, (bytes, bytearray)):
        raise PrivateStorageError("replica payload rejected", code="bad_ref")
    ledger = _workspace_ledger(repository)
    identity = _workspace_identity(tenant_id, case_id, principal_id, key_id)
    frame = _seal_workspace_frame(
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
        key=key,
        key_id=key_id,
        revision=revision,
        complaint=bytes(complaint),
        fact_graph=bytes(fact_graph),
        proof=bytes(proof),
    )
    digest = _replica_digest(frame)
    lock = _process_lock(ledger)
    lock.acquire()
    descriptor = None
    try:
        descriptor = _acquire_lock(ledger)
        _assert_workspace_owner(ledger, identity)
        if _read_json_file(ledger / _WORKSPACE_OWNER) is None:
            _write_workspace_bytes(ledger, _WORKSPACE_OWNER, json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        catalog = {
            "digest": digest,
            "version": revision,
            "revision": revision,
            "desired": policy.desired,
            "minimum": policy.minimum,
            "mode": policy.mode,
            "providers": sorted(str(name) for name in (providers or {})),
        }
        # Record the exact predecessor and complete next catalog before the
        # frame replacement. Recovery accepts only this interrupted transition.
        previous_catalog = _read_exact(ledger / _WORKSPACE_CATALOG) or b""
        intent = {"previous_catalog_sha256": _replica_digest(previous_catalog), "catalog": catalog}
        _write_workspace_bytes(ledger, _WORKSPACE_PENDING,
                               json.dumps(intent, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        _write_workspace_bytes(ledger, _WORKSPACE_FRAME, frame)
        _write_workspace_bytes(ledger, _WORKSPACE_CATALOG, json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    finally:
        if descriptor is not None:
            _release_lock(descriptor)
        lock.release()
    primary_verified, local_row = _local_frame_placement(ledger, digest)
    placements = [local_row]
    if policy.mode == "private_remote" and providers:
        for name, provider in providers.items():
            placements.append(
                _observe_workspace_provider(
                    str(name),
                    provider,
                    digest=digest,
                    version=revision,
                    frame=frame,
                    timeout_seconds=timeout_seconds,
                    place=True,
                )
            )
    return _workspace_receipt(policy, primary_verified=primary_verified, placements=placements)


def _catalog_policy(catalog: Mapping[str, Any] | None) -> ReplicaPolicy:
    if not catalog:
        return configure_replica_policy(desired=1, minimum=1, mode="local_private")
    return configure_replica_policy(
        desired=int(catalog.get("desired") or 1),
        minimum=int(catalog.get("minimum") or 1),
        mode=str(catalog.get("mode") or "local_private"),
    )


def _reconcile_workspace_replicas(
    repository: str | Path,
    *,
    providers: Mapping[str, Any] | None,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    ledger = _workspace_ledger(repository)
    catalog = _read_json_file(ledger / _WORKSPACE_CATALOG)
    policy = _catalog_policy(catalog)
    digest = str((catalog or {}).get("digest") or "")
    version = str((catalog or {}).get("version") or "")
    primary_verified, local_row = _local_frame_placement(ledger, digest) if digest else (False, {
        "provider": "local-primary",
        "counted": False,
        "state": "missing",
        "digest_match": False,
    })
    frame = _read_exact(ledger / _WORKSPACE_FRAME) if primary_verified else b""
    placements = [local_row]
    selected = providers or {}
    if policy.mode == "private_remote":
        for name, provider in selected.items():
            placements.append(
                _observe_workspace_provider(
                    str(name),
                    provider,
                    digest=digest,
                    version=version,
                    frame=frame if primary_verified else b"",
                    timeout_seconds=timeout_seconds,
                    place=False,
                )
            )
    return _workspace_receipt(policy, primary_verified=primary_verified, placements=placements)


def restore_encrypted_workspace(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    providers: Mapping[str, Any] | None = None,
    timeout_seconds: float | None = None,
    clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Open the local primary, or repair it from a verified ciphertext replica."""

    del clock
    _reject_tombstoned_case(repository, tenant_id, case_id)
    ledger = _workspace_ledger(repository)
    identity = _workspace_identity(tenant_id, case_id, principal_id, key_id)
    _assert_workspace_owner(ledger, identity)
    options = {
        "tenant_id": tenant_id,
        "case_id": case_id,
        "principal_id": principal_id,
        "key": key,
        "key_id": key_id,
    }
    lock = _process_lock(ledger)
    with lock:
        descriptor = _acquire_lock(ledger)
        try:
            _assert_workspace_owner(ledger, identity)
            local = _read_exact(ledger / _WORKSPACE_FRAME)
            catalog_bytes = _read_exact(ledger / _WORKSPACE_CATALOG) or b""
            catalog = _read_json_file(ledger / _WORKSPACE_CATALOG)
            digest_matches = local is not None and (catalog is None or _replica_digest(local) == catalog.get("digest"))
            interrupted_catalog = None
            if local is not None and not digest_matches:
                intent = _read_json_file(ledger / _WORKSPACE_PENDING) or {}
                following = intent.get("catalog")
                if (isinstance(following, dict)
                        and intent.get("previous_catalog_sha256") == _replica_digest(catalog_bytes)
                        and following.get("digest") == _replica_digest(local)):
                    interrupted_catalog = following
            if digest_matches or interrupted_catalog is not None:
                opened = _open_workspace_frame(local, **options)
                if interrupted_catalog is not None:
                    if opened["revision"] != interrupted_catalog.get("version"):
                        raise PrivateStorageError("replica publication version mismatch", code="readback_mismatch")
                    _write_workspace_bytes(ledger, _WORKSPACE_CATALOG,
                                           json.dumps(interrupted_catalog, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                    catalog = interrupted_catalog
                opened["source"] = "local"
                opened["status"] = "ready"
                return opened
        finally:
            _release_lock(descriptor)
    if not catalog or not catalog.get("digest") or not catalog.get("version"):
        raise PrivateStorageError("verified replica unavailable", code="replica_unavailable")
    digest = str(catalog["digest"])
    version = str(catalog["version"])
    timed_out = False
    for provider in (providers or {}).values():
        loaded = _bounded_provider_call(provider.readback, timeout_seconds, digest=digest, version=version)
        if not isinstance(loaded, Mapping):
            continue
        if loaded.get("error_category") == "timeout" or loaded.get("status") == "timeout":
            timed_out = True
            continue
        remote = loaded.get("frame")
        if loaded.get("status") != "available" or loaded.get("version") != version:
            continue
        if not isinstance(remote, (bytes, bytearray)) or _replica_digest(bytes(remote)) != digest:
            continue
        frame = bytes(remote)
        try:
            opened = _open_workspace_frame(frame, **options)
        except PrivateStorageError:
            continue
        lock = _process_lock(ledger)
        lock.acquire()
        descriptor = None
        try:
            descriptor = _acquire_lock(ledger)
            _assert_workspace_owner(ledger, identity)
            current_catalog = _read_json_file(ledger / _WORKSPACE_CATALOG)
            if current_catalog != catalog:
                raise PrivateStorageError("replica revision changed during restore", code="revision_conflict")
            _write_workspace_bytes(ledger, _WORKSPACE_FRAME, frame)
        finally:
            if descriptor is not None:
                _release_lock(descriptor)
            lock.release()
        opened["source"] = "replica"
        opened["status"] = "ready"
        opened["verified_replica_count"] = 1
        return opened
    if timed_out:
        raise PrivateStorageError("replica provider timed out", code="replica_timeout")
    raise PrivateStorageError("verified replica unavailable", code="replica_unavailable")


def upstream_replication_fixture_qualification(workspace: str | Path | None = None) -> dict[str, Any]:
    """Report upstream replication suites separately. A missing suite is not a pass."""

    root = Path(workspace) if workspace is not None else Path(__file__).resolve().parents[1]
    roots = (
        root / "external" / "ipfs_datasets_py",
        root / "external" / "ipfs_kit_py",
    )
    suites = []
    for relative in _UPSTREAM_REPLICATION_SUITES:
        found = any((root / relative).is_file() for root in roots)
        suites.append({
            "suite": relative,
            "status": "present" if found else "missing",
            "passed": False,
            "counts_as_passed": False,
            "returncode": None,
        })
    executed = False
    return {
        "executed": executed,
        "passed": False,
        "substitutes_first_party": False,
        "intended_environment": "ipfs_datasets_py",
        "suites": suites,
    }


def publish_encrypted_replicas(
    repository: str | Path,
    *,
    policy: ReplicaPolicy,
    providers: Sequence[Any] | Mapping[str, Any] = (),
    clock: Callable[[], float] | None = None,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    expected_head: str | None = None,
    expected_hash: str | None = None,
    artifacts: Mapping[str, Any] | None = None,
    private_names: Mapping[str, Any] | None = None,
    fsync_file: Callable[[int], None] | None = None,
    fsync_directory: Callable[[int], None] | None = None,
    complaint: bytes | None = None,
    fact_graph: bytes | None = None,
    proof: bytes | None = None,
    revision: str = "r1",
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Publish the sealed case locally, then optionally copy ciphertext to explicit providers.

    Remote providers are ignored in local private mode. This function never sleeps.
    A complaint/fact-graph/proof publication uses the workspace replica ledger.
    """

    if complaint is not None or fact_graph is not None or proof is not None:
        return _publish_workspace_replica(
            repository,
            policy=policy,
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            key=key,
            key_id=key_id,
            revision=revision,
            complaint=complaint if complaint is not None else b"",
            fact_graph=fact_graph if fact_graph is not None else b"",
            proof=proof if proof is not None else b"",
            providers=providers if isinstance(providers, Mapping) else None,
            timeout_seconds=timeout_seconds,
        )
    if artifacts is None or expected_head is None or expected_hash is None:
        raise ValueError("replica_publication_incomplete")
    if not isinstance(policy, ReplicaPolicy):
        raise ValueError("replica_policy_required")
    publication = publish_case_manifest(
        repository,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
        key=key,
        key_id=key_id,
        expected_head=expected_head,
        expected_hash=expected_hash,
        artifacts=artifacts,
        private_names=private_names,
        backend="local",
        fsync_file=fsync_file,
        fsync_directory=fsync_directory,
    )
    root = _case_root(repository)
    version = str(publication.generation or "")
    catalog = _ciphertext_catalog(root, version)
    observations = _local_replica_observations(root, catalog)
    unavailable: list[dict[str, Any]] = []
    activations_before = _REMOTE_STORAGE_ACTIVATIONS
    if policy.mode == "private_remote":
        for index, provider in enumerate(providers):
            provider_id = _provider_id(provider, index)
            rows, failure = _observe_remote_provider(provider, provider_id, root, catalog)
            observations.extend(rows)
            if failure is not None:
                unavailable.append(failure)
    receipt = _replica_receipt(
        policy,
        catalog,
        observations,
        unavailable,
        now=_replica_clock(clock),
        generation=publication.generation,
        manifest_hash=publication.manifest_hash,
        network_sharing_started=_REMOTE_STORAGE_ACTIVATIONS > activations_before,
    )
    receipt["publication_state"] = publication.state
    receipt["minted_completion"] = publication.minted_completion
    return receipt


def reconcile_encrypted_replicas(
    repository: str | Path,
    receipt: Mapping[str, Any] | None = None,
    *,
    policy: ReplicaPolicy | None = None,
    providers: Sequence[Any] | Mapping[str, Any] = (),
    clock: Callable[[], float] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Retry providers whose next retry is due. A future retry returns immediately.

    A workspace reconcile with no manifest receipt rechecks the local primary
    and any supplied providers against the stored ciphertext digest.
    """

    if receipt is None or isinstance(providers, Mapping):
        del clock
        return _reconcile_workspace_replicas(
            repository,
            providers=providers if isinstance(providers, Mapping) else None,
            timeout_seconds=timeout_seconds,
        )
    if not isinstance(policy, ReplicaPolicy):
        raise ValueError("replica_policy_required")
    now = _replica_clock(clock)
    root = _case_root(repository)
    catalog = [dict(entry) for entry in receipt.get("catalog") or []]
    if policy.mode != "private_remote":
        refreshed = dict(receipt)
        refreshed["synchronous_wait_seconds"] = 0
        refreshed["waited"] = False
        refreshed["network_sharing_started"] = False
        return refreshed
    due = {
        str(item.get("provider_id")): item
        for item in receipt.get("unavailable_providers") or []
        if isinstance(item, Mapping)
        and item.get("next_retry_at") is not None
        and float(item["next_retry_at"]) <= now
        and not item.get("exhausted")
    }
    activations_before = _REMOTE_STORAGE_ACTIVATIONS
    observations: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, provider in enumerate(providers):
        provider_id = _provider_id(provider, index)
        seen.add(provider_id)
        previous = due.get(provider_id)
        if previous is None:
            continue
        rows, failure = _observe_remote_provider(provider, provider_id, root, catalog)
        if failure is not None:
            failure["attempts"] = int(previous.get("attempts") or 1) + 1
            unavailable.append(failure)
        else:
            observations.extend(rows)
    for item in receipt.get("unavailable_providers") or []:
        if not isinstance(item, Mapping):
            continue
        provider_id = str(item.get("provider_id"))
        if provider_id in due:
            continue
        unavailable.append({
            "provider_id": provider_id,
            "error_category": "unavailable",
            "attempts": int(item.get("attempts") or 1),
            "exhausted": bool(item.get("exhausted")),
            "next_retry_at": item.get("next_retry_at"),
            "preserve_schedule": True,
        })
    kept = [
        row for row in _observations_from_receipt(receipt)
        if str(row.get("provider_id")) not in due and str(row.get("provider_id")) != "local-primary"
    ]
    local_rows = _local_replica_observations(root, catalog) if all(
        root.joinpath(*str(entry["name"]).split("/")).is_file() for entry in catalog
    ) else []
    refreshed = _replica_receipt(
        policy,
        catalog,
        [*local_rows, *kept, *observations],
        unavailable,
        now=now,
        generation=receipt.get("generation") if isinstance(receipt.get("generation"), str) else None,
        manifest_hash=receipt.get("manifest_hash") if isinstance(receipt.get("manifest_hash"), str) else None,
        network_sharing_started=_REMOTE_STORAGE_ACTIVATIONS > activations_before,
    )
    refreshed["synchronous_wait_seconds"] = 0
    refreshed["waited"] = False
    return refreshed


def _observations_from_receipt(receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    catalog = list(receipt.get("catalog") or [])
    for provider_id in receipt.get("verified_providers") or []:
        if provider_id == "local-primary":
            continue
        for entry in catalog:
            rows.append({
                "provider_id": provider_id,
                "role": "remote",
                "name": entry["name"],
                "state": "verified",
                "counted": True,
                "digest_match": True,
                "version_match": True,
                "version": entry["version"],
            })
    for item in receipt.get("uncounted") or []:
        if not isinstance(item, Mapping) or item.get("provider_id") == "local-primary":
            continue
        rows.append({
            "provider_id": item.get("provider_id"),
            "role": "remote",
            "name": item.get("name"),
            "state": item.get("state"),
            "counted": False,
            "digest_match": False,
            "version_match": False,
            "version": "",
        })
    return rows


def restore_encrypted_replicas(
    repository: str | Path,
    receipt: Mapping[str, Any],
    *,
    providers: Sequence[Any],
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    fsync_file: Callable[[int], None] | None = None,
    fsync_directory: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Restore a missing local primary from a remote replica whose readback matches the catalog.

    The user key opens the restored ciphertext. A replica that fails digest or
    version checks is not used.
    """

    catalog = [dict(entry) for entry in receipt.get("catalog") or []]
    if not catalog:
        raise PrivateRevisionError("replica catalog missing", code="missing_object", state="recoverable")
    version = str(catalog[0].get("version") or "")
    selected: list[tuple[str, bytes]] | None = None
    for index, provider in enumerate(providers):
        restored: list[tuple[str, bytes]] = []
        try:
            for entry in catalog:
                relative = str(entry["name"])
                if _REPLICA_NAME.fullmatch(relative) is None or entry.get("version") != version:
                    raise PrivateRevisionError("replica rejected", code="readback_mismatch", state="recoverable")
                loaded = provider.get(relative)
                if not isinstance(loaded, (bytes, bytearray)) or _replica_digest(bytes(loaded)) != entry["digest"]:
                    raise PrivateRevisionError("replica readback mismatch", code="readback_mismatch", state="recoverable")
                restored.append((relative, bytes(loaded)))
        except Exception:
            continue
        selected = restored
        break
    if selected is None:
        raise PrivateRevisionError("verified replica unavailable", code="replica_unavailable", state="recoverable")
    root = _case_root(repository)
    root.mkdir(parents=True, exist_ok=True)
    (root / "o").mkdir(parents=True, exist_ok=True)
    for relative, payload in selected:
        parent_name, _, leaf = relative.rpartition("/")
        parent = root / parent_name if parent_name else root
        parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(parent, leaf, payload, fsync_file=fsync_file, fsync_directory=fsync_directory)
    opened = read_case_manifest(
        repository,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
        key=key,
        key_id=key_id,
    )
    if opened is None:
        raise PrivateRevisionError("restored case is unreadable", code="stale_head", state="recoverable")
    return opened


def count_verified_ciphertext_replicas(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Count providers whose every object survived digest and version readback."""

    grouped: dict[str, list[bool]] = {}
    rejected: list[dict[str, str]] = []
    for row in observations:
        provider_id = str(row.get("provider_id") or "")
        state = str(row.get("state") or "")
        counted = (
            state == "verified"
            and row.get("digest_match") is True
            and row.get("version_match") is True
            and state not in _UNCOUNTED_REPLICA_STATES
        )
        grouped.setdefault(provider_id, []).append(counted)
        if not counted:
            rejected.append({"provider_id": provider_id, "state": state})
    verified = [provider_id for provider_id, flags in grouped.items() if flags and all(flags)]
    return {"verified_replicas": len(verified), "verified_providers": verified, "uncounted": rejected}


def _json_bytes(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_mode600(path: Path, payload: bytes) -> None:
    """Persist bytes as owner-read/write without requiring a private parent mode."""

    _reject_secret_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = payload
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PrivateStorageError("private write failed", code="key_store_io")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def _assert_recovery_separated(export_dir: str | Path, recovery_path: str | Path) -> None:
    export = Path(export_dir).resolve()
    recovery = Path(recovery_path).resolve()
    if recovery == export or export in recovery.parents or recovery.parent == export:
        raise PrivateKeyMaterialError("recovery_inside_export")


def _reject_unwrapped_key(blob: bytes, secret: bytes) -> None:
    if not secret:
        return
    if secret in blob or _b64e(secret).encode("ascii") in blob:
        raise PrivateKeyMaterialError("unwrapped_key_in_export")


def assert_tree_excludes_unwrapped_keys(root: str | Path, secrets: Sequence[bytes]) -> None:
    """Refuse an export tree that contains raw key bytes or their base64 form."""

    directory = Path(root)
    if not directory.exists():
        return
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        blob = path.read_bytes()
        for secret in secrets:
            _reject_unwrapped_key(blob, secret)


def _load_portability_manifest(export_dir: Path) -> dict[str, Any]:
    raw = _read_exact(export_dir / "manifest.json")
    if raw is None:
        raise PrivatePortabilityError(
            "The ciphertext archive has no versioned manifest. Nothing was restored.",
            code="manifest_missing",
            actions=("export_retry",),
        )
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PrivatePortabilityError(
            "The versioned manifest is unreadable. Encrypted state was not reset.",
            code="corrupt_manifest",
            actions=("export_retry",),
        ) from exc
    if not isinstance(document, dict):
        raise PrivatePortabilityError(
            "The versioned manifest is unreadable. Encrypted state was not reset.",
            code="corrupt_manifest",
            actions=("export_retry",),
        )
    if document.get("schema") != PORTABILITY_SCHEMA or int(document.get("schema_version") or 0) != PORTABILITY_VERSION:
        raise PrivatePortabilityError(
            "The archive manifest version is not supported. Encrypted state was not reset.",
            code="unsupported_version",
            actions=("export_retry",),
        )
    if document.get("recovery_included") is not False or document.get("unwrapped_master_included") is not False:
        raise PrivateKeyMaterialError("unwrapped_key_in_export")
    if document.get("key_material_included") is not False:
        raise PrivateKeyMaterialError("unwrapped_key_in_export")
    return document


def _workspace_frames(ledger: Path) -> list[tuple[str, bytes]]:
    frames: list[tuple[str, bytes]] = []
    primary = _read_exact(ledger / _WORKSPACE_FRAME)
    if primary is not None:
        frames.append(("primary", primary))
    generations = ledger / "generations"
    if generations.is_dir():
        for path in sorted(generations.glob("*.frame")):
            payload = _read_exact(path)
            if payload is not None:
                frames.append((path.name, payload))
    return frames


def read_private_workspace_generation(
    repository: str | Path,
    session: UserOwnedKeySession,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
) -> dict[str, Any]:
    """Open the active generation, or a retained generation after a partial rotation."""

    _reject_deleted_private_case(repository, tenant_id, case_id, session)
    session._require_unlocked("Reading a private workspace requires an unlocked session.")
    ledger = _workspace_ledger(repository)
    identity = _workspace_identity(tenant_id, case_id, principal_id, "")
    _assert_workspace_owner(ledger, identity)
    opened_frames: list[dict[str, Any]] = []
    for name, frame in _workspace_frames(ledger):
        try:
            parsed = parse_private_envelope(frame)
        except PrivateArtifactIntegrityError:
            continue
        key = session.lookup_data_key(tenant_id, case_id, str(parsed["key_id"]))
        if key is None:
            continue
        try:
            opened = _open_workspace_frame(
                frame,
                tenant_id=tenant_id,
                case_id=case_id,
                principal_id=principal_id,
                key=key,
                key_id=str(parsed["key_id"]),
            )
        except PrivateStorageError:
            continue
        opened["data_key_id"] = str(parsed["key_id"])
        opened["source_name"] = name
        opened["frame_sha256"] = _replica_digest(frame)
        opened_frames.append(opened)
    if not opened_frames:
        raise PrivatePortabilityError(
            "No retained or active key opened a ciphertext generation. " + UNRECOVERED_KEY_EXPLANATION,
            code="recovery_key_missing",
            actions=("passphrase_unlock", "recovery_import"),
        )
    active = session._data_keys.get((tenant_id, case_id))
    active_id = active[0] if active is not None else ""
    for opened in opened_frames:
        if opened["source_name"] == "primary" and opened["data_key_id"] == active_id:
            opened["generation"] = "active"
            return opened
    for opened in opened_frames:
        if opened["data_key_id"] == active_id:
            opened["generation"] = "active"
            return opened
    opened_frames[0]["generation"] = "retained"
    return opened_frames[0]


def stage_private_workspace(
    repository: str | Path,
    session: UserOwnedKeySession,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    revision: str,
    complaint: bytes,
    fact_graph: bytes,
    proof: bytes,
) -> dict[str, Any]:
    """Seal one case, fact graph, and proof revision into the local ciphertext ledger."""

    _reject_tombstoned_case(repository, tenant_id, case_id)
    session.ensure_data_key(tenant_id, case_id)
    key_id, key = session._require_case_key(tenant_id, case_id)
    _publish_workspace_replica(
        repository,
        policy=select_private_storage_mode("local_private"),
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
        key=key,
        key_id=key_id,
        revision=revision,
        complaint=bytes(complaint),
        fact_graph=bytes(fact_graph),
        proof=bytes(proof),
        providers=None,
        timeout_seconds=None,
    )
    return read_private_workspace_generation(
        repository,
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
    )


def export_encrypted_workspace(
    repository: str | Path,
    export_dir: str | Path,
    recovery_path: str | Path,
    session: UserOwnedKeySession,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    recovery_passphrase: str,
) -> dict[str, Any]:
    """Write a ciphertext archive and a separate recovery file. No raw master key."""

    session._require_unlocked("Export requires an unlocked session. Nothing was written.")
    assert_store_isolated_from_exports(session.directory, export_dir)
    _assert_recovery_separated(export_dir, recovery_path)
    opened = read_private_workspace_generation(
        repository,
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
    )
    if opened.get("generation") == "retained":
        raise PrivatePortabilityError(
            "The active generation is not the readable generation. Export was not written.",
            code="rotation_incomplete",
            actions=("resume_rotation", "retain"),
        )
    frame = _read_exact(_workspace_ledger(repository) / _WORKSPACE_FRAME)
    if frame is None or _replica_digest(frame) != opened["frame_sha256"]:
        raise PrivatePortabilityError(
            "The active ciphertext does not match the opened generation. Nothing was written.",
            code="readback_mismatch",
            actions=("restore_generation",),
        )
    key_id = str(opened["data_key_id"])
    manifest = {
        "schema": PORTABILITY_SCHEMA,
        "schema_version": PORTABILITY_VERSION,
        "manifest_version": PORTABILITY_VERSION,
        "tenant_id": tenant_id,
        "case_id": case_id,
        "principal_id": principal_id,
        "revision": opened["revision"],
        "data_key_id": key_id,
        "ciphertext": "ciphertext.frame",
        "ciphertext_sha256": _replica_digest(frame),
        "roles": ["complaint", "fact_graph", "proof"],
        "recovery_included": False,
        "unwrapped_master_included": False,
        "key_material_included": False,
    }
    destination = Path(export_dir)
    destination.mkdir(parents=True, exist_ok=True)
    os.chmod(destination, 0o700)
    _write_mode600(destination / "manifest.json", _json_bytes(manifest))
    _write_mode600(destination / "ciphertext.frame", frame)
    session.export_recovery(tenant_id, case_id, recovery_passphrase, recovery_path)
    secrets = [session._master or b""]
    active = session._data_keys.get((tenant_id, case_id))
    if active is not None:
        secrets.append(active[1])
    assert_tree_excludes_unwrapped_keys(destination, secrets)
    recovery_blob = Path(recovery_path).read_bytes()
    for secret in secrets:
        _reject_unwrapped_key(recovery_blob, secret)
    _PORTABILITY_LOG.info("exported versioned ciphertext manifest without key material")
    return {
        "status": "exported",
        "code": "exported",
        "operation": "export",
        "manifest_version": PORTABILITY_VERSION,
        "revision": opened["revision"],
        "recovery_separated": True,
        "unwrapped_master_included": False,
        "deliberate_export": True,
        "automatic_backup": False,
        "keys_reconstructed": False,
        "data_reset": False,
        "only_recovery_path_erased": False,
        "raw_key_persisted": False,
        "protection": (session._document or {}).get("protection"),
        "unlocked": True,
        "message": "Wrote a ciphertext archive and a separate recovery file.",
        "actions": ["import_archive", "lock"],
        "awaiting_user": False,
        "worker_may_continue": True,
        "worker_state": "ready_for_independent_tasks",
        "cloud_processing_enabled": False,
        "unlock_is_remote_consent": False,
    }


def import_encrypted_workspace(
    repository: str | Path,
    export_dir: str | Path,
    recovery_path: str | Path,
    store_dir: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    recovery_passphrase: str,
    store_passphrase: str | None = None,
) -> dict[str, Any]:
    """Restore an archive into a workspace. Failures do not reset existing ciphertext."""

    _require_label(tenant_id)
    _require_label(case_id)
    _require_label(principal_id)
    _reject_tombstoned_case(repository, tenant_id, case_id)
    recovery_file = Path(recovery_path)
    if not recovery_file.is_file():
        raise PrivatePortabilityError(
            "Recovery material is missing, so the encryption key is unrecovered. " + UNRECOVERED_KEY_EXPLANATION,
            code="recovery_key_missing",
            actions=("recovery_import", "retry_with_recovery_file"),
        )
    manifest = _load_portability_manifest(Path(export_dir))
    if manifest.get("tenant_id") != tenant_id or manifest.get("case_id") != case_id or manifest.get("principal_id") != principal_id:
        raise PrivateArtifactBindingError("foreign_case")
    frame_name = str(manifest.get("ciphertext") or "")
    if frame_name != "ciphertext.frame":
        raise PrivatePortabilityError(
            "The archive ciphertext name is not the versioned frame. Nothing was restored.",
            code="corrupt_manifest",
            actions=("export_retry",),
        )
    frame = _read_exact(Path(export_dir) / frame_name)
    if frame is None or _replica_digest(frame) != manifest.get("ciphertext_sha256"):
        raise PrivatePortabilityError(
            "The ciphertext archive does not match its manifest. Encrypted state was not reset.",
            code="readback_mismatch",
            actions=("export_retry",),
        )
    session = UserOwnedKeySession(store_dir)
    try:
        session.import_recovery(
            recovery_file.read_bytes(),
            tenant_id=tenant_id,
            case_id=case_id,
            recovery_passphrase=recovery_passphrase,
            store_passphrase=store_passphrase if store_passphrase is not None else recovery_passphrase,
        )
    except PrivateArtifactIntegrityError as exc:
        raise PrivatePortabilityError(
            "The recovery passphrase did not authenticate. " + UNRECOVERED_KEY_EXPLANATION,
            code="authentication_failed",
            actions=("retry_passphrase", "recovery_import"),
        ) from exc
    except PrivateKeyLockedError:
        raise
    key_id = str(manifest.get("data_key_id") or "")
    key = session.lookup_data_key(tenant_id, case_id, key_id)
    if key is None:
        raise PrivatePortabilityError(
            "The recovery file did not provide the archive data key. " + UNRECOVERED_KEY_EXPLANATION,
            code="recovery_key_missing",
            actions=("recovery_import",),
        )
    try:
        opened = _open_workspace_frame(
            frame,
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            key=key,
            key_id=key_id,
        )
    except PrivateStorageError as exc:
        raise PrivatePortabilityError(
            "The archive did not open with the recovered key. " + UNRECOVERED_KEY_EXPLANATION,
            code="authentication_failed",
            actions=("recovery_import",),
        ) from exc
    if opened["revision"] != manifest.get("revision"):
        raise PrivatePortabilityError(
            "The opened revision does not match the manifest. The destination workspace was not replaced.",
            code="revision_mismatch",
            actions=("export_retry",),
        )
    ledger = _workspace_ledger(repository)
    identity = _workspace_identity(tenant_id, case_id, principal_id, key_id)
    _assert_workspace_owner(ledger, identity)
    if _read_json_file(ledger / _WORKSPACE_OWNER) is None:
        _write_workspace_bytes(ledger, _WORKSPACE_OWNER, _json_bytes(identity))
    catalog = {
        "digest": _replica_digest(frame),
        "version": opened["revision"],
        "revision": opened["revision"],
        "desired": 1,
        "minimum": 1,
        "mode": "local_private",
        "providers": [],
    }
    _write_workspace_bytes(ledger, _WORKSPACE_FRAME, frame)
    _write_workspace_bytes(ledger, _WORKSPACE_CATALOG, _json_bytes(catalog))
    restored = read_private_workspace_generation(
        repository,
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
    )
    _PORTABILITY_LOG.info("imported ciphertext archive with a separate recovery file")
    restored.update({
        "status": "imported",
        "code": "imported",
        "operation": "import",
        "manifest_version": int(manifest.get("manifest_version") or 0),
        "imported": True,
        "keys_reconstructed": False,
        "data_reset": False,
        "unwrapped_master_included": False,
        "recovery_separated": True,
        "message": "Restored the case, fact graph, and proof revision from the ciphertext archive.",
    })
    return restored


DELETION_SCHEMA = "private-case-deletion"
DELETION_VERSION = 1
DELETION_POLICIES = ("retain_keys", "destroy_case_keys")
DELETION_PHASES = (
    "references_removed",
    "local_deleted",
    "unpinned",
    "remote_requested",
    "keys_destroyed",
    "tombstoned",
)
_PUBLIC_IPFS_LIMITATION = (
    "Unpin and remote deletion requests cover only managed replicas this workspace tracks. "
    "They do not erase copies on public IPFS or unmanaged external peers."
)


def _case_scope_token(tenant_id: str, case_id: str) -> str:
    _require_label(tenant_id)
    _require_label(case_id)
    return hashlib.sha256(f"{tenant_id}\n{case_id}".encode("utf-8")).hexdigest()


def _deletion_root(repository: str | Path) -> Path:
    return Path(repository)


def _scope_dir(repository: str | Path, tenant_id: str, case_id: str) -> Path:
    return _deletion_root(repository) / "deletion-scopes" / _case_scope_token(tenant_id, case_id)


def _tombstone_path(repository: str | Path, tenant_id: str, case_id: str) -> Path:
    return _deletion_root(repository) / "tombstones" / f"{_case_scope_token(tenant_id, case_id)}.json"


def _deletion_journal_path(repository: str | Path, tenant_id: str, case_id: str) -> Path:
    return _deletion_root(repository) / "deletion-journals" / f"{_case_scope_token(tenant_id, case_id)}.json"


def _shared_legal_index_path(repository: str | Path) -> Path:
    return _deletion_root(repository) / "shared-legal-index.json"


def _managed_pin_index_path(repository: str | Path) -> Path:
    return _deletion_root(repository) / "managed-pins.json"


def _read_json_object(path: Path) -> dict[str, Any]:
    document = _read_json_file(path)
    return document or {}


def _write_json_object(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    _write_mode600(path, _json_bytes(document))


def _remove_tree(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    for child in sorted(path.iterdir(), reverse=True):
        _remove_tree(child)
    path.rmdir()


def read_case_tombstone(repository: str | Path, tenant_id: str, case_id: str) -> dict[str, Any] | None:
    """Return the case tombstone, if deletion already committed one."""

    document = _read_json_file(_tombstone_path(repository, tenant_id, case_id))
    if document is None:
        return None
    if document.get("schema") != DELETION_SCHEMA or document.get("status") != "tombstoned":
        raise PrivateStorageError("deletion tombstone is unreadable", code="corrupt_manifest")
    return document


def _reject_tombstoned_case(repository: str | Path, tenant_id: str, case_id: str) -> None:
    tombstone = read_case_tombstone(repository, tenant_id, case_id)
    if tombstone is None:
        return
    code = "case_key_destroyed" if tombstone.get("case_keys_destroyed") else "tombstoned"
    raise PrivatePortabilityError(
        "A deletion tombstone blocks stale recovery from resurrecting this case's private state.",
        code=code,
        actions=("inspect_deletion_receipt",),
    )


def _reject_deleted_private_case(
    repository: str | Path,
    tenant_id: str,
    case_id: str,
    session: UserOwnedKeySession | None,
) -> None:
    if session is not None and session._case_was_destroyed(tenant_id, case_id):
        raise PrivatePortabilityError(
            "The deleted case key is inaccessible. Stale recovery cannot open this private state.",
            code="case_key_destroyed",
            actions=("inspect_deletion_receipt",),
        )
    _reject_tombstoned_case(repository, tenant_id, case_id)


def normal_reset_retention_receipt() -> dict[str, Any]:
    """Normal reset keeps the encryption key and the recovery path."""

    return {
        "operation": "normal_reset",
        "retention_policy": "normal_reset_retains_keys",
        "policy_explicit": True,
        "encryption_key_destroyed": False,
        "recovery_path_destroyed": False,
        "key_destruction": "not_performed",
        "irreversible_recovery_path_destroyed": False,
        "data_reset": False,
        "universal_erasure": False,
        "public_ipfs_erased": False,
        "message": "Normal reset does not destroy the encryption key or the recovery path.",
    }


def bind_shared_legal_artifact(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    name: str,
    payload: bytes,
) -> dict[str, Any]:
    """Record one shared legal-source blob and this case's reference to it."""

    _require_label(name)
    if not isinstance(payload, (bytes, bytearray)):
        raise PrivateStorageError("legal source payload rejected", code="bad_ref")
    body = bytes(payload)
    digest = hashlib.sha256(body).hexdigest()
    token = _case_scope_token(tenant_id, case_id)
    root = _deletion_root(repository)
    shared = root / "shared-legal" / digest
    if not shared.exists():
        shared.parent.mkdir(parents=True, exist_ok=True)
        _write_mode600(shared, body)
    index = _read_json_object(_shared_legal_index_path(repository))
    entry = dict(index.get(digest) or {})
    cases = sorted(set(list(entry.get("cases") or []) + [token]))
    index[digest] = {"cases": cases, "name": name}
    _write_json_object(_shared_legal_index_path(repository), index)
    scope = _scope_dir(repository, tenant_id, case_id)
    references = _read_json_object(scope / "references.json")
    artifacts = [dict(item) for item in references.get("legal_sources") or [] if isinstance(item, Mapping)]
    if not any(item.get("digest") == digest for item in artifacts):
        artifacts.append({"name": name, "digest": digest, "shared": True})
    references["legal_sources"] = artifacts
    references["tenant_id"] = tenant_id
    references["case_id"] = case_id
    _write_json_object(scope / "references.json", references)
    return {"digest": digest, "shared": True, "referencing_cases": len(cases)}


def write_case_local_private_file(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    kind: str,
    name: str,
    payload: bytes,
) -> Path:
    """Write ciphertext, cache, or temp bytes that belong only to one case."""

    if kind not in {"ciphertext", "cache", "temp"}:
        raise PrivateStorageError("private file kind rejected", code="bad_ref")
    _require_label(name)
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise PrivateStorageError("private file name rejected", code="bad_ref")
    if not isinstance(payload, (bytes, bytearray)):
        raise PrivateStorageError("private file payload rejected", code="bad_ref")
    path = _scope_dir(repository, tenant_id, case_id) / kind / name
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_mode600(path, bytes(payload))
    return path


def record_managed_replica(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    cid: str,
    provider_id: str,
) -> dict[str, Any]:
    """Track a managed replica pin. Shared CIDs stay pinned while another case uses them."""

    _require_label(cid)
    _require_label(provider_id)
    token = _case_scope_token(tenant_id, case_id)
    index = _read_json_object(_managed_pin_index_path(repository))
    entry = dict(index.get(cid) or {})
    cases = sorted(set(list(entry.get("cases") or []) + [token]))
    entry["cases"] = cases
    entry["provider_id"] = provider_id
    index[cid] = entry
    _write_json_object(_managed_pin_index_path(repository), index)
    scope = _scope_dir(repository, tenant_id, case_id)
    references = _read_json_object(scope / "references.json")
    pins = [dict(item) for item in references.get("managed_replicas") or [] if isinstance(item, Mapping)]
    if not any(item.get("cid") == cid for item in pins):
        pins.append({"cid": cid, "provider_id": provider_id})
    references["managed_replicas"] = pins
    references["tenant_id"] = tenant_id
    references["case_id"] = case_id
    _write_json_object(scope / "references.json", references)
    return {"cid": cid, "provider_id": provider_id, "referencing_cases": len(cases)}


def _load_deletion_journal(repository: str | Path, tenant_id: str, case_id: str) -> dict[str, Any]:
    path = _deletion_journal_path(repository, tenant_id, case_id)
    document = _read_json_file(path)
    if document is None:
        return {
            "schema": DELETION_SCHEMA,
            "schema_version": DELETION_VERSION,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "completed": [],
            "phases": {},
            "plan": {},
        }
    if document.get("schema") != DELETION_SCHEMA:
        raise PrivateStorageError("deletion journal is unreadable", code="corrupt_manifest")
    document.setdefault("completed", [])
    document.setdefault("phases", {})
    document.setdefault("plan", {})
    return document


def _save_deletion_journal(repository: str | Path, journal: Mapping[str, Any]) -> None:
    tenant_id = str(journal.get("tenant_id") or "")
    case_id = str(journal.get("case_id") or "")
    _write_json_object(_deletion_journal_path(repository, tenant_id, case_id), journal)


def _capture_deletion_plan(repository: str | Path, tenant_id: str, case_id: str) -> dict[str, Any]:
    token = _case_scope_token(tenant_id, case_id)
    references = _read_json_object(_scope_dir(repository, tenant_id, case_id) / "references.json")
    legal = [dict(item) for item in references.get("legal_sources") or [] if isinstance(item, Mapping)]
    pins = [dict(item) for item in references.get("managed_replicas") or [] if isinstance(item, Mapping)]
    index = _read_json_object(_shared_legal_index_path(repository))
    pin_index = _read_json_object(_managed_pin_index_path(repository))
    exclusive_digests = []
    preserved_digests = []
    for item in legal:
        digest = str(item.get("digest") or "")
        holders = list((index.get(digest) or {}).get("cases") or [])
        if holders in ([], [token]) or holders == [token]:
            exclusive_digests.append(digest)
        else:
            preserved_digests.append(digest)
    exclusive_cids = []
    shared_cids = []
    for item in pins:
        cid = str(item.get("cid") or "")
        holders = list((pin_index.get(cid) or {}).get("cases") or [])
        if not holders or holders == [token]:
            exclusive_cids.append(cid)
        else:
            shared_cids.append(cid)
    ledger = _workspace_ledger(repository)
    owner = _read_json_file(ledger / _WORKSPACE_OWNER) or {}
    ledger_owned = owner.get("tenant_id") == tenant_id and owner.get("case_id") == case_id
    return {
        "token": token,
        "legal_sources": legal,
        "managed_replicas": pins,
        "exclusive_digests": exclusive_digests,
        "preserved_digests": preserved_digests,
        "exclusive_cids": exclusive_cids,
        "shared_cids": shared_cids,
        "ledger_owned": ledger_owned,
    }


def _remove_case_references(repository: str | Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    token = str(plan["token"])
    index = _read_json_object(_shared_legal_index_path(repository))
    for digest in list(index):
        entry = dict(index[digest])
        cases = [item for item in entry.get("cases") or [] if item != token]
        entry["cases"] = cases
        index[digest] = entry
    _write_json_object(_shared_legal_index_path(repository), index)
    pins = _read_json_object(_managed_pin_index_path(repository))
    for cid in list(pins):
        entry = dict(pins[cid])
        entry["cases"] = [item for item in entry.get("cases") or [] if item != token]
        pins[cid] = entry
    _write_json_object(_managed_pin_index_path(repository), pins)
    scope = _deletion_root(repository) / "deletion-scopes" / token
    references = scope / "references.json"
    if references.exists():
        _write_json_object(references, {"removed": True, "tenant_token": token})
    return {
        "step": "remove_case_references",
        "status": "completed",
        "references_removed": True,
        "preserved_shared_digests": list(plan.get("preserved_digests") or []),
        "exclusive_digests": list(plan.get("exclusive_digests") or []),
    }


def _delete_local_private_bytes(repository: str | Path, tenant_id: str, case_id: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    scope = _scope_dir(repository, tenant_id, case_id)
    removed_kinds = []
    for kind in ("ciphertext", "cache", "temp"):
        target = scope / kind
        if target.exists():
            _remove_tree(target)
            removed_kinds.append(kind)
    deleted_shared = []
    preserved = []
    index = _read_json_object(_shared_legal_index_path(repository))
    for digest in list(plan.get("exclusive_digests") or []):
        holders = list((index.get(digest) or {}).get("cases") or [])
        if holders:
            preserved.append(digest)
            continue
        path = _deletion_root(repository) / "shared-legal" / str(digest)
        if path.exists():
            path.unlink()
        index.pop(str(digest), None)
        deleted_shared.append(digest)
    for digest in list(plan.get("preserved_digests") or []):
        path = _deletion_root(repository) / "shared-legal" / str(digest)
        if path.is_file():
            preserved.append(digest)
    _write_json_object(_shared_legal_index_path(repository), index)
    ledger_removed = False
    if plan.get("ledger_owned"):
        ledger = _workspace_ledger(repository)
        for name in (_WORKSPACE_FRAME, _WORKSPACE_CATALOG, _WORKSPACE_PENDING, _WORKSPACE_OWNER, "rotation-data.json"):
            path = ledger / name
            if path.is_file():
                path.unlink()
                ledger_removed = True
        generations = ledger / "generations"
        if generations.exists():
            _remove_tree(generations)
            ledger_removed = True
    return {
        "step": "delete_local_ciphertext_cache_temp",
        "status": "completed",
        "local_kinds_removed": removed_kinds,
        "shared_artifacts_deleted": deleted_shared,
        "shared_artifacts_preserved": preserved,
        "ledger_ciphertext_removed": ledger_removed,
    }


def _provider_method(provider: Any, *names: str) -> Callable[..., Any] | None:
    for name in names:
        method = getattr(provider, name, None)
        if callable(method):
            return method
    return None


def _provider_status(result: Any) -> str:
    if not isinstance(result, Mapping):
        return "unreachable"
    status = str(result.get("status") or result.get("state") or "unreachable")
    if status in {"unpinned", "deleted", "accepted", "requested", "pending", "unreachable", "unavailable"}:
        return "unreachable" if status in {"unavailable", "timeout"} else status
    if status in {"timeout", "error"}:
        return "unreachable"
    return "unreachable"


def _unpin_managed_replicas(
    repository: str | Path,
    plan: Mapping[str, Any],
    providers: Mapping[str, Any] | None,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    pins = _read_json_object(_managed_pin_index_path(repository))
    unpinned = []
    left_shared = []
    unreachable = []
    for cid in list(plan.get("exclusive_cids") or []):
        entry = dict(pins.get(cid) or {})
        if entry.get("cases"):
            left_shared.append({"cid": cid, "reason": "still_referenced"})
            continue
        provider_id = str(entry.get("provider_id") or "")
        provider = (providers or {}).get(provider_id)
        method = _provider_method(provider, "unpin") if provider is not None else None
        if method is None:
            unreachable.append({"cid": cid, "provider_id": provider_id, "status": "unreachable", "reason": "unpin_unavailable"})
            continue
        try:
            result = _bounded_provider_call(method, timeout_seconds, cid=cid)
        except Exception:
            result = {"status": "unreachable"}
        status = _provider_status(result)
        if status == "unpinned":
            pins.pop(cid, None)
            unpinned.append({"cid": cid, "provider_id": provider_id, "status": "unpinned"})
        else:
            unreachable.append({"cid": cid, "provider_id": provider_id, "status": "unreachable", "reason": status})
    for cid in list(plan.get("shared_cids") or []):
        left_shared.append({"cid": cid, "reason": "shared_with_another_case"})
    _write_json_object(_managed_pin_index_path(repository), pins)
    return {
        "step": "unpin_managed_replicas",
        "status": "completed" if not unreachable else "partial",
        "unpinned": unpinned,
        "left_in_place": left_shared,
        "unreachable": unreachable,
    }


def _request_remote_deletion(
    plan: Mapping[str, Any],
    providers: Mapping[str, Any] | None,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    requested = []
    pending = []
    unreachable = []
    external = []
    by_cid = {
        str(item.get("cid") or ""): str(item.get("provider_id") or "")
        for item in plan.get("managed_replicas") or []
        if isinstance(item, Mapping)
    }
    residual = []
    for cid in list(plan.get("shared_cids") or []):
        residual.append({
            "cid": cid,
            "provider_id": by_cid.get(cid, ""),
            "status": "not_requested",
            "erased": False,
            "reason": "shared_with_another_case",
        })
    replicas = [
        {"cid": cid, "provider_id": by_cid.get(cid, "")}
        for cid in list(plan.get("exclusive_cids") or [])
    ]
    for item in replicas:
        cid = str(item.get("cid") or "")
        provider_id = str(item.get("provider_id") or "")
        provider = (providers or {}).get(provider_id)
        method = _provider_method(provider, "request_deletion", "delete") if provider is not None else None
        if method is None:
            row = {
                "cid": cid,
                "provider_id": provider_id,
                "status": "external_replica",
                "erased": False,
                "reason": "no_managed_deletion_api",
            }
            external.append(row)
            continue
        try:
            result = _bounded_provider_call(method, timeout_seconds, cid=cid)
        except Exception:
            result = {"status": "unreachable"}
        status = _provider_status(result)
        row = {"cid": cid, "provider_id": provider_id, "erased": False, "status": status}
        if status == "pending":
            row["reason"] = "remote_removal_pending"
            pending.append(row)
        elif status in {"deleted", "accepted", "requested"}:
            row["status"] = "requested"
            row["reason"] = "managed_deletion_requested_not_universal"
            requested.append(row)
        else:
            row["status"] = "unreachable"
            row["reason"] = "remote_removal_unreachable"
            unreachable.append(row)
    residual.extend(external)
    residual.extend(pending)
    residual.extend(unreachable)
    residual.extend(requested)
    residual.append({
        "kind": "public_ipfs",
        "erased": False,
        "managed": False,
        "status": "not_erased",
        "reason": "public IPFS copies are outside this workspace and were not erased",
    })
    if pending:
        remote_status = "pending"
    elif unreachable or external:
        remote_status = "unreachable"
    elif requested:
        remote_status = "requested"
    else:
        remote_status = "not_applicable"
    return {
        "step": "request_remote_deletion",
        "status": remote_status,
        "requested": requested,
        "pending": pending,
        "unreachable": unreachable,
        "external_replicas": external,
        "residual_replicas": residual,
        "universal_erasure": False,
        "public_ipfs_erased": False,
        "external_replica_limitation": _PUBLIC_IPFS_LIMITATION,
    }


def _deletion_receipt(journal: Mapping[str, Any], *, idempotent: bool, resumed_from: str | None) -> dict[str, Any]:
    phases = dict(journal.get("phases") or {})
    remote = dict(phases.get("remote_requested") or {})
    keys = dict(phases.get("keys_destroyed") or {})
    local = dict(phases.get("local_deleted") or {})
    references = dict(phases.get("references_removed") or {})
    unpinned = dict(phases.get("unpinned") or {})
    destroyed = bool(keys.get("encryption_key_destroyed"))
    steps = [
        references or {"step": "remove_case_references", "status": "not_started"},
        local or {"step": "delete_local_ciphertext_cache_temp", "status": "not_started"},
        unpinned or {"step": "unpin_managed_replicas", "status": "not_started"},
        remote or {"step": "request_remote_deletion", "status": "not_started"},
        keys or {"step": "destroy_case_keys", "status": "not_started"},
    ]
    completed = list(journal.get("completed") or [])
    status = "completed" if "tombstoned" in completed else "partial"
    return {
        "operation": "delete_private_case",
        "status": status,
        "code": status,
        "tenant_id": journal.get("tenant_id"),
        "case_id": journal.get("case_id"),
        "retention_policy": journal.get("retention_policy"),
        "policy_explicit": True,
        "legal_hold": False,
        "workspace_required": False,
        "steps": steps,
        "remove_case_references": references,
        "delete_local_ciphertext_cache_temp": local,
        "unpin_managed_replicas": unpinned,
        "request_remote_deletion": remote,
        "destroy_case_keys": keys,
        "shared_artifacts_preserved": list(local.get("shared_artifacts_preserved") or references.get("preserved_shared_digests") or []),
        "encryption_key_destroyed": destroyed,
        "recovery_path_destroyed": destroyed,
        "irreversible_recovery_path_destroyed": destroyed,
        "master_key_destroyed": False,
        "universal_erasure": False,
        "public_ipfs_erased": False,
        "external_replica_limitation": remote.get("external_replica_limitation") or _PUBLIC_IPFS_LIMITATION,
        "residual_replicas": list(remote.get("residual_replicas") or []),
        "pending_remote_removals": list(remote.get("pending") or []),
        "unreachable_remote_removals": list(remote.get("unreachable") or []),
        "tombstone": journal.get("tombstone"),
        "idempotent": idempotent,
        "resumed_from": resumed_from,
        "data_reset": False,
        "message": "Scoped deletion finished. Public IPFS and unmanaged replicas are not universally erased.",
    }


def _refused_deletion_receipt(
    *,
    tenant_id: str,
    case_id: str,
    policy: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    empty = {"status": "not_started"}
    return {
        "operation": "delete_private_case",
        "status": "refused",
        "code": code,
        "tenant_id": tenant_id,
        "case_id": case_id,
        "retention_policy": policy,
        "policy_explicit": True,
        "legal_hold": code == "legal_hold",
        "workspace_required": code == "workspace_required",
        "steps": [
            {"step": "remove_case_references", **empty},
            {"step": "delete_local_ciphertext_cache_temp", **empty},
            {"step": "unpin_managed_replicas", **empty},
            {"step": "request_remote_deletion", **empty},
            {"step": "destroy_case_keys", **empty},
        ],
        "encryption_key_destroyed": False,
        "recovery_path_destroyed": False,
        "irreversible_recovery_path_destroyed": False,
        "universal_erasure": False,
        "public_ipfs_erased": False,
        "external_replica_limitation": _PUBLIC_IPFS_LIMITATION,
        "residual_replicas": [],
        "idempotent": False,
        "data_reset": False,
        "message": message,
    }


def delete_private_case(
    repository: str | Path,
    session: UserOwnedKeySession | None,
    *,
    tenant_id: str,
    case_id: str,
    policy: str,
    legal_hold: bool = False,
    workspace_required: bool = False,
    providers: Mapping[str, Any] | None = None,
    timeout_seconds: float | None = None,
    crash_at: str | None = None,
) -> dict[str, Any]:
    """Delete one case's private state without touching another case's shared sources.

    ``crash_at`` persists that phase and then raises so a later call can resume.
    A second call after the tombstone is committed is idempotent.
    """

    _require_label(tenant_id)
    _require_label(case_id)
    if policy not in DELETION_POLICIES:
        raise PrivatePortabilityError(
            "Deletion needs an explicit retention policy. Nothing was erased.",
            code="retention_policy",
            actions=DELETION_POLICIES,
        )
    if crash_at not in {None, *DELETION_PHASES}:
        raise PrivateKeyMaterialError("deletion_phase")
    if legal_hold:
        return _refused_deletion_receipt(
            tenant_id=tenant_id,
            case_id=case_id,
            policy=policy,
            code="legal_hold",
            message="Legal hold is an explicit retention need. The case was not deleted.",
        )
    if workspace_required:
        return _refused_deletion_receipt(
            tenant_id=tenant_id,
            case_id=case_id,
            policy=policy,
            code="workspace_required",
            message="The workspace still requires this case. The case was not deleted.",
        )
    existing = read_case_tombstone(repository, tenant_id, case_id)
    journal = _load_deletion_journal(repository, tenant_id, case_id)
    if existing is not None and "tombstoned" in (journal.get("completed") or []):
        journal["tombstone"] = existing
        receipt = _deletion_receipt(journal, idempotent=True, resumed_from=None)
        receipt["tombstone"] = existing
        return receipt
    journal["retention_policy"] = policy
    if not journal.get("plan"):
        journal["plan"] = _capture_deletion_plan(repository, tenant_id, case_id)
        _save_deletion_journal(repository, journal)
    plan = journal["plan"]
    completed = list(journal.get("completed") or [])
    resumed_from = completed[-1] if completed else None
    phases = dict(journal.get("phases") or {})

    def _finish(phase: str, result: Mapping[str, Any]) -> None:
        phases[phase] = dict(result)
        if phase not in completed:
            completed.append(phase)
        journal["completed"] = completed
        journal["phases"] = phases
        _save_deletion_journal(repository, journal)
        if crash_at == phase:
            raise PrivateRevisionInterrupted(phase, _case_scope_token(tenant_id, case_id))

    if "references_removed" not in completed:
        _finish("references_removed", _remove_case_references(repository, plan))
    if "local_deleted" not in completed:
        _finish("local_deleted", _delete_local_private_bytes(repository, tenant_id, case_id, plan))
    if "unpinned" not in completed:
        _finish("unpinned", _unpin_managed_replicas(repository, plan, providers, timeout_seconds))
    if "remote_requested" not in completed:
        _finish("remote_requested", _request_remote_deletion(plan, providers, timeout_seconds))
    if "keys_destroyed" not in completed:
        if policy == "retain_keys":
            key_result = {
                "step": "destroy_case_keys",
                "status": "retained_by_policy",
                "encryption_key_destroyed": False,
                "recovery_path_destroyed": False,
                "master_key_destroyed": False,
            }
        else:
            if session is None:
                raise PrivateKeyMaterialError("key_unavailable")
            destroyed = session.destroy_case_keys(tenant_id, case_id)
            key_result = {
                "step": "destroy_case_keys",
                "status": "destroyed",
                "encryption_key_destroyed": True,
                "recovery_path_destroyed": True,
                "master_key_destroyed": False,
                "other_cases_retained": True,
                "data_key_ids": list(destroyed.get("data_key_ids") or []),
            }
        _finish("keys_destroyed", key_result)
    if "tombstoned" not in completed:
        remote = dict(phases.get("remote_requested") or {})
        keys = dict(phases.get("keys_destroyed") or {})
        tombstone = {
            "schema": DELETION_SCHEMA,
            "schema_version": DELETION_VERSION,
            "status": "tombstoned",
            "tenant_id": tenant_id,
            "case_id": case_id,
            "case_keys_destroyed": bool(keys.get("encryption_key_destroyed")),
            "universal_erasure": False,
            "public_ipfs_erased": False,
            "external_replica_limitation": _PUBLIC_IPFS_LIMITATION,
            "residual_replicas": list(remote.get("residual_replicas") or []),
            "pending_remote_removals": list(remote.get("pending") or []),
            "unreachable_remote_removals": list(remote.get("unreachable") or []),
        }
        _write_json_object(_tombstone_path(repository, tenant_id, case_id), tombstone)
        journal["tombstone"] = tombstone
        _finish("tombstoned", {"step": "tombstone", "status": "tombstoned"})
    receipt = _deletion_receipt(journal, idempotent=False, resumed_from=resumed_from)
    if resumed_from is not None:
        receipt["idempotent"] = False
        receipt["resumed"] = True
    else:
        receipt["resumed"] = False
    receipt["tombstone"] = read_case_tombstone(repository, tenant_id, case_id)
    return receipt


LEGACY_HOOK_ARTIFACT_CLASS = "legacy-private-hook"
LEGACY_HOOK_RETENTION = ("retain", "retire_plaintext_after_verified_commit")
_LEGACY_HOOK_HEAD = "legacy-hook-head.json"
_LEGACY_HOOK_SCHEMA = "legacy-hook-encrypted-head"
_LEGACY_HOOK_RECEIPT = "legacy-hook-migration-receipt"
_LEGACY_HOOK_MAX_BYTES = 1024 * 1024


def _legacy_hook_ref(revision: str, preimage: str) -> str:
    return f"{LEGACY_HOOK_ARTIFACT_CLASS}:{revision}:{preimage}"


def _legacy_hook_binding(
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    revision: str,
) -> dict[str, str]:
    return {
        "tenant_id": tenant_id,
        "case_id": case_id,
        "principal_id": principal_id,
        "artifact_kind": LEGACY_HOOK_ARTIFACT_CLASS,
        "artifact_class": LEGACY_HOOK_ARTIFACT_CLASS,
        "revision": revision,
    }


def _legacy_hook_receipt(
    *,
    status: str,
    code: str,
    revision: str,
    preimage: str,
    binding: Mapping[str, str],
    retention_policy: str,
    encrypted: bool,
    pending_kind: str,
    verified_commit: bool,
    plaintext_retired: bool,
    plaintext_retirement: str,
    source_bytes_preserved: bool,
    last_valid_head_preserved: bool,
    prior_head_present: bool,
    encryption_established: bool,
) -> dict[str, Any]:
    ref = _legacy_hook_ref(revision, preimage)
    encrypted_items = [{"ref": ref, "case_id": binding["case_id"], "revision": revision, "source_preimage": preimage}] if encrypted else []
    pending_items: list[dict[str, str]] = []
    if pending_kind:
        pending_items.append({"ref": ref, "pending": pending_kind})
    return {
        "schema": _LEGACY_HOOK_RECEIPT,
        "schema_version": 1,
        "status": status,
        "code": code,
        "artifact_class": LEGACY_HOOK_ARTIFACT_CLASS,
        "single_case": True,
        "automatic_scan": False,
        "imported_sessions": False,
        "rewrote_user_tree": False,
        "rewrote_campaign_artifacts": False,
        "rewrote_historical_qualifiers": False,
        "encrypted": encrypted,
        "pending": bool(pending_items),
        "encrypted_items": encrypted_items,
        "pending_items": pending_items,
        "verified_commit": verified_commit,
        "encryption_established": encryption_established,
        "plaintext_retired": plaintext_retired,
        "plaintext_retirement": plaintext_retirement,
        "source_bytes_preserved": source_bytes_preserved,
        "last_valid_head_preserved": last_valid_head_preserved,
        "prior_head_present": prior_head_present,
        "retention_policy": retention_policy,
        "source_preimage": preimage,
        "destination_binding": dict(binding),
        "durable": False,
        "network_durable": False,
        "stored_local": encrypted,
        "mode_bits_establish_encryption": False,
        "local_copy_establishes_encryption": False,
        "local_copy_establishes_durability": False,
    }


def legacy_hook_migration_claim(
    *,
    mode_private: bool = False,
    local_copy: bool = False,
    receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Mode bits and a local copy do not establish encryption or durability."""

    established = bool(
        isinstance(receipt, Mapping)
        and receipt.get("encryption_established") is True
        and receipt.get("verified_commit") is True
    )
    return {
        "encrypted": established,
        "encryption_established": established,
        "durable": False,
        "network_durable": False,
        "mode_private": bool(mode_private),
        "local_copy": bool(local_copy),
        "mode_bits_establish_encryption": False,
        "local_copy_establishes_encryption": False,
        "local_copy_establishes_durability": False,
        "automatic_scan": False,
    }


def _legacy_preimage(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise PrivateArtifactIntegrityError("preimage")
    return value


def _inspect_legacy_hook_source(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        return {"ok": False, "code": "aliased_source"}
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return {"ok": False, "code": "source_missing"}
    except OSError:
        return {"ok": False, "code": "aliased_source"}
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            return {"ok": False, "code": "source_not_file"}
        if info.st_nlink != 1:
            return {"ok": False, "code": "aliased_source"}
        if info.st_size > _LEGACY_HOOK_MAX_BYTES:
            return {"ok": False, "code": "oversized"}
        chunks: list[bytes] = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
            if sum(len(item) for item in chunks) > _LEGACY_HOOK_MAX_BYTES:
                return {"ok": False, "code": "oversized"}
        payload = b"".join(chunks)
    finally:
        os.close(descriptor)
    if not payload:
        return {"ok": False, "code": "empty_source", "dev": info.st_dev, "ino": info.st_ino}
    return {"ok": True, "data": payload, "dev": info.st_dev, "ino": info.st_ino, "nlink": info.st_nlink}


def _read_nofollow_bytes(path: Path) -> bytes | None:
    if not path.exists():
        return None
    if path.is_symlink():
        raise PrivateArtifactIntegrityError("aliased_destination")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PrivateArtifactIntegrityError("aliased_destination")
        return os.read(descriptor, info.st_size + 1)
    finally:
        os.close(descriptor)


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = payload
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PrivateStorageError("private write failed", code="legacy_hook_io")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_legacy_head(destination: Path, payload: bytes) -> None:
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination / (".legacy-hook-head-" + uuid.uuid4().hex + ".tmp")
    _write_exclusive(temporary, payload)
    os.replace(temporary, destination / _LEGACY_HOOK_HEAD)
    try:
        directory = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _load_legacy_head(destination: Path) -> dict[str, Any]:
    head_path = destination / _LEGACY_HOOK_HEAD
    if not head_path.exists() and not head_path.is_symlink():
        return {"present": False}
    try:
        raw = _read_nofollow_bytes(head_path)
    except PrivateArtifactIntegrityError:
        return {"present": True, "aliased": True}
    except OSError:
        return {"present": True, "corrupt": True, "raw": b""}
    if raw is None:
        return {"present": False}
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"present": True, "corrupt": True, "raw": raw}
    if not isinstance(document, dict) or document.get("schema") != _LEGACY_HOOK_SCHEMA:
        return {"present": True, "corrupt": True, "raw": raw}
    digest = str(document.get("ciphertext_sha256") or "")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        return {"present": True, "corrupt": True, "raw": raw}
    object_path = destination / "objects" / f"{digest}.bin"
    try:
        envelope = _read_nofollow_bytes(object_path)
    except (PrivateArtifactIntegrityError, OSError):
        return {"present": True, "corrupt": True, "raw": raw, "document": document}
    if envelope is None or hashlib.sha256(envelope).hexdigest() != digest:
        return {"present": True, "corrupt": True, "raw": raw, "document": document}
    return {"present": True, "corrupt": False, "raw": raw, "document": document, "envelope": envelope}


def _legacy_hook_keys(
    binding: PrivateArtifactBinding,
    *,
    key: bytes | None,
    key_id: str | None,
    key_provider: InjectedCaseKeyProvider | None,
) -> tuple[str, bytes]:
    return _resolve_key(binding, key=key, key_id=key_id, key_provider=key_provider)


def _retire_legacy_source(path: Path, snapshot: Mapping[str, Any], payload: bytes) -> bool:
    inspected = _inspect_legacy_hook_source(path)
    if not inspected.get("ok"):
        return False
    if inspected["data"] != payload or inspected["dev"] != snapshot["dev"] or inspected["ino"] != snapshot["ino"]:
        return False
    if inspected["nlink"] != 1:
        return False
    path.unlink()
    return not path.exists()


def preflight_legacy_hook_migration(
    source_path: str | Path,
    *,
    source_preimage: str,
    destination: str | Path,
    access: Any,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    revision: str,
    retention_policy: str = "retain",
    key: bytes | None = None,
    key_id: str | None = None,
    key_provider: InjectedCaseKeyProvider | None = None,
) -> dict[str, Any]:
    """Inspect one caller-selected legacy hook artifact. Writes nothing."""

    return _legacy_hook_migration(
        source_path,
        source_preimage=source_preimage,
        destination=destination,
        access=access,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
        revision=revision,
        retention_policy=retention_policy,
        key=key,
        key_id=key_id,
        key_provider=key_provider,
        commit=False,
        interrupt_at=None,
    )


def commit_legacy_hook_migration(
    source_path: str | Path,
    *,
    source_preimage: str,
    destination: str | Path,
    access: Any,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    revision: str,
    retention_policy: str = "retain",
    key: bytes | None = None,
    key_id: str | None = None,
    key_provider: InjectedCaseKeyProvider | None = None,
    interrupt_at: str | None = None,
) -> dict[str, Any]:
    """Seal one explicit legacy hook artifact, then retire plaintext only if verified.

    ``interrupt_at`` may be ``before_object``, ``before_head``, or ``before_retire``.
    A mode change or local copy is not a commit.
    """

    return _legacy_hook_migration(
        source_path,
        source_preimage=source_preimage,
        destination=destination,
        access=access,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
        revision=revision,
        retention_policy=retention_policy,
        key=key,
        key_id=key_id,
        key_provider=key_provider,
        commit=True,
        interrupt_at=interrupt_at,
    )


def open_legacy_hook_artifact(
    destination: str | Path,
    *,
    access: Any,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    revision: str,
    key: bytes | None = None,
    key_id: str | None = None,
    key_provider: InjectedCaseKeyProvider | None = None,
) -> dict[str, Any]:
    """Open the last valid encrypted head for one destination binding."""

    binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=LEGACY_HOOK_ARTIFACT_CLASS,
        revision=revision,
        principal_id=principal_id,
    )
    assert_access_matches_binding(access, binding)
    loaded = _load_legacy_head(Path(destination))
    if not loaded.get("present") or loaded.get("corrupt") or loaded.get("aliased"):
        raise PrivateArtifactIntegrityError("corrupt_head" if loaded.get("present") else "head_missing")
    document = loaded["document"]
    if str(document.get("case_id") or "") != case_id or str(document.get("revision") or "") != revision:
        raise PrivateArtifactBindingError("foreign_case")
    resolved_id, resolved_key = _legacy_hook_keys(binding, key=key, key_id=key_id, key_provider=key_provider)
    if str(document.get("key_id") or "") != resolved_id:
        raise PrivateArtifactIntegrityError("authentication_failed")
    plaintext = open_private_artifact(
        loaded["envelope"],
        binding=binding,
        key=resolved_key,
        expected_key_id=resolved_id,
    )
    return {
        "status": "available",
        "data": plaintext,
        "source_preimage": hashlib.sha256(plaintext).hexdigest(),
        "verified_commit": document.get("verified_commit") is True,
        "network_durable": False,
        "durable": False,
    }


def _legacy_hook_migration(
    source_path: str | Path,
    *,
    source_preimage: str,
    destination: str | Path,
    access: Any,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    revision: str,
    retention_policy: str,
    key: bytes | None,
    key_id: str | None,
    key_provider: InjectedCaseKeyProvider | None,
    commit: bool,
    interrupt_at: str | None,
) -> dict[str, Any]:
    if interrupt_at not in {None, "before_object", "before_head", "before_retire"}:
        raise PrivateStorageError("unknown migration interrupt", code="interrupt_at")
    preimage = _legacy_preimage(source_preimage)
    _require_label(revision)
    if retention_policy not in LEGACY_HOOK_RETENTION:
        raise PrivateKeyMaterialError("retention_policy")
    binding_record = _legacy_hook_binding(
        tenant_id=tenant_id, case_id=case_id, principal_id=principal_id, revision=revision,
    )
    artifact_binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=LEGACY_HOOK_ARTIFACT_CLASS,
        revision=revision,
        principal_id=principal_id,
    )
    assert_access_matches_binding(access, artifact_binding)

    def finish(**kwargs: Any) -> dict[str, Any]:
        return _legacy_hook_receipt(
            revision=revision,
            preimage=preimage,
            binding=binding_record,
            retention_policy=retention_policy,
            **kwargs,
        )

    source = Path(source_path)
    dest = Path(destination)
    if source.is_symlink():
        return finish(status="rejected", code="aliased_source", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=True, last_valid_head_preserved=True, prior_head_present=False,
                      encryption_established=False)
    try:
        source_resolved = source.resolve()
        dest_resolved = dest.resolve() if dest.exists() else dest.absolute()
    except OSError:
        return finish(status="unavailable", code="destination_unavailable", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=True, last_valid_head_preserved=True, prior_head_present=False,
                      encryption_established=False)
    if source_resolved == dest_resolved or dest_resolved in source_resolved.parents or source_resolved in dest_resolved.parents:
        return finish(status="rejected", code="source_destination_overlap", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=True, last_valid_head_preserved=True, prior_head_present=False,
                      encryption_established=False)
    if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
        return finish(status="unavailable", code="destination_unavailable", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=True, last_valid_head_preserved=True, prior_head_present=False,
                      encryption_established=False)
    head_before = _load_legacy_head(dest) if dest.exists() else {"present": False}
    prior = bool(head_before.get("present"))
    inspected = _inspect_legacy_hook_source(source)
    source_existed = source.exists() or source.is_symlink()
    original = inspected.get("data") if inspected.get("ok") else (source.read_bytes() if source.is_file() and not source.is_symlink() else None)

    def preserved() -> bool:
        if original is None:
            return not source.exists()
        if not source.is_file() or source.is_symlink():
            return False
        try:
            return source.read_bytes() == original and source.stat().st_nlink >= 1
        except OSError:
            return False

    if head_before.get("aliased"):
        return finish(status="rejected", code="aliased_source", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    if not inspected.get("ok"):
        code = str(inspected.get("code") or "source_missing")
        status = "rejected" if code in {"aliased_source", "corrupt_source", "empty_source", "preimage_mismatch"} else "pending"
        if code == "source_missing" and prior and not head_before.get("corrupt"):
            status = "pending"
        return finish(status=status, code=code, encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved() if source_existed or original is not None else True,
                      last_valid_head_preserved=True, prior_head_present=prior, encryption_established=False)
    payload = bytes(inspected["data"])
    if hashlib.sha256(payload).hexdigest() != preimage:
        return finish(status="rejected", code="corrupt_source", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    if head_before.get("corrupt"):
        return finish(status="rejected", code="corrupt_head", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                      encryption_established=False)
    try:
        resolved_id, resolved_key = _legacy_hook_keys(
            artifact_binding, key=key, key_id=key_id, key_provider=key_provider,
        )
    except PrivateCryptoCapabilityError:
        return finish(status="unavailable", code="private_crypto_unavailable", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    except PrivateKeyMaterialError as exc:
        return finish(status="unavailable", code=str(exc.reason or "key_unavailable"), encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)

    document = head_before.get("document") if head_before.get("present") else None
    if isinstance(document, dict):
        same_binding = (
            document.get("tenant_id") == tenant_id
            and document.get("case_id") == case_id
            and document.get("principal_id") == principal_id
            and document.get("revision") == revision
            and document.get("artifact_class") == LEGACY_HOOK_ARTIFACT_CLASS
        )
        if not same_binding:
            return finish(status="rejected", code="binding_mismatch", encrypted=False, pending_kind="encryption",
                          verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                          source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                          encryption_established=False)
        if str(document.get("key_id") or "") != resolved_id:
            return finish(status="rejected", code="wrong_key", encrypted=False, pending_kind="encryption",
                          verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                          source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                          encryption_established=False)
        try:
            opened = open_private_artifact(
                head_before["envelope"], binding=artifact_binding, key=resolved_key, expected_key_id=resolved_id,
            )
        except PrivateArtifactIntegrityError:
            return finish(status="rejected", code="wrong_key", encrypted=False, pending_kind="encryption",
                          verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                          source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                          encryption_established=False)
        if opened != payload or str(document.get("source_preimage") or "") != preimage:
            return finish(status="rejected", code="preimage_mismatch", encrypted=False, pending_kind="encryption",
                          verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                          source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                          encryption_established=False)
        retired = document.get("plaintext_retired") is True and not source.exists()
        if commit and retention_policy == "retire_plaintext_after_verified_commit" and not retired and interrupt_at != "before_retire":
            retired = _retire_legacy_source(source, inspected, payload)
            if retired:
                updated = dict(document)
                updated["plaintext_retired"] = True
                _publish_legacy_head(dest, _json_bytes(updated))
        retirement = "retired" if retired else ("pending" if retention_policy == "retire_plaintext_after_verified_commit" else "retained")
        return finish(
            status="committed" if commit else "preflight",
            code="",
            encrypted=True,
            pending_kind="" if retirement != "pending" else "plaintext_retirement",
            verified_commit=True,
            plaintext_retired=retired,
            plaintext_retirement=retirement,
            source_bytes_preserved=not retired,
            last_valid_head_preserved=True,
            prior_head_present=True,
            encryption_established=True,
        )

    if not commit or interrupt_at == "before_object":
        return finish(
            status="preflight" if not commit else "interrupted",
            code="" if not commit else "interrupted",
            encrypted=False,
            pending_kind="encryption",
            verified_commit=False,
            plaintext_retired=False,
            plaintext_retirement="retained",
            source_bytes_preserved=preserved(),
            last_valid_head_preserved=True,
            prior_head_present=prior,
            encryption_established=False,
        )
    try:
        load_aesgcm()
        envelope = seal_private_artifact(payload, binding=artifact_binding, key=resolved_key, key_id=resolved_id)
        if open_private_artifact(envelope, binding=artifact_binding, key=resolved_key, expected_key_id=resolved_id) != payload:
            raise PrivateArtifactIntegrityError("readback_mismatch")
    except PrivateCryptoCapabilityError:
        return finish(status="unavailable", code="private_crypto_unavailable", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    digest = hashlib.sha256(envelope).hexdigest()
    object_path = dest / "objects" / f"{digest}.bin"
    if not object_path.exists():
        _write_exclusive(object_path, envelope)
    else:
        existing = _read_nofollow_bytes(object_path)
        if existing != envelope:
            return finish(status="rejected", code="destination_conflict", encrypted=False, pending_kind="encryption",
                          verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                          source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                          encryption_established=False)
    if interrupt_at == "before_head":
        return finish(status="interrupted", code="interrupted", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    head_document = {
        "schema": _LEGACY_HOOK_SCHEMA,
        "schema_version": 1,
        "artifact_class": LEGACY_HOOK_ARTIFACT_CLASS,
        "tenant_id": tenant_id,
        "case_id": case_id,
        "principal_id": principal_id,
        "revision": revision,
        "source_preimage": preimage,
        "ciphertext_sha256": digest,
        "key_id": resolved_id,
        "verified_commit": True,
        "plaintext_retired": False,
    }
    _publish_legacy_head(dest, _json_bytes(head_document))
    reread = _load_legacy_head(dest)
    if reread.get("corrupt") or reread.get("envelope") != envelope:
        return finish(status="rejected", code="readback_mismatch", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    confirmed = open_private_artifact(reread["envelope"], binding=artifact_binding, key=resolved_key, expected_key_id=resolved_id)
    if confirmed != payload or not preserved():
        return finish(status="rejected", code="readback_mismatch", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                      encryption_established=False)
    retired = False
    if retention_policy == "retire_plaintext_after_verified_commit" and interrupt_at != "before_retire":
        retired = _retire_legacy_source(source, inspected, payload)
        if retired:
            head_document["plaintext_retired"] = True
            _publish_legacy_head(dest, _json_bytes(head_document))
    retirement = "retired" if retired else ("pending" if retention_policy == "retire_plaintext_after_verified_commit" else "retained")
    return finish(
        status="committed",
        code="",
        encrypted=True,
        pending_kind="" if retirement != "pending" else "plaintext_retirement",
        verified_commit=True,
        plaintext_retired=retired,
        plaintext_retirement=retirement,
        source_bytes_preserved=not retired,
        last_valid_head_preserved=True,
        prior_head_present=prior,
        encryption_established=True,
    )


def assert_store_isolated_from_exports(store_dir: str | Path, export_dir: str | Path) -> None:
    """Refuse to keep a key store inside or next to an encrypted export directory."""

    store = Path(store_dir).resolve()
    export = Path(export_dir).resolve()
    if store == export or store in export.parents or export in store.parents or store.parent == export:
        raise PrivateKeyMaterialError("key_beside_export")


__all__ = [
    "ALGORITHM_NAME",
    "DATA_KEY_BYTES",
    "ENVELOPE_MAGIC",
    "InjectedCaseKeyProvider",
    "KIT_CRYPTOGRAPHY_FLOOR",
    "KIT_CRYPTOGRAPHY_FLOOR_IS_PACKAGE_VERSION",
    "MAX_ENVELOPE_BYTES",
    "NONCE_BYTES",
    "PrivateArtifactBinding",
    "PrivateArtifactBindingError",
    "PrivateArtifactIntegrityError",
    "PrivateCryptoCapabilityError",
    "PrivateKeyMaterialError",
    "PrivateStorageError",
    "ROOT_CRYPTOGRAPHY_SPEC",
    "SCHEMA_VERSION",
    "assert_access_matches_binding",
    "canonical_associated_data",
    "cryptography_available",
    "kit_crypto_contract",
    "kit_memory_gcm_associated_data_probe",
    "load_aesgcm",
    "open_private_artifact",
    "parse_private_envelope",
    "retrieve_private_artifact",
    "seal_private_artifact",
    "store_private_artifact",
    "RESOURCE_GRANT_SCHEMA",
    "RESOURCE_GRANT_VERSION",
    "resource_grant_associated_data",
    "wrap_resource_key_for_recipient",
    "unwrap_resource_key_for_recipient",
    "KEY_STORE_SCHEMA",
    "KEY_RECOVERY_SCHEMA",
    "PrivateKeyLockedError",
    "UserOwnedKeySession",
    "PORTABILITY_SCHEMA",
    "UNRECOVERED_KEY_EXPLANATION",
    "PrivatePortabilityError",
    "assert_store_isolated_from_exports",
    "assert_tree_excludes_unwrapped_keys",
    "export_encrypted_workspace",
    "import_encrypted_workspace",
    "read_private_workspace_generation",
    "read_unlock_passphrase",
    "stage_private_workspace",
    "task_key_receipt",
    "PrivateRevisionError",
    "PrivateRevisionInterrupted",
    "RevisionPublication",
    "commit_acknowledged_by_receipt",
    "commit_private_revision",
    "inspect_revision_journal",
    "read_private_revision",
    "private_revision_readiness",
    "recover_private_revision",
    "CaseManifestConflict",
    "CaseManifestPublication",
    "publish_case_manifest",
    "read_case_manifest",
    "recover_case_manifest",
    "ReplicaPolicy",
    "configure_replica_policy",
    "replica_policy",
    "select_private_storage_mode",
    "publish_encrypted_replicas",
    "reconcile_encrypted_replicas",
    "restore_encrypted_replicas",
    "restore_encrypted_workspace",
    "count_verified_ciphertext_replicas",
    "remote_storage_activation_count",
    "upstream_replication_fixture_qualification",
    "DELETION_PHASES",
    "DELETION_POLICIES",
    "bind_shared_legal_artifact",
    "delete_private_case",
    "normal_reset_retention_receipt",
    "read_case_tombstone",
    "record_managed_replica",
    "write_case_local_private_file",
    "LEGACY_HOOK_ARTIFACT_CLASS",
    "LEGACY_HOOK_RETENTION",
    "preflight_legacy_hook_migration",
    "commit_legacy_hook_migration",
    "open_legacy_hook_artifact",
    "legacy_hook_migration_claim",
    "DURABILITY_STATES",
    "verify_ciphertext_durability",
    "CiphertextDurabilityError",
    "KitLocalCiphertextBackend",
    "PRIVATE_RECORD_KINDS",
    "MAX_BOUND_RECOVERY_ATTEMPTS",
    "BoundPrivateRecordError",
    "commit_private_bound_record",
    "stage_interrupted_bound_record",
    "open_private_bound_record",
    "recover_private_bound_records",
    "qualify_content_address",
]


# Ciphertext durability is four observations. A local manifest commit, a queued
# replication acknowledgement, and a pin are never a verified replica. Only a
# Kit readback of the same ciphertext bytes can set durable. A CID string or a
# public gateway URL is not evidence.

DURABILITY_STATE_LOCAL_COMMIT = "local_commit"
DURABILITY_STATE_QUEUED_REPLICATION = "queued_replication"
DURABILITY_STATE_PIN = "pin"
DURABILITY_STATE_VERIFIED_REPLICA = "verified_replica"
DURABILITY_STATES = (
    DURABILITY_STATE_LOCAL_COMMIT,
    DURABILITY_STATE_QUEUED_REPLICATION,
    DURABILITY_STATE_PIN,
    DURABILITY_STATE_VERIFIED_REPLICA,
)
_GATEWAY_MARKERS = (
    "ipfs.io",
    "gateway.ipfs",
    "dweb.link",
    "cloudflare-ipfs.com",
    "ipfs.tech/ipfs",
    "https://",
    "http://",
)


class CiphertextDurabilityError(PrivateStorageError):
    """Kit durability could not be shown from ciphertext readback."""

    def __init__(self, code: str) -> None:
        super().__init__(code, code=code)


def _kit_replica_contract():
    """Load the current Kit replica vocabulary. A missing contract is a failure."""

    _prefer_vendored_kit()
    try:
        from ipfs_kit_py.core.replication.contracts import (
            NON_DURABLE_REPLICA_STATES,
            ReplicaState,
        )
    except Exception as exc:
        raise CiphertextDurabilityError("kit_contracts_unavailable") from exc
    if ReplicaState.QUEUED not in NON_DURABLE_REPLICA_STATES:
        raise CiphertextDurabilityError("kit_contracts_unavailable")
    if ReplicaState.VERIFIED in NON_DURABLE_REPLICA_STATES:
        raise CiphertextDurabilityError("kit_contracts_unavailable")
    return ReplicaState


def _reject_public_gateway(value: Any) -> None:
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in _GATEWAY_MARKERS):
            raise CiphertextDurabilityError("public_gateway_rejected")
        return
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_public_gateway(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_public_gateway(item)


def _kit_call(kit: Any, name: str, *args: Any) -> Any:
    method = getattr(kit, name, None)
    if not callable(method):
        raise CiphertextDurabilityError(f"kit_{name}_unavailable")
    try:
        result = method(*args)
    except CiphertextDurabilityError:
        raise
    except Exception as exc:
        raise CiphertextDurabilityError(f"kit_{name}_failed") from exc
    _reject_public_gateway(result if not isinstance(result, (bytes, bytearray)) else "")
    return result


def _ciphertext_commit_reference(result: Mapping[str, Any]) -> str:
    ref = result.get("ref") or result.get("locator")
    if isinstance(ref, str) and ref.strip() and ref == ref.strip() and len(ref) <= 200:
        if any(marker in ref.lower() for marker in _GATEWAY_MARKERS):
            raise CiphertextDurabilityError("public_gateway_rejected")
        return ref
    cid = result.get("cid")
    if isinstance(cid, str) and cid.strip() and "://" not in cid and len(cid) <= 200:
        return cid
    raise CiphertextDurabilityError("kit_ref_rejected")


def verify_ciphertext_durability(kit: Any, envelope: bytes) -> dict[str, Any]:
    """Commit, queue, pin, and read back one ciphertext through a Kit owner.

    ``durable`` is true only when ``readback`` returns the same bytes that
    ``manifest`` accepted. Queued replication and pin stay distinct and
    non-durable. Public gateway URLs are rejected. A CID is not proof.
    """

    if not isinstance(envelope, (bytes, bytearray)) or not bytes(envelope).startswith(ENVELOPE_MAGIC):
        raise CiphertextDurabilityError("ciphertext_required")
    payload = bytes(envelope)
    replica_state = _kit_replica_contract()
    states: list[dict[str, Any]] = []

    def _record(state: str, *, ref: str, kit_state: str) -> None:
        if state not in DURABILITY_STATES or any(item["state"] == state for item in states):
            raise CiphertextDurabilityError("durability_state_collision")
        states.append({
            "state": state,
            "ref": ref,
            "kit_replica_state": kit_state,
            "durable": False,
            "counts_as_verified_replica": False,
        })

    manifest = _kit_call(kit, "manifest", payload)
    if not isinstance(manifest, Mapping):
        raise CiphertextDurabilityError("kit_manifest_failed")
    ref = _ciphertext_commit_reference(manifest)
    _record(DURABILITY_STATE_LOCAL_COMMIT, ref=ref, kit_state="local_commit")

    queued = _kit_call(kit, "queue_replication", ref)
    if not isinstance(queued, Mapping):
        raise CiphertextDurabilityError("kit_queue_replication_failed")
    _record(
        DURABILITY_STATE_QUEUED_REPLICATION,
        ref=ref,
        kit_state=replica_state.QUEUED.value,
    )

    pinned = _kit_call(kit, "pin", ref)
    if not isinstance(pinned, Mapping) or pinned.get("pinned") is not True:
        raise CiphertextDurabilityError("kit_pin_failed")
    _record(DURABILITY_STATE_PIN, ref=ref, kit_state="pin")

    loaded = _kit_call(kit, "readback", ref)
    matched = isinstance(loaded, (bytes, bytearray)) and bytes(loaded) == payload
    if matched:
        _record(
            DURABILITY_STATE_VERIFIED_REPLICA,
            ref=ref,
            kit_state=replica_state.VERIFIED.value,
        )
        states[-1]["counts_as_verified_replica"] = True
        states[-1]["durable"] = True
    observed = [item["state"] for item in states]
    if observed[:3] != list(DURABILITY_STATES[:3]):
        raise CiphertextDurabilityError("durability_state_collision")
    if len(set(observed)) != len(observed):
        raise CiphertextDurabilityError("durability_state_collision")
    return {
        "states": states,
        "state_names": observed,
        "durable": matched and observed[-1] == DURABILITY_STATE_VERIFIED_REPLICA,
        "readback_matched": matched,
        "ciphertext_sha256": hashlib.sha256(payload).hexdigest(),
        "byte_length": len(payload),
        "ref": ref,
        "public_gateway_consulted": False,
        "cid_inference": False,
        "pin_is_durable": False,
        "queued_replication_is_durable": False,
        "local_commit_is_durable": False,
        "code": "" if matched else "readback_mismatch",
    }


# Evidence, annotations, classification revisions, and linkage records share one
# bound ciphertext path. Actual Kit AES-GCM output preserves the Host header
# and associated data. Actual Kit filesystem commits and verified disk readback
# qualify local durability; no remote producer is currently qualified here. A content hash, a queued acknowledgement, a local file, and a
# caller success flag are not remote durability and are not encryption.

PRIVATE_RECORD_KINDS = (
    "evidence",
    "annotation",
    "classification_revision",
    "linkage",
)
MAX_BOUND_RECOVERY_ATTEMPTS = 3
_MAX_BOUND_PLAINTEXT = 256 * 1024
_RECORD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,63}$")
_FORBIDDEN_BOUND_RECEIPT = frozenset({
    "success",
    "cid",
    "plaintext",
    "key",
    "data_key",
    "master_key",
    "private_key",
    "wrapped_key",
})


class BoundPrivateRecordError(PrivateStorageError):
    """A bound private record could not be sealed, qualified, or recovered."""

    def __init__(self, code: str) -> None:
        super().__init__(code, code=code)


def qualify_content_address(digest: str) -> dict[str, Any]:
    """A content hash is an address, not an encrypted or durable record."""

    if not isinstance(digest, str) or not digest.strip():
        raise BoundPrivateRecordError("content_address_rejected")
    return {
        "encrypted": False,
        "local_durable": False,
        "remote_durable": False,
        "counts_toward_desired": False,
        "queued_can_claim_committed": False,
        "content_address_is_encryption": False,
        "plaintext_fallback": False,
        "code": "content_address_is_not_encryption",
    }


def _require_record_id(record_id: str) -> str:
    if not isinstance(record_id, str) or _RECORD_ID_RE.fullmatch(record_id) is None:
        raise BoundPrivateRecordError("record_id_rejected")
    return record_id


def _require_record_kind(kind: str, binding: PrivateArtifactBinding) -> str:
    if kind not in PRIVATE_RECORD_KINDS:
        raise BoundPrivateRecordError("record_kind_rejected")
    if not isinstance(binding, PrivateArtifactBinding) or binding.artifact_kind != kind:
        raise BoundPrivateRecordError("binding_kind_mismatch")
    return kind


def _bound_root(root: str | Path) -> Path:
    path = Path(root)
    if path.is_symlink():
        raise BoundPrivateRecordError("symlink_rejected")
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    for name in ("journal", "objects", "staging"):
        child = path / name
        if child.is_symlink():
            raise BoundPrivateRecordError("symlink_rejected")
        child.mkdir(exist_ok=True)
        os.chmod(child, 0o700)
    return path


def _journal_path(root: Path, record_id: str) -> Path:
    return root / "journal" / record_id


def _staging_path(root: Path, record_id: str) -> Path:
    return root / "staging" / record_id


def _object_path(root: Path, content_ref: str) -> Path:
    if "/" in content_ref or content_ref.startswith("."):
        raise BoundPrivateRecordError("content_ref_rejected")
    return root / "objects" / content_ref


def _write_private_file(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise BoundPrivateRecordError("symlink_rejected")
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    directory = path.parent
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_private_file(path: Path) -> bytes | None:
    if not path.exists() or path.is_symlink() or not path.is_file():
        return None
    return path.read_bytes()


def _content_ref(envelope: bytes) -> str:
    return "ct." + hashlib.sha256(envelope).hexdigest()


def _load_journal(path: Path) -> dict[str, Any] | None:
    raw = _read_private_file(path)
    if raw is None:
        return None
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundPrivateRecordError("journal_malformed") from exc
    if not isinstance(document, dict):
        raise BoundPrivateRecordError("journal_malformed")
    return document


def _store_journal(path: Path, document: Mapping[str, Any]) -> None:
    _write_private_file(path, json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _binding_document(binding: PrivateArtifactBinding) -> dict[str, str]:
    return {
        "tenant_id": binding.tenant_id,
        "case_id": binding.case_id,
        "artifact_kind": binding.artifact_kind,
        "revision": binding.revision,
        "principal_id": binding.principal_id,
    }


def _binding_from_document(document: Mapping[str, Any]) -> PrivateArtifactBinding:
    try:
        return PrivateArtifactBinding(
            tenant_id=str(document["tenant_id"]),
            case_id=str(document["case_id"]),
            artifact_kind=str(document["artifact_kind"]),
            revision=str(document["revision"]),
            principal_id=str(document["principal_id"]),
        )
    except (KeyError, TypeError, PrivateArtifactBindingError) as exc:
        raise BoundPrivateRecordError("journal_malformed") from exc


def _seal_kit_bound_envelope(
    plaintext: bytes,
    *,
    key: bytes,
    key_id: str,
    binding: PrivateArtifactBinding,
) -> bytes:
    """Use actual Kit AES-GCM output in the existing opaque Host envelope."""

    if not isinstance(key_id, str) or not key_id.strip():
        raise BoundPrivateRecordError("ambient_key_rejected")
    _prefer_vendored_kit()
    try:
        from datetime import datetime, timezone

        from ipfs_kit_py.mcp.enterprise.encryption import (
            EncryptionAlgorithm,
            EncryptionKey,
            EncryptionManager,
            KeyManager,
            KeyStorageType,
            KeyType,
        )
    except Exception as exc:
        raise BoundPrivateRecordError("kit_encryption_unavailable") from exc
    key_bytes = _require_data_key(key)
    key_id_raw = _require_key_id(key_id)
    header = ENVELOPE_MAGIC + bytes((SCHEMA_VERSION, len(key_id_raw))) + key_id_raw
    associated = _envelope_associated_data(binding, header)
    manager_key = KeyManager(storage_type=KeyStorageType.MEMORY)
    manager_key._key_metadata[key_id] = EncryptionKey(
        id=key_id,
        type=KeyType.DATA,
        algorithm=EncryptionAlgorithm.AES_256_GCM,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    manager_key._store_key_material(key_id, key_bytes)
    try:
        encrypted = EncryptionManager(manager_key).encrypt(
            plaintext,
            key_id=key_id,
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            additional_authenticated_data=associated,
        )
        opened = EncryptionManager(manager_key).decrypt(encrypted)
    except Exception as exc:
        raise BoundPrivateRecordError("kit_encryption_failed") from exc
    finally:
        manager_key._key_cache.pop(key_id, None)
        manager_key._key_metadata.pop(key_id, None)
    nonce, ciphertext, tag = encrypted.initialization_vector, encrypted.encrypted_data, encrypted.auth_tag
    if (opened != plaintext or not isinstance(nonce, bytes) or len(nonce) != NONCE_BYTES
            or not isinstance(ciphertext, bytes) or len(ciphertext) != len(plaintext)
            or not isinstance(tag, bytes) or len(tag) != TAG_BYTES
            or encrypted.additional_authenticated_data != associated):
        raise BoundPrivateRecordError("kit_encryption_failed")
    # Persist no rich Kit object, original-size field, key, or binding metadata.
    envelope = header + nonce + ciphertext + tag
    if open_private_artifact(envelope, binding=binding, key=key_bytes, expected_key_id=key_id) != plaintext:
        raise BoundPrivateRecordError("kit_encryption_failed")
    return envelope


def _queued_cannot_claim_committed() -> bool:
    _prefer_vendored_kit()
    from ipfs_kit_py.core.wal.contracts import (
        WALAcknowledgementError,
        WALAcknowledgementMode,
        WALRecordState,
        assert_ack_allows_state,
    )

    try:
        assert_ack_allows_state(WALAcknowledgementMode.QUEUED, WALRecordState.COMMITTED)
    except WALAcknowledgementError:
        return True
    return False



def _receipt(
    *,
    record_id: str,
    kind: str,
    key_id: str,
    local_durable: bool,
    remote_durable: bool,
    counts_toward_desired: bool,
    placement_intents: int,
    recovery_attempts: int,
    phase: str,
    code: str,
) -> dict[str, Any]:
    if not _queued_cannot_claim_committed():
        raise BoundPrivateRecordError("queued_claimed_committed")
    receipt = {
        "record_id": record_id,
        "kind": kind,
        "key_id": key_id,
        "phase": phase,
        "local_durable": local_durable,
        "remote_durable": remote_durable,
        "counts_toward_desired": counts_toward_desired,
        "placement_intents": placement_intents,
        "recovery_attempts": recovery_attempts,
        "queued_can_claim_committed": False,
        "local_write_is_remote_durable": False,
        "content_address_is_encryption": False,
        "plaintext_fallback": False,
        "code": code,
    }
    leaked = _FORBIDDEN_BOUND_RECEIPT.intersection(receipt)
    if leaked:
        raise BoundPrivateRecordError("receipt_leaked")
    return receipt


def _seal_bound_record(
    plaintext: bytes,
    *,
    kind: str,
    binding: PrivateArtifactBinding,
    key: bytes,
    key_id: str,
) -> tuple[bytes, str]:
    _require_record_kind(kind, binding)
    if not isinstance(plaintext, (bytes, bytearray)) or not plaintext or len(plaintext) > _MAX_BOUND_PLAINTEXT:
        raise BoundPrivateRecordError("plaintext_rejected")
    if not isinstance(key_id, str) or not key_id.strip() or len(key_id) > 80:
        raise BoundPrivateRecordError("ambient_key_rejected")
    envelope = _seal_kit_bound_envelope(bytes(plaintext), key=key, key_id=key_id, binding=binding)
    if plaintext in envelope:
        raise BoundPrivateRecordError("plaintext_fallback")
    return envelope, _content_ref(envelope)


def stage_interrupted_bound_record(
    root: str | Path,
    *,
    record_id: str,
    kind: str,
    plaintext: bytes,
    binding: PrivateArtifactBinding,
    key: bytes,
    key_id: str,
) -> dict[str, Any]:
    """Seal and stage a record without publishing it. Recovery is still bounded."""

    record_id = _require_record_id(record_id)
    directory = _bound_root(root)
    journal = _journal_path(directory, record_id)
    if journal.exists():
        raise BoundPrivateRecordError("record_exists")
    envelope, content_ref = _seal_bound_record(
        plaintext, kind=kind, binding=binding, key=key, key_id=key_id,
    )
    _write_private_file(_staging_path(directory, record_id), envelope)
    _store_journal(journal, {
        "record_id": record_id,
        "kind": kind,
        "key_id": key_id,
        "content_ref": content_ref,
        "attempts": 0,
        "phase": "staged",
        "binding": _binding_document(binding),
    })
    return _receipt(
        record_id=record_id,
        kind=kind,
        key_id=key_id,
        local_durable=False,
        remote_durable=False,
        counts_toward_desired=False,
        placement_intents=0,
        recovery_attempts=0,
        phase="staged",
        code="staged_not_durable",
    )


def _bound_kit_types():
    _prefer_vendored_kit()
    try:
        from ipfs_kit_py.assurance.local_durable import LiveLocalFilesystemAdapter, LiveLocalResult
        from ipfs_kit_py.core.operation_contracts import DurabilityMode, OperationState
    except Exception as exc:
        raise BoundPrivateRecordError("kit_durability_unavailable") from exc
    return LiveLocalFilesystemAdapter, LiveLocalResult, DurabilityMode, OperationState


def _read_kit_bound_envelope(root: Path, content_ref: str) -> bytes:
    adapter_type, result_type, _durability_mode, states = _bound_kit_types()
    adapter = None
    try:
        # The private content reference is a path locator, never a public CID.
        _object_path(root, content_ref)
        adapter = adapter_type.reopen(root)
        result = adapter.get(content_ref, deadline=time.monotonic() + 5.0)
        if (type(result) is not result_type or result.state is not states.ACCEPTED
                or not result.success or _content_ref(result.data) != content_ref
                or result.resulting_content_cid != adapter_type.content_cid(result.data)):
            raise BoundPrivateRecordError("record_unavailable")
        return result.data
    except BoundPrivateRecordError:
        raise
    except Exception as exc:
        raise BoundPrivateRecordError("record_unavailable") from exc
    finally:
        if adapter is not None:
            adapter.close()


def _commit_kit_ciphertext(root: Path, content_ref: str, payload: bytes, *, create: bool) -> str:
    """Require an actual Kit local commit and verified disk reconstruction."""
    adapter_type, result_type, durability_mode, states = _bound_kit_types()
    adapter = None
    try:
        adapter = adapter_type(root) if create else adapter_type.reopen(root)
        deadline = time.monotonic() + 5.0
        committed = adapter.put(content_ref, payload, deadline=deadline)
        result = committed.canonical_result
        durability = result.durability
        if (type(committed) is not result_type or committed.state is not states.COMMITTED
                or not committed.success or durability is None
                or durability.mode is not durability_mode.BACKEND_DURABLE
                or not durability.backend_ack_id or not result.effect_evidence
                or set(durability.effect_evidence_ids) != {effect.evidence_id for effect in result.effect_evidence}
                or any(effect.backend_id != adapter.backend_id for effect in result.effect_evidence)):
            raise BoundPrivateRecordError("kit_durability_unproven")
        expected_cid = adapter_type.content_cid(payload)
        for observed in (committed, adapter.get(content_ref, deadline=deadline), adapter.digest(content_ref, deadline=deadline)):
            if (type(observed) is not result_type or not observed.success
                    or observed.resulting_content_cid != expected_cid):
                raise BoundPrivateRecordError("kit_durability_unproven")
            if observed is not committed and observed.data != payload:
                raise BoundPrivateRecordError("kit_durability_unproven")
    except BoundPrivateRecordError:
        raise
    except Exception as exc:
        raise BoundPrivateRecordError("kit_durability_unproven") from exc
    finally:
        if adapter is not None:
            adapter.close()
    if _read_kit_bound_envelope(root, content_ref) != payload:
        raise BoundPrivateRecordError("kit_durability_unproven")
    return expected_cid


def _publish_local(root: Path, record_id: str, content_ref: str) -> bool:
    staged = _read_private_file(_staging_path(root, record_id))
    if staged is None or _content_ref(staged) != content_ref:
        return False
    try:
        _commit_kit_ciphertext(root, content_ref, staged, create=True)
        return True
    except BoundPrivateRecordError as exc:
        if exc.code == "kit_durability_unavailable":
            raise
        return False


class KitLocalCiphertextBackend:
    """Explicit local Kit byte owner for already sealed Host artifacts.

    The existing EvidenceWorkspace owns catalog, versions, authorization and
    keys. This adapter adds no catalog, wallet, fallback, network pin or remote
    claim. Its required root stores only opaque envelopes and Kit metadata.
    """

    backend_name = "kit-local-ciphertext"

    def __init__(self, root: str | Path, *, create: bool = True) -> None:
        self._root = Path(root)
        self._closed = False
        if self._root.is_symlink():
            raise BoundPrivateRecordError("symlink_rejected")
        if create:
            self._root.mkdir(parents=True, exist_ok=True)
            os.chmod(self._root, 0o700)
        adapter_type, _result_type, _durability_mode, _states = _bound_kit_types()
        try:
            adapter = adapter_type(self._root) if create else adapter_type.reopen(self._root)
            adapter.close()
        except Exception as exc:
            raise BoundPrivateRecordError("kit_durability_unavailable") from exc

    @classmethod
    def reopen(cls, root: str | Path) -> "KitLocalCiphertextBackend":
        return cls(root, create=False)

    @staticmethod
    def _locator(cid: str) -> str:
        # Kit's raw CIDv1 uses sha2-256. Derive its private path rather than
        # assuming the CID itself is a filesystem locator or keeping a map in RAM.
        try:
            if not isinstance(cid, str) or not cid.startswith("b"):
                raise ValueError("not a raw CID")
            encoded = cid[1:]
            raw = base64.b32decode(encoded.upper() + "=" * ((-len(encoded)) % 8))
            canonical = "b" + base64.b32encode(raw).decode("ascii").rstrip("=").lower()
            if len(raw) != 36 or raw[:4] != b"\x01\x55\x12\x20" or canonical != cid:
                raise ValueError("unsupported CID")
        except Exception as exc:
            raise BoundPrivateRecordError("content_ref_rejected") from exc
        return "ct." + raw[4:].hex()

    def _require_open(self) -> None:
        if self._closed:
            raise BoundPrivateRecordError("kit_durability_unavailable")

    def add(self, data: bytes, pin: bool = True) -> dict[str, Any]:
        self._require_open()
        if not isinstance(data, bytes):
            raise BoundPrivateRecordError("ciphertext_required")
        parse_private_envelope(data)
        cid = _commit_kit_ciphertext(self._root, _content_ref(data), data, create=False)
        # A genuine local commit never implies an IPFS pin or remote replica.
        return {"cid": cid, "status": "available", "pinned": False}

    def cat(self, cid: str) -> bytes:
        self._require_open()
        payload = _read_kit_bound_envelope(self._root, self._locator(cid))
        parse_private_envelope(payload)
        return payload

    def close(self) -> None:
        self._closed = True


def commit_private_bound_record(
    root: str | Path,
    *,
    record_id: str,
    kind: str,
    plaintext: bytes,
    binding: PrivateArtifactBinding,
    key: bytes,
    key_id: str,
    remote_backend: Any | None = None,
) -> dict[str, Any]:
    """Qualify a Kit local commit. Arbitrary remote byte echoes stay unqualified."""

    record_id = _require_record_id(record_id)
    directory = _bound_root(root)
    journal = _journal_path(directory, record_id)
    if journal.exists():
        raise BoundPrivateRecordError("record_exists")
    envelope, content_ref = _seal_bound_record(
        plaintext, kind=kind, binding=binding, key=key, key_id=key_id,
    )
    _write_private_file(_staging_path(directory, record_id), envelope)
    document = {
        "record_id": record_id,
        "kind": kind,
        "key_id": key_id,
        "content_ref": content_ref,
        "attempts": 1,
        "phase": "staged",
        "binding": _binding_document(binding),
    }
    _store_journal(journal, document)
    local_ok = _publish_local(directory, record_id, content_ref)
    if local_ok:
        document["phase"] = "verified"
        _store_journal(journal, document)
    # No remote producer with an authenticated durability contract is installed
    # on this API. A queued acknowledgement, put/get echo, caller capability,
    # or even a second local adapter cannot establish a remote replica. Do not
    # invoke an unqualified backend or synthesize VERIFIED observations for it.
    remote_requested = remote_backend is not None
    code = "remote_unqualified" if remote_requested else ""
    if not local_ok:
        code = "readback_mismatch"
    return _receipt(
        record_id=record_id,
        kind=kind,
        key_id=key_id,
        local_durable=local_ok,
        remote_durable=False,
        counts_toward_desired=bool(local_ok and not remote_requested),
        placement_intents=0,
        recovery_attempts=1,
        phase="verified" if local_ok else "staged",
        code=code,
    )


def open_private_bound_record(
    root: str | Path,
    *,
    record_id: str,
    binding: PrivateArtifactBinding,
    key: bytes,
) -> bytes:
    """Open a published record. A missing or staged object is not plaintext."""

    record_id = _require_record_id(record_id)
    directory = _bound_root(root)
    document = _load_journal(_journal_path(directory, record_id))
    if document is None or document.get("phase") != "verified":
        raise BoundPrivateRecordError("record_unavailable")
    expected = _binding_from_document(document.get("binding") or {})
    if _binding_document(expected) != _binding_document(binding):
        raise BoundPrivateRecordError("binding_mismatch")
    content_ref = str(document.get("content_ref") or "")
    envelope = _read_kit_bound_envelope(directory, content_ref)
    try:
        return open_private_artifact(
            envelope,
            binding=binding,
            key=key,
            expected_key_id=str(document.get("key_id") or ""),
        )
    except PrivateKeyMaterialError as exc:
        raise BoundPrivateRecordError("key_unavailable") from exc
    except PrivateArtifactIntegrityError as exc:
        raise BoundPrivateRecordError("authentication_failed") from exc


def recover_private_bound_records(
    root: str | Path,
    *,
    key: bytes,
    bindings: Mapping[str, PrivateArtifactBinding],
    max_attempts: int = MAX_BOUND_RECOVERY_ATTEMPTS,
) -> dict[str, Any]:
    """Promote staged ciphertext within a fixed attempt budget. Never invent bytes."""

    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 8:
        raise BoundPrivateRecordError("recovery_bound_rejected")
    directory = _bound_root(root)
    promoted: list[str] = []
    exhausted: list[str] = []
    unavailable: list[str] = []
    for path in sorted((directory / "journal").iterdir()):
        if not path.is_file() or path.is_symlink():
            continue
        document = _load_journal(path)
        if document is None:
            continue
        record_id = str(document.get("record_id") or "")
        if document.get("phase") == "verified":
            continue
        attempts = document.get("attempts")
        if isinstance(attempts, bool) or not isinstance(attempts, int):
            raise BoundPrivateRecordError("journal_malformed")
        if attempts >= max_attempts:
            exhausted.append(record_id)
            continue
        attempts += 1
        document["attempts"] = attempts
        binding = bindings.get(record_id)
        content_ref = str(document.get("content_ref") or "")
        staged = _read_private_file(_staging_path(directory, record_id))
        matched = staged is not None and _content_ref(staged) == content_ref
        if binding is None or not matched or attempts > max_attempts:
            _store_journal(path, document)
            if attempts >= max_attempts:
                exhausted.append(record_id)
            else:
                unavailable.append(record_id)
            continue
        stored = _binding_from_document(document.get("binding") or {})
        if _binding_document(stored) != _binding_document(binding):
            _store_journal(path, document)
            unavailable.append(record_id)
            continue
        if not _publish_local(directory, record_id, content_ref):
            _store_journal(path, document)
            unavailable.append(record_id)
            continue
        document["phase"] = "verified"
        _store_journal(path, document)
        try:
            open_private_bound_record(directory, record_id=record_id, binding=binding, key=key)
        except BoundPrivateRecordError:
            document["phase"] = "staged"
            _store_journal(path, document)
            unavailable.append(record_id)
            continue
        promoted.append(record_id)
    return {
        "promoted": promoted,
        "exhausted": exhausted,
        "unavailable": unavailable,
        "max_attempts": max_attempts,
        "plaintext_fallback": False,
        "queued_can_claim_committed": False,
    }


_SCOPE_LEDGER = "scope-ledger.json"


def _scope_ledger_path(root: Path) -> Path:
    return root / _SCOPE_LEDGER


def _load_scope_ledger(root: Path) -> dict[str, Any]:
    path = _scope_ledger_path(root)
    if not path.exists():
        return {"revisions": {}}
    raw = _read_private_bytes(path)
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BoundPrivateRecordError("source_integrity") from exc
    revisions = document.get("revisions") if isinstance(document, dict) else None
    if not isinstance(revisions, dict):
        raise BoundPrivateRecordError("source_integrity")
    return {"revisions": revisions}


def _store_scope_ledger(root: Path, document: Mapping[str, Any]) -> None:
    _write_private_bytes(_scope_ledger_path(root), json.dumps(document, sort_keys=True).encode("utf-8"), protect_parent=True)


def probe_kit_evidence_capability() -> dict[str, Any]:
    """Ask the pinned Kit local owner and AES-GCM stack before any write."""

    if not cryptography_available():
        return {"available": False, "code": "missing_capability", "owner": "cryptography.hazmat.primitives.ciphers.aead.AESGCM"}
    try:
        _bound_kit_types()
    except BoundPrivateRecordError:
        return {"available": False, "code": "missing_capability", "owner": "ipfs_kit_py.assurance.local_durable.LiveLocalFilesystemAdapter"}
    return {
        "available": True,
        "code": "available",
        "owner": "ipfs_kit_py.assurance.local_durable.LiveLocalFilesystemAdapter",
        "plaintext_fallback": False,
    }


def commit_scoped_kit_record(
    root: str | Path,
    *,
    record_id: str,
    kind: str,
    plaintext: bytes,
    binding: PrivateArtifactBinding,
    key: bytes | None,
    key_id: str,
    source_sha256: str,
    key_locked: bool = False,
) -> dict[str, Any]:
    """Seal one case-scoped record only after Kit and the source hash agree.

    A locked key, a hash mismatch, or a revision that already names different
    bytes refuses before a new envelope is published. The ledger stores hashes
    and record ids, never plaintext.
    """

    directory = _bound_root(root)
    if key_locked or key is None:
        raise BoundPrivateRecordError("key_locked")
    if not isinstance(plaintext, (bytes, bytearray)) or not plaintext:
        raise BoundPrivateRecordError("source_integrity")
    payload = bytes(plaintext)
    digest = hashlib.sha256(payload).hexdigest()
    if not isinstance(source_sha256, str) or source_sha256 != digest:
        raise BoundPrivateRecordError("source_integrity")
    capability = probe_kit_evidence_capability()
    if capability["available"] is not True:
        raise BoundPrivateRecordError("missing_capability")
    record_id = _require_record_id(record_id)
    _require_record_kind(kind, binding)
    ledger = _load_scope_ledger(directory)
    prior = ledger["revisions"].get(binding.revision)
    if isinstance(prior, dict):
        if prior.get("sha256") != digest or prior.get("record_id") != record_id or prior.get("kind") != kind:
            raise BoundPrivateRecordError("conflicting_revision")
        opened = open_private_bound_record(directory, record_id=record_id, binding=binding, key=key)
        if hashlib.sha256(opened).hexdigest() != digest:
            raise BoundPrivateRecordError("source_integrity")
        return {
            "status": "qualified",
            "code": "replayed",
            "record_id": record_id,
            "kind": kind,
            "revision": binding.revision,
            "source_sha256": digest,
            "local_durable": True,
            "remote_durable": False,
            "plaintext_fallback": False,
            "plaintext_persisted": False,
            "kit_owner": capability["owner"],
        }
    receipt = commit_private_bound_record(
        directory,
        record_id=record_id,
        kind=kind,
        plaintext=payload,
        binding=binding,
        key=key,
        key_id=key_id,
    )
    if receipt.get("local_durable") is not True:
        raise BoundPrivateRecordError(str(receipt.get("code") or "missing_capability"))
    opened = open_private_bound_record(directory, record_id=record_id, binding=binding, key=key)
    if opened != payload:
        raise BoundPrivateRecordError("source_integrity")
    ledger["revisions"][binding.revision] = {
        "sha256": digest,
        "record_id": record_id,
        "kind": kind,
        "case_id": binding.case_id,
        "principal_id": binding.principal_id,
    }
    _store_scope_ledger(directory, ledger)
    return {
        "status": "qualified",
        "code": "committed",
        "record_id": record_id,
        "kind": kind,
        "revision": binding.revision,
        "source_sha256": digest,
        "local_durable": True,
        "remote_durable": False,
        "plaintext_fallback": False,
        "plaintext_persisted": False,
        "kit_owner": capability["owner"],
        "content_address_is_encryption": False,
    }


def open_scoped_kit_record(
    root: str | Path,
    *,
    record_id: str,
    binding: PrivateArtifactBinding,
    key: bytes | None,
    key_locked: bool = False,
) -> bytes:
    if key_locked or key is None:
        raise BoundPrivateRecordError("key_locked")
    return open_private_bound_record(root, record_id=record_id, binding=binding, key=key)
