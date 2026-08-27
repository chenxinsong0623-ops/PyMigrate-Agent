"""直接 import domain 的 renderer。"""

from domain import Item, export_item


def render(item: Item) -> str:
    return str(export_item(item))


def item_name() -> str:
    return Item.__name__


FORMAT = "text"
ENCODING = "utf-8"


def renderer_metadata() -> dict[str, str]:
    return {
        "format": FORMAT,
        "encoding": ENCODING,
    }


class Renderer:
    def write(self, item: Item) -> str:
        return render(item)


renderer = Renderer()


__all__ = ["render", "Renderer"]
