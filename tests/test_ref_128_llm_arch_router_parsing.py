import pytest

from integrations.ipfs_datasets import llm


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network]


@pytest.mark.parametrize(
    ("response", "expected_route"),
    [
        ('{"route": "legal_reasoning"}', "legal_reasoning"),
        ('```json\n{"name": "document_drafting"}\n```', "document_drafting"),
        ('{"route": "malformed_json", trailing}', "malformed_json"),
        ("plain_text_route", "plain_text_route"),
    ],
)
def test_parse_arch_router_route_supports_expected_response_formats(
    response: str,
    expected_route: str,
) -> None:
    assert llm._parse_arch_router_route(response) == expected_route


def test_parse_arch_router_route_does_not_swallow_unexpected_parser_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_unexpectedly(_: str) -> object:
        raise RuntimeError("JSON parser unavailable")

    monkeypatch.setattr(llm.json, "loads", _fail_unexpectedly)

    with pytest.raises(RuntimeError, match="JSON parser unavailable"):
        llm._parse_arch_router_route('{"route": "legal_reasoning"}')


def test_unexpected_parser_failure_is_reported_by_arch_router_error_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_models: list[str | None] = []

    def _fake_generate_text(
        prompt: str,
        *,
        provider: str | None = None,
        model_name: str | None = None,
        **kwargs: object,
    ) -> str:
        observed_models.append(model_name)
        if model_name == llm.HF_ARCH_ROUTER_MODEL:
            return '{"route": "legal_reasoning"}'
        return "fallback model output"

    def _fail_unexpectedly(_: str) -> object:
        raise RuntimeError("JSON parser unavailable")

    monkeypatch.setattr(llm, "generate_text", _fake_generate_text)
    monkeypatch.setattr(llm.json, "loads", _fail_unexpectedly)
    monkeypatch.setenv("HF_TOKEN", "test-token")

    payload = llm.generate_text_with_metadata(
        "Analyze this claim.",
        provider="huggingface_router",
        model_name="fallback-model",
        arch_router={
            "routes": {
                "legal_reasoning": "legal-model",
            },
        },
    )

    assert payload["status"] == "available"
    assert payload["text"] == "fallback model output"
    assert payload["effective_model_name"] == "fallback-model"
    assert payload["arch_router_status"] == "fallback_error"
    assert payload["arch_router_error"] == "JSON parser unavailable"
    assert observed_models == [llm.HF_ARCH_ROUTER_MODEL, "fallback-model"]
