"""Screen one candidate: eligibility gate, then scoring for eligible ones only."""

import logging

from app.llm import SemanticOutcome
from app.models import (
    Candidate,
    CandidateResult,
    GitHubEnrichment,
    GitHubStatus,
    LLMEnrichment,
)
from app.screening.ai_depth import analyze_units
from app.screening.eligibility import check_eligibility
from app.screening.explain import (
    build_project_summaries,
    build_strengths_and_concerns,
    semantic_concerns,
)
from app.screening.scoring import score_candidate
from app.screening.semantic import SemanticSignals, ground_signals

logger = logging.getLogger(__name__)


def _prepare_semantic(
    candidate: Candidate, outcome: SemanticOutcome | None
) -> tuple[SemanticSignals | None, LLMEnrichment]:
    """Ground the LLM output. Any problem degrades to deterministic-only scoring."""
    if outcome is None:
        return None, LLMEnrichment(status="skipped", reason="llm_disabled")
    if outcome.status != "ok" or outcome.analysis is None:
        return None, LLMEnrichment(status=outcome.status, reason=outcome.reason, model=outcome.model)
    try:
        signals = ground_signals(candidate.lines, outcome.analysis)
    except Exception as exc:  # defensive: advisory layer must never break screening
        logger.exception("Could not normalise semantic output for %s", candidate.resume_filename)
        return None, LLMEnrichment(
            status="failed", reason=f"normalization_error:{type(exc).__name__}", model=outcome.model
        )
    return signals, LLMEnrichment(
        status="ok",
        model=outcome.model,
        reason=None,
        signals_accepted=signals.accepted,
        rejected_signals=dict(signals.rejected),
        overall_evidence=signals.overall_evidence,
        confidence_notes=signals.confidence_notes,
    )


def _github_concerns(github: GitHubEnrichment) -> list[str]:
    """Informational only: a GitHub problem never changes eligibility or other categories."""
    if github.status in (GitHubStatus.OK, GitHubStatus.NOT_EVALUATED, GitHubStatus.MISSING):
        return []  # a missing link is already reported by the explain step
    return [f"GitHub not scored ({github.status.value}); 0 GitHub points, candidate otherwise unaffected"]


def screen_candidate(
    candidate: Candidate,
    semantic: SemanticOutcome | None = None,
    github: GitHubEnrichment | None = None,
) -> CandidateResult:
    """Eligibility gate, then scoring for eligible candidates.

    ``semantic`` (LLM) and ``github`` (public GitHub signal) are optional and are only
    consulted after the candidate has passed the deterministic eligibility gate.
    """
    eligibility = check_eligibility(candidate)
    base = {
        "resume_filename": candidate.resume_filename,
        "resume_hash": candidate.resume_hash,
        "candidate_name": candidate.candidate_name,
        "email": candidate.email,
        "github_url": candidate.github_url,
        "eligibility": eligibility,
        "matched_skills": eligibility.matched_skills,
    }

    if not eligibility.eligible:
        return CandidateResult(
            **base,
            eligible=False,
            rejection_reasons=eligibility.rejection_reasons,
            project_summary=build_project_summaries(candidate, None),
            concerns=list(candidate.parse_warnings),
            llm_enrichment=LLMEnrichment(status="skipped", reason="not_eligible"),
            github_enrichment=GitHubEnrichment(
                reason="not_eligible",
                profile_url=candidate.github_url,
                summary="GitHub not checked: candidate is not eligible.",
            ),
        )

    signals, enrichment = _prepare_semantic(candidate, semantic)
    units = analyze_units(candidate.lines, signals)
    if github is None:
        github = GitHubEnrichment(
            reason="github_disabled",
            profile_url=candidate.github_url,
            summary="GitHub enrichment was not run.",
        )
    score = score_candidate(candidate, eligibility, signals, github)
    strengths, concerns = build_strengths_and_concerns(candidate, score, units)
    concerns.extend(_github_concerns(github))
    if github.status == GitHubStatus.OK and github.total_points >= 6:
        strengths.append(f"Active, relevant public GitHub presence ({github.total_points}/10)")
    if signals:
        concerns.extend(semantic_concerns(signals))
    return CandidateResult(
        **base,
        eligible=True,
        project_summary=build_project_summaries(candidate, units, signals),
        score_breakdown=score,
        strengths=strengths,
        concerns=concerns,
        llm_enrichment=enrichment,
        github_enrichment=github,
    )
