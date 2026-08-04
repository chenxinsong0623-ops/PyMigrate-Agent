"""进程存活探针端点。"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app import SERVICE_NAME, __version__

router = APIRouter(tags=["health"])


class LiveResponse(BaseModel):
    """稳定的进程存活响应契约。"""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"
    service: str = SERVICE_NAME
    version: str = __version__


@router.get("/health/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    """在不检查外部依赖的情况下报告 API 进程是否存活。"""
    return LiveResponse()
