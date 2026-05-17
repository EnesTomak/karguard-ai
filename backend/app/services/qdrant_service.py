"""Qdrant RAG Service — Knowledge Layer for KârGuard AI.

Provides:
- Qdrant local persistence mode
- Embedding pipeline using Gemini embedding models
- Semantic search across reviews, product descriptions, and policies
- Evidence retrieval for root cause analysis
"""

from __future__ import annotations

import hashlib
import importlib
import logging
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import settings

logger = logging.getLogger(__name__)

_client: Any | None = None
_qdrant_client_cls: Any | None = None
_qdrant_models: Any | None = None
_indexed_runs: dict[str, str] = {}  # run_id -> input file signature


# ── Optional dependency loading ────────────────────────


def _load_qdrant() -> tuple[Any, Any]:
    """Return (QdrantClient, models), loading qdrant-client lazily."""
    global _qdrant_client_cls, _qdrant_models

    if _qdrant_client_cls is None or _qdrant_models is None:
        try:
            qdrant_module = importlib.import_module("qdrant_client")
            _qdrant_client_cls = getattr(qdrant_module, "QdrantClient")
            _qdrant_models = getattr(qdrant_module, "models", None)

            if _qdrant_models is None:
                _qdrant_models = importlib.import_module("qdrant_client.models")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "qdrant-client is not installed in the selected Python environment. "
                "Install it with: python -m pip install -U qdrant-client"
            ) from exc

    return _qdrant_client_cls, _qdrant_models


def _models() -> Any:
    return _load_qdrant()[1]


def reset_qdrant_client() -> None:
    """Reset the cached Qdrant client. Useful in tests."""
    global _client
    _client = None


# ── Qdrant Client Singleton ────────────────────────────


def get_qdrant_client() -> Any:
    """Lazy-initialize Qdrant client in memory/local/server mode."""
    global _client

    if _client is None:
        QdrantClient, _ = _load_qdrant()

        mode = str(settings.QDRANT_MODE).lower()
        if mode == "memory":
            _client = QdrantClient(":memory:")
            logger.info("Qdrant client başlatıldı (:memory: mode)")
        elif mode == "local":
            Path(settings.QDRANT_LOCAL_PATH).mkdir(parents=True, exist_ok=True)
            _client = QdrantClient(path=str(settings.QDRANT_LOCAL_PATH))
            logger.info("Qdrant client başlatıldı (local path: %s)", settings.QDRANT_LOCAL_PATH)
        else:
            _client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )
            logger.info("Qdrant client başlatıldı (%s:%s)", settings.QDRANT_HOST, settings.QDRANT_PORT)

        _ensure_collections(_client)

    return _client


def health_check() -> dict[str, Any]:
    """Check Qdrant connection and return status."""
    try:
        client = get_qdrant_client()
        collections = client.get_collections().collections
        collection_names = [collection.name for collection in collections]

        return {
            "status": "healthy",
            "mode": settings.QDRANT_MODE,
            "collections": collection_names,
            "collection_count": len(collection_names),
        }
    except Exception as exc:
        logger.error("Qdrant health check başarısız: %s", exc)
        return {"status": "unhealthy", "error": str(exc)}


# ── Collection Management ──────────────────────────────


def _ensure_collections(client: Any) -> None:
    """Create required collections if they do not exist."""
    models = _models()
    collection_names = (
        settings.QDRANT_COLLECTION_REVIEWS,
        settings.QDRANT_COLLECTION_PRODUCTS,
        settings.QDRANT_COLLECTION_POLICY,
    )

    existing = {collection.name for collection in client.get_collections().collections}

    for name in collection_names:
        if name in existing:
            continue

        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=settings.EMBEDDING_DIM,
                distance=models.Distance.COSINE,
            ),
        )
        logger.info("Collection oluşturuldu: %s", name)


# ── Embedding Pipeline ─────────────────────────────────


def _get_genai_client() -> Any:
    """Get the Gemini client for embeddings."""
    from app.services.gemini_service import get_client

    return get_client()


def _get_genai_types() -> Any:
    """Get google.genai.types lazily through gemini_service."""
    from app.services.gemini_service import get_genai_types

    return get_genai_types()


def _payload_to_dict(payload: Any) -> dict[str, Any]:
    """Safely convert optional Qdrant payloads to a plain dict."""
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _safe_int(value: object, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _format_embedding_input(text: str, task_type: str) -> str:
    """Format input text for embedding models based on task strategy.

    For gemini-embedding-2, task hints are encoded in the text because the
    separate task_type config is not used for that model in this project.
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


def _zero_vector() -> list[float]:
    return [0.0] * int(settings.EMBEDDING_DIM)


def embed_text(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """Embed a single text using the configured Gemini embedding model."""
    if not text.strip():
        return _zero_vector()

    client = _get_genai_client()
    types = _get_genai_types()

    model = settings.GEMINI_EMBEDDING_MODEL
    prepared_text = _format_embedding_input(text, task_type)

    config_kwargs: dict[str, Any] = {
        "output_dimensionality": settings.EMBEDDING_DIM,
    }

    if model != "gemini-embedding-2":
        config_kwargs["task_type"] = task_type

    response = client.models.embed_content(
        model=model,
        contents=prepared_text,
        config=types.EmbedContentConfig(**config_kwargs),
    )

    embeddings = getattr(response, "embeddings", None)
    if not embeddings:
        raise ValueError("Embedding API returned no embeddings.")

    values = getattr(embeddings[0], "values", None)
    if values is None:
        raise ValueError("Embedding API returned empty vector values.")

    vector = [float(value) for value in values]
    if len(vector) != settings.EMBEDDING_DIM:
        logger.warning(
            "Embedding dimension mismatch: expected %s, got %s",
            settings.EMBEDDING_DIM,
            len(vector),
        )

    return vector


def embed_batch(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embed multiple texts individually to stay inside API limits."""
    vectors: list[list[float]] = []

    for index, text in enumerate(texts, start=1):
        try:
            vectors.append(embed_text(text, task_type))
            if index < len(texts):
                time.sleep(0.3)
        except Exception as exc:
            error_text = str(exc)

            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                logger.warning("Embedding rate limit — 5s bekleniyor... (%s/%s)", index, len(texts))
                time.sleep(5)
                try:
                    vectors.append(embed_text(text, task_type))
                    continue
                except Exception as retry_exc:
                    logger.error("Embedding başarısız (retry): %s", retry_exc)
            else:
                logger.error("Embedding hatası: %s", exc)

            vectors.append(_zero_vector())

    return vectors


# ── Indexing Functions ─────────────────────────────────


def _text_id(text: str, namespace: str = "") -> int:
    """Generate a stable integer ID from text content."""
    raw = f"{namespace}|{text}" if namespace else text
    return int(hashlib.md5(raw.encode("utf-8")).hexdigest()[:15], 16)


def _build_run_signature(run_dir: Path) -> str:
    tracked_files = (
        "reviews.csv",
        "products.csv",
        "product_descriptions.csv",
    )

    parts: list[str] = []
    for filename in tracked_files:
        file_path = run_dir / filename
        if file_path.exists():
            stat = file_path.stat()
            parts.append(f"{filename}:{stat.st_size}:{stat.st_mtime_ns}")
        else:
            parts.append(f"{filename}:missing")

    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _build_run_filter(run_id: str, sku: str | None = None) -> Any:
    models = _models()
    must_conditions = [
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


def _delete_run_points(client: Any, run_id: str) -> None:
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


def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None

    try:
        return pd.read_csv(path)
    except Exception as exc:
        logger.warning("CSV okunamadı (%s): %s", path, exc)
        return None


def index_reviews(run_dir: Path, run_id: str) -> int:
    """Index reviews from reviews.csv into the review collection."""
    reviews_path = run_dir / "reviews.csv"
    df = _read_csv(reviews_path)

    if df is None:
        logger.warning("reviews.csv bulunamadı veya okunamadı: %s", reviews_path)
        return 0

    client = get_qdrant_client()
    models = _models()

    texts: list[str] = []
    payloads: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        comment = str(row.get("comment", "")).strip()
        if not comment:
            continue

        sku = str(row.get("sku", "")).strip()
        rating = _safe_int(row.get("rating", 0))
        review_id = str(row.get("review_id", "")).strip()

        enriched = f"[SKU: {sku}] [Puan: {rating}/5] {comment}"
        texts.append(enriched)
        payloads.append(
            {
                "run_id": run_id,
                "sku": sku,
                "rating": rating,
                "comment": comment,
                "review_id": review_id,
                "date": str(row.get("date", "")),
                "source": "review",
            }
        )

    if not texts:
        return 0

    logger.info("Reviews embedding başlıyor (%s yorum)...", len(texts))
    vectors = embed_batch(texts)

    points = [
        models.PointStruct(
            id=_text_id(texts[index], namespace=f"{run_id}:reviews"),
            vector=vectors[index],
            payload=payloads[index],
        )
        for index in range(len(texts))
    ]

    client.upsert(
        collection_name=settings.QDRANT_COLLECTION_REVIEWS,
        points=points,
        wait=True,
    )

    logger.info("✅ %s review vektörleştirildi → reviews_index", len(points))
    return len(points)


def index_product_descriptions(run_dir: Path, run_id: str) -> int:
    """Index product descriptions.

    Uses run_dir/product_descriptions.csv if available, then MOCK_DIR fallback,
    then run_dir/products.csv as a final fallback.
    """
    client = get_qdrant_client()
    models = _models()

    desc_path = run_dir / "product_descriptions.csv"
    if not desc_path.exists():
        desc_path = settings.MOCK_DIR / "product_descriptions.csv"

    products_path = run_dir / "products.csv"

    texts: list[str] = []
    payloads: list[dict[str, Any]] = []

    desc_df = _read_csv(desc_path)
    products_df = _read_csv(products_path) if desc_df is None else None

    if desc_df is not None:
        for _, row in desc_df.iterrows():
            name = str(row.get("name", "")).strip()
            category = str(row.get("category", "")).strip()
            description = str(row.get("detailed_description", "")).strip()
            sku = str(row.get("sku", "")).strip()

            if not (name or description):
                continue

            enriched = f"{name} — {category}. {description}"
            texts.append(enriched)
            payloads.append(
                {
                    "run_id": run_id,
                    "sku": sku,
                    "name": name,
                    "category": category,
                    "description": description,
                    "source": "product_description",
                }
            )
    elif products_df is not None:
        for _, row in products_df.iterrows():
            name = str(row.get("name", "")).strip()
            category = str(row.get("category", "")).strip()
            description = str(row.get("description", "")).strip()
            sku = str(row.get("sku", "")).strip()

            if not (name or description):
                continue

            enriched = f"{name} — {category}. {description}"
            texts.append(enriched)
            payloads.append(
                {
                    "run_id": run_id,
                    "sku": sku,
                    "name": name,
                    "category": category,
                    "description": description,
                    "source": "product_description",
                }
            )
    else:
        logger.warning("Ürün açıklama dosyası bulunamadı.")
        return 0

    if not texts:
        return 0

    logger.info("Product description embedding başlıyor (%s ürün)...", len(texts))
    vectors = embed_batch(texts)

    points = [
        models.PointStruct(
            id=_text_id(texts[index], namespace=f"{run_id}:products"),
            vector=vectors[index],
            payload=payloads[index],
        )
        for index in range(len(texts))
    ]

    client.upsert(
        collection_name=settings.QDRANT_COLLECTION_PRODUCTS,
        points=points,
        wait=True,
    )

    logger.info("✅ %s ürün açıklaması vektörleştirildi → product_description_index", len(points))
    return len(points)


def index_policies() -> int:
    """Index marketplace policies from markdown file into policy_index."""
    policy_path = Path(settings.POLICY_PATH)

    if not policy_path.exists():
        logger.warning("Politika dosyası bulunamadı: %s", policy_path)
        return 0

    client = get_qdrant_client()
    models = _models()

    content = policy_path.read_text(encoding="utf-8")
    chunks = _split_policy_into_chunks(content)

    if not chunks:
        return 0

    texts = [chunk["text"] for chunk in chunks]
    logger.info("Policy embedding başlıyor (%s bölüm)...", len(texts))
    vectors = embed_batch(texts)

    points = [
        models.PointStruct(
            id=_text_id(texts[index], namespace="global:policy"),
            vector=vectors[index],
            payload={
                "section": chunks[index]["section"],
                "subsection": chunks[index].get("subsection", ""),
                "text": chunks[index]["text"],
                "chunk_id": f"policy-{index + 1}",
                "source": "policy",
            },
        )
        for index in range(len(texts))
    ]

    client.upsert(
        collection_name=settings.QDRANT_COLLECTION_POLICY,
        points=points,
        wait=True,
    )

    logger.info("✅ %s politika bölümü vektörleştirildi → policy_index", len(points))
    return len(points)


def _split_policy_into_chunks(content: str) -> list[dict[str, str]]:
    """Split markdown policy into section-level chunks."""
    chunks: list[dict[str, str]] = []
    current_section = ""
    current_subsection = ""
    current_text_lines: list[str] = []

    def flush() -> None:
        nonlocal current_text_lines
        text = "\n".join(current_text_lines).strip()
        if text:
            chunks.append(
                {
                    "section": current_section,
                    "subsection": current_subsection,
                    "text": text,
                }
            )
        current_text_lines = []

    for line in content.splitlines():
        if line.startswith("## "):
            flush()
            current_section = line.lstrip("# ").strip()
            current_subsection = ""
        elif line.startswith("### "):
            flush()
            current_subsection = line.lstrip("# ").strip()
        elif line.strip():
            current_text_lines.append(line)

    flush()
    return chunks


def index_all(run_dir: Path) -> dict[str, int | bool]:
    """Index all RAG data sources for a run directory."""
    if settings.DEMO_OFFLINE_MODE or not settings.GEMINI_API_KEY:
        logger.info("RAG indexing skipped (demo offline mode or missing Gemini API key).")
        return {"reviews": 0, "products": 0, "policies": 0, "skipped": True}

    run_id = run_dir.name
    run_signature = _build_run_signature(run_dir)

    if _indexed_runs.get(run_id) == run_signature:
        logger.info("Bu run zaten indekslenmiş: %s", run_id)
        return {"reviews": 0, "products": 0, "policies": 0, "skipped": True}

    client = get_qdrant_client()
    _delete_run_points(client, run_id)

    results: dict[str, int | bool] = {
        "reviews": index_reviews(run_dir, run_id=run_id),
        "products": index_product_descriptions(run_dir, run_id=run_id),
        "policies": index_policies(),
        "skipped": False,
    }

    _indexed_runs[run_id] = run_signature
    total = int(results["reviews"]) + int(results["products"]) + int(results["policies"])

    logger.info(
        "✅ RAG indexing tamamlandı: %s toplam vektör "
        "(reviews=%s, products=%s, policies=%s)",
        total,
        results["reviews"],
        results["products"],
        results["policies"],
    )

    return results


# ── Semantic Search Functions ──────────────────────────


def _search_points(
    client: Any,
    *,
    collection_name: str,
    query_vector: list[float],
    limit: int,
    query_filter: Any | None = None,
) -> list[Any]:
    """Run vector search with compatibility for older/newer qdrant-client APIs."""
    if hasattr(client, "search"):
        return client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
        )

    response = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
    )
    return list(getattr(response, "points", response))


def _scroll_points(
    client: Any,
    *,
    collection_name: str,
    scroll_filter: Any,
    limit: int,
) -> list[Any]:
    points, _next_offset = client.scroll(
        collection_name=collection_name,
        scroll_filter=scroll_filter,
        limit=limit,
    )
    return list(points)


def _hit_to_dict(hit: Any) -> dict[str, Any]:
    payload = _payload_to_dict(getattr(hit, "payload", None))
    hit_id = getattr(hit, "id", "")
    score = getattr(hit, "score", 1.0)

    return {
        **payload,
        "score": round(float(score), 4),
        "reference_id": (
            payload.get("review_id")
            or payload.get("sku")
            or payload.get("chunk_id")
            or f"qdrant:{hit_id}"
        ),
    }


def search_reviews_by_sku(
    run_id: str,
    sku: str,
    query: str | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Search reviews by SKU with optional semantic query."""
    client = get_qdrant_client()
    sku_filter = _build_run_filter(run_id=run_id, sku=sku)

    query_vector: list[float] | None = None
    if query:
        try:
            query_vector = embed_text(query, task_type="RETRIEVAL_QUERY")
        except Exception as exc:
            logger.warning("Semantic review search fallback to filter-only mode: %s", exc)

    if query_vector is not None:
        results = _search_points(
            client,
            collection_name=settings.QDRANT_COLLECTION_REVIEWS,
            query_vector=query_vector,
            query_filter=sku_filter,
            limit=top_k,
        )
        return [_hit_to_dict(hit) for hit in results]

    points = _scroll_points(
        client,
        collection_name=settings.QDRANT_COLLECTION_REVIEWS,
        scroll_filter=sku_filter,
        limit=top_k,
    )
    return [_hit_to_dict(point) for point in points]


def search_product_description(
    run_id: str,
    query: str,
    sku: str | None = None,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Search product descriptions by semantic similarity."""
    client = get_qdrant_client()
    query_filter = _build_run_filter(run_id=run_id, sku=sku)

    query_vector: list[float] | None = None
    try:
        query_vector = embed_text(query, task_type="RETRIEVAL_QUERY")
    except Exception as exc:
        logger.warning("Semantic description search fallback to filter-only mode: %s", exc)

    if query_vector is not None:
        results = _search_points(
            client,
            collection_name=settings.QDRANT_COLLECTION_PRODUCTS,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=top_k,
        )
        return [_hit_to_dict(hit) for hit in results]

    points = _scroll_points(
        client,
        collection_name=settings.QDRANT_COLLECTION_PRODUCTS,
        scroll_filter=query_filter,
        limit=top_k,
    )
    return [_hit_to_dict(point) for point in points]


def search_marketplace_policy(
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Search marketplace policies by semantic similarity."""
    client = get_qdrant_client()
    query_vector = embed_text(query, task_type="RETRIEVAL_QUERY")

    results = _search_points(
        client,
        collection_name=settings.QDRANT_COLLECTION_POLICY,
        query_vector=query_vector,
        limit=top_k,
    )
    return [_hit_to_dict(hit) for hit in results]


def retrieve_root_cause_evidence(
    run_id: str,
    sku: str,
    financial_summary: str,
    top_k_reviews: int = 5,
    top_k_descriptions: int = 2,
    top_k_policies: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Retrieve evidence from reviews, product descriptions, and policies."""
    evidence: dict[str, list[dict[str, Any]]] = {
        "reviews": [],
        "product_descriptions": [],
        "policies": [],
    }

    try:
        evidence["reviews"] = search_reviews_by_sku(
            run_id=run_id,
            sku=sku,
            query=financial_summary,
            top_k=top_k_reviews,
        )
    except Exception as exc:
        logger.warning("Review araması başarısız (%s): %s", sku, exc)

    try:
        evidence["product_descriptions"] = search_product_description(
            run_id=run_id,
            query=f"{sku} {financial_summary}",
            sku=sku,
            top_k=top_k_descriptions,
        )
    except Exception as exc:
        logger.warning("Ürün açıklaması araması başarısız: %s", exc)

    try:
        evidence["policies"] = search_marketplace_policy(
            query=financial_summary,
            top_k=top_k_policies,
        )
    except Exception as exc:
        logger.warning("Politika araması başarısız: %s", exc)

    total = sum(len(items) for items in evidence.values())
    logger.info(
        "RAG evidence toplandı (%s): %s review, %s açıklama, %s politika — toplam %s",
        sku,
        len(evidence["reviews"]),
        len(evidence["product_descriptions"]),
        len(evidence["policies"]),
        total,
    )

    return evidence


async def generate_evidence_summary(
    evidence: dict[str, list[dict[str, Any]]],
    sku: str,
) -> str:
    """Generate a natural-language evidence summary using Gemini."""
    from app.services.gemini_service import generate_text

    sections: list[str] = []

    if evidence.get("reviews"):
        review_lines = []
        for review in evidence["reviews"]:
            score_str = f" (benzerlik: {review['score']:.2f})" if review.get("score") else ""
            review_lines.append(
                f'  - {review.get("rating", "?")}/5: "{review.get("comment", "")}"{score_str}'
            )

        sections.append(
            f"### Müşteri Yorumları ({len(evidence['reviews'])} adet)\n"
            + "\n".join(review_lines)
        )

    if evidence.get("product_descriptions"):
        desc_lines = [
            f"  - {description.get('name', '')}: {str(description.get('description', ''))[:200]}..."
            for description in evidence["product_descriptions"]
        ]
        sections.append("### Ürün Açıklamaları\n" + "\n".join(desc_lines))

    if evidence.get("policies"):
        policy_lines = []
        for policy in evidence["policies"]:
            section = policy.get("section", "")
            subsection = policy.get("subsection", "")
            text_preview = str(policy.get("text", ""))[:200]
            policy_lines.append(f"  - [{section} > {subsection}]: {text_preview}...")

        sections.append("### İlgili Politikalar\n" + "\n".join(policy_lines))

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
            system_instruction=(
                "Sen bir e-ticaret analiz asistanısın. Kanıtları özetlerken objektif ol "
                "ve verilere dayalı konuş."
            ),
            temperature=0.3,
        )
        return summary.strip()
    except Exception as exc:
        logger.error("Kanıt özeti oluşturulamadı: %s", exc)

        total = sum(len(items) for items in evidence.values())
        return (
            f"{sku} için {total} kanıt toplandı: "
            f"{len(evidence.get('reviews', []))} yorum, "
            f"{len(evidence.get('product_descriptions', []))} açıklama, "
            f"{len(evidence.get('policies', []))} politika."
        )
