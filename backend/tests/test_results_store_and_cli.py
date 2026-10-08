import json
import os
import stat

import pytest
from conftest import screen_text
from samples import NO_PYTHON, RAG_PIPELINE, STRONG_AGENTIC
from starlette.testclient import TestClient

import main
from api_helpers import make_env, upload
from app.models import ScreeningResults
from app.pipeline import ResultsCorruptError, ResultsNotFoundError, read_results, write_results_atomic
from app.screening.batch import BatchProcessor
from datetime import UTC, datetime


def sample_results():
    return BatchProcessor(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC)).process(
        [("a.txt", lambda: STRONG_AGENTIC.encode())]
    )


def test_atomic_write_round_trips_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "nested" / "results.json"
    results = sample_results()
    write_results_atomic(results, path)
    assert read_results(path) == results
    assert [p.name for p in path.parent.iterdir()] == ["results.json"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o644  # readable on the host mount


def test_failed_write_keeps_the_old_file_and_cleans_up(tmp_path, monkeypatch):
    path = tmp_path / "results.json"
    write_results_atomic(sample_results(), path)
    before = path.read_text()

    def boom(*a, **k):
        raise OSError("rename failed")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_results_atomic(sample_results(), path)
    assert path.read_text() == before and [p.name for p in tmp_path.iterdir()] == ["results.json"]


def test_read_results_errors(tmp_path):
    with pytest.raises(ResultsNotFoundError):
        read_results(tmp_path / "missing.json")
    (tmp_path / "bad.json").write_text(json.dumps({"nope": 1}))
    with pytest.raises(ResultsCorruptError):
        read_results(tmp_path / "bad.json")


# --- CLI -----------------------------------------------------------------------------------

def run_cli(tmp_path, *extra):
    src = tmp_path / "in"
    src.mkdir(exist_ok=True)
    return main.main(["--input", str(src), "--output", str(tmp_path / "out" / "results.json"), *extra])


def test_cli_still_works_end_to_end(tmp_path, capsys):
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.txt").write_text(STRONG_AGENTIC)
    (src / "b.txt").write_text(NO_PYTHON)
    assert run_cli(tmp_path, "--no-llm", "--no-github") == 0
    out = capsys.readouterr().out
    assert "1 eligible, 1 rejected" in out
    results = read_results(tmp_path / "out" / "results.json")
    assert results.eligible_candidates[0].resume_filename == "a.txt"


def test_cli_reports_a_missing_input_folder(tmp_path, capsys):
    assert main.main(["--input", str(tmp_path / "nope"), "--output", str(tmp_path / "o.json")]) == 2
    assert "Input directory not found" in capsys.readouterr().err


def test_cli_and_api_run_the_same_pipeline(tmp_path):
    files = {"a.txt": STRONG_AGENTIC, "b.txt": RAG_PIPELINE, "c.txt": NO_PYTHON, "d.txt": ""}
    src = tmp_path / "in"
    src.mkdir()
    for name, text in files.items():
        (src / name).write_text(text)
    assert run_cli(tmp_path, "--no-llm", "--no-github") == 0
    cli = read_results(tmp_path / "out" / "results.json")

    e = make_env(tmp_path / "api")
    with TestClient(e.app) as client:
        response = client.post(
            "/screen", params={"use_llm": "false", "use_github": "false"},
            files=[("files", (n, t.encode(), "text/plain")) for n, t in files.items()],
        )
    api = ScreeningResults.model_validate(response.json())
    assert api.model_dump(exclude={"generated_at"}) == cli.model_dump(exclude={"generated_at"})


# --- CORS / OpenAPI / settings ---------------------------------------------------------------

def preflight(client, origin):
    return client.options(
        "/screen", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                            "Access-Control-Request-Headers": "content-type"})


def test_cors_allows_only_configured_origins(tmp_path):
    e = make_env(tmp_path, cors_origins="http://localhost:3000, http://localhost:5173")
    with TestClient(e.app) as client:
        ok = preflight(client, "http://localhost:5173")
        assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:5173"
        bad = preflight(client, "http://evil.example")
        assert "access-control-allow-origin" not in bad.headers
        assert client.get("/health", headers={"Origin": "http://evil.example"}).headers.get("access-control-allow-origin") is None
        assert client.get("/health", headers={"Origin": "http://localhost:3000"}).headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_can_be_disabled_and_default_is_not_a_wildcard(tmp_path, monkeypatch):
    from app.config import Settings

    assert Settings(_env_file=None).cors_origin_list == ["http://localhost:3000"]
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test,http://b.test")
    assert Settings(_env_file=None).cors_origin_list == ["http://a.test", "http://b.test"]
    e = make_env(tmp_path, cors_origins="")
    with TestClient(e.app) as client:
        assert "access-control-allow-origin" not in client.get("/health", headers={"Origin": "http://localhost:3000"}).headers


def test_openapi_documents_the_three_endpoints(tmp_path):
    e = make_env(tmp_path)
    with TestClient(e.app) as client:
        spec = client.get("/openapi.json").json()
    assert set(spec["paths"]) == {"/health", "/screen", "/results"}
    screen = spec["paths"]["/screen"]["post"]
    assert "multipart/form-data" in screen["requestBody"]["content"]
    body_schema = spec["components"]["schemas"][screen["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"].split("/")[-1]]
    assert body_schema["properties"]["files"]["type"] == "array" and "files" in body_schema["required"]
    assert {p["name"] for p in screen["parameters"]} == {"use_llm", "use_github"}
    for path, method in (("/screen", "post"), ("/results", "get")):
        ok = spec["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]
        assert ok["$ref"].endswith("/ScreeningResults")
    assert {"400", "409", "413", "500"} <= set(screen["responses"])
    assert "404" in spec["paths"]["/results"]["get"]["responses"]
