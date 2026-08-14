from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_have_offline_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.llm_backend == "fake"
    assert settings.sqlite_path == Path("var/data/migrationlens.sqlite3")
    assert settings.sqlite_timeout_seconds == 2.0
    assert settings.readiness_timeout_seconds == 1.0
    assert str(settings.qdrant_url) == "http://127.0.0.1:6333/"
    assert settings.qdrant_collection_name == "migrationlens-documents"
    assert settings.qdrant_timeout_seconds == 2
    assert settings.embedding_cache_path == Path("var/cache/huggingface")
    assert settings.embedding_batch_size == 16
    assert settings.embedding_timeout_seconds == 120.0
    assert settings.rrf_k == 60


def test_settings_read_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIGRATIONLENS_ENVIRONMENT", "test")
    monkeypatch.setenv("MIGRATIONLENS_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MIGRATIONLENS_LLM_BACKEND", "fake")
    monkeypatch.setenv("MIGRATIONLENS_SQLITE_PATH", "var/test/custom.sqlite3")
    monkeypatch.setenv("MIGRATIONLENS_SQLITE_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("MIGRATIONLENS_READINESS_TIMEOUT_SECONDS", "0.75")
    monkeypatch.setenv("MIGRATIONLENS_QDRANT_URL", "http://qdrant.test:6333")
    monkeypatch.setenv("MIGRATIONLENS_QDRANT_COLLECTION_NAME", "migrationlens-test")
    monkeypatch.setenv("MIGRATIONLENS_QDRANT_TIMEOUT_SECONDS", "4")
    monkeypatch.setenv("MIGRATIONLENS_EMBEDDING_CACHE_PATH", "var/test/hf-cache")
    monkeypatch.setenv("MIGRATIONLENS_EMBEDDING_BATCH_SIZE", "8")
    monkeypatch.setenv("MIGRATIONLENS_EMBEDDING_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("MIGRATIONLENS_RRF_K", "40")

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.llm_backend == "fake"
    assert settings.sqlite_path == Path("var/test/custom.sqlite3")
    assert settings.sqlite_timeout_seconds == 3.5
    assert settings.readiness_timeout_seconds == 0.75
    assert str(settings.qdrant_url) == "http://qdrant.test:6333/"
    assert settings.qdrant_collection_name == "migrationlens-test"
    assert settings.qdrant_timeout_seconds == 4
    assert settings.embedding_cache_path == Path("var/test/hf-cache")
    assert settings.embedding_batch_size == 8
    assert settings.embedding_timeout_seconds == 180.0
    assert settings.rrf_k == 40


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("environment", "staging"),
        ("log_level", "TRACE"),
        ("llm_backend", "openai"),
    ],
)
def test_settings_reject_invalid_day_one_values(
    field: str,
    invalid_value: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: invalid_value})


@pytest.mark.parametrize(
    "invalid_timeout",
    [0, -1, 30.1, float("nan"), float("inf"), float("-inf")],
)
def test_settings_reject_invalid_sqlite_timeout(invalid_timeout: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, sqlite_timeout_seconds=invalid_timeout)


def test_settings_reject_blank_sqlite_path() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, sqlite_path="   ")


def test_settings_accept_sqlite_timeout_upper_boundary() -> None:
    settings = Settings(_env_file=None, sqlite_timeout_seconds=30.0)

    assert settings.sqlite_timeout_seconds == 30.0


@pytest.mark.parametrize(
    "invalid_timeout",
    [0, -1, 5.1, float("nan"), float("inf"), float("-inf")],
)
def test_settings_reject_invalid_readiness_timeout(
    invalid_timeout: float,
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, readiness_timeout_seconds=invalid_timeout)


def test_settings_accept_readiness_timeout_upper_boundary() -> None:
    settings = Settings(_env_file=None, readiness_timeout_seconds=5.0)

    assert settings.readiness_timeout_seconds == 5.0


@pytest.mark.parametrize(
    "invalid_timeout",
    [0, -1, 31, 1.5, float("nan"), float("inf"), float("-inf")],
)
def test_settings_reject_invalid_qdrant_timeout(invalid_timeout: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, qdrant_timeout_seconds=invalid_timeout)


def test_settings_accept_qdrant_timeout_upper_boundary() -> None:
    settings = Settings(_env_file=None, qdrant_timeout_seconds=30)

    assert settings.qdrant_timeout_seconds == 30


@pytest.mark.parametrize(
    "invalid_collection_name",
    ["", " leading", "slash/name", "name with spaces", "x" * 256],
)
def test_settings_reject_invalid_qdrant_collection_name(
    invalid_collection_name: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, qdrant_collection_name=invalid_collection_name)


@pytest.mark.parametrize("invalid_url", ["", "localhost:6333", "file:///tmp/qdrant"])
def test_settings_reject_invalid_qdrant_url(invalid_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, qdrant_url=invalid_url)


@pytest.mark.parametrize("invalid_batch_size", [0, -1, 129, 1.5, True])
def test_settings_reject_invalid_embedding_batch_size(
    invalid_batch_size: object,
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embedding_batch_size=invalid_batch_size)


@pytest.mark.parametrize(
    "invalid_timeout",
    [0, -1, 600.1, float("nan"), float("inf"), float("-inf")],
)
def test_settings_reject_invalid_embedding_timeout(invalid_timeout: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embedding_timeout_seconds=invalid_timeout)


def test_settings_reject_blank_embedding_cache_path() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embedding_cache_path="   ")


@pytest.mark.parametrize("invalid_rrf_k", [0, -1, 1001, 1.5, True])
def test_settings_reject_invalid_rrf_k(invalid_rrf_k: object) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rrf_k=invalid_rrf_k)
