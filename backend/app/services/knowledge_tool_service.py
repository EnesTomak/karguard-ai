"""Knowledge service adapter used by insight agent.

This module keeps service-layer calls independent from MCP server modules.
"""

from __future__ import annotations

from app.config import settings
from app.services.qdrant_service import index_all, retrieve_root_cause_evidence


def retrieve_root_cause_evidence_for_run(
    run_id: str,
    sku: str,
    financial_summary: str,
    top_k_reviews: int = 5,
    top_k_descriptions: int = 2,
    top_k_policies: int = 3,
) -> dict:
    run_dir = settings.UPLOAD_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run not found: {run_id}")

    index_all(run_dir)
    return retrieve_root_cause_evidence(
        run_id=run_id,
        sku=sku,
        financial_summary=financial_summary,
        top_k_reviews=top_k_reviews,
        top_k_descriptions=top_k_descriptions,
        top_k_policies=top_k_policies,
    )
