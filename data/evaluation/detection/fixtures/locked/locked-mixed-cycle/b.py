"""Cycle B：validator direct finding，并直接 import A。"""

import a
from pydantic import validator as legacy_validator


@legacy_validator("name")
def normalize_name(value: str) -> str:
    return value.strip()


def a_name() -> str:
    return a.__name__


class OrdinaryValidator:
    def validator(self, value: str) -> str:
        return value


ordinary = OrdinaryValidator()


NODE_KIND = "cycle-b"
DEFAULT_NAME = "b"


def metadata() -> dict[str, str]:
    return {
        "kind": NODE_KIND,
        "name": DEFAULT_NAME,
    }


__all__ = ["normalize_name", "a_name"]
