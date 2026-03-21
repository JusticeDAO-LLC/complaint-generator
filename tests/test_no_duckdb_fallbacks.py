from mediator.claim_support_hooks import ClaimSupportHook
from mediator.evidence_hooks import EvidenceStateHook


class _MediatorStub:
    def __init__(self):
        self.state = type("State", (), {"username": "stub-user", "hashed_username": "stub-hash"})()
        self.events = []

    def log(self, event_type, **data):
        self.events.append((event_type, data))


def test_evidence_state_hook_keeps_records_in_memory_when_duckdb_is_unavailable(monkeypatch):
    import mediator.evidence_hooks as evidence_hooks

    monkeypatch.setattr(evidence_hooks, "DUCKDB_AVAILABLE", False)
    mediator = _MediatorStub()
    hook = EvidenceStateHook(mediator, db_path="/tmp/nonexistent-evidence.duckdb")

    result = hook.upsert_evidence_record(
        user_id="memory-user",
        evidence_info={
            "cid": "bafy-memory-evidence",
            "type": "document",
            "size": 12,
            "timestamp": "2026-03-21T00:00:00+00:00",
            "metadata": {"filename": "notice.txt"},
            "document_graph": {
                "status": "available",
                "entities": [{"id": "e1", "type": "person", "name": "Dana Morris"}],
                "relationships": [{"id": "r1", "source_id": "e1", "target_id": "e1", "relation_type": "mentioned_in"}],
                "facts": [{"fact_id": "f1", "text": "HACC sent an adverse notice on March 3, 2026."}],
            },
        },
        claim_type="housing_discrimination",
        description="Adverse notice",
    )

    assert result["created"] is True
    evidence = hook.get_user_evidence("memory-user")
    assert len(evidence) == 1
    assert evidence[0]["cid"] == "bafy-memory-evidence"
    assert hook.get_evidence_by_cid("bafy-memory-evidence")["claim_type"] == "housing_discrimination"
    assert hook.get_evidence_graph(evidence[0]["id"])["status"] == "available"
    assert hook.get_evidence_facts(evidence[0]["id"])[0]["text"] == "HACC sent an adverse notice on March 3, 2026."


def test_claim_support_hook_keeps_links_in_memory_when_duckdb_is_unavailable(monkeypatch):
    import mediator.claim_support_hooks as claim_support_hooks

    monkeypatch.setattr(claim_support_hooks, "DUCKDB_AVAILABLE", False)
    mediator = _MediatorStub()
    hook = ClaimSupportHook(mediator, db_path="/tmp/nonexistent-claim-support.duckdb")

    hook.register_claim_requirements(
        "memory-user",
        {
            "housing_discrimination": [
                "Protected trait",
                "Adverse housing action",
            ]
        },
    )
    link_result = hook.upsert_support_link(
        user_id="memory-user",
        claim_type="housing_discrimination",
        support_kind="evidence",
        support_ref="bafy-memory-evidence",
        support_label="Adverse notice",
        source_table="evidence",
    )

    assert link_result["created"] is True
    links = hook.get_support_links("memory-user", "housing_discrimination")
    assert len(links) == 1
    summary = hook.summarize_claim_support("memory-user", "housing_discrimination")
    assert summary["available"] is False
    assert summary["total_links"] == 1
    assert summary["claims"]["housing_discrimination"]["support_by_kind"]["evidence"] == 1
