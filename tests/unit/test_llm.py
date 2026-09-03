import asyncio
import json
import socket

import httpx
import pytest

from app.core.llm import (
    FakeLLM,
    LLMClient,
    LLMClientError,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    RealLLMClient,
)


def _request() -> LLMRequest:
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content="请返回结构化输出。"),
            LLMMessage(role="user", content="请审查这个发现。"),
        ]
    )


def test_fake_llm_satisfies_runtime_client_protocol() -> None:
    fake_llm = FakeLLM()

    assert isinstance(fake_llm, LLMClient)


@pytest.mark.asyncio
async def test_fake_llm_returns_expected_default_response() -> None:
    fake_llm = FakeLLM()

    response = await fake_llm.complete(
        _request(),
        timeout_seconds=1.0,
    )

    assert response.model == "fake"
    assert response.content == "MigrationLens 离线模拟响应：未调用真实大模型。"
    assert response.finish_reason == "stop"
    assert fake_llm.call_count == 1


@pytest.mark.asyncio
async def test_fake_llm_is_deterministic_and_records_calls() -> None:
    response = LLMResponse(
        model="fake-test",
        content='{"status":"ok"}',
        finish_reason="stop",
    )
    fake_llm = FakeLLM(response=response)
    request = _request()

    first = await fake_llm.complete(request, 2.5)
    second = await fake_llm.complete(request, timeout_seconds=2.5)

    assert first == response
    assert second == response
    assert fake_llm.call_count == 2
    assert fake_llm.calls == [(request, 2.5), (request, 2.5)]


@pytest.mark.asyncio
async def test_fake_llm_does_not_open_a_network_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("FakeLLM 尝试建立网络连接")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)

    fake_llm = FakeLLM()
    await fake_llm.complete(_request(), timeout_seconds=1.0)

    assert fake_llm.call_count == 1


def _real_client(
    handler: httpx.AsyncBaseTransport,
    *,
    api_key: str = "unit-test-secret-value",
) -> RealLLMClient:
    return RealLLMClient(
        base_url="https://provider.example/v1/",
        model="provider-model",
        api_key=api_key,
        max_output_tokens=512,
        transport=handler,
    )


@pytest.mark.asyncio
async def test_real_llm_request_and_response_model_identity() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://provider.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer unit-test-secret-value"
        payload = json.loads(request.content)
        assert payload == {
            "model": "provider-model",
            "messages": [
                {"role": "system", "content": "请返回结构化输出。"},
                {"role": "user", "content": "请审查这个发现。"},
            ],
            "max_tokens": 512,
            "stream": False,
        }
        return httpx.Response(
            200,
            json={
                "model": "provider-model-actual",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": '{"ok":true}'},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    response = await _real_client(httpx.MockTransport(handler)).complete(
        _request(), timeout_seconds=3.0
    )

    assert response == LLMResponse(
        model="provider-model-actual",
        content='{"ok":true}',
        finish_reason="stop",
    )


@pytest.mark.asyncio
async def test_real_llm_maps_timeout_without_leaking_secret() -> None:
    secret = "unit-test-secret-timeout"

    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider detail with " + secret)

    client = _real_client(httpx.MockTransport(handler), api_key=secret)
    with pytest.raises(LLMClientError) as captured:
        await client.complete(_request(), timeout_seconds=0.01)

    assert str(captured.value) == "LLM provider timeout"
    assert secret not in str(captured.value)
    assert secret not in repr(client)


@pytest.mark.asyncio
async def test_real_llm_maps_http_error_without_provider_body() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="sensitive provider body")

    with pytest.raises(LLMClientError, match="LLM provider request failed") as captured:
        await _real_client(httpx.MockTransport(handler)).complete(
            _request(), timeout_seconds=1.0
        )

    assert "sensitive provider body" not in str(captured.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"model": "actual", "choices": []},
        {
            "model": "actual",
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
        },
        {
            "model": "actual",
            "choices": [{"message": {"content": "ok"}, "finish_reason": None}],
        },
    ],
)
async def test_real_llm_rejects_invalid_or_empty_response(
    payload: dict[str, object],
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(
        LLMClientError,
        match="LLM provider returned an invalid response",
    ):
        await _real_client(httpx.MockTransport(handler)).complete(
            _request(), timeout_seconds=1.0
        )


@pytest.mark.asyncio
async def test_real_llm_does_not_swallow_cancellation() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await _real_client(httpx.MockTransport(handler)).complete(
            _request(), timeout_seconds=1.0
        )
