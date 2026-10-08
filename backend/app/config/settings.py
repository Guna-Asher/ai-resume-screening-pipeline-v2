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

    # API / output
    results_path: Path = Path("output/results.json")  # /app/output/results.json in Docker
    cors_origins: str = "http://localhost:3000"  # comma-separated; empty disables CORS
    max_upload_files: int = Field(default=200, ge=1, le=2000)
    max_upload_total_mb: int = Field(default=200, ge=1, le=2000)

    # GitHub enrichment (public REST API). The token is optional: it only raises rate limits.
    github_token: SecretStr | None = None
    github_api_base_url: str = "https://api.github.com"
    github_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    github_max_concurrency: int = Field(default=3, ge=1, le=16)


    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def load_settings() -> Settings:
    """Build settings from the environment. Missing values are fine."""
    return Settings()
