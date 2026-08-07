"""进程存活与基础设施就绪探针端点。"""

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict

from app import SERVICE_NAME, __version__
from app.core.readiness import ReadinessResult

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


@router.get(
    "/health/ready",
    response_model=ReadinessResult,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResult,
            "description": "一个或多个基础设施检查尚未就绪",
        }
    },
)
async def ready(request: Request, response: Response) -> ReadinessResult:
    """检查当前应用实例拥有的 SQLite、索引和检索后端。"""
    result = await request.app.state.dependencies.readiness.check()
    if result.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
