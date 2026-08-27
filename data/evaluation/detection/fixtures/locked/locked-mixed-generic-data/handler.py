"""直接 import envelope 的 handler。"""

from envelope import Envelope, parsed


def envelope_type() -> str:
    return Envelope.__name__


def parsed_status() -> str:
    return parsed.status


HANDLER_KIND = "generic"
HANDLER_MODE = "read-only"


def handler_metadata() -> dict[str, str]:
    return {
        "kind": HANDLER_KIND,
        "mode": HANDLER_MODE,
    }


class Handler:
    def inspect(self) -> str:
        return parsed_status()


handler = Handler()


__all__ = ["Handler", "envelope_type"]
