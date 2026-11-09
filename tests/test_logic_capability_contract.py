from __future__ import annotations

import pytest

from integrations.ipfs_datasets import logic
from lib.formal_logic import (
    FormalLogicCapability,
    FormalLogicDegradedError,
    FormalLogicOperation,
    FormalLogicUnavailableError,
    LogicCapabilityState,
    capability_state_from_payload,
)


def test_capability_state_exposes_typed_decisions_and_stable_serialization() -> None:
    capability = FormalLogicCapability(
        operation=FormalLogicOperation.CHECK_CONTRADICTIONS,
        state=LogicCapabilityState.DEGRADED,
        provider="test-provider",
        module_path="test.logic",
        reason="structural validation only",
        details={"mode": "fallback"},
    )

    assert capability.available is True
    assert capability.degraded is True
    assert capability.implemented is False
    assert capability.as_dict() == {
        "operation": "check_contradictions",
        "status": "degraded",
        "available": True,
        "degraded": True,
        "implemented": False,
        "provider": "test-provider",
        "module_path": "test.logic",
        "reason": "structural validation only",
        "details": {"mode": "fallback"},
    }

    with pytest.raises(FormalLogicDegradedError) as raised:
        capability.require_implemented()
    assert raised.value.operation is FormalLogicOperation.CHECK_CONTRADICTIONS
    assert raised.value.state is LogicCapabilityState.DEGRADED
    assert raised.value.as_dict() == {
        "error": "formal_logic_degraded",
        "operation": "check_contradictions",
        "required": "an implemented capability",
        "status": "degraded",
        "reason": "structural validation only",
        "capability": capability.as_dict(),
    }


def test_unavailable_capability_fails_predictably_without_string_branching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logic, "_fol_module", None)
    monkeypatch.setattr(logic, "_fol_error", RuntimeError("FOL extra is missing"))

    capability = logic.get_logic_capability(FormalLogicOperation.TEXT_TO_FOL)

    assert capability.state is LogicCapabilityState.UNAVAILABLE
    assert capability.available is False
    with pytest.raises(FormalLogicUnavailableError, match="FOL extra is missing"):
        logic.require_logic_capability(FormalLogicOperation.TEXT_TO_FOL)
    with pytest.raises(FormalLogicUnavailableError):
        logic.text_to_fol("A tenant has notice.", require_implemented=True)

    diagnostic = logic.text_to_fol("A tenant has notice.")
    assert diagnostic["capability"]["status"] == "unavailable"
    assert diagnostic["metadata"]["capability_status"] == "unavailable"
    assert diagnostic["metadata"]["capability_available"] is False
    assert diagnostic["metadata"]["implementation_status"] == "unavailable"


def test_adapter_report_distinguishes_all_three_capability_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logic, "LOGIC_AVAILABLE", True)
    monkeypatch.setattr(logic, "_fol_module", None)
    monkeypatch.setattr(logic, "_fol_error", RuntimeError("missing FOL"))
    monkeypatch.setattr(logic, "_deontic_module", object())
    monkeypatch.setattr(logic, "_tdfol_module", object())
    monkeypatch.setattr(logic, "LOCAL_FORMAL_LOGIC_AVAILABLE", True)

    report = logic.get_logic_capability_report()

    assert "text_to_fol" in report["unavailable"]
    assert "legal_text_to_deontic" in report["degraded"]
    assert "run_hybrid_reasoning" in report["implemented"]
    assert report["state_counts"] == {
        "unavailable": 1,
        "degraded": 3,
        "implemented": 1,
    }
    assert set(report["capabilities"]) == {
        operation.value for operation in FormalLogicOperation
    }


def test_degraded_gate_can_be_explicitly_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logic, "LOGIC_AVAILABLE", True)
    monkeypatch.setattr(logic, "_tdfol_module", object())

    capability = logic.require_logic_capability(
        FormalLogicOperation.CHECK_CONTRADICTIONS,
        allow_degraded=True,
    )

    assert capability.state is LogicCapabilityState.DEGRADED
    with pytest.raises(FormalLogicDegradedError):
        logic.require_logic_capability(FormalLogicOperation.CHECK_CONTRADICTIONS)


def test_persisted_legacy_states_are_normalized_at_contract_boundary() -> None:
    assert capability_state_from_payload(
        {"backend_available": True, "implementation_status": "not_implemented"}
    ) is LogicCapabilityState.DEGRADED
    assert capability_state_from_payload(
        {"backend_available": False, "implementation_status": "not_implemented"}
    ) is LogicCapabilityState.UNAVAILABLE
    assert capability_state_from_payload(
        {
            "status": "diagnostic",
            "metadata": {
                "backend_available": False,
                "implementation_status": "not_implemented",
            },
        }
    ) is LogicCapabilityState.UNAVAILABLE
    assert capability_state_from_payload(
        {"capability": {"status": "implemented", "implemented": True}}
    ) is LogicCapabilityState.IMPLEMENTED


def test_complete_adapter_payload_resolves_nested_capability_contract() -> None:
    payload = {
        "status": "success",
        "metadata": {
            "implementation_status": "available",
            "backend_available": True,
            "capability": {
                "status": "degraded",
                "available": True,
                "degraded": True,
                "implemented": False,
            },
        },
    }

    assert capability_state_from_payload(payload) is LogicCapabilityState.DEGRADED


def test_conflicting_capability_signals_are_resolved_conservatively() -> None:
    assert capability_state_from_payload(
        {
            "capability": {
                "status": "implemented",
                "available": False,
                "implemented": True,
            }
        }
    ) is LogicCapabilityState.UNAVAILABLE
