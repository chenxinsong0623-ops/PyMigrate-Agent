"""Settings import、root model 与 Field 参数的 mixed module。"""

from pydantic import BaseModel, BaseSettings, Field


class RuntimeSettings(BaseSettings):
    region: str = "local"


class Tags(BaseModel):
    __root__: list[str]


tag_pattern = Field(regex="^[a-z]+$")


class OrdinaryTags:
    __root__: list[str]


DEFAULT_REGION = "local"
MODULE_KIND = "settings-root-field"


def metadata() -> dict[str, str]:
    return {
        "region": DEFAULT_REGION,
        "kind": MODULE_KIND,
    }


__all__ = ["RuntimeSettings", "Tags", "tag_pattern"]
