"""Field direct alias 和动态 kwargs 的边界样本。"""

from pydantic import Field as LegacyField  # noqa: I001


immutable = LegacyField(allow_mutation=False)
distinct = LegacyField(unique_items=True)


valid = LegacyField(
    frozen=True,
    json_schema_extra={"unique": True},
)


options = {"regex": "^[0-9]+$"}
dynamic = LegacyField(**options)


LegacyField = custom_field  # noqa: F811, F821
shadowed = LegacyField(const=True)


DEFAULT_CODE = "100"
FIELD_VARIANT = "direct-alias"


def metadata() -> tuple[str, str]:
    return DEFAULT_CODE, FIELD_VARIANT


__all__ = ["immutable", "distinct", "valid"]


SAFE_NOTE = "dynamic kwargs are not expanded"
