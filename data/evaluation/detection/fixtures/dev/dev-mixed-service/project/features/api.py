"""直接 import service，但不直接 import models。"""

import external.models
import models
from another_lib import models as external_models

from .. import service


def create(raw: str):
    return service.load_user(raw)


def external_name() -> str:
    return external_models.__name__


def unrelated_module_name() -> str:
    return models.__name__


API_KIND = "one-hop"
DEFAULT_RAW = "safe"


def api_metadata() -> dict[str, str]:
    return {"kind": API_KIND, "default": DEFAULT_RAW}


def external_metadata() -> str:
    return external.models.__name__


API_VARIANT = "strict-one-hop"
__all__ = ["create"]
