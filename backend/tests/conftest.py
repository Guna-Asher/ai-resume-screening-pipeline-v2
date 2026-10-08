import pytest

from app.extraction import extract_candidate
from app.models import Candidate, CandidateResult
from app.screening.engine import screen_candidate


def make_candidate(text: str, filename: str = "resume.txt") -> Candidate:
    return extract_candidate(text, filename, resume_hash=f"hash-{filename}")


def screen_text(text: str, filename: str = "resume.txt") -> CandidateResult:
    return screen_candidate(make_candidate(text, filename))


@pytest.fixture
def screen():
    return screen_text


@pytest.fixture(autouse=True)
def _hermetic_llm_env(monkeypatch):
    """Tests must never pick up a developer's real LLM / GitHub configuration."""
    for var in (
        "LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL",
        "LLM_TIMEOUT_SECONDS", "LLM_MAX_CONCURRENCY", "GITHUB_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
