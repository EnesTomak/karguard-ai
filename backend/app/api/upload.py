"""File upload endpoint — CSV/Excel ingestion."""

import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.config import settings
from app.models.schemas import UploadResponse

router = APIRouter()

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".md", ".txt"}


@router.post("/upload", response_model=UploadResponse)
async def upload_files(files: list[UploadFile] = File(...)):
    """Upload CSV/Excel/Markdown files for a new analysis run."""
    run_id = str(uuid.uuid4())[:8]
    run_dir = settings.UPLOAD_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    saved_files: list[str] = []

    for f in files:
        # Sanitize filename — prevent path traversal
        safe_name = Path(f.filename).name.replace("..", "").strip()
        if not safe_name:
            raise HTTPException(status_code=400, detail="Geçersiz dosya adı.")

        ext = Path(safe_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Desteklenmeyen dosya türü: {ext}. İzin verilenler: {ALLOWED_EXTENSIONS}",
            )

        dest = run_dir / safe_name
        # Extra guard: ensure dest is inside run_dir
        if not dest.resolve().is_relative_to(run_dir.resolve()):
            raise HTTPException(status_code=400, detail="Geçersiz dosya yolu.")

        with open(dest, "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        saved_files.append(safe_name)

    return UploadResponse(
        run_id=run_id,
        uploaded_files=saved_files,
        message=f"{len(saved_files)} dosya yüklendi. Analiz başlatmak için POST /api/analyze/{run_id} çağırın.",
    )
