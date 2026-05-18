from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ["DEBUG"] = "true"

from app.api import analyze
from app.config import settings
from app.main import app
from app.mcp_client.audit import clear_tool_traces
from app.services.action_registry import clear_cache as clear_action_cache
from app.services.finance_engine import FinanceEngine
from app.services.storage_service import init_db


@pytest.fixture(autouse=True)
def isolate_state(tmp_path, monkeypatch):
    test_upload_dir = tmp_path / "uploads"
    test_upload_dir.mkdir(parents=True, exist_ok=True)
    test_db = tmp_path / "karguard.db"

    monkeypatch.setattr(settings, "UPLOAD_DIR", test_upload_dir)
    monkeypatch.setattr(settings, "DB_PATH", test_db)

    FinanceEngine._cache.clear()
    analyze._runs.clear()
    analyze._tasks.clear()
    clear_tool_traces()
    clear_action_cache()
    init_db()
    yield
    FinanceEngine._cache.clear()
    analyze._runs.clear()
    analyze._tasks.clear()
    clear_tool_traces()
    clear_action_cache()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
