"""注解、attribute chain 与跨函数返回值证据不足负例。"""

from pydantic import BaseModel


class User(BaseModel):
    name: str


def build_user() -> User:
    return User(name="Ada")


returned = build_user()
returned.dict()


container = object()
container.user = User(name="Ada")  # type: ignore[attr-defined]
container.user.json()  # type: ignore[attr-defined]


maybe: object = User(name="Ada")
maybe.copy()  # type: ignore[attr-defined]


def unknown(value):
    value: object
    return value.schema()


EVIDENCE_KIND = "outside-shallow-contract"


def metadata() -> dict[str, str]:
    return {"kind": EVIDENCE_KIND}
