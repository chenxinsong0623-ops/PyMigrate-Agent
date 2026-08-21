import pydantic as pd


class User(pd.BaseModel):
    name: str = "Ada"


User.parse_raw('{"name": "Ada"}')


def from_parameter(user: User):
    return user.parse_file("user.json")


def from_assignment():
    current = User()
    return current.from_orm(object())


class Loader:
    @classmethod
    def parse_raw(cls, value):
        return value


Loader.parse_raw("{}")
unknown = factory()  # noqa: F821
unknown.from_orm(object())


User = Loader
User.parse_file("user.json")


def boundary(value):
    return value.parse_raw("{}")


safe_value = {"name": "Ada"}
