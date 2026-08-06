"""FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import SERVICE_NAME, __version__
from app.api.health import router as health_router
from app.core.config import Settings
from app.core.dependencies import build_application_dependencies
from app.core.logging import configure_logging


class ApplicationStartupError(RuntimeError):
    """应用基础设施无法安全启动。"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建独立的 MigrationLens FastAPI 应用。"""
    resolved_settings = settings if settings is not None else Settings()
    configure_logging(resolved_settings)
    dependencies = build_application_dependencies(resolved_settings)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        try:
            initialized = await dependencies.sqlite.initialize()
            if not initialized:
                raise ApplicationStartupError("应用基础设施初始化失败")
            yield
        finally:
            await dependencies.sqlite.close()

    application = FastAPI(
        title=SERVICE_NAME,
        version=__version__,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.dependencies = dependencies
    application.include_router(health_router)
    return application


app = create_app()
