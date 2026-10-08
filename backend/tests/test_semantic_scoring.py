import json

import pytest
from conftest import make_candidate
from fakes import analysis_json, project
from samples import (
    NO_PYTHON,
    PARAPHRASED_RAG,
    PARAPHRASED_RAG_QUOTE,
    SKILLS_ONLY_FRAMEWORKS,
    STRONG_AGENTIC,
    THIN_WRAPPER,
)

from app.llm import SemanticOutcome, Signal, parse_analysis
from app.screening.engine import screen_candidate

CHATBOT_LINE = "We created a chatbot using OpenAI API"
AGENT_LINE = "Built a stateful agentic workflow with retrieval, tool calling, orchestration and an evaluation pipeline"


def outcome(*projects, **extra) -> SemanticOutcome:
    return SemanticOutcome("ok", analysis=parse_analysis(analysis_json(*projects, **extra)), model="m")


def run(text, semantic=None, name="r.txt"):
    return screen_candidate(make_candidate(text, name), semantic=semantic)


def points(result, category, signal):
    return next(i.points for i in result.score_breakdown.score_evidence if i.category == category and i.signal == signal)


# --- shallow wrapper: LLM flags it, deterministic code decides the penalty ------------------

def test_shallow_chatbot_keeps_the_deterministic_penalty_and_notes_the_semantic_flag():
    sem = outcome(project("Chatbot", ("llm_usage", CHATBOT_LINE), shallow=True, depth="shallow"))
    base, with_llm = run(THIN_WRAPPER), run(THIN_WRAPPER, sem)
    penalty = with_llm.score_breakdown.penalties[0]
    assert penalty.code == "shallow_ai_project"
    assert penalty.amount == base.score_breakdown.penalties[0].amount == 15
    assert 5 <= penalty.amount <= 15
    assert "semantic analysis also judged it a shallow wrapper" in penalty.reason
    assert with_llm.score_breakdown.total_score == base.score_breakdown.total_score
    summary = with_llm.project_summary[0]
    assert summary.semantic_shallow_wrapper is True and summary.semantic_depth == "shallow"


def test_llm_cannot_set_its_own_penalty_or_score():
    reply = {
        **project("Chatbot", ("llm_usage", CHATBOT_LINE), shallow=False, depth="substantial"),
        "penalty": 0, "score": 100, "total_score": 100,
    }
    result = run(THIN_WRAPPER, outcome(reply, penalty=0, total_score=100))
    assert result.score_breakdown.penalties[0].amount == 15  # still derived from rules + grounded signals
    assert result.score_breakdown.total_score == run(THIN_WRAPPER).score_breakdown.total_score


# --- semantic evidence changes the deterministic score ------------------------------------

def test_meaningful_rag_found_only_semantically_raises_score_and_removes_penalty():
    baseline = run(PARAPHRASED_RAG)
    assert baseline.score_breakdown.penalties  # rules alone see a thin OpenAI wrapper

    sem = outcome(
        project(
            "Policy Assistant",
            ("rag", PARAPHRASED_RAG_QUOTE),
            ("embeddings", PARAPHRASED_RAG_QUOTE),
            ("llm_usage", PARAPHRASED_RAG_QUOTE),
            ("testing", "Wrote checks that run on every commit"),
            depth="substantial",
        )
    )
    result = run(PARAPHRASED_RAG, sem)
    b, a = baseline.score_breakdown, result.score_breakdown
    assert a.penalties == []
    assert a.ai_project_depth == b.ai_project_depth + 7 + 4  # retrieval + embeddings, once each
    assert a.engineering_depth == b.engineering_depth + 1  # testing
    assert a.total_score > b.total_score + 15

    ledger = {i.signal: i for i in a.score_evidence if i.category == "ai_project_depth"}
    best = ledger["best_ai_unit"]
    assert "retrieval (semantic)" in best.explanation and "embeddings_vector_store (semantic)" in best.explanation
    llm_evidence = [e for e in best.evidence if e.origin == "llm"]
    assert llm_evidence and all(e.text.startswith("Built a question-answering") for e in llm_evidence)
    assert llm_evidence[0].context == "Policy Assistant" and llm_evidence[0].source == "project"
    assert result.project_summary[0].ai_signals == ["retrieval", "embeddings_vector_store"]
    assert result.llm_enrichment.status == "ok" and result.llm_enrichment.signals_accepted == 4  # retrieval, embeddings, baseline, testing


def test_semantic_agent_result_adds_nothing_when_rules_already_found_everything():
    sem = outcome(
        project(
            "Research Assistant Agent",
            ("agents", AGENT_LINE), ("state_management", AGENT_LINE), ("orchestration", AGENT_LINE),
            ("tool_calling", AGENT_LINE), ("rag", AGENT_LINE), ("evaluation", AGENT_LINE),
            depth="substantial",
        )
    )
    base, with_llm = run(STRONG_AGENTIC), run(STRONG_AGENTIC, sem)
    assert with_llm.score_breakdown.model_dump(exclude={"score_evidence"}) == base.score_breakdown.model_dump(exclude={"score_evidence"})
    assert with_llm.llm_enrichment.status == "ok"


def test_aliases_and_keyword_soup_cannot_double_count():
    once = outcome(project("Policy Assistant", ("rag", PARAPHRASED_RAG_QUOTE)))
    aliases = outcome(
        project(
            "Policy Assistant",
            ("rag", PARAPHRASED_RAG_QUOTE), ("vector_search", PARAPHRASED_RAG_QUOTE),
            ("rag", PARAPHRASED_RAG_QUOTE),
        )
    )
    assert run(PARAPHRASED_RAG, once).score_breakdown.ai_project_depth == run(PARAPHRASED_RAG, aliases).score_breakdown.ai_project_depth

    soup = outcome(project("Policy Assistant", *[(s.value, PARAPHRASED_RAG_QUOTE) for s in Signal]))
    s = run(PARAPHRASED_RAG, soup).score_breakdown
    assert s.ai_project_depth <= 40 and s.python_backend <= 30 and s.cloud_fullstack <= 15
    assert s.engineering_depth <= 5 and s.total_score <= 100
    # one sentence can earn each distinct target at most once: 5 baseline + 7+4+5+6+5+5+4+3 = 44 -> capped 40
    assert s.ai_project_depth == 40


# --- grounding: no evidence in the resume, no points -------------------------------------

def test_invented_quote_is_discarded():
    sem = outcome(project("Policy Assistant", ("rag", "Implemented a Pinecone hybrid search engine with rerankers")))
    result = run(PARAPHRASED_RAG, sem)
    assert result.score_breakdown.total_score == run(PARAPHRASED_RAG).score_breakdown.total_score
    assert result.llm_enrichment.signals_accepted == 0
    assert result.llm_enrichment.rejected_signals == {"ungrounded": 1}


def test_skills_list_and_tutorial_lines_earn_nothing_from_the_llm():
    text = SKILLS_ONLY_FRAMEWORKS + "\nCERTIFICATIONS\nCompleted a RAG tutorial course on Udemy\n"
    sem = outcome(
        project(
            "n/a",
            ("rag", "AI: LangChain, LangGraph, LlamaIndex, RAG, Google ADK"),
            ("rag", "Completed a RAG tutorial course on Udemy"),
        )
    )
    result = run(text, sem)
    assert result.score_breakdown.ai_project_depth == run(text).score_breakdown.ai_project_depth
    assert result.llm_enrichment.rejected_signals == {"not_implementation": 2}


def test_unknown_and_python_signals_are_not_scored():
    sem = outcome(project("Policy Assistant", ("quantum_magic", PARAPHRASED_RAG_QUOTE), ("python", PARAPHRASED_RAG_QUOTE)))
    result = run(PARAPHRASED_RAG, sem)
    assert result.llm_enrichment.rejected_signals == {"unknown_signal": 1, "not_scored": 1}
    assert result.score_breakdown.total_score == run(PARAPHRASED_RAG).score_breakdown.total_score


def test_cloud_backend_and_engineering_signals_upgrade_only_their_own_rule():
    text = "A B\n\nSKILLS\nPython, LangChain\n\nPROJECTS\nBot\n• Built an agentic workflow with tool calling\n• Shipped it packaged as one image to our cloud\n"
    base = run(text).score_breakdown
    sem = outcome(project("Bot", ("deployment", "Shipped it packaged as one image to our cloud")))
    after = run(text, sem).score_breakdown
    assert after.cloud_fullstack == base.cloud_fullstack + 4
    assert after.python_backend == base.python_backend and after.ai_project_depth == base.ai_project_depth


# --- failure & eligibility ------------------------------------------------------------------

@pytest.mark.parametrize(
    ("status", "reason"),
    [("failed", "timeout"), ("failed", "invalid_json"), ("unavailable", "missing_api_key")],
)
def test_llm_failure_preserves_the_deterministic_result(status, reason):
    baseline = run(PARAPHRASED_RAG)
    result = run(PARAPHRASED_RAG, SemanticOutcome(status, reason=reason, model="m"))
    assert result.eligible
    assert result.score_breakdown == baseline.score_breakdown
    assert (result.llm_enrichment.status, result.llm_enrichment.reason) == (status, reason)


def test_semantic_output_can_never_make_a_rejected_candidate_eligible():
    sem = outcome(project("Smart Search", ("rag", "Built a RAG pipeline in Java with embeddings and vector search"), ("python", "Built a RAG pipeline in Java")))
    result = run(NO_PYTHON, sem)
    assert not result.eligible and result.score_breakdown is None and result.rank is None
    assert result.llm_enrichment.status == "skipped" and result.llm_enrichment.reason == "not_eligible"


def test_no_llm_outcome_is_reported_as_skipped():
    result = run(PARAPHRASED_RAG)
    assert (result.llm_enrichment.status, result.llm_enrichment.reason) == ("skipped", "llm_disabled")


def test_enrichment_is_concise_json_without_raw_model_output():
    sem = outcome(
        project("Policy Assistant", ("rag", PARAPHRASED_RAG_QUOTE), raw_dump="RAW-MODEL-OUTPUT-SENTINEL"),
        overall_evidence=["Single project"], confidence_notes=["No metrics given"],
    )
    payload = json.loads(run(PARAPHRASED_RAG, sem).model_dump_json())
    assert "RAW-MODEL-OUTPUT-SENTINEL" not in json.dumps(payload)
    assert payload["llm_enrichment"]["overall_evidence"] == ["Single project"]
    assert set(payload["llm_enrichment"]) == {
        "status", "reason", "model", "signals_accepted", "rejected_signals",
        "overall_evidence", "confidence_notes",
    }
