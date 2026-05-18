"""FastAPI entry point for KarGuard AI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import actions, analyze, dashboard, products, simulate, traces, upload
from app.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.services.storage_service import init_db

setup_logging()
logger = get_logger(__name__)


def _parse_cors_origins(raw: str) -> list[str]:
    parts = [item.strip() for item in raw.split(",")]
    return [item for item in parts if item]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("SQLite initialized at %s", settings.DB_PATH)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Agentic ProfitOps Platform for Marketplace Sellers",
    version="1.0.0",
    lifespan=lifespan,
)

cors_origins = _parse_cors_origins(settings.CORS_ALLOWED_ORIGINS)
allow_all_origins = cors_origins == ["*"]
allow_credentials = settings.CORS_ALLOW_CREDENTIALS and not allow_all_origins
if settings.CORS_ALLOW_CREDENTIALS and allow_all_origins:
    logger.warning(
        "CORS credentials disabled because wildcard origin is configured. "
        "Set explicit origins to enable credentials safely."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["http://localhost:5173"],
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.middleware("http")
async def log_request_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid4().hex[:12])
    request.state.request_id = request_id
    started = perf_counter()

    response = await call_next(request)
    elapsed_ms = (perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "%s %s -> %s (%.2fms) [request_id=%s]",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )
    return response


app.include_router(upload.router, prefix="/api", tags=["Upload"])
app.include_router(analyze.router, prefix="/api", tags=["Analyze"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(products.router, prefix="/api", tags=["Products"])
app.include_router(simulate.router, prefix="/api", tags=["Simulate"])
app.include_router(actions.router, prefix="/api", tags=["Actions"])
app.include_router(traces.router, prefix="/api", tags=["Traces"])


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "status": "running",
        "docs": "/docs",
    }

