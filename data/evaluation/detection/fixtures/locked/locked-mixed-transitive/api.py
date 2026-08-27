"""只直接 import service；对 model 仅是二跳依赖。"""

import service


def service_type() -> str:
    return service.IdentifierService.__name__


def identifier_pattern():
    return service.identifier_pattern


ROUTE = "/identifiers"
METHOD = "GET"


def route_metadata() -> dict[str, str]:
    return {
        "route": ROUTE,
        "method": METHOD,
    }


class Endpoint:
    def inspect(self) -> str:
        return service_type()


endpoint = Endpoint()


__all__ = ["Endpoint", "service_type"]
