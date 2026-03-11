import json
from pathlib import Path


def test_review_surface_config_exists_and_targets_review_surface_mode():
    config_path = Path("config.review_surface.json")

    assert config_path.exists()
    config = json.loads(config_path.read_text())
    assert config["APPLICATION"]["type"] == ["review-surface"]
    assert config["APPLICATION"]["port"] == 8000
    assert config["MEDIATOR"]["backends"] == ["llm-router"]