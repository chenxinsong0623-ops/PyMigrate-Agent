"""Config 与 validator 共同存在的 direct affected module。"""

import pydantic as validation


class Customer(validation.BaseModel):
    class Config:
        orm_mode = True

    name: str


@validation.validator("name")
def normalize_name(value: str) -> str:
    return value.strip()


class Ordinary:
    class Config:
        orm_mode = True


def display(customer: Customer) -> str:
    return customer.name


MODEL_KIND = "config-validator"


def metadata() -> dict[str, str]:
    return {"kind": MODEL_KIND}


__all__ = ["Customer", "normalize_name"]
