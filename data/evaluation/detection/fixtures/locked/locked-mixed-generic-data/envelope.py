"""GenericModel import/base 与 data loading 的 mixed module。"""

from pydantic import BaseModel
from pydantic.generics import GenericModel as LegacyGeneric


class Envelope(LegacyGeneric):
    value: object
    status: str = "ok"


class Payload(BaseModel):
    value: object


parsed = Payload.parse_raw('{"value":1}')


class LocalEnvelope:
    @classmethod
    def parse_raw(cls, raw: str):
        return raw


LocalEnvelope.parse_raw("{}")


DEFAULT_STATUS = "ok"
MODULE_KIND = "generic-data"


def metadata() -> dict[str, str]:
    return {
        "status": DEFAULT_STATUS,
        "kind": MODULE_KIND,
    }


__all__ = ["Envelope", "parsed"]
