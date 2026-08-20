"""Day 15 根模型规则 candidate；只读取 AST。"""

from pydantic import BaseModel as BM


class Pets(BM):
    __root__: list[str]


class PetMapping(BM):
    __root__ = dict[str, int]


class DerivedPets(Pets):
    __root__: tuple[str, ...]


class Ordinary:
    label = "__root__"


def root_label() -> str:
    return "__root__"


ROOT_CANDIDATE_MARKER = "day15"


__all__ = ["Pets", "PetMapping", "DerivedPets"]


DEFAULT_KIND = "pets"
