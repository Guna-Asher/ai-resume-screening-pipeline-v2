from samples import (
    JAVA_REACT_PYTHON_AI,
    RAG_PIPELINE,
    SKILLS_ONLY_FRAMEWORKS,
    STRONG_AGENTIC,
    THIN_WRAPPER,
)


def test_framework_names_in_skills_do_not_earn_full_ai_credit(screen):
    score = screen(SKILLS_ONLY_FRAMEWORKS).score_breakdown
    assert score.ai_project_depth <= 3
    assert score.ai_project_depth < screen(RAG_PIPELINE).score_breakdown.ai_project_depth


def test_thin_llm_wrapper_gets_penalty_with_reason_and_evidence(screen):
    score = screen(THIN_WRAPPER).score_breakdown
    assert len(score.penalties) == 1
    penalty = score.penalties[0]
    assert 5 <= penalty.amount <= 15
    assert penalty.code == "shallow_ai_project"
    assert "thin LLM/API wrapper" in penalty.reason
    assert penalty.evidence
    assert score.total_score == max(
        0,
        score.ai_project_depth + score.python_backend + score.cloud_fullstack
        + score.github + score.engineering_depth - penalty.amount,
    )


def test_strong_rag_and_agentic_score_higher_than_thin_wrapper(screen):
    thin = screen(THIN_WRAPPER).score_breakdown
    rag = screen(RAG_PIPELINE).score_breakdown
    agentic = screen(STRONG_AGENTIC).score_breakdown
    assert thin.ai_project_depth < rag.ai_project_depth < agentic.ai_project_depth
    assert agentic.ai_project_depth >= 30
    assert rag.ai_project_depth >= 3 * thin.ai_project_depth
    assert rag.penalties == [] and agentic.penalties == []


def test_one_real_project_cancels_penalty_for_a_side_chatbot(screen):
    text = RAG_PIPELINE + "\nSide Bot\n• Made a chatbot using OpenAI API\n"
    assert screen(text).score_breakdown.penalties == []


def test_github_defaults_to_zero_and_does_not_fail_candidate(screen):
    result = screen(STRONG_AGENTIC)
    assert result.eligible
    assert result.score_breakdown.github == 0
    assert result.score_breakdown.github_status == "not_evaluated"
    assert result.github_enrichment.status == "not_evaluated"
    # a resume with no GitHub link at all is still eligible
    no_gh = screen(RAG_PIPELINE)
    assert no_gh.eligible and no_gh.github_url is None


def test_category_caps_and_total_never_exceed_limits(screen):
    s = screen(STRONG_AGENTIC).score_breakdown
    assert s.ai_project_depth <= 40 and s.python_backend <= 30
    assert s.cloud_fullstack <= 15 and s.engineering_depth <= 5
    assert 0 <= s.total_score <= 100


def test_every_score_point_has_a_ledger_entry_with_evidence(screen):
    s = screen(STRONG_AGENTIC).score_breakdown
    for item in s.score_evidence:
        if item.points > 0 and item.category != "github":
            assert item.evidence, f"{item.signal} earned points without evidence"
    assert {i.category for i in s.score_evidence} == {
        "ai_project_depth", "python_backend", "cloud_fullstack", "github", "engineering_depth",
    }


def test_project_work_evidence_beats_skills_list_for_backend(screen):
    skills_only = screen(
        "A B\n\nSKILLS\nPython, FastAPI, Redis, LangChain\n\nPROJECTS\nBot\n• Built an agentic workflow with tool calling\n"
    ).score_breakdown
    in_project = screen(
        "A B\n\nSKILLS\nPython, LangChain\n\nPROJECTS\nBot\n• Built an agentic workflow with tool calling "
        "using FastAPI and Redis in Python\n"
    ).score_breakdown
    assert in_project.python_backend > skills_only.python_backend


def test_project_summary_lists_depth_signals(screen):
    result = screen(JAVA_REACT_PYTHON_AI)
    project = result.project_summary[0]
    assert project.name == "Document QA Assistant"
    assert "retrieval" in project.ai_signals and project.ai_depth_points
    assert project.shallow is False
