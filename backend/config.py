"""Environment-driven configuration.

Every deployment-varying value lives here and is read from the
environment. Nothing in this module hardcodes a domain, a provider, or
a credential -- see `.env.example` for the full key list.
"""

from __future__ import annotations

import functools
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_domains(raw: str | list[str]) -> list[str]:
    """Normalise a comma-separated domain list to lowercase, no leading '@'."""
    if isinstance(raw, str):
        parts = raw.split(",")
    else:
        parts = list(raw)
    return [p.strip().lower().lstrip("@") for p in parts if p and p.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- core ---
    public_url: str = Field("http://localhost:3000", alias="LABTUTOR_PUBLIC_URL")
    session_secret: str = Field("dev-insecure-secret", alias="LABTUTOR_SESSION_SECRET")
    env: Literal["development", "production"] = Field("development", alias="LABTUTOR_ENV")

    # --- database ---
    postgres_user: str = Field("labtutor", alias="POSTGRES_USER")
    postgres_password: str = Field("labtutor", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field("labtutor", alias="POSTGRES_DB")
    postgres_host: str = Field("localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    # Overrides the assembled Postgres URL entirely. Tests use sqlite here.
    database_url_override: str | None = Field(None, alias="LABTUTOR_DATABASE_URL")

    # --- role domains ---
    # Configurable so an additional/corrected domain never requires a code
    # change. Role determination reads ONLY these (backend/auth/roles.py).
    student_domains: list[str] = Field(
        default_factory=lambda: ["vitstudent.ac.in"], alias="LABTUTOR_STUDENT_DOMAINS"
    )
    faculty_domains: list[str] = Field(
        default_factory=lambda: ["vit.ac.in"], alias="LABTUTOR_FACULTY_DOMAINS"
    )

    # --- oauth ---
    google_client_id: str = Field("", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field("", alias="GOOGLE_CLIENT_SECRET")

    # --- llm ---
    llm_backend: Literal["hosted", "ollama"] = Field("hosted", alias="LABTUTOR_LLM_BACKEND")
    llm_base_url: str = Field("", alias="LABTUTOR_LLM_BASE_URL")
    llm_api_key: str = Field("", alias="LABTUTOR_LLM_API_KEY")
    llm_model: str = Field("", alias="LABTUTOR_LLM_MODEL")
    llm_timeout_seconds: float = Field(30.0, alias="LABTUTOR_LLM_TIMEOUT_SECONDS")
    llm_max_tokens: int = Field(400, alias="LABTUTOR_LLM_MAX_TOKENS")
    ollama_base_url: str = Field("http://localhost:11434", alias="LABTUTOR_OLLAMA_BASE_URL")
    ollama_model: str = Field("llama3.1:8b", alias="LABTUTOR_OLLAMA_MODEL")
    llm_auto_fallback: bool = Field(True, alias="LABTUTOR_LLM_AUTO_FALLBACK")

    # --- retrieval ---
    manual_pdf: str = Field("manual/BACHY105.pdf", alias="LABTUTOR_MANUAL_PDF")

    # --- rate limits ---
    ratelimit_socratic_per_minute: int = Field(12, alias="LABTUTOR_RATELIMIT_SOCRATIC_PER_MINUTE")
    ratelimit_submit_per_hour: int = Field(30, alias="LABTUTOR_RATELIMIT_SUBMIT_PER_HOUR")

    # --- summaries ---
    summary_workers: int = Field(4, alias="LABTUTOR_SUMMARY_WORKERS")

    @field_validator("student_domains", "faculty_domains", mode="before")
    @classmethod
    def _norm_domains(cls, v):
        return _split_domains(v)

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cookie_secure(self) -> bool:
        return self.env == "production"


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Clear the cache. Tests use this after mutating the environment."""
    get_settings.cache_clear()
    return get_settings()
