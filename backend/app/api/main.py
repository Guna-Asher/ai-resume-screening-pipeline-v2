import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import Settings, load_settings
from app.models import SCHEMA_VERSION

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(
        title="AI Resume Screening API",
        version="0.4.0",
        description=(
            "Thin HTTP interface over the same screening pipeline the CLI uses. "
            f"Results follow the `ScreeningResults` schema (version {SCHEMA_VERSION})."
        ),
    )
    app.state.screen_lock = asyncio.Lock()  # one screening run at a time; no job queue

    origins = settings.cors_origin_list
    if origins:
        if "*" in origins:
            logger.warning("CORS_ORIGINS contains '*': any website may call this API")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse({"detail": "Internal server error."}, status_code=500)

    app.include_router(router)
    return app


app = create_app()
