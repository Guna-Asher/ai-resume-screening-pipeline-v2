"""Hard eligibility gate: genuine Python evidence AND meaningful AI evidence.

Fully deterministic. Other languages (Java, JavaScript, React, ...) never
affect the outcome. Missing GitHub never affects it either.
"""

from collections.abc import Sequence

from app.models import Candidate, EligibilityResult, Evidence, ResumeLine, Strength
from app.screening import ai_evidence, python_evidence, rules
from app.screening.context import Role, classify_line

MAX_EVIDENCE_PER_LIST = 15


def _top(evidence: Sequence[Evidence]) -> list[Evidence]:
    """Strongest first (stable), capped so output stays readable."""
    ordered = sorted(evidence, key=lambda e: -e.strength.rank)
    return ordered[:MAX_EVIDENCE_PER_LIST]


def collect_matched_skills(lines: Sequence[ResumeLine]) -> list[str]:
    """Canonical Python / AI / backend / cloud skill names seen in non-weak context."""
    found: set[str] = set()
    for line in lines:
        if classify_line(line) == Role.WEAK:
            continue
        text = line.text
        if rules.PYTHON_PATTERN.search(text):
            found.add("Python")
        found.update(name for name, p in rules.PYTHON_ECOSYSTEM if p.search(text))
        found.update(name for name, p in rules.SUPPORTING_SKILLS if p.search(text))
        found.update(t.name for t in ai_evidence.matching_terms(text))
    return sorted(found, key=str.casefold)


def _rejection_reason(label: str, evidence: Sequence[Evidence], needs: str) -> str:
    if not evidence:
        return f"No {label} evidence found: {needs}."
    examples = ", ".join(sorted({f"'{e.term}' ({e.note})" for e in evidence})[:3])
    return f"Only weak {label} mentions found, not genuine evidence: {examples}. Needs {needs}."


def check_eligibility(candidate: Candidate) -> EligibilityResult:
    py = python_evidence.detect_python_evidence(candidate.lines)
    ai = ai_evidence.detect_ai_evidence(candidate.lines)
    py_ok = python_evidence.qualifies(py)
    ai_ok = ai_evidence.qualifies(ai)

    reasons: list[str] = []
    if not py_ok:
        reasons.append(
            _rejection_reason(
                "Python", py, "Python in skills, a project, or work/internship experience"
            )
        )
    if not ai_ok:
        reasons.append(
            _rejection_reason(
                "AI/LLM/RAG/agentic",
                ai,
                "an AI project/implementation (RAG, agents, tool calling, embeddings, LLM app) "
                "or a named AI framework",
            )
        )

    return EligibilityResult(
        eligible=py_ok and ai_ok,
        python_passed=py_ok,
        ai_passed=ai_ok,
        python_evidence=_top(py),
        ai_evidence=_top(ai),
        matched_skills=collect_matched_skills(candidate.lines),
        rejection_reasons=reasons,
    )
