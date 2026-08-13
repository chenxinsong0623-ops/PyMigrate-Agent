"""Qdrant 集合生命周期、文档 point 写入和 dense query 边界。"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ApiException

from app.core.config import Settings
from app.core.embedding import EMBEDDING_DIMENSION

LOGGER = logging.getLogger(__name__)
QDRANT_BACKEND_NAME = "qdrant"

_ResultT = TypeVar("_ResultT")


class QdrantDistance(StrEnum):
    """Qdrant 当前公开支持的向量距离类型。"""

    COSINE = "cosine"
    EUCLID = "euclid"
    DOT = "dot"
    MANHATTAN = "manhattan"


@dataclass(frozen=True, slots=True)
class QdrantCollectionConfig:
    """MigrationLens 关心的最小集合配置。"""

    vector_size: int
    distance: QdrantDistance


class QdrantInfrastructureError(Exception):
    """可安全转换为基础设施不可用的 Qdrant 客户端错误。"""


class QdrantCollectionConfigurationError(Exception):
    """已有集合不满足 MigrationLens 固定向量契约。"""


class QdrantPayloadError(Exception):
    """Qdrant 返回的 point 或 payload 不满足项目内严格契约。"""


class _QdrantBoundaryModel(BaseModel):
    """Qdrant 业务边界使用的严格不可变模型。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class QdrantPointPayload(_QdrantBoundaryModel):
    """从 Day 9 chunk 完整映射的文档 point payload。"""

    chunk_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    heading_path: tuple[str, ...]
    text: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: Literal["pydantic-v2-migration"]
    source_url: str = Field(min_length=1)
    git_ref: str = Field(min_length=1)
    resolved_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_path: Literal["docs/migration.md"]
    source_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_start_char: int = Field(ge=0)
    source_end_char: int = Field(gt=0)
    continuation_index: int = Field(ge=0)
    overlap_chars: int = Field(ge=0, le=150)
    identity_occurrence: int = Field(ge=0)
    embedding_model: Literal["intfloat/multilingual-e5-small"]
    embedding_revision: str = Field(pattern=r"^[0-9a-f]{40}$")


class QdrantPoint(_QdrantBoundaryModel):
    """与官方 client 类型隔离的单个 Qdrant 写入 point。"""

    point_id: str
    vector: tuple[float, ...]
    payload: QdrantPointPayload

    @field_validator("point_id")
    @classmethod
    def validate_point_id(cls, point_id: str) -> str:
        """P0 固定使用规范化 UUID 字符串，不允许任意 chunk ID。"""
        try:
            normalized = str(UUID(point_id))
        except (ValueError, AttributeError, TypeError):
            raise ValueError("Qdrant point_id 必须是 UUID") from None
        if normalized != point_id:
            raise ValueError("Qdrant point_id 必须是规范化 UUID")
        return point_id

    @field_validator("vector")
    @classmethod
    def validate_vector(cls, vector: tuple[float, ...]) -> tuple[float, ...]:
        if len(vector) != EMBEDDING_DIMENSION:
            raise ValueError("Qdrant point vector 必须为 384 维")
        if any(not math.isfinite(value) for value in vector):
            raise ValueError("Qdrant point vector 只能包含有限 float")
        return vector


class QdrantScoredPoint(_QdrantBoundaryModel):
    """Qdrant dense query 返回的严格 point。"""

    point_id: str
    score: float
    payload: QdrantPointPayload

    @field_validator("point_id")
    @classmethod
    def validate_point_id(cls, point_id: str) -> str:
        try:
            normalized = str(UUID(point_id))
        except (ValueError, AttributeError, TypeError):
            raise ValueError("Qdrant scored point_id 必须是 UUID") from None
        if normalized != point_id:
            raise ValueError("Qdrant scored point_id 必须是规范化 UUID")
        return point_id

    @field_validator("score")
    @classmethod
    def validate_score(cls, score: float) -> float:
        if not math.isfinite(score):
            raise ValueError("Qdrant score 必须是有限数值")
        return score


@runtime_checkable
class QdrantClientProtocol(Protocol):
    """QdrantBackend 所依赖的最小异步客户端能力。"""

    async def collection_exists(self, collection_name: str) -> bool:
        """返回集合是否存在。"""
        ...

    async def get_collection_config(
        self,
        collection_name: str,
    ) -> QdrantCollectionConfig:
        """读取已有集合的向量配置。"""
        ...

    async def create_collection(
        self,
        collection_name: str,
        config: QdrantCollectionConfig,
    ) -> None:
        """创建一个不存在的集合。"""
        ...

    async def upsert_points(
        self,
        collection_name: str,
        points: tuple[QdrantPoint, ...],
    ) -> None:
        """等待一批文档 points 完成写入。"""
        ...

    async def query_points(
        self,
        collection_name: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[QdrantScoredPoint, ...]:
        """执行 dense query 并返回 payload。"""
        ...

    async def count_points(self, collection_name: str, source_id: str) -> int:
        """精确统计一个 source 的文档 points。"""
        ...

    async def source_point_ids(
        self,
        collection_name: str,
        source_id: str,
    ) -> frozenset[str]:
        """读取一个 source 当前全部 point IDs。"""
        ...

    async def ping(self) -> bool:
        """检查 Qdrant 服务是否可访问。"""
        ...

    async def close(self) -> None:
        """关闭底层异步客户端。"""
        ...


class QdrantClientAdapter:
    """将 qdrant-client 的公开异步 API 适配为项目内最小协议。"""

    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def collection_exists(self, collection_name: str) -> bool:
        """通过公开 API 判断集合是否存在。"""
        try:
            return await self._client.collection_exists(collection_name)
        except ApiException:
            raise QdrantInfrastructureError("Qdrant collection check failed") from None

    async def get_collection_config(
        self,
        collection_name: str,
    ) -> QdrantCollectionConfig:
        """读取未命名向量集合的维度和距离配置。"""
        try:
            info = await self._client.get_collection(collection_name)
        except ApiException:
            raise QdrantInfrastructureError("Qdrant collection read failed") from None

        vectors = info.config.params.vectors
        if not isinstance(vectors, models.VectorParams):
            raise QdrantCollectionConfigurationError(
                "MigrationLens requires one unnamed vector"
            )

        try:
            distance = QdrantDistance(vectors.distance.value.casefold())
        except (AttributeError, ValueError):
            raise QdrantCollectionConfigurationError(
                "Qdrant collection uses an unsupported distance"
            ) from None

        return QdrantCollectionConfig(
            vector_size=vectors.size,
            distance=distance,
        )

    async def create_collection(
        self,
        collection_name: str,
        config: QdrantCollectionConfig,
    ) -> None:
        """使用显式向量配置创建集合。"""
        distance = models.Distance(config.distance.value.capitalize())
        try:
            created = await self._client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=config.vector_size,
                    distance=distance,
                ),
            )
        except ApiException:
            raise QdrantInfrastructureError("Qdrant collection create failed") from None
        if not created:
            raise QdrantInfrastructureError("Qdrant collection was not created")

    async def upsert_points(
        self,
        collection_name: str,
        points: tuple[QdrantPoint, ...],
    ) -> None:
        """使用公开 upsert API，并等待 Server 报告完成。"""
        raw_points = [
            models.PointStruct(
                id=point.point_id,
                vector=list(point.vector),
                payload=point.payload.model_dump(mode="json"),
            )
            for point in points
        ]
        try:
            result = await self._client.upsert(
                collection_name=collection_name,
                points=raw_points,
                wait=True,
            )
        except ApiException:
            raise QdrantInfrastructureError("Qdrant point upsert failed") from None
        if result.status is not models.UpdateStatus.COMPLETED:
            raise QdrantInfrastructureError("Qdrant point upsert was not completed")

    async def query_points(
        self,
        collection_name: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[QdrantScoredPoint, ...]:
        """使用公开 query_points API 返回不含 vectors 的 typed points。"""
        try:
            response = await self._client.query_points(
                collection_name=collection_name,
                query=list(vector),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except ApiException:
            raise QdrantInfrastructureError("Qdrant dense query failed") from None

        results: list[QdrantScoredPoint] = []
        try:
            for point in response.points:
                if point.payload is None:
                    raise ValueError("missing payload")
                results.append(
                    QdrantScoredPoint(
                        point_id=str(point.id),
                        score=float(point.score),
                        payload=QdrantPointPayload.model_validate(point.payload),
                    )
                )
        except (AttributeError, TypeError, ValueError, ValidationError):
            raise QdrantPayloadError(
                "Qdrant dense query returned malformed payload"
            ) from None
        return tuple(results)

    async def count_points(self, collection_name: str, source_id: str) -> int:
        """使用精确 filter count 验证当前 source point 数量。"""
        try:
            result = await self._client.count(
                collection_name=collection_name,
                count_filter=_source_filter(source_id),
                exact=True,
            )
        except ApiException:
            raise QdrantInfrastructureError("Qdrant point count failed") from None
        if isinstance(result.count, bool) or result.count < 0:
            raise QdrantPayloadError("Qdrant point count is malformed")
        return result.count

    async def source_point_ids(
        self,
        collection_name: str,
        source_id: str,
    ) -> frozenset[str]:
        """分页 scroll 当前 source 的规范化 UUID point IDs。"""
        ids: set[str] = set()
        offset: Any = None
        while True:
            try:
                records, next_offset = await self._client.scroll(
                    collection_name=collection_name,
                    scroll_filter=_source_filter(source_id),
                    limit=256,
                    offset=offset,
                    with_payload=False,
                    with_vectors=False,
                )
            except ApiException:
                raise QdrantInfrastructureError("Qdrant point scroll failed") from None
            try:
                for record in records:
                    point_id = str(UUID(str(record.id)))
                    ids.add(point_id)
            except (AttributeError, TypeError, ValueError):
                raise QdrantPayloadError("Qdrant point ID is malformed") from None
            if next_offset is None:
                return frozenset(ids)
            if next_offset == offset:
                raise QdrantPayloadError("Qdrant scroll did not advance")
            offset = next_offset

    async def ping(self) -> bool:
        """通过公开集合列表 API 检查服务可访问性。"""
        try:
            await self._client.get_collections()
        except ApiException:
            raise QdrantInfrastructureError("Qdrant ping failed") from None
        return True

    async def close(self) -> None:
        """关闭官方异步客户端。"""
        try:
            await self._client.close()
        except ApiException:
            raise QdrantInfrastructureError("Qdrant close failed") from None


class QdrantBackendState(StrEnum):
    """QdrantBackend 的单向生命周期状态。"""

    NEW = "new"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    FAILED = "failed"
    CLOSED = "closed"


class QdrantBackend:
    """管理一个 Qdrant 客户端及 MigrationLens 文档集合的生命周期。"""

    backend_name = QDRANT_BACKEND_NAME

    def __init__(
        self,
        client: QdrantClientProtocol,
        collection_name: str,
        timeout_seconds: float,
    ) -> None:
        if not collection_name.strip():
            raise ValueError("collection_name 不能为空")
        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds, (int, float)
        ):
            raise TypeError("timeout_seconds 必须为数值")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须为正的有限数值")

        self._client = client
        self._collection_name = collection_name
        self._timeout_seconds = float(timeout_seconds)
        self._expected_config = QdrantCollectionConfig(
            vector_size=EMBEDDING_DIMENSION,
            distance=QdrantDistance.COSINE,
        )
        self._state = QdrantBackendState.NEW
        self._client_closed = False
        self._lifecycle_lock = asyncio.Lock()

    @property
    def state(self) -> QdrantBackendState:
        """返回当前生命周期状态。"""
        return self._state

    async def initialize(self) -> bool:
        """创建或验证集合；预期基础设施失败时返回 False。"""
        async with self._lifecycle_lock:
            if self._state is QdrantBackendState.INITIALIZED:
                return True
            if self._state in {QdrantBackendState.FAILED, QdrantBackendState.CLOSED}:
                return False

            self._state = QdrantBackendState.INITIALIZING
            try:
                exists = await self._with_timeout(
                    self._client.collection_exists(self._collection_name)
                )
                if exists:
                    actual = await self._with_timeout(
                        self._client.get_collection_config(self._collection_name)
                    )
                    if actual != self._expected_config:
                        raise QdrantCollectionConfigurationError(
                            "Qdrant collection does not match the embedding contract"
                        )
                else:
                    await self._with_timeout(
                        self._client.create_collection(
                            self._collection_name,
                            self._expected_config,
                        )
                    )
            except TimeoutError:
                self._state = QdrantBackendState.FAILED
                self._log_expected_failure("initialize", "timeout")
                await self._cleanup_after_failed_initialize()
                return False
            except (
                QdrantInfrastructureError,
                QdrantCollectionConfigurationError,
            ) as error:
                self._state = QdrantBackendState.FAILED
                self._log_expected_failure("initialize", type(error).__name__)
                await self._cleanup_after_failed_initialize()
                return False
            except BaseException:
                self._state = QdrantBackendState.FAILED
                await self._cleanup_after_failed_initialize()
                raise

            self._state = QdrantBackendState.INITIALIZED
            return True

    async def ping(self) -> bool:
        """已初始化时执行受超时保护的真实客户端探针。"""
        if self._state is not QdrantBackendState.INITIALIZED:
            return False
        try:
            return await self._with_timeout(self._client.ping())
        except TimeoutError:
            self._log_expected_failure("ping", "timeout")
            return False
        except QdrantInfrastructureError as error:
            self._log_expected_failure("ping", type(error).__name__)
            return False

    async def upsert_points(self, points: tuple[QdrantPoint, ...]) -> None:
        """向已初始化 collection 幂等写入稳定 IDs。"""
        if not points:
            raise ValueError("Qdrant upsert points 不能为空")
        await self._dense_operation(
            "upsert",
            self._client.upsert_points(self._collection_name, points),
        )

    async def query_points(
        self,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[QdrantScoredPoint, ...]:
        """执行一次 dense query；正常 0 命中返回空 tuple。"""
        _validate_query_vector(vector)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("Qdrant query limit 必须是整数")
        if limit <= 0:
            raise ValueError("Qdrant query limit 必须大于 0")
        return await self._dense_operation(
            "query",
            self._client.query_points(self._collection_name, vector, limit),
        )

    async def count_points(self, source_id: str) -> int:
        """统计当前 collection 中指定 source points。"""
        _validate_source_id(source_id)
        return await self._dense_operation(
            "count",
            self._client.count_points(self._collection_name, source_id),
        )

    async def source_point_ids(self, source_id: str) -> frozenset[str]:
        """返回当前 collection 中指定 source 的全部稳定 IDs。"""
        _validate_source_id(source_id)
        return await self._dense_operation(
            "scroll",
            self._client.source_point_ids(self._collection_name, source_id),
        )

    async def close(self) -> None:
        """最多关闭底层客户端一次，并使 backend 永久进入 closed。"""
        async with self._lifecycle_lock:
            if self._state is QdrantBackendState.CLOSED:
                return
            await self._close_client_safely("close")
            self._state = QdrantBackendState.CLOSED

    async def _with_timeout(self, operation: Awaitable[_ResultT]) -> _ResultT:
        """为每次可能阻塞的外部调用施加独立超时。"""
        async with asyncio.timeout(self._timeout_seconds):
            return await operation

    async def _dense_operation(
        self,
        operation_name: str,
        operation: Awaitable[_ResultT],
    ) -> _ResultT:
        if self._state is not QdrantBackendState.INITIALIZED:
            operation_iterator = getattr(operation, "close", None)
            if callable(operation_iterator):
                operation_iterator()
            raise QdrantInfrastructureError("Qdrant backend is not initialized")
        try:
            return await self._with_timeout(operation)
        except TimeoutError:
            raise QdrantInfrastructureError(
                f"Qdrant {operation_name} timed out"
            ) from None

    async def _cleanup_after_failed_initialize(self) -> None:
        """初始化失败后回收已拥有的客户端。"""
        await self._close_client_safely("initialize_cleanup")

    async def _close_client_safely(self, operation: str) -> None:
        """关闭客户端；仅将预期基础设施失败转换为安全日志。"""
        if self._client_closed:
            return
        self._client_closed = True
        try:
            await self._with_timeout(self._client.close())
        except TimeoutError:
            self._log_expected_failure(operation, "timeout")
        except QdrantInfrastructureError as error:
            self._log_expected_failure(operation, type(error).__name__)

    @staticmethod
    def _log_expected_failure(operation: str, error_type: str) -> None:
        """只记录白名单字段，不记录 URL、集合名或异常原文。"""
        LOGGER.warning(
            "Qdrant operation unavailable",
            extra={
                "component": QDRANT_BACKEND_NAME,
                "operation": operation,
                "error_type": error_type,
            },
        )


def build_qdrant_backend(settings: Settings) -> QdrantBackend:
    """仅构造 Qdrant 生命周期对象，不执行网络访问。"""
    raw_client = AsyncQdrantClient(
        url=str(settings.qdrant_url),
        timeout=settings.qdrant_timeout_seconds,
        prefer_grpc=False,
    )
    return QdrantBackend(
        client=QdrantClientAdapter(raw_client),
        collection_name=settings.qdrant_collection_name,
        timeout_seconds=settings.qdrant_timeout_seconds,
    )


def _source_filter(source_id: str) -> models.Filter:
    _validate_source_id(source_id)
    return models.Filter(
        must=[
            models.FieldCondition(
                key="source_id",
                match=models.MatchValue(value=source_id),
            )
        ]
    )


def _validate_source_id(source_id: str) -> None:
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id 不能为空")


def _validate_query_vector(vector: tuple[float, ...]) -> None:
    if len(vector) != EMBEDDING_DIMENSION:
        raise ValueError("Qdrant query vector 必须为 384 维")
    if any(not math.isfinite(value) for value in vector):
        raise ValueError("Qdrant query vector 只能包含有限 float")
