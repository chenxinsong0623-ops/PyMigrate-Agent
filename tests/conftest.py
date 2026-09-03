import os
from collections.abc import Iterator

import pytest

import app.core.dependencies as dependencies_module
from app.core.config import Settings

# pytest collection 可能 import module-level FastAPI app。先用明确的测试值遮蔽本地
# ``.env``，避免 collection 读取开发者的真实 provider secret 或构造真实 client。
_COLLECTION_SAFE_LLM_ENVIRONMENT = {
    "MIGRATIONLENS_LLM_BACKEND": "fake",
    "MIGRATIONLENS_LLM_BASE_URL": "https://provider.example/v1",
    "MIGRATIONLENS_LLM_MODEL": "unit-test-model",
    "MIGRATIONLENS_LLM_API_KEY": "unit-test-secret-value",
}
os.environ.update(_COLLECTION_SAFE_LLM_ENVIRONMENT)


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
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for variable in (
        "MIGRATIONLENS_ENVIRONMENT",
        "MIGRATIONLENS_LOG_LEVEL",
        "MIGRATIONLENS_LLM_BACKEND",
        "MIGRATIONLENS_LLM_BASE_URL",
        "MIGRATIONLENS_LLM_MODEL",
        "MIGRATIONLENS_LLM_API_KEY",
        "MIGRATIONLENS_LLM_MAX_OUTPUT_TOKENS",
        "MIGRATIONLENS_REAL_LLM_LOAD_OPT_IN",
        "MIGRATIONLENS_SQLITE_PATH",
        "MIGRATIONLENS_SQLITE_TIMEOUT_SECONDS",
        "MIGRATIONLENS_READINESS_TIMEOUT_SECONDS",
        "MIGRATIONLENS_QDRANT_URL",
        "MIGRATIONLENS_QDRANT_COLLECTION_NAME",
        "MIGRATIONLENS_QDRANT_TIMEOUT_SECONDS",
        "MIGRATIONLENS_EMBEDDING_CACHE_PATH",
        "MIGRATIONLENS_EMBEDDING_BATCH_SIZE",
        "MIGRATIONLENS_EMBEDDING_TIMEOUT_SECONDS",
        "MIGRATIONLENS_RRF_K",
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
