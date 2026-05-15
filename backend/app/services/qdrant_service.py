"""Qdrant RAG Service â€” Knowledge Layer for KÃ¢rGuard AI.

Provides:
- Qdrant local persistence mode (no external server needed)
- Embedding pipeline using Gemini embedding models
- Semantic search across reviews, product descriptions, and policies
- Evidence retrieval for root cause analysis
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
from qdrant_client import QdrantClient, models

from app.config import settings

logger = logging.getLogger(__name__)

# â”€â”€ Qdrant Client Singleton â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_client: QdrantClient | None = None
_indexed_runs: dict[str, str] = {}  # run_id -> input file signature


def get_qdrant_client() -> QdrantClient:
    """Lazy-initialize Qdrant client in memory/local/server mode."""
    global _client
    if _client is None:
        if settings.QDRANT_MODE == "memory":
            _client = QdrantClient(":memory:")
            logger.info("Qdrant client baslatildi (:memory: mode)")
        elif settings.QDRANT_MODE == "local":
            _client = QdrantClient(path=str(settings.QDRANT_LOCAL_PATH))
            logger.info("Qdrant client baslatildi (local path: %s)", settings.QDRANT_LOCAL_PATH)
        else:
            _client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )
            logger.info("Qdrant client baslatildi (%s:%s)", settings.QDRANT_HOST, settings.QDRANT_PORT)
        _ensure_collections(_client)
    return _client


def health_check() -> dict[str, Any]:
    """Check Qdrant connection and return status."""
    try:
        client = get_qdrant_client()
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]
        return {
            "status": "healthy",
            "mode": settings.QDRANT_MODE,
            "collections": collection_names,
            "collection_count": len(collection_names),
        }
    except Exception as e:
        logger.error(f"Qdrant health check baÅŸarÄ±sÄ±z: {e}")
        return {"status": "unhealthy", "error": str(e)}


# â”€â”€ Collection Management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _ensure_collections(client: QdrantClient) -> None:
    """Create the 3 required collections if they don't exist."""
    collection_configs = [
        settings.QDRANT_COLLECTION_REVIEWS,
        settings.QDRANT_COLLECTION_PRODUCTS,
        settings.QDRANT_COLLECTION_POLICY,
    ]

    existing = {c.name for c in client.get_collections().collections}

    for name in collection_configs:
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=settings.EMBEDDING_DIM,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info(f"Collection oluÅŸturuldu: {name}")


# â”€â”€ Embedding Pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _get_genai_client():
    """Get the Gemini client for embeddings (reuses gemini_service singleton)."""
    from app.services.gemini_service import get_client
    return get_client()


def _payload_to_dict(payload: Any) -> dict[str, Any]:
    """Safely convert optional Qdrant payloads to a plain dict."""
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _format_embedding_input(text: str, task_type: str) -> str:
    """Format input text for embedding models based on task strategy.

    For `gemini-embedding-2`, Google recommends encoding task instructions
    in the content itself (for retrieval use-cases).
    """
    model = settings.GEMINI_EMBEDDING_MODEL
    if model == "gemini-embedding-2":
        if task_type == "RETRIEVAL_QUERY":
            return f"task: search result | query: {text}"
        if task_type == "RETRIEVAL_DOCUMENT":
            return f"title: none | text: {text}"
        if task_type == "SEMANTIC_SIMILARITY":
            return f"task: sentence similarity | query: {text}"
    return text


def embed_text(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """Embed a single text using configured Gemini embedding model.

    Args:
        text: Text to embed.
        task_type: One of RETRIEVAL_DOCUMENT, RETRIEVAL_QUERY,
                   SEMANTIC_SIMILARITY.

    Returns:
        Embedding vector (768 dimensions).
    """
    from google.genai import types

    client = _get_genai_client()
    model = settings.GEMINI_EMBEDDING_MODEL
    prepared_text = _format_embedding_input(text, task_type)

    config_kwargs: dict[str, Any] = {
        "output_dimensionality": settings.EMBEDDING_DIM,
    }
    # `task_type` is supported by gemini-embedding-001, not gemini-embedding-2.
    if model != "gemini-embedding-2":
        config_kwargs["task_type"] = task_type

    response = client.models.embed_content(
        model=model,
        contents=prepared_text,
        config=types.EmbedContentConfig(**config_kwargs),
    )
    embeddings = response.embeddings
    if not embeddings:
        raise ValueError("Embedding API returned no embeddings.")

    values = embeddings[0].values
    if values is None:
        raise ValueError("Embedding API returned empty vector values.")

    return [float(v) for v in values]


def embed_batch(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embed multiple texts using configured Gemini embedding model.

    Processes texts individually to avoid API limits.

    Args:
        texts: List of texts to embed.
        task_type: Embedding task type.

    Returns:
        List of embedding vectors.
    """
    import time

    vectors: list[list[float]] = []
    for i, text in enumerate(texts):
        try:
            vec = embed_text(text, task_type)
            vectors.append(vec)
            # Small delay between calls to respect rate limits
            if i < len(texts) - 1:
                time.sleep(0.3)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                logger.warning(f"Rate limit â€” 5s bekleniyor... ({i+1}/{len(texts)})")
                time.sleep(5)
                try:
                    vec = embed_text(text, task_type)
                    vectors.append(vec)
                except Exception as retry_err:
                    logger.error(f"Embedding baÅŸarÄ±sÄ±z (retry): {retry_err}")
                    # Zero vector as fallback
                    vectors.append([0.0] * settings.EMBEDDING_DIM)
            else:
                logger.error(f"Embedding hatasÄ±: {e}")
                vectors.append([0.0] * settings.EMBEDDING_DIM)
    return vectors


# â”€â”€ Indexing Functions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _text_id(text: str, namespace: str = "") -> int:
    """Generate a stable integer ID from text content."""
    raw = f"{namespace}|{text}" if namespace else text
    return int(hashlib.md5(raw.encode()).hexdigest()[:15], 16)


def _build_run_signature(run_dir: Path) -> str:
    tracked_files = (
        "reviews.csv",
        "products.csv",
        "product_descriptions.csv",
    )
    parts: list[str] = []
    for name in tracked_files:
        file_path = run_dir / name
        if file_path.exists():
            stat = file_path.stat()
            parts.append(f"{name}:{stat.st_size}:{stat.st_mtime_ns}")
        else:
            parts.append(f"{name}:missing")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def _build_run_filter(run_id: str, sku: str | None = None) -> models.Filter:
    must_conditions: list[models.FieldCondition] = [
        models.FieldCondition(
            key="run_id",
            match=models.MatchValue(value=run_id),
        )
    ]
    if sku is not None:
        must_conditions.append(
            models.FieldCondition(
                key="sku",
                match=models.MatchValue(value=sku),
            )
        )
    return models.Filter(must=must_conditions)


def _delete_run_points(client: QdrantClient, run_id: str) -> None:
    run_filter = _build_run_filter(run_id)
    for collection_name in (
        settings.QDRANT_COLLECTION_REVIEWS,
        settings.QDRANT_COLLECTION_PRODUCTS,
    ):
        client.delete(
            collection_name=collection_name,
            points_selector=run_filter,
            wait=True,
        )


def index_reviews(run_dir: Path, run_id: str) -> int:
    """Index reviews from reviews.csv into reviews_index collection.

    Args:
        run_dir: Directory containing reviews.csv.

    Returns:
        Number of reviews indexed.
    """
    reviews_path = run_dir / "reviews.csv"
    if not reviews_path.exists():
        logger.warning(f"reviews.csv bulunamadÄ±: {reviews_path}")
        return 0

    client = get_qdrant_client()
    df = pd.read_csv(reviews_path)

    texts: list[str] = []
    payloads: list[dict] = []

    for _, row in df.iterrows():
        comment = str(row.get("comment", ""))
        if not comment.strip():
            continue

        sku = str(row.get("sku", ""))
        rating = int(row.get("rating", 0))
        review_id = str(row.get("review_id", ""))

        # Enrich text with context for better embedding
        enriched = f"[SKU: {sku}] [Puan: {rating}/5] {comment}"
        texts.append(enriched)
        payloads.append({
            "run_id": run_id,
            "sku": sku,
            "rating": rating,
            "comment": comment,
            "review_id": review_id,
            "date": str(row.get("date", "")),
            "source": "review",
        })

    if not texts:
        return 0

    logger.info(f"Reviews embedding baÅŸlÄ±yor ({len(texts)} yorum)...")
    vectors = embed_batch(texts)

    points = [
        models.PointStruct(
            id=_text_id(texts[i], namespace=f"{run_id}:reviews"),
            vector=vectors[i],
            payload=payloads[i],
        )
        for i in range(len(texts))
    ]

    client.upsert(
        collection_name=settings.QDRANT_COLLECTION_REVIEWS,
        points=points,
        wait=True,
    )
    logger.info(f"âœ… {len(points)} review vektÃ¶rleÅŸtirildi â†’ reviews_index")
    return len(points)


def index_product_descriptions(run_dir: Path, run_id: str) -> int:
    """Index product descriptions into product_description_index.

    Uses product_descriptions.csv if available, falls back to products.csv.

    Args:
        run_dir: Directory containing product CSV files.

    Returns:
        Number of products indexed.
    """
    client = get_qdrant_client()

    # Try detailed descriptions first, then fallback to basic products.csv
    desc_path = run_dir / "product_descriptions.csv"
    if not desc_path.exists():
        desc_path = settings.MOCK_DIR / "product_descriptions.csv"

    products_path = run_dir / "products.csv"

    texts: list[str] = []
    payloads: list[dict] = []

    if desc_path.exists():
        df = pd.read_csv(desc_path)
        for _, row in df.iterrows():
            name = str(row.get("name", ""))
            category = str(row.get("category", ""))
            description = str(row.get("detailed_description", ""))
            sku = str(row.get("sku", ""))

            enriched = f"{name} â€” {category}. {description}"
            texts.append(enriched)
            payloads.append({
                "run_id": run_id,
                "sku": sku,
                "name": name,
                "category": category,
                "description": description,
                "source": "product_description",
            })
    elif products_path.exists():
        df = pd.read_csv(products_path)
        for _, row in df.iterrows():
            name = str(row.get("name", ""))
            category = str(row.get("category", ""))
            description = str(row.get("description", ""))
            sku = str(row.get("sku", ""))

            enriched = f"{name} â€” {category}. {description}"
            texts.append(enriched)
            payloads.append({
                "run_id": run_id,
                "sku": sku,
                "name": name,
                "category": category,
                "description": description,
                "source": "product_description",
            })
    else:
        logger.warning("ÃœrÃ¼n aÃ§Ä±klama dosyasÄ± bulunamadÄ±.")
        return 0

    if not texts:
        return 0

    logger.info(f"Product description embedding baÅŸlÄ±yor ({len(texts)} Ã¼rÃ¼n)...")
    vectors = embed_batch(texts)

    points = [
        models.PointStruct(
            id=_text_id(texts[i], namespace=f"{run_id}:products"),
            vector=vectors[i],
            payload=payloads[i],
        )
        for i in range(len(texts))
    ]

    client.upsert(
        collection_name=settings.QDRANT_COLLECTION_PRODUCTS,
        points=points,
        wait=True,
    )
    logger.info(f"âœ… {len(points)} Ã¼rÃ¼n aÃ§Ä±klamasÄ± vektÃ¶rleÅŸtirildi â†’ product_description_index")
    return len(points)


def index_policies() -> int:
    """Index marketplace policies from markdown file into policy_index.

    Splits the markdown into section-level chunks for granular retrieval.

    Returns:
        Number of policy chunks indexed.
    """
    policy_path = settings.POLICY_PATH
    if not policy_path.exists():
        logger.warning(f"Politika dosyasÄ± bulunamadÄ±: {policy_path}")
        return 0

    client = get_qdrant_client()
    content = policy_path.read_text(encoding="utf-8")

    # Split by ## headings (level 2 and 3)
    chunks = _split_policy_into_chunks(content)

    if not chunks:
        return 0

    texts = [c["text"] for c in chunks]
    logger.info(f"Policy embedding baÅŸlÄ±yor ({len(texts)} bÃ¶lÃ¼m)...")
    vectors = embed_batch(texts)

    points = [
        models.PointStruct(
            id=_text_id(texts[i], namespace="global:policy"),
            vector=vectors[i],
            payload={
                "section": chunks[i]["section"],
                "subsection": chunks[i].get("subsection", ""),
                "text": chunks[i]["text"],
                "chunk_id": f"policy-{i + 1}",
                "source": "policy",
            },
        )
        for i in range(len(texts))
    ]

    client.upsert(
        collection_name=settings.QDRANT_COLLECTION_POLICY,
        points=points,
        wait=True,
    )
    logger.info(f"âœ… {len(points)} politika bÃ¶lÃ¼mÃ¼ vektÃ¶rleÅŸtirildi â†’ policy_index")
    return len(points)


def _split_policy_into_chunks(content: str) -> list[dict]:
    """Split markdown policy into section-level chunks."""
    chunks = []
    current_section = ""
    current_subsection = ""
    current_text_lines: list[str] = []

    for line in content.split("\n"):
        # Level 2 heading
        if line.startswith("## "):
            # Save previous chunk
            if current_text_lines:
                text = "\n".join(current_text_lines).strip()
                if text:
                    chunks.append({
                        "section": current_section,
                        "subsection": current_subsection,
                        "text": text,
                    })
                current_text_lines = []
            current_section = line.lstrip("# ").strip()
            current_subsection = ""
        # Level 3 heading
        elif line.startswith("### "):
            # Save previous chunk
            if current_text_lines:
                text = "\n".join(current_text_lines).strip()
                if text:
                    chunks.append({
                        "section": current_section,
                        "subsection": current_subsection,
                        "text": text,
                    })
                current_text_lines = []
            current_subsection = line.lstrip("# ").strip()
        else:
            if line.strip():
                current_text_lines.append(line)

    # Last chunk
    if current_text_lines:
        text = "\n".join(current_text_lines).strip()
        if text:
            chunks.append({
                "section": current_section,
                "subsection": current_subsection,
                "text": text,
            })

    return chunks


def index_all(run_dir: Path) -> dict[str, int]:
    """Index all data sources for a run directory.

    Skips if already indexed for this run_dir.

    Returns:
        Dict with counts per collection.
    """
    if settings.DEMO_OFFLINE_MODE or not settings.GEMINI_API_KEY:
        logger.info("RAG indexing skipped (demo offline mode or missing Gemini API key).")
        return {"reviews": 0, "products": 0, "policies": 0, "skipped": True}

    run_id = run_dir.name
    run_signature = _build_run_signature(run_dir)
    if _indexed_runs.get(run_id) == run_signature:
        logger.info(f"Bu run zaten indekslenmis: {run_id}")
        return {"reviews": 0, "products": 0, "policies": 0, "skipped": True}

    client = get_qdrant_client()
    _delete_run_points(client, run_id)

    results = {
        "reviews": index_reviews(run_dir, run_id=run_id),
        "products": index_product_descriptions(run_dir, run_id=run_id),
        "policies": index_policies(),
        "skipped": False,
    }

    _indexed_runs[run_id] = run_signature
    total = results["reviews"] + results["products"] + results["policies"]
    logger.info(
        f"âœ… RAG indexing tamamlandÄ±: {total} toplam vektÃ¶r "
        f"(reviews={results['reviews']}, products={results['products']}, "
        f"policies={results['policies']})"
    )
    return results


# â”€â”€ Semantic Search Functions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def search_reviews_by_sku(
    run_id: str,
    sku: str,
    query: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Search reviews by SKU with optional semantic query."""
    client = get_qdrant_client()

    sku_filter = _build_run_filter(run_id=run_id, sku=sku)

    if query:
        try:
            query_vector = embed_text(query, task_type="RETRIEVAL_QUERY")
        except Exception as exc:
            logger.warning("Semantic review search fallback to filter-only mode: %s", exc)
            query = None
    if query:
        results = client.search(
            collection_name=settings.QDRANT_COLLECTION_REVIEWS,
            query_vector=query_vector,
            query_filter=sku_filter,
            limit=top_k,
        )
        return [
            {
                **_payload_to_dict(hit.payload),
                "score": round(hit.score, 4),
                "reference_id": (
                    _payload_to_dict(hit.payload).get("review_id")
                    or f"qdrant:{hit.id}"
                ),
            }
            for hit in results
        ]

    scroll_results = client.scroll(
        collection_name=settings.QDRANT_COLLECTION_REVIEWS,
        scroll_filter=sku_filter,
        limit=top_k,
    )
    return [
        {
            **_payload_to_dict(point.payload),
            "score": 1.0,
            "reference_id": (
                _payload_to_dict(point.payload).get("review_id")
                or f"qdrant:{point.id}"
            ),
        }
        for point in scroll_results[0]
    ]


def search_product_description(
    run_id: str,
    query: str,
    sku: str | None = None,
    top_k: int = 3,
) -> list[dict]:
    """Search product descriptions by semantic similarity."""
    client = get_qdrant_client()
    query_filter = _build_run_filter(run_id=run_id, sku=sku)
    query_vector: list[float] | None = None
    try:
        query_vector = embed_text(query, task_type="RETRIEVAL_QUERY")
    except Exception as exc:
        logger.warning("Semantic description search fallback to filter-only mode: %s", exc)

    if query_vector is None:
        scroll_results = client.scroll(
            collection_name=settings.QDRANT_COLLECTION_PRODUCTS,
            scroll_filter=query_filter,
            limit=top_k,
        )
        return [
            {
                **_payload_to_dict(point.payload),
                "score": 1.0,
                "reference_id": (
                    _payload_to_dict(point.payload).get("sku")
                    or f"qdrant:{point.id}"
                ),
            }
            for point in scroll_results[0]
        ]

    results = client.search(
        collection_name=settings.QDRANT_COLLECTION_PRODUCTS,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=top_k,
    )

    return [
        {
            **_payload_to_dict(hit.payload),
            "score": round(hit.score, 4),
            "reference_id": (
                _payload_to_dict(hit.payload).get("sku")
                or f"qdrant:{hit.id}"
            ),
        }
        for hit in results
    ]


def search_marketplace_policy(
    query: str,
    top_k: int = 3,
) -> list[dict]:
    """Search marketplace policies by semantic similarity."""
    client = get_qdrant_client()
    query_vector = embed_text(query, task_type="RETRIEVAL_QUERY")

    results = client.search(
        collection_name=settings.QDRANT_COLLECTION_POLICY,
        query_vector=query_vector,
        limit=top_k,
    )

    return [
        {
            **_payload_to_dict(hit.payload),
            "score": round(hit.score, 4),
            "reference_id": (
                _payload_to_dict(hit.payload).get("chunk_id")
                or f"qdrant:{hit.id}"
            ),
        }
        for hit in results
    ]


def retrieve_root_cause_evidence(
    run_id: str,
    sku: str,
    financial_summary: str,
    top_k_reviews: int = 5,
    top_k_descriptions: int = 2,
    top_k_policies: int = 3,
) -> dict[str, list[dict]]:
    """Retrieve comprehensive evidence from all RAG sources for root cause analysis.

    This is the main evidence retrieval function used by the Insight Agent.
    It queries across reviews, product descriptions, and policies.

    Args:
        sku: Product SKU.
        financial_summary: Brief financial context for semantic matching
                          (e.g., "yÃ¼ksek iade oranÄ±, dÃ¼ÅŸÃ¼k kÃ¢r marjÄ±").
        top_k_reviews: Max reviews to retrieve.
        top_k_descriptions: Max product descriptions.
        top_k_policies: Max policy chunks.

    Returns:
        Dict with keys: reviews, product_descriptions, policies.
    """
    evidence = {
        "reviews": [],
        "product_descriptions": [],
        "policies": [],
    }

    try:
        # 1. Reviews â€” search by financial context within SKU
        evidence["reviews"] = search_reviews_by_sku(
            run_id=run_id,
            sku=sku,
            query=financial_summary,
            top_k=top_k_reviews,
        )
    except Exception as e:
        logger.warning(f"Review aramasÄ± baÅŸarÄ±sÄ±z ({sku}): {e}")

    try:
        # 2. Product descriptions â€” find related product info
        evidence["product_descriptions"] = search_product_description(
            run_id=run_id,
            query=f"{sku} {financial_summary}",
            sku=sku,
            top_k=top_k_descriptions,
        )
    except Exception as e:
        logger.warning(f"ÃœrÃ¼n aÃ§Ä±klamasÄ± aramasÄ± baÅŸarÄ±sÄ±z: {e}")

    try:
        # 3. Policies â€” find relevant marketplace rules
        evidence["policies"] = search_marketplace_policy(
            query=financial_summary,
            top_k=top_k_policies,
        )
    except Exception as e:
        logger.warning(f"Politika aramasÄ± baÅŸarÄ±sÄ±z: {e}")

    total = sum(len(v) for v in evidence.values())
    logger.info(
        f"RAG evidence toplandÄ± ({sku}): "
        f"{len(evidence['reviews'])} review, "
        f"{len(evidence['product_descriptions'])} aÃ§Ä±klama, "
        f"{len(evidence['policies'])} politika â€” toplam {total}"
    )
    return evidence


async def generate_evidence_summary(
    evidence: dict[str, list[dict]],
    sku: str,
) -> str:
    """Generate a natural language summary of collected evidence using Gemini.

    Args:
        evidence: Output from retrieve_root_cause_evidence().
        sku: Product SKU for context.

    Returns:
        Human-readable evidence summary.
    """
    from app.services.gemini_service import generate_text

    # Build evidence text
    sections = []

    if evidence.get("reviews"):
        review_lines = []
        for r in evidence["reviews"]:
            score_str = f" (benzerlik: {r['score']:.2f})" if r.get("score") else ""
            review_lines.append(
                f"  - â­{r.get('rating', '?')}/5: \"{r.get('comment', '')}\"{score_str}"
            )
        sections.append(
            f"### MÃ¼ÅŸteri YorumlarÄ± ({len(evidence['reviews'])} adet)\n"
            + "\n".join(review_lines)
        )

    if evidence.get("product_descriptions"):
        desc_lines = []
        for d in evidence["product_descriptions"]:
            desc_lines.append(
                f"  - {d.get('name', '')}: {d.get('description', '')[:200]}..."
            )
        sections.append(
            f"### ÃœrÃ¼n AÃ§Ä±klamalarÄ±\n" + "\n".join(desc_lines)
        )

    if evidence.get("policies"):
        policy_lines = []
        for p in evidence["policies"]:
            section = p.get("section", "")
            subsection = p.get("subsection", "")
            text_preview = p.get("text", "")[:200]
            policy_lines.append(
                f"  - [{section} > {subsection}]: {text_preview}..."
            )
        sections.append(
            f"### Ä°lgili Politikalar\n" + "\n".join(policy_lines)
        )

    if not sections:
        return "KanÄ±t bulunamadÄ±."

    evidence_text = "\n\n".join(sections)

    prompt = f"""AÅŸaÄŸÄ±daki kanÄ±tlarÄ± analiz ederek {sku} Ã¼rÃ¼nÃ¼ iÃ§in kÄ±sa bir kanÄ±t Ã¶zeti oluÅŸtur.
Ã–zetin 3-5 cÃ¼mle olsun. MÃ¼ÅŸteri yorumlarÄ±ndaki kalÄ±plarÄ±, Ã¼rÃ¼n aÃ§Ä±klamasÄ±ndaki eksiklikleri ve ilgili politikalarÄ± vurgula.

{evidence_text}

KanÄ±t Ã–zeti:"""

    try:
        summary = await generate_text(
            prompt=prompt,
            system_instruction="Sen bir e-ticaret analiz asistanÄ±sÄ±n. KanÄ±tlarÄ± Ã¶zetlerken objektif ol ve verilere dayalÄ± konuÅŸ.",
            temperature=0.3,
        )
        return summary.strip()
    except Exception as e:
        logger.error(f"KanÄ±t Ã¶zeti oluÅŸturulamadÄ±: {e}")
        # Fallback: simple text summary
        total = sum(len(v) for v in evidence.values())
        return (
            f"{sku} iÃ§in {total} kanÄ±t toplandÄ±: "
            f"{len(evidence.get('reviews', []))} yorum, "
            f"{len(evidence.get('product_descriptions', []))} aÃ§Ä±klama, "
            f"{len(evidence.get('policies', []))} politika."
        )


