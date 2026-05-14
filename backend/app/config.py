import os
from pathlib import Path

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_REVIEWS: str = "reviews_index"
    QDRANT_COLLECTION_PRODUCTS: str = "product_description_index"
    QDRANT_COLLECTION_POLICY: str = "policy_index"

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "app" / "data" / "uploads"
    MOCK_DIR: Path = BASE_DIR / "app" / "data" / "mock"
    DB_PATH: Path = BASE_DIR / "app" / "data" / "karguard.db"

    # App
    APP_NAME: str = "KârGuard AI"
    DEBUG: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# Ensure directories exist
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.MOCK_DIR.mkdir(parents=True, exist_ok=True)
