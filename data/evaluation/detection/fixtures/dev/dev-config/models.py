"""配置规则正式 DEV 样本；文件只作为静态 AST 输入。"""

from pydantic import BaseModel as BM


class User(BM):
    class Config:
        orm_mode = True
        schema_extra = {"example": {"name": "Ada"}}
        allow_population_by_field_name = True

    name: str
    email: str | None = None


class Admin(User):
    class Config:
        orm_mode = True

    permissions: tuple[str, ...] = ()


class Audit(User):
    created_by: str
    action: str


def describe(user: User) -> str:
    return user.name


CONFIG_VARIANT = "alias-and-inheritance"
