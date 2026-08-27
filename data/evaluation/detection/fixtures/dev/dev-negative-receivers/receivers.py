"""高碰撞方法名、未知 factory 与文本关键词负例。"""


class Payload:
    def dict(self) -> dict[str, str]:
        return {"kind": "ordinary"}

    def json(self) -> str:
        return "{}"


payload = Payload()
payload.dict()
payload.json()


unknown = build_payload()  # noqa: F821
unknown.parse_raw("{}")


def serialize(value):
    return value.schema()


class AnnotatedOrdinary:
    pass


typed: AnnotatedOrdinary = AnnotatedOrdinary()
typed.copy()


MIGRATION_WORDS = "BaseModel.dict Field(regex=) root_validator"
# pydantic.BaseModel.parse_obj appears only in a comment.


def safe_summary() -> tuple[str, str]:
    return payload.json(), MIGRATION_WORDS
