"""经过校验的应用配置。"""

from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LLMBackend = Literal["fake", "openai_compatible"]


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
    llm_base_url: HttpUrl | None = None
    llm_model: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$",
    )
    llm_api_key: SecretStr | None = None
    llm_max_output_tokens: int = Field(default=2048, gt=0, le=16384)
    sqlite_path: Path = Path("var/data/migrationlens.sqlite3")
    sqlite_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    readiness_timeout_seconds: float = Field(default=1.0, gt=0, le=5)
    qdrant_url: HttpUrl = HttpUrl("http://127.0.0.1:6333")
    qdrant_collection_name: str = Field(
        default="migrationlens-documents",
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$",
    )
    qdrant_timeout_seconds: int = Field(default=2, gt=0, le=30)
    embedding_cache_path: Path = Path("var/cache/huggingface")
    embedding_batch_size: int = Field(default=16, gt=0, le=128)
    embedding_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    rrf_k: int = Field(default=60, gt=0, le=1000)

    @field_validator("sqlite_path", mode="before")
    @classmethod
    def reject_empty_sqlite_path(cls, value: object) -> object:
        """拒绝空白的 SQLite 数据库路径。"""
        if isinstance(value, str) and not value.strip():
            raise ValueError("SQLite 数据库路径不能为空")
        return value

    @field_validator("embedding_cache_path", mode="before")
    @classmethod
    def reject_empty_embedding_cache_path(cls, value: object) -> object:
        """拒绝空白模型 cache 路径。"""
        if isinstance(value, str) and not value.strip():
            raise ValueError("Embedding cache 路径不能为空")
        return value

    @field_validator(
        "embedding_batch_size",
        "rrf_k",
        "llm_max_output_tokens",
        mode="before",
    )
    @classmethod
    def reject_boolean_integer_settings(cls, value: object) -> object:
        """允许环境变量数字文本，但拒绝 bool 被当作整数 1。"""
        if isinstance(value, bool):
            raise ValueError("整数配置不得使用 bool")
        return value

    @model_validator(mode="after")
    def validate_llm_backend_configuration(self) -> "Settings":
        """真实 backend 缺少任一必要配置时 fail closed。"""
        if self.llm_backend == "fake":
            return self
        if self.llm_base_url is None or self.llm_model is None:
            raise ValueError("真实 LLM 配置不完整")
        if self.llm_api_key is None or not self.llm_api_key.get_secret_value().strip():
            raise ValueError("真实 LLM 配置不完整")
        if (
            self.llm_base_url.query is not None
            or self.llm_base_url.fragment is not None
            or self.llm_base_url.username is not None
            or self.llm_base_url.password is not None
        ):
            raise ValueError("LLM base URL 不得包含凭据、query 或 fragment")
        return self
