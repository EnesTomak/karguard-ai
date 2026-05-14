"""FastAPI entry point for KârGuard AI."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import upload, analyze, dashboard, products, simulate, actions

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

# ── Routers ────────────────────────────────────────────
app.include_router(upload.router, prefix="/api", tags=["Upload"])
app.include_router(analyze.router, prefix="/api", tags=["Analyze"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(products.router, prefix="/api", tags=["Products"])
app.include_router(simulate.router, prefix="/api", tags=["Simulate"])
app.include_router(actions.router, prefix="/api", tags=["Actions"])


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "status": "running",
        "docs": "/docs",
    }
