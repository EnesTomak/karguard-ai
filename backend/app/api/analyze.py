"""Analysis trigger endpoint."""

from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger
from app.models.schemas import AnalysisRunResponse, AnalysisStatus
from app.services.storage_service import get_analysis_run as db_get_analysis_run
from app.services.storage_service import upsert_analysis_run

router = APIRouter()
logger = get_logger(__name__)

# In-memory run cache
_runs: dict[str, AnalysisRunResponse] = {}


@router.post("/analyze/{run_id}", response_model=AnalysisRunResponse)
async def start_analysis(run_id: str):
    """Start the full agentic analysis pipeline for a run."""
    from app.config import settings
    from app.services.agent_orchestrator import run_pipeline

    run_dir = settings.UPLOAD_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Ensure run exists before writing FK-bound snapshots.
    pending = AnalysisRunResponse(
        run_id=run_id,
        status=AnalysisStatus.RUNNING,
        created_at=datetime.now().isoformat(),
        agent_steps=[],
    )
    upsert_analysis_run(pending)

    try:
        result = await run_pipeline(run_id, run_dir)
    except Exception:
        failed = AnalysisRunResponse(
            run_id=run_id,
            status=AnalysisStatus.FAILED,
            created_at=pending.created_at,
            agent_steps=[],
        )
        upsert_analysis_run(failed)
        logger.exception("Analysis pipeline failed for run_id=%s", run_id)
        raise

    _runs[run_id] = result
    upsert_analysis_run(result)
    return result


def get_run(run_id: str) -> AnalysisRunResponse | None:
    """Retrieve run from memory first, then SQLite."""
    cached = _runs.get(run_id)
    if cached is not None:
        return cached
    return db_get_analysis_run(run_id)
