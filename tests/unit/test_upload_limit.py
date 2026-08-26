from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from app.api.upload_limit import (
    MAX_ANALYSIS_REQUEST_BYTES,
    AnalysisUploadLimitMiddleware,
)


@pytest.mark.asyncio
async def test_chunked_body_without_content_length_is_stopped_at_receive_limit() -> (
    None
):
    inner_called = False
    chunks = [
        {
            "type": "http.request",
            "body": b"x" * MAX_ANALYSIS_REQUEST_BYTES,
            "more_body": True,
        },
        {"type": "http.request", "body": b"x", "more_body": False},
    ]
    sent: list[dict[str, Any]] = []

    async def inner(
        _scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        _send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        nonlocal inner_called
        inner_called = True
        while (await receive()).get("more_body"):
            pass

    async def receive() -> dict[str, Any]:
        return chunks.pop(0)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await AnalysisUploadLimitMiddleware(inner)(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/analyses",
            "headers": (),
        },
        receive,
        send,
    )

    assert inner_called is True
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    payload = json.loads(sent[1]["body"])
    assert payload["error"]["code"] == "upload_too_large"


@pytest.mark.asyncio
async def test_non_analysis_request_bypasses_body_limit() -> None:
    inner_called = False

    async def inner(
        _scope: dict[str, Any],
        _receive: Callable[[], Awaitable[dict[str, Any]]],
        _send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        nonlocal inner_called
        inner_called = True

    async def receive() -> dict[str, Any]:
        raise AssertionError("bypassed inner does not read")

    async def send(_message: dict[str, Any]) -> None:
        raise AssertionError("bypassed inner does not send")

    await AnalysisUploadLimitMiddleware(inner)(
        {"type": "http", "method": "GET", "path": "/v1/rules"},
        receive,
        send,
    )

    assert inner_called is True
