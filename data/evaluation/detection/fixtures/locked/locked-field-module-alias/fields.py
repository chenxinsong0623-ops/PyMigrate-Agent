"""Pydantic module alias 下的多个旧 Field keyword。"""

import pydantic as validation  # noqa: I001


minimum_tags = validation.Field(min_items=1)


maximum_tags = validation.Field(max_items=5)


pattern = validation.Field(regex="^[a-z-]+$")


valid = validation.Field(
    title="Tag",
    min_length=1,
    pattern="^[a-z-]+$",
)


class OtherModule:
    @staticmethod
    def Field(**kwargs):
        return kwargs


other = OtherModule()
other.Field(regex="ignored")


FIELD_KIND = "module-alias"


def field_metadata() -> dict[str, str]:
    return {"kind": FIELD_KIND}


__all__ = ["minimum_tags", "maximum_tags", "pattern"]
