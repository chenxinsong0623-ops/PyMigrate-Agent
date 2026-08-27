"""BaseModel method 与多个 Field keyword 的 direct module。"""

from pydantic import BaseModel, Field


class Item(BaseModel):
    name: str = Field(regex="^[a-z]+$")
    tags: list[str] = Field(min_items=1)


def export_item(item: Item) -> dict[str, object]:
    return item.dict()


class OrdinaryItem:
    def dict(self) -> dict[str, object]:
        return {}


ordinary = OrdinaryItem()
ordinary.dict()


ITEM_KIND = "method-field"
DEFAULT_NAME = "sample"


def metadata() -> dict[str, str]:
    return {"kind": ITEM_KIND, "name": DEFAULT_NAME}


__all__ = ["Item", "export_item"]
