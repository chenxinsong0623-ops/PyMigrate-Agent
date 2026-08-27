"""BaseSettings module attribute reference 的迁移样本。"""

import pydantic as validation


class JobSettings(validation.BaseSettings):
    queue: str = "events"
    workers: int = 1


def queue_name(settings: JobSettings) -> str:
    return settings.queue


class LocalSettings:
    queue = "local"


local = LocalSettings()


DEFAULT_QUEUE = "events"
DEFAULT_WORKERS = 1


def defaults() -> tuple[str, int]:
    return DEFAULT_QUEUE, DEFAULT_WORKERS


SETTINGS_KIND = "module-reference"


__all__ = ["JobSettings"]
