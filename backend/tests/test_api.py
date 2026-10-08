import asyncio
import tempfile

import pytest
from api_helpers import FIXED, env, make_env, pdf, upload, with_gh  # noqa: F401
from fakes import failing
from samples import NO_PYTHON, RAG_PIPELINE, STRONG_AGENTIC
from starlette.testclient import TestClient

from app.llm import LLMFailure
from app.models import ScreeningResults


def post(env, *files, **params):
    return env.client.post("/screen", files=upload(*files), params=params)


# --- health / basic screening -------------------------------------------------------------

def test_health_is_minimal_and_exposes_no_configuration(env):
    response = env.client.get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


def test_single_valid_pdf(env):
    response = post(env, ("jane.pdf", pdf(STRONG_AGENTIC)))
    assert response.status_code == 200
    results = ScreeningResults.model_validate(response.json())
    assert results.batch_summary.total_resumes == 1 and results.batch_summary.eligible == 1
    top = results.eligible_candidates[0]
    assert top.rank == 1 and top.candidate_name == "Jane Doe" and top.resume_filename == "jane.pdf"
    assert top.score_breakdown.github > 0 and top.github_enrichment.status == "ok"
    assert top.llm_enrichment.status == "ok"


def test_multiple_pdfs_are_one_ranked_batch(env):
    response = post(
        env,
        ("a.pdf", pdf(STRONG_AGENTIC)),
        ("b.pdf", pdf(RAG_PIPELINE)),
        ("c.pdf", pdf(NO_PYTHON)),
    )
    results = ScreeningResults.model_validate(response.json())
    assert [(r.rank, r.resume_filename) for r in results.eligible_candidates] == [(1, "a.pdf"), (2, "b.pdf")]
    assert [r.resume_filename for r in results.rejected_candidates] == ["c.pdf"]
    assert results.rejected_candidates[0].rank is None


def test_folder_style_upload_is_just_many_files_in_one_batch(env):
    response = post(env, ("resumes/team_a/cv.pdf", pdf(STRONG_AGENTIC)), ("resumes/team_b/cv.pdf", pdf(RAG_PIPELINE)))
    names = [r["resume_filename"] for r in response.json()["eligible_candidates"]]
    assert sorted(names) == ["resumes/team_a/cv.pdf", "resumes/team_b/cv.pdf"]


def test_response_matches_the_canonical_schema_and_the_results_file(env):
    response = post(env, ("a.pdf", pdf(STRONG_AGENTIC)))
    body = ScreeningResults.model_validate(response.json())
    on_disk = ScreeningResults.model_validate_json(env.results_path.read_text())
    assert body == on_disk
    assert set(response.json()) == {
        "schema_version", "generated_at", "batch_summary", "eligible_candidates",
        "rejected_candidates", "failed_candidates", "duplicates",
    }


# --- validation ---------------------------------------------------------------------------

def test_no_files_is_rejected_with_a_useful_message(env):
    response = env.client.post("/screen")
    assert response.status_code == 422 and "files" in response.text
    assert env.factory_calls == 0
    blank = env.client.post("/screen", files=[("files", ("", b"", "application/octet-stream"))])
    assert blank.status_code in (400, 422)


def test_unsupported_file_is_a_per_file_failure_not_an_api_error(env):
    response = post(env, ("notes.docx", b"PK..."), ("ok.pdf", pdf(RAG_PIPELINE)))
    assert response.status_code == 200
    body = response.json()
    assert [c["resume_filename"] for c in body["eligible_candidates"]] == ["ok.pdf"]
    failed = body["failed_candidates"][0]
    assert failed["resume_filename"] == "notes.docx" and failed["error"]["error_type"] == "UnsupportedFormatError"


def test_only_unsupported_files_still_returns_a_result(env):
    body = post(env, ("a.exe", b"MZ"), ("b.png", b"\x89PNG")).json()
    assert body["batch_summary"]["failed"] == 2 and body["batch_summary"]["eligible"] == 0


def test_malformed_pdf_and_empty_file_do_not_crash_the_batch(env):
    response = post(
        env,
        ("good1.pdf", pdf(STRONG_AGENTIC)),
        ("corrupt.pdf", b"%PDF-1.4 definitely not a pdf"),
        ("empty.pdf", b""),
        ("good2.pdf", pdf(RAG_PIPELINE)),
    )
    assert response.status_code == 200
    summary = response.json()["batch_summary"]
    assert (summary["total_resumes"], summary["eligible"], summary["failed"]) == (4, 2, 2)
    errors = {c["resume_filename"]: c["error"]["stage"] for c in response.json()["failed_candidates"]}
    assert errors == {"corrupt.pdf": "parse", "empty.pdf": "parse"}


def test_duplicates_are_detected_and_same_names_are_disambiguated(env):
    data = pdf(RAG_PIPELINE)
    response = post(env, ("cv.pdf", data), ("copy_of_cv.pdf", data), ("cv.pdf", pdf(STRONG_AGENTIC)))
    body = response.json()
    assert body["batch_summary"]["duplicates"] == 1 and body["duplicates"][0]["reason"] == "identical_file"
    # uploads are processed in sorted-name order (deterministic): the first identical copy is kept
    assert body["duplicates"][0]["resume_filename"] == "cv.pdf"
    assert body["duplicates"][0]["duplicate_of"] == "copy_of_cv.pdf"
    assert sorted(c["resume_filename"] for c in body["eligible_candidates"]) == ["copy_of_cv.pdf", "cv (2).pdf"]


def test_hidden_files_are_skipped_like_the_cli(env):
    body = post(env, (".DS_Store", b"x"), ("a.pdf", pdf(RAG_PIPELINE))).json()
    assert body["batch_summary"]["total_resumes"] == 1
    assert post(env, (".DS_Store", b"x")).status_code == 400


def test_too_many_files_and_oversized_uploads_are_413(tmp_path):
    e = make_env(tmp_path, max_upload_files=2, max_upload_total_mb=1)
    with TestClient(e.app) as client:
        e.client = client
        assert post(e, ("a.txt", b"x"), ("b.txt", b"x"), ("c.txt", b"x")).status_code == 413
        big = b"x" * 700_000
        assert post(e, ("a.txt", big), ("b.txt", big)).status_code == 413
        assert e.factory_calls == 0


# --- options ------------------------------------------------------------------------------

def test_use_llm_false_skips_the_model(env):
    body = post(env, ("a.pdf", pdf(STRONG_AGENTIC)), use_llm="false").json()
    assert env.adapter.calls == 0
    llm = body["eligible_candidates"][0]["llm_enrichment"]
    assert (llm["status"], llm["reason"]) == ("skipped", "llm_disabled")
    assert body["eligible_candidates"][0]["github_enrichment"]["status"] == "ok"
    post(env, ("a.pdf", pdf(STRONG_AGENTIC)))  # default: full pipeline
    assert env.adapter.calls == 1


def test_use_github_false_skips_github(env):
    body = post(env, ("a.pdf", pdf(STRONG_AGENTIC)), use_github="false").json()
    assert env.github.requests == []
    top = body["eligible_candidates"][0]
    assert top["github_enrichment"]["status"] == "not_evaluated" and top["score_breakdown"]["github"] == 0
    assert top["llm_enrichment"]["status"] == "ok"


def test_rejected_candidates_trigger_neither_llm_nor_github(env):
    text = NO_PYTHON.replace("alex@example.com", "alex@example.com | github.com/janedoe")
    post(env, ("r.pdf", pdf(text)))
    assert env.adapter.calls == 0 and env.github.requests == []


# --- LLM / GitHub failures stay candidate-level ---------------------------------------------

def test_llm_and_github_failures_do_not_fail_the_request(env):
    env.adapter = failing(LLMFailure.TIMEOUT)
    flaky = with_gh(RAG_PIPELINE, "nobody-here", "Fay Flaky")  # unknown to the fake GitHub -> 404
    response = post(env, ("a.pdf", pdf(STRONG_AGENTIC)), ("b.pdf", pdf(flaky)))
    assert response.status_code == 200
    body = response.json()
    assert body["batch_summary"]["eligible"] == 2 and body["batch_summary"]["failed"] == 0
    by = {c["resume_filename"]: c for c in body["eligible_candidates"]}
    assert by["a.pdf"]["llm_enrichment"]["reason"] == "timeout"
    assert by["b.pdf"]["github_enrichment"]["status"] == "not_found"
    assert by["b.pdf"]["score_breakdown"]["github"] == 0


def test_same_github_username_is_enriched_once_within_a_request(env):
    two = (
        ("a.pdf", pdf(with_gh(RAG_PIPELINE, "shared", "Ann One"))),
        ("b.pdf", pdf(with_gh(RAG_PIPELINE, "Shared", "Bob Two"))),
    )
    post(env, *two)
    assert len(env.github.requests) == 2  # one repos + one events call for both candidates


def test_requests_do_not_share_run_state(env):
    post(env, ("a.pdf", pdf(with_gh(RAG_PIPELINE, "shared", "Ann One"))))
    second = post(env, ("b.pdf", pdf(with_gh(RAG_PIPELINE, "shared", "Bob Two")))).json()
    assert [c["resume_filename"] for c in second["eligible_candidates"]] == ["b.pdf"]
    assert second["batch_summary"]["total_resumes"] == 1
    assert len(env.github.requests) == 4  # fresh cache per request


def test_production_factory_builds_an_isolated_processor_per_call():
    from app.api.routes import get_processor_factory
    from app.config import Settings
    from app.pipeline import PipelineOptions

    factory = get_processor_factory(Settings(_env_file=None))
    a, b = factory(PipelineOptions()), factory(PipelineOptions())
    assert a is not b and a._github is not b._github and a._analyzer is not b._analyzer
    assert factory(PipelineOptions(use_llm=False, use_github=False))._analyzer is None


# --- results ------------------------------------------------------------------------------

def test_get_results_before_any_run_is_a_clean_404(env):
    response = env.client.get("/results")
    assert response.status_code == 404 and "No results yet" in response.json()["detail"]


def test_get_results_after_a_run_returns_the_same_document(env):
    posted = post(env, ("a.pdf", pdf(STRONG_AGENTIC))).json()
    fetched = env.client.get("/results")
    assert fetched.status_code == 200 and fetched.json() == posted
    ScreeningResults.model_validate(fetched.json())


def test_unreadable_results_file_is_a_generic_500(env):
    env.results_path.parent.mkdir(parents=True)
    env.results_path.write_text("{not json")
    response = env.client.get("/results")
    assert response.status_code == 500 and "not json" not in response.text


def test_a_failed_request_leaves_the_previous_results_intact(env):
    first = post(env, ("a.pdf", pdf(STRONG_AGENTIC))).json()
    before = env.results_path.read_text()

    env.fail_with = RuntimeError("boom super-secret-token-123")
    failed = post(env, ("b.pdf", pdf(RAG_PIPELINE)))
    assert failed.status_code == 500
    assert "secret" not in failed.text and "boom" not in failed.text and "Traceback" not in failed.text
    env.fail_with = None
    assert env.results_path.read_text() == before and env.client.get("/results").json() == first


def test_a_write_failure_is_a_500_and_keeps_the_previous_file(env, monkeypatch):
    post(env, ("a.pdf", pdf(STRONG_AGENTIC)))
    before = env.results_path.read_text()

    def broken(*args, **kwargs):
        raise OSError("disk full: /secret/path")

    monkeypatch.setattr("app.pipeline.results_store.os.replace", broken)
    response = post(env, ("b.pdf", pdf(RAG_PIPELINE)))
    assert response.status_code == 500 and "secret" not in response.text
    assert env.results_path.read_text() == before
    assert [p.name for p in env.results_path.parent.iterdir()] == ["results.json"]  # no stray temp file


def test_concurrent_run_is_rejected_with_409_not_queued(env):
    class Busy:
        def locked(self):
            return True

    env.app.state.screen_lock = Busy()
    response = post(env, ("a.pdf", pdf(RAG_PIPELINE)))
    assert response.status_code == 409 and env.factory_calls == 0


# --- upload safety / event loop -------------------------------------------------------------

def test_malicious_filenames_never_leave_the_temp_directory(env, tmp_path, monkeypatch):
    sandbox = tmp_path / "tmp-root"
    sandbox.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(sandbox))
    names = ["../../../etc/passwd.pdf", "..\\..\\windows\\evil.pdf", "/abs/path/cv.pdf", "C:\\Users\\me\\cv2.pdf", "a/../../b.pdf"]
    response = post(env, *[(n, pdf(with_gh(RAG_PIPELINE, "shared", f"Cand {i}") + f"\n# {i}")) for i, n in enumerate(names)])
    assert response.status_code == 200
    reported = sorted(c["resume_filename"] for c in response.json()["eligible_candidates"] + response.json()["failed_candidates"])
    assert reported == ["a/b.pdf", "abs/path/cv.pdf", "cv2.pdf", "etc/passwd.pdf", "windows/evil.pdf"]  # the parser already strips C:\\ paths
    assert list(sandbox.iterdir()) == []  # the per-request temp dir was removed
    assert not (tmp_path / "etc").exists() and not (tmp_path.parent / "etc").exists()


def test_the_api_never_nests_asyncio_run(env, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("asyncio.run() must not be called while serving a request")

    monkeypatch.setattr(asyncio, "run", forbidden)
    response = post(env, ("a.pdf", pdf(STRONG_AGENTIC)), ("b.pdf", pdf(with_gh(RAG_PIPELINE, "shared", "Bob Two"))))
    assert response.status_code == 200 and response.json()["batch_summary"]["eligible"] == 2
    assert env.client.get("/results").status_code == 200
