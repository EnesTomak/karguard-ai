"""Analysis run manager endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger
from app.models.schemas import AgentStepResponse, AnalysisRunResponse, AnalysisStatus
from app.services.storage_service import get_analysis_run as db_get_analysis_run
from app.services.storage_service import upsert_analysis_run

router = APIRouter()
logger = get_logger(__name__)

# In-memory run cache and task registry
_runs: dict[str, AnalysisRunResponse] = {}
_tasks: dict[str, asyncio.Task[None]] = {}


def _cache_and_persist(run: AnalysisRunResponse) -> None:
    _runs[run.run_id] = run
    upsert_analysis_run(run)


def get_run(run_id: str) -> AnalysisRunResponse | None:
    """Retrieve run from SQLite first, then memory cache."""
    persisted = db_get_analysis_run(run_id)
    if persisted is not None:
        _runs[run_id] = persisted
        return persisted
    return _runs.get(run_id)


async def _progress_hook(
    run_id: str,
    created_at: str,
    steps: list[AgentStepResponse],
    status: AnalysisStatus,
) -> None:
    run = AnalysisRunResponse(
        run_id=run_id,
        status=status,
        created_at=created_at,
        agent_steps=steps,
    )
    _cache_and_persist(run)


async def _run_pipeline_task(run_id: str, created_at: str) -> None:
    from app.config import settings
    from app.services.agent_orchestrator import run_pipeline

    run_dir = settings.UPLOAD_DIR / run_id
    try:
        result = await run_pipeline(
            run_id=run_id,
            run_dir=run_dir,
            progress_hook=lambda steps, status: _progress_hook(
                run_id=run_id,
                created_at=created_at,
                steps=steps,
                status=status,
            ),
        )
        # Preserve initial created_at for easier run tracking.
        result.created_at = created_at
        _cache_and_persist(result)
    except Exception:
        failed = AnalysisRunResponse(
            run_id=run_id,
            status=AnalysisStatus.FAILED,
            created_at=created_at,
            agent_steps=[],
        )
        _cache_and_persist(failed)
        logger.exception("Analysis pipeline failed for run_id=%s", run_id)
    finally:
        _tasks.pop(run_id, None)


@router.post("/analyze/{run_id}", response_model=AnalysisRunResponse)
async def start_analysis(run_id: str):
    """Start analysis asynchronously and return current run state."""
    from app.config import settings

    run_dir = settings.UPLOAD_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    existing = get_run(run_id)
    active_task = _tasks.get(run_id)

    # Return the currently running state if local worker is active.
    if active_task is not None and not active_task.done():
        if existing is not None:
            return existing

    if existing is not None and existing.status == AnalysisStatus.COMPLETED:
        return existing

    # If run was marked running but process restarted, restart pipeline.
    created_at = existing.created_at if existing is not None else datetime.now().isoformat()
    pending = AnalysisRunResponse(
        run_id=run_id,
        status=AnalysisStatus.RUNNING,
        created_at=created_at,
        agent_steps=(
            existing.agent_steps
            if existing is not None and existing.status == AnalysisStatus.RUNNING
            else []
        ),
    )
    _cache_and_persist(pending)

    _tasks[run_id] = asyncio.create_task(_run_pipeline_task(run_id, created_at))
    return pending


@router.get("/analyze/{run_id}", response_model=AnalysisRunResponse)
async def get_analysis(run_id: str):
    """Get latest status for a run."""
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    active_task = _tasks.get(run_id)
    if run.status == AnalysisStatus.RUNNING and (active_task is None or active_task.done()):
        from app.config import settings

        run_dir = settings.UPLOAD_DIR / run_id
        if not run_dir.exists():
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

        steps = [step.model_copy(deep=True) for step in run.agent_steps]
        steps.append(
            AgentStepResponse(
                step_name="Run Manager",
                status="running",
                message="Calisma devam ettiriliyor. Pipeline otomatik yeniden baslatildi.",
                timestamp=datetime.now().isoformat(),
            )
        )
        resumed = AnalysisRunResponse(
            run_id=run.run_id,
            status=AnalysisStatus.RUNNING,
            created_at=run.created_at,
            agent_steps=steps,
        )
        _cache_and_persist(resumed)
        if active_task is None or active_task.done():
            _tasks[run_id] = asyncio.create_task(_run_pipeline_task(run_id, run.created_at))
        return resumed

    return run
