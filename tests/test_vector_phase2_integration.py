from pathlib import Path
import tempfile
from unittest.mock import patch

from mediator.integrations.vector_tools import VectorRetrievalAugmentor


def test_vector_augmentor_capabilities_shape():
    augmentor = VectorRetrievalAugmentor()
    capabilities = augmentor.capabilities()

    assert isinstance(capabilities, dict)
    assert "embeddings_available" in capabilities
    assert "mode" in capabilities


def test_vector_augmentor_boosts_overlap_and_sets_metadata():
    augmentor = VectorRetrievalAugmentor()
    records = [
        {
            "title": "Employment discrimination law",
            "snippet": "Title VII protections",
            "content": "Federal employment discrimination standards",
            "score": 0.2,
            "confidence": 0.2,
            "metadata": {},
        }
    ]

    augmented = augmentor.augment_normalized_records(records, query="employment discrimination")

    assert len(augmented) == 1
    assert augmented[0]["score"] >= 0.2
    assert augmented[0]["metadata"]["vector_augmented"] is True
    assert "vector_hint_overlap" in augmented[0]["metadata"]


def test_vector_augmentor_applies_evidence_context_similarity_metadata():
    augmentor = VectorRetrievalAugmentor()
    records = [
        {
            "title": "Termination email discussing retaliation",
            "snippet": "Manager email about retaliation complaint",
            "content": "Email evidence tied to employment retaliation and discrimination",
            "score": 0.2,
            "confidence": 0.2,
            "metadata": {},
        }
    ]

    augmented = augmentor.augment_normalized_records(
        records,
        query="employment discrimination",
        context_texts=["termination email", "retaliation complaint"],
    )

    assert len(augmented) == 1
    assert augmented[0]["metadata"]["evidence_similarity_applied"] is True
    assert augmented[0]["metadata"]["evidence_similarity_overlap"] > 0
    assert augmented[0]["metadata"]["evidence_similarity_score"] > 0.0
    assert augmented[0]["metadata"]["evidence_similarity_boost"] > 0.0


def test_vector_augmentor_capability_detection_uses_module_paths_without_importing():
    with tempfile.TemporaryDirectory() as tmpdir:
        package_root = Path(tmpdir) / "ipfs_datasets_py"
        package_root.mkdir()
        (package_root / "__init__.py").write_text("", encoding="utf-8")
        (package_root / "embeddings_router.py").write_text("", encoding="utf-8")

        fake_spec = type(
            "FakeSpec",
            (),
            {"submodule_search_locations": [str(package_root)]},
        )()

        with patch("mediator.integrations.vector_tools.importlib.util.find_spec", return_value=fake_spec):
            augmentor = VectorRetrievalAugmentor()

    assert augmentor.capabilities()["embeddings_available"] is True
