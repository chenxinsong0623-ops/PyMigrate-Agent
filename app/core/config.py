"""经过校验的应用配置。"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LLMBackend = Literal["fake"]


class Settings(BaseSettings):
    """从环境变量或 ``.env`` 加载 MigrationLens 配置。"""

    model_config = SettingsConfigDict(
        env_prefix="MIGRATIONLENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    environment: Environment = "development"
    log_level: LogLevel = "INFO"
    llm_backend: LLMBackend = "fake"
