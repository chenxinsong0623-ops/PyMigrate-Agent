"""直接 import definitions 的 bootstrap module。"""

import definitions


def settings_type() -> str:
    return definitions.RuntimeSettings.__name__


def tags_type() -> str:
    return definitions.Tags.__name__


BOOT_MODE = "static"
BOOT_REGION = "local"


def boot_metadata() -> dict[str, str]:
    return {
        "mode": BOOT_MODE,
        "region": BOOT_REGION,
    }


class Bootstrap:
    def run(self) -> tuple[str, str]:
        return settings_type(), tags_type()


bootstrap = Bootstrap()


__all__ = ["Bootstrap", "settings_type"]
