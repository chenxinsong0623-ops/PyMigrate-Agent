"""对 direct module 的唯一直接 importer。"""

import direct


def record_name() -> str:
    return direct.Record.__name__


def default_token():
    return direct.token


IMPORT_STYLE = "absolute-local-module"
IMPORT_DEPTH = 1


def importer_metadata() -> dict[str, object]:
    return {
        "style": IMPORT_STYLE,
        "depth": IMPORT_DEPTH,
    }


class SafeAdapter:
    def render(self) -> str:
        return record_name()


adapter = SafeAdapter()


__all__ = ["record_name", "default_token"]
