"""类型化 Embedding 边界、离线 fake 与固定 revision 的真实 E5 adapter。"""

from __future__ import annotations

import asyncio
import hashlib
import math
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

EMBEDDING_DIMENSION = 384
FAKE_EMBEDDING_MODEL = "fake-embedding"
E5_MODEL_ID = "intfloat/multilingual-e5-small"
E5_MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
E5_MODEL_LICENSE = "MIT"
E5_MAX_SEQUENCE_LENGTH = 512

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


class E5ModelMetadata(_EmbeddingBoundaryModel):
    """已实际加载的 E5 runtime 元数据。"""

    model_id: Literal["intfloat/multilingual-e5-small"] = E5_MODEL_ID
    revision: str
    dimension: Literal[384] = EMBEDDING_DIMENSION
    max_sequence_length: Literal[512] = E5_MAX_SEQUENCE_LENGTH
    device: str


class EmbeddingInfrastructureError(RuntimeError):
    """真实模型加载或推理无法可靠完成。"""


class SentenceTransformerModel(Protocol):
    """真实 adapter 使用的最小同步模型接口。"""

    max_seq_length: int
    device: object

    def get_embedding_dimension(self) -> int | None:
        """返回模型的 sentence embedding 维度。"""
        ...

    def encode(self, inputs: list[str], **kwargs: Any) -> object:
        """同步生成一批 sentence embeddings。"""
        ...


class SentenceTransformerLoader(Protocol):
    """可注入且仅在显式加载时调用的模型工厂。"""

    def __call__(
        self,
        model_id: str,
        *,
        revision: str,
        cache_folder: str,
    ) -> SentenceTransformerModel:
        """从固定身份加载模型。"""
        ...


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


def _load_sentence_transformer(
    model_id: str,
    *,
    revision: str,
    cache_folder: str,
) -> SentenceTransformerModel:
    """延迟导入生产依赖，避免模块 import 或应用构造触发模型加载。"""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        model_id,
        revision=revision,
        cache_folder=cache_folder,
        trust_remote_code=False,
    )


class E5Embedding:
    """固定 multilingual-e5-small 身份的真实异步 Embedding adapter。"""

    def __init__(
        self,
        *,
        cache_folder: Path,
        batch_size: int = 16,
        model_loader: SentenceTransformerLoader | None = None,
    ) -> None:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise TypeError("batch_size 必须是整数")
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")
        self._cache_folder = cache_folder
        self._batch_size = batch_size
        self._model_loader = model_loader or _load_sentence_transformer
        self._model: SentenceTransformerModel | None = None
        self._metadata: E5ModelMetadata | None = None
        self._load_task: asyncio.Task[E5ModelMetadata] | None = None
        self._load_lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        """返回固定模型是否已成功加载并通过契约校验。"""
        return self._model is not None

    async def load(self, timeout_seconds: float) -> E5ModelMetadata:
        """并发安全地加载一次模型；timeout 不启动第二个后台加载。"""
        validated_timeout = _validate_timeout(timeout_seconds)
        async with self._load_lock:
            if self._metadata is not None:
                return self._metadata
            if self._load_task is None:
                self._load_task = asyncio.create_task(self._load_once())
            load_task = self._load_task

        try:
            async with asyncio.timeout(validated_timeout):
                return await asyncio.shield(load_task)
        except TimeoutError:
            raise EmbeddingInfrastructureError(
                "Embedding model load timed out"
            ) from None
        except OSError:
            await self._forget_failed_task(load_task)
            raise EmbeddingInfrastructureError("Embedding model load failed") from None
        except BaseException:
            await self._forget_failed_task(load_task)
            raise

    async def embed(
        self,
        request: EmbeddingRequest,
        timeout_seconds: float,
    ) -> EmbeddingResponse:
        """在线程桥接与短 timeout 内生成 normalized 384 维向量。"""
        validated_timeout = _validate_timeout(timeout_seconds)
        await self.load(validated_timeout)
        model = self._model
        if model is None:
            raise EmbeddingInfrastructureError("Embedding model is unavailable")

        try:
            async with asyncio.timeout(validated_timeout):
                raw_vectors = await asyncio.to_thread(
                    model.encode,
                    list(request.model_inputs),
                    batch_size=self._batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
        except TimeoutError:
            raise EmbeddingInfrastructureError(
                "Embedding inference timed out"
            ) from None
        except OSError:
            raise EmbeddingInfrastructureError("Embedding inference failed") from None

        try:
            vectors = _coerce_normalized_vectors(raw_vectors, len(request.texts))
            return EmbeddingResponse(
                model=f"{E5_MODEL_ID}@{E5_MODEL_REVISION}",
                dimension=EMBEDDING_DIMENSION,
                vectors=vectors,
                input_count=len(request.texts),
            )
        except (TypeError, ValueError) as error:
            raise EmbeddingInfrastructureError(
                "Embedding model returned malformed vectors"
            ) from error

    async def _load_once(self) -> E5ModelMetadata:
        model = await asyncio.to_thread(
            self._model_loader,
            E5_MODEL_ID,
            revision=E5_MODEL_REVISION,
            cache_folder=str(self._cache_folder),
        )
        dimension = model.get_embedding_dimension()
        if dimension != EMBEDDING_DIMENSION:
            raise EmbeddingInfrastructureError(
                "Embedding model dimension does not match contract"
            )
        if model.max_seq_length != E5_MAX_SEQUENCE_LENGTH:
            raise EmbeddingInfrastructureError(
                "Embedding model sequence length does not match contract"
            )
        device = str(model.device)
        if not device.strip():
            raise EmbeddingInfrastructureError("Embedding model device is unavailable")
        metadata = E5ModelMetadata(
            revision=E5_MODEL_REVISION,
            device=device,
        )
        async with self._load_lock:
            self._model = model
            self._metadata = metadata
            self._load_task = None
        return metadata

    async def _forget_failed_task(
        self,
        task: asyncio.Task[E5ModelMetadata],
    ) -> None:
        async with self._load_lock:
            if self._load_task is task and task.done():
                self._load_task = None


def _coerce_normalized_vectors(
    raw_vectors: object,
    expected_count: int,
) -> tuple[EmbeddingVector, ...]:
    """把 numpy/sequence 输出收敛为严格、单位范数的 Python float tuple。"""
    serializable = (
        raw_vectors.tolist() if hasattr(raw_vectors, "tolist") else raw_vectors
    )
    if not isinstance(serializable, (list, tuple)):
        raise TypeError("Embedding output must be a sequence")
    if len(serializable) != expected_count:
        raise ValueError("Embedding output count does not match input")

    vectors: list[EmbeddingVector] = []
    for raw_vector in serializable:
        if not isinstance(raw_vector, (list, tuple)):
            raise TypeError("Embedding vector must be a sequence")
        vector = tuple(float(value) for value in raw_vector)
        if len(vector) != EMBEDDING_DIMENSION:
            raise ValueError("Embedding vector dimension does not match contract")
        if any(not math.isfinite(value) for value in vector):
            raise ValueError("Embedding vector contains non-finite values")
        norm = math.sqrt(sum(value * value for value in vector))
        if not math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5):
            raise ValueError("Embedding vector is not normalized")
        vectors.append(vector)
    return tuple(vectors)
