"""Day 15 Settings 规则 candidate；只读取 AST。"""

import pydantic as pd
from pydantic import BaseSettings as BS


class ApplicationSettings(BS):
    service_name: str = "migrationlens"
    debug: bool = False


class WorkerSettings(pd.BaseSettings):
    queue_name: str = "default"
    retries: int = 3


def settings_name(settings: ApplicationSettings) -> str:
    return settings.service_name


DEFAULT_RETRIES = 3


def ordinary_mapping() -> dict[str, object]:
    return {"service_name": "migrationlens"}


SETTINGS_CANDIDATE_MARKER = "day15"


__all__ = ["ApplicationSettings", "WorkerSettings"]
