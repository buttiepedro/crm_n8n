"""Aplicación FastAPI: middleware de observabilidad, handlers de errores,
routers bajo /api/v1 y ciclo de vida (engine, cola, storage)."""

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request

from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import dispose_engine, init_engine
from app.infra.queue import get_queue, init_queue
from app.infra.storage import init_storage
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.config.router import router as config_router
from app.modules.conversations.router import router as conversations_router
from app.modules.health.router import router as health_router
from app.modules.hooks.router import router as hooks_router
from app.modules.leads.router import router as leads_router
from app.modules.tags.router import router as tags_router
from app.modules.task_handlers import register_task_handlers
from app.modules.whatsapp.router import router as whatsapp_router

log = structlog.get_logger()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.app_env != "development")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_engine(settings)
        queue = init_queue(settings)
        register_task_handlers(queue)
        init_storage(settings)
        log.info("startup", app_env=settings.app_env)
        yield
        # Shutdown graceful: drenar tareas en vuelo y cerrar el pool
        await get_queue().drain()
        await dispose_engine()
        log.info("shutdown")

    app = FastAPI(
        title="CRM WhatsApp ↔ n8n",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )

    @app.middleware("http")
    async def observability(request: Request, call_next):
        structlog.contextvars.clear_contextvars()
        trace_header = request.headers.get("X-Cloud-Trace-Context", "")
        trace_id = trace_header.split("/")[0] if trace_header else uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"

        if not request.url.path.startswith("/api/v1/health"):
            log.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )
        return response

    register_exception_handlers(app)

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(whatsapp_router, prefix="/api/v1")
    app.include_router(hooks_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(conversations_router, prefix="/api/v1")
    app.include_router(leads_router, prefix="/api/v1")
    app.include_router(tags_router, prefix="/api/v1")
    app.include_router(config_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    return app


app = create_app()
