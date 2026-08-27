"""同时含 Config、旧 key 与根模型的 direct affected module。"""

from pydantic import BaseModel

from . import service


class User(BaseModel):
    class Config:
        orm_mode = True

    __root__: str


def label(user: User) -> str:
    return "user"


class Audit:
    user: User
    action: str


def build_user(value: str) -> User:
    return User(__root__=value)


MODEL_KIND = "root-with-config"
DEFAULT_VALUE = "safe"


def describe() -> dict[str, str]:
    return {"kind": MODEL_KIND, "default": DEFAULT_VALUE}


__all__ = ["User", "Audit", "build_user"]
MODEL_VARIANT = "cycle-target"
CYCLE_SERVICE_MODULE = service.__name__
