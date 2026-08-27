"""模块路径相似但不属于 Pydantic 的 import provenance 负例。"""

from my_pydantic import BaseSettings  # noqa: I001
from my_pydantic import Field
from my_pydantic.generics import GenericModel


class AppSettings(BaseSettings):
    value: str


class Box(GenericModel):
    value: object


token = Field(regex="^[a-z]+$", unique_items=True)


class Config:
    orm_mode = True


def settings_value(settings: AppSettings) -> str:
    return settings.value


IMPORT_KIND = "similar-module-name"


def metadata() -> dict[str, str]:
    return {"kind": IMPORT_KIND}


__all__ = ["AppSettings", "Box", "token"]
