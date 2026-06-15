"""Production configuration via pydantic-settings.

All values are read from the environment (or a `.env` file). Secrets MUST be
injected at runtime from an HSM/KMS in a real sovereign deployment — the
defaults here are safe-but-inert placeholders so the app can still boot for
local checks. Anything carrying real data MUST be overridden in production.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.production",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- environment -------------------------------------------------------
    ENV: str = "production"
    APP_TITLE: str = "DRISHTI — Crime Intelligence Platform (Production)"
    APP_VERSION: str = "1.0-prod"

    # ---- relational + spatial store (Postgres/PostGIS) ---------------------
    # Default to a local SQLite file so the app boots without a live Postgres
    # for import/compile checks. Production overrides with a postgres URL.
    DATABASE_URL: str = "sqlite:///./drishti_prod.db"

    # ---- graph store (Neo4j) ----------------------------------------------
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j"

    # ---- vector store (Qdrant) --------------------------------------------
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_COLLECTION: str = "drishti_firs"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ---- assistant LLM -----------------------------------------------------
    LLM_PROVIDER: str = "none"          # none | anthropic | groq | openai
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""

    # ---- auth / JWT --------------------------------------------------------
    JWT_SECRET: str = "CHANGE_ME_dev_only_jwt_secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MIN: int = 60

    # ---- field encryption (envelope) --------------------------------------
    # 32-byte url-safe base64 Fernet key. Empty => a deterministic dev key is
    # derived at runtime (NEVER use the dev key in production).
    MASTER_ENCRYPTION_KEY: str = ""

    # ---- rate limiting -----------------------------------------------------
    RATE_LIMIT_PER_MIN: int = 120

    # ---- CORS (comma-separated string; parsed by cors_list) ----------------
    CORS_ORIGINS: str = "https://drishti.example.gov.in"

    # ---- default seeded admin (first boot only) ---------------------------
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "CHANGE_ME_admin"
    ADMIN_FULL_NAME: str = "DRISHTI Administrator"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() in ("production", "prod")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
