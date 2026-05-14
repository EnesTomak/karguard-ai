"""Analysis trigger endpoint."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import AnalysisRunResponse, AnalysisStatus

router = APIRouter()

# In-memory store for runs (SQLite will replace later)
_runs: dict = {}


@router.post("/analyze/{run_id}", response_model=AnalysisRunResponse)
async def start_analysis(run_id: str):
    """Start the agentic analysis pipeline for a given run."""
    from app.config import settings
    from app.services.agent_orchestrator import run_pipeline

    run_dir = settings.UPLOAD_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run {run_id} bulunamadı. Önce dosya yükleyin.")

    result = await run_pipeline(run_id, run_dir)
    _runs[run_id] = result
    return result


def get_run(run_id: str):
    """Utility to retrieve cached run result."""
    return _runs.get(run_id)
