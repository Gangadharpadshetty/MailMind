"""
Application configuration — reads from .env / environment variables.
Single Responsibility: only manages settings.
"""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM Keys ─────────────────────────────────────────────────
    groq_api_key: str = ""

    # ── Default provider ─────────────────────────────────────────
    default_provider: str = "groq"

    # ── Groq model ────────────────────────────────────────────────
    groq_model: str = "llama-3.3-70b-versatile"

    # ── Embedding model ──────────────────────────────────────────
    embed_model: str = "all-MiniLM-L6-v2"

    # ── Retrieval ─────────────────────────────────────────────────
    top_k: int = 6
    rrf_k: int = 60          # Reciprocal Rank Fusion constant

    # ── Paths ─────────────────────────────────────────────────────
    # Use Windows-friendly defaults that match this project layout
    data_dir: Path = Path("data")
    lancedb_dir: Path = Path("data/lancedb")
    runs_dir: Path = Path("runs")
    # Default Enron CSV location; you are using Data\emails.csv, so point here.
    enron_csv: Path = Path("Data/emails.csv")

    # ── App ───────────────────────────────────────────────────────
    app_title: str = "MailMind"
    app_version: str = "1.0.0"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
