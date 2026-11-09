"""Gate qualified model outputs as engineering candidates.

Cases use synthetic private fixtures and the current compact-content and
predicate-training identity owners. No test is skipped. Mandatory checks do
not train, restore, download, or fit a model.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from integrations.ipfs_datasets import definition_evidence, logic
from integrations.ipfs_datasets.loader import import_module_optional
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = []

_PERSISTENT_OWNER = (
    "ipfs_datasets_py.logic.formalization.autoencoder.legal_compact_content_persistent_v1"
)
_PREDICATE_OWNER = (
    "ipfs_datasets_py.logic.formalization.autoencoder.legal_compact_content_predicate_training_v1"
)
_REFUSED_CALLS = {
    "train_compact_content_persistent_v1",
    "restore",
    "pack",
    "create",
    "training_row",
    "build_compact_content_persistent_v1",
}


def _requirement():
    return {
        "requirement_id": "req-notice",
        "admitted_legal_text": "A covered employer must keep a written record.",
        "proof": {"status": "unverified", "body": "prior-proof"},
    }


def _checkpoint(case_id: str) -> dict[str, str]:
    return {"probe": "synthetic-mgnd-26", "case_id": case_id}


def _pins(case_id: str, raw: bytes):
    predicate, predicate_error = import_module_optional(_PREDICATE_OWNER)
    persistent, persistent_error = import_module_optional(_PERSISTENT_OWNER)
    checkpoint = _checkpoint(case_id)
    persistent_checkpoint = {"probe": "synthetic-mgnd-26-persistent", "case_id": case_id}
    policy_sha = None
    checkpoint_sha = None
    persistent_sha = None
    if predicate is not None and predicate_error is None:
        policy = predicate.policy("full537")
        policy_sha = predicate.policy_sha256(policy)
        checkpoint_sha = predicate.checkpoint_sha256(checkpoint)
    if persistent is not None and persistent_error is None:
        persistent_sha = persistent.compact_content_persistent_sha256(persistent_checkpoint)
    return {
        "predicate_error": predicate_error,
        "persistent_error": persistent_error,
        "checkpoint": checkpoint,
        "persistent_checkpoint": persistent_checkpoint,
        "policy_sha": policy_sha,
        "checkpoint_sha": checkpoint_sha,
        "persistent_sha": persistent_sha,
        "raw_sha": hashlib.sha256(raw).hexdigest(),
        "raw": raw,
    }


def _described(case_id: str, **overrides):
    raw = overrides.pop("raw", f"synthetic-private:{case_id}".encode("utf-8"))
    pins = _pins(case_id, raw)
    payload = {
        "source_space": f"synthetic-private:{case_id}",
        "conditioning_mode": "every_step",
        "objective_kind": "full537",
        "expected_policy_sha256": pins["policy_sha"],
        "expected_checkpoint_sha256": pins["checkpoint_sha"],
        "expected_persistent_checkpoint_sha256": pins["persistent_sha"],
        "expected_raw_sha256": pins["raw_sha"],
        "checkpoint": pins["checkpoint"],
        "persistent_checkpoint": pins["persistent_checkpoint"],
        "checkpoint_raw": pins["raw"],
    }
    payload.update(overrides)
    described = definition_evidence.describe_qualified_model_candidate(**payload)
    return described, pins


def test_meaningful_cases_are_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id for case in cases)


def test_exact_identity_pins_are_engineering_evidence(tmp_path: Path):
    case = meaningful_cases()[0]
    raw_path = tmp_path / "synthetic-checkpoint.txt"
    raw = f"synthetic-private:{case.case_id}".encode("utf-8")
    raw_path.write_bytes(raw)
    described, pins = _described(case.case_id, raw=raw_path.read_bytes())
    assert described["schema"] == definition_evidence.QUALIFIED_MODEL_CANDIDATE_SCHEMA
    assert described["skipped"] is False
    assert described["eligible_as_authority"] is False
    assert described["legally_eligible"] is False
    assert described["selects_governing_law"] is False
    assert described["satisfies_definition_review"] is False
    assert described["proves_element"] is False
    assert described["model_executed"] is False
    assert described["live_owner_verified"] is False
    assert described["effects"] == {name: False for name in definition_evidence._REFUSED_MODEL_EFFECTS}
    assert described["requested"]["source_space"] == f"synthetic-private:{case.case_id}"
    assert described["requested"]["conditioning_mode"] == "every_step"
    assert described["requested"]["objective_kind"] == "full537"
    persistent = described["persistent"]
    predicate = described["predicate"]
    assert persistent["qualified_name_load"].endswith(".load_compact_content_persistent_v1")
    assert persistent["qualified_name_score"].endswith(".score_compact_content_persistent_v1")
    assert persistent["load_called"] is False
    assert persistent["score_called"] is False
    assert persistent["restore_called"] is False
    assert predicate["qualified_name_inspect"].endswith(".inspect")
    assert predicate["qualified_name_checkpoint"].endswith(".checkpoint_sha256")
    assert predicate["inspect_called"] is False
    assert predicate["training_executed"] is False
    assert predicate["optimizer_constructed"] is False
    if pins["predicate_error"] is None and pins["policy_sha"]:
        assert predicate["observed"]["policy_sha256"] == pins["policy_sha"]
        assert predicate["observed"]["checkpoint_sha256"] == pins["checkpoint_sha"]
        assert predicate["requested"]["expected_policy_sha256"] == pins["policy_sha"]
        assert predicate["requested"]["expected_checkpoint_sha256"] == pins["checkpoint_sha"]
        assert predicate["engineering_evidence"] is True
        assert predicate["training_preparation_is_engineering_evidence"] is True
        assert predicate["status"] == "ineligible"
        assert predicate["reason"] == "inspect_not_executed"
    else:
        assert predicate["status"] == "unavailable"
    if pins["persistent_error"] is None and pins["persistent_sha"]:
        assert persistent["observed"]["checkpoint_sha256"] == pins["persistent_sha"]
        assert persistent["observed"]["raw_sha256"] == pins["raw_sha"]
        assert persistent["requested"]["source_space"] == f"synthetic-private:{case.case_id}"
        assert persistent["requested"]["conditioning_mode"] == "every_step"
        assert persistent["load_called"] is False
        if persistent["runtime_available"]:
            assert persistent["status"] == "ineligible"
            assert persistent["reason"] == "model_output_absent"
        else:
            assert persistent["status"] == "unavailable"
            assert persistent["reason"] == "runtime_unavailable"
    else:
        assert persistent["status"] == "unavailable"
    assert described["status"] in {"unavailable", "ineligible"}


def test_private_cases_keep_distinct_source_space_and_checkpoint_identity(tmp_path: Path):
    seen = set()
    for case in meaningful_cases():
        raw = f"synthetic-private:{case.case_id}".encode("utf-8")
        (tmp_path / f"{case.case_id}.txt").write_bytes(raw)
        described, pins = _described(case.case_id, raw=raw)
        assert described["requested"]["source_space"] == f"synthetic-private:{case.case_id}"
        assert described["skipped"] is False
        assert described["status"] in {"unavailable", "ineligible"}
        if pins["checkpoint_sha"]:
            assert described["predicate"]["observed"]["checkpoint_sha256"] == pins["checkpoint_sha"]
            seen.add(pins["checkpoint_sha"])
    if seen:
        assert len(seen) == len(meaningful_cases())


def test_incompatible_metadata_is_ineligible_without_owner_execution():
    described, _pins = _described(
        "case-incompatible",
        conditioning_mode="sideways",
        objective_kind="not-an-objective",
        expected_policy_sha256="0" * 64,
        expected_checkpoint_sha256="1" * 64,
        expected_persistent_checkpoint_sha256="2" * 64,
        expected_raw_sha256="3" * 64,
    )
    assert described["status"] in {"unavailable", "ineligible"}
    assert described["eligible_as_authority"] is False
    assert described["persistent"]["load_called"] is False
    assert described["persistent"]["score_called"] is False
    assert described["predicate"]["inspect_called"] is False
    assert described["predicate"]["training_executed"] is False
    if described["persistent"]["status"] != "unavailable":
        assert described["persistent"]["status"] == "ineligible"
        assert described["persistent"]["metadata_exact"] is False
    if described["predicate"]["status"] != "unavailable":
        assert described["predicate"]["status"] == "ineligible"
        assert described["predicate"]["metadata_exact"] is False
        assert described["predicate"]["engineering_evidence"] is False


def test_missing_owner_is_asserted_unavailable(monkeypatch):
    def _missing(name: str):
        return None, definition_evidence._diagnostic(ModuleNotFoundError(name)) or {
            "error_type": "ModuleNotFoundError",
            "message": name,
        }

    monkeypatch.setattr(definition_evidence, "import_module_optional", _missing)
    described = definition_evidence.describe_qualified_model_candidate(
        source_space="synthetic-private:missing",
        conditioning_mode="every_step",
        objective_kind="full537",
        expected_policy_sha256="a" * 64,
        expected_checkpoint_sha256="b" * 64,
        expected_raw_sha256="c" * 64,
        checkpoint={"probe": "missing"},
        checkpoint_raw=b"missing",
    )
    assert described["status"] == "unavailable"
    assert described["eligible"] is False
    assert described["persistent"]["status"] == "unavailable"
    assert described["predicate"]["status"] == "unavailable"
    assert described["persistent"]["load_called"] is False
    assert described["predicate"]["checkpoint_called"] is False
    assert described["skipped"] is False


def test_matching_shaped_output_is_candidate_not_authority():
    case = meaningful_cases()[0]
    described, pins = _described(case.case_id)
    if described["persistent"]["status"] == "unavailable" or described["predicate"]["status"] == "unavailable":
        assert described["status"] == "unavailable"
        assert described["proves_element"] is False
        return
    observed_score = {
        "schema": "legal-compact-content-persistent-score/v1",
        "conditioning_mode": "every_step",
        "source_space": f"synthetic-private:{case.case_id}",
        "checkpoint_sha256": pins["persistent_sha"],
        "authority": {"proof_authority": True, "governing_use_verified": True},
        "training_executed": True,
    }
    observed_inspect = {
        "schema": "legal-compact-predicate-training-checkpoint/v1",
        "checkpoint_sha256": pins["checkpoint_sha"],
        "objective_policy_sha256": pins["policy_sha"],
        "authority": {"statutory_accuracy": True},
    }
    gated_input, _pins = _described(
        case.case_id,
        observed_score=observed_score,
        observed_inspect=observed_inspect,
    )
    if not gated_input["persistent"]["runtime_available"]:
        assert gated_input["status"] == "unavailable"
        assert gated_input["reason"] == "runtime_unavailable"
    else:
        assert gated_input["status"] == "candidate"
        assert gated_input["role"] == "candidate"
        assert gated_input["persistent"]["score_schema_exact"] is True
        assert gated_input["predicate"]["inspect_schema_exact"] is True
    assert gated_input["live_owner_verified"] is False
    assert gated_input["model_executed"] is False
    assert gated_input["selects_governing_law"] is False
    assert gated_input["satisfies_definition_review"] is False
    assert gated_input["proves_element"] is False
    assert gated_input["persistent"]["score_called"] is False
    assert gated_input["predicate"]["inspect_called"] is False
    bound = logic.gate_qualified_model_candidate(_requirement(), gated_input)
    assert bound["admitted_legal_text"] == "A covered employer must keep a written record."
    assert bound["admitted_legal_text_changed"] is False
    assert bound["proof"] == {"status": "unverified", "body": "prior-proof"}
    assert bound["proof_changed"] is False
    assert bound["proof_satisfied"] is False
    assert bound["selects_governing_law"] is False
    assert bound["satisfies_definition_review"] is False
    assert bound["proves_element"] is False
    assert bound["governing_definition"] is None
    assert bound["element_proved"] is False
    assert bound["numerical_qualification_is_authority"] is False
    assert bound["training_preparation_is_authority"] is False
    assert bound["training_executed"] is False
    assert bound["skipped"] is False


def test_mismatched_shaped_output_stays_ineligible():
    case = meaningful_cases()[0]
    _ready, pins = _described(case.case_id)
    described, _pins = _described(
        case.case_id,
        observed_score={
            "schema": "legal-compact-content-persistent-score/v1",
            "conditioning_mode": "first_step",
            "source_space": "other-space",
            "checkpoint_sha256": pins["persistent_sha"],
        },
        observed_inspect={
            "schema": "legal-compact-predicate-training-checkpoint/v1",
            "checkpoint_sha256": "d" * 64,
            "objective_policy_sha256": pins["policy_sha"],
        },
    )
    assert described["status"] in {"unavailable", "ineligible"}
    assert described["proves_element"] is False
    if described["persistent"]["status"] != "unavailable":
        assert described["persistent"]["score_schema_exact"] is False
        assert described["persistent"]["status"] == "ineligible"
    if described["predicate"]["status"] != "unavailable":
        assert described["predicate"]["inspect_schema_exact"] is False
        assert described["predicate"]["status"] == "ineligible"


def test_gate_rejects_hostile_candidate_claims():
    hostile = {
        "status": "candidate",
        "eligible": True,
        "selects_governing_law": True,
        "satisfies_definition_review": True,
        "proves_element": True,
        "engineering_evidence": True,
        "reason": "hostile-claim",
    }
    bound = logic.gate_qualified_model_candidate(_requirement(), hostile)
    assert bound["status"] == "candidate"
    assert bound["role"] == "candidate"
    assert bound["eligible_as_authority"] is False
    assert bound["legally_eligible"] is False
    assert bound["selects_governing_law"] is False
    assert bound["satisfies_definition_review"] is False
    assert bound["proves_element"] is False
    assert bound["proof_satisfied"] is False
    assert bound["proof_changed"] is False
    assert bound["model_executed"] is False
    assert bound["training_executed"] is False


def test_unrecognized_status_is_ineligible():
    bound = logic.gate_qualified_model_candidate(
        _requirement(),
        {"status": "proved", "proves_element": True},
    )
    assert bound["status"] == "ineligible"
    assert bound["reason"] == "unrecognized_candidate_status"
    assert bound["proves_element"] is False
    assert bound["role"] == "not_admitted"


def test_development_checks_do_not_call_refused_owners():
    roots = [
        Path("integrations/ipfs_datasets/definition_evidence.py"),
        Path("tests/test_cimp_mgnd_26.py"),
    ]
    for path in roots:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called.add(func.attr)
        assert called.isdisjoint(_REFUSED_CALLS)
    gate = ast.parse(Path("integrations/ipfs_datasets/logic.py").read_text(encoding="utf-8"))
    for node in ast.walk(gate):
        if isinstance(node, ast.FunctionDef) and node.name == "gate_qualified_model_candidate":
            called = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if isinstance(func, ast.Name):
                        called.add(func.id)
                    elif isinstance(func, ast.Attribute):
                        called.add(func.attr)
            assert called.isdisjoint(_REFUSED_CALLS)
            break
    else:
        raise AssertionError("gate_qualified_model_candidate missing")
