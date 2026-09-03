"""类型化、可注入的 LLM 边界，以及离线确定性模拟实现。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _BoundaryModel(BaseModel):
    """LLM 边界值使用的严格不可变基础模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LLMMessage(_BoundaryModel):
    """发送给 LLM 客户端的一条结构化消息。"""

    role: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=1, max_length=131_072)


class LLMRequest(_BoundaryModel):
    """通过 LLM 客户端边界传递的结构化请求。"""

    messages: tuple[LLMMessage, ...] = Field(min_length=1, max_length=64)


class LLMResponse(_BoundaryModel):
    """LLM 客户端返回的结构化响应。"""

    model: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=262_144)
    finish_reason: str = Field(min_length=1, max_length=64)


class LLMClientError(RuntimeError):
    """可安全归类、但不暴露 provider 原文或凭据的调用失败。"""


@runtime_checkable
class LLMClient(Protocol):
    """所有 LLM 客户端均须实现的可注入异步接口。"""

    async def complete(
        self,
        request: LLMRequest,
        timeout_seconds: float,
    ) -> LLMResponse:
        """在调用方指定的超时时间内完成结构化请求。"""
        ...


class FakeLLM:
    """供测试和本地开发使用的确定性离线 LLM 客户端。"""

    def __init__(self, response: LLMResponse | None = None) -> None:
        self._response = response or LLMResponse(
            model="fake",
            content="MigrationLens 离线模拟响应：未调用真实大模型。",
            finish_reason="stop",
        )
        self.calls: list[tuple[LLMRequest, float]] = []

    @property
    def call_count(self) -> int:
        """返回已完成的模拟调用次数。"""
        return len(self.calls)

    async def complete(
        self,
        request: LLMRequest,
        timeout_seconds: float,
    ) -> LLMResponse:
        """记录调用并在不执行 I/O 的情况下返回预设响应。"""
        self.calls.append((request, float(timeout_seconds)))
        return self._response


class _ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    content: str | None = None


class _ChatChoice(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    message: _ChatMessage
    finish_reason: str | None = None


class _ChatCompletion(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    model: str
    choices: tuple[_ChatChoice, ...]


class RealLLMClient:
    """最小 OpenAI-compatible Chat Completions 异步 adapter。"""

    _ALLOWED_ROLES = frozenset({"system", "user", "assistant"})

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        max_output_tokens: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url or not model or not api_key:
            raise ValueError("真实 LLM client 配置不完整")
        if not 1 <= max_output_tokens <= 16_384:
            raise ValueError("LLM 最大输出 token 配置无效")
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._api_key = api_key
        self._max_output_tokens = max_output_tokens
        self._transport = transport

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(model={self._model!r}, "
            f"endpoint={self._endpoint!r}, api_key=<redacted>)"
        )

    async def complete(
        self,
        request: LLMRequest,
        timeout_seconds: float,
    ) -> LLMResponse:
        checked = LLMRequest.model_validate(request.model_dump(mode="python"))
        if timeout_seconds <= 0:
            raise ValueError("LLM timeout 必须大于 0")
        if any(item.role not in self._ALLOWED_ROLES for item in checked.messages):
            raise LLMClientError("LLM request contract rejected")
        payload = {
            "model": self._model,
            "messages": [
                {"role": item.role, "content": item.content}
                for item in checked.messages
            ],
            "max_tokens": self._max_output_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds),
                transport=self._transport,
            ) as client:
                response = await client.post(
                    self._endpoint,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.TimeoutException:
            raise LLMClientError("LLM provider timeout") from None
        except httpx.HTTPError:
            raise LLMClientError("LLM provider request failed") from None

        try:
            completion = _ChatCompletion.model_validate_json(response.content)
            if len(completion.choices) != 1:
                raise ValueError("unexpected choice count")
            choice = completion.choices[0]
            content = choice.message.content
            finish_reason = choice.finish_reason
            if content is None or not content.strip() or finish_reason is None:
                raise ValueError("empty completion")
            return LLMResponse(
                model=completion.model,
                content=content,
                finish_reason=finish_reason,
            )
        except (ValidationError, ValueError):
            raise LLMClientError("LLM provider returned an invalid response") from None
