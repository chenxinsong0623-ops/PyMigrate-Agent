"""Pydantic module alias 装饰器样本。"""

import pydantic as validation


@validation.validator("slug")
def normalize_slug(value: str) -> str:
    return value.strip().lower()


@validation.root_validator()
def require_slug(values: dict[str, object]) -> dict[str, object]:
    return values


class LocalValidation:
    @staticmethod
    def validator(*names: str):
        return lambda function: function


local = LocalValidation()


@local.validator("slug")
def local_slug(value: str) -> str:
    return value


VALIDATOR_KIND = "module-alias"
__all__ = ["normalize_slug", "require_slug"]
