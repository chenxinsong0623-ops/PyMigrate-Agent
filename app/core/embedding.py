"""类型化 Embedding 边界与完全离线的确定性模拟实现。"""

from __future__ import annotations

import hashlib
import math
from typing import Literal, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

EMBEDDING_DIMENSION = 384
FAKE_EMBEDDING_MODEL = "fake-embedding"

EmbeddingInputType = Literal["query", "passage"]
EmbeddingVector = tuple[float, ...]


class _EmbeddingBoundaryModel(BaseModel):
    """Embedding 边界值使用的严格不可变基础模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EmbeddingRequest(_EmbeddingBoundaryModel):
    """由边界统一添加 e5 prefix 的原始文本批量请求。"""

    input_type: EmbeddingInputType
    texts: tuple[str, ...]

    @field_validator("texts")
    @classmethod
    def validate_texts(cls, texts: tuple[str, ...]) -> tuple[str, ...]:
        """拒绝空 batch、空白文本和调用方预先拼接的保留前缀。"""
        if not texts:
            raise ValueError("Embedding 文本批量不能为空")

        for text in texts:
            if not text.strip():
                raise ValueError("Embedding 文本不能为空或纯空白")
            normalized = text.lstrip().casefold()
            if normalized.startswith(("query:", "passage:")):
                raise ValueError("调用方必须传入未添加 e5 prefix 的原始文本")
        return texts

    @property
    def model_inputs(self) -> tuple[str, ...]:
        """返回按输入类型添加了唯一正确 prefix 的稳定模型输入。"""
        return tuple(format_e5_input(self.input_type, text) for text in self.texts)


class EmbeddingResponse(_EmbeddingBoundaryModel):
    """Embedding 客户端返回的批量向量。"""

    model: str
    dimension: Literal[384] = EMBEDDING_DIMENSION
    vectors: tuple[EmbeddingVector, ...] = Field(min_length=1)
    input_count: int = Field(gt=0)

    @field_validator("model")
    @classmethod
    def validate_model(cls, model: str) -> str:
        """模型或 backend 标识必须是非空稳定文本。"""
        if not model.strip():
            raise ValueError("Embedding model 不能为空")
        return model

    @model_validator(mode="after")
    def validate_vectors(self) -> EmbeddingResponse:
        """校验向量数量、固定维度和所有元素的有限性。"""
        if len(self.vectors) != self.input_count:
            raise ValueError("Embedding vector 数量必须与输入数量一致")
        for vector in self.vectors:
            if len(vector) != self.dimension:
                raise ValueError("Embedding vector 必须为 384 维")
            if any(not math.isfinite(value) for value in vector):
                raise ValueError("Embedding vector 只能包含有限 float")
        return self


@runtime_checkable
class EmbeddingClient(Protocol):
    """所有 Embedding 客户端均须实现的可注入异步接口。"""

    async def embed(
        self,
        request: EmbeddingRequest,
        timeout_seconds: float,
    ) -> EmbeddingResponse:
        """在调用方指定的超时边界内生成批量向量。"""
        ...


def format_e5_input(input_type: EmbeddingInputType, text: str) -> str:
    """将已校验的原始文本格式化为唯一正确的 e5 模型输入。"""
    if input_type == "query":
        prefix = "query"
    elif input_type == "passage":
        prefix = "passage"
    else:
        raise ValueError("不支持的 Embedding input type")
    return f"{prefix}: {text}"


def _validate_timeout(timeout_seconds: float) -> float:
    """将公开 timeout 参数校验为正的有限浮点数。"""
    if isinstance(timeout_seconds, bool) or not isinstance(
        timeout_seconds, (int, float)
    ):
        raise TypeError("timeout_seconds 必须是数值")

    validated = float(timeout_seconds)
    if not math.isfinite(validated) or validated <= 0:
        raise ValueError("timeout_seconds 必须是正的有限数值")
    return validated


def _deterministic_vector(model_input: str) -> EmbeddingVector:
    """使用标准库稳定摘要生成无语义含义的 384 维测试向量。"""
    raw = hashlib.shake_256(model_input.encode("utf-8")).digest(EMBEDDING_DIMENSION * 4)
    maximum = float((1 << 32) - 1)
    return tuple(
        (int.from_bytes(raw[offset : offset + 4], "big") / maximum) * 2.0 - 1.0
        for offset in range(0, len(raw), 4)
    )


class FakeEmbedding:
    """供测试和本地开发使用的确定性离线 Embedding 客户端。"""

    def __init__(self) -> None:
        self.calls: list[tuple[EmbeddingRequest, float]] = []

    @property
    def call_count(self) -> int:
        """返回已完成的模拟调用次数。"""
        return len(self.calls)

    async def embed(
        self,
        request: EmbeddingRequest,
        timeout_seconds: float,
    ) -> EmbeddingResponse:
        """验证公开边界并在不执行 I/O 的情况下生成确定性向量。"""
        validated_timeout = _validate_timeout(timeout_seconds)
        vectors = tuple(
            _deterministic_vector(model_input) for model_input in request.model_inputs
        )
        response = EmbeddingResponse(
            model=FAKE_EMBEDDING_MODEL,
            dimension=EMBEDDING_DIMENSION,
            vectors=vectors,
            input_count=len(request.texts),
        )
        self.calls.append((request, validated_timeout))
        return response
