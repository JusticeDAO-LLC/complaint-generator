"""Bounded owner-capability probe for the declared A/Data/Kit APIs.

Cases use synthetic private fixtures. Optional failures stay typed records.
No test is skipped.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from integrations.ipfs_datasets.capabilities import (
    DECLARED_OWNER_PINS,
    OWNER_INVENTORY_SCHEMA_VERSION,
    _ENABLED_KG_PATH,
    build_owner_inventory,
    record_enhanced_feature_flags,
)
from integrations.ipfs_datasets.loader import classify_owner_checkout, observe_checked_out_commit

INVENTORY_PATH = Path("docs/task_boards/complaint_mediator_grounding_owner_inventory.json")
ROOT = Path(__file__).resolve().parents[1]
_CHECKOUT_OBSERVATION_FIELDS = frozenset({
    "checked_out_commit", "checked_out_commit_status", "checked_out_commit_error_type", "pin_is_observed_head",
})
NAMED_MODULES = {
    "ipfs_datasets_py.knowledge_graphs.extraction.extractor",
    "ipfs_datasets_py.knowledge_graphs",
    "ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api",
    "integrations.ipfs_datasets.logic",
    "ipfs_datasets_py.logic.autoformal.legal_source_sampling_review_context",
    "ipfs_datasets_py.logic.autoformal.legal_source_sampling_context_definition_binding_v2",
    "ipfs_datasets_py.logic.autoformal.legal_source_sampling_context_definition_review_v2",
    "ipfs_datasets_py.logic.autoformal.legal_norm_definition_evidence_v1",
    "ipfs_datasets_py.logic.autoformal.legal_norm_scope_correspondence_v1",
    "ipfs_datasets_py.logic.autoformal.legal_norm_interpretation_review_v1",
    "ipfs_datasets_py.logic.autoformal.legal_bound_variable_definition_v1",
    "ipfs_datasets_py.logic.formalization.autoencoder.legal_compact_content_persistent_v1",
    "ipfs_datasets_py.logic.formalization.autoencoder.legal_compact_content_predicate_training_v1",
    "integrations.ipfs_datasets.storage",
}


def _inventory_contract(inventory: dict) -> dict:
    """Compare the owned-source contract independently of a checkout observation."""
    return {
        **inventory,
        "owners": [
            {key: value for key, value in row.items() if key not in _CHECKOUT_OBSERVATION_FIELDS}
            for row in inventory["owners"]
        ],
    }


def _assert_checkout_observation(row: dict) -> None:
    assert _CHECKOUT_OBSERVATION_FIELDS <= set(row)
    assert row["checked_out_commit_status"] in {"available", "unavailable"}
    if row["checked_out_commit_status"] == "available":
        commit = row["checked_out_commit"]
        assert isinstance(commit, str) and len(commit) == 40
        assert all(character in "0123456789abcdef" for character in commit)
        assert row["checked_out_commit_error_type"] == ""
    else:
        assert row["checked_out_commit"] == ""
        assert isinstance(row["checked_out_commit_error_type"], str) and row["checked_out_commit_error_type"]
    assert row["pin_is_observed_head"] is (
        row["checked_out_commit"] == row["declared_pin"] and row["checked_out_commit_status"] == "available"
    )


def test_synthetic_checkout_kinds_distinguish_gitlink_from_populated_tree(tmp_path: Path):
    populated = tmp_path / "populated"
    source = populated / "pkg" / "__init__.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n", encoding="utf-8")
    opaque = tmp_path / "opaque-gitlink"
    opaque.mkdir()
    missing = tmp_path / "missing"

    populated_record = classify_owner_checkout(
        populated, canonical_relative="pkg/__init__.py", declared_submodule=True,
    )
    opaque_record = classify_owner_checkout(
        opaque, canonical_relative="pkg/__init__.py", declared_submodule=True,
    )
    absent_record = classify_owner_checkout(
        missing, canonical_relative="pkg/__init__.py", declared_submodule=True,
    )
    undeclared_record = classify_owner_checkout(
        missing, canonical_relative="pkg/__init__.py", declared_submodule=False,
    )

    assert populated_record["checkout_kind"] == "populated_checkout"
    assert populated_record["populated"] is True
    assert opaque_record["checkout_kind"] == "opaque_gitlink"
    assert opaque_record["populated"] is False
    assert absent_record["checkout_kind"] == "opaque_gitlink"
    assert undeclared_record["checkout_kind"] == "missing_checkout"

    readable = tmp_path / "readable-gitdir"
    readable.mkdir()
    (readable / ".git").write_text("gitdir: ../sealed-modules/owner\n", encoding="utf-8")
    sealed = tmp_path / "sealed-gitdir"
    sealed.mkdir()
    sealed_git = sealed / ".git"
    sealed_git.write_text("gitdir: ../sealed-modules/owner\n", encoding="utf-8")
    sealed_git.chmod(0)
    try:
        readable_commit = classify_owner_checkout(
            readable, canonical_relative="pkg/__init__.py", declared_submodule=True,
        )

        assert readable_commit["checkout_kind"] == "opaque_gitlink"
        assert observe_checked_out_commit(readable)["error_type"] == "GitdirPointer"
        assert observe_checked_out_commit(sealed)["error_type"] == "GitdirPointer"
        assert observe_checked_out_commit(readable)["commit"] == ""
        assert observe_checked_out_commit(sealed)["status"] == "unavailable"
    finally:
        sealed_git.chmod(0o644)


def test_owner_inventory_records_pins_paths_flags_and_seam_invocations():
    inventory = build_owner_inventory()
    committed = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    assert inventory["schema_version"] == OWNER_INVENTORY_SCHEMA_VERSION
    # The recorded worker observed GitdirPointer; a proper clone can now
    # observe HEAD. Preserve every non-observational source/pin/API contract.
    assert _inventory_contract(inventory) == _inventory_contract(committed)
    for row in [*committed["owners"], *inventory["owners"]]:
        _assert_checkout_observation(row)
    assert inventory["api_count"] == len(NAMED_MODULES)
    assert inventory["conditional_engineering_count"] >= 1

    owners = {row["name"]: row for row in inventory["owners"]}
    assert set(owners) == set(DECLARED_OWNER_PINS)
    for name, pin in DECLARED_OWNER_PINS.items():
        row = owners[name]
        observed = observe_checked_out_commit(ROOT / row["relative_path"])
        assert row["checked_out_commit"] == observed["commit"]
        assert row["checked_out_commit_status"] == observed["status"]
        assert row["checked_out_commit_error_type"] == observed["error_type"]
        if observed["status"] == "available":
            actual = subprocess.run(
                ["git", "--no-optional-locks", "-c", "core.hooksPath=/dev/null", "-C",
                 str(ROOT / row["relative_path"]), "rev-parse", "--verify", "HEAD^{commit}"],
                check=True, capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            assert observed["commit"] == actual
        assert row["declared_pin"] == pin
        assert row["canonical_source_path"].endswith("__init__.py")
        assert row["checkout_kind"] in {"populated_checkout", "opaque_gitlink", "missing_checkout"}
        assert row["checkout_kind"] != "populated_checkout" or row["populated"] is True
        assert row["pin_is_observed_head"] is (row["checked_out_commit"] == pin and row["checked_out_commit_status"] == "available")
        if row["checked_out_commit_status"] != "available":
            assert row["checked_out_commit"] == ""
            assert row["checked_out_commit_error_type"]

    modules = {row["module"]: row for row in inventory["apis"]}
    assert set(modules) == NAMED_MODULES
    for row in modules.values():
        assert row["symbols"]
        assert row["canonical_source_path"]
        assert row["semantic_authority"] is False
        assert row["proof_authority"] is False
        assert row["status"] in {"present", "unavailable"}
        if row["status"] == "unavailable":
            assert row["error_type"]
            assert row["source_present"] is False

    flags = inventory["feature_flags"]
    assert flags == record_enhanced_feature_flags()
    assert flags["global_enable_all"] is False
    assert flags["environment_mutated"] is False
    assert flags["wikipedia_enrichment_enabled"] is False
    assert flags["model_setup_enabled"] is False
    assert flags["scraping_enabled"] is False
    assert flags["enhanced_path_enabled"] is False
    assert flags["actually_enabled_path"] == _ENABLED_KG_PATH
    assert flags["extractor_options"] == {
        "use_spacy": False,
        "use_transformers": False,
        "use_tracer": False,
        "use_srl": False,
    }

    seams = inventory["seams"]
    assert set(seams) == {"knowledge_graph", "legal", "logic", "private_storage"}
    for seam in seams.values():
        assert seam["status"]
        assert "error_type" in seam
        assert seam["called"] is True or seam["status"] == "unavailable"

    knowledge = seams["knowledge_graph"]
    assert knowledge["method"] == _ENABLED_KG_PATH
    assert knowledge["enhanced_called"] is False
    assert knowledge["wikipedia_enrichment_enabled"] is False
    if knowledge["called"]:
        assert knowledge["entity_count"] >= 0

    legal = seams["legal"]
    assert legal["symbol"] == "search_us_code_corpus_from_parameters"
    assert legal["network_requested"] is False
    assert legal["scraping_requested"] is False
    if legal["called"]:
        assert legal["early_parameter_refusal"] is True or legal["status"] == "unavailable"

    logic = seams["logic"]
    assert logic["symbol"] == "proof_cache_identity"
    assert logic["proof_authority"] is False
    assert logic["satisfied"] is False
    if logic["called"] and logic["status"] == "available":
        assert logic["cache_identity_present"] is True

    storage = seams["private_storage"]
    assert storage["symbol"] == "store_private_artifact"
    assert storage["kit_enabled_by_probe"] is False
    assert storage["plaintext_observed"] is False
    if storage["called"] and storage["status"] != "unavailable":
        assert storage["verified"] is True

    training = inventory["training_and_definition"]
    assert training["authority_role"] == "conditional_engineering"
    assert training["semantic_authority"] is False
    assert training["proof_authority"] is False
    assert training["governing_law"] is False
    assert training["training_executed"] is False
    assert training["inspect_called"] is False
    assert training["model_setup"] is False
    if training["called"]:
        assert training["symbol"] == "checkpoint_sha256"
        assert training["authority_all_false"] is True

    conditional = [row for row in inventory["apis"] if row["conditional_engineering"]]
    assert conditional
    assert all(row["authority_role"] == "conditional_engineering" for row in conditional)
    assert all(row["semantic_authority"] is False and row["proof_authority"] is False for row in conditional)
