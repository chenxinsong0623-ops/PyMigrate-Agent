"""根模型正式 DEV 样本；只读取 AST。"""

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


ROOT_VARIANT = "annotation-assignment-inheritance"


__all__ = ["Pets", "PetMapping", "DerivedPets"]


DEFAULT_KIND = "pets"
