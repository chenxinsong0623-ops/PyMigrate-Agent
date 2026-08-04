import socket

import pytest

from app.core.llm import (
    FakeLLM,
    LLMClient,
    LLMMessage,
    LLMRequest,
    LLMResponse,
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
