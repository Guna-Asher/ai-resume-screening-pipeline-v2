"""Runtime configuration, read from environment variables / a local ``.env`` file.

Every value is optional: the deterministic screening engine needs no
configuration, and the LLM / GitHub integrations arrive in later steps.
Secrets are held as ``SecretStr`` so they never show up in ``repr`` or logs.
"""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_PROJECT_ROOT / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    python_env: str = "development"
    log_level: str = "INFO"

    # Optional LLM semantic analysis (advisory evidence only). Unset => deterministic-only run.
    llm_provider: str | None = None  # openrouter | openai | openai_compatible
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None  # overrides the provider's default endpoint
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    llm_max_concurrency: int = Field(default=3, ge=1, le=32)

    # Used from a later step (GitHub enrichment).
    github_token: SecretStr | None = None


def load_settings() -> Settings:
    """Build settings from the environment. Missing values are fine."""
    return Settings()
