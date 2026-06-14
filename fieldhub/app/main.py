"""fastapi application for the field hub - local dji cloud api gateway."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes.health import router as health_router
from app.api.routes.internal import router as internal_router
from app.api.routes.manage import router as manage_router
from app.api.routes.media import router as media_router
from app.api.routes.pilot import STATIC_DIR
from app.api.routes.pilot import router as pilot_router
from app.api.routes.storage import router as storage_router
from app.api.routes.wayline import router as wayline_router
from app.core.config import settings
from app.core.db import init_db
from app.core.exceptions import HubApiError
from app.schemas.envelope import HttpResultResponse
from app.services.mqtt_listener import listener


@asynccontextmanager
async def lifespan(app: FastAPI):
    """init the registry db and run the mqtt listener for the app's lifetime."""
    init_db()
    task = None
    if settings.mqtt_enabled:
        task = asyncio.create_task(listener.run())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    """build the field hub app with routers wired."""
    app = FastAPI(
        lifespan=lifespan,
        title="TarmacView Field Hub",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @app.exception_handler(HubApiError)
    async def hub_api_error_handler(request: Request, exc: HubApiError):
        """render hub errors as dji envelopes - pilot checks code, not status."""
        body = HttpResultResponse(code=exc.code, message=exc.message)
        return JSONResponse(status_code=exc.http_status, content=body.model_dump())

    app.include_router(health_router)
    app.include_router(manage_router)
    app.include_router(wayline_router)
    app.include_router(storage_router)
    app.include_router(media_router)
    app.include_router(internal_router)
    app.include_router(pilot_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
