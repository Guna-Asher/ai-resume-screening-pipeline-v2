from samples import (
    AI_ONLY_AS_BARE_KEYWORD,
    JAVA_REACT_PYTHON_AI,
    NO_PYTHON,
    PYTHON_NO_AI,
    PYTHON_ONLY_IN_TUTORIAL,
    SKILLS_ONLY_FRAMEWORKS,
    STRONG_AGENTIC,
    THIN_WRAPPER,
)


def test_python_and_ai_is_eligible(screen):
    result = screen(STRONG_AGENTIC)
    assert result.eligible
    assert result.rejection_reasons == []
    assert result.eligibility.python_passed and result.eligibility.ai_passed
    assert result.score_breakdown is not None


def test_no_python_is_rejected_even_with_strong_ai(screen):
    result = screen(NO_PYTHON)
    assert not result.eligible
    assert result.score_breakdown is None and result.rank is None
    assert any("Python" in r for r in result.rejection_reasons)
    assert not any("AI/LLM" in r for r in result.rejection_reasons)
    assert "Java" in result.matched_skills  # rejected candidates still show evidence


def test_python_without_meaningful_ai_is_rejected(screen):
    result = screen(PYTHON_NO_AI)
    assert not result.eligible
    assert result.eligibility.python_passed
    assert any("AI/LLM" in r for r in result.rejection_reasons)
    assert "Python" in result.matched_skills


def test_bare_ai_keyword_in_summary_is_not_ai_evidence(screen):
    result = screen(AI_ONLY_AS_BARE_KEYWORD)
    assert not result.eligible
    assert result.eligibility.ai_evidence == [] or all(
        e.strength == "weak" for e in result.eligibility.ai_evidence
    )


def test_python_tutorial_mention_is_not_python_evidence(screen):
    result = screen(PYTHON_ONLY_IN_TUTORIAL)
    assert not result.eligible
    assert not result.eligibility.python_passed
    assert result.eligibility.ai_passed  # the AI side is real; only Python fails


def test_java_react_do_not_cause_rejection(screen):
    result = screen(JAVA_REACT_PYTHON_AI)
    assert result.eligible
    assert {"Java", "React", "Next.js", "Python"} <= set(result.matched_skills)


def test_framework_in_skills_list_passes_gate_but_is_flagged_weak(screen):
    result = screen(SKILLS_ONLY_FRAMEWORKS)
    assert result.eligible
    assert any("skills" in (e.note or "") for e in result.eligibility.ai_evidence if e.strength == "weak")


def test_thin_wrapper_is_still_eligible(screen):
    assert screen(THIN_WRAPPER).eligible
