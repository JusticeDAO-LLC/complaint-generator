"""Real encrypted factual-review publication with current owner authority."""
import json
import os
from pathlib import Path
from threading import Event, Thread

from fastapi.testclient import TestClient
import pytest

from tests.test_cimp_gui_14 import (
    PASSPHRASE, _composed_case_world, _composed_headers, _composed_login,
)
from tests.test_gui24_private_context import _start

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.mark.parametrize("stage", ["crypto", "head_temp_fsync"])
@pytest.mark.parametrize("boundary,status", [("logout", 403), ("expire", 403), ("key_lock", 503)])
def test_refused_factual_review_never_publishes_or_recovers(tmp_path, monkeypatch, stage, boundary, status):
    from integrations import private_storage

    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    entered, release = Event(), Event()
    seal, fsync = private_storage._seal_role, private_storage._fsync_file

    def pause():
        entered.set()
        if not release.wait(10):
            raise AssertionError("bounded actual factual publication did not release")

    def seal_then_wait(payload, **values):
        result = seal(payload, **values)
        if stage == "crypto" and values.get("kind") == "revision-manifest":
            pause()
        return result

    def head_fsync_then_wait(fd, operation):
        fsync(fd, operation)
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if stage == "head_temp_fsync" and path.parent == repository and path.read_bytes().startswith(private_storage._HEAD_RECORD_MAGIC):
            pause()

    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _start(client, world.case)
        path = f"/api/graphs/{world.case.case_id}/factual"
        current = client.get(path, headers=_composed_headers(world.case))
        assert current.status_code == 200, current.text
        revision = current.json()["factual_review_revision"]
        repository = service.joined_revision_repository(world.case.tenant_id, world.case.case_id)
        head = (repository / "head.cgpe").read_bytes()
        monkeypatch.setattr(private_storage, "_seal_role", seal_then_wait)
        monkeypatch.setattr(private_storage, "_fsync_file", head_fsync_then_wait)
        results, errors = [], []

        def update():
            try:
                results.append(client.post(path + "/reviews", headers=_composed_headers(world.case, csrf), json={
                    "review_action": "propose", "origin": "model", "event_id": "synthetic-late-review",
                    "text": "Synthetic refused factual hypothesis.", "expected_graph_revision": revision,
                }))
            except BaseException as exc:
                errors.append(exc)

        worker = Thread(target=update, daemon=True)
        worker.start()
        try:
            assert entered.wait(10), "actual encrypted publication boundary was not reached"
            assert (repository / "head.cgpe").read_bytes() == head
            if boundary == "logout":
                assert client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": csrf}).status_code == 200
            elif boundary == "expire":
                world.clock["now"] += 301
            else:
                service.lock_private_keys()
        finally:
            release.set()
            worker.join(10)
        assert not worker.is_alive()
        if errors:
            raise errors[0]
        assert len(results) == 1 and results[0].status_code == status, results[0].text if results else "missing result"
        assert (repository / "head.cgpe").read_bytes() == head
        decisions = [json.loads(line) for line in (repository / "wal/transaction-decisions.jsonl").read_text().splitlines()]
        transaction = [item for item in decisions if item["kind"] == "intent"][-1]["transaction_id"]
        assert any(item["kind"] == "abort" and item["transaction_id"] == transaction for item in decisions)
        assert not any(item["kind"] == "commit" and item["transaction_id"] == transaction for item in decisions)
        if boundary == "key_lock":
            service.unlock_private_keys(passphrase=PASSPHRASE)
        service.recover_joined_intake_revision(world.case.tenant_id, case_id=world.case.case_id)
        service.recover_joined_intake_revision(world.case.tenant_id, case_id=world.case.case_id)
        assert (repository / "head.cgpe").read_bytes() == head
        _composed_login(client)
        observed = client.get(path, headers=_composed_headers(world.case))
        assert observed.status_code == 200, observed.text
        assert observed.json()["factual_review_revision"] == revision
        assert "Synthetic refused factual hypothesis." not in observed.text
