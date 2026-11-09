from unittest.mock import patch
import base64
from types import SimpleNamespace

import pytest

from integrations.ipfs_datasets.storage import pin_cid, retrieve_bytes, store_bytes, translate_kit_operation_result


class _FakeKit:
    def __init__(self):
        self.blobs = {}

    def add_bytes(self, data, pin=True):
        cid = "bafykit"
        self.blobs[cid] = bytes(data)
        return {"success": True, "resulting_content_cid": cid, "pinned": pin}

    def cat(self, cid):
        return self.blobs[cid]

    def pin(self, cid):
        return {"success": True, "cid": cid}


def test_translate_kit_operation_result_reads_resulting_content_cid():
    translated = translate_kit_operation_result(
        {"success": True, "resulting_content_cid": "bafykit"},
        backend_name="kit",
    )
    assert translated["status"] == "available"
    assert translated["cid"] == "bafykit"
    assert translated["backend_name"] == "kit"


def test_store_retrieve_and_pin_roundtrip_on_fake_kit():
    backend = _FakeKit()
    stored = store_bytes(b"evidence bytes", backend=backend, backend_name="kit")
    assert stored["status"] == "available"
    assert stored["backend_name"] == "kit"
    assert stored["cid"] == "bafykit"
    retrieved = retrieve_bytes("bafykit", backend=backend, backend_name="kit")
    assert retrieved["data"] == b"evidence bytes"
    pinned = pin_cid("bafykit", backend=backend, backend_name="kit")
    assert pinned["backend_name"] == "kit"
    assert pinned["pinned"] is True


def test_pseudo_cid_is_not_network_pinned(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPLAINT_GENERATOR_IPFS_CACHE_DIR", str(tmp_path / "ipfs-cache"))
    with patch("integrations.ipfs_datasets.storage._load_optional_kit_backend", return_value=None):
        with patch("integrations.ipfs_datasets.storage.add_bytes", None):
            stored = store_bytes(b"local evidence", pin_content=True)
    assert stored["cid_kind"] == "pseudo_cid"
    assert stored["stored_local"] is True
    assert stored["pinned"] is False
    assert stored["uploaded"] is False
    assert stored["network_durable"] is False
    assert stored["replicated"] is False


def test_pin_failure_is_not_reported_as_pinned():
    class _PinFails:
        measurement_label = "measured-hermetic"

        def __init__(self):
            self.blobs = {}

        def add_bytes(self, data, pin=True):
            del pin
            self.blobs["bafymeasuredhermeticvalue"] = bytes(data)
            return {"success": True, "cid": "bafymeasuredhermeticvalue", "pinned": False}

        def cat(self, cid):
            return self.blobs[cid]

        def pin(self, cid):
            raise RuntimeError(f"pin rejected {cid}")

    stored = store_bytes(b"evidence bytes", backend=_PinFails(), backend_name="kit")
    assert stored["cid"] == "bafymeasuredhermeticvalue"
    assert stored["pinned"] is False
    assert stored["verified"] is True
    assert stored["measurement"] == "measured-hermetic"
    assert stored["network_durable"] is False
    assert stored["status"] == "available"


def test_readback_mismatch_is_not_verified():
    class _Mismatch:
        measurement_label = "measured-hermetic"

        def add_bytes(self, data, pin=True):
            del data, pin
            return {"success": True, "cid": "bafymismatchcid", "pinned": True}

        def cat(self, cid):
            del cid
            return b"other-bytes"

    stored = store_bytes(b"evidence bytes", backend=_Mismatch(), backend_name="kit")
    assert stored["verified"] is False
    assert stored["verification"]["matched"] is False
    assert stored["network_durable"] is False
    assert stored["pinned"] is True


def test_malformed_and_offline_results_stay_unpinned():
    class _Malformed:
        measurement_label = "measured-hermetic"

        def add_bytes(self, data, pin=True):
            del data, pin
            return 5

    malformed = store_bytes(b"evidence bytes", backend=_Malformed(), backend_name="kit")
    assert malformed["status"] == "error"
    assert malformed["pinned"] is False
    assert malformed["network_durable"] is False

    class _Offline:
        def add_bytes(self, data, pin=True):
            del data, pin
            raise ConnectionError("ipfs daemon offline")

    offline = store_bytes(b"evidence bytes", backend=_Offline(), backend_name="kit")
    assert offline["status"] == "error"
    assert offline["pinned"] is False
    assert offline["uploaded"] is False


def test_service_router_uses_declared_operations_not_add_bytes():
    class _Definition:
        def __init__(self, operation_id):
            self.operation_id = operation_id
            self.aliases = ()

    class _Registry:
        def __init__(self):
            self._ops = (
                _Definition("storage.ipfs.add"),
                _Definition("storage.ipfs.cat"),
            )

        def operations(self):
            return self._ops

    class _Router:
        measurement_label = "measured-hermetic"

        def __init__(self):
            self.registry = _Registry()
            self.blobs = {}
            self.calls = []

        def dispatch(self, operation, request, context=None):
            del context
            self.calls.append(operation)
            if operation == "storage.ipfs.add":
                cid = "bafyroutercid"
                self.blobs[cid] = bytes(request["data"])
                return {"success": True, "cid": cid, "pinned": False}
            if operation == "storage.ipfs.cat":
                return self.blobs[request["cid"]]
            raise AssertionError(operation)

    router = _Router()
    stored = store_bytes(b"routed", backend=router, backend_name="kit", pin_content=True)
    assert stored["calls"] if False else stored["cid"] == "bafyroutercid"
    assert stored["pinned"] is False
    assert stored["verified"] is True
    assert stored["receipt"]["pin_evidence"] == "pin_call_failed"
    assert "storage.ipfs.add" in router.calls
    assert "storage.ipfs.pin" not in router.calls
    assert all(call in {"storage.ipfs.add", "storage.ipfs.cat"} for call in router.calls)


def test_execute_protocol_is_not_called_as_byte_api():
    class _Protocol:
        def execute(self, operation, request, context):
            raise AssertionError("execute must go through ServiceRouter.dispatch")

    stored = store_bytes(b"nope", backend=_Protocol(), backend_name="kit")
    assert stored["pinned"] is False
    assert stored["status"] in {"error", "deferred"}
    assert "ServiceRouter" in stored["error"]


def test_import_and_probe_do_not_construct_kit(monkeypatch):
    import integrations.ipfs_datasets.storage as storage

    monkeypatch.delenv("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", raising=False)
    calls = []

    def _explode(*_args, **_kwargs):
        calls.append("import")
        raise AssertionError("kit import during disabled probe")

    monkeypatch.setattr(storage, "import_attr_optional", _explode)
    assert storage._load_optional_kit_backend() is None
    assert calls == []


def test_store_bytes_uses_local_cache_when_kit_and_datasets_router_are_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPLAINT_GENERATOR_IPFS_CACHE_DIR", str(tmp_path / "ipfs-cache"))
    with patch("integrations.ipfs_datasets.storage._load_optional_kit_backend", return_value=None):
        with patch("integrations.ipfs_datasets.storage.add_bytes", None):
            stored = store_bytes(b"local evidence")
    assert stored["backend_name"] == "local_cache"
    assert stored["status"] == "degraded"
    assert stored["cid"]
    with patch("integrations.ipfs_datasets.storage._load_optional_kit_backend", return_value=None):
        with patch("integrations.ipfs_datasets.storage.cat", None):
            retrieved = retrieve_bytes(stored["cid"])
    assert retrieved["backend_name"] == "local_cache"
    assert retrieved["data"] == b"local evidence"


@pytest.mark.parametrize("action", ["store", "retrieve", "pin"])
def test_configured_kit_failure_does_not_dispatch_a_second_backend(monkeypatch, action):
    from integrations.ipfs_datasets import storage

    class OfflineKit:
        measurement_label = "measured-hermetic"

        def add_bytes(self, data, pin=True):
            raise RuntimeError("Kit write failed")

        def cat(self, cid):
            raise RuntimeError("Kit read failed")

        def pin(self, cid):
            raise RuntimeError("Kit pin failed")

    def unexpected(*args, **kwargs):
        pytest.fail("configured Kit failure dispatched the datasets backend")

    monkeypatch.setattr(storage, "_load_optional_kit_backend", lambda: OfflineKit())
    for name in ("add_bytes", "cat", "pin", "_runtime_backend_probe"):
        monkeypatch.setattr(storage, name, unexpected)
    if action == "store":
        result = storage.store_bytes(b"synthetic public bytes")
    elif action == "retrieve":
        result = storage.retrieve_bytes("synthetic-cid")
    else:
        result = storage.pin_cid("synthetic-cid")
    assert result["status"] == "error"
    assert result["backend_name"] == "kit"
    assert "Kit" in result["error"]
    assert result["pinned"] is False
    assert result["verified"] is False
    assert result["deferred"] is True


@pytest.mark.parametrize("action", ["store", "retrieve", "pin"])
def test_explicit_missing_kit_stays_unavailable(monkeypatch, action):
    from integrations.ipfs_datasets import storage

    monkeypatch.setenv("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", "1")
    monkeypatch.setattr(storage, "_load_optional_kit_backend", lambda: None)
    def unexpected(*args, **kwargs):
        pytest.fail("explicit missing Kit dispatched the datasets backend")
    for name in ("add_bytes", "cat", "pin", "_runtime_backend_probe"):
        monkeypatch.setattr(storage, name, unexpected)
    calls = {
        "store": lambda: storage.store_bytes(b"synthetic bytes"),
        "retrieve": lambda: storage.retrieve_bytes("synthetic-cid"),
        "pin": lambda: storage.pin_cid("synthetic-cid"),
    }
    result = calls[action]()
    assert result["status"] == "unavailable"
    assert result["deferred"] is True
    assert result["uploaded"] is False


@pytest.mark.parametrize("failure", [
    {"success": False}, {"success": "false"}, {"status": "rejected"},
    {"error": "read failed"}, {"success": True, "error": "read failed"},
])
def test_failed_readback_dominates_matching_bytes(failure):
    class RejectedReadback:
        measurement_label = "measured-hermetic"

        def add_bytes(self, data, pin=True):
            self.data = bytes(data)
            return {"success": True, "cid": "bafyreadback", "pinned": False}

        def cat(self, cid):
            return {**failure, "data": self.data, "cid": cid}

    stored = store_bytes(b"synthetic bytes", backend=RejectedReadback())
    assert stored["verified"] is False
    assert stored["verification"]["matched"] is False
    assert stored["error"]
    assert stored["network_durable"] is False


@pytest.mark.parametrize("ack", [
    {"success": False, "pinned": True},
    {"success": "false", "pinned": True},
    {"success": True, "pinned": "false"},
    {"error": "write failed"},
    {"success": True, "error": "write failed"},
])
def test_failure_or_malformed_flags_dominate_nonempty_cid(ack):
    class MalformedAcknowledgement:
        measurement_label = "measured-hermetic"

        def add_bytes(self, data, pin=True):
            return {**ack, "cid": "bafynonempty", "data": bytes(data)}

    stored = store_bytes(b"synthetic bytes", backend=MalformedAcknowledgement())
    assert stored["status"] == "error"
    assert stored["uploaded"] is False
    assert stored["pinned"] is False
    assert stored["verified"] is False


def test_real_service_router_local_write_preserves_locator_and_local_receipt():
    from integrations.ipfs_datasets.loader import ensure_import_paths
    ensure_import_paths("ipfs_kit_py")
    from ipfs_kit_py.core.operation_registry import AuthorizationRequirement, OperationDefinition, OperationRegistry
    from ipfs_kit_py.core.service_router import ServiceRouter

    operations = tuple(OperationDefinition(
        operation_id=f"storage.local-durable.{action}", version=1,
        request_schema="synthetic-request@1", result_schema="synthetic-result@1",
        error_schema="synthetic-error@1", capability="synthetic.local-storage",
        authorization=AuthorizationRequirement.public(), handler_route="synthetic-local",
        transport_names={"python": f"synthetic-{action}"},
        aliases=("storage.ipfs.pin",) if action == "pin" else (),
    ) for action in ("put", "get", "pin"))
    class LocalBytes:
        def __init__(self):
            self.blobs = {}
            self.calls = []

        def execute(self, operation, request, context):
            self.calls.append((operation.operation_id, dict(request)))
            if operation.operation_id.endswith(".put"):
                self.blobs[request["path"]] = base64.b64decode(request["data_b64"])
                return {"success": True, "cid": "bafylocalcontent"}
            if operation.operation_id.endswith(".pin"):
                return {"success": True, "cid": request["cid"], "pinned": True}
            return self.blobs[request["path"]]

    service = LocalBytes()
    router = ServiceRouter(OperationRegistry(operations))
    router.measurement_label = "measured-hermetic"
    router.bind_service("synthetic-local", service, capabilities={"synthetic.local-storage"})
    stored = store_bytes(b"synthetic local bytes", backend=router)
    assert stored["stored_local"] is True
    assert stored["uploaded"] is False
    assert stored["pinned"] is False
    assert stored["verified"] is True
    assert stored["measurement"] == "measured-hermetic"
    assert stored["network_durable"] is False
    path = service.calls[0][1]["path"]
    assert path == next(request["path"] for operation, request in service.calls if operation.endswith(".get"))
    retrieved = retrieve_bytes(path, backend=router)
    pinned = pin_cid(stored["cid"], backend=router)
    assert retrieved["data"] == b"synthetic local bytes"
    for result in (retrieved, pinned):
        assert result["status"] == "available"
        assert result["stored_local"] is True
        assert result["uploaded"] is False
        assert result["pinned"] is False
        assert result["network_durable"] is False


def test_datasets_router_local_marker_does_not_become_a_network_pin(monkeypatch, tmp_path):
    from integrations.ipfs_datasets import storage

    cache = storage.LocalCacheIPFSBackend(str(tmp_path / "private-test-cache"))
    monkeypatch.setattr(storage, "_load_optional_kit_backend", lambda: None)
    monkeypatch.delenv("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", raising=False)
    monkeypatch.setattr(storage, "_runtime_backend_probe", lambda: {
        "backend": cache, "backend_name": "LocalCacheIPFSBackend", "status": "available", "reason": "",
    })
    monkeypatch.setattr(storage, "add_bytes", cache.add_bytes)
    monkeypatch.setattr(storage, "pin", cache.pin)
    stored = storage.store_bytes(b"synthetic cached bytes")
    pinned = storage.pin_cid(stored["cid"])
    for result in (stored, pinned):
        assert result["stored_local"] is True
        assert result["uploaded"] is False
        assert result["pinned"] is False
        assert result["network_durable"] is False
        assert result["cid_kind"] == "pseudo_cid"


@pytest.mark.parametrize("ack", [
    {"success": False, "pinned": True},
    {"success": "false", "pinned": True},
    {"success": True, "pinned": "false"},
    SimpleNamespace(success=True, pinned="false", cid="bafyrequested"),
    {"error": "pin failed"},
    {"success": True, "error": "pin failed"},
])
def test_datasets_pin_rejects_explicit_failure_and_malformed_flags(monkeypatch, ack):
    from integrations.ipfs_datasets import storage

    monkeypatch.setattr(storage, "_load_optional_kit_backend", lambda: None)
    monkeypatch.delenv("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", raising=False)
    monkeypatch.setattr(storage, "_runtime_backend_probe", lambda: {
        "backend": None, "backend_name": "datasets_router", "status": "available", "reason": "",
    })
    monkeypatch.setattr(storage, "pin", lambda cid: ack)
    result = storage.pin_cid("bafyrequested")
    assert result["status"] == "error"
    assert result["pinned"] is False
    assert result["verified"] is False
    assert result["network_durable"] is False


@pytest.mark.parametrize("path", ["datasets", "injected"])
@pytest.mark.parametrize("ack,accepted", [
    ({"Pins": ["QmRequested"]}, True),
    ({"Pins": ["QmOther", "QmRequested"]}, True),
    ({"Pins": []}, False),
    ({"Pins": ["QmOther"]}, False),
    ({"Pins": "QmRequested"}, False),
    ({"Pins": None}, False),
    ({"Pins": ["QmRequested", 7]}, False),
    ({"Pins": ["QmRequested", ""]}, False),
    ({"Pins": ["QmRequested"], "error": "pin failed"}, False),
    ({"Pins": ["QmRequested"], "status": "rejected"}, False),
    ({"Pins": ["QmRequested"], "success": False}, False),
    ({"Pins": ["QmRequested"], "success": "false"}, False),
    ({"Pins": ["QmRequested"], "pinned": False}, False),
    ({"Pins": ["QmRequested"], "pinned": "false"}, False),
    ({"Pins": ["QmRequested"], "cid": "QmOther"}, False),
    ({"Pins": ["QmRequested"], "Hash": "QmOther"}, False),
    ({"Pins": ["QmRequested"], "resulting_content_cid": "QmOther"}, False),
])
def test_kubo_pin_acknowledgement_binds_requested_cid(monkeypatch, path, ack, accepted):
    from integrations.ipfs_datasets import storage

    class PinBackend:
        measurement_label = "measured-hermetic"

        def pin(self, cid):
            assert cid == "QmRequested"
            return ack

    backend = PinBackend()
    if path == "injected":
        result = storage.pin_cid("QmRequested", backend=backend)
    else:
        monkeypatch.setattr(storage, "_load_optional_kit_backend", lambda: None)
        monkeypatch.delenv("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", raising=False)
        monkeypatch.setattr(storage, "_runtime_backend_probe", lambda: {
            "backend": backend, "backend_name": "datasets_router", "status": "available", "reason": "",
        })
        monkeypatch.setattr(storage, "pin", backend.pin)
        result = storage.pin_cid("QmRequested")
    assert result["cid"] == "QmRequested"
    assert result["status"] == ("available" if accepted else "error")
    assert result["pinned"] is accepted
    assert result["verified"] is False
    assert result["network_durable"] is False
    if accepted:
        assert result["measurement"] == "measured-hermetic"


@pytest.mark.parametrize("ack,accepted", [
    ({"Pins": ["QmRequested"]}, True),
    ({"Pins": ["QmRequested"], "error": "pin failed"}, False),
])
def test_store_reads_back_bytes_independently_of_kubo_pin_result(ack, accepted):
    class ByteBackend:
        measurement_label = "measured-hermetic"

        def add_bytes(self, data, pin=True):
            self.data = bytes(data)
            return {"success": True, "cid": "QmRequested", "pinned": False}

        def pin(self, cid):
            return ack

        def cat(self, cid):
            return self.data

    result = store_bytes(b"synthetic bytes", backend=ByteBackend())
    assert result["pinned"] is accepted
    assert result["verified"] is True
    assert result["network_durable"] is False
    assert result["measurement"] == "measured-hermetic"
