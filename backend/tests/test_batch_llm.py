import json
from datetime import UTC, datetime

import pytest
import stub_llm_server
from conftest import screen_text
from fakes import FakeAdapter, analysis_json, failing, project
from samples import (
    NO_PYTHON,
    PARAPHRASED_RAG,
    PARAPHRASED_RAG_QUOTE,
    RAG_PIPELINE,
    STRONG_AGENTIC,
)

from app.config import Settings
from app.llm import LLMFailure, SemanticAnalyzer
from app.models import ScreeningResults
from app.screening.batch import BatchProcessor

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def items(files):
    return [(n, (lambda d=d: d.encode())) for n, d in files.items()]


def processor(analyzer):
    return BatchProcessor(analyzer=analyzer, clock=lambda: NOW)


def reply_for(user: str) -> str:
    if "Policy Assistant" in user:
        return analysis_json(
            project(
                "Policy Assistant",
                ("rag", PARAPHRASED_RAG_QUOTE),
                ("embeddings", PARAPHRASED_RAG_QUOTE),
                ("testing", "Wrote checks that run on every commit"),
            )
        )
    return analysis_json(project("Document QA", ("rag", "Built a RAG pipeline with document chunking, embeddings, vector retrieval and citations")))


def test_only_eligible_candidates_reach_the_llm():
    adapter = FakeAdapter(reply_for)
    results = processor(SemanticAnalyzer(adapter)).process(
        items({"good.txt": PARAPHRASED_RAG, "bad.txt": NO_PYTHON})
    )
    assert adapter.calls == 1 and "Smart Search" not in adapter.prompts[0]
    assert [r.resume_filename for r in results.eligible_candidates] == ["good.txt"]
    assert results.rejected_candidates[0].llm_enrichment.reason == "not_eligible"
    assert results.batch_summary.llm_status_counts == {"ok": 1, "skipped": 1}


def test_semantic_evidence_changes_the_ranking_inputs():
    plain = BatchProcessor(clock=lambda: NOW).process(items({"a.txt": PARAPHRASED_RAG}))
    llm = processor(SemanticAnalyzer(FakeAdapter(reply_for))).process(items({"a.txt": PARAPHRASED_RAG}))
    assert plain.eligible_candidates[0].llm_enrichment.reason == "llm_disabled"
    assert llm.eligible_candidates[0].score_breakdown.total_score > plain.eligible_candidates[0].score_breakdown.total_score


def test_one_llm_failure_does_not_stop_the_batch_or_change_that_candidates_baseline():
    def reply(user: str) -> str:
        if "Research Assistant Agent" in user:
            raise failing(LLMFailure.TIMEOUT).error
        return reply_for(user)

    files = {"a.txt": STRONG_AGENTIC, "b.txt": PARAPHRASED_RAG, "c.txt": RAG_PIPELINE, "d.txt": NO_PYTHON}
    results = processor(SemanticAnalyzer(FakeAdapter(reply), max_concurrency=2)).process(items(files))
    s = results.batch_summary
    assert (s.eligible, s.rejected, s.failed) == (3, 1, 0)
    assert s.llm_status_counts == {"failed": 1, "ok": 2, "skipped": 1}
    by_name = {r.resume_filename: r for r in results.eligible_candidates}
    assert by_name["a.txt"].llm_enrichment.reason == "timeout"
    assert by_name["a.txt"].score_breakdown == screen_text(STRONG_AGENTIC, "a.txt").score_breakdown
    assert [r.rank for r in results.eligible_candidates] == [1, 2, 3]


def test_missing_api_key_finishes_the_batch_with_deterministic_scores():
    analyzer = SemanticAnalyzer.from_settings(Settings(_env_file=None, llm_provider="openrouter", llm_model="m"))
    results = processor(analyzer).process(items({"a.txt": STRONG_AGENTIC, "b.txt": NO_PYTHON}))
    assert results.batch_summary.llm_status_counts == {"skipped": 1, "unavailable": 1}
    top = results.eligible_candidates[0]
    assert (top.llm_enrichment.status, top.llm_enrichment.reason) == ("unavailable", "missing_api_key")
    assert top.score_breakdown == screen_text(STRONG_AGENTIC, "a.txt").score_breakdown


def test_results_json_has_no_raw_output_prompts_or_secrets():
    secret = "sk-live-VERY-SECRET"
    adapter = FakeAdapter(lambda u: analysis_json(
        project("Policy Assistant", ("rag", PARAPHRASED_RAG_QUOTE), leaked_field="RAW-SENTINEL")))
    results = processor(SemanticAnalyzer(adapter)).process(items({"a.txt": PARAPHRASED_RAG}))
    blob = results.model_dump_json()
    json.loads(blob)
    assert ScreeningResults.model_validate_json(blob) == results
    for forbidden in ("RAW-SENTINEL", "RESUME START", "You extract structured", secret):
        assert forbidden not in blob


# --- real adapter against a local OpenAI-compatible stub (no external network) -----------------

@pytest.fixture
def stub():
    server, url = stub_llm_server.start()
    yield server, url
    server.shutdown()


def stub_analyzer(url, timeout=0.5):
    settings = Settings(
        _env_file=None, llm_provider="openai_compatible", llm_model="stub", llm_api_key="stub-key",
        llm_base_url=url, llm_timeout_seconds=timeout, llm_max_concurrency=2,
    )
    return SemanticAnalyzer.from_settings(settings)


def with_marker(text: str, marker: str) -> str:
    return text + f"\nMarker Project\n• {marker} built an agent with the OpenAI API\n"


def test_end_to_end_with_real_adapter_and_failure_modes(stub):
    _, url = stub
    files = {
        "ok.txt": PARAPHRASED_RAG,
        "http500.txt": with_marker(RAG_PIPELINE, "STUB:500"),
        "malformed.txt": with_marker(STRONG_AGENTIC, "STUB:MALFORMED"),
        "slow.txt": with_marker(RAG_PIPELINE.replace("Ravi", "Slow"), "STUB:SLOW"),
        "rejected.txt": NO_PYTHON,
    }
    results = processor(stub_analyzer(url)).process(items(files))
    by_name = {r.resume_filename: r for r in results.eligible_candidates}

    assert results.batch_summary.failed == 0 and results.batch_summary.eligible == 4
    assert by_name["ok.txt"].llm_enrichment.status == "ok"
    assert by_name["ok.txt"].score_breakdown.penalties == []  # stub reported retrieval semantically
    assert by_name["http500.txt"].llm_enrichment.reason == "api_error"
    assert by_name["malformed.txt"].llm_enrichment.reason == "invalid_json"
    assert by_name["slow.txt"].llm_enrichment.reason == "timeout"
    blob = results.model_dump_json()
    assert "SECRET-PROVIDER-ERROR-BODY" not in blob and "stub-key" not in blob
