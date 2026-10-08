from samples import STRONG_AGENTIC

from app.extraction.fields import extract_github_profile, extract_name
from app.extraction.projects import parse_projects
from app.config import Settings
from conftest import make_candidate


def test_extracts_core_fields():
    c = make_candidate(STRONG_AGENTIC)
    assert c.candidate_name == "Jane Doe"
    assert c.email == "jane.doe@example.com"
    assert c.github_url == "https://github.com/janedoe"
    assert {"Python", "FastAPI", "LangGraph"} <= set(c.skills)
    assert [p.name for p in c.projects] == ["Research Assistant Agent"]
    assert c.parse_warnings == []


def test_missing_fields_become_warnings_not_errors():
    c = make_candidate("just some text without structure")
    assert c.candidate_name is None and c.email is None and c.projects == []
    assert any("name" in w for w in c.parse_warnings)


def test_github_repo_link_resolves_to_profile():
    assert extract_github_profile("see github.com/jane/cool-repo.git") == "https://github.com/jane"
    assert extract_github_profile("github.com/features") is None


def test_name_ignores_contact_and_title_lines():
    assert extract_name(["Software Engineer", "JANE DOE | jane@x.com"]) == "Jane Doe"


def test_projects_split_on_titles_and_blank_lines():
    projects = parse_projects(
        ["Alpha | Python", "• did a", "• did b", "", "Beta", "Tech: Python, Redis", "• did c"]
    )
    assert [p.name for p in projects] == ["Alpha", "Beta"]
    assert projects[1].technologies == ["Python", "Redis"]


def test_settings_tolerate_missing_values(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.llm_api_key is None and s.github_token is None
    monkeypatch.setenv("LLM_API_KEY", "secret-value")
    assert "secret-value" not in repr(Settings(_env_file=None))


def test_health_endpoint():
    from fastapi.testclient import TestClient

    from app.api import app

    assert TestClient(app).get("/health").json()["status"] == "ok"
