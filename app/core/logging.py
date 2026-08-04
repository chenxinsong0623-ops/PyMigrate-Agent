"""基于标准库的结构化 JSON 日志。"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import IO, Final

from app import SERVICE_NAME
from app.core.config import Settings

LOGGER_NAME: Final = "migrationlens"
_HANDLER_MARKER: Final = "_migrationlens_json_handler"


class JsonFormatter(logging.Formatter):
    """将每条日志记录渲染为一个 JSON 对象。"""

    def __init__(self, *, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        """使用必需的公共字段序列化日志记录。"""
        timestamp = datetime.fromtimestamp(record.created, tz=UTC)
        payload = {
            "timestamp": timestamp.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "service": self._service,
            "environment": self._environment,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(
    settings: Settings,
    *,
    stream: IO[str] | None = None,
) -> logging.Logger:
    """配置并返回 MigrationLens 日志器，且不重复添加处理器。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, settings.log_level))
    logger.disabled = False
    logger.propagate = False

    target_stream = stream if stream is not None else sys.stdout
    owned_handlers = [
        handler
        for handler in logger.handlers
        if getattr(handler, _HANDLER_MARKER, False)
    ]

    if owned_handlers:
        handler = owned_handlers[0]
        for duplicate in owned_handlers[1:]:
            logger.removeHandler(duplicate)
            duplicate.close()
        if isinstance(handler, logging.StreamHandler):
            # 直接赋值可避免刷新捕获流；pytest 可能已在两次应用工厂调用之间
            # 关闭该捕获流。
            handler.stream = target_stream
    else:
        handler = logging.StreamHandler(target_stream)
        setattr(handler, _HANDLER_MARKER, True)
        logger.addHandler(handler)

    handler.setLevel(getattr(logging, settings.log_level))
    handler.setFormatter(
        JsonFormatter(
            service=SERVICE_NAME,
            environment=settings.environment,
        )
    )
    return logger
