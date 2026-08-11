from collections.abc import Iterator

import pytest


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
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(variable, raising=False)

    yield
