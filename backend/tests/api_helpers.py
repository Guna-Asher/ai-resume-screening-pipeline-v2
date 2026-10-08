from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fakes import FakeAdapter, analysis_json
from github_fakes import NOW, STRONG_USER, FakeGitHub
from pdf_utils import pdf_from_text
from samples import NO_PYTHON, RAG_PIPELINE, STRONG_AGENTIC
from starlette.testclient import TestClient

from app.api import create_app
from app.api.routes import get_processor_factory, get_results_path, get_settings
from app.config import Settings
from app.github import GitHubClient, GitHubEnricher
from app.llm import SemanticAnalyzer
from app.screening.batch import BatchProcessor

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def with_gh(text: str, username: str, name: str) -> str:
    return text.replace("Ravi Kumar", name).replace(
        "ravi@example.com", f"ravi@example.com | github.com/{username}"
    )


def pdf(text: str) -> bytes:
    return pdf_from_text(text)


def upload(*files: tuple[str, bytes]) -> list:
    return [("files", (name, data, "application/pdf")) for name, data in files]


def make_env(tmp_path, **settings_kwargs):
    """A TestClient whose pipeline uses fake LLM / GitHub (no network) and a temp results file."""
    settings = Settings(_env_file=None, **settings_kwargs)
    env = SimpleNamespace(
        adapter=FakeAdapter(analysis_json()),
        github=FakeGitHub({"janedoe": STRONG_USER, "shared": STRONG_USER}),
        results_path=tmp_path / "out" / "results.json",
        settings=settings,
        fail_with=None,
        factory_calls=0,
    )

    def factory(options):
        env.factory_calls += 1
        if env.fail_with:
            raise env.fail_with
        analyzer = SemanticAnalyzer(env.adapter) if options.use_llm else None
        github = None
        if options.use_github:  # a fresh enricher (and cache) per request, like production
            client = GitHubClient(base_url="http://gh.test", transport=env.github.transport)
            github = GitHubEnricher(client, clock=lambda: NOW)
        return BatchProcessor(analyzer=analyzer, github=github, clock=lambda: FIXED)

    env.app = create_app(settings)
    env.app.dependency_overrides[get_processor_factory] = lambda: factory
    env.app.dependency_overrides[get_results_path] = lambda: env.results_path
    env.app.dependency_overrides[get_settings] = lambda: settings
    return env


@pytest.fixture
def env(tmp_path):
    e = make_env(tmp_path)
    with TestClient(e.app) as client:  # keeps one event loop alive across requests
        e.client = client
        yield e
