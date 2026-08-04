import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_have_offline_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.llm_backend == "fake"


def test_settings_read_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIGRATIONLENS_ENVIRONMENT", "test")
    monkeypatch.setenv("MIGRATIONLENS_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MIGRATIONLENS_LLM_BACKEND", "fake")

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.llm_backend == "fake"


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
