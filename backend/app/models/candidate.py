from pydantic import BaseModel, Field

from app.models.evidence import EvidenceSource


class ResumeLine(BaseModel):
    """One line of resume text with the section it belongs to.

    All evidence detectors work on these lines, so every decision can point
    back to the exact text and section that justified it.
    """

    source: EvidenceSource
    text: str
    project: str | None = None  # project name for lines inside a project


class Project(BaseModel):
    name: str
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)  # explicit "Tech:" lines only
    github_url: str | None = None

    @property
    def description(self) -> str:
        return " ".join(self.bullets)


class Candidate(BaseModel):
    candidate_name: str | None = None
    email: str | None = None
    resume_filename: str
    resume_hash: str
    skills: list[str] = Field(default_factory=list)
    github_url: str | None = None
    projects: list[Project] = Field(default_factory=list)
    lines: list[ResumeLine] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
