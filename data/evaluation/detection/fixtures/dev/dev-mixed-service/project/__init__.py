"""正式 mixed package initializer；不形成 finding。"""

PACKAGE_NAME = "project"
PACKAGE_VERSION = "dev-mixed"


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


PACKAGE_VARIANT = "cycle-and-two-hop"
PACKAGE_NOTE = "no imports in package initializer"
