import pytest


def test_accelerate_router_preserves_fallback_reason(monkeypatch):
	from ipfs_datasets_py.llm_router import generate_text
	from ipfs_datasets_py.router_deps import RouterDeps

	class FakeManager:
		def run_inference(self, model_name, payload, task_type):
			assert model_name == "gpt2"
			assert payload["prompt"] == "Reply with exactly OK."
			assert task_type == "text-generation"
			return {
				"status": "success",
				"backend": "local_fallback",
				"text": None,
				"message": "Accelerate not available, using local fallback",
			}

	deps = RouterDeps(accelerate_managers={"llm_router": FakeManager()})
	monkeypatch.delenv("IPFS_DATASETS_PY_ENABLE_IPFS_ACCELERATE", raising=False)

	with pytest.raises(RuntimeError, match="local_fallback") as exc_info:
		generate_text(
			"Reply with exactly OK.",
			provider="accelerate",
			model_name="gpt2",
			deps=deps,
		)

	message = str(exc_info.value)
	assert "Accelerate not available, using local fallback" in message
	assert "status=success" in message
	assert "backend=local_fallback" in message