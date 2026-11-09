"""First-party AES-256-GCM encrypt-before-addressing tests for private artifacts.

Upstream Kit fixtures are a separate compatibility qualification. A missing or
skipped upstream file is not counted as a pass and does not replace the
assertions in this module. Historical session migration is DUR002 and is not
claimed here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from applications.complaint_workspace import WorkspaceAccess
from integrations.ipfs_datasets.storage import (
    LocalCacheIPFSBackend,
    retrieve_private_artifact as storage_retrieve_private_artifact,
    store_bytes,
    store_private_artifact as storage_store_private_artifact,
)
from integrations.private_storage import (
    ENVELOPE_MAGIC,
    KIT_CRYPTOGRAPHY_FLOOR,
    MAX_ENVELOPE_BYTES,
    ROOT_CRYPTOGRAPHY_SPEC,
    SCHEMA_VERSION,
    InjectedCaseKeyProvider,
    PrivateArtifactBinding,
    PrivateArtifactBindingError,
    PrivateArtifactIntegrityError,
    PrivateCryptoCapabilityError,
    PrivateKeyMaterialError,
    canonical_associated_data,
    kit_crypto_contract,
    kit_memory_gcm_associated_data_probe,
    open_private_artifact,
    parse_private_envelope,
    retrieve_private_artifact,
    seal_private_artifact,
    store_private_artifact,
)

SENTINEL = b"SENTINEL_PLAINTEXT_cimp_priv_003"
KEY_A = bytes(range(32))
KEY_B = bytes(range(32, 64))
KEY_ID_A = "case-key-a"
KEY_ID_B = "case-key-b"
REPO_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_FIXTURE = (
    REPO_ROOT / "external" / "ipfs_kit_py" / "tests" / "unit" / "test_aes_encryption.py"
)


def _binding(**overrides: str) -> PrivateArtifactBinding:
    fields = {
        "tenant_id": "tenant-a",
        "case_id": "case-a",
        "artifact_kind": "intake-note",
        "revision": "rev-1",
        "principal_id": "tenant-a",
    }
    fields.update(overrides)
    return PrivateArtifactBinding(**fields)


def _access(principal: str = "tenant-a", case_id: str = "case-a") -> WorkspaceAccess:
    return WorkspaceAccess.authenticated(principal, case_id=case_id)


def _provider(*pairs: tuple[tuple[str, str], tuple[str, bytes]]) -> InjectedCaseKeyProvider:
    return InjectedCaseKeyProvider(dict(pairs))


def _store(tmp_path: Path, plaintext: bytes = SENTINEL, **overrides: object) -> tuple[dict, LocalCacheIPFSBackend]:
    backend = LocalCacheIPFSBackend(cache_dir=str(tmp_path / "cache"))
    binding = _binding(**{k: v for k, v in overrides.items() if k in {
        "tenant_id", "case_id", "artifact_kind", "revision", "principal_id"
    }})
    access = overrides.get("access") or _access(binding.principal_id, binding.case_id)
    receipt = store_private_artifact(
        plaintext,
        access=access,
        tenant_id=binding.tenant_id,
        case_id=binding.case_id,
        artifact_kind=binding.artifact_kind,
        revision=binding.revision,
        principal_id=binding.principal_id,
        key=overrides.get("key", KEY_A),
        key_id=overrides.get("key_id", KEY_ID_A),
        backend=backend,
        replicate=overrides.get("replicate"),
        journal=overrides.get("journal"),
    )
    return receipt, backend


def _flip(blob: bytes, index: int) -> bytes:
    mutable = bytearray(blob)
    mutable[index] ^= 0x01
    return bytes(mutable)


def test_round_trip_uses_aes_gcm_envelope_and_expected_binding(tmp_path: Path) -> None:
    receipt, backend = _store(tmp_path)
    assert receipt["algorithm"] == "AES-256-GCM"
    assert receipt["schema_version"] == SCHEMA_VERSION
    assert receipt["key_id"] == KEY_ID_A
    assert receipt["private_artifact"] is True
    assert "size" not in receipt
    blob = backend.cat(receipt["cid"])
    assert blob.startswith(ENVELOPE_MAGIC)
    assert SENTINEL not in blob
    parsed = parse_private_envelope(blob)
    assert len(parsed["nonce"]) == 12
    assert parsed["key_id"] == KEY_ID_A
    opened = retrieve_private_artifact(
        receipt["cid"],
        access=_access(),
        tenant_id="tenant-a",
        case_id="case-a",
        artifact_kind="intake-note",
        revision="rev-1",
        key=KEY_A,
        key_id=KEY_ID_A,
        backend=backend,
    )
    assert opened["data"] == SENTINEL


def test_same_plaintext_twice_changes_ciphertext_and_address(tmp_path: Path) -> None:
    first, backend = _store(tmp_path)
    second = store_private_artifact(
        SENTINEL,
        access=_access(),
        tenant_id="tenant-a",
        case_id="case-a",
        artifact_kind="intake-note",
        revision="rev-1",
        key=KEY_A,
        key_id=KEY_ID_A,
        backend=backend,
    )
    blob_a = backend.cat(first["cid"])
    blob_b = backend.cat(second["cid"])
    assert blob_a != blob_b
    assert first["cid"] != second["cid"]
    assert parse_private_envelope(blob_a)["nonce"] != parse_private_envelope(blob_b)["nonce"]
    assert parse_private_envelope(blob_a)["ciphertext"] != parse_private_envelope(blob_b)["ciphertext"]


def test_public_store_bytes_is_not_reclassified_as_private(tmp_path: Path) -> None:
    backend = LocalCacheIPFSBackend(cache_dir=str(tmp_path / "public"))
    stored = store_bytes(SENTINEL, backend=backend)
    assert backend.cat(stored["cid"]) == SENTINEL
    assert not backend.cat(stored["cid"]).startswith(ENVELOPE_MAGIC)


def test_backend_hash_journal_and_replication_see_only_ciphertext(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    seen_hashes: list[bytes] = []
    replicated: list[bytes] = []
    journaled: list[dict] = []
    import integrations.ipfs_datasets.storage as storage_module

    real_sha256 = storage_module.hashlib.sha256

    def spy_sha256(data: bytes = b"", **kwargs: object) -> object:
        seen_hashes.append(bytes(data))
        return real_sha256(data, **kwargs)

    class SpyBackend(LocalCacheIPFSBackend):
        def __init__(self) -> None:
            super().__init__(cache_dir=str(tmp_path / "spy"))
            self.added: list[bytes] = []

        def add_bytes(self, data: bytes, *, pin: bool = True) -> str:
            self.added.append(bytes(data))
            return super().add_bytes(data, pin=pin)

    backend = SpyBackend()
    caplog.set_level("DEBUG")
    storage_module.hashlib.sha256 = spy_sha256
    try:
        receipt = store_private_artifact(
            SENTINEL,
            access=_access(),
            tenant_id="tenant-a",
            case_id="case-a",
            artifact_kind="intake-note",
            revision="rev-1",
            key=KEY_A,
            key_id=KEY_ID_A,
            backend=backend,
            replicate=replicated.append,
            journal=journaled.append,
        )
    finally:
        storage_module.hashlib.sha256 = real_sha256

    assert backend.added and all(SENTINEL not in item for item in backend.added)
    assert replicated and SENTINEL not in replicated[0]
    assert journaled and SENTINEL not in str(journaled[0]).encode()
    assert KEY_A not in str(journaled[0]).encode()
    assert seen_hashes and all(SENTINEL not in item for item in seen_hashes)
    assert receipt["cid"]
    disk = b"".join(path.read_bytes() for path in tmp_path.rglob("*") if path.is_file())
    assert SENTINEL not in disk
    assert KEY_A not in disk
    assert SENTINEL not in caplog.text.encode()
    assert KEY_A.hex() not in caplog.text


def test_ciphertext_and_tag_bit_flips_fail(tmp_path: Path) -> None:
    receipt, backend = _store(tmp_path)
    blob = bytearray(backend.cat(receipt["cid"]))
    parsed = parse_private_envelope(bytes(blob))
    body_start = bytes(blob).rfind(parsed["ciphertext"])
    blob[body_start] ^= 0x01
    backend.add_bytes(bytes(blob), pin=True)
    flipped_cid = backend._cid_for_bytes(bytes(blob))
    with pytest.raises(PrivateArtifactIntegrityError) as caught:
        retrieve_private_artifact(
            flipped_cid,
            access=_access(),
            tenant_id="tenant-a",
            case_id="case-a",
            artifact_kind="intake-note",
            revision="rev-1",
            key=KEY_A,
            key_id=KEY_ID_A,
            backend=backend,
        )
    assert caught.value.reason == "authentication_failed"
    tag_blob = bytearray(backend.cat(receipt["cid"]))
    tag_blob[-1] ^= 0x01
    with pytest.raises(PrivateArtifactIntegrityError):
        open_private_artifact(bytes(tag_blob), binding=_binding(), key=KEY_A, expected_key_id=KEY_ID_A)


def test_wrong_key_fails() -> None:
    envelope = seal_private_artifact(SENTINEL, binding=_binding(), key=KEY_A, key_id=KEY_ID_A)
    with pytest.raises(PrivateArtifactIntegrityError) as caught:
        open_private_artifact(envelope, binding=_binding(), key=KEY_B, expected_key_id=KEY_ID_A)
    assert caught.value.reason == "authentication_failed"


def test_nonce_header_and_version_tamper_fail() -> None:
    envelope = seal_private_artifact(SENTINEL, binding=_binding(), key=KEY_A, key_id=KEY_ID_A)
    parsed = parse_private_envelope(envelope)
    nonce_at = envelope.find(parsed["nonce"])
    with pytest.raises(PrivateArtifactIntegrityError):
        open_private_artifact(_flip(envelope, nonce_at), binding=_binding(), key=KEY_A, expected_key_id=KEY_ID_A)
    with pytest.raises(PrivateArtifactIntegrityError) as header:
        open_private_artifact(_flip(envelope, 0), binding=_binding(), key=KEY_A, expected_key_id=KEY_ID_A)
    assert header.value.reason == "malformed"
    versioned = bytearray(envelope)
    versioned[4] = SCHEMA_VERSION + 1
    with pytest.raises(PrivateArtifactIntegrityError) as version:
        open_private_artifact(bytes(versioned), binding=_binding(), key=KEY_A, expected_key_id=KEY_ID_A)
    assert version.value.reason == "unsupported_version"
    with pytest.raises(PrivateArtifactIntegrityError):
        PrivateArtifactBinding(
            tenant_id="tenant-a",
            case_id="case-a",
            artifact_kind="intake-note",
            revision="rev-1",
            principal_id="tenant-a",
            schema_version=99,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "tenant-b"),
        ("case_id", "case-b"),
        ("artifact_kind", "export"),
        ("revision", "rev-2"),
        ("principal_id", "other-principal"),
    ],
)
def test_wrong_binding_field_fails(field: str, value: str) -> None:
    envelope = seal_private_artifact(SENTINEL, binding=_binding(), key=KEY_A, key_id=KEY_ID_A)
    with pytest.raises(PrivateArtifactIntegrityError) as caught:
        open_private_artifact(envelope, binding=_binding(**{field: value}), key=KEY_A, expected_key_id=KEY_ID_A)
    assert caught.value.reason == "authentication_failed"


def test_cross_case_envelope_substitution_fails(tmp_path: Path) -> None:
    backend = LocalCacheIPFSBackend(cache_dir=str(tmp_path / "cases"))
    left = store_private_artifact(
        b"left-case-secret",
        access=_access("tenant-a", "case-a"),
        tenant_id="tenant-a",
        case_id="case-a",
        artifact_kind="intake-note",
        revision="rev-1",
        key=KEY_A,
        key_id=KEY_ID_A,
        backend=backend,
    )
    right = store_private_artifact(
        b"right-case-secret",
        access=_access("tenant-b", "case-b"),
        tenant_id="tenant-b",
        case_id="case-b",
        artifact_kind="intake-note",
        revision="rev-1",
        principal_id="tenant-b",
        key=KEY_B,
        key_id=KEY_ID_B,
        backend=backend,
    )
    swapped = backend.cat(left["cid"])
    with pytest.raises(PrivateArtifactIntegrityError):
        open_private_artifact(
            swapped,
            binding=_binding(tenant_id="tenant-b", case_id="case-b", principal_id="tenant-b"),
            key=KEY_B,
            expected_key_id=KEY_ID_B,
        )
    with pytest.raises((PrivateArtifactIntegrityError, PrivateArtifactBindingError)):
        retrieve_private_artifact(
            right["cid"],
            access=_access("tenant-a", "case-a"),
            tenant_id="tenant-a",
            case_id="case-a",
            artifact_kind="intake-note",
            revision="rev-1",
            key=KEY_A,
            key_id=KEY_ID_A,
            backend=backend,
        )


def test_malformed_and_oversized_envelopes_fail() -> None:
    with pytest.raises(PrivateArtifactIntegrityError) as short:
        parse_private_envelope(b"CGPE")
    assert short.value.reason == "malformed"
    with pytest.raises(PrivateArtifactIntegrityError) as huge:
        parse_private_envelope(b"x" * (MAX_ENVELOPE_BYTES + 1))
    assert huge.value.reason == "oversized"
    envelope = seal_private_artifact(SENTINEL, binding=_binding(), key=KEY_A, key_id=KEY_ID_A)
    with pytest.raises(PrivateArtifactIntegrityError) as truncated:
        parse_private_envelope(envelope[:20])
    assert truncated.value.reason == "malformed"


def test_missing_crypto_is_recoverable_and_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = LocalCacheIPFSBackend(cache_dir=str(tmp_path / "none"))
    writes: list[bytes] = []
    real_add = backend.add_bytes

    def record(data: bytes, *, pin: bool = True) -> str:
        writes.append(bytes(data))
        return real_add(data, pin=pin)

    backend.add_bytes = record  # type: ignore[method-assign]

    def unavailable() -> object:
        raise PrivateCryptoCapabilityError("AES-256-GCM is unavailable")

    monkeypatch.setattr("integrations.private_storage.load_aesgcm", unavailable)
    with pytest.raises(PrivateCryptoCapabilityError) as caught:
        store_private_artifact(
            SENTINEL,
            access=_access(),
            tenant_id="tenant-a",
            case_id="case-a",
            artifact_kind="intake-note",
            revision="rev-1",
            key=KEY_A,
            key_id=KEY_ID_A,
            backend=backend,
        )
    assert caught.value.recoverable is True
    assert caught.value.code == "private_crypto_unavailable"
    assert writes == []
    assert list(tmp_path.rglob("*")) == [] or all(not path.is_file() for path in tmp_path.rglob("*"))
    assert not hasattr(caught.value, "plaintext")


def test_no_generated_default_key_or_plaintext_xor_fallback() -> None:
    with pytest.raises(PrivateKeyMaterialError) as missing:
        store_private_artifact(
            SENTINEL,
            access=_access(),
            tenant_id="tenant-a",
            case_id="case-a",
            artifact_kind="intake-note",
            revision="rev-1",
            backend=None,
        )
    assert missing.value.recoverable is True
    envelope = seal_private_artifact(SENTINEL, binding=_binding(), key=KEY_A, key_id=KEY_ID_A)
    xored = bytes(byte ^ KEY_A[index % len(KEY_A)] for index, byte in enumerate(SENTINEL))
    assert xored not in envelope
    assert SENTINEL not in envelope


def test_associated_data_omits_plaintext_and_changes_with_binding() -> None:
    left = canonical_associated_data(_binding())
    right = canonical_associated_data(_binding(case_id="case-b"))
    assert left != right
    assert b"SENTINEL" not in left
    assert b"filename" not in left
    envelope = seal_private_artifact(SENTINEL, binding=_binding(), key=KEY_A, key_id=KEY_ID_A)
    assert left not in envelope
    assert _binding().tenant_id.encode() not in envelope


def test_unauthenticated_and_cross_principal_access_fail(tmp_path: Path) -> None:
    backend = LocalCacheIPFSBackend(cache_dir=str(tmp_path / "auth"))
    with pytest.raises(PrivateArtifactBindingError):
        store_private_artifact(
            SENTINEL,
            access=WorkspaceAccess.unauthenticated(),
            tenant_id="tenant-a",
            case_id="case-a",
            artifact_kind="intake-note",
            revision="rev-1",
            key=KEY_A,
            key_id=KEY_ID_A,
            backend=backend,
        )
    with pytest.raises(PrivateArtifactBindingError):
        store_private_artifact(
            SENTINEL,
            access=_access("tenant-a", "case-b"),
            tenant_id="tenant-a",
            case_id="case-a",
            artifact_kind="intake-note",
            revision="rev-1",
            key=KEY_A,
            key_id=KEY_ID_A,
            backend=backend,
        )
    assert list(backend.blobs_dir.glob("*")) == []


def test_injected_provider_resolves_per_case_and_storage_facade_matches(tmp_path: Path) -> None:
    provider = _provider(
        (("tenant-a", "case-a"), (KEY_ID_A, KEY_A)),
        (("tenant-b", "case-b"), (KEY_ID_B, KEY_B)),
    )
    backend = LocalCacheIPFSBackend(cache_dir=str(tmp_path / "provider"))
    receipt = storage_store_private_artifact(
        SENTINEL,
        access=_access(),
        tenant_id="tenant-a",
        case_id="case-a",
        artifact_kind="intake-note",
        revision="rev-1",
        key_provider=provider,
        backend=backend,
    )
    opened = storage_retrieve_private_artifact(
        receipt["cid"],
        access=_access(),
        tenant_id="tenant-a",
        case_id="case-a",
        artifact_kind="intake-note",
        revision="rev-1",
        key_provider=provider,
        backend=backend,
    )
    assert opened["data"] == SENTINEL
    with pytest.raises(PrivateKeyMaterialError):
        provider.resolve(_binding(tenant_id="tenant-c", case_id="case-c", principal_id="tenant-c"))


def test_dependency_contract_keeps_root_pin_and_optional_extras() -> None:
    project = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    kit_requirements = (REPO_ROOT / "external" / "ipfs_kit_py" / "requirements.txt").read_text(encoding="utf-8")
    assert ROOT_CRYPTOGRAPHY_SPEC in project
    assert ROOT_CRYPTOGRAPHY_SPEC in requirements
    assert "private-storage" in project
    assert "keyring>=" in project
    assert KIT_CRYPTOGRAPHY_FLOOR in kit_requirements
    contract = kit_crypto_contract()
    assert contract["kit_cryptography_floor_is_package_version"] is False
    assert contract["aes_encryption_string_api_sufficient"] is False
    assert contract["default_key_generated"] is False
    assert contract["historical_sessions_migrated"] is False
    assert contract["keyring_installed_by_default"] is False
    assert "cryptography>=41.0.0" in requirements
    assert "cryptography>=38.0.0" not in requirements.split("Private-storage contract", 1)[0]


def test_kit_probe_and_upstream_fixture_do_not_replace_first_party(tmp_path: Path) -> None:
    receipt, backend = _store(tmp_path / "first-party")
    opened = retrieve_private_artifact(
        receipt["cid"],
        access=_access(),
        tenant_id="tenant-a",
        case_id="case-a",
        artifact_kind="intake-note",
        revision="rev-1",
        key=KEY_A,
        key_id=KEY_ID_A,
        backend=backend,
    )
    assert opened["data"] == SENTINEL

    probe = kit_memory_gcm_associated_data_probe(b"probe", KEY_A, canonical_associated_data(_binding()))
    assert probe["substitutes_for_first_party"] is False
    assert probe["used_on_canonical_envelope"] is False
    assert probe["passed"] is False

    qualification = _upstream_kit_fixture_qualification()
    assert qualification["substitutes_first_party"] is False
    if qualification["status"] in {"absent", "skipped", "failed", "uncollected"}:
        assert qualification["passed"] is False
    if qualification["status"] == "passed":
        assert qualification["fixture_present"] is True
        assert qualification["skipped"] == 0
    assert hashlib.sha256(SENTINEL).hexdigest() not in receipt["cid"]


def _upstream_kit_fixture_qualification() -> dict[str, object]:
    """Record scope only: upstream compatibility is run and reported separately.

    Kit parent conftest bootstraps IPFS services. A crypto unit test must not
    launch that nested suite or hide its failure in a passing outer assertion.
    """
    return {
        "fixture": str(UPSTREAM_FIXTURE),
        "fixture_present": UPSTREAM_FIXTURE.is_file(),
        "passed": False,
        "status": "separate_qualification_required" if UPSTREAM_FIXTURE.is_file() else "absent",
        "skipped": None,
        "returncode": None,
        "substitutes_first_party": False,
    }


@pytest.mark.parametrize('expected', [None, KEY_ID_A, 'case-key-b'])
def test_routing_key_id_tamper_is_authenticated_even_without_optional_expectation(expected) -> None:
    envelope = bytearray(seal_private_artifact(SENTINEL, binding=_binding(), key=KEY_A, key_id=KEY_ID_A))
    # The same-length alternative is structurally valid and uses the SAME key;
    # only cryptographic binding of the routing header detects substitution.
    envelope[6:6 + len(KEY_ID_A)] = b'case-key-b'
    with pytest.raises(PrivateArtifactIntegrityError):
        open_private_artifact(bytes(envelope), binding=_binding(), key=KEY_A, expected_key_id=expected)


@pytest.mark.parametrize('version', [True, 1.0, 2.0, '2'])
def test_schema_version_requires_exact_supported_integer(version) -> None:
    with pytest.raises(PrivateArtifactIntegrityError, match='unsupported_version'):
        PrivateArtifactBinding('tenant-a', 'case-a', 'intake-note', 'rev-1', 'tenant-a', schema_version=version)


def test_v1_real_crypto_fixture_is_explicitly_unsupported_without_plaintext_migration() -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    fields = ['private-artifact-aad', '1', 'tenant-a', 'case-a', 'tenant-a', 'intake-note', 'rev-1']
    legacy_aad = b''.join(len(field.encode()).to_bytes(4, 'big') + field.encode() for field in fields)
    nonce = bytes(range(12))  # Fixed synthetic legacy fixture only.
    ciphertext = AESGCM(KEY_A).encrypt(nonce, SENTINEL, legacy_aad)
    header = ENVELOPE_MAGIC + bytes((1, len(KEY_ID_A))) + KEY_ID_A.encode()
    legacy = header + nonce + ciphertext
    assert AESGCM(KEY_A).decrypt(nonce, ciphertext, legacy_aad) == SENTINEL
    with pytest.raises(PrivateArtifactIntegrityError, match='unsupported_version'):
        open_private_artifact(legacy, binding=_binding(), key=KEY_A, expected_key_id=KEY_ID_A)


@pytest.mark.parametrize('failure', ['rng_oserror', 'rng_unsupported', 'backend_constructor', 'backend_encrypt'])
def test_crypto_capability_failure_is_typed_sanitized_and_writes_nothing(tmp_path, monkeypatch, failure) -> None:
    import traceback
    import integrations.private_storage as private
    from cryptography.exceptions import UnsupportedAlgorithm
    secret_error = 'SYNTHETIC_SECRET_ERROR /private/case/keypath'
    observed = {'backend': [], 'replicate': [], 'journal': []}
    class Backend:
        def add_bytes(self, data, **kwargs):
            observed['backend'].append(data)
            raise AssertionError('crypto failure reached storage')
    if failure.startswith('rng_'):
        def unavailable(_size):
            if failure == 'rng_oserror':
                raise OSError(secret_error)
            raise NotImplementedError(secret_error)
        monkeypatch.setattr(private.os, 'urandom', unavailable)
    else:
        class UnavailableAES:
            def __init__(self, _key):
                if failure == 'backend_constructor':
                    raise UnsupportedAlgorithm(secret_error)
            def encrypt(self, *args):
                raise UnsupportedAlgorithm(secret_error)
        monkeypatch.setattr(private, 'load_aesgcm', lambda: UnavailableAES)
    with pytest.raises(PrivateCryptoCapabilityError) as caught:
        store_private_artifact(SENTINEL, access=_access(), tenant_id='tenant-a', case_id='case-a',
            artifact_kind='intake-note', revision='rev-1', key=KEY_A, key_id=KEY_ID_A,
            backend=Backend(), replicate=observed['replicate'].append, journal=observed['journal'].append)
    assert caught.value.recoverable is True and caught.value.code == 'private_crypto_unavailable'
    assert secret_error not in str(caught.value)
    assert secret_error not in ''.join(traceback.format_exception(caught.value))
    assert observed == {'backend': [], 'replicate': [], 'journal': []}
    assert list(tmp_path.iterdir()) == []


def test_decrypt_backend_unavailable_is_not_misreported_as_corrupt_ciphertext(monkeypatch) -> None:
    import integrations.private_storage as private
    from cryptography.exceptions import UnsupportedAlgorithm
    envelope = seal_private_artifact(SENTINEL, binding=_binding(), key=KEY_A, key_id=KEY_ID_A)
    class UnavailableAES:
        def __init__(self, _key):
            pass
        def decrypt(self, *args):
            raise UnsupportedAlgorithm('SYNTHETIC_SECRET_BACKEND_ERROR')
    monkeypatch.setattr(private, 'load_aesgcm', lambda: UnavailableAES)
    with pytest.raises(PrivateCryptoCapabilityError) as caught:
        open_private_artifact(envelope, binding=_binding(), key=KEY_A, expected_key_id=KEY_ID_A)
    assert caught.value.recoverable and 'SYNTHETIC_SECRET_BACKEND_ERROR' not in str(caught.value)


def test_first_party_suite_never_runs_nested_upstream_process(monkeypatch) -> None:
    import subprocess
    def forbidden(*args, **kwargs):
        pytest.fail('first-party unit test launched upstream subprocess')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    report = _upstream_kit_fixture_qualification()
    assert report['passed'] is False
    assert report['status'] in {'absent', 'separate_qualification_required'}
