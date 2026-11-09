"""Bounded Legal IR proof routing with explicit unknown outcomes."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from integrations.ipfs_datasets.logic import route_bound_legal_ir_proof
from ipfs_datasets_py.logic.integration.reasoning.legal_ir_obligations import (
    LegalIRProofObligation,
)
from ipfs_datasets_py.logic.integration.reasoning.legal_ir_proof_router import (
    LegalIRProofRouter,
    ProofRoutingPolicy,
)


def _budgets():
    return {
        "deterministic": 0.4,
        "native_logic": 0.4,
        "smt_atp": 0.6,
        "lean_reconstruction": 0.6,
    }


def _obligation(**metadata):
    return LegalIRProofObligation(
        obligation_id="obligation-proof03",
        statement="element_holds(notice)",
        kind="modal_well_formedness",
        legal_ir_view="TDFOL.prover",
        logic_family="temporal",
        sample_id="sample-proof03",
        formula_id="f1",
        metadata=metadata,
    )


def _route(obligation=None, **kwargs):
    payload = {
        "obligation": obligation if obligation is not None else _obligation(),
        "goal_statement": "element_holds(notice)",
        "required_trust": "kernel",
        "total_timeout_seconds": 2.0,
        "stage_timeout_seconds": _budgets(),
    }
    payload.update(kwargs)
    return route_bound_legal_ir_proof(**payload)


def _blocking_router_source(router_pid: Path, descendant_pid: Path | None = None) -> str:
    """Test-only runner injection; the production API accepts no callbacks."""
    from integrations.ipfs_datasets import logic

    source = logic._PROOF_ROUTER_CALL_SOURCE
    marker = "  router = LegalIRProofRouter(pipeline, policy=policy)"
    assert source.count(marker) == 1
    fork = ""
    if descendant_pid is not None:
        # The original child audit forbids fork. Only this fixed inert test
        # callback enables it, so real manager adoption/reaping is exercised.
        source = source.replace(",'os.fork','os.forkpty'", "")
        fork = (
            "   child = os.fork()\n"
            "   if child == 0:\n"
            f"    open({str(descendant_pid)!r},'w').write(str(os.getpid()))\n"
            "    while True:time.sleep(.02)\n"
        )
    injected = (
        "  def blocking_runner(request):\n"
        f"   open({str(router_pid)!r},'w').write(str(os.getpid()))\n"
        + fork
        + "   while True:time.sleep(.02)\n"
        + "  router = LegalIRProofRouter(pipeline, policy=policy, route_runners={'deterministic_syntax':blocking_runner})"
    )
    return source.replace(marker, injected, 1)


def test_policy_uses_real_router_and_explicit_deadlines():
    routed = _route()
    policy = ProofRoutingPolicy(
        required_trust="kernel",
        total_timeout_seconds=2.0,
        stage_timeout_seconds={
            "deterministic": 0.4,
            "native_logic": 0.4,
            "smt_atp": 0.6,
            "lean_reconstruction": 0.6,
        },
        enabled_routes=("deterministic_syntax", "deterministic_graph", "deterministic_contract"),
    )
    assert routed["router"].endswith("LegalIRProofRouter")
    assert routed["policy"]["total_timeout_seconds"] == policy.total_timeout_seconds
    assert routed["policy"]["stage_timeout_seconds"] == policy.to_dict()["stage_timeout_seconds"]
    assert routed["policy"]["required_trust"] == "kernel"
    assert routed["policy"]["enabled_routes"]
    assert routed["empty_enabled_routes_enables_all"] is True
    assert routed["installs_disabled"]["IPFS_DATASETS_PY_LAZY_INSTALL_PROVERS"] == "0"
    assert routed["installs_disabled"]["IPFS_DATASETS_PY_AUTO_INSTALL_PROVERS"] == "0"
    assert LegalIRProofRouter.__name__ == "LegalIRProofRouter"
    assert routed["attempts"]
    assert {item["status"] for item in routed["attempts"]}
    assert routed["process"]["isolated_no_site_bootstrap_verified"] is True
    assert routed["process"]["request_transport"] == "sealed_parent_memfd"
    assert routed["process"]["sealed_request_transport_verified"] is True
    expected_flags = {key: 1 for key in ("no_site", "isolated", "ignore_environment", "dont_write_bytecode")}
    assert routed["process"]["manager_bootstrap_flags"] == expected_flags
    assert routed["process"]["worker_bootstrap_flags"] == expected_flags


def test_empty_enabled_routes_do_not_enable_install_prone_native_flogic():
    routed = _route(enabled_routes=())
    assert routed["rejected_empty_enabled_routes"] is True
    assert "native_flogic" not in routed["policy"]["enabled_routes"]
    flogic = next(item for item in routed["attempts"] if item["route"] == "native_flogic")
    assert flogic["status"] == "skipped"
    assert flogic["skip_reason"] == "route_disabled_by_policy"


def test_structural_deterministic_trust_is_not_substantive():
    sample = {
        "frame_logic": {
            "triples": [{"subject": "Employee", "predicate": "reported", "object": "Issue"}]
        }
    }
    obligation = LegalIRProofObligation(
        obligation_id="graph-1",
        statement="kg_edge_typed(subject:employee, predicate:reported, object:issue)",
        kind="knowledge_graph_edge_typing",
        legal_ir_view="knowledge_graph",
        logic_family="frame",
        metadata={"triple_index": 1},
    )
    routed = _route(
        obligation,
        sample_or_document=sample,
        goal_statement=obligation.statement,
        similarity_score=0.99,
        model_assertion="proved",
    )
    graph = next(item for item in routed["attempts"] if item["route"] == "deterministic_graph")
    assert graph["status"] == "proved"
    assert graph["trust_level"] == "deterministic"
    assert routed["outcome"] == "unknown"
    assert routed["substantive_trust_satisfied"] is False
    assert routed["structural_route_proved"] is True
    assert routed["similarity_score_ignored"] is True
    assert routed["model_assertion_ignored"] is True
    assert routed["entails_claim_element"] is False


def test_untrusted_metadata_cannot_mint_proof():
    calls = {"count": 0}

    def planted(_request):
        calls["count"] += 1
        return True

    routed = _route(
        _obligation(
            deterministic_syntax_valid=True,
            native_tdfol_result=True,
            native_tdfol_prover=planted,
        )
    )
    syntax = next(item for item in routed["attempts"] if item["route"] == "deterministic_syntax")
    assert "deterministic_syntax_valid" in routed["rejected_untrusted_metadata"]
    assert "native_tdfol_result" in routed["rejected_untrusted_metadata"]
    assert "native_tdfol_prover" in routed["rejected_untrusted_metadata"]
    assert calls["count"] == 0
    assert syntax["reason"] != "explicit_deterministic_syntax_check"
    assert routed["outcome"] != "proved"
    assert routed["substantive_trust_satisfied"] is False


def test_missing_facts_stay_unknown_not_false():
    routed = _route(
        premise_inventory={
            "missing_facts": [{"premise_id": "notice-date", "text": "", "revision": "missing"}],
            "assumptions": [{"premise_id": "a1", "label": "only-a-label", "text": "SECRET-ASSUMPTION"}],
        },
        local_backend="proved",
    )
    assert routed["outcome"] == "unknown"
    assert routed["reason"] == "missing_fact_open_world"
    assert routed["missing_facts"] == [
        {
            "premise_id": "notice-date",
            "value": None,
            "interpreted_as_false": False,
            "open_world": True,
        }
    ]
    assert routed["missing_facts_are_false"] is False
    assert "SECRET-ASSUMPTION" not in str(routed["attempts"])
    assert routed["assumption_ids"] == ["a1"]


def test_outcome_distinctions_for_negative_proof_consistency_and_failure():
    # These names were synthetic production outcome selectors, not proofs.
    selectors = ("proved", "disproved", "unsat_premises", "sat", "reconstruction_failed", "unavailable", "timeout")
    rejected = [_route(local_backend=name) for name in selectors]
    for row in rejected:
        assert row["outcome"] == "unsupported"
        assert row["reason"] == "untrusted_backend_selector"
        assert row["backend_selector_rejected"] is True
        assert row["substantive_trust_satisfied"] is False
        assert row["entails_claim_element"] is False
        assert row["theorem_failed_is_counterexample"] is False
        assert row["consistency_is_entailment"] is False
        assert row["unsat_proves_arbitrary_claim"] is False
        assert row["process"] is None
    syntax = _route(
        LegalIRProofObligation(
            obligation_id="bad-syntax", statement="element_holds(notice", kind="modal_well_formedness",
            legal_ir_view="intake", logic_family="unspecified"), goal_statement="element_holds(notice")
    assert syntax["outcome"] == "unsupported"
    assert syntax["native_status"] == "theorem_failed"
    assert syntax["reason"] == "theorem_failed_without_bound_negative_proof"
    assert syntax["outcome"] != "refuted"
    assert syntax["substantive_trust_satisfied"] is False
    assert syntax["process"]["actual_router_owned"] is True
    assert syntax["process"]["process_group_reaped"] is True


def routed_outcomes(*rows):
    return {row["outcome"] for row in rows}


def test_stale_versions_do_not_reuse_a_kernel_proof():
    routed = _route(
        local_backend="proved",
        execution_identity="identity-a",
        expected_execution_identity="identity-b",
        obligation_version="ob-1",
        premise_version="fact-1",
    )
    assert routed["outcome"] == "unknown"
    assert routed["reason"] == "stale_source_or_policy_version"
    assert routed["substantive_trust_satisfied"] is False
    assert routed["versions"]["policy_version"]
    assert routed["versions"]["obligation_version"] == "ob-1"


def test_managed_child_timeout_reaps_the_process_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from integrations.ipfs_datasets import logic

    router_pid = tmp_path / "router-pid"
    monkeypatch.setattr(logic, "_PROOF_ROUTER_CALL_SOURCE", _blocking_router_source(router_pid))
    started = time.monotonic()
    routed = _route(managed_state_directory=str(tmp_path / "timeout-state"), total_timeout_seconds=2.0)
    elapsed = time.monotonic() - started
    assert routed["outcome"] == "timeout"
    assert routed["process"]["timed_out"] is True
    assert routed["process"]["process_group_reaped"] is True
    assert elapsed < 3.0
    # This marker is written by a runner called inside the real native route().
    assert router_pid.exists()
    pid = int(router_pid.read_text())
    assert routed["process"]["router_pid"] == pid
    assert routed["process"]["actual_router_owned"] is True
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_managed_child_cancel_reaps_descendants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from integrations.ipfs_datasets import logic

    router_pid = tmp_path / "router-pid"
    grandchild = tmp_path / "grandchild-pid"
    monkeypatch.setattr(logic, "_PROOF_ROUTER_CALL_SOURCE", _blocking_router_source(router_pid, grandchild))
    cancel = threading.Event()

    def _cancel():
        deadline = time.monotonic() + 2.0
        while not grandchild.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        cancel.set()

    thread = threading.Thread(target=_cancel)
    thread.start()
    started = time.monotonic()
    routed = _route(managed_state_directory=str(tmp_path / "cancel-state"),
                    total_timeout_seconds=5.0, cancellation_event=cancel)
    elapsed = time.monotonic() - started
    thread.join(timeout=0.1)
    assert routed["outcome"] == "cancelled"
    assert routed["process"]["cancelled"] is True
    assert routed["process"]["process_group_reaped"] is True
    assert elapsed < 3.0
    assert grandchild.exists()
    child_pid = int(grandchild.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
    assert router_pid.exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int(router_pid.read_text()), 0)
    assert routed["process"]["router_tree_reaped"] is True
    assert not thread.is_alive()


def test_non_finite_deadline_is_rejected():
    with pytest.raises(ValueError):
        _route(total_timeout_seconds=float("inf"))


def test_arbitrary_preliminary_command_cannot_supply_proof_or_execute(tmp_path: Path):
    marker = tmp_path / "must-not-exist"
    routed = _route(managed_command=["/usr/bin/python3.12", "-c", f"open({str(marker)!r},'w').write('unsafe')"])
    assert routed["outcome"] == "unsupported"
    assert routed["reason"] == "untrusted_process_command"
    assert routed["managed_command_rejected"] is True
    assert routed["entails_claim_element"] is False
    assert routed["process"] is None
    assert not marker.exists()


def test_cancellation_before_routing_does_not_launch_an_actual_worker(tmp_path: Path):
    cancel = threading.Event()
    cancel.set()
    root = tmp_path / "never-created"
    routed = _route(cancellation_event=cancel, managed_state_directory=str(root))
    assert routed["outcome"] == "cancelled"
    assert routed["process"]["cancelled"] is True
    assert routed["process"]["process_group_reaped"] is True
    assert not root.exists()
    assert routed["substantive_trust_satisfied"] is False


def test_native_outcome_labels_without_checked_artifacts_do_not_mint_proof():
    from integrations.ipfs_datasets import logic

    common = dict(native_trust="kernel", native_reason="backend_counterexample", attempt_metadata=[],
        missing_facts=[], versions_match=True, similarity_score=1.0, model_assertion="proved",
        process={"process_group_reaped": True})
    # Fixture results are inputs to a private classification test, never a
    # selectable production prover or a claimed successful substantive proof.
    proved_label = logic._classify_route(native_status="proved", **common)
    failed_label = logic._classify_route(native_status="theorem_failed", **common)
    assert proved_label["outcome"] == "unknown"
    assert proved_label["substantive_trust_satisfied"] is False
    assert failed_label["outcome"] == "unsupported"
    assert failed_label["theorem_failed_is_counterexample"] is False
    assert proved_label["consistency_is_entailment"] is False
    assert failed_label["unsat_proves_arbitrary_claim"] is False


def test_real_router_exception_is_typed_and_does_not_expose_private_error(monkeypatch: pytest.MonkeyPatch):
    from integrations.ipfs_datasets import logic

    marker = "  router = LegalIRProofRouter(pipeline, policy=policy)"
    source = logic._PROOF_ROUTER_CALL_SOURCE
    assert source.count(marker) == 1
    source = source.replace(marker,
        "  def failing_runner(request):\n"
        "   raise ValueError('PRIVATE-ROUTER-ERROR-CONTENT')\n"
        "  router = LegalIRProofRouter(pipeline, policy=policy, route_runners={'deterministic_syntax':failing_runner})", 1)
    monkeypatch.setattr(logic, "_PROOF_ROUTER_CALL_SOURCE", source)
    routed = _route()
    syntax = next(row for row in routed["attempts"] if row["route"] == "deterministic_syntax")
    assert syntax["status"] == "error"
    assert syntax["reason"] == "route_execution_failed"
    assert "PRIVATE-ROUTER-ERROR-CONTENT" not in str(routed)
    assert routed["entails_claim_element"] is False
    assert routed["process"]["actual_router_owned"] is True
    assert routed["process"]["process_group_reaped"] is True


@pytest.mark.parametrize("stop", ["timeout", "cancelled"])
def test_stalled_request_reader_is_deadline_bounded_before_input_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop: str,
):
    import json
    import signal

    from integrations.ipfs_datasets import logic

    observed = tmp_path / "before-request-read.json"
    source = logic._PROOF_ROUTER_CALL_SOURCE
    marker = "request = json.loads(sys.stdin.buffer.read(1048577))"
    assert source.count(marker) == 1
    # This fixed inert child stops after one byte. The request exceeds pipe
    # capacity, so the manager must cancel/expire while still pumping stdin.
    stall = (
        "state = ctypes.c_int()\n"
        "assert ctypes.CDLL(None).prctl(2,ctypes.byref(state),0,0,0) == 0\n"
        "assert len(os.read(sys.stdin.fileno(),1)) == 1\n"
        f"with open({str(observed)!r},'w') as stream:\n"
        " json.dump({'pid':os.getpid(),'parent':os.getppid(),'manager':manager,'pdeathsig':state.value},stream)\n"
        "while True:time.sleep(.02)\n"
    )
    monkeypatch.setattr(logic, "_PROOF_ROUTER_CALL_SOURCE", source.replace(marker, stall, 1))
    cancel = threading.Event()
    thread = None
    if stop == "cancelled":
        def cancel_after_reader_starts():
            deadline = time.monotonic() + 2.0
            while not observed.exists() and time.monotonic() < deadline:
                time.sleep(.005)
            cancel.set()
        thread = threading.Thread(target=cancel_after_reader_starts)
        thread.start()
    started = time.monotonic()
    routed = _route(sample_or_document={"metadata": {"padding": "x" * 262144}},
        managed_state_directory=str(tmp_path / "owned"), total_timeout_seconds=2.0,
        cancellation_event=cancel)
    elapsed = time.monotonic() - started
    if thread is not None:
        thread.join(timeout=.1)
        assert not thread.is_alive()
    assert routed["outcome"] == stop
    assert routed["process"]["timed_out" if stop == "timeout" else "cancelled"] is True
    assert elapsed < 3.0
    assert observed.exists()
    state = json.loads(observed.read_text())
    assert state["pdeathsig"] == signal.SIGKILL
    assert state["parent"] == state["manager"] == routed["process"]["pid"]
    assert state["pid"] == routed["process"]["router_pid"]
    assert routed["process"]["stdin_complete"] is False
    assert routed["process"]["isolated_no_site_bootstrap_verified"] is True
    assert routed["process"]["request_transport"] == "sealed_parent_memfd"
    assert routed["process"]["sealed_request_transport_verified"] is True
    expected_flags = {key: 1 for key in ("no_site", "isolated", "ignore_environment", "dont_write_bytecode")}
    assert routed["process"]["manager_bootstrap_flags"] == expected_flags
    assert routed["process"]["worker_bootstrap_flags"] == expected_flags
    assert 0 < routed["process"]["input_bytes_sent"] < routed["process"]["input_bytes_total"]
    assert routed["process"]["input_bytes_total"] > 262144
    identity = routed["process"]["router_child_identity"]
    assert identity["pid"] == state["pid"]
    assert identity["start_ticks"] > 0
    assert identity["manager_pid"] == state["manager"]
    assert routed["process"]["router_tree_reaped"] is True
    assert routed["process"]["process_group_reaped"] is True
    assert routed["substantive_trust_satisfied"] is False
    assert routed["entails_claim_element"] is False
    with pytest.raises(ProcessLookupError):
        os.kill(state["pid"], 0)
    assert list((tmp_path / "owned").iterdir()) == []


def _element_identity(**overrides):
    from integrations.ipfs_datasets.logic import proof_cache_identity

    payload = {
        "claim_id": "retaliation",
        "element_id": "causation",
        "factual_revisions": [{"fact_id": "fact-1", "revision": "rev-1"}],
        "legal_source": {
            "source_id": "statute-1",
            "source_version": "law-v1",
            "legal_context_version": "law-v1",
            "law_as_of": "2024-01-01",
            "rules": [{"rule_id": "rule-1", "version": "law-v1", "superseded": False}],
        },
        "compiler": {"compiler_config_cid": "compiler-a", "schema": "schema-a", "execution_identity": "fixture-execution"},
        "compiler_config": {"max_obligations": 8},
        "proof_policy": {"required_trust": "kernel", "total_timeout_seconds": 1.5},
        "chronology": {"issues": []},
    }
    payload.update(overrides)
    return proof_cache_identity(**payload)


def test_proof_cache_identity_covers_fact_law_compiler_and_policy():
    from integrations.ipfs_datasets.logic import reset_satisfied_element_proof_cache

    reset_satisfied_element_proof_cache()
    base = _element_identity()
    components = base["components"]
    assert components["factual_revisions"][0]["revision"] == "rev-1"
    assert components["legal_source"]["law_as_of"] == "2024-01-01"
    assert components["legal_source"]["source_version"] == "law-v1"
    assert components["compiler"]["identities"]["compiler_config_cid"] == "compiler-a"
    assert components["compiler"]["schema_version"]
    assert components["proof_policy"]["policy"]["required_trust"] == "kernel"
    assert components["proof_policy"]["cache_policy"]
    variants = [
        _element_identity(factual_revisions=[{"fact_id": "fact-1", "revision": "rev-2"}]),
        _element_identity(legal_source={
            "source_id": "statute-1", "source_version": "law-v1", "legal_context_version": "law-v1",
            "law_as_of": "2025-06-01", "rules": [{"rule_id": "rule-1", "version": "law-v1", "superseded": False}],
        }),
        _element_identity(legal_source={
            "source_id": "statute-1", "source_version": "law-v2", "legal_context_version": "law-v2",
            "law_as_of": "2024-01-01", "rules": [{"rule_id": "rule-1", "version": "law-v2", "superseded": True}],
        }),
        _element_identity(compiler={"compiler_config_cid": "compiler-b", "schema": "schema-b"}),
        _element_identity(proof_policy={"required_trust": "kernel", "total_timeout_seconds": 2.5}),
    ]
    assert len({base["cache_identity"], *(item["cache_identity"] for item in variants)}) == 6


def test_corrected_facts_law_date_and_superseded_rules_do_not_reuse_satisfied_results():
    from integrations.ipfs_datasets.logic import (
        lookup_satisfied_element_proof,
        replay_satisfied_element_proof,
        reset_satisfied_element_proof_cache,
    )

    reset_satisfied_element_proof_cache()
    calls = {"count": 0}

    def provider():
        calls["count"] += 1
        from integrations.ipfs_datasets.logic import route_bound_legal_ir_proof
        return route_bound_legal_ir_proof(local_backend='proved',
            execution_identity='fixture-execution', expected_execution_identity='fixture-execution')

    original = _element_identity()
    first = replay_satisfied_element_proof(original, provider=provider)
    assert first["satisfied"] is False
    assert first["substantive_trust_satisfied"] is False
    assert first["result"]["reason"] == "untrusted_backend_selector"
    assert first["provider_called"] is True
    assert calls["count"] == 1
    again = replay_satisfied_element_proof(original, provider=provider)
    assert again["reused"] is True
    assert again["provider_called"] is False
    assert again["result"] == first["result"]
    assert calls["count"] == 1

    corrected = _element_identity(factual_revisions=[{"fact_id": "fact-1", "revision": "rev-2"}])
    corrected_result = replay_satisfied_element_proof(corrected, provider=provider)
    assert calls["count"] == 2 and corrected_result["reused"] is False
    assert corrected_result["cache_identity"] != first["cache_identity"]
    assert lookup_satisfied_element_proof(original) is None
    assert lookup_satisfied_element_proof(corrected) is None

    changed_date = _element_identity(legal_source={
        "source_id": "statute-1", "source_version": "law-v1", "legal_context_version": "law-v1",
        "law_as_of": "2026-01-01", "rules": [{"rule_id": "rule-1", "version": "law-v1", "superseded": False}],
    })
    dated = replay_satisfied_element_proof(changed_date, provider=provider)
    assert calls["count"] == 3 and dated["satisfied"] is False
    assert lookup_satisfied_element_proof(original) is None

    superseded = _element_identity(legal_source={
        "source_id": "statute-1", "source_version": "law-v1", "legal_context_version": "law-v1",
        "law_as_of": "2024-01-01", "rules": [{"rule_id": "rule-1", "version": "law-v1", "superseded": True}],
    })
    blocked = replay_satisfied_element_proof(superseded, provider=provider)
    assert blocked["satisfied"] is False
    assert blocked["reason"] == "superseded_rule"
    assert calls["count"] == 4 and blocked["provider_called"] is True
    assert lookup_satisfied_element_proof(superseded) is None
    assert lookup_satisfied_element_proof(original) is None
    replay_satisfied_element_proof(superseded, provider=provider)
    assert calls["count"] == 4


def test_contradictory_dates_and_relative_chronology_stay_uncertain():
    from complaint_phases.dependency_graph import DependencyGraph, DependencyGraphBuilder, DependencyNode, NodeType
    from integrations.ipfs_datasets.logic import replay_satisfied_element_proof, reset_satisfied_element_proof_cache

    reset_satisfied_element_proof_cache()

    def provider():
        raise AssertionError("live provider called")

    contradictory = _element_identity(chronology={"contradictory_dates": True})
    first = replay_satisfied_element_proof(contradictory, provider=provider)
    second = replay_satisfied_element_proof(contradictory, provider=provider)
    assert first["satisfied"] is False
    assert first["status"] == "uncertain"
    assert first["provider_called"] is False
    assert first["recommended_follow_ups"][0]["issue_type"] == "contradictory_dates"
    assert first["recommended_follow_ups"][0]["follow_up_target"] == "document_request"
    assert second["reused"] is True
    assert second["provider_called"] is False
    assert second["result"] == first["result"]

    relative = _element_identity(chronology={"issues": ["relative_only_ordering"]})
    relative_result = replay_satisfied_element_proof(relative, provider=provider)
    assert relative_result["status"] == "uncertain"
    assert relative_result["reason"] == "relative_only_chronology"
    assert relative_result["recommended_follow_ups"][0]["target_kind"] == "absolute_chronology"
    assert relative_result["provider_called"] is False

    graph = DependencyGraph()
    node = DependencyNode(
        id="element-1",
        node_type=NodeType.LEGAL_ELEMENT,
        name="causation",
        satisfied=True,
        attributes={
            "dependency_class": "legally_sourced",
            "date_sensitive": True,
            "satisfaction_state": "satisfied",
            "dependency_scope": {"rule_id": "rule-1", "fact_ids": ["fact-1"], "date_sensitive": True},
        },
    )
    graph.add_node(node)
    builder = DependencyGraphBuilder()
    bound = builder.apply_element_proof_cache(graph, "element-1", first)
    assert bound["satisfaction_state"] == "uncertain"
    assert bound["proof_cache_reusable"] is False
    assert bound["recommended_follow_ups"][0]["issue_type"] == "contradictory_dates"
    report = builder.refresh_affected_dependencies(graph, {"chronology_issue": "relative_only_ordering"})
    assert "element-1" in report["affected_node_ids"]
    assert graph.nodes["element-1"].attributes["satisfaction_state"] == "uncertain"
    assert graph.nodes["element-1"].attributes["recommended_follow_ups"][0]["issue_type"] == "relative_only_ordering"
    assert graph.nodes["element-1"].satisfied is False


def test_unchanged_proof_replay_is_deterministic_without_a_live_provider():
    from integrations.ipfs_datasets.logic import replay_satisfied_element_proof, reset_satisfied_element_proof_cache

    reset_satisfied_element_proof_cache()
    calls = {"count": 0}

    def provider():
        calls["count"] += 1
        from integrations.ipfs_datasets.logic import route_bound_legal_ir_proof
        return route_bound_legal_ir_proof(local_backend='proved',
            execution_identity='fixture-execution', expected_execution_identity='fixture-execution')

    identity = _element_identity()
    first = replay_satisfied_element_proof(identity, provider=provider)
    second = replay_satisfied_element_proof(identity, provider=provider)
    assert calls["count"] == 1
    assert second["provider_called"] is False
    assert second["reused"] is True
    assert second["result"] == first["result"]
    assert second["cache_identity"] == first["cache_identity"]


def test_large_request_is_fully_pumped_into_the_real_router(tmp_path: Path):
    routed = _route(sample_or_document={"metadata": {"padding": "x" * 262144}},
        managed_state_directory=str(tmp_path / "owned"))
    assert routed["process"]["stdin_complete"] is True
    assert routed["process"]["isolated_no_site_bootstrap_verified"] is True
    assert routed["process"]["request_transport"] == "sealed_parent_memfd"
    assert routed["process"]["sealed_request_transport_verified"] is True
    expected_flags = {key: 1 for key in ("no_site", "isolated", "ignore_environment", "dont_write_bytecode")}
    assert routed["process"]["manager_bootstrap_flags"] == expected_flags
    assert routed["process"]["worker_bootstrap_flags"] == expected_flags
    assert routed["process"]["input_bytes_sent"] == routed["process"]["input_bytes_total"]
    assert routed["process"]["input_bytes_total"] > 262144
    assert routed["router"].endswith("LegalIRProofRouter")
    assert routed["attempts"]
    assert routed["runtime_sources"]
    assert routed["process"]["router_tree_reaped"] is True
    assert routed["process"]["process_group_reaped"] is True
    assert routed["entails_claim_element"] is False
    assert list((tmp_path / "owned").iterdir()) == []


@pytest.mark.parametrize('mutate', [
    lambda x: x['components']['legal_source'].update(law_as_of='2026-01-01'),
    lambda x: x['components'].update(chronology={'contradictory_dates': True}),
    lambda x: x['components']['compiler'].update(current_identities={'forged': True}),
])
def test_modified_cache_components_cannot_reuse_old_key_or_call_provider(mutate):
    from copy import deepcopy
    from integrations.ipfs_datasets.logic import replay_satisfied_element_proof, reset_satisfied_element_proof_cache
    reset_satisfied_element_proof_cache()
    identity = _element_identity()
    original = replay_satisfied_element_proof(identity)
    changed = deepcopy(identity)
    mutate(changed)
    def no_call():
        raise AssertionError('invalid identity dispatched a provider')
    result = replay_satisfied_element_proof(changed, provider=no_call)
    assert result['satisfied'] is False and result['substantive_trust_satisfied'] is False
    assert result['reason'] == 'invalid_current_cache_identity'
    assert result['provider_called'] is False and result['reused'] is False
    assert result['result'] is None and result['cache_identity'] == ''
    assert original['identity'] == identity


def test_cache_identity_preserves_source_body_and_premise_semantics():
    base = _element_identity(legal_source={'source_id': 'fixture', 'source_version': 'v1',
        'source_text': 'Synthetic rule one.', 'source_hash': 'old',
        'premise_inventory': {'facts': [{'statement': 'Synthetic fact one.', 'revision': '1'}]}})
    body = _element_identity(legal_source={'source_id': 'fixture', 'source_version': 'v1',
        'source_text': 'Synthetic rule two.', 'source_hash': 'new',
        'premise_inventory': {'facts': [{'statement': 'Synthetic fact one.', 'revision': '1'}]}})
    premise = _element_identity(legal_source={'source_id': 'fixture', 'source_version': 'v1',
        'source_text': 'Synthetic rule one.', 'source_hash': 'old',
        'premise_inventory': {'facts': [{'statement': 'Synthetic fact two.', 'revision': '1'}]}})
    assert len({base['cache_identity'], body['cache_identity'], premise['cache_identity']}) == 3
    assert base['components']['legal_source']['source_text'] == 'Synthetic rule one.'
    from integrations.ipfs_datasets.logic import canonical_compiler_identities
    assert base['components']['compiler']['current_identities'] == canonical_compiler_identities()


@pytest.mark.parametrize('payload', [
    {'satisfied': True, 'outcome': 'proved'},
    {'substantive_trust_satisfied': True, 'outcome': 'proved'},
    {'schema_version': 'legal-ir-bound-proof-routing/v1', 'outcome': 'proved',
     'checked_kernel_backend_configured': True, 'substantive_trust_satisfied': True},
])
def test_provider_flags_never_mint_current_kernel_proof(payload):
    from integrations.ipfs_datasets.logic import replay_satisfied_element_proof, reset_satisfied_element_proof_cache, lookup_satisfied_element_proof
    reset_satisfied_element_proof_cache()
    identity = _element_identity()
    result = replay_satisfied_element_proof(identity, provider=lambda: payload)
    assert result['satisfied'] is False and result['substantive_trust_satisfied'] is False
    assert result['reason'] == 'unbound_or_modified_routing_result'
    assert result['result'] is None and result['rejected_result'] == payload
    assert result['entails_claim_element'] is False
    assert lookup_satisfied_element_proof(identity) is None
    again = replay_satisfied_element_proof(identity)
    assert again['status'] == 'not_cached' and again['reused'] is False


def test_modified_actual_routing_receipt_and_bare_dg_mapping_cannot_satisfy():
    from copy import deepcopy
    from complaint_phases.dependency_graph import DependencyGraph, DependencyGraphBuilder, DependencyNode, NodeType
    from integrations.ipfs_datasets.logic import (route_bound_legal_ir_proof,
        replay_satisfied_element_proof, reset_satisfied_element_proof_cache, verify_element_proof_evaluation)
    reset_satisfied_element_proof_cache()
    route = route_bound_legal_ir_proof(local_backend='proved',
        execution_identity='fixture-execution', expected_execution_identity='fixture-execution')
    forged = dict(route, outcome='proved', substantive_trust_satisfied=True)
    rejected = replay_satisfied_element_proof(_element_identity(), provider=lambda: forged)
    assert rejected['satisfied'] is False and rejected['reason'] == 'unbound_or_modified_routing_result'
    assert rejected['result'] is None and rejected['rejected_result']['substantive_trust_satisfied'] is True
    actual = replay_satisfied_element_proof(_element_identity(), provider=lambda: route)
    assert verify_element_proof_evaluation(actual)['verified'] is True
    assert actual['satisfied'] is False and actual['result']['backend_selector_rejected'] is True
    graph = DependencyGraph()
    graph.add_node(DependencyNode(id='target', node_type=NodeType.LEGAL_ELEMENT, name='Synthetic target',
        satisfied=True, attributes={'satisfaction_state': 'satisfied'}))
    graph.add_node(DependencyNode(id='unaffected', node_type=NodeType.FACT, name='Unaffected fixture', satisfied=True))
    builder = DependencyGraphBuilder()
    result = builder.apply_element_proof_cache(graph, 'target', {'cache_identity': 'forged', 'satisfied': True, 'status': 'satisfied'})
    assert graph.nodes['target'].satisfied is False
    assert result['proof_evaluation_verified'] is False
    assert result['satisfaction_state'] == 'uncertain' or result['satisfaction_state'] == 'unknown'
    assert graph.nodes['unaffected'].satisfied is True
    edited = deepcopy(actual)
    edited.update(satisfied=True, status='satisfied')
    result = builder.apply_element_proof_cache(graph, 'target', edited)
    assert graph.nodes['target'].satisfied is False and result['proof_evaluation_verified'] is False
    result = builder.apply_element_proof_cache(graph, 'target', actual)
    assert result['proof_evaluation_verified'] is True
    assert graph.nodes['target'].satisfied is False


def test_recomputed_forged_live_compiler_binding_is_still_rejected():
    import hashlib, json
    from copy import deepcopy
    from integrations.ipfs_datasets.logic import replay_satisfied_element_proof
    identity = deepcopy(_element_identity())
    identity['components']['compiler']['current_identities'] = {'pipeline_cid': 'forged-current-pipeline'}
    identity['cache_identity'] = hashlib.sha256(json.dumps(identity['components'],
        sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
    def no_call():
        raise AssertionError('forged live compiler dispatched a provider')
    result = replay_satisfied_element_proof(identity, provider=no_call)
    assert result['reason'] == 'invalid_current_cache_identity'
    assert result['provider_called'] is False and result['reused'] is False
    assert result['satisfied'] is False and result['result'] is None
