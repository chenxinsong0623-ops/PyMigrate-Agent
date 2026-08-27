"""GenericModel direct alias import 与 base reference 样本。"""

from pydantic.generics import GenericModel as LegacyGeneric


class Page(LegacyGeneric):
    items: list[object]
    total: int


def page_size(page: Page) -> int:
    return len(page.items)


class LocalGeneric:
    items: list[object]


DEFAULT_TOTAL = 0
GENERIC_KIND = "direct-alias"


def empty_page() -> dict[str, object]:
    return {
        "items": [],
        "total": DEFAULT_TOTAL,
    }


__all__ = ["Page"]


SAFE_NOTE = "import and base are separate constructs"
