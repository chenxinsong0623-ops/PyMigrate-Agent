"""已证明父类之后的本地继承配置样本。"""

from pydantic import BaseModel as BM


class NamedModel(BM):
    name: str


class Customer(NamedModel):
    class Config:
        allow_population_by_field_name = True

    customer_id: int


class FutureParent(UnknownBase):  # noqa: F821
    class Config:
        orm_mode = True


def display(customer: Customer) -> str:
    return customer.name


CUSTOMER_KIND = "named"


def customer_metadata() -> dict[str, str]:
    return {"kind": CUSTOMER_KIND}


__all__ = ["Customer", "NamedModel"]
