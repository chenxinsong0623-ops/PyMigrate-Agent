"""在 multipart parser 之前限制分析请求的 ASGI body 字节数。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi.responses import JSONResponse

from app.security import MAX_UPLOAD_BYTES

MAX_MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_ANALYSIS_REQUEST_BYTES = MAX_UPLOAD_BYTES + MAX_MULTIPART_OVERHEAD_BYTES

_Receive = Callable[[], Awaitable[dict[str, Any]]]
_Send = Callable[[dict[str, Any]], Awaitable[None]]


class _RequestBodyTooLarge(RuntimeError):
    pass


class AnalysisUploadLimitMiddleware:
    """只为 POST analysis 施加不依赖 Content-Length 的接收上限。"""

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: _Receive,
        send: _Send,
    ) -> None:
        if scope.get("type") != "http" or not (
            scope.get("method") == "POST" and scope.get("path") == "/v1/analyses"
        ):
            await self._app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > MAX_ANALYSIS_REQUEST_BYTES:
            await _send_too_large(scope, receive, send)
            return

        consumed = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal consumed
            message = await receive()
            if message.get("type") == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > MAX_ANALYSIS_REQUEST_BYTES:
                    raise _RequestBodyTooLarge()
            return message

        try:
            await self._app(scope, limited_receive, send)
        except _RequestBodyTooLarge:
            await _send_too_large(scope, receive, send)


def _content_length(scope: dict[str, Any]) -> int | None:
    for raw_name, raw_value in scope.get("headers", ()):
        if raw_name.lower() == b"content-length":
            try:
                value = int(raw_value)
            except ValueError:
                return None
            return value if value >= 0 else None
    return None


async def _send_too_large(
    scope: dict[str, Any],
    receive: _Receive,
    send: _Send,
) -> None:
    response = JSONResponse(
        status_code=413,
        content={
            "error": {
                "code": "upload_too_large",
                "message": "上传 ZIP 超出大小限制。",
            }
        },
    )
    await response(scope, receive, send)
