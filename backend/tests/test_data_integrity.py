"""Data-integrity guarantees: every result comes from the uploaded files of THIS run.

(The fixtures used here are synthetic test data; none of it is imported by production code.)
"""

import json
import re
from pathlib import Path

import pytest
from api_helpers import env, pdf, upload, with_gh  # noqa: F401
from conftest import screen_text
from samples import (
    JAVA_REACT_PYTHON_AI, NO_PYTHON, PYTHON_NO_AI, RAG_PIPELINE, SKILLS_ONLY_FRAMEWORKS,
    STRONG_AGENTIC, THIN_WRAPPER,
)

import app as app_package
from app.extraction.text import normalize_text


def post(env, *files, **params):
    return env.client.post("/screen", files=upload(*files), params=params)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_text(text)).casefold()


# --- no leakage between runs -------------------------------------------------------------------

def test_second_batch_inherits_nothing_from_the_first(env):
    batch_a = post(env, ("alpha.pdf", pdf(STRONG_AGENTIC)), ("broken_alpha.pdf", b"%PDF-1.4 not a pdf")).json()
    batch_b_text = with_gh(RAG_PIPELINE, "shared", "Ravi Kumar")
    batch_b = post(env, ("beta.pdf", pdf(batch_b_text))).json()

    a_only = ["Jane Doe", "jane.doe@example.com", "Research Assistant Agent", "janedoe", "Acme",
              "alpha.pdf", "broken_alpha.pdf", "Chroma"]
    blob_b = json.dumps(batch_b)
    assert [t for t in a_only if t.lower() in blob_b.lower()] == []
    assert [c["resume_filename"] for c in batch_b["eligible_candidates"]] == ["beta.pdf"]
    assert batch_b["failed_candidates"] == [] and batch_b["batch_summary"]["total_resumes"] == 1
    assert batch_b["eligible_candidates"][0]["candidate_name"] == "Ravi Kumar"
    assert "Ravi" not in json.dumps(batch_a)
    # the stored "latest results" were replaced by batch B, not merged with A
    assert env.client.get("/results").json() == batch_b


def test_caches_do_not_carry_github_or_llm_data_between_runs(env):
    same_account = with_gh(RAG_PIPELINE, "shared", "Ravi Kumar")
    post(env, ("one.pdf", pdf(same_account)))
    first = len(env.github.requests)
    post(env, ("two.pdf", pdf(same_account.replace("Ravi Kumar", "Someone Else"))))
    assert len(env.github.requests) == 2 * first  # fetched again: live data per run, no cross-run cache
    assert env.adapter.calls == 2  # one LLM call per run for the one eligible candidate in each


def test_results_endpoint_has_nothing_before_the_first_run(env):
    assert not env.results_path.exists()
    assert env.client.get("/results").status_code == 404


# --- everything shown traces back to the uploaded text -----------------------------------------

@pytest.mark.parametrize(
    "text",
    [STRONG_AGENTIC, RAG_PIPELINE, THIN_WRAPPER, JAVA_REACT_PYTHON_AI, SKILLS_ONLY_FRAMEWORKS, NO_PYTHON, PYTHON_NO_AI],
)
def test_every_extracted_value_and_evidence_quote_comes_from_the_resume_text(text):
    haystack = norm(text)
    result = screen_text(text).model_dump(mode="json")
    values = [result["candidate_name"], result["email"]]
    values += [p["name"] for p in result["project_summary"]]
    if result["github_url"]:
        values.append(result["github_url"].replace("https://", ""))
    evidence = list(result["eligibility"]["python_evidence"]) + list(result["eligibility"]["ai_evidence"])
    if result["score_breakdown"]:
        evidence += [e for item in result["score_breakdown"]["score_evidence"] for e in item["evidence"]]
        evidence += [e for p in result["score_breakdown"]["penalties"] for e in p["evidence"]]
    values += [e["text"] for e in evidence]
    assert values
    for value in filter(None, values):
        assert norm(value).rstrip("…").strip() in haystack, f"not found in the resume: {value!r}"


def test_missing_fields_are_null_never_placeholders():
    result = screen_text("Built a RAG chatbot in Python using LangChain and FAISS embeddings.").model_dump(mode="json")
    assert result["candidate_name"] is None and result["email"] is None and result["github_url"] is None
    assert result["github_enrichment"]["status"] == "not_evaluated"  # no invented GitHub data
    assert result["llm_enrichment"]["status"] == "skipped"  # no invented semantic analysis
    assert not re.search(r"example\.com|@", json.dumps({k: result[k] for k in ("candidate_name", "email", "github_url")}))


def test_failed_files_never_become_candidates(env):
    body = post(env, ("junk.pdf", b"%PDF-1.4 garbage"), ("empty.pdf", b"")).json()
    assert body["eligible_candidates"] == [] and body["rejected_candidates"] == []
    for failed in body["failed_candidates"]:
        assert failed["candidate_name"] is None and failed["email"] is None
        assert failed["score_breakdown"] is None and failed["project_summary"] == []


# --- production code carries no candidate data and imports no fixtures --------------------------

def test_production_code_has_no_fixture_imports_or_embedded_candidate_data():
    root = Path(app_package.__file__).parent
    sources = {p: p.read_text(encoding="utf-8") for p in root.rglob("*.py")}
    assert len(sources) > 30
    forbidden_import = re.compile(
        r"^\s*(from|import)\s+(tests|fakes|github_fakes|api_helpers|pdf_utils|conftest|stub_\w+|samples|make_synthetic_resumes)\b", re.M)
    for path, text in sources.items():
        assert not forbidden_import.search(text), f"{path} imports test code"
        assert not re.search(r"[\w.+-]+@(example|test)\.[a-z]+", text), f"{path} embeds an email"
        assert "synthetic_resumes" not in text and "/samples" not in text, f"{path} reads sample data"
    # nothing in production reads results.json except the GET /results endpoint
    readers = [p.name for p, t in sources.items() if re.search(r"\bread_results\b", t) and p.name not in ("results_store.py", "__init__.py")]
    assert readers == ["routes.py"]
