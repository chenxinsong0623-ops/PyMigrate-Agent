"""正确来源在 use position 前被重绑定的负例。"""

import pydantic as validation  # noqa: I001
from pydantic import Field as PField
from pydantic import validator as legacy_validator


validation = alternate_validation  # noqa: F811, F821
PField = local_field  # noqa: F811, F821
legacy_validator = local_validator  # noqa: F811, F821


class ReboundModel(validation.BaseModel):
    class Config:
        orm_mode = True


value = PField(regex="^[a-z]+$")


@legacy_validator("value")
def normalize(value: str) -> str:
    return value


def export(model):
    return model.dict()


REBIND_KIND = "all-symbols-replaced"


def metadata() -> dict[str, str]:
    return {"kind": REBIND_KIND}
