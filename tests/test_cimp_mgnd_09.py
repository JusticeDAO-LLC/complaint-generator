"""Connect the selected knowledge-graph extractor to factual candidate roles.

Cases are synthetic private fixtures. No test is skipped. Importing the
extractor class is not treated as execution. A schema-valid model record stays
a candidate until the user source span is bound, and legal, retrieved, and
encyclopedia records are not user assertions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from complaint_phases.knowledge_graph import KnowledgeGraphBuilder
from integrations.ipfs_datasets.graphs import (
    SELECTED_KG_EXTRACTION_PATH,
    executed_extraction_path,
    prepare_private_extraction,
)
from integrations.ipfs_datasets.types import source_byte_hash, user_assertion_from_mapping


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

AUTHORED = "Ada notified HR."
LOCAL_TEXT = "My employer discriminated against me at work."
_TRUTHFUL_UNAVAILABLE = {
    "extractor_unavailable",
    "extractor_custody_unavailable",
    "extractor_effect_denied",
    "extractor_timeout",
    "extractor_cleanup_unconfirmed",
    "extractor_error",
    "extractor_invalid_result",
    "extractor_output_limit",
}

_FIXTURE = r'''
import json, os, pathlib
from types import SimpleNamespace
root = pathlib.Path(__file__).resolve().parents[3]
mode = json.loads((root / "mode.json").read_text())["mode"]
class KnowledgeGraphExtractor:
    def __init__(self, **options):
        assert options == {"use_spacy": False, "use_transformers": False, "use_tracer": False, "use_srl": False}
        assert os.environ.get("HF_HUB_OFFLINE") == "1"
        assert os.environ.get("HF_DATASETS_OFFLINE") == "1"
        assert os.environ.get("TRANSFORMERS_OFFLINE") == "1"
        assert os.environ.get("IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD") == "0"
        if mode == "import-only":
            raise AttributeError("selected method is not this constructor")
    def extract_knowledge_graph(self, text):
        if mode == "empty":
            return SimpleNamespace(entities={}, relationships={})
        if mode == "wiki":
            class Entity:
                entity_id = "wiki-ada"
                entity_type = "person"
                name = "Ada Lovelace"
                confidence = 0.99
                source_text = text
                extraction_method = "wikipedia"
                properties = {"wikidata": "Q7259"}
            return SimpleNamespace(entities={"wiki-ada": Entity()}, relationships={})
        if mode == "retrieved":
            class Entity:
                entity_id = "graph-claim"
                entity_type = "fact"
                name = "retrieved graph claim"
                confidence = 0.9
                source_text = text
                extraction_method = "retrieved_graph"
                properties = {"graph": "retrieved_graph"}
            return SimpleNamespace(entities={"graph-claim": Entity()}, relationships={})
        if mode == "statute":
            class Entity:
                entity_id = "statute-1"
                entity_type = "statute"
                name = "Title VII"
                confidence = 0.9
                source_text = text
                extraction_method = "rule_based"
                properties = {}
            return SimpleNamespace(entities={"statute-1": Entity()}, relationships={})
        if mode == "neural":
            class Entity:
                entity_id = "neural-ada"
                entity_type = "person"
                name = "Ada"
                confidence = 0.95
                source_text = text
                extraction_method = "neural"
                properties = {}
            return SimpleNamespace(entities={"neural-ada": Entity()}, relationships={})
        class Entity:
            entity_id = "person-ada"
            entity_type = "person"
            name = "Ada"
            confidence = 0.9
            source_text = text
            extraction_method = "rule_based"
            properties = {}
        return SimpleNamespace(entities={"person-ada": Entity()}, relationships={})
'''


def _cases():
    return (
        {"label": "bound-user-span", "text": AUTHORED, "mode": "bound"},
        {"label": "model-candidate", "text": AUTHORED, "mode": "neural"},
        {"label": "encyclopedia", "text": AUTHORED, "mode": "wiki"},
        {"label": "retrieved-graph", "text": AUTHORED, "mode": "retrieved"},
        {"label": "statute-entity", "text": AUTHORED, "mode": "statute"},
        {"label": "empty-graph", "text": AUTHORED, "mode": "empty"},
        {"label": "import-is-not-execution", "text": AUTHORED, "mode": "import-only"},
        {"label": "local-fallback", "text": LOCAL_TEXT, "mode": "unavailable"},
        {"label": "legal-passage", "text": "Retaliation is prohibited.", "mode": "legal"},
    )


def _context(text: str) -> dict:
    return {
        "source_kind": "user_statement",
        "source_id": "message-private",
        "message_id": "message-private",
        "assertion_status": "asserted",
        "extractor_version": "kg-candidate-v1",
        "source_hash": source_byte_hash(text),
    }


def _install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    root = tmp_path / "extractor-root"
    package = root / "ipfs_datasets_py" / "knowledge_graphs" / "extraction"
    package.mkdir(parents=True)
    for directory in (package, package.parent, package.parent.parent, package.parent.parent.parent):
        (directory / "__init__.py").write_text("")
    (package / "extractor.py").write_text(_FIXTURE)
    (root / "mode.json").write_text(json.dumps({"mode": mode}))
    monkeypatch.setattr(
        "integrations.ipfs_datasets.graphs._private_extractor_roots",
        lambda: [str(root)],
    )


def _upstream_asserted(graph) -> list[str]:
    names = []
    for entity in graph.entities.values():
        if entity.attributes.get("upstream_extraction") is not True:
            continue
        envelope = user_assertion_from_mapping((entity.provenance or {}).get("user_assertion"))
        if envelope.is_asserted_user_fact:
            names.append(entity.name)
    return names


def test_meaningful_cases_are_nonempty_and_unskipped():
    cases = _cases()
    assert cases
    assert len({item["label"] for item in cases}) == len(cases)
    assert all(item["text"].strip() for item in cases)
    assert executed_extraction_path({
        "extractor": "KnowledgeGraphExtractor",
        "module": "ipfs_datasets_py.knowledge_graphs.extraction.extractor",
    }) == ""


def test_selected_path_binds_one_user_span_and_keeps_model_output_a_candidate(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "bound")
    bound = prepare_private_extraction(AUTHORED, _context(AUTHORED))
    assert bound["status"] == "available"
    assert bound["provenance"]["path_executed"] is True
    assert bound["provenance"]["enabled_path"] == SELECTED_KG_EXTRACTION_PATH
    assert bound["provenance"]["options"]["use_tracer"] is False
    assert bound["provenance"]["options"]["use_transformers"] is False
    roles = bound["factual_candidate_roles"]
    assert roles["path_executed"] is True
    assert roles["import_available_is_execution"] is False
    assert roles["source_binding"] == "admitted"
    assert roles["roles"][0]["admitted"] is True
    record = roles["roles"][0]["record"]
    assert record["role"] == "extracted_candidate"
    assert record["candidate_extractor_ref"] == SELECTED_KG_EXTRACTION_PATH
    assert record["governs_law"] is False
    graph = KnowledgeGraphBuilder().build_from_text(AUTHORED, source_context=_context(AUTHORED))
    assert _upstream_asserted(graph) == ["Ada"]

    _install(tmp_path / "neural", monkeypatch, "neural")
    neural = prepare_private_extraction(AUTHORED, _context(AUTHORED))
    assert neural["provenance"]["enabled_path"] == SELECTED_KG_EXTRACTION_PATH
    assert neural["factual_candidate_roles"]["source_binding"] == "unknown"
    assert neural["factual_candidate_roles"]["binding_checked"] is True
    neural_graph = KnowledgeGraphBuilder().build_from_text(AUTHORED, source_context=_context(AUTHORED))
    assert _upstream_asserted(neural_graph) == []
    model = next(entity for entity in neural_graph.entities.values() if entity.attributes.get("upstream_extraction") is True)
    assert model.type == "model_suggestion"
    assert model.provenance["user_assertion"]["role"]


def test_legal_retrieved_and_encyclopedia_records_are_not_user_assertions(tmp_path, monkeypatch):
    for mode, kind in (("wiki", "wikidata_wikipedia"), ("retrieved", "retrieved_graph_claim"), ("statute", "legal_text")):
        _install(tmp_path / mode, monkeypatch, mode)
        extraction = prepare_private_extraction(AUTHORED, _context(AUTHORED))
        assert extraction["provenance"]["path_executed"] is True
        assert extraction["factual_candidate_roles"]["source_binding"] == "withheld"
        assert kind in extraction["factual_candidate_roles"]["withheld_non_user"]
        graph = KnowledgeGraphBuilder().build_from_text(AUTHORED, source_context=_context(AUTHORED))
        assert _upstream_asserted(graph) == []
        upstream = [entity for entity in graph.entities.values() if entity.attributes.get("upstream_extraction") is True]
        assert upstream
        assert all(entity.type in {"model_suggestion", "legal_text"} for entity in upstream)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legal text must not run the private extractor")

    monkeypatch.setattr("integrations.ipfs_datasets.graphs._run_owned_private_extractor", forbidden)
    legal = KnowledgeGraphBuilder().build_from_text(
        "Retaliation is prohibited.",
        source_context={"source_kind": "law", "source_id": "synthetic-law"},
    )
    handoff = legal.metadata["factual_candidate_roles"]
    assert handoff["path_executed"] is False
    assert handoff["enabled_path"] == ""
    assert handoff["withheld_non_user"] == ["legal_text"]
    assert legal.entities
    assert _upstream_asserted(legal) == []
    assert all(entity.type == "legal_text" for entity in legal.entities.values())
    assert all(
        not user_assertion_from_mapping((entity.provenance or {}).get("user_assertion")).is_asserted_user_fact
        for entity in legal.entities.values()
    )


def test_unavailable_extractor_keeps_local_fallback_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr("integrations.ipfs_datasets.graphs._private_extractor_roots", lambda: [])
    graph = KnowledgeGraphBuilder().build_from_text(LOCAL_TEXT, source_context=_context(LOCAL_TEXT))
    private = graph.metadata["private_extraction"]
    assert private["status"] == "unavailable"
    assert private["diagnostic"] == "extractor_unavailable"
    assert private["local_fallback"] is True
    assert private["provenance"]["path_executed"] is False
    assert private["provenance"]["enabled_path"] == ""
    assert graph.metadata["factual_candidate_roles"]["roles"] == []
    assert graph.entities
    assert _upstream_asserted(graph) == []

    _install(tmp_path, monkeypatch, "import-only")
    missing = prepare_private_extraction(AUTHORED, _context(AUTHORED))
    assert missing["status"] == "unavailable"
    assert missing["diagnostic"] == "extractor_unavailable"
    assert missing["provenance"]["path_executed"] is False
    assert missing["factual_candidate_roles"]["roles"] == []


def test_configured_extractor_records_the_path_only_when_it_returns():
    """The checkout extractor, with enrichment and downloads disabled.

    Absence stays a typed unavailable result. Import success is not a run.
    """
    result = prepare_private_extraction(AUTHORED, _context(AUTHORED))
    provenance = result["provenance"]
    assert provenance["method"] == "extract_knowledge_graph"
    assert provenance["options"] == {
        "use_spacy": False,
        "use_transformers": False,
        "use_tracer": False,
        "use_srl": False,
    }
    assert provenance["import_available_is_execution"] is False
    roles = result["factual_candidate_roles"]
    if result["status"] != "available":
        assert result["status"] in {"unavailable", "degraded"}
        assert result["diagnostic"] in _TRUTHFUL_UNAVAILABLE
        assert provenance["path_executed"] is False
        assert provenance["enabled_path"] == ""
        assert roles["roles"] == []
        return
    assert provenance["path_executed"] is True
    assert provenance["enabled_path"] == SELECTED_KG_EXTRACTION_PATH
    assert roles["path_executed"] is True
    assert roles["roles"] and roles["roles"][0]["record"]["role"] == "extracted_candidate"
    graph = KnowledgeGraphBuilder().build_from_text(AUTHORED, source_context=_context(AUTHORED))
    for entity in graph.entities.values():
        envelope = user_assertion_from_mapping((entity.provenance or {}).get("user_assertion"))
        if envelope.is_asserted_user_fact:
            assert entity.name in AUTHORED
            assert entity.attributes.get("non_user_kind") in (None, "")
