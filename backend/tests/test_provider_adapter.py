"""The real provider adapter, exercised over a mocked HTTP transport. NO network call and NO real model is used,
so this proves request/response handling only. A live call with real credentials is recorded as NOT RUN in docs/TESTING.md."""
import httpx
import pytest

from app.core.config import Settings
from app.services.review.providers import AnthropicProvider, ProviderInvalidOutput, ProviderUnavailable, build_provider

KEY = "sk-test-secret-value"


def provider(handler):
    settings = Settings(llm_api_key=KEY, llm_model="test-model", llm_base_url="https://llm.example.test")
    return AnthropicProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_request_shape_and_text_extraction():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"], seen["key"], seen["body"] = str(request.url), request.headers["x-api-key"], request.read().decode()
        return httpx.Response(200, json={"content": [{"type": "text", "text": '{"claims":'}, {"type": "text", "text": "[]}"}]})

    assert provider(handler).complete(system="s", user="u") == '{"claims":[]}'
    assert seen["url"] == "https://llm.example.test/v1/messages" and seen["key"] == KEY and '"model":"test-model"' in seen["body"].replace(" ", "")


@pytest.mark.parametrize("response", [httpx.Response(500, text="boom"), httpx.Response(401, json={"error": "bad key " + KEY}), httpx.Response(429)])
def test_http_errors_become_provider_unavailable_without_leaking_secrets(response):
    with pytest.raises(ProviderUnavailable) as exc:
        provider(lambda r: response).complete(system="s", user="u")
    assert KEY not in str(exc.value)


def test_timeouts_and_connection_errors():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("nope", request=request)

    for handler in (timeout, refused):
        with pytest.raises(ProviderUnavailable):
            provider(handler).complete(system="s", user="u")


def test_unreadable_success_response_is_invalid_output():
    with pytest.raises(ProviderInvalidOutput):
        provider(lambda r: httpx.Response(200, text="<html>not json</html>")).complete(system="s", user="u")
    with pytest.raises(ProviderInvalidOutput):
        provider(lambda r: httpx.Response(200, json={"unexpected": True})).complete(system="s", user="u")


def test_no_key_means_no_provider():
    assert build_provider(Settings(llm_api_key="")) is None
    assert build_provider(Settings(llm_api_key="   ")) is None
    assert build_provider(Settings(llm_api_key=KEY)).name == "anthropic"
