"""Screen one candidate: eligibility gate, then scoring for eligible ones only."""

import logging

from app.llm import SemanticOutcome
from app.models import Candidate, CandidateResult, GitHubEnrichment, LLMEnrichment
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


def screen_candidate(
    candidate: Candidate, semantic: SemanticOutcome | None = None
) -> CandidateResult:
    """``semantic`` is the optional LLM outcome. It is only consulted for eligible candidates."""
    eligibility = check_eligibility(candidate)
    base = {
        "resume_filename": candidate.resume_filename,
        "resume_hash": candidate.resume_hash,
        "candidate_name": candidate.candidate_name,
        "email": candidate.email,
        "github_url": candidate.github_url,
        "eligibility": eligibility,
        "matched_skills": eligibility.matched_skills,
        "github_enrichment": GitHubEnrichment(profile_url=candidate.github_url),
    }

    if not eligibility.eligible:
        return CandidateResult(
            **base,
            eligible=False,
            rejection_reasons=eligibility.rejection_reasons,
            project_summary=build_project_summaries(candidate, None),
            concerns=list(candidate.parse_warnings),
            llm_enrichment=LLMEnrichment(status="skipped", reason="not_eligible"),
        )

    signals, enrichment = _prepare_semantic(candidate, semantic)
    units = analyze_units(candidate.lines, signals)
    score = score_candidate(candidate, eligibility, signals)
    strengths, concerns = build_strengths_and_concerns(candidate, score, units)
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
    )
