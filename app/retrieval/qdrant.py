"""Qdrant 集合生命周期边界，不包含写入或检索行为。"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeVar, runtime_checkable

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
