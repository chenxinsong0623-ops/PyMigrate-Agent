"""直接 import models，并含 Pydantic Field 旧参数。"""

from pydantic import Field

import project.models as absolute_models
from project import models as package_models

from .models import User

value = Field(regex="^[a-z]+$")


def load_user(raw: str) -> User:
    return User(__root__=raw)


def absolute_name() -> str:
    return absolute_models.User.__name__


def package_name() -> str:
    return package_models.User.__name__


SERVICE_KIND = "mixed-imports"
DEFAULT_RAW = "safe"


def service_metadata() -> dict[str, str]:
    return {"kind": SERVICE_KIND, "default": DEFAULT_RAW}


__all__ = ["load_user", "value"]
SERVICE_VARIANT = "duplicate-import-edge"
