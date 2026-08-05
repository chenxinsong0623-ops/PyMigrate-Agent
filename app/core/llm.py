"""类型化、可注入的 LLM 边界，以及离线确定性模拟实现。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class _BoundaryModel(BaseModel):
    """LLM 边界值使用的严格不可变基础模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LLMMessage(_BoundaryModel):
    """发送给 LLM 客户端的一条结构化消息。"""

    role: str
    content: str


class LLMRequest(_BoundaryModel):
    """通过 LLM 客户端边界传递的结构化请求。"""

    messages: tuple[LLMMessage, ...]


class LLMResponse(_BoundaryModel):
    """LLM 客户端返回的结构化响应。"""

    model: str
    content: str
    finish_reason: str


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
