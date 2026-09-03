from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_pytest_disables_local_dotenv_loading() -> None:
    assert Settings.model_config["env_file"] is None


def test_settings_have_offline_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.llm_backend == "fake"
    assert settings.llm_base_url is None
    assert settings.llm_model is None
    assert settings.llm_api_key is None
    assert settings.llm_max_output_tokens == 2048
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
    monkeypatch.setenv("MIGRATIONLENS_LLM_MAX_OUTPUT_TOKENS", "1024")
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
    assert settings.llm_max_output_tokens == 1024
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


def test_fake_backend_does_not_require_real_provider_configuration() -> None:
    settings = Settings(_env_file=None, llm_backend="fake")

    assert settings.llm_api_key is None


@pytest.mark.parametrize(
    "values",
    [
        {"llm_model": "provider-model", "llm_api_key": "secret"},
        {"llm_base_url": "https://provider.example/v1", "llm_api_key": "secret"},
        {"llm_base_url": "https://provider.example/v1", "llm_model": "model"},
    ],
)
def test_real_backend_requires_base_url_model_and_api_key(
    values: dict[str, str],
) -> None:
    with pytest.raises(ValidationError, match="真实 LLM 配置不完整"):
        Settings(_env_file=None, llm_backend="openai_compatible", **values)


def test_real_backend_uses_secret_type_and_redacts_repr() -> None:
    secret = "unit-test-real-api-secret"
    settings = Settings(
        _env_file=None,
        llm_backend="openai_compatible",
        llm_base_url="https://provider.example/v1",
        llm_model="provider-model",
        llm_api_key=secret,
    )

    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == secret
    assert secret not in repr(settings)
    assert secret not in str(settings.model_dump())


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@provider.example/v1",
        "https://provider.example/v1?api_key=secret",
        "https://provider.example/v1#fragment",
    ],
)
def test_real_backend_rejects_secret_bearing_base_url(url: str) -> None:
    with pytest.raises(ValidationError, match="LLM base URL"):
        Settings(
            _env_file=None,
            llm_backend="openai_compatible",
            llm_base_url=url,
            llm_model="provider-model",
            llm_api_key="secret",
        )
