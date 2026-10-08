"""Screen one candidate: eligibility gate, then scoring for eligible ones only."""

from app.models import Candidate, CandidateResult, GitHubEnrichment
from app.screening.ai_depth import analyze_units
from app.screening.eligibility import check_eligibility
from app.screening.explain import build_project_summaries, build_strengths_and_concerns
from app.screening.scoring import score_candidate


def screen_candidate(candidate: Candidate) -> CandidateResult:
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
        )

    units = analyze_units(candidate.lines)
    score = score_candidate(candidate, eligibility)
    strengths, concerns = build_strengths_and_concerns(candidate, score, units)
    return CandidateResult(
        **base,
        eligible=True,
        project_summary=build_project_summaries(candidate, units),
        score_breakdown=score,
        strengths=strengths,
        concerns=concerns,
    )
