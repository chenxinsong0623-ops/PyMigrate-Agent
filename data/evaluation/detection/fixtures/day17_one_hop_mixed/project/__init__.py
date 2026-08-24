"""Day 17 package mapping candidate；只作为静态 AST 输入。"""

PACKAGE_NAME = "project"
PACKAGE_VERSION = "candidate"


def package_label() -> str:
    return PACKAGE_NAME


def package_metadata() -> dict[str, str]:
    return {
        "name": PACKAGE_NAME,
        "version": PACKAGE_VERSION,
    }


DEFAULT_LANGUAGE = "zh-CN"
DEFAULT_MODE = "read-only"


def supported_modes() -> tuple[str, ...]:
    return (DEFAULT_MODE,)


__all__ = ["PACKAGE_NAME", "package_label"]


PACKAGE_CANDIDATE_MARKER = "day17"
PACKAGE_NOTE = "no imports in package initializer"
