"""已证明本地继承下的根模型样本。"""

from pydantic import BaseModel


class RootBase(BaseModel):
    label: str = "values"


class IntegerMap(RootBase):
    __root__ = dict[str, int]


class LaterParent(BaseModel):
    pass


class Ordinary:
    __root__ = "not a model"


def model_label(model: IntegerMap) -> str:
    return model.label


ROOT_KIND = "local-inheritance"


def metadata() -> dict[str, str]:
    return {"kind": ROOT_KIND}


__all__ = ["IntegerMap", "RootBase"]
