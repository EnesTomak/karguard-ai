"""Qdrant RAG Service — Knowledge Layer for KârGuard AI.

Provides:
- In-memory Qdrant vector store (no external server needed)
- Embedding pipeline using Gemini embedding models
- Semantic search across reviews, product descriptions, and policies
- Evidence retrieval for root cause analysis
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
from qdrant_client import QdrantClient, models

from app.config import settings

logger = logging.getLogger(__name__)

# ── Qdrant Client Singleton ──────────────────────────

_client: QdrantClient | None = None
_indexed_runs: set[str] = set()  # Track which run_dirs have been indexed


def get_qdrant_client() -> QdrantClient:
    """Lazy-initialize Qdrant client in :memory: or server mode."""
    global _client
    if _client is None:
        if settings.QDRANT_MODE == "memory":
            _client = QdrantClient(":memory:")
            logger.info("Qdrant client başlatıldı (:memory: modu)")
        else:
            _client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )
            logger.info(
                f"Qdrant client başlatıldı "
                f"({settings.QDRANT_HOST}:{settings.QDRANT_PORT})"
            )
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
        logger.error(f"Qdrant health check başarısız: {e}")
        return {"status": "unhealthy", "error": str(e)}


# ── Collection Management ────────────────────────────

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
            logger.info(f"Collection oluşturuldu: {name}")


# ── Embedding Pipeline ───────────────────────────────

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
                logger.warning(f"Rate limit — 5s bekleniyor... ({i+1}/{len(texts)})")
                time.sleep(5)
                try:
                    vec = embed_text(text, task_type)
                    vectors.append(vec)
                except Exception as retry_err:
                    logger.error(f"Embedding başarısız (retry): {retry_err}")
                    # Zero vector as fallback
                    vectors.append([0.0] * settings.EMBEDDING_DIM)
            else:
                logger.error(f"Embedding hatası: {e}")
                vectors.append([0.0] * settings.EMBEDDING_DIM)
    return vectors


# ── Indexing Functions ────────────────────────────────

def _text_id(text: str) -> int:
    """Generate a stable integer ID from text content."""
    return int(hashlib.md5(text.encode()).hexdigest()[:15], 16)


def index_reviews(run_dir: Path) -> int:
    """Index reviews from reviews.csv into reviews_index collection.

    Args:
        run_dir: Directory containing reviews.csv.

    Returns:
        Number of reviews indexed.
    """
    reviews_path = run_dir / "reviews.csv"
    if not reviews_path.exists():
        logger.warning(f"reviews.csv bulunamadı: {reviews_path}")
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
            "sku": sku,
            "rating": rating,
            "comment": comment,
            "review_id": review_id,
            "date": str(row.get("date", "")),
            "source": "review",
        })

    if not texts:
        return 0

    logger.info(f"Reviews embedding başlıyor ({len(texts)} yorum)...")
    vectors = embed_batch(texts)

    points = [
        models.PointStruct(
            id=_text_id(texts[i]),
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
    logger.info(f"✅ {len(points)} review vektörleştirildi → reviews_index")
    return len(points)


def index_product_descriptions(run_dir: Path) -> int:
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

            enriched = f"{name} — {category}. {description}"
            texts.append(enriched)
            payloads.append({
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

            enriched = f"{name} — {category}. {description}"
            texts.append(enriched)
            payloads.append({
                "sku": sku,
                "name": name,
                "category": category,
                "description": description,
                "source": "product_description",
            })
    else:
        logger.warning("Ürün açıklama dosyası bulunamadı.")
        return 0

    if not texts:
        return 0

    logger.info(f"Product description embedding başlıyor ({len(texts)} ürün)...")
    vectors = embed_batch(texts)

    points = [
        models.PointStruct(
            id=_text_id(texts[i]),
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
    logger.info(f"✅ {len(points)} ürün açıklaması vektörleştirildi → product_description_index")
    return len(points)


def index_policies() -> int:
    """Index marketplace policies from markdown file into policy_index.

    Splits the markdown into section-level chunks for granular retrieval.

    Returns:
        Number of policy chunks indexed.
    """
    policy_path = settings.POLICY_PATH
    if not policy_path.exists():
        logger.warning(f"Politika dosyası bulunamadı: {policy_path}")
        return 0

    client = get_qdrant_client()
    content = policy_path.read_text(encoding="utf-8")

    # Split by ## headings (level 2 and 3)
    chunks = _split_policy_into_chunks(content)

    if not chunks:
        return 0

    texts = [c["text"] for c in chunks]
    logger.info(f"Policy embedding başlıyor ({len(texts)} bölüm)...")
    vectors = embed_batch(texts)

    points = [
        models.PointStruct(
            id=_text_id(texts[i]),
            vector=vectors[i],
            payload={
                "section": chunks[i]["section"],
                "subsection": chunks[i].get("subsection", ""),
                "text": chunks[i]["text"],
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
    logger.info(f"✅ {len(points)} politika bölümü vektörleştirildi → policy_index")
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
    run_key = str(run_dir)
    if run_key in _indexed_runs:
        logger.info(f"Bu dizin zaten indekslenmiş: {run_dir.name}")
        return {"reviews": 0, "products": 0, "policies": 0, "skipped": True}

    results = {
        "reviews": index_reviews(run_dir),
        "products": index_product_descriptions(run_dir),
        "policies": index_policies(),
        "skipped": False,
    }

    _indexed_runs.add(run_key)
    total = results["reviews"] + results["products"] + results["policies"]
    logger.info(
        f"✅ RAG indexing tamamlandı: {total} toplam vektör "
        f"(reviews={results['reviews']}, products={results['products']}, "
        f"policies={results['policies']})"
    )
    return results


# ── Semantic Search Functions ─────────────────────────

def search_reviews_by_sku(
    sku: str,
    query: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Search reviews by SKU with optional semantic query.

    Args:
        sku: Product SKU to filter by.
        query: Optional semantic query (e.g., "beden problemi").
               If None, retrieves all reviews for the SKU sorted by relevance.
        top_k: Maximum number of results.

    Returns:
        List of review dicts with scores.
    """
    client = get_qdrant_client()

    # Build SKU filter
    sku_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="sku",
                match=models.MatchValue(value=sku),
            )
        ]
    )

    if query:
        # Semantic search with SKU filter
        query_vector = embed_text(query, task_type="RETRIEVAL_QUERY")
        results = client.search(
            collection_name=settings.QDRANT_COLLECTION_REVIEWS,
            query_vector=query_vector,
            query_filter=sku_filter,
            limit=top_k,
        )
    else:
        # Scroll all reviews for the SKU (no query vector needed)
        scroll_results = client.scroll(
            collection_name=settings.QDRANT_COLLECTION_REVIEWS,
            scroll_filter=sku_filter,
            limit=top_k,
        )
        # Return as list of dicts
        return [
            {
                **_payload_to_dict(point.payload),
                "score": 1.0,
            }
            for point in scroll_results[0]
        ]

    return [
        {
            **_payload_to_dict(hit.payload),
            "score": round(hit.score, 4),
        }
        for hit in results
    ]


def search_product_description(
    query: str,
    top_k: int = 3,
) -> list[dict]:
    """Search product descriptions by semantic similarity.

    Args:
        query: Search query (e.g., "beden tablosu", "kumaş kalitesi").
        top_k: Maximum number of results.

    Returns:
        List of product description dicts with scores.
    """
    client = get_qdrant_client()
    query_vector = embed_text(query, task_type="RETRIEVAL_QUERY")

    results = client.search(
        collection_name=settings.QDRANT_COLLECTION_PRODUCTS,
        query_vector=query_vector,
        limit=top_k,
    )

    return [
        {
            **_payload_to_dict(hit.payload),
            "score": round(hit.score, 4),
        }
        for hit in results
    ]


def search_marketplace_policy(
    query: str,
    top_k: int = 3,
) -> list[dict]:
    """Search marketplace policies by semantic similarity.

    Args:
        query: Policy-related query (e.g., "iade koşulları", "komisyon oranı").
        top_k: Maximum number of results.

    Returns:
        List of policy chunk dicts with scores.
    """
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
        }
        for hit in results
    ]


def retrieve_root_cause_evidence(
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
                          (e.g., "yüksek iade oranı, düşük kâr marjı").
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
        # 1. Reviews — search by financial context within SKU
        evidence["reviews"] = search_reviews_by_sku(
            sku=sku,
            query=financial_summary,
            top_k=top_k_reviews,
        )
    except Exception as e:
        logger.warning(f"Review araması başarısız ({sku}): {e}")

    try:
        # 2. Product descriptions — find related product info
        evidence["product_descriptions"] = search_product_description(
            query=f"{sku} {financial_summary}",
            top_k=top_k_descriptions,
        )
    except Exception as e:
        logger.warning(f"Ürün açıklaması araması başarısız: {e}")

    try:
        # 3. Policies — find relevant marketplace rules
        evidence["policies"] = search_marketplace_policy(
            query=financial_summary,
            top_k=top_k_policies,
        )
    except Exception as e:
        logger.warning(f"Politika araması başarısız: {e}")

    total = sum(len(v) for v in evidence.values())
    logger.info(
        f"RAG evidence toplandı ({sku}): "
        f"{len(evidence['reviews'])} review, "
        f"{len(evidence['product_descriptions'])} açıklama, "
        f"{len(evidence['policies'])} politika — toplam {total}"
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
                f"  - ⭐{r.get('rating', '?')}/5: \"{r.get('comment', '')}\"{score_str}"
            )
        sections.append(
            f"### Müşteri Yorumları ({len(evidence['reviews'])} adet)\n"
            + "\n".join(review_lines)
        )

    if evidence.get("product_descriptions"):
        desc_lines = []
        for d in evidence["product_descriptions"]:
            desc_lines.append(
                f"  - {d.get('name', '')}: {d.get('description', '')[:200]}..."
            )
        sections.append(
            f"### Ürün Açıklamaları\n" + "\n".join(desc_lines)
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
            f"### İlgili Politikalar\n" + "\n".join(policy_lines)
        )

    if not sections:
        return "Kanıt bulunamadı."

    evidence_text = "\n\n".join(sections)

    prompt = f"""Aşağıdaki kanıtları analiz ederek {sku} ürünü için kısa bir kanıt özeti oluştur.
Özetin 3-5 cümle olsun. Müşteri yorumlarındaki kalıpları, ürün açıklamasındaki eksiklikleri ve ilgili politikaları vurgula.

{evidence_text}

Kanıt Özeti:"""

    try:
        summary = await generate_text(
            prompt=prompt,
            system_instruction="Sen bir e-ticaret analiz asistanısın. Kanıtları özetlerken objektif ol ve verilere dayalı konuş.",
            temperature=0.3,
        )
        return summary.strip()
    except Exception as e:
        logger.error(f"Kanıt özeti oluşturulamadı: {e}")
        # Fallback: simple text summary
        total = sum(len(v) for v in evidence.values())
        return (
            f"{sku} için {total} kanıt toplandı: "
            f"{len(evidence.get('reviews', []))} yorum, "
            f"{len(evidence.get('product_descriptions', []))} açıklama, "
            f"{len(evidence.get('policies', []))} politika."
        )
