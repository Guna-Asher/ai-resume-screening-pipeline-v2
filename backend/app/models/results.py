from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.config.scoring import (
    AI_PROJECT_DEPTH_MAX,
    CLOUD_FULLSTACK_MAX,
    ENGINEERING_DEPTH_MAX,
    GITHUB_MAX,
    PYTHON_BACKEND_MAX,
)
from app.models.evidence import Evidence

SCHEMA_VERSION = "1.0"


class EligibilityResult(BaseModel):
    eligible: bool
    python_passed: bool
    ai_passed: bool
    python_evidence: list[Evidence] = Field(default_factory=list)
    ai_evidence: list[Evidence] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)


class GitHubStatus(StrEnum):
    NOT_EVALUATED = "not_evaluated"


class GitHubEnrichment(BaseModel):
    status: GitHubStatus = GitHubStatus.NOT_EVALUATED
    profile_url: str | None = None
    summary: str | None = "GitHub enrichment has not been evaluated yet."


class Penalty(BaseModel):
    code: str
    amount: int = Field(ge=0)
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)


class ScoreItem(BaseModel):
    """One line of the score ledger: a signal, the points it earned and why."""

    category: Literal[
        "ai_project_depth", "python_backend", "cloud_fullstack", "github", "engineering_depth"
    ]
    signal: str
    points: int
    max_points: int
    explanation: str
    evidence: list[Evidence] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    ai_project_depth: int = Field(ge=0, le=AI_PROJECT_DEPTH_MAX)
    python_backend: int = Field(ge=0, le=PYTHON_BACKEND_MAX)
    cloud_fullstack: int = Field(ge=0, le=CLOUD_FULLSTACK_MAX)
    github: int = Field(default=0, ge=0, le=GITHUB_MAX)
    github_status: GitHubStatus = GitHubStatus.NOT_EVALUATED
    engineering_depth: int = Field(ge=0, le=ENGINEERING_DEPTH_MAX)
    penalties: list[Penalty] = Field(default_factory=list)
    total_score: int = Field(ge=0, le=100)
    score_evidence: list[ScoreItem] = Field(default_factory=list)

    @classmethod
    def build(
        cls,
        *,
        ai_project_depth: int,
        python_backend: int,
        cloud_fullstack: int,
        engineering_depth: int,
        penalties: list[Penalty],
        score_evidence: list[ScoreItem],
        github: int = 0,
        github_status: GitHubStatus = GitHubStatus.NOT_EVALUATED,
    ) -> "ScoreBreakdown":
        """total_score = sum(categories) - sum(penalties), clamped to 0..100."""
        gross = ai_project_depth + python_backend + cloud_fullstack + github + engineering_depth
        total = max(0, min(100, gross - sum(p.amount for p in penalties)))
        return cls(
            ai_project_depth=ai_project_depth,
            python_backend=python_backend,
            cloud_fullstack=cloud_fullstack,
            github=github,
            github_status=github_status,
            engineering_depth=engineering_depth,
            penalties=penalties,
            total_score=total,
            score_evidence=score_evidence,
        )


class ProcessingStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


class ProcessingError(BaseModel):
    stage: str
    error_type: str
    message: str


class ProjectSummary(BaseModel):
    name: str
    description: str
    technologies: list[str] = Field(default_factory=list)
    ai_signals: list[str] = Field(default_factory=list)
    ai_depth_points: int | None = None  # None for rejected candidates (not scored)
    shallow: bool | None = None
    # Advisory semantic analysis (only when an LLM analysed the candidate successfully)
    semantic_summary: str | None = None
    semantic_depth: str | None = None
    semantic_shallow_wrapper: bool | None = None


class LLMEnrichment(BaseModel):
    """Outcome of the optional LLM semantic analysis. Never contains raw model output."""

    status: Literal["ok", "failed", "unavailable", "skipped"] = "skipped"
    reason: str | None = "not_requested"  # failure category / why skipped
    model: str | None = None
    signals_accepted: int = 0
    rejected_signals: dict[str, int] = Field(default_factory=dict)  # reason -> count
    overall_evidence: list[str] = Field(default_factory=list)
    confidence_notes: list[str] = Field(default_factory=list)


class CandidateResult(BaseModel):
    rank: int | None = None  # only eligible candidates are ranked
    resume_filename: str
    resume_hash: str | None = None
    candidate_name: str | None = None
    email: str | None = None
    github_url: str | None = None
    status: ProcessingStatus = ProcessingStatus.OK
    error: ProcessingError | None = None
    eligible: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    eligibility: EligibilityResult | None = None
    project_summary: list[ProjectSummary] = Field(default_factory=list)
    score_breakdown: ScoreBreakdown | None = None  # None unless eligible
    github_enrichment: GitHubEnrichment = Field(default_factory=GitHubEnrichment)
    llm_enrichment: LLMEnrichment = Field(default_factory=LLMEnrichment)
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


class DuplicateRecord(BaseModel):
    resume_filename: str
    duplicate_of: str
    reason: Literal["identical_file", "identical_text"]


class BatchSummary(BaseModel):
    total_resumes: int
    successfully_parsed: int  # read, extracted and screened (eligible + rejected)
    eligible: int
    rejected: int
    failed: int
    duplicates: int
    llm_status_counts: dict[str, int] = Field(default_factory=dict)  # ok/failed/unavailable/skipped


class ScreeningResults(BaseModel):
    """The contract written to results.json and consumed by the frontend."""

    schema_version: str = SCHEMA_VERSION
    generated_at: datetime
    batch_summary: BatchSummary
    eligible_candidates: list[CandidateResult] = Field(default_factory=list)  # best first
    rejected_candidates: list[CandidateResult] = Field(default_factory=list)
    failed_candidates: list[CandidateResult] = Field(default_factory=list)
    duplicates: list[DuplicateRecord] = Field(default_factory=list)
