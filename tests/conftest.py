from collections.abc import Iterator

import pytest

import app.core.dependencies as dependencies_module


class OfflineQdrantBackend:
    """普通 pytest 使用的离线 Qdrant 生命周期替身。"""

    backend_name = "qdrant"

    def __init__(self) -> None:
        self.initialize_calls = 0
        self.ping_calls = 0
        self.close_calls = 0
        self.initialized = False

    async def initialize(self) -> bool:
        self.initialize_calls += 1
        self.initialized = True
        return True

    async def ping(self) -> bool:
        self.ping_calls += 1
        return self.initialized

    async def close(self) -> None:
        self.close_calls += 1
        self.initialized = False


@pytest.fixture(autouse=True)
def clear_application_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """避免测试依赖开发者计算机上的凭据与配置。"""
    for variable in (
        "MIGRATIONLENS_ENVIRONMENT",
        "MIGRATIONLENS_LOG_LEVEL",
        "MIGRATIONLENS_LLM_BACKEND",
        "MIGRATIONLENS_SQLITE_PATH",
        "MIGRATIONLENS_SQLITE_TIMEOUT_SECONDS",
        "MIGRATIONLENS_READINESS_TIMEOUT_SECONDS",
        "MIGRATIONLENS_QDRANT_URL",
        "MIGRATIONLENS_QDRANT_COLLECTION_NAME",
        "MIGRATIONLENS_QDRANT_TIMEOUT_SECONDS",
        "MIGRATIONLENS_EMBEDDING_CACHE_PATH",
        "MIGRATIONLENS_EMBEDDING_BATCH_SIZE",
        "MIGRATIONLENS_EMBEDDING_TIMEOUT_SECONDS",
        "OPENAI_API_KEY",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
    ):
        monkeypatch.delenv(variable, raising=False)

    yield


@pytest.fixture(autouse=True)
def use_offline_qdrant_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """让普通测试保留完整 runtime wiring，同时不依赖真实 Qdrant server。"""
    monkeypatch.setattr(
        dependencies_module,
        "build_qdrant_backend",
        lambda _settings: OfflineQdrantBackend(),
    )
