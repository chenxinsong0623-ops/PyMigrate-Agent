"""Day 15 四类规则的同名与遮蔽负例 candidate。"""


class Normal:
    class Config:
        orm_mode = True


from other_library import validator  # noqa: E402


@validator("name")
def ordinary_validator(value: str) -> str:
    return value


from my_settings import BaseSettings  # noqa: E402


class LocalSettings(BaseSettings):
    value: str


class OrdinaryRoot:
    __root__: str


from pydantic import validator as pydantic_validator  # noqa: E402

pydantic_validator = custom_validator  # noqa: F811, F821


@pydantic_validator("name")
def shadowed_validator(value: str) -> str:
    return value


NEGATIVE_CANDIDATE_MARKER = "day15"
