"""直接 import model，且自身含 Field direct finding。"""

import model  # noqa: I001
from pydantic import Field


identifier_pattern = Field(regex="^id-[0-9]+$")


def identifier_type() -> str:
    return model.Identifier.__name__


def default_value() -> str:
    return model.DEFAULT_VALUE


SERVICE_KIND = "direct-importer"
SERVICE_MODE = "read-only"


def metadata() -> dict[str, str]:
    return {
        "kind": SERVICE_KIND,
        "mode": SERVICE_MODE,
    }


class IdentifierService:
    def describe(self) -> str:
        return identifier_type()


__all__ = ["IdentifierService", "identifier_pattern"]
