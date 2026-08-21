from pydantic import BaseModel as BM


class User(BM):
    name: str = "Ada"


def serialize_parameter(user: User):
    return user.dict()


def serialize_assignment():
    current = User()
    return current.json()


User.parse_obj({"name": "Ada"})
User.schema()


unknown = factory()  # noqa: F821
unknown.dict()


class Ordinary:
    def dict(self):
        return {"ordinary": True}


plain = Ordinary()
plain.dict()


annotated: User = User()
annotated.copy()
annotated = factory()  # noqa: F821
annotated.copy()


def boundary(value):
    return value.json()
