"""Decide how much a resume line can prove, based on where it is and how it reads."""

from enum import StrEnum

from app.extraction.text import snippet
from app.models import Evidence, EvidenceCategory, EvidenceSource, ResumeLine, Strength
from app.screening import rules


class Role(StrEnum):
    PROJECT_WORK = "project_work"  # inside a project or work/internship entry
    CUED = "cued"  # elsewhere, but phrased as having used/built something
    SKILL_LISTING = "skill_listing"  # keyword in a skills list
    WEAK = "weak"  # tutorial/coursework/learning, or a bare keyword elsewhere


def is_negative_context(text: str) -> bool:
    """Learning / passive context ("watched a tutorial"), unless an action verb shows real work."""
    cleaned = rules.LEARNING_FALSE_FRIENDS.sub(" ", text)
    return bool(rules.NEGATIVE_CONTEXT.search(cleaned)) and not rules.ACTION_VERBS.search(text)


def classify_line(line: ResumeLine) -> Role:
    if is_negative_context(line.text):
        return Role.WEAK
    if line.source in (EvidenceSource.PROJECT, EvidenceSource.EXPERIENCE):
        return Role.PROJECT_WORK
    if line.source == EvidenceSource.SKILLS:
        return Role.SKILL_LISTING
    if line.source in (EvidenceSource.EDUCATION, EvidenceSource.CERTIFICATIONS):
        # Coursework is not implementation unless the line says something was built.
        return Role.CUED if rules.ACTION_VERBS.search(line.text) else Role.WEAK
    if rules.ACTION_VERBS.search(line.text) or rules.IMPLEMENTATION_CUES.search(line.text):
        return Role.CUED
    return Role.WEAK


def weak_note(line: ResumeLine) -> str:
    if is_negative_context(line.text):
        return "learning/tutorial context, not implementation"
    if line.source == EvidenceSource.SKILLS:
        return "listed in a skills section only, no project/work evidence"
    if line.source in (EvidenceSource.EDUCATION, EvidenceSource.CERTIFICATIONS):
        return "coursework/certification mention, not implementation"
    return "bare keyword outside a project, work entry or skills list"


def make_evidence(
    category: EvidenceCategory, term: str, line: ResumeLine, strength: Strength
) -> Evidence:
    return Evidence(
        category=category,
        term=term,
        text=snippet(line.text),
        source=line.source,
        strength=strength,
        context=line.project,
        note=weak_note(line) if strength == Strength.WEAK else None,
    )
