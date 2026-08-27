"""相似方法存在，但 receiver 没有 Pydantic 静态证明。"""


class Document:
    def dict(self) -> dict[str, str]:
        return {"type": "plain"}

    def parse_file(self, path: str) -> str:
        return path


document = Document()
document.dict()
document.parse_file("document.json")


factory_document = create_document()  # noqa: F821
factory_document.schema()
factory_document.from_orm(object())


def serialize(argument):
    return argument.json()


def parse(argument):
    return argument.parse_raw("{}")


DOCUMENT_KIND = "ordinary-receiver"


def metadata() -> dict[str, str]:
    return {"kind": DOCUMENT_KIND}
