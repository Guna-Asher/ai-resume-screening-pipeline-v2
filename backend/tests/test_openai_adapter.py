import asyncio
import json

import httpx
import pytest

from app.llm import LLMError, LLMFailure, OpenAICompatibleAdapter

KEY = "sk-test-SECRET-KEY"


def adapter(handler) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        provider="openai_compatible",
        base_url="http://llm.test/v1/",
        api_key=KEY,
        model="some-model",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )


def complete(a):
    return asyncio.run(a.complete(system="sys", user="usr"))


def ok(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_success_sends_expected_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return ok('{"projects": []}')

    assert complete(adapter(handler)) == '{"projects": []}'
    assert seen["url"] == "http://llm.test/v1/chat/completions"
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["body"]["model"] == "some-model" and seen["body"]["temperature"] == 0
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (429, LLMFailure.RATE_LIMIT),
        (401, LLMFailure.AUTH_ERROR),
        (403, LLMFailure.AUTH_ERROR),
        (500, LLMFailure.API_ERROR),
        (400, LLMFailure.API_ERROR),
    ],
)
def test_http_errors_are_normalised_and_bodies_are_not_kept(status, category):
    handler = lambda request: httpx.Response(status, text=f"provider says {KEY} is bad")  # noqa: E731
    with pytest.raises(LLMError) as exc:
        complete(adapter(handler))
    assert exc.value.category == category
    assert KEY not in str(exc.value) and "provider says" not in str(exc.value)


def test_timeout_and_connection_errors():
    def slow(request):
        raise httpx.ReadTimeout("took too long", request=request)

    def down(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMError) as exc:
        complete(adapter(slow))
    assert exc.value.category == LLMFailure.TIMEOUT
    with pytest.raises(LLMError) as exc:
        complete(adapter(down))
    assert exc.value.category == LLMFailure.CONNECTION_ERROR


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json at all"),
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]}),
    ],
)
def test_unexpected_response_shapes_are_api_errors(response):
    with pytest.raises(LLMError) as exc:
        complete(adapter(lambda request: response))
    assert exc.value.category == LLMFailure.API_ERROR
