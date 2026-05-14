"""FastAPI entry point for KarGuard AI."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import actions, analyze, dashboard, products, simulate, upload
from app.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.services.storage_service import init_db

setup_logging()
logger = get_logger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description="Agentic ProfitOps Platform for Marketplace Sellers",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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


@app.on_event("startup")
async def on_startup():
    init_db()
    logger.info("SQLite initialized at %s", settings.DB_PATH)


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "status": "running",
        "docs": "/docs",
    }

