"""
Application settings and configuration
"""
import os
from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings from environment variables"""

    # Basic app settings
    TESTING_FLOW: bool = Field(default=False)
    DEBUG: bool = Field(default=False)
    APP_NAME: str = Field(default="After-Hours Service")
    SECRET_KEY: str = Field(default="change-this-in-production")

    # JWT Authentication settings
    JWT_SECRET_KEY: str = Field(
        default="change-this-jwt-secret-in-production-use-long-random-string"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)  # 1 hour
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30)  # 30 days

    # Server settings
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    EMAIL_HOST: str = "smtp.gmail.com"  # or your SMTP provider
    EMAIL_PORT: int = 587
    EMAIL_USE_TLS: bool = True
    EMAIL_USERNAME: str = "voxiodesk@gmail.com"  # Your SMTP username
    EMAIL_PASSWORD: str = "ytwk sigq ssyn nnmi"  # Your SMTP password or app password
    EMAIL_FROM_ADDRESS: str = "voxiodesk@gmail.com"
    EMAIL_FROM_NAME: str = "VoxioDesk"

    # Frontend settings
    FRONTEND_URL: str = Field(default="http://localhost:3000")

    # Database settings
    DATABASE_URL: str = Field(
        default="postgresql://user:password@localhost:5432/afterhours"
    )
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)

    # Redis settings
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_MAX_CONNECTIONS: int = Field(default=50)

    # Celery settings
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")
    CELERY_TASK_SERIALIZER: str = Field(default="json")

    # Twilio settings
    TWILIO_ACCOUNT_SID: str = Field(default="")
    TWILIO_AUTH_TOKEN: str = Field(default="")
    TWILIO_WEBHOOK_SECRET: str = Field(default="")

    # OpenAI settings
    OPENAI_API_KEY: str = Field(default="")
    OPENAI_MODEL: str = Field(default="gpt-4")
    OPENAI_MAX_TOKENS: int = Field(default=500)

    # Google Calendar settings
    GOOGLE_CREDENTIALS_PATH: Optional[str] = None
    GOOGLE_CLIENT_ID: str = Field(default="")
    GOOGLE_CLIENT_SECRET: str = Field(default="")
    GOOGLE_REDIRECT_URI: str = Field(default="http://localhost:3000/callback/google")

    # Business settings
    DEFAULT_TIMEZONE: str = Field(default="UTC")
    CONVERSATION_TIMEOUT_HOURS: int = Field(default=2)
    MAX_RETRY_ATTEMPTS: int = Field(default=3)

    # Fernes settings
    CALENDAR_ENCRYPTION_KEY: str = Field(default="")

    # Monitoring settings
    ENABLE_METRICS: bool = Field(default=True)
    LOG_LEVEL: str = Field(default="INFO")

    # ==========================================
    # RAG (Retrieval-Augmented Generation) Settings
    # ==========================================

    # Embedding Model Configuration
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

    # Vector Search Configuration
    RAG_SIMILARITY_THRESHOLD: float = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.7"))
    RAG_MAX_CONTEXT_CHUNKS: int = int(os.getenv("RAG_MAX_CONTEXT_CHUNKS", "5"))

    # Indexing Configuration
    RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "500"))  # Max chars per chunk
    RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))  # Overlap between chunks

    # Performance Settings
    RAG_CACHE_TTL: int = int(os.getenv("RAG_CACHE_TTL", "3600"))  # Cache embeddings for 1 hour
    RAG_BATCH_SIZE: int = int(os.getenv("RAG_BATCH_SIZE", "10"))  # Batch size for bulk indexing

    # Feature Flags
    RAG_ENABLED: bool = os.getenv("RAG_ENABLED", "true").lower() == "true"
    RAG_AUTO_REINDEX: bool = os.getenv("RAG_AUTO_REINDEX", "false").lower() == "true"

    # Logging
    RAG_LOG_QUERIES: bool = os.getenv("RAG_LOG_QUERIES", "true").lower() == "true"
    RAG_LOG_RETRIEVALS: bool = os.getenv("RAG_LOG_RETRIEVALS", "true").lower() == "true"

    # ✅ New Pydantic v2 config style
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # allows extra env vars without breaking
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience accessor for settings
settings = get_settings()