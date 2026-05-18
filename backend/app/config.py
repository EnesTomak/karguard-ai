from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"
    GEMINI_CALL_TIMEOUT_SECONDS: int = 20
    GEMINI_MAX_RETRIES: int = 1
    GEMINI_BASE_DELAY_SECONDS: int = 2
    DEMO_OFFLINE_MODE: bool = False
    MAX_AI_SKUS_PER_RUN: int = 3

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_MODE: str = "local"  # "memory" | "local" | "server"
    QDRANT_COLLECTION_REVIEWS: str = "reviews_index"
    QDRANT_COLLECTION_PRODUCTS: str = "product_description_index"
    QDRANT_COLLECTION_POLICY: str = "policy_index"
    EMBEDDING_DIM: int = 768
    TRANSACTION_FEE_PER_ORDER: float = 2.99

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "app" / "data" / "uploads"
    MOCK_DIR: Path = BASE_DIR / "app" / "data" / "mock"
    POLICY_PATH: Path = MOCK_DIR / "marketplace_policy.md"
    BRAND_VOICE_PATH: Path = MOCK_DIR / "brand_voice.md"
    DB_PATH: Path = BASE_DIR / "app" / "data" / "karguard.db"
    QDRANT_LOCAL_PATH: Path = BASE_DIR / "app" / "data" / "qdrant_local"

    # App
    APP_NAME: str = "KârGuard AI"
    DEBUG: bool = True
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    CORS_ALLOW_CREDENTIALS: bool = True
    MAX_FILE_SIZE_MB: int = 10
    MAX_TOTAL_UPLOAD_MB: int = 50

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# Ensure directories exist
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.MOCK_DIR.mkdir(parents=True, exist_ok=True)
settings.QDRANT_LOCAL_PATH.mkdir(parents=True, exist_ok=True)
