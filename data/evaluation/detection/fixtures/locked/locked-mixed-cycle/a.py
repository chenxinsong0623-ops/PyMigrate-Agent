"""Cycle A：Config/Field direct findings，并直接 import B。"""

import b
from pydantic import BaseModel, Field


class Node(BaseModel):
    class Config:
        schema_extra = {"example": {"name": "a"}}

    name: str


token = Field(const=True)


def b_name() -> str:
    return b.__name__


NODE_KIND = "cycle-a"
DEFAULT_NAME = "a"


def metadata() -> dict[str, str]:
    return {
        "kind": NODE_KIND,
        "name": DEFAULT_NAME,
    }


__all__ = ["Node", "token"]
