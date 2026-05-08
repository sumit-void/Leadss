"""
LeadGen Pro — Configuration
Reads all settings from environment variables with sensible defaults.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- PostgreSQL ---
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="leadgen", alias="POSTGRES_USER")
    postgres_password: str = Field(default="leadgen_secret_2024", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="leadgen", alias="POSTGRES_DB")

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # --- Celery ---
    celery_broker_url: str = Field(default="redis://localhost:6379/0", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/1", alias="CELERY_RESULT_BACKEND")

    # --- AI Audit (Optional — free Ollama) ---
    ollama_base_url: str = Field(default="", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3", alias="OLLAMA_MODEL")

    # --- Scraping ---
    max_search_results: int = Field(default=50, alias="MAX_SEARCH_RESULTS")
    max_search_pages: int = Field(default=3, alias="MAX_SEARCH_PAGES")
    crawl_concurrency: int = Field(default=5, alias="CRAWL_CONCURRENCY")
    request_delay_min: int = Field(default=3, alias="REQUEST_DELAY_MIN")
    request_delay_max: int = Field(default=7, alias="REQUEST_DELAY_MAX")

    # --- FastAPI ---
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    debug: bool = Field(default=False, alias="DEBUG")

    @property
    def database_url(self) -> str:
        """Async PostgreSQL connection string."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync PostgreSQL connection string (for Celery workers / Alembic)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "populate_by_name": True,
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
