"""FastAPI 应用入口。"""

from fastapi import FastAPI

from app import SERVICE_NAME, __version__
from app.api.health import router as health_router
from app.core.config import Settings
from app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建独立的 MigrationLens FastAPI 应用。"""
    resolved_settings = settings if settings is not None else Settings()
    configure_logging(resolved_settings)

    application = FastAPI(title=SERVICE_NAME, version=__version__)
    application.state.settings = resolved_settings
    application.include_router(health_router)
    return application


app = create_app()
