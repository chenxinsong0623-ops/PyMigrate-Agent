"""Transitive target：Config 与 root direct findings。"""

from pydantic import BaseModel


class Identifier(BaseModel):
    class Config:
        orm_mode = True

    __root__: str


class OrdinaryIdentifier:
    __root__: str


def identifier_kind() -> str:
    return Identifier.__name__


MODEL_KIND = "transitive-target"
DEFAULT_VALUE = "id-1"


def metadata() -> dict[str, str]:
    return {
        "kind": MODEL_KIND,
        "value": DEFAULT_VALUE,
    }


__all__ = ["Identifier"]


SAFE_NOTE = "api does not import this module directly"
