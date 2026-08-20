"""Day 15 验证器规则 candidate；只读取 AST。"""

import pydantic as pd
from pydantic import validate_arguments as va
from pydantic import validator as v


@v("name")
def normalize_name(value: str) -> str:
    return value.strip()


@pd.root_validator()
def require_identity(values: dict[str, object]) -> dict[str, object]:
    return values


@va
def validated_sum(left: int, right: int) -> int:
    return left + right


def validator(*values: object) -> tuple[object, ...]:
    return values


def ordinary(value: str) -> str:
    return value


VALIDATOR_CANDIDATE_MARKER = "day15"


__all__ = ["normalize_name", "require_identity", "validated_sum"]
