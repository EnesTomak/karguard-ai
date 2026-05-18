"""File upload endpoint - CSV/Excel ingestion."""

from __future__ import annotations

import uuid
from pathlib import Path
from shutil import rmtree

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.models.schemas import UploadResponse

router = APIRouter()

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB


def _mb_to_bytes(size_mb: int) -> int:
    return int(size_mb) * 1024 * 1024


@router.post("/upload", response_model=UploadResponse)
async def upload_files(files: list[UploadFile] = File(...)):
    """Upload CSV/Excel files for a new analysis run."""
    run_id = str(uuid.uuid4())[:8]
    run_dir = settings.UPLOAD_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    max_file_size_bytes = _mb_to_bytes(settings.MAX_FILE_SIZE_MB)
    max_total_size_bytes = _mb_to_bytes(settings.MAX_TOTAL_UPLOAD_MB)
    total_uploaded_bytes = 0
    saved_files: list[str] = []

    try:
        for file_obj in files:
            safe_name = Path(file_obj.filename).name.replace("..", "").strip()
            if not safe_name:
                raise HTTPException(status_code=400, detail="Gecersiz dosya adi.")

            ext = Path(safe_name).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Desteklenmeyen dosya turu: {ext}. Izin verilenler: {ALLOWED_EXTENSIONS}",
                )

            destination = run_dir / safe_name
            if not destination.resolve().is_relative_to(run_dir.resolve()):
                raise HTTPException(status_code=400, detail="Gecersiz dosya yolu.")

            file_uploaded_bytes = 0
            with open(destination, "wb") as handle:
                while True:
                    chunk = await file_obj.read(UPLOAD_CHUNK_SIZE)
                    if not chunk:
                        break

                    chunk_size = len(chunk)
                    file_uploaded_bytes += chunk_size
                    total_uploaded_bytes += chunk_size

                    if file_uploaded_bytes > max_file_size_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                f"Tek dosya boyutu limiti asildi: {safe_name}. "
                                f"Maksimum {settings.MAX_FILE_SIZE_MB} MB."
                            ),
                        )
                    if total_uploaded_bytes > max_total_size_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                "Toplam upload limiti asildi. "
                                f"Maksimum {settings.MAX_TOTAL_UPLOAD_MB} MB."
                            ),
                        )

                    handle.write(chunk)

            saved_files.append(safe_name)
            await file_obj.close()
    except Exception:
        rmtree(run_dir, ignore_errors=True)
        raise

    return UploadResponse(
        run_id=run_id,
        uploaded_files=saved_files,
        message=f"{len(saved_files)} dosya yuklendi. Analiz baslatmak icin POST /api/analyze/{run_id} cagirin.",
    )
