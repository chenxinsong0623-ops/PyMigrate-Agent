"""Module alias config 与 Field direct alias 的 mixed direct module。"""

import pydantic as pd
from pydantic import Field as PField


class Record(pd.BaseModel):
    class Config:
        schema_extra = {"example": {"code": "A"}}

    code: str


token = PField(regex="^[A-Z]+$")


class Ordinary:
    class Config:
        schema_extra = {"ignored": True}


def ordinary_dict(value: object) -> dict[str, object]:
    return value.dict()  # type: ignore[attr-defined]


DEFAULT_CODE = "A"
MODULE_KIND = "alias-mixed"


def metadata() -> dict[str, str]:
    return {"code": DEFAULT_CODE, "kind": MODULE_KIND}


__all__ = ["Record", "token"]
