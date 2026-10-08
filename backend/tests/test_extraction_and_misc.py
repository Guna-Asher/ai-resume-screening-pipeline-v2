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


def test_repo_links_to_several_owners_do_not_define_a_profile():
    text = "github.com/langchain-ai/langchain and github.com/jane/mine"
    assert extract_github_profile(text) is None
    assert extract_github_profile("github.com/jane/a github.com/Jane/b") == "https://github.com/jane"
    assert extract_github_profile("github.com/other/x github.com/jane  github.com/jane/b") == "https://github.com/jane"


def test_long_inline_skills_line_is_still_a_skills_section():
    # regression: a >60-character "Skills: ..." line used to be treated as plain header text
    text = (
        "Ivan Jovanovic\nivan@example.com\n"
        "Skills: Python, LangChain, LangGraph, LlamaIndex, RAG, Google ADK, FastAPI, Docker, PostgreSQL\n"
        "Projects\nInventory Tracker\n- Built a CRUD app with Django\n"
    )
    c = make_candidate(text)
    assert {"Python", "LangChain", "Docker"} <= set(c.skills)
    assert [(l.source.value) for l in c.lines if "LangChain" in l.text] == ["skills"]


def test_classic_ml_alone_is_not_ai_evidence_but_machine_learning_is_not_learning_context(screen):
    # documented design: scikit-learn / classic ML is not "AI/LLM/RAG/agentic" evidence...
    text = "A B\n\nSKILLS\nPython, scikit-learn\n\nPROJECTS\nChurn\n- Built a machine learning classifier with scikit-learn and pandas\n"
    result = screen(text)
    assert not result.eligible and result.eligibility.python_passed and not result.eligibility.ai_passed
    # ...and the phrase "machine learning" must not be mistaken for a tutorial/"learning" context
    assert all("learning/tutorial" not in (e.note or "") for e in result.eligibility.python_evidence)


def test_scikit_learn_in_a_skills_list_does_not_demote_python_to_weak(screen):
    # regression: the hyphen in "scikit-learn" made "learn" look like a learning/tutorial context
    text = "A B\n\nSKILLS\nPython, scikit-learn, LangChain\n"
    result = screen(text)
    assert result.eligibility.python_passed and result.eligible
