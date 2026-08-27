"""模块别名 BaseModel 子类的 class-reference 数据加载样本。"""

import pydantic as validation


class Profile(validation.BaseModel):
    nickname: str
    active: bool = True


profile = Profile.from_orm(object())


class ProfileFactory:
    @classmethod
    def from_orm(cls, value: object):
        return cls()


ProfileFactory.from_orm(object())


factory = build_factory()  # noqa: F821
factory.from_orm(object())


SOURCE_KIND = "orm"
PROFILE_STATE = "active"


def source_metadata() -> dict[str, str]:
    return {"kind": SOURCE_KIND, "state": PROFILE_STATE}


__all__ = ["Profile", "profile"]
