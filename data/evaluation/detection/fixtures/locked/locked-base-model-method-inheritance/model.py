"""本地继承和 constructor clue 的方法迁移样本。"""

from pydantic import BaseModel


class Entity(BaseModel):
    identifier: int


class Invoice(Entity):
    total: float


draft = Invoice(identifier=1, total=2.5)
payload = draft.dict()


Invoice.update_forward_refs()


class InvoiceView:
    def dict(self) -> dict[str, float]:
        return {"total": 2.5}


view = InvoiceView()
view.dict()


DOCUMENT_KIND = "invoice"


def current_payload() -> dict[str, object]:
    return payload
