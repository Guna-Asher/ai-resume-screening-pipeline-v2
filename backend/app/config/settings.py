"""Runtime configuration, read from environment variables / a local ``.env`` file.

Every value is optional: the deterministic screening engine needs no
configuration, and the LLM / GitHub integrations arrive in later steps.
Secrets are held as ``SecretStr`` so they never show up in ``repr`` or logs.
"""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_PROJECT_ROOT / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    python_env: str = "development"
    log_level: str = "INFO"

    # Used from a later step (LLM semantic extraction behind a provider adapter).
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None

    # Used from a later step (GitHub enrichment).
    github_token: SecretStr | None = None


def load_settings() -> Settings:
    """Build settings from the environment. Missing values are fine."""
    return Settings()
