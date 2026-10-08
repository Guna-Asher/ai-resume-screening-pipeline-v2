import asyncio
import json

import pytest
from conftest import make_candidate
from fakes import FakeAdapter, analysis_json, failing, project
from samples import RAG_PIPELINE, STRONG_AGENTIC

from app.config import Settings
from app.llm import LLMError, LLMFailure, SemanticAnalyzer, build_adapter, parse_analysis
from app.llm.prompts import PROMPT_VERSION, build_user_prompt

VALID = analysis_json(
    project(
        "Document QA",
        ("rag", "Built a RAG pipeline with document chunking, embeddings, vector retrieval and citations"),
        depth="substantial",
    ),
    overall_evidence=["RAG pipeline"],
)


def analyze(adapter, candidate=None, **kwargs):
    analyzer = SemanticAnalyzer(adapter, **kwargs)
    candidate = candidate or make_candidate(RAG_PIPELINE)
    return analyzer.analyze_many([candidate])[candidate.resume_hash]


def test_valid_structured_response():
    outcome = analyze(FakeAdapter(VALID))
    assert outcome.status == "ok" and outcome.reason is None
    assert outcome.model == "fake-model"
    assert outcome.analysis.projects[0].signals[0].signal == "rag"
    assert outcome.analysis.projects[0].depth_assessment == "substantial"


def test_json_inside_code_fence_or_prose_is_accepted():
    assert parse_analysis(f"```json\n{VALID}\n```").projects
    assert parse_analysis(f"Here is the analysis:\n{VALID}\nHope that helps").projects


@pytest.mark.parametrize("reply", ["this is not json", "", "{ broken", "[1, 2, 3]"])
def test_malformed_reply_is_invalid_json_or_schema_failure(reply):
    outcome = analyze(FakeAdapter(reply))
    assert outcome.status == "failed"
    assert outcome.reason in {"invalid_json", "schema_validation"}
    assert outcome.analysis is None


@pytest.mark.parametrize(
    "reply",
    [
        json.dumps({"overall_evidence": []}),  # projects missing
        json.dumps({"projects": "nope"}),  # wrong type
        json.dumps({"projects": [{"summary": "no name"}]}),  # missing project_name
        json.dumps({"projects": [{"project_name": "x", "depth_assessment": "amazing"}]}),
        json.dumps({"projects": [{"project_name": "x", "signals": [{"signal": "rag"}]}]}),
    ],
)
def test_schema_validation_failure(reply):
    outcome = analyze(FakeAdapter(reply))
    assert (outcome.status, outcome.reason) == ("failed", "schema_validation")


def test_extra_fields_such_as_score_or_penalty_are_ignored():
    reply = analysis_json(
        {**project("X", ("rag", "Built a RAG pipeline with embeddings")), "score": 99, "penalty": 0},
        total_score=100,
    )
    parsed = parse_analysis(reply)
    assert not hasattr(parsed, "total_score") and not hasattr(parsed.projects[0], "score")


def test_unknown_signal_names_do_not_invalidate_the_response():
    reply = analysis_json(project("X", ("quantum_magic", "whatever text here ok"), ("rag", "Built a RAG pipeline")))
    assert len(parse_analysis(reply).projects[0].signals) == 2  # filtered later, during grounding


def test_oversized_fields_are_clipped():
    reply = analysis_json(project("X", ("rag", "word " * 500)), overall_evidence=["a" * 5000] * 20)
    parsed = parse_analysis(reply)
    assert len(parsed.projects[0].signals[0].evidence) <= 300
    assert len(parsed.overall_evidence) <= 5 and len(parsed.overall_evidence[0]) <= 300


@pytest.mark.parametrize(
    ("category", "status"),
    [
        (LLMFailure.TIMEOUT, "failed"),
        (LLMFailure.RATE_LIMIT, "failed"),
        (LLMFailure.API_ERROR, "failed"),
        (LLMFailure.CONNECTION_ERROR, "failed"),
    ],
)
def test_adapter_errors_become_failed_outcomes(category, status):
    adapter = failing(category)
    outcome = analyze(adapter)
    assert (outcome.status, outcome.reason) == (status, category.value)
    assert adapter.calls == 1


def test_slow_model_hits_the_analyzer_timeout():
    outcome = analyze(FakeAdapter(VALID, delay=1.0), timeout_seconds=0.05)
    assert (outcome.status, outcome.reason) == ("failed", "timeout")


def test_unexpected_adapter_exception_is_contained():
    outcome = analyze(FakeAdapter(error=RuntimeError("boom with secret sk-123")))
    assert (outcome.status, outcome.reason) == ("failed", "unexpected")
    assert "sk-123" not in repr(outcome)


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"llm_provider": "openrouter", "llm_model": "m"}, "missing_api_key"),
        ({"llm_provider": "openrouter", "llm_api_key": "k"}, "missing_model"),
        ({"llm_api_key": "k", "llm_model": "m"}, "not_configured"),
        ({"llm_provider": "mystery", "llm_api_key": "k", "llm_model": "m"}, "not_configured"),
        ({"llm_provider": "openai_compatible", "llm_api_key": "k", "llm_model": "m"}, "missing_base_url"),
    ],
)
def test_missing_configuration_means_unavailable_and_no_call(kwargs, reason):
    analyzer = SemanticAnalyzer.from_settings(Settings(_env_file=None, **kwargs))
    candidate = make_candidate(RAG_PIPELINE)
    outcome = analyzer.analyze_many([candidate])[candidate.resume_hash]
    assert (outcome.status, outcome.reason) == ("unavailable", reason)
    assert outcome.analysis is None


def test_build_adapter_uses_settings_and_hides_the_key():
    adapter = build_adapter(
        Settings(_env_file=None, llm_provider="openai_compatible", llm_model="m1",
                 llm_api_key="super-secret", llm_base_url="http://localhost:9/v1")
    )
    assert adapter.model == "m1"
    assert "super-secret" not in repr(adapter)
    with pytest.raises(LLMError) as exc:
        build_adapter(Settings(_env_file=None, llm_provider="openrouter", llm_model="m"))
    assert exc.value.category == LLMFailure.MISSING_API_KEY


def test_results_are_cached_per_candidate_for_the_run():
    adapter = FakeAdapter(VALID)
    analyzer = SemanticAnalyzer(adapter)
    a = make_candidate(RAG_PIPELINE, "a.txt")
    analyzer.analyze_many([a])
    analyzer.analyze_many([a, a])
    assert adapter.calls == 1
    analyzer.analyze_many([make_candidate(STRONG_AGENTIC, "b.txt")])
    assert adapter.calls == 2


def test_failures_are_cached_too_within_a_run():
    adapter = failing(LLMFailure.RATE_LIMIT)
    analyzer = SemanticAnalyzer(adapter)
    c = make_candidate(RAG_PIPELINE)
    analyzer.analyze_many([c])
    analyzer.analyze_many([c])
    assert adapter.calls == 1


def _candidates(n):
    return [make_candidate(RAG_PIPELINE + f"\n# {i}", f"r{i}.txt") for i in range(n)]


@pytest.mark.parametrize("limit", [1, 2, 4])
def test_concurrency_is_bounded(limit):
    adapter = FakeAdapter(VALID, delay=0.05)
    analyzer = SemanticAnalyzer(adapter, max_concurrency=limit)
    outcomes = analyzer.analyze_many(_candidates(8))
    assert len(outcomes) == 8 and all(o.status == "ok" for o in outcomes.values())
    assert adapter.max_in_flight == limit


def test_one_failing_call_does_not_affect_the_others():
    def reply(user: str) -> str:
        if "# 3" in user:
            raise LLMError(LLMFailure.API_ERROR, "HTTP 500")
        return VALID

    outcomes = SemanticAnalyzer(FakeAdapter(reply), max_concurrency=3).analyze_many(_candidates(6))
    statuses = sorted(o.status for o in outcomes.values())
    assert statuses == ["failed"] + ["ok"] * 5


def test_prompt_is_versioned_excludes_contact_details_and_marks_projects():
    candidate = make_candidate(STRONG_AGENTIC)
    prompt = build_user_prompt(candidate)
    assert "jane.doe@example.com" not in prompt and "555" not in prompt and "janedoe" not in prompt
    assert "[PROJECT: Research Assistant Agent]" in prompt and "[SKILLS]" in prompt
    assert PROMPT_VERSION == "semantic-v1"


def test_analyze_async_works_inside_an_event_loop():
    async def run():
        return await SemanticAnalyzer(FakeAdapter(VALID)).analyze_async(make_candidate(RAG_PIPELINE))

    assert asyncio.run(run()).status == "ok"
