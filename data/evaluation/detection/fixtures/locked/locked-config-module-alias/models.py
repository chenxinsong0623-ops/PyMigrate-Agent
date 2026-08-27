"""通过 pydantic module alias 证明的配置样本。"""

import pydantic as validation


class Product(validation.BaseModel):
    class Config:
        schema_extra = {"example": {"sku": "P-1"}}

    sku: str
    price: float


class OrdinaryProduct:
    class Config:
        schema_extra = {"not": "pydantic"}


def product_key(product: Product) -> str:
    return product.sku


DEFAULT_SKU = "P-1"
DEFAULT_PRICE = 1.0


def defaults() -> dict[str, object]:
    return {"sku": DEFAULT_SKU, "price": DEFAULT_PRICE}


__all__ = ["Product"]
