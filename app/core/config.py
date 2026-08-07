"""经过校验的应用配置。"""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
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
    sqlite_path: Path = Path("var/data/migrationlens.sqlite3")
    sqlite_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    readiness_timeout_seconds: float = Field(default=1.0, gt=0, le=5)

    @field_validator("sqlite_path", mode="before")
    @classmethod
    def reject_empty_sqlite_path(cls, value: object) -> object:
        """拒绝空白的 SQLite 数据库路径。"""
        if isinstance(value, str) and not value.strip():
            raise ValueError("SQLite 数据库路径不能为空")
        return value
