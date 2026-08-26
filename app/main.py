"""FastAPI 应用入口。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import SERVICE_NAME, __version__
from app.api.analyses import router as analyses_router
from app.api.health import router as health_router
from app.api.models import ApiErrorDetail, ApiErrorResponse, BusinessApiError
from app.api.upload_limit import AnalysisUploadLimitMiddleware
from app.core.config import Settings
from app.core.dependencies import (
    ApplicationDependencies,
    build_application_dependencies,
)
from app.core.logging import configure_logging


class ApplicationStartupError(RuntimeError):
    """应用基础设施无法安全启动。"""


def create_app(
    settings: Settings | None = None,
    dependencies: ApplicationDependencies | None = None,
) -> FastAPI:
    """创建独立的 MigrationLens FastAPI 应用。"""
    resolved_settings = settings if settings is not None else Settings()
    configure_logging(resolved_settings)
    resolved_dependencies = (
        dependencies
        if dependencies is not None
        else build_application_dependencies(resolved_settings)
    )

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        try:
            sqlite_initialized = await resolved_dependencies.sqlite.initialize()
            if not sqlite_initialized:
                raise ApplicationStartupError("应用基础设施初始化失败")
            retriever_initialized = (
                await resolved_dependencies.retriever_backend.initialize()
            )
            if not retriever_initialized:
                raise ApplicationStartupError("应用基础设施初始化失败")
            yield
        finally:
            try:
                await resolved_dependencies.retriever_backend.close()
            finally:
                await resolved_dependencies.sqlite.close()

    application = FastAPI(
        title=SERVICE_NAME,
        version=__version__,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.dependencies = resolved_dependencies
    application.add_middleware(AnalysisUploadLimitMiddleware)
    application.add_exception_handler(BusinessApiError, _business_error_handler)
    application.add_exception_handler(RequestValidationError, _validation_error_handler)
    application.add_exception_handler(StarletteHTTPException, _http_error_handler)
    application.add_exception_handler(Exception, _unexpected_error_handler)
    application.include_router(health_router)
    application.include_router(analyses_router)
    return application


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    payload = ApiErrorResponse(error=ApiErrorDetail(code=code, message=message))
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
    )


async def _business_error_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    checked = error
    if not isinstance(checked, BusinessApiError):
        return _error_response(500, "internal_error", "服务暂时无法完成请求。")
    return _error_response(
        checked.status_code,
        checked.code,
        checked.public_message,
    )


async def _validation_error_handler(
    _request: Request,
    _error: Exception,
) -> JSONResponse:
    return _error_response(422, "request_invalid", "请求字段不符合接口约束。")


async def _http_error_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    status_code = (
        error.status_code if isinstance(error, StarletteHTTPException) else 500
    )
    if status_code == 400:
        return _error_response(400, "malformed_multipart", "multipart 请求格式无效。")
    if status_code == 404:
        return _error_response(404, "route_not_found", "未找到该接口。")
    return _error_response(status_code, "http_error", "HTTP 请求无法处理。")


async def _unexpected_error_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    logging.getLogger("migrationlens").error(
        "api_unexpected_error",
        extra={"component": "api", "error_type": type(error).__name__},
    )
    return _error_response(500, "internal_error", "服务暂时无法完成请求。")


app = create_app()
