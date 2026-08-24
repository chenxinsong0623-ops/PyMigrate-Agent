"""Day 17 direct affected model 与 cycle candidate；绝不执行。"""

from pydantic import BaseModel

from . import service


class User(BaseModel):
    __root__: str


def label(user: User) -> str:
    return "user"


class Audit:
    user: User
    action: str


def build_user(value: str) -> User:
    return User(__root__=value)


MODEL_KIND = "root"
DEFAULT_VALUE = "safe"


def describe() -> dict[str, str]:
    return {"kind": MODEL_KIND, "default": DEFAULT_VALUE}


__all__ = ["User", "Audit", "build_user"]
MODEL_CANDIDATE_MARKER = "day17"
CYCLE_SERVICE_MODULE = service.__name__
