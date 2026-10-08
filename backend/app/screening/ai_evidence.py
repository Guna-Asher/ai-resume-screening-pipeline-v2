"""Rule-based detection of meaningful AI / LLM / RAG / agentic evidence.

Terms live in ``rules.AI_TERMS`` (framework / technique / generic). A bare
"AI" is never evidence. Strength depends on kind and context:

                      project/work   cued claim   skills list   tutorial etc.
    framework/technique   STRONG       MODERATE     see below       WEAK
    generic (LLM, OpenAI) MODERATE     MODERATE     WEAK            WEAK

Skills list: a named *framework* (LangChain, LangGraph, ...) is MODERATE
("framework" route to eligibility, scored with minimal credit); techniques
and generic terms listed only as skills are WEAK.
"""

from collections.abc import Sequence

from app.models import Evidence, ResumeLine, Strength
from app.screening import rules
from app.screening.context import Role, classify_line, make_evidence
from app.screening.rules import AIKind, AITerm


def ai_strength(term: AITerm, role: Role) -> Strength:
    if role == Role.WEAK:
        return Strength.WEAK
    if role == Role.CUED:
        return Strength.MODERATE
    if role == Role.SKILL_LISTING:
        return Strength.MODERATE if term.kind == AIKind.FRAMEWORK else Strength.WEAK
    return Strength.MODERATE if term.kind == AIKind.GENERIC else Strength.STRONG


def matching_terms(text: str) -> list[AITerm]:
    return [t for t in rules.AI_TERMS if t.pattern.search(text)]


def detect_ai_evidence(lines: Sequence[ResumeLine]) -> list[Evidence]:
    evidence: list[Evidence] = []
    for line in lines:
        role = classify_line(line)
        for term in matching_terms(line.text):
            evidence.append(make_evidence(term.category, term.name, line, ai_strength(term, role)))
    return evidence


def qualifies(evidence: Sequence[Evidence]) -> bool:
    return any(e.strength.rank >= Strength.MODERATE.rank for e in evidence)
