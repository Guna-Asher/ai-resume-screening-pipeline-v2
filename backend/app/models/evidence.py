from enum import StrEnum

from pydantic import BaseModel


class EvidenceSource(StrEnum):
    """Resume section a piece of evidence came from."""

    HEADER = "header"
    SUMMARY = "summary"
    SKILLS = "skills"
    PROJECT = "project"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATIONS = "certifications"
    OTHER = "other"


class EvidenceCategory(StrEnum):
    PYTHON = "python"
    PYTHON_ECOSYSTEM = "python_ecosystem"
    AI_FRAMEWORK = "ai_framework"
    AI_TECHNIQUE = "ai_technique"
    LLM_USAGE = "llm_usage"
    BACKEND = "backend"
    CLOUD = "cloud"
    FULLSTACK = "fullstack"
    ENGINEERING = "engineering"


class Strength(StrEnum):
    """How much a piece of evidence proves.

    weak:     keyword-only / non-implementation context (tutorial, coursework, ...)
    moderate: listed skill, or a cued claim outside project/work sections
    strong:   described inside a project or work/internship entry
    """

    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"

    @property
    def rank(self) -> int:
        return _STRENGTH_RANK[self]


_STRENGTH_RANK = {Strength.WEAK: 0, Strength.MODERATE: 1, Strength.STRONG: 2}


class Evidence(BaseModel):
    category: EvidenceCategory
    term: str
    text: str  # the resume line (truncated) the match was found in
    source: EvidenceSource
    strength: Strength
    context: str | None = None  # e.g. project name
    note: str | None = None  # why the strength was downgraded, etc.
