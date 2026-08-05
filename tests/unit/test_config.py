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


def test_settings_read_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIGRATIONLENS_ENVIRONMENT", "test")
    monkeypatch.setenv("MIGRATIONLENS_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MIGRATIONLENS_LLM_BACKEND", "fake")
    monkeypatch.setenv("MIGRATIONLENS_SQLITE_PATH", "var/test/custom.sqlite3")
    monkeypatch.setenv("MIGRATIONLENS_SQLITE_TIMEOUT_SECONDS", "3.5")

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.llm_backend == "fake"
    assert settings.sqlite_path == Path("var/test/custom.sqlite3")
    assert settings.sqlite_timeout_seconds == 3.5


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
