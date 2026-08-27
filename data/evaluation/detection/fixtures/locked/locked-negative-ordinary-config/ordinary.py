"""普通 Config、同名 decorator 和普通根字段负例。"""

from validation_helpers import root_validator


class CacheEntry:
    class Config:
        orm_mode = True
        schema_extra = {"cache": True}

    __root__: str


@root_validator()
def normalize_cache(values: dict[str, object]) -> dict[str, object]:
    return values


class PlainModel:
    def dict(self) -> dict[str, bool]:
        return {"cached": True}


entry = PlainModel()
entry.dict()


CACHE_KIND = "ordinary"


def metadata() -> dict[str, str]:
    return {"kind": CACHE_KIND}


__all__ = ["CacheEntry", "normalize_cache"]
