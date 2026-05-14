"""Knowledge MCP server.

Exposes RAG knowledge capabilities as MCP tools:
- search_reviews_by_sku
- search_product_description
- retrieve_root_cause_evidence
- search_marketplace_policy
- generate_evidence_summary
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.services.qdrant_service import (
    generate_evidence_summary as rag_generate_evidence_summary,
    health_check,
    index_all,
    index_policies,
    retrieve_root_cause_evidence as rag_retrieve_root_cause_evidence,
    search_marketplace_policy as rag_search_marketplace_policy,
    search_product_description as rag_search_product_description,
    search_reviews_by_sku as rag_search_reviews_by_sku,
)

mcp = FastMCP("knowledge-mcp")


def _ensure_index(run_id: str) -> dict[str, int]:
    """Ensure run data is indexed in Qdrant before querying."""
    run_dir = settings.UPLOAD_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run not found: {run_id}")
    return index_all(run_dir)


def _run_async(coro):
    """Run async coroutine from sync tool context."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "Event loop already running; call async summary through async MCP transport."
    )


@mcp.tool()
def search_reviews_by_sku(
    run_id: str,
    sku: str,
    query: str | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Search semantically relevant reviews for a SKU."""
    index_result = _ensure_index(run_id)
    warning = ""
    try:
        items = rag_search_reviews_by_sku(sku=sku, query=query, top_k=top_k)
    except Exception as exc:
        warning = f"Semantic search failed; fallback used: {exc}"
        items = rag_search_reviews_by_sku(sku=sku, query=None, top_k=top_k)
    return {
        "run_id": run_id,
        "sku": sku,
        "indexed": index_result,
        "warning": warning,
        "count": len(items),
        "items": items,
    }


@mcp.tool()
def search_product_description(
    run_id: str,
    query: str,
    top_k: int = 3,
) -> dict[str, Any]:
    """Search product descriptions by semantic similarity."""
    index_result = _ensure_index(run_id)
    warning = ""
    try:
        items = rag_search_product_description(query=query, top_k=top_k)
    except Exception as exc:
        warning = f"Semantic search failed: {exc}"
        items = []
    return {
        "run_id": run_id,
        "indexed": index_result,
        "warning": warning,
        "count": len(items),
        "items": items,
    }


@mcp.tool()
def retrieve_root_cause_evidence(
    run_id: str,
    sku: str,
    financial_summary: str,
    top_k_reviews: int = 5,
    top_k_descriptions: int = 2,
    top_k_policies: int = 3,
) -> dict[str, Any]:
    """Retrieve RAG evidence from reviews, product descriptions, and policies."""
    index_result = _ensure_index(run_id)
    evidence = rag_retrieve_root_cause_evidence(
        sku=sku,
        financial_summary=financial_summary,
        top_k_reviews=top_k_reviews,
        top_k_descriptions=top_k_descriptions,
        top_k_policies=top_k_policies,
    )
    return {
        "run_id": run_id,
        "sku": sku,
        "indexed": index_result,
        "evidence": evidence,
    }


@mcp.tool()
def search_marketplace_policy(query: str, top_k: int = 3) -> dict[str, Any]:
    """Search marketplace policy chunks semantically."""
    index_policies()
    warning = ""
    try:
        items = rag_search_marketplace_policy(query=query, top_k=top_k)
    except Exception as exc:
        warning = f"Semantic search failed: {exc}"
        items = []
    return {
        "warning": warning,
        "count": len(items),
        "items": items,
    }


@mcp.tool()
def generate_evidence_summary(
    run_id: str,
    sku: str,
    financial_summary: str,
    top_k_reviews: int = 5,
    top_k_descriptions: int = 2,
    top_k_policies: int = 3,
) -> dict[str, Any]:
    """Generate a short summary from retrieved RAG evidence."""
    index_result = _ensure_index(run_id)
    evidence = rag_retrieve_root_cause_evidence(
        sku=sku,
        financial_summary=financial_summary,
        top_k_reviews=top_k_reviews,
        top_k_descriptions=top_k_descriptions,
        top_k_policies=top_k_policies,
    )
    summary = _run_async(rag_generate_evidence_summary(evidence=evidence, sku=sku))
    return {
        "run_id": run_id,
        "sku": sku,
        "indexed": index_result,
        "summary": summary,
        "evidence": evidence,
    }


@mcp.tool()
def knowledge_health_check() -> dict[str, Any]:
    """Return Qdrant health status for the knowledge layer."""
    return health_check()


if __name__ == "__main__":
    mcp.run()
