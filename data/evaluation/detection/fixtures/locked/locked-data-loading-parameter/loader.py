"""参数 annotation 下的 parse_raw 数据加载样本。"""

from pydantic import BaseModel


class Event(BaseModel):
    name: str
    sequence: int


def decode_event(event: Event):
    return event.parse_raw('{"name":"start","sequence":1}')


class JsonCodec:
    def parse_raw(self, raw: str) -> dict[str, str]:
        return {"raw": raw}


codec = JsonCodec()
codec.parse_raw("{}")


def decode_unknown(value):
    return value.parse_raw("{}")


DEFAULT_EVENT = "start"
DEFAULT_SEQUENCE = 1


def defaults() -> tuple[str, int]:
    return DEFAULT_EVENT, DEFAULT_SEQUENCE
