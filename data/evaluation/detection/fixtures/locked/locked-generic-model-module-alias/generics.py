"""pydantic.generics module alias class base 样本。"""

import pydantic.generics as generics


class Envelope(generics.GenericModel):
    value: object
    status: str = "ok"


class OrdinaryGeneric:
    value: object


def envelope_status(envelope: Envelope) -> str:
    return envelope.status


GENERIC_KIND = "module-alias"
DEFAULT_STATUS = "ok"


def metadata() -> dict[str, str]:
    return {
        "kind": GENERIC_KIND,
        "status": DEFAULT_STATUS,
    }


__all__ = ["Envelope"]


SAFE_NOTE = "no local GenericModel shadow"
