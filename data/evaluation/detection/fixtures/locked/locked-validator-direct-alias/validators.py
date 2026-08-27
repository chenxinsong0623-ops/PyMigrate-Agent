"""validate_arguments direct alias 的函数装饰器样本。"""

from pydantic import validate_arguments as checked


@checked
def sum_values(left: int, right: int) -> int:
    return left + right


def checked(value: str) -> str:  # noqa: F811
    return value


@checked
def shadowed_after_rebind(value: str) -> str:
    return value


def plain(value: int) -> int:
    return value


DEFAULT_LEFT = 1
DEFAULT_RIGHT = 2


def expected_sum() -> int:
    return DEFAULT_LEFT + DEFAULT_RIGHT


VALIDATION_MODE = "call-boundary"


__all__ = ["sum_values"]
