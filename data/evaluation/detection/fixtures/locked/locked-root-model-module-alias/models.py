"""Pydantic module alias 下的根模型样本。"""

import pydantic as validation


class StringList(validation.BaseModel):
    __root__: list[str]


class OrdinaryList:
    __root__: list[str]


def first_value(values: StringList) -> str | None:
    return values.__root__[0] if values.__root__ else None


DEFAULT_VALUES = ("one", "two")
ROOT_KIND = "module-alias"


def defaults() -> tuple[str, ...]:
    return DEFAULT_VALUES


def kind() -> str:
    return ROOT_KIND


__all__ = ["StringList"]


SAFE_NOTE = "ordinary same-name target remains negative"
