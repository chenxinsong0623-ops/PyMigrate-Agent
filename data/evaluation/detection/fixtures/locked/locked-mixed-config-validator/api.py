"""直接 import models 的 API adapter。"""

import models


def customer_type() -> str:
    return models.Customer.__name__


def normalize(value: str) -> str:
    return models.normalize_name(value)


ROUTE = "/customers"
METHOD = "POST"


def route_metadata() -> dict[str, str]:
    return {
        "route": ROUTE,
        "method": METHOD,
    }


class CustomerEndpoint:
    def handle(self, value: str) -> str:
        return normalize(value)


endpoint = CustomerEndpoint()


__all__ = ["customer_type", "normalize"]
