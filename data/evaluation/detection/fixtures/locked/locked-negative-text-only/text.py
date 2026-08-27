"""迁移关键词只出现在字符串、注释和数据键中。"""

GUIDE_TEXT = """
BaseModel.dict and BaseModel.parse_raw need migration.
Field(regex=...) and root_validator are legacy APIs.
class Config may contain orm_mode and schema_extra.
BaseSettings and GenericModel also changed.
"""


KEYWORDS = {
    "method": "schema_json",
    "loader": "from_orm",
    "root": "__root__",
    "validator": "validate_arguments",
}


# from pydantic import BaseSettings
# @validator('name')
# item = Field(const=True)


def migration_words() -> tuple[str, ...]:
    return tuple(sorted(KEYWORDS.values()))


def guide_length() -> int:
    return len(GUIDE_TEXT)


TEXT_KIND = "documentation-only"


__all__ = ["GUIDE_TEXT", "KEYWORDS"]
