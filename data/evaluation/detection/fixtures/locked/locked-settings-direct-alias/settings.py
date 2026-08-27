"""BaseSettings direct import alias 的迁移样本。"""

from pydantic import BaseSettings as LegacySettings


class ServiceSettings(LegacySettings):
    endpoint: str = "http://localhost"
    retries: int = 2


class OrdinarySettings:
    endpoint: str = "memory://"


def endpoint(settings: ServiceSettings) -> str:
    return settings.endpoint


DEFAULT_ENDPOINT = "http://localhost"
DEFAULT_RETRIES = 2


def defaults() -> dict[str, object]:
    return {
        "endpoint": DEFAULT_ENDPOINT,
        "retries": DEFAULT_RETRIES,
    }


SETTINGS_KIND = "direct-alias-import"


__all__ = ["ServiceSettings"]
